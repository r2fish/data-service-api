#!/usr/bin/env python3
"""gate.py -- the supervisor's solo root-suite gate in one command.

WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (b),
design docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2 D-5/D-6, decision
Q-3): gate starts its own throwaway PostgreSQL cluster
(`tools/testpg/dsa_testpg.py`), runs the root suite against THAT cluster
(`DSA_TEST_PG=external` + `Cluster.env()`), and judges `pg_database` /
`pg_roles` drift on it -- never on the shared local PostgreSQL
(`host=/tmp port=5432`) the standing MitateDB-api service and other
sessions' tests use. The shared local PostgreSQL is still read, before and
after, for information only (Q-3): its own diff is printed as an `info=`
line and never affects PASS/FAIL. Exclusivity is a real flock
(`dsa_testpg.suite_lock(exclusive=True, ...)`), replacing the former
`ps`-based `other_pytest` poll and the gate-hold flag file entirely
(Q-2 (a)).

Usage:
    tools/dev/gate.py [-C DIR] [--label LABEL] [--wait SECONDS] [--python PY]

    -C DIR      where to run (default: current directory; normally the repository root)
    --wait      longest wait for the exclusive suite lock (default 1800)

Command run: `<main checkout>/.venv/bin/python -m pytest -q -n 5 --dist loadgroup`,
with `DSA_TEST_PG=external` and the gate's own cluster's `Cluster.env()`.
PASS requires exit 0, a fully parsed summary line with passed > 0 and
failed / errors / skipped / xfailed / xpassed / deselected and subtests
failed / skipped / xfailed / xpassed all 0 (1.3-22), plus no pg_database /
pg_roles change on the gate's own run cluster (1.3-23, D-5).

Output: the tally, `judge=PASS|FAIL (...)`, the run-cluster catalog diff with
the log path, and one `info=` line for the shared cluster's own diff (never
judged; review M-2: prints `unavailable (<reason>)` instead of a diff if the
shared read itself fails, rather than aborting the whole gate for a read
that cannot affect the verdict). When the run-cluster catalog changed, one
line per non-empty added / removed list comes before the last line (at most
STDOUT_NAMES names each); the log ends with a section naming every added /
removed database and role, sorted.
The suite outlasts the Bash timeout: run it with run_in_background.
Exit: 0 PASS; 1 FAIL; 75 refused (the exclusive suite lock timed out); 78
precondition error (cluster start-up failed, or psql/pytest itself errored).
The pytest child runs with `DSA_TEST_PG_LOCK_HELD=1` (review B-1) so an
owned-mode pytest the suite spawns as a genuine nested subprocess (e.g.
conformance-tests/test_testpg_cluster.py's own nested-controller tests)
does not try to acquire the suite lock again and deadlock against this gate.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: anything under `tools/tests` -- the root suite does
       not collect it (it has its own pytest.ini root).
       why: the command run is the root `-m pytest -q -n 5 --dist
       loadgroup`.
       caught by: tools/dev/finalize.py --tools-tests.
    2. not detected: that it was pointed at the wrong tree -- `-C`
       defaults to the CURRENT directory, so a call made from the main
       checkout measures main and still prints `judge=PASS`.
       why: that default (see `-C` above).
       caught by: reading the directory gate.py prints with its own
       output lines (accepted).
    3. not detected: catalog drift on the shared local PostgreSQL -- its
       diff is printed as `info=` and never judged.
       why: the judged cluster is the gate's own throwaway one (D-5,
       Q-3; see the paragraph above).
       caught by: accepted by that decision -- the shared cluster
       carries the standing local service and other sessions' runs.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testpg"))
import dsa_testpg  # noqa: E402

GATE_ARGS = ["-q", "-n", "5", "--dist", "loadgroup"]
MUST_BE_ZERO = ("failed", "errors", "skipped", "xfailed", "xpassed", "deselected",
                "subtests failed", "subtests skipped", "subtests xfailed", "subtests xpassed")
STDOUT_NAMES = 10
LOG_SECTION = "gate: pg_database / pg_roles diff"


def judge(exit_code: int, tally: str | None) -> tuple[bool, list[str]]:
    counts = dl.parse_counts(tally)
    if counts is None:
        return False, [f"unparsable summary line: {tally!r}", f"exit={exit_code}"]
    reasons = [f"{k}={counts[k]}" for k in MUST_BE_ZERO if counts.get(k)]
    if exit_code != 0:
        reasons.append(f"exit={exit_code}")
    if not counts.get("passed"):
        reasons.append("passed=0")
    return not reasons, reasons


def catalog(query: str, env: dict[str, str]) -> list[str]:
    proc = subprocess.run(["psql", "-h", env.get("PGHOST", "/tmp"), "-d", "postgres", "-Atc", query],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise dl.DevError(f"psql failed: {proc.stderr.strip()}")
    return proc.stdout.splitlines()


def run_snapshot(env: dict[str, str]) -> dict[str, list[str]]:
    """The gate's OWN throwaway cluster (judged -- work order §3.1 (b))."""
    return {
        "pg_database": catalog("select datname from pg_database order by 1", env),
        "pg_roles": catalog("select rolname from pg_roles order by 1", env),
    }


