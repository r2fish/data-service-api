"""Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
D-5(ii)/(iii)/(iv), work order docs/work-orders/
WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md WP-6a): the deployer
declaration `process_ceilings` -- contract 1.8.0's enforcement-scope
definition made concrete. Same mechanism as `surfaces`/`audit_
coalescing_window_ms` (Q4 D-2): a single-source declaration table row,
written only via `ops declare-process-ceilings`, read at startup by both
composition roots, validated by the SAME Python function on the write
path and every read path (`platform_declarations.validate_process_
ceilings_value`).

Own file, own fixtures (mirrors `test_ops_verify_declarations.py`'s own
"separate from WP-1's declaration-series file" convention) -- this file is
NOT shared with `test_ops_declarations.py`/`test_surfaces_env.py`.

Scope (WP-6a is r2db-api only; MitateDB-api is WP-6b's own file):

  1. `validate_process_ceilings_value` shape checks (pure, no PostgreSQL).
  2. Startup fail-fast (F-15) when the row is missing.
  3. The 3-region `limit_enforcement` mapping (design D-5(ii)):
     region (i) request-scoped classes are unaffected by the ceiling;
     region (ii) in-memory-per-process classes read `enforced` at ceiling
     1 and `deployment_required` at ceiling >= 2, for BOTH planes;
     region (iii) DB-side-bound classes stay `enforced` regardless --
     `applications`/`credentials_per_application`'s check-then-write is
     lock-protected by this same WP; `idempotency_entries` is also
     `enforced` (it does not resolve within one request either) but its
     own check-then-write lock is WP-6d-i's scope (both peers, one pass),
     not added here (supervisory ruling 2026-09-08).
  4. `ops declare-process-ceilings` round trip, rejection of non-positive
     values, and that the declaration table is the ONLY source (no env
     fallback).
  5. `ops verify-declarations`'s new F-15 check and its exit code (14).
  6. The lock this WP adds to the two region-(iii) classes it locks
     itself (`applications`/`credentials_per_application`, both in
     `control_plane.py`) actually blocks a concurrent lock-taker -- a
     second connection's own `count_locked`/`count_active_for_
     application_locked` call blocks on `LockNotAvailable` while the
     first holds the table-scoped constant-key `pg_advisory_xact_lock`,
     then succeeds immediately once the first ends. `idempotency_
     entries`'s own lock observation is WP-6d-i's, not this file's.
  7. (Review finding F2, supervisor ruling `scratchpad/phase10/wp6-
     rulings.md` #2) the ACTUAL check-then-write body (`register_
     application` x2 / `issue_credential` x2), barrier-synchronized so
     both run concurrently against a bound of "current count + 1": never
     a deadlock, never a leaked `SERVICE_UNAVAILABLE`, and the bound is
     never exceeded (exactly one call succeeds, the other observes
     `LIMIT_EXCEEDED`). Section 6 above only proves a second lock-taker
     blocks; this proves the lock actually keeps the bound intact under
     real concurrent traffic.
  8. (Review finding F3, supervisor ruling `scratchpad/phase10/wp6-
     rulings.md` #3) the CONTROL-plane ceiling mapping through the real
     composition root (`control_main.build_control_app`, real HTTP),
     with an asymmetric `{"data": 1, "control": 2}` ceiling, pinning that
     `declarations.process_ceilings.control` (never `.data`) drives it --
     `test_control_plane_ceiling_mapping` above injects `process_ceiling`
     directly and so never exercises that composition-root read.

Migration `0008_process_ceilings.sql`'s own naming-convention static test
(platform single-shot, never `*_upgrade.sql`) lives in this repository's
existing `test_platform_upgrade_ledger_scan.py` (completion condition 8) --
not duplicated here.
"""
from __future__ import annotations

import json
import secrets
import subprocess
import sys
import threading
import types
from pathlib import Path
from typing import Any, Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

import r2db_api.ops as ops
from r2db_api.control_plane import ControlPlaneService, PostgresControlBackend
from r2db_api.credential_store import (
    PostgresApplicationRegistry,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
    _PostgresWork,
    _take_bound_advisory_lock,
    compose_bearer_locator,
)
from r2db_api.errors import FoundationError
from r2db_api.limits import ControlPlaneLimits, ResourceLimits
from r2db_api.platform_declarations import (
    PROCESS_CEILINGS_MIGRATION_NUMBER,
    PlatformDeclarationError,
    ProcessCeilings,
    read_platform_declarations,
    validate_process_ceilings_value,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
PEPPER = "synthetic-test-pepper-process-ceilings-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-process-ceilings-ctl-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    "0008_platform_declarations_and_writer_timeouts.sql",
    "0012_process_ceilings.sql",
)

_DATA_URL = "https://r2db-process-ceilings-test.example.invalid/v1"
_CONTROL_URL = "https://r2db-process-ceilings-control-test.example.invalid/control/v1"
_DEFAULT_SURFACES_VALUE = {"data": {"base_url": _DATA_URL}, "control": {"base_url": _CONTROL_URL}}
_DEFAULT_CEILINGS_VALUE = {"data": 1, "control": 1}


# ---------------------------------------------------------------------------
# fixture plumbing (mirrors test_ops_verify_declarations.py/test_audit_
# query.py's own established shape -- see those files for the full
# rationale of each helper)
# ---------------------------------------------------------------------------


