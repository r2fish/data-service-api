"""`PostgresCredentialStore` (`r2db_api.credential_store`), `python -m
r2db_api.ops`, and `r2db_api.main`'s composition root -- tested against a
real PostgreSQL server, mirroring `test_postgres.py`'s own conventions
(§5.3 C-5: "this work machine has PostgreSQL 16 running; ... must be
verified against it, not skipped").

Design this file is written against: docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md §4 ("テスト要求").
Everything this file creates in the cluster is named under one
random-per-run `r2dbtest<8 hex>` prefix -- the exact same convention
`test_postgres.py` already uses (this repository's own review explicitly
allows the `r2db(test|svc|http)` prefix families; nothing outside them, and
none of the pre-existing unrelated objects named in that review
(`r2db_control`, `r2db_admin`, `auth_api`, the `app_*` databases), is ever
read, listed, or touched) -- and is dropped in a module-scoped fixture
finalizer that runs even if a test fails.

Most tests below register an application by inserting a synthetic
`r2dbsvc_registry.applications` row directly (`_register_application`)
rather than running the full `0003_provision_application.sql` script: the
credential-store/CLI behaviour under test here never touches the
application's own database at all (only the platform database's
`applications`/`credentials` tables), so provisioning a real
per-application database for every one of these tests would only add
PostgreSQL round trips without exercising anything this file is actually
about. The composition-root (`r2db_api.main`) tests are the one place a
*real* provisioned application is required (`PostgresCell` needs real
runtime/developer roles and an actual database to connect to) -- those use
the `provisioned_app` fixture, which does run the real `0003` script,
exactly like `test_postgres.py::app_a`.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.testclient import TestClient

from r2db_api.credential_store import PostgresCredentialStore
from r2db_api.errors import FoundationError

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
PEPPER = "synthetic-test-pepper-credential-persistence-0000"


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
            "test_credential_persistence.py requires a reachable local PostgreSQL "
            f"server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These "
            "tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    """Identical in spirit and mechanics to `test_postgres.py::_sweep_
    prefix` / `conformance_adapter_r2db_http.py::_sweep_prefix` (duplicated
    rather than imported, matching those two files' own established
    precedent of not taking an import-time dependency on another module in
    this repository): drop every database and role whose name starts with
    this run's unique prefix, retrying `DROP DATABASE` briefly on
    `ObjectInUse` (a connection this module's own tests just closed can
    take a brief moment to fully disappear from `pg_stat_activity`).
    """
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
    """Bootstraps `0001`/`0002`/`0005`/`0006` (control plane + credential
    store + control-plane HTTP storage, CCR-14 WP-2) under one throwaway
    prefix, exactly like `test_postgres.py::platform` plus the `0005`/`0006`
    steps. `0003`/`0004` are rewritten and kept too, for the one fixture
    (`provisioned_app`, below) that needs a real per-application database.
    `0006` is applied here (not only in `test_control_plane_store.py`)
    because `python -m r2db_api.ops`'s pre-existing subcommands now write to
    `control_audit` in the same transaction as their state change (§8
    M-10) -- every `_run_cli` invocation in this file needs that table to
    exist.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtest{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_cred_migrations")
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        "0005_credential_store.sql",
        "0006_control_plane_http.sql",
    ):
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
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=f"{prefix}_controlplane", password=controlplane_password, dbname=platform_db)

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        control_role=control_role,
        api_dsn=api_dsn,
        api_role=api_role,
        platform_db=platform_db,
        schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        credential_store_sql=rewritten["0005_credential_store.sql"],
        control_plane_sql=rewritten["0006_control_plane_http.sql"],
        api_password=api_password,
        controlplane_dsn=controlplane_dsn,
        controlplane_password=controlplane_password,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _fresh_slug(letter: str) -> str:
    return f"{letter}{secrets.token_hex(3)}"


