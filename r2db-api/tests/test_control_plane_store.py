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

from r2db_api.auth import ControlAuthContext, ControlCredentialStore, CredentialStore
from r2db_api.credential_store import PostgresControlCredentialStore, PostgresCredentialStore, validate_control_pepper_separation
from r2db_api.errors import FoundationError

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
PEPPER = "synthetic-test-pepper-control-plane-store-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-control-plane-store-ctl-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
)


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
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)

    return types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        control_role=control_role,
        api_dsn=api_dsn,
        api_role=api_role,
        controlplane_dsn=controlplane_dsn,
        controlplane_role=controlplane_role,
        platform_db=platform_db,
        schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        control_plane_sql=rewritten["0006_control_plane_http.sql"],
        api_password=api_password,
        controlplane_password=controlplane_password,
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
    context = store.authenticate("secret-uow1")
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
        with store.unit_of_work() as work:
            store.add("crd_" + secrets.token_hex(8), slug, "runtime", "secret-pguow1", work=work)
        context = store.authenticate("secret-pguow1")
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
            context = store.authenticate("secret-parity-before")
            assert isinstance(context, ControlAuthContext)
            assert context.credential_id == credential_id
            assert context.must_rotate is True  # DEFAULT true (R-5)

            with store.unit_of_work() as work:
                store.rotate(credential_id, "secret-parity-after", work=work)
            with pytest.raises(FoundationError) as exc:
                store.authenticate("secret-parity-before")
            assert exc.value.code == "AUTH_INVALID"
            context2 = store.authenticate("secret-parity-after")
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
            in_memory.authenticate("secret-approt-after")
        assert exc.value.code == "AUTH_REVOKED"
        with pytest.raises(FoundationError) as exc:
            in_memory.authenticate("secret-approt-before")
        assert exc.value.code == "AUTH_INVALID"  # old secret no longer matches at all

        pg_id = "crd_" + secrets.token_hex(8)
        with pg.unit_of_work() as work:
            pg.add(pg_id, slug, "runtime", "secret-approt-pg-before", work=work)
        with pg.unit_of_work() as work:
            pg.set_state(pg_id, revoked=True, work=work)
        with pg.unit_of_work() as work:
            pg.rotate(pg_id, "secret-approt-pg-after", work=work)  # must not raise
        with pytest.raises(FoundationError) as exc:
            pg.authenticate("secret-approt-pg-after")
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
        context = reader.authenticate("secret-propagation")
        assert context.credential_id == credential_id

        with writer.unit_of_work() as work:
            writer.set_state(credential_id, revoked=True, work=work)
        with pytest.raises(FoundationError) as exc:
            reader.authenticate("secret-propagation")
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        writer.close()
        reader.close()


def test_control_authenticate_fails_closed_when_platform_db_unreachable() -> None:
    store = PostgresControlCredentialStore(_unreachable_dsn(), pepper=CONTROL_PEPPER)
    try:
        with pytest.raises(FoundationError) as exc:
            store.authenticate("any-secret")
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
        # to the application store -- AUTH_INVALID.
        with pytest.raises(FoundationError) as exc:
            app_store.authenticate(control_secret)
        assert exc.value.code == "AUTH_INVALID"

        # Cross direction 2: the application credential's own secret,
        # presented to the control store -- AUTH_INVALID.
        with pytest.raises(FoundationError) as exc:
            control_store.authenticate(app_secret)
        assert exc.value.code == "AUTH_INVALID"

        # Each store still correctly authenticates its own credential.
        assert app_store.authenticate(app_secret).credential_id == app_credential_id
        assert control_store.authenticate(control_secret).credential_id == control_credential_id

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

        reset_result = _run_cli(info, "reset")
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
            app_context = app_reader.authenticate("secret-untouched-by-reset")
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
            faulted = _run_cli(info, "reset")
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
        recovered = _run_cli(info, "reset")
        assert recovered.returncode == 0, recovered.stderr
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


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
        context = store.authenticate("secret-unprovisioned")
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
    when omitted, as before."""
    event_id = event_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    statement = sql.SQL(
        "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
        "actor_type, actor_id, role, operation, target_kind, outcome, reason_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    ).format(table=sql.Identifier(platform.schema, "control_audit"))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                statement,
                [event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code],
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
        application_id=slug, target_kind="application", outcome="allow",
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
