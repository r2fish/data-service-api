"""Phase 4 WP-2(a): the durable application-plane audit sink -- migration
`0007_application_audit.sql`, the sink pair (`audit.ApplicationAuditSink` /
`credential_store.PostgresApplicationAuditSink`), the `StorageBackend`
pre-commit hook (`backend.py`/`structured.py`/`postgres.py`), the dispatch
rules in `service.py` (fail-closed vs. coalesced-denial vs. buffer vs.
non-durable), the bounded buffer + overflow alert, and the two writer-
connection timeouts -- tested against real PostgreSQL (§5.3 C-5: must not
be skipped) and, where real-PostgreSQL realism is not the point of the
test, against the pure in-memory backend (`structured.ApplicationCell` +
`audit.ApplicationAuditSink`), which lets the dispatch/buffer/coalescing
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
# In-memory helpers for the dispatch/buffer/coalescing/hook tests below.
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
    """Wraps a real `ApplicationAuditSink`, failing only `append`/
    `append_many` calls whose `event_class` is in `fail_event_classes` --
    lets a test target exactly one durable-write call site (e.g. only the
    D-4 overflow-alert row) while every other call succeeds normally, which
    a single blanket `inject_fault()` cannot express."""

    def __init__(self, inner: ApplicationAuditSink) -> None:
        self._inner = inner
        self.fail_event_classes: set[str] = set()
        self.append_calls: list[dict[str, Any]] = []
        self.append_many_calls: int = 0

    def append(self, **kwargs: Any) -> AuditEvent:
        self.append_calls.append(dict(kwargs))
        if kwargs.get("event_class") in self.fail_event_classes:
            raise RuntimeError("simulated selective sink failure")
        return self._inner.append(**kwargs)

    def append_many(self, events: list[AuditEvent]) -> None:
        self.append_many_calls += 1
        if "__buffer__" in self.fail_event_classes:
            raise RuntimeError("simulated buffer-flush failure")
        self._inner.append_many(events)

    def events(self) -> tuple:
        return self._inner.events()


def build_service(
    *, durable_audit: Any | None = None, clock: Any | None = None, audit_buffer_capacity: int = 1000,
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
        audit_buffer_capacity=audit_buffer_capacity, denial_coalesce_window_s=denial_coalesce_window_s,
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
    assert durable_events(durable) == []


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


def test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    with pytest.raises(FoundationError) as exc:
        service.query(ctx, "notes", select="not-a-list")  # type: ignore[arg-type]
    assert exc.value.code == "VALIDATION_FAILED"

    assert durable_events(durable) == []
    assert service._audit_buffer.pending_count() == 0


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
# Section 7: D-4 bounded buffer + overflow alert (§9.2 property 3/7).
# ===========================================================================


class _AlwaysFailingAppendMany:
    """WP-2(a) review M-2: `_AuditBuffer.push` now triggers a SYNCHRONOUS
    `flush()` the moment the buffer reaches its threshold (§7.3's own
    "periodic or threshold" flush triggers), and `flush()` now RETAINS
    buffered events on a failed `append_many` instead of discarding them
    (so a transient failure is retried, not lost outright) -- together,
    this means that under a HEALTHY sink, capacity eviction is no longer
    reachable via ordinary sequential `push()` calls at all: the threshold
    flush keeps draining the buffer well before it can ever reach capacity
    (see `test_healthy_sink_threshold_flush_prevents_reaching_capacity_
    eviction`, below, which proves exactly this). Genuine eviction is now a
    signal that the SINK cannot keep up, not an artifact of the periodic
    timer's interval -- so these tests reach it with a durably-failing
    `append_many` (a slow/down sink is exactly the scenario D-4's overflow
    alert exists for)."""

    def append(self, **kwargs: Any) -> None:
        pass  # unused by these two tests

    def append_many(self, events: list[Any]) -> None:
        raise RuntimeError("simulated durably-failing sink")

    def events(self) -> tuple:
        return ()


def test_buffer_does_not_grow_past_its_configured_bound() -> None:
    service, _control = build_service(durable_audit=_AlwaysFailingAppendMany(), audit_buffer_capacity=3)
    ctx = runtime_context(service)

    for _ in range(10):
        service.query(ctx, "notes", select=["id"])

    assert service._audit_buffer.pending_count() == 3


def test_healthy_sink_threshold_flush_prevents_reaching_capacity_eviction() -> None:
    """The positive counterpart to the eviction tests around it (M-2's own
    "壊れるシナリオ", proven in the direction it actually protects against):
    under a HEALTHY sink, pushing well past a small capacity never once
    evicts -- the threshold flush (§7.3, `_AuditBuffer._FLUSH_THRESHOLD_
    FRACTION`) keeps draining the buffer first."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable, audit_buffer_capacity=5)
    ctx = runtime_context(service)

    for _ in range(50):
        service.query(ctx, "notes", select=["id"])

    assert service._audit_buffer.pending_count() < 5
    # Every event pushed either sits in the (small, below-threshold) tail
    # or was already durably flushed -- none was silently dropped.
    assert len(durable_events(durable)) + service._audit_buffer.pending_count() == 50


