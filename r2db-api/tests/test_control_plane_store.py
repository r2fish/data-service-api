"""CCR-14 WP-2: `0006_control_plane_http.sql`, the `unit_of_work()` pair
retrofit (`CredentialStore`/`PostgresCredentialStore`), the new
`ControlCredentialStore`/`PostgresControlCredentialStore` pair, and the
`python -m r2db_api.ops` bootstrap/reset ritual + break-glass + audited
existing subcommands -- tested against a real PostgreSQL server, mirroring
`test_credential_persistence.py`'s own conventions (§5.3 C-5: must not be
skipped).

Design this file is written against: docs/design/
R2DB_CCR14_CONTROL_PLANE_V1.md v1.4, §1 R-2/R-3/R-4/R-5/R-6/R-10, §5 WP-2
row, §7, §8 B-1/B-2/M-2/M-3/M-6/M-9/M-10/m-1..m-5 -- and the WP-2 work
order's own §6 test list.

**Round-2 history (reviewer N-2): the deviation this section used to document
is resolved, not merely re-explained.** Round 1 of this WP made `work` an
*optional* keyword argument on `add`/`set_state`/`rotate`/`delete` (default
`None`, auto-opening its own `unit_of_work()` when omitted), specifically to
avoid touching `r2db-api/conformance/conformance_adapter_r2db_http.py` --
out of round 1's scope -- which called `PostgresCredentialStore.add`/
`.set_state` without a `work` argument at several sites. The independent
review (round 2) measured that auto-managed fallback actually splitting a
caller's own multi-call transaction onto a *second* pooled connection
silently (invisible unless specifically tested for), and hard-failing
outright once the pool was exhausted (`pool_size=1`) -- exactly the "state
change and audit INSERT land on different connections" hazard design §7
warns against. Round 2's scope was explicitly extended to include that
adapter (and `r2db-api/tests/test_http.py`) so this could be fixed
properly: `work` is now a **required** keyword-only argument (no default) on
every state-changing method of all four store classes (`CredentialStore`,
`PostgresCredentialStore`, `ControlCredentialStore`,
`PostgresControlCredentialStore`) -- omitting it is a `TypeError` at the call
boundary, exactly as the work order's original §2 text asked for. Every
caller in this repository (`ops.py`, `service.ControlAuthority`, the HTTP
conformance adapter, and every test file that constructs a store directly)
now opens `unit_of_work()` explicitly and passes the handle through. The
`test_omitting_work_is_a_typeerror_*` tests below assert this directly.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from r2db_api.auth import ControlAuthContext, ControlCredentialStore, CredentialStore, compose_bearer_locator
from r2db_api.credential_store import PostgresControlCredentialStore, PostgresCredentialStore, validate_control_pepper_separation
from r2db_api.errors import FoundationError
from r2db_api.structured import RESET_CONTROL_CREDENTIALS

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
PEPPER = "synthetic-test-pepper-control-plane-store-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-control-plane-store-ctl-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    # R-56 WP-1: role-level `statement_timeout` on `r2dbsvc_auditreader`
    # -- placed right after 0007 (the migration that creates that role).
    "0014_auditreader_statement_timeout.sql",
)


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
            "test_control_plane_store.py requires a reachable local PostgreSQL "
            f"server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These "
            "tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    """Identical in spirit and mechanics to `test_credential_persistence.
    py::_sweep_prefix` / `test_postgres.py::_sweep_prefix` (duplicated
    rather than imported, matching those files' own established
    precedent)."""
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


def _provision_platform(tmp_path_factory: pytest.TempPathFactory) -> types.SimpleNamespace:
    """Bootstraps `0001` through `0006` under one throwaway prefix. Factored
    out of the `platform` fixture below so tests that need their own
    *independent* platform (the bootstrap/reset ritual's C-15-equivalent
    tests -- bootstrap is a once-per-platform operation, so tests that
    exercise it cannot safely share the module-scoped `platform` fixture
    with each other) can call this directly instead.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbtest{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-5/D-9): the
    # `auditreader` role's own password -- this file's own GRANT-realized
    # tests (`test_auditreader_role_can_select_both_audit_tables_and_
    # nothing_else` and friends) connect AS this role directly.
    auditreader_password = secrets.token_urlsafe(24)
    auditreader_role = f"{prefix}_auditreader"

    rewritten_dir = tmp_path_factory.mktemp("r2db_cp_migrations")
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
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)
    auditreader_dsn = _dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db)

    return types.SimpleNamespace(
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
        control_plane_sql=rewritten["0006_control_plane_http.sql"],
        application_audit_sql=rewritten["0007_application_audit.sql"],
        api_password=api_password,
        controlplane_password=controlplane_password,
        auditreader_password=auditreader_password,
    )


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    info = _provision_platform(tmp_path_factory)
    try:
        yield info
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def _fresh_slug(letter: str) -> str:
    return f"{letter}{secrets.token_hex(3)}"


def _register_application(platform: types.SimpleNamespace, slug: str, *, enabled: bool = True) -> None:
    """Fully-provisioned synthetic row (all four provisioning columns set) --
    see `test_credential_persistence.py::_register_application`'s identical
    helper/docstring; duplicated here per this repository's own established
    precedent of not taking cross-test-module import dependencies."""
    statement = sql.SQL(
        "INSERT INTO {table} (application_slug, database_name, runtime_role, developer_role, enabled, provisioned_at) VALUES (%s, %s, %s, %s, %s, now())"
    ).format(table=sql.Identifier(platform.schema, "applications"))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [slug, f"synthetic_db_{slug}", f"synthetic_{slug}_runtime", f"synthetic_{slug}_developer", enabled])
        conn.commit()


def _register_application_only(platform: types.SimpleNamespace, slug: str, *, enabled: bool = True) -> None:
    """Registered-only row (R-4/§8 B-1's new state): all four provisioning
    columns NULL."""
    statement = sql.SQL("INSERT INTO {table} (application_slug, enabled) VALUES (%s, %s)").format(
        table=sql.Identifier(platform.schema, "applications")
    )
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [slug, enabled])
        conn.commit()


def _write_app_store(platform: types.SimpleNamespace) -> PostgresCredentialStore:
    return PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema)


def _control_store(platform: types.SimpleNamespace) -> PostgresControlCredentialStore:
    return PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)


def _unreachable_dsn() -> str:
    return "host=127.0.0.1 port=1 dbname=nope user=nope password=nope connect_timeout=2"


