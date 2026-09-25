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

import base64
import json
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

from r2db_api import platform_upgrades
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell, SharedPoolManager, _RolePool
from r2db_api.structured import ApplicationCell, Predicate, encode_page_cursor

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def test_admin_dsn_requires_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-44 WP-3 (a) completion condition 7: `_admin_dsn()` raises when
    `R2DB_TEST_ADMIN_DSN` is unset or empty -- there is no shared-cluster
    default to fall back to any more (design D-4)."""
    monkeypatch.delenv(ADMIN_DSN_ENV, raising=False)
    with pytest.raises(RuntimeError):
        _admin_dsn()

    monkeypatch.setenv(ADMIN_DSN_ENV, "")
    with pytest.raises(RuntimeError):
        _admin_dsn()


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
            f"{ADMIN_DSN_ENV} is set by tools/testpg/dsa_testpg.py for each "
            "test run; there is no shared-cluster default. These tests must "
            "not be skipped (§5.3 C-5).",
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
    `0004_deprovision_application.sql`'s own (unchanged) terminate
    statement is (design docs/design/DEPROVISION_FORCED_DROP_V0_1.md
    D-2R stage (5) -- the earlier stages that design added do not call
    `pg_terminate_backend` at all): this admin connection authenticates as
    the OS/cluster superuser locally, so it *could* terminate a background
    worker too, but a freshly churned database routinely has an autovacuum
    worker visiting it, and terminating that is unnecessary -- it finishes
    on its own well within this retry loop's backoff, which is what
    actually clears the `ObjectInUse` in that case.
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
    provisioned").

    Retrying the entire script from the top remains safe after design D-2R
    (`docs/design/DEPROVISION_FORCED_DROP_V0_1.md` §4.1) added the
    live-connection pre-check/temporary-grant/`ALLOW_CONNECTIONS` stages
    this race can now fail past: a failed attempt that reached `DROP
    DATABASE` already ran those earlier stages, so -- unlike this
    docstring's own previous claim that "`begin_deprovision_application`,
    a plain `SELECT` with no side effect, is the only step that ran" --
    the state left behind is no longer exactly as it was: the registry row
    itself is untouched (still exactly as it was before this function was
    called -- only `finish_deprovision_application`, at the very end,
    removes it), but the database is left non-connectable and the
    temporary self-grant is left standing. It is still safe to retry from
    the top: the `ALTER DATABASE` stage's own `pg_database` existence
    check (design F-1) is idempotent, the `GRANT` stage on an
    already-granted role is a harmless no-op, and the registry row (and
    both roles) are still there for the next attempt to finish removing --
    the §4.1 table documents this state and its manual fallback in full.
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


# --- R-54: 0004's live-connection handling (design docs/design/ ----------
# --- DEPROVISION_FORCED_DROP_V0_1.md v1.0, D-1/D-2R) -----------------------


def test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection(platform: types.SimpleNamespace) -> None:
    """Completion condition 1 (design D-1/D-2R, H-1): a runtime-role
    connection stays open across the whole deprovision attempt -- 0004's
    stage (3) temporary self-grant plus its existing stage (5) narrowed
    terminate close it out, so `_run_psql` (deliberately not
    `deprovision_app`, whose own retry loop would hide whether a single
    attempt already succeeds) can run 0004 against the control DSN exactly
    once, with no retry, and it succeeds. Uses its own throwaway
    application (not `app_a`/`app_b`) so this test's own single attempt is
    the only deprovision call made for it."""
    app = provision_app(platform, "live_conn_app")
    live_conn = psycopg.connect(app.runtime_dsn)
    try:
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": "live_conn_app"})
    finally:
        try:
            live_conn.close()
        except Exception:
            pass


def test_0004_allow_connections_false_is_between_the_temporary_grant_and_terminate() -> None:
    """Completion condition 2 (design D-2R stage (4)): a structural check
    on `0004_deprovision_application.sql`'s own source text -- the
    `ALLOW_CONNECTIONS false` statement must appear after the temporary
    self-grant stage and before the existing narrowed `pg_terminate_
    backend` statement. Behavioural backing is design H-1's own quoted
    single-session run, in that same order, not re-exercised here. Code
    review round 1 addendum (c): searches a comment-stripped copy of the
    text (every line that starts with `--`, leading whitespace ignored,
    is dropped first) so a future prose comment mentioning these same
    words in a different order can never satisfy this pin -- only the
    real SQL can."""
    raw_text = (MIGRATIONS_DIR / "0004_deprovision_application.sql").read_text()
    text = "\n".join(line for line in raw_text.splitlines() if not line.strip().startswith("--"))
    grant_index = text.find("SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role')")
    allow_connections_index = text.find("WITH ALLOW_CONNECTIONS false")
    terminate_index = text.find(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'database_name' "
        "AND pid <> pg_backend_pid() AND backend_type = 'client backend';"
    )
    assert grant_index != -1
    assert allow_connections_index != -1
    assert terminate_index != -1
    assert grant_index < allow_connections_index < terminate_index


def test_deprovision_leaves_no_role_or_executor_membership_behind(platform: types.SimpleNamespace) -> None:
    """Completion condition 3 (design D-1/D-3, M-7/M-13's own "membership
    残り0行"): after a normal deprovision (no stalled live connection),
    both this application's roles are gone from `pg_roles`, and
    `r2dbsvc_control` holds no `inherit_option = true` row in
    `pg_auth_members` as the *member* side -- the same accounting
    `MitateDB-api/tests/test_application_audit.py::test_new_auditreader_
    role_has_no_memberships`'s own analogous check uses, narrowed to
    `inherit_option = true` because that is the one property D-1's own
    grant sets that the baseline `CREATE ROLE`-implicit ADMIN OPTION row
    (inherit_option = false, M-7) never does, so this stays 0 regardless
    of any other application this module-scoped fixture has provisioned.
    The temporary self-grant D-1 adds does not outlive the `DROP ROLE`
    that follows it on the normal path. The membership assert runs before
    the `pg_roles` residual assert below so that removing only the `DROP
    ROLE` step for `runtime_role` (M3) fails at the membership assert
    itself, not merely at the role-residual assert (code review round 1,
    item 1)."""
    app = provision_app(platform, "membership_check_app")
    conn = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", [app.runtime_role, app.developer_role])
            assert {row[0] for row in cur.fetchall()} == {app.runtime_role, app.developer_role}
    finally:
        conn.close()

    deprovision_app(platform, "membership_check_app")

    conn = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON m.member = r.oid "
                "WHERE r.rolname = %s AND m.inherit_option = true",
                [platform.control_role],
            )
            assert cur.fetchone()[0] == 0
        with conn.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", [app.runtime_role, app.developer_role])
            assert cur.fetchall() == []
    finally:
        conn.close()


def test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role(platform: types.SimpleNamespace) -> None:
    """Completion condition 4 (design D-2R stage (2), H-2): a normal LOGIN
    role that is neither this application's runtime/developer role nor
    the executing (control) role, holding a connection to this
    application's database, makes 0004 raise before any of its later
    stages run -- the database, its `datallowconn`, the executing role's
    own `inherit_option = true` membership count (D-1's own grant marker,
    see `test_deprovision_leaves_no_role_or_executor_membership_behind`'s
    own docstring for why that -- not a raw row count -- is what stays 0
    here), and the registry row are all exactly as before. Design §6.1
    pins only "it stopped" and "nothing changed" -- not PostgreSQL's own
    `DETAIL:` text."""
    app = provision_app(platform, "third_party_conn_app")
    registry_schema = f"{platform.prefix}_registry"
    other_role = f"{platform.prefix}_third_party_reader"
    other_password = secrets.token_urlsafe(24)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    other_conn = None
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(other_role), sql.Literal(other_password)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(app.database), sql.Identifier(other_role)))
        other_dsn = _dsn_with(platform.admin_dsn, user=other_role, password=other_password, dbname=app.database)
        other_conn = psycopg.connect(other_dsn)

        with pytest.raises(RuntimeError):
            _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": "third_party_conn_app"})

        with admin.cursor() as cur:
            cur.execute("SELECT datallowconn FROM pg_database WHERE datname = %s", [app.database])
            assert cur.fetchone() == (True,)
            cur.execute(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON m.member = r.oid "
                "WHERE r.rolname = %s AND m.inherit_option = true",
                [platform.control_role],
            )
            assert cur.fetchone()[0] == 0

        control_conn = psycopg.connect(platform.control_dsn)
        try:
            with control_conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE application_slug = %s").format(
                        sql.Identifier(registry_schema, "applications")
                    ),
                    ["third_party_conn_app"],
                )
                assert cur.fetchone()[0] == 1
        finally:
            control_conn.close()
    finally:
        if other_conn is not None:
            other_conn.close()
        with admin.cursor() as cur:
            cur.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(sql.Identifier(app.database), sql.Identifier(other_role)))
            cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(other_role)))
        admin.close()

    deprovision_app(platform, "third_party_conn_app")


def test_0004_temporary_grant_uses_inherit_true_set_false() -> None:
    """Completion condition 5 (design D-2R stage (3)): a structural check
    on `0004_deprovision_application.sql`'s own source text -- the
    temporary self-grant must be written `WITH INHERIT TRUE, SET FALSE`,
    for both roles it can grant. Behavioural backing is design M-9's own
    quoted measurement of this exact form, not re-exercised here. Code
    review round 1 addendum (c): searches a comment-stripped copy of the
    text (every line that starts with `--`, leading whitespace ignored,
    is dropped first), the same hardening
    `test_0004_allow_connections_false_is_between_the_temporary_grant_and_
    terminate` applies, above."""
    raw_text = (MIGRATIONS_DIR / "0004_deprovision_application.sql").read_text()
    text = "\n".join(line for line in raw_text.splitlines() if not line.strip().startswith("--"))
    assert text.count("GRANT %I TO CURRENT_USER WITH INHERIT TRUE, SET FALSE") == 2


def test_deprovision_completes_on_rerun_after_the_database_was_already_dropped(platform: types.SimpleNamespace) -> None:
    """Completion condition 6 (design §4.1 row 3, F-1): simulates 0004
    having already gotten through `DROP DATABASE` on some earlier attempt
    that then failed before `DROP ROLE`/`finish_deprovision_application`
    ran (a stalled lock/statement timeout, a killed psql, etc.) --
    database gone, both roles and the registry row still there -- by
    dropping the database directly and then running 0004 once more:
    stage (4)'s own `pg_database` existence check (F-1) must skip the
    `ALTER DATABASE` rather than fail on a database that no longer
    exists, and the rest of the script must still complete."""
    app = provision_app(platform, "predropped_db_app")
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(app.database)))
    finally:
        admin.close()

    _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": "predropped_db_app"})

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", [app.runtime_role, app.developer_role])
            assert cur.fetchall() == []
    finally:
        admin.close()


LIMITS = ResourceLimits()


# --- destructive-confirmation phrase probes (WP-3, declare-and-echo -------
# effectivization): the old fixed tokens "DELETE"/"DROP_ENTITY"/"DROP_INDEX"
# this WP retires are replaced everywhere below with a real probe -> echo
# round trip against `PostgresCell` itself -- a plain unconfirmed attempt
# (`destructive: True`, no `confirmation`) is always denied with
# `DESTRUCTIVE_CONFIRMATION_REQUIRED` and never mutates anything, so
# reading the real, currently-valid phrase off that denial's own
# `details["required_confirmation"]` and echoing it back is the same
# protocol a real client (and this repository's own conformance suite,
# `adapter.resolve_valid_confirmation`) uses -- never a hand-rolled digest/
# revision computation that could silently drift from the real
# implementation. ------------------------------------------------------


def _delete_phrase(cell: PostgresCell, entity: str, where: list[dict]) -> str:
    with pytest.raises(FoundationError) as exc:
        cell.transact(entity, [{"operation": "delete", "where": where, "destructive": True}], LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    return exc.value.details["required_confirmation"]


def _drop_entity_phrase(cell: PostgresCell, entity: str) -> str:
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_entity", "entity": entity, "destructive": True}, developer=True, limits=LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    return exc.value.details["required_confirmation"]


def _drop_index_phrase(cell: PostgresCell, entity: str, index: str) -> str:
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "drop_index", "entity": entity, "index": index, "destructive": True}, developer=True, limits=LIMITS)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    return exc.value.details["required_confirmation"]


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
# Q4 WP-3 (design D-3(a)): the per-application platform-upgrade ledger
# `0003`/`0009` now also provision unconditionally into every application
# database -- excluded below for the identical reason, so `_real_table_
# names`' own "nothing but what THIS test created" assertions stay true.
# Phase 9 WP-2a/WP-2c: `0003`/`0010`/`0011` likewise now unconditionally
# provision the field-constraints and idempotency-record side tables.
_BOOKKEEPING_TABLES = (_REVISION_TABLE, "_r2db_platform_upgrades", "_r2db_field_constraints", "_r2db_idempotency")


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
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE' AND table_name <> ALL(%s)",
                [schema, list(_BOOKKEEPING_TABLES)],
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


def test_create_entity_rejects_audit_events_by_exact_match_only(app_a: types.SimpleNamespace) -> None:
    """WP-2(b) review B-2 (supervisor ruling): the Postgres backend's own
    defense-in-depth check (`postgres.py`'s `apply_schema`, alongside the
    shared, load-bearing `structured.bind_schema_operation` check both
    cell implementations already go through)."""
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "audit_events"}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        # Exact match only -- a superstring is accepted.
        cell.apply_schema({"operation": "create_entity", "entity": "audit_events_archive"}, developer=True, limits=LIMITS)
        assert any(item["entity"] == "audit_events_archive" for item in cell.catalog())
    finally:
        cell.close()


def test_audit_events_is_reserved_at_every_entity_identifier_position_postgres(app_a: types.SimpleNamespace) -> None:
    """WP-2(b) fix round 2 (coordinator item C), `PostgresCell`'s own
    counterpart to `test_foundation.py`'s identically-named test: add_field/
    drop_entity/create_index/drop_index (via the shared `structured.
    bind_schema_operation` choke) and query/mutate (via `PostgresCell`'s
    own direct checks) all refuse `audit_events` before ever reaching a
    NOT_FOUND/catalog lookup."""
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "add_field", "entity": "audit_events", "field": "x"}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"

        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_entity", "entity": "audit_events", "destructive": True, "confirmation": "whatever"}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"

        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_index", "entity": "audit_events", "index": "ix1", "fields": ["x"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"

        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_index", "entity": "audit_events", "index": "ix1"}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"

        with pytest.raises(FoundationError) as exc:
            cell.query("audit_events", select=["id"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"

        with pytest.raises(FoundationError) as exc:
            cell.transact("audit_events", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
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
        # R-1: every entity table also carries the server-provisioned `id`
        # (selectable) and `_r2db_revision` (invisible) columns now.
        assert _real_column_names(app_a.developer_dsn, app_a.schema, "items") == {"id", "_r2db_revision", "label"}
        assert cell.catalog()[0]["fields"] == ["id", "label"]
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
        assert rows.items == [{"label": payload}]
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
        assert rows.items == []

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
        assert rows.items == []
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


# --- catalog carries a per-transaction statement bound, like the other 3 ---
# --- client-reachable operations (`query`/`transact`/`apply_schema`) -------


def test_catalog_wires_statement_and_lock_timeout_to_the_passed_resource_limits(app_a: types.SimpleNamespace) -> None:
    """`catalog(limits=...)` enters `_load_catalog`'s own transaction only
    after `_set_timeouts` has run -- the effective `statement_timeout`/
    `lock_timeout` PostgreSQL reports for that same connection, inside that
    same transaction, is the exact `f"{timeout_ms}ms"` `_set_timeouts`
    composes from `limits.execution_ms`. `_load_catalog` is swapped out for
    a probe that reads `pg_settings.setting` directly (never `SHOW`, never
    the SQL text `_set_timeouts` issues) so this observes the live session
    state a timeout would actually be enforced against.
    """
    cell = make_cell(app_a)
    captured: dict[str, str] = {}

    def probing_load_catalog(self: PostgresCell, conn: "psycopg.Connection", *, with_constraints: bool = True) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
            captured["statement_timeout"] = cur.fetchone()[0]
            cur.execute("SELECT setting FROM pg_settings WHERE name = 'lock_timeout'")
            captured["lock_timeout"] = cur.fetchone()[0]
        return {}

    try:
        limits = ResourceLimits(execution_ms=1234)
        original = PostgresCell._load_catalog
        PostgresCell._load_catalog = probing_load_catalog
        try:
            assert cell.catalog(limits=limits) == []
        finally:
            PostgresCell._load_catalog = original
        assert captured["statement_timeout"] == "1234"
        assert captured["lock_timeout"] == "1234"
    finally:
        cell.close()


def test_catalog_without_an_explicit_limits_argument_uses_default_resource_limits(app_a: types.SimpleNamespace) -> None:
    """A bare `cell.catalog()` -- the shape every existing direct call site
    in this file already uses -- still carries a bound: the observed
    `statement_timeout` is the default `ResourceLimits().execution_ms`,
    read the same way (live `pg_settings.setting`) as the explicit-`limits`
    case above, never a proxy such as "non-zero"."""
    cell = make_cell(app_a)
    captured: dict[str, str] = {}

    def probing_load_catalog(self: PostgresCell, conn: "psycopg.Connection", *, with_constraints: bool = True) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
            captured["statement_timeout"] = cur.fetchone()[0]
        return {}

    try:
        original = PostgresCell._load_catalog
        PostgresCell._load_catalog = probing_load_catalog
        try:
            assert cell.catalog() == []
        finally:
            PostgresCell._load_catalog = original
        assert captured["statement_timeout"] == str(ResourceLimits().execution_ms)
    finally:
        cell.close()


def test_catalog_set_local_timeouts_do_not_leak_to_the_next_transaction(app_a: types.SimpleNamespace) -> None:
    """`_set_timeouts` uses `SET LOCAL`, so a bound set for one `catalog`
    transaction must not survive into the next transaction run over the
    SAME pooled connection. `pool_size=1` pins this cell to exactly one
    physical connection; the probe also records `id(conn)` so both the
    baseline read below and the second, directly-opened transaction after
    `catalog()` are proven to be the very same connection object `catalog`
    itself used, not merely "a" connection from a same-sized pool. The
    baseline is read from that SAME connection, before `catalog()` ever
    runs `SET LOCAL` on it, so the comparison never assumes the cluster's
    own default is `0` -- it only checks that whatever the connection
    carried before `catalog()` is what it carries again afterward."""
    cell = make_cell(app_a, pool_size=1)
    captured: dict[str, object] = {}

    def probing_load_catalog(self: PostgresCell, conn: "psycopg.Connection", *, with_constraints: bool = True) -> dict:
        captured["conn_id"] = id(conn)
        return {}

    try:
        with cell._runtime.connection() as conn:
            baseline_conn_id = id(conn)
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                    baseline_statement_timeout = cur.fetchone()[0]
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'lock_timeout'")
                    baseline_lock_timeout = cur.fetchone()[0]

        original = PostgresCell._load_catalog
        PostgresCell._load_catalog = probing_load_catalog
        try:
            cell.catalog(limits=ResourceLimits(execution_ms=1234))
        finally:
            PostgresCell._load_catalog = original
        assert captured["conn_id"] == baseline_conn_id

        with cell._runtime.connection() as conn:
            assert id(conn) == baseline_conn_id
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                    statement_timeout = cur.fetchone()[0]
                    cur.execute("SELECT setting FROM pg_settings WHERE name = 'lock_timeout'")
                    lock_timeout = cur.fetchone()[0]
        assert statement_timeout == baseline_statement_timeout
        assert lock_timeout == baseline_lock_timeout
    finally:
        cell.close()


def test_catalog_maps_timeout_and_lock_conflicts_to_limit_exceeded(app_a: types.SimpleNamespace) -> None:
    """`catalog`'s transaction maps `psycopg.errors.QueryCanceled`/
    `LockNotAvailable` to the same `LIMIT_EXCEEDED` (413, `resource`/
    `limit_class` = `execution_ms`, `limit` = `limits.execution_ms`)
    `query`/`transact`/`apply_schema` already return, rather than falling
    through to a generic `SERVICE_UNAVAILABLE`. Two routes are exercised,
    each with `_load_catalog` swapped out: (i) an actual `pg_sleep` inside
    the same transaction, genuinely cancelled by the short timeout; (ii) a
    directly raised `LockNotAvailable`, observing only the mapping."""
    cell = make_cell(app_a)
    limits = ResourceLimits(execution_ms=200)

    def slow_load_catalog(self: PostgresCell, conn: "psycopg.Connection", *, with_constraints: bool = True) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_sleep(2)")
        return {}

    def lock_conflict_load_catalog(self: PostgresCell, conn: "psycopg.Connection", *, with_constraints: bool = True) -> dict:
        raise psycopg.errors.LockNotAvailable("simulated lock conflict")

    try:
        original = PostgresCell._load_catalog
        PostgresCell._load_catalog = slow_load_catalog
        try:
            with pytest.raises(FoundationError) as exc:
                cell.catalog(limits=limits)
        finally:
            PostgresCell._load_catalog = original
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 413
        assert exc.value.details == {"resource": "execution_ms", "limit_class": "execution_ms", "limit": 200}

        PostgresCell._load_catalog = lock_conflict_load_catalog
        try:
            with pytest.raises(FoundationError) as lock_exc:
                cell.catalog(limits=limits)
        finally:
            PostgresCell._load_catalog = original
        assert lock_exc.value.code == "LIMIT_EXCEEDED"
        assert lock_exc.value.status == 413
        assert lock_exc.value.details == {"resource": "execution_ms", "limit_class": "execution_ms", "limit": 200}
    finally:
        cell.close()


# --- ordinary correctness: catalog, schema ops, mutation semantics --------


def test_catalog_reflects_entities_and_excludes_internal_bookkeeping_table(app_a: types.SimpleNamespace) -> None:
    """CCR-13 §2/R-1: `catalog()` now publishes the full `EntityDescriptor`
    shape -- the same one `ApplicationCell.catalog()` publishes -- not just
    `{entity, fields}`. `id` appears in `fields` (visible, R-3 property 2);
    `_r2db_revision` never does (R-3/R-4)."""
    cell = make_cell(app_a)
    try:
        assert cell.catalog() == []
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name", "qty"]}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        # Phase 6 WP-2 (design D-3(iii)): `field_types` -- `name`/`qty` were
        # created with no declared type (JSONB), so they report `json`
        # (decision (ii)'s default); `id` is always `integer`.
        assert catalog == [
            {
                "entity": "widgets",
                "fields": ["id", "name", "qty"],
                "field_types": {"id": "integer", "name": "json", "qty": "json"},
                # Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints`,
                # total, `nullable: true` and no `enum` (nothing declared).
                "field_constraints": {"id": {"nullable": True}, "name": {"nullable": True}, "qty": {"nullable": True}},
                "mutation_class": "mutable",
                "address_fields": ["id"],
                "address_reuse": "never",
                "unique_keys": [],
            }
        ]

        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "color"}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        assert catalog[0]["fields"] == ["color", "id", "name", "qty"]

        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "by_color", "fields": ["color"], "unique": True}, developer=True, limits=LIMITS)
        assert cell.catalog()[0]["unique_keys"] == [{"name": "by_color", "fields": ["color"]}]
    finally:
        cell.close()


def test_schema_revision_increments_and_create_entity_conflict(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        first = cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS).revision
        second = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "name"}, developer=True, limits=LIMITS).revision
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
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": _drop_entity_phrase(cell, "widgets")}, developer=True, limits=LIMITS)
        assert cell.catalog() == []
    finally:
        cell.close()


def test_mutation_operations_insert_update_delete_succeed_and_upsert_is_capability_unsupported(app_a: types.SimpleNamespace) -> None:
    """Contract 1.1.0 (CCR-13, `structured_operations.upsert`): "upsert's
    existence test is the entity's declared domain uniqueness. upsert on an
    entity without a declared uniqueness key ... fail[s] with
    CAPABILITY_UNSUPPORTED." `items` here declares no unique key, so upsert
    is rejected via the real (WP-3) catalog-driven check -- `_apply_upsert`
    finds no declared uniqueness key and refuses before even looking at the
    operation's own `where`/`values` -- exactly like `ApplicationCell`. See
    `test_upsert_*` below for the full suite of executable-upsert branches
    (a declared key resolving to insert/update, multi-key selection,
    `expected_revision`, the other-key CONFLICT case, etc). insert/update/
    delete are otherwise unchanged from before this contract version; only
    the upsert exercise changes shape, from "succeeds" (pre-CCR-13) to "is
    rejected, and rejects the whole batch it appears in via failure-before-
    execution".
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "qty"]}, developer=True, limits=LIMITS)
        outcome = cell.transact("items", [{"operation": "insert", "values": {"label": "a", "qty": 1}}], LIMITS)
        assert outcome.affected == 1
        outcome = cell.transact(
            "items",
            [{"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "a"}], "values": {"qty": 2}}],
            LIMITS,
        )
        assert outcome.affected == 1
        rows = cell.query("items", select=["qty"], where=[P("label", "eq", "a")], page_size=10, limits=LIMITS)
        assert rows.items == [{"qty": 2}]

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
        assert rows.items == [{"label": "a"}]

        delete_where = [{"field": "label", "operator": "eq", "value": "a"}]
        outcome = cell.transact(
            "items",
            [{"operation": "delete", "where": delete_where, "destructive": True, "confirmation": _delete_phrase(cell, "items", delete_where)}],
            LIMITS,
        )
        assert outcome.affected == 1
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == []
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
        assert {r["label"] for r in rows.items} == {"alpha", "beta"}

        rows = cell.query("items", select=["label"], where=[P("label", "contains", "et")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"beta"}

        rows = cell.query("items", select=["label"], where=[P("tag", "is_null")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"gamma"}
    finally:
        cell.close()


# --- CCR-13 §0.5 Q-2: `contains` literal semantics, `matches` wildcard,
# and non-disclosure of PostgreSQL's LIKE-escaping mechanics ---------------


def test_escape_like_literal_leaf_preserves_facade_and_escape_order() -> None:
    from r2db_api.postgres import _escape_like_literal
    from r2db_api.postgres_like import _escape_like_literal as leaf_escape_like_literal

    assert _escape_like_literal is leaf_escape_like_literal
    assert _escape_like_literal(r"a\\%_b") == "a" + "\\" * 5 + "%" + "\\" + "_b"


def test_contains_is_a_literal_substring_and_never_interprets_wildcards(app_a: types.SimpleNamespace) -> None:
    """Q-2 (案i): `%`/`_`/`\\` in the *value* must never be interpreted as a
    LIKE wildcard -- a row literally containing a percent sign must be
    found by a `contains` search for that literal percent sign, and a row
    that merely happens to match the *wildcard interpretation* of the
    search text must NOT be found unless it also matches literally."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "50% off"}},
                {"operation": "insert", "values": {"label": "50X off"}},
                {"operation": "insert", "values": {"label": "under_score"}},
                {"operation": "insert", "values": {"label": "underxscore"}},
            ],
            LIMITS,
        )
        rows = cell.query("items", select=["label"], where=[P("label", "contains", "50%")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"50% off"}  # not "50X off", which a LIKE wildcard would also match

        rows = cell.query("items", select=["label"], where=[P("label", "contains", "er_sc")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"under_score"}  # not "underxscore"
    finally:
        cell.close()


def test_matches_wildcard_semantics_and_case_sensitivity(app_a: types.SimpleNamespace) -> None:
    """Q-2 (補足案): `%` = any sequence (including empty), `_` = exactly one
    character, `\\` escapes the following character; both operators are
    case-sensitive."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "hello"}},
                {"operation": "insert", "values": {"label": "help"}},
                {"operation": "insert", "values": {"label": "HELLO"}},
                {"operation": "insert", "values": {"label": "hxllo"}},
                {"operation": "insert", "values": {"label": "100% sure"}},
            ],
            LIMITS,
        )
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "hel%")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"hello", "help"}  # not "HELLO" (case-sensitive)

        rows = cell.query("items", select=["label"], where=[P("label", "matches", "h_llo")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"hello", "hxllo"}

        # A literal `%` in the pattern, escaped, matches only that literal
        # character -- not "any sequence".
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "100\\% sure")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows.items} == {"100% sure"}
    finally:
        cell.close()


