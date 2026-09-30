"""`ops startup-checks` -- the judgment of every declared revision's own startup
checks on role connection limits and on `max_connections` headroom against a
proposed `process_ceilings` declaration (`mitatedb_api.startup_checks`).

Covers: the per-class floors of each code generation against the real check
functions of that generation (read from git objects, run inside the test) at
`floor` and `floor - 1` (headroom at equality and one over); the migration
window; the pool-size input readers of every generation; generation
identification from git objects (the known table, its recomputation from every
representative ref, the current tree, the first-parent history, and the
positively identified oldest generation); the input rejections and their exit
codes (all before any database connection); and the output shape.

The database is a real PostgreSQL with a throwaway prefix (same shape as
`tests/test_ops_inventory.py`, not imported). A history that cannot be read is
a failure, never a silent pass.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import types
import typing
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import mitatedb_api.ops as ops
from mitatedb_api import config, http, platform_declarations, startup_checks
from mitatedb_api.startup_checks import DatabaseFacts, Identification, Revision

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = Path(startup_checks.__file__).resolve().parents[1]
_PACKAGE_DIR = "MitateDB-api/src/mitatedb_api/"

_DATA_URL = "https://startup-checks-test.example.invalid/v1"
_ZERO_REF = "0" * 40


# ---------------------------------------------------------------------------
# Database fixture (real PostgreSQL, throwaway prefix).
# ---------------------------------------------------------------------------


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; there is no shared-cluster default."
        )
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


def _bootstrap(prefix: str) -> types.SimpleNamespace:
    admin_dsn = _admin_dsn()
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)
    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_startup_checks_"))
    rewritten: dict = {}
    for name in (
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql", "0005_application_audit.sql",
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
        "0007_platform_declarations.sql", "0011_process_ceilings.sql",
    ):
        out = rewritten_dir / name
        out.write_text((MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix))
        rewritten[name] = out
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    for name in ("0002_registry_and_functions.sql", "0005_application_audit.sql", "0012_role_connection_limits.sql",
                 "0013_role_statement_timeouts.sql"):
        _run_psql(provision_dsn, rewritten[name])
    _run_psql(
        provision_dsn, rewritten["0007_platform_declarations.sql"],
        {"api_role": api_role, "controlplane_role": controlplane_role},
    )
    _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
    return types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, platform_db=platform_db,
        schema=schema, api_role=api_role, controlplane_role=controlplane_role,
        auditreader_role=f"{prefix}svc_auditreader",
    )


@pytest.fixture(scope="module")
def platform() -> Iterator[types.SimpleNamespace]:
    """One throwaway platform (0001/0002/0005/0012/0013/0007/0011) per module.
    Every test sets the limits it reads before reading them."""
    admin_dsn = _admin_dsn()
    try:
        psycopg.connect(admin_dsn, connect_timeout=5).close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_ops_startup_checks.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)
    prefix = f"r116chk{secrets.token_hex(4)}"
    try:
        info = _bootstrap(prefix)
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("MITATEDB_PROVISION_DSN", info.provision_dsn)
            patch.setenv("MITATEDB_PLATFORM_SCHEMA", info.schema)
            assert ops.main(["declare-surfaces", "--data-base-url", _DATA_URL, "--no-control"]) == 0
            assert ops.main(["declare-process-ceilings", "--data", "1", "--control", "1"]) == 0
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _set_limit(platform: types.SimpleNamespace, role: str, limit: int) -> None:
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT {}").format(sql.Identifier(role), sql.Literal(limit)))
    finally:
        admin.close()


def _set_limits(platform: types.SimpleNamespace, *, api: int, controlplane: int, auditreader: int) -> None:
    _set_limit(platform, platform.api_role, api)
    _set_limit(platform, platform.controlplane_role, controlplane)
    _set_limit(platform, platform.auditreader_role, auditreader)


@contextmanager
def _registered_application(platform: types.SimpleNamespace, app_id: str, *, runtime: int, developer: int):
    """A registry row with both roles set, and the two roles, removed on exit."""
    runtime_role = f"{platform.prefix}_{app_id}_rt"
    developer_role = f"{platform.prefix}_{app_id}_dev"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    provision = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for role, limit in ((runtime_role, runtime), (developer_role, developer)):
                cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN CONNECTION LIMIT {}").format(
                    sql.Identifier(role), sql.Literal(limit)))
        with provision.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {} (application_id, runtime_role, developer_role) VALUES (%s, %s, %s)").format(
                    sql.Identifier(platform.schema, "applications")),
                [app_id, runtime_role, developer_role],
            )
        yield runtime_role, developer_role
    finally:
        with provision.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE application_id = %s").format(sql.Identifier(platform.schema, "applications")),
                [app_id],
            )
        with admin.cursor() as cur:
            for role in (runtime_role, developer_role):
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        admin.close()
        provision.close()


def _read_facts(platform: types.SimpleNamespace) -> DatabaseFacts:
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        return startup_checks.read_database_facts(
            conn, schema=platform.schema, role_classes=ops._inventory_role_classes(conn, platform.schema),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Git helpers (history is shared by every worktree).
# ---------------------------------------------------------------------------


def _git(repository: "str | Path", *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}", *arguments],
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        pytest.fail(f"git {' '.join(arguments)} failed: {result.stderr.strip()}", pytrace=False)
    return result.stdout


def _require_history() -> None:
    """The oldest ref these tests read must resolve: an unreadable history is
    a failure (a shallow checkout would otherwise pass vacuously)."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--verify", "9361f1b^{commit}"], capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail("the git history is not readable here (a full-depth checkout is required)", pytrace=False)


