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

import asyncio
import contextlib
import os
import secrets
import sys
import threading
import time
from types import SimpleNamespace

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


# ---------------------------------------------------------------------
# R-101 WP-1 D-3 / WP-3 D-10: the `DSA_PERF_THREAD_LIMIT` env reader and
# the `-http` adapter's construction-time wiring of its effective value
# into `create_app(..., thread_limit=)` (mirrors r2db-api/tests/
# test_r78_pool_wait_stats.py's own identical section).
# ---------------------------------------------------------------------


def test_perf_thread_limit_value_reads_a_positive_integer(monkeypatch):
    """Completion condition 103/107: the env reader returns the parsed
    integer when `DSA_PERF_THREAD_LIMIT` is a positive integer."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "4")
    assert _http_module._perf_thread_limit_value() == 4


def test_perf_thread_limit_value_defaults_to_4_when_unset_empty_or_invalid(monkeypatch):
    """Completion conditions 103/155: unset, empty, non-numeric, zero, and
    negative all resolve to `DEFAULT_THREAD_LIMIT` (4) -- WP-3 (D-10)
    replaced WP-1's own `None` result with `create_app`'s own default.

    mutation M145 (`conformance_adapter_mitatedb_http.py`): make the env
    reader return `None` again when the env is absent -- this test's own
    first assertion (`== 4`) goes red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    assert _http_module._perf_thread_limit_value() == 4
    for raw in ("", "not-a-number", "0", "-3"):
        monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", raw)
        assert _http_module._perf_thread_limit_value() == 4, raw


def test_perf_thread_limit_accessor_reads_the_instance_attribute():
    """Completion condition 107: `perf_thread_limit()` returns whatever
    `self._perf_thread_limit` holds, bound to a lightweight stand-in.

    mutation M149 (`conformance_adapter_mitatedb_http.py`): make `perf_
    thread_limit` always return `DEFAULT_THREAD_LIMIT` regardless of
    `self._perf_thread_limit` -- this test's own `== 5` assertion goes
    red."""
    stand_in = SimpleNamespace(_perf_thread_limit=5)
    assert _http_module.MitateDBHttpConformanceAdapter.perf_thread_limit(stand_in) == 5
    stand_in_default = SimpleNamespace(_perf_thread_limit=4)
    assert _http_module.MitateDBHttpConformanceAdapter.perf_thread_limit(stand_in_default) == 4


# ---------------------------------------------------------------------
# R-101 WP-3 D-10: adapter construction-time wiring identity (completion
# conditions 103/105/107/109/155) and `platform_db_time_stats()` observed
# through a real, authenticated HTTP request (D-11, unaffected by this
# WP: the credential store still opens a per-call connection, no pool
# yet -- see the work order's own §8 scope note).
# ---------------------------------------------------------------------


def test_http_adapter_default_thread_limit_is_4_and_app_is_the_create_app_result(monkeypatch):
    """Completion conditions 103/109: constructing the `-http` adapter
    with `DSA_PERF_THREAD_LIMIT` absent reports `perf_thread_limit() ==
    4`, and `adapter._app` is exactly the object `create_app` returned --
    the SAME object the asgi client dials.

    mutation M151 (`conformance_adapter_mitatedb_http.py`): pass a
    SECOND, freshly built `create_app(...)` result to `self._build_client
    (...)` instead of the local `app` variable -- this test's own
    `client_app is adapter._app` assertion goes red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    try:
        assert adapter.perf_thread_limit() == 4
        client_app = adapter._client._transport.app  # noqa: SLF001 -- identity check only, no request sent
        assert client_app is adapter._app
    finally:
        adapter.close()


def test_http_adapter_thread_limit_env_overrides_and_sets_the_loop_limiter(monkeypatch):
    """Completion conditions 105/107 (code review 1 F2 shape): constructing
    the `-http` adapter with `DSA_PERF_THREAD_LIMIT=5` reports `perf_
    thread_limit() == 5`, and after sending one real request through it
    (`authenticate` -- a real `GET /v1/capabilities`), `adapter._loop`'s
    own default anyio thread limiter has actually been set to `5`.

    mutation M147 (`conformance_adapter_mitatedb_http.py`): pass
    `DEFAULT_THREAD_LIMIT` to `create_app` regardless of the env reader's
    own value -- this test's own `total_tokens == 5` assertion goes red
    (stays at `4`)."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "5")
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101perf{secrets.token_hex(4)}"
    try:
        assert adapter.perf_thread_limit() == 5
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        adapter.authenticate(handle)  # a real request, through create_app's own middleware

        async def _read_total_tokens() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert adapter._loop.run_until_complete(_read_total_tokens()) == 5
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
        adapter.close()


