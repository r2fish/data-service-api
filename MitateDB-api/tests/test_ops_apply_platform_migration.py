"""`ops apply-platform-migration` -- the public subcommand
that applies a run of one or more platform migration files (never a
per-application upgrade, never the bootstrap-only 0001/0002) a second
(or later) time against a running cluster, and the static coverage
proving which subcommands' own `--lock-timeout` is required.

Covers: filename validation (enumeration, path separators, directory
containment, no value echoed on rejection, a symlinked migrations
directory), the psql-variable table, DSN-via-environment-only
(design Z-8/D-10), connection-value redaction, the required `--lock-
timeout`, `ON_ERROR_STOP`, psql 16+, drift-then-restore for 5 of the 7
accepted files (0005/0007/0011/0012/0013; 0014 and 0016 have none), and the
AST-derived "flows DDL" subcommand set.

Test infrastructure: own fixtures, duplicated bootstrap shape from
`test_ops_inventory.py`/`test_platform_migration_reapply.py`, not
imported (this repository's own precedent of not taking cross-test-
module import dependencies). This subcommand is never run against
production (work order section 7) -- every test below targets a
throwaway PostgreSQL cluster only.
"""
from __future__ import annotations

import ast
import os
import re
import secrets
import subprocess
import shutil
import tempfile
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import mitatedb_api.ops as ops

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(ops.__file__).resolve().parent
OPS_SOURCE_PATH = Path(ops.__file__).resolve()
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"

_TEST_LOCK_TIMEOUT = "5000ms"


def _admin_dsn() -> str:
    """Embeds ambient `PGPASSFILE` into the returned DSN up front --
    several tests below clear that ambient variable before an in-process
    `apply-platform-migration` call, and this DSN must keep working through fixture teardown regardless."""
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; there is no shared-cluster default."
        )
    passfile = os.environ.get("PGPASSFILE")
    if passfile and "passfile=" not in dsn:
        params = conninfo_to_dict(dsn)
        params["passfile"] = passfile
        dsn = make_conninfo(**params)
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
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            f"test_ops_apply_platform_migration.py requires a reachable local PostgreSQL server: {exc}",
            pytrace=False,
        )


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


_PLATFORM_MIGRATION_NAMES = (
    "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
    "0005_application_audit.sql", "0007_platform_declarations.sql",
    "0011_process_ceilings.sql", "0012_role_connection_limits.sql",
    "0013_role_statement_timeouts.sql", "0014_role_connection_limits_rollout.sql",
)


def _bootstrap(prefix: str, *, apply_0013: bool = True) -> types.SimpleNamespace:
    """`apply_0013=False` stops right after `0012` -- used by the one test
    that observes 0013's own per-application loop (section 2) declaring
    `statement_timeout` retroactively on roles provisioned before 0013
    first ran. 0014 is only copied into the rewritten temp dir here; it
    is not applied -- each test that needs 0014 applies it itself."""
    admin_dsn = _admin_dsn()
    provision_role = f"{prefix}svc_provision"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_apm_"))
    rewritten: "dict[str, Path]" = {}
    for name in _PLATFORM_MIGRATION_NAMES:
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
    _run_psql(
        provision_dsn, rewritten["0007_platform_declarations.sql"],
        {"api_role": api_role, "controlplane_role": controlplane_role},
    )
    _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
    _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
    if apply_0013:
        _run_psql(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])

    return types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, provision_role=provision_role,
        api_role=api_role, controlplane_role=controlplane_role, platform_db=platform_db, schema=schema,
        migrations_dir=rewritten_dir, migration_paths=rewritten,
    )


def _provision_app_via_function(dsn: str, schema: str, app_id: str) -> "tuple[str, str, str]":
    """Calls `begin_provision_application` directly (never the full 0003
    script) -- enough to observe 0013's own role-setting behavior without
    also creating a real per-application database this test would then
    have to clean up. `database_name` stays NULL on the registry row
    until `finish_provision_application` runs (0003's own job, never
    called here), so calling this twice for the SAME `app_id` is not
    rejected as already-provisioned -- it instead exercises `CREATE
    ROLE`'s own `duplicate_object` fallback branch."""
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {fn}(%s, %s, %s)").format(
                    fn=sql.Identifier(schema, "begin_provision_application")),
                [app_id, secrets.token_urlsafe(24), secrets.token_urlsafe(24)],
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return row[0], row[1], row[2]


def _clear_ambient_pg_connection_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test-infrastructure cluster (`tools/testpg/dsa_testpg.py`)
    exports `PGPASSFILE` (and may export other libpq connection
    variables) for the whole pytest process -- ambient values
    `_psql_connection_env`'s own leftover-variable check correctly
    refuses to let a psql child inherit silently. Real apply-platform-
    migration invocations below clear these first; the ONE test that
    exercises the leftover-variable rejection itself sets its own
    sentinel back afterward."""
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def platform() -> Iterator[types.SimpleNamespace]:
    """A fresh, throwaway platform through 0001/0002/0005/0007/0011/0012/
    0013 -- one per test, never shared (several tests drift role settings,
    constraints, ACLs, and function bodies). Does NOT clear the ambient
    libpq connection variables the test-infra cluster exports (`_run_
    apply` does that, right before the one in-process `ops.main` call
    that would otherwise inherit them) -- this fixture's own bootstrap
    psql/psycopg calls need the ambient `PGPASSFILE` for auth."""
    _require_admin_connection()
    prefix = f"r45wpeapm{secrets.token_hex(4)}"
    admin_dsn = _admin_dsn()
    try:
        info = _bootstrap(prefix)
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)
        shutil.rmtree(info.migrations_dir, ignore_errors=True)


def _run_apply(
    monkeypatch: pytest.MonkeyPatch, platform: types.SimpleNamespace, filename: str,
    *, clear_ambient: bool = True, **cli_kwargs,
) -> "int | None":
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(platform.migrations_dir))
    if clear_ambient:
        _clear_ambient_pg_connection_env_vars(monkeypatch)
    argv = ["apply-platform-migration", filename]
    if "lock_timeout" not in cli_kwargs:
        cli_kwargs["lock_timeout"] = _TEST_LOCK_TIMEOUT
    for flag, value in cli_kwargs.items():
        if value is None:
            continue
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    try:
        return ops.main(argv)
    except SystemExit as exc:
        return exc.code


def _run_apply_run(
    monkeypatch: pytest.MonkeyPatch, platform: types.SimpleNamespace, *filenames: str,
    clear_ambient: bool = True, **cli_kwargs,
) -> "int | None":
    """Same as `_run_apply`, but for a RUN of one or more FILENAMEs
    (D-1) -- `filenames` are passed as one or more positional
    arguments, in the given order, never sorted here."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(platform.migrations_dir))
    if clear_ambient:
        _clear_ambient_pg_connection_env_vars(monkeypatch)
    argv = ["apply-platform-migration", *filenames]
    if "lock_timeout" not in cli_kwargs:
        cli_kwargs["lock_timeout"] = _TEST_LOCK_TIMEOUT
    for flag, value in cli_kwargs.items():
        if value is None:
            continue
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    try:
        return ops.main(argv)
    except SystemExit as exc:
        return exc.code


# ===========================================================================
# filename validation
# ===========================================================================


def test_apply_platform_migration_rejects_a_name_outside_the_known_enumeration(monkeypatch, capsys, platform):
    """A real file that sits in the migrations directory but is
    NOT in the known enumeration (a bootstrap-only migration) is
    refused -- no psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0002_registry_and_functions.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "0002_registry_and_functions.sql" not in captured.err


def test_apply_platform_migration_rejects_a_path_separator(monkeypatch, capsys, platform):
    """A value containing a path separator is refused with its
    OWN fixed message (distinct from the enumeration-mismatch message),
    even one that would resolve harmlessly inside the directory."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "./0007_platform_declarations.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: apply-platform-migration: FILENAME must not contain a path separator"


def test_apply_platform_migration_rejects_a_symlink_escaping_the_directory(monkeypatch, capsys, platform):
    """A known filename that is ITSELF a symlink resolving
    outside the migrations directory is refused -- no psql subprocess
    starts, the resolved path is never echoed."""
    outside_target = Path(tempfile.mkdtemp(prefix="mitatedb_apm_outside_")) / "evil.sql"
    outside_target.write_text("-- not a real migration\n")
    (platform.migrations_dir / "0011_process_ceilings.sql").unlink()
    (platform.migrations_dir / "0011_process_ceilings.sql").symlink_to(outside_target)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert str(outside_target) not in captured.err


def test_apply_platform_migration_rejection_never_echoes_the_input_value(monkeypatch, capsys, platform):
    """The enumeration-mismatch rejection message never
    contains the rejected value."""
    rc = _run_apply(monkeypatch, platform, "not-a-real-migration-name.sql")
    assert rc == 2
    captured = capsys.readouterr()
    assert "not-a-real-migration-name.sql" not in captured.err


def test_apply_platform_migration_resolves_every_file_before_any_psql_starts(monkeypatch, capsys, platform):
    """R-57 WP-1 code review fix 5 (resolve half): an unknown FILENAME
    LATER in the run is refused before ANY psql subprocess starts --
    including for a known, valid file earlier in the SAME run (every
    file is resolved up front, never one at a time inside the apply
    loop)."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0011_process_ceilings.sql", "not-a-real-migration-name.sql")
    assert rc == 2
    assert calls == []


def test_apply_platform_migration_run_variable_mismatch_is_rejected_before_any_psql_starts(
    monkeypatch, capsys, platform,
):
    """R-57 WP-1 code review fix 5 (variables half): a variable
    mismatch anywhere in the run is refused before ANY psql subprocess
    starts, including for `0011` -- earlier in the run and individually
    fine on its own -- when `0007` later in the SAME run is missing
    `--controlplane-role`."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform, "0007_platform_declarations.sql", "0011_process_ceilings.sql",
        api_role=platform.api_role,
    )
    assert rc == 2
    assert calls == []


