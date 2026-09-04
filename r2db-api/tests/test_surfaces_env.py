"""Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
V1.md D-2): `r2db_api.main`'s and `r2db_api.control_main`'s own
`R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_URL` startup-time SHAPE validation
(`_validate_surface_base_url`/`_surfaces` in each module), and the
`surfaces` object both processes' `capabilities()` publish from it.

This file's own `platform`/`provisioned_app`/`main_module` fixtures are
`test_credential_persistence.py`'s own module-scoped fixtures, reused by
import (a plain top-level `from test_credential_persistence import ...` --
`r2db-api/tests` carries no `__init__.py`, so sibling test modules are
importable by filename, the same convention `test_postgres.py`'s own
`make_cell` helper is reused by other files under) rather than duplicated:
importing `r2db_api.main` for the first time in this process is what
triggers its module-level `app = build_app()`, which needs a real,
reachable, fully-provisioned PostgreSQL platform database -- `main_module`
already carries that whole ceremony, and this file adds nothing to it
except its own module-scoped platform/schema (`scope="module"` fixtures
instantiate once PER IMPORTING MODULE, so this file gets its own
independent throwaway prefix, never colliding with test_credential_
persistence.py's).

`r2db_api.control_main.build_control_app`/`assemble_control_stack`, by
contrast, never connects to PostgreSQL eagerly (`control_main.py`'s own
module docstring, "No startup DSN reachability check") -- and the
`surfaces` check this WP added runs BEFORE `assemble_control_stack` is
ever called (`build_control_app`'s own body). So the control_main tests
below use entirely placeholder DSNs/peppers (never a real connection is
attempted before the surfaces check itself raises or succeeds) -- the same
"unreachable placeholder is fine, this path is zero-network" convention
`test_audit_query.py`'s own module-level `os.environ.setdefault(
"R2DB_CONTROLPLANE_DSN", "host=/tmp port=1 dbname=...")` already
establishes for this exact module.
"""
from __future__ import annotations

import importlib
import sys
import types
from typing import Iterator

import pytest

from test_credential_persistence import (  # noqa: F401 -- imported for fixture re-export, pytest discovers by name
    PEPPER,
    _main_env,
    main_module,
    platform,
    provisioned_app,
)

# --------------------------------------------------------------------------
# r2db_api.main -- R2DB_DATA_BASE_URL (always required) / R2DB_CONTROL_
# BASE_URL (required only when R2DB_CONTROL_PLANE_STATUS=enabled).
# --------------------------------------------------------------------------

_BAD_DATA_BASE_URLS = (
    ("relative", "/v1"),  # relative -- no scheme/host at all
    ("wrong-suffix", "https://r2db-surfaces-test.example.invalid/v2"),  # wrong terminal path
    ("trailing-slash", "https://r2db-surfaces-test.example.invalid/v1/"),  # correct suffix, extra trailing slash
)


