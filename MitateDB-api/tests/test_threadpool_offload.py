"""WP-8b (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-8 (3),
work order docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md
WP-8a/WP-8b section): pins that both HTTP surfaces (`http.py`'s data
plane, `control_http.py`'s control plane) delegate the synchronous
section of every handler -- authenticate/rate-precharge, then the real
cell/`ControlPlaneService`/psycopg call -- to `starlette.concurrency.
run_in_threadpool`, started only after the async body read (where one
exists) has already completed, and that the process-wide in-memory state
this delegation now reaches from multiple real OS threads concurrently
(`cell._LimitStateHolder`, `pool.BoundedConnectionPool`) stays correct
under that concurrency.

Independent implementation for THIS peer only (WP-8a is r2db-api's own,
separate worktree) -- no code shared between peers (R-2's closing
paragraph); this file reuses only this SAME peer's own existing test
fixtures/helpers (`test_http.py`/`test_postgres.py`/
`test_control_http_unmounted.py`), the same "a peer's own two files may
share a helper" convention `control_http.py`'s own top-of-file docstring
already states.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from unittest import mock

import httpx
import psycopg
import pytest

import mitatedb_api.control_http as control_http_module
import mitatedb_api.http as http_module
import mitatedb_api.credential_store_postgres as credential_store_postgres_module
from mitatedb_api.auth import Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell, ApplicationRuntime, _LimitStateHolder
from mitatedb_api.config import FoundationConfig, role_pool_size
from mitatedb_api.control_plane import ControlPlaneService
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import AuthorizationStateUnavailable
from mitatedb_api.pool import BoundedConnectionPool

# Fixture reuse (same peer, two test files -- see this module's own
# docstring): `app_a_stack` (a real, throwaway-provisioned PostgreSQL
# application wired into a real `http.create_app` ASGI app) is DEFINED in
# `test_http.py` and itself depends on `platform`/`app_a` (defined in
# `test_postgres.py`) -- all three are imported here, exactly the same
# transitive set `test_http.py` itself imports, so pytest's fixture
# resolution finds `platform`/`app_a` from THIS module's own namespace
# when it resolves `app_a_stack`'s own dependencies for a test here.
# `credential_app` (also `test_postgres.py`) is this same file's own
# lightweight "registered application" fixture -- the platform-pool test
# below only exercises `credentials`/`applications`, never a real
# per-application database, exactly like every OTHER `credential_app`
# consumer in `test_postgres.py`.
from .test_http import BASE_URL, _create_entity, _post, _run, app_a_stack  # noqa: F401
from .test_postgres import app_a, credential_app, platform  # noqa: F401
from .test_control_http_unmounted import _service_with_bootstrapped_credential
# `_run` reused verbatim from `test_http.py`'s own identical `asyncio.run`
# bridge (imported above) -- `httpx.ASGITransport` only implements the
# async context-manager protocol.


async def _apost_rotate(app, credential_id: str, secret: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://mitatedb-wp8b-control-test.invalid",
    ) as client:
        return await client.post(
            f"/control/v1/credentials/{credential_id}/rotate", headers={"authorization": f"Bearer {secret}"},
        )


# ---------------------------------------------------------------------------
# Completion condition 1 (data plane) / 2 (control plane): the handler's
# own synchronous section runs off the ASGI event-loop thread -- proven by
# holding one request's own synchronous section open (blocked on a
# `threading.Event`, from inside a worker thread) while a SECOND,
# independent request completes concurrently, driven from the SAME event
# loop. Mutation: removing the `run_in_threadpool` delegation from the
# held request's own endpoint makes its synchronous section run directly
# on the single ASGI event-loop thread, so the probe request's own
# `client.get(...)` coroutine never gets a turn until the held one
# releases -- `asyncio.wait_for`'s own timeout below then fires, a clean,
# fast red (never a hang).
# ---------------------------------------------------------------------------


def test_sync_section_runs_off_the_event_loop(app_a_stack):
    """Held: `GET /v1/capabilities` (`ApplicationRuntime.capabilities`
    stalled). Probe: `GET /v1/catalog` (`ApplicationRuntime.catalog`,
    untouched) -- a DIFFERENT bound method, so patching one cannot itself
    explain the probe completing.

    Mutation (`http.py::get_capabilities`'s own `document = await
    run_in_threadpool(_sync)` reverted to a direct `document = _sync()`):
    measured directly (`{scratchpad}/phase10/wp8b-mutation1.log`) --
    `_stalling_capabilities`'s own `release.wait(timeout=10)` then blocks
    the ONE AND ONLY event-loop thread directly (never yielding), so the
    probe's own `client.get("/v1/catalog", ...)` coroutine never gets a
    turn to even START until the held request's OWN 10s wait times out on
    its own accord -- `held_task` then completes (with a 503, from the
    `AssertionError` on `held` inside `_stalling_capabilities`, caught by
    `_endpoint`'s generic `except Exception`) BEFORE the probe ever runs,
    so this test's own `assert not held_task.done()` goes red once the
    probe is finally issued -- a fast (~10s, bounded by that same
    `timeout=10`), deterministic failure, never an unbounded hang.
    """
    entered = threading.Event()
    release = threading.Event()
    original = ApplicationRuntime.capabilities

    def _stalling_capabilities(self, *, request_id=None):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, request_id=request_id)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a_stack.app), base_url=BASE_URL,
        ) as client:
            held_task = asyncio.ensure_future(client.get(
                "/v1/capabilities", headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/v1/catalog", headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"}),
                timeout=5,
            )
            assert probe.status_code == 200
            # Non-vacuity (design D-8's own "壊すとどう見えるか"): the
            # probe must have completed WHILE the held request's own
            # synchronous section was still blocked -- at least 2
            # requests genuinely in flight together, not merely 2 issued.
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ApplicationRuntime, "capabilities", _stalling_capabilities):
        asyncio.run(_scenario())


def test_control_sync_section_runs_off_the_event_loop():
    """Control-plane counterpart of the test above -- `control_http.py`'s
    own handlers. Held: `GET /control/v1/applications` (`ControlPlaneService.
    list_applications` stalled). Probe: `GET /control/v1/capabilities`
    (`ControlPlaneService.control_capabilities`, untouched).

    Mutation (`control_http.py::get_list_applications`'s own `result =
    await run_in_threadpool(_sync)` reverted to a direct `result =
    _sync()`): measured directly (`{scratchpad}/phase10/wp8b-mutation2.
    log`) -- same observed failure mode as the data-plane test above: the
    held request's own blocking `release.wait(timeout=10)` monopolizes the
    single event-loop thread, so `held_task` finishes (with a 503) before
    the probe ever gets to run at all, and this test's own `assert not
    held_task.done()` goes red once the probe is finally issued -- fast
    (~10s) and deterministic, never an unbounded hang.
    """
    service, credential_id, secret = _service_with_bootstrapped_credential()
    app = control_http_module.create_control_app(service, request_bytes_limit=1_048_576)
    # `bootstrap_control_credential` issues a `must_rotate=True` credential
    # -- `list_applications` (unlike `control_capabilities`) is NOT on the
    # `_gate_must_rotate` allow-list, so it must be self-rotated first
    # (same real HTTP round trip `test_control_http_unmounted.py::test_
    # full_register_issue_list_flow_over_real_http` uses).
    rotate_response = _run(_apost_rotate(app, credential_id, secret))
    assert rotate_response.status_code == 200, rotate_response.text
    secret = rotate_response.json()["secret"]

    entered = threading.Event()
    release = threading.Event()
    original = ControlPlaneService.list_applications

    def _stalling_list_applications(self, secret, *, request_id=None, rate_precharged=False):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, secret, request_id=request_id, rate_precharged=rate_precharged)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://mitatedb-wp8b-control-test.invalid",
        ) as client:
            held_task = asyncio.ensure_future(client.get(
                "/control/v1/applications", headers={"authorization": f"Bearer {secret}"}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {secret}"}), timeout=5,
            )
            assert probe.status_code == 200
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ControlPlaneService, "list_applications", _stalling_list_applications):
        asyncio.run(_scenario())


