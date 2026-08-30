"""`control_main.build_control_app` / `control_composition.build_control_
service` (WP-5 flip, design v1.2 R-6/R-7/R-9) -- the literal
`uvicorn mitatedb_api.control_main:app` entry point, tested directly.

`control_composition.build_control_service` itself is ALSO reachable as
`mitatedb_api.main.build_control_service` (a re-export kept for
`test_main.py`'s own pre-existing call sites, WP-4) -- this file exercises
it via the NEW module directly, and additionally proves the ASGI-mounting
half (`control_http.create_control_app`) that `test_main.py` does not
touch at all.

`mitatedb_api.control_main` ends with a module-level `app = build_control_
app()`, which reads `os.environ` immediately on import (design v1.2 §8
m-10, mirroring `mitatedb_api.main`'s own identical `app = build_app()`
pattern) -- this file's own `control_main_module` fixture imports it
EXACTLY ONCE, with `os.environ` populated from a real, throwaway-
provisioned platform (`monkeypatch`, cleared automatically at teardown),
mirroring `test_main.py`'s own `main_module` fixture convention for the
identical reason. Every test then calls `control_main_module.build_
control_app` directly with its OWN explicit `env` dict -- never relying on
the cached module-level `app` object itself, which stays bound to
whichever env happened to be active on the very first import.
"""
from __future__ import annotations

import asyncio
import sys

import httpx
import pytest

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_composition import build_control_service
from mitatedb_api.control_plane import bootstrap_control_credential

BASE_URL = "http://mitatedb-control-main-test.invalid"

_APP_PEPPER = "control-main-test-app-pepper-00000"
_CONTROL_PEPPER = "control-main-test-ctl-pepper-00000"


def _env(control_platform, **overrides) -> dict[str, str]:
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
    }
    env.update(overrides)
    return env


@pytest.fixture
def control_main_module(control_platform, monkeypatch):
    """Imports `mitatedb_api.control_main` exactly once (cached in
    `sys.modules` for the rest of the process either way) with
    `os.environ` populated from a real, throwaway-provisioned platform,
    then returns the module object so tests can call its own
    `build_control_app` function directly with their own `env` dicts."""
    if "mitatedb_api.control_main" not in sys.modules:
        for key, value in _env(control_platform).items():
            monkeypatch.setenv(key, value)
        import mitatedb_api.control_main  # noqa: F401
    import mitatedb_api.control_main as control_main_module
    return control_main_module


@pytest.fixture(autouse=True)
def _clean_control_state(control_platform):
    import psycopg
    yield
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.control_audit")
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
    finally:
        conn.close()


def _run(coro):
    return asyncio.run(coro)


async def _aget(app, path, *, headers=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.get(path, headers=headers or {})


async def _apost(app, path, *, headers=None, json_body=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        if json_body is not None:
            return await client.post(path, json=json_body, headers=headers or {})
        return await client.post(path, headers=headers or {})


def test_build_control_app_missing_required_env_fails_loudly(control_main_module, control_platform) -> None:
    env = _env(control_platform)
    del env["MITATEDB_CONTROLPLANE_DSN"]
    with pytest.raises(RuntimeError, match="MITATEDB_CONTROLPLANE_DSN"):
        control_main_module.build_control_app(env)


def test_build_control_app_rejects_identical_peppers(control_main_module, control_platform) -> None:
    # `assert_pepper_separation` raises `ValueError` directly (a
    # configuration error, not a `RuntimeError` "missing env" failure) --
    # matches `test_main.py::test_control_service_factory_rejects_
    # identical_peppers`'s own identical expectation for the SAME
    # underlying `control_composition.build_control_service` call.
    env = _env(control_platform, MITATEDB_CONTROL_CREDENTIAL_PEPPER=_APP_PEPPER)
    with pytest.raises(ValueError):
        control_main_module.build_control_app(env)


def test_build_control_app_mounts_a_real_working_control_v1_surface(control_main_module, control_platform) -> None:
    """End-to-end proof that `control_main.build_control_app` (the literal
    uvicorn entry point) produces a genuinely working `/control/v1`
    surface -- not merely that `build_control_service` alone works
    (`test_main.py`'s own pre-existing coverage), and not merely that
    `control_http.create_control_app` alone works against a hand-built
    service (`test_control_http_unmounted.py`'s own WP-4 coverage). This
    is the one test exercising the actual composition WP-5 adds."""
    app = control_main_module.build_control_app(_env(control_platform))

    # Bootstrap out-of-band (the ceremony core directly, mirroring what
    # `python -m mitatedb_api.ops bootstrap` does against the SAME
    # PostgreSQL platform) -- this app has no bootstrap endpoint of its
    # own by contract.
    service = build_control_service(_env(control_platform))
    backend = service._backend  # test-only reach-in, mirrors test_main.py's own convention
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)

    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {credential_id}.{secret}"}))
    assert rotate_resp.status_code == 200, rotate_resp.text
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {credential_id}.{secret}"}

    caps_resp = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.status_code == 200, caps_resp.text
    document = caps_resp.json()
    assert document["capabilities"]["control_plane"]["status"] == "enabled"
    # R-6: `request_bytes` is declared `enforced` from the very first
    # commit that mounts anything at all (m-10) -- real enforcement, same
    # commit as the mount itself (`control_http.RequestByteBoundMiddleware`,
    # sized from THIS service's own `limits.request_bytes`, R-6/control_
    # main.py's own module docstring).
    assert document["limit_enforcement"]["request_bytes"] == "enforced"

    register_resp = _run(_apost(app, "/control/v1/applications", headers=auth_header,
                                json_body={"application_id": "controlmainapp"}))
    assert register_resp.status_code == 200, register_resp.text
    assert register_resp.json() == {"application_id": "controlmainapp", "enabled": True}

    issue_resp = _run(_apost(app, "/control/v1/credentials", headers=auth_header,
                             json_body={"application_id": "controlmainapp", "role": "runtime"}))
    assert issue_resp.status_code == 200, issue_resp.text
    assert issue_resp.json()["role"] == "runtime"


def test_build_control_app_request_bytes_limit_matches_the_declared_one(control_main_module, control_platform) -> None:
    """R-7: "宣言値と enforce 値が同一ソースから出ることを構造で保証する" --
    a custom `MITATEDB_CONTROL_REQUEST_BYTES_LIMIT` really changes what the
    ASGI middleware enforces, not only what `control_capabilities()`
    reports."""
    env = _env(control_platform, MITATEDB_CONTROL_REQUEST_BYTES_LIMIT="256")
    app = control_main_module.build_control_app(env)

    service = build_control_service(env)
    backend = service._backend
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {credential_id}.{secret}"}))
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {credential_id}.{secret}"}

    caps_resp = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.json()["limits"]["request_bytes"] == 256

    oversized = {"application_id": "a" * 1024}
    response = _run(_apost(app, "/control/v1/applications", headers=auth_header, json_body=oversized))
    assert response.status_code == 413
    assert response.json()["code"] == "LIMIT_EXCEEDED"
