"""Tests for the ASGI HTTP boundary in `r2db_api.http` (D-2).

Uses httpx against the ASGI app in-process (`httpx.ASGITransport`) -- no
network listener, no port binding. `anyio_mode = "auto"` (see pyproject.toml)
lets plain `async def test_*` functions run without a per-test marker.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

import httpx
import pytest

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.http import create_app
from r2db_api.limits import ResourceLimits

BASE_URL = "http://r2db.example.invalid"

# Explicit marker (rather than relying solely on the `anyio_mode = "auto"`
# setting in this package's pyproject.toml) so these tests also run
# correctly under the repo-root pytest invocation, whose own
# `[tool.pytest.ini_options]` in the top-level pyproject.toml is what
# actually governs a `pytest` run from the repository root.
pytestmark = pytest.mark.anyio


def _build_service(**limit_overrides):
    credentials = CredentialStore(pepper="http-test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("cred-b", "app-b", "runtime", "secret-b", work=work)
    limits = ResourceLimits(**limit_overrides) if limit_overrides else ResourceLimits()
    service = DataService(credentials, limits=limits)
    control = ControlAuthority(service)
    # Contract 1.1.0 (CCR-13): `id` is server-assigned, so seed fixtures no
    # longer supply it -- app-a's and app-b's `notes` are separate cells
    # with independent counters, so both seeded rows get `id == 1`.
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    control.register_application("app-b", entities={"notes": [{"body": "b"}]})
    return service, control


def _auth(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


@asynccontextmanager
async def _client(service):
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


@pytest.fixture
def service():
    service, _control = _build_service()
    return service


@pytest.fixture
async def client(service):
    async with _client(service) as c:
        yield c


# --------------------------------------------------------------------------
# SI-08: request byte bound is enforced before parsing.
# --------------------------------------------------------------------------


async def test_honest_oversized_body_is_rejected_with_413_before_parsing():
    service, _control = _build_service(request_bytes=200)
    async with _client(service) as client:
        response = await client.post(
            "/v1/data/notes/query",
            headers=_auth("secret-a"),
            json={"select": ["id"], "where": [{"field": "id", "operator": "eq", "value": "x" * 5000}]},
        )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["resource"] == "request_bytes"
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


async def test_declared_content_length_smaller_than_actual_body_is_still_bounded():
    """A lying/short Content-Length header must not let an oversized body through.

    Drives the ASGI app directly with a hand-built scope/receive so the
    declared Content-Length header (5 bytes) can disagree with the real
    accumulated body (60 bytes) -- something httpx's own client normalizes
    away if asked to compute the header itself.
    """
    service, _control = _build_service(request_bytes=50)
    app = create_app(service)

    chunks = [b"a" * 30, b"b" * 30]  # 60 real bytes > the 50-byte bound
    state = {"index": 0}

    async def receive():
        index = state["index"]
        if index >= len(chunks):
            return {"type": "http.disconnect"}
        state["index"] += 1
        more_body = state["index"] < len(chunks)
        return {"type": "http.request", "body": chunks[index], "more_body": more_body}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/data/notes/mutations",
        "raw_path": b"/v1/data/notes/mutations",
        "query_string": b"",
        "headers": [
            (b"authorization", b"Bearer secret-a"),
            (b"content-type", b"application/json"),
            (b"content-length", b"5"),  # lies: real body below is 60 bytes
        ],
        "server": ("r2db.example.invalid", 443),
        "client": ("198.51.100.10", 12345),
        "scheme": "https",
        "http_version": "1.1",
    }

    await app(scope, receive, send)

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, "exactly one response must be sent, never a double response"
    assert starts[0]["status"] == 413
    headers = dict(starts[0]["headers"])
    assert headers[b"content-type"].startswith(b"application/problem+json")
    body = b"".join(m["body"] for m in sent if m["type"] == "http.response.body")
    problem = json.loads(body)
    assert problem["code"] == "LIMIT_EXCEEDED"
    assert problem["request_id"]
    assert headers[b"x-request-id"].decode() == problem["request_id"]


# --------------------------------------------------------------------------
# SI-06: scope is server-bound; body content cannot switch or elevate it.
# --------------------------------------------------------------------------


async def test_body_scope_fields_are_rejected_outright_and_have_no_effect(client):
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "application_id": "app-b"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"

    for field, value in (("role", "developer"), ("database", "app-b"), ("schema", "app-b")):
        response = await client.post(
            "/v1/data/notes/mutations",
            headers=_auth("secret-a"),
            json={"operations": [{"operation": "insert", "values": {"id": 42}}], field: value},
        )
        assert response.status_code == 400, field
        assert response.json()["code"] == "VALIDATION_FAILED", field

    # Prove scope really is server-bound: a syntactically valid request from
    # app-a's credential only ever sees app-a's row.
    ok = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"]})
    assert ok.status_code == 200
    assert ok.json()["items"] == [{"id": 1}]


async def test_cross_application_isolation_over_http(client):
    resp_a = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"]})
    resp_b = await client.post("/v1/data/notes/query", headers=_auth("secret-b"), json={"select": ["id"]})
    assert resp_a.json()["items"] == [{"id": 1}]
    # app-b's `notes` is a separate cell with its own independent id
    # counter (CCR-13, R-1), so its one seeded row is also id 1 -- this
    # still proves isolation (each credential only ever sees its own
    # application's row), just not via distinct id values anymore.
    assert resp_b.json()["items"] == [{"id": 1}]


# --------------------------------------------------------------------------
# SI-10: safe errors, including uncaught exceptions.
# --------------------------------------------------------------------------


async def test_uncaught_exception_becomes_safe_generic_problem(monkeypatch):
    service, _control = _build_service()
    secret_marker = "internal-db-password-should-never-leak-9f3c"

    def boom(*_args, **_kwargs):
        raise RuntimeError(f"connection string leaked: {secret_marker}")

    monkeypatch.setattr(service, "capabilities", boom)
    async with _client(service) as client:
        response = await client.get("/v1/capabilities", headers=_auth("secret-a"))

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert secret_marker not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert body["request_id"]


async def test_malformed_json_body_is_validation_failed(client):
    response = await client.post(
        "/v1/data/notes/query",
        headers={**_auth("secret-a"), "content-type": "application/json"},
        content=b"{not-valid-json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_unknown_route_and_method_not_allowed_are_safe_problem_json(client):
    response = await client.get("/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "NOT_FOUND"

    response = await client.post("/v1/capabilities")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")


# --------------------------------------------------------------------------
# request_id correlation.
# --------------------------------------------------------------------------


async def test_request_id_present_on_header_and_correlates_with_problem_body(client):
    denied = await client.get("/v1/capabilities")
    header_id = denied.headers.get("x-request-id")
    assert header_id
    assert denied.json()["request_id"] == header_id

    ok = await client.get("/v1/capabilities", headers=_auth("secret-a"))
    assert ok.status_code == 200
    ok_header_id = ok.headers.get("x-request-id")
    assert ok_header_id
    assert ok_header_id != header_id


async def test_audit_events_from_one_request_share_its_request_id():
    """A single HTTP request authenticates and then performs a data
    operation, each of which emits its own audit event (`DataService.
    authenticate` and `DataService.query`). Both must carry the same
    `request_id` as each other and as the response's `X-Request-Id`,
    so an investigator can correlate every event produced by one request.
    """
    service, control = _build_service()
    async with _client(service) as client:
        response = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"]})
    assert response.status_code == 200
    header_id = response.headers["x-request-id"]

    events = control.audit_events()
    correlated = [event for event in events if event.get("operation") in {"authenticate", "query"}]
    assert len(correlated) >= 2
    assert {event["request_id"] for event in correlated} == {header_id}


# --------------------------------------------------------------------------
# Packaged contract copy (Task 3): must never silently drift from
# `spec/data-service-api.v1.json`, the common repository's single source of
# truth. `r2db_api.http` loads the packaged copy so the distribution is
# self-contained off the repository checkout; this test is what prevents
# that copy from going stale.
# --------------------------------------------------------------------------


def test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth():
    packaged = resources.files("r2db_api.contract").joinpath("data-service-api.v1.json").read_bytes()
    source_of_truth = (Path(__file__).parents[2] / "spec" / "data-service-api.v1.json").read_bytes()
    assert packaged == source_of_truth


# --------------------------------------------------------------------------
# Auth failures.
# --------------------------------------------------------------------------


async def test_missing_credential_is_auth_required(client):
    response = await client.get("/v1/capabilities")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_invalid_credential_is_auth_invalid(client):
    response = await client.get("/v1/capabilities", headers=_auth("not-a-real-secret"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


async def test_revoked_credential_fails_closed():
    service, control = _build_service()
    control.set_credential_state("cred-a", revoked=True)
    async with _client(service) as client:
        response = await client.get("/v1/capabilities", headers=_auth("secret-a"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REVOKED"


async def test_disabled_application_fails_closed():
    service, control = _build_service()
    control.set_application_enabled("app-a", enabled=False)
    async with _client(service) as client:
        response = await client.get("/v1/capabilities", headers=_auth("secret-a"))
    assert response.status_code == 403
    assert response.json()["code"] == "APPLICATION_DISABLED"


# --------------------------------------------------------------------------
# capabilities
# --------------------------------------------------------------------------


async def test_capabilities_document_matches_contract_shape(client):
    response = await client.get("/v1/capabilities", headers=_auth("secret-a"))
    assert response.status_code == 200
    body = response.json()
    for key in ("contract_version", "capabilities", "limits", "limit_enforcement"):
        assert key in body
    assert response.headers["x-request-id"]


# --------------------------------------------------------------------------
# query
# --------------------------------------------------------------------------


async def test_query_happy_path(client):
    response = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [{"id": 1}]
    assert body["next_page"] is None
    # CCR-13 WP-5b: `revisions` is index-aligned with `items` -- a fixed
    # UUID string cannot be asserted by value, so length/type stand in.
    assert len(body["revisions"]) == 1
    assert isinstance(body["revisions"][0], str) and body["revisions"][0]


async def test_query_page_size_is_forwarded(client):
    response = await client.post(
        "/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"], "page": {"size": 1}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [{"id": 1}]
    assert body["next_page"] is None


async def test_query_page_size_over_the_contract_maximum_is_validation_failed(client):
    """WP-4 review minor-1: `Page.size` is bounded at 1000 by the contract
    itself (`spec/data-service-api.v1.json`), independent of whatever
    `ResourceLimits.result_items` a deployment happens to configure."""
    response = await client.post(
        "/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"], "page": {"size": 1001}}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_query_order_by_sorts_ascending_and_descending(client):
    """CCR-13 WP-4: `order_by` is delegated, not rejected, and the HTTP
    response reflects the real sort order."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}, {"operation": "insert", "values": {"body": "m"}}]},
    )
    assert response.status_code == 200

    ascending = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["body"], "order_by": [{"field": "body", "direction": "asc"}]},
    )
    assert ascending.status_code == 200
    ascending_body = ascending.json()
    assert ascending_body["items"] == [{"body": "a"}, {"body": "m"}, {"body": "z"}]
    assert ascending_body["next_page"] is None
    assert len(ascending_body["revisions"]) == 3

    descending = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["body"], "order_by": [{"field": "body", "direction": "desc"}]},
    )
    assert descending.status_code == 200
    descending_body = descending.json()
    assert descending_body["items"] == [{"body": "z"}, {"body": "m"}, {"body": "a"}]
    assert descending_body["next_page"] is None


