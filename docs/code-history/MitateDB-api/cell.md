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

## CH-0600

- moved from: `src/mitatedb_api/cell.py` (`_LimitStateHolder.acquire_rate`)
- parent commit: `6635064`
- kind: comment

```
# design D-3 (1): every worker this deployment runs shares
# ONE credential-keyed count. Reached from `ApplicationCell.
# _limit_gate` after `_require_data`'s own `assert_active`
# borrow has returned its connection -- sequential, never
# nested.
```

## CH-0601

- moved from: `src/mitatedb_api/cell.py` (`_LimitStateHolder.concurrency_slot`)
- parent commit: `6635064`
- kind: comment

```
# design D-3 (2): a wired host-shared slot directory admits this
# non-reserved caller through the SAME mechanism the pre-
# authentication entry below uses, never the in-memory counter.
```

## CH-0602

- moved from: `src/mitatedb_api/cell.py` (`_LimitStateHolder.acquire_concurrency_slot`)
- parent commit: `6635064`
- kind: docstring

```
Phase 10 WP-8c (design D-8 (3), review F-2): pre-authentication
concurrency admission -- the entry point `http.py` calls BEFORE
`_authenticate`, mirroring r2db `service.py::DataService.
acquire_concurrency_slot`'s own identical purpose and this peer's
own control-plane precedent for a pre-auth admission check taken
ahead of everything else.

Performs the SAME check-then-increment `concurrency_slot` above
performs (own copy, not a shared helper -- kept trivially small
and independently readable, matching r2db `service.py::DataService.
acquire_concurrency_slot`'s own identical choice and reasoning),
and additionally sets `_CONCURRENCY_RESERVED` for the duration of
the `with` block so a NESTED call to `concurrency_slot` above (from
`ApplicationCell._limit_gate`, reached once authentication and the
rest of this request's own dispatch complete) recognizes the slot
is already held and does not reserve a second one.

A refusal here raises `ResourceLimitError` directly, exactly like
`concurrency_slot` above already does -- reaching `http.py`'s own
`except FoundationError`-equivalent handling with no `_event`/
durable-audit call in between, so this denial is never durably
audited (there is no authenticated principal to attribute it to
yet, in any case).
```

## CH-0603

- moved from: `src/mitatedb_api/cell.py` (`_LimitStateHolder.acquire_concurrency_slot`)
- parent commit: `6635064`
- kind: comment

```
# design D-3 (2): a wired host-shared slot directory holds ONE
# `slot-<i>` file for the whole request and sets the SAME
# `_CONCURRENCY_RESERVED` marker, so the nested `concurrency_slot`
# call never takes a second one. A slot backend failure maps to
# `StorageConfigurationError` (`SERVICE_UNAVAILABLE`, 503), never
# to a refusal and never to an admission.
```

## CH-0604

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell`)
- parent commit: `6635064`
- kind: docstring

```
A private application storage boundary.

The default backend (`backend_sqlite.SQLiteBackend`) is used only as a
deterministic local foundation backend. `backend_postgres.
PostgresBackend` is the production-shaped Cloud SQL adapter (WP-1);
both keep this class's own authority shape identical, never exposing a
raw database connection to Application code.
```

## CH-0605

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.__init__`)
- parent commit: `6635064`
- kind: comment

```
# Phase 8 WP-1a (design D-1): `None` (every pre-WP-1a caller --
# this repository's own tests, any direct construction) gets a
# PRIVATE, unshared holder -- exactly like `audit_router=None`
# already defaults to a private `AuditRouter()` two lines above --
# so a lone `ApplicationCell()` still enforces its own 4 classes
# correctly, just without sharing state with any sibling cell (the
# composition root is what actually needs the SHARED instance;
# see `main.py`/`service.py`/both conformance adapters, which all
# construct exactly one holder and pass it to every cell they
# build).
```

## CH-0606

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._limit_gate`)
- parent commit: `6635064`
- kind: docstring

```
Phase 8 WP-1a rework 1 (裁定 5, 監督裁定 2026-09-06; design D-1
"順序"/"実装の形"): the single choke every application-plane
operation below (`insert`/`read`/`update`/`delete`/`transact`,
`catalog`/`schema_revision` immediately above, `ApplicationRuntime.
capabilities()`, and `ApplicationDeveloper`'s own schema
operations) passes through, immediately after its own
`_require_data`/`_require_developer` call -- in the r2db-matching
order `requests_per_minute -> concurrency -> request_bytes ->
operation_depth -> deadline` (r2db `service.py::_slot`
`:1133-1144`/`:1156-1163`, `_query_outcome`/`_mutate_outcome`
`:996-999`/`:1037-1039`).

`request` is the JSON-safe structure this call's own arguments
amount to (built by the caller, immediately before this is
entered) -- `None` for an operation with no client-supplied
structure to bound (`catalog`/`schema_revision`/`capabilities`):
those still pass through the rate/concurrency wrap (mirrors r2db
`catalog()`/`schema()`/`capabilities()`, which all wrap with
`_slot` but never call `check_request`/`check_depth`), just never
the request_bytes/operation_depth checks. (裁定 5 correction: an
earlier revision of this docstring already stated this, but the
code did not yet match it -- `catalog`/`schema_revision`/
`capabilities` were NOT actually wrapped by this gate until this
rework commit; see each of those three methods' own docstrings
for the measured, pre-rework gap this closes.)

Yields the computed wall-clock `deadline` (`time.monotonic()`
seconds) for the caller to hand to `self._backend`.

`budget`/`endpoint_kind` (Phase 9 WP-3cd closure, design D-6,
監督裁定集約 rulings-r5-r6.md K-1/B-2/B-3 -- supersedes the WP-3d
`effective_limits` parameter this replaces): `budget` validity
(applicable class / integer >= 1 / not above the deployed bound --
`config.narrow_limits_by_budget`, which is what actually raises
`errors.ValidationError` for an invalid one) is now checked HERE,
AFTER `requests_per_minute`/`concurrency`/`request_bytes`/
`operation_depth` above have all already passed, and BEFORE the
`deadline` below is computed from the result -- the exact r2db
order (`_slot` -> `check_request` -> `check_depth` -> `narrow_
limits_by_budget` -> `deadline = ... effective_limits.execution_ms
...`, `service.py::_query_outcome`/`_mutate_outcome`) this WP's
own audit (audit-wp3cd.md §3) found MitateDB did NOT match: every
pre-closure caller computed `effective_limits` at the FACADE layer
(`ApplicationRuntime.read`/`.transact`, `ApplicationDeveloper.*`),
before this gate was ever entered, so an invalid `budget` on a
request that ALSO exceeded (say) the rate limit surfaced
`VALIDATION_FAILED` instead of r2db's `LIMIT_EXCEEDED` for the
identical combination -- an observable peer asymmetry (裁定 I-3
groups all seven bounds -- rate/concurrency/request_bytes/
operation_depth/shape/capability/budget -- without ordering
WITHIN the group, but K-1 now fixes MitateDB's own position to
match r2db's, closing the asymmetry rather than leaving it to a
future conformance gap). `None`/falsy `budget` (every pre-WP-3d
caller, and every WP-3d+ caller that simply never presented one)
makes `narrow_limits_by_budget` return `self.config` unchanged --
identity-shaped, so `max_requests_per_minute`/`max_concurrency`/
`max_request_bytes`/`max_operation_depth` above are ALWAYS read
from `self.config` directly (those four are never budgetable --
D-6 (2)'s own three-class table -- so there is no reason for this
gate to defer reading them until after a budget it cannot affect
is resolved); only `max_execution_ms`, read below to build
`deadline`, is ever narrower than `self.config`'s own value.
Callers that need the resolved `FoundationConfig` themselves (for
a check point past this gate's own `with` block, e.g. `read`'s
`max_result_rows` or `transact`'s `max_batch_items`) call `config.
narrow_limits_by_budget(self.config, budget, endpoint_kind)`
again, once past this gate's `__enter__` -- a second call to the
SAME pure function, already proven not to raise by this gate's
own successful entry, never a second, independently-drifting
computation.
```

