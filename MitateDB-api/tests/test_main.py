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

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import httpx
import psycopg
import pytest

import mitatedb_api.http as http_module
from mitatedb_api.application_audit import PostgresApplicationAuditSink
from mitatedb_api.auth import Role
from mitatedb_api.credential_store_postgres import PostgresCredentialStore

# A RELATIVE import: see `test_http.py`'s own identical comment for why a
# bare `from test_postgres import ...` is unsafe under the combined root
# suite (r2db-api's own, differently-shaped `test_postgres.py` occupies
# the bare `sys.modules["test_postgres"]` name first).
from .test_postgres import MIGRATIONS_DIR, platform, provision_app  # noqa: F401

BASE_URL = "http://mitatedb-main-test.invalid"

_PEPPER = "synthetic-test-pepper-mitatedb-main-0000"
_CONTROL_PEPPER = "synthetic-test-pepper-mitatedb-main-ctl-0000"
_PROBE_APP_ID = "main_import_probe"
# `main.build_app` requires `MITATEDB_WORKERS`/`MITATEDB_SLOT_DIR`: one
# shared, real slot directory (mode 0700, `mkdtemp`'s own default) for
# every `build_app(env)` call in this module, mirroring a single-process
# (`workers=1`) deployment; left to the OS temp dir like this repository's
# other `tempfile.mkdtemp` test call sites.
_SLOT_DIR = tempfile.mkdtemp(prefix="mitatedb-test-slots-main-")


def _base_env(platform, probe_app) -> dict[str, str]:
    # Q4 phase (design D-2, work order §4 WP-2 変更対象 E): `MITATEDB_
    # DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL` are REMOVED env vars
    # (F-2) -- `surfaces` comes from `<registry>.platform_declarations`,
    # already seeded (`data` only -- see `test_postgres.py::_bootstrap_
    # platform`'s own comment) by the shared `platform` fixture.
    return {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": probe_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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


@pytest.mark.parametrize(
    "removed_var,value",
    [
        ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", ""),
        ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "5000"),
        ("MITATEDB_AUDIT_IDLE_TIMEOUT_MS", ""),
        ("MITATEDB_AUDIT_IDLE_TIMEOUT_MS", "5000"),
        ("MITATEDB_DATA_BASE_URL", ""),
        ("MITATEDB_DATA_BASE_URL", "https://removed-env.example.invalid/v1"),
        ("MITATEDB_CONTROL_BASE_URL", ""),
        ("MITATEDB_CONTROL_BASE_URL", "https://removed-env.example.invalid/control/v1"),
    ],
)
def test_build_app_rejects_every_removed_env_var_through_the_real_composition_root(
    main_module, platform, probe_app, removed_var: str, value: str,
) -> None:
    """{scratchpad}/wp12-audit-gaps.md G5 (WP-2 completion condition
    23(a)): `reject_removed_timeout_env`/`reject_removed_surface_env`
    were exercised ONLY as bare function calls in `test_platform_
    declarations.py` -- never through `build_app` itself. Removing
    `main.py`'s own two calls to those functions (`main.py:257-258`)
    left every PRE-EXISTING test in this file green, since none of them
    ever set one of the four removed env vars at all. 8 cases: {the 2
    removed timeout vars, the 2 removed surface vars} x {empty string,
    a real-looking value} -- design §3.8 F-1/F-2's own "値は問わない。空
    文字列を含む" (whatever its value, an empty string included)."""
    env = _base_env(platform, probe_app)
    env[removed_var] = value
    with pytest.raises(RuntimeError, match="no longer read"):
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
        # Phase 6 WP-3 (design D-1(d)): `issue`'s second element is now
        # the complete bearer -- used verbatim.
        credential_id, bearer = write_store.issue(probe_app.app_id, Role.RUNTIME)
    finally:
        write_store.close()

    import asyncio

    async def _call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

    response = asyncio.run(_call())
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["application_scope"] == probe_app.app_id
    assert document["role"] == "runtime"
    assert document["limit_enforcement"]["request_bytes"] == "enforced"
    # WP-5 (design v1.2 R-9): an operator who never sets
    # `MITATEDB_CONTROL_PLANE_STATUS` must see NO behavior change at all --
    # this app was built (fixture `main_module`, module import time) from
    # `_base_env`, which does not set that variable.
    assert document["capabilities"]["control_plane"]["status"] == "unavailable"


def test_build_app_capabilities_document_is_a_startup_snapshot_not_re_read_per_request(main_module, platform, probe_app):
    """WP-1/WP-2 completion condition 13 / rework condition 27 (U-3,
    requester ruling 2026-09-05): the declaration read happens ONCE, at
    startup -- changing `platform_declarations.surfaces` directly in the
    DB AFTER `build_app` has already returned must NOT change what an
    already-running process' `/v1/capabilities` reports. Mirrors r2db-
    api's own `test_surfaces_env.py::test_build_app_capabilities_
    document_is_a_startup_snapshot_not_re_read_per_request` (added there
    first); this is the MitateDB-side non-vacuity companion (work order
    変異14/28's own target -- previously absent for this peer)."""
    import asyncio
    import json

    app = main_module.app
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema,
    )
    try:
        credential_id, bearer = write_store.issue(probe_app.app_id, Role.RUNTIME)
    finally:
        write_store.close()

    async def _get():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

    before = asyncio.run(_get())
    assert before.status_code == 200, before.text
    before_surfaces = before.json().get("surfaces")

    admin = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s::jsonb WHERE key = 'surfaces'",
                [json.dumps({"data": {"base_url": "https://startup-snapshot-changed.example.invalid/v1"}})],
            )
        try:
            after = asyncio.run(_get())
            assert after.status_code == 200, after.text
            assert after.json().get("surfaces") == before_surfaces
        finally:
            # restore -- IDENTICAL to the value this test itself observed
            # BEFORE mutating (never a hardcoded guess at the fixture's
            # own seed shape).
            with admin.cursor() as cur:
                cur.execute(
                    f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s::jsonb WHERE key = 'surfaces'",
                    [json.dumps(before_surfaces)],
                )
    finally:
        admin.close()


