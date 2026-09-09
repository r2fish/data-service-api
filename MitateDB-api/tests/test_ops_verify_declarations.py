"""Phase 8 WP-4 (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md
D-5, work order docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md §2
WP-4): `ops verify-declarations` -- one test per F-number in the D-5 exit
code table (completion condition 1), plus the `code` attribute
(completion condition 2). Own file, own fixtures (deliberately NOT sharing
`tests/test_ops_declarations.py`'s own declaration-series file -- this is
the ops-series file the work order §0.0 point 6 requires WP-4 to keep
separate from WP-1's limit-series files).

Each test connects `ops verify-declarations` to a freshly bootstrapped,
throwaway-prefixed platform database (own bootstrap, not the shared
module-scoped `control_plane_harness.control_platform` fixture other test
modules in this directory use -- this file's own tests both ADD and
REMOVE the `surfaces` row and mutate `pg_db_role_setting`, so a shared
fixture would make later tests' outcomes depend on execution order) and
manipulates exactly ONE row/setting to construct the ONE F-number
condition under test, then asserts the exact exit code from the D-5
table. Mirrors r2db-api's own `tests/test_ops_verify_declarations.py` in
shape (per-test bootstrap, in-process `ops.main([...])` calls) -- not
itself isomorphism-pinned (常設規律6 pins same-named HELPERS, not every
`test_*` function; `_verify_declarations_ok`/`_verify_declarations_fail`/
the two module-level tables in `ops.py` are the rows this WP adds to
`_ISOMORPHIC_TARGETS`, not this file's own tests)."""
from __future__ import annotations

import secrets
import subprocess
import tempfile
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Json

import mitatedb_api.ops as ops
from mitatedb_api.platform_declarations import PlatformDeclarationError, check_role_connection_limits

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

MIGRATION_NAMES = (
    "0001_bootstrap_platform.sql",
    "0002_registry_and_functions.sql",
    "0005_application_audit.sql",
    # Phase 10 WP-4f (supervisor ruling 2026-09-09; peer-symmetric with
    # r2db-api's own `0013_role_connection_limits.sql`): raises
    # `mitatedbsvc_api`/`mitatedbsvc_controlplane`'s own `CONNECTION
    # LIMIT`. Inserted here (before 0007, not appended at the tuple's own
    # end) so `MIGRATION_NAMES_WITHOUT_DECLARATIONS`'s own `[:-2]` slice
    # below still drops exactly `{0007, 0011}`, unchanged (this file's own
    # isomorphism-pinned symbol, `tests/test_audit_query.py::
    # _ISOMORPHIC_TARGETS`).
    "0012_role_connection_limits.sql",
    "0007_platform_declarations.sql",
    # Phase 10 WP-6b (design D-5 (ii)): widens `platform_declarations.
    # key`'s own CHECK constraint to accept `process_ceilings`. `_bootstrap`
    # below auto-seeds a default `{"data": 1, "control": 1}` row whenever
    # this migration ran (mirroring `0007`'s own auto-seed of `audit_
    # coalescing_window_ms`/`audit_writer_roles`) -- none of this file's
    # own tests are ABOUT `process_ceilings` (that is `test_process_
    # ceilings_declaration.py`'s job), so every test here needs it present
    # and out of the way, not set individually.
    "0011_process_ceilings.sql",
)
#: F-8's own fixture omits the last TWO entries above -- this is that same
#: sequence minus migrations 0007/0011 (0007 creates `platform_
#: declarations` in the first place; 0011 only widens a CHECK on a table
#: that, on THIS fixture, does not exist at all).
MIGRATION_NAMES_WITHOUT_DECLARATIONS = MIGRATION_NAMES[:-2]

_DATA_URL = "https://ops-verify-test.example.invalid/v1"
_CONTROL_URL = "https://ops-verify-test.example.invalid/control/v1"


def _admin_dsn() -> str:
    import os

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
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_ops_verify_declarations.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)


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


