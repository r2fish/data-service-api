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

import os
import sys
import threading
import time

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