# ===========================================================================
# Q4 rework (supervisor ruling 2026-09-05, H-1 = (a)): the cell-open-time
# check (F-12, design D-3(f)) exercised through the REAL startup path
# (`build_app`) AND real HTTP (`httpx.AsyncClient`/`ASGITransport`), not
# just `test_platform_upgrades.py::test_cell_open_check_raises_service_
# unavailable_for_missing_upgrade`'s own direct `PostgresBackend(...)`
# construction -- proving `main.py`'s own per-application loop actually
# wires the check in AND that ONE application's own missing upgrade never
# takes the whole process down (never turning `build_app` itself into a
# `pytest.raises` target, unlike the pre-rework form this replaces --
# review H-1, `backend_postgres.py`'s own `__init__` no longer raises).
# Deliberately its OWN, dedicated, never-deprovisioned application pair
# (`h1_good`/`h1_bad`) -- this file's own module docstring already
# explains why `test_postgres.py`'s `iso_a`/`iso_b` must not be reused for
# a `build_app` call that leaks persistent connections.
# ===========================================================================


@pytest.fixture(scope="module")
def h1_good_app(platform):
    return provision_app(platform, "h1good")


@pytest.fixture(scope="module")
def h1_bad_app(platform):
    return provision_app(platform, "h1bad")


def _h1_env(platform, good_app, bad_app) -> dict[str, str]:
    return {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": f"{good_app.app_id},{bad_app.app_id}",
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{good_app.app_id.upper()}_RUNTIME_DSN": good_app.runtime_dsn,
        f"MITATEDB_APP_{good_app.app_id.upper()}_DEVELOPER_DSN": good_app.developer_dsn,
        f"MITATEDB_APP_{bad_app.app_id.upper()}_RUNTIME_DSN": bad_app.runtime_dsn,
        f"MITATEDB_APP_{bad_app.app_id.upper()}_DEVELOPER_DSN": bad_app.developer_dsn,
    }


def _h1_delete_ledger_upgrade_8(bad_app) -> None:
    conn = psycopg.connect(bad_app.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._mdb_platform_upgrades WHERE upgrade_number = 8")
    finally:
        conn.close()


def _h1_issue_runtime_credential(platform, app) -> str:
    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema,
    )
    try:
        _credential_id, bearer = write_store.issue(app.app_id, Role.RUNTIME)
    finally:
        write_store.close()
    return bearer


_F12_MESSAGE_UPGRADE_8 = (
    "This application's storage is missing platform upgrade(s) 8: the deployment must apply "
    "them before this application can serve requests. Run 'python -m mitatedb_api.ops "
    "upgrade-applications --lock-timeout <value>' (its '--dry-run' shows applied and pending "
    "per application and requires the same '--lock-timeout'), then retry."
)


def test_build_app_h1_serves_every_application_and_refuses_only_the_one_with_a_pending_upgrade(
    platform, h1_good_app, h1_bad_app, main_module,
) -> None:
    """裁定 1 (H-1 = (a)): `h1_bad_app`'s own upgrade 8 is deleted below
    before `build_app` ever runs -- `h1_good_app`'s own ledger stays
    complete (seeded `{6, 8}` by the current `0003`). `build_app` itself
    must NOT raise (a mutation reverting `backend_postgres.PostgresBackend.
    __init__` back to raising `StorageConfigurationError` directly, out of
    `main.py`'s own eager per-application construction loop, would fail
    THIS test at `build_app(...)` itself, before either HTTP assertion
    below is ever reached). `GET /v1/catalog` for `h1_good_app` returns
    200; for `h1_bad_app` it returns 503 with the F-12 message verbatim."""
    _h1_delete_ledger_upgrade_8(h1_bad_app)

    env = _h1_env(platform, h1_good_app, h1_bad_app)
    app = main_module.build_app(env)

    bearer_good = _h1_issue_runtime_credential(platform, h1_good_app)
    bearer_bad = _h1_issue_runtime_credential(platform, h1_bad_app)

    import asyncio

    async def _get(bearer: str):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/catalog", headers={"authorization": f"Bearer {bearer}"})

    response_good = asyncio.run(_get(bearer_good))
    assert response_good.status_code == 200, response_good.text

    response_bad = asyncio.run(_get(bearer_bad))
    assert response_bad.status_code == 503, response_bad.text
    body_bad = response_bad.json()
    assert body_bad["code"] == "SERVICE_UNAVAILABLE"
    assert body_bad["message"] == _F12_MESSAGE_UPGRADE_8

    # U-2 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査, design
    # D-3(f) 追記の精密化): H-1's own refusal is scoped to operations that
    # cross the storage boundary -- `/v1/capabilities` (the discovery
    # document) never touches the backend, so it must still answer
    # normally (200) for `h1_bad_app` even while its own `GET /v1/catalog`
    # is refused above.
    async def _get_capabilities(bearer: str):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

    response_bad_capabilities = asyncio.run(_get_capabilities(bearer_bad))
    assert response_bad_capabilities.status_code == 200, response_bad_capabilities.text


def test_build_app_h1_logs_the_f12_message_verbatim_at_cell_open_time(
    platform, h1_good_app, h1_bad_app, main_module, caplog: pytest.LogCaptureFixture,
) -> None:
    """U-6 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査): H-1's own
    design-doc claim ("起動時にはログへ F-12 を1行出す (API 応答と同じ
    文面)") previously had no direct evidence -- `main.py`'s own stderr
    `print` was a visual-only check (裁定 1 の証拠不足). `main.py`'s own
    eager per-application construction loop now logs through the standard
    `logging` module, so `caplog` pins the verbatim F-12 text at cell-open
    time -- the SAME text `h1_bad_app`'s own HTTP responses carry
    (companion H-1 test above) -- and confirms `h1_good_app` (whose own
    ledger is complete) never logs a refusal at all. `_h1_delete_ledger_
    upgrade_8` is re-run here (independently of test execution order/the
    companion tests above -- idempotent, a plain `DELETE`)."""
    _h1_delete_ledger_upgrade_8(h1_bad_app)
    env = _h1_env(platform, h1_good_app, h1_bad_app)

    import logging

    caplog.set_level(logging.WARNING, logger="mitatedb_api.main")
    main_module.build_app(env)

    messages = [record.getMessage() for record in caplog.records if record.name == "mitatedb_api.main"]
    expected = (
        f"mitatedb_api: application '{h1_bad_app.app_id}' cell refusing requests: {_F12_MESSAGE_UPGRADE_8}"
    )
    assert expected in messages
    assert not any(h1_good_app.app_id in message for message in messages)