def _bootstrap(prefix: str, migration_names: tuple[str, ...]) -> types.SimpleNamespace:
    admin_dsn = _admin_dsn()
    provision_role = f"{prefix}svc_provision"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)

    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_ops_verify_"))
    rewritten: dict[str, Path] = {}
    for name in migration_names:
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
    # Phase 10 WP-4f: unconditional, like 0002/0005 above -- depends only
    # on those two (never on 0007/0011), so it always runs here regardless
    # of which fixture variant (`MIGRATION_NAMES` vs `MIGRATION_NAMES_
    # WITHOUT_DECLARATIONS`) called this function.
    _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
    if "0007_platform_declarations.sql" in rewritten:
        _run_psql(
            provision_dsn,
            rewritten["0007_platform_declarations.sql"],
            {"api_role": api_role, "controlplane_role": controlplane_role},
        )
    if "0011_process_ceilings.sql" in rewritten:
        _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
        # Phase 10 WP-6b: auto-seed the default ceiling row -- see
        # `MIGRATION_NAMES`'s own comment above for why every test in this
        # file needs it present unconditionally.
        with psycopg.connect(provision_dsn) as _seed_conn:
            with _seed_conn.cursor() as _seed_cur:
                _seed_cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('process_ceilings', %s) ON CONFLICT (key) DO NOTHING").format(
                        table=sql.Identifier(schema, "platform_declarations")
                    ),
                    [Json({"data": 1, "control": 1})],
                )
            _seed_conn.commit()
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
    finally:
        admin.close()

    return types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, provision_role=provision_role,
        api_role=api_role, api_password=api_password, api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_role=controlplane_role, controlplane_password=controlplane_password,
        platform_db=platform_db, schema=schema,
        role_connection_limits_sql=rewritten["0012_role_connection_limits.sql"],
    )


@pytest.fixture()
def platform() -> Iterator[types.SimpleNamespace]:
    """A fresh, fully-migrated (through `0007`) throwaway platform, one per
    test -- no `surfaces` row yet (migration `0007` seeds only
    `audit_coalescing_window_ms`/`audit_writer_roles`; `surfaces` is
    written only by `ops declare-surfaces`)."""
    _require_admin_connection()
    prefix = f"p8wp4_mtdbverify{secrets.token_hex(4)}"
    admin_dsn = _admin_dsn()
    try:
        info = _bootstrap(prefix, MIGRATION_NAMES)
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


@pytest.fixture()
def undeclared_platform() -> Iterator[types.SimpleNamespace]:
    """F-8's own fixture: every migration through `0005`, but NOT `0007`
    -- `<schema>.platform_declarations` does not exist at all."""
    _require_admin_connection()
    prefix = f"p8wp4_mtdbverifynodecl{secrets.token_hex(4)}"
    admin_dsn = _admin_dsn()
    try:
        info = _bootstrap(prefix, MIGRATION_NAMES_WITHOUT_DECLARATIONS)
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _set_row(platform: types.SimpleNamespace, key: str, value: object) -> None:
    with psycopg.connect(platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                (key, Json(value)),
            )
        conn.commit()


def _delete_row(platform: types.SimpleNamespace, key: str) -> None:
    with psycopg.connect(platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE key = %s").format(table=sql.Identifier(platform.schema, "platform_declarations")),
                (key,),
            )
        conn.commit()


def _run_verify(monkeypatch: pytest.MonkeyPatch, *, dsn: str, schema: str, control: bool = False, control_plane_status: str | None = None) -> int:
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", schema)
    if control_plane_status is None:
        monkeypatch.delenv("MITATEDB_CONTROL_PLANE_STATUS", raising=False)
    else:
        monkeypatch.setenv("MITATEDB_CONTROL_PLANE_STATUS", control_plane_status)
    argv = ["verify-declarations"] + (["--control"] if control else [])
    return ops.main(argv)


# ===========================================================================
# completion condition 2: `code` attribute (not prefix-matched by ops.py)
# ===========================================================================