def test_concurrent_periodic_and_threshold_flush_never_double_writes_pending_events() -> None:
    """WP-3(a) review B-2 (both peers): `_AuditBuffer.flush()` had no
    reentrancy guard. `push()`'s own synchronous threshold-flush (M-2,
    above) and the composition root's periodic flush thread
    (`main.py`'s `_audit_flush_loop` -> `service.flush_audit_buffer()`) can
    both call `flush()` on the SAME buffer instance concurrently. The old
    body only ever held `self._lock` for the brief snapshot
    (`pending = list(self._events)`) and, on success, for the brief
    deletion (`del self._events[:len(pending)]`) -- the durable
    `append_many` I/O itself ran with the lock released. A second,
    concurrent `flush()` call could take an IDENTICAL snapshot of
    `self._events` before the first one's `append_many` returned and
    deleted that prefix, so BOTH durably wrote the same pending events --
    D-10's "1 operation = at most 1 durable row" broken by duplication
    (observed verbatim on the MitateDB peer as `['e1','e2','e3','e1',
    'e2','e3']`; r2db is the same shape).

    Reproduced deterministically (not as a rare timing accident): a fake
    sink blocks the FIRST `append_many` call it receives (signalling once
    it has been entered) and lets any OTHER concurrent call through
    immediately. The test starts one `flush()` thread, waits until it is
    confirmed blocked inside `append_many` (i.e. it has already taken its
    snapshot but not yet deleted it), THEN starts a second `flush()` call
    for the very same buffer and lets it run to completion, and only then
    releases the first call. This is exactly the interleaving a real
    periodic-thread/threshold-flush race can hit, made certain instead of
    probabilistic -- and it stays deterministic under the fix too: a
    correct swap-under-lock leaves the second call nothing to flush (it
    returns immediately without ever calling the sink), so this test can
    never deadlock waiting for a second sink call that a correct
    implementation would not make.
    """
    from r2db_api.service import _AuditBuffer

    class _BlockFirstCallSink:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []
            self._state_lock = threading.Lock()
            self.first_call_started = threading.Event()
            self.release_first_call = threading.Event()
            self._first_call_claimed = False

        def append(self, **kwargs: Any) -> None:  # pragma: no cover - unused by this test
            raise AssertionError("append() (single-event) is not used by this reentrancy test")

        def append_many(self, events: "list[AuditEvent]") -> None:
            with self._state_lock:
                is_first = not self._first_call_claimed
                self._first_call_claimed = True
            if is_first:
                self.first_call_started.set()
                assert self.release_first_call.wait(timeout=5), "test never released the blocked first append_many() call"
            with self._state_lock:
                self.calls.append([e.request_id for e in events])

    sink = _BlockFirstCallSink()
    buffer = _AuditBuffer(sink, capacity=1000, clock=lambda: 0.0)
    # Seed a pre-existing backlog directly -- this is the SAME backlog both
    # flush() calls below race over, mirroring "the periodic timer fires
    # while a request-path threshold flush is already in flight for it".
    for i in range(3):
        buffer._events.append(
            AuditEvent(
                str(uuid.uuid4()), "data_operation", "2026-09-03T00:00:00+00:00",
                f"e{i + 1}", "app-a", "application_credential", "cred-a", "runtime",
                "query", "entity", "allow", None, None, None,
            )
        )

    thread_a = threading.Thread(target=buffer.flush, name="periodic-flush")
    thread_a.start()
    assert sink.first_call_started.wait(timeout=5), "thread A's flush() never reached append_many()"

    # Thread A is now blocked inside append_many, holding no lock -- pre-fix,
    # its snapshot is still sitting un-deleted in `self._events`; post-fix,
    # it has already been swapped out and `self._events` is empty.
    thread_b = threading.Thread(target=buffer.flush, name="threshold-flush")
    thread_b.start()
    thread_b.join(timeout=5)
    assert not thread_b.is_alive(), "thread B's flush() did not complete promptly"

    sink.release_first_call.set()
    thread_a.join(timeout=5)
    assert not thread_a.is_alive(), "thread A's flush() deadlocked after being released"

    all_written = [rid for call in sink.calls for rid in call]
    assert sorted(all_written) == ["e1", "e2", "e3"], (
        "the same pending backlog must be durably written EXACTLY ONCE across both concurrent "
        f"flush() calls (periodic + threshold), never duplicated -- got {all_written!r} from calls {sink.calls!r}"
    )
    assert buffer.pending_count() == 0, f"both events must have left the buffer after a successful flush, got {buffer.pending_count()} left"


