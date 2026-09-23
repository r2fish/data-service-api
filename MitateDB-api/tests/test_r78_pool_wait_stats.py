r"""r78 pool/lock wait statistics -- `mitatedb_api.pool.
BoundedConnectionPool`'s and `mitatedb_api.cell.ApplicationCell`'s new
acquisition/wait counters (design D-1,
docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md WP-1
completion conditions 5, 6, 11).

No real PostgreSQL: `BoundedConnectionPool` here uses the same fake-
connection substitution `test_threadpool_offload.py`'s own thread-safety
test already established (`pool._new_connection = ...`, a plain object
with `closed`/`close()`) -- this file is entirely about pool/lock
bookkeeping, never about a real connection's own behaviour.
`ApplicationCell` uses its default in-memory `SQLiteBackend`.

Run directly:
    ./.venv/bin/python -m pytest MitateDB-api/tests/test_r78_pool_wait_stats.py -q
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from mitatedb_api.cell import ApplicationCell, _CountingRLock
from mitatedb_api.errors import AuthorizationStateUnavailable
from mitatedb_api.pool import BoundedConnectionPool

_CONFORMANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "conformance")
if _CONFORMANCE_DIR not in sys.path:
    sys.path.insert(0, _CONFORMANCE_DIR)
import conformance_adapter_mitatedb_http as _http_module  # noqa: E402


class _FakeConnection:
    """Same shape `test_threadpool_offload.py`'s own thread-safety test
    substitutes for a real `psycopg.Connection` -- only `closed`/`close()`
    are ever touched by `BoundedConnectionPool` itself."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _fake_pool(max_size: int, acquire_timeout: float = 5.0) -> BoundedConnectionPool:
    pool = BoundedConnectionPool(
        "dsn-unused-fake-pool-r78-test.invalid", max_size=max_size, connect_timeout=1, acquire_timeout=acquire_timeout,
    )
    pool._new_connection = lambda: _FakeConnection()  # type: ignore[method-assign]  # noqa: SLF001
    return pool


def test_bounded_connection_pool_wait_stats_and_key_set():
    """Completion condition 5: `BoundedConnectionPool.stats()` carries the
    SAME six statistics names `r2db_api.postgres._RolePool.stats()` does;
    only stage (3) of `acquire()` (the deadline loop, entered only once
    `max_size` is exhausted) increments `wait_count`/`wait_total_ms`/
    `wait_max_ms` -- a second acquisition that genuinely has to wait for
    the first to release observes exactly one such wait.

    mutation M5 (`pool.py`): drop the `wait_count`/`wait_max_ms` update
    from stage (3) -- the `wait_count == 1` assertion below goes red (it
    stays 0)."""
    pool = _fake_pool(max_size=1, acquire_timeout=5.0)
    try:
        assert set(pool.stats().keys()) == {
            "size", "acquire_count", "wait_count", "wait_total_ms", "wait_max_ms", "in_use_peak",
        }

        held_ready = threading.Event()
        release_holder = threading.Event()

        def holder() -> None:
            conn = pool.acquire()
            held_ready.set()
            release_holder.wait(timeout=5)
            pool.release(conn)

        holder_thread = threading.Thread(target=holder)
        holder_thread.start()
        assert held_ready.wait(timeout=5)
        time.sleep(0.05)

        outcome: list[object] = []

        def waiter() -> None:
            try:
                outcome.append(pool.acquire())
            except BaseException as exc:  # noqa: BLE001 - captured for the main thread's own assertions
                outcome.append(exc)

        waiter_thread = threading.Thread(target=waiter)
        waiter_thread.start()
        time.sleep(0.2)
        release_holder.set()
        holder_thread.join(timeout=5)
        waiter_thread.join(timeout=5)
        assert len(outcome) == 1 and not isinstance(outcome[0], BaseException)

        stats = pool.stats()
        assert stats["wait_count"] == 1
        assert stats["wait_max_ms"] > 0.0
    finally:
        pool.closeall()