def _cli_env(platform: types.SimpleNamespace, **overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["R2DB_CONTROL_DSN"] = platform.control_dsn
    env["R2DB_CREDENTIAL_PEPPER"] = PEPPER
    env["R2DB_CONTROL_CREDENTIAL_PEPPER"] = CONTROL_PEPPER
    env["R2DB_PLATFORM_SCHEMA"] = platform.schema
    env.update(overrides)
    return env


def _run_cli(platform: types.SimpleNamespace, *args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", *args],
        capture_output=True,
        text=True,
        env=_cli_env(platform, **(env_overrides or {})),
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


# ===========================================================================
# Section A: store parity (unit_of_work included) -- work order §6 item 1.
# ===========================================================================


def test_in_memory_unit_of_work_commit_applies_change() -> None:
    store = CredentialStore(pepper=PEPPER)
    with store.unit_of_work() as work:
        store.add("crd_uow1", "app-uow", "runtime", "secret-uow1", work=work)
    context = store.authenticate(compose_bearer_locator("crd_uow1", "secret-uow1"))
    assert context.credential_id == "crd_uow1"


def test_in_memory_unit_of_work_exception_rolls_back_no_change() -> None:
    store = CredentialStore(pepper=PEPPER)
    with pytest.raises(RuntimeError):
        with store.unit_of_work() as work:
            store.add("crd_uow2", "app-uow", "runtime", "secret-uow2", work=work)
            raise RuntimeError("injected failure")
    with pytest.raises(FoundationError) as exc:
        store.authenticate("secret-uow2")
    assert exc.value.code == "AUTH_INVALID"


def test_postgres_unit_of_work_commit_applies_change(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ua")
    _register_application(platform, slug)
    store = _write_app_store(platform)
    try:
        pg_credential_id = "crd_" + secrets.token_hex(8)
        with store.unit_of_work() as work:
            store.add(pg_credential_id, slug, "runtime", "secret-pguow1", work=work)
        context = store.authenticate(compose_bearer_locator(pg_credential_id, "secret-pguow1"))
        assert context.application_id == slug
    finally:
        store.close()


def test_postgres_unit_of_work_exception_rolls_back_no_change(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ub")
    _register_application(platform, slug)
    store = _write_app_store(platform)
    try:
        with pytest.raises(RuntimeError):
            with store.unit_of_work() as work:
                store.add("crd_" + secrets.token_hex(8), slug, "runtime", "secret-pguow2", work=work)
                raise RuntimeError("injected failure")
        with pytest.raises(FoundationError) as exc:
            store.authenticate("secret-pguow2")
        assert exc.value.code == "AUTH_INVALID"
    finally:
        store.close()


def test_omitting_work_is_a_typeerror_in_memory() -> None:
    """Round-2 review ruling (A): `work` is a required keyword-only argument
    on every state-changing method of all four store classes -- omitting it
    is a `TypeError` raised by Python itself at the call boundary (no
    default value exists any more). This supersedes round 1's "auto-managed
    fallback" behaviour (see this file's module docstring history, and the
    WP-2 implementation report's Round 2 section): the independent review
    measured that fallback silently opening a *second* connection/
    transaction for the auto-managed call, splitting what a caller intended
    as one atomic sequence -- exactly the hazard design §7 warns against.
    """
    store = CredentialStore(pepper=PEPPER)
    with pytest.raises(TypeError):
        store.add("crd_notypework1", "app-notypework", "runtime", "secret-notypework1")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        store.set_state("crd_whatever")  # type: ignore[call-arg]


def test_omitting_work_is_a_typeerror_postgres(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("uc")
    _register_application(platform, slug)
    store = _write_app_store(platform)
    try:
        with pytest.raises(TypeError):
            store.add("crd_" + secrets.token_hex(8), slug, "runtime", "secret-notypework2")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            store.set_state("crd_whatever")  # type: ignore[call-arg]
    finally:
        store.close()


def test_omitting_work_is_a_typeerror_control_credential_stores(platform: types.SimpleNamespace) -> None:
    """Same guarantee, both `ControlCredentialStore` implementations --
    `add`/`set_state`/`rotate`/`revoke_all` all require `work`."""
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            with pytest.raises(TypeError):
                store.add("ctl_" + secrets.token_hex(8), "secret-notypework-ctl")  # type: ignore[call-arg]
            with pytest.raises(TypeError):
                store.revoke_all()  # type: ignore[call-arg]
    finally:
        pg.close()


def test_control_credential_parity_add_authenticate_rotate_must_rotate_both_impls(platform: types.SimpleNamespace) -> None:
    """Both implementations, exercised the same way, asserting identical
    outcomes at every step -- CCR-13's `test_parity_*` convention."""
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store, credential_id in ((in_memory, "ctl_" + secrets.token_hex(8)), (pg, "ctl_" + secrets.token_hex(8))):
            with store.unit_of_work() as work:
                store.add(credential_id, "secret-parity-before", work=work)
            context = store.authenticate(compose_bearer_locator(credential_id, "secret-parity-before"))
            assert isinstance(context, ControlAuthContext)
            assert context.credential_id == credential_id
            assert context.must_rotate is True  # DEFAULT true (R-5)

            with store.unit_of_work() as work:
                store.rotate(credential_id, "secret-parity-after", work=work)
            with pytest.raises(FoundationError) as exc:
                store.authenticate(compose_bearer_locator(credential_id, "secret-parity-before"))
            assert exc.value.code == "AUTH_INVALID"
            context2 = store.authenticate(compose_bearer_locator(credential_id, "secret-parity-after"))
            assert context2.must_rotate is False  # rotate clears must_rotate (R-5)
    finally:
        pg.close()


def test_control_credential_parity_revoked_rotate_refused_both_impls(platform: types.SimpleNamespace) -> None:
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            credential_id = "ctl_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, "secret-revrot", work=work)
                store.set_state(credential_id, revoked=True, work=work)
            with pytest.raises(FoundationError) as exc:
                with store.unit_of_work() as work:
                    store.rotate(credential_id, "secret-revrot-new", work=work)
            assert exc.value.code == "VALIDATION_FAILED"
    finally:
        pg.close()


def test_control_credential_parity_un_revoke_refused_both_impls(platform: types.SimpleNamespace) -> None:
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            credential_id = "ctl_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, "secret-unrevoke", work=work)
                store.set_state(credential_id, revoked=True, work=work)
            with pytest.raises(FoundationError) as exc:
                with store.unit_of_work() as work:
                    store.set_state(credential_id, revoked=False, work=work)
            assert exc.value.code == "VALIDATION_FAILED"
    finally:
        pg.close()


def test_application_credential_rotate_parity_both_impls_does_not_check_revoked(platform: types.SimpleNamespace) -> None:
    """§8 M-2: the *application*-credential `rotate` (both implementations)
    deliberately does NOT refuse a revoked credential -- matching the
    pre-existing Postgres behaviour this WP's new in-memory `rotate` was
    written to align with (see `auth.CredentialStore.rotate`'s docstring).
    This is the opposite rule from `ControlCredentialStore.rotate` above --
    asserted explicitly here so the two are never conflated."""
    slug = _fresh_slug("ud")
    _register_application(platform, slug)
    in_memory = CredentialStore(pepper=PEPPER)
    pg = _write_app_store(platform)
    try:
        with in_memory.unit_of_work() as work:
            in_memory.add("crd_" + secrets.token_hex(8), slug, "runtime", "secret-approt-before", work=work)
        in_memory_id = list(in_memory._records)[0]
        with in_memory.unit_of_work() as work:
            in_memory.set_state(in_memory_id, revoked=True, work=work)
        with in_memory.unit_of_work() as work:
            in_memory.rotate(in_memory_id, "secret-approt-after", work=work)  # must not raise (unlike control rotate)
        # The verifier is replaced (new secret is the one on record now) --
        # but `revoked` itself is untouched by rotate, so authenticate still
        # refuses with AUTH_REVOKED, never AUTH_INVALID (which would imply
        # the new secret was simply never stored).
        with pytest.raises(FoundationError) as exc:
            in_memory.authenticate(compose_bearer_locator(in_memory_id, "secret-approt-after"))
        assert exc.value.code == "AUTH_REVOKED"
        with pytest.raises(FoundationError) as exc:
            in_memory.authenticate(compose_bearer_locator(in_memory_id, "secret-approt-before"))
        assert exc.value.code == "AUTH_INVALID"  # old secret no longer matches at all

        pg_id = "crd_" + secrets.token_hex(8)
        with pg.unit_of_work() as work:
            pg.add(pg_id, slug, "runtime", "secret-approt-pg-before", work=work)
        with pg.unit_of_work() as work:
            pg.set_state(pg_id, revoked=True, work=work)
        with pg.unit_of_work() as work:
            pg.rotate(pg_id, "secret-approt-pg-after", work=work)  # must not raise
        with pytest.raises(FoundationError) as exc:
            pg.authenticate(compose_bearer_locator(pg_id, "secret-approt-pg-after"))
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        pg.close()


def test_control_credential_visible_to_a_separate_store_instance(platform: types.SimpleNamespace) -> None:
    """0ms propagation (P2-D4-equivalent for the control-credential store):
    a change committed over a *different* connection/instance is visible to
    the very next call on an already-open reader."""
    writer = _control_store(platform)
    reader = _control_store(platform)
    try:
        credential_id = "ctl_" + secrets.token_hex(8)
        with writer.unit_of_work() as work:
            writer.add(credential_id, "secret-propagation", work=work)
        context = reader.authenticate(compose_bearer_locator(credential_id, "secret-propagation"))
        assert context.credential_id == credential_id

        with writer.unit_of_work() as work:
            writer.set_state(credential_id, revoked=True, work=work)
        with pytest.raises(FoundationError) as exc:
            reader.authenticate(compose_bearer_locator(credential_id, "secret-propagation"))
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        writer.close()
        reader.close()


def test_control_authenticate_fails_closed_when_platform_db_unreachable() -> None:
    store = PostgresControlCredentialStore(_unreachable_dsn(), pepper=CONTROL_PEPPER)
    try:
        # Phase 6 WP-2 (design D-1(c)): a WELL-FORMED locator is required
        # here -- authentication now checks the locator's SHAPE before ever
        # attempting the (unreachable) database lookup (SI-15 fail-closed,
        # no lookup on a malformed presentation), so a bare, dot-less
        # secret would short-circuit to AUTH_INVALID without ever reaching
        # the DB-unreachable path this test means to exercise.
        with pytest.raises(FoundationError) as exc:
            store.authenticate("ctl_whatever.any-secret")
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
        assert exc.value.status == 503
        with pytest.raises(FoundationError) as exc:
            store.assert_active(ControlAuthContext("ctl_whatever", True))
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
    finally:
        store.close()


def test_control_available_false_fails_closed_without_touching_the_database(platform: types.SimpleNamespace) -> None:
    store = _control_store(platform)
    try:
        store.available = False
        with pytest.raises(FoundationError) as exc:
            store.authenticate("irrelevant")
        assert exc.value.code == "AUTH_STATE_UNAVAILABLE"
        assert exc.value.status == 503
    finally:
        store.close()


def test_control_credential_store_requires_control_pepper_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("R2DB_CONTROL_CREDENTIAL_PEPPER", raising=False)
    with pytest.raises(ValueError, match="R2DB_CONTROL_CREDENTIAL_PEPPER"):
        ControlCredentialStore()


def test_cross_store_leakage_secret_added_to_one_store_never_authenticates_the_other(platform: types.SimpleNamespace) -> None:
    """MA-4 (round-2 review), R-2/R-8's separate-pepper property: a secret
    added to the application store must never authenticate against the
    control store, and vice versa -- in both cross directions. Each store
    holds an unrelated row of its own (proving a failure below is not
    merely "the store happens to be empty"). The final assertion checks
    R-2's own literal claim directly: even the *identical* secret string
    computes a different verifier under each store's pepper, so a
    coincidental same-text secret could never collide even if it were ever
    presented to the wrong store.
    """
    app_secret = "cross-leak-app-" + secrets.token_urlsafe(16)
    control_secret = "cross-leak-control-" + secrets.token_urlsafe(16)
    slug = _fresh_slug("xl")
    _register_application(platform, slug)
    app_store = _write_app_store(platform)
    control_store = _control_store(platform)
    try:
        app_credential_id = "crd_" + secrets.token_hex(8)
        with app_store.unit_of_work() as work:
            app_store.add(app_credential_id, slug, "runtime", app_secret, work=work)
        control_credential_id = "ctl_" + secrets.token_hex(8)
        with control_store.unit_of_work() as work:
            control_store.add(control_credential_id, control_secret, work=work)

        # Cross direction 1: the control credential's own secret, presented
        # to the application store UNDER THE APP STORE'S OWN KNOWN
        # credential_id (Phase 6 WP-2, design D-1(c): a locator naming an
        # unknown credential_id would fail on that alone, never reaching
        # compare_digest at all -- using the app store's own real id here
        # is what makes this genuinely exercise "the secret half from the
        # WRONG store/pepper never matches", not merely "unknown id") --
        # AUTH_INVALID.
        with pytest.raises(FoundationError) as exc:
            app_store.authenticate(compose_bearer_locator(app_credential_id, control_secret))
        assert exc.value.code == "AUTH_INVALID"

        # Cross direction 2: the application credential's own secret,
        # presented to the control store under the control store's own
        # known credential_id -- AUTH_INVALID.
        with pytest.raises(FoundationError) as exc:
            control_store.authenticate(compose_bearer_locator(control_credential_id, app_secret))
        assert exc.value.code == "AUTH_INVALID"

        # Each store still correctly authenticates its own credential.
        assert app_store.authenticate(compose_bearer_locator(app_credential_id, app_secret)).credential_id == app_credential_id
        assert control_store.authenticate(compose_bearer_locator(control_credential_id, control_secret)).credential_id == control_credential_id

        # R-2's own claim, directly: identical literal secret, different
        # verifier under each store's pepper.
        shared = "identical-literal-secret-" + secrets.token_urlsafe(8)
        assert app_store.verifier(shared) != control_store.verifier(shared)
    finally:
        app_store.close()
        control_store.close()


# ===========================================================================
# Section B: pepper separation (R-2) -- work order §6 item 5.
# ===========================================================================


# ===========================================================================
# Section A2 (Phase 6 WP-2, design docs/design/PHASE6_CONTRACT_160_CLIENT_
# DISCOVERY_V1.md D-1(c)): the locator wire form itself -- verbatim accept,
# the 3 malformed-locator fail-closed shapes, response uniformity (SI-10),
# and judgment order (compare_digest before revoked/enabled/app_enabled),
# for BOTH the application store and the control store, BOTH backends.
# ===========================================================================


_MALFORMED_LOCATORS = (
    "no-dot-at-all",  # no "." separator
    ".secret-part-only",  # empty credential_id half
    "credential-id-only.",  # empty secret half
    "crd_\x00nulid.secret",  # NUL byte in the credential_id half (coordinator F1)
    "crd_nulid.sec\x00ret",  # NUL byte in the secret half (coordinator F1)
)


@pytest.mark.parametrize("malformed", _MALFORMED_LOCATORS)
def test_malformed_locator_fails_closed_without_a_lookup_in_memory_app_store(malformed: str) -> None:
    """Design D-1(c) fail-closed rule: a malformed locator (no `.`, empty
    credential_id half, empty secret half) is `AUTH_INVALID` WITHOUT ever
    looking anything up -- exercised here against a store holding a REAL
    row, so a mutation that starts scanning `self._records` for a malformed
    presentation (rather than rejecting the shape outright) would still
    observe AUTH_INVALID by coincidence only if nothing happens to match;
    the dedicated `split_bearer_locator`-return-`None` path is what this
    test is really pinned to (see the sibling Postgres test below, whose
    malformed presentation deliberately shares no substring with any real
    row, closing that coincidence gap for both backends together)."""
    store = CredentialStore(pepper=PEPPER)
    with store.unit_of_work() as work:
        store.add("crd_realrow00000001", "some-app", "runtime", "some-real-secret", work=work)
    with pytest.raises(FoundationError) as exc:
        store.authenticate(malformed)
    assert exc.value.code == "AUTH_INVALID"


@pytest.mark.parametrize("malformed", _MALFORMED_LOCATORS)
def test_malformed_locator_fails_closed_without_a_lookup_postgres_app_store(malformed: str, platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ml")
    _register_application(platform, slug)
    store = _write_app_store(platform)
    try:
        with store.unit_of_work() as work:
            store.add("crd_" + secrets.token_hex(8), slug, "runtime", "some-real-secret-" + secrets.token_urlsafe(8), work=work)
        with pytest.raises(FoundationError) as exc:
            store.authenticate(malformed)
        assert exc.value.code == "AUTH_INVALID"
    finally:
        store.close()


@pytest.mark.parametrize("malformed", _MALFORMED_LOCATORS)
def test_malformed_locator_fails_closed_control_store_both_impls(malformed: str, platform: types.SimpleNamespace) -> None:
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            credential_id = "ctl_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, "some-real-control-secret-" + secrets.token_urlsafe(8), work=work)
            with pytest.raises(FoundationError) as exc:
                store.authenticate(malformed)
            assert exc.value.code == "AUTH_INVALID"
    finally:
        pg.close()


def test_dot_less_locator_matching_a_real_secrets_own_text_still_fails_closed_in_memory() -> None:
    """Work order mutation 4's own pin: a dot-less presentation is refused
    WITHOUT ever being compared against any stored row -- even when that
    presentation happens to be the EXACT TEXT of a real credential's own
    secret. A full-table-scan fallback for the malformed-shape case (the
    mutation this test is written against) would find this coincidental
    match and wrongly authenticate; the correct fail-closed behavior
    rejects on the missing `.` alone, before any comparison happens."""
    store = CredentialStore(pepper=PEPPER)
    coincidental_secret = "this-text-has-no-dot-in-it-at-all"
    with store.unit_of_work() as work:
        store.add("crd_coincidence0001", "some-app", "runtime", coincidental_secret, work=work)
    with pytest.raises(FoundationError) as exc:
        store.authenticate(coincidental_secret)  # presented bare, no locator prefix
    assert exc.value.code == "AUTH_INVALID"


def test_unknown_locator_and_known_locator_wrong_secret_are_both_uniformly_auth_invalid_app_store(platform: types.SimpleNamespace) -> None:
    """SI-10: an unknown `credential_id` and a known `credential_id` with a
    digest mismatch must be indistinguishable in the response -- both
    `AUTH_INVALID`, both both backends. (The malformed-shape case above is
    already, separately, `AUTH_INVALID` too -- this test is about the two
    LOOKUP-REACHING outcomes specifically.)"""
    slug = _fresh_slug("un")
    _register_application(platform, slug)
    for store in (CredentialStore(pepper=PEPPER), _write_app_store(platform)):
        try:
            credential_id = "crd_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, slug, "runtime", "the-real-secret", work=work)

            with pytest.raises(FoundationError) as exc_unknown:
                store.authenticate(compose_bearer_locator("crd_" + secrets.token_hex(8), "irrelevant-secret"))
            with pytest.raises(FoundationError) as exc_wrong_secret:
                store.authenticate(compose_bearer_locator(credential_id, "the-WRONG-secret"))

            assert exc_unknown.value.code == "AUTH_INVALID"
            assert exc_wrong_secret.value.code == "AUTH_INVALID"
            assert exc_unknown.value.status == exc_wrong_secret.value.status == 401
            # Same message, same shape -- SI-10's own "no existence-
            # distinction disclosure" reading extended to this pair.
            assert exc_unknown.value.message == exc_wrong_secret.value.message
        finally:
            if hasattr(store, "close"):
                store.close()


def test_digest_check_precedes_revoked_and_enabled_state_both_impls_and_both_stores(platform: types.SimpleNamespace) -> None:
    """Design implementation constraint 1 (B-1 ruling maintained): `compare_
    digest` is evaluated -- and must succeed -- BEFORE any `revoked`/
    `enabled` state check. Pinned here by presenting the WRONG secret
    against a row that is ALSO revoked/disabled: if state were checked
    first, this would surface AUTH_REVOKED/AUTH_INVALID-via-disabled
    instead of the digest-mismatch AUTH_INVALID this test asserts -- a
    mutation that reorders the checks turns this red without touching the
    uniformity test above (which never revokes/disables anything)."""
    # Application store, revoked.
    slug = _fresh_slug("or")
    _register_application(platform, slug)
    for store in (CredentialStore(pepper=PEPPER), _write_app_store(platform)):
        try:
            credential_id = "crd_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, slug, "runtime", "real-secret-order", work=work)
                store.set_state(credential_id, revoked=True, work=work)
            with pytest.raises(FoundationError) as exc:
                store.authenticate(compose_bearer_locator(credential_id, "WRONG-secret-order"))
            assert exc.value.code == "AUTH_INVALID"  # not AUTH_REVOKED -- digest never matched
        finally:
            if hasattr(store, "close"):
                store.close()

    # Control store, disabled (both impls).
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            credential_id = "ctl_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, "real-control-secret-order", work=work)
                store.set_state(credential_id, enabled=False, work=work)
            with pytest.raises(FoundationError) as exc:
                store.authenticate(compose_bearer_locator(credential_id, "WRONG-control-secret-order"))
            assert exc.value.code == "AUTH_INVALID"  # not the disabled-AUTH_INVALID path -- digest never matched
    finally:
        pg.close()


def test_locator_id_must_own_the_secret_not_merely_any_row_app_store(platform: types.SimpleNamespace) -> None:
    """Design D-1(c), r2db decision (c): authentication is a `credential_id`
    -keyed row lookup, THEN a digest check against THAT row -- never a
    digest-keyed (`_SELECT_BY_VERIFIER`) scan across every row. Pinned by
    presenting credential 2's own `credential_id` locator-joined with
    credential 1's own (genuinely valid, for credential 1) secret: under
    the correct id-first lookup, this fails (credential 2's row's verifier
    does not match credential 1's secret). Under a digest-keyed lookup
    (the retired `_SELECT_BY_VERIFIER` form, work order mutation 2), the
    digest WOULD match credential 1's row regardless of which id was
    named in the locator, and would wrongly authenticate as credential 1
    under credential 2's own claimed identity."""
    slug = _fresh_slug("xw")
    _register_application(platform, slug)
    for store in (CredentialStore(pepper=PEPPER), _write_app_store(platform)):
        try:
            id1 = "crd_" + secrets.token_hex(8)
            secret1 = "cross-wire-secret-1-" + secrets.token_urlsafe(8)
            id2 = "crd_" + secrets.token_hex(8)
            secret2 = "cross-wire-secret-2-" + secrets.token_urlsafe(8)
            with store.unit_of_work() as work:
                store.add(id1, slug, "runtime", secret1, work=work)
            with store.unit_of_work() as work:
                store.add(id2, slug, "runtime", secret2, work=work)

            # id2's own locator, but credential 1's secret -- must fail.
            with pytest.raises(FoundationError) as exc:
                store.authenticate(compose_bearer_locator(id2, secret1))
            assert exc.value.code == "AUTH_INVALID"

            # Each credential's OWN genuine locator still authenticates as
            # itself (not as the other).
            assert store.authenticate(compose_bearer_locator(id1, secret1)).credential_id == id1
            assert store.authenticate(compose_bearer_locator(id2, secret2)).credential_id == id2
        finally:
            if hasattr(store, "close"):
                store.close()


def test_compose_bearer_locator_rejects_a_dot_in_either_half() -> None:
    """Coordinator item 7(iii) (reviewer O2): `compose_bearer_locator`'s
    own docstring claim ("credential_id/secret never contain `.`, so this
    join is always unambiguous") was, before this fix, a documented
    convention of this module's OWN minters, never a checked precondition
    of the function itself. A `.` in either half is now a `ValueError` at
    the issuance boundary."""
    with pytest.raises(ValueError):
        compose_bearer_locator("crd.with.dot", "secret")
    with pytest.raises(ValueError):
        compose_bearer_locator("crd_ok", "secret.with.dot")
    # Positive control: no dot in either half still composes normally.
    assert compose_bearer_locator("crd_ok", "secret_ok") == "crd_ok.secret_ok"


def test_locator_id_must_own_the_secret_not_merely_any_row_control_store(platform: types.SimpleNamespace) -> None:
    in_memory = ControlCredentialStore(pepper=CONTROL_PEPPER)
    pg = _control_store(platform)
    try:
        for store in (in_memory, pg):
            id1 = "ctl_" + secrets.token_hex(8)
            secret1 = "cross-wire-control-secret-1-" + secrets.token_urlsafe(8)
            id2 = "ctl_" + secrets.token_hex(8)
            secret2 = "cross-wire-control-secret-2-" + secrets.token_urlsafe(8)
            with store.unit_of_work() as work:
                store.add(id1, secret1, work=work)
            with store.unit_of_work() as work:
                store.add(id2, secret2, work=work)

            with pytest.raises(FoundationError) as exc:
                store.authenticate(compose_bearer_locator(id2, secret1))
            assert exc.value.code == "AUTH_INVALID"

            assert store.authenticate(compose_bearer_locator(id1, secret1)).credential_id == id1
            assert store.authenticate(compose_bearer_locator(id2, secret2)).credential_id == id2
    finally:
        pg.close()


def test_verbatim_composed_bearer_authenticates_every_store_and_backend(platform: types.SimpleNamespace) -> None:
    """The positive control for the 3 tests above: a genuinely composed,
    unmodified bearer (`compose_bearer_locator`, never hand-assembled) DOES
    authenticate, for the application store and the control store, both
    backends -- confirming the malformed/unknown/wrong-secret/wrong-order
    tests above are rejecting for the RIGHT reason, not because nothing
    can ever authenticate."""
    slug = _fresh_slug("vb")
    _register_application(platform, slug)
    for store in (CredentialStore(pepper=PEPPER), _write_app_store(platform)):
        try:
            credential_id = "crd_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, slug, "runtime", "verbatim-secret", work=work)
            context = store.authenticate(compose_bearer_locator(credential_id, "verbatim-secret"))
            assert context.credential_id == credential_id
        finally:
            if hasattr(store, "close"):
                store.close()

    for store in (ControlCredentialStore(pepper=CONTROL_PEPPER), _control_store(platform)):
        try:
            credential_id = "ctl_" + secrets.token_hex(8)
            with store.unit_of_work() as work:
                store.add(credential_id, "verbatim-control-secret", work=work)
            context = store.authenticate(compose_bearer_locator(credential_id, "verbatim-control-secret"))
            assert context.credential_id == credential_id
        finally:
            if hasattr(store, "close"):
                store.close()


def test_validate_control_pepper_separation_rejects_equal_peppers() -> None:
    with pytest.raises(ValueError, match="must not be equal"):
        validate_control_pepper_separation("same-value", "same-value")


def test_validate_control_pepper_separation_allows_distinct_or_absent_peppers() -> None:
    validate_control_pepper_separation("app-pepper", "control-pepper")  # must not raise
    validate_control_pepper_separation(None, "control-pepper")
    validate_control_pepper_separation("app-pepper", None)
    validate_control_pepper_separation(None, None)


def test_cli_control_ritual_refuses_when_peppers_are_equal(platform: types.SimpleNamespace) -> None:
    result = _run_cli(platform, "bootstrap", env_overrides={"R2DB_CONTROL_CREDENTIAL_PEPPER": PEPPER})
    assert result.returncode != 0
    assert "must not be equal" in (result.stderr or "")


def test_cli_control_ritual_requires_control_pepper_env(platform: types.SimpleNamespace) -> None:
    env = _cli_env(platform)
    env.pop("R2DB_CONTROL_CREDENTIAL_PEPPER", None)
    result = subprocess.run([sys.executable, "-m", "r2db_api.ops", "bootstrap"], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "R2DB_CONTROL_CREDENTIAL_PEPPER" in result.stderr


# ===========================================================================
# Section C: bootstrap/reset ritual, C-15-equivalent -- work order §6 item 2.
# Each test below provisions its OWN independent platform (bootstrap is a
# once-per-platform operation; sharing the module `platform` fixture across
# these tests would make them order-dependent on each other).
# ===========================================================================


def test_bootstrap_before_no_secret_authenticates_then_bootstrap_succeeds_then_refuses_again(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    info = _provision_platform(tmp_path_factory)
    try:
        # §8 M-5: before bootstrap, no secret at all authenticates as a
        # control credential -- not even against an entirely empty table.
        reader = _control_store(info)
        try:
            for candidate in ("", "admin", "password", secrets.token_urlsafe(32)):
                if not candidate:
                    continue
                with pytest.raises(FoundationError) as exc:
                    reader.authenticate(candidate)
                assert exc.value.code == "AUTH_INVALID"
        finally:
            reader.close()

        first = _run_cli(info, "bootstrap")
        assert first.returncode == 0, first.stderr
        credential_id, secret = _parse_issued(first.stdout)
        assert "must_rotate: true" in first.stdout
        # MI-8 (round-2 review): the ritual's own id format, pinned --
        # `ctl_` + 16 lowercase hex characters (`secrets.token_hex(8)`).
        assert re.fullmatch(r"ctl_[0-9a-f]{16}", credential_id), f"bootstrap-issued id {credential_id!r} does not match ^ctl_[0-9a-f]{{16}}$"

        control = _control_store(info)
        try:
            context = control.authenticate(secret)
            assert context.credential_id == credential_id
            assert context.must_rotate is True
        finally:
            control.close()

        # Row exists now -- a second bootstrap is refused, exit code 1.
        second = _run_cli(info, "bootstrap")
        assert second.returncode == 1
        assert "reset" in (second.stderr or "").lower()

        # §8 M-6: even once every existing row is revoked (simulating the
        # future in-band revoke endpoint, WP-3 -- direct store manipulation
        # here, since no CLI revoke-control-credential path exists in this
        # WP by design, R-10: "revoke された control credential の復活手段は
        # 作らない"), bootstrap still refuses -- existence, not liveness.
        admin_store = _control_store(info)
        try:
            with admin_store.unit_of_work() as work:
                admin_store.set_state(credential_id, revoked=True, work=work)
            assert admin_store.has_any(include_revoked=True) is True
            assert admin_store.has_any(include_revoked=False) is False
        finally:
            admin_store.close()

        third = _run_cli(info, "bootstrap")
        assert third.returncode == 1
        assert "reset" in (third.stderr or "").lower()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_two_independent_bootstraps_produce_different_secrets(tmp_path_factory: pytest.TempPathFactory) -> None:
    info_a = _provision_platform(tmp_path_factory)
    info_b = _provision_platform(tmp_path_factory)
    try:
        result_a = _run_cli(info_a, "bootstrap")
        result_b = _run_cli(info_b, "bootstrap")
        assert result_a.returncode == 0, result_a.stderr
        assert result_b.returncode == 0, result_b.stderr
        _id_a, secret_a = _parse_issued(result_a.stdout)
        _id_b, secret_b = _parse_issued(result_b.stdout)
        assert secret_a != secret_b
    finally:
        _sweep_prefix(info_a.admin_dsn, info_a.prefix)
        _sweep_prefix(info_b.admin_dsn, info_b.prefix)


def test_reset_revokes_all_and_issues_one_new_credential_atomically_and_touches_nothing_else(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        old_id, old_secret = _parse_issued(bootstrapped.stdout)

        # Application data + application credential, present before reset --
        # R-5: reset must not touch either.
        slug = _fresh_slug("rs")
        _register_application(info, slug)
        app_store = _write_app_store(info)
        try:
            app_credential_id = "crd_" + secrets.token_hex(8)
            with app_store.unit_of_work() as work:
                app_store.add(app_credential_id, slug, "runtime", "secret-untouched-by-reset", work=work)
        finally:
            app_store.close()

        reset_result = _run_cli(info, "reset", "--confirm", RESET_CONTROL_CREDENTIALS)
        assert reset_result.returncode == 0, reset_result.stderr
        new_id, new_secret = _parse_issued(reset_result.stdout)
        assert new_id != old_id
        assert new_secret != old_secret

        control = _control_store(info)
        try:
            # Old credential revoked...
            with pytest.raises(FoundationError) as exc:
                control.authenticate(old_secret)
            assert exc.value.code == "AUTH_REVOKED"
            # ...new one live, must_rotate true.
            context = control.authenticate(new_secret)
            assert context.credential_id == new_id
            assert context.must_rotate is True
        finally:
            control.close()

        # Application data/credential unaffected.
        app_reader = _write_app_store(info)
        try:
            app_context = app_reader.authenticate(compose_bearer_locator(app_credential_id, "secret-untouched-by-reset"))
            assert app_context.application_id == slug
        finally:
            app_reader.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_reset_atomicity_fault_injection_leaves_old_state_completely_intact(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """R-6/design §7 "reset の原子性": the revoke-all and the new issuance
    share one transaction with the canonical `control_audit` INSERT.
    Faulting the audit write (by making `control_audit` momentarily
    unreachable under its expected name) must abort the *entire* reset --
    the pre-existing credential must still authenticate afterwards, exactly
    as if `reset` had never run at all.
    """
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        old_id, old_secret = _parse_issued(bootstrapped.stdout)

        rename_away = sql.SQL("ALTER TABLE {table} RENAME TO control_audit_fault_injected").format(
            table=sql.Identifier(info.schema, "control_audit")
        )
        rename_back = sql.SQL("ALTER TABLE {schema}.control_audit_fault_injected RENAME TO control_audit").format(
            schema=sql.Identifier(info.schema)
        )
        with psycopg.connect(info.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(rename_away)
            conn.commit()
        try:
            faulted = _run_cli(info, "reset", "--confirm", RESET_CONTROL_CREDENTIALS)
            assert faulted.returncode != 0, "reset must fail when control_audit cannot be written"
        finally:
            with psycopg.connect(info.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(rename_back)
                conn.commit()

        control = _control_store(info)
        try:
            # The pre-existing credential is untouched -- still authenticates,
            # never revoked by the aborted attempt.
            context = control.authenticate(old_secret)
            assert context.credential_id == old_id
            # And no new row was left behind by the aborted attempt either.
            assert control.has_any(include_revoked=True) is True
        finally:
            control.close()

        # A subsequent, un-faulted reset still works normally -- the failed
        # attempt left the table in a clean, reusable state, not a
        # half-applied one.
        recovered = _run_cli(info, "reset", "--confirm", RESET_CONTROL_CREDENTIALS)
        assert recovered.returncode == 0, recovered.stderr
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


# ===========================================================================
# Q-1 WP-4 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4):
# `reset`'s own declare-and-echo gate.
# ===========================================================================

_DECLARATION_DETAILS_KEYS = {"required_confirmation", "consequence", "reversible_alternative", "recovery"}


def test_cli_reset_without_confirm_declares_and_touches_nothing(tmp_path_factory: pytest.TempPathFactory) -> None:
    """An unconfirmed `reset` executes nothing at all: the pre-existing
    control credential is neither revoked nor replaced, and no row is
    added -- the confirmation gate runs before `_control_store()`/
    `_control_audit_sink()` are even constructed (`ops._require_cli_
    confirmation`'s own docstring), so not even a connection is opened."""
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        old_id, old_secret = _parse_issued(bootstrapped.stdout)

        control = _control_store(info)
        try:
            before = control.list_all()
        finally:
            control.close()

        refused = _run_cli(info, "reset")
        assert refused.returncode == 2, refused.stderr
        assert refused.stdout == ""
        declaration = json.loads(refused.stderr.strip())
        assert declaration["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        details = declaration["details"]
        assert set(details) == _DECLARATION_DETAILS_KEYS, "all four contract-required declaration keys must be present"
        # Opus review MA-2: literal expected value, not the imported
        # constant re-compared against itself -- a mutation of `structured.
        # RESET_CONTROL_CREDENTIALS`'s own value would otherwise silently
        # agree with whatever this test imports, since both sides would be
        # the same (mutated) object.
        assert details["required_confirmation"] == "RESET_CONTROL_CREDENTIALS"
        assert isinstance(details["consequence"], str) and details["consequence"], "consequence must be a non-empty string"
        assert isinstance(details["reversible_alternative"], str) and details["reversible_alternative"]
        assert isinstance(details["recovery"], str) and details["recovery"]

        control = _control_store(info)
        try:
            after = control.list_all()
            context = control.authenticate(old_secret)
            assert context.credential_id == old_id
        finally:
            control.close()
        assert after == before, "an unconfirmed reset must not change any control_credentials row"
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_cli_reset_wrong_confirm_phrase_declares_and_touches_nothing(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Contract `valid_confirmation`'s exact-match rule, adversarially: a
    suffix, a prefix, a case fold, and an empty string are all refused --
    never a prefix/suffix/truthy/presence check."""
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        old_id, old_secret = _parse_issued(bootstrapped.stdout)

        control = _control_store(info)
        try:
            before = control.list_all()
        finally:
            control.close()

        # Literal, not the imported constant (Opus review MA-2) -- see the
        # identical note above.
        for wrong in (
            "RESET_CONTROL_CREDENTIALSX",
            "RESET_CONTROL_CREDENTIAL",
            "reset_control_credentials",
            "",
        ):
            refused = _run_cli(info, "reset", "--confirm", wrong)
            assert refused.returncode == 2, refused.stderr
            declaration = json.loads(refused.stderr.strip())
            assert declaration["details"]["required_confirmation"] == "RESET_CONTROL_CREDENTIALS"

        control = _control_store(info)
        try:
            after = control.list_all()
            context = control.authenticate(old_secret)
            assert context.credential_id == old_id
        finally:
            control.close()
        assert after == before, "no wrong-phrase attempt above may have changed any control_credentials row"
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def _run_cli_no_env(*args: str) -> subprocess.CompletedProcess:
    """Opus review MA-3: runs the CLI with NONE of this codebase's own
    `R2DB_*` environment variables set at all -- not `R2DB_CONTROL_DSN`,
    not `R2DB_CONTROL_CREDENTIAL_PEPPER` -- to prove the confirmation gate
    really does run before any environment variable is even required, let
    alone before a database connection is opened. `PYTHONPATH` is kept
    (needed only so the subprocess can import `r2db_api` at all; it is not
    part of this CLI's own documented environment contract)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("R2DB_")}
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run([sys.executable, "-m", "r2db_api.ops", *args], capture_output=True, text=True, env=env)


def test_cli_reset_without_confirm_refuses_before_any_env_var_is_required() -> None:
    """Opus review MA-3: with no `R2DB_*` environment variable set at all,
    an unconfirmed `reset` still produces the ordinary gate declaration --
    not `_require_env`'s "R2DB_CONTROL_DSN is required" -- proving the gate
    runs before `_control_store()` even looks at the environment, let alone
    connects to a database. No platform to provision/sweep here at all:
    this process never reaches anything that would need one."""
    result = _run_cli_no_env("reset")
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "R2DB_CONTROL_DSN" not in (result.stderr or ""), "must not have reached the env-var check at all"
    declaration = json.loads(result.stderr.strip())
    assert declaration["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert declaration["details"]["required_confirmation"] == "RESET_CONTROL_CREDENTIALS"


def test_cli_reset_confirmation_phrase_is_deterministic_across_denials(tmp_path_factory: pytest.TempPathFactory) -> None:
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr

        first = _run_cli(info, "reset")
        second = _run_cli(info, "reset")
        assert first.returncode == second.returncode == 2
        phrase_1 = json.loads(first.stderr.strip())["details"]["required_confirmation"]
        phrase_2 = json.loads(second.stderr.strip())["details"]["required_confirmation"]
        # Literal expected value (Opus review MA-2) -- see the note above.
        assert phrase_1 == phrase_2 == "RESET_CONTROL_CREDENTIALS"
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_cli_reset_echo_of_declared_phrase_succeeds(tmp_path_factory: pytest.TempPathFactory) -> None:
    """The probe->echo protocol end to end: an operator who does not
    already know the phrase gets it from a first, refused invocation's own
    stderr declaration, and echoing it back verbatim on a second invocation
    proceeds exactly as `reset` always has."""
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        old_id, old_secret = _parse_issued(bootstrapped.stdout)

        probe = _run_cli(info, "reset")
        assert probe.returncode == 2
        phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]

        echoed = _run_cli(info, "reset", "--confirm", phrase)
        assert echoed.returncode == 0, echoed.stderr
        new_id, new_secret = _parse_issued(echoed.stdout)
        assert new_id != old_id
        assert new_secret != old_secret

        control = _control_store(info)
        try:
            with pytest.raises(FoundationError) as exc:
                control.authenticate(old_secret)
            assert exc.value.code == "AUTH_REVOKED"
            context = control.authenticate(new_secret)
            assert context.credential_id == new_id
        finally:
            control.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases() -> None:
    """WP-4 item A's own "3 面 (data/control/CLI) 書式一致" follow-through:
    the CLI's two destructive-confirmation phrases (`RESET_CONTROL_
    CREDENTIALS`/`delete_credential_confirmation_phrase`) live in the exact
    same module `structured.py` (now in `delete_confirmation.py`) as the data/schema-plane phrase functions
    and the control-plane's own `revoke_last_control_credential_
    confirmation_phrase` -- `ops.py` imports these exact module-level
    symbols rather than re-deriving its own spelling.

    Opus review MI-3 (measured): the `delete_credential_confirmation_
    phrase is` assertion below genuinely proves no re-derivation -- function
    objects are never coalesced by CPython the way equal string literals
    can be, so an accidental copy/shadow in `ops.py` (even one that happened
    to produce identical output) would fail this `is` check. The `RESET_
    CONTROL_CREDENTIALS is` assertion does NOT carry the same guarantee:
    CPython interns short, identifier-like string literals, so a `ops.py`
    that hardcoded its own literal `"RESET_CONTROL_CREDENTIALS"` instead of
    importing the constant would, in practice, still pass an `is` check
    against `structured.RESET_CONTROL_CREDENTIALS` (confirmed by measurement
    -- a separately-written literal of the same text interned to the same
    object). This assertion is kept because it is still true and documents
    the intended sharing, but the actual regression coverage for `RESET_
    CONTROL_CREDENTIALS`'s own correctness comes from the literal-value
    assertions in the `test_cli_reset_*` tests above (Opus review MA-2),
    not from this identity check.
    """
    import r2db_api.ops as ops
    import r2db_api.structured as structured

    assert ops.delete_credential_confirmation_phrase is structured.delete_credential_confirmation_phrase
    assert ops.RESET_CONTROL_CREDENTIALS is structured.RESET_CONTROL_CREDENTIALS


def test_bootstrap_audit_write_failure_aborts_the_whole_bootstrap(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Same fail-closed guarantee as `test_reset_atomicity_fault_injection_
    leaves_old_state_completely_intact` above, exercised against `bootstrap`
    instead of `reset`: if the canonical `control_audit` row cannot be
    written, the credential issuance itself must not have happened either --
    a faulted bootstrap must be retryable from a still-completely-empty
    `control_credentials` table, not leave an unaudited row behind."""
    info = _provision_platform(tmp_path_factory)
    rename_away = sql.SQL("ALTER TABLE {table} RENAME TO control_audit_fault_injected").format(table=sql.Identifier(info.schema, "control_audit"))
    rename_back = sql.SQL("ALTER TABLE {schema}.control_audit_fault_injected RENAME TO control_audit").format(schema=sql.Identifier(info.schema))
    try:
        with psycopg.connect(info.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(rename_away)
            conn.commit()
        try:
            faulted = _run_cli(info, "bootstrap")
            assert faulted.returncode != 0, "bootstrap must fail when control_audit cannot be written"
        finally:
            with psycopg.connect(info.control_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(rename_back)
                conn.commit()

        control = _control_store(info)
        try:
            assert control.has_any(include_revoked=True) is False, "the faulted bootstrap must not have left a credential row behind"
        finally:
            control.close()

        recovered = _run_cli(info, "bootstrap")
        assert recovered.returncode == 0, recovered.stderr
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_break_glass_enable_control_credential(tmp_path_factory: pytest.TempPathFactory) -> None:
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        credential_id, secret = _parse_issued(bootstrapped.stdout)

        control = _control_store(info)
        try:
            with control.unit_of_work() as work:
                control.set_state(credential_id, enabled=False, work=work)
        finally:
            control.close()

        with pytest.raises(FoundationError):
            reader = _control_store(info)
            try:
                reader.authenticate(secret)
            finally:
                reader.close()

        enabled = _run_cli(info, "enable-control-credential", credential_id)
        assert enabled.returncode == 0, enabled.stderr

        reader = _control_store(info)
        try:
            context = reader.authenticate(secret)
            assert context.credential_id == credential_id
        finally:
            reader.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_break_glass_rotate_control_credential_keeps_same_id_and_clears_must_rotate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        credential_id, old_secret = _parse_issued(bootstrapped.stdout)

        rotated = _run_cli(info, "rotate-control-credential", credential_id)
        assert rotated.returncode == 0, rotated.stderr
        rotated_id, new_secret = _parse_issued(rotated.stdout)
        assert rotated_id == credential_id
        assert new_secret != old_secret

        control = _control_store(info)
        try:
            with pytest.raises(FoundationError) as exc:
                control.authenticate(old_secret)
            assert exc.value.code == "AUTH_INVALID"
            context = control.authenticate(new_secret)
            assert context.credential_id == credential_id
            assert context.must_rotate is False
        finally:
            control.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_break_glass_never_offers_un_revoke(tmp_path_factory: pytest.TempPathFactory) -> None:
    """R-10: revoked control credentials have no CLI recovery path at all
    (no `revoke-control-credential` subcommand exists to have produced this
    state via the CLI in this WP -- simulated here via direct store access,
    matching a future in-band revoke). `enable-control-credential` only ever
    flips `enabled`, never `revoked` (`cmd_enable_control_credential` calls
    `set_state(enabled=True)`, not `revoked=False`) -- matching the existing
    C-13-fixed semantics `enable-credential` already has for application
    credentials (design §2's `.../credentials/{id}/enable` row: "revoked は
    反転しない...enable 自体は revoked を残したまま state を返す"): the CLI
    command itself exits 0 (it is not an error to call `enable` on a
    disabled-or-revoked row), but a still-revoked credential remains
    permanently unable to authenticate regardless -- there is no way,
    through this subcommand or any other in this WP, to clear `revoked`."""
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        credential_id, secret = _parse_issued(bootstrapped.stdout)

        control = _control_store(info)
        try:
            with control.unit_of_work() as work:
                control.set_state(credential_id, revoked=True, work=work)
        finally:
            control.close()

        result = _run_cli(info, "enable-control-credential", credential_id)
        assert result.returncode == 0, result.stderr

        reader = _control_store(info)
        try:
            with pytest.raises(FoundationError) as exc:
                reader.authenticate(secret)
            assert exc.value.code == "AUTH_REVOKED"
        finally:
            reader.close()

        # And a *direct* attempt to clear `revoked` (what a real un-revoke
        # would require) is refused at the store layer regardless of which
        # caller attempts it -- this CLI subcommand simply never tries.
        direct = _control_store(info)
        try:
            with pytest.raises(FoundationError) as exc:
                with direct.unit_of_work() as work:
                    direct.set_state(credential_id, revoked=False, work=work)
            assert exc.value.code == "VALIDATION_FAILED"
        finally:
            direct.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


# ===========================================================================
# Phase 3.5 WP-4: `issue-audit-credential` ceremony, `freeze-issuance`/
# `unfreeze-issuance` CLI subcommands (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
# §4/§1-D/§1-E).
# ===========================================================================


def test_cli_issue_audit_credential_produces_a_ready_to_use_credential(platform: types.SimpleNamespace) -> None:
    """Out-of-band audit-credential issuance -- no in-band path exists for
    `role="audit"` either. The printed secret already has `must_rotate:
    false` (the ceremony issues AND rotates before ever printing, design §4
    M-1 -- there is no in-band self-rotate path for an audit principal to
    otherwise clear it with)."""
    result = _run_cli(platform, "issue-audit-credential")
    assert result.returncode == 0, result.stderr
    credential_id, secret = _parse_issued(result.stdout)
    assert "must_rotate: false" in result.stdout
    assert re.fullmatch(r"ctl_[0-9a-f]{16}", credential_id), f"issued id {credential_id!r} does not match ^ctl_[0-9a-f]{{16}}$"

    control = _control_store(platform)
    try:
        context = control.authenticate(secret)
        assert context.credential_id == credential_id
        assert context.must_rotate is False
        assert context.role == "audit"
    finally:
        control.close()


def test_cli_issue_audit_credential_is_not_a_once_only_ritual(platform: types.SimpleNamespace) -> None:
    """Unlike `bootstrap`, any number of audit credentials may be issued --
    there is no "first row" invariant to protect here."""
    first = _run_cli(platform, "issue-audit-credential")
    second = _run_cli(platform, "issue-audit-credential")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_id, _ = _parse_issued(first.stdout)
    second_id, _ = _parse_issued(second.stdout)
    assert first_id != second_id


def test_cli_freeze_issuance_then_unfreeze_round_trips(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("fz")
    _register_application_only(platform, slug)

    def _read_frozen() -> bool:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT issuance_frozen FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "applications")),
                    [slug],
                )
                row = cur.fetchone()
        assert row is not None
        return bool(row[0])

    assert _read_frozen() is False  # NOT NULL DEFAULT false

    frozen = _run_cli(platform, "freeze-issuance", slug)
    assert frozen.returncode == 0, frozen.stderr
    assert "frozen" in frozen.stdout
    assert _read_frozen() is True

    unfrozen = _run_cli(platform, "unfreeze-issuance", slug)
    assert unfrozen.returncode == 0, unfrozen.stderr
    assert _read_frozen() is False


def test_cli_freeze_issuance_unknown_application_fails_closed(platform: types.SimpleNamespace) -> None:
    result = _run_cli(platform, "freeze-issuance", "definitely_not_registered_xyz")
    assert result.returncode != 0


def test_cli_freeze_issuance_writes_control_audit_row(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("fa")
    _register_application_only(platform, slug)
    result = _run_cli(platform, "freeze-issuance", slug)
    assert result.returncode == 0, result.stderr

    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT operation, target_kind, application_id, target_id, outcome FROM {table} "
                    "WHERE operation = 'freeze_issuance' AND application_id = %s"
                ).format(table=sql.Identifier(platform.schema, "control_audit")),
                [slug],
            )
            rows = cur.fetchall()
    assert len(rows) == 1
    operation, target_kind, application_id, target_id, outcome = rows[0]
    assert target_kind == "application"
    assert application_id == slug
    assert target_id == slug
    assert outcome == "allow"


def test_control_credential_locked_by_must_rotate_still_authenticates_and_rotate_clears_it(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """C-15 vector 3's store-level half (the HTTP-layer must_rotate *gate*
    -- refusing every operation except capabilities/self-rotate -- is
    `ControlPlaneService`'s job, WP-3; this WP only guarantees the store
    correctly persists/exposes `must_rotate` and that rotating clears it,
    which is what a future WP-3 gate will read)."""
    info = _provision_platform(tmp_path_factory)
    try:
        bootstrapped = _run_cli(info, "bootstrap")
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        credential_id, secret = _parse_issued(bootstrapped.stdout)

        control = _control_store(info)
        try:
            context = control.authenticate(secret)
            assert context.must_rotate is True
            canonical = control.assert_active(context)
            assert canonical.must_rotate is True
        finally:
            control.close()

        rotated = _run_cli(info, "rotate-control-credential", credential_id)
        assert rotated.returncode == 0, rotated.stderr
        _rotated_id, new_secret = _parse_issued(rotated.stdout)

        control = _control_store(info)
        try:
            context = control.authenticate(new_secret)
            assert context.must_rotate is False
        finally:
            control.close()
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


def test_without_the_ritual_lock_two_concurrent_existence_checks_both_see_no_row(platform: types.SimpleNamespace) -> None:
    """MA-3/M9 (round-2 review): deterministically demonstrates, via two
    real PostgreSQL connections with manually controlled statement
    ordering (no thread timing involved -- the interleaving below is
    exactly what this test's own statement order dictates, not a race
    against the clock), the exact TOCTOU window `ops._lock_ritual` exists
    to close. Both "bootstrap attempts" below run their existence check
    with no advisory lock held; under ordinary read-committed isolation
    (PostgreSQL's default -- no special setup needed), the second
    connection's check does not see the first connection's still-open,
    uncommitted transaction, so both observe "no row" and both inserts
    succeed -- leaving two live control-credential rows, exactly the
    invariant `cmd_bootstrap` exists to prevent (§8 M-6/R-5: "issuance is
    bootstrap/reset only, at most once").

    This exercises the store-level mechanism directly, not a real
    concurrent `python -m r2db_api.ops bootstrap` subprocess race: making
    that literal scenario deterministic would require adding test-only
    timing hooks to `cmd_bootstrap` itself (invasive, and not something
    production code should carry for testability alone). The WP-2
    implementation report's Round 2 section records this as the "M9"
    mutation's disposition: applying M9 (removing `_lock_ritual` from
    `cmd_bootstrap`) does not turn any *existing* test red, because no test
    drives genuine concurrent CLI invocations -- this test is the review-
    evidence boundary the round-2 fix order itself anticipated or that
    exact case, demonstrating precisely what the lock (present, unmutated,
    in the real `cmd_bootstrap`) closes.
    """
    store_a = _control_store(platform)
    store_b = _control_store(platform)
    try:
        credential_id_a = "ctl_" + secrets.token_hex(8)
        credential_id_b = "ctl_" + secrets.token_hex(8)

        # `include_revoked=False` (a "does any *live* row exist" reading)
        # deliberately, rather than `include_revoked=True` -- this test's
        # platform fixture is shared with every other test in this module
        # (several of which add their own control credentials to the same
        # table), so the table is not guaranteed empty here. What this test
        # demonstrates does not depend on the table's prior contents: the
        # race is that B's check does not observe A's still-open insert,
        # regardless of what else the table already holds -- proven below
        # by confirming both of *this test's own* new rows land, not by any
        # claim about the table's starting state.
        with store_a.unit_of_work() as work_a:
            store_a.has_any(include_revoked=True, work=work_a)
            with store_b.unit_of_work() as work_b:
                # Read-committed: B's check does not see A's still-open,
                # uncommitted transaction -- deterministic, not a fluke.
                store_b.has_any(include_revoked=True, work=work_b)
                store_b.add(credential_id_b, "secret-race-b", work=work_b)
            # work_b committed here (the nested `with` block above exited).
            store_a.add(credential_id_a, "secret-race-a", work=work_a)
        # work_a committed here -- both inserts succeeded: the race.

        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT credential_id FROM {table} WHERE credential_id = ANY(%s)").format(
                        table=sql.Identifier(platform.schema, "control_credentials")
                    ),
                    [[credential_id_a, credential_id_b]],
                )
                found = {row[0] for row in cur.fetchall()}
        assert found == {credential_id_a, credential_id_b}, (
            f"without a serializing lock, both concurrent existence-check-then-insert attempts must succeed -- found {found!r}"
        )
    finally:
        store_a.close()
        store_b.close()


def test_control_credentials_locked_scan_serializes_against_a_concurrent_scan(platform: types.SimpleNamespace) -> None:
    """WP-3 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3, WP-0
    MA-2): the same deterministic, manually-sequenced-real-connections
    technique as this module's own `test_without_the_ritual_lock_two_
    concurrent_existence_checks_both_see_no_row` immediately above -- no
    thread timing involved -- proving the POSITIVE property that precedent
    test proves the ABSENCE of: `PostgresControlCredentialStore.list_all_
    for_update`, the read `ControlPlaneService.revoke_credential`'s
    last-active-control-credential gate uses inside its own `control_
    credentials_unit_of_work` (`_body`'s own real call sequence, `control_
    plane.py`), genuinely locks every control-credential row (`FOR UPDATE`,
    no `WHERE`) for the remainder of that transaction.

    This is the exact property that closes the TOCTOU window WP-0 MA-2
    describes: without it (an unlocked `list_all()` read, or this same read
    taken BEFORE `control_credentials_unit_of_work` even opens -- design's
    own mutation-injection completion condition (vi), "gate 判定を uow 外
    へ"), two concurrent revokes of the last two active control credentials
    could each independently observe "count = 2" and both proceed
    unconfirmed, leaving zero active control credentials with neither
    revoke ever having been asked to confirm anything.

    Demonstrated with a short `lock_timeout` on the second connection
    (turning contention into an immediate, deterministic `LockNotAvailable`
    rather than a real hang, exactly like `test_control_plane_service.py`'s
    own `_run_state_change` `psycopg.errors.LockNotAvailable` handling
    already anticipates for this exact statement shape) -- first while the
    first connection's transaction is still open (must raise), then again
    after it commits (must succeed immediately, proving the block was the
    lock and not some unrelated contention).
    """
    store_a = _control_store(platform)
    table = sql.Identifier(platform.schema, "control_credentials")
    lock_statement = sql.SQL("SELECT credential_id FROM {table} FOR UPDATE").format(table=table)
    try:
        credential_id = "ctl_" + secrets.token_hex(8)
        with store_a.unit_of_work() as work_a:
            store_a.add(credential_id, "secret-lockscan-" + secrets.token_hex(4), work=work_a)

        with store_a.unit_of_work() as work_a:
            # Mirrors `_body`'s own real call: locks every row for the
            # remainder of THIS transaction.
            store_a.list_all_for_update(work_a)

            with psycopg.connect(platform.control_dsn) as conn_b:
                conn_b.autocommit = False
                with conn_b.cursor() as cur:
                    cur.execute("SET lock_timeout = '250ms'")
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    with conn_b.cursor() as cur:
                        cur.execute(lock_statement)
                conn_b.rollback()
            # work_a commits here (the `with store_a.unit_of_work()` block
            # exits) -- the lock is released.

        # Identical statement, fresh connection, no contention: succeeds
        # immediately now that work_a's transaction has ended.
        with psycopg.connect(platform.control_dsn) as conn_c:
            with conn_c.cursor() as cur:
                cur.execute("SET lock_timeout = '250ms'")
                cur.execute(lock_statement)
            conn_c.commit()
    finally:
        store_a.close()


# ===========================================================================
# Section D: 0002-revision provisioning round trip -- work order §6 item 3.
# ===========================================================================


def test_operator_first_flow_no_pre_registered_row_still_provisions_normally(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pf")
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(platform.control_dsn, platform.provision_script, {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password})
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT database_name, provisioned_at IS NOT NULL FROM {table} WHERE application_slug = %s").format(
                        table=sql.Identifier(platform.schema, "applications")
                    ),
                    [slug],
                )
                row = cur.fetchone()
        assert row is not None
        assert row[0] == f"{platform.prefix}_app_{slug}"
        assert row[1] is True
    finally:
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})


def test_registered_row_provisioning_completes_via_update_then_0003_finishes(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pg")
    _register_application_only(platform, slug)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(platform.control_dsn, platform.provision_script, {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password})
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT database_name, runtime_role, developer_role, provisioned_at IS NOT NULL FROM {table} WHERE application_slug = %s").format(
                        table=sql.Identifier(platform.schema, "applications")
                    ),
                    [slug],
                )
                row = cur.fetchone()
        assert row is not None
        assert row[0] == f"{platform.prefix}_app_{slug}"
        assert row[1] == f"{platform.prefix}_app_{slug}_runtime"
        assert row[2] == f"{platform.prefix}_app_{slug}_developer"
        assert row[3] is True
    finally:
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})


def test_provisioned_application_reprovision_raises(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ph")
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(platform.control_dsn, platform.provision_script, {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password})
    try:
        with pytest.raises(RuntimeError, match="already provisioned"):
            _run_psql(
                platform.control_dsn,
                platform.provision_script,
                {"app_slug": slug, "runtime_password": secrets.token_urlsafe(24), "developer_password": secrets.token_urlsafe(24)},
            )
    finally:
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})


def test_registered_only_application_deprovision_raises_and_touches_nothing(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pi")
    _register_application_only(platform, slug)
    with pytest.raises(RuntimeError, match="not provisioned"):
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT database_name FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "applications")),
                [slug],
            )
            row = cur.fetchone()
    assert row is not None and row[0] is None, "registered-only row must be untouched by the refused deprovision attempt"


def test_begin_alone_against_a_registered_row_leaves_it_registered_only_crash_window(platform: types.SimpleNamespace) -> None:
    """Ruling (B) (round-2 review): `begin_provision_application` writes
    NOTHING to `applications` in any case now -- calling it alone (without
    the rest of 0003 following through to `finish_provision_application`,
    simulating a crash between the two) against a registered-only row must
    leave that row exactly as it was: all four provisioning columns still
    NULL. This is the crash-safety property ruling (B) restores identically
    for both the operator-first and registered-row flows (see 0006's own
    header comment on `begin_provision_application`).

    "main.py still refuses to serve it" (the other half of this scenario,
    per the round-2 review) is not re-tested here with a second `r2db_api.
    main` import: `main.py`'s check is a pure function of `database_name IS
    NOT NULL`, and `test_credential_persistence.py::test_build_app_
    registered_only_slug_raises` already exercises that exact check against
    a registered-only row -- it does not matter *how* the row became
    registered-only (a plain registration INSERT, or -- as here -- a crashed
    `begin` call), the row shape `main.py` reads is identical either way.
    Re-importing `r2db_api.main` fresh in this file would risk depending on
    which test file's module-level `app = build_app()` import happens first
    across the whole pytest session -- not worth the risk for a check that
    is already covered structurally.
    """
    slug = _fresh_slug("cw")
    _register_application_only(platform, slug)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {fn}(%s, %s, %s)").format(fn=sql.Identifier(platform.schema, "begin_provision_application")),
                [slug, runtime_password, developer_password],
            )
            computed_database_name, runtime_role, developer_role = cur.fetchone()
        conn.commit()
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT database_name, runtime_role, developer_role, provisioned_at FROM {table} WHERE application_slug = %s").format(
                        table=sql.Identifier(platform.schema, "applications")
                    ),
                    [slug],
                )
                row = cur.fetchone()
        assert row == (None, None, None, None), f"begin alone must leave a registered-only row untouched, got {row!r}"
    finally:
        # `begin_provision_application` really did create these two login
        # roles (its one side effect, `CREATE ROLE`, unconditional) -- clean
        # them up directly since no `finish`/0004 ever ran for this slug.
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role)))
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(developer_role)))
            conn.commit()


def test_finish_completes_a_registration_that_arrived_between_begin_and_finish(platform: types.SimpleNamespace) -> None:
    """Ruling (B) (round-2 review): the masking case the round-1 `ON
    CONFLICT (application_slug) DO NOTHING` revision would have gotten
    wrong. `begin_provision_application` sees "no row at all" (operator-
    first path) and writes nothing; before `finish_provision_application`
    runs, a registration lands for the *same* slug (simulated here via
    direct SQL -- a stand-in for a future `/control/v1 POST /applications`
    landing concurrently, WP-3+). `finish` must still complete that row
    (`UPDATE ... WHERE database_name IS NULL` matches it) -- never silently
    leave it registered-only because a naive `INSERT` would have conflicted
    on `application_slug`.
    """
    slug = _fresh_slug("fm")
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {fn}(%s, %s, %s)").format(fn=sql.Identifier(platform.schema, "begin_provision_application")),
                [slug, runtime_password, developer_password],
            )
            database_name, runtime_role, developer_role = cur.fetchone()
        conn.commit()
    try:
        # A registration "arrives" for the same slug, between begin and
        # finish, from -- structurally -- an entirely different actor.
        _register_application_only(platform, slug)

        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT {fn}(%s, %s, %s, %s)").format(fn=sql.Identifier(platform.schema, "finish_provision_application")),
                    [slug, database_name, runtime_role, developer_role],
                )
            conn.commit()

        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT database_name, runtime_role, developer_role, provisioned_at IS NOT NULL FROM {table} WHERE application_slug = %s").format(
                        table=sql.Identifier(platform.schema, "applications")
                    ),
                    [slug],
                )
                row = cur.fetchone()
        assert row == (database_name, runtime_role, developer_role, True), (
            f"finish must complete the row that arrived between begin and finish, never mask it as registered-only, got {row!r}"
        )
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role)))
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(developer_role)))
            conn.commit()


def test_check_constraint_rejects_a_half_filled_row(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("pj")
    statement = sql.SQL("INSERT INTO {table} (application_slug, database_name) VALUES (%s, %s)").format(
        table=sql.Identifier(platform.schema, "applications")
    )
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.CheckViolation):
                cur.execute(statement, [slug, "half_filled_db"])
        conn.rollback()


def test_0006_migration_is_idempotent(platform: types.SimpleNamespace) -> None:
    _run_psql(platform.control_dsn, platform.control_plane_sql, {"controlplane_password": platform.controlplane_password})
    # Re-running left the two-state CHECK, the new tables, and the
    # controlplane role/grants exactly as before: a fresh registered-only
    # row followed by provisioning still round-trips.
    slug = _fresh_slug("pk")
    _register_application_only(platform, slug)
    _run_psql(platform.control_dsn, platform.provision_script, {"app_slug": slug, "runtime_password": secrets.token_urlsafe(24), "developer_password": secrets.token_urlsafe(24)})
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT database_name IS NOT NULL FROM {table} WHERE application_slug = %s").format(table=sql.Identifier(platform.schema, "applications")),
                    [slug],
                )
                assert cur.fetchone() == (True,)
    finally:
        _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})


def test_credential_issuance_succeeds_for_registered_unprovisioned_application(platform: types.SimpleNamespace) -> None:
    """R-4: a registered-but-not-yet-provisioned application can still have
    application credentials issued against it (the credential can
    authenticate; whether the request then reaches a real database is a
    separate, serving-time concern -- `main.py`'s own new check, tested in
    `test_credential_persistence.py`)."""
    slug = _fresh_slug("pl")
    _register_application_only(platform, slug)
    store = _write_app_store(platform)
    try:
        credential_id = "crd_" + secrets.token_hex(8)
        with store.unit_of_work() as work:
            store.add(credential_id, slug, "runtime", "secret-unprovisioned", work=work)
        context = store.authenticate(compose_bearer_locator(credential_id, "secret-unprovisioned"))
        assert context.application_id == slug
    finally:
        store.close()


# ===========================================================================
# Section E: GRANT verification for r2dbsvc_controlplane -- work order §6
# item 4 (R-3 is "本設計の安全の要" -- required, not optional).
# ===========================================================================


def test_controlplane_role_grants_match_the_design(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("gr")
    _register_application(platform, slug)

    def _denied(dsn: str, sql_text: str, params: list | None = None) -> bool:
        try:
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_text, params or [])
        except psycopg.errors.InsufficientPrivilege:
            return True
        except psycopg.Error:
            # Any other error (e.g. a benign FK/constraint issue on an
            # otherwise-permitted statement) is not what this test is
            # checking for -- re-raise so it surfaces as a real failure.
            raise
        return False

    applications_table = f'"{platform.schema}"."applications"'
    credentials_table = f'"{platform.schema}"."credentials"'
    control_credentials_table = f'"{platform.schema}"."control_credentials"'
    control_audit_table = f'"{platform.schema}"."control_audit"'

    # --- r2dbsvc_controlplane: must be refused (permission denied) ---
    assert _denied(platform.controlplane_dsn, f"INSERT INTO {control_credentials_table} (credential_id, verifier) VALUES ('ctl_denied', 'v')"), "control_credentials INSERT must be denied to r2dbsvc_controlplane"
    assert _denied(platform.controlplane_dsn, f"DELETE FROM {applications_table} WHERE application_slug = %s", [slug]), "applications DELETE must be denied to r2dbsvc_controlplane"
    assert _denied(platform.controlplane_dsn, f"DELETE FROM {credentials_table}"), "credentials DELETE must be denied to r2dbsvc_controlplane"
    assert _denied(platform.controlplane_dsn, f"UPDATE {control_audit_table} SET outcome = 'x'"), "control_audit UPDATE must be denied to r2dbsvc_controlplane"
    assert _denied(platform.controlplane_dsn, f"DELETE FROM {control_audit_table}"), "control_audit DELETE must be denied to r2dbsvc_controlplane"
    assert _denied(
        platform.controlplane_dsn,
        f'SELECT * FROM "{platform.schema}".begin_provision_application(%s, %s, %s)',
        ["gr_denied", "x" * 20, "x" * 20],
    ), "begin_provision_application EXECUTE must be denied to r2dbsvc_controlplane"
    # MA-2 (round-2 review): r2dbsvc_controlplane can INSERT into control_audit
    # (append-only, verified below) but must never be able to read it back --
    # append-only means the *writer itself* cannot see what it wrote, not
    # merely that it cannot alter/erase it.
    assert _denied(platform.controlplane_dsn, f"SELECT * FROM {control_audit_table}"), "control_audit SELECT must be denied to r2dbsvc_controlplane"

    # MA-1 (round-2 review): R-2's central claim -- the application-plane
    # read-only role (r2dbsvc_api, the role the running API process itself
    # authenticates as) can read neither control-plane storage table at all.
    # A compromised application-plane process cannot even read a control
    # credential's verifier or a single control_audit row.
    assert _denied(platform.api_dsn, f"SELECT * FROM {control_credentials_table}"), "control_credentials SELECT must be denied to r2dbsvc_api"
    assert _denied(platform.api_dsn, f"SELECT * FROM {control_audit_table}"), "control_audit SELECT must be denied to r2dbsvc_api"

    # --- r2dbsvc_controlplane: must succeed ---
    with psycopg.connect(platform.controlplane_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {control_audit_table} (event_id, event_class, occurred_at, request_id, actor_type, operation, outcome) "
                "VALUES (gen_random_uuid(), 'x', now(), 'r', 'operator_cli', 'op', 'allow')"
            )
        conn.commit()
    with psycopg.connect(platform.controlplane_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {control_credentials_table} SET enabled = false WHERE credential_id = 'no-such-row'")
        conn.commit()  # 0-row UPDATE succeeding proves the privilege, not any row change


# ===========================================================================
# Section F: existing subcommand audit -- work order §6 item 7.
# ===========================================================================


def _control_audit_rows_for_operation(platform: types.SimpleNamespace, operation: str) -> list[tuple]:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT event_class, actor_type, actor_id, outcome, application_id FROM {table} WHERE operation = %s ORDER BY recorded_at DESC LIMIT 5").format(
                    table=sql.Identifier(platform.schema, "control_audit")
                ),
                [operation],
            )
            return cur.fetchall()


def test_cli_issue_credential_writes_control_audit_row_with_no_secret_anywhere(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("aa")
    _register_application(platform, slug)
    # Distinguish this test's own row from others' via a fresh slug value
    # used as `application_id` -- simplest unique marker without needing a
    # dedicated operation name column trick.
    result = _run_cli(platform, "issue-credential", slug, "runtime")
    assert result.returncode == 0, result.stderr
    _credential_id, secret = _parse_issued(result.stdout)

    rows = _control_audit_rows_for_operation(platform, "issue_credential")
    matching = [row for row in rows if row[4] == slug]
    assert len(matching) == 1, f"expected exactly one control_audit row for slug {slug!r}, found {matching}"
    event_class, actor_type, actor_id, outcome, application_id = matching[0]
    assert event_class == "credential_lifecycle"
    assert actor_type == "operator_cli"
    assert actor_id is None
    assert outcome == "allow"
    assert application_id == slug

    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {table}").format(table=sql.Identifier(platform.schema, "control_audit")))
            columns = [desc.name for desc in cur.description]
            all_rows = cur.fetchall()
    for row in all_rows:
        for column, value in zip(columns, row):
            if isinstance(value, str):
                assert secret not in value, f"secret leaked into control_audit.{column}"


def test_cli_revoke_credential_writes_control_audit_row(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ab")
    _register_application(platform, slug)
    issued = _run_cli(platform, "issue-credential", slug, "runtime")
    assert issued.returncode == 0, issued.stderr
    credential_id, _secret = _parse_issued(issued.stdout)

    revoked = _run_cli(platform, "revoke-credential", credential_id)
    assert revoked.returncode == 0, revoked.stderr

    rows = _control_audit_rows_for_operation(platform, "revoke_credential")
    assert len(rows) >= 1
    event_class, actor_type, actor_id, outcome, _application_id = rows[0]
    assert event_class == "credential_lifecycle"
    assert actor_type == "operator_cli"
    assert actor_id is None
    assert outcome == "allow"


def test_cli_disable_app_writes_control_audit_row(platform: types.SimpleNamespace) -> None:
    slug = _fresh_slug("ac")
    _register_application(platform, slug)

    disabled = _run_cli(platform, "disable-app", slug)
    assert disabled.returncode == 0, disabled.stderr

    rows = _control_audit_rows_for_operation(platform, "disable_application")
    matching = [row for row in rows if row[4] == slug]
    assert len(matching) == 1
    event_class, actor_type, actor_id, outcome, application_id = matching[0]
    assert event_class == "application_lifecycle"
    assert actor_type == "operator_cli"
    assert actor_id is None
    assert outcome == "allow"
    assert application_id == slug

    # Restore for hygiene (other tests may share this platform's registry).
    _run_cli(platform, "enable-app", slug)


# ===========================================================================
# Section G: `audit-report` (R-11 compromise/misuse playbook helper) --
# work order §C ("audit-report の仕様確定" / "テスト + 変異注入").
# ===========================================================================


def _insert_control_audit_row(
    platform: types.SimpleNamespace,
    *,
    occurred_at: datetime,
    operation: str,
    event_class: str = "control_credential_lifecycle",
    outcome: str = "allow",
    application_id: str | None = None,
    actor_type: str = "operator_cli",
    actor_id: str | None = None,
    role: str | None = None,
    target_kind: str | None = None,
    reason_code: str | None = None,
    event_id: str | None = None,
    target_id: str | None = None,
) -> str:
    """Inserts one `control_audit` row directly (as `r2dbsvc_control`, this
    schema's owner -- full DML), with an explicit, caller-chosen
    `occurred_at` -- unlike the real ritual/CLI/service code (which always
    stamps `occurred_at = now()`), `audit-report`'s own boundary/ordering
    behaviour needs precise, deterministic timestamps, not real wall-clock
    delay. Returns the `event_id` (string) so callers can assert exactly
    which rows a report line corresponds to. `event_id` may be supplied by
    the caller (WP-6 review MI-3: the `event_id` ASC tiebreaker test needs
    to control which of two identical-`occurred_at` rows sorts first,
    independent of uuid4's own randomness) -- defaults to a fresh `uuid4()`
    when omitted, as before.

    Phase 3.5 WP-4 (design §1-C/§4): `target_id` -- the contract's 13th,
    optional `audit.fields` member (0006's own nullable column) -- defaults
    to `None` (omitted), same as every other optional column here.
    """
    event_id = event_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    statement = sql.SQL(
        "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
        "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    ).format(table=sql.Identifier(platform.schema, "control_audit"))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                statement,
                [event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id],
            )
        conn.commit()
    return event_id


def _run_audit_report(platform: types.SimpleNamespace, since: str, until: str | None = None) -> subprocess.CompletedProcess:
    args = ["audit-report", "--since", since]
    if until is not None:
        args += ["--until", until]
    return _run_cli(platform, *args)


def _parse_jsonl(stdout: str) -> list[dict]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _synthetic_window() -> datetime:
    """A random base timestamp decades in the past, so each test's own
    synthetic `control_audit` rows never collide -- inside the narrow
    `--since`/`--until` bound that test asserts against -- with another
    test's rows (this module's other sections write real `now()`-stamped
    rows throughout a full test run; sibling tests in this section each
    pick their own random base too)."""
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=secrets.randbelow(200_000_000))


def test_audit_report_filters_since_and_until_inclusive_boundaries(platform: types.SimpleNamespace) -> None:
    t0 = _synthetic_window()
    before = t0 - timedelta(seconds=1)
    at_since = t0
    middle = t0 + timedelta(seconds=30)
    at_until = t0 + timedelta(seconds=60)
    after = t0 + timedelta(seconds=61)

    marker = "arb" + secrets.token_hex(4)
    id_before = _insert_control_audit_row(platform, occurred_at=before, operation=marker)
    id_since = _insert_control_audit_row(platform, occurred_at=at_since, operation=marker)
    id_middle = _insert_control_audit_row(platform, occurred_at=middle, operation=marker)
    id_until = _insert_control_audit_row(platform, occurred_at=at_until, operation=marker)
    id_after = _insert_control_audit_row(platform, occurred_at=after, operation=marker)

    result = _run_audit_report(platform, at_since.isoformat(), at_until.isoformat())
    assert result.returncode == 0, result.stderr
    own = [r for r in _parse_jsonl(result.stdout) if r["operation"] == marker]
    ids = [r["event_id"] for r in own]

    # Inclusive on both ends ("in [--since, --until]"): `before`/`after` are
    # excluded, `at_since`/`middle`/`at_until` are included.
    assert id_before not in ids
    assert id_after not in ids
    assert ids == [id_since, id_middle, id_until]


def test_audit_report_orders_ascending_by_occurred_at_regardless_of_insertion_order(platform: types.SimpleNamespace) -> None:
    t0 = _synthetic_window()
    marker = "aro" + secrets.token_hex(4)
    # Insert deliberately out of chronological order.
    id_late = _insert_control_audit_row(platform, occurred_at=t0 + timedelta(seconds=20), operation=marker)
    id_early = _insert_control_audit_row(platform, occurred_at=t0, operation=marker)
    id_mid = _insert_control_audit_row(platform, occurred_at=t0 + timedelta(seconds=10), operation=marker)

    result = _run_audit_report(platform, t0.isoformat(), (t0 + timedelta(seconds=25)).isoformat())
    assert result.returncode == 0, result.stderr
    own = [r for r in _parse_jsonl(result.stdout) if r["operation"] == marker]
    assert [r["event_id"] for r in own] == [id_early, id_mid, id_late]


def test_audit_report_emits_one_json_object_per_line_with_contract_fields(platform: types.SimpleNamespace) -> None:
    t0 = _synthetic_window()
    marker = "arf" + secrets.token_hex(4)
    slug = _fresh_slug("ar")
    event_id = _insert_control_audit_row(
        platform, occurred_at=t0, operation=marker, event_class="application_lifecycle",
        application_id=slug, target_kind="application", outcome="allow", target_id=slug,
    )
    result = _run_audit_report(platform, t0.isoformat(), t0.isoformat())
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    own_lines = [line for line in lines if marker in line]
    # One JSON object per line (JSON Lines) -- never a single wrapping array.
    assert len(own_lines) == 1
    assert not own_lines[0].lstrip().startswith("[")
    record = json.loads(own_lines[0])
    assert record["event_id"] == event_id
    assert record["event_class"] == "application_lifecycle"
    assert record["application_id"] == slug
    assert record["operation"] == marker
    assert record["outcome"] == "allow"
    assert record["target_kind"] == "application"
    # Phase 3.5 WP-4 (design §1-C/§4): `target_id` now appears in the report
    # too -- the "no target_id field" caveat this docstring/test used to
    # carry is resolved.
    assert record["target_id"] == slug
    # Both timestamps present and ISO-8601-parseable -- `recorded_at` (the
    # table's own DB-side insertion time) is distinct from `occurred_at` and
    # both round-trip through this report.
    datetime.fromisoformat(record["occurred_at"])
    datetime.fromisoformat(record["recorded_at"])


def test_audit_report_omitted_until_has_no_upper_bound(platform: types.SimpleNamespace) -> None:
    t0 = _synthetic_window()
    marker = "aru" + secrets.token_hex(4)
    id_a = _insert_control_audit_row(platform, occurred_at=t0, operation=marker)
    id_far = _insert_control_audit_row(platform, occurred_at=t0 + timedelta(days=3650), operation=marker)

    result = _run_audit_report(platform, t0.isoformat())
    assert result.returncode == 0, result.stderr
    own = [r for r in _parse_jsonl(result.stdout) if r["operation"] == marker]
    ids = {r["event_id"] for r in own}
    assert {id_a, id_far} <= ids


def test_audit_report_rejects_until_before_since(platform: types.SimpleNamespace) -> None:
    t0 = _synthetic_window()
    result = _run_audit_report(platform, t0.isoformat(), (t0 - timedelta(seconds=1)).isoformat())
    assert result.returncode != 0
    assert "--until" in (result.stderr or "")


def test_audit_report_requires_since() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", "audit-report"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    assert result.returncode != 0
    assert "--since" in (result.stderr or "")


def test_audit_report_rejects_non_iso8601_since() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "r2db_api.ops", "audit-report", "--since", "not-a-timestamp"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    assert result.returncode != 0
    assert "--since" in (result.stderr or "")


def test_audit_report_ties_break_by_event_id_ascending(platform: types.SimpleNamespace) -> None:
    """WP-6 review MI-3(a): two rows sharing the exact same `occurred_at`
    must sort by `event_id` ascending (matching `PostgresControlAuditSink.
    events()`'s own tiebreaker), never by insertion order. Deliberately
    inserts the lexicographically-larger id FIRST -- a "drop the tiebreaker,
    keep only `ORDER BY occurred_at`" mutation degrades to a plan-dependent
    order (typically insertion/physical order for a plain heap scan on a
    small table), which disagrees with ascending `event_id` exactly because
    of this insertion order."""
    t0 = _synthetic_window()
    marker = "att" + secrets.token_hex(4)
    id_high = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    id_low = "00000000-0000-4000-8000-000000000001"
    inserted_high = _insert_control_audit_row(platform, occurred_at=t0, operation=marker, event_id=id_high)
    inserted_low = _insert_control_audit_row(platform, occurred_at=t0, operation=marker, event_id=id_low)
    assert (inserted_high, inserted_low) == (id_high, id_low)

    result = _run_audit_report(platform, t0.isoformat(), t0.isoformat())
    assert result.returncode == 0, result.stderr
    own = [r for r in _parse_jsonl(result.stdout) if r["operation"] == marker]
    assert [r["event_id"] for r in own] == [id_low, id_high]


def test_audit_report_naive_since_is_interpreted_as_utc(platform: types.SimpleNamespace) -> None:
    """WP-6 review MI-3(b): a `--since` with no timezone offset/`Z` suffix
    must be treated as UTC, not left for PostgreSQL to interpret against the
    session's own default `TimeZone` -- this local test cluster's default
    session TimeZone is `Asia/Tokyo` (UTC+9, confirmed via `SHOW TimeZone`),
    so a client-side bug that stopped forcing a naive value to UTC before
    binding it would send an untyped/naive parameter that PostgreSQL then
    casts to `timestamptz` using that +9 offset -- shifting the effective
    boundary 9 hours away from the intended instant, decisively wrong for
    this test's own once-per-second-scale rows near `t0`."""
    t0 = _synthetic_window()
    marker = "atz" + secrets.token_hex(4)
    id_since = _insert_control_audit_row(platform, occurred_at=t0, operation=marker)
    id_before = _insert_control_audit_row(platform, occurred_at=t0 - timedelta(seconds=1), operation=marker)

    naive_since = t0.replace(tzinfo=None).isoformat()
    assert "+" not in naive_since and "Z" not in naive_since and "-0" not in naive_since[-6:]

    result = _run_audit_report(platform, naive_since)
    assert result.returncode == 0, result.stderr
    own = [r for r in _parse_jsonl(result.stdout) if r["operation"] == marker]
    ids = {r["event_id"] for r in own}
    assert id_since in ids
    assert id_before not in ids


def test_audit_report_does_not_modify_control_audit(platform: types.SimpleNamespace) -> None:
    """WP-6 review MI-3(c): `audit-report` is read-only -- a row count taken
    immediately before and after running it must be identical."""

    def _count() -> int:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SELECT count(*) FROM {table}").format(table=sql.Identifier(platform.schema, "control_audit")))
                return cur.fetchone()[0]

    t0 = _synthetic_window()
    marker = "aro2" + secrets.token_hex(4)
    _insert_control_audit_row(platform, occurred_at=t0, operation=marker)
    before = _count()
    result = _run_audit_report(platform, t0.isoformat())
    assert result.returncode == 0, result.stderr
    after = _count()
    assert after == before, "audit-report must not write any control_audit row (read-only)"


# ===========================================================================
# Coordinator item 3 / item 7(i) (2026-09-04 review) -- structural (white-
# box) pins that a functional-outcome test cannot express: composition
# LOCATION discipline, and unconditional `compare_digest` usage.
# ===========================================================================


def test_in_process_adapter_never_composes_the_bearer_itself() -> None:
    """Coordinator item 3: `conformance_adapter_r2db.py`'s own privileged-
    setup `issue_credential` port method must present `ControlAuthority.
    issue_credential`'s ALREADY-COMPOSED return value verbatim -- it must
    never call `compose_bearer_locator` itself (design D-1(c) "合成は
    store/service 層のみ" -- adapter is a verbatim consumer, port v1.10
    (a)). A source-text pin: the conformance suite's own AST-based
    `test_c19_adapters_never_compose_or_decompose_the_bearer_secret`
    (`conformance-tests/test_c19_client_self_sufficiency.py`) only
    recognizes f-string/`+`/`.join` composition, not a named helper call --
    it would NOT have caught the exact violation this rework fixes (audit
    finding (d)), so this repository's own local suite carries this
    narrower, exact-string pin instead."""
    source = (Path(__file__).resolve().parents[1] / "conformance" / "conformance_adapter_r2db.py").read_text()
    assert "compose_bearer_locator" not in source, (
        "conformance_adapter_r2db.py references compose_bearer_locator -- the adapter must present "
        "issuance responses verbatim, never compose the bearer itself (coordinator item 3)"
    )


# ---------------------------------------------------------------------------
# Phase 6 WP-3 追補 (isomorphism table extension, supervisor ruling
# 2026-09-04): `test_authenticate_methods_use_the_shared_dummy_verifier_
# for_unconditional_compare_digest` below is now a row in `tests/test_
# audit_query.py::_ISOMORPHIC_TARGETS` (pinned isomorphic to MitateDB-
# api's own same-named test in its own `tests/test_control_plane_store.
# py`). The two peers' `authenticate` implementations live under
# DIFFERENT file/class names -- this peer's 4 live across 2 files
# (`auth.py`'s 2 in-memory classes, `credential_store.py`'s 2 Postgres
# classes), MitateDB-api's own 4 live across 4 files (one class per file:
# `auth.py`, `control_auth.py`, `credential_store_postgres.py`,
# `control_credential_store_postgres.py`) -- a real per-peer module-
# layout difference, not a naming accident, and NOT something package-
# name substitution alone can normalize away. This {filename: {class
# names}} map is therefore kept HERE, at module level, OUTSIDE the pinned
# function body, so the function itself stays byte-identical (after
# normalization) across both peers; only this table differs per peer.
# ---------------------------------------------------------------------------
_TIMING_PIN_TARGETS: dict[str, set[str]] = {
    "auth.py": {"CredentialStore", "ControlCredentialStore"},
    "credential_store.py": {"PostgresCredentialStore", "PostgresControlCredentialStore"},
}


def test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest() -> None:
    """Coordinator item 7(i) (reviewer O3): a structural pin for a property
    a functional-outcome test cannot express without flaky timing
    measurement -- all 4 `authenticate` implementations (`auth.py`'s two
    in-memory stores, `credential_store.py`'s two Postgres stores) must
    reference `_DUMMY_VERIFIER` so `compare_digest` runs unconditionally
    (same cost whether or not the presented `credential_id` names a real
    row), closing the "does this credential_id exist" timing oracle. This
    is a source-text pin, not a timing measurement -- a real timing attack
    test would be flaky by nature and is out of this WP's scope; this pin
    at least prevents a future edit from silently reintroducing the
    short-circuit form without touching this text."""
    # Supervisor rework (2026-09-04, audit of the WP-2 rework, item 7(i)):
    # the previous form of this pin only counted occurrences of the
    # `_DUMMY_VERIFIER` token per file (>= 2), which stayed green even when
    # both use sites in a file were reverted to the short-circuit form
    # (definition + comment still made the count) -- measured by the
    # auditor. This form reads the AST of each of the four
    # `authenticate` methods and requires, per method, at least one
    # `hmac.compare_digest(...)` call that is NOT nested inside any `if`
    # whose test mentions the looked-up row (`record` / `row`) -- i.e. the
    # digest comparison must be reached unconditionally, whether or not
    # the presented locator named a real row. Reverting any ONE of the
    # four methods to `if record is None: fail(...)` before the
    # comparison turns this red (measured, one method at a time).
    import ast

    src_root = Path(__file__).resolve().parents[1] / "src" / "r2db_api"
    targets = _TIMING_PIN_TARGETS
    row_names = {"record", "row"}

    def _mentions_row(node: ast.AST) -> bool:
        return any(isinstance(n, ast.Name) and n.id in row_names for n in ast.walk(node))

    def _unconditional_compare_digest(fn: ast.FunctionDef) -> bool:
        # Walk with an explicit parent chain so each Call knows the `if`
        # tests it sits under.
        found = False

        def visit(node: ast.AST, guarding: list[ast.If]) -> None:
            nonlocal found
            if isinstance(node, ast.Call):
                f = node.func
                is_cd = (isinstance(f, ast.Attribute) and f.attr == "compare_digest") or (isinstance(f, ast.Name) and f.id == "compare_digest")
                if is_cd and not any(_mentions_row(g.test) for g in guarding):
                    found = True
            for child in ast.iter_child_nodes(node):
                if isinstance(node, ast.If) and child in node.body + node.orelse:
                    visit(child, guarding + [node])
                else:
                    visit(child, guarding)

        visit(fn, [])
        if not found:
            return False
        # Ordering: an early `if record is None: fail(...)` BEFORE the
        # comparison is the same timing oracle in a different syntactic
        # coat (the digest is never computed for an unknown locator), so
        # no `if` whose test mentions the row may precede the first
        # compare_digest call in source order.
        first_cd = min(
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call) and (
                (isinstance(n.func, ast.Attribute) and n.func.attr == "compare_digest")
                or (isinstance(n.func, ast.Name) and n.func.id == "compare_digest")
            )
        )
        early_row_ifs = [n for n in ast.walk(fn) if isinstance(n, ast.If) and n.lineno < first_cd and _mentions_row(n.test)]
        return not early_row_ifs

    checked: list[str] = []
    for filename, class_names in targets.items():
        tree = ast.parse((src_root / filename).read_text())
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in class_names]:
            fns = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "authenticate"]
            assert len(fns) == 1, f"{filename}::{cls.name} must define exactly one authenticate()"
            assert _unconditional_compare_digest(fns[0]), (
                f"{filename}::{cls.name}.authenticate() must call hmac.compare_digest unconditionally "
                f"(not only inside an `if` that depends on whether the locator named a row)"
            )
            checked.append(f"{filename}::{cls.name}")
    assert len(checked) == 4, checked
