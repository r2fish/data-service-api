r"""Pool and schema-lock statistics -- `mitatedb_api.pool.
BoundedConnectionPool`'s acquisition/wait counters and the
`PostgresBackend` schema-lock counters, as the `-http` conformance plug's
`pool_stats()` returns them (design D-1; docs/design/
MITATEDB_APPLICATION_SERIALIZATION_V0_1.md D-7;
docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md WP-1
completion conditions 5, 6, 11).

No real PostgreSQL for the pool tests: `BoundedConnectionPool` there uses
the same fake-connection substitution `test_threadpool_offload.py`'s own
thread-safety test already established (`pool._new_connection = ...`, a
plain object with `closed`/`close()`/`info`) -- those tests are entirely
about pool bookkeeping, never about a real connection's own behaviour. The
plug test below builds a real `-http` adapter against the test PostgreSQL.

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

import psycopg
import pytest

from mitatedb_api.config import FoundationConfig, role_pool_size
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import AuthorizationStateUnavailable
from mitatedb_api.http import DEFAULT_THREAD_LIMIT
from mitatedb_api.pool import BoundedConnectionPool, PoolExhausted

_CONFORMANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "conformance")
if _CONFORMANCE_DIR not in sys.path:
    sys.path.insert(0, _CONFORMANCE_DIR)
import conformance_adapter_mitatedb_http as _http_module  # noqa: E402


class _FakeConnection:
    """Same shape `test_threadpool_offload.py`'s own thread-safety test
    substitutes for a real `psycopg.Connection` -- only `closed`/`close()`
    and `info.transaction_status` (idle, so `release()` has nothing to roll
    back) are ever touched by `BoundedConnectionPool` itself."""

    def __init__(self) -> None:
        self.closed = False
        self.info = SimpleNamespace(transaction_status=psycopg.pq.TransactionStatus.IDLE)

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
    elapsing with nothing returned) also counts as a wait. The pool itself
    raises `PoolExhausted`; the credential store borrowing from it answers
    `AuthorizationStateUnavailable` with the message text it always had."""
    pool = _fake_pool(max_size=1, acquire_timeout=0.2)
    store = PostgresCredentialStore(
        "dsn-unused-fake-pool-r78-test.invalid", pepper="synthetic-test-pepper-wp4e-platform-pool-0000",
        pool=pool,
    )
    try:
        held = pool.acquire()
        try:
            with pytest.raises(PoolExhausted):
                pool.acquire()
            with pytest.raises(AuthorizationStateUnavailable) as excinfo:
                with store._borrow_connection():  # noqa: SLF001 -- the one choke point every store method borrows through
                    pass
            assert str(excinfo.value) == "platform registry connection pool exhausted (max_size reached)"
            stats = pool.stats()
            assert stats["wait_count"] == 2  # the direct `acquire()` and the store's
            assert stats["wait_max_ms"] > 0.0
        finally:
            pool.release(held)
    finally:
        pool.closeall()


def test_http_and_socket_mitatedb_plugs_expose_pool_stats():
    """Extra assurance for completion condition 11 (no dedicated mutation
    of its own -- the mutation table's M10 already covers this same
    property on the r2db side): both the `-http` and `-socket` MitateDB
    conformance plugs expose `pool_stats()`, the socket plug inheriting it
    unchanged from the http class."""
    assert hasattr(_http_module.MitateDBHttpConformanceAdapter, "pool_stats")
    import conformance_adapter_mitatedb_socket as _socket_module  # noqa: E402 - conformance dir already on sys.path (module level, above)

    assert _socket_module.MitateDBSocketConformanceAdapter.pool_stats is _http_module.MitateDBHttpConformanceAdapter.pool_stats


