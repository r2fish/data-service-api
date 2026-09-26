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
# R-101 WP-1 D-3: `DSA_PERF_THREAD_LIMIT` env reader, `_PerfThreadLimit
# Wrapper`, and the `perf_thread_limit()` accessor -- unit-level (see
# r2db-api/tests/test_r78_pool_wait_stats.py's own identical section for
# why: both helpers are byte-identical between peers, so the same
# lightweight technique applies here without constructing a live adapter).
# ---------------------------------------------------------------------


def test_perf_thread_limit_value_reads_a_positive_integer(monkeypatch):
    """Completion condition 57: the env reader returns the parsed integer
    when `DSA_PERF_THREAD_LIMIT` is a positive integer."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "4")
    assert _http_module._perf_thread_limit_value() == 4


def test_perf_thread_limit_value_is_none_when_unset_empty_or_invalid(monkeypatch):
    """Completion condition 57 (negative side): unset, empty, non-numeric,
    zero, and negative all resolve to `None` (no override) -- rejects
    zero/negative the same way as absent/invalid.

    mutation M48 (`conformance_adapter_mitatedb_http.py`): drop the
    positive-value check so `_perf_thread_limit_value` accepts `0`/
    negative integers too -- this test's own `is None` assertions for
    `"0"`/`"-3"` go red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    assert _http_module._perf_thread_limit_value() is None
    for raw in ("", "not-a-number", "0", "-3"):
        monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", raw)
        assert _http_module._perf_thread_limit_value() is None, raw


def test_perf_thread_limit_wrapper_sets_the_limiter_once_per_loop():
    """Completion conditions 59/62/63 (fresh loop / once per loop / loop-
    scoped): same property as the r2db-side test, against this peer's own
    copy of the wrapper class.

    mutation M50 (`conformance_adapter_mitatedb_http.py`): drop the
    `total_tokens` assignment from the wrapper's own `__call__` -- this
    test's own first assertion (`== 7`) goes red.
    mutation M53 (`conformance_adapter_mitatedb_http.py`): make the
    wrapper set `total_tokens` on every call, dropping the per-loop-id
    membership check -- this test's own second assertion (still `== 3`,
    unchanged after a manual reset) goes red.
    mutation M54 (`conformance_adapter_mitatedb_http.py`): track
    "configured" with a single instance-wide flag instead of a per-loop-id
    set -- this test's own third assertion (loop B independently reaching
    `7`) goes red.

    Completion condition 59's own negative side (コードレビュー 2 差し戻し 3
    指摘 9, matching r2db-side `test_perf_thread_limit_wrapper_sets_the_
    limiter_once_per_loop` above): a THIRD fresh loop the wrapper is never
    called on at all stays at anyio's own untouched default (40) -- the
    wrapper's own effect is strictly per-loop, never process-global."""
    import anyio.to_thread

    async def _noop_app(scope, receive, send) -> None:
        pass

    wrapper = _http_module._PerfThreadLimitWrapper(_noop_app, total_tokens=7)

    async def _call_once() -> int:
        await wrapper(None, None, None)
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    loop_a = asyncio.new_event_loop()
    try:
        assert loop_a.run_until_complete(_call_once()) == 7

        async def _reset_and_call_again() -> int:
            anyio.to_thread.current_default_thread_limiter().total_tokens = 3
            await wrapper(None, None, None)
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_a.run_until_complete(_reset_and_call_again()) == 3
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        assert loop_b.run_until_complete(_call_once()) == 7
    finally:
        loop_b.close()

    async def _read_default() -> int:
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    loop_c = asyncio.new_event_loop()
    try:
        assert loop_c.run_until_complete(_read_default()) == 40
    finally:
        loop_c.close()


def test_perf_thread_limit_wrapper_is_detected_as_asgi3_by_uvicorn():
    """Completion condition 65: same asgi3-detection property as the
    r2db-side test, against this peer's own copy of the wrapper class.

    mutation M56 (`conformance_adapter_mitatedb_http.py`): make
    `__call__` a plain (non-async) method that itself returns a coroutine
    -- this test's own `== "asgi3"` assertion goes red."""
    import uvicorn

    async def _noop_app(scope, receive, send) -> None:
        pass

    wrapper = _http_module._PerfThreadLimitWrapper(_noop_app, total_tokens=4)
    config = uvicorn.Config(wrapper, lifespan="off")
    config.load()
    assert config.interface == "asgi3"


def test_perf_thread_limit_accessor_reads_the_instance_attribute():
    """Completion condition 67: `perf_thread_limit()` returns whatever
    `self._perf_thread_limit` holds, bound to a lightweight stand-in.

    mutation M58 (`conformance_adapter_mitatedb_http.py`): make `perf_
    thread_limit` always return `None` regardless of `self._perf_thread_
    limit` -- this test's own `== 4` assertion goes red."""
    stand_in = SimpleNamespace(_perf_thread_limit=4)
    assert _http_module.MitateDBHttpConformanceAdapter.perf_thread_limit(stand_in) == 4
    stand_in_none = SimpleNamespace(_perf_thread_limit=None)
    assert _http_module.MitateDBHttpConformanceAdapter.perf_thread_limit(stand_in_none) is None


# ---------------------------------------------------------------------
# R-101 WP-1 差し戻し 1: adapter construction-time wiring identity (D-3
# completion conditions 53/55/69) and `platform_db_time_stats()` observed
# through a real, authenticated HTTP request (mirrors r2db-api/tests/
# test_r78_pool_wait_stats.py's own identical section; MitateDB has no
# `_RolePool`/`acquire_count` concept for its per-call platform
# connections, so the "accessor itself opens nothing" check instead
# confirms `sessions` is unchanged by a second, back-to-back accessor
# call).
# ---------------------------------------------------------------------


