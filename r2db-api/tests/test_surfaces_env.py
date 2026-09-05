"""Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
V1.md D-2): `r2db_api.main`'s and `r2db_api.control_main`'s own `surfaces`
startup-time SHAPE validation, and the `surfaces` object both processes'
`capabilities()` publish from it.

Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-2, work
order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1):
`surfaces` is no longer an env var -- it is a DB-side declaration
(`<registry>.platform_declarations`, migration `0008`) both processes read
at startup. Every test below that used to manipulate `R2DB_DATA_BASE_URL`/
`R2DB_CONTROL_BASE_URL` now manipulates the shared `platform` fixture's
`platform_declarations` row directly (`_set_surfaces_row`, `test_credential_
persistence.py`) -- the "hand-edited row" scenario design D-2(d) itself
anticipates ("この表は手で編集され得るため...書き込み時と読み出し時の両方"),
which is exactly what these tests now exercise for the READ side.

This file's own `platform`/`provisioned_app`/`main_module` fixtures are
`test_credential_persistence.py`'s own module-scoped fixtures, reused by
import (see that file's own fixtures for the full rationale) -- Q4 WP-1
extends `platform` to also apply migration `0008` and seed a default
`surfaces` row (`_DEFAULT_SURFACES_VALUE`, control-less, matching `R2DB_
CONTROL_PLANE_STATUS` defaulting `unavailable`).

`r2db_api.control_main.build_control_app` is NO LONGER zero-network as of
the Q4 WP-1 REWORK round (supervisor ruling 2026-09-05, rulings-q4-wp12-
rework.md sec.2, superseding this file's own earlier assumption): its
DB-side checks (surfaces/writer-role double-check) now run SYNCHRONOUSLY
inside `build_control_app()` itself, mirroring `r2db_api.main.build_app`'s
own startup sequence -- never deferred to ASGI `_lifespan`. So testing a
control-plane surfaces failure now requires only (1) a REAL, migrated
platform database (this file's own `platform` fixture, shared with the
`r2db_api.main` tests above it), (2) setting the `platform_declarations`
row to the malformed/missing value under test, and (3) calling `build_
control_app(env)` directly inside `pytest.raises(...)` -- no ASGI lifespan
needs to be driven any longer, since the check already ran by the time
this call returns (or fails to).

`_control_main_module()`'s own reload-with-placeholder-env pattern (below)
remains valid and necessary for a DIFFERENT reason after the rework: a
bare `import r2db_api.control_main` no longer builds `app` eagerly at all
(module-level `app` is now a PEP 562 lazy attribute, `control_main.py`'s
own tail) -- but reloading with a controlled env before FIRST import still
matters for any test that touches `module.app` directly (this file has
none), and keeps this helper symmetric with `test_credential_persistence.
py`'s own `main_module` fixture.
"""
from __future__ import annotations

import importlib
import sys
import types
from typing import Iterator

import pytest
from starlette.testclient import TestClient

from test_credential_persistence import (  # noqa: F401 -- imported for fixture re-export, pytest discovers by name
    PEPPER,
    _DEFAULT_SURFACES_VALUE,
    _main_env,
    _set_surfaces_row,
    main_module,
    platform,
    provisioned_app,
)

# --------------------------------------------------------------------------
# r2db_api.main -- surfaces.data (always required) / surfaces.control
# (required only when R2DB_CONTROL_PLANE_STATUS=enabled), now read from the
# shared `platform_declarations` row instead of an env var.
# --------------------------------------------------------------------------

_BAD_DATA_BASE_URLS = (
    ("relative", "/v1"),  # relative -- no scheme/host at all
    ("wrong-suffix", "https://r2db-surfaces-test.example.invalid/v2"),  # wrong terminal path
    ("trailing-slash", "https://r2db-surfaces-test.example.invalid/v1/"),  # correct suffix, extra trailing slash
)

_GOOD_DATA_BASE_URL = "https://r2db-surfaces-test.example.invalid/v1"


