"""`ops inventory` -- the DB-layer half of Mitate Gate-0 (design docs/design/
MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md). Own file, own fixtures
(duplicated bootstrap shape from `tests/test_ops_verify_declarations.py`/
`tests/test_platform_migration_reapply.py`, not imported -- this
repository's own precedent of not taking cross-test-module import
dependencies).

Covers: item judgments (1)/(2)/(3)/(4)/(6, runtime-settings half)/(8), the
`unjudged_items` list for item (5) and item (6)'s declared half, the closed
output vocabulary and top-level JSON shape, the read-only/timeout session
discipline every connection carries (platform AND application
connections), the single-factory connection pattern, the four-sentinel
non-disclosure discipline, the positive-integer CLI argument discipline,
and the roadmap R-47 per-application `InsufficientPrivilege` handling.
"""
from __future__ import annotations

import json
import secrets
import subprocess
import tempfile
import types
import unittest.mock
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Json

import mitatedb_api.ops as ops
from mitatedb_api import platform_declarations, platform_upgrades

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
_REPO_ROOT = Path(__file__).resolve().parents[2]

_DATA_URL = "https://ops-inventory-test.example.invalid/v1"

#: The commit that first granted the provision role's own `GRANT USAGE ON
#: SCHEMA public` in `0003_provision_application.sql` (roadmap R-47, WP-C's
#: own starting-point exclusion set). Fetched from the parent of this
#: commit to get the LAST version of `0003` that predates the grant.
_PRE_R47_FIX_COMMIT = "b87d1c85"


def _admin_dsn() -> str:
    import os

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


def _require_admin_connection() -> None:
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_ops_inventory.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)


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


def _repo_relpath(path: Path) -> str:
    return str(path.relative_to(_REPO_ROOT))


def _historical_0003(commit: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{_repo_relpath(MIGRATIONS_DIR / '0003_provision_application.sql')}"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not read historical 0003 as of {commit}: {result.stderr}")
    return result.stdout


def _bootstrap(prefix: str) -> types.SimpleNamespace:
    admin_dsn = _admin_dsn()
    provision_role = f"{prefix}svc_provision"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = Path(tempfile.mkdtemp(prefix="mitatedb_ops_inventory_"))
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
        "0005_application_audit.sql", "0012_role_connection_limits.sql",
        "0007_platform_declarations.sql", "0011_process_ceilings.sql",
        "0003_provision_application.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out
    historical_0003_text = _historical_0003(f"{_PRE_R47_FIX_COMMIT}~1").replace("mitatedb", prefix)
    historical_0003_path = rewritten_dir / "0003_historical_pre_r47.sql"
    historical_0003_path.write_text(historical_0003_text)
    rewritten["0003_historical_pre_r47.sql"] = historical_0003_path

    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
    _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
    _run_psql(
        provision_dsn, rewritten["0007_platform_declarations.sql"],
        {"api_role": api_role, "controlplane_role": controlplane_role},
    )
    _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])

    return types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, provision_role=provision_role,
        provision_password=provision_password, api_role=api_role, controlplane_role=controlplane_role,
        platform_db=platform_db, schema=schema,
        provision_script=rewritten["0003_provision_application.sql"],
        historical_provision_script=rewritten["0003_historical_pre_r47.sql"],
    )


@pytest.fixture()
def platform() -> Iterator[types.SimpleNamespace]:
    """A fresh, throwaway platform through 0001/0002/0005/0012/0007/0011 --
    one per test, never shared (several tests mutate CONNECTION LIMITs and
    hold locks)."""
    _require_admin_connection()
    prefix = f"r45wpbinv{secrets.token_hex(4)}"
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


def _declare_golden_path(monkeypatch: pytest.MonkeyPatch, platform: types.SimpleNamespace, *, data: int = 1, control: int = 1) -> None:
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    assert ops.main(["declare-surfaces", "--data-base-url", _DATA_URL, "--no-control"]) == 0
    assert ops.main(["declare-process-ceilings", "--data", str(data), "--control", str(control)]) == 0


def _declare_role_lock_timeouts(platform: types.SimpleNamespace) -> None:
    """`0007` declares only `statement_timeout`/`idle_in_transaction_
    session_timeout` on the two writer roles -- `lock_timeout` is never
    part of that migration, and NEITHER timeout is ever declared on
    `mitatedbsvc_auditreader` (created by `0005`). Tests that need item
    (6)'s runtime-settings half to read `confirmed` add both here,
    mirroring an operator's own `ALTER ROLE ... SET lock_timeout`/`SET
    statement_timeout` run after 0007 -- covering the SAME full role set
    item (8) discovers (api/controlplane/auditreader)."""
    auditreader_role = f"{platform.prefix}svc_auditreader"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for role in (platform.api_role, platform.controlplane_role, auditreader_role):
                cur.execute(sql.SQL("ALTER ROLE {} SET lock_timeout = '3000ms'").format(sql.Identifier(role)))
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(role)))
    finally:
        admin.close()


def _provision_app(platform: types.SimpleNamespace, app_id: str, *, script: "Path | None" = None) -> str:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.provision_dsn, script or platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    return f"{platform.prefix}_app_{app_id}"


def _run_inventory(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], platform: types.SimpleNamespace, **cli_kwargs) -> tuple:
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    argv = ["inventory"]
    for flag, value in cli_kwargs.items():
        if value is None:
            continue
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    rc = ops.main(argv)
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    report = json.loads(lines[-1]) if lines else None
    return rc, report, captured.out, captured.err


#: `reserved_connections=0` (supervisor ruling unlike the other
#: three numeric arguments, `--reserved-connections` accepts 0 -- "no
#: reserve" is a genuine value, not a usage error).
_HEADROOM_OK = dict(concurrency=2, data_process_count=1, control_process_count=1, reserved_connections=0)


def _headroom_args(**overrides) -> types.SimpleNamespace:
    values = dict(_HEADROOM_OK)
    values.update(overrides)
    return types.SimpleNamespace(**values)


# ===========================================================================
# Row 1 / 2 / 2a / W2-1 / W2-2 / 10c: overall shape
# ===========================================================================


def test_inventory_reports_every_db_layer_item_with_a_judgment(monkeypatch, capsys, platform):
    """(1) 1+ observation for every DB-layer item."""
    _declare_golden_path(monkeypatch, platform)
    rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report is not None, f"expected JSON on stdout, got out={out!r} err={err!r}"
    for key in ops._INVENTORY_TOP_LEVEL_KEYS:
        assert key in report, f"missing item {key!r} in {report!r}"
    assert rc in (0, 2)


