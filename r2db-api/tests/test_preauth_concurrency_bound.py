"""Phase 10 WP-8c (design D-8 (3), review F-2 -- `{scratchpad}/phase10/
wp8a-review.md`): the data plane now takes its `concurrency` slot BEFORE
`_authenticate`, mirroring the control plane's own pre-auth `check_rate()`
admission (`control_http.py`'s module header). Before this WP, an
unauthenticated flood (invalid bearer tokens) never touched `DataService.
_active` at all -- `_authenticate`'s own worker-thread and platform-
credential-pool demand grew unbounded by `limits.concurrency`, up to
anyio's own thread-limiter ceiling (40), so legitimate authenticated
callers could see `AUTH_STATE_UNAVAILABLE`/503 once a real platform pool
was exhausted.

Independent implementation (no code sharing with `MitateDB-api`'s own
`test_preauth_concurrency_bound.py`), following the SAME general recipe:
build a small, deterministic `DataService` (in-memory `CredentialStore`,
no real Postgres needed for this layer's own HTTP-boundary behaviour),
drive it over `httpx.ASGITransport` exactly like `test_threadpool_offload.
py` already does, and use a monkeypatched blocking point to force genuine
concurrent overlap deterministically rather than relying on scheduling
luck.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import queue
import textwrap
import threading
from contextlib import asynccontextmanager

import httpx
import pytest

from r2db_api import http as http_module
from r2db_api.auth import CredentialStore
from r2db_api.http import create_app
from r2db_api.limits import ResourceLimits
from r2db_api.service import ControlAuthority, DataService

pytestmark = pytest.mark.anyio

BASE_URL = "http://r2db.example.invalid"
PEPPER = "synthetic-test-pepper-preauth-concurrency-0000"


def _build_service(**limit_overrides) -> DataService:
    credentials = CredentialStore(pepper=PEPPER)
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    limits = ResourceLimits(**limit_overrides)
    service = DataService(credentials, limits=limits)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    return service


def _auth(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


@asynccontextmanager
async def _client(service: DataService):
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


async def _query(client: httpx.AsyncClient, secret: str) -> httpx.Response:
    return await client.post("/v1/data/notes/query", headers=_auth(secret), json={"select": ["id"]})


# ---------------------------------------------------------------------------
# Completion condition 1: an unauthenticated flood of N = concurrency + 1
# concurrent requests is bounded by `concurrency` -- exactly one gets
# LIMIT_EXCEEDED/`limit_class: concurrency`, and NONE ever reach
# AUTH_STATE_UNAVAILABLE/503 (they never got far enough to exhaust anything
# `_authenticate` itself depends on).
# ---------------------------------------------------------------------------


async def test_unauthenticated_flood_is_bounded_by_concurrency():
    """`_authenticate` is monkeypatched to block on a `threading.Event` so
    N = concurrency invalid-bearer requests can be forced to pile up INSIDE
    it simultaneously (proving the concurrency slot was already taken
    before this call, not merely fast-failing sequentially) before the
    N+1'th is fired and observed to be refused immediately, while the first
    N are still blocked.

    Mutation (condition 1's own pinned mutation, manifest table row 1):
    moving `service.acquire_concurrency_slot()` in `http.py` back to AFTER
    `_authenticate` (i.e. reverting this WP) turns this red -- every one of
    the N+1 concurrent invalid-bearer requests then reaches `_authenticate`
    unconditionally (nothing gates it beforehand), so the N+1'th never
    receives `LIMIT_EXCEEDED`/`concurrency` at all; it blocks in the SAME
    monkeypatched `_authenticate` just like the others and eventually
    returns `AUTH_INVALID`, not the pre-auth refusal this test asserts.
    """
    concurrency = 3
    service = _build_service(concurrency=concurrency, requests_per_minute=100_000)
    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_authenticate = http_module._authenticate

    def blocking_authenticate(request, svc):
        entered.put(1)
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held requests would hang forever"
        return original_authenticate(request, svc)

    http_module._authenticate = blocking_authenticate
    try:
        async with _client(service) as client:
            tasks = [asyncio.create_task(_query(client, "invalid-cred.invalid-secret")) for _ in range(concurrency)]
            # Wait until all `concurrency` requests are genuinely INSIDE the
            # blocked `_authenticate` call at once -- the observable proof
            # that each one already passed the pre-auth concurrency gate
            # before reaching authentication. Polled with `await asyncio.
            # sleep(...)` (never a blocking `Queue.get`) so the event loop
            # this test's own coroutine shares with the tasks above keeps
            # running -- a blocking wait here would starve those very tasks
            # of the loop time they need to ever reach `entered.put(1)`.
            for _ in range(500):
                if entered.qsize() >= concurrency:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= concurrency, "not all held requests reached the blocked authenticate call"

            # The (concurrency + 1)'th request, fired while the first
            # `concurrency` are still blocked mid-`_authenticate`: this is
            # the completion condition itself.
            extra_response = await _query(client, "invalid-cred.invalid-secret")
            assert extra_response.status_code == 429, extra_response.text
            body = extra_response.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            # Zero of the requests -- held or extra -- ever surfaced
            # AUTH_STATE_UNAVAILABLE/503: this is what F-2 measured as the
            # actual harm (platform-pool exhaustion cascading into
            # legitimate callers seeing 503), restated here as "never
            # observed" rather than independently re-measuring the pool
            # exhaustion itself (WP-8a review's own scope).
            assert extra_response.status_code != 503

            release.set()
            held_responses = await asyncio.gather(*tasks)
            for response in held_responses:
                assert response.status_code != 503, response.text
                # Invalid credential -> AUTH_INVALID (401), never masked by
                # a limiter refusal now that the slot each of them reserved
                # is released on its own way out.
                assert response.json()["code"] == "AUTH_INVALID", response.text
    finally:
        http_module._authenticate = original_authenticate


# ---------------------------------------------------------------------------
# Completion condition 2: a pre-authentication concurrency denial is never
# durably audited -- the same "rate-class pre-auth denial is never durably
# audited" rule the rate limiter's own denial already follows (there is no
# authenticated principal to attribute it to yet, in either case).
# ---------------------------------------------------------------------------


async def test_preauth_concurrency_denial_is_never_durably_audited():
    """Fills the (tiny) declared `concurrency` bound with one held request,
    then observes that the request refused by the pre-auth admission gate
    adds no row to `DataService`'s own durable audit sink
    (`ApplicationAuditSink`/`PostgresApplicationAuditSink`, `service.py`'s
    `self._durable_audit`) -- exactly the same non-audited treatment
    `_acquire_rate`'s own `LIMIT_EXCEEDED` denial already gets (neither
    call site sits behind `_event`, `service.py`'s `_slot`/`acquire_
    concurrency_slot` docstrings).

    Mutation (condition 2's own pinned mutation, manifest table row 2):
    adding a durable-audit write to `DataService.acquire_concurrency_slot`'s
    own refusal branch (e.g. `self._durable_audit.append(...)` before the
    `fail(...)` call) turns this red -- the snapshot count changes.
    """
    service = _build_service(concurrency=1, requests_per_minute=100_000)
    entered = threading.Event()
    release = threading.Event()
    original_authenticate = http_module._authenticate

    def blocking_authenticate(request, svc):
        entered.set()
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held request would hang forever"
        return original_authenticate(request, svc)

    http_module._authenticate = blocking_authenticate
    try:
        async with _client(service) as client:
            hold_task = asyncio.create_task(_query(client, "cred-a.secret-a"))
            for _ in range(300):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), "the held request never reached its blocked authenticate call"

            before = len(service._durable_audit.events())  # noqa: SLF001 - test-only introspection, same convention `test_threadpool_offload.py` uses on other private attrs
            extra_response = await _query(client, "cred-a.secret-a")
            assert extra_response.status_code == 429, extra_response.text
            assert extra_response.json()["details"]["limit_class"] == "concurrency"
            after = len(service._durable_audit.events())  # noqa: SLF001
            assert after == before, "a pre-authentication concurrency denial was durably audited"

            release.set()
            held_response = await hold_task
            assert held_response.status_code == 200, held_response.text
    finally:
        http_module._authenticate = original_authenticate


# ---------------------------------------------------------------------------
# WP-8c review F-1 (supervisor ruling 2026-09-09): a request that ENDS in an
# exception -- `AUTH_INVALID` (401) from `_authenticate`, or `VALIDATION_
# FAILED` (400) from body parsing -- must still release the pre-auth slot it
# reserved, exactly like a normally-served (200) request does. Both sit
# strictly INSIDE `with service.acquire_concurrency_slot():` (every handler
# body, `http.py`) and propagate out through it as a raised `FoundationError`
# -- proving `acquire_concurrency_slot`'s own `finally: self._active -= 1`
# (`service.py`) runs on this exception path too, not only the success path
# `test_unauthenticated_flood_is_bounded_by_concurrency` above already
# observes (that test releases its held requests with a VALID credential,
# `AUTH_INVALID`, after the flood -- never itself proving the SLOT NEVER
# HELD one is released; these two tests below prove exactly that, for both
# exception shapes named in the ruling).
# ---------------------------------------------------------------------------


async def test_slot_is_released_after_a_401_ending_request():
    """`concurrency + 1` SEQUENTIAL invalid-bearer requests -- each one ends
    in `_authenticate` raising `AUTH_INVALID` (401) from strictly INSIDE
    `service.acquire_concurrency_slot()`'s own `with` block, never touching
    `DataService._slot`/`_acquire_rate` at all (`_authenticate` itself
    fails first). If the slot each one reserved were never released on
    this exception path, the counter would climb past `concurrency` from
    nothing but a flood of invalid bearer tokens -- no authenticated
    caller involved at all -- and a later iteration would see `LIMIT_
    EXCEEDED`/`concurrency` (429) instead of `AUTH_INVALID` (401): a
    permanent, unauthenticated DoS against the whole deployment, strictly
    worse than the gap this WP closed (review F-1's own framing).

    Mutation (review F-1's own pinned mutation): changing `acquire_
    concurrency_slot`'s `finally: self._active -= 1` (`service.py`) to
    decrement only on the SUCCESS path (e.g. moving the decrement to run
    right after `yield` returns normally, skipped whenever the `with`
    block instead propagates an exception) turns this red -- by the
    `concurrency`'th iteration the counter never comes back down, and
    every iteration from there on (the `(concurrency + 1)`'th and
    beyond) is denied `LIMIT_EXCEEDED` instead of `AUTH_INVALID`.
    """
    concurrency = 3
    service = _build_service(concurrency=concurrency, requests_per_minute=100_000)
    async with _client(service) as client:
        for attempt in range(concurrency + 1):
            response = await _query(client, "invalid-cred.invalid-secret")
            assert response.status_code == 401, f"attempt {attempt}: {response.text}"
            assert response.json()["code"] == "AUTH_INVALID", f"attempt {attempt}: {response.text}"


async def test_slot_is_released_after_a_validation_failed_ending_request():
    """`concurrency + 1` SEQUENTIAL requests with a VALID bearer but a
    malformed (non-JSON) body -- each one authenticates successfully, then
    ends in `_read_json_object` raising `VALIDATION_FAILED` (400), still
    strictly INSIDE `service.acquire_concurrency_slot()`'s own `with`
    block (`http.py::post_query`'s own body-read call comes AFTER
    `_authenticate`, both inside the SAME `with`, never reaching
    `DataService.query_page`/`_slot` at all). Same mutation, same theory
    as the 401 test immediately above, but exercising the OTHER exception
    shape review F-1 names ending a request further along inside the same
    `with` block, after `_authenticate` has already returned successfully
    -- not merely the earliest possible exit point.

    Mutation: identical to the 401 test above -- turns this red by the
    same mechanism (the counter climbs past `concurrency` and a later
    iteration is denied `LIMIT_EXCEEDED` instead of `VALIDATION_FAILED`).
    """
    concurrency = 3
    service = _build_service(concurrency=concurrency, requests_per_minute=100_000)
    async with _client(service) as client:
        for attempt in range(concurrency + 1):
            response = await client.post(
                "/v1/data/notes/query", headers=_auth("cred-a.secret-a"), content=b"not-json-at-all",
            )
            assert response.status_code == 400, f"attempt {attempt}: {response.text}"
            assert response.json()["code"] == "VALIDATION_FAILED", f"attempt {attempt}: {response.text}"


# ---------------------------------------------------------------------------
# WP-8c review F-3 (supervisor ruling 2026-09-09, updating 裁定 4 for the
# HTTP plane): `MitateDB-api/tests/test_application_plane_limits.py::test_
# gate_denies_requests_per_minute_before_concurrency`'s own docstring pins
# 裁定 4 (監督裁定 2026-09-06) at the CELL level (a direct, in-process call
# into `ApplicationCell`/here, `DataService` itself with no HTTP boundary
# involved): rate is checked before concurrency, so a request BOTH
# rate-exhausted AND concurrency-exhausted is denied `requests_per_minute`.
#
# On the HTTP plane, this WP introduced a pre-authentication, deployment-
# wide `concurrency` slot (`service.acquire_concurrency_slot()`, taken
# BEFORE `_authenticate`) that is now evaluated ahead of the per-credential
# `requests_per_minute` window, which stays keyed by credential and
# therefore stays reachable only AFTER authentication succeeds (`_slot`'s
# own docstring). Consequently, on the HTTP plane specifically, the SAME
# both-exhausted request is now denied `concurrency`, not `requests_per_
# minute` -- the OPPOSITE of 裁定 4's own cell-level order. This is not a
# contradiction of 裁定 4 (which governs, and remains true for, a direct
# cell-level call reaching neither `http.py` nor this new pre-auth slot at
# all); it is a SEPARATE ruling for the HTTP plane specifically, pinned
# here, isomorphically to the MitateDB HTTP-plane test of the same name.
# ---------------------------------------------------------------------------


async def test_http_plane_denies_concurrency_before_requests_per_minute():
    """A request that is BOTH `requests_per_minute`-exhausted (for ITS OWN
    credential, `cred-a`) AND `concurrency`-exhausted (the deployment-wide
    pre-auth slot, held for real by a genuinely DIFFERENT, concurrently
    in-flight request under `cred-b`) is denied `concurrency`, not
    `requests_per_minute`, on the HTTP surface -- the order this WP's own
    module-header comment declares (`http.py`: BYTE BOUND -> CONCURRENCY
    SLOT -> AUTHENTICATION -> body -> rate/business), restated here as the
    supervisor's own explicit HTTP-plane ruling (F-3) rather than merely
    an implementation detail nobody pinned.

    `cred-a`'s own single `requests_per_minute` unit is consumed by one
    ordinary, unblocked request FIRST. `cred-b` then holds the sole
    `concurrency` slot for real (`DataService.query_page` monkeypatched to
    block on its FIRST invocation only, mirroring `test_concurrency_hold_
    spans_the_gap_between_authentication_and_dispatch` above) -- `cred-b`'s
    own rate window is untouched, so its request reaches the pre-auth slot
    honestly (not itself rate-denied) and holds it. `cred-a` then fires
    again: its own rate window is exhausted AND the sole concurrency slot
    is held by `cred-b`, at the same instant -- this is the completion
    condition itself. The block is call-counted (blocks only the FIRST
    call, every later call goes straight to the REAL `query_page`) rather
    than unconditional: `cred-a`'s own second request must be free to
    reach the real, unmutated `DataService._slot`/`_acquire_rate` machinery
    the instant it is not turned away earlier by the HTTP-level pre-auth
    slot -- an unconditional block would instead hang IT too (there being
    only one shared `service.query_page` to monkeypatch), manufacturing a
    timeout artifact indistinguishable from a genuine denial.

    Mutation: removing the pre-auth `with service.acquire_concurrency_
    slot():` wrapper from `post_query` entirely (dropping `concurrency_
    precharged=True` from its own `query_page(...)` call along with it --
    a full revert of this handler to its pre-WP-8c shape, `MUT-F3-R2DB`)
    turns this red -- `cred-b`'s own blocked (first) call then holds NO
    slot of any kind (the monkeypatch intercepts before `DataService.
    _slot` is ever reached), so `cred-a`'s own second request sails
    straight through to `_authenticate` (succeeding) and then `DataService.
    _slot`, whose own `_acquire_rate` call precedes its concurrency check
    (`_slot`'s own docstring, not precharged now) -- `cred-a`'s own
    already-exhausted rate window is denied FIRST, flipping the response
    to `requests_per_minute`, not `concurrency`.
    """
    concurrency = 1
    credentials = CredentialStore(pepper=PEPPER)
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
        credentials.add("cred-b", "app-a", "runtime", "secret-b", work=work)
    limits = ResourceLimits(concurrency=concurrency, requests_per_minute=1)
    service = DataService(credentials, limits=limits)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})

    entered = threading.Event()
    release = threading.Event()
    original_query_page = service.query_page
    call_count = {"n": 0}

    def blocking_query_page(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            entered.set()
            released = release.wait(timeout=5.0)
            assert released, "release was never set -- the held request would hang forever"
        return original_query_page(*args, **kwargs)

    async with _client(service) as client:
        # Exhaust cred-a's own requests_per_minute window with one
        # ordinary, unblocked request (query_page not yet monkeypatched).
        first = await _query(client, "cred-a.secret-a")
        assert first.status_code == 200, first.text

        # Now block query_page and hold the SOLE concurrency slot with a
        # DIFFERENT credential (cred-b), whose own rate window is untouched.
        service.query_page = blocking_query_page
        try:
            hold_task = asyncio.create_task(_query(client, "cred-b.secret-b"))
            for _ in range(500):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), "the held request never reached the blocked query_page call"

            # cred-a fires again: its OWN rate window is exhausted AND the
            # sole concurrency slot is held by cred-b, at the same instant.
            extra = await _query(client, "cred-a.secret-a")
            assert extra.status_code == 429, extra.text
            body = extra.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            release.set()
            held_response = await hold_task
            assert held_response.status_code == 200, held_response.text
        finally:
            service.query_page = original_query_page


