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
import os
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
from mitatedb_api import config, platform_declarations, platform_upgrades

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


def _bootstrap(prefix: str, *, apply_0013: bool = True) -> types.SimpleNamespace:
    """`apply_0013=False` stops right after `0012` -- used by the one test
    that observes `apply-platform-migration` itself turning item (6) from
    `unknown` into `confirmed`. Every other caller applies 0013
    unconditionally, like 0012, since 0013 depends only on 0005/0012.
    0014 is only copied into the rewritten temp dir here; it is not
    applied -- each test that needs 0014 applies it itself."""
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
        "0013_role_statement_timeouts.sql", "0014_role_connection_limits_rollout.sql",
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
    if apply_0013:
        _run_psql(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])
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
        migrations_dir=rewritten_dir,
    )


@pytest.fixture()
def platform() -> Iterator[types.SimpleNamespace]:
    """A fresh, throwaway platform through 0001/0002/0005/0012/0007/0011/
    0013 -- one per test, never shared (several tests mutate CONNECTION
    LIMITs and hold locks)."""
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
    part of that migration, and 0013's own default bootstrap declares
    only `statement_timeout` on `mitatedbsvc_auditreader` (never
    `lock_timeout`). Tests that need item (6)'s runtime-settings half to
    read `confirmed` add both here,
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


