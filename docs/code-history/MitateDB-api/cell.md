# src/mitatedb_api/cell.py -- code-comment history

Companion for `src/mitatedb_api/cell.py` per `docs/code-history/README.md`.

## CH-0548

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.prepared_stats`)
- parent commit: `ddf9c73`
- kind: docstring

```
R-79 (WO §1.2 D-2, D-3; §2.1 起草時の裁定 4): read-only accessor
-- delegates to `self._backend.prepared_stats()` under `self.
_lock` (this class's own `RLock`, WO §1.2 D-2's own "lock is taken
by `ApplicationCell`, r2db does not take one -- it drains a queue
instead" split) and returns `[]` when the backend has no such
method (`SQLiteBackend`, and any other non-PostgreSQL backend).
Called exactly once per (plug, op) by `tools/perf_baseline.py`'s
`_emit_prepared_rows` (via the conformance adapter's own `prepared_
stats()`), so one call here is one `self._lock` acquisition --
this is also why the harness's own `POOL lock=` `acquire` count
includes one entry per preceding probe from R-79 onward (`tools/
PERF_BASELINE_README.md`).

Does not widen or narrow the scope `with self._lock:` already
covers elsewhere in this class -- this is a new, independent
acquisition of the SAME lock, not a change to any existing one.
```

### correction: 2026-10-01

- reason: the cell no longer holds a lock (every request borrows its own connections), so the probe takes none

old:
```
delegates to `self._backend.prepared_stats()` under `self._lock` (this class's own `RLock`, WO §1.2 D-2's own "lock is taken by `ApplicationCell`, r2db does not take one -- it drains a queue instead" split) and returns
```

new:
```
delegates to `self._backend.prepared_stats()` and returns
```

### correction: 2026-10-01

- reason: the harness probes before and after each measured window (two calls, three under `--roundtrip`), not once per op, and a probe no longer counts on a cell lock but on the role pools' rows

old:
```
Called exactly once per (plug, op) by `tools/perf_baseline.py`'s `_emit_prepared_rows` (via the conformance adapter's own `prepared_stats()`), so one call here is one `self._lock` acquisition -- this is also why the harness's own `POOL lock=` `acquire` count includes one entry per preceding probe from R-79 onward (`tools/PERF_BASELINE_README.md`).
```

new:
```
One call is one backend probe and takes no lock of the cell's own (the cell holds none). `tools/perf_baseline.py` calls it (via the conformance adapter's own `prepared_stats()`) once before and once after each measured (plug, op) window, and once more before the warmup under `--roundtrip`; `tools/PERF_BASELINE_README.md` says what each call adds to the `POOL` rows.
```

## CH-0566

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._error_row_once_fired`)
- parent commit: `62136cd`
- kind: docstring

```
Guarantees the `error` row of D-2's rule for a backend method
that takes the hook itself (`create_collection`/`add_field`/
`alter_field_constraints`/`delete`): once `hook.pre_commit()` has
recorded the `allow` row, EVERY failure that leaves the method
without committing writes the `error` row -- a cancelled or
lock-timed-out COMMIT and a failure of the idempotency record
included, whichever branch of the backend's own handling they
pass through. The response and its class are unchanged (the
original exception propagates); a backend that already wrote the
row itself does not write a second (`commit_failed()` records at
most once per hook).
```

### correction: 2026-10-03

- reason: R-42 -- the schema operations write the idempotency record before the pre-commit row, so a failure of the record write comes before the `allow` row and never reaches this guarantee

old:
```
a cancelled or lock-timed-out COMMIT and a failure of the idempotency record included, whichever branch of the backend's own handling they pass through
```

new:
```
a cancelled or lock-timed-out COMMIT included, whichever branch of the backend's own handling it passes through
```

## CH-0570

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._prepare_values`)
- parent commit: `9a65cbc`
- kind: comment

```
# B-1 (independent review round 2): `available[field]` is this
# field's own value-domain category from the active backend's
# live catalog (`None` on SQLite -- domain validation skipped
# there, matching its own unchanged external behavior) --
# passed through so a type-mismatched value (e.g. a string for
# a declared-`integer` column) is rejected deterministically
# here, before any statement reaches PostgreSQL. 追補 4 O-2:
# `field`/`declared_type` are this value's own request-
# internal path (`_prepare_values`'s own path prefix, the
# SAME position `check_declared_value`'s own `except` clause
# above attaches) and contract-vocabulary declared type, so a
# backend-layer value-domain denial (NUL/lone surrogate/
# out-of-range) carries the same D-3 (4) 4-key form.
```

### correction: 2026-10-04

- reason: R-82 -- the backend's catalog read behind `available[field]` is answered from a process copy of the live read while the schema revision is unchanged

old:
```
live catalog (`None` on SQLite
```

new:
```
catalog (a live read kept as a process copy while the schema revision is unchanged; `None` on SQLite
```