@pytest.mark.parametrize("label,bad_url", _BAD_DATA_BASE_URLS)
def test_build_app_rejects_malformed_data_base_url(
    label: str, bad_url: str, platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    _set_surfaces_row(platform, {"data": {"base_url": bad_url}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.data.base_url"):
            main_module.build_app(env=_main_env(platform, provisioned_app))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_app_rejects_missing_surfaces_row(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """F-3 (design §3.8): the `surfaces` row itself absent -- `surfaces.
    data` is an UNCONDITIONAL 1.6.0 obligation, so this is required
    regardless of `R2DB_CONTROL_PLANE_STATUS`."""
    import psycopg
    from psycopg import sql

    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {table} WHERE key = 'surfaces'").format(table=sql.Identifier(platform.schema, "platform_declarations")))
        conn.commit()
    try:
        with pytest.raises(RuntimeError, match="no 'surfaces' row"):
            main_module.build_app(env=_main_env(platform, provisioned_app))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_app_accepts_a_well_formed_data_base_url_and_omits_control_when_unavailable(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """Positive control for the negative tests above, and design D-2's
    conditional-omission rule: the `platform` fixture's own default row
    (control-less) plus `R2DB_CONTROL_PLANE_STATUS` defaulting `unavailable`
    -- `surfaces.control` must not be required (or read) in that case."""
    asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
    with TestClient(asgi_app) as client:
        credential_id, secret = _issue_and_compose(platform, provisioned_app, main_module)
        response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {credential_id}.{secret}"})
        assert response.status_code == 200
        document = response.json()
        assert document["surfaces"] == _DEFAULT_SURFACES_VALUE
        assert "control" not in document["surfaces"]


@pytest.mark.parametrize("label,bad_url", _BAD_DATA_BASE_URLS)
def test_build_app_rejects_malformed_control_base_url_when_control_plane_enabled(
    label: str, bad_url: str, platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    bad_control_url = bad_url.replace("/v1", "/control/v1").replace("v2", "control/v2")
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}, "control": {"base_url": bad_control_url}})
    try:
        env = _main_env(platform, provisioned_app)
        env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
        with pytest.raises(RuntimeError, match="surfaces.control.base_url"):
            main_module.build_app(env=env)
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_app_rejects_missing_control_base_url_when_control_plane_enabled(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """F-6 (reverse direction, design §3.8): `R2DB_CONTROL_PLANE_STATUS`
    other than `unavailable` but the shared row has no `control` key."""
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    with pytest.raises(RuntimeError, match="surfaces.control is not declared"):
        main_module.build_app(env=env)


def test_build_app_control_plane_enabled_publishes_both_surfaces(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    control_url = "https://r2db-surfaces-test-control.example.invalid/control/v1"
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}, "control": {"base_url": control_url}})
    try:
        env = _main_env(platform, provisioned_app)
        env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
        asgi_app = main_module.build_app(env=env)
        with TestClient(asgi_app) as client:
            credential_id, secret = _issue_and_compose(platform, provisioned_app, main_module)
            response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {credential_id}.{secret}"})
            assert response.status_code == 200
            document = response.json()
            assert document["surfaces"] == {
                "data": {"base_url": _GOOD_DATA_BASE_URL},
                "control": {"base_url": control_url},
            }
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_app_capabilities_document_is_a_startup_snapshot_not_re_read_per_request(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """Completion condition 13 (U-3, requester ruling 2026-09-05): the
    declaration read happens ONCE, at startup -- changing `platform_
    declarations.surfaces` directly in the DB AFTER `build_app` has
    already returned must NOT change what an already-running process'
    `/v1/capabilities` reports. A mutation that made capability-document
    assembly re-read the table per request (work order 変異 14's sibling
    for surfaces specifically) would turn this red."""
    import json

    import psycopg
    from psycopg import sql

    asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
    try:
        with TestClient(asgi_app) as client:
            credential_id, secret = _issue_and_compose(platform, provisioned_app, main_module)
            headers = {"authorization": f"Bearer {credential_id}.{secret}"}
            before = client.get("/v1/capabilities", headers=headers).json()
            assert before["surfaces"] == _DEFAULT_SURFACES_VALUE

            # Change the DB-side row directly (never through `ops`,
            # simulating a change made without restarting this process --
            # design's own U-3 says this must have NO effect until restart).
            with psycopg.connect(platform.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("UPDATE {table} SET value = %s WHERE key = 'surfaces'").format(
                            table=sql.Identifier(platform.schema, "platform_declarations")
                        ),
                        [json.dumps({"data": {"base_url": "https://startup-snapshot-changed.example.invalid/v1"}})],
                    )
                conn.commit()
            try:
                after = client.get("/v1/capabilities", headers=headers).json()
                assert after["surfaces"] == before["surfaces"] == _DEFAULT_SURFACES_VALUE
            finally:
                _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)
    finally:
        asgi_app.app.state.service._durable_audit.close()
        asgi_app.app.state.service._credentials.close()
        main_module.default_pool_manager.dispose_all()


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
# r2db_api.control_main -- surfaces.data AND surfaces.control are BOTH
# unconditionally required (this process is always a control-plane).
# `build_control_app()` itself stays zero-network (see module docstring);
# the DB-side checks below run inside `_lifespan`'s own startup, so every
# test here needs the REAL, migrated `platform` fixture and drives the
# lifespan via `TestClient` to observe the raised `RuntimeError`.
# --------------------------------------------------------------------------

_CONTROL_ENV_BASE_IMPORT_PLACEHOLDER = {
    # Only used to satisfy `build_control_app()`'s own F-1/F-2-independent,
    # zero-network `_require` checks at MODULE IMPORT time -- never
    # connected to (see `control_main.py`'s own docstring on why `build_
    # control_app()` remains zero-network after Q4 WP-1).
    "R2DB_CONTROLPLANE_DSN": "host=/tmp port=1 dbname=r2db_surfaces_test_import_placeholder",
    "R2DB_CONTROL_CREDENTIAL_PEPPER": "r2db-surfaces-test-ctl-pepper",
    "R2DB_CREDENTIAL_PEPPER": "r2db-surfaces-test-app-pepper",
}


def _control_main_module() -> types.ModuleType:
    """Same safe-reload convention as `test_credential_persistence.py`'s
    own `main_module` fixture, for `r2db_api.control_main` -- imported
    lazily inside each test (not this module's own top level) so a bare
    `import test_surfaces_env` never itself triggers `control_main.py`'s
    module-level `app = build_control_app()` against whatever `os.environ`
    a fresh process happens to have.
    """
    mp = pytest.MonkeyPatch()
    for key, value in _CONTROL_ENV_BASE_IMPORT_PLACEHOLDER.items():
        mp.setenv(key, value)
    try:
        if "r2db_api.control_main" in sys.modules:
            module = importlib.reload(sys.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as module
        return module
    finally:
        mp.undo()


def _real_control_env(platform: types.SimpleNamespace) -> dict[str, str]:
    """A real, working `build_control_app` env -- `R2DB_CONTROLPLANE_DSN`
    points at the SAME real, migrated platform database `r2db_api.main`'s
    own tests above use (`platform.controlplane_dsn`), so `_lifespan`'s
    own DB-side checks (Q4 WP-1) have something real to read."""
    return {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "r2db-surfaces-test-real-ctl-pepper",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
    }


_BAD_CONTROL_BASE_URLS = (
    ("relative", "/control/v1"),
    ("wrong-suffix", "https://r2db-control-main-surfaces-test.example.invalid/control/v2"),
    ("trailing-slash", "https://r2db-control-main-surfaces-test.example.invalid/control/v1/"),
)

_GOOD_CONTROL_BASE_URL = "https://r2db-control-main-surfaces-test.example.invalid/control/v1"


@pytest.mark.parametrize("label,bad_url", _BAD_CONTROL_BASE_URLS)
def test_build_control_app_rejects_malformed_control_base_url(label: str, bad_url: str, platform: types.SimpleNamespace) -> None:
    module = _control_main_module()
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}, "control": {"base_url": bad_url}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.control.base_url"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_control_app_rejects_missing_control_base_url(platform: types.SimpleNamespace) -> None:
    """F-3c (q4-f3c-and-amendments.md, rework round): a `surfaces` row that
    exists but omits `control` is a DIFFERENT condition from F-3 (row
    absent entirely) -- the control-plane process (unconditionally
    required to have a control surface) raises the F-3c-pinned text, not
    the pre-rework ad hoc message this test used to expect."""
    module = _control_main_module()
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}})  # no 'control' key
    try:
        with pytest.raises(RuntimeError, match="has no surfaces.control, but this is the control-plane process"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


@pytest.mark.parametrize(
    "label,bad_url",
    (
        ("relative", "/v1"),
        ("wrong-suffix", "https://r2db-control-main-surfaces-test.example.invalid/v2"),
        ("trailing-slash", "https://r2db-control-main-surfaces-test.example.invalid/v1/"),
    ),
)
def test_build_control_app_rejects_malformed_data_base_url(label: str, bad_url: str, platform: types.SimpleNamespace) -> None:
    module = _control_main_module()
    _set_surfaces_row(platform, {"data": {"base_url": bad_url}, "control": {"base_url": _GOOD_CONTROL_BASE_URL}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.data.base_url"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_control_app_rejects_missing_surfaces_row(platform: types.SimpleNamespace) -> None:
    import psycopg
    from psycopg import sql

    module = _control_main_module()
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {table} WHERE key = 'surfaces'").format(table=sql.Identifier(platform.schema, "platform_declarations")))
        conn.commit()
    try:
        with pytest.raises(RuntimeError, match="no 'surfaces' row"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_control_main_validate_surface_base_url_accepts_the_well_formed_positive_control() -> None:
    """Positive control (no test above ever observes a SUCCESSFUL surfaces
    validation in isolation, only through the full startup failure paths)
    -- confirms the malformed-shape tests above are rejecting for the
    right reason, not because nothing can ever pass this check. Rework
    round: the shape check itself now lives in `platform_declarations.
    validate_surfaces_value` (consolidated from `main.py`/`control_main.
    py`'s own former per-module copies, rulings-q4-wp12-rework.md sec.1,
    closing L6-17) -- exercised here directly, not through either
    composition root."""
    from r2db_api.platform_declarations import PEER_MODULE, DEFAULT_SCHEMA, validate_surfaces_value

    data_only = validate_surfaces_value({"data": {"base_url": "https://ok.example.invalid/v1"}}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert data_only.data_base_url == "https://ok.example.invalid/v1"
    assert data_only.control_base_url is None

    both = validate_surfaces_value({
        "data": {"base_url": "https://ok.example.invalid/v1"},
        "control": {"base_url": "https://ok.example.invalid/control/v1"},
    }, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert both.data_base_url == "https://ok.example.invalid/v1"
    assert both.control_base_url == "https://ok.example.invalid/control/v1"


# --------------------------------------------------------------------------
# Coordinator item 7(ii) (reviewer O4, 2026-09-04 review): the two
# variables' suffix checks must be mutually exclusive -- surfaces.data.
# base_url must reject a value ending `/control/v1` (it "ends with /v1"
# too, since "/control/v1" itself ends with the substring "/v1") and
# surfaces.control.base_url must reject a bare `/v1`-only ending.
# --------------------------------------------------------------------------


def test_build_app_rejects_data_base_url_ending_in_control_v1(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    _set_surfaces_row(platform, {"data": {"base_url": "https://r2db-surfaces-test.example.invalid/control/v1"}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.data.base_url"):
            main_module.build_app(env=_main_env(platform, provisioned_app))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_app_rejects_control_base_url_ending_in_bare_v1(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}, "control": {"base_url": "https://r2db-surfaces-test.example.invalid/v1"}})
    try:
        env = _main_env(platform, provisioned_app)
        env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
        with pytest.raises(RuntimeError, match="surfaces.control.base_url"):
            main_module.build_app(env=env)
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_control_app_rejects_data_base_url_ending_in_control_v1(platform: types.SimpleNamespace) -> None:
    module = _control_main_module()
    _set_surfaces_row(platform, {"data": {"base_url": "https://r2db-control-main-surfaces-test.example.invalid/control/v1"}, "control": {"base_url": _GOOD_CONTROL_BASE_URL}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.data.base_url"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


def test_build_control_app_rejects_control_base_url_ending_in_bare_v1(platform: types.SimpleNamespace) -> None:
    module = _control_main_module()
    _set_surfaces_row(platform, {"data": {"base_url": _GOOD_DATA_BASE_URL}, "control": {"base_url": "https://r2db-control-main-surfaces-test.example.invalid/v1"}})
    try:
        with pytest.raises(RuntimeError, match="surfaces.control.base_url"):
            module.build_control_app(env=_real_control_env(platform))
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


# --------------------------------------------------------------------------
# Coordinator audit item (a): the data document and the control document's
# OWN `surfaces` agree, fixed over REAL HTTP against BOTH real ASGI apps
# (`main.build_app` and `control_main.build_control_app`), not merely
# through the shared `self._surfaces` dict both classes are constructed
# with in-process (`test_control_plane_service.py`'s own harness never
# builds a real `control_main` app at all).
# --------------------------------------------------------------------------


def test_data_and_control_documents_agree_on_surfaces_over_real_http(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    from r2db_api.control_plane import bootstrap_control_credential
    from r2db_api.credential_store import PostgresControlAuditSink, PostgresControlCredentialStore

    data_base_url = "https://r2db-surfaces-agree-test.example.invalid/v1"
    control_base_url = "https://r2db-surfaces-agree-test-control.example.invalid/control/v1"

    _set_surfaces_row(platform, {"data": {"base_url": data_base_url}, "control": {"base_url": control_base_url}})
    try:
        data_env = _main_env(platform, provisioned_app)
        data_env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
        data_app = main_module.build_app(env=data_env)

        control_module = _control_main_module()
        control_env = _real_control_env(platform)
        control_app = control_module.build_control_app(env=control_env)

        control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=control_env["R2DB_CONTROL_CREDENTIAL_PEPPER"], schema=platform.schema)
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
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


# --------------------------------------------------------------------------
# N-3 (monitor ruling 2026-09-05, delta review §4): condition 27's
# CONTROL half of the startup-snapshot requirement (U-3) had no test --
# only the data-plane half did (`test_build_app_capabilities_document_is_
# a_startup_snapshot_not_re_read_per_request` above/in `test_main.py`'s
# MitateDB sibling). `assemble_control_stack` reads `platform_declarations`
# exactly ONCE and passes `surfaces=` into `ControlPlaneService.__init__`
# (`self._surfaces`, `control_plane.py`) -- `capabilities()` never re-reads
# the DB -- so this is a NON-VACUOUS pin of behavior that already exists,
# not a new mechanism (裁定: 設計外の機構は足さない).
# --------------------------------------------------------------------------


def test_control_capabilities_document_is_a_startup_snapshot_not_re_read_per_request(
    platform: types.SimpleNamespace,
) -> None:
    import json

    import psycopg
    from psycopg import sql

    from r2db_api.control_plane import bootstrap_control_credential
    from r2db_api.credential_store import PostgresControlAuditSink, PostgresControlCredentialStore

    control_base_url = "https://r2db-control-snapshot-test.example.invalid/control/v1"
    _set_surfaces_row(platform, {
        "data": {"base_url": "https://r2db-control-snapshot-test.example.invalid/v1"},
        "control": {"base_url": control_base_url},
    })
    try:
        control_module = _control_main_module()
        control_env = _real_control_env(platform)
        control_app = control_module.build_control_app(env=control_env)

        # `platform` is a shared (module-scoped) fixture, and `bootstrap_
        # control_credential` refuses a second call once ANY control
        # credential row exists ("bootstrap runs at most once") -- clear
        # any row a DIFFERENT test in this file/session left behind
        # before bootstrapping this test's own (this test's own `finally`
        # below leaves the table clean again for whichever test runs
        # next).
        _precleanup = psycopg.connect(platform.control_dsn, autocommit=True)
        try:
            with _precleanup.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {table}").format(table=sql.Identifier(platform.schema, "control_credentials")))
        finally:
            _precleanup.close()

        control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=control_env["R2DB_CONTROL_CREDENTIAL_PEPPER"], schema=platform.schema)
        control_audit = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)
        try:
            with control_store.unit_of_work() as work:
                _credential_id, control_bearer = bootstrap_control_credential(control_store, control_audit, work=work)
        finally:
            control_store.close()
            control_audit.close()

        with TestClient(control_app) as client:
            headers = {"authorization": f"Bearer {control_bearer}"}
            before = client.get("/control/v1/capabilities", headers=headers)
            assert before.status_code == 200, before.text
            before_surfaces = before.json()["surfaces"]

            admin = psycopg.connect(platform.control_dsn)
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        sql.SQL("UPDATE {table} SET value = %s::jsonb WHERE key = 'surfaces'").format(
                            table=sql.Identifier(platform.schema, "platform_declarations")),
                        [json.dumps({
                            "data": {"base_url": "https://control-snapshot-changed.example.invalid/v1"},
                            "control": {"base_url": "https://control-snapshot-changed.example.invalid/control/v1"},
                        })],
                    )
                admin.commit()
                try:
                    after = client.get("/control/v1/capabilities", headers=headers)
                    assert after.status_code == 200, after.text
                    assert after.json()["surfaces"] == before_surfaces
                finally:
                    with admin.cursor() as cur:
                        cur.execute(
                            sql.SQL("UPDATE {table} SET value = %s::jsonb WHERE key = 'surfaces'").format(
                                table=sql.Identifier(platform.schema, "platform_declarations")),
                            [json.dumps(before_surfaces)],
                        )
                    admin.commit()
            finally:
                admin.close()
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)
        # `platform` is a shared (module-scoped) fixture -- `bootstrap_
        # control_credential` above refuses a second call once a control
        # credential row exists ("bootstrap runs at most once"), so this
        # test must leave the table exactly as it found it (empty),
        # rather than leaking a row that would break a LATER test in this
        # same file/session that also bootstraps one.
        cleanup = psycopg.connect(platform.control_dsn, autocommit=True)
        try:
            with cleanup.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {table}").format(table=sql.Identifier(platform.schema, "control_credentials")))
        finally:
            cleanup.close()
