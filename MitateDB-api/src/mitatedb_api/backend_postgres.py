"""PostgreSQL storage backend (R-2/R-3).

R-2 choke point: values are always bound as psycopg parameters, never
string-interpolated into SQL text. Identifiers reach this module already
syntax-checked by the shared allowlist (``identifiers.validate_identifier``,
re-applied here defensively as this module's own first gate too -- cheap,
and keeps this file's own safety property self-contained rather than
depending entirely on the caller having done it) and, for every identifier
that names something ALREADY EXPECTED TO EXIST (a collection/field a
read/write/filter references), additionally checked against this
database's own live catalog by ``field_domains`` before it is ever used --
only *new* names (``create_collection``/``add_field``) skip that second
stage, for the obvious reason that a name being created cannot already be
in the catalog; PostgreSQL's own ``DuplicateTable``/``DuplicateColumn``
still catches a collision there. Every identifier is composed into a
statement exclusively via ``psycopg.sql.Identifier`` -- this module never
builds a statement by embedding a name into a plain Python string.

Execution itself is centralized in ``_execute``, the ONLY function in this
module allowed to call ``cursor.execute`` directly: it rejects (``TypeError``,
at runtime, not merely by convention) anything that is not already a
``psycopg.sql.SQL``/``psycopg.sql.Composed`` object -- a bare Python
``str`` in particular -- so no method anywhere in this file has a route to
execute raw, string-interpolated SQL even by future accident.

WP-1 independent review B-1 (blocker): a value whose Python-level SHAPE
was acceptable (`cell.ApplicationCell._normalize_value`'s own
str/int/float/bool/None/dict/list check) can still MISMATCH the declared
PostgreSQL column type it is bound against (e.g. a string bound to a
`BIGINT` column, or an out-of-range integer bound to one) -- PostgreSQL
then raises a driver-level error (`InvalidTextRepresentation`,
`NumericValueOutOfRange`, ...) that used to escape this module's own
`errors.FoundationError` boundary entirely, AND left the connection in
PostgreSQL's own aborted-transaction state (every subsequent statement on
that connection failing with `InFailedSqlTransaction` until an explicit
`ROLLBACK`) because only the narrower `UniqueViolation`/`UndefinedTable`
handlers called `rollback()`. Fixed with two independent layers, per the
review's own two-layer split:

(i) ``field_domains`` reports each column's own DOMAIN category (`"text"`/
`"int32"`/`"int64"`/`"float"`, derived from this backend's own `_TYPES`
mapping via a live `information_schema.columns.data_type` query -- the
SAME live-catalog query `field_domains` already performs for stage-2
identifier validation, now also answering "what domain does this column
accept" in the same round trip). `encode_value(value, domain=...)`
deterministically rejects a value outside its target column's domain
BEFORE any statement reaches the database -- the SQLite backend's own
`encode_value` ignores `domain` entirely (matching WP-1 P3 round 2
instruction #1's own precedent: SQLite's more permissive behavior for the
embedded-NUL case stays UNCHANGED here too; SQLite's column affinity is
dynamic, so there is no equivalent mismatch to detect there).

(ii) every DML/DDL method below now has a FINAL, catch-all
``except psycopg.Error`` (after any more specific handler) that always
calls the correct connection's own `rollback()` before re-raising a
classified `errors.ValidationError` -- so a genuinely unanticipated
PostgreSQL-level rejection (anything layer (i) did not already catch)
still (a) never leaves a connection aborted for the next call on the same
cell, and (b) never leaks a raw `psycopg.Error` past this module's own
boundary. This is a deliberately conservative, defensive backstop, not a
precise error classification -- by the time layer (i) is in place, this
branch should be effectively unreachable for realistic client input; it
exists only so an unanticipated case still fails safely (connection
recovers, caller gets a classified exception) rather than poisoning the
connection for every future call.

This is not a port of r2db-api's own ``postgres.py`` (R-2's closing
paragraph: "the peer implementations are never shared" -- two independent
implementations of the same safety property is what gives the common
conformance suite its own detection power). Notable, deliberate
differences from that peer's own design: no row
addressability (``row_addressability`` stays declared ``unavailable`` --
see ``insert_in_transaction``'s own comment for why its ``rowid`` return value uses
PostgreSQL's ``ctid`` rather than a stable published address), and no Row
Level Security (this foundation's primary isolation wall is
database-per-application, R-1 -- RLS as an additional layer is future-work,
design v1.1 §7, not this WP's own containment boundary).

Connections and requests: each application has one bounded pool per role
(runtime, developer). A request borrows what it needs once, at its start
(``request_scope``), runs as ONE transaction on its main connection and
returns the connections when it ends, rolling back whatever is
uncommitted -- so no two requests ever share a connection or a
transaction, and nothing one request set on a connection reaches the next.
Requests on the same application run concurrently; what PostgreSQL
serializes for them is named at each lock (``lock_schema``,
``lock_entities``, the two idempotency locks).
"""

import json
import threading
import time
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from .backend import SCOPE_KINDS, UNCHANGED, RequestScope
from .config import FoundationConfig
from .errors import (AuditSinkUnavailable, ConflictError, NotFoundError,
                     PlatformUpgradePending, ResourceLimitError,
                     StorageConfigurationError, StorageTransientError,
                     ValidationError, violation)
from .identifiers import validate_identifier
from .field_types import FOUNDATION_TYPE_TO_CONTRACT_TYPE as _FOUNDATION_TYPE_TO_CONTRACT_TYPE
from . import platform_upgrades
# The `pg_prepared_statements` probe
# `prepared_stats` (below) calls -- byte-identical to
# `r2db_api.psycopg_counting` (a same-named test in `tests/` pins the
# sha256 match; rework 指摘 3 moved the probe itself there so it is not
# duplicated per peer).
from .pool import DEFAULT_MAX_SIZE, BoundedConnectionPool, PoolConnectFailed, PoolExhausted
from .psycopg_counting import prepared_stats_skeleton, probe_prepared_statements
# `_INT_DOMAIN_RANGES`/`_check_domain` are re-exported for facade
# compatibility (design D-2); not referenced elsewhere in this module.
from .postgres_value_domain import _INT_DOMAIN_RANGES, _validate_value_domain, _check_domain
from .postgres_reserved_names import _RESERVED_EXACT, _RESERVED_PREFIX, _check_reserved_name
from .postgres_types import _TYPE_SQL, _DOMAIN_BY_DATA_TYPE, _TEXT_DOMAIN_BY_DECLARED_TYPE
from .postgres_sql import _DIRECTION_SQL, _NULLS_SQL, _keyset_predicate_sql, _where_sql


# Bookkeeping table name (provisioned by `migrations/0003_provision_
# application.sql`, mirroring r2db-api's own `_r2db_schema_revision`
# table -- an independently-designed table of the same SHAPE, not shared
# code, matching R-2's own "no code sharing between peers" principle
# applied here to the migrations set instead).
#
# m-1 (independent review correction): this table is NOT excluded from
# `field_domains`'s own visible catalog by any special-case filter in this
# module (unlike r2db-api's own `_r2db_schema_revision` exclusion, which
# IS filtered out of that peer's catalog view) -- an application-level
# `field_domains("_mdb_schema_revision")` call would in fact return its
# real columns if one were ever issued. The REAL defenses that keep it
# unreachable from application code are two independent, structural ones:
# (a) `identifiers._IDENTIFIER` requires a name to start with `[a-z]`, so
# the leading underscore alone makes `"_mdb_schema_revision"` fail the
# SHARED syntax allowlist before this module is ever consulted (`cell.py`'s
# own `_identifier` gate), and (b) even if that gate were bypassed, the
# runtime role this backend's own `_runtime` connection authenticates as
# has NO grant of any kind on this table (`migrations/0003_provision_
# application.sql` creates it BEFORE the `ALTER DEFAULT PRIVILEGES`
# statement runs, so that statement's future-tables grant never reaches
# it) -- `tests/test_postgres.py`'s own dedicated tests exercise both of
# these directly.
_SCHEMA_REVISION_TABLE = "_mdb_schema_revision"

# Phase 6 WP-3 (design D-3, §1.5 finding 2a): the declared-type registry
# itself -- provisioned by `migrations/0003_provision_application.sql`
# for a new application, retrofitted onto an existing one by
# `migrations/0006_declared_field_types_upgrade.sql`. Same access-pattern
# reasoning as `_SCHEMA_REVISION_TABLE` immediately above (developer-
# connection only; the runtime role gets no grant on it at all -- created
# before `ALTER DEFAULT PRIVILEGES` in both migrations).
_FIELD_TYPES_TABLE = "_mdb_field_types"

# Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(a)/(e)(i),
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
# WP-4 変更対象 C): the per-application platform-upgrade ledger -- same
# access-pattern reasoning as `_SCHEMA_REVISION_TABLE`/`_FIELD_TYPES_TABLE`
# above for EXCLUSION purposes (`schema_count`'s own accounting must never
# count this bookkeeping table towards `FoundationConfig.max_schema_
# objects`, design D-3(e)(i): "放置すると全 application の schema_objects
# 会計が +1 ずれる"), but UNLIKE those two, the runtime role DOES hold a
# grant on it (`SELECT` only, design D-3(a)/U-2) -- read directly by
# `platform_upgrades.require_application_upgrades_applied` below, over the
# runtime connection, at cell-open time.
_PLATFORM_UPGRADES_TABLE = platform_upgrades.LEDGER_TABLE_NAME