def _admin_dsn() -> str:
    import os

    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_process_ceilings_declaration.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            for (database,) in cur.fetchall():
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            for (role,) in cur.fetchall():
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """A single throwaway platform, migrated through `0008`+`0012`, with
    `surfaces` (both planes) and `process_ceilings` (`{"data": 1,
    "control": 1}`, the single-uvicorn default) seeded -- the healthy
    baseline every test in this file starts from. Tests that need a
    DIFFERENT ceiling, or no row at all, mutate it and restore this
    default in a `finally` (this fixture is module-scoped and shared)."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbpceil{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_pceil_migrations")
    rewritten: dict[str, Path] = {}
    for name in MIGRATION_NAMES:
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
        _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
        _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
        _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
        _run_psql(control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(control_dsn, rewritten["0012_process_ceilings.sql"])
        with psycopg.connect(control_dsn) as _seed_conn:
            with _seed_conn.cursor() as _seed_cur:
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_CEILINGS_VALUE)],
                )
            _seed_conn.commit()
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        api_role=api_role, api_dsn=api_dsn,
        controlplane_role=controlplane_role, controlplane_dsn=controlplane_dsn,
        platform_db=platform_db, schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.control_dsn, platform.provision_script,
        {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{slug}"
    runtime_role = f"{database}_runtime"
    developer_role = f"{database}_developer"
    return types.SimpleNamespace(
        slug=slug, database=database, schema="public",
        runtime_role=runtime_role, developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def deprovision_app(platform: types.SimpleNamespace, slug: str) -> None:
    import time

    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


@pytest.fixture(scope="module")
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "pceila")
    try:
        yield app
    finally:
        deprovision_app(platform, "pceila")


def _main_env(platform: types.SimpleNamespace, app: types.SimpleNamespace) -> dict[str, str]:
    return {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app.slug,
        f"R2DB_APP_{app.slug.upper()}_RUNTIME_DSN": app.runtime_dsn,
        f"R2DB_APP_{app.slug.upper()}_DEVELOPER_DSN": app.developer_dsn,
        # This file's own `platform` fixture seeds `surfaces` WITH a
        # `control` half (needed by nothing in THIS file directly, but
        # kept consistent with a real "both surfaces" deployment) -- F-6
        # requires this data-plane process to agree by declaring itself
        # `enabled`, never the default `unavailable`.
        "R2DB_CONTROL_PLANE_STATUS": "enabled",
    }


def _reload_module_with_env(module_name: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """`r2db_api.main`/`r2db_api.control_main` both have `app = build_*()`
    at MODULE level -- see `test_application_audit.py::_reload_module_
    with_env`'s identical, peer-local-duplicated helper for the full
    rationale."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import importlib

    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def _set_row(platform: types.SimpleNamespace, key: str, value: object) -> None:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES (%s, %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                (key, Jsonb(value)),
            )
        conn.commit()


def _delete_row(platform: types.SimpleNamespace, key: str) -> None:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE key = %s").format(table=sql.Identifier(platform.schema, "platform_declarations")),
                (key,),
            )
        conn.commit()


def _restore_default_ceilings(platform: types.SimpleNamespace) -> None:
    _set_row(platform, "process_ceilings", _DEFAULT_CEILINGS_VALUE)