def _full(ref: str) -> str:
    _require_history()
    return _git(_REPO_ROOT, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _show(ref: str, path: str) -> str:
    return _git(_REPO_ROOT, "show", f"{ref}:{path}")


def _known_row(plane: str, generation: str) -> "startup_checks.KnownFingerprint":
    return next(row for row in startup_checks.KNOWN_FINGERPRINTS if row.plane == plane and row.generation == generation
                and row.representative_ref)


def _ref_of(generation: str) -> str:
    _require_history()
    return _known_row("data", generation).representative_ref


def _make_repository(root: Path, files: "dict[str, str]") -> "tuple[str, str]":
    """A synthetic git repository with one commit holding `files` (paths from the
    repository root). Returns (path, commit id)."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture")
    return str(root), _git(root, "rev-parse", "HEAD").strip()


_START_MAIN = "def build_app():\n    return None\n"
_START_CONTROL = "def build_control_service():\n    return None\n"


def _synthetic_files(**extra: str) -> "dict[str, str]":
    files = {
        _PACKAGE_DIR + "main.py": _START_MAIN,
        _PACKAGE_DIR + "control_composition.py": _START_CONTROL,
    }
    files.update({_PACKAGE_DIR + name: content for name, content in extra.items()})
    return files


_module_cache: dict = {}


def _load_module(ref: str, filename: str) -> types.ModuleType:
    """A module compiled from `<ref>:<filename>` of the package, run as a
    submodule of `mitatedb_api` so its relative imports resolve (the
    dependencies of the old files are current files)."""
    key = (ref, filename)
    if key not in _module_cache:
        source = _show(ref, _PACKAGE_DIR + filename)
        name = f"mitatedb_api._startup_checks_test_{Path(filename).stem}_{ref[:12]}"
        module = types.ModuleType(name)
        module.__package__ = "mitatedb_api"
        sys.modules[name] = module
        try:
            exec(compile(source, f"<{ref[:12]}:{filename}>", "exec"), module.__dict__)
        finally:
            sys.modules.pop(name, None)
        _module_cache[key] = module
    return _module_cache[key]


# ---------------------------------------------------------------------------
# Builders.
# ---------------------------------------------------------------------------


def _revision(
    plane: str = "data", *, max_concurrency: "str | None" = None, thread_limit: "str | None" = None,
    audit: "bool | None" = None,
) -> Revision:
    return Revision(
        name="rev", plane=plane, kinds=("serving",), source_ref=_ZERO_REF, max_concurrency=max_concurrency,
        thread_limit=thread_limit, audit_dsn_configured=audit if plane == "control" else None,
    )


def _facts(**overrides) -> DatabaseFacts:
    values = dict(
        api_roles=("api_role",), controlplane_roles=("cp_role",), auditreader_roles=("ar_role",),
        application_roles=(), role_limits={"api_role": 1000, "cp_role": 1000, "ar_role": 1000},
        registered_applications=0, settings=(1000, 3, 0), declared_process_ceilings={"data": 1, "control": 1},
    )
    values.update(overrides)
    return DatabaseFacts(**values)


def _evaluate(revision: Revision, generation: "str | None", facts: DatabaseFacts, d: int = 3, c: int = 2,
              reason: "str | None" = None) -> dict:
    return startup_checks.evaluate_revision(revision, Identification(generation, reason), facts, d, c)


def _entry(platform: types.SimpleNamespace, revision: Revision, generation: str, d: int = 3, c: int = 2) -> dict:
    return _evaluate(revision, generation, _read_facts(platform), d, c)


def _rev_json(name: str, plane: str, ref: str, kinds: "list[str]", *, max_concurrency=None, thread_limit=None,
              audit=None) -> dict:
    entry = {
        "name": name, "plane": plane, "kinds": kinds, "source_ref": ref,
        "env": {"MITATEDB_MAX_CONCURRENCY": max_concurrency, "MITATEDB_THREAD_LIMIT": thread_limit},
    }
    if plane == "control":
        entry["audit_dsn_configured"] = True if audit is None else audit
    return entry


def _document(data_ref: str = _ZERO_REF, control_ref: str = _ZERO_REF, **overrides) -> dict:
    """A complete valid revisions document, then `overrides` applied."""
    document = {
        "format": "mitatedb-startup-checks/1",
        "declared_absent": ["data.env_only_revision", "data.other", "control.env_only_revision", "control.other"],
        "revisions": [
            _rev_json("data-a", "data", data_ref, ["serving", "rollback_target", "candidate"]),
            _rev_json("control-a", "control", control_ref, ["serving", "rollback_target", "candidate"]),
        ],
    }
    document.update(overrides)
    return document


@dataclasses.dataclass
class _Run:
    rc: int
    report: "dict | None"
    out: str
    err: str
    connects: list


def _run(monkeypatch, capsys, platform, tmp_path, document: "dict | str", *, data: int = 3, control: int = 2,
         repository: "str | Path | None" = None, extra: "list[str] | None" = None) -> _Run:
    path = tmp_path / "revisions.json"
    path.write_text(document if isinstance(document, str) else json.dumps(document))
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    connects: list = []
    real_connect = psycopg.connect

    def spy(*args, **kwargs):
        connects.append(args)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(psycopg, "connect", spy)
    argv = [
        "startup-checks", "--data", str(data), "--control", str(control), "--revisions", str(path),
        "--repository", str(repository if repository is not None else _REPO_ROOT), *(extra or []),
    ]
    try:
        rc = ops.main(argv)
    except SystemExit as exc:
        rc = exc.code
    captured = capsys.readouterr()
    report = json.loads(captured.out) if captured.out.strip() else None
    return _Run(rc, report, captured.out, captured.err, connects)


# ===========================================================================
# Current generation: floors against the real check functions.
# ===========================================================================


def _real_passes(module, check, *args, **kwargs) -> bool:
    try:
        check(*args, **kwargs)
    except module.PlatformDeclarationError:
        return False
    return True


def _independent_pool_size(thread_limit: str) -> int:
    return config.role_pool_size(config.thread_limit_from_env({"MITATEDB_THREAD_LIMIT": thread_limit}, "MITATEDB_THREAD_LIMIT", 4))


def _real_f16(platform, p: int, d: int, c: int, classes, application_ids) -> bool:
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        return _real_passes(
            platform_declarations, platform_declarations.check_role_connection_limits, conn, schema=platform.schema, ops_module="mitatedb_api",
            pool_size=p, process_ceilings=platform_declarations.ProcessCeilings(data=d, control=c),
            role_classes=frozenset(classes), application_ids=application_ids,
        )
    finally:
        conn.close()


def _assert_floor_agrees(platform, *, role: str, floor: int, tool_current, real) -> None:
    for limit, should_pass in ((floor, True), (floor - 1, False)):
        _set_limit(platform, role, limit)
        assert tool_current() == ("confirmed" if should_pass else "blocked"), (role, limit)
        assert real() is should_pass, (role, limit)


def test_current_generation_api_floor_agrees_with_the_real_check_at_the_boundary(platform):
    """Data plane, api role: floor `2 * p * D`, with p computed by the test
    from the same env through the shared readers, agrees with the real
    `check_role_connection_limits` at `floor` and `floor - 1` (D = 3, C = 2)."""
    d, c = 3, 2
    p = _independent_pool_size("3")
    revision = _revision("data", thread_limit="3")
    _set_limits(platform, api=-1, controlplane=-1, auditreader=-1)
    floor = 2 * p * d
    _assert_floor_agrees(
        platform, role=platform.api_role, floor=floor,
        tool_current=lambda: _entry(platform, revision, "G3", d, c)["f16"]["current_judgment"],
        real=lambda: _real_f16(platform, p, d, c, {"api"}, ()),
    )
    assert _entry(platform, revision, "G3", d, c)["f16"]["roles"][0]["floor"] == floor


def test_current_generation_application_floor_agrees_with_the_real_check_at_the_boundary(platform):
    """Data plane, an application's runtime role: floor `p * D`."""
    d, c = 3, 2
    p = _independent_pool_size("3")
    revision = _revision("data", thread_limit="3")
    _set_limits(platform, api=-1, controlplane=-1, auditreader=-1)
    with _registered_application(platform, "chkapp", runtime=1000, developer=1000) as (runtime_role, _developer):
        _assert_floor_agrees(
            platform, role=runtime_role, floor=p * d,
            tool_current=lambda: _entry(platform, revision, "G3", d, c)["f16"]["current_judgment"],
            real=lambda: _real_f16(platform, p, d, c, set(), ["chkapp"]),
        )


def test_current_generation_controlplane_floor_agrees_with_the_real_check_at_the_boundary(platform):
    """Control plane, controlplane role: floor `16 * C` (C = 2 -> 32)."""
    d, c = 3, 2
    revision = _revision("control", thread_limit="3", audit=False)
    _set_limits(platform, api=-1, controlplane=-1, auditreader=-1)
    _assert_floor_agrees(
        platform, role=platform.controlplane_role, floor=16 * c,
        tool_current=lambda: _entry(platform, revision, "G3", d, c)["f16"]["current_judgment"],
        real=lambda: _real_f16(platform, _independent_pool_size("3"), d, c, {"controlplane"}, ()),
    )


def test_current_generation_auditreader_floor_agrees_with_the_real_check_at_the_boundary(platform):
    """Control plane with an audit dsn, auditreader role: floor `4 * C`."""
    d, c = 3, 2
    revision = _revision("control", thread_limit="3", audit=True)
    _set_limits(platform, api=-1, controlplane=-1, auditreader=-1)
    _assert_floor_agrees(
        platform, role=platform.auditreader_role, floor=4 * c,
        tool_current=lambda: _entry(platform, revision, "G3", d, c)["f16"]["current_judgment"],
        real=lambda: _real_f16(platform, _independent_pool_size("3"), d, c, {"auditreader"}, ()),
    )


def _real_f18(platform, monkeypatch, module, *, registered: int, settings: tuple, kwargs: dict) -> bool:
    monkeypatch.setattr(module, "_read_connection_headroom_settings", lambda conn: settings)
    monkeypatch.setattr(module, "_count_registered_applications", lambda conn, schema: registered)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        return _real_passes(
            module, module.check_max_connections_headroom, conn, schema=platform.schema, ops_module="mitatedb_api", **kwargs,
        )
    finally:
        conn.close()


def test_current_generation_headroom_agrees_with_the_real_check_at_equality_and_one_over(platform, monkeypatch):
    """F-18: with 1 registered application, D = 3, C = 2, p = 6 the lower bound
    is 104; plus the two reserved settings (3 + 1) it equals `max_connections`
    = 108 and passes there, and fails at 107."""
    d, c = 3, 2
    p = _independent_pool_size("4")
    revision = _revision("data", thread_limit="4")
    for max_connections, should_pass in ((108, True), (107, False)):
        facts = _facts(registered_applications=1, settings=(max_connections, 3, 1))
        entry = _evaluate(revision, "G3", facts, d, c)
        assert entry["f18"]["lower_bound"] == 104
        assert entry["f18"]["judgment"] == ("confirmed" if should_pass else "blocked")
        assert _real_f18(
            platform, monkeypatch, platform_declarations, registered=1, settings=(max_connections, 3, 1),
            kwargs=dict(process_ceilings=platform_declarations.ProcessCeilings(data=d, control=c), pool_size=p),
        ) is should_pass


# ===========================================================================
# Frozen generations and every representative ref: the formulas against the
# ref's own check functions.
# ===========================================================================


def _rows_with_ref() -> list:
    return [row for row in startup_checks.KNOWN_FINGERPRINTS if row.representative_ref]


def _old_f16(pd, generation: str, conn, schema: str, x: int, d: int, c: int, classes, application_ids) -> bool:
    common = dict(schema=schema, ops_module="mitatedb_api", role_classes=frozenset(classes), application_ids=application_ids)
    try:
        if generation == "G3":
            pd.check_role_connection_limits(
                conn, pool_size=x, process_ceilings=pd.ProcessCeilings(data=d, control=c), **common)
        else:
            pd.check_role_connection_limits(conn, concurrency=x, **common)
    except pd.PlatformDeclarationError:
        return False
    return True


def _f16_agrees_on_row(platform, row) -> None:
    """The row's generation formula for the api role and one application's
    runtime role (data plane) or the controlplane and auditreader roles
    (control plane) against the row's own ref, at floor and floor - 1."""
    d, c = 3, 2
    ref = row.representative_ref
    pd = _load_module(ref, "platform_declarations.py")
    if row.generation == "G3":
        cfg = _load_module(ref, "config.py")
        env = {"MITATEDB_THREAD_LIMIT": "3"}
        x = cfg.role_pool_size(cfg.thread_limit_from_env(env, "MITATEDB_THREAD_LIMIT", 4))
        revision = _revision(row.plane, thread_limit="3", audit=True)
        assert _evaluate(revision, "G3", _facts(), d, c)["pool_input"]["x"] == x, ref
    else:
        x = 10
        revision = _revision(row.plane, max_concurrency="10", audit=True)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        _set_limits(platform, api=-1, controlplane=-1, auditreader=-1)
        if row.plane == "data":
            targets = [(platform.api_role, "api")]
        else:
            targets = [(platform.controlplane_role, "controlplane"), (platform.auditreader_role, "auditreader")]
        for role, role_class in targets:
            floor = next(
                entry["floor"] for entry in _entry(platform, revision, row.generation, d, c)["f16"]["roles"]
                if entry["role"] == role
            )
            for limit, should_pass in ((floor, True), (floor - 1, False)):
                _set_limit(platform, role, limit)
                tool = _entry(platform, revision, row.generation, d, c)["f16"]["current_judgment"]
                real = _old_f16(pd, row.generation, conn, platform.schema, x, d, c, {role_class}, ())
                assert (tool == "confirmed") is should_pass and real is should_pass, (ref, row.plane, role, limit)
            _set_limit(platform, role, -1)
        if row.plane == "data":
            with _registered_application(platform, "rowapp", runtime=1000, developer=1000) as (runtime_role, _developer):
                floor = next(
                    entry["floor"] for entry in _entry(platform, revision, row.generation, d, c)["f16"]["roles"]
                    if entry["role"] == runtime_role
                )
                for limit, should_pass in ((floor, True), (floor - 1, False)):
                    _set_limit(platform, runtime_role, limit)
                    tool = _entry(platform, revision, row.generation, d, c)["f16"]["current_judgment"]
                    real = _old_f16(pd, row.generation, conn, platform.schema, x, d, c, set(), ["rowapp"])
                    assert (tool == "confirmed") is should_pass and real is should_pass, (ref, "application", limit)
    finally:
        conn.close()


def _f18_agrees_on_row(platform, monkeypatch, row) -> None:
    """The row's headroom formula against the row's own `check_max_connections_
    headroom`, with 1 registered application at equality and one over."""
    d, c = 3, 2
    ref = row.representative_ref
    pd = _load_module(ref, "platform_declarations.py")
    if row.generation == "G3":
        cfg = _load_module(ref, "config.py")
        x = cfg.role_pool_size(cfg.thread_limit_from_env({"MITATEDB_THREAD_LIMIT": "3"}, "MITATEDB_THREAD_LIMIT", 4))
        revision = _revision(row.plane, thread_limit="3", audit=True)
        kwargs = dict(process_ceilings=pd.ProcessCeilings(data=d, control=c), pool_size=x)
    else:
        x = 10
        revision = _revision(row.plane, max_concurrency="10", audit=True)
        kwargs = dict(process_ceilings=pd.ProcessCeilings(data=d, control=c), concurrency=x)
    lower = _evaluate(revision, row.generation, _facts(registered_applications=1), d, c)["f18"]["lower_bound"]
    for max_connections, should_pass in ((lower + 4, True), (lower + 3, False)):
        settings = (max_connections, 3, 1)
        tool = _evaluate(revision, row.generation, _facts(registered_applications=1, settings=settings), d, c)["f18"]["judgment"]
        real = _real_f18(platform, monkeypatch, pd, registered=1, settings=settings, kwargs=kwargs)
        assert (tool == "confirmed") is should_pass and real is should_pass, (ref, row.plane, max_connections)


def test_frozen_generation_role_floors_agree_with_the_check_of_a_representative_ref(platform):
    """G1 and G2 role floors (no process multiplier: api `2x`, controlplane 16,
    auditreader 4) against the real check of a representative ref, at floor and
    floor - 1, with D = 3 and C = 2 so that a multiplier would disagree."""
    _require_history()
    for generation in ("G1", "G2"):
        for plane in ("data", "control"):
            _f16_agrees_on_row(platform, _known_row(plane, generation))


def test_frozen_generation_headroom_agrees_with_the_check_of_a_representative_ref(platform, monkeypatch):
    """G2 headroom (`D * (2x + 2x) + 16 * C` with one registered application)
    against a representative G2 ref's own check at equality and one over. G1
    carries no headroom check."""
    _require_history()
    _f18_agrees_on_row(platform, monkeypatch, _known_row("data", "G2"))


def test_every_row_with_a_representative_ref_agrees_with_that_refs_check_functions(platform, monkeypatch):
    """Every table row that has a representative ref: the tool's formula for
    the row's generation, with the ref's own platform declarations (and, for the
    current generation, its own configuration reader) loaded from git objects,
    agrees at floor and floor - 1 (headroom: equality and one over)."""
    _require_history()
    rows = _rows_with_ref()
    assert len(rows) >= 23
    for row in rows:
        _f16_agrees_on_row(platform, row)
        if row.generation in ("G2", "G3"):
            _f18_agrees_on_row(platform, monkeypatch, row)


# ===========================================================================
# Headroom details.
# ===========================================================================


def test_headroom_with_no_registration_is_judged_at_one_and_shows_the_zero_bound():
    """Zero registered applications: judged at "at least one" (lower bound
    with the application pair), the zero-registration bound reported beside it
    and the judged count 1."""
    revision = _revision("data", thread_limit="4")
    facts = _facts(registered_applications=0, settings=(1000, 3, 0))
    f18 = _evaluate(revision, "G3", facts, 3, 2)["f18"]
    assert f18["registered_applications_judged"] == 1
    assert f18["lower_bound"] == 3 * (12 + 12) + 32
    assert f18["lower_bound_without_registrations"] == 3 * 12 + 32
    assert f18["lower_bound"] > f18["lower_bound_without_registrations"]
    two = _evaluate(revision, "G3", _facts(registered_applications=2, settings=(1000, 3, 0)), 3, 2)["f18"]
    assert two["registered_applications_judged"] == 2 and two["lower_bound"] == f18["lower_bound"]


def test_registered_applications_count_includes_a_row_whose_roles_are_null(platform):
    """A registered-but-not-provisioned row (roles NULL) is counted."""
    provision = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        before = _read_facts(platform).registered_applications
        with provision.cursor() as cur:
            cur.execute(sql.SQL("INSERT INTO {} (application_id) VALUES (%s)").format(
                sql.Identifier(platform.schema, "applications")), ["nullroles"])
        try:
            assert _read_facts(platform).registered_applications == before + 1
            assert _read_facts(platform).application_roles == ()
        finally:
            with provision.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {} WHERE application_id = %s").format(
                    sql.Identifier(platform.schema, "applications")), ["nullroles"])
    finally:
        provision.close()