def _register_application(platform: types.SimpleNamespace, slug: str, *, enabled: bool = True) -> None:
    """Insert a synthetic, already-*provisioned* `applications` row
    directly, without running the real `0003` script -- see this module's
    own docstring for why that is the right tradeoff for tests that only
    exercise the credential store / CLI, never `PostgresCell`/a real
    per-application database. `database_name`/`runtime_role`/
    `developer_role` are synthetic placeholders (never a real, connectable
    role) -- fine, because nothing in this file's non-`provisioned_app`
    tests ever tries to connect as them. `provisioned_at` is supplied
    explicitly (CCR-14 WP-2, `0006_control_plane_http.sql` drops that
    column's own `DEFAULT now()` -- see that migration's header): this
    helper always produces a fully-provisioned row (all four columns set),
    matching every existing caller's expectation that `_register_
    application` alone is enough to issue/authenticate a credential against
    `slug`. A *registered-only* row (all four columns NULL) is a distinct,
    deliberately separate helper -- see `_register_application_only` below,
    used by this WP's own two-state tests.
    """
    statement = sql.SQL(
        "INSERT INTO {table} (application_slug, database_name, runtime_role, developer_role, enabled, provisioned_at) VALUES (%s, %s, %s, %s, %s, now())"
    ).format(table=sql.Identifier(platform.schema, "applications"))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [slug, f"synthetic_db_{slug}", f"synthetic_{slug}_runtime", f"synthetic_{slug}_developer", enabled])
        conn.commit()


def _register_application_only(platform: types.SimpleNamespace, slug: str, *, enabled: bool = True) -> None:
    """Insert a *registered-only* `applications` row (R-4/§8 B-1's new
    state: all four provisioning columns NULL) -- the counterpart to
    `_register_application` above, which always produces a fully-
    provisioned row. Used by this WP's own two-state round-trip tests.
    """
    statement = sql.SQL("INSERT INTO {table} (application_slug, enabled) VALUES (%s, %s)").format(
        table=sql.Identifier(platform.schema, "applications")
    )
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [slug, enabled])
        conn.commit()


def _set_application_enabled(platform: types.SimpleNamespace, slug: str, enabled: bool) -> None:
    statement = sql.SQL("UPDATE {table} SET enabled = %s WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "applications"))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [enabled, slug])
        conn.commit()


def _write_store(platform: types.SimpleNamespace) -> PostgresCredentialStore:
    return PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)


def _read_store(platform: types.SimpleNamespace) -> PostgresCredentialStore:
    """The strictly read-only path: connects as `<prefix>_api`
    (0005's grants are `SELECT` only). Used by the tests below that
    specifically verify the least-privilege role's grants are sufficient
    for the whole `authenticate`/`assert_active` read path -- P2-D3's
    actual security property, not just its naming.
    """
    return PostgresCredentialStore(platform.api_dsn, pepper=PEPPER, schema=platform.schema)


# ---------------------------------------------------------------------------
# Persistence across separate store instances ("restart" equivalent).
# ---------------------------------------------------------------------------


