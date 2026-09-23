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

## Known gaps (all checkers)

The rule is `docs/work-orders/OPERATING_CONDITIONS.md` 1.12-71 -- one question per gap found in a checker: could a product defect (a contract violation or a Security Invariant breach) pass the completion gate through it? Yes: file it in `docs/design/ROADMAP_POST_PHASE7_V1.md` section 8. No: record it in that checker's own module docstring and do not file it. 1.12-72 treats the tool layer as complete once every checker carries the section. Each checker's `Known gaps` section is the authoritative text (what is not detected / why / what catches it instead); this table is only an index.

| Checker | Gaps (count) | One-line summary |
| --- | --- | --- |
| `tools/change_class.py` | 3 | Classifies only the paths it is handed (the caller's enumeration is the gap, not the path rules -- ledger R-100); content-level C/D triggers are invisible to a path-only classifier; a newly created (not moved) file under `docs/archive/` is graded A the same as a genuine record. |
| `tools/check_collection_floor.py` | 2 | A same-size swap or any drop still above the floor passes; `tools/tests` is not part of the root collection. |
| `tools/check_comment_provenance.py` | 5 | `file:line` references inside src comments are never resolved (ledger R-96); a same-AST-kind substitute after a CH-ID-less block stays silent; a first docstring on an existing function reads as a justified red; nothing outside both peers' `src/` is scanned; a companion duplicate under `docs/archive/docs/code-history/<peer>/` is never enumerated. |
| `tools/check_control_mapping_restructure.py` | 2 | Compares claim text, never claim truth; a one-time check that assumes the old table form. |
| `tools/check_control_mapping_split.py` | 2 | Compares bullet text per (SI, peer, axis), never truth; the move counters gate the exit code only with `--expect`. |
| `tools/check_doc_refs.py` | 5 | IDs beyond a family's own digit width match no family (R widened to 3 digits 2026-09-23; G/P/L stay at 2, SI/C/CCR at exactly 2); the scan set excludes both peers' `.md`, `tools/` below the top level and all code comments; a resolving reference is not checked against what the sentence claims; a dangling or unreadable `.md` inside `docs/archive/` is never reported; a hand-over left past the newest 2 (rotation unperformed) is not detected. |
| `tools/check_image_pins.py` | 4 | Only the image-to-constraints direction is walked; the freeze transcript's provenance is the CI job's, not this script's; `.` is not folded in name normalization; MitateDB-api's is the only production image. |
| `tools/public_value_scan.py` | 3 | A deny-suffix host nested inside another URL's query string is not seen (**ledger R-46, OPEN -- fix before the public flip**); R7 personal names are out of scope; bare FQDNs outside the narrow TLD set, and shapes no rule describes, are never examined. |
| `tools/rewrite_hash_refs.py` | 3 | Sha references under 7 hex characters (or all-digit/all-letter) are not candidates; only tracked `*.md` is targeted by default; `unmatched` tokens do not block `--apply`. |
| `tools/dev/_devlib.py` | 2 | An unknown pytest summary wording parses as None (fail-closed, never a wrong number); a mutate run killed before its journal was written leaves no blocker. |
| `tools/dev/finalize.py` | 3 | Never runs the root suite; `--tools-tests` takes no suite lock and waits for nothing; the `--allow` globs prove a match, not narrowness. |
| `tools/dev/fold.py` | 2 | Safety notes (a)-(c): another chat's clean, old-enough worktree can be folded, and `-C` protects only one worktree; ancestry is checked against the local `--main` only. |
| `tools/dev/gate.py` | 3 | The root suite excludes `tools/tests`; `-C` defaults to the current directory (a call from the main checkout measures main and still says PASS); the shared cluster's catalog diff is `info=` only. |
| `tools/dev/handover_ready.py` | 2 | `--no-running-agents` is a self-declaration; only the worktrees passed with `--worktree` are checked clean-and-merged. |
| `tools/dev/mutate.py` | 2 | `-x` hides every test after the first failure in one mutation entry; a red is an exit code, not evidence of the intended assertion. |
| `tools/dev/pt.py` | 2 | Runs what it is handed and judges nothing; FAILED/ERROR lines beyond `--show N` are only in the log. |
| `tools/dev/section.py` | 3 | Setext headings are not recognized; a fence of more than three markers is read as a 3-marker fence; a `#` line inside an indented code block is reported as a heading. |
| `tools/dev/turn_budget_hook.py` | 2 | Every exception exits 0 silently, so a broken counter is invisible; calls made inside a subagent are never counted. |
| `conformance-tests/test_control_mapping_register.py` | 4 | Shape, cap and reference resolution only -- never a claim's truth, nor the content at a resolving line; the current longest sub-block is deliberately unrecorded (ledger R-73); CONDITIONS.md is never read here; the `POSITION_REF_*_FLOOR` pins fix the document's current reference mix, so a legitimate restructure that only reshapes references (split claims, shorter preamble, normalised paths) reads red until the floors are re-pinned. |
| `conformance-tests/test_conditions_register.py` | 4 | Only the 5 backtick forms inside backtick spans are extracted; a path-omitted name relies on basename uniqueness (non-unique is red, never silent); resolution does not show that the test drives the condition; D-3 (f)'s one allowlisted span is never resolved. |
| `conformance-tests/test_conformance_docstring_position_refs.py` | 5 | Limits (D-9): an in-range reference pointing at an unrelated statement is not seen; route (iii) does not pin a directory; a bare path with no line number and R-88's label shape are out of scope; both peers' `src`/`tests` are out of scope (ledger R-96); a non-backtick-quoted reference and an ID-prefixed form are not extracted. |
| `tools/tests/test_src_import_readers.py` | 3 | Pins the allow table's row set, cannot judge whether a reader-zero import should exist (ledger R-94's ruling did that); D-5's limits (dataflow, dynamic imports, shadowing, aliased `Literal`/`Annotated`); scope is both peers' `src/` only. |

### Checks that live outside tools/

- `r2db-api/src/r2db_api/ops.py:1728-1752` (`_PLATFORM_MIGRATION_SUPERSEDED_BY`) with its derivation in `r2db-api/tests/test_ops_apply_platform_migration.py:402-436` -- **not detected**: a later platform migration that redefines an already-covered role's target while spelling that role differently from the earlier file (a psql variable such as `:"api_role"` in one file, a literal such as `r2dbsvc_api` in another) loses its supersede edge, and `apply-platform-migration`'s own closure check stays green. **why**: the derivation keeps each role reference as its own matched text and never resolves a psql variable to the role name an operator supplies at invocation time, so the two spellings are two different targets. **caught by**: that derivation's own disclosure -- a new migration must spell an already-referenced role exactly as an earlier accepted file already spells it -- plus code review of every new platform migration; ledger R-98 records the gap. Whether MitateDB-api's own same-shaped derivation (R-57 D-3) has the same property is unverified. The peers' `src/` docstrings are inside the comment-provenance scan, so this entry is recorded here rather than in `ops.py` itself.