def test_http_adapter_thread_limit_env_invalid_falls_back_to_default(monkeypatch):
    """Completion condition 155: `DSA_PERF_THREAD_LIMIT=0` (invalid)
    resolves to `DEFAULT_THREAD_LIMIT` (4), both on the accessor and on
    the loop's own limiter after one real request.

    mutation M193 (`conformance_adapter_mitatedb_http.py`): have the env
    reader return `None` for an invalid value and pass that straight to
    `create_app` -- `create_app` then adds no middleware, so this test's
    own `total_tokens == 4` assertion goes red (stays at 40)."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "0")
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101perf{secrets.token_hex(4)}"
    try:
        assert adapter.perf_thread_limit() == 4
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        adapter.authenticate(handle)

        async def _read_total_tokens() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert adapter._loop.run_until_complete(_read_total_tokens()) == 4
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
        adapter.close()


def test_socket_adapter_shares_the_same_data_plane_app_identity():
    """Completion condition 109: the `-socket` adapter's own data-plane
    surface (`_socket_surface_for(adapter._app)`) is bound to the SAME
    app object `adapter._app` holds. Looks the surface up by
    `id(adapter._app)` in `adapter._socket_surfaces` itself, rather than
    calling `_socket_surface_for(adapter._app)` here, so a `KeyError`
    means `_build_client` (the ONLY other caller) ran with a different
    app object."""
    import conformance_adapter_mitatedb_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    adapter = _socket_module.MitateDBSocketConformanceAdapter()
    try:
        surface = adapter._socket_surfaces[id(adapter._app)]
        assert surface.app is adapter._app
        assert surface._started is False  # noqa: SLF001 -- no real server started by this test
    finally:
        adapter.close()


def test_platform_db_time_stats_observes_a_real_authenticated_http_request():
    """MitateDB side of completion conditions 22/23 (差し戻し 1 item 2;
    the work order's own §2.3 table names only r2db-api mutations for this
    pair -- this test and its own mutation, M99, are an addition the
    supervisor's return-file ruling directed): sending one real,
    authenticated HTTP request through the `-http` adapter (`authenticate
    ()` -- a real `GET /v1/capabilities` round trip) increases `platform_
    db_time_stats()`'s own `sessions`, `connect_wall_ms`, `db_wall_ms`,
    and `db_calls` (the per-call credential store opens and closes a real
    connection to run `authenticate`'s SELECT). A second, back-to-back
    call to the accessor itself changes nothing further -- it opens no
    connection of its own. Unaffected by WP-3 (D-11, this WP's own credential-
    store pool wiring, is out of scope for this change set -- this
    adapter's `_read_store` still opens a connection per call).

    mutation M99 (`conformance_adapter_mitatedb_http.py`): drop `self.
    _read_store` from `platform_db_time_stats()`'s own sum -- this test's
    own `sessions`/`db_wall_ms`/`db_calls` delta assertions go red (the
    credential store's own real traffic is excluded from the total)."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101perf{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        before = adapter.platform_db_time_stats()
        adapter.authenticate(handle)
        after = adapter.platform_db_time_stats()
        again = adapter.platform_db_time_stats()
        assert after["sessions"] - before["sessions"] >= 1
        assert after["connect_wall_ms"] > before["connect_wall_ms"]
        assert after["db_wall_ms"] > before["db_wall_ms"]
        assert after["db_calls"] - before["db_calls"] >= 1
        assert again["sessions"] == after["sessions"]
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()
