"""Phase 4 WP-3(a): the durable application-plane audit sink -- migration
`0005_application_audit.sql`, the 13-column (+`count`) emitter pair
(`application_audit.ApplicationAuditSink`/`PostgresApplicationAuditSink`),
the pre-commit hook (`audit_hook.py`, wired through `backend_postgres.py`/
`backend_sqlite.py`/`cell.py`), the dispatch rules in `audit_dispatch.py`
(fail-closed vs. coalesced-denial vs. buffer vs. non-durable, wired through
`cell.py`/`auth.py`/`credential_store_postgres.py`), the bounded buffer +
overflow alert, and the two writer-connection timeouts -- tested against
real PostgreSQL (design R-8: must not be skipped) and, where real-
PostgreSQL realism is not the point of the test, against the pure
in-memory dispatch machinery (`audit_dispatch.AuditRouter` +
`application_audit.ApplicationAuditSink`), which lets the dispatch/buffer/
coalescing logic itself be exercised deterministically (an injected fake
clock, no network) without diluting what each test is actually checking.

Design this file is written against: docs/design/
PHASE4_DURABLE_AUDIT_SINK_V1.md (D-1 through D-10, §6.2, §7, §9.2) and
docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-3(a).

WP-3(a) scope only: `audit_query`, `control_capabilities` declarations,
`contract_version`, and the `audit_requests_per_minute` window are WP-3(b)
territory and are not exercised here.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import subprocess
import threading
import time
import types
import uuid
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mitatedb_api.application_audit import (APPLICATION_AUDIT_FIELDS,
                                            DECLARED_AUDIT_EVENT_CLASSES,
                                            DEFAULT_AUDIT_IDLE_TIMEOUT_MS,
                                            DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
                                            ApplicationAuditEvent,
                                            ApplicationAuditSink,
                                            PostgresApplicationAuditSink,
                                            coalesced_count)
from mitatedb_api.audit_dispatch import DURABLE_DENIAL_CODES, AuditRouter
from mitatedb_api.auth import CredentialStore, Principal, Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import (ApplicationCell, ApplicationDeveloper,
                               ApplicationRuntime, Filter, _delete_confirmation_phrase)
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import (AuditSinkUnavailable, AuthenticationError,
                                 AuthorizationError, DestructiveConfirmationRequired,
                                 FoundationError)
from mitatedb_api.pg_timeouts import ms_from_pg_timeout_text

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

_APP_PEPPER = "application-audit-postgres-app-pepper-x"
# Phase 6 WP-3 (design D-2): `MITATEDB_DATA_BASE_URL`/`_CONTROL_BASE_URL`
# are required unconditionally/conditionally from here on -- see
# `config.FoundationConfig.from_env`/`control_composition.
# build_control_service`.
_DATA_BASE_URL = "http://mitatedb-app-audit-test.example.invalid/v1"
_CONTROL_BASE_URL = "http://mitatedb-app-audit-test.example.invalid/control/v1"

MIGRATION_NAMES = (
    "0001_bootstrap_platform.sql",
    "0002_registry_and_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_application_audit.sql",
    # Phase 10 WP-4g (supervisor ruling 2026-09-09): `mitatedb_api.main.
    # build_app`/`mitatedb_api.control_composition.build_control_service`
    # now run F-16 (this process' own role CONNECTION LIMIT)
    # unconditionally at startup -- applied in the fixture right after
    # 0002 (before 0005), same reasoning as 0007 immediately below: it
    # only `ALTER`s 0002's own two roles (no GRANT statements of its own),
    # so running it before `grant_snapshot_before_0005` is captured does
    # not affect that snapshot comparison's own meaning.
    "0012_role_connection_limits.sql",
    # Q4 phase (design D-1/D-2, work order §4 WP-2): platform declarations
    # table + the two service writer roles' timeout role settings. Applied
    # in the fixture right after 0002 (before 0005) -- it only depends on
    # 0002's two roles, and running it before `grant_snapshot_before_0005`
    # is captured keeps `test_migration_0005_applies_after_0004_and_
    # changes_no_existing_grant`'s own "0005's new grants name only the
    # new table" assertion meaningful (0007's own new GRANTs land in the
    # BASELINE snapshot, not in "what 0005 added").
    "0007_platform_declarations.sql",
    # Phase 10 WP-6b (design D-5 (ii)): widens `platform_declarations.
    # key`'s own CHECK constraint to accept `process_ceilings` -- no
    # GRANT statements of its own, so it does not affect the `0005`
    # GRANT-invariance snapshot comparison below either way. Every test
    # here that touches `platform_declarations` (directly, or via
    # `main.build_app`/`build_control_service`) now depends on this
    # migration + the row seeded below, or fails startup with F-15.
    "0011_process_ceilings.sql",
)


# ===========================================================================
# Real-PostgreSQL fixtures (migration/GRANT/timeout/hook-against-real-DB
# tests). Mirrors `tests/test_postgres.py`'s own established fixture
# pattern (duplicated rather than imported -- this repository's own
# precedent of not taking cross-test-module import dependencies).
# ===========================================================================


# Q4 phase WP-0 (design D-1 (b)(ii), work order §4 WP-0 完了条件 2): the
# ms-normalization helper this file used to define locally
# (`_ms_from_pg_timeout_text`) is now `mitatedb_api.pg_timeouts.
# ms_from_pg_timeout_text` (imported above) -- promoted to `src` so Q4
# WP-2's own startup double-check can share it. No local copy remains.


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
            "tests must not be skipped (design R-8).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
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


def _grant_snapshot(dsn: str) -> set[tuple]:
    """A comparable snapshot of every GRANT on every object this migration
    set could conceivably touch, keyed by (grantee, table, privilege) --
    used to prove `0005_application_audit.sql` changes NONE of them
    (WP-2(a) review 8's own lesson: a GRANT-invariance test taken AFTER
    0005 has already applied is vacuously green; this snapshot must be
    taken BEFORE 0005 runs, and compared against the identical query
    taken after)."""
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT grantee, table_schema || '.' || table_name, privilege_type "
                "FROM information_schema.role_table_grants "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY 1, 2, 3"
            )
            return set(cur.fetchall())
    finally:
        conn.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """Bootstraps `0001` through `0005` under one throwaway prefix -- the
    full set, not only `0005`, because `0005`'s own compatibility argument
    (its header) is "applies cleanly after 0002 on an already-provisioned
    instance, changing no existing GRANT", which can only be exercised by
    actually applying 0001/0002 first, for real, every module run.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbaud{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    auditreader_role = f"{prefix}svc_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_appaudit_migrations")
    rewritten: dict[str, Path] = {}
    for name in MIGRATION_NAMES:
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)

    grant_snapshot_before_0005 = None
    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
        finally:
            admin.close()
        _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
        _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
        surfaces_conn = psycopg.connect(provision_dsn, autocommit=True)
        try:
            with surfaces_conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', %s)").format(
                        table=sql.Identifier(schema, "platform_declarations")),
                    [
                        '{"data":{"base_url":"' + _DATA_BASE_URL + '"},'
                        '"control":{"base_url":"' + _CONTROL_BASE_URL + '"}}'
                    ],
                )
                # Phase 10 WP-6b (design D-5 (ii)): seeded alongside
                # `surfaces` -- `main.build_app`/`build_control_service`
                # both now require this row too (F-15).
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('process_ceilings', %s)").format(
                        table=sql.Identifier(schema, "platform_declarations")),
                    ['{"data": 1, "control": 1}'],
                )
        finally:
            surfaces_conn.close()
        grant_snapshot_before_0005 = _grant_snapshot(provision_dsn)
        _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(auditreader_role), sql.Literal(auditreader_password)))
        finally:
            admin.close()
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        provision_role=provision_role,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        api_role=api_role,
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        controlplane_role=controlplane_role,
        auditreader_dsn=_dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db),
        auditreader_role=auditreader_role,
        platform_db=platform_db,
        schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        application_audit_sql=rewritten["0005_application_audit.sql"],
        grant_snapshot_before_0005=grant_snapshot_before_0005,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform: types.SimpleNamespace, app_id: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.provision_dsn, platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{app_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return types.SimpleNamespace(
        app_id=app_id, database=database, runtime_role=runtime_role, developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def deprovision_app(platform: types.SimpleNamespace, app_id: str) -> None:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


@pytest.fixture
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "aaudit")
    try:
        yield app
    finally:
        deprovision_app(platform, "aaudit")


@pytest.fixture(scope="module")
def timeout_probe_app(platform: types.SimpleNamespace) -> types.SimpleNamespace:
    """Review M-1 (major, supervisor ruling 2026-09-03): a dedicated,
    NEVER-deprovisioned application -- mirrors `test_main.py::probe_app`'s
    own established precedent one-for-one, for the identical reason: a
    real `main.build_app(...)`/`control_composition.build_control_service(
    ...)` call holds persistent connections nothing in this file's own
    lifespan drives closed, so reusing `app_a` (torn down after every
    single test) would leave `deprovision_app` failing against a database
    still "accessed by other users". `platform`'s own module-scoped
    `_sweep_prefix` teardown removes it regardless."""
    return provision_app(platform, "timeoutprobe")


def make_backend(app: types.SimpleNamespace) -> PostgresBackend:
    return PostgresBackend(app.runtime_dsn, app.developer_dsn)


def make_router(sink: Any = None, **kwargs: Any) -> AuditRouter:
    return AuditRouter(sink if sink is not None else ApplicationAuditSink(), **kwargs)


def make_developer(cell: ApplicationCell, application_id: str, credential_id: str = "devone") -> ApplicationDeveloper:
    principal = Principal(application_id=application_id, credential_id=credential_id, role=Role.DEVELOPER)
    return ApplicationDeveloper(cell, principal)


def make_runtime(cell: ApplicationCell, application_id: str, credential_id: str = "rtone") -> ApplicationRuntime:
    principal = Principal(application_id=application_id, credential_id=credential_id, role=Role.RUNTIME)
    return ApplicationRuntime(cell, principal)


def clean_application_audit(platform: types.SimpleNamespace) -> None:
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(platform.schema, "application_audit")))
    finally:
        conn.close()


# ===========================================================================
# Migration / GRANT tests (real PostgreSQL, module `platform` fixture)
# ===========================================================================


def test_migration_0005_applies_after_0004_and_changes_no_existing_grant(platform: types.SimpleNamespace) -> None:
    after = _grant_snapshot(platform.provision_dsn)
    assert platform.grant_snapshot_before_0005 is not None
    # Every grant that existed BEFORE 0005 ran must still be present
    # afterward (0005 never REVOKEs/narrows anything 0001/0002 granted).
    assert platform.grant_snapshot_before_0005 <= after
    # And every NEW grant 0005 adds must name only the new table/role,
    # never touching `applications`/`credentials`/`control_credentials`/
    # `control_audit` for a role that did not already have that exact
    # grant before.
    new_grants = after - platform.grant_snapshot_before_0005
    for grantee, table, _privilege in new_grants:
        # Every new grant names either the new table, or (D-5(b): a THIRD
        # grantee's SELECT alongside the two existing ones) the new
        # `mitatedbsvc_auditreader` role's own SELECT on the pre-existing
        # `control_audit` table -- never any other existing table, and
        # never any other role gaining anything on `control_audit`.
        if table.endswith(".application_audit"):
            continue
        assert table.endswith(".control_audit") and grantee == platform.auditreader_role, (grantee, table)


def test_migration_0005_reapplication_is_idempotent(platform: types.SimpleNamespace) -> None:
    before = _grant_snapshot(platform.provision_dsn)
    _run_psql(platform.provision_dsn, platform.application_audit_sql)
    after = _grant_snapshot(platform.provision_dsn)
    assert before == after


def test_new_auditreader_role_has_no_memberships(platform: types.SimpleNamespace) -> None:
    conn = psycopg.connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON m.member = r.oid WHERE r.rolname = %s", [platform.auditreader_role])
            (count,) = cur.fetchone()
            assert count == 0
            cur.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin FROM pg_roles WHERE rolname = %s",
                [platform.auditreader_role],
            )
            rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin = cur.fetchone()
            assert (rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin) == (False, False, False, False, True)
    finally:
        conn.close()


def test_api_role_cannot_select_update_or_delete_application_audit(platform: types.SimpleNamespace) -> None:
    conn = psycopg.connect(platform.api_dsn)
    try:
        table = sql.Identifier(platform.schema, "application_audit")
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(table))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("UPDATE {} SET outcome = 'x'").format(table))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("DELETE FROM {}").format(table))
        conn.rollback()
    finally:
        conn.close()