def _delete_credential(platform: types.SimpleNamespace, credential_id: str) -> None:
    """`0005`'s `credentials.application_slug` is `ON DELETE RESTRICT` --
    every credential this file issues against the shared, module-scoped
    `app_a` must be cleaned up here, or `deprovision_app` in `app_a`'s own
    teardown fails (mirrors `test_credential_persistence.py::provisioned_
    app`'s identical teardown responsibility)."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "credentials")),
                [credential_id],
            )
        conn.commit()


# ===========================================================================
# 1. `validate_process_ceilings_value` -- pure shape checks (completion
#    condition 1's shape half; no PostgreSQL needed).
# ===========================================================================


@pytest.mark.parametrize(
    "bad_value",
    [
        {},
        {"data": 1},
        {"control": 1},
        {"data": 1, "control": 1, "extra": 1},
        {"data": 0, "control": 1},
        {"data": 1, "control": 0},
        {"data": -1, "control": 1},
        {"data": 1, "control": -1},
        {"data": True, "control": 1},
        {"data": 1, "control": True},
        {"data": "1", "control": 1},
        {"data": 1.5, "control": 1},
        [1, 1],
        "not-an-object",
        None,
    ],
    ids=repr,
)
def test_validate_process_ceilings_value_rejects_malformed_shapes(bad_value: object) -> None:
    """Non-空振り: at least one observed rejection per malformed dimension
    -- missing key, extra key, zero, negative, bool-as-int, non-int,
    non-dict. A mutation weakening `validate_process_ceilings_value` to
    accept any of these turns exactly the corresponding case here red."""
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_process_ceilings_value(bad_value, schema="r2dbsvc_registry", ops_module="r2db_api")
    assert exc.value.code == "F-15"


def test_validate_process_ceilings_value_accepts_well_formed_values() -> None:
    result = validate_process_ceilings_value({"data": 1, "control": 2}, schema="r2dbsvc_registry", ops_module="r2db_api")
    assert result == ProcessCeilings(data=1, control=2)


# ===========================================================================
# 2. startup fail-fast (F-15) when the row is missing (completion
#    condition 1).
# ===========================================================================


def test_missing_row_fails_fast_at_startup(platform: types.SimpleNamespace) -> None:
    """Completion condition 1: `read_platform_declarations` -- the SAME
    function both `r2db_api.main.build_app`/`r2db_api.control_main.
    build_control_app` call at startup -- raises `PlatformDeclarationError
    (code="F-15")` naming `ops declare-process-ceilings` when the row is
    absent, mirroring `surfaces`'s own F-3 treatment exactly. A mutation
    that drops `process_ceilings` from the required-row check (design
    D-5(ii)'s own "行が無ければ起動時 fail-fast") leaves this call
    succeeding instead, turning this test red."""
    _delete_row(platform, "process_ceilings")
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_platform_declarations(conn, schema=platform.schema, ops_module="r2db_api", migration="0008")
        assert exc.value.code == "F-15"
        assert "process_ceilings" in str(exc.value)
        assert "declare-process-ceilings" in str(exc.value)
        assert PROCESS_CEILINGS_MIGRATION_NUMBER in str(exc.value)
    finally:
        _restore_default_ceilings(platform)


def test_missing_row_fails_fast_through_build_app(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 1, composition-root end of the wire: `build_
    app` itself refuses to assemble when `process_ceilings` is absent --
    not merely the lower-level `read_platform_declarations` call. The
    module is FIRST reloaded against the healthy default (module-level
    `app = build_app()`, P2-D5, would otherwise raise at import time,
    uncaught by this test's own `pytest.raises` below) -- the row is only
    deleted afterward, and the failing call is a plain `module.build_app
    (env=...)` invocation, never a second reload."""
    module = _reload_module_with_env("r2db_api.main", _main_env(platform, app_a), monkeypatch)
    _delete_row(platform, "process_ceilings")
    try:
        with pytest.raises(RuntimeError):
            module.build_app(env=_main_env(platform, app_a))
    finally:
        _restore_default_ceilings(platform)


# ===========================================================================
# 3. the 3-region `limit_enforcement` mapping (design D-5(ii); completion
#    conditions 2/3/4).
# ===========================================================================

#: Region (i) -- request-scoped, unaffected by the ceiling either way
#: (design D-5(ii)); `execution_ms` is excluded here (it is its own
#: `reference_wall_clock` category, unrelated to the ceiling question).
_DATA_PLANE_REQUEST_SCOPED_CLASSES = (
    "request_bytes", "batch_items", "result_items", "query_complexity",
    "schema_objects", "operation_depth", "enum_members",
)


def test_ceiling_one_maps_in_memory_classes_to_enforced(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 2 (ceiling 1 half), data plane."""
    module = _reload_module_with_env("r2db_api.main", _main_env(platform, app_a), monkeypatch)
    app = module.build_app(env=_main_env(platform, app_a))
    try:
        writer = PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)
        try:
            with writer.unit_of_work() as work:
                writer.add("crd_pceil1_00000000", app_a.slug, "runtime", "secret-pceil1", work=work)
        finally:
            writer.close()
        service = app.app.state.service
        context = service.authenticate(compose_bearer_locator("crd_pceil1_00000000", "secret-pceil1"))
        caps = service.capabilities(context)
        enforcement = caps["limit_enforcement"]
        assert enforcement["requests_per_minute"] == "enforced"
        assert enforcement["concurrency"] == "enforced"
    finally:
        app.app.state.service._durable_audit.close()  # noqa: SLF001
        app.app.state.service._credentials.close()  # noqa: SLF001
        module.default_pool_manager.dispose_all()
        _delete_credential(platform, "crd_pceil1_00000000")


def test_ceiling_two_maps_in_memory_classes_to_deployment_required(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 2 (ceiling 2 half) + completion condition 3
    (region (i)/(iii) unaffected), data plane. A mutation that hardcodes
    the mapping to always `enforced` (design D-5(ii)'s own "壊すとどう見え
    るか": "写像を『常に enforced』に固定する") turns the `deployment_
    required` assertions below red; a mutation that includes region (i)/
    (iii) classes in the ceiling-dependent set turns the unaffected
    assertions red."""
    _set_row(platform, "process_ceilings", {"data": 2, "control": 1})
    try:
        module = _reload_module_with_env("r2db_api.main", _main_env(platform, app_a), monkeypatch)
        app = module.build_app(env=_main_env(platform, app_a))
        try:
            writer = PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)
            try:
                with writer.unit_of_work() as work:
                    writer.add("crd_pceil2_00000000", app_a.slug, "runtime", "secret-pceil2", work=work)
            finally:
                writer.close()
            service = app.app.state.service
            context = service.authenticate(compose_bearer_locator("crd_pceil2_00000000", "secret-pceil2"))
            caps = service.capabilities(context)
            enforcement = caps["limit_enforcement"]

            assert enforcement["requests_per_minute"] == "deployment_required"
            assert enforcement["concurrency"] == "deployment_required"

            for class_name in _DATA_PLANE_REQUEST_SCOPED_CLASSES:
                assert enforcement[class_name] == "enforced", f"region (i) class {class_name!r} must be unaffected by process_ceilings"

            # Region (iii): DB-side-bound, unaffected by the ceiling (its
            # own check-then-write lock is WP-6d-i's scope, not this WP's
            # -- see the module docstring, item 3).
            assert enforcement["idempotency_entries"] == "enforced"
            # Not a `limit_enforcement` category at all (its own `reference_
            # wall_clock` bucket) -- included to prove the ceiling-2
            # mapping did not accidentally sweep it up either.
            assert enforcement["execution_ms"] == "reference_wall_clock"
        finally:
            app.app.state.service._durable_audit.close()  # noqa: SLF001
            app.app.state.service._credentials.close()  # noqa: SLF001
            module.default_pool_manager.dispose_all()
            _delete_credential(platform, "crd_pceil2_00000000")
    finally:
        _restore_default_ceilings(platform)


def test_control_plane_ceiling_mapping(platform: types.SimpleNamespace) -> None:
    """Completion conditions 2/3/4, control plane: `control_requests_per_
    minute`/`audit_requests_per_minute` (region (ii)) follow the
    constructor-injected `process_ceiling`; `applications`/`credentials_
    per_application` (region (iii)) and `request_bytes` (region (i)) do
    not. Exercises the SAME `ControlPlaneService.capabilities()` real
    Postgres-backed instance `control_main.assemble_control_stack` builds
    (`PostgresControlBackend`) -- constructed directly here (bypassing the
    full `build_control_app`/HTTP layer, which needs a bootstrapped,
    rotated control credential just to call `GET .../capabilities`) so
    this test can vary `process_ceiling` without repeatedly re-running the
    startup declaration-read plumbing `test_missing_row_fails_fast_
    through_build_app`/the data-plane mapping tests above already cover."""
    from r2db_api.control_main import assemble_control_stack
    from r2db_api.control_plane import bootstrap_control_credential
    from r2db_api.credential_store import PostgresControlCredentialStore

    for control_ceiling, expected in ((1, "enforced"), (2, "deployment_required")):
        # Bootstrap/reset issuance is exclusively an `r2dbsvc_control`
        # (schema-owner) operation -- migration `0006`'s own GRANTs give
        # `r2dbsvc_controlplane` only SELECT/UPDATE on `control_
        # credentials`, never INSERT (ops.py's own module header: "This
        # module, run by an operator with R2DB_CONTROL_DSN ... is the
        # entire issuance surface"). A throwaway audit sink here (never
        # closed by design -- `ControlAuditSink` is a plain in-memory
        # list) is fine: this bootstrap ceremony's own audit row is not
        # what this test is about.
        from r2db_api.audit import ControlAuditSink

        bootstrap_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
        try:
            with bootstrap_store.unit_of_work() as work:
                # `bootstrap_control_credential` already returns the
                # composed bearer as its own `secret` half (contract
                # 1.6.0's own "issuance point returns the ready-to-present
                # bearer" discipline) -- never re-`compose_bearer_locator`
                # it a second time.
                credential_id, bearer = bootstrap_control_credential(bootstrap_store, ControlAuditSink(), work=work)
        finally:
            bootstrap_store.close()

        service, stores = assemble_control_stack(
            controlplane_dsn=platform.controlplane_dsn, app_pepper=PEPPER, control_pepper=CONTROL_PEPPER,
            schema=platform.schema, process_ceiling=control_ceiling,
        )
        applications, credentials, control_credentials, audit, audit_reader = stores
        try:
            caps = service.capabilities(bearer)
            enforcement = caps["limit_enforcement"]
            assert enforcement["control_requests_per_minute"] == expected
            assert enforcement["audit_requests_per_minute"] == expected
            assert enforcement["applications"] == "enforced"
            assert enforcement["credentials_per_application"] == "enforced"
            # `request_bytes` (region (i)) is "unavailable" at this bare
            # `ControlPlaneService` layer regardless of `process_ceiling`
            # (`control_http.py`'s own handler is what flips it to
            # "enforced" once `RequestByteBoundMiddleware` is actually
            # mounted -- unaffected either way by this test's own
            # ceiling variation, which is the only property under test
            # for this class).
            assert enforcement["request_bytes"] == "unavailable"
        finally:
            applications.close()
            credentials.close()
            control_credentials.close()
            audit.close()
            if audit_reader is not None:
                audit_reader.close()
            with psycopg.connect(platform.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "control_credentials")), [credential_id])
                conn.commit()


