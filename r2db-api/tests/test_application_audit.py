"""Phase 4 WP-2(a): the durable application-plane audit sink -- migration
`0007_application_audit.sql`, the sink pair (`audit.ApplicationAuditSink` /
`credential_store.PostgresApplicationAuditSink`), the `StorageBackend`
pre-commit hook (`backend.py`/`structured.py`/`postgres.py`), the dispatch
rules in `service.py` (fail-closed vs. coalesced-denial vs. synchronously
written ordinary events vs. non-durable), and the two writer-
connection timeouts -- tested against real PostgreSQL (§5.3 C-5: must not
be skipped) and, where real-PostgreSQL realism is not the point of the
test, against the pure in-memory backend (`structured.ApplicationCell` +
`audit.ApplicationAuditSink`), which lets the dispatch/coalescing
logic itself be exercised deterministically (an injected fake clock, no
network) without diluting what each test is actually checking.

Design this file is written against: docs/design/
PHASE4_DURABLE_AUDIT_SINK_V1.md (D-1 through D-10, §6.1, §7, §9.2) and
docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-2(a).

WP-2(a) scope only: `audit_query`, `control_capabilities` declarations,
`contract_version`, and the `audit_requests_per_minute` window are WP-2(b)
territory and are not exercised here.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
import types
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.testclient import TestClient

import r2db_api.ops as ops
from r2db_api.audit import ApplicationAuditSink, AuditEvent
from r2db_api.audit_hook import ApplicationAuditHook
from r2db_api.auth import CredentialStore, compose_bearer_locator
from r2db_api.credential_store import PostgresApplicationAuditSink, PostgresControlAuditSink
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell
from r2db_api.service import ControlAuthority, DataService
from r2db_api.structured import ApplicationCell, Predicate, delete_confirmation_phrase

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
PEPPER = "synthetic-test-pepper-application-audit-0000"

# WP-2 (design D-1/D-3 (2'), 監督裁定 11/27): `R2DB_WORKERS`/`R2DB_SLOT_DIR`
# are now required for `build_app()` to start at all -- one shared, real
# slot directory (mode 0700 by `mkdtemp`'s own default) for this whole
# test module's several `build_app(env=...)` call sites, mirroring a
# single-process (`workers=1`) deployment. Not explicitly torn down --
# this repository's own other `tempfile.mkdtemp` test call sites follow
# the same "leaked to the OS temp dir" convention.
_SLOT_DIR = tempfile.mkdtemp(prefix="r2db-test-slots-application-audit-")

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    # R-56 WP-1: role-level `statement_timeout` on `r2dbsvc_auditreader`
    # -- placed right after 0007 (the migration that creates that role);
    # no dependency on 0008/0012/0013.
    "0014_auditreader_statement_timeout.sql",
    # Phase 10 WP-4g (supervisor ruling 2026-09-09): `r2db_api.main.build_
    # app` now runs F-16 (this process' own role CONNECTION LIMIT)
    # unconditionally at startup, on every real launch this file's own
    # `platform` fixture drives -- this migration must run BEFORE the api
    # role's own pre-WP-4f `CONNECTION LIMIT` (10) would otherwise sit
    # below F-16's own real pool-composition floor and fail every test in
    # this file at fixture setup, not just the ones actually about F-16.
    "0013_role_connection_limits.sql",
    "0008_platform_declarations_and_writer_timeouts.sql",
    # Phase 10 WP-6a (design D-5(ii)): widens `platform_declarations_key_
    # check` to admit `process_ceilings` -- required so this file's own
    # `platform` fixture can seed that row below (F-15 is unconditional,
    # like F-3 for `surfaces`, since WP-6a).
    "0012_process_ceilings.sql",
    # WP-2 (design D-3 (1), 監督裁定15): `r2db_api.main.build_app` now
    # always wires the PostgreSQL-backed `requests_per_minute` rate row.
    "0015_credential_request_rate.sql",
    # Q4 rework (supervisor ruling 2026-09-05, H-1 test (ii)): rewritten
    # (its own literal `r2dbsvc_registry` textually replaced by this
    # module's own throwaway prefix, same as every other migration file
    # here) but never applied at PLATFORM level by this fixture -- `0009`
    # is a PER-APPLICATION upgrade script, run against one application's
    # own database by `ops upgrade-applications` (`R2DB_MIGRATIONS_DIR`
    # pointed at `platform.upgrade_migrations_dir`, below), not part of
    # the platform bootstrap sequence.
    "0009_platform_upgrades_ledger_upgrade.sql",
)

# Q4 phase WP-1 (design D-2(c)): the default `surfaces` row this file's own
# `platform` fixture seeds -- `r2db_api.main.build_app`/`r2db_api.control_
# main`'s startup now requires a `surfaces` row to exist (F-3) even for
# tests whose whole point is the WRITER-TIMEOUT double-check, not surfaces.
_DEFAULT_SURFACES_VALUE = {"data": {"base_url": "https://r2db-application-audit-test.example.invalid/v1"}}


# ===========================================================================
# Real-PostgreSQL fixtures (migration/GRANT/timeout/hook-against-real-DB
# tests). Mirrors `test_postgres.py`/`test_control_plane_store.py`'s own
# established fixture pattern one-for-one (duplicated rather than imported,
# matching this repository's own precedent of not taking cross-test-module
# import dependencies).
# ===========================================================================


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


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
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_application_audit.py requires a reachable local PostgreSQL "
            f"server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These "
            "tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            leftover_databases = [row[0] for row in cur.fetchall()]
            for database in leftover_databases:
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
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """Bootstraps `0001` through `0007` under one throwaway prefix -- the
    full set, not only `0007`, because `0007`'s own compatibility argument
    (its header) is "applies cleanly after 0006 on an already-provisioned
    instance", which can only be exercised by actually applying 0001..0006
    first, for real, every module run.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtest{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_appaudit_migrations")
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
        _run_psql(control_dsn, rewritten["0014_auditreader_statement_timeout.sql"])
        _run_psql(control_dsn, rewritten["0013_role_connection_limits.sql"])
        _run_psql(control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(control_dsn, rewritten["0012_process_ceilings.sql"])
        _run_psql(control_dsn, rewritten["0015_credential_request_rate.sql"])
        with psycopg.connect(control_dsn) as _seed_conn:
            with _seed_conn.cursor() as _seed_cur:
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
                # Phase 10 WP-6a (design D-5(ii)): unconditionally
                # required, like `surfaces` above (F-15) -- single-process
                # ceiling for both planes.
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            _seed_conn.commit()
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)
    auditreader_dsn = _dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db)

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        control_role=control_role,
        api_dsn=api_dsn,
        api_role=api_role,
        controlplane_dsn=controlplane_dsn,
        controlplane_role=controlplane_role,
        auditreader_dsn=auditreader_dsn,
        auditreader_role=auditreader_role,
        platform_db=platform_db,
        schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        application_audit_sql=rewritten["0007_application_audit.sql"],
        # Q4 rework (H-1 test (ii)): the directory `ops upgrade-
        # applications`' own `R2DB_MIGRATIONS_DIR` test escape hatch
        # (`test_ops_upgrade.py`'s own established convention) should
        # point at -- holds a REWRITTEN `0009` (this module's own
        # throwaway schema prefix, matching every other migration file
        # here) alongside the platform-bootstrap files, so a real `ops.
        # main(["upgrade-applications", ...])` call against THIS
        # module's own throwaway registry resolves `<schema>.applications`
        # correctly instead of the real deployment's literal
        # `r2dbsvc_registry`.
        upgrade_migrations_dir=rewritten_dir,
        controlplane_password=controlplane_password,
        auditreader_password=auditreader_password,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.control_dsn,
        platform.provision_script,
        {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{slug}"
    runtime_role = f"{database}_runtime"
    developer_role = f"{database}_developer"
    return types.SimpleNamespace(
        slug=slug,
        database=database,
        schema="public",
        runtime_role=runtime_role,
        developer_role=developer_role,
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


def make_cell(app: types.SimpleNamespace, *, pool_size: int = 2) -> PostgresCell:
    return PostgresCell(
        app.slug, app.schema, runtime_dsn=app.runtime_dsn, developer_dsn=app.developer_dsn,
        runtime_role=app.runtime_role, developer_role=app.developer_role, pool_size=pool_size,
    )


def _delete_credentials_for(platform: types.SimpleNamespace, slug: str) -> None:
    """`0005`'s own `credentials.application_slug` is `ON DELETE RESTRICT`
    (`test_credential_persistence.py::provisioned_app`'s own teardown
    docstring) -- any test that issues a credential against an `app_a`/
    `app_b`-fixture application (the H-1 tests below, via `_issue_runtime_
    credential`) must clear it before `deprovision_app` runs, or `0004`
    genuinely fails with a foreign-key-shaped `RAISE`. Safe to call even
    when no credential was ever issued (deletes zero rows)."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "credentials")),
                [slug],
            )
        conn.commit()


@pytest.fixture
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "aaudit")
    try:
        yield app
    finally:
        _delete_credentials_for(platform, "aaudit")
        deprovision_app(platform, "aaudit")


@pytest.fixture
def app_b(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    """Q4 rework (supervisor ruling 2026-09-05, H-1): a SECOND, independently
    provisioned application, used alongside `app_a` to prove H-1(a) --
    ONE served application's own missing platform upgrade must refuse only
    that application's own cell, never take down the whole data-plane
    process (which would refuse `app_a` too)."""
    app = provision_app(platform, "baudit")
    try:
        yield app
    finally:
        _delete_credentials_for(platform, "baudit")
        deprovision_app(platform, "baudit")


def real_durable_sink(platform: types.SimpleNamespace, **kwargs: Any) -> PostgresApplicationAuditSink:
    return PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool_size=2, **kwargs)


def _application_audit_rows(platform: types.SimpleNamespace) -> list[tuple]:
    """Reads `application_audit` back with full (`r2dbsvc_control`)
    privilege -- this file's own test-observation surface, distinct from
    the `auditreader` role's own restricted read (which the GRANT tests
    below exercise directly)."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT event_class, request_id, application_id, actor_type, actor_id, role, operation, "
                    "target_kind, outcome, reason_code, target_id, count FROM {table} ORDER BY recorded_at, event_id"
                ).format(table=sql.Identifier(platform.schema, "application_audit"))
            )
            return cur.fetchall()


LIMITS = ResourceLimits(requests_per_minute=100_000, concurrency=1000)


def _delete_phrase(cell: PostgresCell, entity: str, where: list[dict]) -> str:
    with pytest.raises(FoundationError) as exc:
        cell.transact(entity, [{"operation": "delete", "where": where, "destructive": True}], LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    return exc.value.details["required_confirmation"]


# ===========================================================================
# Section 1: migration 0007 -- applies cleanly, idempotent, changes no
# existing GRANT (work order completion condition 9).
# ===========================================================================


def _grants(admin_dsn: str, platform_db: str, schema: str, table: str, role: str) -> set[str]:
    with psycopg.connect(admin_dsn, dbname=platform_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE table_schema = %s AND table_name = %s AND grantee = %s",
                [schema, table, role],
            )
            return {row[0] for row in cur.fetchall()}


def test_migration_0007_reapplication_is_idempotent_and_changes_no_existing_grant(platform: types.SimpleNamespace) -> None:
    """Re-running 0007 against an instance that already has it applied is
    a no-op, including for 0001-0006's own existing grants -- a WEAKER
    claim than "applying 0007 for the FIRST time (0006-state instance)
    leaves 0001-0006 alone" (see `test_migration_0007_applied_for_the_
    first_time_changes_no_0001_through_0006_grant`, below, for that one);
    kept because idempotent re-application is itself part of design D-9's
    own compatibility argument.
    """
    before_api_applications = _grants(platform.admin_dsn, platform.platform_db, platform.schema, "applications", platform.api_role)
    before_api_credentials = _grants(platform.admin_dsn, platform.platform_db, platform.schema, "credentials", platform.api_role)
    before_controlplane_applications = _grants(platform.admin_dsn, platform.platform_db, platform.schema, "applications", platform.controlplane_role)
    before_controlplane_control_audit = _grants(platform.admin_dsn, platform.platform_db, platform.schema, "control_audit", platform.controlplane_role)

    _run_psql(platform.control_dsn, platform.application_audit_sql, {"auditreader_password": platform.auditreader_password})

    assert _grants(platform.admin_dsn, platform.platform_db, platform.schema, "applications", platform.api_role) == before_api_applications
    assert _grants(platform.admin_dsn, platform.platform_db, platform.schema, "credentials", platform.api_role) == before_api_credentials
    assert _grants(platform.admin_dsn, platform.platform_db, platform.schema, "applications", platform.controlplane_role) == before_controlplane_applications
    assert _grants(platform.admin_dsn, platform.platform_db, platform.schema, "control_audit", platform.controlplane_role) == before_controlplane_control_audit
    assert _grants(platform.admin_dsn, platform.platform_db, platform.schema, "application_audit", platform.api_role) == {"INSERT"}


def test_migration_0007_applied_for_the_first_time_changes_no_0001_through_0006_grant(tmp_path_factory: pytest.TempPathFactory) -> None:
    """WP-2(a) fix round 2 review N-3: the module-scoped `platform` fixture
    every other test in this file shares has ALREADY applied 0007 by the
    time any test runs (needed so those tests can exercise `application_
    audit` at all) -- so a 'before' snapshot taken from it can only prove
    0007's own RE-application is idempotent (the test immediately above),
    never that applying 0007 for the FIRST time (a genuinely 0006-state
    instance, matching every already-deployed instance this migration's
    own header argues compatibility against) leaves 0001-0006's existing
    grants alone. This test provisions its own, fully independent,
    throwaway instance -- applying ONLY 0001/0002/0005/0006 -- takes the
    'before' snapshot from THAT instance, then applies 0007 once and
    compares.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtestn3{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_n3_migrations")
    rewritten: dict[str, Path] = {}
    for name in ("0001_bootstrap_control_plane.sql", "0002_provisioning_functions.sql", "0005_credential_store.sql", "0006_control_plane_http.sql", "0007_application_audit.sql"):
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

        # Genuine 0006-state snapshot -- 0007 has never touched this instance.
        before_api_applications = _grants(admin_dsn, platform_db, schema, "applications", api_role)
        before_api_credentials = _grants(admin_dsn, platform_db, schema, "credentials", api_role)
        before_controlplane_applications = _grants(admin_dsn, platform_db, schema, "applications", controlplane_role)
        before_controlplane_credentials = _grants(admin_dsn, platform_db, schema, "credentials", controlplane_role)
        before_controlplane_control_credentials = _grants(admin_dsn, platform_db, schema, "control_credentials", controlplane_role)
        before_controlplane_control_audit = _grants(admin_dsn, platform_db, schema, "control_audit", controlplane_role)

        _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})

        assert _grants(admin_dsn, platform_db, schema, "applications", api_role) == before_api_applications
        assert _grants(admin_dsn, platform_db, schema, "credentials", api_role) == before_api_credentials
        assert _grants(admin_dsn, platform_db, schema, "applications", controlplane_role) == before_controlplane_applications
        assert _grants(admin_dsn, platform_db, schema, "credentials", controlplane_role) == before_controlplane_credentials
        assert _grants(admin_dsn, platform_db, schema, "control_credentials", controlplane_role) == before_controlplane_control_credentials
        assert _grants(admin_dsn, platform_db, schema, "control_audit", controlplane_role) == before_controlplane_control_audit
        # 0007's own new grant is present and is exactly INSERT-only.
        assert _grants(admin_dsn, platform_db, schema, "application_audit", api_role) == {"INSERT"}
    finally:
        _sweep_prefix(admin_dsn, prefix)


def test_build_app_refuses_to_start_when_migration_0008_has_not_been_applied(tmp_path_factory: pytest.TempPathFactory) -> None:
    """SS4(g)/completion condition 9's non-vacuity requirement (work
    order): a REAL platform database that has never had migration `0008`
    applied at all (0001/0002/0005/0006/0007 only -- the exact pre-Q4
    shape every already-deployed instance has) must refuse to start
    (F-8: `platform_declarations` itself does not exist) rather than
    surface a raw psycopg exception or, worse, silently start unbounded.
    Provisions its own fully independent, throwaway instance -- mirrors
    `test_migration_0007_applied_for_the_first_time_changes_no_0001_
    through_0006_grant`'s own bootstrap pattern immediately above."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtestf8{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_f8_migrations")
    rewritten: dict[str, Path] = {}
    for name in ("0001_bootstrap_control_plane.sql", "0002_provisioning_functions.sql", "0005_credential_store.sql", "0006_control_plane_http.sql", "0007_application_audit.sql"):
        text_ = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text_)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
        _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
        _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
        _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
        # Deliberately NEVER applies 0008.

        # `R2DB_SERVE_APPS`'s own registry validation (`_load_registry_
        # rows`) runs BEFORE the platform_declarations read inside `build_
        # app` (design SS3.7 step 3 precedes step 4) -- provisioning a real
        # SERVABLE application here (0003/0004) purely to reach step 4
        # would be a large, unrelated detour for this one condition, so
        # this exercises `read_platform_declarations` directly instead:
        # the SAME function `build_app`'s own step 4 calls (proven called
        # from that real startup path by every other real-PG test in this
        # file/`test_ops_declarations.py`), against a genuinely NEVER-
        # migrated-0008 instance (complementary to `test_ops_declarations.
        # py::test_f8_message_is_pinned_verbatim_and_not_a_raw_psycopg_
        # exception`'s "created, then dropped" variant).
        api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
        from r2db_api.platform_declarations import MIGRATION_NUMBER, PEER_MODULE, PlatformDeclarationError, read_platform_declarations

        with psycopg.connect(api_dsn) as conn:
            with pytest.raises(PlatformDeclarationError, match="migration 0008"):
                read_platform_declarations(conn, schema=schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        _sweep_prefix(admin_dsn, prefix)


# ===========================================================================
# Section 2: GRANT-realized tests (work order completion conditions 3,
# design §9.2 property 2) -- raw connections, no facade in between.
# ===========================================================================


def test_api_role_cannot_select_update_or_delete_application_audit(platform: types.SimpleNamespace) -> None:
    table = sql.Identifier(platform.schema, "application_audit").as_string(psycopg.connect(platform.admin_dsn, dbname=platform.platform_db))
    with psycopg.connect(platform.api_dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table}")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {table} SET outcome = 'x'")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {table}")
        conn.rollback()
    # Positive control: INSERT (the one grant this role does hold) succeeds.
    with psycopg.connect(platform.api_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, operation, outcome) "
                "VALUES (gen_random_uuid(), 'x', now(), 'r-grant-positive', 'application_credential', 'op', 'allow')"
            )
        conn.commit()


