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

import json
import os
import secrets
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.testclient import TestClient

from r2db_api.auth import compose_bearer_locator, split_bearer_locator
from r2db_api.credential_store import PostgresCredentialStore
from r2db_api.errors import FoundationError
from r2db_api.structured import delete_credential_confirmation_phrase

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
PEPPER = "synthetic-test-pepper-credential-persistence-0000"
# WP-2 (design D-1/D-3 (2'), 監督裁定 11/27): a shared, real slot
# directory (mode 0700 by `mkdtemp`'s own default) for the handful of
# tests in this file that build their OWN inline `env` dict (rather than
# through `_main_env`, below) and expect `build_app()` to fail LATER, at
# a check downstream of the slot-directory validation -- not explicitly
# torn down, see `_main_env`'s own identical convention.
_INLINE_ENV_SLOT_DIR = tempfile.mkdtemp(prefix="r2db-test-slots-inline-")


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
    # Q4 phase WP-1 rework (D-2(h) point 1): migration `0008` now takes
    # `-v api_role=... -v controlplane_role=...` -- this fixture never
    # otherwise needed a `controlplane_role` local (this file's own tests
    # never authenticate AS that role), so it is introduced here solely to
    # feed the migration invocation below.
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-9): the
    # `auditreader` role's password -- unused directly by this file's own
    # tests (none of them read `application_audit`/`control_audit` through
    # that role), but `0007_application_audit.sql` still requires the
    # `-v auditreader_password=...` variable to run at all.
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_cred_migrations")
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        "0005_credential_store.sql",
        "0006_control_plane_http.sql",
        "0007_application_audit.sql",
        # R-56 WP-1: role-level `statement_timeout` on
        # `r2dbsvc_auditreader` -- placed right after 0007 (the
        # migration that creates that role); no dependency on
        # 0008/0012/0013.
        "0014_auditreader_statement_timeout.sql",
        # Phase 10 WP-4g (supervisor ruling 2026-09-09): `r2db_api.main.
        # build_app`/`r2db_api.control_main.build_control_app` now run
        # F-16 (this process' own role CONNECTION LIMIT) unconditionally
        # at startup, on every real launch this file's own `platform`
        # fixture drives (`main_module`, below, and every file that
        # imports this fixture) -- this migration must run BEFORE the
        # api/controlplane roles' own pre-WP-4f `CONNECTION LIMIT` (10)
        # would otherwise sit below F-16's own real pool-composition
        # floor and fail every test that touches `main_module` at
        # fixture setup, not just the ones actually about F-16.
        "0013_role_connection_limits.sql",
        "0008_platform_declarations_and_writer_timeouts.sql",
        # Phase 10 WP-6a (design D-5(ii)): widens `platform_declarations_
        # key_check` to admit `process_ceilings` -- required so this
        # fixture can seed that row below (F-15 is unconditional, like
        # F-3 for `surfaces`, since WP-6a).
        "0012_process_ceilings.sql",
        # WP-2 (design D-3 (1), 監督裁定15): `r2db_api.main.build_app` now
        # always wires the PostgreSQL-backed `requests_per_minute` rate
        # row (`R2DB_SLOT_DIR`/`R2DB_WORKERS` are required env vars as of
        # this WP) -- every real request through `main_module`'s own app
        # needs this table/function to exist.
        "0015_credential_request_rate.sql",
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
        # Phase 4: `r2db_api.main.build_app`/`r2db_api.control_main.
        # build_control_app` now unconditionally construct a Postgres-
        # backed durable application/control audit sink against this same
        # platform database -- every fixture that exercises either
        # composition root against a real server needs `application_audit`
        # (and the `auditreader` role) to exist, exactly as it already
        # needed `0006`'s `control_audit`/`r2dbsvc_controlplane`.
        _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
        _run_psql(control_dsn, rewritten["0014_auditreader_statement_timeout.sql"])
        _run_psql(control_dsn, rewritten["0013_role_connection_limits.sql"])
        # Q4 phase WP-1 (design D-1/D-2): platform single-shot migration --
        # ALTER ROLE writer-timeout role settings + the platform_
        # declarations table (seeds only audit_coalescing_window_ms; see
        # this file's own `_DEFAULT_SURFACES_VALUE`/`_set_surfaces_row`
        # below for the `surfaces` row every fixture in this file needs).
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
        application_audit_sql=rewritten["0007_application_audit.sql"],
        api_password=api_password,
        controlplane_dsn=controlplane_dsn,
        controlplane_password=controlplane_password,
        auditreader_password=auditreader_password,
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
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-persist", work=work)
    finally:
        writer.close()

    # A brand-new store instance -- its own fresh pool, no shared Python
    # state with `writer` above -- stands in for "a restarted process" per
    # design §4. Using the *read-only* role here also proves P2-D3's grants
    # (`SELECT` only) are sufficient for the entire authenticate path.
    reader = _read_store(platform)
    try:
        context = reader.authenticate(compose_bearer_locator(credential_id, "s3cret-persist"))
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
            context = reader.authenticate(compose_bearer_locator(credential_id, "s3cret-canonical"))
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

        context = long_lived_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-revoke"))

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
            long_lived_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-revoke"))
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
        context = long_lived_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-appdisable"))
        _set_application_enabled(platform, slug, False)

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-appdisable"))
        assert exc.value.code == "APPLICATION_DISABLED"
        assert exc.value.status == 403

        with pytest.raises(FoundationError) as exc:
            long_lived_reader.assert_active(context)
        assert exc.value.code == "APPLICATION_DISABLED"

        _set_application_enabled(platform, slug, True)
        # No cache anywhere -- re-enabling is visible immediately too.
        long_lived_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-appdisable"))
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
            post_restart_reader.authenticate(compose_bearer_locator(credential_id, "s3cret-restart-disable"))
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
            # A well-formed locator (any shape survives `split_bearer_
            # locator` -- it never reaches the unreachable DB anyway) so
            # this test actually exercises the DB-unreachable path, not an
            # earlier malformed-locator short-circuit.
            store.authenticate(compose_bearer_locator("crd_unreachable", "any-secret-at-all"))
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
                # Well-formed locator -- must actually reach the pool (an
                # unparseable one would short-circuit before ever touching
                # it, defeating this test's own pool-exhaustion premise).
                future = executor.submit(store.authenticate, compose_bearer_locator("crd_irrelevant", "irrelevant-secret"))
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
        credential_id = "crd_" + secrets.token_hex(8)
        writer = _write_store(platform)
        try:
            with writer.unit_of_work() as work:
                writer.add(credential_id, slug, "runtime", "s3cret-recovery", work=work)
        finally:
            writer.close()

        store._pool._dsn = platform.api_dsn
        context = store.authenticate(compose_bearer_locator(credential_id, "s3cret-recovery"))
        assert context.application_id == slug
    finally:
        store.close()