def test_platform_declaration_error_code_attribute_is_not_paraphrased() -> None:
    """Completion condition 2: raising with a given `code=` sets exactly
    that attribute, and the message text is unaffected."""
    exc = PlatformDeclarationError("some message", code="F-9")
    assert exc.code == "F-9"
    assert str(exc) == "some message"


# ===========================================================================
# completion condition 1: one test per F-number, exact exit code
# ===========================================================================


def test_verify_declarations_f8_when_platform_declarations_table_is_missing(
    undeclared_platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc = _run_verify(monkeypatch, dsn=undeclared_platform.provision_dsn, schema=undeclared_platform.schema)
    assert rc == 8


def test_verify_declarations_f3_when_surfaces_row_is_absent(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 3


def test_verify_declarations_f3c_when_control_flag_but_no_control_surface(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema, control=True)
    assert rc == 4


def test_verify_declarations_f4_when_coalescing_window_row_is_absent(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _delete_row(platform, "audit_coalescing_window_ms")
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 5


def test_verify_declarations_f4b_when_coalescing_window_value_is_malformed(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _set_row(platform, "audit_coalescing_window_ms", "not-a-number")
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 6


def test_verify_declarations_f4b_when_audit_writer_roles_value_is_malformed(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _set_row(platform, "audit_writer_roles", [])
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 6


def test_verify_declarations_f15_when_process_ceilings_row_is_absent(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 10 WP-6b (design D-5 (ii)): `process_ceilings` is checked
    for row-existence right after `audit_coalescing_window_ms` (F-4) and
    before any of the three rows' own VALUES are validated -- unlike
    `surfaces`, `_bootstrap` DOES auto-seed a default `process_ceilings`
    row (`MIGRATION_NAMES`'s own comment above), so this test has to
    delete it explicitly to reach F-15."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _delete_row(platform, "process_ceilings")
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 14


def test_verify_declarations_f15_when_process_ceilings_value_is_malformed(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The malformed-VALUE half of F-15 (design D-5 (ii)):
    `validate_process_ceilings_value` shares the SAME F-number as the
    missing-row check immediately above -- `process_ceilings` is one new
    key, not two (unlike `surfaces`/F-3+F-5 or `audit_coalescing_window_
    ms`/F-4+F-4b, which each pre-date this WP and already had a separate
    F-number budgeted for their own missing-row vs malformed-value
    conditions)."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _set_row(platform, "process_ceilings", {"data": 0, "control": 1})
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 14


def test_verify_declarations_f5_when_surfaces_value_is_malformed(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": "not-a-url"}})
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 7


def test_verify_declarations_f6_when_control_declared_but_status_unavailable(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}, "control": {"base_url": _CONTROL_URL}})
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema, control_plane_status="unavailable")
    assert rc == 9


def test_verify_declarations_f13_when_connected_role_is_not_a_declared_writer(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`platform.provision_dsn` logs in as the schema-owner provision role,
    never a declared `audit_writer_roles` member (`[api_role,
    controlplane_role]`, migration `0007`) -- the default state of every
    freshly bootstrapped platform in this file already exercises F-13."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    assert rc == 11


def test_verify_declarations_f7_when_declared_role_has_no_timeout_row(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    with psycopg.connect(platform.admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(platform.api_role)))
            cur.execute(sql.SQL("ALTER ROLE {} RESET idle_in_transaction_session_timeout").format(sql.Identifier(platform.api_role)))
    rc = _run_verify(monkeypatch, dsn=platform.api_dsn, schema=platform.schema)
    assert rc == 10


def test_verify_declarations_f10_when_declared_timeout_is_zero(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    with psycopg.connect(platform.admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = 0").format(sql.Identifier(platform.api_role)))
    rc = _run_verify(monkeypatch, dsn=platform.api_dsn, schema=platform.schema)
    assert rc == 10


def test_verify_declarations_f11_when_a_per_database_override_exists(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    with psycopg.connect(platform.admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET statement_timeout = '1000ms'").format(
                    sql.Identifier(platform.api_role), sql.Identifier(platform.platform_db)))
    rc = _run_verify(monkeypatch, dsn=platform.api_dsn, schema=platform.schema)
    assert rc == 10


def test_verify_declarations_f9_when_effective_value_disagrees_with_declared(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    overridden_dsn = _dsn_with(platform.api_dsn, options="-c statement_timeout=999ms")
    rc = _run_verify(monkeypatch, dsn=overridden_dsn, schema=platform.schema)
    assert rc == 12


def test_verify_declarations_exits_0_when_every_check_passes(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-空振り: proves the F-number checks are not vacuously true --
    the SAME writer-role connection that hits F-13 above (`platform.
    provision_dsn`) here instead connects as `api_role`, a declared writer
    with its migration-seeded 5000ms/5000ms timeouts intact, and every
    check passes."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    rc = _run_verify(monkeypatch, dsn=platform.api_dsn, schema=platform.schema)
    assert rc == 0


def test_verify_declarations_exits_2_when_platform_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc = _run_verify(monkeypatch, dsn="host=/tmp port=1 dbname=nonexistent_mitatedb_verify_target connect_timeout=2", schema="whatever")
    assert rc == 2


def test_verify_declarations_exits_1_when_dsn_env_var_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #7):
    design D-5's own exit code table assigns 1 to a USAGE error (this
    command's own required env var missing) and reserves 2 for a real
    connection failure once the DSN is known -- distinct rows, previously
    both mapped to 2 (the shared `_die` convention). No PostgreSQL
    connection is attempted on this path at all."""
    monkeypatch.delenv("MITATEDB_PROVISION_DSN", raising=False)
    rc = ops.main(["verify-declarations"])
    assert rc == 1


# ===========================================================================
# completion condition 3 (WP-4 rework #2): output format -- one line per
# check, and the F-1/F-2/F-12 out-of-scope line as the LAST line on BOTH
# the all-pass path and a FAIL path.
# ===========================================================================


def test_verify_declarations_output_format_has_one_line_per_check_and_trailing_out_of_scope_line(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #2): the
    code review found the F-1/F-2/F-12 disclosure line printed only on the
    all-pass (exit 0) path -- every FAIL `return` was a `return` out of
    the `try/finally` the print statement lived textually AFTER, so the
    finally ran (closing the connection) but the print never did. This
    test drives BOTH a pass and a FAIL run and asserts the disclosure line
    is the LAST line of stdout either way, and every other line is exactly
    one 'OK ...'/'FAIL ...' check line -- deleting the disclosure print
    (or leaving it reachable only from the 0 path) turns this red."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})

    rc_pass = _run_verify(monkeypatch, dsn=platform.api_dsn, schema=platform.schema)
    out_pass = capsys.readouterr().out.rstrip("\n").splitlines()
    assert rc_pass == 0
    assert len(out_pass) >= 2, out_pass
    assert out_pass[-1].startswith("--   F-1/F-2/F-12"), out_pass
    for line in out_pass[:-1]:
        assert line.startswith("OK   "), line

    rc_fail = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    out_fail = capsys.readouterr().out.rstrip("\n").splitlines()
    assert rc_fail == 11
    assert len(out_fail) >= 2, out_fail
    assert out_fail[-1].startswith("--   F-1/F-2/F-12"), "FAIL path must still print the out-of-scope line as the last line"
    assert any(line.startswith("FAIL ") for line in out_fail[:-1]), out_fail
    for line in out_fail[:-1]:
        assert line.startswith("OK   ") or line.startswith("FAIL "), line


# ===========================================================================
# F-14 (contract 1.7.0, WP-3e rework T3, ruling `{scratchpad}/
# rulings-r3-r7-flip.md` L-2/M-7): the ONE part of `check_contract_170_
# declarations` a real deployment can actually fail through this exact
# command -- a REAL, provisioned application whose own per-application
# upgrade ledger (`public._mdb_platform_upgrades`, seeded by `0003_
# provision_application.sql`) is missing a required upgrade number.
# Mirrors r2db-api's own `test_verify_declarations_f14_fails_when_an_
# application_has_not_applied_every_upgrade`/`test_verify_declarations_
# f14_passes_when_every_application_has_applied_every_upgrade` in shape.
# ===========================================================================


def _provision_app_for_verify(platform: types.SimpleNamespace, app_id: str) -> types.SimpleNamespace:
    """Runs the REAL `0003_provision_application.sql` (rewritten with this
    platform's own throwaway prefix, `_bootstrap`'s own `.replace("mitatedb",
    prefix)` convention) against `platform.provision_dsn` -- not otherwise
    touched by this file's own `platform` fixture, which only migrates
    through `0007` and provisions no application by default. `0003`
    already seeds the new application's own ledger with `{6, 8, 9, 10}`
    (its own trailing `INSERT INTO public._mdb_platform_upgrades ...`), so
    no separate `0008`/`0009`/`0010` per-application upgrade run is needed
    to reach a healthy starting ledger here."""
    script_text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text().replace("mitatedb", platform.prefix)
    script = Path(tempfile.mkdtemp(prefix="mitatedb_ops_verify_app_")) / "0003_provision_application.sql"
    script.write_text(script_text)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.provision_dsn, script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{app_id}"
    return types.SimpleNamespace(app_id=app_id, database=database)


def _declare_provision_role_as_the_writer(platform: types.SimpleNamespace) -> None:
    """Reading every application's own ledger (F-14's new per-application
    check, `_applied_upgrade_numbers_by_application`/`_app_dsn`) needs a
    role with cross-database access -- `platform.provision_role` (proven
    able to do this: `ops upgrade-applications`/`upgrade-status` already
    read every application's ledger connected as this same role, `_app_
    dsn`'s own docstring). Unlike `api_role`/`controlplane_role`, migration
    `0007` does not seed `provision_role` as a declared audit writer --
    done here instead so this test can connect `verify-declarations` AS
    `provision_role` and reach F-14 (the check under test) rather than
    failing earlier at F-13 (the default state every OTHER test in this
    file that connects as `provision_dsn` deliberately exercises)."""
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(platform.provision_role)))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '5000ms'").format(sql.Identifier(platform.provision_role)))
        conn.commit()
    _set_row(platform, "audit_writer_roles", [platform.provision_role])


def test_verify_declarations_f14_fails_when_an_application_has_not_applied_every_upgrade(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Provisions one REAL application (`0003` seeds its ledger with
    `{6, 8, 9, 10}` directly), then deletes upgrade number `10` from that
    application's own ledger table -- the SAME real-Postgres "construct a
    hole" technique `test_ops_upgrade.py::delete_ledger_row` uses -- to
    simulate an application whose database has not yet run Phase 9's own
    per-application upgrade. `ops verify-declarations` must then exit
    non-zero (F-14's own exit code, 13) and name the lagging application,
    never a silent `OK F-14`."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _declare_provision_role_as_the_writer(platform)
    app = _provision_app_for_verify(platform, "verifyf14")
    with psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database)) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._mdb_platform_upgrades WHERE upgrade_number = 10")
        conn.commit()
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    out = capsys.readouterr().out
    assert rc == 13
    assert "FAIL F-14" in out, out
    assert "verifyf14" in out, out
    assert "pending=[10]" in out, out


def test_verify_declarations_f14_passes_when_every_application_has_applied_every_upgrade(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-空振り positive control for the test immediately above: the
    SAME real application, ledger left intact (`{6, 8, 9, 10}`, exactly
    what `0003` seeds), passes F-14 -- proving the FAIL above is really
    about the missing upgrade number, not some other difference between
    this test's setup and the happy-path fixture."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _declare_provision_role_as_the_writer(platform)
    _provision_app_for_verify(platform, "verifyf14ok")
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    out = capsys.readouterr().out
    assert rc == 0, out


# ===========================================================================
# H-1 non-regression (WP-4 integration review 2026-09-10): unlike
# r2db-api's own `0013_role_connection_limits.sql`, MitateDB-api's
# `0012_role_connection_limits.sql` section 2 already filtered
# `runtime_role`/`developer_role IS NOT NULL` from the start (the review's
# own finding) -- this pins that correct behavior directly, peer-symmetric
# with r2db-api's own `test_0013_migration_tolerates_a_registered_only_
# application_...` test, so a future edit cannot silently regress it.
# ===========================================================================


def test_0012_migration_tolerates_a_registered_only_application_and_still_raises_a_provisioned_applications_role_limits(
    platform: types.SimpleNamespace,
) -> None:
    """H-1 non-regression, peer-symmetric (WP-4 integration review
    2026-09-10): a registered-but-not-provisioned application row (`mitatedb_
    registry.applications` two-state registry, 0002's own header -- a row
    with `runtime_role`/`developer_role` still NULL) must not stop
    `0012_role_connection_limits.sql` section 2 from raising a REAL
    provisioned application's own role limits when re-applied (idempotent
    by design). This uses this file's own function-scoped `platform`
    fixture (not a module-scoped one shared with other tests' own
    synthetic rows) so the only `applications` rows present are the two
    this test itself inserts.

    Mutation: reintroduce r2db-api's own pre-fix bug here too (drop the
    `WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL` filter
    from section 2) -> this test's `_run_psql` call raises `RuntimeError`
    ("...null values cannot be formatted as an SQL identifier...")."""
    registered_id = f"regonly{secrets.token_hex(3)}"
    with psycopg.connect(platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {table} (application_id) VALUES (%s)").format(table=sql.Identifier(platform.schema, "applications")),
                [registered_id],
            )
        conn.commit()

    provisioned_id = "regonlyprov"
    _provision_app_for_verify(platform, provisioned_id)
    database = f"{platform.prefix}_app_{provisioned_id}"
    # `mitatedb_registry.begin_provision_application`'s own naming (0002):
    # `<database>_rt` / `<database>_dv`, unlike r2db-api's own `_runtime`/
    # `_developer` suffixes.
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"

    _run_psql(platform.provision_dsn, platform.role_connection_limits_sql)

    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)", [[runtime_role, developer_role]])
            limits = dict(cur.fetchall())
    assert limits[runtime_role] == 36, limits
    assert limits[developer_role] == 36, limits


# ===========================================================================
# F-16 (Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric with
# r2db-api's own same-numbered test): every role this deployment pools
# connections against has a CONNECTION LIMIT of -1 or at least its own real
# pool-composition floor -- `0012_role_connection_limits.sql` (already
# applied unconditionally by `_bootstrap` above) is what makes the POSITIVE
# case real: before that migration, `mitatedbsvc_api`'s own CONNECTION
# LIMIT (20) already sat below its own floor (64), so F-16 would fail on
# every freshly-bootstrapped platform, not just the mutated one below.
# ===========================================================================


def test_verify_declarations_f16_passes_after_migration_0012(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Positive control: a freshly bootstrapped platform (migration 0012
    already applied by `_bootstrap`, one real provisioned application so
    its own runtime/developer roles exist too) passes F-16 -- proving the
    FAIL test below is really about the lowered CONNECTION LIMIT, not some
    other difference between the two fixtures."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _declare_provision_role_as_the_writer(platform)
    _provision_app_for_verify(platform, "verifyf16ok")
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "OK   F-16" in out, out


def test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """The real mutation this check exists to catch: an operator (or a
    future migration regression) lowers `mitatedbsvc_api`'s own CONNECTION
    LIMIT back below its own real pool-composition floor (2 stores x
    concurrency 32 = 64) -- here, back to `0002_registry_and_functions.
    sql`'s own pre-WP-4f value (20), simulating exactly the state every
    platform was in before migration 0012 existed. `ops verify-
    declarations` must exit non-zero (F-16's own exit code, 15) and name
    the role, its current limit, and the required floor -- never a silent
    `OK F-16`."""
    _set_row(platform, "surfaces", {"data": {"base_url": _DATA_URL}})
    _declare_provision_role_as_the_writer(platform)
    _provision_app_for_verify(platform, "verifyf16bad")
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 20").format(sql.Identifier(platform.api_role)))
        conn.commit()
    rc = _run_verify(monkeypatch, dsn=platform.provision_dsn, schema=platform.schema)
    out = capsys.readouterr().out
    assert rc == 15
    assert "FAIL F-16" in out, out
    assert platform.api_role in out, out
    assert "CONNECTION LIMIT 20" in out, out
    assert "64" in out, out


def test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned(
    platform: types.SimpleNamespace,
) -> None:
    """M-1 (WP-4 integration review 2026-09-10, peer-symmetric with
    r2db-api's own same-named test): `check_role_connection_limits`'s own
    `floors` dict previously did plain `floors[role] = N` for each of the
    three platform-plane classes in turn (api, controlplane, auditreader,
    in that order) -- a role granted matching privileges under MORE than
    one class silently ended up with whichever class's floor was assigned
    LAST (auditreader's, the smallest: 4), not the largest floor it is
    actually subject to. This pins the fix with a synthetic role that is
    NOT the schema-owning role (so the separate owner-exclusion this same
    fix adds, tested below, cannot mask this arithmetic bug): granted
    INSERT on both audit tables (api class, floor 2 x 32 = 64;
    controlplane class, floor 16) and SELECT on both (auditreader class,
    floor 4). The correct required floor is max(64, 16, 4) = 64 -- with
    the pre-fix last-write-wins bug, the computed floor would be 4, and
    this role's own CONNECTION LIMIT (10) would satisfy that, so
    `check_role_connection_limits` would NOT raise at all (this test would
    fail to see the expected `PlatformDeclarationError`)."""
    role = f"{platform.prefix}_multiclass"
    platform_dsn = _dsn_with(platform.admin_dsn, dbname=platform.platform_db)
    with psycopg.connect(platform_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN CONNECTION LIMIT 10").format(sql.Identifier(role)))
            for table in ("application_audit", "control_audit"):
                cur.execute(
                    sql.SQL("GRANT INSERT, SELECT ON {} TO {}").format(sql.Identifier(platform.schema, table), sql.Identifier(role))
                )
        conn.commit()
    try:
        with psycopg.connect(platform.provision_dsn) as conn:
            with pytest.raises(PlatformDeclarationError) as excinfo:
                check_role_connection_limits(conn, schema=platform.schema, ops_module="test", concurrency=32, application_ids=())
        assert excinfo.value.code == "F-16"
        message = str(excinfo.value)
        assert role in message, message
        assert "CONNECTION LIMIT 10" in message, message
        assert "64" in message, message
    finally:
        with psycopg.connect(platform_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            conn.commit()
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            conn.commit()


def test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class(
    platform: types.SimpleNamespace,
) -> None:
    """M-1 (WP-4 integration review 2026-09-10, peer-symmetric with
    r2db-api's own same-named test): `platform.provision_role` (the role
    every migration in this fixture runs AS, hence the OWNER of both
    `application_audit`/`control_audit`) genuinely holds explicit INSERT
    on both tables (0002/0005's own break-glass CLI grants) AND, as owner,
    an implicit SELECT on both -- matching all three platform-plane
    classes at once. It is not a real pooled role (module header's own
    "Deliberately excludes" note) and must never be floor-checked at all,
    regardless of its own real `CONNECTION LIMIT` (5, `0001_bootstrap_
    platform.sql`'s own value, never raised by 0012). This pins that
    exclusion directly: lowering it even further (to 1, well below every
    floor constant) must still not raise."""
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 1").format(sql.Identifier(platform.provision_role)))
        conn.commit()
    try:
        with psycopg.connect(platform.provision_dsn) as conn:
            check_role_connection_limits(conn, schema=platform.schema, ops_module="test", concurrency=32, application_ids=())
    finally:
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 5").format(sql.Identifier(platform.provision_role)))
            conn.commit()
