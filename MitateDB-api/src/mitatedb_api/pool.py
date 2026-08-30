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

# mitatedbsvc_api's own CONNECTION LIMIT (migration
# 0002_registry_and_functions.sql) -- the composition root's own default
# should sit at or below this so this pool alone can never be the sole
# cause of that server-side limit being exceeded (a real deployment may
# still run other connections against the same role from other processes,
# but this default keeps a single process' own contribution bounded to
# exactly the server-side grant).
DEFAULT_MAX_SIZE = 20


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

    def _new_connection(self) -> "psycopg.Connection":
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False)

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
                self._forget_one()
                continue
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
                return self._new_connection()
            except psycopg.Error as exc:
                self._forget_one()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc

        # 3) At budget: wait briefly for a released connection rather than
        # manufacturing one past the cap or blocking forever.
        deadline = time.monotonic() + self._acquire_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AuthorizationStateUnavailable(
                    "platform registry connection pool exhausted (max_size reached)"
                )
            try:
                conn = self._idle.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if conn.closed:
                self._forget_one()
                continue
            return conn

    def release(self, conn: "psycopg.Connection") -> None:
        """Return a healthy connection to the idle pool."""
        if conn.closed:
            self._forget_one()
            return
        self._idle.put(conn)

    def discard(self, conn: "psycopg.Connection") -> None:
        """Close and forget a connection that must never be reused."""
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
