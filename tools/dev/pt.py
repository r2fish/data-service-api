#!/usr/bin/env python3
"""pt.py -- guarded pytest run with a short report.

One call replaces the manual sequence: check for an unfinished mutation
journal, run the shared-venv pytest in a worktree, then `tail` the output
(OPERATING_CONDITIONS 1.6-42).

Usage:
    tools/dev/pt.py [-C DIR] [--wait SECONDS] [--show N] -- <pytest args>

    -C DIR        directory to run in (default: current directory)
    --wait        WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md
                  §3.1 (c)): how long the pytest subprocess's own owned-mode
                  PostgreSQL cluster start-up (`conftest.py` ->
                  `dsa_testpg.ensure_for_pytest()`) waits for gate.py's
                  exclusive suite lock to clear, forwarded via
                  `DSA_TEST_PG_LOCK_WAIT` (default 0 -- refuse immediately if
                  a gate is running). pt.py itself takes no lock of its own:
                  the pytest subprocess takes the shared lock directly, so
                  there is no double acquisition on the tool side.
    --python      interpreter (default: <main checkout>/.venv/bin/python)
    --show        FAILED/ERROR lines to print (default 20)

Also refuses while an unfinished mutation run's journal exists (mutate.py --recover).
Also converts a lock-wait timeout to REFUSED: if the pytest subprocess's own
owned-mode conftest.py could not get the exclusive suite lock to clear within
`--wait` (review M-3, WP-2 §3.1 (a)/(c) -- "道具側は REFUSED 75 に変換する"),
that is detected from `dsa_testpg.TestPgError`'s own message in the captured
output, never guessed from the raw pytest exit code alone (which would
otherwise be an ordinary-looking 2-4, indistinguishable from a real failure).
Output: the tally line, up to --show FAILED/ERROR lines, then
`pt: exit=<code> log=<path>`; the full output is in the log ($SP/dev-logs/).
Exit: pytest's own code (0-5); 75 = refused to start (including a lock-wait
timeout); 78 = precondition error.
Run it in the foreground with the Bash timeout set to 600000 (1.6-42).

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: whether the args select what a WP claims to have
       run -- pt.py runs exactly what it is handed and judges nothing.
       why: its exit code is pytest's own; the PASS/FAIL rule lives in
       gate.py (OPERATING_CONDITIONS 1.3-19..22).
       caught by: gate.py's own root-suite run, and the reviewer
       checking the args against the WP's own verification method.
    2. not detected: FAILED/ERROR lines beyond `--show N` on stdout.
       why: only the first N such lines are printed.
       caught by: the complete output at the printed `log=` path.
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


def guarded_run(cwd: Path, python: str, args: list[str], wait: float,
                show: int, out=sys.stdout, guard: bool = True) -> int:
    if guard:
        blocker = dl.journal_blocker(cwd)
        if blocker:
            print(f"pt: REFUSED -- {blocker}", file=out)
            return dl.REFUSED
    log = dl.log_dir() / f"pt-{dl.stamp()}.log"
    env = {**os.environ, dsa_testpg.ENV_LOCK_WAIT: str(wait)}
    proc = subprocess.run([python, "-m", "pytest", *args], cwd=cwd, capture_output=True, text=True, env=env)
    combined = proc.stdout + proc.stderr
    log.write_text(proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
    tally = dl.tally_line(proc.stdout)
    if dl.lock_timeout_detected(combined, tally):
        print(f"pt: REFUSED -- exclusive suite lock wait timed out (log={log})", file=out)
        return dl.REFUSED
    print(f"pt: {tally or '(no tally line)'}", file=out)
    for line in dl.failure_lines(proc.stdout, show):
        print(line, file=out)
    print(f"pt: exit={proc.returncode} log={log}", file=out)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--wait", type=float, default=0.0)
    parser.add_argument("--python")
    parser.add_argument("--show", type=int, default=20)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    args = ns.pytest_args[1:] if ns.pytest_args[:1] == ["--"] else ns.pytest_args
    try:
        cwd = Path(ns.cwd).resolve()
        python = ns.python or dl.venv_python(cwd)
        return guarded_run(cwd, python, args, ns.wait, ns.show)
    except dl.DevError as exc:
        print(f"pt: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
