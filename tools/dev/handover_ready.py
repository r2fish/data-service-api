#!/usr/bin/env python3
"""handover_ready.py -- is this a safe boundary to move to a new chat?

Checks the conditions of OPERATING_CONDITIONS 1.10-67 and, once they hold
and the handover document is committed on main, prints the continuation
prompt to pass to spawn_task (it carries the marker turn_budget_hook.py
watches for, which stops its reminders).

Usage:
    tools/dev/handover_ready.py [-C DIR] --no-running-agents [--worktree PATH ...]
                                [--handover PATH]

    --no-running-agents  the chat states that no subagent or background task of its own is
                         still running (not machine-checkable; required, so it is said explicitly)
    --worktree PATH      a worktree this chat worked in: must be clean with its HEAD in main
    --handover PATH      handover document (repository-relative); must exist in main's tree

Checks: the statement above; gate not running (WP-2, docs/work-orders/
WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (c): replaces the former "no
pytest process" + "gate-hold flag absent" pair with `dsa_testpg.gate_running()`
-- true when `gate.intent` is present or the exclusive suite lock cannot be
taken without blocking, which also covers "some pytest run is still active"
since every owned-mode run holds that lock's shared side); the main checkout
on main and clean; no unfinished mutation journal in any worktree; each
--worktree clean and merged; the handover document committed on main.
Output: one line per check, then READY or NOT READY; with --handover and READY,
the continuation prompt between BEGIN/END lines.
Exit: 0 READY; 1 NOT READY; 78 precondition error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _devlib as dl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testpg"))
import dsa_testpg  # noqa: E402

HANDOVER_MARKER = "HANDOVER-CONTINUATION"  # same literal as turn_budget_hook.py


def worktrees(main_root: Path) -> list[Path]:
    out = dl.git(main_root, "worktree", "list", "--porcelain")
    return [Path(line[len("worktree "):]) for line in out.splitlines() if line.startswith("worktree ")]


def continuation_prompt(main_root: Path, handover: str, sha: str) -> str:
    return "\n".join([
        HANDOVER_MARKER,
        "data-service-api の監督を引き継いでください。",
        f"- 作業はメインのチェックアウト `{main_root}` で行ってください。"
        "このチャットに割り当てられた worktree は origin/main から作られており、push 停止中は古いので使わないでください。",
        f"- 最初に `{main_root}/CLAUDE.md`、`{main_root}/docs/work-orders/OPERATING_CONDITIONS.md`、"
        f"引き継ぎ書 `{main_root}/{handover}` (main {sha}) を読み、引き継ぎ書に書かれた次の作業から続けてください。",
        "- 定型手順は OPERATING_CONDITIONS §1.10 に従い、tools/dev/ の道具で行ってください。",
    ])


def check(cwd: Path, running_agents_denied: bool, own_worktrees: list[str],
          handover: str | None, out=sys.stdout) -> int:
    main_root = dl.main_checkout(cwd)
    results: list[tuple[bool, str]] = []
    results.append((running_agents_denied, "no running subagents / background tasks (stated by the chat)"))
    running, reason = dsa_testpg.gate_running()
    results.append((not running, "gate not running (no intent, exclusive lock free)" + (f" -- {reason}" if running else "")))
    branch = dl.git(main_root, "branch", "--show-current").strip()
    dirty = dl.git(main_root, "status", "--porcelain", "--untracked-files=all").strip()
    results.append((branch == "main" and not dirty, f"main checkout on main and clean (branch={branch}, dirty={len(dirty.splitlines())})"))
    journals = [str(wt) for wt in worktrees(main_root) if wt.is_dir() and dl.journal_path(wt).exists()]
    results.append((not journals, "no unfinished mutation journal" + (f" ({', '.join(journals)})" if journals else "")))
    for name in own_worktrees:
        wt = Path(name) if Path(name).is_absolute() else main_root / name
        if not wt.is_dir():
            results.append((False, f"worktree {name}: not found"))
            continue
        wt_dirty = dl.git(wt, "status", "--porcelain", "--untracked-files=all").strip()
        head = dl.git(wt, "rev-parse", "HEAD").strip()
        merged = subprocess.run(["git", "-C", str(main_root), "merge-base", "--is-ancestor", head, "main"],
                                capture_output=True).returncode == 0
        results.append((not wt_dirty and merged, f"worktree {name}: clean={not wt_dirty} merged={merged}"))
    sha = ""
    if handover:
        blob = dl.git(main_root, "cat-file", "-s", f"main:{handover}", check=False).strip()
        committed = blob.isdigit() and int(blob) > 0
        sha = dl.git(main_root, "rev-parse", "--short", "main").strip()
        results.append((committed, f"handover committed on main: {handover}"))
    for ok, label in results:
        print(f"{'ok' if ok else 'NG'}  {label}", file=out)
    ready = all(ok for ok, _ in results)
    print("READY" if ready else "NOT READY", file=out)
    if ready and handover:
        print("----- BEGIN CONTINUATION PROMPT -----", file=out)
        print(continuation_prompt(main_root, handover, sha), file=out)
        print("----- END CONTINUATION PROMPT -----", file=out)
    return 0 if ready else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-C", dest="cwd", default=".")
    parser.add_argument("--no-running-agents", action="store_true")
    parser.add_argument("--worktree", action="append", default=[])
    parser.add_argument("--handover")
    ns = parser.parse_args(argv)
    try:
        return check(Path(ns.cwd).resolve(), ns.no_running_agents, ns.worktree, ns.handover)
    except dl.DevError as exc:
        print(f"handover_ready: ERROR -- {exc}")
        return dl.ERROR


if __name__ == "__main__":
    sys.exit(main())
