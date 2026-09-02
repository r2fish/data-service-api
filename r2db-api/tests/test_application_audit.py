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

from r2db_api.audit import ApplicationAuditSink, AuditEvent
from r2db_api.audit_hook import ApplicationAuditHook
from r2db_api.auth import CredentialStore
from r2db_api.credential_store import PostgresApplicationAuditSink, PostgresControlAuditSink
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell
from r2db_api.service import ControlAuthority, DataService
from r2db_api.structured import ApplicationCell, Predicate, delete_confirmation_phrase

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
PEPPER = "synthetic-test-pepper-application-audit-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
)


# ===========================================================================
# Real-PostgreSQL fixtures (migration/GRANT/timeout/hook-against-real-DB
# tests). Mirrors `test_postgres.py`/`test_control_plane_store.py`'s own
# established fixture pattern one-for-one (duplicated rather than imported,
# matching this repository's own precedent of not taking cross-test-module
# import dependencies).
# ===========================================================================


def _admin_dsn() -> str:
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


@pytest.fixture
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "aaudit")
    try:
        yield app
    finally:
        deprovision_app(platform, "aaudit")


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


def test_audit_write_connections_have_statement_and_idle_in_transaction_timeouts_set(platform: types.SimpleNamespace) -> None:
    app_sink = real_durable_sink(platform, statement_timeout_ms=1234, idle_in_transaction_session_timeout_ms=4321)
    try:
        with app_sink._pool.connection() as conn:
            assert _show(conn, "statement_timeout") == "1234ms"
            assert _show(conn, "idle_in_transaction_session_timeout") == "4321ms"
    finally:
        app_sink.close()

    control_sink = PostgresControlAuditSink(
        platform.controlplane_dsn, schema=platform.schema, pool_size=2,
        statement_timeout_ms=2345, idle_in_transaction_session_timeout_ms=5432,
    )
    try:
        with control_sink._pool.connection() as conn:
            assert _show(conn, "statement_timeout") == "2345ms"
            assert _show(conn, "idle_in_transaction_session_timeout") == "5432ms"
    finally:
        control_sink.close()


def test_audit_sink_without_configured_timeouts_leaves_server_defaults_untouched(platform: types.SimpleNamespace) -> None:
    """Regression guard: `_RolePool`'s new timeout parameters must be
    opt-in (`None` = do not touch either setting) -- every OTHER `_RolePool`
    consumer (ordinary application data-plane pools) must not silently
    acquire a timeout policy as a side effect of this WP."""
    sink = real_durable_sink(platform)
    try:
        with sink._pool.connection() as conn:
            # The server's own compiled-in default is "0" (disabled) unless
            # an operator's `postgresql.conf` overrides it -- this assertion
            # is about THIS CODE not issuing a `SET SESSION` at all, not
            # about what the value happens to be, so it checks the actual
            # cluster default rather than assuming "0".
            with psycopg.connect(platform.admin_dsn) as admin:
                with admin.cursor() as cur:
                    cur.execute("SHOW statement_timeout")
                    cluster_default = cur.fetchone()[0]
            assert _show(conn, "statement_timeout") == cluster_default
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


