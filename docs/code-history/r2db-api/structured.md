# src/r2db_api/structured.py -- code-comment history

Companion for `src/r2db_api/structured.py` per `docs/code-history/README.md`.

## CH-0552

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Contract 1.7.0 (D-2 (1)/(7), WP-2a): `enum_members` is
# checked BEFORE any mutation below (limits.enum_members's own
# text: "before anything is created or altered") -- `fail()`
# raised from inside this method is not caught by anything
# short of unwinding the whole call (only the LATER deadline-
# check/audit-hook points below restore `before_*`), so this
# must run first, not merely "before `schema_revision`
# advances".
```

### correction: 2026-10-03

- reason: R-42 -- the deadline check after a schema operation's operation was removed (the entry check is the only deadline check of `apply_schema` and runs before the `before_*` snapshots), so no deadline-check point restores `before_*` any more; the points that do are the plan-mismatch, dry-run and audit-hook ones

old:
```
(only the LATER deadline-check/audit-hook points below restore `before_*`)
```

new:
```
(only the plan, dry-run and audit-hook points below restore `before_*`; the deadline is checked once at entry, before anything is snapshotted, and never after the operation)
```

### correction: 2026-10-03

- reason: R-42 -- the in-memory schema operation's entry deadline check now sits before the idempotency lookup, reply and reservation (an idempotency record read is a storage operation, and the next operation is refused once the budget is spent), so the comment names that point

old:
```
the deadline is checked once at entry, before anything is snapshotted
```

new:
```
the deadline is checked once at entry, before the idempotency lookup and before anything is snapshotted
```

### correction: 2026-10-03

- reason: R-42 -- the in-memory schema operation also checks its deadline just before the operation, after the snapshot, so the comment names both points

old:
```
the deadline is checked once at entry, before the idempotency lookup and before anything is snapshotted
```

new:
```
the deadline is checked at entry, before the idempotency lookup, and again just before the operation, after the snapshot
```

## CH-0553

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Phase 6 WP-2 (design D-3(iv)): a name present in `bound.
# field_types` gets its declared type; every other name in
# `bound.fields` keeps the pre-WP-2 default (`None` == `json`,
# decision (ii)) via `dict.get`'s own implicit fallback.
```

## CH-0554

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Only fields the request itself gave a `field_constraints`
# spec ever touch the registry (D-2 (1): "省略 = 制約なし").
```

## CH-0555

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# R-1: address_reuse is scoped to one entity's lifetime; a drop
# ends that lifetime, so a later create_entity of the same name
# is a new entity and its addresses start at 1 again.
```

## CH-0556

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): the registry is scoped to
# the entity's own lifetime too, symmetric with `schema`/
# `indexes`/`_next_id` above -- a later `create_entity` of the
# same name is a new entity with no inherited constraints.
```

## CH-0557

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Contract 1.7.0 (D-2 (1)/(7), WP-2a): `add_field`'s own
# single-field declaration, mirroring `create_entity`'s enum_
# members check above -- checked BEFORE the mutation just
# below (`bound.constraints` is `None` when the request never
# carried `enum`/`nullable` at all).
```

## CH-0558

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Monitor ruling M-6 (rulings-wp2a-review.md, contract
# corrigendum): "An add_field declaring nullable: false on an
# entity that already holds rows is refused with CONFLICT on
# the same rule, because every existing row would hold null in
# the new field" -- the SAME rule `alter_field`'s own existing-
# row scan enforces (D-2 (6)), applied here since a brand new
# field with no default always starts every existing row at
# `null`. Checked BEFORE the field is created (fail-closed:
# nothing has been mutated yet at this point).
```

## CH-0559

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Contract 1.7.0 (D-2 (5)/(6), WP-2a): "redeclares the
# constraints of one existing field" -- both the entity and
# the field must already exist (`field_type` redeclaration is
# rejected earlier, at bind time, `bind_schema_operation`).
```

## CH-0560

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Monitor ruling A/B-2 (rulings-wp3a-review.md, rulings-wp2a-
# review.md): compose the request's PATCH against the field's
# EXISTING declared constraints -- only known here, never at
# bind time (addendum R-b/R-c, D-2 (3)). `enum` omitted/
# `nullable` omitted each LEAVE the existing value as it is;
# `enum: null` CLEARS it; an explicit list is fully validated
# against the field's real declared type now.
```

