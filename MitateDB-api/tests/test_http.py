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

import json

import httpx
import pytest

from mitatedb_api.auth import Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import ValidationError
from mitatedb_api.http import PROBLEM_CONTENT_TYPE, HttpService, _problem_for_exception, create_app

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
    cell = ApplicationCell(app_a.app_id, backend=backend)

    def _cell_factory(application_id: str) -> ApplicationCell:
        assert application_id == app_a.app_id
        return cell

    service = HttpService(read_store, _cell_factory)
    app = create_app(service, request_bytes_limit=1024)

    runtime_id, runtime_secret = write_store.issue(app_a.app_id, Role.RUNTIME)
    developer_id, developer_secret = write_store.issue(app_a.app_id, Role.DEVELOPER)

    import types
    stack = types.SimpleNamespace(
        app=app,
        app_id=app_a.app_id,
        runtime_bearer=f"{runtime_id}.{runtime_secret}",
        developer_bearer=f"{developer_id}.{developer_secret}",
        write_store=write_store,
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
# Authentication: the four fail-closed categories.
# ---------------------------------------------------------------------------


def test_missing_authorization_header_is_auth_required(app_a_stack):
    response = _get(app_a_stack, "/v1/capabilities")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert response.headers["content-type"].split(";")[0].strip() == PROBLEM_CONTENT_TYPE


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

    service = HttpService(unreachable, _cell_factory)
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
    assert document["contract_version"] == "1.2.0"
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


def _create_entity(stack, entity, fields=None):
    body = {"operation": "create_entity", "entity": entity}
    if fields is not None:
        body["fields"] = fields
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
    assert json.loads(items[0]["payload_obj"]) == nested_object
    assert json.loads(items[0]["payload_arr"]) == nested_array


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


def test_page_cursor_is_deterministically_rejected(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/shared_items/query", bearer=app_a_stack.runtime_bearer,
        json_body={"select": ["item_key"], "page": {"cursor": "opaque-cursor-value"}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


def test_nul_value_is_validation_failed(app_a_stack):
    entity = "http_nul_entity"
    _create_entity(app_a_stack, entity, fields=["label"])
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
        ("GET", "/v1/catalog", None),
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


@pytest.mark.parametrize("operation", ["alter_field", "create_index", "drop_index", "drop_entity"])
def test_unimplemented_schema_operations_are_present_denials(app_a_stack, operation):
    entity = "http_unimplemented_schema_target"
    _create_entity(app_a_stack, entity)
    body = {"operation": operation, "entity": entity}
    if operation == "create_index":
        body.update({"index": "idx1", "fields": ["item_key"], "unique": True})
    response = _post(app_a_stack, "/v1/schema/operations", bearer=app_a_stack.developer_bearer, json_body=body)
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


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
    assert response.json() == {"committed": True, "affected": 2}
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


def test_cross_entity_mutation_idempotency_key_is_capability_unsupported(app_a_stack):
    response = _post(
        app_a_stack, "/v1/data/mutations", bearer=app_a_stack.runtime_bearer,
        json_body={"operations": [{"operation": "insert", "entity": "shared_items", "values": {"item_key": 1}}],
                   "idempotency_key": "abc123"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


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
    gives `expected_revision` (`_TRANSACT_INSERT_KEYS` in `cell.py`),
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
    assert committed.json() == {"committed": True, "affected": 2}


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