def test_inventory_exit_code_is_0_when_every_judged_item_is_confirmed(monkeypatch, capsys, platform):
    """2a's own positive half: with `lock_timeout`
    declared on both writer roles (item (6)'s own runtime-settings input)
    and a matching connection name (item (1)), every judged item is
    confirmed and the exit code is exactly 0."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    host = conninfo_to_dict(platform.provision_dsn)["host"]
    connection_name = Path(host).name
    rc, report, out, err = _run_inventory(
        monkeypatch, capsys, platform, cloud_sql_connection_name=connection_name, **_HEADROOM_OK)
    assert report is not None, f"out={out!r} err={err!r}"
    assert report["connection"]["comparison"] == "match"
    assert report["ddl_lock"]["judgment"] == "confirmed"
    assert rc == 0


def test_inventory_never_reports_an_overall_ready_key(monkeypatch, capsys, platform):
    """2."""
    _declare_golden_path(monkeypatch, platform)
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert "ready" not in report


def test_inventory_top_level_and_item_keys_are_pinned(monkeypatch, capsys, platform):
    """W2-1 (revised, supervisor ruling): item
    (5) has no key at all; item (6)'s own key covers only its
    runtime-settings half; `unjudged_items` names the item DB layer never
    judges."""
    _declare_golden_path(monkeypatch, platform)
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert set(report.keys()) == ops._INVENTORY_TOP_LEVEL_KEYS
    assert set(report["connection"].keys()) == {"comparison", "judgment"}
    assert set(report["declarations"].keys()) == {"judgment", "remediation_required", "reason"}
    assert set(report["migrations"].keys()) == {"judgment", "remediation_required", "reason", "registered_only_count"}
    assert set(report["credentials"].keys()) == {
        "judgment", "remediation_required", "total_count", "enabled_count", "revoked_count", "must_rotate_count",
    }
    assert set(report["ddl_lock"].keys()) == {"judgment", "remediation_required"}
    assert set(report["connection_headroom"].keys()) == {"judgment", "remediation_required"}
    assert report["unjudged_items"] == [
        {"item": 5, "part": "all", "reason": "runbook-acceptance"},
        {"item": 6, "part": "lock-and-downtime", "reason": "runbook-acceptance"},
    ]
    assert {entry["part"] for entry in report["unjudged_items"]} <= ops._INVENTORY_UNJUDGED_PARTS


def test_inventory_judgment_vocabulary_is_closed(monkeypatch, capsys, platform):
    """W2-2: every judgment word observed across a
    confirmed run and an all-unknown run stays inside the closed
    vocabulary."""
    _declare_golden_path(monkeypatch, platform)
    _rc, confirmed_report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    _rc2, empty_report, _out2, _err2 = _run_inventory(monkeypatch, capsys, platform)
    seen_judgments = set()
    seen_comparisons = set()
    for report in (confirmed_report, empty_report):
        for key, item in report.items():
            if key == "unjudged_items":
                continue
            if key == "connection":
                seen_comparisons.add(item["comparison"])
            seen_judgments.add(item["judgment"])
    assert seen_judgments <= ops._INVENTORY_JUDGMENTS
    assert seen_comparisons <= ops._INVENTORY_COMPARISONS
    assert "unknown" in seen_judgments  # non-vacuous: the empty run has real unknowns


def test_inventory_reason_vocabulary_is_pinned():
    """the closed set of fixed reason
    words a `blocked` judgment may carry."""
    assert ops._INVENTORY_REASONS == frozenset({"ledger-unreadable", "declaration-invalid"})


def test_inventory_unjudged_parts_vocabulary_is_pinned():
    """the closed set of fixed `part` words an
    `unjudged_items` entry may carry."""
    assert ops._INVENTORY_UNJUDGED_PARTS == frozenset({"all", "lock-and-downtime"})


def test_inventory_exit_code_is_2_when_any_item_is_not_confirmed(monkeypatch, capsys, platform):
    """2a and W4-1: with no `lock_timeout` declared
    on either writer role, item (6) is naturally `unknown` even with item
    (1) forced to `match` -- the exit code must be exactly 2 (not 0, not
    1)."""
    _declare_golden_path(monkeypatch, platform)
    host = conninfo_to_dict(platform.provision_dsn)["host"]
    connection_name = Path(host).name
    rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, cloud_sql_connection_name=connection_name, **_HEADROOM_OK)
    assert report["connection"]["comparison"] == "match"
    assert report["ddl_lock"]["judgment"] == "unknown"
    assert rc == 2


def test_inventory_connection_judgment_drives_the_exit_code(monkeypatch, capsys, platform):
    """Item (1)'s own `judgment` (mapped from
    `comparison`) is read by `_inventory_exit_code` exactly like every
    other item's -- a `mismatch` or `unknown` comparison alone is enough
    to make the exit code 2, even with every other item confirmed."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["connection"] == {"comparison": "unknown", "judgment": "unknown"}
    assert rc == 2
    rc2, report2, _out2, _err2 = _run_inventory(
        monkeypatch, capsys, platform, cloud_sql_connection_name="not-the-real-socket-name", **_HEADROOM_OK)
    assert report2["connection"] == {"comparison": "mismatch", "judgment": "blocked"}
    assert rc2 == 2


def test_inventory_tool_failure_exit_code_is_1_with_fixed_text_only(monkeypatch, capsys, platform):
    """W4-2."""
    monkeypatch.delenv("MITATEDB_PROVISION_DSN", raising=False)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err.strip() == ops._INVENTORY_TOOL_FAILURE_MESSAGE


