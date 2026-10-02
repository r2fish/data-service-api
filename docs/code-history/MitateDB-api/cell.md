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

## CH-0556

- moved from: `src/mitatedb_api/cell.py` (`<module>`)
- parent commit: `4241b55`
- kind: comment

```
# Phase 10 WP-8c (design D-8 (3), review F-2, r2db `service.py::_slot`'s
# own `concurrency_precharged` docstring): set for the duration of
# `_LimitStateHolder.acquire_concurrency_slot` below (the pre-authentication
# entry point `http.py` uses, BEFORE `_authenticate`) so that `concurrency_
# slot` (the post-authentication entry point `ApplicationCell._limit_gate`
# already called before this WP) does not reserve a SECOND slot for the
# SAME logical request. A `ContextVar`, not an explicit parameter threaded
# through every one of `ApplicationCell`'s ~10 gated methods and their
# `ApplicationRuntime`/`ApplicationDeveloper` thin wrappers (the shape
# `r2db`'s own flatter `DataService` uses, `concurrency_precharged`): this
# peer's application-plane facade is a THREE-LEVEL chain (`http.py` ->
# `ApplicationRuntime`/`ApplicationDeveloper` -> `ApplicationCell` ->
# `_gate`/`_limit_gate`) with no single choke narrow enough to carry an
# explicit parameter without touching every intermediate signature -- a
# `ContextVar` set once, at the single call site that already spans both
# `run_in_threadpool` calls one HTTP request makes (`http.py`'s own
# comment on `acquire_concurrency_slot`), reaches `concurrency_slot` no
# matter how many layers of pass-through sit in between, with zero
# intermediate signature changes and therefore zero risk of a missed call
# site. Correct across the thread hop: `starlette.concurrency.
# run_in_threadpool` (`anyio.to_thread.run_sync`) copies the CALLING
# coroutine's own `contextvars.Context` into whichever worker thread runs
# the offloaded call, so a value set on the event-loop thread before
# either `await run_in_threadpool(...)` call is visible inside both, even
# when they land on two different physical OS threads (verified
# empirically for this exact call shape). Every DIRECT/in-process caller
# of `ApplicationCell`/`ApplicationRuntime` (this repository's own tests,
# the in-process conformance adapter) never sets this at all, so `get()`
# returns the default `False` for them and `concurrency_slot` behaves
# exactly as it did before this WP -- unaffected, by construction.
```

## CH-0557

- moved from: `src/mitatedb_api/cell.py` (`_LimitStateHolder.acquire_concurrency_slot`)
- parent commit: `4241b55`
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

## CH-0558

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell`)
- parent commit: `4241b55`
- kind: docstring

```
A private application storage boundary.

The default backend (`backend_sqlite.SQLiteBackend`) is used only as a
deterministic local foundation backend. `backend_postgres.
PostgresBackend` is the production-shaped Cloud SQL adapter (WP-1);
both keep this class's own authority shape identical, never exposing a
raw database connection to Application code.
```

## CH-0559

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._limit_gate`)
- parent commit: `4241b55`
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

## CH-0562

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `4241b55`
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

## CH-0563

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `4241b55`
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

## CH-0564

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_collection`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3a rework 2 (監督裁定 m-1, 2026-09-07): "a
# declaration naming a field the request does not
# create" -- the 4th `constraint_declaration` case.
# No `declared_type` (the named field is never
# created by this request, so it has none).
```

## CH-0565

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.create_entity`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3a closure (監督裁定 2026-09-07, audit §3 G3): D-3 details
# -- this is a missing-key request-shape violation, not one
# about a value's own type, so `declared_type`/`observed_type`
# are omitted per D-3 (3).
```

## CH-0566

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): mirrors `create_collection`'s
# own identical per-field check above -- `add_field`'s
# single scalar `field_type` key is its own request
# position (matches r2db-api's own `add_field` site,
# `field="field_type"`).
```

## CH-0567

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `4241b55`
- kind: comment

```
# WP-1c ext -- see `create_collection`'s identical
# comment for the rationale (契約 1.7.0 idempotency.
# record).
```

## CH-0568

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.add_field`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3e rework T1 (追補 L-1): `request_schema`, `field`
# names the request key this bound is about -- `add_field`
# has no plural container to point at (unlike `create_
# collection`'s own `fields`), so this points at the one
# new field name the request itself carries.
```

## CH-0571

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `4241b55`
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

## CH-0572

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `4241b55`
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

## CH-0573

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `4241b55`
- kind: comment

```
# WP-1c ext -- see `create_collection`'s identical
# comment for the rationale (契約 1.7.0 idempotency.
# record).
```

## CH-0574

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.alter_field`)
- parent commit: `4241b55`
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

## CH-0576

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.schema_revision`)
- parent commit: `4241b55`
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

## CH-0577

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.insert`)
- parent commit: `4241b55`
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

## CH-0578

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.read_page`)
- parent commit: `4241b55`
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

## CH-0579

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_update`)
- parent commit: `4241b55`
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

## CH-0580

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_update`)
- parent commit: `4241b55`
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

## CH-0581

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._validate_delete_confirmation`)
- parent commit: `4241b55`
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

## CH-0582

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.delete`)
- parent commit: `4241b55`
- kind: docstring

```
Contract `destructive_confirmation`: `delete` is this peer's
only destructive operation (see the module-level comment above (now in `request_vocabulary.py`)
`_DELETE_CONSEQUENCE` for why `drop_entity`/`drop_index`/the
control-plane revoke gate are all structurally absent here, not
merely unimplemented). See `_validate_delete_confirmation` above
for the actual confirmation semantics -- shared verbatim with
`transact()`'s own batch-embedded delete (P3-D2, WP-1.5).
```

## CH-0583

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._plan_operation`)
- parent commit: `4241b55`
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

