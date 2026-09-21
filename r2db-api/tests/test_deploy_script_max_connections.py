"""R-66 WP-1 (design D-2, work order docs/work-orders/
WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_TIMEOUT_V1.md §2 完了条件 4):
`r2db-api/deploy/scripts/part1a_check_max_connections.sh`'s own refusal/
pass logic, driven directly (no `sudo useradd`/venv-creation steps stand
between a test and this script the way they do for
`part1_provision_host_and_db.sh` itself -- design D-2's own "置き場"
rationale) with a stub `psql` placed first on `PATH`.

The stub (`_write_stub_psql` below) never parses real SQL -- it recognizes
which of the script's four queries it was handed by a distinguishing
keyword in the SQL text (`to_regclass`, `superuser_reserved_connections`,
`max_connections`, `count(*)`) and answers from environment variables the
test sets per scenario, exactly as the work order's own §2.4 asks for
("stub は SHOW の2値とNを試験ごとに差し替えられる形にする").

Four scenarios (work order §2.2 完了条件 4 (a)-(d), non-vacuous: every
scenario below both invokes the script and asserts on its exit code, so
at least one real observation exists per test):

  (a) insufficient headroom -> non-zero exit + a refusal naming every
      value the work order requires (§2.2 完了条件 3).
  (b) sufficient headroom -> exit 0.
  (c) R2DBSVC_EXPECTED_PEAK_CONNECTIONS holding a non-positive-integer
      value (including an EXPLICITLY EMPTY string -- code review 1 高2:
      empty is one of the forms the work order names as rejected, and is
      distinguishable in bash from "unset" via `${VAR+x}`, not `${VAR:-}`)
      -> refused, regardless of (a)/(b)'s own headroom.
  (d) R2DBSVC_EXPECTED_PEAK_CONNECTIONS holding a valid positive integer
      -> REPLACES (never adds to) the script's own conservative default,
      proven here by giving it a value low enough to pass a scenario that
      would fail under the default.

`_run` invokes `SCRIPT` DIRECTLY (`subprocess.run([str(SCRIPT), ...])`,
never `["bash", str(SCRIPT)]`) -- the same way
`part1_provision_host_and_db.sh`'s own Step 3 calls it
(`"${SCRIPT_DIR}/part1a_check_max_connections.sh"`, no `bash` prefix).
Code review 1 高1: prefixing the subprocess call with `bash` masked a real
defect -- the script shipped in this WP with mode `100644` (not
executable), which `part1_provision_host_and_db.sh`'s own direct-invocation
form fails on with "permission denied" (exit 126) under `set -euo
pipefail`, right after `0002`. `test_script_is_executable` below pins the
mode directly; every other test in this file exercises it as a side effect
of using it as an executable at all.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "scripts" / "part1a_check_max_connections.sh"

_STUB_PSQL = """#!/usr/bin/env bash
sql="$3"
case "$sql" in
    *to_regclass*) echo "${STUB_REGCLASS:-}" ;;
    *superuser_reserved_connections*) echo "${STUB_SUPERUSER_RESERVED:?unset}" ;;
    *max_connections*) echo "${STUB_MAX_CONNECTIONS:?unset}" ;;
    *'count(*)'*) echo "${STUB_APP_COUNT:-0}" ;;
    *) echo "test stub psql: unrecognized query: $sql" >&2; exit 9 ;;
