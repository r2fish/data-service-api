# tools/dev

Single-command versions of procedures that `docs/work-orders/OPERATING_CONDITIONS.md` makes agents repeat by hand. One call replaces several tool calls, so a long session re-reads its context fewer times. The rules themselves stay in OPERATING_CONDITIONS; these scripts only carry them out. Standard library only; tests in `tools/tests/test_dev_tools.py`.

WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1): PostgreSQL exclusivity moved to a real flock, `tools/testpg/dsa_testpg.py`'s own `suite_lock()` — `gate.py` and `tools/perf_baseline.py` take it exclusively for their own run; every owned-mode pytest run (any `pt.py` / `mutate.py` invocation, or a bare `pytest`) takes it shared, directly from its own `conftest.py`, for the run's whole life. This replaces the old gate-hold flag file and the `ps`-based "other pytest running" poll entirely — they no longer exist. Only the mutation-journal check (`dev-mutate-journal.json`, an unfinished `mutate.py` run) remains a tool-side precondition.

| Script | Replaces | Rules |
|---|---|---|
| `pt.py` | mutation-journal check → `cd WT && .venv/bin/python -m pytest … \| tail`; `--wait` is forwarded to the pytest subprocess's own owned-mode suite-lock wait | 1.6-42 |
| `mutate.py` | per mutation: backup → edit → test → `cp` back → `sleep 3` → sha256 ×2 → grep; `--wait` is forwarded the same way as `pt.py`'s | 1.4-28..31 |
| `section.py` | paging a long document with `sed -n` / repeated reads | — |
| `gate.py` | take the exclusive suite lock → start a throwaway cluster → catalog snapshot on it → root suite (`DSA_TEST_PG=external`) → judge → stop the cluster / release the lock | 1.3-19..23 |
| `finalize.py` | per-change `finalize_*.sh`: allowlist → checks → commit → merge into main | 1.1-12a, 1.2, 1.9, 2-15 |
| `fold.py` | walking `git worktree list` / `git branch` by hand to find already-merged linked worktrees and local branches safe to remove; `--apply` takes the exclusive suite lock for the whole run (default `--wait 0`); a `prunable` worktree is only reported, never pruned | — |
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
- Full output goes to `$SP/dev-logs/`; stdout carries only tally lines, failures and the log path.
- `gate.py` names the databases and roles behind a non-empty `pg_database` / `pg_roles` diff **on its own run cluster**: all of them, sorted, in a section appended to the end of the log; the first 10 of each list on stdout, before the log path. Any diff there is still FAIL. The shared local PostgreSQL's own diff is printed separately as an `info=` line and never affects PASS/FAIL.
- Exit codes stay clear of pytest's 0-5: 75 refused to start (unfinished mutation journal; for `gate.py` / `perf_baseline.py` / `fold.py --apply`, also the exclusive suite lock timing out), 76 finalize committed but not merged, 70 restore failed, 78 precondition error.
- `mutate.py` writes a journal in the worktree's git dir before editing; if the run is killed, `pt.py` / `finalize.py` / `mutate.py` refuse until `tools/dev/mutate.py --recover -C WT` restores.
- `mutate.py`'s per-mutation `expect` is `"red"` (pytest exit code exactly 1), `"green"` (exactly 0), or `"error"` (any of exit 2-5 -- interrupted / internal error / usage error / no tests collected: something broke the run itself, not merely a failed test, e.g. a mutation that keeps a conftest.py from starting its own cluster at all). The printed `got=` stays pytest's own specific outcome (`red` / `green` / `no-tests` / `error(N)`); only the pass/fail comparison against `expect` treats every code in 2-5 as one "error" bucket (WP-2 §3.1, following up on WP-1's `M13-no-lc-all`, whose exit 4 was wrongly reported as a mismatch against `expect: "red"`).

Examples (Bash timeout 600000 for pt / mutate; gate with run_in_background):

```bash
tools/dev/pt.py -C .claude/worktrees/wp1 -- r2db-api/tests/test_foundation.py -q
tools/dev/mutate.py "$SP/wp1-mutations.json" -C .claude/worktrees/wp1
tools/dev/section.py docs/work-orders/WORK_ORDER_X.md --list --depth 3
tools/dev/section.py docs/work-orders/WORK_ORDER_X.md 'WP-1j' -n
tools/dev/gate.py --label wp1
tools/dev/finalize.py -C .claude/worktrees/wp1 --branch wp1 --allow 'r2db-api/*' --allow 'docs/code-history/*' -m "$SP/msg.txt" --tools-tests
tools/dev/fold.py
tools/dev/fold.py --apply
```