def test_api_role_cannot_insert_a_value_longer_than_the_length_check(platform: types.SimpleNamespace) -> None:
    table = sql.Identifier(platform.schema, "application_audit").as_string(psycopg.connect(platform.admin_dsn, dbname=platform.platform_db))
    with psycopg.connect(platform.api_dsn) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, operation, outcome) "
                    "VALUES (gen_random_uuid(), %s, now(), 'r-len', 'application_credential', 'op', 'allow')",
                    ["x" * 65],
                )
        conn.rollback()


def test_controlplane_role_has_no_privilege_on_application_audit(platform: types.SimpleNamespace) -> None:
    table = sql.Identifier(platform.schema, "application_audit").as_string(psycopg.connect(platform.admin_dsn, dbname=platform.platform_db))
    with psycopg.connect(platform.controlplane_dsn) as conn:
        for stmt in (
            f"SELECT * FROM {table}",
            f"INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, operation, outcome) VALUES (gen_random_uuid(), 'x', now(), 'r', 'application_credential', 'op', 'allow')",
            f"UPDATE {table} SET outcome = 'x'",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.cursor() as cur:
                    cur.execute(stmt)
            conn.rollback()


def test_auditreader_role_can_select_both_audit_tables_and_nothing_else(platform: types.SimpleNamespace) -> None:
    admin = psycopg.connect(platform.admin_dsn, dbname=platform.platform_db)
    application_audit = sql.Identifier(platform.schema, "application_audit").as_string(admin)
    control_audit = sql.Identifier(platform.schema, "control_audit").as_string(admin)
    applications = sql.Identifier(platform.schema, "applications").as_string(admin)
    with psycopg.connect(platform.auditreader_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {application_audit}")
            cur.execute(f"SELECT * FROM {control_audit}")
        # Positive control passed (both SELECTs succeeded above). Now the
        # negative controls: nothing beyond SELECT on those two tables.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {applications}")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {application_audit} (event_id, event_class, occurred_at, request_id, actor_type, operation, outcome) "
                    "VALUES (gen_random_uuid(), 'x', now(), 'r', 'application_credential', 'op', 'allow')"
                )
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {control_audit} SET outcome = 'x'")
        conn.rollback()


# ===========================================================================
# Section 3: writer-connection timeouts (design D-6/N-3; work order
# completion condition 8).
# ===========================================================================


def _show(conn: "psycopg.Connection[Any]", setting: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return cur.fetchone()[0]


def test_audit_write_connections_effective_timeouts_come_from_the_role_setting(platform: types.SimpleNamespace) -> None:
    """Q4 phase WP-1 (design D-1(b)): `PostgresApplicationAuditSink`/
    `PostgresControlAuditSink` no longer accept OR issue a per-connection
    SESSION `SET` for either timeout at all (design D-1(b): "書き手プロセス
    は接続時のセッションSETをやめ") -- migration `0008` (applied by this
    file's own `platform` fixture) is now the ONLY mechanism governing the
    effective value, via `ALTER ROLE ... SET`. This observes that
    property directly, end to end: (a) with 0008's own shipped default
    (5000ms/5000ms) untouched, both writer connections' EFFECTIVE
    `pg_settings` value (`effective_timeouts_ms()`, design D-1(b)(ii)) is
    5000/5000; (b) after `ALTER ROLE ... SET`-ing a DIFFERENT value on each
    role directly (mirroring what `ops set-platform-timeouts` does), a
    FRESH sink's fresh connection reflects the NEW value -- proving this
    is genuinely role-setting-derived, never a value cached anywhere in
    this test's own process or set by either sink class itself."""
    app_sink = real_durable_sink(platform)
    try:
        assert app_sink.effective_timeouts_ms() == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}
    finally:
        app_sink.close()

    control_sink = PostgresControlAuditSink(platform.controlplane_dsn, schema=platform.schema, pool_size=2)
    try:
        assert control_sink.effective_timeouts_ms() == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}
    finally:
        control_sink.close()

    api_role = sql.Identifier(platform.api_role)
    controlplane_role = sql.Identifier(platform.controlplane_role)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '1234ms'").format(api_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '4321ms'").format(api_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '2345ms'").format(controlplane_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5432ms'").format(controlplane_role))
        conn.commit()
    try:
        app_sink2 = real_durable_sink(platform)
        try:
            assert app_sink2.effective_timeouts_ms() == {"statement_timeout": 1234, "idle_in_transaction_session_timeout": 4321}
        finally:
            app_sink2.close()

        control_sink2 = PostgresControlAuditSink(platform.controlplane_dsn, schema=platform.schema, pool_size=2)
        try:
            assert control_sink2.effective_timeouts_ms() == {"statement_timeout": 2345, "idle_in_transaction_session_timeout": 5432}
        finally:
            control_sink2.close()
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(api_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(api_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(controlplane_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(controlplane_role))
            conn.commit()


def test_audit_sink_never_issues_a_session_set_regardless_of_the_role_setting(platform: types.SimpleNamespace) -> None:
    """Q4 phase WP-1 (design D-1(b)) regression guard: `_RolePool` no
    longer HAS a timeout parameter at all (removed, not merely opt-in) --
    a connection this class opens carries whatever the LOGIN ROLE's own
    `pg_db_role_setting` declares (5000ms/5000ms, migration 0008's default,
    applied by this file's own `platform` fixture), never a value this
    class itself sets. Distinguishable from a coincidence: a bare `SHOW`
    on an UNRELATED role (this test's own admin connection, which is
    neither `r2dbsvc_api` nor `r2dbsvc_controlplane` and so carries NO
    role-setting override) shows the untouched cluster default, which this
    assertion confirms differs from 5000ms/5000ms in this test environment
    -- so `real_durable_sink`'s own 5000ms/5000ms reading is verifiably the
    ROLE setting, not merely "whatever the cluster default happens to be
    too"."""
    with psycopg.connect(platform.admin_dsn) as admin:
        with admin.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            cluster_default = cur.fetchone()[0]
    assert cluster_default != "5000ms" and cluster_default != "5s", (
        "test environment's own cluster-wide default statement_timeout coincidentally equals the role setting "
        "this test means to distinguish it from -- adjust postgresql.conf or this assertion"
    )

    sink = real_durable_sink(platform)
    try:
        effective = sink.effective_timeouts_ms()
        assert effective == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}
    finally:
        sink.close()


def _reload_module_with_env(module_name: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """`r2db_api.main`/`r2db_api.control_main` both have `app = build_*()`
    at MODULE level (P2-D5 / design §8 m-10 -- the literal entry point), so
    a bare `import` unconditionally reads real `os.environ` the instant it
    first runs, in ANY test, regardless of which test triggers it first.
    Mirrors `test_credential_persistence.py::main_module`'s own established
    pattern exactly (duplicated per this repository's precedent of not
    taking cross-test-module import dependencies): set a valid environment
    via `monkeypatch`, then import-or-reload so the module-level call runs
    (or re-runs) against THIS test's own `env`, not whatever import order
    happened to run first.
    """
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import importlib
    import sys

    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_build_app_double_check_reflects_the_real_role_setting_not_a_cached_default(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q4 phase WP-1 (design D-1(b)(i)/(ii), M-1's own successor concern):
    `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`/`R2DB_AUDIT_IDLE_TIMEOUT_MS` are
    REMOVED -- defining either now fails startup outright (F-1,
    `test_build_app_rejects_removed_audit_timeout_env_vars` below), so
    there is no env-based "wiring" left to test the way M-1 originally
    meant. What replaced it (and what a mutation dropping the double-check
    call entirely -- work order variant 8 -- would leave undetected by a
    test that only ever exercises `PostgresApplicationAuditSink` directly)
    is that `build_app`'s OWN startup double-check reads the REAL, CURRENT
    `pg_db_role_setting` value every time it runs, not a cached constant:
    this builds the real app TWICE -- once against migration 0008's own
    shipped default (5000/5000), once after changing the role setting
    directly (mirroring `ops set-platform-timeouts`) -- and observes the
    WIRED sink's own effective value track the change both times.
    """
    def _env() -> dict[str, str]:
        return {
            "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-main",
            "R2DB_PLATFORM_DSN": platform.api_dsn,
            "R2DB_PLATFORM_SCHEMA": platform.schema,
            "R2DB_SERVE_APPS": app_a.slug,
            "R2DB_WORKERS": "1",
            "R2DB_SLOT_DIR": _SLOT_DIR,
            f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
            f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
        }

    module = _reload_module_with_env("r2db_api.main", _env(), monkeypatch)
    default_app = module.build_app(env=_env())
    try:
        sink = default_app.app.state.service._durable_audit
        assert sink.effective_timeouts_ms() == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}
    finally:
        default_app.app.state.service._durable_audit.close()
        default_app.app.state.service._credentials.close()

    api_role = sql.Identifier(platform.api_role)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '1234ms'").format(api_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '4321ms'").format(api_role))
        conn.commit()
    try:
        overridden_app = module.build_app(env=_env())
        try:
            sink = overridden_app.app.state.service._durable_audit
            assert sink.effective_timeouts_ms() == {"statement_timeout": 1234, "idle_in_transaction_session_timeout": 4321}
        finally:
            overridden_app.app.state.service._durable_audit.close()
            overridden_app.app.state.service._credentials.close()
            module.default_pool_manager.dispose_all()
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(api_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(api_role))
            conn.commit()


def test_build_app_f9_fires_when_a_connection_string_options_override_changes_the_effective_value(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SS4(e)/completion condition 8(iv), non-vacuity requirement (work
    order): F-9 fires when the EFFECTIVE value diverges from the
    DECLARED (`pg_db_role_setting`) value via a real PostgreSQL GUC-
    priority override -- a connection-string `options=-c
    statement_timeout=...` outranks `ALTER ROLE ... SET` (design D-1(b),
    the GUC source-priority chain) -- exercised against a REAL PostgreSQL
    connection, never a synthetic stub. `R2DB_PLATFORM_DSN` carries the
    override, so `PostgresApplicationAuditSink`'s own pool (built from
    that SAME DSN) opens its connections with it too."""
    good_env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f9-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    # Reload FIRST, against the GOOD env (module-level `app = build_app()`
    # would itself raise -- uncaught by this test own pytest.raises
    # below -- if the override were already active before this point).
    module = _reload_module_with_env("r2db_api.main", good_env, monkeypatch)
    overridden_env = dict(good_env)
    overridden_env["R2DB_PLATFORM_DSN"] = _dsn_with(platform.api_dsn, options="-c statement_timeout=30000")
    with pytest.raises(RuntimeError, match="effective value is 30000 ms"):
        module.build_app(env=overridden_env)


def test_build_app_checks_the_env_mapping_argument_not_os_environ(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 4 (design D-1(d)): the removed-env-var check
    (F-1/F-2) inspects the `env` MAPPING `build_app` was actually called
    with, never the real process `os.environ` -- a deployer's shell (or
    this pytest process' own ambient environment) can carry a leftover
    R2DB_AUDIT_STATEMENT_TIMEOUT_MS without affecting a `build_app(env=...)`
    call whose own explicit `env` dict does not name it. This sets the
    REAL `os.environ` (via monkeypatch.setenv, not the `env=` argument)
    and confirms `build_app` still starts successfully."""
    env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-cond4-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    # Reload FIRST, against a clean environment (module-level `app =
    # build_app()` reads real `os.environ` at reload time -- polluting it
    # before this point would make the RELOAD itself raise, which is not
    # what this test is checking). Only AFTER the module is loaded do we
    # pollute the real `os.environ` -- proving the explicit `env=` argument
    # to `.build_app()` below, not `os.environ`, is what this composition
    # root actually reads.
    module = _reload_module_with_env("r2db_api.main", dict(env), monkeypatch)
    monkeypatch.setenv("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", "9999")
    monkeypatch.setenv("R2DB_DATA_BASE_URL", "https://this-must-never-be-read.example.invalid/v1")
    asgi_app = module.build_app(env=env)
    try:
        assert asgi_app is not None
    finally:
        asgi_app.app.state.service._durable_audit.close()
        asgi_app.app.state.service._credentials.close()
        module.default_pool_manager.dispose_all()


@pytest.mark.parametrize("bad_value", ["60000", -1, 60000.5])
def test_build_app_rejects_a_hand_edited_coalescing_window_value(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, bad_value,
) -> None:
    """Completion condition 6 (design D-2(d), F-4b): the SAME validation
    function runs on the write path (`ops declare-coalescing-window`,
    `test_ops_declarations.py`) and this READ path -- a value hand-edited
    directly into `platform_declarations` (never through `ops`, simulating
    an operator editing the row by hand, or a bug in some other writer)
    must ALSO be rejected at startup, for a string, a negative integer, and
    a fractional (decimal) value."""
    env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f4b-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    # Reload FIRST, while the row is still the good default (module-level
    # `app = build_app()` would itself raise -- uncaught by this test's own
    # `pytest.raises` below -- if the bad value were already written before
    # this point).
    module = _reload_module_with_env("r2db_api.main", env, monkeypatch)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('audit_coalescing_window_ms', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps(bad_value)],
            )
        conn.commit()
    try:
        with pytest.raises(RuntimeError, match="audit_coalescing_window_ms"):
            module.build_app(env=env)
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('audit_coalescing_window_ms', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps(60000)],
                )
            conn.commit()


def test_build_app_rejects_removed_audit_timeout_env_vars(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-1 (design §3.8): `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`/`R2DB_AUDIT_
    IDLE_TIMEOUT_MS`, whatever their value (including empty string), fail
    startup outright -- the M-1 test above's original premise (these vars
    configure the writer connection) no longer holds even a LITTLE; they
    are actively rejected."""
    base_env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f1-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    module = _reload_module_with_env("r2db_api.main", base_env, monkeypatch)
    for name, value in (
        ("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", "1234"),
        ("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", ""),
        ("R2DB_AUDIT_IDLE_TIMEOUT_MS", "4321"),
        ("R2DB_AUDIT_IDLE_TIMEOUT_MS", ""),
    ):
        env = dict(base_env)
        env[name] = value
        with pytest.raises(RuntimeError, match=name):
            module.build_app(env=env)


def test_build_app_rejects_removed_surface_env_vars(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SS4(a): F-2 -- `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_URL`,
    whatever their value (including empty string), fail `r2db_api.main.
    build_app`'s REAL startup path outright. Completes the {2 timeout
    vars, 2 surface vars} x {empty, real value} = 8-case matrix SS4(a)
    requires -- `test_build_app_rejects_removed_audit_timeout_env_vars`
    above is this test's timeout-pair sibling."""
    base_env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f2-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    module = _reload_module_with_env("r2db_api.main", base_env, monkeypatch)
    for name, value in (
        ("R2DB_DATA_BASE_URL", "https://this-must-never-be-read.example.invalid/v1"),
        ("R2DB_DATA_BASE_URL", ""),
        ("R2DB_CONTROL_BASE_URL", "https://this-must-never-be-read.example.invalid/control/v1"),
        ("R2DB_CONTROL_BASE_URL", ""),
    ):
        env = dict(base_env)
        env[name] = value
        with pytest.raises(RuntimeError, match=name):
            module.build_app(env=env)


def test_build_control_app_double_check_reflects_the_real_role_setting_not_a_cached_default(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q4 phase WP-1 (design D-1(b)(i)/(ii)) -- the `control_main.py` half
    of `test_build_app_double_check_reflects_the_real_role_setting_not_a_
    cached_default` above; see that test's own docstring for the full
    rationale. `build_control_app()` itself stays zero-network (module
    docstring) -- the double-check runs inside `_lifespan`'s own startup,
    so this drives it via `TestClient` as a context manager (the same
    mechanism `test_surfaces_env.py` uses for control-plane surfaces
    checks)."""
    def _env() -> dict[str, str]:
        return {
            "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-control-ctl",
            "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-control-app",
            "R2DB_PLATFORM_SCHEMA": platform.schema,
            "R2DB_CONTROL_WORKERS": "1",
        }

    module = _reload_module_with_env("r2db_api.control_main", _env(), monkeypatch)

    # control-plane unconditionally requires surfaces.control (design §3.7
    # control-plane 1-5) -- this file's own `platform` fixture seeds a
    # control-less default row (data-plane tests never need one); restore
    # it afterward since `platform` is module-scoped and shared.
    _control_surfaces_value = {
        "data": {"base_url": "https://r2db-application-audit-test.example.invalid/v1"},
        "control": {"base_url": "https://r2db-application-audit-control-test.example.invalid/control/v1"},
    }
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps(_control_surfaces_value)],
            )
        conn.commit()
    try:
        default_app = module.build_control_app(env=_env())
        with TestClient(default_app):
            sink = default_app.app.state.control_service._audit
            assert sink.effective_timeouts_ms() == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}

        controlplane_role = sql.Identifier(platform.controlplane_role)
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '2345ms'").format(controlplane_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5432ms'").format(controlplane_role))
            conn.commit()
        try:
            overridden_app = module.build_control_app(env=_env())
            with TestClient(overridden_app):
                sink = overridden_app.app.state.control_service._audit
                assert sink.effective_timeouts_ms() == {"statement_timeout": 2345, "idle_in_transaction_session_timeout": 5432}
        finally:
            with psycopg.connect(platform.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(controlplane_role))
                    cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(controlplane_role))
                conn.commit()
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
            conn.commit()


def test_build_control_app_rejects_removed_audit_timeout_env_vars(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-1 -- the `control_main.py` half of `test_build_app_rejects_
    removed_audit_timeout_env_vars` above."""
    base_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-f1-control-ctl",
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f1-control-app",
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    module = _reload_module_with_env("r2db_api.control_main", base_env, monkeypatch)
    for name, value in (
        ("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", "1234"),
        ("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", ""),
        ("R2DB_AUDIT_IDLE_TIMEOUT_MS", "4321"),
        ("R2DB_AUDIT_IDLE_TIMEOUT_MS", ""),
    ):
        env = dict(base_env)
        env[name] = value
        with pytest.raises(RuntimeError, match=name):
            module.build_control_app(env=env)


def test_build_control_app_rejects_removed_surface_env_vars(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SS4(a): F-2 -- the `control_main.py` half of `test_build_app_
    rejects_removed_surface_env_vars` above. Rework round: `build_control_
    app` validates F-1/F-2 before any network access, so a placeholder
    `R2DB_CONTROLPLANE_DSN` still surfaces this error, never a connection
    failure."""
    base_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-f2-control-ctl",
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f2-control-app",
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    module = _reload_module_with_env("r2db_api.control_main", base_env, monkeypatch)
    for name, value in (
        ("R2DB_DATA_BASE_URL", "https://this-must-never-be-read.example.invalid/v1"),
        ("R2DB_DATA_BASE_URL", ""),
        ("R2DB_CONTROL_BASE_URL", "https://this-must-never-be-read.example.invalid/control/v1"),
        ("R2DB_CONTROL_BASE_URL", ""),
    ):
        env = dict(base_env)
        env[name] = value
        with pytest.raises(RuntimeError, match=name):
            module.build_control_app(env=env)


def test_both_composition_roots_derive_the_same_visibility_lag_ms_from_one_db_side_source(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q4 phase WP-1 (design D-1(c), condition 10): WP-2(a)'s original N-6
    concern -- both composition roots must never independently drift on
    what `visibility_lag_ms` means -- no longer has two Python constants
    to compare (`r2db_api.main`/`r2db_api.control_main` do not import
    `DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`_IDLE_TIMEOUT_MS` at all anymore;
    there is nothing left to drift, since BOTH processes now derive from
    the SAME `pg_db_role_setting` catalog, migration 0008). What replaces
    N-6's guarantee is observed here directly: `r2db_api.main`'s own
    writer double-check succeeds against 0008's shipped default (5000/5000
    for both roles, unchanged since `platform`'s own migration application)
    -- proving `r2dbsvc_api`'s catalog entry is exactly 5000/5000 -- and
    `r2db_api.control_main`'s REAL `capabilities()` response (driven
    through `TestClient`, exercising `_lifespan`'s own derivation) reports
    `visibility_lag_ms == 5000 + 5000 + 1000 == 11000` -- design condition
    10's own shipped-default value, unchanged from the pre-Q4 constant.
    """
    from r2db_api.control_plane import bootstrap_control_credential
    from r2db_api.credential_store import PostgresControlCredentialStore

    main_env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-n6-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    main_module = _reload_module_with_env("r2db_api.main", main_env, monkeypatch)
    main_app = main_module.build_app(env=main_env)
    try:
        assert main_app.app.state.service._durable_audit.effective_timeouts_ms() == {
            "statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000,
        }
    finally:
        main_app.app.state.service._durable_audit.close()
        main_app.app.state.service._credentials.close()
        main_module.default_pool_manager.dispose_all()

    control_pepper = "synthetic-test-pepper-n6-control-ctl"
    control_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": control_pepper,
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-n6-control-app",
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
        "R2DB_AUDIT_DSN": platform.auditreader_dsn,
    }
    control_main_module = _reload_module_with_env("r2db_api.control_main", control_env, monkeypatch)

    # control-plane unconditionally requires surfaces.control (design §3.7
    # control-plane 1-5) -- this file's own `platform` fixture seeds a
    # control-less default row (data-plane tests never need one); restore
    # it afterward since `platform` is module-scoped and shared.
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({
                    "data": {"base_url": "https://r2db-application-audit-test.example.invalid/v1"},
                    "control": {"base_url": "https://r2db-application-audit-control-test.example.invalid/control/v1"},
                })],
            )
        conn.commit()
    try:
        control_app = control_main_module.build_control_app(env=control_env)

        control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=control_pepper, schema=platform.schema)
        control_audit = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)
        try:
            with control_store.unit_of_work() as work:
                _credential_id, control_bearer = bootstrap_control_credential(control_store, control_audit, work=work)
        finally:
            control_store.close()
            control_audit.close()

        with TestClient(control_app) as client:
            response = client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {control_bearer}"})
            assert response.status_code == 200, response.text
            assert response.json()["capabilities"]["audit_query"]["visibility_lag_ms"] == 5_000 + 5_000 + 1_000
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
            conn.commit()


def test_control_visibility_lag_ms_reflects_the_sibling_roles_catalog_not_only_its_own(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 21: `derive_visibility_lag_ms` must be fed
    EVERY role in the declared `audit_writer_roles` set, not only the
    control-plane process' own role -- proven by setting ASYMMETRIC
    timeouts (api role bigger than the control-plane's own) and observing
    the REAL `control_main.build_control_app` -> `/control/v1/
    capabilities` path report the max across BOTH, not just its own. A
    mutation that dropped the sibling-role loop (work order 変異 18) would
    report a SMALLER value here (its own role's 1000+1000+1000=3000
    instead of the api role's 9000+9000+1000=19000)."""
    from r2db_api.control_plane import reset_control_credentials
    from r2db_api.credential_store import PostgresControlCredentialStore

    api_role = sql.Identifier(platform.api_role)
    controlplane_role = sql.Identifier(platform.controlplane_role)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9000ms'").format(api_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '9000ms'").format(api_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '1000ms'").format(controlplane_role))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '1000ms'").format(controlplane_role))
        conn.commit()

    control_pepper = "synthetic-test-pepper-sibling-ctl"
    control_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": control_pepper,
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-sibling-app",
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
        "R2DB_AUDIT_DSN": platform.auditreader_dsn,
    }
    control_main_module = _reload_module_with_env("r2db_api.control_main", control_env, monkeypatch)

    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({
                    "data": {"base_url": "https://r2db-sibling-lag-test.example.invalid/v1"},
                    "control": {"base_url": "https://r2db-sibling-lag-test-control.example.invalid/control/v1"},
                })],
            )
        conn.commit()
    try:
        control_app = control_main_module.build_control_app(env=control_env)

        control_store = PostgresControlCredentialStore(platform.control_dsn, pepper=control_pepper, schema=platform.schema)
        control_audit = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)
        try:
            with control_store.unit_of_work() as work:
                # Rework note: this file's shared `platform` fixture is
                # module-scoped and may already have a control credential
                # bootstrapped by an earlier test in this same session
                # (bootstrap refuses -- CONFLICT -- once ANY row exists,
                # even revoked) -- `reset` always succeeds regardless of
                # prior state and gives this test its own fresh bearer.
                _credential_id, control_bearer = reset_control_credentials(control_store, control_audit, work=work)
        finally:
            control_store.close()
            control_audit.close()

        with TestClient(control_app) as client:
            response = client.get("/control/v1/capabilities", headers={"authorization": f"Bearer {control_bearer}"})
            assert response.status_code == 200, response.text
            assert response.json()["capabilities"]["audit_query"]["visibility_lag_ms"] == 9_000 + 9_000 + 1_000
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(api_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(api_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(controlplane_role))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(controlplane_role))
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
            conn.commit()


# ===========================================================================
# In-memory helpers for the dispatch/coalescing/hook tests below.
# These deliberately do NOT use `PostgresCell`/real Postgres: what they
# check is `DataService`'s own dispatch logic (§7.1-7.4, D-2/D-3/D-4/D-10),
# which is backend-agnostic by construction (`StorageBackend` protocol) --
# exercising it against the in-memory backend keeps these tests fast and
# deterministic (an injected fake clock, no network) without weakening what
# each one actually proves. Section 7 below (`test_each_data_operation_
# adds_exactly_one_application_audit_row` and the parity test) exercises
# the identical dispatch logic against a REAL `PostgresCell` + real
# `PostgresApplicationAuditSink`, so the in-memory-vs-Postgres backend
# choice is never load-bearing for what Phase 4 actually promises.
# ===========================================================================


class _FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _SelectiveFaultSink:
    """Wraps a real `ApplicationAuditSink`, failing only `append` calls
    whose `event_class` is in `fail_event_classes` -- lets a test target
    exactly one durable-write call site while every other call succeeds
    normally, which a single blanket `inject_fault()` cannot express."""

    def __init__(self, inner: ApplicationAuditSink) -> None:
        self._inner = inner
        self.fail_event_classes: set[str] = set()
        self.append_calls: list[dict[str, Any]] = []

    def append(self, **kwargs: Any) -> AuditEvent:
        self.append_calls.append(dict(kwargs))
        if kwargs.get("event_class") in self.fail_event_classes:
            raise RuntimeError("simulated selective sink failure")
        return self._inner.append(**kwargs)

    def events(self) -> tuple:
        return self._inner.events()


def build_service(
    *, durable_audit: Any | None = None, clock: Any | None = None,
    denial_coalesce_window_s: float = 60.0, limits: ResourceLimits | None = None,
) -> tuple[DataService, Any]:
    """A pure in-memory `DataService`, one application (`app-a`, runtime
    credential `secret-a`, developer credential `dev-secret-a`), one seeded
    entity (`notes`, one row) -- mirrors `test_foundation.py::service`'s own
    shape, extended with Phase 4's new constructor knobs."""
    credentials = CredentialStore(pepper="test-pepper-application-audit")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(
        credentials, limits=limits or LIMITS, durable_audit=durable_audit, clock=clock,
        denial_coalesce_window_s=denial_coalesce_window_s,
    )
    control = ControlAuthority(service)
    control.register_application("app-a", entities={"notes": [{"body": "a"}]})
    return service, control


def runtime_context(service: DataService):
    return service.authenticate(compose_bearer_locator("cred-a", "secret-a"))


def developer_context(service: DataService):
    return service.authenticate(compose_bearer_locator("dev-a", "dev-secret-a"))


def durable_events(durable_audit: Any) -> list[dict]:
    return [dict(e) for e in durable_audit.events()]


def test_durable_denial_codes_match_the_design_d3_table() -> None:
    """WP-2(a) review J-2 (supervisor ruling 2026-09-02): `service.py`'s
    `_DURABLE_DENIAL_CODES` is an INCLUSION set -- only design D-3's table
    row "fail-closed 類" (SI-14's minimal authn/authz-denial class) is
    durable/coalesced; everything else (D-3's originally-named 4 non-durable
    codes, and every other reason_code this facade can raise -- `CONFLICT`,
    `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_UNAVAILABLE`,
    ...) is out of scope. This fixes that set against the design's own 6
    named items so a future edit cannot silently widen or narrow it without
    this test moving.
    """
    from r2db_api.service import _DURABLE_DENIAL_CODES

    assert _DURABLE_DENIAL_CODES == {
        "AUTH_REQUIRED", "AUTH_INVALID", "AUTH_REVOKED",
        "FORBIDDEN", "APPLICATION_DISABLED", "DESTRUCTIVE_CONFIRMATION_REQUIRED",
    }
    # Positive control: none of D-3's originally-named 4 non-durable codes,
    # nor the codes this WP's own review flagged as wrongly durable under
    # the old exclusion-list reading, are in the inclusion set.
    for excluded in ("VALIDATION_FAILED", "LIMIT_EXCEEDED", "CAPABILITY_UNSUPPORTED", "NOT_FOUND", "CONFLICT", "PRECONDITION_FAILED", "SERVICE_UNAVAILABLE", "AUTH_STATE_UNAVAILABLE"):
        assert excluded not in _DURABLE_DENIAL_CODES


# ===========================================================================
# Section 4: fail-closed by construction (design D-2, §9.2 property 1).
# ===========================================================================


def test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)

    durable.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(FoundationError) as exc:
        service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}])
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert exc.value.status == 503

    # Data side is untouched: the row is still there.
    durable.inject_fault(None)
    assert service.query(ctx, "notes", select=["id"]) == [{"id": 1}]
    assert [e for e in durable_events(durable) if e["operation"] == "mutate"] == []


