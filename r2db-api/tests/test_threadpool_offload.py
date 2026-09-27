"""Phase 10 WP-8a (design D-8 (3)): the HTTP boundary's synchronous section
-- authentication and the composed `DataService`/`ControlPlaneService` call,
both real psycopg round trips in the production composition -- runs off the
event-loop thread via `starlette.concurrency.run_in_threadpool`.

Read this file against `r2db_api/http.py`'s and `r2db_api/control_http.py`'s
own "Phase 10 WP-8a" comment blocks (immediately above their endpoint
tables), and against WP-4b ruling 3 (`{scratchpad}/phase10/wp4b-rulings.md`):
a real single-uvicorn/single-event-loop deployment could only ever show
`in-flight == 1` for `hold_in_flight(n>1)` before this change -- the declared
`concurrency` limit (default 32) was structurally unreachable because every
request's synchronous psycopg work fully occupied the one event loop thread
for its own duration. This file's first two tests are the direct evidence
that a second request now completes while a first one's own synchronous
section is still blocked (in-flight >= 2), and the remaining three pin the
thread-safety audit WP-8a's own work order required before this delegation
could be introduced safely.

Uses httpx `ASGITransport` in-process, same convention as `test_http.py`/
`test_control_http.py`.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import pathlib
import sys
import textwrap
import threading
import time
import types
from contextlib import asynccontextmanager

import httpx
import pytest
from psycopg.pq import TransactionStatus

from r2db_api import http as http_module
from r2db_api.auth import ControlCredentialStore, CredentialStore, compose_bearer_locator
from r2db_api.audit import ControlAuditSink
from r2db_api.control_http import create_control_app
from r2db_api.control_plane import ControlPlaneService, InMemoryControlBackend
from r2db_api.errors import FoundationError
from r2db_api.http import DEFAULT_THREAD_LIMIT, create_app
from r2db_api.limits import ControlPlaneLimits, ResourceLimits, role_pool_size
from r2db_api.postgres import _RolePool
from r2db_api.service import ControlAuthority, DataService
from r2db_api.structured import QueryOutcome

# Explicit marker -- same reasoning as `test_http.py`'s own identical
# comment: this file must also run correctly under the repo-root pytest
# invocation, whose own `pyproject.toml` does not set `anyio_mode = "auto"`.
pytestmark = pytest.mark.anyio

BASE_URL = "http://r2db.example.invalid"
CONTROL_BASE_URL = "http://r2db-control.example.invalid"
PEPPER = "synthetic-test-pepper-threadpool-offload-0000"
CONTROL_PEPPER = "synthetic-test-pepper-threadpool-offload-ctl-0000"
_SEED_SECRET = "synthetic-threadpool-offload-seed-secret-0000"
_SEED_CREDENTIAL_ID = "ctl_threadpooloffload000"

# Generous enough that these tests never trip a limit they are not
# specifically exercising (mirrors `test_control_http.py`'s own `_GENEROUS_
# LIMITS` convention).
_GENEROUS_CONTROL_LIMITS = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=100_000)


def _build_service(**limit_overrides) -> DataService:
    credentials = CredentialStore(pepper=PEPPER)
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    limits = ResourceLimits(**limit_overrides) if limit_overrides else ResourceLimits()
    service = DataService(credentials, limits=limits)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    return service


def _auth(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


@asynccontextmanager
async def _client(service: DataService, *, thread_limit: "int | None" = DEFAULT_THREAD_LIMIT):
    transport = httpx.ASGITransport(app=create_app(service, thread_limit=thread_limit))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


def _build_control_harness() -> types.SimpleNamespace:
    credentials = CredentialStore(pepper=PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    audit = ControlAuditSink()
    service = ControlPlaneService(backend, audit=audit, limits=_GENEROUS_CONTROL_LIMITS)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(_SEED_CREDENTIAL_ID, _SEED_SECRET, work=work)
    with control_credentials.unit_of_work() as work:
        control_credentials.rotate(_SEED_CREDENTIAL_ID, _SEED_SECRET, work=work)
    return types.SimpleNamespace(service=service, secret=compose_bearer_locator(_SEED_CREDENTIAL_ID, _SEED_SECRET))


@asynccontextmanager
async def _control_client(service: ControlPlaneService):
    transport = httpx.ASGITransport(app=create_control_app(service))
    async with httpx.AsyncClient(transport=transport, base_url=CONTROL_BASE_URL) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Data plane: the sync section (auth + `DataService.query_page`, both a
#    real psycopg round trip in production) runs off the event loop.
# ---------------------------------------------------------------------------


async def test_sync_section_runs_off_the_event_loop():
    """Holds one `post_query` request inside its own delegated sync section
    (`query_page`, monkeypatched to block on a `threading.Event`) and proves
    a SECOND request completes while the first is still blocked -- in-flight
    >= 2, WP-4b ruling 3's own direct evidence that the pre-WP-8a shape could
    never reach the declared `concurrency` limit on a real single-event-loop
    deployment. `run_in_threadpool` removed (this test's own pinned
    mutation) collapses this back to in-flight == 1: the probe request can
    only start once the held one has finished, so the bounded `wait_for`
    below times out instead of the held call ever unblocking.
    """
    service = _build_service()
    entered = threading.Event()
    release = threading.Event()
    original_query_page = service.query_page

    def blocking_query_page(*args, **kwargs):
        entered.set()
        release.wait(timeout=3.0)
        return original_query_page(*args, **kwargs)

    service.query_page = blocking_query_page

    async with _client(service) as client:

        async def hold():
            return await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})

        async def probe():
            for _ in range(300):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), "the held request never reached its blocking sync section"
            # The second request completing HERE, while `hold()`'s own sync
            # section is still parked on `release.wait()`, is the in-flight
            # >= 2 observation itself.
            response = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
            release.set()
            return response

        hold_response, probe_response = await asyncio.wait_for(asyncio.gather(hold(), probe()), timeout=1.5)

    assert probe_response.status_code == 200
    assert hold_response.status_code == 200
    assert hold_response.json()["items"] == [{"id": 1}]


# ---------------------------------------------------------------------------
# 2. Control plane: the same shape, `ControlPlaneService.capabilities`.
# ---------------------------------------------------------------------------


async def test_control_sync_section_runs_off_the_event_loop():
    harness = _build_control_harness()
    entered = threading.Event()
    release = threading.Event()
    original_capabilities = harness.service.capabilities

    def blocking_capabilities(*args, **kwargs):
        entered.set()
        release.wait(timeout=3.0)
        return original_capabilities(*args, **kwargs)

    harness.service.capabilities = blocking_capabilities

    async with _control_client(harness.service) as client:

        async def hold():
            return await client.get("/control/v1/capabilities", headers=_auth(harness.secret))

        async def probe():
            for _ in range(300):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), "the held request never reached its blocking sync section"
            response = await client.get("/control/v1/applications", headers=_auth(harness.secret))
            release.set()
            return response

        hold_response, probe_response = await asyncio.wait_for(asyncio.gather(hold(), probe()), timeout=1.5)

    assert probe_response.status_code == 200
    assert hold_response.status_code == 200
    assert hold_response.json()["role"] == "control"


# ---------------------------------------------------------------------------
# 3. Body reading itself stays on the event-loop thread; only the section
#    that follows it is delegated.
# ---------------------------------------------------------------------------


async def test_body_read_stays_on_the_loop(monkeypatch):
    service = _build_service()
    main_thread = threading.current_thread()
    read_threads: list[threading.Thread] = []
    call_threads: list[threading.Thread] = []

    original_read = http_module._read_json_object

    async def spy_read(request):
        read_threads.append(threading.current_thread())
        return await original_read(request)

    monkeypatch.setattr(http_module, "_read_json_object", spy_read)

    original_query_page = service.query_page

    def spy_query_page(*args, **kwargs):
        call_threads.append(threading.current_thread())
        return original_query_page(*args, **kwargs)

    service.query_page = spy_query_page

    async with _client(service) as client:
        response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})

    assert response.status_code == 200
    assert read_threads == [main_thread], "the request body was not read on the event-loop thread"
    assert call_threads and call_threads[0] is not main_thread, "the DataService call did not run off the event-loop thread"


# ---------------------------------------------------------------------------
# 4. `DataService._slot`/`_acquire_rate`'s in-memory state is thread-safe
#    (design D-8 (3) audit item (a)): both are already guarded by
#    `threading.Lock` (`self._active_lock`/`self._rate_lock`,
#    `service.py`'s `DataService.__init__`) -- this pins that property
#    directly against the real methods, independent of the HTTP layer.
# ---------------------------------------------------------------------------


def test_limiter_state_is_thread_safe():
    """Phase 10 WP-8a review F-4 (supervisor ruling 2026-09-08): this
    race-based overshoot assertion (`max(observed_active) <= concurrency_
    limit`) is KEPT as a stress/bookkeeping check (no crash, no deadlock,
    every thread returns), but it is NOT the mutation pin for "the check-
    then-increment happens under `self._active_lock`" -- the review found
    it cannot be: in CPython, removing the lock produces a lost-update
    race that only ever SHRINKS the observed counter, never grows it past
    the limit (`{scratchpad}/phase10/wp8a-review.md` F-4, `probe_slotrace.
    py`: no overshoot in 20 trials at 60 threads even with the lock
    removed). `test_slot_check_then_increment_is_lexically_inside_the_
    active_lock`, below, is the deterministic replacement pin for that
    property.
    """
    concurrency_limit = 2
    service = _build_service(concurrency=concurrency_limit, requests_per_minute=100_000)
    context = service.authenticate("cred-a.secret-a")

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # force frequent GIL handoffs -- widens any unguarded check-then-act race
    observed_active: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(40)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            with service._slot(context):  # noqa: SLF001 -- exercising the private lock discipline directly
                observed_active.append(service._active)  # noqa: SLF001
                time.sleep(0.001)
        except FoundationError:
            pass  # LIMIT_EXCEEDED (429) is an expected outcome once the concurrency cap is hit
        except BaseException as exc:  # pragma: no cover -- failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
    finally:
        sys.setswitchinterval(old_interval)

    assert not any(t.is_alive() for t in threads), "a worker thread never returned"
    assert not errors, errors
    assert observed_active, "no thread ever observed DataService._active -- vacuous test"
    assert max(observed_active) <= concurrency_limit, (
        f"observed DataService._active={max(observed_active)} exceeded the configured concurrency "
        f"limit {concurrency_limit} -- the in-flight counter's check-then-increment is not serialized"
    )


# ---------------------------------------------------------------------------
# 5. `_RolePool` checkout/return is thread-safe (design D-8 (3) audit item
#    (c)): already guarded by `threading.Lock` (`self._lock`, `postgres.py`'s
#    `_RolePool.__init__`). `_connect` is monkeypatched to a lightweight fake
#    connection so this pins the pool's own bookkeeping (`_created`, the
#    checkout queue) without requiring a live PostgreSQL server.
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return (1,)


def test_pool_acquire_is_thread_safe(monkeypatch):
    """Phase 10 WP-8a review F-4 (supervisor ruling 2026-09-08): same
    status as `test_limiter_state_is_thread_safe` above -- kept as a
    stress/bookkeeping check, superseded as the lock-discipline mutation
    pin by `test_role_pool_reservation_is_lexically_inside_the_pool_lock`,
    below, for the same reason (a lost-update race on `_created` only
    shrinks the observed count, it does not exceed `maxconn`).
    """
    maxconn = 3
    pool = _RolePool("postgresql://unused.example.invalid/db", schema="public", maxconn=maxconn)

    created_conns: list[types.SimpleNamespace] = []
    created_conns_lock = threading.Lock()

    def fake_connect(self: _RolePool) -> types.SimpleNamespace:
        conn = types.SimpleNamespace()
        conn.closed = 0
        conn.info = types.SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        conn.cursor = lambda: _FakeCursor()
        conn.rollback = lambda: None
        conn.commit = lambda: None
        conn.close = lambda: setattr(conn, "closed", 1)
        with created_conns_lock:
            created_conns.append(conn)
        return conn

    monkeypatch.setattr(_RolePool, "_connect", fake_connect)
    monkeypatch.setattr(_RolePool, "_liveness_check", lambda self, conn: True)

    checkouts: list[object] = []
    checkouts_lock = threading.Lock()
    errors: list[BaseException] = []
    barrier = threading.Barrier(30)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            with pool.connection() as conn:
                with checkouts_lock:
                    checkouts.append(conn)
                time.sleep(0.001)
        except BaseException as exc:  # pragma: no cover -- failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not any(t.is_alive() for t in threads), "a worker thread never returned"
    assert not errors, errors
    assert len(checkouts) == 30, "not every worker completed its checkout -- vacuous test"
    assert len(created_conns) <= maxconn, (
        f"created {len(created_conns)} connections against maxconn={maxconn} -- "
        "the pool's checkout accounting (`_created`) is not serialized"
    )
    assert pool._created == len(created_conns)  # noqa: SLF001 -- bookkeeping consistency, not merely a ceiling


# ---------------------------------------------------------------------------
# 6. Phase 10 WP-8a review F-4 (supervisor ruling 2026-09-08): deterministic
#    replacements for tests 4/5's own race-based lock-discipline assertion,
#    which the review found CANNOT go red for the mutation it was meant to
#    pin (`self._active_lock`/`self._rate_lock`/`_RolePool._lock` swapped
#    for `contextlib.nullcontext()`, or the guarded check-then-act moved
#    outside the `with` block that names the real lock) -- CPython's GIL
#    turns an unguarded check-then-act race into a LOST UPDATE, which only
#    ever shrinks an observed counter, never grows it past a ceiling
#    (`probe_slotrace.py`, `{scratchpad}/phase10/wp8a-review.md` F-4: no
#    overshoot in 20 trials at 60 threads, `sys.setswitchinterval(1e-6)`,
#    even with the lock actually removed).
#
#    These tests instead PIN THE SHAPE OF THE SOURCE (an AST scan, the same
#    technique `tests/test_l1_details_vocabulary_ast_scan.py` already uses
#    elsewhere in this suite): the check-then-act statements must be
#    LEXICALLY NESTED inside the `with self.<lock>:` block that names the
#    real lock, not merely present somewhere in the same method. This is
#    scheduling-independent -- it cannot flake, and it goes red the instant
#    the mutation is applied, on every run, regardless of GIL timing.
# ---------------------------------------------------------------------------


def _self_attr(node: ast.AST, attr: str) -> bool:
    """`True` iff `node` is exactly the attribute access `self.<attr>`."""
    return isinstance(node, ast.Attribute) and node.attr == attr and isinstance(node.value, ast.Name) and node.value.id == "self"


def _find_with_lock_body(tree: ast.AST, *, lock_attr: str) -> list[ast.stmt] | None:
    """The `body` of the first `with self.<lock_attr>:` statement found
    anywhere in `tree`, or `None` if there is no such statement at all."""
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                if _self_attr(item.context_expr, lock_attr):
                    return node.body
    return None


def _body_contains(body: list[ast.stmt], predicate) -> bool:
    """`True` iff any statement in `body` (searched recursively, e.g. into
    an `if`'s own body) contains a node matching `predicate`."""
    for stmt in body:
        for node in ast.walk(stmt):
            if predicate(node):
                return True
    return False


def _parsed_method(method) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(method)))


