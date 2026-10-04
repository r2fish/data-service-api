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
