"""Direct tests for `control_http.create_control_app` -- WP-4's own "全て
直接テスト" scope: this proves the control app itself is real, working
code (httpx + ASGITransport, no mount, no PostgreSQL dependency -- an
`InMemoryControlBackend` suffices for exercising the ASGI layer itself).

The COMPLEMENTARY regression test -- that `mitatedb_api.main`'s own public
composition mounts no `/control/v1` route at all, and that `main.py`'s own
source never imports this module or `control_plane.py` -- lives in
`test_main.py` instead (see that file's own comment on why: those checks
need `main_module`/`platform`/`probe_app`, and a SECOND test file importing
those same-named fixtures would bootstrap a SECOND, independent throwaway
PostgreSQL platform, confirmed empirically to collide with `test_main.py`'s
own real-request test once its own module-scoped teardown ran first).
"""
from __future__ import annotations

import json

import httpx
import pytest

from mitatedb_api.application_audit import ApplicationAuditSink
from mitatedb_api.audit_query import InMemoryAuditQueryStore
from mitatedb_api.control_http import _ROUTES, create_control_app
from mitatedb_api.control_plane import (_AUDIT_ROLE_ALLOWED_OPERATIONS, ControlPlaneLimits,
                                        ControlPlaneService, InMemoryControlBackend,
                                        bootstrap_control_credential)

BASE_URL = "http://mitatedb-control-test.invalid"
_APP_PEPPER = "control-http-unmounted-app-pepper-x"
_CONTROL_PEPPER = "control-http-unmounted-ctl-pepper-x"


def _service_with_bootstrapped_credential():
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    # Phase 4 WP-3(b) (design D-5): a real in-memory `audit_query` reader --
    # this file's own audit-role matrix test needs `audit_query` to
    # genuinely be `enabled` (not `unavailable`) so an authorized audit-role
    # request reaches 200, not `CAPABILITY_UNSUPPORTED`.
    audit_reader = InMemoryAuditQueryStore(backend.audit_sink, ApplicationAuditSink())
    service = ControlPlaneService(
        backend, limits=ControlPlaneLimits(applications=5, credentials_per_application=2, control_requests_per_minute=90),
        audit_reader=audit_reader, audit_visibility_lag_ms=0,
    )
    return service, credential_id, secret


@pytest.fixture
def control_app():
    service, credential_id, secret = _service_with_bootstrapped_credential()
    app = create_control_app(service, request_bytes_limit=1_048_576)
    return app, credential_id, secret


def _run(coro):
    """`httpx.ASGITransport` only implements the async context-manager
    protocol -- mirrors `test_http.py`'s own identical `_run`/`asyncio.run`
    bridge, independently applied here for this file's own requests."""
    import asyncio

    return asyncio.run(coro)


def _auth_header(credential_id: str, secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential_id}.{secret}"}