def test_schema_operation_is_service_unavailable_when_the_durable_sink_fails() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    dev = developer_context(service)

    durable.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(FoundationError) as exc:
        service.schema(dev, {"operation": "create_entity", "entity": "widgets"})
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert exc.value.status == 503

    durable.inject_fault(None)
    # The entity was never created -- a later create_entity of the same
    # name succeeds cleanly (a lingering half-applied schema change would
    # instead raise CONFLICT). Exactly one durable row exists afterwards --
    # from this SECOND, successful call; the first, faulted attempt left
    # nothing durable behind.
    assert service.schema(dev, {"operation": "create_entity", "entity": "widgets"}).revision == 1
    events = durable_events(durable)
    assert len(events) == 1
    assert events[0]["operation"] == "schema" and events[0]["outcome"] == "allow"


def test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)

    durable.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(FoundationError) as exc:
        service.authenticate("totally-wrong-secret")
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert exc.value.status == 503
    assert durable_events(durable) == []


# ===========================================================================
# Section 5: the D-2 error-row rule (§9.2 property 9) -- a clean data-
# commit failure durably records an `outcome="error"` row for the same
# `request_id` as the `allow` row; a simulated process-loss (the hook's
# `commit_failed()` never runs at all) leaves the `allow` row standing
# alone, by design (N-1's own documented limit).
# ===========================================================================