def test_platform_pool_sized_to_thread_limit_avoids_premature_503(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 10 WP-4e (supervisor ruling 2026-09-09), updated for WP-2
    (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5), 監督裁定16):
    peer-local real-PostgreSQL pin for the platform pool sizing fix
    `r2db_api.main.build_app` and this adapter's own conformance
    composition now apply -- the SAME F-1 shape `r2db_api.limits.role_
    pool_size` already fixed for the per-application role pools
    (`test_threadpool_offload.py::
    test_role_pool_sized_to_thread_limit_avoids_premature_503`, which uses
    a FAKE `_RolePool._connect` -- no live PostgreSQL needed). This test
    exercises the same property one layer up, against a REAL platform
    database: with `PostgresCredentialStore`'s own pool sized via `role_
    pool_size(thread_limit)` (the exact function `build_app` now calls --
    the real per-process simultaneous-borrow ceiling is `thread_limit`,
    never the deployment-wide admission bound `concurrency`, as of this
    WP), `thread_limit` genuinely concurrent `authenticate()` calls are
    all served (0 x `AUTH_STATE_UNAVAILABLE`), even though each call holds
    its checked-out connection for longer than the pool's own `acquire_
    timeout`.

    `_execute` (this module's own single execution choke point) is
    monkeypatched to sleep for `hold_s` seconds AFTER the real query runs
    but BEFORE returning -- the sleep happens while `_fetch_or_503`'s own
    `with self._pool.connection()` block still holds the checked-out real
    connection, so `thread_limit` threads genuinely contend for the
    pool's `maxconn` slots against a live PostgreSQL server, not a
    simulation.

    Mutation: hardcoding `PostgresCredentialStore`'s own `pool_size=` back
    to a fixed `2` (or `4`) regardless of the declared `thread_limit=6`
    this test configures turns this red -- the 3rd+ concurrent
    `authenticate()` call then waits past `acquire_timeout` for a
    connection none of the first two callers have released yet (still
    sleeping), and fails closed with `AUTH_STATE_UNAVAILABLE` instead of
    succeeding.
    """
    import concurrent.futures
    import time

    from r2db_api import credential_store as credential_store_module
    from r2db_api.limits import ResourceLimits, role_pool_size

    thread_limit = 6
    concurrency = thread_limit
    hold_s = 0.6
    resource_limits = ResourceLimits(concurrency=concurrency, requests_per_minute=100_000)
    platform_pool_size = role_pool_size(thread_limit)

    slug = _fresh_slug("pp")
    _register_application(platform, slug)
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-pool-size", work=work)
    finally:
        writer.close()

    store = PostgresCredentialStore(
        platform.api_dsn, pepper=PEPPER, schema=platform.schema,
        pool_size=platform_pool_size, acquire_timeout=0.3,
    )

    original_execute = credential_store_module._execute

    def _slow_execute(cursor, statement, params=()):
        original_execute(cursor, statement, params)
        time.sleep(hold_s)

    monkeypatch.setattr(credential_store_module, "_execute", _slow_execute)

    try:
        secret = compose_bearer_locator(credential_id, "s3cret-pool-size")
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(store.authenticate, secret) for _ in range(concurrency)]
            results = []
            denials = []
            for future in futures:
                try:
                    results.append(future.result(timeout=10))
                except FoundationError as exc:
                    denials.append(exc.code)
        assert not denials, f"expected 0 AUTH_STATE_UNAVAILABLE denials at in-flight == declared concurrency, got: {denials}"
        assert len(results) == concurrency
        assert all(context.application_id == slug for context in results)
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
    credential_id = "crd_" + secrets.token_hex(8)
    writer = _write_store(platform)
    try:
        with writer.unit_of_work() as work:
            writer.add(credential_id, slug, "runtime", "s3cret-idempotent", work=work)
    finally:
        writer.close()
    reader = _read_store(platform)
    try:
        reader.authenticate(compose_bearer_locator(credential_id, "s3cret-idempotent"))
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
    *before* the live-connection pre-check, the temporary self-grant,
    `ALLOW_CONNECTIONS`, `pg_terminate_backend`/`DROP DATABASE`/`DROP
    ROLE` -- anything at all -- ever run (design `docs/design/
    DEPROVISION_FORCED_DROP_V0_1.md` v1.0 D-2R adds the first three
    stages ahead of the ones this docstring already named) --
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
            reader.authenticate(compose_bearer_locator(credential_id, "s3cret-guard"))
        finally:
            reader.close()

        # The guard's own error message points at this exact remedy -- but
        # the remedy itself is guarded too: a credential that was never
        # revoked cannot be deleted (deleting it would erase the only
        # record that access was ever cut). Revoke first, then delete.
        # Q-1 WP-4: `delete-credential` is now gated (design R-4) -- passing
        # the correct `--confirm` here so this test still exercises the
        # underlying "must already be revoked" precondition it is actually
        # about, not merely the confirmation gate that now runs before it.
        confirm = delete_credential_confirmation_phrase(credential_id)
        refused = _run_cli(platform, "delete-credential", credential_id, "--confirm", confirm)
        # nit N-1 (Opus review): pinned to the exact precondition failure
        # (`credential_store.PostgresCredentialStore.delete`'s own
        # `VALIDATION_FAILED`, routed through `main()`'s ordinary
        # `FoundationError` handler -- exit 1, not the R-4 gate's exit 2),
        # not merely "some non-zero exit containing the word revoke" --
        # this is what proves the confirmation gate above already passed
        # and this refusal is the underlying "not yet revoked" precondition
        # the confirm-phrase construction ensured we would actually reach.
        assert refused.returncode == 1, "deleting a live (never-revoked) credential must be refused by the precondition, not the gate"
        assert "VALIDATION_FAILED" in refused.stderr
        assert "Credential is not revoked" in refused.stderr
        revoked = _run_cli(platform, "revoke-credential", credential_id)
        assert revoked.returncode == 0, revoked.stderr
        deleted = _run_cli(platform, "delete-credential", credential_id, "--confirm", confirm)
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
            store.authenticate(compose_bearer_locator(credential_id, "s3cret-before-rotate"))
        assert exc.value.code == "AUTH_INVALID"

        context = store.authenticate(compose_bearer_locator(credential_id, "s3cret-after-rotate"))
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


def test_cli_revoke_credential_remains_ungated_and_has_no_confirm_flag(platform: types.SimpleNamespace) -> None:
    """Q1-D4/WP-0 MA-1: `revoke-credential` (application credentials) is
    deliberately excluded from the Q-1 R-4 gate -- unlike `reset`/`delete-
    credential`, it does not even accept a `--confirm` flag at all, and
    executes exactly as it always has, with no confirmation of any kind."""
    slug = _fresh_slug("cl")
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

    rejected_flag = _run_cli(platform, "revoke-credential", credential_id, "--confirm", "anything")
    assert rejected_flag.returncode != 0, "revoke-credential must not accept a --confirm flag at all (it was never given one)"


# ---------------------------------------------------------------------------
# Q-1 WP-4 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4):
# `delete-credential`'s own declare-and-echo gate.
# ---------------------------------------------------------------------------

_DECLARATION_DETAILS_KEYS = {"required_confirmation", "consequence", "reversible_alternative", "recovery"}


def test_cli_delete_credential_without_confirm_declares_and_touches_nothing(platform: types.SimpleNamespace) -> None:
    """An unconfirmed `delete-credential` executes nothing at all -- the row
    is not removed, even though it is already revoked and would otherwise be
    eligible for deletion (the confirmation gate runs strictly before that
    precondition is even reached, see `ops._require_cli_confirmation`)."""
    slug = _fresh_slug("ch")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, _secret = _parse_issued(issued.stdout)
    revoked = _run_cli(platform, "revoke-credential", credential_id)
    assert revoked.returncode == 0, revoked.stderr

    refused = _run_cli(platform, "delete-credential", credential_id)
    assert refused.returncode == 2, refused.stderr
    assert refused.stdout == ""
    declaration = json.loads(refused.stderr.strip())
    assert declaration["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    details = declaration["details"]
    assert set(details) == _DECLARATION_DETAILS_KEYS, "all four contract-required declaration keys must be present"
    # Opus review MA-2: asserted against a literal expected value, not the
    # production function's own output -- self-comparing against `delete_
    # credential_confirmation_phrase(credential_id)` here would make this
    # assertion pass even if that function were mutated to no longer
    # incorporate `credential_id` at all (its caller and this test would
    # simply agree on the same wrong answer). See `test_cli_delete_
    # credential_confirmation_phrase_literal_and_cross_target` below for the
    # dedicated mutation-sensitive coverage this shorthand doesn't replace.
    assert details["required_confirmation"] == f"DELETE_CREDENTIAL {credential_id}"
    assert isinstance(details["consequence"], str) and details["consequence"], "consequence must be a non-empty string"
    assert isinstance(details["reversible_alternative"], str) and details["reversible_alternative"]
    assert details["recovery"] is None, "delete-credential is genuinely irreversible -- recovery is truthfully null"

    listed = _run_cli(platform, "list-credentials")
    assert listed.returncode == 0, listed.stderr
    assert credential_id in listed.stdout, "an unconfirmed delete-credential must not have removed the row"