def test_contains_and_matches_reject_non_string_values(app_a: types.SimpleNamespace) -> None:
    """Q-2: both operators' value is always a plain string, independent of
    the target field's own declared type."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["label"], where=[P("label", "contains", 5)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["label"], where=[P("label", "matches", 5)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


# ==========================================================================
# CCR-13 WP-3 (docs/design/R2DB_CCR13_STORAGE_V1.md): `PostgresCell`'s real
# implementation of typed columns, indexes/uniqueness, upsert, revision
# preconditions, order_by, and cursor pagination. Mirrors the granularity of
# `test_foundation.py`'s own WP-2 test suite for `ApplicationCell` -- the
# same semantics, error codes, and precedence, verified against a real
# PostgreSQL server this time.
# ==========================================================================


def _row_revision(cell: PostgresCell, entity: str, row_id: int) -> str:
    rows = cell.query(entity, select=["id"], where=[P("id", "eq", row_id)], page_size=10, limits=LIMITS)
    return rows.revisions[0]


# --- typed columns (R-2/R-7) ------------------------------------------------


def test_field_type_maps_to_a_real_typed_column_and_round_trips_every_type(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "typed", "fields": []}, developer=True, limits=LIMITS)
        for name, field_type in (("i", "integer"), ("n", "number"), ("b", "boolean"), ("s", "string"), ("o", "object"), ("a", "array")):
            cell.apply_schema({"operation": "add_field", "entity": "typed", "field": name, "field_type": field_type}, developer=True, limits=LIMITS)
        good = {"i": 1, "n": 1.5, "b": True, "s": "x", "o": {"k": 1}, "a": [1, 2]}
        cell.transact("typed", [{"operation": "insert", "values": good}], LIMITS)
        rows = cell.query("typed", select=["i", "n", "b", "s", "o", "a"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [good]

        # `object`/`array` are deliberately excluded here (R-2): both map
        # to the same physical PostgreSQL type (JSONB), so once a column
        # is created, PostgreSQL's own catalog cannot tell this backend
        # which of the two the client originally declared -- `_load_
        # catalog` reports both as untyped, and an untyped column accepts
        # any JSON-shaped value (same as this module's own documented
        # `lt`/`lte`/`gt`/`gte` divergence for JSONB's total ordering).
        # `ApplicationCell` tracks the declared type string itself, so it
        # *can* still reject a list written to a field declared `object`;
        # this is a legitimate, physical-data-model-driven difference the
        # Security Invariants explicitly allow, not a validation gap both
        # backends still reject bad identifiers/operators/shapes
        # identically.
        bad_cases = {"i": "not-an-int", "n": "not-a-number", "b": "not-a-bool", "s": 5}
        for field_name, bad_value in bad_cases.items():
            with pytest.raises(FoundationError) as exc:
                cell.transact("typed", [{"operation": "insert", "values": {field_name: bad_value}}], LIMITS)
            assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("typed", select=["i"], where=[P("i", "eq", "nope")], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"

        # `isinstance(True, int)` is `True` in Python -- bool must be
        # explicitly excluded from integer/number, not accepted as 0/1.
        with pytest.raises(FoundationError) as exc:
            cell.transact("typed", [{"operation": "update", "where": [{"field": "i", "operator": "eq", "value": 1}], "values": {"i": True}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


# ===========================================================================
# Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-3): `create_entity`'s own `field_types` request key applies
# per-field DDL directly at table-creation time (not only via a follow-up
# `add_field`), and an explicit `json` declaration maps to the same bare
# JSONB an untyped field already used.
# ===========================================================================


def test_create_entity_field_types_applies_per_field_ddl_and_round_trips_and_rejects_wrong_type(app_a: types.SimpleNamespace) -> None:
    """The `field_types` request key on `create_entity` itself (not a
    follow-up `add_field`) drives real per-field DDL -- a field it names
    gets a genuinely typed column at CREATE TABLE time, exactly like
    `add_field`'s own `field_type` does after the fact."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {
                "operation": "create_entity", "entity": "ce_typed",
                "fields": ["i", "n", "b", "s", "o", "a", "untyped"],
                "field_types": {"i": "integer", "n": "number", "b": "boolean", "s": "string", "o": "object", "a": "array"},
            },
            developer=True, limits=LIMITS,
        )
        entity = cell.catalog()[0]
        assert entity["field_types"] == {
            "id": "integer", "i": "integer", "n": "number", "b": "boolean", "s": "string", "o": "object", "a": "array", "untyped": "json",
        }
        good = {"i": 1, "n": 1.5, "b": True, "s": "x", "o": {"k": 1}, "a": [1, 2], "untyped": {"any": ["shape", 1, True]}}
        cell.transact("ce_typed", [{"operation": "insert", "values": good}], LIMITS)
        rows = cell.query("ce_typed", select=["i", "n", "b", "s", "o", "a", "untyped"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [good]

        # A field the `create_entity`-time `field_types` declared -- not
        # merely a follow-up `add_field` -- genuinely enforces its type.
        with pytest.raises(FoundationError) as exc:
            cell.transact("ce_typed", [{"operation": "insert", "values": {"i": "not-an-int"}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_create_entity_explicit_json_field_type_maps_to_jsonb_and_matches_untyped_behavior(app_a: types.SimpleNamespace) -> None:
    """Design D-3(ii)/G11: a field explicitly declared `json` (via `create_
    entity`'s `field_types` or `add_field`'s scalar `field_type`) behaves
    identically to an untyped field -- same JSONB column, same NUL
    rejection, same catalog report (`json`, never left as a distinct
    physical marker)."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "ce_json", "fields": ["j"], "field_types": {"j": "json"}},
            developer=True, limits=LIMITS,
        )
        cell.apply_schema({"operation": "add_field", "entity": "ce_json", "field": "j2", "field_type": "json"}, developer=True, limits=LIMITS)
        entity = cell.catalog()[0]
        assert entity["field_types"]["j"] == "json"
        assert entity["field_types"]["j2"] == "json"

        # Every JSON shape round-trips, on both the create_entity-declared
        # and the add_field-declared explicit-json columns.
        good = {"j": {"nested": [1, "two", 3.0, True, None]}, "j2": "plain string"}
        cell.transact("ce_json", [{"operation": "insert", "values": good}], LIMITS)
        rows = cell.query("ce_json", select=["j", "j2"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [good]

        # NUL byte refused -- the exact regression design's own G11 note
        # names (an unmapped "json" string would fall through `_check_
        # type`'s catch-all `ok = True` branch, skipping the NUL check
        # untyped/mapped-to-None fields get).
        with pytest.raises(FoundationError) as exc:
            cell.transact("ce_json", [{"operation": "insert", "values": {"j": "bad\x00value"}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"

        # Coordinator audit item (b): the PHYSICAL PostgreSQL column type
        # is genuinely bare JSONB (never a distinct marker/domain) --
        # confirmed via `information_schema` directly, not merely via this
        # backend's own catalog report (which is itself derived from that
        # same introspection -- this assertion checks the introspection
        # SOURCE, closing the possibility that catalog and physical reality
        # silently disagree).
        with cell._developer.connection() as conn:  # noqa: SLF001 -- test-only reach-in, established convention in this file
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name IN ('j', 'j2')",
                    ["ce_json"],
                )
                data_types = {row[0] for row in cur.fetchall()}
        assert data_types == {"jsonb"}, f"explicit-json columns are not bare JSONB: {data_types!r}"
    finally:
        cell.close()


def test_field_type_sql_json_entry_maps_to_jsonb_without_keyerror() -> None:
    """Design D-3, r2db decision (c) / work order completion condition 16:
    `_FIELD_TYPE_SQL` carries a `"json"` entry mapping to the same bare
    JSONB every untyped field already used -- exercised directly (white-
    box) since normal request handling never presents the literal string
    "json" to this dict at all (`bind_schema_operation` already translates
    it to `None` before either DDL applier is reached, `structured.py`'s
    own G11 decision) -- this is what guards against a `KeyError` if a
    caller ever DOES look "json" up here directly (`_column_type_sql`'s own
    docstring)."""
    from psycopg import sql

    from r2db_api.postgres import _JSONB_SQL, _column_type_sql
    from r2db_api.postgres import _FIELD_TYPE_SQL
    from r2db_api.postgres_types import _FIELD_TYPE_SQL as leaf_field_type_sql
    from r2db_api.postgres_types import _JSONB_SQL as leaf_jsonb_sql
    from r2db_api.postgres_types import _column_type_sql as leaf_column_type_sql

    # `postgres` remains the compatibility facade for current callers.
    assert _FIELD_TYPE_SQL is leaf_field_type_sql
    assert _JSONB_SQL is leaf_jsonb_sql
    assert _column_type_sql is leaf_column_type_sql
    assert "json" in _FIELD_TYPE_SQL
    assert _FIELD_TYPE_SQL["json"] is _JSONB_SQL
    assert set(_FIELD_TYPE_SQL) == {"string", "integer", "number", "boolean", "object", "array", "json"}
    assert all(isinstance(_FIELD_TYPE_SQL[field_type], sql.SQL) for field_type in ("string", "integer", "number", "boolean", "json"))
    assert all(isinstance(_FIELD_TYPE_SQL[field_type], sql.Identifier) for field_type in ("object", "array"))
    assert _column_type_sql("json") is _JSONB_SQL
    assert _column_type_sql(None) is _JSONB_SQL  # untyped -- same physical type
    assert _column_type_sql("not-a-contract-field-type") is _JSONB_SQL


def test_field_type_null_is_allowed_for_any_declared_type(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "nullable", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "nullable", "field": "i", "field_type": "integer"}, developer=True, limits=LIMITS)
        cell.transact("nullable", [{"operation": "insert", "values": {"i": None}}], LIMITS)
        rows = cell.query("nullable", select=["i"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [{"i": None}]
        # And it is a real SQL NULL, not the JSONB-only literal (R-7) -- an
        # is_null predicate on a *typed* column must find it too.
        rows = cell.query("nullable", select=["i"], where=[P("i", "is_null")], page_size=10, limits=LIMITS)
        assert rows.items == [{"i": None}]
    finally:
        cell.close()


def test_in_operator_type_checks_each_element_on_a_typed_column(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "ints", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "ints", "field": "i", "field_type": "integer"}, developer=True, limits=LIMITS)
        cell.transact("ints", [{"operation": "insert", "values": {"i": 1}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("ints", select=["i"], where=[P("i", "in", [1, "two"])], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        rows = cell.query("ints", select=["i"], where=[P("i", "in", [1, 2])], page_size=10, limits=LIMITS)
        assert rows.items == [{"i": 1}]
    finally:
        cell.close()


def test_in_operator_rejects_an_empty_list(app_a: types.SimpleNamespace) -> None:
    """WP-2e closure audit M-3 (`{scratchpad}/audit-wp2e-2.md` R-2,
    ruling `{scratchpad}/rulings-r3-r7-flip.md` addendum 2): an empty `in`
    list is refused at the shared choke point (`structured._validate_
    predicate_types`, both cells call it) BEFORE any SQL is built --
    `violated_declaration: request_schema`, `field: where/<i>/value` --
    identical to the in-memory plug's own `test_foundation.py::test_in_
    operator_rejects_an_empty_list`. `postgres.py`'s own local `in`-branch
    fallback in `_predicate_sql` (M-1: kept only as an unreachable
    defensive backstop, never the site that actually answers this
    request) is proven unreached by this test's own passing: if it WERE
    reached instead, it would answer with the SAME code/details shape
    (both use `violation("request_schema", field="where")`, this choke-
    point's own per-index path just narrower), so this test alone cannot
    distinguish the two layers -- `test_l1_details_vocabulary_ast_scan.py`
    already pins per-file/line details vocabulary compliance for that
    fallback separately."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "emptyin", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "emptyin", "field": "i", "field_type": "integer"}, developer=True, limits=LIMITS)
        cell.transact("emptyin", [{"operation": "insert", "values": {"i": 1}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("emptyin", select=["i"], where=[P("i", "in", [])], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"violated_declaration": "request_schema", "field": "where/0/value"}
    finally:
        cell.close()


def test_eq_and_ne_reject_a_null_predicate_value(app_a: types.SimpleNamespace) -> None:
    """WP-3 confirmation review N-3: shared-boundary parity with
    `ApplicationCell` -- `= NULL`/`<> NULL` is refused rather than executed
    as a query that silently always returns nothing."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["tag"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"tag": None}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["tag"], where=[P("tag", "eq", None)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["tag"], where=[P("tag", "ne", None)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        rows = cell.query("items", select=["tag"], where=[P("tag", "is_null")], page_size=10, limits=LIMITS)
        assert rows.items == [{"tag": None}]
    finally:
        cell.close()


def test_json_null_binds_as_sql_null_on_untyped_column_not_jsonb_literal_null(app_a: types.SimpleNamespace) -> None:
    """R-7 addendum (WP-2 review M-B): a JSON `null` written to an untyped
    (JSONB) column must be stored as SQL `NULL`, not `'null'::jsonb` -- the
    two are otherwise indistinguishable to `is_null`/`order_by` unless the
    write path itself keeps them apart."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["value"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"value": None}}, {"operation": "insert", "values": {"value": 1}}], LIMITS)
        rows = cell.query("docs", select=["value"], where=[P("value", "is_null")], page_size=10, limits=LIMITS)
        assert rows.items == [{"value": None}]
        # A raw SQL-level check, independent of PostgresCell's own reading
        # back: the stored value must be a genuine SQL NULL.
        conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value IS NULL, jsonb_typeof(value) FROM docs WHERE value IS NULL")
                is_null, typeof = cur.fetchone()
                assert is_null is True
                assert typeof is None  # jsonb_typeof(NULL) is NULL, not 'null'
        finally:
            conn.close()
    finally:
        cell.close()


# --- create_index / drop_index (R-5) ---------------------------------------


def test_create_index_and_unique_conflict_on_insert_and_update(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "accounts", "fields": ["email"]}, developer=True, limits=LIMITS)
        revision = cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS).revision
        assert isinstance(revision, int)
        assert cell.catalog()[0]["unique_keys"] == [{"name": "by_email", "fields": ["email"]}]

        cell.transact("accounts", [{"operation": "insert", "values": {"email": "a@example.invalid"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("accounts", [{"operation": "insert", "values": {"email": "a@example.invalid"}}], LIMITS)
        assert exc.value.code == "CONFLICT"
        # R-5, corrigendum M-5: only the client-recognizable index name is
        # disclosed -- never PostgreSQL's own DETAIL text, constraint
        # internals, or the colliding row value.
        assert exc.value.details == {"index": "by_email"}
        rendered = repr(exc.value)
        assert "a@example.invalid" not in rendered

        cell.transact("accounts", [{"operation": "insert", "values": {"email": "b@example.invalid"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "accounts",
                [{"operation": "update", "where": [{"field": "email", "operator": "eq", "value": "b@example.invalid"}], "values": {"email": "a@example.invalid"}}],
                LIMITS,
            )
        assert exc.value.code == "CONFLICT"
        assert exc.value.details == {"index": "by_email"}

        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_email", "fields": ["email"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_ghost", "fields": ["ghost"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell.close()


def test_unique_index_with_null_key_field_never_conflicts(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "accounts", "fields": ["email"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_index", "entity": "accounts", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS)
        cell.transact("accounts", [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}], LIMITS)
        rows = cell.query("accounts", select=["id", "email"], where=[], page_size=10, limits=LIMITS).items
        assert [row["email"] for row in rows] == [None, None]
    finally:
        cell.close()


def test_create_index_unique_rejects_when_existing_data_has_duplicates(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "dupes", "fields": ["tag"]}, developer=True, limits=LIMITS)
        cell.transact("dupes", [{"operation": "insert", "values": {"tag": "x"}}, {"operation": "insert", "values": {"tag": "x"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_index", "entity": "dupes", "index": "by_tag", "fields": ["tag"], "unique": True}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
        assert exc.value.status == 409
        # No side effect: the rejected index never landed.
        assert cell.catalog()[0]["unique_keys"] == []
    finally:
        cell.close()


def test_create_index_rejects_address_field_and_drop_index_requires_destructive_confirmation(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "shapes", "fields": ["tag"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            # R-5, WP-2 review M-5: `id` is the address, not a domain
            # uniqueness declaration.
            cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "by_id", "fields": ["id"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"

        cell.apply_schema({"operation": "create_index", "entity": "shapes", "index": "by_tag", "fields": ["tag"], "unique": True}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_index", "entity": "shapes", "index": "by_tag"}, developer=True, limits=LIMITS)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert cell.catalog()[0]["unique_keys"] == [{"name": "by_tag", "fields": ["tag"]}]
        cell.apply_schema({"operation": "drop_index", "entity": "shapes", "index": "by_tag", "destructive": True, "confirmation": _drop_index_phrase(cell, "shapes", "by_tag")}, developer=True, limits=LIMITS)
        assert cell.catalog()[0]["unique_keys"] == []
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_index", "entity": "shapes", "index": "by_tag", "destructive": True, "confirmation": "irrelevant, the index no longer exists"}, developer=True, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
        # Dropping the (now non-unique) index frees `upsert` back to
        # CAPABILITY_UNSUPPORTED -- proving the index is actually gone, not
        # just unlisted.
        with pytest.raises(FoundationError) as exc:
            cell.transact("shapes", [{"operation": "upsert", "values": {"tag": "x"}}], LIMITS)
        assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    finally:
        cell.close()


def test_composite_unique_key_enforces_uniqueness_and_supports_upsert(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "memberships", "fields": ["org", "user", "role"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_index", "entity": "memberships", "index": "by_org_user", "fields": ["org", "user"], "unique": True}, developer=True, limits=LIMITS)
        cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "ann", "role": "member"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "ann", "role": "admin"}}], LIMITS)
        assert exc.value.code == "CONFLICT"
        cell.transact("memberships", [{"operation": "insert", "values": {"org": "acme", "user": "bob", "role": "member"}}], LIMITS)

        outcome = cell.transact("memberships", [{"operation": "upsert", "values": {"org": "acme", "user": "ann", "role": "owner"}}], LIMITS)
        assert outcome.affected == 1
        assert outcome.assigned_addresses == []
        rows = cell.query("memberships", select=["org", "user", "role"], where=[P("user", "eq", "ann")], page_size=10, limits=LIMITS).items
        assert rows == [{"org": "acme", "user": "ann", "role": "owner"}]
    finally:
        cell.close()


# --- upsert (R-5, §0.5 Q-1) --------------------------------------------------


def test_upsert_with_one_declared_key_resolves_to_insert_then_update_with_assigned_addresses(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "people", "fields": ["email", "name"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_index", "entity": "people", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS)

        outcome = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann"}}], LIMITS)
        assert outcome.affected == 1
        assert outcome.assigned_addresses == [{"address": {"id": 1}}]

        outcome2 = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann2"}}], LIMITS)
        assert outcome2.affected == 1
        assert outcome2.assigned_addresses == []  # resolved to update, not insert
        rows = cell.query("people", select=["id", "name"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [{"id": 1, "name": "Ann2"}]

        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "people",
                [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann3"}, "where": [{"field": "name", "operator": "eq", "value": "Ann2"}]}],
                LIMITS,
            )
        assert exc.value.code == "VALIDATION_FAILED"  # R-5, corrigendum M-3: upsert does not accept a filter

        with pytest.raises(FoundationError) as exc:
            cell.transact("people", [{"operation": "upsert", "values": {"name": "NoEmail"}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"  # missing key field
    finally:
        cell.close()


def _notes_cell_with_two_unique_keys(app_a: types.SimpleNamespace) -> "PostgresCell":
    cell = make_cell(app_a)
    cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body", "email"]}, developer=True, limits=LIMITS)
    cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
    cell.apply_schema({"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"], "unique": True}, developer=True, limits=LIMITS)
    cell.apply_schema({"operation": "create_index", "entity": "notes", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS)
    return cell


def test_upsert_on_multi_key_entity_requires_unique_key_and_validates_it(app_a: types.SimpleNamespace) -> None:
    cell = _notes_cell_with_two_unique_keys(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "upsert", "values": {"body": "z", "email": "z@example.invalid"}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"  # unique_key required, 2 keys declared

        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "upsert", "unique_key": "no_such_key", "values": {"body": "z", "email": "z@example.invalid"}}], LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell.close()


def test_upsert_on_multi_key_entity_resolves_using_the_named_key_only(app_a: types.SimpleNamespace) -> None:
    """A match on the *other* declared key must not resolve the upsert to
    an update -- only the explicitly named key decides existence."""
    cell = _notes_cell_with_two_unique_keys(app_a)
    try:
        cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "new-body", "email": "new@example.invalid"}}], LIMITS)
        rows = cell.query("notes", select=["id", "body", "email"], where=[], page_size=10, limits=LIMITS).items
        assert len(rows) == 2
        bodies_by_email = {row["email"]: row["body"] for row in rows}
        assert bodies_by_email == {None: "a", "new@example.invalid": "new-body"}

        cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "changed", "email": "new@example.invalid"}}], LIMITS)
        rows = cell.query("notes", select=["body", "email"], where=[], page_size=10, limits=LIMITS).items
        bodies_by_email = {row["email"]: row["body"] for row in rows}
        assert bodies_by_email == {None: "a", "new@example.invalid": "changed"}
    finally:
        cell.close()


def test_upsert_conflicts_on_a_declared_key_other_than_the_selected_one(app_a: types.SimpleNamespace) -> None:
    """WP-2 review M-13 parity: selecting a key with `unique_key` only
    decides *existence* -- every declared unique key is still enforced on
    write, including ones the selection did not name."""
    cell = _notes_cell_with_two_unique_keys(app_a)
    try:
        cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "unique-1", "email": "one@example.invalid"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "upsert", "unique_key": "by_email", "values": {"body": "unique-1", "email": "two@example.invalid"}}], LIMITS)
        assert exc.value.code == "CONFLICT"
        assert exc.value.details == {"index": "by_body"}
    finally:
        cell.close()


def test_upsert_on_single_key_entity_with_wrong_explicit_unique_key_name_is_not_found(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
        cell.apply_schema({"operation": "create_index", "entity": "notes", "index": "by_body", "fields": ["body"], "unique": True}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "upsert", "unique_key": "not_by_body", "values": {"body": "a"}}], LIMITS)
        assert exc.value.code == "NOT_FOUND"
        outcome = cell.transact("notes", [{"operation": "upsert", "unique_key": "by_body", "values": {"body": "a"}}], LIMITS)
        assert outcome.affected == 1
        assert outcome.assigned_addresses == []
    finally:
        cell.close()


def test_unique_key_is_rejected_on_insert_update_and_delete(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("notes", [{"operation": "insert", "values": {"body": "a"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "insert", "values": {"body": "z"}, "unique_key": "by_body"}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.transact("notes", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "z"}, "unique_key": "by_body"}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            where = [{"field": "id", "operator": "eq", "value": 1}]
            cell.transact("notes", [{"operation": "delete", "where": where, "unique_key": "by_body", "destructive": True, "confirmation": _delete_phrase(cell, "notes", where)}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_upsert_expected_revision_updates_in_place_and_never_resolves_to_insert(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "people", "fields": ["email", "name"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_index", "entity": "people", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS)

        # No existing row at all: never resolves to an insert.
        with pytest.raises(FoundationError) as exc:
            cell.transact("people", [{"operation": "upsert", "values": {"email": "new@example.invalid"}, "expected_revision": "anything"}], LIMITS)
        assert exc.value.code == "NOT_FOUND"
        assert cell.query("people", select=["id"], where=[], page_size=10, limits=LIMITS).items == []

        cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann"}}], LIMITS)
        revision = _row_revision(cell, "people", 1)

        with pytest.raises(FoundationError) as exc:
            cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann2"}, "expected_revision": "wrong-revision"}], LIMITS)
        assert exc.value.code == "PRECONDITION_FAILED"

        outcome = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann3"}, "expected_revision": revision}], LIMITS)
        assert outcome.affected == 1
        assert outcome.assigned_addresses == []
        rows = cell.query("people", select=["name"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [{"name": "Ann3"}]
        assert _row_revision(cell, "people", 1) != revision
    finally:
        cell.close()


# --- expected_revision on update/delete: the contract's 6 clauses (R-4) ----


def test_expected_revision_on_insert_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}, "expected_revision": "anything"}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_expected_revision_mismatch_is_precondition_failed(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "docs",
                [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": "not-the-real-revision"}],
                LIMITS,
            )
        assert exc.value.code == "PRECONDITION_FAILED"
    finally:
        cell.close()


def test_expected_revision_with_no_predicate_match_is_not_found(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
        revision = _row_revision(cell, "docs", 1)
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "docs",
                [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 999}], "values": {"body": "v2"}, "expected_revision": revision}],
                LIMITS,
            )
        assert exc.value.code == "NOT_FOUND"
        with pytest.raises(FoundationError) as exc:
            where = [{"field": "id", "operator": "eq", "value": 999}]
            cell.transact(
                "docs",
                [{"operation": "delete", "where": where, "expected_revision": revision, "destructive": True, "confirmation": _delete_phrase(cell, "docs", where)}],
                LIMITS,
            )
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell.close()


def test_expected_revision_success_rotates_revision_and_leaves_other_rows_unaffected(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}, {"operation": "insert", "values": {"body": "other"}}], LIMITS)
        revision_1 = _row_revision(cell, "docs", 1)
        revision_2_before = _row_revision(cell, "docs", 2)

        outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": revision_1}], LIMITS)
        assert outcome.affected == 1
        assert _row_revision(cell, "docs", 1) != revision_1
        assert _row_revision(cell, "docs", 2) == revision_2_before

        with pytest.raises(FoundationError) as exc:
            cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v3"}, "expected_revision": revision_1}], LIMITS)
        assert exc.value.code == "PRECONDITION_FAILED"
    finally:
        cell.close()


def test_expected_revision_without_precondition_zero_row_update_and_delete_still_succeed(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 999}], "values": {"body": "v2"}}], LIMITS)
        assert outcome.affected == 0
        where = [{"field": "id", "operator": "eq", "value": 999}]
        outcome = cell.transact("docs", [{"operation": "delete", "where": where, "destructive": True, "confirmation": _delete_phrase(cell, "docs", where)}], LIMITS)
        assert outcome.affected == 0
    finally:
        cell.close()


def test_expected_revision_on_empty_values_update_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    """R-4, corrigendum M-1: an empty-`values` update never silently
    discards a precondition riding along with it."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
        revision = _row_revision(cell, "docs", 1)
        with pytest.raises(FoundationError) as exc:
            cell.transact("docs", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {}, "expected_revision": revision}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_expected_revision_predicate_matching_several_rows_affects_only_the_revision_row(app_a: types.SimpleNamespace) -> None:
    """R-4, corrigendum M-2: the target of an `expected_revision` mutation
    is "predicate match AND revision match" -- revision is unique per row,
    so at most one row is ever changed even if the predicate matches many."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact(
            "docs",
            [
                {"operation": "insert", "values": {"body": "shared"}},
                {"operation": "insert", "values": {"body": "shared"}},
                {"operation": "insert", "values": {"body": "shared"}},
            ],
            LIMITS,
        )
        revision_2 = _row_revision(cell, "docs", 2)
        outcome = cell.transact("docs", [{"operation": "update", "where": [{"field": "body", "operator": "eq", "value": "shared"}], "values": {"body": "updated"}, "expected_revision": revision_2}], LIMITS)
        assert outcome.affected == 1
        rows = cell.query("docs", select=["id", "body"], where=[], page_size=10, limits=LIMITS).items
        assert {row["id"]: row["body"] for row in rows} == {1: "shared", 2: "updated", 3: "shared"}
    finally:
        cell.close()


def test_type_mismatch_is_validation_failed_even_with_a_matching_precondition(app_a: types.SimpleNamespace) -> None:
    """R-7, corrigendum M-9: a type mismatch is refused before a
    precondition is even evaluated -- never surfaced as PRECONDITION_FAILED/
    NOT_FOUND, both of which read as "retry" to an AI agent client."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "docs", "field": "n", "field_type": "integer"}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1", "n": 1}}], LIMITS)
        revision = _row_revision(cell, "docs", 1)
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "docs",
                [{"operation": "update", "where": [{"field": "n", "operator": "eq", "value": "not-an-int"}], "values": {"body": "v2"}, "expected_revision": revision}],
                LIMITS,
            )
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_destructive_confirmation_is_checked_before_precondition_evaluation(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("docs", [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "expected_revision": "wrong-revision"}], LIMITS)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert cell.query("docs", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]
    finally:
        cell.close()


def test_query_revisions_are_index_aligned_with_items(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["n"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"n": n}} for n in range(3)], LIMITS)
        outcome = cell.query("items", select=["id", "n"], where=[], page_size=10, limits=LIMITS)
        assert len(outcome.revisions) == len(outcome.items)
        assert len(set(outcome.revisions)) == len(outcome.items)
        for revision in outcome.revisions:
            assert isinstance(revision, str) and revision
    finally:
        cell.close()


# --- order_by (R-6) ----------------------------------------------------------


def _numbered_cell(app_a: types.SimpleNamespace, count: int) -> PostgresCell:
    cell = make_cell(app_a)
    cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["n"]}, developer=True, limits=LIMITS)
    cell.transact("items", [{"operation": "insert", "values": {"n": n}} for n in range(count)], LIMITS)
    return cell


def test_order_by_sorts_and_appends_id_when_absent(app_a: types.SimpleNamespace) -> None:
    cell = _numbered_cell(app_a, 3)  # n = 0, 1, 2 with id = 1, 2, 3 respectively
    try:
        descending = cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "n", "direction": "desc"}])
        assert descending.items == [{"n": 2}, {"n": 1}, {"n": 0}]
        default_order = cell.query("items", select=["id"], where=[], page_size=10, limits=LIMITS)
        assert default_order.items == [{"id": 1}, {"id": 2}, {"id": 3}]
    finally:
        cell.close()


def test_order_by_unknown_field_is_validation_failed_and_rejects_a_repeated_field(app_a: types.SimpleNamespace) -> None:
    # Contract 1.11.0 (subordinate ruling 16): an undeclared order_by field
    # is a request_schema violation naming the position, not NOT_FOUND.
    cell = _numbered_cell(app_a, 1)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "ghost", "direction": "asc"}])
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details["violated_declaration"] == "request_schema"
        assert exc.value.details["field"] == "order_by/0/field"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "n", "direction": "asc"}, {"field": "n", "direction": "desc"}])
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_order_by_null_placement_matches_application_cell_defaults(app_a: types.SimpleNamespace) -> None:
    """R-6, WP-2 review M-6: NULL sorts last for ascending, first for
    descending -- PostgreSQL's own default with no explicit NULLS clause,
    which is exactly the semantics `ApplicationCell._sort_key` was written
    to match."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "tasks", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "tasks", "field": "priority", "field_type": "integer"}, developer=True, limits=LIMITS)
        cell.transact(
            "tasks",
            [
                {"operation": "insert", "values": {"priority": 2}},
                {"operation": "insert", "values": {"priority": None}},
                {"operation": "insert", "values": {"priority": 1}},
            ],
            LIMITS,
        )
        ascending = cell.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": "asc"}])
        assert ascending.items == [{"priority": 1}, {"priority": 2}, {"priority": None}]
        descending = cell.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": "desc"}])
        assert descending.items == [{"priority": None}, {"priority": 2}, {"priority": 1}]
    finally:
        cell.close()


def test_order_by_untyped_column_uses_jsonb_cross_type_order(app_a: types.SimpleNamespace) -> None:
    """WP-2 review M-6 parity: an untyped (JSONB-equivalent) column's
    cross-type ascending order is String < Number < Boolean < Array <
    Object -- PostgreSQL's own native jsonb comparison, matching
    `ApplicationCell._sort_key`'s `_JSON_TYPE_RANK`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "mixed", "fields": ["value"]}, developer=True, limits=LIMITS)
        cell.transact(
            "mixed",
            [
                {"operation": "insert", "values": {"value": {"k": 1}}},
                {"operation": "insert", "values": {"value": [1]}},
                {"operation": "insert", "values": {"value": True}},
                {"operation": "insert", "values": {"value": 1}},
                {"operation": "insert", "values": {"value": "x"}},
            ],
            LIMITS,
        )
        ascending = cell.query("mixed", select=["value"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "value", "direction": "asc"}])
        assert ascending.items == [{"value": "x"}, {"value": 1}, {"value": True}, {"value": [1]}, {"value": {"k": 1}}]
    finally:
        cell.close()


def test_order_by_clause_count_is_charged_to_query_complexity(app_a: types.SimpleNamespace) -> None:
    cell = _numbered_cell(app_a, 1)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=10, limits=ResourceLimits(query_complexity=1), order_by=[{"field": "n", "direction": "asc"}])
        assert exc.value.code == "LIMIT_EXCEEDED"
    finally:
        cell.close()


# --- cursor pagination (R-6) -------------------------------------------------


def test_cursor_pagination_pages_through_results_and_signals_has_more(app_a: types.SimpleNamespace) -> None:
    cell = _numbered_cell(app_a, 5)
    try:
        first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
        assert first.items == [{"n": 0}, {"n": 1}]
        assert first.has_more is True
        assert first.next_cursor is not None
        second = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=first.next_cursor)
        assert second.items == [{"n": 2}, {"n": 3}]
        assert second.has_more is True
        third = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=second.next_cursor)
        assert third.items == [{"n": 4}]
        assert third.has_more is False
        assert third.next_cursor is None
    finally:
        cell.close()


def test_cursor_stays_valid_across_a_select_or_page_size_change_and_malformed_cursor_is_rejected(app_a: types.SimpleNamespace) -> None:
    """Phase 11 keyset paging (design D-1 (4), D-3 (3)): the binding hash
    covers only (Application, entity, `where`, `order_by`) -- `select` and
    `page.size` are deliberately outside it (mirrors `test_foundation.py`'s
    identically-named in-memory test; both cells share the same binding
    rule, D-3 (5))."""
    cell = _numbered_cell(app_a, 5)
    try:
        first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
        wider = cell.query("items", select=["id", "n"], where=[], page_size=2, limits=LIMITS, cursor=first.next_cursor)
        assert wider.items == [{"id": 3, "n": 2}, {"id": 4, "n": 3}]
        resized = cell.query("items", select=["n"], where=[], page_size=3, limits=LIMITS, cursor=first.next_cursor)
        assert resized.items == [{"n": 2}, {"n": 3}, {"n": 4}]
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor="not-a-valid-cursor")
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def _forge_cursor(payload) -> str:
    blob = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def _decode_cursor_binding(cursor: str) -> str:
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))["b"]


def test_cursor_rejects_malformed_payload_shapes(app_a: types.SimpleNamespace) -> None:
    """Phase 11 keyset paging (design D-6): mirrors `test_foundation.py`'s
    identically-named in-memory test -- a well-formed base64url/JSON
    envelope that is not a dict, is missing `v`/`b`, or carries `v` as a
    non-list, is rejected the same as an undecodable string."""
    cell = _numbered_cell(app_a, 3)
    try:
        first = cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS)
        binding = _decode_cursor_binding(first.next_cursor)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor(["not", "a", "dict"]))
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor({"v": [0], "b": binding, "extra": 1}))
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=2, limits=LIMITS, cursor=_forge_cursor({"v": "not-a-list", "b": binding}))
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_cursor_pagination_uses_the_id_tie_break_when_the_order_by_field_ties(app_a: types.SimpleNamespace) -> None:
    """Design D-3 (2): mirrors `test_foundation.py`'s identically-named
    in-memory test -- the deterministic `id ASC` tie-break the keyset
    predicate's own trailing term supplies is what keeps a PostgreSQL cell
    traversal total when the caller's own `order_by` field does not
    already distinguish every row. Seeded so a group of tied rows (3 rows
    of `bucket='x'`) is guaranteed to straddle a `page_size=1` page
    boundary, in both directions."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "ties", "fields": ["bucket"]}, developer=True, limits=LIMITS)
        cell.transact("ties", [{"operation": "insert", "values": {"bucket": b}} for b in ["x", "x", "x", "y", "y"]], LIMITS)
        for direction in ("asc", "desc"):
            order_by = [{"field": "bucket", "direction": direction}]
            unpaged = cell.query("ties", select=["id", "bucket"], where=[], page_size=10, limits=LIMITS, order_by=order_by)
            paged_items: list[dict] = []
            cursor = None
            for _ in range(10):
                page = cell.query("ties", select=["id", "bucket"], where=[], page_size=1, limits=LIMITS, order_by=order_by, cursor=cursor)
                paged_items.extend(page.items)
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor
            assert paged_items == unpaged.items, (
                f"direction={direction}: paged={paged_items!r} != unpaged={unpaged.items!r}"
            )
    finally:
        cell.close()


def test_domain_out_of_range_values_are_validation_failed_not_service_unavailable(app_a: types.SimpleNamespace) -> None:
    """`value_types._check_type` (the shared choke point `where` and
    `page/cursor` both pass through) refuses a value PostgreSQL's own
    typed columns cannot represent, before it ever reaches a bind
    parameter: a 401-digit integer bound to a `number` (`float8`) column
    overflows `float()`, and a lone UTF-16 surrogate bound to a `string`
    column cannot be encoded by the driver -- both would otherwise reach
    the connection and come back mapped to `SERVICE_UNAVAILABLE` (503),
    the wrong signal for a client-supplied-value bug. Fixed for `where`
    directly, and for a tampered `page/cursor` token (which can carry the
    identical kind of value, D-3 (4a))."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "domain_check", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "domain_check", "field": "score", "field_type": "number"}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "domain_check", "field": "label", "field_type": "string"}, developer=True, limits=LIMITS)
        cell.transact("domain_check", [{"operation": "insert", "values": {"score": 1.0, "label": "a"}}, {"operation": "insert", "values": {"score": 2.0, "label": "b"}}], LIMITS)

        huge_integer = 10**401
        with pytest.raises(FoundationError) as exc:
            cell.query("domain_check", select=["score"], where=[Predicate("score", "gt", huge_integer)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"violated_declaration": "request_schema", "field": "where/0/value"}

        lone_surrogate = "\ud800"
        with pytest.raises(FoundationError) as exc:
            cell.query("domain_check", select=["label"], where=[Predicate("label", "eq", lone_surrogate)], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"violated_declaration": "request_schema", "field": "where/0/value"}

        first = cell.query("domain_check", select=["score"], where=[], page_size=1, limits=LIMITS, order_by=[{"field": "score", "direction": "asc"}])
        binding = _decode_cursor_binding(first.next_cursor)
        with pytest.raises(FoundationError) as exc:
            cell.query("domain_check", select=["score"], where=[], page_size=1, limits=LIMITS, order_by=[{"field": "score", "direction": "asc"}], cursor=encode_page_cursor([huge_integer, 1], binding))
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"violated_declaration": "request_schema", "field": "page/cursor"}

        first2 = cell.query("domain_check", select=["label"], where=[], page_size=1, limits=LIMITS, order_by=[{"field": "label", "direction": "asc"}])
        binding2 = _decode_cursor_binding(first2.next_cursor)
        with pytest.raises(FoundationError) as exc:
            cell.query("domain_check", select=["label"], where=[], page_size=1, limits=LIMITS, order_by=[{"field": "label", "direction": "asc"}], cursor=encode_page_cursor([lone_surrogate, 1], binding2))
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"violated_declaration": "request_schema", "field": "page/cursor"}
    finally:
        cell.close()


def test_page_size_over_the_contract_maximum_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    """WP-4 review minor-1: shared-boundary parity with `ApplicationCell`
    -- `Page.size`'s contract maximum (1000) is enforced independent of
    `ResourceLimits.result_items`."""
    cell = _numbered_cell(app_a, 1)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["n"], where=[], page_size=1001, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        cell.query("items", select=["n"], where=[], page_size=1000, limits=LIMITS)
    finally:
        cell.close()


# --- catalog completeness guard (R-1) ---------------------------------------


def test_catalog_completeness_guard_fails_closed_when_id_or_revision_is_missing(app_a: types.SimpleNamespace) -> None:
    """R-1's fail-closed declaration-completeness guard: if even one entity
    table does not actually have both a `bigint identity` `id` and a `uuid`
    `_r2db_revision` column, `_load_catalog` must fail the whole call
    closed (`SERVICE_UNAVAILABLE`, naming only the offending entity), rather
    than silently publish a false `mutable`/`address_fields` declaration for
    it. A table like this can only arise from something bypassing
    `PostgresCell.apply_schema` entirely (this deployment never provisions
    one) -- simulated here with a raw DDL statement against a table
    `PostgresCell` itself created normally.
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_entity", "entity": "sprockets", "fields": ["name"]}, developer=True, limits=LIMITS)
        # Drift outside PostgresCell entirely: drop the revision column
        # from one table, bypassing `apply_schema`.
        dev_conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with dev_conn.cursor() as cur:
                cur.execute("ALTER TABLE public.sprockets DROP COLUMN _r2db_revision")
        finally:
            dev_conn.close()

        with pytest.raises(FoundationError) as exc:
            cell.catalog()
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert exc.value.details["entities"] == ["sprockets"]

        # The same fail-closed guard blocks every other operation against
        # this application too, including on the unaffected table --
        # `_load_catalog` runs before any operation touches stored data.
        with pytest.raises(FoundationError) as exc:
            cell.query("widgets", select=["name"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "another", "fields": []}, developer=True, limits=LIMITS)
        assert exc.value.code == "SERVICE_UNAVAILABLE"
    finally:
        cell.close()


# --- address non-reuse (R-1, property 5) -------------------------------------


def test_id_is_never_reused_after_delete_or_a_failed_batch(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}], LIMITS)
        delete_where = [{"field": "id", "operator": "eq", "value": 2}]
        cell.transact("widgets", [{"operation": "delete", "where": delete_where, "destructive": True, "confirmation": _delete_phrase(cell, "widgets", delete_where)}], LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
        ids = sorted(row["id"] for row in cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items)
        assert ids == [1, 3]  # id 2 is gone forever

        # A failed batch containing an insert still consumes the id --
        # PostgreSQL's own `GENERATED ALWAYS AS IDENTITY` sequence is
        # non-transactional and does not rewind on ROLLBACK.
        with pytest.raises(FoundationError):
            cell.transact("widgets", [{"operation": "insert", "values": {}}, {"operation": "unsupported"}], LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
        ids_after = sorted(row["id"] for row in cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items)
        assert ids_after == [1, 3, 5]  # id 4 was consumed and gapped

        # drop_entity + recreate is a new entity: addressing restarts at 1.
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": _drop_entity_phrase(cell, "widgets")}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
        assert cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]
    finally:
        cell.close()


def test_delete_phrase_invalidated_by_drop_recreate_of_the_same_entity_under_the_same_name(app_a: types.SimpleNamespace) -> None:
    """Opus review minor m-2, monitor decision Q1-D10 (reviewer's own
    measured scenario, against real PostgreSQL): probe a `delete` phrase
    for `widgets` at its current schema_revision, `drop_entity` `widgets`,
    `create_entity` `widgets` again (same name), then echo the OLD phrase
    against the freshly re-created entity's identical-looking delete
    request -- it must now be denied. Before this fix the where-digest-only
    delete phrase carried no state fingerprint at all, so the stale phrase
    would incorrectly still validate."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
        where = [{"field": "id", "operator": "eq", "value": 1}]
        old_phrase = _delete_phrase(cell, "widgets", where)

        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": _drop_entity_phrase(cell, "widgets")}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)  # the re-created entity's own fresh row

        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", [{"operation": "delete", "where": where, "destructive": True, "confirmation": old_phrase}], LIMITS)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items == [{"id": 1}]
    finally:
        cell.close()


def test_id_is_never_reused_after_vacuum(app_a: types.SimpleNamespace) -> None:
    """R-1: `VACUUM` (and `pg_dump`/restore) preserve stored values and
    identity sequence state -- a deleted id must stay gone even after the
    dead row is physically reclaimed, not merely while its tuple is still
    on disk."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {}}, {"operation": "insert", "values": {}}], LIMITS)
        delete_where = [{"field": "id", "operator": "eq", "value": 2}]
        cell.transact("widgets", [{"operation": "delete", "where": delete_where, "destructive": True, "confirmation": _delete_phrase(cell, "widgets", delete_where)}], LIMITS)

        conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("VACUUM public.widgets")
        finally:
            conn.close()

        cell.transact("widgets", [{"operation": "insert", "values": {}}], LIMITS)
        ids = sorted(row["id"] for row in cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items)
        assert ids == [1, 3]
    finally:
        cell.close()


# ==========================================================================
# WP-3 independent review (Opus) corrigenda: blocker-1 (matches gate,
# tested in test_foundation.py/test_http.py against DataService/HTTP --
# this file tests PostgresCell directly, which is deliberately ungated),
# blocker-2 (value-domain validation + 22xxx mapping), D-1~D-4 (predicate
# semantics unified with SQL's own three-valued logic), and the object/
# array DOMAIN unification.
# ==========================================================================


def test_integer_field_value_out_of_bigint_range_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    """R-7 addendum (WP-3 review blocker-2): shared-boundary parity with
    `ApplicationCell` -- a JSON integer outside signed 64-bit range must
    never reach PostgreSQL's own bigint column at all."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "readings", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "n", "field_type": "integer"}, developer=True, limits=LIMITS)
        too_big = 2**63
        too_small = -(2**63) - 1
        for bad in (too_big, too_small):
            with pytest.raises(FoundationError) as exc:
                cell.transact("readings", [{"operation": "insert", "values": {"n": bad}}], LIMITS)
            assert exc.value.code == "VALIDATION_FAILED"
            # Monitor ruling M-3/D (rulings-wp2a-review.md): request-
            # internal path, not a bare field name. Contract 1.7.0 (D-3,
            # WP-2e): out-of-range is a `field_type` violation --
            # `declared_type`/`observed_type` both "integer".
            assert exc.value.details == {
                "field": "operations/0/values/n", "violated_declaration": "field_type",
                "declared_type": "integer", "observed_type": "integer",
            }
        cell.transact("readings", [{"operation": "insert", "values": {"n": 2**63 - 1}}, {"operation": "insert", "values": {"n": -(2**63)}}], LIMITS)
        rows = {row["n"] for row in cell.query("readings", select=["n"], where=[], page_size=10, limits=LIMITS).items}
        assert rows == {2**63 - 1, -(2**63)}
    finally:
        cell.close()


def test_nul_byte_is_rejected_in_string_object_array_and_untyped_values(app_a: types.SimpleNamespace) -> None:
    """R-7 addendum (WP-3 review blocker-2): shared-boundary parity with
    `ApplicationCell` -- a U+0000 anywhere inside the value must never
    reach PostgreSQL's `text`/`jsonb` storage."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["u"]}, developer=True, limits=LIMITS)
        for name, field_type in (("s", "string"), ("o", "object"), ("a", "array")):
            cell.apply_schema({"operation": "add_field", "entity": "docs", "field": name, "field_type": field_type}, developer=True, limits=LIMITS)
        bad_values = {"s": "has\x00nul", "o": {"k": "has\x00nul"}, "a": ["has\x00nul"], "u": "has\x00nul"}
        # Contract 1.7.0 (D-3, WP-2e): see `test_foundation.py`'s identical
        # comment -- a typed field's NUL-byte refusal is `field_type`
        # (`declared_type`/`observed_type` both the field's own type); the
        # untyped field ("u") has `violated_declaration: request_schema`
        # instead (WP-2e rework, audit-wp2e.md D-1 = (A)/ruling L-1: every
        # choke-point site now carries `violated_declaration`).
        declared_types = {"s": "string", "o": "object", "a": "array"}
        for field_name, bad_value in bad_values.items():
            with pytest.raises(FoundationError) as exc:
                cell.transact("docs", [{"operation": "insert", "values": {field_name: bad_value}}], LIMITS)
            assert exc.value.code == "VALIDATION_FAILED"
            # Monitor ruling M-3/D: request-internal path.
            if field_name in declared_types:
                assert exc.value.details == {
                    "field": f"operations/0/values/{field_name}", "violated_declaration": "field_type",
                    "declared_type": declared_types[field_name], "observed_type": declared_types[field_name],
                }
            else:
                assert exc.value.details == {"field": f"operations/0/values/{field_name}", "violated_declaration": "request_schema"}
        assert cell.query("docs", select=["u"], where=[], page_size=10, limits=LIMITS).items == []
    finally:
        cell.close()


def test_expected_revision_containing_nul_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "docs", "fields": ["body"]}, developer=True, limits=LIMITS)
        cell.transact("docs", [{"operation": "insert", "values": {"body": "v1"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "docs",
                [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"body": "v2"}, "expected_revision": "has\x00nul"}],
                LIMITS,
            )
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_matches_pattern_ending_in_an_unescaped_backslash_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    """WP-3 review blocker-2 (Q-2 adjudication 5): rejected deterministically
    in the shared boundary before this backend's own LIKE execution -- a
    trailing bare backslash's behaviour there would otherwise depend on
    stored data (non-deterministic from the client's point of view)."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"label": "a"}}], LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["label"], where=[P("label", "matches", "a\\")], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=["label"], where=[P("label", "matches", "a\\\\\\")], page_size=10, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        # Even trailing backslash count (paired escapes) is well-formed.
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "a\\\\")], page_size=10, limits=LIMITS)
        assert rows.items == []
        # Escape grammar boundary: `\x` (escapes a plain, non-wildcard
        # character -- matches that character literally, same as no
        # escape) and `\\` (escapes a literal backslash).
        cell.transact("items", [{"operation": "insert", "values": {"label": "a\\b"}}], LIMITS)
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "a\\\\b")], page_size=10, limits=LIMITS)
        assert rows.items == [{"label": "a\\b"}]
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "\\a")], page_size=10, limits=LIMITS)
        assert rows.items == [{"label": "a"}]
    finally:
        cell.close()


def test_postgres_write_of_an_out_of_range_number_value_is_validation_failed(app_a: types.SimpleNamespace) -> None:
    """WP-3 review blocker-2 / review corrections 2026-09-25 (task C):
    `_check_type`'s "number" branch now range-checks against a finite
    float64 (design PHASE11_KEYSET_PAGING_V1 D-3 (4a), the same domain
    check `where`/`page/cursor` share, `test_domain_out_of_range_values_
    is_validation_failed_not_service_unavailable` above) -- a value this
    large is refused there, before it ever reaches this backend's own SQL
    execution. It must never surface as `SERVICE_UNAVAILABLE` (a false
    "retry" signal to an AI agent client), and must never leak the value
    itself into the error.

    Renamed from `test_postgres_data_error_from_an_out_of_range_number_
    value_is_validation_failed`: the domain check closing this gap means
    the value no longer reaches `PostgresCell._fail_client_value`'s own
    generic `psycopg.errors.DataError` catch (WP-2e rework audit-wp2e.md
    I-6, ruling L-1 / D-1 = (A), completion-condition-6's own no-`details`
    backend-layer exemption pin) for THIS trigger -- that pin's own
    executable proof needs a different trigger value now, left to a
    separate item (the domain check itself is this WP's own scope)."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "readings", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "n", "field_type": "number"}, developer=True, limits=LIMITS)
        huge = 10**400
        with pytest.raises(FoundationError) as exc:
            cell.transact("readings", [{"operation": "insert", "values": {"n": huge}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.status == 400
        assert exc.value.details.get("violated_declaration") == "request_schema", exc.value.details
        rendered = repr(exc.value)
        assert str(huge)[:20] not in rendered
        # No side effect.
        assert cell.query("readings", select=["n"], where=[], page_size=10, limits=LIMITS).items == []
    finally:
        cell.close()


# --- object/array DOMAIN unification (R-7 addendum) -------------------------


def test_object_and_array_field_types_use_domains_and_are_distinguishable(app_a: types.SimpleNamespace) -> None:
    """WP-3 review, "object/array の DOMAIN 型統一": unlike a bare `jsonb`
    column, `_load_catalog` can now recover which of the two a column was
    declared as (via `information_schema.columns.domain_name`), and
    `_check_type` enforces the declared shape on write -- the same mapping
    `ApplicationCell` already provides, closing the previously-accepted
    cross-backend divergence.
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "typed", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "o", "field_type": "object"}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "a", "field_type": "array"}, developer=True, limits=LIMITS)

        cell.transact("typed", [{"operation": "insert", "values": {"o": {"k": 1}, "a": [1, 2]}}], LIMITS)
        rows = cell.query("typed", select=["o", "a"], where=[], page_size=10, limits=LIMITS)
        assert rows.items == [{"o": {"k": 1}, "a": [1, 2]}]

        # Null is still allowed for either domain.
        cell.transact("typed", [{"operation": "insert", "values": {}}], LIMITS)

        # A list written to a field declared "object" (and vice versa) is
        # now rejected -- the DOMAIN lets this backend tell them apart,
        # closing the gap the pre-review docstring called a "legitimate
        # divergence".
        with pytest.raises(FoundationError) as exc:
            cell.transact("typed", [{"operation": "insert", "values": {"o": [1, 2]}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        # Monitor ruling M-3/D (rulings-wp2a-review.md): request-internal
        # path, not a bare field name. Contract 1.7.0 (D-3, WP-2e):
        # `field_type` -- `declared_type` the field's own declared type,
        # `observed_type` the JSON type of the value actually received.
        assert exc.value.details == {
            "field": "operations/0/values/o", "violated_declaration": "field_type",
            "declared_type": "object", "observed_type": "array",
        }
        with pytest.raises(FoundationError) as exc:
            cell.transact("typed", [{"operation": "insert", "values": {"a": {"k": 1}}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {
            "field": "operations/0/values/a", "violated_declaration": "field_type",
            "declared_type": "array", "observed_type": "object",
        }
        # Same rejection on update.
        with pytest.raises(FoundationError) as exc:
            cell.transact("typed", [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {"o": [1]}}], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        cell.close()


def test_object_and_array_domain_name_is_read_back_from_the_live_catalog(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "typed", "fields": []}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "o", "field_type": "object"}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "a", "field_type": "array"}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "typed", "field": "plain"}, developer=True, limits=LIMITS)
        with cell._runtime.connection() as conn:
            with conn.transaction():
                info = cell._load_catalog(conn)
        table_info = info["typed"]
        assert table_info.columns["o"] == "object"
        assert table_info.columns["a"] == "array"
        assert table_info.columns["plain"] is None

        # Raw SQL-level confirmation, independent of PostgresCell's own
        # reading back: the domain really is what `information_schema`
        # reports.
        conn2 = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            with conn2.cursor() as cur:
                cur.execute(
                    "SELECT column_name, domain_name FROM information_schema.columns WHERE table_name = 'typed' AND column_name IN ('o', 'a', 'plain')"
                )
                by_column = dict(cur.fetchall())
                assert by_column["o"] == "_r2db_json_object"
                assert by_column["a"] == "_r2db_json_array"
                assert by_column["plain"] is None
        finally:
            conn2.close()
    finally:
        cell.close()


# --- assigned_addresses ordering for plain inserts (mutation M11) ----------


def test_plain_insert_assigned_addresses_returned_in_operation_order(app_a: types.SimpleNamespace) -> None:
    """A single, ordinary insert (no upsert involved at all) must still
    report its resolved address in `assigned_addresses` -- and a batch of
    several must report them in operation order, index-aligned with the
    inserts (not, say, sorted by id or reversed)."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)

        outcome = cell.transact("items", [{"operation": "insert", "values": {"label": "solo"}}], LIMITS)
        assert outcome.affected == 1
        assert outcome.assigned_addresses == [{"address": {"id": 1}}]

        outcome = cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "a"}},
                {"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "solo"}], "values": {"label": "renamed"}},
                {"operation": "insert", "values": {"label": "b"}},
                {"operation": "insert", "values": {"label": "c"}},
            ],
            LIMITS,
        )
        assert outcome.affected == 4
        # Insert-only, in operation order -- the update in between
        # contributes nothing to `assigned_addresses`, and does not shift
        # the ids reported for the inserts around it.
        assert outcome.assigned_addresses == [{"address": {"id": 2}}, {"address": {"id": 3}}, {"address": {"id": 4}}]
    finally:
        cell.close()


# --- WP-3 review D-1~D-4: predicate semantics unified with SQL's own
# three-valued logic (PostgresCell side: confirms the shared-boundary
# escaping/grammar and the *reference* implementation's parity fix, not
# this backend's own semantics, which were already SQL-native) ------------


def test_contains_and_matches_escape_grammar_boundary_with_null_rows_mixed_in(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "back\\slash"}},
                {"operation": "insert", "values": {"label": None}},
                {"operation": "insert", "values": {"label": "plainx"}},
            ],
            LIMITS,
        )
        # `\\` (escaped literal backslash) via contains -- NULL row excluded,
        # never an error.
        rows = cell.query("items", select=["label"], where=[P("label", "contains", "back\\slash")], page_size=10, limits=LIMITS)
        assert rows.items == [{"label": "back\\slash"}]
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "back\\\\slash")], page_size=10, limits=LIMITS)
        assert rows.items == [{"label": "back\\slash"}]
        # `\x` (escapes a non-wildcard character -- matches it literally,
        # same as leaving it unescaped).
        rows = cell.query("items", select=["label"], where=[P("label", "matches", "\\p\\l\\a\\i\\n\\x")], page_size=10, limits=LIMITS)
        assert rows.items == [{"label": "plainx"}]
    finally:
        cell.close()


# ==========================================================================
# Direct ApplicationCell <-> PostgresCell parity: the same scenario, run
# against both engines, asserting the observable results match (WP-3
# review D-1~D-4's own point: the reference implementation must not behave
# narrower than, or differently from, the deployed backend).
# ==========================================================================


def _memory_cell() -> ApplicationCell:
    return ApplicationCell("parity-app", {})


def test_parity_contains_matches_ne_in_with_null_rows(app_a: types.SimpleNamespace) -> None:
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "n"]}, developer=True, limits=LIMITS)
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "hello", "n": 5}},
                    {"operation": "insert", "values": {"label": None, "n": None}},
                    {"operation": "insert", "values": {"label": "help", "n": 7}},
                ],
                LIMITS,
            )

        cases = [
            ("contains", "el"),
            ("matches", "hel%"),
            ("ne", "hello"),
            ("in", ["hello", None]),
            # WP-3 confirmation review N-5: substrings of Python's own
            # `str(None)` ("None") -- makes the `if actual is None: return
            # False` guard load-bearing. Neither "hello" nor "help"
            # contains "on"/"No" (case-sensitive), so the only way either
            # of these could spuriously match is a regression that fell
            # back to formatting the NULL row's value with plain `str()`
            # instead of excluding it outright.
            ("contains", "on"),
            ("contains", "No"),
            ("matches", "%on%"),
            # WP-3 confirmation review N-5 (round 2): "ul" is a substring
            # of `_jsonb_scalar_text(None)`'s own literal output, `"null"`
            # -- this codebase's *actual* fallback text for a NULL value,
            # unlike the hypothetical `str(None)` ("None") the "on"/"No"
            # needles above guard against. Without the `if actual is None:
            # return False` short-circuit, `_predicate_text` would reach
            # `_jsonb_scalar_text(None)` -> `"null"`, and `"ul" in "null"`
            # is `True` -- so this needle is the one that actually kills a
            # regression that removes the guard from *this* code path.
            ("contains", "ul"),
        ]
        for operator, value in cases:
            pg_items = pg.query("items", select=["label"], where=[P("label", operator, value)], page_size=10, limits=LIMITS).items
            mem_items = mem.query("items", select=["label"], where=[Predicate("label", operator, value)], page_size=10, limits=LIMITS).items
            assert sorted(pg_items, key=str) == sorted(mem_items, key=str), operator
        # The N-5 needles specifically must match nothing at all on either
        # cell -- not merely "agree with each other" (two cells that both
        # spuriously matched the NULL row would also "agree").
        for operator, value in cases[-4:]:
            assert pg.query("items", select=["label"], where=[P("label", operator, value)], page_size=10, limits=LIMITS).items == [], (operator, value)
    finally:
        pg.close()


def test_parity_contains_matches_with_integer_valued_float_on_a_typed_number_column(app_a: types.SimpleNamespace) -> None:
    """WP-3 confirmation review N-1: `_predicate_text`'s float formatting
    must match PostgreSQL's `float8out` (invoked by `PostgresCell._text_
    expression`'s plain `::text` cast on a `double precision` column) --
    an integer-valued float drops its trailing `.0`. This is a `field_type:
    "number"` column specifically: an *untyped* JSONB column's own numeric
    storage preserves the original literal text instead (confirmed
    empirically against a real server -- `('100.0'::jsonb) #>> '{}'` stays
    `"100.0"`, never dropping the `.0`), which is `PostgresCell`'s existing,
    unrelated `#>> '{}'` behaviour for untyped columns, not something this
    fix touches.
    """
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "readings", "fields": []}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "n", "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("readings", [{"operation": "insert", "values": {"n": 100.0}}, {"operation": "insert", "values": {"n": 1234567890123.0}}], LIMITS)

        for needle, expect_match in (("100", True), (".0", False), ("1234567890123", True)):
            pg_items = pg.query("readings", select=["n"], where=[P("n", "contains", needle)], page_size=10, limits=LIMITS).items
            mem_items = mem.query("readings", select=["n"], where=[Predicate("n", "contains", needle)], page_size=10, limits=LIMITS).items
            assert pg_items == mem_items, needle
            assert bool(pg_items) is expect_match, needle
    finally:
        pg.close()


def test_parity_contains_on_untyped_float_and_nested_float_use_jsonb_numeric_rules(app_a: types.SimpleNamespace) -> None:
    """WP-3 confirmation review N-1 correction: the first pass applied
    `float8out`-style formatting (drop trailing `.0`) to EVERY float
    regardless of column type or nesting position -- correct only for a
    TYPED `"number"` column's TOP-LEVEL scalar. An UNTYPED top-level float,
    or a float at ANY nested position (inside a dict/list, even one
    declared `field_type: "object"`/`"array"`), must instead use
    PostgreSQL jsonb's own numeric storage/output rules: trailing zeros
    are PRESERVED (never dropped), and scientific notation is EXPANDED to
    full plain-decimal digits (confirmed empirically against a real
    server: `('1e+20'::jsonb) #>> '{}'` -> `"100000000000000000000"`,
    never `"1e+20"`) -- the opposite of `float8out` on both counts.
    """
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["n", "payload"]}, developer=True, limits=LIMITS)
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"n": 100.0}},
                    {"operation": "insert", "values": {"n": 1e20}},
                    {"operation": "insert", "values": {"payload": {"yy": 1.0}}},
                ],
                LIMITS,
            )

        cases = [
            # Untyped top-level float: trailing `.0` is preserved (unlike
            # a typed "number" column, where `float8out` would drop it).
            ("n", "100.0", True),
            # Scientific notation is expanded to full decimal digits.
            ("n", "100000000000000000000", True),
            ("n", "1e+20", False),
            # Nested float (inside an untyped dict): `.0` preserved.
            ("payload", '"yy": 1.0', True),
            ("payload", '"yy": 1}', False),
        ]
        for field, needle, expect_match in cases:
            pg_items = pg.query("items", select=[field], where=[P(field, "contains", needle)], page_size=10, limits=LIMITS).items
            mem_items = mem.query("items", select=[field], where=[Predicate(field, "contains", needle)], page_size=10, limits=LIMITS).items
            assert pg_items == mem_items, (field, needle)
            assert bool(pg_items) is expect_match, (field, needle)
    finally:
        pg.close()


