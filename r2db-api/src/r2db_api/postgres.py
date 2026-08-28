"""`PostgresCell`: a `StorageBackend` (design D-1) over PostgreSQL via psycopg 3.

Design constraints this file is written to satisfy (design D-4):

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
- No method on this class -- public or private -- accepts a `str` and
  executes it. `_run`, the single choke point every statement passes
  through, is typed to accept only `psycopg.sql.Composed`/`psycopg.sql.SQL`
  and raises `TypeError` for anything else. This is a type-level property of
  the file, not a convention: every SQL fragment built anywhere below is
  constructed via `sql.SQL(...)`/`sql.Identifier`/`sql.Literal`/
  `sql.Placeholder`, never an f-string or `%`-formatted plain string.

This module does not duplicate validation. Identifier syntax, the operator
allowlist, mutation shape, and destructive-confirmation logic are imported
from `r2db_api.structured` and are the exact same functions `ApplicationCell`
uses -- see that module's "Shared validation/planning boundary" section.
This file only adds what is inherently PostgreSQL-specific: catalog lookup
against a live schema, SQL composition, session/transaction/timeout
handling, and per-role connection pooling.

Data model: every field declared via `create_entity`/`add_field` becomes a
`JSONB` column. The common contract's structured operations do not carry
per-field types (`SchemaOperationRequest.field_type` is accepted by the
schema but not by this foundation's own operation-shape allowlist), and the
in-memory reference cell stores arbitrary JSON-shaped Python values per
field with no static typing -- JSONB is the direct PostgreSQL analogue that
preserves that same dynamic-value semantics. One consequence worth noting
for callers: JSONB has a total, defined ordering across all JSON types, so
`lt`/`lte`/`gt`/`gte` comparisons that would raise `TypeError` against
mismatched Python types in `ApplicationCell` typically do not raise here;
they instead produce a deterministic (if occasionally surprising)
`ORDER`-consistent boolean. This is a legitimate cross-backend semantic
difference the Security Invariants explicitly allow (implementations are
not required to share a physical data model), not a validation gap: both
backends still reject bad identifiers/operators/shapes identically.
"""
from __future__ import annotations

import json
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

from .backend import StorageBackend as _StorageBackend
from .errors import fail
from .limits import ResourceLimits
from .structured import (
    MutationOutcome,
    Predicate,
    QueryOutcome,
    bind_mutation,
    bind_schema_operation,
    require_destructive_confirmation,
    validate_identifier,
    validate_predicates,
    validate_projection,
)

_REVISION_TABLE = "_r2db_schema_revision"

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

_COMPARISON_OPERATORS: dict[str, sql.SQL] = {
    "eq": sql.SQL("="),
    "ne": sql.SQL("<>"),
    "lt": sql.SQL("<"),
    "lte": sql.SQL("<="),
    "gt": sql.SQL(">"),
    "gte": sql.SQL(">="),
}


