#!/usr/bin/env python3
"""pt.py -- guarded pytest run with a short report.

One call replaces the manual sequence: check the supervisor's gate-hold flag,
check `ps` for other pytest processes, run the shared-venv pytest in a
worktree, then `tail` the output (OPERATING_CONDITIONS 1.3-20, 1.6-42, 2-18).

Usage:
    tools/dev/pt.py [-C DIR] [--hold PATH|-] [--wait SECONDS] [--show N] -- <pytest args>

    -C DIR        directory to run in (default: current directory)
    --hold        gate-hold flag (default: $GATE_HOLD_FLAG, else $SP/gate-hold.flag;
                  `-` = this session has no supervisor gate)
    --wait        wait up to SECONDS for the blockers to clear (default 0)
    --python      interpreter (default: <main checkout>/.venv/bin/python)
    --show        FAILED/ERROR lines to print (default 20)

Also refuses while an unfinished mutation run's journal exists (mutate.py --recover).
Output: the tally line, up to --show FAILED/ERROR lines, then
`pt: exit=<code> log=<path>`; the full output is in the log ($SP/dev-logs/).
Exit: pytest's own code (0-5); 75 = refused to start; 78 = precondition error.
Run it in the foreground with the Bash timeout set to 600000 (1.6-42).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402


def guarded_run(cwd: Path, python: str, args: list[str], flag: Path | None, wait: float,
                show: int, out=sys.stdout, guard: bool = True) -> int:
    if guard:
        reasons = dl.wait_clear(flag, wait, root=cwd)
        if reasons:
            for r in reasons:
                print(f"pt: REFUSED -- {r}", file=out)
            return dl.REFUSED
    log = dl.log_dir() / f"pt-{dl.stamp()}.log"
    proc = subprocess.run([python, "-m", "pytest", *args], cwd=cwd, capture_output=True, text=True)
    log.write_text(proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
    print(f"pt: {dl.tally_line(proc.stdout) or '(no tally line)'}", file=out)
    for line in dl.failure_lines(proc.stdout, show):
        print(line, file=out)
    print(f"pt: exit={proc.returncode} log={log}", file=out)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--hold")
    parser.add_argument("--wait", type=float, default=0.0)
    parser.add_argument("--python")
    parser.add_argument("--show", type=int, default=20)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    args = ns.pytest_args[1:] if ns.pytest_args[:1] == ["--"] else ns.pytest_args
    try:
        cwd = Path(ns.cwd).resolve()
        flag = dl.hold_flag(ns.hold)
        python = ns.python or dl.venv_python(cwd)
        return guarded_run(cwd, python, args, flag, ns.wait, ns.show)
    except dl.DevError as exc:
        print(f"pt: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
