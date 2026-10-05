"""Phase 10 WP-6b (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
D-5 (ii)/(iii)/(iv), work order docs/work-orders/
WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6b): the deployer
declaration `process_ceilings` -- mechanism mirrors Q4 D-2 (`surfaces`):
the single source is `<registry>.platform_declarations`, written by `ops
declare-process-ceilings`, read at startup by both composition roots
(fail-fast, F-15, if the row is absent or malformed).

Three kinds of coverage, in three sections:

  (A) Pure-Python, no database: `validate_process_ceilings_value`'s own
      shape checks.
  (B) In-memory (`ApplicationCell(process_ceiling=...)`/`ControlPlaneService
      (process_ceiling=...)`, `SQLiteBackend`/`InMemoryControlBackend`):
      the ceiling -> `limit_enforcement` mapping (design D-5 (ii)'s own
      3-region table) -- fast, no PostgreSQL dependency, since the
      mapping itself is pure constructor-argument-driven logic.
  (C) Real PostgreSQL (`control_plane_harness.control_platform` / `test_
      postgres.platform`): row-existence fail-fast (F-15), a real
      composition-root round trip of the ceiling -> mapping (complementing
      (B)'s direct-construction version), `ops declare-process-ceilings`/
      `verify-declarations`, and -- the one completion condition that
      cannot be observed without a real database at all -- the DB-side
      lock that keeps `applications`/`credentials_per_application`
      genuinely `enforced` under concurrent writers. (`idempotency_
      entries`'s own same-key serialization + count lock is WP-6d-i, a
      separate WP -- out of scope here.)

Non-vacuity (常設規律 32): every parametrized assertion below observes at
least one real case; every completion condition has a paired mutation
recorded in this WP's own completion report (常設規律 33), not repeated
here as comments (the report is where "変異の赤 verbatim" is recorded).
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from .test_postgres import platform as data_platform, provision_app  # noqa: F401 (fixture, relative import -- see test_main.py's own identical rationale)
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import ApplicationCell, ApplicationRuntime
from mitatedb_api.auth import Principal, Role
from mitatedb_api.config import FoundationConfig
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService,
                                        InMemoryControlBackend, PostgresApplicationRegistry,
                                        PostgresControlBackend, PostgresCredentialRegistry,
                                        bootstrap_control_credential)
from mitatedb_api.errors import ResourceLimitError
from mitatedb_api.platform_declarations import (DEFAULT_SCHEMA, PEER_MODULE,
                                                PlatformDeclarationError,
                                                ProcessCeilings,
                                                validate_process_ceilings_value)

_APP_PEPPER = "process-ceilings-pg-app-pepper-x"
# `main.build_app` requires `MITATEDB_WORKERS`/`MITATEDB_SLOT_DIR`: one
# shared, real slot directory (mode 0700, `mkdtemp`'s own default),
# `workers=1` -- every ceiling this file declares (1 or 2) accepts
# `workers=1` at startup (only `workers > ceiling` fails).
_SLOT_DIR = tempfile.mkdtemp(prefix="mitatedb-test-slots-process-ceilings-")
_CONTROL_PEPPER = "process-ceilings-pg-ctl-pepper-x"

# region (i): request-scoped classes -- unaffected by `process_ceilings`
# (design D-5 (ii)'s own 3-region table, row 1).
_REGION_I_CLASSES = (
    "request_bytes", "operation_depth", "batch_items", "batch_entities",
    "result_items", "query_complexity", "schema_objects", "enum_members",
)
# region (ii): in-memory-per-process-bound classes -- `enforced` at
# ceiling 1, `deployment_required` at ceiling >= 2 (design D-5 (ii) row 2).
_REGION_II_DATA_CLASSES = ("concurrency", "requests_per_minute")
_REGION_II_CONTROL_CLASSES = ("control_requests_per_minute", "audit_requests_per_minute")
# region (iii): DB-side-bound classes -- `enforced` regardless of ceiling,
# held there by a lock (design D-5 (ii) row 3).
_REGION_III_CONTROL_CLASSES = ("applications", "credentials_per_application")


# ===========================================================================
# (A) Pure-Python: `validate_process_ceilings_value` shape checks.
# ===========================================================================


@pytest.mark.parametrize("bad_value", [
    {},                                    # missing both keys
    {"data": 1},                           # missing `control`
    {"control": 1},                        # missing `data`
    {"data": 1, "control": 1, "extra": 1},  # an extra key
    {"data": 0, "control": 1},             # `data` below 1
    {"data": 1, "control": 0},             # `control` below 1
    {"data": -1, "control": 1},            # negative
    {"data": True, "control": 1},          # bool, not int (Python `bool` is an `int` subclass)
    {"data": 1.5, "control": 1},           # float
    {"data": "1", "control": 1},           # string
    "not-a-dict",                          # wrong type entirely
    ["data", "control"],                   # wrong type entirely
])
def test_validate_process_ceilings_value_rejects(bad_value) -> None:
    with pytest.raises(PlatformDeclarationError, match="process_ceilings") as exc:
        validate_process_ceilings_value(bad_value, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert exc.value.code == "F-15"


def test_validate_process_ceilings_value_accepts_the_minimum_shape() -> None:
    result = validate_process_ceilings_value({"data": 1, "control": 1}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert result == ProcessCeilings(data=1, control=1)


def test_validate_process_ceilings_value_accepts_a_larger_ceiling() -> None:
    result = validate_process_ceilings_value({"data": 3, "control": 2}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert result == ProcessCeilings(data=3, control=2)


def test_f15_message_names_the_next_ops_command() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_process_ceilings_value({"data": 0, "control": 1}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert "python -m mitatedb_api.ops declare-process-ceilings" in str(exc.value)


# ===========================================================================
# (B) In-memory: ceiling -> `limit_enforcement` mapping (design D-5 (ii)).
# Completion conditions 2/3 -- direct construction, no PostgreSQL needed.
# ===========================================================================


def _data_plane_limit_enforcement(process_ceiling: int) -> dict:
    cell = ApplicationCell("pc_probe", FoundationConfig(), process_ceiling=process_ceiling)
    principal = Principal(application_id="pc_probe", credential_id="pc_probe_cred", role=Role.RUNTIME)
    runtime = ApplicationRuntime(cell, principal)
    return runtime.capabilities()["limit_enforcement"]


def test_ceiling_one_maps_data_plane_in_memory_classes_to_enforced() -> None:
    enforcement = _data_plane_limit_enforcement(1)
    for name in _REGION_II_DATA_CLASSES:
        assert enforcement[name] == "enforced", (name, enforcement[name])


@pytest.mark.parametrize("ceiling", [2, 3])
def test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required(ceiling) -> None:
    enforcement = _data_plane_limit_enforcement(ceiling)
    for name in _REGION_II_DATA_CLASSES:
        assert enforcement[name] == "deployment_required", (ceiling, name, enforcement[name])


def test_data_plane_default_process_ceiling_is_one() -> None:
    """Every pre-existing direct construction of `ApplicationCell` (this
    repository's own tests, the in-process conformance adapter) never
    passes `process_ceiling` at all -- the default must keep declaring
    `enforced`, unchanged from before this WP."""
    cell = ApplicationCell("pc_default_probe")
    assert cell.process_ceiling == 1


@pytest.mark.parametrize("ceiling", [1, 2])
def test_region_i_classes_are_unaffected_by_ceiling(ceiling) -> None:
    enforcement = _data_plane_limit_enforcement(ceiling)
    for name in _REGION_I_CLASSES:
        assert enforcement[name] == "enforced", (ceiling, name, enforcement[name])


def _control_plane_limit_enforcement(process_ceiling: int) -> dict:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with backend.unit_of_work() as work:
        _credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, process_ceiling=process_ceiling)
    rotated = service.rotate_credential(bearer, _credential_id)
    document = service.control_capabilities(rotated["secret"])
    return document["limit_enforcement"]


def test_ceiling_one_maps_control_plane_in_memory_classes_to_enforced() -> None:
    enforcement = _control_plane_limit_enforcement(1)
    for name in _REGION_II_CONTROL_CLASSES:
        assert enforcement[name] == "enforced", (name, enforcement[name])
    for name in _REGION_III_CONTROL_CLASSES:
        assert enforcement[name] == "enforced", (name, enforcement[name])


@pytest.mark.parametrize("ceiling", [2, 3])
def test_ceiling_two_maps_control_plane_in_memory_classes_to_deployment_required(ceiling) -> None:
    enforcement = _control_plane_limit_enforcement(ceiling)
    for name in _REGION_II_CONTROL_CLASSES:
        assert enforcement[name] == "deployment_required", (ceiling, name, enforcement[name])
    # region (iii): unaffected by ceiling, unlike region (ii) immediately
    # above -- the SAME service, at the SAME (elevated) ceiling.
    for name in _REGION_III_CONTROL_CLASSES:
        assert enforcement[name] == "enforced", (ceiling, name, enforcement[name])


def test_control_plane_default_process_ceiling_is_one() -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend)
    assert service._process_ceiling == 1  # noqa: SLF001 -- this WP's own new attribute, no public accessor exists (mirrors `_limits`)


# ===========================================================================
# (C) Real PostgreSQL.
# ===========================================================================


@pytest.fixture
def control_backend(control_platform) -> Iterator[PostgresControlBackend]:
    applications = PostgresApplicationRegistry(control_platform.controlplane_dsn, schema=control_platform.registry_schema)
    credentials = PostgresCredentialRegistry(control_platform.controlplane_dsn, pepper=_APP_PEPPER,
                                             schema=control_platform.registry_schema)
    control_credentials = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER,
                                                         schema=control_platform.registry_schema)
    yield PostgresControlBackend(applications=applications, credentials=credentials,
                                 control_credentials=control_credentials,
                                 audit_schema=control_platform.registry_schema, dsn=control_platform.controlplane_dsn)
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
            cur.execute(f"DELETE FROM {schema}.control_audit")
    finally:
        conn.close()


def _bootstrapped_control_service(backend, limits=None) -> tuple[ControlPlaneService, str]:
    with backend.unit_of_work() as work:
        credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=limits or ControlPlaneLimits(
        applications=100, credentials_per_application=100, control_requests_per_minute=5000))
    rotated = service.rotate_credential(bearer, credential_id)
    return service, rotated["secret"]


def _set_declaration(platform_info, key: str, value_json: str) -> None:
    conn = psycopg.connect(platform_info.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value) VALUES (%s, %s::jsonb) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
                ).format(table=sql.Identifier(platform_info.registry_schema, "platform_declarations")),
                (key, value_json),
            )
    finally:
        conn.close()


def _delete_declaration(platform_info, key: str) -> None:
    conn = psycopg.connect(platform_info.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE key = %s").format(
                    table=sql.Identifier(platform_info.registry_schema, "platform_declarations")),
                (key,),
            )
    finally:
        conn.close()


# ---- F-15: missing row fails startup, real composition root -------------


def test_missing_row_fails_fast_at_startup_control_plane(control_platform) -> None:
    """Completion condition 1, control-plane half: `build_control_service`
    -- the SAME `read_platform_declarations` call both composition roots
    make -- fails fast with F-15 when `process_ceilings` is absent. The
    fixture's own seed (`control_plane_harness.bootstrap_control_platform`)
    is restored in `finally` so no other test in this module (or a module
    reusing the SAME `control_platform` fixture instance) observes the
    deletion."""
    import mitatedb_api.control_composition as control_composition_module

    _delete_declaration(control_platform, "process_ceilings")
    try:
        env = {
            "MITATEDB_CREDENTIAL_PEPPER": "synthetic-pc-f15-pepper",
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "synthetic-pc-f15-ctl-pepper",
            "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
        }
        with pytest.raises(PlatformDeclarationError) as exc:
            control_composition_module.build_control_service(env)
        assert exc.value.code == "F-15"
        assert "no 'process_ceilings' row" in str(exc.value)
    finally:
        _set_declaration(control_platform, "process_ceilings", '{"data": 1, "control": 1}')


def _main_module_for(platform, probe_app):
    """Guarded first import (`test_main.py`'s own identical precedent,
    this file's own duplicate -- no cross-module import taken, matching
    this repository's own `test_http.py`/`test_main.py` established
    convention of NOT importing `test_main.py` itself): `mitatedb_api.
    main`'s own module-level `app = build_app()` statement runs on first
    import, and would otherwise demand real environment this fixture's
    own throwaway platform/app must supply first."""
    if "mitatedb_api.main" not in sys.modules:
        import os
        previous = dict(os.environ)
        try:
            os.environ.update({
                "MITATEDB_CREDENTIAL_PEPPER": "synthetic-pc-main-import-pepper",
                "MITATEDB_PLATFORM_DSN": platform.api_dsn,
                "MITATEDB_PLATFORM_SCHEMA": platform.registry_schema,
                "MITATEDB_SERVE_APPS": probe_app.app_id,
                "MITATEDB_WORKERS": "1",
                "MITATEDB_SLOT_DIR": _SLOT_DIR,
                f"MITATEDB_APP_{probe_app.app_id.upper()}_RUNTIME_DSN": probe_app.runtime_dsn,
                f"MITATEDB_APP_{probe_app.app_id.upper()}_DEVELOPER_DSN": probe_app.developer_dsn,
            })
            import mitatedb_api.main  # noqa: F401
        finally:
            os.environ.clear()
            os.environ.update(previous)
    import mitatedb_api.main as main_module
    return main_module


@pytest.fixture(scope="module")
def pc_data_probe_app(data_platform):
    return provision_app(data_platform, "pc_data_probe")


def _data_plane_env(data_platform, probe_app) -> dict:
    return {
        "MITATEDB_CREDENTIAL_PEPPER": "synthetic-pc-data-pepper",
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "synthetic-pc-data-ctl-pepper",
        "MITATEDB_PLATFORM_DSN": data_platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": data_platform.registry_schema,
        "MITATEDB_SERVE_APPS": probe_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{probe_app.app_id.upper()}_RUNTIME_DSN": probe_app.runtime_dsn,
        f"MITATEDB_APP_{probe_app.app_id.upper()}_DEVELOPER_DSN": probe_app.developer_dsn,
    }


def test_missing_row_fails_fast_at_startup_data_plane(data_platform, pc_data_probe_app) -> None:
    """Completion condition 1, data-plane half: `main.build_app` reaches
    the identical `read_platform_declarations` call site."""
    main_module = _main_module_for(data_platform, pc_data_probe_app)
    _delete_declaration(data_platform, "process_ceilings")
    try:
        with pytest.raises(PlatformDeclarationError) as exc:
            main_module.build_app(_data_plane_env(data_platform, pc_data_probe_app))
        assert exc.value.code == "F-15"
    finally:
        _set_declaration(data_platform, "process_ceilings", '{"data": 1, "control": 1}')


# ---- ceiling -> mapping, through a REAL composition root -----------------


def test_ceiling_two_maps_through_a_real_composition_root_control_plane(control_platform) -> None:
    """Completion condition 2, exercised via the REAL `build_control_
    service` entry point this time (complementing (B)'s direct-
    construction unit test) -- proves the wiring from the declared table
    row through to the served document, not only the mapping function in
    isolation."""
    import mitatedb_api.control_composition as control_composition_module

    _set_declaration(control_platform, "process_ceilings", '{"data": 1, "control": 2}')
    # F-16 multiplies controlplane's own floor by `process_ceilings.
    # control` (2): 16*2=32 is above the role's CONNECTION LIMIT (20 from
    # 0012), so the limit is raised to 32 here for this test's own
    # control-plane mapping assertion to be reached, and put back to the
    # value read below in `finally` (the `control_platform` fixture is
    # shared by later tests).
    controlplane_role = f"{control_platform.prefix}svc_controlplane"
    with psycopg.connect(control_platform.admin_dsn, autocommit=True) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname = %s", [controlplane_role])
            (original_connlimit,) = _cur.fetchone()
            _cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 32").format(sql.Identifier(controlplane_role)))
    try:
        env = {
            "MITATEDB_CREDENTIAL_PEPPER": "synthetic-pc-ceiling2-pepper",
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "synthetic-pc-ceiling2-ctl-pepper",
            "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
        }
        service = control_composition_module.build_control_service(env)
        with service._backend.unit_of_work() as work:  # noqa: SLF001
            credential_id, bearer = bootstrap_control_credential(
                service._backend.control_credential_store, service._backend.append_audit, work=work)  # noqa: SLF001
        rotated = service.rotate_credential(bearer, credential_id)
        document = service.control_capabilities(rotated["secret"])
        for name in _REGION_II_CONTROL_CLASSES:
            assert document["limit_enforcement"][name] == "deployment_required", name
        for name in _REGION_III_CONTROL_CLASSES:
            assert document["limit_enforcement"][name] == "enforced", name
    finally:
        with psycopg.connect(control_platform.admin_dsn, autocommit=True) as _conn:
            with _conn.cursor() as _cur:
                _cur.execute(
                    sql.SQL("ALTER ROLE {} CONNECTION LIMIT {}").format(
                        sql.Identifier(controlplane_role), sql.Literal(int(original_connlimit))
                    )
                )
        _set_declaration(control_platform, "process_ceilings", '{"data": 1, "control": 1}')
        conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                schema = control_platform.registry_schema
                cur.execute(f"DELETE FROM {schema}.credentials")
                cur.execute(f"DELETE FROM {schema}.control_credentials")
                cur.execute(f"DELETE FROM {schema}.applications")
                cur.execute(f"DELETE FROM {schema}.control_audit")
        finally:
            conn.close()


def test_ceiling_asymmetric_declaration_maps_through_a_real_composition_root_data_plane(
    data_platform, pc_data_probe_app,
) -> None:
    """M-1 (review `scratchpad/phase10/wp6b-review.md`): `main.py`'s own
    `ApplicationCell(..., process_ceiling=declarations.process_ceilings.
    data)` wiring was, before this test, unpinned by ANY test -- every
    fixture in this file seeded a SYMMETRIC `{"data": N, "control": N}`
    value, so a plane mix-up (reading `.control` where `.data` belongs, or
    a constant `1` that ignores the declaration outright) could not turn
    any assertion red. This test declares an ASYMMETRIC `{"data": 2,
    "control": 1}` row and drives the REAL data-plane composition root
    (`main.build_app`) through a genuine authenticated HTTP request
    (`GET /v1/capabilities`, `httpx.ASGITransport`) -- the data plane's
    own `concurrency` must read `deployment_required` (its OWN declared
    value, 2, above this composition root's `MITATEDB_WORKERS=1`), never
    `enforced` (what reading the CONTROL side's 1, or a hardcoded
    default, would wrongly produce). `requests_per_minute` reads
    `enforced`: `main.build_app` always wires the PostgreSQL-backed rate
    row (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (4)), which
    holds at any declared ceiling.

    Mutation: swapping the `process_ceiling=declarations.process_ceilings.
    data` keyword `main.py::build_app` passes to `ApplicationCell` for `.control` (or for a literal `1`) makes this test's own
    `deployment_required` assertion fail -- `test_process_ceilings_
    declaration.py`'s pre-existing `_data_plane_limit_enforcement`-based
    tests above cannot catch this because they never go through
    `read_platform_declarations`/`main.build_app` at all (direct
    `ApplicationCell(process_ceiling=...)` construction), and the control-
    plane composition-root test above cannot catch it either (it exercises
    only `.control`, never `.data`)."""
    import asyncio

    import httpx

    main_module = _main_module_for(data_platform, pc_data_probe_app)
    _set_declaration(data_platform, "process_ceilings", '{"data": 2, "control": 1}')
    try:
        app = main_module.build_app(_data_plane_env(data_platform, pc_data_probe_app))

        write_store = PostgresCredentialStore(
            data_platform.controlplane_dsn, pepper="synthetic-pc-data-pepper", schema=data_platform.registry_schema,
        )
        try:
            _credential_id, bearer = write_store.issue(pc_data_probe_app.app_id, Role.RUNTIME)
        finally:
            write_store.close()

        async def _call():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"})

        response = asyncio.run(_call())
        assert response.status_code == 200, response.text
        enforcement = response.json()["limit_enforcement"]
        assert enforcement["concurrency"] == "deployment_required", enforcement["concurrency"]
        assert enforcement["requests_per_minute"] == "enforced", enforcement["requests_per_minute"]
        # Region (i) stays unaffected regardless of plane or ceiling value
        # (the SAME pin `test_region_i_classes_are_unaffected_by_ceiling`
        # already holds for direct construction -- this proves it also
        # holds through the real composition root).
        assert enforcement["request_bytes"] == "enforced"
    finally:
        _set_declaration(data_platform, "process_ceilings", '{"data": 1, "control": 1}')


# ---- the table is the only source (no env fallback) -----------------------


def test_declaration_table_is_the_only_source(control_platform) -> None:
    """Completion condition 6: an env var that COULD plausibly be read as
    a `process_ceilings` fallback (a plausible name this peer has never
    defined) must have no effect at all -- only the table row does.
    `reject_removed_timeout_env`/`reject_removed_surface_env` reject two
    SPECIFIC, already-removed names; this is a different property (no NEW
    fallback exists for THIS row) that those two functions do not cover."""
    import mitatedb_api.control_composition as control_composition_module

    env = {
        "MITATEDB_CREDENTIAL_PEPPER": "synthetic-pc-envfallback-pepper",
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "synthetic-pc-envfallback-ctl-pepper",
        "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
        # A plausible-looking env var this peer has never defined for this
        # row -- if any fallback existed, it would disagree with the
        # table's own seeded `{"data": 1, "control": 1}` and be observed
        # below.
        "MITATEDB_PROCESS_CEILINGS": '{"data": 9, "control": 9}',
        "MITATEDB_CONTROL_PROCESS_CEILING": "9",
    }
    service = control_composition_module.build_control_service(env)
    with service._backend.unit_of_work() as work:  # noqa: SLF001
        credential_id, bearer = bootstrap_control_credential(
            service._backend.control_credential_store, service._backend.append_audit, work=work)  # noqa: SLF001
    rotated = service.rotate_credential(bearer, credential_id)
    document = service.control_capabilities(rotated["secret"])
    # ceiling 1 (the table's own row) -> `enforced`, never `deployment_
    # required` (which a ceiling of 9 taken from the bogus env vars above
    # would produce).
    for name in _REGION_II_CONTROL_CLASSES:
        assert document["limit_enforcement"][name] == "enforced", name
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
            cur.execute(f"DELETE FROM {schema}.control_audit")
    finally:
        conn.close()


# ---- `ops declare-process-ceilings` / `verify-declarations` ---------------


def test_declare_process_ceilings_round_trip(control_platform) -> None:
    """Completion condition 6 (round trip half): `ops declare-process-
    ceilings` writes exactly the row `read_platform_declarations` reads
    back."""
    import os
    import subprocess
    from pathlib import Path

    src_dir = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")
    env["MITATEDB_PROVISION_DSN"] = control_platform.provision_dsn
    env["MITATEDB_PLATFORM_SCHEMA"] = control_platform.registry_schema
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mitatedb_api.ops", "declare-process-ceilings", "--data", "2", "--control", "3"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, result.stderr
        assert "process_ceilings declared" in result.stdout

        conn = psycopg.connect(control_platform.provision_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT value FROM {table} WHERE key = 'process_ceilings'").format(
                        table=sql.Identifier(control_platform.registry_schema, "platform_declarations")))
                (value,) = cur.fetchone()
        finally:
            conn.close()
        assert value == {"data": 2, "control": 3}
    finally:
        _set_declaration(control_platform, "process_ceilings", '{"data": 1, "control": 1}')


def test_declare_process_ceilings_rejects_a_zero_value(control_platform) -> None:
    import os
    import subprocess

    from pathlib import Path

    src_dir = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")
    env["MITATEDB_PROVISION_DSN"] = control_platform.provision_dsn
    env["MITATEDB_PLATFORM_SCHEMA"] = control_platform.registry_schema
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", "declare-process-ceilings", "--data", "0", "--control", "1"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 2
    assert "process_ceilings" in result.stderr


def test_verify_declarations_f15_exit_code(control_platform) -> None:
    """Completion condition 7: `ops verify-declarations` returns F-15's
    own fixed exit code (14) when `process_ceilings` is absent."""
    import mitatedb_api.ops as ops

    _delete_declaration(control_platform, "process_ceilings")
    try:
        import os

        old = os.environ.get("MITATEDB_PROVISION_DSN")
        old_schema = os.environ.get("MITATEDB_PLATFORM_SCHEMA")
        os.environ["MITATEDB_PROVISION_DSN"] = control_platform.provision_dsn
        os.environ["MITATEDB_PLATFORM_SCHEMA"] = control_platform.registry_schema
        try:
            rc = ops.main(["verify-declarations"])
        finally:
            if old is None:
                os.environ.pop("MITATEDB_PROVISION_DSN", None)
            else:
                os.environ["MITATEDB_PROVISION_DSN"] = old
            if old_schema is None:
                os.environ.pop("MITATEDB_PLATFORM_SCHEMA", None)
            else:
                os.environ["MITATEDB_PLATFORM_SCHEMA"] = old_schema
        assert rc == 14
    finally:
        _set_declaration(control_platform, "process_ceilings", '{"data": 1, "control": 1}')


# ===========================================================================
# (D) Region (iii): DB-side lock under concurrent writers. Completion
# condition 4 -- the ONE property that genuinely needs real concurrency
# against real PostgreSQL, since a single-connection/in-memory backend
# cannot reproduce the phantom-write window `applications_count_locked`/
# `credentials_active_count_locked`'s own close. (`idempotency_entries`'s own same-key
# serialization + count lock is WP-6d-i -- out of scope here.)
# ===========================================================================


def test_db_side_bounds_hold_under_concurrent_writers_applications(control_backend) -> None:
    """`applications` (design D-5 (iii)): N threads race to register N
    DIFFERENT application ids against a capacity of 1 -- exactly one must
    succeed, and every other must fail with `ResourceLimitError(limit_
    class="applications")`, never a silent over-limit (more than one
    committed row) and never an unrelated exception (a raw
    `DeadlockDetected`, say)."""
    service, secret = _bootstrapped_control_service(
        control_backend, limits=ControlPlaneLimits(applications=1, credentials_per_application=1, control_requests_per_minute=5000))
    n = 6
    barrier = threading.Barrier(n)

    def _attempt(i: int):
        barrier.wait(timeout=10)
        try:
            service.register_application(secret, f"pcconc{i}")
            return ("ok", None)
        except ResourceLimitError as exc:
            return ("limit", exc.details.get("limit_class"))
        except Exception as exc:  # pragma: no cover -- observed only under a real defect
            return ("error", repr(exc))

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(_attempt, range(n)))

    outcomes = [kind for kind, _ in results]
    assert outcomes.count("ok") == 1, results
    assert outcomes.count("limit") == n - 1, results
    assert all(detail == "applications" for kind, detail in results if kind == "limit"), results
    assert "error" not in outcomes, results
    # The committed count itself, independent of what each thread observed
    # (the strongest form of this assertion): never more than the declared
    # bound.
    assert control_backend.applications_count() == 1


def test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application(control_backend) -> None:
    """`credentials_per_application` (design D-5 (iii)): the SAME race,
    one level down -- N threads race to issue N credentials for ONE
    already-registered application against a capacity of 1."""
    service, secret = _bootstrapped_control_service(
        control_backend, limits=ControlPlaneLimits(applications=10, credentials_per_application=1, control_requests_per_minute=5000))
    service.register_application(secret, "pcconccred")
    n = 6
    barrier = threading.Barrier(n)

    def _attempt(_i: int):
        barrier.wait(timeout=10)
        try:
            service.issue_credential(secret, "pcconccred", "runtime")
            return ("ok", None)
        except ResourceLimitError as exc:
            return ("limit", exc.details.get("limit_class"))
        except Exception as exc:  # pragma: no cover
            return ("error", repr(exc))

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(_attempt, range(n)))

    outcomes = [kind for kind, _ in results]
    assert outcomes.count("ok") == 1, results
    assert outcomes.count("limit") == n - 1, results
    assert all(detail == "credentials_per_application" for kind, detail in results if kind == "limit"), results
    assert "error" not in outcomes, results
    assert control_backend.credentials_active_count("pcconccred") == 1


@pytest.mark.parametrize("capacity", [1, 2])
def test_db_side_lock_holds_under_barrier_synchronized_two_writers_applications(control_backend, capacity: int) -> None:
    """Supervisor ruling `scratchpad/phase10/wp6-rulings.md` #2 (completion
    condition 4's own acceptance form): exactly TWO writers, `threading.
    Barrier`-synchronized so both attempt `register_application` at the
    same instant, against a `capacity` that may or may not admit both. The
    ONLY two valid outcomes are (a) `capacity >= 2`: BOTH succeed (bound
    not yet reached), or (b) `capacity == 1`: exactly one succeeds and the
    other hits `LIMIT_EXCEEDED` (bound reached) -- never a deadlock, never
    an unexpected 503, and never a committed count exceeding `capacity`
    (the phantom-write window the table-scoped advisory lock closes).
    Mutation: removing the advisory lock (`_take_bound_advisory_lock`'s
    own call site in `count_locked`) lets `capacity == 1` observe BOTH
    threads succeed (a genuine over-count, `ok_count == 2 > capacity`) --
    this test goes red."""
    service, secret = _bootstrapped_control_service(
        control_backend, limits=ControlPlaneLimits(applications=capacity, credentials_per_application=capacity, control_requests_per_minute=5000))
    n = 2
    barrier = threading.Barrier(n)

    def _attempt(i: int):
        barrier.wait(timeout=10)
        try:
            service.register_application(secret, f"pcbarrierapp{capacity}{i}")
            return ("ok", None)
        except ResourceLimitError as exc:
            return ("limit", exc.details.get("limit_class"))
        except Exception as exc:  # pragma: no cover -- observed only under a real defect
            return ("error", repr(exc))

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(_attempt, range(n)))

    outcomes = [kind for kind, _ in results]
    assert "error" not in outcomes, results
    ok_count = outcomes.count("ok")
    assert ok_count == min(n, capacity), results
    assert outcomes.count("limit") == n - ok_count, results
    assert all(detail == "applications" for kind, detail in results if kind == "limit"), results
    assert control_backend.applications_count() == ok_count


@pytest.mark.parametrize("capacity", [1, 2])
def test_db_side_lock_holds_under_barrier_synchronized_two_writers_credentials_per_application(control_backend, capacity: int) -> None:
    """The `credentials_per_application` counterpart of the barrier test
    above -- see that test's own docstring for the full rationale."""
    service, secret = _bootstrapped_control_service(
        control_backend, limits=ControlPlaneLimits(applications=10, credentials_per_application=capacity, control_requests_per_minute=5000))
    service.register_application(secret, f"pcbarriercred{capacity}")
    n = 2
    barrier = threading.Barrier(n)

    def _attempt(_i: int):
        barrier.wait(timeout=10)
        try:
            service.issue_credential(secret, f"pcbarriercred{capacity}", "runtime")
            return ("ok", None)
        except ResourceLimitError as exc:
            return ("limit", exc.details.get("limit_class"))
        except Exception as exc:  # pragma: no cover
            return ("error", repr(exc))

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(_attempt, range(n)))

    outcomes = [kind for kind, _ in results]
    assert "error" not in outcomes, results
    ok_count = outcomes.count("ok")
    assert ok_count == min(n, capacity), results
    assert outcomes.count("limit") == n - ok_count, results
    assert all(detail == "credentials_per_application" for kind, detail in results if kind == "limit"), results
    assert control_backend.credentials_active_count(f"pcbarriercred{capacity}") == ok_count


# `idempotency_entries`'s own same-key serialization + count lock is WP-6d-i (a separate WP, not this one).
