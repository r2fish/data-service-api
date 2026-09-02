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

    try:
        _run_psql(dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
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
    except Exception:
        sweep_prefix(dsn, prefix)
        raise

    return types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=dsn,
        provision_dsn=provision_dsn,
        registry_schema=registry_schema,
        api_dsn=_dsn_with(dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        auditreader_dsn=_dsn_with(dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db),
    )


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