## CH-0607

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._make_audit_hook`)
- parent commit: `6635064`
- kind: docstring

```
Phase 4 (design D-2): builds the `audit_hook.ApplicationAuditHook`
a backend method (or `transact` below) calls itself, immediately
before its own commit point. Every field the durable row needs is
already resolved here -- the backend/batch loop supplies none of
it, only the moment.
```

## CH-0608

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._write_replayed_data_operation_event`)
- parent commit: `6635064`
- kind: docstring

```
`transact`'s own idempotency-REPLAY counterpart of the row a
fresh batch writes: the SAME `event_class="data_operation"`
(a mutate replay is never LESS durable than a fresh success --
even when the replayed batch was itself destructive, a resend must
leave SOME evidence, not necessarily the original commit's own
class), written synchronously before the replayed response is
returned (`errors.AuditSinkUnavailable` when the sink cannot
record it -- the replay is not answered). `request_id` is THIS
replay request's own id (never the original's -- correlation with
the original is the RESPONSE's own `request_id`, contract
`idempotency.correlation`). `outcome="replayed"` -- never `key`,
which never reaches this call at all (I-11).
```

## CH-0609

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._write_replayed_schema_event`)
- parent commit: `6635064`
- kind: docstring

```
Phase 9 WP-3cd closure (design D-5 (1)(v), 監督裁定集約
rulings-r5-r6.md J-4/SI-14): `create_collection`/`add_field`/
`alter_field`'s own idempotency-REPLAY counterpart of `_make_
audit_hook`'s own `event_class="schema_change"` pre-commit hook
-- schema operations are UNCONDITIONALLY fail-closed class (D-2
item 2), so their replay line is too (`AuditRouter.write_
replayed_fail_closed_event`, raises `errors.AuditSinkUnavailable`
if the durable sink cannot record it, rather than silently
answering the replay with zero evidence). `request_id` is THIS
replay request's own id, never the original's; never `key`
(I-11).
```

## CH-0610

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: docstring

```
Phase 6 WP-3 (design D-3): `field_types`, when given, is a
`{field_name: contract_type}` map (the 7-word contract vocabulary,
`field_types.CONTRACT_TYPES`) -- the declared type this call
records in the registry for that field. A field named in `fields`
but NOT in `field_types` (or every field, when `field_types` is
`None` -- every pre-1.6.0-shaped direct caller: this repository's
own tests, the in-process conformance adapter) gets its declared
contract type DERIVED from the foundation type it was given
(`field_types.FOUNDATION_TYPE_TO_CONTRACT_TYPE`) -- the same
backfill rule `migrations/0006_...upgrade_declared_types.sql`
applies to pre-existing columns (design §1.5 finding 2a).

Phase 9 WP-3a (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)):
`field_constraints`, when given, is a `{field_name: {"enum": [...],
"nullable": bool}}` map, PARTIAL over `fields` (contract
`SchemaOperationRequest.field_constraints.description`: "any name
in fields it omits is created with no enum and nullable: true").
A name in `field_constraints` that is not in `fields` fails
`VALIDATION_FAILED` -- none of it is silently ignored.

Phase 9 WP-3b (design D-4): `dry_run`/`plan` -- see `add_field`'s
own identical paragraph immediately below for the full contract;
this method follows it exactly, with `create_collection` itself
as the schema operation each `dry_run`/`plan` behavior applies
to.
```

## CH-0611

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# Phase 9 WP-3e (design D-7 (3), Q-1): resolved here, before
# anything else -- the audit events below and this method's
# own returned `SchemaOperationResult.request_id` (added to
# `result` further below) both read this SAME resolved value.
```

## CH-0612

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# Q1-D11 (design v1.5 §7, supersedes the WP-5 body's own
# `query_complexity` tagging): this bounds how many columns a
# single collection DEFINITION may name in one `create_
# collection` call -- a one-time shape bound on the request
# itself, not a repeated, finite-resource consumption class.
# WP-3e rework T1 (追補 L-1): `request_schema`, mirroring
# r2db-api's own "Mutation contains too many fields"
# treatment for the SAME `maxProperties`-style shape
# bound -- `field` names the container the bound applies
# to, not any one entry inside it.
```

## CH-0613

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): `enum` -- the declared
# type name itself must be a member of the closed
# foundation-type vocabulary; mirrors r2db-api's own
# `field_types/<name>` "Unsupported field type"
# treatment (`violated_declaration: "enum"`,
# `declared_type: "string"`, no `observed_type` --
# the violation is about the vocabulary MEMBERSHIP of
# the declared name, not about a value's type).
```

## CH-0614

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# 監督裁定 N-2 (2026-09-07, wp3a-closure2): a
# non-object `field_constraints` is a request-shape
# violation about the top-level `field_constraints`
# key's own type -- the same `request_schema` shape
# `create_entity`'s sibling "field_constraints without
# fields" refusal already carries (below), so both
# `field_constraints` defects report the identical
# `details` vocabulary. `declared_type`/`observed_type`
# are omitted here (unlike the per-field `nullable`
# value-type violations above) because this D-3 (3)
# branch is reserved for a violation about the type of
# a VALUE, and `field_constraints` at this position is
# a container the request declares, not a value being
# checked against a field's own declared type.
```

## CH-0615

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# WP-3a rework 2 (監督裁定 m-1, 2026-09-07): "a
# declaration naming a field the request does not
# create" -- the 4th `constraint_declaration` case.
# No `declared_type` (the named field is never
# created by this request, so it has none).
```

## CH-0617

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# `digest_request` (rework, 監督裁定 G-1; Phase 9 WP-3c
# rework): built ABOVE, before this method's own
# idempotency choke -- see that hoisted block's own
# comment for the full per-key rationale (`operation`/
# `entity`/`fields`/`field_types`/`field_constraints`/
# `digest_extra`/`idempotency_key`, unchanged from the
# pre-hoist version this replaces). `compute_plan_token`
# excludes only `plan`/`dry_run`, so an `idempotency_key`
# this object carries (I-13) is part of what THIS token
# commits to too.
```

## CH-0618

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `6635064`
- kind: comment

```
# Phase 4 (design D-2 item 2): every schema operation is
# unconditionally fail-closed class -- the hook's own `pre_commit()`
# is called by `self._backend.create_collection` itself, as the
# last thing it does before its own commit point. Phase 9 WP-3b
# (design D-4 (4), §5 U-2 = (A)): NOT built at all for a dry
# run -- no audit hook, no audit event, not even an attempt.
```

## CH-0619

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_entity`)
- parent commit: `6635064`
- kind: comment

```
# WP-3a closure (監督裁定 2026-09-07, audit §3 G3): D-3 details
# -- this is a missing-key request-shape violation, not one
# about a value's own type, so `declared_type`/`observed_type`
# are omitted per D-3 (3).
```

## CH-0620

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: docstring