def test_parity_contains_with_mixed_key_length_dict(app_a: types.SimpleNamespace) -> None:
    """WP-3 confirmation review N-2: an object's key order in its
    `contains`/`matches` text form is PostgreSQL's own jsonb storage order
    -- `(byte length, byte value)`, not Python's default alphabetical
    string sort. `"aa"` sorts *before* `"b"` alphabetically but is
    *longer*, so the two orderings disagree here: the literal substring
    `{"b": 1, "aa": 2}` is only found if the byte-length rule is actually
    applied (alphabetical order would produce `{"aa": 2, "b": 1}` instead,
    in which that substring never appears at all).
    """
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["payload"]}, developer=True, limits=LIMITS)
            cell.transact("items", [{"operation": "insert", "values": {"payload": {"b": 1, "aa": 2}}}], LIMITS)

        needle = '{"b": 1, "aa": 2}'
        pg_items = pg.query("items", select=["payload"], where=[P("payload", "contains", needle)], page_size=10, limits=LIMITS).items
        mem_items = mem.query("items", select=["payload"], where=[Predicate("payload", "contains", needle)], page_size=10, limits=LIMITS).items
        assert pg_items == mem_items == [{"payload": {"b": 1, "aa": 2}}]

        # The alphabetically-sorted form must NOT be found on either cell
        # -- proving this isn't a coincidental match on an unordered
        # substring check.
        wrong_order = '{"aa": 2, "b": 1}'
        assert pg.query("items", select=["payload"], where=[P("payload", "contains", wrong_order)], page_size=10, limits=LIMITS).items == []
        assert mem.query("items", select=["payload"], where=[Predicate("payload", "contains", wrong_order)], page_size=10, limits=LIMITS).items == []
    finally:
        pg.close()


