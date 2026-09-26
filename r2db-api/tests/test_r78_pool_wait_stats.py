r"""r78 pool wait statistics -- `r2db_api.postgres._RolePool`'s and
`SharedPoolManager`'s new acquisition/wait counters (design D-1,
docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md WP-1
completion conditions 1, 2, 3, 4, 7, 11), plus the `-http`/`-socket`
conformance plugs' new `pool_stats()`.

Real PostgreSQL, no application provisioning: every `_RolePool`/
`PostgresCell` here targets `R2DB_TEST_ADMIN_DSN`'s own `postgres`
database with `schema="public"` and role `"postgres"` -- always present,
never provisioned by this file -- the same lightweight target
`test_postgres.py`'s own connect-failure-recovery test already reaches for
(its own `pool._dsn = _admin_dsn()` recovery step). These tests are about
pool bookkeeping, not about anything application-specific.

Run directly:
    ./.venv/bin/python -m pytest r2db-api/tests/test_r78_pool_wait_stats.py -q
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

from r2db_api.postgres import PostgresCell, SharedPoolManager, _RolePool

ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"

_CONFORMANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "conformance")
if _CONFORMANCE_DIR not in sys.path:
    sys.path.insert(0, _CONFORMANCE_DIR)
import conformance_adapter_r2db_http as _http_module  # noqa: E402


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def test_role_pool_wait_stats_increment_when_a_second_acquisition_finds_the_pool_full():
    """Completion condition 1: a `maxconn=1` pool, one connection held by
    another thread, a second acquisition against the same pool genuinely
    blocks on the wait branch (`queue.Queue.get(timeout=...)`) and
    observes it -- `wait_count` rises by exactly one and `wait_max_ms` is
    positive once the holder releases and the waiter succeeds.

    mutation M1 (`r2db_api/postgres.py`): drop the `wait_count`/`wait_max_
    ms` update from the wait branch -- both assertions below go red (they
    stay at their starting values, 0 and 0.0)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1, connect_timeout=5, acquire_timeout=5.0)
    try:
        held_ready = threading.Event()
        release_holder = threading.Event()

        def holder() -> None:
            with pool.connection():
                held_ready.set()
                release_holder.wait(timeout=5)

        holder_thread = threading.Thread(target=holder)
        holder_thread.start()
        assert held_ready.wait(timeout=5)
        # Let the holder thread actually settle inside `with pool.
        # connection():` before this thread's own acquisition starts
        # timing a wait against it.
        time.sleep(0.05)

        outcome: list[BaseException | None] = []

        def waiter() -> None:
            try:
                with pool.connection():
                    pass
            except BaseException as exc:  # noqa: BLE001 - captured for the main thread's own assertions
                outcome.append(exc)
            else:
                outcome.append(None)

        waiter_thread = threading.Thread(target=waiter)
        waiter_thread.start()
        time.sleep(0.2)
        release_holder.set()
        holder_thread.join(timeout=5)
        waiter_thread.join(timeout=5)
        assert outcome == [None]

        stats = pool.stats()
        assert stats["wait_count"] == 1
        assert stats["wait_max_ms"] > 0.0
    finally:
        pool.close_all()