def test_inventory_tool_failure_when_read_only_cannot_be_confirmed(monkeypatch, capsys, platform):
    """`cmd_inventory`'s own use
    of `_inventory_confirmed_read_only` is exercised for real -- forcing
    it to report False must make the WHOLE subcommand fail closed (exit
    1, fixed text), not silently proceed to build a report anyway."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    monkeypatch.setattr(ops, "_inventory_confirmed_read_only", lambda conn: False)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err.strip() == ops._INVENTORY_TOOL_FAILURE_MESSAGE


def test_inventory_writes_nothing_but_stdout(monkeypatch, capsys, platform, tmp_path):
    """10c."""
    _declare_golden_path(monkeypatch, platform)
    monkeypatch.chdir(tmp_path)
    _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert list(tmp_path.iterdir()) == []


def test_inventory_does_not_accept_a_dsn_argument(monkeypatch, capsys, platform):
    """20 (static): the `inventory` subparser's own
    argument set never includes anything DSN-shaped."""
    parser = ops._build_parser()
    subparsers_action = next(a for a in parser._subparsers._group_actions if a.dest == "command")
    inventory_parser = subparsers_action.choices["inventory"]
    dests = {action.dest for action in inventory_parser._actions}
    assert dests == {
        "help", "cloud_sql_connection_name", "concurrency",
        "data_process_count", "control_process_count", "reserved_connections",
    }


def test_inventory_numeric_arguments_reject_zero_and_negative(capsys):
    """`--concurrency`/`--data-process-count`/
    `--control-process-count` accept only a positive integer (0 refused
    too -- `--reserved-connections`'s own 0-vs-negative behavior is's own separate test below)."""
    parser = ops._build_parser()
    for flag in ("--concurrency", "--data-process-count", "--control-process-count"):
        for bad_value in ("0", "-1", "not-a-number"):
            with pytest.raises(SystemExit) as excinfo:
                parser.parse_args(["inventory", flag, bad_value])
            assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "positive integer" in captured.err
    # a valid positive value is still accepted
    ns = parser.parse_args(["inventory", "--concurrency", "3"])
    assert ns.concurrency == 3


def test_inventory_reserved_connections_accepts_zero_but_rejects_negative(capsys):
    """unlike the other three numeric
    arguments, `--reserved-connections` accepts `0` ("no reserve") -- only
    a negative value (or non-integer text) is a usage error."""
    parser = ops._build_parser()
    ns = parser.parse_args(["inventory", "--reserved-connections", "0"])
    assert ns.reserved_connections == 0
    for bad_value in ("-1", "not-a-number"):
        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["inventory", "--reserved-connections", bad_value])
        assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "non-negative integer" in captured.err


def test_inventory_never_calls_psycopg_connect_outside_its_own_factory():
    """27b (static)."""
    import inspect

    factory_source = inspect.getsource(ops._inventory_connect)
    other_sources = "".join(
        inspect.getsource(fn) for fn in (
            ops.cmd_inventory, ops._inventory_connection_match, ops._inventory_declarations,
            ops._inventory_migrations, ops._inventory_select_credential_rows, ops._inventory_credentials,
            ops._inventory_role_classes, ops._inventory_ddl_lock_declaration,
            ops._inventory_connection_headroom, ops._inventory_exit_code,
        )
    )
    assert "psycopg.connect(" in factory_source
    assert "psycopg.connect(" not in other_sources


def test_inventory_connect_closes_the_connection_when_a_set_statement_fails(monkeypatch, platform):
    """`_inventory_connect` must not
    leak a connection when one of its own `SET` statements fails."""
    real_connect = psycopg.connect
    opened = []

    def _spy_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(psycopg, "connect", _spy_connect)
    original_execute = psycopg.Cursor.execute
    call_count = {"n": 0}

    def _failing_execute(self, query, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise psycopg.errors.OperationalError("boom")
        return original_execute(self, query, *args, **kwargs)

    with unittest.mock.patch.object(psycopg.Cursor, "execute", _failing_execute):
        with pytest.raises(psycopg.errors.OperationalError):
            ops._inventory_connect(platform.provision_dsn)
    assert opened, "psycopg.connect was never called"
    assert opened[-1].closed


# ===========================================================================
# Item (1): rows 8a, 8b, 8c
# ===========================================================================


def test_inventory_connection_comparison_reports_a_mismatch():
    """8a."""
    dsn = "host=/var/run/fakesocket dbname=x user=y password=z"
    assert ops._inventory_connection_match(dsn, "some-other-connection-name") == {"comparison": "mismatch", "judgment": "blocked"}


def test_inventory_connection_comparison_matches_the_real_socket_path():
    """8a (the `match` half)."""
    dsn = "host=/var/run/fakesocket dbname=x user=y password=z"
    assert ops._inventory_connection_match(dsn, "fakesocket") == {"comparison": "match", "judgment": "confirmed"}


def test_inventory_connection_comparison_tcp_dsn_is_unknown():
    """8b."""
    dsn = "host=127.0.0.1 dbname=x user=y password=z"
    assert ops._inventory_connection_match(dsn, "some-connection-name") == {"comparison": "unknown", "judgment": "unknown"}


def test_inventory_connection_output_never_includes_the_socket_path_or_name():
    """8c."""
    dsn = "host=/var/run/fakesocket dbname=x user=y password=z"
    result = ops._inventory_connection_match(dsn, "fakesocket")
    assert set(result.keys()) == {"comparison", "judgment"}
    assert "fakesocket" not in json.dumps(result)


# ===========================================================================
# C1: sentinels (rows 10a, 10b, 11, 11a, 11b, 12, 13, 14; row 15 is an
# audit note, see the report). 11/11a/11b/12's first stage
# also asserts the exact fixed text (never merely "some text without the
# sentinel").
# ===========================================================================


def test_inventory_success_route_never_leaks_user_or_password(monkeypatch, capsys, platform):
    """(10a) the DSN's own
    `user` sentinel must be a value that can actually appear in the DSN
    `_inventory_connect` opens -- a REAL login role, granted the
    provision role's own membership (so it inherits the same privileges
    and a real inventory run can complete), name-and-password both
    sentinel-bearing. Both the success route (correct password) and the
    connect-failure route (wrong password, a real `password authentication
    failed`) are exercised through the SAME sentinel role."""
    user_sentinel_role = f"usersentinelxyz{secrets.token_hex(4)}"
    password_sentinel = f"passsentinelxyz{secrets.token_hex(4)}"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} CONNECTION LIMIT 5 IN ROLE {}").format(
                    sql.Identifier(user_sentinel_role), sql.Literal(password_sentinel), sql.Identifier(platform.provision_role)
                )
            )
    finally:
        admin.close()
    try:
        success_dsn = _dsn_with(
            platform.admin_dsn, user=user_sentinel_role, password=password_sentinel, dbname=platform.platform_db,
        )
        monkeypatch.setenv("MITATEDB_PROVISION_DSN", success_dsn)
        monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
        rc = ops.main(["inventory"])
        captured = capsys.readouterr()
        assert rc in (0, 2), f"success route did not run: out={captured.out!r} err={captured.err!r}"
        assert user_sentinel_role not in captured.out and user_sentinel_role not in captured.err
        assert password_sentinel not in captured.out and password_sentinel not in captured.err

        failure_dsn = _dsn_with(
            platform.admin_dsn, user=user_sentinel_role, password=f"{password_sentinel}-wrong", dbname=platform.platform_db,
        )
        with pytest.raises(psycopg.Error) as excinfo:
            psycopg.connect(failure_dsn, connect_timeout=2)
        assert user_sentinel_role in str(excinfo.value)  # confirms the route really carries the sentinel
        monkeypatch.setenv("MITATEDB_PROVISION_DSN", failure_dsn)
        rc2 = ops.main(["inventory"])
        captured2 = capsys.readouterr()
        assert rc2 == 1
        assert user_sentinel_role not in captured2.out and user_sentinel_role not in captured2.err
        assert password_sentinel not in captured2.out and password_sentinel not in captured2.err
    finally:
        admin2 = psycopg.connect(platform.admin_dsn, autocommit=True)
        try:
            with admin2.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(user_sentinel_role)))
        finally:
            admin2.close()


def test_inventory_success_route_never_leaks_dbname(monkeypatch, capsys, platform):
    """(10b) item (1) never emits the connection
    target at all (row 8c), so the dbname sentinel (embedded in the
    platform db's own name via the fixture prefix) never appears anywhere
    in the output, including outside the identify field."""
    dbname_sentinel = platform.platform_db.upper()
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc in (0, 2)
    assert dbname_sentinel.lower() not in captured.out.lower()
    assert dbname_sentinel.lower() not in captured.err.lower()


def _probe_connect_failure(bad_dsn: str, sentinel: str) -> type:
    """returns the real exception TYPE the bad DSN raises, after
    confirming (stage 1 of D-2's 3-step discipline) the route is really
    taken and the sentinel really appears in the raw exception text."""
    with pytest.raises(psycopg.Error) as excinfo:
        psycopg.connect(bad_dsn, connect_timeout=2)
    assert sentinel in str(excinfo.value)
    return type(excinfo.value)


def test_inventory_connect_failure_host_never_leaks(monkeypatch, capsys, platform):
    """11."""
    host_sentinel = "hostsentinelxyz.invalid"
    bad_dsn = _dsn_with(platform.provision_dsn, host=host_sentinel, hostaddr="")
    exc_type = _probe_connect_failure(bad_dsn, host_sentinel)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", bad_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip() == f"error: database operation failed ({exc_type.__name__})"
    assert host_sentinel not in captured.out and host_sentinel not in captured.err


def test_inventory_connect_failure_role_never_leaks(monkeypatch, capsys, platform):
    """11a."""
    role_sentinel = "rolesentinelxyz"
    bad_dsn = _dsn_with(platform.provision_dsn, user=role_sentinel, password="whatever")
    exc_type = _probe_connect_failure(bad_dsn, role_sentinel)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", bad_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip() == f"error: database operation failed ({exc_type.__name__})"
    assert role_sentinel not in captured.out and role_sentinel not in captured.err


def test_inventory_connect_failure_database_never_leaks(monkeypatch, capsys, platform):
    """11b."""
    dbname_sentinel = "dbsentinelxyz"
    bad_dsn = _dsn_with(platform.provision_dsn, dbname=dbname_sentinel)
    exc_type = _probe_connect_failure(bad_dsn, dbname_sentinel)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", bad_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip() == f"error: database operation failed ({exc_type.__name__})"
    assert dbname_sentinel not in captured.out and dbname_sentinel not in captured.err


def test_inventory_dsn_parse_failure_never_leaks(monkeypatch, capsys, platform):
    """(12) an unescaped `%` in a URI-form DSN's own
    password fails conninfo parsing before any connection attempt."""
    password_sentinel = "passsentinelxyz"
    bad_dsn = f"postgresql://user:{password_sentinel}%@127.0.0.1:1/db"
    with pytest.raises(psycopg.Error) as excinfo:
        conninfo_to_dict(bad_dsn)
    assert password_sentinel in str(excinfo.value)
    exc_type = type(excinfo.value)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", bad_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip() == f"error: database operation failed ({exc_type.__name__})"
    assert password_sentinel not in captured.out and password_sentinel not in captured.err


def test_inventory_post_connect_psycopg_exception_never_leaks(monkeypatch, capsys, platform):
    """13 (also exercises completion condition 6:
    a non-`UndefinedTable` `psycopg.Error` from `read_applied_upgrade_
    numbers` leaves item (3) unknown, never a crash)."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    exception_sentinel = "CURSOREXECSENTINELXYZ"

    def _boom(conn, *, ledger_table_name):
        raise psycopg.errors.OperationalError(exception_sentinel)

    monkeypatch.setattr(platform_upgrades, "read_applied_upgrade_numbers", _boom)
    rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert exception_sentinel not in out and exception_sentinel not in err
    assert report["migrations"]["judgment"] == "unknown"


def test_inventory_non_psycopg_exception_is_caught_at_the_top_level_without_a_traceback(monkeypatch, capsys, platform):
    """(14) `cmd_inventory` never adds its own broad
    exception handler that would print `str(exc)` -- an unexpected
    non-psycopg exception from any item reaches `main`'s own existing
    top-level handler (type name and fixed text only)."""
    exception_sentinel = "NONPSYCOPGSENTINELXYZ"

    def _boom(conn, schema):
        raise ValueError(exception_sentinel)

    monkeypatch.setattr(ops, "_inventory_declarations", _boom)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    rc = ops.main(["inventory"])
    captured = capsys.readouterr()
    assert rc == 1
    assert exception_sentinel not in captured.out and exception_sentinel not in captured.err
    assert "ValueError" in captured.err


# ===========================================================================
# Item (2): declarations
# ===========================================================================


def test_inventory_declarations_missing_row_is_confirmed_with_remediation(monkeypatch, capsys, platform):
    """`declare-surfaces`/`declare-process-
    ceilings` never run yet (F-3/F-15 missing-row) is a known, recoverable
    gap -- confirmed + remediation_required, never blocked."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["declarations"] == {"judgment": "confirmed", "remediation_required": True, "reason": None}


def test_inventory_declarations_shape_violation_is_blocked(monkeypatch, capsys, platform):
    """an existing but hand-corrupted
    declaration row (F-15's own shape-violation case) is `blocked` with
    the fixed reason `declaration-invalid`, never treated as absent."""
    _declare_golden_path(monkeypatch, platform)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET value = %s WHERE key = 'process_ceilings'").format(
                    sql.Identifier(platform.schema, "platform_declarations")
                ),
                [Json({"data": "not-a-number", "control": 1})],
            )
    finally:
        conn.close()
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["declarations"] == {"judgment": "blocked", "remediation_required": False, "reason": "declaration-invalid"}


def test_inventory_declarations_connection_failure_is_unknown(platform):
    """(fail-closed baseline, C3)."""

    class _FailingCursorConn:
        def cursor(self):
            raise psycopg.errors.OperationalError("boom")

    report = ops._inventory_declarations(_FailingCursorConn(), platform.schema)
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


# ===========================================================================
# Item (3): rows 4, 5, 6 (see above), 7, and (R-47)
# ===========================================================================


def test_inventory_migrations_unapplied_ledger_is_confirmed_with_remediation(monkeypatch, capsys, platform):
    """(4) a per-application upgrade number the
    ledger does not record yet is confirmed + remediation_required,
    never blocked."""
    _declare_golden_path(monkeypatch, platform)
    database_name = _provision_app(platform, "app1")
    conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=database_name), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._mdb_platform_upgrades WHERE upgrade_number = 8")
    finally:
        conn.close()
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["migrations"]["judgment"] == "confirmed"
    assert report["migrations"]["remediation_required"] is True


def test_inventory_migrations_connection_failure_is_unknown(monkeypatch, capsys, platform):
    """5."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET database_name = %s WHERE application_id = %s").format(
                    sql.Identifier(platform.schema, "applications")
                ),
                [f"{platform.prefix}_does_not_exist", "app1"],
            )
    finally:
        conn.close()
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["migrations"]["judgment"] == "unknown"


def test_inventory_migrations_registered_only_application_is_counted(monkeypatch, capsys, platform):
    """7."""
    _declare_golden_path(monkeypatch, platform)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {} (application_id) VALUES (%s)").format(
                    sql.Identifier(platform.schema, "applications")
                ),
                ["registeredonly"],
            )
    finally:
        conn.close()
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["migrations"]["registered_only_count"] == 1
    assert report["migrations"]["judgment"] == "confirmed"