def test_parity_contains_matches_on_typed_non_string_columns(app_a: types.SimpleNamespace) -> None:
    """WP-3 confirmation review N-6: `contains`/`matches` against typed
    non-string columns (integer, boolean), directly cross-checked between
    both engines rather than only verified against `PostgresCell` alone."""
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "readings", "fields": []}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "n", "field_type": "integer"}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "flag", "field_type": "boolean"}, developer=True, limits=LIMITS)
            cell.transact(
                "readings",
                [{"operation": "insert", "values": {"n": 12345, "flag": True}}, {"operation": "insert", "values": {"n": 999, "flag": False}}],
                LIMITS,
            )
        for field, operator, value in (("n", "contains", "234"), ("flag", "matches", "tr%"), ("flag", "contains", "fals")):
            pg_items = pg.query("readings", select=[field], where=[P(field, operator, value)], page_size=10, limits=LIMITS).items
            mem_items = mem.query("readings", select=[field], where=[Predicate(field, operator, value)], page_size=10, limits=LIMITS).items
            assert pg_items == mem_items, (field, operator, value)
    finally:
        pg.close()


def test_parity_order_by_null_placement_and_cross_type(app_a: types.SimpleNamespace) -> None:
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "tasks", "fields": []}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "tasks", "field": "priority", "field_type": "integer"}, developer=True, limits=LIMITS)
            cell.transact(
                "tasks",
                [
                    {"operation": "insert", "values": {"priority": 2}},
                    {"operation": "insert", "values": {"priority": None}},
                    {"operation": "insert", "values": {"priority": 1}},
                ],
                LIMITS,
            )
        for direction in ("asc", "desc"):
            pg_items = pg.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": direction}]).items
            mem_items = mem.query("tasks", select=["priority"], where=[], page_size=10, limits=LIMITS, order_by=[{"field": "priority", "direction": direction}]).items
            assert pg_items == mem_items, direction
    finally:
        pg.close()