# ---------------------------------------------------------------------------
# WP-8b review 差し戻し, additional mutation 2 (`{scratchpad}/phase10/
# wp8b-review.md` §4): the two held/probe pairs above (`get_capabilities`/
# `get_catalog`, `get_list_applications`/`get_control_capabilities`) are
# both NO-BODY handlers -- a mutation reverting `post_query`'s, `post_
# mutate`'s, or `post_cross_entity_mutate`'s own tail `await run_in_
# threadpool(_sync)` (after the body read) back to a direct `_sync()`
# left all 5 pre-existing tests in this file green (measured by the
# review). The three tests below (plus one control-plane body-carrying
# handler, `post_issue_credential`) close that gap -- one held/probe pair
# PER handler, so a mutation isolated to any ONE of them is caught by
# that one test alone, never masked by a sibling handler's own,
# unaffected delegation.
# ---------------------------------------------------------------------------


def test_post_query_sync_section_runs_off_the_event_loop(app_a_stack):
    """Held: `POST /v1/data/<entity>/query` (`ApplicationRuntime.
    read_page` stalled -- WP-2, design docs/design/
    PHASE11_KEYSET_PAGING_V1.md D-2b.4: `post_query` now calls this
    cursor-carrying entry point instead of the plain `read`). Probe:
    `GET /v1/catalog` (untouched).

    Mutation (`http.py::post_query`'s own `rows, next_page = await
    run_in_threadpool(_sync)` reverted to `rows, next_page = _sync()`):
    the held request's own synchronous section now runs directly on the
    ASGI event-loop thread, so the probe never gets a turn until the held
    request's own 10s `release.wait` times out on its own accord -- this
    test's own `assert not held_task.done()` goes red once the probe is
    finally issued.
    """
    entity = f"wp8b_query_offload_probe_{uuid.uuid4().hex[:12]}"
    _create_entity(app_a_stack, entity, ["item_key"])

    entered = threading.Event()
    release = threading.Event()
    original = ApplicationRuntime.read_page

    def _stalling_read_page(self, *args, **kwargs):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, *args, **kwargs)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a_stack.app), base_url=BASE_URL,
        ) as client:
            held_task = asyncio.ensure_future(client.post(
                f"/v1/data/{entity}/query",
                headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"},
                json={"select": ["item_key"]}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/v1/catalog", headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"}),
                timeout=5,
            )
            assert probe.status_code == 200
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ApplicationRuntime, "read_page", _stalling_read_page):
        asyncio.run(_scenario())


def test_post_mutate_sync_section_runs_off_the_event_loop(app_a_stack):
    """Held: `POST /v1/data/<entity>/mutations` (`ApplicationRuntime.
    transact` stalled). Probe: `GET /v1/catalog`.

    Mutation (`http.py::post_mutate`'s own `affected, committed, plan_
    token, mutation_request_id = await run_in_threadpool(_sync)` reverted
    to a direct `_sync()` call): same failure mode as every other test in
    this section -- `assert not held_task.done()` goes red.
    """
    entity = f"wp8b_mutate_offload_probe_{uuid.uuid4().hex[:12]}"
    _create_entity(app_a_stack, entity, ["item_key"])

    entered = threading.Event()
    release = threading.Event()
    original = ApplicationRuntime.transact

    def _stalling_transact(self, *args, **kwargs):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, *args, **kwargs)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a_stack.app), base_url=BASE_URL,
        ) as client:
            held_task = asyncio.ensure_future(client.post(
                f"/v1/data/{entity}/mutations",
                headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"},
                json={"operations": [{"operation": "insert", "values": {"item_key": "held"}}]}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/v1/catalog", headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"}),
                timeout=5,
            )
            assert probe.status_code == 200
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ApplicationRuntime, "transact", _stalling_transact):
        asyncio.run(_scenario())


def test_post_cross_entity_mutate_sync_section_runs_off_the_event_loop(app_a_stack):
    """Held: `POST /v1/data/mutations` (`post_cross_entity_mutate`'s own
    route -- `ApplicationRuntime.transact` stalled). Probe: `GET /v1/
    catalog`. A SEPARATE test from the one above even though both stall
    the SAME bound method: this one drives the request through `post_
    cross_entity_mutate`'s own handler function, so a mutation isolated
    to THAT handler's own delegation (leaving `post_mutate`'s untouched)
    is caught here and only here.

    Mutation (`http.py::post_cross_entity_mutate`'s own tail `await
    run_in_threadpool(_sync)` reverted to a direct `_sync()` call): same
    failure mode as every other test in this section.
    """
    entity = f"wp8b_cross_mutate_offload_probe_{uuid.uuid4().hex[:12]}"
    _create_entity(app_a_stack, entity, ["item_key"])

    entered = threading.Event()
    release = threading.Event()
    original = ApplicationRuntime.transact

    def _stalling_transact(self, *args, **kwargs):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, *args, **kwargs)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a_stack.app), base_url=BASE_URL,
        ) as client:
            held_task = asyncio.ensure_future(client.post(
                "/v1/data/mutations",
                headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"},
                json={"operations": [{"operation": "insert", "entity": entity, "values": {"item_key": "held"}}]}))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/v1/catalog", headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"}),
                timeout=5,
            )
            assert probe.status_code == 200
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ApplicationRuntime, "transact", _stalling_transact):
        asyncio.run(_scenario())