def _kill_idle_in_transaction_backend(admin_dsn: str, dbname: str) -> None:
    """Terminates whichever backend on `dbname` is currently `idle in
    transaction` -- called from inside a test's own `pre_commit()`
    override, i.e. from the SAME synchronous call stack as the data
    connection's own open (but not-yet-committed) transaction, which is
    therefore sitting idle (no statement in flight) at exactly this
    instant. `pg_terminate_backend` closes that connection outright, so
    the implicit `COMMIT` `conn.transaction()` is about to issue next
    (this is the LAST statement inside that `with` block -- see `postgres.
    py::PostgresCell.transact`'s own comment) fails with a real
    `psycopg.Error` on a dead connection -- a genuine data-commit failure,
    not a simulated one. This never touches the PLATFORM connection the
    durable audit sink itself commits on (a different database entirely),
    so the pre-commit row (and, when exercised, the error row) still land
    for real.
    """
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend' "
                "AND state = 'idle in transaction'",
                [dbname],
            )


class _CommitKillingHook:
    """Wraps a real `ApplicationAuditHook`: `pre_commit()` performs the
    real durable write and then kills the data connection so the caller's
    OWN subsequent implicit commit fails for real (see
    `_kill_idle_in_transaction_backend`); `commit_failed()` is forwarded
    unchanged (or entirely omitted, to simulate process loss -- see
    `omit_commit_failed`)."""

    def __init__(self, real_hook: ApplicationAuditHook, admin_dsn: str, dbname: str, *, omit_commit_failed: bool = False) -> None:
        self._real_hook = real_hook
        self._admin_dsn = admin_dsn
        self._dbname = dbname
        self._omit_commit_failed = omit_commit_failed

    def pre_commit(self) -> None:
        self._real_hook.pre_commit()
        _kill_idle_in_transaction_backend(self._admin_dsn, self._dbname)

    def commit_failed(self) -> None:
        if self._omit_commit_failed:
            return  # simulated process loss: nobody calls this at all in reality
        self._real_hook.commit_failed()


def test_failed_data_commit_writes_an_error_row_for_the_same_request_id(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
        phrase = _delete_phrase(cell, "notes", [{"field": "id", "operator": "eq", "value": 1}])

        request_id = f"r-commit-fail-{uuid.uuid4()}"
        fields = {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        }
        from r2db_api.service import _PreCommitHook

        hook = _CommitKillingHook(_PreCommitHook(sink, fields), platform.admin_dsn, app_a.database)

        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}],
                LIMITS, audit_hook=hook,
            )
        assert exc.value.code == "SERVICE_UNAVAILABLE"

        rows = _application_audit_rows(platform)
        matching = [r for r in rows if r[1] == request_id]
        outcomes = sorted(r[8] for r in matching)
        assert outcomes == ["allow", "error"], f"expected exactly an allow row then an error row for {request_id!r}, got {matching!r}"
        error_row = [r for r in matching if r[8] == "error"][0]
        assert error_row[9] == "commit_failed"

        # The data side genuinely did not commit: the row is still there
        # (the backend was killed mid-transaction, so PostgreSQL discarded
        # it entirely).
        fresh_cell = make_cell(app_a)
        try:
            outcome = fresh_cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS)
            assert [row["id"] for row in outcome.items] == [1]
        finally:
            fresh_cell.close()
    finally:
        sink.close()
        cell.close()


def test_error_row_write_failure_makes_the_response_service_unavailable(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """When the data commit fails AND the subsequent `error`-row write
    itself also fails, the response is still `SERVICE_UNAVAILABLE` (D-2:
    `commit_failed()` is best-effort from the response's point of view --
    the data commit already failed either way)."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
        phrase = _delete_phrase(cell, "notes", [{"field": "id", "operator": "eq", "value": 1}])

        class _FlakySink:
            def __init__(self) -> None:
                self.calls = 0

            def append(self, **kwargs: Any) -> None:
                self.calls += 1
                if self.calls == 1:
                    return  # pre_commit succeeds once
                raise RuntimeError("simulated error-row write failure")

        from r2db_api.service import _PreCommitHook

        hook = _CommitKillingHook(
            _PreCommitHook(_FlakySink(), {
                "event_class": "data_operation", "request_id": "r-both-fail", "application_id": app_a.slug,
                "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
                "operation": "mutate", "target_kind": "entity", "target_id": None,
            }),
            platform.admin_dsn, app_a.database,
        )

        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}],
                LIMITS, audit_hook=hook,
            )
        assert exc.value.code == "SERVICE_UNAVAILABLE"
    finally:
        cell.close()


def test_failed_data_commit_through_dataservice_writes_exactly_two_durable_rows(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """WP-2(a) review B-1 (blocker): a data-commit failure reached through
    the FULL `DataService` path (not `cell.transact(...)` called directly,
    as the two tests above do) must produce exactly 2 durable rows (`allow`
    + `error`) for the one operation -- never a 3rd `deny`/`SERVICE_
    UNAVAILABLE` row from the generic `except FoundationError` denial
    routing every `DataService` public method also has (D-10's prohibited
    case (ii)). The B-1 finding was specifically that this 3rd row is only
    reachable through `DataService`'s own dispatch (`_event`'s deny
    branch), which `cell.transact(...)` called directly -- as the two
    `test_..._error_row_...` tests above do -- structurally cannot exercise
    at all; this test closes that gap by going through `DataService.
    mutate_result` end to end against a real `PostgresCell`.
    """
    sink = real_durable_sink(platform)
    credentials = CredentialStore(pepper="test-pepper-b1")
    with credentials.unit_of_work() as work:
        credentials.add("cred-b1-runtime", app_a.slug, "runtime", "secret-b1-runtime", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("cred-b1-developer", app_a.slug, "developer", "secret-b1-developer", work=work)

    real_cell = make_cell(app_a)

    def _cell_factory(application_id: str, entities: Any) -> PostgresCell:
        assert entities is None
        return real_cell

    service = DataService(credentials, limits=LIMITS, durable_audit=sink, cell_factory=_cell_factory)
    control = ControlAuthority(service)
    control.register_application(app_a.slug)
    try:
        ctx = service.authenticate(compose_bearer_locator("cred-b1-runtime", "secret-b1-runtime"))
        dev = service.authenticate(compose_bearer_locator("cred-b1-developer", "secret-b1-developer"))
        service.schema(dev, {"operation": "create_entity", "entity": "notes", "fields": ["body"]})
        service.mutate(ctx, "notes", [{"operation": "insert", "values": {"body": "a"}}])

        with pytest.raises(FoundationError) as exc:
            service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True}])
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        phrase = exc.value.details["required_confirmation"]

        request_id = f"r-b1-dataservice-{uuid.uuid4()}"
        real_make_audit_hook = DataService._make_audit_hook

        def _killing_hook(self: DataService, canonical: Any, **kwargs: Any) -> Any:
            real_hook = real_make_audit_hook(self, canonical, **kwargs)
            return _CommitKillingHook(real_hook, platform.admin_dsn, app_a.database)

        with patch.object(DataService, "_make_audit_hook", _killing_hook):
            with pytest.raises(FoundationError) as exc:
                service.mutate_result(
                    ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}],
                    request_id=request_id,
                )
        assert exc.value.code == "SERVICE_UNAVAILABLE"

        rows = _application_audit_rows(platform)
        matching = [r for r in rows if r[1] == request_id]
        outcomes = sorted(r[8] for r in matching)
        assert outcomes == ["allow", "error"], f"expected EXACTLY 2 durable rows (allow, error) for {request_id!r} -- never a 3rd deny row (D-10 (ii)); got {matching!r}"
    finally:
        sink.close()
        real_cell.close()


def test_simulated_process_loss_leaves_the_allow_row_alone(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """N-1's own documented limit, fixed as a specification, not a defect:
    if the process disappears between the pre-commit `allow` row's commit
    and the data commit (so `commit_failed()` never runs at all -- no
    exception handler survives to call it), the `allow` row is left
    standing alone. This is simulated by calling `pre_commit()` directly
    and never calling `commit_failed()` at all -- exactly what "the process
    is gone" looks like from the durable sink's point of view."""
    sink = real_durable_sink(platform)
    try:
        request_id = f"r-process-loss-{uuid.uuid4()}"
        fields = {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        }
        from r2db_api.service import _PreCommitHook

        hook = _PreCommitHook(sink, fields)
        hook.pre_commit()  # succeeds -- the durable "allow" row is committed
        # (the process "disappears" here -- commit_failed() is never called)

        rows = [r for r in _application_audit_rows(platform) if r[1] == request_id]
        assert len(rows) == 1
        assert rows[0][8] == "allow"
    finally:
        sink.close()


def _install_commit_time_sleep(platform: types.SimpleNamespace, app: types.SimpleNamespace, entity: str, *, seconds: float) -> None:
    """Installs a deferred constraint trigger on `entity` that sleeps inside
    the COMMIT statement itself (deferred triggers fire at commit, after
    every statement of the transaction has already run) -- the one place a
    cancellation can land AFTER the pre-commit hook has returned. A
    statement timeout cannot do that job: PostgreSQL disarms it before it
    commits, so a COMMIT that runs long inside a deferred trigger is never
    canceled by `SET LOCAL statement_timeout` (measured, not assumed)."""
    admin_dsn = _dsn_with(platform.admin_dsn, dbname=app.database)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(
            f"CREATE FUNCTION public.r2db_test_slow_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep({seconds}); RETURN NULL; END $$"
        )
        admin.execute(
            f"CREATE CONSTRAINT TRIGGER r2db_test_slow_commit AFTER INSERT OR DELETE ON public.{entity} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.r2db_test_slow_commit()"
        )


