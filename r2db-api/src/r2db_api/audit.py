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
    # Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
    # §1-C/§4): contract `audit.fields`' 13th, optional field -- "set when
    # the event has a single target credential/application, omitted
    # otherwise" (the contract text's own optionality note; `audit.fields`
    # is an additive vocabulary, not a fixed column set). Defaulted so every
    # pre-WP-4 positional `AuditEvent(...)` construction (this file's own
    # `AuditSink.append` below, and any other 12-positional-arg call site)
    # keeps working unchanged, with `target_id` simply absent (`as_dict()`'s
    # own None-filtering already omits it, matching the optional wire
    # semantics with no special-casing needed here).
    target_id: str | None = None
    # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-3/D-4): the
    # 14th column `application_audit`/`control_audit`'s durable schema adds
    # beyond contract `audit.fields`' 13 -- "this row represents `count`
    # occurrences, NULL means 1". Only D-4's buffer-overflow alert row and
    # D-3's coalesced-denial summary row ever set this to a concrete int;
    # every other event leaves it `None`. Carried on the shared `AuditEvent`
    # dataclass (not a `control_audit`/`application_audit`-only subclass)
    # so `ControlAuditSink`/`AuditSink`/`ApplicationAuditSink` all construct
    # the same event shape -- `control_audit` itself never receives a
    # non-`None` value here (0006's table has no such column, and D-4/D-3
    # are application-plane-only mechanisms), but the *type* stays uniform.
    count: int | None = None

    def as_dict(self) -> MappingProxyType:
        return MappingProxyType({k: v for k, v in self.__dict__.items() if v is not None})


class AuditSink:
    """Append-only in-memory sink; production must supply external governance."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, *, event_class: str, request_id: str, application_id: str | None, actor_type: str, actor_id: str | None, role: str | None, operation: str, target_kind: str | None, outcome: str, reason_code: str | None = None, target_id: str | None = None, **extra: Any) -> AuditEvent:
        if any(k.lower() in FORBIDDEN for k in extra):
            raise ValueError("forbidden audit field")
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id)
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
        target_id: str | None = None,
        work: Any = None,
    ) -> AuditEvent:
        del work  # see class docstring -- accepted for call-surface symmetry only
        if self._fault is not None:
            raise self._fault
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id)
        self._events.append(event)
        return event

    def events(self) -> tuple[MappingProxyType, ...]:
        return tuple(event.as_dict() for event in self._events)


class ApplicationAuditSink:
    """Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10): the
    durable application-plane audit trail's in-memory half -- `AuditSink`'s
    (this module's first class, above) durable-designated sibling for
    `r2dbsvc_registry.application_audit` (migration `0007_application_
    audit.sql`), mirroring `ControlAuditSink`'s relationship to `control_
    audit` one-for-one.

    A *separate* sink from `AuditSink`, not a replacement for it (D-10's
    own instruction: the pre-existing in-memory `AuditSink` stays the sole
    recorder for D-3's 4 non-durable denial classes -- `VALIDATION_FAILED`/
    `LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND` -- which never
    reach this class at all). Every event `DataService`'s dispatch logic
    (`service.py`) classifies as fail-closed, coalesced-denial, or
    buffer-class is appended here (or to `PostgresApplicationAuditSink`,
    `credential_store.py`'s Postgres-backed counterpart) instead.

    `append_many` exists for D-4's buffer flush (`service.py`'s bounded
    buffer always drains in one batch call, never one `append()` per
    buffered event) -- `ControlAuditSink` has no equivalent because
    control-plane events are never buffered (every `control_audit` row is
    written synchronously, one event at a time).

    `inject_fault`/`work` mirror `ControlAuditSink`'s identical mechanisms
    one-for-one; see that class's docstring for the full rationale, which
    applies here unchanged.
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._fault: Exception | None = None

    def inject_fault(self, exc: Exception | None) -> None:
        """Test-only fault injection (Phase 4 mutation coverage, the
        `application_audit` parity counterpart to `ControlAuditSink.
        inject_fault`): when `exc` is not `None`, every subsequent
        `append`/`append_many` call raises it instead of recording
        anything. Pass `None` to clear. Production code never calls this."""
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
        target_id: str | None = None,
        count: int | None = None,
        work: Any = None,
    ) -> AuditEvent:
        del work  # call-surface symmetry with `PostgresApplicationAuditSink.append` only
        if self._fault is not None:
            raise self._fault
        event = AuditEvent(str(uuid.uuid4()), event_class, datetime.now(timezone.utc).isoformat(), request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count)
        self._events.append(event)
        return event

    def append_many(self, events: "list[AuditEvent]") -> None:
        """D-4's buffer-flush batch write -- either every event in `events`
        is recorded, or (on injected/simulated failure) none is: this
        mirrors the all-or-nothing character of `PostgresApplicationAuditSink.
        append_many`'s real single-statement multi-row `INSERT`, so a caller
        cannot observe a partially-flushed buffer from either backend.
        """
        if self._fault is not None:
            raise self._fault
        self._events.extend(events)

    def events(self) -> tuple[MappingProxyType, ...]:
        return tuple(event.as_dict() for event in self._events)


__all__ = ["FORBIDDEN", "AuditEvent", "AuditSink", "ControlAuditSink", "ApplicationAuditSink"]