# ===========================================================================
# Pool-size input readers.
# ===========================================================================

_PARSE_INPUTS = ("1_000", " 7", "", "0", "-3", "abc", None)


def _data_reader(ref: str):
    source = _show(ref, _PACKAGE_DIR + "main.py")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_optional_int")
    namespace: dict = {"Mapping": typing.Mapping}
    exec(compile(ast.Module(body=[node], type_ignores=[]), f"<{ref[:12]}:main.py>", "exec"), namespace)
    return lambda raw: namespace["_optional_int"]({} if raw is None else {"MITATEDB_MAX_CONCURRENCY": raw},
                                                   "MITATEDB_MAX_CONCURRENCY", 32)


def _control_reader(ref: str):
    tree = ast.parse(_show(ref, _PACKAGE_DIR + "control_composition.py"))
    statements = None
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for index, statement in enumerate(body):
            if (isinstance(statement, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "_raw_declared_concurrency" for t in statement.targets)):
                statements = [statement, body[index + 1]]
    assert statements is not None, "the control reader was not found"
    code = compile(ast.Module(body=statements, type_ignores=[]), f"<{ref[:12]}:control_composition.py>", "exec")

    def read(raw):
        namespace = {"env": {} if raw is None else {"MITATEDB_MAX_CONCURRENCY": raw},
                     "FoundationConfig": types.SimpleNamespace(max_concurrency=32)}
        exec(code, namespace)
        return namespace["_declared_concurrency"]
    return read


