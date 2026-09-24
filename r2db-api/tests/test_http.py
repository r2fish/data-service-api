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

from r2db_api import ControlAuthority, CredentialStore, DataService, FoundationError
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
            headers=_auth("cred-a.secret-a"),
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
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "application_id": "app-b"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"

    for field, value in (("role", "developer"), ("database", "app-b"), ("schema", "app-b")):
        response = await client.post(
            "/v1/data/notes/mutations",
            headers=_auth("cred-a.secret-a"),
            json={"operations": [{"operation": "insert", "values": {"id": 42}}], field: value},
        )
        assert response.status_code == 400, field
        assert response.json()["code"] == "VALIDATION_FAILED", field

    # Prove scope really is server-bound: a syntactically valid request from
    # app-a's credential only ever sees app-a's row.
    ok = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
    assert ok.status_code == 200
    assert ok.json()["items"] == [{"id": 1}]


async def test_cross_application_isolation_over_http(client):
    resp_a = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
    resp_b = await client.post("/v1/data/notes/query", headers=_auth("cred-b.secret-b"), json={"select": ["id"]})
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
        response = await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))

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
        headers={**_auth("cred-a.secret-a"), "content-type": "application/json"},
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

    ok = await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))
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
        response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
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
        response = await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REVOKED"


async def test_disabled_application_fails_closed():
    service, control = _build_service()
    control.set_application_enabled("app-a", enabled=False)
    async with _client(service) as client:
        response = await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))
    assert response.status_code == 403
    assert response.json()["code"] == "APPLICATION_DISABLED"


# --------------------------------------------------------------------------
# capabilities
# --------------------------------------------------------------------------


async def test_capabilities_document_matches_contract_shape(client):
    response = await client.get("/v1/capabilities", headers=_auth("cred-a.secret-a"))
    assert response.status_code == 200
    body = response.json()
    for key in ("contract_version", "capabilities", "limits", "limit_enforcement"):
        assert key in body
    assert response.headers["x-request-id"]


# --------------------------------------------------------------------------
# query
# --------------------------------------------------------------------------


async def test_query_happy_path(client):
    response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
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
        "/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"], "page": {"size": 1}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [{"id": 1}]
    assert body["next_page"] is None


async def test_query_page_size_over_the_contract_maximum_is_validation_failed(client):
    """WP-4 review minor-1: `Page.size` is bounded at 1000 by the contract
    itself (`spec/data-service-api.v1.json`), independent of whatever
    `ResourceLimits.result_items` a deployment happens to configure.
    Phase 11 (design D-3 (8)): out-of-range `page.size` (both above 1000
    and, D-3 (8)'s other half, `<= 0`) is refused as a contract-schema
    violation naming `page/size`, not `budget`/`page_size`."""
    response = await client.post(
        "/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"], "page": {"size": 1001}}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert response.json()["details"] == {"violated_declaration": "request_schema", "field": "page/size"}