def shared_snapshot() -> tuple[dict[str, list[str]] | None, str]:
    """The shared local PostgreSQL (`host=/tmp port=5432` by default) --
    read-only, information only, never judged (Q-3). Returns `(snapshot,
    reason)`: `snapshot` is `None` and `reason` names the failure when the
    read itself fails (review M-2: a down/moved shared PostgreSQL, or a bad
    `PGPORT`/`PGPASSFILE` in the operator's own shell, must never raise past
    here -- Q-3 already keeps this read out of the verdict, but letting an
    exception propagate would throw away a completed, possibly 40-minute
    suite run's tally/judge/log entirely, for a read that was never
    supposed to be able to do that)."""
    env = {**os.environ, "PGHOST": os.environ.get("PGHOST", "/tmp")}
    try:
        return {
            "pg_database": catalog("select datname from pg_database order by 1", env),
            "pg_roles": catalog("select rolname from pg_roles order by 1", env),
        }, ""
    except dl.DevError as exc:
        return None, str(exc)


def catalog_changes(before: dict[str, list[str]], after: dict[str, list[str]]) -> list[tuple[str, list[str], list[str]]]:
    """(catalog, added names, removed names) for each catalog that changed; names sorted."""
    out = []
    for name in before:
        added = sorted(set(after[name]) - set(before[name]))
        removed = sorted(set(before[name]) - set(after[name]))
        if added or removed:
            out.append((name, added, removed))
    return out


def diff(before: dict[str, list[str]], after: dict[str, list[str]]) -> list[str]:
    return counts(catalog_changes(before, after))


def counts(changed: list[tuple[str, list[str], list[str]]]) -> list[str]:
    return [f"{name} +{len(added)} -{len(removed)}" for name, added, removed in changed]


def _name_lists(changed: list[tuple[str, list[str], list[str]]]):
    for name, added, removed in changed:
        for kind, names in (("added", added), ("removed", removed)):
            if names:
                yield name, kind, names


def name_lines(changed: list[tuple[str, list[str], list[str]]], limit: int) -> list[str]:
    """Stdout form: one line per non-empty list, at most `limit` names each."""
    lines = []
    for name, kind, names in _name_lists(changed):
        more = len(names) - limit
        lines.append(f"{name} {kind} ({len(names)}): {', '.join(names[:limit])}"
                     + (f", ... +{more} more" if more > 0 else ""))
    return lines


def log_section(changed: list[tuple[str, list[str], list[str]]]) -> str:
    """Log form: every added / removed name, one per line (appended after pytest's output)."""
    lines = ["", f"== {LOG_SECTION} (names sorted) =="]
    if not changed:
        lines.append("0")
    for name, kind, names in _name_lists(changed):
        lines.append(f"{name} {kind} ({len(names)}):")
        lines += [f"  {n}" for n in names]
    return "\n".join(lines) + "\n"