async def test_query_order_by_multiple_clauses(client):
    """Multiple `order_by` clauses -- the second breaks ties left by the
    first, exactly like a real multi-column ORDER BY."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "dup"}}, {"operation": "insert", "values": {"body": "dup"}}]},
    )
    assert response.status_code == 200
    # Seeded row: id=1, body="a". Then id=2/3, body="dup"/"dup".
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id", "body"], "order_by": [{"field": "body", "direction": "asc"}, {"field": "id", "direction": "desc"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [{"id": 1, "body": "a"}, {"id": 3, "body": "dup"}, {"id": 2, "body": "dup"}]
    assert body["next_page"] is None


async def test_query_order_by_unknown_field_is_not_found(client):
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "order_by": [{"field": "ghost", "direction": "asc"}]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_query_cursor_pagination_pages_through_results_and_terminates(client):
    """CCR-13 WP-4: `page.cursor` is delegated, not rejected -- pages
    through a real multi-page result set and terminates with `next_page:
    null` on the last page."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": f"p{n}"}} for n in range(2, 6)]},
    )
    assert response.status_code == 200
    # 5 rows total (seeded "a" + 4 inserted), id 1..5.

    seen_ids: list[int] = []
    cursor = None
    for _ in range(10):  # bounded loop -- a real termination bug must not hang the test
        body: dict = {"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 2}}
        if cursor is not None:
            body["page"]["cursor"] = cursor
        response = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json=body)
        assert response.status_code == 200
        payload = response.json()
        seen_ids.extend(item["id"] for item in payload["items"])
        cursor = payload["next_page"]
        if cursor is None:
            break
    else:
        pytest.fail("pagination never terminated (next_page stayed non-null)")
    assert seen_ids == [1, 2, 3, 4, 5]