def test_parity_upsert_representative_branches(app_a: types.SimpleNamespace) -> None:
    pg = make_cell(app_a)
    mem = _memory_cell()
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "people", "fields": ["email", "name"]}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "create_index", "entity": "people", "index": "by_email", "fields": ["email"], "unique": True}, developer=True, limits=LIMITS)

        for cell in (pg, mem):
            outcome = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann"}}], LIMITS)
            assert outcome.affected == 1
            assert outcome.assigned_addresses == [{"address": {"id": 1}}]
            outcome2 = cell.transact("people", [{"operation": "upsert", "values": {"email": "a@example.invalid", "name": "Ann2"}}], LIMITS)
            assert outcome2.affected == 1
            assert outcome2.assigned_addresses == []

        pg_items = pg.query("people", select=["id", "name"], where=[], page_size=10, limits=LIMITS).items
        mem_items = mem.query("people", select=["id", "name"], where=[], page_size=10, limits=LIMITS).items
        assert pg_items == mem_items == [{"id": 1, "name": "Ann2"}]
    finally:
        pg.close()


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
                assert rows.items == [{"value": "app-a-only"}]

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


# ===========================================================================
# Q4 phase WP-3 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3,
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md
# WP-3): the per-application platform-upgrade ledger -- `0003`'s revised
# template seed, `0009`'s retrofit for a pre-existing application, the
# backend bookkeeping-exclusion set, and the cell open time check (F-12).
# ===========================================================================