def test_cli_delete_credential_wrong_confirm_phrase_declares_and_touches_nothing(platform: types.SimpleNamespace) -> None:
    """Contract `valid_confirmation`'s exact-match rule, adversarially: a
    suffix, a prefix, a case fold, and an empty string are all refused --
    never a prefix/suffix/truthy/presence check."""
    slug = _fresh_slug("ci")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, _secret = _parse_issued(issued.stdout)
    revoked = _run_cli(platform, "revoke-credential", credential_id)
    assert revoked.returncode == 0, revoked.stderr

    # Literal, not `delete_credential_confirmation_phrase(credential_id)`
    # (Opus review MA-2) -- see the identical note above.
    phrase = f"DELETE_CREDENTIAL {credential_id}"
    for wrong in (phrase + "X", phrase[:-1], phrase.lower(), ""):
        refused = _run_cli(platform, "delete-credential", credential_id, "--confirm", wrong)
        assert refused.returncode == 2, refused.stderr
        declaration = json.loads(refused.stderr.strip())
        assert declaration["details"]["required_confirmation"] == phrase

    listed = _run_cli(platform, "list-credentials")
    assert credential_id in listed.stdout, "no wrong-phrase attempt above may have removed the row"


def test_cli_delete_credential_confirmation_phrase_is_deterministic(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("cj")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, _secret = _parse_issued(issued.stdout)

    first = _run_cli(platform, "delete-credential", credential_id)
    second = _run_cli(platform, "delete-credential", credential_id)
    assert first.returncode == second.returncode == 2
    phrase_1 = json.loads(first.stderr.strip())["details"]["required_confirmation"]
    phrase_2 = json.loads(second.stderr.strip())["details"]["required_confirmation"]
    # Literal expected value (Opus review MA-2) -- see the note above.
    assert phrase_1 == phrase_2 == f"DELETE_CREDENTIAL {credential_id}"


def _run_cli_no_env(*args: str) -> subprocess.CompletedProcess:
    """Opus review MA-3: runs the CLI with NONE of this codebase's own
    `R2DB_*` environment variables set at all -- not `R2DB_CONTROL_DSN`,
    not `R2DB_CREDENTIAL_PEPPER` -- to prove the confirmation gate really
    does run before any environment variable is even required, let alone
    before a database connection is opened. `PYTHONPATH` is kept (needed
    only so the subprocess can import `r2db_api` at all)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("R2DB_")}
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run([sys.executable, "-m", "r2db_api.ops", *args], capture_output=True, text=True, env=env)


def test_cli_delete_credential_without_confirm_refuses_before_any_env_var_is_required() -> None:
    """Opus review MA-3: with no `R2DB_*` environment variable set at all,
    an unconfirmed `delete-credential` (given a format-valid, if made-up,
    credential_id -- MA-1's own format check needs no environment either)
    still produces the ordinary gate declaration -- not `_require_env`'s
    "R2DB_CONTROL_DSN is required" -- proving the gate runs before
    `_store()` even looks at the environment, let alone connects to a
    database. No `platform` fixture needed here at all: this process never
    reaches anything that would need one."""
    result = _run_cli_no_env("delete-credential", "crd_" + "a" * 16)
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "R2DB_CONTROL_DSN" not in (result.stderr or ""), "must not have reached the env-var check at all"
    declaration = json.loads(result.stderr.strip())
    assert declaration["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert declaration["details"]["required_confirmation"] == "DELETE_CREDENTIAL crd_" + "a" * 16


@pytest.mark.parametrize(
    "bad_credential_id",
    [
        "not-a-credential-id",
        "crd_tooshort",
        "crd_" + "g" * 16,  # not hex
        "crd_" + "A" * 16,  # uppercase, not lowercase hex
        "ctl_" + "a" * 16,  # a control-credential id shape, not application
        "crd_" + "a" * 17,  # one hex digit too many
        "",
    ],
)
def test_cli_delete_credential_rejects_malformed_credential_id_before_any_env_var_is_required(bad_credential_id: str) -> None:
    """Opus review MA-1: `cmd_delete_credential` validates `credential_id`
    against `^crd_[0-9a-f]{16}$` -- the exact shape both application-
    credential minters (`ops._new_credential_id`/`control_plane._new_
    credential_id`) produce -- strictly before the confirmation gate and
    with no environment variable required either, so a malformed id is
    `VALIDATION_FAILED` (exit 1, `main()`'s ordinary error path), never
    reaching `delete_credential_confirmation_phrase` at all (which would
    otherwise reflect this unvalidated string straight into the declared
    `required_confirmation`, contract `phrase_construction` rule (c))."""
    result = _run_cli_no_env("delete-credential", bad_credential_id)
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert "VALIDATION_FAILED" in result.stderr
    assert "credential_id must match" in result.stderr
    # Not the gate's shape at all -- no JSON, no DESTRUCTIVE_CONFIRMATION_
    # REQUIRED code, and critically, the rejected string itself is never
    # echoed back (rule (c): no unvalidated-input reflection).
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stderr.strip())
    if bad_credential_id:
        assert bad_credential_id not in result.stderr, "the rejected string itself must never be echoed back"


def test_cli_delete_credential_echo_of_declared_phrase_succeeds(platform: types.SimpleNamespace) -> None:
    """The probe->echo protocol end to end: an operator who does not
    already know the phrase gets it from a first, refused invocation's own
    stderr declaration, and echoing it back verbatim on a second invocation
    deletes the row exactly as `delete-credential` always has."""
    slug = _fresh_slug("ck")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, _secret = _parse_issued(issued.stdout)
    revoked = _run_cli(platform, "revoke-credential", credential_id)
    assert revoked.returncode == 0, revoked.stderr

    probe = _run_cli(platform, "delete-credential", credential_id)
    assert probe.returncode == 2
    phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]

    echoed = _run_cli(platform, "delete-credential", credential_id, "--confirm", phrase)
    assert echoed.returncode == 0, echoed.stderr

    listed = _run_cli(platform, "list-credentials")
    assert credential_id not in listed.stdout, "the echoed, confirmed delete-credential must have removed the row"


def test_cli_delete_credential_cross_target_phrase_is_rejected(platform: types.SimpleNamespace) -> None:
    """Opus review MA-2: credential A's own declared phrase must not
    validate a delete of credential B -- the phrase's own `credential_id`
    component is load-bearing, not decorative. Also exercises MA-2's own
    mutation-sensitivity requirement: a mutant `delete_credential_
    confirmation_phrase` that dropped `credential_id` from its output
    entirely (returning a fixed string regardless of argument) would make
    every credential's declared phrase identical, and this test would then
    catch that by A's phrase being wrongly accepted for B."""
    slug = _fresh_slug("cm")
    _register_application(platform, slug)

    issued_a = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued_a.returncode == 0, issued_a.stderr
    credential_a, _secret_a = _parse_issued(issued_a.stdout)
    revoked_a = _run_cli(platform, "revoke-credential", credential_a)
    assert revoked_a.returncode == 0, revoked_a.stderr

    issued_b = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued_b.returncode == 0, issued_b.stderr
    credential_b, _secret_b = _parse_issued(issued_b.stdout)
    revoked_b = _run_cli(platform, "revoke-credential", credential_b)
    assert revoked_b.returncode == 0, revoked_b.stderr

    probe_a = _run_cli(platform, "delete-credential", credential_a)
    assert probe_a.returncode == 2
    phrase_a = json.loads(probe_a.stderr.strip())["details"]["required_confirmation"]
    assert phrase_a == f"DELETE_CREDENTIAL {credential_a}"
    assert phrase_a != f"DELETE_CREDENTIAL {credential_b}"

    cross = _run_cli(platform, "delete-credential", credential_b, "--confirm", phrase_a)
    assert cross.returncode == 2, "credential A's own declared phrase must never validate a delete of credential B"
    declaration = json.loads(cross.stderr.strip())
    assert declaration["details"]["required_confirmation"] == f"DELETE_CREDENTIAL {credential_b}"

    listed = _run_cli(platform, "list-credentials")
    assert credential_a in listed.stdout, "the rejected cross-target attempt must not have deleted A either"
    assert credential_b in listed.stdout, "the rejected cross-target attempt must not have deleted B"


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
    # `secret` is the composed `<credential_id>.<secret_part>` bearer the
    # CLI issued -- the actual stored verifier is computed over the
    # secret HALF only (see `PostgresCredentialStore.authenticate`), so
    # split it first rather than hashing the whole locator.
    _issued_credential_id, secret_part = split_bearer_locator(secret)
    reader = _read_store(platform)
    try:
        verifier = reader.verifier(secret_part)
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


def test_cli_help_declares_ritual_and_break_glass() -> None:
    """CCR-14 WP-6 (design R-10, D-4): the CLI's `--help` no longer describes
    itself as a stand-in pending CCR-14's disposition -- CCR-14 is resolved
    (spec/CCR_DISPOSITION.md) and the canonical in-band surface (`/control/v1`)
    exists. This asserts the current re-definition text directly: the CLI
    names itself as the bootstrap/reset *ritual* (the only control-credential
    issuance path) plus operator *break-glass* recovery, still under the
    "CCR-14" heading (`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-10) --
    not merely "some string called CCR-14 is present somewhere".
    """
    result = subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    assert result.returncode == 0
    assert "CCR-14" in result.stdout
    assert "ritual" in result.stdout
    assert "break-glass" in result.stdout


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


# Q4 phase WP-1 (design D-2(c)): `surfaces` is now a DB-side declaration
# (`<registry>.platform_declarations`), never an env var -- this is the
# SAME default value `_main_env` used to inject via `R2DB_DATA_BASE_URL`
# before this phase, seeded once by the `platform` fixture (module-scoped,
# shared by every test below) and left WITHOUT a `control` key (matching
# `R2DB_CONTROL_PLANE_STATUS` defaulting `unavailable`, F-6). The one test
# that needs `control_plane_status=enabled`
# (`test_build_app_control_plane_status_enabled_is_declared`) adds it via
# `_set_surfaces_row` and restores this default afterward (`finally`) --
# this row is shared, module-scoped state, unlike the pre-Q4 per-test env
# var it replaces.
_DEFAULT_SURFACES_VALUE = {"data": {"base_url": "https://r2db-main-test.example.invalid/v1"}}


def _set_surfaces_row(platform: types.SimpleNamespace, value: dict) -> None:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps(value)],
            )
        conn.commit()


def _main_env(platform: types.SimpleNamespace, app: types.SimpleNamespace) -> dict[str, str]:
    # WP-2 (design D-1/D-3 (2'), 監督裁定 11/27): `R2DB_WORKERS`/`R2DB_
    # SLOT_DIR` are now required for `build_app()` to start at all --
    # every caller of this helper gets a fresh `mkdtemp` slot directory
    # (mode 0700 by `mkdtemp`'s own default, satisfying `concurrency_
    # slots.check_slot_directory`) and `workers=1`, mirroring a real
    # single-process deployment. Not explicitly torn down -- this test
    # module's own other `tempfile.mkdtemp` call sites (`test_ops_apply_
    # platform_migration.py`/`test_ops_verify_declarations.py`) follow the
    # same "leaked to the OS temp dir" convention.
    slot_dir = tempfile.mkdtemp(prefix="r2db-test-slots-")
    return {
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_DSN": platform.api_dsn,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_SERVE_APPS": app.slug,
        f"R2DB_APP_{app.slug.upper()}_RUNTIME_DSN": app.runtime_dsn,
        f"R2DB_APP_{app.slug.upper()}_DEVELOPER_DSN": app.developer_dsn,
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": slot_dir,
        # Q4 phase WP-1 (design D-2(f)): `R2DB_DATA_BASE_URL`/`R2DB_
        # CONTROL_BASE_URL` are REMOVED -- surfaces now come from the
        # `platform` fixture's own seeded `platform_declarations` row (see
        # `_DEFAULT_SURFACES_VALUE` above), never from this env dict.
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
        response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {compose_bearer_locator(credential_id, 's3cret-main-e2e')}"})
        assert response.status_code == 200
        document = response.json()
        assert document["application_scope"] == provisioned_app.slug
        assert document["role"] == "runtime"
        assert document["authorization_propagation_bound_ms"] == 0

        unauthenticated = client.get("/v1/capabilities")
        assert unauthenticated.status_code == 401


def test_nul_locator_over_real_http_is_401_and_durably_audited_not_503_silent(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """Coordinator F1 (2026-09-04 review): before this fix, a bearer with a
    NUL (U+0000) byte in either locator half reached `psycopg` as a real
    query parameter (`credential_store.py`'s `_fetch_or_503`), which
    refuses a NUL-bearing `text` parameter and mapped that to
    `AUTH_STATE_UNAVAILABLE` (503) -- a code a CLIENT could trigger at
    will, and one that `service._DURABLE_DENIAL_CODES` does not include,
    so the denial was never durably audited at all (SI-14 regression).
    `auth.split_bearer_locator` now rejects a NUL in either half BEFORE
    any lookup, exactly like the other 3 malformed shapes -- this test
    fixes both halves of the regression over REAL HTTP + REAL PostgreSQL:
    (1) the response is `401 AUTH_INVALID`, never `503`; (2) the denial
    reaches the durable `application_audit` sink (`AUTH_INVALID` IS in
    `_DURABLE_DENIAL_CODES`, unlike `AUTH_STATE_UNAVAILABLE`).
    """
    asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
    with TestClient(asgi_app) as client:
        for locator in ("crd_\x00nulid.secret", "crd_nulid.sec\x00ret"):
            response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {locator}"})
            assert response.status_code == 401, f"NUL locator {locator!r} returned {response.status_code}, not 401: {response.text}"
            assert response.json()["code"] == "AUTH_INVALID"

        # Force any coalescing window open for this denial's key closed --
        # `service.flush_audit_buffer`'s own hook, the same one the real
        # periodic background thread calls (`main.py`'s `_audit_flush_loop`)
        # -- so the durable row this denial's FIRST occurrence already
        # wrote synchronously (`_DenialCoalescer.route`'s own "first
        # occurrence writes immediately" rule) is guaranteed visible by the
        # time this test reads `application_audit` below, regardless of
        # real wall-clock timing relative to `denial_coalesce_window_s`.
        asgi_app.app.state.service.flush_audit_buffer(force_expire_denial_windows=True)

    with psycopg.connect(_dsn_with(platform.admin_dsn, user=f"{platform.prefix}_auditreader", password=platform.auditreader_password, dbname=platform.platform_db)) as conn:
        with conn.cursor() as cur:
            table = sql.Identifier(platform.schema, "application_audit").as_string(conn)
            cur.execute(f"SELECT count(*) FROM {table} WHERE reason_code = 'AUTH_INVALID' AND operation = 'authenticate'")
            (count,) = cur.fetchone()
    assert count >= 1, "NUL-locator AUTH_INVALID denial did not reach the durable application_audit sink"


def test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """Phase 10 WP-4g (supervisor ruling 2026-09-09): F-16 is not only an
    `ops verify-declarations` check (WP-4f) -- `r2db_api.main.build_app`
    itself now fails fast on the SAME condition at real startup, scoped to
    exactly the role THIS process' own pool composition uses
    (`platform.api_role`, the `r2dbsvc_api`-class role `main_module`'s own
    `credentials`/`durable_audit` stores both pool connections against).
    Lowering it back below its own real floor (2 stores x pool size 6 =
    12 at the default thread limit 4) -- exactly the pre-`0013_role_connection_limits.sql` state every
    platform was in before Phase 10 WP-4f -- must raise, never silently
    start a process that can hit PostgreSQL's own hard 'too many
    connections for role' refusal under real concurrent traffic. Restores
    the migration-seeded limit (68) in a `finally` so this shared,
    module-scoped `platform` fixture is left healthy for every other test
    in this file."""
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(sql.Identifier(platform.api_role)))
        conn.commit()
    try:
        with pytest.raises(RuntimeError, match="F-16|CONNECTION LIMIT"):
            main_module.build_app(env=_main_env(platform, provisioned_app))
    finally:
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 68").format(sql.Identifier(platform.api_role)))
            conn.commit()
        # Non-空振り: proves the restore above is really what makes
        # `build_app` healthy again, not some other side effect of this
        # test -- a mutation that silently drops the new startup check
        # would make BOTH the `pytest.raises` above AND this call succeed,
        # but a mutation that left the check permanently broken (e.g.
        # caching the FIRST observed limit) would fail here instead.
        # `TestClient` as a context manager drives the real ASGI lifespan
        # protocol (startup+shutdown), the same established convention
        # every other real-`build_app` test in this file already uses.
        asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
        with TestClient(asgi_app):
            pass


def test_build_app_fails_fast_when_the_declared_process_ceilings_lower_bound_exceeds_max_connections(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """R-91 (work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_
    HEADROOM_CHECK_V1.md §1.2 D-3, completion condition 10), numbers
    updated for WP-2 (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3
    (5), 監督裁定16: `role_pool_size(thread_limit)`, `main_module`'s own
    `R2DB_THREAD_LIMIT` unset -> `DEFAULT_THREAD_LIMIT` 4, i.e. pool_size
    6 -- never `ResourceLimits.concurrency` 32): unlike F-16 (this file's
    own test just above), this new startup check is run UNSCOPED --
    `data=1` keeps F-16's own now-ceiling-multiplied floor
    (`main.py`'s own completion condition 72: `pool_size * process_
    ceiling`, here 2*6*1=12) well under `platform.api_role`'s real
    `CONNECTION LIMIT` (F-16 alone would pass), but `control=30` (the
    declared `process_ceilings` `{"data": 1, "control": 30}`, lower bound
    1*(12+12)+30*16=504) exceeds this throwaway cluster's own real
    headroom (297, §1.3 (8)) -- proving a per-process role floor check
    alone (F-16) cannot catch a cluster-wide overcommit a NARROWED check
    would miss. Mutation M9a (dropping this startup call from `r2db_api.
    main.build_app`) turns this red."""
    with psycopg.connect(platform.control_dsn) as conn:
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
            main_module.build_app(env=_main_env(platform, provisioned_app))
        assert excinfo.value.code == "F-18"
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
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
        # `build_app` healthy again, mirroring the F-16 test's own
        # non-空振り check just above.
        asgi_app = main_module.build_app(env=_main_env(platform, provisioned_app))
        with TestClient(asgi_app):
            pass


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
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _INLINE_ENV_SLOT_DIR,
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
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _INLINE_ENV_SLOT_DIR,
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
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _INLINE_ENV_SLOT_DIR,
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
        "R2DB_WORKERS": "1",
        "R2DB_SLOT_DIR": _INLINE_ENV_SLOT_DIR,
        f"R2DB_APP_{slug.upper()}_RUNTIME_DSN": "irrelevant",
        f"R2DB_APP_{slug.upper()}_DEVELOPER_DSN": "irrelevant",
    }
    with pytest.raises(RuntimeError, match="not yet provisioned"):
        main_module.build_app(env=env)


def test_build_app_invalid_control_plane_status_raises(platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType) -> None:
    """CCR-14 WP-5, R-9: `R2DB_CONTROL_PLANE_STATUS` must fail startup
    loudly on a value other than exactly `enabled`/`unavailable` -- never
    silently degrade a typo into the safe default (M6's own mutation target:
    a "silently round unknown values down to unavailable" mutation must
    turn this test red)."""
    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "ENABLED"
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_PLANE_STATUS"):
        main_module.build_app(env=env)


_INVALID_AUDIT_FLUSH_INTERVAL_VALUES = ["0", "-1", "nan", "inf", "not-a-number"]


@pytest.mark.parametrize("bad_value", _INVALID_AUDIT_FLUSH_INTERVAL_VALUES)
def test_build_app_fails_fast_on_invalid_audit_flush_interval(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType, bad_value: str,
) -> None:
    """Phase 6 WP-0 (design D-4(a)): `R2DB_AUDIT_FLUSH_INTERVAL_S` is the
    interval `main.py`'s own flush thread passes straight to `threading.
    Event.wait` (`main.py:397`) -- `wait(0)`/`wait(-1)`/`wait(float("nan"))`
    all return immediately (`False`), turning that daemon thread into a
    silent hot loop nothing about which would look alarming to an operator
    who mistyped this variable. `_optional_float` must now refuse every
    non-empty value that is not a finite, positive float at startup
    (`ValueError` naming the variable) -- exercised here through the REAL
    `build_app` path (not a direct call to `_optional_float`), so this is
    the actual startup-failure consumer wiring, not merely the helper
    function in isolation. Each of the 5 forms (zero / negative / NaN /
    infinity / unparsable text) is its own parametrize case, per WP-0
    completion condition 1 ("5 形すべてを個別ケースで観測する")."""
    env = _main_env(platform, provisioned_app)
    env["R2DB_AUDIT_FLUSH_INTERVAL_S"] = bad_value
    with pytest.raises(ValueError, match="R2DB_AUDIT_FLUSH_INTERVAL_S"):
        main_module.build_app(env=env)


def test_optional_float_default_path_is_not_regressed(main_module: types.ModuleType) -> None:
    """WP-0 completion condition 2: an unset OR empty-string
    `R2DB_AUDIT_FLUSH_INTERVAL_S` must still fall back to `default` -- the
    "空なら既定値" half that must stay green while mutation 2 (dropping the
    `if not raw: return default` early return) turns it red. A direct call
    is sufficient here (unlike the fail-fast cases above): the real-startup
    wiring for this same function/variable pair is already established by
    `test_build_app_fails_fast_on_invalid_audit_flush_interval` and by
    `_optional_float` having exactly one caller in `main.py` (the flush-
    interval assignment feeding `threading.Event.wait`)."""
    assert main_module._optional_float({}, "R2DB_AUDIT_FLUSH_INTERVAL_S", 2.5) == 2.5
    assert main_module._optional_float({"R2DB_AUDIT_FLUSH_INTERVAL_S": ""}, "R2DB_AUDIT_FLUSH_INTERVAL_S", 2.5) == 2.5


def test_build_app_default_control_plane_status_is_unavailable(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """R-9: omitting `R2DB_CONTROL_PLANE_STATUS` entirely must default to
    `unavailable`, not `enabled` -- the single-commit rule's safe default."""
    writer = _write_store(platform)
    try:
        credential_id = "crd_" + secrets.token_hex(8)
        with writer.unit_of_work() as work:
            writer.add(credential_id, provisioned_app.slug, "runtime", "s3cret-default-status", work=work)
    finally:
        writer.close()

    env = _main_env(platform, provisioned_app)
    assert "R2DB_CONTROL_PLANE_STATUS" not in env
    asgi_app = main_module.build_app(env=env)
    with TestClient(asgi_app) as client:
        response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {compose_bearer_locator(credential_id, 's3cret-default-status')}"})
        assert response.status_code == 200
        assert response.json()["capabilities"]["control_plane"] == {"status": "unavailable"}


def test_build_app_control_plane_status_enabled_is_declared(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType
) -> None:
    """R-9: setting `R2DB_CONTROL_PLANE_STATUS=enabled` is reflected
    verbatim in the real `capabilities()` response -- the deployer's own
    declaration, not a value this composition root invents."""
    writer = _write_store(platform)
    try:
        credential_id = "crd_" + secrets.token_hex(8)
        with writer.unit_of_work() as work:
            writer.add(credential_id, provisioned_app.slug, "runtime", "s3cret-enabled-status", work=work)
    finally:
        writer.close()

    env = _main_env(platform, provisioned_app)
    env["R2DB_CONTROL_PLANE_STATUS"] = "enabled"
    # Q4 phase WP-1 (design D-2(f)/F-6): `surfaces.control`'s presence is
    # now the SAME shared, DB-side `platform_declarations` row every
    # process reads (never a per-call env override) -- this test flips the
    # status to `enabled` itself, so it must also add `control` to that
    # row, and restore the module-scoped `platform` fixture's default
    # (control-less) row afterward, since later tests in this module share
    # the same fixture instance.
    _set_surfaces_row(platform, {
        "data": {"base_url": "https://r2db-main-test.example.invalid/v1"},
        "control": {"base_url": "https://r2db-control-test.example.invalid/control/v1"},
    })
    try:
        asgi_app = main_module.build_app(env=env)
        with TestClient(asgi_app) as client:
            response = client.get("/v1/capabilities", headers={"authorization": f"Bearer {compose_bearer_locator(credential_id, 's3cret-enabled-status')}"})
            assert response.status_code == 200
            assert response.json()["capabilities"]["control_plane"] == {"status": "enabled"}
    finally:
        _set_surfaces_row(platform, _DEFAULT_SURFACES_VALUE)


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