def run_suite(cmd: list[str], cwd: Path, env: dict[str, str], stdout_path: Path) -> int:
    """Run the root suite with `env` (carries `DSA_TEST_PG=external` and the
    gate's own cluster's `Cluster.env()`), capturing combined output. No
    polling for other pytest processes any more (work order §3.1 (b)):
    exclusivity is the suite lock itself, held by the caller for the whole
    call."""
    with open(stdout_path, "w", encoding="utf-8") as out, open(f"{stdout_path}.stderr", "w", encoding="utf-8") as err:
        proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=out, stderr=err, text=True)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--label", default="gate")
    parser.add_argument("--wait", type=float, default=dsa_testpg.DEFAULT_LOCK_WAIT)
    parser.add_argument("--python")
    ns = parser.parse_args(argv)
    try:
        cwd = Path(ns.cwd).resolve()
        python = ns.python or dl.venv_python(cwd)
    except dl.DevError as exc:
        print(f"gate: ERROR -- {exc}")
        return dl.ERROR

    stage = "lock"
    try:
        with dsa_testpg.suite_lock(exclusive=True, wait=ns.wait):
            stage = "cluster"
            with dsa_testpg.cluster() as c:
                stage = "run"
                # review B-1: DSA_TEST_PG_LOCK_HELD tells any owned-mode pytest THIS suite run
                # itself spawns (e.g. conformance-tests/test_testpg_cluster.py's own nested-
                # controller tests) that an ancestor (this gate) already holds the suite lock
                # for the whole process tree, so it must not try to acquire it again -- that
                # would deadlock against this very gate, which cannot release the lock until
                # the suite (including that nested pytest) finishes.
                run_env = {**os.environ, **c.env(), dsa_testpg.ENV_MODE: "external",
                           dsa_testpg.ENV_LOCK_HELD: "1"}
                run_env.pop("PGPASSWORD", None)
                shared_before, shared_before_err = shared_snapshot()
                before = run_snapshot(run_env)
                log = dl.log_dir() / f"gate-{ns.label}-{dl.stamp()}.log"
                code = run_suite([python, "-m", "pytest", *GATE_ARGS], cwd, run_env, log)
                after = run_snapshot(run_env)
                shared_after, shared_after_err = shared_snapshot()
    except dl.DevError as exc:
        print(f"gate: ERROR -- {exc}")
        return dl.ERROR
    except dsa_testpg.TestPgError as exc:
        if stage == "lock":
            print(f"gate: REFUSED -- {exc}")
            return dl.REFUSED
        print(f"gate: ERROR -- {exc}")
        return dl.ERROR

    changed = catalog_changes(before, after)
    changes = counts(changed)
    # The tally is pytest's last line: read it before the name section is appended.
    tally = dl.tally_line(log.read_text(encoding="utf-8"))
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(log_section(changed))
    ok, reasons = judge(code, tally)
    reasons += changes
    ok = ok and not changes
    print(f"gate: {tally or '(no tally line)'}")
    print(f"gate: judge={'PASS' if ok else 'FAIL'}" + ("" if ok else f" ({', '.join(reasons)})"))
    for line in name_lines(changed, STDOUT_NAMES):
        print(f"gate: {line}")
    print(f"gate: pg_database/pg_roles diff {'0' if not changes else ', '.join(changes)} | log={log}")
    # review M-2: the shared cluster's own read can fail independently of the run cluster's --
    # never lets that abort the gate or drop the verdict already computed above (Q-3: this line
    # is information only in either case).
    if shared_before is None or shared_after is None:
        reason = shared_after_err or shared_before_err
        print(f"gate: info=shared pg_database/pg_roles diff unavailable ({reason})")
    else:
        shared_changes = counts(catalog_changes(shared_before, shared_after))
        print(f"gate: info=shared pg_database/pg_roles diff {'0' if not shared_changes else ', '.join(shared_changes)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