def test_api_role_can_insert_but_not_read_it_back(platform: types.SimpleNamespace) -> None:
    sink = PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema)
    sink.append(
        event_class="schema_change", request_id="r1", application_id="a", actor_type="application_credential",
        actor_id="c1", role="developer", operation="create_collection", target_kind="collection",
        outcome="allow", reason_code=None, target_id="t",
    )
    with pytest.raises(psycopg.Error):
        sink.events()
    clean_application_audit(platform)


def test_api_role_cannot_insert_a_value_longer_than_the_length_check(platform: types.SimpleNamespace) -> None:
    sink = PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema)
    with pytest.raises(psycopg.Error):
        sink.append(
            event_class="x" * 100, request_id="r1", application_id="a", actor_type="application_credential",
            actor_id="c1", role="developer", operation="create_collection", target_kind="collection",
            outcome="allow", reason_code=None, target_id="t",
        )
    clean_application_audit(platform)


def test_controlplane_role_has_no_privilege_on_application_audit(platform: types.SimpleNamespace) -> None:
    conn = psycopg.connect(platform.controlplane_dsn)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(platform.schema, "application_audit")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("INSERT INTO {} (event_id, event_class, occurred_at, operation, outcome) VALUES ('x', 'y', now(), 'z', 'allow')").format(
                    sql.Identifier(platform.schema, "application_audit")))
    finally:
        conn.close()


def test_auditreader_role_can_select_both_audit_tables_and_nothing_else(platform: types.SimpleNamespace) -> None:
    conn = psycopg.connect(platform.auditreader_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(platform.schema, "application_audit")))
            cur.fetchall()
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(platform.schema, "control_audit")))
            cur.fetchall()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("INSERT INTO {} (event_id, event_class, occurred_at, operation, outcome) VALUES ('x', 'y', now(), 'z', 'allow')").format(
                    sql.Identifier(platform.schema, "application_audit")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(platform.schema, "applications")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(platform.schema, "credentials")))
    finally:
        conn.close()


# ===========================================================================
# Writer-connection timeouts (Q4 phase, design D-1(b) -- SUPERSEDES Phase 4
# D-6/N-3's per-connection `SET SESSION`, both composition roots)
#
# `PostgresApplicationAuditSink`/`PostgresControlBackend` no longer accept
# `statement_timeout_ms=`/`idle_in_transaction_session_timeout_ms=`
# constructor arguments at all -- the SET-SESSION mechanism they configured
# is REMOVED product code (D-1(b): "書き手プロセスは接続時のセッションSET
# をやめ"). The three tests this section used to hold (constructing a sink
# directly with explicit timeout kwargs; asserting "no configuration
# leaves the server default"; calling the now-deleted `_apply_session_
# timeouts` directly against a raw control-plane connection) each tested
# behavior that no longer exists. Replaced below with the Q4 mechanism:
# `ALTER ROLE ... SET` (the SAME shape migration `0007`/`ops set-platform-
# timeouts` use) on the role itself, observed via each writer's own real
# connection.
# ===========================================================================


def _set_role_timeouts(admin_dsn: str, role: str, *, statement_ms: int, idle_ms: int) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                sql.Identifier(role), sql.Literal(f"{statement_ms}ms")))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = {}").format(
                sql.Identifier(role), sql.Literal(f"{idle_ms}ms")))
    finally:
        admin.close()