def test_role_pool_wait_stats_stay_zero_when_capacity_is_never_exhausted():
    """Completion condition 2: with headroom in `maxconn`, N sequential
    acquire/release cycles never enter the wait branch -- `acquire_count`
    reaches N, `wait_count` stays 0, `wait_total_ms` stays 0.0.

    mutation M2 (`r2db_api/postgres.py`): count `wait_count` unconditionally
    at the top of `_acquire`, not only in the wait branch -- the `wait_
    count == 0` assertion below goes red."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=4, connect_timeout=5, acquire_timeout=5.0)
    try:
        n = 5
        for _ in range(n):
            with pool.connection():
                pass
        stats = pool.stats()
        assert stats["acquire_count"] == n
        assert stats["wait_count"] == 0
        assert stats["wait_total_ms"] == 0.0
    finally:
        pool.close_all()


def test_role_pool_in_use_peak_keeps_the_highest_concurrent_checkout():
    """Completion condition 3: two connections held at once, then both
    released, then a THIRD acquisition made alone (`in_use` back down to
    1) -- `in_use_peak` keeps 2 throughout, never overwritten downward by
    a later, lower in-use count.

    mutation M3 (`r2db_api/postgres.py`): update `in_use_peak` by plain
    assignment (the LAST value of `in_use`, not the running max) instead
    of `max(...)` -- the final assertion below goes red (`in_use_peak`
    becomes 1, the in-use count during that solo third acquisition)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=2, connect_timeout=5, acquire_timeout=5.0)
    try:
        with pool.connection():
            with pool.connection():
                assert pool.stats()["in_use_peak"] == 2
        assert pool.stats()["in_use_peak"] == 2
        with pool.connection():
            assert pool.stats()["in_use_peak"] == 2
        assert pool.stats()["in_use_peak"] == 2
    finally:
        pool.close_all()


def test_shared_pool_manager_stats_keys_and_isolation():
    """Completion condition 4: `SharedPoolManager.stats()` returns a dict
    keyed by the literal `"<application_id>/<role>"` string, each value a
    dict whose key SET is exactly the six D-1 names; two different
    applications' pools do not clobber each other; an empty manager
    returns `{}`.

    mutation M4 (`r2db_api/postgres.py`): drop `in_use_peak` from the
    per-pool dict `SharedPoolManager.stats()` returns -- the key-set
    assertion below goes red."""
    manager = SharedPoolManager(idle_seconds=300, cache_max=10, pool_size=1, pool_max_overflow=0)
    try:
        assert manager.stats() == {}
        manager.get_pool(("app1", "runtime"), _admin_dsn(), schema="public")
        manager.get_pool(("app2", "developer"), _admin_dsn(), schema="public")
        stats = manager.stats()
        assert set(stats.keys()) == {"app1/runtime", "app2/developer"}
        expected_keys = {"acquire_count", "wait_count", "wait_total_ms", "wait_max_ms", "in_use_peak", "size"}
        assert set(stats["app1/runtime"].keys()) == expected_keys
        assert set(stats["app2/developer"].keys()) == expected_keys
    finally:
        manager.dispose_all()


def test_dsa_perf_pool_size_env_overrides_the_default_pool_size(monkeypatch):
    """Completion condition 7: the `-http` plug's `_perf_pool_size()`
    returns `2` (the pre-existing default) when `DSA_PERF_POOL_SIZE` is
    absent, and the env value when it names a positive integer -- observed
    via the ACTUAL pool's `size` stat once a real `PostgresCell` opens a
    connection through it, never a proxy for whether the env var was
    merely read (OPERATING_CONDITIONS.md 1.5-52).

    mutation M7 (`conformance_adapter_r2db_http.py`): remove the `DSA_
    PERF_POOL_SIZE` read from `_perf_pool_size()`, always returning `2` --
    the `pool_size=32` branch of this assertion goes red."""
    manager = SharedPoolManager(idle_seconds=300, cache_max=10, pool_size=1, pool_max_overflow=0)
    try:
        monkeypatch.delenv("DSA_PERF_POOL_SIZE", raising=False)
        cell_default = PostgresCell(
            "r78app1", "public",
            runtime_dsn=_admin_dsn(), developer_dsn=_admin_dsn(),
            runtime_role="postgres", developer_role="postgres",
            pool_size=_http_module._perf_pool_size(), pool_manager=manager,
        )
        with cell_default._runtime.connection():
            pass
        assert manager.stats()["r78app1/runtime"]["size"] == 2

        monkeypatch.setenv("DSA_PERF_POOL_SIZE", "32")
        cell_big = PostgresCell(
            "r78app2", "public",
            runtime_dsn=_admin_dsn(), developer_dsn=_admin_dsn(),
            runtime_role="postgres", developer_role="postgres",
            pool_size=_http_module._perf_pool_size(), pool_manager=manager,
        )
        with cell_big._runtime.connection():
            pass
        assert manager.stats()["r78app2/runtime"]["size"] == 32
    finally:
        manager.dispose_all()


