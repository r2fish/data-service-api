# `tools/perf_baseline.py` -- R-12 performance baseline harness

design: `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` D-6.
work order: `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` WP-5.

## What this is, and is not

This is a **measurement tool, not a test and not a gate**. It places **no
threshold** on anything (design principle P-8) -- there is no pass/fail
judgement beyond one narrow self-check (see below). Running it never fails
a build; it only prints numbers.

The performance baseline itself (the numbers recorded in design section
11.2) is measured **once, by the supervisor, at the phase's completion
gate**, on the branch head after every WP has merged -- not by this
implementation WP's own trial runs. This WP's own trial run (recorded in
the WP-5 completion report) uses a small `--n`/`--warmup` purely to confirm
the harness runs end-to-end and produces well-formed output; those numbers
are not the baseline.

## How to run it

```
./.venv/bin/python tools/perf_baseline.py
```

Defaults: `--warmup 20 --n 200` (design D-6, U-3). Override either:

```
./.venv/bin/python tools/perf_baseline.py --warmup 2 --n 5
```

Only the measured sample count is echoed back, as every `PERF` line's own
`n=` field; the warm-up count is NOT recoverable from the output, so record
the exact command line (including `--warmup`) next to any baseline table.

## Environment

- **In-process plugs** (`r2db-api`, `MitateDB-api`) need nothing beyond
  the shared `.venv` -- they run entirely in memory (r2db) or against a
  throwaway SQLite `:memory:` database (MitateDB), exactly like the
  conformance suite's own in-process plugs.
