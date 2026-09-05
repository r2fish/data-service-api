"""The durable application-plane audit trail's 13-column (+`count`) emitter
(design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10, work order
WP-3(a)).

Independent implementation of r2db-api's own `r2db_api.audit.
ApplicationAuditSink`/`r2db_api.credential_store.PostgresApplicationAuditSink`
pair (R-2's closing paragraph: no code sharing between peers) -- same
D-10 in-memory/PostgreSQL pair shape, writing to
`mitatedb_registry.application_audit` (migration `0005_application_audit.
sql`) instead of r2db's `r2dbsvc_registry.application_audit`.

A *separate* sink from `audit.AuditSink` (this peer's existing 6-field,
application-plane-only, `_SAFE_EVENTS`/`_SAFE_DETAILS`-rounding sink) and
from `control_audit.ControlAuditSink`/`insert_control_audit_row` (the
control plane's own 13-field durable pair) -- not a replacement for
either. D-3/D-10's own instruction: the pre-existing 6-field `audit.
AuditSink` stays the sole recorder for the non-durable denial codes (every
`errors.FoundationError` this peer raises whose contract code is outside
`audit_dispatch._DURABLE_DENIAL_CODES`), which never reach this module at
all -- and, per design §6.2 (monitor裁定 R6), this module's own emit sites
never round a value through that 6-field sink's `_SAFE_EVENTS`/
`_SAFE_DETAILS` vocabulary: every event this module records durably uses
`DECLARED_AUDIT_EVENT_CLASSES` directly, so the emitted `event_class`
column always matches this peer's own declared vocabulary (the
`test_declared_event_classes_cover_every_emittable_class` / `test_
durable_path_never_passes_through_the_six_field_rounding_sink` regression
guard this WP's own completion conditions name).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import psycopg
from psycopg import sql

DEFAULT_SCHEMA = "mitatedb_registry"

# Phase 4 (design D-6/N-3; WP-2(a) parity): the two SESSION-level timeout
# defaults every connection that writes `application_audit` OR
# `control_audit` carries for its entire lifetime -- ONE shared
# definition. `main.build_app` (the application-plane composition root)
# and `control_composition.build_control_service` (the control-plane
# composition root) both import these SAME two names and read the SAME
# two env-var names (`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS`/`MITATEDB_
# AUDIT_IDLE_TIMEOUT_MS`) rather than each maintaining its own literal
# that could silently drift apart -- see those two composition roots' own
# comments (D-6's derived `visibility_lag_ms`, a WP-3(b) declaration
# concern, depends on both processes agreeing on these two values).
DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS = 5000
DEFAULT_AUDIT_IDLE_TIMEOUT_MS = 5000

# Phase 4 (design §7.3/§7.4; WP-2(a) parity): the bounded buffer's default
# capacity (implementation discretion per the design -- "既定 1000、実装
# 裁量で設定可"), and the default periodic buffer-flush interval / minimum
# interval between overflow-alert-row attempts -- ONE constant serving
# both roles, matching r2db-api's own `_DEFAULT_AUDIT_FLUSH_INTERVAL_S`.
DEFAULT_AUDIT_BUFFER_CAPACITY = 1000
DEFAULT_AUDIT_FLUSH_INTERVAL_S = 2.0

# Phase 4 (design D-3, P4-D3): the coalescing window.
DEFAULT_DENIAL_COALESCE_WINDOW_S = 60.0

# Phase 4 (design D-7): "each peer declares its own event_class
# vocabulary; the contract defines no enum". This is that declaration --
# the ONLY `event_class` values this peer's durable emit sites ever
# construct (`cell.py`/`auth.py`/`credential_store_postgres.py`/
# `audit_dispatch.py` all import and use this constant directly, rather
# than each spelling its own literal set of strings that could drift).
# `test_declared_event_classes_cover_every_emittable_class`
# (`tests/test_application_audit.py`) fixes emitted classes against this
# set via an AST walk of every emit call site (positional, keyword, and
# `.append(event_class=...)` forms alike).
#
#   schema_change              -- create_collection / add_field (D-2 item
#                                  2: unconditionally fail-closed). Reuses
#                                  this peer's own pre-existing 6-field
#                                  `audit.AuditSink._SAFE_EVENTS` name for
#                                  the SAME real-world event, so a reader
#                                  correlating both sinks sees matching
#                                  class names.
#   destructive_data_operation -- delete (single-operation and
#                                  batch-embedded via transact()), always
#                                  fail-closed (D-2 item 1: the
#                                  confirmation choke). Reuses this peer's
#                                  own pre-existing 6-field sink name.
#   data_operation              -- query / insert / update success (P4-D5:
#                                  a NEW emit site this WP introduces --
#                                  this peer recorded none of these
#                                  before). Buffer-class (D-4). Matches
#                                  r2db-api's own identical term for the
#                                  identical conceptual event, deliberately
#                                  -- an AI-agent consumer of both peers'
#                                  audit streams sees one vocabulary for
#                                  "an ordinary data operation succeeded".
#   authentication_denied       -- a durable-range (D-3 inclusion table)
#                                  denial from `auth.CredentialStore`/
#                                  `credential_store_postgres.
#                                  PostgresCredentialStore` (`authenticate`/
#                                  `assert_active`). Reuses this peer's own
#                                  pre-existing 6-field sink name.
#   authorization_denied        -- a durable-range denial from `cell.
#                                  ApplicationCell._require_developer`
#                                  (developer authority required).
#                                  Reuses this peer's own pre-existing
#                                  6-field sink name.
#   security_control_failure    -- D-4's buffer-overflow alert row. The
#                                  design's own §7.4 names this class
#                                  literally; not a peer-specific choice.
DECLARED_AUDIT_EVENT_CLASSES = frozenset({
    "schema_change",
    "destructive_data_operation",
    "data_operation",
    "authentication_denied",
    "authorization_denied",
    "security_control_failure",
})

# Phase 5 WP-3 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
# D-1, contract 1.5.0 subordinate ruling 10 item 1): this peer's
# application-plane half of the `operation` vocabulary (`audit_query.
# DECLARED_AUDIT_OPERATIONS`'s own union with `audit_query.py`'s control
# half -- same 2-module shape as `DECLARED_AUDIT_EVENT_CLASSES` above).
# Every element here is a real literal `cell.ApplicationCell`/`auth.
# CredentialStore`/`credential_store_postgres.PostgresCredentialStore`/
# `http.py`/`audit_dispatch.AuditRouter` durably write to `application_
# audit` -- fixed against the real source by `tests/test_audit_query.py`'s
# generalized `U == D | N` AST scan.
DECLARED_AUDIT_OPERATIONS = frozenset({
    "access",
    "add_field",
    "assert_active",
    "audit_buffer",
    "authenticate",
    "create_collection",
    "delete",
    "insert",
    "query",
    "schema",
    "transact",
    "update",
})

# Phase 5 WP-3 (same design/ruling as `DECLARED_AUDIT_OPERATIONS` above):
# this peer's application-plane half of the `target_kind` vocabulary.
DECLARED_AUDIT_TARGET_KINDS = frozenset({
    "audit_sink",
    "collection",
    "credential",
})

# Contract `audit.fields`, verbatim order (matches `control_audit.
# CONTROL_AUDIT_FIELDS`) plus the 14th, durable-schema-only `count` column
# (D-3's coalesced-denial summary row / D-4's buffer-overflow alert row;
# every other event leaves it `None` -- see migration `0005_application_
# audit.sql`'s own header for why this column is not added to
# `control_audit`).
APPLICATION_AUDIT_FIELDS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome",
    "reason_code", "target_id", "count",
)


def coalesced_count(occurrences: int) -> Optional[int]:
    """Phase 4 WP-2(b) review B-1 (major, supervisor ruling 2026-09-03),
    carried into this WP from the start (per the发注 instruction to fold in
    WP-2(a)/(b) review rulings from the outset): the durable `count`
    column's own semantics -- "the number of occurrences this ONE row
    represents; when that number is 1, the column is absent (NULL)"
    (contract `audit.query_event_fields_note`: "never zero or one"). Both
    call sites that can ever pass a real integer here -- `audit_dispatch.
    _DenialCoalescer`'s aggregate (repeat-count) row and `audit_dispatch.
    _AuditBuffer`'s overflow-alert row -- route the raw tally through this
    one function instead of writing it verbatim, so "exactly one repeat/
    one drop" always renders as an ordinary NULL-count row.
    """
    return occurrences if occurrences >= 2 else None


@dataclass(frozen=True)
class ApplicationAuditEvent:
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
    target_id: Optional[str] = None
    count: Optional[int] = None


class ApplicationAuditSink:
    """The durable application-plane audit trail's in-memory half
    (D-1/D-10) -- mirrors `control_audit.ControlAuditSink`'s shape and
    `inject_fault`/fault-injection mechanism one-for-one, extended with
    `append_many` for D-4's buffer flush (a single batch write, never one
    `append()` per buffered event -- `ControlAuditSink` has no equivalent
    because control-plane events are never buffered, every `control_audit`
    row is written synchronously).
    """

    def __init__(self) -> None:
        self._events: list[ApplicationAuditEvent] = []
        self._fault: Optional[BaseException] = None

    def inject_fault(self, exc: Optional[BaseException]) -> None:
        """Test-only fault injection: when `exc` is not `None`, every
        subsequent `append`/`append_many` call raises it instead of
        recording anything. Pass `None` to clear. Production code never
        calls this."""
        self._fault = exc

    def append(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], outcome: str, reason_code: Optional[str] = None,
        target_id: Optional[str] = None, count: Optional[int] = None,
    ) -> ApplicationAuditEvent:
        if self._fault is not None:
            raise self._fault
        event = ApplicationAuditEvent(
            event_id=uuid.uuid4().hex, event_class=event_class,
            occurred_at=datetime.now(timezone.utc).isoformat(), request_id=request_id,
            application_id=application_id, actor_type=actor_type, actor_id=actor_id, role=role,
            operation=operation, target_kind=target_kind, outcome=outcome, reason_code=reason_code,
            target_id=target_id, count=count,
        )
        self._events.append(event)
        return event

    def append_many(self, events: "list[ApplicationAuditEvent]") -> None:
        """D-4's buffer-flush batch write -- either every event in
        `events` is recorded, or (on injected/simulated failure) none is,
        mirroring `PostgresApplicationAuditSink.append_many`'s all-or-
        nothing real multi-row `INSERT`."""
        if self._fault is not None:
            raise self._fault
        self._events.extend(events)

    def events(self) -> "tuple[ApplicationAuditEvent, ...]":
        return tuple(self._events)


_APPLICATION_AUDIT_INSERT = (
    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) "
    "VALUES ({ph0}, {ph1}, {ph2}, {ph3}, {ph4}, {ph5}, {ph6}, {ph7}, {ph8}, {ph9}, {ph10}, {ph11}, {ph12}, {ph13})"
)


class PostgresApplicationAuditSink:
    """The durable application-plane audit trail's PostgreSQL half
    (D-1/D-10) -- writes to `mitatedb_registry.application_audit`
    (migration `0005_application_audit.sql`).

    No pooling, one connection per call (mirrors this peer's own
    established `credential_store_postgres.py`/`control_plane.
    PostgresControlBackend` precedent, not r2db-api's own pooled
    `_RolePool` -- R-2's closing paragraph: no code sharing between
    peers, and this peer's OWN existing audit-writer precedent
    (`control_plane.PostgresControlBackend.unit_of_work`) already opens a
    fresh connection per call). Every call -- the D-2 pre-commit
    fail-closed write, the D-3 coalesced-denial first-occurrence write,
    the D-2 commit-failure `error` row, the D-4 buffer flush -- opens (and
    commits, or rolls back on failure) its own single connection/
    transaction, which is exactly what makes D-4's "buffer flush never
    shares a transaction with a fail-closed write" requirement automatic
    rather than something a caller has to arrange: two calls to this class
    are, structurally, always two different connections.

    Never accepts a `work` handle unlike `control_audit.
    insert_control_audit_row` -- there is no cross-database unit-of-work
    to join (design §1.3/D-1: application data lives in a DIFFERENT
    database per application; `application_audit` lives in the platform
    database alongside `control_audit`).
    """

    def __init__(self, dsn: str, *, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5) -> None:
        # Q4 phase (design D-1(b), work order §4 WP-2 変更対象 B): the two
        # writer timeouts are no longer this constructor's own concern --
        # this peer's former `SET SESSION` (removed here) is superseded by
        # `mitatedbsvc_api`'s own PostgreSQL role setting (`ALTER ROLE ...
        # SET`, migration `0007_platform_declarations.sql`), which applies
        # automatically to every connection made as this role, this
        # connection included -- no client-side action needed. The
        # composition root checks the declared-vs-effective value once at
        # startup (`platform_declarations.check_writer_role_timeouts`)
        # instead of this class setting it per connection.
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._table = sql.Identifier(schema, "application_audit")

    def _connect(self) -> "psycopg.Connection":
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False)

    def append(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], outcome: str, reason_code: Optional[str] = None,
        target_id: Optional[str] = None, count: Optional[int] = None,
    ) -> None:
        """Synchronous durable INSERT + commit, on this call's own fresh
        connection/transaction. A `psycopg.Error` here propagates to the
        caller unchanged (never mapped to `errors.FoundationError` at this
        layer) -- `audit_dispatch.py`'s pre-commit-hook/denial/alert
        closures are the layer that decides how a failure here becomes
        `errors.AuditSinkUnavailable`."""
        event_id = uuid.uuid4().hex
        occurred_at = datetime.now(timezone.utc)
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(14)}
        statement = sql.SQL(_APPLICATION_AUDIT_INSERT).format(table=self._table, **placeholders)
        params = [
            event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id,
            role, operation, target_kind, outcome, reason_code, target_id, count,
        ]
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(statement, params)
            conn.commit()
        finally:
            conn.close()

    def append_many(self, events: "list[ApplicationAuditEvent]") -> None:
        """D-4's buffer flush: every buffered `ApplicationAuditEvent` in
        `events` is written as one multi-row `INSERT` on one connection/
        transaction -- either the whole batch commits or (on failure) none
        of it does, mirroring `ApplicationAuditSink.append_many`'s
        in-memory all-or-nothing behaviour (D-10 parity)."""
        if not events:
            return
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(14)}
        row_sql = sql.SQL("({})").format(sql.SQL(", ").join(placeholders[f"ph{i}"] for i in range(14)))
        statement = sql.SQL(
            "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
            "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) VALUES {rows}"
        ).format(table=self._table, rows=sql.SQL(", ").join(row_sql for _ in events))
        params: list[Any] = []
        for event in events:
            occurred_at = datetime.fromisoformat(event.occurred_at) if isinstance(event.occurred_at, str) else event.occurred_at
            params.extend([
                event.event_id, event.event_class, occurred_at, event.request_id, event.application_id,
                event.actor_type, event.actor_id, event.role, event.operation, event.target_kind,
                event.outcome, event.reason_code, event.target_id, event.count,
            ])
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(statement, params)
            conn.commit()
        finally:
            conn.close()

    def events(self) -> "list[tuple[Any, ...]]":
        """Read surface for tests/tooling connected with sufficient
        privilege (the schema owner `mitatedbsvc_provision`, or the
        dedicated `mitatedbsvc_auditreader` role -- never the data-plane
        process' own `mitatedbsvc_api` role, which has no SELECT on this
        table at all, migration `0005_application_audit.sql`).
        """
        statement = sql.SQL("SELECT {columns} FROM {table} ORDER BY recorded_at, event_id").format(
            columns=sql.SQL(", ").join(sql.Identifier(name) for name in APPLICATION_AUDIT_FIELDS), table=self._table
        )
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(statement)
                return cur.fetchall()
        finally:
            conn.close()


__all__ = [
    "DEFAULT_SCHEMA",
    "DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS",
    "DEFAULT_AUDIT_IDLE_TIMEOUT_MS",
    "DEFAULT_AUDIT_BUFFER_CAPACITY",
    "DEFAULT_AUDIT_FLUSH_INTERVAL_S",
    "DEFAULT_DENIAL_COALESCE_WINDOW_S",
    "DECLARED_AUDIT_EVENT_CLASSES",
    "DECLARED_AUDIT_OPERATIONS",
    "DECLARED_AUDIT_TARGET_KINDS",
    "APPLICATION_AUDIT_FIELDS",
    "coalesced_count",
    "ApplicationAuditEvent",
    "ApplicationAuditSink",
    "PostgresApplicationAuditSink",
]