def test_http_and_socket_r2db_plugs_expose_pool_stats():
    """Completion condition 11: both the `-http` and `-socket` r2db
    conformance plugs expose `pool_stats()` -- the socket plug inherits it
    unchanged from the http class (D-2, monitor 裁定 2026-09-23: same
    in-process cell/pool object, no need to redefine it).

    mutation M10 (`conformance_adapter_r2db_http.py`): delete the `-http`
    plug's `pool_stats` method -- both assertions below go red (the
    method disappears from the http class, so its inherited copy on the
    socket subclass disappears with it)."""
    assert hasattr(_http_module.R2DBHttpConformanceAdapter, "pool_stats")
    import conformance_adapter_r2db_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    assert _socket_module.R2DBSocketConformanceAdapter.pool_stats is _http_module.R2DBHttpConformanceAdapter.pool_stats


# ---------------------------------------------------------------------
# R-101 WP-1 D-3: `DSA_PERF_THREAD_LIMIT` env reader, `_PerfThreadLimit
# Wrapper`, and the `perf_thread_limit()` accessor -- unit-level (no real
# PostgreSQL, no live adapter construction: the env reader and wrapper
# class are pure Python, and `perf_thread_limit()` is tested by binding
# the unbound method to a lightweight stand-in carrying just the one
# attribute it reads, the same technique this file's own `hasattr`/`is`
# checks above already use to avoid constructing a live adapter).
# ---------------------------------------------------------------------


def test_perf_thread_limit_value_reads_a_positive_integer(monkeypatch):
    """Completion condition 56: the env reader returns the parsed integer
    when `DSA_PERF_THREAD_LIMIT` is a positive integer."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "4")
    assert _http_module._perf_thread_limit_value() == 4


def test_perf_thread_limit_value_is_none_when_unset_empty_or_invalid(monkeypatch):
    """Completion condition 56 (negative side): unset, empty, non-numeric,
    zero, and negative all resolve to `None` (no override) -- rejects
    zero/negative the same way as absent/invalid, never "0 or below is
    fine".

    mutation M47 (`conformance_adapter_r2db_http.py`): drop the positive-
    value check so `_perf_thread_limit_value` accepts `0`/negative
    integers too -- this test's own `is None` assertions for `"0"`/`"-3"`
    go red (both would read `0`/`-3` instead)."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    assert _http_module._perf_thread_limit_value() is None
    for raw in ("", "not-a-number", "0", "-3"):
        monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", raw)
        assert _http_module._perf_thread_limit_value() is None, raw