async def test_query_cursor_tampering_is_validation_failed(client):
    seeded = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert seeded.status_code == 200
    first = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1}},
    )
    cursor = first.json()["next_page"]
    assert cursor  # the just-inserted second row makes a next page exist
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1, "cursor": tampered}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_query_cursor_minted_for_a_different_entity_is_rejected(client):
    """A cursor's opaque shape hash binds the entity it was minted against
    (`r2db_api.structured._shape_hash`) -- reusing one against a different
    entity must fail loudly, never silently page through the wrong
    entity's rows."""
    developer = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "create_entity", "entity": "widgets", "fields": ["name"]},
    )
    assert developer.status_code == 200
    seeded = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert seeded.status_code == 200

    minted = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1}},
    )
    cursor = minted.json()["next_page"]
    assert cursor

    response = await client.post(
        "/v1/data/widgets/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1, "cursor": cursor}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_query_matches_filter_executes(client):
    """CCR-13 WP-5b: `matches` is declared `enabled` (`structured_query.
    operators`) and reachable end-to-end over HTTP."""
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("secret-a"),
        json={"select": ["id"], "where": [{"field": "body", "operator": "matches", "value": "a%"}]},
    )
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": 1}]


async def test_entity_identifier_validation_flows_through_http(client):
    response = await client.post(
        "/v1/data/bad-entity!/query", headers=_auth("secret-a"), json={"select": ["id"]}
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"IDENTIFIER_INVALID", "NOT_FOUND"}


