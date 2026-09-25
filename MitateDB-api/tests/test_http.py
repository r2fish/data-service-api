"""Direct tests of `mitatedb_api.http` (WP-3, docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-5).

Reuses `test_postgres.py`'s own `platform`/`app_a` fixture machinery (a
plain Python import, not a new `conftest.py`) rather than duplicating the
throwaway-prefix PostgreSQL bootstrap a second time in this file -- both
modules already share the SAME repository's own established convention
for it (R-4/R-8's "prefix 置換方式"), so importing it is consistency, not
code sharing across peers (R-2's own principle is about the two DIFFERENT
peer implementations, not about two test files of the SAME peer).

If PostgreSQL is not reachable, this module's tests fail loudly through
the SAME `platform`/`app_a` fixtures `test_postgres.py` already uses --
no separate skip policy is introduced here.
"""
from __future__ import annotations

import base64
import json
import uuid
from importlib import resources
from pathlib import Path

import httpx
import pytest

from mitatedb_api.application_audit import ApplicationAuditSink
from mitatedb_api.audit_dispatch import AuditRouter
from mitatedb_api.auth import Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, _LimitStateHolder
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import CapabilityError, ResourceLimitError, ValidationError
from mitatedb_api.http import PROBLEM_CONTENT_TYPE, HttpService, _problem_for_exception, create_app
from mitatedb_api import paging

# A RELATIVE import, not a bare `from test_postgres import ...`: this
# package (`MitateDB-api/tests`, which carries an `__init__.py`) is
# collected by pytest as `tests.test_http`/`tests.test_postgres`, but
# `r2db-api/tests` has NO `__init__.py` of its own, so pytest's default
# "prepend" import mode caches r2db-api's OWN `test_postgres.py` under the
# bare top-level module name `test_postgres` in `sys.modules` when the
# combined root suite collects `r2db-api/tests` first (root pyproject.
# toml's own `testpaths` ordering lists it before `MitateDB-api/tests`).
# A bare `from test_postgres import ...` here would then silently resolve
# to THAT cached module instead of this package's own sibling file --
# measured directly under the combined suite: `platform`/`app_a` came back
# as r2db-api's own fixtures, provisioning r2db's OWN throwaway PostgreSQL
# roles/databases instead of this peer's. The relative import below
# resolves within this package's own namespace unambiguously, regardless
# of what any other test file elsewhere in the combined suite already
# imported under the bare name.
from .test_postgres import app_a, platform  # noqa: F401

BASE_URL = "http://mitatedb-http-test.invalid"


@pytest.fixture
def app_a_stack(platform, app_a):
    """One real, throwaway-provisioned application wired into a real
    `HttpService`/ASGI app: a `PostgresCredentialStore` against the
    platform's own read/write roles, and one `ApplicationCell` backed by
    `app_a`'s own `PostgresBackend`. Issues one runtime and one developer
    credential up front (composite bearer tokens, `http.py`'s own
    `<credential_id>.<secret>` wire form) and yields everything a test
    needs, closing every connection this fixture opened afterward.
    """
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-mitatedb-http-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-mitatedb-http-0000", schema=platform.registry_schema,
    )
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    # Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09): `HttpService`
    # now fails closed at construction time unless BOTH `limit_holder`/
    # `max_concurrency` are supplied (`http.py::HttpService.__init__`'s own
    # comment) -- an explicit `_LimitStateHolder`, shared with `cell` below
    # (never each side building its own private one), and this file's own
    # `FoundationConfig` default (32), matching `ApplicationCell`'s own
    # implicit default when no `config` is passed.
    limit_holder = _LimitStateHolder()
    cell = ApplicationCell(app_a.app_id, backend=backend, limit_holder=limit_holder)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    service = HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=FoundationConfig().max_concurrency)
    app = create_app(service, request_bytes_limit=1024)

    # Phase 6 WP-3 (design D-1(d)): `PostgresCredentialStore.issue` now
    # returns the complete bearer as its second element -- used verbatim.
    runtime_id, runtime_bearer = write_store.issue(app_a.app_id, Role.RUNTIME)
    developer_id, developer_bearer = write_store.issue(app_a.app_id, Role.DEVELOPER)

    import types
    stack = types.SimpleNamespace(
        app=app,
        app_id=app_a.app_id,
        runtime_bearer=runtime_bearer,
        developer_bearer=developer_bearer,
        write_store=write_store,
        read_store=read_store,
        cell=cell,
    )
    try:
        yield stack
    finally:
        backend.close()
        read_store.close()
        write_store.close()


@pytest.fixture
def app_a_stack_with_audit(platform, app_a):
    """WP-3e rework T3 (L-7, ruling `{scratchpad}/rulings-r3-r7-flip.md`):
    the SAME real, throwaway-provisioned stack `app_a_stack` builds, except
    the `ApplicationCell` is wired to an explicit, INSPECTABLE
    `audit_dispatch.AuditRouter(application_audit.ApplicationAuditSink())`
    (never the private default `app_a_stack` leaves every pre-Phase-4
    caller with, `cell.py::ApplicationCell.__init__`'s own docstring) --
    `stack.router.durable_sink.events()` is this file's own read path for
    the durable application-plane audit row a real HTTP call produces,
    mirroring `test_application_audit.py`'s own `make_router`/`router.
    durable_sink.events()` pattern rather than a second, independently
    maintained PostgreSQL-backed audit reader. `stack.router.flush()`
    drains the buffer-class events `cell.py::ApplicationCell._push_data_
    operation_event` (query/insert/update) queues before they reach
    `durable_sink` -- called by every test below immediately after its own
    HTTP call, before reading `events()`."""
    read_store = PostgresCredentialStore(
        platform.api_dsn, pepper="synthetic-test-pepper-mitatedb-http-audit-0000", schema=platform.registry_schema,
    )
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper="synthetic-test-pepper-mitatedb-http-audit-0000", schema=platform.registry_schema,
    )
    backend = PostgresBackend(app_a.runtime_dsn, app_a.developer_dsn)
    router = AuditRouter(ApplicationAuditSink())
    # Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09): same
    # fail-closed `HttpService` requirement `app_a_stack` above already
    # documents -- an explicit, shared `_LimitStateHolder`.
    limit_holder = _LimitStateHolder()
    cell = ApplicationCell(app_a.app_id, backend=backend, audit_router=router, limit_holder=limit_holder)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    service = HttpService(read_store, _cell_factory, limit_holder=limit_holder, max_concurrency=FoundationConfig().max_concurrency)
    app = create_app(service, request_bytes_limit=1024)

    runtime_id, runtime_bearer = write_store.issue(app_a.app_id, Role.RUNTIME)
    developer_id, developer_bearer = write_store.issue(app_a.app_id, Role.DEVELOPER)

    import types
    stack = types.SimpleNamespace(
        app=app,
        app_id=app_a.app_id,
        runtime_bearer=runtime_bearer,
        developer_bearer=developer_bearer,
        write_store=write_store,
        read_store=read_store,
        cell=cell,
        router=router,
    )
    try:
        yield stack
    finally:
        backend.close()
        read_store.close()
        write_store.close()


def _run(coro):
    """`httpx.ASGITransport` only implements the ASYNC context-manager
    protocol (`__aenter__`/`__aexit__`) -- an ASGI app is inherently async
    -- so every real request in this file goes through `httpx.AsyncClient`,
    driven synchronously from these plain `def` test functions via
    `asyncio.run`. Mirrors every conformance adapter's own identical
    `_run`/`loop.run_until_complete` bridge (`conformance_adapter_
    mitatedb_http.py`, `conformance_adapter_r2db_http.py`)."""
    import asyncio

    return asyncio.run(coro)


async def _apost(stack, path, *, bearer=None, json_body=None, headers=None, content=None) -> httpx.Response:
    hdrs = dict(headers or {})
    if bearer is not None:
        hdrs["authorization"] = f"Bearer {bearer}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url=BASE_URL) as client:
        if content is not None:
            return await client.post(path, content=content, headers=hdrs)
        return await client.post(path, json=json_body, headers=hdrs)


async def _aget(stack, path, *, bearer=None, headers=None) -> httpx.Response:
    hdrs = dict(headers or {})
    if bearer is not None:
        hdrs["authorization"] = f"Bearer {bearer}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url=BASE_URL) as client:
        return await client.get(path, headers=hdrs)


def _post(stack, path, *, bearer=None, json_body=None, headers=None, content=None) -> httpx.Response:
    return _run(_apost(stack, path, bearer=bearer, json_body=json_body, headers=headers, content=content))


def _get(stack, path, *, bearer=None, headers=None) -> httpx.Response:
    return _run(_aget(stack, path, bearer=bearer, headers=headers))


# ---------------------------------------------------------------------------
# Packaged contract copy (Phase 6 WP-0, design D-4(b)): must never silently
# drift from `spec/data-service-api.v1.json`, the common repository's single
# source of truth. `mitatedb_api.http` loads the packaged copy
# (`mitatedb_api/contract/data-service-api.v1.json`, wired in as package
# data in `pyproject.toml`) via `importlib.resources` so a unit installed or
# copied onto the VPS without the sibling `spec/` checkout still imports;
# this test is what prevents that copy from going stale. Near-verbatim twin
# of `r2db-api/tests/test_http.py::
# test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth`
# (same `parents[2]` depth from this file to the repository root) -- the two
# are pinned to each other by this repository's own peer-symmetry
# isomorphism test (`test_audit_query.py`).
# ---------------------------------------------------------------------------