def test_build_app_h1_after_ops_upgrade_applications_and_a_restart_the_refused_application_serves_normally(
    platform, h1_bad_app, main_module, monkeypatch, tmp_path,
) -> None:
    """裁定 1 (H-1, (i)/(ii)): running the real `ops upgrade-applications`
    against `h1_bad_app` (whose own upgrade 8 is deleted below,
    independently of test execution order/the companion test above) and
    then restarting the data-plane process (a fresh `build_app` call --
    the only way this rework's own startup snapshot, D-1(e)/D-2(g)/U-3,
    is ever re-read) makes `h1_bad_app`'s own cell a normal one again:
    `GET /v1/catalog` now returns 200."""
    import mitatedb_api.ops as ops

    _h1_delete_ledger_upgrade_8(h1_bad_app)

    # `h1_bad_app` alone is enough to observe both the refusal and the
    # recovery -- no second, "good" application is needed for this test's
    # own claim.
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": h1_bad_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{h1_bad_app.app_id.upper()}_RUNTIME_DSN": h1_bad_app.runtime_dsn,
        f"MITATEDB_APP_{h1_bad_app.app_id.upper()}_DEVELOPER_DSN": h1_bad_app.developer_dsn,
    }

    import asyncio

    async def _get(app, bearer: str):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/catalog", headers={"authorization": f"Bearer {bearer}"})

    app_before = main_module.build_app(env)
    bearer_before = _h1_issue_runtime_credential(platform, h1_bad_app)
    response_before = asyncio.run(_get(app_before, bearer_before))
    assert response_before.status_code == 503, response_before.text

    # `ops.py`'s own test-only escape hatch (`MITATEDB_MIGRATIONS_DIR`,
    # `test_ops_upgrade.py`'s own established convention) -- points
    # `_migrations_dir()` at a REWRITTEN `0008` (this module's own
    # throwaway schema/db prefix, the SAME blanket `.replace("mitatedb",
    # prefix)` step `test_postgres.py::_bootstrap_platform` already
    # applies to every other migration file) instead of the real
    # `MitateDB-api/migrations/`, whose `0008` names the real deployment's
    # literal `mitatedb_registry`/`mitatedb_platform`.
    rewritten_0008 = tmp_path / "0008_platform_upgrades_upgrade.sql"
    rewritten_0008.write_text(
        (MIGRATIONS_DIR / "0008_platform_upgrades_upgrade.sql").read_text().replace("mitatedb", platform.prefix)
    )
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.registry_schema)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(tmp_path))
    # design D-2: this
    # test's own throwaway-cluster launcher (`tools/testpg/dsa_testpg.
    # py`) exports `PGPORT`/`PGUSER`/`PGPASSFILE` ambiently at the
    # PROCESS level; `platform.provision_dsn` above already carries every
    # connection parameter `upgrade-applications` needs explicitly, so
    # those ambient exports are pure interference for `_psql_connection_
    # env`'s own A-13 fail-closed check (`ops.main` below runs IN-
    # PROCESS, unlike `test_ops_upgrade.py`'s own subprocess-based
    # `_run_ops`, so `os.environ` itself -- not a copy -- must be
    # cleared).
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)
    rc = ops.main(["upgrade-applications", "--application", h1_bad_app.app_id, "--lock-timeout", "5000ms"])
    assert rc == 0

    # "Restart" -- a fresh `build_app` call re-reads the ledger this
    # rework's own startup snapshot only ever reads once per process.
    app_after = main_module.build_app(env)
    bearer_after = _h1_issue_runtime_credential(platform, h1_bad_app)
    response_after = asyncio.run(_get(app_after, bearer_after))
    assert response_after.status_code == 200, response_after.text


def test_build_app_writer_role_dual_check_connects_via_the_sinks_own_connect_method(main_module, platform, probe_app, monkeypatch):
    """N-2 (monitor ruling 2026-09-05, delta review §4): `check_writer_
    role_timeouts`'s own connection must be opened via the sink's own
    method for opening a connection (`PostgresApplicationAuditSink.
    _connect`, which the sink's writes use when it has no pool) -- never a
    separately-written `psycopg.connect(...)` call that merely happens to
    match its arguments today.
    Patches `_connect` to record every call; `build_app` makes no HTTP
    request of its own, so a call recorded here can only have happened
    during the startup dual-check step itself. Would go RED under the
    delta review's own finding (`main.py:295` duplicating the connect
    call instead of calling `_connect`)."""
    calls: list[object] = []
    real_connect = PostgresApplicationAuditSink._connect

    def _spy(self):
        calls.append(self)
        return real_connect(self)

    monkeypatch.setattr(PostgresApplicationAuditSink, "_connect", _spy)
    env = _base_env(platform, probe_app)
    main_module.build_app(env)
    assert len(calls) >= 1
    assert all(isinstance(c, PostgresApplicationAuditSink) for c in calls)


def _record_built_pools_and_sinks(main_module, monkeypatch) -> "tuple[list, list]":
    """Makes `main.build_app` record every `BoundedConnectionPool` and every
    `PostgresApplicationAuditSink` it constructs (both real, subclassed)."""
    pools: list = []
    sinks: list = []
    real_pool = main_module.BoundedConnectionPool
    real_sink = main_module.PostgresApplicationAuditSink

    class _RecordingPool(real_pool):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            pools.append(self)

    class _RecordingSink(real_sink):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            sinks.append(self)

    monkeypatch.setattr(main_module, "BoundedConnectionPool", _RecordingPool)
    monkeypatch.setattr(main_module, "PostgresApplicationAuditSink", _RecordingSink)
    return pools, sinks