def test_control_post_issue_credential_sync_section_runs_off_the_event_loop():
    """The control-plane's own representative BODY-carrying handler (`test_
    control_sync_section_runs_off_the_event_loop` above only exercises a
    NO-body one, `get_list_applications`). Held: `POST /control/v1/
    credentials` (`ControlPlaneService.issue_credential` stalled). Probe:
    `GET /control/v1/capabilities`.

    Mutation (`control_http.py::post_issue_credential`'s own `result =
    await run_in_threadpool(_sync)` reverted to `result = _sync()`): same
    failure mode as every other test in this file.
    """
    service, credential_id, secret = _service_with_bootstrapped_credential()
    app = control_http_module.create_control_app(service, request_bytes_limit=1_048_576)
    rotate_response = _run(_apost_rotate(app, credential_id, secret))
    assert rotate_response.status_code == 200, rotate_response.text
    secret = rotate_response.json()["secret"]

    async def _aregister():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://mitatedb-wp8b-control-test.invalid",
        ) as client:
            return await client.post(
                "/control/v1/applications", headers={"authorization": f"Bearer {secret}"},
                json={"application_id": "wp8b_issue_cred_probe"},
            )

    register_response = _run(_aregister())
    assert register_response.status_code == 200, register_response.text

    entered = threading.Event()
    release = threading.Event()
    original = ControlPlaneService.issue_credential

    def _stalling_issue_credential(self, *args, **kwargs):
        entered.set()
        held = release.wait(timeout=10)
        assert held, "release was never set -- the held request would hang forever"
        return original(self, *args, **kwargs)

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://mitatedb-wp8b-control-test.invalid",
        ) as client:
            held_task = asyncio.ensure_future(client.post(
                "/control/v1/credentials", headers={"authorization": f"Bearer {secret}"},
                json={"application_id": "wp8b_issue_cred_probe", "role": "runtime"},
            ))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "held request never reached its own synchronous section"

            probe = await asyncio.wait_for(
                client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {secret}"}), timeout=5,
            )
            assert probe.status_code == 200
            assert not held_task.done(), (
                "the held request finished before the probe -- no real "
                "concurrency was observed (the event loop was blocked)"
            )
            release.set()
            held_response = await asyncio.wait_for(held_task, timeout=5)
            assert held_response.status_code == 200

    with mock.patch.object(ControlPlaneService, "issue_credential", _stalling_issue_credential):
        asyncio.run(_scenario())


# ---------------------------------------------------------------------------
# Completion condition 3: the body read itself stays a plain `await` on
# the event-loop thread; only the synchronous tail after it is delegated.
# ---------------------------------------------------------------------------


def test_body_read_stays_on_the_loop(app_a_stack):
    """`http.py::_read_json_object` (patched here only to RECORD which
    thread called it, never to change its behavior) runs on the same
    thread as `threading.main_thread()` -- the thread `asyncio.run`
    drives this test's own event loop on -- while `_check_object_shape`
    (the first synchronous call inside `post_schema`'s own delegated
    `_sync()` closure) runs on a DIFFERENT thread.

    Mutation (`http.py::post_schema`'s own `body = await
    _read_json_object(request)` changed to route the SAME coroutine
    through a second, worker-thread-local event loop via `run_in_
    threadpool`/a freshly-constructed `asyncio.new_event_loop().
    run_until_complete(...)` instead of a plain `await` on the current
    one): measured directly (`{scratchpad}/phase10/wp8b-mutation3.log`) --
    the request itself still completes (`response.status_code == 200`;
    the ASGI receive callable this test's own in-process `httpx.
    ASGITransport` provides tolerates being awaited from a second loop),
    but `body_read_threads` then records the WORKER thread, not
    `threading.main_thread()`'s own ident -- this test's own `body_read_
    threads == [main_ident]` assertion goes red immediately (0.74s, no
    hang: the mutated call runs its own throwaway loop to completion and
    returns normally, it just runs on the wrong thread).
    """
    main_ident = threading.main_thread().ident
    body_read_threads: list[int] = []
    tail_threads: list[int] = []

    original_read = http_module._read_json_object
    original_check = http_module._check_object_shape

    async def _tracking_read(request):
        body_read_threads.append(threading.get_ident())
        return await original_read(request)

    def _tracking_check(*args, **kwargs):
        tail_threads.append(threading.get_ident())
        return original_check(*args, **kwargs)

    entity = f"wp8b_thread_probe_{uuid.uuid4().hex[:12]}"
    with mock.patch.object(http_module, "_read_json_object", _tracking_read), \
         mock.patch.object(http_module, "_check_object_shape", _tracking_check):
        response = _post(
            app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
            json_body={"operation": "create_entity", "entity": entity, "fields": ["x"]},
        )

    assert response.status_code == 200, response.text
    assert body_read_threads == [main_ident], (
        f"body read ran on thread(s) {body_read_threads}, expected only the "
        f"event-loop thread {main_ident}"
    )
    assert tail_threads, "the delegated synchronous tail never ran at all"
    assert main_ident not in tail_threads, (
        f"the synchronous tail ran on the event-loop thread {main_ident} -- "
        "it must run off it, in the threadpool"
    )


# ---------------------------------------------------------------------------
# Completion condition 9 (WP-8b 差し戻し (0), U-10): moving the synchronous
# section off the event loop is only safe if that section's own critical
# region (`ApplicationCell._lock`) actually covers the WHOLE per-request
# lookup -> pass-1 (validation/catalog reads) -> pass-2 (execute/commit)
# sequence -- not merely the final backend call. Before this WP's fix (per
# the code review that sent WP-8b back, `{scratchpad}/phase10/wp8b-review.
# md` §1/§2), `ApplicationCell`'s pass-1 catalog reads (`field_domains` et
# al, `_idempotency_check`) ran OUTSIDE `self._lock`, sharing `Postgres
# Backend`'s single `_developer` connection with every other in-flight
# request against the SAME application/cell -- so one request's own
# `commit()`/`rollback()` on that shared connection could land on a
# DIFFERENT request's still-open transaction (measured concretely by the
# review: an independent third connection could see request A's
# uncommitted `CREATE TABLE` after request B's own unrelated `commit()`
# ran on the shared connection). This WP moves `self._lock` to wrap
# lookup -> pass-1 -> pass-2 for every public `ApplicationCell` method
# (`create_collection`/`add_field`/`alter_field`/`schema_revision`/
# `catalog`/`insert`/`read`/`update`/`delete`/`transact`), so two requests
# against the SAME cell are now fully serialized in Python BEFORE either
# one ever touches the shared `_developer` connection -- eliminating the
# interleaving structurally.
# ---------------------------------------------------------------------------