- **HTTP plugs** (`r2db-api-http`, `MitateDB-api-http`) need a **real,
  reachable local PostgreSQL** -- the same one the conformance suite and
  `pytest` already require. Each reads its own admin DSN from an
  environment variable, defaulting to a local Unix-socket connection if
  unset:
  - `R2DB_TEST_ADMIN_DSN` (default `host=/tmp port=5432 dbname=postgres`)
  - `MITATEDB_TEST_ADMIN_DSN` (default `host=/tmp port=5432 dbname=postgres`)

  If neither variable is set and no local PostgreSQL answers on that
  socket, building the two HTTP-plug adapters fails and the whole run
  fails loudly (registry entries are all `"required": true` -- this tool
  never silently skips a required plug, mirroring `conformance-tests/
  conftest.py`'s own discovery discipline).

Plug selection is read from `conformance-tests/registry.json` -- this file
never hardcodes a plug or adapter module name; adding a registry entry
grows this tool's own output with no code change here.

## Output format

One `PERFRUN` line, then one `PERF` line per (peer, plug, op):

```
PERFRUN host=<OS/arch> python=<version> commit=<short sha> date=<YYYY-MM-DD>
PERF peer=<peer> plug=<plug> transport=<in-process|asgi-inprocess> op=<query|mutate|batch|cross_entity> n=<N> p50_ms=<x.xxx> p95_ms=<x.xxx> backend_calls=<n.nn>
```

Three operations are measured on every plug: `query` (`select_eq`, one
predicate), `mutate` (`insert`, one operation), `batch` (a single-entity
atomic batch of exactly 5 operations, `attempt_batch_with_addresses`). A
fourth, `cross_entity` (`attempt_cross_entity_batch`), is measured **only**
for a plug that declares `cross_entity_mutation` as something other than
`unavailable` -- currently the two `MitateDB-api` plugs. `r2db-api`
declares `cross_entity_mutation: unavailable`, so neither `r2db-api` row
carries a `cross_entity` line: the cost of a request that is refused
before any real work happens is not a performance number. A full run
against the 4 currently-registered plugs therefore prints **14** `PERF`
lines (4 plugs x 3 ops, plus 2 plugs x 1 `cross_entity` op).

## The limits of what these numbers mean

- **In-process only.** Every number here is an in-process (or, for the two
  HTTP plugs, ASGI-in-process -- `httpx.ASGITransport`, no real socket, no
  TLS, no reverse proxy) measurement. `transport=asgi-inprocess` names this
  explicitly. Real-network numbers do not exist yet (they require an
  actual deployed socket plug, phase 10's own L7-2). This tool currently
  only knows how to classify two plug shapes (plain in-process, and
  `-http`-suffixed + ASGITransport httpx client) and refuses to run
  (non-zero exit, no guessed row) for anything else -- when L7-2 registers
  a real socket plug, `_classify_plug` in `tools/perf_baseline.py` needs
  an explicit third branch (and very likely a `socket` transport label),
  not a widened fallback.
- **`backend_calls` is a call count, not a round-trip count, and its
  granularity differs by plug on purpose:**
  - For the two PostgreSQL-backed plugs (`r2db-api-http`,
    `MitateDB-api-http`), it counts real `psycopg.Cursor.execute`/
    `.executemany` calls -- one logical request can, and often does, issue
    more than one (a `batch` request's own multiple operations inside one
    transaction, for instance).
  - For the two in-process plugs (`r2db-api`'s in-memory cell, `MitateDB-
    api`'s SQLite-backed cell), there is no lower-level "statement" layer
    to count, so it counts calls to the backend/cell object's own public
    methods instead.

  These are **not the same unit**. A `backend_calls` value from a
  PostgreSQL-backed plug is not directly comparable to one from an
  in-process plug, and a difference between the two peers on the SAME
  transport is not automatically a difference in "how many database
  operations happen" -- it can also reflect how many internal method calls
  one peer's own backend object happens to expose versus the other's.
  Compare `p50_ms`/`p95_ms` across peers on the same transport; treat
  `backend_calls` as a within-plug signal (did THIS plug's own call count
  for THIS op change between two runs), not a cross-plug one.
- **`op=batch` is fixed at 5 operations** (design D-6 decision 1). If a
  future run changes that count, it is recorded in design section 11.2's
  own footnote, never silently.
- **`op=cross_entity` uses 2 operations across 2 entities** (this tool's
  own implementation choice -- the design left the cross-entity operation
  count unspecified, only that `attempt_cross_entity_batch` is the entry
  point and that MitateDB is the only measured peer for it).
- **No threshold.** This tool never decides "too slow" -- see design
  section 4's own rejected-alternative entry for why (a threshold is a
  bound, and P-5 forbids inventing bounds outside the contract's own
  `limits.classes`). Regression handling is deferred to a future phase,
  once two phases' worth of baselines exist (design section 3 D-6,
  disclosure).
- **Runs of different `--n` are not comparable, because the four ops run
  in a fixed order (`query` -> `mutate` -> `batch` -> `cross_entity`) on
  ONE shared entity that keeps growing.** `mutate`, `batch`, and
  `cross_entity` each insert new rows into the same seeded entity/entities
  before the next op runs, so `query`'s own `select_eq` is measured
  against a 1-row table while `cross_entity` (on the two MitateDB plugs)
  is measured against a table that has already absorbed every prior op's
  own inserts for that run. Changing `--n` changes not only the sample
  count but the size of the state every later op is measured against --
  a `batch` row from a `--n 5` run and a `batch` row from a `--n 200` run
  are not the same measurement. Take a baseline to compare against a
  later one with the SAME `--n` (and `--warmup`, which inserts rows too).
- **`p50_ms`/`p95_ms` are linear-interpolation percentiles, and the
  measured window is never just the product backend.** It always includes
  whatever the conformance adapter (the port) itself does to translate a
  call into a backend operation; for the two HTTP plugs it additionally
  includes `loop.run_until_complete` and the ASGI transport layer itself.
  A sub-0.1ms in-process number is therefore a peer-vs-peer comparison of
  "adapter call + backend call", not of the backend alone -- read the
  peer comparisons in design section 11.2 with that in mind.

## The one self-check this tool performs

Before printing a plug's own `query` row, this tool asserts that EVERY
individual `query` sample it just measured observed at least 1 backend
call (`min(query_calls) >= 1`, not the N-sample average), and exits
non-zero (printing the failure to stderr) if even one sample is 0. This is
**not** a claim about what the "right" call count is -- only that the
counting proxy is not silently wired to nothing for any of the samples
that make up the printed row. See `tools/perf_baseline.py`'s own
`_run_self_check` docstring.
