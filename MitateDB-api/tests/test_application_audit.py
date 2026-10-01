"""Phase 4 WP-3(a): the durable application-plane audit sink -- migration
`0005_application_audit.sql`, the 13-column (+`count`) emitter pair
(`application_audit.ApplicationAuditSink`/`PostgresApplicationAuditSink`),
the pre-commit hook (`audit_hook.py`, wired through `backend_postgres.py`/
`backend_sqlite.py`/`cell.py`), the dispatch rules in `audit_dispatch.py`
(fail-closed vs. coalesced-denial vs. non-durable, wired through
`cell.py`/`auth.py`/`credential_store_postgres.py`), the synchronous write of
an ordinary event, and the two writer-connection timeouts -- tested against
real PostgreSQL (design R-8: must not be skipped) and, where real-
PostgreSQL realism is not the point of the test, against the pure
in-memory dispatch machinery (`audit_dispatch.AuditRouter` +
`application_audit.ApplicationAuditSink`), which lets the dispatch/
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
import os
import secrets
import json
import subprocess
import tempfile
import threading
import time
import types
import uuid
from datetime import datetime, timedelta, timezone
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
                               ApplicationRuntime, Filter, _delete_confirmation_phrase,
                               _LimitStateHolder)
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import (AuditSinkUnavailable, AuthenticationError,
                                 AuthorizationError, DestructiveConfirmationRequired,
                                 FoundationError)
from mitatedb_api.pg_timeouts import ms_from_pg_timeout_text
from mitatedb_api import pool as pool_module
from mitatedb_api.pool import BoundedConnectionPool

from .scoped_backend import commits_failing, scoped

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
# `main.build_app` requires `MITATEDB_WORKERS`/`MITATEDB_SLOT_DIR`: one
# shared, real slot directory (mode 0700, `mkdtemp`'s own default) for
# every `build_app(env)` call in this module, mirroring a single-process
# (`workers=1`) deployment.
_SLOT_DIR = tempfile.mkdtemp(prefix="mitatedb-test-slots-application-audit-")

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
    # Sets a role-level `statement_timeout` on `mitatedbsvc_auditreader`
    # and every application's own runtime/developer role -- names
    # `mitatedbsvc_auditreader` directly, so the fixture applies it AFTER
    # 0005 (which creates that role), not right after 0012 like the
    # other migrations above.
    "0013_role_statement_timeouts.sql",
    # design D-3 (1): `main.build_app` always wires the PostgreSQL-backed
    # `requests_per_minute` rate row -- applied right after 0011, before
    # the 0005 GRANT-invariance snapshot below.
    "0016_credential_request_rate.sql",
    # the refusal-window counter and its function: every refusal's count is
    # written through it. Depends on 0005 (`application_audit`, the
    # `auditreader` role), so the fixture applies it right after 0005.
    "0017_denial_window_counter.sql",
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
        _run_psql(provision_dsn, rewritten["0016_credential_request_rate.sql"])
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
        _run_psql(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])
        _run_psql(provision_dsn, rewritten["0017_denial_window_counter.sql"])
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
            cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(platform.schema, "denial_window_counter")))
    finally:
        conn.close()


# ===========================================================================
# Role-level statement_timeout (0013) reaches the catalog path's own
# developer connection
# ===========================================================================


def test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout(
    timeout_probe_app: types.SimpleNamespace,
) -> None:
    """`PostgresBackend.all_field_types`/`.all_field_constraints` -- the
    storage this application's `GET /v1/catalog` reads -- run on a
    developer-pool connection (`backend_postgres.py`). `0013_role_statement_
    timeouts.sql` bounds that role with a role-level `ALTER ROLE ... SET
    statement_timeout = '5000ms'`. This reads the EFFECTIVE value straight
    off a connection of the pool `PostgresBackend` borrows that path's
    connections from (`pg_settings.setting`, never `pg_roles.rolconfig`/
    `pg_db_role_setting`'s own declaration) -- proof the session the
    catalog path actually runs in carries the bound, not merely that the
    role declares one.

    A request scope sets `statement_timeout`/`lock_timeout` with `SET
    LOCAL` when it opens (`request_scope`); the second half below reads
    the SAME role-level value a SECOND time, this time AFTER a real scope
    on a DIFFERENT backend -- proof the per-transaction `SET LOCAL` does
    not leak past its own transaction onto the connection the next request
    borrows."""
    backend = make_backend(timeout_probe_app)
    try:
        conn = backend._developer_pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                statement_timeout = cur.fetchone()[0]
        finally:
            backend._developer_pool.release(conn)
    finally:
        backend.close()
    assert statement_timeout == "5000"

    # A `SET LOCAL` issued when a request scope opens must not leak past
    # the scope: the connection goes back to its pool and the next borrower
    # sees the role-level value again. Constructed with a value (1234)
    # distinct from the role-level `statement_timeout` default (5000) -- if
    # it leaked, `statement_timeout` would read back as `1234` after the
    # call. The comparison is against a BASELINE read on a connection of
    # the same pool, taken BEFORE any catalog call, never a hardcoded
    # cluster-default literal (`lock_timeout`'s own role-level absence is
    # whatever this cluster's own global default is, not necessarily `0`
    # on every cluster) -- so this test does not depend on this cluster's
    # particular defaults, only on "before" and "after" agreeing.
    probe_backend = PostgresBackend(
        timeout_probe_app.runtime_dsn, timeout_probe_app.developer_dsn, max_execution_ms=1234,
    )
    try:
        def _settings() -> tuple[str, str]:
            conn = probe_backend._developer_pool.acquire()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                    statement = cur.fetchone()[0]
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'lock_timeout'")
                    lock = cur.fetchone()[0]
                return statement, lock
            finally:
                probe_backend._developer_pool.release(conn)

        baseline_statement_timeout, baseline_lock_timeout = _settings()
        scoped(probe_backend).schema_count()
        after_statement_timeout, after_lock_timeout = _settings()
    finally:
        probe_backend.close()
    assert after_statement_timeout == baseline_statement_timeout, (
        after_statement_timeout, baseline_statement_timeout)
    assert after_lock_timeout == baseline_lock_timeout, (after_lock_timeout, baseline_lock_timeout)
    # Independent sanity check that this comparison is not vacuous against
    # a cluster where `max_execution_ms` itself happens to equal the
    # role-level default: the constructed value (1234) never appears.
    assert baseline_statement_timeout != "1234"
    assert after_statement_timeout != "1234"


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
        # The refusal-window counter's migration runs after 0005 (it needs
        # `application_audit` and the reader role): its one new table is
        # held by its owner and readable by the reader, nobody else.
        if table.endswith(".denial_window_counter") and grantee in (platform.provision_role, platform.auditreader_role):
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
        PostgresApplicationAuditSink(
            "host=/tmp port=1 dbname=mitatedb_application_audit_sink_statement_timeout_unreachable",
            statement_timeout_ms=1000,
        )
    with pytest.raises(TypeError):
        PostgresApplicationAuditSink(
            "host=/tmp port=1 dbname=mitatedb_application_audit_sink_idle_timeout_unreachable",
            idle_in_transaction_session_timeout_ms=1000,
        )


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
            "MITATEDB_WORKERS": "1",
            "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
    py`'s, always applies it). Lowering it below its own real floor (2
    stores x `role_pool_size(thread_limit)` 6 x `process_ceilings.data`
    1 = 12, design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5), with
    `MITATEDB_THREAD_LIMIT` unset -> `DEFAULT_THREAD_LIMIT` 4) -- here to
    10 -- must raise, never silently start a process that can hit
    PostgreSQL's own hard 'too many connections for role' refusal under
    real concurrent traffic. Restores the migration-seeded limit (68) in a
    `finally` so this shared, module-scoped `platform` fixture is left
    healthy for every other test in this file."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(sql.Identifier(platform.api_role)))
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


def test_build_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-91 (work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_
    HEADROOM_CHECK_V1.md §1.2 D-3, completion condition 10, peer-symmetric
    with r2db-api's own same-numbered test): unlike F-16 (this file's own
    test just above), this new startup check is run UNSCOPED --
    `platform.api_role`'s own `CONNECTION LIMIT` is left healthy (F-16
    alone would pass), but the declared `process_ceilings` (`{"data": 1,
    "control": 30}`, lower bound 1*(12+12)+30*16=504 with `pool_size` 6
    -- design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5):
    `role_pool_size(thread_limit)`, never the declared `concurrency` --
    `timeout_probe_app` guarantees at least one registered application)
    exceeds this throwaway cluster's own real headroom (297, §1.3 (8));
    `data` stays 1 so this startup's own `api`-scoped F-16 floor (12)
    still passes. Mutation M9c
    (dropping this startup call from `mitatedb_api.main.build_app`) turns
    this red."""
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform.schema,
        "MITATEDB_SERVE_APPS": timeout_probe_app.app_id,
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    with psycopg.connect(platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({"data": 1, "control": 30})],
            )
        conn.commit()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            main_module.build_app(env)
        assert excinfo.value.code == "F-18"
    finally:
        with psycopg.connect(platform.provision_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()
        # Non-空振り: the restore above is really what makes
        # `build_app` healthy again.
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
            "MITATEDB_WORKERS": "1",
            "MITATEDB_SLOT_DIR": _SLOT_DIR,
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


class _SinkClock:
    """The in-memory sink's clock, as a `datetime` a test moves by hand.
    Starts on a whole minute in 2001 UTC, so every window a test opens
    closes long before the wall clock the reader compares against."""

    def __init__(self) -> None:
        self.now = datetime(2001, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _refuse(router: AuditRouter, **overrides: Any) -> None:
    """One durable refusal (`AUTH_INVALID`, no application, no actor) through
    the router, the way a credential store routes it."""
    fields: dict[str, Any] = dict(
        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=None,
        application_id=None, actor_type="unknown", actor_id=None, role=None,
        operation="authenticate", target_kind="credential", target_id=None,
    )
    fields.update(overrides)
    router.route_denial(**fields)


def _summaries_closed_by(sink: ApplicationAuditSink, closed_before: datetime) -> "list[ApplicationAuditEvent]":
    """The summary event of every window that ended before `closed_before`."""
    return [event for event, _window_end in sink.denial_window_summaries(closed_before=closed_before)]


def test_dispatch_point_is_the_destructive_confirmation_choke() -> None:
    """§9.2 property 6: the SAME `_validate_delete_confirmation` choke
    both `ApplicationCell.delete` and `transact`'s pass-1 planning loop
    (`_plan_operation`) call is what determines a batch's event class
    (`destructive_data_operation` vs. `data_operation`) -- not the caller's
    own `event_class`. Fixed here by source inspection: a
    single call site name, used by both the dedicated and batch-embedded
    paths."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    source = (src_dir / "cell.py").read_text()
    assert source.count("def _validate_delete_confirmation(") == 1
    assert source.count("self._validate_delete_confirmation(") == 2  # delete() and _plan_operation()


def test_the_router_keeps_no_denial_window_of_its_own() -> None:
    """The counting state is not held in the service process: neither the
    coalescer class nor the sweep that drained it exists, and a router built
    with a sink holds no per-key table."""
    import mitatedb_api.audit_dispatch as dispatch_module

    assert not hasattr(dispatch_module, "_DenialCoalescer")
    router = make_router()
    assert not hasattr(router, "_coalescer")
    assert not hasattr(router, "flush")


def test_repeated_invalid_secret_counts_n_repeats_once_in_the_windows_summary() -> None:
    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    router = make_router(sink)
    n_repeats = 49
    for _ in range(1 + n_repeats):
        _refuse(router, actor_id="leaked-cred", target_id="leaked-cred")

    # Only the first refusal is a row; the repeats are counted, not written.
    events = sink.events()
    assert len(events) == 1
    assert events[0].count is None

    # While the window is open it has no summary; once it has closed it has
    # exactly one, with one identity across reads.
    assert _summaries_closed_by(sink, clock.now) == []
    clock.advance(61.0)
    summaries = _summaries_closed_by(sink, clock.now)
    assert len(summaries) == 1, f"expected the closed window's one summary event, got {summaries!r}"
    assert summaries[0].count == n_repeats
    assert [e.event_id for e in _summaries_closed_by(sink, clock.now)] == [summaries[0].event_id]
    # The first row and the summary account for every occurrence.
    assert len(events) + summaries[0].count == 1 + n_repeats


def test_a_window_with_one_repeat_has_a_summary_without_a_count_and_a_lone_refusal_has_none() -> None:
    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    router = make_router(sink)

    # n = 1: one refusal, no summary at all, even once its window has closed.
    _refuse(router, actor_id="lone")
    clock.advance(61.0)
    assert _summaries_closed_by(sink, clock.now) == []

    # n = 2: one repeat -> a summary event that carries no `count`
    # (contract: never zero or one), so the first row and the summary make 2.
    for _ in range(2):
        _refuse(router, actor_id="boundary", reason_code="FORBIDDEN", event_class="authorization_denied",
                application_id="a", actor_type="application_credential", role="runtime", operation="schema",
                target_kind="collection")
    clock.advance(61.0)
    summaries = _summaries_closed_by(sink, clock.now)
    assert len(summaries) == 1, f"expected exactly one summary (the n=2 window; the n=1 window has none), got {summaries!r}"
    assert summaries[0].count is None, f"a window with exactly one repeat must never carry count=1 -- got {summaries[0]!r}"


def test_the_window_follows_the_clock_so_refusals_across_a_boundary_are_two_first_rows() -> None:
    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    router = make_router(sink)

    clock.advance(59.0)
    _refuse(router, actor_id="edge")
    clock.advance(2.0)  # 61 s past the aligned start: the next 60 s window
    _refuse(router, actor_id="edge")

    assert len(sink.events()) == 2
    clock.advance(120.0)
    assert _summaries_closed_by(sink, clock.now) == []


def test_a_window_length_of_zero_writes_every_refusal_as_a_row() -> None:
    sink = ApplicationAuditSink()
    router = make_router(sink, denial_coalesce_window_s=0.0)
    for _ in range(3):
        _refuse(router, actor_id="zero")
    assert len(sink.events()) == 3
    assert _summaries_closed_by(sink, datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_every_refusal_of_a_window_is_fail_closed_not_only_the_first() -> None:
    """A refusal that is only counted (the window's first row is already
    written) still fails closed when the count cannot be recorded: the
    response is `AuditSinkUnavailable`, never an ordinary refusal for an
    uncounted request."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    _refuse(router, actor_id="repeat-fault")
    sink.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(AuditSinkUnavailable):
        _refuse(router, actor_id="repeat-fault")


def test_the_reader_returns_a_closed_windows_summary_and_not_an_open_one() -> None:
    from mitatedb_api.audit_query import InMemoryAuditQueryStore
    from mitatedb_api.control_audit import ControlAuditSink

    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    router = make_router(sink)
    reader = InMemoryAuditQueryStore(ControlAuditSink(), sink)

    for _ in range(4):
        _refuse(router, actor_id="reader")
    clock.advance(61.0)

    rows = reader.query(event_classes=None, after=None, limit=100, visibility_lag_ms=0)
    summaries = [row for row in rows if row["outcome"] == "deny" and row["count"] is not None]
    assert len(summaries) == 1, f"expected exactly one summary row, got {rows!r}"
    summary = summaries[0]
    assert summary["plane"] == "application"
    assert summary["count"] == 3
    assert summary["recorded_at"] == datetime(2001, 1, 1, 0, 1, 0, tzinfo=timezone.utc)

    # A window that has not closed contributes nothing. The sink's clock now
    # stands well ahead of the reader's, so the new window ends after the
    # reader's cutoff; three refusals make a summary whose count is 2, which
    # the reader would return if it did not leave open windows out.
    clock.now = datetime.now(timezone.utc) + timedelta(days=30)
    for _ in range(3):
        _refuse(router, actor_id="reader-open")
    again = reader.query(event_classes=None, after=None, limit=100, visibility_lag_ms=0)
    assert [row["event_id"] for row in again if row["count"] is not None] == [summary["event_id"]]


def test_two_window_lengths_never_share_a_window_in_memory() -> None:
    """The window length is part of the key: a refusal counted under one
    length is not added to a window another length opened."""
    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    for window_ms in (60_000, 3_600_000, 60_000):
        sink.record_denial(
            window_ms=window_ms, event_class="authorization_denied", request_id="req-len", application_id="app-len",
            actor_type="application_credential", actor_id="cred-len", role="runtime", operation="op_len",
            target_kind="collection", reason_code="FORBIDDEN",
        )
    assert len(sink.events()) == 2, "each length opened its own window and wrote its own first row"
    clock.advance(3_601.0)
    summaries = _summaries_closed_by(sink, clock.now)
    assert [(s.operation, s.count) for s in summaries] == [("op_len", None)], summaries


def test_the_memory_reader_pages_through_summary_events_and_filters_them_by_class() -> None:
    from mitatedb_api.audit_query import InMemoryAuditQueryStore
    from mitatedb_api.control_audit import ControlAuditSink

    clock = _SinkClock()
    sink = ApplicationAuditSink(clock=clock)
    reader = InMemoryAuditQueryStore(ControlAuditSink(), sink)
    for operation, event_class in (("op_a", "authorization_denied"), ("op_b", "authorization_denied"), ("op_c", "authentication_denied")):
        for _ in range(3):
            sink.record_denial(
                window_ms=60_000, event_class=event_class, request_id="req-mem", application_id="app-mem",
                actor_type="application_credential", actor_id="cred-mem", role="runtime", operation=operation,
                target_kind="collection", reason_code="FORBIDDEN",
            )
    clock.advance(61.0)
    expected = {summary.event_id for summary in _summaries_closed_by(sink, clock.now)}
    assert len(expected) == 3

    seen: list[str] = []
    after = None
    for _ in range(200):  # the walk ends long before this; a cursor-blind branch never would
        page = reader.query(event_classes=None, after=after, limit=1, visibility_lag_ms=0)
        if not page:
            break
        row = page[0]
        seen.append(row["event_id"])
        after = (row["recorded_at"], row["plane"], row["event_id"])
    else:
        pytest.fail("the walk did not end: the summary branch ignores the cursor")
    assert len(seen) == len(set(seen)), "a row was returned twice in one walk"
    assert expected <= set(seen), "a summary event was missing from the walk"

    only_authentication = reader.query(event_classes=["authentication_denied"], after=None, limit=100, visibility_lag_ms=0)
    assert {row["operation"] for row in only_authentication} == {"op_c"}, only_authentication
    assert sum(1 for row in only_authentication if row["count"] is not None) == 1


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


def test_validation_failed_denials_add_no_durable_row() -> None:
    router = make_router()
    router.route_denial(
        reason_code="VALIDATION_FAILED", event_class="authorization_denied", request_id=None, application_id="a",
        actor_type="application_credential", actor_id="c1", role="runtime", operation="query",
        target_kind="collection", target_id=None,
    )
    assert router.durable_sink.events() == ()


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
    assert scoped(cell._backend).schema_count() == 0


def test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_sqlite() -> None:
    sink = ApplicationAuditSink()
    router = make_router(sink)
    cell = _sqlite_cell(router)
    developer = make_developer(cell, "appone")
    developer.create_collection("things", {"id": "integer"})
    runtime = make_runtime(cell, "appone")
    runtime.insert("things", {"id": 1})
    sink.inject_fault(RuntimeError("sink down"))
    revision = scoped(cell._backend).schema_revision()
    from mitatedb_api.cell import _delete_confirmation_phrase
    phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
    with pytest.raises(AuditSinkUnavailable):
        runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase)
    sink.inject_fault(None)  # a read writes its own event before it answers
    rows = runtime.read("things")
    assert len(rows) == 1  # data unchanged


def _lose_the_connection_during_commit(backend: Any) -> "tuple[Any, Any]":
    """Makes the backend's commit fail as a lost connection does and its
    rollback fail too (a closed connection cannot roll back); returns the
    two real methods for the caller to put back."""
    real_commit, real_rollback = backend.commit, backend.rollback

    def _lost_commit(**kwargs: Any) -> None:
        raise psycopg.OperationalError("the connection was lost during the commit")

    def _closed_rollback(**kwargs: Any) -> None:
        raise psycopg.OperationalError("the connection is closed")

    backend.commit, backend.rollback = _lost_commit, _closed_rollback
    return real_commit, real_rollback


def test_a_batch_whose_commit_loses_the_connection_still_writes_the_error_row() -> None:
    """The commit's outcome is unknown when the connection is lost during
    it, and the rollback that follows fails on the closed connection. The
    `allow` row is already recorded, so the `error` row for the same
    request must be written all the same -- the rollback's failure does not
    skip it."""
    sink = ApplicationAuditSink()
    cell = _sqlite_cell(make_router(sink))
    make_developer(cell, "appone").create_collection("things", {"id": "integer"})
    runtime = make_runtime(cell, "appone")
    real_commit, real_rollback = _lose_the_connection_during_commit(cell._backend)
    try:
        with pytest.raises(psycopg.OperationalError):
            runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 1}}], request_id="req-lost-batch")
    finally:
        cell._backend.commit, cell._backend.rollback = real_commit, real_rollback
    rows = [(e.outcome, e.request_id) for e in sink.events() if e.operation == "transact"]
    assert sorted(rows) == [("allow", "req-lost-batch"), ("error", "req-lost-batch")], rows