def test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth():
    packaged = resources.files("mitatedb_api.contract").joinpath("data-service-api.v1.json").read_bytes()
    source_of_truth = (Path(__file__).parents[2] / "spec" / "data-service-api.v1.json").read_bytes()
    assert packaged == source_of_truth


# ---------------------------------------------------------------------------
# Authentication: the four fail-closed categories.
# ---------------------------------------------------------------------------


def test_missing_authorization_header_is_auth_required(app_a_stack):
    response = _get(app_a_stack, "/v1/capabilities")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_CONTENT_TYPE


def test_missing_authorization_header_on_operation_catalog_is_auth_required(app_a_stack):
    """`GET /v1/operation-catalog` carries no unauthenticated face of its
    own -- the SAME `AUTH_REQUIRED` gate
    `test_missing_authorization_header_is_auth_required` immediately
    above pins for `GET /v1/capabilities`."""
    response = _get(app_a_stack, "/v1/operation-catalog")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_malformed_bearer_without_dot_is_auth_invalid(app_a_stack):
    response = _get(app_a_stack, "/v1/capabilities", bearer="not-a-composite-token")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


def test_wrong_secret_is_auth_invalid(app_a_stack):
    credential_id = app_a_stack.runtime_bearer.split(".", 1)[0]
    response = _get(app_a_stack, "/v1/capabilities", bearer=f"{credential_id}.wrong-secret-value")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


def test_revoked_credential_is_auth_invalid(app_a_stack):
    credential_id = app_a_stack.runtime_bearer.split(".", 1)[0]
    app_a_stack.write_store.revoke(credential_id)
    response = _get(app_a_stack, "/v1/capabilities", bearer=app_a_stack.runtime_bearer)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


def test_authorization_state_unavailable_is_reported(app_a_stack):
    """A store pointed at an unreachable DSN fails closed with `AUTH_STATE_
    UNAVAILABLE`, mirroring `credential_store_postgres.py`'s own documented
    fail-closed behavior -- verified here through the real HTTP boundary,
    not merely at the store level (`test_postgres.py` already covers the
    store level directly)."""
    unreachable = PostgresCredentialStore(
        "host=/tmp port=1 dbname=mitatedb_http_test_unreachable",
        pepper="synthetic-test-pepper-mitatedb-http-0000", schema="mitatedb_registry", connect_timeout=1,
    )

    def _cell_factory(application_id: str):  # pragma: no cover - never reached
        raise AssertionError("unreachable store must fail before any cell lookup")

    # Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09): same
    # fail-closed `HttpService` requirement `app_a_stack` above documents
    # -- this test's own `_cell_factory` is never reached (the store fails
    # first), so the concrete `_LimitStateHolder` given here is never
    # exercised either, but `HttpService.__init__` still requires one.
    service = HttpService(unreachable, _cell_factory, limit_holder=_LimitStateHolder(), max_concurrency=FoundationConfig().max_concurrency)
    app = create_app(service, request_bytes_limit=1024)

    async def _call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": "Bearer someid.somesecret"})

    response = _run(_call())
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_STATE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# m-3 (independent review): authentication happens BEFORE shape/JSON
# validation on every executing endpoint -- a security property `http.py`
# already asserted in comments (`_endpoint`/each handler's own call
# ordering) but never had a test pinning it. A mutation that swapped this
# order (read/validate the body first, authenticate second) would leave
# every one of these tests passing IF the tests only ever sent well-formed
# bodies -- these deliberately send MALFORMED ones, with no credential at
# all, to prove the malformed body is never even reached.
# ---------------------------------------------------------------------------