@pytest.mark.parametrize("label,bad_url", _BAD_DATA_BASE_URLS)
def test_build_app_rejects_malformed_data_base_url(
    label: str, bad_url: str, platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_DATA_BASE_URL"] = bad_url
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        main_module.build_app(env=env)


def test_build_app_rejects_missing_data_base_url(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """The 4th malformed form (design D-2's own enumeration): absent
    entirely -- `surfaces.data` is an UNCONDITIONAL 1.6.0 obligation, so
    this is required regardless of `R2DB_CONTROL_PLANE_STATUS`."""
    env = _main_env(platform, provisioned_app)
    del env["R2DB_DATA_BASE_URL"]
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        main_module.build_app(env=env)


def test_build_app_accepts_a_well_formed_data_base_url_and_omits_control_when_unavailable(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """Positive control for the negative tests above, and design D-2's
    conditional-omission rule: `R2DB_CONTROL_PLANE_STATUS` defaults
    `unavailable` in `_main_env` -- `surfaces.control` must not be
    required (or read) in that case."""
    env = _main_env(platform, provisioned_app)  # R2DB_CONTROL_BASE_URL deliberately absent
    asgi_app = main_module.build_app(env=env)
    from starlette.testclient import TestClient

    with TestClient(asgi_app) as client:
        credential_id, secret = _issue_and_compose(platform, provisioned_app, main_module)
        response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {credential_id}.{secret}"})
        assert response.status_code == 200
        document = response.json()
        assert document["surfaces"] == {"data": {"base_url": env["R2DB_DATA_BASE_URL"]}}
        assert "control" not in document["surfaces"]


@pytest.mark.parametrize("label,bad_url", _BAD_DATA_BASE_URLS)
def test_build_app_rejects_malformed_control_base_url_when_control_plane_enabled(
    label: str, bad_url: str, platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    env["R2DB_CONTROL_BASE_URL"] = bad_url.replace("/v1", "/control/v1").replace("v2", "control/v2")
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        main_module.build_app(env=env)


def test_build_app_rejects_missing_control_base_url_when_control_plane_enabled(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        main_module.build_app(env=env)


def test_build_app_control_plane_enabled_publishes_both_surfaces(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    env["R2DB_CONTROL_BASE_URL"] = "https://r2db-surfaces-test-control.example.invalid/control/v1"
    asgi_app = main_module.build_app(env=env)
    from starlette.testclient import TestClient

    with TestClient(asgi_app) as client:
        credential_id, secret = _issue_and_compose(platform, provisioned_app, main_module)
        response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {credential_id}.{secret}"})
        assert response.status_code == 200
        document = response.json()
        assert document["surfaces"] == {
            "data": {"base_url": env["R2DB_DATA_BASE_URL"]},
            "control": {"base_url": env["R2DB_CONTROL_BASE_URL"]},
        }


def _issue_and_compose(platform, provisioned_app, main_module) -> tuple[str, str]:
    """Seeds a fresh application credential directly against the platform
    database (mirroring `test_credential_persistence.py`'s own convention)
    and returns `(credential_id, raw_secret)` -- the caller composes the
    locator bearer itself, exercising D-1's verbatim form over real HTTP
    at the same time as D-2's `surfaces`."""
    import secrets as _secrets

    from r2db_api.credential_store import PostgresCredentialStore

    store = PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)
    try:
        credential_id = "crd_" + _secrets.token_hex(8)
        secret = "surfaces-e2e-secret-" + _secrets.token_urlsafe(8)
        with store.unit_of_work() as work:
            store.add(credential_id, provisioned_app.slug, "runtime", secret, work=work)
    finally:
        store.close()
    return credential_id, secret


# --------------------------------------------------------------------------
# r2db_api.control_main -- both R2DB_DATA_BASE_URL and R2DB_CONTROL_BASE_URL
# are unconditionally required. Zero-network: no real Postgres needed (see
# module docstring).
# --------------------------------------------------------------------------

_CONTROL_ENV_BASE = {
    "R2DB_CONTROLPLANE_DSN": "host=/tmp port=1 dbname=r2db_surfaces_test_import_placeholder",
    "R2DB_CONTROL_CREDENTIAL_PEPPER": "r2db-surfaces-test-ctl-pepper",
    "R2DB_CREDENTIAL_PEPPER": "r2db-surfaces-test-app-pepper",
    "R2DB_DATA_BASE_URL": "https://r2db-control-main-surfaces-test.example.invalid/v1",
    "R2DB_CONTROL_BASE_URL": "https://r2db-control-main-surfaces-test.example.invalid/control/v1",
}

_BAD_CONTROL_BASE_URLS = (
    ("relative", "/control/v1"),
    ("wrong-suffix", "https://r2db-control-main-surfaces-test.example.invalid/control/v2"),
    ("trailing-slash", "https://r2db-control-main-surfaces-test.example.invalid/control/v1/"),
)


def _control_main_module() -> types.ModuleType:
    """Same safe-reload convention as `test_credential_persistence.py`'s
    own `main_module` fixture, for `r2db_api.control_main` -- imported
    lazily inside each test (not this module's own top level) so a bare
    `import test_surfaces_env` never itself triggers `control_main.py`'s
    module-level `app = build_control_app()` against whatever `os.environ`
    a fresh process happens to have.
    """
    mp = pytest.MonkeyPatch()
    for key, value in _CONTROL_ENV_BASE.items():
        mp.setenv(key, value)
    try:
        if "r2db_api.control_main" in sys.modules:
            module = importlib.reload(sys.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as module
        return module
    finally:
        mp.undo()


@pytest.mark.parametrize("label,bad_url", _BAD_CONTROL_BASE_URLS)
def test_build_control_app_rejects_malformed_control_base_url(label: str, bad_url: str) -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    env["R2DB_CONTROL_BASE_URL"] = bad_url
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        module.build_control_app(env=env)


def test_build_control_app_rejects_missing_control_base_url() -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    del env["R2DB_CONTROL_BASE_URL"]
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        module.build_control_app(env=env)


@pytest.mark.parametrize(
    "label,bad_url",
    (
        ("relative", "/v1"),
        ("wrong-suffix", "https://r2db-control-main-surfaces-test.example.invalid/v2"),
        ("trailing-slash", "https://r2db-control-main-surfaces-test.example.invalid/v1/"),
    ),
)
def test_build_control_app_rejects_malformed_data_base_url(label: str, bad_url: str) -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    env["R2DB_DATA_BASE_URL"] = bad_url
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        module.build_control_app(env=env)


def test_build_control_app_rejects_missing_data_base_url() -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    del env["R2DB_DATA_BASE_URL"]
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        module.build_control_app(env=env)


def test_control_main_validate_surface_base_url_accepts_the_well_formed_positive_control() -> None:
    """Positive control (no test above ever observes a SUCCESSFUL
    `_validate_surface_base_url` call in isolation, only through the full
    `build_control_app` failure paths) -- confirms the 4 malformed-shape
    tests above are rejecting for the right reason, not because nothing
    can ever pass this check."""
    module = _control_main_module()
    assert module._validate_surface_base_url("R2DB_DATA_BASE_URL", "https://ok.example.invalid/v1", suffix="/v1") == "https://ok.example.invalid/v1"  # noqa: SLF001
    assert module._validate_surface_base_url(  # noqa: SLF001
        "R2DB_CONTROL_BASE_URL", "https://ok.example.invalid/control/v1", suffix="/control/v1"
    ) == "https://ok.example.invalid/control/v1"


# --------------------------------------------------------------------------
# Coordinator item 7(ii) (reviewer O4, 2026-09-04 review): the two
# variables' suffix checks must be mutually exclusive -- R2DB_DATA_BASE_URL
# must reject a value ending `/control/v1` (it "ends with /v1" too, since
# "/control/v1" itself ends with the substring "/v1") and R2DB_CONTROL_
# BASE_URL must reject a bare `/v1`-only ending.
# --------------------------------------------------------------------------


def test_build_app_rejects_data_base_url_ending_in_control_v1(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_DATA_BASE_URL"] = "https://r2db-surfaces-test.example.invalid/control/v1"
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        main_module.build_app(env=env)


def test_build_app_rejects_control_base_url_ending_in_bare_v1(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    env["R2DB_CONTROL_BASE_URL"] = "https://r2db-surfaces-test.example.invalid/v1"
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        main_module.build_app(env=env)


def test_build_control_app_rejects_data_base_url_ending_in_control_v1() -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    env["R2DB_DATA_BASE_URL"] = "https://r2db-control-main-surfaces-test.example.invalid/control/v1"
    with pytest.raises(RuntimeError, match="R2DB_DATA_BASE_URL"):
        module.build_control_app(env=env)


def test_build_control_app_rejects_control_base_url_ending_in_bare_v1() -> None:
    module = _control_main_module()
    env = dict(_CONTROL_ENV_BASE)
    env["R2DB_CONTROL_BASE_URL"] = "https://r2db-control-main-surfaces-test.example.invalid/v1"
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_BASE_URL"):
        module.build_control_app(env=env)


# --------------------------------------------------------------------------
# Coordinator audit item (a): the data document and the control document's
# OWN `surfaces` agree, fixed over REAL HTTP against BOTH real ASGI apps
# (`main.build_app` and `control_main.build_control_app`), not merely
# through the shared `self._surfaces` dict both classes are constructed
# with in-process (`test_control_plane_service.py`'s own harness never
# builds a real `control_main` app at all). This is also the dedicated
# home for the work-order's own mutation 8 (breaking `control_plane.py`'s
# OWN control-document surfaces code) -- a DIFFERENT experiment from
# mutation 16 (which drops `surfaces.control` from the CONFORMANCE
# ADAPTER's own declared `_SURFACES`, never touching `control_plane.py`
# itself).
# --------------------------------------------------------------------------

CONTROL_PEPPER = "synthetic-test-pepper-surfaces-env-ctl-0000"


def test_data_and_control_documents_agree_on_surfaces_over_real_http(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    from starlette.testclient import TestClient

    from r2db_api.control_plane import bootstrap_control_credential
    from r2db_api.credential_store import PostgresControlAuditSink, PostgresControlCredentialStore

    data_base_url = "https://r2db-surfaces-agree-test.example.invalid/v1"
    control_base_url = "https://r2db-surfaces-agree-test-control.example.invalid/control/v1"

    data_env = _main_env(platform, provisioned_app)
    data_env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    data_env["R2DB_DATA_BASE_URL"] = data_base_url
    data_env["R2DB_CONTROL_BASE_URL"] = control_base_url
    data_app = main_module.build_app(env=data_env)

    control_module = _control_main_module()
    control_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": CONTROL_PEPPER,
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_DATA_BASE_URL": data_base_url,
        "R2DB_CONTROL_BASE_URL": control_base_url,
    }
    control_app = control_module.build_control_app(env=control_env)

    control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    control_audit = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)
    try:
        with control_store.unit_of_work() as work:
            _credential_id, control_bearer = bootstrap_control_credential(control_store, control_audit, work=work)
    finally:
        control_store.close()
        control_audit.close()

    with TestClient(data_app) as data_client, TestClient(control_app) as control_client:
        app_credential_id, app_secret = _issue_and_compose(platform, provisioned_app, main_module)
        data_response = data_client.get("/v1/capabilities", headers={"authorization": f"Bearer {app_credential_id}.{app_secret}"})
        assert data_response.status_code == 200
        control_response = control_client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {control_bearer}"})
        assert control_response.status_code == 200, control_response.text

        data_surfaces = data_response.json()["surfaces"]
        control_surfaces = control_response.json()["surfaces"]
        assert data_surfaces == control_surfaces == {
            "data": {"base_url": data_base_url},
            "control": {"base_url": control_base_url},
        }