def test_a_single_write_whose_commit_loses_the_connection_still_writes_the_error_row() -> None:
    sink = ApplicationAuditSink()
    cell = _sqlite_cell(make_router(sink))
    make_developer(cell, "appone").create_collection("things", {"id": "integer"})
    runtime = make_runtime(cell, "appone")
    real_commit, real_rollback = _lose_the_connection_during_commit(cell._backend)
    try:
        with pytest.raises(psycopg.OperationalError):
            runtime.insert("things", {"id": 1}, request_id="req-lost-insert")
    finally:
        cell._backend.commit, cell._backend.rollback = real_commit, real_rollback
    rows = [(e.outcome, e.request_id) for e in sink.events() if e.operation == "insert"]
    assert sorted(rows) == [("allow", "req-lost-insert"), ("error", "req-lost-insert")], rows


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
# 1-operation-1-row, the synchronous emit sites, parity.
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
        revision = scoped(cell._backend).schema_revision()
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
            scoped(cell._backend).field_domains("things")  # never created
    finally:
        backend.close()


def test_each_data_operation_adds_exactly_one_application_audit_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
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
    `transact` and `query`/`insert`/`update`/non-destructive `transact`
    (every one durable before the call returns, no flush needed) -- so a regression that left a stray
    post-commit `__record`-style SECOND durable emit on any ONE of them
    (D-10's own prohibited case (ii)) is caught by row-count arithmetic,
    not merely by the event CLASSES present."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        runtime = make_runtime(cell, app_a.app_id)

        def _count() -> int:
            return len(durable.events())

        # 1) create_collection -- durable before the call returns.
        developer.create_collection("things", {"id": "integer"})
        assert _count() == 1

        # 2) add_field -- durable before the call returns.
        developer.add_field("things", "label", "text")
        assert _count() == 2

        # 3) insert -- durable before the call returns.
        runtime.insert("things", {"id": 1, "label": "a"})
        assert _count() == 3

        # 4) query (read) -- durable before the rows are returned.
        runtime.read("things")
        assert _count() == 4

        # 5) update -- durable before the call returns.
        runtime.update("things", {"label": "b"}, [Filter("id", "eq", 1)])
        assert _count() == 5

        # 6) non-destructive transact (insert-only batch) -- exactly ONE
        # row for the WHOLE batch (not one per operation).
        runtime.transact([
            {"type": "insert", "collection": "things", "values": {"id": 2, "label": "c"}},
            {"type": "insert", "collection": "things", "values": {"id": 3, "label": "d"}},
        ])
        assert _count() == 6

        # 7) destructive delete (single-operation) -- durable before the
        # call returns.
        revision = scoped(cell._backend).schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase)
        assert _count() == 7

        # 8) destructive transact (batch containing a delete) -- exactly
        # ONE row for the WHOLE batch.
        revision = scoped(cell._backend).schema_revision()
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
    """Each of these is durable before its call returns (no flush)."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        runtime.update("things", {"id": 2}, [Filter("id", "eq", 1)])
        runtime.read("things")
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


def test_delete_bearing_mutate_adds_exactly_one_destructive_row(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        developer.create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        revision = scoped(cell._backend).schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        runtime.transact([
            {"type": "insert", "collection": "things", "values": {"id": 2}},
            {"type": "delete", "collection": "things", "values": {}, "filters": [Filter("id", "eq", 1)],
             "destructive": True, "confirm": phrase},
        ])
        # The batch is destructive -- its one durable row is already
        # present, and no `data_operation` row was made up for the batch.
        events_now = durable.events()
        destructive_rows = [e for e in events_now if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "destructive_data_operation"]
        assert len(destructive_rows) == 1
        batch_rows = [e for e in events_now if e[APPLICATION_AUDIT_FIELDS.index("operation")] == "transact"]
        assert len(batch_rows) == 1
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
        # pre-commit hook has already succeeded: the commit of the
        # developer connection the request borrows raises. The schema
        # operation's one transaction commits exactly once, at its end, so
        # the first commit is the DDL's.
        probe_request_id = "req-" + uuid.uuid4().hex
        with commits_failing(backend, "developer", psycopg.OperationalError("simulated commit failure")):
            with pytest.raises(AuditSinkUnavailable):
                developer.create_collection("things", {"id": "integer"}, request_id=probe_request_id)

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
        with commits_failing(backend, "developer", psycopg.OperationalError("simulated")):
            with pytest.raises(AuditSinkUnavailable):
                developer.create_collection("things", {"id": "integer"})
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
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
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
                scoped(backend).create_collection("things", {"id": "integer"}, audit_hook=hook)
            assert scoped(backend).schema_count() == 0
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
# of the M-3/m-1 emit sites, (2) `data_operation` request_id <-> HTTP
# x-request-id, (3) completion condition 25's own literal test name.
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
    # Phase 10 WP-8c review F-2 (supervisor ruling 2026-09-09): `HttpService`
    # now fails closed at construction time unless BOTH `limit_holder`/
    # `max_concurrency` are supplied (`http.py::HttpService.__init__`'s own
    # comment) -- this test never calls `acquire_concurrency_slot`, only
    # `authenticate`, so the concrete values below are never exercised,
    # but construction itself still requires them.
    service = HttpService(
        CredentialStore("x" * 16), lambda application_id: None, audit_router=router,
        limit_holder=_LimitStateHolder(), max_concurrency=FoundationConfig().max_concurrency,
    )
    with pytest.raises(Exception):  # `http._CredentialMissing`, a private class
        service.authenticate(None, request_id="req-probe")
    events = sink.events()
    assert len(events) == 1
    assert events[0].reason_code == "AUTH_REQUIRED"
    assert events[0].request_id == "req-probe"
    assert events[0].actor_id is None


def test_http_data_operation_event_request_id_matches_the_durable_audit_row(
    platform: types.SimpleNamespace, timeout_probe_app: types.SimpleNamespace,
    main_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence gap (2): the fail-closed (pre-commit hook) path already
    has this proof (`test_http_response_request_id_matches_the_durable_
    audit_row`, schema_change). This is the `data_operation` counterpart
    (a non-destructive mutation) -- a real HTTP mutation's own
    `x-request-id` must equal the `request_id` column on the durable row
    that SAME request wrote, already there with no flush in between."""
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
        "MITATEDB_WORKERS": "1",
        "MITATEDB_SLOT_DIR": _SLOT_DIR,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_RUNTIME_DSN": timeout_probe_app.runtime_dsn,
        f"MITATEDB_APP_{timeout_probe_app.app_id.upper()}_DEVELOPER_DSN": timeout_probe_app.developer_dsn,
        # Q4 phase: `platform`'s own seeded `surfaces` declaration
        # includes `control` -- F-6 requires this process' own declared
        # status to agree with that.
        "MITATEDB_CONTROL_PLANE_STATUS": "enabled",
    }
    collection_name = "bufreqid" + secrets.token_hex(3)

    router_cls, _router_captured = _capturing_subclass(main_module.AuditRouter)
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
    # this peer), so the emit this request produces carries
    # `operation="transact"` (`cell.py::transact`'s own non-destructive
    # pre-commit row), not `"insert"` -- `"insert"` is only the emitted
    # value for the DEDICATED `ApplicationCell.insert` Python-level method
    # (exercised directly, not via HTTP, by `test_query_insert_and_
    # update_success_events_are_durably_recorded` above).
    data_op_rows = [e for e in events if e[APPLICATION_AUDIT_FIELDS.index("event_class")] == "data_operation"
                    and e[APPLICATION_AUDIT_FIELDS.index("operation")] == "transact"]
    assert len(data_op_rows) == 1
    assert data_op_rows[0][APPLICATION_AUDIT_FIELDS.index("request_id")] == http_request_id
    clean_application_audit(platform)


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
        with commits_failing(backend, "developer", psycopg.OperationalError("simulated commit failure")):
            with pytest.raises(AuditSinkUnavailable) as excinfo:
                developer.create_collection("things", {"id": "integer"})
        assert not isinstance(excinfo.value, psycopg.Error), "the caller must see a CLASSIFIED FoundationError, never a raw psycopg.Error"

        error_rows = [e for e in sink.events() if e.outcome == "error"]
        assert len(error_rows) == 1
        assert error_rows[0].reason_code == "commit_failed"
    finally:
        backend.close()
        clean_application_audit(platform)