# ---------------------------------------------------------------------------
# Completion condition 4: the slot is held for the caller's ENTIRE request
# -- across authentication AND the gap between authentication completing
# and the eventual `DataService` business call being reached -- never
# released and re-acquired somewhere in between.
# ---------------------------------------------------------------------------


async def test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch():
    """`DataService.query_page` (called from INSIDE `http.py`'s own `_run`
    closure, strictly AFTER `_authenticate` has already returned) is
    monkeypatched to block -- so the stall point sits in the exact gap a
    "release after auth, then reacquire before dispatch" implementation
    would have to pass through empty-handed. `concurrency = 2` VALID
    requests are driven into that gap and held there; a THIRD valid request
    fired while they are stuck there must still see `LIMIT_EXCEEDED`/
    `concurrency` -- proof the slot the first two reserved before their own
    `_authenticate` call is still held, continuously, this far past it.

    Mutation (condition 4's own pinned mutation, manifest table row 4):
    changing `http.py` to release `acquire_concurrency_slot()` right after
    `_authenticate` returns and re-acquire a fresh one immediately before
    the `_run()`/`query_page` call turns this red -- at the moment this
    test's own two held requests sit inside the monkeypatched `query_page`
    (i.e. exactly inside that gap), both reservations would already be
    released and not yet retaken, so the third request's own pre-auth
    check would see 0 slots in use and be served (200), not refused (429).
    """
    concurrency = 2
    service = _build_service(concurrency=concurrency, requests_per_minute=100_000)
    entered: "queue.Queue[int]" = queue.Queue()
    release = threading.Event()
    original_query_page = service.query_page

    def blocking_query_page(*args, **kwargs):
        entered.put(1)
        released = release.wait(timeout=5.0)
        assert released, "release was never set -- the held requests would hang forever"
        return original_query_page(*args, **kwargs)

    service.query_page = blocking_query_page
    try:
        async with _client(service) as client:
            tasks = [asyncio.create_task(_query(client, "cred-a.secret-a")) for _ in range(concurrency)]
            for _ in range(500):
                if entered.qsize() >= concurrency:
                    break
                await asyncio.sleep(0.01)
            assert entered.qsize() >= concurrency, "not all held requests reached the blocked query_page call"

            extra_response = await _query(client, "cred-a.secret-a")
            assert extra_response.status_code == 429, extra_response.text
            body = extra_response.json()
            assert body["code"] == "LIMIT_EXCEEDED", body
            assert body["details"]["limit_class"] == "concurrency", body

            release.set()
            held_responses = await asyncio.gather(*tasks)
            for response in held_responses:
                assert response.status_code == 200, response.text
    finally:
        service.query_page = original_query_page