def test_concurrent_requests_on_one_application_never_touch_each_others_transaction(app_a_stack, app_a):
    """Two requests against the SAME application (one cell, one backend)
    run at once and never reach each other's connection or transaction.

    A = `POST /v1/schema/operations` (`create_entity`) -- stalled, via a
    patched `PostgresBackend._bump_schema_revision`, WHILE it holds an OPEN
    developer transaction (the `CREATE TABLE` this operation just issued).
    B = `POST /v1/data/<entity>/query` on another entity -- its catalog
    reads run on the developer connection its own request scope borrowed,
    and commit or roll back there, never on A's. While A is stalled:

    - B completes (nothing serializes the two requests on the cell: the
      connections are per request and A's schema locks cover only A's own
      entity, which a query never locks);
    - an independent connection does not see A's uncommitted `CREATE TABLE`
      (B's transaction end did not commit A's transaction);
    - after A is released A commits, and its table is visible (B's scope
      exit did not roll A's transaction back).

    Mutation: hand both requests the same connection (`PostgresBackend.
    _borrow` returning one fixed connection per pool) -- B's catalog
    reads then run inside A's transaction and B's scope end commits or
    rolls it back: `visible_before_a_commit` becomes 1 or
    `visible_after_a_commit` becomes 0."""
    _create_entity(app_a_stack, "wp8b_u10_probe_target", ["item_key"])

    entered = threading.Event()
    release = threading.Event()

    original_bump = PostgresBackend._bump_schema_revision

    def _stalling_bump(self, cur):
        result = original_bump(self, cur)
        entered.set()
        held = release.wait(timeout=30)
        assert held, "release was never set -- the held request would hang forever"
        return result

    observed: dict[str, object] = {}

    def _visible() -> int:
        with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='wp8b_u10_probe_race'")
            return cur.fetchone()[0]

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_a_stack.app), base_url=BASE_URL,
        ) as client:
            a_task = asyncio.ensure_future(client.post(
                "/v1/schema/operations",
                headers={"authorization": f"Bearer {app_a_stack.developer_bearer}"},
                json={"operation": "create_entity", "entity": "wp8b_u10_probe_race", "fields": ["k"]}))
            for _ in range(400):
                if entered.is_set():
                    break
                await asyncio.sleep(0.025)
            assert entered.is_set(), "A never reached its own stall point"

            b_response = await asyncio.wait_for(client.post(
                "/v1/data/wp8b_u10_probe_target/query",
                headers={"authorization": f"Bearer {app_a_stack.runtime_bearer}"},
                json={"select": ["item_key"]}), timeout=10)
            observed["b_status"] = b_response.status_code
            observed["a_still_stalled"] = not a_task.done() and not release.is_set()
            observed["visible_before_a_commit"] = await asyncio.to_thread(_visible)

            release.set()
            a_response = await asyncio.wait_for(a_task, timeout=30)
            observed["a_status"] = a_response.status_code
            observed["visible_after_a_commit"] = await asyncio.to_thread(_visible)

    with mock.patch.object(PostgresBackend, "_bump_schema_revision", _stalling_bump):
        asyncio.run(_scenario())

    print("\nU-10 PROBE OBSERVED:", observed)
    assert observed["a_still_stalled"], (
        f"request A was not stalled when B answered, so B never ran alongside it: {observed}")
    assert observed["b_status"] == 200, (
        f"request B did not complete while request A held its open transaction: {observed}")
    assert observed["visible_before_a_commit"] == 0, (
        "INTERLEAVING REGRESSION: an independent connection saw request A's own uncommitted CREATE TABLE "
        f"before A's own commit point -- B's transaction end committed A's transaction: {observed}")
    assert observed["a_status"] == 200 and observed["visible_after_a_commit"] == 1, (
        f"request A did not commit its own transaction after B finished: {observed}")


# ---------------------------------------------------------------------------
# Completion conditions 4/5: the process-wide in-memory state this
# delegation now reaches from multiple real OS threads concurrently stays
# correct under that concurrency (design D-8 (3)'s own required audit).
# Pre-implementation audit (reported alongside this WP): both classes
# below were ALREADY thread-safe before this WP -- `_LimitStateHolder`
# (`cell.py:774`/`:781`, `Lock`-guarded `_rate_lock`/`_active_lock`) and
# `BoundedConnectionPool` (`pool.py:78`, `threading.Lock` + `queue.
# LifoQueue`) -- no lock was added by this WP; these tests exist because
# the work order requires the property demonstrated, not merely audited.
# ---------------------------------------------------------------------------


class _CountingLock:
    """Wraps a real `threading.Lock`, counting `__enter__`/`__exit__`
    calls. Assigned onto a live `_LimitStateHolder` instance in place of
    its own real lock (no `__slots__` on that class, so this is a plain
    attribute swap) so this test can assert DETERMINISTICALLY that a
    given critical section actually takes the lock -- rather than relying
    on a live data race actually manifesting under real thread
    contention, which this SAME test empirically tried first (`n_threads`
    up to 128, `sys.setswitchinterval` down to `1e-7`, both a free-running
    and a `threading.Barrier`-lockstepped loop) and could not reproduce
    reliably on this machine even with the lock genuinely removed
    (`{scratchpad}/phase10/race_probe.py`) -- CPython 3.11's own
    specialized-bytecode fast path for a plain attribute increment
    apparently keeps that particular critical section too short a window
    for the GIL to land a switch inside it often enough for a fixed-size
    test run to depend on. The actual net-zero counter value is still
    checked below too (belt and suspenders), just not as the sole
    evidence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self._lock.__enter__()

    def __exit__(self, *exc_info):
        self.exit_count += 1
        return self._lock.__exit__(*exc_info)


def test_limiter_state_is_thread_safe():
    """`_LimitStateHolder.acquire_rate`'s own sliding window (`_rate_
    windows`) and `concurrency_slot`'s own in-flight counter (`_active`)
    are each guarded by their own lock (`_rate_lock`/`_active_lock`,
    `cell.py`). `N` threads call both repeatedly, concurrently, with
    `bound` set high enough that neither ever denies -- this test asserts
    the SAME lock objects were actually engaged the expected number of
    times (deterministic -- see `_CountingLock`'s own docstring for why
    this is the primary check here, not a live race), plus the resulting
    state is still exactly correct (`_active == 0`; each credential's own
    recorded window length equals its own call count) as a secondary,
    behavioral sanity check.

    Mutation (`cell.py::_LimitStateHolder.acquire_rate`'s own `with self.
    _rate_lock:` removed, OR `concurrency_slot`'s own two `with self.
    _active_lock:` blocks removed): the corresponding `_CountingLock`'s
    `enter_count`/`exit_count` stay at 0 (that lock is never referenced by
    the mutated code path at all) while every other assertion here would
    still pass -- this test's own `counting_rate_lock.enter_count ==
    expected_calls` (or the `_active_lock` equivalent) goes red
    immediately, deterministically, verified in `{scratchpad}/phase10/
    wp8b-mutation4.log`.
    """
    holder = _LimitStateHolder()
    counting_rate_lock = _CountingLock()
    counting_active_lock = _CountingLock()
    holder._rate_lock = counting_rate_lock  # noqa: SLF001 - test-only substitution
    holder._active_lock = counting_active_lock  # noqa: SLF001 - test-only substitution

    n_threads = 16
    calls_per_thread = 50
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            credential_id = f"wp8b-thread-safety-credential-{index}"
            for _ in range(calls_per_thread):
                holder.acquire_rate(credential_id, bound=calls_per_thread + 1)
                with holder.concurrency_slot(10_000):
                    pass
        except BaseException as exc:  # noqa: BLE001 - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"unexpected errors under a bound that is never exceeded/denied: {errors!r}"

    total_calls = n_threads * calls_per_thread
    assert counting_rate_lock.enter_count == total_calls, (
        f"expected acquire_rate()'s own rate lock to be entered exactly "
        f"{total_calls} times (once per call), got {counting_rate_lock.enter_count}"
    )
    assert counting_rate_lock.exit_count == total_calls
    # `concurrency_slot` is a context manager wrapping ONE call each --
    # its OWN body takes `_active_lock` twice per invocation (once on
    # entry, once in the `finally` on exit), so double the raw call count.
    assert counting_active_lock.enter_count == total_calls * 2, (
        f"expected concurrency_slot()'s own active lock to be entered "
        f"exactly {total_calls * 2} times (twice per call), got "
        f"{counting_active_lock.enter_count}"
    )
    assert counting_active_lock.exit_count == total_calls * 2

    # Secondary, behavioral sanity check (not the primary mutation signal
    # -- see `_CountingLock`'s own docstring for why).
    assert holder._active == 0, f"expected the in-flight counter back at 0, got {holder._active}"  # noqa: SLF001
    for i in range(n_threads):
        recorded = len(holder._rate_windows.get(f"wp8b-thread-safety-credential-{i}", []))  # noqa: SLF001
        assert recorded == calls_per_thread, (
            f"credential {i}: expected {calls_per_thread} recorded timestamps, got {recorded}"
        )


# ---------------------------------------------------------------------------
# WP-8b review 差し戻し, additional mutation 1 (`{scratchpad}/phase10/
# wp8b-review.md` §4): `test_limiter_state_is_thread_safe` above pins that
# `_active_lock` is ENTERED/EXITED the expected number of times -- but a
# mutation that leaves `with self._active_lock:` in place while moving the
# actual check-then-increment/decrement bodies OUT of it (an empty `with`
# block, still entered/exited once per call) leaves that test green: the
# review measured this directly (`enter_count`/`exit_count` both stayed
# correct under exactly this mutation shape). The test below instruments
# `_active` ITSELF, not the lock, to pin the actual boundaries of the
# critical section -- deterministic, no dependence on thread scheduling.
# ---------------------------------------------------------------------------