# ===========================================================================
# The durable sink's connection pool: every write borrows a connection from
# a `pool.BoundedConnectionPool` instead of opening one of its own.
# ===========================================================================


def _pooled_sink(platform: types.SimpleNamespace, *, size: int) -> "tuple[PostgresApplicationAuditSink, BoundedConnectionPool]":
    pool = BoundedConnectionPool(platform.api_dsn, max_size=size)
    return PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool=pool), pool


def _pooled_append(sink: PostgresApplicationAuditSink, target_id: str) -> None:
    sink.append(
        event_class="schema_change", request_id="r1", application_id="a", actor_type="application_credential",
        actor_id="c1", role="developer", operation="create_collection", target_kind="collection",
        outcome="allow", reason_code=None, target_id=target_id,
    )


def _landed_target_ids(platform: types.SimpleNamespace) -> "list[str]":
    """`target_id` of every row in `application_audit`, read with the schema
    owner's own privilege (the writer role has no SELECT), sorted."""
    reader = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    index = APPLICATION_AUDIT_FIELDS.index("target_id")
    return sorted(row[index] for row in reader.events())


def test_pooled_sink_reuses_one_connection_for_consecutive_writes(platform: types.SimpleNamespace) -> None:
    """Completion condition 26: consecutive writes -- `append` and the D-4
    batch `append_many` alike -- run on the pool's one connection, and no
    write opens a connection of its own.

    mutation (`application_audit.py`, `_borrow`): take the no-pool branch
    even when a pool is given (`if self._pool is None:` becomes `if True:`),
    the shape this sink had before it had a pool -- every write opens its
    own connection, the pool opens none, and the pool's `sessions` reads 0
    instead of 1."""
    clean_application_audit(platform)
    sink, pool = _pooled_sink(platform, size=3)
    try:
        for index in range(4):
            _pooled_append(sink, f"seq-{index}")
        batch_event = ApplicationAuditEvent(
            event_id=uuid.uuid4().hex, event_class="schema_change", occurred_at=datetime.now(timezone.utc).isoformat(),
            request_id="r1", application_id="a", actor_type="application_credential", actor_id="c1", role="developer",
            operation="create_collection", target_kind="collection", outcome="allow", reason_code=None, target_id="seq-batch",
        )
        sink.append_many([batch_event])
        assert _landed_target_ids(platform) == ["seq-0", "seq-1", "seq-2", "seq-3", "seq-batch"]
        assert pool.platform_stats()["sessions"] == 1
        assert sink.platform_stats()["sessions"] == 1  # the sink's own view adds the pool's, and has none of its own
    finally:
        sink.close()
        clean_application_audit(platform)


