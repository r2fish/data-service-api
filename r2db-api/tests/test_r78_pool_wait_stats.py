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
# R-101 WP-1 D-3 / WP-3 D-10: the `DSA_PERF_THREAD_LIMIT` env reader and
# the `-http` adapter's construction-time wiring of its effective value
# into `create_app(..., thread_limit=)` -- unit-level (no real
# PostgreSQL, no live adapter construction) for the env reader itself,
# and real-adapter-construction level (throwaway PostgreSQL platform)
# for the wiring, since `_perf_thread_limit_value`'s own contract does
# not need a live adapter and the wiring does.
# ---------------------------------------------------------------------


def test_perf_thread_limit_value_reads_a_positive_integer(monkeypatch):
    """Completion condition 102/106 (positive side): the env reader
    returns the parsed integer when `DSA_PERF_THREAD_LIMIT` is a positive
    integer."""
    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "4")
    assert _http_module._perf_thread_limit_value() == 4


def test_perf_thread_limit_value_defaults_to_4_when_unset_empty_or_invalid(monkeypatch):
    """Completion conditions 102/154: unset, empty, non-numeric, zero, and
    negative all resolve to `DEFAULT_THREAD_LIMIT` (4) -- WP-3 (D-10)
    replaced WP-1's own `None` ("no override") result with `create_app`'s
    own default, since the adapter no longer wraps the app itself; it
    always passes SOME effective `thread_limit=` int through.

    mutation M144 (`conformance_adapter_r2db_http.py`): make the env
    reader return `None` again when the env is absent -- this test's own
    first assertion (`== 4`) goes red (`None != 4`)."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    assert _http_module._perf_thread_limit_value() == 4
    for raw in ("", "not-a-number", "0", "-3"):
        monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", raw)
        assert _http_module._perf_thread_limit_value() == 4, raw


def test_perf_thread_limit_accessor_reads_the_instance_attribute():
    """Completion condition 106: `perf_thread_limit()` returns whatever
    `self._perf_thread_limit` holds. Bound to a lightweight stand-in
    (never a fully constructed adapter, which would need a real
    PostgreSQL platform) -- the method itself is a one-line attribute
    read, so this is enough to pin its own contract.

    mutation M148 (`conformance_adapter_r2db_http.py`): make `perf_thread_
    limit` always return `DEFAULT_THREAD_LIMIT` regardless of `self.
    _perf_thread_limit` -- this test's own `== 5` assertion goes red."""
    stand_in = SimpleNamespace(_perf_thread_limit=5)
    assert _http_module.R2DBHttpConformanceAdapter.perf_thread_limit(stand_in) == 5
    stand_in_default = SimpleNamespace(_perf_thread_limit=4)
    assert _http_module.R2DBHttpConformanceAdapter.perf_thread_limit(stand_in_default) == 4


def test_perf_thread_limit_env_reader_and_accessor_are_registered_isomorphic():
    """Completion condition 110: the `-http` conformance adapter's own
    `_perf_thread_limit_value`/`perf_thread_limit` stay registered in
    `_ISOMORPHIC_TARGETS` (WP-1), and `ThreadLimitMiddleware`/`DEFAULT_
    THREAD_LIMIT` (`http.py`)/`_thread_limit_from_env` (`main.py`) are
    now registered too (WP-3) -- delegates to the real check rather than
    re-typing it, so it cannot drift from what that test actually
    verifies."""
    import test_audit_query

    names = {row[2] for row in test_audit_query._ISOMORPHIC_TARGETS}
    assert {
        "_perf_thread_limit_value", "perf_thread_limit",
        "ThreadLimitMiddleware", "DEFAULT_THREAD_LIMIT", "_thread_limit_from_env",
    } <= names
    assert "_PerfThreadLimitWrapper" not in names
    assert len(test_audit_query._ISOMORPHIC_TARGETS) == 196


