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
from r2db_api.audit_query import InMemoryAuditQueryStore
from r2db_api.auth import ControlCredentialStore, CredentialStore, compose_bearer_locator
from r2db_api.control_http import _ROUTES, create_control_app
from r2db_api.control_plane import _AUDIT_ROLE_ALLOWED_OPERATIONS, ControlPlaneService, InMemoryControlBackend
from r2db_api.http import create_app
from r2db_api.limits import ControlPlaneLimits
from r2db_api.service import ControlAuthority, DataService

# Q4 phase WP-1 rework round (rulings-q4-wp12-rework.md sec.2): `build_control_app` is
# no longer zero-network, so the module-level-`app`/subprocess-import tests below
# (section 8) need a REAL, migrated platform database -- reused by import from
# `test_credential_persistence.py`/`test_surfaces_env.py`, the same convention
# `test_surfaces_env.py` itself already uses for this exact fixture.
from test_credential_persistence import PEPPER, _DEFAULT_SURFACES_VALUE, _set_surfaces_row, platform  # noqa: F401 -- imported for fixture re-export, pytest discovers by name
from test_surfaces_env import _control_main_module, _real_control_env  # noqa: F401
from r2db_api.control_main import assemble_control_stack  # noqa: E402

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
    # Phase 4 WP-2(b): `audit_query` declared `enabled` for this harness --
    # an in-memory reader over this SAME `audit` sink and `data_service`'s
    # own in-memory `application_audit` half (D-10), so this file's route-
    # table/authorization-matrix tests exercise the real PROVIDED branch
    # rather than a permanently-`unavailable` stub.
    audit_reader = InMemoryAuditQueryStore(audit, data_service._durable_audit)  # noqa: SLF001
    service = ControlPlaneService(backend, audit=audit, limits=limits or _GENEROUS_LIMITS, audit_reader=audit_reader, audit_visibility_lag_ms=0)
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
        # Phase 6 WP-2 (design D-1(c)): every caller of this harness uses
        # `.secret` as a `Bearer` value straight into `_auth()` -- the
        # composed locator form, not the raw secret half `.add`/`.rotate`
        # above were seeded with.
        secret=compose_bearer_locator(_SEED_CREDENTIAL_ID, _SEED_SECRET),
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
        # Phase 4 WP-2(b): `audit_requests_per_minute` joins the declared
        # set -- a real `ControlPlaneLimits` field now (its own separate
        # pre-auth window, `test_audit_query.py`).
        assert set(caps_doc["limits"]) == {"applications", "credentials_per_application", "control_requests_per_minute", "request_bytes", "audit_requests_per_minute"}
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


# ---------------------------------------------------------------------------
# WP-2(b) review M-4/M-5 (major, supervisor ruling 2026-09-03): the ONLY
# wire path `audit_query` has is `post_audit_query` (control_http.py) --
# the peer-local `test_audit_query.py` suite calls `ControlPlaneService.
# audit_query` directly, which never proves the HTTP HANDLER charges the
# right window at the right time. Mutation M7 (HTTP handler ALSO calls
# `service.check_rate()`) and M8b (the audit window moved to run AFTER
# `_authenticate`) both left every pre-existing test green -- these two
# tests close that gap by driving the real ASGI app.
# ---------------------------------------------------------------------------