def test_application_audit_writer_connection_reflects_the_api_roles_own_setting(platform: types.SimpleNamespace) -> None:
    """Q4 phase (design D-1(a)/(b)): `platform`'s own `0007` migration
    already set `mitatedbsvc_api` to the shipped 5000ms/5000ms default --
    this overrides it to a distinguishable value via the SAME `ALTER
    ROLE ... SET` mechanism `ops set-platform-timeouts` uses, then proves
    the sink's own real connection (which no longer accepts ANY
    timeout-related constructor argument) reflects it automatically,
    login-time, with no client-side action."""
    _set_role_timeouts(platform.admin_dsn, platform.api_role, statement_ms=1234, idle_ms=5678)
    try:
        sink = PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema)
        conn = sink._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW statement_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 1234
                cur.execute("SHOW idle_in_transaction_session_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 5678
        finally:
            conn.close()
    finally:
        _set_role_timeouts(platform.admin_dsn, platform.api_role, statement_ms=5000, idle_ms=5000)


def test_control_audit_writer_connection_reflects_the_controlplane_roles_own_setting(platform: types.SimpleNamespace) -> None:
    """Same mechanism, the OTHER writer role -- `mitatedbsvc_controlplane`,
    the role `PostgresControlBackend.unit_of_work`'s own connection logs
    in as."""
    _set_role_timeouts(platform.admin_dsn, platform.controlplane_role, statement_ms=2345, idle_ms=6789)
    try:
        conn = psycopg.connect(platform.controlplane_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW statement_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 2345
                cur.execute("SHOW idle_in_transaction_session_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 6789
        finally:
            conn.close()
    finally:
        _set_role_timeouts(platform.admin_dsn, platform.controlplane_role, statement_ms=5000, idle_ms=5000)


def test_application_audit_sink_no_longer_accepts_a_timeout_constructor_argument() -> None:
    """Non-vacuity companion / regression guard: `PostgresApplicationAudit
    Sink`'s constructor genuinely dropped the two Phase-4 parameters --
    passing either now raises `TypeError`, rather than silently accepting
    and ignoring them (which would be a worse, silent-degradation form of
    the SAME bug this WP exists to close)."""
    with pytest.raises(TypeError):
        PostgresApplicationAuditSink("host=/tmp dbname=x", statement_timeout_ms=1000)
    with pytest.raises(TypeError):
        PostgresApplicationAuditSink("host=/tmp dbname=x", idle_in_transaction_session_timeout_ms=1000)


def _capturing_subclass(base_cls):
    """Review M-1 (major, supervisor ruling 2026-09-03): a subclass that
    records the exact keyword arguments a composition root constructed
    `base_cls` with, then delegates to the real constructor -- used to
    observe a composition root's OWN real object-construction call site
    (`main.build_app`/`control_composition.build_control_service`)
    without hand-constructing a parallel object with the same arguments
    (which would prove nothing about the composition root's own wiring --
    exactly WP-2(a) review M-1's own "insufficient" finding, reproduced
    here as this WP's own M-1 before this fix)."""
    captured: dict[str, Any] = {}

    class _Capturing(base_cls):
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            captured["instance"] = self
            super().__init__(*args, **kwargs)

    return _Capturing, captured


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch):
    """Loads `mitatedb_api/main.py` as a FRESH, independently-executed
    module -- deliberately NOT `import mitatedb_api.main` (which would
    register/reuse the single, process-wide `sys.modules["mitatedb_api.
    main"]` slot).

    Cross-test-file hazard this avoids (found while adding this fixture):
    `mitatedb_api.main` ends with a module-level `app = build_app()` that
    runs ONCE, at FIRST import, against whatever `os.environ` holds at
    that exact moment -- `test_main.py::main_module` already has its own
    identical-shaped fixture for exactly this reason, priming `os.environ`
    via `monkeypatch` before its OWN first import. Two independently-
    primed fixtures in two different test files RACE for which one
    actually executes that first import (pytest's default collection
    order runs this file before `test_main.py`, alphabetically) --
    whichever loses silently inherits the WINNER's env-derived
    configuration for the single shared `mitatedb_api.main.app` object,
    including a `MITATEDB_SERVE_APPS`/platform DSN pointing at a
    DIFFERENT throwaway prefix's database, one this file's own
    module-scoped `platform` fixture drops at teardown -- surfaced
    concretely as `test_main.py::test_build_app_serves_a_real_
    authenticated_request` failing with `AUTH_STATE_UNAVAILABLE` (the
    shared `app` object's platform database no longer exists) whenever
    THIS file's own fixture won the race. Loading a fresh, unregistered
    module object via `importlib.util` sidesteps the shared-singleton
    race entirely: this fixture's own `app`/`build_app` never touches
    `sys.modules["mitatedb_api.main"]`, so it can never win (or lose) that
    race, regardless of collection order.
    """
    import importlib.util

    monkeypatch.setenv("MITATEDB_CREDENTIAL_PEPPER", _APP_PEPPER)
    # A syntactically valid but UNPROVISIONED placeholder env -- this
    # fixture's own callers never rely on the module-level `app = build_
    # app()` result itself (every test below calls `main_module.build_
    # app(env)` explicitly, with its own real env); it only needs to
    # exist so `exec_module` below has valid identifier/DSN syntax to
    # parse. `MITATEDB_PLATFORM_DSN` points at the real, already-verified-
    # reachable admin connection (`_admin_dsn()`, `_require_admin_
    # connection`'s own target) so the connection itself succeeds; the
    # registry LOOKUP then fails fast (no `mitatedb_registry` schema on
    # the bare admin database) with an ordinary `psycopg.Error`, caught
    # below and discarded -- every name `main.py` defines BEFORE its own
    # final `app = build_app()` statement (every class/function this
    # fixture's own callers actually use) is already bound on `module` by
    # the time that statement is reached and fails, so discarding this
    # one expected failure loses nothing.
    monkeypatch.setenv("MITATEDB_PLATFORM_DSN", _admin_dsn())
    monkeypatch.setenv("MITATEDB_SERVE_APPS", "isolatedplaceholder")
    monkeypatch.setenv("MITATEDB_APP_ISOLATEDPLACEHOLDER_RUNTIME_DSN", _admin_dsn())
    monkeypatch.setenv("MITATEDB_APP_ISOLATEDPLACEHOLDER_DEVELOPER_DSN", _admin_dsn())
    main_path = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api" / "main.py"
    spec = importlib.util.spec_from_file_location("mitatedb_api._isolated_main_for_tests", main_path)
    module = importlib.util.module_from_spec(spec)
    # `main.py` uses package-relative imports (`from .application_audit
    # import ...`) -- resolved via `__package__`, against the NORMALLY
    # imported (and therefore normally cached) `mitatedb_api` package;
    # this does not need THIS module itself registered in `sys.modules`
    # under any name for that resolution to work.
    module.__package__ = "mitatedb_api"
    try:
        spec.loader.exec_module(module)
    except Exception:
        pass
    return module


import contextlib


@contextlib.contextmanager
def _closing_build_app(main_module_: Any, env: dict[str, str], monkeypatch: pytest.MonkeyPatch):
    """Review M-1 follow-up (resource-leak fix): `main.build_app` opens a
    REAL `BoundedConnectionPool` (the credential store) and a REAL
    `PostgresBackend` (two persistent connections) per served application
    -- none of which this function's own return value (an ASGI app) lets
    a caller close without driving the ASGI lifespan. Repeated raw
    `build_app(...)` calls across several test functions (this file's own
    M-1/M-3 tests each need a handful) previously leaked enough
    connections across a full test session to exhaust the local
    PostgreSQL server's own connection budget, surfacing as an unrelated
    LATER test's `AuthorizationStateUnavailable`. This context manager
    captures the real `PostgresCredentialStore`/`ApplicationCell`
    instances `build_app` constructs (via the same capturing-subclass/
    patched-`__init__` technique the tests themselves already use) and
    closes them on exit, regardless of outcome."""
    credential_store_cls, credential_store_captured = _capturing_subclass(main_module_.PostgresCredentialStore)
    cell_instances: list = []
    real_cell_init = main_module_.ApplicationCell.__init__

    def _capturing_cell_init(self, *args, **kwargs):
        real_cell_init(self, *args, **kwargs)
        cell_instances.append(self)

    monkeypatch.setattr(main_module_, "PostgresCredentialStore", credential_store_cls)
    monkeypatch.setattr(main_module_.ApplicationCell, "__init__", _capturing_cell_init)
    try:
        app = main_module_.build_app(env)
        yield app
    finally:
        monkeypatch.setattr(main_module_.ApplicationCell, "__init__", real_cell_init)
        store = credential_store_captured.get("instance")
        if store is not None:
            store.close()
        for cell in cell_instances:
            cell._backend.close()


def test_build_app_wires_the_real_writer_connection_to_the_declared_role_setting(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q4 phase (design D-1(b), work order §4 WP-2 変更対象 B/E) --
    SUPERSEDES the Phase 4 env-configured-timeout test this replaces:
    `main.build_app` no longer passes ANY timeout keyword to
    `PostgresApplicationAuditSink(...)` at all (asserted below via the
    SAME capturing-subclass technique the superseded test used), and the
    REAL writer connection's own effective value now comes from `mitatedb
    svc_api`'s PostgreSQL role setting -- proven here for both the shipped
    5000ms/5000ms default (`platform`'s own `0007` migration) and a
    role-level override (`_set_role_timeouts`, the SAME `ALTER ROLE ...
    SET` shape `ops set-platform-timeouts` uses), never a per-connection
    override `build_app` itself performs."""

    def _env(**overrides: str) -> dict[str, str]:
        base = {
            "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
            "MITATEDB_PLATFORM_DSN": platform.api_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.schema,
            "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
            f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
            f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
            # Q4 phase: `platform`'s own seeded `surfaces` declaration
            # includes `control` (matching the common real-deployment
            # topology this fixture models) -- F-6 requires this
            # process' own declared status to agree with that.
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        }
        base.update(overrides)
        return base

    # 1) Shipped default (0007's own seed, no override) -- and the
    # construction call site itself carries no timeout keyword any more.
    capturing_cls, captured = _capturing_subclass(PostgresApplicationAuditSink)
    monkeypatch.setattr(main_module, "PostgresApplicationAuditSink", capturing_cls)
    with _closing_build_app(main_module, _env(), monkeypatch):
        assert "statement_timeout_ms" not in captured["kwargs"]
        assert "idle_in_transaction_session_timeout_ms" not in captured["kwargs"]
        conn = captured["instance"]._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW statement_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
                cur.execute("SHOW idle_in_transaction_session_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == DEFAULT_AUDIT_IDLE_TIMEOUT_MS
        finally:
            conn.close()

    # 2) Role-level override -- must reach the real connection unchanged,
    # with NO env variable involved at all (F-1 rejects the old ones).
    _set_role_timeouts(platform.admin_dsn, platform.api_role, statement_ms=4321, idle_ms=8765)
    try:
        capturing_cls, captured = _capturing_subclass(PostgresApplicationAuditSink)
        monkeypatch.setattr(main_module, "PostgresApplicationAuditSink", capturing_cls)
        with _closing_build_app(main_module, _env(), monkeypatch):
            conn = captured["instance"]._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SHOW statement_timeout")
                    assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 4321
                    cur.execute("SHOW idle_in_transaction_session_timeout")
                    assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 8765
            finally:
                conn.close()
    finally:
        _set_role_timeouts(platform.admin_dsn, platform.api_role, statement_ms=5000, idle_ms=5000)


@pytest.mark.parametrize("removed_var", ["MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS"])
def test_build_app_rejects_the_removed_timeout_env_vars(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, removed_var: str,
) -> None:
    """F-1 (design D-1(d)): defined whatever the value -- exercised
    through the REAL startup path (`main.build_app`), not the fail-fast
    helper called directly, per this WP's own non-vacuity requirement."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        removed_var: "",
    }
    from mitatedb_api.platform_declarations import PlatformDeclarationError

    with pytest.raises(PlatformDeclarationError, match="is no longer read"):
        main_module.build_app(env)


def test_build_app_checks_the_env_mapping_argument_not_os_environ(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WP-1/WP-2 completion condition 4 (design D-1(d)): the removed-env-
    var check (F-1/F-2) inspects the `env` MAPPING `build_app` was
    actually called with, never the real process `os.environ` --
    exercised through the REAL startup path (`main.build_app`), mirroring
    r2db-api's own `test_application_audit.py::test_build_app_checks_the_
    env_mapping_argument_not_os_environ` (this peer's own non-vacuity
    companion to `test_reject_removed_env_checks_the_mapping_argument_
    not_os_environ`, `test_platform_declarations.py`, which only calls
    the helper function directly -- never through this composition
    root)."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    monkeypatch.setenv("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "9999")
    monkeypatch.setenv("MITATEDB_DATA_BASE_URL", "https://this-must-never-be-read.example.invalid/v1")
    with _closing_build_app(main_module, env, monkeypatch):
        pass  # must not raise -- os.environ pollution above is never read


def test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 10 WP-4g (supervisor ruling 2026-09-09, peer-symmetric with
    r2db-api's own same-numbered test): F-16 is not only an `ops
    verify-declarations` check (WP-4f) -- `mitatedb_api.main.build_app`
    itself now fails fast on the SAME condition at real startup, scoped to
    exactly the role THIS process' own pool composition uses (`platform.
    api_role`, the `mitatedbsvc_api`-class role identified here by its own
    real `INSERT` grant on `application_audit`, migration `0005` -- this
    file's own `platform` fixture, unlike `test_main.py`'s/`test_postgres.
    py`'s, always applies it). Lowering it back below its own real floor
    (2 stores x concurrency 32 = 64) -- exactly the pre-`0012_role_
    connection_limits.sql` state every platform was in before Phase 10
    WP-4f -- must raise, never silently start a process that can hit
    PostgreSQL's own hard 'too many connections for role' refusal under
    real concurrent traffic. Restores the migration-seeded limit (68) in a
    `finally` so this shared, module-scoped `platform` fixture is left
    healthy for every other test in this file."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        # This file's own `platform` fixture seeds `surfaces` WITH a
        # `control` half (`_CONTROL_BASE_URL`) -- F-6 requires this
        # process to agree by declaring itself `enabled`, never the
        # default `unavailable` (mirrors `test_build_app_wires_the_real_
        # writer_connection_to_the_declared_role_setting`'s own `_env`
        # helper immediately above).
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 20").format(sql.Identifier(platform.api_role)))
        conn.commit()
    try:
        with pytest.raises(RuntimeError, match="F-16|CONNECTION LIMIT"):
            main_module.build_app(env)
    finally:
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 68").format(sql.Identifier(platform.api_role)))
            conn.commit()
        # Non-空振り: proves the restore above is really what makes
        # `build_app` healthy again -- a mutation that silently drops the
        # new startup check would make BOTH the `pytest.raises` above AND
        # this call succeed, but a mutation that left the check
        # permanently broken (e.g. caching the FIRST observed limit) would
        # fail here instead.
        with _closing_build_app(main_module, env, monkeypatch):
            pass


def test_build_control_app_wires_the_real_control_audit_connection_to_the_declared_role_setting(
    platform: types.SimpleNamespace,
) -> None:
    """Q4 phase (design D-1(b)) -- SUPERSEDES the Phase 4 env-configured-
    timeout test this replaces: same proof as the application-plane test
    above, for `control_composition.build_control_service` and the
    connection that writes `control_audit`
    (`PostgresControlBackend.unit_of_work`), against `mitatedbsvc_
    controlplane`'s own role setting."""
    import mitatedb_api.control_composition as control_composition_module

    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "control-audit-postgres-ctl-pepper-x",
        "MITATEDB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
    }

    backend = control_composition_module.build_control_service(env)._backend
    with backend.unit_of_work() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert ms_from_pg_timeout_text(cur.fetchone()[0]) == DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
            cur.execute("SHOW idle_in_transaction_session_timeout")
            assert ms_from_pg_timeout_text(cur.fetchone()[0]) == DEFAULT_AUDIT_IDLE_TIMEOUT_MS

    _set_role_timeouts(platform.admin_dsn, platform.controlplane_role, statement_ms=2345, idle_ms=6789)
    try:
        backend2 = control_composition_module.build_control_service(env)._backend
        with backend2.unit_of_work() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW statement_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 2345
                cur.execute("SHOW idle_in_transaction_session_timeout")
                assert ms_from_pg_timeout_text(cur.fetchone()[0]) == 6789
    finally:
        _set_role_timeouts(platform.admin_dsn, platform.controlplane_role, statement_ms=5000, idle_ms=5000)


def test_main_wires_the_audit_router_into_both_the_credential_store_and_every_cell(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavioural proof that `main.build_app` shares ONE `AuditRouter`
    between `PostgresCredentialStore` and every `ApplicationCell` it
    builds: captures the real `AuditRouter` instance `build_app`
    constructs, and the real `ApplicationCell`/`PostgresCredentialStore`
    instances, then asserts identity (`is`), not merely that a kwarg
    with a plausible name was passed somewhere."""
    router_cls, router_captured = _capturing_subclass(main_module.AuditRouter)
    cell_captured_list: list = []
    cell_instances: list = []
    real_cell_init = main_module.ApplicationCell.__init__

    def _capturing_cell_init(self, *args, **kwargs):
        cell_captured_list.append(kwargs.get("audit_router"))
        real_cell_init(self, *args, **kwargs)
        cell_instances.append(self)

    credential_store_cls, credential_store_captured = _capturing_subclass(main_module.PostgresCredentialStore)
    monkeypatch.setattr(main_module, "AuditRouter", router_cls)
    monkeypatch.setattr(main_module, "PostgresCredentialStore", credential_store_cls)
    monkeypatch.setattr(main_module.ApplicationCell, "__init__", _capturing_cell_init)
    try:
        main_module.build_app({
            "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
            "MITATEDB_PLATFORM_DSN": platform.api_dsn,
            "MITATEDB_PLATFORM_SCHEMA": platform.schema,
            "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
            f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
            f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
            # Q4 phase: `platform`'s own seeded `surfaces` declaration
            # includes `control` (matching the common real-deployment
            # topology this fixture models) -- F-6 requires this
            # process' own declared status to agree with that.
            "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
        })
    finally:
        monkeypatch.setattr(main_module.ApplicationCell, "__init__", real_cell_init)
        # Review M-1 follow-up (resource-leak fix -- see `_closing_build_
        # app`'s own identical rationale): release the real pool/
        # connections this real `build_app` call opened.
        store = credential_store_captured.get("instance")
        if store is not None:
            store.close()
        for cell in cell_instances:
            cell._backend.close()

    router_instance = router_captured["instance"]
    assert credential_store_captured["kwargs"]["audit_router"] is router_instance
    assert cell_captured_list  # at least one cell was built
    assert all(r is router_instance for r in cell_captured_list)


# ===========================================================================
# D-3 durable denial code table
# ===========================================================================


def test_durable_denial_codes_match_the_design_d3_table() -> None:
    assert DURABLE_DENIAL_CODES == frozenset({
        "AUTH_REQUIRED", "AUTH_INVALID", "AUTH_REVOKED", "FORBIDDEN",
        "APPLICATION_DISABLED", "DESTRUCTIVE_CONFIRMATION_REQUIRED",
    })


# ===========================================================================
# Declared-vocabulary AST guard (§9.2 property 5)
# ===========================================================================
#
# WP-B1 (P4-D16 v3): this file's own `test_declared_event_classes_cover_
# every_emittable_class` (a hand-picked 4-file enumeration,
# `_SOURCE_FILES_WITH_EMIT_SITES`, that never reached `http.py`'s real
# `route_denial(..., event_class="authentication_denied", ...)` emit site)
# has been REMOVED and consolidated into `test_audit_query.py`'s own
# test of the same name -- that file's scan already walked the whole
# package unfiltered by callee name; WP-B1 widened it to a RECURSIVE
# `rglob` and added the (b)/(c)/(d) checks (literal discipline,
# definition-side keyword-only guarantee, dict-smuggling ban) alongside
# it. Two same-named tests with two different (one strong, one weak)
# implementations is exactly the kind of drift L4-5 exists to close; see
# `docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md` §1 P4-D16 v3.


def test_durable_path_never_passes_through_the_six_field_rounding_sink() -> None:
    """Design §6.2 (monitor裁定 R6): the durable emitters (`audit_
    dispatch.py`/`application_audit.py`) never import or call `audit.
    AuditSink`/`.record` at all -- structurally separate from the
    pre-existing 6-field sink, whose `_SAFE_EVENTS`/`_SAFE_DETAILS`
    silently round anything outside its OWN vocabulary to `"unclassified"`/
    `"unspecified"`. If the durable path ever routed a value through that
    rounding, the durable `event_class` column could silently diverge
    from what was actually attempted -- and from `DECLARED_AUDIT_EVENT_
    CLASSES` (this file's own preceding AST guard)."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    for name in ("audit_dispatch.py", "application_audit.py"):
        source = (src_dir / name).read_text()
        assert "from .audit import" not in source
        assert "import audit\n" not in source


def test_declared_event_class_values_are_disjoint_from_the_six_field_sink_rounding_fallbacks() -> None:
    """None of the durable vocabulary's values collide with the 6-field
    sink's OWN rounding fallback strings (`"unclassified"`/
    `"unspecified"`) -- a reader distinguishing the two streams must never
    see an ambiguous value."""
    assert "unclassified" not in DECLARED_AUDIT_EVENT_CLASSES
    assert "unspecified" not in DECLARED_AUDIT_EVENT_CLASSES


# ===========================================================================
# In-memory dispatch unit tests (fast, deterministic, no real PostgreSQL)
# ===========================================================================


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_dispatch_point_is_the_destructive_confirmation_choke() -> None:
    """§9.2 property 6: the SAME `_validate_delete_confirmation` choke
    both `ApplicationCell.delete` and `transact`'s pass-1 planning loop
    (`_plan_operation`) call is what determines fail-closed vs.
    buffer-class -- not `event_class`. Fixed here by source inspection: a
    single call site name, used by both the dedicated and batch-embedded
    paths."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    source = (src_dir / "cell.py").read_text()
    assert source.count("def _validate_delete_confirmation(") == 1
    assert source.count("self._validate_delete_confirmation(") == 2  # delete() and _plan_operation()


def test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n() -> None:
    clock = _FakeClock()
    router = make_router(clock=clock)
    for _ in range(50):
        router.route_denial(
            reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None,
            application_id=None, actor_type="unknown", actor_id="leaked-cred", role=None,
            operation="authenticate", target_kind="credential", target_id="leaked-cred",
        )
    clock.advance(61)
    router.flush()
    events = router.durable_sink.events()
    assert len(events) == 2  # first-occurrence row + one coalesced summary row
    assert events[0].count is None
    assert events[1].count == 49


def test_coalesced_summary_row_with_exactly_one_repeat_writes_no_literal_count_of_one() -> None:
    clock = _FakeClock()
    router = make_router(clock=clock)
    for _ in range(2):
        router.route_denial(
            reason_code="FORBIDDEN", event_class="authorization_denied", request_id=None,
            application_id="a", actor_type="application_credential", actor_id="c1", role="runtime",
            operation="schema", target_kind="collection", target_id=None,
        )
    clock.advance(61)
    router.flush()
    events = router.durable_sink.events()
    assert len(events) == 2
    assert events[1].count is None  # exactly one repeat -> NULL, never a literal 1


def test_different_denial_keys_do_not_coalesce_together() -> None:
    router = make_router()
    router.route_denial(
        reason_code="FORBIDDEN", event_class="authorization_denied", request_id=None, application_id="a",
        actor_type="application_credential", actor_id="c1", role="runtime", operation="schema",
        target_kind="collection", target_id=None,
    )
    router.route_denial(
        reason_code="FORBIDDEN", event_class="authorization_denied", request_id=None, application_id="b",
        actor_type="application_credential", actor_id="c2", role="runtime", operation="schema",
        target_kind="collection", target_id=None,
    )
    assert len(router.durable_sink.events()) == 2


def test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry() -> None:
    router = make_router()
    router.route_denial(
        reason_code="VALIDATION_FAILED", event_class="authorization_denied", request_id=None, application_id="a",
        actor_type="application_credential", actor_id="c1", role="runtime", operation="query",
        target_kind="collection", target_id=None,
    )
    assert router.durable_sink.events() == ()
    assert router.pending_buffer_count() == 0


def test_capability_unsupported_and_not_found_and_service_unavailable_denials_add_no_durable_row() -> None:
    router = make_router()
    for code in ("CAPABILITY_UNSUPPORTED", "NOT_FOUND", "LIMIT_EXCEEDED", "AUTH_STATE_UNAVAILABLE", "CONFLICT"):
        router.route_denial(
            reason_code=code, event_class="authorization_denied", request_id=None, application_id="a",
            actor_type="application_credential", actor_id="c1", role="runtime", operation="query",
            target_kind="collection", target_id=None,
        )
    assert router.durable_sink.events() == ()


def test_concurrent_same_key_denials_are_both_fail_closed_when_the_sink_is_down() -> None:
    sink = ApplicationAuditSink()
    sink.inject_fault(RuntimeError("sink down"))
    router = make_router(sink)
    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        try:
            router.route_denial(
                reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None,
                application_id=None, actor_type="unknown", actor_id="x", role=None, operation="authenticate",
                target_kind="credential", target_id="x",
            )
        except AuditSinkUnavailable as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 4  # every concurrent caller for the SAME key fails closed


def test_different_key_denials_do_not_wait_on_each_other() -> None:
    """A slow-appending sink for ONE key must not block a DIFFERENT key's
    own route() call (per-key locking, not a process-wide lock held
    across I/O)."""
    release = threading.Event()
    started = threading.Event()

    class _SlowSink(ApplicationAuditSink):
        def append(self, **kwargs):
            if kwargs.get("actor_id") == "slow":
                started.set()
                release.wait(timeout=2.0)
            return super().append(**kwargs)

    router = make_router(_SlowSink())
    slow_thread = threading.Thread(target=lambda: router.route_denial(
        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None, application_id=None,
        actor_type="unknown", actor_id="slow", role=None, operation="authenticate", target_kind="credential", target_id="slow",
    ))
    slow_thread.start()
    assert started.wait(timeout=2.0)
    fast_start = time.monotonic()
    router.route_denial(
        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None, application_id=None,
        actor_type="unknown", actor_id="fast", role=None, operation="authenticate", target_kind="credential", target_id="fast",
    )
    fast_elapsed = time.monotonic() - fast_start
    assert fast_elapsed < 1.0
    release.set()
    slow_thread.join(timeout=2.0)


def test_force_expire_denial_windows_flushes_an_unexpired_window_too() -> None:
    clock = _FakeClock()
    router = make_router(clock=clock)
    router.route_denial(
        reason_code="FORBIDDEN", event_class="authorization_denied", request_id=None, application_id="a",
        actor_type="application_credential", actor_id="c1", role="runtime", operation="schema",
        target_kind="collection", target_id=None,
    )
    router.route_denial(
        reason_code="FORBIDDEN", event_class="authorization_denied", request_id=None, application_id="a",
        actor_type="application_credential", actor_id="c1", role="runtime", operation="schema",
        target_kind="collection", target_id=None,
    )
    router.flush()  # window not yet expired -- ordinary flush leaves it open
    assert len(router.durable_sink.events()) == 1
    router.flush(force_expire_denial_windows=True)
    assert len(router.durable_sink.events()) == 2


class _AggregateOnlyFailingSink(ApplicationAuditSink):
    """A durable sink that fails ONLY a coalesced-denial summary
    (aggregate) row -- identified by carrying a non-`None` `count` -- and
    otherwise behaves normally (first-occurrence rows, buffer flushes,
    alert rows all succeed). `fail_aggregate` is toggled by the test to
    simulate recovery."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_aggregate = True

    def append(self, **kwargs):
        if kwargs.get("count") is not None and self.fail_aggregate:
            raise RuntimeError("simulated aggregate-write failure")
        return super().append(**kwargs)


def test_failed_aggregate_write_retains_the_repeat_count_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    """A failed coalesced-denial summary write (reached via the periodic/
    explicit sweep, `flush_expired`) must not lose the accumulated repeat
    count -- it is retained and retried on every subsequent flush; once
    the sink recovers, exactly one summary row carries the FULL
    accumulated total."""
    sink = _AggregateOnlyFailingSink()
    clock = _FakeClock()
    router = make_router(sink, clock=clock)
    n_repeats = 5
    for _ in range(1 + n_repeats):
        router.route_denial(
            reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None, application_id=None,
            actor_type="unknown", actor_id="leaked", role=None, operation="authenticate",
            target_kind="credential", target_id="leaked",
        )
    assert len(sink.events()) == 1  # only the first-occurrence row so far

    clock.advance(61.0)
    with caplog.at_level(logging.ERROR):
        router.flush()
    assert len(sink.events()) == 1  # aggregate write failed -- retained, not lost
    assert len([r for r in caplog.records if "could not be written" in r.message]) == 1

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        router.flush()  # still failing -- no additional log line (state unchanged)
    assert not [r for r in caplog.records if "could not be written" in r.message]
    assert len(sink.events()) == 1

    sink.fail_aggregate = False
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        router.flush()
    assert len([r for r in caplog.records if "recorded; retry cleared" in r.message]) == 1
    events = sink.events()
    assert len(events) == 2
    assert events[1].count == n_repeats


def test_failed_aggregate_write_via_inline_route_expiry_retains_the_repeat_count() -> None:
    """Same property as the sweep-path test above, reached instead through
    `route()`'s OWN inline expired-window flush (a fresh `route()` call
    for the SAME key, arriving after the window has already expired)."""
    sink = _AggregateOnlyFailingSink()
    clock = _FakeClock()
    router = make_router(sink, clock=clock)
    kwargs = dict(
        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None, application_id=None,
        actor_type="unknown", actor_id="leaked2", role=None, operation="authenticate",
        target_kind="credential", target_id="leaked2",
    )
    router.route_denial(**kwargs)  # first occurrence -- durable row #1
    n_repeats = 5
    for _ in range(n_repeats):
        router.route_denial(**kwargs)

    clock.advance(61.0)
    # Inline expiry: a FRESH route() call for the same (now-expired) key
    # -- not the sweep -- must attempt (and fail to write) the aggregate
    # row for the OLD window, then open a fresh window carrying THIS new
    # occurrence as its own synchronous first-occurrence row (route()'s
    # own normative behaviour: the aggregate-flush attempt and the fresh
    # window's own first-occurrence INSERT are two independent effects of
    # one route() call).
    router.route_denial(**kwargs)
    events_after_inline_expiry = sink.events()
    assert len(events_after_inline_expiry) == 2  # original first-occurrence + the fresh window's own
    assert events_after_inline_expiry[1].count is None  # the fresh window's first row, not a summary

    sink.fail_aggregate = False
    clock.advance(61.0)
    router.flush()  # the fresh window's own summary row -- carrying the RETAINED 5, not lost
    events = sink.events()
    assert len(events) == 3
    assert events[2].count == n_repeats  # the requeued 5 repeats, merged into the fresh window -- never lost


def test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval() -> None:
    """The alert-row EMISSION RATE is bounded independently of how often
    eviction/flush-failure occurs -- "1 alert row (attempt) per flush
    interval per process" for as long as the underlying flush keeps
    failing."""
    sink = _FlushAlwaysFailsSink()
    clock = _FakeClock()
    alert_min_interval_s = 2.0
    router = make_router(sink, buffer_capacity=2, clock=clock, alert_min_interval_s=alert_min_interval_s)
    n_requests = 40
    step_s = 0.3  # far more frequent than the alert interval
    for i in range(n_requests):
        router.push_buffer_event(
            event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
            actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
        )
        clock.advance(step_s)
    elapsed_s = n_requests * step_s

    clock.advance(router._buffer._alert_backoff_s + 1.0)
    router.flush()

    alert_rows = [e for e in sink.events() if e.event_class == "security_control_failure"]
    upper_bound = int(elapsed_s // alert_min_interval_s) + 2  # ceil + slack
    assert 1 <= len(alert_rows) <= upper_bound
    assert len(alert_rows) < n_requests  # must not emit one alert row per request


def test_buffer_does_not_grow_past_its_configured_bound() -> None:
    sink = ApplicationAuditSink()
    sink.inject_fault(RuntimeError("sink down"))  # never actually flushes
    router = make_router(sink, buffer_capacity=10, alert_min_interval_s=1000.0)
    for i in range(50):
        router.push_buffer_event(
            event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
            actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
        )
    assert router._buffer.pending_count() <= 10


def test_concurrent_push_during_a_failing_flush_never_grows_the_buffer_past_capacity() -> None:
    """Review B-3 (blocker, supervisor ruling 2026-09-03, adjudicated (a)
    -- same fix, same strength as r2db-api's own identical patch,
    `scratchpad/r2db-flush-reentrancy.patch`): while `flush()` holds
    `pending` outside `self._events` (the swap that fixed the B-2
    double-write), `push()` sees a transiently empty buffer and does not
    evict against `pending`'s own size -- only against whatever `push()`
    itself is concurrently adding. A naive unconditional restore-on-
    failure (`self._events = pending + self._events`) could therefore let
    the buffer grow WITHOUT BOUND across repeated failed flushes,
    breaking D-4's "bounded in-memory buffer" -- and silently: no
    `push()` eviction fires during that growth, so neither `_dropped_
    total` nor the overflow alert ever reflects it.

    Reproduces the exact scenario deterministically (an `Event`, not a
    timing guess): a `capacity`-sized backlog is already held by an
    in-flight, durably-failing `flush()` call (blocked inside
    `append_many`) when MORE events are concurrently `push()`-ed. Before
    this fix: 413 passed (this test did not exist); the SAME assertions
    against the pre-fix `flush()` body reproduce the r2db audit's own
    measured "capacity * 3.5, `dropped_total` stuck at 0" growth. Asserts
    (i) the buffer never exceeds `capacity` once the failed flush's
    restore completes, (ii) the overflow alert's `count` equals EXACTLY
    the number of events actually, irrevocably truncated (never the
    retained remainder -- N-1's own discipline), and (iii) the truncation
    drops the OLDEST events first (FIFO, matching `push()`'s own `pop(0)`
    eviction), never the newly-pushed ones."""
    first_call_started = threading.Event()
    release_first_call = threading.Event()
    append_calls: list[dict] = []

    class _BlockThenAlwaysFailSink(ApplicationAuditSink):
        def append(self, **kwargs):
            # The overflow-alert row (`_retry_alert()`, called at the
            # tail of `flush()`) -- recorded so this test can assert on
            # its `count` directly.
            append_calls.append(dict(kwargs))
            return super().append(**kwargs)

        def append_many(self, events):
            first_call_started.set()
            assert release_first_call.wait(timeout=5), "test never released the blocked flush() call"
            raise RuntimeError("simulated durably-failing sink")

    def _event(request_id: str) -> ApplicationAuditEvent:
        return ApplicationAuditEvent(
            event_id=str(uuid.uuid4()), event_class="data_operation", occurred_at="2026-09-03T00:00:00+00:00",
            request_id=request_id, application_id="a", actor_type="application_credential", actor_id="c1",
            role="runtime", operation="query", target_kind="collection", outcome="allow", reason_code=None,
            target_id=None,
        )

    sink = _BlockThenAlwaysFailSink()
    capacity = 5
    router = make_router(sink, buffer_capacity=capacity, alert_min_interval_s=0.0)
    buffer = router._buffer
    for i in range(capacity):
        buffer._events.append(_event(f"seed{i + 1}"))

    flush_thread = threading.Thread(target=buffer.flush, name="in-flight-flush")
    flush_thread.start()
    assert first_call_started.wait(timeout=5), "flush() never reached append_many()"

    # The flush is now blocked inside append_many, holding no lock, with
    # `capacity` events swapped OUT of `self._events` -- push() below
    # sees an empty buffer and will not evict any of these new pushes,
    # exactly the B-3 window. Stays below the flush threshold (0.8 *
    # capacity == 4) so this does not itself trigger a nested
    # threshold-flush.
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

    release_first_call.set()
    flush_thread.join(timeout=5)
    assert not flush_thread.is_alive(), "flush() deadlocked after being released"

    total_pushed = capacity + new_event_count
    expected_dropped = total_pushed - capacity  # combined restore length minus capacity
    assert buffer.pending_count() <= capacity, (
        f"buffer must never exceed its configured capacity ({capacity}) after a failed flush's "
        f"restore, got {buffer.pending_count()}"
    )
    alert_rows = [c for c in append_calls if c.get("event_class") == "security_control_failure"]
    assert alert_rows, "a genuine truncation must produce an overflow alert row, same as a push()-path eviction"
    for row in alert_rows:
        assert row["reason_code"] == "audit_buffer_overflow"
    assert sum(row.get("count") or 1 for row in alert_rows) == expected_dropped, (
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
    recovered (the threshold flush keeps refilling it), so the prior
    "only when empty" gate left the flag (and the alert backoff it feeds)
    stuck at the sink-broken state long after recovery.

    Independent implementation of r2db-api's own identical-shape test:
    reproduces "buffer not empty under continuous push" deterministically
    rather than by timing -- the recovery flush's own (now succeeding)
    `append_many` call appends a new event directly into the buffer
    before returning, standing in for a concurrent `push()` landing while
    that I/O was in flight, so `self._events` is provably non-empty at
    the moment the success branch runs.

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
    def _event(request_id: str) -> ApplicationAuditEvent:
        return ApplicationAuditEvent(
            event_id=str(uuid.uuid4()), event_class="data_operation", occurred_at="2026-09-03T00:00:00+00:00",
            request_id=request_id, application_id="a", actor_type="application_credential", actor_id="c1",
            role="runtime", operation="query", target_kind="collection", outcome="allow", reason_code=None,
            target_id=None,
        )

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    class _ControllableSink(ApplicationAuditSink):
        """A single `fail` switch controls BOTH write paths (`append_many`
        -- the ordinary buffer flush -- and `append` -- the overflow-alert
        row), standing in for "the sink is down" / "the sink has
        recovered" as one fact, the same way a real Postgres outage would
        affect both. `refill_on_next_success_write`, when set, lets the
        NEXT successful `append_many` refill the buffer before returning
        -- simulating a concurrent `push()` landing mid-flight."""

        def __init__(self) -> None:
            super().__init__()
            self.fail = True
            self.buffer: Any = None
            self.refill_on_next_success_write = False

        def append_many(self, events):
            if self.fail:
                raise RuntimeError("simulated durably-failing sink (write path)")
            if self.refill_on_next_success_write:
                self.refill_on_next_success_write = False
                assert self.buffer is not None
                self.buffer._events.append(_event("concurrent-push"))

        def append(self, **kwargs):
            if self.fail:
                raise RuntimeError("simulated durably-failing sink (alert path)")

    clock = _Clock()
    sink = _ControllableSink()
    alert_min_interval_s = 2.0
    capacity = 2
    router = make_router(sink, buffer_capacity=capacity, alert_min_interval_s=alert_min_interval_s, clock=clock)
    buffer = router._buffer
    sink.buffer = buffer

    # Genuine drops via push()'s own eviction branch (capacity 2, 5
    # pushes, BOTH sink write paths durably failing throughout) -- also
    # drives several threshold-triggered failing flush() calls, each
    # setting `_flush_currently_failing = True` and (once `_alert_pending`
    # is set) attempting, and failing, the alert row -- growing
    # `_alert_backoff_s` past the floor via `_retry_alert`'s own exception
    # branch.
    for i in range(5):
        buffer.push(_event(f"seed{i + 1}"))
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
    def _event(request_id: str) -> ApplicationAuditEvent:
        return ApplicationAuditEvent(
            event_id=str(uuid.uuid4()), event_class="data_operation", occurred_at="2026-09-03T00:00:00+00:00",
            request_id=request_id, application_id="a", actor_type="application_credential", actor_id="c1",
            role="runtime", operation="query", target_kind="collection", outcome="allow", reason_code=None,
            target_id=None,
        )

    class _BlockFirstCallThenFailSink(ApplicationAuditSink):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.first_call_started = threading.Event()
            self.release_first_call = threading.Event()

        def append_many(self, events):
            self.calls += 1
            if self.calls == 1:
                self.first_call_started.set()
                assert self.release_first_call.wait(timeout=5), "test never released the blocked first call"
                raise RuntimeError("simulated durably-failing sink (first call)")
            # second call onward: succeeds immediately, unblocked.

    sink = _BlockFirstCallThenFailSink()
    router = make_router(sink, buffer_capacity=100, alert_min_interval_s=0.0)
    buffer = router._buffer

    # Thread A: a flush() whose own write is the FIRST call this sink ever
    # receives -- blocked mid-I/O below, will raise once released.
    buffer._events.append(_event("a1"))
    thread_a = threading.Thread(target=buffer.flush, name="failing-flush")
    thread_a.start()
    assert sink.first_call_started.wait(timeout=5), "thread A's flush() never reached append_many()"

    # Thread A is now blocked inside append_many, holding no lock (the B-2
    # /B-3 swap-out already emptied `self._events`). Push a new event and
    # run a SECOND, independent flush() on the main thread: its own
    # append_many call is the second one this sink ever receives, which
    # succeeds immediately.
    buffer.push(_event("b1"))
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


def test_healthy_sink_threshold_flush_prevents_reaching_capacity_eviction(caplog: pytest.LogCaptureFixture) -> None:
    router = make_router(buffer_capacity=10, alert_min_interval_s=1000.0)
    with caplog.at_level(logging.ERROR):
        for i in range(50):
            router.push_buffer_event(
                event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
                actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
            )
    assert "buffer overflow" not in caplog.text


class _FlushAlwaysFailsSink(ApplicationAuditSink):
    """A durable sink whose batch flush (`append_many`, D-4's ordinary-
    buffer-flush path) always fails, but whose single-event `append`
    (D-4's overflow-alert path) succeeds -- lets a test force the buffer
    to actually reach `capacity` and evict for real, instead of the
    threshold-flush (M-2) draining it before eviction is ever reached
    under a healthy sink."""

    def append_many(self, events):
        raise RuntimeError("flush always fails")


def test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row(caplog: pytest.LogCaptureFixture) -> None:
    """Mirrors r2db-api's own identical-shape test (WP-2(a) fix round 2
    review N-1): capacity=2, 5 pushes, `append_many` durably failing
    throughout, `append` (the alert row) healthy. The clock stays fixed
    during the push loop -- the alert-rate floor (default 2.0s) blocks
    every retry after the first attempt, so all 3 genuine evictions
    accumulate into ONE alert row once the clock is advanced and a final
    flush is issued."""
    sink = _FlushAlwaysFailsSink()
    clock = _FakeClock()
    router = make_router(sink, buffer_capacity=2, clock=clock)
    with caplog.at_level(logging.ERROR):
        for i in range(5):
            router.push_buffer_event(
                event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
                actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
            )
    assert "buffer overflow" in caplog.text
    assert router._buffer.pending_count() == 2  # the 2 never-evicted events are still genuinely buffered
    clock.advance(100.0)
    router.flush()
    alert_rows = [e for e in sink.events() if e.event_class == "security_control_failure"]
    assert alert_rows
    assert sum(e.count or 1 for e in alert_rows) == 3  # 5 pushed, capacity 2 -> 3 evicted


def test_buffer_overflow_alert_row_with_exactly_one_drop_writes_no_literal_count_of_one() -> None:
    sink = _FlushAlwaysFailsSink()
    clock = _FakeClock()
    router = make_router(sink, buffer_capacity=2, clock=clock)
    for i in range(3):  # capacity 2, 3 pushes -> exactly 1 eviction
        router.push_buffer_event(
            event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
            actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
        )
    clock.advance(100.0)
    router.flush()
    alert_rows = [e for e in sink.events() if e.event_class == "security_control_failure"]
    assert sum(e.count or 1 for e in alert_rows) == 1
    for row in alert_rows:
        assert row.count is None


def test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations(caplog: pytest.LogCaptureFixture) -> None:
    class _AlertFailingSink(ApplicationAuditSink):
        def append(self, **kwargs):
            if kwargs.get("event_class") == "security_control_failure":
                raise RuntimeError("alert sink down")
            return super().append(**kwargs)

        def append_many(self, events):
            raise RuntimeError("flush always fails")

    clock = _FakeClock()
    sink = _AlertFailingSink()
    router = make_router(sink, buffer_capacity=2, clock=clock, alert_min_interval_s=1.0)
    with caplog.at_level(logging.ERROR):
        for i in range(5):
            router.push_buffer_event(
                event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
                actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
            )
    assert "could not be written; retrying" in caplog.text
    # Operations are never blocked -- push_buffer_event itself never raised.
    assert router._buffer.pending_count() <= 2


def test_buffer_row_failure_does_not_block_a_fail_closed_operation() -> None:
    """§9.2 property 7: a buffer-row write failure must never prevent a
    fail-closed operation's own (separate) durable write from succeeding
    -- the buffer flush and the pre-commit hook always use independent
    sink calls/connections."""
    class _BufferFailingSink(ApplicationAuditSink):
        def append_many(self, events):
            raise RuntimeError("buffer flush down")

    router = make_router(_BufferFailingSink())
    router.push_buffer_event(
        event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
        actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id="t",
    )
    router.flush()  # buffer flush fails silently (retained, not raised)
    hook = router.make_pre_commit_hook(
        event_class="schema_change", request_id=None, application_id="a", actor_type="application_credential",
        actor_id="c1", role="developer", operation="create_collection", target_kind="collection", target_id="t",
    )
    hook.pre_commit()  # must succeed -- independent sink call


def test_two_concurrent_flushes_never_write_the_same_buffered_event_twice() -> None:
    """Review B-2 (major, supervisor ruling 2026-09-03): `_AuditBuffer.
    flush()` previously snapshotted `pending = list(self._events)` under
    the lock but only removed that prefix from `self._events` AFTER the
    (unlocked, potentially slow) `append_many` I/O completed -- two
    concurrent `flush()` calls (the composition root's own periodic
    thread racing a request thread's own threshold-triggered flush,
    §7.3's "TWO flush triggers") could both snapshot the SAME still-
    present events before either one's own slower I/O had a chance to
    remove them, durably writing every event in that overlap TWICE.

    Reproduced deterministically (not by timing luck): thread A's own
    `append_many` is held open on an `Event`, simulating slow I/O still
    in flight; thread B's `flush()` is then started and allowed to run to
    completion WHILE thread A is still blocked. With the fix (swap
    `self._events` out for a fresh empty list UNDER THE LOCK, before any
    I/O begins), thread B's own swap always sees an empty `self._events`
    at that point (thread A's own swap already emptied it, synchronously,
    before thread A's slow I/O ever started) -- so thread B's `flush()`
    must return WITHOUT calling `append_many` at all, never re-sending
    thread A's still-in-flight batch. Releasing thread A afterward, the
    UNION of everything actually written must equal exactly what was
    pushed, with no event written twice."""
    thread_a_may_proceed = threading.Event()
    thread_a_entered_append_many = threading.Event()
    written_batches: list[list[str]] = []
    write_lock = threading.Lock()

    class _SlowFirstFlushSink(ApplicationAuditSink):
        def append_many(self, events):
            thread_a_entered_append_many.set()
            thread_a_may_proceed.wait(timeout=5.0)
            with write_lock:
                written_batches.append([e.event_id for e in events])
            super().append_many(events)

    router = make_router(_SlowFirstFlushSink())
    for i in range(6):
        router.push_buffer_event(
            event_class="data_operation", request_id=None, application_id="a", actor_type="application_credential",
            actor_id="c1", role="runtime", operation="query", target_kind="collection", target_id=str(i),
        )
    with router._buffer._lock:
        expected_ids = [e.event_id for e in router._buffer._events]
    assert len(expected_ids) == 6

    thread_a = threading.Thread(target=router.flush)
    thread_a.start()
    assert thread_a_entered_append_many.wait(timeout=5.0), "thread A never reached append_many"

    # Thread A's own swap-out has already happened (it is blocked INSIDE
    # append_many, which only runs after the swap) -- thread B's flush()
    # must see an empty buffer and return without writing anything.
    router.flush()
    assert written_batches == [], "a concurrent flush() must never re-send a batch another flush() already swapped out"

    thread_a_may_proceed.set()
    thread_a.join(timeout=5.0)

    all_written_ids = [event_id for batch in written_batches for event_id in batch]
    assert sorted(all_written_ids) == sorted(expected_ids), (
        "the union of everything written must equal exactly what was pushed -- nothing lost, nothing duplicated"
    )
    assert len(all_written_ids) == len(set(all_written_ids)), "no event_id was written twice"


# ===========================================================================
# Fail-closed by construction (§9.2 property 1) -- pure in-memory backend
# (SQLite) with an injected-fault durable sink, exercised through the
# public ApplicationCell surface. Real-PostgreSQL equivalents follow below.
# ===========================================================================


def _sqlite_cell(router: AuditRouter) -> ApplicationCell:
    return ApplicationCell("appone", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)


def test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_sqlite() -> None:
    sink = ApplicationAuditSink()
    sink.inject_fault(RuntimeError("sink down"))
    router = make_router(sink)
    cell = _sqlite_cell(router)
    developer = make_developer(cell, "appone")
    with pytest.raises(AuditSinkUnavailable):
        developer.create_collection("things", {"id": "integer"})
    assert cell._backend.schema_count() == 0


def test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_sqlite() -> None:
    sink = ApplicationAuditSink()
    router = make_router(sink)
    cell = _sqlite_cell(router)
    developer = make_developer(cell, "appone")
    developer.create_collection("things", {"id": "integer"})
    runtime = make_runtime(cell, "appone")
    runtime.insert("things", {"id": 1})
    sink.inject_fault(RuntimeError("sink down"))
    revision = cell._backend.schema_revision()
    from mitatedb_api.cell import _delete_confirmation_phrase
    phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
    with pytest.raises(AuditSinkUnavailable):
        runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase)
    rows = runtime.read("things")
    assert len(rows) == 1  # data unchanged


def test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails_sqlite() -> None:
    sink = ApplicationAuditSink()
    sink.inject_fault(RuntimeError("sink down"))
    router = make_router(sink)
    cell = _sqlite_cell(router)
    runtime = make_runtime(cell, "appone")
    with pytest.raises(AuditSinkUnavailable):
        cell._require_developer(runtime.principal)


# ===========================================================================
# Real-PostgreSQL: fail-closed, commit-failure error rows, process-loss,
# 1-operation-1-row, buffer/P4-D5 emit sites, parity.
# ===========================================================================


def test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_postgres(app_a: types.SimpleNamespace) -> None:
    sink = ApplicationAuditSink()
    router = make_router(sink)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        sink.inject_fault(RuntimeError("sink down"))
        revision = cell._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        with pytest.raises(AuditSinkUnavailable):
            runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase)
        sink.inject_fault(None)
        rows = runtime.read("things")
        assert len(rows) == 1  # data unchanged despite the raised error
    finally:
        backend.close()


def test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_postgres(app_a: types.SimpleNamespace) -> None:
    sink = ApplicationAuditSink()
    sink.inject_fault(RuntimeError("sink down"))
    router = make_router(sink)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        with pytest.raises(AuditSinkUnavailable):
            developer.create_collection("things", {"id": "integer"})
        with pytest.raises(FoundationError):
            cell._backend.field_domains("things")  # never created
    finally:
        backend.close()


def test_each_data_operation_adds_exactly_one_application_audit_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable, alert_min_interval_s=0.0)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        assert len(durable.events()) == 1  # schema_change: exactly one durable row
    finally:
        backend.close()
        clean_application_audit(platform)


def test_each_data_operation_adds_exactly_one_application_audit_row_for_every_operation_kind(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """Review m-3 (minor, folded into "全件必須"): extends the identical
    property the preceding test fixes only for `create_collection` to
    EVERY operation kind D-10's own "at most one durable row per
    operation" rule covers -- `add_field` and destructive `delete`/
    `transact` (fail-closed, durable immediately, no flush needed) and
    `query`/`insert`/`update`/non-destructive `transact` (buffer-class,
    durable only after a flush) -- so a regression that left a stray
    post-commit `__record`-style SECOND durable emit on any ONE of them
    (D-10's own prohibited case (ii)) is caught by row-count arithmetic,
    not merely by the event CLASSES present."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable, alert_min_interval_s=0.0)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        runtime = make_runtime(cell, app_a.app_id)

        def _count() -> int:
            return len(durable.events())

        # 1) create_collection -- fail-closed, durable immediately.
        developer.create_collection("things", {"id": "integer"})
        assert _count() == 1

        # 2) add_field -- fail-closed, durable immediately.
        developer.add_field("things", "label", "text")
        assert _count() == 2

        # 3) insert -- buffer-class, durable only after flush.
        runtime.insert("things", {"id": 1, "label": "a"})
        assert _count() == 2  # not yet flushed
        router.flush()
        assert _count() == 3

        # 4) query (read) -- buffer-class.
        runtime.read("things")
        router.flush()
        assert _count() == 4

        # 5) update -- buffer-class.
        runtime.update("things", {"label": "b"}, [Filter("id", "eq", 1)])
        router.flush()
        assert _count() == 5

        # 6) non-destructive transact (insert-only batch) -- buffer-class,
        # exactly ONE row for the WHOLE batch (not one per operation).
        runtime.transact([
            {"type": "insert", "collection": "things", "values": {"id": 2, "label": "c"}},
            {"type": "insert", "collection": "things", "values": {"id": 3, "label": "d"}},
        ])
        router.flush()
        assert _count() == 6

        # 7) destructive delete (single-operation) -- fail-closed,
        # durable immediately.
        revision = cell._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase)
        assert _count() == 7

        # 8) destructive transact (batch containing a delete) --
        # fail-closed, exactly ONE row for the WHOLE batch.
        revision = cell._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 2)], revision)
        runtime.transact([
            {"type": "insert", "collection": "things", "values": {"id": 4, "label": "e"}},
            {"type": "delete", "collection": "things", "values": {}, "filters": [Filter("id", "eq", 2)],
             "destructive": True, "confirm": phrase},
        ])
        assert _count() == 8
    finally:
        backend.close()
        clean_application_audit(platform)


def test_query_insert_and_update_success_events_are_durably_recorded(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """P4-D5: this peer recorded NONE of these before Phase 4."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable, alert_min_interval_s=0.0)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        runtime.update("things", {"id": 2}, [Filter("id", "eq", 1)])
        runtime.read("things")
        router.flush()
        events = durable.events()
        classes = [row[APPLICATION_AUDIT_FIELDS.index("event_class")] for row in events]
        operations = [row[APPLICATION_AUDIT_FIELDS.index("operation")] for row in events]
        assert classes.count("schema_change") == 1
        assert "insert" in operations
        assert "update" in operations
        assert "query" in operations
    finally:
        backend.close()
        clean_application_audit(platform)


def test_delete_bearing_mutate_never_enters_the_buffer_path(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable, buffer_capacity=1000, alert_min_interval_s=0.0)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        revision = cell._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        runtime.transact([
            {"type": "insert", "collection": "things", "values": {"id": 2}},
            {"type": "delete", "collection": "things", "values": {}, "filters": [Filter("id", "eq", 1)],
             "destructive": True, "confirm": phrase},
        ])
        # The batch is destructive -- its durable row (if any) must
        # already be present WITHOUT calling router.flush() (buffer-class
        # events only become durable after a flush).
        events_before_flush = durable.events()
        destructive_rows = [e for e in events_before_flush if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "destructive_data_operation"]
        assert len(destructive_rows) == 1
    finally:
        backend.close()
        clean_application_audit(platform)


def test_failed_data_commit_writes_an_error_row_for_the_same_request_id(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)

        # Force the backend's own DDL commit to fail AFTER the durable
        # pre-commit hook has already succeeded, by monkeypatching the
        # developer connection's `commit` to raise -- but only on the
        # SECOND call: `create_collection`'s own `schema_count()` guard
        # (`backend_postgres.py`) already commits its own read-only
        # transaction once, before the DDL statement is even issued, and
        # that first commit must succeed normally.
        real_commit = backend._developer.commit
        calls = {"n": 0}

        def _commit_second_call_fails():
            calls["n"] += 1
            if calls["n"] >= 2:
                raise psycopg.OperationalError("simulated commit failure")
            return real_commit()

        probe_request_id = "req-" + uuid.uuid4().hex
        with patch.object(backend._developer, "commit", side_effect=_commit_second_call_fails):
            with pytest.raises(AuditSinkUnavailable):
                developer.create_collection("things", {"id": "integer"}, request_id=probe_request_id)
        backend._developer.rollback()

        events = durable.events()
        outcomes = [row[APPLICATION_AUDIT_FIELDS.index("outcome")] for row in events]
        # Review m-2 (minor, folded into "全件必須"): fixes the TOTAL row
        # count, not merely the presence of one of each -- a regression
        # that silently wrote a THIRD row (WP-2(a) review's own original
        # "欠陥1" shape) would slip past `count("allow") == 1`/`count(
        # "error") == 1` alone if the third row carried some OTHER outcome
        # value, but never past an exact `sorted(...)` equality.
        assert sorted(outcomes) == ["allow", "error"]
        # Review M-2 ("完全案"): the allow row and its paired error row
        # must carry the SAME request_id -- D-2's own identification rule
        # ("同一 request_id に allow 行と error 行が両方あるとき...") is
        # only executable against real data once both rows actually carry
        # a real, non-None, matching value.
        request_ids = [row[APPLICATION_AUDIT_FIELDS.index("request_id")] for row in events]
        assert request_ids == [probe_request_id, probe_request_id]
    finally:
        backend.close()
        clean_application_audit(platform)


def test_error_row_write_failure_makes_the_response_service_unavailable(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """Even when the error-row write ITSELF also fails, the response is
    still `AuditSinkUnavailable` -- best-effort from the caller's own
    point of view (D-2's own documented rule)."""
    clean_application_audit(platform)

    class _CommitFailedFailingSink(PostgresApplicationAuditSink):
        def append(self, **kwargs):
            if kwargs.get("outcome") == "error":
                raise RuntimeError("error-row write also fails")
            return super().append(**kwargs)

    durable = _CommitFailedFailingSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        real_commit = backend._developer.commit
        calls = {"n": 0}

        def _commit_second_call_fails():
            calls["n"] += 1
            if calls["n"] >= 2:
                raise psycopg.OperationalError("simulated")
            return real_commit()

        with patch.object(backend._developer, "commit", side_effect=_commit_second_call_fails):
            with pytest.raises(AuditSinkUnavailable):
                developer.create_collection("things", {"id": "integer"})
        backend._developer.rollback()
    finally:
        backend.close()
        clean_application_audit(platform)


def test_http_response_request_id_matches_the_durable_audit_row(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M-2 (major, supervisor ruling 2026-09-03, "完全案"): the
    REAL end-to-end proof -- a real HTTP request through the real
    `main.build_app` composition, whose `x-request-id` response header
    (`http.py::RequestByteBoundMiddleware`, generated once per request)
    must equal the `request_id` column on the durable row that SAME
    request's own schema change produces. This is the property D-2's own
    identification rule and the contract's `audit.fields.request_id`
    depend on -- distinct from the in-process tests above (which prove
    the allow/error PAIRING is internally consistent even with `None`);
    this one proves the value is the ACTUAL HTTP request id, not merely
    "the same one twice"."""
    clean_application_audit(platform)
    write_store = PostgresCredentialStore(platform.controlplane_dsn, pepper=_APP_PEPPER, schema=platform.schema)
    try:
        # Phase 6 WP-3 (design D-1(d)): `issue`'s second element is now
        # the complete bearer -- used verbatim.
        credential_id, bearer = write_store.issue(timeout_probe_app.app_id, Role.DEVELOPER)
    finally:
        write_store.close()

    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        # Q4 phase: `platform`'s own seeded `surfaces` declaration
        # includes `control` -- F-6 requires this process' own declared
        # status to agree with that.
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    collection_name = "reqidprobe" + secrets.token_hex(3)

    async def _call(app: Any) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://reqid-probe.invalid") as client:
            return await client.post(
                "/v1/schema/operations",
                json={"operation": "create_entity", "entity": collection_name, "fields": ["id"]},
                headers={"authorization": f"Bearer {bearer}"},
            )

    with _closing_build_app(main_module, env, monkeypatch) as app:
        response = asyncio.run(_call(app))
    assert response.status_code == 200, response.text
    http_request_id = response.headers["x-request-id"]
    assert http_request_id

    reader = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    events = reader.events()
    schema_rows = [e for e in events if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "schema_change"]
    assert len(schema_rows) == 1
    assert schema_rows[0][APPLICATION_AUDIT_FIELDS.index("request_id")] == http_request_id
    clean_application_audit(platform)


def test_http_service_durably_audits_a_nul_locator_as_auth_invalid_not_503(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 3,
    review F4), mirroring `r2db-api/tests/test_credential_persistence.py::
    test_nul_locator_over_real_http_is_401_and_durably_audited_not_503_
    silent` one-for-one: before `credential_wire.split_bearer_locator`'s
    own NUL-byte check existed, a bearer with a NUL (U+0000) byte in
    either locator half would have reached `psycopg` as a real query
    parameter deep inside `credential_store_postgres.
    PostgresCredentialStore.authenticate` -- psycopg refuses a NUL-bearing
    `text` parameter outright, which that method's own generic `except
    psycopg.Error` maps to `AuthorizationStateUnavailable` (503,
    `AUTH_STATE_UNAVAILABLE`), a client-triggerable state-unavailable
    response `audit_dispatch.DURABLE_DENIAL_CODES` does not include -- so
    the denial would never reach the durable sink at all (SI-14
    regression). `split_bearer_locator` now rejects a NUL in either half
    BEFORE any lookup, exactly like the other 3 malformed shapes -- this
    test fixes both halves of that regression over REAL HTTP (`main.
    build_app`'s own composition, not `HttpService` built by hand) + REAL
    PostgreSQL: (1) the response is `401 AUTH_INVALID`, never `503`; (2)
    the denial reaches the durable `application_audit` sink as exactly
    ONE `authentication_denied`/`AUTH_INVALID` row -- both NUL-bearing
    locators route through `credential_store_postgres.py`'s own pre-auth
    `_route_denial(application_id=None, credential_id=None,
    operation="authenticate", ...)` branch, so (unlike two DIFFERENT
    malformed credential ids) they coalesce into the SAME durable-denial
    key within one coalescing window (`test_postgres_credential_store_
    authentication_denial_is_durably_coalesced`'s own established
    property, exercised here over real HTTP instead of the store
    directly) -- hence a clean-slate delta of exactly +1, not +2; (3)
    `actor_id`/`target_id` stay `None` (review B-1's "never record the
    client-claimed id" discipline, unaffected by this fix)."""
    clean_application_audit(platform)
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        # Q4 phase: `platform`'s own seeded `surfaces` declaration
        # includes `control` -- F-6 requires this process' own declared
        # status to agree with that.
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }

    async def _call(app: Any, locator: str) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://nul-probe.invalid") as client:
            return await client.get("/v1/capabilities", headers={"authorization": f"Bearer {locator}"})

    with _closing_build_app(main_module, env, monkeypatch) as app:
        for locator in ("crd_\x00nulid.secret", "crd_nulid.sec\x00ret"):
            response = asyncio.run(_call(app, locator))
            assert response.status_code == 401, f"NUL locator {locator!r} returned {response.status_code}, not 401: {response.text}"
            assert response.json()["code"] == "AUTH_INVALID"

    reader = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    events = reader.events()
    denial_rows = [e for e in events if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "authentication_denied"]
    assert len(denial_rows) == 1, f"expected exactly one coalesced durable denial row, got {denial_rows!r}"
    assert denial_rows[0][APPLICATION_AUDIT_FIELDS.index("reason_code")] == "AUTH_INVALID"
    assert denial_rows[0][APPLICATION_AUDIT_FIELDS.index("actor_id")] is None
    assert denial_rows[0][APPLICATION_AUDIT_FIELDS.index("target_id")] is None
    clean_application_audit(platform)


def test_simulated_process_loss_leaves_the_allow_row_alone(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """§9.2 property 9's own documented limit: a crash BETWEEN the durable
    pre-commit write and the backend's own commit leaves an `allow` row
    with no paired `error` row -- this is the DESIGNED behaviour, not a
    defect. Simulated here by calling `pre_commit()` directly and never
    calling `commit_failed()`/committing the data change at all (modelling
    the process disappearing at exactly that point)."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    hook = router.make_pre_commit_hook(
        event_class="schema_change", request_id=str(uuid.uuid4()), application_id=app_a.app_id,
        actor_type="application_credential", actor_id="dev-1", role="developer", operation="create_collection",
        target_kind="collection", target_id="things",
    )
    hook.pre_commit()
    # Process "crashes" here -- commit_failed() is never called.
    events = durable.events()
    assert len(events) == 1
    assert events[0][APPLICATION_AUDIT_FIELDS.index("outcome")] == "allow"
    clean_application_audit(platform)


def test_in_memory_and_postgres_application_audit_sinks_have_parity(platform: types.SimpleNamespace) -> None:
    in_memory = ApplicationAuditSink()
    postgres = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    clean_application_audit(platform)
    shared_kwargs = dict(
        request_id="r1", application_id="a", actor_type="application_credential", actor_id="c1", role="developer",
        target_kind="collection", target_id="t",
    )
    in_memory.append(event_class="schema_change", operation="create_collection", outcome="allow", **shared_kwargs)
    postgres.append(event_class="schema_change", operation="create_collection", outcome="allow", **shared_kwargs)
    in_memory_events = in_memory.events()
    postgres_events = postgres.events()
    assert len(in_memory_events) == len(postgres_events) == 1
    assert in_memory_events[0].event_class == postgres_events[0][APPLICATION_AUDIT_FIELDS.index("event_class")]
    assert in_memory_events[0].outcome == postgres_events[0][APPLICATION_AUDIT_FIELDS.index("outcome")]
    clean_application_audit(platform)


def test_in_memory_and_postgres_backends_have_pre_commit_hook_parity(app_a: types.SimpleNamespace) -> None:
    """D-10: both `SQLiteBackend` and `PostgresBackend` call `audit_hook.
    pre_commit()` as the last thing before their own commit point, for
    `create_collection`/`add_field`/`delete`."""
    for backend in (SQLiteBackend(), make_backend(app_a)):
        try:
            sink = ApplicationAuditSink()
            sink.inject_fault(RuntimeError("sink down"))
            router = make_router(sink)
            hook = router.make_pre_commit_hook(
                event_class="schema_change", request_id=None, application_id="a", actor_type="application_credential",
                actor_id="c1", role="developer", operation="create_collection", target_kind="collection", target_id="things",
            )
            with pytest.raises(AuditSinkUnavailable):
                backend.create_collection("things", {"id": "integer"}, audit_hook=hook)
            assert backend.schema_count() == 0
        finally:
            backend.close()


# ===========================================================================
# Denial coalescing / dispatch through the REAL authentication paths
# (auth.CredentialStore + credential_store_postgres.PostgresCredentialStore)
# ===========================================================================


def test_in_memory_credential_store_authentication_denial_is_durably_coalesced() -> None:
    sink = ApplicationAuditSink()
    router = make_router(sink)
    store = CredentialStore("x" * 16, audit_router=router)
    store.provision_application("appone")
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            store.authenticate("unknown-cred.wrong-secret")
    events = sink.events()
    assert len(events) == 1
    assert events[0].reason_code == "AUTH_INVALID"
    assert events[0].event_class == "authentication_denied"
    # Review B-1 (blocker, supervisor ruling 2026-09-03): a pre-auth
    # denial (unknown credential_id) must never record the client-claimed
    # id as actor_id/target_id.
    assert events[0].actor_id is None
    assert events[0].target_id is None
    assert events[0].application_id is None


def test_postgres_credential_store_authentication_denial_is_durably_coalesced(platform: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    store = PostgresCredentialStore(platform.api_dsn, pepper=_APP_PEPPER, schema=platform.schema, audit_router=router)
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            store.authenticate("unknown-cred.wrong-secret")
    events = durable.events()
    assert len(events) == 1
    assert events[0][APPLICATION_AUDIT_FIELDS.index("reason_code")] == "AUTH_INVALID"
    assert events[0][APPLICATION_AUDIT_FIELDS.index("actor_id")] is None
    assert events[0][APPLICATION_AUDIT_FIELDS.index("target_id")] is None
    clean_application_audit(platform)


def test_rotating_unknown_credential_ids_still_coalesce_into_one_durable_row_in_memory() -> None:
    """Review B-1 (blocker): an attacker who varies the CLAIMED credential_
    id on every attempt must not be able to defeat D-3 coalescing -- since
    the pre-auth branch never lets the claimed id into the coalescing key,
    500 distinct ids collapse into the SAME `(None, "unknown",
    "authenticate", "AUTH_INVALID")` window regardless."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    store = CredentialStore("x" * 16, audit_router=router)
    store.provision_application("appone")
    for i in range(500):
        with pytest.raises(AuthenticationError):
            store.authenticate(f"rotating-cred-{i}.wrong-secret")
    events = sink.events()
    # First-occurrence row (count=None) only -- the window has not been
    # flushed, so the window-end summary row does not exist yet either;
    # in-process the bound is "at most 2 rows per process per window"
    # (first-occurrence + eventual summary), never "one row per attempt".
    assert len(events) <= 2
    assert all(e.actor_id is None for e in events)


def test_rotating_unknown_credential_ids_still_coalesce_into_one_durable_row_postgres(platform: types.SimpleNamespace) -> None:
    """Same property as the in-memory test above, against the REAL
    production credential store (`credential_store_postgres.
    PostgresCredentialStore`) and a real durable sink -- 500 attempts,
    each with a DIFFERENT claimed credential_id, must produce at most 2
    durable rows for the whole process/window, never 500."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    store = PostgresCredentialStore(platform.api_dsn, pepper=_APP_PEPPER, schema=platform.schema, audit_router=router)
    for i in range(500):
        with pytest.raises(AuthenticationError):
            store.authenticate(f"rotating-cred-{i}.wrong-secret")
    events = durable.events()
    assert len(events) <= 2
    for row in events:
        assert row[APPLICATION_AUDIT_FIELDS.index("actor_id")] is None
    clean_application_audit(platform)


def test_an_over_long_credential_id_does_not_suppress_the_durable_denial_row(platform: types.SimpleNamespace) -> None:
    """Review B-1 (blocker): before this fix, a 300-character claimed
    credential_id would be written verbatim into `actor_id`/`target_id`,
    which exceeds migration 0005's own `application_audit_len_actor_id`/
    `_len_target_id` `CHECK (length(...) <= 256)` constraints -- making
    the first-occurrence INSERT itself fail deterministically and
    flipping the response from `AUTH_INVALID` to `SERVICE_UNAVAILABLE`
    under pure attacker control (no server misconfiguration involved).
    After the fix, the claimed id never reaches the durable row at all
    (pre-auth -> `actor_id=None`/`target_id=None`), so an over-long id has
    no effect on either the response code or the durable write."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    store = PostgresCredentialStore(platform.api_dsn, pepper=_APP_PEPPER, schema=platform.schema, audit_router=router)
    over_long_id = "x" * 300
    with pytest.raises(AuthenticationError):
        store.authenticate(f"{over_long_id}.wrong-secret")
    events = durable.events()
    assert len(events) == 1
    assert events[0][APPLICATION_AUDIT_FIELDS.index("reason_code")] == "AUTH_INVALID"
    assert events[0][APPLICATION_AUDIT_FIELDS.index("actor_id")] is None
    assert events[0][APPLICATION_AUDIT_FIELDS.index("target_id")] is None
    clean_application_audit(platform)


def test_an_over_long_credential_id_does_not_flip_the_response_to_service_unavailable_in_memory() -> None:
    """In-memory counterpart -- no length CHECK exists in-memory, but this
    fixes the RESPONSE-CODE behaviour (never `SERVICE_UNAVAILABLE`/
    `AuditSinkUnavailable`) independent of any real database."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    store = CredentialStore("x" * 16, audit_router=router)
    store.provision_application("appone")
    over_long_id = "x" * 300
    with pytest.raises(AuthenticationError):
        store.authenticate(f"{over_long_id}.wrong-secret")
    events = sink.events()
    assert len(events) == 1
    assert events[0].actor_id is None


def test_postgres_credential_store_is_the_actual_production_wiring() -> None:
    """Doubt recorded in this WP's own report: `main.build_app` wires
    `credential_store_postgres.PostgresCredentialStore`, not `auth.
    CredentialStore` -- fixed here so a future refactor that silently
    reverts that wiring (and, with it, this WP's own durable-denial
    coverage of the real deployed authentication path) is caught."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    source = (src_dir / "main.py").read_text()
    assert "PostgresCredentialStore(" in source
    assert "audit_router=audit_router" in source


# ===========================================================================
# Acceptance-audit evidence round 2 (2026-09-03): (1) durable observability
# of the M-3/m-1 emit sites, (2) buffer-class request_id <-> HTTP
# x-request-id, (3) overflow reachable from the real emit path (completion
# condition 27), (4) completion condition 25's own literal test name.
# ===========================================================================


def test_application_scope_denied_is_durably_recorded() -> None:
    """Evidence gap (1): `_require_data`'s "application scope denied"
    `FORBIDDEN` (cell.py, review M-3) must be durably OBSERVABLE, not
    merely present in the diff -- a principal whose own `application_id`
    does not match the cell it is used against is SI-00's own
    application-boundary denial, the single most evidence-worthy
    `FORBIDDEN` this peer can produce."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    cell = ApplicationCell("appone", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    foreign_principal = Principal(application_id="othertenant", credential_id="c1", role=Role.RUNTIME)
    with pytest.raises(AuthorizationError):
        cell.insert(foreign_principal, "things", {"id": 1})
    forbidden_rows = [e for e in sink.events() if e.reason_code == "FORBIDDEN"]
    assert len(forbidden_rows) == 1
    assert forbidden_rows[0].application_id == "appone"  # the cell's own (victim) scope
    assert forbidden_rows[0].event_class == "authorization_denied"


def test_role_denied_is_durably_recorded() -> None:
    """Evidence gap (1): `_require_data`'s "role denied" `FORBIDDEN`
    (cell.py, review M-3) -- a principal whose `role` is neither
    `Role.RUNTIME` nor `Role.DEVELOPER` (a forged/corrupted session,
    since `auth.Principal` is a plain, unvalidated dataclass -- the same
    forging technique the in-process conformance adapter's own negative
    tests already use, `conformance_adapter_mitatedb.py:1290/1302`)."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    cell = ApplicationCell("appone", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    bogus_role_principal = Principal(application_id="appone", credential_id="c1", role="auditor")
    with pytest.raises(AuthorizationError):
        cell.insert(bogus_role_principal, "things", {"id": 1})
    forbidden_rows = [e for e in sink.events() if e.reason_code == "FORBIDDEN"]
    assert len(forbidden_rows) == 1
    assert forbidden_rows[0].actor_id == "c1"


def test_auth_required_is_durably_recorded() -> None:
    """Evidence gap (1)/m-1: `HttpService.authenticate`'s own
    `AUTH_REQUIRED` emit site (http.py, review m-1) -- no bearer token
    presented at all, the ONLY call site in this peer that can ever
    durably record this code (it never reaches any credential store)."""
    from mitatedb_api.http import HttpService

    sink = ApplicationAuditSink()
    router = make_router(sink)
    service = HttpService(CredentialStore("x" * 16), lambda application_id: None, audit_router=router)
    with pytest.raises(Exception):  # `http._CredentialMissing`, a private class
        service.authenticate(None, request_id="req-probe")
    events = sink.events()
    assert len(events) == 1
    assert events[0].reason_code == "AUTH_REQUIRED"
    assert events[0].request_id == "req-probe"
    assert events[0].actor_id is None


def test_http_buffer_class_event_request_id_matches_the_durable_audit_row(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence gap (2): the fail-closed (pre-commit hook) path already
    has this proof (`test_http_response_request_id_matches_the_durable_
    audit_row`, schema_change). This is the BUFFER-class counterpart
    (P4-D5's own new `data_operation` emit site, `insert`) -- a real HTTP
    mutation's own `x-request-id` must equal the `request_id` column on
    the durable row that SAME request's buffered event becomes, once
    flushed."""
    clean_application_audit(platform)
    write_store = PostgresCredentialStore(platform.controlplane_dsn, pepper=_APP_PEPPER, schema=platform.schema)
    try:
        # Phase 6 WP-3 (design D-1(d)): `issue`'s second element is now
        # the complete bearer -- used verbatim.
        credential_id, bearer = write_store.issue(timeout_probe_app.app_id, Role.DEVELOPER)
    finally:
        write_store.close()

    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        # Q4 phase: `platform`'s own seeded `surfaces` declaration
        # includes `control` -- F-6 requires this process' own declared
        # status to agree with that.
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    collection_name = "bufreqid" + secrets.token_hex(3)

    router_cls, router_captured = _capturing_subclass(main_module.AuditRouter)
    credential_store_cls, credential_store_captured = _capturing_subclass(main_module.PostgresCredentialStore)
    cell_instances: list = []
    real_cell_init = main_module.ApplicationCell.__init__

    def _capturing_cell_init(self, *args, **kwargs):
        real_cell_init(self, *args, **kwargs)
        cell_instances.append(self)

    monkeypatch.setattr(main_module, "AuditRouter", router_cls)
    monkeypatch.setattr(main_module, "PostgresCredentialStore", credential_store_cls)
    monkeypatch.setattr(main_module.ApplicationCell, "__init__", _capturing_cell_init)
    try:
        app = main_module.build_app(env)

        async def _call() -> tuple[httpx.Response, httpx.Response]:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bufreqid-probe.invalid") as client:
                schema_response = await client.post(
                    "/v1/schema/operations",
                    json={"operation": "create_entity", "entity": collection_name, "fields": ["id"]},
                    headers={"authorization": f"Bearer {bearer}"},
                )
                mutate_response = await client.post(
                    f"/v1/data/{collection_name}/mutations",
                    # `create_entity`'s own "name-only fields -> text"
                    # mapping (http.py) means `id` here is a TEXT column,
                    # not integer -- a string value matches its real type.
                    json={"operations": [{"operation": "insert", "values": {"id": "1"}}]},
                    headers={"authorization": f"Bearer {bearer}"},
                )
                return schema_response, mutate_response

        schema_response, mutate_response = asyncio.run(_call())
        assert schema_response.status_code == 200, schema_response.text
        assert mutate_response.status_code == 200, mutate_response.text
        http_request_id = mutate_response.headers["x-request-id"]
        assert http_request_id

        router_captured["instance"].flush()
    finally:
        monkeypatch.setattr(main_module.ApplicationCell, "__init__", real_cell_init)
        store = credential_store_captured.get("instance")
        if store is not None:
            store.close()
        for cell in cell_instances:
            cell._backend.close()

    reader = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    events = reader.events()
    # HTTP mutations always go through `session.transact()` (`http.py::
    # post_mutate` -- there is no dedicated single-insert HTTP endpoint on
    # this peer), so the buffer-class emit this request produces carries
    # `operation="transact"` (`cell.py::transact`'s own non-destructive
    # buffer-class push), not `"insert"` -- `"insert"` is only the emitted
    # value for the DEDICATED `ApplicationCell.insert` Python-level method
    # (exercised directly, not via HTTP, by `test_query_insert_and_
    # update_success_events_are_durably_recorded` above).
    data_op_rows = [e for e in events if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "data_operation"
                    and e[APPLICATION_AUDIT_FIELDS.index("operation")] == "transact"]
    assert len(data_op_rows) == 1
    assert data_op_rows[0][APPLICATION_AUDIT_FIELDS.index("request_id")] == http_request_id
    clean_application_audit(platform)


def test_buffer_overflow_is_reachable_from_the_real_emit_path() -> None:
    """Completion condition 27 (work order literal name): `push_buffer_
    event` is an internal dispatch primitive the overflow tests above
    call directly -- this test proves the SAME property from the actual
    PUBLIC emit path (real `insert` calls through `cell.py`/P4-D5's own
    new emit site), not a direct call to the buffer's own internals, so a
    regression that broke the wiring BETWEEN `cell.py`'s operations and
    `AuditRouter.push_buffer_event` (while leaving `push_buffer_event`
    itself correct) would still be caught here."""
    class _FlushAlwaysFailsSink(ApplicationAuditSink):
        def append_many(self, events):
            raise RuntimeError("flush always fails")

    sink = _FlushAlwaysFailsSink()
    router = make_router(sink, buffer_capacity=2, alert_min_interval_s=0.0)
    cell = ApplicationCell("appone", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    developer = make_developer(cell, "appone")
    developer.create_collection("things", {"id": "integer"})
    runtime = make_runtime(cell, "appone")
    for i in range(5):
        runtime.insert("things", {"id": i})
    alert_rows = [e for e in sink.events() if e.event_class == "security_control_failure"]
    assert alert_rows, "5 real insert() calls against a capacity-2, always-failing-flush buffer must reach overflow"
    for row in alert_rows:
        assert row.reason_code == "audit_buffer_overflow"
        assert row.operation == "audit_buffer"
        assert row.target_kind == "audit_sink"


def test_backend_commit_failure_is_classified_and_produces_an_error_row(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """Completion condition 25 (work order's own literal test name,
    absent from the acceptance audit's diff -- added here verbatim).
    `backend_postgres.PostgresBackend`'s `commit()` used to run in an
    `else:` clause OUTSIDE the `try`/`except` (review M-6) -- a commit
    failure there escaped as a raw, UNCLASSIFIED `psycopg.Error`, never
    reaching this peer's own `errors.FoundationError` hierarchy. Fixes
    BOTH halves of "classified AND produces an error row": (i) the
    exception the caller actually sees is `errors.AuditSinkUnavailable`
    (a real, classified `FoundationError` -- never a bare `psycopg.
    Error`), and (ii) a durable `outcome=\"error\"` row exists.
    `test_failed_data_commit_writes_an_error_row_for_the_same_request_id`
    additionally pins the same-request_id pairing (M-2); this is the
    narrower, literally-named check."""
    clean_application_audit(platform)
    sink = ApplicationAuditSink()
    router = make_router(sink)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        real_commit = backend._developer.commit
        calls = {"n": 0}

        def _commit_second_call_fails():
            calls["n"] += 1
            if calls["n"] >= 2:
                raise psycopg.OperationalError("simulated commit failure")
            return real_commit()

        with patch.object(backend._developer, "commit", side_effect=_commit_second_call_fails):
            with pytest.raises(AuditSinkUnavailable) as excinfo:
                developer.create_collection("things", {"id": "integer"})
        assert not isinstance(excinfo.value, psycopg.Error), "the caller must see a CLASSIFIED FoundationError, never a raw psycopg.Error"
        backend._developer.rollback()

        error_rows = [e for e in sink.events() if e.outcome == "error"]
        assert len(error_rows) == 1
        assert error_rows[0].reason_code == "commit_failed"
    finally:
        backend.close()
        clean_application_audit(platform)
