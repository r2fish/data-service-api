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
                "contract_version": "1.0.0",
                "capabilities": {
                    "structured_query": {"status": "enabled", "operators": ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "is_null"]},
                    "atomic_mutation": {"status": "enabled", "operations": ["insert", "update", "upsert", "delete"]},
                    "application_catalog": {"status": "enabled"},
                    "schema_operations": {"status": "partial", "operations": schema_ops, "unsupported": ["alter_field", "create_index", "drop_index", "jobs"]},
                    "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                    "best_effort_transactions": {"status": "unavailable"},
                    "idempotency": {"status": "unavailable"},
                    "revision_preconditions": {"status": "unavailable"}
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
                result = self._cells[canonical.application_id].query(entity, select=select, where=predicates, page_size=page_size, limits=self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "data_operation", "query", "allow", "entity", request_id=request_id)
                return result
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
                request = {"entity": entity, "operations": operations}
                self.limits.check_request(request)
                self.limits.check_depth(request)
                deadline = self._clock() + self.limits.execution_ms / 1000
                affected = self._cells[canonical.application_id].transact(entity, operations, self.limits, deadline=deadline, clock=self._clock)
                self._event(canonical, "data_operation", "mutate", "allow", "entity", request_id=request_id)
                return affected
        except FoundationError as exc:
            self._event(context, "operation_denial", "mutate", "deny", "entity", exc.code, request_id=request_id)
            raise

    def schema(self, context: AuthContext, operation: dict[str, Any] | None, *, request_id: str | None = None) -> int:
        try:
            with self._slot(context) as canonical:
                if not isinstance(operation, dict):
                    fail("VALIDATION_FAILED", "Schema operation must be an object.")
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
                self._event(canonical, "data_operation", "catalog", "allow", "entity", request_id=request_id)
                return {"application_scope": canonical.application_id, "entities": entities}
        except FoundationError as exc:
            self._event(context, "authorization_denial", "catalog", "deny", "entity", exc.code, request_id=request_id)
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