# ---------------------------------------------------------------------------
# Completion condition 4, structural half. WP-8a review F-4's own finding
# applies here too: a "release right after `_authenticate` returns, then
# immediately re-acquire" mutation has NO `await` between the release and
# the re-acquire (`with service.acquire_concurrency_slot():` exits and a
# fresh one enters back-to-back, synchronously, on the event-loop thread),
# so no OTHER coroutine can ever be scheduled into that gap to observe it
# empty -- it is not a race a black-box concurrent-request test (the test
# immediately above) can ever force red, for the same reason F-4 found
# CPython-level lock-removal races frequently cannot be forced red either.
# The fix there was the same fix here: PIN THE SHAPE OF THE SOURCE (an AST
# scan, `test_threadpool_offload.py`'s own established technique for
# exactly this class of problem) instead of trying to race it.
# ---------------------------------------------------------------------------


def _unwrap_endpoint(wrapped):
    """`http.py::_endpoint` wraps each handler in a `wrapped(request)`
    closure with no `functools.wraps` -- `inspect.getsource(http_module.
    get_capabilities)` would otherwise return `_endpoint`'s own generic
    try/except body, never the real handler's, since module-level lookup
    only ever sees the wrapper. The real handler is reachable as the
    `handler` free variable `wrapped`'s own closure captures."""
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
    in `function_def`'s own body (not nested inside another `with`/`if`/
    etc. -- exactly the handler-level shape every endpoint in `http.py`
    uses)."""
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
    genuinely invokes `_authenticate` -- either directly (`_authenticate(
    request, service)`, the `get_capabilities`/`get_catalog`/`post_cross_
    entity_mutate`/`post_audit_query` shape) or via `run_in_threadpool`
    (`run_in_threadpool(_authenticate, request, service)`, the `post_
    query`/`post_mutate`/`post_schema` shape -- the bare `_authenticate`
    NAME as the first positional argument is what actually gets invoked
    once the delegated thread runs, so it counts here too). `ast.walk`
    reaches a `Call` wrapped in `Await` (`await run_in_threadpool(...)`)
    the same as an unwrapped one -- `Await` is simply an ancestor node in
    the SAME subtree walk, not something that needs separate unwrapping."""
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
    own `_authenticate` call and its own eventual `DataService` business
    call -- never released and re-entered a second time in between.

    Mutation (condition 4's own pinned mutation, manifest table row 4,
    restated as a source-shape edit for the reason given above): splitting
    a handler's single `with service.acquire_concurrency_slot():` block
    into two -- one around `_authenticate` alone, released, then a second
    fresh one entered before the body read / business call -- turns this
    red immediately: `len(blocks) == 2`, not 1.

    WP-8c review F-4 (supervisor ruling 2026-09-09, "slot 取得が
    `_authenticate` 呼び出しより前" -- strengthens this pin to check the
    ORDER, not merely the block count): `len(blocks) == 1` alone does not
    check what this docstring (and the manifest's own completion condition
    4) actually claims -- a handler edited to call `_authenticate` BEFORE
    the `with` statement (hoisted entirely out of it, the `with` reduced
    to wrapping only the eventual business call) would still show exactly
    ONE `with service.acquire_concurrency_slot():` block and pass the
    count check alone, while no longer spanning authentication at all (a
    real regression: the pre-auth slot would then gate nothing an
    unauthenticated flood of invalid bearer tokens ever reaches -- exactly
    review F-2's own original gap, reopened). The two assertions below
    close that: EVERY genuine call to `_authenticate` anywhere in this
    handler's own body must sit INSIDE the located `with` block, and at
    least one must -- together, "the slot acquisition precedes (wraps)
    every `_authenticate` call this handler makes", never the reverse.

    Mutation: hoisting `context = await run_in_threadpool(_authenticate,
    request, service)` (or the bare-call form) to run BEFORE `with
    service.acquire_concurrency_slot():` in any of the 7 handlers turns
    this red -- that call now sits OUTSIDE the located block, caught by
    the second assertion, even though `len(blocks)` alone would stay 1
    and miss it entirely.
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