async def test_query_order_by_sorts_ascending_and_descending(client):
    """CCR-13 WP-4: `order_by` is delegated, not rejected, and the HTTP
    response reflects the real sort order."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}, {"operation": "insert", "values": {"body": "m"}}]},
    )
    assert response.status_code == 200

    ascending = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["body"], "order_by": [{"field": "body", "direction": "asc"}]},
    )
    assert ascending.status_code == 200
    ascending_body = ascending.json()
    assert ascending_body["items"] == [{"body": "a"}, {"body": "m"}, {"body": "z"}]
    assert ascending_body["next_page"] is None
    assert len(ascending_body["revisions"]) == 3

    descending = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
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
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "dup"}}, {"operation": "insert", "values": {"body": "dup"}}]},
    )
    assert response.status_code == 200
    # Seeded row: id=1, body="a". Then id=2/3, body="dup"/"dup".
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id", "body"], "order_by": [{"field": "body", "direction": "asc"}, {"field": "id", "direction": "desc"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [{"id": 1, "body": "a"}, {"id": 3, "body": "dup"}, {"id": 2, "body": "dup"}]
    assert body["next_page"] is None


async def test_query_order_by_unknown_field_is_not_found(client):
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
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
        headers=_auth("cred-a.secret-a"),
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
        response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json=body)
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
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert seeded.status_code == 200
    first = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1}},
    )
    cursor = first.json()["next_page"]
    assert cursor  # the just-inserted second row makes a next page exist
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1, "cursor": tampered}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_query_cursor_minted_for_a_different_entity_is_rejected(client):
    """A cursor's opaque binding hash binds the entity it was minted
    against (`r2db_api.structured.canonical_page_binding`) -- reusing one
    against a different entity must fail loudly, never silently page
    through the wrong entity's rows."""
    developer = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_entity", "entity": "widgets", "fields": ["name"]},
    )
    assert developer.status_code == 200
    seeded = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert seeded.status_code == 200

    minted = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1}},
    )
    cursor = minted.json()["next_page"]
    assert cursor

    response = await client.post(
        "/v1/data/widgets/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "order_by": [{"field": "id", "direction": "asc"}], "page": {"size": 1, "cursor": cursor}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_query_matches_filter_executes(client):
    """CCR-13 WP-5b: `matches` is declared `enabled` (`structured_query.
    operators`) and reachable end-to-end over HTTP."""
    response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "where": [{"field": "body", "operator": "matches", "value": "a%"}]},
    )
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": 1}]


async def test_entity_identifier_validation_flows_through_http(client):
    response = await client.post(
        "/v1/data/bad-entity!/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]}
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"IDENTIFIER_INVALID", "NOT_FOUND"}


# --------------------------------------------------------------------------
# mutate
# --------------------------------------------------------------------------


async def test_mutate_happy_path_commits(client):
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "z"}}]},
    )
    assert response.status_code == 200
    # CCR-13 WP-5b: `assigned_addresses` now reaches the response -- the
    # seeded row is id=1, so this insert resolves to id=2. Contract 1.7.0
    # (D-7, WP-2e): `request_id` now reaches every successful response too
    # -- popped here (its own value is opaque/per-request, covered by
    # `tests/test_denial_details_and_request_id.py`) so this test keeps
    # pinning the REST of the shape by equality.
    body = response.json()
    request_id = body.pop("request_id", None)
    assert request_id, "a successful MutationResult must carry request_id (D-7)"
    assert body == {"committed": True, "affected": 1, "assigned_addresses": [{"address": {"id": 2}}]}


async def test_mutate_assigned_addresses_are_insert_only_in_operation_order(client):
    """A batch mixing insert/update: only the inserts contribute an
    element, in operation order -- an update contributes nothing."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
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


async def test_mutate_best_effort_is_capability_unsupported(client):
    """`idempotency_key` used to be gated here too (WP-1 snapshot) -- WP-2c
    (contract 1.7.0, D-5) removed that gate in the same commit as flipping
    `capabilities().idempotency` to `enabled`; its own real, positive HTTP-
    boundary coverage lives in `tests/test_idempotency_records.py`.
    `best_effort_transactions` is untouched by this phase and stays
    `unavailable`."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"id": 6}}], "transaction": "best_effort"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