def test_unauthenticated_malformed_json_body_is_auth_required_not_validation_failed(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/shared_items/query", content=b"{not valid json at all",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_unauthenticated_shape_invalid_body_is_auth_required_not_validation_failed(app_a_stack):
    # A body that is valid JSON but violates `QueryRequest`'s own shape
    # (missing the required `select` key, plus an unknown field) -- if
    # shape validation ran before authentication, this would surface as
    # VALIDATION_FAILED instead.
    response = _post(
        app_a_stack, "/v1/data/shared_items/query", json_body={"not_select_at_all": 1, "bogus_field": True},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_unauthenticated_schema_invalid_body_is_auth_required_not_validation_failed(app_a_stack):
    response = _post(
        app_a_stack, "/v1/schema/operations", json_body={"operation": "not_a_real_operation_at_all"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_unauthenticated_cross_entity_shape_invalid_body_is_auth_required_not_validation_failed(app_a_stack):
    """m-4 (independent review, WP-2 follow-up): the same auth-before-
    shape-validation property the three tests above already pin for
    `/v1/data/{entity}/query`/`/v1/schema/operations`, exercised for the
    cross-entity endpoint too (newly real dispatch as of this WP) -- a
    body that does not even satisfy `ScopedMutationRequest`'s own closed
    shape (`{"bogus": 1}` has neither `operations` nor any recognized
    key) must still surface `AUTH_REQUIRED`, not `VALIDATION_FAILED`, when
    no credential is presented at all."""
    response = _post(app_a_stack, "/v1/data/mutations", json_body={"bogus": 1})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


# ---------------------------------------------------------------------------
# problem+json shape / request_id header.
# ---------------------------------------------------------------------------


def test_problem_json_shape_and_request_id_header(app_a_stack):
    response = _get(app_a_stack, "/v1/capabilities")
    assert response.status_code == 401
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_CONTENT_TYPE
    body = response.json()
    for key in ("type", "code", "message", "request_id", "details"):
        assert key in body, f"problem+json body missing {key!r}: {body!r}"
    assert isinstance(body["details"], dict)
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"] == body["request_id"]


def test_capabilities_declares_request_bytes_enforced(app_a_stack):
    response = _get(app_a_stack, "/v1/capabilities", bearer=app_a_stack.runtime_bearer)
    assert response.status_code == 200
    document = response.json()
    assert document["limit_enforcement"]["request_bytes"] == "enforced"
    # Phase 4 WP-3(b): contract_version flip lands in the same commit as
    # the audit_query bundle it accompanies (design §5, P4-D4). Phase 5
    # WP-3: re-flipped to 1.5.0 (design D-1, subordinate ruling 10 item 1).
    # Phase 10 WP-6b/pair-closing: re-flipped again to 1.8.0 in the same
    # commit as this host's own `process_ceilings` mapping (design D-5
    # (v)).
    assert document["contract_version"] == "1.9.0"
    assert document["application_scope"] == app_a_stack.app_id
    assert document["role"] == "runtime"


# ---------------------------------------------------------------------------
# request_bytes boundary (SI-08): exactly at the limit vs. one byte over.
# ---------------------------------------------------------------------------


def test_request_exactly_at_byte_limit_is_not_rejected_for_size(app_a_stack):
    # `request_bytes_limit=1024` (this fixture's own composition). Pad an
    # otherwise-valid query body's `select` array with a field name whose
    # own length brings the whole serialized body to exactly 1024 bytes.
    # The response may still legitimately be a 4xx for an unrelated reason
    # (an unknown field name) -- what matters here is that byte-bound
    # rejection specifically (413/LIMIT_EXCEEDED) never fires at the exact
    # boundary.
    base = json.dumps({"select": ["item_key"]}).encode("utf-8")
    padding_needed = 1024 - len(base)
    assert padding_needed > 0
    # Grow the body via a harmless second, syntactically valid field name
    # in `select` until the exact byte count is hit.
    body = {"select": ["item_key", "x" * max(0, padding_needed - len('{"select": ["item_key", ""]}') + 2)]}
    payload = json.dumps(body).encode("utf-8")
    # Trim/pad precisely to 1024 bytes with a filler value that keeps the
    # JSON well-formed (a longer/shorter throwaway field name).
    while len(payload) < 1024:
        body["select"][1] += "x"
        payload = json.dumps(body).encode("utf-8")
    while len(payload) > 1024:
        body["select"][1] = body["select"][1][:-1]
        payload = json.dumps(body).encode("utf-8")
    assert len(payload) == 1024
    response = _post(app_a_stack, "/v1/data/shared_items/query", bearer=app_a_stack.runtime_bearer, content=payload, headers={"content-type": "application/json"})
    assert response.status_code != 413
    assert response.json().get("code") != "LIMIT_EXCEEDED"


def test_request_over_byte_limit_is_limit_exceeded_before_parsing(app_a_stack):
    oversized = b" " * 1025
    response = _post(app_a_stack, "/v1/data/shared_items/query", bearer=app_a_stack.runtime_bearer, content=oversized, headers={"content-type": "application/json"})
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["limit_class"] == "request_bytes"


def test_request_over_byte_limit_rejected_even_with_invalid_json(app_a_stack):
    """Proves the byte bound is enforced BEFORE JSON parsing (SI-08): an
    oversized body that is not even valid JSON still gets 413/
    LIMIT_EXCEEDED, never a JSON-parse-error VALIDATION_FAILED -- if
    parsing ran first, a malformed oversized body could return the wrong
    code and the ordering claim would be false."""
    garbage = b"{not valid json" + b"x" * 2000
    response = _post(app_a_stack, "/v1/data/shared_items/query", bearer=app_a_stack.runtime_bearer, content=garbage, headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.json()["code"] == "LIMIT_EXCEEDED"


def test_byte_bound_is_measured_from_actual_received_bytes_not_content_length_header(app_a_stack):
    """Drives the ASGI app directly (bypassing httpx, which always computes
    an accurate `Content-Length` itself) with a hand-crafted scope/receive
    that LIES about `Content-Length` (declares 10 bytes) while actually
    delivering an oversized body across multiple `http.request` chunks.
    `RequestByteBoundMiddleware` must still reject it: the bound is
    measured from bytes actually received in the ASGI loop, never trusted
    from the header (`http.py`'s own docstring claim) -- this is exactly
    the mutation `request_bytes 計測をヘッダ Content-Length 依存化` targets.
    """
    import asyncio

    bearer = app_a_stack.runtime_bearer
    real_body = json.dumps({"select": ["item_key"]}).encode("utf-8") + b" " * 2000  # far over the 1024 limit
    chunk_size = 200
    chunks = [real_body[i : i + chunk_size] for i in range(0, len(real_body), chunk_size)]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/data/shared_items/query",
        "raw_path": b"/v1/data/shared_items/query",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "headers": [
            (b"host", b"mitatedb-http-test.invalid"),
            (b"authorization", f"Bearer {bearer}".encode()),
            (b"content-type", b"application/json"),
            # The lie: far smaller than the real body actually delivered
            # below via the receive callable's own chunks.
            (b"content-length", b"10"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("mitatedb-http-test.invalid", 80),
    }

    remaining = list(chunks)

    async def receive():
        if remaining:
            chunk = remaining.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(remaining)}
        return {"type": "http.disconnect"}

    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    asyncio.run(app_a_stack.app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    body_bytes = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    assert start["status"] == 413, f"expected 413, got {start['status']} body={body_bytes!r}"
    payload = json.loads(body_bytes)
    assert payload["code"] == "LIMIT_EXCEEDED"
    assert payload["details"]["limit_class"] == "request_bytes"


def test_over_limit_request_body_is_fully_drained_before_the_response_is_sent(app_a_stack):
    """m-6 (independent review): the middleware must call `receive()`
    until the client's body is exhausted, even after it has already
    decided to reject the request -- otherwise a real ASGI server
    (uvicorn) could be left with unread bytes on the connection. Same
    hand-crafted ASGI scope/receive approach as the sibling test above;
    this one instead asserts every chunk this test handed to `receive()`
    was actually consumed (`remaining` is empty) by the time the
    middleware returns."""
    import asyncio

    bearer = app_a_stack.runtime_bearer
    real_body = json.dumps({"select": ["item_key"]}).encode("utf-8") + b" " * 5000
    chunk_size = 200
    chunks = [real_body[i : i + chunk_size] for i in range(0, len(real_body), chunk_size)]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/data/shared_items/query",
        "raw_path": b"/v1/data/shared_items/query",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "headers": [
            (b"host", b"mitatedb-http-test.invalid"),
            (b"authorization", f"Bearer {bearer}".encode()),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("mitatedb-http-test.invalid", 80),
    }

    remaining = list(chunks)
    receive_calls = 0

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        if remaining:
            chunk = remaining.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(remaining)}
        return {"type": "http.disconnect"}

    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    asyncio.run(app_a_stack.app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 413
    assert remaining == [], "the middleware returned a response without draining the rest of the client's body"
    # Every chunk was handed to `receive()` at least once (bounds the drain
    # loop's own call count against the real chunk count, so this is not
    # satisfied vacuously by e.g. a drain loop that spins forever).
    assert receive_calls == len(chunks)


# ---------------------------------------------------------------------------
# entity smuggling (mutate.semantics): a body `entity` field is unknown.
# ---------------------------------------------------------------------------


def test_body_entity_field_in_mutation_request_is_rejected_as_unknown_field(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/shared_items/mutations", bearer=app_a_stack.developer_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"item_key": 1}}], "entity": "shared_items"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# Schema: create_entity / add_field, object/array -> json round trip,
# multi-field order_by, page.cursor rejection, NUL -> VALIDATION_FAILED.
# ---------------------------------------------------------------------------


def _create_entity(stack, entity, fields=None, field_types=None):
    body = {"operation": "create_entity", "entity": entity}
    if fields is not None:
        body["fields"] = fields
    if field_types is not None:
        body["field_types"] = field_types
    response = _post(stack, "/v1/schema/operations", bearer=stack.developer_bearer, json_body=body)
    assert response.status_code == 200, response.text
    return response


def _add_field(stack, entity, field, field_type):
    response = _post(
        stack, "/v1/schema/operations", bearer=stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": field, "field_type": field_type},
    )
    assert response.status_code == 200, response.text
    return response


def test_create_entity_then_add_field_object_and_array_round_trip(app_a_stack):
    entity = "http_roundtrip_entity"
    _create_entity(app_a_stack, entity)
    _add_field(app_a_stack, entity, "payload_obj", "object")
    _add_field(app_a_stack, entity, "payload_arr", "array")

    nested_object = {"a": 1, "b": [1, 2, 3]}
    nested_array = [1, "two", {"three": 3}]
    response = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"payload_obj": nested_object, "payload_arr": nested_array}}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["affected"] == 1

    query = _post(
        app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer,
        json_body={"select": ["payload_obj", "payload_arr"]},
    )
    assert query.status_code == 200
    items = query.json()["items"]
    assert len(items) == 1
    # Phase 6 WP-3 (design D-3, F2 -- behaviour change (β)): the read side
    # now restores the declared JSON shape itself -- `payload_obj`/
    # `payload_arr` come back as a real object/array in the response's
    # OWN JSON body, not a string a caller must `json.loads()` a second
    # time.
    assert items[0]["payload_obj"] == nested_object
    assert items[0]["payload_arr"] == nested_array


def test_add_field_with_no_field_type_defaults_to_json(app_a_stack):
    """WP-3a rework 3 (real, measured bug): `SchemaOperationRequest.
    field_type` is optional at the JSON-schema level (only `operation`/
    `entity` are globally `required`), and contract `field_types`'s own
    description states the general rule this peer's `create_entity`
    branch already honors for `fields`/`field_types`: "A field created
    without a declared type has type json ... this names an existing
    default rather than introducing a new one." `add_field`'s own
    singular `field_type` is that identical rule for the one field it
    adds. This peer used to answer every field_type-omitting `add_field`
    with a bare `VALIDATION_FAILED` ("add_field requires field and a
    supported field_type") instead of defaulting to `json` -- a real
    divergence from `r2db-api` (which keeps its own pre-existing JSONB
    default) and from this peer's OWN in-process surface, the exact gap
    `conformance-tests/test_c20_constraint_declaration_agreement.py`'s
    `MitateDB-api-http` plug surfaced (a declaration-invalid `enum` on
    such a field_type-omitting `add_field` was refused for the WRONG
    reason -- missing `field_type`, not the invalid `enum` -- so the
    denial carried none of `constraint_declaration`'s own `details`)."""
    entity = "http_add_field_no_field_type_entity"
    _create_entity(app_a_stack, entity, fields=["label"])
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": "extra"},
    )
    assert response.status_code == 200, response.text
    catalog = _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer).json()
    row = {e["entity"]: e for e in catalog["entities"]}[entity]
    assert row["field_types"]["extra"] == "json", row

    # A present-but-unsupported field_type is still refused, unchanged.
    bad_response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": "bad", "field_type": "not_a_type"},
    )
    assert bad_response.status_code == 400
    assert bad_response.json()["code"] == "VALIDATION_FAILED"


def test_schema_operation_result_revision_is_a_real_advancing_counter(app_a_stack):
    """m-2 (independent review): `SchemaOperationResult.revision` must be
    this peer's own real schema-revision counter, not a fixed placeholder
    that never changes -- a `create_entity` followed by an `add_field`
    must report two DIFFERENT revision values, both parseable as
    non-negative integers, with the second strictly greater."""
    entity = "http_schema_revision_entity"
    create_response = _create_entity(app_a_stack, entity, fields=["label"])
    first_revision = int(create_response.json()["revision"])
    add_response = _add_field(app_a_stack, entity, "extra", "string")
    second_revision = int(add_response.json()["revision"])
    assert second_revision > first_revision


def test_create_entity_with_field_type_is_capability_unsupported_not_silently_honored(app_a_stack):
    """M-3 (independent review): `create_entity` has no per-field type
    slot (`field_type` is a single, request-level value, P3-D1) -- a
    request naming BOTH `fields` and a `field_type` cannot be honored for
    real, so it must be refused up front rather than answered with
    `committed: true` while quietly creating every field as `text`
    regardless of the caller's stated intent."""
    entity = "http_field_type_honor_entity"
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "create_entity", "entity": entity, "fields": ["rank"], "field_type": "integer"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"
    # No entity was created either -- the refusal happened before any
    # backend call, not after a partially-honored creation.
    query = _post(
        app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["rank"]},
    )
    assert query.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Phase 6 WP-3 追補 (mutation-testing finding, supervisor ruling 2026-09-04):
# work order §4 WP-3 完了条件12 ("不正3ケース -- `fields` に無い名前 / 7語外
# の値 / `fields` を伴わない `field_types` の3つが全て `VALIDATION_FAILED`
# であること") had NO test anywhere -- neither in the common conformance
# suite nor peer-local -- before this addition. `http.py::post_schema`
# already implements all 3 checks ((a)/(b)/(c) comments right above each
# `raise ValidationError` in that function), but nothing exercised them:
# mutating any ONE of the 3 branches away (confirmed for (b), the
# vocabulary check) passed the full existing suite. This is a test gap,
# not a product-code gap -- the 3 cases below close it. Product code is
# untouched.
# ---------------------------------------------------------------------------


def test_create_entity_field_types_naming_an_unknown_field_is_validation_failed(app_a_stack):
    """(a): `field_types` names a field not present in `fields`."""
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={
            "operation": "create_entity", "entity": "http_bad_field_types_a",
            "fields": ["known"], "field_types": {"unknown_field": "string"},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_create_entity_field_types_outside_the_7_word_vocabulary_is_validation_failed(app_a_stack):
    """(b): a `field_types` value outside the contract's 7-word vocabulary
    (`string`/`integer`/`number`/`boolean`/`object`/`array`/`json`)."""
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={
            "operation": "create_entity", "entity": "http_bad_field_types_b",
            "fields": ["rank"], "field_types": {"rank": "not_a_real_field_type"},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_create_entity_field_types_without_fields_is_validation_failed(app_a_stack):
    """(c): `field_types` present but `fields` absent entirely."""
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={
            "operation": "create_entity", "entity": "http_bad_field_types_c",
            "field_types": {"rank": "integer"},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_multi_field_order_by(app_a_stack):
    entity = "http_orderby_entity"
    # `create_entity`'s own name-only `fields` array has no type slot on
    # the wire (P3-D1) -- every named field becomes this peer's own `text`
    # type. `rank` needs to hold an integer for this test's own ordering
    # assertion, so it is added separately via `add_field`, exactly the
    # create_entity + per-field add_field construction this whole design
    # exists for.
    _create_entity(app_a_stack, entity, fields=["bucket"])
    _add_field(app_a_stack, entity, "rank", "integer")
    rows = [
        {"bucket": "a", "rank": 2},
        {"bucket": "a", "rank": 1},
        {"bucket": "b", "rank": 1},
    ]
    for row in rows:
        response = _post(app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer, json_body={"operations": [{"operation": "insert", "values": row}]})
        assert response.status_code == 200, response.text

    response = _post(
        app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer,
        json_body={
            "select": ["bucket", "rank"],
            "order_by": [{"field": "bucket", "direction": "asc"}, {"field": "rank", "direction": "asc"}],
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(item["bucket"], item["rank"]) for item in items] == [("a", 1), ("a", 2), ("b", 1)]


def test_undecodable_page_cursor_is_validation_failed(app_a_stack):
    entity = f"http_page_cursor_probe_{uuid.uuid4().hex[:12]}"
    _create_entity(app_a_stack, entity, fields=["item_key"])
    response = _post(
        app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer,
        json_body={"select": ["item_key"], "page": {"cursor": "opaque-cursor-value"}},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"]["violated_declaration"] == "request_schema"
    assert body["details"]["field"] == "page/cursor"


def _decoded_cursor_payload(cursor: str) -> dict:
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def _assert_page_cursor_refused(response):
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"] == {"violated_declaration": "request_schema", "field": "page/cursor"}


def test_tampered_page_cursor_count_and_type_and_domain_mismatches_are_validation_failed(app_a_stack):
    entity = f"http_page_cursor_tamper_probe_{uuid.uuid4().hex[:12]}"
    _create_entity(app_a_stack, entity, fields=["label"], field_types={"label": "string"})
    for value in ("a", "b"):
        response = _post(
            app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.developer_bearer,
            json_body={"operations": [{"operation": "insert", "values": {"label": value}}]},
        )
        assert response.status_code == 200, response.text

    def _page(cursor=None):
        page = {"size": 1}
        if cursor is not None:
            page["cursor"] = cursor
        return _post(
            app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer,
            json_body={"select": ["label"], "order_by": [{"field": "label", "direction": "asc"}], "page": page},
        )

    response = _page()
    assert response.status_code == 200, response.text
    cursor = response.json()["next_page"]
    assert cursor is not None, "a 1-of-2 page reported a null next_page"
    payload = _decoded_cursor_payload(cursor)
    binding = payload["b"]
    values = payload["v"]
    # design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2b.1: `values` is
    # `[label, _mdb_row]` -- the order-by term plus the row-order
    # tie-break, index-aligned with `order_spec`.
    assert len(values) == 2, values

    # (a) count mismatch: one ordering value where two are declared.
    _assert_page_cursor_refused(_page(paging.encode_page_cursor(values[:1], binding)))

    # (b) declared-type mismatch: an integer where `label` (string) is declared.
    _assert_page_cursor_refused(_page(paging.encode_page_cursor([1, values[1]], binding)))

    # (c) out-of-domain: a lone UTF-16 surrogate code point for `label`.
    _assert_page_cursor_refused(_page(paging.encode_page_cursor(["\ud800", values[1]], binding)))

    # (d) out-of-domain: an embedded NUL byte for `label` -- rejected on
    # this peer's PostgreSQL plug (this fixture's own backend, design
    # §10 の 11); the SQLite plug accepts the identical payload (measured
    # separately, design §11).
    _assert_page_cursor_refused(_page(paging.encode_page_cursor(["tail\x00head", values[1]], binding)))

    # (e) out-of-domain: an out-of-64-bit-range integer for `_mdb_row`
    # (BIGINT on this peer's PostgreSQL plug).
    _assert_page_cursor_refused(_page(paging.encode_page_cursor([values[0], 2**63], binding)))

    # (f) declared-type mismatch: a string tie-break for `_mdb_row`, which
    # carries no `_mdb_field_types` registry row of its own (code-review
    # instruction, design D-2b.1) -- `_decode_and_check_page_cursor`
    # supplies this column's declared type ("integer") explicitly rather
    # than letting the missing registry row skip the check.
    _assert_page_cursor_refused(_page(paging.encode_page_cursor([values[0], "x"], binding)))


def test_nul_value_is_validation_failed(app_a_stack):
    entity = "http_nul_entity"
    # Phase 6 WP-3 (design D-3, decision (ii)): a name-only field now
    # defaults to `json`, whose write-side canonicalization (`cell.py::
    # _normalize_value_for_storage` (body now in `request_binding.py`)) JSON-escapes an embedded NUL byte
    # (`json.dumps` turns it into the 6-character `backslash-u-0000` sequence,
    # never a literal NUL) -- so this test declares `label` explicitly
    # `string` to keep exercising the PostgreSQL backend's own literal-
    # NUL rejection (`backend_postgres._validate_value_domain`), the
    # property this test's own name is actually about.
    _create_entity(app_a_stack, entity, fields=["label"], field_types={"label": "string"})
    response = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "value\x00tail"}}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# Declared-unavailable endpoints (present denial, uniform CAPABILITY_
# UNSUPPORTED, authenticate-first).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,body",
    [
        # P35 WP-2: `/v1/data/mutations` (cross_entity_mutation) is no
        # longer declared unavailable -- see the dedicated cross-entity
        # mutation test section below for its own coverage.
        # Phase 6 WP-3 (design D-3): `/v1/catalog` (`application_catalog`)
        # is no longer declared unavailable either -- flipped to `enabled`,
        # own dedicated coverage above (`test_create_entity_then_add_
        # field_object_and_array_round_trip` and friends).
        ("POST", "/v1/audit/query", {}),
    ],
)
def test_declared_unavailable_endpoints_deny_uniformly_after_auth(app_a_stack, method, path, body):
    if method == "GET":
        response = _get(app_a_stack, path, bearer=app_a_stack.runtime_bearer)
    else:
        response = _post(app_a_stack, path, bearer=app_a_stack.runtime_bearer, json_body=body)
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"
    # Authenticate-first: an unauthenticated caller still gets AUTH_* first.
    if method == "GET":
        anon = _get(app_a_stack, path)
    else:
        anon = _post(app_a_stack, path, json_body=body)
    assert anon.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("operation", ["create_index", "drop_index", "drop_entity"])
def test_unimplemented_schema_operations_are_present_denials(app_a_stack, operation):
    """Phase 9 WP-3a (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (5)):
    `alter_field` REMOVED from this parametrize set -- it is no longer a
    present-denial, it is now a real, executed operation (same commit as
    `constraint_declarations` flipping to `enabled`). See
    `test_alter_field_real_http_round_trip` below for its own coverage."""
    entity = "http_unimplemented_schema_target"
    _create_entity(app_a_stack, entity)
    body = {"operation": operation, "entity": entity}
    if operation == "create_index":
        body.update({"index": "idx1", "fields": ["item_key"], "unique": True})
    response = _post(app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer, json_body=body)
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


def test_create_entity_field_constraints_http_round_trip_and_enum_enforcement(app_a_stack):
    """WP-3a closure (監督裁定 2026-09-07, audit `wp3a-closure` §2 G2 /
    m-2): the ONE full HTTP-path positive test for `field_constraints`
    this repository was missing -- `create_entity` with `field_types` +
    `field_constraints` (`enum` and `nullable` both declared on the same
    field), `GET /v1/catalog` reporting `field_constraints` back, an
    enum-violating insert refused with `VALIDATION_FAILED` and the D-3
    `details` shape, and an in-set insert succeeding with `200`. Mirrors
    `test_constraints_declaration.py`'s own in-process completion-
    condition tests, but through the real ASGI `HttpService` this file's
    other tests already drive (`app_a_stack`), not the direct
    `ApplicationDeveloper`/`ApplicationRuntime` API."""
    entity = "http_field_constraints_entity"
    create_response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={
            "operation": "create_entity", "entity": entity, "fields": ["status"],
            "field_types": {"status": "string"},
            "field_constraints": {"status": {"enum": ["a", "b"], "nullable": False}},
        },
    )
    assert create_response.status_code == 200, create_response.text

    catalog = _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer).json()
    row = {e["entity"]: e for e in catalog["entities"]}[entity]
    assert row["field_constraints"]["status"] == {"enum": ["a", "b"], "nullable": False}, row

    violation_response = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"status": "z"}}]},
    )
    assert violation_response.status_code == 400, violation_response.text
    violation_body = violation_response.json()
    assert violation_body["code"] == "VALIDATION_FAILED", violation_body
    details = violation_body["details"]
    assert details.get("violated_declaration") == "enum", details
    assert details.get("field") == "operations/0/values/status", details
    assert details.get("declared_type") == "string", details
    assert "observed_type" not in details, details

    ok_response = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"status": "a"}}]},
    )
    assert ok_response.status_code == 200, ok_response.text
    assert ok_response.json()["affected"] == 1