# --------------------------------------------------------------------------
# mutate
# --------------------------------------------------------------------------


async def test_mutate_happy_path_commits(client):
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert response.status_code == 200
    # CCR-13 WP-5b: `assigned_addresses` now reaches the response -- the
    # seeded row is id=1, so this insert resolves to id=2.
    assert response.json() == {"committed": True, "affected": 1, "assigned_addresses": [{"address": {"id": 2}}]}


async def test_mutate_assigned_addresses_are_insert_only_in_operation_order(client):
    """A batch mixing insert/update: only the inserts contribute an
    element, in operation order -- an update contributes nothing."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={
            "operations": [
                {"operation": "insert", "values": {"body": "first"}},
                {"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "renamed"}},
                {"operation": "insert", "values": {"body": "second"}},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["affected"] == 3
    assert body["assigned_addresses"] == [{"address": {"id": 2}}, {"address": {"id": 3}}]


async def test_mutate_idempotency_key_and_best_effort_are_capability_unsupported(client):
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"id": 5}}], "idempotency_key": "abc"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"

    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"id": 6}}], "transaction": "best_effort"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


async def test_mutate_update_and_delete_where_matches_executes(client):
    """CCR-13 WP-5b: `update`/`delete`'s own `operation.where` accepts
    `matches` too, not only `query()`'s predicates -- executes end-to-end
    over HTTP now that `matches` is declared `enabled`."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "body", "operator": "matches", "value": "a%"}], "values": {"body": "renamed"}}]},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1

    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={
            "operations": [
                {"operation": "delete", "where": [{"field": "body", "operator": "matches", "value": "rename%"}], "destructive": True, "confirmation": "DELETE"}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1
    query_response = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["body"]})
    assert query_response.json()["items"] == []


async def test_mutate_invalid_transaction_value_is_validation_failed(client):
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "insert", "values": {"id": 7}}], "transaction": "nonsense"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------
# CCR-13 WP-5b: the provisional `DataService` gate (design
# R2DB_CCR13_STORAGE_V1.md §3) is removed and `capabilities()` catches up
# in the same commit -- these are the positive-side HTTP-level tests for
# the vocabulary the gate used to refuse, replacing the old gate-regression
# tests (which asserted the opposite outcome).
# --------------------------------------------------------------------------