def test_apply_platform_migration_accepts_a_known_file_through_a_symlinked_migrations_directory(monkeypatch, platform):
    """Resolving BOTH the directory and the candidate file
    (never the file alone) means a migrations directory that is itself a
    symlink still accepts a known file."""
    symlinked_dir = Path(tempfile.mkdtemp(prefix="mitatedb_apm_parent_")) / "migrations_link"
    symlinked_dir.symlink_to(platform.migrations_dir, target_is_directory=True)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(symlinked_dir))
    rc = ops.main([
        "apply-platform-migration", "0011_process_ceilings.sql", "--lock-timeout", _TEST_LOCK_TIMEOUT,
    ])
    assert rc == 0


# ===========================================================================
# the accepted-file constant
# ===========================================================================


def test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id():
    """The accepted-file constant is pinned to the 7 named files
    (`0016_credential_request_rate.sql`, design docs/design/MULTI_
    PROCESS_WORKER_V0_1.md D-3 (1), included -- a platform single-shot
    migration); each is real and references no `:app_id` psql variable;
    the directory's own `:app_id`-free files differ from this set by
    exactly the 2 bootstrap-only migrations."""
    assert ops._PLATFORM_MIGRATION_FILENAMES == (
        "0005_application_audit.sql", "0007_platform_declarations.sql",
        "0011_process_ceilings.sql", "0012_role_connection_limits.sql",
        "0013_role_statement_timeouts.sql", "0014_role_connection_limits_rollout.sql",
        "0016_credential_request_rate.sql",
    )
    no_app_id_files = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if "app_id" not in ops._extract_psql_variables(path.read_text()):
            no_app_id_files.add(path.name)
    assert set(ops._PLATFORM_MIGRATION_FILENAMES) <= no_app_id_files
    assert no_app_id_files - set(ops._PLATFORM_MIGRATION_FILENAMES) == {
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
    }
    for name in ops._PLATFORM_MIGRATION_FILENAMES:
        assert (MIGRATIONS_DIR / name).is_file()


# ===========================================================================
# DSN via environment only
# ===========================================================================


def test_apply_platform_migration_has_no_dsn_argument():
    """The subparser's own argument set never includes anything
    DSN-shaped (static, design Z-8)."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    apm_parser = subparsers_action.choices["apply-platform-migration"]
    dests = {action.dest for action in apm_parser._actions}
    assert dests == {"help", "file", "lock_timeout", "api_role", "controlplane_role"}


def test_apply_platform_migration_argv_never_carries_a_dsn_sentinel(monkeypatch, platform):
    """psql's own argv never carries a DSN element -- connection
    parameters travel only through the subprocess environment."""
    host_sentinel = conninfo_to_dict(platform.provision_dsn)["host"]
    captured = {}

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 16.4", stderr="")
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 0
    assert not any(host_sentinel in str(part) for part in captured["argv"])
    assert captured["env"]["PGHOST"] == host_sentinel


def test_apply_platform_migration_rejects_a_leftover_ambient_connection_variable(monkeypatch, capsys, platform):
    """A connection-setting variable in THIS process' own
    environment, not overridden by the DSN, is refused by name (never its
    value) before the migration file is applied (a `psql --version`
    check may still run first)."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    calls = []

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 16.4", stderr="")
        calls.append((argv, kwargs))
        pytest.fail("psql started")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql", clear_ambient=False)
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "PGSSLMODE" in captured.err
    assert "verify-full" not in captured.err


# ===========================================================================
# psql invocation shape
# ===========================================================================


def test_apply_platform_migration_requires_psql_16_or_newer(monkeypatch, capsys, platform):
    """An old/unreadable psql version is refused before the real
    migration is ever run."""
    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 15.4", stderr="")
        pytest.fail("psql started past the version check")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 2
    captured = capsys.readouterr()
    assert "older than PostgreSQL 16" in captured.err


def test_apply_platform_migration_argv_carries_on_error_stop(monkeypatch, platform):
    """The applied migration's own argv carries `ON_ERROR_STOP=1`
    (static, real subprocess)."""
    captured = {}
    real_run = subprocess.run

    def _spy_run(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured["argv"] = argv
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 0
    assert "-v" in captured["argv"] and "ON_ERROR_STOP=1" in captured["argv"]


def test_apply_platform_migration_lock_timeout_reaches_pgoptions(monkeypatch, platform):
    """`--lock-timeout` reaches psql through `PGOPTIONS`."""
    captured = {}
    real_run = subprocess.run

    def _spy_run(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured["env"] = kwargs.get("env")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql", lock_timeout="7000ms")
    assert rc == 0
    assert "-c lock_timeout=7000ms" in captured["env"]["PGOPTIONS"]


def test_apply_platform_migration_rejects_a_malformed_lock_timeout(monkeypatch, capsys, platform):
    """An invalid `--lock-timeout` value is refused before any
    psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql", lock_timeout="not-a-value")
    assert rc == 2
    assert calls == []


def test_apply_platform_migration_redacts_connection_values_on_failure(monkeypatch, capsys, platform):
    """A psql failure's own captured output is redacted before it
    reaches stderr."""
    host_sentinel = conninfo_to_dict(platform.provision_dsn)["host"]

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 16.4", stderr="")
        return subprocess.CompletedProcess(
            argv, 1, stdout=f"connection to server at {host_sentinel} failed\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 2
    captured = capsys.readouterr()
    assert host_sentinel not in captured.err
    assert "<redacted>" in captured.err


# ===========================================================================
# A dependency-missing apply fails by exit code
# ===========================================================================


def test_apply_platform_migration_fails_by_exit_code_when_its_dependency_is_missing(monkeypatch):
    """0011 depends on 0007's own table -- applying it against a
    platform that never applied 0007 fails (non-zero), never silently
    succeeds."""
    prefix = f"r45wpeapmdep{secrets.token_hex(4)}"
    admin_dsn = _admin_dsn()
    provision_password = secrets.token_urlsafe(24)
    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_apm_dep_"))
    rewritten = {}
    for name in ("0001_bootstrap_platform.sql", "0002_registry_and_functions.sql", "0011_process_ceilings.sql"):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out
    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(
            admin_dsn, user=f"{prefix}svc_provision", password=provision_password, dbname=f"{prefix}_platform")
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        monkeypatch.setenv("MITATEDB_PROVISION_DSN", provision_dsn)
        monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(rewritten_dir))
        _clear_ambient_pg_connection_env_vars(monkeypatch)
        try:
            rc = ops.main(["apply-platform-migration", "0011_process_ceilings.sql", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        except SystemExit as exc:
            rc = exc.code
        assert rc != 0
    finally:
        _sweep_prefix(admin_dsn, prefix)


# ===========================================================================
# drift-then-restore -- 0005/0007/0011/0012 (0013's own is in its own
# section below; 0014 has none)
# ===========================================================================


def _table_acl(dsn: str, schema: str, table: str) -> list:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s",
                [schema, table],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _acl_has_public_grantee(acl: "list | None") -> bool:
    return any(str(item).startswith("=") for item in (acl or []))


def _role_setting(dsn: str, role: str) -> "list[str] | None":
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.setconfig FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole "
                "WHERE r.rolname = %s AND s.setdatabase = 0",
                [role],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _constraint_definition(dsn: str, conname: str) -> str:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s", [conname])
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _function_def_and_acl(dsn: str, schema: str, function_name: str) -> tuple:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_get_functiondef(p.oid), p.proacl FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = %s AND p.proname = %s",
                [schema, function_name],
            )
            row = cur.fetchone()
            return (row[0], row[1]) if row else (None, None)
    finally:
        conn.close()


def _role_connlimit(dsn: str, role: str) -> "int | None":
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname = %s", [role])
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def test_apply_platform_migration_0005_restores_a_manually_drifted_public_grant(monkeypatch, platform):
    """A manually added PUBLIC grant on
    `application_audit` does not survive an apply-platform-migration
    re-application of 0005 -- its own `REVOKE ALL ... FROM PUBLIC` runs
    every time."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("GRANT SELECT ON {table} TO PUBLIC").format(
                table=sql.Identifier(platform.schema, "application_audit")))
    finally:
        conn.close()
    assert _acl_has_public_grantee(_table_acl(platform.provision_dsn, platform.schema, "application_audit"))
    rc = _run_apply(monkeypatch, platform, "0005_application_audit.sql")
    assert rc == 0
    assert not _acl_has_public_grantee(_table_acl(platform.provision_dsn, platform.schema, "application_audit"))


def test_apply_platform_migration_0007_restores_a_manually_drifted_role_setting(monkeypatch, platform):
    """A hand-changed `controlplane_role`
    session setting does not survive an apply-platform-migration
    re-application of 0007."""
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9999ms'").format(
                sql.Identifier(platform.controlplane_role)))
    finally:
        admin.close()
    drifted = _role_setting(platform.provision_dsn, platform.controlplane_role)
    assert drifted == ["statement_timeout=9999ms", "idle_in_transaction_session_timeout=5000ms"]
    rc = _run_apply(
        monkeypatch, platform, "0007_platform_declarations.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    reset = _role_setting(platform.provision_dsn, platform.controlplane_role)
    assert reset == ["statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms"]


def test_apply_platform_migration_0011_restores_a_manually_drifted_constraint(monkeypatch, platform):
    """A hand-narrowed
    `platform_declarations_key_check` does not survive an apply-platform-
    migration re-application of 0011. Connects with `provision_dsn`
    (the platform DATABASE, not the cluster-wide superuser connection
    `admin_dsn` defaults to) since this is a per-database ALTER TABLE,
    unlike the cluster-wide ALTER ROLE the 0007 test above uses."""
    admin = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT platform_declarations_key_check").format(
                sql.Identifier(platform.schema, "platform_declarations")))
            cur.execute(
                sql.SQL(
                    "ALTER TABLE {} ADD CONSTRAINT platform_declarations_key_check "
                    "CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles'))"
                ).format(sql.Identifier(platform.schema, "platform_declarations")))
    finally:
        admin.close()
    drifted = _constraint_definition(platform.provision_dsn, "platform_declarations_key_check")
    assert "process_ceilings" not in drifted
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 0
    restored = _constraint_definition(platform.provision_dsn, "platform_declarations_key_check")
    assert "process_ceilings" in restored
    assert "audit_writer_roles" in restored


