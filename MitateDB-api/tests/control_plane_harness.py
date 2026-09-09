"""Shared PostgreSQL bootstrap harness for the control-plane test modules
(WP-4, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-4/R-8).

Trimmed relative to `test_postgres.py::_bootstrap_platform` -- this harness
only needs `0001_bootstrap_platform.sql` + `0002_registry_and_functions.sql`
(the platform registry: `applications`/`credentials`/`control_credentials`/
`control_audit`, plus the two process roles). WP-4's control plane never
provisions a per-application database (that is `0003`/`0004`'s job, a
concern of the application-plane facade, not the control plane); every
"application" a control-plane test registers is a bare registry row
(`database_name` stays `NULL`, the two-state registry's own "registered,
unprovisioned" state, R-4).

A distinct prefix stem (`mtdbctl<8 hex>`) keeps this harness's own databases/
roles from colliding with `test_postgres.py`'s `mtdbtest<...>` or the future
HTTP adapter's `mitatedbhttp<...>` on a shared local cluster (R-4's own
prefix-replacement convention, restated here for a third, independent
prefix stem).
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

_SWEEP_LOCK_KEY = 0x4D5444424354524C  # ASCII-derived "MTDBCTRL", arbitrary but stable and distinct from test_postgres.py's own key


def admin_dsn() -> str:
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


def require_admin_connection() -> None:
    dsn = admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "control-plane tests require a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests "
            "must not be skipped (design R-8's own 'skip 禁止' condition).",
            pytrace=False,
        )


def sweep_prefix(dsn: str, prefix: str) -> None:
    admin = psycopg.connect(dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", [_SWEEP_LOCK_KEY])
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
                leftover_databases = [row[0] for row in cur.fetchall()]
                for database in leftover_databases:
                    for attempt in range(5):
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
                leftover_roles = [row[0] for row in cur.fetchall()]
                for role in leftover_roles:
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        finally:
            with admin.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [_SWEEP_LOCK_KEY])
    finally:
        admin.close()


def bootstrap_control_platform(dsn: str, prefix: str, tmp_path_factory: pytest.TempPathFactory):
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    # Phase 4 WP-3(b) (design D-5): the `<prefix>svc_auditreader` role's own
    # throwaway password -- mirrors the 3 above.
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_control_migrations_" + prefix)
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
        # Phase 4 WP-3(b): application_audit table + mitatedbsvc_auditreader
        # role -- run AFTER 0002, exactly the order the file's own header
        # requires. This harness never provisions a per-application database
        # (this module's own docstring), so `0003`/`0004` stay unneeded here.
        "0005_application_audit.sql",
        # Q4 phase (design D-1/D-2, work order §4 WP-2): platform
        # declarations table + the two service writer roles' timeout role
        # settings -- run AFTER 0002 (its own two `ALTER ROLE` targets,
        # `<prefix>svc_api`/`<prefix>svc_controlplane`, must already
        # exist). Every test that calls `build_control_service` (directly
        # or via `_postgres_harness`) now depends on this migration having
        # been applied, or it fails startup with F-7/F-3/F-4 (by design --
        # `platform_declarations` is the single source those checks read).
        "0007_platform_declarations.sql",
        # Phase 10 WP-6b (design D-5 (ii)): widens `platform_declarations.
        # key`'s own CHECK constraint to accept `process_ceilings` -- every
        # test that calls `build_control_service`/`main.build_app` now
        # depends on this migration having been applied AND the row seeded
        # below, or it fails startup with F-15.
        "0011_process_ceilings.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    auditreader_role = f"{prefix}svc_auditreader"
    registry_schema = f"{prefix}_registry"

    # Q4 phase (design D-2(c)): a synthetic, example.invalid `surfaces`
    # declaration -- `build_control_service`/`main.build_app` both now
    # require a `surfaces` row to exist at all (F-3) before anything else
    # can be tested. Public-repository-safe (`example.invalid`, never a
    # real domain, mirrors this repository's own established fixture
    # convention).
    surfaces_json = (
        '{"data":{"base_url":"https://data.mitatedb-control-platform.example.invalid/v1"},'
        '"control":{"base_url":"https://control.mitatedb-control-platform.example.invalid/control/v1"}}'
    )

    try:
        _run_psql(dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
        _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
        admin = psycopg.connect(dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(auditreader_role), sql.Literal(auditreader_password)))
        finally:
            admin.close()
        provision_conn = psycopg.connect(provision_dsn, autocommit=True)
        try:
            with provision_conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', %s)").format(
                        table=sql.Identifier(registry_schema, "platform_declarations")),
                    [surfaces_json],
                )
                # Phase 10 WP-6b (design D-5 (ii)): seeded alongside
                # `surfaces` -- `build_control_service`/`main.build_app`
                # both now require this row too (F-15). `{"data": 1,
                # "control": 1}` matches this harness's own single-process
                # reality -- `limit_enforcement` for `control_requests_
                # per_minute`/`audit_requests_per_minute` stays `enforced`,
                # unchanged from before this WP. A test that needs the
                # `deployment_required` mapping re-declares this row with
                # a ceiling of 2 (`test_process_ceilings_declaration.py`).
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('process_ceilings', %s)").format(
                        table=sql.Identifier(registry_schema, "platform_declarations")),
                    ['{"data": 1, "control": 1}'],
                )
        finally:
            provision_conn.close()
    except Exception:
        sweep_prefix(dsn, prefix)
        raise

    return types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=dsn,
        provision_dsn=provision_dsn,
        registry_schema=registry_schema,
        api_role=api_role,
        controlplane_role=controlplane_role,
        api_dsn=_dsn_with(dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        auditreader_dsn=_dsn_with(dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db),
    )


def set_role_timeouts(admin_dsn: str, role: str, *, statement_ms: int, idle_ms: int) -> None:
    """Q4 phase test helper (design D-1(a)): issues the SAME `ALTER ROLE
    ... SET` shape `ops set-platform-timeouts`/migration `0007` use,
    against ONE role -- lets a test override the shipped 5000ms/5000ms
    default (e.g. to keep a visibility-lag-dependent test's own wall-clock
    wait short) the same way a real deployment would, rather than a
    per-connection override product code no longer supports (design
    D-1(b): the SET-SESSION mechanism this replaces was removed)."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                sql.Identifier(role), sql.Literal(f"{statement_ms}ms")))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = {}").format(
                sql.Identifier(role), sql.Literal(f"{idle_ms}ms")))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def control_platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[object]:
    require_admin_connection()
    dsn = admin_dsn()
    prefix = f"mtdbctl{secrets.token_hex(4)}"
    info = bootstrap_control_platform(dsn, prefix, tmp_path_factory)
    try:
        yield info
    finally:
        sweep_prefix(dsn, prefix)