```
P3-D1 (design v1.1 §0 exception, WP-1): the one capability-
envelope addition this phase makes -- `schema_operations.add_field`,
developer-only, on BOTH backends (declaration and implementation
land in this same commit). Adds one column to an EXISTING
collection; see the module-level comment above (now in `request_vocabulary.py`) `_DELETE_
CONSEQUENCE` for why this is also what makes a schema-revision
fingerprint necessary in the `delete` confirmation phrase.

Phase 6 WP-3 (design D-3): `contract_type`, when given, is the
7-word contract vocabulary type this call records in the
registry for `field` (`http.py`'s own `add_field` handler always
supplies it -- `SchemaOperationRequest.field_type` is required
there). `None` (every pre-1.6.0-shaped direct caller) derives it
from `field_type` via the same backfill rule `create_collection`
uses.

Phase 9 WP-3a (design D-2 (1)): `enum`/`nullable`, when given,
are this one new field's own `field_constraints` declaration --
validated (`field_types.validate_enum_declaration`, `enum_members`)
and written to the constraint registry BEFORE anything is
created, same as `create_collection`'s own `field_constraints`.

Phase 9 WP-3b (design D-4): `dry_run` (bool) asks this call to
reach the SAME decision a real call would -- every gate above
still runs, in the SAME order -- and then leave nothing behind:
no column, no registry write, no revision bump, no audit event
(§5 U-2 = (A)). Its response carries `committed: False`, the
`descriptor` the entity would have afterwards, and `revision` as
it stands NOW (the value the returned `plan` was taken against),
never the value this call would establish. `plan`, when
presented (`str | None`), is checked against a fresh digest of
this exact request and the Application's current schema
revision (`compute_plan_token`/`check_plan_precondition`,
module-level above) -- a mismatch refuses the WHOLE call with
`errors.PreconditionFailedError` before anything is touched,
real or dry. A dry run always returns a fresh `plan` of its own
(`SchemaOperationResult.plan`, optional); a real (non-dry-run)
call never returns one, whether or not the request itself
presented one to be checked (Minor m-1, review: fixed to match
the actual, measured behavior -- `result["plan"]` is only ever
set inside `if dry_run:` below, never on the real-call path;
there is nothing left to preview once a real call has already
committed).
```

## CH-0621

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 9 WP-3e (design D-7 (3), Q-1): resolved here, before
# anything else -- the audit events below and this method's
# own returned `SchemaOperationResult.request_id` (added to
# `result` further below) both read this SAME resolved value.
```

## CH-0622

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): mirrors `create_collection`'s
# own identical per-field check above -- `add_field`'s
# single scalar `field_type` key is its own request
# position (matches r2db-api's own `add_field` site,
# `field="field_type"`).
```

## CH-0623

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# WP-1c ext -- see `create_collection`'s identical
# comment for the rationale (契約 1.7.0 idempotency.
# record).
```

## CH-0624

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-3/I-7): checked before
# `field_domains` immediately below -- this method's own
# target-existence check.
```

## CH-0625

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): `request_schema`, `field`
# names the request key this bound is about -- `add_field`
# has no plural container to point at (unlike `create_
# collection`'s own `fields`), so this points at the one
# new field name the request itself carries.
```

## CH-0626

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# `digest_request` (rework, 監督裁定 M-1/G-1; WP-3b closure
# H-3 (a); Phase 9 WP-3c rework): built ABOVE, before this
# method's own idempotency choke -- see that hoisted
# block's own comment for the full per-key rationale
# (`field_type` sourced from `contract_type`, the RAW
# argument, never the resolved `declared_type` -- H-3 (a),
# unchanged by this hoist). `compute_plan_token` excludes
# only `plan`/`dry_run`, so an `idempotency_key` this
# object carries (I-13) is part of what THIS token commits
# to too.
```

## CH-0627

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 4 (design D-2 item 2): same unconditional fail-closed
# pre-commit hook as `create_collection` above. Phase 9 WP-3b:
# not built at all for a dry run.
```

## CH-0629

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: docstring

```
Phase 9 WP-3a (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (5)/
(6)): redeclares `field`'s own `enum`/`nullable` constraints.
`field_type` is accepted only so `field_type is not None` can be
refused explicitly (contract `structured_operations.alter_field`
description: "an alter_field carrying field_type fails
VALIDATION_FAILED...because converting values already stored
under one type into another is not defined by this version",
§4 A-2) -- `alter_field` never redeclares a field's own type.

Code review §2 A / 監督裁定 A (2026-09-07): `enum` is tri-state --
the sentinel default `backend.UNCHANGED` (the request omitted
`enum` entirely) leaves the field's current `enum` exactly as it
is; an explicit `enum: null` (`enum=None`, distinguishable from
omission only because the default is the `UNCHANGED` sentinel,
never a plain `None`) CLEARS it; any other value (a non-empty
`list`) SETS/REPLACES it, exactly as before this rework. This is
the one new client-visible meaning `alter_field` gains here --
design D-2 (5)'s own "enum の設定・置換・解除" ("sets, replaces or
clears", contract `structured_operations.alter_field`) was, before
this rework, only two-thirds implemented (no client-reachable way
to express "解除"/"clears"). `http.py`'s own HTTP dispatch is the
one caller that can observe the wire distinction between an
omitted `enum` and an `enum: null` (`body.get("enum", UNCHANGED)`)
-- every direct/in-process caller expresses it the identical way,
by omitting the keyword or passing `enum=None` explicitly.

Code review §2 H / 監督裁定 H (2026-09-07): the `field_type`
rejection below now runs INSIDE `_limit_gate` (rate/concurrency/
request_bytes/operation_depth), at the same validation stage
every other `alter_field` check (identifier syntax, `nullable`'s
own type check, `enum` validation) already runs at -- previously
it ran BEFORE the gate entirely, so a request this large could
reach a definitive answer without ever being counted against
rate/concurrency or measured for `request_bytes`/`operation_
depth`, unlike `add_field`/`create_collection`'s own unsupported-
shape refusals, which have always run inside their own gates.

Refuses (`errors.ConflictError`, `CONFLICT`) in full, changing
NOTHING -- not even the schema revision -- if any existing row
would violate the constraints this call would establish; a
non-conflicting call advances the schema revision. The
existing-row scan, the registry write, and the revision bump all
happen inside ONE transaction on the backend (`alter_field_
constraints`), never a separate pre-flight scan in a different
transaction from the one that commits the change (design D-2
実装の形 4, F-6, 監督裁定 S-g).
```

## CH-0630

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 9 WP-3e (design D-7 (3), Q-1): resolved here, before
# anything else -- the audit events below and this method's
# own returned `SchemaOperationResult.request_id` (added to
# `result` further below) both read this SAME resolved value.
```

## CH-0631

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# 監督裁定 N-1 (2026-09-07, wp3a-closure2): an alter_field
# carrying neither enum nor nullable declares nothing --
# refused with VALIDATION_FAILED before the schema is
# touched (no collection/field lookup above this line, so
# this always wins over NOT_FOUND for a nonexistent
# collection too: the request is defective on its own
# terms regardless of what it names). `field` is
# "operation" (design D-3 (2)'s request-relative path):
# the missing declaration is a defect of the operation as
# a whole, not of any single top-level key.
```

## CH-0632

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# WP-1c ext -- see `create_collection`'s identical
# comment for the rationale (契約 1.7.0 idempotency.
# record).
```

## CH-0633

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-3/I-7): checked before
# `field_domains` immediately below -- this method's own
# target-existence check.
```

## CH-0634

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# WP-3a closure (監督裁定 2026-09-07, audit §3 G3): the
# request NAMES a field the entity does not have -- a
# constraint-declaration violation (`errors.details_
# vocabulary.violated_declaration_vocabulary`'s own
# `constraint_declaration` word: "a declaration naming a
# field the request does not create"), not a request-
# shape one; `field` echoes the request's own top-level
# `field` key (design D-3 (2)), never a type pair (D-3
# (3): this is not a violation about a value's own type).
```

## CH-0635

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# `digest_request` (rework, 監督裁定 G-1; Phase 9 WP-3c
# rework): built ABOVE, before this method's own
# idempotency choke -- see that hoisted block's own
# comment for the full per-key rationale (`field_type`
# never included -- the `field_type is not None` check
# above always refuses first, unchanged by this hoist).
# `compute_plan_token` excludes only `plan`/`dry_run`, so
# an `idempotency_key` this object carries (I-13) is part
# of what THIS token commits to too.
```