def _reset_role_statement_timeout(admin_dsn: str, role: str) -> None:
    """Undoes a role-level `statement_timeout` declaration -- used to put
    a role back into the undeclared state 0013 no longer leaves it in by
    default (0013 sets this on `mitatedbsvc_auditreader` and every
    provisioned application's own runtime/developer role
    unconditionally)."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(role)))
    finally:
        admin.close()


def _set_role_statement_timeout(admin_dsn: str, role: str, value: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                sql.Identifier(role), sql.SQL(value)))
    finally:
        admin.close()


def _set_connection_limit(admin_dsn: str, role: str, limit: int) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT {}").format(sql.Identifier(role), sql.Literal(limit)))
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
        if value is None or value is False:
            continue
        flag_name = f"--{flag.replace('_', '-')}"
        if value is True:
            argv.append(flag_name)
        else:
            argv += [flag_name, str(value)]
    rc = ops.main(argv)
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    report = json.loads(lines[-1]) if lines else None
    return rc, report, captured.out, captured.err


#: `reserved_connections=0` (supervisor ruling unlike the other
#: numeric arguments, `--reserved-connections` accepts 0 -- "no
#: reserve" is a genuine value, not a usage error). Ceiling and total
#: are the SAME value here (no mid-migration revision overlap in
#: these golden-path tests), and Control is declared deployed
#: (`control_not_deployed=False`, omitted from argv). All 1 Data-plane
#: process is on the NEW basis (`data_process_count_old_basis=0`) --
#: `--data-process-count-old-basis` at 0 means `--concurrency` must be
#: omitted (`_inventory_validate_headroom_inputs`), so `concurrency` is
#: `None` here; `thread_limit` (`DEFAULT_THREAD_LIMIT`) sizes the one
#: new-basis process instead.
_HEADROOM_OK = dict(
    concurrency=None, thread_limit=ops.DEFAULT_THREAD_LIMIT, data_process_count_old_basis=0,
    data_process_ceiling=1, data_process_count_total=1,
    control_process_ceiling=1, control_process_count_total=1,
    control_not_deployed=False, reserved_connections=0,
)


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
    assert set(report["ddl_lock"].keys()) == {"judgment", "remediation_required", "reason"}
    assert set(report["connection_headroom"].keys()) == {"judgment", "remediation_required", "control_deployed"}
    assert report["unjudged_items"] == [
        {"item": 5, "part": "all", "reason": "runbook-acceptance"},
        {"item": 6, "part": "lock-and-downtime", "reason": "runbook-acceptance"},
    ]
    assert {entry["part"] for entry in report["unjudged_items"]} <= ops._INVENTORY_UNJUDGED_PARTS


def test_inventory_judgment_vocabulary_is_closed(monkeypatch, capsys, platform):
    """Every judgment word observed across a confirmed run, an
    all-unknown run, and a `--control-not-deployed` run stays inside the
    closed vocabulary."""
    _declare_golden_path(monkeypatch, platform)
    _rc, confirmed_report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    _rc2, empty_report, _out2, _err2 = _run_inventory(monkeypatch, capsys, platform)
    not_deployed_kwargs = dict(_HEADROOM_OK)
    not_deployed_kwargs.update(control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None)
    _rc3, not_deployed_report, _out3, _err3 = _run_inventory(monkeypatch, capsys, platform, **not_deployed_kwargs)
    seen_judgments = set()
    seen_comparisons = set()
    for report in (confirmed_report, empty_report, not_deployed_report):
        for key, item in report.items():
            if key == "unjudged_items":
                continue
            if key == "connection":
                seen_comparisons.add(item["comparison"])
            seen_judgments.add(item["judgment"])
    assert seen_judgments <= ops._INVENTORY_JUDGMENTS
    assert seen_comparisons <= ops._INVENTORY_COMPARISONS
    assert "unknown" in seen_judgments  # non-vacuous: the empty run has real unknowns
    assert not_deployed_report["connection_headroom"]["control_deployed"] is False


def test_inventory_reason_vocabulary_is_pinned():
    """the closed set of fixed reason
    words a `blocked` judgment may carry."""
    assert ops._INVENTORY_REASONS == frozenset(
        {"ledger-unreadable", "declaration-invalid", "statement-timeout-unbounded"})


def test_inventory_unjudged_parts_vocabulary_is_pinned():
    """the closed set of fixed `part` words an
    `unjudged_items` entry may carry."""
    assert ops._INVENTORY_UNJUDGED_PARTS == frozenset({"all", "lock-and-downtime"})


def test_inventory_exit_code_is_2_when_any_item_is_not_confirmed(monkeypatch, capsys, platform):
    """2a and W4-1: with `mitatedbsvc_auditreader`'s own
    `statement_timeout` (declared by 0013's default bootstrap) reset away,
    item (6) is `unknown` even with item (1) forced to `match` -- the exit
    code must be exactly 2 (not 0, not 1)."""
    _declare_golden_path(monkeypatch, platform)
    _reset_role_statement_timeout(platform.admin_dsn, f"{platform.prefix}svc_auditreader")
    host = conninfo_to_dict(platform.provision_dsn)["host"]
    connection_name = Path(host).name
    rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, cloud_sql_connection_name=connection_name, **_HEADROOM_OK)
    assert report["connection"]["comparison"] == "match"
    assert report["ddl_lock"]["judgment"] == "unknown"
    assert rc == 2


def test_inventory_exit_code_is_2_when_ddl_lock_is_blocked(monkeypatch, capsys, platform):
    """A blocked item (6) exits 2, the same as any other
    non-confirmed judgment -- never 1, which `cmd_inventory` reserves for
    a failure before any item judgment exists at all."""
    _declare_role_lock_timeouts(platform)
    _set_role_statement_timeout(platform.admin_dsn, f"{platform.prefix}svc_auditreader", "0")
    rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **_HEADROOM_OK)
    assert report["ddl_lock"]["judgment"] == "blocked"
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
        "data_process_ceiling", "data_process_count_total",
        "control_process_ceiling", "control_process_count_total", "control_not_deployed",
        "reserved_connections", "thread_limit", "data_process_count_old_basis",
    }


def test_inventory_numeric_arguments_reject_zero_and_negative(capsys):
    """`--concurrency`/`--data-process-ceiling`/
    `--data-process-count-total`/`--control-process-ceiling`/`--control-
    process-count-total`/`--thread-limit` accept only a positive integer
    (0 refused too -- `--reserved-connections`'s/`--data-process-count-
    old-basis`'s own 0-vs-negative behavior has its own separate test
    below). `inventory`'s own subparser remaps this usage error's exit
    code to 1, never argparse's default 2 (which this subcommand
    reserves for a completed item judgment)."""
    parser = ops._build_parser()
    for flag in (
        "--concurrency", "--data-process-ceiling", "--data-process-count-total",
        "--control-process-ceiling", "--control-process-count-total", "--thread-limit",
    ):
        for bad_value in ("0", "-1", "not-a-number"):
            with pytest.raises(SystemExit) as excinfo:
                parser.parse_args(["inventory", flag, bad_value])
            assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "positive integer" in captured.err
    # a valid positive value is still accepted
    ns = parser.parse_args(["inventory", "--concurrency", "3"])
    assert ns.concurrency == 3


def test_inventory_unrecognized_argument_is_rejected_with_exit_code_1(monkeypatch, capsys):
    """`inventory`'s own unrecognized-arguments/
    extra-positional-arguments case exits 1 like every other `inventory`
    usage error (never argparse's default 2, which this subcommand
    reserves for a completed item judgment) -- no database connection is
    attempted (`MITATEDB_PROVISION_DSN` is left unset) and the rejected
    value is never echoed."""
    monkeypatch.delenv("MITATEDB_PROVISION_DSN", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        ops.main(["inventory", "--no-such-flag"])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "no-such-flag" not in captured.err


def test_other_subcommand_unrecognized_argument_still_exits_2(capsys):
    """Only `inventory` remaps the unrecognized-
    arguments case to exit 1 -- every other subcommand keeps argparse's
    own default (exit 2)."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main(["list-applications", "--no-such-flag"])
    assert excinfo.value.code == 2


def test_inventory_reserved_connections_accepts_zero_but_rejects_negative(capsys):
    """unlike the other numeric
    arguments, `--reserved-connections` accepts `0` ("no reserve") -- only
    a negative value (or non-integer text) is a usage error -- exit
    code 1, not argparse's default 2 (`inventory`'s own `p.error`
    override)."""
    parser = ops._build_parser()
    ns = parser.parse_args(["inventory", "--reserved-connections", "0"])
    assert ns.reserved_connections == 0
    for bad_value in ("-1", "not-a-number"):
        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["inventory", "--reserved-connections", bad_value])
        assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "non-negative integer" in captured.err


def test_inventory_old_basis_accepts_zero_but_rejects_negative(capsys):
    """182/183: `--data-process-count-old-basis`
    accepts `0` ("no old-basis process is declared") -- only a negative
    value (or non-integer text) is a usage error -- exit code 1, not
    argparse's default 2."""
    parser = ops._build_parser()
    try:
        ns = parser.parse_args(["inventory", "--data-process-count-old-basis", "0"])
    except SystemExit as exc:
        assert False, f"0 must be accepted for --data-process-count-old-basis, got SystemExit({exc.code})"
    assert ns.data_process_count_old_basis == 0
    for bad_value in ("-1", "not-a-number"):
        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["inventory", "--data-process-count-old-basis", bad_value])
        assert excinfo.value.code == 1
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


def test_inventory_ddl_lock_is_confirmed_without_lock_timeout_declared(platform):
    """`lock_timeout` is no longer part of
    this judgment -- confirmed once `statement_timeout` is declared
    database-independently on every target role (and each role's
    `CONNECTION LIMIT` is set, already true from `0012`), even though
    `0007` never declares `lock_timeout` on either writer role at all
    (replaces the earlier `test_inventory_ddl_lock_is_unknown_when_lock_
    timeout_not_declared`, from before item (6) dropped `lock_timeout`)."""
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for role in (platform.api_role, platform.controlplane_role, f"{platform.prefix}svc_auditreader"):
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5000ms'").format(sql.Identifier(role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "confirmed", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared(platform):
    """`lock_timeout` declared alone (never
    `statement_timeout`) on every target role still leaves item (6)
    unknown -- `lock_timeout` alone is never sufficient. Resets
    `mitatedbsvc_auditreader`'s own `statement_timeout` (declared by
    0013's default bootstrap) back to undeclared first."""
    _reset_role_statement_timeout(platform.admin_dsn, f"{platform.prefix}svc_auditreader")
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            for role in (platform.api_role, platform.controlplane_role, f"{platform.prefix}svc_auditreader"):
                cur.execute(sql.SQL("ALTER ROLE {} SET lock_timeout = '3000ms'").format(sql.Identifier(role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


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
    assert report == {"judgment": "confirmed", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_key_set_is_the_same_on_the_psycopg_error_path(monkeypatch, platform):
    """A `psycopg.Error` while discovering item (6)'s own target roles
    (`_inventory_role_classes`) still returns the SAME key set as every
    other outcome (`judgment`/`remediation_required`/`reason`) -- the
    confirmed, unknown (undeclared, `-1` CONNECTION LIMIT), and blocked
    paths are each already pinned to this exact dict shape by the other
    tests in this file; this is the one remaining return path (the
    `psycopg.Error` early returns) none of them exercises."""
    def _raise(conn, schema):
        raise psycopg.OperationalError("synthetic failure")

    monkeypatch.setattr(ops, "_inventory_role_classes", _raise)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_target_roles_include_auditreader(platform):
    """Item (6)'s target roles are the SAME
    full set item (8) discovers (api/controlplane/auditreader) -- with
    `lock_timeout`/`statement_timeout` declared on api/controlplane ONLY
    (and `mitatedbsvc_auditreader`'s own `statement_timeout`, declared by
    0013's default bootstrap, reset back to undeclared), the item
    stays unknown."""
    _reset_role_statement_timeout(platform.admin_dsn, f"{platform.prefix}svc_auditreader")
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
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_is_confirmed_by_default_bootstrap_alone(platform):
    """`statement_timeout` is already declared, database-
    independently, on every platform-plane role by 0007 (api/
    controlplane) and 0013 (`mitatedbsvc_auditreader`) alone, with each
    role's `CONNECTION LIMIT` already set by 0012 -- item (6) reads
    confirmed with no further declaration step and no application
    provisioned yet."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "confirmed", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_zero(platform):
    """`mitatedbsvc_auditreader`'s own
    `statement_timeout` (declared by 0013's default bootstrap) explicitly
    set to `0` (PostgreSQL's own disabled rendering) makes item (6)
    blocked with the fixed reason, `remediation_required` staying
    `False`, and the item still carries a `reason` key in the blocked
    case."""
    _declare_role_lock_timeouts(platform)
    _set_role_statement_timeout(platform.admin_dsn, f"{platform.prefix}svc_auditreader", "0")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False, "reason": "statement-timeout-unbounded"}
    assert set(report.keys()) == {"judgment", "remediation_required", "reason"}


def test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_negative(monkeypatch, platform):
    """PostgreSQL itself refuses a negative `statement_timeout`
    on a real role, so this observes the judgment through a
    substitute reader returning one negative declared value for
    `mitatedbsvc_auditreader` only -- every other role is still read for
    real."""
    _declare_role_lock_timeouts(platform)
    auditreader_role = f"{platform.prefix}svc_auditreader"
    original = platform_declarations._role_setting_rows

    def _fake(conn, role_name):
        if role_name == auditreader_role:
            return [(0, None, ["statement_timeout=-5000"])]
        return original(conn, role_name)

    monkeypatch.setattr(platform_declarations, "_role_setting_rows", _fake)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False, "reason": "statement-timeout-unbounded"}


def test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_unparseable(monkeypatch, platform):
    """An unrecognized `statement_timeout` rendering
    (never producible on a real role) is blocked, never confirmed
    or unknown, its own raw text never surfacing in the output, and the
    judgment stays inside the closed vocabulary."""
    _declare_role_lock_timeouts(platform)
    auditreader_role = f"{platform.prefix}svc_auditreader"
    original = platform_declarations._role_setting_rows

    def _fake(conn, role_name):
        if role_name == auditreader_role:
            return [(0, None, ["statement_timeout=not-a-timeout"])]
        return original(conn, role_name)

    monkeypatch.setattr(platform_declarations, "_role_setting_rows", _fake)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False, "reason": "statement-timeout-unbounded"}
    assert report["judgment"] in ops._INVENTORY_JUDGMENTS
    assert "not-a-timeout" not in json.dumps(report)


def test_inventory_ddl_lock_is_blocked_when_only_the_application_runtime_role_is_unbounded(monkeypatch, platform):
    """Every other target role stays positively bounded; only
    the provisioned application's own runtime role is set to `0`."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    app_database = _provision_app(platform, "app1")
    _set_role_statement_timeout(platform.admin_dsn, f"{app_database}_rt", "0")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False, "reason": "statement-timeout-unbounded"}


def test_inventory_ddl_lock_is_blocked_when_only_the_application_developer_role_is_unbounded(monkeypatch, platform):
    """Same property as the runtime-role test above, for the
    developer role."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    app_database = _provision_app(platform, "app1")
    _set_role_statement_timeout(platform.admin_dsn, f"{app_database}_dv", "0")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "blocked", "remediation_required": False, "reason": "statement-timeout-unbounded"}


def test_inventory_ddl_lock_blocked_outranks_unknown_when_mixed_with_an_undeclared_role(monkeypatch, platform):
    """One provisioned application role at `0` (blocked) and its
    own sibling role reset to undeclared (unknown) -- the combined
    judgment across the whole target set is `blocked`, mirroring item
    (3)'s own judgment-combining rule."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    app_database = _provision_app(platform, "app1")
    _set_role_statement_timeout(platform.admin_dsn, f"{app_database}_rt", "0")
    _reset_role_statement_timeout(platform.admin_dsn, f"{app_database}_dv")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_ddl_lock_minus_one_and_zero_statement_timeout_mixture_is_unknown(platform):
    """The CONNECTION LIMIT early return happens before
    any role's `statement_timeout` value is read, so a `-1` CONNECTION
    LIMIT on `controlplane_role` mixed with a `0` `statement_timeout` on
    `api_role` still reads unknown, never blocked -- the "blocked
    outranks unknown" rule applies only between `statement_timeout`
    value judgments, never back across this early return."""
    _declare_role_lock_timeouts(platform)
    _set_role_statement_timeout(platform.admin_dsn, platform.api_role, "0")
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.controlplane_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_confirmed_after_0013_is_applied(monkeypatch, capsys):
    """A platform bootstrapped only through 0012
    (0013 not yet applied) reads item (6) as unknown; applying 0013
    alone -- no further declaration step -- makes it confirmed. Applies
    0013 directly via psql (design D-6, R-57): a solo `0013` is now
    refused by `apply-platform-migration` (its own successor `0014` is
    absent from a single-file call); this test's own subject is item
    (6)'s own read of 0013's SQL-level effect, unrelated to that
    refusal."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r45wpbinvf29{secrets.token_hex(4)}"
    try:
        info = _bootstrap(prefix, apply_0013=False)
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        _declare_golden_path(monkeypatch, info)
        conn = ops._inventory_connect(info.provision_dsn)
        try:
            before = ops._inventory_ddl_lock_declaration(conn, info.schema)
        finally:
            conn.close()
        assert before["judgment"] == "unknown"

        _run_psql(info.provision_dsn, info.migrations_dir / "0013_role_statement_timeouts.sql")

        conn = ops._inventory_connect(info.provision_dsn)
        try:
            after = ops._inventory_ddl_lock_declaration(conn, info.schema)
        finally:
            conn.close()
        assert after == {"judgment": "confirmed", "remediation_required": False, "reason": None}
    finally:
        _sweep_prefix(admin_dsn, prefix)


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
    """29b/189: while
    `--data-process-count-old-basis` declares 1 or more old-basis
    processes, omitting `--concurrency` leaves item (8) unknown -- the
    code never fills it in with a default. A `--data-process-count-old-
    basis=1`/`--data-process-count-total=2` shape with the declaration
    already in place (`_declare_golden_path`) is `confirmed` once
    `--concurrency` IS supplied (filling the default-filled value 32 makes
    the api-role demand 76, under `0014`'s 132 -- `0012`'s own default
    bootstrap limit, 68, would wrongly stay `blocked` here), isolating the
    omission itself from any other reason item (8) could stay
    `unknown`."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=None,
                data_process_ceiling=1, data_process_count_total=2,
            ))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


def test_inventory_connection_headroom_old_basis_missing_is_unknown(monkeypatch, platform):
    """188: omitting `--data-process-count-old-basis`
    entirely leaves item (8) unknown -- it is never filled in with `0`
    (the value that would otherwise make this input `confirmed`,
    `_HEADROOM_OK`'s own golden path, once the declaration
    (`_declare_golden_path`) is in place)."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(data_process_count_old_basis=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


def test_inventory_connection_headroom_old_basis_zero_without_concurrency_is_judged(monkeypatch, platform):
    """190: `--data-process-count-old-basis 0` with
    `--concurrency` omitted (the only combination that input-shape
    validation accepts for old-basis 0) still reaches a judgment once the
    rest of the input is present -- never stuck at `unknown` merely
    because `--concurrency` is absent when old-basis is 0."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(data_process_count_old_basis=0, concurrency=None))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_thread_limit_missing_is_unknown(monkeypatch, platform):
    """191: omitting `--thread-limit` leaves item (8)
    unknown -- it is never filled in with `DEFAULT_THREAD_LIMIT` (the
    value `_HEADROOM_OK`'s own golden path uses, which would otherwise
    make this `confirmed` once the declaration (`_declare_golden_path`) is
    in place)."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(thread_limit=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


def test_inventory_connection_headroom_process_count_missing_is_unknown(platform):
    """31a: any ONE of the four process
    arguments missing (here `--data-process-ceiling`) leaves item (8)
    unknown -- the other three never fill in for it."""
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(data_process_ceiling=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


def test_inventory_connection_headroom_reserved_connections_missing_is_unknown(monkeypatch, platform):
    """35b."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(reserved_connections=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


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
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


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


# ===========================================================================
# W1-7 (design §4, 2026-09-18 supervisor ruling S-1): a stray single-file
# re-application of `0012` or `0013` AFTER `0014` is not reverted by any
# migration file -- `apply-platform-migration` re-applies exactly the one
# file named. Item (8) catches the resulting under-provisioned state in
# some cases and not others; these fix which, rather than adding a new
# check.
# ===========================================================================


def test_inventory_connection_headroom_catches_0012_reapplied_alone_after_0014(monkeypatch, platform):
    """S-1: a stray `0012` re-application rolls every existing
    platform-plane and application role back to 0012's own values (68/20/
    36) -- item (8), read at one old-basis process (`concurrency=6`)
    plus one new-basis process (`thread_limit=4`, control total 2),
    catches this via condition 1 on `mitatedbsvc_controlplane` ALONE
    (demand 32 > 20); the api role's own demand (24) stays under its
    68, the app role's own demand (12) stays under its 36, and the
    auditreader role's own demand (8) stays under its untouched 12, so
    no other role's condition 1 check can explain the `blocked` result
    here."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _provision_app(platform, "w17a")
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0012_role_connection_limits.sql")
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=6, data_process_ceiling=1, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=2, reserved_connections=0))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_catches_0013_reapplied_alone_after_0014_when_a_new_application_exists(
    monkeypatch, platform,
):
    """S-1: a stray `0013` re-application does not touch any EXISTING
    role's own CONNECTION LIMIT (0013 only replaces the provisioning
    FUNCTION) -- item (8) catches it once an application is provisioned
    AFTER the stray re-application, since THAT application's own
    runtime/developer role is created with 36 (0013's own value) instead
    of 68."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0013_role_statement_timeouts.sql")
    _provision_app(platform, "w17b")
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=32, data_process_ceiling=1, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=2, reserved_connections=0))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_misses_0013_reapplied_alone_after_0014_with_no_new_application(
    monkeypatch, platform,
):
    """S-1 (documented current limitation -- a fix to the underlying
    detection would make this test go red): a stray `0013` re-application
    after 0014, with NO application provisioned afterward, touches
    nothing item (8) reads -- every existing role's own CONNECTION LIMIT
    is still 0014's own value, so condition 1 stays satisfied and item
    (8) reads `confirmed`, even though the provisioning FUNCTION itself
    is silently back at 36 for the NEXT application provisioned."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _provision_app(platform, "w17c")
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0013_role_statement_timeouts.sql")
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=32, data_process_ceiling=1, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=2, reserved_connections=0))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_data_process_count_overflow_is_blocked(monkeypatch, capsys, platform):
    """33a (all-revision process count, not just
    one) and 34 (condition 1's own role-vs-limit comparison). 0014 raises
    `mitatedbsvc_api`'s CONNECTION LIMIT to 132; at 35 new-basis
    processes (the golden-path `_HEADROOM_OK` basis) and the default
    `thread_limit` (4, `role_pool_size` 6), the api role's own demand is
    `2 * 35 * 6 = 420`, still well past 132 -- blocked."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _declare_golden_path(monkeypatch, platform, data=35, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(data_process_ceiling=35, data_process_count_total=35, control_process_ceiling=1, control_process_count_total=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_declared_and_actual_process_counts_disagree_is_blocked(monkeypatch, platform):
    """33b: the declared Data ceiling (1)
    disagrees with the passed `--data-process-ceiling` (2)."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(data_process_ceiling=2, data_process_count_total=2, control_process_ceiling=1, control_process_count_total=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_control_process_count_mismatch_is_blocked(monkeypatch, platform):
    """(33b): the
    CONTROL side of the declared-vs-actual comparison is checked
    independently of the DATA side. Declares `control=2` but PASSES
    `control_process_ceiling=1` (matching data on both sides, and keeping
    the ACTUAL controlplane demand well under its CONNECTION LIMIT so
    condition 1 alone could never explain a `blocked` result) -- isolates
    the mismatch check itself."""
    _declare_golden_path(monkeypatch, platform, data=1, control=2)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(data_process_ceiling=1, data_process_count_total=1, control_process_ceiling=1, control_process_count_total=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_role_coefficient_is_two_times_concurrency_for_api(monkeypatch, platform):
    """34a/202: the OLD-basis api demand term is
    `_API_ROLE_STORE_COUNT * concurrency` PER old-basis process (never a
    hardcoded `1`, and never folded into the new-basis `role_pool_size`
    term). 0014 raises `mitatedbsvc_api`'s CONNECTION LIMIT to 132; with
    one old-basis process (`concurrency=67`) and one new-basis process
    (`thread_limit=4`, `role_pool_size` 6), demand is
    `2*67 + 2*6 = 146`, past 132 -- blocked."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=67, data_process_ceiling=1, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=1))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_rollout_two_processes_confirmed_three_processes_blocked(monkeypatch, platform):
    """the rollout worked example (design
    docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md §5.1 (i)): one
    OLD-basis process (`concurrency=32`) plus W NEW-basis processes
    (`thread_limit=4`, `role_pool_size` 6) on a 0014-applied cluster
    (`mitatedbsvc_api` CONNECTION LIMIT 132). api demand is
    `2*32 + 2*6*W = 64 + 12W`: at W=5 (`data_process_count_total=6`) it
    is 124, confirmed; at W=6 (`data_process_count_total=7`) it is 136,
    past 132 -- blocked. The app role's own floor (`32 + 6W`) stays
    within its own CONNECTION LIMIT (68) at both W, isolating the api
    role as the one that blocks at W=6."""
    _run_psql(platform.provision_dsn, platform.migrations_dir / "0014_role_connection_limits_rollout.sql")
    _provision_app(platform, "w110")
    _declare_golden_path(monkeypatch, platform, data=1, control=1)

    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        confirmed_report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=32, data_process_ceiling=1, data_process_count_total=6,
                control_process_ceiling=1, control_process_count_total=1, reserved_connections=0))
    finally:
        conn.close()
    assert confirmed_report["judgment"] == "confirmed"

    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        blocked_report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=32, data_process_ceiling=1, data_process_count_total=7,
                control_process_ceiling=1, control_process_count_total=1, reserved_connections=0))
    finally:
        conn.close()
    assert blocked_report["judgment"] == "blocked"


def test_inventory_connection_headroom_shared_application_role_budget_counts_once(monkeypatch, platform):
    """34b: the aggregate's
    own shared-application-role term (condition 2) is the LARGER of
    condition 1's per-role floor and `2 * K * (O + N * role_pool_size)` (K
    registered applications, each with up to `role_pool_size` connections
    per role on a new-basis process and one on an old-basis one), never the
    per-role floor multiplied by K (a per-role floor that then "counts
    once" no matter how many applications share it, as long as
    `2 * K * (O + N * role_pool_size)` stays below it). With K=2
    applications, one new-basis process (`thread_limit=4`,
    `role_pool_size` 6), and no old-basis process, `2*2*(0+1*6)=24`
    exceeds the per-role floor (6), so it is the term that is used."""
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
    thread_limit = 4
    pool_size = config.role_pool_size(thread_limit)
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * pool_size
    controlplane_demand = 16
    auditreader_demand = 4
    app_shared_demand = max(pool_size, 2 * 2 * (0 + 1 * pool_size))  # K=2, O=0, N=1
    correct_total = (
        api_demand + controlplane_demand + auditreader_demand + app_shared_demand
        + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
    )
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                thread_limit=thread_limit, data_process_ceiling=1, data_process_count_total=1,
                control_process_ceiling=1, control_process_count_total=1,
                reserved_connections=max_connections - correct_total,
            ),
        )
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"

    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                thread_limit=thread_limit, data_process_ceiling=1, data_process_count_total=1,
                control_process_ceiling=1, control_process_count_total=1,
                reserved_connections=max_connections - correct_total + 1,
            ),
        )
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_condition1_uses_concurrency_not_one(monkeypatch, platform):
    """Condition 1's own OLD-basis app-role
    term is `concurrency`, never a hardcoded `1` -- with one old-basis
    process (`concurrency=2`) and one new-basis process (`thread_limit=4`,
    `role_pool_size` 6), the floor is `2 + 6 = 8`; a hardcoded `1` in
    place of `concurrency` would instead give `1 + 6 = 7`. An app role
    `CONNECTION LIMIT` of 7 must still be `blocked` (7 < 8), which a
    hardcoded-`1` floor (7 == 7) would wrongly confirm."""
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
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 7").format(sql.Identifier(runtime_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=2, data_process_ceiling=1, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_demand_scales_with_data_process_count(monkeypatch, platform):
    """Condition 1's own
    app-role threshold is `data_process_count_total * role_pool_size
    (thread_limit)` (all-new-basis here, `N=3`, `role_pool_size(4)=6`),
    never `role_pool_size` alone -- the app role's own `CONNECTION LIMIT`
    (17) sits strictly between the per-process floor (6) and the
    N-scaled floor (18), so a mutation that drops the `* N` factor
    would wrongly read `confirmed` here. Isolated from the
    platform-plane roles' own checks by keeping THEIR demand well under
    their real `CONNECTION LIMIT` (68/20/5) while only the app role's own
    (lowered) limit is exceeded."""
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
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 17").format(sql.Identifier(runtime_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=3, data_process_count_total=3,
                control_process_ceiling=1, control_process_count_total=1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_overflow_with_named_values(monkeypatch, platform):
    """One old-basis process (`concurrency=28`) plus two
    new-basis processes (`thread_limit=4`, `role_pool_size` 6): the app
    role's own condition 1 floor is `28 + 2*6 = 40`, past the default
    `0003` app-role `CONNECTION LIMIT` of 36 -- blocked. The API role's own
    CONNECTION LIMIT is raised out of the way (100000) so only the app
    role's own (default) CONNECTION LIMIT can explain a `blocked` result
    (without this, `0012`'s own default of 68 for `mitatedbsvc_api` is
    itself exceeded here -- `1*2*28 + 2*2*6 = 80`). This floor catches
    two distinct mutations, each of which reads `confirmed` here instead
    of `blocked`: dropping the app-role floor's own `* N` factor
    (`28 + 6 = 34`) and counting the old-basis process at
    `role_pool_size` instead of `concurrency` (`(1+2)*6 = 18`)."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    _provision_app(platform, "app1")
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 100000").format(sql.Identifier(platform.api_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=1, concurrency=28, data_process_ceiling=2, data_process_count_total=3,
                control_process_ceiling=1, control_process_count_total=1,
            ))
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
    assert report == {"judgment": "unknown", "remediation_required": True, "control_deployed": True}


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
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


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
    assert report == {"judgment": "blocked", "remediation_required": False, "control_deployed": True}


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
    """A `statement_timeout` declared only for
    ONE specific database (`setdatabase != 0`) does not count as the
    role's own database-independent declaration -- stays unknown (item
    (6)'s runtime-settings half no longer reads `lock_timeout` at all,
    so this targets the property that IS still checked)."""
    _declare_role_lock_timeouts(platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} RESET statement_timeout").format(
                    sql.Identifier(platform.api_role), sql.Identifier(platform.platform_db)
                )
            )
            cur.execute(
                sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(platform.api_role))
            )
            cur.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET statement_timeout = '3000ms'").format(
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
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_target_roles_include_application_roles(monkeypatch, platform):
    """Item (6)'s target roles include every
    provisioned application's own `runtime_role`/`developer_role`, the
    SAME full set item (8) discovers -- resetting both roles' own
    `statement_timeout` (declared automatically by 0013's
    `begin_provision_application` at provisioning time) back to
    undeclared leaves item (6) unknown even when every platform-plane
    role has it."""
    _declare_golden_path(monkeypatch, platform)
    _declare_role_lock_timeouts(platform)
    app_database = _provision_app(platform, "app1")
    _reset_role_statement_timeout(platform.admin_dsn, f"{app_database}_rt")
    _reset_role_statement_timeout(platform.admin_dsn, f"{app_database}_dv")
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


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
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_connection_headroom_auditreader_counted_under_control_only(monkeypatch, platform):
    """34c."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=2, data_process_count_total=2,
                control_process_ceiling=1, control_process_count_total=1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


# ===========================================================================
# ceiling vs total, input-shape rejection, and --control-not-deployed
# ===========================================================================


def test_inventory_connection_headroom_total_may_exceed_ceiling_without_a_declaration_mismatch(monkeypatch, platform):
    """The declared/actual comparison is checked
    against each revision's own CEILING, never against the (larger,
    traffic-migration) TOTAL -- a total well above the declared ceiling
    is not, by itself, a declaration mismatch."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=1, data_process_count_total=5,
                control_process_ceiling=1, control_process_count_total=1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_condition1_demand_uses_the_total_not_the_ceiling(monkeypatch, platform):
    """Condition 1's own per-role demand is computed
    from `--data-process-count-total`, never from `--data-process-
    ceiling` -- a ceiling of 1 (matching the declaration) would fit
    comfortably under the API role's own CONNECTION LIMIT (68), but a
    total of 20 does not."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=1, data_process_count_total=20,
                control_process_ceiling=1, control_process_count_total=1, reserved_connections=0,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_condition2_demand_uses_the_total_not_the_ceiling(monkeypatch, platform):
    """The aggregate (condition 2) demand against
    `max_connections` is computed from the process-count TOTALs, never
    from the ceilings -- every per-role CONNECTION LIMIT is left with
    ample headroom (so condition 1 alone cannot explain a `blocked`
    result), and `--reserved-connections` is set so only the TOTAL-based
    aggregate demand overflows `max_connections`. 16 old-basis processes
    (`concurrency=1`) plus 1 new-basis process (`thread_limit=4`,
    `role_pool_size` 6) give a total of 17, far above the declared
    ceiling of 1."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)
    old_basis, concurrency, thread_limit = 16, 1, 4
    pool_size = config.role_pool_size(thread_limit)
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * (old_basis * concurrency + 1 * pool_size)  # 44
    controlplane_demand = 16
    auditreader_demand = 4
    total_demand = api_demand + controlplane_demand + auditreader_demand + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
    reserved = max_connections - total_demand + 1
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=old_basis, concurrency=concurrency, thread_limit=thread_limit,
                data_process_ceiling=1, data_process_count_total=17,
                control_process_ceiling=1, control_process_count_total=1, reserved_connections=reserved,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_role_demand_uses_the_total_not_the_ceiling(monkeypatch, platform):
    """Condition 1's own per-app-role demand is
    computed from `--data-process-count-total`, never from `--data-
    process-ceiling` -- the API role's own CONNECTION LIMIT is raised
    out of the way so only the app role's own (default) CONNECTION
    LIMIT (36) can explain a `blocked` result: with `N=10` the app
    role's own demand is 60 (over 36), while condition 2's own
    TOTAL-based aggregate demand (262) stays at or under
    `max_connections`, so condition 2 cannot explain the `blocked`
    result instead."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _provision_app(platform, "app1")
    platform_conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with platform_conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role, developer_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")
                )
            )
            (runtime_role, developer_role) = cur.fetchone()
    finally:
        platform_conn.close()
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 100000").format(sql.Identifier(platform.api_role)))
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)
    data_process_count_total = 10
    pool_size = config.role_pool_size(ops.DEFAULT_THREAD_LIMIT)
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * data_process_count_total * pool_size  # 120
    app_role_floor = data_process_count_total * pool_size  # 60
    app_shared_demand = max(app_role_floor, 2 * 1 * data_process_count_total * pool_size)  # 120
    controlplane_demand = platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR  # 16
    auditreader_demand = platform_declarations._AUDITREADER_ROLE_POOL_FLOOR  # 4
    condition_2_demand = (
        api_demand + controlplane_demand + auditreader_demand + app_shared_demand
        + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
    )  # 262
    assert condition_2_demand <= max_connections
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=1, data_process_count_total=data_process_count_total,
                control_process_ceiling=1, control_process_count_total=1, reserved_connections=0,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_control_demand_uses_the_total_not_the_ceiling(monkeypatch, platform):
    """Condition 1's own per-role demand for
    Control (controlplane/auditreader) is computed from `--control-
    process-count-total`, never from `--control-process-ceiling` -- a
    total of 4 against the controlplane role's own (default) CONNECTION
    LIMIT (20) must still be `blocked` even though a ceiling of 1 would
    fit comfortably."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=1, data_process_count_total=1,
                control_process_ceiling=1, control_process_count_total=4, reserved_connections=0,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_app_shared_demand_in_the_aggregate_uses_the_total_not_the_ceiling(monkeypatch, platform):
    """The aggregate (condition 2)'s own
    contribution from the shared application-role budget is computed
    from the TOTAL-based `app_role_floor` (`N * role_pool_size
    (thread_limit)`, all-new-basis here), never re-derived from the
    ceiling -- every per-role CONNECTION LIMIT is raised at least to
    condition 1's own demand (`api >= 2 * pool_size * N`, `app >=
    pool_size * N`) so condition 1 alone cannot explain
    a `blocked` result, Control's own ceiling (1) and total (2)
    deliberately differ, and `--reserved-connections` is set so only the
    TOTAL-based aggregate demand overflows `max_connections` (a mutation
    that zeroes condition 2's own application term would instead read
    `confirmed`)."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _provision_app(platform, "app1")
    platform_conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with platform_conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role, developer_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")
                )
            )
            (runtime_role, developer_role) = cur.fetchone()
    finally:
        platform_conn.close()
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 300").format(sql.Identifier(platform.api_role)))
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 50").format(sql.Identifier(platform.controlplane_role)))
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(
                sql.Identifier(f"{platform.prefix}svc_auditreader")))
            for role in (runtime_role, developer_role):
                cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 150").format(sql.Identifier(role)))
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)
    thread_limit, data_process_count_total = 4, 10
    pool_size = config.role_pool_size(thread_limit)
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * pool_size * data_process_count_total
    assert api_demand == 120 and 300 >= api_demand
    app_role_floor = pool_size * data_process_count_total
    assert app_role_floor == 60 and 150 >= app_role_floor
    controlplane_demand = 2 * 16
    auditreader_demand = 2 * 4
    app_shared_demand = max(app_role_floor, 2 * 1 * data_process_count_total * pool_size)
    assert app_shared_demand == 2 * app_role_floor
    total_demand = (
        api_demand + controlplane_demand + auditreader_demand + app_shared_demand
        + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS
    )
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_ceiling=1, data_process_count_total=data_process_count_total,
                control_process_ceiling=1, control_process_count_total=2,
                reserved_connections=max_connections - total_demand + 1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_data_total_below_ceiling_is_rejected_with_exit_code_1():
    """Data's total < ceiling is a contradictory input,
    refused with a fixed message and exit code 1 (never blocked/2) --
    input-shape validation runs before any database connection is
    attempted."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--concurrency", "2",
            "--data-process-ceiling", "5", "--data-process-count-total", "1",
            "--control-process-ceiling", "1", "--control-process-count-total", "1",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1


def test_inventory_control_total_below_ceiling_is_rejected_with_exit_code_1(capsys):
    """Control's total < ceiling is refused the same way,
    with its own fixed message naming the CONTROL arguments (input
    values never echoed)."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "1",
            "--control-process-ceiling", "7", "--control-process-count-total", "3",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: --control-process-count-total must not be less than --control-process-ceiling"
    assert "7" not in captured.err and "3" not in captured.err


def test_inventory_control_not_deployed_with_ceiling_is_rejected_with_exit_code_1(capsys):
    """--control-not-deployed and --control-process-ceiling
    together are refused before any database connection, exit code 1."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "1",
            "--control-not-deployed", "--control-process-ceiling", "1",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: --control-not-deployed and --control-process-ceiling are mutually exclusive"


def test_inventory_control_not_deployed_with_total_is_rejected_with_exit_code_1(capsys):
    """--control-not-deployed and --control-process-count-total
    together are refused before any database connection, exit code 1."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "1",
            "--control-not-deployed", "--control-process-count-total", "1",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: --control-not-deployed and --control-process-count-total are mutually exclusive"


def test_inventory_old_basis_exceeding_total_is_rejected_with_exit_code_1(capsys):
    """184: `--data-process-count-old-basis` greater than
    `--data-process-count-total` is a contradictory input, refused with a
    fixed message and exit code 1 (never blocked/2) -- the rejected
    values are never echoed. Both the total (2) and the ceiling (1) here
    already satisfy the existing total-vs-ceiling check, isolating this
    one."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--data-process-count-old-basis", "3", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "2",
            "--control-process-ceiling", "1", "--control-process-count-total", "1",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: --data-process-count-old-basis must not exceed --data-process-count-total"
    assert "3" not in captured.err and "2" not in captured.err


def test_inventory_new_basis_count_below_ceiling_is_rejected_with_exit_code_1(capsys):
    """185: `--data-process-count-total` minus
    `--data-process-count-old-basis` (the new-basis count) less than
    `--data-process-ceiling` is a contradictory input (the new candidate
    revision itself must be present at least `--data-process-ceiling`
    times) -- refused before any database connection, exit code 1. The
    total (3) is not itself below the ceiling (2) -- only the NEW-basis
    remainder (1) is -- so the existing total-vs-ceiling check alone
    would not catch this."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--data-process-count-old-basis", "2", "--concurrency", "2",
            "--data-process-ceiling", "2", "--data-process-count-total", "3",
            "--control-process-ceiling", "1", "--control-process-count-total", "1",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        "error: --data-process-count-total minus --data-process-count-old-basis must not be less than "
        "--data-process-ceiling"
    )


def test_inventory_old_basis_zero_with_concurrency_is_rejected_with_exit_code_1(capsys):
    """186: declaring `--data-process-count-old-basis 0`
    (no process on the old basis) together with `--concurrency` (a value
    that would then read nothing) is refused before any database
    connection, exit code 1 -- omitting `--data-process-count-old-basis`
    entirely never trips this check (188's own `unknown`, not a usage
    error)."""
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--data-process-count-old-basis", "0", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "1",
            "--control-process-ceiling", "1", "--control-process-count-total", "1",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "error: --concurrency must be omitted when --data-process-count-old-basis is 0"


def test_inventory_old_basis_shape_checks_run_before_any_connection(monkeypatch, capsys):
    """187: 184's own input-shape rejection happens before
    `cmd_inventory` ever opens a connection -- `MITATEDB_PROVISION_DSN`
    is set to a real, reachable DSN, and the connection factory
    (`psycopg.connect`) is spied to prove it is never called."""
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", _admin_dsn())
    calls = {"count": 0}
    original_connect = psycopg.connect

    def _spy_connect(*args, **kwargs):
        calls["count"] += 1
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(psycopg, "connect", _spy_connect)
    with pytest.raises(SystemExit) as excinfo:
        ops.main([
            "inventory", "--data-process-count-old-basis", "3", "--concurrency", "2",
            "--data-process-ceiling", "1", "--data-process-count-total", "2",
            "--control-process-ceiling", "1", "--control-process-count-total", "1",
            "--reserved-connections", "0",
        ])
    assert excinfo.value.code == 1
    assert calls["count"] == 0


def test_inventory_connection_headroom_control_not_deployed_computes_with_control_zeroed(monkeypatch, platform):
    """--control-not-deployed computes (8) with Control's own
    process count and auditreader connections at 0, never unknown merely
    because Control's own process arguments are absent."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"
    assert report["control_deployed"] is False


def test_inventory_connection_headroom_control_absent_without_the_not_deployed_flag_is_unknown(monkeypatch, platform):
    """Control's own process arguments missing AND --control-not-
    deployed absent leaves (8) unknown -- unknown is never silently read
    as not-deployed."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema, _headroom_args(control_process_ceiling=None, control_process_count_total=None))
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "control_deployed": True}


def test_inventory_connection_headroom_control_not_deployed_ignores_declared_control_mismatch(monkeypatch, platform):
    """Control's own declared ceiling (a permitted maximum) is
    never compared once --control-not-deployed is given, even when the
    declared value differs wildly from reality."""
    _declare_golden_path(monkeypatch, platform, data=1, control=99)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_control_not_deployed_ignores_auditreader_minus_one(monkeypatch, platform):
    """With --control-not-deployed, auditreader's own
    CONNECTION LIMIT = -1 is excluded from the -1 check -- (8) is not
    forced unknown by it."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(
                sql.Identifier(f"{platform.prefix}svc_auditreader")))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_control_not_deployed_with_no_control_roles_found_is_not_unknown(monkeypatch, platform):
    """If no Control-plane role is found by grant at all (the
    exclusion set is empty), that alone is not a reason to fall back to
    unknown when --control-not-deployed is given."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    original_role_classes = ops._inventory_role_classes
    monkeypatch.setattr(
        ops, "_inventory_role_classes",
        lambda conn, schema: (original_role_classes(conn, schema)[0], (), ()),
    )
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_connection_headroom_control_not_deployed_still_checks_data_mismatch(monkeypatch, platform):
    """--control-not-deployed does not relax the Data-side
    declared/actual comparison -- a Data ceiling mismatch is
    still blocked."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                control_not_deployed=True, control_process_ceiling=None, control_process_count_total=None,
                data_process_ceiling=2, data_process_count_total=2,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "blocked"


def test_inventory_connection_headroom_control_deployed_is_true_when_flag_absent(monkeypatch, platform):
    """control_deployed is true whenever
    --control-not-deployed was not given (the default)."""
    _declare_golden_path(monkeypatch, platform)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args())
    finally:
        conn.close()
    assert report["control_deployed"] is True


# ===========================================================================
# item (8) matches F-16's own thread-limit-basis floors (design
# docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md D-1) -- one shared
# boundary probe for the four role classes and the four floor constants,
# then the mixed-basis and aggregate boundaries.
# ===========================================================================


def _f16_and_inventory_agree_at_boundary(
    platform: types.SimpleNamespace, *, roles: "tuple[str, ...]", pool_size: int,
    process_ceilings: "platform_declarations.ProcessCeilings", role_classes: "frozenset[str]",
    application_ids: "tuple[str, ...]", headroom_kwargs: dict, minimum: int,
) -> None:
    """Shared boundary probe for the 一致/定数の差し替え tests: asserts
    F-16 (`platform_declarations.check_role_connection_limits`) and item
    (8) (`ops._inventory_connection_headroom`) both pass at `minimum` and
    both fail at `minimum - 1`, for the SAME role(s), pool size, and
    process count."""
    def _set(limit: int) -> None:
        for role in roles:
            _set_connection_limit(platform.admin_dsn, role, limit)

    def _f16_passes(limit: int) -> bool:
        _set(limit)
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            try:
                platform_declarations.check_role_connection_limits(
                    conn, schema=platform.schema, ops_module=platform_declarations.PEER_MODULE,
                    pool_size=pool_size, process_ceilings=process_ceilings,
                    role_classes=role_classes, application_ids=application_ids,
                )
                return True
            except platform_declarations.PlatformDeclarationError:
                return False
        finally:
            conn.close()

    def _inventory_confirms(limit: int) -> bool:
        _set(limit)
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(conn, platform.schema, _headroom_args(**headroom_kwargs))
        finally:
            conn.close()
        return report["judgment"] == "confirmed"

    assert _f16_passes(minimum) and _inventory_confirms(minimum)
    assert not _f16_passes(minimum - 1) and not _inventory_confirms(minimum - 1)


def test_inventory_connection_headroom_matches_f16_minimum_limit_for_api(monkeypatch, platform):
    """192 (一致, api): the same thread-limit/process-count
    input makes F-16 and item (8) agree on the minimum `mitatedbsvc_api`
    CONNECTION LIMIT that passes -- both pass at the computed minimum and
    both fail one below it. `thread_limit=7` (never `DEFAULT_THREAD_LIMIT`
    4) and `n=2` (never 1): a mutation that reads item (8)'s NEW-basis
    pool size from `DEFAULT_THREAD_LIMIT` instead of the declared
    `--thread-limit` moves item (8)'s own minimum away
    from F-16's, per new-basis process, and this boundary catches it."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    thread_limit, n = 7, 2
    pool_size = config.role_pool_size(thread_limit)
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(platform.api_role,), pool_size=pool_size,
        process_ceilings=platform_declarations.ProcessCeilings(data=n, control=1),
        role_classes=frozenset({"api"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=thread_limit,
            data_process_ceiling=n, data_process_count_total=n,
            control_process_ceiling=1, control_process_count_total=1,
        ),
        minimum=platform_declarations._API_ROLE_STORE_COUNT * pool_size * n,
    )


def test_inventory_connection_headroom_matches_f16_minimum_limit_for_application(monkeypatch, platform):
    """193 (一致, application): 192's own property,
    for one application's runtime/developer roles -- F-16 narrowed to
    `application_ids=("app1",)` with `role_classes=frozenset()`
    (excluding the platform-plane classes) is compared against item (8)'s
    own application-role floor. `thread_limit=7`/`n=2` (never the
    default/1) so a mutation that ignores the declared `--thread-limit`
    is caught here too."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    _provision_app(platform, "app1")
    conn0 = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn0.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role, developer_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")))
            (runtime_role, developer_role) = cur.fetchone()
    finally:
        conn0.close()
    thread_limit, n = 7, 2
    pool_size = config.role_pool_size(thread_limit)
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(runtime_role, developer_role), pool_size=pool_size,
        process_ceilings=platform_declarations.ProcessCeilings(data=n, control=1),
        role_classes=frozenset(), application_ids=("app1",),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=thread_limit,
            data_process_ceiling=n, data_process_count_total=n,
            control_process_ceiling=1, control_process_count_total=1,
        ),
        minimum=pool_size * n,
    )


def test_inventory_connection_headroom_matches_f16_minimum_limit_for_controlplane(monkeypatch, platform):
    """194 (一致, controlplane): 192's own
    property, for `mitatedbsvc_controlplane` -- F-16 narrowed to
    `role_classes={"controlplane"}` (excluding the application floor via
    `application_ids=()`) is compared against item (8)'s own controlplane
    demand (D-5: independent of thread_limit/concurrency)."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    n = 1
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(platform.controlplane_role,), pool_size=config.role_pool_size(4),
        process_ceilings=platform_declarations.ProcessCeilings(data=1, control=n),
        role_classes=frozenset({"controlplane"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=4,
            data_process_ceiling=1, data_process_count_total=1,
            control_process_ceiling=n, control_process_count_total=n,
        ),
        minimum=platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR * n,
    )


def test_inventory_connection_headroom_matches_f16_minimum_limit_for_auditreader(monkeypatch, platform):
    """195 (一致, auditreader): 194's own
    property, for `mitatedbsvc_auditreader` (`role_classes=
    {"auditreader"}`)."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    n = 1
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(auditreader_role,), pool_size=config.role_pool_size(4),
        process_ceilings=platform_declarations.ProcessCeilings(data=1, control=n),
        role_classes=frozenset({"auditreader"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=4,
            data_process_ceiling=1, data_process_count_total=1,
            control_process_ceiling=n, control_process_count_total=n,
        ),
        minimum=platform_declarations._AUDITREADER_ROLE_POOL_FLOOR * n,
    )


def test_inventory_connection_headroom_pool_size_headroom_constant_moves_both(monkeypatch, platform):
    """196 (定数の差し替え, pool): patching
    `config._POOL_SIZE_HEADROOM` (a module attribute `config.
    role_pool_size` reads at call time) moves F-16's own minimum
    CONNECTION LIMIT and item (8)'s own `confirmed` minimum together --
    item (8) reads the constant by name rather than baking today's value
    into its own arithmetic. `thread_limit=7`/`n=2` (never the default/1)
    so a mutation that ignores the declared `--thread-limit`
    is caught here too."""
    _declare_golden_path(monkeypatch, platform, data=2, control=1)
    monkeypatch.setattr(config, "_POOL_SIZE_HEADROOM", 9)
    thread_limit, n = 7, 2
    pool_size = config.role_pool_size(thread_limit)
    assert pool_size == thread_limit + 9
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(platform.api_role,), pool_size=pool_size,
        process_ceilings=platform_declarations.ProcessCeilings(data=n, control=1),
        role_classes=frozenset({"api"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=thread_limit,
            data_process_ceiling=n, data_process_count_total=n,
            control_process_ceiling=1, control_process_count_total=1,
        ),
        minimum=platform_declarations._API_ROLE_STORE_COUNT * pool_size * n,
    )


def test_inventory_connection_headroom_api_role_store_count_constant_moves_both(monkeypatch, platform):
    """197 (定数の差し替え, api): patching
    `platform_declarations._API_ROLE_STORE_COUNT` moves both minimums
    together."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    monkeypatch.setattr(platform_declarations, "_API_ROLE_STORE_COUNT", 5)
    thread_limit, n = 4, 1
    pool_size = config.role_pool_size(thread_limit)
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(platform.api_role,), pool_size=pool_size,
        process_ceilings=platform_declarations.ProcessCeilings(data=n, control=1),
        role_classes=frozenset({"api"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=thread_limit,
            data_process_ceiling=n, data_process_count_total=n,
            control_process_ceiling=1, control_process_count_total=1,
        ),
        minimum=5 * pool_size * n,
    )


def test_inventory_connection_headroom_controlplane_floor_constant_moves_both(monkeypatch, platform):
    """198 (定数の差し替え, controlplane): patching
    `platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR` moves both
    minimums together."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    monkeypatch.setattr(platform_declarations, "_CONTROLPLANE_ROLE_POOL_FLOOR", 21)
    n = 1
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(platform.controlplane_role,), pool_size=config.role_pool_size(4),
        process_ceilings=platform_declarations.ProcessCeilings(data=1, control=n),
        role_classes=frozenset({"controlplane"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=4,
            data_process_ceiling=1, data_process_count_total=1,
            control_process_ceiling=n, control_process_count_total=n,
        ),
        minimum=21 * n,
    )


def test_inventory_connection_headroom_auditreader_floor_constant_moves_both(monkeypatch, platform):
    """199 (定数の差し替え, auditreader): patching
    `platform_declarations._AUDITREADER_ROLE_POOL_FLOOR` moves both
    minimums together."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    monkeypatch.setattr(platform_declarations, "_AUDITREADER_ROLE_POOL_FLOOR", 9)
    n = 1
    auditreader_role = f"{platform.prefix}svc_auditreader"
    _f16_and_inventory_agree_at_boundary(
        platform, roles=(auditreader_role,), pool_size=config.role_pool_size(4),
        process_ceilings=platform_declarations.ProcessCeilings(data=1, control=n),
        role_classes=frozenset({"auditreader"}), application_ids=(),
        headroom_kwargs=dict(
            data_process_count_old_basis=0, thread_limit=4,
            data_process_ceiling=1, data_process_count_total=1,
            control_process_ceiling=n, control_process_count_total=n,
        ),
        minimum=9 * n,
    )


def test_inventory_connection_headroom_mixed_basis_condition1_boundary_for_api(monkeypatch, platform):
    """200 (混在, api, 条件1): with one
    old-basis process (`concurrency=10`) and one new-basis process
    (`thread_limit=4`, `role_pool_size` 6, deliberately `!= concurrency`),
    the api role's own condition 1 floor is `2*(10 + 6) = 32` -- confirmed
    at 32, blocked at 31."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    thread_limit, concurrency = 4, 10
    pool_size = config.role_pool_size(thread_limit)
    minimum = platform_declarations._API_ROLE_STORE_COUNT * (1 * concurrency + 1 * pool_size)
    assert minimum == 32

    def _judge(limit: int) -> str:
        _set_connection_limit(platform.admin_dsn, platform.api_role, limit)
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=1, concurrency=concurrency, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=2, control_not_deployed=True,
                    control_process_ceiling=None, control_process_count_total=None,
                ))
        finally:
            conn.close()
        return report["judgment"]

    assert _judge(minimum) == "confirmed"
    assert _judge(minimum - 1) == "blocked"


def test_inventory_connection_headroom_mixed_basis_condition1_boundary_for_application(monkeypatch, platform):
    """201 (混在, application, 条件1): the
    application role's own condition 1 floor is `O*c + N*p` (200's own
    property, without the api role's own store-count multiplier) --
    `10 + 6 = 16`, confirmed at 16 on both the runtime and developer
    role, blocked at 15."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    _provision_app(platform, "app1")
    conn0 = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn0.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT runtime_role, developer_role FROM {} WHERE application_id = 'app1'").format(
                    sql.Identifier(platform.schema, "applications")))
            (runtime_role, developer_role) = cur.fetchone()
    finally:
        conn0.close()
    thread_limit, concurrency = 4, 10
    pool_size = config.role_pool_size(thread_limit)
    minimum = 1 * concurrency + 1 * pool_size
    assert minimum == 16

    def _judge(limit: int) -> str:
        _set_connection_limit(platform.admin_dsn, runtime_role, limit)
        _set_connection_limit(platform.admin_dsn, developer_role, limit)
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=1, concurrency=concurrency, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=2, control_not_deployed=True,
                    control_process_ceiling=None, control_process_count_total=None,
                ))
        finally:
            conn.close()
        return report["judgment"]

    assert _judge(minimum) == "confirmed"
    assert _judge(minimum - 1) == "blocked"


def test_inventory_connection_headroom_control_demand_independent_of_thread_limit_and_concurrency(monkeypatch, platform):
    """203: Control's own demand (D-5) depends
    only on `--control-process-count-total`, never on `--thread-limit`/
    `--concurrency` -- the controlplane boundary (16 per process) stays
    fixed across two very different (concurrency, thread_limit) pairs."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)

    def _judge(limit: int, *, concurrency: int, thread_limit: int) -> str:
        _set_connection_limit(platform.admin_dsn, platform.controlplane_role, limit)
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=1, concurrency=concurrency, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=2,
                    control_process_ceiling=1, control_process_count_total=1,
                ))
        finally:
            conn.close()
        return report["judgment"]

    for concurrency, thread_limit in ((2, 1), (20, 4)):
        assert _judge(16, concurrency=concurrency, thread_limit=thread_limit) == "confirmed"
        assert _judge(15, concurrency=concurrency, thread_limit=thread_limit) == "blocked"


def test_inventory_connection_headroom_aggregate_application_term_uses_the_per_role_floor_when_larger(monkeypatch, platform):
    """204 (条件2 第1項): with K=1 registered
    application, the per-role floor (`O*c + N*p = 50 + 6 = 56`) exceeds
    `2*K*(O+N*p) = 2*1*(1+6) = 14` -- the aggregate's own application term
    is 56, never the smaller `2*K*(O+N*p)`. Every per-role CONNECTION LIMIT is
    raised out of the way so condition 1 alone cannot explain a `blocked`
    result; `--reserved-connections` isolates the aggregate boundary."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    database_name = _provision_app(platform, "app1")
    _set_connection_limit(platform.admin_dsn, platform.api_role, 100000)
    _set_connection_limit(platform.admin_dsn, f"{database_name}_rt", 100000)
    _set_connection_limit(platform.admin_dsn, f"{database_name}_dv", 100000)

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)

    old_basis, concurrency, thread_limit = 1, 50, 4
    pool_size = config.role_pool_size(thread_limit)
    app_role_floor = old_basis * concurrency + 1 * pool_size
    assert app_role_floor == 56
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * (old_basis * concurrency + 1 * pool_size)
    app_shared_demand = max(app_role_floor, 2 * 1 * (old_basis + 1 * pool_size))
    assert app_shared_demand == app_role_floor
    total_demand = api_demand + app_shared_demand + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS

    def _judge(reserved: int) -> str:
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=old_basis, concurrency=concurrency, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=2, control_not_deployed=True,
                    control_process_ceiling=None, control_process_count_total=None,
                    reserved_connections=reserved,
                ))
        finally:
            conn.close()
        return report["judgment"]

    assert _judge(max_connections - total_demand) == "confirmed"
    assert _judge(max_connections - total_demand + 1) == "blocked"


def test_inventory_connection_headroom_aggregate_application_term_uses_the_registration_count_when_larger(monkeypatch, platform):
    """205 (条件2 第2項): with K=4 registered
    applications and only one new-basis process (`thread_limit=4`,
    `role_pool_size` 6, no old-basis process), `2*K*(O+N*p) = 2*4*6 = 48`
    exceeds the per-role floor (6) -- the aggregate's own application
    term is 48, never the smaller per-role floor."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    for app_id in ("app1", "app2", "app3", "app4"):
        _provision_app(platform, app_id)

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)

    thread_limit = 4
    pool_size = config.role_pool_size(thread_limit)
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * pool_size
    app_role_floor = pool_size
    app_shared_demand = max(app_role_floor, 2 * 4 * (0 + 1 * pool_size))
    assert app_shared_demand == 48
    total_demand = api_demand + app_shared_demand + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS

    def _judge(reserved: int) -> str:
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=0, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=1, control_not_deployed=True,
                    control_process_ceiling=None, control_process_count_total=None,
                    reserved_connections=reserved,
                ))
        finally:
            conn.close()
        return report["judgment"]

    assert _judge(max_connections - total_demand) == "confirmed"
    assert _judge(max_connections - total_demand + 1) == "blocked"


def test_inventory_connection_headroom_aggregate_application_term_registration_count_wins_with_an_old_basis_process(monkeypatch, platform):
    """205's own property (registration
    count wins), with an old-basis process present (`O=1`): 204's own
    input keeps `O` in the per-role floor's dominant term, so it never
    exercises `2*K*(O+N)`'s own `O` addend. Here
    `O=1`, `concurrency=6`, one new-basis process (`thread_limit=4`,
    `role_pool_size` 6), and `K=4` registered applications: the per-role
    floor is `O*c + N*p = 6 + 6 = 12`, but `2*K*(O+N*p) = 2*4*(1+6) = 56`
    exceeds it -- the aggregate's own application term is 56, never the
    smaller per-role floor. A mutation that drops `O` from this term
    (`2*K*N*p = 2*4*6 = 48`) would read 48 instead, under-counting by 8."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    for app_id in ("app1", "app2", "app3", "app4"):
        database_name = _provision_app(platform, app_id)
        _set_connection_limit(platform.admin_dsn, f"{database_name}_rt", 100000)
        _set_connection_limit(platform.admin_dsn, f"{database_name}_dv", 100000)
    _set_connection_limit(platform.admin_dsn, platform.api_role, 100000)

    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
    finally:
        admin.close()
    max_connections = int(max_connections_text)

    old_basis, concurrency, thread_limit = 1, 6, 4
    pool_size = config.role_pool_size(thread_limit)
    app_role_floor = old_basis * concurrency + 1 * pool_size
    assert app_role_floor == 12
    api_demand = platform_declarations._API_ROLE_STORE_COUNT * (old_basis * concurrency + 1 * pool_size)
    app_shared_demand = max(app_role_floor, 2 * 4 * (old_basis + 1 * pool_size))
    assert app_shared_demand == 56
    total_demand = api_demand + app_shared_demand + ops._INVENTORY_MAX_CONCURRENT_CONNECTIONS

    def _judge(reserved: int) -> str:
        conn = ops._inventory_connect(platform.provision_dsn)
        try:
            report = ops._inventory_connection_headroom(
                conn, platform.schema,
                _headroom_args(
                    data_process_count_old_basis=old_basis, concurrency=concurrency, thread_limit=thread_limit,
                    data_process_ceiling=1, data_process_count_total=2, control_not_deployed=True,
                    control_process_ceiling=None, control_process_count_total=None,
                    reserved_connections=reserved,
                ))
        finally:
            conn.close()
        return report["judgment"]

    assert _judge(max_connections - total_demand) == "confirmed"
    assert _judge(max_connections - total_demand + 1) == "blocked"


def test_inventory_connection_headroom_condition1_application_floor_independent_of_registration_count(monkeypatch, platform):
    """206: condition 1's own per-role floor for
    an application's runtime/developer role is `O*c + N*p` alone, never
    `2*K*(O+N)` -- with K=4 registered applications and every runtime/
    developer role's own CONNECTION LIMIT set to EXACTLY the per-role
    floor (6, not the larger `2*4*1=8`), item (8) still reads `confirmed`
    (the aggregate's own larger `2*K*(O+N)` term still fits comfortably
    under `max_connections`)."""
    _declare_golden_path(monkeypatch, platform, data=1, control=1)
    thread_limit = 4
    pool_size = config.role_pool_size(thread_limit)
    for app_id in ("app1", "app2", "app3", "app4"):
        database_name = _provision_app(platform, app_id)
        _set_connection_limit(platform.admin_dsn, f"{database_name}_rt", pool_size)
        _set_connection_limit(platform.admin_dsn, f"{database_name}_dv", pool_size)
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_connection_headroom(
            conn, platform.schema,
            _headroom_args(
                data_process_count_old_basis=0, thread_limit=thread_limit,
                data_process_ceiling=1, data_process_count_total=1,
                control_process_ceiling=1, control_process_count_total=1,
            ))
    finally:
        conn.close()
    assert report["judgment"] == "confirmed"


def test_inventory_ddl_lock_control_not_deployed_does_not_exclude_controlplane_role(monkeypatch, platform):
    """Item (6)'s own runtime-settings judgment keeps reading
    Control's roles regardless of item (8)'s --control-not-deployed: a
    controlplane role with CONNECTION LIMIT = -1 still makes (6)
    unknown."""
    _declare_role_lock_timeouts(platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.controlplane_role)))
    finally:
        admin.close()
    conn = ops._inventory_connect(platform.provision_dsn)
    try:
        report = ops._inventory_ddl_lock_declaration(conn, platform.schema)
    finally:
        conn.close()
    assert report == {"judgment": "unknown", "remediation_required": False, "reason": None}


def test_inventory_ddl_lock_via_cli_control_not_deployed_still_reads_controlplane_role(monkeypatch, capsys, platform):
    """The full `inventory` CLI invocation, run
    with item (8)'s own --control-not-deployed, never lets that flag
    reach item (6): `_inventory_ddl_lock_declaration` takes no `args`
    at all, so there is no path for the flag to reach it -- a
    controlplane role with CONNECTION LIMIT = -1 still makes (6)
    unknown."""
    _declare_role_lock_timeouts(platform)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT -1").format(sql.Identifier(platform.controlplane_role)))
    finally:
        admin.close()
    kwargs = dict(_HEADROOM_OK)
    kwargs.pop("control_process_ceiling")
    kwargs.pop("control_process_count_total")
    kwargs["control_not_deployed"] = True
    _rc, report, _out, _err = _run_inventory(monkeypatch, capsys, platform, **kwargs)
    assert report["ddl_lock"] == {"judgment": "unknown", "remediation_required": False, "reason": None}


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