def test_control_plane_ceiling_mapping_reads_control_not_data_through_build_control_app(
    platform: types.SimpleNamespace,
) -> None:
    """Review finding F3 (`scratchpad/phase10/wp6a-review.md`, supervisor
    ruling `scratchpad/phase10/wp6-rulings.md` #3): `test_control_plane_
    ceiling_mapping` above constructs `ControlPlaneService` directly via
    `assemble_control_stack(..., process_ceiling=control_ceiling)` --
    `process_ceiling` is INJECTED by the test, so it never exercises
    `control_main.build_control_app`'s own read of `declarations.process_
    ceilings.control` (`control_main.py`, step 6 of that function's own
    docstring). A mutation swapping `.control` for `.data` there is
    invisible to every process_ceilings test in this repository
    (`grep -rl process_ceiling r2db-api/tests/` confirms no OTHER file
    constructs `process_ceiling` through this composition root either) --
    the control plane would then silently declare enforcement for the
    WRONG plane's process count, exactly the false safety declaration
    contract 1.8.0 exists to prevent.

    This test goes through the REAL composition root (`build_control_app`,
    a real ASGI app, a bootstrapped control credential, real HTTP via
    `TestClient`) with an ASYMMETRIC ceiling (`{"data": 1, "control": 2}`)
    so `.data`/`.control` are never accidentally equal -- pinning the
    result on the `.control` side. Mutating `control_main.py`'s own
    `process_ceiling=declarations.process_ceilings.control` to read
    `.data` instead turns this test red (the control plane would then
    read the DATA plane's ceiling, 1, and answer `enforced` instead of the
    expected `deployment_required`)."""
    from starlette.testclient import TestClient

    from r2db_api.control_plane import bootstrap_control_credential

    credential_id: str | None = None
    _set_row(platform, "process_ceilings", {"data": 1, "control": 2})
    try:
        import r2db_api.control_main as control_main_module

        control_env = {
            "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": CONTROL_PEPPER,
            "R2DB_CREDENTIAL_PEPPER": PEPPER,
            "R2DB_PLATFORM_SCHEMA": platform.schema,
        }
        control_app = control_main_module.build_control_app(env=control_env)

        control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
        control_audit = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)
        try:
            with control_store.unit_of_work() as work:
                credential_id, control_bearer = bootstrap_control_credential(control_store, control_audit, work=work)
        finally:
            control_store.close()
            control_audit.close()

        with TestClient(control_app) as client:
            response = client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {control_bearer}"})
        assert response.status_code == 200, response.text
        enforcement = response.json()["limit_enforcement"]
        # `.control` == 2 -> `deployment_required`. If the mutation this
        # test targets swapped `.control` for `.data` (== 1), this would
        # instead read `enforced` -- the two ceilings are asymmetric
        # specifically so this distinction is unmistakable.
        assert enforcement["control_requests_per_minute"] == "deployment_required"
        assert enforcement["audit_requests_per_minute"] == "deployment_required"
        # Region (iii), unaffected by either plane's ceiling -- unchanged
        # by the mutation, included so a `.control`/`.data` swap cannot be
        # masked by also weakening these two.
        assert enforcement["applications"] == "enforced"
        assert enforcement["credentials_per_application"] == "enforced"
    finally:
        if credential_id is not None:
            with psycopg.connect(platform.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "control_credentials")), [credential_id])
                conn.commit()
        _restore_default_ceilings(platform)