esac
"""


def _write_stub_psql(tmp_path: Path) -> Path:
    stub_dir = tmp_path / "stubbin"
    stub_dir.mkdir()
    stub = stub_dir / "psql"
    stub.write_text(_STUB_PSQL)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub_dir


def _run(tmp_path: Path, env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    stub_dir = _write_stub_psql(tmp_path)
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"
    env["R2DBSVC_CONTROL_DSN"] = "postgresql://ignored.example.invalid/ignored"
    env.pop("R2DBSVC_EXPECTED_PEAK_CONNECTIONS", None)
    env.update(env_overrides)
    return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)


def test_script_is_executable() -> None:
    """Code review 1 高1: pins the executable bit directly, in addition to
    every other test in this file exercising it as a side effect of `_run`
    invoking `SCRIPT` directly (no `bash` prefix)."""
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable (mode {oct(SCRIPT.stat().st_mode)})"


def test_insufficient_headroom_is_refused_and_names_every_required_value(tmp_path: Path) -> None:
    """(a): max_connections 205 - superuser_reserved 7 = 198 available;
    N=1 already-provisioned application makes the required figure
    98 + 72 x (1 + 1) = 242. 198 < 242 -> refused. The refusal text names
    the two SHOW values, the computed required figure, N, the runbook
    section, and R2DBSVC_EXPECTED_PEAK_CONNECTIONS itself (work order §2.2
    完了条件 3). Code review 1 低1: the four numbers (205, 7, 242, N=1) share
    no digits with one another, so each `assert "<value>" in stderr` below
    can only be satisfied by that value's own occurrence, never by
    coincidentally matching a substring of a DIFFERENT value in the same
    message (the previous 100/3/314/N=2 choice let "3" match inside "314"
    too, so the superuser_reserved_connections assertion was not actually
    independent of the required-figure assertion)."""
    result = _run(
        tmp_path,
        {"STUB_MAX_CONNECTIONS": "205", "STUB_SUPERUSER_RESERVED": "7", "STUB_REGCLASS": "r2dbsvc_registry.applications", "STUB_APP_COUNT": "1"},
    )
    assert result.returncode != 0, result.stderr
    assert "refusing to proceed" in result.stderr, result.stderr
    assert "205" in result.stderr, result.stderr
    assert "superuser_reserved_connections (7)" in result.stderr, result.stderr
    assert "242" in result.stderr, result.stderr
    assert "N=1" in result.stderr, result.stderr
    assert "POSTGRES_PROVISIONING_RUNBOOK.md §4" in result.stderr, result.stderr
    assert "R2DBSVC_EXPECTED_PEAK_CONNECTIONS" in result.stderr, result.stderr


def test_sufficient_headroom_passes(tmp_path: Path) -> None:
    """(b): max_connections 300 - superuser_reserved 3 = 297 available;
    no `applications` table at all (empty to_regclass) -> N=0, required
    98 + 72 x (0 + 1) = 170. 297 >= 170 -> exit 0."""
    result = _run(
        tmp_path,
        {"STUB_MAX_CONNECTIONS": "300", "STUB_SUPERUSER_RESERVED": "3", "STUB_REGCLASS": ""},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("bad_value", ["", "0", "-5", "not-a-number"])
def test_expected_peak_connections_rejects_non_positive_integers(tmp_path: Path, bad_value: str) -> None:
    """(c): every non-positive-integer form the work order names (空文字・
    0・負・非数字) is refused, independently of whether the underlying
    headroom would otherwise pass (300 - 3 = 297 available here, well
    above the 170 default -- so a pass-through bug would show up as a
    wrongly-successful exit 0, not merely a differently-worded failure).

    Code review 1 高2/中1: an EXPLICITLY SET, empty
    `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` (`bad_value == ""` -- distinct from
    the variable being unset at all, which `test_sufficient_headroom_
    passes` above exercises via `_run`'s own `env.pop(...)`) is one of the
    forms the work order names as rejected. bash CAN distinguish "set to
    empty" from "unset" (`${VAR+x}`, contra this file's own previous
    docstring here, which wrongly claimed the two were indistinguishable);
    the script under test now uses that form specifically so this case is
    refused rather than silently falling through to the default-required
    path."""
    overrides = {
        "STUB_MAX_CONNECTIONS": "300",
        "STUB_SUPERUSER_RESERVED": "3",
        "STUB_REGCLASS": "",
        "R2DBSVC_EXPECTED_PEAK_CONNECTIONS": bad_value,
    }
    result = _run(tmp_path, overrides)
    assert result.returncode != 0, result.stderr
    assert "refusing to proceed" in result.stderr, result.stderr
    assert "R2DBSVC_EXPECTED_PEAK_CONNECTIONS" in result.stderr, result.stderr
    assert "positive integer" in result.stderr, result.stderr


def test_expected_peak_connections_replaces_the_default_not_added_to_it(tmp_path: Path) -> None:
    """(d): default required here would be 98 + 72 x (0 + 1) = 170, which
    97 available connections would FAIL -- but a valid override (50)
    replaces that default outright, so the same 97 available passes."""
    result = _run(
        tmp_path,
        {
            "STUB_MAX_CONNECTIONS": "100",
            "STUB_SUPERUSER_RESERVED": "3",
            "STUB_REGCLASS": "",
            "R2DBSVC_EXPECTED_PEAK_CONNECTIONS": "50",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "required 50" in result.stdout + result.stderr, result.stdout + result.stderr
