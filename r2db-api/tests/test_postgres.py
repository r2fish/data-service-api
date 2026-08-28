"""`PostgresCell` (`r2db_api.postgres`) tested against a real PostgreSQL
server -- design D-3/D-4/D-5, §8 ("D-3 改訂" -- database-per-application),
§5.3 C-5 ("this work machine has PostgreSQL 16 running; PostgresCell and
the provisioning SQL must be verified against it, not skipped").

Everything this file creates in the cluster -- the control-plane bootstrap
(role + platform database + registry schema), and every per-application
*database* + role pair it provisions -- is named under one random-per-run
prefix (`r2dbtest<8 hex chars>_...`) so it can never collide with anything
else in this shared local cluster, and is dropped in a module-scoped
fixture finalizer that runs even if a test fails. Nothing outside that
prefix is ever read, listed, or touched.

The control-plane bootstrap and per-application provisioning are exercised
by actually running the real `r2db-api/migrations/0001_bootstrap_control_
plane.sql` through `0004_deprovision_application.sql` files (with
`r2dbsvc` textually replaced by this run's throwaway prefix) through the
real `psql` binary, exactly as an operator would per `r2db-api/docs/`. This
is deliberately not a Python reimplementation of what those files do: it
is the actual migration SQL, proving the runbook's own documented commands
work, not a parallel approximation of them. Provisioning one application is
itself now a multi-statement `psql` *script* (0003), not a single function
call, because `CREATE DATABASE` cannot run inside a transaction block --
see that file's header comment for why.

If PostgreSQL is not reachable, every test in this module fails loudly
(module-scoped fixture error) naming the DSN that failed -- it does not
skip. A skip would turn "we could not verify this" into "this is allowed",
which is exactly what §5.3 C-5 forbids.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import threading
import time
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell, SharedPoolManager, _RolePool
from r2db_api.structured import Predicate

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


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
            "test_postgres.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. "
            f"Set {ADMIN_DSN_ENV} to a reachable admin/superuser DSN "
            "(e.g. 'host=/tmp port=5432 dbname=postgres' or "
            "'postgresql://user:pass@example.invalid:5432/postgres' against "
            "the VPS). These tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, platform_db: str, prefix: str) -> None:
    """Drop everything this run created: every database whose name starts
    with this run's unique prefix -- the platform database *and* every
    per-application database provisioned during the run (each one takes
    every schema/table/grant inside it with it) -- then every role whose
    name starts with the same prefix (roles are cluster-global objects,
    independent of any one database, so they need their own sweep). Never
    touches any object outside this run's prefix.

    Unlike the previous (schema-per-application) revision of this function,
    `platform_db` alone is not enough to enumerate here: database-per-
    application (architecture §8) means each test's `app_a`/`app_b`
    fixtures create *additional* databases beyond the platform one, and a
    test failing before its own `deprovision_app` teardown runs must not
    leave one behind. Enumerating by `LIKE '<prefix>%'` against
    `pg_database` catches all of them, the platform database included, in
    one pass.

    `DROP DATABASE` is retried with a short backoff on `ObjectInUse` --
    identical reasoning to `deprovision_app`'s own retry above and to
    `conformance_adapter_r2db_http.py::_sweep_prefix`: a connection this
    module's own tests just closed can take a brief moment to fully
    disappear from `pg_stat_activity`. `pg_terminate_backend` is scoped to
    `backend_type = 'client backend'` for the same reason
    `0004_deprovision_application.sql` is: this admin connection
    authenticates as the OS/cluster superuser locally, so it *could*
    terminate a background worker too, but a freshly churned database
    routinely has an autovacuum worker visiting it, and terminating that is
    unnecessary -- it finishes on its own well within this retry loop's
    backoff, which is what actually clears the `ObjectInUse` in that case.
    """
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
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
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtest{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    platform_db = f"{prefix}_platform"
    control_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_migrations")
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, platform_db, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        control_role=control_role,
        platform_db=platform_db,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, platform_db, prefix)


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
        # Every application's entities now live in *that application's own
        # database*'s `public` schema (architecture §8) rather than in a
        # control-plane-assigned schema name inside one shared database --
        # `schema` is kept as an attribute (rather than removed) because
        # `PostgresCell.__init__` still takes a `schema` argument (§8.6: no
        # structural change to that constructor), it is simply always
        # `"public"` now.
        schema="public",
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def deprovision_app(platform: types.SimpleNamespace, slug: str) -> None:
    """Run `0004_deprovision_application.sql`, retrying the whole script a
    few times with a short backoff if `DROP DATABASE` there hits
    PostgreSQL's `database "..." is being accessed by other users`: a
    connection this same test itself just closed (typically one of
    `PostgresCell`'s pooled connections, via the test's own `cell.close()`
    a moment earlier -- or, empirically, an autovacuum worker that visited
    this freshly churned database on its own initiative, which `0004`
    deliberately does not try to terminate; see that file's comment) can
    take a brief moment to fully disappear from `pg_stat_activity` from the
    server's point of view, which can otherwise race `DROP DATABASE`.
    `conformance_adapter_r2db_http.py::_sweep_prefix` already established
    this exact retry pattern for the same underlying race; this applies it
    here too, since `0004`'s own `\\set ON_ERROR_STOP on` means a single
    such failure would otherwise abort the whole script before `DROP
    ROLE`/`finish_deprovision_application` ever run -- leaving the registry
    row (and the roles) behind, which would then collide with a *later*
    test provisioning the same slug again ("application already
    provisioned"). Retrying the entire script from the top is safe: on a
    failed attempt, `begin_deprovision_application` (a plain `SELECT`, no
    side effect) is the only step that ran, so the registry row is exactly
    as it was before this function was called.
    """
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


def make_cell(app: types.SimpleNamespace, *, pool_size: int = 2, pool_manager: SharedPoolManager | None = None) -> PostgresCell:
    return PostgresCell(
        app.slug,
        app.schema,
        runtime_dsn=app.runtime_dsn,
        developer_dsn=app.developer_dsn,
        runtime_role=app.runtime_role,
        developer_role=app.developer_role,
        pool_size=pool_size,
        pool_manager=pool_manager,
    )


@contextmanager
def provisioned_apps(platform: types.SimpleNamespace, slugs: list[str]) -> Iterator[list[types.SimpleNamespace]]:
    """Provision several applications for the duration of one `with` block,
    tearing down exactly the ones that were actually provisioned (in
    reverse order) even if provisioning a later slug fails partway through
    -- the multi-application `SharedPoolManager` tests below need more than
    the two `app_a`/`app_b` fixtures provide.
    """
    apps: list[types.SimpleNamespace] = []
    provisioned_slugs: list[str] = []
    try:
        for slug in slugs:
            apps.append(provision_app(platform, slug))
            provisioned_slugs.append(slug)
        yield apps
    finally:
        for slug in reversed(provisioned_slugs):
            deprovision_app(platform, slug)


def _live_connections_by_role(admin_dsn: str, roles: list[str]) -> dict[str, int]:
    """The live connection count PostgreSQL itself reports right now
    (`pg_stat_activity`), grouped by login role, restricted to exactly the
    roles named -- never inspecting `SharedPoolManager`'s own Python state.
    Used by the pool-cap/eviction tests below to verify the fix against
    real server state.
    """
    conn = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT usename, count(*) FROM pg_stat_activity WHERE usename = ANY(%s) GROUP BY usename", [roles])
            return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


@pytest.fixture
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "iso_a")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_a")


@pytest.fixture
def app_b(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "iso_b")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_b")


LIMITS = ResourceLimits()


def P(field: str, operator: str, value: object = None) -> Predicate:
    """`PostgresCell.query`'s `where` parameter, per the `StorageBackend`
    protocol, is `list[Predicate]` -- already parsed. In the real request
    path `DataService.query` does that parsing (`parse_predicate`) before
    ever calling the cell; these tests call `PostgresCell` directly, so they
    do that same parsing step themselves rather than passing raw dicts.
    """
    return Predicate(field=field, operator=operator, value=value)


# --- cross-application isolation, verified at the database level ----------
#
# §8.5 condition 1: with database-per-application, the primary wall is
# `CONNECT` on the database itself -- a role scoped to one application must
# be refused a raw connection to another application's database outright,
# never merely denied once connected. This is verified directly (a raw
# `psycopg.connect`, not through `PostgresCell`) in the test immediately
# below, which is the executable check for §8.5 condition 1 and the most
# important test this revision adds.


def test_cross_database_connect_is_refused_at_the_database_level(app_a: types.SimpleNamespace, app_b: types.SimpleNamespace) -> None:
    """The primary wall (§8.5 condition 1): Application A's own runtime
    role, with its own real password, attempting to open a connection
    straight at Application B's database -- not through `PostgresCell`,
    not even attempting any query once connected, because it never gets
    that far. `0003_provision_application.sql` closes `PUBLIC`'s default
    `CONNECT` on every newly created database and grants it only to that
    one application's own two roles; this is the test that this actually
    holds, for a real login role with real, valid credentials for a
    *different* application.
    """
    cross_dsn = _dsn_with(app_a.runtime_dsn, dbname=app_b.database)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(cross_dsn, connect_timeout=5)

    # The same refusal holds for A's developer role -- elevated authority
    # within A's *own* database does not generalize to reaching B's
    # database at all (SI-00/SI-01): there is no PostgreSQL operation that
    # authority could even attempt once the connection itself is refused.
    cross_dev_dsn = _dsn_with(app_a.developer_dsn, dbname=app_b.database)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(cross_dev_dsn, connect_timeout=5)


def test_cross_application_isolation_at_the_application_level(app_a: types.SimpleNamespace, app_b: types.SimpleNamespace) -> None:
    """The application-level counterpart to the raw-connection test above:
    even though B's `PostgresCell` never gets a chance to reach A's
    database at all (it is never even given A's connection information --
    a `PostgresCell` only ever holds the DSNs its own constructor call was
    given), this confirms end-to-end that entities created through A's
    cell are simply invisible to B's, from B's own database, which is what
    an application actually observes.
    """
    cell_a = make_cell(app_a)
    try:
        cell_a.apply_schema({"operation": "create_entity", "entity": "secrets", "fields": ["value"]}, developer=True, limits=LIMITS)
        cell_a.transact("secrets", [{"operation": "insert", "values": {"value": "app-a-only"}}], LIMITS)
    finally:
        cell_a.close()

    cell_b = make_cell(app_b)
    try:
        assert cell_b.catalog() == []
        with pytest.raises(FoundationError) as exc:
            cell_b.query("secrets", select=["value"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell_b.close()


def test_public_schema_default_privileges_closed_and_developer_owns_it(app_a: types.SimpleNamespace) -> None:
    """§8.5 condition 2: `public`'s default privileges are closed
    (`REVOKE ALL ON SCHEMA public FROM PUBLIC` in `0003`), the developer
    role owns `public` outright (its DDL authority, SI-03), and runtime
    has exactly `USAGE` -- enough to resolve names, never `CREATE`.
    """
    conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'")
            (owner,) = cur.fetchone()
            assert owner == app_a.developer_role

            cur.execute("SELECT has_schema_privilege('public', 'public', 'CREATE')")
            assert cur.fetchone() == (False,)
            cur.execute("SELECT has_schema_privilege('public', 'public', 'USAGE')")
            assert cur.fetchone() == (False,)

            cur.execute("SELECT has_schema_privilege(%s, 'public', 'USAGE')", [app_a.runtime_role])
            assert cur.fetchone() == (True,)
            cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", [app_a.runtime_role])
            assert cur.fetchone() == (False,)

            cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", [app_a.developer_role])
            assert cur.fetchone() == (True,)
    finally:
        conn.close()


def test_row_level_security_is_enabled_and_forced_on_created_tables(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=LIMITS)
    finally:
        cell.close()
    # Must connect to this application's own database (not the bootstrap
    # `_admin_dsn()`, which points at `postgres`) to see this table's
    # catalog row at all.
    admin = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s",
                [app_a.schema, "widgets"],
            )
            row = cur.fetchone()
            assert row == (True, True)
    finally:
        admin.close()


def test_verify_row_level_security_detects_missing_rls(app_a: types.SimpleNamespace) -> None:
    """§8.5 condition 3(b): `PostgresCell.verify_row_level_security()` must
    both (a) pass silently for a database whose tables were all created the
    normal way (through `PostgresCell.apply_schema`, which always applies
    RLS), and (b) actually detect drift -- a table with RLS disabled by
    some means other than `PostgresCell` -- rather than only ever agreeing
    with whatever `PostgresCell` itself already believes.
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_entity", "entity": "gadgets", "fields": ["name"]}, developer=True, limits=LIMITS)
        # (a) clean state: no exception.
        cell.verify_row_level_security()

        # `migrations/0003_provision_application.sql` also installs a
        # SQL-level equivalent of this same check, `public._r2db_missing_
        # rls`, directly inside this application's own database -- usable
        # by an operator with no PostgresCell/Python involved at all.
        # Confirm it agrees with the clean state too.
        dev_conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with dev_conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert cur.fetchall() == []
        finally:
            dev_conn.close()
    finally:
        cell.close()

    # Simulate drift: disable RLS on one table directly, bypassing
    # `PostgresCell` entirely -- exactly the "someone forgot" scenario
    # §8.5 condition 3 asks this verification to catch rather than trust.
    dev_conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with dev_conn.cursor() as cur:
            cur.execute("ALTER TABLE public.gadgets DISABLE ROW LEVEL SECURITY")
    finally:
        dev_conn.close()

    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.verify_row_level_security()
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert exc.value.details["tables"] == ["gadgets"]

        # And the SQL-level view installed at provisioning time agrees.
        dev_conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with dev_conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert cur.fetchall() == [("gadgets",)]
        finally:
            dev_conn.close()

        # Defence in depth (`_create_entity` calls the same check inline,
        # in the same transaction, after every table it creates): with
        # `gadgets` already missing RLS, creating a brand new, unrelated
        # entity must also fail -- the database-wide check runs regardless
        # of which table triggered it, and the new table's own creation is
        # rolled back along with everything else in that transaction.
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "sprockets", "fields": []}, developer=True, limits=LIMITS)
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert "sprockets" not in {item["entity"] for item in cell.catalog()}
    finally:
        cell.close()