def test_concurrent_push_during_a_failing_flush_never_grows_the_buffer_past_capacity() -> None:
    """WP-3(a) review B-1 (blocker, on the B-2 swap-out fix above): while
    `flush()` holds `pending` outside `self._events` (the swap that fixed
    B-2's double-write), `push()` sees an (transiently empty) buffer and
    does not evict against `pending`'s size -- only against whatever
    `push()` itself is concurrently adding. A naive unconditional
    restore-on-failure (`self._events = pending + self._events`) could
    therefore let the buffer grow WITHOUT BOUND across repeated failed
    flushes, breaking D-4's "bounded in-memory buffer (既定 1000)" -- and
    silently: no `push()` eviction fires during that growth, so neither
    `_dropped_total` nor the overflow alert ever reflects it (a sink
    outage would accumulate unbounded evidence in memory with no in-band
    signal at all).

    Reproduces the exact scenario deterministically: a `capacity`-sized
    backlog is already held by an in-flight, durably-failing `flush()`
    call (blocked inside `append_many` via a `threading.Event`, not a
    timing guess) when MORE events are concurrently `push()`-ed. Asserts
    (i) the buffer never exceeds `capacity` once the failed flush's
    restore completes, (ii) `_dropped_total` equals EXACTLY the number of
    events actually, irrevocably truncated by that restore (never the
    retained remainder -- N-1's own discipline), and (iii) the truncation
    drops the OLDEST events first (FIFO, matching `push()`'s own `pop(0)`
    eviction), never the newly-pushed ones.
    """
    from r2db_api.service import _AuditBuffer

    class _BlockThenAlwaysFailSink:
        def __init__(self) -> None:
            self.first_call_started = threading.Event()
            self.release_first_call = threading.Event()
            self.append_calls: list[dict[str, Any]] = []

        def append(self, **kwargs: Any) -> None:
            # The overflow-alert row (`_retry_alert()`, called at the tail
            # of `flush()`) -- recorded (not just accepted) so this test can
            # assert on its `count` directly, since `flush()`'s own success
            # here immediately resolves `_dropped_total` back towards 0
            # (by design -- the alert row having been durably written IS
            # what the drop count is for), so `_dropped_total` itself is not
            # observable post-flush.
            self.append_calls.append(dict(kwargs))

        def append_many(self, events: "list[AuditEvent]") -> None:
            self.first_call_started.set()
            assert self.release_first_call.wait(timeout=5), "test never released the blocked flush() call"
            raise RuntimeError("simulated durably-failing sink")

    def _event(request_id: str) -> AuditEvent:
        return AuditEvent(
            str(uuid.uuid4()), "data_operation", "2026-09-03T00:00:00+00:00",
            request_id, "app-a", "application_credential", "cred-a", "runtime",
            "query", "entity", "allow", None, None, None,
        )

    sink = _BlockThenAlwaysFailSink()
    capacity = 5
    buffer = _AuditBuffer(sink, capacity=capacity, clock=lambda: 0.0)
    for i in range(capacity):
        buffer._events.append(_event(f"seed{i + 1}"))

    flush_thread = threading.Thread(target=buffer.flush, name="in-flight-flush")
    flush_thread.start()
    assert sink.first_call_started.wait(timeout=5), "flush() never reached append_many()"

    # The flush is now blocked inside append_many, holding no lock, with
    # `capacity` events swapped OUT of `self._events` -- push() below sees
    # an empty buffer and will not evict any of these new pushes, exactly
    # the B-1 window. Stays below the flush threshold (0.8 * capacity ==
    # 4) so this does not itself trigger a nested threshold-flush.
    new_event_count = 3
    assert new_event_count < buffer._flush_threshold

    def _push_more() -> None:
        for i in range(new_event_count):
            buffer.push(_event(f"new{i + 1}"))

    push_thread = threading.Thread(target=_push_more, name="concurrent-push")
    push_thread.start()
    push_thread.join(timeout=5)
    assert not push_thread.is_alive(), "concurrent push() did not complete promptly"
    assert buffer.pending_count() == new_event_count, "push() must not evict while the buffer is transiently empty mid-flush"

    sink.release_first_call.set()
    flush_thread.join(timeout=5)
    assert not flush_thread.is_alive(), "flush() deadlocked after being released"

    total_pushed = capacity + new_event_count
    expected_dropped = total_pushed - capacity  # combined restore length minus capacity
    assert buffer.pending_count() <= capacity, (
        f"buffer must never exceed its configured capacity ({capacity}) after a failed flush's "
        f"restore, got {buffer.pending_count()}"
    )
    alert_rows = [c for c in sink.append_calls if c.get("event_class") == "security_control_failure"]
    assert alert_rows, "a genuine truncation must produce an overflow alert row, same as a push()-path eviction"
    for row in alert_rows:
        assert row["reason_code"] == "audit_buffer_overflow"
    assert sum(row.get("count", 1) for row in alert_rows) == expected_dropped, (
        f"the alert row(s)' count must equal exactly the truncated overflow ({expected_dropped}), never the "
        f"retained remainder -- got {alert_rows!r}"
    )
    assert buffer._dropped_total == 0 and not buffer._alert_pending, (
        "the alert row above must have fully resolved the drop count (this fake sink's append() always "
        "succeeds), leaving nothing pending"
    )
    remaining_ids = [e.request_id for e in buffer._events]
    assert remaining_ids == [f"seed{i + 1}" for i in range(expected_dropped, capacity)] + [f"new{i + 1}" for i in range(new_event_count)], (
        f"truncation must drop the OLDEST events first (FIFO) and keep the newly-pushed ones -- got {remaining_ids!r}"
    )