class _HeldTrackingLock:
    """Like `_CountingLock` above, but additionally exposes whether the
    lock is CURRENTLY held (`.held`), toggled around the real
    `threading.Lock` it wraps."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.held = False

    def __enter__(self):
        result = self._lock.__enter__()
        self.held = True
        return result

    def __exit__(self, *exc_info):
        self.held = False
        return self._lock.__exit__(*exc_info)


class _ActiveAccessOutsideLock(AssertionError):
    """Raised by `_make_guarded_holder`'s own `_active` property below
    when `_LimitStateHolder`'s in-flight counter is read or written while
    its guarding lock (a `_HeldTrackingLock`) is not currently held."""


def _make_guarded_holder() -> _LimitStateHolder:
    """A live `_LimitStateHolder` whose `_active` attribute is backed by a
    property that raises `_ActiveAccessOutsideLock` the moment it is read
    or written while `holder._active_lock` is not held -- pins the
    CRITICAL SECTION's actual boundaries (what `concurrency_slot`'s check-
    then-increment/decrement bodies are allowed to touch, and when), not
    merely that the lock object itself is entered/exited the right number
    of times somewhere in the method (`test_limiter_state_is_thread_safe`
    above already covers that, separately)."""

    class _GuardedLimitStateHolder(_LimitStateHolder):
        @property
        def _active(self):
            lock = self.__dict__.get("_active_lock")
            if isinstance(lock, _HeldTrackingLock) and not lock.held:
                raise _ActiveAccessOutsideLock("holder._active was READ while _active_lock was not held")
            return self.__dict__.get("_active_value", 0)

        @_active.setter
        def _active(self, value):
            lock = self.__dict__.get("_active_lock")
            if isinstance(lock, _HeldTrackingLock) and not lock.held:
                raise _ActiveAccessOutsideLock("holder._active was WRITTEN while _active_lock was not held")
            self.__dict__["_active_value"] = value

    holder = _GuardedLimitStateHolder()
    holder._active_lock = _HeldTrackingLock()  # noqa: SLF001 - test-only substitution, AFTER __init__
    return holder


def test_concurrency_slot_check_then_increment_is_inside_the_active_lock():
    """Pins the review's own 'additional mutation 1' finding directly: a
    correct `concurrency_slot` call sequence never touches `_active`
    while `_active_lock` (`_HeldTrackingLock`, substituted in by `_make_
    guarded_holder`) reports itself not held, so none of the ordinary
    calls below ever raise.

    Mutation (`cell.py::_LimitStateHolder.concurrency_slot`'s own check-
    then-increment/decrement bodies moved OUTSIDE their `with self.
    _active_lock:` statements, the statements themselves left in place,
    now wrapping nothing): the very first `with holder.concurrency_slot
    (...):` call below raises `_ActiveAccessOutsideLock` immediately --
    this test goes red on contact, deterministically, with no dependence
    on thread scheduling (contrast `test_limiter_state_is_thread_safe`
    above, whose `_CountingLock`-based enter/exit counts stay correct,
    and therefore green, under this exact mutation).
    """
    holder = _make_guarded_holder()

    for _ in range(5):
        with holder.concurrency_slot(10_000):
            pass

    # Bypasses the guard property deliberately (reads the raw backing
    # value directly) -- this sanity check itself runs OUTSIDE any
    # `concurrency_slot` call, so a plain `holder._active` read here would
    # trip the very guard this test relies on, for a completely unrelated
    # (and correct) reason.
    assert holder.__dict__.get("_active_value", 0) == 0  # noqa: SLF001


def test_pool_acquire_is_thread_safe():
    """`BoundedConnectionPool.acquire()`'s own docstring promise --
    "never manufactures a connection past `max_size`" -- rests on the
    create-budget check-then-increment (`acquire()`'s "create a new one,
    if under budget" branch) being taken under `self._lock`. `N` threads,
    released together via a `threading.Barrier`, each call `acquire()`
    exactly once against a fake, no-I/O `_new_connection` (this test needs
    no real PostgreSQL: it is `pool.py`'s own bookkeeping under test, not
    connectivity) with `max_size == N` and NO thread ever releasing during
    the race -- the idle queue therefore starts and stays empty for the
    whole race, so every one of the `N` calls is structurally FORCED
    through that SAME budget-check branch (never the "reuse an idle
    connection" shortcut), taking `self._lock` exactly once each --
    deterministic by construction, not a statistical race (see
    `_CountingLock`'s own docstring on `test_limiter_state_is_thread_safe`
    above for why a live, unassisted data race did not reproduce reliably
    on this machine for the structurally identical `x += 1` pattern).

    Mutation (`pool.py::BoundedConnectionPool.acquire`'s own `with self.
    _lock:` removed from the "create a new one, if under budget" branch,
    its body dedented one level): `counting_lock.enter_count` stays at 0
    (that lock object is never referenced by the mutated code path at
    all) while `pool.acquire()` itself still succeeds for every caller --
    this test's own `counting_lock.enter_count == n` assertion goes red
    immediately, deterministically, verified in `{scratchpad}/phase10/
    wp8b-mutation5.log`.
    """

    class _FakeConnection:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    n = 40
    pool = BoundedConnectionPool(
        "dsn-unused-fake-pool-thread-safety-test.invalid", max_size=n, connect_timeout=1, acquire_timeout=3,
    )
    counting_lock = _CountingLock()
    pool._lock = counting_lock  # noqa: SLF001 - test-only substitution

    created: list[_FakeConnection] = []
    created_append_lock = threading.Lock()

    def _fake_new_connection() -> "_FakeConnection":
        conn = _FakeConnection()
        with created_append_lock:
            created.append(conn)
        return conn

    pool._new_connection = _fake_new_connection  # type: ignore[method-assign]  # noqa: SLF001

    barrier = threading.Barrier(n, timeout=5)
    errors: list[BaseException] = []
    acquired = []
    acquired_lock = threading.Lock()

    def worker():
        try:
            barrier.wait(timeout=5)
            # `max_size == n` and nothing is ever released during this
            # race, so this call can never be satisfied by an idle
            # connection -- it always reaches the lock-guarded
            # create-budget branch.
            conn = pool.acquire()
            with acquired_lock:
                acquired.append(conn)
        except BaseException as exc:  # noqa: BLE001 - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"unexpected acquire() failures under a max_size that admits every caller: {errors!r}"
    assert len(acquired) == n, f"expected all {n} callers to acquire a connection, got {len(acquired)}"

    assert counting_lock.enter_count == n, (
        f"expected the create-budget branch's own lock to be entered exactly "
        f"{n} times (once per caller, none satisfiable from the empty idle "
        f"queue), got {counting_lock.enter_count}"
    )
    assert counting_lock.exit_count == n

    # Secondary, behavioral sanity check (not the primary mutation signal
    # -- see `_CountingLock`'s own docstring above for why): the pool's
    # own bookkeeping is still exactly correct.
    assert len(created) == n, f"expected exactly {n} fake connections created, got {len(created)}"
    assert pool._created == n, f"expected pool._created == {n}, got {pool._created}"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Phase 10 WP-4e (supervisor ruling 2026-09-09, 同型 with r2db-api's own
# `test_credential_persistence.py::test_platform_pool_sized_to_declared_
# concurrency_avoids_premature_503`): the platform pool `main.build_app`
# sizes for `PostgresCredentialStore` used to default to a fixed `pool.
# DEFAULT_MAX_SIZE` (20), entirely disconnected from the declared `max_
# concurrency` ceiling (default 32) -- the same F-1 shape as r2db-api's
# own per-application role pools, applied here to this peer's ONE pooled
# platform store (`config.role_pool_size`'s own docstring: this peer has
# no per-application pool to match -- `backend_postgres.PostgresBackend`
# never pools at all).
# ---------------------------------------------------------------------------


def test_platform_pool_sized_to_thread_limit_avoids_premature_503(platform, credential_app, monkeypatch):
    """Real-PostgreSQL pin for the platform pool's own F-1 shape: with the
    platform pool sized via `role_pool_size(thread_limit)` (the exact
    function `main.build_app` calls -- design docs/design/MULTI_PROCESS_
    WORKER_V0_1.md D-3 (5): the real per-process simultaneous-borrow
    ceiling is the thread limit, never the declared `max_concurrency`),
    `thread_limit` genuinely concurrent `authenticate()` calls against ONE
    credential store are all served (0 x `AuthorizationStateUnavailable`
    denials), even though each call is made to hold its checked-out
    connection for longer than the pool's own `acquire_timeout`.

    Real PostgreSQL, a real `BoundedConnectionPool` -- only `credential_
    store_postgres._execute` (this module's own single execution choke
    point) is monkeypatched to sleep for `hold_s` seconds AFTER the real
    query runs but BEFORE returning, while `_borrow_connection`'s own
    `with` block still holds the checked-out real connection -- so
    `thread_limit` threads genuinely contend for the pool's `max_size`
    slots against a live PostgreSQL server, not a simulation.

    Mutation: hardcoding this test's own `pool` construction back to a
    fixed `max_size=2` regardless of the `thread_limit=6` this test
    configures (or `role_pool_size` returning a fixed 4) turns this red --
    the 3rd+ concurrent `authenticate()` call then waits past `acquire_
    timeout` for a connection none of the first two callers have released
    yet (still sleeping), and raises `AuthorizationStateUnavailable`
    instead of succeeding.
    """
    import concurrent.futures
    import time

    thread_limit = 6
    concurrency = thread_limit
    hold_s = 0.6
    platform_pool_size = role_pool_size(thread_limit)

    pool = BoundedConnectionPool(platform.api_dsn, max_size=platform_pool_size, acquire_timeout=0.3)
    store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-wp4e-platform-pool-0000",
        schema=platform.registry_schema, pool=pool,
    )

    # `issue()` needs the controlplane (full-DML) role -- `store` above,
    # against `platform.api_dsn` (SELECT-only, migration 0002), is the
    # read path this test's own concurrent `authenticate()` calls below
    # exercise, mirroring r2db-api's identical read/write store split.
    writer = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-wp4e-platform-pool-0000",
        schema=platform.registry_schema,
    )
    try:
        _credential_id, secret = writer.issue(credential_app, Role.RUNTIME)
    finally:
        writer.close()

    original_execute = credential_store_postgres_module._execute

    def _slow_execute(cursor, statement, params=()):
        original_execute(cursor, statement, params)
        time.sleep(hold_s)

    monkeypatch.setattr(credential_store_postgres_module, "_execute", _slow_execute)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(store.authenticate, secret) for _ in range(concurrency)]
            results = []
            denials = []
            for future in futures:
                try:
                    results.append(future.result(timeout=10))
                except AuthorizationStateUnavailable as exc:
                    denials.append(exc)
        assert not denials, f"expected 0 AuthorizationStateUnavailable denials at in-flight == declared concurrency, got: {denials!r}"
        assert len(results) == concurrency
        assert all(principal.application_id == credential_app for principal in results)
    finally:
        store.close()


