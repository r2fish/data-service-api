# src/mitatedb_api/backend_postgres.py -- code-comment history (change set 6)

Companion for `src/mitatedb_api/backend_postgres.py` per `docs/code-history/README.md`.

## CH-0525

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend._field_types_and_constraints_locked`)
- parent commit: `80fad55`
- kind: docstring

```
Code review §2 C / 監督裁定 C (2026-09-07): `field_types`'s own
`declared_type` and `field_constraints`'s own `enum_json`/
`nullable` live on the SAME `_mdb_field_types` row -- this reads
all three columns in the ONE query `_field_types_locked`/
`_field_constraints_locked` used to make as TWO independent
round trips against that identical row.
```

## CH-0526

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.field_types_and_constraints`)
- parent commit: `80fad55`
- kind: docstring

```
Code review §2 C / 監督裁定 C (2026-09-07, P-8/G-4 performance
finding): see `backend.StorageBackend.field_types_and_
constraints`'s own contract -- `field_types` and `field_
constraints` merged into the single query `_field_types_and_
constraints_locked` above makes. `cell.py::_prepare_values` (and,
via the pair it returns, `_check_missing_required_fields`) is
the sole caller -- every other reader of `field_types`/`field_
constraints` keeps calling one of those two on their own,
unchanged. Existence-checked the same way both are.
```

## CH-0528

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.alter_field_constraints`)
- parent commit: `80fad55`
- kind: comment

```
# Code review §2 A / 監督裁定 A (2026-09-07): tri-state
# `enum` -- `UNCHANGED` (default) keeps the field's
# current `enum` (decoded from the row already read
# above); an explicit `None` CLEARS it; any other value
# (an already-validated, non-empty list) SETS/REPLACES
# it. This is the SAME three-way rule `backend_sqlite.
# SQLiteBackend.alter_field_constraints` applies.
```

## CH-0529

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.alter_field_constraints`)
- parent commit: `80fad55`
- kind: comment

```
# Code review §2 F / 監督裁定 F (2026-09-07): locks
# `collection` IN SHARE ROW EXCLUSIVE MODE before scanning
# its existing rows, inside this SAME transaction -- this
# blocks a concurrent INSERT/UPDATE/DELETE (ROW
# EXCLUSIVE) on this table for the rest of this
# transaction while still permitting concurrent SELECTs
# (ACCESS SHARE), so no other session's write can land a
# newly-violating row in the window between this scan
# and this same transaction's own COMMIT below. The
# single-transaction placement (実装の形 4, S-g) alone
# only closes "registry updated while a row still went
# unscanned"; under READ COMMITTED (this connection's own
# default) it does not, by itself, close this phantom-
# write window -- this lock does.
#
# R-35 (Phase 10, WP-6d-i review): the original fix used
# plain `SHARE MODE`, which does not conflict with itself
# -- two concurrent `alter_field`/`add_field` calls on the
# SAME entity could both acquire it here, then each block
# at its own later `ALTER TABLE` (ACCESS EXCLUSIVE)
# waiting on the other's SHARE lock, a guaranteed mutual
# wait broken only by PostgreSQL's deadlock detector
# aborting one side with an error rather than the two
# calls simply serializing. `SHARE ROW EXCLUSIVE`
# conflicts with itself, so the second caller instead
# waits here, at LOCK TABLE, and proceeds only once the
# first transaction commits or rolls back -- it still
# excludes concurrent row writers (ROW EXCLUSIVE) exactly
# as plain SHARE did, so the scan property above is
# unchanged.
```

## CH-0530

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.alter_field_constraints`)
- parent commit: `80fad55`
- kind: comment

```
# Code review §2 D / 監督裁定 D (2026-09-07): `field`
# names a POSITION IN THE REQUEST (design D-3 (2)),
# not the entity field name -- see `backend_sqlite.
# SQLiteBackend.alter_field_constraints`'s identical
# comment for why that position is `violation` itself.
```

## CH-0537

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.insert_in_transaction`)
- parent commit: `80fad55`
- kind: comment

```
# Phase 8 WP-1a rework 1 (裁定 2, 監督裁定 2026-09-06): the SAME
# `execution_ms` mapping `insert()` above already has -- not rolled
# back here either (same B-1 (ii) reasoning as every other
# `except` clause in this method: the OUTER `transact()`
# (`cell.py`) is the single rollback point for the whole batch).
# `begin()`'s own `SET LOCAL statement_timeout`/`lock_timeout`
# (module-level comment above `_timeout_ms`) is what makes this
# exception reachable from an operation running INSIDE a batch,
# not only a standalone single-operation call -- every HTTP
# mutation reaches the database through this exact `..._in_
# transaction` family (`cell.py::transact`, `http.py::post_mutate`
# always dispatches through it), so leaving this mapping out here
# left the whole HTTP mutation surface unable to ever observe a
# real `LIMIT_EXCEEDED`/`execution_ms` denial (review finding 2).
```

### correction: 2026-10-01

- reason: R-115 -- the single-statement `insert()` / `update()` backend methods are removed (no product path called them and they committed without the audit hook); this comment no longer refers to them

old:
```
the SAME `execution_ms` mapping `insert()` above already has -- not rolled back here either (same B-1 (ii) reasoning
```

new:
```
the `execution_ms` mapping -- not rolled back here (same B-1 (ii) reasoning
```

## CH-0553

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.field_domains`)
- parent commit: `4241b55`
- kind: comment

```
# WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
# 裁定 6, review F9): `_mdb_field_types` missing entirely means
# migration 0006 was never applied to this application DB -- an
# OPERATOR/DEPLOYMENT defect, never a client mistake. Before
# this fix every read/write on an un-migrated DB surfaced as
# `ValidationError` (contract `VALIDATION_FAILED`, a CLIENT
# fault code) -- fail-closed either way, but the wrong fault
# attribution. `StorageConfigurationError` is this peer's own
# existing "permanent misconfiguration, not a client mistake"
# class (`credential_store_postgres.py`'s identical `
# InsufficientPrivilege` precedent), mapping to `SERVICE_
# UNAVAILABLE` at the HTTP boundary instead.
```

## CH-0554

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.add_field`)
- parent commit: `4241b55`
- kind: comment

```
# M-6 (監督裁定, WP-3a rework 2, 2026-09-07): mirrors
# `alter_field_constraints`'s own existing-row rule
# (LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE, inside
# this SAME transaction, before the scan), for a NEW
# field instead of an existing one -- a NEW field
# declaring `nullable: false` on an entity that
# already holds rows would leave every one of them
# holding `null` in it (there being no earlier value
# for it to have held), so it is refused the same
# way. Checked BEFORE the DDL below, so a conflicting
# call changes NOTHING -- no column, no registry row,
# no revision bump; this cursor's own transaction
# rolls back whole (`except ... scope.main.
# rollback()` below, the same as every other failure
# path here).
#
# R-35 (Phase 10, WP-6d-i review): plain `SHARE MODE`
# does not conflict with itself, so two concurrent
# `add_field`/`alter_field` calls on the SAME entity
# could both acquire it, then each block at its own
# later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on
# the other's SHARE lock -- a guaranteed mutual wait,
# broken only by PostgreSQL's deadlock detector
# aborting one side with an error instead of the two
# calls simply serializing. `SHARE ROW EXCLUSIVE`
# conflicts with itself, so the second caller instead
# waits here, at LOCK TABLE, and proceeds only once
# the first transaction commits or rolls back -- it
# still excludes concurrent row writers (ROW
# EXCLUSIVE) exactly as plain SHARE did, so the scan
# property above is unchanged.
```
