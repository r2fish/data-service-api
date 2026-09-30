"""Phase 10 WP-8c (design D-8 (3), review F-2 -- `{scratchpad}/phase10/
wp8a-review.md`): the data plane now takes its `concurrency` slot BEFORE
`_authenticate`, mirroring r2db `service.py::DataService.
acquire_concurrency_slot`'s own identical purpose and this peer's own
control-plane precedent for pre-auth admission. Before this WP, an
unauthenticated flood (invalid bearer tokens) never touched `cell.
_LimitStateHolder._active` at all -- `_authenticate`'s own
`PostgresCredentialStore` round trip absorbed unbounded concurrent demand,
regardless of `config.max_concurrency`.

Independent implementation (no code sharing with `r2db-api`'s own
`test_preauth_concurrency_bound.py`), following the SAME general recipe
this peer's own `test_threadpool_offload.py` already established: plain
`def` test functions each driving one `asyncio.run(_scenario())`, a real
throwaway-provisioned PostgreSQL application (`test_postgres.py`'s
`platform`/`app_a` fixtures), and a monkeypatched blocking point to force
genuine concurrent overlap deterministically.

Disclosed scope limit (`HttpService.__init__`'s own comment, `main.py`'s
own wiring comment): this WP's new pre-authentication admission is wired
into `main.py`'s real composition root, but NOT into either conformance
adapter's own `HttpService(...)` construction (`conformance_adapter_
mitatedb_http.py`, untouched by this WP -- "conformance adapters は触ら
ない"), which therefore keeps the OLD post-authentication-only concurrency
enforcement, unaffected by this WP. This test file builds its OWN small,
explicitly-wired `HttpService` (mirroring `main.py`'s own wiring) to
exercise the real, configured behaviour end to end.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import queue
import textwrap
import threading
import types

import httpx
import pytest

import mitatedb_api.http as http_module
from mitatedb_api.application_audit import ApplicationAuditSink
from mitatedb_api.audit_dispatch import AuditRouter
from mitatedb_api.auth import Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell, _LimitStateHolder
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.http import HttpService, create_app

from .test_postgres import app_a, platform  # noqa: F401 - fixture reuse, same convention `test_http.py` uses

BASE_URL = "http://mitatedb-preauth-concurrency-test.invalid"


@pytest.fixture
def preauth_stack(platform, app_a):
    """The SAME general shape `test_http.py::app_a_stack` builds, with two
    additions this WP needs: a small, explicit `max_concurrency` (via a
    dedicated `FoundationConfig`) and the `limit_holder`/`max_concurrency`
    keywords `HttpService` now accepts (`http.py`'s own comment) -- without
    both, `acquire_concurrency_slot()` is the documented no-op
    (`HttpService.__init__`'s own comment), and this file's own tests
    would have nothing real to observe.
    """
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-preauth-concurrency-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-preauth-concurrency-0000", schema=platform.registry_schema,
    )
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    config = FoundationConfig(max_concurrency=2, max_requests_per_minute=100_000)
    limit_holder = _LimitStateHolder()
    # An inspectable router (same convention `test_http.py::app_a_stack_
    # with_audit` uses), not the private, unshared default -- so condition
    # 2's test can read `router.durable_sink.events()` back directly.
    router = AuditRouter(ApplicationAuditSink())
    cell = ApplicationCell(app_a.app_id, config=config, backend=backend, limit_holder=limit_holder, audit_router=router)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    # `audit_router=router` -- the SAME router `cell` above carries -- so a
    # mutation that adds a durable-audit write to `HttpService.
    # acquire_concurrency_slot`'s own refusal path (the realistic place for
    # one: `_LimitStateHolder` itself holds no audit router at all) is
    # observable through `router.durable_sink.events()`, this file's own
    # single read path for durable rows.
    service = HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=config.max_concurrency, audit_router=router)
    app = create_app(service, request_bytes_limit=1024)

    runtime_id, runtime_bearer = write_store.issue(app_a.app_id, Role.RUNTIME)

    stack = types.SimpleNamespace(
        app=app, app_id=app_a.app_id, runtime_bearer=runtime_bearer,
        service=service, cell=cell, router=router, write_store=write_store, read_store=read_store,
    )
    try:
        yield stack
    finally:
        backend.close()
        read_store.close()
        write_store.close()


async def _query(client: httpx.AsyncClient, bearer: str) -> httpx.Response:
    return await client.get("/v1/catalog", headers={"authorization": f"Bearer {bearer}"})


# ---------------------------------------------------------------------------
# Completion condition 1: an unauthenticated flood of N = concurrency + 1
# concurrent requests is bounded by `concurrency` -- exactly one gets
# LIMIT_EXCEEDED/`limit_class: concurrency`, and NONE ever reach a
# credential-store-outage-shaped denial (they never got far enough to
# exhaust anything `_authenticate` itself depends on).
# ---------------------------------------------------------------------------


def test_unauthenticated_flood_is_bounded_by_concurrency(preauth_stack):
    """`http_module._authenticate` is monkeypatched to block on a
    `threading.Event` so `max_concurrency` (= 2) invalid-bearer requests
    can be forced to pile up INSIDE it simultaneously -- proof the
    concurrency slot was already taken before this call -- before the
    THIRD is fired and observed to be refused immediately, while the first
    two are still blocked.

    Mutation (condition 1's own pinned mutation, manifest table row 1):
    moving `service.acquire_concurrency_slot()` in `http.py` back to AFTER
    `_authenticate` (i.e. reverting this WP) turns this red -- every one
    of the 3 concurrent invalid-bearer requests then reaches
    `_authenticate` unconditionally, so the third never receives `LIMIT_
    EXCEEDED`/`concurrency` at all.
    """
    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_authenticate = http_module._authenticate

    def blocking_authenticate(request):
        entered.put(1)
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held requests would hang forever"
        return original_authenticate(request)

    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preauth_stack.app), base_url=BASE_URL) as client:
            tasks = [asyncio.create_task(_query(client, "invalid-cred.invalid-secret")) for _ in range(2)]
            for _ in range(500):
                if entered.qsize() >= 2:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= 2, "not all held requests reached the blocked authenticate call"

            extra_response = await _query(client, "invalid-cred.invalid-secret")
            assert extra_response.status_code == 413, extra_response.text
            body = extra_response.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            release.set()
            held_responses = await asyncio.gather(*tasks)
            for response in held_responses:
                # Invalid credential -> AUTH_INVALID, never masked by a
                # limiter refusal now that the slot each held request
                # reserved is released on its own way out.
                assert response.json()["code"] == "AUTH_INVALID", response.text

    http_module._authenticate = blocking_authenticate
    try:
        asyncio.run(_scenario())
    finally:
        http_module._authenticate = original_authenticate


# ---------------------------------------------------------------------------
# Completion condition 2: a pre-authentication concurrency denial is never
# durably audited.
# ---------------------------------------------------------------------------


def test_preauth_concurrency_denial_is_never_durably_audited(preauth_stack):
    """Fills the (tiny, `max_concurrency=2`) declared bound with BOTH held
    request, then observes that the request refused by the pre-auth
    admission gate adds no row to `cell._LimitStateHolder`'s own owner
    process's durable audit trail. This peer's own durable dispatch is
    per-cell (`ApplicationCell.__audit_router`), so this reads the SAME
    `AuditRouter`/`ApplicationAuditSink` `test_http.py::app_a_stack_with_
    audit`'s own docstring already establishes as this file's read path
    for durable rows.

    Mutation (condition 2's own pinned mutation, manifest table row 2):
    `_LimitStateHolder` itself holds no audit router at all (only
    `ApplicationCell` does) -- the realistic place a durable-audit write
    could be mistakenly added to this refusal path is `HttpService.
    acquire_concurrency_slot` in `http.py`, which DOES hold one
    (`self._audit_router`). Wrapping its own `with self._limit_holder.
    acquire_concurrency_slot(...)` in a `try/except` that calls
    `self._audit_router.durable_sink.append(...)` (unconditionally, not
    through `route_denial`, whose own `reason_code not in DURABLE_DENIAL_
    CODES` filter would otherwise make a `route_denial(reason_code=
    "LIMIT_EXCEEDED", ...)`-shaped mutation silently a no-op here too --
    `LIMIT_EXCEEDED` is not itself a durable-denial-class code on this
    peer, matching the rate limiter's own identical exemption) before
    re-raising turns this red -- the snapshot count changes.
    """
    router = preauth_stack.router
    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_authenticate = http_module._authenticate

    def blocking_authenticate(request):
        entered.put(1)
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held request would hang forever"
        return original_authenticate(request)

    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preauth_stack.app), base_url=BASE_URL) as client:
            # `max_concurrency=2` (the fixture's own bound): fill BOTH slots
            # before observing the THIRD request's own refusal.
            hold_tasks = [asyncio.ensure_future(_query(client, preauth_stack.runtime_bearer)) for _ in range(2)]
            for _ in range(500):
                if entered.qsize() >= 2:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= 2, "not all held requests reached the blocked authenticate call"

            before = len(router.durable_sink.events())
            extra_response = await _query(client, preauth_stack.runtime_bearer)
            assert extra_response.status_code == 413, extra_response.text
            assert extra_response.json()["details"]["limit_class"] == "concurrency"
            after = len(router.durable_sink.events())
            assert after == before, "a pre-authentication concurrency denial was durably audited"

            release.set()
            held_responses = await asyncio.gather(*hold_tasks)
            for held_response in held_responses:
                assert held_response.status_code == 200, held_response.text

    http_module._authenticate = blocking_authenticate
    try:
        asyncio.run(_scenario())
    finally:
        http_module._authenticate = original_authenticate


# ---------------------------------------------------------------------------
# WP-8c review F-1 (supervisor ruling 2026-09-09): a request that ENDS in an
# exception -- `AUTH_INVALID` (401) from `_authenticate`, or `VALIDATION_
# FAILED` (400) from body parsing -- must still release the pre-auth slot it
# reserved, exactly like a normally-served (200) request does. Both sit
# strictly INSIDE `service.acquire_concurrency_slot()`'s own `with` block
# (every handler body, `http.py`) and propagate out through it, proving
# `_LimitStateHolder.acquire_concurrency_slot`'s own `finally` block
# (`cell.py`) runs on this exception path too, not only the success path.
# ---------------------------------------------------------------------------


def test_slot_is_released_after_a_401_ending_request(preauth_stack):
    """`max_concurrency + 1` (= 3, `preauth_stack`'s own bound) SEQUENTIAL
    invalid-bearer requests -- each one ends in `_authenticate` raising
    `AuthenticationError` -> `AUTH_INVALID` (401), strictly INSIDE
    `service.acquire_concurrency_slot()`'s own `with` block, never
    touching `ApplicationCell._limit_gate` at all (`_authenticate` itself
    fails first). If the slot each one reserved were never released on
    this exception path, the counter would climb past `max_concurrency`
    from nothing but a flood of invalid bearer tokens -- no authenticated
    caller involved at all -- and a later iteration would see `LIMIT_
    EXCEEDED`/`concurrency` (413) instead of `AUTH_INVALID` (401): a
    permanent, unauthenticated DoS against the whole deployment.

    Mutation (review F-1's own pinned mutation): changing `_LimitState
    Holder.acquire_concurrency_slot`'s `finally` block (`cell.py`) to
    decrement only on the SUCCESS path turns this red -- by the third
    iteration the counter never comes back down, and it (and every
    iteration after it) is denied `LIMIT_EXCEEDED` instead of `AUTH_
    INVALID`.
    """
    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preauth_stack.app), base_url=BASE_URL) as client:
            for attempt in range(3):
                response = await _query(client, "invalid-cred.invalid-secret")
                assert response.status_code == 401, f"attempt {attempt}: {response.text}"
                assert response.json()["code"] == "AUTH_INVALID", f"attempt {attempt}: {response.text}"

    asyncio.run(_scenario())


def test_slot_is_released_after_a_validation_failed_ending_request(preauth_stack):
    """`max_concurrency + 1` (= 3) SEQUENTIAL requests with a VALID bearer
    but a malformed (non-JSON) body -- each one authenticates
    successfully, then ends in `_read_json_object` raising `Validation
    Error` -> `VALIDATION_FAILED` (400), still strictly inside the SAME
    `with` block (`http.py::post_query`'s own body-read call comes AFTER
    `_authenticate`, both inside the same `with`, never reaching `session.
    read`/`ApplicationCell._limit_gate` at all). Same mutation, same
    theory as the 401 test immediately above, exercising the OTHER
    exception shape review F-1 names ending a request further along
    inside the same `with` block.
    """
    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preauth_stack.app), base_url=BASE_URL) as client:
            for attempt in range(3):
                response = await client.post(
                    "/v1/data/notes/query",
                    headers={"authorization": f"Bearer {preauth_stack.runtime_bearer}"},
                    content=b"not-json-at-all",
                )
                assert response.status_code == 400, f"attempt {attempt}: {response.text}"
                assert response.json()["code"] == "VALIDATION_FAILED", f"attempt {attempt}: {response.text}"

    asyncio.run(_scenario())


# ---------------------------------------------------------------------------
# WP-8c review F-3 (supervisor ruling 2026-09-09, updating 裁定 4 for the
# HTTP plane): `test_application_plane_limits.py::test_gate_denies_requests_
# per_minute_before_concurrency`'s own docstring pins 裁定 4 (監督裁定
# 2026-09-06) at the CELL level (a direct, in-process `cell._limit_gate`
# call, no HTTP boundary involved): rate is checked before concurrency, so
# a request BOTH rate-exhausted AND concurrency-exhausted is denied
# `requests_per_minute`.
#
# On the HTTP plane, this WP introduced a pre-authentication, deployment-
# wide `concurrency` slot (`service.acquire_concurrency_slot()`, taken
# BEFORE `_authenticate`) that is now evaluated ahead of the per-credential
# `requests_per_minute` window, which stays keyed by credential and
# therefore stays reachable only AFTER authentication succeeds. Consequently,
# on the HTTP plane specifically, the SAME both-exhausted request is now
# denied `concurrency`, not `requests_per_minute` -- the OPPOSITE of 裁定
# 4's own cell-level order. This is not a contradiction of 裁定 4 (which
# governs, and remains true for, a direct cell-level call reaching neither
# `http.py` nor this new pre-auth slot at all); it is a SEPARATE ruling for
# the HTTP plane specifically, pinned here, isomorphically to r2db's own
# HTTP-plane test of the same name.
# ---------------------------------------------------------------------------


@pytest.fixture
def preauth_stack_rate_vs_concurrency(platform, app_a):
    """The SAME general stack `preauth_stack` above builds, with `max_
    concurrency=1`/`max_requests_per_minute=1` instead of (2 / 100_000) --
    both bounds trivially exhaustible with a SECOND credential, which this
    file's own HTTP-plane order test (immediately below) needs. Own copy
    (not a parametrization of `preauth_stack` above), for the same reason
    `concurrency_slot`/`acquire_concurrency_slot` in `cell.py` keep their
    own separate check-then-increment block rather than sharing one
    (`acquire_concurrency_slot`'s own docstring): independent, readable,
    and never at risk of a future edit to one silently changing the
    other's fixture behaviour."""
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-preauth-concurrency-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-preauth-concurrency-0000", schema=platform.registry_schema,
    )
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    config = FoundationConfig(max_concurrency=1, max_requests_per_minute=1)
    limit_holder = _LimitStateHolder()
    router = AuditRouter(ApplicationAuditSink())
    cell = ApplicationCell(app_a.app_id, config=config, backend=backend, limit_holder=limit_holder, audit_router=router)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    service = HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=config.max_concurrency, audit_router=router)
    app = create_app(service, request_bytes_limit=1024)

    _, bearer_a = write_store.issue(app_a.app_id, Role.RUNTIME)
    _, bearer_b = write_store.issue(app_a.app_id, Role.RUNTIME)

    stack = types.SimpleNamespace(
        app=app, app_id=app_a.app_id, bearer_a=bearer_a, bearer_b=bearer_b,
        service=service, cell=cell, router=router, write_store=write_store, read_store=read_store,
    )
    try:
        yield stack
    finally:
        backend.close()
        read_store.close()
        write_store.close()


def test_http_plane_denies_concurrency_before_requests_per_minute(preauth_stack_rate_vs_concurrency):
    """A request that is BOTH `requests_per_minute`-exhausted (for ITS OWN
    credential, `bearer_a`) AND `concurrency`-exhausted (the deployment-
    wide pre-auth slot, held for real by a genuinely DIFFERENT,
    concurrently in-flight request under `bearer_b`) is denied
    `concurrency`, not `requests_per_minute`, on the HTTP surface -- the
    order this WP's own `http.py` module comment declares, restated here
    as the supervisor's own explicit HTTP-plane ruling (F-3) rather than
    merely an implementation detail nobody pinned.

    `bearer_a`'s own single `requests_per_minute` unit is consumed by one
    ordinary, unblocked GET /v1/catalog request FIRST. `bearer_b` then
    holds the sole `concurrency` slot for real (`ApplicationRuntime.
    catalog` monkeypatched to block on its FIRST invocation only,
    mirroring `test_concurrency_hold_spans_the_gap_between_authentication_
    and_dispatch` above) -- `bearer_b`'s own rate window is untouched, so
    its request reaches the pre-auth slot honestly (not itself rate-
    denied) and holds it. `bearer_a` then fires again: its own rate
    window is exhausted AND the sole concurrency slot is held by `bearer_
    b`, at the same instant -- this is the completion condition itself.
    The block is call-counted (blocks only the FIRST call, every later
    call goes straight to the REAL `catalog`) rather than unconditional:
    `bearer_a`'s own second request must be free to reach the real,
    unmutated `ApplicationCell._limit_gate` machinery the instant it is
    not turned away earlier by the HTTP-level pre-auth slot -- an
    unconditional block would instead hang IT too (`ApplicationRuntime.
    catalog` is patched on the CLASS, shared across every session), a
    timeout artifact indistinguishable from a genuine denial.

    Mutation: removing the pre-auth `with service.acquire_concurrency_
    slot():` wrapper from `get_catalog` entirely (a full revert of this
    handler to its pre-WP-8c shape) turns this red -- `bearer_b`'s own
    blocked (first) call then holds NO slot of any kind (the monkeypatch
    intercepts before `ApplicationCell._limit_gate` is ever reached), so
    `bearer_a`'s own second request sails straight through to `_
    authenticate` (succeeding) and then `_limit_gate`, whose own `acquire_
    rate` call precedes its `concurrency_slot` call -- `bearer_a`'s own
    already-exhausted rate window is denied FIRST, flipping the response
    to `requests_per_minute`, not `concurrency`.
    """
    from mitatedb_api.cell import ApplicationRuntime

    stack = preauth_stack_rate_vs_concurrency
    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_catalog = ApplicationRuntime.catalog
    call_count = {"n": 0}

    def blocking_catalog(self, *, request_id=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            entered.put(1)
            released = release.wait(timeout=5.0)
            assert released, "release was never set -- the held request would hang forever"
        return original_catalog(self, request_id=request_id)

    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url=BASE_URL) as client:
            # Exhaust bearer_a's own requests_per_minute window with one
            # ordinary, unblocked request.
            first = await _query(client, stack.bearer_a)
            assert first.status_code == 200, first.text

            # Hold the SOLE concurrency slot with bearer_b -- a genuinely
            # DIFFERENT credential, whose own rate window is untouched.
            ApplicationRuntime.catalog = blocking_catalog
            hold_task = asyncio.ensure_future(_query(client, stack.bearer_b))
            for _ in range(500):
                if entered.qsize() >= 1:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= 1, "the held request never reached the blocked catalog call"

            # bearer_a fires again: its OWN rate window is exhausted AND
            # the sole concurrency slot is held by bearer_b, at the same
            # instant.
            extra_response = await _query(client, stack.bearer_a)
            assert extra_response.status_code == 413, extra_response.text
            body = extra_response.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            release.set()
            held_response = await hold_task
            assert held_response.status_code == 200, held_response.text

    try:
        asyncio.run(_scenario())
    finally:
        ApplicationRuntime.catalog = original_catalog


# ---------------------------------------------------------------------------
# Completion condition 4, behavioural half: the slot the first N requests
# reserved before their own `_authenticate` call is still held, this far
# past it -- proven by stalling them right after dispatch begins and
# observing a fresh request is still refused.
# ---------------------------------------------------------------------------


def test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch(preauth_stack):
    """`ApplicationRuntime.catalog` (called strictly AFTER `_authenticate`
    has already returned) is monkeypatched to block, mirroring `test_
    threadpool_offload.py::test_sync_section_runs_off_the_event_loop`'s own
    stall technique. `max_concurrency` (= 2) VALID requests are driven
    into that gap and held there; a THIRD valid request fired while they
    are stuck there must still see `LIMIT_EXCEEDED`/`concurrency`.
    """
    from mitatedb_api.cell import ApplicationRuntime

    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_catalog = ApplicationRuntime.catalog

    def blocking_catalog(self, *, request_id=None):
        entered.put(1)
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held requests would hang forever"
        return original_catalog(self, request_id=request_id)

    async def _scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preauth_stack.app), base_url=BASE_URL) as client:
            tasks = [asyncio.create_task(_query(client, preauth_stack.runtime_bearer)) for _ in range(2)]
            for _ in range(500):
                if entered.qsize() >= 2:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= 2, "not all held requests reached the blocked catalog call"

            extra_response = await _query(client, preauth_stack.runtime_bearer)
            assert extra_response.status_code == 413, extra_response.text
            body = extra_response.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            release.set()
            held_responses = await asyncio.gather(*tasks)
            for response in held_responses:
                assert response.status_code == 200, response.text

    with_patch = ApplicationRuntime.catalog
    ApplicationRuntime.catalog = blocking_catalog
    try:
        asyncio.run(_scenario())
    finally:
        ApplicationRuntime.catalog = original_catalog


# ---------------------------------------------------------------------------
# Completion condition 4, structural half. WP-8a review F-4's own finding
# applies here too: a "release right after `_authenticate` returns, then
# immediately re-acquire" mutation has NO `await` between the release and
# the re-acquire, so no other coroutine can ever be scheduled into that
# gap to observe it empty -- not a race a black-box concurrent-request
# test can force red. The fix is the same one `test_threadpool_offload.py`
# already established for this class of problem: PIN THE SHAPE OF THE
# SOURCE (an AST scan) instead of trying to race it.
# ---------------------------------------------------------------------------


def _unwrap_endpoint(wrapped):
    """`http.py::_endpoint` wraps each handler in a `wrapped(request)`
    closure with no `functools.wraps` -- the real handler is reachable as
    the `handler` free variable `wrapped`'s own closure captures."""
    freevars = wrapped.__code__.co_freevars
    index = freevars.index("handler")
    return wrapped.__closure__[index].cell_contents


def _parse_handler(func) -> ast.AsyncFunctionDef:
    """The parsed `ast.AsyncFunctionDef` for `func`'s own real source (an
    already-unwrapped handler, `_unwrap_endpoint`'s own return value)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    function_def = tree.body[0]
    assert isinstance(function_def, ast.AsyncFunctionDef), f"{func!r} is not an async def"
    return function_def


def _acquire_concurrency_slot_with_blocks(function_def: ast.AsyncFunctionDef) -> list[ast.With]:
    """Every top-level `with service.acquire_concurrency_slot():` statement
    in `function_def`'s own body."""
    return [
        stmt for stmt in function_def.body
        if isinstance(stmt, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "acquire_concurrency_slot"
            for item in stmt.items
        )
    ]


def _authenticate_call_nodes(node: ast.AST) -> list[ast.Call]:
    """WP-8c review F-4 (supervisor ruling 2026-09-09, "slot 取得が
    `_authenticate` 呼び出しより前" -- strengthens condition 4's own AST
    pin to actually check the ORDER its docstring claims, not merely a
    block count): every `Call` ANYWHERE inside `node`'s own subtree that
    genuinely invokes `_authenticate` -- either directly (`session =
    _authenticate(request)`, the `get_capabilities`/`get_catalog`/`post_
    cross_entity_mutate`/`post_audit_query` shape) or via `run_in_
    threadpool` (`session = await run_in_threadpool(_authenticate,
    request)`, the `post_query`/`post_mutate`/`post_schema` shape -- the
    bare `_authenticate` NAME as the first positional argument is what
    actually gets invoked once the delegated thread runs, so it counts
    here too). `ast.walk` reaches a `Call` wrapped in `Await` the same as
    an unwrapped one -- `Await` is simply an ancestor node in the SAME
    subtree walk, not something that needs separate unwrapping."""
    calls: list[ast.Call] = []
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        func = candidate.func
        if isinstance(func, ast.Name) and func.id == "_authenticate":
            calls.append(candidate)
        elif (
            isinstance(func, ast.Name) and func.id == "run_in_threadpool"
            and candidate.args and isinstance(candidate.args[0], ast.Name) and candidate.args[0].id == "_authenticate"
        ):
            calls.append(candidate)
    return calls


@pytest.mark.parametrize(
    "handler_name",
    [
        "get_capabilities", "post_query", "post_mutate", "get_catalog",
        "post_schema", "post_cross_entity_mutate", "post_audit_query",
    ],
)
def test_concurrency_slot_is_acquired_exactly_once_per_handler(handler_name: str):
    """Each of the 7 data-plane HTTP handlers enters `service.
    acquire_concurrency_slot()` LEXICALLY EXACTLY ONCE, spanning both its
    own `_authenticate` call and its own eventual business call -- never
    released and re-entered a second time in between.

    Mutation (condition 4's own pinned mutation, manifest table row 4,
    restated as a source-shape edit for the reason given above): splitting
    a handler's single `with service.acquire_concurrency_slot():` block
    into two turns this red immediately: `len(blocks) == 2`, not 1.

    WP-8c review F-4 (supervisor ruling 2026-09-09, "slot 取得が
    `_authenticate` 呼び出しより前"): `len(blocks) == 1` alone does not
    check what this docstring (and the manifest's own completion condition
    4) actually claims -- a handler edited to call `_authenticate` BEFORE
    the `with` statement (hoisted entirely out of it) would still show
    exactly ONE `with service.acquire_concurrency_slot():` block and pass
    the count check alone, while no longer spanning authentication at all
    (a real regression: the pre-auth slot would then gate nothing an
    unauthenticated flood of invalid bearer tokens ever reaches -- review
    F-2's own original gap, reopened). The two assertions below close
    that: EVERY genuine call to `_authenticate` anywhere in this handler's
    own body must sit INSIDE the located `with` block, and at least one
    must -- together, "the slot acquisition precedes (wraps) every
    `_authenticate` call this handler makes", never the reverse.

    Mutation: hoisting `session = await run_in_threadpool(_authenticate,
    request)` (or the bare-call form) to run BEFORE `with service.
    acquire_concurrency_slot():` in any of the 7 handlers turns this red
    -- that call now sits OUTSIDE the located block, caught by the second
    assertion, even though `len(blocks)` alone would stay 1 and miss it.
    """
    handler = _unwrap_endpoint(getattr(http_module, handler_name))
    function_def = _parse_handler(handler)
    blocks = _acquire_concurrency_slot_with_blocks(function_def)
    assert len(blocks) == 1, (
        f"{handler_name} must enter `service.acquire_concurrency_slot()` exactly once, lexically spanning its "
        f"whole body; found {len(blocks)} separate `with` blocks"
    )
    block = blocks[0]
    calls_inside = _authenticate_call_nodes(block)
    assert calls_inside, (
        f"{handler_name}'s own `with service.acquire_concurrency_slot():` block does not contain a real "
        f"`_authenticate` call anywhere inside it -- the slot no longer spans authentication"
    )
    calls_anywhere = _authenticate_call_nodes(function_def)
    calls_outside = [call for call in calls_anywhere if call not in calls_inside]
    assert not calls_outside, (
        f"{handler_name} calls `_authenticate` OUTSIDE its own `with service.acquire_concurrency_slot():` "
        f"block -- the concurrency slot no longer precedes authentication for at least one call"
    )