## CH-0636

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `6635064`
- kind: comment

```
# Phase 4 (design D-2 item 2): same unconditional fail-closed
# pre-commit hook as `create_collection`/`add_field` above.
# Phase 9 WP-3b: not built at all for a dry run.
```

## CH-0637

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.schema_revision`)
- parent commit: `6635064`
- kind: docstring

```
m-2 (independent WP-3 review): the SAME monotonically-increasing
counter `_validate_delete_confirmation` already reads to fingerprint
a delete confirmation phrase (`_delete_confirmation_phrase`), now
also exposed as a read-only, authorized query -- so the HTTP
surface's `SchemaOperationResult.revision` field can report this
peer's REAL current schema-revision value after a `create_entity`/
`add_field` call, rather than a hardcoded placeholder that would
never actually change (a false declaration: the contract's own
`SchemaOperationResult.revision` field implies a real, observable
value, and always returning the same literal after every schema
change is not honest about what the peer just did).

Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): WRAPPED by
`_limit_gate` (rate/concurrency only -- `request=None`, exactly
like `catalog` immediately below and r2db's own `catalog()`/
`schema()`, which wrap `_slot` but never call `check_request`/
`check_depth`, `service.py:996-1000`/`:1072-1074`): this is a
real, client-callable, authenticated application-plane query
(`ApplicationRuntime.schema_revision()`, the in-process port's own
`session.schema_revision()`), not exempt from the request-rate/
concurrency bound SI-08 requires on every credentialed call --
r2db's own equivalent (`schema()`/`catalog()`) is bound this way
too (`service.py:1133-1144`/`:1156-1163`'s `_slot`), so leaving
THIS peer's version unbound left an authenticated credential able
to hit `schema_revision`/`catalog` at unlimited rate/concurrency
while every other application-plane call was bound -- a real,
peer-specific gap the code review that sent this WP back found
(measured: `rpm=50` with `catalog()` called 500 times in a row,
zero denials, zero window consumption, pre-rework).

`http.py::post_schema`'s OWN post-op revision readback does NOT
go through this method any more -- see `_schema_revision_
uncounted` below and `ApplicationRuntime._post_schema_revision`'s
own docstring for why that separate, ungated internal accessor
exists (this method's own gating would otherwise silently double
the effective `requests_per_minute`/`concurrency` cost of every
HTTP schema operation relative to the in-process surface, whose
own `create_entity`/`add_field` never make this extra call at
all -- the SAME asymmetry finding the WP-1a report already made,
just resolved the other way: gate the real client-facing query,
exempt the internal wire-formatting readback, rather than
exempting both).
```

## CH-0730

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.insert`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3a (design D-2 (3), "検査順序は欠落検査 -> 値検査"):
# a `nullable: false` field this insert simply does not name is
# never handed to `check_declared_value` at all (that choke
# point only ever sees VALUES actually present) -- checked
# here, immediately before `_prepare_values`, on this peer's
# own direct single-operation insert entry point (the in-
# process conformance adapter's own `attempt_mutation`
# dispatches "insert" here, never through `_plan_operation`
# below -- WP-3a report discloses this second insert entry
# point; design D-2 (3)'s own file:line names only `_plan_
# operation`'s insert branch).
# Code review §2 C / 監督裁定 C (2026-09-07): the ONE fetch
# `_check_missing_required_fields` makes is reused by
# `_prepare_values` immediately below (`prefetched=`) --
# this insert makes one backend round trip for declared
# types/constraints, not two.
# Phase 9 WP-3e rework (裁定 C-21 (B)/監督裁定 N-4, 2026-09-08):
# `path_prefix` is `"operations/0/values"`, not the bare
# `"values"` this used before -- N-4 requires every VALUE-
# position `details.field` to read `operations/<i>/values/
# <field>` UNCONDITIONALLY (rulings-r2-closure.md; mirrors
# r2db-api's own `structured.py::_apply`, whose `values_path`
# is `f"operations/{operation_index}/values/"` for every
# mutation, including a solo one -- there is no wire shape
# that omits the `operations` envelope: `http.py::post_mutate`
# always builds `{"operations": [...]}`, so this direct,
# single-operation in-process entry point occupies the SAME
# request-internal position (`operations/0/...`) a real client
# submitting one operation would, even though this method's
# own Python-level `values` argument carries no such envelope.
```

## CH-0731

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.read_page`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3e (design D-7 (3), Q-1): resolved here, once, so the
# audit event below and this call's own caller (who already holds
# the SAME value when it is `http.py`'s own per-request id, and
# generates a fresh one itself otherwise -- `read()` has no
# return-shape room of its own to echo a self-generated value
# back through, unlike `transact()`/the schema methods below,
# whose dict/list-shaped returns do) always agree.
```

## CH-0732

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.read_page`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3cd closure (K-1): `narrow_limits_by_budget` is
# no longer called at the facade layer, before this gate --
# `self._gate` above already validated `budget` (raising
# VALIDATION_FAILED there, AFTER rate/concurrency/request_
# bytes/operation_depth, if it is invalid) and used it to size
# its own `deadline`. This second call is the SAME pure
# function, on the SAME inputs, already proven not to raise by
# the gate's own successful entry -- it resolves `limits`, the
# ONE narrowing point `result_items` reads through below (the
# check itself is unchanged in SHAPE, still driven by the
# REQUESTED `limit` value, never the row count actually
# returned, L9-11).
```

## CH-0733

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_update`)
- parent commit: `987b004`
- kind: docstring

```
m-1 (independent review, P3-D2 follow-up): the single choke
BOTH `ApplicationCell.update` below AND `transact()`'s own
batch-embedded update branch (`_plan_operation`, since P35 WP-2's
two-pass restructuring) pass through -- identical four-step validation (non-empty `filters`
shape check -> `_prepare_values` -> non-empty `fields` check ->
`_bind_filters`), so a batch-embedded update is held to exactly
the same mass-operation guard as the dedicated method, never a
looser one. Mirrors `_validate_delete_confirmation`'s own role for
`delete` -- there is no second definition of this validation
anywhere in this file.

`path_prefix` (code review §2 D, 監督裁定 D 2026-09-07): forwarded
to `_prepare_values` verbatim -- `"operations/0/values"` for a
direct `update()` call, `"operations/<i>/values"` for one batch
item (N-4's "no wire shape omits the operations envelope"
convention).

Returns `(collection, fields, values_params, bound_filters)` on
success. Does not execute the update itself and does not touch the
backend's transaction state beyond its catalog reads on `scope` --
callers own both, same division of responsibility as
`_validate_delete_confirmation`.
```

## CH-0734

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_update`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3e (design D-3 (2)): `where`'s own request-
# relative path is `path_prefix`'s own sibling -- `"operations/
# 0/where"` for a direct `update()` call, `"operations/<i>/
# where"` for one batch item. WP-3e rework T2 (追補 L-3/M-4):
# the wire contract's own predicate container is named
# `where` (`ScopedMutation.where`/`Mutation.where`), never
# `filters` (this module's own internal Python parameter name
# only) -- the label this raise used to carry was wrong.
```

## CH-0735

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_update`)
- parent commit: `987b004`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): unreachable in practice --
# `_prepare_values` above already guarantees a non-empty
# `fields` whenever it returns without raising (every key of
# its own non-empty `values` argument either raises or is
# appended) -- kept as a defensive `request_schema` guard
# rather than removed (matching this module's own pre-
# existing defensive style, `field_types.check_declared_
# value`'s "unknown declared field type" branch), now with
# the same `details` its unreachable-in-practice sibling
# sites carry.
```

## CH-0736

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_delete_confirmation`)
- parent commit: `987b004`
- kind: docstring

