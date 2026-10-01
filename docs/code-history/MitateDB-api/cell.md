# src/mitatedb_api/cell.py -- code-comment history (change set 7)

Companion for `src/mitatedb_api/cell.py` per `docs/code-history/README.md`.

## CH-0547

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.__init__`)
- parent commit: `ddf9c73`
- kind: comment

```
# WP-8b 差し戻し (0)/監督裁定 2026-09-08 (design D-8 (3), U-10 --
# RECORD OF FACT, after measurement, not an aspiration): every
# public method below now takes `self._lock` immediately inside
# its own `_gate`/`_limit_gate` (rate/concurrency slot) call, and
# holds it for the WHOLE lookup -> pass-1 (validation/catalog
# reads) -> pass-2 (execute/commit) sequence -- not merely the
# final backend call, which is all it covered before this fix
# (code review `{scratchpad}/phase10/wp8b-review.md` §1/§2 found
# pass-1's own catalog reads/`_idempotency_check` running OUTSIDE
# this lock, sharing `PostgresBackend`'s single `_developer`
# connection with every OTHER in-flight request against this SAME
# cell -- measured concretely: one request's own `commit()`/
# `rollback()` on that shared connection landing on a DIFFERENT
# request's still-open transaction, an application-name DDL
# leaking without its own audit pre-commit row in the worst case).
# An `RLock`, not a plain `Lock`, because `_schema_revision_
# uncounted` (called both directly, as `schema_revision`'s own
# body, and from inside `create_collection`/`add_field`/`alter_
# field`/`transact`'s own dry-run/plan precondition block) takes
# this SAME lock a second time, from the SAME thread, while the
# first acquisition is still held -- safe re-entry, not a
# deadlock, precisely because this is reentrant.
#
# The measured consequence (`test_pass1_and_pass2_serialize_
# through_cell_lock_no_developer_connection_race`, `tests/test_
# threadpool_offload.py`; `{scratchpad}/phase10/wp8b_review_slot_
# probe.py`, re-run against this fix): two requests against the
# SAME application (SAME `ApplicationCell` instance, one lock)
# are now fully serialized end to end -- concurrency across
# DIFFERENT applications (each with its own cell, its own lock)
# is unaffected, still real. `_limit_gate`'s own `concurrency_
# slot` is acquired BEFORE this lock on every call site (this
# lock sits inside the gate's `with`, never outside it) -- a
# `hold_in_flight` probe (C-05/C-27) still observes N distinct
# in-flight SLOTS held concurrently even though, for the SAME
# application, only one of those N requests can be past this
# lock's own acquisition at a time; slot accounting itself is
# therefore unaffected by this fix (measured: 3 concurrent
# slot holders, 1 concurrent lock holder, `wp8b_review_slot_
# probe.py`).
```
