"""Application facade and separately held Control/Provisioning authority."""
from __future__ import annotations

from contextlib import contextmanager
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


class DataService:
    """Public application facade; control state is deliberately private."""

    def __init__(self, credentials: CredentialStore, limits: ResourceLimits | None = None, topology: AuthorityTopology | None = None, audit: AuditSink | None = None, initial_cells: dict[str, StorageBackend] | None = None, clock: Callable[[], float] | None = None, cell_factory: CellFactory | None = None) -> None:
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
            schema_ops = ["create_entity", "add_field", "drop_entity"] if canonical.role == "developer" else []
            return {
                "contract_version": "1.1.0",
                "capabilities": {
                    "structured_query": {"status": "enabled", "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "is_null"]},
                    # Contract 1.1.0 (CCR-13, `structured_operations.
                    # upsert`): upsert's existence test must be the
                    # entity's declared domain uniqueness, which this
                    # foundation does not implement (`CatalogDocument.
                    # entities` has no uniqueness-declaration mechanism
                    # yet -- see `EntityDescriptor.unique_keys`). Declaring
                    # `atomic_mutation` as `enabled` with `upsert` in
                    # `operations`, as before this contract version, would
                    # itself violate `capability_status.rules`'s "must not
                    # be advertised as enabled unless its operations are
                    # executable" the moment `structured.py::bind_mutation`
                    # rejects every upsert with `CAPABILITY_UNSUPPORTED`
                    # (which it now does). `status: partial` plus the
                    # explicit `unsupported` list is what
                    # `schema_operations` right below already does for its
                    # own gaps -- this mirrors that existing pattern rather
                    # than inventing a new one.
                    "atomic_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
                    "application_catalog": {"status": "enabled"},
                    "schema_operations": {"status": "partial", "operations": schema_ops, "unsupported": ["alter_field", "create_index", "drop_index", "jobs"]},
                    "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                    "best_effort_transactions": {"status": "unavailable"},
                    "idempotency": {"status": "unavailable"},
                    "revision_preconditions": {"status": "unavailable"},
                    # Contract 1.1.0 additions (CCR-13/15/14 respectively).
                    # None of the three are implemented by this foundation
                    # yet -- `row_addressability` needs the same catalog
                    # uniqueness/addressability declarations `upsert`
                    # above is waiting on; `cross_entity_mutation` needs
                    # the new `POST /v1/data/mutations` endpoint (stubbed
                    # in `http.py` as CAPABILITY_UNSUPPORTED, not
                    # executable); `control_plane` needs the `/control/v1`
                    # surface (still the provisional out-of-band CLI, `ops.
                    # py`, per docs/design/
                    # R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md
                    # §0's "no HTTP control plane" constraint, unresolved
                    # until CCR-14's in-band-issuance dependent judgment is
                    # implemented). `unavailable`, not `partial`: none of
                    # the three has any executable operation yet, unlike
                    # `atomic_mutation`/`schema_operations` above which do.
                    "row_addressability": {"status": "unavailable"},
                    "cross_entity_mutation": {"status": "unavailable"},
                    "control_plane": {"status": "unavailable"}
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

    def query(self, context: AuthContext, entity: str, *, select: list[str], where: list[dict[str, Any]] | None = None, page_size: int = 100, request_id: str | None = None) -> list[dict[str, Any]]:
        try:
            with self._slot(context) as canonical:
                if not isinstance(select, list) or not isinstance(page_size, int) or isinstance(page_size, bool):
                    fail("VALIDATION_FAILED", "Projection and page size have invalid types.")
                if where is not None and not isinstance(where, list):
                    fail("VALIDATION_FAILED", "Filter must be a list.")
                request = {"entity": entity, "select": select, "where": where or [], "page_size": page_size}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                predicates = [parse_predicate(item) for item in (where or [])]
                deadline = self._clock() + self.limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].query(entity, select=select, where=predicates, page_size=page_size, limits=self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "data_operation", "query", "allow", "entity", request_id=request_id)
                # CCR-13 (docs/design/R2DB_CCR13_STORAGE_V1.md): `query()`
                # now returns a `QueryOutcome` dataclass (items + revisions +
                # pagination continuation) rather than a bare list. This work
                # package does not change this facade's own external contract
                # yet (order_by/cursor rejection stays in `http.py`, and
                # neither revisions nor next_page reach a caller here) --
                # only the storage-layer return shape changed, so only the
                # plain item list is unwrapped and returned, unchanged from
                # before.
                return list(outcome.items)
        except FoundationError as exc:
            self._event(context, "authorization_denial", "query", "deny", "entity", exc.code, request_id=request_id)
            raise

    def mutate(self, context: AuthContext, entity: str, operations: list[dict[str, Any]], *, transaction: str = "atomic", request_id: str | None = None) -> int:
        try:
            with self._slot(context) as canonical:
                if transaction != "atomic":
                    fail("CAPABILITY_UNSUPPORTED", "This foundation exposes atomic transactions only.")
                if not isinstance(operations, list):
                    fail("VALIDATION_FAILED", "Mutations must be a list.")
                # --- WP-2-through-WP-5 provisional gate (design R2DB_CCR13_
                # STORAGE_V1.md §3, "WP-2〜WP-5 の乖離封鎖", WP-2 review
                # blocker B-1) -----------------------------------------------
                # The shared bind boundary (`structured.bind_mutation`) now
                # structurally accepts `expected_revision` and `upsert`
                # regardless of what `capabilities()` currently declares --
                # deciding whether either is actually executable needs live
                # catalog knowledge only a backend has (declared unique keys,
                # a revision column), which C-12's own declared-implies-
                # executable check cannot see the *reverse* of (declared
                # unavailable/unsupported, yet observably executes). Refuse
                # both here, unconditionally, until `capabilities()` is
                # updated in the same commit as WP-5. REMOVE THIS BLOCK in
                # that commit -- `structured.py`'s own semantics (entity-
                # scoped upsert eligibility, real precondition resolution)
                # take over once the declaration catches up.
                for item in operations:
                    if isinstance(item, dict) and (item.get("operation") == "upsert" or "expected_revision" in item):
                        fail("CAPABILITY_UNSUPPORTED", "This foundation does not yet expose upsert or revision preconditions.")
                request = {"entity": entity, "operations": operations}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                deadline = self._clock() + self.limits.execution_ms / 1000
                outcome = self._cells[canonical.application_id].transact(entity, operations, self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "data_operation", "mutate", "allow", "entity", request_id=request_id)
                # CCR-13: `transact()` now returns a `MutationOutcome`
                # dataclass (affected count + resolved insert addresses)
                # rather than a bare int -- see the identical note in
                # `query()` above. `assigned_addresses` does not reach a
                # caller here yet (WP-4); only the affected count is
                # unwrapped and returned.
                return outcome.affected
        except FoundationError as exc:
            self._event(context, "operation_denial", "mutate", "deny", "entity", exc.code, request_id=request_id)
            raise

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None) -> int:
        try:
            with self._slot(context) as canonical:
                if not isinstance(operation, dict):
                    fail("VALIDATION_FAILED", "Schema operation must be an object.")
                # WP-2 confirmation-review fix M-A: authority is checked
                # here, before the provisional gate below, so a non-
                # developer credential still gets pre-WP-2's FORBIDDEN/403
                # for *any* schema operation -- including `create_index`/
                # `drop_index`/`field_type`, which the gate below would
                # otherwise answer with CAPABILITY_UNSUPPORTED/400 first
                # (the gate has no idea who is asking; `bind_schema_
                # operation`'s own `if not developer: fail FORBIDDEN` is
                # what used to run first for every schema operation before
                # this gate existed, and this restores that precedence).
                if canonical.role != "developer":
                    fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
                # --- WP-2-through-WP-5 provisional gate (see the identical
                # note in `mutate()` above) --------------------------------
                # `create_index`/`drop_index` are now structurally accepted
                # by `structured.bind_schema_operation`, and `field_type` is
                # now accepted on `add_field` -- none of that is declared
                # (`schema_operations.unsupported` still lists `create_index`/
                # `drop_index`; `field_type` has no declared capability of
                # its own but was rejected pre-WP-2 as an unrecognized key).
                # Refuse both here until `capabilities()` catches up in the
                # same commit as WP-5. REMOVE THIS BLOCK in that commit.
                if operation.get("operation") in {"create_index", "drop_index"}:
                    fail("CAPABILITY_UNSUPPORTED", "This foundation does not yet expose index declarations.")
                if "field_type" in operation:
                    fail("VALIDATION_FAILED", "field_type is not a recognized field.")
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
                entities = self._cells[canonical.application_id].catalog()
                # --- WP-2-through-WP-5 provisional gate (see the identical
                # note in `mutate()` above) --------------------------------
                # `ApplicationCell.catalog()` now always publishes the full
                # CCR-13 `EntityDescriptor` (mutation_class/address_fields/
                # address_reuse/unique_keys), but `row_addressability` is
                # still declared `unavailable`. Narrow the published shape
                # back to the pre-WP-2 `{entity, fields}` until
                # `capabilities()` catches up in the same commit as WP-5.
                # REMOVE THIS narrowing in that commit. `id`'s appearance in
                # `fields` is left untouched -- it is a storage fact (a
                # reserved, always-present field name), not a capability
                # declaration, and is independent of whether addressability
                # itself is announced.
                entities = [{"entity": item["entity"], "fields": item["fields"]} for item in entities]
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

    def set_credential_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None) -> None:
        try:
            self._service._credentials.set_state(credential_id, enabled=enabled, revoked=revoked)
            self._control_event("credential_lifecycle", "set_credential_state", "allow", credential_id)
        except FoundationError as exc:
            self._control_event("control_failure", "set_credential_state", "deny", credential_id, exc.code)
            raise

    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str) -> None:
        try:
            if application_id not in self._service._cells:
                fail("NOT_FOUND", "Application was not found.", status=404)
            self._service._credentials.add(credential_id, application_id, role, secret)
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
