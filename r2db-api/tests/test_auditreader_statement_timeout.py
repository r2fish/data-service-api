"""R-56 WP-1 (design docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md
D-1, work order docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md
WP-1 completion conditions W1-1/W1-2/W1-3): migration
`0014_auditreader_statement_timeout.sql` against a real, throwaway-prefixed
PostgreSQL platform.

Own file, own fixture (function-scoped: the idempotency test re-applies
`0014` a second time and the effective-value probe depends on opening a
FRESH connection, so a shared platform would make later tests' outcomes
depend on execution order -- the same reasoning `tests/
test_ops_verify_declarations.py`'s own `platform` fixture docstring gives
for staying function-scoped). Migrates only through `0007`/`0014` -- the
scenarios here need `r2dbsvc_auditreader` to exist and nothing past it.
"""
from __future__ import annotations

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

import r2db_api.credential_store as credential_store
from r2db_api.credential_store import PostgresAuditQueryStore
from r2db_api.errors import FoundationError

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    "0014_auditreader_statement_timeout.sql",
)


def _admin_dsn() -> str:
    import os

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


def _run_psql(dsn: str, path: Path, variables: "dict[str, str] | None" = None) -> None:
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
            "test_auditreader_statement_timeout.py requires a reachable local "
            f"PostgreSQL server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: "
            f"{exc}. These tests must not be skipped (§5.3 C-5).",
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


@pytest.fixture()
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbauditrto{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_auditreader_rto_migrations")
    rewritten: "dict[str, Path]" = {}
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
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    auditreader_dsn = _dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db)

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        auditreader_dsn=auditreader_dsn, auditreader_role=auditreader_role,
        platform_db=platform_db, schema=schema,
        migration_0014=rewritten["0014_auditreader_statement_timeout.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


# ===========================================================================
# W1-1: effective value on a freshly opened reader connection.
# ===========================================================================


def test_reader_connection_effective_statement_timeout_is_5000ms_after_0014(platform: types.SimpleNamespace) -> None:
    """Completion condition W1-1 (design §6 条件 1): reads `pg_settings.
    setting` (the raw ms integer string) on a connection opened AFTER
    `0014` has already run -- never `SHOW`/`current_setting`, which round
    to whichever unit divides evenly (design §6 条件 1 の低9)."""
    with psycopg.connect(platform.auditreader_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
            (setting,) = cur.fetchone()
    assert setting == "5000"


# ===========================================================================
# W1-3: idempotent re-application.
# ===========================================================================


def test_0014_reapplication_is_idempotent(platform: types.SimpleNamespace) -> None:
    """Completion condition W1-3: applying `0014` a second time succeeds
    and leaves the same terminal state -- the effective value on a newly
    opened connection is still 5000ms."""
    _run_psql(platform.control_dsn, platform.migration_0014)
    with psycopg.connect(platform.auditreader_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
            (setting,) = cur.fetchone()
    assert setting == "5000"


# ===========================================================================
# W1-2: a slow audit query is canceled within the reader's own
# statement_timeout, answers 503 SERVICE_UNAVAILABLE with no backend detail
# leaked, and the connection is returned to the pool.
# ===========================================================================


def _read_auditreader_statement_timeout(admin_dsn: str, role: str) -> str:
    """Reads the role's own PRE-existing `statement_timeout` straight from
    `pg_roles.rolconfig` (the same catalog `ALTER ROLE ... SET` writes
    to) -- never a hardcoded literal -- so the scenario below can restore
    EXACTLY the value that was in place before it shortened the timeout."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT rolconfig FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
            row = cur.fetchone()
    finally:
        admin.close()
    rolconfig = row[0] if row else None
    if rolconfig:
        for entry in rolconfig:
            if entry.startswith("statement_timeout="):
                return entry.split("=", 1)[1]
    raise AssertionError(f"role {role!r} has no statement_timeout set in pg_roles.rolconfig")


def _set_auditreader_statement_timeout(control_dsn: str, role: str, value: str) -> None:
    with psycopg.connect(control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(sql.Identifier(role), sql.Literal(value)))
        conn.commit()


def test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition W1-2 (design §6 条件 2, verbatim): the
    reader ROLE's own `statement_timeout` (`ALTER ROLE ... SET`, on
    `platform.control_dsn`) is shortened to `200ms` for the scenario and
    restored to whatever it was before (read via `pg_roles.rolconfig`,
    never a hardcoded literal) in `finally` -- never a connection-level
    `options=-c statement_timeout=...` override, which would prove
    nothing about the ROLE-level value `0014` actually declares reaching
    a pooled connection. `store` is built AFTER the shortening (role
    settings apply at login, design §4 D-1's own "高 1") -- its FIRST
    query is the one made slow, so the pool's own first connection is
    guaranteed to carry the shortened value.

    Slowness is made by the reader's OWN SQL, never by a held lock (a lock
    wait would hang indefinitely under the mutation that removes `0014`'s
    own `ALTER ROLE ... SET` line, design §6 条件 2): `credential_store.
    _AUDIT_QUERY_UNION_SQL` is monkeypatched, for the duration of the
    first `query()` call only, to a literal `SELECT pg_sleep(2)` -- a real
    round trip that always takes longer than the shortened timeout below,
    regardless of machine speed or data volume (the same `pg_sleep(...)`
    technique `tests/test_postgres.py` already uses, e.g. around its own
    `SELECT pg_sleep(2)` call, to provoke a real `QueryCanceled`
    deterministically)."""
    original_timeout = _read_auditreader_statement_timeout(platform.admin_dsn, platform.auditreader_role)
    _set_auditreader_statement_timeout(platform.control_dsn, platform.auditreader_role, "200ms")
    try:
        store = PostgresAuditQueryStore(platform.auditreader_dsn, schema=platform.schema, pool_size=1)
        try:
            original_sql = credential_store._AUDIT_QUERY_UNION_SQL
            monkeypatch.setattr(credential_store, "_AUDIT_QUERY_UNION_SQL", "SELECT pg_sleep(2)")
            start = time.monotonic()
            with pytest.raises(FoundationError) as excinfo:
                store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)
            elapsed = time.monotonic() - start
            assert elapsed < 8.0, f"took {elapsed}s -- the role-level statement_timeout did not cancel the query"
            assert excinfo.value.code == "SERVICE_UNAVAILABLE"
            assert excinfo.value.status == 503
            assert excinfo.value.message == "The database could not complete the request."
            rendered = repr(excinfo.value.problem())
            assert platform.auditreader_dsn not in rendered
            assert platform.auditreader_role not in rendered
            assert "SELECT" not in rendered
            assert "canceling statement" not in rendered

            # Pool returned: the SAME store's very next query, against the
            # real (un-monkeypatched) SQL and comfortably inside the
            # shortened timeout, succeeds normally.
            monkeypatch.setattr(credential_store, "_AUDIT_QUERY_UNION_SQL", original_sql)
            rows = store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)
            assert rows == []
        finally:
            store.close()
    finally:
        _set_auditreader_statement_timeout(platform.control_dsn, platform.auditreader_role, original_timeout)
