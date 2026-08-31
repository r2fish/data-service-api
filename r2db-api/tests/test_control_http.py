"""Tests for the CCR-14 control-plane ASGI HTTP boundary in `r2db_api.control_http`
(+ its composition root, `r2db_api.control_main`).

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.6, §2 (endpoint table + common processing order + problem+json/deterrence
discipline), §3 (`AuthorityTopology` -- covered by `test_topology.py`, not
here), §5's WP-4 row (test list item-for-item), §8 m-7 (401 code
non-fixation)/m-10 (no module-level `app`), and §12.5 (WP-3 handoff).

httpx `ASGITransport` against the in-memory backend, mirroring `test_http.
py`'s own established pattern -- the Postgres backend's own operational
semantics (must_rotate gate, R-7 limits, R-6 same-transaction/denial audit,
R-11 declarations) are already verified end-to-end against a real server in
`test_control_plane_service.py` (WP-3); this file only has to prove the
*wiring* -- 11 routes -> 9 `ControlPlaneService` methods, request/response
shape checks, byte-bound/problem+json/independence -- is correct.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

from r2db_api.audit import ControlAuditSink
from r2db_api.auth import ControlCredentialStore, CredentialStore
from r2db_api.control_http import _ROUTES, create_control_app
from r2db_api.control_plane import _AUDIT_ROLE_ALLOWED_OPERATIONS, ControlPlaneService, InMemoryControlBackend
from r2db_api.http import create_app
from r2db_api.limits import ControlPlaneLimits
from r2db_api.service import ControlAuthority, DataService

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

BASE_URL = "http://r2db-control.example.invalid"
PEPPER = "synthetic-test-pepper-control-http-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-control-http-ctl-0000"
_SEED_SECRET = "synthetic-control-http-seed-secret-0000"
_SEED_CREDENTIAL_ID = "ctl_httptest0000000000000"

# Explicit marker -- same reasoning as `test_http.py`'s own identical
# comment: this also has to run correctly under the repo-root pytest
# invocation, whose own `pyproject.toml` does not set `anyio_mode = "auto"`
# (only `r2db-api/pyproject.toml`'s standalone-package config does).
pytestmark = pytest.mark.anyio

# Generous enough that no test below accidentally trips a limit it isn't
# specifically testing (mirrors `test_control_plane_service.py`'s own
# `_GENEROUS_LIMITS` convention) -- the rate-limit test builds its own tight
# `ControlPlaneLimits` explicitly instead.
_GENEROUS_LIMITS = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=100_000)


def _auth(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


def _build_control_harness(limits: ControlPlaneLimits | None = None) -> types.SimpleNamespace:
    """In-memory `ControlPlaneService` + a control credential that has
    already completed its must-rotate ceremony (R-5) -- the seeded secret is
    usable for every ordinary operation the tests below exercise, exactly
    the state `ops.py bootstrap` + `rotate-control-credential` would leave
    behind for a real deployment.
    """
    credentials = CredentialStore(pepper=PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    audit = ControlAuditSink()
    service = ControlPlaneService(backend, audit=audit, limits=limits or _GENEROUS_LIMITS)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(_SEED_CREDENTIAL_ID, _SEED_SECRET, work=work)
    with control_credentials.unit_of_work() as work:
        # `rotate` clears `must_rotate` (design R-5/§2 M-2) -- the seeded
        # credential is immediately usable for every operation, not just
        # `capabilities`/self-rotate.
        control_credentials.rotate(_SEED_CREDENTIAL_ID, _SEED_SECRET, work=work)
    return types.SimpleNamespace(
        service=service,
        control_credentials=control_credentials,
        audit=audit,
        secret=_SEED_SECRET,
        credential_id=_SEED_CREDENTIAL_ID,
        data_service=data_service,
        authority=authority,
    )


@pytest.fixture
def control_harness() -> types.SimpleNamespace:
    return _build_control_harness()


# ===========================================================================
# 1. All 11 endpoints wired to the 9 `ControlPlaneService` methods (work
#    order §4 item 1): a full register -> list -> issue -> rotate -> revoke
#    -> enable/disable roundtrip, contract-shaped throughout.
# ===========================================================================


async def test_full_endpoint_roundtrip_through_all_11_routes(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        caps = await client.get("/control/v1/capabilities", headers=headers)
        assert caps.status_code == 200
        caps_doc = caps.json()
        assert caps_doc["capabilities"]["control_plane"] == {"status": "enabled"}
        assert caps_doc["role"] == "control"
        assert set(caps_doc["limits"]) == {"applications", "credentials_per_application", "control_requests_per_minute", "request_bytes"}
        # Phase 3.5 WP-4 (§4 "L4"): the HTTP-mounted two-layer override --
        # `request_bytes` reads `"enforced"` here (unlike the bare-service
        # `"unavailable"` `test_control_plane_service.py` pins), because a
        # real `RequestByteBoundMiddleware` IS mounted in front of this app.
        assert caps_doc["limit_enforcement"]["request_bytes"] == "enforced"

        registered = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_roundtrip"})
        assert registered.status_code == 200
        assert registered.json() == {"application_id": "app_roundtrip", "enabled": True}

        listed_apps = await client.get("/control/v1/applications", headers=headers)
        assert listed_apps.status_code == 200
        assert {"application_id": "app_roundtrip", "enabled": True} in listed_apps.json()["applications"]

        issued = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_roundtrip", "role": "runtime"})
        assert issued.status_code == 200
        issued_body = issued.json()
        credential_id = issued_body["credential_id"]
        assert issued_body["application_id"] == "app_roundtrip"
        assert issued_body["role"] == "runtime"
        assert issued_body["secret"]

        listed_creds = await client.get("/control/v1/credentials", headers=headers)
        assert listed_creds.status_code == 200
        assert any(row["credential_id"] == credential_id and row["role"] == "runtime" for row in listed_creds.json()["credentials"])

        rotated = await client.post(f"/control/v1/credentials/{credential_id}/rotate", headers=headers)
        assert rotated.status_code == 200
        rotated_body = rotated.json()
        assert rotated_body["credential_id"] == credential_id
        assert rotated_body["secret"] and rotated_body["secret"] != issued_body["secret"]

        disabled_cred = await client.post(f"/control/v1/credentials/{credential_id}/disable", headers=headers)
        assert disabled_cred.status_code == 200
        assert disabled_cred.json() == {"credential_id": credential_id, "enabled": False, "revoked": False}

        enabled_cred = await client.post(f"/control/v1/credentials/{credential_id}/enable", headers=headers)
        assert enabled_cred.status_code == 200
        assert enabled_cred.json() == {"credential_id": credential_id, "enabled": True, "revoked": False}

        revoked = await client.post(f"/control/v1/credentials/{credential_id}/revoke", headers=headers, json={})
        assert revoked.status_code == 200
        assert revoked.json() == {"credential_id": credential_id, "enabled": True, "revoked": True}

        disabled_app = await client.post("/control/v1/applications/app_roundtrip/disable", headers=headers)
        assert disabled_app.status_code == 200
        assert disabled_app.json() == {"application_id": "app_roundtrip", "enabled": False}

        enabled_app = await client.post("/control/v1/applications/app_roundtrip/enable", headers=headers)
        assert enabled_app.status_code == 200
        assert enabled_app.json() == {"application_id": "app_roundtrip", "enabled": True}


# ===========================================================================
# 2. Authentication (work order §4 item 2): missing bearer -> 401
#    AUTH_REQUIRED, durably audited, unattributed declaration; garbage
#    secret -> 401 AUTH_INVALID, same declaration form; role=control
#    issuance -> CAPABILITY_UNSUPPORTED + futility declaration, transcribed
#    verbatim.
# ===========================================================================


async def test_missing_bearer_is_401_auth_required_and_durably_audited(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    before = len(control_harness.audit.events())
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/capabilities")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert body["details"]["audited"] is True
    # MA-2 (WP-3 review): no secret at all identifies no credential -- the
    # *unattributed* declaration form, never the attributed one.
    assert body["details"]["attribution"] == "This request is durably recorded; not even a control credential can erase that record."

    after_events = control_harness.audit.events()
    assert len(after_events) == before + 1
    event = after_events[-1]
    assert event["outcome"] == "deny"
    assert event["reason_code"] == "AUTH_REQUIRED"
    assert event.get("actor_id") is None


async def test_garbage_secret_is_401_auth_invalid_with_recorded_declaration(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/capabilities", headers=_auth("not-a-real-control-secret-at-all"))
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_INVALID"
    assert body["details"]["audited"] is True
    assert body["details"]["attribution"] == "This request is durably recorded; not even a control credential can erase that record."


async def test_role_control_issuance_is_capability_unsupported_with_futility_declaration(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_ctl_probe"})
        response = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_ctl_probe", "role": "control"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "CAPABILITY_UNSUPPORTED"
    assert body["details"]["audited"] is True
    assert body["details"]["attribution"].startswith("This request is durably recorded and attributed")
    assert body["details"]["futility"] == (
        "No in-band path exists to create a control credential; issuance is limited to the "
        "operator bootstrap/reset ceremony, with no exceptions."
    )


# ===========================================================================
# 3. Shape validation (work order §4 item 3): unknown key / missing
#    required key / pattern violation -> VALIDATION_FAILED at the HTTP
#    layer or the service layer (both surface the same client-facing code);
#    a broken response from the service is caught before it reaches a
#    client.
# ===========================================================================


async def test_unknown_field_in_request_body_is_validation_failed(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_shape", "unexpected_field": True})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"]["fields"] == ["unexpected_field"]


async def test_missing_required_field_in_request_body_is_validation_failed(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/applications", headers=headers, json={})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_slug_pattern_violation_is_validation_failed(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/applications", headers=headers, json={"application_id": "NOT-VALID-SLUG!"})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_role_type_violation_is_validation_failed(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_role_shape"})
        response = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_role_shape", "role": "not-a-real-role"})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_broken_response_shape_from_service_is_service_unavailable():
    """WP-4 test item 3: a service that hands back a dict that does not
    match the contract's response schema must never reach a client as-is --
    `_check_response_shape` (control_http.py) is the backstop. A minimal
    stub is enough: only the one method the exercised route calls needs to
    exist."""

    class _BrokenCapabilitiesService:
        # Phase 3.5 WP-4 (§4 "L4", single source): `create_control_app` now
        # reads `.limits.request_bytes` off whatever it is given, at app-
        # build time -- a minimal stand-in service needs this attribute too.
        limits = ControlPlaneLimits()

        def check_rate(self) -> None:  # MAJOR-1: control_http.py calls this before every method now
            pass

        def capabilities(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
            del secret, request_id, rate_precharged
            return {"unexpected_key": True}  # missing every required CapabilityDocument field

    transport = httpx.ASGITransport(app=create_control_app(_BrokenCapabilitiesService()))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/capabilities", headers=_auth("irrelevant"))
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


# ===========================================================================
# 4. problem+json discipline (work order §4 item 4): content-type,
#    `request_id`, and no internal detail leaking through an uncaught
#    exception (SI-10).
# ===========================================================================


async def test_problem_json_content_type_and_request_id_header(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/capabilities")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


async def test_uncaught_service_exception_is_generic_503_with_no_internal_detail():
    _SENTINEL = "raw-postgres-connection-string-should-never-leak-abcdef123456"

    class _RaisingService:
        limits = ControlPlaneLimits()  # Phase 3.5 WP-4: see `_BrokenCapabilitiesService`'s identical comment above

        def check_rate(self) -> None:  # MAJOR-1: control_http.py calls this before every method now
            pass

        def list_applications(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
            del secret, request_id, rate_precharged
            raise RuntimeError(_SENTINEL)

    transport = httpx.ASGITransport(app=create_control_app(_RaisingService()))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/applications", headers=_auth("irrelevant"))
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert _SENTINEL not in response.text


# ===========================================================================
# 5. Byte bound (work order §4 item 5): `RequestByteBoundMiddleware`, the
#    exact same class the data plane uses, rejects an oversized body before
#    any route/shape logic runs.
# ===========================================================================


async def test_oversized_body_is_rejected_with_413_before_shape_check(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    oversized = "x" * (1_048_576 + 4096)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_x", "padding": oversized})
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["resource"] == "request_bytes"
    assert response.headers["x-request-id"] == body["request_id"]


# ===========================================================================
# 6. Rate limit (work order §4 item 6): 429 reaches the client, and it runs
#    ahead of authentication (R-6/R-7 -- an unauthenticated caller still
#    trips it).
# ===========================================================================


async def test_rate_limit_reaches_http_as_429_before_auth():
    limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=2)
    harness = _build_control_harness(limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        first = await client.get("/control/v1/capabilities")  # no Authorization header at all
        second = await client.get("/control/v1/capabilities")
        third = await client.get("/control/v1/capabilities")
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    body = third.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["resource"] == "control_requests_per_minute"
    # Design §4: rate-limit refusals carry no R-11 declaration at all (no
    # attributable actor yet, and this denial category is deliberately
    # never durably audited).
    assert "audited" not in body["details"]


# ---------------------------------------------------------------------------
# Round-2 review MAJOR-1: the rate window is charged before the body is even
# read, on the 3 body-carrying endpoints -- a malformed/unauthenticated body
# flood against any of them must still consume the window (previously it did
# not: the HTTP-layer shape check raised VALIDATION_FAILED before the one
# composed service call that used to be the only place charging happened).
# ---------------------------------------------------------------------------

_MALFORMED_BODY_ENDPOINTS = [
    ("/control/v1/applications", {}),  # missing required application_id
    ("/control/v1/credentials", {}),  # missing required application_id/role
    ("/control/v1/credentials/crd_doesnotexist00000000/revoke", {"nonsense_field": 1}),  # unknown field
]


@pytest.mark.parametrize(("path", "malformed_body"), _MALFORMED_BODY_ENDPOINTS)
async def test_malformed_body_flood_still_consumes_the_rate_window(path, malformed_body):
    limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=2)
    harness = _build_control_harness(limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # No Authorization header at all -- the whole point is this must
        # not be a free, unbounded probe just because it never authenticates.
        first = await client.post(path, json=malformed_body)
        second = await client.post(path, json=malformed_body)
        third = await client.post(path, json=malformed_body)
    assert first.status_code == 400
    assert first.json()["code"] == "VALIDATION_FAILED"
    assert second.status_code == 400
    assert second.json()["code"] == "VALIDATION_FAILED"
    assert third.status_code == 429
    assert third.json()["code"] == "LIMIT_EXCEEDED"
    assert third.json()["details"]["resource"] == "control_requests_per_minute"


async def test_valid_requests_consume_exactly_one_token_each_no_double_charge():
    """Round-2 review MAJOR-1: `control_http.py` charges the window once via
    `service.check_rate()` and then passes `rate_precharged=True` into the
    service call -- if that flag were ignored (double charge), N requests
    would consume 2N tokens and the refusal would arrive at request N/2+1,
    not N+1. Driving exactly to the configured bound pins the refusal
    position."""
    limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=3)
    harness = _build_control_harness(limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    headers = _auth(harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        responses = [await client.get("/control/v1/capabilities", headers=headers) for _ in range(3)]
        fourth = await client.get("/control/v1/capabilities", headers=headers)
    assert [r.status_code for r in responses] == [200, 200, 200]
    assert fourth.status_code == 429
    assert fourth.json()["code"] == "LIMIT_EXCEEDED"


# ===========================================================================
# 7. Independence (work order §4 item 7): the two ASGI apps' route tables
#    never overlap, in either direction; an unknown path is 404.
# ===========================================================================


def test_control_and_data_plane_route_tables_are_disjoint(control_harness):
    control_app = create_control_app(control_harness.service)
    control_routes = control_app.app.routes  # RequestByteBoundMiddleware.app is the wrapped Starlette app
    assert len(control_routes) == 11
    control_paths = {route.path for route in control_routes}
    assert all(path.startswith("/control/v1") for path in control_paths)

    data_credentials = CredentialStore(pepper="disjoint-check-pepper-0000")
    data_service = DataService(data_credentials)
    data_app = create_app(data_service)
    data_paths = {route.path for route in data_app.app.routes}

    assert not any(path.startswith("/control") for path in data_paths)
    assert not any(path.startswith("/v1") for path in control_paths)


async def test_unknown_control_path_is_404(control_harness):
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/does-not-exist")
    assert response.status_code == 404


async def test_unknown_method_is_405_with_data_plane_parity_not_found_code(control_harness):
    """Round-2 review MINOR-7(a): `control_http.py` reuses `http.py`'s
    `_http_exception_handler` unchanged, so a 405 (known path, unsupported
    method) gets the same `NOT_FOUND` code the data plane's own 404/405
    responses use -- pinned here as the control-plane counterpart to that
    parity (`http.py`'s handler maps both statuses to `NOT_FOUND`)."""
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.delete("/control/v1/capabilities", headers=_auth(control_harness.secret))
    assert response.status_code == 405
    assert response.json()["code"] == "NOT_FOUND"


async def test_revoke_with_no_body_at_all_exercises_empty_branch(control_harness):
    """Round-2 review MINOR-7(b): distinct from `json={}` (an actual, present
    empty JSON object body, already exercised by the full-roundtrip test) --
    this sends no body/content-type at all, exercising `_read_json_object_
    or_empty`'s `if not raw: return {}` branch specifically."""
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_no_body_revoke"})
        issued = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_no_body_revoke", "role": "runtime"})
        credential_id = issued.json()["credential_id"]
        response = await client.post(f"/control/v1/credentials/{credential_id}/revoke", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"credential_id": credential_id, "enabled": True, "revoked": True}


# ===========================================================================
# 7b. Destructive confirmation gate (WP-3, design docs/design/
#     DESTRUCTIVE_CONFIRMATION_V1.md R-3) over a REAL HTTP round trip --
#     `control_harness`'s own single seeded control credential is always
#     the sole live one, i.e. always the gate's own precondition.
# ===========================================================================


async def test_revoke_last_control_credential_unconfirmed_is_409_over_http(control_harness):
    """The harness's own control credential is the SOLE live one --
    revoking it without a valid confirmation must be denied over real HTTP
    with the four-key declaration, and the credential must remain fully
    live (still authenticates) afterward."""
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            f"/control/v1/credentials/{control_harness.credential_id}/revoke",
            headers=headers, json={"destructive": True},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
            assert key in body["details"]
        still_alive = await client.get("/control/v1/capabilities", headers=headers)
    assert still_alive.status_code == 200


async def test_revoke_last_control_credential_with_wire_truthy_non_boolean_destructive_is_validation_failed(control_harness):
    """Review blocker B-1, real wire reproduction: a request whose
    `destructive` field is the STRING `"false"` (a non-boolean value a
    loose `bool(...)` cast would silently coerce to `True`) must be
    rejected as a shape defect (`VALIDATION_FAILED`, 400) -- the HTTP
    layer's own `_check_object_shape` does not validate per-field JSON
    types (only extra/missing keys, `http.py`'s own docstring), so this is
    exactly the wire shape that would otherwise reach `ControlPlaneService.
    revoke_credential` unvalidated; that method's own new `isinstance`
    check (review blocker B-1) is what actually catches it. The sole
    control credential must remain fully live (not revoked) afterward.
    """
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            f"/control/v1/credentials/{control_harness.credential_id}/revoke",
            headers=headers, json={"destructive": "false", "confirmation": "irrelevant -- shape check runs first"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_FAILED"
        still_alive = await client.get("/control/v1/capabilities", headers=headers)
    assert still_alive.status_code == 200


# ===========================================================================
# 8. `control_main.build_control_app` (work order §4 item 8): required-env
#    failures, pepper-equality failure, a normal env returns an ASGI app
#    without ever connecting, and a module-level `app` exists (§8 m-10,
#    flipped WP-5).
# ===========================================================================

_VALID_ENV = {
    "R2DB_CONTROLPLANE_DSN": "host=/tmp port=1 dbname=r2db_control_http_test_unreachable",
    "R2DB_CONTROL_CREDENTIAL_PEPPER": "control-main-test-control-pepper-0000",
    "R2DB_CREDENTIAL_PEPPER": "control-main-test-app-pepper-0000",
}


@pytest.fixture
def control_main_module():
    """CCR-14 WP-5: `r2db_api.control_main` now ends with a module-level
    `app = build_control_app()` (§8 m-10's flip, same single commit as
    `main.py`'s own declaration flip) -- a bare `import r2db_api.control_main`
    therefore reads real `os.environ` the instant it first runs, exactly
    like `r2db_api.main` already does (P2-D5). This mirrors `test_credential_
    persistence.py`'s own `main_module` fixture for that exact reason: a
    valid, synthetic environment (`_VALID_ENV` above -- zero-network,
    `build_control_app`/its stores never connect eagerly, see
    `test_build_control_app_returns_asgi_app_without_connecting`'s own
    comment) is set via `pytest.MonkeyPatch` before the first import/reload,
    so this file's own top-level collection never touches this module
    (avoiding a collection-time crash for the whole root pytest suite, which
    has no such environment configured ambiently) and every test below gets
    a fresh, valid module object instead.
    """
    mp = pytest.MonkeyPatch()
    for key, value in _VALID_ENV.items():
        mp.setenv(key, value)
    try:
        import importlib
        import sys

        if "r2db_api.control_main" in sys.modules:
            module = importlib.reload(sys.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as module
        yield module
    finally:
        mp.undo()


def test_build_control_app_requires_controlplane_dsn(control_main_module):
    env = dict(_VALID_ENV)
    del env["R2DB_CONTROLPLANE_DSN"]
    with pytest.raises(RuntimeError, match="R2DB_CONTROLPLANE_DSN"):
        control_main_module.build_control_app(env)


def test_build_control_app_requires_control_credential_pepper(control_main_module):
    env = dict(_VALID_ENV)
    del env["R2DB_CONTROL_CREDENTIAL_PEPPER"]
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_CREDENTIAL_PEPPER"):
        control_main_module.build_control_app(env)


def test_build_control_app_requires_application_pepper(control_main_module):
    env = dict(_VALID_ENV)
    del env["R2DB_CREDENTIAL_PEPPER"]
    with pytest.raises(RuntimeError, match="R2DB_CREDENTIAL_PEPPER"):
        control_main_module.build_control_app(env)


def test_build_control_app_rejects_equal_peppers(control_main_module):
    env = dict(_VALID_ENV)
    env["R2DB_CREDENTIAL_PEPPER"] = env["R2DB_CONTROL_CREDENTIAL_PEPPER"]
    with pytest.raises(RuntimeError, match="must not be equal"):
        control_main_module.build_control_app(env)


def test_build_control_app_returns_asgi_app_without_connecting(control_main_module):
    # `R2DB_CONTROLPLANE_DSN` above points at a database that does not
    # exist -- if construction ever tried to connect, this would raise a
    # `psycopg` error instead of returning. `_RolePool.__init__` (postgres.py)
    # does not connect eagerly, which is exactly what this test pins down.
    app = control_main_module.build_control_app(_VALID_ENV)
    assert app is not None
    assert hasattr(app, "app")  # RequestByteBoundMiddleware wrapping a Starlette app
    assert len(app.app.routes) == 11


def test_control_main_module_level_app_exists_and_is_asgi(control_main_module):
    # §8 m-10's flip (WP-5, bound to the same single commit as `main.py`'s
    # own declaration flip): importing this module now constructs a real
    # module-level `app`, exactly like `r2db_api.main:app` already does --
    # the inverse of the pre-WP-5 mechanical check of the same name.
    assert hasattr(control_main_module, "app")
    app = control_main_module.app
    assert app is not None
    assert hasattr(app, "app")  # RequestByteBoundMiddleware wrapping a Starlette app
    assert len(app.app.routes) == 11


def test_import_r2db_api_control_main_module_succeeds_with_valid_environment():
    # Mirrors `test_credential_persistence.py::
    # test_import_r2db_api_main_module_succeeds_with_valid_environment`: a
    # real `import` in a fresh subprocess (never polluting this pytest
    # process' own `sys.modules`/`control_main_module` fixture state),
    # proving the literal `r2db_api.control_main:app` ASGI-server entry
    # point actually works end to end.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env.update(_VALID_ENV)
    script = "import r2db_api.control_main as m; assert m.app is not None; print('IMPORT_OK')"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


# ===========================================================================
# 9. Single-commit rule preserved (work order §4 item 9): the application
#    plane's own `control_plane` capability declaration stays `unavailable`.
# ===========================================================================


def test_application_plane_still_declares_control_plane_unavailable():
    credentials = CredentialStore(pepper="single-commit-check-pepper-0000")
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    authority.register_application("app_single_commit_check")
    with credentials.unit_of_work() as work:
        credentials.add("cred-single-commit", "app_single_commit_check", "runtime", "secret-single-commit", work=work)
    context = data_service.authenticate("secret-single-commit")
    document = data_service.capabilities(context)
    assert document["capabilities"]["control_plane"] == {"status": "unavailable"}


# ===========================================================================
# 10. Phase 3.5 WP-4 control-plane bundle (design docs/design/
#     PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4): audit-role HTTP
#     authorization matrix (§1-D), issuance freeze over real HTTP (§1-E),
#     and the L4 `request_bytes` single-source/two-layer form (§4 "L4").
# ===========================================================================


def _seed_audit_credential(harness: types.SimpleNamespace, *, must_rotate: bool = False) -> tuple[str, str]:
    credential_id = "ctl_" + os.urandom(8).hex()
    secret = "audit-http-secret-" + os.urandom(8).hex()
    with harness.control_credentials.unit_of_work() as work:
        harness.control_credentials.add(credential_id, secret, role="audit", work=work)
    if not must_rotate:
        with harness.control_credentials.unit_of_work() as work:
            harness.control_credentials.rotate(credential_id, secret, work=work)
    return credential_id, secret


# Round-2 independent review m-3: the operation name each route maps to --
# a second, independent source (alongside `matrix` below) this test cross-
# checks BOTH against `control_http._ROUTES` (the wire boundary's own route
# table) AND against `control_plane._AUDIT_ROLE_ALLOWED_OPERATIONS` (the
# product code's own allow-list), so a future route added to either the
# route table or the allow-list without a corresponding update here fails
# the structural-completeness assertion below, rather than silently never
# being exercised.
_ROUTE_OPERATION_NAMES: dict[tuple[str, str], str] = {
    ("GET", "/control/v1/capabilities"): "control_capabilities",
    ("POST", "/control/v1/applications"): "register_application",
    ("GET", "/control/v1/applications"): "list_applications",
    ("POST", "/control/v1/applications/{application_id}/disable"): "disable_application",
    ("POST", "/control/v1/applications/{application_id}/enable"): "enable_application",
    ("POST", "/control/v1/credentials"): "issue_credential",
    ("GET", "/control/v1/credentials"): "list_credentials",
    ("POST", "/control/v1/credentials/{credential_id}/rotate"): "rotate_credential",
    ("POST", "/control/v1/credentials/{credential_id}/revoke"): "revoke_credential",
    ("POST", "/control/v1/credentials/{credential_id}/disable"): "disable_credential",
    ("POST", "/control/v1/credentials/{credential_id}/enable"): "enable_credential",
}


async def test_audit_role_http_authorization_matrix_all_11_endpoints(control_harness):
    """Endpoint-by-endpoint audit-role authorization matrix, driven over
    real HTTP against every one of the 11 routes `_ROUTES` declares (§8
    risk 3: fail-closed completeness). The 3 read-only routes return 200 for
    an `audit`-role bearer; every other route returns 403 FORBIDDEN.

    Round-2 independent review m-3: structurally complete, not a hand-
    maintained list a future 10th route could silently bypass -- the set of
    (method, route-template) pairs this test exercises is asserted equal to
    `control_http._ROUTES` itself (a route added there with no entry here
    fails immediately), and the derived "allowed" subset is asserted equal
    to `control_plane._AUDIT_ROLE_ALLOWED_OPERATIONS` (the product code's
    own allow-list, imported directly rather than re-typed as a literal).
    """
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    control_headers = _auth(control_harness.secret)
    audit_id, audit_secret = _seed_audit_credential(control_harness)
    audit_headers = _auth(audit_secret)

    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        registered = await client.post("/control/v1/applications", headers=control_headers, json={"application_id": "app_audit_matrix"})
        assert registered.status_code == 200
        issued = await client.post("/control/v1/credentials", headers=control_headers, json={"application_id": "app_audit_matrix", "role": "runtime"})
        assert issued.status_code == 200
        credential_id = issued.json()["credential_id"]

        # (method, route-template, body-or-None, expected status) -- one
        # entry per key in `_ROUTE_OPERATION_NAMES`.
        matrix = [
            ("GET", "/control/v1/capabilities", None, 200),
            ("POST", "/control/v1/applications", {"application_id": "app_audit_matrix_denied"}, 403),
            ("GET", "/control/v1/applications", None, 200),
            ("POST", "/control/v1/applications/{application_id}/disable", None, 403),
            ("POST", "/control/v1/applications/{application_id}/enable", None, 403),
            ("POST", "/control/v1/credentials", {"application_id": "app_audit_matrix", "role": "runtime"}, 403),
            ("GET", "/control/v1/credentials", None, 200),
            ("POST", "/control/v1/credentials/{credential_id}/rotate", None, 403),
            ("POST", "/control/v1/credentials/{credential_id}/revoke", {}, 403),
            ("POST", "/control/v1/credentials/{credential_id}/disable", None, 403),
            ("POST", "/control/v1/credentials/{credential_id}/enable", None, 403),
        ]
        matrix_keys = {(method, template) for method, template, _body, _status in matrix}

        # (1) `_ROUTE_OPERATION_NAMES`' own keys must match `_ROUTES` exactly
        # -- catches drift between this file's static mapping and the real
        # route table (a route renamed/added/removed in `control_http.py`
        # without this file being updated).
        route_keys = {(method, route.path) for route in _ROUTES for method in (route.methods - {"HEAD"})}
        assert set(_ROUTE_OPERATION_NAMES) == route_keys, (
            f"_ROUTE_OPERATION_NAMES does not match control_http._ROUTES: "
            f"missing={route_keys - set(_ROUTE_OPERATION_NAMES)} extra={set(_ROUTE_OPERATION_NAMES) - route_keys}"
        )
        # (2) this test's own `matrix` must cover every one of those routes
        # -- catches a new route added to `_ROUTES`/`_ROUTE_OPERATION_NAMES`
        # with no corresponding entry in `matrix` (the "future 10th
        # operation" case m-3 names).
        assert matrix_keys == route_keys, (
            f"matrix does not cover control_http._ROUTES exactly: "
            f"missing={route_keys - matrix_keys} extra={matrix_keys - route_keys}"
        )
        # (3) the "allowed" subset this matrix expects (status 200) must
        # equal the product code's own `_AUDIT_ROLE_ALLOWED_OPERATIONS`
        # allow-list, translated through `_ROUTE_OPERATION_NAMES` -- catches
        # the allow-list being edited (in either direction) without this
        # test's own expectations being updated to match.
        allowed_keys = {(m, t) for m, t, _b, status in matrix if status == 200}
        denied_keys = {(m, t) for m, t, _b, status in matrix if status == 403}
        assert allowed_keys | denied_keys == matrix_keys  # every entry is classified one way or the other
        allowed_operations = {_ROUTE_OPERATION_NAMES[key] for key in allowed_keys}
        assert allowed_operations == _AUDIT_ROLE_ALLOWED_OPERATIONS

        for method, template, body, expected_status in matrix:
            path = template.format(application_id="app_audit_matrix", credential_id=credential_id)
            if method == "GET":
                response = await client.get(path, headers=audit_headers)
            else:
                response = await client.post(path, headers=audit_headers, json=body)
            assert response.status_code == expected_status, f"{method} {path}: expected {expected_status}, got {response.status_code} ({response.text})"
            if expected_status == 403:
                assert response.json()["code"] == "FORBIDDEN"

        # The audit credential itself was never touched by any of the 8
        # refused attempts above (still enabled, not revoked) -- confirmed
        # by it still authenticating for a 4th read afterward.
        still_alive = await client.get("/control/v1/capabilities", headers=audit_headers)
        assert still_alive.status_code == 200
        assert still_alive.json()["role"] == "audit"


async def test_issuance_freeze_forbidden_over_http_then_unfreeze_allows_again(control_harness):
    """Freeze has no in-band HTTP toggle (design §1-E, P35-D6 -- CLI only);
    this test flips the flag directly at the backend level (as `ops.py
    freeze-issuance`/`unfreeze-issuance` do out-of-band) and confirms the
    in-band `issue_credential` endpoint refuses/allows accordingly."""
    transport = httpx.ASGITransport(app=create_control_app(control_harness.service))
    headers = _auth(control_harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        registered = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_freeze_http"})
        assert registered.status_code == 200

        with control_harness.service._backend.applications_unit_of_work() as work:  # noqa: SLF001
            control_harness.service._backend.set_application_issuance_frozen("app_freeze_http", True, work=work)  # noqa: SLF001

        denied = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_freeze_http", "role": "runtime"})
        assert denied.status_code == 403
        assert denied.json()["code"] == "FORBIDDEN"

        with control_harness.service._backend.applications_unit_of_work() as work:  # noqa: SLF001
            control_harness.service._backend.set_application_issuance_frozen("app_freeze_http", False, work=work)  # noqa: SLF001

        allowed = await client.post("/control/v1/credentials", headers=headers, json={"application_id": "app_freeze_http", "role": "runtime"})
        assert allowed.status_code == 200


async def test_l4_request_bytes_single_source_mutating_limit_changes_both_bound_and_discovery():
    """§4 "L4" single-source rule: a `ControlPlaneService` constructed with a
    non-default `request_bytes` changes BOTH the real `RequestByteBound
    Middleware` bound `create_control_app` mounts AND the value `GET .../
    capabilities` discovers -- from the one place that value lives
    (`ControlPlaneService.limits`), never two independently-configured
    numbers that could drift apart."""
    small_limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=100_000, request_bytes=2048)
    harness = _build_control_harness(small_limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    headers = _auth(harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        caps = await client.get("/control/v1/capabilities", headers=headers)
        assert caps.status_code == 200
        caps_doc = caps.json()
        assert caps_doc["limits"]["request_bytes"] == 2048
        assert caps_doc["limit_enforcement"]["request_bytes"] == "enforced"

        # A body comfortably under 2048 measured bytes succeeds.
        small_ok = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_l4_small"})
        assert small_ok.status_code == 200

        # A body that exceeds the CUSTOM 2048-byte bound (but is nowhere
        # near the data plane's own default 1 MiB bound) is rejected --
        # proving the middleware is actually using this instance's own
        # smaller `request_bytes`, not a leftover default.
        oversized = "x" * 4096
        over = await client.post("/control/v1/applications", headers=headers, json={"application_id": "app_l4_over", "padding": oversized})
        assert over.status_code == 413
        assert over.json()["details"]["resource"] == "request_bytes"
        assert over.json()["details"]["limit"] == 2048