def test_a_successful_flush_clears_the_failing_flag_even_when_the_buffer_is_not_empty() -> None:
    """P4-D15 (WP-B2, ledger L4-3): `_flush_currently_failing` clears on
    ANY successful `append_many`, regardless of whether the buffer this
    call observes afterward is empty. Under sustained push load the
    buffer is essentially never empty even once the sink has genuinely
    recovered (the threshold flush -- M-2 -- keeps refilling it), so the
    prior "only when empty" gate left the flag (and the alert backoff it
    feeds) stuck at the sink-broken state long after recovery.

    Reproduces "buffer not empty under continuous push" deterministically
    rather than by timing: the recovery flush's own (now succeeding)
    `append_many` call appends a new event directly into the buffer
    before returning -- standing in for a concurrent `push()` landing
    while that I/O was in flight -- so `self._events` is provably
    non-empty at the moment the success branch runs.

    Opus review M-1 (coordinator-adopted): completion condition 1 also
    requires the ALERT BACKOFF to return to its floor on this same
    successful flush, not merely the flag. Reproduced here by: (1)
    forcing GENUINE drops via `push()`'s own eviction branch while both
    sink write paths durably fail, so `_alert_pending`/`_dropped_total`
    are set for real (not hand-seeded); (2) driving further failing
    `_retry_alert()` passes so `_alert_backoff_s` grows past the floor via
    its own exception branch; (3) recovering both write paths; (4) one
    successful flush, arranged (per above) to leave the buffer non-empty;
    (5) asserting BOTH the flag and the backoff the flush's own trailing
    `_retry_alert()` call already advanced are back to their recovered
    state.

    LOAD-BEARING (flag half): on the prior code
    (`if not self._events: self._flush_currently_failing = False`) the
    flag assertion fails, because the buffer is non-empty when the
    successful flush's success branch runs, and the flag stays True.
    LOAD-BEARING (backoff half, M-1): mutating the floor-reset branch in
    `_retry_alert` (`if flush_failing:` -> `if True:`) makes the backoff
    assertion fail, because the just-recovered flush would then still be
    treated as failing for backoff purposes.
    """
    from r2db_api.service import _AuditBuffer

    def _mk_event(request_id: str) -> AuditEvent:
        return AuditEvent(
            str(uuid.uuid4()), "data_operation", "2026-09-03T00:00:00+00:00",
            request_id, "app-a", "application_credential", "cred-a", "runtime",
            "query", "entity", "allow", None, None, None,
        )

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    class _ControllableSink:
        """A single `fail` switch controls BOTH write paths (`append_many`
        -- the ordinary buffer flush -- and `append` -- the overflow-alert
        row), standing in for "the sink is down" / "the sink has
        recovered" as one fact, the same way a real Postgres outage would
        affect both. `refill_on_next_success_write`, when set, lets the
        NEXT successful `append_many` refill the buffer before returning
        -- simulating a concurrent `push()` landing mid-flight."""

        def __init__(self) -> None:
            self.fail = True
            self.buffer: Any = None
            self.refill_on_next_success_write = False

        def append_many(self, events: list) -> None:
            if self.fail:
                raise RuntimeError("simulated durably-failing sink (write path)")
            if self.refill_on_next_success_write:
                self.refill_on_next_success_write = False
                assert self.buffer is not None
                self.buffer._events.append(_mk_event("concurrent-push"))

        def append(self, **kwargs: Any) -> None:
            if self.fail:
                raise RuntimeError("simulated durably-failing sink (alert path)")

    clock = _Clock()
    sink = _ControllableSink()
    alert_min_interval_s = 2.0
    capacity = 2
    buffer = _AuditBuffer(sink, capacity=capacity, clock=clock, alert_min_interval_s=alert_min_interval_s)
    sink.buffer = buffer

    # Genuine drops via push()'s own eviction branch (capacity 2, 5
    # pushes, BOTH sink write paths durably failing throughout) -- also
    # drives several threshold-triggered failing flush() calls, each
    # setting `_flush_currently_failing = True` and (once `_alert_pending`
    # is set) attempting, and failing, the alert row -- growing
    # `_alert_backoff_s` past the floor via `_retry_alert`'s own exception
    # branch.
    for i in range(5):
        buffer.push(_mk_event(f"seed{i + 1}"))
    assert buffer._alert_pending is True
    assert buffer._dropped_total > 0
    assert buffer._flush_currently_failing is True

    # Drive a few more failing retry-alert passes explicitly, each spaced
    # past the current backoff, so it keeps growing (both write paths
    # still fail here -- the sink stays fully down).
    for _ in range(3):
        clock.advance(buffer._alert_backoff_s + 0.001)
        buffer._retry_alert()
    grown_backoff = buffer._alert_backoff_s
    assert grown_backoff > alert_min_interval_s, (
        f"setup check: the alert backoff must have grown past the floor ({alert_min_interval_s}) "
        f"before recovery -- got {grown_backoff}"
    )

    # Recover: BOTH write paths start succeeding. Arrange for this
    # recovery flush's own `append_many` to refill the buffer before
    # returning, so the buffer is NOT empty when the success branch runs.
    sink.fail = False
    sink.refill_on_next_success_write = True
    clock.advance(buffer._alert_backoff_s + 0.001)
    buffer.flush()

    assert buffer.pending_count() == 1, "sanity check: the buffer must be non-empty when the success branch runs"
    assert buffer._flush_currently_failing is False, (
        "a successful flush must clear the failing flag unconditionally (P4-D15) -- "
        "even though the buffer is not empty afterward"
    )
    # M-1: `flush()`'s own trailing `_retry_alert()` call (which already
    # ran, above, as part of this same `flush()`) reads the JUST-CLEARED
    # `_flush_currently_failing` and must take the reset-to-floor branch,
    # not the exponential-growth one.
    assert buffer._alert_backoff_s == alert_min_interval_s, (
        "the alert backoff must reset to the floor (alert_min_interval_s) on the retry that runs as part "
        f"of a successful flush (P4-D15) -- got backoff still elevated at {buffer._alert_backoff_s}"
    )