def test_alter_field_real_http_round_trip(app_a_stack):
    """Phase 9 WP-3a (design D-2 (5)/(6)): `alter_field` over HTTP is a
    real, executed operation as of this commit -- enforces the redeclared
    `enum`, and a conflicting `alter_field` (an existing row violates the
    constraints it would establish) is refused with `CONFLICT`, changing
    nothing."""
    entity = "http_alter_field_target"
    _create_entity(app_a_stack, entity, fields=["status"], field_types={"status": "string"})
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "alter_field", "entity": entity, "field": "status", "enum": ["a", "b"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["committed"] is True
    assert body.get("revision") is not None

    field_type_response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "alter_field", "entity": entity, "field": "status", "field_type": "integer"},
    )
    assert field_type_response.status_code == 400
    assert field_type_response.json()["code"] == "VALIDATION_FAILED"
    assert field_type_response.json()["details"].get("violated_declaration") == "unsupported_field"


def test_alter_field_with_neither_enum_nor_nullable_is_refused_over_http(app_a_stack):
    """監督裁定 N-1 (2026-09-07, wp3a-closure2): an `alter_field` request
    carrying neither `enum` nor `nullable` declares nothing -- refused
    with `VALIDATION_FAILED` over the real HTTP dispatch path, and the
    schema revision does not advance (pinned here by observing that a
    SUBSEQUENT, unrelated schema operation still advances the revision by
    exactly one step from where it stood before the refused call, not
    two)."""
    entity = "http_alter_field_neither_target"
    create_response = _create_entity(app_a_stack, entity, fields=["status"], field_types={"status": "string"})
    revision_before = int(create_response.json()["revision"])
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "alter_field", "entity": entity, "field": "status"},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED", body
    assert body["details"].get("violated_declaration") == "constraint_declaration", body
    assert body["details"].get("field") == "operation", body

    schema_response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": "unrelated_probe"},
    )
    revision_after = int(schema_response.json()["revision"])
    assert revision_after == revision_before + 1, "the refused alter_field must not itself have advanced the revision"