def test_perf_thread_limit_leaves_the_http_adapter_unwrapped_when_env_is_absent(monkeypatch):
    """Completion condition 53 (negative side): constructing the `-http`
    adapter with `DSA_PERF_THREAD_LIMIT` absent leaves `adapter._app` as
    the plain `create_app` return value, and the asgi client dials that
    SAME unwrapped object.

    mutation M44 (`conformance_adapter_mitatedb_http.py`): wrap the app
    unconditionally, ignoring the env reader's own `None` -- this test's
    own `not isinstance(...)` assertion goes red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    try:
        assert not isinstance(adapter._app, _http_module._PerfThreadLimitWrapper)
        client_app = adapter._client._transport.app  # noqa: SLF001 -- identity check only, no request sent
        assert client_app is adapter._app
    finally:
        adapter.close()


def test_perf_thread_limit_wraps_the_http_adapters_own_app_and_the_asgi_client_dials_it(monkeypatch):
    """Completion conditions 69/59 (code review 1 F2: the identity checks
    alone are a proxy for the condition's own words, "1 要求を通した後、
    `adapter._loop` の既定 limiter の `total_tokens` が N"): constructing
    the `-http` adapter with `DSA_PERF_THREAD_LIMIT` set wraps its own
    data-plane app, the SAME wrapped object is what the asgi client
    actually dials, AND, after sending one real request through it
    (`authenticate` -- a real `GET /v1/capabilities`), `adapter._loop`'s
    own default anyio thread limiter has actually been set to `N`.

    mutation M60 (`conformance_adapter_mitatedb_http.py`): pass the
    pre-wrap `app` to `self._build_client(...)` instead of the (possibly
    wrapped) local `app` variable -- this test's own `client_app is
    adapter._app` assertion goes red.
    mutation M50 (`conformance_adapter_mitatedb_http.py`): drop the
    wrapper's own `total_tokens` assignment -- this test's own `== 5`
    assertion on `adapter._loop`'s limiter goes red (stays at 40)."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "5")
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101perf{secrets.token_hex(4)}"
    try:
        assert isinstance(adapter._app, _http_module._PerfThreadLimitWrapper)
        assert adapter._app._total_tokens == 5
        client_app = adapter._client._transport.app  # noqa: SLF001
        assert client_app is adapter._app
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        adapter.authenticate(handle)  # a real request, through the wrapper's own __call__

        async def _read_total_tokens() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert adapter._loop.run_until_complete(_read_total_tokens()) == 5
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
        adapter.close()


def test_perf_thread_limit_wraps_the_socket_adapters_own_data_plane_surface_app(monkeypatch):
    """Completion condition 55: the `-socket` adapter's own data-plane
    surface (`_socket_surface_for(adapter._app)`) is bound to the SAME
    wrapped app `adapter._app` holds. `_AppSocketSurface.__init__` itself
    never starts a real uvicorn/nginx (`ensure_started()` runs lazily,
    only from a real request) -- calling `_socket_surface_for` again here
    only looks the already-built surface up by `id(app)`, starting
    nothing.

    mutation M46 (`conformance_adapter_mitatedb_http.py`): assign the
    UNWRAPPED app to `self._app` while still handing the wrapped one to
    `self._build_client(...)` -- this test's own `surface.app is adapter.
    _app` assertion goes red.

    Looks the surface up by `id(adapter._app)` in `adapter._socket_
    surfaces` itself, rather than calling `_socket_surface_for(adapter.
    _app)` here: that method builds a fresh entry for WHATEVER app id it
    is handed, even a wrong one, so calling it with `adapter._app` can
    never observe what `_build_client` (the ONLY other caller) was
    actually given -- a `KeyError` here means `_build_client` ran with a
    different app object (コードレビュー 2 差し戻し 3 指摘 5)."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "3")
    import conformance_adapter_mitatedb_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    adapter = _socket_module.MitateDBSocketConformanceAdapter()
    try:
        assert isinstance(adapter._app, _http_module._PerfThreadLimitWrapper)
        surface = adapter._socket_surfaces[id(adapter._app)]
        assert surface.app is adapter._app
        assert surface._started is False  # noqa: SLF001 -- no real server started by this test
    finally:
        monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
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
    connection of its own.

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


def test_perf_thread_limit_wrapper_drops_a_collected_loop_from_its_own_tracking():
    """F6 (code review 1): mirrors the r2db-side identical test -- the
    wrapper's own "already configured" tracking holds the actual loop
    OBJECT in a `weakref.WeakSet`, never `id(loop)` in a plain `set`, so a
    closed, dereferenced, garbage-collected loop is dropped automatically.

    mutation (`conformance_adapter_mitatedb_http.py`): track membership by
    `id(loop)` in a plain `set` again -- this test's own `len(...) == 0`
    assertion (after `loop_a` is closed, dereferenced, and collected) goes
    red (stays at `1`)."""
    import gc

    import anyio.to_thread

    async def _noop_app(scope, receive, send) -> None:
        pass

    wrapper = _http_module._PerfThreadLimitWrapper(_noop_app, total_tokens=7)

    async def _call_once() -> None:
        await wrapper(None, None, None)

    loop_a = asyncio.new_event_loop()
    loop_a.run_until_complete(_call_once())
    assert len(wrapper._configured_loops) == 1
    loop_a.close()
    del loop_a
    gc.collect()
    assert len(wrapper._configured_loops) == 0

    async def _call_and_read() -> int:
        await wrapper(None, None, None)
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    loop_b = asyncio.new_event_loop()
    try:
        assert loop_b.run_until_complete(_call_and_read()) == 7
    finally:
        loop_b.close()