async def test_contract_1_7_0_provisional_gate_has_closed_for_budget_and_idempotency_key(client):
    """Phase 9 WP-1 (contract 1.7.0, design D-1 (3)) shipped the packaged
    contract copy already at 1.7.0 with a provisional gate rejecting
    `dry_run`/`plan`/`budget`/`SchemaOperationRequest.idempotency_key`
    outright, before any of the four capabilities those fields govern was
    real. WP-2a closed it for `field_constraints`/`enum`/`nullable`
    (`constraint_declarations`), WP-2b for `dry_run`/`plan` (`dry_run`),
    and WP-2c/WP-2d (this commit) close the LAST two remaining names --
    `idempotency_key` (`idempotency`) and `budget` (`request_budget`).
    There is no provisional gate left for r2db to observe at the HTTP
    boundary; this test instead pins the CLOSURE itself -- every one of
    the 6 originally-gated fields now reaches real handling over HTTP,
    across all three endpoints, with no leftover `CAPABILITY_UNSUPPORTED`
    anywhere. Full positive/negative behavioural coverage for `budget`/
    `idempotency_key` lives in `tests/test_budget_narrowing.py`/`tests/
    test_idempotency_records.py`; this test's own scope is the HTTP
    boundary reaching real service code for all three endpoints, not
    those fields' own semantics.
    """
    # --- query: budget ---
    query_response = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "budget": {"result_items": 1}},
    )
    assert query_response.status_code == 200
    assert "items" in query_response.json()

    # --- mutate: budget, real narrowing effect over HTTP (a real row is
    # created -- this is no longer refused before execution). ---
    mutate_response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "budget-closure"}}], "budget": {"batch_items": 1}},
    )
    assert mutate_response.status_code == 200
    assert mutate_response.json()["committed"] is True
    assert mutate_response.json()["affected"] == 1

    # --- mutate: idempotency_key, real record-and-replay effect over
    # HTTP. ---
    idem_body = {"operations": [{"operation": "insert", "values": {"body": "idem-closure"}}], "idempotency_key": "http-closure-key"}
    first = await client.post("/v1/data/notes/mutations", headers=_auth("cred-a.secret-a"), json=idem_body)
    assert first.status_code == 200
    second = await client.post("/v1/data/notes/mutations", headers=_auth("cred-a.secret-a"), json=dict(idem_body))
    assert second.status_code == 200
    assert second.json() == first.json()
    catalog_after = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    query_after = await client.post(
        "/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"], "where": [{"field": "body", "operator": "eq", "value": "idem-closure"}]}
    )
    assert catalog_after.status_code == 200
    assert len(query_after.json()["items"]) == 1, "the replay must not have inserted a second row"

    # --- schema: budget / idempotency_key ---
    schema_cases = [
        {"operation": "add_field", "entity": "notes", "field": "budget_closure_field", "budget": {"execution_ms": 1000}},
        {"operation": "add_field", "entity": "notes", "field": "idempotency_closure_field", "idempotency_key": "http-schema-closure-key"},
    ]
    for case in schema_cases:
        response = await client.post("/v1/schema/operations", headers=_auth("dev-a.dev-secret-a"), json=case)
        assert response.status_code == 200, (case, response.json())
        assert response.json()["committed"] is True
    schema_revision_after = (await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))).json()
    notes_fields_after = next(e["fields"] for e in schema_revision_after["entities"] if e["entity"] == "notes")
    for real_field in ("budget_closure_field", "idempotency_closure_field"):
        assert real_field in notes_fields_after


def test_contract_1_7_0_provisional_gate_has_closed_for_budget_and_idempotency_key_in_process():
    """WP-1a rework item 6's own gate (`DataService.schema`, in-process --
    bypassing `r2db_api.http`'s ASGI boundary entirely) used to reject
    `budget`/`idempotency_key` unconditionally, including the empty/falsy
    forms `budget={}`/`idempotency_key=""` (WP-1a code review item 5's own
    key-membership-not-truthiness pin). WP-2c/WP-2d remove that gate for
    both names in this commit (`_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS` no
    longer names either) -- an empty `budget` (no class narrowed) and an
    empty-string `idempotency_key` (a valid, if unwise, client-chosen key)
    both now reach real handling and commit successfully, mirroring WP-2a/
    WP-2b's identical closure for `field_constraints`/`enum`/`nullable`/
    `dry_run`/`plan`."""
    service, _control = _build_service()
    developer = service.authenticate("dev-a.dev-secret-a")

    outcome_a = service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "in_process_budget_field", "budget": {}})
    assert outcome_a.committed is True

    outcome_b = service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "in_process_idempotency_field", "idempotency_key": ""})
    assert outcome_b.committed is True

    catalog_after = service.catalog(developer)
    notes_fields_after = next(e["fields"] for e in catalog_after["entities"] if e["entity"] == "notes")
    assert "in_process_budget_field" in notes_fields_after
    assert "in_process_idempotency_field" in notes_fields_after