## CH-0561

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Contract 1.7.0 (D-2 (6)): every existing row is checked
# against the constraints this operation would establish,
# BEFORE anything commits -- one violating row refuses the
# WHOLE operation with CONFLICT, changing nothing (this
# method's own fail-closed/`before_*`-restore machinery, never
# reached here since nothing has been mutated yet at this
# point).
#
# Monitor ruling F (rulings-wp3a-review.md, applied to r2db by
# M-1/rulings-wp2a-review.md): `PostgresCell.apply_schema`'s
# own alter_field branch takes `LOCK TABLE ... IN SHARE ROW
# EXCLUSIVE MODE` (plain `SHARE MODE` does not conflict with
# itself and can deadlock two concurrent callers at their own
# later `ALTER TABLE`, R-35, Phase 10, WP-6d-i review) before
# this same scan, closing a race where another transaction
# commits a violating row between the scan and the registry
# write. This in-memory backend needs no such lock:
# `ApplicationCell` serves one process, one operation at a
# time (there is no concurrent transaction that could commit a
# row between this scan and `entity_registry[...]` below), so
# the scan-then-write sequence is already atomic by
# construction.
```

## CH-0562

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# WP-2 review M-1: unify with every other CONFLICT in this
# module at HTTP 409 (this one previously fell through to
# `fail`'s 400 default).
```

## CH-0563

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# R-5, corrigendum M-6: dropping a unique index removes a
# guardrail (uniqueness) and can silently re-enable upsert's
# CAPABILITY_UNSUPPORTED gate to flip -- SI-09 destructive
# confirmation applies exactly like drop_entity.
```

## CH-0564

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `e332c34`
- kind: comment

```
# Phase 4 (design D-2, item 2): every schema operation is
# fail-closed class, unconditionally (unlike `transact`, there is
# no non-destructive schema operation) -- the pre-commit hook is
# called as the last thing this method does before its own commit
# point (here: `schema_revision += 1` and returning). A raise here
# restores every piece of state this method may have mutated,
# using the same `before_*` snapshots the deadline-check branch
# above already relies on, and propagates -- fail-closed by
# construction, no separate rollback path needed.
```

### correction: 2026-10-03

- reason: R-42 -- the deadline-check branch after the operation was removed, so the `before_*` snapshots are used by the plan-mismatch and dry-run branches above the pre-commit hook, not by a deadline check

old:
```
using the same `before_*` snapshots the deadline-check branch above already relies on
```

new:
```
using the same `before_*` snapshots the dry-run and plan-mismatch branches above use
```

## CH-0990

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# WP-2 review minor (e): `revision` was previously an accepted-but-
# unused key (schema-level optimistic locking has no implementation
# here) -- silently accepting and ignoring it is exactly the kind
# of gap `field_type`'s own precedent below closes, so stop
# tolerating it instead of leaving it a silent no-op.
```