def test_slot_check_then_increment_is_lexically_inside_the_active_lock():
    """`DataService._slot`'s concurrency check-then-increment (`if self.
    _active >= self.limits.concurrency: fail(...)` then `self._active +=
    1`) must be lexically inside the SAME `with self._active_lock:` block.
    Mutation (F-4's own MUT-F, restated as a source-shape edit rather than
    an attribute swap): moving either statement out of that block turns
    this red immediately, independent of scheduling.
    """
    tree = _parsed_method(DataService._slot)
    body = _find_with_lock_body(tree, lock_attr="_active_lock")
    assert body is not None, "no `with self._active_lock:` block found in `_slot`"
    assert _body_contains(body, lambda n: isinstance(n, ast.Compare) and _self_attr(n.left, "_active")), (
        "the concurrency check (`self._active >= ...`) is not lexically inside `with self._active_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_active") and isinstance(n.op, ast.Add)), (
        "the increment (`self._active += 1`) is not lexically inside `with self._active_lock:`"
    )


def test_rate_window_check_then_append_is_lexically_inside_the_rate_lock():
    """`DataService._acquire_rate`'s sliding-window check-then-append (read
    + filter the window, check `len(window) >= self.limits.requests_per_
    minute`, then `window.append(now)`) must be lexically inside the SAME
    `with self._rate_lock:` block. Mutation (F-4's own MUT-E, restated):
    moving the length check or the append out of that block turns this
    red immediately.
    """
    tree = _parsed_method(DataService._acquire_rate)
    body = _find_with_lock_body(tree, lock_attr="_rate_lock")
    assert body is not None, "no `with self._rate_lock:` block found in `_acquire_rate`"
    assert _body_contains(body, lambda n: isinstance(n, ast.Compare) and isinstance(n.left, ast.Call) and isinstance(n.left.func, ast.Name) and n.left.func.id == "len"), (
        "the window-length check (`len(window) >= ...`) is not lexically inside `with self._rate_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append"), (
        "the window append (`window.append(now)`) is not lexically inside `with self._rate_lock:`"
    )


