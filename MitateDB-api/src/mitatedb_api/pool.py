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

This is NOT a general-purpose connection pool (no idle reaping thread, no
health-check ping loop) -- it is scoped exactly to what the platform
registry's own read-heavy, short-statement workload needs: reuse a
recently-used, still-open connection where possible, create a new one
under the configured cap otherwise, and fail closed (never fail open) when
the cap is exhausted and no connection is returned in time. Consistent
with this whole package's own "no code sharing between peers" principle
(R-2's closing paragraph): this is an independent implementation, not a
port of any pooling library or of r2db-api's own pooling module.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional

import psycopg

from .errors import AuthorizationStateUnavailable
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
    connection past `max_size` -- it raises `AuthorizationStateUnavailable`
    (the same exception a direct connection failure already raises) rather
    than let a caller wait indefinitely or silently bypass the cap.
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

    def _record_acquire(self) -> None:
        """Count one successful acquisition under `self._stats_lock`: `acquire_count` rises by one, `in_use` rises by one, and `in_use_peak` keeps the highest value `in_use` ever reaches."""
        with self._stats_lock:
            self._acquire_count += 1
            self._in_use += 1
            if self._in_use > self._in_use_peak:
                self._in_use_peak = self._in_use

    def _record_wait(self, waited_ms: float) -> None:
        """Count one entry into stage (3) of `acquire()` (the deadline loop reached only when the pool is at `max_size`), whether it ends in a reused connection or in `AuthorizationStateUnavailable`. `wait_max_ms` keeps the highest single wait observed."""
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

    def acquire(self) -> "psycopg.Connection":
        """Return a connection, reusing an idle one when possible.

        Fail-closed on both real failure modes: a connection attempt that
        raises (`psycopg.Error`) and a pool that is at `max_size` with no
        connection returned within `acquire_timeout` both raise
        `AuthorizationStateUnavailable` -- never a raw driver exception,
        and never an indefinite hang.
        """
        # 1) Reuse an idle connection, discarding any that turned out to be
        # dead (closed by the server, or left in an unrecoverable state) in
        # the meantime.
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                break
            if conn.closed:
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
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
            self._record_acquire()
            return conn

        # 3) At budget: wait briefly for a released connection rather than
        # manufacturing one past the cap or blocking forever.
        wait_start = time.monotonic()
        deadline = wait_start + self._acquire_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._record_wait((time.monotonic() - wait_start) * 1000.0)
                raise AuthorizationStateUnavailable(
                    "platform registry connection pool exhausted (max_size reached)"
                )
            try:
                conn = self._idle.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if conn.closed:
                self._fold_closed_connection_stats(conn)
                self._forget_one()
                continue
            self._record_wait((time.monotonic() - wait_start) * 1000.0)
            self._record_acquire()
            return conn

    def release(self, conn: "psycopg.Connection") -> None:
        """Return a healthy connection to the idle pool."""
        self._record_release()
        if conn.closed:
            self._forget_one()
            return
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
