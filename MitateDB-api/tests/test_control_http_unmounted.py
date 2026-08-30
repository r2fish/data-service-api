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

import httpx
import pytest

from mitatedb_api.control_http import create_control_app
from mitatedb_api.control_plane import ControlPlaneLimits, ControlPlaneService, InMemoryControlBackend, bootstrap_control_credential

BASE_URL = "http://mitatedb-control-test.invalid"
_APP_PEPPER = "control-http-unmounted-app-pepper-x"
_CONTROL_PEPPER = "control-http-unmounted-ctl-pepper-x"


def _service_with_bootstrapped_credential():
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=ControlPlaneLimits(
        applications=5, credentials_per_application=2, control_requests_per_minute=90))
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
