"""Bounded connection pool for the platform registry (WP-3 completion
condition, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-8
future-work ledger / WP-2 review N-1):

WP-2 deliberately made `PostgresCredentialStore` open a brand-new
connection on every single call ("fail-closed の一様観測" -- see that
module's own top-of-file docstring). That is fine for a test harness or a
low-traffic in-process adapter, but the HTTP application-plane process
calls `assert_active`/`authenticate` on every single incoming request --
one fresh TCP+auth handshake per request against `mitatedbsvc_api`, whose
own `CONNECTION LIMIT 20` (migration `0002_registry_and_functions.sql`)
a handful of concurrent requests can exhaust outright, at which point every
further request fails closed with `AUTH_STATE_UNAVAILABLE` even though the
service itself is healthy. This module is the fix: a small, bounded,
thread-safe connection pool the HTTP composition root constructs once and
hands to `PostgresCredentialStore`, so the platform-registry connection
count this process holds open is capped at `max_size` regardless of how
many concurrent requests are in flight.

This is NOT a general-purpose connection pool (no reaping thread or timer,
no health-check ping loop) -- it is scoped exactly to what its callers'
short-statement workloads need: reuse a recently-used, still-open
connection where possible, create a new one under the configured cap
otherwise, and fail closed (never fail open) when the cap is exhausted and
no connection is returned in time. The pool raises its own neutral
exceptions (`PoolError` and the two classes under it); each caller maps
them to its own error type. A connection
that sat idle longer than `IDLE_PING_THRESHOLD_S` is checked with one
round trip before it is handed out (`BoundedConnectionPool._ping`), so a
server-side end of a long-idle session (a database restart, a failover, an
idle disconnect on the route) is found by the pool and not by the caller's
own first statement; a connection returned within the threshold is handed
out unchecked, so a pool under load adds no round trip. Consistent
with this whole package's own "no code sharing between peers" principle
(R-2's closing paragraph): this is an independent implementation, not a
port of any pooling library or of r2db-api's own pooling module.
"""
from __future__ import annotations

import queue
import threading
import time
import weakref
from typing import Optional

import psycopg

# R-79 (WO §2.1 D-1): the counting cursor/connection subclasses `_new_
# connection` (below) uses instead of plain `psycopg.connect` --
# byte-identical to `r2db_api.psycopg_counting` (a same-named test in
# `tests/` pins the sha256 match).
from .psycopg_counting import CountingConnection

# mitatedbsvc_api's own CONNECTION LIMIT (migration
# 0002_registry_and_functions.sql) -- the composition root's own default
# should sit at or below this so this pool alone can never be the sole
# cause of that server-side limit being exceeded (a real deployment may
# still run other connections against the same role from other processes,
# but this default keeps a single process' own contribution bounded to
# exactly the server-side grant).
DEFAULT_MAX_SIZE = 20

# A connection idle in the pool for longer than this many seconds is
# checked with one round trip (`BoundedConnectionPool._ping`) before it is
# handed out again; one returned within this window is not.
IDLE_PING_THRESHOLD_S = 1.0

# A connection idle in its pool for longer than this many seconds is closed
# by the next `acquire()` of any pool in this process
# (`BoundedConnectionPool._close_stale_idle_in_every_pool`).
IDLE_CLOSE_THRESHOLD_S = 300.0

# The process-wide sweep of idle connections runs at most once per this many
# seconds, however many `acquire()` calls arrive meanwhile.
_IDLE_SWEEP_MIN_INTERVAL_S = 1.0

# Every `BoundedConnectionPool` this process creates, held weakly. The set is
# read only by the idle sweep above; nothing looks a pool up in it, so it is
# not a path from one application's request to another application's pool.
_live_pools: "weakref.WeakSet[BoundedConnectionPool]" = weakref.WeakSet()
_registry_lock = threading.Lock()
# `time.monotonic()` of the last sweep that started, `None` before the first.
_last_sweep_monotonic: Optional[float] = None


class PoolError(Exception):
    """Base of the exceptions `BoundedConnectionPool.acquire` raises. It is
    deliberately not a `FoundationError`: the pool knows nothing of the
    error vocabulary of the code that borrows from it, and each borrower
    maps these to its own error type."""


class PoolExhausted(PoolError):
    """The pool is at `max_size` and no connection was returned within the
    wait limit of this `acquire()` call."""


class PoolConnectFailed(PoolError):
    """Opening a new connection raised `psycopg.Error`; the original error
    is the `__cause__`."""