def test_apply_platform_migration_0012_restores_a_manually_drifted_function_body(monkeypatch, platform):
    """A hand-edited
    `begin_provision_application` body does not survive an apply-
    platform-migration re-application of 0012."""
    marker = "NAMEDATALEN"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION {fn}(p_app_id text, p_runtime_password text, "
                    "p_developer_password text) RETURNS TABLE(database_name text, runtime_role text, "
                    "developer_role text) LANGUAGE plpgsql AS $fn$ BEGIN RAISE EXCEPTION 'drifted stub'; END; $fn$"
                ).format(fn=sql.Identifier(platform.schema, "begin_provision_application")))
    finally:
        conn.close()
    drifted_def, _ = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert marker not in drifted_def
    # R-12 (design D-6): `0012` alone is now refused by `apply-platform-
    # migration` (its own successors `0013`/`0014` are absent from this
    # single-file call) -- proven inline here too (scoped `MonkeyPatch.
    # context()`, undone before the psql-direct call below, so it never
    # leaks into it) -- this test's own subject is 0012's OWN restore-
    # on-reapply granularity, so the RESTORE itself is applied directly
    # via psql, never through the now-refusing subcommand.
    with pytest.MonkeyPatch.context() as ops_mp:
        calls = []
        ops_mp.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
        rc = _run_apply(ops_mp, platform, "0012_role_connection_limits.sql")
        assert rc == 2
        assert calls == []
    _run_psql(platform.provision_dsn, platform.migration_paths["0012_role_connection_limits.sql"])
    restored_def, _ = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert marker in restored_def
    assert "drifted stub" not in restored_def


# ===========================================================================
# 0013 -- role-level statement_timeout for auditreader and every
# application's own runtime/developer role
# ===========================================================================


def test_apply_platform_migration_0013_sets_statement_timeout_on_auditreader_database_independently(platform):
    """0013's own bootstrap application already declared
    `mitatedbsvc_auditreader`'s `statement_timeout`, database-
    independently (`setdatabase = 0`, the row `_role_setting` reads)."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    assert _role_setting(platform.provision_dsn, auditreader_role) == ["statement_timeout=5000ms"]


def test_apply_platform_migration_0013_sets_statement_timeout_on_pre_existing_application_roles():
    """0013's own per-application loop (section 2) retroactively
    declares `statement_timeout` on BOTH the runtime and developer role
    of every application already provisioned BEFORE 0013 first ran,
    observed across 2 applications (a single application could not tell
    this apart from a coincidence). Applies 0013 directly via psql
    (design D-6): a solo `0013` is now refused by `apply-platform-
    migration` (its own successor `0014` is absent from a single-file
    call) -- this test's own subject is 0013's SQL-level retroactive
    declare, unrelated to that refusal."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r45wpef102{secrets.token_hex(4)}"
    try:
        platform = _bootstrap(prefix, apply_0013=False)
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        _d1, rt1, dv1 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f102a")
        _d2, rt2, dv2 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f102b")
        for role in (rt1, dv1, rt2, dv2):
            assert _role_setting(platform.provision_dsn, role) is None
        _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
        for role in (rt1, dv1, rt2, dv2):
            assert _role_setting(platform.provision_dsn, role) == ["statement_timeout=5000ms"]
    finally:
        _sweep_prefix(admin_dsn, prefix)


