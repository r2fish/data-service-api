"""R-90 WP-1/WP-2: `ops apply-platform-migration` and `ops deprovision`
-- their static AST-derived acceptance checks, and their real-PostgreSQL
drift-then-restore/destructive behavior.

Design: work order
docs/work-orders/WORK_ORDER_R90_R2DB_PLATFORM_MIGRATION_AND_DEPROVISION_OPS_V1.md
§1 (D-0..D-10), §2 (WP-1), §3 (WP-2).

This module owns its OWN throwaway-PostgreSQL fixture (`platform` below)
-- it never imports one from another test module, mirroring
`MitateDB-api/tests/test_ops_apply_platform_migration.py`'s own stated
precedent (that file's own header docstring) and this repository's own
established convention of not taking cross-test-module import
dependencies (`test_audit_query.py`/`test_application_audit.py`/
`test_postgres.py` each duplicate their own platform fixture rather than
share one).
"""
from __future__ import annotations

import ast
import json
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

import r2db_api.ops as ops

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
OPS_SOURCE_PATH = Path(ops.__file__)
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
_TEST_LOCK_TIMEOUT = "5s"


# ===========================================================================
# PostgreSQL platform fixture -- self-contained (see module docstring).
# Bootstraps only the NON-re-appliable prerequisites (0001/0002/0005/
# 0006/0007 -- the bootstrap-only and password-carrying migrations
# `apply-platform-migration` itself never accepts, work order D-1); every
# test that needs 0008/0012/0013/0014 applies them itself, through the
# real `ops apply-platform-migration` subcommand under test -- exercising
# the real thing end-to-end rather than a stand-in.
# ===========================================================================


def _admin_dsn() -> str:
    """Embeds ambient `PGPASSFILE` into the returned DSN up front --
    several tests below clear that ambient variable before an
    in-process `apply-platform-migration` call, and this DSN (and
    anything `_dsn_with` derives from it) must keep working through the
    REST of that same test and through fixture teardown regardless."""
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
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
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_ops_apply_platform_migration.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests must not be skipped.",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            for (database,) in cur.fetchall():
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                    [database],
                )
                cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            for (role,) in cur.fetchall():
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


_PREREQUISITE_MIGRATIONS = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
)

#: not part of `_PLATFORM_MIGRATION_FILENAMES` (they are per-application,
#: D-1) -- copied into the rewritten migrations dir too, so `deprovision`
#: tests can provision/deprovision a real per-application database.
_APPLICATION_LIFECYCLE_MIGRATIONS = (
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
)


def _bootstrap(prefix: str) -> types.SimpleNamespace:
    admin_dsn = _admin_dsn()
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = Path(tempfile.mkdtemp(prefix="r2db_apm_"))
    rewritten: "dict[str, Path]" = {}
    for name in (*_PREREQUISITE_MIGRATIONS, *_APPLICATION_LIFECYCLE_MIGRATIONS, *ops._PLATFORM_MIGRATION_FILENAMES):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
    control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
    _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
    _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
    _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})

    return types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        api_role=api_role, api_password=api_password,
        controlplane_role=controlplane_role, controlplane_password=controlplane_password,
        auditreader_role=auditreader_role, auditreader_password=auditreader_password,
        platform_db=platform_db, schema=schema,
        migrations_dir=rewritten_dir, migration_paths=rewritten,
    )


@pytest.fixture()
def platform() -> Iterator[types.SimpleNamespace]:
    """A fresh, throwaway platform through 0001/0002/0005/0006/0007 --
    one per test, never shared (several tests drift role settings,
    constraints, and declaration rows that 0008/0012/0013/0014 own)."""
    _require_admin_connection()
    prefix = f"r90apm{secrets.token_hex(4)}"
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


def _clear_ambient_pg_connection_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test-infrastructure cluster (`tools/testpg/dsa_testpg.py`)
    exports `PGPASSFILE` (and may export other libpq connection
    variables) for the whole pytest process -- ambient values
    `_psql_connection_env`'s own leftover-variable check correctly
    refuses to let a psql child inherit silently. Every real
    `apply-platform-migration`/`deprovision` invocation below clears
    these first."""
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)


def _run_apply_run(
    monkeypatch: pytest.MonkeyPatch, platform: types.SimpleNamespace, *filenames: str,
    clear_ambient: bool = True, **cli_kwargs,
) -> "int | None":
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
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


def _show_setting(dsn: str, name: str) -> str:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SHOW {}").format(sql.Identifier(name)))
            return cur.fetchone()[0]
    finally:
        conn.close()


def _role_connlimit(admin_dsn: str, role: str) -> int:
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname = %s", [role])
            return cur.fetchone()[0]
    finally:
        conn.close()


def _declared_value(control_dsn: str, schema: str, key: str):
    conn = psycopg.connect(control_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT value FROM {table} WHERE key = %s").format(table=sql.Identifier(schema, "platform_declarations")),
                [key],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _constraint_definition(control_dsn: str, name: str) -> "str | None":
    conn = psycopg.connect(control_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s", [name])
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


# ===========================================================================
# completion conditions 1/2 -- filename resolution
# ===========================================================================


def test_apply_platform_migration_rejects_unknown_filename_before_any_psql(platform, monkeypatch, capsys):
    """Completion condition 1: a FILENAME not in
    `_PLATFORM_MIGRATION_FILENAMES` is refused before any psql
    subprocess starts, and the rejected value itself is never echoed."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0002_provisioning_functions.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "0002_provisioning_functions.sql" not in captured.err