def test_contract_1_7_0_new_capabilities_are_all_declared_enabled():
    """Completion condition 25 (peer-local half): the 3 new capabilities
    were ALL declared `unavailable` in the SAME commit as the provisional
    gate (P-3) -- the common-suite half of this (defined ⊆ declared, all
    14 names present) is `conformance-tests/test_c11_document_
    conformance.py` (裁定 T-4). WP-2a flipped `constraint_declarations` to
    `enabled` in its own commit (its own gate/behavior/declaration
    together, per D-1 (4)); WP-2b flipped `dry_run` the same way; WP-2c/
    WP-2d (this commit) flip the last two -- `idempotency`/`request_
    budget` -- closing out every one of the 3 new capabilities this phase
    introduced."""
    service, _control = _build_service()
    developer = service.authenticate("dev-a.dev-secret-a")
    capabilities = service.capabilities(developer)["capabilities"]
    assert capabilities["constraint_declarations"]["status"] == "enabled"
    assert capabilities["dry_run"]["status"] == "enabled"
    assert capabilities["idempotency"]["status"] == "enabled"
    assert capabilities["request_budget"]["status"] == "enabled"


# --------------------------------------------------------------------------
# Contract 1.7.0 (D-4, WP-2b): dry_run/plan at the HTTP boundary.
#
# Review round F-4 (`{scratchpad}/rulings-r4.md`): this WP built the
# response-shaping code (`http.py:post_mutate`/`post_schema`) but the
# original submission's own `test_http.py` diff only ever REMOVED the
# gate-test assertions above -- no peer-local test observed the dry_run/
# plan response SHAPE over the actual ASGI boundary (in-process coverage
# in `tests/test_dry_run_and_plan.py` never exercises `http.py` at all).
# A mutation to hardcode `result.committed` to `True` in `post_mutate`
# left the FULL suite (1054 tests) green before these three existed.
# --------------------------------------------------------------------------


async def test_http_mutate_dry_run_response_shape(client):
    """(a) mutation dry_run: `committed: false`, a `plan`, no row added,
    and `assigned_addresses` absent (review F-6 -- the KEY itself, not an
    empty list)."""
    before = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    before_notes = next(e for e in before.json()["entities"] if e["entity"] == "notes")

    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "http-dry"}}], "dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["committed"] is False
    assert body["affected"] == 1
    assert isinstance(body["plan"], str) and body["plan"]
    assert "assigned_addresses" not in body

    query = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "where": [{"field": "body", "operator": "eq", "value": "http-dry"}]},
    )
    assert query.json()["items"] == []
    after = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    after_notes = next(e for e in after.json()["entities"] if e["entity"] == "notes")
    assert after_notes == before_notes


async def test_http_schema_dry_run_response_shape(client):
    """(b) schema dry_run: `committed: false`, `descriptor` reports the
    entity as it WOULD read afterwards (the new field present), and
    `revision` is the CURRENT (pre-apply) value, not a bumped one
    (addendum 2 S-j) -- a real apply afterwards actually advances it."""
    # `revision` is not surfaced by `/v1/catalog` -- read the current
    # value off a real, harmless schema apply first (a `create_index`
    # baseline), the same way `test_schema_endpoint_requires_developer_
    # authority` reads a response's `revision`.
    baseline = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "http_dry_baseline_idx", "fields": ["body"]},
    )
    assert baseline.status_code == 200
    revision_before = int(baseline.json()["revision"])

    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "http_dry_field", "dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["committed"] is False
    assert int(body["revision"]) == revision_before
    assert "http_dry_field" in body["descriptor"]["fields"]
    assert isinstance(body["plan"], str) and body["plan"]

    catalog = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    notes = next(e for e in catalog.json()["entities"] if e["entity"] == "notes")
    assert "http_dry_field" not in notes["fields"]

    # A real apply (no `dry_run`/`plan`) afterwards genuinely advances the
    # revision past what the dry run reported -- the pre-1.7.0 response
    # shape (`committed: true`, no `descriptor`/`plan`) is unchanged.
    real = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "http_real_field"},
    )
    assert real.status_code == 200
    real_body = real.json()
    assert real_body["committed"] is True
    assert int(real_body["revision"]) > revision_before
    assert "descriptor" not in real_body
    assert "plan" not in real_body