# design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-4: the
# `application_name` every PostgreSQL connection this process opens
# carries, process-wide. `None` (the default -- this repository's own
# tests and every conformance adapter never set it) omits the parameter
# entirely, leaving libpq's own default (`""`) untouched.
# `mitatedb_api.main.build_app`/`mitatedb_api.control_main.build_control_
# app` each set this ONCE, near the top, to `"MitateDB-api:data:<pid>"`/
# `"MitateDB-api:control:<pid>"` -- every connection factory in this
# package (this module's own `_new_connection`, `backend_postgres.
# PostgresBackend`'s two persistent connections, the credential stores,
# the audit sinks and readers, the control-plane stores) spreads
# `_application_name_connect_kwargs()` into its own `connect(...)` call,
# so every connection this SAME process opens afterward carries that one
# value without a constructor-parameter change at each call site. A real
# deployment's data/control planes are always two separate OS processes,
# so this process-wide value is never ambiguous between the two.
_connection_application_name: str | None = None


def set_connection_application_name(name: str | None) -> None:
    """Sets (or clears, with `None`) the `application_name` every
    connection this package opens from now on carries -- see the module-
    level comment above. Every real caller (`main.py`/`control_main.py`)
    calls this exactly once, at composition-root startup, before any
    request-serving thread exists."""
    global _connection_application_name
    _connection_application_name = name


def _application_name_connect_kwargs() -> dict[str, str]:
    """`{"application_name": ...}` when `set_connection_application_name`
    has been called with a non-`None` value, `{}` otherwise -- spread into
    a `psycopg.connect(...)`/`CountingConnection.connect(...)` call so an
    unset value omits the keyword argument entirely (never passes
    `application_name=None`)."""
    if _connection_application_name is None:
        return {}
    return {"application_name": _connection_application_name}