def test_frozen_generation_parse_agrees_with_the_readers_of_a_representative_ref():
    """The frozen generations' pool-size reader agrees with the data reader
    (`_optional_int`) and the control reader (the inline read) of a G1 and a
    G2 representative ref on seven inputs, `"1_000"`, `" 7"`, `""`, `"0"`,
    `"-3"`, `"abc"` and unset."""
    _require_history()
    for generation in ("G1", "G2"):
        for plane, reader in (("data", _data_reader), ("control", _control_reader)):
            read = reader(_known_row(plane, generation).representative_ref)
            for raw in _PARSE_INPUTS:
                assert startup_checks._frozen_concurrency(raw) == read(raw), (generation, plane, raw)
    assert startup_checks._frozen_concurrency("1_000") == 1000 and startup_checks._frozen_concurrency(" 7") == 7


def test_an_unset_env_gets_the_default_of_the_generation():
    """Unset (`null`) is the generation's default: 32 for G1 and G2, 4 for G3;
    the declared and the applied value are both in the output."""
    assert http.DEFAULT_THREAD_LIMIT == 4
    for generation in ("G1", "G2"):
        pool = _evaluate(_revision("data"), generation, _facts())["pool_input"]
        assert pool == {"env": "MITATEDB_MAX_CONCURRENCY", "declared": None, "applied": 32, "x": 32}
    pool = _evaluate(_revision("data"), "G3", _facts())["pool_input"]
    assert pool == {"env": "MITATEDB_THREAD_LIMIT", "declared": None, "applied": 4, "x": 6}


def test_current_generation_pool_size_is_the_shared_reader_result():
    """G3: `x` is `role_pool_size(thread_limit)` (thread limit 7 -> 9), not the
    thread limit."""
    pool = _evaluate(_revision("data", thread_limit="7"), "G3", _facts())["pool_input"]
    assert pool["applied"] == 7 and pool["x"] == config.role_pool_size(7) == 9


@pytest.mark.parametrize("bad", ["abc", "0", "-1"])
def test_an_invalid_current_generation_env_blocks_both_checks(bad):
    """A thread limit the shared reader refuses: both checks blocked with
    `startup-fails-on-env` (the revision would not start)."""
    entry = _evaluate(_revision("data", thread_limit=bad), "G3", _facts())
    for key in ("f16", "f18"):
        assert entry[key]["judgment"] == "blocked" and entry[key]["reason"] == "startup-fails-on-env", key
    assert entry["reason"] is None and entry["pool_input"]["x"] is None


# ===========================================================================
# Roles of a class, and settings that do not read.
# ===========================================================================


def test_no_api_role_makes_the_data_f16_unknown():
    """Data plane with no role of class api: f16 `unknown`, `no-role-of-class`."""
    f16 = _evaluate(_revision("data", thread_limit="4"), "G3", _facts(api_roles=()))["f16"]
    assert f16["judgment"] == "unknown" and f16["reason"] == "no-role-of-class"
    assert _evaluate(_revision("data", thread_limit="4"), "G3", _facts())["f16"]["judgment"] == "confirmed"


def test_no_auditreader_role_makes_an_audit_configured_control_f16_unknown():
    """Control with `audit_dsn_configured: true` and no auditreader role: f16
    `unknown`; without an audit dsn the same facts are `confirmed`."""
    facts = _facts(auditreader_roles=())
    f16 = _evaluate(_revision("control", thread_limit="4", audit=True), "G3", facts, 1, 1)["f16"]
    assert f16["judgment"] == "unknown" and f16["reason"] == "no-role-of-class"
    assert _evaluate(_revision("control", thread_limit="4", audit=False), "G3", facts, 1, 1)["f16"]["judgment"] == "confirmed"


def test_no_controlplane_role_makes_the_control_f16_unknown():
    facts = _facts(controlplane_roles=())
    f16 = _evaluate(_revision("control", thread_limit="4", audit=False), "G3", facts, 1, 1)["f16"]
    assert f16["judgment"] == "unknown" and f16["reason"] == "no-role-of-class"