```
P3-D2 (design v1.2 R-5, WP-1.5): the single choke BOTH
`ApplicationCell.delete` below AND `transact()`'s own
batch-embedded delete branch (`_plan_operation`, since P35 WP-2's
two-pass restructuring) pass through -- identical shape checks, identical schema-revision-
fingerprinted phrase construction (`_delete_confirmation_phrase`),
identical exact-match comparison, identical four-key `details`
shape on failure. A batch-embedded delete is therefore held to
EXACTLY the same declare-and-echo requirement as the dedicated
method, never a looser one -- there is no second, batch-specific
copy of this logic anywhere in this file.

`destructive` missing is equivalent to `False` (contract
`valid_confirmation`); a valid confirmation requires BOTH
`destructive is True` AND `confirm` to exactly equal the server's
own currently-recomputed `required_confirmation` for this exact
request (Unicode code point sequence, no normalization -- a plain
`!=` string comparison already has this property). A non-bool
`destructive`/non-str `confirm` is a shape defect
(`ValidationError`), not a confirmation mismatch -- truthy
acceptance of either is exactly the defect WP-0/WP-3's own B-1
finding (r2db-api) forbids, applied here identically (WP-5 R-5).

Returns `(collection, bound_filters)` on success; raises
`DestructiveConfirmationRequired` otherwise. Does not execute the
delete itself and does not touch the backend's transaction state
beyond its catalog reads on `scope` (the request's own scope, with
the entity's shared lock already taken) -- callers own both. It runs
from `_plan_operation` during pass 1 of `transact()`, and from
`delete()` before the delete itself.
```

## CH-0737

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_delete_confirmation`)
- parent commit: `987b004`
- kind: comment

```
# B-3 (WP-0/WP-5): identifier + filter-shape validation (which,
# via `_bind_filters`'s own `field_domains` call, also performs the
# contract's own "target-existence checks" step) must complete
# BEFORE the confirmation check below -- a phrase must never
# reflect an unvalidated client-supplied collection name back to
# the client, and evaluation_order requires target existence to be
# settled before confirmation validity is evaluated.
```

## CH-0738

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.delete`)
- parent commit: `987b004`
- kind: comment

```
# Phase 4 (design D-3): `DESTRUCTIVE_CONFIRMATION_REQUIRED` is
# a durable-range denial code -- routed (coalesced) before
# re-raising, unchanged, to the caller.
```

## CH-0739

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.delete`)
- parent commit: `987b004`
- kind: comment

```
# Phase 4 (design D-2 item 1): delete is fail-closed class only
# once it has passed the confirmation choke (this point) -- the
# hook's own `pre_commit()` is called by `self._backend.delete`
# itself, as the last thing it does before its own commit point.
```

## CH-0740

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._plan_operation`)
- parent commit: `987b004`
- kind: docstring

```
P35 WP-2 (R-1, design docs/design/PHASE35_CROSS_ENTITY_AND_
CONTRACT_130_V1.md §2): builds one fully-bound, side-effect-free
plan step for a single `transact()` operation-dict -- identical
shape/capability checks and identical validation chokes
(`_prepare_values`/`_validate_update`/`_validate_delete_
confirmation`, the pre-existing `_TRANSACT_*_KEYS` excess-key
checks) as before this WP, just no longer interleaved with any
OTHER operation's own execution. Never touches the DML
(`_runtime`) transaction state (no `begin`/`commit`/`rollback`,
no `..._in_transaction` call): the read-only catalog calls this
method makes (`field_domains`/`schema_revision`, via `_prepare_
values`/`_bind_filters`/`_validate_delete_confirmation`) run on
`scope`'s developer connection, a separate transaction from the
runtime connection's that pass 2 alone writes in, and commit
nothing.

Returns `("insert" | "update" | "delete", payload)` on success,
`payload` a plain tuple of exactly the arguments the matching
backend `..._in_transaction` method needs. Raises the identical
`FoundationError` subclass, for the identical reason, that the
pre-WP-2 in-loop branch below used to raise for this same
operation shape -- this is a relocation of that logic, not a
second copy of it (the module's own `_TRANSACT_INSERT_KEYS`/
`_TRANSACT_UPDATE_KEYS`/`_TRANSACT_DELETE_KEYS`/
`_CONTRACT_MUTATION_VOCABULARY` constants (now in `request_vocabulary.py`) are unchanged, and
`_prepare_values`/`_validate_update`/`_validate_delete_
confirmation` are the exact same single chokes `insert`/`update`/
`delete` above also use.

`index` (code review §2 D, 監督裁定 D 2026-09-07): this
operation's own position in `transact()`'s `operations` list --
used only to build the request-relative `path_prefix`
(`f"operations/{index}/values"`) a `_prepare_values`/`_check_
missing_required_fields` violation's own `details.field` is
joined onto (design D-3 (2): `field` names a POSITION IN THE
REQUEST, and only this method's own caller, `transact()`'s pass-1
loop, knows which list position `operation` came from).
```

## CH-0741

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._plan_operation`)
- parent commit: `987b004`
- kind: comment

```
# Only "upsert" ever reaches here -- P3-D2 (WP-1.5) converged
# `update`/`delete` to real execution above. Per
# `capability_status.rules` ("optional target operations ...
# must fail with CAPABILITY_UNSUPPORTED"), this is a
# capability gap, not a malformed request.
```

## CH-0742

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._distinct_batch_entities`)
- parent commit: `987b004`
- kind: docstring

```
P35 WP-2 (R-2): the set of DISTINCT `collection` names named
across the raw, not-yet-validated operation dicts -- the same
entity may repeat across multiple operations without counting
twice (contract `endpoints.cross_entity_mutate.semantics`:
"batch_entities bounds the number of distinct entity names
referenced across operations[] ... the same entity may appear in
more than one operation, and total operation count remains
bounded by batch_items independently"). Deliberately reads the
RAW dicts (a non-dict operation is simply skipped here -- its own
malformed shape is a `_plan_operation` concern, reached
immediately after this check) rather than the validated plan, so
this whole-batch shape bound is evaluated symmetrically with the
`batch_items` check immediately above it in `transact()`: both
are checked before any single operation's own validation begins.

Independent review B-1 (WP-2 follow-up): a `collection` value
that is present but not itself a string (e.g. `["t"]`, `{}`) must
be SKIPPED here too, not added to the set -- adding an unhashable
value would raise a bare `TypeError` out of this whole-batch
pre-check, before `_plan_operation` ever gets a chance to
classify that same malformed operation as an ordinary
`ValidationError` (its own proper job). This mirrors the
non-dict-operation skip immediately above: a shape defect at
THIS layer is deferred to `_plan_operation`, never raised here as
an unclassified exception.
```

## CH-0743

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: docstring

