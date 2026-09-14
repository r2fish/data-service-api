#!/usr/bin/env python3
"""turn_budget_hook.py -- PostToolUse hook: tell a long chat to hand over.

Counts the model calls of the session's main conversation (unique assistant
message ids in its transcript, read incrementally) and, once the count reaches
--threshold, adds a short instruction to the model's context: move to a new
chat at the next safe boundary (OPERATING_CONDITIONS 1.10-67). The reminder
repeats every --every calls until the chat emits the handover chip (a
spawn_task call whose prompt contains HANDOVER_MARKER).

Registered in user settings with --project-root, so it acts only for sessions
whose cwd is inside that checkout (its worktrees included; a handover chip
starts the next chat in a fresh worktree) and stays silent everywhere else.
Calls made inside a subagent (input carrying agent_id) are never answered.
Any error exits 0 silently: a broken counter must never disturb a session.

Usage (settings.json command):
    python3 -B <root>/tools/dev/turn_budget_hook.py --project-root <root> --threshold 300 --every 50
State: $TURN_BUDGET_STATE_DIR, else ~/.claude/turn-budget/<session_id>.json
Standard library only; Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HANDOVER_MARKER = "HANDOVER-CONTINUATION"
_RECENT_IDS = 64
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def fresh_state() -> dict:
    return {"offset": 0, "calls": 0, "recent": [], "notified_at": None, "handed_over": False}


def count_new(transcript: Path, state: dict) -> dict:
    """Advance `state` over the complete lines appended since its offset."""
    if transcript.stat().st_size < state["offset"]:  # rewritten transcript: start over
        state.update(fresh_state())
    with open(transcript, "rb") as fh:
        fh.seek(state["offset"])
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return state
    for raw in data[:end].split(b"\n"):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        msg = rec.get("message") or {}
        mid = msg.get("id")
        if mid and mid not in state["recent"]:  # one call is written as one record per content block
            state["calls"] += 1
            state["recent"] = (state["recent"] + [mid])[-_RECENT_IDS:]
        for block in msg.get("content") or []:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and str(block.get("name", "")).endswith("spawn_task")
                    and HANDOVER_MARKER in json.dumps(block.get("input"), ensure_ascii=False)):
                state["handed_over"] = True
    state["offset"] += end + 1
    return state


def decide(state: dict, threshold: int, every: int) -> str | None:
    calls = state["calls"]
    if state["handed_over"] or calls < threshold:
        return None
    if state["notified_at"] is not None and calls - state["notified_at"] < every:
        return None
    state["notified_at"] = calls
    return (
        f"[turn-budget] このチャットのモデル呼び出しは {calls} 回で、しきい値 {threshold} 回を超えました"
        "(チャット本体への指示です。サブエージェントは無視してください)。"
        "OPERATING_CONDITIONS §1.10 の 67 に従い、次の区切りで新しいチャットへ移ってください。手順は次のとおりです。"
        "新しい WP やサブエージェントは始めない → 進行中の作業を区切りまで終える → "
        "`tools/dev/handover_ready.py --no-running-agents --worktree <担当 worktree>` が READY を返す → "
        "引き継ぎ書を書いて finalize.py でコミットする → "
        "`handover_ready.py ... --handover <引き継ぎ書>` が出力するプロンプトで spawn_task を呼ぶ。"
        f"引き継ぐまで {every} 回ごとに再通知します。"
    )


def main(argv: list[str] | None = None, stdin=None, out=None) -> int:
    stdin = stdin or sys.stdin
    out = out or sys.stdout
    try:
        parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
        parser.add_argument("--project-root", required=True)
        parser.add_argument("--threshold", type=int, default=300)
        parser.add_argument("--every", type=int, default=50)
        ns = parser.parse_args(argv)
        payload = json.load(stdin)
        if payload.get("agent_id"):
            return 0
        root = Path(ns.project_root).resolve()
        cwd = Path(payload.get("cwd") or "/").resolve()
        if cwd != root and root not in cwd.parents:
            return 0
        sid = str(payload.get("session_id") or "")
        transcript = Path(str(payload.get("transcript_path") or ""))
        if not _SESSION_ID_RE.match(sid) or transcript.name != f"{sid}.jsonl" or not transcript.is_file():
            return 0
        state_dir = Path(os.environ.get("TURN_BUDGET_STATE_DIR") or Path.home() / ".claude" / "turn-budget")
        state_file = state_dir / f"{sid}.json"
        try:
            state = {**fresh_state(), **json.loads(state_file.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            state = fresh_state()
        count_new(transcript, state)
        message = decide(state, ns.threshold, ns.every)
        state_dir.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, state_file)
        if message:
            json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}},
                      out, ensure_ascii=False)
    except BaseException:  # never disturb the session, whatever went wrong
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