def test_apply_platform_migration_0013_succeeds_with_an_unprovisioned_registry_row(platform):
    """A registry row that is registered but never provisioned
    (`runtime_role` NULL) is filtered out by the loop's own `WHERE`
    clause before either column's own value is ever read -- 0013 still
    succeeds, and the loop never touches a role an unfiltered row's own
    `developer_role` column happens to name (here, the unrelated
    provision role itself, which is a real row in `pg_roles`). Applies
    0013 directly via psql (design D-6, same reason as the sibling test
    above)."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {table} (application_id, developer_role) VALUES (%s, %s)").format(
                    table=sql.Identifier(platform.schema, "applications")),
                ["f103", platform.provision_role],
            )
    finally:
        conn.close()
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, platform.provision_role) is None


def test_apply_platform_migration_0013_sets_statement_timeout_on_both_branches_of_begin_provision_application(platform):
    """The first call to `begin_provision_application` for a
    fresh `application_id` takes the `CREATE ROLE` branch; calling it
    again for the SAME `application_id` (its own `database_name` column
    stays NULL until `finish_provision_application` runs, so this is not
    rejected as already-provisioned) takes the `duplicate_object` ->
    `ALTER ROLE` fallback branch instead -- both branches leave BOTH
    roles with the SAME `statement_timeout` declaration."""
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f104")
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, developer_role) == ["statement_timeout=5000ms"]

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(runtime_role)))
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(developer_role)))
    finally:
        admin.close()
    assert _role_setting(platform.provision_dsn, runtime_role) is None
    assert _role_setting(platform.provision_dsn, developer_role) is None

    _database_name_2, runtime_role_2, developer_role_2 = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f104")
    assert runtime_role_2 == runtime_role and developer_role_2 == developer_role
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, developer_role) == ["statement_timeout=5000ms"]


def _extract_function_block(text: str, function_name: str) -> "list[str]":
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if start is None and f"CREATE OR REPLACE FUNCTION mitatedb_registry.{function_name}(" in line:
            start = i
        if start is not None and line.startswith(f"REVOKE ALL ON FUNCTION mitatedb_registry.{function_name}("):
            end = i
            break
    assert start is not None and end is not None, (function_name, start, end)
    return lines[start:end + 1]


def test_apply_platform_migration_0013_function_body_differs_from_0012_only_by_the_added_statement_timeout_lines():
    """0013's own `CREATE OR REPLACE FUNCTION begin_provision_
    application` differs from 0012's identical block ONLY by 4 added
    `ALTER ROLE ... SET statement_timeout` lines (one per role, in both
    the `CREATE ROLE` branch and its own `duplicate_object` fallback) --
    CONNECTION LIMIT 36, the `application_id` pattern, the NAMEDATALEN
    check, the password-length check, the double-provision exception,
    `assert_role_has_no_memberships`, and the returned columns are all
    unchanged. The comparison is ORDER-PRESERVING: removing the added
    lines from 0013's own body must leave the EXACT line sequence 0012
    has, not merely the same multiset -- a reordered or misplaced branch
    would pass a multiset-only comparison but fails this one."""
    text_0012 = (MIGRATIONS_DIR / "0012_role_connection_limits.sql").read_text()
    text_0013 = (MIGRATIONS_DIR / "0013_role_statement_timeouts.sql").read_text()
    lines_0012 = [line.strip() for line in _extract_function_block(text_0012, "begin_provision_application")]
    lines_0013 = [line.strip() for line in _extract_function_block(text_0013, "begin_provision_application")]
    added_runtime_line = "EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_runtime_role, '5000ms');"
    added_developer_line = "EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_developer_role, '5000ms');"
    filtered_0013 = [line for line in lines_0013 if line not in (added_runtime_line, added_developer_line)]
    assert filtered_0013 == lines_0012
    assert lines_0013.count(added_runtime_line) == 2
    assert lines_0013.count(added_developer_line) == 2


def test_apply_platform_migration_0013_statement_timeout_values_are_a_single_positive_literal():
    """Every place 0013's own body places a `statement_timeout` value --
    the auditreader `ALTER ROLE` (section 1) and the 4 provisioning-time
    `EXECUTE format(...)` calls' own value argument (section 3) -- carries
    the exact SAME literal (the last quoted substring on each matching,
    comment-stripped line), never a mix of values; that one literal
    parses to a POSITIVE number of milliseconds through `pg_timeouts.
    ms_from_pg_timeout_text` (0 or negative would make `inventory`'s own
    item (6) `blocked` rather than `confirmed`)."""
    import re

    text = ops._strip_sql_line_comments((MIGRATIONS_DIR / "0013_role_statement_timeouts.sql").read_text())
    values = []
    for line in text.splitlines():
        if "statement_timeout" not in line:
            continue
        quoted = re.findall(r"'([^']*)'", line)
        if quoted:
            values.append(quoted[-1])
    assert len(values) >= 1
    assert len(values) == 7
    assert set(values) == {"5000ms"}
    assert ops.pg_timeouts.ms_from_pg_timeout_text(values[0]) > 0


def test_apply_platform_migration_solo_0013_is_rejected_by_the_subcommand(monkeypatch, capsys, platform):
    """0013 is a known name (present in the pinned constant), but the
    real subcommand now refuses it ALONE -- its own successor `0014`
    (`_PLATFORM_MIGRATION_SUPERSEDED_BY`) is absent from a single-file
    call (design D-2, R-57). No psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0013_role_statement_timeouts.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: 0013_role_statement_timeouts.sql is superseded by a later "
        "platform migration; apply the whole run in one call, in this order: "
        "0013_role_statement_timeouts.sql 0014_role_connection_limits_rollout.sql"
    )


def test_apply_platform_migration_variable_table_keys_match_the_filenames_constant():
    """`_PLATFORM_MIGRATION_VARIABLE_TABLE`'s own key set
    equals `_PLATFORM_MIGRATION_FILENAMES` exactly -- no accepted file
    missing a variable-table entry, no stale entry for a file no longer
    accepted."""
    assert set(ops._PLATFORM_MIGRATION_VARIABLE_TABLE.keys()) == set(ops._PLATFORM_MIGRATION_FILENAMES)


def test_apply_platform_migration_0013_revokes_public_execute_on_the_replaced_function(platform):
    """0013's own `REVOKE ALL ON FUNCTION ... FROM PUBLIC`
    runs every time it (re)applies the function -- a hand-added PUBLIC
    EXECUTE grant does not survive a reapplication of 0013 (0012's own
    prior REVOKE would already leave the ACL clean on a fresh bootstrap,
    so this test grants PUBLIC EXECUTE back by hand first to prove 0013's
    OWN REVOKE, not merely 0012's, is what keeps it closed). Applies
    0013 directly via psql (design D-6): a solo `0013` is now refused
    by `apply-platform-migration`."""
    function_signature = f"{platform.schema}.begin_provision_application(text, text, text)"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {fn} TO PUBLIC").format(fn=sql.SQL(function_signature)))
    finally:
        conn.close()
    _, acl = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert _acl_has_public_grantee(acl)
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    _, acl = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert not _acl_has_public_grantee(acl)


def test_apply_platform_migration_0013_restores_manually_drifted_settings_and_function_body(platform):
    """Hand-drifted `mitatedbsvc_auditreader` setting, a
    pre-existing application's own runtime-role setting, and the
    replaced `begin_provision_application` body all get restored by
    re-applying 0013 -- this file ALONE restores its own targets, a
    granularity design R-12/D-6 keeps by applying 0013 directly via
    psql (a solo `0013` is now refused by `apply-platform-migration`);
    a second re-application changes nothing further."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _database_name, runtime_role, _developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f111")
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(auditreader_role)))
    finally:
        admin.close()
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(runtime_role)))
    finally:
        conn.close()
    marker = "NAMEDATALEN"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION {fn}(p_app_id text, p_runtime_password text, "
                    "p_developer_password text) RETURNS TABLE(database_name text, runtime_role text, "
                    "developer_role text) LANGUAGE plpgsql AS $fn$ BEGIN RAISE EXCEPTION 'drifted stub'; END; $fn$"
                ).format(fn=sql.Identifier(platform.schema, "begin_provision_application")))
    finally:
        conn.close()

    assert _role_setting(platform.provision_dsn, auditreader_role) is None
    assert _role_setting(platform.provision_dsn, runtime_role) is None
    drifted_def, _ = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert marker not in drifted_def

    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, auditreader_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    restored_def, _ = _function_def_and_acl(platform.provision_dsn, platform.schema, "begin_provision_application")
    assert marker in restored_def
    assert "drifted stub" not in restored_def

    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, auditreader_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]


def test_apply_platform_migration_0013_then_0012_then_0013_restores_new_application_setting(platform):
    """0012 and 0013 `CREATE OR REPLACE` the
    identical function -- applying 0012 alone after 0013 drops the
    `statement_timeout` lines for FUTURE applications; applying 0013 once
    more restores them, observed on an application provisioned after the
    stray 0012 re-application. Each of the 3 files is applied directly
    via psql (design D-6): this exact stray-single-file sequence is
    precisely what `apply-platform-migration` now refuses through the
    subcommand (design D-2) -- the SQL-level restore behavior this test
    is about is independent of that refusal."""
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    _run_psql(platform.provision_dsn, platform.migration_paths["0012_role_connection_limits.sql"])
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f113")
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, developer_role) == ["statement_timeout=5000ms"]


def test_apply_platform_migration_0013_is_transactional_and_rolls_back_on_permission_failure(platform):
    """A per-application role 0013's own applying role
    (`mitatedbsvc_provision`) lacks ADMIN OPTION on (created directly by
    the cluster admin, not by `begin_provision_application`, so
    CREATEROLE's own implicit ADMIN OPTION never attaches) makes the
    whole loop fail; the auditreader `ALTER ROLE` from section 1 rolls
    back with it, so nothing is left half-applied. Applies 0013 directly
    via psql (design D-6): a solo `0013` is now refused by
    `apply-platform-migration` before ANY psql subprocess starts, which
    would make this SQL-level failure unreachable through the
    subcommand."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(auditreader_role)))
    finally:
        admin.close()
    assert _role_setting(platform.provision_dsn, auditreader_role) is None

    foreign_role = f"{platform.prefix}foreignrole"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            ).format(sql.Identifier(foreign_role), sql.Literal(secrets.token_urlsafe(24))))
    finally:
        admin.close()
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (application_id, runtime_role, developer_role) VALUES (%s, %s, %s)"
                ).format(table=sql.Identifier(platform.schema, "applications")),
                ["f114", foreign_role, foreign_role],
            )
    finally:
        conn.close()

    with pytest.raises(RuntimeError):
        _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, auditreader_role) is None


def test_apply_platform_migration_0013_skips_a_registry_row_with_no_matching_role(platform):
    """A registry row naming a role `pg_roles` no longer
    carries (a deprovisioned application whose own row survived) is
    skipped rather than aborting the whole migration; that row's own
    role never picks up the setting, since 0013 never touched it.
    Applies 0013 directly via psql (design D-6): a solo `0013` is now
    refused by `apply-platform-migration`."""
    ghost_runtime = f"{platform.prefix}_app_f115_rt"
    ghost_developer = f"{platform.prefix}_app_f115_dv"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (application_id, runtime_role, developer_role) VALUES (%s, %s, %s)"
                ).format(table=sql.Identifier(platform.schema, "applications")),
                ["f115", ghost_runtime, ghost_developer],
            )
    finally:
        conn.close()
    _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, ghost_runtime) is None


def test_apply_platform_migration_0013_fails_when_auditreader_was_created_by_a_different_role():
    """A cluster where `mitatedbsvc_auditreader` was
    created by the cluster admin role directly (never by the applying
    provision role, so CREATEROLE's own implicit ADMIN OPTION never
    attaches to it) makes 0013 fail; neither an application role
    setting nor the replaced function body ever appear. Applies 0013
    directly via psql (design D-6): a solo `0013` is now refused by
    `apply-platform-migration` before ANY psql subprocess starts, which
    would make this SQL-level failure unreachable through the
    subcommand."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r45wpef118{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)
    auditreader_role = f"{prefix}svc_auditreader"

    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_apm_f118_"))
    rewritten: "dict[str, Path]" = {}
    for name in (
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
        "0007_platform_declarations.sql", "0011_process_ceilings.sql",
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out
    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        # 0005 is never applied in this fixture at all (the cluster admin
        # creates `mitatedbsvc_auditreader` directly instead) -- this has
        # no bearing on this test's own subject, CREATEROLE's own
        # implicit ADMIN OPTION, granted only to a role's own creator.
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5"
                ).format(sql.Identifier(auditreader_role), sql.Literal(secrets.token_urlsafe(24))))
        finally:
            admin.close()
        _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"],
                 {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
        _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])

        with pytest.raises(RuntimeError):
            _run_psql(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])
        assert _role_setting(provision_dsn, auditreader_role) is None
        function_def, _ = _function_def_and_acl(provision_dsn, schema, "begin_provision_application")
        assert "statement_timeout" not in (function_def or "")
    finally:
        _sweep_prefix(admin_dsn, prefix)


def test_apply_platform_migration_0013_section_3_permission_failure_rolls_back_sections_1_and_2(platform):
    """Section 1 (the auditreader `ALTER ROLE`), section 2 (the
    per-application loop), and section 3 (`CREATE OR REPLACE FUNCTION`)
    all run inside the SAME transaction -- a permission failure confined
    to section 3 (the applying role no longer owns `begin_provision_
    application`, so `CREATE OR REPLACE FUNCTION` is refused) rolls back
    section 1 and section 2's own changes from THIS run too, not merely
    section 3's own attempted change. Applies 0013 directly via psql
    (design D-6): a solo `0013` is now refused by `apply-platform-
    migration` before ANY psql subprocess starts, which would make this
    SQL-level failure unreachable through the subcommand."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _database_name, runtime_role, _developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f119")

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(auditreader_role)))
    finally:
        admin.close()
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(runtime_role)))
    finally:
        conn.close()
    assert _role_setting(platform.provision_dsn, auditreader_role) is None
    assert _role_setting(platform.provision_dsn, runtime_role) is None

    other_owner = conninfo_to_dict(platform.admin_dsn)["user"]
    admin_on_platform_db = psycopg.connect(
        _dsn_with(platform.admin_dsn, dbname=platform.platform_db), autocommit=True)
    try:
        with admin_on_platform_db.cursor() as cur:
            cur.execute(sql.SQL(
                "ALTER FUNCTION {}.begin_provision_application(text, text, text) OWNER TO {}"
            ).format(sql.Identifier(platform.schema), sql.Identifier(other_owner)))
    finally:
        admin_on_platform_db.close()

    with pytest.raises(RuntimeError):
        _run_psql(platform.provision_dsn, platform.migration_paths["0013_role_statement_timeouts.sql"])
    assert _role_setting(platform.provision_dsn, auditreader_role) is None
    assert _role_setting(platform.provision_dsn, runtime_role) is None


# ===========================================================================
# 0014 -- rollout-time role `CONNECTION LIMIT`
# (design `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §4)
# ===========================================================================