def test_build_app_sizes_the_audit_sinks_pool_from_the_value_f16_counts_per_api_store(main_module, platform, probe_app, monkeypatch) -> None:
    """Completion condition 28: F-16's floor for the `mitatedbsvc_api`
    role counts `platform_declarations._API_ROLE_STORE_COUNT` stores of
    `role_pool_size(thread_limit)` connections each, per process. The
    pools `build_app` builds against that role are exactly that many, each
    of that size (a thread limit of 3 makes it 5), and the audit sink
    writes through the last of them rather than sharing the credential
    store's, so the sink cannot hold more connections than the floor
    counted for it.

    mutation (`main.py`): build the sink's pool twice as large as the
    platform pool (`max_size=pool_size` becomes `max_size=pool_size * 2`
    on `audit_pool`) -- the two sizes then sum to 15 where the floor
    counts 10."""
    from mitatedb_api import platform_declarations
    from mitatedb_api.config import role_pool_size

    pools, sinks = _record_built_pools_and_sinks(main_module, monkeypatch)
    env = _base_env(platform, probe_app)
    env["MITATEDB_THREAD_LIMIT"] = "3"
    main_module.build_app(env)
    per_store = role_pool_size(3)
    assert per_store == 5
    assert len(sinks) == 1
    assert len(pools) == platform_declarations._API_ROLE_STORE_COUNT
    assert sinks[0]._pool is pools[-1] and pools[-1] is not pools[0]
    assert [pool.stats()["size"] for pool in pools] == [per_store] * platform_declarations._API_ROLE_STORE_COUNT
    assert sum(pool.stats()["size"] for pool in pools) == platform_declarations._API_ROLE_STORE_COUNT * per_store


def test_build_app_lifespan_shutdown_closes_the_audit_sinks_pooled_connections(main_module, platform, probe_app, monkeypatch) -> None:
    """The lifespan shutdown closes the connections the audit sink's pool
    holds: with a connection idle in that pool, running the app's lifespan
    startup and shutdown ends its server session.

    mutation (`main.py`): drop the `durable_audit.close()` call from the
    lifespan shutdown -- the pooled session is still on the server."""
    _pools, sinks = _record_built_pools_and_sinks(main_module, monkeypatch)
    app = main_module.build_app(_base_env(platform, probe_app))
    sink = sinks[0]
    conn = sink._pool.acquire()  # the pool opens a connection and, released, keeps it idle
    backend_pid = conn.info.backend_pid
    sink._pool.release(conn)

    def _session_present() -> bool:
        admin = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = %s", [backend_pid])
                return cur.fetchone()[0] == 1
        finally:
            admin.close()

    assert _session_present()
    asyncio.run(main_module._run_lifespan_once(app))
    assert not _session_present()


def test_build_app_rejects_invalid_control_plane_status_value(main_module, platform, probe_app):
    env = _base_env(platform, probe_app)
    env["MITATEDB_CONTROL_PLANE_STATUS"] = "ENABLED"  # wrong case -- not one of the two exact members
    with pytest.raises(Exception, match="MITATEDB_CONTROL_PLANE_STATUS"):
        main_module.build_app(env)


def test_thread_limit_from_env_unit_contract(main_module) -> None:
    """Completion conditions 97/153: unset or empty falls back to
    `default`; a positive integer is returned as-is -- the function
    itself, in isolation (mirrors `test_optional_float_default_path_is_
    not_regressed` immediately below).

    mutation M191 (`mitatedb_api/main.py`): treat an empty string as if
    it were a valid override -- this test's own second assertion (`""`
    -> `4`) goes red."""
    assert main_module._thread_limit_from_env({}, "MITATEDB_THREAD_LIMIT", 4) == 4
    assert main_module._thread_limit_from_env({"MITATEDB_THREAD_LIMIT": ""}, "MITATEDB_THREAD_LIMIT", 4) == 4
    assert main_module._thread_limit_from_env({"MITATEDB_THREAD_LIMIT": "6"}, "MITATEDB_THREAD_LIMIT", 4) == 6


def test_thread_limit_from_env_rejects_zero_negative_or_non_numeric(main_module) -> None:
    """Completion conditions 99/100/101: `0`, a negative integer, and a
    non-numeric value all raise `ValueError` naming the variable.

    mutation M141 (`mitatedb_api/main.py`): only reject a negative value,
    letting `0` through -- this test's own `"0"` `pytest.raises` goes red.
    mutation M142 (`mitatedb_api/main.py`): only reject `0`, letting a
    negative value through -- this test's own `"-3"` `pytest.raises` goes
    red.
    mutation M143 (`mitatedb_api/main.py`): fall back to `default`
    instead of raising when `int()` fails -- this test's own `"abc"`
    `pytest.raises` goes red."""
    for raw in ("0", "-3", "abc"):
        with pytest.raises(ValueError, match="MITATEDB_THREAD_LIMIT"):
            main_module._thread_limit_from_env({"MITATEDB_THREAD_LIMIT": raw}, "MITATEDB_THREAD_LIMIT", 4)


def test_build_app_wires_thread_limit_from_the_env(main_module, platform, probe_app) -> None:
    """Completion conditions 97/98: `build_app`'s own `create_app(...)`
    call receives the SAME effective value `_thread_limit_from_env`
    resolves -- observed on the constructed app's own Starlette middleware
    list (`Middleware.kwargs`), never re-executed against a live request
    here (`test_threadpool_offload.py`'s own D-8 tests already pin that
    `create_app(thread_limit=N)` itself sets a fresh loop's limiter to
    `N`; composing that with this wiring check is condition 97/98's own
    full claim).

    mutation M139 (`mitatedb_api/main.py`): pass a hardcoded `None`
    instead of the computed value to `create_app(...)`'s own `thread_
    limit=` keyword -- this test's own `next(m for m in ... if m.cls is
    ThreadLimitMiddleware)` lookup goes red (no `ThreadLimitMiddleware`
    in the list at all, `StopIteration`).
    mutation M140 (`mitatedb_api/main.py`): assign the wired value from
    `DEFAULT_THREAD_LIMIT` unconditionally, discarding the env -- this
    test's own `== 6` assertion (env set to `"6"`) goes red (reads `4`)."""
    env = _base_env(platform, probe_app)
    env["MITATEDB_THREAD_LIMIT"] = "6"
    app = main_module.build_app(env)
    inner_app = app.app
    middleware = next(m for m in inner_app.user_middleware if m.cls is http_module.ThreadLimitMiddleware)
    assert middleware.kwargs["thread_limit"] == 6

    env_unset = _base_env(platform, probe_app)
    app_unset = main_module.build_app(env_unset)
    middleware_unset = next(m for m in app_unset.app.user_middleware if m.cls is http_module.ThreadLimitMiddleware)
    assert middleware_unset.kwargs["thread_limit"] == 4