def test_pooled_sink_writes_beyond_the_pool_size_wait_and_every_row_lands(platform: types.SimpleNamespace) -> None:
    """Completion condition 27: with every pooled connection borrowed,
    writes that arrive wait for one -- none fails and none is dropped -- and
    the sink never holds more connections than the pool's size while they
    do. The test borrows both connections itself, starts six writers, and
    returns the connections only afterwards, so every writer is provably in
    the pool's wait.

    mutation (`pool.py`, `acquire` stage 3): stop waiting for a returned
    connection (`if remaining <= 0:` becomes `if True:`), so a write that
    finds the pool exhausted raises at once and its event is lost -- the
    writers' errors list is no longer empty and fewer than six rows
    land."""
    clean_application_audit(platform)
    size, writers = 2, 6
    sink, pool = _pooled_sink(platform, size=size)
    errors: list[BaseException] = []

    def _writer(index: int) -> None:
        try:
            _pooled_append(sink, f"wait-{index}")
        except BaseException as exc:  # noqa: BLE001 -- the assertion below reports whatever a writer raised
            errors.append(exc)

    held = [pool.acquire() for _ in range(size)]
    threads = [threading.Thread(target=_writer, args=(index,)) for index in range(writers)]
    try:
        for thread in threads:
            thread.start()
        time.sleep(0.5)  # every writer is now inside the pool's wait (each has 5 s)
        for conn in held:
            pool.release(conn)
        held = []
        for thread in threads:
            thread.join(timeout=20)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        assert _landed_target_ids(platform) == sorted(f"wait-{index}" for index in range(writers))
        stats = pool.stats()
        assert stats["wait_count"] == writers  # non-vacuous: all six really waited
        assert stats["in_use_peak"] <= size
        assert pool.platform_stats()["sessions"] <= size
    finally:
        for conn in held:
            pool.release(conn)
        sink.close()
        clean_application_audit(platform)