def test_apply_platform_migration_rejects_path_separator_in_filename(platform, monkeypatch, capsys):
    """Completion condition 1: a FILENAME containing a path separator is
    refused before any psql subprocess starts, and never echoed."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "../0008_platform_declarations_and_writer_timeouts.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert "../0008_platform_declarations_and_writer_timeouts.sql" not in captured.err


def test_apply_platform_migration_rejects_symlink_escaping_migrations_dir(platform, monkeypatch, capsys, tmp_path):
    """Completion condition 2: a symlink placed inside the migrations
    directory, whose own target resolves OUTSIDE it, is refused. Uses
    `0014` (no successor, no required variable, condition 5/7/8 out of
    the way) so the containment check is the ONLY thing standing
    between this call and a real psql subprocess."""
    outside = tmp_path / "outside.sql"
    outside.write_text("SELECT 1;")
    escape_name = "0014_auditreader_statement_timeout.sql"
    # Overwrite the fixture's own rewritten copy with a symlink escaping the directory.
    target = platform.migrations_dir / escape_name
    target.unlink()
    target.symlink_to(outside)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, escape_name)
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert str(outside) not in captured.err


def test_apply_platform_migration_rejects_missing_file(platform, monkeypatch, capsys):
    """Completion condition 2: a known FILENAME whose real file is
    absent from the migrations directory is refused."""
    missing_name = "0014_auditreader_statement_timeout.sql"
    (platform.migrations_dir / missing_name).unlink()
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, missing_name)
    assert rc == 2
    assert calls == []


# ===========================================================================
# completion condition 3 -- run order and duplicates
# ===========================================================================


def test_apply_platform_migration_rejects_out_of_order_run(platform, monkeypatch, capsys):
    """Completion condition 3: a run not ascending in
    `_PLATFORM_MIGRATION_FILENAMES` order is refused before any psql
    subprocess starts, and the operator's own given order is never
    echoed."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform,
        "0012_process_ceilings.sql", "0008_platform_declarations_and_writer_timeouts.sql",
    )
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: FILENAMEs must be given in migration order, each at most once"
    )


