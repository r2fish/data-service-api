#!/usr/bin/env python3
"""finalize.py -- commit a worktree's changes and merge them into main.

Replaces the per-change `finalize_*.sh` scripts: branch check, path
allowlist, empty-.md check, doc-refs and public-value scans, commit,
optional tools/tests at the new HEAD, `--no-ff` merge into main, and
fast-forwarding the worktree (OPERATING_CONDITIONS 1.1-12a, 1.2, 1.9, 2-15).

Usage:
    tools/dev/finalize.py -C WORKTREE --branch NAME --allow GLOB [--allow GLOB ...] -m MSGFILE
                          [--check "CMD" ...] [--tools-tests] [--hold PATH|-] [--no-merge]

    --allow        every changed path (tracked or untracked) must match one glob
                   (fnmatch: `*` also matches `/`)
    -m MSGFILE     full commit message; its Co-Authored-By lines are copied to the merge commit
    --check        extra shell command run in the worktree before committing; non-zero stops
    --tools-tests  run `pytest -q tools/tests` (guarded, as pt.py) at the new HEAD before merging
    --leave GLOB   changed paths matching GLOB stay uncommitted (to split one worktree's changes
                   into several commits: e.g. `--no-merge --leave 'r2db-api/*'`, then a second call)

Only the listed paths are added (never `git add -A`). Author and committer
(`git var`) must use GitHub noreply addresses. The branch and HEAD are checked
again right before the commit, and main merges the commit's SHA, not the
branch name. On a merge conflict the merge is aborted and main is left as it was.
Refuses while an unfinished mutation run's journal exists.
Exit: 0 committed (and merged); 1 a check failed, nothing committed;
76 committed but not merged (or merged but the worktree not fast-forwarded;
the output says which); 78 precondition error, nothing committed.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

NOREPLY_SUFFIX = "@users.noreply.github.com"


class CheckFailed(Exception):
    pass


def changed_paths(wt: Path) -> list[str]:
    raw = dl.git(wt, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
    return sorted({entry[3:] for entry in raw.split("\0") if len(entry) > 3})


def ident_email(wt: Path, var: str) -> str:
    m = re.search(r"<([^>]*)>", dl.git(wt, "var", var))
    return m.group(1) if m else ""


def run_check(wt: Path, argv: list[str] | str, label: str, out) -> None:
    proc = subprocess.run(argv, cwd=wt, capture_output=True, text=True, shell=isinstance(argv, str))
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    print(f"finalize: {label}: {lines[-1] if lines else ''}", file=out)
    if proc.returncode != 0:
        raise CheckFailed(f"{label} exited {proc.returncode}")


def finalize(wt: Path, branch: str, allow: list[str], msgfile: Path, checks: list[str],
             tools_tests: bool, flag: Path | None, merge: bool, python: str, out=sys.stdout,
             repo_checks: bool = True, leave: list[str] = ()) -> int:
    wt = dl.worktree_root(wt)
    if dl.journal_path(wt).exists():
        raise dl.DevError(f"unfinished mutation run in this worktree ({dl.journal_path(wt)}); run mutate.py --recover")
    current = dl.git(wt, "branch", "--show-current").strip()
    if current != branch:
        raise dl.DevError(f"worktree is on {current!r}, not {branch!r}")
    head = dl.git(wt, "rev-parse", "HEAD").strip()
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        if not ident_email(wt, var).endswith(NOREPLY_SUFFIX):
            raise dl.DevError(f"{var} does not use a GitHub noreply address")
    message = msgfile.read_text(encoding="utf-8")
    if not message.strip():
        raise dl.DevError("commit message file is empty")

    all_paths = changed_paths(wt)
    left = [p for p in all_paths if any(fnmatch.fnmatch(p, g) for g in leave)]
    paths = [p for p in all_paths if p not in left]
    if not paths:
        raise dl.DevError("nothing to commit")
    if left:
        print(f"finalize: left uncommitted by --leave: {len(left)} paths", file=out)
    outside = [p for p in paths if not any(fnmatch.fnmatch(p, g) for g in allow)]
    for p in outside:
        print(f"finalize: not allowed: {p}", file=out)
    if outside:
        return 1
    empty_md = [p for p in paths if p.endswith(".md") and (wt / p).is_file() and (wt / p).stat().st_size == 0]
    for p in empty_md:
        print(f"finalize: zero-byte .md (Drive sync hazard): {p}", file=out)
    if empty_md:
        return 1

    try:
        if repo_checks:
            run_check(wt, [python, "tools/check_doc_refs.py"], "check_doc_refs", out)
            existing = [p for p in paths if (wt / p).is_file()]
            if existing:
                run_check(wt, [python, "tools/public_value_scan.py", *existing], "public_value_scan", out)
        for cmd in checks:
            run_check(wt, cmd, f"check `{cmd[:50]}`", out)
    except CheckFailed as exc:
        print(f"finalize: STOP -- {exc}; nothing committed", file=out)
        return 1

    # Shared-checkout rule: confirm branch and HEAD again immediately before committing.
    if dl.git(wt, "symbolic-ref", "--short", "HEAD").strip() != branch or dl.git(wt, "rev-parse", "HEAD").strip() != head:
        raise dl.DevError("branch or HEAD moved during the checks; nothing committed")
    if changed_paths(wt) != all_paths:
        print("finalize: STOP -- the changed-path set moved during the checks; nothing committed", file=out)
        return 1
    dl.git(wt, "add", "--", *paths)
    unstaged = dl.git(wt, "diff", "--name-only").splitlines() + dl.git(wt, "ls-files", "--others", "--exclude-standard").splitlines()
    if [p for p in unstaged if p not in left]:
        print("finalize: STOP -- changes outside the staged set; paths are staged, nothing committed", file=out)
        return 1
    stat = dl.git(wt, "diff", "--cached", "--stat").strip().splitlines()
    print(f"finalize: staged {len(paths)} paths | {stat[-1] if stat else ''}", file=out)
    proc = subprocess.run(["git", "-C", str(wt), "commit", "-q", "-F", str(msgfile)], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"finalize: STOP -- commit failed ({proc.stderr.strip()[:200]}); paths are staged, nothing committed", file=out)
        return 1
    sha = dl.git(wt, "rev-parse", "HEAD").strip()
    print(f"finalize: committed {dl.git(wt, 'log', '-1', '--format=%h %s').strip()[:100]}", file=out)

    def partial(reason: str, merged: bool) -> int:
        print(f"finalize: STOP -- {reason}; committed {sha[:7]}, merged={'yes' if merged else 'no'}", file=out)
        return dl.PARTIAL

    try:
        if tools_tests:
            reasons = dl.blockers(flag)
            if reasons:
                return partial(f"tools/tests refused ({reasons[0]})", False)
            proc = subprocess.run([python, "-m", "pytest", "-q", "tools/tests"], cwd=wt, capture_output=True, text=True)
            print(f"finalize: tools/tests: {dl.tally_line(proc.stdout)}", file=out)
            if proc.returncode != 0:
                for line in dl.failure_lines(proc.stdout, 10):
                    print(line, file=out)
                return partial("tools/tests red at the new HEAD", False)
        if not merge:
            return 0

        main_root = dl.main_checkout(wt)
        if dl.git(main_root, "branch", "--show-current").strip() != "main":
            return partial("main checkout is not on main", False)
        if dl.git(main_root, "status", "--porcelain").strip():
            return partial("main checkout is not clean", False)
        subject = message.strip().splitlines()[0]
        tail = " [skip ci]" if "[skip ci]" in subject else ""
        subject = subject.replace("[skip ci]", "").strip()
        trailers = [l for l in message.splitlines() if l.lower().startswith("co-authored-by:")]
        merge_msg = f"Merge {branch}: {subject}{tail}" + ("\n\n" + "\n".join(trailers) if trailers else "")
        proc = subprocess.run(["git", "-C", str(main_root), "merge", "-q", "--no-ff", sha, "-m", merge_msg],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["git", "-C", str(main_root), "merge", "--abort"], capture_output=True)
            return partial(f"merge failed and was aborted: {proc.stderr.strip()[:200]}", False)
        print(f"finalize: main {dl.git(main_root, 'log', '-1', '--format=%h %s').strip()[:100]}", file=out)
        proc = subprocess.run(["git", "-C", str(wt), "merge", "-q", "--ff-only", "main"], capture_output=True, text=True)
        if proc.returncode != 0:
            return partial(f"worktree not fast-forwarded to main: {proc.stderr.strip()[:200]}", True)
        print(f"finalize: worktree now {dl.git(wt, 'rev-parse', '--short', 'HEAD').strip()}", file=out)
        return 0
    except dl.DevError as exc:
        return partial(str(exc), False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--allow", action="append", required=True)
    parser.add_argument("-m", dest="msgfile", required=True)
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--tools-tests", action="store_true")
    parser.add_argument("--hold")
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--leave", action="append", default=[])
    parser.add_argument("--python")
    ns = parser.parse_args(argv)
    try:
        wt = Path(ns.cwd).resolve()
        flag = dl.hold_flag(ns.hold) if ns.tools_tests else None
        python = ns.python or dl.venv_python(wt)
        return finalize(wt, ns.branch, ns.allow, Path(ns.msgfile), ns.check, ns.tools_tests, flag,
                        not ns.no_merge, python, leave=ns.leave)
    except dl.DevError as exc:
        print(f"finalize: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
