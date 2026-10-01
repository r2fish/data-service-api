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