def test_inventory_migrations_r47_pre_fix_application_is_blocked_with_a_fixed_reason(monkeypatch, capsys, platform):
    """an application
    provisioned with the historical, pre-`b87d1c85` `0003` (no `GRANT
    USAGE ON SCHEMA public` to the provision role) and no `0008` applied
    is reported `blocked` with reason `ledger-unreadable` -- the raw
    `InsufficientPrivilege` text never appears, and every OTHER item is
    still reported (`inventory` does not crash)."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "legacyapp", script=platform.historical_provision_script)
    rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report is not None, f"inventory crashed instead of reporting: out={out!r} err={err!r}"
    assert report["migrations"]["judgment"] == "blocked"
    assert report["migrations"]["reason"] == "ledger-unreadable"
    assert "InsufficientPrivilege" not in out and "InsufficientPrivilege" not in err
    assert "public" not in out.lower()
    assert rc == 2
    # every other item still ran (the one bad application did not crash the tool)
    assert report["credentials"]["judgment"] == "confirmed"


# ===========================================================================
# Item (4): rows 22, 23, 23a, and (per-state counts)
# ===========================================================================


def test_inventory_credentials_never_output_credential_id_or_digest(monkeypatch, capsys, platform):
    """s 22 and 23: a real credential row (with a
    sentinel-bearing id and a distinctive digest) is present, but neither
    the id nor the digest bytes appear anywhere in the output."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    credential_id_sentinel = "credidsentinelxyz"
    digest_sentinel = b"DIGESTSENTINELBYTESXYZ"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {} (credential_id, application_id, role, digest) VALUES (%s, %s, 'runtime', %s)").format(
                    sql.Identifier(platform.schema, "credentials")
                ),
                [credential_id_sentinel, "app1", digest_sentinel],
            )
    finally:
        conn.close()
    rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert credential_id_sentinel not in out and credential_id_sentinel not in err
    assert digest_sentinel.decode() not in out and digest_sentinel.decode() not in err
    assert report["credentials"]["judgment"] == "confirmed"
    assert report["credentials"]["total_count"] >= 1