def _ledger_numbers(dsn: str) -> frozenset[int]:
    conn = psycopg.connect(dsn)
    try:
        return platform_upgrades.read_applied_upgrade_numbers(conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME) or frozenset()
    finally:
        conn.close()


def _rewrite_0009(prefix: str, tmp_path: Path) -> Path:
    text = (MIGRATIONS_DIR / "0009_platform_upgrades_ledger_upgrade.sql").read_text().replace("r2dbsvc", prefix)
    out = tmp_path / "0009_platform_upgrades_ledger_upgrade.sql"
    out.write_text(text)
    return out


def _rewrite_0010(prefix: str, tmp_path: Path) -> Path:
    text = (MIGRATIONS_DIR / "0010_field_constraints_upgrade.sql").read_text().replace("r2dbsvc", prefix)
    out = tmp_path / "0010_field_constraints_upgrade.sql"
    out.write_text(text)
    return out


def _rewrite_0011(prefix: str, tmp_path: Path) -> Path:
    text = (MIGRATIONS_DIR / "0011_idempotency_records_upgrade.sql").read_text().replace("r2dbsvc", prefix)
    out = tmp_path / "0011_idempotency_records_upgrade.sql"
    out.write_text(text)
    return out


def test_template_seeds_the_ledger_with_the_current_platform_upgrade_numbers(app_a: types.SimpleNamespace) -> None:
    """完了条件 1/5: `0003` テンプレートで新規 provision した application の
    台帳が、パッケージ定数 `platform_upgrades.PLATFORM_UPGRADE_NUMBERS`
    (Phase 9 WP-2a で `10` (field-constraints side table)、WP-2c で `11`
    (idempotency-record side table) が加わり `{9, 10, 11}`) と一致するこ
    と。"""
    assert _ledger_numbers(app_a.developer_dsn) == platform_upgrades.PLATFORM_UPGRADE_NUMBERS == frozenset({9, 10, 11})