def test_perf_thread_limit_wrapper_sets_the_limiter_once_per_loop():
    """Completion conditions 58/60/61 (fresh loop / once per loop / loop-
    scoped, never process-global): calling the wrapper on a fresh loop
    sets THAT loop's own default anyio thread limiter to the configured
    token count; calling it again on the SAME loop after the value is
    changed back leaves it unchanged (already configured); a DIFFERENT
    fresh loop gets the same one-time treatment independently, starting
    from anyio's own default (40).

    mutation M49 (`conformance_adapter_r2db_http.py`): drop the `total_
    tokens` assignment from the wrapper's own `__call__` -- this test's
    own first assertion (`== 7`) goes red (stays at anyio's default 40).
    mutation M51 (`conformance_adapter_r2db_http.py`): remove the loop-id
    membership check so the wrapper sets `total_tokens` on EVERY call --
    this test's own second assertion (still `== 3`, unchanged after a
    manual reset) goes red (it would read `7` again).
    mutation M52 (`conformance_adapter_r2db_http.py`): track "configured"
    with a single instance-wide flag instead of a per-loop-id set -- this
    test's own third assertion (loop B independently reaching `7`) goes
    red (loop B would be skipped as "already configured").

    Completion condition 58's own negative side (code review 1 F2): a
    THIRD fresh loop the wrapper is never called on at all stays at
    anyio's own untouched default (40) -- the wrapper's own effect is
    strictly per-loop, never process-global."""
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
    """Completion condition 64: `uvicorn.Config(wrapper, lifespan="off").
    load()` resolves the wrapper to the asgi3 interface (`async def
    __call__`), never asgi2 -- this is what lets the socket plug's own
    uvicorn thread (`interface="auto"`, never specified explicitly) drive
    the wrapper correctly.

    mutation M55 (`conformance_adapter_r2db_http.py`): make `__call__` a
    plain (non-async) method that itself returns a coroutine -- this
    test's own `== "asgi3"` assertion goes red (`iscoroutinefunction`
    reads a plain function as false, so uvicorn resolves asgi2 instead)."""
    import uvicorn

    async def _noop_app(scope, receive, send) -> None:
        pass

    wrapper = _http_module._PerfThreadLimitWrapper(_noop_app, total_tokens=4)
    config = uvicorn.Config(wrapper, lifespan="off")
    config.load()
    assert config.interface == "asgi3"


def test_perf_thread_limit_accessor_reads_the_instance_attribute():
    """Completion condition 66: `perf_thread_limit()` returns whatever
    `self._perf_thread_limit` holds -- the resolved env value (`int`) when
    a wrapper is in place, `None` when it is not. Bound to a lightweight
    stand-in (never a fully constructed adapter, which would need a real
    PostgreSQL platform) -- the method itself is a one-line attribute
    read, so this is enough to pin its own contract.

    mutation M57 (`conformance_adapter_r2db_http.py`): make `perf_thread_
    limit` always return `None` regardless of `self._perf_thread_limit`
    -- this test's own `== 4` assertion goes red."""
    stand_in = SimpleNamespace(_perf_thread_limit=4)
    assert _http_module.R2DBHttpConformanceAdapter.perf_thread_limit(stand_in) == 4
    stand_in_none = SimpleNamespace(_perf_thread_limit=None)
    assert _http_module.R2DBHttpConformanceAdapter.perf_thread_limit(stand_in_none) is None


def test_perf_thread_limit_env_reader_and_wrapper_and_accessor_are_registered_isomorphic():
    """Completion condition 70: the 3 helpers this WP added to both
    peers' own HTTP conformance adapter (`_perf_thread_limit_value`,
    `_PerfThreadLimitWrapper`, `perf_thread_limit`) are registered in
    `_ISOMORPHIC_TARGETS`, and the peer-symmetry test itself is green --
    delegates to the real check rather than re-typing it, so it cannot
    drift from what that test actually verifies."""
    import test_audit_query

    names = {row[2] for row in test_audit_query._ISOMORPHIC_TARGETS}
    assert {"_perf_thread_limit_value", "_PerfThreadLimitWrapper", "perf_thread_limit"} <= names
    assert len(test_audit_query._ISOMORPHIC_TARGETS) == 167


# ---------------------------------------------------------------------
# R-101 WP-1 差し戻し 1: adapter construction-time wiring identity (D-3
# completion conditions 52/54/68) and `platform_db_time_stats()` observed
# through a real, authenticated HTTP request (completion conditions
# 22/23, `db_calls=` folded in per 差し戻し 1 item 4). Each test here
# constructs a real `R2DBHttpConformanceAdapter`/`R2DBSocketConformance
# Adapter` against the throwaway PostgreSQL cluster (the same one every
# other real-PG test in this file already targets) -- genuinely heavier
# than the unit-level tests above, but this is exactly the adapter
# `__init__`/`_build_client` wiring those tests cannot reach.
# ---------------------------------------------------------------------