def test_pooled_writes_in_flight_together_never_share_a_transaction(platform: types.SimpleNamespace) -> None:
    """Completion condition 30: a write whose INSERT has run but not
    committed, and a second write that commits meanwhile, are on different
    connections -- the second commit does not commit the first write's
    row, and when the first write then fails, only the second row exists.
    This is the pre_commit / `error` row / first-occurrence write versus
    ordinary-event write independence, with the connections now pooled.

    mutation (`application_audit.py`, `_borrow`): hand every borrower the
    same connection (`conn = self._pool.acquire()` becomes a per-sink
    cached one), so the second write's commit also commits the first
    write's INSERT -- `held-first` is then among the rows."""
    clean_application_audit(platform)
    sink, _pool = _pooled_sink(platform, size=2)
    table = sql.Identifier(platform.schema, "application_audit")
    try:
        with pytest.raises(RuntimeError, match="first write fails"):
            with sink._borrow() as first:  # noqa: SLF001 -- a write in flight, held open on purpose
                with first.cursor() as cur:
                    cur.execute(
                        sql.SQL("INSERT INTO {} (event_id, event_class, occurred_at, operation, outcome, target_id) "
                                "VALUES (%s, 'schema_change', now(), 'create_collection', 'allow', 'held-first')").format(table),
                        [uuid.uuid4().hex],
                    )
                _pooled_append(sink, "committed-second")
                raise RuntimeError("first write fails")
        assert _landed_target_ids(platform) == ["committed-second"]
    finally:
        sink.close()
        clean_application_audit(platform)