def test_http_plug_pool_stats_returns_role_rows_and_one_schema_lock_row_per_application():
    """The `-http` plug's `pool_stats()` returns, for each open application,
    a `<application_id>/runtime` row and a `<application_id>/developer` row
    (the role pools' own six keys, the same key form as r2db's) and one
    `<application_id>` row (the schema lock's four keys). A schema operation
    through the plug moves the developer pool's `acquire_count` and the
    schema-lock row's `acquire_count` (the application-wide lock and the
    entity lock, two acquisitions) and leaves every `wait_count` at 0 -- nothing
    contends.

    mutation V72 (`conformance_adapter_mitatedb_http.py`): return the
    `runtime` row only -- the key-set assertion goes red (the `developer`
    row is missing)."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r102stats{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        session = adapter.authenticate(adapter.issue_credential(app_id, "developer"))
        before = adapter.pool_stats()
        assert set(before) == {f"{app_id}/runtime", f"{app_id}/developer", app_id}
        role_keys = {"size", "acquire_count", "wait_count", "wait_total_ms", "wait_max_ms", "in_use_peak"}
        lock_keys = {"acquire_count", "wait_count", "wait_total_ms", "wait_max_ms"}
        assert set(before[f"{app_id}/runtime"]) == role_keys
        assert set(before[f"{app_id}/developer"]) == role_keys
        assert set(before[app_id]) == lock_keys

        adapter.create_entity(session, "r102stats_entity", {})
        after = adapter.pool_stats()
        assert after[f"{app_id}/developer"]["acquire_count"] > before[f"{app_id}/developer"]["acquire_count"]
        assert after[app_id]["acquire_count"] - before[app_id]["acquire_count"] == 2
        for key in (f"{app_id}/runtime", f"{app_id}/developer", app_id):
            assert after[key]["wait_count"] == 0, key
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_http_adapter_builds_each_applications_role_pools_like_the_composition_root():
    """Completion condition 65 (adapter half): the backend the `-http`
    adapter builds for a provisioned application has two role pools of
    `role_pool_size(DEFAULT_THREAD_LIMIT)` = 6 connections each, the figure
    `main.build_app` passes, not the pool module's default.

    mutation V65b (`conformance_adapter_mitatedb_http.py`): drop the
    `pool_size=` keyword from `_new_backend` -- the pools take the default
    size (20) and the assertion goes red."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r102size{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        backend = adapter._cells[app_id]._backend  # noqa: SLF001 -- adapter-internal reach-in
        expected = role_pool_size(DEFAULT_THREAD_LIMIT)
        assert expected == 6
        assert backend.pool_stats()["runtime"]["size"] == expected
        assert backend.pool_stats()["developer"]["size"] == expected
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


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
# through a real, authenticated HTTP request (D-11: `self._read_store`
# now checks connections out of `self._read_pool`, a real `pool.Bounded
# ConnectionPool` sized from this surface's own declared `max_
# concurrency` -- see the tests below this section for the pool's own
# reuse/size/close-on-cleanup properties, completion conditions 112-114).
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
    supervisor's return-file ruling directed), also completion condition
    161 (R-101 WP-3 D-11, expected values re-measured for this WP): sending
    one real, authenticated HTTP request through the `-http` adapter
    (`authenticate()` -- a real `GET /v1/capabilities` round trip)
    increases `platform_db_time_stats()`'s own `sessions`, `connect_wall_
    ms`, `db_wall_ms`, and `db_calls`. Since D-11, that traffic runs
    through `self._read_pool` (a real `pool.BoundedConnectionPool`) rather
    than a fresh per-call connection: the first authenticated request
    opens exactly one new pooled session, and its own `db_wall_ms`/
    `db_calls` still show up in the sum because `platform_db_time_stats()`
    reads `self._read_pool.platform_stats()`, which includes every
    connection currently idle in the pool (not only ones already closed).
    A second, back-to-back call to the accessor itself changes nothing
    further -- it opens no connection of its own and makes no DB round
    trip.

    mutation M199 (`conformance_adapter_mitatedb_http.py`): drop the
    credential-store pool's own contribution from `platform_db_time_
    stats()`'s sum -- this test's own `sessions`/`db_wall_ms`/`db_calls`
    delta assertions go red (the pooled connection's own real traffic is
    excluded from the total)."""
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


def test_read_pool_reuses_connection_across_two_authenticated_requests():
    """Completion condition 112 (R-101 WP-3 D-11): sending a second real,
    authenticated request after the first no longer opens a new session on
    the credential-store pool -- `adapter._read_pool.platform_stats()`'s
    own `sessions` stays unchanged between the two, while `stats()["
    acquire_count"]` still rises (the same pooled connection is acquired
    and released again, never a fresh `connect()`).

    mutation M153 (`conformance_adapter_mitatedb_http.py`): construct
    `self._read_store` without `pool=self._read_pool` (the pre-D-11 shape)
    -- this test's own `acquire_count` assertion goes red (`self._read_
    pool` is never touched by `authenticate()`, so it stays 0 for both
    calls instead of rising)."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101poolreuse{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        adapter.authenticate(handle)
        sessions_after_first = adapter._read_pool.platform_stats()["sessions"]
        acquire_count_after_first = adapter._read_pool.stats()["acquire_count"]
        adapter.authenticate(handle)
        sessions_after_second = adapter._read_pool.platform_stats()["sessions"]
        acquire_count_after_second = adapter._read_pool.stats()["acquire_count"]
        assert sessions_after_second == sessions_after_first
        assert acquire_count_after_second > acquire_count_after_first
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_read_pool_size_matches_role_pool_size_of_the_thread_limit():
    """Completion condition 113 (R-101 WP-3 D-11): the credential-store
    pool's own `size` (`stats()["size"]`, its `max_size`) is derived the
    same way `main.py`'s production pool is -- `role_pool_size(<the
    thread limit>)` (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3
    (5): `DEFAULT_THREAD_LIMIT` here, the per-process simultaneous-borrow
    ceiling) -- never a fixed literal.

    mutation M154 (`conformance_adapter_mitatedb_http.py`): fix the pool's
    `max_size` at `1` -- this test's own equality assertion goes red
    (`role_pool_size(DEFAULT_THREAD_LIMIT)` is 6, not 1)."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    try:
        expected = role_pool_size(DEFAULT_THREAD_LIMIT)
        assert adapter._read_pool.stats()["size"] == expected
    finally:
        adapter.close()


def test_read_pool_closes_all_connections_on_adapter_close():
    """Completion condition 114 (R-101 WP-3 D-11): after a real
    authenticated request leaves a connection idle in the credential-store
    pool, `adapter.close()` (which reaches `self._read_store.close()` ->
    `self._pool.closeall()`) closes every connection the pool was holding.

    mutation M155 (`conformance_adapter_mitatedb_http.py`): drop `self.
    _read_store.close()` from `_cleanup` -- this test's own `conn.closed`
    assertion goes red (the pooled connection this test captured a
    reference to stays open)."""
    adapter = _http_module.MitateDBHttpConformanceAdapter()
    app_id = f"r101poolclose{secrets.token_hex(4)}"
    conn = None
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        adapter.authenticate(handle)
        conn = adapter._read_pool.acquire()
        assert conn.closed is False
        adapter._read_pool.release(conn)
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()
    assert conn is not None
    assert conn.closed is True