## CH-0584

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._plan_operation`)
- parent commit: `4241b55`
- kind: comment

```
# Only "upsert" ever reaches here -- P3-D2 (WP-1.5) converged
# `update`/`delete` to real execution above. Per
# `capability_status.rules` ("optional target operations ...
# must fail with CAPABILITY_UNSUPPORTED"), this is a
# capability gap, not a malformed request.
```

## CH-0585

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `4241b55`
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

## CH-0586

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `4241b55`
- kind: comment

```
# Independent review B-2 (WP-2 follow-up -- the
# atomicity hole, largest safety fix of that review):
# rollback is now UNCONDITIONAL. The pre-fix `except`
# tuple listed only `errors.FoundationError` subclasses;
# a non-`FoundationError` exception reaching this point
# used to skip `self._backend.rollback()` entirely and
# escape this method uncaught -- measured concretely: a
# lone UTF-16 surrogate code point in a value's own text
# (e.g. `"\ud800"`) escapes both backend drivers' own
# parameter-binding step as a raw `UnicodeEncodeError`
# (neither a `sqlite3.Error` nor a `psycopg.Error`
# subclass), on BOTH backends. With the pre-fix narrow
# `except`, that left every EARLIER, individually-valid
# operation's own write sitting UNCOMMITTED but already
# VISIBLE on this same connection (both SQLite and
# PostgreSQL give a transaction read-your-own-writes
# visibility before `COMMIT`) -- a real partial-effect
# breach of the "whole batch commits or rolls back as one
# unit" invariant this method's own docstring promises.
# B-2(ii) below (`encode_value`, both backends) now closes
# THIS specific case deterministically at validation time
# (pass 1, before `self._backend.begin()` is ever called),
# but the unconditional rollback here is the actual safety
# backstop -- it must hold for ANY exception a backend
# could ever raise during pass 2, known or not, not only
# the one concrete case that happened to be found.
#
# P3-D2 (WP-1.5) / m-2 (WP-2 review correction):
# `DestructiveConfirmationRequired` is not actually
# reachable from pass 2 at all -- `_plan_operation` (pass
# 1) is the ONLY site that ever evaluates a destructive
# confirmation (`_validate_delete_confirmation`), so a
# schema change racing pass 1/pass 2 (§2 PG note) surfaces
# here as a `NotFoundError`/`ConflictError` from the
# backend's own DML instead (the table/column the plan
# was bound against no longer matches reality), never as
# a re-evaluated confirmation mismatch; it stays listed
# here only for defensive symmetry with `_plan_operation`'s
# own vocabulary, not because this `except Exception:`
# needs it to reach that branch specifically (every
# `Exception` already does). `ConflictError`/`NotFoundError`
# (a unique-constraint conflict / a collection that
# stopped existing between this call's own validation pass
# and its execution pass) and `ValidationError`/
# `ResourceLimitError`/`CapabilityError` (this file names
# no backend-native exception type at all -- every backend
# translates its own low-level, EXPECTED failures into
# this shared `errors.FoundationError` vocabulary before
# this point) remain the classified, expected outcomes;
# anything else (like the `UnicodeEncodeError` above, pre
# B-2(ii)) rolls back and re-raises unclassified, exactly
# as before -- this method itself never reclassifies an
# exception type, only guarantees rollback runs first.
```

## CH-0587

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell.transact`)
- parent commit: `4241b55`
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

## CH-0589

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._select_fields`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3e rework T2 (追補 L-3), corrected 追補 4 O-3 (版フリップ
# 監査 §4/§16, `{scratchpad}/rulings-r3-r7-flip.md`): the
# container position (`"select"`, the whole list's own
# request position), not a per-item indexed slot -- r2db-api's
# own form for this exact site (N-1's "両 peer 同形" -- an
# indexed slot was this peer's own pre-audit choice, now
# aligned). The value at this position may not even be a
# string, so there is no safe raw value to echo the way an
# already-syntax-valid identifier can be below.
```

## CH-0590

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._check_missing_required_fields`)
- parent commit: `4241b55`
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

## CH-0591

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._prepare_values`)
- parent commit: `4241b55`
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

## CH-0593

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._prepare_values`)
- parent commit: `4241b55`
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

## CH-0594

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._bind_filters`)
- parent commit: `4241b55`
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

## CH-0595

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._require_data`)
- parent commit: `4241b55`
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

## CH-0596

- moved from: `src/mitatedb_api/cell.py` (`ApplicationCell._require_data`)
- parent commit: `4241b55`
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

## CH-0597

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime._post_schema_revision`)
- parent commit: `4241b55`
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

## CH-0599

- moved from: `src/mitatedb_api/cell.py` (`ApplicationRuntime.capabilities`)
- parent commit: `4241b55`
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

## CH-0601

- moved from: `src/mitatedb_api/cell.py` (`ApplicationDeveloper.add_field`)
- parent commit: `4241b55`
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

## CH-0602

- moved from: `src/mitatedb_api/cell.py` (`ApplicationDeveloper.alter_field`)
- parent commit: `4241b55`
- kind: comment

```
# Phase 9 WP-3cd closure (K-1): `budget` now reaches
# `ApplicationCell.alter_field` RAW/unvalidated -- see `create_
# entity`'s own identical comment above.
# `digest_extra` (WP-3b closure, H-3 (b)): pure digest-construction
# pass-through, unexamined here.
```