def test_0009_has_no_skip_path() -> None:
    """完了条件 3 (監査照合の実測版): `0009` に `\\q` によるskip経路が無い
    こと -- design §1.5 の 7a、静的規則の走査対象外の性質を直接 grep で
    固定する。"""
    text = (MIGRATIONS_DIR / "0009_platform_upgrades_ledger_upgrade.sql").read_text()
    assert "\\q" not in text


def test_0009_upgrades_a_legacy_application_to_match_a_freshly_provisioned_ledger(
    platform: types.SimpleNamespace, tmp_path: Path
) -> None:
    """完了条件 1/2/5: `0009` を「台帳の無い既存 application」(WP-3 以前に
    provision された状態を、台帳表を落として模する) に当てると、新規
    provision (`0003`) と同じ終状態 (`{9}`) に着くこと。2 回適用しても
    終状態が変わらないこと (冪等)。"""
    script = _rewrite_0009(platform.prefix, tmp_path)
    with provisioned_apps(platform, ["upglegacy"]) as apps:
        app = apps[0]
        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._r2db_platform_upgrades")
        finally:
            conn.close()
        assert _ledger_numbers(app.developer_dsn) == frozenset()

        _run_psql(platform.control_dsn, script, {"app_slug": app.slug})
        first = _ledger_numbers(app.developer_dsn)
        assert first == frozenset({9})

        _run_psql(platform.control_dsn, script, {"app_slug": app.slug})
        second = _ledger_numbers(app.developer_dsn)
        assert second == first == frozenset({9})