def test_build_app_rejects_invalid_thread_limit_env(main_module, platform, probe_app) -> None:
    """Completion conditions 99/100/101 (wiring level): `build_app`
    itself fails to start on `0`/negative/non-numeric `MITATEDB_THREAD_
    LIMIT`.

    mutation M143 (`mitatedb_api/main.py`, wiring level): silently
    degrading to `DEFAULT_THREAD_LIMIT` on an unparsable value -- this
    test's own `pytest.raises` goes red (`build_app` returns an app
    instead of raising)."""
    for raw in ("0", "-3", "abc"):
        env = _base_env(platform, probe_app)
        env["MITATEDB_THREAD_LIMIT"] = raw
        with pytest.raises(ValueError, match="MITATEDB_THREAD_LIMIT"):
            main_module.build_app(env)


_INVALID_AUDIT_FLUSH_INTERVAL_VALUES = ["0", "-1", "nan", "inf", "not-a-number"]


@pytest.mark.parametrize("bad_value", _INVALID_AUDIT_FLUSH_INTERVAL_VALUES)
def test_build_app_fails_fast_on_invalid_audit_flush_interval(main_module, platform, probe_app, bad_value):
    """Phase 6 WP-0 (design D-4(a)): `MITATEDB_AUDIT_FLUSH_INTERVAL_S` is
    the interval `main.py`'s own flush thread passes straight to
    `threading.Event.wait` (`main.py:350`) -- `wait(0)`/`wait(-1)`/
    `wait(float("nan"))` all return immediately (`False`), turning that
    daemon thread into a silent hot loop nothing about which would look
    alarming to an operator who mistyped this variable. `_optional_float`
    must now refuse every non-empty value that is not a finite, positive
    float at startup (`ValueError` naming the variable) -- exercised here
    through the REAL `build_app` path (not a direct call to
    `_optional_float`), so this is the actual startup-failure consumer
    wiring, not merely the helper function in isolation. Each of the 5
    forms (zero / negative / NaN / infinity / unparsable text) is its own
    parametrize case, per WP-0 completion condition 1 ("5 形すべてを個別
    ケースで観測する")."""
    env = _base_env(platform, probe_app)
    env["MITATEDB_AUDIT_FLUSH_INTERVAL_S"] = bad_value
    with pytest.raises(ValueError, match="MITATEDB_AUDIT_FLUSH_INTERVAL_S"):
        main_module.build_app(env)


def test_optional_float_default_path_is_not_regressed(main_module) -> None:
    """WP-0 completion condition 2: an unset OR empty-string
    `MITATEDB_AUDIT_FLUSH_INTERVAL_S` must still fall back to `default` --
    the "空なら既定値" half that must stay green while mutation 2 (dropping
    the `if not raw: return default` early return) turns it red. A direct
    call is sufficient here (unlike the fail-fast cases above): the real-
    startup wiring for this same function/variable pair is already
    established by `test_build_app_fails_fast_on_invalid_audit_flush_
    interval` and by `_optional_float` having exactly one caller in
    `main.py` (the flush-interval assignment feeding `threading.Event.
    wait`)."""
    assert main_module._optional_float({}, "MITATEDB_AUDIT_FLUSH_INTERVAL_S", 2.5) == 2.5
    assert main_module._optional_float({"MITATEDB_AUDIT_FLUSH_INTERVAL_S": ""}, "MITATEDB_AUDIT_FLUSH_INTERVAL_S", 2.5) == 2.5


def test_build_app_control_plane_status_env_flip_is_reflected_in_a_real_request(main_module, platform):
    """WP-5 flip: `MITATEDB_CONTROL_PLANE_STATUS=enabled` really changes
    what a real `/v1/capabilities` request answers -- not merely what
    `FoundationConfig` holds in memory. Builds a SEPARATE app against its
    own, dedicated, never-shared-with-other-tests application (mirrors
    this file's own docstring reasoning for why `main_import_probe` is
    never reused) so this test's own persistent connections do not
    interfere with `main_module.app`'s already-built probe."""
    # A dedicated, never-reused application id -- same reasoning as this
    # file's own `main_import_probe` (module docstring): the resulting
    # `ApplicationCell`'s 2 persistent PostgreSQL connections are
    # deliberately never closed by this test (no ASGI server here to drive
    # the lifespan-shutdown hook that would release them); `platform`'s own
    # module-scoped `_sweep_prefix` teardown drops this run's entire
    # throwaway database regardless, so this is not real residue.
    flip_app = provision_app(platform, "main_control_plane_flip_probe")
    # Q4 phase (design D-2(f), F-6): flipping ONLY this process' own
    # `MITATEDB_CONTROL_PLANE_STATUS` is no longer sufficient on its own
    # -- `surfaces.control`'s presence in the SHARED declarations row
    # must agree, or F-6 refuses to start (exactly the drift this phase
    # closes: a real deployment now re-declares surfaces via `ops
    # declare-surfaces --control-base-url <URL>` in the SAME operation as
    # flipping this status, §9.2). This test re-declares the row with a
    # `control` key added, mirroring that real operator action, before
    # calling `build_app` with the flipped status.
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                [
                    '{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"},'
                    '"control":{"base_url":"https://control.mitatedb-main-test.example.invalid/control/v1"}}'
                ],
            )
    finally:
        conn.close()
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": flip_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{flip_app.app_id.upper()}_RUNTIME_DSN": flip_app.runtime_dsn,
        f"MITATEDB_APP_{flip_app.app_id.upper()}_DEVELOPER_DSN": flip_app.developer_dsn,
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    try:
        app = main_module.build_app(env)
    finally:
        # Restore the shared row to its data-only baseline so every OTHER
        # test in this module-scoped fixture keeps seeing the default
        # (`unavailable`)-consistent declaration.
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                    ['{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"}}'],
                )
        finally:
            conn.close()

    write_store = PostgresCredentialStore(
        platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema,
    )
    try:
        credential_id, bearer = write_store.issue(flip_app.app_id, Role.RUNTIME)
    finally:
        write_store.close()

    import asyncio

    async def _call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

    response = asyncio.run(_call())
    assert response.status_code == 200, response.text
    assert response.json()["capabilities"]["control_plane"]["status"] == "enabled"