def test_credential_store_authenticates_after_every_idle_pooled_connection_was_ended_by_the_server(platform, credential_app):
    """The credential store shares the pool's dead-connection handling: two
    pooled connections idle, ended by the server (`pg_terminate_backend`,
    the shape of a database restart or an idle disconnect), the pool left
    past `pool.IDLE_PING_THRESHOLD_S` -- the next `authenticate()` calls
    still succeed instead of answering `AuthorizationStateUnavailable` once
    per dead connection.

    mutation (`pool.py`, `_is_dead`): skip the round trip (`if self._ping(
    conn):` becomes `if True:`) -- the first `authenticate()` is handed a
    dead connection and raises `AuthorizationStateUnavailable`."""
    from mitatedb_api import pool as pool_module

    pool = BoundedConnectionPool(platform.api_dsn, max_size=3)
    store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-wp4e-platform-pool-0000",
        schema=platform.registry_schema, pool=pool,
    )
    writer = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-wp4e-platform-pool-0000",
        schema=platform.registry_schema,
    )
    try:
        _credential_id, secret = writer.issue(credential_app, Role.RUNTIME)
    finally:
        writer.close()
    try:
        first, second = pool.acquire(), pool.acquire()
        backend_pids = [first.info.backend_pid, second.info.backend_pid]
        pool.release(first)
        pool.release(second)
        admin = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                for backend_pid in backend_pids:
                    cur.execute("SELECT pg_terminate_backend(%s)", [backend_pid])
                    assert cur.fetchone() == (True,)
        finally:
            admin.close()
        time.sleep(pool_module.IDLE_PING_THRESHOLD_S + 0.3)
        for _ in range(3):
            assert store.authenticate(secret).application_id == credential_app
        assert pool.platform_stats()["sessions"] == 3
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R-101 WP-3 D-8: `create_app`'s own `thread_limit=` middleware wiring.
# No real PostgreSQL needed -- `HttpService` itself only requires a
# `credential_store`/`cell_factory` pair and a `_LimitStateHolder` at
# construction time (`http.py::HttpService.__init__`'s own fail-closed
# guard); these tests never reach `_authenticate`'s own store lookup
# (`ThreadLimitMiddleware` runs before routing, on every http-scope
# request, success or failure alike), so a stand-in (`None`) is enough.
# ---------------------------------------------------------------------------


def _build_light_service() -> "http_module.HttpService":
    limit_holder = _LimitStateHolder()
    return http_module.HttpService(
        None, lambda application_id: None, limit_holder=limit_holder, max_concurrency=FoundationConfig().max_concurrency,
    )