def test_the_current_declaration_is_read_from_its_one_row_in_three_states(platform):
    """`declaration.current` is read from the `process_ceilings` row alone:
    the declared numbers when the row is valid, `not-declared` when the table
    has no such row (the other declaration rows are not needed), `unreadable`
    when the value is malformed. The fixture's row is restored afterwards."""
    provision = psycopg.connect(platform.provision_dsn, autocommit=True)
    table = sql.Identifier(platform.schema, platform_declarations.TABLE_NAME)
    try:
        with provision.cursor() as cur:
            cur.execute(sql.SQL("SELECT value FROM {} WHERE key = 'process_ceilings'").format(table))
            original = cur.fetchone()[0]
        assert _read_facts(platform).declared_process_ceilings == {"data": 1, "control": 1}
        try:
            with provision.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {} WHERE key = 'process_ceilings'").format(table))
            assert _read_facts(platform).declared_process_ceilings == "not-declared"
            with provision.cursor() as cur:
                cur.execute(sql.SQL("INSERT INTO {} (key, value) VALUES ('process_ceilings', %s)").format(table),
                            [psycopg.types.json.Json({"data": 0})])
            assert _read_facts(platform).declared_process_ceilings == "unreadable"
        finally:
            with provision.cursor() as cur:
                cur.execute(sql.SQL("DELETE FROM {} WHERE key = 'process_ceilings'").format(table))
                cur.execute(sql.SQL("INSERT INTO {} (key, value) VALUES ('process_ceilings', %s)").format(table),
                            [psycopg.types.json.Json(original)])
    finally:
        provision.close()


def test_missing_headroom_settings_block_f18_and_still_judge_f16_with_exit_2(
        monkeypatch, capsys, platform, tmp_path):
    """The database does not answer all three settings: every revision that
    carries F-18 is `blocked` with `headroom-settings-missing`, F-16 is still
    judged, the exit code is 2."""
    def missing(conn):
        raise platform_declarations.PlatformDeclarationError("settings missing", code="F-18")

    monkeypatch.setattr(platform_declarations, "_read_connection_headroom_settings", missing)
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    run = _run(monkeypatch, capsys, platform, tmp_path,
               _document(data_ref=_ref_of("G3"), control_ref=_ref_of("G2")), data=1, control=1)
    assert run.rc == 2 and run.report is not None
    by_name = {entry["name"]: entry for entry in run.report["revisions"]}
    for name in ("data-a", "control-a"):
        f18 = by_name[name]["f18"]
        assert f18["judgment"] == "blocked" and f18["reason"] == "headroom-settings-missing", name
        assert by_name[name]["f16"]["judgment"] == "confirmed" and by_name[name]["f16"]["roles"], name
    assert run.report["overall"] == "blocked"
    assert run.report["database"]["max_connections"] is None


# ===========================================================================
# Migration window.
# ===========================================================================


def test_window_is_the_minimum_of_current_and_both_migration_values_per_class(platform):
    """Each class's window: min(current, 0012, 0014). Current limits are the
    0014 values (api 132, controlplane 36, auditreader 12, application 68):
    windows 68, 20, 12, 36."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    with _registered_application(platform, "winapp", runtime=68, developer=68) as (runtime_role, _developer):
        data = _entry(platform, _revision("data", thread_limit="4"), "G3", 1, 1)["f16"]["roles"]
        control = _entry(platform, _revision("control", thread_limit="4", audit=True), "G3", 1, 1)["f16"]["roles"]
    windows = {entry["class"]: entry["window_limit"] for entry in data + control}
    assert windows == {"api": 68, "application": 36, "controlplane": 20, "auditreader": 12}
    assert {entry["class"]: entry["current_limit"] for entry in data + control} == {
        "api": 132, "application": 68, "controlplane": 36, "auditreader": 12}


def test_window_is_applied_by_the_class_of_the_grant_not_the_name_of_the_role(platform):
    """The fixture's roles carry a throwaway prefix, not `mitatedbsvc_`: the api
    role still gets the api class window (68), not its current limit."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    roles = _entry(platform, _revision("data", thread_limit="4"), "G3", 1, 1)["f16"]["roles"]
    api = next(entry for entry in roles if entry["class"] == "api")
    assert not api["role"].startswith("mitatedbsvc_")
    assert api["window_limit"] == 68 and api["current_limit"] == 132


def test_minus_one_is_left_out_of_the_window_minimum(platform):
    """An api role with limit `-1`: the window is the migration values' minimum
    (68), and with floor 36 (`2 * 6 * D`, D = 3) the window judgment is
    confirmed; `-1` is not read as a smaller limit."""
    _set_limits(platform, api=-1, controlplane=36, auditreader=12)
    f16 = _entry(platform, _revision("data", thread_limit="4"), "G3", 3, 1)["f16"]
    api = next(entry for entry in f16["roles"] if entry["class"] == "api")
    assert api["current_limit"] == -1 and api["window_limit"] == 68 and api["floor"] == 36
    assert f16["window_judgment"] == "confirmed" and f16["current_judgment"] == "confirmed"