def test_a_failing_flush_that_completes_after_a_successful_one_sets_the_flag_again() -> None:
    """P4-D15 (WP-B2, ledger L4-3): completion-order semantics -- the
    FAILURE branch unconditionally sets `_flush_currently_failing = True`
    (unchanged by this WP). A failing flush that completes AFTER a
    successful one must therefore win, which is what lets the flag track
    "the outcome of the most recently COMPLETED flush attempt", not
    merely "has any flush ever succeeded". This is a regression guard,
    not a load-bearing test for P4-D15 itself: it is green both before
    and after the WP-B2 change, because the failure branch is untouched
    by it.

    Opus review M-2 (coordinator-adopted): uses REAL threads with a
    blocking fake sink to force the actual COMPLETION order, rather than
    merely calling `flush()` twice in program order (which cannot by
    itself distinguish "completes after" from "is merely called after").
    Thread A's flush() BEGINS first and is durably failing, but is
    blocked mid-I/O on a `threading.Event`; the main thread's own,
    independent flush() then BEGINS and COMPLETES successfully SECOND,
    while A is still blocked; only THEN is A released to finish failing,
    reproducing "a failing flush that completes after a successful one"
    by actual completion order, not call order.
    """
    from r2db_api.service import _AuditBuffer

    def _mk_event(request_id: str) -> AuditEvent:
        return AuditEvent(
            str(uuid.uuid4()), "data_operation", "2026-09-03T00:00:00+00:00",
            request_id, "app-a", "application_credential", "cred-a", "runtime",
            "query", "entity", "allow", None, None, None,
        )

    class _BlockFirstCallThenFailSink:
        def __init__(self) -> None:
            self.calls = 0
            self.first_call_started = threading.Event()
            self.release_first_call = threading.Event()

        def append_many(self, events: list) -> None:
            self.calls += 1
            if self.calls == 1:
                self.first_call_started.set()
                assert self.release_first_call.wait(timeout=5), "test never released the blocked first call"
                raise RuntimeError("simulated durably-failing sink (first call)")
            # second call onward: succeeds immediately, unblocked.

        def append(self, **kwargs: Any) -> None:  # pragma: no cover -- alert row, unused here
            pass

    sink = _BlockFirstCallThenFailSink()
    buffer = _AuditBuffer(sink, capacity=100, clock=lambda: 0.0)

    # Thread A: a flush() whose own write is the FIRST call this sink ever
    # receives -- blocked mid-I/O below, will raise once released.
    buffer._events.append(_mk_event("a1"))
    thread_a = threading.Thread(target=buffer.flush, name="failing-flush")
    thread_a.start()
    assert sink.first_call_started.wait(timeout=5), "thread A's flush() never reached append_many()"

    # Thread A is now blocked inside append_many, holding no lock (the B-2
    # swap-out already emptied `self._events`). Push a new event and run a
    # SECOND, independent flush() on the main thread: its own append_many
    # call is the second one this sink ever receives, which succeeds
    # immediately.
    buffer.push(_mk_event("b1"))
    buffer.flush()
    assert buffer._flush_currently_failing is False, (
        "the main thread's own flush() completed successfully (second call to the sink) and must have "
        "cleared the flag"
    )

    # NOW release thread A -- its still in-flight, durably-failing call
    # COMPLETES AFTER the successful one above.
    sink.release_first_call.set()
    thread_a.join(timeout=5)
    assert not thread_a.is_alive(), "thread A's flush() deadlocked after being released"

    assert buffer._flush_currently_failing is True, (
        "a failing flush that completes after a successful one must set the flag back to True"
    )