```
P3-D2 (design v1.2 R-5, WP-1.5): `insert`/`update`/`delete` all
execute for real here, atomically with everything else in the
same batch -- converging this entry point's real behavior onto
the existing `atomic_mutation.operations` declaration (unchanged
by this WP). `upsert` alone remains a real capability gap: no
execution path for it exists anywhere on this peer.

The whole batch commits or rolls back as one unit (contract "A
batch is atomic unless explicitly declared best_effort" --
`best_effort_transactions: unavailable`, unchanged): a mid-batch
failure of ANY kind (a shape defect, a missing/wrong destructive
confirmation, a unique-constraint conflict, a collection that does
not exist) discards every write already performed earlier in the
SAME batch, insert included -- `self._backend.rollback()` in the
`except` clause below is the one and only rollback point for the
whole batch, reached from every operation type's own failure path.

P35 WP-2 (R-1, design docs/design/PHASE35_CROSS_ENTITY_AND_
CONTRACT_130_V1.md §2, P35-D9/P35-D10/P35-D11): two-pass as of
this WP -- ALL operations across ALL entities are validated first
(`self._plan_operation`, side-effect-free, building a fully-bound
execution plan), and `self._backend.begin()` is never called at
all until that whole-batch validation pass has succeeded end to
end. Only then does the second pass execute the plan inside the
begin/commit/rollback envelope below. This entry point is shared
by both the single-entity HTTP path (`http.py::post_mutate`) and
the cross-entity one (`http.py::post_cross_entity_mutate`) --
neither is a second copy of this method, so both are two-pass by
construction. Atomicity itself (all-or-nothing) is UNCHANGED by
this restructuring; the one externally-observable consequence
(P35-D9) is that a batch mixing an operation that would have
failed at BACKEND EXECUTION time with a LATER operation that
fails VALIDATION now surfaces the validation error (previously,
the earlier operation's execution-time error could surface first,
after already having reached the backend, since the old single
pass validated-then-executed each operation in strict order
before ever looking at the next one's own type) -- the validation
error winning is the contract-required priority
(`transactions.cross_entity`), adopted deliberately (M-7). The
internal ordering itself (validate-all, then execute-all) is not
black-box observable and is not a conformance-suite concern
(P35-D10) -- it is pinned locally, structurally, by this
package's own tests (a wrapped/monkeypatched backend proving zero
`..._in_transaction`/`begin` calls happen when a later operation
fails validation).
```

## CH-0744

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3e (design D-7 (3), Q-1): resolved ONCE, here, before
# anything else -- every audit event this method emits below
# already takes `request_id=request_id` (unchanged), and the
# commit-path envelope folded into `results[-1]` (below) echoes
# this SAME resolved value, so the response `MutationResult.
# request_id` a caller reads back is provably the one this
# request's own audit evidence carries too.
```

## CH-0745

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1/I-3): `idempotency_key` has two
# entry points into this method -- this KEYWORD (`http.py::
# post_mutate`/`post_cross_entity_mutate` already hold the single
# request-level `MutationRequest.idempotency_key`/`ScopedMutation
# Request.idempotency_key` value and pass it here directly), or
# folded onto EVERY operation dict (the port's own `fold_batch_
# idempotency_key`, `conformance-tests/adapter.py` -- every
# in-process caller reaches this method this way, never via the
# keyword). When the keyword is `None`, the first operation
# carrying a non-`None` `idempotency_key` supplies it -- the
# adapter's own fold already guarantees every operation in one
# batch carries the IDENTICAL value (or none at all), so reading
# just the first is sufficient; `_TRANSACT_INSERT_KEYS`/`_UPDATE_
# KEYS`/`_DELETE_KEYS` above (now in `request_vocabulary.py`) all list this key so it is never
# rejected as an unread capability-shaped field, and `_plan_
# operation` never reads it into any execution payload (every
# branch extracts fields by explicit name, never `**operation`).
```

## CH-0746

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3cd closure (K-1, design D-6, B-2): `narrow_
# limits_by_budget` is no longer called at the facade layer,
# before this gate -- `self._gate` above already validated
# `budget` (raising VALIDATION_FAILED there, AFTER rate/
# concurrency/request_bytes/operation_depth, if it is
# invalid) and used it to size its own `deadline`. This
# second call is the SAME pure function, on the SAME inputs,
# already proven not to raise by the gate's own successful
# entry -- it resolves `limits`, the ONE point the COUNT-
# valued checks below (`batch_items`/`batch_entities`) and
# `_plan_operation`'s own `_bind_filters` `in`-filter check
# (K-3) read instead of `self.config` directly. A caller that
# never presented a `budget` gets `self.config` back
# unchanged (identity-shaped narrowing).
```

## CH-0747

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# I-7: a dry run never records or consults an idempotency
# record, regardless of whether `idempotency_key` was
# presented -- the `not dry_run` guard above is this
# method's only such check.
```

## CH-0748

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# I-3/I-8: answered from the record, before target
# existence/confirmation/precondition/execution are
# ever reached -- the exact `results` object this
# method itself returned when the original request
# committed. J-4 (SI-14): a replayed mutation response
# earns its own durable row before it is ever
# returned -- otherwise a confirmed destructive
# delete's own resend would return `committed: true`
# while leaving zero evidence this Application was
# touched at time T (WP-2cd/WP-3cd audit N-5).
```

## CH-0749

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Pass 1: validate every operation, across every entity, before
# any execution begins (P35-D9/P35-D10 above). Nothing below this
# line has written through `self._backend` yet.
# Phase 4 (design D-3): `_plan_operation`'s own delete branch may
# raise `DestructiveConfirmationRequired` (via `_validate_delete_
# confirmation`, the same choke `delete()` uses) -- routed
# (coalesced) here, at the one call site with `principal` in
# scope, mirroring `delete()`'s own identical wrapping.
# Phase 9 WP-3b (design D-4 (7)): the LOCAL execution plan
# `_plan_operation` builds is renamed `execution_plan` here
# (it was `plan` before this WP) -- this method's own new
# `plan` PARAMETER (the caller-presented token) needs the
# name `add_field`/`alter_field`/`create_collection` above
# already use for the identical concept; keeping both names
# `plan` in one scope would shadow one with the other.
```

## CH-0750

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# `digest_request` (WP-3b closure, H-1/H-2; Phase 9 WP-3c
# rework, I-13): built ONCE, above (before pass 1), not
# here -- see this method's own idempotency-lookup block
# for the full construction rationale (entity/budget/
# transaction/idempotency_key handling unchanged from the
# pre-WP-3c version this replaces). Reused verbatim here:
# `compute_plan_token` excludes only `plan`/`dry_run`, so
# an `idempotency_key` this object carries (I-13) is part
# of what THIS token commits to too.
```

## CH-0751

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 4 (design D-2, review M-6): `hook_fired` distinguishes
# "the durable pre-commit write itself failed" (nothing was
# committed to correct -- the batch is simply refused) from
# "the durable write succeeded but this backend's own commit
# then failed" (D-2's error-row case) -- mirrors `backend_
# postgres.PostgresBackend`'s identical single-operation
# pattern, here at the batch level since `transact`'s own
# begin/commit/rollback envelope lives in `cell.py`, not
# either backend module.
```

## CH-0753

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1): the idempotency
# record is written as the LAST thing before this
# backend's own commit -- a failure anywhere above
# (including the execution loop itself) never
# reaches this line, so a failed attempt leaves no
# record (the `except Exception` below rolls the
# whole transaction back, this write included, on
# the PostgreSQL backend; the SQLite/in-memory
# backend never applies it either, since this
# statement itself never ran). `idempotency_
# response_digest`/`idempotency_key` are only both
# non-`None` when this method's own earlier lookup
# block found no matching record to replay.
```

## CH-0754

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3cd closure (K-5, N-8): undoes a `record_
# idempotency` write that turned out NOT to share the
# data's own fate -- e.g. `record_idempotency` itself
# succeeded but `self._backend.commit()` immediately
# after it then raised (reaching THIS handler with the
# `SQLiteBackend`/in-memory backend's own private,
# non-transactional dict already holding a record for
# data `self.rollback()` above just discarded). A no-op
# when there is nothing pending to discard (the far
# more common case: some EARLIER step failed, before
# `record_idempotency` was ever reached) -- mirrors the
# 3 schema-mutating DDL methods' own identical `except
# Exception:` cleanup one-for-one.
```

## CH-0756

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 4 (design D-10): the pre-existing 6-field-sink record
# is unconditional and unchanged -- it fires for a
# batch-embedded delete exactly as it did before this WP,
# now safely AFTER `self._backend.commit()` has actually
# succeeded (no `pending_audit` deferral needed any more: the
# hook above already gave the durable trail its own, separate,
# PRE-commit guarantee, so this post-commit legacy record
# never needs to claim a write a later operation rolled back
# -- if we are here at all, `self._backend.commit()` already
# succeeded for the whole batch).
# Phase 9 WP-3b (design D-4 (4), §5 U-2 = (A)): NEITHER
# audit path below runs for a dry run -- rolled back
# above, nothing to record. `results` itself is still the
# real per-item outcome each write produced before the
# rollback undid it (`affected` "is the count if it had
# executed", D-4 (3)) -- a trailing envelope dict is
# appended (only for a dry run) carrying `committed`/
# `plan`/`request_id`, the same convention `attempt_
# mutation_with_result`'s own port docstring documents
# (`results[-1]`, `conformance-tests/adapter.py`); `zip`
# against `items` (this method's own callers, `http.py`/
# the port) truncates to `len(items)`, so this extra
# entry never perturbs `affected`'s own per-item sum.
```

## CH-0758

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._check_missing_required_fields`)
- parent commit: `987b004`
- kind: docstring

