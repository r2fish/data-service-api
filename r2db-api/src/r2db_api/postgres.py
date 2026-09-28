"""`PostgresCell`: a `StorageBackend` over PostgreSQL via psycopg 3.

Design constraints this file is written to satisfy:

- Values reach PostgreSQL exclusively through server-side bind parameters
  (via `psycopg.sql.Placeholder()` and a parameter list passed to
  `cursor.execute(...)`) or, for JSON-shaped values, `psycopg.types.json.Jsonb`
  -- never through string interpolation.
- Identifiers (table/column names) are composed only with `psycopg.sql.
  Identifier`, and only after (a) the shared syntax allowlist in
  `r2db_api.structured` and (b) verification against this application's
  *live* PostgreSQL catalog (`information_schema`), via `_load_catalog`.
  Syntax validation alone would still admit a well-formed but unknown
  identifier; the catalog check is what closes that gap.
- Operators and sort directions map to a fixed table of `sql.SQL` literals
  (`_COMPARISON_OPERATORS`); no operator string from a request is ever
  written into SQL text.
- No method on this class -- public or private -- accepts request-derived
  content and executes it as a `str`. `_run`, the single choke point every
  *client-influenced* statement passes through, is typed to accept only
  `psycopg.sql.Composed`/`psycopg.sql.SQL` and raises `TypeError` for
  anything else. Every SQL fragment built anywhere below (and in
  `postgres_sql.py`) that carries a
  client-supplied identifier/operator/value is constructed via
  `sql.SQL(...)`/`sql.Identifier`/`sql.Literal`/`sql.Placeholder`, never an
  f-string or `%`-formatted plain string, and never bypasses `_run`. The
  one exception, by design, not oversight: `_RolePool._liveness_check`'s
  pool-health probe (`cur.execute("SELECT 1")`) is a fixed, zero-argument
  literal with no request content anywhere near it -- a connection-pool
  implementation detail unrelated to any application-plane operation, and
  the only `.execute(...)` call in this file that does not go through
  `_run`.

This module does not duplicate validation. Identifier syntax, the operator
allowlist, mutation shape, and destructive-confirmation logic are imported
from `r2db_api.structured` and are the exact same functions `ApplicationCell`
uses -- see that module's "Shared validation/planning boundary" section.
This file only adds what is inherently PostgreSQL-specific: catalog lookup
against a live schema, SQL composition, session/transaction/timeout
handling, and per-role connection pooling.

Data model (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-2/R-4/R-7):
`create_entity` always provisions a server-assigned `id bigint GENERATED
ALWAYS AS IDENTITY PRIMARY KEY` (the row address) and an invisible
`_r2db_revision uuid NOT NULL DEFAULT gen_random_uuid()` (the per-row
optimistic-concurrency token), ahead of the caller's own declared fields.
Those own fields default to `JSONB` (`create_entity` never carries a `field_type` -- rejected at the shared `bind_schema_operation` boundary); `add_field`'s own optional `field_type` maps `string`/`integer`/`number`/`boolean` to `TEXT`/`BIGINT`/`DOUBLE PRECISION`/`BOOLEAN` respectively, and `object`/`array` to the two DOMAINs `migrations/0003_provision_application.sql` provisions per application database, `_r2db_json_object`/`_r2db_json_array` -- each a `jsonb` DOMAIN with a `jsonb_typeof(VALUE)` CHECK, so PostgreSQL's own catalog (`information_schema.columns.domain_name`) is what lets `_load_catalog` tell "declared as object" apart from "declared as array" apart from "untyped JSONB" ("object/array の DOMAIN 型統一": a bare `jsonb` column cannot report this distinction at all). `id`/`_r2db_revision` require PostgreSQL 13+
(`gen_random_uuid()` is a built-in as of that version).

Two layers validate a value written to an `object`/`array` column: `_check_
type` (shared with `ApplicationCell`, `r2db_api.structured`) refuses a
non-dict/non-list value with `VALIDATION_FAILED` naming only the field --
this is what a well-behaved client actually sees. The DOMAIN's own
`jsonb_typeof` CHECK is a second, defence-in-depth layer underneath that:
a real server-side invariant that should never fire if `_check_type` is
doing its job, so a CHECK violation is left to fall through to this
module's ordinary `SERVICE_UNAVAILABLE` mapping (a true "this should never
happen" backstop, not a validation response) rather than being decoded and
re-surfaced as a second `VALIDATION_FAILED` path.

Two legitimate, accepted cross-backend semantic differences remain: an
untyped (JSONB) column has no per-column type in the shared `r2db_api.
structured` vocabulary (`None`), so `lt`/`lte`/`gt`/`gte` comparisons that
would raise `TypeError` against mismatched Python types in `ApplicationCell`
typically do not raise here -- PostgreSQL's own jsonb ordering is total
across JSON types, producing a deterministic (if occasionally surprising)
`ORDER`-consistent boolean instead. And a `jsonb` (or `_r2db_json_object`/
`_r2db_json_array`-domain) column's own storage normalizes the value it is
given -- an object's key order is not the order it was written in JSON
source (PostgreSQL's own `(byte length, byte value)` order, `r2db_api.
structured._jsonb_text` reproduces this for `contains`/`matches`'s own
text-form comparison, WP-3 review N-1/N-2), and a duplicate key collapses
to its last-written value, silently, the same way a plain Python `dict`
literal with a repeated key would -- `ApplicationCell`, storing the Python
value directly with no serialization round-trip, does not normalize either
of these at write time, though a query response's item order/shape is
otherwise identical between the two backends for every value this
contract's type vocabulary can express. Both are what the Security
Invariants allow (implementations are not required to share a physical
data model), not validation gaps: both backends still reject bad
identifiers/operators/shapes, and the exact same errors/precedence for
every other checked property (addressability, uniqueness, revision
preconditions, `contains`/`matches` literal/wildcard semantics against
SQL's own three-valued logic, and object/array typing), identically.

History: CH-0001
"""
from __future__ import annotations

import os
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Sequence

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from .audit_hook import ApplicationAuditHook
from .backend import StorageBackend as _StorageBackend
from .errors import fail, violation
from .limits import ResourceLimits
from . import platform_upgrades
# R-79 (WO §2.1 D-1/D-2): the counting cursor/connection subclasses
# `_connect` (below) uses instead of plain `psycopg.connect`, and the
# `pg_prepared_statements` probe `prepared_stats` (below) calls -- all
# byte-identical to `mitatedb_api.psycopg_counting` (a same-named test in
# `tests/` pins the sha256 match; rework 指摘 3 moved the
# probe itself there so it is not duplicated per peer).
from .psycopg_counting import CountingConnection, prepared_stats_skeleton, probe_prepared_statements
# `_escape_like_literal` is not used directly in this module (its one
# call site, inside `_predicate_sql`, moved to `postgres_sql.py`); the
# import exists only as a facade-compat re-export for `r2db-api/tests/
# test_postgres.py`'s own facade test, which still imports it from
# `postgres`.
from .postgres_like import _escape_like_literal
from .postgres_sql import _append_revision_predicate, _bind_value, _keyset_predicate_sql, _order_by_sql, _predicate_sql, _select_statement, _text_expression, _where_clause
# `_FIELD_TYPE_SQL`/`_JSONB_SQL` are not used directly in this module; the import exists only as a facade-compat re-export for callers that still import them from `postgres`.
# history: CH-0002
from .postgres_types import _DOMAIN_TO_DECLARED, _FIELD_TYPE_SQL, _JSONB_SQL, _SQL_TYPE_TO_DECLARED, _TableInfo, _column_type_sql
from .structured import (
    BoundMutation,
    ConstraintPatch,
    FieldConstraints,
    MutationOutcome,
    Predicate,
    QueryOutcome,
    SchemaOutcome,
    compute_plan_token,
    idempotency_digest,
    _check_type,
    _ConstraintDeclarationError,
    _declared_type_label,
    _fail_constraint_declaration,
    _idempotency_record_has_request_id,
    _resolve_order_by,
    _validate_predicate_types,
    _reject_reserved_entity_name,
    bind_mutation,
    canonical_page_binding,
    decode_and_check_page_cursor,
    encode_page_cursor,
    bind_schema_operation,
    delete_confirmation_phrase,
    drop_entity_confirmation_phrase,
    drop_index_confirmation_phrase,
    require_destructive_confirmation,
    validate_enum_declaration,
    validate_identifier,
    validate_page_size,
    validate_predicates,
    validate_projection,
)

_REVISION_TABLE = "_r2db_schema_revision"
# Q4 WP-3 (design D-3(e), work order §4 WP-3 change table C): every backend
# bookkeeping table that must be excluded from (a) the application-visible
# catalog (`_load_catalog`) and (b) the RLS-coverage check (`_rls_offenders`,
# also reached inline by `_create_entity` right after every `CREATE TABLE`)
# -- a SET, not a single name, now that the per-application platform-upgrade
# ledger (`platform_upgrades.LEDGER_TABLE_NAME`) joins `_REVISION_TABLE` as a
# second bookkeeping table living in `public`. `_REVISION_TABLE` itself is
# kept as its own name (not folded away) because `_read_schema_revision`/
# `_bump_revision` still need it by name for real access, unlike the ledger
# table, which this file never reads or writes directly (the ledger is
# owned by `migrations/0003_provision_application.sql`/`0009_...sql` and
# read only by `platform_upgrades.read_applied_upgrade_numbers`, via the
# runtime pool's own connection -- U-2's `SELECT`-only grant).
#: Contract 1.7.0 (D-2 (4), WP-2a): the per-application field-constraints
#: declaration registry (side table) -- the declaration's own source of
#: truth (physical column constraints are never added, §4 A-1), so this is
#: a THIRD backend bookkeeping table joining `_REVISION_TABLE`/the platform-
#: upgrade ledger, excluded from the application-visible catalog/RLS-
#: coverage check the same way.
_FIELD_CONSTRAINTS_TABLE = "_r2db_field_constraints"
#: Contract 1.7.0 (D-5 (6), U-3 = (A), WP-2c): the per-application
#: idempotency-record side table -- a FOURTH backend bookkeeping table,
#: excluded from the application-visible catalog/RLS-coverage check the
#: same way the other three are (migration `0011_idempotency_records_
#: upgrade.sql`).
# history: CH-0102
_IDEMPOTENCY_TABLE = "_r2db_idempotency"
_BOOKKEEPING_TABLES: frozenset[str] = frozenset({_REVISION_TABLE, platform_upgrades.LEDGER_TABLE_NAME, _FIELD_CONSTRAINTS_TABLE, _IDEMPOTENCY_TABLE})
# two-int `pg_advisory_xact_lock(namespace, hashtext(key))` namespace for the PER-KEY idempotency lock -- see `_idempotency_key_lock` below.
#
# Code-review fix F7 (Opus review 2): the rationale this comment carried before this fix was FALSE and is corrected here (the constant itself is unaffected). It claimed a namespace of 0 would land in the SAME lock space the single-bigint form `ops.py::_RITUAL_ADVISORY_LOCK_KEY` (1414141) uses, risking a collision between a bootstrap/reset ritual's lock and an idempotency-key lock. PostgreSQL actually
# keeps those two key spaces disjoint by construction, regardless of
# namespace value: the 1-argument `pg_advisory_xact_lock(bigint)` form
# and the 2-argument `pg_advisory_xact_lock(int, int)` form record
# different `objsubid` values in `pg_locks` (1 for the 1-argument form,
# 2 for the 2-argument form) -- so `pg_advisory_xact_lock(1414141)` and
# `pg_advisory_xact_lock(0, 1414141)` are two DIFFERENT locks, never the
# same one, even though they would superficially "look like" the same
# 64-bit id under a naive `(namespace << 32 | key2)` encoding. This
# namespace constant is still a large, distinctive value, far from both
# `_RITUAL_ADVISORY_LOCK_KEY` values (r2db 1414141, MitateDB 761761761)
# and from `_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY` below -- kept for
# HUMAN legibility (so two DIFFERENT lock families never share a
# suspiciously similar-looking id in a `pg_locks` dump), not because a
# collision with the 1-argument form was ever actually possible.
# history: CH-0003
_IDEMPOTENCY_KEY_LOCK_NAMESPACE = 20261007
# table-level (not per-key) advisory lock serializing `_idempotency_reserve`'s COUNT-then-write across DIFFERENT keys -- same family as `ops.py::_RITUAL_ADVISORY_LOCK_KEY` (a single, fixed 64-bit `pg_advisory_xact_lock` key), a DIFFERENT constant from it (that lock guards bootstrap/reset ritual ordering; this one guards `idempotency_entries` capacity accounting -- two independent serialization points that must never share one lock id).
# history: CH-0004
_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY = 1414142
# Contract 1.1.0 (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-3/R-4):
# every entity table this backend creates now carries a server-assigned
# `id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY` (the row address) and
# an invisible `_r2db_revision uuid` column (the per-row optimistic-
# concurrency token) alongside its declared JSONB/typed fields.
_ID_COLUMN = "id"
_REVISION_COLUMN = "_r2db_revision"
_RESERVED_INTERNAL_PREFIX = "_r2db"

# `_RolePool`'s own bounded-wait defaults (review fix: neither of these
# existed before -- a connect attempt against an unreachable target had no
# timeout at all, and a caller waiting for a pooled connection to free up
# waited on `queue.Queue.get()` with no timeout either). Both are
# constructor parameters, not environment-tunable knobs like `R2DB_POOL_*`
# below: they bound worst-case latency for a single acquisition, not
# steady-state pool sizing, and a caller (a test, most concretely) that
# needs a different value passes it directly to `_RolePool`/`PostgresCell`/
# `PostgresCredentialStore`.
_DEFAULT_CONNECT_TIMEOUT_S = 5
_DEFAULT_ACQUIRE_TIMEOUT_S = 10.0


