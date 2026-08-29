"""Application facade and separately held Control/Provisioning authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Iterator
import uuid

from .audit import AuditSink
from .auth import AuthContext, CredentialStore
from .backend import StorageBackend
from .errors import FoundationError, fail
from .limits import ResourceLimits
from .structured import ApplicationCell, parse_predicate
from .topology import AuthorityTopology

# Default cell factory (design D-1 step 2): builds the existing in-memory
# `ApplicationCell`, unchanged, so every caller that does not pass
# `cell_factory` gets exactly today's behavior. A deployment that wants
# `PostgresCell` (or any other `StorageBackend`) instead passes its own
# factory -- `DataService` itself never imports `postgres.py` or references
# PostgreSQL, keeping this module backend-agnostic (D-1: "in-memory backend
# and PostgreSQL backend pass through the same validation boundary" without
# either backend leaking into this facade).
CellFactory = Callable[[str, dict[str, list[dict[str, Any]]] | None], StorageBackend]


def _default_cell_factory(application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> StorageBackend:
    return ApplicationCell(application_id, entities or {})


@dataclass(frozen=True)
class QueryPage:
    """`DataService.query_page`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `QueryResult` (CCR-13 WP-4 introduced
    `items`/`next_page`; WP-5 adds `revisions`, index-aligned with `items`,
    now that `revision_preconditions` is declared `enabled`). `next_page`
    is the opaque cursor for the next page (`QueryOutcome.next_cursor`,
    `r2db_api.structured`), or `None` when this was the last page.
    """

    items: list[dict[str, Any]]
    next_page: str | None
    revisions: list[str]


@dataclass(frozen=True)
class MutationResult:
    """`DataService.mutate_result`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `MutationResult` minus `committed`
    (added by `http.post_mutate` itself, which is always `True` for a
    response that reaches this point at all -- an atomic batch that failed
    partway through never returns anything, it raises). Mirrors the
    `query`/`query_page` split (WP-4): `mutate` below stays byte-for-byte
    backward compatible (a bare `int`, the affected count) for every
    existing caller (`tests/test_foundation.py`, the in-process conformance
    adapter); this richer shape reaches only the HTTP boundary, which needs
    `assigned_addresses` to build the contract's own response. `entity` is
    never present on any element here (contract: only the cross-entity
    endpoint's own elements name their entity; this is the per-entity
    endpoint's shape).
    """

    affected: int
    assigned_addresses: list[dict[str, Any]]


class DataService:
    """Public application facade; control state is deliberately private."""

    def __init__(self, credentials: CredentialStore, limits: ResourceLimits | None = None, topology: AuthorityTopology | None = None, audit: AuditSink | None = None, initial_cells: dict[str, StorageBackend] | None = None, clock: Callable[[], float] | None = None, cell_factory: CellFactory | None = None, control_plane_status: str = "unavailable") -> None:
        # R-9 (CCR-14 WP-5, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
        # §1: "capability 申告は環境変数由来で composition root 注入"):
        # whether this application-plane process' own `capabilities()`
        # declares `control_plane: enabled` is a *deployer* fact this class
        # cannot know on its own (a separated `/control/v1` deployment, the
        # default, means the application-plane process has no idea whether a
        # control-plane process is running anywhere at all) -- it is
        # constructor-injected, defaulting to the safe, honest `unavailable`
        # so nothing short of an explicit composition-root decision
        # (`main.py`, reading `R2DB_CONTROL_PLANE_STATUS`) ever declares
        # `enabled`. Validated here too (not only at `main.py`'s env-parsing
        # boundary) so any other caller constructing a `DataService` directly
        # (this repository's own tests, the WP-5 in-process conformance
        # adapter) gets the same fail-loud guard against a typo'd status
        # string, rather than silently publishing an invalid capability
        # value.
        if control_plane_status not in {"enabled", "unavailable"}:
            raise ValueError("control_plane_status must be 'enabled' or 'unavailable'")
        self._control_plane_status = control_plane_status
        self._credentials = credentials
        self.limits = limits or ResourceLimits()
        self.topology = topology or AuthorityTopology()
        self._audit = audit or AuditSink()
        self._cell_factory: CellFactory = cell_factory or _default_cell_factory
        self._cells: dict[str, StorageBackend] = dict(initial_cells or {})
        self._disabled_apps: set[str] = set()
        self._active = 0
        self._active_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._rate_windows: dict[str, list[float]] = {}
        self._clock = clock or time.monotonic
        self.topology.validate()

    def authenticate(self, secret: str | None, *, request_id: str | None = None) -> AuthContext:
        try:
            context = self._credentials.authenticate(secret)
            if context.application_id in self._disabled_apps:
                fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
            self._event(context, "authentication", "authenticate", "allow", "application", request_id=request_id)
            return context
        except FoundationError as exc:
            self._audit.append(event_class="authentication_denial", request_id=request_id or str(uuid.uuid4()), application_id=None, actor_type="unknown", actor_id=None, role=None, operation="authenticate", target_kind="application", outcome="deny", reason_code=exc.code)
            raise

    def capabilities(self, context: AuthContext) -> dict[str, Any]:
        with self._slot(context) as canonical:
            # CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design
            # R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit
            # (see `query`/`mutate`/`schema`/`catalog` below) -- this
            # declaration update is what makes that removal honest rather
            # than a new C-12 "declared unavailable, executes anyway" gap.
            schema_ops = ["create_entity", "add_field", "create_index", "drop_index", "drop_entity"] if canonical.role == "developer" else []
            return {
                "contract_version": "1.1.0",
                "capabilities": {
                    "structured_query": {"status": "enabled", "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "matches", "is_null"]},
                    # Contract 1.1.0 (CCR-13, `structured_operations.
                    # upsert`): `upsert`'s existence test is the entity's
                    # own declared domain uniqueness (`EntityDescriptor.
                    # unique_keys`, `application_catalog` below) -- an
                    # entity with no declared uniqueness key still refuses
                    # `upsert` with `CAPABILITY_UNSUPPORTED` (structured.py::
                    # bind_mutation/_apply_upsert), but that is a per-entity
                    # condition the catalog itself communicates, not a
                    # service-wide gap `atomic_mutation` needs to qualify.
                    "atomic_mutation": {"status": "enabled", "operations": ["insert", "update", "upsert", "delete"]},
                    "application_catalog": {"status": "enabled"},
                    "schema_operations": {"status": "partial", "operations": schema_ops, "unsupported": ["alter_field", "jobs"]},
                    "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                    "best_effort_transactions": {"status": "unavailable"},
                    "idempotency": {"status": "unavailable"},
                    "revision_preconditions": {"status": "enabled"},
                    "row_addressability": {"status": "enabled"},
                    # `cross_entity_mutation` needs the new `POST /v1/data/
                    # mutations` endpoint (stubbed in `http.py` as
                    # CAPABILITY_UNSUPPORTED, not executable); `control_
                    # plane` needs the `/control/v1` surface (still the
                    # provisional out-of-band CLI, `ops.py`, per docs/
                    # design/R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_
                    # ROOT_V1.md §0's "no HTTP control plane" constraint,
                    # unresolved until CCR-14's in-band-issuance dependent
                    # judgment is implemented). Both remain `unavailable`:
                    # neither has any executable operation at all.
                    "cross_entity_mutation": {"status": "unavailable"},
                    # R-9: reflects this instance's own constructor-injected
                    # deployer declaration -- never hardcoded (see __init__'s
                    # comment on this field).
                    "control_plane": {"status": self._control_plane_status}
                },
                "limits": self.limits.as_dict(),
                "limit_enforcement": {name: "reference_wall_clock" if name == "execution_ms" else "enforced" for name in self.limits.as_dict()},
                # `_check()` (called by `_slot()` above) re-validates
                # credential/application authorization state on every
                # single application-plane operation; there is no cache, so
                # revoke/disable/state-unavailable propagation is
                # synchronous (see also the identical reasoning in
                # `conformance/conformance_adapter_r2db.py`'s
                # `propagation_bound_ms()`).
                "authorization_propagation_bound_ms": 0,
                "application_scope": canonical.application_id,
                "role": canonical.role
            }

    def query(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        """Plain-item-list form, unchanged in shape since before CCR-13
        (every existing caller -- `tests/test_foundation.py`, the in-process
        conformance adapter -- keeps working against exactly this return
        type). `order_by`/`cursor` (CCR-13 WP-4) are accepted here too (so
        this method alone is enough to exercise/test them against the
        facade), but the pagination continuation itself only reaches a
        caller through `query_page` below, which `http.post_query` uses.
        """
        return list(self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id).items)

    def query_page(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, order_by: list[dict[str, Any]] | None = None, cursor: str | None = None, request_id: str | None = None) -> "QueryPage":
        """The HTTP-facing shape (`{items, next_page, revisions}`,
        `spec/data-service-api.v1.json`'s `QueryResult`) -- used by `http.
        post_query` instead of `query` above, since building a real
        `next_page`/`revisions` needs `QueryOutcome.next_cursor`/
        `.revisions`, which the plain-list `query()` deliberately does not
        expose (kept byte-for-byte backward compatible with every pre-
        CCR-13 caller). `revisions` is always index-aligned with `items`:
        `revision_preconditions` is declared `enabled`, and every entity
        both cells provision is `mutable`, so a query response always
        carries revisions (R-4).
        """
        outcome = self._query_outcome(context, entity, select=select, where=where, page_size=page_size, order_by=order_by, cursor=cursor, request_id=request_id)
        return QueryPage(items=list(outcome.items), next_page=outcome.next_cursor, revisions=list(outcome.revisions or []))

    def _query_outcome(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None, page_size: int, order_by: list[dict[str, Any]] | None, cursor: str | None, request_id: str | None):
        try:
            with self._slot(context) as canonical:
                if not isinstance(select, list) or not isinstance(page_size, int) or isinstance(page_size, bool):
                    fail("VALIDATION_FAILED", "Projection and page size have invalid types.")
                if where is not None and not isinstance(where, list):
                    fail("VALIDATION_FAILED", "Filter must be a list.")
                if order_by is not None and not isinstance(order_by, list):
                    fail("VALIDATION_FAILED", "order_by must be a list.")
                if cursor is not None and not isinstance(cursor, str):
                    fail("VALIDATION_FAILED", "Cursor must be a string.")
                request = {"entity": entity, "select": select, "where": where or [], "page_size": page_size, "order_by": order_by or [], "cursor": cursor}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                predicates = [parse_predicate(item) for item in (where or [])]
                deadline = self._clock() + self.limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].query(
                    entity, select=select, where=predicates, page_size=page_size, order_by=order_by, cursor=cursor, limits=self.limits, deadline=deadline, clock=self._clock
                )
                self._event(canonical, "data_operation", "query", "allow", "entity", request_id=request_id)
                return outcome
        except FoundationError as exc:
            self._event(context, "authorization_denial", "query", "deny", "entity", exc.code, request_id=request_id)
            raise

    def mutate(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> int:
        """Plain affected-count form, unchanged in shape since before
        CCR-13 (every existing caller -- `tests/test_foundation.py`, the
        in-process conformance adapter -- keeps working against exactly
        this return type). `mutate_result` below is the richer shape
        `http.post_mutate` uses.
        """
        return self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id).affected

    def mutate_result(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> "MutationResult":
        """The HTTP-facing shape (`{affected, assigned_addresses}`,
        `spec/data-service-api.v1.json`'s `MutationResult`) -- used by
        `http.post_mutate` instead of `mutate` above, mirroring the
        `query`/`query_page` split (WP-4/WP-5)."""
        outcome = self._mutate_outcome(context, entity, operations, transaction=transaction, request_id=request_id)
        return MutationResult(affected=outcome.affected, assigned_addresses=list(outcome.assigned_addresses or []))

    def _mutate_outcome(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str, request_id: str | None):
        try:
            with self._slot(context) as canonical:
                if transaction != "atomic":
                    fail("CAPABILITY_UNSUPPORTED", "This foundation exposes atomic transactions only.")
                if not isinstance(operations, list):
                    fail("VALIDATION_FAILED", "Mutations must be a list.")
                request = {"entity": entity, "operations": operations}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                deadline = self._clock() + self.limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].transact(entity, operations, self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "data_operation", "mutate", "allow", "entity", request_id=request_id)
                return outcome
        except FoundationError as exc:
            self._event(context, "operation_denial", "mutate", "deny", "entity", exc.code, request_id=request_id)
            raise

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None) -> int:
        try:
            with self._slot(context) as canonical:
                if not isinstance(operation, dict):
                    fail("VALIDATION_FAILED", "Schema operation must be an object.")
                # Authority is checked before touching request content at
                # all, so a non-developer credential gets FORBIDDEN/403 for
                # any schema operation, before any shape/capability
                # question is even considered.
                if canonical.role != "developer":
                    fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
                self.limits.check_request(operation)
                self.limits.check_depth(operation)
                deadline = self._clock() + self.limits.execution_ms / 1000
                revision = self._cells[canonical.application_id].apply_schema(operation, developer=canonical.role == "developer", limits=self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "privilege_sensitive", "schema", "allow", "entity", request_id=request_id)
                return revision
        except FoundationError as exc:
            self._event(context, "privilege_denial", "schema", "deny", "entity", exc.code, request_id=request_id)
            raise

    def catalog(self, context: AuthContext, *, request_id: str | None = None) -> dict[str, Any]:
        try:
            with self._slot(context) as canonical:
                # The full CCR-13 `EntityDescriptor` shape (mutation_class/
                # address_fields/address_reuse/unique_keys) -- `row_
                # addressability` is now declared `enabled`, so this
                # publishes exactly what the cell itself already computes,
                # with no narrowing.
                entities = self._cells[canonical.application_id].catalog()
                self._event(canonical, "data_operation", "catalog", "allow", "entity", request_id=request_id)
                return {"application_scope": canonical.application_id, "entities": entities}
        except FoundationError as exc:
            self._event(context, "authorization_denial", "catalog", "deny", "entity", exc.code, request_id=request_id)
            raise

    def deny_unsupported(self, context: AuthContext, operation: str, message: str, *, request_id: str | None = None) -> None:
        """Refuse a capability this foundation does not implement, while
        still passing through `_slot`'s rate/concurrency accounting and
        emitting a denial audit event -- exactly like every other
        application-plane method below, instead of being a bare pre-`_slot`
        `fail()` call that an unauthenticated-looking credential could
        spend for free (review R12).

        `http.py`'s `post_audit_query`/`post_cross_entity_mutate` stub
        handlers use this for the two contract endpoints this foundation
        declares `unavailable`/has no execution path for at all
        (`audit_query`, `cross_entity_mutation`); this always raises
        `CAPABILITY_UNSUPPORTED`, it never returns.
        """
        try:
            with self._slot(context):
                fail("CAPABILITY_UNSUPPORTED", message)
        except FoundationError as exc:
            self._event(context, "operation_denial", operation, "deny", "entity", exc.code, request_id=request_id)
            raise

    @contextmanager
    def _slot(self, context: AuthContext) -> Iterator[AuthContext]:
        canonical = self._check(context)
        self._acquire_rate(canonical)
        with self._active_lock:
            if self._active >= self.limits.concurrency:
                fail("LIMIT_EXCEEDED", "Concurrency limit exceeded.", status=429, details={"resource": "concurrency", "limit": self.limits.concurrency})
            self._active += 1
        try:
            yield canonical
        finally:
            with self._active_lock:
                self._active -= 1

    def _check(self, context: AuthContext) -> AuthContext:
        if not isinstance(context, AuthContext):
            fail("AUTH_INVALID", "Authentication context is invalid.", status=401)
        canonical = self._credentials.assert_active(context)
        if canonical.application_id in self._disabled_apps:
            fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
        if canonical.application_id not in self._cells:
            fail("FORBIDDEN", "Application scope is unavailable.", status=403)
        return canonical

    def _acquire_rate(self, context: AuthContext) -> None:
        now = self._clock()
        with self._rate_lock:
            window = self._rate_windows.setdefault(context.credential_id, [])
            window[:] = [stamp for stamp in window if now - stamp < 60]
            if len(window) >= self.limits.requests_per_minute:
                fail("LIMIT_EXCEEDED", "Request rate limit exceeded.", status=429, details={"resource": "requests_per_minute", "limit": self.limits.requests_per_minute})
            window.append(now)

    def _event(self, context: AuthContext, event_class: str, operation: str, outcome: str, target_kind: str, reason_code: str | None = None, *, request_id: str | None = None) -> None:
        canonical = self._credentials.canonical_context(context)
        self._audit.append(event_class=event_class, request_id=request_id or str(uuid.uuid4()), application_id=canonical.application_id if canonical else None, actor_type="application_credential" if canonical else "unknown", actor_id=canonical.credential_id if canonical else None, role=canonical.role if canonical else None, operation=operation, target_kind=target_kind, outcome=outcome, reason_code=reason_code)

    def _register_application(self, application_id: str, entities: dict[str, list[dict[str, Any]]] | None = None) -> None:
        if application_id in self._cells:
            fail("CONFLICT", "Application already exists.", status=409)
        self._cells[application_id] = self._cell_factory(application_id, entities)

    def _set_application_disabled(self, application_id: str, disabled: bool) -> None:
        if application_id not in self._cells:
            fail("NOT_FOUND", "Application was not found.", status=404)
        if disabled:
            self._disabled_apps.add(application_id)
        else:
            self._disabled_apps.discard(application_id)


class ControlAuthority:
    """Trusted lifecycle authority; it is not an application API capability."""

    def __init__(self, service: DataService) -> None:
        self._service = service

    def register_application(self, application_id: str, *, entities: dict[str, list[dict[str, Any]]] | None = None) -> None:
        try:
            self._service._register_application(application_id, entities)
            self._control_event("application_lifecycle", "register_application", "allow", application_id)
        except FoundationError as exc:
            self._control_event("control_failure", "register_application", "deny", application_id, exc.code)
            raise

    def set_application_enabled(self, application_id: str, enabled: bool) -> None:
        try:
            if not isinstance(enabled, bool):
                fail("VALIDATION_FAILED", "Application enabled state must be boolean.")
            self._service._set_application_disabled(application_id, not enabled)
            self._control_event("application_lifecycle", "enable_application" if enabled else "disable_application", "allow", application_id)
        except FoundationError as exc:
            self._control_event("control_failure", "enable_application" if enabled else "disable_application", "deny", application_id, exc.code)
            raise

    def set_credential_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: Any = None) -> None:
        """`work` is keyword-only and defaults to `None` (CCR-14 WP-3): when
        omitted, this method self-manages exactly as before -- opens its own
        `unit_of_work()`, commits/reverts exactly one call's worth of state,
        and every pre-WP-3 caller (this repository's own tests, the
        in-process conformance adapter) keeps working unchanged. When a
        caller supplies its own already-open `work` handle (`ControlPlane
        Service`'s in-memory backend, WP-3: it needs the credential-state
        change and its own `control_audit` sink append to land in the *same*
        transaction, R-6), this method uses that handle directly instead of
        opening a second one -- never both. `work`'s type is deliberately
        untyped (`Any`) rather than importing `auth._InMemoryWork`/
        `credential_store._PostgresWork` here: this module stays agnostic to
        which store implementation (in-memory or PostgreSQL) it is holding,
        exactly as it already is everywhere else (`self._service._credentials`
        is never type-narrowed in this class)."""
        try:
            if work is not None:
                self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)
            else:
                # R-6/§8 B-2: chase `CredentialStore`/`PostgresCredentialStore`'s
                # new `unit_of_work()`-required call form -- semantics are
                # unchanged (this still commits/reverts exactly one call's
                # worth of state, same as before WP-2; `ControlAuthority`'s own
                # audit trail stays on the existing in-memory `AuditSink` below,
                # not on the new `control_audit` table, which only `ops.py`'s
                # ritual/CLI-path writes to in this work package).
                with self._service._credentials.unit_of_work() as own_work:
                    self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=own_work)
            self._control_event("credential_lifecycle", "set_credential_state", "allow", credential_id)
        except FoundationError as exc:
            self._control_event("control_failure", "set_credential_state", "deny", credential_id, exc.code)
            raise

    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str, *, work: Any = None) -> None:
        """`work` is keyword-only, defaulting to `None` -- see `set_credential_
        state`'s docstring immediately above for the full CCR-14 WP-3
        rationale; identical reasoning applies here."""
        try:
            if application_id not in self._service._cells:
                fail("NOT_FOUND", "Application was not found.", status=404)
            if work is not None:
                self._service._credentials.add(credential_id, application_id, role, secret, work=work)
            else:
                with self._service._credentials.unit_of_work() as own_work:
                    self._service._credentials.add(credential_id, application_id, role, secret, work=own_work)
            self._control_event("credential_lifecycle", "issue_credential", "allow", application_id)
        except FoundationError as exc:
            self._control_event("control_failure", "issue_credential", "deny", application_id, exc.code)
            raise

    def audit_events(self) -> tuple[Any, ...]:
        """Read-only evidence view; application facade has no audit accessor."""
        return self._service._audit.events()

    def delete_audit(self) -> None:
        try:
            self._service._audit.delete()
        except PermissionError:
            self._control_event("control_failure", "delete_audit", "deny", "audit", "AUDIT_APPEND_ONLY")
            raise

    def set_authorization_state_available(self, available: bool) -> None:
        try:
            if not isinstance(available, bool):
                fail("VALIDATION_FAILED", "Authorization state availability must be boolean.")
            self._service._credentials.available = available
            self._control_event("control_state", "set_authorization_state_available", "allow", "authorization")
        except FoundationError as exc:
            self._control_event("control_failure", "set_authorization_state_available", "deny", "authorization", exc.code)
            raise

    def _control_event(self, event_class: str, operation: str, outcome: str, target: str, reason_code: str | None = None) -> None:
        target_app = target if target in self._service._cells else self._service._credentials.application_id_for(target)
        self._service._audit.append(event_class=event_class, request_id=str(uuid.uuid4()), application_id=target_app, actor_type="control_authority", actor_id=None, role="control", operation=operation, target_kind="application_or_credential", outcome=outcome, reason_code=reason_code)
