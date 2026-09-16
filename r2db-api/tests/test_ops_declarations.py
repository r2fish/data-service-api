"""Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2,
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1
change table C): the 4 declaration subcommands (`set-platform-timeouts`,
`declare-surfaces`, `declare-coalescing-window`, `show-declarations`) --
placement confirmed by supervisor ruling 2026-09-05 (work order §7
prohibition 7): its own file, `tests/test_ops_declarations.py`, separate
from the upgrade-series subcommands' own `test_ops_upgrade.py` (WP-3/WP-4
territory).

Also the home for the fail-fast message string-pin tests (design §3.8,
completion condition 12, work order constant regime 4): F-1 through F-11 +
F-13 (+F-3c) copied VERBATIM from `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md`
§3.8 / `{scratchpad}/q4-f3c-and-amendments.md`, with `<peer>` -> `r2db_api`,
`<NNNN>` -> `0008` substituted (the design's own substitution rule) --
exact-equality assertions against the actual raised message, not a substring
match, so a message that drifted even slightly from the pinned text (a
paraphrase, a dropped clause, a missing `ops` command name) goes red.

REWORK ROUND (supervisor rulings 2026-09-05, rulings-q4-wp12-rework.md
sec.1/sec.2, rulings-q4-writer-roles.md D-2(h)): rewritten against the new
`platform_declarations.py` API (`conn`-based, not `dsn`-based;
`PlatformDeclarationError`, not a bare `ValueError`/`RuntimeError` mix;
`audit_writer_roles` as the SOLE source of writer-role identity, never a
naming-convention derivation) -- migration `0008` now takes `-v
api_role=... -v controlplane_role=...` and seeds `audit_writer_roles` from
those SAME two variables, in the SAME transaction as its own `ALTER ROLE`
statements (D-2(h) point 1). `ops.py`'s `set-platform-timeouts`/`show-
declarations` now source their target role set from the declared
`audit_writer_roles` row, never from `_schema()` naming-convention rewrite
(removed).
"""
from __future__ import annotations

import json
import secrets
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql

import r2db_api.ops as ops
from r2db_api.platform_declarations import (
    MIGRATION_NUMBER,
    PEER_MODULE,
    PlatformDeclarationError,
    RoleTimeoutCatalog,
    derive_visibility_lag_ms,
    read_declared_role_timeouts,
    read_platform_declarations,
    validate_audit_writer_roles_value,
    validate_coalescing_window_value,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    "0008_platform_declarations_and_writer_timeouts.sql",
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


def _dsn_with(base_dsn: str, **overrides: str):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    import subprocess

    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_ops_declarations.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            for (database,) in cur.fetchall():
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
            for (role,) in cur.fetchall():
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbopsdecl{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_ops_decl_migrations")
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
        # D-2(h) point 1: migration `0008` now takes `-v api_role=... -v
        # controlplane_role=...` -- the SAME two throwaway-prefixed role
        # names this fixture already bootstrapped above (never the
        # production literals `r2dbsvc_api`/`r2dbsvc_controlplane`, design
        # D-2(h) point 5: "逐語の本番role名をテストへ焼き付けない").
        _run_psql(control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        api_role=api_role, controlplane_role=controlplane_role, platform_db=platform_db, schema=schema,
        rewritten_migrations_dir=rewritten_dir,
        # api_password is needed by the one test that connects AS the api role:
        # under TCP + scram (CI) the password is actually checked, unlike the
        # local unix-socket trust setup that hid this omission.
        api_password=api_password,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


@pytest.fixture()
def ops_env(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Points `ops.py`'s own module-level env-reading helpers
    (`_control_dsn`/`_schema`) at this test's throwaway platform -- the
    same `R2DB_CONTROL_DSN`/`R2DB_PLATFORM_SCHEMA` a real operator's shell
    would export."""
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    return platform


def _row_value(platform: types.SimpleNamespace, key: str):
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT value FROM {table} WHERE key = %s").format(table=sql.Identifier(platform.schema, "platform_declarations")), [key])
            row = cur.fetchone()
    return row[0] if row else None


def _role_setting(platform: types.SimpleNamespace, role: str) -> dict[str, int]:
    with psycopg.connect(platform.control_dsn) as conn:
        catalog = read_declared_role_timeouts(conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    return {"statement_timeout": catalog.statement_ms, "idle_in_transaction_session_timeout": catalog.idle_ms}


@pytest.fixture()
def bare_platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """{scratchpad}/wp12-audit-gaps.md G1: a function-scoped, freshly
    bootstrapped platform distinct from the module-scoped `platform`
    fixture above. `platform` is SHARED across this whole file, and later
    tests in this module write to the declarations table (`declare-
    surfaces`/`declare-coalescing-window`) -- so asserting the `surfaces`
    row's ABSENCE against it would depend on test execution order.
    Mirrors MitateDB-api's own `tests/test_migration_0007_ddl.py::
    bare_platform` (same migrations-through-the-platform-declarations-
    migration-only shape, a distinct throwaway prefix stem so a failure
    here is never confused with `platform`'s own state)."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbbare{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_ops_decl_bare_migrations")
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
        _run_psql(
            control_dsn,
            rewritten["0008_platform_declarations_and_writer_timeouts.sql"],
            {"api_role": api_role, "controlplane_role": controlplane_role},
        )
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        api_role=api_role, controlplane_role=controlplane_role, platform_db=platform_db, schema=schema,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


# ===========================================================================
# migration 0008: audit_writer_roles seed + idempotency (completion
# condition 19)
# ===========================================================================


def test_migration_0008_seeds_audit_writer_roles_from_the_same_variables_as_alter_role(platform: types.SimpleNamespace) -> None:
    assert _row_value(platform, "audit_writer_roles") == [platform.api_role, platform.controlplane_role]


def test_migration_0008_alter_role_and_audit_writer_roles_are_idempotent_across_two_applications(platform: types.SimpleNamespace) -> None:
    """Completion condition 1/19: re-applying migration `0008` with the
    SAME `-v api_role=.../-v controlplane_role=...` variables leaves an
    IDENTICAL terminal state for both the `ALTER ROLE` role settings and
    the `audit_writer_roles` row -- exercised against the REAL migration
    file this fixture already applied once, not a synthetic stand-in."""
    before_roles = _row_value(platform, "audit_writer_roles")
    before_api = _role_setting(platform, platform.api_role)
    before_controlplane = _role_setting(platform, platform.controlplane_role)

    migration_path = platform.rewritten_migrations_dir / "0008_platform_declarations_and_writer_timeouts.sql"
    _run_psql(platform.control_dsn, migration_path, {"api_role": platform.api_role, "controlplane_role": platform.controlplane_role})

    after_roles = _row_value(platform, "audit_writer_roles")
    after_api = _role_setting(platform, platform.api_role)
    after_controlplane = _role_setting(platform, platform.controlplane_role)

    assert before_roles == after_roles == [platform.api_role, platform.controlplane_role]
    assert before_api == after_api
    assert before_controlplane == after_controlplane


def test_migration_0008_grants_select_to_both_writer_roles_and_nothing_to_public(bare_platform: types.SimpleNamespace) -> None:
    """{scratchpad}/wp12-audit-gaps.md G1: WP-1 completion conditions 2/26
    name the GRANT explicitly; no prior test in this file observed
    `has_table_privilege` for `platform_declarations`. Mirrors MitateDB-
    api's `tests/test_migration_0007_ddl.py::test_0007_grants_select_to_
    both_roles_and_nothing_to_public` (line 130 at audit time)."""
    with psycopg.connect(bare_platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT')",
                [bare_platform.api_role, f"{bare_platform.schema}.platform_declarations"],
            )
            assert cur.fetchone()[0] is True
            cur.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT')",
                [bare_platform.controlplane_role, f"{bare_platform.schema}.platform_declarations"],
            )
            assert cur.fetchone()[0] is True
            cur.execute(
                "SELECT count(*) FROM information_schema.table_privileges "
                "WHERE table_schema = %s AND table_name = 'platform_declarations' AND grantee = 'PUBLIC'",
                [bare_platform.schema],
            )
            assert cur.fetchone()[0] == 0


def test_migration_0008_seeds_window_default_but_not_surfaces(bare_platform: types.SimpleNamespace) -> None:
    """{scratchpad}/wp12-audit-gaps.md G1: WP-1 completion conditions 2/26.
    Uses the freshly bootstrapped `bare_platform`, never the module-scoped
    `platform` fixture (mutated by later `declare-surfaces`/`declare-
    coalescing-window` tests in this file, so its declarations-table state
    at any given point depends on test execution order). Mirrors MitateDB-
    api's `tests/test_migration_0007_ddl.py::test_0007_seeds_window_
    default_and_audit_writer_roles_but_not_surfaces` (line 122 at audit
    time)."""
    with psycopg.connect(bare_platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT key, value FROM {table}").format(table=sql.Identifier(bare_platform.schema, "platform_declarations"))
            )
            rows = dict(cur.fetchall())
    assert rows["audit_coalescing_window_ms"] == 60000
    assert rows["audit_writer_roles"] == [bare_platform.api_role, bare_platform.controlplane_role]
    assert "surfaces" not in rows


def test_migration_0008_reapplication_resets_a_manually_changed_timeout_back_to_the_seed_default(platform: types.SimpleNamespace) -> None:
    """SS4(c)/completion condition 1: `ALTER ROLE ... SET` is an
    UNCONDITIONAL overwrite (design D-1(a): "上書き代入であり、再実行しても
    同じ終状態になる") -- re-applying the migration after an intermediate
    `ops set-platform-timeouts` change must reset the role setting back to
    the migration's own hardcoded default (5000ms/5000ms), never leave the
    intermediate value in place. This is the test a "conditional insert"
    mutation (work order 変異 1) turns red: a conditional `ALTER ROLE`
    (only-if-not-already-set) would SKIP the second application entirely
    and leave the manually-changed value untouched."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9999ms'").format(sql.Identifier(platform.api_role)))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '9999ms'").format(sql.Identifier(platform.api_role)))
        conn.commit()
    try:
        changed = _role_setting(platform, platform.api_role)
        assert changed == {"statement_timeout": 9999, "idle_in_transaction_session_timeout": 9999}

        migration_path = platform.rewritten_migrations_dir / "0008_platform_declarations_and_writer_timeouts.sql"
        _run_psql(platform.control_dsn, migration_path, {"api_role": platform.api_role, "controlplane_role": platform.controlplane_role})

        reset = _role_setting(platform, platform.api_role)
        assert reset == {"statement_timeout": 5000, "idle_in_transaction_session_timeout": 5000}
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(platform.api_role)))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(sql.Identifier(platform.api_role)))
            conn.commit()


def test_migration_0008_source_file_names_the_check_constraint_explicitly() -> None:
    """Completion condition 2, static counterpart: PostgreSQL happens to
    auto-generate the SAME name ('<table>_<column>_check') for an UNNAMED
    single-column CHECK on 'platform_declarations.key' as this migration's
    own explicit 'CONSTRAINT platform_declarations_key_check' clause --
    so the dynamic ('does a constraint with this name exist') test above
    cannot, on its own, distinguish an explicit name from that coincidental
    default. This static check on the migration's OWN source text closes
    that gap: the 'CONSTRAINT platform_declarations_key_check' clause must
    literally be present in the file (design SS7 rule 2's own reason: a
    future migration must 'DROP CONSTRAINT'/'ADD CONSTRAINT' by a name it
    can rely on, not one that happens to match today's auto-generated
    default)."""
    migration_path = MIGRATIONS_DIR / "0008_platform_declarations_and_writer_timeouts.sql"
    text = migration_path.read_text()
    assert "CONSTRAINT platform_declarations_key_check" in text


def test_migration_0008_key_check_constraint_is_named(platform: types.SimpleNamespace) -> None:
    """Completion condition 2 (design D-2(a)): the CHECK constraint on
    `key` must be a NAMED constraint, `platform_declarations_key_check` --
    not a processor-generated name -- so a future migration adding a
    fourth key can `DROP CONSTRAINT`/`ADD CONSTRAINT` by name (design SS7
    rule 2: no in-place edits to an already-shipped migration)."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = 'platform_declarations' AND c.contype = 'c'",
                [platform.schema],
            )
            names = {row[0] for row in cur.fetchall()}
    assert "platform_declarations_key_check" in names


def test_migration_0008_key_check_admits_audit_writer_roles(platform: types.SimpleNamespace) -> None:
    """Completion condition 2/19: the named CHECK constraint's closed set
    includes `audit_writer_roles` (proven by the seed row from the fixture
    itself already existing under that key -- the row could not have been
    inserted at all if the CHECK rejected the key) and still rejects an
    unknown key."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.CheckViolation):
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('not_a_real_key', to_jsonb(1))").format(
                        table=sql.Identifier(platform.schema, "platform_declarations")
                    )
                )
        conn.rollback()


# ===========================================================================
# set-platform-timeouts
# ===========================================================================


def test_set_platform_timeouts_places_the_same_two_values_on_both_writer_roles(ops_env: types.SimpleNamespace) -> None:
    rc = ops.main(["set-platform-timeouts", "--statement-ms", "1234", "--idle-ms", "4321"])
    assert rc == 0
    assert _role_setting(ops_env, ops_env.api_role) == {"statement_timeout": 1234, "idle_in_transaction_session_timeout": 4321}
    assert _role_setting(ops_env, ops_env.controlplane_role) == {"statement_timeout": 1234, "idle_in_transaction_session_timeout": 4321}


def test_set_platform_timeouts_is_idempotent(ops_env: types.SimpleNamespace) -> None:
    assert ops.main(["set-platform-timeouts", "--statement-ms", "1500", "--idle-ms", "1500"]) == 0
    first = _role_setting(ops_env, ops_env.api_role)
    assert ops.main(["set-platform-timeouts", "--statement-ms", "1500", "--idle-ms", "1500"]) == 0
    second = _role_setting(ops_env, ops_env.api_role)
    assert first == second == {"statement_timeout": 1500, "idle_in_transaction_session_timeout": 1500}


@pytest.mark.parametrize("statement_ms,idle_ms", [("0", "5000"), ("5000", "0"), ("-1", "5000"), ("5000", "-1")])
def test_set_platform_timeouts_rejects_zero_and_negative_values(ops_env: types.SimpleNamespace, statement_ms: str, idle_ms: str) -> None:
    with pytest.raises(SystemExit) as exc:
        ops.main(["set-platform-timeouts", "--statement-ms", statement_ms, "--idle-ms", idle_ms])
    assert exc.value.code == 2


def test_main_returns_exit_code_1_on_a_foundation_or_psycopg_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """{scratchpad}/wp12-audit-gaps.md G2 (completion condition 11): `ops.
    main`'s `except FoundationError`/`except psycopg.Error` branches
    (ops.py:1438-1443) both return 1 -- observed nowhere in this file
    before this test, which only ever exercised the argparse-level `_die`
    (`SystemExit(2)`) path above. Points `R2DB_CONTROL_DSN` at a host that
    refuses the TCP connection outright, so `set-platform-timeouts` fails
    with a `psycopg.OperationalError` (a `psycopg.Error` subclass) before
    ever reaching an ALTER ROLE statement, and asserts the exit code
    `main()` returns -- via its ordinary `return`, no `SystemExit` at all
    here -- is 1."""
    monkeypatch.setenv("R2DB_CONTROL_DSN", "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1")
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", "irrelevant_registry")
    exit_code = ops.main(["set-platform-timeouts", "--statement-ms", "5000", "--idle-ms", "5000"])
    assert exit_code == 1


def test_set_platform_timeouts_targets_come_from_the_declared_audit_writer_roles_row(ops_env: types.SimpleNamespace) -> None:
    """Completion condition 22 (D-2(h) point 4): `set-platform-timeouts`
    takes NO role-name argument and its target set is read from the
    declared `audit_writer_roles` row -- proven here by targeting the SAME
    throwaway-prefixed role pair the fixture seeded (never a hardcoded
    production literal), and confirming both (and only both) roles moved."""
    assert ops.main(["set-platform-timeouts", "--statement-ms", "2222", "--idle-ms", "3333"]) == 0
    assert _role_setting(ops_env, ops_env.api_role) == {"statement_timeout": 2222, "idle_in_transaction_session_timeout": 3333}
    assert _role_setting(ops_env, ops_env.controlplane_role) == {"statement_timeout": 2222, "idle_in_transaction_session_timeout": 3333}


# ===========================================================================
# declare-surfaces
# ===========================================================================


def test_declare_surfaces_writes_data_and_control(ops_env: types.SimpleNamespace) -> None:
    rc = ops.main([
        "declare-surfaces",
        "--data-base-url", "https://ops-declare-test.example.invalid/v1",
        "--control-base-url", "https://ops-declare-test.example.invalid/control/v1",
    ])
    assert rc == 0
    assert _row_value(ops_env, "surfaces") == {
        "data": {"base_url": "https://ops-declare-test.example.invalid/v1"},
        "control": {"base_url": "https://ops-declare-test.example.invalid/control/v1"},
    }


def test_declare_surfaces_no_control_removes_the_control_key(ops_env: types.SimpleNamespace) -> None:
    ops.main([
        "declare-surfaces",
        "--data-base-url", "https://ops-declare-test.example.invalid/v1",
        "--control-base-url", "https://ops-declare-test.example.invalid/control/v1",
    ])
    rc = ops.main(["declare-surfaces", "--data-base-url", "https://ops-declare-test.example.invalid/v1", "--no-control"])
    assert rc == 0
    assert _row_value(ops_env, "surfaces") == {"data": {"base_url": "https://ops-declare-test.example.invalid/v1"}}


def test_declare_surfaces_omitting_control_base_url_is_no_longer_an_error(ops_env: types.SimpleNamespace) -> None:
    """Amendment (q4-f3c-and-amendments.md, 裁定訂正): `--control-base-url`
    is now OPTIONAL -- omitting it (without `--no-control` either) is
    equivalent to passing `--no-control`, not a usage error."""
    rc = ops.main(["declare-surfaces", "--data-base-url", "https://ops-declare-test.example.invalid/v1"])
    assert rc == 0
    assert _row_value(ops_env, "surfaces") == {"data": {"base_url": "https://ops-declare-test.example.invalid/v1"}}


def test_declare_surfaces_rejects_both_control_base_url_and_no_control_together(ops_env: types.SimpleNamespace) -> None:
    with pytest.raises(SystemExit) as exc:
        ops.main([
            "declare-surfaces", "--data-base-url", "https://ops-declare-test.example.invalid/v1",
            "--control-base-url", "https://ops-declare-test.example.invalid/control/v1", "--no-control",
        ])
    assert exc.value.code == 2


@pytest.mark.parametrize("bad_url", ["/v1", "https://ops-declare-test.example.invalid/v2", "https://ops-declare-test.example.invalid/v1/"])
def test_declare_surfaces_rejects_malformed_data_base_url(ops_env: types.SimpleNamespace, bad_url: str) -> None:
    with pytest.raises(SystemExit) as exc:
        ops.main(["declare-surfaces", "--data-base-url", bad_url, "--no-control"])
    assert exc.value.code == 2


def test_declare_surfaces_empty_control_base_url_is_rejected_not_silently_no_control(ops_env: types.SimpleNamespace) -> None:
    """N-5 (monitor ruling 2026-09-05): `--control-base-url ""` is a
    DEFINED but malformed value -- it must hit F-5 like every other bad
    URL, never be silently treated as "no control declared" the way a
    truthiness check (`args.control_base_url and ...`) would collapse it.
    MitateDB-api's own `is not None` check already gets this right; this
    pins the SAME behavior for r2db-api (parity closure, N-5)."""
    with pytest.raises(SystemExit) as exc:
        ops.main(["declare-surfaces", "--data-base-url", "https://ops-declare-test.example.invalid/v1", "--control-base-url", ""])
    assert exc.value.code == 2


# ===========================================================================
# declare-coalescing-window
# ===========================================================================


def test_declare_coalescing_window_writes_the_value(ops_env: types.SimpleNamespace) -> None:
    assert ops.main(["declare-coalescing-window", "--ms", "0"]) == 0
    assert _row_value(ops_env, "audit_coalescing_window_ms") == 0

    assert ops.main(["declare-coalescing-window", "--ms", "120000"]) == 0
    assert _row_value(ops_env, "audit_coalescing_window_ms") == 120000


def test_declare_coalescing_window_rejects_negative_value(ops_env: types.SimpleNamespace) -> None:
    with pytest.raises(SystemExit) as exc:
        ops.main(["declare-coalescing-window", "--ms", "-1"])
    assert exc.value.code == 2


# ===========================================================================
# show-declarations
# ===========================================================================


def test_show_declarations_prints_rows_and_role_settings(ops_env: types.SimpleNamespace, capsys: pytest.CaptureFixture) -> None:
    ops.main(["declare-surfaces", "--data-base-url", "https://ops-show-test.example.invalid/v1", "--no-control"])
    ops.main(["declare-coalescing-window", "--ms", "60000"])
    ops.main(["set-platform-timeouts", "--statement-ms", "7000", "--idle-ms", "8000"])
    capsys.readouterr()  # discard the 3 setup commands' own output

    rc = ops.main(["show-declarations"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "https://ops-show-test.example.invalid/v1" in out
    assert "60000" in out
    assert ops_env.api_role in out
    assert "statement_timeout=7000ms" in out
    assert "idle_in_transaction_session_timeout=8000ms" in out


# ===========================================================================
# audit_writer_roles value validation (F-4b) -- completion condition 23
# ===========================================================================


@pytest.mark.parametrize(
    "bad_value",
    [
        [],
        "not-a-list",
        ["dup", "dup"],
        ["1starts-with-digit"],
        ["valid_name", "-not-an-identifier"],
    ],
)
def test_f4b_audit_writer_roles_rejects_malformed_values(bad_value) -> None:
    with pytest.raises(PlatformDeclarationError):
        validate_audit_writer_roles_value(bad_value, schema="r2dbsvc_registry", ops_module=PEER_MODULE)


def test_f4b_writer_roles_message_is_pinned_verbatim() -> None:
    """Agent C addition (task step 3): design §3.8 F-4b(ii) verbatim, not
    previously pinned by an exact-equality assertion (only `pytest.raises
    (PlatformDeclarationError)` above, which would not catch a paraphrase)."""
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_audit_writer_roles_value([], schema="r2dbsvc_registry", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "'audit_writer_roles' in r2dbsvc_registry.platform_declarations must be a non-empty JSON array of "
        "distinct, valid PostgreSQL identifiers, got '[]'. This table can be edited by hand, so the value is "
        "validated on every read. This row is written only by migration 0008, which seeds it with the very "
        "role names it issues ALTER ROLE for: re-apply that migration to this platform database with this "
        "deployment's writer role names, then restart both processes."
    )


def test_f4b_audit_writer_roles_validation_runs_on_every_read_path(ops_env: types.SimpleNamespace) -> None:
    """Completion condition 23: the SAME validation function runs on every
    read path -- corrupt the row by hand, then observe `show-declarations`
    (never dies, diagnostic) and a fresh `read_platform_declarations` call
    (dies, F-4b) both notice."""
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET value = to_jsonb(ARRAY['dup', 'dup']) WHERE key = 'audit_writer_roles'").format(
                    table=sql.Identifier(ops_env.schema, "platform_declarations")
                )
            )
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError):
                read_platform_declarations(conn, schema=ops_env.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("UPDATE {table} SET value = to_jsonb(ARRAY[%s, %s]) WHERE key = 'audit_writer_roles'").format(
                        table=sql.Identifier(ops_env.schema, "platform_declarations")
                    ),
                    [ops_env.api_role, ops_env.controlplane_role],
                )
            conn.commit()


# ===========================================================================
# Fail-fast message string pins (design §3.8, completion condition 12 + 20)
# -- copied VERBATIM, <peer> -> r2db_api, <NNNN> -> 0008.
# ===========================================================================

_F1_STATEMENT = (
    "R2DB_AUDIT_STATEMENT_TIMEOUT_MS is no longer read (Q4 D-1): the audit writer roles carry statement_timeout / "
    "idle_in_transaction_session_timeout as PostgreSQL role settings, applied by migration 0008. This variable is "
    "rejected whenever it is defined, whatever its value (an empty string included). Unset this variable, then "
    "set the value with 'python -m r2db_api.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>' and "
    "restart both processes. Note this setting also bounds every other connection made by this role (credential "
    "store lookups and control-plane registry operations included)."
)

def _f2(schema: str) -> str:
    return (
        f"R2DB_DATA_BASE_URL is no longer read (Q4 D-2): surfaces are declared in {schema}.platform_declarations, "
        f"created by migration 0008. This variable is rejected whenever it is defined, whatever its value (an empty "
        f"string included). Unset this variable, then declare with 'python -m r2db_api.ops declare-surfaces "
        f"--data-base-url <URL> [--control-base-url <URL>]' and restart both processes."
    )


def _f3(schema: str) -> str:
    return (
        f"no 'surfaces' row in {schema}.platform_declarations: contract 1.6.0 requires surfaces.data "
        f"unconditionally. Declare it with 'python -m r2db_api.ops declare-surfaces --data-base-url <URL> "
        f"[--control-base-url <URL>]', then restart both processes."
    )


def _f3c(schema: str) -> str:
    return (
        f"'surfaces' row in {schema}.platform_declarations has no surfaces.control, but this is the "
        f"control-plane process, which always has a control surface to declare (contract 1.6.0: both "
        f"documents return the same surfaces object). Declare it with 'python -m r2db_api.ops "
        f"declare-surfaces --data-base-url <URL> --control-base-url <URL>', then restart both processes."
    )


def _f4(schema: str) -> str:
    return (
        f"no 'audit_coalescing_window_ms' row in {schema}.platform_declarations: migration 0008 seeds it with "
        f"the shipped default (60000). Apply that migration, or set the value with 'python -m r2db_api.ops "
        f"declare-coalescing-window --ms <N>', then restart both processes."
    )


def _f4b_window(schema: str, value) -> str:
    return (
        f"'audit_coalescing_window_ms' in {schema}.platform_declarations must be a non-negative integer (0 "
        f"means no coalescing), got '{value}'. This table can be edited by hand, so the value is validated on "
        f"every read as well as on write. Re-set it with 'python -m r2db_api.ops declare-coalescing-window "
        f"--ms <N>', then restart both processes."
    )


def _f7(role: str) -> str:
    return (
        f"role '{role}' has no statement_timeout / idle_in_transaction_session_timeout in pg_db_role_setting: "
        f"migration 0008 is not applied to this platform database, and an audit writer must never run unbounded. "
        f"Apply migration 0008, or set the values with 'python -m r2db_api.ops set-platform-timeouts "
        f"--statement-ms <N> --idle-ms <N>', then restart both processes. Note this setting also bounds every "
        f"other connection made by this role (credential store lookups and control-plane registry operations "
        f"included)."
    )


def _f10(role: str, label: str, ms: int) -> str:
    return (
        f"role '{role}' declares {label} = {ms} in pg_db_role_setting, which PostgreSQL reads as \"no "
        f"limit\": an audit writer must never run unbounded, and the declared visibility_lag_ms would describe "
        f"a bound that does not exist. Set a positive value with 'python -m r2db_api.ops "
        f"set-platform-timeouts --statement-ms <N> --idle-ms <N>' (the command rejects 0 and negative "
        f"values), then restart both processes."
    )


def _f13(current_user: str, declared_roles, *, schema: str = "r2dbsvc_registry") -> str:
    declared_repr = "[" + ", ".join(f'"{role}"' for role in declared_roles) + "]" if declared_roles else "absent"
    return (
        f"current_user '{current_user}' is not declared as an audit writer role: 'audit_writer_roles' in "
        f"{schema}.platform_declarations is absent, or it does not list this role (declared: "
        f"{declared_repr}). Migration 0008 seeds that row with the very role names it issues 'ALTER "
        f"ROLE … SET statement_timeout / idle_in_transaction_session_timeout' for, in the same "
        f"transaction, so a process connecting as any other role writes audit rows whose timeouts the "
        f"declared visibility_lag_ms does not describe. Apply migration 0008 to this platform database "
        f"with this deployment's writer role names, or connect this process as one of the declared roles; "
        f"then set the timeouts with 'python -m r2db_api.ops set-platform-timeouts --statement-ms <N> "
        f"--idle-ms <N>' (it issues ALTER ROLE for every role in 'audit_writer_roles', and takes no role-name "
        f"argument) and restart both processes."
    )


def test_f8_message_is_pinned_verbatim_and_not_a_raw_psycopg_exception(ops_env: types.SimpleNamespace) -> None:
    """F-8 (design §3.7 step 4 ordering, completion condition 5): the table
    itself missing (migration 0008 not applied) must surface the pinned
    message, never a raw `psycopg.errors.UndefinedTable`. Drops the table
    temporarily (restored in `finally`) -- this file's own `platform`
    fixture is module-scoped and shared by every other test here, so the
    table must come back exactly as it was, `audit_writer_roles` included."""
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP TABLE {table}").format(table=sql.Identifier(ops_env.schema, "platform_declarations")))
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_platform_declarations(conn, schema=ops_env.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        assert not isinstance(exc.value, psycopg.errors.UndefinedTable)
        expected = (
            f"relation {ops_env.schema}.platform_declarations does not exist: migration 0008 (Q4 D-2) has not "
            f"been applied to this platform database. Apply it with 'psql \"$R2DB_CONTROL_DSN\" -f r2db-api/"
            f"migrations/0008_platform_declarations_and_writer_timeouts.sql', then restart both processes."
        )
        assert str(exc.value) == expected
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "CREATE TABLE {table} ("
                        "key text PRIMARY KEY CONSTRAINT platform_declarations_key_check "
                        "CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles')), "
                        "value jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())"
                    ).format(table=sql.Identifier(ops_env.schema, "platform_declarations"))
                )
                cur.execute(sql.SQL("REVOKE ALL ON {table} FROM PUBLIC").format(table=sql.Identifier(ops_env.schema, "platform_declarations")))
                cur.execute(sql.SQL("GRANT SELECT ON {table} TO {role}").format(table=sql.Identifier(ops_env.schema, "platform_declarations"), role=sql.Identifier(ops_env.api_role)))
                cur.execute(sql.SQL("GRANT SELECT ON {table} TO {role}").format(table=sql.Identifier(ops_env.schema, "platform_declarations"), role=sql.Identifier(ops_env.controlplane_role)))
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('audit_coalescing_window_ms', to_jsonb(60000::int)) ON CONFLICT (key) DO NOTHING").format(
                        table=sql.Identifier(ops_env.schema, "platform_declarations")
                    )
                )
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('audit_writer_roles', to_jsonb(ARRAY[%s, %s])) ON CONFLICT (key) DO NOTHING").format(
                        table=sql.Identifier(ops_env.schema, "platform_declarations")
                    ),
                    [ops_env.api_role, ops_env.controlplane_role],
                )
            conn.commit()


def test_f1_message_is_pinned_verbatim() -> None:
    from r2db_api.platform_declarations import reject_removed_timeout_env

    with pytest.raises(PlatformDeclarationError) as exc:
        reject_removed_timeout_env({"R2DB_AUDIT_STATEMENT_TIMEOUT_MS": ""}, names=("R2DB_AUDIT_STATEMENT_TIMEOUT_MS",))
    assert str(exc.value) == _F1_STATEMENT


def test_f2_message_is_pinned_verbatim() -> None:
    from r2db_api.platform_declarations import reject_removed_surface_env

    with pytest.raises(PlatformDeclarationError) as exc:
        reject_removed_surface_env({"R2DB_DATA_BASE_URL": ""}, names=("R2DB_DATA_BASE_URL",), schema="r2dbsvc_registry")
    assert str(exc.value) == _f2("r2dbsvc_registry")


def test_f2_message_names_the_real_schema_not_a_literal_placeholder() -> None:
    """N-7 (monitor ruling 2026-09-05): `reject_removed_surface_env` must
    NOT hardcode `DEFAULT_SCHEMA` -- a deployment that overrides
    `R2DB_PLATFORM_SCHEMA` must see ITS OWN schema name in F-2's remedy
    text, not the shipped default."""
    from r2db_api.platform_declarations import reject_removed_surface_env

    with pytest.raises(PlatformDeclarationError) as exc:
        reject_removed_surface_env({"R2DB_DATA_BASE_URL": ""}, names=("R2DB_DATA_BASE_URL",), schema="some_throwaway_schema_x1")
    assert str(exc.value) == _f2("some_throwaway_schema_x1")
    assert "r2dbsvc_registry" not in str(exc.value)


def test_f3_message_is_pinned_verbatim_against_real_absence(platform: types.SimpleNamespace) -> None:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {table} WHERE key = 'surfaces'").format(table=sql.Identifier(platform.schema, "platform_declarations")))
        conn.commit()
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_platform_declarations(conn, schema=platform.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        assert str(exc.value) == _f3(platform.schema)
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {table} WHERE key = 'surfaces'").format(table=sql.Identifier(platform.schema, "platform_declarations"))
                )
            conn.commit()


def test_f3c_message_is_pinned_verbatim() -> None:
    from r2db_api.platform_declarations import Surfaces, require_control_surface_declared

    with pytest.raises(PlatformDeclarationError) as exc:
        require_control_surface_declared(Surfaces(data_base_url="https://x.example.invalid/v1", control_base_url=None), schema="r2dbsvc_registry", ops_module=PEER_MODULE)
    assert str(exc.value) == _f3c("r2dbsvc_registry")


def test_f4_message_is_pinned_verbatim(platform: types.SimpleNamespace) -> None:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            # F-3 must not fire ahead of F-4 here (design SS3.7 step 4's own
            # order is F-3 THEN F-4, but this file's shared `platform`
            # fixture never seeds `surfaces` at all, design D-2(c)) -- seed
            # a throwaway row first, matching what a real deployment would
            # already have via `ops declare-surfaces`.
            cur.execute(
                sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', %s) ON CONFLICT (key) DO NOTHING").format(
                    table=sql.Identifier(platform.schema, "platform_declarations")
                ),
                [json.dumps({"data": {"base_url": "https://f4-test.example.invalid/v1"}})],
            )
            cur.execute(sql.SQL("DELETE FROM {table} WHERE key = 'audit_coalescing_window_ms'").format(table=sql.Identifier(platform.schema, "platform_declarations")))
        conn.commit()
    try:
        with psycopg.connect(platform.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_platform_declarations(conn, schema=platform.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        assert str(exc.value) == _f4(platform.schema)
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {table} WHERE key = 'surfaces'").format(table=sql.Identifier(platform.schema, "platform_declarations")))
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('audit_coalescing_window_ms', to_jsonb(60000)) ON CONFLICT (key) DO NOTHING").format(
                        table=sql.Identifier(platform.schema, "platform_declarations")
                    )
                )
            conn.commit()


@pytest.mark.parametrize("bad_value", ["60000", 60000.5, -1])
def test_f4b_window_message_is_pinned_verbatim(bad_value) -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_coalescing_window_value(bad_value, schema="r2dbsvc_registry", ops_module=PEER_MODULE)
    assert str(exc.value) == _f4b_window("r2dbsvc_registry", bad_value)


def test_f5_message_is_pinned_verbatim() -> None:
    """Agent C addition (task step 3): design §3.8 F-5 verbatim -- not
    previously pinned by an exact-equality assertion anywhere in this
    file (only the malformed-shape behavioral tests in `test_surfaces_
    env.py`, which assert a `match=` substring against `RuntimeError`,
    not the raised `PlatformDeclarationError`'s own full text)."""
    from r2db_api.platform_declarations import validate_surfaces_value

    with pytest.raises(PlatformDeclarationError) as exc:
        validate_surfaces_value({"data": {"base_url": "https://h.example.invalid/v1/"}}, schema="r2dbsvc_registry", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "surfaces.data.base_url in r2dbsvc_registry.platform_declarations must be an absolute URL ending in "
        "'/v1' with no trailing slash, got 'https://h.example.invalid/v1/'. Re-declare it with 'python -m "
        "r2db_api.ops declare-surfaces …'."
    )


def test_f6_forward_message_is_pinned_verbatim() -> None:
    """Agent C addition (task step 3): design §3.8 F-6 verbatim (forward
    direction: `surfaces.control` declared but `R2DB_CONTROL_PLANE_STATUS`
    is `'unavailable'`) -- not previously pinned by an exact-equality
    assertion anywhere in this file."""
    from r2db_api.platform_declarations import Surfaces, check_control_surface_consistency

    surfaces = Surfaces(data_base_url="https://h.example.invalid/v1", control_base_url="https://h.example.invalid/control/v1")
    with pytest.raises(PlatformDeclarationError) as exc:
        check_control_surface_consistency(surfaces, "unavailable", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "surfaces.control is declared but R2DB_CONTROL_PLANE_STATUS is 'unavailable' (contract 1.6.0: a "
        "deployment declaring control_plane unavailable omits surfaces.control). The surfaces row is shared "
        "by BOTH processes: re-declaring with '--no-control' removes the control declaration for the "
        "control-plane process too, and that process will then fail to start (F-3). Unless this deployment "
        "really offers no control surface, change R2DB_CONTROL_PLANE_STATUS on this process instead, then "
        "restart both processes. If the deployment genuinely has no control surface, re-declare with 'python "
        "-m r2db_api.ops declare-surfaces --data-base-url <URL> --no-control'."
    )


def test_f6_reverse_message_is_pinned_verbatim() -> None:
    """Agent C addition (task step 3): design §3.8 F-6's own "逆向き...も
    同型の1文で出す" note -- the reverse direction (`surfaces.control` NOT
    declared but the status is other than `'unavailable'`)."""
    from r2db_api.platform_declarations import Surfaces, check_control_surface_consistency

    surfaces = Surfaces(data_base_url="https://h.example.invalid/v1", control_base_url=None)
    with pytest.raises(PlatformDeclarationError) as exc:
        check_control_surface_consistency(surfaces, "enabled", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "surfaces.control is not declared but R2DB_CONTROL_PLANE_STATUS is 'enabled' (contract 1.6.0: a "
        "deployment declaring control_plane other than unavailable must have a control surface). The surfaces "
        "row is shared by BOTH processes: declare a control base url with 'python -m r2db_api.ops "
        "declare-surfaces --data-base-url <URL> --control-base-url <URL>', or unless this deployment really "
        "offers a control surface, change R2DB_CONTROL_PLANE_STATUS to 'unavailable' on this process instead, "
        "then restart both processes."
    )


def test_f9_message_is_pinned_verbatim() -> None:
    """Agent C addition (task step 3): design §3.8 F-9 verbatim -- a
    direct unit-level call to the private message builder (same style as
    MitateDB-api's own `test_f13_message_is_verbatim`/`test_f3c_message_
    is_verbatim`), complementing the real-PG behavioral coverage already
    in `test_application_audit.py::
    test_build_app_f9_fires_when_a_connection_string_options_override_
    changes_the_effective_value` (which asserts only a `match=` substring,
    not the full pinned text)."""
    from r2db_api.platform_declarations import _f9_message

    message = _f9_message("r2dbsvc_api", "statement_timeout", 5000, 30000, ops_module=PEER_MODULE)
    assert message == (
        "role 'r2dbsvc_api' declares statement_timeout = 5000 ms in pg_db_role_setting but this connection's "
        "effective value is 30000 ms (both shown in milliseconds; PostgreSQL renders these settings in "
        "whichever unit divides evenly, so never compare the rendered strings): the declared visibility_lag_ms "
        "would not describe the effective connection. Remove the override -- a connection-string "
        "'options=-c …', PGOPTIONS, or an 'ALTER ROLE … IN DATABASE … SET' row -- so the role setting is the "
        "effective value, or change the role setting with 'python -m r2db_api.ops set-platform-timeouts "
        "--statement-ms <N> --idle-ms <N>', then restart both processes. Note this setting also bounds every "
        "other connection made by this role."
    )


def test_f7_message_is_pinned_verbatim(ops_env: types.SimpleNamespace) -> None:
    # A role with no ALTER ROLE ... SET row at all -- the schema's own
    # provision role (never given a role setting by any migration).
    with psycopg.connect(ops_env.control_dsn) as conn:
        with pytest.raises(PlatformDeclarationError) as exc:
            read_declared_role_timeouts(conn, ops_env.control_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    assert str(exc.value) == _f7(ops_env.control_role)


def test_f10_message_is_pinned_verbatim(ops_env: types.SimpleNamespace) -> None:
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '0'").format(sql.Identifier(ops_env.api_role)))
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_declared_role_timeouts(conn, ops_env.api_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        assert str(exc.value) == _f10(ops_env.api_role, "statement_timeout", 0)
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(ops_env.api_role)))
            conn.commit()


def test_f11_message_is_pinned_verbatim(ops_env: types.SimpleNamespace) -> None:
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} SET statement_timeout = '9999ms'").format(sql.Identifier(ops_env.api_role), sql.Identifier(ops_env.platform_db)))
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_declared_role_timeouts(conn, ops_env.api_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        expected = (
            f"role '{ops_env.api_role}' has an 'ALTER ROLE … IN DATABASE …' setting row for database "
            f"'{ops_env.platform_db}', which takes precedence over the database-independent role setting this "
            f"deployment declares. The role setting must be a single database-independent row. Remove it with "
            f"'ALTER ROLE {ops_env.api_role} IN DATABASE {ops_env.platform_db} RESET statement_timeout, "
            f"idle_in_transaction_session_timeout;' (issued on the provision DSN), then restart both processes."
        )
        assert str(exc.value) == expected
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} RESET statement_timeout").format(sql.Identifier(ops_env.api_role), sql.Identifier(ops_env.platform_db)))
            conn.commit()


def test_f11_ignores_a_per_database_row_that_carries_no_timeout_key(ops_env: types.SimpleNamespace) -> None:
    """q4-f3c-and-amendments.md's F-11 amendment: a per-database row that
    sets an UNRELATED GUC (e.g. `search_path`) must never trip F-11."""
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path = 'public'").format(sql.Identifier(ops_env.api_role), sql.Identifier(ops_env.platform_db)))
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            catalog = read_declared_role_timeouts(conn, ops_env.api_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        assert catalog.role == ops_env.api_role
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} RESET search_path").format(sql.Identifier(ops_env.api_role), sql.Identifier(ops_env.platform_db)))
            conn.commit()


def test_f13_message_is_pinned_verbatim_and_fires_before_f7(ops_env: types.SimpleNamespace) -> None:
    """Completion condition 20: a role NOT in `audit_writer_roles`
    (`ops_env.control_role`, which also has no `pg_db_role_setting` row at
    all -- i.e. would ALSO trip F-7) hits F-13 first."""
    from r2db_api.platform_declarations import check_writer_role_timeouts

    with psycopg.connect(_dsn_with(ops_env.control_dsn, user=ops_env.control_role)) as conn:
        with pytest.raises(PlatformDeclarationError) as exc:
            check_writer_role_timeouts(conn, declared_roles=(ops_env.api_role, ops_env.controlplane_role), schema=ops_env.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    assert str(exc.value) == _f13(ops_env.control_role, (ops_env.api_role, ops_env.controlplane_role), schema=ops_env.schema)


def test_f13_fires_when_audit_writer_roles_row_is_absent(ops_env: types.SimpleNamespace) -> None:
    from r2db_api.platform_declarations import check_writer_role_timeouts

    with psycopg.connect(
        _dsn_with(ops_env.control_dsn, user=ops_env.api_role, password=ops_env.api_password)
    ) as conn:
        with pytest.raises(PlatformDeclarationError) as exc:
            check_writer_role_timeouts(conn, declared_roles=(), schema=ops_env.schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    assert str(exc.value) == _f13(ops_env.api_role, (), schema=ops_env.schema)


def test_derive_visibility_lag_ms_default_is_11000() -> None:
    """Completion condition 10 (design §3, D-1(c)): the shipped default
    (5000ms/5000ms for both roles) derives 11000 -- the same value the
    pre-Q4 constant this phase replaces already published."""
    assert derive_visibility_lag_ms([
        RoleTimeoutCatalog(role="a", statement_ms=5000, idle_ms=5000),
        RoleTimeoutCatalog(role="b", statement_ms=5000, idle_ms=5000),
    ]) == 11_000


def test_derive_visibility_lag_ms_uses_the_max_across_declared_roles(ops_env: types.SimpleNamespace) -> None:
    """Completion condition 21: seeding two DIFFERENT timeouts on the two
    declared roles makes `derive_visibility_lag_ms` take the max, not
    either role in particular -- proving the derivation reads BOTH
    declared roles' catalogs, not a single hardcoded one."""
    with psycopg.connect(ops_env.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '1000ms'").format(sql.Identifier(ops_env.api_role)))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '1000ms'").format(sql.Identifier(ops_env.api_role)))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9000ms'").format(sql.Identifier(ops_env.controlplane_role)))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '9000ms'").format(sql.Identifier(ops_env.controlplane_role)))
        conn.commit()
    try:
        with psycopg.connect(ops_env.control_dsn) as conn:
            catalogs = [read_declared_role_timeouts(conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER) for role in (ops_env.api_role, ops_env.controlplane_role)]
        assert derive_visibility_lag_ms(catalogs) == 9000 + 9000 + 1000
    finally:
        with psycopg.connect(ops_env.control_dsn) as conn:
            with conn.cursor() as cur:
                for role in (ops_env.api_role, ops_env.controlplane_role):
                    cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(role)))
                    cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(sql.Identifier(role)))
            conn.commit()


def test_no_naming_convention_role_derivation_remains_in_composition_roots() -> None:
    """Completion condition 21: `grep` proof that the rejected naming-
    convention role-derivation pattern (`removesuffix("_registry")`/
    similar schema-name rewrites for a WRITER role name) is gone from both
    composition roots and `ops.py`."""
    import subprocess

    root = Path(__file__).resolve().parents[1] / "src" / "r2db_api"
    result = subprocess.run(
        ["grep", "-rn", "removesuffix", str(root / "main.py"), str(root / "control_main.py"), str(root / "ops.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"unexpected 'removesuffix' occurrences (naming-convention role derivation):\n{result.stdout}"
