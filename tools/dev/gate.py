#!/usr/bin/env python3
"""gate.py -- the supervisor's solo root-suite gate in one command.

Replaces: touch the gate-hold flag, wait for other pytest processes to end,
snapshot pg_database / pg_roles, run the root suite, snapshot again, judge
the tally, remove the flag (OPERATING_CONDITIONS 1.3-19..23).

Usage:
    tools/dev/gate.py [-C DIR] [--hold PATH] [--label LABEL] [--wait-max SECONDS] [--keep-hold]

    -C DIR      where to run (default: current directory; normally the repository root)
    --hold      gate-hold flag to create (default: $GATE_HOLD_FLAG, else $SP/gate-hold.flag)
    --wait-max  longest wait for other pytest processes (default 1800)

The flag is created exclusively: if it already exists (another gate), the
gate refuses and leaves it alone; it removes only a flag it created.
Command run: `<main checkout>/.venv/bin/python -m pytest -q -n 5 --dist loadgroup`.
While it runs, other pytest processes are polled every 10 s; any sighting fails
the gate (the run was not solo). PASS requires exit 0, a fully parsed summary
line with passed > 0 and failed / errors / skipped / xfailed / xpassed /
deselected and subtests failed / skipped / xfailed / xpassed all 0 (1.3-22),
plus no pg_database / pg_roles change (1.3-23). psql connects with
`-h $PGHOST` (default /tmp).

Output (3 lines): the tally, `judge=PASS|FAIL (...)`, and the catalog diff with the log path.
The suite outlasts the Bash timeout: run it with run_in_background.
Exit: 0 PASS; 1 FAIL; 75 refused (flag exists / other pytest did not end); 78 precondition error.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

GATE_ARGS = ["-q", "-n", "5", "--dist", "loadgroup"]
MUST_BE_ZERO = ("failed", "errors", "skipped", "xfailed", "xpassed", "deselected",
                "subtests failed", "subtests skipped", "subtests xfailed", "subtests xpassed")
POLL_SECONDS = 10.0


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


def catalog(query: str) -> list[str]:
    host = os.environ.get("PGHOST", "/tmp")
    proc = subprocess.run(["psql", "-h", host, "-d", "postgres", "-Atc", query], capture_output=True, text=True)
    if proc.returncode != 0:
        raise dl.DevError(f"psql failed: {proc.stderr.strip()}")
    return proc.stdout.splitlines()


def snapshot() -> dict[str, list[str]]:
    return {
        "pg_database": catalog("select datname from pg_database order by 1"),
        "pg_roles": catalog("select rolname from pg_roles order by 1"),
    }


def diff(before: dict[str, list[str]], after: dict[str, list[str]]) -> list[str]:
    out = []
    for name in before:
        added = sorted(set(after[name]) - set(before[name]))
        removed = sorted(set(before[name]) - set(after[name]))
        if added or removed:
            out.append(f"{name} +{len(added)} -{len(removed)}")
    return out


def create_flag(flag: Path) -> bool:
    """Create the hold flag exclusively; False if it already exists."""
    flag.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(flag, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    return True


def run_watched(cmd: list[str], cwd: Path, stdout_path: Path, poll: float = POLL_SECONDS) -> tuple[int, list[str]]:
    """Run `cmd`, polling for pytest processes outside this process's own chain."""
    seen: list[str] = []
    done = threading.Event()

    def watch():
        while not done.wait(poll):
            try:
                seen.extend(f"concurrent pytest pid={pid}" for pid, _ in dl.current_other_pytest())
            except dl.DevError as exc:
                seen.append(str(exc))

    with open(stdout_path, "w", encoding="utf-8") as out, open(f"{stdout_path}.stderr", "w", encoding="utf-8") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, text=True)
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        code = proc.wait()
        done.set()
        watcher.join()
    return code, sorted(set(seen))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--hold")
    parser.add_argument("--label", default="gate")
    parser.add_argument("--wait-max", type=float, default=1800.0)
    parser.add_argument("--keep-hold", action="store_true")
    parser.add_argument("--python")
    ns = parser.parse_args(argv)
    try:
        cwd = Path(ns.cwd).resolve()
        if ns.hold == "-":
            raise dl.DevError("the gate sets the hold flag; --hold - is not accepted here")
        flag = dl.hold_flag(ns.hold)
        python = ns.python or dl.venv_python(cwd)
    except dl.DevError as exc:
        print(f"gate: ERROR -- {exc}")
        return dl.ERROR
    if not create_flag(flag):
        print(f"gate: REFUSED -- hold flag already exists (another gate?): {flag}")
        return dl.REFUSED
    try:
        others = dl.wait_clear(None, ns.wait_max)
        if others:
            for r in others:
                print(f"gate: REFUSED -- {r}")
            return dl.REFUSED
        before = snapshot()
        log = dl.log_dir() / f"gate-{ns.label}-{dl.stamp()}.log"
        code, concurrent = run_watched([python, "-m", "pytest", *GATE_ARGS], cwd, log)
        changes = diff(before, snapshot())
        tally = dl.tally_line(log.read_text(encoding="utf-8"))
        ok, reasons = judge(code, tally)
        reasons += concurrent + changes
        ok = ok and not concurrent and not changes
        print(f"gate: {tally or '(no tally line)'}")
        print(f"gate: judge={'PASS' if ok else 'FAIL'}" + ("" if ok else f" ({', '.join(reasons)})"))
        print(f"gate: pg_database/pg_roles diff {'0' if not changes else ', '.join(changes)} | log={log}")
        return 0 if ok else 1
    except dl.DevError as exc:
        print(f"gate: ERROR -- {exc}")
        return dl.ERROR
    finally:
        if not ns.keep_hold:
            flag.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