def test_inventory_credentials_per_state_counts(monkeypatch, capsys, platform):
    """(4) reports counts per state (`enabled`/
    `revoked`/`must_rotate`), not merely a total."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {} (credential_id, application_id, role, digest, enabled, revoked) VALUES "
                    "('cred-enabled', 'app1', 'runtime', 'x', TRUE, FALSE), "
                    "('cred-revoked', 'app1', 'developer', 'x', FALSE, TRUE)"
                ).format(sql.Identifier(platform.schema, "credentials"))
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {} (credential_id, digest, role, must_rotate) VALUES "
                    "('ctrl-cred-1', 'x', 'control', TRUE)"
                ).format(sql.Identifier(platform.schema, "control_credentials"))
            )
    finally:
        conn.close()
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    credentials = report["credentials"]
    assert credentials["total_count"] == 3
    assert credentials["enabled_count"] == 2  # cred-enabled + ctrl-cred-1's own default `enabled=TRUE`
    assert credentials["revoked_count"] == 1
    assert credentials["must_rotate_count"] == 1


def test_inventory_credentials_column_allowlist_excludes_secrets():
    """22 (static)."""
    assert "credential_id" not in ops._INVENTORY_CREDENTIAL_COLUMNS
    assert "digest" not in ops._INVENTORY_CREDENTIAL_COLUMNS
    assert "credential_id" not in ops._INVENTORY_CONTROL_CREDENTIAL_COLUMNS
    assert "digest" not in ops._INVENTORY_CONTROL_CREDENTIAL_COLUMNS


def test_inventory_credentials_cursor_description_matches_the_allowlist(platform):
    """`cursor.description`'s own column names
    (not merely the query text) match the allow-list exactly -- a single
    secret column returned by the driver, however it got there, is red."""
    captured_descriptions = []
    original_execute = psycopg.Cursor.execute

    def _capturing_execute(self, query, *args, **kwargs):
        result = original_execute(self, query, *args, **kwargs)
        text = query.as_string(self) if hasattr(query, "as_string") else str(query)
        if "credentials" in text.lower() and self.description is not None:
            captured_descriptions.append(tuple(d.name for d in self.description))
        return result

    with unittest.mock.patch.object(psycopg.Cursor, "execute", _capturing_execute):
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            ops._inventory_credentials(conn, platform.schema)
        finally:
            conn.close()
    assert captured_descriptions, "no credentials query observed"
    allowlist = set(ops._INVENTORY_CREDENTIAL_COLUMNS) | set(ops._INVENTORY_CONTROL_CREDENTIAL_COLUMNS)
    for names in captured_descriptions:
        assert set(names) <= allowlist, names
        assert "credential_id" not in names
        assert "digest" not in names


def test_inventory_credentials_query_never_selects_star_or_secret_columns(platform):
    """s 22 and 23: the actual SQL text `inventory`
    sends for item (4) never contains `*`, `credential_id`, or `digest` --
    proof at the query level too, not merely `cursor.description`."""
    captured_queries = []
    original_execute = psycopg.Cursor.execute

    def _capturing_execute(self, query, *args, **kwargs):
        captured_queries.append(query.as_string(self) if hasattr(query, "as_string") else str(query))
        return original_execute(self, query, *args, **kwargs)

    with unittest.mock.patch.object(psycopg.Cursor, "execute", _capturing_execute):
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            ops._inventory_credentials(conn, platform.schema)
        finally:
            conn.close()
    credential_queries = [q for q in captured_queries if "credentials" in q.lower()]
    assert credential_queries, captured_queries
    for query in credential_queries:
        assert "*" not in query, query
        assert "credential_id" not in query, query
        assert "digest" not in query, query


def test_inventory_credentials_permission_error_is_unknown(monkeypatch, capsys, platform):
    """23a."""
    reader_role = f"{platform.prefix}svc_noreader"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'x' CONNECTION LIMIT 5").format(sql.Identifier(reader_role)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(platform.platform_db), sql.Identifier(reader_role)))
    finally:
        admin.close()
    reader_dsn = _dsn_with(platform.admin_dsn, user=reader_role, password="x", dbname=platform.platform_db)
    conn = psycopg.connect(reader_dsn, autocommit=True)
    try:
        report = ops._inventory_credentials(conn, platform.schema)
    finally:
        conn.close()
    assert report["judgment"] == "unknown"


# ===========================================================================
# Item (6), runtime-settings half only; item
# (5) has no output at all (see the `unjudged_items` pin test above)
# ===========================================================================


def test_inventory_ddl_lock_is_unknown_when_lock_timeout_not_declared(platform):
    """37 (revised,): `0007` never declares
    `lock_timeout` on either writer role -- unknown by default."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_ddl_lock_is_confirmed_when_role_settings_are_declared(platform):
    """37 (revised,): once BOTH `lock_timeout`
    and `statement_timeout` are declared (and each target role's
    `CONNECTION LIMIT` is set, already true from `0012`), item (6)'s
    runtime-settings half reads confirmed."""
    _declare_role_lock_timeouts(platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "confirmed", "remediation_required": False}