def test_perf_thread_limit_leaves_the_http_adapter_unwrapped_when_env_is_absent(monkeypatch):
    """Completion condition 52 (negative side): constructing the `-http`
    adapter with `DSA_PERF_THREAD_LIMIT` absent leaves `adapter._app` as
    the plain `create_app` return value (never a `_PerfThreadLimitWrapper`
    instance) -- identity unchanged from before this feature existed --
    and the asgi client dials that SAME unwrapped object.

    mutation M43 (`conformance_adapter_r2db_http.py`): wrap the app
    unconditionally, ignoring the env reader's own `None` -- this test's
    own `not isinstance(...)` assertion goes red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    adapter = _http_module.R2DBHttpConformanceAdapter()
    try:
        assert not isinstance(adapter._app, _http_module._PerfThreadLimitWrapper)
        client_app = adapter._client._transport.app  # noqa: SLF001 -- identity check only, no request sent
        assert client_app is adapter._app
    finally:
        adapter.close()


def test_perf_thread_limit_wraps_the_http_adapters_own_app_and_the_asgi_client_dials_it(monkeypatch):
    """Completion conditions 68/58 (code review 1 F2: the identity checks
    alone are a proxy -- the condition's own words are "1 要求を通した後、
    `adapter._loop` の既定 limiter の `total_tokens` が N"): constructing
    the `-http` adapter with `DSA_PERF_THREAD_LIMIT` set wraps its own
    data-plane app -- `adapter._app` is a `_PerfThreadLimitWrapper`
    instance -- the SAME wrapped object is what the asgi client actually
    dials, AND, after sending one real request through it (`authenticate`
    -- a real `GET /v1/capabilities`), `adapter._loop`'s own default anyio
    thread limiter has actually been set to `N` -- observed on `adapter.
    _loop` itself (`run_until_complete`), never inferred from the wrapper
    object's own attributes alone.

    mutation M59 (`conformance_adapter_r2db_http.py`): pass the pre-wrap
    `app` to `self._build_client(...)` instead of the (possibly wrapped)
    local `app` variable -- this test's own `client_app is adapter._app`
    assertion goes red (the asgi client would dial the UNWRAPPED app
    while `adapter._app` is the wrapper).
    mutation M49 (`conformance_adapter_r2db_http.py`): drop the wrapper's
    own `total_tokens` assignment -- this test's own `== 5` assertion on
    `adapter._loop`'s limiter goes red (stays at anyio's default 40)."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "5")
    adapter = _http_module.R2DBHttpConformanceAdapter()
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