def test_credential_persists_and_is_visible_to_a_separate_store_instance(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pa")
    _register_application(platform, slug)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add("crd_" + secrets.token_hex(8), slug, "runtime", "s3cret-persist", work=work)
    finally:
        writer.close()

    # A brand-new store instance -- its own fresh pool, no shared Python
    # state with `writer` above -- stands in for "a restarted process" per
    # design §4. Using the *read-only* role here also proves P2-D3's grants
    # (`SELECT` only) are sufficient for the entire authenticate path.
    reader = _read_store(platform)
    try:
        context = reader.authenticate("s3cret-persist")
        assert context.application_id == slug
        assert context.role == "runtime"
    finally:
        reader.close()


def test_application_id_for_and_canonical_context_resolve_after_persistence(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pb")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "developer", "s3cret-canonical", work=work)
        reader = _read_store(platform)
        try:
            assert reader.application_id_for(credential_id) == slug
            context = reader.authenticate("s3cret-canonical")
            canonical = reader.canonical_context(context)
            assert canonical is not None
            assert canonical.application_id == slug
            assert canonical.role == "developer"
        finally:
            reader.close()
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# Propagation bound 0: a change committed over a *different* connection is
# visible to the very next call on an already-open store/connection.
# ---------------------------------------------------------------------------


def test_revoke_from_a_separate_connection_is_visible_immediately(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pc")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    long_lived_reader = _read_store(platform)
    try:
        writer = _write_store(platform)
        try:
            with writer.unit_of_work() as work:
                writer.add(credential_id, slug, "runtime", "s3cret-revoke", work=work)
        finally:
            writer.close()

        context = long_lived_reader.authenticate("s3cret-revoke")

        # A *different* store/connection (CLI-equivalent) performs the
        # revoke -- `long_lived_reader` above has no cache to invalidate,
        # so this is the actual mechanism, not a coincidence of timing.
        revoker = _write_store(platform)
        try:
            with revoker.unit_of_work() as work:
                revoker.set_state(credential_id, revoked=True, work=work)
        finally:
            revoker.close()

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.authenticate("s3cret-revoke")
        assert exc.value.code == "AUTH_REVOKED"
        assert exc.value.status == 401

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.assert_active(context)
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        long_lived_reader.close()


def test_application_disable_from_a_separate_connection_is_visible_immediately(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pd")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-appdisable", work=work)
    finally:
        writer.close()

    long_lived_reader = _read_store(platform)
    try:
        context = long_lived_reader.authenticate("s3cret-appdisable")
        _set_application_enabled(platform, slug, False)

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.authenticate("s3cret-appdisable")
        assert exc.value.code == "APPLICATION_DISABLED"
        assert exc.value.status == 403

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.assert_active(context)
        assert exc.value.code == "APPLICATION_DISABLED"

        _set_application_enabled(platform, slug, True)
        # No cache anywhere -- re-enabling is visible immediately too.
        long_lived_reader.authenticate("s3cret-appdisable")
    finally:
        long_lived_reader.close()


# ---------------------------------------------------------------------------
# Restart persistence of application disable (P2-D2's fail-open concern).
# ---------------------------------------------------------------------------


def test_application_disable_survives_a_new_store_instance(platform: types.SimpleNamespace) -> None:
    """The specific fail-open scenario P2-D2 exists to close: an
    application disabled via the CLI must still be disabled after the API
    process restarts, not silently re-enabled because the disabled state
    only ever lived in a since-discarded in-memory set. A brand-new store
    instance here stands in for that restart.
    """
    slug = _fresh_slug("pe")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-restart-disable", work=work)
    finally:
        writer.close()

    _set_application_enabled(platform, slug, False)

    # A fresh process/instance, with no memory of the disable above other
    # than what it reads from PostgreSQL right now.
    post_restart_reader = _read_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            post_restart_reader.authenticate("s3cret-restart-disable")
        assert exc.value.code == "APPLICATION_DISABLED"
    finally:
        post_restart_reader.close()


# ---------------------------------------------------------------------------
# Fail-closed: PostgreSQL unreachable -> AUTH_STATE_UNAVAILABLE (503), never
# AUTH_INVALID (401).
# ---------------------------------------------------------------------------


def _unreachable_dsn() -> str:
    # Port 1 on loopback: not a privileged operation to attempt connecting
    # to, and overwhelmingly unlikely to have anything listening -- a
    # near-instant ECONNREFUSED rather than a multi-second connect timeout,
    # which is what actually keeps this test fast.
    return "host=127.0.0.1 port=1 dbname=nope user=nope password=nope connect_timeout=2"


def test_authenticate_fails_closed_when_platform_db_is_unreachable() -> None:
    store = PostgresCredentialStore(_unreachable_dsn(), pepper=PEPPER)
    try:
        with pytest.raises(FoundationError) as exc:
            store.authenticate("any-secret-at-all")
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
        assert exc.value.status == 503
    finally:
        store.close()


def test_assert_active_fails_closed_when_platform_db_is_unreachable() -> None:
    from r2db_api.auth import AuthContext

    store = PostgresCredentialStore(_unreachable_dsn(), pepper=PEPPER)
    try:
        with pytest.raises(FoundationError) as exc:
            store.assert_active(AuthContext("crd_whatever", "someapp", "runtime"))
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
        assert exc.value.status == 503
    finally:
        store.close()


def test_available_false_fails_closed_without_touching_the_database(platform: types.SimpleNamespace) -> None:
    store = _read_store(platform)
    try:
        store.available = False
        with pytest.raises(FoundationError) as exc:
            store.authenticate("irrelevant")
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
        assert exc.value.status == 503
    finally:
        store.close()


def test_authenticate_never_hangs_across_repeated_pool_exhaustion_and_recovers_once_reachable(
    platform: types.SimpleNamespace,
) -> None:
    """Review-reported regression: `authenticate()` against an unreachable
    platform DB used to permanently block starting from the
    `maxconn`-plus-first call (`_RolePool._acquire`'s `_created` leak --
    see `test_postgres.py::
    test_role_pool_never_hangs_after_repeated_connect_failures_and_recovers`
    for the underlying mechanism, fixed in that same file). This test
    exercises the property at the layer the review actually measured it
    against: `PostgresCredentialStore.authenticate()`, called `maxconn + 2`
    times in a row against an unreachable platform DSN, each one bounded by
    a background-thread timeout so a reintroduced regression fails this
    test instead of hanging the suite -- then confirms the same store
    recovers once its pool's target becomes reachable again.
    """
    import concurrent.futures

    maxconn = 2
    store = PostgresCredentialStore(
        _unreachable_dsn(), pepper=PEPPER, schema=platform.schema, pool_size=maxconn, connect_timeout=1, acquire_timeout=1
    )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            for attempt_number in range(maxconn + 2):
                future = executor.submit(store.authenticate, "irrelevant-secret")
                try:
                    future.result(timeout=10)
                except concurrent.futures.TimeoutError:
                    pytest.fail(
                        f"authenticate() call #{attempt_number + 1} did not return within 10s -- "
                        "this is the pool-exhaustion hang regression this test guards against"
                    )
                except FoundationError as exc:
                    assert exc.code == "AUTH_STATE_UNAVAILABLE"
                    assert exc.status == 503
                else:
                    pytest.fail("authenticate() against an unreachable platform DB unexpectedly succeeded")

        # Recovery: swap this same store's pool onto a real, reachable
        # target (the read-only role against the real throwaway platform
        # database this module's fixtures already provisioned) and confirm
        # a real credential authenticates -- only possible if none of the
        # `maxconn + 2` failures above left the pool's own bookkeeping
        # permanently exhausted.
        slug = _fresh_slug("rh")
        _register_application(platform, slug)
        writer = _write_store(platform)
        try:
            with writer.unit_of_work() as work:
                writer.add("crd_" + secrets.token_hex(8), slug, "runtime", "s3cret-recovery", work=work)
        finally:
            writer.close()

        store._pool._dsn = platform.api_dsn
        context = store.authenticate("s3cret-recovery")
        assert context.application_id == slug
    finally:
        store.close()


def test_canonical_context_and_application_id_for_degrade_to_none_on_db_error() -> None:
    """Unlike `authenticate`/`assert_active` (authorization gates,
    fail-closed to 503), `canonical_context`/`application_id_for` are
    audit-attribution-only helpers -- a database error must not turn an
    already-authorized request into a raised error here (see
    `credential_store.py`'s own docstring for the reasoning).
    """
    from r2db_api.auth import AuthContext

    store = PostgresCredentialStore(_unreachable_dsn(), pepper=PEPPER)
    try:
        assert store.canonical_context(AuthContext("crd_x", "app_x", "runtime")) is None
        assert store.application_id_for("crd_x") is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 0005 idempotency.
# ---------------------------------------------------------------------------


def test_0005_migration_is_idempotent(platform: types.SimpleNamespace) -> None:
    _run_psql(platform.control_dsn, platform.credential_store_sql, {"api_password": platform.api_password})
    # Re-running left the role/grants/table exactly as before: a fresh
    # write still succeeds and a fresh read-only-role read still works,
    # which is only true if 0005's second run neither dropped anything nor
    # left the schema in a broken half-applied state.
    slug = _fresh_slug("pf")
    _register_application(platform, slug)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add("crd_" + secrets.token_hex(8), slug, "runtime", "s3cret-idempotent", work=work)
    finally:
        writer.close()
    reader = _read_store(platform)
    try:
        reader.authenticate("s3cret-idempotent")
    finally:
        reader.close()


# ---------------------------------------------------------------------------
# 0004's credential-residue deprovisioning guard (review-reported gap).
# ---------------------------------------------------------------------------


def test_0004_refuses_to_deprovision_while_a_credential_remains_and_touches_nothing(
    platform: types.SimpleNamespace,
) -> None:
    """Review-reported regression: before this guard, `0004_deprovision_
    application.sql` would already have dropped the application's database
    and both its login roles by the time `finish_deprovision_application`'s
    registry `DELETE` hit the surviving credential's foreign key and
    failed -- an inconsistent half-torn-down state (database/roles gone,
    registry still claiming the application provisioned, credential still
    valid). This confirms the fixed behaviour: the whole script aborts
    *before* `pg_terminate_backend`/`DROP DATABASE`/`DROP ROLE` ever run --
    the database, both roles, and the registry row are all still
    completely intact afterwards -- and that deleting the blocking
    credential (`python -m r2db_api.ops delete-credential`, the escape
    hatch this guard's own error message points to) lets deprovisioning
    then succeed normally.
    """
    slug = _fresh_slug("dg")
    app = provision_app(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-guard", work=work)
    finally:
        writer.close()

    try:
        with pytest.raises(RuntimeError, match="credential row"):
            deprovision_app(platform, slug)

        # Nothing destructive ran: the database and both roles this
        # `provision_app` call created are all still there.
        admin = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [app.database])
                assert cur.fetchone() is not None, "the application's database was dropped despite the guard"
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [app.runtime_role])
                assert cur.fetchone() is not None, "the application's runtime role was dropped despite the guard"
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [app.developer_role])
                assert cur.fetchone() is not None, "the application's developer role was dropped despite the guard"
        finally:
            admin.close()

        # The registry row is untouched too -- the credential still
        # authenticates normally (proving `applications`/`credentials` were
        # never modified by the aborted attempt).
        reader = _read_store(platform)
        try:
            reader.authenticate("s3cret-guard")
        finally:
            reader.close()

        # The guard's own error message points at this exact remedy -- but
        # the remedy itself is guarded too: a credential that was never
        # revoked cannot be deleted (deleting it would erase the only
        # record that access was ever cut). Revoke first, then delete.
        refused = _run_cli(platform, "delete-credential", credential_id)
        assert refused.returncode != 0, "deleting a live (never-revoked) credential must be refused"
        assert "revoke" in (refused.stderr or "").lower()
        revoked = _run_cli(platform, "revoke-credential", credential_id)
        assert revoked.returncode == 0, revoked.stderr
        deleted = _run_cli(platform, "delete-credential", credential_id)
        assert deleted.returncode == 0, deleted.stderr

        # Deprovisioning now succeeds -- no exception, and this function's
        # own `finally` below must not try to deprovision "dg..." a second
        # time.
        deprovision_app(platform, slug)
        deprovisioned = True
    except BaseException:
        deprovisioned = False
        raise
    finally:
        if not deprovisioned:
            # Best-effort cleanup for a failed assertion path above: clear
            # any remaining credential row and finish deprovisioning so
            # this test does not leak a database/role pair into the
            # cluster even if one of the assertions above raised first.
            with psycopg.connect(platform.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("DELETE FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "credentials")),
                        [slug],
                    )
                conn.commit()
            deprovision_app(platform, slug)


# ---------------------------------------------------------------------------
# add()/set_state()/rotate() error mapping.
# ---------------------------------------------------------------------------


def test_add_unknown_application_is_not_found(platform: types.SimpleNamespace) -> None:
    store = _write_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            with store.unit_of_work() as work:
                store.add("crd_" + secrets.token_hex(8), "no-such-application-" + secrets.token_hex(4), "runtime", "whatever", work=work)
        assert exc.value.code == "NOT_FOUND"
        assert exc.value.status == 404
    finally:
        store.close()


def test_add_duplicate_credential_id_is_conflict(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pg")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    store = _write_store(platform)
    try:
        with store.unit_of_work() as work:
            store.add(credential_id, slug, "runtime", "s3cret-one", work=work)
        with pytest.raises(FoundationError) as exc:
            with store.unit_of_work() as work:
                store.add(credential_id, slug, "runtime", "s3cret-two", work=work)
        assert exc.value.code == "CONFLICT"
        assert exc.value.status == 409
    finally:
        store.close()


def test_add_rejects_role_outside_runtime_or_developer(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ph")
    _register_application(platform, slug)
    store = _write_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            with store.unit_of_work() as work:
                store.add("crd_" + secrets.token_hex(8), slug, "control", "whatever", work=work)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        store.close()


def test_set_state_unknown_credential_is_not_found(platform: types.SimpleNamespace) -> None:
    store = _write_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            with store.unit_of_work() as work:
                store.set_state("crd_does_not_exist_" + secrets.token_hex(4), enabled=False, work=work)
        assert exc.value.code == "NOT_FOUND"
    finally:
        store.close()


def test_rotate_replaces_the_secret_old_secret_rejected_new_secret_succeeds(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pi")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    store = _write_store(platform)
    try:
        with store.unit_of_work() as work:
            store.add(credential_id, slug, "runtime", "s3cret-before-rotate", work=work)
        with store.unit_of_work() as work:
            store.rotate(credential_id, "s3cret-after-rotate", work=work)

        with pytest.raises(FoundationError) as exc:
            store.authenticate("s3cret-before-rotate")
        assert exc.value.code == "AUTH_INVALID"

        context = store.authenticate("s3cret-after-rotate")
        assert context.credential_id == credential_id
    finally:
        store.close()


# ---------------------------------------------------------------------------
# `python -m r2db_api.ops` -- subprocess, real CLI invocation.
# ---------------------------------------------------------------------------


def _cli_env(platform: types.SimpleNamespace, **overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["R2DB_CONTROL_DSN"] = platform.control_dsn
    env["R2DB_CREDENTIAL_PEPPER"] = PEPPER
    env["R2DB_PLATFORM_SCHEMA"] = platform.schema
    env.update(overrides)
    return env


def _run_cli(platform: types.SimpleNamespace, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", *args],
        capture_output=True,
        text=True,
        env=_cli_env(platform),
    )


def _parse_issued(stdout: str) -> tuple[str, str]:
    credential_id = None
    secret = None
    for line in stdout.splitlines():
        if line.startswith("credential_id: "):
            credential_id = line[len("credential_id: "):].strip()
        elif line.startswith("secret: "):
            secret = line[len("secret: "):].strip()
    assert credential_id and secret, f"could not parse issued credential from CLI output:\n{stdout}"
    return credential_id, secret


def test_cli_issue_credential_then_authenticate_succeeds(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ca")
    _register_application(platform, slug)
    result = _run_cli(platform, "issue-credential", slug, "runtime")
    assert result.returncode == 0, result.stderr
    credential_id, secret = _parse_issued(result.stdout)

    reader = _read_store(platform)
    try:
        context = reader.authenticate(secret)
        assert context.credential_id == credential_id
        assert context.application_id == slug
        assert context.role == "runtime"
    finally:
        reader.close()


def test_cli_rotate_credential_old_secret_rejected_new_secret_succeeds(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cb")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "developer")
    assert issued.returncode == 0, issued.stderr
    credential_id, old_secret = _parse_issued(issued.stdout)

    rotated = _run_cli(platform, "rotate-credential", credential_id)
    assert rotated.returncode == 0, rotated.stderr
    rotated_id, new_secret = _parse_issued(rotated.stdout)
    assert rotated_id == credential_id
    assert new_secret != old_secret

    reader = _read_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            reader.authenticate(old_secret)
        assert exc.value.code == "AUTH_INVALID"
        context = reader.authenticate(new_secret)
        assert context.credential_id == credential_id
    finally:
        reader.close()


def test_cli_revoke_credential_produces_auth_revoked(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cc")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, secret = _parse_issued(issued.stdout)

    revoked = _run_cli(platform, "revoke-credential", credential_id)
    assert revoked.returncode == 0, revoked.stderr

    reader = _read_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            reader.authenticate(secret)
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        reader.close()


def test_cli_disable_and_enable_credential(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cd")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, secret = _parse_issued(issued.stdout)

    disabled = _run_cli(platform, "disable-credential", credential_id)
    assert disabled.returncode == 0, disabled.stderr

    reader = _read_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            reader.authenticate(secret)
        assert exc.value.code == "AUTH_INVALID"
    finally:
        reader.close()

    enabled = _run_cli(platform, "enable-credential", credential_id)
    assert enabled.returncode == 0, enabled.stderr

    reader = _read_store(platform)
    try:
        reader.authenticate(secret)
    finally:
        reader.close()


def test_cli_disable_and_enable_app(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ce")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    _credential_id, secret = _parse_issued(issued.stdout)

    disabled = _run_cli(platform, "disable-app", slug)
    assert disabled.returncode == 0, disabled.stderr

    reader = _read_store(platform)
    try:
        with pytest.raises(FoundationError) as exc:
            reader.authenticate(secret)
        assert exc.value.code == "APPLICATION_DISABLED"
    finally:
        reader.close()

    enabled = _run_cli(platform, "enable-app", slug)
    assert enabled.returncode == 0, enabled.stderr
    reader = _read_store(platform)
    try:
        reader.authenticate(secret)
    finally:
        reader.close()


def test_cli_disable_app_unknown_slug_fails_loudly(platform: types.SimpleNamespace) -> None:
    result = _run_cli(platform, "disable-app", "no-such-app-" + secrets.token_hex(4))
    assert result.returncode != 0


def test_cli_list_credentials_never_prints_verifier_or_secret(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cf")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, secret = _parse_issued(issued.stdout)

    listed = _run_cli(platform, "list-credentials")
    assert listed.returncode == 0, listed.stderr
    assert credential_id in listed.stdout
    assert secret not in listed.stdout
    # The verifier is a 64-hex-char HMAC-SHA256 digest -- computing it
    # independently and confirming it is absent from the listing is a
    # stronger check than merely "the secret string itself is absent"
    # (`list-credentials` could not print the secret even if it wanted to,
    # since it never selects that column at all -- see `verifier` below).
    reader = _read_store(platform)
    try:
        verifier = reader.verifier(secret)
    finally:
        reader.close()
    assert verifier not in listed.stdout


def test_cli_list_apps_shows_registered_application(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cg")
    _register_application(platform, slug)
    result = _run_cli(platform, "list-apps")
    assert result.returncode == 0, result.stderr
    assert slug in result.stdout


def test_cli_missing_control_dsn_fails_loudly() -> None:
    env = dict(os.environ)
    env.pop("R2DB_CONTROL_DSN", None)
    env["PYTHONPATH"] = str(SRC_DIR)
    env["R2DB_CREDENTIAL_PEPPER"] = PEPPER
    result = subprocess.run([sys.executable, "-m", "r2db_api.ops", "list-apps"], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "R2DB_CONTROL_DSN" in result.stderr


def test_cli_help_mentions_ccr14_provisional_status() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    assert result.returncode == 0
    assert "CCR-14" in result.stdout


# ---------------------------------------------------------------------------
# `r2db_api.main` composition root.
# ---------------------------------------------------------------------------


def provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    """Real per-application provisioning (0003), identical in spirit to
    `test_postgres.py::provision_app` -- needed only for the composition-
    root tests below, which build a real `PostgresCell` and must therefore
    have a real, connectable database/role pair.
    """
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


@pytest.fixture(scope="module")
def provisioned_app(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "mainroot")
    try:
        yield app
    finally:
        # Tests in this module issue credentials against `app.slug`
        # (`0005`'s `credentials.application_slug` is `ON DELETE RESTRICT`,
        # by design -- see `0005_credential_store.sql`'s header, and this
        # is real, observed behaviour: `0004_deprovision_application.sql`
        # genuinely fails with a foreign-key violation here if any
        # `credentials` row still references this slug). Clearing those
        # rows first is this fixture's teardown responsibility, not a
        # workaround for a bug -- an operator deprovisioning a real
        # application would need to do the equivalent (or accept that
        # deprovisioning is blocked while credentials still reference it).
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "credentials")),
                    [app.slug],
                )
            conn.commit()
        deprovision_app(platform, "mainroot")


def _main_env(platform: types.SimpleNamespace, app: types.SimpleNamespace) -> dict[str, str]:
    return {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app.slug,
        f"R2DB_APP_{app.slug.upper()}_RUNTIME_DSN": app.runtime_dsn,
        f"R2DB_APP_{app.slug.upper()}_DEVELOPER_DSN": app.developer_dsn,
    }


@pytest.fixture(scope="module")
def main_module(platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace) -> Iterator[types.ModuleType]:
    """`r2db_api.main` has `app = build_app()` at *module* level (P2-D5:
    the literal uvicorn/systemd entry point) -- so a bare `import r2db_api.
    main` unconditionally reads real `os.environ` the instant it first
    runs, in *any* test, regardless of which test triggers it first. This
    fixture sets a valid, real environment (this module's own provisioned
    application) via `pytest.MonkeyPatch`, module-scoped, before that first
    import happens, so `build_app()`'s own top-level call succeeds instead
    of failing on this pytest process' unrelated ambient environment.
    Every test below that needs the *module object* (to call `.build_app`
    with its own, separate, deliberately-different `env=` argument) depends
    on this fixture rather than importing the module directly.
    """
    mp = pytest.MonkeyPatch()
    for key, value in _main_env(platform, provisioned_app).items():
        mp.setenv(key, value)
    try:
        import importlib
        import sys

        if "r2db_api.main" in sys.modules:
            module = importlib.reload(sys.modules["r2db_api.main"])
        else:
            import r2db_api.main as module
        yield module
    finally:
        mp.undo()


def test_build_app_serves_capabilities_over_real_http_and_shuts_down_cleanly(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    writer = _write_store(platform)
    try:
        credential_id = "crd_" + secrets.token_hex(8)
        with writer.unit_of_work() as work:
            writer.add(credential_id, provisioned_app.slug, "runtime", "s3cret-main-e2e", work=work)
    finally:
        writer.close()

    asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
    # `TestClient` as a context manager drives the ASGI lifespan protocol
    # (startup/shutdown), which is what actually exercises `build_app`'s
    # `_lifespan` hook (`default_pool_manager.dispose_all()` +
    # `credentials.close()`) -- a plain request without the `with` block
    # would never trigger shutdown at all.
    with TestClient(asgi_app) as client:
        response = client.get("/v1/capabilities", headers={"authorization": "Bearer s3cret-main-e2e"})
        assert response.status_code == 200
        document = response.json()
        assert document["application_scope"] == provisioned_app.slug
        assert document["role"] == "runtime"
        assert document["authorization_propagation_bound_ms"] == 0

        unauthenticated = client.get("/v1/capabilities")
        assert unauthenticated.status_code == 401


def test_build_app_missing_required_env_var_raises(main_module: types.ModuleType) -> None:
    with pytest.raises(RuntimeError, match="R2DB_CREDENTIAL_PEPPER"):
        main_module.build_app(env={})


def test_build_app_missing_serve_apps_raises(main_module: types.ModuleType) -> None:
    with pytest.raises(RuntimeError, match="R2DB_SERVE_APPS"):
        main_module.build_app(env={"R2DB_CREDENTIAL_PEPPER": PEPPER, "R2DB_PLATFORM_DSN": "irrelevant"})


def test_build_app_missing_per_app_dsn_raises(platform: types.SimpleNamespace, main_module: types.ModuleType) -> None:
    slug = _fresh_slug("me")
    _register_application(platform, slug)
    env = {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": slug,
    }
    with pytest.raises(RuntimeError, match=f"R2DB_APP_{slug.upper()}_RUNTIME_DSN"):
        main_module.build_app(env=env)


def test_build_app_unregistered_slug_raises(platform: types.SimpleNamespace, main_module: types.ModuleType) -> None:
    slug = "no-such-app-" + secrets.token_hex(4)
    env = {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": slug,
        f"R2DB_APP_{slug.upper()}_RUNTIME_DSN": "irrelevant",
        f"R2DB_APP_{slug.upper()}_DEVELOPER_DSN": "irrelevant",
    }
    with pytest.raises(RuntimeError, match="not registered"):
        main_module.build_app(env=env)


def test_build_app_disabled_slug_raises(platform: types.SimpleNamespace, main_module: types.ModuleType) -> None:
    slug = _fresh_slug("mf")
    _register_application(platform, slug, enabled=False)
    env = {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": slug,
        f"R2DB_APP_{slug.upper()}_RUNTIME_DSN": "irrelevant",
        f"R2DB_APP_{slug.upper()}_DEVELOPER_DSN": "irrelevant",
    }
    with pytest.raises(RuntimeError, match="disabled"):
        main_module.build_app(env=env)


def test_build_app_registered_only_slug_raises(platform: types.SimpleNamespace, main_module: types.ModuleType) -> None:
    """R-4 (CCR-14 WP-2): a slug that is registered but not yet provisioned
    (0006's two-state `applications` -- `database_name IS NULL`) must fail
    startup exactly like an unregistered or disabled slug does, not be
    silently served against DSNs that reference a database/roles nobody
    ever actually provisioned."""
    slug = _fresh_slug("mg")
    _register_application_only(platform, slug)
    env = {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": slug,
        f"R2DB_APP_{slug.upper()}_RUNTIME_DSN": "irrelevant",
        f"R2DB_APP_{slug.upper()}_DEVELOPER_DSN": "irrelevant",
    }
    with pytest.raises(RuntimeError, match="not yet provisioned"):
        main_module.build_app(env=env)


def test_import_r2db_api_main_module_succeeds_with_valid_environment(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace
) -> None:
    """Proves the literal `r2db_api.main:app` uvicorn/systemd entry point
    (P2-D5) works -- a real `import`, in a fresh subprocess (so this does
    not pollute the current pytest process' `sys.modules`/`default_pool_
    manager` global state with a second, module-level `app` this test file
    does not otherwise need).
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env.update(_main_env(platform, provisioned_app))
    script = "import r2db_api.main as m; assert m.app is not None; print('IMPORT_OK')"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