async def test_http_mutate_stale_plan_is_precondition_failed_412(client):
    """(c) a `plan` presented on a real (non-dry-run) request that no
    longer matches the request/schema state is refused `PRECONDITION_
    FAILED`, HTTP 412, `details.violated_declaration: plan` -- and
    nothing executes."""
    dry = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "http-plan-probe"}}], "dry_run": True},
    )
    assert dry.status_code == 200
    stale_plan = dry.json()["plan"]

    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        # A body differing from the one the plan was computed against --
        # the digest no longer agrees (D-4 (7)).
        json={"operations": [{"operation": "insert", "values": {"body": "http-plan-probe-different"}}], "plan": stale_plan},
    )
    assert response.status_code == 412
    body = response.json()
    assert body["code"] == "PRECONDITION_FAILED"
    assert body["details"]["violated_declaration"] == "plan"

    query = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "where": [{"field": "body", "operator": "matches", "value": "http-plan-probe%"}]},
    )
    assert query.json()["items"] == []


async def test_http_mutate_plan_digest_treats_an_omitted_transaction_key_differently_from_an_explicit_one(client):
    """N-2 (`{scratchpad}/audit-wp2b.md`) / G-1 (`{scratchpad}/rulings-r4.md`
    addendum): the plan digest never fills in a `transaction` *default* --
    a body that omits the key digests differently from one that spells out
    `"atomic"` explicitly, even though both behave identically otherwise
    (`service.py`'s own comment: "a request that carried `transaction:
    "atomic"` explicitly digests differently from one that omitted the key
    entirely"). Before this test, no peer-local test observed this at the
    HTTP boundary -- the un-committed `service.py`/`http.py` fix (reverting
    `plan_request` to always carry the RESOLVED `transaction` value, audit
    mutation M-1) left `r2db-api/tests` (1061 passed) fully green; only
    `conformance-tests`' own leg 10 caught it."""
    # A body omitting `transaction` entirely -- its own dry-run plan,
    # presented on the SAME (still omitting) body, is honored.
    dry = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "http-tx-omit"}}], "dry_run": True},
    )
    assert dry.status_code == 200
    plan = dry.json()["plan"]

    real = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "http-tx-omit"}}], "plan": plan},
    )
    assert real.status_code == 200
    assert real.json()["committed"] is True

    # A second dry run, for a DIFFERENT body (so the query check below is
    # unambiguous), again omitting `transaction`.
    dry2 = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "insert", "values": {"body": "http-tx-explicit"}}], "dry_run": True},
    )
    assert dry2.status_code == 200
    plan2 = dry2.json()["plan"]

    # The IDENTICAL operations, now with `"transaction": "atomic"` spelled
    # out explicitly -- behaviourally identical, but a DIFFERENT digest
    # input (G-1) -- refused for staleness, never accepted-and-ignored.
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={
            "operations": [{"operation": "insert", "values": {"body": "http-tx-explicit"}}],
            "transaction": "atomic",
            "plan": plan2,
        },
    )
    assert response.status_code == 412
    body = response.json()
    assert body["code"] == "PRECONDITION_FAILED"
    assert body["details"]["violated_declaration"] == "plan"

    query = await client.post(
        "/v1/data/notes/query",
        headers=_auth("cred-a.secret-a"),
        json={"select": ["id"], "where": [{"field": "body", "operator": "eq", "value": "http-tx-explicit"}]},
    )
    assert query.json()["items"] == []


async def test_mutate_update_and_delete_where_matches_executes(client):
    """CCR-13 WP-5b: `update`/`delete`'s own `operation.where` accepts
    `matches` too, not only `query()`'s predicates -- executes end-to-end
    over HTTP now that `matches` is declared `enabled`."""
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "body", "operator": "matches", "value": "a%"}], "values": {"body": "renamed"}}]},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1

    delete_where = [{"field": "body", "operator": "matches", "value": "rename%"}]
    probe = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "delete", "where": delete_where, "destructive": True}]},
    )
    assert probe.status_code == 409
    assert probe.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    phrase = probe.json()["details"]["required_confirmation"]

    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={
            "operations": [
                {"operation": "delete", "where": delete_where, "destructive": True, "confirmation": phrase}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1
    query_response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["body"]})
    assert query_response.json()["items"] == []