## CH-0991

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Phase 6 WP-2 (design D-3(iv)): `field_types` (the per-field map)
# is accepted only by `create_entity` -- symmetric with `field_
# type`'s (the scalar) `add_field`-only rule immediately above.
```

## CH-0992

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints` (the
# per-field map) is accepted only by `create_entity` -- symmetric
# with `field_types` immediately above.
```

## CH-0993

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): the scalar `enum`/`nullable`
# pair is accepted only by `add_field`/`alter_field` -- symmetric
# with `field_type`'s own `add_field`-only rule above.
```

## CH-0994

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# WP-2 review M-3: `index`/`unique` are meaningful only to
# `create_index` (`drop_index` additionally accepts `index` as the
# name to drop, but never `unique`) -- the same "don't silently
# tolerate a key this operation does not use" principle as
# `field_type` above, applied to this pair.
```

## CH-0995

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Review blocker B-1: symmetric with `bind_mutation`'s identical
# check above (now in `mutation_binding.py`) -- a non-boolean truthy `destructive` (a string, an
# int, an object) must never be silently coerced into `True` by a
# loose `bool(...)` cast downstream. This is a shape check (contract
# `SchemaOperationRequest.destructive: {"type": "boolean"}`), so it
# runs here, before the destructive-confirmation gate itself, per
# contract `evaluation_order` (shape validation precedes
# confirmation evaluation).
```

## CH-0996

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# (b) a value outside the 7-word vocabulary. `isinstance`
# checked FIRST (coordinator F2, 2026-09-04 review): `in`
# against `FIELD_TYPES` (a `set`) raises `TypeError` for an
# unhashable value (a list/dict) rather than returning
# `False`, and `_endpoint` (http.py) maps an uncaught
# `TypeError` to a bare 503 -- `_check_object_shape`'s own
# JSON-Schema check does not constrain `field_types`'
# VALUES (only that the object's own top-level shape
# matches), so a list/dict/int/bool/null value reaches this
# line from real HTTP input, not merely from a
# bind_schema_operation direct call.
```

## CH-0997

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints` is an
# OPTIONAL, never-required key -- a `create_entity` carrying no
# `field_constraints` at all stays valid unchanged (every field it
# creates gets no `enum`, `nullable: true`, D-2 (2)'s own default).
# Placed AFTER `field_types` above so each field's own declared
# type (`field_types.get(name)`, `None`/json if that field was
# never given one) is already resolved for `validate_enum_
# declaration` below.
```

## CH-0998

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Mirrors `field_types`'s identical "sent without fields"
# check above. Monitor ruling N-2 (rulings-r2-closure.md,
# WP-2a closure): `field` names the request-internal key
# this whole clause hangs off, mirrors the adjacent
# per-entry branches below which already load this key.
```

## CH-0999

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Monitor ruling N-2 (rulings-r2-closure.md): same key,
# same reason as the "requires fields" branch above.
```

## CH-1001

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): `add_field`'s own single-field
# `enum`/`nullable`, validated against THIS SAME request's own
# `field_type` (already resolved above -- `add_field` declares a
# brand new field, so there is no "existing declared type" to
# defer to, unlike `alter_field` below).
```

## CH-1002

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (5), WP-2a; monitor ruling A/B-2): `alter_
# field` redeclares one EXISTING field's `enum`/`nullable` as a
# PATCH, never a wholesale replace -- omitting `enum` LEAVES it as
# it is, `enum: null` CLEARS it, omitting `nullable` LEAVES it as
# it is. `field_type` is rejected above (before this branch is
# ever reached) in the D-3 four-key form.
#
# The field's own EXISTING declared type/constraints are not known
# here (no catalog access at bind time) -- only this request's own
# SHAPE is checked (a list, non-empty, no `None` member, no
# duplicate); the member-type-vs-declared-type check (`validate_
# enum_declaration`, called again with the real declared type),
# the `enum_members` bound, and the omitted/clear/value COMPOSITION
# against the field's existing constraints are all deferred to
# `apply_schema` (addendum R-b/R-c, D-2 (3)) -- see `ConstraintPatch`.
```

## CH-1003

- moved from: `src/r2db_api/structured.py` (`bind_schema_operation`)
- parent commit: `ff76b35`
- kind: comment

```
# Monitor ruling A: `enum: null` clears the field's enum.
```

## CH-1004

- moved from: `src/r2db_api/structured.py` (`<module>`)
- parent commit: `ff76b35`
- kind: comment

```
# --- contract 1.7.0 dry_run/plan (D-4, WP-2b) --------------------------------
#
# Peer symmetry (work order §2 WP-2b "同型性テストの対象"): MitateDB-api
# places its own same-named, same-signature pair in `field_types.py`
# (the module its own D-2 constraint helpers already live in) -- no code
# is shared between the two peers (依頼者裁定 2026-09-03 案(a)); only the
# two names/signatures/behaviour are pinned isomorphic.
```

## CH-1007

- moved from: `src/r2db_api/structured.py` (`ApplicationCell`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): entity -> field_name -> FieldConstraints
# -- the in-memory backend's own declaration registry ("プロセス内参照
# cell の構造", no upgrade script needed, unlike Postgres's side table).
# A field name is present here ONLY when SOMETHING was declared for it
# (`FieldConstraints.is_declared`) -- absence means the version-wide
# default (`nullable: true`, no `enum`), exactly like `schema`'s own
# "省略 = json" convention. Never read/written directly by anything
# outside this class; `catalog()`/`_apply`/`_apply_upsert`/`apply_
# schema` below are its only callers.
```

## CH-1009

- moved from: `src/r2db_api/structured.py` (`ApplicationCell`)
- parent commit: `ff76b35`
- kind: comment

```
# ---- idempotency (contract 1.7.0 D-5, WP-2c) --------------------------
```

## CH-1010

- moved from: `src/r2db_api/structured.py` (`ApplicationCell.query`)
- parent commit: `ff76b35`
- kind: comment

```
# WP-2 review minor (c): order_by clauses count toward query
# complexity like select/where terms already do (the raw, caller-
# supplied count -- not the implicit trailing `id asc` `
# _resolve_order_by` may have appended, which is bookkeeping this
# engine adds, not complexity the caller asked for).
```

## CH-1011

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._describe_entity`)
- parent commit: `ff76b35`
- kind: docstring