def _run(cursor: "psycopg.Cursor[Any]", statement: sql.Composed | sql.SQL, params: Sequence[Any] = ()) -> None:
    """The single execution choke point. Typed to accept only a composed psycopg SQL object -- never `str` -- so a raw string cannot reach the database from anywhere in this file, as a checked property rather than a convention.

    History: CH-0007
    """
    if not isinstance(statement, (sql.Composed, sql.SQL)):
        raise TypeError("PostgresCell only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, list(params))


# design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-4
# (completion conditions 68/69): the `application_name` every
# connection this module opens carries, process-wide. `None` (the
# default -- this repository's own tests and both conformance adapters
# never set it) omits the parameter entirely, leaving libpq's own
# default (`""`) untouched. `r2db_api.main`/`r2db_api.control_main` each
# set this ONCE, near the top of their own `build_app()`/`build_control_
# app()`, to `"r2db-api:data:<pid>"`/`"r2db-api:control:<pid>"` -- every
# `_RolePool` this SAME process opens afterward (regardless of which
# store class in `credential_store.py` constructs it) then carries that
# one value, without a constructor-parameter change at each of this
# module's several call sites. A real deployment's data/control planes
# are always two separate OS processes (`r2db_api.main:app`/`r2db_api.
# control_main:app`, both peer launchers' own `start()`), so this
# process-wide value is never ambiguous between the two.
_connection_application_name: str | None = None


def set_connection_application_name(name: str | None) -> None:
    """Sets (or clears, with `None`) the `application_name` every
    connection this module opens from now on carries -- see the module-
    level comment above for the full rationale. Not thread-safe against a
    concurrent `_RolePool._connect()`/`PostgresCell.verify_platform_
    upgrades_applied()` call in a DIFFERENT thread of the SAME process --
    unneeded in practice, since every real caller (`main.py`/`control_
    main.py`) calls this exactly once, at composition-root startup,
    before any request-serving thread exists."""
    global _connection_application_name
    _connection_application_name = name


def _application_name_connect_kwargs() -> dict[str, str]:
    """`{"application_name": ...}` when `set_connection_application_name`
    has been called with a non-`None` value, `{}` otherwise -- spread
    into a `psycopg.connect(...)`/`CountingConnection.connect(...)` call
    so an unset value omits the keyword argument entirely (never passes
    `application_name=None`, which psycopg would reject)."""
    if _connection_application_name is None:
        return {}
    return {"application_name": _connection_application_name}


class _RolePool:
    """A small connection pool dedicated to exactly one (login role,
    database, schema) triple.

    Design D-3 calls out a specific hazard: a pool shared across roles that
    uses `SET ROLE`/`search_path` per checkout leaks the previous borrower's
    authority into the next one if the release-time reset is ever missed.
    This class avoids that hazard structurally rather than by remembering to
    reset: every connection this pool ever hands out is opened with
    `psycopg.connect(dsn)` where `dsn` already authenticates as one fixed
    role, and `search_path` is set exactly once, at connection-open time, to
    one fixed schema -- never touched again for that connection's lifetime,
    and never reused by a different role or a different application (each
    `PostgresCell` owns its own pools). There is no `SET ROLE` anywhere in
    this file. A role switch on a shared connection simply never happens, so
    there is nothing to reset and nothing to forget to reset.

    `r2db_api/tests/test_postgres.py::test_pool_never_leaks_role_or_schema_
    across_applications` is the executable check for this: it interleaves
    heavy use of two applications' pools and asserts every connection drawn
    from either one reports its own fixed role/schema, never the other's.
    """

    def __init__(self, dsn: str, *, schema: str, maxconn: int = 4, connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT_S, acquire_timeout: float = _DEFAULT_ACQUIRE_TIMEOUT_S) -> None:
        self._dsn = dsn
        self._schema = schema
        self._maxconn = max(1, maxconn)
        self._queue: "queue.Queue[psycopg.Connection[Any]]" = queue.Queue(maxsize=self._maxconn)
        self._lock = threading.Lock()
        self._created = 0
        self._connect_timeout = connect_timeout
        self._acquire_timeout = acquire_timeout
        # Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md
        # D-1(b)): this pool no longer accepts or issues a per-connection
        # SESSION `SET` for `statement_timeout`/`idle_in_transaction_
        # session_timeout` -- the two audit-writer sinks that used to pass
        # `statement_timeout_ms`/`idle_in_transaction_session_timeout_ms`
        # here (`PostgresApplicationAuditSink`/`PostgresControlAuditSink`,
        # `credential_store.py`) now rely ENTIRELY on the PostgreSQL role
        # setting migration `0008` applies (`ALTER ROLE ... SET`) plus each
        # composition root's own startup double-check (`r2db_api.platform_
        # declarations`) that the writer connection's effective value
        # agrees with that role setting -- there is no longer a second,
        # independent code path that could disagree with it.
        # Set by `retire()` (called only by `SharedPoolManager`, below, when
        # this pool is evicted -- idle timeout or LRU cap). A retired pool
        # keeps serving any connection a caller already checked out (see
        # `connection()`'s `finally` below), it simply never re-queues one on
        # return; the pool drains to zero connections and stops being handed
        # out for new acquisitions once every outstanding checkout returns.
        self._retired = False
        # R-78 acquisition statistics: counted under `self._stats_lock`, a
        # lock dedicated to this bookkeeping and never shared with `self.
        # _lock` above -- the fast path in `_acquire` (`self._queue.get_
        # nowait()` succeeding) takes no lock at all today, and this
        # statistics addition does not change that; every counter update
        # below is a plain integer/float addition under `self._stats_lock`,
        # never a second acquisition of `self._lock`.
        self._stats_lock = threading.Lock()
        self._acquire_count = 0
        self._wait_count = 0
        self._wait_total_ms = 0.0
        self._wait_max_ms = 0.0
        self._in_use = 0
        self._in_use_peak = 0
        # Platform DB-time accounting, under the same `self._stats_lock`
        # as the acquisition counters above: `_sessions`/`_connect_wall_
        # ms` rise once per `_connect()` call (below), and `_closed_db_
        # wall_ms`/`_closed_txn_count`/`_closed_db_calls` receive a
        # connection's own `CountingConnection.db_wall_ms`/`txn_count`/
        # `execute_count + executemany_count` folded in right before that
        # connection is closed (`_liveness_check`, `close_all`, and
        # `connection()`'s own non-recycle path) -- so a closed
        # connection's own totals are never lost, only moved from "on the
        # connection" to "on this pool".
        self._connect_wall_ms = 0.0
        self._sessions = 0
        self._closed_db_wall_ms = 0.0
        self._closed_txn_count = 0
        self._closed_db_calls = 0

    def _connect(self) -> "psycopg.Connection[Any]":
        # `connect_timeout` (a real libpq connection parameter, merged into
        # `self._dsn`'s already-parsed conninfo by `psycopg.connect`'s own
        # kwargs-override-conninfo behaviour) bounds how long a single
        # connect attempt can take against an unreachable/blackholed target.
        # Without this, a target that never responds at the TCP level (as
        # opposed to an immediate `ECONNREFUSED`) can block for the
        # platform's default TCP connect timeout -- minutes, not seconds --
        # which is exactly the kind of unbounded wait `_acquire` below must
        # not be exposed to while holding `self._lock` (see that method's
        # own comment on why `_connect()` is never called under the lock).
        connect_start = time.monotonic()
        conn = CountingConnection.connect(
            self._dsn, autocommit=False, connect_timeout=self._connect_timeout,
            **_application_name_connect_kwargs(),
        )
        connect_wall_ms = (time.monotonic() - connect_start) * 1000.0
        with self._stats_lock:
            self._sessions += 1
            self._connect_wall_ms += connect_wall_ms
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
        conn.commit()
        return conn

    def _fold_closed_connection_stats(self, conn: "psycopg.Connection[Any]") -> None:
        """Called right before every `conn.close()` in this class (`_
        liveness_check`, `connection()`'s non-recycle path, `close_all`):
        adds this one connection's own `db_wall_ms`/`txn_count`/`execute_
        count + executemany_count` (from `psycopg_counting.
        CountingConnection`) into this pool's own running totals, under
        `self._stats_lock`, so closing a connection never loses time,
        transactions, or statements it already spent."""
        db_wall_ms = getattr(conn, "db_wall_ms", 0.0)
        txn_count = getattr(conn, "txn_count", 0)
        db_calls = getattr(conn, "execute_count", 0) + getattr(conn, "executemany_count", 0)
        with self._stats_lock:
            self._closed_db_wall_ms += db_wall_ms
            self._closed_txn_count += txn_count
            self._closed_db_calls += db_calls

    def _acquire(self) -> "psycopg.Connection[Any]":
        try:
            conn = self._queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._record_acquire()
            return conn
        # Reserve a slot (increment `_created`) and release the lock
        # *before* calling `_connect()` -- a real, previously-shipped bug
        # this class had: `_connect()` used to run while `self._lock` was
        # held, so every thread contending for a new connection against an
        # unreachable target serialized on this lock for the full connect
        # attempt, and a failed `_connect()` never rolled its reservation
        # back. `r2db_api/tests/
        # test_postgres.py::test_role_pool_recovers_after_connect_failures_
        # are_exhausted_and_target_becomes_reachable` and
        # `test_credential_persistence.py::
        # test_authenticate_never_hangs_across_repeated_pool_exhaustion_and_
        # recovers_once_reachable` are the executable checks for this fix.
        # history: CH-0181
        reserved = False
        with self._lock:
            if self._created < self._maxconn:
                self._created += 1
                reserved = True
        if reserved:
            try:
                conn = self._connect()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise
            self._record_acquire()
            return conn
        # Every slot is claimed by a connection some other caller currently
        # holds (or that is itself mid-`_connect()` on another thread) --
        # wait for one to be returned, but never unboundedly: a
        # `queue.Empty` here (nothing returned within `acquire_timeout`) is
        # re-raised as a `psycopg.OperationalError`, the same exception
        # type an actual failed connection attempt would raise, so every
        # existing `except psycopg.Error` call site in this file and in
        # `r2db_api.credential_store` already handles it correctly (fail-
        # closed to `SERVICE_UNAVAILABLE`/`AUTH_STATE_UNAVAILABLE`, never a
        # silent hang).
        try:
            wait_start = time.monotonic()
            conn = self._queue.get(timeout=self._acquire_timeout)
        except queue.Empty:
            self._record_wait((time.monotonic() - wait_start) * 1000.0)
            raise psycopg.OperationalError(
                f"timed out after {self._acquire_timeout}s waiting for an available pooled connection (pool exhausted at maxconn={self._maxconn})"
            )
        self._record_wait((time.monotonic() - wait_start) * 1000.0)
        self._record_acquire()
        return conn

    def _record_acquire(self) -> None:
        """Count one successful acquisition under `self._stats_lock`: `acquire_count` rises by one, `in_use` rises by one, and `in_use_peak` keeps the highest value `in_use` ever reaches. Called from every branch of `_acquire` that returns a connection, never from the branch that raises."""
        with self._stats_lock:
            self._acquire_count += 1
            self._in_use += 1
            if self._in_use > self._in_use_peak:
                self._in_use_peak = self._in_use

    def _record_wait(self, waited_ms: float) -> None:
        """Count one entry into the blocking `self._queue.get(timeout=...)` branch of `_acquire`, whether it ends in a connection or in the timeout `psycopg.OperationalError` -- both are a wait that happened. `wait_max_ms` keeps the highest single wait observed."""
        with self._stats_lock:
            self._wait_count += 1
            self._wait_total_ms += waited_ms
            if waited_ms > self._wait_max_ms:
                self._wait_max_ms = waited_ms

    def _record_release(self) -> None:
        """Count one connection returning from checked-out (`in_use`) back to available, under `self._stats_lock`. Called once per `connection()` context, regardless of which path (recycled or closed) the returned connection takes."""
        with self._stats_lock:
            self._in_use = max(0, self._in_use - 1)

    def stats(self) -> dict[str, int | float]:
        """Return this pool's acquisition statistics as a plain dict with exactly six keys: `size` (this pool's `maxconn`), `acquire_count`, `wait_count`, `wait_total_ms`, `wait_max_ms`, `in_use_peak`. Read under `self._stats_lock`; never touches `self._lock` or the connection queue itself."""
        with self._stats_lock:
            return {
                "size": self._maxconn,
                "acquire_count": self._acquire_count,
                "wait_count": self._wait_count,
                "wait_total_ms": self._wait_total_ms,
                "wait_max_ms": self._wait_max_ms,
                "in_use_peak": self._in_use_peak,
            }

    def platform_stats(self) -> dict[str, int | float]:
        """Read-only sum of this pool's own DB-time accounting: every
        connection currently idle in `self._queue` (drained via `get_
        nowait` and put back with `put_nowait`, exactly like `prepared_
        stats` below -- never through `_acquire()`, so `acquire_count`
        above stays untouched) plus the running totals `_fold_closed_
        connection_stats`/`_connect` already folded in for connections
        that are now closed. A connection some other caller currently has
        checked out is not in the queue right now, so its own not-yet-
        closed `db_wall_ms`/`txn_count`/`db_calls` are not yet visible
        here -- they land in this method's next call, once that
        connection is returned or closed. No DB round trip: every value
        read here is a plain Python attribute. `db_calls` is `execute_
        count + executemany_count`, the same pair `DBTIME scope=app` sums
        for the application-database side."""
        conns: list["psycopg.Connection[Any]"] = []
        live_db_wall_ms = 0.0
        live_txn_count = 0
        live_db_calls = 0
        while True:
            try:
                conns.append(self._queue.get_nowait())
            except queue.Empty:
                break
        for conn in conns:
            live_db_wall_ms += getattr(conn, "db_wall_ms", 0.0)
            live_txn_count += getattr(conn, "txn_count", 0)
            live_db_calls += getattr(conn, "execute_count", 0) + getattr(conn, "executemany_count", 0)
            self._queue.put_nowait(conn)
        with self._stats_lock:
            return {
                "sessions": self._sessions,
                "connect_wall_ms": self._connect_wall_ms,
                "db_wall_ms": live_db_wall_ms + self._closed_db_wall_ms,
                "txn_count": live_txn_count + self._closed_txn_count,
                "db_calls": live_db_calls + self._closed_db_calls,
            }

    def prepared_stats(self, label_prefix: str) -> list[dict[str, Any]]:
        """R-79 (WO §1.2 D-2, completion condition 8): probe every
        connection currently sitting IDLE in this pool's own queue --
        drained via `get_nowait` (never `_acquire()`: `_acquire()` would
        touch `_record_acquire`/`_record_wait` above, and this call must
        leave R-78's own `acquire_count`/`wait_count`/`in_use_peak`
        completely unchanged), probed with `psycopg_counting.probe_
        prepared_statements`, then returned to the SAME queue with `put_
        nowait` -- always, even when the probe raised (mutation M15
        removes that `finally`; WO §6.1 H-4). A connection some other
        caller currently has checked out is simply not in the queue right
        now and is not probed -- in-use connections are out of scope for
        this probe by construction (WO §1.2 D-2's own "idle 接続"
        wording), not by any extra check here.

        A probe that raises may leave its connection mid-transaction
        (aborted) -- if the failure happened after the probe's own SELECT
        but before its `commit()` (rework 指摘 5): rolled
        back here, before the connection rejoins the queue, so a caller
        that later checks it out never inherits an aborted transaction
        (mutation M25 drops this rollback). This does lose whatever was
        prepared on that connection (F2), but a connection already stuck
        aborted from a probe failure is not a state worth preserving
        prepared statements over.

        No lock: only this call drains this pool's own queue for the
        duration of this method (mirrors `close_all()`, above, which does
        the identical `get_nowait` drain with no lock either).

        This drains the queue in one shot, so it must never be called
        while a request may be mid-`_acquire()` on this same pool (another
        thread could see the queue empty and open a brand-new connection
        past `maxconn`, or simply stall waiting for one this call is
        temporarily holding) -- the only caller is the measurement
        harness, between ops, never inside a real request's own code
        path."""
        conns: list["psycopg.Connection[Any]"] = []
        while True:
            try:
                conns.append(self._queue.get_nowait())
            except queue.Empty:
                break
        rows: list[dict[str, Any]] = []
        for conn in conns:
            label = f"{label_prefix}@{conn.info.backend_pid}"
            try:
                rows.append(probe_prepared_statements(conn, label))
            except Exception as exc:  # noqa: BLE001 -- reported as probed=False/error=<class name>, connection still returned below (completion condition 15)
                if conn.info.transaction_status != TransactionStatus.IDLE:
                    conn.rollback()
                rows.append(prepared_stats_skeleton(conn, label, error=type(exc).__name__))
            finally:
                self._queue.put_nowait(conn)
        return rows

    def _liveness_check(self, conn: "psycopg.Connection[Any]") -> bool:
        """`pool_pre_ping` equivalent: a connection dequeued from `self._
        queue` may have been sitting idle long enough for the *server* to
        have terminated it (an operator's `pg_terminate_backend`, an idle
        session timeout, a network blip) without the client-side socket
        ever observing that -- `psycopg.Connection.closed` stays `0` in
        that case until something actually tries to use the connection.
        Checking `conn.closed` alone therefore misses exactly the failure
        mode a pool most needs to catch. This runs one cheap round trip
        (`SELECT 1`) on every checkout and reports whether the connection is
        actually usable; a dead connection is closed here (the caller is
        responsible for replacing it, not for reusing it in this state).
        """
        try:
            if conn.info.transaction_status != TransactionStatus.IDLE:
                conn.rollback()
            # The ping runs under `autocommit=True` so `SELECT 1` never
            # opens a transaction, leaving nothing for a `rollback()` to
            # close afterwards -- `rollback()` on a non-IDLE connection
            # clears every prepared statement on it, which a checkout-time
            # ping must not do. The check above rolls a non-IDLE connection
            # back first so this flip (which requires IDLE) never raises.
            # `autocommit` returns to `False` in `finally` so the
            # connection is handed to the caller IDLE, exactly as
            # `_connect()` leaves a freshly opened one -- the ping itself
            # must be invisible to whatever runs next.
            # history: CH-0541
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                conn.autocommit = False
            return True
        except Exception:
            self._fold_closed_connection_stats(conn)
            try:
                conn.close()
            except Exception:
                pass
            return False

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        conn = self._acquire()
        # `already_folded_conn` names whichever object this method itself
        # has ALREADY folded (and, for the `conn.closed` branch, closed)
        # before attempting a replacement `_connect()` -- so the `finally`
        # block below, which sees the OLD `conn` value again if `_connect(
        # )` itself raises, never folds that same connection's own stats a
        # second time.
        already_folded_conn: "psycopg.Connection[Any] | None" = None
        try:
            if conn.closed:
                # A connection dequeued already `closed` (server-
                # terminated, observed here rather than via `_liveness_
                # check`'s own round trip) is about to be discarded and
                # replaced -- fold its own accumulated stats in BEFORE
                # replacing it, or they vanish from both "idle in queue"
                # (it is no longer queued -- `_acquire()` already removed
                # it) and the closed-connection accumulator, showing up as
                # a window that lost time it should never lose.
                self._fold_closed_connection_stats(conn)
                already_folded_conn = conn
                conn = self._connect()
            elif not self._liveness_check(conn):
                # `_liveness_check`'s own `except` branch already folded
                # and closed `conn` before reporting `False` here.
                already_folded_conn = conn
                conn = self._connect()
            yield conn
        finally:
            # No `return` (or any other flow-control statement) anywhere in
            # this block: inside a generator's `finally`, `return` silently
            # swallows whatever exception was propagating through `yield`
            # above -- a real bug caught by this file's own tests (a
            # `FoundationError` raised by the caller was being discarded
            # instead of reaching them). Recycling the connection is
            # therefore expressed as a plain if/else with no early exit, so
            # an exception from the `try` block always continues propagating
            # once this `finally` finishes.
            keep = True
            try:
                if conn.closed:
                    keep = False
                elif conn.info.transaction_status != TransactionStatus.IDLE:
                    # Defence in depth: even though `conn.transaction()`
                    # leaves connections IDLE on both success and exception,
                    # a connection is never returned to the pool mid
                    # transaction. Nothing about role/schema is touched here.
                    conn.rollback()
            except Exception:
                keep = False
            with self._lock:
                retired = self._retired
            recycled = False
            if keep and not retired and not conn.closed:
                try:
                    self._queue.put_nowait(conn)
                    recycled = True
                except queue.Full:
                    recycled = False
            if not recycled:
                # `conn` here is the SAME object already folded above
                # (`already_folded_conn`) exactly when this method's own
                # replacement `_connect()` call itself raised -- the
                # assignment `conn = self._connect()` never completed, so
                # `conn` still names the old, already-discarded connection
                # when this `finally` block runs. Folding it again here
                # would double-count that one connection's own stats.
                if conn is not already_folded_conn:
                    self._fold_closed_connection_stats(conn)
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._created = max(0, self._created - 1)
            self._record_release()

    def close_all(self) -> None:
        while True:
            try:
                conn = self._queue.get_nowait()
            except queue.Empty:
                break
            self._fold_closed_connection_stats(conn)
            try:
                conn.close()
            except Exception:
                pass
        with self._lock:
            self._created = 0

    def retire(self) -> None:
        """Take this pool permanently out of service: called only by
        `SharedPoolManager` when this pool is evicted (idle timeout or LRU
        cap), never by `PostgresCell` directly. Every connection currently
        sitting idle in the queue is closed immediately -- those are safe to
        drop right now. Any connection presently checked out by a caller
        (mid-query, mid-transaction) is left completely alone here: closing
        it out from under an in-flight operation is exactly the "random
        failure under load" hazard this method exists to avoid. Setting
        `self._retired` instead makes `connection()`'s own `finally` block
        (above) close that connection -- instead of re-queuing it -- the
        moment its caller returns it normally, which is the only place a
        checked-out connection is ever safe to retire.
        """
        with self._lock:
            self._retired = True
        self.close_all()


def _env_int(name: str, default: int) -> int:
    """Read an `int`-valued setting the way the rest of this package does (`R2DB_`-prefixed environment variables, e.g. `R2DB_CREDENTIAL_PEPPER` in `auth.py`) -- a bare `os.environ.get` rather than a `pydantic` settings object, since this package (unlike the SQLAlchemy-based reference implementation this design is adapted from) has no `Settings`/`get_settings()` of its own. An unset, empty, or unparsable
    value silently falls back to `default` rather than raising: these are
    pool-tuning knobs, not required configuration, and a malformed value at
    startup should degrade to a sane default, not crash the process.

    History: CH-0100
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class _PoolManagerEntry:
    pool: "_RolePool"
    last_used: float


class SharedPoolManager:
    """The fix for this module's connection-pooling defect: a single,
    process-wide cache of `_RolePool` instances keyed by `(application_id,
    role)`, shared across every `PostgresCell` -- not one pair of pools per
    cell, held forever, as before.

    Design, adapted from the currently deployed reference implementation (a SQLAlchemy engine cache with the same two properties) to this package's hand-rolled psycopg pooling:

    - **Idle eviction.** A pool unused for `R2DB_POOL_IDLE_SECONDS` (default
      300) is retired the next time *any* key is looked up here -- eviction
      is swept lazily, on access, exactly like the reference implementation,
      not on a background timer.
    - **An LRU cap on live pools (`R2DB_POOL_CACHE_MAX`, default 32).** This
      is the property that actually decouples the connection ceiling from
      the number of applications: `PostgresCell.__init__` no longer creates
      a pool eagerly at all, it only registers a `(dsn, schema, maxconn)`
      recipe with this manager and asks for the live pool by key on every
      use (`_PoolHandle`, below). However many applications exist, at most
      `cache_max` *pools* are ever open at once, each capped at
      `maxconn` connections (default `R2DB_POOL_SIZE + R2DB_POOL_MAX_
      OVERFLOW` = 2 + 2 = 4, matching the reference implementation's
      effective per-application capacity) -- an absolute ceiling of
      `cache_max * maxconn` connections cluster-wide (default 32 * 4 = 128,
      itself still an operator-facing figure to size against `max_
      connections`, but no longer one that grows with application count).

    Eviction never closes a connection a caller currently has checked out
    -- see `_RolePool.retire()`. It closes idle connections in the pool's
    queue immediately and lets any in-flight one finish and be closed on
    return.

    A default instance (`default_pool_manager`, below) is what `PostgresCell`
    uses when no `pool_manager` is supplied, so this behaves as a drop-in
    fix with no caller changes required. Tests (and any caller that wants
    isolated pool-cache behaviour, e.g. a short idle interval to make
    eviction observable) construct their own `SharedPoolManager` and pass it
    to `PostgresCell(..., pool_manager=...)` explicitly.

    History: CH-0099
    """

    def __init__(self, *, idle_seconds: int | None = None, cache_max: int | None = None, pool_size: int | None = None, pool_max_overflow: int | None = None) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], _PoolManagerEntry] = {}
        self._idle_seconds = idle_seconds if idle_seconds is not None else _env_int("R2DB_POOL_IDLE_SECONDS", 300)
        self._cache_max = max(1, cache_max if cache_max is not None else _env_int("R2DB_POOL_CACHE_MAX", 32))
        base = pool_size if pool_size is not None else _env_int("R2DB_POOL_SIZE", 2)
        overflow = pool_max_overflow if pool_max_overflow is not None else _env_int("R2DB_POOL_MAX_OVERFLOW", 2)
        self._default_maxconn = max(1, base + overflow)

    def _evict_locked(self, now: float) -> None:
        """Called at the top of every `get_pool()`, under `self._lock`
        (mirrors `AppPoolManager._evict_idle_locked`): first retire every
        pool idle longer than `self._idle_seconds`, then -- independently --
        retire the least-recently-used pool(s) until at most `self._cache_
        max` remain. The two sweeps are separate passes for the same reason
        the reference implementation keeps them separate: an application
        that is still within its idle window but pushed out by the cap is a
        different, and more important, condition than one that simply went
        quiet -- the cap is what actually bounds total connections
        regardless of how many applications exist, per this class's
        docstring.
        """
        stale = [key for key, entry in self._entries.items() if now - entry.last_used > self._idle_seconds]
        for key in stale:
            entry = self._entries.pop(key)
            entry.pool.retire()

        while len(self._entries) > self._cache_max:
            oldest_key = min(self._entries.items(), key=lambda item: item[1].last_used)[0]
            entry = self._entries.pop(oldest_key)
            entry.pool.retire()

    def get_pool(self, key: tuple[str, str], dsn: str, *, schema: str, maxconn: int | None = None) -> "_RolePool":
        """Return the live pool for `key`, creating one (lazily, as before)
        if none is cached, and refresh its recency so it survives the next
        idle sweep. `dsn`/`schema`/`maxconn` are only consulted the moment a
        pool is (re)created for this key -- once cached, a lookup for the
        same key returns the existing pool as-is, exactly like the
        reference implementation, which also only reads its connection
        settings at first creation for a given key.
        """
        now = time.monotonic()
        with self._lock:
            self._evict_locked(now)
            entry = self._entries.get(key)
            if entry is not None:
                entry.last_used = now
                return entry.pool
            pool = _RolePool(dsn, schema=schema, maxconn=maxconn if maxconn is not None else self._default_maxconn)
            self._entries[key] = _PoolManagerEntry(pool=pool, last_used=now)
            return pool

    def release(self, key: tuple[str, str]) -> None:
        """Explicitly retire and drop the cached pool for `key`, if any --
        called by `PostgresCell.close()` (via `_PoolHandle.close()`). This is
        distinct from idle/LRU eviction (which only ever runs as a side
        effect of some *other* key's `get_pool()` call): closing a cell is an
        immediate, caller-driven release of exactly its own two pools,
        independent of this manager's lazy sweep and of whatever else is
        cached for other applications.
        """
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            entry.pool.retire()

    def dispose_all(self) -> None:
        """Retire every cached pool right now, regardless of key. Intended
        for process shutdown / test-suite teardown, not for routine use --
        routine release of one application's pools is `release()`, above."""
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.pool.retire()

    def stats(self) -> dict[str, dict[str, int | float]]:
        """Return every live pool's own `stats()` dict, keyed by `"<application_id>/<role>"` (a plain string, not the `(application_id, role)` tuple `self._entries` is keyed by: role alone would collide across different applications sharing this manager). Empty when no pool is cached. Reads `self._entries` under `self._lock`, the same lock every other method on this class already takes to touch it; each pool's own `stats()` call happens outside that lock, under the pool's own `_stats_lock`."""
        with self._lock:
            items = [(key, entry.pool) for key, entry in self._entries.items()]
        return {f"{application_id}/{role}": pool.stats() for (application_id, role), pool in items}

    def prepared_stats(self) -> list[dict[str, Any]]:
        """R-79 (WO §1.2 D-2, completion condition 8): a flat list across
        every live pool's own `prepared_stats(...)`, one dict per idle
        connection probed. Snapshots `(key, pool)` pairs under `self._lock`
        exactly like `stats()` above, then calls each pool's own `prepared_
        stats` OUTSIDE that lock -- probing drains/refills each pool's own
        queue, which is thread-safe on its own and does not need this
        manager's lock held for the duration."""
        with self._lock:
            items = [(key, entry.pool) for key, entry in self._entries.items()]
        rows: list[dict[str, Any]] = []
        for (application_id, role), pool in items:
            rows.extend(pool.prepared_stats(f"{application_id}/{role}"))
        return rows


class _PoolHandle:
    """`PostgresCell`'s own `self._runtime`/`self._developer` attribute: a
    thin, stateless-between-calls handle that resolves the live `_RolePool`
    from `SharedPoolManager` on every `.connection()` call rather than
    holding a direct reference to one pool for the cell's whole lifetime.
    That indirection is what makes eviction and recreation transparent to
    `PostgresCell` and its callers: if the pool behind this key was retired
    (idle timeout or LRU cap) since the last call, the next `.connection()`
    simply gets a freshly created one back from the manager -- same `dsn`/
    `schema`, so it authenticates as exactly the same single fixed role as
    before (D-3/§10.1: still no `SET ROLE`, still one role per pool) -- with
    no special handling required here or in `PostgresCell`.
    """

    def __init__(self, manager: SharedPoolManager, key: tuple[str, str], dsn: str, schema: str, maxconn: int | None) -> None:
        self._manager = manager
        self._key = key
        self._dsn = dsn
        self._schema = schema
        self._maxconn = maxconn

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        pool = self._manager.get_pool(self._key, self._dsn, schema=self._schema, maxconn=self._maxconn)
        with pool.connection() as conn:
            yield conn

    def close(self) -> None:
        self._manager.release(self._key)


# The process-wide default `PostgresCell` uses when no `pool_manager` is
# supplied explicitly -- constructed once at import time, reading
# `R2DB_POOL_*` from the environment then (§ SharedPoolManager docstring).
# Sized (and shaped) so the total ceiling stops scaling with the number of
# applications; see `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §4 for
# the resulting bounded arithmetic and how to size it for a given cluster.
default_pool_manager = SharedPoolManager()


class PostgresCell:
    """A `StorageBackend` over one application's own PostgreSQL database
    (architecture §8, "D-3 改訂": database-per-application, not
    schema-per-application -- each application's entities live in that
    database's `public` schema; `schema` below is `"public"` for every
    application, and the isolation boundary is which *database* a
    connection's DSN names, not a schema name inside a shared one).

    `application_id` and `schema` are supplied by the caller (the control
    plane), never derived from client request content (D-3: "the physical
    namespace is assigned by the control plane, not derived from client
    input" -- true of both the database name and the schema name within
    it). `runtime_dsn`/`developer_dsn` are two separate, already fully-formed connection strings authenticating as this application's `runtime` and `developer` PostgreSQL roles respectively, each already naming this application's own database (provisioned by, see); this class never embeds a control-plane credential and never widens a connection's role at runtime, so schema-changing operations physically execute under the `developer` role (DDL-capable on this database's `public` schema only) while queries and data mutations physically execute under the `runtime` role (DML only) -- a second, DB-enforced layer under the `developer: bool` check already performed by `bind_schema_operation` (SI-03 defence in depth).

    Connection pooling (D-3/§10.1, and the fix this class's `_runtime`/
    `_developer` attributes are part of): each is a `_PoolHandle` onto a
    pool owned by `pool_manager` -- `default_pool_manager` (module-level, a
    single process-wide `SharedPoolManager`) unless a caller supplies its
    own, e.g. a test that wants an isolated cache with a short idle
    interval. No pool is created here at construction time; `PostgresCell`
    itself now holds nothing heavier than DSNs and a pool-cache key
    (`application_id`, role) until something actually calls `.connection()`.
    Because the cache is shared across every `PostgresCell` instance rather
    than private to each one, the number of live pools is bounded by
    `pool_manager`'s own cap regardless of how many applications exist --
    see `SharedPoolManager`'s docstring and `r2db-api/docs/
    POSTGRES_PROVISIONING_RUNBOOK.md` §4 for the resulting arithmetic.
    `pool_size`, same as before, is this cell's own requested per-pool
    connection cap (`None` defers to `pool_manager`'s configured default,
    itself `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW` unless overridden) --
    it is only consulted the moment a pool is actually (re)created for this
    cell's key, exactly like every other pool setting here.

    History: CH-0098
    """

    def __init__(self, application_id: str, schema: str, *, runtime_dsn: str, developer_dsn: str, runtime_role: str, developer_role: str, pool_size: int | None = None, pool_manager: SharedPoolManager | None = None) -> None:
        validate_identifier(schema, field="schema")
        self.application_id = application_id
        self.schema = schema
        # Role *names* (not credentials) are needed at table-creation time to
        # embed the RLS policy (see `_create_entity`): D-3's third,
        # defence-in-depth layer, on top of schema separation and the two
        # distinct DB roles. They are control-plane-assigned constants, the
        # same trust level as `schema` above -- never taken from a client
        # request.
        validate_identifier(runtime_role, field="runtime_role")
        validate_identifier(developer_role, field="developer_role")
        self._runtime_role = runtime_role
        self._developer_role = developer_role
        # kept as a plain attribute, separate from `self._runtime` below, so `verify_platform_upgrades_applied` can open a single, UNPOOLED, explicitly-closed connection for its own one-shot cell open time check -- never through the shared pool manager. Reaching through `self._runtime`'s own pool instead
        # would leave a live connection sitting in that pool indefinitely
        # (pools are released only by `close()`/idle eviction, never by
        # this class itself), which would needlessly hold every served
        # application's runtime database open from the moment its cell is
        # constructed, before a single real request against it ever
        # arrives -- exactly the standing-connection cost this class' own
        # "no pool is created here at construction time" design (this
        # docstring's own paragraph above) exists to avoid.
        # history: CH-0008
        self._runtime_dsn = runtime_dsn
        manager = pool_manager if pool_manager is not None else default_pool_manager
        self._pool_manager = manager
        self._runtime = _PoolHandle(manager, (application_id, "runtime"), runtime_dsn, schema, pool_size)
        self._developer = _PoolHandle(manager, (application_id, "developer"), developer_dsn, schema, pool_size)

    def close(self) -> None:
        """Release this cell's own two pools back to the shared manager
        (`SharedPoolManager.release`, via `_PoolHandle.close`) -- retiring
        them immediately rather than waiting for idle/LRU eviction. This
        matters beyond tidiness: `application_id` is a cache key this
        manager is shared on, and a caller that deprovisions this
        application (dropping its database/roles) and later reprovisions
        the *same* `application_id` must not have a new `PostgresCell` for
        it silently hand back a stale pool of connections authenticated
        against credentials that no longer exist.
        """
        self._runtime.close()
        self._developer.close()

    def verify_platform_upgrades_applied(self) -> None:
        """Q4 WP-3 cell open time check (design D-3(f)/§3.7 data-plane
        steps 9-10, requester ruling 2026-09-05 U-2): before this cell is
        handed to `DataService` (its caller, `r2db_api.main`'s own
        `_cell_factory`, calls this immediately after constructing the
        cell -- "cell open" IS the moment `_cell_factory` runs, since every
        served application's cell is opened eagerly at startup, not
        lazily on first request, design §3.7's own "起動シーケンスの後、
        当該applicationのcellを初めて開くとき"), confirm this application's
        own per-application platform-upgrade ledger already has every
        number `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` requires.

        Read-only, over the RUNTIME role's own connection (U-2: "読み取り
        はruntime roleのSELECT 1本である") -- never the developer
        connection. Deliberately a single, UNPOOLED connection
        (`self._runtime_dsn`, opened and closed right here), never the
        shared runtime POOL (`self._runtime`) every ordinary request-
        serving call in this class borrows from: this check runs exactly
        once per cell, at cell open time, before any real request ever
        needs a pooled runtime connection at all -- reaching through the
        pool instead would leave a live connection sitting in it
        indefinitely (this class creates no pool at construction time
        otherwise; see this class' own docstring), holding every served
        application's own database connection open from startup for no
        request-serving reason. Raises `FoundationError`
        (`SERVICE_UNAVAILABLE`, F-12's own verbatim text) if anything is
        pending; does nothing otherwise.
        """
        conn = psycopg.connect(self._runtime_dsn, **_application_name_connect_kwargs())
        try:
            try:
                platform_upgrades.require_application_upgrades_applied(
                    conn,
                    ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME,
                    expected=platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
                    application_id=self.application_id,
                    ops_module=platform_upgrades.PEER_MODULE,
                )
            except platform_upgrades.PlatformUpgradeError as exc:
                fail("SERVICE_UNAVAILABLE", str(exc), status=503)
            finally:
                conn.rollback()
        finally:
            conn.close()

    # ---- catalog -----------------------------------------------------

    def _describe_table(self, name: str, table_info: "_TableInfo") -> dict[str, Any]:
        """One entity's `EntityDescriptor` (contract shape) -- factored out of `catalog()` below so `apply_schema`'s own `dry_run` response can build the identical descriptor for the ONE entity a schema operation targets, re-reading `table_info` from the SAME open transaction/connection a tentative (not yet committed, and about to be rolled back) DDL/registry write just ran in -- mirrors `ApplicationCell._describe_entity`'s identical role for the in-memory backend, without sharing code with it.

        History: CH-0009
        """
        unique_keys = [
            {"name": index_name, "fields": list(index_info["fields"])}
            for index_name, index_info in sorted(table_info.indexes.items())
            if index_info["unique"]
        ]
        # Contract 1.7.0: total over `table_info.columns` (like `field_types` below) -- `nullable` always present, `enum` only for a field the registry (`table_info.constraints`, read by `_load_catalog`'s own `_load_field_constraints`) actually carries a declaration for.
        # history: CH-0097
        field_constraints_out: dict[str, Any] = {}
        for field_name in table_info.columns:
            constraints = table_info.constraints.get(field_name, FieldConstraints())
            entry: dict[str, Any] = {"nullable": constraints.nullable}
            if constraints.enum is not None:
                entry["enum"] = list(constraints.enum)
            field_constraints_out[field_name] = entry
        return {
            "entity": name,
            "fields": sorted(table_info.columns),
            # `table_info.columns` is already `{field_name: declared_type_or_None}` -- `None` (untyped/JSONB) reports as `json`, decision (ii)'s own default.
            # history: CH-0010
            "field_types": {field_name: (declared_type or "json") for field_name, declared_type in table_info.columns.items()},
            "field_constraints": field_constraints_out,
            # R-1/R-2/§2: every entity this backend provisions is
            # server-addressed, mutable, and never reuses an
            # address within one entity's lifetime -- there is no
            # per-entity toggle for any of this (R-1: "クライアント
            # は区分を選べない").
            "mutation_class": "mutable",
            "address_fields": [_ID_COLUMN],
            "address_reuse": "never",
            "unique_keys": unique_keys,
        }

    def catalog(self, limits: ResourceLimits | None = None) -> list[dict[str, Any]]:
        """List this application's entities and their known fields, inside a transaction bounded by `statement_timeout`/`lock_timeout` derived from `limits` (`ResourceLimits()` when omitted), exactly like `query`/`transact`/`apply_schema`. A timeout maps to the same `LIMIT_EXCEEDED` those three operations already return."""
        if limits is None:
            limits = ResourceLimits()
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, None, None)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    info = self._load_catalog(conn)
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        return [self._describe_table(name, info[name]) for name in sorted(info)]

    def _load_catalog(self, conn: "psycopg.Connection[Any]", *, with_constraints: bool = True) -> dict[str, "_TableInfo"]:
        """The catalog-verification step D-4 requires before any client
        identifier may be composed with `sql.Identifier`: this is the live
        set of tables/columns/unique-indexes that actually exist in this
        application's schema right now, queried from `information_schema`/
        `pg_catalog` (never from request content), inside the same
        transaction as the operation being validated.

        R-1's declaration-completeness guard also lives here: every entity
        table this backend's own `_create_entity` provisions always carries
        a `bigint GENERATED ALWAYS AS IDENTITY` `id` column and a `uuid`
        `_r2db_revision` column -- if even one entity table does not
        actually have both (this deployment has never provisioned one that
        doesn't, but this is re-derived from live catalog state on every
        call rather than trusted as a standing assumption), publishing this
        application's catalog at all would be a false `mutable`/
        `address_fields`/`revision_preconditions` declaration for that
        entity (contract `declaration_required`: "must not be advertised as
        enabled unless every entity can produce one"). This fails the whole
        call closed (`SERVICE_UNAVAILABLE`) rather than silently omitting
        the offending entity or downgrading its declaration, naming only
        the offending entities (never a column value) in `details`.
        """
        columns_statement = sql.SQL(
            "SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name "
            "FROM information_schema.tables t "
            "JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = {schema} AND t.table_type = 'BASE TABLE' AND t.table_name <> ALL({bookkeeping_tables})"
        ).format(schema=sql.Placeholder(), bookkeeping_tables=sql.Placeholder())
        # Every unique index (composite or single-column) on any of this
        # application's tables, excluding the primary key (`id`'s own PK is
        # the address, not a domain uniqueness declaration -- R-1/§2) and
        # excluding partial/expression indexes (`create_index` never
        # produces either, so any that exist were not created by this
        # backend and are not a shape it understands). `NOT idx.indisunique`
        # rows (plain, non-unique indexes `create_index(unique=False)`
        # creates) are included too -- SI-08/R-5: an index is a real
        # resource and counts toward `schema_objects` whether or not it is
        # a uniqueness declaration.
        indexes_statement = sql.SQL(
            "SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, "
            "array_agg(a.attname ORDER BY k.ord) AS fields "
            "FROM pg_index idx "
            "JOIN pg_class c ON c.oid = idx.indrelid "
            "JOIN pg_class i ON i.oid = idx.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN LATERAL unnest(idx.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum "
            "WHERE n.nspname = {schema} AND NOT idx.indisprimary "
            "AND idx.indexprs IS NULL AND idx.indpred IS NULL "
            "GROUP BY c.relname, i.relname, idx.indisunique"
        ).format(schema=sql.Placeholder())

        tables: dict[str, dict[str, str | None]] = {}
        identity_ok: dict[str, bool] = {}
        revision_ok: dict[str, bool] = {}
        with conn.cursor() as cur:
            _run(cur, columns_statement, [self.schema, list(_BOOKKEEPING_TABLES)])
            for table_name, column_name, data_type, is_identity, domain_name in cur.fetchall():
                columns = tables.setdefault(table_name, {})
                if column_name == _ID_COLUMN:
                    identity_ok[table_name] = data_type == "bigint" and is_identity == "YES"
                    columns[_ID_COLUMN] = "integer"
                elif column_name == _REVISION_COLUMN:
                    revision_ok[table_name] = data_type == "uuid"
                    # Never a known/selectable field.
                    # history: CH-0011
                elif column_name.startswith(_RESERVED_INTERNAL_PREFIX):
                    continue
                else:
                    # WP-3 review, object/array DOMAIN unification: a
                    # column declared via one of this backend's own two
                    # JSON-shape DOMAINs reports its domain name here --
                    # checked first, since `data_type` alone (always
                    # `jsonb` for either domain) cannot distinguish them.
                    # A plain, non-domain column (including bare `jsonb`)
                    # falls through to the ordinary data-type mapping.
                    declared = _DOMAIN_TO_DECLARED.get(domain_name) if domain_name else None
                    if declared is None:
                        declared = _SQL_TYPE_TO_DECLARED.get(data_type)
                    columns[column_name] = declared

        offenders = sorted(
            name for name in tables
            if not identity_ok.get(name, False) or not revision_ok.get(name, False)
        )
        if offenders:
            fail(
                "SERVICE_UNAVAILABLE",
                "An entity table does not satisfy the required id/revision declaration.",
                status=503,
                details={"entities": offenders},
            )

        indexes: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in tables}
        with conn.cursor() as cur:
            _run(cur, indexes_statement, [self.schema])
            for table_name, index_name, is_unique, fields in cur.fetchall():
                if table_name not in tables:
                    continue
                prefix = f"{table_name}__"
                if not index_name.startswith(prefix):
                    # Not one of this backend's own indexes (R-5's physical
                    # naming convention) -- ignore rather than misreport it
                    # under a fabricated client name.
                    continue
                client_name = index_name[len(prefix):]
                indexes[table_name][client_name] = {"physical": index_name, "fields": tuple(fields), "unique": bool(is_unique)}

        # the side-table read (a nested SAVEPOINT + SELECT + RELEASE SAVEPOINT, `_load_field_constraints` below) is skipped entirely when `with_constraints` is `False` -- `query` (D-2 (2): "query の predicate 値は enum を検査しない") never uses `table_info.constraints` at all, so paying for that read on every read-only request is pure waste.
        # history: CH-0012
        constraints_by_entity = self._load_field_constraints(conn) if with_constraints else {}
        return {
            name: _TableInfo(columns=columns, indexes=indexes.get(name, {}), constraints=constraints_by_entity.get(name, {}))
            for name, columns in tables.items()
        }

    def _load_field_constraints(self, conn: "psycopg.Connection[Any]") -> dict[str, dict[str, "FieldConstraints"]]:
        """Contract 1.7.0: reads the side-table registry (`public._r2db_field_constraints`, migration `0010_field_constraints_upgrade.sql`) -- the declaration's own source of truth (physical column constraints are never added, §4). `conn` is already inside the caller's own `with conn.transaction():` block (`catalog`/`transact`/`apply_schema` above), so this method opens a NESTED transaction (a real PostgreSQL SAVEPOINT once already inside one) around its own read: if the table does not exist yet (an application that has never run `python -m r2db_api.ops upgrade-applications` for upgrade 10 completion condition 10), that one savepoint rolls back to a clean, still-usable state and this method returns `{}` -- every entity/field then reports the version-wide default (`nullable: true`, no `enum`). An application
        that never declares any `field_constraints`/`enum`/`nullable` at
        all keeps working unmodified without ever needing that upgrade;
        only an attempt to WRITE a declaration (`_write_field_constraints`
        below) actually needs the table to exist -- that failure is left
        to propagate to this class' own existing `except psycopg.Error`
        handling (`transact`/`apply_schema`), which already maps it to a
        safe `SERVICE_UNAVAILABLE` with no rows changed (the enclosing
        `with conn.transaction():` rolls the whole operation back).

        History: CH-0013
        """
        result: dict[str, dict[str, FieldConstraints]] = {}
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    _run(cur, sql.SQL("SELECT entity_name, field_name, nullable, enum_values FROM public.{}").format(sql.Identifier(_FIELD_CONSTRAINTS_TABLE)))
                    rows = cur.fetchall()
        except psycopg.errors.UndefinedTable:
            return result
        for entity_name, field_name, nullable, enum_values in rows:
            result.setdefault(entity_name, {})[field_name] = FieldConstraints(
                enum=tuple(enum_values) if enum_values is not None else None,
                nullable=bool(nullable),
            )
        return result

    def _write_field_constraints(self, conn: "psycopg.Connection[Any]", entity: str, field_name: str, constraints: "FieldConstraints") -> None:
        """Contract 1.7.0: persists (or clears) one field's own row in the side-table registry -- the ONLY write path into it, called from `apply_schema`'s `create_entity`/`add_field`/`alter_field` branches, always inside that method's own outer `with conn.transaction():` (never a separate commit). A field whose
        constraints are no longer declared at all (`not constraints.is_
        declared` -- `alter_field` clearing back to the version-wide
        default) has its row DELETEd rather than left standing; `create_
        entity`/`add_field` only ever call this for a field the request
        gave an actual spec (never for the fully-default case, so a plain
        `create_entity`/`add_field` that never mentions `field_constraints`
        /`enum`/`nullable` never touches this table at all).

        History: CH-0096
        """
        table = sql.Identifier(_FIELD_CONSTRAINTS_TABLE)
        with conn.cursor() as cur:
            if not constraints.is_declared:
                _run(
                    cur,
                    sql.SQL("DELETE FROM public.{table} WHERE entity_name = {ph} AND field_name = {ph2}").format(table=table, ph=sql.Placeholder(), ph2=sql.Placeholder()),
                    [entity, field_name],
                )
                return
            enum_json = Jsonb(list(constraints.enum)) if constraints.enum is not None else None
            _run(
                cur,
                sql.SQL(
                    "INSERT INTO public.{table} (entity_name, field_name, nullable, enum_values) VALUES ({e}, {f}, {n}, {v}) "
                    "ON CONFLICT (entity_name, field_name) DO UPDATE SET nullable = EXCLUDED.nullable, enum_values = EXCLUDED.enum_values"
                ).format(table=table, e=sql.Placeholder(), f=sql.Placeholder(), n=sql.Placeholder(), v=sql.Placeholder()),
                [entity, field_name, constraints.nullable, enum_json],
            )

    def _clear_field_constraints(self, conn: "psycopg.Connection[Any]", entity: str) -> None:
        """`drop_entity`'s own registry cleanup, protected the same way `_load_field_constraints` above protects its own read -- a real PostgreSQL SAVEPOINT (a NESTED transaction, `conn` is already inside `apply_schema`'s own outer `with conn.transaction():`) around the `DELETE`, swallowing `UndefinedTable` if the side table itself was never created (an application that has never run upgrade `10`). `drop_entity` must
        succeed for such an application regardless -- dropping an entity
        that never had a `field_constraints` row is unrelated to whether
        the registry TABLE exists at all, unlike `alter_field`/`create_
        entity`/`add_field` actually WRITING a declaration, which legitimately
        needs the table and is left to fail closed (`SERVICE_UNAVAILABLE`,
        `_write_field_constraints`'s own docstring) if it is missing.

        History: CH-0014
        """
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    _run(
                        cur,
                        sql.SQL("DELETE FROM public.{table} WHERE entity_name = {ph}").format(table=sql.Identifier(_FIELD_CONSTRAINTS_TABLE), ph=sql.Placeholder()),
                        [entity],
                    )
        except psycopg.errors.UndefinedTable:
            return

    # ---- idempotency (contract 1.7.0 D-5) --------------------------
    #
    # Ruling I-1/U-3 = (A): the Postgres-backend counterpart of `Application
    # Cell`'s process-internal dict -- the `public._r2db_idempotency` side
    # table, migration `0011_idempotency_records_upgrade.sql`, read/written
    # inside the SAME `with conn.transaction():` block `transact`/`apply_
    # schema` already open (D-5 (1)/(3): "同一 tx で書く"). Expiry uses
    # PostgreSQL's own `now()`, never a client-supplied clock value -- this
    # is a durable side table shared by concurrent requests, unlike
    # `ApplicationCell`'s single-process dict, so the DATABASE's own notion
    # of "now" is what a lazy reclaim compares against.
    #
    # Read (`_idempotency_lookup`) fails CLOSED on a missing table (ruling audit) -- an application that has never run upgrade 11 gets `SERVICE_UNAVAILABLE` right here, before target-existence/execution, exactly like the WRITE (`_idempotency_store`) already did: `UndefinedTable` is left to propagate to `transact`/`apply_schema`'s own `except psycopg.Error` clause, rolling back the (as yet empty) transaction and touching no row. This method runs FIRST on the
    # idempotent path (before `catalog`/target-existence in `transact`;
    # right after `catalog` but before any operation-specific work in
    # `apply_schema`), so nothing has executed yet when it raises.
    # `_idempotency_reserve` (below) can therefore no longer actually
    # observe `UndefinedTable` in practice: on this same path it always
    # runs after this method has already succeeded (or already raised),
    # in the SAME transaction, so the table's existence cannot change in
    # between -- its own guard is kept anyway (defense in depth, and it
    # matches `_load_field_constraints`'s own posture of not depending on
    # a caller having gotten the ordering right).
    # history: CH-0015

    def _idempotency_key_lock(self, conn: "psycopg.Connection[Any]", key: str) -> None:
        """transaction-scoped advisory lock keyed on this idempotency key -- taken directly in the OUTER `with conn.transaction():` (`transact`/`apply_schema`), immediately BEFORE calling `_idempotency_lookup`, never inside `_idempotency_lookup`'s own nested `with conn.transaction():` (a SAVEPOINT).
        `pg_advisory_xact_lock` auto-releases only at the enclosing
        (outer) transaction's own commit/rollback, never at a savepoint
        rollback or a savepoint's own commit -- taking it here, before
        the savepoint even opens, makes that lifetime obvious by
        construction rather than relying on that Postgres-specific
        savepoint/advisory-lock interaction.

        Effect: a second concurrent request for the SAME key blocks here
        until the first's transaction commits or rolls back. It then
        proceeds to `_idempotency_lookup` and sees either the first
        request's now-committed record (same digest -> replay, different
        digest -> CONFLICT) or nothing at all (first request rolled
        back -- e.g. `NOT_FOUND`/a refused confirmation -- so this
        request executes as new). The DB is per-Application (module
        docstring), so the raw idempotency key alone is Application-
        scoped already -- no extra scoping component is needed here.

        Two-int form (`_IDEMPOTENCY_KEY_LOCK_NAMESPACE`, `hashtext(key)`)
        chosen over a plain `hashtext(key)::bigint`: `hashtext` alone is
        only a 32-bit hash, so a bare-bigint lock would put every key's
        lock in the SAME narrow 32-bit-sized space `_IDEMPOTENCY_COUNT_
        ADVISORY_LOCK_KEY` and `ops.py::_RITUAL_ADVISORY_LOCK_KEY` also
        occupy (all three are small positive integers); namespacing the
        high 32 bits keeps per-key locks in a visibly separate space.
        `hashtext` collisions between two DIFFERENT keys are accepted (ruling): a collision only over-serializes (two unrelated keys briefly wait on each other), it can never under-serialize.

        History: CH-0016
        """
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SELECT pg_advisory_xact_lock(%s, hashtext(%s))"), [_IDEMPOTENCY_KEY_LOCK_NAMESPACE, key])

    def _idempotency_reserve_lock(self, conn: "psycopg.Connection[Any]") -> None:
        """table-level advisory lock serializing `_idempotency_reserve`'s COUNT-then-write across DIFFERENT keys -- taken directly in the OUTER transaction, BEFORE calling `_idempotency_reserve`, never inside that method's own nested `with conn.transaction():` savepoint (same reasoning as `_idempotency_key_lock` above: the lock's lifetime should not depend on savepoint/advisory-lock interaction being understood by a future reader). A constant lock id (not keyed on anything)
        because this guards the TABLE'S row count, not any one key.

        `LOCK TABLE public.<idempotency table> IN SHARE MODE` was
        considered and rejected for this same purpose: two concurrent
        SHARE lock holders never conflict with EACH OTHER (SHARE only
        conflicts with ROW EXCLUSIVE and stronger), so both would pass
        the COUNT and only then deadlock against each other's own
        subsequent INSERT (which needs ROW EXCLUSIVE, which SHARE does
        conflict with) -- see the WP-6d report for the Phase 9 R-2
        precedent's own lock mode finding. `pg_advisory_xact_lock` has
        no such self-conflict-free class: a second holder of the SAME
        key always waits for the first, full stop.

        History: CH-0017
        """
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SELECT pg_advisory_xact_lock(%s)"), [_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY])

    def _idempotency_lookup(self, conn: "psycopg.Connection[Any]", key: str) -> tuple[str, str, dict[str, Any]] | None:
        table = sql.Identifier(_IDEMPOTENCY_TABLE)
        with conn.transaction():
            with conn.cursor() as cur:
                _run(cur, sql.SQL("DELETE FROM public.{table} WHERE expires_at <= now()").format(table=table))
            with conn.cursor() as cur:
                _run(cur, sql.SQL("SELECT request_digest, kind, response FROM public.{table} WHERE idempotency_key = {ph}").format(table=table, ph=sql.Placeholder()), [key])
                row = cur.fetchone()
        if row is None:
            return None
        digest, kind, payload = row
        return digest, kind, payload

    def _idempotency_reserve(self, conn: "psycopg.Connection[Any]", limits: ResourceLimits) -> None:
        table = sql.Identifier(_IDEMPOTENCY_TABLE)
        # the lazy-reclaim DELETE this method used to also issue here is dropped -- `_idempotency_lookup`, this same transaction, always runs first on this path and already reclaimed every expired record moments earlier; a second DELETE here was always a 0-row no-op (measured closure: `_run` count for a keyed write drops from 11 to 10; a replay never reaches this method at all and stays at 4).
        # history: CH-0018
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Phase 10 WP-6a (design docs/design/
                    # PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-5(ii) region
                    # (iii)): `idempotency_entries` stays a declared DB-side
                    # `enforced` class (region (iii)) via this count-then-
                    # check, but the same-key serialization AND the count
                    # lock that would close this count's TOCTOU window are
                    # WP-6d-i's scope (both peers, one pass) -- not added
                    # here.
                    # history: CH-0085
                    _run(cur, sql.SQL("SELECT count(*) FROM public.{table}").format(table=table))
                    (count,) = cur.fetchone()
        except psycopg.errors.UndefinedTable:
            count = 0
        # checked BEFORE this request executes anything -- reusing the SAME generic `ResourceLimits.check()` every other COUNT-valued class already uses (`ApplicationCell`'s identical `_idempotency_reserve` comment).
        # history: CH-0019
        limits.check("idempotency_entries", count + 1)

    def _idempotency_store(self, conn: "psycopg.Connection[Any]", key: str, *, digest: str, kind: str, payload: dict[str, Any], retention_ms: int) -> None:
        # M-6 (addendum 2 closure audit): `ON CONFLICT (idempotency_key) DO UPDATE`, not a bare `INSERT` -- a resend of a key whose stored record was just treated as absent (`_idempotency_record_has_request_id` returned false, at both call sites below) reaches this SAME method for the SAME key, and must overwrite the stale row rather than fail on the primary key it still holds -- an expired-but-not-yet-reaped row, or a pre-1.7.0-shaped row with no `request_id` at all, are the only ways a live row can still be sitting under this key when this INSERT runs. Mirrors
        # `ApplicationCell._idempotency_store`'s plain dict assignment,
        # which overwrites unconditionally by construction.
        #
        # this `ON CONFLICT DO UPDATE` is NOT what makes concurrent same-key requests safe -- `_idempotency_key_lock` (taken by every caller before `_idempotency_lookup`, in the same outer transaction) is what closes that race, by making the second concurrent request wait for the first's commit/rollback before either one reaches this method at all. Once that lock serializes entry,
        # nothing else can be racing THIS INSERT for the SAME key: the
        # conflict this clause resolves is only ever this key's own
        # prior (already-committed, sequential) row -- never a row a
        # peer transaction is concurrently trying to write right now.
        # Kept as `DO UPDATE` (not narrowed to a bare `INSERT`) purely
        # for that stale-row-still-present case above, not for
        # concurrency.
        # history: CH-0020
        table = sql.Identifier(_IDEMPOTENCY_TABLE)
        with conn.cursor() as cur:
            _run(
                cur,
                sql.SQL(
                    "INSERT INTO public.{table} (idempotency_key, request_digest, kind, response, expires_at) "
                    "VALUES ({k}, {d}, {kind}, {r}, now() + ({ms} * interval '1 millisecond')) "
                    "ON CONFLICT (idempotency_key) DO UPDATE SET "
                    "request_digest = EXCLUDED.request_digest, kind = EXCLUDED.kind, "
                    "response = EXCLUDED.response, expires_at = EXCLUDED.expires_at"
                ).format(table=table, k=sql.Placeholder(), d=sql.Placeholder(), kind=sql.Placeholder(), r=sql.Placeholder(), ms=sql.Placeholder()),
                [key, digest, kind, Jsonb(payload), retention_ms],
            )

    # ---- query ---------------------------------------------------------

    def query(
        self,
        entity: str,
        *,
        select: list[str],
        where: list[Predicate],
        page_size: int,
        limits: ResourceLimits,
        order_by: list[dict[str, Any]] | None = None,
        cursor: str | None = None,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> QueryOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity, field="entity")
        _reject_reserved_entity_name(entity, field="entity")  # WP-2(b) fix round 2, item C
        validate_page_size(page_size, limits)
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    # `query` never reads `table_info.constraints` (D-2 (2): predicates are not bound by `enum`/`nullable`) -- skip the side-table read.
                    # history: CH-0021
                    catalog = self._load_catalog(conn, with_constraints=False)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    table_info = catalog[entity]
                    known_fields = set(table_info.columns)
                    validate_projection(select, known_fields)
                    validate_predicates(where, known_fields)
                    # identifier/catalog-checked order_by, with a deterministic trailing `id ASC` tie-break appended whenever the caller's own order_by does not already mention `id` -- the exact same shared function `ApplicationCell.query` uses, so both backends accept/reject the same order_by shapes identically.
                    # history: CH-0022
                    order_spec = _resolve_order_by(order_by, known_fields)
                    order_by_count = len(order_by) if order_by else 0
                    limits.check("query_complexity", len(where) + len(select) + order_by_count)
                    # validate every predicate's value type before touching stored rows at all -- the same shared function and the same ordering `ApplicationCell.query` uses.
                    # history: CH-0023
                    _validate_predicate_types(where, table_info.columns)
                    # keyset paging (design D-3 (3), D-6): the cursor's binding hash covers the Application scope, entity, and the normalized where/order_by only (never select/size, which do not decide a row's position) -- decoded (and count/type-checked) here, before any SQL referencing it runs.
                    # history: CH-0024
                    where_terms = [(p.field, p.operator, p.value) for p in where]
                    binding = canonical_page_binding(self.application_id, entity, where_terms, order_spec)
                    cursor_values: list[Any] | None = None
                    if cursor is not None:
                        cursor_values = decode_and_check_page_cursor(cursor, binding, order_spec, table_info.columns)
                    where_sql, where_params = self._where_clause(where, table_info.columns)
                    if cursor_values is not None:
                        # keyset paging (design D-3 (4)): the keyset predicate replaces the old OFFSET, ANDed onto the caller's own where clause.
                        keyset_sql, keyset_params = _keyset_predicate_sql(order_spec, cursor_values, table_info.columns)
                        where_sql = sql.SQL("{w} AND {k}").format(w=where_sql, k=keyset_sql) if where_sql is not None else keyset_sql
                        where_params = list(where_params) + keyset_params
                    # keyset paging (design D-3 (10)): the internal projection reads select's own columns plus every order_spec column select omits (tie-break `id` included), so the cursor can always be rebuilt from the fetched row -- trimmed back to select alone below, once the row is fetched.
                    order_only_fields = [field_name for field_name, _direction in order_spec if field_name not in select]
                    read_columns = list(select) + order_only_fields
                    statement = self._select_statement(entity, read_columns, where_sql, order_spec, page_size, revision_column=_REVISION_COLUMN)
                    with conn.cursor() as cur:
                        _run(cur, statement, where_params)
                        rows = cur.fetchall()
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # `rows` was fetched with `LIMIT page_size + 1` (the look-ahead row, if present, is never returned to the caller -- it only signals `has_more`); `min(len(rows), page_size)` therefore equals `page_size` whenever at least `page_size` rows matched, or the true (smaller) match count otherwise -- exactly the quantity `ApplicationCell.query`'s own equivalent check computes from its full (unbounded) in-memory match list, before it slices to a window.
        # history: CH-0025
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        # Every row was selected as `read_columns ++ [_r2db_revision::text]`
        # (`_select_statement`, in `postgres_sql.py`) with `read_columns`
        # = `select` followed by any order_spec-only columns (D-3 (10)) --
        # `select` is therefore always `read_columns`'s own prefix, so
        # `row[:len(select)]` recovers exactly the caller's own projection,
        # and the revision stays the last column, index-aligned with
        # `page_rows` (R-4: capability `revision_preconditions: enabled`
        # means every entity is mutable, so a query response always
        # includes revisions).
        items = [dict(zip(select, row[: len(select)])) for row in page_rows]
        revisions = [row[-1] for row in page_rows]
        next_cursor = None
        if has_more:
            # keyset paging (design D-3 (4)): the next cursor encodes the LAST
            # returned row's own order_spec values (tie-break included),
            # never a count or an offset -- read back through `read_
            # columns`'s own index, since `order_spec` fields may live
            # past `select`'s own prefix.
            column_index = {field_name: i for i, field_name in enumerate(read_columns)}
            last_row = page_rows[-1]
            cursor_position = [last_row[column_index[field_name]] for field_name, _direction in order_spec]
            next_cursor = encode_page_cursor(cursor_position, binding)
        return QueryOutcome(items=items, revisions=revisions, has_more=has_more, next_cursor=next_cursor)

    _select_statement = staticmethod(_select_statement)
    _order_by_sql = staticmethod(_order_by_sql)

    # ---- mutations -------------------------------------------------------

    def transact(
        self,
        entity: str,
        operations: list[dict[str, Any]],
        limits: ResourceLimits,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> MutationOutcome:
        """`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): the single tx-exit point sits right before the pre-commit hook, inside the SAME `with conn.transaction():` block every operation already writes its (uncommitted) row changes in. A `dry_run`
        forces a real ROLLBACK via `psycopg.Rollback` (caught and
        swallowed by `conn.transaction()`'s own `__exit__`, never
        surfacing as an error -- `ApplicationCell.transact`'s in-memory
        `before`-restore, realized with a real transaction instead of a
        `deepcopy`) rather than committing; `committed` below carries the
        decided result out of that block, since a raise cannot itself
        return a value.

        History: CH-0027
        """
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity, field="entity")
        _reject_reserved_entity_name(entity, field="entity")  # WP-2(b) fix round 2, item C
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.", details=violation("request_schema", field="operations"))
        limits.check("batch_items", len(operations))
        affected = 0
        assigned_addresses: list[dict[str, Any]] = []
        # whether this batch passed through the DESTRUCTIVE_CONFIRMATION_V1 choke -- see `ApplicationCell.transact`'s identical comment (parity).
        # history: CH-0095
        destructive = False
        committed = True
        # Set the instant `audit_hook.pre_commit()` returns successfully --
        # everything that can still fail after that point is this method's
        # OWN data commit (the implicit `conn.commit()` `conn.transaction()`
        # issues on normal `with`-block exit), never the audit write again.
        # This is what lets the `except psycopg.Error` clause below tell
        # "the durable audit row committed but the data commit then failed"
        # (D-2's error-row case) apart from every other psycopg failure.
        hook_fired = False
        idempotency_digest_value: str | None = None
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    # Contract 1.7.0 (addendum 2 S-b, ruling): the idempotency lookup -- see `ApplicationCell.transact`'s identical comment for the ordering rationale (after bounds, before target existence). A `dry_run` never consults or writes a record (ruling).
                    # history: CH-0028
                    if idempotency_key is not None and not dry_run:
                        assert plan_request is not None  # service.py always builds this
                        idempotency_digest_value = idempotency_digest(plan_request)
                        # taken in THIS outer transaction, before `_idempotency_lookup` opens its own nested savepoint -- see `_idempotency_key_lock`'s own docstring for why the lock must sit here and not inside that savepoint.
                        # history: CH-0029
                        self._idempotency_key_lock(conn, idempotency_key)
                        record = self._idempotency_lookup(conn, idempotency_key)
                        # a record with no `request_id` (pre-1.7.0) is not a usable replay source -- treated as absent, checked before the digest comparison.
                        # history: CH-0030
                        if record is not None and _idempotency_record_has_request_id(record[2]):
                            stored_digest, _stored_kind, stored_payload = record
                            if stored_digest != idempotency_digest_value:
                                fail(
                                    "CONFLICT", "This idempotency key was already used with a different request.", status=409,
                                    details={"violated_declaration": "idempotency_key", "field": "idempotency_key"},
                                )
                            # answered from the record -- target existence, confirmation, precondition and execution never run for a replay.
                            # history: CH-0031
                            return MutationOutcome(
                                affected=stored_payload["affected"], assigned_addresses=stored_payload["assigned_addresses"],
                                destructive=False, committed=True, plan=None, replayed=True,
                                # the ORIGINAL execution's own `request_id` (guaranteed present), no fallback to this resend's own.
                                # history: CH-0032
                                request_id=stored_payload["request_id"],
                            )
                        # capacity checked before this request executes anything. the table-level count lock is likewise taken in THIS outer transaction, before `_idempotency_reserve` opens its own nested savepoint.
                        # history: CH-0033
                        self._idempotency_reserve_lock(conn)
                        self._idempotency_reserve(conn, limits)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    table_info = catalog[entity]
                    # Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a, WP-2b):
                    # read ONCE, before any row change this transaction is
                    # about to (tentatively) make -- mutations never
                    # advance this counter, but reading it here (rather
                    # than after the loop) keeps this identical in spirit
                    # to `apply_schema`'s own "before this operation's own
                    # tentative write" read. gated on `dry_run or plan is not None` too -- an ordinary apply (neither) skips both the digest computation AND this method's own extra `_read_schema_revision` round trip, which `delete` would otherwise pay twice over (once here, once for its own confirmation phrase).
                    # history: CH-0034
                    expected_plan = (
                        compute_plan_token(plan_request, self._read_schema_revision(conn))
                        if plan_request is not None and (dry_run or plan is not None)
                        else None
                    )
                    for operation_index, operation in enumerate(operations):
                        if deadline is not None and clock is not None:
                            # per-operation deadline check, not only before/after the whole batch.
                            # history: CH-0035
                            limits.check_deadline(deadline, clock)
                        # this operation's own position in the request's `operations` list -- `_apply` composes `details.field` as a request-internal path from it.
                        # history: CH-0036
                        count, address, op_destructive = self._apply(conn, entity, operation, table_info, operation_index)
                        affected += count
                        destructive = destructive or op_destructive
                        if address is not None:
                            assigned_addresses.append(address)
                        limits.check("result_items", affected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    # Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single
                    # tx-exit point -- plan validity, then commit vs
                    # rollback (dry_run) vs real commit. Reached only once
                    # every operation above has tentatively succeeded (a
                    # confirmation/precondition/value/limit refusal inside
                    # `_apply` already raised and rolled this transaction
                    # back via the normal exception path below).
                    if plan is not None and plan != expected_plan:
                        fail(
                            "PRECONDITION_FAILED", "The plan no longer matches this request or the Application's schema.",
                            status=412, details={"violated_declaration": "plan"},
                        )
                    if dry_run:
                        committed = False
                        raise psycopg.Rollback()
                    # the pre-commit hook is the LAST statement inside this `with conn.transaction():` block -- a raise here propagates straight through the block's own `__exit__`, which rolls the data transaction back exactly like any other exception raised inside it (no special-casing needed at this call site: fail-closed by construction).
                    # history: CH-0037
                    if destructive and audit_hook is not None:
                        audit_hook.pre_commit()
                        hook_fired = True
                    # Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c):
                    # recorded in the SAME `with conn.transaction():`
                    # block as the data changes above -- the LAST
                    # statement before this block's own normal exit
                    # (implicit COMMIT). See this class' own "idempotency"
                    # section header comment for the strict (non-nested-
                    # savepoint) `UndefinedTable` handling here.
                    if idempotency_key is not None and idempotency_digest_value is not None:
                        self._idempotency_store(
                            conn, idempotency_key, digest=idempotency_digest_value, kind="mutation",
                            payload={"affected": affected, "assigned_addresses": assigned_addresses, "request_id": request_id},
                            retention_ms=limits.idempotency_retention_ms,
                        )
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.UniqueViolation as exc:
                self._fail_unique_conflict(entity, exc)
            except psycopg.errors.DataError:
                self._fail_client_value()
            except psycopg.Error:
                # `hook_fired` is only `True` once the durable pre-commit row has already committed on its own (separate) connection -- so an exception reaching here after that point can only be this method's own data commit failing. Record the durable
                # `outcome="error"` row for the same `request_id` (still
                # fail-closed: this call may itself raise `FoundationError`
                # SERVICE_UNAVAILABLE, which is exactly what happens next
                # regardless of whether it does).
                # history: CH-0094
                if hook_fired and audit_hook is not None:
                    audit_hook.commit_failed()
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # `conn.transaction()` rolls back the *entire* batch on any exception (including a `FoundationError` raised by a later operation), giving the whole batch one real database transaction in place of `ApplicationCell`'s in-memory deepcopy/restore.
        # `assigned_addresses` (CCR-13) lists, in operation order, the address of every operation that resolved to an insert (a plain `insert`, or an `upsert` whose declared key found no existing row) -- an `upsert` that resolved to an update contributes nothing here, exactly like `ApplicationCell.transact`. `plan` is surfaced only for a `dry_run` -- `None` for a real commit (`committed=True`), matching `ApplicationCell.transact`.
        # history: CH-0038
        return MutationOutcome(
            affected=affected, assigned_addresses=assigned_addresses, destructive=destructive,
            committed=committed, plan=(expected_plan if not committed else None), request_id=request_id,
        )

    def _fail_unique_conflict(self, entity: str, exc: "psycopg.errors.UniqueViolation") -> None:
        """map a real PostgreSQL `UniqueViolation` (raised naturally by any INSERT/UPDATE that collides with a `create_index(unique=True)`-declared index -- including one other than the key an `upsert` used for its own existence test, R-5's "既存重複は CONFLICT") to the contract's `CONFLICT`, disclosing at most the client-recognizable index name and never PostgreSQL's own DETAIL text, constraint/index internals, or any row value. `exc.
        diag.constraint_name` is PostgreSQL's own (physical) index name; it
        is only ever used here to look up the corresponding client name by
        stripping this backend's own `{entity}__` naming convention -- never
        surfaced to the caller directly.

        History: CH-0039
        """
        physical = exc.diag.constraint_name or ""
        prefix = f"{entity}__"
        details: dict[str, Any] = {}
        if physical.startswith(prefix):
            details = {"index": physical[len(prefix):]}
        fail("CONFLICT", "A declared uniqueness key would be violated.", status=409, details=details)

    def _fail_client_value(self) -> None:
        """a `psycopg.errors.DataError` (SQLSTATE class 22 -- e.g. `NumericValueOutOfRange`, or a NUL byte PostgreSQL's `text`/`jsonb` storage cannot hold at all) is always a decisive, deterministic client-supplied-value bug, not a transient server condition -- `VALIDATION_FAILED`, never `SERVICE_UNAVAILABLE` (which reads as "retry", and an AI agent client retrying an identical, never-succeeding request is exactly the failure mode this refusal exists to prevent). This is a second,
        defence-in-depth layer underneath the shared boundary's own value-
        domain checks (`r2db_api.structured._check_type`'s integer-range/
        NUL-byte validation, `_validate_wildcard_pattern`'s grammar check)
        -- those already refuse every value this maps today before it ever
        reaches SQL, so reaching this handler in practice means either
        check has a gap, not that this handler is the primary defence.
        Fixed message, no `details`: unlike `_fail_unique_conflict` above,
        a single `DataError` from a whole batch/statement cannot be
        reliably attributed to one specific field from this generic catch
        site, so no field name is guessed at (`errors.disclosure`: never
        wrong information is safer than no information).

        History: CH-0040
        """
        fail("VALIDATION_FAILED", "A value in this request is not acceptable to the underlying storage.")

    _bind_value = staticmethod(_bind_value)

    def _apply(self, conn: "psycopg.Connection[Any]", entity: str, operation: dict[str, Any], table_info: "_TableInfo", operation_index: int) -> tuple[int, dict[str, Any] | None, bool]:
        field_types = table_info.columns
        known_fields = set(field_types)
        bound = bind_mutation(operation, known_fields, operation_index=operation_index)
        # Contract 1.7.0: this entity's own declared constraints, already read by `_load_catalog` into `table_info` (addendum 2 S-k's 6 write call sites all pass this through to `_check_type`; the 2 predicate call sites never do).
        # history: CH-0093
        entity_constraints = table_info.constraints
        # every `details.field` this method raises for a VALUE-position defect in `bound.values` names the request-internal PATH to that value.
        # history: CH-0092
        values_path = f"operations/{operation_index}/values/"

        if bound.operation == "insert":
            # Contract 1.7.0 (D-2 (3)(ii), addendum R-c): the "declared
            # non-nullable field was never given a value at all" check,
            # insert-only -- mirrors `ApplicationCell._apply`'s identical
            # check (see that method's own comment for why this cannot be
            # folded into the choke point itself).
            missing_non_nullable = sorted({name for name, c in entity_constraints.items() if not c.nullable} - set(bound.values))
            if missing_non_nullable:
                missing_field = missing_non_nullable[0]
                fail(
                    "VALIDATION_FAILED",
                    "A field declared nullable: false requires a value on insert.",
                    details={"field": values_path + missing_field, "violated_declaration": "nullable", "declared_type": _declared_type_label(field_types.get(missing_field)), "observed_type": "absent"},
                )
            # value types are validated before anything is sent to the database.
            # history: CH-0042
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))
            row_id = self._insert(conn, entity, bound.values, field_types)
            return 1, {"address": {"id": row_id}}, False

        if bound.operation == "upsert":
            count, address = self._apply_upsert(conn, entity, bound, table_info, values_path)
            return count, address, False

        # update / delete: R-7, corrigendum M-9 -- validate every value's
        # type (predicate values, and for `update` the write values too)
        # before executing anything, symmetric with the `insert` branch
        # above and with `ApplicationCell._apply`.
        _validate_predicate_types(bound.where, field_types, path_prefix=f"operations/{operation_index}/where")
        if bound.operation == "update":
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))

        where_sql, where_params = self._where_clause(bound.where, field_types)

        if bound.operation == "delete":
            # destructive confirmation is checked before any precondition-related outcome (never resolves to a PRECONDITION_FAILED/NOT_FOUND).
            # history: CH-0043
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                delete_confirmation_phrase(entity, bound.where, self._read_schema_revision(conn)),
                "Delete requires explicit destructive confirmation.",
                consequence="Rows matching the filter are permanently deleted; there is no in-band restore.",
                reversible_alternative=None,
                recovery=None,
            )
            # reaching this point means the confirmation choke above did not raise -- confirmed-destructive, same signal `ApplicationCell._apply` returns.
            # history: CH-0044
            affected = self._delete(conn, entity, where_sql, where_params, bound.expected_revision)
            return affected, None, True

        affected = self._update(conn, entity, bound.values, where_sql, where_params, field_types, bound.expected_revision)
        return affected, None, False

    _append_revision_predicate = staticmethod(_append_revision_predicate)

    def _resolve_precondition_miss(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> None:
        """when a revision-qualified UPDATE/DELETE affects zero rows, re-evaluate the caller's own predicate alone (no revision clause), in the same transaction, to decide which of the two failures applies -- `PRECONDITION_FAILED` (a row exists, but its revision was not the one asserted) or `NOT_FOUND` (no row matches the predicate at all, so there was no row to assert about).

        History: CH-0046
        """
        if self._exists(conn, table, where_sql, where_params):
            fail("PRECONDITION_FAILED", "The row's revision no longer matches the supplied precondition.", status=412)
        fail("NOT_FOUND", "No row matches the supplied filter.", status=404)

    def _exists(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> bool:
        inner = sql.SQL("SELECT 1 FROM {table}").format(table=table)
        if where_sql is not None:
            inner = sql.SQL("{base} WHERE {where}").format(base=inner, where=where_sql)
        statement = sql.SQL("SELECT EXISTS({inner})").format(inner=inner)
        with conn.cursor() as cur:
            _run(cur, statement, where_params if where_sql is not None else [])
            row = cur.fetchone()
            return bool(row[0]) if row else False

    def _insert(self, conn: "psycopg.Connection[Any]", entity: str, values: dict[str, Any], field_types: dict[str, str | None]) -> int:
        table = sql.Identifier(entity)
        if not values:
            statement = sql.SQL("INSERT INTO {table} DEFAULT VALUES RETURNING {id}").format(table=table, id=sql.Identifier(_ID_COLUMN))
            params: list[Any] = []
        else:
            columns = sql.SQL(", ").join(sql.Identifier(key) for key in values)
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
            statement = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING {id}").format(table=table, columns=columns, placeholders=placeholders, id=sql.Identifier(_ID_COLUMN))
            params = [self._bind_value(v, field_types.get(k)) for k, v in values.items()]
        with conn.cursor() as cur:
            _run(cur, statement, params)
            row = cur.fetchone()
        return int(row[0])

    def _update(
        self,
        conn: "psycopg.Connection[Any]",
        entity: str,
        values: dict[str, Any],
        where_sql: sql.Composed | None,
        where_params: list[Any],
        field_types: dict[str, str | None],
        expected_revision: str | None,
    ) -> int:
        table = sql.Identifier(entity)
        if expected_revision is None and not values:
            # this branch is only reachable without a precondition -- `bind_mutation` already rejects an empty- `values` `update` carrying `expected_revision` outright, so a precondition is never silently discarded here.
            # history: CH-0047
            return self._count(conn, table, where_sql, where_params)
        full_where_sql, full_params = self._append_revision_predicate(where_sql, where_params, expected_revision, revision_column=_REVISION_COLUMN)
        revision_bump = sql.SQL("{col} = gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        if values:
            assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(key), ph=sql.Placeholder()) for key in values)
            set_clause = sql.SQL("{assignments}, {revision}").format(assignments=assignments, revision=revision_bump)
            value_params = [self._bind_value(v, field_types.get(k)) for k, v in values.items()]
        else:
            set_clause = revision_bump
            value_params = []
        statement = sql.SQL("UPDATE {table} SET {set} WHERE {where}").format(table=table, set=set_clause, where=full_where_sql)
        with conn.cursor() as cur:
            _run(cur, statement, value_params + full_params)
            affected = cur.rowcount
        if affected == 0 and expected_revision is not None:
            self._resolve_precondition_miss(conn, table, where_sql, where_params)
        return affected

    def _delete(self, conn: "psycopg.Connection[Any]", entity: str, where_sql: sql.Composed | None, where_params: list[Any], expected_revision: str | None) -> int:
        table = sql.Identifier(entity)
        full_where_sql, full_params = self._append_revision_predicate(where_sql, where_params, expected_revision, revision_column=_REVISION_COLUMN)
        statement = sql.SQL("DELETE FROM {table} WHERE {where}").format(table=table, where=full_where_sql)
        with conn.cursor() as cur:
            _run(cur, statement, full_params)
            affected = cur.rowcount
        if affected == 0 and expected_revision is not None:
            self._resolve_precondition_miss(conn, table, where_sql, where_params)
        return affected

    def _count(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        statement = sql.SQL("SELECT COUNT(*) FROM {table}").format(table=table)
        params: list[Any] = []
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            row = cur.fetchone()
            return row[0] if row else 0

    def _apply_upsert(self, conn: "psycopg.Connection[Any]", entity: str, bound: "BoundMutation", table_info: "_TableInfo", values_path: str) -> tuple[int, dict[str, Any] | None]:
        """R-5 / §0.5 Q-1 (adjudicated 案B). Mirrors `ApplicationCell.
        _apply_upsert`'s exact key-selection and error-precedence rules;
        the only difference is execution: two real SQL statements
        (`INSERT ... ON CONFLICT (<key>) DO NOTHING RETURNING id`, then --
        only if that inserted nothing -- `UPDATE ... WHERE <key eq>`)
        instead of an in-memory existence check, per corrigendum M-4 (never
        relying on `xmax`-based "was this an insert or update" tricks).
        """
        field_types = table_info.columns
        declared = {name: info for name, info in table_info.indexes.items() if info["unique"]}
        if not declared:
            fail("CAPABILITY_UNSUPPORTED", "Upsert requires a declared domain uniqueness key.", details=violation("capability", field="operation"))
        if bound.unique_key is not None:
            if bound.unique_key not in declared:
                fail("NOT_FOUND", "No declared uniqueness key matches unique_key.", status=404)
            key_name = bound.unique_key
        elif len(declared) == 1:
            key_name = next(iter(declared))
        else:
            fail("VALIDATION_FAILED", "unique_key is required when an entity declares more than one uniqueness key.", details=violation("request_schema", field="unique_key"))
        if bound.where:
            fail("VALIDATION_FAILED", "Upsert does not accept a filter; its existence test is the entity's declared uniqueness key.", details=violation("unsupported_field", field="where"))
        key_fields: tuple[str, ...] = declared[key_name]["fields"]
        for key_field in key_fields:
            if bound.values.get(key_field) is None:
                fail("VALIDATION_FAILED", "Upsert values must include every uniqueness key field.", details=violation("request_schema", field="values/" + key_field))
        # Contract 1.7.0: this entity's own declared constraints, same source `_apply` above reads.
        # history: CH-0091
        entity_constraints = table_info.constraints
        # type-check before any SQL runs, symmetric with insert/update above.
        # history: CH-0048
        for key, value in bound.values.items():
            _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))

        table = sql.Identifier(entity)
        key_where_sql = sql.SQL(" AND ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(f), ph=sql.Placeholder()) for f in key_fields)
        key_where_params = [self._bind_value(bound.values[f], field_types.get(f)) for f in key_fields]
        update_values = {k: v for k, v in bound.values.items() if k not in key_fields}

        # Contract 1.7.0 (D-2 (3)(ii), contract text: "An upsert that
        # resolves to an insert is refused on the same rule [as insert];
        # an upsert that resolves to an update is not"). Unlike `_apply`'s plain `insert` branch, this backend cannot know ahead of the two real SQL statements below whether THIS upsert will resolve to an insert or an update (corrigendum M-4: no separate existence check drives that choice) -- so the missing-field question is only even asked (one extra, targeted `SELECT ... LIMIT 1`, skipped entirely when every non-nullable field IS present, the common case) when it can actually change the outcome: a precondition (`expected_revision`) already guarantees this upsert can never resolve to an insert (`_apply_upsert`'s own docstring), so this check does not apply there at all.
        # history: CH-0049
        if bound.expected_revision is None:
            missing_non_nullable = sorted({name for name, c in entity_constraints.items() if not c.nullable} - set(bound.values))
            if missing_non_nullable:
                # `FOR UPDATE` locks the row this existence check found, inside this same transaction, for the rest of it -- without this, a concurrent session could DELETE this exact row and commit between this `SELECT` (finds it, "resolves to update") and the `INSERT ... ON CONFLICT DO NOTHING` below, letting that INSERT actually insert (the key is free again) -- a row missing a `nullable: false` field, never caught, because this check already concluded "resolves to update, skip it". Locking the row means the
                # concurrent DELETE blocks until this transaction commits
                # or rolls back, so the row this SELECT saw is still there
                # (or the whole transaction serializes behind it) when the
                # INSERT/UPDATE below actually run -- the missing-field
                # verdict this check reaches can no longer go stale.
                # history: CH-0050
                with conn.cursor() as cur:
                    _run(cur, sql.SQL("SELECT 1 FROM {table} WHERE {where} LIMIT 1 FOR UPDATE").format(table=table, where=key_where_sql), key_where_params)
                    resolves_to_update = cur.fetchone() is not None
                if not resolves_to_update:
                    missing_field = missing_non_nullable[0]
                    fail(
                        "VALIDATION_FAILED",
                        "A field declared nullable: false requires a value on an upsert that resolves to an insert.",
                        details={"field": values_path + missing_field, "violated_declaration": "nullable", "declared_type": _declared_type_label(field_types.get(missing_field)), "observed_type": "absent"},
                    )
        revision_bump = sql.SQL("{col} = gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        if update_values:
            assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(k), ph=sql.Placeholder()) for k in update_values)
            set_clause = sql.SQL("{a}, {r}").format(a=assignments, r=revision_bump)
            update_value_params = [self._bind_value(v, field_types.get(k)) for k, v in update_values.items()]
        else:
            set_clause = revision_bump
            update_value_params = []

        if bound.expected_revision is not None:
            # a precondition never resolves an upsert to an insert -- no key match is NOT_FOUND (via `_resolve_precondition_miss`), exactly like update/delete.
            # history: CH-0051
            full_where_sql, full_params = self._append_revision_predicate(key_where_sql, key_where_params, bound.expected_revision, revision_column=_REVISION_COLUMN)
            statement = sql.SQL("UPDATE {table} SET {set} WHERE {where}").format(table=table, set=set_clause, where=full_where_sql)
            with conn.cursor() as cur:
                _run(cur, statement, update_value_params + full_params)
                affected = cur.rowcount
            if affected == 0:
                self._resolve_precondition_miss(conn, table, key_where_sql, key_where_params)
            return 1, None

        columns = sql.SQL(", ").join(sql.Identifier(k) for k in bound.values)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in bound.values)
        conflict_columns = sql.SQL(", ").join(sql.Identifier(f) for f in key_fields)
        insert_statement = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({phs}) ON CONFLICT ({conflict}) DO NOTHING RETURNING {id}").format(
            table=table, cols=columns, phs=placeholders, conflict=conflict_columns, id=sql.Identifier(_ID_COLUMN)
        )
        insert_params = [self._bind_value(v, field_types.get(k)) for k, v in bound.values.items()]
        with conn.cursor() as cur:
            _run(cur, insert_statement, insert_params)
            row = cur.fetchone()
        if row is not None:
            return 1, {"address": {"id": int(row[0])}}

        update_statement = sql.SQL("UPDATE {table} SET {set} WHERE {where} RETURNING {id}").format(table=table, set=set_clause, where=key_where_sql, id=sql.Identifier(_ID_COLUMN))
        with conn.cursor() as cur:
            _run(cur, update_statement, update_value_params + key_where_params)
            row = cur.fetchone()
        if row is None:
            # the row this INSERT's ON CONFLICT saw was removed by a concurrent transaction before this UPDATE could find it -- neither statement resolved, so the whole batch rolls back as a concurrent-modification conflict rather than silently inserting a second time.
            # history: CH-0052
            fail("CONFLICT", "The row was concurrently modified.", status=409)
        return 1, None

    # ---- predicate/WHERE composition ------------------------------------

    _where_clause = staticmethod(_where_clause)
    _text_expression = staticmethod(_text_expression)
    _predicate_sql = staticmethod(_predicate_sql)

    # ---- schema ----------------------------------------------------------

    def apply_schema(
        self,
        operation: dict[str, Any],
        *,
        developer: bool,
        limits: ResourceLimits,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> "SchemaOutcome":
        """`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): identical single tx-exit-point discipline to `transact` above -- the exit point sits right before `_bump_revision`/the pre-commit hook, inside the SAME `with conn.transaction():` block every operation branch already writes its (uncommitted) DDL/registry changes in. A `dry_run` forces a real ROLLBACK via `psycopg.
        Rollback` (caught and swallowed by `conn.transaction()`'s own
        `__exit__`, never surfacing as an error) rather than committing --
        `outcome_*` locals below carry the decided result out of that
        block, since a raise cannot itself return a value. Always returns `SchemaOutcome` (review round F-8; mirrors `ApplicationCell.apply_schema`'s identical unification) -- this method's own direct callers (`tests/test_constraints_declaration.py`'s many `cell.apply_schema(...)` call sites among them) read `.revision` off the result.

        History: CH-0058
        """
        bound = bind_schema_operation(operation, developer=developer)
        # see `transact`'s identical `hook_fired` comment -- `True` only once the durable pre-commit row has already committed on its own connection, which is what lets the `except psycopg.Error` clause below tell a post-hook data-commit failure apart from every other failure.
        # history: CH-0090
        hook_fired = False
        # Contract 1.7.0: the tx-exit-point's own decided outcome, set inside `with conn.transaction():` below (a `dry_run`'s own `return` cannot come from inside that block -- normal exit COMMITS -- so `psycopg.Rollback` is raised instead, and these locals carry the already-decided result past it).
        # history: CH-0059
        outcome_committed = True
        outcome_revision: int | None = None
        outcome_descriptor: dict[str, Any] | None = None
        outcome_plan: str | None = None
        idempotency_digest_value: str | None = None
        with self._developer.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    # Contract 1.7.0 (D-5 (8)/(9), addendum 2 S-b, ruling
                    # I-3, WP-2c): the idempotency lookup -- as early as
                    # possible after loading the catalog, before ANY
                    # operation-specific accounting or target-dependent
                    # computation (including the `schema_objects`
                    # projection below, which for `drop_entity`/`add_
                    # field`/etc. reads `catalog.get(bound.entity)`'s
                    # CURRENT state -- reading it for an entity a replay's
                    # own key already dropped would compute nonsense, not
                    # merely skip a check the design allows skipping; see
                    # `ApplicationCell.apply_schema`'s identical comment).
                    # `dry_run` never consults/writes a record (ruling).
                    # history: CH-0060
                    if idempotency_key is not None and not dry_run:
                        assert plan_request is not None  # service.py always builds this
                        idempotency_digest_value = idempotency_digest(plan_request)
                        # see `transact`'s identical comment -- taken in THIS outer transaction, before `_idempotency_lookup`'s own nested savepoint.
                        # history: CH-0061
                        self._idempotency_key_lock(conn, idempotency_key)
                        record = self._idempotency_lookup(conn, idempotency_key)
                        # a record with no `request_id` (pre-1.7.0) is not a usable replay source -- treated as absent, checked before the digest comparison.
                        # history: CH-0062
                        if record is not None and _idempotency_record_has_request_id(record[2]):
                            stored_digest, _stored_kind, stored_payload = record
                            if stored_digest != idempotency_digest_value:
                                fail(
                                    "CONFLICT", "This idempotency key was already used with a different request.", status=409,
                                    details={"violated_declaration": "idempotency_key", "field": "idempotency_key"},
                                )
                            # applies to schema operations too -- a resent `drop_entity` answers from the record even though the entity, and any confirmation phrase computed against it, are both long gone.
                            # history: CH-0063
                            return SchemaOutcome(
                                committed=True, revision=stored_payload["revision"], descriptor=None, plan=None, replayed=True,
                                # the ORIGINAL execution's own `request_id` (guaranteed present), no fallback to this resend's own.
                                # history: CH-0064
                                request_id=stored_payload["request_id"],
                            )
                        # capacity checked before this request executes anything. table-level count lock, same outer-transaction placement as `transact` above.
                        # history: CH-0065
                        self._idempotency_reserve_lock(conn)
                        self._idempotency_reserve(conn, limits)
                    # Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a/S-j, WP-2b): read ONCE, before any DDL/registry write this transaction is about to (tentatively) make -- "the revision as it stood when the request was decided", the SAME value a dry run's own `revision` reports (S-j) and a real apply's `plan` verification is checked against. read only when actually needed -- `dry_run` always needs it for `outcome_revision` below (S-j), and a caller-presented `plan` needs it to verify; an ordinary apply (neither) needs neither, and skips this extra round trip entirely (`plan_request` is otherwise built unconditionally by `service.py`, so gating on `plan_request is not None` alone would not have helped).
                    # history: CH-0066
                    revision_before = self._read_schema_revision(conn) if dry_run or plan is not None else None
                    expected_plan = (
                        compute_plan_token(plan_request, revision_before)
                        if plan_request is not None and revision_before is not None
                        else None
                    )
                    # Object accounting mirrors `ApplicationCell.apply_
                    # schema` exactly (R-5: an index is a real resource and
                    # counts toward `schema_objects` too, SI-08): one object
                    # per entity table plus one per declared field
                    # (`id` included, `_r2db_revision` never counted, same
                    # as `ApplicationCell.schema`'s own dict), plus one per
                    # index (unique or not).
                    current_objects = sum(len(info.columns) + 1 for info in catalog.values()) + sum(len(info.indexes) for info in catalog.values())
                    if bound.operation == "create_entity":
                        projected = current_objects + 1 + 1 + len(bound.fields)  # entity + id + declared fields
                    elif bound.operation == "add_field":
                        projected = current_objects + 1
                    elif bound.operation == "drop_entity":
                        info = catalog.get(bound.entity)
                        columns_len = len(info.columns) if info is not None else 0
                        indexes_len = len(info.indexes) if info is not None else 0
                        projected = current_objects - (columns_len + 1) - indexes_len
                    elif bound.operation == "create_index":
                        projected = current_objects + 1
                    elif bound.operation == "alter_field":
                        # Contract 1.7.0 (D-2 (7), U-1 = (β), WP-2a):
                        # redeclares an EXISTING field -- no new entity/
                        # field/index, so `schema_objects` never moves
                        # (`enum_members` is checked separately below, once
                        # the field's real declared type is known).
                        projected = current_objects
                    else:  # drop_index
                        projected = current_objects - 1
                    limits.check("schema_objects", projected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    if bound.operation == "create_entity":
                        # defense-in-depth -- `bind_schema_operation` above already rejects this exact name (structured.py's own `_reject_reserved_entity_name`, the real, load-bearing check for BOTH cell implementations), but this backend's own physical-DDL layer re-checks it directly too, mirroring MitateDB's per-backend `check_reserved` redundancy rather than relying solely on the shared caller never being bypassed.
                        # history: CH-0067
                        _reject_reserved_entity_name(bound.entity, field="entity")
                        if bound.entity in catalog:
                            fail("CONFLICT", "Entity already exists.", status=409)
                        # Contract 1.7.0 (D-2 (1)/(7), WP-2a): `enum_
                        # members` is checked BEFORE `_create_entity`
                        # issues any DDL below (limits.enum_members's own
                        # text: "before anything is created or altered")
                        # -- a `fail()` here would in any case roll back
                        # the whole `with conn.transaction():` block, but
                        # checking first avoids issuing DDL only to
                        # discard it, and matches the in-memory backend's
                        # identical ordering (`ApplicationCell.apply_
                        # schema`).
                        for field_constraints_spec in bound.field_constraints.values():
                            if field_constraints_spec.enum is not None:
                                limits.check("enum_members", len(field_constraints_spec.enum))
                        self._create_entity(conn, bound.entity, bound.fields, bound.field_types)
                        # Only fields the request itself gave a `field_
                        # constraints` spec ever touch the registry (D-2
                        # (1): "省略 = 制約なし").
                        for field_name, field_constraints_spec in bound.field_constraints.items():
                            if field_constraints_spec.is_declared:
                                self._write_field_constraints(conn, bound.entity, field_name, field_constraints_spec)
                    elif bound.operation == "drop_entity":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        require_destructive_confirmation(
                            bound.destructive, bound.confirmation,
                            drop_entity_confirmation_phrase(bound.entity, self._read_schema_revision(conn)),
                            "Drop requires explicit destructive confirmation.",
                            consequence="The entity and all of its rows and indexes are permanently destroyed; re-creating an entity of the same name creates a new entity, not a restore.",
                            reversible_alternative=None,
                            recovery=None,
                        )
                        self._drop_entity(conn, bound.entity)
                        # Contract 1.7.0: the registry is scoped to the entity's own lifetime, symmetric with `ApplicationCell.apply_schema`'s identical `field_constraints.pop` -- a later `create_entity` of the same name must never inherit a dropped entity's own constraints. this cleanup runs ONLY when the side table itself exists -- an application that has never run upgrade `10` has no such table at all, and `drop_entity` (an operation wholly unrelated to whether that table exists) must still succeed for it, exactly like every other schema/data operation that never touches `field_constraints`.
                        # history: CH-0068
                        self._clear_field_constraints(conn, bound.entity)
                    elif bound.operation == "add_field":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        if bound.field in catalog[bound.entity].columns:
                            fail("CONFLICT", "Field already exists.", status=409)
                        # Contract 1.7.0 (D-2 (1)/(7), WP-2a): `add_field`'s
                        # own single-field declaration, mirroring `create_
                        # entity`'s enum_members check above -- checked
                        # BEFORE the mutation just below (`bound.
                        # constraints` is `None` when the request never
                        # carried `enum`/`nullable` at all).
                        if bound.constraints is not None and bound.constraints.enum is not None:
                            limits.check("enum_members", len(bound.constraints.enum))
                        # "An add_field declaring nullable: false on an entity that already holds rows is refused with CONFLICT on the same rule" -- the SAME tx + lock `alter_field`'s own existing-row scan uses below: `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` before the existence check, so a concurrent INSERT cannot slip a row in between this check and the DDL/registry write below.
                        #
                        # plain `SHARE MODE` does not conflict with itself, so two concurrent `add_field`/`alter_field` calls on the SAME entity could both acquire it, then each block at its own later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on the other's SHARE lock -- a guaranteed mutual wait, broken only by PostgreSQL's deadlock detector aborting one side with an error instead of the two calls simply serializing. `SHARE ROW EXCLUSIVE` conflicts with
                        # itself, so the second caller instead waits here,
                        # at LOCK TABLE, and proceeds only once the first
                        # transaction commits or rolls back -- it still
                        # excludes concurrent row writers (ROW EXCLUSIVE)
                        # exactly as plain SHARE did, so the R-2 existing-
                        # row-scan property above is unchanged.
                        # history: CH-0069
                        if bound.constraints is not None and not bound.constraints.nullable:
                            add_field_table_ident = sql.Identifier(bound.entity)
                            with conn.cursor() as cur:
                                _run(cur, sql.SQL("LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE").format(table=add_field_table_ident))
                            with conn.cursor() as cur:
                                _run(cur, sql.SQL("SELECT 1 FROM {table} LIMIT 1").format(table=add_field_table_ident))
                                if cur.fetchone() is not None:
                                    fail(
                                        "CONFLICT",
                                        "Existing rows would hold null in a field declared nullable: false.",
                                        status=409,
                                        details={"field": bound.field, "violated_declaration": "nullable"},
                                    )
                        self._add_field(conn, bound.entity, bound.field, bound.field_type)
                        if bound.constraints is not None and bound.constraints.is_declared:
                            self._write_field_constraints(conn, bound.entity, bound.field, bound.constraints)
                    elif bound.operation == "alter_field":
                        # Contract 1.7.0 (D-2 (5)/(6), WP-2a): "redeclares
                        # the constraints of one existing field" -- `field_
                        # type` redeclaration is already rejected at bind
                        # time (`bind_schema_operation`).
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        table_info = catalog[bound.entity]
                        if bound.field not in table_info.columns:
                            fail("NOT_FOUND", "Field was not found.", status=404)
                        declared_type = table_info.columns[bound.field]
                        patch = bound.constraint_patch
                        assert patch is not None  # bind_schema_operation always sets this for alter_field
                        # compose the request's PATCH against the field's EXISTING declared constraints -- only known here (`table_info.constraints`, never at bind time, addendum R-b/R-c, D-2 (3)). `enum`/`nullable` omitted each
                        # LEAVE the existing value as it is; `enum: null`
                        # CLEARS it; an explicit list is fully validated
                        # against the field's real declared type now.
                        # history: CH-0070
                        existing_constraints = table_info.constraints.get(bound.field, FieldConstraints())
                        new_nullable = existing_constraints.nullable if patch.nullable_omitted else patch.nullable
                        if patch.enum_clear:
                            new_enum: tuple[Any, ...] | None = None
                        elif patch.enum_omitted:
                            new_enum = existing_constraints.enum
                        else:
                            try:
                                new_enum = validate_enum_declaration(list(patch.enum_raw), declared_type)
                            except _ConstraintDeclarationError as exc:
                                _fail_constraint_declaration("enum", declared_type, exc)
                            limits.check("enum_members", len(new_enum))
                        new_constraints = FieldConstraints(enum=new_enum, nullable=new_nullable)
                        # Contract 1.7.0: every existing row is checked against the constraints this operation would establish, INSIDE this same `with conn.transaction():` block, before anything commits -- one violating row refuses the WHOLE operation with CONFLICT via `fail()`, which unwinds this entire transaction (nothing has been written yet at this point, so there is nothing to roll back beyond PostgreSQL's own transactional DDL/DML).
                        # Two separate, targeted queries (never a combined
                        # OR) so the CONFLICT can name exactly which
                        # declaration a violating row breaks, without ever
                        # naming the row itself or how many there are
                        # (SI-10, contract text).
                        # history: CH-0089
                        table_ident = sql.Identifier(bound.entity)
                        field_ident = sql.Identifier(bound.field)
                        # lock the entity's own table (SHARE ROW EXCLUSIVE -- blocks concurrent writers, never concurrent readers) BEFORE the scan below, inside this SAME transaction. Without this, READ COMMITTED lets another session INSERT/UPDATE a row that violates the new constraints, commit it AFTER this scan sees zero violations but BEFORE this transaction's own `_write_field_constraints` commits -- `alter_field` would then succeed while a violating row already exists, making the catalog's own declaration false the instant it is published. A table-level lock (not a row lock) because the scan below reads the WHOLE table, not a single identified row (contrast the upsert TOCTOU fix below, which locks one row).
                        #
                        # the original fix used plain `SHARE MODE`, which does not conflict with itself -- two concurrent `alter_field`/`add_field` calls on the SAME entity could both acquire it here, then each block at its own later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on the other's SHARE lock, a guaranteed mutual wait broken only by PostgreSQL's deadlock detector aborting one side with an error rather than the two calls simply serializing. `SHARE ROW
                        # EXCLUSIVE` conflicts with itself, so the second
                        # caller instead waits here, at LOCK TABLE, and
                        # proceeds only once the first transaction commits
                        # or rolls back -- it still excludes concurrent row
                        # writers (ROW EXCLUSIVE) exactly as plain SHARE
                        # did, so the R-2 existing-row-scan property above
                        # is unchanged.
                        # history: CH-0071
                        with conn.cursor() as cur:
                            _run(cur, sql.SQL("LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE").format(table=table_ident))
                        if not new_constraints.nullable:
                            with conn.cursor() as cur:
                                _run(cur, sql.SQL("SELECT 1 FROM {table} WHERE {f} IS NULL LIMIT 1").format(table=table_ident, f=field_ident))
                                if cur.fetchone() is not None:
                                    fail("CONFLICT", "Existing rows violate the constraints this alter_field would establish.", status=409, details={"field": bound.field, "violated_declaration": "nullable"})
                        if new_constraints.enum is not None:
                            # `_bind_value` (never a bare member) so this
                            # binds correctly for `declared_type`'s real
                            # typed column -- ruling B-1 means `declared_
                            # type` is always one of the 4 scalar words
                            # here (`validate_enum_declaration`'s own
                            # `_ENUM_ELIGIBLE_TYPES` gate already refused
                            # `enum` on any untyped/object/array field at
                            # declaration time), so this is never an
                            # unwrapped bind against a `jsonb` column.
                            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in new_constraints.enum)
                            statement = sql.SQL("SELECT 1 FROM {table} WHERE {f} IS NOT NULL AND {f} NOT IN ({items}) LIMIT 1").format(table=table_ident, f=field_ident, items=placeholders)
                            enum_params = [self._bind_value(member, declared_type) for member in new_constraints.enum]
                            with conn.cursor() as cur:
                                _run(cur, statement, enum_params)
                                if cur.fetchone() is not None:
                                    fail("CONFLICT", "Existing rows violate the constraints this alter_field would establish.", status=409, details={"field": bound.field, "violated_declaration": "enum"})
                        self._write_field_constraints(conn, bound.entity, bound.field, new_constraints)
                    elif bound.operation == "create_index":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        table_info = catalog[bound.entity]
                        for index_field in bound.index_fields:
                            if index_field not in table_info.columns:
                                fail("NOT_FOUND", "Field was not found.", status=404)
                        if bound.index in table_info.indexes:
                            fail("CONFLICT", "Index already exists.", status=409)
                        self._create_index(conn, bound.entity, bound.index, bound.index_fields, bound.unique)
                    else:  # drop_index
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        table_info = catalog[bound.entity]
                        if bound.index not in table_info.indexes:
                            fail("NOT_FOUND", "Index was not found.", status=404)
                        # dropping a unique index removes a guardrail and can silently re-enable upsert -- SI-09 destructive confirmation applies exactly like drop_entity.
                        # history: CH-0072
                        require_destructive_confirmation(
                            bound.destructive, bound.confirmation,
                            drop_index_confirmation_phrase(bound.entity, bound.index, self._read_schema_revision(conn)),
                            "Dropping an index requires explicit destructive confirmation.",
                            consequence="The index is destroyed; query semantics are unaffected, only performance (and any uniqueness guarantee it enforced) are lost.",
                            reversible_alternative=None,
                            recovery="create_index with the same definition restores it -- an index carries no data of its own, so this fully restores a non-unique index; recreating a UNIQUE index re-validates existing rows against that uniqueness and can instead fail with CONFLICT if data written after the drop now violates it.",
                        )
                        self._drop_index(conn, table_info.indexes[bound.index]["physical"])
                    # Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single
                    # tx-exit point -- plan validity, then commit vs
                    # rollback (dry_run) vs real commit -- right before
                    # `_bump_revision`/the pre-commit hook. Reached only
                    # once the operation branch above has already
                    # tentatively written its DDL/registry changes (a
                    # `require_destructive_confirmation` failure inside
                    # the `drop_entity`/`drop_index` branches above
                    # already raised, before this point is ever reached
                    # for it -- D-4 (2)'s own ordering, and why an
                    # unconfirmed `drop_entity` carrying a stale `plan` is
                    # refused DESTRUCTIVE_CONFIRMATION_REQUIRED, never
                    # PRECONDITION_FAILED).
                    if plan is not None and plan != expected_plan:
                        fail(
                            "PRECONDITION_FAILED", "The plan no longer matches this request or the Application's schema.",
                            status=412, details={"violated_declaration": "plan"},
                        )
                    if dry_run:
                        # `descriptor` is the target entity's own descriptor as it would read afterwards -- built from a FRESH `_load_catalog` re-read inside this SAME (still open, uncommitted) transaction, which sees this operation's own tentative writes; `None` for a dry-run `drop_entity` (the entity no longer appears in that re-read). `revision`
                        # (S-j) is `revision_before`, never a bumped value
                        # -- `_bump_revision` below is never reached here.
                        # history: CH-0073
                        catalog_after = self._load_catalog(conn)
                        outcome_descriptor = self._describe_table(bound.entity, catalog_after[bound.entity]) if bound.entity in catalog_after else None
                        outcome_committed = False
                        outcome_revision = revision_before
                        outcome_plan = expected_plan
                        raise psycopg.Rollback()
                    outcome_revision = self._bump_revision(conn)
                    # unconditional -- every schema operation is fail-closed class. Last statement
                    # inside this `with conn.transaction():` block, same
                    # reasoning as `transact`'s identical comment.
                    # history: CH-0088
                    if audit_hook is not None:
                        audit_hook.pre_commit()
                        hook_fired = True
                    # Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c):
                    # recorded in the same `with conn.transaction():` block
                    # as the DDL/registry writes above -- see `transact`'s
                    # identical comment.
                    if idempotency_key is not None and idempotency_digest_value is not None:
                        self._idempotency_store(
                            conn, idempotency_key, digest=idempotency_digest_value, kind="schema",
                            payload={"revision": outcome_revision, "request_id": request_id},
                            retention_ms=limits.idempotency_retention_ms,
                        )
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.UniqueViolation as exc:
                # `create_index(unique=True)` against data that already violates the requested uniqueness.
                # history: CH-0074
                self._fail_unique_conflict(bound.entity, exc)
            except psycopg.errors.DataError:
                self._fail_client_value()
            except psycopg.Error:
                # see `transact`'s identical comment.
                # history: CH-0087
                if hook_fired and audit_hook is not None:
                    audit_hook.commit_failed()
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # always `SchemaOutcome`, dry_run/plan or neither (mirrors `ApplicationCell.apply_schema`'s identical unification) -- every pre-1.7.0 direct caller of this method (`tests/test_constraints_declaration.py`'s many `cell.apply_schema(...)` call sites among them) now reads `.revision` off the result instead of comparing the result itself to an `int`.
        # history: CH-0075
        return SchemaOutcome(committed=outcome_committed, revision=outcome_revision, descriptor=outcome_descriptor, plan=outcome_plan, request_id=request_id)

    def _create_entity(self, conn: "psycopg.Connection[Any]", entity: str, fields: tuple[str, ...], field_types: dict[str, str | None] | None = None) -> None:
        # every entity table gets a server-assigned `id` address (`GENERATED ALWAYS AS IDENTITY`, so the sequence is never rewound by any statement reachable through this public API -- see R-1's "採番識別子の非推論条項"/property-5 note) and an invisible, per-row `_r2db_revision` (PostgreSQL 13+'s built-in `gen_random_uuid()`), ahead of the caller's own declared fields.
        # `"id"`/`"_r2db_revision"` are hardcoded server literals here,
        # never client input, so composing them as fixed SQL text (rather
        # than through `sql.Identifier`) does not reopen the
        # identifier-injection surface D-4 closes for client-supplied names.
        #
        # Phase 6 WP-2 (design D-3, r2db decision (c)): a field named in
        # `field_types` gets that declared type's real PostgreSQL column
        # type (the same `_FIELD_TYPE_SQL` mapping `_add_field` below
        # already uses); every other field keeps the pre-WP-2 default,
        # JSONB (`field_types` defaults to `None`/empty, so an ordinary
        # 1.5.0-shaped `create_entity` -- `fields` only, no `field_types` --
        # creates every column JSONB, unchanged).
        # history: CH-0076
        field_types = field_types or {}
        id_column = sql.SQL("id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
        revision_column = sql.SQL("{col} uuid NOT NULL DEFAULT gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        declared_columns = [
            sql.SQL("{col} {type}").format(col=sql.Identifier(f), type=_column_type_sql(field_types.get(f)))
            for f in fields
        ]
        all_columns = sql.SQL(", ").join([id_column, revision_column] + declared_columns)
        statement = sql.SQL("CREATE TABLE {table} ({columns})").format(table=sql.Identifier(entity), columns=all_columns)
        with conn.cursor() as cur:
            _run(cur, statement)
            self._apply_row_level_security(cur, entity)
            # §8.5 condition 3(b): do not depend on remembering that the
            # line above ran correctly. Re-derive, from live catalog state
            # in the same transaction, whether *every* table in this
            # application's database (not just the one just created) has
            # RLS enabled and forced -- and refuse to let this CREATE TABLE
            # commit if not. This is what makes RLS coverage a checked
            # invariant rather than a convention: a future bug in
            # `_apply_row_level_security`, or a table created by some other
            # code path entirely, is caught here, before commit, not
            # discovered later by an operator. See
            # `verify_row_level_security` below for the same check exposed
            # standalone (used by `r2db-api/tests/test_postgres.py` and
            # available for an operator/health-check to call at any time,
            # independent of a schema change happening at all).
            offenders = self._rls_offenders(cur)
            if offenders:
                fail(
                    "SERVICE_UNAVAILABLE",
                    "Row level security is not enabled and forced on every table in this application's database.",
                    status=503,
                    details={"tables": offenders},
                )

    def _apply_row_level_security(self, cur: "psycopg.Cursor[Any]", entity: str) -> None:
        """RLS as defence-in-depth underneath the database boundary and the two distinct DB roles (architecture §8, "D-3 改訂": each application now owns its own PostgreSQL database, not merely its own schema inside one shared database -- the database boundary is the primary wall, since PostgreSQL admits no cross-database query path at all without FDW/dblink, which this deployment never grants). This policy's job is to survive a
        *future* misconfiguration of that primary wall -- e.g. an
        accidental broader `CONNECT` grant -- rather than to be the
        primary control itself. It restricts every row in every table this
        cell creates to being visible/writable only by this application's
        own two roles, checked by PostgreSQL itself via `current_user`, not
        by anything this Python process asserts about itself.

        History: CH-0077
        """
        table = sql.Identifier(entity)
        _run(cur, sql.SQL("ALTER TABLE {table} ENABLE ROW LEVEL SECURITY").format(table=table))
        _run(cur, sql.SQL("ALTER TABLE {table} FORCE ROW LEVEL SECURITY").format(table=table))
        policy = sql.Identifier(f"{entity}_application_isolation")
        _run(
            cur,
            sql.SQL("CREATE POLICY {policy} ON {table} USING (current_user IN ({runtime}, {developer})) WITH CHECK (current_user IN ({runtime}, {developer}))").format(
                policy=policy,
                table=table,
                runtime=sql.Literal(self._runtime_role),
                developer=sql.Literal(self._developer_role),
            ),
        )

    def _rls_offenders(self, cur: "psycopg.Cursor[Any]") -> list[str]:
        """The live list of base tables in this application's database
        (current schema, i.e. `public`) that do NOT have both `ENABLE ROW
        LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` set right now,
        according to PostgreSQL's own catalog -- never this Python
        process's memory of what it thinks it did. Every backend
        bookkeeping table (`_BOOKKEEPING_TABLES`: `_r2db_schema_revision`,
        already RLS-protected, and -- Q4 WP-3 -- the per-application
        platform-upgrade ledger, which deliberately carries no RLS at all,
        design D-3(a)) is excluded the same way `_load_catalog` excludes
        them from the application-visible catalog. Ordered so callers get
        a deterministic offender list.
        """
        statement = sql.SQL(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r' AND c.relname <> ALL({bookkeeping_tables}) "
            "AND (c.relrowsecurity = false OR c.relforcerowsecurity = false) "
            "ORDER BY c.relname"
        ).format(bookkeeping_tables=sql.Placeholder())
        _run(cur, statement, [list(_BOOKKEEPING_TABLES)])
        return [row[0] for row in cur.fetchall()]

    def verify_row_level_security(self) -> None:
        """Standalone form of the same check `_create_entity` runs inline
        after every `CREATE TABLE` (§8.5 condition 3(b)): confirms every
        base table in this application's database has RLS both enabled and
        forced, independent of any schema change happening right now.
        Callable at any time -- by a test, or by an operator/health-check
        script -- as a live verification against real catalog state, not a
        cached or point-in-time claim. Raises `FoundationError` naming the
        offending tables if any are found; does nothing (no return value)
        if the database is clean.

        `migrations/0003_provision_application.sql` additionally installs
        an always-available SQL-level equivalent of this same query,
        `public._r2db_missing_rls`, directly inside every application's own
        database, so this property can also be checked with `psql` (or any
        other client) without going through `PostgresCell`/Python at all.
        """
        with self._developer.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    offenders = self._rls_offenders(cur)
        if offenders:
            fail(
                "SERVICE_UNAVAILABLE",
                "Row level security is not enabled and forced on every table in this application's database.",
                status=503,
                details={"tables": offenders},
            )

    def _drop_entity(self, conn: "psycopg.Connection[Any]", entity: str) -> None:
        statement = sql.SQL("DROP TABLE {table}").format(table=sql.Identifier(entity))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _add_field(self, conn: "psycopg.Connection[Any]", entity: str, field: str, field_type: str | None) -> None:
        # `field_type` maps to a real typed column; omitted keeps the pre-CCR-13 default, JSONB.
        # history: CH-0078
        statement = sql.SQL("ALTER TABLE {table} ADD COLUMN {col} {type}").format(table=sql.Identifier(entity), col=sql.Identifier(field), type=_column_type_sql(field_type))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _create_index(self, conn: "psycopg.Connection[Any]", entity: str, index_name: str, fields: tuple[str, ...], unique: bool) -> None:
        # the physical index name is `{entity}__{index}` -- `bind_schema_operation` has already rejected any client index name containing `__` or whose composed length would exceed the identifier limit, so this composition is unambiguous to invert (`_load_catalog` does exactly that). `entity`/`index_name` are
        # plain Python strings built from already-validated identifiers;
        # `sql.Identifier` below is what actually makes this safe to send
        # to PostgreSQL (it quotes/escapes the resulting name regardless of
        # content), not the string concatenation itself.
        # history: CH-0079
        physical_name = f"{entity}__{index_name}"
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        unique_keyword = sql.SQL("UNIQUE ") if unique else sql.SQL("")
        statement = sql.SQL("CREATE {unique}INDEX {name} ON {table} ({columns})").format(unique=unique_keyword, name=sql.Identifier(physical_name), table=sql.Identifier(entity), columns=columns)
        with conn.cursor() as cur:
            _run(cur, statement)

    def _drop_index(self, conn: "psycopg.Connection[Any]", physical_name: str) -> None:
        statement = sql.SQL("DROP INDEX {name}").format(name=sql.Identifier(physical_name))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _read_schema_revision(self, conn: "psycopg.Connection[Any]") -> int:
        """Read-only counterpart to `_bump_revision` below (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1 m-1): a plain `SELECT` of the current `schema_revision`, in the SAME transaction as the pending schema operation, used to compute a `drop_entity`/`drop_index` confirmation phrase's own state fingerprint before the destructive-confirmation gate runs (and therefore before this same transaction's own `_bump_revision` call increments it again).
        `migrations/0003_provision_application.sql` inserts this table's one
        row (`revision = 0`) at provisioning time, so the `SELECT` always
        finds it in practice; the `0` fallback below exists only so this
        method never raises on a row that -- against that expectation --
        turns out to be missing, mirroring `_bump_revision`'s own
        insert-if-missing defensiveness without itself writing anything.

        History: CH-0080
        """
        table = sql.Identifier(_REVISION_TABLE)
        select = sql.SQL("SELECT revision FROM {table}").format(table=table)
        with conn.cursor() as cur:
            _run(cur, select)
            row = cur.fetchone()
            return int(row[0]) if row is not None else 0

    def _bump_revision(self, conn: "psycopg.Connection[Any]") -> int:
        table = sql.Identifier(_REVISION_TABLE)
        update = sql.SQL("UPDATE {table} SET revision = revision + 1 RETURNING revision").format(table=table)
        with conn.cursor() as cur:
            _run(cur, update)
            row = cur.fetchone()
            if row is None:
                insert = sql.SQL("INSERT INTO {table} (id, revision) VALUES (TRUE, 1) RETURNING revision").format(table=table)
                _run(cur, insert)
                row = cur.fetchone()
            return int(row[0])

    # ---- session/timeout ---------------------------------------------------

    def _timeout_ms(self, limits: ResourceLimits, deadline: float | None, clock: "Callable[[], float] | None") -> int:
        budget_ms = limits.execution_ms
        if deadline is not None and clock is not None:
            remaining_ms = max(0.0, (deadline - clock()) * 1000)
            budget_ms = min(budget_ms, max(1, int(remaining_ms)))
        return max(1, int(budget_ms))

    def _set_timeouts(self, conn: "psycopg.Connection[Any]", timeout_ms: int) -> None:
        """One request = one transaction: `statement_timeout` and `lock_timeout` are set with `SET LOCAL`, so they apply only to the current transaction and are automatically discarded on commit or rollback -- never leaking onto the next transaction this pooled connection is reused for. The timeout value passed here is always a
        server-computed `int` (derived from `ResourceLimits.execution_ms`
        and the caller's deadline, never from request content), so
        `sql.Literal` -- necessary because PostgreSQL's `SET` grammar does
        not accept a bind placeholder in this position -- is composing a
        trusted value, not interpolating untrusted text.

        History: CH-0081
        """
        statement_timeout = sql.SQL("SET LOCAL statement_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        lock_timeout = sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        with conn.cursor() as cur:
            _run(cur, statement_timeout)
            _run(cur, lock_timeout)


class _RefusingPlatformUpgradeCell:
    """stands in for one served application's own `PostgresCell` when `main.py::build_app`'s own `_cell_factory` finds, at cell-open time, that this application's per-application platform-upgrade ledger is missing an entry `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` requires.

    Now `_cell_factory` catches that same `FoundationError` and registers
    one of these instead: this process still starts, every OTHER served
    application's `PostgresCell` opens and serves exactly as before, and
    ONLY this one application's cell -- carrying the identical
    `StorageBackend` face (`query`/`transact`/`apply_schema`/`catalog`,
    `r2db_api.backend.StorageBackend`, asserted below exactly like
    `PostgresCell` itself is) -- refuses every real request against it
    with the SAME F-12 message (design §3.8, verbatim, `SERVICE_
    UNAVAILABLE`, HTTP 503) `verify_platform_upgrades_applied` would have
    raised. The message is captured once, at cell-open time (a startup
    snapshot, matching D-1(e)/D-2(g)/U-3's own "起動時スナップショット"
    discipline for every other Q4 declared value) -- never re-derived per
    request.

    History: CH-0082
    """

    def __init__(self, application_id: str, message: str) -> None:
        self.application_id = application_id
        self._message = message

    def _refuse(self) -> None:
        fail("SERVICE_UNAVAILABLE", self._message, status=503)

    def close(self) -> None:
        """No pool/connection was ever opened for a refusing cell (the
        one-shot ledger check that discovered the pending upgrade already
        closed its own connection, `verify_platform_upgrades_applied`'s
        own `finally: conn.close()`) -- nothing to release here."""

    def query(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse()

    def transact(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse()

    def apply_schema(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse()

    def catalog(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse()


# Checked, not just claimed: `PostgresCell` must present the exact same call surface as `ApplicationCell`. See `backend.py` for the
# equivalent assertion covering `ApplicationCell`.
# history: CH-0083
assert issubclass(PostgresCell, _StorageBackend), "PostgresCell must conform to StorageBackend (design D-1)"
# the refusing cell registered in its place must present that same face too -- `DataService` (and every conformance/test caller) cannot tell the two apart at the type level.
# history: CH-0084
assert issubclass(_RefusingPlatformUpgradeCell, _StorageBackend), "_RefusingPlatformUpgradeCell must conform to StorageBackend (H-1(a))"

__all__ = ["PostgresCell", "SharedPoolManager", "default_pool_manager", "_RefusingPlatformUpgradeCell"]
