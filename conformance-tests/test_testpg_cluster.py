"""conformance-tests/test_testpg_cluster.py -- integration coverage for
tools/testpg/dsa_testpg.py against a REAL PostgreSQL 16 cluster (work order
docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §2.4, design
docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2). The pure-Python decision
table, `Cluster.env()`'s shape, `pgpass`, and `sweep()` are instead
tools/tests/test_testpg.py, which never touches a real server.

Every test below starts its OWN, nested throwaway cluster through the
launcher's own public API (the `run --` CLI, or `dsa_testpg.cluster()`
in-process) rather than depending on the SUITE's own session cluster
(this test module's own `conftest.py` chain already started one, per
`DSA_TEST_PG=owned:...`) -- so these tests behave identically whether the
whole suite happens to be running "owned" (a throwaway cluster this
session started) or "external" (CI's `DSA_TEST_PG=external`, a real
Postgres container already running) -- design §7 WP-1's own stated
integration scope. `sweep()`'s own base-directory scan (used inside every
`start()`) is shared with the suite's session cluster, but never touches
it: that cluster's `owner.lock` stays held (and alive) for the whole
suite, so `sweep()` always leaves it alone (work order §2.1).

Not itself given an `adapter` fixture param, so `conftest.py`'s own
`pytest_collection_modifyitems` xdist-grouping hook places every test here
in the single shared, fixed `xdist_group` alongside the suite's other
non-adapter guards.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

import dsa_testpg  # tools/testpg/dsa_testpg.py -- sys.path-injected by the root conftest.py

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "tools" / "testpg" / "dsa_testpg.py"

_DSA_ENV_NAMES = (
    dsa_testpg.ENV_MODE, dsa_testpg.R2DB_DSN, dsa_testpg.MITATEDB_DSN,
    "PGHOST", "PGPORT", "PGUSER", "PGPASSFILE", "PGPASSWORD",
)


def _run_cli(args: list[str], timeout: float = 90) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LAUNCHER), *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=timeout)


def _last_json_object(text: str) -> dict:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON object line found in:\n{text}")


def _clean_dsa_env(env: dict) -> dict:
    """A copy of `env` with every `DSA_TEST_PG`/`PG*` variable this
    launcher cares about removed -- the starting point for a nested pytest
    that should decide for itself (rows 4/5/6 of the decision table) rather
    than inherit this test process's own `owned:...` state. Also strips
    every `PYTEST_*` variable (review follow-up, gate run 2026-09-16):
    under the root gate's `-n 5 --dist loadgroup`, THIS test process is
    itself an xdist worker, so `PYTEST_XDIST_WORKER` is genuinely set here
    -- an un-scrubbed copy would leak it into the nested pytest below,
    which then sees the variable, is NOT itself a worker, and (before
    `dsa_testpg._is_xdist_worker()` existed) was wrongly refused for
    looking like a stale one."""
    env = dict(env)
    for name in _DSA_ENV_NAMES:
        env.pop(name, None)
    for name in list(env):
        if name.startswith("PYTEST_"):
            del env[name]
    return env


def _system_identifier(dsn: str, passfile: str) -> int:
    with psycopg.connect(f"{dsn} passfile={passfile}") as conn, conn.cursor() as cur:
        cur.execute("select system_identifier from pg_control_system()")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# 1. No-host connection reaches the run's own cluster with the declared settings
# ---------------------------------------------------------------------------

_SETTINGS_SCRIPT = """
import json, os, psycopg
conn = psycopg.connect("dbname=postgres")
cur = conn.cursor()
cur.execute(
    "select current_setting('unix_socket_directories'), current_setting('max_connections'), "
    "current_setting('TimeZone'), current_setting('password_encryption'), current_setting('listen_addresses'), "
    "(select source from pg_settings where name = 'TimeZone'), "
    "(select source from pg_settings where name = 'max_connections'), "
    "(select system_identifier from pg_control_system())"
)
usd, maxconn, tz, pwenc, listen, tz_source, maxconn_source, system_id = cur.fetchone()
print(json.dumps({
    "pghost": os.environ.get("PGHOST"),
    "unix_socket_directories": usd,
    "max_connections": maxconn,
    "max_connections_source": maxconn_source,
    "timezone": tz,
    "timezone_source": tz_source,
    "password_encryption": pwenc,
    "listen_addresses": listen,
    "system_identifier": system_id,
}))
"""


def test_no_host_connection_reaches_the_run_cluster_with_declared_settings():
    """Review M-3: the CLI child's own `system_identifier` (`pg_control_
    system()`) is compared against a SEPARATE, independently-started
    reference cluster -- never the ambient session/suite DSN (review B-1:
    that can be the shared cluster under `DSA_TEST_PG=external`, or a
    `PGPASSFILE`-less DSN that raises `KeyError` under CI) -- so a false
    pass from an accidental pgpass-host match against some OTHER reachable
    cluster is ruled out, not just a `pghost == unix_socket_directories`
    tautology (true of any cluster, including a wrong one)."""
    with dsa_testpg.cluster() as reference:
        reference_env = reference.env()
        reference_sid = _system_identifier(reference_env[dsa_testpg.R2DB_DSN], reference_env["PGPASSFILE"])

        proc = _run_cli(["run", "--", sys.executable, "-c", _SETTINGS_SCRIPT])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = _last_json_object(proc.stdout)

    pghost = Path(data["pghost"])
    assert pghost.name == "s" and pghost.parent.name.startswith("run-"), (
        f"PGHOST does not look like a throwaway run directory's own socket dir: {data['pghost']!r}"
    )
    assert data["system_identifier"] != reference_sid, (
        "the CLI child's system_identifier matches an unrelated, independently-started reference "
        "cluster -- it did not reach its own nested cluster"
    )
    assert data["max_connections"] == "300"
    assert data["max_connections_source"] == "command line"
    assert data["timezone"] == "Asia/Tokyo"
    # `source = 'command line'` (pg_settings), not just a value comparison:
    # this machine's own local TimeZone happens to already be Asia/Tokyo, so
    # a bare `current_setting('TimeZone') == "Asia/Tokyo"` would pass even
    # with the launcher's own `-c TimeZone=Asia/Tokyo` removed entirely --
    # the `source` check is what actually proves the launcher set it.
    assert data["timezone_source"] == "command line"
    assert data["password_encryption"] == "scram-sha-256"
    assert data["listen_addresses"] == ""


# ---------------------------------------------------------------------------
# 2. A wrong password is rejected (scram, not trust)
# ---------------------------------------------------------------------------

_WRONG_PASSWORD_SCRIPT = """
import os, psycopg
os.environ["PGPASSFILE"] = "/dev/null"
try:
    psycopg.connect("dbname=postgres password=definitely-the-wrong-password")
    print("CONNECTED")
except psycopg.OperationalError:
    print("REJECTED")
"""


def test_wrong_password_is_rejected():
    proc = _run_cli(["run", "--", sys.executable, "-c", _WRONG_PASSWORD_SCRIPT])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "REJECTED" in proc.stdout
    assert "CONNECTED" not in proc.stdout


# ---------------------------------------------------------------------------
# 3. cluster() tears down on exit; a nested cluster has its own identity
# ---------------------------------------------------------------------------

def test_cluster_context_manager_tears_down_and_has_a_distinct_identity():
    """Review B-1: compares two INDEPENDENTLY-STARTED nested clusters
    against each other, never the ambient session/suite DSN -- reading
    `os.environ[R2DB_DSN]`/`PGPASSFILE` directly would `KeyError` under CI
    (`DSA_TEST_PG=external` sets the two DSNs and, since R-44 WP-4,
    `PGHOST`/`PGPORT`, but no `PGPASSFILE`: the container is TCP +
    password-in-DSN) and, worse, would connect straight
    to the SHARED cluster under any `external` that happens to name one --
    exactly what work order §1 forbids at every stage of implementation or
    testing."""
    with dsa_testpg.cluster() as a:
        a_sid = _system_identifier(a.env()[dsa_testpg.R2DB_DSN], a.env()["PGPASSFILE"])
        with dsa_testpg.cluster() as b:
            b_sid = _system_identifier(b.env()[dsa_testpg.R2DB_DSN], b.env()["PGPASSFILE"])
            run_dir = b.run_dir
            pid = b.postmaster_pid
            assert dsa_testpg._pid_alive(pid)

        assert a_sid != b_sid
        assert not run_dir.exists()
        assert not dsa_testpg._pid_alive(pid)


# ---------------------------------------------------------------------------
# 4. SIGKILLing the `run --` CLI process still tears the cluster down
# ---------------------------------------------------------------------------

_LONG_SLEEP_SCRIPT = (
    "import os, sys\n"
    "sys.stdout.write('READY %d %s\\n' % (os.getpid(), os.environ['PGHOST']))\n"
    "sys.stdout.flush()\n"
    "import time\n"
    "time.sleep(120)\n"
)


def test_sigkilling_the_cli_process_still_cleans_up():
    proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER), "run", "--", sys.executable, "-c", _LONG_SLEEP_SCRIPT],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    grandchild_pid = None
    try:
        ready = proc.stdout.readline()
        assert ready.startswith("READY "), ready
        _, pid_str, socket_dir = ready.split(None, 2)
        grandchild_pid = int(pid_str)
        run_dir = Path(socket_dir.strip()).parent
        assert run_dir.is_dir()

        proc.kill()  # SIGKILL the `dsa_testpg.py run --` process itself, not the grandchild
        proc.wait(timeout=30)

        deadline = time.monotonic() + 30
        while run_dir.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not run_dir.exists(), f"{run_dir} was not cleaned up after SIGKILL"
    finally:
        if grandchild_pid is not None and dsa_testpg._pid_alive(grandchild_pid):
            os.kill(grandchild_pid, signal.SIGKILL)  # this test's own collateral child, never PID-reused
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        proc.stdout.close()


# ---------------------------------------------------------------------------
# 5. Nested pytest: ambiguous env fails; owned: env does not start a new cluster
# ---------------------------------------------------------------------------

def test_nested_pytest_with_a_dsn_but_no_mode_is_ambiguous_and_fails():
    """The nested pytest must reach the "ambiguous" branch, not the
    xdist-worker one -- `_clean_dsa_env` strips `PYTEST_XDIST_WORKER` along
    with everything else, so the DSNs are added back explicitly (this is
    the one test in this file that WANTS a DSN present with no mode set)."""
    env = _clean_dsa_env(os.environ)
    env[dsa_testpg.R2DB_DSN] = os.environ[dsa_testpg.R2DB_DSN]
    env[dsa_testpg.MITATEDB_DSN] = os.environ[dsa_testpg.MITATEDB_DSN]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "r2db-api/tests/test_foundation.py"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode != 0
    assert "ambiguous" in (proc.stdout + proc.stderr)


def test_nested_pytest_with_owned_mode_does_not_start_a_new_cluster(tmp_path):
    """Review M-8: constructs an explicit `owned:...` environment from a
    cluster THIS test starts itself, rather than inheriting whatever mode
    the outer suite happens to be running under -- inheriting made this
    test mean "owned:..." only when the suite itself was already in owned
    mode, and a silent no-op (vacuous pass, neither branch exercising the
    `owned:` row) once the suite runs `DSA_TEST_PG=external` (CI today,
    and every gate run once WP-2's D-5 lands)."""
    report = tmp_path / "nested-owned-report.txt"
    with dsa_testpg.cluster() as inner:
        env = _clean_dsa_env(os.environ)
        env.update(inner.env())
        env[dsa_testpg.ENV_MODE] = f"owned:{inner.run_dir.name}"
        env[dsa_testpg.ENV_REPORT] = str(report)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "r2db-api/tests/test_foundation.py"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=90,
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not report.exists()


# ---------------------------------------------------------------------------
# 6. Each peer root starts (and cleans up) its own cluster
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("peer_test_path", [
    "r2db-api/tests/test_foundation.py",
    "MitateDB-api/tests/test_foundation.py",
])
def test_peer_root_starts_and_cleans_up_its_own_cluster(tmp_path, peer_test_path):
    report = tmp_path / (peer_test_path.replace("/", "_") + ".report.txt")
    env = _clean_dsa_env(os.environ)
    env[dsa_testpg.ENV_REPORT] = str(report)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", peer_test_path],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert report.is_file(), proc.stdout + proc.stderr
    run_dir = Path(report.read_text(encoding="utf-8").strip())
    assert not run_dir.exists(), f"{run_dir} should be gone once the nested pytest process exited"


# ---------------------------------------------------------------------------
# 7. `pytest tools/tests` never starts a cluster
# ---------------------------------------------------------------------------

def test_tools_tests_root_does_not_start_a_cluster(tmp_path):
    report = tmp_path / "tools-tests-report.txt"
    env = _clean_dsa_env(os.environ)
    env[dsa_testpg.ENV_REPORT] = str(report)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tools/tests"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not report.exists()