async def _one_capabilities_request(app) -> None:
    """The minimal http-scope request completion conditions 79/etc. call
    "1 回呼ぶ" -- any real http request through the SAME app object is
    enough (`ThreadLimitMiddleware` runs ahead of routing/auth, so an
    eventual 401/500 from the unauthenticated stand-in credential store
    below still exercises it)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.get("/v1/capabilities")


def test_create_app_default_thread_limit_sets_4_on_a_fresh_loop():
    """Completion condition 79.

    mutation M121 (`mitatedb_api/http.py`): `DEFAULT_THREAD_LIMIT = 40`
    -- this test's own `== 4` assertion goes red."""
    import anyio.to_thread

    service = _build_light_service()
    app = http_module.create_app(service, request_bytes_limit=1_048_576)

    async def _scenario() -> int:
        await _one_capabilities_request(app)
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    assert _run(_scenario()) == 4


def test_create_app_rejects_a_non_positive_thread_limit():
    """Review round 1 finding F11 (supervisor ruling 2026-09-28): `create_
    app(thread_limit=...)` rejects zero, a negative int, a non-int
    (`"4"`), and a `bool` (`True` -- `bool` is an `int` subclass in
    Python, rejected explicitly rather than silently accepted as `1`) at
    construction time, before any request is ever served -- a
    misconfigured deployment fails fast at startup instead of every
    request hitting `ThreadLimitMiddleware`'s own attempt to apply an
    invalid value to the loop's limiter.

    mutation M206 (`mitatedb_api/http.py`): drop the validation `if` and
    its `raise ValueError` from `create_app` -- this test's own `pytest.
    raises(ValueError)` assertions go red (`create_app(thread_limit=0)`
    and `create_app(thread_limit=-1)` both return a plain app instead).
    mutation M208 (`mitatedb_api/http.py`, review round 2 finding N2):
    drop the `isinstance(thread_limit, bool) or ` clause from the
    validation -- this test's own `create_app(thread_limit=True)`
    assertion goes red (`True` passes the remaining `isinstance(...,
    int)`/`< 1` checks unrejected, since `bool` is an `int` subclass and
    `True == 1`)."""
    service = _build_light_service()
    with pytest.raises(ValueError, match="thread_limit"):
        http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=0)
    with pytest.raises(ValueError, match="thread_limit"):
        http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=-1)
    with pytest.raises(ValueError, match="thread_limit"):
        http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit="4")
    with pytest.raises(ValueError, match="thread_limit"):
        http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=True)


def test_create_app_thread_limit_none_adds_no_middleware():
    """Completion condition 81.

    mutation M123 (`mitatedb_api/http.py`): add the middleware even when
    `thread_limit is None` -- this test's own `total_tokens == 40`
    (untouched) assertion goes red."""
    import anyio.to_thread

    service = _build_light_service()
    app = http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=None)
    assert not any(m.cls is http_module.ThreadLimitMiddleware for m in app.app.user_middleware)

    async def _scenario() -> int:
        await _one_capabilities_request(app)
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    assert _run(_scenario()) == 40


def test_create_app_explicit_thread_limit_sets_that_value():
    """Completion condition 83.

    mutation M125 (`mitatedb_api/http.py`): the middleware sets `DEFAULT_
    THREAD_LIMIT` instead of the value it was constructed with -- this
    test's own `== 7` assertion goes red (reads `4`)."""
    import anyio.to_thread

    service = _build_light_service()
    app = http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=7)

    async def _scenario() -> int:
        await _one_capabilities_request(app)
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    assert _run(_scenario()) == 7


def test_create_app_middleware_sets_the_limiter_once_per_loop():
    """Completion conditions 86/87: the middleware sets `total_tokens`
    only the first time a given (fresh) loop serves a request through it;
    a DIFFERENT fresh loop gets the same one-time treatment
    independently. `_run` (`asyncio.run`) gives each call its own fresh
    loop, so a manual-reset-then-call-again check within ONE loop needs
    its own scenario, driven on a loop this test creates directly.

    mutation M128 (`mitatedb_api/http.py`): drop the loop-membership
    check so the middleware sets `total_tokens` on EVERY request -- this
    test's own second assertion (still `== 3`, unchanged after a manual
    reset) goes red (would read `4` again).
    mutation M129 (`mitatedb_api/http.py`): track "configured" with a
    single instance-wide flag instead of a per-loop set -- this test's
    own third assertion (loop B independently reaching `4`) goes red."""
    import anyio.to_thread

    service = _build_light_service()
    app = http_module.create_app(service, request_bytes_limit=1_048_576)

    loop_a = asyncio.new_event_loop()
    try:
        loop_a.run_until_complete(_one_capabilities_request(app))

        async def _read() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_a.run_until_complete(_read()) == 4

        async def _reset_and_call_again() -> int:
            anyio.to_thread.current_default_thread_limiter().total_tokens = 3
            await _one_capabilities_request(app)
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_a.run_until_complete(_reset_and_call_again()) == 3
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        loop_b.run_until_complete(_one_capabilities_request(app))

        async def _read_b() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_b.run_until_complete(_read_b()) == 4
    finally:
        loop_b.close()


def test_thread_limit_middleware_call_is_a_coroutine_function():
    """Completion condition 89: `ThreadLimitMiddleware.__call__` is a
    coroutine function.

    mutation M131 (`mitatedb_api/http.py`): make `__call__` a plain
    (non-async) method that itself returns a coroutine -- this test's own
    `iscoroutinefunction` assertion goes red."""
    import inspect

    assert inspect.iscoroutinefunction(http_module.ThreadLimitMiddleware.__call__)


def test_create_app_default_return_shape_matches_thread_limit_none():
    """Completion condition 91: the returned value's own shape is the
    same whether `thread_limit` is left at its default or explicitly
    `None` -- only the middleware list differs.

    mutation M133 (`mitatedb_api/http.py`): wrap the FINAL returned value
    in an extra layer instead of adding to the Starlette middleware list
    -- this test's own `isinstance(app.app, Starlette)` assertion goes
    red."""
    from starlette.applications import Starlette

    service = _build_light_service()
    app_default = http_module.create_app(service, request_bytes_limit=1_048_576)
    app_none = http_module.create_app(service, request_bytes_limit=1_048_576, thread_limit=None)

    assert isinstance(app_default, type(app_none))
    assert isinstance(app_default.app, Starlette)
    assert app_default.app.state.service is service
    default_paths = {r.path for r in app_default.app.routes}
    none_paths = {r.path for r in app_none.app.routes}
    assert default_paths == none_paths
    assert default_paths, "route table must not be empty"


# ---------------------------------------------------------------------------
# D-13: the thread limiter (4, default) bounds how many requests run their
# synchronous section at once, WITHOUT changing concurrency-slot admission
# (still `max_concurrency`, 8 here) or the deadlock-free wait discipline.
# Real, throwaway-provisioned PostgreSQL (`platform`/`app_a`, same recipe
# `test_preauth_concurrency_bound.py::preauth_stack` uses) -- `_authenticate`
# must genuinely succeed so `ApplicationRuntime.capabilities` (the patched
# blocking point) is ever reached at all.
# ---------------------------------------------------------------------------


