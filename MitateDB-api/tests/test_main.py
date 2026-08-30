"""Tests for the composition root `mitatedb_api.main.build_app` (WP-3).

Reuses `test_postgres.py`'s own `platform` fixture and `provision_app`
helper (a plain Python import, matching `test_http.py`'s identical choice
and rationale; see that file's own docstring) -- but deliberately does
NOT use `test_postgres.py`'s own `app_a`/`app_b` fixtures (which reuse the
FIXED name "iso_a"/"iso_b" and deprovision it again after every single
test function). `mitatedb_api.main` ends with a module-level
`app = build_app()` (the same shape r2db-api's own `r2db_api.main` uses),
and this file's own `main_module` fixture triggers that module-level call
exactly ONCE per test process by importing it. That ONE real composition
holds two PERSISTENT `PostgresBackend` connections against whichever
application it served for the rest of the process' life (nothing in this
file drives the ASGI lifespan-shutdown event that would release them) --
reusing "iso_a" for this would make every LATER test in this whole session
that provisions/deprovisions "iso_a" (including `test_postgres.py`'s own
tests, and `test_http.py`'s `app_a_stack` fixture, if collected in the
same session) fail to drop that database at teardown ("... is being
accessed by other users"). This file therefore provisions its OWN,
separately-named, dedicated application (`main_import_probe`) that no
other test file ever touches, and never explicitly deprovisions it either
(the leaked connections would only make that attempt fail loudly) --
`platform`'s own module-scoped teardown (`_sweep_prefix`) drops every
database under this run's throwaway prefix regardless of explicit
deprovisioning, so this is not real residue.
"""
from __future__ import annotations

import sys

import httpx
import pytest

from mitatedb_api.auth import Role
from mitatedb_api.credential_store_postgres import PostgresCredentialStore

# A RELATIVE import: see `test_http.py`'s own identical comment for why a
# bare `from test_postgres import ...` is unsafe under the combined root
# suite (r2db-api's own, differently-shaped `test_postgres.py` occupies
# the bare `sys.modules["test_postgres"]` name first).
from .test_postgres import platform, provision_app  # noqa: F401

BASE_URL = "http://mitatedb-main-test.invalid"

_PEPPER = "synthetic-test-pepper-mitatedb-main-0000"
_CONTROL_PEPPER = "synthetic-test-pepper-mitatedb-main-ctl-0000"
_PROBE_APP_ID = "main_import_probe"


def _base_env(platform, probe_app) -> dict[str, str]:
    return {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": probe_app.app_id,
        f"MITATEDB_APP_{probe_app.app_id.upper()}_RUNTIME_DSN": probe_app.runtime_dsn,
        f"MITATEDB_APP_{probe_app.app_id.upper()}_DEVELOPER_DSN": probe_app.developer_dsn,
    }


@pytest.fixture(scope="module")
def probe_app(platform):
    """This file's own dedicated, never-deprovisioned application (see
    this module's own docstring for why) -- module-scoped so every test
    in this file shares the same one, and the module-scoped `platform`
    fixture's own final sweep is what actually removes it."""
    return provision_app(platform, _PROBE_APP_ID)


@pytest.fixture
def main_module(platform, probe_app, monkeypatch):
    """Imports `mitatedb_api.main` exactly once (cached in `sys.modules`
    for the rest of the process either way) with `os.environ` populated
    from `probe_app`, then returns the module object so tests can call its
    `build_app` function directly with their own `env` dicts."""
    if "mitatedb_api.main" not in sys.modules:
        for key, value in _base_env(platform, probe_app).items():
            monkeypatch.setenv(key, value)
        import mitatedb_api.main  # noqa: F401
    import mitatedb_api.main as main_module
    return main_module


def test_build_app_fails_loudly_when_pepper_missing(main_module, platform, probe_app):
    env = _base_env(platform, probe_app)
    del env["MITATEDB_CREDENTIAL_PEPPER"]
    with pytest.raises(RuntimeError, match="MITATEDB_CREDENTIAL_PEPPER"):
        main_module.build_app(env)


def test_build_app_fails_loudly_when_served_app_not_registered(main_module, platform, probe_app):
    env = _base_env(platform, probe_app)
    env["MITATEDB_SERVE_APPS"] = "totally_unregistered_app_id"
    # Its own DSN env vars must still be present, or `build_app` raises
    # for that (earlier-checked) reason instead of exercising the
    # registry-lookup failure this test targets.
    env["MITATEDB_APP_TOTALLY_UNREGISTERED_APP_ID_RUNTIME_DSN"] = probe_app.runtime_dsn
    env["MITATEDB_APP_TOTALLY_UNREGISTERED_APP_ID_DEVELOPER_DSN"] = probe_app.developer_dsn
    with pytest.raises(RuntimeError, match="not registered"):
        main_module.build_app(env)


def test_build_app_rejects_identical_peppers(main_module, platform, probe_app):
    env = _base_env(platform, probe_app)
    env["MITATEDB_CONTROL_CREDENTIAL_PEPPER"] = env["MITATEDB_CREDENTIAL_PEPPER"]
    with pytest.raises(ValueError):
        main_module.build_app(env)


def test_build_app_serves_a_real_authenticated_request(main_module, platform, probe_app):
    # Reuses the SAME app object the module-level `app = build_app()` call
    # already built at import time (calling `build_app()` a second time
    # here would leak a SECOND pair of persistent connections against the
    # same probe application for no additional coverage).
    app = main_module.app

    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema,
    )
    try:
        credential_id, secret = write_store.issue(probe_app.app_id, Role.RUNTIME)
    finally:
        write_store.close()

    import asyncio

    async def _call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {credential_id}.{secret}"})

    response = asyncio.run(_call())
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["application_scope"] == probe_app.app_id
    assert document["role"] == "runtime"
    assert document["limit_enforcement"]["request_bytes"] == "enforced"