def test_overall_judgment_is_the_window_judgment(platform, monkeypatch, capsys, tmp_path):
    """Control, C = 2: controlplane current 36, floor 32, window 20. The current
    limit passes, the window does not: the revision's judgment and `overall` are
    `blocked`."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    f16 = _entry(platform, _revision("control", thread_limit="4", audit=False), "G3", 1, 2)["f16"]
    assert f16["current_judgment"] == "confirmed" and f16["window_judgment"] == "blocked"
    assert f16["judgment"] == "blocked"
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(data_ref=_ref_of("G3"), control_ref=_ref_of("G3")),
               data=1, control=2)
    control = next(entry for entry in run.report["revisions"] if entry["name"] == "control-a")
    assert control["f16"]["judgment"] == "blocked" and run.report["overall"] == "blocked" and run.rc == 2


def test_migration_constants_equal_the_values_in_the_migrations():
    """The tool's window constants equal the `CONNECTION LIMIT` values in
    0012 and 0014 for the four classes."""
    twelve = (MIGRATIONS_DIR / "0012_role_connection_limits.sql").read_text()
    fourteen = (MIGRATIONS_DIR / "0014_role_connection_limits_rollout.sql").read_text()

    def platform_role(text: str, role: str) -> int:
        matches = re.findall(rf"ALTER ROLE {role} CONNECTION LIMIT (\d+);", text)
        assert len(matches) == 1, (role, matches)
        return int(matches[0])

    def application(text: str) -> int:
        matches = set(re.findall(r"EXECUTE format\('ALTER ROLE %I CONNECTION LIMIT (\d+)'", text))
        assert len(matches) == 1, matches
        return int(matches.pop())

    assert "mitatedbsvc_auditreader" not in re.findall(r"ALTER ROLE (\w+) CONNECTION LIMIT", twelve)
    assert startup_checks._MIGRATION_LIMITS == {
        "api": (platform_role(twelve, "mitatedbsvc_api"), platform_role(fourteen, "mitatedbsvc_api")),
        "controlplane": (platform_role(twelve, "mitatedbsvc_controlplane"), platform_role(fourteen, "mitatedbsvc_controlplane")),
        "auditreader": (None, platform_role(fourteen, "mitatedbsvc_auditreader")),
        "application": (application(twelve), application(fourteen)),
    }


# ===========================================================================
# Generation identification.
# ===========================================================================


def test_every_row_with_a_representative_ref_is_recomputed_from_that_ref():
    """The fingerprint recomputed from each representative ref equals its
    table literal (blob ids, the digest of the `DEFAULT_THREAD_LIMIT`
    assignment, the check-function reference list); at least 23 rows carry a
    ref (12 data, 11 control)."""
    _require_history()
    rows = _rows_with_ref()
    assert sum(1 for row in rows if row.plane == "data") >= 12 and sum(1 for row in rows if row.plane == "control") >= 11
    for row in rows:
        computed = startup_checks.source_tree_fingerprint_at(str(_REPO_ROOT), row.representative_ref).fingerprint(row.plane)
        assert computed == row.fingerprint, (row.plane, row.generation, row.representative_ref)


def _current_row(plane: str) -> "startup_checks.KnownFingerprint":
    rows = [row for row in startup_checks.KNOWN_FINGERPRINTS if row.plane == plane and row.generation == "G3"]
    assert rows
    return rows[-1]  # the newest row: a change that keeps the formula appends a row of the same generation


def test_working_tree_data_fingerprint_is_the_current_generation_row():
    """The data plane's fingerprint computed from the files of the imported
    package equals the G3 data row: a change to the data startup module, the
    platform declarations, the configuration or the check references is red
    here until the table is updated."""
    computed = startup_checks.working_tree_fingerprints(_SOURCE_ROOT).fingerprint("data")
    assert computed == _current_row("data").fingerprint


def test_working_tree_control_fingerprint_is_the_current_generation_row():
    """The control plane's fingerprint computed from the files of the imported
    package equals the G3 control row."""
    computed = startup_checks.working_tree_fingerprints(_SOURCE_ROOT).fingerprint("control")
    assert computed == _current_row("control").fingerprint


def test_every_first_parent_fingerprint_is_in_the_table():
    """Walking the first-parent history from the parent of the first commit that
    carried the checks to HEAD, every (plane, fingerprint) is a table row. A
    history that cannot be read fails."""
    _require_history()
    known = {(row.plane, row.fingerprint) for row in startup_checks.KNOWN_FINGERPRINTS}
    commits = startup_checks.first_parent_commits(str(_REPO_ROOT), "9361f1b^1..HEAD")
    assert len(commits) >= 284
    unknown = []
    for commit in commits:
        tree = startup_checks.source_tree_fingerprint_at(str(_REPO_ROOT), commit)
        for plane in startup_checks.PLANES:
            if (plane, tree.fingerprint(plane)) not in known:
                unknown.append((commit[:9], plane))
    assert unknown == []


def test_a_ref_that_does_not_exist_is_unknown_with_ref_not_found():
    _require_history()
    result = startup_checks.identify_generation(str(_REPO_ROOT), "data", "1" * 40)
    assert result == Identification(None, "ref-not-found")
    assert _evaluate(_revision("data"), None, _facts(), reason="ref-not-found")["reason"] == "ref-not-found"


def test_git_is_run_with_lazy_fetch_disabled(monkeypatch):
    """Every git command the tool runs carries `GIT_NO_LAZY_FETCH=1` (a partial
    clone never fetches a missing object) and `GIT_NO_REPLACE_OBJECTS=1` (a
    `refs/replace` entry never substitutes an object) in its environment."""
    ref = _ref_of("G3")
    environments: list = []
    real_run = subprocess.run

    def observing(*args, **kwargs):
        environments.append(kwargs.get("env"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", observing)
    assert startup_checks.identify_generation(str(_REPO_ROOT), "data", ref).generation == "G3"
    assert environments and all(env is not None and env.get("GIT_NO_LAZY_FETCH") == "1" for env in environments)
    assert all(env.get("GIT_NO_REPLACE_OBJECTS") == "1" for env in environments)


def test_a_failed_git_read_is_unknown_with_git_failed(tmp_path):
    """A repository whose git commands fail (a directory that is not a
    checkout, handed to the identification directly): `unknown`, `git-failed`,
    never a generation."""
    plain = tmp_path / "plain"
    plain.mkdir()
    assert startup_checks.identify_generation(str(plain), "data", "a" * 40) == Identification(None, "git-failed")


def test_a_ref_not_in_the_table_is_not_generation_zero(tmp_path):
    """`5e1eeac` carries the check only in the operator diagnostic: unknown,
    `fingerprint-not-in-table`. A synthetic ref whose only reference to a check
    function is in a file other than the startup modules is unknown too."""
    _require_history()
    for plane in startup_checks.PLANES:
        assert startup_checks.identify_generation(str(_REPO_ROOT), plane, _full("5e1eeac")) == Identification(
            None, "fingerprint-not-in-table")
    repository, commit = _make_repository(tmp_path / "repo", _synthetic_files(**{
        "ops.py": "def diagnostic(platform_declarations):\n    platform_declarations.check_role_connection_limits()\n",
    }))
    assert startup_checks.identify_generation(repository, "data", commit) == Identification(
        None, "fingerprint-not-in-table")


def test_a_ref_without_the_startup_module_is_unknown(tmp_path):
    """`785b23e` has no control startup module: control is unknown with
    `startup-module-missing` (its data startup module exists)."""
    _require_history()
    assert startup_checks.identify_generation(str(_REPO_ROOT), "control", _full("785b23e")) == Identification(
        None, "startup-module-missing")
    assert startup_checks.identify_generation(str(_REPO_ROOT), "data", _full("785b23e")) == Identification("G0", None)


def test_an_unparseable_source_file_makes_the_ref_unknown(tmp_path):
    """A `.py` under the source tree that does not parse: `source-unparseable`
    (the startup module exists and nothing references a check)."""
    repository, commit = _make_repository(tmp_path / "repo", _synthetic_files(**{"broken.py": "def (:\n"}))
    assert startup_checks.identify_generation(repository, "data", commit) == Identification(None, "source-unparseable")
    intact, intact_commit = _make_repository(tmp_path / "intact", _synthetic_files())
    assert startup_checks.identify_generation(intact, "data", intact_commit) == Identification("G0", None)


def test_a_ref_without_platform_declarations_is_generation_zero():
    """`448c660` predates the platform declarations file: still G0 (`present:
    false` for both checks), the file's absence does not matter."""
    _require_history()
    ref = _full("448c660")
    assert subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "cat-file", "-e", f"{ref}:{_PACKAGE_DIR}platform_declarations.py"],
        capture_output=True).returncode != 0
    for plane in startup_checks.PLANES:
        assert startup_checks.identify_generation(str(_REPO_ROOT), plane, ref) == Identification("G0", None)
    entry = _evaluate(_revision("data"), "G0", _facts())
    assert entry["f16"] == {"present": False, "judgment": "confirmed", "reason": "check-not-in-generation"}
    assert entry["f18"] == entry["f16"] and entry["pool_input"] is None


def test_generation_zero_counts_names_in_the_syntax_tree_not_substrings():
    """`c387b32` is G0 although its sources contain `F-16` inside another word
    (`UTF-16`): the constants are compared for equality, references are counted
    in the syntax tree."""
    _require_history()
    ref = _full("c387b32")
    assert _git(_REPO_ROOT, "grep", "-c", "F-16", ref, "--", "MitateDB-api/src").strip(), "the fixture no longer holds"
    for plane in startup_checks.PLANES:
        assert startup_checks.identify_generation(str(_REPO_ROOT), plane, ref) == Identification("G0", None)