def test_role_pool_reservation_is_lexically_inside_the_pool_lock():
    """`_RolePool._acquire`'s reservation check-then-increment (`if self.
    _created < self._maxconn: self._created += 1; reserved = True`) must
    be lexically inside the SAME `with self._lock:` block. Mutation
    (F-4's own MUT-D, restated): moving the check or the increment out of
    that block turns this red immediately.
    """
    tree = _parsed_method(_RolePool._acquire)
    body = _find_with_lock_body(tree, lock_attr="_lock")
    assert body is not None, "no `with self._lock:` block found in `_acquire`"
    assert _body_contains(body, lambda n: isinstance(n, ast.Compare) and _self_attr(n.left, "_created")), (
        "the reservation check (`self._created < self._maxconn`) is not lexically inside `with self._lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_created") and isinstance(n.op, ast.Add)), (
        "the reservation increment (`self._created += 1`) is not lexically inside `with self._lock:`"
    )


# ---------------------------------------------------------------------------
# 7. Phase 10 WP-8a review F-5 (supervisor ruling 2026-09-08): broadened
#    delegation pins. The review found only `post_query`'s SECOND
#    delegation and `get_control_capabilities` were actually pinned by any
#    existing test before this WP -- MUT-A (removing `post_rotate_
#    credential`'s ONLY delegation) and MUT-C (removing all 3 data-plane
#    `_authenticate` delegations) both left `r2db-api/tests` fully green.
#    These tests use the same "thread-identity spy" technique as test 3
#    above (`test_body_read_stays_on_the_loop`) -- deterministic and cheap
#    (one request per target, no concurrency/timing needed): a delegated
#    call's spy records a worker thread; a non-delegated one records the
#    event-loop (main) thread.
# ---------------------------------------------------------------------------


