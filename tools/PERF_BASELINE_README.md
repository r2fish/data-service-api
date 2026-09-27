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

**`DSA_PERF_THREAD_LIMIT` (both peers' `-http`/`-socket` plugs).** Passed
straight through to the plug's own `create_app(..., thread_limit=)` call
(R-101 WP-3, D-10) -- a positive integer is that value; absent, empty, or
not a positive integer resolves to `create_app`'s own production default
(`DEFAULT_THREAD_LIMIT`, 4), **never** anyio's own untouched default (40).
`create_app`'s own middleware sets the first request served on any one
event loop's own default anyio thread limiter (`anyio.to_thread.
current_default_thread_limiter()`) to that resolved value, then never
touches it again on that loop -- an `-http` plug's own asgi loop and an
`-socket` plug's own uvicorn thread each get this treatment
independently, the first time either serves a request. **Do not leave
this variable set while running `pytest`**: every conformance/unit test
that builds one of these plugs would then run its own requests under the
reduced thread limit too, changing timing-sensitive test behaviour that
has nothing to do with this tool.

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

**Row order, per (plug, op):** `CPU` -> `POOL` -> `DBTIME` -> `PREPARED`/
`PREPSTMT` -> `ROUNDTRIP` (the last two lines only under `--roundtrip`),
then, once every op for that plug has run, that plug's own `PERF` lines
as one block (unchanged from before `CPU`/`DBTIME` existed).

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

## `CPU` lines (R-101)

One `CPU` line per (plug, op), printed FIRST in that op's own block --
before `POOL`, `DBTIME`, `PREPARED`, and `ROUNDTRIP`:

```
CPU peer=<peer> plug=<plug> op=<op> concurrency=<K> thread_limit=<N|default> requests=<n * K> wall_ms=<x.xxx> cpu_total_ms=<x.xxx> cpu_main_ms=<x.xxx> cpu_other_ms=<x.xxx>
```

The window is the MEASURED `--n` samples only -- warmup is excluded, the
same convention every other row on this page already follows.
`thread_limit=` is the plug's own `perf_thread_limit()` value (the
resolved `DSA_PERF_THREAD_LIMIT` this run was started with, `create_
app`'s own default -- 4 -- when the env was absent or invalid) -- always
an integer for the two `-http`/`-socket` plugs per peer (R-101 WP-3, D-10:
`perf_thread_limit()` no longer returns `None`), or the literal `default`
only for the two `in_process` plugs, which have no such accessor at all.
`requests=` is `n * K` --
measured requests only, never `(warmup + n) * K` (`ROUNDTRIP`'s own
`requests=` below uses the warmup-inclusive count instead; the two are
deliberately different denominators for different purposes). `wall_ms=`
is the sum of the measured groups' own wall-clock durations (the same
numbers `p50_ms`/`p95_ms` on the `PERF` line are computed from).
`cpu_total_ms=` is `resource.getrusage(RUSAGE_SELF)`'s own `ru_utime +
ru_stime` difference across that same window -- every CPU-second this
whole OS process spent, on any of its threads, while the measured window
ran. `cpu_main_ms=` is `time.thread_time()`'s own difference on the
CALLING thread only (the main thread, where this tool's own client loop
and, for an asgi plug, the app's own async layer all run). `cpu_other_
ms=` is `cpu_total_ms - cpu_main_ms`: the CPU spent on every OTHER thread
in the process -- an anyio worker thread running a `run_in_threadpool`
call, or, for a `-socket` plug, the uvicorn server thread. This tool
takes no position on what "the primary serialization actor" is; it prints
these numbers so a reader with the plug's own `thread_limit=`/`concurrency=`
sweep in hand can judge that themselves.

## `DBTIME` lines (R-101)

For each (plug, op), immediately AFTER that op's own `POOL` line(s) and
BEFORE its `PREPARED` line(s), this tool prints one or two `DBTIME`
lines -- only for a plug with a `prepared_stats()` method (every plug
this addition does not touch prints none, no exception):

```
DBTIME peer=<peer> plug=<plug> op=<op> concurrency=<K> scope=app conns=<n> gone=<n> db_calls=<n> txns=<n> db_wall_ms=<x.xxx> db_wall_ms_per_req=<x.xxx>
DBTIME peer=<peer> plug=<plug> op=<op> concurrency=<K> scope=platform sessions=<n> connect_wall_ms=<x.xxx> db_calls=<n> txns=<n> db_wall_ms=<x.xxx> db_wall_ms_per_req=<x.xxx>
```

Both lines are PRE/POST differences across the same measured window `CPU`
uses -- the PRE snapshot is taken inside `_measure_op`, after warmup and
before the measured window starts (its own `prepared_stats()` call); the
POST snapshot is the same call `PREPARED` already makes. `prepared_stats(
)` therefore runs TWICE per op (PRE + POST) without `--roundtrip`, three
times with it (`ROUNDTRIP`'s own separate PRE probe is a third call) --
the POST call itself is shared by `DBTIME scope=app` and every `PREPARED`
line, never a second POST probe for this addition's own sake.

**`scope=app`** covers the application-database round trips the connections
`prepared_stats()` itself returns spent: `conns=` is the number of
connection labels in the POST snapshot (including one opened during the
window, absent from PRE); `gone=` is the number of labels present only in
PRE (closed during the window, contributing nothing to the sums below);
`db_calls=` is the summed `execute_count + executemany_count` delta per
label (a POST-only label's own PRE is treated as 0, never dropped from
the sum); `txns=` and `db_wall_ms=` are the same PRE/POST delta on
`psycopg_counting.CountingConnection`'s own `txn_count`/`db_wall_ms`
attributes. `db_wall_ms_per_req=` divides by `requests=n * K` (not
printed on this line itself, but the same denominator `CPU`'s own
`requests=` column carries for the same op).

**`scope=platform`** covers the platform-side connections (the
credential store and the durable application-audit sink) the data-plane
measurement path itself opens -- never a plug's own control-plane or
provisioning connections. `sessions=` and `connect_wall_ms=` are the
PRE/POST delta of how many NEW connections opened during the window and
how long those `connect()` calls themselves took; `txns=`/`db_wall_ms=`/
`db_calls=` are the same delta on the platform accessor's own `txn_
count`/`db_wall_ms`/`execute_count + executemany_count` sum (`_RolePool.
platform_stats()` on r2db-api; on MitateDB-api, the durable audit sink's
own per-call `platform_stats()` plus the credential store's pooled
connections' own `pool.BoundedConnectionPool.platform_stats()` -- the
credential store itself no longer opens per-call connections once a pool
is wired, so its share comes from the pool it checks connections out of,
not from the store's own no-pool accumulators. Both accessors fold every
closed/discarded connection's own counters in before it closes/discards,
the same discipline `scope=app` relies on for its own connections).
`db_wall_ms_per_req=` divides `db_wall_ms +
connect_wall_ms` by
`requests=` -- the connect cost is folded into the same per-request
denominator `scope=app` uses for its own round-trip-only wall time.

**`txns=` is not `ROUNDTRIP`'s own `xacts=`.** `txns=` counts `commit()`/
`rollback()`/`transaction()` enter-and-exit calls on `psycopg_counting.
CountingConnection` (SAVEPOINT/RELEASE included, each side of a `with
conn.transaction():` block counted separately) -- a client-side call
count. `ROUNDTRIP`'s own `xacts=` (below) counts PostgreSQL's own
server-side `pg_stat_database.xact_commit + xact_rollback` delta. The two
peers' own connection-management shapes give these different units, and
this tool does not attempt to reconcile them into one number.

**MitateDB's `POOL lock=` `acquire`, on any op after the first, reflects
TWO probe acquisitions, not one**: this op's own DBTIME PRE snapshot
(taken inside `_measure_op`, before the measured window, so it lands on
THIS SAME op's own `POOL lock=` line) and the PRECEDING op's own shared
POST snapshot (`DBTIME scope=app`'s and `PREPARED`'s common `prepared_
stats()` call, which runs after that preceding op's own `POOL lock=` line
already printed, so it lands on the NEXT op's own line instead -- this
op's). `ApplicationCell.prepared_stats()` takes the cell's own lock every
time it runs at all, so each of the two calls raises `acquire_count` by 1
independently. **The very first op's own `POOL lock=` line carries only
its own PRE snapshot's acquisition** -- there is no preceding op's own
POST snapshot to add.

**A probe that fails still shows up as a windowed round trip.** If the
POST (or PRE) `prepared_stats()` call itself raises on a particular
connection, `psycopg_counting.probe_prepared_statements` reports `probed=
False` and the caller rolls that connection back before returning it --
that rollback is itself one `txn_count`/`db_wall_ms` entry on the SAME
connection, so a probe failure shows up in `DBTIME scope=app`'s own
numbers as one extra transaction on the window it happened in, not as a
silently missing connection.

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

## `PREPARED` / `PREPSTMT` lines (R-79)

For each (plug, op), immediately AFTER that op's own `POOL` line(s)
(never before, never interleaved), this tool calls `prepared_stats()` on
the plug if it has one, and prints one `PREPARED` line per connection the
call returns:

```
PREPARED peer=<peer> plug=<plug> op=<op> conn=<label> executes=<n> executemany=<n> prepared=<n> prepared_execs=<n> share=<x.xxx>
```

`conn=<label>` ends in `@<backend_pid>` (`r2db-api` `<application_id>/
<role>@<pid>`, `MitateDB-api` `runtime@<pid>`/`developer@<pid>`) -- a
re-connect shows up as the pid changing. `executes=`/`executemany=` are
that connection's own lifetime `execute()`/`executemany()` call counts
(`r2db_api.psycopg_counting`/`mitatedb_api.psycopg_counting`'s own
`CountingCursor`); `prepared=` is how many rows `pg_prepared_statements`
currently holds for that connection; `prepared_execs=` is the sum of
those rows' own `generic_plans + custom_plans`.

**`--prepared-detail` adds one `PREPSTMT` line per prepared statement per
connection** (off by default -- far more output than the summary line
above it):

```
PREPSTMT peer=<peer> plug=<plug> op=<op> conn=<label> name=<name> generic=<n> custom=<n> stmt=<first 80 chars, whitespace collapsed to one space>
```

**`share` is a LOWER BOUND, and structurally can never reach `1.000`.**
`share = prepared_execs / executes` (`0.000` when `executes == 0`, never
a `ZeroDivisionError`) is "how much of this connection's own traffic is
CURRENTLY landing on a statement `pg_prepared_statements` still holds" --
not "how much of it ever did". A `rollback()` on a non-IDLE connection
clears every prepared statement psycopg is tracking (`Connection.
rollback`/`Transaction.rollback`, PostgreSQL's own `DEALLOCATE ALL`); the
executions that already happened against a since-cleared statement are
gone from the numerator but still counted in the denominator. The
denominator also includes statements that can never themselves become
prepared at all -- `SET LOCAL`, DDL, a `prepare=False` read -- so `share`
carries a structural ceiling below `1.000` even with zero deallocation.
**Judge whether a given statement is prepared by the `PREPSTMT` list
(`--prepared-detail`), never by `share`'s own magnitude.**

**The `executes`/`executemany`/`prepared`/`prepared_execs` numbers are
the connection's own LIFETIME counters, never reset per op** -- exactly
like the `POOL` line counters above: a `batch` op's `PREPARED` line
reflects every `execute()` call on that connection since it was opened,
not just `batch`'s own.

**The probe runs strictly AFTER the op it is measuring, and never
mutates prepared-statement state.** It reads `pg_prepared_statements`
with a bare `psycopg.Cursor` (never the connection's own `CountingCursor`
-- so the probe's own read is never itself counted as `execute_count`)
and `prepare=False` (so the probe's own SELECT can never itself become a
server-side prepared statement -- it never appears in `PREPSTMT`, and
never inflates `prepared`/`prepared_execs`), followed immediately by
`conn.commit()`, never `rollback()` (a rollback on a non-IDLE connection
would clear whatever the probe is trying to observe). A connection that
is not IDLE at the moment the probe reaches it is left completely
alone -- not probed at all that round -- rather than risk disturbing an
in-flight caller's own transaction.

**"Never mutates prepared-statement state" is about the SERVER side
only.** The probe's own SELECT still lands a key in psycopg's own
client-side bookkeeping (WO §1.1 F3) -- one extra entry per probe,
occupying a slot in that connection's own `prepared_max`-capped table
until a later, unrelated statement's own key eventually evicts it (the
same LRU behaviour `_counts` always has, `_preparing.py`'s own `_rotate`)
-- it never becomes a server-side prepared statement itself and never
appears in `pg_prepared_statements`/`PREPSTMT`, but it is not entirely
free on the client side either (design memo §1's own F3 note).

**MitateDB's `POOL lock=` `acquire`, at this section's own R-79 baseline,
included one acquisition per PRECEDING probe** (superseded by the `##
DBTIME lines (R-101)` section above, which now runs `prepared_stats()`
twice per op -- see that section's own note on this op's own PRE
acquisition and the preceding op's own POST acquisition for the current
count). `ApplicationCell.prepared_stats()`
takes the SAME cell lock every other operation on that cell takes
(`cell.py::ApplicationCell._lock`), so calling it once (to print the
`PREPARED` line(s) for the op that just ran) raises that cell's own
`lock_acquire_count` by 1 -- the NEXT op's own `POOL lock=` line reflects
that extra acquisition alongside the op's own real ones. r2db-api's
`POOL role=` line is unaffected: its probe drains idle connections
directly off the pool's own queue (`get_nowait`/`put_nowait`), never
`_acquire()`, so it never touches `acquire_count`/`wait_count`/`in_use_
peak`.

## `ROUNDTRIP` lines (R-80)

**Off by default -- pass `--roundtrip` to turn them on.** Unlike every
other line this tool prints, a `--roundtrip` run's `pg_stat_database`
confirm-wait (below) costs several real seconds per (plug, op), taken
TWICE (once before the op, once after) -- so the ordinary run's own
duration stays unaffected unless `--roundtrip` is actually given
(docs/work-orders/WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md, "WO" below,
§1.2 D-1).

For each (plug, op), `--roundtrip` prints two kinds of line, AFTER that
op's own `PREPARED`/`PREPSTMT` lines (`POOL` -> `PREPARED` (+`PREPSTMT`)
-> `ROUNDTRIP`, never any other order):

```
ROUNDTRIP peer=<peer> plug=<plug> op=<op> requests=<n> conn=<label> stmts=<n> stmts_per_req=<x.xx>
ROUNDTRIP peer=<peer> plug=<plug> op=<op> requests=<n> db=<app|platform> xacts=<n> xacts_per_req=<x.xx> sessions=<n> sessions_per_req=<x.xx> stale=<0|1>
```

**Why these are separate lines, not one number.** A single "round trips
per request" figure would silently add together things that do not add:
an autocommit statement (the liveness ping) has no `BEGIN`/`COMMIT` of
its own, and a new session's own connection-establishment round trip is
neither a statement nor a transaction. `conn=` (one line per connection)
carries the STATEMENT count; `db=` (one line per resolved database)
carries the TRANSACTION and SESSION counts -- three separate components,
never merged into one.

**`requests=` is the number of real requests this run actually sent for
that op**, `(warmup + n) * concurrency` -- a DIFFERENT number from the
`PERF` line's own `n=` (the measured-sample count alone, never counting
`--warmup`).

**Both kinds of line are a PRE/POST difference, never a running total.**
Immediately before `_measure_op` starts timing an op, and again
immediately after, this tool takes a PROBE (`prepared_stats()`, same as
the `PREPARED` line above -- the POST probe's own return value is reused
for both `ROUNDTRIP` and `DBTIME scope=app`) and a `pg_stat_database`
read. `ROUNDTRIP`'s own PRE probe is a SEPARATE call from `DBTIME`'s own
PRE probe (each taken at a different point: `ROUNDTRIP`'s before warmup,
`DBTIME`'s after warmup/before measured) -- a `--roundtrip` run therefore
calls `prepared_stats()` three times per op in total (two PRE + one
shared POST), not twice. `stmts=`
is that op's own `Δexecute_count` for one connection (matched by
`label`; a label absent from the PRE probe -- a reconnect -- reads as
baseline 0, never a raised exception and never the value carried over
from a different label). Taking the baseline from the immediately
preceding PRE probe, rather than the previous op's own POST value, keeps
activity BETWEEN two ops (credential issuance, `authenticate`, a
`cross_entity` op's own `create_entity`) out of the next op's own count.

**`db=app`/`db=platform` name resolution.** The application database name
comes from whichever of two forms a plug's resolved cell/backend has: a
DSN string (`r2db_api.postgres.PostgresCell._runtime_dsn`, parsed with
`psycopg.conninfo.conninfo_to_dict`) or a public `psycopg` property
(`mitatedb_api.backend_postgres.PostgresBackend._runtime.info.dbname`).
The platform database name is both http plugs' own `_platform.
platform_db`. A plug matching NEITHER form (every non-PostgreSQL plug)
gets zero `db=` lines for that op -- never an exception.

**Probe `commit()`s are excluded from `xacts`.** The probe's own SELECT
is followed by `conn.commit()` on every IDLE connection it reaches (same
as the `PREPARED` section above) -- each such commit raises that
connection's own database `xact_commit` by 1, a round trip this tool
itself caused, not the measured op. `db=app`'s own `xacts` subtracts the
count of POST-probed connections belonging to THIS run's own application
(r2db-api: `label` starts with `<application_id>/`; MitateDB-api: the
resolved cell's own exactly-2 persistent connections, identified by
their own `.info.backend_pid` -- never a DIFFERENT application's own
cell, such as the one `capability_document()` provisions once to probe
`cross_entity_mutation` availability). **`db=platform`'s own correction
is always 0** -- neither peer's platform/credential connections are ever
probed (r2db-api's platform/credential/audit-sink pools are never
registered with `SharedPoolManager`; MitateDB-api's credential-store
pool (`pool.BoundedConnectionPool`, `_read_pool`) does hold IDLE
connections, but the adapter's own `prepared_stats()` walks application
cells only, never that pool). `db=app`'s correction subtracts BOTH probes that land
inside a `--roundtrip` window: `DBTIME`'s own PRE snapshot (taken after
warmup, before the measured window) and the shared POST snapshot
(`DBTIME scope=app`/`PREPARED`'s common call) -- each probes the same
connections and each commit counts once against `xacts`.

**`pg_stat_database`'s own counters lag real time -- the poll waits for
them to settle.** This tool's own admin connection to the throwaway
cluster (never a plug's own connection) runs `pg_stat_clear_snapshot()`,
then reads `xact_commit`/`xact_rollback`/`sessions` for the resolved
database name(s) every 1 second, confirming a value only once BOTH at
least 12 seconds have elapsed since the clear AND the last 3 reads agreed
-- a value that has been flat since the very first read does NOT confirm
before that 12-second minimum (WO §1.3 (5b): a real burst was observed
flat at a wrong value for 20 real seconds before the backend's own
pending statistics actually flushed). Past a 30-second ceiling, the
last-seen value is printed anyway, with **`stale=1`** (a confirmed value
prints `stale=0`) -- a `stale=1` row is not this op's settled value and
should not be treated as one.

**`BEGIN`/`COMMIT`/`ROLLBACK` count toward `xacts`; `SAVEPOINT`/`RELEASE`
count toward NOTHING this tool measures at all.** `Cursor.execute` is
never called for any of the five (psycopg's own `Connection._exec_
command` path) -- `BEGIN`/`COMMIT`/`ROLLBACK` still show up indirectly,
as a `pg_stat_database` transaction; `SAVEPOINT`/`RELEASE` show up
NOWHERE -- not in `stmts` (no `execute()` call), not in `xacts` (no
separate top-level transaction, no distinct `pg_stat_database` counter
for a savepoint). A round trip spent taking or releasing a savepoint is
invisible to every `ROUNDTRIP` component.

**A second application's own connections never appear in `db=app`.**
Deciding whether `cross_entity` is even available at all calls
`capability_document()`, which provisions its own separate capability-
probe application (a real database + 2 roles) the FIRST time it is
reached -- from the `cross_entity` op onward, that second application's
own connections sit alongside this run's own in whatever `prepared_
stats()` returns, but `db=app`'s own probe-commit correction (above)
only ever counts THIS run's own resolved cell, never that second
application's.

**Under `--roundtrip`, MitateDB's `POOL lock=` `acquire` carries ONE MORE
extra acquisition per op than without it.** The `## DBTIME lines (R-101)`
section above already notes that `DBTIME`'s own PRE probe (present on
EVERY op regardless of `--roundtrip`) lands on THAT SAME op's own `POOL
lock=` line, while its shared POST probe lands on the NEXT op's own line.
`--roundtrip` adds `ROUNDTRIP`'s own SEPARATE PRE probe, taken even
earlier (before warmup) but still before that op's own `POOL lock=` line
prints, so it too lands on the SAME op's own line -- three calls in total
across the two probed ops' own lines (two of this op's own, one carried
over from the preceding op's own POST) where two ran without
`--roundtrip` (one of this op's own, one carried over), so each op's own
`POOL lock=` line runs 1 higher under `--roundtrip` than without it, from
the very first op onward -- not just the last one. **R-80 時点の実測** (before `DBTIME`'s
own PRE probe existed, when the baseline was a single POST-only probe per
op): against the real, registered `MitateDB-api-http` plug (a throwaway-
cluster confirmation run, `--warmup 2 --n 5`, `perfbase_*` lock, `query`/
`mutate`/`batch`/`cross_entity` in order, not a `tools/tests` assertion):
`acquire=20/35/50/69` without `--roundtrip`, `acquire=21/37/53/73` with
it -- these two specific series are from that R-80-era baseline (one
probe per op) and are not re-measured against the current (two-probe)
baseline here.

## `REALPERF` / `REALCPU` lines

**`--real-server <peer>` measures a real, separately-started composition
root instead of the 6 registered conformance plugs** (work order
`docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`
§7.3 D-15, §9 WP-4)
-- the SAME C-26 launcher `conformance-tests/test_c26_composition_root.py`
drives (`conformance-tests/registry.json`'s own `composition_roots`
entry named `peer`), started and stopped as a real, separate OS process
pair (application + control, fronted by nginx), never the in-process/
ASGI-in-process composition the 6 plugs above measure. A `--real-server`
run measures `query` ONLY, and prints ONLY the two lines below -- never
`PERF`/`CPU`/`POOL`/`DBTIME`/`PREPARED`/`ROUNDTRIP`, and never both in one
invocation with the 6-plug path. Without `--real-server`, nothing here
changes: the launcher is never even instantiated.

```
REALPERF peer=<peer> plug=<peer>-real transport=real-server op=query concurrency=<K> client_processes=<N> n=<n> p50_ms=<x.xxx> p95_ms=<x.xxx>
REALCPU peer=<peer> plug=<peer>-real op=query concurrency=<K> client_processes=<N> requests=<n * K> wall_ms=<x.xxx> cpu_client_ms=<x.xxx>
```

Both lines print as one block, immediately after `PERFRUN`, with nothing
else printed between or before them.

**Why no server-side `CPU`/`DBTIME` line.** The measured server is a
separate OS process (in fact two: application and control), not this
tool's own process -- there is nothing in THIS process's own
`resource.getrusage`/`prepared_stats()` that could describe it. The floor
this measurement exists to demonstrate (work order `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`
§7.1's own "床の算術") is
precisely that client and server no longer share one process/one GIL --
see `cpu_client_ms=` below for the client side of that same floor.

**Window and denominator.** `--warmup`/`--n` mean exactly what they mean
for the 6-plug path (see "How to run it" above) -- `--concurrency K`
(default 1) is `--real-server`'s own load per measured sample: every
warmup and measured sample is one GROUP of `K` real, concurrent `query`
requests, dispatched across `min(--client-processes, K)` real OS client
processes (default `--client-processes 8`; see below), never `K`
sequential requests. Every client process is released together by a
shared `multiprocessing.Barrier`; a group's own start is the MINIMUM
of the children's own `time.time_ns()`, each read immediately after
ITS OWN barrier release -- never the parent's, which lags the first
child to resume by however long the parent itself takes to wake and
re-schedule -- and `wall_ms=` is the LATEST child's own completion
time minus that minimum. `n=`/`p50_ms=`/`p95_ms=` on `REALPERF` are
the MEASURED groups only -- a slow warmup group never enters the
printed distribution, exactly like the 6-plug path's own `PERF` line.
`REALCPU`'s own `requests=` is the number of MEASURED responses this
run actually observed (`n * K` when every measured group completes;
fewer than that aborts the run rather than printing an undercount);
`wall_ms=` is the sum of the measured groups' own wall-clock
spans (the same numbers `p50_ms=`/`p95_ms=` are computed from).

**`cpu_client_ms=` is a floor visualization, never a judgement this tool
makes (P-8).** It is the SUM, across every measured group's own client OS
processes, of that process's own `resource.getrusage(RUSAGE_SELF)`
difference (`ru_utime + ru_stime`) across the one `asyncio.gather` call
that group's own share of `K` requests went through -- the client-side
CPU cost of driving `K` real concurrent HTTP requests through a real TCP
+ TLS-less loopback stack, spread across real OS processes specifically
so it does NOT share a GIL with the measured server (or with this
harness's own process). D-16's closure judgement (query `p50` at `K=32`
within 8x of `K=1`, both peers, two runs) is made and recorded by the
supervisor from `REALPERF`'s own `p50_ms=` alone; `REALCPU` is recorded
alongside it for context, never compared against a threshold by this tool
itself.

**Launcher start/stop and cleanup.** `launcher.start(ceilings={"data": 1,
"control": 1})` runs once, at the top of a `--real-server` run;
`launcher.stop()` runs exactly once, in a `finally`, whether the run
succeeded, failed partway through the HTTP setup, or failed partway
through measurement (a non-200 `query` response mid-run aborts the WHOLE
run -- see below) -- a `--real-server` run never leaves the launcher's own
throwaway platform, processes, or bound ports behind. The launcher itself
is never modified by this flag: it is reused exactly as `test_c26_
composition_root.py` already uses it.

**Credential use, in order.** `launcher.control_bearer` issues ONE
developer credential (`POST /control/v1/credentials`, `role=developer`)
for this run's own application (its `application_id`, read from `GET
/v1/capabilities` via `launcher.runtime_bearer` -- the launcher's own
observation surface names no `application_id` property directly). That
developer credential -- never `control_bearer`/`runtime_bearer` -- creates
the one measurement entity (`POST /v1/schema/operations`) and seeds its
one row (`POST /v1/data/<entity>/mutations`). Every `query` request from
that point on, including the K=1 sanity check below, uses `launcher.
runtime_bearer` -- never the developer credential.

**The K=1 sanity check (空振り禁止, `OPERATING_CONDITIONS.md` 1.5-32).**
Before any concurrent measurement starts, this tool sends exactly ONE real
`query` request and confirms BOTH a `200` status AND at least one row in
the response -- a `200` with zero rows is refused exactly like a non-200
status is. Either failure aborts the run before any `REALPERF`/`REALCPU`
line is printed (a non-zero exit; `stop()` still runs).

**`client_processes=<N>` and the remainder.** The actual number of client
OS processes a run uses is `min(--client-processes, K)` -- never more
processes than there are requests in one group to spread across them.
Each client process sends its own share of one group's `K` requests via
exactly ONE `asyncio.gather` call, never one request at a time; when `K`
does not divide evenly by the process count, the remainder goes to the
FIRST that many processes, one extra request each (`K=10`, 4 processes:
`[3, 3, 2, 2]`, never `[2, 2, 3, 3]`).

**Staying under the server's own request budget.** Both peers' own
composition roots default to `requests_per_minute`/`max_requests_per_
minute` `600` (work order
`docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`
§7.5 (W-17) -- the composition root's own value; the conformance
adapter plugs' own `requests_per_minute` (`50`) is unrelated). A
`--real-server` run sends `(--warmup + --n) * K` measured/warmup
`query` requests plus 4 one-shot setup requests -- at
`K=32` with D-16's own `--warmup 3 --n 15`, that is `576 + 4 = 580`
of the `600` budget (20 to spare; `--n 16` already exceeds it); the
DEFAULT `--warmup 10 --n 100` at `K=32` would be `3520`, well over it
(the run aborts on the first `429`, never a silently wrong number).

**`--real-server` never builds one of the 6 registered plugs.** Only
`registry.json`'s own `composition_roots` section is read for this flag
-- its `adapters` section (the 6 plugs) is never touched, and no adapter
is ever built for a `--real-server` run.

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