def _cancel_the_commit_in_flight(admin_dsn: str, dbname: str, *, deadline_s: float = 10.0) -> None:
    """Polls until a backend on `dbname` is running a bare `COMMIT`
    (`conn.transaction()`'s own exit) and cancels that statement with
    `pg_cancel_backend`, the same signal an operator's cancel sends."""
    end = time.monotonic() + deadline_s
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        while time.monotonic() < end:
            rows = admin.execute(
                "SELECT pg_cancel_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid() AND state = 'active' AND query = 'COMMIT'",
                [dbname],
            ).fetchall()
            if rows:
                return
            time.sleep(0.05)


@pytest.mark.parametrize("kind", ["insert", "delete"])
def test_commit_canceled_after_the_pre_commit_row_writes_an_error_row_and_stays_413(platform: types.SimpleNamespace, app_a: types.SimpleNamespace, kind: str) -> None:
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
        phrase = _delete_phrase(cell, "notes", [{"field": "id", "operator": "eq", "value": 1}])
        _install_commit_time_sleep(platform, app_a, "notes", seconds=3.0)

        request_id = f"r-commit-canceled-{kind}-{uuid.uuid4()}"
        fields = {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        }
        from r2db_api.service import _PreCommitHook

        operation = (
            {"operation": "insert", "values": {"body": "b"}} if kind == "insert"
            else {"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}
        )
        canceller = threading.Thread(target=_cancel_the_commit_in_flight, args=(_dsn_with(platform.admin_dsn, dbname=app_a.database), app_a.database))
        canceller.start()
        try:
            with pytest.raises(FoundationError) as exc:
                cell.transact("notes", [operation], LIMITS, audit_hook=_PreCommitHook(sink, fields))
        finally:
            canceller.join()
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413

        matching = [r for r in _application_audit_rows(platform) if r[1] == request_id]
        assert sorted(r[8] for r in matching) == ["allow", "error"], f"expected an allow row then an error row for {request_id!r}, got {matching!r}"
        assert [r[9] for r in matching if r[8] == "error"] == ["commit_failed"]

        # the data did not commit: the seeded row is still the only one, unchanged
        fresh_cell = make_cell(app_a)
        try:
            outcome = fresh_cell.query("notes", select=["id", "body"], where=[], page_size=10, limits=LIMITS)
            assert [(row["id"], row["body"]) for row in outcome.items] == [(1, "a")]
        finally:
            fresh_cell.close()
    finally:
        sink.close()
        cell.close()


def test_commit_waiting_on_a_lock_past_the_execution_budget_writes_an_error_row_and_stays_413(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """The other 413 branch: work a deferred trigger does at commit can wait
    on a lock, and `lock_timeout` (unlike `statement_timeout`) does bound
    that wait. The response stays 413 and the `error` row is written."""
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    admin_dsn = _dsn_with(platform.admin_dsn, dbname=app_a.database)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("CREATE TABLE public.r2db_test_lock_target (id integer)")
            admin.execute(
                "CREATE FUNCTION public.r2db_test_lock_wait() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$ "
                "BEGIN LOCK TABLE public.r2db_test_lock_target IN ACCESS SHARE MODE; RETURN NULL; END $$"
            )
            admin.execute(
                "CREATE CONSTRAINT TRIGGER r2db_test_lock_wait AFTER INSERT ON public.notes "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.r2db_test_lock_wait()"
            )

        request_id = f"r-commit-lock-{uuid.uuid4()}"
        fields = {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        }
        from r2db_api.service import _PreCommitHook

        with psycopg.connect(admin_dsn) as holder:
            holder.execute("LOCK TABLE public.r2db_test_lock_target IN ACCESS EXCLUSIVE MODE")
            with pytest.raises(FoundationError) as exc:
                cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], replace(LIMITS, execution_ms=300), audit_hook=_PreCommitHook(sink, fields))
            holder.rollback()
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413

        matching = [r for r in _application_audit_rows(platform) if r[1] == request_id]
        assert sorted(r[8] for r in matching) == ["allow", "error"], f"expected an allow row then an error row for {request_id!r}, got {matching!r}"
        assert cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS).items == []
    finally:
        sink.close()
        cell.close()


def _schema_hook_fields(app: types.SimpleNamespace, request_id: str) -> dict[str, Any]:
    return {
        "event_class": "data_operation", "request_id": request_id, "application_id": app.slug,
        "actor_type": "application_credential", "actor_id": "cred-fake", "role": "developer",
        "operation": "schema", "target_kind": "entity", "target_id": None,
    }


def test_a_failing_idempotency_record_write_happens_before_the_schema_pre_commit_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """Same order as the data transaction: the pre-commit row is the last
    statement of the schema transaction, after the idempotency record. A
    record write that fails (here: cancelled) therefore leaves no `allow`
    row behind for a schema change that never committed.

    mutation (`postgres.py`, `apply_schema`): move the `audit_hook.
    pre_commit()` block back in front of the idempotency record write -- the
    `allow` row is durable and `hook.fired` is True."""
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        request_id = f"r-schema-idem-order-{uuid.uuid4()}"
        from r2db_api.service import _PreCommitHook

        hook = _PreCommitHook(sink, _schema_hook_fields(app_a, request_id))
        operation = {"operation": "create_entity", "entity": "notes", "fields": ["body"]}

        def _cancelled_record_write(*args: Any, **kwargs: Any) -> None:
            raise psycopg.errors.QueryCanceled("simulated cancel of the idempotency record write")

        with patch.object(PostgresCell, "_idempotency_store", _cancelled_record_write):
            with pytest.raises(FoundationError) as exc:
                cell.apply_schema(
                    operation, developer=True, limits=LIMITS, audit_hook=hook,
                    plan_request={"operation": "create_entity", "entity": "notes"}, idempotency_key="k-schema-idem-order", request_id=request_id,
                )
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413
        assert hook.fired is False
        assert [r for r in _application_audit_rows(platform) if r[1] == request_id] == []
    finally:
        sink.close()
        cell.close()


def _install_schema_commit_trigger(platform: types.SimpleNamespace, app: types.SimpleNamespace, function_body: str) -> None:
    """A deferred constraint trigger on the schema revision table -- every
    schema change updates that row, so the trigger's function runs inside the
    COMMIT itself, after the pre-commit row is durable."""
    admin_dsn = _dsn_with(platform.admin_dsn, dbname=app.database)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f"CREATE FUNCTION public.r2db_test_schema_commit() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$ BEGIN {function_body} RETURN NULL; END $$")
        admin.execute(
            "CREATE CONSTRAINT TRIGGER r2db_test_schema_commit AFTER UPDATE ON public._r2db_schema_revision "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.r2db_test_schema_commit()"
        )