def test_pooled_sink_recovers_when_its_connection_is_lost(platform: types.SimpleNamespace) -> None:
    """A pooled connection the server ended, less than the pool's idle-ping
    threshold after its last use, costs at most the one write that found it
    dead: that write either raises or lands -- never reports success
    without a row -- and the next write lands on a fresh connection. The
    pool has one slot, so a connection the sink failed to give back would
    leave the next write waiting out the pool's acquire timeout and
    failing. (Past the threshold no write fails: the two tests below.)

    mutation (`application_audit.py`, `_borrow`): neither return nor
    discard a connection that raised (`self._pool.discard(conn)` becomes
    `pass`), leaking the pool's only slot -- the last write then raises
    `AuthorizationStateUnavailable` after the 5 s wait."""
    clean_application_audit(platform)
    sink, pool = _pooled_sink(platform, size=1)
    try:
        _pooled_append(sink, "before-loss")
        conn = pool.acquire()
        backend_pid = conn.info.backend_pid
        pool.release(conn)
        admin = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT pg_terminate_backend(%s)", [backend_pid])
                assert cur.fetchone() == (True,)
        finally:
            admin.close()
        lost = False
        try:
            _pooled_append(sink, "on-dead-connection")
        except psycopg.Error:
            lost = True
        _pooled_append(sink, "after-loss")
        landed = _landed_target_ids(platform)
        assert landed == sorted(["before-loss", "after-loss"] if lost else ["before-loss", "on-dead-connection", "after-loss"])
        assert pool.platform_stats()["sessions"] == 2
    finally:
        sink.close()
        clean_application_audit(platform)


def test_pooled_sink_rolls_back_what_a_call_left_uncommitted_before_the_connection_returns(platform: types.SimpleNamespace) -> None:
    """A call that returns normally without committing (a read-only
    `events()`, or an INSERT it never committed) leaves a transaction open
    on the pooled connection; `_borrow` rolls it back before the connection
    goes back, so the next write on the same connection does not commit that
    stray row along with its own. The pool has one slot, so the next write is
    provably on the same connection.

    mutation (`application_audit.py`, `_borrow`): drop the defensive
    `conn.rollback()` on the healthy path (`try: conn.rollback()` becomes
    `pass`) -- the connection returns inside its transaction and the next
    write's commit lands the `stray` row too."""
    clean_application_audit(platform)
    sink, pool = _pooled_sink(platform, size=1)
    table = sql.Identifier(platform.schema, "application_audit")
    try:
        with sink._borrow() as conn:  # noqa: SLF001 -- a call that never commits, held open on purpose
            backend_pid = conn.info.backend_pid
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {} (event_id, event_class, occurred_at, operation, outcome, target_id) "
                            "VALUES (%s, 'schema_change', now(), 'create_collection', 'allow', 'stray')").format(table),
                    [uuid.uuid4().hex],
                )
            assert conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        again = pool.acquire()
        assert again.info.backend_pid == backend_pid
        assert again.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        pool.release(again)
        _pooled_append(sink, "next")
        assert _landed_target_ids(platform) == ["next"]
        assert pool.platform_stats()["sessions"] == 1
    finally:
        sink.close()
        clean_application_audit(platform)


def _terminate_backends(platform: types.SimpleNamespace, backend_pids: "list[int]") -> None:
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for backend_pid in backend_pids:
                cur.execute("SELECT pg_terminate_backend(%s)", [backend_pid])
                assert cur.fetchone() == (True,)
    finally:
        admin.close()


def test_pooled_sink_writes_after_every_idle_connection_was_ended_by_the_server(platform: types.SimpleNamespace) -> None:
    """A pool of size 3 holds two idle connections; the server ends both
    (`pg_terminate_backend`, the shape of a database restart or an idle
    disconnect); the pool then sits past `IDLE_PING_THRESHOLD_S`. Every write
    after that lands -- none fails on a dead connection -- because the pool
    checks a connection that long idle before it hands it out and replaces
    it. Non-vacuous: the two terminated sessions really are gone from the
    server, and the pool opened a third connection to serve the writes.

    mutation (`pool.py`, `_is_dead`): skip the round trip (`if self._ping(
    conn):` becomes `if True:`) -- the first write is handed a dead
    connection and raises `psycopg.OperationalError`."""
    clean_application_audit(platform)
    sink, pool = _pooled_sink(platform, size=3)
    try:
        first, second = pool.acquire(), pool.acquire()
        backend_pids = [first.info.backend_pid, second.info.backend_pid]
        pool.release(first)
        pool.release(second)
        assert pool.platform_stats()["sessions"] == 2
        _terminate_backends(platform, backend_pids)
        time.sleep(pool_module.IDLE_PING_THRESHOLD_S + 0.3)
        for index in range(3):
            _pooled_append(sink, f"after-restart-{index}")
        assert _landed_target_ids(platform) == [f"after-restart-{index}" for index in range(3)]
        assert pool.platform_stats()["sessions"] == 3
        admin = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(%s)", [backend_pids])
                assert cur.fetchone() == (0,)
        finally:
            admin.close()
    finally:
        sink.close()
        clean_application_audit(platform)


