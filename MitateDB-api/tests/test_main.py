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


# --------------------------------------------------------------------------
# WP-4 (design v1.2 R-7): the control plane is built (`control_plane.py`/
# `control_http.py`) but must NEVER be mounted anywhere in this WP's public
# composition -- "declared-unavailable form (b) の状態を一瞬も経由しない".
# Kept in THIS file (not a separate test module) deliberately: `main_module`
# is a process-wide singleton import keyed to the module-scoped `platform`/
# `probe_app` fixtures ABOVE -- a second test file importing `main_module`
# via its OWN, differently-prefixed `platform`/`probe_app` would trigger a
# second, independent `import mitatedb_api.main` bound to a throwaway
# database that file's own teardown then drops, leaving whichever test file
# runs later holding a dead connection (confirmed empirically while writing
# this test: exactly this cross-file collision produced a spurious
# `AUTH_STATE_UNAVAILABLE` in `test_build_app_serves_a_real_authenticated_
# request` above when these checks first lived in their own module).
def test_main_composition_root_mounts_no_control_v1_route(main_module) -> None:
    inner = main_module.app.app  # `http.RequestByteBoundMiddleware.app` is the real Starlette app
    paths = [route.path for route in inner.routes]
    assert not any(path.startswith("/control/v1") for path in paths), (
        f"main.py's own composition root must not mount /control/v1 in WP-4; found: {paths}"
    )


def test_build_app_never_references_the_control_plane_at_all(main_module) -> None:
    """`build_app` (the function that actually produces the module-level
    `app` object `uvicorn mitatedb_api.main:app` serves) must not import,
    construct, or call anything control-plane-shaped -- checked at the
    function-source level, not the whole module, because the module ALSO
    defines `build_control_service` (design v1.2 §3 WP-4 row instruction
    #6: "control 用 factory は用意するが公開 serve には出さない") which
    legitimately references `control_plane`/`control_credential_store_
    postgres` -- that factory is prepared for WP-5 to call, but `build_app`
    itself must never reach it or any of its own dependencies."""
    import inspect

    source = inspect.getsource(main_module.build_app)
    forbidden_snippets = (
        "control_http", "control_plane", "ControlPlaneService", "create_control_app", "build_control_service",
    )
    for forbidden in forbidden_snippets:
        assert forbidden not in source, (
            f"build_app must not reference {forbidden!r} in WP-4 (the mount is a single WP-5 commit)"
        )


def test_control_service_factory_exists_but_is_never_called_at_import_time(main_module) -> None:
    """Positive half of the same guarantee: `build_control_service`
    (design v1.2 §3 WP-4 row instruction #6) is real, present, importable
    code -- not merely planned -- but the module-level `app = build_app()`
    statement that runs at import time never calls it (confirmed by the
    test immediately above: `build_app`'s own source has zero reference to
    it), so importing `mitatedb_api.main` alone (as every application-plane
    test in this file already does) never constructs a control-plane
    backend or opens a `MITATEDB_CONTROLPLANE_DSN` connection."""
    assert callable(main_module.build_control_service)
    import inspect

    signature = inspect.signature(main_module.build_control_service)
    assert "env" in signature.parameters


def test_control_service_factory_builds_a_real_working_service(main_module, platform) -> None:
    """The factory is not merely present -- calling it with real env
    produces a genuinely working `control_plane.ControlPlaneService`
    against the SAME throwaway PostgreSQL platform every other test in this
    file already bootstrapped (`platform.controlplane_dsn`), independent of
    whatever application(s) `main_module`'s own `app` happens to be serving."""
    from mitatedb_api.control_plane import bootstrap_control_credential

    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
    }
    service = main_module.build_control_service(env)

    backend = service._backend  # test-only reach-in, mirroring this file's own existing conventions
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    try:
        rotated = service.rotate_credential(credential_id, secret, credential_id)
        document = service.control_capabilities(credential_id, rotated["secret"])
        assert document["capabilities"]["control_plane"]["status"] == "enabled"
    finally:
        # Clean up so this factory-only credential does not linger in the
        # shared throwaway platform for the rest of the test session.
        import psycopg
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
        finally:
            conn.close()


def test_control_service_factory_rejects_identical_peppers(main_module, platform) -> None:
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
    }
    with pytest.raises(ValueError):
        main_module.build_control_service(env)