def test_thread_limit_bounds_synchronous_concurrency_while_slot_admission_stays_at_the_declared_ceiling(platform, app_a):
    """Completion conditions 118/119: with `max_concurrency=8` and
    `create_app`'s own default `thread_limit` (4), 8 concurrent requests
    are all ADMITTED (their concurrency slot is taken on the event-loop
    thread, before any of them ever reaches a worker thread) while at
    most 4 of them ever run their own synchronous section
    (`ApplicationRuntime.capabilities`) at once; a 9th, sent only once
    5-8 have genuinely reached the worker-thread queue (observed
    directly: `current == 4` and `limit_holder._active == 8`, not merely
    inferred from a fixed sleep), is refused with 413 (this peer's own
    `LIMIT_EXCEEDED` -> 413 status mapping, `http.py`'s own `_STATUS_BY_
    CODE`, unlike r2db's 429 -- a pre-existing, unrelated cross-peer
    difference, not something this WP changes; confirmed by the 9th
    response's own `code`/`details.limit_class`); once released, all 8
    complete with 200.

    mutation M158 (`mitatedb_api/http.py`): move the handler's own slot
    acquisition INTO the function delegated to `run_in_threadpool` (so it
    happens AFTER a worker thread is granted) -- only the (up to 4)
    requests that already hold a worker thread would then hold a slot at
    the moment the 9th is sent, so this test's own `limit_holder._active
    == 8` assertion goes red (only 4 are ever admitted at once).
    mutation M159 (`mitatedb_api/http.py`): drop the `total_tokens`
    assignment from the middleware's own `__call__` -- this test's own
    `current == 4` wait loop never observes 4 (all 8 requests run their
    synchronous section concurrently, jumping straight to `current ==
    8`), so its own post-loop assertion goes red."""
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-r101-wp3-thread-limit-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-r101-wp3-thread-limit-0000", schema=platform.registry_schema,
    )
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    concurrency = 8
    config = FoundationConfig(max_concurrency=concurrency, max_requests_per_minute=100_000)
    limit_holder = _LimitStateHolder()
    app_cell = ApplicationCell(app_a.app_id, config=config, backend=backend, limit_holder=limit_holder)

    def _cell_factory(application_id: str):
        assert application_id == app_a.app_id
        return app_cell

    service = http_module.HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=config.max_concurrency)
    app = http_module.create_app(service, request_bytes_limit=1024)
    runtime_id, runtime_bearer = write_store.issue(app_a.app_id, Role.RUNTIME)

    lock = threading.Lock()
    current = 0
    peak = 0
    release = threading.Event()
    original = ApplicationRuntime.capabilities

    def blocking_capabilities(self, *, request_id=None):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        release.wait(timeout=5.0)
        with lock:
            current -= 1
        return original(self, request_id=request_id)

    async def _scenario():
        with mock.patch.object(ApplicationRuntime, "capabilities", blocking_capabilities):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:

                async def _one():
                    return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {runtime_bearer}"})

                tasks = [asyncio.ensure_future(_one()) for _ in range(concurrency)]
                await asyncio.sleep(0)

                # Real worker-thread dispatch needs actual wall-clock time
                # for the OS scheduler to run the up-to-4 threads the
                # limiter grants -- wait for it BEFORE sending the 9th
                # request below, so the 9th is genuinely sent while 5-8
                # are holding their own slot but still queued for a
                # worker thread (never merely inferred from a fixed
                # sleep).
                for _ in range(100):
                    await asyncio.sleep(0.01)
                    with lock:
                        if current == 4:
                            break
                assert current == 4, f"synchronous concurrency never reached the thread limiter's own ceiling (4), observed current={current}"
                assert limit_holder._active == 8, f"all 8 requests must already hold their own concurrency slot, observed _active={limit_holder._active}"

                resp9 = await client.get("/v1/capabilities", headers={"authorization": f"Bearer {runtime_bearer}"})
                assert resp9.status_code == 413, resp9.text
                resp9_body = resp9.json()
                assert resp9_body["code"] == "LIMIT_EXCEEDED", resp9_body
                assert resp9_body["details"]["limit_class"] == "concurrency", resp9_body

                release.set()
                return await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

    try:
        responses = _run(_scenario())
    finally:
        backend.close()
        read_store.close()
        write_store.close()

    assert peak == 4, f"synchronous concurrency must be bounded to the thread limiter (4), observed peak={peak}"
    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == concurrency, statuses


# ---------------------------------------------------------------------------
# design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5): `main.py`'s own
# `_thread_limit_from_env` (a registered isomorphism target, kept as its
# own body) and `config.thread_limit_from_env` (the reader `control_
# composition.py`/`ops._declared_pool_size` use) agree on every input.
# ---------------------------------------------------------------------------


def _load_main_thread_limit_from_env():
    """Loads `_thread_limit_from_env` from `mitatedb_api/main.py`'s own
    source via AST + isolated exec -- never a plain `import mitatedb_api.
    main`, which would run that module's own module-level `app =
    build_app()` (needs real env vars and a live platform database). The
    function references nothing else at module scope (a pure parse/raise),
    so its own AST node exec'd in an isolated namespace is sufficient."""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api" / "main.py"
    tree = ast.parse(path.read_text())
    func_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_thread_limit_from_env")
    isolated = ast.Module(body=[func_node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace: dict = {}
    exec(compile(isolated, str(path), "exec"), namespace)
    return namespace["_thread_limit_from_env"]


def test_thread_limit_from_env_agrees_with_the_shared_config_reader():
    """Completion condition 128b: `main.py`'s own `_thread_limit_from_env`
    and `config.thread_limit_from_env` read the SAME variable
    (`MITATEDB_THREAD_LIMIT`) with the SAME discipline -- same return value
    for unset, empty and a valid positive integer, and both raise
    `ValueError` for `0`, a negative integer and a non-numeric value.

    mutation M128b (`config.py`): `thread_limit_from_env`'s own `value <=
    0` branch becomes `value < 0` -- `main.py`'s own copy still raises for
    `"0"`, so the agreement check for that input goes red."""
    from mitatedb_api.config import thread_limit_from_env as shared_thread_limit_from_env

    main_thread_limit_from_env = _load_main_thread_limit_from_env()
    checked = 0
    for env in ({}, {"MITATEDB_THREAD_LIMIT": ""}, {"MITATEDB_THREAD_LIMIT": "6"}):
        assert main_thread_limit_from_env(env, "MITATEDB_THREAD_LIMIT", 4) == shared_thread_limit_from_env(
            env, "MITATEDB_THREAD_LIMIT", 4
        )
        checked += 1
    for raw in ("0", "-3", "abc"):
        env = {"MITATEDB_THREAD_LIMIT": raw}
        main_exc = shared_exc = None
        try:
            main_thread_limit_from_env(env, "MITATEDB_THREAD_LIMIT", 4)
        except ValueError as exc:
            main_exc = exc
        try:
            shared_thread_limit_from_env(env, "MITATEDB_THREAD_LIMIT", 4)
        except ValueError as exc:
            shared_exc = exc
        assert (main_exc is None) == (shared_exc is None), (
            f"raw={raw!r}: main.py's own reader raised {main_exc!r}, config.thread_limit_from_env raised "
            f"{shared_exc!r} -- disagreement"
        )
        checked += 1
    assert checked == 6