async def test_audit_query_rate_limit_is_pre_auth_and_reaches_http_as_429():
    """M-5: `audit_requests_per_minute` is charged BEFORE authentication,
    on both wire paths -- mirrors `test_rate_limit_reaches_http_as_429_
    before_auth`'s own exact structure/assertions, but for `audit_query`'s
    own window (never `control_requests_per_minute`, which stays generous
    here so a regression collapsing the two windows together would not
    hide behind it)."""
    limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=1_000, audit_requests_per_minute=2)
    harness = _build_control_harness(limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        first = await client.post("/control/v1/audit/query")  # no Authorization header at all
        second = await client.post("/control/v1/audit/query")
        third = await client.post("/control/v1/audit/query")
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    body = third.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["resource"] == "audit_requests_per_minute"
    assert "audited" not in body["details"]


async def test_audit_query_wire_calls_never_consume_the_control_requests_per_minute_window():
    """M-4: driving `audit_query` over real HTTP, past `control_requests_
    per_minute`'s own (tight) ceiling, must never trip it -- and an
    ordinary control-window-charging endpoint must still have its full,
    untouched budget available afterward. Both paths (canonical + alias)
    exercised."""
    limits = ControlPlaneLimits(applications=1_000, credentials_per_application=1_000, control_requests_per_minute=2, audit_requests_per_minute=1_000)
    harness = _build_control_harness(limits)
    transport = httpx.ASGITransport(app=create_control_app(harness.service))
    headers = _auth(harness.secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        for path in ("/control/v1/audit/query", "/v1/audit/query"):
            for _ in range(10):
                response = await client.post(path, headers=headers, json={"limit": 1})
                assert response.status_code == 200, response.json()
        # `control_requests_per_minute` is still fresh (limit=2): exactly
        # 2 ordinary control calls succeed, the 3rd is refused -- proving
        # the 20 audit_query calls above spent nothing from this window.
        first = await client.get("/control/v1/capabilities", headers=headers)
        second = await client.get("/control/v1/capabilities", headers=headers)
        third = await client.get("/control/v1/capabilities", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["code"] == "LIMIT_EXCEEDED"
    assert third.json()["details"]["resource"] == "control_requests_per_minute"


async def test_audit_query_without_reader_answers_an_audit_role_credential_with_capability_unsupported_over_http():
    """WP-2(b) fix round 2 (coordinator item G), HTTP-level counterpart to
    `test_audit_query.py::test_audit_query_without_audit_dsn_refuses_with_
    capability_unsupported_not_404`'s own audit-role case: contract 1.4.0
    unconditional obligation (b)'s literal combination -- unavailable
    `audit_query` still answers an AUTHORIZED audit-role caller with
    `CAPABILITY_UNSUPPORTED` over the real wire, never `FORBIDDEN` (the
    role IS authorized) and never a bare 404 (the route is always
    registered)."""
    credentials = CredentialStore(pepper=PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    audit = ControlAuditSink()
    service = ControlPlaneService(backend, audit=audit, limits=_GENEROUS_LIMITS)  # no audit_reader at all
    audit_credential_id = "ctl_" + os.urandom(8).hex()
    audit_secret = "no-reader-http-audit-role-" + os.urandom(8).hex()
    with control_credentials.unit_of_work() as work:
        control_credentials.add(audit_credential_id, audit_secret, role="audit", work=work)
        control_credentials.rotate(audit_credential_id, audit_secret, work=work)

    transport = httpx.ASGITransport(app=create_control_app(service))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/audit/query", headers=_auth(compose_bearer_locator(audit_credential_id, audit_secret)), json={"limit": 1})
    assert response.status_code != 404
    assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"
    assert response.json()["code"] not in ("FORBIDDEN", "NOT_FOUND")


# ===========================================================================
# 7. Independence (work order §4 item 7): the two ASGI apps' route tables
#    never overlap, in either direction; an unknown path is 404.
# ===========================================================================


def test_control_and_data_plane_route_tables_are_disjoint(control_harness):
    control_app = create_control_app(control_harness.service)
    control_routes = control_app.app.routes  # RequestByteBoundMiddleware.app is the wrapped Starlette app
    # Phase 4 WP-2(b) (design D-5): 11 pre-existing control_endpoints + 2
    # audit_query paths (`/control/v1/audit/query` and its pre-1.4.0 alias).
    assert len(control_routes) == 13
    control_paths = {route.path for route in control_routes}
    # D-5's own ONE deliberate exception: `/v1/audit/query` is the pre-1.4.0
    # `endpoints.audit_query` path, aliased onto this control host too (see
    # `control_http.py`'s own module-level comment on `_ROUTES` for why) --
    # every other control-host path still starts with `/control/v1`.
    assert all(path.startswith("/control/v1") or path == "/v1/audit/query" for path in control_paths)

    data_credentials = CredentialStore(pepper="disjoint-check-pepper-0000")
    data_service = DataService(data_credentials)
    data_app = create_app(data_service)
    data_paths = {route.path for route in data_app.app.routes}

    assert not any(path.startswith("/control") for path in data_paths)
    # Both hosts legitimately serve the identical `/v1/audit/query` path
    # string (D-5) -- the data-plane's own copy stays its pre-existing
    # `CAPABILITY_UNSUPPORTED` stub (§8.1 vector 3: two hosts answering
    # differently for the same path is not a contradiction). Disjointness
    # therefore excludes this ONE shared path explicitly, rather than
    # silently weakening the general "no /v1/... path on the control host"
    # rule for anything else.
    assert not any(path.startswith("/v1") and path != "/v1/audit/query" for path in control_paths)
    assert "/v1/audit/query" in data_paths


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
#    failures, pepper-equality failure, a normal env returns an ASGI app,
#    and a module-level `app` exists (§8 m-10, flipped WP-5).
#
#    Q4 phase WP-1 REWORK ROUND (supervisor ruling 2026-09-05, rulings-q4-
#    wp12-rework.md sec.2): `build_control_app` is NO LONGER zero-network
#    -- design SS3.7's own startup-sequence DB-side checks (surfaces/
#    writer-role dual check) now run SYNCHRONOUSLY inside it, mirroring
#    `r2db_api.main.build_app`. The required-env and pepper-separation
#    checks below still run BEFORE any network access (moved ahead of the
#    DB read inside `build_control_app`, see that module's own docstring)
#    and so still pass with a placeholder, unreachable DSN (`_VALID_ENV`).
#    Tests that need `build_control_app` to actually SUCCEED (a normal env
#    returns a real app; the module-level `app`; the literal subprocess
#    entry point) now need a REAL, migrated platform database -- reused by
#    import from `test_credential_persistence.py`'s own `platform` fixture
#    (the same convention `test_surfaces_env.py` already established for
#    testing this exact module). `assemble_control_stack` itself remains
#    zero-network (its own constructors never connect eagerly) -- pinned
#    down directly, with explicit injected values, replacing the previous
#    round's env-driven `build_control_app(_VALID_ENV)` zero-network test.
# ===========================================================================

_VALID_ENV = {
    "R2DB_CONTROLPLANE_DSN": "host=/tmp port=1 dbname=r2db_control_http_test_unreachable",
    "R2DB_CONTROL_CREDENTIAL_PEPPER": "control-main-test-control-pepper-0000",
    "R2DB_CREDENTIAL_PEPPER": "control-main-test-app-pepper-0000",
    # Q4 phase WP-1 (design D-2(f)): `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_
    # BASE_URL` are REMOVED -- `build_control_app` rejects them outright
    # (F-2) if defined at all; neither is present here.
}


@pytest.fixture
def control_main_module():
    """CCR-14 WP-5: `r2db_api.control_main` ends with a module-level `app`
    (§8 m-10's flip) resolved LAZILY (rework round: a PEP 562 module
    `__getattr__`, `control_main.py`'s own tail -- necessary now that
    `build_control_app()` is network-dependent, see that module's own
    docstring) -- a bare `import r2db_api.control_main` no longer builds
    anything eagerly, but this fixture still sets a controlled environment
    via `pytest.MonkeyPatch` before each test's own first `import`/reload,
    mirroring `test_credential_persistence.py`'s own `main_module` fixture,
    so tests that DO touch `.app` (below) get a deterministic, per-test
    module object rather than depending on import order across the file.
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
    """Rework round: pepper-separation validation runs BEFORE the DB-side
    declaration read inside `build_control_app` (see that module's own
    docstring) -- a placeholder, unreachable `R2DB_CONTROLPLANE_DSN` must
    still surface THIS error, not a connection failure, proving the order
    is what the module claims."""
    env = dict(_VALID_ENV)
    env["R2DB_CREDENTIAL_PEPPER"] = env["R2DB_CONTROL_CREDENTIAL_PEPPER"]
    with pytest.raises(RuntimeError, match="must not be equal"):
        control_main_module.build_control_app(env)


def test_assemble_control_stack_returns_asgi_wireable_service_without_connecting():
    """Rework round replacement for the previous round's `test_build_
    control_app_returns_asgi_app_without_connecting` (rulings-q4-wp12-
    rework.md sec.2: "zero-network の既存テストは明示注入のassemble_
    control_stack(...)を使う形に書き換える") -- `build_control_app` itself
    is no longer zero-network (see this section's own header), but
    `assemble_control_stack` still is: `_RolePool.__init__` (postgres.py)
    never connects eagerly, so a bogus, unreachable DSN still returns a
    fully wireable `ControlPlaneService` when values are injected
    explicitly rather than read from `env`."""
    service, stores = assemble_control_stack(
        controlplane_dsn=_VALID_ENV["R2DB_CONTROLPLANE_DSN"],
        app_pepper=_VALID_ENV["R2DB_CREDENTIAL_PEPPER"],
        control_pepper=_VALID_ENV["R2DB_CONTROL_CREDENTIAL_PEPPER"],
    )
    try:
        app = create_control_app(service)
        assert app is not None
        assert hasattr(app, "app")  # RequestByteBoundMiddleware wrapping a Starlette app
        assert len(app.app.routes) == 13  # Phase 4 WP-2(b): 11 + audit_query's 2 paths
    finally:
        for store in stores:
            if store is not None:
                store.close()


def _real_env_for_control_main_module(platform: types.SimpleNamespace) -> dict[str, str]:
    env = _real_control_env(platform)
    env["R2DB_CONTROL_DSN"] = platform.control_dsn
    return env


def test_control_main_module_level_app_exists_and_is_asgi(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """§8 m-10's flip (WP-5): importing this module with a REAL, migrated
    platform database and then touching `.app` constructs a real module-
    level app, exactly like `r2db_api.main:app` already does. Rework round:
    `.app` is a PEP 562 lazy attribute, resolved (and, on the FIRST touch,
    cached) the moment something accesses it -- `hasattr`/plain attribute
    access below is that touch. `platform`'s own shared default `surfaces`
    row is control-LESS (matches `r2db_api.main`'s own default), but this
    module unconditionally requires `surfaces.control` (F-3c) -- seeded
    here, restored in `finally`.

    Uses pytest's own `monkeypatch` fixture (NOT a manually-constructed
    `pytest.MonkeyPatch()` undone by a helper before returning) -- `.app`
    access is now lazy (PEP 562 `__getattr__`, `control_main.py`'s own
    tail), so it happens INSIDE this test's own body, and the env must
    still be in effect at that point; `monkeypatch`'s own teardown runs
    only after this test function returns."""
    for key, value in _real_env_for_control_main_module(platform).items():
        monkeypatch.setenv(key, value)
    _set_surfaces_row(platform, {
        "data": {"base_url": "https://control-http-module-level-test.example.invalid/v1"},
        "control": {"base_url": "https://control-http-module-level-test.example.invalid/control/v1"},
    })
    try:
        import importlib
        import sys

        if "r2db_api.control_main" in sys.modules:
            module = importlib.reload(sys.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as module
        assert hasattr(module, "app")
        app = module.app
        assert app is not None
        assert hasattr(app, "app")  # RequestByteBoundMiddleware wrapping a Starlette app
        assert len(app.app.routes) == 13  # Phase 4 WP-2(b): 11 + audit_query's 2 paths
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_import_r2db_api_control_main_module_succeeds_with_valid_environment(platform: types.SimpleNamespace) -> None:
    # Mirrors `test_credential_persistence.py::
    # test_import_r2db_api_main_module_succeeds_with_valid_environment`: a
    # real `import` in a fresh subprocess (never polluting this pytest
    # process' own `sys.modules`/`control_main_module` fixture state),
    # proving the literal `r2db_api.control_main:app` ASGI-server entry
    # point actually works end to end -- now against a REAL, migrated
    # platform database (rework round: `build_control_app` is no longer
    # zero-network). See the sibling test above for why a control-
    # INCLUSIVE `surfaces` row must be seeded first.
    _set_surfaces_row(platform, {
        "data": {"base_url": "https://control-http-subprocess-import-test.example.invalid/v1"},
        "control": {"base_url": "https://control-http-subprocess-import-test.example.invalid/control/v1"},
    })
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC_DIR)
        env.update(_real_env_for_control_main_module(platform))
        script = "import r2db_api.control_main as m; assert m.app is not None; print('IMPORT_OK')"
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert "IMPORT_OK" in result.stdout
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_import_r2db_api_control_main_module_exits_nonzero_on_a_bad_declared_state(platform: types.SimpleNamespace) -> None:
    """N-4 (monitor ruling 2026-09-05, delta review §4/§6 point 2): the
    PEP 562 lazy `.app` attribute is justified only if a bad declared
    state still makes the PROCESS fail loudly -- the delta review's own
    "副次" concern is that a real ASGI server's `import_from_string`
    flattens an `AttributeError` raised while resolving `.app` into a
    generic "Attribute 'app' not found in module" that HIDES the real
    cause. This subprocess accesses `.app` against `platform`'s own
    DEFAULT `surfaces` row (deliberately control-LESS, per this file's
    sibling tests' own comments) with NO control surface seeded -- F-3c
    (`require_control_surface_declared`) must fire, propagate as a plain
    `RuntimeError` (not `AttributeError`), and exit this process non-zero
    with THAT message on stderr, not a generic "not found" one."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env.update(_real_env_for_control_main_module(platform))
    script = "import r2db_api.control_main as m; m.app"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "surfaces.control" in result.stderr, result.stderr
    assert "control-plane process, which always has a control surface" in result.stderr
    assert "Attribute 'app' not found" not in result.stderr
    assert "AttributeError" not in result.stderr


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
    context = data_service.authenticate(compose_bearer_locator("cred-single-commit", "secret-single-commit"))
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
    # Phase 4 WP-2(b) (design D-5): `audit_query` joins `_AUDIT_ROLE_
    # ALLOWED_OPERATIONS` -- both paths map to the SAME operation name.
    ("POST", "/control/v1/audit/query"): "audit_query",
    ("POST", "/v1/audit/query"): "audit_query",
}


async def test_audit_role_http_authorization_matrix_all_13_endpoints(control_harness):
    """Endpoint-by-endpoint audit-role authorization matrix, driven over
    real HTTP against every one of the 13 routes `_ROUTES` declares (§8
    risk 3: fail-closed completeness; Phase 4 WP-2(b) added `audit_query`'s
    own 2 paths to the original 11). The 3 pre-existing read-only routes
    PLUS `audit_query` (both its paths, m-4 rename) return 200 for an
    `audit`-role bearer; every other route returns 403 FORBIDDEN.

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
    audit_headers = _auth(compose_bearer_locator(audit_id, audit_secret))

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
            # Phase 4 WP-2(b): `audit_query` is read-only and now in the
            # allow-list -- 200 for BOTH paths (`control_harness` wires a
            # real in-memory `audit_reader`, so this is the genuine
            # PROVIDED branch, not a `CAPABILITY_UNSUPPORTED` stand-in).
            ("POST", "/control/v1/audit/query", {"limit": 1}, 200),
            ("POST", "/v1/audit/query", {"limit": 1}, 200),
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