async def test_authenticate_delegation_pinned_for_every_body_first_handler():
    """Pins `_authenticate`'s OWN `run_in_threadpool` delegation at all 3
    data-plane call sites that perform it BEFORE the body read (`post_
    query`, `post_mutate`, `post_schema`) -- F-5's MUT-C removed all 3 at
    once and nothing went red. Each is recorded independently here so
    removing even ONE of the 3 is caught (not merely "at least one still
    delegates").
    """
    service = _build_service()
    main_thread = threading.current_thread()
    recorded_threads: dict[str, threading.Thread] = {}
    original_authenticate = http_module._authenticate

    def spy(request, service_):
        recorded_threads[request.url.path] = threading.current_thread()
        return original_authenticate(request, service_)

    http_module._authenticate = spy
    try:
        async with _client(service) as client:
            await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
            await client.post("/v1/data/notes/mutations", headers=_auth("cred-a.secret-a"), json={"operations": []})
            await client.post("/v1/schema/operations", headers=_auth("cred-a.secret-a"), json={"operations": []})
    finally:
        http_module._authenticate = original_authenticate

    assert set(recorded_threads) == {"/v1/data/notes/query", "/v1/data/notes/mutations", "/v1/schema/operations"}, recorded_threads
    for path, thread in recorded_threads.items():
        assert thread is not main_thread, f"_authenticate for {path} ran on the event-loop thread -- its delegation is missing"


async def test_service_call_delegation_pinned_for_query_mutate_cross_entity_schema():
    """Pins the SECOND `run_in_threadpool` delegation (the composed
    `DataService` call itself, a real psycopg round trip in production)
    for the 4 data-plane handlers named by the supervisor ruling:
    `query_page` (`post_query`), `mutate_result` (`post_mutate`), `schema`
    (`post_schema`), and `deny_unsupported` (`post_cross_entity_mutate`,
    which has no body of its own to read and so delegates its whole
    authenticate-then-call sequence in this one call).
    """
    service = _build_service()
    main_thread = threading.current_thread()
    recorded_threads: dict[str, threading.Thread] = {}
    originals = {name: getattr(service, name) for name in ("query_page", "mutate_result", "schema", "deny_unsupported")}

    def _make_spy(name: str, original):
        def spy(*args, **kwargs):
            recorded_threads[name] = threading.current_thread()
            return original(*args, **kwargs)

        return spy

    for name, original in originals.items():
        setattr(service, name, _make_spy(name, original))

    async with _client(service) as client:
        await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
        await client.post("/v1/data/notes/mutations", headers=_auth("cred-a.secret-a"), json={"operations": []})
        await client.post("/v1/schema/operations", headers=_auth("cred-a.secret-a"), json={"operation": "create_entity", "entity": "widgets"})
        await client.post("/v1/data/mutations", headers=_auth("cred-a.secret-a"), json={})

    assert set(recorded_threads) == {"query_page", "mutate_result", "schema", "deny_unsupported"}, recorded_threads
    for name, thread in recorded_threads.items():
        assert thread is not main_thread, f"DataService.{name} ran on the event-loop thread -- its delegation is missing"


async def test_control_service_call_delegation_pinned_for_rotate_and_issue_credential():
    """Control-plane representative coverage beyond the single `get_
    control_capabilities` test 2 (above) already exercises -- `post_
    issue_credential` (body, no path param) and `post_rotate_credential`
    (path param, no body, F-5's own MUT-A target), pinning that EACH
    handler's own composed `ControlPlaneService` call actually runs
    delegated, not merely that SOME control-plane handler does. F-5's
    MUT-A (removing `post_rotate_credential`'s only delegation) left
    `r2db-api/tests` fully green (1177 passed, unchanged) before this
    test existed.
    """
    harness = _build_control_harness()
    main_thread = threading.current_thread()
    recorded_threads: dict[str, threading.Thread] = {}
    original_issue = harness.service.issue_credential
    original_rotate = harness.service.rotate_credential

    def spy_issue(*args, **kwargs):
        recorded_threads["issue_credential"] = threading.current_thread()
        return original_issue(*args, **kwargs)

    def spy_rotate(*args, **kwargs):
        recorded_threads["rotate_credential"] = threading.current_thread()
        return original_rotate(*args, **kwargs)

    harness.service.issue_credential = spy_issue
    harness.service.rotate_credential = spy_rotate

    async with _control_client(harness.service) as client:
        await client.post("/control/v1/applications", headers=_auth(harness.secret), json={"application_id": "appb"})
        issue_response = await client.post(
            "/control/v1/credentials", headers=_auth(harness.secret), json={"application_id": "appb", "role": "runtime"}
        )
        assert issue_response.status_code == 200, issue_response.text
        credential_id = issue_response.json()["credential_id"]
        rotate_response = await client.post(f"/control/v1/credentials/{credential_id}/rotate", headers=_auth(harness.secret))
        assert rotate_response.status_code == 200, rotate_response.text

    assert set(recorded_threads) == {"issue_credential", "rotate_credential"}, recorded_threads
    for name, thread in recorded_threads.items():
        assert thread is not main_thread, f"ControlPlaneService.{name} ran on the event-loop thread -- its delegation is missing"