def _run(cursor: "psycopg.Cursor[Any]", statement: sql.Composed | sql.SQL, params: Sequence[Any] = ()) -> None:
    """The single execution choke point. Typed to accept only a composed
    psycopg SQL object -- never `str` -- so a raw string cannot reach the
    database from anywhere in this file, as a checked property rather than a
    convention (design D-4).
    """
    if not isinstance(statement, (sql.Composed, sql.SQL)):
        raise TypeError("PostgresCell only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, list(params))


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
        # Set by `retire()` (called only by `SharedPoolManager`, below, when
        # this pool is evicted -- idle timeout or LRU cap). A retired pool
        # keeps serving any connection a caller already checked out (see
        # `connection()`'s `finally` below), it simply never re-queues one on
        # return; the pool drains to zero connections and stops being handed
        # out for new acquisitions once every outstanding checkout returns.
        self._retired = False

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
        conn = psycopg.connect(self._dsn, autocommit=False, connect_timeout=self._connect_timeout)
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
        conn.commit()
        return conn

    def _acquire(self) -> "psycopg.Connection[Any]":
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            pass
        # Reserve a slot (increment `_created`) and release the lock
        # *before* calling `_connect()` -- a real, previously-shipped bug
        # this class had: `_connect()` used to run while `self._lock` was
        # held, so every thread contending for a new connection against an
        # unreachable target serialized on this lock for the full connect
        # attempt, and a failed `_connect()` never rolled its reservation
        # back. `maxconn` consecutive failures against an unreachable
        # target therefore permanently pinned `_created` at `maxconn`, so
        # every later `_acquire()` call fell straight through to the
        # untimed `self._queue.get()` below and blocked forever -- even
        # once the target became reachable again, since nothing ever put a
        # connection back on this empty queue. `r2db_api/tests/
        # test_postgres.py::test_role_pool_recovers_after_connect_failures_
        # are_exhausted_and_target_becomes_reachable` and
        # `test_credential_persistence.py::
        # test_authenticate_never_hangs_across_repeated_pool_exhaustion_and_
        # recovers_once_reachable` are the executable checks for this fix.
        reserved = False
        with self._lock:
            if self._created < self._maxconn:
                self._created += 1
                reserved = True
        if reserved:
            try:
                return self._connect()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise
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
            return self._queue.get(timeout=self._acquire_timeout)
        except queue.Empty:
            raise psycopg.OperationalError(
                f"timed out after {self._acquire_timeout}s waiting for an available pooled connection (pool exhausted at maxconn={self._maxconn})"
            )

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
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            # A `SELECT` inside `autocommit=False` opens a transaction; roll
            # it back immediately so the connection is handed to the caller
            # IDLE, exactly as `_connect()` leaves a freshly opened one --
            # the ping itself must be invisible to whatever runs next.
            conn.rollback()
            return True
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return False

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        conn = self._acquire()
        try:
            if conn.closed or not self._liveness_check(conn):
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
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._created = max(0, self._created - 1)

    def close_all(self) -> None:
        while True:
            try:
                conn = self._queue.get_nowait()
            except queue.Empty:
                break
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
    """Read an `int`-valued setting the way the rest of this package does
    (`R2DB_`-prefixed environment variables, e.g. `R2DB_CREDENTIAL_PEPPER`
    in `auth.py`) -- a bare `os.environ.get` rather than a `pydantic`
    settings object, since this package (unlike the SQLAlchemy-based
    reference implementation this design is adapted from) has no
    `Settings`/`get_settings()` of its own. An unset, empty, or unparsable
    value silently falls back to `default` rather than raising: these are
    pool-tuning knobs, not required configuration, and a malformed value at
    startup should degrade to a sane default, not crash the process.
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

    Design, adapted from the currently deployed reference implementation
    (`r2-vps/apps/r2db-api/src/r2db_api/pools.py::AppPoolManager`, a
    SQLAlchemy engine cache with the same two properties) to this package's
    hand-rolled psycopg pooling:

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
    it). `runtime_dsn`/`developer_dsn` are two separate, already
    fully-formed connection strings authenticating as this application's
    `runtime` and `developer` PostgreSQL roles respectively, each already
    naming this application's own database (provisioned by
    `r2db-api/migrations/`, see `r2db-api/docs/`); this class never embeds a
    control-plane credential and never widens a connection's role at
    runtime, so schema-changing operations physically execute under the
    `developer` role (DDL-capable on this database's `public` schema only)
    while queries and data mutations physically execute under the `runtime`
    role (DML only) -- a second, DB-enforced layer under the `developer:
    bool` check already performed by `bind_schema_operation` (SI-03
    defence in depth).

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
    """

    def __init__(self, application_id: str, schema: str, *, runtime_dsn: str, developer_dsn: str, runtime_role: str, developer_role: str, pool_size: int | None = None, pool_manager: SharedPoolManager | None = None) -> None:
        validate_identifier(schema)
        self.application_id = application_id
        self.schema = schema
        # Role *names* (not credentials) are needed at table-creation time to
        # embed the RLS policy (see `_create_entity`): D-3's third,
        # defence-in-depth layer, on top of schema separation and the two
        # distinct DB roles. They are control-plane-assigned constants, the
        # same trust level as `schema` above -- never taken from a client
        # request.
        validate_identifier(runtime_role)
        validate_identifier(developer_role)
        self._runtime_role = runtime_role
        self._developer_role = developer_role
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

    # ---- catalog -----------------------------------------------------

    def catalog(self) -> list[dict[str, Any]]:
        with self._runtime.connection() as conn:
            with conn.transaction():
                fields_by_entity = self._load_catalog(conn)
        return [{"entity": name, "fields": sorted(fields_by_entity[name])} for name in sorted(fields_by_entity)]

    def _load_catalog(self, conn: "psycopg.Connection[Any]") -> dict[str, set[str]]:
        """The catalog-verification step D-4 requires before any client
        identifier may be composed with `sql.Identifier`: this is the live
        set of tables/columns that actually exist in this application's
        schema right now, queried from `information_schema` (never from
        request content), inside the same transaction as the operation
        being validated.
        """
        statement = sql.SQL(
            "SELECT t.table_name, c.column_name "
            "FROM information_schema.tables t "
            "LEFT JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = {schema} AND t.table_type = 'BASE TABLE' AND t.table_name <> {revision_table}"
        ).format(schema=sql.Placeholder(), revision_table=sql.Placeholder())
        with conn.cursor() as cur:
            _run(cur, statement, [self.schema, _REVISION_TABLE])
            rows = cur.fetchall()
        result: dict[str, set[str]] = {}
        for table_name, column_name in rows:
            fields = result.setdefault(table_name, set())
            if column_name is not None:
                fields.add(column_name)
        return result

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
        validate_identifier(entity)
        if page_size <= 0:
            fail("LIMIT_EXCEEDED", "Page size must be positive.", status=413, details={"resource": "result_items", "limit": limits.result_items})
        if order_by is not None or cursor is not None:
            # CCR-13 (docs/design/R2DB_CCR13_STORAGE_V1.md WP-2 scope note):
            # this backend does not implement order_by/pagination yet
            # (WP-3) -- refuse rather than silently ignore either one.
            fail("CAPABILITY_UNSUPPORTED", "Result ordering and cursor pagination are not implemented by this backend yet.")
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    known_fields = catalog[entity]
                    validate_projection(select, known_fields)
                    validate_predicates(where, known_fields)
                    limits.check("query_complexity", len(where) + len(select))
                    where_sql, where_params = self._where_clause(where)
                    statement = self._select_statement(entity, select, where_sql, page_size)
                    with conn.cursor() as cur:
                        _run(cur, statement, where_params)
                        rows = cur.fetchall()
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        # CCR-13 shim (WP-2 scope note): full revisions/has_more/next_cursor
        # is WP-3 (needs the `_r2db_revision` column this backend does not
        # provision yet); wrap today's unchanged result in the new outcome
        # shape. `revisions=None` (not `[]`) -- WP-2 review M-10's
        # `QueryOutcome.__post_init__` invariant is "None (unmaintained) or
        # index-aligned with items", and an empty list would be wrong-length
        # the moment `rows` is non-empty.
        return QueryOutcome(items=[dict(zip(select, row)) for row in rows], revisions=None, has_more=False)

    def _select_statement(self, entity: str, select: list[str], where_sql: sql.Composed | None, page_size: int) -> sql.Composed:
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in select)
        statement = sql.SQL("SELECT {columns} FROM {table}").format(columns=columns, table=sql.Identifier(entity))
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
        return sql.SQL("{base} LIMIT {limit}").format(base=statement, limit=sql.Literal(int(page_size)))

    # ---- mutations -------------------------------------------------------

    def transact(self, entity: str, operations: list[dict[str, Any]], limits: ResourceLimits, *, deadline: float | None = None, clock: Callable[[], float] | None = None) -> MutationOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.")
        limits.check("batch_items", len(operations))
        affected = 0
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    known_fields = catalog[entity]
                    for operation in operations:
                        affected += self._apply(conn, entity, operation, known_fields)
                        limits.check("result_items", affected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # `conn.transaction()` rolls back the *entire* batch on any
        # exception (including a `FoundationError` raised by a later
        # operation), giving the whole batch one real database transaction
        # (D-5) in place of `ApplicationCell`'s in-memory deepcopy/restore.
        # CCR-13 shim (WP-2 scope note): resolved-insert addresses are WP-3
        # (needs the `id` identity column this backend does not provision
        # yet); wrap today's unchanged affected-count in the new outcome
        # shape. `assigned_addresses=None` (not `[]`) -- confirmation-review
        # fix (minor): `None` means "not maintained", symmetric with
        # `QueryOutcome.revisions`; `[]` would incorrectly claim this
        # backend tracks addresses and simply resolved none this batch.
        return MutationOutcome(affected=affected, assigned_addresses=None)

    def _apply(self, conn: "psycopg.Connection[Any]", entity: str, operation: dict[str, Any], known_fields: set[str]) -> int:
        bound = bind_mutation(operation, known_fields)
        # CCR-13 (docs/design/R2DB_CCR13_STORAGE_V1.md WP-2 scope note):
        # `bind_mutation` (the shared boundary) no longer rejects every
        # `upsert`/`expected_revision` outright -- whether either is
        # actually executable now depends on catalog knowledge
        # (declared uniqueness keys, a revision column) that only
        # `ApplicationCell` has as of this work package. This backend has
        # neither yet (both are WP-3), so it must reject them itself here,
        # explicitly, rather than falling through to the pre-CCR-13
        # "match on `where`, insert if none found" code below -- which
        # would otherwise become reachable again and silently reinstate
        # exactly the enabled-but-undefined-semantics gap CCR-13 closed.
        if bound.operation == "delete":
            # WP-2 review minor (f): destructive confirmation is checked
            # before the expected_revision gate below, for `delete`
            # specifically -- unifying error precedence with
            # `ApplicationCell` (R-4, corrigendum m-5: confirmation before
            # any precondition-related outcome, and here "not implemented"
            # is the precondition-adjacent outcome being checked against).
            require_destructive_confirmation(bound.destructive, bound.confirmation, "DELETE", "Delete requires explicit destructive confirmation.")
        if bound.expected_revision is not None:
            fail("CAPABILITY_UNSUPPORTED", "Revision preconditions are not implemented by this backend yet.")
        if bound.operation == "upsert":
            fail("CAPABILITY_UNSUPPORTED", "Upsert requires a declared domain uniqueness key, which this backend does not implement yet.")
        table = sql.Identifier(entity)
        if bound.operation == "insert":
            return self._insert(conn, table, bound.values)
        where_sql, where_params = self._where_clause(bound.where)
        if bound.operation == "delete":
            return self._delete(conn, table, where_sql, where_params)
        return self._update(conn, table, bound.values, where_sql, where_params)

    def _insert(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, values: dict[str, Any]) -> int:
        if not values:
            statement = sql.SQL("INSERT INTO {table} DEFAULT VALUES").format(table=table)
            params: list[Any] = []
        else:
            columns = sql.SQL(", ").join(sql.Identifier(key) for key in values)
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
            statement = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(table=table, columns=columns, placeholders=placeholders)
            # TODO(WP-3, R-7 addendum): a Python `None` here must bind as
            # SQL NULL, never as the JSON literal `jsonb 'null'` -- `Jsonb(
            # None)` currently produces the latter for an untyped column.
            # This has no observable effect while every column here is
            # JSONB (untyped, WP-2's only shape), but becomes load-bearing
            # once WP-3 adds typed columns/predicate type-checking, where
            # "no value" and "the JSON null value" must stay distinguishable.
            params = [Jsonb(v) for v in values.values()]
        with conn.cursor() as cur:
            _run(cur, statement, params)
        return 1

    def _update(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, values: dict[str, Any], where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        if not values:
            return self._count(conn, table, where_sql, where_params)
        assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(key), ph=sql.Placeholder()) for key in values)
        statement = sql.SQL("UPDATE {table} SET {assignments}").format(table=table, assignments=assignments)
        # TODO(WP-3, R-7 addendum): same SQL-NULL-vs-`jsonb 'null'` note as
        # `_insert` above.
        params = [Jsonb(v) for v in values.values()]
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = params + where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            return cur.rowcount

    def _delete(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        statement = sql.SQL("DELETE FROM {table}").format(table=table)
        params: list[Any] = []
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            return cur.rowcount

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

    # ---- predicate/WHERE composition ------------------------------------

    def _where_clause(self, where: list[Predicate]) -> tuple[sql.Composed | None, list[Any]]:
        if not where:
            return None, []
        fragments: list[sql.Composed] = []
        params: list[Any] = []
        for predicate in where:
            fragment, values = self._predicate_sql(predicate)
            fragments.append(fragment)
            params.extend(values)
        return sql.SQL(" AND ").join(fragments), params

    def _predicate_sql(self, predicate: Predicate) -> tuple[sql.Composed, list[Any]]:
        column = sql.Identifier(predicate.field)
        if predicate.operator == "is_null":
            return sql.SQL("{col} IS NULL").format(col=column), []
        if predicate.operator == "in":
            if not isinstance(predicate.value, list) or not predicate.value:
                fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in predicate.value)
            # TODO(WP-3, R-7 addendum): same SQL-NULL-vs-`jsonb 'null'` note
            # as `_insert` above, applied per element (m-7).
            return sql.SQL("{col} IN ({items})").format(col=column, items=placeholders), [Jsonb(v) for v in predicate.value]
        if predicate.operator == "contains":
            needle = predicate.value if isinstance(predicate.value, str) else _json_text(predicate.value)
            return sql.SQL("{col}::text LIKE {ph}").format(col=column, ph=sql.Placeholder()), [f"%{needle}%"]
        operator = _COMPARISON_OPERATORS.get(predicate.operator)
        if operator is None:
            # Unreachable in practice: `predicate.validate()` (called by
            # `validate_predicates`, upstream of every caller here) already
            # rejects any operator outside `structured.OPERATORS`. Kept as
            # an explicit, fixed-literal-only fallback rather than trusting
            # that invariant silently (D-4: "operators map to fixed
            # literals").
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details={"field": predicate.field})
        # TODO(WP-3, R-7 addendum): same SQL-NULL-vs-`jsonb 'null'` note as
        # `_insert` above.
        return sql.SQL("{col} {op} {ph}").format(col=column, op=operator, ph=sql.Placeholder()), [Jsonb(predicate.value)]

    # ---- schema ----------------------------------------------------------

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        bound = bind_schema_operation(operation, developer=developer)
        with self._developer.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    current_objects = sum(len(fields) + 1 for fields in catalog.values())
                    if bound.operation == "create_entity":
                        projected = current_objects + 1 + len(bound.fields)
                    elif bound.operation == "add_field":
                        projected = current_objects + 1
                    elif bound.operation == "drop_entity":
                        projected = current_objects - (len(catalog.get(bound.entity, set())) + 1)
                    else:  # create_index / drop_index: no table/column object accounted
                        projected = current_objects
                    limits.check("schema_objects", projected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    if bound.operation == "create_entity":
                        if bound.entity in catalog:
                            fail("CONFLICT", "Entity already exists.", status=409)
                        self._create_entity(conn, bound.entity, bound.fields)
                    elif bound.operation == "drop_entity":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        require_destructive_confirmation(bound.destructive, bound.confirmation, "DROP_ENTITY", "Drop requires explicit destructive confirmation.")
                        self._drop_entity(conn, bound.entity)
                    elif bound.operation == "add_field":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        if bound.field in catalog.get(bound.entity, set()):
                            fail("CONFLICT", "Field already exists.", status=409)
                        if bound.field_type is not None:
                            # CCR-13 (WP-2 scope note): typed columns are
                            # WP-3 (needs the type-map DDL this backend
                            # does not implement yet) -- refuse rather than
                            # silently create an untyped column and drop
                            # the caller's declared type on the floor.
                            fail("CAPABILITY_UNSUPPORTED", "Typed columns are not implemented by this backend yet.")
                        self._add_field(conn, bound.entity, bound.field)
                    else:  # create_index / drop_index
                        # CCR-13 (WP-2 scope note): index declarations are
                        # WP-3. Without this explicit branch, `create_index`/
                        # `drop_index` -- now structurally accepted by the
                        # shared `bind_schema_operation` boundary -- would
                        # fall through and be misdispatched as `add_field`.
                        fail("CAPABILITY_UNSUPPORTED", "Index declarations are not implemented by this backend yet.")
                    revision = self._bump_revision(conn)
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        return revision

    def _create_entity(self, conn: "psycopg.Connection[Any]", entity: str, fields: tuple[str, ...]) -> None:
        if fields:
            columns = sql.SQL(", ").join(sql.SQL("{col} JSONB").format(col=sql.Identifier(f)) for f in fields)
            statement = sql.SQL("CREATE TABLE {table} ({columns})").format(table=sql.Identifier(entity), columns=columns)
        else:
            statement = sql.SQL("CREATE TABLE {table} ()").format(table=sql.Identifier(entity))
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
        """D-3's third layer: RLS as defence-in-depth underneath the
        database boundary and the two distinct DB roles (architecture §8,
        "D-3 改訂": each application now owns its own PostgreSQL database,
        not merely its own schema inside one shared database -- the
        database boundary is the primary wall, since PostgreSQL admits no
        cross-database query path at all without FDW/dblink, which this
        deployment never grants). This policy's job is to survive a
        *future* misconfiguration of that primary wall -- e.g. an
        accidental broader `CONNECT` grant -- rather than to be the
        primary control itself. It restricts every row in every table this
        cell creates to being visible/writable only by this application's
        own two roles, checked by PostgreSQL itself via `current_user`, not
        by anything this Python process asserts about itself.
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
        process's memory of what it thinks it did. `_r2db_schema_revision`
        (provisioned by `migrations/0003_provision_application.sql`,
        already RLS-protected there) is excluded the same way
        `_load_catalog` excludes it from the application-visible catalog.
        Ordered so callers get a deterministic offender list.
        """
        statement = sql.SQL(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r' AND c.relname <> {revision_table} "
            "AND (c.relrowsecurity = false OR c.relforcerowsecurity = false) "
            "ORDER BY c.relname"
        ).format(revision_table=sql.Placeholder())
        _run(cur, statement, [_REVISION_TABLE])
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

    def _add_field(self, conn: "psycopg.Connection[Any]", entity: str, field: str) -> None:
        statement = sql.SQL("ALTER TABLE {table} ADD COLUMN {col} JSONB").format(table=sql.Identifier(entity), col=sql.Identifier(field))
        with conn.cursor() as cur:
            _run(cur, statement)

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
        """One request = one transaction (D-5): `statement_timeout` and
        `lock_timeout` are set with `SET LOCAL`, so they apply only to the
        current transaction and are automatically discarded on commit or
        rollback -- never leaking onto the next transaction this pooled
        connection is reused for. The timeout value passed here is always a
        server-computed `int` (derived from `ResourceLimits.execution_ms`
        and the caller's deadline, never from request content), so
        `sql.Literal` -- necessary because PostgreSQL's `SET` grammar does
        not accept a bind placeholder in this position -- is composing a
        trusted value, not interpolating untrusted text.
        """
        statement_timeout = sql.SQL("SET LOCAL statement_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        lock_timeout = sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        with conn.cursor() as cur:
            _run(cur, statement_timeout)
            _run(cur, lock_timeout)


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


# Checked, not just claimed: `PostgresCell` must present the exact same call
# surface as `ApplicationCell` (design D-1). See `backend.py` for the
# equivalent assertion covering `ApplicationCell`.
assert issubclass(PostgresCell, _StorageBackend), "PostgresCell must conform to StorageBackend (design D-1)"

__all__ = ["PostgresCell", "SharedPoolManager", "default_pool_manager"]