def test_schema_commit_canceled_after_the_pre_commit_row_writes_an_error_row_and_stays_413(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """The schema transaction's COMMIT can be cancelled after the `allow` row
    is durable (a deferred trigger's work is not bounded by `statement_
    timeout`, but a cancel request still interrupts it): the response stays
    413 and the `error` row is written, like the data transaction's.

    mutation (`postgres.py`, `apply_schema`): drop the `commit_failed()` call
    from the `QueryCanceled` branch -- only the `allow` row is there."""
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        _install_schema_commit_trigger(platform, app_a, "PERFORM pg_sleep(3.0);")
        request_id = f"r-schema-commit-canceled-{uuid.uuid4()}"
        from r2db_api.service import _PreCommitHook

        canceller = threading.Thread(target=_cancel_the_commit_in_flight, args=(_dsn_with(platform.admin_dsn, dbname=app_a.database), app_a.database))
        canceller.start()
        try:
            with pytest.raises(FoundationError) as exc:
                cell.apply_schema(
                    {"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS,
                    audit_hook=_PreCommitHook(sink, _schema_hook_fields(app_a, request_id)),
                )
        finally:
            canceller.join()
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413
        matching = [r for r in _application_audit_rows(platform) if r[1] == request_id]
        assert sorted(r[8] for r in matching) == ["allow", "error"], f"expected an allow row then an error row for {request_id!r}, got {matching!r}"
        assert [r[9] for r in matching if r[8] == "error"] == ["commit_failed"]
    finally:
        sink.close()
        cell.close()


def test_schema_commit_waiting_on_a_lock_past_the_execution_budget_writes_an_error_row_and_stays_413(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """The other 413 branch of the schema transaction: work a deferred
    trigger does at commit can wait on a lock, and `lock_timeout` bounds that
    wait. The response stays 413 and the `error` row is written.

    mutation (`postgres.py`, `apply_schema`): drop the `commit_failed()` call
    from the `LockNotAvailable` branch -- only the `allow` row is there."""
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    admin_dsn = _dsn_with(platform.admin_dsn, dbname=app_a.database)
    try:
        # the entity is created first: `create_entity` refuses to commit while a table without row-level security (the lock target below) exists in the database.
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("CREATE TABLE public.r2db_test_lock_target (id integer)")
        _install_schema_commit_trigger(platform, app_a, "LOCK TABLE public.r2db_test_lock_target IN ACCESS SHARE MODE;")
        request_id = f"r-schema-commit-lock-{uuid.uuid4()}"
        from r2db_api.service import _PreCommitHook

        with psycopg.connect(admin_dsn) as holder:
            holder.execute("LOCK TABLE public.r2db_test_lock_target IN ACCESS EXCLUSIVE MODE")
            with pytest.raises(FoundationError) as exc:
                cell.apply_schema(
                    {"operation": "add_field", "entity": "notes", "field": "extra"}, developer=True, limits=replace(LIMITS, execution_ms=1000),
                    audit_hook=_PreCommitHook(sink, _schema_hook_fields(app_a, request_id)),
                )
            holder.rollback()
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413
        matching = [r for r in _application_audit_rows(platform) if r[1] == request_id]
        assert sorted(r[8] for r in matching) == ["allow", "error"], f"expected an allow row then an error row for {request_id!r}, got {matching!r}"
    finally:
        sink.close()
        cell.close()


# ===========================================================================
# Section 6: D-3 coalescing (§9.2 property 10(ii)) and the durable denial
# code vocabulary (§9.2 property 10, D-3's range table, J-2 inclusion list).
# ===========================================================================


def test_concurrent_same_key_denials_are_both_fail_closed_when_the_sink_is_down() -> None:
    """WP-2(a) review B-2 (major): a prior revision of `_DenialCoalescer.
    route` released its lock BEFORE the first-occurrence durable INSERT, so
    a second, concurrent denial for the SAME key could observe "a window
    already exists" (`repeat_count += 1`, an ordinary-looking response)
    while that INSERT was still in flight -- or had already failed -- never
    attempting its own durable write at all. Under a sink outage during a
    denial flood (exactly the scenario D-3's coalescing exists for), this
    let §9.2 property 1's fail-closed guarantee hold only single-threaded:
    a concurrent caller could get a normal 401 instead of 503 while the
    window's own first row was never durably recorded.

    Reproduced deterministically with a blocking sink (no timing luck): a
    first caller is let INTO `sink.append()` and held there; a second,
    concurrent same-key caller is then started and given every reasonable
    chance to resolve early. The fixed `route()` holds the coalescer's lock
    for the whole first-occurrence INSERT, so the second caller cannot even
    acquire the lock -- let alone resolve -- until the first has fully
    failed; both callers then attempt (and fail) their own INSERT and both
    fail closed.
    """
    call_started = threading.Event()
    release = threading.Event()
    call_count = 0
    call_count_lock = threading.Lock()

    class _BlockingThenFailingSink:
        def append(self, **kwargs: Any) -> None:
            nonlocal call_count
            with call_count_lock:
                call_count += 1
                is_first = call_count == 1
            if is_first:
                call_started.set()
                assert release.wait(timeout=5), "test did not release the blocked first call in time"
            raise RuntimeError("simulated sink outage")

        def append_many(self, events: list[Any]) -> None:  # pragma: no cover - unused here
            raise RuntimeError("simulated sink outage")

        def events(self) -> tuple:
            return ()

    service, _control = build_service(durable_audit=_BlockingThenFailingSink())
    results: list[str] = []
    results_lock = threading.Lock()

    def _attempt() -> None:
        try:
            service.authenticate("bogus-secret-race")
        except FoundationError as exc:
            with results_lock:
                results.append(exc.code)

    thread_a = threading.Thread(target=_attempt)
    thread_a.start()
    assert call_started.wait(timeout=5), "the first occurrence's sink.append() was never reached"

    # Thread A is now blocked INSIDE sink.append() for the key's first
    # occurrence, holding `_DenialCoalescer._lock` (the B-2 fix). Start a
    # second, concurrent same-key denial and give it every chance to
    # (wrongly) resolve before thread A's own attempt has even failed.
    thread_b = threading.Thread(target=_attempt)
    thread_b.start()
    time.sleep(0.2)
    with results_lock:
        assert results == [], (
            "a concurrent same-key denial resolved WHILE the first occurrence's own "
            f"insert was still in flight -- the lock was not held across the I/O: {results!r}"
        )

    release.set()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert sorted(results) == ["SERVICE_UNAVAILABLE", "SERVICE_UNAVAILABLE"], (
        f"both concurrent same-key denials against a down sink must fail closed, never a silent ordinary denial: {results!r}"
    )


def test_different_key_denials_do_not_wait_on_each_other() -> None:
    """WP-2(a) fix round 2, supervisor ruling on review m-2: per-KEY
    locking (not a single process-wide lock held across I/O) means a
    DIFFERENT coalescing key's `route()` call must never block on another
    key's in-flight first-occurrence INSERT -- only SAME-key callers
    serialize (B-2, the test immediately above). Key A (an
    `authentication_denial`, `AUTH_INVALID`) is held blocked inside its own
    first-occurrence INSERT; a concurrent DIFFERENT-key denial (`FORBIDDEN`
    from a runtime credential attempting a developer-only schema
    operation) must resolve promptly regardless -- run on its own thread
    with a bounded join timeout, so a regression to process-wide
    serialization fails this test promptly instead of hanging it forever.
    """
    call_started = threading.Event()
    release = threading.Event()

    class _BlockingForKeyASink:
        def append(self, **kwargs: Any) -> None:
            if kwargs.get("reason_code") == "AUTH_INVALID" and not call_started.is_set():
                call_started.set()
                assert release.wait(timeout=5), "test did not release the blocked key-A call in time"
            # Every call (key A's own eventual proceed, and key B's own
            # first occurrence) otherwise just "succeeds" trivially.

        def append_many(self, events: list[Any]) -> None:  # pragma: no cover - unused here
            pass

        def events(self) -> tuple:
            return ()

    service, _control = build_service(durable_audit=_BlockingForKeyASink())

    def _attempt_key_a() -> None:
        with pytest.raises(FoundationError):
            service.authenticate("bogus-secret-key-a")

    thread_a = threading.Thread(target=_attempt_key_a)
    thread_a.start()
    assert call_started.wait(timeout=5), "key A's first-occurrence sink.append() was never reached"

    # Key A is now blocked inside its own first-occurrence INSERT, holding
    # ONLY its own per-key lock. A DIFFERENT key (FORBIDDEN, not
    # AUTH_INVALID) must resolve promptly -- run on its own thread with a
    # bounded join so an accidental regression to process-wide locking
    # fails this test with a clear assertion, not an indefinite hang.
    ctx = runtime_context(service)
    results: dict[str, str] = {}

    def _attempt_key_b() -> None:
        try:
            service.schema(ctx, {"operation": "create_entity", "entity": "widgets_m2_different_key_test"})
        except FoundationError as exc:
            results["code"] = exc.code

    thread_b = threading.Thread(target=_attempt_key_b)
    thread_b.start()
    thread_b.join(timeout=2.0)
    assert not thread_b.is_alive(), (
        "a DIFFERENT-key denial did not resolve within 2s -- looks serialized behind an unrelated "
        "key's in-flight INSERT (process-wide locking regression)"
    )
    assert results.get("code") == "FORBIDDEN"

    release.set()
    thread_a.join(timeout=5)


def test_failed_aggregate_write_retains_the_repeat_count_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    """WP-2(a) fix round 3 review D-1 (major): a sink that fails ONLY the
    coalesced-denial summary (aggregate) row -- the first-occurrence row
    itself succeeds -- must not lose the accumulated repeat count when the
    window expires and that summary write fails. A round-2 revision
    deleted the due window before attempting the write and simply dropped
    it on failure; this closes that gap: the count is retained and
    retried on every subsequent flush, and once the sink recovers, exactly
    one summary row is written carrying the FULL accumulated total (never
    split, never lost). `logging.error` fires exactly once while the
    failure persists (state-transition discipline, not once per attempt),
    matching N-2's own established pattern for the overflow-alert path.
    """
    inner = ApplicationAuditSink()

    class _AggregateOnlyFailingSink:
        def __init__(self) -> None:
            self.fail_aggregate = True

        def append(self, **kwargs: Any) -> None:
            if kwargs.get("count") is not None and self.fail_aggregate:
                raise RuntimeError("simulated aggregate-write failure")
            return inner.append(**kwargs)

        def append_many(self, events: list[Any]) -> None:
            inner.append_many(events)

        def events(self) -> tuple:
            return inner.events()

    faulty = _AggregateOnlyFailingSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=faulty, clock=clock)

    n_repeats = 5
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-d1")
    for _ in range(n_repeats):
        with pytest.raises(FoundationError):
            service.authenticate("bogus-secret-d1")

    # Window still open -- only the first-occurrence row exists so far.
    assert len(durable_events(inner)) == 1

    clock.advance(61.0)
    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()

    # The aggregate write failed -- the repeat count is RETAINED, not lost.
    assert len(durable_events(inner)) == 1
    failed_logs = [r for r in caplog.records if "coalesced-denial summary row could not be written" in r.message]
    assert len(failed_logs) == 1

    # A second attempt while still failing adds no additional log line --
    # the failure STATE has not changed, only the same ongoing failure.
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()
    assert not [r for r in caplog.records if "coalesced-denial summary row could not be written" in r.message]
    assert len(durable_events(inner)) == 1  # still retained, still not lost

    # The sink recovers -- the next flush writes EXACTLY ONE summary row
    # carrying the full accumulated repeat count, and a recovery log fires.
    faulty.fail_aggregate = False
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()
    recovered_logs = [r for r in caplog.records if "coalesced-denial summary row recorded" in r.message]
    assert len(recovered_logs) == 1

    events = durable_events(inner)
    assert len(events) == 2
    summary_row = events[1]
    assert summary_row["reason_code"] == "AUTH_INVALID"
    assert summary_row["count"] == n_repeats


def test_route_and_flush_racing_on_the_same_key_preserves_the_total_repeat_count() -> None:
    """WP-2(a) fix round 3 review D-1 regression guard: a flush sweep's
    aggregate-row write for an expired window and a concurrent `route()`
    call for the SAME key must never lose or double-count repeats.
    Reproduced deterministically with a blocking sink (barrier), not
    timing luck: the sweep is let INTO its aggregate-row write and held
    there; a concurrent same-key denial is then started and given every
    reasonable chance to resolve early (it must not, until the sweep's
    write has fully resolved -- the per-key lock the D-1 fix depends on).
    """
    inner = ApplicationAuditSink()
    release = threading.Event()
    call_started = threading.Event()

    class _BlockingOnAggregateSink:
        def append(self, **kwargs: Any) -> None:
            if kwargs.get("count") is not None and not call_started.is_set():
                call_started.set()
                assert release.wait(timeout=5), "test did not release the blocked aggregate write in time"
            return inner.append(**kwargs)

        def append_many(self, events: list[Any]) -> None:  # pragma: no cover - unused here
            inner.append_many(events)

        def events(self) -> tuple:
            return inner.events()

    clock = _FakeClock()
    service, _control = build_service(durable_audit=_BlockingOnAggregateSink(), clock=clock)

    # Seed an already-expired window with a known repeat count directly
    # (bypassing `route()`, matching this file's own established internal-
    # state-seeding pattern) so the race is deterministic and does not
    # depend on first driving a real window to expiry.
    key = (None, "unknown", "authenticate", "AUTH_INVALID")
    seed_fields = {
        "event_class": "authentication_denial", "request_id": "r-seed", "application_id": None,
        "actor_type": "unknown", "actor_id": None, "role": None, "operation": "authenticate",
        "target_kind": "application", "outcome": "deny", "reason_code": "AUTH_INVALID", "target_id": None,
    }
    seeded_repeat_count = 5
    service._denial_coalescer._windows[key] = {"window_start": clock() - 1000.0, "repeat_count": seeded_repeat_count, "fields": seed_fields}

    thread_a = threading.Thread(target=service.flush_audit_buffer)
    thread_a.start()
    assert call_started.wait(timeout=5), "the sweep's aggregate-row write was never reached"

    # Thread A is now blocked inside the aggregate write, holding this
    # key's OWN lock. A concurrent `route()` call for the SAME key must
    # wait for it.
    results: list[str] = []
    results_lock = threading.Lock()

    def _attempt_same_key() -> None:
        try:
            service.authenticate("bogus-secret-d1-race")
        except FoundationError as exc:
            with results_lock:
                results.append(exc.code)

    thread_b = threading.Thread(target=_attempt_same_key)
    thread_b.start()
    time.sleep(0.2)
    with results_lock:
        assert results == [], "a same-key route() call resolved WHILE the sweep's aggregate write for that key was still in flight"

    release.set()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert results == ["AUTH_INVALID"]

    # No count lost: the aggregate row for the seeded window plus thread
    # B's own first-occurrence row together must account for every
    # occurrence (5 seeded repeats + 1 for thread B's own denial) -- never
    # more, never less.
    events = durable_events(inner)
    aggregate_rows = [e for e in events if e.get("count") is not None]
    first_occurrence_rows = [e for e in events if e.get("count") is None]
    assert sum(r["count"] for r in aggregate_rows) + len(first_occurrence_rows) == seeded_repeat_count + 1


def test_failed_aggregate_write_via_inline_route_expiry_retains_the_repeat_count() -> None:
    """WP-2(a) fix round 4 (spot-check, major): same property as `test_
    failed_aggregate_write_retains_the_repeat_count_and_recovers` above,
    but reached through `route()`'s OWN inline expired-window flush (a
    fresh `route()` call for the SAME key, arriving after the window has
    expired) rather than `_flush_keys`'s sweep -- the exact path the
    round-4 bug lived in: `route()`'s own final `self._windows[key] = ...`
    assignment used to unconditionally OVERWRITE whatever `_requeue_
    failed_aggregate` had just put back moments earlier in the SAME call,
    silently discarding the retained repeat count the instant the very
    next (fresh) first-occurrence write happened to succeed. The existing
    round-3 test never reaches this branch at all (it drives expiry only
    through `flush_audit_buffer()`, never a second `route()` call for the
    same, already-expired key).
    """
    inner = ApplicationAuditSink()

    class _AggregateOnlyFailingSink:
        def __init__(self) -> None:
            self.fail_aggregate = True

        def append(self, **kwargs: Any) -> None:
            if kwargs.get("count") is not None and self.fail_aggregate:
                raise RuntimeError("simulated aggregate-write failure")
            return inner.append(**kwargs)

        def append_many(self, events: list[Any]) -> None:
            inner.append_many(events)

        def events(self) -> tuple:
            return inner.events()

    faulty = _AggregateOnlyFailingSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=faulty, clock=clock)
    key = (None, "unknown", "authenticate", "AUTH_INVALID")

    n_repeats = 5
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-d1-inline")  # first occurrence -- durable row #1
    for _ in range(n_repeats):
        with pytest.raises(FoundationError):
            service.authenticate("bogus-secret-d1-inline")  # in-memory repeats only, window still open

    assert len(durable_events(inner)) == 1

    # Expire the window, then route a FRESH occurrence for the SAME key --
    # this is what drives `route()`'s own inline expiry-flush branch (as
    # opposed to `flush_audit_buffer()`, which goes through `_flush_keys`
    # instead). The aggregate write for the just-expired window fails
    # (requeued); the fresh call's own first-occurrence write succeeds
    # right after it, in the SAME `route()` call.
    clock.advance(61.0)
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-d1-inline")

    # The fresh call's own first-occurrence row IS durable (a genuinely
    # new occurrence) -- but the requeued repeat count from the EXPIRED
    # window must still be present too, not silently discarded by the
    # fresh window's own creation.
    assert len(durable_events(inner)) == 2
    assert service._denial_coalescer._windows[key]["repeat_count"] == n_repeats, (
        "the requeued repeat count was lost when route() opened its fresh window"
    )

    # Recover the sink and force this (now also expired) window to flush
    # -- the aggregate row must carry the FULL original count.
    faulty.fail_aggregate = False
    clock.advance(61.0)
    service.flush_audit_buffer(force_expire_denial_windows=True)

    events = durable_events(inner)
    assert len(events) == 3
    summary_row = events[2]
    assert summary_row["reason_code"] == "AUTH_INVALID"
    assert summary_row["count"] == n_repeats


def test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n() -> None:
    durable = ApplicationAuditSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=durable, clock=clock)

    n_repeats = 7
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-x")
    for _ in range(n_repeats):
        with pytest.raises(FoundationError):
            service.authenticate("bogus-secret-x")

    # Still inside the coalescing window: exactly the first-occurrence row.
    events = durable_events(durable)
    assert len(events) == 1
    assert events[0]["reason_code"] == "AUTH_INVALID"
    assert "count" not in events[0]  # NULL/1

    # Advance past the window and force the sweep.
    clock.advance(61.0)
    service.flush_audit_buffer()

    events = durable_events(durable)
    assert len(events) == 2, f"expected the window's repeat-summary row too, got {events!r}"
    summary = events[1]
    assert summary["count"] == n_repeats
    assert summary["reason_code"] == "AUTH_INVALID"


def test_coalesced_count_leaf_preserves_the_service_facade() -> None:
    from r2db_api.audit_counts import _coalesced_count as leaf_coalesced_count
    from r2db_api.service import _coalesced_count

    assert _coalesced_count is leaf_coalesced_count
    assert _coalesced_count(0) is None
    assert _coalesced_count(1) is None
    assert _coalesced_count(2) == 2
    assert _coalesced_count(7) == 7


def test_coalesced_summary_row_with_exactly_one_repeat_writes_no_literal_count_of_one() -> None:
    """WP-2(b) review B-1 (major, supervisor ruling 2026-09-03): a window
    with exactly ONE repeat (2 total occurrences: the first-occurrence row
    plus one more) must still write its summary row with `count` ABSENT
    (NULL) -- never the literal `1` (contract `audit.query_event_fields_
    note`: "never zero or one"). The general-N test just above uses
    `n_repeats=7` and never exercises this boundary; this test exercises
    it directly with `repeat_count == 1` at flush time.
    """
    durable = ApplicationAuditSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=durable, clock=clock)

    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-boundary")
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-boundary")

    clock.advance(61.0)
    service.flush_audit_buffer()

    events = durable_events(durable)
    assert len(events) == 2, f"expected exactly the first-occurrence row + one summary row, got {events!r}"
    summary = events[1]
    assert "count" not in summary, f"a window representing exactly 2 total occurrences must never write count=1 -- got {summary!r}"


def test_different_denial_keys_do_not_coalesce_together() -> None:
    durable = ApplicationAuditSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=durable, clock=clock)

    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-a")
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-b")

    # Two DIFFERENT invalid secrets both resolve to `actor_id=None` ->
    # "unknown" in the coalescing key, but their VALUES differ only in the
    # secret text, which is not part of the key at all (application_id,
    # actor_id, operation, reason_code) -- so they coalesce into the SAME
    # window (both AUTH_INVALID, both "unknown" actor). This is a
    # deliberate consequence of the key's own shape, not a bug: the key
    # exists to bound row *count*, not to distinguish every possible
    # secret value an attacker could try.
    assert len(durable_events(durable)) == 1


def test_validation_failed_denials_add_no_durable_row() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    with pytest.raises(FoundationError) as exc:
        service.query(ctx, "notes", select="not-a-list")  # type: ignore[arg-type]
    assert exc.value.code == "VALIDATION_FAILED"

    assert durable_events(durable) == []


def test_capability_unsupported_and_not_found_denials_add_no_durable_row() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    with pytest.raises(FoundationError) as exc:
        service.deny_unsupported(ctx, operation="audit_query", message="not implemented")
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"

    with pytest.raises(FoundationError) as exc:
        service.query(ctx, "no_such_entity", select=["id"])
    assert exc.value.code == "NOT_FOUND"

    assert durable_events(durable) == []


def test_force_expire_denial_windows_flushes_an_unexpired_window_too() -> None:
    """WP-2(a) fix round 2 review N-4: `flush_audit_buffer(force_expire_
    denial_windows=True)` (only ever called by a composition root's
    graceful-shutdown path) flushes EVERY currently-open denial-coalescing
    window, not only ones whose own `window_s` has already elapsed --
    otherwise a window still short of expiry at the moment the process
    stops loses its accumulated repeat count entirely, which D-3 only ever
    sanctions for an actual crash, not an orderly stop. The plain
    (default) `flush_audit_buffer()` -- no different from before -- must
    NOT flush an unexpired window at all.
    """
    durable = ApplicationAuditSink()
    clock = _FakeClock()
    service, _control = build_service(durable_audit=durable, clock=clock)

    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-shutdown")
    with pytest.raises(FoundationError):
        service.authenticate("bogus-secret-shutdown")  # repeat -- window still open, well inside 60s

    events_before = durable_events(durable)
    assert len(events_before) == 1  # only the first-occurrence row so far

    # The default (periodic-timer-shaped) flush must NOT touch the
    # still-open window.
    service.flush_audit_buffer()
    assert durable_events(durable) == events_before

    # The shutdown-shaped flush forces it out anyway, with the repeat
    # count (1 repeat) it had accumulated so far. WP-2(b) review B-1
    # (supervisor ruling 2026-09-03): a summary row representing exactly
    # 1 repeat (2 total occurrences) writes `count` ABSENT (NULL), never
    # the literal `1` -- see `test_coalesced_summary_row_with_exactly_
    # one_repeat_writes_no_literal_count_of_one` for the dedicated
    # boundary test; this assertion is updated to match, not weakened.
    service.flush_audit_buffer(force_expire_denial_windows=True)
    events_after = durable_events(durable)
    assert len(events_after) == 2
    summary_row = events_after[1]
    assert summary_row["reason_code"] == "AUTH_INVALID"
    assert "count" not in summary_row