class BoundedConnectionPool:
    """Bounded, thread-safe pool of `psycopg.Connection` objects against one
    fixed DSN. `acquire()`/`release()`/`discard()` are the only mutating
    operations; `closeall()` releases every idle connection (used at
    process shutdown).

    Fail-closed (R-6/WP-2 discipline, extended here to pool exhaustion
    too): `acquire()` never blocks forever and never manufactures a
    connection past `max_size` -- it raises `PoolExhausted` (a wait past
    the limit) or `PoolConnectFailed` (a connection that could not be
    opened), both under `PoolError`, rather than let a caller wait
    indefinitely or silently bypass the cap.

    `release()` rolls back whatever transaction a connection still has
    open before it goes back to the idle queue, and discards a connection
    whose rollback fails, so no transaction and no session setting made
    inside one survives into the next borrower. A connection that stays
    idle longer than `IDLE_CLOSE_THRESHOLD_S` is closed by an `acquire()`
    of any pool in this process.
    """

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = DEFAULT_MAX_SIZE,
        connect_timeout: int = 5,
        acquire_timeout: float = 5.0,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._acquire_timeout = acquire_timeout
        self._max_size = max_size
        self._lock = threading.Lock()
        # LIFO: a recently-returned (and therefore most likely still warm/
        # alive) connection is reused before an older idle one -- purely a
        # locality heuristic, not a correctness requirement.
        self._idle: "queue.LifoQueue[psycopg.Connection]" = queue.LifoQueue()
        self._created = 0
        # R-78 acquisition statistics: counted under `self._stats_lock`, a
        # lock dedicated to this bookkeeping and never shared with `self.
        # _lock` above -- stage (1) of `acquire()` (reusing an idle,
        # still-open connection) takes no lock at all today, and this
        # statistics addition does not change that.
        self._stats_lock = threading.Lock()
        self._acquire_count = 0
        self._wait_count = 0
        self._wait_total_ms = 0.0
        self._wait_max_ms = 0.0
        self._in_use = 0
        self._in_use_peak = 0
        # Platform DB-time accounting, under the same `self._stats_lock`
        # as the acquisition counters above -- `_sessions`/`_connect_wall_
        # ms` rise once per `_new_connection()` call (below), and `_closed_
        # db_wall_ms`/`_closed_txn_count`/`_closed_db_calls` receive a
        # connection's own `CountingConnection.db_wall_ms`/`txn_count`/
        # `execute_count + executemany_count` folded in right before that
        # connection is discarded (`discard`, `closeall`, and the dead-
        # connection branches of `acquire()`) -- so a discarded
        # connection's own totals are never lost, only moved from "on the
        # connection" to "on this pool". Same shape as `r2db_api.postgres.
        # _RolePool`'s identical accounting.
        self._connect_wall_ms = 0.0
        self._sessions = 0
        self._closed_db_wall_ms = 0.0
        self._closed_txn_count = 0
        self._closed_db_calls = 0
        with _registry_lock:
            _live_pools.add(self)

    def _record_acquire(self) -> None:
        """Count one successful acquisition under `self._stats_lock`: `acquire_count` rises by one, `in_use` rises by one, and `in_use_peak` keeps the highest value `in_use` ever reaches."""
        with self._stats_lock:
            self._acquire_count += 1
            self._in_use += 1
            if self._in_use > self._in_use_peak:
                self._in_use_peak = self._in_use

    def _record_wait(self, waited_ms: float) -> None:
        """Count one entry into stage (3) of `acquire()` (the deadline loop reached only when the pool is at `max_size`), whether it ends in a reused connection or in `PoolExhausted`. `wait_max_ms` keeps the highest single wait observed."""
        with self._stats_lock:
            self._wait_count += 1
            self._wait_total_ms += waited_ms
            if waited_ms > self._wait_max_ms:
                self._wait_max_ms = waited_ms

    def _record_release(self) -> None:
        """Count one connection returning from checked-out (`in_use`) back to available, under `self._stats_lock`. Called once per `release()`/`discard()` call -- the two ways a connection this pool handed out comes back."""
        with self._stats_lock:
            self._in_use = max(0, self._in_use - 1)

    def stats(self) -> dict[str, int | float]:
        """Return this pool's acquisition statistics as a plain dict with exactly six keys: `size` (this pool's `max_size`), `acquire_count`, `wait_count`, `wait_total_ms`, `wait_max_ms`, `in_use_peak`. Read under `self._stats_lock`; never touches `self._lock` or the idle queue itself."""
        with self._stats_lock:
            return {
                "size": self._max_size,
                "acquire_count": self._acquire_count,
                "wait_count": self._wait_count,
                "wait_total_ms": self._wait_total_ms,
                "wait_max_ms": self._wait_max_ms,
                "in_use_peak": self._in_use_peak,
            }

    def _new_connection(self) -> "psycopg.Connection":
        # R-79 (WO §2.1 D-1): `CountingConnection.connect` in place of
        # plain `psycopg.connect` -- same classmethod, same signature
        # (`psycopg.connect` is itself `Connection.connect`, `psycopg/
        # __init__.py`), the only difference is every connection this pool
        # ever hands out now carries its own `execute_count`/`executemany_
        # count` and a `CountingCursor` factory.
        #
        # The connect call itself is timed into `_connect_wall_ms`/
        # `_sessions` under `self._stats_lock`, mirroring `r2db_api.
        # postgres._RolePool._connect`. A failed connect raises before
        # either counter is touched.
        connect_start = time.monotonic()
        conn = CountingConnection.connect(
            self._dsn, connect_timeout=self._connect_timeout, autocommit=False,
            **_application_name_connect_kwargs(),
        )
        connect_wall_ms = (time.monotonic() - connect_start) * 1000.0
        with self._stats_lock:
            self._sessions += 1
            self._connect_wall_ms += connect_wall_ms
        return conn

    def _fold_closed_connection_stats(self, conn: "psycopg.Connection") -> None:
        """Called right before every connection this pool discards leaves
        this pool for good (`discard`, `closeall`, and the dead-connection
        branches of `acquire()` below): adds this one connection's own
        `db_wall_ms`/`txn_count`/`execute_count + executemany_count` (from
        `psycopg_counting.CountingConnection`) into this pool's own running
        totals, under `self._stats_lock`, so discarding a connection never
        loses time, transactions, or statements it already spent. Same
        shape as `r2db_api.postgres._RolePool._fold_closed_connection_
        stats`."""
        db_wall_ms = getattr(conn, "db_wall_ms", 0.0)
        txn_count = getattr(conn, "txn_count", 0)
        db_calls = getattr(conn, "execute_count", 0) + getattr(conn, "executemany_count", 0)
        with self._stats_lock:
            self._closed_db_wall_ms += db_wall_ms
            self._closed_txn_count += txn_count
            self._closed_db_calls += db_calls

    def platform_stats(self) -> dict[str, int | float]:
        """Read-only sum of this pool's own DB-time accounting: every
        connection currently idle in `self._idle` (drained via `get_
        nowait` and put back with `put_nowait`, never through `acquire()`,
        so `acquire_count` above stays untouched) plus the running totals
        `_fold_closed_connection_stats`/`_new_connection` already folded in
        for connections that are now discarded. A connection some other
        caller currently has checked out is not in the idle queue right
        now, so its own not-yet-discarded `db_wall_ms`/`txn_count`/
        `db_calls` are not yet visible here -- they land in this method's
        next call, once that connection is released or discarded. No DB
        round trip: every value read here is a plain Python attribute."""
        conns: "list[psycopg.Connection]" = []
        live_db_wall_ms = 0.0
        live_txn_count = 0
        live_db_calls = 0
        while True:
            try:
                conns.append(self._idle.get_nowait())
            except queue.Empty:
                break
        for conn in conns:
            live_db_wall_ms += getattr(conn, "db_wall_ms", 0.0)
            live_txn_count += getattr(conn, "txn_count", 0)
            live_db_calls += getattr(conn, "execute_count", 0) + getattr(conn, "executemany_count", 0)
            self._idle.put_nowait(conn)
        with self._stats_lock:
            return {
                "sessions": self._sessions,
                "connect_wall_ms": self._connect_wall_ms,
                "db_wall_ms": live_db_wall_ms + self._closed_db_wall_ms,
                "txn_count": live_txn_count + self._closed_txn_count,
                "db_calls": live_db_calls + self._closed_db_calls,
            }

    def _forget_one(self) -> None:
        with self._lock:
            self._created = max(0, self._created - 1)

    def _ping(self, conn: "psycopg.Connection") -> bool:
        """One round trip on an idle connection: a plain `SELECT 1` sent
        through libpq directly, outside any transaction (the connection is
        idle here, and psycopg opens its own transaction only lazily before
        a statement of its own), so the connection goes back out neither
        inside a transaction nor with a statement counted in its own
        `execute_count`. `True` only when the server answered with a
        result; any error, or a connection that psycopg now reports as
        closed, is `False`."""
        try:
            result = conn.pgconn.exec_(b"SELECT 1")
        except Exception:
            return False
        return result.status == psycopg.pq.ExecStatus.TUPLES_OK and not conn.closed

    def _is_dead(self, conn: "psycopg.Connection") -> bool:
        """`True` when `conn` must not be handed out: psycopg already knows
        it is closed, or it sat idle in this pool longer than
        `IDLE_PING_THRESHOLD_S` (measured from its last `release()`) and the
        `_ping` round trip failed. A connection with no release time (one
        this pool never saw returned) and one returned within the threshold
        are not pinged."""
        if conn.closed:
            return True
        returned_at = getattr(conn, "_pool_returned_at", None)
        if returned_at is None or time.monotonic() - returned_at <= IDLE_PING_THRESHOLD_S:
            return False
        if self._ping(conn):
            return False
        try:
            conn.close()
        except psycopg.Error:
            pass
        return True

    def _close_stale_idle(self, now: float) -> None:
        """Close and forget every idle connection of this pool whose last
        `release()` was more than `IDLE_CLOSE_THRESHOLD_S` seconds before
        `now` (a `time.monotonic()` reading), folding its statistics first.
        Only connections in the idle queue are examined, so a connection
        a caller has checked out is never touched. The idle queue is
        drained and the fresh connections put back in their former order
        (oldest first), so the LIFO order is unchanged."""
        drained: "list[psycopg.Connection]" = []
        while True:
            try:
                drained.append(self._idle.get_nowait())
            except queue.Empty:
                break
        stale: "list[psycopg.Connection]" = []
        kept: "list[psycopg.Connection]" = []
        for conn in drained:
            returned_at = getattr(conn, "_pool_returned_at", None)
            if returned_at is not None and now - returned_at > IDLE_CLOSE_THRESHOLD_S:
                stale.append(conn)
            else:
                kept.append(conn)
        for conn in reversed(kept):
            self._idle.put_nowait(conn)
        for conn in stale:
            self._fold_closed_connection_stats(conn)
            try:
                conn.close()
            except psycopg.Error:
                pass
            self._forget_one()

    def _close_stale_idle_in_every_pool(self) -> None:
        """Called at the top of every `acquire()`: closes the connections
        that stayed idle past `IDLE_CLOSE_THRESHOLD_S` in every pool this
        process holds (`_live_pools`), not only this one, so the
        connections of an application that stopped receiving requests are
        released by requests to any other. The sweep starts at most once
        per `_IDLE_SWEEP_MIN_INTERVAL_S` in the whole process; a call
        inside that interval returns at once. No thread or timer drives
        it: a process that receives no request sweeps nothing."""
        global _last_sweep_monotonic
        now = time.monotonic()
        with _registry_lock:
            if _last_sweep_monotonic is not None and now - _last_sweep_monotonic < _IDLE_SWEEP_MIN_INTERVAL_S:
                return
            _last_sweep_monotonic = now
            pools = list(_live_pools)
        for pool in pools:
            pool._close_stale_idle(now)  # noqa: SLF001 -- same class

    def acquire(self, timeout: Optional[float] = None) -> "psycopg.Connection":
        """Return a connection, reusing an idle one when possible.

        `timeout` is how many seconds this call waits for a returned
        connection when the pool is at `max_size`; `None` uses the
        `acquire_timeout` the pool was constructed with.

        Fail-closed on both real failure modes: a connection attempt that
        raises (`psycopg.Error`) raises `PoolConnectFailed`, and a pool
        that is at `max_size` with no connection returned within the wait
        limit raises `PoolExhausted` -- never a raw driver exception, and
        never an indefinite hang.
        """
        self._close_stale_idle_in_every_pool()
        wait_limit = self._acquire_timeout if timeout is None else timeout
        # 1) Reuse an idle connection, discarding any that turned out to be
        # dead (closed by the server, or left in an unrecoverable state) in
        # the meantime -- one that sat idle past `IDLE_PING_THRESHOLD_S` is
        # asked with one round trip first (`_is_dead`).
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                break
            if self._is_dead(conn):
                self._fold_closed_connection_stats(conn)
                self._forget_one()
                continue
            self._record_acquire()
            return conn

        # 2) Create a new one, if under budget.
        with self._lock:
            if self._created < self._max_size:
                self._created += 1
                under_budget = True
            else:
                under_budget = False
        if under_budget:
            try:
                conn = self._new_connection()
            except psycopg.Error as exc:
                self._forget_one()
                raise PoolConnectFailed("connection to the database could not be opened") from exc
            self._record_acquire()
            return conn

        # 3) At budget: wait briefly for a released connection rather than
        # manufacturing one past the cap or blocking forever.
        wait_start = time.monotonic()
        deadline = wait_start + wait_limit
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._record_wait((time.monotonic() - wait_start) * 1000.0)
                raise PoolExhausted("connection pool exhausted (max_size reached)")
            try:
                conn = self._idle.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if self._is_dead(conn):
                self._fold_closed_connection_stats(conn)
                self._forget_one()
                continue
            self._record_wait((time.monotonic() - wait_start) * 1000.0)
            self._record_acquire()
            return conn

    def release(self, conn: "psycopg.Connection") -> None:
        """Return a connection to the idle pool. A connection that still
        has a transaction open (or is in an error state) is rolled back
        first, which also reverts any `SET` made inside that transaction;
        one whose rollback raises is discarded instead of returned. A
        connection with no transaction open is returned without a round
        trip."""
        if conn.closed:
            self._record_release()
            self._forget_one()
            return
        try:
            if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                conn.rollback()
        except Exception:
            self.discard(conn)
            return
        self._record_release()
        conn._pool_returned_at = time.monotonic()  # noqa: SLF001 -- read back by `_is_dead`
        self._idle.put(conn)

    def discard(self, conn: "psycopg.Connection") -> None:
        """Close and forget a connection that must never be reused."""
        self._record_release()
        self._fold_closed_connection_stats(conn)
        try:
            conn.close()
        except psycopg.Error:
            pass
        self._forget_one()

    def closeall(self) -> None:
        """Close every currently-idle connection. Used at process shutdown
        (a checked-out connection closes itself independently, e.g. via a
        request that never returned it -- this only reaches idle ones)."""
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                break
            self._fold_closed_connection_stats(conn)
            try:
                conn.close()
            except psycopg.Error:
                pass
            self._forget_one()


def pool_size_from_env(value: Optional[str], *, default: int = DEFAULT_MAX_SIZE) -> int:
    """Parse an optional pool-size environment variable, degrading to
    `default` on anything unset/unparsable/non-positive -- the same
    lenient-degrade discipline `config.FoundationConfig.from_env` uses for
    every OTHER tuning knob it reads, applied here for the one new knob
    this module introduces."""
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