```
One entity's `EntityDescriptor` (contract shape) -- factored out
of `catalog()` below (WP-2b) so `apply_schema`'s own `dry_run`
response can build the identical descriptor for the ONE entity a
schema operation targets (D-4 (3): "schema なら変更後の
EntityDescriptor を descriptor に載せる"), without duplicating this
construction logic a second time.
```

## CH-1012

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._describe_entity`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): total over `fields` --
# `nullable` always present, `enum` only for a field the
# registry (`self.field_constraints`) actually carries a row
# for. Read from the registry itself, never re-derived from
# any physical/stored value (D-2 (4): "catalog は...宣言
# registry から報告する").
```

## CH-1013

- moved from: `src/r2db_api/structured.py` (`ApplicationCell.transact`)
- parent commit: `ff76b35`
- kind: docstring

```
Ruling U-7 (WP-6d): thin lock wrapper -- `self._idempotency_lock`
is held for this call's entire duration, so a concurrent thread
calling `transact`/`apply_schema` on this SAME cell cannot
interleave with this one's own idempotency lookup -> execute ->
store window (see `_idempotency_lock`'s own field comment above).
All actual behavior lives in `_transact_locked` below, unchanged.
```

## CH-1014

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: docstring

```
`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
`dry_run` walks every gate a real request would (no early-out
anywhere above or inside this method) and this method's own
SINGLE tx-exit point -- after the per-operation loop below, before
this method's own commit point -- decides plan validity, then
commit vs rollback; it never branches mid-loop (D-4 (2): a
mid-loop branch would make "reaches the same decision" false).
`plan_request`, when given, is the contract-level request object
`service.py` assembled (`entity`/`operations`/`transaction`/
`budget`, never `plan`/`dry_run` themselves -- H-1, `{scratchpad}/
rulings-r4.md` addendum 2: `entity` is this request's own target,
the URL path segment, at the object's own top level) --
`expected_plan` below is
computed from it together with THIS entity's Application's own
`schema_revision`, read once, before the loop runs (mutations
never advance it, so reading it before or after is the identical
value; D-4 (7): the plan commits to the revision "as it stood
when the request was decided", not a value the loop could still
change). A caller-supplied `plan` that no longer matches is a
precondition failure (D-4 (2): evaluated after confirmation --
every confirmation check inside `_apply` below already raised, if
it was going to, before this point is ever reached -- and before
this method's own commit).

Review round F-5 (`{scratchpad}/rulings-r4.md`): `service.py`
builds `plan_request` unconditionally for every mutation, so the
digest below is only computed when it is actually consumed --
`dry_run`'s own response, or a caller-presented `plan` to verify
-- never for the ordinary apply that carries neither. A plain
apply pays no `json.dumps`/`sha256` cost it never uses.
```

## CH-1015

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-5 (8), addendum 2 S-b, ruling I-3, WP-2c): the
# idempotency lookup sits HERE -- after every bound this method's
# own caller (`service.py`) and the batch-size bound just above
# have already checked, before the entity-existence check right
# below (this contract's own `target-existence` stage, the first
# of `destructive_confirmation.evaluation_order`'s four). A
# `dry_run` never consults or writes a record at all (ruling I-7 /
# D-4): the guard below is `idempotency_key is not None and not
# dry_run`, never merely `idempotency_key is not None`.
```

## CH-1016

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-7 (3), WP-2e): the ORIGINAL
# execution's own `request_id` -- read back from the
# record's own payload (guaranteed present, M-6: no
# fallback to this resend's own request_id).
```

## CH-1017

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Phase 4 (design D-2): whether this batch passed through the
# DESTRUCTIVE_CONFIRMATION_V1 choke -- what
# `MutationOutcome.destructive` reports. Tracked here (not re-derived
# from `operations` after the fact) because it is `_apply`'s
# own successful pass through `require_destructive_
# confirmation` that establishes it, not merely the presence
# of a `delete` key in the request.
```

## CH-1018

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# WP-2 review M-2: per-operation deadline check, not
# only before/after the whole batch -- a unique-index
# write check is O(rows) per operation, so an O(N^2)-ish
# batch (many operations against a large, uniquely-
# indexed entity) could otherwise run well past the
# execution budget before the next checkpoint.
```

## CH-1019

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Monitor ruling M-3/D (rulings-wp2a-review.md, rulings-
# wp3a-review.md D): `operation_index` is this operation's
# own position in the request's `operations` list --
# `_apply` below uses it to compose `details.field` as a
# request-internal path (`operations/<i>/values/<field>`,
# D-3 (2)) for any VALIDATION_FAILED it raises validating
# this operation's own `values`.
```

## CH-1020

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Phase 4 (design D-2/D-10): the pre-commit hook is called for
# every real batch, not only a destructive one, as the LAST
# thing this method does before its own commit point (here:
# returning normally -- this in-memory backend has no separate
# commit step that could itself fail once this call returns,
# unlike `PostgresCell`, so there is no `commit_failed()`
# counterpart call anywhere in this class). A raise here is
# caught by the `except Exception` below, exactly like any
# other mid-batch failure -- restoring `before` and propagating
# (fail-closed by construction, no special-casing needed).
```

## CH-1022

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._transact_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-7 (3), WP-2e): `request_id` rides
# in the same payload the replay branch above reads
# back from -- so a future replay returns THIS
# execution's own `request_id`, not a fresh one.
```

## CH-1023

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): the registry's own entry for
# this entity -- addendum 2 S-k's 6 write call sites (3 here, 3 in
# `postgres.py`) all pass THIS through to `_check_type`; the 2
# predicate call sites (`_validate_predicate_types`, below and in
# `query`) never do (D-2 (2): a query predicate is not bound by
# `enum`/`nullable`).
```

## CH-1024

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply`)
- parent commit: `ff76b35`
- kind: comment

```
# Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): every
# `details.field` this method raises for a VALUE-position defect
# in `bound.values` names the request-internal PATH to that value
# (`operations/<operation_index>/values/<field>`), never the bare
# entity field name -- mirrors the contract text's own example
# verbatim ("operations/0/values/label").
```

## CH-1025

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply`)
- parent commit: `ff76b35`
- kind: comment

```
# Phase 4 (design D-2): reaching this point means `require_
# destructive_confirmation` above did not raise -- this
# operation is confirmed-destructive, the fail-closed dispatch
# signal `transact` aggregates across the whole batch.
```

## CH-1026

- moved from: `src/r2db_api/structured.py` (`ApplicationCell.apply_schema`)
- parent commit: `ff76b35`
- kind: docstring

```
Ruling U-7 (WP-6d): thin lock wrapper -- see `transact`'s
identical wrapper above and `_idempotency_lock`'s own field
comment. All actual behavior lives in `_apply_schema_locked`
below, unchanged.
```

## CH-1027

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `ff76b35`
- kind: docstring

```
`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
identical single tx-exit-point discipline to `transact` above,
adapted to this method's own pre-existing `before_*`-snapshot
restore machinery (5 pieces of state, not one `deepcopy`d dict).
Always returns `SchemaOutcome` -- review round F-8 (`{scratchpad}/
rulings-r4.md`): a bare `int` for one request and a `SchemaOutcome`
for the structurally identical request differing only in whether
it happened to carry `plan` was two shapes for the same call, not
a backward-compatibility rule. `DataService.schema` (`service.py`)
is a pure passthrough of this return value and therefore now
always returns `SchemaOutcome` too -- its own pre-1.7.0-shaped
direct callers read `.revision` off it instead of comparing the
result itself to an `int`.
```

## CH-1029

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# WP-2 review M-2: indexes count toward `schema_objects` too, like
# entities/fields already did (SI-08: an index is a real resource,
# and every write against a uniquely-indexed entity pays a
# per-index scan cost proportional to the index count).
```

## CH-1033

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Contract 1.7.0 (D-7 (3), WP-2e): see `transact`'s
# identical comment -- `request_id` rides in the payload a
# future replay reads back.
```

## CH-1034

- moved from: `src/r2db_api/structured.py` (`ApplicationCell._apply_schema_locked`)
- parent commit: `ff76b35`
- kind: comment

```
# Review round F-8: always `SchemaOutcome`, plan or no plan --
# every pre-1.7.0 direct caller of this method (`test_constraints_
# declaration.py`'s many `cell.apply_schema(...)` call sites among
# them) now reads `.revision` off the result instead of comparing
# the result itself to an `int`.
```
