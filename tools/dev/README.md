# tools/dev

Single-command versions of procedures that `docs/work-orders/OPERATING_CONDITIONS.md` makes agents repeat by hand. One call replaces several tool calls, so a long session re-reads its context fewer times. The rules themselves stay in OPERATING_CONDITIONS; these scripts only carry them out. Standard library only; tests in `tools/tests/test_dev_tools.py`.

| Script | Replaces | Rules |
|---|---|---|
| `pt.py` | gate-hold flag check → `ps` check → `cd WT && .venv/bin/python -m pytest … \| tail` | 1.3-20, 1.6-42, 2-18 |
| `mutate.py` | per mutation: backup → edit → test → `cp` back → `sleep 3` → sha256 ×2 → grep | 1.4-28..31 |
| `section.py` | paging a long document with `sed -n` / repeated reads | — |
| `gate.py` | touch hold flag → wait → catalog snapshot → root suite → judge → remove flag | 1.3-19..23 |
| `finalize.py` | per-change `finalize_*.sh`: allowlist → checks → commit → merge into main | 1.1-12a, 1.2, 1.9, 2-15 |
| `handover_ready.py` | judging whether this is a safe boundary to move to a new chat; prints the continuation prompt | 1.10-67 |
| `turn_budget_hook.py` | (PostToolUse hook) counting a chat's model calls; reminds it to hand over past the threshold | 1.10-67 |

The hook is registered in user settings, not in the gitignored `.claude/settings.local.json`, because a handover chip starts the next chat in a fresh worktree that has no local settings; `--project-root` keeps it silent outside this checkout. The registration calls a copy under `~/.claude`, not the working tree (user instruction 2026-09-15, same as the PreToolUse guard hook): a hook that points at the working tree runs every session's uncommitted, unreviewed edits on every tool call of every session.

```json
{"matcher": "*", "hooks": [{"type": "command", "timeout": 10,
  "command": "python3 -B \"$HOME/.claude/hooks-turn-budget/data-service-api/turn_budget_hook.py\" --project-root \"<main checkout>\" --threshold 300 --every 50"}]}
```

After changing `turn_budget_hook.py`, the copy must be refreshed on the user-settings side (the user does the copy). Check for drift with `diff tools/dev/turn_budget_hook.py ~/.claude/hooks-turn-budget/data-service-api/turn_budget_hook.py` (no output = identical).

Common behaviour:

- Interpreter: `<main checkout>/.venv/bin/python`, found from any worktree (`--python` overrides).
- Gate-hold flag: `--hold PATH`, else `$GATE_HOLD_FLAG`, else `$SP/gate-hold.flag`. `--hold -` states that the session has no supervisor gate. With none of these the tools refuse instead of assuming "no hold".
- Other pytest processes are counted by executable name (python / pytest) excluding the caller's own process chain, so the check never matches its own shell.
- Full output goes to `$SP/dev-logs/`; stdout carries only tally lines, failures and the log path.
- `gate.py` names the databases and roles behind a non-empty `pg_database` / `pg_roles` diff: all of them, sorted, in a section appended to the end of the log; the first 10 of each list on stdout, before the log path. Any diff is still FAIL.
- Exit codes stay clear of pytest's 0-5: 75 refused to start (hold flag, other pytest, unfinished mutation journal), 76 finalize committed but not merged, 70 restore failed, 78 precondition error.
- `mutate.py` writes a journal in the worktree's git dir before editing; if the run is killed, `pt.py` / `finalize.py` / `mutate.py` refuse until `tools/dev/mutate.py --recover -C WT` restores.

Examples (Bash timeout 600000 for pt / mutate; gate with run_in_background):

```bash
tools/dev/pt.py -C .claude/worktrees/wp1 -- r2db-api/tests/test_foundation.py -q
tools/dev/mutate.py "$SP/wp1-mutations.json" -C .claude/worktrees/wp1
tools/dev/section.py docs/work-orders/WORK_ORDER_X.md --list --depth 3
tools/dev/section.py docs/work-orders/WORK_ORDER_X.md 'WP-1j' -n
tools/dev/gate.py --label wp1
tools/dev/finalize.py -C .claude/worktrees/wp1 --branch wp1 --allow 'r2db-api/*' --allow 'docs/code-history/*' -m "$SP/msg.txt" --tools-tests
```
