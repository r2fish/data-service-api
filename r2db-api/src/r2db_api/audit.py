"""Canonical append-only security event sink for the foundation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any
import uuid


FORBIDDEN = ("credential", "token", "password", "secret", "private_key", "sql", "row_value")


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_class: str
    occurred_at: str
    request_id: str
    application_id: str | None
    actor_type: str
    actor_id: str | None
    role: str | None
    operation: str
    target_kind: str | None
    outcome: str
    reason_code: str | None

    def as_dict(self) -> MappingProxyType:
        return MappingProxyType({k: v for k, v in self.__dict__.items() if v is not None})


class AuditSink:
    """Append-only in-memory sink; production must supply external governance."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, *, event_class: str, request_id: str, application_id: str | None, actor_type: str, actor_id: str | None, role: str | None, operation: str, target_kind: str | None, outcome: str, reason_code: str | None = None, **extra: Any) -> AuditEvent:
        if any(k.lower() in FORBIDDEN for k in extra):
            raise ValueError("forbidden audit field")
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code)
        self._events.append(event)
        return event

    def events(self) -> tuple[MappingProxyType, ...]:
        return tuple(event.as_dict() for event in self._events)

    def delete(self, *_: Any, **__: Any) -> None:
        raise PermissionError("audit sink is append-only")


class ControlAuditSink:
    """CCR-14 WP-3, R-6: the durable control-plane audit trail's in-memory
    half -- `AuditSink`'s parallel counterpart for `r2dbsvc_registry.
    control_audit` (migration `0006_control_plane_http.sql`), used by
    `ControlPlaneService`'s in-memory backend (`control_plane.py`) and this
    repository's tests. A parallel sink, not a replacement: `DataService`'s
    own `AuditSink` (data-plane events, this module's class above) is
    completely untouched by this class. Same 12-field `AuditEvent` shape and
    the same `FORBIDDEN`-field discipline -- but realized structurally here
    rather than by scanning `**extra` kwargs (this sink's `append` accepts
    only the fixed 12 named fields, so there is no keyword-argument slot a
    caller could ever put a `secret`/`verifier` value into in the first
    place; contrast `AuditSink.append` above, whose `**extra: Any` exists for
    a different, pre-existing reason this class does not need to replicate).

    The Postgres-backed counterpart, `PostgresControlAuditSink`, lives in
    `credential_store.py`, not here -- deliberately mirroring the existing
    `CredentialStore` (this module -- no PostgreSQL dependency)/
    `PostgresCredentialStore` (`credential_store.py`) split, so that this
    module (`audit.py`, imported unconditionally by `service.py`, and
    therefore by the top-level `r2db_api` package) never gains a `psycopg`
    import. `r2db_api/__init__.py`'s own header states this property
    explicitly ("this top-level package stays importable without `psycopg`
    installed at all") -- putting a Postgres-backed class in this file would
    silently break that for every pure in-memory consumer.

    `append(..., work=None)`: `work` is accepted for call-surface symmetry
    with `PostgresControlAuditSink.append` (so `ControlPlaneService` can call
    either sink identically, not knowing which backend it holds), but this
    in-memory sink needs no rollback-participation hook for it, unlike the
    credential stores' own `unit_of_work()`: `append` either fully adds the
    event (the common case) or raises before adding anything at all (the
    `inject_fault` fault-injection path below) -- there is never a partially
    -applied append this class would need to undo if a caller's enclosing
    `with store.unit_of_work() as work:` block later rolls back for some
    *other* reason. That enclosing block's own snapshot/restore already
    covers the state change; this sink's own list is simply never mutated on
    the failure path, so nothing here needs undoing.
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._fault: Exception | None = None

    def inject_fault(self, exc: Exception | None) -> None:
        """Test-only fault injection (CCR-14 WP-3 mutation coverage, M3/M4):
        when `exc` is not `None`, every subsequent `append` call raises it
        instead of recording anything -- simulating "the control_audit sink
        cannot be written" for the in-memory backend, the parity counterpart
        to the Postgres tests' table-rename fault injection (`test_control_
        plane_store.py`'s `ALTER TABLE ... RENAME TO control_audit_fault_
        injected` technique). Pass `None` to clear the fault. Production
        code (`ControlPlaneService`) never calls this."""
        self._fault = exc

    def append(
        self,
        *,
        event_class: str,
        request_id: str,
        application_id: str | None,
        actor_type: str,
        actor_id: str | None,
        role: str | None,
        operation: str,
        target_kind: str | None,
        outcome: str,
        reason_code: str | None = None,
        work: Any = None,
    ) -> AuditEvent:
        del work  # see class docstring -- accepted for call-surface symmetry only
        if self._fault is not None:
            raise self._fault
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code)
        self._events.append(event)
        return event

    def events(self) -> tuple[MappingProxyType, ...]:
        return tuple(event.as_dict() for event in self._events)
