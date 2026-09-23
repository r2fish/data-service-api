# `tools/perf_baseline.py` -- R-12 performance baseline harness

design: `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` D-6.
work order: `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` WP-5.

Phase 10 WP-7 (design `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-8 /
D-12, work order `docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md`
WP-7) added `--concurrency K` -- see "Concurrency (`--concurrency K`)" below.

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

Defaults: `--warmup 10 --n 100` (Phase 10 WP-7, design D-8 (1); lowered from
the pre-Phase-10 `--warmup 20 --n 200`, design D-6/U-3 -- see "Concurrency"
below for why). Override either:

```
./.venv/bin/python tools/perf_baseline.py --warmup 2 --n 5
```

Only the measured sample count is echoed back, as every `PERF` line's own
`n=` field; the warm-up count is NOT recoverable from the output, so record
the exact command line (including `--warmup`) next to any baseline table.

## Concurrency (`--concurrency K`)

**Mechanism**: at `--concurrency K` (default 1), every measured sample
becomes a GROUP of `K` requests fired together via exactly one
`asyncio.gather` call on the plug's own event loop, timed as one group (from
just before the `gather` call to every member of it completing) -- never `K`
separate per-request times, and never OS threads (threads would mix
client-side GIL contention into a measurement whose whole point is
server-side event loop serialization). `K == 1` walks the identical dispatch
call with singleton groups -- there is no separate, sequential-`await`
branch for it. For an `asgi`/`socket`-transport plug (a real
`httpx.AsyncClient`), this genuinely overlaps `K` in-flight requests on the
wire; for an `in_process` plug (no event loop anywhere in its own call
chain) it necessarily reduces to running `K` calls one after another
regardless of `K`, since there is no real I/O to overlap with in the first
place -- not a bug, just nothing to measure there.

Because each SAMPLE now fires `K` real requests, `(n + warmup) * K` requests
land on a single measured op's own credential -- this is why the default
`--n`/`--warmup` dropped from 200/20 to 100/10 (see above): at `--concurrency
3` with the OLD defaults, `(200 + 20) * 3 = 660` would exceed the shared
surface's default `requests_per_minute` bound of 600
(`r2db-api/src/r2db_api/limits.py:18`; the bound actually in play is the
shared surface's own default `concurrency=32`, `:17`, not any isolated-
profile value) -- the new defaults keep this at `(100 + 10) * 3 = 330`.

**Judgement rule (fixed BEFORE any measurement is taken -- design D-8 (2),
U-2)**: if a socket-transport plug's own `K=3` `p50_ms` exceeds 2x its own
`K=1` `p50_ms` for the SAME (peer, plug, op), that is treated as evidence of
server-side event-loop serialization under concurrent load, and WP-8
(threadpool delegation) is warranted in that phase; otherwise the
measurement is recorded only. This script never evaluates or prints that
comparison itself (no thresholds anywhere in this tool, P-8) -- applying the
rule to two runs' own `PERF` lines is the supervisor's own recorded
judgement, comparing the SAME (peer, plug, op) row across a `--concurrency
1` run and a `--concurrency 3` run.

```
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 1
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 3
```

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
PERF peer=<peer> plug=<plug> transport=<in-process|asgi-inprocess|socket> op=<query|mutate|batch|cross_entity> n=<N> p50_ms=<x.xxx> p95_ms=<x.xxx> backend_calls=<n.nn> concurrency=<K>
```

`concurrency=<K>` (Phase 10 WP-7, design D-8/D-12) is the ONLY column added
to this line since the format above -- every other column keeps its exact
pre-WP-7 name, order, and formatting; see "Concurrency (`--concurrency K`)"
above for what `K` means.

Three operations are measured on every plug: `query` (`select_eq`, one
predicate), `mutate` (`insert`, one operation), `batch` (a single-entity
atomic batch of exactly 5 operations, `attempt_batch_with_addresses`). A
fourth, `cross_entity` (`attempt_cross_entity_batch`), is measured **only**
for a plug that declares `cross_entity_mutation` as something other than
`unavailable` -- currently the two `MitateDB-api` plugs. `r2db-api`
declares `cross_entity_mutation: unavailable`, so neither `r2db-api` row
carries a `cross_entity` line: the cost of a request that is refused
before any real work happens is not a performance number. A full run
against the 6 currently-registered plugs (Phase 10 WP-4 added the two
`-socket` plugs to the original 4) therefore prints **21** `PERF` lines (6
plugs x 3 ops, plus the 3 `MitateDB-api` plugs -- in-process, `-http`, and
`-socket`, all three declaring `cross_entity_mutation: partial` -- x 1
`cross_entity` op; the two `r2db-api` plugs still declare it `unavailable`).
This row count is per invocation regardless of `--concurrency`: a
`--concurrency 1` run and a `--concurrency 3` run each print 21 lines on
their own -- comparing the two is what the judgement rule above is for
(the three `r2db-api` plugs -- in-process, `-http`, `-socket` -- still
declare `cross_entity_mutation: unavailable`, so none of them ever carries
a `cross_entity` line).

## `POOL` lines (R-78)

For each (plug, op) this tool measures, it calls `pool_stats()` on the
plug if it has one, and prints one `POOL` line per entry the call returns
-- never a proxy for whether a wait happened, the plug's own connection-
pool/lock bookkeeping. **Position**: every `POOL` line for a plug is
printed while `_measure_plug` is still running (a side effect, once per
op measured), and only once `_measure_plug` returns does the caller print
that plug's own `PERF` lines -- so a plug's `POOL` lines print as ONE
BLOCK, all of them, BEFORE that plug's `PERF` lines, never interleaved
with them op by op:

```
POOL peer=<peer> plug=<plug> op=<op> role=<role> size=<n> acquire=<n> waits=<n> wait_total_ms=<x.xxx> wait_max_ms=<x.xxx> in_use_peak=<n>
POOL peer=<peer> plug=<plug> op=<op> lock=<application_id> acquire=<n> waits=<n> wait_total_ms=<x.xxx> wait_max_ms=<x.xxx>
```

The first shape is a `r2db-api` role pool (`r2db_api.postgres._RolePool.
stats()`'s own six keys: `size`/`acquire_count`/`wait_count`/`wait_total_
ms`/`wait_max_ms`/`in_use_peak`); the second is a `MitateDB-api`
application cell lock (`mitatedb_api.cell._CountingRLock.stats()`'s own
four keys -- `lock_acquire_count`/`wait_count`/`wait_total_ms`/`wait_max_
ms` -- there is no pool `size`/`in_use_peak` concept for a mutex, so
neither column is printed on this shape). Only plugs with a `pool_stats()`
method print `POOL` lines at all -- a plug without one (any plug this WP
did not touch) is silently skipped, the same way a plug without `cross_
entity_mutation` support is silently skipped for that op.

**The numbers are cumulative across the whole plug run, never reset per
op.** `size`/`acquire`/`waits`/`wait_total_ms`/`wait_max_ms`/`in_use_peak`
(or the lock equivalents) keep accumulating from the plug's first
measured op through its last -- a `batch` op's `POOL` line reflects every
acquisition since `query`'s own first one too, not just `batch`'s own.
Reading a single op's `POOL` line in isolation as "this op's own cost"
undercounts nothing but attributes everything to the wrong op. The
counters live on the pool/lock object itself, not on this tool, so they
also survive across plugs that share one process (the `-http`/`-socket`
pair) -- and are lost outright if the underlying pool/lock object is ever
evicted and recreated (r2db's `SharedPoolManager` idle/LRU eviction,
MitateDB's `_MAX_OPEN_CELLS` cap): a `POOL` line after an eviction reflects
only the NEW object's own counters from zero, not the evicted one's
history.

**`-socket` plugs print `POOL` lines too.** A socket-transport plug is the
SAME in-process object as its `-http` counterpart (`R2DBSocketConformance
Adapter`/`MitateDBSocketConformanceAdapter` only override `transport_kind`/
`_build_client`/`_surfaces_value`/`_reset_surface_state` -- composition,
including the cell/pool, is inherited unchanged) running behind a real
`uvicorn` thread of the SAME process; the only genuinely separate process
in that path is the `nginx` front end. There is nothing across a process
boundary this tool cannot read for a socket plug that it could read for
its `-http` sibling.

**`DSA_PERF_POOL_SIZE` (r2db-api `-http`/`-socket` only).** This
environment variable is read only by the `r2db-api-http` conformance
plug's `_make_cell` (`-socket` inherits it, unchanged); it is a harness-
only escape hatch, never read by production code. Set to a positive
integer, it overrides this plug's own per-application data-plane pool
size (otherwise a fixed `2`) so a K-sweep can measure the plug at the
production dimension (`role_pool_size(ResourceLimits())`, i.e. `Resource
Limits.concurrency`) as well as at the existing conformance default.
Absent, empty, or not a positive integer, the plug's pool size is the
unchanged default `2` -- conformance's own default behaviour never
depends on this variable being set.

## The limits of what these numbers mean

- **In-process / ASGI-in-process / real socket.** `_classify_plug` (Phase
  10 WP-3, design D-12) reads each adapter's own DECLARED `transport_kind`
  (`conformance-tests/adapter.py` port v1.14 -- one of `"in_process"`/
  `"asgi"`/`"socket"`), never the built object's own attribute shape or its
  registry name alone (a proxy indicator this tool used to rely on,
  `OPERATING_CONDITIONS.md` section 1.7 item 52), and cross-checks the
  declaration against the registry name's own suffix convention (`-http`
  for `asgi`, `-socket` for `socket`, no suffix for `in_process`) -- a plug
  whose name and declaration disagree, or whose declared value falls
  outside this 3-word vocabulary, still refuses to run (non-zero exit, no
  guessed row) rather than printing a wrong label.
  `transport=in-process`/`transport=asgi-inprocess` are the SAME literal
  labels this tool printed before Phase 10; `transport=socket`
  (`r2db-api-socket`/`MitateDB-api-socket`, Phase 10 WP-4, design D-1 (A))
  is the one genuinely new label, for a REAL loopback socket + reverse
  proxy (nginx) in front of the same composition the other two transports
  hold in-process -- no ASGI transport, no in-process function call.
  `backend_calls` stays available for a socket plug too (it holds its own
  composition in-process, unlike a launched-elsewhere composition root,
  design D-12) -- only the transport itself is real. A socket-transport
  plug's own numbers are the ONLY ones in this tool's output measuring a
  real wire round trip end to end (TCP + nginx + the peer's own HTTP
  stack); every other plug's numbers stay in-process or ASGI-in-process as
  described above.
- **`backend_calls` is a call count, not a round-trip count, and its
  granularity differs by plug on purpose:**
  - For the four PostgreSQL-backed plugs (`r2db-api-http`,
    `r2db-api-socket`, `MitateDB-api-http`, `MitateDB-api-socket` -- a
    `-socket` plug holds the identical PostgreSQL-backed composition its
    own `-http` counterpart does, design D-1 (A)), it counts real
    `psycopg.Cursor.execute`/`.executemany` calls -- one logical request
    can, and often does, issue more than one (a `batch` request's own
    multiple operations inside one transaction, for instance).
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
  against a 1-row table while `cross_entity` (on the three MitateDB plugs)
  is measured against a table that has already absorbed every prior op's
  own inserts for that run. Changing `--n` changes not only the sample
  count but the size of the state every later op is measured against --
  a `batch` row from a `--n 5` run and a `batch` row from a `--n 200` run
  are not the same measurement. Take a baseline to compare against a
  later one with the SAME `--n` (and `--warmup`, which inserts rows too).
- **`p50_ms`/`p95_ms` are linear-interpolation percentiles, and the
  measured window is never just the product backend.** It always includes
  whatever the conformance adapter (the port) itself does to translate a
  call into a backend operation; for the `-http`/`-socket` plugs it
  additionally includes `loop.run_until_complete` and either the ASGI
  transport layer (`-http`) or the real TCP + nginx + HTTP stack round
  trip (`-socket`). A sub-0.1ms in-process number is therefore a
  peer-vs-peer comparison of "adapter call + backend call", not of the
  backend alone -- read the
  peer comparisons in design section 11.2 with that in mind.

## The one self-check this tool performs

Before printing a plug's own `query` row, this tool asserts that EVERY
individual `query` sample it just measured observed at least 1 backend
call (`min(query_calls) >= 1`), and exits non-zero (printing the failure to
stderr) if even one sample is 0. This is **not** a claim about what the
"right" call count is -- only that the counting proxy is not silently wired
to nothing for any of the samples that make up the printed row. See
`tools/perf_baseline.py`'s own `_run_self_check` docstring.

**At `--concurrency 1`** this check is exact per sample, unchanged from
before Phase 10 WP-7 (an average can be >= 1 while individual samples are
actually 0; checking the minimum cannot be fooled that way). **At
`--concurrency K > 1`**, a single sample's own `K` constituent requests
genuinely overlap in time by design (that overlap is the entire point of
this measurement), so their backend calls cannot be safely attributed to
one request or another; this tool instead spreads the WHOLE measured
phase's own total observed calls evenly across every sample before running
the same `>= 1` check -- a documented, coarser relaxation of the check's
precision that only applies when `--concurrency > 1` (`_rows_from_groups`'
own docstring).