# ===========================================================================
# Section 7: an ordinary data operation's event is durable before its
# response. A query, a catalog read, a non-destructive mutate, and the
# replay of a keyed mutate or schema operation all reach the durable sink
# before the caller sees a result; a sink failure is fail-closed (503).
# ===========================================================================


def _events_for(durable: Any, request_id: str) -> list[dict]:
    return [e for e in durable_events(durable) if e["request_id"] == request_id]


def test_query_event_is_durable_before_the_result_is_returned() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    service.query(ctx, "notes", select=["id"], request_id="r-query-sync")

    rows = _events_for(durable, "r-query-sync")
    assert [(r["event_class"], r["operation"], r["outcome"]) for r in rows] == [("data_operation", "query", "allow")]


def test_catalog_event_is_durable_before_the_result_is_returned() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    service.catalog(ctx, request_id="r-catalog-sync")

    rows = _events_for(durable, "r-catalog-sync")
    assert [(r["event_class"], r["operation"], r["outcome"]) for r in rows] == [("data_operation", "catalog", "allow")]


def test_mutate_replay_event_is_durable_before_the_result_is_returned() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    operations = [{"operation": "insert", "values": {"body": "replayed-once"}}]

    service.mutate_result(ctx, "notes", operations, idempotency_key="k-mutate-replay", request_id="r-mutate-first")
    replay = service.mutate_result(ctx, "notes", operations, idempotency_key="k-mutate-replay", request_id="r-mutate-resend")

    assert replay.request_id == "r-mutate-first"  # answered from the record, not re-executed
    rows = _events_for(durable, "r-mutate-resend")
    assert [(r["event_class"], r["operation"], r["outcome"]) for r in rows] == [("data_operation", "mutate", "replayed")]


def test_schema_replay_event_is_durable_before_the_result_is_returned() -> None:
    """A resent keyed schema operation answered from its record still
    leaves its own durable line -- unlike a first execution, no pre-commit
    hook ran for it, so `_event` itself must write it before the response."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    dev = developer_context(service)
    operation = {"operation": "create_entity", "entity": "widgets_schema_replay", "idempotency_key": "k-schema-replay"}

    service.schema(dev, operation, request_id="r-schema-first")
    replay = service.schema(dev, operation, request_id="r-schema-resend")

    assert replay.replayed is True
    rows = _events_for(durable, "r-schema-resend")
    assert [(r["event_class"], r["operation"], r["outcome"]) for r in rows] == [("privilege_sensitive", "schema", "replayed")]


@pytest.mark.parametrize("kind", ["query", "catalog", "insert", "mutate_replay", "schema_replay"])
def test_a_sink_failure_makes_an_ordinary_operation_service_unavailable_and_keeps_no_event(kind: str) -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    dev = developer_context(service)
    operations = [{"operation": "insert", "values": {"body": "sink-failure"}}]
    schema_operation = {"operation": "create_entity", "entity": "widgets_sink_failure", "idempotency_key": "k-sink-failure-schema"}
    if kind == "mutate_replay":
        service.mutate_result(ctx, "notes", operations, idempotency_key="k-sink-failure-mutate", request_id="r-first")
    if kind == "schema_replay":
        service.schema(dev, schema_operation, request_id="r-first")
    events_before = len(durable_events(durable))

    durable.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(FoundationError) as exc:
        if kind == "query":
            service.query(ctx, "notes", select=["id"])
        elif kind == "catalog":
            service.catalog(ctx)
        elif kind == "insert":
            service.mutate(ctx, "notes", operations)
        elif kind == "mutate_replay":
            service.mutate_result(ctx, "notes", operations, idempotency_key="k-sink-failure-mutate", request_id="r-resend")
        else:
            service.schema(dev, schema_operation, request_id="r-resend")
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert exc.value.status == 503

    durable.inject_fault(None)
    assert len(durable_events(durable)) == events_before  # the failed write kept no event, and no denial row was made up for it


def test_authenticate_success_stays_out_of_the_durable_sink() -> None:
    """`authenticate`'s own success is not a data operation: it stays in the
    legacy in-memory sink only, with no durable row (and so no new failure
    mode on the login path)."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)

    runtime_context(service)
    durable.inject_fault(RuntimeError("simulated durable-sink failure"))
    ctx = runtime_context(service)  # would raise if authenticate wrote durably

    assert ctx is not None
    durable.inject_fault(None)
    assert durable_events(durable) == []


class _ObservingHook:
    """Forwards to a real `_PreCommitHook`; right after the real
    `pre_commit()` returns -- i.e. while the data transaction is still
    open and uncommitted -- it records what a second connection can see:
    the `allow` row in `application_audit`, and the entity's rows."""

    def __init__(self, real_hook: Any, platform: types.SimpleNamespace, app: types.SimpleNamespace, request_id: str) -> None:
        self._real_hook = real_hook
        self._platform = platform
        self._app = app
        self._request_id = request_id
        self.allow_rows_seen_before_commit: list[tuple] | None = None
        self.entity_rows_seen_before_commit: int | None = None
        self.fired = False

    def pre_commit(self) -> None:
        self._real_hook.pre_commit()
        self.fired = True
        self.allow_rows_seen_before_commit = [r for r in _application_audit_rows(self._platform) if r[1] == self._request_id]
        fresh = make_cell(self._app)
        try:
            self.entity_rows_seen_before_commit = len(fresh.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS).items)
        finally:
            fresh.close()

    def commit_failed(self) -> None:
        self._real_hook.commit_failed()


def test_non_destructive_mutate_allow_row_is_committed_before_the_data_commit(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        request_id = f"r-nondestructive-{uuid.uuid4()}"
        from r2db_api.service import _PreCommitHook

        fields = {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        }
        hook = _ObservingHook(_PreCommitHook(sink, fields), platform, app_a, request_id)

        outcome = cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS, audit_hook=hook)

        assert outcome.destructive is False  # an insert never passes the confirmation choke
        assert hook.fired is True
        assert [r[8] for r in hook.allow_rows_seen_before_commit or []] == ["allow"]  # committed before the data
        assert hook.entity_rows_seen_before_commit == 0  # while the data was still uncommitted
        assert len(cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS).items) == 1
    finally:
        sink.close()
        cell.close()


class _FailingSink:
    """An audit sink whose every write fails, standing in for a platform
    database that cannot be written."""

    def append(self, **kwargs: Any) -> None:
        raise RuntimeError("simulated durable-sink failure")


def test_non_destructive_mutate_is_service_unavailable_and_uncommitted_when_the_sink_fails(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        from r2db_api.service import _PreCommitHook

        hook = _PreCommitHook(_FailingSink(), {
            "event_class": "data_operation", "request_id": "r-nondestructive-fail", "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        })
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS, audit_hook=hook)
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert exc.value.status == 503
        assert hook.fired is False
        assert cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS).items == []  # fail-closed: nothing committed
    finally:
        cell.close()


def test_a_failing_idempotency_record_write_happens_before_the_pre_commit_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """The pre-commit row is the last statement of the data transaction --
    after the idempotency record is written. A record write that fails
    (here: cancelled) therefore leaves no `allow` row behind for data that
    never committed."""
    sink = real_durable_sink(platform)
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        request_id = f"r-idem-order-{uuid.uuid4()}"
        from r2db_api.service import _PreCommitHook

        hook = _PreCommitHook(sink, {
            "event_class": "data_operation", "request_id": request_id, "application_id": app_a.slug,
            "actor_type": "application_credential", "actor_id": "cred-fake", "role": "runtime",
            "operation": "mutate", "target_kind": "entity", "target_id": None,
        })
        operations = [{"operation": "insert", "values": {"body": "a"}}]

        def _cancelled_record_write(*args: Any, **kwargs: Any) -> None:
            raise psycopg.errors.QueryCanceled("simulated cancel of the idempotency record write")

        with patch.object(PostgresCell, "_idempotency_store", _cancelled_record_write):
            with pytest.raises(FoundationError) as exc:
                cell.transact(
                    "notes", operations, LIMITS, audit_hook=hook,
                    plan_request={"entity": "notes", "operations": operations}, idempotency_key="k-idem-order", request_id=request_id,
                )
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413
        assert hook.fired is False
        assert [r for r in _application_audit_rows(platform) if r[1] == request_id] == []
    finally:
        sink.close()
        cell.close()


def test_non_destructive_mutate_through_dataservice_writes_exactly_one_durable_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """A real `PostgresCell` records the row itself (pre-commit hook), so
    `DataService` must not write a second one for the same operation."""
    sink = real_durable_sink(platform)
    credentials = CredentialStore(pepper="test-pepper-sync-events")
    with credentials.unit_of_work() as work:
        credentials.add("cred-sync-runtime", app_a.slug, "runtime", "secret-sync-runtime", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("cred-sync-developer", app_a.slug, "developer", "secret-sync-developer", work=work)
    real_cell = make_cell(app_a)

    def _cell_factory(application_id: str, entities: Any) -> PostgresCell:
        assert entities is None
        return real_cell

    service = DataService(credentials, limits=LIMITS, durable_audit=sink, cell_factory=_cell_factory)
    control = ControlAuthority(service)
    control.register_application(app_a.slug)
    try:
        ctx = service.authenticate(compose_bearer_locator("cred-sync-runtime", "secret-sync-runtime"))
        dev = service.authenticate(compose_bearer_locator("cred-sync-developer", "secret-sync-developer"))
        service.schema(dev, {"operation": "create_entity", "entity": "notes", "fields": ["body"]})

        insert_id = f"r-sync-insert-{uuid.uuid4()}"
        query_id = f"r-sync-query-{uuid.uuid4()}"
        service.mutate_result(ctx, "notes", [{"operation": "insert", "values": {"body": "a"}}], request_id=insert_id)
        service.query(ctx, "notes", select=["id"], request_id=query_id)

        rows = _application_audit_rows(platform)
        assert [(r[6], r[8]) for r in rows if r[1] == insert_id] == [("mutate", "allow")]
        assert [(r[6], r[8]) for r in rows if r[1] == query_id] == [("query", "allow")]
    finally:
        sink.close()
        real_cell.close()


# ===========================================================================
# Section 8: dispatch-point correctness (§9.2 properties 6/8, D-2/D-10).
# ===========================================================================


def test_mutation_outcome_destructive_still_reports_the_confirmation_choke() -> None:
    """`MutationOutcome.destructive` still says whether a batch passed
    `require_destructive_confirmation`: a batch with only insert/update
    never sets it, but a confirmed delete does -- even though both reach
    `DataService` through the identical `mutate` call and the identical
    `data_operation` event_class. It no longer selects how the event is
    written (every real batch is recorded before its response)."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    outcome = service._mutate_outcome(ctx, "notes", [{"operation": "insert", "values": {"body": "x"}}], transaction="atomic", request_id=None)
    assert outcome.destructive is False

    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)
    outcome = service._mutate_outcome(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}], transaction="atomic", request_id=None)
    assert outcome.destructive is True


class _CountingHook:
    """An `ApplicationAuditHook` that counts its calls and can be made to fail."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.pre_commit_calls = 0
        self.commit_failed_calls = 0

    def pre_commit(self) -> None:
        self.pre_commit_calls += 1
        if self._fail:
            raise RuntimeError("simulated pre-commit failure")

    def commit_failed(self) -> None:
        self.commit_failed_calls += 1


def test_in_memory_non_destructive_mutate_calls_the_pre_commit_hook_before_the_batch_is_kept() -> None:
    """The in-memory backend calls the audit hook for every real batch, like
    the PostgreSQL one -- the batch is kept only once the hook has returned,
    and a hook that raises leaves the data untouched.

    mutation (`structured.py`, `ApplicationCell.transact`): call the hook only
    for a destructive batch again (`if audit_hook is not None:` becomes `if
    destructive and audit_hook is not None:`) -- the hook is never called for
    the insert and the failing one lets the row in."""
    cell = ApplicationCell(application_id="app-mem-hook-order")
    cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
    hook = _CountingHook()
    outcome = cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS, audit_hook=hook)
    assert outcome.destructive is False
    assert hook.pre_commit_calls == 1
    assert [row["body"] for row in cell.query("notes", select=["body"], where=[], page_size=10, limits=LIMITS).items] == ["a"]

    failing = _CountingHook(fail=True)
    with pytest.raises(RuntimeError, match="simulated pre-commit failure"):
        cell.transact("notes", [{"operation": "insert", "values": {"body": "b"}}], LIMITS, audit_hook=failing)
    assert failing.pre_commit_calls == 1
    assert [row["body"] for row in cell.query("notes", select=["body"], where=[], page_size=10, limits=LIMITS).items] == ["a"]


def test_delete_bearing_mutate_adds_exactly_one_durable_row() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)

    service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}])

    events = durable_events(durable)
    assert len(events) == 1
    assert events[0]["operation"] == "mutate"
    assert events[0]["outcome"] == "allow"


def test_each_data_operation_adds_exactly_one_application_audit_row() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    dev = developer_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)

    # A confirmed delete: exactly +1 durable row immediately.
    service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}])
    assert len(durable_events(durable)) == 1

    # An ordinary insert: exactly +1 durable row immediately as well (D-10:
    # max one row per operation), with no flush call in between.
    service.mutate(ctx, "notes", [{"operation": "insert", "values": {"body": "b"}}])
    assert len(durable_events(durable)) == 2

    # Schema (unconditionally fail-closed): +1 more.
    service.schema(dev, {"operation": "create_entity", "entity": "widgets_count_test"})
    assert len(durable_events(durable)) == 3