def test_pool_pings_only_a_connection_that_sat_idle_past_the_threshold(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Counts the pool's round trips: borrowing a connection right after it
    was returned (well within `IDLE_PING_THRESHOLD_S`) pings nothing, so a
    pool under load adds no round trip; borrowing one that sat idle past the
    threshold pings it exactly once, and the live connection is handed out
    outside any transaction (`IDLE`), the same session as before.

    mutation (`pool.py`): `IDLE_PING_THRESHOLD_S = 0.0` -- every borrow
    pings, so the first count is 5 where this test requires 0."""
    pool = BoundedConnectionPool(platform.api_dsn, max_size=2)
    pings: list[object] = []
    real_ping = pool._ping  # noqa: SLF001

    def _counting_ping(conn: Any) -> bool:
        pings.append(conn)
        return real_ping(conn)

    monkeypatch.setattr(pool, "_ping", _counting_ping)
    try:
        conn = pool.acquire()
        backend_pid = conn.info.backend_pid
        pool.release(conn)
        for _ in range(5):
            conn = pool.acquire()
            pool.release(conn)
        assert len(pings) == 0
        time.sleep(pool_module.IDLE_PING_THRESHOLD_S + 0.3)
        conn = pool.acquire()
        assert len(pings) == 1
        assert conn.info.backend_pid == backend_pid
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        pool.release(conn)
        assert pool.platform_stats()["sessions"] == 1
    finally:
        pool.closeall()


# ===========================================================================
# An ordinary data operation's event is durable before its response: a
# query, an insert/update, a non-destructive batch and the replay of a keyed
# batch all reach the durable sink before the caller sees a result, a write's
# `allow` row goes in before its data commit, and a failed event write fails
# the operation closed.
# ===========================================================================


def _things_cell(router: AuditRouter) -> tuple[ApplicationCell, ApplicationRuntime]:
    cell = _sqlite_cell(router)
    make_developer(cell, "appone").create_collection("things", {"id": "integer"})
    return cell, make_runtime(cell, "appone")


def _rows_for(sink: ApplicationAuditSink, request_id: str) -> list[tuple[str, str, str]]:
    return [(e.event_class, e.operation, e.outcome) for e in sink.events() if e.request_id == request_id]


@pytest.mark.parametrize("kind", ["transact", "insert", "update"])
def test_a_write_records_its_allow_row_before_the_data_commit(kind: str) -> None:
    """The `allow` row is the last statement before the data commit -- for a
    non-destructive batch as for a confirmed delete -- so it is already in
    the sink when the backend commits.

    mutation (`cell.py`, `transact`): build the hook only for a destructive
    batch again (`if not dry_run:` becomes `if destructive and not
    dry_run:`) -- the batch is committed with no row in the sink (the
    `transact` case). mutation (`cell.py`, `_write_row_before_commit`):
    drop the `hook.pre_commit()` call -- the same for `insert`/`update`."""
    sink = ApplicationAuditSink()
    cell, runtime = _things_cell(make_router(sink))
    runtime.insert("things", {"id": 1})
    seen: list[list[tuple[str, str]]] = []
    real_commit = cell._backend.commit

    def _observing_commit(**kwargs: Any) -> None:
        seen.append([(e.request_id, e.outcome) for e in sink.events()])
        real_commit(**kwargs)

    cell._backend.commit = _observing_commit
    request_id = f"rid-write-{kind}"
    if kind == "transact":
        runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 2}}], request_id=request_id)
    elif kind == "insert":
        runtime.insert("things", {"id": 2}, request_id=request_id)
    else:
        runtime.update("things", {"id": 3}, [Filter("id", "eq", 1)], request_id=request_id)

    assert len(seen) == 1, "the write must commit exactly once"
    assert (request_id, "allow") in seen[0], f"the allow row was not in the sink when the data committed: {seen[0]!r}"


def test_a_non_destructive_batch_records_its_allow_row_before_the_data_commit_postgres(platform: types.SimpleNamespace, app_a: types.SimpleNamespace) -> None:
    """The same order against a real database: the `allow` row is committed
    on the sink's own connection while the batch's data transaction is
    still open, so a second connection sees the row and not the data.

    mutation (`cell.py`, `transact`): build the hook only for a destructive
    batch again -- the row is not there when the data commits."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        make_developer(cell, app_a.app_id).create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        request_id = "req-" + uuid.uuid4().hex
        seen: list[list[tuple[str, str]]] = []
        real_commit = backend.commit

        def _observing_commit(**kwargs: Any) -> None:
            seen.append([
                (row[APPLICATION_AUDIT_FIELDS.index("request_id")], row[APPLICATION_AUDIT_FIELDS.index("outcome")])
                for row in durable.events()
            ])
            real_commit(**kwargs)

        backend.commit = _observing_commit
        runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 1}}], request_id=request_id)
        assert len(seen) == 1
        assert (request_id, "allow") in seen[0]
    finally:
        backend.close()
        clean_application_audit(platform)


def test_query_event_is_durable_before_the_rows_are_returned() -> None:
    """mutation (`cell.py`, `read_page`): drop the
    `_write_data_operation_event(...)` call -- the read is answered with no
    row in the sink."""
    sink = ApplicationAuditSink()
    _cell, runtime = _things_cell(make_router(sink))
    runtime.insert("things", {"id": 1})

    runtime.read("things", request_id="rid-query-sync")

    assert _rows_for(sink, "rid-query-sync") == [("data_operation", "query", "allow")]


def test_replay_of_a_non_destructive_batch_writes_its_event_before_answering() -> None:
    """mutation (`cell.py`, `transact`): drop the
    `_write_replayed_data_operation_event(...)` call -- the replay is
    answered from the record with no row of its own."""
    sink = ApplicationAuditSink()
    _cell, runtime = _things_cell(make_router(sink))
    operations = [{"type": "insert", "collection": "things", "values": {"id": 1}, "idempotency_key": "k-replay-sync"}]

    first = runtime.transact(operations, request_id="rid-first")
    second = runtime.transact(operations, request_id="rid-resend")

    assert first == second  # answered from the record, not executed again
    assert _rows_for(sink, "rid-resend") == [("data_operation", "transact", "replayed")]
    assert len(runtime.read("things")) == 1


@pytest.mark.parametrize("kind", ["query", "insert", "update", "transact", "mutate_replay", "schema_replay"])
def test_a_failed_event_write_fails_the_operation_closed_and_keeps_no_event(kind: str) -> None:
    """A sink that cannot record the event turns the operation into
    `AuditSinkUnavailable`: nothing is answered, no data is kept, and the
    failed write leaves no row (and no made-up denial row) behind.

    mutation (`audit_dispatch.py`, `write_event`): swallow the sink failure
    -- the `query` is answered with no evidence. mutation (`audit_
    dispatch.py`, `_PreCommitHook.pre_commit`): swallow the sink failure --
    the `insert`/`update`/`transact` commit their data with no row."""
    sink = ApplicationAuditSink()
    cell, runtime = _things_cell(make_router(sink))
    developer = make_developer(cell, "appone")
    runtime.insert("things", {"id": 1})
    batch = [{"type": "insert", "collection": "things", "values": {"id": 2}, "idempotency_key": "k-closed"}]
    if kind == "mutate_replay":
        runtime.transact(batch, request_id="rid-first")
    if kind == "schema_replay":
        developer.create_entity("widgets", {"label": "text"}, idempotency_key="k-closed-schema", request_id="rid-first")
    events_before = len(sink.events())

    sink.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(AuditSinkUnavailable):
        if kind == "query":
            runtime.read("things")
        elif kind == "insert":
            runtime.insert("things", {"id": 2})
        elif kind == "update":
            runtime.update("things", {"id": 3}, [Filter("id", "eq", 1)])
        elif kind == "transact":
            runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 2}}])
        elif kind == "mutate_replay":
            runtime.transact(batch, request_id="rid-resend")
        else:
            developer.create_entity("widgets", {"label": "text"}, idempotency_key="k-closed-schema", request_id="rid-resend")
    sink.inject_fault(None)

    assert len(sink.events()) == events_before
    if kind in ("insert", "update", "transact"):
        assert runtime.read("things") == [{"id": 1}], "the write must not have been kept"


def test_a_failing_idempotency_record_write_leaves_no_allow_row() -> None:
    """The `allow` row is the last statement before the data commit, after
    the idempotency record: a record write that fails leaves no `allow` row
    for data that never committed, and the failure surfaces as itself.

    mutation (`cell.py`, `transact`): call `hook.pre_commit()` in front of
    the idempotency record again -- the row is durable and the failure
    surfaces as `AuditSinkUnavailable`."""
    sink = ApplicationAuditSink()
    cell, runtime = _things_cell(make_router(sink))
    events_before = len(sink.events())

    def _failing_record(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated record-write failure")

    cell._backend.record_idempotency = _failing_record
    with pytest.raises(RuntimeError, match="simulated record-write failure"):
        runtime.transact(
            [{"type": "insert", "collection": "things", "values": {"id": 1}, "idempotency_key": "k-order"}],
            request_id="rid-record-fails",
        )

    assert _rows_for(sink, "rid-record-fails") == []
    assert len(sink.events()) == events_before


def test_a_failed_non_destructive_commit_writes_an_error_row_for_the_same_request_id() -> None:
    """Every failure after the `allow` row is durable -- here the data
    commit -- leaves the `error` row for the same request, whichever kind of
    batch it was.

    mutation (`cell.py`, `transact`): drop the `hook.commit_failed()` call
    from the `except` clause -- only the `allow` row is there."""
    sink = ApplicationAuditSink()
    cell, runtime = _things_cell(make_router(sink))

    def _failing_commit(**kwargs: Any) -> None:
        raise RuntimeError("simulated commit failure")

    cell._backend.commit = _failing_commit
    with pytest.raises(AuditSinkUnavailable):
        runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 1}}], request_id="rid-commit-fails")

    assert [(o, e.reason_code) for e in sink.events() if e.request_id == "rid-commit-fails" for o in [e.outcome]] == [
        ("allow", None), ("error", "commit_failed"),
    ]


