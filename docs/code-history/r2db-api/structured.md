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