async def test_mutate_invalid_transaction_value_is_validation_failed(client):
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
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
    query_response = await client.post("/v1/data/notes/query", headers=_auth("cred-a.secret-a"), json={"select": ["id"]})
    revision = query_response.json()["revisions"][0]
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "z"}, "expected_revision": revision}]},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1
    # A stale revision now fails as a real precondition mismatch, not a
    # capability refusal.
    stale = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
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
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "upsert", "values": {"body": "z"}}]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


async def test_http_mutate_upsert_with_a_declared_unique_key_executes(client):
    developer_response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "tag"},
    )
    assert developer_response.status_code == 200
    index_response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_tag", "fields": ["tag"], "unique": True},
    )
    assert index_response.status_code == 200
    response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "upsert", "values": {"tag": "z"}}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["affected"] == 1
    assert body["assigned_addresses"] == [{"address": {"id": 2}}]


async def test_http_schema_create_index_and_drop_index_execute(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"], "unique": True},
    )
    assert response.status_code == 200
    catalog_response = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    assert catalog_response.json()["entities"][0]["unique_keys"] == [{"name": "by_body", "fields": ["body"]}]

    without_confirmation = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "drop_index", "entity": "notes", "index": "by_body"},
    )
    assert without_confirmation.status_code == 409
    assert without_confirmation.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    phrase = without_confirmation.json()["details"]["required_confirmation"]

    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "drop_index", "entity": "notes", "index": "by_body", "destructive": True, "confirmation": phrase},
    )
    assert response.status_code == 200
    catalog_response = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    assert catalog_response.json()["entities"][0]["unique_keys"] == []


async def test_http_schema_create_index_still_requires_developer_authority(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("cred-a.secret-a"),
        json={"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_http_schema_field_type_executes(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "n", "field_type": "integer"},
    )
    assert response.status_code == 200
    mutate_response = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": 5}}]},
    )
    assert mutate_response.status_code == 200
    bad_type = await client.post(
        "/v1/data/notes/mutations",
        headers=_auth("cred-a.secret-a"),
        json={"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"n": "not-an-int"}}]},
    )
    assert bad_type.status_code == 400
    assert bad_type.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("bad_field_types", [{"a": ["string"]}, {"a": {"x": 1}}, {"a": 1}, {"a": None}])
async def test_http_create_entity_field_types_non_string_value_is_validation_failed_not_503(client, bad_field_types):
    """Coordinator F2 (2026-09-04 review): the ACTUAL reachable path for a
    non-string `field_types` value is real HTTP, not a direct
    `bind_schema_operation` call -- `_check_object_shape` (`http.py`'s own
    JSON-Schema check) constrains `field_types`' own top-level shape (must
    be an object) but not its VALUES, so `{"a": ["string"]}` reaches
    `structured.py`'s `if declared_type not in FIELD_TYPES:` unfiltered.
    Before the fix, the unhashable cases (`list`/`dict`) raised `TypeError`
    there, which `_endpoint` (http.py) maps to a bare 503
    SERVICE_UNAVAILABLE -- not the `VALIDATION_FAILED` design D-3(iv)(b)
    requires. `{"a": 1}`/`{"a": None}` are hashable (no `TypeError`) but
    were ALSO wrongly accepted-as-a-lookup-miss before the `isinstance`
    guard was added first, so all four forms are exercised together here."""
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_entity", "entity": "f2_http_reject", "fields": ["a"], "field_types": bad_field_types},
    )
    assert response.status_code == 400, f"{bad_field_types!r} -> {response.status_code} {response.text}"
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_http_add_field_field_type_non_string_value_is_validation_failed_not_503(client):
    """Coordinator F2: the scalar `add_field.field_type` sibling, over real
    HTTP."""
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "add_field", "entity": "notes", "field": "f2_scalar", "field_type": ["string"]},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