# ---------------------------------------------------------------------
# R-101 WP-3 D-10: adapter construction-time wiring identity (completion
# conditions 102/104/106/108/154) and the socket plug's own shared app
# identity (109). Each test here constructs a real `R2DBHttpConformance
# Adapter`/`R2DBSocketConformanceAdapter` against the throwaway
# PostgreSQL cluster (the same one every other real-PG test in this file
# already targets) -- genuinely heavier than the unit-level tests above,
# but this is exactly the adapter `__init__`/`_build_client` wiring those
# tests cannot reach.
# ---------------------------------------------------------------------


def test_http_adapter_default_thread_limit_is_4_and_app_is_the_create_app_result(monkeypatch):
    """Completion conditions 102/108: constructing the `-http` adapter
    with `DSA_PERF_THREAD_LIMIT` absent reports `perf_thread_limit() ==
    4`, and `adapter._app` is exactly the object `create_app` returned --
    the SAME object the asgi client dials, never a second, separately
    built app.

    mutation M150 (`conformance_adapter_r2db_http.py`): pass a SECOND,
    freshly built `create_app(...)` result to `self._build_client(...)`
    instead of the local `app` variable -- this test's own `client_app is
    adapter._app` assertion goes red."""
    monkeypatch.delenv("DSA_PERF_THREAD_LIMIT", raising=False)
    adapter = _http_module.R2DBHttpConformanceAdapter()
    try:
        assert adapter.perf_thread_limit() == 4
        client_app = adapter._client._transport.app  # noqa: SLF001 -- identity check only, no request sent
        assert client_app is adapter._app
    finally:
        adapter.close()


def test_http_adapter_thread_limit_env_overrides_and_sets_the_loop_limiter(monkeypatch):
    """Completion conditions 104/106 (code review 1 F2 shape: the
    condition's own words are "1 要求を通した後、`adapter._loop` の既定
    limiter の `total_tokens` が N"): constructing the `-http` adapter
    with `DSA_PERF_THREAD_LIMIT=5` reports `perf_thread_limit() == 5`,
    and after sending one real request through it (`authenticate()` -- a
    real `GET /v1/capabilities`), `adapter._loop`'s own default anyio
    thread limiter has actually been set to `5` -- observed on `adapter.
    _loop` itself (`run_until_complete`), never inferred from the
    adapter's own attributes alone.

    mutation M146 (`conformance_adapter_r2db_http.py`): pass `DEFAULT_
    THREAD_LIMIT` to `create_app` regardless of the env reader's own
    value -- this test's own `total_tokens == 5` assertion goes red
    (stays at `4`)."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "5")
    adapter = _http_module.R2DBHttpConformanceAdapter()
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
    """Completion condition 154: `DSA_PERF_THREAD_LIMIT=0` (invalid --
    not a positive integer) resolves to `DEFAULT_THREAD_LIMIT` (4), both
    on the accessor and on the loop's own limiter after one real request.

    mutation M192 (`conformance_adapter_r2db_http.py`): have the env
    reader return `None` for an invalid value and pass that straight to
    `create_app` -- `create_app` then adds no middleware at all, so this
    test's own `total_tokens == 4` assertion goes red (stays at anyio's
    untouched default, 40) and the accessor no longer reports a plain
    int."""
    import anyio.to_thread

    monkeypatch.setenv("DSA_PERF_THREAD_LIMIT", "0")
    adapter = _http_module.R2DBHttpConformanceAdapter()
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
    """Completion condition 109 (r2db's own share of the "socket plug"
    half of 108): the `-socket` adapter's own data-plane surface is bound
    to the SAME app object `adapter._app` holds -- the object
    `_AppDispatch` will use once the surface actually starts. Never
    started here: `_DeclaredSocketSurface.rebind_app` only records the
    app before a real start, so this observes identity with no real
    uvicorn/nginx ever spun up."""
    import conformance_adapter_r2db_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    adapter = _socket_module.R2DBSocketConformanceAdapter()
    try:
        surface_app = adapter._data_surface._app  # noqa: SLF001 -- pre-start identity check, no real server
        assert surface_app is adapter._app
        assert adapter._data_surface._started is False
    finally:
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