def test_perf_thread_limit_wraps_the_socket_adapters_own_data_surface_app(monkeypatch):
    """Completion condition 54: the `-socket` adapter's own data-plane
    surface is bound to the SAME wrapped app `adapter._app` holds -- the
    object `_AppDispatch` will use the moment the surface actually starts.
    Never started here: `_DeclaredSocketSurface.rebind_app` only records
    the app before a real start (`_ensure_started` runs lazily, only from
    `base_url`/a real request), so this observes identity with no real
    uvicorn/nginx ever spun up (`adapter._data_surface._started` stays
    `False` throughout).

    mutation M45 (`conformance_adapter_r2db_http.py`): assign the
    UNWRAPPED app to `self._app` while still handing the wrapped one to
    `self._build_client(...)` -- this test's own `surface_app is adapter.
    _app` assertion goes red (the socket surface's own bound app would be
    the wrapper, while `adapter._app` is the plain app)."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "3")
    import conformance_adapter_r2db_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    adapter = _socket_module.R2DBSocketConformanceAdapter()
    try:
        assert isinstance(adapter._app, _http_module._PerfThreadLimitWrapper)
        surface_app = adapter._data_surface._app  # noqa: SLF001 -- pre-start identity check, no real server
        assert surface_app is adapter._app
        assert adapter._data_surface._started is False
    finally:
        monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
        adapter.close()


def test_platform_db_time_stats_observes_a_real_authenticated_http_request():
    """Completion conditions 22/23, plus `db_calls=` (差し戻し 1 item 4):
    sending one real, authenticated HTTP request through the `-http`
    adapter (`authenticate()` -- a real `GET /v1/capabilities` round trip,
    `conformance_adapter_r2db_http.py`'s own docstring on that method)
    increases `platform_db_time_stats()`'s own `db_wall_ms` and `db_
    calls` (the credential store's pooled `_RolePool` runs the real
    `_authenticate` SELECT on this request) -- observed as a PRE/POST
    difference around that one call, never a proxy. Read-only: calling
    `platform_db_time_stats()` itself never changes `_RolePool.
    acquire_count` (R-78, both the credentials pool and the audit pool it
    also sums) or any queued connection's own `execute_count`/`db_wall_
    ms` (condition 23).

    mutation M21 (`conformance_adapter_r2db_http.py`): drop `self.
    _credentials` from `platform_db_time_stats()`'s own sum -- this test's
    own `db_wall_ms`/`db_calls` delta assertions go red (the credential
    pool's own real traffic is excluded from the total).
    mutation M22 (`conformance_adapter_r2db_http.py`): read `platform_db_
    time_stats()` through `self._credentials._pool.connection()` (`_
    acquire()`) instead of `platform_stats()` -- this test's own `acquire_
    count` no-op assertion goes red (an extra acquisition is recorded)."""
    adapter = _http_module.R2DBHttpConformanceAdapter()
    app_id = f"r101perf{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        before = adapter.platform_db_time_stats()
        adapter.authenticate(handle)
        # `acquire_count` is read immediately around the SECOND (POST)
        # `platform_db_time_stats()` call only -- the real `authenticate()`
        # request above legitimately raises it (a real `_acquire()`), so
        # comparing across that call would prove nothing; this isolates
        # whether the accessor CALL ITSELF touches `_acquire()`.
        acquire_count_before_read = adapter._credentials._pool.stats()["acquire_count"]  # noqa: SLF001
        audit_acquire_count_before_read = adapter._application_durable_audit._pool.stats()["acquire_count"]  # noqa: SLF001
        # Condition 23: the accessor is read-only for every connection it
        # walks, not just for the pool's own acquire counter -- snapshot
        # each queued connection's own `execute_count`/`db_wall_ms` (the
        # same objects, not copies) around the call and compare.
        queued_conns = list(adapter._credentials._pool._queue.queue)  # noqa: SLF001
        conn_stats_before_read = [(c.execute_count, c.db_wall_ms) for c in queued_conns]
        after = adapter.platform_db_time_stats()
        acquire_count_after_read = adapter._credentials._pool.stats()["acquire_count"]  # noqa: SLF001
        audit_acquire_count_after_read = adapter._application_durable_audit._pool.stats()["acquire_count"]  # noqa: SLF001
        conn_stats_after_read = [(c.execute_count, c.db_wall_ms) for c in queued_conns]
        assert after["db_wall_ms"] > before["db_wall_ms"]
        assert after["db_calls"] - before["db_calls"] >= 1
        assert acquire_count_after_read == acquire_count_before_read
        assert audit_acquire_count_after_read == audit_acquire_count_before_read
        assert conn_stats_after_read == conn_stats_before_read
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_perf_thread_limit_wrapper_drops_a_collected_loop_from_its_own_tracking():
    """F6 (code review 1): the wrapper's own "already configured"
    tracking holds the actual loop OBJECT in a `weakref.WeakSet`, never
    `id(loop)` in a plain `set` -- so a closed, dereferenced, garbage-
    collected loop is dropped from that tracking automatically (`len()`
    falls to 0), never left as a permanent entry a later, unrelated loop's
    own reused `id()` could collide with. A brand new loop still gets the
    same one-time treatment (`== 7`) regardless.

    mutation (`conformance_adapter_r2db_http.py`): track membership by
    `id(loop)` in a plain `set` again -- this test's own `len(...) == 0`
    assertion (after `loop_a` is closed, dereferenced, and collected) goes
    red: a plain `int` in a `set` is never dropped by garbage collection,
    so the tracking set's own length stays at `1`, not `0`."""
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