async def test_schema_endpoint_requires_developer_authority(client):
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("cred-a.secret-a"),
        json={"operation": "create_entity", "entity": "widgets"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_entity", "entity": "widgets"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["committed"] is True
    assert isinstance(body["revision"], str)


async def test_destructive_schema_operation_requires_confirmation(client):
    await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "create_entity", "entity": "temp_entity"},
    )
    response = await client.post(
        "/v1/schema/operations",
        headers=_auth("dev-a.dev-secret-a"),
        json={"operation": "drop_entity", "entity": "temp_entity"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


async def test_catalog_matches_contract_shape_and_application_scope(client):
    response = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    assert response.status_code == 200
    body = response.json()
    # Contract 1.1.0 (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md §2/R-1):
    # `row_addressability` is declared `enabled` (WP-5b), so the full
    # `EntityDescriptor` shape reaches the response with no narrowing.
    # Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints` is a real key
    # too now -- total, `nullable: true` and no `enum` here (nothing was
    # ever declared).
    assert body == {
        "application_scope": "app-a",
        "entities": [
            {
                "entity": "notes",
                "fields": ["body", "id"],
                "field_types": {"body": "json", "id": "integer"},
                "field_constraints": {"body": {"nullable": True}, "id": {"nullable": True}},
                "mutation_class": "mutable",
                "address_fields": ["id"],
                "address_reuse": "never",
                "unique_keys": [],
            }
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
        response = await client.get("/v1/catalog", headers=_auth("cred-a.secret-a"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REVOKED"


# --------------------------------------------------------------------------
# audit_query: unimplemented capability must say so honestly.
# --------------------------------------------------------------------------


async def test_audit_query_unreachable_with_any_application_credential(client):
    for secret in ("cred-a.secret-a", "dev-a.dev-secret-a"):
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
    for secret in ("cred-a.secret-a", "dev-a.dev-secret-a"):
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
        first = await client.post("/v1/data/mutations", headers=_auth("cred-a.secret-a"), json={})
        assert first.status_code == 400
        assert first.json()["code"] == "CAPABILITY_UNSUPPORTED"

        second = await client.post("/v1/data/mutations", headers=_auth("cred-a.secret-a"), json={})
        assert second.status_code == 429
        assert second.json()["code"] == "LIMIT_EXCEEDED"
        assert second.json()["details"]["resource"] == "requests_per_minute"

        # A different credential has its own independent rate window
        # (DataService._acquire_rate keys on credential_id), so this is not
        # a cross-credential accounting bug -- audit_query is bound too.
        other = await client.post("/v1/audit/query", headers=_auth("dev-a.dev-secret-a"), json={})
        assert other.status_code == 400
        assert other.json()["code"] == "CAPABILITY_UNSUPPORTED"
        other_again = await client.post("/v1/audit/query", headers=_auth("dev-a.dev-secret-a"), json={})
        assert other_again.status_code == 429
        assert other_again.json()["code"] == "LIMIT_EXCEEDED"


async def test_cross_entity_mutate_route_does_not_collide_with_per_entity_mutate_route_for_an_entity_named_mutations(client):
    # `POST /v1/data/mutations` (3 path segments) is the new cross-entity
    # stub -- always CAPABILITY_UNSUPPORTED, per the test above.
    cross_entity = await client.post("/v1/data/mutations", headers=_auth("cred-a.secret-a"), json={})
    assert cross_entity.json()["code"] == "CAPABILITY_UNSUPPORTED"

    # `POST /v1/data/mutations/mutations` (4 path segments: the per-entity
    # route with `entity="mutations"`) must still resolve to the ordinary,
    # executing `post_mutate` handler -- proven here by getting the
    # per-entity handler's own outcome (NOT_FOUND, since no entity named
    # "mutations" is registered for app-a) rather than the cross-entity
    # stub's CAPABILITY_UNSUPPORTED. The two outcomes are only possible
    # from two different handlers, so this is a direct routing check, not
    # an inference from status code alone.
    per_entity = await client.post("/v1/data/mutations/mutations", headers=_auth("cred-a.secret-a"), json={"operations": [{"operation": "insert", "values": {}}]})
    assert per_entity.status_code == 404
    assert per_entity.json()["code"] == "NOT_FOUND"