def test_build_app_wires_the_preauth_concurrency_slot(main_module, platform) -> None:
    """Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09, review
    round 2): `build_app` must wire `HttpService`'s own `limit_holder`/
    `max_concurrency` (`main.py`'s own `HttpService(...)` call, `:474`)
    onto the SAME `_LimitStateHolder` every served `ApplicationCell`
    shares, and this deployment's own real declared `max_concurrency` --
    not merely SOME non-`None` values `HttpService.__init__`'s own
    fail-closed guard happens to accept.

    Builds a SEPARATE, dedicated application (mirrors this file's own
    `main_control_plane_flip_probe` reasoning immediately above: this
    test's own persistent connections must not interfere with `main_
    module.app`'s already-built probe) with `MITATEDB_MAX_CONCURRENCY` set
    to a value (7) distinct from `FoundationConfig`'s own dataclass
    default (32), so a coincidental match against the untouched default
    cannot pass this test by accident.

    Mutation (review F-2's own pinned mutation, restated for the
    fail-closed constructor this round introduces): removing the `limit_
    holder=limit_holder, max_concurrency=config.max_concurrency` keywords
    from `main.py`'s own `HttpService(...)` call now turns this red at
    `build_app(...)` itself -- `HttpService.__init__`'s own fail-closed
    guard (`http.py`) raises `RuntimeError` before this function can even
    return an app to assert against, since a silent no-op is no longer
    accepted at construction time. This is a STRONGER red than round 1's
    own pinned shape (a passing-but-behaviorally-wrong app): the whole
    process now refuses to start.
    """
    wiring_app = provision_app(platform, "main_preauth_concurrency_probe")
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        "MITATEDB_SERVE_APPS": wiring_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{wiring_app.app_id.upper()}_RUNTIME_DSN": wiring_app.runtime_dsn,
        f"MITATEDB_APP_{wiring_app.app_id.upper()}_DEVELOPER_DSN": wiring_app.developer_dsn,
        "MITATEDB_MAX_CONCURRENCY": "7",
    }
    app = main_module.build_app(env)
    inner_app = app.app  # unwrap RequestByteBoundMiddleware -> the wrapped Starlette app
    service = inner_app.state.service
    assert service._limit_holder is not None
    assert service._max_concurrency == 7
    cell = service._cell_factory(wiring_app.app_id)
    assert cell._ApplicationCell__limit_holder is service._limit_holder


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
    # Q4 phase (design F-6): `build_control_service` unconditionally
    # requires `surfaces.control` -- `platform`'s own shared declaration
    # row is data-only (matching `test_main.py`'s OWN data-plane-default
    # baseline, `MITATEDB_CONTROL_PLANE_STATUS` unset) -- this test adds
    # `control` to that SAME row before calling the factory, then
    # restores it, so no other test in this module sees a lingering
    # control declaration.
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                [
                    '{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"},'
                    '"control":{"base_url":"https://control.mitatedb-main-test.example.invalid/control/v1"}}'
                ],
            )
    finally:
        conn.close()
    try:
        service = main_module.build_control_service(env)

        backend = service._backend  # test-only reach-in, mirroring this file's own existing conventions
        with backend.unit_of_work() as work:
            credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
        try:
            secret = bearer
            rotated = service.rotate_credential(secret, credential_id)
            rotated_secret = rotated["secret"]
            document = service.control_capabilities(rotated_secret)
            assert document["capabilities"]["control_plane"]["status"] == "enabled"
        finally:
            # Clean up so this factory-only credential does not linger in
            # the shared throwaway platform for the rest of the test
            # session.
            conn = psycopg.connect(platform.provision_dsn, autocommit=True)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
            finally:
                conn.close()
    finally:
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                    ['{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"}}'],
                )
        finally:
            conn.close()