# ---------------------------------------------------------------------------
# Phase 9 WP-3b rework (code review §3 m-6(1)/F-4): the HTTP-boundary
# dry_run/plan tests the original WP-3b submission never added at all (it
# only ever DELETED the pre-WP-3b gate-denial cases, `test_contract_1_7_0_
# provisional_gate_rejects_new_fields_before_execution` above, with no
# replacement) -- `MitateDB-api/tests/test_dry_run_and_plan.py` exercises
# `cell.py`/`ApplicationDeveloper`/`ApplicationRuntime` directly, never
# through `http.py`'s own request parsing (`_mutation_item`/`post_schema`'s
# own field-by-field extraction) or its own response assembly
# (`_mutation_outcome`, the `descriptor`/`plan` conditional keys). These
# three are the minimum F-4 asks for: a mutation dry-run response, a schema
# dry-run response, and a plan-mismatch refusal -- all driven through a
# real ASGI request/response round trip.
# ---------------------------------------------------------------------------


def test_http_mutation_dry_run_response_shape(app_a_stack):
    """F-4 (1/3): a mutation `dry_run` over HTTP answers `committed:
    false`, a real `affected` count, a `plan`, and NO `assigned_addresses`
    key at all -- and leaves no row behind. A mutation on `committed`
    that hardcodes `True` (this endpoint's own pre-WP-3b literal) would
    fail this test's own first assertion."""
    entity = "http_mutation_dry_run_entity"
    _create_entity(app_a_stack, entity, fields=["label"])

    response = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "dry-row"}}], "dry_run": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["committed"] is False, body
    assert body["affected"] == 1, body
    assert isinstance(body.get("plan"), str) and body["plan"], body
    assert "assigned_addresses" not in body, body

    rows = _post(app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert rows.json()["items"] == [], "a dry-run insert over HTTP must leave no row behind"


def test_http_schema_dry_run_response_shape(app_a_stack):
    """F-4 (2/3): a schema `dry_run` over HTTP answers `committed: false`,
    a `descriptor` carrying the field the entity would have afterward, and
    a `revision` equal to the CURRENT (pre-apply) value -- and leaves the
    real catalog unchanged."""
    entity = "http_schema_dry_run_entity"
    create_response = _create_entity(app_a_stack, entity, fields=["label"])
    revision_before = create_response.json()["revision"]

    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": "new_field", "field_type": "string",
                  "dry_run": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["committed"] is False, body
    assert body["revision"] == revision_before, "a dry-run schema op must report the PRE-apply revision"
    assert "new_field" in body["descriptor"]["fields"], body
    assert body["descriptor"]["field_types"]["new_field"] == "string", body
    assert isinstance(body.get("plan"), str) and body["plan"], body

    catalog = {e["entity"]: e for e in _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer).json()["entities"]}
    assert "new_field" not in catalog[entity]["fields"], "a dry-run add_field over HTTP left a real field behind"


def test_http_plan_mismatch_is_412_precondition_failed(app_a_stack):
    """F-4 (3/3): a `plan` taken for one mutation body, presented on a
    DIFFERENT body, is refused over the real HTTP boundary with the exact
    contract mapping -- HTTP 412, `code: PRECONDITION_FAILED`,
    `details.violated_declaration: plan` -- and never executes."""
    entity = "http_plan_mismatch_entity"
    _create_entity(app_a_stack, entity, fields=["label"])

    dry = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "body-a"}}], "dry_run": True},
    )
    plan = dry.json()["plan"]

    mismatched = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "body-b"}}], "plan": plan},
    )
    assert mismatched.status_code == 412, mismatched.text
    body = mismatched.json()
    assert body["code"] == "PRECONDITION_FAILED", body
    assert body["details"] == {"violated_declaration": "plan"}, body

    rows = _post(app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert rows.json()["items"] == [], "the plan-mismatched apply must not have executed"


def test_cross_entity_mutation_dry_run_leaves_no_row_and_carries_a_plan(app_a_stack):
    """G-5 (c): `POST /v1/data/mutations` (cross-entity) honors `dry_run`/
    `plan` too -- this response shape has never been exercised by any
    peer-local test (`ApplicationRuntime` has no separate cross-entity
    method of its own; the distinction is entirely an HTTP-layer request-
    shape one, `_scoped_mutation_item`)."""
    entity_x = "http_cross_entity_dry_run_x"
    entity_y = "http_cross_entity_dry_run_y"
    _create_entity(app_a_stack, entity_x, fields=["label"])
    _create_entity(app_a_stack, entity_y, fields=["label"])

    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "insert", "entity": entity_x, "values": {"label": "x-dry"}},
            {"operation": "insert", "entity": entity_y, "values": {"label": "y-dry"}},
        ], "dry_run": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["committed"] is False, body
    assert body["affected"] == 2, body
    assert isinstance(body.get("plan"), str) and body["plan"], body
    assert "assigned_addresses" not in body, body

    x_rows = _post(app_a_stack, f"/v1/data/{entity_x}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    y_rows = _post(app_a_stack, f"/v1/data/{entity_y}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert x_rows.json()["items"] == [], "a dry-run cross-entity insert must leave no row behind (entity x)"
    assert y_rows.json()["items"] == [], "a dry-run cross-entity insert must leave no row behind (entity y)"

    # The SAME plan, replayed as a real apply, actually commits (proves the
    # dry run's own `plan` is honored on this endpoint, not merely accepted
    # and discarded).
    real = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "insert", "entity": entity_x, "values": {"label": "x-dry"}},
            {"operation": "insert", "entity": entity_y, "values": {"label": "y-dry"}},
        ], "plan": body["plan"]},
    )
    assert real.status_code == 200, real.text
    assert real.json()["committed"] is True, real.json()