def test_apply_platform_migration_0014_sets_role_connection_limits_for_every_role_class(monkeypatch, platform):
    """W1-1: after 0014, the 3 platform-plane roles read 132/36/12
    (api/controlplane/auditreader) and every ALREADY-PROVISIONED
    application's own runtime/developer role reads 68 -- observed across
    2 applications provisioned BEFORE 0014 runs."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _d1, rt1, dv1 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f120a")
    _d2, rt2, dv2 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f120b")

    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0

    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 132
    assert _role_connlimit(platform.provision_dsn, platform.controlplane_role) == 36
    assert _role_connlimit(platform.provision_dsn, auditreader_role) == 12
    for role in (rt1, dv1, rt2, dv2):
        assert _role_connlimit(platform.provision_dsn, role) == 68


def test_apply_platform_migration_0014_new_application_connection_limit_is_68(monkeypatch, platform):
    """W1-2 (new-creation branch): an application provisioned AFTER 0014
    is created directly with `CONNECTION LIMIT 68` on both roles."""
    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f121")
    assert _role_connlimit(platform.provision_dsn, runtime_role) == 68
    assert _role_connlimit(platform.provision_dsn, developer_role) == 68


def test_apply_platform_migration_0014_duplicate_object_fallback_connection_limit_is_68(monkeypatch, platform):
    """W1-2 (`duplicate_object` fallback branch): calling `begin_
    provision_application` twice for the SAME `application_id` (its
    `database_name` stays NULL after the first call, since `finish_
    provision_application` never runs here) exercises the `ALTER ROLE`
    retry-safety branch on the second call -- still 68 on both roles."""
    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0
    _provision_app_via_function(platform.provision_dsn, platform.schema, "f122")
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f122")
    assert _role_connlimit(platform.provision_dsn, runtime_role) == 68
    assert _role_connlimit(platform.provision_dsn, developer_role) == 68


def test_apply_platform_migration_0014_preserves_0013_statement_timeout_on_provisioned_roles(monkeypatch, platform):
    """W1-3: an application provisioned AFTER 0014 still carries 0013's
    own `statement_timeout` setting on both roles -- 0014's own `CREATE
    OR REPLACE FUNCTION` does not drop the setting 0013 added."""
    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f123")
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, developer_role) == ["statement_timeout=5000ms"]


def test_apply_platform_migration_0014_is_transactional_and_rolls_back_on_permission_failure(monkeypatch, platform):
    """W1-4: a registry row naming a role 0014's own applying role
    (`mitatedbsvc_provision`) lacks ADMIN OPTION on (created directly by
    the cluster admin, not by `begin_provision_application`, so
    CREATEROLE's own implicit ADMIN OPTION never attaches) makes the
    whole per-application loop fail; the platform-plane roles' own
    `ALTER ROLE` from section 1 (which runs first) rolls back with it,
    so nothing from this run is left half-applied."""
    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 68
    foreign_role = f"{platform.prefix}foreignrole014"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            ).format(sql.Identifier(foreign_role), sql.Literal(secrets.token_urlsafe(24))))
    finally:
        admin.close()
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (application_id, runtime_role, developer_role) VALUES (%s, %s, %s)"
                ).format(table=sql.Identifier(platform.schema, "applications")),
                ["f124", foreign_role, foreign_role],
            )
    finally:
        conn.close()

    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc != 0
    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 68


def test_apply_platform_migration_0014_survives_a_registry_role_dropped_before_it_runs(monkeypatch, platform):
    """W1-14 (remand 1, item 1): a registry row whose runtime/developer
    role was `DROP ROLE`d directly (the shape `0004_deprovision_
    application.sql` can leave behind if it fails between its own `DROP
    ROLE` and `finish_deprovision_application`) does not abort 0014 --
    section 2's loop below carries the same `IF EXISTS (SELECT 1 FROM
    pg_roles WHERE rolname = ...)` guard 0013's own section 2 carries
    (0013:91-96). The platform-plane roles and a second, still-real
    application's own roles still reach 132/36/12/68."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _d1, rt1, dv1 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f125a")
    _d2, rt2, dv2 = _provision_app_via_function(platform.provision_dsn, platform.schema, "f125b")

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(rt1)))
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(dv1)))
    finally:
        admin.close()
    assert _role_connlimit(platform.provision_dsn, rt1) is None
    assert _role_connlimit(platform.provision_dsn, dv1) is None

    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0

    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 132
    assert _role_connlimit(platform.provision_dsn, platform.controlplane_role) == 36
    assert _role_connlimit(platform.provision_dsn, auditreader_role) == 12
    for role in (rt2, dv2):
        assert _role_connlimit(platform.provision_dsn, role) == 68


def test_apply_platform_migration_accepts_0014_via_the_subcommand(monkeypatch, platform):
    """0014 is accepted by name through the real subcommand (not merely
    present in the pinned constant)."""
    rc = _run_apply(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0


# ===========================================================================
# audit-only -- the connection target used by every test above
# ===========================================================================

# `_admin_dsn` (this file, line ~44) reads `MITATEDB_TEST_ADMIN_DSN` --
# the SAME test-infrastructure-managed throwaway-cluster admin DSN every
# other MitateDB-api test module uses (`tools/testpg/dsa_testpg.py` sets
# it per run; there is no shared-cluster default, `_admin_dsn`'s own
# RuntimeError above). No test in this file ever reads a production
# connection string.


# ===========================================================================
# the psql-variable table and extraction rule
# ===========================================================================


def test_apply_platform_migration_variable_table_matches_each_files_own_references():
    """The table's own required-variable set for each file
    matches that file's REAL `:name` references, extracted by
    `_extract_psql_variables`."""
    for name, required in ops._PLATFORM_MIGRATION_VARIABLE_TABLE.items():
        actual = ops._extract_psql_variables((MIGRATIONS_DIR / name).read_text())
        assert set(required) == actual, (name, required, actual)


def test_apply_platform_migration_extraction_excludes_comments_and_casts():
    """A synthetic SQL string proves the
    extraction rule excludes `--` line comments and `::` type casts, on
    both sides of a positive case."""
    synthetic = "SELECT :'foo'::text, :bar -- a comment mentioning :not_a_variable\n"
    assert ops._extract_psql_variables(synthetic) == {"foo", "bar"}


def _extract_bare_psql_variables(text: str) -> "set[str]":
    """The subset of `ops._PSQL_VARIABLE_RE`'s own matches that are the
    BARE `:name` form (never `:'name'`/`:"name"`) -- reuses the SAME
    regex and comment-stripping rule `ops._extract_psql_variables`
    applies (`ops._strip_sql_line_comments`), so the quoted-vs-bare
    judgment never drifts from the real extraction behavior."""
    stripped = ops._strip_sql_line_comments(text)
    return {
        match.group(3)
        for match in ops._PSQL_VARIABLE_RE.finditer(stripped)
        if match.group(3)
    }


def test_apply_platform_migration_variables_are_referenced_only_in_quoted_form():
    """psql's own quoted interpolation
    (`:"name"`/`:'name'`) is what makes a role-name argument safe to
    substitute into DDL -- no value validation is layered on top of it.
    Each of the 7 accepted platform migration files
    references its own psql variables only through that quoted form; a
    bare `:name` reference is never present. 0007 has at least one
    quoted reference (non-vacuous)."""
    quoted_reference_seen = False
    for name in ops._PLATFORM_MIGRATION_FILENAMES:
        text = (MIGRATIONS_DIR / name).read_text()
        assert _extract_bare_psql_variables(text) == set(), name
        if ops._extract_psql_variables(text):
            quoted_reference_seen = True
    assert quoted_reference_seen


def test_bare_psql_variable_detection_catches_a_synthetic_bare_reference():
    """The bare-form detector is exercised against
    a synthetic SQL string containing one bare and one quoted reference
    -- proves the detector is non-vacuous (catches a real bare form,
    never just an always-empty result)."""
    synthetic = "SELECT :api_role, :'quoted_role'\n"
    assert _extract_bare_psql_variables(synthetic) == {"api_role"}


def test_apply_platform_migration_missing_required_variable_is_rejected(monkeypatch, capsys, platform):
    """0007 without `--controlplane-role` is refused before
    any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0007_platform_declarations.sql", api_role=platform.api_role)
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "--controlplane-role" in captured.err


def test_apply_platform_migration_unexpected_variable_is_rejected(monkeypatch, capsys, platform):
    """0011 (which takes no variables) with `--api-role`
    supplied is refused before any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0011_process_ceilings.sql", api_role="somerole")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "--api-role" in captured.err


def test_apply_platform_migration_missing_variable_message_is_deterministic_by_table_order(
    monkeypatch, capsys, platform,
):
    """R-57 WP-1 code review fix 2: with BOTH `--api-role`/
    `--controlplane-role` omitted, the missing-variable message always
    names `--api-role` FIRST -- `_PLATFORM_MIGRATION_VARIABLE_TABLE
    ["0007_platform_declarations.sql"]`'s own tuple order -- never a
    name that depends on Python's own (hash-randomized) `set`
    iteration order."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply(monkeypatch, platform, "0007_platform_declarations.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "--api-role" in captured.err
    assert "--controlplane-role" not in captured.err


def test_apply_platform_migration_run_unexpected_variable_message_names_no_file(monkeypatch, capsys, platform):
    """R-57 WP-1 code review fix 7 (裁定): a run of 2+ files rejects an
    unexpected variable naming NO file (which file, if any, would have
    accepted it depends on every other file in the run, not a fixed
    position) -- distinct from the single-file message above, which
    keeps the basis form."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform,
        "0011_process_ceilings.sql", "0012_role_connection_limits.sql",
        "0013_role_statement_timeouts.sql", "0014_role_connection_limits_rollout.sql",
        api_role="somerole",
    )
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: apply-platform-migration: no file in this run accepts --api-role"


# ===========================================================================
# D-3 -- the target-level map ("target -> the files, in
# `_PLATFORM_MIGRATION_FILENAMES` order, that define it") that
# `ops._PLATFORM_MIGRATION_SUPERSEDED_BY` is proved to derive from, at
# file granularity. "Target" = (role or function identifier, setting
# kind) per design R-10: a literal role name, a psql `:"name"`
# variable's own NAME, or a plpgsql expression's own source text (e.g.
# `app.runtime_role`) as identifier; `CONNECTION LIMIT`, `SET <param>`,
# or `function body` as kind. This machinery reads the 7 accepted
# migration files directly -- it is test-only static analysis, never
# part of `ops.py`'s own runtime surface.
# ===========================================================================

#: code review round 1 (高 1): `OR REPLACE` is OPTIONAL -- a bare
#: `CREATE FUNCTION` defines a function body target exactly the same
#: way a `CREATE OR REPLACE FUNCTION` does; requiring `OR REPLACE`
#: would silently miss a plain `CREATE FUNCTION`'s own body (never
#: exclude it from scanning, never register it as a target either).
_FUNCTION_HEADER_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z0-9_.]+)\s*\(.*?\)\s*RETURNS[^;]*?AS\s+(\$\w*\$)",
    re.DOTALL,
)
_IF_NOT_EXISTS_GUARDED_BLOCK_RE = re.compile(r"IF NOT EXISTS\s*\(.*?\)\s*THEN.*?END IF;", re.DOTALL)
_CREATE_ROLE_CONNECTION_LIMIT_RE = re.compile(r"CREATE ROLE\s+(\S+)\s+LOGIN PASSWORD[^;]*?CONNECTION LIMIT")
_ALTER_ROLE_CONNECTION_LIMIT_RE = re.compile(r"ALTER ROLE\s+(\S+)\s+CONNECTION LIMIT")
_ALTER_ROLE_SET_RE = re.compile(r"ALTER ROLE\s+(\S+)\s+SET\s+(\w+)")
_FORMAT_ALTER_ROLE_CONNECTION_LIMIT_RE = re.compile(
    r"format\(\s*'ALTER ROLE %I CONNECTION LIMIT\s+\d+'\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)"
)
_FORMAT_ALTER_ROLE_SET_RE = re.compile(
    r"format\(\s*'ALTER ROLE %I SET (\w+)\s*=\s*%L'\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)\s*,"
)


def _normalize_role_identifier(raw: str) -> str:
    """R-10: a literal role name is used AS-IS; a psql `:"name"`/
    `:'name'` variable reference is reduced to its own NAME (never the
    `:"..."` wrapper) -- it is the VARIABLE, not this particular
    quoting, that identifies the target across files."""
    match = re.fullmatch(r':"([A-Za-z_][A-Za-z0-9_]*)"', raw) or re.fullmatch(r":'([A-Za-z_][A-Za-z0-9_]*)'", raw)
    return match.group(1) if match else raw


def _blank_span(text: str, start: int, end: int) -> str:
    """Replaces `text[start:end]` with an equal-length run of spaces
    (never removes characters), so every later match's own OFFSET into
    the ORIGINAL text stays meaningful."""
    return text[:start] + (" " * (end - start)) + text[end:]


def _strip_function_bodies(text: str) -> "tuple[str, list[tuple[str, str]]]":
    """Removes every `CREATE OR REPLACE FUNCTION ... AS $tag$ ... $tag$`
    span (header AND body) from `text`, registering ONE `(identifier,
    "function body")` target per span -- the body's own content (e.g.
    an `EXECUTE format('ALTER ROLE %I ...')` call) is never
    independently scanned; it is part of this ONE target, not a target
    of its own (design D-3)."""
    targets: "list[tuple[str, str]]" = []
    result = text
    while True:
        header_match = _FUNCTION_HEADER_RE.search(result)
        if header_match is None:
            break
        tag = header_match.group(2)
        close = result.find(tag, header_match.end())
        if close == -1:
            break
        span_end = close + len(tag)
        targets.append((header_match.group(1), "function body"))
        result = _blank_span(result, header_match.start(), span_end)
    return result, targets


def _strip_if_not_exists_guarded_blocks(text: str) -> str:
    """Removes every `IF NOT EXISTS (...) THEN ... END IF;` span --
    e.g. `0005_application_audit.sql`'s own conditional `CREATE ROLE
    mitatedbsvc_auditreader ... CONNECTION LIMIT 5` -- so a value only
    ever set when the target does not YET exist is never registered as
    a target competing with a later file's own unconditional `ALTER
    ROLE`. Deliberately anchored on the literal `IF NOT EXISTS` (never
    bare `IF EXISTS`), so the skip guards `0013_role_statement_
    timeouts.sql`/`0014_role_connection_limits_rollout.sql`'s own
    section 2 use (`IF EXISTS (SELECT 1 FROM pg_roles ...)`) are left
    untouched (design D-3's "走査の規則"). LIMITATION (R-57 WP-1 code
    review, 低 6, 裁定): a guard with a NESTED `IF`/`END IF;` closes on
    the INNER `END IF;` (`.*?` is non-greedy) rather than its own outer
    one -- none of the 7 accepted migration files has this shape today,
    and the failure mode is over-detection (an extra target, a red
    test), never a silently missed one, so this is accepted rather than
    fixed."""
    return _IF_NOT_EXISTS_GUARDED_BLOCK_RE.sub("", text)


def _extract_role_setting_targets(text: str) -> "list[tuple[str, str]]":
    """Every `CONNECTION LIMIT`/`SET <param>` target `text` carries --
    direct SQL (`ALTER ROLE <role> CONNECTION LIMIT`/`SET <param>`,
    `CREATE ROLE <role> ... CONNECTION LIMIT`) and DO-block dynamic SQL
    (`format('ALTER ROLE %I CONNECTION LIMIT ...', <expr>)`/
    `format('ALTER ROLE %I SET <param> = %L', <expr>, ...)`) alike. The
    dynamic forms are matched and blanked FIRST, so a direct-SQL regex
    never mistakes the literal `%I` placeholder inside a `format(...)`
    string argument for a role name."""
    targets: "list[tuple[str, str]]" = []
    working = text
    for match in _FORMAT_ALTER_ROLE_CONNECTION_LIMIT_RE.finditer(working):
        targets.append((match.group(1), "CONNECTION LIMIT"))
    working = _FORMAT_ALTER_ROLE_CONNECTION_LIMIT_RE.sub("", working)
    for match in _FORMAT_ALTER_ROLE_SET_RE.finditer(working):
        targets.append((match.group(2), f"SET {match.group(1)}"))
    working = _FORMAT_ALTER_ROLE_SET_RE.sub("", working)
    for match in _CREATE_ROLE_CONNECTION_LIMIT_RE.finditer(working):
        targets.append((_normalize_role_identifier(match.group(1)), "CONNECTION LIMIT"))
    for match in _ALTER_ROLE_CONNECTION_LIMIT_RE.finditer(working):
        targets.append((_normalize_role_identifier(match.group(1)), "CONNECTION LIMIT"))
    for match in _ALTER_ROLE_SET_RE.finditer(working):
        targets.append((_normalize_role_identifier(match.group(1)), f"SET {match.group(2)}"))
    return targets


def _platform_migration_targets_in_file(path: Path) -> "list[tuple[str, str]]":
    text = ops._strip_sql_line_comments(path.read_text())
    text, function_targets = _strip_function_bodies(text)
    text = _strip_if_not_exists_guarded_blocks(text)
    return function_targets + _extract_role_setting_targets(text)


def _derive_platform_migration_target_map() -> "dict[tuple[str, str], tuple[str, ...]]":
    """D-3: `target -> the files (in `_PLATFORM_MIGRATION_FILENAMES`
    order) that define it`, derived from the 7 accepted migration files
    themselves -- this is the thing D-3 FIXES; `ops._PLATFORM_
    MIGRATION_SUPERSEDED_BY` is proved (below) to be exactly what this
    map derives at file granularity, never the other way around."""
    target_map: "dict[tuple[str, str], list[str]]" = {}
    for name in ops._PLATFORM_MIGRATION_FILENAMES:
        for target in _platform_migration_targets_in_file(MIGRATIONS_DIR / name):
            target_map.setdefault(target, []).append(name)
    return {target: tuple(files) for target, files in target_map.items()}


def _file_level_superseded_by(
    target_map: "dict[tuple[str, str], tuple[str, ...]]",
) -> "dict[str, tuple[str, ...]]":
    """Folds the target-level map down to `file -> the files, in order,
    that redefine at least one of its own targets` -- the SAME shape as
    `ops._PLATFORM_MIGRATION_SUPERSEDED_BY`. A target defined by only
    ONE file contributes no entry (nothing to be superseded BY)."""
    successors: "dict[str, set]" = {}
    for files in target_map.values():
        for i, name in enumerate(files[:-1]):
            successors.setdefault(name, set()).update(files[i + 1:])
    order = {name: i for i, name in enumerate(ops._PLATFORM_MIGRATION_FILENAMES)}
    return {
        name: tuple(sorted(later, key=order.__getitem__))
        for name, later in successors.items()
    }


def test_platform_migration_target_map_contains_the_4_known_targets():
    """Completion condition 1 (non-vacuousness, design D-7 #1): the
    derived target-level map contains the function-body target and 3
    of the `CONNECTION LIMIT` targets `_PLATFORM_MIGRATION_SUPERSEDED_
    BY`'s own file-level chain depends on."""
    target_map = _derive_platform_migration_target_map()
    known = {
        ("mitatedb_registry.begin_provision_application", "function body"): (
            "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
            "0014_role_connection_limits_rollout.sql",
        ),
        ("mitatedbsvc_api", "CONNECTION LIMIT"): (
            "0012_role_connection_limits.sql", "0014_role_connection_limits_rollout.sql",
        ),
        ("mitatedbsvc_controlplane", "CONNECTION LIMIT"): (
            "0012_role_connection_limits.sql", "0014_role_connection_limits_rollout.sql",
        ),
        ("app.runtime_role", "CONNECTION LIMIT"): (
            "0012_role_connection_limits.sql", "0014_role_connection_limits_rollout.sql",
        ),
    }
    assert len(known) >= 1
    for target, files in known.items():
        assert target_map.get(target) == files, target


def test_platform_migration_target_map_excludes_the_if_not_exists_guarded_auditreader_creation():
    """Completion condition 2: `0005`'s own conditional `CREATE ROLE
    mitatedbsvc_auditreader ... CONNECTION LIMIT 5` never appears as a
    `CONNECTION LIMIT`-kind target competing with 0014's own
    unconditional `ALTER ROLE mitatedbsvc_auditreader CONNECTION LIMIT
    12` -- the target's own file list is `(0014,)`, never `(0005,
    0014)`."""
    target_map = _derive_platform_migration_target_map()
    assert target_map[("mitatedbsvc_auditreader", "CONNECTION LIMIT")] == (
        "0014_role_connection_limits_rollout.sql",
    )


def test_platform_migration_target_map_includes_the_if_exists_skip_guarded_alters():
    """Completion condition 2b: the `IF EXISTS (SELECT 1 FROM pg_roles
    ...)` skip guard inside 0013's/0014's own per-application loop does
    NOT exclude the `ALTER ROLE` it guards -- both `app.runtime_role`
    and `app.developer_role`'s own `CONNECTION LIMIT` targets are
    present, spanning 0012 -> 0014."""
    target_map = _derive_platform_migration_target_map()
    for identifier in ("app.runtime_role", "app.developer_role"):
        assert target_map[(identifier, "CONNECTION LIMIT")] == (
            "0012_role_connection_limits.sql", "0014_role_connection_limits_rollout.sql",
        )


def test_platform_migration_target_map_never_scans_inside_a_function_body():
    """Completion condition 2c: the `EXECUTE format('ALTER ROLE %I SET
    statement_timeout ...')` lines inside 0013's/0014's own replacement
    `begin_provision_application` body never surface as independent
    `v_runtime_role`/`v_developer_role` targets -- they are part of
    the ONE `function body` target, never scanned on their own
    (code review round 1: docstring corrected to name only what this
    assert covers -- `--` comment stripping is `ops._strip_sql_line_
    comments`'s own subject, not this test's)."""
    target_map = _derive_platform_migration_target_map()
    for identifier in ("v_runtime_role", "v_developer_role"):
        assert (identifier, "SET statement_timeout") not in target_map


def test_platform_migration_function_header_regex_matches_a_bare_create_function_too():
    """Code review round 1, 高 1: a bare `CREATE FUNCTION` (never `OR
    REPLACE`) is scanned as a function-body target too -- two synthetic
    SQL strings, one plain `CREATE FUNCTION` and one `CREATE OR REPLACE
    FUNCTION`, fold to the exact SAME `(identifier, "function body")`
    target."""
    plain = "CREATE FUNCTION pkg.f(a int) RETURNS int LANGUAGE plpgsql AS $fn$ BEGIN RETURN a; END; $fn$;"
    replaced = "CREATE OR REPLACE FUNCTION pkg.f(a int) RETURNS int LANGUAGE plpgsql AS $fn$ BEGIN RETURN a; END; $fn$;"
    _, plain_targets = _strip_function_bodies(plain)
    _, replaced_targets = _strip_function_bodies(replaced)
    assert plain_targets == replaced_targets == [("pkg.f", "function body")]


def test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level():
    """Completion condition 1b: `ops._PLATFORM_MIGRATION_SUPERSEDED_BY`
    is exactly what the target-level map derives at file granularity."""
    target_map = _derive_platform_migration_target_map()
    assert _file_level_superseded_by(target_map) == ops._PLATFORM_MIGRATION_SUPERSEDED_BY


# ===========================================================================
# D-1/D-2/D-4 -- a RUN of one or more FILENAMEs
# ===========================================================================


def test_apply_platform_migration_run_of_0012_0013_0014_succeeds_in_one_call(monkeypatch, platform):
    """Completion condition 6: the whole numbered run, given as 3
    FILENAMEs in one call, applies all 3 in order with a single call to
    `apply-platform-migration`."""
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 0


def test_apply_platform_migration_run_reports_applied_per_file(monkeypatch, platform, capsys):
    """Completion condition 6: `applied <file>` is printed once per
    FILENAME in the run, in order."""
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "applied 0012_role_connection_limits.sql",
        "applied 0013_role_statement_timeouts.sql",
        "applied 0014_role_connection_limits_rollout.sql",
    ]


def test_apply_platform_migration_solo_0012_is_rejected_with_the_confirmed_closure_message(
    monkeypatch, capsys, platform,
):
    """Completion condition 3a/3b: `0012` alone (its own successors
    `0013`/`0014` both absent from the call) is refused before any psql
    subprocess starts, with the confirmed T-1 message naming the FULL
    required run."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0012_role_connection_limits.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: 0012_role_connection_limits.sql is superseded by a later "
        "platform migration; apply the whole run in one call, in this order: "
        "0012_role_connection_limits.sql 0013_role_statement_timeouts.sql 0014_role_connection_limits_rollout.sql"
    )