def test_apply_platform_migration_rejects_duplicate_filename_in_run(platform, monkeypatch, capsys):
    """Completion condition 3: a repeated FILENAME in the same run is
    refused before any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform, "0014_auditreader_statement_timeout.sql", "0014_auditreader_statement_timeout.sql",
    )
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: FILENAMEs must be given in migration order, each at most once"
    )


# ===========================================================================
# completion conditions 4/4b -- superseded-by, derived from the 5 real
# migration files (and, separately, from a synthetic pair)
# ===========================================================================


# `_strip_sql_line_comments`/`_extract_psql_variables`/`_PSQL_VARIABLE_RE` are
# NOT duplicated here (差し戻し 1 F4) -- they live in `ops.py` (same names,
# same placement as MitateDB-api's own), isomorphic-pinned; this file uses
# `ops._strip_sql_line_comments`/`ops._extract_psql_variables` directly.
_FUNC_HEADER_RE = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][A-Za-z0-9_.]*)\s*\(", re.IGNORECASE)
_DOLLAR_QUOTE_RE = re.compile(r"\$([A-Za-z_]*)\$.*?\$\1\$", re.DOTALL)
_ROLE_TOKEN = r'(:"[A-Za-z_][A-Za-z0-9_]*"|:\'[A-Za-z_][A-Za-z0-9_]*\'|"[A-Za-z_][A-Za-z0-9_]*"|[A-Za-z_][A-Za-z0-9_]*)'
_ALTER_ROLE_SET_RE = re.compile(r"ALTER\s+ROLE\s+" + _ROLE_TOKEN + r"\s+SET\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_ALTER_ROLE_CONNLIMIT_RE = re.compile(r"ALTER\s+ROLE\s+" + _ROLE_TOKEN + r"\s+CONNECTION\s+LIMIT", re.IGNORECASE)
_INLINE_TABLE_CONSTRAINT_RE = re.compile(r"CONSTRAINT\s+([A-Za-z_][A-Za-z0-9_]*)\s+CHECK", re.IGNORECASE)
_ADD_CONSTRAINT_RE = re.compile(r"ADD\s+CONSTRAINT\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _platform_migration_targets_in_text(text: str) -> "list[tuple[str, str]]":
    """Design D-1's 3 derivation criteria, applied to one migration
    file's own text: (i) a `CREATE [OR REPLACE] FUNCTION <name>(...)
    $tag$ ... $tag$` body -- the function's own qualified name is
    recorded as a `"function body"` target BEFORE the dollar-quoted body
    (and any OTHER dollar-quoted span, e.g. an anonymous `DO $$ ... $$`
    block with no preceding `FUNCTION` header) is stripped from the text
    -- so a role name interpolated dynamically inside a function/DO body
    (`EXECUTE format('ALTER ROLE %I ...', ...)`) is never scanned as an
    independent (ii)-kind target of its own. (ii) `ALTER ROLE <role> SET
    <param>` / `ALTER ROLE <role> CONNECTION LIMIT` against the
    REMAINING (dollar-quote-stripped) text -- `<role>` may be a bare
    identifier, a double-quoted identifier, or a psql `:"name"`/`:'name'`
    variable reference (0008's own `ALTER ROLE :"api_role" SET ...`), all
    kept as their own literal matched text. This derivation does NOT
    resolve a psql variable reference to the literal role name an
    operator's own `--api-role`/`--controlplane-role` value supplies at
    invocation time -- a role named by a psql variable in one file and
    by its own literal identifier in another (0008's own
    `:"controlplane_role"` and 0013's own `r2dbsvc_controlplane`, the
    SAME real role once `0008` is actually invoked with the production
    value) are matched as two DIFFERENT targets here, never folded
    together. This is safe for the 5 CURRENTLY accepted files only
    because none of them redefines the SAME KIND of target (the same
    `SET <param>`, or `CONNECTION LIMIT`) for that role under two
    different spellings -- a RESIDUAL GAP: a future migration that
    redefines an already-covered role's target under a spelling that
    differs from the earlier file's own reference would not be detected
    as that file's successor here; a new migration must spell an
    already-referenced role identically to how an earlier accepted file
    already spells it, for this derivation to see the redefinition.
    (iii) a same-named table CONSTRAINT -- either defined inline inside
    a `CREATE TABLE` (`CONSTRAINT <name> CHECK ...`) or added via `ALTER
    TABLE ... ADD CONSTRAINT <name>`; a `DROP CONSTRAINT` is never a
    "define" event on its own (it is always paired, in the SAME file,
    with the `ADD CONSTRAINT` that actually redefines it)."""
    stripped_comments = ops._strip_sql_line_comments(text)
    targets: "list[tuple[str, str]]" = []
    cursor = 0
    remainder_parts: "list[str]" = []
    for match in _DOLLAR_QUOTE_RE.finditer(stripped_comments):
        preceding = stripped_comments[cursor:match.start()]
        header = _FUNC_HEADER_RE.search(preceding)
        if header:
            targets.append((header.group(1), "function body"))
        remainder_parts.append(preceding)
        cursor = match.end()
    remainder_parts.append(stripped_comments[cursor:])
    remainder = "".join(remainder_parts)

    working = remainder
    for match in _ALTER_ROLE_CONNLIMIT_RE.finditer(working):
        targets.append((match.group(1), "CONNECTION LIMIT"))
    working = _ALTER_ROLE_CONNLIMIT_RE.sub("", working)
    for match in _ALTER_ROLE_SET_RE.finditer(working):
        targets.append((match.group(1), f"SET {match.group(2)}"))
    working = _ALTER_ROLE_SET_RE.sub("", working)
    for match in _ADD_CONSTRAINT_RE.finditer(working):
        targets.append((match.group(1), "constraint"))
    working = _ADD_CONSTRAINT_RE.sub("", working)
    for match in _INLINE_TABLE_CONSTRAINT_RE.finditer(working):
        targets.append((match.group(1), "constraint"))
    return targets


def _derive_target_map(named_texts: "dict[str, str]", order: "tuple[str, ...]") -> "dict[tuple[str, str], tuple[str, ...]]":
    """`target -> the files (in `order`) that define it`, derived from
    `named_texts` (each key a filename, each value that file's own
    text), walked in `order`."""
    target_map: "dict[tuple[str, str], list[str]]" = {}
    for name in order:
        for target in _platform_migration_targets_in_text(named_texts[name]):
            target_map.setdefault(target, []).append(name)
    return {target: tuple(files) for target, files in target_map.items()}


def _file_level_superseded_by(
    target_map: "dict[tuple[str, str], tuple[str, ...]]", order: "tuple[str, ...]",
) -> "dict[str, tuple[str, ...]]":
    """Folds the target-level map down to `file -> the files, in order,
    that redefine at least one of its own targets` -- the SAME shape as
    `ops._PLATFORM_MIGRATION_SUPERSEDED_BY`."""
    successors: "dict[str, set]" = {}
    for files in target_map.values():
        for i, name in enumerate(files[:-1]):
            successors.setdefault(name, set()).update(files[i + 1:])
    positions = {name: i for i, name in enumerate(order)}
    return {name: tuple(sorted(later, key=positions.__getitem__)) for name, later in successors.items()}


def _derive_platform_migration_target_map() -> "dict[tuple[str, str], tuple[str, ...]]":
    named_texts = {name: (MIGRATIONS_DIR / name).read_text() for name in ops._PLATFORM_MIGRATION_FILENAMES}
    return _derive_target_map(named_texts, ops._PLATFORM_MIGRATION_FILENAMES)


def test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level():
    """Completion condition 4: `ops._PLATFORM_MIGRATION_SUPERSEDED_BY`
    is exactly what the target-level map, derived directly from the 5
    accepted migration files' own real text, derives at file
    granularity. Non-vacuous: the derived table is non-empty (`{0008:
    (0012,)}`, design D-1 monitor ruling R1-5, criterion (iii) -- the
    same-named `platform_declarations_key_check` constraint 0008 defines
    inline and 0012 redefines via `ADD CONSTRAINT`)."""
    target_map = _derive_platform_migration_target_map()
    derived = _file_level_superseded_by(target_map, ops._PLATFORM_MIGRATION_FILENAMES)
    assert derived
    assert derived == ops._PLATFORM_MIGRATION_SUPERSEDED_BY


def test_platform_migration_target_map_derivation_exercises_all_3_criteria_on_synthetic_sources():
    """Completion condition 4b (monitor ruling R1-4): a derivation that
    always returns an empty map would still pass condition 4 by
    accident if `_PLATFORM_MIGRATION_SUPERSEDED_BY` itself were ever
    emptied in lockstep -- this test exercises the derivation directly,
    independent of the 5 real files, with a minimal synthetic pair where
    EACH of the 3 criteria fires exactly once: (i) the same function
    name `CREATE OR REPLACE FUNCTION`d in both; (ii) the same role's own
    `ALTER ROLE ... SET statement_timeout` in both; (iii) the same table
    constraint name, defined inline in the first and re-added (after a
    `DROP CONSTRAINT IF EXISTS`) in the second."""
    source_a = (
        "CREATE OR REPLACE FUNCTION pkg.f(a int) RETURNS int LANGUAGE plpgsql AS $fn$ BEGIN RETURN a; END; $fn$;\n"
        "ALTER ROLE demo_role SET statement_timeout = '1000ms';\n"
        "CREATE TABLE demo (\n"
        "    key text PRIMARY KEY CONSTRAINT demo_key_check CHECK (key IN ('a'))\n"
        ");\n"
    )
    source_b = (
        "CREATE OR REPLACE FUNCTION pkg.f(a int) RETURNS int LANGUAGE plpgsql AS $fn$ BEGIN RETURN a + 1; END; $fn$;\n"
        "ALTER ROLE demo_role SET statement_timeout = '2000ms';\n"
        "ALTER TABLE demo DROP CONSTRAINT IF EXISTS demo_key_check;\n"
        "ALTER TABLE demo ADD CONSTRAINT demo_key_check CHECK (key IN ('a', 'b'));\n"
    )
    order = ("a.sql", "b.sql")
    derived = _derive_target_map(dict(zip(order, (source_a, source_b))), order)
    assert derived
    assert derived == {
        ("pkg.f", "function body"): ("a.sql", "b.sql"),
        ("demo_role", "SET statement_timeout"): ("a.sql", "b.sql"),
        ("demo_key_check", "constraint"): ("a.sql", "b.sql"),
    }


# ===========================================================================
# completion condition 5 -- closure over successors
# ===========================================================================


def test_apply_platform_migration_solo_0008_is_rejected_with_the_full_required_run(platform, monkeypatch, capsys):
    """Completion condition 5: `0008` alone (its own successor `0012`
    absent from the call) is refused before any psql subprocess starts,
    with a message naming the FULL required run."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0008_platform_declarations_and_writer_timeouts.sql")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: 0008_platform_declarations_and_writer_timeouts.sql is superseded "
        "by a later platform migration; apply the whole run in one call, in this order: "
        "0008_platform_declarations_and_writer_timeouts.sql 0012_process_ceilings.sql"
    )


def test_apply_platform_migration_solo_0014_still_passes_the_closure_check(platform, monkeypatch):
    """Completion condition 5: `0014` alone (no successors, the LAST
    file in `_PLATFORM_MIGRATION_FILENAMES`) still passes the closure
    check and actually applies (real PostgreSQL)."""
    rc = _run_apply_run(monkeypatch, platform, "0014_auditreader_statement_timeout.sql")
    assert rc == 0


def test_apply_platform_migration_run_of_0008_0012_succeeds_in_one_call(platform, monkeypatch):
    """Completion condition 5: the required run, given as both
    FILENAMEs in one call, applies both in order (real PostgreSQL)."""
    rc = _run_apply_run(
        monkeypatch, platform,
        "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0


# ===========================================================================
# completion conditions 6/7/8 -- psql variable reconciliation
# ===========================================================================


# `ops._extract_psql_variables` used directly below (差し戻し 1 F4).


def test_platform_migration_variable_table_matches_each_files_own_real_references():
    """Completion condition 6: `ops._PLATFORM_MIGRATION_VARIABLE_TABLE`
    equals, for each of the 5 accepted files, that file's own real
    `:name` references (never a `--` comment, never a `::` type cast)."""
    for name in ops._PLATFORM_MIGRATION_FILENAMES:
        text = (MIGRATIONS_DIR / name).read_text()
        assert set(ops._PLATFORM_MIGRATION_VARIABLE_TABLE[name]) == ops._extract_psql_variables(text), name


def test_apply_platform_migration_missing_required_variable_is_rejected_deterministically(platform, monkeypatch, capsys):
    """Completion condition 7: `0008 0012` (satisfying the closure check,
    condition 5, so the variable check is actually reached) without
    `--api-role`/`--controlplane-role` is refused before any psql
    subprocess starts, naming the SAME variable across repeated
    invocations (never varying with Python's own hash-randomized set
    order)."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    messages = set()
    for _ in range(5):
        rc = _run_apply_run(
            monkeypatch, platform,
            "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        )
        assert rc == 2
        messages.add(capsys.readouterr().err.strip())
    assert calls == []
    assert messages == {
        "error: apply-platform-migration: 0008_platform_declarations_and_writer_timeouts.sql requires --api-role"
    }


def test_apply_platform_migration_extra_variable_is_rejected(platform, monkeypatch, capsys):
    """Completion condition 8: a variable no file in the run requires
    is refused before any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(monkeypatch, platform, "0014_auditreader_statement_timeout.sql", api_role="whatever")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: apply-platform-migration: 0014_auditreader_statement_timeout.sql does not accept --api-role"
    )


# ===========================================================================
# completion condition 9 -- DSN is R2DB_CONTROL_DSN only
# ===========================================================================


def test_apply_platform_migration_parser_has_no_dsn_argument():
    """Completion condition 9: the built `apply-platform-migration`
    subparser has no argument that could carry a DSN -- the only way to
    reach a platform database is R2DB_CONTROL_DSN."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    subparser = subparsers_action.choices["apply-platform-migration"]
    dests = {action.dest for action in subparser._actions}
    assert not any("dsn" in dest.lower() for dest in dests)


def test_apply_platform_migration_requires_r2db_control_dsn_env(platform, monkeypatch, capsys):
    """Completion condition 9: with `R2DB_CONTROL_DSN` unset, the
    subcommand is refused before any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
    monkeypatch.delenv("R2DB_CONTROL_DSN", raising=False)
    try:
        rc = ops.main(["apply-platform-migration", "0014_auditreader_statement_timeout.sql", "--lock-timeout", _TEST_LOCK_TIMEOUT])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 2
    assert calls == []


# ===========================================================================
# completion condition 10 -- no psql subprocess on any rejection
# ===========================================================================


def test_apply_platform_migration_never_starts_psql_on_any_of_several_rejections(platform, monkeypatch):
    """Completion condition 10: across several distinct rejection
    reasons (conditions 1/3/7/8), `subprocess.run` is never invoked.
    The order-violation scenario deliberately uses 2 files that
    together need NO `-v` variable (`0013`/`0012`), so removing the
    order/closure check ALONE (with nothing else standing in the way)
    is what a real psql invocation would expose."""
    scenarios = (
        ("unknown-name.sql",),
        ("0013_role_connection_limits.sql", "0012_process_ceilings.sql"),  # out of order, no variables needed
        ("0014_auditreader_statement_timeout.sql", "0014_auditreader_statement_timeout.sql"),  # duplicate
        ("0014_auditreader_statement_timeout.sql",),  # extra variable
    )
    kwargs_by_scenario = ({}, {}, {}, {"api_role": "x"})
    for filenames, kwargs in zip(scenarios, kwargs_by_scenario):
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
        rc = _run_apply_run(monkeypatch, platform, *filenames, **kwargs)
        assert rc == 2
        assert calls == []


# ===========================================================================
# completion condition 11 -- PGOPTIONS lock_timeout, DSN options preserved
# ===========================================================================


def test_apply_platform_migration_pgoptions_carries_lock_timeout_and_preserves_dsn_options(platform, monkeypatch):
    """Completion condition 11: the psql subprocess env's own `PGOPTIONS`
    carries `-c lock_timeout=<value>`, and a DSN-supplied `options` value
    keeps taking effect alongside it (never dropped)."""
    dsn_with_options = _dsn_with(platform.control_dsn, options="-c application_name=r90-apm-test")
    monkeypatch.setenv("R2DB_CONTROL_DSN", dsn_with_options)
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    captured_envs = []
    real_run = subprocess.run

    def _spy(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured_envs.append(kwargs.get("env"))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy)
    rc = ops.main([
        "apply-platform-migration", "0014_auditreader_statement_timeout.sql", "--lock-timeout", _TEST_LOCK_TIMEOUT,
    ])
    assert rc == 0
    assert len(captured_envs) == 1
    pgoptions = captured_envs[0]["PGOPTIONS"]
    assert "-c application_name=r90-apm-test" in pgoptions
    assert f"-c lock_timeout={_TEST_LOCK_TIMEOUT}" in pgoptions


# ===========================================================================
# completion condition 12 -- exact argv shape
# ===========================================================================


def test_apply_platform_migration_argv_carries_only_this_files_own_variables(platform, monkeypatch):
    """Completion condition 12: the psql argv is `psql -v ON_ERROR_STOP=1
    ... -f <resolved absolute path>`, carrying only THIS file's own
    required `-v` variables."""
    captured_argvs = []
    real_run = subprocess.run

    def _spy(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured_argvs.append(argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy)
    rc = _run_apply_run(
        monkeypatch, platform, "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    assert len(captured_argvs) == 2
    first = captured_argvs[0]
    resolved_0008 = str((platform.migrations_dir / "0008_platform_declarations_and_writer_timeouts.sql").resolve())
    assert first == [
        "psql", "-v", "ON_ERROR_STOP=1",
        "-v", f"api_role={platform.api_role}", "-v", f"controlplane_role={platform.controlplane_role}",
        "-f", resolved_0008,
    ]
    second = captured_argvs[1]
    resolved_0012 = str((platform.migrations_dir / "0012_process_ceilings.sql").resolve())
    assert second == ["psql", "-v", "ON_ERROR_STOP=1", "-f", resolved_0012]


# ===========================================================================
# completion condition 13 -- --lock-timeout required, no default, pre-psql
# ===========================================================================


def test_apply_platform_migration_lock_timeout_is_required_with_no_default():
    """Completion condition 13: `--lock-timeout` is required with no
    default on the built parser."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    subparser = subparsers_action.choices["apply-platform-migration"]
    action = next(a for a in subparser._actions if a.dest == "lock_timeout")
    assert action.required is True
    assert action.default is None


def test_apply_platform_migration_rejects_malformed_lock_timeout_before_any_psql(platform, monkeypatch):
    """Completion condition 13: a malformed `--lock-timeout` value is
    refused before any psql subprocess starts."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_apply_run(
        monkeypatch, platform, "0014_auditreader_statement_timeout.sql", lock_timeout="not-a-duration",
    )
    assert rc == 2
    assert calls == []


# ===========================================================================
# completion condition 14 -- failure output shape and redaction
# ===========================================================================


def test_apply_platform_migration_failure_output_names_applied_and_not_run_and_redacts(platform, monkeypatch, capsys):
    """Completion condition 14 (R1-11): when a file in a 3-file run
    fails, the failed file is in NEITHER `applied` NOR `not run`; the
    output states a partial apply is possible and instructs a full
    re-run from the first file; and the DSN's own connection-parameter
    values never appear in the output (redaction)."""
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    real_run = subprocess.run
    call_count = {"n": 0}

    def _fake(argv, **kwargs):
        if "--version" in argv:
            return real_run(argv, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 1:
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr=f"psql: error: connection failed: user={platform.control_role}",
        )

    monkeypatch.setattr(subprocess, "run", _fake)
    try:
        rc = ops.main([
            "apply-platform-migration",
            "0008_platform_declarations_and_writer_timeouts.sql",
            "0012_process_ceilings.sql",
            "0013_role_connection_limits.sql",
            "--lock-timeout", _TEST_LOCK_TIMEOUT,
            "--api-role", platform.api_role, "--controlplane-role", platform.controlplane_role,
        ])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 2
    err = capsys.readouterr().err
    assert "applied: 0008_platform_declarations_and_writer_timeouts.sql" in err
    assert "not run: 0013_role_connection_limits.sql" in err
    assert "0012_process_ceilings.sql" not in err.split("applied:")[1].split("not run:")[0]
    assert "0012_process_ceilings.sql" not in err.split("not run:")[1]
    assert "Re-run the whole run from its first file" in err
    assert platform.control_role not in err


# ===========================================================================
# completion conditions 15-18 -- drift-then-restore (real PostgreSQL)
# ===========================================================================


def test_apply_platform_migration_0008_drift_then_restore(platform, monkeypatch):
    """Completion condition 15: a hand-drifted `statement_timeout` on
    the api role, and a hand-drifted `audit_writer_roles` declaration
    row, both reconverge on re-apply of `0008` (given together with its
    own required successor `0012`, condition 5 -- 0008 alone is always
    refused by the closure check, real or synthetic state aside)."""
    rc = _run_apply_run(
        monkeypatch, platform,
        "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9999ms'").format(sql.Identifier(platform.api_role)))
    finally:
        admin.close()
    control = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with control.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET value = %s WHERE key = 'audit_writer_roles'").format(
                    sql.Identifier(platform.schema, "platform_declarations")
                ),
                ['["drifted_role_a", "drifted_role_b"]'],
            )
    finally:
        control.close()
    rc = _run_apply_run(
        monkeypatch, platform,
        "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    api_dsn = _dsn_with(platform.admin_dsn, user=platform.api_role, password=platform.api_password, dbname=platform.platform_db)
    assert _show_setting(api_dsn, "statement_timeout") == "5s"
    restored = _declared_value(platform.control_dsn, platform.schema, "audit_writer_roles")
    assert restored == [platform.api_role, platform.controlplane_role]


def test_apply_platform_migration_0012_drift_then_restore(platform, monkeypatch):
    """Completion condition 16: a hand-dropped `platform_declarations_
    key_check` constraint reconverges (back to its own 5-key `CHECK`)
    on re-apply of `0012` alone."""
    rc = _run_apply_run(
        monkeypatch, platform,
        "0008_platform_declarations_and_writer_timeouts.sql", "0012_process_ceilings.sql",
        api_role=platform.api_role, controlplane_role=platform.controlplane_role,
    )
    assert rc == 0
    control = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with control.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS platform_declarations_key_check").format(
                    sql.Identifier(platform.schema, "platform_declarations")
                )
            )
    finally:
        control.close()
    assert _constraint_definition(platform.control_dsn, "platform_declarations_key_check") is None
    rc = _run_apply_run(monkeypatch, platform, "0012_process_ceilings.sql")
    assert rc == 0
    restored = _constraint_definition(platform.control_dsn, "platform_declarations_key_check")
    assert restored is not None
    assert "process_ceilings" in restored


def test_apply_platform_migration_0013_drift_then_restore(platform, monkeypatch):
    """Completion condition 17: a hand-lowered `CONNECTION LIMIT` on the
    api role reconverges to `68` on re-apply of `0013`."""
    rc = _run_apply_run(monkeypatch, platform, "0013_role_connection_limits.sql")
    assert rc == 0
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 3").format(sql.Identifier(platform.api_role)))
    finally:
        admin.close()
    assert _role_connlimit(platform.admin_dsn, platform.api_role) == 3
    rc = _run_apply_run(monkeypatch, platform, "0013_role_connection_limits.sql")
    assert rc == 0
    assert _role_connlimit(platform.admin_dsn, platform.api_role) == 68


def test_apply_platform_migration_0014_drift_then_restore(platform, monkeypatch):
    """Completion condition 18: a hand-drifted `statement_timeout` on
    the auditreader role reconverges to `5000ms` on re-apply of
    `0014`."""
    rc = _run_apply_run(monkeypatch, platform, "0014_auditreader_statement_timeout.sql")
    assert rc == 0
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '1ms'").format(sql.Identifier(platform.auditreader_role)))
    finally:
        admin.close()
    rc = _run_apply_run(monkeypatch, platform, "0014_auditreader_statement_timeout.sql")
    assert rc == 0
    reader_dsn = _dsn_with(
        platform.admin_dsn, user=platform.auditreader_role, password=platform.auditreader_password, dbname=platform.platform_db,
    )
    assert _show_setting(reader_dsn, "statement_timeout") == "5s"


# ===========================================================================
# completion conditions 19/20 -- AST-derived acceptance checks
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
    """The set of subcommand NAMES whose own handler function reaches,
    via direct (module-internal) calls, either a `subprocess.run`/
    `subprocess.Popen` call or a `_migrations_dir()`/`platform_upgrades.
    discover_upgrade_scripts` call."""
    tree = ast.parse(OPS_SOURCE_PATH.read_text(encoding="utf-8"), filename=str(OPS_SOURCE_PATH))
    graph, sinks = _build_call_graph(tree)
    registrations = _find_cmd_registrations(tree)
    return {name for name, func in registrations if _reaches_ddl_sink(func, graph, sinks)}


def _required_lock_timeout_subcommands() -> "set[str]":
    """The set of subcommand names whose own `--lock-timeout` argument
    is required with no default (read from the built parser, never a
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
    """Completion condition 19: the AST-derived "flows DDL" set equals
    the set of subcommands whose own `--lock-timeout` is a required,
    no-default argument -- no literal count on either side, so this
    holds both before and after `deprovision` exists (WP-2)."""
    assert _derive_ddl_flowing_subcommands() == _required_lock_timeout_subcommands()


def _derive_psql_file_launching_functions() -> "set[str]":
    """Every ops.py function whose own body directly calls
    `subprocess.run`/`subprocess.Popen` AND contains the literal argv
    token `"-f"` (a psql `-f FILE` invocation) -- derived from the AST,
    never a hand-written name list."""
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


def test_psql_launching_functions_all_apply_the_lock_timeout_option():
    """Completion condition 20: every function the AST derives as
    launching psql against a migration file (`-f FILE`) also calls
    `_with_lock_timeout_option` -- checked against the DERIVED set, non-
    empty, never a hand-written name list."""
    tree = ast.parse(OPS_SOURCE_PATH.read_text(encoding="utf-8"), filename=str(OPS_SOURCE_PATH))
    derived = _derive_psql_file_launching_functions()
    assert derived
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



# ===========================================================================
# WP-2 -- `ops deprovision`
# ===========================================================================


def _provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.control_dsn, platform.migration_paths["0003_provision_application.sql"],
        {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{slug}"
    return types.SimpleNamespace(
        slug=slug, database=database,
        runtime_role=f"{database}_runtime", developer_role=f"{database}_developer",
        runtime_password=runtime_password, developer_password=developer_password,
    )


def _register_only(platform: types.SimpleNamespace, slug: str) -> None:
    """Inserts a bare `applications` row (`database_name`/`runtime_role`/
    `developer_role`/`provisioned_at` all NULL) -- the two-state
    registry's own "registered but never provisioned" shape (0006's own
    `applications_registration_state_check`), reached directly via SQL
    since this repository's own `register_application` lives behind the
    full `/control/v1` HTTP stack this test module does not stand up."""
    conn = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {table} (application_slug) VALUES (%s)").format(
                    table=sql.Identifier(platform.schema, "applications")
                ),
                [slug],
            )
    finally:
        conn.close()


def _application_provisioned_at(platform: types.SimpleNamespace, slug: str):
    conn = psycopg.connect(platform.control_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT provisioned_at FROM {table} WHERE application_slug = %s").format(
                    table=sql.Identifier(platform.schema, "applications")
                ),
                [slug],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _row_count(dsn: str, schema: str, table: str) -> int:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {table}").format(table=sql.Identifier(schema, table)))
            return cur.fetchone()[0]
    finally:
        conn.close()


def _database_exists(admin_dsn: str, database: str) -> bool:
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [database])
            return cur.fetchone() is not None
    finally:
        conn.close()


def _role_exists(admin_dsn: str, role: str) -> bool:
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            return cur.fetchone() is not None
    finally:
        conn.close()


def _run_deprovision(
    monkeypatch: pytest.MonkeyPatch, platform: types.SimpleNamespace, slug: str,
    *, clear_ambient: bool = True, **cli_kwargs,
) -> "int | None":
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    if clear_ambient:
        _clear_ambient_pg_connection_env_vars(monkeypatch)
    argv = ["deprovision", slug]
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


def test_deprovision_rejects_malformed_slug_before_any_db_access(platform, monkeypatch):
    """Completion condition 1: an `application_id` not matching
    `_APPLICATION_ID_PATTERN` is refused before any psql OR psycopg
    connection is attempted."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("psycopg started")))
    rc = _run_deprovision(monkeypatch, platform, "Not-A-Valid-Slug!")
    assert rc == 2
    assert calls == []


def test_deprovision_rejects_unregistered_slug(platform, monkeypatch, capsys):
    """Completion condition 2: an unregistered slug is refused (a
    plain, fixed `_die` message -- NOT a `--confirm` JSON denial, which
    is what this would fall through to if the not-registered check were
    ever skipped); `0004` never runs."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_deprovision(monkeypatch, platform, "neverregistered")
    assert rc == 2
    assert calls == []
    err = capsys.readouterr().err.strip()
    assert err.startswith("error: deprovision: application ")
    assert "is not registered" in err


def test_deprovision_rejects_registered_but_not_provisioned_slug(platform, monkeypatch):
    """Completion condition 2: a slug that is registered but never
    provisioned (`database_name`/`provisioned_at` both NULL) is
    refused; `0004` never runs."""
    _register_only(platform, "onlyregistered")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_deprovision(monkeypatch, platform, "onlyregistered")
    assert rc == 2
    assert calls == []


def test_deprovision_confirm_mismatch_is_a_json_denial_and_touches_nothing(platform, monkeypatch, capsys):
    """Completion condition 3: an omitted/mismatched `--confirm` is a
    JSON denial on stderr, exit 2, `required_confirmation`/
    `consequence`/`reversible_alternative` present and
    `required_confirmation` matching the real phrase exactly; `0004`
    never runs; the registry and `control_audit` are both untouched
    (row counts before/after are equal, R1-8)."""
    app = _provision_app(platform, "denyme")
    before_apps = _row_count(platform.control_dsn, platform.schema, "applications")
    before_audit = _row_count(platform.control_dsn, platform.schema, "control_audit")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_deprovision(monkeypatch, platform, "denyme", confirm="wrong-phrase")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    denial = json.loads(captured.err.strip())
    details = denial["details"]
    provisioned_at = _application_provisioned_at(platform, "denyme")
    expected_phrase = ops._deprovision_confirmation_phrase("denyme", provisioned_at)
    assert details["required_confirmation"] == expected_phrase
    assert details["consequence"] == ops._DEPROVISION_CONSEQUENCE
    assert details["reversible_alternative"] == ops._DEPROVISION_REVERSIBLE_ALTERNATIVE
    assert _database_exists(platform.admin_dsn, app.database)
    after_apps = _row_count(platform.control_dsn, platform.schema, "applications")
    after_audit = _row_count(platform.control_dsn, platform.schema, "control_audit")
    assert after_apps == before_apps
    assert after_audit == before_audit


def test_deprovision_confirm_omitted_is_a_json_denial_and_touches_nothing(platform, monkeypatch, capsys):
    """Completion condition 3 (差し戻し 1 F3): the SAME JSON-denial shape
    as a mismatched `--confirm` also holds when `--confirm` is OMITTED
    entirely (`args.confirm` stays `None`, never a special-cased
    bypass) -- exit 2, `required_confirmation`/`consequence`/
    `reversible_alternative` present and `required_confirmation`
    matching the real phrase exactly; `0004` never runs; the registry
    and `control_audit` are both untouched."""
    app = _provision_app(platform, "denyomit")
    before_apps = _row_count(platform.control_dsn, platform.schema, "applications")
    before_audit = _row_count(platform.control_dsn, platform.schema, "control_audit")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_deprovision(monkeypatch, platform, "denyomit")
    assert rc == 2
    assert calls == []
    captured = capsys.readouterr()
    denial = json.loads(captured.err.strip())
    details = denial["details"]
    provisioned_at = _application_provisioned_at(platform, "denyomit")
    expected_phrase = ops._deprovision_confirmation_phrase("denyomit", provisioned_at)
    assert details["required_confirmation"] == expected_phrase
    assert details["consequence"] == ops._DEPROVISION_CONSEQUENCE
    assert details["reversible_alternative"] == ops._DEPROVISION_REVERSIBLE_ALTERNATIVE
    assert _database_exists(platform.admin_dsn, app.database)
    after_apps = _row_count(platform.control_dsn, platform.schema, "applications")
    after_audit = _row_count(platform.control_dsn, platform.schema, "control_audit")
    assert after_apps == before_apps
    assert after_audit == before_audit


def test_deprovision_confirmation_phrase_changes_across_reprovision(platform, monkeypatch):
    """Completion condition 4: the confirmation phrase is bound to
    `provisioned_at` -- deprovisioning an application then re-
    provisioning the SAME slug yields a DIFFERENT required phrase."""
    _provision_app(platform, "reprovme")
    first_at = _application_provisioned_at(platform, "reprovme")
    first_phrase = ops._deprovision_confirmation_phrase("reprovme", first_at)
    rc = _run_deprovision(monkeypatch, platform, "reprovme", confirm=first_phrase)
    assert rc == 0
    _provision_app(platform, "reprovme")
    second_at = _application_provisioned_at(platform, "reprovme")
    second_phrase = ops._deprovision_confirmation_phrase("reprovme", second_at)
    assert second_phrase != first_phrase


def test_deprovision_matching_confirm_drops_database_and_both_roles(platform, monkeypatch):
    """Completion condition 5: a matching `--confirm` runs `0004` --
    the application's database and both its login roles are gone."""
    app = _provision_app(platform, "dropme")
    provisioned_at = _application_provisioned_at(platform, "dropme")
    phrase = ops._deprovision_confirmation_phrase("dropme", provisioned_at)
    rc = _run_deprovision(monkeypatch, platform, "dropme", confirm=phrase)
    assert rc == 0
    assert not _database_exists(platform.admin_dsn, app.database)
    assert not _role_exists(platform.admin_dsn, app.runtime_role)
    assert not _role_exists(platform.admin_dsn, app.developer_role)


def test_deprovision_refuses_when_a_credential_row_still_references_the_application(platform, monkeypatch, capsys):
    """Completion condition 6: with `0005_credential_store.sql` applied
    (this fixture's own bootstrap), a surviving `credentials` row for
    the slug makes `0004` itself refuse -- SPECIFICALLY via `0005`'s own
    `assert_no_credentials_for_deprovision` guard ("still has ...
    credential row(s) referencing it"), not merely any other failure --
    and database and roles are left standing (§1.3 (4))."""
    app = _provision_app(platform, "residue")
    provisioned_at = _application_provisioned_at(platform, "residue")
    phrase = ops._deprovision_confirmation_phrase("residue", provisioned_at)
    monkeypatch.setenv("R2DB_CREDENTIAL_PEPPER", "synthetic-test-pepper-r90-deprovision-0000")
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    try:
        rc = ops.main(["issue-credential", "residue", "runtime"])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 0
    rc = _run_deprovision(monkeypatch, platform, "residue", confirm=phrase, clear_ambient=False)
    assert rc != 0
    err = capsys.readouterr().err
    assert "still has" in err
    assert "credential row" in err
    assert _database_exists(platform.admin_dsn, app.database)
    assert _role_exists(platform.admin_dsn, app.runtime_role)


def test_deprovision_lock_timeout_is_required_with_no_default():
    """Completion condition 7: `--lock-timeout` is required with no
    default on the built `deprovision` subparser."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    subparser = subparsers_action.choices["deprovision"]
    action = next(a for a in subparser._actions if a.dest == "lock_timeout")
    assert action.required is True
    assert action.default is None


def test_deprovision_rejects_malformed_lock_timeout_before_any_psql(platform, monkeypatch):
    """Completion condition 7: a malformed `--lock-timeout` value is
    refused before any psql subprocess starts (the confirm phrase is
    supplied and correct, isolating this check)."""
    app = _provision_app(platform, "badtimeout")
    provisioned_at = _application_provisioned_at(platform, "badtimeout")
    phrase = ops._deprovision_confirmation_phrase("badtimeout", provisioned_at)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)) or pytest.fail("psql started"))
    rc = _run_deprovision(monkeypatch, platform, "badtimeout", confirm=phrase, lock_timeout="not-a-duration")
    assert rc == 2
    assert calls == []
    assert _database_exists(platform.admin_dsn, app.database)


def test_deprovision_argv_and_pgoptions_shape(platform, monkeypatch):
    """Completion condition 8: argv is `psql -v ON_ERROR_STOP=1 -v
    app_slug=<slug> -f <0004 path>`, with `PGOPTIONS` carrying `-c
    lock_timeout=<value>`."""
    app = _provision_app(platform, "argvcheck")
    provisioned_at = _application_provisioned_at(platform, "argvcheck")
    phrase = ops._deprovision_confirmation_phrase("argvcheck", provisioned_at)
    captured = []
    real_run = subprocess.run

    def _spy(argv, **kwargs):
        if argv[:1] == ["psql"] and "--version" not in argv:
            captured.append((argv, kwargs.get("env")))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy)
    rc = _run_deprovision(monkeypatch, platform, "argvcheck", confirm=phrase)
    assert rc == 0
    assert len(captured) == 1
    argv, env = captured[0]
    # `-f` receives the resolved path: `_run_deprovision_script` passes
    # `0004` through the same containment check every other psql `-f`
    # path in this module goes through.
    resolved = str((platform.migrations_dir / "0004_deprovision_application.sql").resolve())
    assert argv == ["psql", "-v", "ON_ERROR_STOP=1", "-v", "app_slug=argvcheck", "-f", resolved]
    assert f"-c lock_timeout={_TEST_LOCK_TIMEOUT}" in env["PGOPTIONS"]


def test_deprovision_redacts_dsn_values_on_script_failure(platform, monkeypatch, capsys):
    """Completion condition 9: a failed `0004` invocation's own output
    never contains the DSN's connection-parameter values."""
    app = _provision_app(platform, "faildeprovision")
    provisioned_at = _application_provisioned_at(platform, "faildeprovision")
    phrase = ops._deprovision_confirmation_phrase("faildeprovision", provisioned_at)
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(platform.migrations_dir))
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    _clear_ambient_pg_connection_env_vars(monkeypatch)

    def _fake(argv, **kwargs):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 16.0\n", stderr="")
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr=f"psql: error: connection failed: user={platform.control_role}",
        )

    monkeypatch.setattr(subprocess, "run", _fake)
    try:
        rc = ops.main(["deprovision", "faildeprovision", "--confirm", phrase, "--lock-timeout", _TEST_LOCK_TIMEOUT])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 2
    err = capsys.readouterr().err
    assert platform.control_role not in err
    assert _database_exists(platform.admin_dsn, app.database)


def test_deprovision_help_names_runbook_section_and_confirmation_fingerprint_source():
    """Completion condition 13b: the `deprovision` subcommand's own
    registered help text names `POSTGRES_PROVISIONING_RUNBOOK.md`
    section 5 and states that the `@registered=` digest is
    `provisioned_at`, changing across a deprovision-then-re-provision
    cycle."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    pseudo_action = next(a for a in subparsers_action._choices_actions if a.dest == "deprovision")
    help_text = pseudo_action.help
    assert "POSTGRES_PROVISIONING_RUNBOOK.md" in help_text
    assert "section 5" in help_text
    assert "provisioned_at" in help_text


# ===========================================================================
# WP-2 -- AST exact-set completion conditions 10/11
# ===========================================================================


def test_ddl_flowing_subcommands_are_exactly_apply_platform_migration_upgrade_applications_deprovision():
    """Completion condition 10: the AST-derived "flows DDL" set is
    EXACTLY `{apply-platform-migration, upgrade-applications,
    deprovision}` -- never a configuration-only subcommand
    (`declare-surfaces`/`declare-process-ceilings`/`declare-coalescing-
    window`/`set-platform-timeouts`, if present)."""
    derived = _derive_ddl_flowing_subcommands()
    assert derived == {"apply-platform-migration", "upgrade-applications", "deprovision"}


def test_psql_file_launching_functions_are_exactly_the_3_expected():
    """Completion condition 11: the AST-derived set of psql-`-f`-
    launching functions is EXACTLY `{_run_upgrade_script,
    _run_deprovision_script, cmd_apply_platform_migration}`."""
    derived = _derive_psql_file_launching_functions()
    assert derived == {"_run_upgrade_script", "_run_deprovision_script", "cmd_apply_platform_migration"}