def test_inventory_ddl_lock_target_roles_include_auditreader(platform):
    """Item (6)'s target roles are the SAME
    full set item (8) discovers (api/controlplane/auditreader) -- with
    `lock_timeout`/`statement_timeout` declared on api/controlplane ONLY
    (never on `mitatedbsvc_auditreader`), the item stays unknown."""
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for role in (platform.api_role, platform.controlplane_role):
                cur.execute(sql.SQL("ALTER ROLE {} SET lock_timeout = '3000ms'").format(sql.Identifier(role)))
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


# ===========================================================================
# C2: read-only discipline (rows 25a, 25b, 25c, 27a, 27c) and W4-3/W4-4
# ===========================================================================


def test_inventory_connections_reject_writes_outside_an_explicit_transaction(platform):
    """25a (platform connection)."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {} (application_id) VALUES ('shouldnotwrite')").format(
                        sql.Identifier(platform.schema, "applications")
                    )
                )
    finally:
        conn.close()


def test_inventory_application_connections_also_reject_writes(monkeypatch, platform):
    """Item (3)'s own per-
    application connections (opened deep INSIDE `_inventory_migrations`,
    never directly by a test) are read-only too -- checked immediately
    BEFORE `_inventory_migrations` itself calls `read_applied_upgrade_
    numbers` on that connection, which is exactly where a regression
    scoped to that one call site (not `_inventory_connect` in general)
    would have already disabled it."""
    _provision_app(platform, "app1")
    original_read = platform_upgrades.read_applied_upgrade_numbers
    checked = {"count": 0}

    def _checking_read(conn, *, ledger_table_name):
        # The ledger table itself is owned by the application's own
        # developer role (0003's own header: "CURRENT_USER is the
        # developer role (this table's own owner)"); the provision role
        # only ever gets `SELECT` on it, so a DELETE there would fail on
        # plain permissions regardless of read-only. `CREATE SCHEMA`
        # instead exercises a right the provision role genuinely has (it
        # owns the whole database, `0001`'s own `CREATE DATABASE ...
        # OWNER`), blocked ONLY by the read-only transaction setting.
        checked["count"] += 1
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA readonly_probe")
        return original_read(conn, ledger_table_name=ledger_table_name)

    monkeypatch.setattr(platform_upgrades, "read_applied_upgrade_numbers", _checking_read)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        ops._inventory_migrations(conn, platform.provision_dsn, platform.schema)
    finally:
        conn.close()
    assert checked["count"] >= 1, "no application connection was opened to check"


def test_inventory_confirms_read_only_by_reading_it_back(platform):
    """(25b) the confirmation genuinely reads the
    setting rather than trusting that `_inventory_connect` already set
    it -- a connection where read-only was never set reads back False."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        assert ops._inventory_confirmed_read_only(conn) is False
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
        assert ops._inventory_confirmed_read_only(conn) is True
    finally:
        conn.close()


