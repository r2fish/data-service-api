#!/usr/bin/env python3
"""mutate.py -- run a list of mutations with verified restores.

One call replaces, per mutation: back up, edit, run the tests, copy the
backup back, `sleep 3`, compare sha256 twice, grep the mutation string
(OPERATING_CONDITIONS 1.4-28..31).

Usage:
    tools/dev/mutate.py SPEC.json [-C DIR] [--wait SECONDS] [--python PY]
    tools/dev/mutate.py --recover [-C DIR]

SPEC.json:
    {
      "pytest": ["-q", "tools/tests/test_x.py"],          # default test args
      "mutations": [
        {"id": "M1", "file": "tools/x.py", "old": "if a:", "new": "if False:",
         "tests": ["tools/tests/test_x.py::test_a"], "expect": "red"},
        {"id": "M2", "expect": "red", "edits": [
            {"file": "r2db-api/src/r2db_api/a.py", "old": "...", "new": "..."},
            {"file": "MitateDB-api/src/mitatedb_api/a.py", "old": "...", "new": "..."}]}
      ]
    }

Each `old` must occur exactly once in the pristine file. Every mutation
starts from the pristine backup. `expect` is "red" (pytest exit code exactly
1, run with -x), "green" (exit code exactly 0), or "error" (exit code 2-5:
interrupted, internal error, usage error, or no tests collected -- something
broke the run itself rather than merely failing a test, e.g. a mutation that
keeps a conftest.py from starting its own cluster at all). The printed
`got=` field still shows pytest's own more specific outcome (`red` / `green`
/ `no-tests` / `error(N)`, unchanged); `expect: "error"` is satisfied by any
of exit codes 2-5, i.e. a `no-tests` (5) outcome counts as "error" too --
only `expect: "red"` requires exactly 1 and only `expect: "green"` requires
exactly 0 (WP-2, docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md
§3.1, following up on WP-1's `M13-no-lc-all`, whose exit 4 was reported as a
mismatch against `expect: "red"` even though it failed for exactly the
intended reason).

WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (c)):
`--wait` is how long each per-mutation pytest subprocess's own owned-mode
PostgreSQL cluster start-up waits for gate.py's exclusive suite lock to
clear (forwarded via `DSA_TEST_PG_LOCK_WAIT`, default 0). mutate.py takes no
lock of its own and no longer waits for a gate-hold flag or other pytest
processes before editing files: each subprocess's own conftest.py takes the
shared lock directly, so there is no double acquisition on the tool side.
If that wait times out, `dsa_testpg.TestPgError`'s own message is detected
in the captured output (review M-3, never guessed from the raw pytest exit
code, which is an ordinary-looking 2-4) and the run STOPS with REFUSED
(after restoring the mutation that hit it) instead of scoring that
mutation under any `expect` -- an infrastructure timeout is not a mutation
outcome, and under `expect: "error"` a raw exit code would otherwise wrongly
report it as OK.

Safety: before the first edit a journal (inside the worktree's git dir)
records the backups. SIGINT/SIGTERM/SIGHUP restore before exiting; further
signals are ignored while restoring. If the process is killed outright the
journal stays, pt.py / finalize.py / mutate.py refuse, and `--recover`
restores. A restore whose sha256 does not match the backup twice stops the
run. At the end every file is compared twice again and `git grep -F` counts
of each mutation line must equal their counts before the run.

Output: one line per mutation and a summary line; per-mutation pytest logs
and the backups are under $SP/dev-logs/mutate-<stamp>/. Large specs can
outlast the Bash timeout: run them with run_in_background.
Exit: 0 all as expected and restored; 1 an expectation not met; 70 restore
or final check failed; 75 refused to start; 78 precondition error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testpg"))
import dsa_testpg  # noqa: E402

SETTLE_SECONDS = 3.0  # OPERATING_CONDITIONS 1.4-30
_SIGNALS = [s for s in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s is not None]


class RestoreError(Exception):
    pass


def normalize(spec: dict) -> list[dict]:
    muts = []
    for i, m in enumerate(spec.get("mutations", [])):
        mid = m.get("id") or f"M{i + 1}"
        edits = m.get("edits") or [{"file": m.get("file"), "old": m.get("old"), "new": m.get("new")}]
        for e in edits:
            if not all(isinstance(e.get(k), str) for k in ("file", "old", "new")) or not e["old"] or e["old"] == e["new"]:
                raise dl.DevError(f"{mid}: each edit needs string file/old/new with a non-empty old != new")
        expect = m.get("expect", "red")
        if expect not in ("red", "green", "error"):
            raise dl.DevError(f"{mid}: expect must be red, green, or error")
        tests = m.get("tests") or spec.get("pytest")
        if not tests:
            raise dl.DevError(f"{mid}: no tests (set mutation 'tests' or top-level 'pytest')")
        muts.append({"id": mid, "edits": edits, "expect": expect, "tests": list(tests)})
    if not muts:
        raise dl.DevError("spec has no mutations")
    return muts


def by_file(edits: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for e in edits:
        grouped.setdefault(e["file"], []).append(e)
    return grouped


def apply_edits(text: str, edits: list[dict], mid: str) -> str:
    for e in edits:
        n = text.count(e["old"])
        if n != 1:
            raise dl.DevError(f"{mid}: 'old' occurs {n} times in {e['file']} (must be exactly 1)")
        text = text.replace(e["old"], e["new"], 1)
    return text


def needle(edit: dict, pristine_text: str) -> str | None:
    """What to grep for after the run: the longest line of `new` absent from the
    pristine file (git grep -F would split a multi-line pattern into lines)."""
    lines = [l for l in edit["new"].splitlines() if l.strip() and l not in pristine_text]
    return max(lines, key=len) if lines else None


def grep_count(root: Path, text: str) -> int:
    proc = subprocess.run(["git", "-C", str(root), "grep", "--untracked", "-c", "-F", "-e", text],
                          capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise dl.DevError(f"git grep failed: {proc.stderr.strip()}")
    return sum(int(line.rsplit(":", 1)[1]) for line in proc.stdout.splitlines() if ":" in line)


def classify(code: int) -> str:
    """The `got=` text printed per mutation -- unchanged by the addition of
    `expect: "error"` below (WP-2 §3.1): still the specific pytest outcome,
    never the coarser "error" bucket `matches()` checks expectations against."""
    return {0: "green", 1: "red", 5: "no-tests"}.get(code, f"error({code})")


_ERROR_CODES = (2, 3, 4, 5)  # pytest: interrupted, internal error, usage error, no tests collected


def matches(code: int, expect: str) -> bool:
    """Whether pytest's own exit `code` satisfies `expect`. `"red"` requires
    EXACTLY 1 and `"green"` EXACTLY 0 (never widened); `"error"` accepts any
    of `_ERROR_CODES` (2-5) -- a mutation that breaks the run itself (e.g.
    keeps a conftest.py from starting its own cluster at all, WP-1's `M13-
    no-lc-all`) is a real, intended "red" of a different shape than a failed
    test, and must not be reported as a mismatch just because pytest's own
    exit code for it is not literally 1."""
    if expect == "red":
        return code == 1
    if expect == "green":
        return code == 0
    if expect == "error":
        return code in _ERROR_CODES
    raise dl.DevError(f"unknown expect: {expect!r}")  # unreachable: normalize() already validated


def copy_back(root: Path, backups: Path, files) -> None:
    for f in files:
        shutil.copyfile(backups / f, root / f)


def mismatches(root: Path, files, base_hash: dict[str, str], settle: float) -> list[str]:
    """Files whose sha256 differs from the backup on either of two reads."""
    files = list(files)
    time.sleep(settle)
    first = {f: dl.sha256(root / f) for f in files}
    time.sleep(min(settle, 0.2))
    return [f for f in files if not (first[f] == dl.sha256(root / f) == base_hash[f])]


def recover(root: Path, out=sys.stdout, settle: float = SETTLE_SECONDS) -> int:
    journal = dl.journal_path(root)
    if not journal.exists():
        print("mutate: no unfinished mutation run", file=out)
        return 0
    data = json.loads(journal.read_text(encoding="utf-8"))
    files, backups = data["files"], Path(data["backups"])
    copy_back(root, backups, files)
    bad = mismatches(root, files, files, settle)
    if bad:
        print(f"mutate: RECOVER FAILED -- still differs from backup: {', '.join(bad)} (backups in {backups})", file=out)
        return dl.RESTORE_FAILED
    journal.unlink()
    print(f"mutate: recovered {len(files)} files from {backups}", file=out)
    return 0


def run(spec: dict, root: Path, python: str, out=sys.stdout,
        settle: float = SETTLE_SECONDS, work: Path | None = None, wait: float = 0.0) -> int:
    muts = normalize(spec)
    journal = dl.journal_path(root)
    if journal.exists():
        raise dl.DevError(f"an unfinished mutation run left {journal}; run tools/dev/mutate.py --recover first")
    files = sorted({e["file"] for m in muts for e in m["edits"]})
    for f in files:
        if not (root / f).is_file():
            raise dl.DevError(f"no such file: {f}")
    pristine = {f: (root / f).read_text(encoding="utf-8") for f in files}
    for m in muts:  # every edit must apply to pristine content before anything is touched
        for f, edits in by_file(m["edits"]).items():
            apply_edits(pristine[f], edits, m["id"])

    work = work or (dl.log_dir() / f"mutate-{dl.stamp()}")
    backups = work / "backups"
    base_hash = {}
    for f in files:  # backups mirror the relative path, so distinct files never collide
        (backups / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / f, backups / f)
        base_hash[f] = dl.sha256(backups / f)
    journal.write_text(json.dumps({"backups": str(backups), "files": base_hash}), encoding="utf-8")
    needles = sorted({n for m in muts for e in m["edits"] if (n := needle(e, pristine[e["file"]]))})
    no_needle = sum(1 for m in muts for e in m["edits"] if needle(e, pristine[e["file"]]) is None)
    base_grep = {n: grep_count(root, n) for n in needles}

    def on_signal(signum, frame):  # restore via the finally block below
        raise KeyboardInterrupt(f"signal {signum}")

    previous = {s: signal.getsignal(s) for s in _SIGNALS}
    for s in _SIGNALS[1:]:
        signal.signal(s, on_signal)
    dirty: set[str] = set()
    status = None
    met = 0
    completed = False
    try:
        for m in muts:
            grouped = by_file(m["edits"])
            for f, edits in grouped.items():
                dirty.add(f)
                (root / f).write_text(apply_edits(pristine[f], edits, m["id"]), encoding="utf-8")
            args = (["-x"] if m["expect"] == "red" else []) + m["tests"]
            # No .pyc writes: a restore in the same second as the mutated write, with the same
            # size, would otherwise let the mutated bytecode be reused by later runs.
            proc = subprocess.run([python, "-m", "pytest", *args], cwd=root, capture_output=True, text=True,
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                       dsa_testpg.ENV_LOCK_WAIT: str(wait)})
            combined = proc.stdout + proc.stderr
            (work / f"{m['id']}.log").write_text(combined, encoding="utf-8")
            copy_back(root, backups, grouped)
            bad = mismatches(root, grouped, base_hash, settle)
            if bad:
                raise RestoreError(f"restore mismatch for {', '.join(bad)} after {m['id']}")
            dirty.difference_update(grouped)
            if dl.lock_timeout_detected(combined, dl.tally_line(proc.stdout)):
                # review M-3: an environmental refusal (gate.py held the exclusive lock past
                # this mutation's own --wait budget) is not a mutation OUTCOME at all -- scoring
                # it under any `expect` (including the new "error" bucket, which a raw pytest
                # exit 2-4 would otherwise satisfy) would misreport an infrastructure timeout as
                # the mutation's own effect. Stop here, after this mutation's own restore, and
                # before every later mutation's file is ever touched (still pristine).
                print(f"mutate: STOPPED before {m['id']} -- exclusive suite lock wait timed out", file=out)
                status = dl.REFUSED
                break
            got = classify(proc.returncode)
            ok = matches(proc.returncode, m["expect"])
            met += ok
            print(f"{m['id']:<8} expect={m['expect']:<5} got={got:<9} {'OK ' if ok else 'NG '} "
                  f"| {dl.tally_line(proc.stdout) or '(no tally)'} | restore=ok", file=out)
        completed = True
    except RestoreError as exc:
        print(f"mutate: ABORT -- {exc}", file=out)
        status = dl.RESTORE_FAILED
        completed = True
    finally:
        for s in _SIGNALS:  # a second signal must not cut the restore short
            signal.signal(s, signal.SIG_IGN)
        try:
            if dirty:
                copy_back(root, backups, sorted(dirty))
                bad = mismatches(root, sorted(dirty), base_hash, settle)
                if bad:
                    print(f"mutate: RESTORE FAILED -- {', '.join(bad)}; journal kept: {journal}", file=out)
                    status = dl.RESTORE_FAILED
                else:
                    print(f"mutate: restored {', '.join(sorted(dirty))} after interruption", file=out)
                    journal.unlink(missing_ok=True)
                    dirty.clear()
            elif not completed:  # interrupted while every file was pristine (verified or never edited)
                journal.unlink(missing_ok=True)
        finally:
            for s, handler in previous.items():
                signal.signal(s, handler)

    bad = mismatches(root, files, base_hash, settle)
    grep_changed = [n for n in needles if grep_count(root, n) != base_grep[n]]
    for f in bad:
        print(f"mutate: FINAL CHECK -- {f} differs from its backup; journal kept: {journal}", file=out)
    for n in grep_changed:
        print(f"mutate: FINAL CHECK -- mutation line count changed: {n[:60]!r}", file=out)
    if not bad:
        journal.unlink(missing_ok=True)
    grep_note = "unchanged" if not grep_changed else "CHANGED"
    if no_needle:
        grep_note += f" (n/a for {no_needle} edits whose lines all exist in the pristine file)"
    print(f"mutate: {len(muts)} mutations, {met} as expected, restores verified {len(files) - len(bad)}/{len(files)} files "
          f"(sha256 x2), grep counts {grep_note} | logs={work}", file=out)
    if bad or grep_changed:
        return dl.RESTORE_FAILED
    if status is not None:
        return status
    return 0 if met == len(muts) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("spec", nargs="?")
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--python")
    parser.add_argument("--wait", type=float, default=0.0)
    parser.add_argument("--recover", action="store_true")
    ns = parser.parse_args(argv)
    try:
        root = dl.worktree_root(Path(ns.cwd).resolve())
        if ns.recover:
            return recover(root)
        if not ns.spec:
            raise dl.DevError("SPEC.json is required (or --recover)")
        spec = json.loads(Path(ns.spec).read_text(encoding="utf-8"))
        python = ns.python or dl.venv_python(root)
        return run(spec, root, python, wait=ns.wait)
    except (dl.DevError, json.JSONDecodeError, OSError) as exc:
        print(f"mutate: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