def test_a_renamed_check_that_raises_the_code_label_is_not_generation_zero(tmp_path):
    """A synthetic ref with both startup modules and a platform declarations
    file whose renamed function raises `code="F-16"`: not G0 (a string
    constant equal to a code label), unknown, `fingerprint-not-in-table`."""
    files = _synthetic_files(**{
        "platform_declarations.py": (
            "class PlatformDeclarationError(RuntimeError):\n    pass\n\n\n"
            "def renamed_role_limit_check():\n    raise PlatformDeclarationError('x', code=\"F-16\")\n"),
    })
    repository, commit = _make_repository(tmp_path / "repo", files)
    for plane in startup_checks.PLANES:
        assert startup_checks.identify_generation(repository, plane, commit) == Identification(
            None, "fingerprint-not-in-table")


def test_the_known_table_has_one_row_per_plane_and_fingerprint():
    """Data has 13 rows (G1 7, G2 4, G3 2), control 12 (G1 6, G2 4, G3 2), and no
    fingerprint is in the table twice. The last G3 row of each plane is the one
    the working tree carries (`_current_row`); the G3 rows after the first have no
    representative ref yet."""
    rows = startup_checks.KNOWN_FINGERPRINTS
    counts = {}
    for row in rows:
        counts[(row.plane, row.generation)] = counts.get((row.plane, row.generation), 0) + 1
    assert counts == {("data", "G1"): 7, ("data", "G2"): 4, ("data", "G3"): 2,
                      ("control", "G1"): 6, ("control", "G2"): 4, ("control", "G3"): 2}
    assert len({(row.plane, row.fingerprint) for row in rows}) == len(rows)


# ===========================================================================
# Input rejections, exit codes, and the output.
# ===========================================================================


def _assert_rejected(run: _Run, rule: str) -> None:
    """Exit 1, empty stdout, one fixed stderr line naming the rule word (never
    the value), no database connection."""
    assert run.rc == 1, (run.rc, run.err)
    assert run.out == "" and run.err.strip() == f"error: startup-checks input rejected ({rule})", (run.out, run.err)
    assert run.connects == []


def test_a_gap_in_the_kind_coverage_is_rejected(monkeypatch, capsys, platform, tmp_path):
    """`data.other` is neither listed nor declared absent: exit 1."""
    document = _document(declared_absent=["data.env_only_revision", "control.env_only_revision", "control.other"])
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, document), "coverage-gap")


def test_control_and_its_items_declared_absent_together_are_rejected(monkeypatch, capsys, platform, tmp_path):
    """`control` next to `control.*` in `declared_absent`: exit 1 (and a
    `control` declaration next to a control revision: exit 1)."""
    document = _document(
        declared_absent=["data.env_only_revision", "data.other", "control", "control.other"],
        revisions=[_rev_json("data-a", "data", _ZERO_REF, ["serving", "rollback_target", "candidate"])])
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, document), "control-declared-absent-with-items")
    with_revision = _document(declared_absent=["data.env_only_revision", "data.other", "control"])
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, with_revision),
                     "control-declared-absent-with-revisions")


def test_an_empty_revision_list_is_rejected(monkeypatch, capsys, platform, tmp_path):
    """An empty `revisions` list is rejected with its own rule word (the
    coverage rule would reject the same input under another word)."""
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, _document(revisions=[])), "empty-revisions")


def test_a_data_candidate_is_required_and_cannot_be_declared_absent(monkeypatch, capsys, platform, tmp_path):
    """`data.candidate` declared absent while a data candidate is listed: exit 1
    (it is not in the `declared_absent` vocabulary); no data revision of kind
    `candidate`: exit 1."""
    without = _document(revisions=[
        _rev_json("data-a", "data", _ZERO_REF, ["serving", "rollback_target"]),
        _rev_json("control-a", "control", _ZERO_REF, ["serving", "rollback_target", "candidate"])])
    absent = ["data.env_only_revision", "data.other", "data.candidate", "control.env_only_revision", "control.other"]
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, _document(declared_absent=absent)), "unknown-value")
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path,
                          _document(declared_absent=absent, revisions=without["revisions"])), "unknown-value")
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, without), "data-candidate-missing")


def test_a_missing_env_key_is_rejected(monkeypatch, capsys, platform, tmp_path):
    """An `env` without `MITATEDB_THREAD_LIMIT` (absent, not `null`): exit 1."""
    document = _document()
    del document["revisions"][0]["env"]["MITATEDB_THREAD_LIMIT"]
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, document), "env-keys")


def test_a_rejected_input_never_opens_a_database_connection(monkeypatch, capsys, platform, tmp_path):
    """A wrong `format`: exit 1, nothing on stdout, and not one call to
    `psycopg.connect`."""
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(format="other/1"))
    _assert_rejected(run, "format")


def _duplicate_names() -> dict:
    document = _document()
    document["revisions"][1]["name"] = document["revisions"][0]["name"]
    return document


def _reject_cases() -> list:
    base = _document

    def with_revision(**changes):
        document = base()
        document["revisions"][0].update(changes)
        return document

    def without_key(key):
        document = base()
        del document["revisions"][0][key]
        return document

    def with_env(**env):
        document = base()
        document["revisions"][0]["env"].update(env)
        return document

    control_only = base()
    control_only["revisions"][1]["audit_dsn_configured"] = "yes"
    no_audit = base()
    del no_audit["revisions"][1]["audit_dsn_configured"]
    data_audit = base()
    data_audit["revisions"][0]["audit_dsn_configured"] = True
    extra_env = base()
    extra_env["revisions"][0]["env"]["OTHER"] = "1"
    no_control = base(
        declared_absent=["data.env_only_revision", "data.other", "control.serving", "control.rollback_target",
                         "control.env_only_revision", "control.candidate", "control.other"],
        revisions=[base()["revisions"][0]])
    return [
        ("not-json", "{not json", "not-json"),
        ("top-level-not-an-object", "[]", "format"),
        ("unknown-top-level-key", base(extra=1), "unknown-key"),
        ("unknown-revision-key", with_revision(extra=1), "unknown-key"),
        ("missing-revision-key", without_key("kinds"), "missing-key"),
        ("unknown-env-key", extra_env, "env-keys"),
        ("source-ref-uppercase", with_revision(source_ref="A" * 40), "source-ref"),
        ("source-ref-short", with_revision(source_ref="a" * 39), "source-ref"),
        ("duplicate-name", _duplicate_names(), "duplicate-name"),
        ("unknown-plane", with_revision(plane="edge"), "unknown-value"),
        ("unknown-kind", with_revision(kinds=["serving", "bogus"]), "unknown-value"),
        ("empty-kinds", with_revision(kinds=[]), "kinds"),
        ("duplicate-kinds", with_revision(kinds=["serving", "serving"]), "kinds"),
        ("unknown-declared-absent", base(declared_absent=["data.other", "data.bogus"]), "unknown-value"),
        ("env-value-not-a-string", with_env(MITATEDB_THREAD_LIMIT=4), "env-value"),
        ("audit-dsn-not-a-bool", control_only, "audit-dsn-type"),
        ("control-without-audit-flag", no_audit, "missing-key"),
        ("data-with-audit-flag", data_audit, "audit-dsn-on-data"),
        ("listed-and-declared-absent",
         base(declared_absent=["data.env_only_revision", "data.other", "data.serving",
                               "control.env_only_revision", "control.other"]), "coverage-conflict"),
        ("control-revisions-missing", no_control, "control-revisions-missing"),
    ]


@pytest.mark.parametrize("case", _reject_cases(), ids=lambda case: case[0])
def test_the_remaining_rejections_exit_1_before_any_connection(monkeypatch, capsys, platform, tmp_path, case):
    """Every other rejected shape of the revisions file: exit 1, empty stdout,
    one fixed stderr line, no database connection."""
    _assert_rejected(_run(monkeypatch, capsys, platform, tmp_path, case[1]), case[2])