def test_a_single_write_whose_commit_fails_writes_an_error_row_for_the_same_request_id() -> None:
    """The single-row `insert`/`update` path answers a failed commit like a
    batch does: the `allow` row is followed by the `error` row.

    mutation (`cell.py`, `_write_row_before_commit`): drop the
    `hook.commit_failed()` call -- only the `allow` row is there."""
    sink = ApplicationAuditSink()
    cell, runtime = _things_cell(make_router(sink))

    def _failing_commit(**kwargs: Any) -> None:
        raise RuntimeError("simulated commit failure")

    cell._backend.commit = _failing_commit
    with pytest.raises(AuditSinkUnavailable):
        runtime.insert("things", {"id": 1}, request_id="rid-single-commit-fails")

    assert [e.outcome for e in sink.events() if e.request_id == "rid-single-commit-fails"] == ["allow", "error"]


def test_a_hook_that_could_not_record_its_row_is_not_marked_fired() -> None:
    """`fired` says an `allow` row is durable: it stays False when the sink
    refused the row, so no `error` row is owed for a row that was never there.

    mutation (`audit_dispatch.py`, `_PreCommitHook.pre_commit`): set
    `self.fired = True` before the sink write -- a failed write reads as
    fired."""
    sink = ApplicationAuditSink()
    router = make_router(sink)
    hook = router.make_pre_commit_hook(
        event_class="data_operation", request_id="rid-fired", application_id="appone", actor_type="application_credential",
        actor_id="c1", role="runtime", operation="transact", target_kind="collection",
    )
    sink.inject_fault(RuntimeError("simulated durable-sink failure"))
    with pytest.raises(AuditSinkUnavailable):
        hook.pre_commit()
    assert hook.fired is False
    sink.inject_fault(None)
    hook.pre_commit()
    assert hook.fired is True


def test_a_cancelled_schema_record_write_after_the_pre_commit_row_writes_an_error_row_and_keeps_the_response(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """The backend's own handling of a cancelled or lock-timed-out statement
    does not know the `allow` row is already durable; the cell records the
    `error` row for it, and the response class does not change.

    mutation (`cell.py`, `_error_row_once_fired`): drop the
    `hook.commit_failed()` call -- only the `allow` row is there."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        developer = make_developer(cell, app_a.app_id)
        request_id = "req-" + uuid.uuid4().hex
        with patch.object(backend, "_write_idempotency_row", side_effect=psycopg.errors.QueryCanceled("simulated cancel")):
            with pytest.raises(FoundationError) as exc:
                developer.create_entity("things", {"id": "integer"}, idempotency_key="k-cancel", request_id=request_id)
        assert type(exc.value).__name__ == "ResourceLimitError"
        outcomes = [
            row[APPLICATION_AUDIT_FIELDS.index("outcome")] for row in durable.events()
            if row[APPLICATION_AUDIT_FIELDS.index("request_id")] == request_id
        ]
        assert outcomes == ["allow", "error"]
    finally:
        backend.close()
        clean_application_audit(platform)


def test_a_cancelled_delete_commit_after_the_pre_commit_row_writes_an_error_row_and_keeps_the_response(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """The same for a confirmed single-operation delete whose COMMIT is
    cancelled.

    mutation (`cell.py`, `_error_row_once_fired`): drop the
    `hook.commit_failed()` call -- only the `allow` row is there."""
    clean_application_audit(platform)
    durable = PostgresApplicationAuditSink(platform.provision_dsn, schema=platform.schema)
    router = make_router(durable)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend, audit_router=router)
        make_developer(cell, app_a.app_id).create_collection("things", {"id": "integer"})
        runtime = make_runtime(cell, app_a.app_id)
        runtime.insert("things", {"id": 1})
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], scoped(cell._backend).schema_revision())
        request_id = "req-" + uuid.uuid4().hex
        with commits_failing(backend, "runtime", psycopg.errors.QueryCanceled("simulated cancel")):
            with pytest.raises(FoundationError) as exc:
                runtime.delete("things", [Filter("id", "eq", 1)], destructive=True, confirm=phrase, request_id=request_id)
        assert type(exc.value).__name__ == "ResourceLimitError"
        outcomes = [
            row[APPLICATION_AUDIT_FIELDS.index("outcome")] for row in durable.events()
            if row[APPLICATION_AUDIT_FIELDS.index("request_id")] == request_id
        ]
        assert outcomes == ["allow", "error"]
        assert len(runtime.read("things")) == 1, "the cancelled delete must not have been kept"
    finally:
        backend.close()
        clean_application_audit(platform)


def test_a_schema_operation_waiting_for_the_audit_pool_is_refused_in_bounded_time_and_leaves_no_lock(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace,
) -> None:
    """The audit pool's connections are held by writers that touch only the
    platform database and wait for nothing in an application database. A
    schema operation holds its transaction and its advisory locks while its
    pre-commit audit row waits for an audit connection: with the pool's only
    connection borrowed elsewhere that wait ends at the pool's own limit
    (here 0.5 s) as `AuditSinkUnavailable`, and the scope's exit returns the
    application connection rolled back -- so once the audit connection is
    back the next schema operation, which needs the same locks, succeeds
    instead of waiting for a lock the refused one still held."""
    clean_application_audit(platform)
    pool = BoundedConnectionPool(platform.api_dsn, max_size=1, acquire_timeout=0.5)
    sink = PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool=pool)
    backend = make_backend(app_a)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(max_execution_ms=3000), backend=backend,
                               audit_router=make_router(sink))
        developer = make_developer(cell, app_a.app_id)
        held = pool.acquire()
        started = time.monotonic()
        try:
            with pytest.raises(AuditSinkUnavailable):
                developer.create_collection("things", {"id": "integer"})
            assert time.monotonic() - started < 3.0
        finally:
            pool.release(held)
        assert scoped(backend).schema_count() == 0
        # A refusal after the locks are taken and before any DDL (a stale
        # plan token) leaves nothing for the backend method to roll back:
        # only the scope's exit can release the locks it took.
        with pytest.raises(FoundationError) as stale:
            developer.create_entity("things", {"id": "integer"}, plan="stale-plan-token")
        assert type(stale.value).__name__ == "PreconditionFailedError"
        developer.create_collection("things", {"id": "integer"})
        assert scoped(backend).schema_count() == 1
    finally:
        backend.close()
        pool.closeall()
        clean_application_audit(platform)