# ---------------------------------------------------------------------------
# 8. Phase 10 WP-8a review F-1 (supervisor ruling 2026-09-08): the served-
#    application `_RolePool` capacity must be DERIVED from the declared
#    `ResourceLimits.concurrency` (`r2db_api.limits.role_pool_size`), and be
#    at least that value -- not a fixed constant (previously, effectively,
#    `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW`, default 4, entirely
#    disconnected from `concurrency`, default 32). Once WP-8a's own
#    `run_in_threadpool` delegation let concurrent requests against ONE
#    application actually reach the pool concurrently, a pool sized below
#    the declared ceiling opened a NEW failure mode: a request comfortably
#    under the declared 429 LIMIT_EXCEEDED bound instead times out waiting
#    for a pooled connection and fails closed with 503 SERVICE_UNAVAILABLE.
# ---------------------------------------------------------------------------


def test_role_pool_size_derives_from_declared_concurrency():
    """Pins `role_pool_size` itself as a real derivation, not a constant
    that happens to match one value: two different `concurrency` settings
    must produce two different pool sizes, and the untouched default must
    not be the old fixed default of 4. Mutation: `return limits.
    concurrency` -> `return 4` turns every assertion here red.
    """
    assert role_pool_size(ResourceLimits(concurrency=7)) == 7
    assert role_pool_size(ResourceLimits(concurrency=32)) == 32
    assert role_pool_size(ResourceLimits()) != 4, "pool size must not be pinned back to the old fixed default of 4"


def test_main_composition_root_wires_pool_size_from_role_pool_size():
    """Structural (AST) pin, not a live-PostgreSQL one: `r2db_api.main.
    build_app` requires a real, provisioned platform database this file's
    other tests deliberately avoid needing (`test_credential_persistence.
    py`'s own `main_module`/`platform` fixtures already cover that). Reads
    `main.py`'s source directly via `importlib.util.find_spec` (locates
    the file without importing/executing the module -- `r2db_api.main`
    has a module-level `app = build_app()` that needs real environment
    variables and a live platform database) and asserts that every
    `PostgresCell(...)` call in `build_app` passes a `pool_size=` keyword
    whose value is a variable assigned (in the same source) from calling
    `role_pool_size(...)` -- never a literal constant.
    """
    spec = importlib.util.find_spec("r2db_api.main")
    assert spec is not None and spec.origin, "could not locate r2db_api.main's source file"
    source = pathlib.Path(spec.origin).read_text()
    tree = ast.parse(source)

    cell_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "PostgresCell"]
    assert cell_calls, "no `PostgresCell(...)` call found in r2db_api/main.py"

    for call in cell_calls:
        pool_size_kw = next((kw for kw in call.keywords if kw.arg == "pool_size"), None)
        assert pool_size_kw is not None, "a `PostgresCell(...)` call has no `pool_size=` keyword"
        assert isinstance(pool_size_kw.value, ast.Name), (
            f"`pool_size=` must reference a variable, not a literal ({ast.dump(pool_size_kw.value)})"
        )
        var_name = pool_size_kw.value.id
        assigns = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var_name for t in n.targets)
        ]
        assert assigns, f"no assignment found for `{var_name}`"
        assert any(
            isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name) and a.value.func.id == "role_pool_size"
            for a in assigns
        ), f"`{var_name}` must be assigned from `role_pool_size(...)`, not a literal constant"


def test_main_composition_root_wires_thread_limit_from_the_env_reader():
    """Structural (AST) pin, same technique and same reason as `test_
    main_composition_root_wires_pool_size_from_role_pool_size` above:
    `build_app` requires a real platform database this file avoids
    needing. Asserts `create_app(...)`'s own `thread_limit=` keyword
    references a variable (never a literal, never `None`), and that
    variable is assigned from calling `_thread_limit_from_env(env,
    "R2DB_THREAD_LIMIT", DEFAULT_THREAD_LIMIT)` -- completion conditions
    92/93's own runtime claim (env value reaches the loop's limiter) is
    the composition of this wiring pin with `_thread_limit_from_env`'s
    own unit tests below and `create_app`'s own D-8 tests above in this
    file, never re-executed against a live platform database here.

    mutation M134 (`r2db_api/main.py`): pass `None` instead of the
    variable when the env is unset -- this test's own `isinstance(...,
    ast.Name)` assertion goes red (a `None` keyword value is an
    `ast.Constant`, not an `ast.Name`).
    mutation M135 (`r2db_api/main.py`): assign the variable from
    `DEFAULT_THREAD_LIMIT` unconditionally, discarding the env -- this
    test's own `_thread_limit_from_env` call-site assertion goes red (no
    assignment calls that function at all).
    """
    spec = importlib.util.find_spec("r2db_api.main")
    assert spec is not None and spec.origin
    source = pathlib.Path(spec.origin).read_text()
    tree = ast.parse(source)

    create_app_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "create_app"
    ]
    assert create_app_calls, "no `create_app(...)` call found in r2db_api/main.py"
    call = create_app_calls[0]
    thread_limit_kw = next((kw for kw in call.keywords if kw.arg == "thread_limit"), None)
    assert thread_limit_kw is not None, "`create_app(...)` has no `thread_limit=` keyword"
    assert isinstance(thread_limit_kw.value, ast.Name), (
        f"`thread_limit=` must reference a variable, not a literal ({ast.dump(thread_limit_kw.value)})"
    )
    var_name = thread_limit_kw.value.id
    assigns = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var_name for t in n.targets)
    ]
    assert assigns, f"no assignment found for `{var_name}`"
    assert any(
        isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name) and a.value.func.id == "_thread_limit_from_env"
        and len(a.value.args) >= 2 and isinstance(a.value.args[1], ast.Constant) and a.value.args[1].value == "R2DB_THREAD_LIMIT"
        for a in assigns
    ), f"`{var_name}` must be assigned from `_thread_limit_from_env(env, \"R2DB_THREAD_LIMIT\", ...)`"