async def _apost(app, path, *, headers=None, json_body=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        if json_body is not None:
            return await client.post(path, json=json_body, headers=headers or {})
        return await client.post(path, headers=headers or {})


async def _aget(app, path, *, headers=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.get(path, headers=headers or {})


def test_control_capabilities_declares_control_plane_enabled_and_request_bytes_enforced(control_app) -> None:
    app, credential_id, secret = control_app
    # must_rotate is still true right after bootstrap -- capabilities is on
    # the must_rotate allow-list.
    response = _run(_aget(app, "/control/v1/capabilities", headers=_auth_header(credential_id, secret)))
    assert response.status_code == 200
    body = response.json()
    assert body["capabilities"]["control_plane"]["status"] == "enabled"
    assert body["limit_enforcement"]["request_bytes"] == "enforced"


def test_missing_bearer_token_is_auth_required(control_app) -> None:
    app, _credential_id, _secret = control_app
    response = _run(_aget(app, "/control/v1/capabilities"))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
    assert response.headers["content-type"].startswith("application/problem+json")


def test_full_register_issue_list_flow_over_real_http(control_app) -> None:
    app, credential_id, secret = control_app
    # Clear must_rotate first via self-rotate over HTTP.
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate", headers=_auth_header(credential_id, secret)))
    assert rotate_resp.status_code == 200
    secret = rotate_resp.json()["secret"]

    register_resp = _run(_apost(app, "/control/v1/applications", headers=_auth_header(credential_id, secret),
                                json_body={"application_id": "httpapp"}))
    assert register_resp.status_code == 200
    assert register_resp.json() == {"application_id": "httpapp", "enabled": True}

    issue_resp = _run(_apost(app, "/control/v1/credentials", headers=_auth_header(credential_id, secret),
                             json_body={"application_id": "httpapp", "role": "runtime"}))
    assert issue_resp.status_code == 200
    issued = issue_resp.json()
    assert issued["role"] == "runtime"

    listing_resp = _run(_aget(app, "/control/v1/credentials", headers=_auth_header(credential_id, secret)))
    assert listing_resp.status_code == 200
    ids = {row["credential_id"] for row in listing_resp.json()["credentials"]}
    assert issued["credential_id"] in ids


def test_body_entity_smuggling_is_rejected_as_unknown_field(control_app) -> None:
    app, credential_id, secret = control_app
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate", headers=_auth_header(credential_id, secret)))
    secret = rotate_resp.json()["secret"]
    response = _run(_apost(app, "/control/v1/applications", headers=_auth_header(credential_id, secret),
                           json_body={"application_id": "shapeapp", "unexpected_extra_field": True}))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# SI-10: an error response never leaks the underlying exception's own text --
# the control-plane surface's own counterpart to `test_http.py`'s
# `test_problem_response_never_leaks_the_underlying_exception_message`. That
# app-plane test exercises the leak-proof renderer (`_problem_for_exception`)
# in isolation; this one drives a REAL request through the mounted
# `/control/v1` ASGI app so the whole `_endpoint`/`except Exception:` ->
# `_generic_service_unavailable` path is covered end to end: an UNCLASSIFIED
# raw exception (not a `FoundationError`, so it never reaches `_classify` at
# all) raised from inside a backend method must collapse to the generic
# `SERVICE_UNAVAILABLE` problem+json body, carrying NONE of the raw
# exception's own message text.
# ---------------------------------------------------------------------------


def test_control_problem_response_never_leaks_the_underlying_exception_message(control_app, monkeypatch) -> None:
    app, credential_id, secret = control_app
    # A raw `RuntimeError` (deliberately NOT a `FoundationError`) injected
    # into a backend method reached on every request's authentication step,
    # planting secret-shaped text into its own message the way a real driver
    # error would (a table/column name, a connection host). `_endpoint`'s
    # `except Exception:` catches it and returns `_generic_service_
    # unavailable`, whose message comes from the fixed per-CODE string table
    # -- never from `str(exc)`.
    marker = "control-internal-detail-leak-marker-4a7e2b"
    service = app.app.state.control_service  # RequestByteBoundMiddleware -> inner Starlette app

    def _raise(*_args, **_kwargs):
        raise RuntimeError(f"control store rejected credential {marker} at connection host 10.0.0.5")

    monkeypatch.setattr(service._backend, "authenticate_control", _raise)

    response = _run(_aget(app, "/control/v1/capabilities", headers=_auth_header(credential_id, secret)))
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert marker not in body["message"]
    assert marker not in json.dumps(body)


def test_revoke_last_active_control_credential_requires_confirmation_over_http(control_app) -> None:
    app, credential_id, secret = control_app
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate", headers=_auth_header(credential_id, secret)))
    secret = rotate_resp.json()["secret"]
    denial = _run(_apost(app, f"/control/v1/credentials/{credential_id}/revoke", headers=_auth_header(credential_id, secret)))
    assert denial.status_code == 409
    body = denial.json()
    assert body["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    phrase = body["details"]["required_confirmation"]

    confirmed = _run(_apost(app, f"/control/v1/credentials/{credential_id}/revoke", headers=_auth_header(credential_id, secret),
                            json_body={"destructive": True, "confirmation": phrase}))
    assert confirmed.status_code == 200
    assert confirmed.json()["revoked"] is True


# ===========================================================================
# Phase 3.5 WP-5 control-plane bundle (design docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4): audit-role HTTP
# authorization matrix (§1-D, structural completeness), issuance freeze
# over real HTTP (§1-E).
# ===========================================================================


def _seed_audit_credential_over_backend(service, *, must_rotate: bool = False):
    store = service._backend.control_credential_store  # noqa: SLF001 -- test-only direct seed
    with service._backend.unit_of_work() as work:  # noqa: SLF001
        credential_id, secret = store.issue(must_rotate=must_rotate, role="audit", work=work)
    return credential_id, secret


# The operation name each route maps to -- a second, independent source
# (alongside `matrix` below) this test cross-checks BOTH against
# `control_http._ROUTES` (the wire boundary's own route table) AND against
# `control_plane._AUDIT_ROLE_ALLOWED_OPERATIONS` (the product code's own
# allow-list), so a future route added to either the route table or the
# allow-list without a corresponding update here fails the structural-
# completeness assertion below, rather than silently never being exercised.
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
    # Phase 4 WP-3(b) (design D-5): `audit_query`'s own 2 paths -- both
    # resolve to the SAME handler and the SAME operation name, so an
    # `audit`-role bearer is accepted on either.
    ("POST", "/control/v1/audit/query"): "audit_query",
    ("POST", "/v1/audit/query"): "audit_query",
}


def test_audit_role_http_authorization_matrix_all_13_routes(control_app) -> None:
    """Endpoint-by-endpoint audit-role authorization matrix, driven over
    real HTTP against every one of the 13 routes `_ROUTES` declares (fail-
    closed completeness; Phase 4 WP-3(b) added `audit_query`'s own 2 paths
    to the original 11). The 5 read-only routes (the original 3 plus
    `audit_query`'s 2 paths) return 200 for an `audit`-role bearer; every
    other route returns 403 FORBIDDEN.

    Structurally complete, not a hand-maintained list a future 10th route
    could silently bypass -- the set of (method, route-template) pairs this
    test exercises is asserted equal to `control_http._ROUTES` itself (a
    route added there with no entry here fails immediately), and the
    derived "allowed" subset is asserted equal to `control_plane._AUDIT_
    ROLE_ALLOWED_OPERATIONS` (the product code's own allow-list, imported
    directly rather than re-typed as a literal).
    """
    app, credential_id, secret = control_app
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate", headers=_auth_header(credential_id, secret)))
    secret = rotate_resp.json()["secret"]

    service = app.app.state.control_service  # RequestByteBoundMiddleware -> inner Starlette app
    audit_id, audit_secret = _seed_audit_credential_over_backend(service)
    audit_headers = _auth_header(audit_id, audit_secret)

    register_resp = _run(_apost(app, "/control/v1/applications", headers=_auth_header(credential_id, secret),
                                json_body={"application_id": "app_audit_matrix"}))
    assert register_resp.status_code == 200
    issue_resp = _run(_apost(app, "/control/v1/credentials", headers=_auth_header(credential_id, secret),
                             json_body={"application_id": "app_audit_matrix", "role": "runtime"}))
    assert issue_resp.status_code == 200
    target_credential_id = issue_resp.json()["credential_id"]

    # (method, route-template, body-or-None, expected status) -- one entry
    # per key in `_ROUTE_OPERATION_NAMES`.
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
        ("POST", "/control/v1/audit/query", {"limit": 1}, 200),
        ("POST", "/v1/audit/query", {"limit": 1}, 200),
    ]
    matrix_keys = {(method, template) for method, template, _body, _status in matrix}

    # (1) `_ROUTE_OPERATION_NAMES`'s own keys must match `_ROUTES` exactly.
    route_keys = {(method, route.path) for route in _ROUTES for method in (route.methods - {"HEAD"})}
    assert set(_ROUTE_OPERATION_NAMES) == route_keys, (
        f"_ROUTE_OPERATION_NAMES does not match control_http._ROUTES: "
        f"missing={route_keys - set(_ROUTE_OPERATION_NAMES)} extra={set(_ROUTE_OPERATION_NAMES) - route_keys}"
    )
    # (2) this test's own `matrix` must cover every one of those routes.
    assert matrix_keys == route_keys, (
        f"matrix does not cover control_http._ROUTES exactly: "
        f"missing={route_keys - matrix_keys} extra={matrix_keys - route_keys}"
    )
    # (3) the "allowed" subset this matrix expects (status 200) must equal
    # the product code's own `_AUDIT_ROLE_ALLOWED_OPERATIONS` allow-list.
    allowed_keys = {(m, t) for m, t, _b, status in matrix if status == 200}
    denied_keys = {(m, t) for m, t, _b, status in matrix if status == 403}
    assert allowed_keys | denied_keys == matrix_keys
    allowed_operations = {_ROUTE_OPERATION_NAMES[key] for key in allowed_keys}
    assert allowed_operations == _AUDIT_ROLE_ALLOWED_OPERATIONS

    for method, template, body, expected_status in matrix:
        path = template.format(application_id="app_audit_matrix", credential_id=target_credential_id)
        if method == "GET":
            response = _run(_aget(app, path, headers=audit_headers))
        else:
            response = _run(_apost(app, path, headers=audit_headers, json_body=body))
        assert response.status_code == expected_status, f"{method} {path}: expected {expected_status}, got {response.status_code} ({response.text})"
        if expected_status == 403:
            assert response.json()["code"] == "FORBIDDEN"

    # The audit credential itself was never touched by any of the 8
    # refused attempts above -- still enabled, not revoked (confirmed by a
    # 4th read).
    still_alive = _run(_aget(app, "/control/v1/capabilities", headers=audit_headers))
    assert still_alive.status_code == 200
    assert still_alive.json()["role"] == "audit"


def test_issuance_freeze_forbidden_over_http_then_unfreeze_allows_again(control_app) -> None:
    """Freeze has no in-band HTTP toggle (design §1-E, P35-D6 -- CLI only);
    this test flips the flag directly at the backend level (as `ops.py
    freeze-issuance`/`unfreeze-issuance` do out-of-band) and confirms the
    in-band `issue_credential` endpoint refuses/allows accordingly."""
    app, credential_id, secret = control_app
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate", headers=_auth_header(credential_id, secret)))
    secret = rotate_resp.json()["secret"]
    headers = _auth_header(credential_id, secret)

    register_resp = _run(_apost(app, "/control/v1/applications", headers=headers, json_body={"application_id": "app_freeze_http"}))
    assert register_resp.status_code == 200

    service = app.app.state.control_service  # RequestByteBoundMiddleware -> inner Starlette app
    with service._backend.unit_of_work() as work:  # noqa: SLF001
        service._backend.set_application_issuance_frozen("app_freeze_http", True, work=work)  # noqa: SLF001

    denied = _run(_apost(app, "/control/v1/credentials", headers=headers, json_body={"application_id": "app_freeze_http", "role": "runtime"}))
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    with service._backend.unit_of_work() as work:  # noqa: SLF001
        service._backend.set_application_issuance_frozen("app_freeze_http", False, work=work)  # noqa: SLF001

    allowed = _run(_apost(app, "/control/v1/credentials", headers=headers, json_body={"application_id": "app_freeze_http", "role": "runtime"}))
    assert allowed.status_code == 200