def test_a_proposed_ceiling_that_is_not_a_positive_integer_exits_1(monkeypatch, capsys, platform, tmp_path):
    for value in (0, -2):
        run = _run(monkeypatch, capsys, platform, tmp_path, _document(), data=value)
        assert run.rc == 1 and run.out == "" and run.connects == []


def test_an_unreadable_revisions_file_exits_1(monkeypatch, capsys, platform, tmp_path):
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    with pytest.raises(SystemExit) as raised:
        ops.main(["startup-checks", "--data", "1", "--control", "1", "--revisions", str(tmp_path / "absent.json"),
                  "--repository", str(_REPO_ROOT)])
    assert raised.value.code == 1
    assert capsys.readouterr().out == ""


def test_a_repository_that_is_not_a_git_checkout_exits_1(monkeypatch, capsys, platform, tmp_path):
    """`--repository` pointing at a directory that is not a git checkout: exit
    1, nothing on stdout, one fixed stderr line."""
    directory = tmp_path / "plain"
    directory.mkdir()
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(), repository=directory)
    assert run.rc == 1 and run.out == "" and run.err.strip() == "error: startup-checks could not run"
    assert run.connects == []


def test_a_missing_required_argument_is_a_usage_error_with_exit_1(monkeypatch, capsys, platform):
    """`--repository` omitted: argparse's usage error exits 1, not 2 (2 is a
    produced judgment that is not confirmed), before any connection."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    with pytest.raises(SystemExit) as raised:
        ops.main(["startup-checks", "--data", "1", "--control", "1", "--revisions", "unused.json"])
    assert raised.value.code == 1
    assert capsys.readouterr().out == ""


def test_an_unrecognised_argument_exits_1(monkeypatch, capsys, platform, tmp_path):
    """An argument the subcommand does not define: exit 1 (as for `inventory`),
    before any connection, nothing on stdout."""
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(), extra=["--bogus"])
    assert run.rc == 1 and run.out == "" and run.connects == []
    assert "unrecognized arguments" in run.err


def test_a_report_with_an_unknown_revision_exits_2_and_is_unknown_overall(monkeypatch, capsys, platform, tmp_path):
    """One revision whose ref does not exist, the others confirmed: `overall`
    `unknown`, exit 2 (a produced judgment that is not confirmed)."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    document = _document(data_ref=_ref_of("G3"), control_ref="1" * 40)
    run = _run(monkeypatch, capsys, platform, tmp_path, document, data=1, control=1)
    assert run.rc == 2 and run.report["overall"] == "unknown"
    control = next(entry for entry in run.report["revisions"] if entry["name"] == "control-a")
    assert control["generation"] is None and control["reason"] == "ref-not-found"
    assert control["f16"] == {"present": None, "judgment": "unknown", "reason": "generation-unknown"}
    assert control["f18"] == control["f16"]
    data = next(entry for entry in run.report["revisions"] if entry["name"] == "data-a")
    assert data["f16"]["judgment"] == "confirmed" and data["f18"]["judgment"] == "confirmed"


def test_all_confirmed_exits_0(monkeypatch, capsys, platform, tmp_path):
    """Every revision confirmed: `overall` `confirmed`, exit 0."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    document = _document(data_ref=_ref_of("G3"), control_ref=_ref_of("G3"))
    run = _run(monkeypatch, capsys, platform, tmp_path, document, data=1, control=1)
    assert run.rc == 0 and run.report["overall"] == "confirmed", run.report


def test_the_connection_is_read_only_and_a_failed_read_back_exits_1(monkeypatch, capsys, platform, tmp_path):
    """The reads run in a session whose `transaction_read_only` reads `on`; a
    session that does not read back as `on` ends the run with exit 1, a fixed
    stderr line and nothing on stdout."""
    observed: list = []
    original = startup_checks.read_database_facts

    def observing(conn, **kwargs):
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            observed.append(cur.fetchone()[0])
        return original(conn, **kwargs)

    monkeypatch.setattr(startup_checks, "read_database_facts", observing)
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(data_ref=_ref_of("G3"), control_ref=_ref_of("G3")))
    assert observed == ["on"] and run.report is not None
    monkeypatch.setattr(ops, "_inventory_confirmed_read_only", lambda conn: False)
    failed = _run(monkeypatch, capsys, platform, tmp_path, _document(data_ref=_ref_of("G3"), control_ref=_ref_of("G3")))
    assert failed.rc == 1 and failed.out == "" and failed.err.strip() == "error: startup-checks could not run"


def test_the_report_names_the_checks_and_nine_known_gaps_in_the_documented_order(monkeypatch, capsys, platform, tmp_path):
    """The report's key set, `checks_evaluated`, the coverage map and the nine
    `known_gaps` identifiers, which are the docstring's Known gaps in order."""
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    run = _run(monkeypatch, capsys, platform, tmp_path, _document(data_ref=_ref_of("G2"), control_ref=_ref_of("G3")),
               data=1, control=1)
    report = run.report
    assert set(report) == {"overall", "checks_evaluated", "declaration", "database", "coverage", "known_gaps", "revisions"}
    assert report["checks_evaluated"] == ["F-16", "F-18"]
    assert len(report["known_gaps"]) == 9
    documented = re.findall(r"^\s+\d+\.\s+``([a-z0-9-]+)``", startup_checks.__doc__, flags=re.M)
    assert report["known_gaps"] == documented
    assert report["declaration"] == {"current": {"control": 1, "data": 1}, "proposed": {"control": 1, "data": 1}}
    assert set(report["database"]) == {
        "max_connections", "registered_applications", "reserved_connections", "superuser_reserved_connections"}
    assert report["coverage"] == {
        "control": "listed", "control.candidate": "listed", "control.env_only_revision": "declared-absent",
        "control.other": "declared-absent", "control.rollback_target": "listed", "control.serving": "listed",
        "data.candidate": "listed", "data.env_only_revision": "declared-absent", "data.other": "declared-absent",
        "data.rollback_target": "listed", "data.serving": "listed"}
    data = next(entry for entry in report["revisions"] if entry["name"] == "data-a")
    assert set(data) == {"name", "plane", "generation", "reason", "pool_input", "f16", "f18"}
    assert data["generation"] == "G2" and data["pool_input"]["x"] == 32
    assert set(data["f16"]) == {"present", "judgment", "reason", "window_judgment", "current_judgment", "roles"}
    assert set(data["f18"]) == {"present", "judgment", "reason", "registered_applications_judged", "lower_bound",
                                "lower_bound_without_registrations", "reserved_total", "required", "max_connections"}
    assert run.out.count("\n") == 1 and list(report) == sorted(report)


def test_a_control_plane_declared_absent_is_reported_as_plane_declared_absent(monkeypatch, capsys, platform, tmp_path):
    """`control` in `declared_absent`: the control items are `plane-declared-absent`
    and no control revision is judged."""
    document = _document(data_ref=_ref_of("G3"),
                         declared_absent=["data.env_only_revision", "data.other", "control"],
                         revisions=[_rev_json("data-a", "data", _ref_of("G3"), ["serving", "rollback_target", "candidate"])])
    _set_limits(platform, api=132, controlplane=36, auditreader=12)
    run = _run(monkeypatch, capsys, platform, tmp_path, document, data=1, control=1)
    assert run.rc == 0
    assert run.report["coverage"]["control"] == "declared-absent"
    assert all(run.report["coverage"][f"control.{kind}"] == "plane-declared-absent"
               for kind in ("serving", "rollback_target", "env_only_revision", "candidate", "other"))
    assert [entry["name"] for entry in run.report["revisions"]] == ["data-a"]