def test_control_service_factory_rejects_identical_peppers(main_module, platform) -> None:
    """Pepper separation is checked BEFORE `surfaces` is ever read (design
    §3.7 control-plane steps 1-2 precede step 4) -- this raises
    regardless of the shared `platform` fixture's own data-only
    declaration, so no `control` re-declaration is needed here."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
    }
    with pytest.raises(ValueError):
        main_module.build_control_service(env)


def _independently_expected_operation_catalog_url(data_base_url: str) -> str:
    """Reads the packaged contract JSON directly (never through
    `mitatedb_api.operation_catalog.derive_operation_catalog_url`, so
    this test's own expectation cannot share a bug with the function it
    is pinning) and derives `data_base_url` BASE-RELATIVE (design/work
    order 訂正註 2026-09-25 (1)): `data_base_url` with its trailing
    contract `versioning.base_path` replaced by the full `endpoints.
    operation_catalog.path` -- never merely `data_base_url`'s origin
    plus `path`, which would drop a reverse-proxy prefix a `data_base_
    url` ahead of `versioning.base_path` might carry. Mirrors r2db-api's
    own `test_surfaces_env.py::_independently_expected_operation_catalog_
    url` in SHAPE, never in code (peer-symmetry isomorphism test)."""
    contract_path = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api" / "contract" / "data-service-api.v1.json"
    contract = json.loads(contract_path.read_text())
    base_path = contract["versioning"]["base_path"]
    path = contract["endpoints"]["operation_catalog"]["path"]
    assert data_base_url.endswith(base_path), f"{data_base_url!r} does not end with versioning.base_path {base_path!r}"
    return data_base_url[: -len(base_path)] + path


def test_data_and_control_documents_derive_the_same_operation_catalog_url_when_unset(main_module, platform) -> None:
    """With `MITATEDB_OPERATION_CATALOG_URL` UNSET on both `build_app`'s
    data plane and `build_control_service`'s control plane, both derive
    the SAME `operation_
    catalog_url` from `surfaces.data.base_url` alone -- this test's own
    expectation is computed independently (`_independently_expected_
    operation_catalog_url`), and a real GET against the derived path on
    the data plane serves the packaged operation catalog. The superseded
    formula (`data_base_url + endpoints.operation_catalog.path`,
    doubling `versioning.base_path`) would derive a 404'ing URL here --
    this is the peer-local regression guard for that defect."""
    derive_app = provision_app(platform, "main_opcat_derive_probe")
    data_base_url = "https://data.mitatedb-opcat-derive-test.example.invalid/v1"
    control_base_url = "https://control.mitatedb-opcat-derive-test.example.invalid/control/v1"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                [f'{{"data":{{"base_url":"{data_base_url}"}},"control":{{"base_url":"{control_base_url}"}}}}'],
            )
    finally:
        conn.close()
    try:
        expected_url = _independently_expected_operation_catalog_url(data_base_url)

        data_env = {
            "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
            "MITATEDB_PLATFORM_DSN": platform.api_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
            "MITATEDB_SERVE_APPS": derive_app.app_id,
            "MITATEDB_WORKERS": "1",
            "MITATEDB_SLOT_DIR": _SLOT_DIR,
            f"MITATEDB_APP_{derive_app.app_id.upper()}_RUNTIME_DSN": derive_app.runtime_dsn,
            f"MITATEDB_APP_{derive_app.app_id.upper()}_DEVELOPER_DSN": derive_app.developer_dsn,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        }
        app = main_module.build_app(data_env)

        control_env = {
            "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
            "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
        }
        control_service = main_module.build_control_service(control_env)

        from mitatedb_api.control_plane import bootstrap_control_credential

        # `platform` is a shared (module-scoped) fixture -- `bootstrap_
        # control_credential` refuses a second call once ANY control
        # credential row exists ("bootstrap runs at most once"); clear
        # any row a DIFFERENT test in this file/session left behind first.
        _precleanup = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with _precleanup.cursor() as cur:
                cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
        finally:
            _precleanup.close()

        backend = control_service._backend  # test-only reach-in, mirrors test_control_service_factory_builds_a_real_working_service above
        with backend.unit_of_work() as work:
            _control_credential_id, control_bearer = bootstrap_control_credential(
                backend.control_credential_store, backend.append_audit, work=work
            )
        try:
            control_document = control_service.control_capabilities(control_bearer)
        finally:
            conn2 = psycopg.connect(platform.provision_dsn, autocommit=True)
            try:
                with conn2.cursor() as cur:
                    cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
            finally:
                conn2.close()

        write_store = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema)
        try:
            _credential_id, bearer = write_store.issue(derive_app.app_id, Role.RUNTIME)
        finally:
            write_store.close()

        async def _call():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
                capabilities = await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})
                catalog = await client.get("/v1/operation-catalog", headers={"authorization": f"Bearer {bearer}"})
                return capabilities, catalog

        data_response, catalog_response = asyncio.run(_call())
        assert data_response.status_code == 200, data_response.text
        assert data_response.json()["operation_catalog_url"] == control_document["operation_catalog_url"] == expected_url
        assert catalog_response.status_code == 200, catalog_response.text
    finally:
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                    ['{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"}}'],
                )
        finally:
            conn.close()


def test_data_and_control_documents_agree_on_an_overridden_operation_catalog_url(main_module, platform) -> None:
    """Sibling of the test immediately above: with `MITATEDB_OPERATION_
    CATALOG_URL` SET on both processes,
    both echo that SAME override value -- the env var wins over the
    derivation."""
    override_app = provision_app(platform, "main_opcat_override_probe")
    data_base_url = "https://data.mitatedb-opcat-override-test.example.invalid/v1"
    control_base_url = "https://control.mitatedb-opcat-override-test.example.invalid/control/v1"
    override_url = "https://cdn.mitatedb-opcat-override-test.example.invalid/catalog/operation-catalog.json"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                [f'{{"data":{{"base_url":"{data_base_url}"}},"control":{{"base_url":"{control_base_url}"}}}}'],
            )
    finally:
        conn.close()
    try:
        data_env = {
            "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
            "MITATEDB_PLATFORM_DSN": platform.api_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
            "MITATEDB_SERVE_APPS": override_app.app_id,
            "MITATEDB_WORKERS": "1",
            "MITATEDB_SLOT_DIR": _SLOT_DIR,
            f"MITATEDB_APP_{override_app.app_id.upper()}_RUNTIME_DSN": override_app.runtime_dsn,
            f"MITATEDB_APP_{override_app.app_id.upper()}_DEVELOPER_DSN": override_app.developer_dsn,
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
            "MITATEDB_OPERATION_CATALOG_URL": override_url,
        }
        app = main_module.build_app(data_env)

        control_env = {
            "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
            "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
            "MITATEDB_OPERATION_CATALOG_URL": override_url,
        }
        control_service = main_module.build_control_service(control_env)

        from mitatedb_api.control_plane import bootstrap_control_credential

        # `platform` is a shared (module-scoped) fixture -- `bootstrap_
        # control_credential` refuses a second call once ANY control
        # credential row exists ("bootstrap runs at most once"); clear
        # any row a DIFFERENT test in this file/session left behind first.
        _precleanup = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with _precleanup.cursor() as cur:
                cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
        finally:
            _precleanup.close()

        backend = control_service._backend  # test-only reach-in, mirrors test_control_service_factory_builds_a_real_working_service above
        with backend.unit_of_work() as work:
            _control_credential_id, control_bearer = bootstrap_control_credential(
                backend.control_credential_store, backend.append_audit, work=work
            )
        try:
            control_document = control_service.control_capabilities(control_bearer)
        finally:
            conn2 = psycopg.connect(platform.provision_dsn, autocommit=True)
            try:
                with conn2.cursor() as cur:
                    cur.execute(f"DELETE FROM {platform.registry_schema}.control_credentials")
            finally:
                conn2.close()

        write_store = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PEPPER, schema=platform.registry_schema)
        try:
            _credential_id, bearer = write_store.issue(override_app.app_id, Role.RUNTIME)
        finally:
            write_store.close()

        async def _call():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
                return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

        data_response = asyncio.run(_call())
        assert data_response.status_code == 200, data_response.text
        assert data_response.json()["operation_catalog_url"] == control_document["operation_catalog_url"] == override_url
    finally:
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {platform.registry_schema}.platform_declarations SET value = %s WHERE key = 'surfaces'",
                    ['{"data":{"base_url":"https://data.mitatedb-main-test.example.invalid/v1"}}'],
                )
        finally:
            conn.close()


# ===========================================================================
# Phase 4 ledger closure WP-B3 (L4-7(ii), design §11.1 未起票 -- 作業指示書
# WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-7(ii) が正本): peer-symmetric
# counterpart of r2db-api's own `tests/test_audit_query.py`
# `test_data_plane_composition_root_does_not_import_the_control_credential_
# store` (same test name -- work order §4 WP-B3 completion condition 5/6).
# No fixture needed (a pure source-text read, no PostgreSQL, no import).
# ===========================================================================


_MITATEDB_FORBIDDEN_CONTROL_CREDENTIAL_IDENTIFIERS = frozenset(
    {"ControlCredentialStore", "PostgresControlCredentialStore", "ControlPlaneService"}
)
# Grounded in a real `grep` of this peer's own `src/mitatedb_api/` tree
# (review fix M4): `control_auth.py` (in-memory `ControlCredentialStore`)
# and `control_credential_store_postgres.py` (`PostgresControlCredential
# Store`) are dedicated modules with no legitimate reason to be imported
# by `main.py` (the DATA-plane root) at all -- unlike r2db-api, where the
# equivalent classes live inside already-legitimately-imported modules
# (`auth.py`/`credential_store.py`), so r2db-api's own module-name check
# covers only `control_plane`. `control_composition` is DELIBERATELY
# EXCLUDED here even though it is control-plane-only machinery: `main.py`
# legitimately imports `build_control_service` from it (`main.py:398`,
# kept for `test_main.py`'s own pre-existing call sites) -- checking that
# module name would false-positive on real, required code. The class-name
# check above still catches anything control-credential-shaped reached
# THROUGH `control_composition` (e.g. `control_composition.
# ControlPlaneService`, an `Attribute.attr` hit).
_MITATEDB_FORBIDDEN_CONTROL_CREDENTIAL_MODULES = frozenset({"control_auth", "control_credential_store_postgres", "control_plane"})


def _control_credential_vocabulary_hits(source: str, *, forbidden_identifiers: frozenset, forbidden_modules: frozenset) -> list:
    """AST-based replacement (review fix M4) for the prior bare
    case-insensitive substring check. Reasons this is a strictly STRONGER
    form than string-containment, not merely a different one:

    - A source-level string check cannot distinguish an actual Python
      reference (`ControlPlaneService(...)`) from an unrelated string
      literal that happens to contain the same characters -- THIS peer's
      own documented, legitimate `MITATEDB_CONTROL_CREDENTIAL_PEPPER` env
      var name (`main.py`'s own module docstring) only ever appears as an
      `ast.Constant` string argument (e.g. `env.get("MITATEDB_CONTROL_
      CREDENTIAL_PEPPER")`), which this walk never inspects at all -- no
      special-case stripping is needed any more (the prior revision's own
      `source.replace("MITATEDB_CONTROL_CREDENTIAL_PEPPER", "")` workaround
      is removed entirely).
    - `ast.parse` is used, never `import` -- `mitatedb_api.main` ends with
      a module-level `app = build_app()` that reads `os.environ`
      immediately on import (this function's own caller explains why
      below).
    - Checks BOTH import statements (`Import`/`ImportFrom` -- the module
      path itself, split on ".", and every imported name's own original
      AND locally-bound (`asname or name`) spelling) AND every other
      reference anywhere in the module body (`ast.Name.id`, `ast.
      Attribute.attr` -- catching `some_module.ControlPlaneService`-style
      access after a bare `import some_module`, which an import-statement-
      only check would miss). Identical implementation shape to r2db-api's
      own `tests/test_audit_query.py::_control_credential_vocabulary_hits`
      (not cross-imported -- this repository's own established
      no-code-sharing-between-peers convention), with this peer's own
      grep-verified vocabulary above."""
    import ast

    tree = ast.parse(source)
    hits: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(part in forbidden_modules for part in alias.name.split(".")):
                    hits.append(f"line {node.lineno}: import {alias.name!r}")
                bound = alias.asname or alias.name.split(".")[-1]
                if bound in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: import bound as {bound!r}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(part in forbidden_modules for part in module.split(".")):
                hits.append(f"line {node.lineno}: from {module!r} import ...")
            for alias in node.names:
                if alias.name in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: from {module!r} import {alias.name!r}")
                bound = alias.asname or alias.name
                if bound in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: bound as {bound!r}")
        elif isinstance(node, ast.Name):
            if node.id in forbidden_identifiers:
                hits.append(f"line {node.lineno}: Name {node.id!r}")
        elif isinstance(node, ast.Attribute):
            if node.attr in forbidden_identifiers:
                hits.append(f"line {node.lineno}: Attribute .{node.attr!r}")
    return hits


def test_data_plane_composition_root_does_not_import_the_control_credential_store() -> None:
    """D-5's own "壊れるシナリオ" (i), applied to this peer: the
    application-plane composition root must never gain a reference to the
    control-credential universe -- `ControlCredentialStore` (in-memory,
    `control_auth.py:99`), `PostgresControlCredentialStore` (`control_
    credential_store_postgres.py:65`), or `ControlPlaneService` (`control_
    plane.py`). Reads the SOURCE FILE directly (never `import mitatedb_api.
    main` -- that module ends with a module-level `app = build_app()`
    (`main.py:400`) that reads `os.environ` at import time), then
    `ast.parse`s it (never regex/substring, review fix M4 -- see
    `_control_credential_vocabulary_hits`'s own docstring for why this is
    strictly stronger, including why THIS peer's own documented
    `MITATEDB_CONTROL_CREDENTIAL_PEPPER` env-var name needs no special
    handling under this approach, unlike the prior substring-based
    revision)."""
    from pathlib import Path

    main_py = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api" / "main.py"
    source = main_py.read_text()
    hits = _control_credential_vocabulary_hits(
        source,
        forbidden_identifiers=_MITATEDB_FORBIDDEN_CONTROL_CREDENTIAL_IDENTIFIERS,
        forbidden_modules=_MITATEDB_FORBIDDEN_CONTROL_CREDENTIAL_MODULES,
    )
    assert not hits, f"mitatedb_api/main.py references the control-credential universe: {hits!r}"