# ---------------------------------------------------------------------------
# D-9: `_thread_limit_from_env`'s own strict-parse contract (unit-level,
# no real platform database -- see the structural pin immediately above
# for why `build_app` itself is never executed here).
# ---------------------------------------------------------------------------


def _load_thread_limit_from_env():
    """Loads `_thread_limit_from_env` from `r2db_api/main.py`'s own
    source via AST + isolated exec -- never a plain `import r2db_api.
    main`, which would trigger that module's own module-level `app =
    build_app()` (needs real env vars and a live platform database, the
    SAME reason `test_main_composition_root_wires_pool_size_from_role_
    pool_size` above reads source instead of importing). The function
    itself references nothing else at module scope (a pure parse/raise),
    so lifting just its own AST node out and exec'ing it in an isolated
    namespace is sufficient."""
    spec = importlib.util.find_spec("r2db_api.main")
    assert spec is not None and spec.origin
    source = pathlib.Path(spec.origin).read_text()
    tree = ast.parse(source)
    func_node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_thread_limit_from_env"
    )
    isolated = ast.Module(body=[func_node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace: dict = {}
    exec(compile(isolated, spec.origin, "exec"), namespace)
    return namespace["_thread_limit_from_env"]


def test_thread_limit_from_env_defaults_when_unset_or_empty():
    """Completion conditions 92/152: unset or empty falls back to
    `default`, startup does not fail.

    mutation M190 (`r2db_api/main.py`): treat an empty string as if it
    were a valid override (skip the `not raw` short-circuit) -- this
    test's own second assertion (`""` -> `4`) goes red (an empty string
    fails `int("")` and would instead raise, not return `4`)."""
    _thread_limit_from_env = _load_thread_limit_from_env()

    assert _thread_limit_from_env({}, "R2DB_THREAD_LIMIT", 4) == 4
    assert _thread_limit_from_env({"R2DB_THREAD_LIMIT": ""}, "R2DB_THREAD_LIMIT", 4) == 4


def test_thread_limit_from_env_accepts_a_positive_integer():
    """Completion condition 93: a positive integer is returned as-is."""
    _thread_limit_from_env = _load_thread_limit_from_env()

    assert _thread_limit_from_env({"R2DB_THREAD_LIMIT": "6"}, "R2DB_THREAD_LIMIT", 4) == 6


def test_thread_limit_from_env_rejects_zero_negative_or_non_numeric():
    """Completion conditions 94/95/96: `0`, a negative integer, and a
    non-numeric value all stop startup with a `ValueError` naming the
    variable -- never a silent fallback (a resource dimension, per
    `_thread_limit_from_env`'s own docstring).

    mutation M136 (`r2db_api/main.py`): only reject a negative value,
    letting `0` through -- this test's own `"0"` `pytest.raises` goes red
    (no exception is raised).
    mutation M137 (`r2db_api/main.py`): only reject `0`, letting a
    negative value through -- this test's own `"-3"` `pytest.raises` goes
    red.
    mutation M138 (`r2db_api/main.py`): fall back to `default` instead of
    raising when `int()` fails -- this test's own `"abc"` `pytest.raises`
    goes red (returns `4` instead of raising)."""
    _thread_limit_from_env = _load_thread_limit_from_env()

    for raw in ("0", "-3", "abc"):
        with pytest.raises(ValueError, match="R2DB_THREAD_LIMIT"):
            _thread_limit_from_env({"R2DB_THREAD_LIMIT": raw}, "R2DB_THREAD_LIMIT", 4)


# ---------------------------------------------------------------------------
# D-8: `create_app`'s own `thread_limit=` middleware wiring.
# ---------------------------------------------------------------------------


def _run_one_capabilities_request(app) -> None:
    """The minimal http-scope request completion conditions 78/79/etc.
    call "1 回呼ぶ" -- a real `GET /v1/capabilities` through the SAME app
    object, on whichever event loop is currently running (the caller's
    own fresh loop)."""

    async def _once() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))

    asyncio.get_event_loop().run_until_complete(_once())