def test_inventory_ledger_absent_read_only_survives_the_internal_rollback(platform):
    """(25c) `read_applied_upgrade_numbers`'s own
    `UndefinedTable` recovery calls `conn.rollback()` -- the connection's
    read-only setting (and by extension the two session timeouts) must
    still hold afterward."""
    database_name = f"{platform.prefix}_app_noledger"
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database_name), sql.Identifier(platform.provision_role)))
    finally:
        admin.close()
    app_dsn = _dsn_with(platform.provision_dsn, dbname=database_name)
    conn = ops._inventory_connect(app_dsn)
    try:
        applied = platform_upgrades.read_applied_upgrade_numbers(conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
        assert applied is None
        assert ops._inventory_confirmed_read_only(conn) is True
    finally:
        conn.close()


def test_inventory_all_opened_connections_go_through_the_factory(monkeypatch, capsys, platform):
    """27a."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    _provision_app(platform, "app2")
    real_connect = psycopg.connect
    factory_calls = {"count": 0}
    raw_calls = {"count": 0}
    original_factory = ops._inventory_connect

    def _counting_factory(dsn):
        factory_calls["count"] += 1
        return original_factory(dsn)

    def _counting_connect(*args, **kwargs):
        raw_calls["count"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(ops, "_inventory_connect", _counting_factory)
    monkeypatch.setattr(psycopg, "connect", _counting_connect)
    _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert factory_calls["count"] > 0
    assert raw_calls["count"] == factory_calls["count"]


def test_inventory_session_timeouts_are_actually_set(platform):
    """27c."""
    from mitatedb_api.pg_timeouts import ms_from_pg_timeout_text

    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW lock_timeout")
            (lock_timeout,) = cur.fetchone()
            cur.execute("SHOW statement_timeout")
            (statement_timeout,) = cur.fetchone()
    finally:
        conn.close()
    assert ms_from_pg_timeout_text(lock_timeout) == ops._INVENTORY_LOCK_TIMEOUT_MS
    assert ms_from_pg_timeout_text(statement_timeout) == ops._INVENTORY_STATEMENT_TIMEOUT_MS


def test_inventory_session_timeout_constants_are_pinned():
    """W4-3."""
    assert ops._INVENTORY_LOCK_TIMEOUT_MS == 3000
    assert ops._INVENTORY_STATEMENT_TIMEOUT_MS == 5000


def test_inventory_credentials_lock_timeout_exceeded_is_unknown(monkeypatch, capsys, platform):
    """W4-4 (exercised through the real CLI, so
    an unexpected failure gracefully exits 1 via `main`'s own top-level
    handler if this item's own catch were ever removed -- never a raw,
    uncaught exception surfacing as a pytest error)."""
    _declare_golden_path(monkeypatch, platform)
    holder = psycopg.connect(platform.provision_dsn, autocommit=False)
    try:
        with holder.cursor() as cur:
            cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(platform.schema, "credentials")))
        rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    finally:
        holder.rollback()
        holder.close()
    assert report is not None, f"out={out!r} err={err!r}"
    assert report["credentials"]["judgment"] == "unknown"
    assert rc == 2


# ===========================================================================
# Item (8): connection headroom (rows 29a, 29b, 30, 31a, 32, 32a, 33a, 33b,
# 34, 34a, 34b, 34c, 35, 35a, 35b, 35c)
# ===========================================================================


def test_inventory_connection_headroom_concurrency_missing_is_unknown(monkeypatch, platform):
    """29b."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(concurrency=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_process_count_missing_is_unknown(platform):
    """31a."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(data_process_count=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_reserved_connections_missing_is_unknown(monkeypatch, platform):
    """35b."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(reserved_connections=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_max_connections_unreadable_is_unknown(monkeypatch, capsys, platform):
    """30 (exercised through the real CLI, so a
    regression that stops catching this failure gracefully exits 1 via
    `main`'s own top-level handler -- the test then fails cleanly on the
    wrong exit code/judgment, never as an uncaught exception inside the
    test body itself)."""
    _declare_golden_path(monkeypatch, platform)
    original_execute = psycopg.Cursor.execute

    def _failing_execute(self, query, *args, **kwargs):
        text = query.as_string(self) if hasattr(query, "as_string") else str(query)
        if "max_connections" in text:
            raise psycopg.errors.OperationalError("max_connections unreadable")
        return original_execute(self, query, *args, **kwargs)

    with unittest.mock.patch.object(psycopg.Cursor, "execute", _failing_execute):
        rc, report, out, err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report is not None, f"out={out!r} err={err!r}"
    assert report["connection_headroom"]["judgment"] == "unknown"
    assert rc == 2


def test_inventory_connection_headroom_minus_one_connection_limit_is_unknown(platform):
    """32."""
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.api_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_minus_one_on_an_unrelated_role_is_not_unknown(monkeypatch, platform):
    """32a."""
    _declare_golden_path(monkeypatch, platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.provision_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_data_process_count_overflow_is_blocked(monkeypatch, capsys, platform):
    """s 33a (all-revision process count, not just
    one) and 34 (condition 1's own role-vs-limit comparison)."""
    _declare_golden_path(monkeypatch, platform, data=20, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(data_process_count=20, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_declared_and_actual_process_counts_disagree_is_blocked(monkeypatch, platform):
    """33b."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(data_process_count=2, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_control_process_count_mismatch_is_blocked(monkeypatch, platform):
    """(33b) the
    CONTROL side of the declared-vs-actual comparison is checked
    independently of the DATA side. Declares `control=2` but PASSES
    `control_process_count=1` (matching data on both sides, and keeping
    the ACTUAL controlplane demand well under its CONNECTION LIMIT so
    condition 1 alone could never explain a `blocked` result) -- isolates
    the mismatch check itself."""
    _declare_golden_path(monkeypatch, platform, data=1, control=2)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(data_process_count=1, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_role_coefficient_is_two_times_concurrency_for_api(monkeypatch, platform):
    """34a."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(concurrency=35, data_process_count=1, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_shared_application_role_budget_counts_once(monkeypatch, platform):
    """34b."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _provision_app(platform, "app1")
    _provision_app(platform, "app2")
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)
    concurrency = 2
    api_demand = 2 * concurrency
    controlplane_demand = 16
    auditreader_demand = 4
    correct_total = api_demand + controlplane_demand + auditreader_demand + concurrency + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
    reserved = max_connections - correct_total
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(concurrency=concurrency, data_process_count=1, control_process_count=1, reserved_connections=reserved),
        )
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_app_role_condition1_uses_concurrency_not_one(monkeypatch, platform):
    """Condition 1's own app-role
    threshold is `concurrency`, never a hardcoded `1` -- an app role whose
    `CONNECTION LIMIT` sits strictly between `1` and `concurrency` must
    still be `blocked`."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _provision_app(platform, "app1")
    platform_conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with platform_conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")
                )
            )
            (runtime_role,) = cur.fetchone()
    finally:
        platform_conn.close()
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 1").format(sql.Identifier(runtime_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(concurrency=2, data_process_count=1, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_demand_scales_with_data_process_count(monkeypatch, platform):
    """Condition 1's own
    app-role threshold is `data_process_count * concurrency`, never
    `concurrency` alone -- isolated from the platform-plane roles' own
    checks by keeping THEIR demand well under their real `CONNECTION
    LIMIT` (68/20/5) while only the app role's own (lowered) limit is
    exceeded."""
    _declare_golden_path(monkeypatch, platform, data=3, control=1)
    database_name = _provision_app(platform, "app1")
    platform_conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with platform_conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")
                )
            )
            (runtime_role,) = cur.fetchone()
    finally:
        platform_conn.close()
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 4").format(sql.Identifier(runtime_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(concurrency=2, data_process_count=3, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_overflow_with_named_values(monkeypatch, platform):
    """data_process_count=2, concurrency=32, against the default `0003`
    app-role `CONNECTION LIMIT` of 36 -- blocked."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    _provision_app(platform, "app1")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(concurrency=32, data_process_count=2, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_application_connections_confirm_read_only(monkeypatch, platform):
    """: `_inventory_migrations`
    itself calls `_inventory_confirmed_read_only` on each application
    connection -- forcing it to report False for THAT call site makes the
    application unknown, never silently read anyway."""
    _provision_app(platform, "app1")
    original_confirmed = ops._inventory_confirmed_read_only
    calls = {"count": 0}

    def _spy_confirmed(conn):
        calls["count"] += 1
        return original_confirmed(conn)

    monkeypatch.setattr(ops, "_inventory_confirmed_read_only", _spy_confirmed)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        ops._inventory_migrations(conn, platform.provision_dsn, platform.schema)
    finally:
        conn.close()
    assert calls["count"] >= 1  # one provisioned application -> at least one app connection


def test_inventory_connection_headroom_declaration_missing_is_unknown_with_remediation(monkeypatch, platform):
    """`declare-process-ceilings` never run
    (F-15 missing-row, surfaces already declared) leaves item (8) unknown
    WITH remediation_required, never silently confirmed."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    assert ops.main(["declare-surfaces", "--data-base-url", _DATA_URL, "--no-control"]) == 0
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": True}