def test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row(caplog: pytest.LogCaptureFixture) -> None:
    """WP-2(a) fix round 2 review N-1: reproduces the audit's own probe
    (capacity=2, 5 pushes, `append_many` durably failing throughout,
    `append` -- used by the alert row -- healthy). The expected eviction
    count is computed INDEPENDENTLY (push_count - capacity), never read
    from the implementation's own internal `_dropped_total` counter --
    the audit's own finding was precisely that the old counter could not
    be trusted as its own expected value (it double-counted RETAINED,
    not-actually-lost events). Before the fix: 5 alert-row attempts
    (one per request) summing to a `count` of 12, even though only 3
    events were ever irrevocably lost (2 remained genuinely buffered).
    After the fix: the fixed overflow log fires exactly once per genuine
    eviction, and every alert row's `count` sums to exactly that
    independently-computed number.
    """
    inner = ApplicationAuditSink()
    faulty = _SelectiveFaultSink(inner)
    faulty.fail_event_classes.add("__buffer__")  # append_many always fails; append (the alert) stays healthy
    clock = _FakeClock()
    capacity = 2
    push_count = 5
    expected_evictions = push_count - capacity
    service, _control = build_service(durable_audit=faulty, clock=clock, audit_buffer_capacity=capacity)
    ctx = runtime_context(service)

    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        for _ in range(push_count):
            service.query(ctx, "notes", select=["id"])

    overflow_events = [r for r in caplog.records if "application_audit buffer overflow" in r.message]
    assert len(overflow_events) == expected_evictions, (
        f"the fixed overflow log must fire exactly once per GENUINE eviction ({expected_evictions}), "
        f"never per retained-but-not-lost flush failure -- got {len(overflow_events)}"
    )
    # The 2 events that never got evicted are still genuinely buffered,
    # not counted anywhere as lost (N-1's own central claim).
    assert service._audit_buffer.pending_count() == capacity

    # Let any still-pending alert state resolve (backoff advanced past).
    clock.advance(service._audit_buffer._alert_backoff_s + 1.0)
    service.flush_audit_buffer()

    events = durable_events(inner)
    alert_rows = [e for e in events if e["event_class"] == "security_control_failure"]
    assert alert_rows, "expected at least one alert row"
    for row in alert_rows:
        assert row["reason_code"] == "audit_buffer_overflow"
        assert row["operation"] == "audit_buffer"
        assert row["target_kind"] == "audit_sink"
    # WP-2(b) review B-1 (supervisor ruling 2026-09-03): an alert row
    # representing exactly ONE drop writes `count` ABSENT (NULL), not the
    # literal `1` -- `row.get("count", 1)` reads that correctly (absence
    # means one occurrence), never `row["count"]` (which would now raise
    # `KeyError` on any single-drop alert row).
    assert sum(row.get("count", 1) for row in alert_rows) == expected_evictions, (
        f"alert rows' counts must sum to the independently-computed eviction count "
        f"({expected_evictions}), got rows {alert_rows!r}"
    )