# ===========================================================================
# 4. `ops declare-process-ceilings` round trip, rejection of non-positive
#    values, and "the table is the only source" (completion conditions
#    4/6).
# ===========================================================================


@pytest.fixture()
def ops_env(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    try:
        yield platform
    finally:
        _restore_default_ceilings(platform)


def _row_value(platform: types.SimpleNamespace, key: str) -> object:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT value FROM {table} WHERE key = %s").format(table=sql.Identifier(platform.schema, "platform_declarations")), [key])
            row = cur.fetchone()
    return row[0] if row else None


def test_declare_process_ceilings_round_trip(ops_env: types.SimpleNamespace) -> None:
    """Completion condition 6: `ops declare-process-ceilings` writes
    EXACTLY the value it was given to the table (no normalization, no
    extra keys), and a subsequent read observes it."""
    rc = ops.main(["declare-process-ceilings", "--data", "3", "--control", "2"])
    assert rc == 0
    assert _row_value(ops_env, "process_ceilings") == {"data": 3, "control": 2}


@pytest.mark.parametrize("data,control", [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_declare_process_ceilings_rejects_non_positive_values(ops_env: types.SimpleNamespace, data: int, control: int) -> None:
    with pytest.raises(SystemExit) as exc:
        ops.main(["declare-process-ceilings", "--data", str(data), "--control", str(control)])
    assert exc.value.code == 2
    # the pre-existing row (this file's own module default) must be left
    # untouched by a rejected declaration.
    assert _row_value(ops_env, "process_ceilings") == _DEFAULT_CEILINGS_VALUE


def test_declaration_table_is_the_only_source_no_env_fallback(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 6 (design D-2(d)'s own "env は廃止する" applied
    to this new declaration too): setting a plausibly-named environment
    variable to a DIFFERENT value has NO effect at all -- only the table
    row is ever consulted. A mutation adding an env-var fallback (work
    order's own variant for this completion condition) that reads,
    e.g., `R2DB_PROCESS_CEILINGS` when the table disagrees turns this red;
    a static source scan closes the gap a fallback keyed on some OTHER
    name would leave open."""
    import inspect

    from r2db_api import platform_declarations as pd

    for name in ("validate_process_ceilings_value", "read_platform_declarations"):
        source = inspect.getsource(getattr(pd, name))
        assert "os.environ" not in source and "getenv" not in source, f"{name} must never read the process environment"

    _set_row(platform, "process_ceilings", {"data": 5, "control": 5})
    try:
        env = _main_env(platform, app_a)
        env["R2DB_PROCESS_CEILINGS"] = json.dumps({"data": 1, "control": 1})
        module = _reload_module_with_env("r2db_api.main", env, monkeypatch)
        app = module.build_app(env=env)
        try:
            writer = PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)
            try:
                with writer.unit_of_work() as work:
                    writer.add("crd_pceilenv_0000000", app_a.slug, "runtime", "secret-pceilenv", work=work)
            finally:
                writer.close()
            service = app.app.state.service
            context = service.authenticate(compose_bearer_locator("crd_pceilenv_0000000", "secret-pceilenv"))
            enforcement = service.capabilities(context)["limit_enforcement"]
            # data=5 (the TABLE value) means deployment_required, never
            # enforced -- an env fallback reading the bogus env var above
            # (data=1) would report enforced instead.
            assert enforcement["requests_per_minute"] == "deployment_required"
        finally:
            app.app.state.service._durable_audit.close()  # noqa: SLF001
            app.app.state.service._credentials.close()  # noqa: SLF001
            module.default_pool_manager.dispose_all()
            _delete_credential(platform, "crd_pceilenv_0000000")
    finally:
        _restore_default_ceilings(platform)


# ===========================================================================
# 5. `ops verify-declarations` F-15 (completion condition 7). Deliberately
#    does NOT touch `_VERIFY_DECLARATIONS_EXIT_CODES`'s own cross-peer
#    isomorphism pin (`_ISOMORPHIC_TARGETS`) -- registering F-15 there is
#    Class D, pair-closing work the supervisor performs once MitateDB-api's
#    own WP-6b lands the same key (work order §4 WP-6a/6b 完了条件 13's own
#    scope line, §4 (7)).
# ===========================================================================


@pytest.fixture()
def verify_env(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    monkeypatch.delenv("R2DB_CONTROL_PLANE_STATUS", raising=False)
    try:
        yield platform
    finally:
        _restore_default_ceilings(platform)


def test_verify_declarations_f15_when_process_ceilings_row_is_absent(verify_env: types.SimpleNamespace) -> None:
    _delete_row(verify_env, "process_ceilings")
    rc = ops.main(["verify-declarations"])
    assert rc == 14


def test_verify_declarations_f15_when_process_ceilings_value_is_malformed(verify_env: types.SimpleNamespace) -> None:
    _set_row(verify_env, "process_ceilings", {"data": 0, "control": 1})
    rc = ops.main(["verify-declarations"])
    assert rc == 14


def test_verify_declarations_exit_code_table_maps_f15_to_14() -> None:
    assert ops._VERIFY_DECLARATIONS_EXIT_CODES["F-15"] == 14  # noqa: SLF001


def test_verify_declarations_passes_at_the_seeded_default(verify_env: types.SimpleNamespace) -> None:
    """Non-空振り positive control: the module `platform` fixture's own
    default (`process_ceilings = {"data": 1, "control": 1}`) does NOT, on
    its own, make `verify-declarations` fail -- proving the two FAIL tests
    above are really about the mutation under test, not some unrelated
    difference. (Connected as the schema owner, not a declared audit
    writer, so F-13 -- not F-15 -- is the expected stopping point; this
    is `test_ops_verify_declarations.py::test_verify_declarations_f13_...`'s
    own well-established default-connection posture, reused here only to
    prove F-15 itself already passed on the way there.)"""
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = ops.main(["verify-declarations"])
    out = buffer.getvalue()
    assert rc == 11, out  # F-13 -- see docstring
    assert "OK   F-15" in out, out


# ===========================================================================
# 6. lock observation for the 2 region-(iii) classes this WP itself locks
#    (completion condition 4 -- `applications` / `credentials_per_
#    application`, both via `credential_store.py`'s `*_locked` helpers):
#    a second connection's OWN attempt to take the SAME table-scoped
#    constant-key `pg_advisory_xact_lock` blocks (`psycopg.errors.
#    LockNotAvailable`, forced by a short `lock_timeout`) while the first
#    connection still holds it -- then succeeds immediately once the first
#    connection's transaction ends. Removing the `_take_bound_advisory_
#    lock` call from either `count_locked`/`count_active_for_application_
#    locked` (this WP's own mutation target) makes the concurrent probe
#    succeed immediately instead of blocking, turning that test below red.
#
#    Review finding F1 (`scratchpad/phase10/wp6a-review.md`, supervisor
#    ruling `scratchpad/phase10/wp6-rulings.md` #1): a plain `INSERT` on
#    the locked table is NOT an appropriate probe for an advisory lock --
#    unlike `LOCK TABLE ... IN SHARE MODE` (this WP's own pre-review-
#    round-3 form), `pg_advisory_xact_lock` is a purely cooperative lock
#    that never blocks ordinary DML on its own; the only thing a second
#    session blocks on is taking the SAME advisory lock key itself. Both
#    probes below therefore call the SAME `count_locked`/`count_active_
#    for_application_locked` method a second time, on a second connection,
#    rather than issuing a raw `INSERT`.
#
#    `idempotency_entries` (the third region-(iii) class) is NOT covered
#    here -- see the note below, supervisory ruling 2026-09-08.
# ===========================================================================


def test_db_side_bounds_hold_under_concurrent_writers_applications(platform: types.SimpleNamespace) -> None:
    """`applications` (control_plane.py `register_application`'s own
    `PostgresApplicationRegistry.count_locked`)."""
    registry = PostgresApplicationRegistry(platform.controlplane_dsn, schema=platform.schema, pool_size=2)
    try:
        conn_a = psycopg.connect(platform.controlplane_dsn)
        conn_a.autocommit = False
        try:
            with conn_a.cursor() as cur:
                cur.execute("SELECT 1")  # forces conn_a's own outer transaction to actually begin (psycopg3 default autocommit=False starts one lazily, on first statement) -- without this, the advisory lock below is taken and released within its own implicit single-statement transaction, never held across this test's own subsequent assertions
            registry.count_locked(_PostgresWork(conn_a))  # holds the table-scoped pg_advisory_xact_lock until conn_a ends

            conn_b = psycopg.connect(_dsn_with(platform.controlplane_dsn, options="-c lock_timeout=500"))
            try:
                # Calls `_take_bound_advisory_lock` directly (the same
                # statement/key `count_locked` itself takes first),
                # bypassing `count_locked`'s own `except psycopg.Error:
                # fail(...)` wrapper -- that wrapper would otherwise turn
                # this expected `LockNotAvailable` into a `FoundationError`
                # (`SERVICE_UNAVAILABLE`), the exact leak F1 named for a
                # genuine deadlock; this probe wants the RAW psycopg
                # exception, exactly like the pre-review-round-3 form of
                # this test asserted against a raw `INSERT`'s own raw
                # exception, never through the store's error translation.
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    with conn_b.cursor() as cur:
                        _take_bound_advisory_lock(cur, schema=platform.schema, table="applications")  # same key -> blocks, then times out
            finally:
                conn_b.rollback()
                conn_b.close()
        finally:
            conn_a.rollback()
            conn_a.close()

        # The advisory lock is released now (conn_a's transaction ended) --
        # the same probe must succeed immediately.
        conn_c = psycopg.connect(platform.controlplane_dsn)
        try:
            registry.count_locked(_PostgresWork(conn_c))
            conn_c.commit()
        finally:
            conn_c.close()
    finally:
        registry.close()


def test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """`credentials_per_application` (control_plane.py `issue_credential`'s
    own `PostgresCredentialStore.count_active_for_application_locked`).
    `app_a` (module-scoped, provisioned via the real `0003` script) is
    already a real registered `applications` row -- this test never
    inserts or deletes any row, only takes/observes the advisory lock."""
    store = PostgresCredentialStore(platform.controlplane_dsn, pepper=PEPPER, schema=platform.schema, pool_size=2)
    try:
        conn_a = psycopg.connect(platform.controlplane_dsn)
        conn_a.autocommit = False
        try:
            with conn_a.cursor() as cur:
                cur.execute("SELECT 1")  # see the sibling `applications` test above for why this matters
            store.count_active_for_application_locked(app_a.slug, _PostgresWork(conn_a))

            conn_b = psycopg.connect(_dsn_with(platform.controlplane_dsn, options="-c lock_timeout=500"))
            try:
                # See the sibling `applications` test above for why this
                # calls `_take_bound_advisory_lock` directly rather than
                # `count_active_for_application_locked` (whose own
                # `except psycopg.Error: fail(...)` wrapper would turn the
                # expected `LockNotAvailable` into `SERVICE_UNAVAILABLE`).
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    with conn_b.cursor() as cur:
                        _take_bound_advisory_lock(cur, schema=platform.schema, table="credentials")  # same key -> blocks, then times out
            finally:
                conn_b.rollback()
                conn_b.close()
        finally:
            conn_a.rollback()
            conn_a.close()

        conn_c = psycopg.connect(platform.controlplane_dsn)
        try:
            store.count_active_for_application_locked(app_a.slug, _PostgresWork(conn_c))
            conn_c.commit()
        finally:
            conn_c.close()
    finally:
        store.close()


# ===========================================================================
# 6b. barrier-synchronized concurrent WRITERS (review finding F2,
#     supervisor ruling `scratchpad/phase10/wp6-rulings.md` #2): section 6
#     above only pins "a second lock-taker blocks" -- it never runs the
#     check-then-write body itself twice concurrently, so it cannot show
#     the lock actually PREVENTS the bound from being exceeded (F1's own
#     deadlock/503 failure mode ran, undetected, through section 6's own
#     tests). These two tests run the REAL production call twice
#     concurrently -- `ControlPlaneService.register_application`/`issue_
#     credential`, released together by a `threading.Barrier` -- against a
#     bound set to "one more than the current count", so the two calls
#     contend for the SAME single remaining slot. With the lock in place
#     this is safe regardless of scheduling: `pg_advisory_xact_lock` makes
#     the second caller's own count-then-insert strictly wait for the
#     first's transaction to end, so exactly one call succeeds and the
#     other observes the bound already reached (`LIMIT_EXCEEDED`) -- never
#     both succeeding (bound exceeded), never a deadlock, never a leaked
#     `SERVICE_UNAVAILABLE` (503). Mutation: removing `_take_bound_
#     advisory_lock`'s call from the relevant `*_locked` method makes the
#     two concurrent calls race the plain count-then-insert this WP
#     replaced (barrier-released together, over a local Unix-socket
#     connection with sub-millisecond round trips): both threads' own
#     `count_locked`/`count_active_for_application_locked` read the SAME
#     pre-insert count, both pass the bound check, and both insert --
#     `ok_count == 2` (bound exceeded) instead of the expected `1`, turning
#     the assertion below red (or, on an unlucky interleaving, a real
#     deadlock instead, surfacing as `SERVICE_UNAVAILABLE` -- also
#     asserted against below).
# ===========================================================================


def test_applications_bound_holds_under_barrier_synchronized_concurrent_registration(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A deterministic widening of the count-then-insert window, applied on
    # TOP of the barrier release: without it, two threads' own single
    # local-Unix-socket round trip can complete close enough together that
    # even the UNLOCKED (mutated) code path sometimes fails to race by pure
    # luck of OS thread scheduling, making the mutation this test targets
    # an unreliable "sometimes red" instead of a reliable one. The sleep
    # runs AFTER `count_locked` returns -- i.e. AFTER the (real) advisory
    # lock is already held -- so with the lock in place this only holds it
    # 0.3s longer (harmless: the other thread already blocks on `pg_
    # advisory_xact_lock` itself, not on wall-clock timing); with the lock
    # REMOVED (mutation), it holds the pre-insert count-read window open
    # long enough that the barrier-released sibling thread reliably reads
    # the SAME stale count before either inserts.
    import time as _time

    _original_count_locked = PostgresApplicationRegistry.count_locked

    def _slow_count_locked(self: PostgresApplicationRegistry, work: _PostgresWork) -> int:
        result = _original_count_locked(self, work)
        _time.sleep(0.3)
        return result

    monkeypatch.setattr(PostgresApplicationRegistry, "count_locked", _slow_count_locked)

    applications = PostgresApplicationRegistry(platform.controlplane_dsn, schema=platform.schema, pool_size=4)
    credentials = PostgresCredentialStore(platform.controlplane_dsn, pepper=PEPPER, schema=platform.schema, pool_size=4)
    control_credentials = PostgresControlCredentialStore(platform.controlplane_dsn, pepper=CONTROL_PEPPER, schema=platform.schema, pool_size=4)
    audit = PostgresControlAuditSink(platform.controlplane_dsn, schema=platform.schema, pool_size=4)
    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)

    credential_id = "ctl_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(24)
    app_id_1 = "pceilbar1" + secrets.token_hex(4)
    app_id_2 = "pceilbar2" + secrets.token_hex(4)
    try:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, role="control", work=work)
        with seed_store.unit_of_work() as work:
            seed_store.rotate(credential_id, secret, work=work)
        bearer = compose_bearer_locator(credential_id, secret)

        current_count = applications.count()
        limits = ControlPlaneLimits(applications=current_count + 1)
        backend = PostgresControlBackend(applications=applications, credentials=credentials, control_credentials=control_credentials)
        service = ControlPlaneService(backend, audit=audit, limits=limits)

        barrier = threading.Barrier(2, timeout=20)
        outcomes: dict[int, tuple[str, str]] = {}

        def _worker(key: int, app_id: str) -> None:
            barrier.wait()
            try:
                service.register_application(bearer, app_id)
                outcomes[key] = ("ok", "")
            except FoundationError as exc:
                outcomes[key] = ("error", exc.code)
            except Exception as exc:  # pragma: no cover - asserted below, not swallowed
                outcomes[key] = ("exception", repr(exc))

        t1 = threading.Thread(target=_worker, args=(1, app_id_1))
        t2 = threading.Thread(target=_worker, args=(2, app_id_2))
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)
        assert not t1.is_alive() and not t2.is_alive(), f"worker thread never finished -- deadlock: {outcomes}"

        results = [outcomes[1], outcomes[2]]
        assert all(kind in ("ok", "error") for kind, _ in results), f"unexpected exception, not a FoundationError: {results}"
        error_codes = [code for kind, code in results if kind == "error"]
        assert "SERVICE_UNAVAILABLE" not in error_codes, f"lock must never surface a 503 to the caller: {results}"
        ok_count = sum(1 for kind, _ in results if kind == "ok")
        assert ok_count == 1, f"exactly one of two concurrent registrations must succeed when the bound is current+1: {results}"
        assert error_codes == ["LIMIT_EXCEEDED"], f"the other call must observe the bound already reached: {results}"
        assert applications.count() == current_count + 1, "the bound must never be exceeded"
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "control_credentials")), [credential_id])
                cur.execute(sql.SQL("DELETE FROM {table} WHERE application_slug IN (%s, %s)").format(table=sql.Identifier(platform.schema, "applications")), [app_id_1, app_id_2])
            conn.commit()
        applications.close()
        credentials.close()
        control_credentials.close()
        audit.close()
        seed_store.close()


def test_credentials_per_application_bound_holds_under_barrier_synchronized_concurrent_issuance(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # See the sibling `applications` test above for why this deterministic
    # delay is here -- same rationale, applied to the credentials-side
    # locked count instead.
    import time as _time

    _original_count_active_for_application_locked = PostgresCredentialStore.count_active_for_application_locked

    def _slow_count_active_for_application_locked(self: PostgresCredentialStore, application_id: str, work: _PostgresWork) -> int:
        result = _original_count_active_for_application_locked(self, application_id, work)
        _time.sleep(0.3)
        return result

    monkeypatch.setattr(PostgresCredentialStore, "count_active_for_application_locked", _slow_count_active_for_application_locked)

    applications = PostgresApplicationRegistry(platform.controlplane_dsn, schema=platform.schema, pool_size=4)
    credentials = PostgresCredentialStore(platform.controlplane_dsn, pepper=PEPPER, schema=platform.schema, pool_size=4)
    control_credentials = PostgresControlCredentialStore(platform.controlplane_dsn, pepper=CONTROL_PEPPER, schema=platform.schema, pool_size=4)
    audit = PostgresControlAuditSink(platform.controlplane_dsn, schema=platform.schema, pool_size=4)
    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)

    credential_id = "ctl_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(24)
    issued: dict[int, str] = {}
    try:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, role="control", work=work)
        with seed_store.unit_of_work() as work:
            seed_store.rotate(credential_id, secret, work=work)
        bearer = compose_bearer_locator(credential_id, secret)

        current_count = credentials.count_active_for_application(app_a.slug)
        limits = ControlPlaneLimits(credentials_per_application=current_count + 1)
        backend = PostgresControlBackend(applications=applications, credentials=credentials, control_credentials=control_credentials)
        service = ControlPlaneService(backend, audit=audit, limits=limits)

        barrier = threading.Barrier(2, timeout=20)
        outcomes: dict[int, tuple[str, str]] = {}

        def _worker(key: int) -> None:
            barrier.wait()
            try:
                result = service.issue_credential(bearer, app_a.slug, "runtime")
                outcomes[key] = ("ok", "")
                issued[key] = result["credential_id"]
            except FoundationError as exc:
                outcomes[key] = ("error", exc.code)
            except Exception as exc:  # pragma: no cover - asserted below, not swallowed
                outcomes[key] = ("exception", repr(exc))

        t1 = threading.Thread(target=_worker, args=(1,))
        t2 = threading.Thread(target=_worker, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)
        assert not t1.is_alive() and not t2.is_alive(), f"worker thread never finished -- deadlock: {outcomes}"

        results = [outcomes[1], outcomes[2]]
        assert all(kind in ("ok", "error") for kind, _ in results), f"unexpected exception, not a FoundationError: {results}"
        error_codes = [code for kind, code in results if kind == "error"]
        assert "SERVICE_UNAVAILABLE" not in error_codes, f"lock must never surface a 503 to the caller: {results}"
        ok_count = sum(1 for kind, _ in results if kind == "ok")
        assert ok_count == 1, f"exactly one of two concurrent issuances must succeed when the bound is current+1: {results}"
        assert error_codes == ["LIMIT_EXCEEDED"], f"the other call must observe the bound already reached: {results}"
        assert credentials.count_active_for_application(app_a.slug) == current_count + 1, "the bound must never be exceeded"
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "control_credentials")), [credential_id])
                for cred_id in issued.values():
                    cur.execute(sql.SQL("DELETE FROM {table} WHERE credential_id = %s").format(table=sql.Identifier(platform.schema, "credentials")), [cred_id])
            conn.commit()
        applications.close()
        credentials.close()
        control_credentials.close()
        audit.close()
        seed_store.close()


# `idempotency_entries` (postgres.py's own `PostgresCell._idempotency_
# reserve`) is NOT covered by a lock-observation test here: the
# supervisory ruling of 2026-09-08 removed this WP's `LOCK TABLE` line
# from `_idempotency_reserve` -- same-key serialization and the count
# lock for this class are WP-6d-i's scope (both peers, one pass), not
# this WP's. `idempotency_entries` remains declared `enforced` (region
# (iii): a DB-side class that does not resolve within one request) --
# only the lock's location moved out of this WP, not the declared value.