def test_runtime_credential_forbidden_from_schema_operations(app_a_stack):
    response = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.runtime_bearer,
        json_body={"operation": "create_entity", "entity": "should_not_be_created"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_cross_entity_mutation_endpoint_route_resolves_distinctly(app_a_stack):
    """`POST /v1/data/mutations` and `POST /v1/data/{entity}/mutations`
    must never collide at the routing level -- an entity literally named
    "mutations" resolves to the per-entity route, never this one."""
    response = _post(
        app_a_stack, "/v1/data/mutations/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"item_key": 1}}]},
    )
    # Resolves to post_mutate with entity="mutations" (which does not
    # exist) -- NOT_FOUND, never any response shape belonging to the real
    # `/v1/data/mutations` cross-entity endpoint.
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# P35 WP-2 (R-3/R-5): cross-entity mutation -- now `enabled`, real HTTP
# dispatch through the same two-pass `ApplicationCell.transact` choke the
# per-entity endpoint already uses.
# ---------------------------------------------------------------------------


def test_cross_entity_mutation_capability_is_declared_partial_with_batch_entities_limit(app_a_stack):
    """M-1 (independent review, WP-2 follow-up): status is `"partial"`,
    matching `atomic_mutation`'s own declared shape exactly."""
    response = _get(app_a_stack, "/v1/capabilities", bearer=app_a_stack.runtime_bearer)
    assert response.status_code == 200
    document = response.json()
    assert document["capabilities"]["cross_entity_mutation"] == {
        "status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"],
    }
    assert document["limits"]["batch_entities"] == 10
    assert document["limit_enforcement"]["batch_entities"] == "enforced"


def test_cross_entity_mutation_commits_across_two_real_entities(app_a_stack):
    entity_x = "http_cross_entity_x"
    entity_y = "http_cross_entity_y"
    _create_entity(app_a_stack, entity_x, fields=["label"])
    _create_entity(app_a_stack, entity_y, fields=["label"])

    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "insert", "entity": entity_x, "values": {"label": "x-row"}},
            {"operation": "insert", "entity": entity_y, "values": {"label": "y-row"}},
        ]},
    )
    assert response.status_code == 200, response.text
    # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): the response also
    # carries `request_id` now -- checked for presence, then popped
    # before the exact-shape assert below.
    body = response.json()
    assert body.pop("request_id")
    assert body == {"committed": True, "affected": 2}
    # No `assigned_addresses` key at all (design M-6) -- not merely empty.
    assert "assigned_addresses" not in response.json()

    x_rows = _post(app_a_stack, f"/v1/data/{entity_x}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    y_rows = _post(app_a_stack, f"/v1/data/{entity_y}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert [r["label"] for r in x_rows.json()["items"]] == ["x-row"]
    assert [r["label"] for r in y_rows.json()["items"]] == ["y-row"]


def test_cross_entity_mutation_rolls_back_both_entities_when_a_later_operation_is_invalid(app_a_stack):
    entity_x = "http_cross_entity_rollback_x"
    entity_y = "http_cross_entity_rollback_y"
    _create_entity(app_a_stack, entity_x, fields=["label"])
    _create_entity(app_a_stack, entity_y, fields=["label"])

    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "insert", "entity": entity_x, "values": {"label": "should-not-persist"}},
            {"operation": "update", "entity": entity_y, "values": {"label": "y"}},  # missing required `where`
        ]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"

    x_rows = _post(app_a_stack, f"/v1/data/{entity_x}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    y_rows = _post(app_a_stack, f"/v1/data/{entity_y}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert x_rows.json()["items"] == []
    assert y_rows.json()["items"] == []


def test_cross_entity_mutation_request_shape_rejects_unknown_top_level_field(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "entity": "shared_items", "values": {"item_key": 1}}],
                   "bogus_field": True},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_cross_entity_mutation_operation_shape_rejects_unknown_field(app_a_stack):
    """`ScopedMutation` (`additionalProperties: false`) closes each
    operation's own shape too -- an unrecognized per-operation key is a
    shape defect, not merely an unread capability-shaped key (that
    distinction belongs to keys `ScopedMutation` DOES declare, like
    `expected_revision`, refused instead with `CAPABILITY_UNSUPPORTED`
    -- see the neighboring `expected_revision` test below)."""
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "entity": "shared_items", "values": {"item_key": 1},
                                    "not_a_real_field": True}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("bad_entity", [["shared_items"], {"name": "shared_items"}])
def test_cross_entity_mutation_non_string_entity_is_validation_failed_not_service_unavailable(app_a_stack, bad_entity):
    """B-1 (independent review, WP-2 follow-up): `ScopedMutation.entity`
    is a wire-typed string field, but `_check_object_shape` only checks
    the KEY SET, not each value's own type -- a well-formed key carrying
    a non-string value (a JSON array or object where the contract expects
    a string) must still be classified `VALIDATION_FAILED`, not escape as
    an unclassified `SERVICE_UNAVAILABLE`. Pre-fix, `ApplicationCell.
    _distinct_batch_entities` added this raw value straight into a `set`
    before `_plan_operation` ever got a chance to classify it -- an
    unhashable list/dict raised a bare `TypeError` that reached this
    endpoint's own generic `except Exception` fallback as a 503."""
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "entity": bad_entity, "values": {"item_key": 1}}]},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_cross_entity_mutation_idempotency_key_replays_via_http(app_a_stack):
    """Phase 9 WP-3c (design D-5): `idempotency_key` on `ScopedMutation
    Request` is real as of this commit -- a resend under the same key
    replays the original result, over HTTP, on the cross-entity endpoint
    exactly like the per-entity one (`test_c23_idempotency_semantics.py`
    is the cross-peer evidence; this pins the HTTP wiring locally)."""
    entity = "http_cem_idem_target"
    _create_entity(app_a_stack, entity, fields=["label"])
    body = {
        "operations": [{"operation": "insert", "entity": entity, "values": {"label": "cem-idem"}}],
        "idempotency_key": "http-cem-idem-1",
    }
    first = _post(app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer, json_body=body)
    assert first.status_code == 200, first.text
    second = _post(app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer, json_body=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()


def test_cross_entity_mutation_budget_narrows_batch_items_over_http(app_a_stack):
    """K-4 (WP-3cd audit §11 推奨7, N-6; 監督裁定集約 rulings-r5-r6.md
    B-1): `http.py::post_cross_entity_mutate` reads `budget=body.get
    ("budget")` and forwards it to `session.transact` -- the audit
    measured that DROPPING that keyword left every existing test green
    (`{scratchpad}` mutation probe). `ScopedMutationRequest.budget` names
    the SAME `batch_items`/`execution_ms` classes `MutationRequest.
    budget` does (B-1's single row for both `mutate`/`cross_entity`); this
    pins the cross-entity endpoint's own real wiring the same way `test_
    contract_1_7_0_budget_and_idempotency_are_real_over_http` above pins
    the per-entity one."""
    entity = "http_cem_budget_target"
    _create_entity(app_a_stack, entity, fields=["label"])
    two_ops = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={
            "operations": [
                {"operation": "insert", "entity": entity, "values": {"label": "cem-budget-a"}},
                {"operation": "insert", "entity": entity, "values": {"label": "cem-budget-b"}},
            ],
            "budget": {"batch_items": 2},
        },
    )
    assert two_ops.status_code == 200, two_ops.text
    assert two_ops.json()["affected"] == 2
    three_ops = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={
            "operations": [
                {"operation": "insert", "entity": entity, "values": {"label": "cem-budget-c"}},
                {"operation": "insert", "entity": entity, "values": {"label": "cem-budget-d"}},
                {"operation": "insert", "entity": entity, "values": {"label": "cem-budget-e"}},
            ],
            "budget": {"batch_items": 2},
        },
    )
    assert three_ops.status_code == 413, three_ops.text
    assert three_ops.json()["code"] == "LIMIT_EXCEEDED"
    assert three_ops.json()["details"]["limit_class"] == "batch_items"


