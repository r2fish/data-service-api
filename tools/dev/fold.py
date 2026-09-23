#!/usr/bin/env python3
"""fold.py -- fold merged-into-main linked worktrees and local branches.

Linked worktrees and their branches pile up once a WP is merged: nothing
removes them automatically, so their count only grows (29 worktrees, 90
branches at the time this was written). This replaces walking `git
worktree list` / `git branch` by hand and deciding, one by one, which are
now safe to remove. Never touches a remote branch. Standard library only;
tests in tools/tests/test_dev_tools.py.

Usage:
    tools/dev/fold.py [-C PATH] [--apply] [--include GLOB ...]
                      [--min-age-hours N] [--main NAME] [--wait SECONDS]
                      [--verbose]

    -C PATH          where to run (default: current directory); git
                     operations run in the main checkout found from here
                     (`_devlib.main_checkout`)
    --apply          actually remove; default is dry-run (nothing changes)
    --include GLOB   fnmatch glob matched against a branch name; a branch
                     that matches a default exclusion (`claude/*` -- other
                     chats' session worktrees) is still folded if it also
                     matches one of these
    --min-age-hours  how long since the last activity before folding
                     (default 24; see note (c) below)
    --main NAME      the branch "merged" is checked against (default main)
    --wait           longest wait for the exclusive suite lock that
                     --apply takes (default 0 -- refuse immediately rather
                     than block a run someone else may be waiting on)
    --verbose        also print every SKIP line (default: counts only)

A worktree is FOLDed when ALL of, checked in this order: it is not the
main checkout and not the worktree `-C` points into; HEAD is not
detached; it is not locked; its branch does not match a default exclusion
(unless overridden by --include); its branch tip -- re-read with `git
rev-parse HEAD` at decision time, not the `git worktree list` snapshot
taken at the start of this run -- is an ancestor of --main; `git status`
(untracked and ignored files included) shows nothing except possibly
ignored files whose own last path element is a known build artifact
(`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.DS_Store`, `*.pyc`,
`*.egg-info`, or the worktree's own `.claude/settings.local.json` -- anything else,
e.g. a stray `.env` or log file, is left alone rather than silently
discarded); no unfinished mutate.py journal (`_devlib.journal_blocker`);
and its last activity -- the newest mtime among its git-dir's own HEAD /
logs/HEAD (only the ones that exist), or the tip commit's own committer
date if neither exists -- is at least --min-age-hours old. A worktree the
porcelain output itself marks `prunable` (its directory is gone, possibly
only because a synced drive has not caught up -- never pruned
automatically here) is counted as PRUNABLE instead and never inspected
further; nothing runs `git worktree prune` -- do that by hand once you
know the listing is really stale.

A local branch with no worktree is FOLDed when it is not --main, does not
match a default exclusion (unless overridden), its tip is an ancestor of
--main, and its own reflog file
(`<git-common-dir>/logs/refs/heads/<name>`) is at least --min-age-hours
old, or (missing entirely) its own commit is that old.

--apply never runs `git worktree remove --force` or `git branch -d`:
removal only starts after every FOLD condition above already held, and
the branch delete re-confirms -- immediately before `git branch -D` --
that the branch's tip is still the same and still an ancestor of --main;
`-D` is used only because that fresh check is the actual safety, not
`-d`'s own (an upstream setting can make `-d` refuse a genuinely safe
delete). A precondition failure while deciding or applying one item (a
`_devlib.DevError`, e.g. a `git` command failing outright) is reported as
a FAIL line for that item and never stops the run.

--apply runs the whole enumerate-then-remove pass inside the exclusive
suite lock (`tools/testpg/dsa_testpg.suite_lock`, the same one gate.py /
perf_baseline.py take) so it can never remove a worktree a concurrently
running pytest still needs; if the lock cannot be taken within --wait the
run REFUSES (exit 75) and changes nothing. Dry-run never takes the lock.

Output: one line per item, `fold: FOLD|SKIP|PRUNABLE|FAIL worktree|branch
NAME [reason]`. SKIP lines are counted (one reason-breakdown line) but
not printed individually unless --verbose. Final summary line: `fold:
dry-run|applied worktrees=N branches=N prunable=N skipped=N failed=N`.
Exit: 0 no FAIL; 1 at least one FAIL (dry-run or --apply alike); 75
--apply could not get the exclusive suite lock within --wait (nothing
changed); 78 precondition error before any item was even looked at.

Safety notes:
    (a) The guardrails above (merged, clean-or-only-artifact-ignored, no
        journal, old enough, and for --apply the suite lock) do not know
        about another chat's own worktree that is simply sitting open,
        not yet edited: if it is already clean and old enough, it can be
        folded -- nothing of that chat's own is lost (clean means there
        was nothing uncommitted to begin with), but the worktree itself
        disappears out from under it.
    (b) `-C` defaults to the current directory, and the "current" guard
        only ever protects the ONE worktree `-C` resolves into. Running
        this from the main checkout itself protects the main checkout,
        not any other worktree someone else may be sitting in.
    (c) `--min-age-hours 0` removes the only guard against (a)/(b): use it
        only when the supervisor already knows, by name, everything the
        run would otherwise be old enough to touch.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: another chat's own clean, old-enough worktree that
       is merely sitting open, and the `-C`-only "current" guard -- see
       Safety notes (a)-(c) above.
       why: same notes; merged + clean + old enough + (for --apply) the
       suite lock are the whole guard set.
       caught by: the supervisor reading the dry-run list by name before
       `--apply` (accepted: that reading is the actual guard).
    2. not detected: whether a folded branch's work also reached the
       remote -- ancestry is checked against the LOCAL --main only.
       why: no remote ref is ever read (and no remote branch is ever
       touched).
       caught by: accepted -- a local branch is folded only after its
       merge into the local main, and remote branches are kept.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testpg"))
import dsa_testpg  # noqa: E402

DEFAULT_MIN_AGE_HOURS = 24.0
DEFAULT_WAIT = 0.0
DEFAULT_EXCLUDES = ("claude/*",)
ACTIVITY_FILES = ("HEAD", "logs/HEAD")  # R1: index dropped -- see worktree_status()
ALLOWED_IGNORED_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store")
ALLOWED_IGNORED_PATTERNS = ("*.pyc", "*.egg-info")


# ---------------------------------------------------------------------------
# Enumeration: `git worktree list --porcelain` and `git for-each-ref`
# ---------------------------------------------------------------------------

def parse_worktrees(porcelain: str) -> list[dict]:
    """One dict per worktree entry (blank-line separated records)."""
    entries: list[dict] = []
    cur: dict = {}
    for line in porcelain.splitlines():
        if not line:
            if cur:
                entries.append(cur)
                cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": val, "branch": None, "detached": False, "locked": False, "prunable": False}
        elif key == "branch":
            cur["branch"] = val[len("refs/heads/"):] if val.startswith("refs/heads/") else val
        elif key == "detached":
            cur["detached"] = True
        elif key == "locked":
            cur["locked"] = True
        elif key == "prunable":
            cur["prunable"] = True
    if cur:
        entries.append(cur)
    return entries


def list_branches(main_root: Path) -> dict[str, str]:
    """`{branch name: tip sha}` for every local branch (never a remote one)."""
    out = dl.git(main_root, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    branches = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, sha = line.partition(" ")
        branches[name] = sha
    return branches


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def is_excluded(name: str, includes: list[str]) -> bool:
    """True when `name` matches a default exclusion AND does not also match
    any --include glob (an --include only ever lifts a default exclusion,
    it never adds one)."""
    for pattern in DEFAULT_EXCLUDES:
        if fnmatch.fnmatchcase(name, pattern) and not any(fnmatch.fnmatchcase(name, inc) for inc in includes):
            return True
    return False


def is_ancestor(root: Path, tip: str, main_branch: str) -> bool:
    if not tip:
        return False
    proc = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", tip, main_branch],
                          capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise dl.DevError(f"git merge-base --is-ancestor failed: {proc.stderr.strip()}")
    return proc.returncode == 0


def _is_allowed_ignored(path_field: str) -> bool:
    """R2: an ignored path is tolerated only when its own last path element
    is a known build-artifact name/pattern, or it is the per-worktree copy of
    `.claude/settings.local.json` -- anything else (a stray `.env`, a log
    file, ...) must never be silently thrown away with the worktree it
    happens to sit in."""
    stripped = path_field.rstrip("/")
    name = stripped.rsplit("/", 1)[-1]
    return (name in ALLOWED_IGNORED_NAMES
            or any(fnmatch.fnmatchcase(name, pat) for pat in ALLOWED_IGNORED_PATTERNS)
            or stripped == ".claude/settings.local.json")


def worktree_status(path: Path) -> tuple[bool, bool]:
    """(dirty, has_disallowed_ignored) from a single `git status` read.
    R1: `--no-optional-locks` -- a plain `git status` can itself write the
    index (a "racily clean" stat-cache refresh), which would stamp its
    mtime with "now" and silently defeat a later mtime-based recency
    check; `--no-optional-locks` makes this read skip that write instead
    of blocking on/competing for the index lock."""
    out = dl.git(path, "--no-optional-locks", "status", "--porcelain", "--untracked-files=all", "--ignored=matching")
    dirty = False
    bad_ignored = False
    for line in out.splitlines():
        if not line:
            continue
        code, path_field = line[:2], line[3:]
        if code == "!!":
            if not _is_allowed_ignored(path_field):
                bad_ignored = True
        else:
            dirty = True
    return dirty, bad_ignored


def worktree_git_dir(path: Path) -> Path:
    return Path(dl.git(path, "rev-parse", "--path-format=absolute", "--git-dir").strip())


def last_activity(git_dir: Path) -> float | None:
    """Newest mtime among the git-dir's own HEAD / logs/HEAD, or None if
    neither exists."""
    times = [(git_dir / rel).stat().st_mtime for rel in ACTIVITY_FILES if (git_dir / rel).exists()]
    return max(times) if times else None


def committer_date(root: Path, sha: str) -> float:
    """R5: what a missing activity file / reflog file falls back to -- the
    tip commit's own committer date, rather than treating a merely-absent
    file as infinitely old."""
    return float(dl.git(root, "log", "-1", "--format=%ct", sha).strip())


def is_recent(mtime: float | None, min_age_hours: float, now: float) -> bool:
    """None (no timestamp resolved) is never "recent" -- normal callers
    always resolve a fallback first (R5: `committer_date`) before calling
    this, but a None here degrades safely to "old enough" rather than
    crashing the whole run."""
    return mtime is not None and (now - mtime) < min_age_hours * 3600


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def decide_worktree(entry: dict, main_path: Path, current_path: Path, main_branch: str, main_root: Path,
                    includes: list[str], min_age_hours: float, now: float) -> tuple[str, str]:
    if entry.get("prunable"):
        return "PRUNABLE", ""
    path = Path(entry["path"])
    resolved = path.resolve() if path.exists() else path
    if resolved == main_path:
        return "SKIP", "main-checkout"
    if resolved == current_path:
        return "SKIP", "current"
    if entry.get("detached") or not entry.get("branch"):
        return "SKIP", "detached"
    if entry.get("locked"):
        return "SKIP", "locked"
    branch = entry["branch"]
    if is_excluded(branch, includes):
        return "SKIP", "excluded"
    # R6: re-read now, not the `git worktree list` snapshot taken at the start
    # of this run -- narrows the window between enumeration and --apply.
    tip = dl.git(path, "rev-parse", "HEAD").strip()
    if not is_ancestor(main_root, tip, main_branch):
        return "SKIP", "unmerged"
    dirty, bad_ignored = worktree_status(path)
    if dirty:
        return "SKIP", "dirty"
    if bad_ignored:
        return "SKIP", "ignored-files"
    if dl.journal_blocker(path):
        return "SKIP", "mutation-journal"
    activity = last_activity(worktree_git_dir(path))
    if activity is None:  # R5: neither HEAD nor logs/HEAD exists
        activity = committer_date(main_root, tip)
    if is_recent(activity, min_age_hours, now):
        return "SKIP", "recent"
    return "FOLD", ""


def decide_branchless(name: str, sha: str, main_branch: str, main_root: Path, includes: list[str],
                      min_age_hours: float, now: float, common_dir: Path) -> tuple[str, str]:
    if name == main_branch:
        return "SKIP", "main-branch"
    if is_excluded(name, includes):
        return "SKIP", "excluded"
    if not is_ancestor(main_root, sha, main_branch):
        return "SKIP", "unmerged"
    log_path = common_dir / "logs" / "refs" / "heads" / name
    mtime = log_path.stat().st_mtime if log_path.exists() else None
    if mtime is None:  # R5: no reflog file
        mtime = committer_date(main_root, sha)
    if is_recent(mtime, min_age_hours, now):
        return "SKIP", "recent"
    return "FOLD", ""


# ---------------------------------------------------------------------------
# --apply actions
# ---------------------------------------------------------------------------

def apply_branch_delete(main_root: Path, branch: str, main_branch: str) -> tuple[bool, str]:
    """Re-confirms the tip is unchanged and still an ancestor of --main
    immediately before `git branch -D` -- that fresh check, not `-d`'s own
    upstream-aware refusal, is the actual safety for using `-D`."""
    tip = dl.git(main_root, "rev-parse", branch, check=False).strip()
    if not tip or not is_ancestor(main_root, tip, main_branch):
        return False, "branch moved or is no longer an ancestor of main just before delete"
    proc = subprocess.run(["git", "-C", str(main_root), "branch", "-D", branch], capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"branch -D failed: {proc.stderr.strip()[:160]}"
    return True, ""


def apply_worktree_fold(main_root: Path, path: Path, branch: str, main_branch: str) -> tuple[bool, str]:
    proc = subprocess.run(["git", "-C", str(main_root), "worktree", "remove", str(path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"worktree remove failed: {proc.stderr.strip()[:160]}"
    return apply_branch_delete(main_root, branch, main_branch)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _run(root: Path, apply: bool, includes: list[str], min_age_hours: float, main_branch: str,
        out, verbose: bool, now: float | None) -> int:
    main_root = dl.main_checkout(root)
    current_root = dl.worktree_root(root)
    now = now if now is not None else time.time()
    main_path = main_root.resolve()
    current_path = current_root.resolve()

    porcelain = dl.git(main_root, "worktree", "list", "--porcelain")
    entries = parse_worktrees(porcelain)
    common_dir = Path(dl.git(main_root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    branches = list_branches(main_root)
    worktree_branches = {e["branch"] for e in entries if e.get("branch")}

    skip_reasons: dict[str, int] = {}
    prunable = folded_wt = folded_br = failed = 0

    def skip(kind: str, name: str, reason: str) -> None:
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        if verbose:
            print(f"fold: SKIP {kind} {name} {reason}", file=out)

    for entry in entries:
        path = entry["path"]
        try:
            action, reason = decide_worktree(entry, main_path, current_path, main_branch, main_root,
                                             includes, min_age_hours, now)
        except dl.DevError as exc:  # R7: one item's precondition failure never stops the run
            failed += 1
            print(f"fold: FAIL worktree {path} {str(exc)[:160]}", file=out)
            continue
        if action == "PRUNABLE":
            prunable += 1
            print(f"fold: PRUNABLE worktree {path}", file=out)
        elif action == "SKIP":
            skip("worktree", path, reason)
        elif apply:
            try:
                ok, fail_reason = apply_worktree_fold(main_root, Path(path), entry["branch"], main_branch)
            except dl.DevError as exc:
                ok, fail_reason = False, str(exc)[:160]
            if ok:
                folded_wt += 1
                print(f"fold: FOLD worktree {path}", file=out)
            else:
                failed += 1
                print(f"fold: FAIL worktree {path} {fail_reason}", file=out)
        else:
            folded_wt += 1
            print(f"fold: FOLD worktree {path}", file=out)

    for name in sorted(branches):
        if name in worktree_branches:
            continue
        try:
            action, reason = decide_branchless(name, branches[name], main_branch, main_root, includes,
                                               min_age_hours, now, common_dir)
        except dl.DevError as exc:
            failed += 1
            print(f"fold: FAIL branch {name} {str(exc)[:160]}", file=out)
            continue
        if action == "SKIP":
            skip("branch", name, reason)
        elif apply:
            try:
                ok, fail_reason = apply_branch_delete(main_root, name, main_branch)
            except dl.DevError as exc:
                ok, fail_reason = False, str(exc)[:160]
            if ok:
                folded_br += 1
                print(f"fold: FOLD branch {name}", file=out)
            else:
                failed += 1
                print(f"fold: FAIL branch {name} {fail_reason}", file=out)
        else:
            folded_br += 1
            print(f"fold: FOLD branch {name}", file=out)

    if skip_reasons:
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(skip_reasons.items()))
        print(f"fold: skipped breakdown: {breakdown}", file=out)
    mode = "applied" if apply else "dry-run"
    skipped = sum(skip_reasons.values())
    print(f"fold: {mode} worktrees={folded_wt} branches={folded_br} prunable={prunable} "
         f"skipped={skipped} failed={failed}", file=out)
    return 1 if failed else 0


def fold(root: Path, apply: bool, includes: list[str], min_age_hours: float, main_branch: str,
         out=sys.stdout, verbose: bool = False, now: float | None = None, wait: float = DEFAULT_WAIT) -> int:
    """R3: dry-run never takes the suite lock (returns straight from
    `_run`); --apply runs the WHOLE enumerate-then-remove pass
    (`_run`) inside it, so nothing here can remove a worktree a
    concurrently running pytest still needs. `dsa_testpg.suite_lock` is
    the module attribute tests monkeypatch (same idiom as gate.py's own
    `dsa_testpg.cluster` / `dsa_testpg.suite_lock` patches)."""
    if not apply:
        return _run(root, apply, includes, min_age_hours, main_branch, out, verbose, now)
    try:
        with dsa_testpg.suite_lock(exclusive=True, wait=wait):
            return _run(root, apply, includes, min_age_hours, main_branch, out, verbose, now)
    except dsa_testpg.TestPgError as exc:
        print(f"fold: REFUSED -- {exc}", file=out)
        return dl.REFUSED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--min-age-hours", type=float, default=DEFAULT_MIN_AGE_HOURS)
    parser.add_argument("--main", dest="main_branch", default="main")
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT)
    parser.add_argument("--verbose", action="store_true")
    ns = parser.parse_args(argv)
    try:
        root = Path(ns.cwd).resolve()
        return fold(root, ns.apply, ns.include, ns.min_age_hours, ns.main_branch, verbose=ns.verbose, wait=ns.wait)
    except dl.DevError as exc:
        print(f"fold: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