# --- runtime cannot perform DDL, verified at the database level -----------


def test_runtime_role_cannot_perform_ddl(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
    finally:
        cell.close()

    conn = psycopg.connect(app_a.runtime_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("CREATE TABLE {}.{} (x INT)").format(sql.Identifier(app_a.schema), sql.Identifier("sneaky")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("ALTER TABLE {}.{} ADD COLUMN sneaky INT").format(sql.Identifier(app_a.schema), sql.Identifier("items")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("DROP TABLE {}.{}").format(sql.Identifier(app_a.schema), sql.Identifier("items")))
    finally:
        conn.rollback()
        conn.close()

    # The application-level path is consistent with this: PostgresCell
    # itself refuses to even attempt DDL for a non-developer caller, before
    # any SQL is sent (design D-1's shared `bind_schema_operation`).
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "should_not_exist", "fields": []}, developer=False, limits=LIMITS)
        assert exc.value.code == "FORBIDDEN"
    finally:
        cell.close()


# --- injection payloads: identifier positions rejected --------------------

# This corpus intentionally mirrors the categorized coverage in
# `conformance-tests/payloads.py` (`IDENTIFIER_PAYLOAD_CATEGORIES`) rather
# than importing it. `conformance-tests` is only on `sys.path` when pytest
# resolves its inifile from the *root* `pyproject.toml`
# (`pythonpath = [..., "conformance-tests"]`, `testpaths` covering all three
# suites). Invoke pytest directly against this file or this package instead
# -- e.g. `pytest r2db-api/tests/test_postgres.py` -- and pytest's rootdir
# search finds `r2db-api/pyproject.toml` first (it also declares
# `[tool.pytest.ini_options]`), whose `pythonpath` is only `["src"]`;
# confirmed empirically (`pytest --collect-only` from the two starting
# points resolves two different inifiles). Importing `payloads` here would
# make this file's collectability depend on the invoking directory, which
# is exactly the fragility this suite should not have, so the categories
# are reproduced locally instead.
#
# Two categories from that corpus are deliberately not reproduced: an
# embedded NUL byte (`embedded_nul`) makes psycopg itself raise
# `DataError` on any parameter carrying it -- including the plain
# `information_schema` verification queries these tests run -- before the
# payload ever reaches `structured.validate_identifier`, so it cannot
# exercise the DDL path this file is adding coverage for; and an empty
# string (`empty_string`) is a PostgreSQL *parser* error ("zero-length
# delimited identifier") once quoted, not an outcome the identifier
# validator controls, so it would not cleanly prove "no side effect" the
# way every other payload below does (verified empirically: every payload
# below, and only these two, behave differently under a bypassed
# validator).
IDENTIFIER_INJECTION_PAYLOADS: list[tuple[str, str]] = [
    ("statement_terminator", "items; DROP TABLE items; --"),
    ("quote_escape_double_then_statement", '"; DROP TABLE items; --'),
    ("quote_escape_single_then_comment", "items'--"),
    ("quote_escape_double", "items\""),
    ("path_traversal", "../items"),
    ("tautology_bare", "items OR 1=1"),
    ("comment_dash", "items--"),
    ("comment_block", "items/*comment*/"),
    ("tautology_quoted", "' OR '1'='1"),
    ("identifier_quote_backtick", "`items`"),
    ("identifier_quote_bracket", "[items]"),
    ("embedded_newline", "items\nname"),
    ("embedded_whitespace", "items name"),
    ("qualified_name", "a.b"),
    ("wildcard", "*"),
    ("starts_with_digit", "1items"),
    ("long_string", "a" * 300),
    ("non_ascii", "usérs"),
    ("fullwidth", "ユーザー"),
]
IDENTIFIER_INJECTION_PAYLOAD_VALUES = [payload for _, payload in IDENTIFIER_INJECTION_PAYLOADS]
IDENTIFIER_INJECTION_PAYLOAD_IDS = [name for name, _ in IDENTIFIER_INJECTION_PAYLOADS]


_REVISION_TABLE = "_r2db_schema_revision"  # provisioned by
# `r2db-api/migrations/0003_provision_application.sql` for every
# application database, independent of anything these tests create --
# excluded below the same way `PostgresCell._load_catalog` excludes it, so
# it does not read as a false "something was created" side effect.


def _real_table_names(dsn: str, schema: str) -> set[str]:
    """The live set of base-table names PostgreSQL itself reports for
    `schema`, queried independently of `PostgresCell.catalog()` -- so a bug
    in `catalog()`'s own filtering could never hide a table that a broken
    identifier validator let through onto the DDL path.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE' AND table_name <> %s",
                [schema, _REVISION_TABLE],
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _real_column_names(dsn: str, schema: str, table: str) -> set[str]:
    """The live set of column names PostgreSQL itself reports for
    `schema.table`, queried independently of `PostgresCell.catalog()` for
    the same reason as `_real_table_names` above.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
                [schema, table],
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


@pytest.mark.parametrize("entity", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payloads_in_identifier_positions_are_rejected(app_a: types.SimpleNamespace, entity: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query(entity, select=["label"], where=[], page_size=10, limits=LIMITS)
        # Tightened per the mutation finding that motivated this change:
        # every payload in this corpus is, by construction, syntactically
        # invalid under the contract's identifier pattern, so acceptance of
        # `NOT_FOUND` alongside `IDENTIFIER_INVALID` here (as this
        # assertion used to read) made the test pass identically whether
        # the shared syntax validator ran at all or was replaced with
        # `^.*$` -- PostgresCell's catalog check produces `NOT_FOUND` for
        # an unknown name either way, so the old assertion could never
        # distinguish "rejected by identifier policy" from "happened not to
        # exist". See `test_syntactically_valid_but_nonexistent_identifier_
        # is_not_found` below for the legitimately-`NOT_FOUND` case this is
        # now distinguishable from.
        assert exc.value.code == "IDENTIFIER_INVALID"
        # No side effect: the legitimate table is still there, untouched.
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


def test_syntactically_valid_but_nonexistent_identifier_is_not_found(app_a: types.SimpleNamespace) -> None:
    """The counterpart to the tightened assertion above: a name that *is* a
    syntactically valid identifier under the contract's pattern, but simply
    does not exist as an entity, legitimately yields `NOT_FOUND` -- proving
    the two outcomes are actually distinguishable rather than both folded
    into one accepted code set.
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("does_not_exist_but_syntactically_valid", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_a_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=[field_name], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


# --- injection payloads: DDL identifier positions --------------------------
#
# The read-path tests above pass even with a broken syntax validator
# (proven by the mutation this module's fix responds to: replacing
# `structured.IDENTIFIER` with `re.compile(r"^.*$")` left all of them
# green) because `PostgresCell.query` independently verifies the identifier
# against the live `information_schema` catalog on every read -- an unknown
# name is rejected regardless of whether the syntax validator did anything.
# DDL has no such backstop: `create_entity`'s `entity` and `fields`, and
# `add_field`'s `field`, name objects that do not exist *yet*, by
# definition, so there is no catalog to check them against.
# `structured.bind_schema_operation` -- called before `PostgresCell` opens
# any database connection at all -- is the only guard on this path. Each
# test below was confirmed, via that same mutation, to fail without it:
# with the syntax check disabled, PostgreSQL's own identifier quoting
# (`psycopg.sql.Identifier`) happily creates a real table or column named
# exactly the payload instead of raising anything.


@pytest.mark.parametrize("entity", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_create_entity_name_is_rejected(app_a: types.SimpleNamespace, entity: str) -> None:
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": entity, "fields": ["label"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        # Checked against PostgreSQL's own information_schema, not
        # `cell.catalog()`: nothing landed in the database at all, under
        # any name.
        assert _real_table_names(app_a.developer_dsn, app_a.schema) == set()
        assert cell.catalog() == []
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_create_entity_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", field_name]}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        # `bind_schema_operation` validates every field in `fields` up
        # front, before any connection opens, so the whole operation is
        # rejected -- not even the otherwise-legitimate "items" table
        # should exist.
        assert _real_table_names(app_a.developer_dsn, app_a.schema) == set()
        assert cell.catalog() == []
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_add_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "add_field", "entity": "items", "field": field_name}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        assert _real_column_names(app_a.developer_dsn, app_a.schema, "items") == {"label"}
        assert cell.catalog() == [{"entity": "items", "fields": ["label"]}]
    finally:
        cell.close()


# --- injection payloads: value positions round-trip byte-equal ------------


@pytest.mark.parametrize(
    "payload",
    [
        "'; DROP TABLE items; --",
        "\" OR \"1\"=\"1",
        "line1\nline2\ttabbed",
        "back\\slash and 'quote' and \"doublequote\"",
        "unicode: éè龍\U0001F600",
        "null-byte-ish: \\x00 not a real null",
        "%s %% percent literal",
    ],
)
def test_injection_payloads_in_value_positions_round_trip_byte_equal(app_a: types.SimpleNamespace, payload: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"label": payload}}], LIMITS)
        rows = cell.query("items", select=["label"], where=[P("label", "eq", payload)], page_size=10, limits=LIMITS)
        assert rows == [{"label": payload}]
        # And the table is provably intact -- a real injection would have
        # dropped it.
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


# --- transaction rollback --------------------------------------------------


def test_transaction_rollback_leaves_no_partial_effect(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError):
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "first"}},
                    {"operation": "insert", "values": {"unknown_field": "boom"}},
                ],
                LIMITS,
            )
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == []

        # A destructive operation without confirmation also rolls back
        # anything earlier in the same batch (SI-09 + SI-11 together).
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "second"}},
                    {"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "second"}]},
                ],
                LIMITS,
            )
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == []
    finally:
        cell.close()


# --- pool-reset hazard (design D-3) ----------------------------------------


def test_pool_never_leaks_role_or_schema_across_applications(app_a: types.SimpleNamespace, app_b: types.SimpleNamespace) -> None:
    """This project's chosen mitigation for D-3's pool-reset hazard is a
    dedicated per-role connection pool (`r2db_api.postgres._RolePool`) that
    never issues `SET ROLE`/`SET search_path` after connect-time, rather
    than a shared pool with a release-time reset -- see that class's
    docstring for the full reasoning. This test is the executable check: it
    interleaves heavy, repeated use of two different applications' pools and
    asserts every connection drawn from either one reports exactly its own
    fixed role, schema, and *database*, never the other's, even immediately
    after the other pool was exercised. `current_database()` is the
    meaningful differentiator under database-per-application (architecture
    §8) -- `current_schemas(false)` alone would now report `["public"]` for
    both applications, since every application's schema is named `public`
    inside its own database.
    """
    cell_a = make_cell(app_a, pool_size=2)
    cell_b = make_cell(app_b, pool_size=2)
    try:
        for _ in range(20):
            with cell_a._runtime.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false), current_database()")
                    user, schemas, database = cur.fetchone()
                    assert user == app_a.runtime_role
                    assert schemas == [app_a.schema]
                    assert database == app_a.database
                conn.rollback()
            with cell_b._runtime.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false), current_database()")
                    user, schemas, database = cur.fetchone()
                    assert user == app_b.runtime_role
                    assert schemas == [app_b.schema]
                    assert database == app_b.database
                conn.rollback()
            with cell_a._developer.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false), current_database()")
                    user, schemas, database = cur.fetchone()
                    assert user == app_a.developer_role
                    assert schemas == [app_a.schema]
                    assert database == app_a.database
                conn.rollback()
    finally:
        cell_a.close()
        cell_b.close()


def test_statement_timeout_is_wired_to_resource_limits(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        with cell._runtime.connection() as conn:
            with conn.transaction():
                cell._set_timeouts(conn, 200)
                with conn.cursor() as cur:
                    with pytest.raises(psycopg.errors.QueryCanceled):
                        cur.execute("SELECT pg_sleep(2)")
    finally:
        cell.close()


# --- ordinary correctness: catalog, schema ops, mutation semantics --------


def test_catalog_reflects_entities_and_excludes_internal_bookkeeping_table(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        assert cell.catalog() == []
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name", "qty"]}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        assert catalog == [{"entity": "widgets", "fields": ["name", "qty"]}]

        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "color"}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        assert catalog == [{"entity": "widgets", "fields": ["color", "name", "qty"]}]
    finally:
        cell.close()


def test_schema_revision_increments_and_create_entity_conflict(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        first = cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        second = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "name"}, developer=True, limits=LIMITS)
        assert second == first + 1
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
    finally:
        cell.close()


def test_drop_entity_requires_destructive_confirmation(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_entity", "entity": "widgets"}, developer=True, limits=LIMITS)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert any(item["entity"] == "widgets" for item in cell.catalog())
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": "DROP_ENTITY"}, developer=True, limits=LIMITS)
        assert cell.catalog() == []
    finally:
        cell.close()


def test_mutation_operations_insert_update_delete_succeed_and_upsert_is_capability_unsupported(app_a: types.SimpleNamespace) -> None:
    """Contract 1.1.0 (CCR-13, `structured_operations.upsert`): "upsert's
    existence test is the entity's declared domain uniqueness. upsert on an
    entity without a declared uniqueness key ... fail[s] with
    CAPABILITY_UNSUPPORTED." This foundation has no uniqueness-declaration
    mechanism at all yet (`CatalogDocument.entities` is still an untyped
    list), so upsert is unconditionally rejected here rather than executed
    under this implementation's own previous, ad hoc "match on `where`,
    insert if none found" semantics -- exactly the enabled-but-undefined-
    semantics gap CCR-13 was raised against, with this implementation as
    the governed evidence for it (`r2db-api/contracts/
    COMMON_CONTRACT_CHANGE_REQUEST.md`). insert/update/delete are otherwise
    unchanged from before this contract version; only the upsert exercise
    changes shape, from "succeeds" to "is rejected, and rejects the whole
    batch it appears in via failure-before-execution".
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "qty"]}, developer=True, limits=LIMITS)
        affected = cell.transact("items", [{"operation": "insert", "values": {"label": "a", "qty": 1}}], LIMITS)
        assert affected == 1
        affected = cell.transact(
            "items",
            [{"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "a"}], "values": {"qty": 2}}],
            LIMITS,
        )
        assert affected == 1
        rows = cell.query("items", select=["qty"], where=[P("label", "eq", "a")], page_size=10, limits=LIMITS)
        assert rows == [{"qty": 2}]

        # upsert is rejected outright -- and, since it is not the first
        # item, this also confirms it rejects the *whole batch* it appears
        # in (failure-before-execution: `PostgresCell.transact` validates/
        # applies each operation inside one real database transaction, so
        # an earlier operation in the same batch is rolled back along with
        # the rejected one, never partially committed).
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "c", "qty": 3}},
                    {"operation": "upsert", "where": [{"field": "label", "operator": "eq", "value": "b"}], "values": {"label": "b", "qty": 9}},
                ],
                LIMITS,
            )
        assert exc.value.code == "CAPABILITY_UNSUPPORTED"
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == [{"label": "a"}]

        affected = cell.transact(
            "items",
            [{"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "a"}], "destructive": True, "confirmation": "DELETE"}],
            LIMITS,
        )
        assert affected == 1
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == []
    finally:
        cell.close()


def test_query_operators_in_and_contains_and_is_null(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "tag"]}, developer=True, limits=LIMITS)
        cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "alpha", "tag": "x"}},
                {"operation": "insert", "values": {"label": "beta", "tag": "y"}},
                {"operation": "insert", "values": {"label": "gamma"}},
            ],
            LIMITS,
        )
        rows = cell.query("items", select=["label"], where=[P("label", "in", ["alpha", "beta"])], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"alpha", "beta"}

        rows = cell.query("items", select=["label"], where=[P("label", "contains", "et")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"beta"}

        rows = cell.query("items", select=["label"], where=[P("tag", "is_null")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"gamma"}
    finally:
        cell.close()


# --- SharedPoolManager: idle eviction + LRU cap (connection-pooling defect
# fix) --------------------------------------------------------------------
#
# Before this revision, `PostgresCell` gave every application its own two
# `_RolePool`s (`runtime`/`developer`), created lazily but held forever --
# effective cluster-wide consumption was `applications x 2 roles x
# pool_size`, growing without bound as applications were added. The four
# tests below verify the fix (`r2db_api.postgres.SharedPoolManager`) against
# the real cluster's own state, not by inspecting the manager's Python
# dict: an LRU cap that bounds the number of *live pools* independent of
# how many applications exist, idle eviction of pools nobody has used
# recently, a guarantee that eviction never closes a connection some caller
# currently has checked out, and that a pool recreated after eviction still
# authenticates as exactly the one role/database it always did.


def test_shared_pool_manager_lru_cap_bounds_live_connections_independent_of_application_count(platform: types.SimpleNamespace) -> None:
    """The important property (see `SharedPoolManager`'s own docstring in
    `r2db_api/postgres.py`): the cap is on the number of live *pools*, not
    on the number of applications, so consumption stops scaling with
    application count. Six applications share one manager capped at 3 live
    pools; traffic is driven through every application's runtime pool three
    times over (18 requests total, more than the cap could ever hold open
    at once) and the live connection count is then read back from
    `pg_stat_activity`, filtered to exactly these six applications' own
    runtime roles.
    """
    cache_max = 3
    manager = SharedPoolManager(idle_seconds=300, cache_max=cache_max, pool_size=1, pool_max_overflow=0)
    slugs = [f"cap{i}" for i in range(6)]  # double the cap
    with provisioned_apps(platform, slugs) as apps:
        cells = [make_cell(app, pool_manager=manager) for app in apps]
        try:
            for _ in range(3):
                for cell in cells:
                    cell.catalog()

            roles = [app.runtime_role for app in apps]
            counts = _live_connections_by_role(platform.admin_dsn, roles)
            total_live = sum(counts.values())
            distinct_live_roles = len(counts)

            # Without the cap, sustained traffic across all 6 applications
            # would leave up to 6 live runtime connections open at once (one
            # per pool_size=1 pool, never evicted). With the cap, the
            # manager only ever holds `cache_max` pools alive -- checked
            # here as `cache_max + 1` to allow for the same single-call
            # insert-before-evict-next-time transient the reference
            # implementation (`AppPoolManager`) has too, which is still a
            # bound strictly below, and independent of, the application
            # count.
            assert distinct_live_roles <= cache_max + 1, counts
            assert total_live <= cache_max + 1, counts
            assert total_live < len(apps), counts
        finally:
            for cell in cells:
                cell.close()


def test_shared_pool_manager_evicts_idle_pool_and_closes_its_connections(platform: types.SimpleNamespace) -> None:
    """A pool unused for longer than `idle_seconds` is retired -- its queued
    connection is actually closed at the PostgreSQL server (confirmed via
    `pg_stat_activity`), not merely forgotten by `SharedPoolManager`.
    Eviction is swept lazily on the next call into the manager for *any*
    key (matching the reference implementation), so the idle application's
    pool is what accumulates the wait; a second, unrelated application's
    pool is what actually triggers the sweep that finds and evicts it --
    exactly as ordinary unrelated traffic would in production.
    """
    manager = SharedPoolManager(idle_seconds=1, cache_max=10, pool_size=1, pool_max_overflow=0)
    with provisioned_apps(platform, ["idlepool", "otherpool"]) as (app_idle, app_other):
        cell_idle = make_cell(app_idle, pool_manager=manager)
        cell_other = make_cell(app_other, pool_manager=manager)
        try:
            cell_idle.catalog()  # opens and queues one runtime connection

            before = _live_connections_by_role(platform.admin_dsn, [app_idle.runtime_role])
            assert before.get(app_idle.runtime_role, 0) >= 1

            time.sleep(1.3)  # exceed idle_seconds=1

            cell_other.catalog()  # unrelated traffic triggers the sweep

            after = _live_connections_by_role(platform.admin_dsn, [app_idle.runtime_role])
            assert after.get(app_idle.runtime_role, 0) == 0
        finally:
            cell_idle.close()
            cell_other.close()


def test_eviction_never_closes_a_checked_out_connection(platform: types.SimpleNamespace) -> None:
    """The correctness property that matters most here: evicting a pool
    must never close a connection some caller currently has checked out --
    doing so would surface as a random failure mid-transaction under real
    load. A background thread holds application X's only connection open
    across a `pg_sleep`, simulating an in-flight operation; while it is
    held, the main thread forces `SharedPoolManager` (capped at 1 live
    pool) to evict X's pool in favour of application Y's. The background
    operation must complete exactly as if nothing had happened.
    """
    manager = SharedPoolManager(idle_seconds=300, cache_max=1, pool_size=1, pool_max_overflow=0)
    with provisioned_apps(platform, ["evictx", "evicty"]) as (app_x, app_y):
        cell_x = make_cell(app_x, pool_manager=manager)
        cell_y = make_cell(app_y, pool_manager=manager)
        try:
            holding = threading.Event()
            result: dict = {}

            def hold_connection() -> None:
                try:
                    with cell_x._runtime.connection() as conn:
                        with conn.cursor() as cur:
                            holding.set()
                            cur.execute("SELECT pg_sleep(1.5)")
                            cur.execute("SELECT 1")
                            result["value"] = cur.fetchone()[0]
                    result["ok"] = True
                except Exception as exc:  # pragma: no cover - asserted below
                    result["ok"] = False
                    result["error"] = repr(exc)

            worker = threading.Thread(target=hold_connection)
            worker.start()
            assert holding.wait(timeout=5), "background thread never acquired its connection"

            # X's pool is the manager's only live entry (cache_max=1), its
            # one connection checked out by the background thread. Force
            # its eviction while that connection is still in flight: the
            # first call registers Y's pool (cache grows to 2 -- the same
            # insert-before-evict-next-time step as the cap test above), the
            # second call sweeps and evicts the least-recently-used entry,
            # which is X.
            cell_y.catalog()
            cell_y.catalog()

            worker.join(timeout=10)
            assert not worker.is_alive(), "background query never completed"
            assert result.get("ok") is True, result.get("error")
            assert result.get("value") == 1
        finally:
            cell_x.close()
            cell_y.close()


def test_isolation_holds_after_pool_eviction_and_recreation(platform: types.SimpleNamespace) -> None:
    """Cross-application isolation (D-3/§10.1: one fixed role per pool,
    never `SET ROLE`) must survive a pool being evicted and later
    recreated. Application A's pool is forced out of a `cache_max=1`
    manager by application B's traffic, confirmed gone from `pg_stat_
    activity`, and then A is used again -- the manager must transparently
    create a fresh pool that still authenticates as exactly A's own
    runtime role against exactly A's own database, and A's own previously
    written data must still be readable through it.
    """
    manager = SharedPoolManager(idle_seconds=300, cache_max=1, pool_size=1, pool_max_overflow=0)
    with provisioned_apps(platform, ["reauth_a", "reauth_b"]) as (app_a2, app_b2):
        cell_a = make_cell(app_a2, pool_manager=manager)
        try:
            cell_a.apply_schema({"operation": "create_entity", "entity": "secrets", "fields": ["value"]}, developer=True, limits=LIMITS)
            cell_a.transact("secrets", [{"operation": "insert", "values": {"value": "app-a-only"}}], LIMITS)

            cell_b = make_cell(app_b2, pool_manager=manager)
            try:
                # Force eviction of A's pool via the LRU cap, same two-call
                # pattern as the checked-out-connection test above.
                cell_b.catalog()
                cell_b.catalog()

                after_evict = _live_connections_by_role(platform.admin_dsn, [app_a2.runtime_role])
                assert after_evict.get(app_a2.runtime_role, 0) == 0

                # The next use of A must transparently recreate its pool --
                # same DSN, so it must still authenticate as exactly A's own
                # fixed role against A's own database.
                with cell_a._runtime.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT current_user, current_database()")
                        user, database = cur.fetchone()
                        assert user == app_a2.runtime_role
                        assert database == app_a2.database
                    conn.rollback()

                rows = cell_a.query("secrets", select=["value"], where=[], page_size=10, limits=LIMITS)
                assert rows == [{"value": "app-a-only"}]

                # B's cell, sharing the same manager, still cannot see A's
                # data.
                assert cell_b.catalog() == []
            finally:
                cell_b.close()
        finally:
            cell_a.close()


# --- `_RolePool` connect-failure accounting (fixed regression) ------------


_UNREACHABLE_DSN = "host=127.0.0.1 port=1 dbname=nope user=nope password=nope"


def test_role_pool_never_hangs_after_repeated_connect_failures_and_recovers() -> None:
    """Regression test for a real, previously-shipped bug in `_RolePool.
    _acquire`: `self._created` used to be incremented *before* calling
    `self._connect()`, with no rollback on failure, and `self._connect()`
    itself ran while `self._lock` was held. `maxconn` consecutive connect
    failures against an unreachable target therefore permanently pinned
    `_created` at `maxconn` -- every later `_acquire()` call fell straight
    through to an untimed `self._queue.get()` and blocked forever, with no
    way to recover even once the target became reachable again (nothing was
    ever queued). Reported by review against real, measured behaviour:
    unreachable DSN + `pool_size=2` blocked the 3rd `authenticate()` call
    permanently.

    Fixed by: (1) releasing the reserved slot on a failed `_connect()`
    (`_created -= 1`), (2) calling `_connect()` outside `self._lock`, and
    (3) giving both connection attempts (`connect_timeout`) and waiting for
    a pooled connection to free up (`acquire_timeout`) real, bounded
    timeouts -- a timed-out wait now raises `psycopg.OperationalError`
    (the same type a genuine failed connection raises), rather than hanging
    the calling thread indefinitely.

    This test's own worker thread runs `daemon=True` and is bounded with a
    `join(timeout=...)` specifically so that *this test itself* cannot hang
    the suite even if this exact regression reappears -- a `TimeoutError`-
    shaped assertion failure is the worst case, never an unbounded wait.
    """
    pool = _RolePool(_UNREACHABLE_DSN, schema="public", maxconn=2, connect_timeout=1, acquire_timeout=1)
    try:
        # The first `maxconn` acquisitions each take the "reserve a slot,
        # try to connect" path. Port 1 on loopback refuses immediately
        # (`ECONNREFUSED`) rather than timing out, so these return fast
        # regardless of `connect_timeout` -- the bug this test is about is
        # in what happens *after* these fail, not in how long they take.
        for _ in range(2):
            with pytest.raises(psycopg.OperationalError):
                with pool.connection():
                    pass

        # Before the fix, `_created` was left pinned at `maxconn` by the
        # two failures above, so this third acquisition fell through to an
        # untimed `queue.Queue.get()` and never returned at all. Run it on
        # a background thread with a bounded join so a reintroduced
        # regression fails this assertion instead of hanging pytest.
        outcome: list[BaseException | None] = []

        def attempt() -> None:
            try:
                with pool.connection():
                    pass
            except BaseException as exc:  # noqa: BLE001 - captured for the main thread's assertions
                outcome.append(exc)
            else:
                outcome.append(None)

        worker = threading.Thread(target=attempt, daemon=True)
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive(), (
            "pool.connection() did not return within 5s after maxconn connect failures -- "
            "this is the _created-leak hang regression this test guards against"
        )
        assert len(outcome) == 1
        assert isinstance(outcome[0], psycopg.OperationalError)

        # Recovery: point this same pool instance at a real, reachable
        # target -- an operator would observe this as "the network/platform
        # DB outage cleared" -- and confirm a connection can still be
        # created. This is only possible if `_created` was correctly rolled
        # back on each failure above; if it had stayed pinned at `maxconn`
        # (the bug), this would time out identically to the blocked
        # attempt above, `acquire_timeout` notwithstanding, since nothing
        # would ever have been queued.
        pool._dsn = _admin_dsn()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone() == (1,)
    finally:
        pool.close_all()