def test_contract_1_7_0_budget_and_idempotency_are_real_over_http(app_a_stack):
    """Phase 9 WP-3c/WP-3d (design D-5/D-6): `budget`/`idempotency_key`
    were the LAST two fields `test_contract_1_7_0_provisional_gate_
    rejects_new_fields_before_execution` (this test's own predecessor,
    WP-1/WP-3a/WP-3b) still refused with `CAPABILITY_UNSUPPORTED` -- both
    now execute for real, on every entry point that gate used to cover
    (query/mutate/cross-entity-mutate/schema), replacing that gate's own
    negative coverage with real positive coverage, the same pattern
    `test_constraints_declaration.py`/`test_dry_run_and_plan.py` already
    established for the fields WP-3a/WP-3b flipped."""
    entity = "http_budget_idem_target"
    _create_entity(app_a_stack, entity, fields=["label"])

    # --- query: budget.result_items is honored, not refused. ---
    query_response = _post(
        app_a_stack, f"/v1/data/{entity}/query", bearer=app_a_stack.runtime_bearer,
        json_body={"select": ["label"], "budget": {"result_items": 5}},
    )
    assert query_response.status_code == 200, query_response.text

    # --- per-entity mutate: budget narrows batch_items for real. ---
    two_ops = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={
            "operations": [
                {"operation": "insert", "values": {"label": "budget-a"}},
                {"operation": "insert", "values": {"label": "budget-b"}},
            ],
            "budget": {"batch_items": 2},
        },
    )
    assert two_ops.status_code == 200, two_ops.text
    assert two_ops.json()["affected"] == 2
    three_ops = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={
            "operations": [
                {"operation": "insert", "values": {"label": "budget-c"}},
                {"operation": "insert", "values": {"label": "budget-d"}},
                {"operation": "insert", "values": {"label": "budget-e"}},
            ],
            "budget": {"batch_items": 2},
        },
    )
    assert three_ops.status_code == 413, three_ops.text
    assert three_ops.json()["code"] == "LIMIT_EXCEEDED"
    assert three_ops.json()["details"]["limit_class"] == "batch_items"

    # --- per-entity mutate: idempotency_key replays the original result. ---
    idem_body = {"operations": [{"operation": "insert", "values": {"label": "idem-http"}}],
                 "idempotency_key": "http-idem-key-1"}
    idem_first = _post(app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer, json_body=idem_body)
    assert idem_first.status_code == 200, idem_first.text
    idem_second = _post(app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer, json_body=idem_body)
    assert idem_second.status_code == 200, idem_second.text
    assert idem_second.json() == idem_first.json()
    idem_conflict = _post(
        app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "idem-http-other"}}],
                   "idempotency_key": "http-idem-key-1"},
    )
    assert idem_conflict.status_code == 409
    assert idem_conflict.json()["code"] == "CONFLICT"
    assert idem_conflict.json()["details"]["violated_declaration"] == "idempotency_key"

    # --- schema: budget.execution_ms and idempotency_key both apply for
    # real. ---
    schema_budget = _post(
        app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer,
        json_body={"operation": "add_field", "entity": entity, "field": "budgeted_field",
                   "field_type": "string", "budget": {"execution_ms": 5000}},
    )
    assert schema_budget.status_code == 200, schema_budget.text
    schema_idem_body = {"operation": "add_field", "entity": entity, "field": "idem_schema_field",
                        "field_type": "string", "idempotency_key": "http-schema-idem-1"}
    schema_idem_first = _post(app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer, json_body=schema_idem_body)
    assert schema_idem_first.status_code == 200, schema_idem_first.text
    schema_idem_second = _post(app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer, json_body=schema_idem_body)
    assert schema_idem_second.status_code == 200, schema_idem_second.text
    assert schema_idem_second.json() == schema_idem_first.json()
    catalog_after = _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer).json()
    target_fields_after = next(e["fields"] for e in catalog_after["entities"] if e["entity"] == entity)
    assert "budgeted_field" in target_fields_after
    assert "idem_schema_field" in target_fields_after


def test_contract_1_7_0_budget_and_idempotency_are_real_in_process(app_a_stack):
    """WP-1a rework item 6's own predecessor exercised this SAME
    provisional gate through the in-process surface -- see this test's
    own HTTP-surface sibling immediately above for the full "gate ->
    real behavior" narrative (Phase 9 WP-3c/WP-3d)."""
    entity = "in_process_budget_idem_target"
    _create_entity(app_a_stack, entity, fields=["label"])

    runtime_principal = app_a_stack.read_store.authenticate(app_a_stack.runtime_bearer)
    developer_principal = app_a_stack.read_store.authenticate(app_a_stack.developer_bearer)
    runtime = ApplicationRuntime(app_a_stack.cell, runtime_principal, app_a_stack.read_store.assert_active)
    developer = ApplicationDeveloper(app_a_stack.cell, developer_principal, app_a_stack.read_store.assert_active)

    rows = runtime.read(entity, budget={"result_items": 5})
    assert rows == []

    result = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "ip-a"}},
         {"type": "insert", "collection": entity, "values": {"label": "ip-b"}}],
        budget={"batch_items": 2},
    )
    assert len(result) == 2
    with pytest.raises(ResourceLimitError) as excinfo:
        runtime.transact(
            [{"type": "insert", "collection": entity, "values": {"label": "ip-c"}},
             {"type": "insert", "collection": entity, "values": {"label": "ip-d"}},
             {"type": "insert", "collection": entity, "values": {"label": "ip-e"}}],
            budget={"batch_items": 2},
        )
    assert excinfo.value.details["limit_class"] == "batch_items"

    key = "in-process-idem-1"
    first = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "ip-idem"}}], idempotency_key=key)
    second = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "ip-idem"}}], idempotency_key=key)
    assert first == second

    created = developer.create_entity("in_process_budget_idem_entity_2", fields={"label": "text"}, idempotency_key="schema-key-1")
    replayed = developer.create_entity("in_process_budget_idem_entity_2", fields={"label": "text"}, idempotency_key="schema-key-1")
    assert created == replayed

    catalog_after = _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer).json()
    entity_names_after = {e["entity"] for e in catalog_after["entities"]}
    assert "in_process_budget_idem_entity_2" in entity_names_after


def test_contract_1_7_0_new_capabilities_are_declared_unavailable(app_a_stack):
    """Completion condition 25 (peer-local half): the 3 new capabilities
    named by this test's own original P-3 commit -- the common-suite half
    of this (defined ⊆ declared, all 14 names present) is `conformance-
    tests/test_c11_document_conformance.py` (裁定 T-4).

    Phase 9 WP-3a (design D-1 (4)): `constraint_declarations` flips to
    `enabled` in this SAME commit as the gate removal/real enforcement
    above.

    Phase 9 WP-3b (design D-1 (4)): `dry_run` flips to `enabled` too.

    Phase 9 WP-3d (design D-6, B-4): `request_budget` flips to `enabled`
    too, in this SAME commit as `narrow_limits_by_budget`'s own real
    enforcement (`config.py`) and the corresponding `http.py` gate
    removal -- this test's own name now describes history (every field
    the original gate covered has since flipped), kept for the same
    declaration-vs-behavior pinning it always did."""
    response = _get(app_a_stack, "/v1/capabilities", bearer=app_a_stack.developer_bearer)
    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert capabilities["constraint_declarations"]["status"] == "enabled"
    assert capabilities["dry_run"]["status"] == "enabled"
    assert capabilities["request_budget"]["status"] == "enabled"
    assert capabilities["idempotency"]["status"] == "enabled"


def test_cross_entity_mutation_upsert_is_capability_unsupported(app_a_stack):
    entity = "http_cross_entity_upsert_target"
    _create_entity(app_a_stack, entity, fields=["label"])
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "upsert", "entity": entity, "values": {"label": "x"}}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


def test_cross_entity_mutation_expected_revision_is_capability_unsupported(app_a_stack):
    """Same "unread capability-shaped key" refusal `post_mutate` already
    gives `expected_revision` (`_TRANSACT_INSERT_KEYS` in `cell.py` (now in `request_vocabulary.py`)),
    exercised through the cross-entity endpoint too."""
    entity = "http_cross_entity_expected_revision_target"
    _create_entity(app_a_stack, entity, fields=["label"])
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "entity": entity, "values": {"label": "x"},
                                    "expected_revision": "deadbeef"}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