```
Phase 9 WP-3a (design D-2 (3)): the insert-only 欠落検査 --
`declared_non_nullable - set(values)`. Placed BEFORE `_prepare_
values` at every real insert entry point (this method's own two
callers: `insert` above and `_plan_operation`'s "insert" branch
below) rather than inside the choke point itself (`field_types.
check_declared_value`), because a field this operation omits is
never handed to that choke point at all -- there is no value for
it to check. Silently returns (deferring to `_prepare_values`'s
own, pre-existing shape errors) when `collection`/`values` are
not even the right Python shape to look field constraints up
for -- this check's own job is the CONTENT of a well-shaped
`values` dict, not `values`' own shape.

Code review §2 D / 監督裁定 D (2026-09-07): `field` names a
POSITION IN THE REQUEST (design D-3 (2)), never a bare entity
field name -- `path_prefix` (this insert's own `values` object,
`"values"` for a direct `insert()`/`update()` call or
`"operations/<i>/values"` for one batch item, the caller's own
job to supply) is joined with the missing field's own name.

Code review §2 C / 監督裁定 C (2026-09-07, P-8/G-4 performance
finding): returns the `(declared_types, declared_constraints)`
pair `self._backend.field_types_and_constraints(collection)`
fetched along the way, on success -- `_prepare_values` (this
insert's own very next call) reuses that SAME pair instead of
re-fetching it from the backend, cutting a plain insert's own
backend round trips (previously: `field_types_and_constraints`'s
two now-merged predecessors were each fetched TWICE per insert,
once here and once in `_prepare_values`). Returns `None` when it
could not fetch one (wrong Python shape, or `collection` does not
exist) -- `_prepare_values` falls back to fetching its own,
unchanged from before this rework.
```

## CH-0759

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._prepare_values`)
- parent commit: `987b004`
- kind: comment

```
# Phase 6 WP-3 (design D-3, G3): the PRIMARY, backend-independent
# declared-type choke point -- `field_types.check_declared_value`
# runs BEFORE `encode_value` on every backend (sqlite included,
# where `field_domains` alone enforces nothing at all, `available`
# above being all-`None` there). Backend domain validation stays
# underneath this as defence-in-depth (`encode_value` itself),
# never a substitute for it.
#
# Phase 9 WP-3a (design D-2 (3), 追補 2 S-k) rework (code review
# §2 C, 監督裁定 C 2026-09-07): `declared_types`/`declared_
# constraints` -- the write-side `enum`/`nullable` registry
# passed to `check_declared_value` below for every field this
# loop checks -- are ONE merged backend read now
# (`field_types_and_constraints`, `field_types`+`field_
# constraints`'s own single-query replacement), reused verbatim
# when `prefetched` (an insert's own `_check_missing_required_
# fields` call, immediately before this one) already fetched it
# for the SAME collection. `_bind_filters` below still reads
# `field_types` alone, the identical way it always has, and
# NEVER calls `field_constraints`/passes `constraints` (D-2 (2):
# "query の predicate 値は enum を検査しない").
```

## CH-0761

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._prepare_values`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3a (design D-3 (2)): `field` names "a position
# in the request" -- `check_declared_value` itself has no
# request-path context (design D-2 (3)'s own fixed new
# signature adds only `constraints`, never a field/path
# argument), so the ONE caller that DOES know which field
# this value belongs to adds it here. A no-op for every
# PRE-EXISTING `ValidationError` this choke point already
# raised before this WP (no `details` attribute at all --
# `getattr(exc, "details", None)` below returns `None`,
# `dict is not None` is `False`) -- this WP's own two NEW
# denials (`enum`/`nullable`) are the only ones that carry
# `details` here to enrich. Code review §2 D / 監督裁定 D
# (2026-09-07): the value written is `path_prefix`'s own
# request position joined with `field`, never the bare
# entity field name (design D-3 (2)).
```

## CH-0762

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `987b004`
- kind: comment

```
# Phase 6 WP-3 (design D-3, G3): same choke point `_prepare_values`
# above uses.
```

## CH-0763

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `987b004`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): unreachable through the
# HTTP surface (`http.py`'s own `_parse_filter` always
# constructs a `Filter` before this method is ever
# called) -- a defensive internal-shape guard against a
# direct caller passing the wrong Python type, kept
# `request_schema` with the list index it can still
# attribute, same treatment as this method's own
# unreachable-in-practice siblings above.
```

## CH-0764

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `987b004`
- kind: comment

```
# WP-3e rework T2 (追補 M-3): an empty (or non-list)
# `in` value is a defect of the VALUE this predicate
# carries, not of the field name it names -- `field`
# is `where/<i>/value`, unconditionally refused on
# both backends (this is the ONE choke point either
# backend's own `transact`/`read` path reaches before
# a SQL `IN (...)` clause is ever built).
```

## CH-0765

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `987b004`
- kind: comment

```
# B-1: every element compares against the SAME column, so
# they all share that column's own domain.
```

## CH-0766

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `987b004`
- kind: comment

```
# 追補 4 O-2: `field`/`declared_type` mirror `_check_
# predicate_value`'s own path immediately above (`where/
# <i>/value`) -- the value being checked, not the field
# position, exactly M-4's "述語値系は要求内パス" rule.
```

## CH-0767

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._require_data`)
- parent commit: `987b004`
- kind: comment

```
# Review M-2 (major, supervisor ruling 2026-09-03, "完全案"):
# `guard` is always `auth.CredentialStore.assert_active` or
# `credential_store_postgres.PostgresCredentialStore.
# assert_active` in every real construction of this class
# (`main.py`/`service.py` -- the only two call sites that ever
# pass a non-`None` guard, verified by source inspection),
# both of which accept this same `request_id` keyword after
# this WP's changes -- so a session re-check failure's own
# durable denial row carries the SAME request_id as the
# operation that triggered the re-check.
```

## CH-0768

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._require_data`)
- parent commit: `987b004`
- kind: comment