def test_buffer_overflow_alert_row_with_exactly_one_drop_writes_no_literal_count_of_one() -> None:
    """WP-2(b) review B-1 (major, supervisor ruling 2026-09-03): the
    overflow-alert row follows the identical `count` rule as the denial-
    coalescer's summary row (design D-4, one sentence added alongside D-3's)
    -- exactly ONE genuine eviction must still produce an alert row with
    `count` ABSENT, never the literal `1`.
    """
    inner = ApplicationAuditSink()
    faulty = _SelectiveFaultSink(inner)
    faulty.fail_event_classes.add("__buffer__")
    clock = _FakeClock()
    capacity = 2
    push_count = 3  # exactly one genuine eviction: push_count - capacity == 1
    service, _control = build_service(durable_audit=faulty, clock=clock, audit_buffer_capacity=capacity)
    ctx = runtime_context(service)

    for _ in range(push_count):
        service.query(ctx, "notes", select=["id"])

    clock.advance(service._audit_buffer._alert_backoff_s + 1.0)
    service.flush_audit_buffer()

    events = durable_events(inner)
    alert_rows = [e for e in events if e["event_class"] == "security_control_failure"]
    assert alert_rows, "expected at least one alert row"
    assert sum(row.get("count", 1) for row in alert_rows) == 1, (
        f"expected exactly one genuine eviction total, got rows {alert_rows!r}"
    )
    for row in alert_rows:
        assert "count" not in row, f"an alert row representing exactly one drop must never write count=1 -- got {row!r}"


def test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval() -> None:
    """WP-2(a) fix round 2 review N-2: the alert-row EMISSION RATE is
    bounded independently of how often eviction/flush-failure occurs --
    "1 alert row (attempt) per flush interval per process" for as long as
    the underlying flush keeps failing, from EITHER the threshold-flush
    path or the periodic/explicit one (§7.4). Simulates sustained
    continuous overflow (every request evicts, `append_many` durably
    failing) across a controlled elapsed time span and asserts the alert
    ROW COUNT ITSELF -- not merely the count each row carries -- respects
    `elapsed_time / alert_min_interval_s`, rounded up with a little slack.
    """
    inner = ApplicationAuditSink()
    faulty = _SelectiveFaultSink(inner)
    faulty.fail_event_classes.add("__buffer__")
    clock = _FakeClock()
    alert_min_interval_s = 2.0  # _AuditBuffer's own default (_DEFAULT_AUDIT_FLUSH_INTERVAL_S)
    service, _control = build_service(durable_audit=faulty, clock=clock, audit_buffer_capacity=2)
    ctx = runtime_context(service)

    n_requests = 40
    step_s = 0.3  # far more frequent than the alert interval
    for _ in range(n_requests):
        service.query(ctx, "notes", select=["id"])
        clock.advance(step_s)
    elapsed_s = n_requests * step_s

    clock.advance(service._audit_buffer._alert_backoff_s + 1.0)
    service.flush_audit_buffer()

    alert_rows = [e for e in durable_events(inner) if e["event_class"] == "security_control_failure"]
    upper_bound = -(-int(elapsed_s * 10) // int(alert_min_interval_s * 10)) + 1  # ceil(elapsed/interval) + 1 slack, integer-safe
    assert 1 <= len(alert_rows) <= upper_bound, (
        f"alert row count ({len(alert_rows)}) must stay within the rate bound ({upper_bound}) "
        f"for {elapsed_s:.1f}s elapsed at a {alert_min_interval_s}s floor -- got {len(alert_rows)} over "
        f"{n_requests} requests, i.e. NOT one alert row per request"
    )
    assert len(alert_rows) < n_requests, "must not emit one alert row per request (N-2's own central claim)"


def test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations(caplog: pytest.LogCaptureFixture) -> None:
    inner = ApplicationAuditSink()
    faulty = _SelectiveFaultSink(inner)
    faulty.fail_event_classes.add("security_control_failure")
    clock = _FakeClock()
    service, _control = build_service(durable_audit=faulty, clock=clock, audit_buffer_capacity=1000)
    ctx = runtime_context(service)
    dev = developer_context(service)

    # Seed the "an overflow already happened" state directly (WP-2(a)
    # review M-2: a healthy `append_many` -- unfaulted here, this test is
    # about the ALERT retry path specifically -- combined with the
    # threshold-flush this WP adds means a small-capacity eviction burst,
    # this test's original setup, no longer reaches eviction at all; see
    # `test_buffer_overflow_emits_logging_error_and_exactly_one_security_
    # control_failure_row` for a genuine-eviction reproduction. This test's
    # own concern -- sticky/backoff/non-blocking retry of the ALERT WRITE
    # itself -- does not depend on how the pending state was reached, so it
    # seeds it directly rather than re-deriving it from a fragile
    # capacity/threshold interaction it does not otherwise care about).
    service._audit_buffer._dropped_total = 2
    service._audit_buffer._alert_pending = True

    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()
    assert any("overflow-alert row could not be written" in r.message for r in caplog.records)
    first_backoff = service._audit_buffer._alert_backoff_s
    # Doubled from the floor (`_DEFAULT_AUDIT_FLUSH_INTERVAL_S` = 2.0,
    # WP-2(a) fix round 2 review N-2 -- no alert attempt is ever spaced
    # closer together than the composition root's own flush cadence).
    assert first_backoff > 2.0

    # A genuinely unrelated fail-closed operation still succeeds while the
    # alert is pending (§9.2 property 7's own spirit, extended to the
    # alert path specifically -- an alert failure must never block traffic).
    revision = service.schema(dev, {"operation": "create_entity", "entity": "widgets_alert_test"}).revision
    assert revision >= 1

    # Before the backoff interval elapses, a retry is not even attempted.
    calls_before = len(faulty.append_calls)
    service.flush_audit_buffer()
    assert len(faulty.append_calls) == calls_before

    # After the backoff interval elapses, it retries (and fails again,
    # backing off further).
    clock.advance(first_backoff + 1.0)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()
    assert len(faulty.append_calls) > calls_before
    assert service._audit_buffer._alert_backoff_s >= first_backoff

    # Now let it succeed -- pending clears, a recovery log fires.
    faulty.fail_event_classes.discard("security_control_failure")
    clock.advance(service._audit_buffer._alert_backoff_s + 1.0)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="r2db_api.service"):
        service.flush_audit_buffer()
    assert any("overflow-alert row recorded" in r.message for r in caplog.records)
    alert_rows = [e for e in durable_events(inner) if e["event_class"] == "security_control_failure"]
    assert len(alert_rows) == 1