def test_apply_platform_migration_0012_0014_without_0013_is_rejected(monkeypatch, capsys, platform):
    """Completion condition 3a: `0012 0014` (skipping `0013`, one of
    `0012`'s own successors) is refused before any psql subprocess
    starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform, "0012_role_connection_limits.sql", "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 2
    assert calls == []


def test_apply_platform_migration_out_of_order_run_is_rejected(monkeypatch, capsys, platform):
    """Completion condition 4: `0013 0012 0014` (not ascending in
    `_PLATFORM_MIGRATION_FILENAMES` order) is refused with the
    confirmed T-2 message."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform,
        "0013_role_statement_timeouts.sql", "0012_role_connection_limits.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: FILENAMEs must be given in migration order, each at most once"
    )


def test_apply_platform_migration_duplicate_filename_in_run_is_rejected(monkeypatch, capsys, platform):
    """Completion condition 4: a repeated FILENAME in the same run
    (`0011 0011`) is refused with the confirmed T-2 message."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0011_process_ceilings.sql", "0011_process_ceilings.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: FILENAMEs must be given in migration order, each at most once"
    )


def test_apply_platform_migration_solo_0011_still_passes_the_closure_check(monkeypatch, platform):
    """Completion condition 5: `0011` alone (no successors) still
    passes the closure check -- unaffected by D-1/D-2."""
    rc = _run_apply_run(monkeypatch, platform, "0011_process_ceilings.sql")
    assert rc == 0


def test_apply_platform_migration_solo_0014_still_passes_the_closure_check(monkeypatch, platform):
    """Completion condition 5: `0014` alone (no successors, the LAST
    file in `_PLATFORM_MIGRATION_FILENAMES`) still passes the closure
    check."""
    rc = _run_apply_run(monkeypatch, platform, "0014_role_connection_limits_rollout.sql")
    assert rc == 0


def test_apply_platform_migration_run_psql_argv_carries_only_each_files_own_variables(monkeypatch, platform):
    """Completion condition 6: psql variables are narrowed to EACH
    file's own required subset -- `0007`'s own run-wide `--api-role`/
    `--controlplane-role` never reach `0011`'s own psql invocation."""
    captured_argvs = []
    real_run = subprocess.run

    def _spy_run(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured_argvs.append(argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)
    rc = _run_apply_run(
        monkeypatch, platform, "0007_platform_declarations.sql", "0011_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    assert len(captured_argvs) == 2
    assert "-v" in captured_argvs[0] and f"api_role={platform.api_role}" in captured_argvs[0]
    assert f"api_role={platform.api_role}" not in captured_argvs[1]
    # `0011` requires no variables at all -- ONLY the constant
    # `ON_ERROR_STOP=1` `-v` pair reaches its own psql argv, never a
    # `-v NAME=VALUE` variable pair.
    assert captured_argvs[1].count("-v") == 1


def test_apply_platform_migration_run_never_starts_a_file_the_operator_did_not_list(monkeypatch, platform):
    """Completion condition 6b (condition (iii)): the set of psql `-f`
    targets started equals EXACTLY the operator's own given run -- the
    tool never adds `0013`'s own successor `0014` on its own."""
    started_files = []
    real_run = subprocess.run

    def _spy_run(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            f_index = argv.index("-f")
            started_files.append(Path(argv[f_index + 1]).name)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 0
    assert started_files == [
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    ]


def test_apply_platform_migration_never_starts_a_files_own_successor_the_operator_omitted(monkeypatch, platform):
    """Completion condition 6b (condition (iii)), R-57 WP-1 code review
    fix 4: the test above gives the FULL run already, so it cannot tell
    "the tool never adds a file on its own" apart from "the tool simply
    ran everything it was given". Here `_validate_platform_migration_
    run` is bypassed (its own closure refusal is `test_apply_platform_
    migration_solo_0013_is_rejected_by_the_subcommand`'s own subject,
    not this test's) -- giving `0013` ALONE starts psql against
    `0013_role_statement_timeouts.sql` ONLY, never its own successor
    `0014`."""
    monkeypatch.setattr(ops, "_validate_platform_migration_run", lambda files: None)
    started_files = []
    real_run = subprocess.run

    def _spy_run(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            f_index = argv.index("-f")
            started_files.append(Path(argv[f_index + 1]).name)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy_run)
    rc = _run_apply(monkeypatch, platform, "0013_role_statement_timeouts.sql")
    assert rc == 0
    assert started_files == ["0013_role_statement_timeouts.sql"]


def test_apply_platform_migration_run_stops_at_the_failing_file_with_the_confirmed_t3_message(
    monkeypatch, capsys, platform,
):
    """Completion condition 7: a mid-run psql failure stops the run --
    no file after the failing one is ever started -- and the confirmed
    T-3 message names the applied/not-run files and tells the operator
    to re-run the whole run."""
    real_run = subprocess.run
    started = []

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return real_run(argv, **kwargs)
        f_index = argv.index("-f")
        name = Path(argv[f_index + 1]).name
        started.append(name)
        if name == "0013_role_statement_timeouts.sql":
            return subprocess.CompletedProcess(argv, 1, stdout="synthetic failure\n", stderr="")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 2
    assert started == ["0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql"]
    captured = capsys.readouterr()
    assert captured.err.startswith(
        "error: apply-platform-migration failed at 0013_role_statement_timeouts.sql\n"
        "applied: 0012_role_connection_limits.sql\n"
        "not run: 0014_role_connection_limits_rollout.sql\n"
        "An applied file may still carry a value a later file in this run replaces. "
        "Re-run the whole run from its first file; every file in it is idempotent.\n"
    )


def test_apply_platform_migration_run_of_0012_0013_0014_leaves_the_newest_values(monkeypatch, platform):
    """Completion condition 8 (real PostgreSQL): re-applying the
    numbered run `0012 0013 0014` in ONE call leaves the state at the
    NEWEST values -- `begin_provision_application`'s own `CONNECTION
    LIMIT` 68 and `statement_timeout`, and the platform-plane roles'
    own 132/36/12."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    )
    assert rc == 0
    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 132
    assert _role_connlimit(platform.provision_dsn, platform.controlplane_role) == 36
    assert _role_connlimit(platform.provision_dsn, auditreader_role) == 12
    _database_name, runtime_role, developer_role = _provision_app_via_function(
        platform.provision_dsn, platform.schema, "f130")
    assert _role_connlimit(platform.provision_dsn, runtime_role) == 68
    assert _role_connlimit(platform.provision_dsn, developer_role) == 68
    assert _role_setting(platform.provision_dsn, runtime_role) == ["statement_timeout=5000ms"]
    assert _role_setting(platform.provision_dsn, developer_role) == ["statement_timeout=5000ms"]


def test_apply_platform_migration_run_reversed_order_leaves_the_oldest_values(monkeypatch, platform):
    """Completion condition 8 (real PostgreSQL, R-11 mutation target):
    reversing the run's own file order (`0014 0013 0012`, itself
    already rejected by the ascending-order check) is exercised here
    directly against `cmd_apply_platform_migration`'s own internal
    per-file loop, bypassing `_validate_platform_migration_run`, to
    prove the loop itself preserves argument order rather than
    re-sorting -- iterating in the GIVEN (reversed) order leaves
    `mitatedbsvc_api` at 0012's own value (68), never 0014's own value
    (132)."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(platform.migrations_dir))
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    reversed_files = (
        "0014_role_connection_limits_rollout.sql", "0013_role_statement_timeouts.sql",
        "0012_role_connection_limits.sql",
    )
    monkeypatch.setattr(ops, "_validate_platform_migration_run", lambda files: None)
    args = types.SimpleNamespace(
        file=list(reversed_files), lock_timeout=_TEST_LOCK_TIMEOUT, api_role=None, controlplane_role=None,
    )
    rc = ops.cmd_apply_platform_migration(args)
    assert rc == 0
    assert _role_connlimit(platform.provision_dsn, platform.api_role) == 68


# ===========================================================================
# the "flows DDL" subcommand set, derived by AST
# ===========================================================================


def _build_call_graph(tree: "ast.Module") -> "tuple[dict, dict]":
    graph: "dict[str, set]" = {}
    sinks: "dict[str, tuple[bool, bool]]" = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            called: "set[str]" = set()
            hits_psql = False
            hits_migrations = False
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Name):
                        called.add(func.id)
                        if func.id == "_migrations_dir":
                            hits_migrations = True
                    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                        owner = func.value.id
                        if owner == "subprocess" and func.attr in ("run", "Popen"):
                            hits_psql = True
                        if owner == "platform_upgrades" and func.attr == "discover_upgrade_scripts":
                            hits_migrations = True
                        called.add(f"{owner}.{func.attr}")
            graph[node.name] = called
            sinks[node.name] = (hits_psql, hits_migrations)
    return graph, sinks


def _reaches_ddl_sink(start: str, graph: dict, sinks: dict) -> bool:
    seen: "set[str]" = set()
    stack = [start]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        hits_psql, hits_migrations = sinks.get(name, (False, False))
        if hits_psql or hits_migrations:
            return True
        for callee in graph.get(name, ()):
            base = callee.split(".")[0]
            if base in graph and base not in seen:
                stack.append(base)
    return False


def _find_cmd_registrations(tree: "ast.Module") -> "list[tuple[str, str]]":
    registrations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_parser":
            current_name = None
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == "add_parser":
                        if call.args and isinstance(call.args[0], ast.Constant):
                            current_name = call.args[0].value
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == "set_defaults":
                        for kw in call.keywords:
                            if kw.arg == "func" and isinstance(kw.value, ast.Name):
                                registrations.append((current_name, kw.value.id))
    return registrations


def _derive_ddl_flowing_subcommands() -> "set[str]":
    """The set of subcommand NAMES whose own handler function
    reaches, via direct (module-internal) calls, either a
    `subprocess.run`/`subprocess.Popen` call or a `_migrations_dir()`/
    `platform_upgrades.discover_upgrade_scripts` call."""
    tree = ast.parse(OPS_SOURCE_PATH.read_text(encoding="utf-8"), filename=str(OPS_SOURCE_PATH))
    graph, sinks = _build_call_graph(tree)
    registrations = _find_cmd_registrations(tree)
    return {name for name, func in registrations if _reaches_ddl_sink(func, graph, sinks)}


def _required_lock_timeout_subcommands() -> "set[str]":
    """The set of subcommand names whose own `--lock-timeout` argument is
    required with no default (read from the built parser, never a
    hand-written literal set)."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    required = set()
    for name, subparser in subparsers_action.choices.items():
        for action in subparser._actions:
            if action.dest == "lock_timeout" and action.required and action.default is None:
                required.add(name)
    return required


def test_ddl_flowing_subcommands_match_the_required_lock_timeout_set():
    """The AST-derived "flows DDL" set equals the set of
    subcommands whose own `--lock-timeout` is a required, no-default
    argument."""
    assert _derive_ddl_flowing_subcommands() == _required_lock_timeout_subcommands()


def test_ddl_flowing_subcommands_contain_exactly_the_three_expected_and_no_configuration_only_ones():
    """Non-vacuous: the derived set contains
    `apply-platform-migration`, `upgrade-applications`, and `deprovision`,
    and never `set-platform-timeouts`/`declare-surfaces`/`declare-
    process-ceilings`/`declare-coalescing-window` (psycopg-only
    configuration writes that never flow a migration file)."""
    derived = _derive_ddl_flowing_subcommands()
    assert derived == {"apply-platform-migration", "upgrade-applications", "deprovision"}
    for name in ("set-platform-timeouts", "declare-surfaces", "declare-process-ceilings", "declare-coalescing-window"):
        assert name not in derived


def _derive_psql_file_launching_functions() -> "set[str]":
    """Every ops.py function whose own body directly calls
    `subprocess.run`/`subprocess.Popen` AND contains the literal argv
    token `"-f"` (a psql `-f FILE` invocation) -- derived from the AST,
    never a hand-written name list, so a newly added function that
    launches psql against a migration file is picked up automatically."""
    tree = ast.parse(OPS_SOURCE_PATH.read_text(encoding="utf-8"), filename=str(OPS_SOURCE_PATH))
    found: "set[str]" = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls_subprocess = False
        has_dash_f = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "subprocess" and func.attr in ("run", "Popen"):
                        calls_subprocess = True
            if isinstance(sub, ast.Constant) and sub.value == "-f":
                has_dash_f = True
        if calls_subprocess and has_dash_f:
            found.add(node.name)
    return found


def test_psql_file_launching_functions_are_derived_and_non_vacuous():
    """The AST-derived set of psql-`-f`-launching functions is never
    empty, and at the current commit is exactly the 3 functions that
    apply a migration file through psql today."""
    derived = _derive_psql_file_launching_functions()
    assert derived
    assert derived == {"_run_upgrade_script", "_run_deprovision_script", "cmd_apply_platform_migration"}


def test_psql_launching_functions_all_apply_the_lock_timeout_option():
    """Every function the AST derives as launching psql against a
    migration file (`-f FILE`) also calls `_with_lock_timeout_option`
    -- checked directly against each function's own AST body, not
    merely by running them (static check), and against the DERIVED set
    rather than a hand-written name list, so a newly added psql-file-
    launching function that skips it is caught automatically."""
    tree = ast.parse(OPS_SOURCE_PATH.read_text(encoding="utf-8"), filename=str(OPS_SOURCE_PATH))
    derived = _derive_psql_file_launching_functions()
    bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in derived:
            calls = {
                sub.func.id for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            }
            bodies[node.name] = calls
    assert set(bodies) == derived
    for name, calls in bodies.items():
        assert "_with_lock_timeout_option" in calls, (name, calls)
