"""Durable, control-plane audit evidence (design v1.2 R-4/R-6, WP-4; field
count updated to 13 by Phase 3.5 WP-5's `target_id` addition, §1-C/§4).

Distinct from `audit.AuditSink`: that class is the foundation's own
6-field, application-plane-only evidence sink (`event_type`/`application_id`/
`credential_id`/`outcome`/`detail`/`occurred_at`). The common contract's own
`audit.fields` (`spec/data-service-api.v1.json`) names 13 columns as of
contract 1.3.0 (12 through 1.2.0, plus the optional `target_id`); this
module is the control plane's own emitter of exactly those fields, for
both the in-memory (`ControlAuditSink`) and PostgreSQL (`insert_control_
audit_row`, against migration `0002_registry_and_functions.sql`'s own
`control_audit` table) backends.

`control_plane.ControlPlaneService` requires every state change and every
authentication/authorization/capability denial to append one of these
events IN THE SAME TRANSACTION as the state change/denial decision itself
(design R-6) -- this module supplies the event shape and each backend's own
append primitive; `control_plane.py` owns the transaction boundary (an
in-memory undo-log `work` token, or a real `psycopg` connection/transaction).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional
import uuid

import psycopg
from psycopg import sql

from .errors import AuthorizationStateUnavailable, StorageConfigurationError
from .identifiers import validate_identifier

# Contract `audit.fields` (spec/data-service-api.v1.json), verbatim order.
#
# Phase 3.5 WP-5, 2026-08-31 (design docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-C/§4, B-1 measure, P35-D14):
# `target_id` appended -- the contract's 13th, optional `audit.fields`
# member ("set when the event has a single target credential/application,
# omitted otherwise"). WP-1 loosened `test_control_plane_service.py`'s own
# contract-agreement test to inclusion specifically so this addition would
# not go red for a reason unrelated to this file; that test is restored to
# exact 13-field set equality in this same WP.
CONTROL_AUDIT_FIELDS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome",
    "reason_code", "target_id",
)


@dataclass(frozen=True)
class ControlAuditEvent:
    event_id: str
    event_class: str
    occurred_at: str
    request_id: Optional[str]
    application_id: Optional[str]
    actor_type: Optional[str]
    actor_id: Optional[str]
    role: Optional[str]
    operation: str
    target_kind: Optional[str]
    outcome: str
    reason_code: Optional[str]
    # Phase 3.5 WP-5 (§1-C/§4): the single target credential_id/
    # application_id this event acted on, when one exists. Defaulted so
    # every existing keyword-constructed `ControlAuditEvent(...)` call site
    # keeps working unchanged, with `target_id` simply `None`.
    target_id: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


class ControlAuditSink:
    """In-memory, append-only, 13-field control-plane audit trail (Phase 3.5
    WP-5: `target_id` added, §1-C/§4).

    A deliberately separate object from `audit.AuditSink` (design v1.2 R-6
    independent-review note m-3: "in-process control 監査 shape も契約
    audit.fields の12フィールド"). Ordering is this list's own append order:
    a single process, under `control_plane.py`'s own external lock (see
    `InMemoryControlBackend`), already serializes every append, so append
    order alone is a stable, gap-free ordering (this backend's own
    in-process analogue of PostgreSQL's `audit_seq` bigserial, R-4/m-2 --
    a real cross-process sequence is unnecessary here because there is only
    ever one process holding the lock).

    `append(..., work=...)` participates in `control_plane.py`'s own shared
    undo-log "unit of work" technique: when `work` is supplied, a rollback
    of that unit removes the just-appended event, so a fault raised *after*
    this append (elsewhere in the same body) also erases it, and a fault
    raised *by this append itself* (see `inject_fault`, a test-only hook)
    can be used to prove that an *earlier* mutation in the same body is
    rolled back too (WP-4 mutation-injection completion condition #1:
    "同一tx監査を分離する" -- separating the audit write from the state
    change it accompanies).
    """

    def __init__(self) -> None:
        self._events: list[ControlAuditEvent] = []
        self._lock = Lock()
        self._fault: Optional[BaseException] = None

    def inject_fault(self, exc: Optional[BaseException]) -> None:
        """Test-only. `exc=None` clears a previously injected fault."""
        self._fault = exc

    def append(self, *, event_class: str, operation: str, outcome: str,
               request_id: Optional[str] = None, application_id: Optional[str] = None,
               actor_type: Optional[str] = None, actor_id: Optional[str] = None,
               role: Optional[str] = None, target_kind: Optional[str] = None,
               reason_code: Optional[str] = None, target_id: Optional[str] = None,
               work: Any = None) -> ControlAuditEvent:
        if self._fault is not None:
            raise self._fault
        event = ControlAuditEvent(
            event_id=uuid.uuid4().hex,
            event_class=event_class,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            request_id=request_id,
            application_id=application_id,
            actor_type=actor_type,
            actor_id=actor_id,
            role=role,
            operation=operation,
            target_kind=target_kind,
            outcome=outcome,
            reason_code=reason_code,
            target_id=target_id,
        )
        with self._lock:
            self._events.append(event)
        if work is not None:
            work.on_rollback(lambda: self._discard(event))
        return event

    def _discard(self, event: ControlAuditEvent) -> None:
        with self._lock:
            try:
                self._events.remove(event)
            except ValueError:  # pragma: no cover - defensive
                pass

    def snapshot(self) -> tuple[ControlAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


def _control_audit_table(schema: str) -> sql.Identifier:
    validate_identifier(schema, "schema")
    return sql.Identifier(schema, "control_audit")


def insert_control_audit_row(conn: "psycopg.Connection", schema: str, *, event_class: str,
                              operation: str, outcome: str, request_id: Optional[str] = None,
                              application_id: Optional[str] = None, actor_type: Optional[str] = None,
                              actor_id: Optional[str] = None, role: Optional[str] = None,
                              target_kind: Optional[str] = None, reason_code: Optional[str] = None,
                              target_id: Optional[str] = None) -> str:
    """Appends one row to `control_audit` (migration 0002) using `conn` --
    the SAME connection/transaction `control_plane.PostgresControlBackend`
    is already holding open for the state change this audit row accompanies
    (R-6 same-transaction requirement). This function never calls `conn.
    commit()`/`conn.rollback()` itself; the caller's own transaction
    boundary decides that -- exactly what makes the "same transaction"
    guarantee possible: a caller that inserts this row and then fails a
    later statement on the SAME `conn`, then rolls `conn` back, undoes this
    INSERT too.
    """
    event_id = uuid.uuid4().hex
    occurred_at = datetime.now(timezone.utc)
    # Phase 3.5 WP-5 (§1-C/§4, B-1 measure): `target_id` appended as the
    # 13th column, matching `CONTROL_AUDIT_FIELDS`'s own order above.
    statement = sql.SQL(
        "INSERT INTO {} (event_id, event_class, occurred_at, request_id, "
        "application_id, actor_type, actor_id, role, operation, target_kind, "
        "outcome, reason_code, target_id) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})"
    ).format(_control_audit_table(schema), *[sql.Placeholder() for _ in range(13)])
    try:
        with conn.cursor() as cur:
            cur.execute(statement, [event_id, event_class, occurred_at, request_id,
                                     application_id, actor_type, actor_id, role,
                                     operation, target_kind, outcome, reason_code,
                                     target_id])
    except psycopg.errors.InsufficientPrivilege as exc:
        raise StorageConfigurationError(
            "control audit insert refused by a privilege/configuration defect"
        ) from exc
    except psycopg.Error as exc:
        raise AuthorizationStateUnavailable("control audit sink unavailable") from exc
    return event_id


def read_control_audit_events(dsn: str, schema: str = "mitatedb_registry", *,
                               connect_timeout: int = 5) -> list[dict]:
    """R-8: a SEPARATE reader for test/adapter observation. The
    control-plane process role (`mitatedbsvc_controlplane`) itself has
    INSERT-only privilege on `control_audit` (migration 0002: append-only
    by grant, not merely by convention) and cannot be used to read this
    table back. `dsn` here must authenticate as a role that CAN select it
    (the schema owner, `mitatedbsvc_provision`, in every test/adapter this
    repository builds) -- this function does not care which; it only
    issues a plain `SELECT ... ORDER BY audit_seq`, the stable monotonic
    ordering column C-15's prefix-strict comparison needs (R-4/m-2)."""
    validate_identifier(schema, "schema")
    statement = sql.SQL(
        "SELECT {fields}, audit_seq FROM {table} ORDER BY audit_seq"
    ).format(
        fields=sql.SQL(", ").join(sql.Identifier(f) for f in CONTROL_AUDIT_FIELDS),
        table=sql.Identifier(schema, "control_audit"),
    )
    conn = psycopg.connect(dsn, connect_timeout=connect_timeout)
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
            rows = cur.fetchall()
    finally:
        conn.close()
    columns = CONTROL_AUDIT_FIELDS + ("audit_seq",)
    return [dict(zip(columns, row)) for row in rows]


__all__ = [
    "CONTROL_AUDIT_FIELDS",
    "ControlAuditEvent",
    "ControlAuditSink",
    "insert_control_audit_row",
    "read_control_audit_events",
]