def test_bounded_connection_pool_wait_on_timeout_and_unavailable_message_unchanged():
    """Completion condition 5: the TIMEOUT path (stage (3)'s deadline
    elapsing with nothing returned) also counts as a wait, and
    `AuthorizationStateUnavailable`'s firing condition/message text stay
    exactly what they were before this WP (this WP only observes the wait
    around them, never changes them)."""
    pool = _fake_pool(max_size=1, acquire_timeout=0.2)
    try:
        held = pool.acquire()
        try:
            with pytest.raises(AuthorizationStateUnavailable) as excinfo:
                pool.acquire()
            assert str(excinfo.value) == "platform registry connection pool exhausted (max_size reached)"
            stats = pool.stats()
            assert stats["wait_count"] == 1
            assert stats["wait_max_ms"] > 0.0
        finally:
            pool.release(held)
    finally:
        pool.closeall()


def test_application_cell_lock_counts_waits_and_reentrant_acquisitions():
    """Completion condition 6: `ApplicationCell._lock`'s wrapper counts
    every acquisition (`lock_acquire_count`, including a single thread's
    own reentrant one) and only counts a WAIT when a different thread
    already holds the lock -- a single thread's own (possibly nested)
    acquisitions never increment `wait_count`.

    mutation M6 (`cell.py`): remove `_CountingRLock`'s non-blocking
    pre-check, always acquiring blocking with no wait measurement at all
    -- the two-thread `wait_count >= 1` assertion below goes red (it stays
    0 forever, since no wait is ever timed any more)."""
    cell = ApplicationCell("r78cell1")
    lock = cell._lock  # noqa: SLF001 - test-only reach-in, same convention this suite already uses for `_lock`/`_pool` internals

    # Single thread, reentrant: 2 acquisitions, 0 waits.
    with lock:
        with lock:
            pass
    solo_stats = lock.stats()
    assert solo_stats["lock_acquire_count"] == 2
    assert solo_stats["wait_count"] == 0

    # Two threads contend: the second genuinely waits for the first.
    ready = threading.Event()

    def holder() -> None:
        with lock:
            ready.set()
            time.sleep(0.3)

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert ready.wait(timeout=5)
    with lock:
        pass
    holder_thread.join(timeout=5)

    stats = lock.stats()
    assert stats["wait_count"] >= 1
    assert stats["wait_max_ms"] > 0.0


def test_counting_rlock_acquire_rejects_a_negative_timeout_like_bare_rlock():
    """Code review R-78 差し戻し 2 item 6(b): `_CountingRLock.acquire()`
    validates `timeout` upfront, exactly like bare `threading.RLock.
    acquire()` does -- a negative, non-`-1` `timeout` raises `ValueError`
    with the SAME message text, even on a completely free (uncontended)
    lock, where this class's own non-blocking probe would otherwise
    succeed and silently swallow the invalid argument.

    mutation (`cell.py`): drop the upfront `timeout != -1 and timeout < 0`
    check from `_CountingRLock.acquire` -- this test's `pytest.raises`
    goes unfulfilled (no exception at all, since the lock is free) and
    the test goes red."""
    lock = _CountingRLock()
    with pytest.raises(ValueError) as excinfo:
        lock.acquire(True, -2)
    assert str(excinfo.value) == "timeout value must be a non-negative number"


def test_http_and_socket_mitatedb_plugs_expose_pool_stats():
    """Extra assurance for completion condition 11 (no dedicated mutation
    of its own -- the mutation table's M10 already covers this same
    property on the r2db side): both the `-http` and `-socket` MitateDB
    conformance plugs expose `pool_stats()`, the socket plug inheriting it
    unchanged from the http class."""
    assert hasattr(_http_module.MitateDBHttpConformanceAdapter, "pool_stats")
    import conformance_adapter_mitatedb_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    assert _socket_module.MitateDBSocketConformanceAdapter.pool_stats is _http_module.MitateDBHttpConformanceAdapter.pool_stats