# Phase 9 WP-3c (design D-5, 追補 2 S-a; 監督裁定集約 rulings-r5-r6.md
# I-1): the per-application idempotency-record side table -- provisioned
# by `migrations/0003_provision_application.sql` for a new application,
# retrofitted onto an existing one by `migrations/0010_idempotency_
# records_upgrade.sql`. UNLIKE `_SCHEMA_REVISION_TABLE`/`_FIELD_TYPES_
# TABLE` (developer-connection only) and LIKE `_PLATFORM_UPGRADES_TABLE`
# (runtime holds a real grant), this table is written from BOTH
# connections: `ApplicationCell.transact`'s own batch path writes it over
# the request's runtime connection (the same connection the batch's own DML
# already runs on, so the record lands in the SAME transaction, I-1), while
# `create_collection`/`add_field`/`alter_field_constraints`'s own
# `idempotency_record` parameter writes it over the request's developer
# connection (the same connection their own DDL already runs on) -- created AFTER `ALTER DEFAULT
# PRIVILEGES FOR ROLE developer_role` in `0003` (and granted explicitly in
# `0010`, for an existing application whose ledger predates this table),
# so the runtime role holds full DML (`SELECT`/`INSERT`/`UPDATE`/
# `DELETE`), not the read-only `SELECT` `_PLATFORM_UPGRADES_TABLE` grants
# it.
_IDEMPOTENCY_TABLE = "_mdb_idempotency"

# Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): two-int
# `pg_advisory_xact_lock(namespace, hashtext(key))` namespace for the
# PER-KEY idempotency lock -- see `idempotency_begin` below.
#
# Code-review fix F8 (Opus review 2): the rationale this comment
# carried before this fix was FALSE and is corrected here (the constant
# itself is unaffected). It claimed a namespace of 0 would land in the
# SAME lock space the single-bigint form `ops.py::_RITUAL_ADVISORY_
# LOCK_KEY` (761761761, a `pg_advisory_xact_lock`) uses, risking a
# collision between a bootstrap/reset ritual's lock and an idempotency-
# key lock. PostgreSQL actually keeps those two key spaces disjoint by
# construction, regardless of namespace value: the 1-argument
# `pg_advisory_[xact_]lock(bigint)` form and the 2-argument
# `pg_advisory_[xact_]lock(int, int)` form record different `objsubid`
# values in `pg_locks` (1 for the 1-argument form, 2 for the
# 2-argument form) -- so `pg_advisory_xact_lock(761761761)` and
# `pg_advisory_lock(0, 761761761)` are two DIFFERENT locks, never the
# same one, even though they would superficially "look like" the same
# 64-bit id under a naive `(namespace << 32 | hashtext(key))` encoding.
# This namespace constant is still a large, distinctive value, far from
# both `_RITUAL_ADVISORY_LOCK_KEY` and `_IDEMPOTENCY_COUNT_ADVISORY_
# LOCK_KEY` below -- kept for HUMAN legibility (so two DIFFERENT lock
# families never share a suspiciously similar-looking id in a
# `pg_locks` dump), not because a collision with the 1-argument form
# was ever actually possible.
_IDEMPOTENCY_KEY_LOCK_NAMESPACE = 76176100
# Ruling U-7: table-level (not per-key) advisory lock serializing
# `idempotency_reserve`'s COUNT-then-write across DIFFERENT keys (D-5
# (iii)) -- same family as `ops.py::_RITUAL_ADVISORY_LOCK_KEY` (a
# single, fixed 64-bit `pg_advisory_xact_lock` key), a DIFFERENT
# constant from it (that lock guards bootstrap/reset ritual ordering;
# this one guards `idempotency_entries` capacity accounting -- two
# independent serialization points that must never share one lock id).
_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY = 761761762
# Schema-operation lock: one fixed single-bigint `pg_advisory_xact_lock` key
# per application database (an advisory lock is scoped to the database it is
# taken in), taken exclusively by every schema operation and by nothing
# else, so the schema operations of one application run one at a time --
# across processes, because PostgreSQL holds it. It is what makes a plan
# token's revision, the `schema_objects` count and the registry row an
# `alter_field` reads still true when the DDL they justify runs. A third
# family beside the two above: a different value from each of them.
_SCHEMA_SERIALIZATION_LOCK_KEY = 761761763
# Entity lock: two-int `(namespace, hashtext(entity))` advisory locks, a
# separate key space from the single-bigint family above and from the
# idempotency namespace (`_IDEMPOTENCY_KEY_LOCK_NAMESPACE`). A schema
# operation takes its entity exclusively, a data write takes every entity
# it touches shared: a write and a schema operation on the same entity
# never overlap, while writes on an entity, and everything on other
# entities, do not wait for each other. A `hashtext` collision only makes
# two entities share a lock (too much serialization, never too little).
_ENTITY_LOCK_NAMESPACE = 76176101

# (try statement, blocking statement) per lock mode. Both take the same
# locks; a lock wait is told apart from an immediate acquisition by trying
# first (`_acquire_advisory`). The entity statements take a whole sorted
# array of names in one round trip.
_KEY_LOCK_STATEMENTS = (
    sql.SQL("SELECT pg_try_advisory_xact_lock(%s, hashtext(%s))"),
    sql.SQL("SELECT pg_advisory_xact_lock(%s, hashtext(%s))"),
)
_COUNT_LOCK_STATEMENTS = (
    sql.SQL("SELECT pg_try_advisory_xact_lock(%s)"),
    sql.SQL("SELECT pg_advisory_xact_lock(%s)"),
)
_SCHEMA_LOCK_STATEMENTS = (
    sql.SQL("SELECT pg_try_advisory_xact_lock(%s)"),
    sql.SQL("SELECT pg_advisory_xact_lock(%s)"),
)
_ENTITY_LOCK_SHARED = (
    sql.SQL("SELECT bool_and(pg_try_advisory_xact_lock_shared(%s, hashtext(e))) FROM unnest(%s::text[]) AS e"),
    sql.SQL("SELECT pg_advisory_xact_lock_shared(%s, hashtext(e)) FROM unnest(%s::text[]) AS e"),
)
_ENTITY_LOCK_EXCLUSIVE = (
    sql.SQL("SELECT bool_and(pg_try_advisory_xact_lock(%s, hashtext(e))) FROM unnest(%s::text[]) AS e"),
    sql.SQL("SELECT pg_advisory_xact_lock(%s, hashtext(e)) FROM unnest(%s::text[]) AS e"),
)

# PostgreSQL's two "try again" outcomes: the transaction was chosen as the
# victim of a deadlock (40P01) or failed to serialize (40001). Neither is
# the client's doing; nothing was applied.
_TRANSIENT_ERRORS = (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure)

# m-1 (independent review correction, extended Q4 phase WP-4; Phase 9
# WP-3c adds `_IDEMPOTENCY_TABLE`): the full set of this package's own
# bookkeeping table names `schema_count()` excludes from its
# `application`-level accounting -- a plain tuple, not a `frozenset`, so
# the SQL `NOT IN (%s, %s, %s, %s)` parameter list below stays in a
# fixed, readable order matching this declaration.
_BOOKKEEPING_TABLES = (_SCHEMA_REVISION_TABLE, _FIELD_TYPES_TABLE, _PLATFORM_UPGRADES_TABLE, _IDEMPOTENCY_TABLE)

# The internal row-order column every collection table carries (design
# docs/design/PHASE11_KEYSET_PAGING_V1.md D-2's own table). Not a
# bookkeeping TABLE (`_BOOKKEEPING_TABLES` above
# lists tables `schema_count()` excludes) -- this is a COLUMN every real
# collection table has, added here by `create_collection` below and by
# `migrations/0015_row_order_column_upgrade.sql` for a collection that
# predates this column. `GENERATED ALWAYS AS IDENTITY` so no INSERT path
# can ever supply its own value. `cell.ApplicationCell._visible_field_
# domains` is the only place that hides it from request-shape/catalog
# logic -- this backend's own `field_domains` reports it like any other
# physical column, unchanged.
_ROW_ORDER_COLUMN = "_mdb_row"