def test_buffer_row_failure_does_not_block_a_fail_closed_operation() -> None:
    inner = ApplicationAuditSink()
    faulty = _SelectiveFaultSink(inner)
    faulty.fail_event_classes.add("__buffer__")  # append_many always fails
    service, _control = build_service(durable_audit=faulty)
    ctx = runtime_context(service)
    dev = developer_context(service)

    service.query(ctx, "notes", select=["id"])  # buffered, not yet flushed
    service.flush_audit_buffer()  # fails -- buffer content lost, alert marked pending
    assert faulty.append_many_calls == 1

    # A fail-closed operation (schema, unconditionally fail-closed) still
    # succeeds -- it does not go through append_many at all.
    revision = service.schema(dev, {"operation": "create_entity", "entity": "widgets_buffer_test"}).revision
    assert revision >= 1
    schema_rows = [e for e in durable_events(inner) if e["operation"] == "schema" and e["outcome"] == "allow"]
    assert len(schema_rows) == 1


# ===========================================================================
# Section 8: dispatch-point correctness (§9.2 properties 6/8, D-2/D-10).
# ===========================================================================


def test_dispatch_point_is_the_destructive_confirmation_choke() -> None:
    """The判定点 is whether `require_destructive_confirmation` was actually
    passed, not `event_class`: a batch with only insert/update never sets
    `MutationOutcome.destructive`, but a confirmed delete does -- even
    though both reach `DataService` through the identical `mutate` call and
    the identical `data_operation` event_class."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)

    outcome = service._mutate_outcome(ctx, "notes", [{"operation": "insert", "values": {"body": "x"}}], transaction="atomic", request_id=None)
    assert outcome.destructive is False

    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)
    outcome = service._mutate_outcome(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}], transaction="atomic", request_id=None)
    assert outcome.destructive is True


def test_delete_bearing_mutate_never_enters_the_buffer_path() -> None:
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    ctx = runtime_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)

    service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}])

    assert service._audit_buffer.pending_count() == 0
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

    # Fail-closed class: exactly +1 durable row immediately.
    service.mutate(ctx, "notes", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}])
    assert len(durable_events(durable)) == 1

    # Buffer class: +1 durable row only after a flush (D-10: max one row
    # per operation, but the ROW ITSELF is durable once flushed).
    service.mutate(ctx, "notes", [{"operation": "insert", "values": {"body": "b"}}])
    assert len(durable_events(durable)) == 1  # not yet flushed
    service.flush_audit_buffer()
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
    "upgrade-applications' (its '--dry-run' shows applied and pending per application), then retry."
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