def test_in_memory_and_postgres_application_audit_sinks_have_parity(platform: types.SimpleNamespace) -> None:
    """D-10's own parity requirement: the same sequence of `append`/
    `append_many` calls, against both sink implementations, produces the
    same READ-BACK shape (field-for-field, modulo the columns each storage
    technology derives itself -- `event_id`/`occurred_at` are supplied by
    the caller in both cases and therefore compared exactly; `audit_seq`/
    `recorded_at` have no in-memory equivalent at all and are excluded from
    the comparison)."""
    memory = ApplicationAuditSink()
    pg = real_durable_sink(platform)
    try:
        base_kwargs = dict(
            request_id="r-parity", application_id="app-parity", actor_type="application_credential",
            actor_id="cred-parity", role="runtime", operation="mutate", target_kind="entity",
            target_id=None, reason_code=None,
        )
        event_id = str(uuid.uuid4())
        for sink in (memory, pg):
            with patch("uuid.uuid4", return_value=uuid.UUID(event_id)):
                sink.append(event_class="data_operation", outcome="allow", count=None, **base_kwargs)

        memory_rows = memory.events()
        assert len(memory_rows) == 1
        pg_rows = _application_audit_rows(platform)
        pg_row = [r for r in pg_rows if r[1] == "r-parity"][0]

        m = memory_rows[0]
        assert m["event_class"] == pg_row[0] == "data_operation"
        assert m["request_id"] == pg_row[1] == "r-parity"
        assert m["application_id"] == pg_row[2] == "app-parity"
        assert m["actor_type"] == pg_row[3] == "application_credential"
        assert m["actor_id"] == pg_row[4] == "cred-parity"
        assert m["role"] == pg_row[5] == "runtime"
        assert m["operation"] == pg_row[6] == "mutate"
        assert m["target_kind"] == pg_row[7] == "entity"
        assert m["outcome"] == pg_row[8] == "allow"
        assert pg_row[9] is None  # reason_code
        assert pg_row[10] is None  # target_id
        assert pg_row[11] is None  # count

        # append_many parity: a 2-event batch lands identically in both.
        batch = [
            AuditEvent(str(uuid.uuid4()), "data_operation", "2026-09-02T00:00:00+00:00", "r-parity-batch", "app-parity", "application_credential", "cred-parity", "runtime", "query", "entity", "allow", None, None, None),
            AuditEvent(str(uuid.uuid4()), "data_operation", "2026-09-02T00:00:01+00:00", "r-parity-batch", "app-parity", "application_credential", "cred-parity", "runtime", "query", "entity", "allow", None, None, None),
        ]
        memory.append_many(batch)
        pg.append_many(batch)
        assert len([e for e in memory.events() if e["request_id"] == "r-parity-batch"]) == 2
        assert len([r for r in _application_audit_rows(platform) if r[1] == "r-parity-batch"]) == 2

        # Fault-injection parity: both sinks raise on append when faulted --
        # `ApplicationAuditSink.inject_fault` is the in-memory mechanism;
        # the Postgres sink's own equivalent is a genuinely broken
        # connection, which this parity test does not need to reproduce
        # (Section 4's real-connection fault-injection tests already cover
        # `PostgresApplicationAuditSink`'s own failure path against a real
        # server). What matters for parity is the CALL CONTRACT: both
        # expose `append`/`append_many` with the identical keyword shape,
        # verified above by calling both with the same arguments.
        memory.inject_fault(RuntimeError("x"))
        with pytest.raises(RuntimeError):
            memory.append(event_class="x", outcome="deny", **base_kwargs)
        memory.inject_fault(None)
    finally:
        pg.close()


# ---------------------------------------------------------------------------
# N-2 (monitor ruling 2026-09-05, delta review §4): "the dual check runs on
# the connection the writer sink's own pool hands out" is the central
# claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c)),
# but nothing pinned that `borrow_connection()` actually delegates to
# `self._pool.connection()` -- the delta review's own mutation B (swapping
# BOTH sinks' `borrow_connection` bodies for a throwaway `psycopg.connect`
# outside the pool) left the full 889-test suite green. These two
# zero-network tests substitute a fake `_pool` object for the real one
# (`_RolePool.__init__` never opens a connection itself, so this needs no
# real PostgreSQL) and assert `borrow_connection()` returns EXACTLY the
# sentinel `_pool.connection()` produces -- an identity check that a
# rewritten `borrow_connection` opening a connection some OTHER way cannot
# satisfy by accident.
# ---------------------------------------------------------------------------


class _SentinelPool:
    def __init__(self) -> None:
        self.connection_call_count = 0
        self.sentinel = object()

    def connection(self):
        self.connection_call_count += 1
        return self.sentinel


def test_application_audit_sink_borrow_connection_delegates_to_its_own_pool() -> None:
    sink = PostgresApplicationAuditSink("postgresql://unused/unused", schema="unused_schema", pool_size=1)
    fake_pool = _SentinelPool()
    sink._pool = fake_pool  # noqa: SLF001 -- substituting the real _RolePool for a zero-network fake
    result = sink.borrow_connection()
    assert result is fake_pool.sentinel
    assert fake_pool.connection_call_count == 1


def test_control_audit_sink_borrow_connection_delegates_to_its_own_pool() -> None:
    sink = PostgresControlAuditSink("postgresql://unused/unused", schema="unused_schema", pool_size=1)
    fake_pool = _SentinelPool()
    sink._pool = fake_pool  # noqa: SLF001 -- substituting the real _RolePool for a zero-network fake
    result = sink.borrow_connection()
    assert result is fake_pool.sentinel
    assert fake_pool.connection_call_count == 1


# ===========================================================================
# Q4 phase WP-3 (design D-3(f), work order §4 WP-3): the cell open time
# check (F-12) exercised through the REAL startup path (`r2db_api.main.
# build_app`), not just a direct `PostgresCell.verify_platform_upgrades_
# applied()` call (`test_postgres.py`'s own unit-level coverage) -- proving
# `main.py`'s own `_cell_factory` actually WIRES this check in, the same
# non-vacuity discipline `test_build_app_double_check_reflects_the_real_
# role_setting_not_a_cached_default`'s own docstring states for the D-1(b)
# double-check ("a mutation dropping the double-check call entirely ...
# would leave undetected by a test that only ever exercises
# `PostgresApplicationAuditSink` directly").
# ===========================================================================


def _issue_runtime_credential(platform: types.SimpleNamespace, app: types.SimpleNamespace) -> tuple[str, str]:
    """Seeds a fresh RUNTIME credential directly against the platform
    database (mirrors `test_surfaces_env.py::_issue_and_compose`'s own
    convention) -- returns `(credential_id, raw_secret)`; the caller
    composes the `Bearer <credential_id>.<secret>` header itself."""
    from r2db_api.credential_store import PostgresCredentialStore

    store = PostgresCredentialStore(platform.control_dsn, pepper="synthetic-test-pepper-f12-main", schema=platform.schema)
    try:
        credential_id = "crd_" + secrets.token_hex(8)
        secret = "h1-e2e-secret-" + secrets.token_urlsafe(8)
        with store.unit_of_work() as work:
            store.add(credential_id, app.slug, "runtime", secret, work=work)
    finally:
        store.close()
    return credential_id, secret


_F12_MESSAGE_UPGRADE_9 = (
    "This application's storage is missing platform upgrade(s) 9: the deployment must apply "
    "them before this application can serve requests. Run 'python -m r2db_api.ops "
    "upgrade-applications --lock-timeout <value>' (its '--dry-run' shows applied and pending "
    "per application and requires the same '--lock-timeout'), then retry."
)


def test_build_app_h1_serves_every_application_and_refuses_only_the_one_with_a_pending_upgrade(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, app_b: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """裁定 1 (H-1 = (a), supervisor ruling 2026-09-05, review H-1): a
    served application whose own ledger is missing an upgrade gets a
    REFUSING cell (`postgres._RefusingPlatformUpgradeCell`), never a
    process that fails to start. `app_a`'s own ledger is complete (seeded
    `{9}` by the updated `0003`); `app_b`'s own upgrade 9 is deleted below
    before `build_app` ever runs. Exercised over REAL HTTP
    (`starlette.testclient.TestClient`, not a direct Python call), the
    same non-vacuity discipline this file already applies to the D-1(b)
    double-check: `app_a`'s own `GET /v1/catalog` must return 200 and
    `app_b`'s own `GET /v1/catalog` must return 503 with the F-12 message
    verbatim -- proving `build_app` itself starts (a mutation reverting
    H-1(a) back to the pre-rework "`_cell_factory` lets `Foundation
    Error` propagate" form would make THIS test fail at `build_app(...)`
    itself, before either HTTP assertion is ever reached)."""
    conn = psycopg.connect(app_b.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
    finally:
        conn.close()

    env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f12-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": f"{app_a.slug},{app_b.slug}",
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_RUNTIME_DSN": app_b.runtime_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_DEVELOPER_DSN": app_b.developer_dsn,
    }
    module = _reload_module_with_env("r2db_api.main", env, monkeypatch)

    # H-1(a)'s own headline claim: this must NOT raise, even though
    # `app_b`'s own ledger is missing upgrade 9.
    asgi_app = module.build_app(env=env)
    try:
        credential_a, secret_a = _issue_runtime_credential(platform, app_a)
        credential_b, secret_b = _issue_runtime_credential(platform, app_b)
        with TestClient(asgi_app) as client:
            response_a = client.get("/v1/catalog", headers={"authorization": f"Bearer {credential_a}.{secret_a}"})
            assert response_a.status_code == 200

            response_b = client.get("/v1/catalog", headers={"authorization": f"Bearer {credential_b}.{secret_b}"})
            assert response_b.status_code == 503
            body_b = response_b.json()
            assert body_b["code"] == "SERVICE_UNAVAILABLE"
            assert body_b["message"] == _F12_MESSAGE_UPGRADE_9
            # U-2 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査,
            # design D-3(f) 追記の精密化): H-1's own refusal is scoped to
            # operations that cross the storage boundary -- `/v1/
            # capabilities` (the discovery document) never touches the
            # cell, so it must still answer normally (200) for `app_b`
            # even while its own `GET /v1/catalog` is refused above. This
            # is what keeps an operator's own AI agent able to read the
            # F-12 remediation hint via `/v1/catalog`'s own error body
            # while ALSO being able to read this application's own
            # declared capabilities.
            response_b_capabilities = client.get(
                "/v1/capabilities", headers={"authorization": f"Bearer {credential_b}.{secret_b}"}
            )
            assert response_b_capabilities.status_code == 200
    finally:
        asgi_app.app.state.service._durable_audit.close()
        asgi_app.app.state.service._credentials.close()


def test_build_app_h1_logs_the_f12_message_verbatim_at_cell_open_time(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, app_b: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """U-6 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査): H-1's own
    design-doc claim ("起動時にはログへ F-12 を1行出す (API 応答と同じ
    文面)") previously had no direct evidence -- `_cell_factory`'s own
    stderr `print` was a visual-only check (裁定 1 の証拠不足).
    `main.py::_cell_factory` now logs through the standard `logging`
    module, so `caplog` pins the verbatim F-12 text at cell-open time --
    the SAME text `app_b`'s own HTTP responses carry (companion H-1 test
    above) -- and confirms `app_a` (whose own ledger is complete) never
    logs a refusal at all."""
    conn = psycopg.connect(app_b.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
    finally:
        conn.close()

    env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f12-log",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": f"{app_a.slug},{app_b.slug}",
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_RUNTIME_DSN": app_b.runtime_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_DEVELOPER_DSN": app_b.developer_dsn,
    }
    module = _reload_module_with_env("r2db_api.main", env, monkeypatch)

    caplog.set_level(logging.WARNING, logger="r2db_api.main")
    asgi_app = module.build_app(env=env)
    try:
        messages = [record.getMessage() for record in caplog.records if record.name == "r2db_api.main"]
        expected = f"r2db_api: application '{app_b.slug}' cell refusing requests: {_F12_MESSAGE_UPGRADE_9}"
        assert expected in messages
        assert not any(app_a.slug in message for message in messages)
    finally:
        asgi_app.app.state.service._durable_audit.close()
        asgi_app.app.state.service._credentials.close()


def test_build_app_h1_after_ops_upgrade_applications_and_a_restart_the_refused_application_serves_normally(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, app_b: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """裁定 1 (H-1, (i)/(ii)): running the real `ops upgrade-applications`
    against `app_b` (whose own ledger is missing upgrade 9, deleted below)
    and then restarting the data-plane process (a fresh `build_app` call,
    the only way this rework's own startup snapshot -- D-1(e)/D-2(g)/U-3
    -- is ever re-read) makes `app_b`'s own cell a normal one again: its
    `GET /v1/catalog` now returns 200, the exact same real-HTTP
    observation the companion test above uses to prove the 503."""
    conn = psycopg.connect(app_b.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
    finally:
        conn.close()

    env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-f12-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": f"{app_a.slug},{app_b.slug}",
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _SLOT_DIR,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_RUNTIME_DSN": app_b.runtime_dsn,
        f"R2DB_APP_{app_b.slug.upper()}_DEVELOPER_DSN": app_b.developer_dsn,
    }
    module = _reload_module_with_env("r2db_api.main", env, monkeypatch)

    # Confirm the refusal first (same observation as the companion test).
    asgi_app = module.build_app(env=env)
    try:
        credential_b, secret_b = _issue_runtime_credential(platform, app_b)
        with TestClient(asgi_app) as client:
            response = client.get("/v1/catalog", headers={"authorization": f"Bearer {credential_b}.{secret_b}"})
            assert response.status_code == 503
    finally:
        asgi_app.app.state.service._durable_audit.close()
        asgi_app.app.state.service._credentials.close()

    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    # `ops.py`'s own test-only escape hatch (`test_ops_upgrade.py`'s own
    # established convention) -- points `_migrations_dir()` at the
    # REWRITTEN `0009` (this module's own throwaway schema prefix)
    # instead of the real `r2db-api/migrations/`, whose `0009` names the
    # real deployment's literal `r2dbsvc_registry`.
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.upgrade_migrations_dir))
    # design D-2: this
    # test's own throwaway-cluster launcher (`tools/testpg/dsa_testpg.
    # py`) exports `PGPORT`/`PGUSER`/`PGPASSFILE` ambiently at the
    # PROCESS level; `platform.control_dsn` above already carries every
    # connection parameter `upgrade-applications` needs explicitly, so
    # those ambient exports are pure interference for `_psql_connection_
    # env`'s own A-13 fail-closed check (`ops.main` below runs IN-
    # PROCESS, so `os.environ` itself must be cleared).
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)
    rc = ops.main(["upgrade-applications", "--application", app_b.slug, "--lock-timeout", "5000ms"])
    assert rc == 0

    # "Restart" -- a fresh `build_app` call re-reads the ledger this
    # rework's own startup snapshot only ever reads once per process.
    asgi_app_restarted = module.build_app(env=env)
    try:
        credential_b2, secret_b2 = _issue_runtime_credential(platform, app_b)
        with TestClient(asgi_app_restarted) as client:
            response = client.get("/v1/catalog", headers={"authorization": f"Bearer {credential_b2}.{secret_b2}"})
            assert response.status_code == 200
    finally:
        asgi_app_restarted.app.state.service._durable_audit.close()
        asgi_app_restarted.app.state.service._credentials.close()