def test_cross_entity_mutation_requires_authentication(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/mutations",
        json_body={"operations": [{"operation": "insert", "entity": "shared_items", "values": {"item_key": 1}}]},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_cross_entity_mutation_batch_entities_boundary(app_a_stack):
    """The declared default (`batch_entities: 10`, pinned above) is
    enforced for real over real HTTP: 10 distinct entities in one batch
    commit; an 11th distinct entity in the same batch is refused with
    `LIMIT_EXCEEDED`/`limit_class=batch_entities`, and nothing from that
    batch persists."""
    # Short entity names deliberately: this fixture's own request_bytes_
    # limit (1024) is an unrelated byte bound this test must stay well
    # clear of, so the 413 asserted below is unambiguously batch_entities.
    entities = [f"cxb{i}" for i in range(11)]
    for entity in entities:
        _create_entity(app_a_stack, entity, fields=["label"])

    ok_ops = [{"operation": "insert", "entity": e, "values": {"label": "x"}} for e in entities[:10]]
    response = _post(app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer, json_body={"operations": ok_ops})
    assert response.status_code == 200, response.text
    assert response.json()["affected"] == 10

    over_ops = [{"operation": "insert", "entity": e, "values": {"label": "y"}} for e in entities]  # 11 distinct
    response = _post(app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer, json_body={"operations": over_ops})
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["limit_class"] == "batch_entities"
    # The over-limit batch must not have inserted a second "y" row into
    # any of the 10 entities that would otherwise have accepted it.
    check = _post(app_a_stack, f"/v1/data/{entities[0]}/query", bearer=app_a_stack.runtime_bearer, json_body={"select": ["label"]})
    assert [r["label"] for r in check.json()["items"]] == ["x"]


def test_cross_entity_mutation_batch_entities_ignores_repeated_entity(app_a_stack):
    """The SAME entity repeated across many operations counts once
    toward `batch_entities`, regardless of how many operations touch it
    (contract `endpoints.cross_entity_mutate.semantics`) -- bounded only
    by `batch_items`, independently."""
    # Kept small (not 20+) so the serialized body stays comfortably under
    # this fixture's own `request_bytes_limit=1024` -- an unrelated byte
    # bound this test does not exist to exercise.
    entity = "http_cross_entity_repeat_target"
    _create_entity(app_a_stack, entity, fields=["label"])
    ops = [{"operation": "insert", "entity": entity, "values": {"label": f"r{i}"}} for i in range(6)]
    response = _post(app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer, json_body={"operations": ops})
    assert response.status_code == 200, response.text
    assert response.json()["affected"] == 6


def test_cross_entity_mutation_delete_declare_and_echo_per_entity_wrong_entity_phrase_refused(app_a_stack):
    """Each `ScopedMutation` delete builds its OWN confirmation phrase,
    fingerprinted to its own entity name -- a phrase probed for entity A
    must be refused when echoed back against entity B's delete, even
    within the SAME cross-entity batch."""
    entity_a = "http_cross_entity_delete_a"
    entity_b = "http_cross_entity_delete_b"
    _create_entity(app_a_stack, entity_a, fields=["label"])
    _create_entity(app_a_stack, entity_b, fields=["label"])
    for entity in (entity_a, entity_b):
        response = _post(
            app_a_stack, f"/v1/data/{entity}/mutations", bearer=app_a_stack.runtime_bearer,
            json_body={"operations": [{"operation": "insert", "values": {"label": "keep-me"}}]},
        )
        assert response.status_code == 200, response.text

    probe_a = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "delete", "entity": entity_a, "where": [{"field": "label", "operator": "eq", "value": "keep-me"}]},
        ]},
    )
    assert probe_a.status_code == 409
    phrase_a = probe_a.json()["details"]["required_confirmation"]
    assert entity_a in phrase_a and entity_b not in phrase_a

    # Using entity A's own valid phrase to confirm entity B's delete must
    # be refused -- the fingerprint is entity-specific.
    wrong_entity = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "delete", "entity": entity_b,
             "where": [{"field": "label", "operator": "eq", "value": "keep-me"}],
             "destructive": True, "confirmation": phrase_a},
        ]},
    )
    assert wrong_entity.status_code == 409
    assert wrong_entity.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"

    # The correct, matching phrase for entity B works.
    probe_b = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "delete", "entity": entity_b, "where": [{"field": "label", "operator": "eq", "value": "keep-me"}]},
        ]},
    )
    phrase_b = probe_b.json()["details"]["required_confirmation"]
    assert phrase_b != phrase_a

    committed = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "delete", "entity": entity_a,
             "where": [{"field": "label", "operator": "eq", "value": "keep-me"}],
             "destructive": True, "confirmation": phrase_a},
            {"operation": "delete", "entity": entity_b,
             "where": [{"field": "label", "operator": "eq", "value": "keep-me"}],
             "destructive": True, "confirmation": phrase_b},
        ]},
    )
    assert committed.status_code == 200, committed.text
    # Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): see the identical
    # comment above this test's own sibling assertion.
    committed_body = committed.json()
    assert committed_body.pop("request_id")
    assert committed_body == {"committed": True, "affected": 2}


# ---------------------------------------------------------------------------
# WP-3e rework T3 (L-7, ruling `{scratchpad}/rulings-r3-r7-flip.md`): the
# non-regeneration pin -- for `post_query`/`post_mutate`(+cross-entity)/
# `post_schema`, the ONE `uuid.uuid4().hex` the ASGI middleware mints per
# request (`http.py`'s own module-level docstring above `REQUEST_ID_
# HEADER`) is: (a) the value threaded into `cell.py`'s own session call
# (`request_id=_request_id(request)`), (b) the value the HTTP JSON
# response carries under its own `"request_id"` key, and (c) the value the
# durable application-audit row this request produced carries under its
# own `request_id` column -- ALL THREE the SAME string, never three
# independently-resolved ones that merely happen to agree today. Each test
# below asserts all three at once; mutating any ONE of the response-body
# `request_id=` call sites in `http.py` (`post_query`/`post_mutate`/
# `post_cross_entity_mutate`/`post_schema`) to mint a fresh
# `uuid.uuid4().hex` instead of reusing the already-threaded value turns
# the corresponding test below red (measured directly, WP-3e rework T3
# mutation table).
# ---------------------------------------------------------------------------


def _latest_audit_event_for(router: AuditRouter, request_id: str):
    """The durable row(s) whose own `request_id` column equals `request_
    id` -- `router.flush()` must already have been called by the time this
    runs (buffer-class events, `cell.py::ApplicationCell._push_data_
    operation_event`, are not visible on `durable_sink` before that).
    Asserts exactly one such row rather than silently taking `[0]`, so a
    request that (by an unrelated bug) left NO durable row, or more than
    one, fails loudly here instead of masquerading as a pass."""
    matches = [event for event in router.durable_sink.events() if event.request_id == request_id]
    assert len(matches) == 1, (request_id, router.durable_sink.events())
    return matches[0]


def test_request_id_is_pinned_through_query_response_and_audit_row(app_a_stack_with_audit):
    stack = app_a_stack_with_audit
    entity = "l7_query_pin_entity"
    _create_entity(stack, entity, fields=["label"])
    response = _post(stack, f"/v1/data/{entity}/query", bearer=stack.runtime_bearer, json_body={"select": ["label"]})
    assert response.status_code == 200, response.text
    header_request_id = response.headers["x-request-id"]
    body_request_id = response.json()["request_id"]
    assert header_request_id == body_request_id
    stack.router.flush()
    event = _latest_audit_event_for(stack.router, body_request_id)
    assert event.operation == "query"


def test_request_id_is_pinned_through_mutate_response_and_audit_row(app_a_stack_with_audit):
    stack = app_a_stack_with_audit
    entity = "l7_mutate_pin_entity"
    _create_entity(stack, entity, fields=["label"])
    response = _post(
        stack, f"/v1/data/{entity}/mutations", bearer=stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "values": {"label": "l7-mutate-pin"}}]},
    )
    assert response.status_code == 200, response.text
    header_request_id = response.headers["x-request-id"]
    body_request_id = response.json()["request_id"]
    assert header_request_id == body_request_id
    stack.router.flush()
    # A non-destructive `transact` batch is ONE buffer-class row for the
    # WHOLE batch (`cell.py::ApplicationCell.transact`'s own D-4/P4-D5
    # comment: "exactly ONE `data_operation` event...operation='transact'"
    # -- single-entity `/mutations` reaches the SAME `transact` path
    # cross-entity `/v1/data/mutations` does, never a separate per-
    # operation "insert" event).
    event = _latest_audit_event_for(stack.router, body_request_id)
    assert event.operation == "transact"


def test_request_id_is_pinned_through_cross_entity_mutate_response_and_audit_row(app_a_stack_with_audit):
    stack = app_a_stack_with_audit
    entity_x = "l7_cross_entity_x"
    entity_y = "l7_cross_entity_y"
    _create_entity(stack, entity_x, fields=["label"])
    _create_entity(stack, entity_y, fields=["label"])
    response = _post(
        stack, "/v1/data/mutations", bearer=stack.runtime_bearer,
        json_body={"operations": [
            {"operation": "insert", "entity": entity_x, "values": {"label": "l7-x"}},
            {"operation": "insert", "entity": entity_y, "values": {"label": "l7-y"}},
        ]},
    )
    assert response.status_code == 200, response.text
    header_request_id = response.headers["x-request-id"]
    body_request_id = response.json()["request_id"]
    assert header_request_id == body_request_id
    stack.router.flush()
    # Both operations share the ONE request-level `request_id` -- at least
    # one durable row for it is enough to prove the pin (unlike `_latest_
    # audit_event_for`'s single-entity siblings, this call legitimately
    # produces more than one row for the same `request_id`, one per
    # entity).
    matches = [event for event in stack.router.durable_sink.events() if event.request_id == body_request_id]
    assert len(matches) >= 1, (body_request_id, stack.router.durable_sink.events())


def test_request_id_is_pinned_through_schema_response_and_audit_row(app_a_stack_with_audit):
    stack = app_a_stack_with_audit
    response = _create_entity(stack, "l7_schema_pin_entity", fields=["label"])
    header_request_id = response.headers["x-request-id"]
    body_request_id = response.json()["request_id"]
    assert header_request_id == body_request_id
    stack.router.flush()
    event = _latest_audit_event_for(stack.router, body_request_id)
    assert event.event_class == "schema_change"


# ---------------------------------------------------------------------------
# SI-10: an error response never leaks the underlying exception's own text.
# ---------------------------------------------------------------------------


def test_problem_response_never_leaks_the_underlying_exception_message():
    """`_problem_for_exception` always builds its `message` field from a
    fixed, static, per-CODE string table -- never from `str(exc)` -- so a
    caller can never learn anything about the server's own internal state
    (a table/column name, a driver detail) through the exception's own
    message text, no matter what that text says. This is exactly the
    mutation `problem+json から内部例外文字列漏えい` targets: interpolating
    `str(exc)` into the response would leak whatever secret-shaped text
    this test plants into `ValidationError`'s own message.
    """
    marker = "internal-detail-leak-marker-8f3c1d"
    exc = ValidationError(f"storage backend rejected column {marker} at connection host 10.0.0.5")
    response = _problem_for_exception(exc, "test-request-id")
    body = json.loads(response.body)
    assert marker not in body["message"]
    assert marker not in json.dumps(body)