def test_create_app_default_thread_limit_sets_4_on_a_fresh_loop():
    """Completion condition 78.

    mutation M120 (`r2db_api/http.py`): `DEFAULT_THREAD_LIMIT = 40` --
    this test's own `== 4` assertion goes red."""
    import anyio.to_thread

    service = _build_service()
    app = create_app(service)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        _run_one_capabilities_request(app)

        async def _read() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop.run_until_complete(_read()) == 4
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_create_app_thread_limit_none_adds_no_middleware():
    """Completion condition 80.

    mutation M122 (`r2db_api/http.py`): add the middleware even when
    `thread_limit is None` (hardcode `40` in that branch) -- this test's
    own `total_tokens == 40` (untouched) assertion goes red."""
    import anyio.to_thread

    service = _build_service()
    app = create_app(service, thread_limit=None)
    assert not any(m.cls is http_module.ThreadLimitMiddleware for m in app.app.user_middleware)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        _run_one_capabilities_request(app)

        async def _read() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop.run_until_complete(_read()) == 40
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_create_app_explicit_thread_limit_sets_that_value():
    """Completion condition 82.

    mutation M124 (`r2db_api/http.py`): the middleware sets `DEFAULT_
    THREAD_LIMIT` instead of the value it was constructed with -- this
    test's own `== 7` assertion goes red (reads `4`)."""
    import anyio.to_thread

    service = _build_service()
    app = create_app(service, thread_limit=7)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        _run_one_capabilities_request(app)

        async def _read() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop.run_until_complete(_read()) == 7
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_create_app_middleware_sets_the_limiter_once_per_loop():
    """Completion conditions 84/85: the middleware sets `total_tokens`
    only the FIRST time a given loop serves a request through it (a
    manual reset in between is left untouched by a second request on the
    SAME loop); a DIFFERENT fresh loop gets the same one-time treatment
    independently.

    mutation M126 (`r2db_api/http.py`): drop the loop-membership check so
    the middleware sets `total_tokens` on EVERY request -- this test's
    own second assertion (still `== 3`, unchanged after a manual reset)
    goes red (would read `4` again).
    mutation M127 (`r2db_api/http.py`): track "configured" with a single
    instance-wide flag instead of a per-loop set -- this test's own third
    assertion (loop B independently reaching `4`) goes red (loop B would
    be skipped as "already configured")."""
    import anyio.to_thread

    service = _build_service()
    app = create_app(service)

    loop_a = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop_a)
        _run_one_capabilities_request(app)

        async def _read() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_a.run_until_complete(_read()) == 4

        async def _reset_and_call_again() -> int:
            anyio.to_thread.current_default_thread_limiter().total_tokens = 3
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
                await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_a.run_until_complete(_reset_and_call_again()) == 3
    finally:
        asyncio.set_event_loop(None)
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop_b)
        _run_one_capabilities_request(app)

        async def _read_b() -> int:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert loop_b.run_until_complete(_read_b()) == 4
    finally:
        asyncio.set_event_loop(None)
        loop_b.close()


def test_thread_limit_middleware_call_is_a_coroutine_function():
    """Completion condition 88: `ThreadLimitMiddleware.__call__` is a
    coroutine function (pure-ASGI middleware shape), so `uvicorn.Config(
    ..., interface="auto")` resolves it to asgi3.

    mutation M130 (`r2db_api/http.py`): make `__call__` a plain
    (non-async) method that itself returns a coroutine -- this test's own
    `iscoroutinefunction` assertion goes red."""
    assert inspect.iscoroutinefunction(http_module.ThreadLimitMiddleware.__call__)


def test_create_app_default_return_shape_matches_thread_limit_none():
    """Completion condition 90: the returned value's own shape (identity
    kind, `.app.state.service`, `.app.routes` path set) is the same
    whether `thread_limit` is left at its default or explicitly `None` --
    only the middleware list differs.

    mutation M132 (`r2db_api/http.py`): wrap the FINAL returned value in
    an extra layer instead of adding to the Starlette middleware list --
    this test's own `isinstance(app.app, Starlette)` assertion goes red
    (`app.app` would be the extra wrapper, not the Starlette instance)."""
    from starlette.applications import Starlette

    service = _build_service()
    app_default = create_app(service)
    app_none = create_app(service, thread_limit=None)

    assert isinstance(app_default, type(app_none))
    assert isinstance(app_default.app, Starlette)
    assert app_default.app.state.service is service
    default_paths = {r.path for r in app_default.app.routes}
    none_paths = {r.path for r in app_none.app.routes}
    assert default_paths == none_paths
    assert default_paths, "route table must not be empty"

class _PoolBackedFakeCell:
    """Minimal `StorageBackend` stand-in whose `query()` checks out a
    connection from a REAL `_RolePool` (fake `_connect`, no live
    PostgreSQL needed) and holds it for `hold_s` seconds -- the same
    "hold a checked-out pooled connection for the call's duration" shape
    `PostgresCell.query()` has in production, so N concurrent HTTP
    requests genuinely contend for the pool's own `maxconn` slots rather
    than merely simulating contention.
    """

    def __init__(self, pool: _RolePool, *, hold_s: float) -> None:
        self._pool = pool
        self._hold_s = hold_s

    def query(self, entity, *, select, where, page_size=100, limits=None, order_by=None, cursor=None, deadline=None, clock=None) -> QueryOutcome:
        with self._pool.connection():
            time.sleep(self._hold_s)
        return QueryOutcome(items=[])

    def transact(self, *args, **kwargs):  # pragma: no cover -- not exercised by this test
        raise NotImplementedError

    def apply_schema(self, *args, **kwargs):  # pragma: no cover -- not exercised by this test
        raise NotImplementedError

    def catalog(self, limits=None) -> list[dict]:  # pragma: no cover -- not exercised by this test
        return []


def _fake_pool_connect(self: _RolePool) -> types.SimpleNamespace:
    conn = types.SimpleNamespace()
    conn.closed = 0
    conn.info = types.SimpleNamespace(transaction_status=TransactionStatus.IDLE)
    conn.cursor = lambda: _FakeCursor()
    conn.rollback = lambda: None
    conn.commit = lambda: None
    conn.close = lambda: setattr(conn, "closed", 1)
    return conn