def test_inventory_connection_headroom_declaration_connection_failure_is_unknown(monkeypatch, platform):
    """a genuine
    `psycopg.Error` while reading the declaration (not missing, not
    malformed -- e.g. a transient connection failure) leaves item (8)
    unknown, never silently confirmed."""
    _declare_golden_path(monkeypatch, platform)

    def _boom(conn, *, schema, ops_module, migration):
        raise psycopg.errors.OperationalError("boom")

    monkeypatch.setattr(platform_declarations, "read_platform_declarations", _boom)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_declaration_shape_violation_is_blocked(monkeypatch, platform):
    """a hand-corrupted `process_ceilings` row
    is blocked, never silently skipped into a confirmed headroom
    computation."""
    _declare_golden_path(monkeypatch, platform)
    conn_write = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn_write.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET value = %s WHERE key = 'process_ceilings'").format(
                    sql.Identifier(platform.schema, "platform_declarations")
                ),
                [Json({"data": "not-a-number", "control": 1})],
            )
    finally:
        conn_write.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False}


def test_inventory_declarations_f15_missing_only_is_confirmed_with_remediation(monkeypatch, platform):
    """Item (2) with
    `surfaces` declared but `process_ceilings` never declared (F-15's own
    missing-row case, in isolation from F-3/F-4/F-8) is confirmed +
    remediation_required, never blocked."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", platform.schema)
    assert ops.main(["declare-surfaces", "--data-base-url", _DATA_URL, "--no-control"]) == 0
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_declarations(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "confirmed", "remediation_required": True, "reason": None}


def test_inventory_ddl_lock_ignores_a_per_database_scoped_setting(platform):
    """A `lock_timeout`/
    `statement_timeout` pair declared only for ONE specific database
    (`setdatabase != 0`) does not count as the role's own database-
    independent declaration -- stays unknown."""
    _declare_role_lock_timeouts(platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} RESET lock_timeout").format(
                    sql.Identifier(platform.api_role), sql.Identifier(platform.platform_db)
                )
            )
            cur.execute(
                sql.SQL("ALTER ROLE {} RESET lock_timeout").format(sql.Identifier(platform.api_role))
            )
            cur.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET lock_timeout = '3000ms'").format(
                    sql.Identifier(platform.api_role), sql.Identifier(platform.platform_db)
                )
            )
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_ddl_lock_target_roles_include_application_roles(monkeypatch, platform):
    """Item (6)'s target roles include every
    provisioned application's own `runtime_role`/`developer_role`, the
    SAME full set item (8) discovers -- lacking the declaration there
    (never declared on ANY role by any migration) leaves item (6)
    unknown even when every platform-plane role has it."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    _provision_app(platform, "app1")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_ddl_lock_minus_one_connection_limit_is_unknown(platform):
    """`CONNECTION LIMIT` is confirmed up to
    its actual value -- `-1` (unlimited) is unknown, not merely "present"."""
    _declare_role_lock_timeouts(platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.api_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False}


def test_inventory_connection_headroom_auditreader_counted_under_control_only(monkeypatch, platform):
    """34c."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(concurrency=2, data_process_count=2, control_process_count=1))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def _function_source_from_file(path: Path, function_name: str) -> str:
    import ast as _ast

    text = path.read_text(encoding="utf-8")
    tree = _ast.parse(text)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == function_name:
            return _ast.get_source_segment(text, node)
    raise AssertionError(f"{function_name} not found in {path}")


def test_only_control_composition_pools_a_connection_against_mitatedbsvc_auditreader():
    """`mitatedb_api.main.
    build_app` never pools a connection against `mitatedbsvc_auditreader`
    -- only `mitatedb_api.control_composition.build_control_service`
    does, and only when `MITATEDB_AUDIT_DSN` is configured. Fixed by
    reading the two functions' own source text directly from disk
    (neither module is imported live -- `main.py` builds a real ASGI app
    at import time, which needs a full set of env vars this test has no
    business supplying) -- guards against a future change quietly making
    the Data-plane process pool one too."""
    src_dir = Path(ops.__file__).resolve().parent
    control_source = _function_source_from_file(src_dir / "control_composition.py", "build_control_service")
    data_source = _function_source_from_file(src_dir / "main.py", "build_app")
    assert '_own_role_classes.add("auditreader")' in control_source
    assert 'role_classes=frozenset({"api"})' in data_source
    assert '_own_role_classes.add("auditreader")' not in data_source
    assert 'role_classes=frozenset({"api", "auditreader"})' not in data_source


def test_inventory_connection_headroom_max_concurrent_connections_constant_is_pinned():
    """35."""
    assert ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS == 2


def test_inventory_connection_headroom_aggregate_overflow_is_blocked(monkeypatch, platform):
    """35a."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(reserved_connections=int(max_connections_text)))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_spy_measured_concurrency_stays_at_or_below_the_constant(monkeypatch, capsys, platform):
    """35c."""
    _declare_golden_path(monkeypatch, platform)
    _provision_app(platform, "app1")
    _provision_app(platform, "app2")
    real_connect = psycopg.connect
    open_count = {"current": 0, "max": 0}

    class _TrackedConn:
        def __init__(self, real):
            self._real = real
            open_count["current"] += 1
            open_count["max"] = max(open_count["max"], open_count["current"])

        def __getattr__(self, name):
            return getattr(self._real, name)

        def close(self):
            if not self._real.closed:
                open_count["current"] -= 1
            self._real.close()

    def _tracking_connect(*args, **kwargs):
        return _TrackedConn(real_connect(*args, **kwargs))

    monkeypatch.setattr(psycopg, "connect", _tracking_connect)
    _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert open_count["max"] <= ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