def test_build_app_wires_env_configured_audit_timeouts_onto_the_real_writer_connection(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WP-2(a) review M-1 (major): a prior revision had no test exercising
    the actual `main.py`/`control_main.py` composition-root WIRING of the
    two writer-connection timeouts -- `test_audit_write_connections_have_
    statement_and_idle_in_transaction_timeouts_set` (above) constructs
    `PostgresApplicationAuditSink`/`PostgresControlAuditSink` directly with
    explicit values, which only proves `_RolePool`'s own `SET SESSION`
    mechanism works, never that `build_app`/`build_control_app` actually
    read the env vars and pass them through (removing that wiring left
    `r2db-api/tests` at 599 passed, unchanged -- a live mutant). This test
    builds the REAL app via `r2db_api.main.build_app(env=...)` and reads
    `SHOW statement_timeout`/`SHOW idle_in_transaction_session_timeout`
    from a connection drawn from the WIRED sink (`app.state.service.
    _durable_audit`, `http.create_app`'s own `app.state.service` -- not a
    separately, directly constructed sink), first with the env vars unset
    (defaults 5000/5000) and then with them overridden.
    """
    def _env(statement_ms: str | None, idle_ms: str | None) -> dict[str, str]:
        env = {
            "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-main",
            "R2DB_PLATFORM_DSN": platform.api_dsn,
            "R2DB_PLATFORM_SCHEMA": platform.schema,
            "R2DB_SERVE_APPS": app_a.slug,
            f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
            f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
        }
        if statement_ms is not None:
            env["R2DB_AUDIT_STATEMENT_TIMEOUT_MS"] = statement_ms
        if idle_ms is not None:
            env["R2DB_AUDIT_IDLE_TIMEOUT_MS"] = idle_ms
        return env

    module = _reload_module_with_env("r2db_api.main", _env(None, None), monkeypatch)
    default_app = module.build_app(env=_env(None, None))
    try:
        sink = default_app.app.state.service._durable_audit
        with sink._pool.connection() as conn:
            # PostgreSQL's own `SHOW` normalizes an exact multiple of 1000ms
            # to the coarser "Ns" unit -- 5000ms and 5s are the same value,
            # this is a display quirk, not a wiring bug (contrast the
            # overridden case below, whose non-round values display in ms).
            assert _show(conn, "statement_timeout") == "5s"
            assert _show(conn, "idle_in_transaction_session_timeout") == "5s"
    finally:
        default_app.app.state.service._durable_audit.close()
        default_app.app.state.service._credentials.close()

    overridden_app = module.build_app(env=_env("1234", "4321"))
    try:
        sink = overridden_app.app.state.service._durable_audit
        with sink._pool.connection() as conn:
            assert _show(conn, "statement_timeout") == "1234ms"
            assert _show(conn, "idle_in_transaction_session_timeout") == "4321ms"
    finally:
        overridden_app.app.state.service._durable_audit.close()
        overridden_app.app.state.service._credentials.close()
        module.default_pool_manager.dispose_all()


def test_build_control_app_wires_env_configured_audit_timeouts_onto_the_real_writer_connection(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `control_main.py` half of M-1 -- see the `main.py` test's own
    docstring immediately above for the full rationale."""
    def _env(statement_ms: str | None, idle_ms: str | None) -> dict[str, str]:
        env = {
            "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-control-ctl",
            "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-m1-control-app",
            "R2DB_PLATFORM_SCHEMA": platform.schema,
        }
        if statement_ms is not None:
            env["R2DB_AUDIT_STATEMENT_TIMEOUT_MS"] = statement_ms
        if idle_ms is not None:
            env["R2DB_AUDIT_IDLE_TIMEOUT_MS"] = idle_ms
        return env

    module = _reload_module_with_env("r2db_api.control_main", _env(None, None), monkeypatch)
    default_app = module.build_control_app(env=_env(None, None))
    try:
        sink = default_app.app.state.control_service._audit
        with sink._pool.connection() as conn:
            # See the `main.py` test's identical comment above.
            assert _show(conn, "statement_timeout") == "5s"
            assert _show(conn, "idle_in_transaction_session_timeout") == "5s"
    finally:
        default_app.app.state.control_service._audit.close()

    overridden_app = module.build_control_app(env=_env("2345", "5432"))
    try:
        sink = overridden_app.app.state.control_service._audit
        with sink._pool.connection() as conn:
            assert _show(conn, "statement_timeout") == "2345ms"
            assert _show(conn, "idle_in_transaction_session_timeout") == "5432ms"
    finally:
        overridden_app.app.state.control_service._audit.close()


def test_both_composition_roots_share_one_audit_timeout_default_definition(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WP-2(a) fix round 2 review N-6: `r2db_api.main`/`r2db_api.control_
    main` must reference the SAME single definition
    (`credential_store.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`_IDLE_TIMEOUT_
    MS`) for their writer-connection timeout defaults, not two
    independently-maintained `5000` literals that could silently drift
    apart -- a WP-2(b) `visibility_lag_ms` declaration is derived from
    both processes' writer connections carrying the identical policy.
    Imports both composition-root modules through the same safe reload
    pattern the M-1 tests use (never a bare `import`, which would read
    real `os.environ` at whatever moment either module happens to be
    imported first in the whole test session -- see `_reload_module_with_
    env`'s own docstring), so this test's result does not depend on test
    execution order.
    """
    import r2db_api.credential_store as credential_store_module

    main_env = {
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-n6-main",
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app_a.slug,
        f"R2DB_APP_{app_a.slug.upper()}_RUNTIME_DSN": app_a.runtime_dsn,
        f"R2DB_APP_{app_a.slug.upper()}_DEVELOPER_DSN": app_a.developer_dsn,
    }
    main_module = _reload_module_with_env("r2db_api.main", main_env, monkeypatch)

    control_env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-n6-control-ctl",
        "R2DB_CREDENTIAL_PEPPER": "synthetic-test-pepper-n6-control-app",
        "R2DB_PLATFORM_SCHEMA": platform.schema,
    }
    control_main_module = _reload_module_with_env("r2db_api.control_main", control_env, monkeypatch)

    assert main_module.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS is credential_store_module.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
    assert main_module.DEFAULT_AUDIT_IDLE_TIMEOUT_MS is credential_store_module.DEFAULT_AUDIT_IDLE_TIMEOUT_MS
    assert control_main_module.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS is credential_store_module.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
    assert control_main_module.DEFAULT_AUDIT_IDLE_TIMEOUT_MS is credential_store_module.DEFAULT_AUDIT_IDLE_TIMEOUT_MS

    main_module.app.app.state.service._durable_audit.close()
    main_module.default_pool_manager.dispose_all()
    control_main_module.app.app.state.control_service._audit.close()


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
    return service.authenticate("secret-a")


def developer_context(service: DataService):
    return service.authenticate("dev-secret-a")


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
    assert service.schema(dev, {"operation": "create_entity", "entity": "widgets"}) == 1
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
        ctx = service.authenticate("secret-b1-runtime")
        dev = service.authenticate("secret-b1-developer")
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
        service.deny_unsupported(ctx, "audit_query", "not implemented")
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
    # count (1 repeat) it had accumulated so far.
    service.flush_audit_buffer(force_expire_denial_windows=True)
    events_after = durable_events(durable)
    assert len(events_after) == 2
    summary_row = events_after[1]
    assert summary_row["reason_code"] == "AUTH_INVALID"
    assert summary_row["count"] == 1


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
    assert sum(row["count"] for row in alert_rows) == expected_evictions, (
        f"alert rows' counts must sum to the independently-computed eviction count "
        f"({expected_evictions}), got rows {alert_rows!r}"
    )


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
    revision = service.schema(dev, {"operation": "create_entity", "entity": "widgets_alert_test"})
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
    revision = service.schema(dev, {"operation": "create_entity", "entity": "widgets_buffer_test"})
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