async def test_role_pool_sized_to_declared_concurrency_avoids_premature_503(monkeypatch):
    """Behavioural pin for F-1: with the pool sized via `role_pool_size`
    (the exact function `r2db_api.main`'s composition root uses), exactly
    `concurrency` concurrent requests against ONE application are all
    served (0 x 503); the `concurrency + 1`-th is refused by `DataService.
    _slot` (429 LIMIT_EXCEEDED), never by pool exhaustion (503). `hold_s`
    (how long each request holds its checked-out connection) is longer
    than `acquire_timeout` (how long a waiting request tolerates none
    being free) specifically so an under-sized pool provably times out
    rather than merely running slower.

    Mutation: hardcoding the pool's `maxconn` back to a fixed 4 regardless
    of the declared `concurrency=6` this test configures turns this red --
    the 5th/6th requests in the first batch, and up to 3 of the 7 in the
    second, then time out waiting for a pooled connection and get 503
    instead of the assertions below.

    R-101 WP-3 (D-13): this test tries the declared `concurrency`'s own
    simultaneous arrival, so it builds the app with `thread_limit=None`
    (anyio's own untouched default, 40) -- `create_app`'s own production
    default (`DEFAULT_THREAD_LIMIT`, 4) would itself become the bottleneck
    at `concurrency=6`, which is exactly the OTHER thing (D-13's own
    trade-off) this behavioural pin is not testing.

    mutation M200 (`r2db_api/limits.py`): `role_pool_size` always returns
    `4` -- this test's own 503-count assertions go red (the pool
    under-sizes relative to the declared `concurrency=6`, so requests
    time out waiting for a pooled connection instead of completing)."""
    monkeypatch.setattr(_RolePool, "_connect", _fake_pool_connect)
    monkeypatch.setattr(_RolePool, "_liveness_check", lambda self, conn: True)

    concurrency = 6
    resource_limits = ResourceLimits(concurrency=concurrency, requests_per_minute=100_000)
    pool = _RolePool(
        "postgresql://unused.example.invalid/db", schema="public",
        maxconn=role_pool_size(resource_limits), acquire_timeout=0.3,
    )
    cell = _PoolBackedFakeCell(pool, hold_s=0.6)

    credentials = CredentialStore(pepper=PEPPER)
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    service = DataService(credentials, limits=resource_limits, initial_cells={"app-a": cell})

    async def _one_query(client: httpx.AsyncClient):
        return await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})

    async with _client(service, thread_limit=None) as client:
        responses = await asyncio.wait_for(asyncio.gather(*[_one_query(client) for _ in range(concurrency)]), timeout=5.0)
    statuses = [r.status_code for r in responses]
    assert statuses.count(503) == 0, f"pool exhaustion (503) at in-flight == declared concurrency: {statuses}"
    assert statuses.count(200) == concurrency, statuses

    async with _client(service, thread_limit=None) as client:
        responses = await asyncio.wait_for(asyncio.gather(*[_one_query(client) for _ in range(concurrency + 1)]), timeout=5.0)
    statuses = [r.status_code for r in responses]
    assert statuses.count(503) == 0, f"pool exhaustion (503) below the declared concurrency + 1 bound: {statuses}"
    assert statuses.count(429) == 1, f"exactly one request must be refused by the slot limiter (429), got: {statuses}"
    assert statuses.count(200) == concurrency, statuses


# ---------------------------------------------------------------------------
# D-13: the thread limiter (4, default) bounds how many requests run their
# synchronous section at once, WITHOUT changing concurrency-slot admission
# (still `concurrency`, 8 here) or the deadlock-free wait discipline.
# ---------------------------------------------------------------------------


async def test_thread_limit_bounds_synchronous_concurrency_while_slot_admission_stays_at_the_declared_ceiling():
    """Completion conditions 116/117: with `concurrency=8` and `create_
    app`'s own default `thread_limit` (4), 8 concurrent requests are all
    ADMITTED (their concurrency slot is taken on the event-loop thread,
    before any of them ever reaches a worker thread) while at most 4 of
    them ever run their own synchronous section (`query_page`) at once; a
    9th, sent once the first 8 have already been admitted, is refused
    with 429 (slot exhaustion, never a worker-thread queue effect); once
    released, all 8 complete with 200 (no deadlock, no timeout).

    mutation M156 (`r2db_api/http.py`): move the handler's own slot
    acquisition INTO the function delegated to `run_in_threadpool` (so it
    happens AFTER a worker thread is granted, not before) -- only the
    (up to 4) requests that already hold a worker thread would then hold
    a slot at the moment the 9th is sent, so this test's own `resp9.
    status_code == 429` assertion goes red (the 9th finds a free slot
    among the 4 not yet admitted and is served, 200).
    mutation M157 (`r2db_api/http.py`): drop the `total_tokens`
    assignment from the middleware's own `__call__` (limiter stays
    anyio's untouched default, 40) -- this test's own `peak == 4`
    assertion goes red (all 8 requests run their synchronous section
    concurrently, `peak == 8`)."""
    concurrency = 8
    service = _build_service(concurrency=concurrency, requests_per_minute=100_000)

    lock = threading.Lock()
    current = 0
    peak = 0
    release = threading.Event()
    original_query_page = service.query_page

    def blocking_query_page(*args, **kwargs):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        release.wait(timeout=5.0)
        with lock:
            current -= 1
        return original_query_page(*args, **kwargs)

    service.query_page = blocking_query_page

    async with _client(service) as client:

        async def _one_query():
            return await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})

        tasks = [asyncio.ensure_future(_one_query()) for _ in range(concurrency)]
        # All 8 handler coroutines run synchronously up to their own first
        # `await` (the body read, AFTER slot acquisition) within this one
        # loop iteration -- a single yield-back is enough for all 8 to
        # have already been admitted (same ordering guarantee `test_sync_
        # section_runs_off_the_event_loop` above relies on).
        await asyncio.sleep(0)

        resp9 = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
        assert resp9.status_code == 429, resp9.text

        # Real worker-thread dispatch (unlike slot admission above) needs
        # actual wall-clock time for the OS scheduler to run the up-to-4
        # threads the limiter grants -- long enough that `peak` has
        # genuinely reached its ceiling before `release` unblocks them.
        for _ in range(100):
            await asyncio.sleep(0.01)
            with lock:
                if current == 4:
                    break

        release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

    assert peak == 4, f"synchronous concurrency must be bounded to the thread limiter (4), observed peak={peak}"
    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == concurrency, statuses