def test_0009_failure_leaves_no_ledger_table_or_row_behind(platform: types.SimpleNamespace, tmp_path: Path) -> None:
    """完了条件 4 (実 PG、設計 §10 実 PG 確認項目 4): 本体 (`BEGIN` ...
    `COMMIT`) の途中に失敗を注入すると psql が非 0 で終わり、台帳表その
    ものが (トランザクショナル DDL のため) 存在しないこと -- 行が残らない
    ことの上位互換の実測。"""
    real_text = (MIGRATIONS_DIR / "0009_platform_upgrades_ledger_upgrade.sql").read_text().replace("r2dbsvc", platform.prefix)
    mutated_text = real_text.replace("COMMIT;\n", "SELECT 1/0;\nCOMMIT;\n", 1)
    assert mutated_text != real_text, "mutation did not actually change the script text"
    mutated_script = tmp_path / "0009_mutated_failure_injection.sql"
    mutated_script.write_text(mutated_text)

    with provisioned_apps(platform, ["upgfail"]) as apps:
        app = apps[0]
        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._r2db_platform_upgrades")
        finally:
            conn.close()

        with pytest.raises(RuntimeError, match="division by zero"):
            _run_psql(platform.control_dsn, mutated_script, {"app_slug": app.slug})

        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public._r2db_platform_upgrades')")
                assert cur.fetchone() == (None,), "a failed run must not leave the ledger table behind at all"
        finally:
            conn.close()


def test_runtime_role_can_select_but_not_write_the_ledger(app_a: types.SimpleNamespace) -> None:
    """完了条件 6 (U-2 逐語): runtime 接続で `SELECT` が通り、`INSERT` /
    `UPDATE` / `DELETE` は `permission denied` になること。"""
    conn = psycopg.connect(app_a.runtime_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT upgrade_number FROM public._r2db_platform_upgrades")
            assert cur.fetchall() == [(9,), (10,), (11,)]
        for statement in (
            "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name) VALUES (99, 'x')",
            "UPDATE public._r2db_platform_upgrades SET script_name = 'y' WHERE upgrade_number = 9",
            "DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.cursor() as cur:
                    cur.execute(statement)
            conn.rollback()
    finally:
        conn.close()


def test_provision_role_can_read_the_ledger_after_the_script_ends(app_a: types.SimpleNamespace, platform: types.SimpleNamespace) -> None:
    """完了条件 7: script 終了後 (`REVOKE :"developer_role" FROM
    CURRENT_USER` の後) の provision DSN から `dbname` を差し替えた接続で
    `SELECT` が通ること -- 付与が無いと `ops upgrade-applications
    --dry-run` すら動かない (設計 D-3(a))。"""
    dsn = _dsn_with(platform.control_dsn, dbname=app_a.database)
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT upgrade_number FROM public._r2db_platform_upgrades")
            assert cur.fetchall() == [(9,), (10,), (11,)]
    finally:
        conn.close()


def test_ledger_table_has_no_row_level_security(app_a: types.SimpleNamespace) -> None:
    """完了条件 8: `pg_class.relrowsecurity` / `relforcerowsecurity` が
    ともに false であること (監督裁定 2026-09-05: FORCE RLS は所有者にも
    適用され、provision -> `SET ROLE developer` の書き込みが拒まれる)。"""
    conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = '_r2db_platform_upgrades'"
            )
            assert cur.fetchone() == (False, False)
    finally:
        conn.close()


_PRE_WP3_MISSING_RLS_VIEW = (
    "CREATE OR REPLACE VIEW public._r2db_missing_rls AS "
    "SELECT c.relname AS table_name FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
    "AND c.relname <> '_r2db_schema_revision' "
    "AND (c.relrowsecurity = false OR c.relforcerowsecurity = false)"
)


def test_missing_rls_view_stays_empty_on_both_a_new_and_an_upgraded_application(
    platform: types.SimpleNamespace, tmp_path: Path
) -> None:
    """完了条件 9: `_r2db_missing_rls` が、テンプレート経由の新規 DB と
    `0009`+`0010`+`0011` 適用済みの既存 DB の両方で空のままであること
    (設計 D-3(e)(ii)、Phase 9 WP-2a/WP-2c: テンプレートと 3 本すべての
    per-app upgrade script が `CREATE OR REPLACE VIEW` を要る)。「既存
    DB」は、3 つの bookkeeping table はある (`0003` 適用時と同じ) がその
    `_r2db_missing_rls` の定義だけが WP-3 以前の (どの table 名も除外し
    ない) 版で固まっている状態を、ビューだけを古い定義へ戻すことで模する
    -- table を丸ごと落とすと「比較対象も無い」形になり、この条件の非空振
    り (3 本すべての per-app upgrade script が要ること、`0009`/`0010` だ
    けでは `_r2db_idempotency` を除外し切れないこと) を実測できない。"""
    script_0009 = _rewrite_0009(platform.prefix, tmp_path)
    script_0010 = _rewrite_0010(platform.prefix, tmp_path)
    script_0011 = _rewrite_0011(platform.prefix, tmp_path)
    with provisioned_apps(platform, ["missrlsnew", "missrlsold"]) as apps:
        new_app, legacy_app = apps

        conn = psycopg.connect(new_app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert cur.fetchall() == []
        finally:
            conn.close()

        # Simulate "provisioned before WP-3": only the VIEW is reverted to
        # its pre-WP-3 definition (all three bookkeeping tables (the
        # ledger, and -- Phase 9 WP-2a/WP-2c -- the field-constraints and
        # idempotency-record side tables), both seeded/created by the
        # now-updated `0003`, are left in place -- unaffected by this
        # revert, and none has RLS, design D-3(a)/D-2(4)/D-5(6)). With the
        # OLD view in place, all three bookkeeping tables now show up as
        # false-positive offenders -- exactly the drift `0009`'s own
        # `CREATE OR REPLACE VIEW` must correct.
        conn = psycopg.connect(legacy_app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(_PRE_WP3_MISSING_RLS_VIEW)
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert sorted(row[0] for row in cur.fetchall()) == ["_r2db_field_constraints", "_r2db_idempotency", "_r2db_platform_upgrades"], (
                    "test setup sanity check: the pre-WP-3 view must see all three bookkeeping tables as offenders"
                )
        finally:
            conn.close()

        # `0009` alone re-installs the view but only excludes the ledger
        # table (unmodified by this WP) -- `_r2db_field_constraints`/
        # `_r2db_idempotency` remain false-positive offenders until `0010`/
        # `0011` also run (non-vacuity: no single script alone suffices).
        _run_psql(platform.control_dsn, script_0009, {"app_slug": legacy_app.slug})
        conn = psycopg.connect(legacy_app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert sorted(row[0] for row in cur.fetchall()) == ["_r2db_field_constraints", "_r2db_idempotency"], (
                    "0009 alone must still see the field-constraints and idempotency tables as offenders"
                )
        finally:
            conn.close()

        _run_psql(platform.control_dsn, script_0010, {"app_slug": legacy_app.slug})
        conn = psycopg.connect(legacy_app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert [row[0] for row in cur.fetchall()] == ["_r2db_idempotency"], (
                    "0009+0010 must still see the idempotency table as an offender until 0011 also runs"
                )
        finally:
            conn.close()

        _run_psql(platform.control_dsn, script_0011, {"app_slug": legacy_app.slug})
        conn = psycopg.connect(legacy_app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM public._r2db_missing_rls")
                assert cur.fetchall() == []
        finally:
            conn.close()


def test_backend_excludes_the_ledger_from_catalog_and_schema_objects_accounting(app_a: types.SimpleNamespace) -> None:
    """完了条件 10 (設計 D-3(e)(i)、実 PG 確認項目 5): 台帳表がある DB で
    (i) `application_catalog` (`cell.catalog()`) が台帳表を entities に
    含めないこと、(ii) `create_entity` が 503 にならないこと (`_create_
    entity` 直後の RLS 検査が台帳表を offenders に含めない)、(iii)
    `verify_row_level_security` が通ること、(iv) `schema_objects` の会計
    が台帳表の分だけずれていない (`+1` にならない) ことを、境界値ちょうど
    での `LIMIT_EXCEEDED` 判定で実測する。"""
    cell = make_cell(app_a)
    try:
        catalog = cell.catalog()
        assert catalog == [], "a freshly provisioned application's catalog must be empty -- the ledger must not appear in it"

        # (iv) exact schema_objects accounting: 1 entity + id + 1 declared
        # field = 3 objects. If the ledger table (3 columns of its own)
        # were mistakenly counted by `_load_catalog`, this would either
        # raise LIMIT_EXCEEDED at exactly 3, or require a higher bound to
        # succeed -- observed both ways below.
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=ResourceLimits(schema_objects=2))
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert cell.catalog() == [], "the rejected create_entity must not have left a table behind"

        # (ii)/(iii) at the correct boundary (schema_objects=3), the SAME
        # operation succeeds without 503 -- and `verify_row_level_security`
        # (which reads `_rls_offenders`, the OTHER exclusion-set call site)
        # agrees the database is clean.
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=ResourceLimits(schema_objects=3))
        cell.verify_row_level_security()

        # (i) again, now with a real entity present: the catalog lists
        # exactly the entity just created, never the ledger table.
        catalog = cell.catalog()
        assert [entry["entity"] for entry in catalog] == ["widgets"]
    finally:
        cell.close()


def test_verify_platform_upgrades_applied_passes_when_the_ledger_is_complete(app_a: types.SimpleNamespace) -> None:
    """完了条件 11 (前半): 台帳が揃った DB では通常どおり通ること。"""
    cell = make_cell(app_a)
    try:
        cell.verify_platform_upgrades_applied()  # must not raise
    finally:
        cell.close()


def test_verify_platform_upgrades_applied_raises_service_unavailable_when_a_number_is_missing(app_a: types.SimpleNamespace) -> None:
    """完了条件 11: 台帳から 1 番号を削った application DB では、cell を
    開く時点で F-12 (`SERVICE_UNAVAILABLE`) になること。F-12 の骨子を
    設計 §3.8 から逐語 assert する (常設規律 4)。"""
    conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
    finally:
        conn.close()

    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.verify_platform_upgrades_applied()
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert exc.value.status == 503
        assert exc.value.message == (
            "This application's storage is missing platform upgrade(s) 9: the deployment must apply "
            "them before this application can serve requests. Run 'python -m r2db_api.ops "
            "upgrade-applications --lock-timeout <value>' (its '--dry-run' shows applied and pending "
            "per application and requires the same '--lock-timeout'), then retry."
        )
    finally:
        cell.close()


def test_verify_platform_upgrades_applied_raises_when_the_ledger_table_is_entirely_absent(app_a: types.SimpleNamespace) -> None:
    """完了条件 11 の「台帳表そのものが無い場合を含む」: `read_applied_
    upgrade_numbers` の `None` センチネル (表が無い) が集合差の計算で
    「全番号が未適用」として扱われること。"""
    conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE public._r2db_platform_upgrades")
    finally:
        conn.close()

    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.verify_platform_upgrades_applied()
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert "missing platform upgrade(s) 9" in exc.value.message
    finally:
        cell.close()