async def test_http_mutate_expected_revision_executes(client):
    query_response = await client.post("/v1/data/notes/query", headers=_auth("secret-a"), json={"select": ["id"]})
    revision = query_response.json()["revisions"][0]
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "z"}, "expected_revision": revision}]},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1
    # A stale revision now fails as a real precondition mismatch, not a
    # capability refusal.
    stale = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "y"}, "expected_revision": revision}]},
    )
    assert stale.status_code == 412
    assert stale.json()["code"] == "PRECONDITION_FAILED"


async def test_http_mutate_upsert_without_a_declared_unique_key_is_capability_unsupported(client):
    """Upsert's per-entity precondition (a declared uniqueness key) is a
    real, entity-scoped condition, unaffected by the gate's removal --
    `notes` here declares no unique key at all."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "upsert", "values": {"body": "z"}}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


async def test_http_mutate_upsert_with_a_declared_unique_key_executes(client):
    developer_response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "tag"},
    )
    assert developer_response.status_code == 200
    index_response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_tag", "fields": ["tag"], "unique": True},
    )
    assert index_response.status_code == 200
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "upsert", "values": {"tag": "z"}}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["affected"] == 1
    assert body["assigned_addresses"] == [{"address": {"id": 2}}]


async def test_http_schema_create_index_and_drop_index_execute(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"], "unique": True},
    )
    assert response.status_code == 200
    catalog_response = await client.get("/v1/catalog", headers=_auth("secret-a"))
    assert catalog_response.json()["entities"][0]["unique_keys"] == [{"name": "by_body", "fields": ["body"]}]

    without_confirmation = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "drop_index", "entity": "notes", "index": "by_body"},
    )
    assert without_confirmation.status_code == 409
    assert without_confirmation.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"

    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "drop_index", "entity": "notes", "index": "by_body", "destructive": True, "confirmation": "DROP_INDEX"},
    )
    assert response.status_code == 200
    catalog_response = await client.get("/v1/catalog", headers=_auth("secret-a"))
    assert catalog_response.json()["entities"][0]["unique_keys"] == []


async def test_http_schema_create_index_still_requires_developer_authority(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_http_schema_field_type_executes(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "n", "field_type": "integer"},
    )
    assert response.status_code == 200
    mutate_response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": 5}}]},
    )
    assert mutate_response.status_code == 200
    bad_type = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": "not-an-int"}}]},
    )
    assert bad_type.status_code == 400
    assert bad_type.json()["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


async def test_schema_endpoint_requires_developer_authority(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("secret-a"),
        json={"operation": "create_entity", "entity": "widgets"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "create_entity", "entity": "widgets"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["committed"] is True
    assert isinstance(body["revision"], str)


async def test_destructive_schema_operation_requires_confirmation(client):
    await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "create_entity", "entity": "temp_entity"},
    )
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-secret-a"),
        json={"operation": "drop_entity", "entity": "temp_entity"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


async def test_catalog_matches_contract_shape_and_application_scope(client):
    response = await client.get("/v1/catalog", headers=_auth("secret-a"))
    assert response.status_code == 200
    body = response.json()
    # Contract 1.1.0 (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md §2/R-1):
    # `row_addressability` is declared `enabled` (WP-5b), so the full
    # `EntityDescriptor` shape reaches the response with no narrowing.
    assert body == {
        "application_scope": "app-a",
        "entities": [
            {"entity": "notes", "fields": ["body", "id"], "mutation_class": "mutable", "address_fields": ["id"], "address_reuse": "never", "unique_keys": []}
        ],
    }
    assert response.headers["x-request-id"]

    unauth = await client.get("/v1/catalog")
    assert unauth.status_code == 401
    assert unauth.json()["code"] == "AUTH_REQUIRED"


async def test_catalog_denied_for_revoked_credential_exactly_as_query():
    service, control = _build_service()
    control.set_credential_state("cred-a", revoked=True)
    async with _client(service) as client:
        response = await client.get("/v1/catalog", headers=_auth("secret-a"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REVOKED"


# --------------------------------------------------------------------------
# audit_query: unimplemented capability must say so honestly.
# --------------------------------------------------------------------------


async def test_audit_query_unreachable_with_any_application_credential(client):
    for secret in ("secret-a", "dev-secret-a"):
        response = await client.post("/v1/audit/query", headers=_auth(secret), json={})
        assert response.status_code == 400, secret
        assert response.json()["code"] == "CAPABILITY_UNSUPPORTED", secret

    unauth = await client.post("/v1/audit/query", json={})
    assert unauth.status_code == 401
    assert unauth.json()["code"] == "AUTH_REQUIRED"


# --------------------------------------------------------------------------
# cross_entity_mutate (contract 1.1.0, CCR-15): unimplemented capability
# must say so honestly, and the new fixed 3-segment route
# (`/v1/data/mutations`) must never collide with the existing 4-segment
# per-entity route (`/v1/data/{entity}/mutations`) even for an entity
# literally named "mutations".
# --------------------------------------------------------------------------


async def test_cross_entity_mutate_is_capability_unsupported_for_any_application_credential(client):
    # The stub never reads the body at all (nothing to validate for an
    # operation this foundation never executes -- see `http.py`'s own
    # comment), so an empty object is enough here, matching `post_audit_
    # query`'s identical precedent above.
    for secret in ("secret-a", "dev-secret-a"):
        response = await client.post("/v1/data/mutations", headers=_auth(secret), json={})
        assert response.status_code == 400, secret
        assert response.json()["code"] == "CAPABILITY_UNSUPPORTED", secret

    unauth = await client.post("/v1/data/mutations", json={})
    assert unauth.status_code == 401
    assert unauth.json()["code"] == "AUTH_REQUIRED"


async def test_stub_endpoints_count_against_the_request_rate_limit():
    # docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 5 item 2 (review
    # R12): `deny_unsupported` routes the stub through `DataService._slot`,
    # so a caller cannot spend requests against `post_audit_query`/
    # `post_cross_entity_mutate` for free just because neither ever
    # executes anything. With `requests_per_minute=1`, the first stub call
    # for a credential must still succeed (as CAPABILITY_UNSUPPORTED, not
    # as a rate-limit response), and the *second* call for that same
    # credential -- even though it is the exact same never-executing stub
    # -- must be refused as LIMIT_EXCEEDED, proving the first call was
    # actually counted.
    service, _control = _build_service(requests_per_minute=1)
    async with _client(service) as client:
        first = await client.post("/v1/data/mutations", headers=_auth("secret-a"), json={})
        assert first.status_code == 400
        assert first.json()["code"] == "CAPABILITY_UNSUPPORTED"

        second = await client.post("/v1/data/mutations", headers=_auth("secret-a"), json={})
        assert second.status_code == 429
        assert second.json()["code"] == "LIMIT_EXCEEDED"
        assert second.json()["details"]["resource"] == "requests_per_minute"

        # A different credential has its own independent rate window
        # (DataService._acquire_rate keys on credential_id), so this is not
        # a cross-credential accounting bug -- audit_query is bound too.
        other = await client.post("/v1/audit/query", headers=_auth("dev-secret-a"), json={})
        assert other.status_code == 400
        assert other.json()["code"] == "CAPABILITY_UNSUPPORTED"
        other_again = await client.post("/v1/audit/query", headers=_auth("dev-secret-a"), json={})
        assert other_again.status_code == 429
        assert other_again.json()["code"] == "LIMIT_EXCEEDED"


async def test_cross_entity_mutate_route_does_not_collide_with_per_entity_mutate_route_for_an_entity_named_mutations(client):
    # `POST /v1/data/mutations` (3 path segments) is the new cross-entity
    # stub -- always CAPABILITY_UNSUPPORTED, per the test above.
    cross_entity = await client.post("/v1/data/mutations", headers=_auth("secret-a"), json={})
    assert cross_entity.json()["code"] == "CAPABILITY_UNSUPPORTED"

    # `POST /v1/data/mutations/mutations` (4 path segments: the per-entity
    # route with `entity="mutations"`) must still resolve to the ordinary,
    # executing `post_mutate` handler -- proven here by getting the
    # per-entity handler's own outcome (NOT_FOUND, since no entity named
    # "mutations" is registered for app-a) rather than the cross-entity
    # stub's CAPABILITY_UNSUPPORTED. The two outcomes are only possible
    # from two different handlers, so this is a direct routing check, not
    # an inference from status code alone.
    per_entity = await client.post("/v1/data/mutations/mutations", headers=_auth("secret-a"), json={"operations": [{"operation": "insert", "values": {}}]})
    assert per_entity.status_code == 404
    assert per_entity.json()["code"] == "NOT_FOUND"