def _execute(cursor, statement, params=()):
    """R-2 choke point. The ONLY call to `cursor.execute` in this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError(
            "PostgresBackend._execute refuses a %s; only psycopg.sql.SQL/"
            "Composed objects may reach the database (R-2 choke point)"
            % (type(statement).__name__,)
        )
    cursor.execute(statement, params)
    return cursor


class PostgresBackend:
    """One application's PostgreSQL storage: a bounded pool per role.

    The developer pool's connections authenticate as this application's own
    PostgreSQL DEVELOPER role (schema owner, DDL authority) and execute every
    schema-mutating and catalog-reading statement; the runtime pool's as its
    RUNTIME role (DML only, per R-1's provisioning grants) and execute every
    data statement. This is R-1's own role separation enforced a second time,
    structurally, underneath this foundation's own application-level
    `_require_developer`/`_require_data` gates (`cell.py`): even a code defect
    that let a non-developer principal reach `create_collection` at the Python
    level would still hit PostgreSQL's own `InsufficientPrivilege` the moment
    it attempted DDL over a runtime connection, because this backend never
    even attempts DDL there.

    Nothing here holds a connection between requests. `request_scope` hands
    one request its connections and every other method works on them.
    """

    def __init__(self, runtime_dsn, developer_dsn, *, application_id=None, max_execution_ms: int | None = None,
                 pool_size: int = DEFAULT_MAX_SIZE):
        # No connection is opened here: each pool opens its connections on
        # first use, up to `pool_size` (the composition root passes the
        # process's own simultaneous-request bound, `config.role_pool_size`).
        self._runtime_pool = BoundedConnectionPool(runtime_dsn, max_size=pool_size)
        self._developer_pool = BoundedConnectionPool(developer_dsn, max_size=pool_size)
        # The timeout a scope that has no deadline of its own
        # (`request_scope(..., deadline=None)`: an internal read, a direct
        # caller) applies to its connections -- the deployment's declared
        # `execution_ms` (`MITATEDB_MAX_EXECUTION_MS` via `FoundationConfig.
        # from_env`), or `FoundationConfig`'s class-attribute default for a
        # bare construction. A scope that has a deadline derives its timeout
        # from it instead.
        self._default_timeout_ms = (
            max_execution_ms if max_execution_ms is not None else FoundationConfig.max_execution_ms
        )
        # Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(f),
        # §3.7 data-plane steps 9-10, F-12): the application's own platform-
        # upgrade ledger is checked once per served application, at startup,
        # by `verify_platform_upgrades` (`main.py::build_app` calls it). A
        # missing upgrade does not stop the process -- every OTHER served
        # application keeps serving -- the message is held here
        # (`None` when nothing is pending) and `request_scope` refuses every
        # request to THIS application with it, as `errors.PlatformUpgradePending`
        # (mapped by `http.py::_CLASSIFY_ORDER` to `SERVICE_UNAVAILABLE`).
        # `application_id=None` (a bare backend in a test or tool, not a
        # served application) skips the check.
        self._application_id = application_id
        self._pending_platform_upgrade_message = None
        # Schema-lock statistics (`lock_schema` / `lock_entities`): one
        # acquire per call, one wait when the first, non-blocking attempt
        # did not get the lock and the call had to block for it.
        self._schema_lock_stats_lock = threading.Lock()
        self._schema_lock_stats = {"acquire_count": 0, "wait_count": 0, "wait_total_ms": 0.0, "wait_max_ms": 0.0}

    def verify_platform_upgrades(self):
        """F-12 (design §3.8): borrows one runtime connection, checks that
        this application's own ledger records every upgrade this package
        requires, and returns the connection. Holds the refusal message
        (`_pending_platform_upgrade_message`) when one is missing -- it does
        not raise for that: the process starts and this application's own
        requests refuse. A database that cannot be reached at all raises
        `pool.PoolConnectFailed`, as an unreachable database always stopped
        the startup of the process. A no-op for a backend built without an
        `application_id`."""
        if self._application_id is None:
            return
        conn = self._runtime_pool.acquire()
        try:
            try:
                platform_upgrades.require_application_upgrades_applied(
                    conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME,
                    expected=platform_upgrades.PLATFORM_UPGRADE_NUMBERS, application_id=self._application_id,
                    ops_module=platform_upgrades.PEER_MODULE,
                )
            finally:
                # `require_application_upgrades_applied` only ever
                # reads (a `SELECT`, or nothing at all if `UndefinedTable`
                # already rolled the connection back itself) -- this
                # `rollback()` closes out that read-only transaction either
                # way.
                conn.rollback()
        except platform_upgrades.PlatformUpgradeError as exc:
            # design §3.8 F-12: the ONLY platform-upgrade condition that
            # reaches an API response. The message is HELD here, not
            # raised -- a later `ops upgrade-applications` run followed by a
            # process restart is the only way this application's own
            # requests stop refusing.
            self._pending_platform_upgrade_message = str(exc)
        finally:
            self._runtime_pool.release(conn)

    def close(self):
        self._runtime_pool.closeall()
        self._developer_pool.closeall()

    def schema_lock_stats(self):
        """A copy of the schema-lock statistics: `acquire_count` (calls to
        `lock_schema` / `lock_entities` that got their locks), `wait_count`
        (entries into the blocking statement, including those that ended in a
        timeout or an error), `wait_total_ms`, `wait_max_ms`."""
        with self._schema_lock_stats_lock:
            return dict(self._schema_lock_stats)

    def pool_stats(self):
        """`{"runtime": ..., "developer": ...}`: each pool's own `stats()`."""
        return {"runtime": self._runtime_pool.stats(), "developer": self._developer_pool.stats()}

    def prepared_stats(self):
        """Probes every connection that is idle in either role pool,
        labelled `runtime@<pid>`/`developer@<pid>` (`conn.info.backend_pid`,
        the same public attribute r2db-api's own pool-based `label` uses): a
        row per idle connection, the runtime pool's first. The connections
        are taken out of the pool's idle queue without `acquire()`
        (`BoundedConnectionPool.map_idle`) and put back afterwards, so the
        probe does not count as an acquisition and sees the same set of
        connections on every call; a connection a request has checked out at
        that moment is not probed.

        A probe that raises may leave its connection mid-transaction
        (aborted) -- if the failure happened after the probe's own SELECT
        but before its `commit()` (rework 指摘 5): rolled
        back here so the row reports the connection idle, and so it is
        never put back aborted (mutation M25 drops this rollback). This
        does lose whatever was prepared on that connection (F2), but a
        connection already stuck aborted from a probe failure is not a
        state worth preserving prepared statements over."""
        rows = []

        def probe(role_name, conn):
            label = f"{role_name}@{conn.info.backend_pid}"
            try:
                return probe_prepared_statements(conn, label)
            except Exception as exc:  # noqa: BLE001 -- reported as probed=False/error=<class name> (D-2, WO §6.1 H-4)
                if conn.info.transaction_status != TransactionStatus.IDLE:
                    conn.rollback()
                return prepared_stats_skeleton(conn, label, error=type(exc).__name__)

        for role_name, pool in (("runtime", self._runtime_pool), ("developer", self._developer_pool)):
            rows.extend(pool.map_idle(lambda conn, role_name=role_name: probe(role_name, conn)))
        return rows

    # ------------------------------------------------------------------
    # request scope: connections, transaction, timeouts, locks
    # ------------------------------------------------------------------
    def _borrow(self, pool, deadline):
        """One connection from `pool`, waiting no longer than what remains
        of `deadline` (the pool's own wait limit when there is none). A
        wait that outlasts the deadline is the request running past its
        `execution_ms`; a database that cannot be reached is a transient
        storage failure."""
        timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
        try:
            return pool.acquire(timeout=timeout)
        except PoolExhausted as exc:
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms") from exc
        except PoolConnectFailed as exc:
            raise StorageTransientError("the storage backend could not be reached") from exc

    @contextmanager
    def request_scope(self, kind, *, deadline=None):
        """See `backend.StorageBackend.request_scope`. Borrows the
        developer connection first and, for a data request, the runtime
        connection second -- always in that order, before any lock is
        taken, so a request never waits for a connection while holding a
        lock another request is waiting for -- opens the transaction on
        each and sets `statement_timeout` / `lock_timeout` from `deadline`
        once. The connections go back to their pools when the scope ends,
        by whichever way it ends: a request that finished normally commits
        the read-only transaction it may still have open (`_end_reads`), and
        the pool rolls back whatever is still open on return, which also
        releases every lock the request took."""
        if kind not in SCOPE_KINDS:
            raise ValueError(f"unknown request scope kind {kind!r}")
        if self._pending_platform_upgrade_message is not None:
            raise PlatformUpgradePending(self._pending_platform_upgrade_message)
        held = []
        try:
            developer = self._borrow(self._developer_pool, deadline)
            held.append((self._developer_pool, developer))
            if kind == "schema":
                main = developer
            else:
                main = self._borrow(self._runtime_pool, deadline)
                held.append((self._runtime_pool, main))
            timeout_ms = self._timeout_ms(deadline)
            if timeout_ms is None:
                timeout_ms = self._default_timeout_ms
            for _pool, conn in held:
                try:
                    with conn.cursor() as cur:
                        self._set_timeouts(cur, timeout_ms)
                except psycopg.Error as exc:
                    raise StorageTransientError("the storage backend could not be reached") from exc
            scope = RequestScope(kind, deadline, backend=self, main=main, developer=developer)
            yield scope
            self._end_reads(scope)
        finally:
            for pool, conn in reversed(held):
                pool.release(conn)

    def _end_reads(self, scope):
        """Reached only when the request's body finished without raising:
        a connection still inside a transaction then holds nothing but reads
        (the main connection of a query, the developer connection of a data
        request's pass 1 or of a catalog read) and its transaction is
        committed, not rolled back. A rollback makes psycopg forget every
        statement it had prepared on the connection (and `DEALLOCATE ALL`
        on the server), so rolling back each read-only transaction at the
        scope's end would keep a pooled connection from ever reaching its
        prepare threshold. The main connection goes first, then the developer
        connection. A request that raised never gets here: the pool rolls its
        connections back when they are returned."""
        seen = set()
        for conn in (scope.main, scope.developer):
            if conn is None or id(conn) in seen:
                continue
            seen.add(id(conn))
            if conn.info.transaction_status != TransactionStatus.INTRANS:
                continue
            try:
                conn.commit()
            except psycopg.Error as exc:
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc

    def _retime(self, scope):
        """Sets `statement_timeout` / `lock_timeout` again, from what remains
        of the request's deadline, on every connection the scope holds. Called
        after a lock wait: the scope's timeouts were set from the budget the
        request had when it opened, and the wait has spent some of it, so the
        statements that follow must not get the full amount again. A wait that
        used the whole budget ends the request."""
        if scope.deadline is None:
            return
        if scope.deadline - time.monotonic() <= 0:
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        timeout_ms = self._timeout_ms(scope.deadline)
        seen = set()
        for conn in (scope.main, scope.developer):
            if conn is None or id(conn) in seen:
                continue
            seen.add(id(conn))
            try:
                with conn.cursor() as cur:
                    self._set_timeouts(cur, timeout_ms)
            except psycopg.Error as exc:
                raise StorageTransientError("the storage backend could not be reached") from exc

    def _acquire_advisory(self, scope, statements, params, *, count=True):
        """Takes the advisory locks `statements` name on the scope's main
        connection, for the rest of its transaction: first the non-blocking
        statement; when it does not get every lock, the blocking one. Entering
        the blocking statement is one wait (in the schema-lock statistics when
        `count`), counted with the time it took whether it ends in the lock or
        in a timeout, a deadlock or a lost connection; an acquisition is
        counted when it succeeded. After a wait the request's timeouts are set
        again from the remaining deadline. An uncontended acquisition is one
        statement. A wait ends at the scope's `lock_timeout`."""
        try_statement, block_statement = statements
        waited_ms = None
        started = None
        try:
            try:
                with scope.main.cursor() as cur:
                    _execute(cur, try_statement, params)
                    acquired = cur.fetchone()[0]
                    if not acquired:
                        waited_ms = 0.0
                        started = time.monotonic()
                        _execute(cur, block_statement, params)
            except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
                raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
            except _TRANSIENT_ERRORS as exc:
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
            except psycopg.errors.DataError as exc:
                # The one client-chosen value these statements carry is an
                # idempotency key; PostgreSQL refusing it as data is a refusal of
                # the request, as for every other statement that binds a value.
                raise ValidationError("storage backend rejected the request") from exc
            except psycopg.Error as exc:
                # Everything else is the connection or the server, never the
                # request.
                raise StorageTransientError("the storage backend could not be reached") from exc
        finally:
            if waited_ms is not None:
                if started is not None:
                    waited_ms = (time.monotonic() - started) * 1000.0
                if count:
                    with self._schema_lock_stats_lock:
                        self._schema_lock_stats["wait_count"] += 1
                        self._schema_lock_stats["wait_total_ms"] += waited_ms
                        if waited_ms > self._schema_lock_stats["wait_max_ms"]:
                            self._schema_lock_stats["wait_max_ms"] = waited_ms
        if count:
            with self._schema_lock_stats_lock:
                self._schema_lock_stats["acquire_count"] += 1
        if waited_ms is not None:
            self._retime(scope)

    def lock_schema(self, *, scope):
        self._acquire_advisory(scope, _SCHEMA_LOCK_STATEMENTS, [_SCHEMA_SERIALIZATION_LOCK_KEY])

    def lock_entities(self, names, *, shared, scope):
        ordered = sorted({validate_identifier(name, "entity") for name in names})
        if not ordered:
            return
        statements = _ENTITY_LOCK_SHARED if shared else _ENTITY_LOCK_EXCLUSIVE
        self._acquire_advisory(scope, statements, [_ENTITY_LOCK_NAMESPACE, ordered])

    def check_reserved(self, value, label):
        # WP-3e rework T1 (追補2 M-1): the reserved-name half of the
        # identifier choke point `cell.ApplicationCell._identifier`
        # always applies together with `identifiers.validate_identifier`
        # (that module's own docstring names this exact pairing) -- not
        # a defence-in-depth backstop for a check the cell layer already
        # performs itself (this backend is the ONLY place PostgreSQL's
        # own `pg_`-prefixed reservations are known), so it carries the
        # same `identifier_syntax` vocabulary `validate_identifier`
        # itself uses, `field` = `label` (the same per-call-site request
        # position `_identifier` already passes to both stages).
        _check_reserved_name(value, label)

    # ------------------------------------------------------------------
    # catalog (developer connection -- schema owner)
    # ------------------------------------------------------------------
    def schema_count(self, *, scope):
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name NOT IN (%s, %s, %s, %s)"
                ), list(_BOOKKEEPING_TABLES))
                count = cur.fetchone()[0]
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return count

    def field_domains(self, collection, *, scope):
        """Live catalog lookup (R-2 stage 2) doubling as the value-domain
        source B-1 (i) needs: for every column of `collection`, this
        database's own `information_schema.columns.data_type` is mapped
        back to a domain category `encode_value` can validate a bound
        value against. Raises `errors.NotFoundError` if `collection` does
        not exist -- the same existence-check role the pre-B-1
        `field_names` method played.

        Phase 6 WP-3 (design D-3, L6-1 (v)): a physical `text` column's
        own domain is no longer a single shared `"text"` bucket
        (`_DOMAIN_BY_DATA_TYPE`'s own corrected comment above) (in `postgres_types.py`) -- it is
        looked up in the declared-type REGISTRY instead
        (`_TEXT_DOMAIN_BY_DECLARED_TYPE`), which is the only place that
        can recover which of `string`/`object`/`array`/`json` the column
        actually is. A `text`-physical column absent from the registry
        (should not occur for any field this peer's own `create_
        collection`/`add_field` created after this WP -- see
        `create_collection`'s own registry-write below) degrades to
        `"string"`, never a crash.
        """
        validate_identifier(collection, "entity")
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position"
                ), [collection])
                rows = cur.fetchall()
                declared = self._field_types_locked(cur, collection) if rows else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            # WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
            # 裁定 6, review F9): `_mdb_field_types` missing entirely means
            # migration 0006 was never applied to this application DB -- an
            # OPERATOR/DEPLOYMENT defect, never a client mistake. Before
            # this fix every read/write on an un-migrated DB surfaced as
            # `ValidationError` (contract `VALIDATION_FAILED`, a CLIENT
            # fault code) -- fail-closed either way, but the wrong fault
            # attribution. `StorageConfigurationError` is this peer's own
            # existing "permanent misconfiguration, not a client mistake"
            # class (`credential_store_postgres.py`'s identical `
            # InsufficientPrivilege` precedent), mapping to `SERVICE_
            # UNAVAILABLE` at the HTTP boundary instead.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        if not rows:
            raise NotFoundError("collection not found")
        domains = {}
        for name, data_type in rows:
            if data_type in _DOMAIN_BY_DATA_TYPE:
                domains[name] = _DOMAIN_BY_DATA_TYPE[data_type]
            else:
                domains[name] = _TEXT_DOMAIN_BY_DECLARED_TYPE.get(declared.get(name), "string")
        return domains

    def _field_types_locked(self, cur, collection):
        """Reads `_mdb_field_types` over an ALREADY-OPEN cursor (shares
        the caller's own transaction/commit-or-rollback, `field_domains`/
        `field_types` alike -- never a second, independent connection
        round trip)."""
        _execute(cur, sql.SQL("SELECT field, declared_type FROM {} WHERE entity = %s")
                  .format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        return {field: declared_type for field, declared_type in cur.fetchall()}

    def field_types(self, collection, *, scope):
        """Phase 6 WP-3 (design D-3): see `backend.StorageBackend.
        field_types`'s own contract -- the single source of truth `GET
        /v1/catalog` (`http.py::get_catalog`) and the cell-layer choke
        point (`cell.py::_prepare_values`/`_bind_filters`) both read.
        Existence-checked the same way `field_domains` is (an entity with
        no columns at all cannot exist on this backend)."""
        validate_identifier(collection, "entity")
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                declared = self._field_types_locked(cur, collection) if exists else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            # See `field_domains`'s own identical rework above -- same
            # operator/deployment-fault attribution, same class.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        if not exists:
            raise NotFoundError("collection not found")
        return declared

    def all_field_types(self, *, scope):
        """Phase 6 WP-3 (design D-3): see `backend_sqlite.SQLiteBackend.
        all_field_types`'s identical docstring -- `GET /v1/catalog`'s
        sole data source."""
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL("SELECT entity, field, declared_type FROM {}")
                          .format(sql.Identifier(_FIELD_TYPES_TABLE)))
                rows = cur.fetchall()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            # See `field_domains`'s own identical rework above -- same
            # operator/deployment-fault attribution, same class.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        result: dict = {}
        for entity, field, declared_type in rows:
            result.setdefault(entity, {})[field] = declared_type
        return result

    @staticmethod
    def _decode_constraint_row(enum_json, nullable_value):
        """Phase 9 WP-3a (design D-2 (1)/(4)): `_mdb_field_types.enum_json`
        (a JSON-array TEXT column, `NULL` when this field declares no
        `enum`) / `.nullable` (a real `boolean` column, migration
        0009_field_constraints_upgrade.sql) -> the same `{"nullable":
        bool, "enum": [...]}` shape `backend_sqlite.SQLiteBackend`'s own
        in-memory registry carries -- `"enum"` present only when
        `enum_json` is not `NULL`."""
        constraints = {"nullable": bool(nullable_value)}
        if enum_json is not None:
            constraints["enum"] = json.loads(enum_json)
        return constraints

    def _field_constraints_locked(self, cur, collection):
        """Reads `_mdb_field_types.enum_json`/`.nullable` over an
        ALREADY-OPEN cursor -- same sharing discipline as
        `_field_types_locked` immediately above."""
        _execute(cur, sql.SQL("SELECT field, enum_json, nullable FROM {} WHERE entity = %s")
                  .format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        return {
            field: self._decode_constraint_row(enum_json, nullable_value)
            for field, enum_json, nullable_value in cur.fetchall()
        }

    def field_constraints(self, collection, *, scope):
        """Phase 9 WP-3a (design D-2 (1)/(4)): see `backend.
        StorageBackend.field_constraints`'s own contract -- the single
        source of truth `GET /v1/catalog` and the cell-layer choke point
        (`cell.py::_prepare_values`, never `_bind_filters`) both read.
        Existence-checked the same way `field_types` is."""
        validate_identifier(collection, "entity")
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                declared = self._field_constraints_locked(cur, collection) if exists else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        if not exists:
            raise NotFoundError("collection not found")
        return declared

    def _field_types_and_constraints_locked(self, cur, collection):
        """Code review §2 C / 監督裁定 C: `field_types`'s own
        `declared_type` and `field_constraints`'s own `enum_json`/
        `nullable` live on the SAME `_mdb_field_types` row -- this reads
        all three columns in the ONE query `_field_types_locked`/
        `_field_constraints_locked` used to make as TWO independent
        round trips against that identical row.

        History: CH-0525
        """
        _execute(cur, sql.SQL(
            "SELECT field, declared_type, enum_json, nullable FROM {} WHERE entity = %s"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        types: dict = {}
        constraints: dict = {}
        for field, declared_type, enum_json, nullable_value in cur.fetchall():
            types[field] = declared_type
            constraints[field] = self._decode_constraint_row(enum_json, nullable_value)
        return types, constraints

    def field_types_and_constraints(self, collection, *, scope):
        """Code review §2 C / 監督裁定 C (P-8/G-4 performance
        finding): see `backend.StorageBackend.field_types_and_
        constraints`'s own contract -- `field_types` and `field_
        constraints` merged into the single query `_field_types_and_
        constraints_locked` above makes. `cell.py::_prepare_values` (and,
        via the pair it returns, `_check_missing_required_fields`) is
        the sole caller -- every other reader of `field_types`/`field_
        constraints` keeps calling one of those two on their own,
        unchanged. Existence-checked the same way both are.

        History: CH-0526
        """
        validate_identifier(collection, "entity")
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                types, constraints = self._field_types_and_constraints_locked(cur, collection) if exists else ({}, {})
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        if not exists:
            raise NotFoundError("collection not found")
        return types, constraints

    def all_field_constraints(self, *, scope):
        """Phase 9 WP-3a (design D-2 (1)/(4)): see `backend_sqlite.
        SQLiteBackend.all_field_constraints`'s identical docstring --
        `GET /v1/catalog`'s sole data source for `field_constraints`."""
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL("SELECT entity, field, enum_json, nullable FROM {}")
                          .format(sql.Identifier(_FIELD_TYPES_TABLE)))
                rows = cur.fetchall()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        result: dict = {}
        for entity, field, enum_json, nullable_value in rows:
            result.setdefault(entity, {})[field] = self._decode_constraint_row(enum_json, nullable_value)
        return result

    def alter_field_constraints(self, collection, field, *, enum=UNCHANGED, nullable=None, audit_hook=None,
                                deadline=None, dry_run=False, idempotency_record=None, scope):
        """Phase 9 WP-3a (design D-2 (5)/(6), 実装の形 4, F-6, 監督裁定
        S-g): see `backend.StorageBackend.alter_field_constraints`'s own
        contract. Unlike `create_collection`/`add_field` above (whose own
        "read the live catalog, then DDL in a later transaction" shape
        `field_domains` embodies), this method never leaves the developer
        connection's own transaction between its existing-row SELECT and
        its registry UPDATE -- both happen inside the SAME `with scope.
        main.cursor()` block, committed (or rolled back) together
        as the LAST step of this one method. The developer connection
        reads real APPLICATION DATA rows here (not only the catalog) --
        safe because this application's own developer role OWNS every
        entity table it creates (`create_collection`/`add_field` above),
        and PostgreSQL grants a table's owner every privilege on it,
        `SELECT` included, with no separate `GRANT` required (F-6,
        `migrations/0003_provision_application.sql`)."""
        validate_identifier(collection, "entity")
        validate_identifier(field, "field")
        hook_fired = False
        try:
            with scope.main.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT declared_type, enum_json, nullable FROM {} WHERE entity = %s AND field = %s"
                ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection, field])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("field not found")
                declared_type, current_enum_json, current_nullable = row
                new_nullable = bool(current_nullable) if nullable is None else nullable
                # Code review §2 A / 監督裁定 A: tri-state
                # `enum` -- `UNCHANGED` (default) keeps the field's
                # current `enum` (decoded from the row already read
                # above); an explicit `None` CLEARS it; any other value
                # (an already-validated, non-empty list) SETS/REPLACES
                # it. This is the SAME three-way rule `backend_sqlite.
                # SQLiteBackend.alter_field_constraints` applies.
                # history: CH-0528
                if enum is UNCHANGED:
                    new_enum = json.loads(current_enum_json) if current_enum_json is not None else None
                elif enum is not None:
                    new_enum = list(enum)
                else:
                    new_enum = None
                # Code review §2 F / 監督裁定 F: locks
                # `collection` IN SHARE ROW EXCLUSIVE MODE before scanning
                # its existing rows, inside this SAME transaction -- this
                # blocks a concurrent INSERT/UPDATE/DELETE (ROW
                # EXCLUSIVE) on this table for the rest of this
                # transaction while still permitting concurrent SELECTs
                # (ACCESS SHARE), so no other session's write can land a
                # newly-violating row in the window between this scan
                # and this same transaction's own COMMIT below. The
                # single-transaction placement (実装の形 4, S-g) alone
                # only closes "registry updated while a row still went
                # unscanned"; under READ COMMITTED (this connection's own
                # default) it does not, by itself, close this phantom-
                # write window -- this lock does.
                #
                # R-35 (Phase 10, WP-6d-i review): the original fix used
                # plain `SHARE MODE`, which does not conflict with itself
                # -- two concurrent `alter_field`/`add_field` calls on the
                # SAME entity could both acquire it here, then each block
                # at its own later `ALTER TABLE` (ACCESS EXCLUSIVE)
                # waiting on the other's SHARE lock, a guaranteed mutual
                # wait broken only by PostgreSQL's deadlock detector
                # aborting one side with an error rather than the two
                # calls simply serializing. `SHARE ROW EXCLUSIVE`
                # conflicts with itself, so the second caller instead
                # waits here, at LOCK TABLE, and proceeds only once the
                # first transaction commits or rolls back -- it still
                # excludes concurrent row writers (ROW EXCLUSIVE) exactly
                # as plain SHARE did, so the scan property above is
                # unchanged.
                # history: CH-0529
                _execute(cur, sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(collection)))
                _execute(cur, sql.SQL("SELECT {} FROM {}").format(
                    sql.Identifier(field), sql.Identifier(collection)))
                violation = None
                for (value,) in cur.fetchall():
                    if value is None:
                        if new_nullable is False:
                            violation = "nullable"
                            break
                        continue
                    if new_enum is not None:
                        decoded = bool(value) if declared_type == "boolean" else value
                        if decoded not in new_enum:
                            violation = "enum"
                            break
                if violation is not None:
                    # Code review §2 D / 監督裁定 D: `field`
                    # names a POSITION IN THE REQUEST (design D-3 (2)),
                    # not the entity field name -- see `backend_sqlite.
                    # SQLiteBackend.alter_field_constraints`'s identical
                    # comment for why that position is `violation` itself.
                    # history: CH-0530
                    raise ConflictError(
                        "existing rows violate the constraints this alter_field would establish",
                        details={"field": violation, "violated_declaration": violation},
                    )
                # Phase 9 WP-3b (design D-4 (4)): the registry UPDATE and
                # revision bump are skipped for a dry run -- the scan
                # above (and its possible `ConflictError`) already ran
                # for real either way, SAME refusal for dry_run and real.
                new_enum_json = json.dumps(new_enum) if new_enum is not None else None
                if not dry_run:
                    _execute(cur, sql.SQL(
                        "UPDATE {} SET enum_json = %s, nullable = %s WHERE entity = %s AND field = %s"
                    ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [new_enum_json, new_nullable, collection, field])
                    self._bump_schema_revision(cur)
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
                # Phase 9 WP-3b: `descriptor`'s OTHER, pre-existing fields
                # -- same-cursor read, so a real (non-dry-run) call's own
                # UPDATE above is already visible here (read-your-own-
                # writes); a dry run's is not, since nothing was written.
                existing_types, existing_constraints = self._field_types_and_constraints_locked(cur, collection)
            # Phase 9 WP-3c rework (design D-5, I-1/I-8): built here,
            # BEFORE the commit/rollback branch below, from `new_enum`/
            # `new_nullable` (already resolved above) and `existing_
            # types`/`existing_constraints` (already read back, real,
            # inside the SAME transaction) -- reused for both this
            # method's own idempotency write below and its final `return`
            # further down, never a second, independently constructed
            # copy.
            new_field_constraints = {"nullable": new_nullable}
            if new_enum is not None:
                new_field_constraints["enum"] = list(new_enum)
            descriptor = {
                "entity": collection,
                "fields": sorted(existing_types),
                "field_types": existing_types,
                "field_constraints": {**existing_constraints, field: new_field_constraints},
            }
            if dry_run:
                scope.main.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): `new_revision` was
                # already read back for real, inside this SAME
                # transaction, above.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision), "descriptor": descriptor,
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(scope.main, key, digest, response_json, now_ms)
                scope.main.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            scope.main.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except (NotFoundError, ConflictError):
            scope.main.rollback()
            raise
        except psycopg.errors.UndefinedTable:
            scope.main.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            scope.main.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            if isinstance(exc, _TRANSIENT_ERRORS):
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            scope.main.rollback()
            raise
        # `descriptor` was already built above (Phase 9 WP-3c rework),
        # before the commit/rollback branch -- reused verbatim here.
        return new_revision, descriptor

    def schema_revision(self, *, scope):
        try:
            with scope.developer.cursor() as cur:
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                row = cur.fetchone()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return row[0] if row else 0

    def _bump_schema_revision(self, cur):
        _execute(cur, sql.SQL("UPDATE {} SET revision = revision + 1 WHERE id = TRUE")
                  .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))

    # ------------------------------------------------------------------
    # DDL (developer connection only -- R-1)
    # ------------------------------------------------------------------
    def create_collection(self, name, fields, *, field_types=None, field_constraints=None, audit_hook=None,
                          deadline=None, dry_run=False, idempotency_record=None, scope):
        validate_identifier(name, "collection")
        definitions = []
        for field, field_type in fields.items():
            validate_identifier(field, "field")
            definitions.append(sql.SQL("{} {}").format(sql.Identifier(field), _TYPE_SQL[field_type]))
        # Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2's own table:
        # every NEW collection carries the
        # internal row-order column from the start -- an existing
        # collection (provisioned before this column existed) gets it
        # retrofitted by `migrations/0015_row_order_column_upgrade.sql`
        # instead. Not reachable through `fields`/`field_types` (the
        # client-declared columns validated above): `identifiers.py`'s
        # own leading-`_` syntax rejection already makes this exact name
        # un-declarable, so no client request can ever collide with it.
        definitions.append(sql.SQL("{} BIGINT GENERATED ALWAYS AS IDENTITY").format(
            sql.Identifier(_ROW_ORDER_COLUMN)))
        statement = sql.SQL("CREATE TABLE {} ({})").format(
            sql.Identifier(name), sql.SQL(", ").join(definitions)
        )
        # Phase 6 WP-3 (design D-3): robust to a direct caller that
        # bypasses `cell.py` (e.g. this repository's own tests, which call
        # this method straight against the backend) and supplies no
        # `field_types` at all, or only a partial one -- every name in
        # `fields` not covered gets the SAME backfill-rule fallback
        # `cell.ApplicationCell.create_collection` itself applies.
        field_types = dict(field_types or {})
        for field, physical_type in fields.items():
            field_types.setdefault(field, _FOUNDATION_TYPE_TO_CONTRACT_TYPE[physical_type])
        # Phase 9 WP-3a (design D-2 (1)/(4)): same robustness fallback for
        # `field_constraints` -- a name in `fields` `field_constraints`
        # (partial) omits gets `{"nullable": True}`, no `enum` (contract
        # `SchemaOperationRequest.field_constraints.description`).
        resolved_constraints = {}
        for field in fields:
            declared = dict((field_constraints or {}).get(field) or {})
            declared.setdefault("nullable", True)
            resolved_constraints[field] = declared
        field_types_statement = sql.SQL(
            "INSERT INTO {} (entity, field, declared_type, enum_json, nullable) VALUES (%s, %s, %s, %s, %s)"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE))
        # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2, review M-6):
        # `commit()` moved INSIDE this `try` (it used to run in an `else:`
        # clause, OUTSIDE the try/except -- a raise from `commit()` itself
        # used to propagate as a raw, unclassified exception, never
        # reaching this method's own `except psycopg.Error` translation at
        # all). `audit_hook.pre_commit()` -- when this schema op is
        # dispatched through `cell.py` -- runs as the LAST statement before
        # `scope.main.commit()`, still inside this same try: a raise
        # from it (an `AuditSinkUnavailable`, not a `psycopg.Error`) is
        # caught by the final `except Exception` below, which rolls back
        # the still-uncommitted DDL before propagating (fail-closed by
        # construction, D-2 item 2: schema operations are unconditionally
        # fail-closed). `hook_fired` distinguishes "the durable pre-commit
        # write itself failed" (no error row needed -- nothing was
        # committed to correct) from "the durable write succeeded but
        # THIS backend's own commit then failed" (D-2's error-row case).
        hook_fired = False
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement)
                # Phase 9 WP-3b (design D-4 (4)): the revision bump and
                # the declared-type registry write are both skipped for a
                # dry run -- the DDL above already ran for real either
                # way, so a dry run reaches the SAME `DuplicateTable` ->
                # `ConflictError` a real call would.
                if not dry_run:
                    self._bump_schema_revision(cur)
                    # Phase 6 WP-3 (design D-3): the declared-type
                    # registry write lands in the SAME transaction as the
                    # DDL above -- atomic by construction (a failure/
                    # rollback below undoes both together, never one
                    # without the other).
                    for field in fields:
                        constraints = resolved_constraints[field]
                        enum_json = json.dumps(constraints["enum"]) if "enum" in constraints else None
                        _execute(cur, field_types_statement,
                                 [name, field, field_types[field], enum_json, constraints["nullable"]])
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
            if dry_run:
                scope.main.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): the idempotency
                # record is written as the LAST statement before this
                # backend's own commit -- same connection, same
                # transaction as the DDL above, exactly like `audit_hook.
                # pre_commit()` immediately above it. `new_revision` was
                # already read back for real, inside this SAME
                # transaction, above -- unlike `backend_sqlite.
                # SQLiteBackend`'s own in-process counterpart, nothing
                # here is a prediction. The stored response mirrors this
                # method's own final `return` below verbatim (same
                # `name`/`fields`/`field_types`/`resolved_constraints`
                # locals), so a later replay is byte-identical to what an
                # uncached call would have returned.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision),
                        "descriptor": {
                            "entity": name, "fields": sorted(fields), "field_types": dict(field_types),
                            "field_constraints": {f: dict(c) for f, c in resolved_constraints.items()},
                        },
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(scope.main, key, digest, response_json, now_ms)
                scope.main.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            scope.main.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.DuplicateTable:
            scope.main.rollback()
            raise ConflictError("collection already exists")
        except psycopg.Error as exc:
            scope.main.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            if isinstance(exc, _TRANSIENT_ERRORS):
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            # Covers `audit_hook.pre_commit()` itself raising
            # `AuditSinkUnavailable` (never a `psycopg.Error`, so the
            # branch above does not catch it) -- the DDL above already ran
            # on this connection but was never committed; roll it back
            # before letting the failure propagate.
            scope.main.rollback()
            raise
        return new_revision, {
            "entity": name,
            "fields": sorted(fields),
            "field_types": dict(field_types),
            "field_constraints": {f: dict(c) for f, c in resolved_constraints.items()},
        }

    def add_field(self, collection, field, field_type, *, contract_type=None, enum=None, nullable=None,
                  audit_hook=None, deadline=None, dry_run=False, idempotency_record=None, scope):
        validate_identifier(collection, "entity")
        validate_identifier(field, "field")
        statement = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
            sql.Identifier(collection), sql.Identifier(field), _TYPE_SQL[field_type]
        )
        # Phase 6 WP-3 (design D-3): same robustness fallback as
        # `create_collection` above, for a direct caller supplying no
        # `contract_type`.
        if contract_type is None:
            contract_type = _FOUNDATION_TYPE_TO_CONTRACT_TYPE[field_type]
        # Phase 9 WP-3a (design D-2 (1)/(4)): `nullable=None` (no explicit
        # declaration) resolves to the contract default `True`, matching
        # `create_collection`'s own identical fallback above.
        resolved_nullable = True if nullable is None else nullable
        enum_json = json.dumps(list(enum)) if enum is not None else None
        field_types_statement = sql.SQL(
            "INSERT INTO {} (entity, field, declared_type, enum_json, nullable) VALUES (%s, %s, %s, %s, %s)"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE))
        # Phase 4: same `commit()`-inside-`try` + pre-commit-hook structure
        # as `create_collection` above -- see that method's own comment.
        hook_fired = False
        try:
            with scope.main.cursor() as cur:
                if resolved_nullable is False:
                    # M-6 (監督裁定, WP-3a rework 2, 2026-09-07): mirrors
                    # `alter_field_constraints`'s own existing-row rule
                    # (LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE, inside
                    # this SAME transaction, before the scan), for a NEW
                    # field instead of an existing one -- a NEW field
                    # declaring `nullable: false` on an entity that
                    # already holds rows would leave every one of them
                    # holding `null` in it (there being no earlier value
                    # for it to have held), so it is refused the same
                    # way. Checked BEFORE the DDL below, so a conflicting
                    # call changes NOTHING -- no column, no registry row,
                    # no revision bump; this cursor's own transaction
                    # rolls back whole (`except ... scope.main.
                    # rollback()` below, the same as every other failure
                    # path here).
                    #
                    # R-35 (Phase 10, WP-6d-i review): plain `SHARE MODE`
                    # does not conflict with itself, so two concurrent
                    # `add_field`/`alter_field` calls on the SAME entity
                    # could both acquire it, then each block at its own
                    # later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on
                    # the other's SHARE lock -- a guaranteed mutual wait,
                    # broken only by PostgreSQL's deadlock detector
                    # aborting one side with an error instead of the two
                    # calls simply serializing. `SHARE ROW EXCLUSIVE`
                    # conflicts with itself, so the second caller instead
                    # waits here, at LOCK TABLE, and proceeds only once
                    # the first transaction commits or rolls back -- it
                    # still excludes concurrent row writers (ROW
                    # EXCLUSIVE) exactly as plain SHARE did, so the scan
                    # property above is unchanged.
                    _execute(cur, sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(collection)))
                    _execute(cur, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(collection)))
                    (existing_rows,) = cur.fetchone()
                    if existing_rows > 0:
                        raise ConflictError(
                            "add_field declaring nullable: false on an entity that already holds rows "
                            "would leave every existing row holding null in the new field",
                            details={"violated_declaration": "nullable", "field": "nullable"},
                        )
                # Phase 9 WP-3b: the entity's OTHER, pre-existing fields,
                # read BEFORE this call's own DDL/registry write -- used
                # for `descriptor` below, dry_run or not (a dry run never
                # writes the new field to the registry at all, so it must
                # come from this call's own arguments instead, exactly
                # like `backend_sqlite.SQLiteBackend.add_field`).
                existing_types, existing_constraints = self._field_types_and_constraints_locked(cur, collection)
                _execute(cur, statement)
                # Phase 9 WP-3b (design D-4 (4)): the revision bump and
                # registry write are both skipped for a dry run -- the
                # DDL above already ran for real either way, so a dry run
                # reaches the SAME `DuplicateColumn`/`UndefinedTable` ->
                # `ConflictError`/`NotFoundError` a real call would.
                if not dry_run:
                    self._bump_schema_revision(cur)
                    # Phase 6 WP-3 (design D-3): same-transaction registry
                    # write as `create_collection` above.
                    _execute(cur, field_types_statement, [collection, field, contract_type, enum_json, resolved_nullable])
                # WP-3a rework 3 (real, measured bug -- SchemaOperationResult.
                # revision is `required` unconditionally, `contract/data-
                # service-api.v1.json`'s own `schemas.SchemaOperationResult.
                # required`): same same-transaction readback `alter_field_
                # constraints` above already performs -- this method used to
                # bump the counter but never read it back, so the caller had
                # no revision to report at all.
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
            # Phase 9 WP-3c rework (design D-5, I-1/I-8): built here,
            # BEFORE the commit/rollback branch below -- see `alter_field_
            # constraints`'s own identical rework comment above.
            new_field_constraints = {"nullable": resolved_nullable}
            if enum is not None:
                new_field_constraints["enum"] = list(enum)
            descriptor = {
                "entity": collection,
                "fields": sorted(set(existing_types) | {field}),
                "field_types": {**existing_types, field: contract_type},
                "field_constraints": {**existing_constraints, field: new_field_constraints},
            }
            if dry_run:
                scope.main.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): see `create_
                # collection`'s own identical comment above.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision), "descriptor": descriptor,
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(scope.main, key, digest, response_json, now_ms)
                scope.main.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            scope.main.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.DuplicateColumn:
            scope.main.rollback()
            raise ConflictError("field already exists")
        except psycopg.errors.UndefinedTable:
            scope.main.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            scope.main.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            if isinstance(exc, _TRANSIENT_ERRORS):
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            scope.main.rollback()
            raise
        return new_revision, descriptor

    # ------------------------------------------------------------------
    # values (R-2/B-1 value-domain gate) -- see the module-level
    # `_validate_value_domain`/`_check_domain` functions below (both in
    # `postgres_value_domain.py`), which hold
    # ALL of the actual logic. `encode_value` is a thin instance-method
    # wrapper only so it satisfies the shared `StorageBackend.encode_value`
    # call shape (`cell.py` always calls it as `self._backend.
    # encode_value(...)`); the real logic is deliberately free-standing,
    # connection-independent functions (m-8, independent review round 2:
    # "layer (i) 単体テストは接続不要であるべき" -- `tests/test_postgres.
    # py` calls these two directly, with no `platform`/`app_a` fixture and
    # no live PostgreSQL server involved at all).
    # ------------------------------------------------------------------
    def encode_value(self, value, domain=None, *, field=None, declared_type=None):
        return _validate_value_domain(value, domain, field=field, declared_type=declared_type)

    # ------------------------------------------------------------------
    # DML (runtime connection only -- R-1)
    # ------------------------------------------------------------------
    _where_sql = staticmethod(_where_sql)

    def insert_in_transaction(self, collection, fields, params, *, scope):
        # No commit/rollback here: this runs inside a transaction the
        # seam's own `transact()` already opened via `begin()` and will
        # `commit()`/`rollback()` once, after every operation in the batch
        # (`cell.py::transact`'s own `except` clause calls
        # `self._backend.rollback()`, which is sufficient to clear a
        # psycopg connection's own aborted-transaction state after an
        # exception raised here). Low-level driver errors are still
        # translated to this shared `errors.FoundationError` vocabulary
        # here so `cell.py`'s `transact()` never needs to name a
        # backend-native exception type (R-3).
        #
        # The returned `rowid` is PostgreSQL's own `ctid` (an opaque
        # `(block,offset)` pair, as its string form): purely an "insert
        # succeeded, here is SOME backend-native handle" value. This
        # foundation's own entity tables carry no server-assigned primary
        # key/serial column, and it declares `row_addressability:
        # unavailable` -- nothing in this return value is part of that
        # capability's own public surface (`conformance/
        # conformance_adapter_mitatedb.py::attempt_mutation_with_addresses`
        # already documents that the return shape carries nothing
        # address-shaped and always reports `None`). Unlike SQLite's own
        # `rowid` (stable across an `UPDATE`), `ctid` changes on
        # `UPDATE`/`VACUUM` -- a deliberate asymmetry between the two
        # backends, harmless because no caller treats the returned value
        # as a stable long-term identity.
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in fields)
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING ctid").format(
            sql.Identifier(collection), columns, placeholders
        )
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement, params)
                rowid = str(cur.fetchone()[0])
        # Phase 8 WP-1a rework 1 (裁定 2): the `execution_ms` mapping --
        # not rolled back here (same B-1 (ii) reasoning as every other
        # `except` clause in this method: the OUTER `transact()`
        # (`cell.py`) is the single rollback point for the whole batch).
        # `begin()`'s own `SET LOCAL statement_timeout`/`lock_timeout`
        # (module-level comment above `_timeout_ms`) is what makes this
        # exception reachable from an operation running INSIDE a batch,
        # not only a standalone single-operation call -- every HTTP
        # mutation reaches the database through this exact `..._in_
        # transaction` family (`cell.py::transact`, `http.py::post_mutate`
        # always dispatches through it), so leaving this mapping out here
        # left the whole HTTP mutation surface unable to ever observe a
        # real `LIMIT_EXCEEDED`/`execution_ms` denial (review finding 2).
        # history: CH-0537
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UniqueViolation:
            raise ConflictError("write conflicts with a constraint")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates,
            # which is the single rollback point for the whole batch.
            raise ValidationError("storage backend rejected the request") from exc
        return {"rowid": rowid}

    def update_in_transaction(self, collection, fields, params, filters, *, scope):
        # P3-D2 (WP-1.5): no commit/rollback here
        # -- mirrors `insert_in_transaction`'s own reasoning above. Runs
        # inside the transaction the seam's own `transact()` already
        # opened via `begin()` and will `commit()`/`rollback()` once,
        # after every operation in the batch.
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(f)) for f in fields
        )
        statement = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(collection), assignments)
        where, where_params = self._where_sql(filters)
        statement = statement + where
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement, list(params) + where_params)
                updated = cur.rowcount
        # Phase 8 WP-1a rework 1 (裁定 2): see `insert_in_transaction`'s own
        # identical `except` clause immediately above for why this mapping
        # (not rolled back here -- the outer `transact()` is the single
        # rollback point) is required on every `..._in_transaction` method.
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates.
            raise ValidationError("storage backend rejected the request") from exc
        return {"updated": updated}

    def delete_in_transaction(self, collection, filters, *, scope):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `delete` below)
        # -- same reasoning as `update_in_transaction` immediately above.
        # `cell.ApplicationCell` has already run this request through the
        # same declare-and-echo confirmation choke `delete()` itself uses
        # before this is ever called.
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement, params)
                deleted = cur.rowcount
        # Phase 8 WP-1a rework 1 (裁定 2): see `insert_in_transaction`'s own
        # identical `except` clause for why this mapping is required here
        # too (not rolled back here -- the outer `transact()` is the
        # single rollback point).
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return {"deleted": deleted}

    def read(self, collection, selected, filters, order_by, limit, *, cursor_values=None, deadline=None, scope):
        columns = sql.SQL(", ").join(sql.Identifier(x) for x in selected)
        statement = sql.SQL("SELECT {} FROM {}").format(columns, sql.Identifier(collection))
        where, where_params = self._where_sql(filters)
        params = list(where_params)
        # Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2b.4/D-3 (4):
        # `cursor_values`, when given, is already count/type-checked and
        # index-aligned with `order_by` (`cell.ApplicationCell.read_page`)
        # -- the keyset predicate is AND-ed onto the caller's own WHERE
        # clause, replacing the old OFFSET.
        if cursor_values is not None:
            keyset_sql, keyset_params = _keyset_predicate_sql(order_by, cursor_values)
            where = (where + sql.SQL(" AND ") + keyset_sql) if filters else (sql.SQL(" WHERE ") + keyset_sql)
            params = params + keyset_params
        statement = statement + where
        # Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2a:
        # `_NULLS_SQL[direction]` explicitly pins NULL placement to
        # PostgreSQL's own default (asc -> NULLS LAST, desc -> NULLS
        # FIRST) rather than leaving it implicit, so the keyset
        # predicate's own NULL branch (`_keyset_predicate_sql`) always
        # agrees with the actual row order.
        if order_by is not None:
            # WP-3: `order_by` is always `None` or a non-empty LIST of
            # `(field, direction)` tuples now (`cell.py::_bind_order_by`),
            # multi-field sort included -- a pre-WP-3 single-field caller
            # already reaches this as a one-element list.
            #
            # M-4 (independent review, consistency fix): an unexpected
            # `direction` here used to raise a raw, untranslated `KeyError`
            # (this dict lookup runs BEFORE the `try/except psycopg.Error`
            # block below, so that block never saw it) -- never reachable
            # through `cell.py`'s own allowlist today, but the identical
            # defense-in-depth reasoning `backend_sqlite.py`'s own
            # `_DIRECTION_TOKENS` lookup now documents applies here too:
            # this backend's own SQL-composition step should fail with a
            # classified `errors.ValidationError`, not an uncaught
            # `KeyError`, regardless of what `cell.py` currently allows
            # through.
            try:
                terms = sql.SQL(", ").join(
                    sql.SQL("{} {} {}").format(sql.Identifier(field), _DIRECTION_SQL[direction], _NULLS_SQL[direction])
                    for field, direction in order_by
                )
            except KeyError as exc:
                # WP-3e rework T1 (追補2 M-1): same literal denial
                # `cell.ApplicationCell._bind_order_by` already carries
                # (`errors.details_vocabulary.enum`) -- this comment's own
                # "defense-in-depth" framing above describes an
                # UNREACHABLE-today re-implementation of that exact cell-
                # layer check, not a storage-layer translation with no
                # in-memory sibling, so it gets the same 4-key `details`
                # (no per-item index survives the generator above, so
                # `field` stays the non-indexed `order_by/direction`
                # position, same convention `identifiers.validate_
                # identifier`'s own module comment documents for a
                # position that cannot be pinned to one list index here).
                raise ValidationError(
                    "invalid order direction",
                    details=violation("enum", field="order_by/direction", declared_type="string"),
                ) from exc
            statement = statement + sql.SQL(" ORDER BY ") + terms
        statement = statement + sql.SQL(" LIMIT %s")
        params = params + [limit]
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement, params)
                columns_desc = [c.name for c in cur.description]
                rows = [dict(zip(columns_desc, row)) for row in cur.fetchall()]
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return rows

    def delete(self, collection, filters, audit_hook=None, *, deadline=None, scope):
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        # Phase 4 (design D-2, review M-6): same `commit()`-inside-`try` +
        # pre-commit-hook structure as `create_collection`/`add_field`
        # above -- `cell.ApplicationCell.delete` has already run this
        # request through `_validate_delete_confirmation` before this is
        # ever called, so every call here is confirmed-destructive and
        # therefore unconditionally fail-closed class (D-2 item 1).
        hook_fired = False
        try:
            with scope.main.cursor() as cur:
                _execute(cur, statement, params)
                deleted = cur.rowcount
            if audit_hook is not None:
                audit_hook.pre_commit()
                hook_fired = True
            scope.main.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            scope.main.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            scope.main.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            scope.main.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            if isinstance(exc, _TRANSIENT_ERRORS):
                raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            scope.main.rollback()
            raise
        return {"deleted": deleted}

    # ------------------------------------------------------------------
    # execution_ms: a real `SET LOCAL statement_timeout`/`lock_timeout`,
    # computed from the residual budget `cell.ApplicationCell._limit_gate`'s
    # own wall-clock `deadline` still has left and set once per connection
    # when the request's scope opens (`request_scope`); r2db
    # `postgres.py::_timeout_ms`/`_set_timeouts` is the matching reference
    # realization (independent code, P-6).
    # ------------------------------------------------------------------

    def _timeout_ms(self, deadline):
        if deadline is None:
            return None
        remaining_ms = max(0.0, (deadline - time.monotonic()) * 1000)
        return max(1, int(remaining_ms))

    def _set_timeouts(self, cur, timeout_ms):
        """`SET LOCAL` (not session-wide `SET`): scoped to the current
        transaction only, automatically discarded on commit/rollback --
        never leaking onto the next transaction this connection serves.
        `timeout_ms` is always a server-computed `int` (from `_timeout_ms`
        above), never request content, so `sql.Literal` (necessary --
        PostgreSQL's `SET` grammar has no bind-placeholder position here)
        composes a trusted value, not untrusted text."""
        statement_timeout = sql.SQL("SET LOCAL statement_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        lock_timeout = sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        _execute(cur, statement_timeout)
        _execute(cur, lock_timeout)

    def begin(self, *, deadline=None, scope):
        """Nothing to open: the request's transaction on `scope.main` is
        open since the scope was entered, with its timeouts already set
        from the request's deadline."""

    def commit(self, *, scope):
        scope.main.commit()

    def rollback(self, *, scope):
        scope.main.rollback()

    # ------------------------------------------------------------------
    # Idempotency records, `public._mdb_idempotency` (per-application
    # upgrade 0010).
    #
    # A keyed request looks its key up, executes and stores its record on
    # its scope's main connection, inside ONE transaction. Two advisory
    # locks, both transaction-scoped and therefore released by the commit
    # or rollback that ends the request -- there is no separate release --
    # serialize what must not interleave: `idempotency_begin` takes the
    # key's lock first, so a second request for the same key waits until
    # the first has committed or rolled back and then finds its record (or
    # runs, when the first did not commit); `idempotency_reserve` takes the
    # application-wide capacity lock, so the count of retained records and
    # the write that follows it cannot interleave across different keys.
    # `cell.py`'s `_idempotency_check` is the only caller.
    # ------------------------------------------------------------------

    def _write_idempotency_row(self, conn, key, digest, response_json, now_ms):
        """Writes (or replaces) one record over `conn`'s OWN currently
        open transaction -- never commits/rolls back itself; the caller
        (either `record_idempotency` below, right before the scope's own
        commit, or a DDL method's own pre-commit point, right before its
        commit) owns that. `ON CONFLICT ... DO UPDATE`
        (not a bare `INSERT`) so a stale, not-yet-reaped row for this
        exact key (a benign race -- the caller already confirmed no
        ACTIVE record exists before reaching this point) is replaced
        rather than raising `UniqueViolation`."""
        statement = sql.SQL(
            "INSERT INTO {} (key, digest, response_json, created_at_ms) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET digest = EXCLUDED.digest, "
            "response_json = EXCLUDED.response_json, created_at_ms = EXCLUDED.created_at_ms"
        ).format(sql.Identifier(_IDEMPOTENCY_TABLE))
        with conn.cursor() as cur:
            _execute(cur, statement, [key, digest, response_json, now_ms])

    def idempotency_begin(self, key, now_ms, retention_ms, *, scope):
        """Takes `key`'s advisory lock, reaps expired records, then looks
        `key` up, all on `scope.main` inside the request's transaction.
        How long the lock wait may last is the scope's `lock_timeout`; a
        wait that outlasts it is `ResourceLimitError(execution_ms)`.

        The lock key: two-int form (`_IDEMPOTENCY_KEY_LOCK_NAMESPACE`,
        `hashtext(key)`), not a bare `hashtext(key)::bigint` -- `hashtext`
        alone is only a 32-bit hash, so a bare-bigint lock would crowd
        every key's lock into the SAME narrow space `_IDEMPOTENCY_
        COUNT_ADVISORY_LOCK_KEY`/`ops.py::_RITUAL_ADVISORY_LOCK_KEY`
        also occupy; namespacing the high 32 bits keeps per-key locks
        visibly separate (mirrors `r2db-api`'s own identical reasoning).
        A `hashtext` collision between two DIFFERENT keys only over-
        serializes (accepted) -- it can never under-serialize. The DB
        is per-Application, so the raw key alone is Application-scoped
        already (I-5) -- no extra scoping component is needed.

        Returns `{"digest": str, "response_json": str}` for `key`, or
        `None` if this Application has no (unexpired) record for it."""
        self._acquire_advisory(scope, _KEY_LOCK_STATEMENTS, [_IDEMPOTENCY_KEY_LOCK_NAMESPACE, key], count=False)
        try:
            with scope.main.cursor() as cur:
                _execute(cur, sql.SQL("DELETE FROM {} WHERE %s - created_at_ms > %s")
                          .format(sql.Identifier(_IDEMPOTENCY_TABLE)), [now_ms, retention_ms])
                _execute(cur, sql.SQL("SELECT digest, response_json FROM {} WHERE key = %s")
                          .format(sql.Identifier(_IDEMPOTENCY_TABLE)), [key])
                row = cur.fetchone()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            # A bounded wait for a same-key advisory lock that expires
            # surfaces as a real, classified `LIMIT_EXCEEDED` refusal,
            # never an unbounded hang -- the same mapping every other
            # lock/statement-timeout site on this backend uses.
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        if row is None:
            return None
        digest, response_json = row
        return {"digest": digest, "response_json": response_json}

    def idempotency_reserve(self, *, scope):
        """Takes the application-wide advisory lock that serializes this
        COUNT-then-write across DIFFERENT keys (D-5 (iii)), then returns
        the number of records this Application retains. Same scope
        connection and transaction as `idempotency_begin`'s.

        `LOCK TABLE public.{_IDEMPOTENCY_TABLE} IN SHARE MODE` was
        considered and rejected for this purpose: two concurrent SHARE
        holders never conflict with EACH OTHER (SHARE only conflicts
        with ROW EXCLUSIVE and stronger), so both would pass the COUNT
        and only then deadlock against each other's own subsequent
        INSERT (which needs ROW EXCLUSIVE). An advisory lock has no
        such self-conflict-free class: a second holder of the SAME key
        always waits for the first."""
        self._acquire_advisory(
            scope, _COUNT_LOCK_STATEMENTS, [_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY], count=False)
        try:
            with scope.main.cursor() as cur:
                _execute(cur, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(_IDEMPOTENCY_TABLE)))
                (count,) = cur.fetchone()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except _TRANSIENT_ERRORS as exc:
            raise StorageTransientError("the storage backend could not serve this request, retry it") from exc
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return count

    def record_idempotency(self, key, digest, response_json, now_ms, *, scope):
        """`ApplicationCell.transact`'s own single-batch write path --
        called directly, immediately before the scope's commit
        (the SAME connection/transaction the batch's own `..._in_
        transaction` DML calls already ran on, I-1); a failed batch never
        reaches this line (the caller's own execution loop raises first,
        never calling this method), so this write and the batch's own
        commit share the identical fate."""
        self._write_idempotency_row(scope.main, key, digest, response_json, now_ms)

    def idempotency_discard_pending(self, key):
        """Phase 9 WP-3cd closure (K-5, N-8): a real no-op HERE -- unlike
        `SQLiteBackend`'s own private, non-transactional dict, this
        backend's `record_idempotency` above writes to the SAME real
        PostgreSQL connection/transaction `self.commit()`/`self.rollback
        ()` already govern, so a `self.commit()` failure's own `self.
        rollback()` already undoes the row this method would otherwise
        need to discard -- there is nothing left pending to clean up by
        the time `ApplicationCell.transact`'s `except Exception:` handler
        reaches this call. Declared (not simply inherited/omitted) so a
        future reader sees this backend was considered, not skipped."""
        return None