```
# Review M-3 (major, supervisor ruling 2026-09-03): this is
# SI-00's own application-boundary check ("this credential's
# own `application_id` does not match the cell it is being
# used against") -- the single most evidence-worthy `FORBIDDEN`
# this peer can produce, and previously recorded on NO audit
# surface at all (neither the 6-field sink nor the durable
# one). `FORBIDDEN` is in D-3's own inclusion table
# unconditionally; routed (coalesced) here, the one choke
# point every public data-operation method (`insert`/`read`/
# `update`/`delete`/`transact`/`schema_revision`, and `_require_
# developer` itself) already passes through. (Scoped to the
# durable D-3 path only, per review M-3's own literal
# instruction -- the pre-existing 6-field sink's own
# `_SAFE_DETAILS` vocabulary has no accurate label for a
# generic access denial, so this does not invent one there.)
```

## CH-0769

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime._post_schema_revision`)
- parent commit: `987b004`
- kind: docstring

```
Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): the
UNGATED counterpart of `schema_revision` above, for exactly one
caller -- `http.py::post_schema`'s own post-op revision readback,
immediately after a `create_entity`/`add_field` call that has
ALREADY passed through `_limit_gate` earlier in this SAME wire
request. That readback is not itself a second client request (no
`GET .../schema-revision` endpoint exists; nothing on the wire
asks for it independently of the schema-mutation call it reports
the consequence of) -- routing it through the now-gated
`schema_revision()` above would silently double the effective
`requests_per_minute`/`concurrency` cost of every HTTP schema
operation relative to the in-process surface, whose own
`create_entity`/`add_field` never make this extra call at all
(the asymmetry the original WP-1a report measured; 裁定 3 resolves
it by gating the real client-facing query and exempting only
this one internal wire-formatting readback, rather than exempting
both, since `catalog`/`schema_revision` themselves ARE real,
independently client-callable queries r2db bounds too).
```

## CH-0770

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime.read`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3d (design D-6, B-4): `request_budget` is `enabled`
# as of this SAME commit (`__build_capabilities_document` below) (body now in `capabilities_document.py`)
# -- the present-denial gate is removed. Phase 9 WP-3cd closure
# (K-1): `budget` now reaches `ApplicationCell.read` RAW/
# unvalidated -- `narrow_limits_by_budget` moved from here into
# `ApplicationCell._limit_gate` itself (`endpoint_kind="query"`),
# so an invalid `budget` is refused AFTER rate/concurrency/
# request_bytes/operation_depth, matching r2db's own gate order
# (audit-wp3cd.md §3 N-3: this facade-layer call used to refuse
# an invalid `budget` BEFORE any of those four bounds, an
# observable peer asymmetry this closure fixes).
```

## CH-0771

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime.transact`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3b (design D-1 (4), P-3): `dry_run`/`plan` gate
# removed -- `dry_run` flips to `enabled` in this SAME commit
# (`__build_capabilities_document` below) (body now in `capabilities_document.py`). Phase 9 WP-3c/WP-3d:
# `idempotency_key`/`budget` are UNGATED as of this SAME commit
# too -- both `idempotency`/`request_budget` flip to `enabled`
# below (now in `capabilities_document.py`). Phase 9 WP-3cd closure (K-1): `budget` now reaches
# `ApplicationCell.transact` RAW/unvalidated -- `narrow_limits_by_
# budget` (`endpoint_kind="mutate"`, shared by the single-entity
# and cross-entity callers alike, both of which route through
# this one method) moved from here into `ApplicationCell.
# _limit_gate` itself, so an invalid `budget` is refused AFTER
# rate/concurrency/request_bytes/operation_depth, matching r2db's
# own gate order (see `ApplicationRuntime.read`'s identical
# comment immediately above). `transaction` (rework, M-4/G-1) is
# NOT gated -- unlike `budget` it names no capability of its own
# (this peer's own `http.py::post_mutate` already accepts and
# validates `MutationRequest.transaction` today, refusing
# anything but `"atomic"` before this method is ever reached); it
# is forwarded so `ApplicationCell.transact`'s own digest can
# commit to it (`MutationRequest`'s contract-required 4th non-
# `plan`/`dry_run` field, alongside `operations`/`idempotency_
# key`/`budget`). `entity`/`digest_operations` (WP-3b closure,
# H-1/H-2): passed straight through, unexamined -- see
# `ApplicationCell.transact`'s own identical-purpose comment for
# the full reasoning. Neither names a capability this peer gates;
# both are pure digest-construction inputs.
```

## CH-0772

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime.capabilities`)
- parent commit: `987b004`
- kind: docstring

```
Minimal capability/discovery document, per this session's own
server-bound scope. Statuses reflect what this foundation actually
executes today, not the common contract's peer-target surface: an
operation this foundation cannot run is never advertised "enabled"
(spec `capability_status.rules`).

This is the single source of truth for this peer's declared
capability document (R-3): both the SQLite-backed in-process
composition and the PostgreSQL-backed composition
(`tests/test_postgres.py`) share this exact method -- there is no
second copy anywhere that could drift out of agreement with it.

Phase 8 WP-1a rework 1 (裁定 3, 監督裁定 2026-09-06): WRAPPED by
`_limit_gate` (rate/concurrency only -- `request=None`) for the
SAME reason as `ApplicationCell.catalog`/`.schema_revision`
(those methods' own docstrings carry the full trace): r2db bounds
its own `capabilities()` this way too (`service.py:877` inside
`_slot`), and this is a real, client-callable, authenticated
query, not a discovery-time exemption -- the pre-rework version
left it entirely outside the gate (measured, pre-rework:
`rpm=50` with 500 consecutive `capabilities()` calls, zero
denials).
```

## CH-0773

- moved from: `src/mitatedb_api/cell.py` (`ApplicationDeveloper.create_entity`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3a (design D-1 (4), P-3): `field_constraints` no
# longer gates -- `constraint_declarations` is `enabled` as of
# that commit, same commit as the real enforcement below. Phase 9
# WP-3b: `dry_run`/`plan` no longer gate either -- `dry_run` is
# `enabled` as of THIS commit, same commit as `cell.py::
# ApplicationCell.create_entity`'s own real dry_run/plan
# behavior. Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` are
# UNGATED as of THIS commit too -- both `idempotency`/`request_
# budget` flip to `enabled` below. Phase 9 WP-3cd closure (K-1):
# `budget` now reaches `ApplicationCell.create_entity` RAW/
# unvalidated -- `narrow_limits_by_budget` (`endpoint_kind=
# "schema"`) moved from here into `ApplicationCell._limit_gate`
# itself, so an invalid `budget` is refused AFTER rate/
# concurrency/request_bytes/operation_depth (see `ApplicationRuntime.
# read`'s identical comment for the full reasoning).
# `digest_extra` (WP-3b closure, H-3 (b)): pure digest-
# construction pass-through, unexamined here.
```

## CH-0774

- moved from: `src/mitatedb_api/cell.py` (`ApplicationDeveloper.add_field`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3a: `enum`/`nullable` no longer gate -- see
# `create_entity`'s own identical comment immediately above.
# Phase 9 WP-3b: `dry_run`/`plan` no longer gate either -- same
# reasoning as `create_entity`'s own identical comment. Phase 9
# WP-3c/WP-3d: `idempotency_key`/`budget` ungated too, same
# reasoning. Phase 9 WP-3cd closure (K-1): `budget` now reaches
# `ApplicationCell.add_field` RAW/unvalidated -- see `create_
# entity`'s own identical comment immediately above.
# `digest_extra` (WP-3b closure, H-3 (b)): pure digest-construction
# pass-through, unexamined here.
```

## CH-0775

- moved from: `src/mitatedb_api/cell.py` (`ApplicationDeveloper.alter_field`)
- parent commit: `987b004`
- kind: comment

```
# Phase 9 WP-3cd closure (K-1): `budget` now reaches
# `ApplicationCell.alter_field` RAW/unvalidated -- see `create_
# entity`'s own identical comment above.
# `digest_extra` (WP-3b closure, H-3 (b)): pure digest-construction
# pass-through, unexamined here.
```
