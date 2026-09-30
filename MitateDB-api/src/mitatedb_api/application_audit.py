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

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Optional
import uuid

import psycopg
from psycopg import sql

from .pool import BoundedConnectionPool, _application_name_connect_kwargs
from .psycopg_counting import CountingConnection

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
    # Phase 9 WP-3a (design docs/design/
    # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (5)):
    # `ApplicationCell.alter_field`'s own `_make_audit_hook(operation=
    # "alter_field", ...)` -- a real, durable `schema_change`-class audit
    # write, same commit as the capability flip.
    "alter_field",
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

# Phase 9 WP-3cd closure (design D-5 (1)(v), 監督裁定集約 rulings-r5-r6.md
# J-4): this peer's own `outcome` column vocabulary -- mirrors r2db-api's
# `audit_query.DECLARED_AUDIT_OUTCOMES` one-for-one (`allow`/`deny`/
# `error`, this module's own pre-existing literals at every `.append(...)`
# call site, plus `replayed`, new as of this closure: an idempotency
# REPLAY's own durable row, `audit_dispatch.AuditRouter.push_buffer_event`/
# `.write_replayed_fail_closed_event`). `test_application_audit.py`'s own
# `test_declared_audit_outcomes_cover_every_emitted_outcome` fixes every
# `outcome=`/`outcome="..."` literal this peer's durable emit sites
# construct against this set, the same AST-scan shape `test_declared_
# event_classes_cover_every_emittable_class` already uses for `event_
# class`.
DECLARED_AUDIT_OUTCOMES = frozenset({
    "allow",
    "deny",
    "error",
    "replayed",
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

    Connections come from one of two places. Given a `pool` (the HTTP
    composition root always gives one), every call borrows a connection
    from that `pool.BoundedConnectionPool`, so the number of connections
    this sink holds against `mitatedbsvc_api` is capped at the pool's
    `max_size` however many request threads write at once, and a call
    that finds every connection borrowed waits (bounded by the pool's own
    acquire timeout) rather than dropping its event. Without a `pool` (the
    default -- this repository's own tests and the in-process conformance
    adapter), every call opens, and closes, a connection of its own, the
    same shape this peer's `credential_store_postgres.py` keeps for its
    own no-pool default.

    Either way every call -- the D-2 pre-commit fail-closed write, the D-3
    coalesced-denial first-occurrence write, the D-2 commit-failure `error`
    row, the D-4 buffer flush -- runs in a transaction of its own that it
    commits itself (or, on failure, never commits). A pooled connection is
    held by exactly one call at a time, so two calls in flight at once are
    on two different connections and never share a transaction; that is
    what makes D-4's "buffer flush never shares a transaction with a
    fail-closed write" requirement structural rather than something a
    caller has to arrange. A connection that raised while borrowed is
    closed and forgotten; one that returned normally is rolled back once
    more (a no-op after the call's own commit, but it ends the transaction
    a read-only `events()` leaves open) before it goes back to the pool.
    A restarted database or a server-side idle disconnect is recovered
    from by the pool, not by this sink: a connection that sat idle longer
    than `pool.IDLE_PING_THRESHOLD_S` is checked with one round trip when
    it is borrowed and replaced if it is dead, so no write fails on it.
    A connection the server ended within that window of its last use is
    handed out unchecked, and the one write that borrows it fails (the
    sink does not retry); the next call opens a fresh connection. A `pool`
    this sink was given is owned by it: `close()` releases every idle
    connection in it.

    Never accepts a `work` handle unlike `control_audit.
    insert_control_audit_row` -- there is no cross-database unit-of-work
    to join (design §1.3/D-1: application data lives in a DIFFERENT
    database per application; `application_audit` lives in the platform
    database alongside `control_audit`).
    """

    def __init__(
        self, dsn: str, *, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5,
        pool: Optional[BoundedConnectionPool] = None,
    ) -> None:
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
        self._pool = pool
        # Platform DB-time accounting for this sink's own per-call
        # connections, the ones `_connect` opens when there is no pool
        # (mirrors `credential_store_postgres.py`'s identical shape): a
        # dedicated `threading.Lock` guards five running totals that only
        # ever grow -- `_sessions`/`_connect_wall_ms` in `_connect` right
        # after the connect returns, `_platform_db_wall_ms`/`_platform_
        # txn_count`/`_platform_db_calls` folded in by `_fold_closed_
        # connection_stats` right before each such connection closes. The
        # connections a `pool` opens are counted by that pool, and
        # `platform_stats` adds its totals in.
        self._platform_stats_lock = threading.Lock()
        self._sessions = 0
        self._connect_wall_ms = 0.0
        self._platform_db_wall_ms = 0.0
        self._platform_txn_count = 0
        self._platform_db_calls = 0

    def _connect(self) -> "psycopg.Connection":
        """Opens a fresh `psycopg_counting.CountingConnection` (a `psycopg.
        Connection` subclass) that this sink itself closes, timed into
        `_connect_wall_ms`/`_sessions` under `self._platform_stats_lock`,
        so this connection's own later `db_wall_ms`/`txn_count` can be
        folded into this sink's platform totals right before it closes.
        Every call opens one when there is no pool; with a pool it is never
        called -- a pooled connection is opened by the pool
        (`BoundedConnectionPool._new_connection`), with the same DSN and
        arguments."""
        connect_start = time.monotonic()
        conn = CountingConnection.connect(
            self._dsn, connect_timeout=self._connect_timeout, autocommit=False, **_application_name_connect_kwargs(),
        )
        connect_wall_ms = (time.monotonic() - connect_start) * 1000.0
        with self._platform_stats_lock:
            self._sessions += 1
            self._connect_wall_ms += connect_wall_ms
        return conn

    def _fold_closed_connection_stats(self, conn: "psycopg.Connection") -> None:
        """Called right before a connection `_connect` opened is closed
        (`_borrow`'s no-pool branch, below): adds this one connection's
        own `db_wall_ms`/`txn_count`/`execute_count + executemany_count`
        into this sink's own running totals, under `self.
        _platform_stats_lock`, so closing a connection never loses time,
        transactions, or statements it already spent."""
        db_wall_ms = getattr(conn, "db_wall_ms", 0.0)
        txn_count = getattr(conn, "txn_count", 0)
        db_calls = getattr(conn, "execute_count", 0) + getattr(conn, "executemany_count", 0)
        with self._platform_stats_lock:
            self._platform_db_wall_ms += db_wall_ms
            self._platform_txn_count += txn_count
            self._platform_db_calls += db_calls

    def platform_stats(self) -> dict[str, int | float]:
        """Read-only sum of this sink's own platform DB-time accounting
        (same shape as `credential_store_postgres.PostgresCredentialStore.
        platform_stats`): `sessions`/`connect_wall_ms` from every
        `_connect` call, `db_wall_ms`/`txn_count`/`db_calls` folded in
        from every connection this sink has already closed, plus -- when
        this sink has a pool -- that pool's own `platform_stats()` for the
        connections it opened. No DB round trip: every value read here is
        a plain Python attribute, under `self._platform_stats_lock`."""
        with self._platform_stats_lock:
            own = {
                "sessions": self._sessions,
                "connect_wall_ms": self._connect_wall_ms,
                "db_wall_ms": self._platform_db_wall_ms,
                "txn_count": self._platform_txn_count,
                "db_calls": self._platform_db_calls,
            }
        if self._pool is None:
            return own
        pooled = self._pool.platform_stats()
        return {name: value + pooled[name] for name, value in own.items()}

    @contextmanager
    def _borrow(self):
        """The one place every read and write below gets its connection.
        With a pool, the connection is borrowed for exactly the duration
        of the `with` block, so no other call can use it meanwhile; one
        that raised inside the block is discarded (closed, never
        returned), and one that did not is rolled back and returned -- a
        rollback that itself fails discards it too. Without a pool, the
        connection is a fresh one closed at the end of the block."""
        if self._pool is None:
            conn = self._connect()
            try:
                yield conn
            finally:
                self._fold_closed_connection_stats(conn)
                conn.close()
            return
        conn = self._pool.acquire()
        healthy = True
        try:
            yield conn
        except BaseException:
            healthy = False
            raise
        finally:
            if healthy:
                try:
                    conn.rollback()
                except Exception:
                    healthy = False
            if healthy:
                self._pool.release(conn)
            else:
                self._pool.discard(conn)

    def close(self) -> None:
        """Releases every idle connection of the pool this sink was given
        (the lifespan shutdown calls it once the last flush is done). A
        no-op without a pool: every call already closed its own
        connection."""
        if self._pool is not None:
            self._pool.closeall()

    def append(
        self, *, event_class: str, request_id: Optional[str], application_id: Optional[str],
        actor_type: Optional[str], actor_id: Optional[str], role: Optional[str], operation: str,
        target_kind: Optional[str], outcome: str, reason_code: Optional[str] = None,
        target_id: Optional[str] = None, count: Optional[int] = None,
    ) -> None:
        """Synchronous durable INSERT + commit, in a transaction of this
        call's own on a connection no other call holds meanwhile. A
        failure here propagates to the caller unchanged (a `psycopg.Error`
        from the statement or the connect, or -- with a pool -- the pool's
        `errors.AuthorizationStateUnavailable` when it cannot connect or
        stays exhausted past its acquire timeout; never mapped to
        `errors.AuditSinkUnavailable` at this layer) -- `audit_dispatch.
        py`'s pre-commit-hook/denial/alert closures are the layer that
        decides how a failure here becomes `errors.AuditSinkUnavailable`."""
        event_id = uuid.uuid4().hex
        occurred_at = datetime.now(timezone.utc)
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(14)}
        statement = sql.SQL(_APPLICATION_AUDIT_INSERT).format(table=self._table, **placeholders)
        params = [
            event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id,
            role, operation, target_kind, outcome, reason_code, target_id, count,
        ]
        with self._borrow() as conn:
            with conn.cursor() as cur:
                cur.execute(statement, params)
            conn.commit()

    def append_many(self, events: "list[ApplicationAuditEvent]") -> None:
        """D-4's buffer flush: every buffered `ApplicationAuditEvent` in
        `events` is written as one multi-row `INSERT` in one transaction --
        either the whole batch commits or (on failure) none of it does,
        mirroring `ApplicationAuditSink.append_many`'s in-memory all-or-
        nothing behaviour (D-10 parity)."""
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
        with self._borrow() as conn:
            with conn.cursor() as cur:
                cur.execute(statement, params)
            conn.commit()

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
        with self._borrow() as conn:
            with conn.cursor() as cur:
                cur.execute(statement)
                return cur.fetchall()


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
    "DECLARED_AUDIT_OUTCOMES",
    "APPLICATION_AUDIT_FIELDS",
    "coalesced_count",
    "ApplicationAuditEvent",
    "ApplicationAuditSink",
    "PostgresApplicationAuditSink",
]
