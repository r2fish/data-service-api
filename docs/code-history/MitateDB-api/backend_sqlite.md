# src/mitatedb_api/backend_sqlite.py -- code-comment history (change set 4)

Companion for `src/mitatedb_api/backend_sqlite.py` per `docs/code-history/README.md`.

## CH-0336

- moved from: `src/mitatedb_api/backend_sqlite.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: docstring

```
SQLite storage backend (R-3 seam execution side).

This is the extracted, backend-specific half of what used to be
``cell.ApplicationCell`` before the WP-1 seam refactor: nothing here
validates a request's SHAPE or a principal's AUTHORITY any more (that
stayed in ``cell.py``, unchanged) -- this module only ever turns an
already-validated request into SQLite statements against one private,
in-memory (``:memory:``) connection.

Kept as "a deterministic local foundation backend" only (`architecture/
DATA_SERVICE_FOUNDATION.md`) -- never the production persistence topology
(that is ``backend_postgres.PostgresBackend``).
```

## CH-0337

- moved from: `src/mitatedb_api/backend_sqlite.py` (`_check_deadline`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 8 WP-1a (design D-1 "実装の形" 5: "変更はapp側deadline検査の
呼び出しのみ"): this backend has no native query-timeout API
(`sqlite3` offers none) -- unlike `backend_postgres.py`'s own real
`SET LOCAL statement_timeout`/`lock_timeout`, this is the app-side
wall-clock check `cell.ApplicationCell._limit_gate`'s own computed
`deadline` (`time.monotonic()` seconds) is handed to. `deadline=None`
(a direct caller of this backend that supplies no deadline -- this
repository's own tests) skips the check entirely, mirroring `backend_
postgres.py`'s identical `None`-means-unbounded convention.
```

## CH-0338

- moved from: `src/mitatedb_api/backend_sqlite.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# R-3 (design v1.1, WP-0 m-7): this set is backend-specific, unlike the
# shared syntax allowlist in identifiers.py. `sqlite_sequence` is a real
# SQLite-internal table name (created automatically by an AUTOINCREMENT
# column); `audit_events` is reserved defensively against a future local
# audit-table name collision on this backend specifically.
```

## CH-0339

- moved from: `src/mitatedb_api/backend_sqlite.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-7 (independent review round 2): SQLite's own native storage class is a
# signed 64-bit integer (https://sqlite.org/datatype3.html) -- a bound
# Python `int` outside that range makes the underlying `sqlite3` C
# extension module raise a bare `OverflowError` (NOT a `sqlite3.Error`
# subclass) at parameter-binding time, which used to escape this
# backend's own `errors.FoundationError` boundary entirely AND, when hit
# inside `transact()` (`cell.py`), skip `cell.py`'s own `except (...):
# self._backend.rollback()` clause (that tuple does not list
# `OverflowError`) -- leaving the connection's already-`BEGIN`-started
# transaction open forever, so every subsequent `transact()` call failed
# with `sqlite3.OperationalError: cannot start a transaction within a
# transaction` (confirmed empirically). Checked deterministically here,
# BEFORE any statement reaches `cursor.execute`.
```

## CH-0340

- moved from: `src/mitatedb_api/backend_sqlite.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-4 (independent review): a closed lookup table, mirroring
# `backend_postgres.py`'s own `_DIRECTION_SQL` constant dict (WP-2.5) --
# this backend had none of its own, and instead concatenated `direction.
# upper()` directly into the SQL TEXT string in `read()` below. `cell.py`'s
# own `_bind_order_by` allowlist (`direction not in ("asc", "desc")`) is
# ALREADY the only thing standing between an arbitrary string and this
# backend's SQL text -- exactly the single-point-of-failure shape R-2/SI-04/
# SI-05 exist to close structurally, not merely by convention at the caller.
# A closed dict lookup here means an unexpected direction value raises
# (`KeyError`, translated to `errors.ValidationError` at the call site
# below) instead of ever reaching string concatenation, regardless of
# whether `cell.py`'s own allowlist is ever weakened or bypassed.
```

### correction: 2026-09-16

- reason: R-37 WP-4a -- backend_postgres.py's `_where_sql`/`_OPERATOR_SQL`/`_DIRECTION_SQL` moved to `postgres_sql.py`; the pointer gets a 40c position bracket

old:
```
`backend_postgres.py`'s own `_DIRECTION_SQL` constant dict (WP-2.5)
```

new:
```
`backend_postgres.py`'s own `_DIRECTION_SQL` (now in `postgres_sql.py`) constant dict (WP-2.5)
```

## CH-0341

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.__init__`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 6 WP-3 (design D-3, §1.5 finding 2a): sqlite has no
# provisioning concept, so this registry is lazily-created,
# in-memory state -- `{collection: {field: contract_type}}`, the
# SAME 7-word contract vocabulary the PostgreSQL registry table
# stores (see `field_types` below). Never derived from `PRAGMA
# table_info` -- that reports THIS backend's own physical type
# (`_TYPES`, `text`/`integer`/`real`/`json` -- SQLite's dynamic
# column affinity does not even enforce it), which cannot recover
# `object` vs `array` vs `json`, nor a declared `boolean` (also
# physically `INTEGER`, same as a declared `integer` "0/1"
# value).
```

## CH-0342

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.__init__`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3a (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (4)):
# "SQLite backend は `_declared_types` と同じプロセス内構造に制約
# を持つ" -- `{collection: {field: {"nullable": bool, "enum":
# [...]}}}`, the SAME lazily-created, in-memory-only shape as
# `_declared_types` immediately above (no upgrade script: this
# backend is the `:memory:` process-local one, F-6). `"enum"` is
# present only on a field that declares one; `"nullable"` is
# always present (default `True`, the contract default, D-2 (2)).
```

## CH-0343

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.__init__`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3c (design D-5, 追補 R-a: "SQLite backend はプロセス
# 内である"; 監督裁定集約 rulings-r5-r6.md I-1): idempotency
# records for this backend are a private, in-process dict -- this
# backend already IS the process-local, non-durable foundation
# (no upgrade script, matching `_declared_types`/`_declared_
# constraints` above), never a SQL table. `{key: {"digest": str,
# "response_json": str, "created_at_ms": int}}`.
```

## CH-0344

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.check_reserved`)
- parent commit: `4d45fc6`
- kind: comment

```
# WP-3e rework T1 (追補2 M-1): mirrors `backend_postgres.
# PostgresBackend.check_reserved`'s own identical rationale -- the
# reserved-name half of the identifier choke point, not defence-
# in-depth, so it carries `identifier_syntax` too.
```

## CH-0345

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.field_domains`)
- parent commit: `4d45fc6`
- kind: comment

```
# B-1 (independent review round 2): SQLite's own column affinity
# is dynamic (no equivalent to PostgreSQL's own type-mismatch
# failure mode this backend's domain concept exists to catch), so
# every field maps to domain `None` -- `ApplicationCell.
# encode_value` calls skip domain validation entirely for `None`,
# matching this backend's own pre-existing, unchanged external
# behavior (WP-1 P3 round 2 instruction #1: "SQLite側の外部挙動は
# 不変に保つこと").
```

## CH-0346

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend._begin_pseudo_tx`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 4 (design D-2/D-10, "擬似 tx"): SQLite's own `sqlite3`
driver, in this connection's default (legacy) isolation mode,
auto-commits a DDL statement (`CREATE TABLE`/`ALTER TABLE`)
IMMEDIATELY -- a subsequent `self._db.rollback()` does NOT undo it
(measured empirically: `db.execute("CREATE TABLE t (id INTEGER)");
db.rollback()` still leaves `t` in `sqlite_master`). An EXPLICIT
`BEGIN` issued first, however, makes the driver honour a following
`rollback()`/`commit()` for DDL exactly like it already does for
DML -- the identical mechanism `begin()` below already uses for
the batch (`transact()`) path, applied here to the three
single-operation DDL/DML methods that need real pre-commit-hook
rollback semantics (D-2's fail-closed guarantee: a raised
`errors.AuditSinkUnavailable` from `audit_hook.pre_commit()` must
leave NO trace of the DDL/DML that already ran). Defensive
rollback-if-already-open first, mirroring `begin()`'s own
identical guard.
```

## CH-0347

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.create_collection`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 6 WP-3 (design D-3): robust to a direct caller (bypassing
# `cell.py`) supplying no `field_types` at all, or only a partial
# one -- the SAME backfill-rule fallback `cell.ApplicationCell.
# create_collection` itself applies for every uncovered name.
# Phase 9 WP-3b: computed regardless of `dry_run` -- a dry run
# needs this SAME resolved shape for its own `descriptor`,
# without ever writing it to `self._declared_types`.
```

## CH-0348

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.create_collection`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3b (design D-4 (4)): commit vs. rollback is decided
# HERE, at the tx's own exit -- the DDL above already ran for
# real either way (the SAME `ConflictError` a real call would
# raise is what a dry run must raise too). No audit hook, no
# registry write, no revision bump for a dry run.
```

## CH-0349

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.create_collection`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1/I-8): the idempotency
# record is written as the LAST thing before this
# backend's own commit, exactly like `audit_hook.pre_
# commit()` immediately above -- a raise anywhere before
# this point (including from `pre_commit()` itself) leaves
# no record, mirrored by the `except Exception: self._db.
# rollback(); raise` below. The stored response is built
# HERE, from the SAME locals (`self._schema_revision + 1`,
# `resolved`/`resolved_constraints`) the return statement
# at the end of this method also uses, so a later replay
# returns byte-identical content to what a real,
# uncached call would have (I-8) -- never a second,
# independently-drifting construction.
```

## CH-0350

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.create_collection`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 6 WP-3 (design D-3): registry write lands only on this
# success path -- an exception above already `raise`d, so a
# rolled-back DDL never leaves a stray registry entry behind.
```

## CH-0351

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.add_field`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-6 (監督裁定, WP-3a rework 2, 2026-09-07): mirrors `alter_
# field_constraints`'s own existing-row rule, for a NEW field
# instead of an existing one -- an `add_field` declaring
# `nullable: false` on an entity that already holds rows is
# refused with `CONFLICT`, because every one of those rows
# would hold `null` in the new field (there being no earlier
# value for it to have held). Checked BEFORE the DDL below
# (this backend has no separate tx step for it to share --
# see `alter_field_constraints`'s own identical comment for
# why no lock is needed on this single-threaded, in-process
# backend), so a conflicting call changes NOTHING.
```

## CH-0352

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.add_field`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3b (design D-4 (4)): commit vs. rollback decided
# HERE, at the tx's own exit -- the DDL above already ran for
# real either way, so a dry run reaches the SAME `ConflictError`/
# `NotFoundError` a real call would. No audit hook, no registry
# write, no revision bump for a dry run.
```

## CH-0353

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.add_field`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 4: same pre-commit-hook structure as `create_
# collection` above -- see that method's own comment.
```

## CH-0354

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.add_field`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1/I-8): see `create_
# collection`'s own identical comment above -- the
# predicted descriptor here uses the SAME `**existing,
# field: ...` formula this method's own final `descriptor`
# (below) uses, reading `self._declared_types`/`self.
# _declared_constraints` BEFORE this call's own registry
# write (which lands after this `try` block, on success).
```

## CH-0355

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.add_field`)
- parent commit: `4d45fc6`
- kind: comment

```
# WP-3a rework 3 (real, measured bug -- SchemaOperationResult.
# revision is `required` unconditionally, `contract/data-service-
# api.v1.json`'s own `schemas.SchemaOperationResult.required`;
# `alter_field_constraints` below already returns the bumped
# revision, but this method used to return nothing at all, so the
# in-process caller's own successful `add_field` result could
# never report one -- see `cell.ApplicationCell.add_field`'s own
# comment at its call site for the full chain this closes). Phase
# 9 WP-3b: `descriptor` added -- the entity's OTHER, pre-existing
# fields read verbatim off the registry (unaffected by this
# call), `field` itself from this call's own arguments (a dry run
# never wrote it, but this is what it WOULD read afterwards).
```

## CH-0356

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.field_types`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 6 WP-3 (design D-3): see `backend.StorageBackend.
field_types`'s own contract. `field_domains` is called only for
its existence check -- its own return value (all-`None` domains,
this backend's own unchanged behaviour) is discarded here.
```

## CH-0357

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.all_field_types`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 6 WP-3 (design D-3): `{collection: {field: contract_
type}}` for EVERY collection this backend currently has -- `GET
/v1/catalog`'s own sole data source (`http.py::get_catalog`).
Never includes a collection with no registry entries (cannot
occur for one this backend's own `create_collection` created --
every field always gets a registry row, `create_collection`'s own
docstring).
```

## CH-0358

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.field_types_and_constraints`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 9 WP-3a rework (code review §2 C, P-8/G-4): see
`backend.StorageBackend.field_types_and_constraints`'s own
contract. This backend has no round trip to cut -- `_declared_
types`/`_declared_constraints` are already two plain in-process
dicts -- so this exists purely to give `cell.py` the SAME method
name on both backends; `field_domains` is still called only once
here (not twice, as calling `field_types`+`field_constraints`
separately would).
```

## CH-0359

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 9 WP-3a (design D-2 (5)/(6), 実装の形 4, 監督裁定 S-g):
see `backend.StorageBackend.alter_field_constraints`'s own
contract. This backend has no separate DDL step for a constraint
change (only the registry moves) -- the existing-row scan, the
registry write, and the schema-revision bump all happen here, in
this one method, inside the SAME pseudo-tx `create_collection`/
`add_field` above use for DDL (`_begin_pseudo_tx`) so a raised
`ConflictError` (or a mid-method `AuditSinkUnavailable` from
`audit_hook.pre_commit()`) leaves NOTHING changed -- not even a
half-applied registry write -- exactly like this backend's own
DDL methods already guarantee for schema changes.

Code review §2 F / 監督裁定 F (2026-09-07): unlike `backend_
postgres.PostgresBackend`'s own implementation, this backend
takes no `LOCK TABLE` before its own row scan below -- this
whole method is one uninterruptible Python call on one private,
single-threaded, in-process (`:memory:`) connection (`__init__`'s
own module-level "PG 留意" note has no counterpart here: there is
no OTHER session that could ever commit a row between this
method's own scan and its own commit). The concurrency hole a
PostgreSQL `LOCK TABLE` closes simply does not exist on this
backend.
```

## CH-0360

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: comment

```
# Code review §2 A / 監督裁定 A (2026-09-07): tri-state `enum` --
# `UNCHANGED` (default) keeps whatever this field's current
# registry entry already carries; an explicit `None` clears it
# (no "enum" key at all in `new_constraints`); any other value
# (already a validated, non-empty list, `cell.py::alter_field`'s
# own job) sets/replaces it.
```

## CH-0361

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: comment

```
# Code review §2 D / 監督裁定 D (2026-09-07): `field` names a
# POSITION IN THE REQUEST (design D-3 (2)), not the entity
# field name -- `alter_field`'s own request carries `enum`/
# `nullable` as its OWN top-level keys (`{"collection": ...,
# "field": <entity field name>, "enum": [...], "nullable":
# ...}`), so the position a violated `enum`/`nullable`
# declaration is attributable to IS that same top-level key
# name -- the same value as `violated_declaration` itself.
```

## CH-0362

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3b (design D-4 (4)): the existing-row scan above
# (and its possible `ConflictError`) already ran for real, dry
# run or not -- SAME refusal either way. What differs from here
# is whether the registry/revision mutation below actually
# happens: for a dry run it is skipped entirely (never applied,
# so there is nothing to undo), and the pseudo-tx is rolled back
# instead of committed. `descriptor`'s OTHER, pre-existing fields
# are read off the registry BEFORE any mutation, so they are
# correct for both branches.
```

## CH-0363

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3c rework (design D-5, I-1/I-8): built here, BEFORE
# the commit/rollback branch below, so both this method's own
# idempotency write (inside the `try`, using the ALREADY-bumped
# `self._schema_revision`) and its final `return` (further below)
# read the identical dict -- never a second, independently
# constructed copy.
```

## CH-0364

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.alter_field_constraints`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1/I-8): unlike `create_
# collection`/`add_field` above, `self._schema_revision`
# is ALREADY the post-bump value at this point (bumped two
# lines above, before this `try`) -- no "+1" needed.
```

## CH-0365

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.encode_value`)
- parent commit: `4d45fc6`
- kind: comment

```
# `domain` is accepted only to match the shared `StorageBackend`
# call shape (`cell.py` always passes it) and is otherwise IGNORED
# -- see `field_domains`'s own comment above for why (this
# backend's own value acceptance is unchanged by B-1's own domain
# concept: SQLite's dynamic column affinity has no equivalent
# mismatch to detect).
#
# `field`/`declared_type` (追補 4 O-2): same threading as
# `backend_postgres.PostgresBackend.encode_value` -- `cell.py`'s
# own 3 call sites always pass both (the caller's own request-
# internal path and the contract-vocabulary declared type), so
# the two value-domain denials below (both genuinely storage-
# only, no in-memory equivalent) carry the same D-3 (4) 4-key
# form a normal client request reaches them with, rather than an
# empty `details`.
#
# SQLite's own driver: an explicit `int(bool)` conversion (rather
# than relying on `bool` being an `int` subclass the driver might
# adapt implicitly) -- unchanged from this backend's pre-seam
# behavior.
```

## CH-0366

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.encode_value`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-7 (independent review round 2): deterministic, pre-execution
# rejection of an out-of-64-bit-range integer -- see this
# module's own `_SQLITE_INT64_MIN`/`_SQLITE_INT64_MAX` comment
# above for why this is a real, previously-unhandled escape (a
# raw `OverflowError`, not a `sqlite3.Error`). This is a genuine
# CHANGE to this backend's own external behavior (an escaping
# `OverflowError` becomes a classified `errors.ValidationError`)
# -- a defect fix, not a preserved quirk: WP-1 P3 round 2
# instruction #1's own "SQLite側の外部挙動は不変に保つこと" applies
# to the NUL-byte/domain-mismatch question B-1 was actually about
# (values SQLite's own storage engine genuinely CAN represent),
# not to a value that ALREADY crashed out of this backend's own
# error hierarchy entirely.
```

## CH-0367

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.encode_value`)
- parent commit: `4d45fc6`
- kind: comment

```
# Independent review B-2(ii) (WP-2 follow-up, same precedent as
# the out-of-range-integer check immediately above -- both are a
# value that would otherwise crash out of this backend's own
# error hierarchy entirely, not a preserved-quirk question):
# `sqlite3`'s own driver raises a raw `UnicodeEncodeError` (never
# a `sqlite3.Error`) when binding a Python `str` that contains a
# LONE UTF-16 surrogate code point (U+D800-U+DFFF, not part of a
# valid pair -- e.g. a literal `"\ud800"`) -- measured directly
# (WP-2 review). Unlike the embedded-NUL case (this backend's own
# storage genuinely round-trips a NUL byte, see `cell.py`'s own
# `test_sqlite_backend_still_round_trips_an_embedded_nul_byte`),
# this is not a case where SQLite is simply more permissive than
# PostgreSQL -- the encoding failure happens in the SAME place
# (UTF-8 encoding at bind time) on both backends' own drivers, so
# this backend needs the identical deterministic, validation-time
# rejection `backend_postgres.py::_validate_value_domain` (in `postgres_value_domain.py`) now
# applies. Only a plain `str` can carry one through to this point
# (a dict/list value already became NUL/surrogate-escaped JSON
# text via `json.dumps` in `cell.ApplicationCell._normalize_
# value`, before this method is ever called).
```

## CH-0368

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.insert_in_transaction`)
- parent commit: `4d45fc6`
- kind: comment

```
# No commit/rollback here (unlike `insert` above): this runs
# inside a transaction the seam's own `transact()` already opened
# via `begin()` and will `commit()`/`rollback()` once, after every
# operation in the batch. Low-level driver errors are still
# translated to this shared `errors.FoundationError` vocabulary
# here (mirroring `insert()`'s own translation) so `cell.py`'s
# `transact()` never needs to name a backend-native exception type
# (R-3).
```

### correction: 2026-10-01

- reason: R-115 -- the single-statement `insert()` / `update()` backend methods are removed (no product path called them and they committed without the audit hook); this comment no longer refers to them

old:
```
No commit/rollback here (unlike `insert` above): this runs inside a transaction
```

new:
```
No commit/rollback here: this runs inside a transaction
```

### correction: 2026-10-01

- reason: R-115 -- the single-statement `insert()` / `update()` backend methods are removed (no product path called them and they committed without the audit hook); this comment no longer refers to them

old:
```
vocabulary here (mirroring `insert()`'s own translation) so `cell.py`'s `transact()`
```

new:
```
vocabulary here so `cell.py`'s `transact()`
```

## CH-0369

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.update_in_transaction`)
- parent commit: `4d45fc6`
- kind: comment

```
# P3-D2 (WP-1.5): no commit/rollback here (unlike `update` above)
# -- mirrors `insert_in_transaction`'s own reasoning above. Runs
# inside the transaction `transact()` already opened via
# `begin()` and will `commit()`/`rollback()` once, after every
# operation in the batch.
```

### correction: 2026-10-01

- reason: R-115 -- the single-statement `insert()` / `update()` backend methods are removed (no product path called them and they committed without the audit hook); this comment no longer refers to them

old:
```
no commit/rollback here (unlike `update` above) -- mirrors
```

new:
```
no commit/rollback here -- mirrors
```

## CH-0370

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.delete_in_transaction`)
- parent commit: `4d45fc6`
- kind: comment

```
# P3-D2 (WP-1.5): no commit/rollback here (unlike `delete` above)
# -- same reasoning as `update_in_transaction` immediately above.
# `cell.ApplicationCell` has already run this request through the
# same declare-and-echo confirmation choke `delete()` itself uses
# before this is ever called.
```

## CH-0371

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.read`)
- parent commit: `4d45fc6`
- kind: comment

```
# WP-3: `order_by` is always `None` or a non-empty LIST of
# `(field, direction)` tuples now (`cell.py::_bind_order_by`),
# multi-field sort included -- a pre-WP-3 single-field caller
# already reaches this as a one-element list.
#
# M-4: `_DIRECTION_TOKENS[direction]` (a closed dict lookup),
# never `direction.upper()` concatenated directly into SQL
# text -- see that constant's own docstring. `KeyError` for an
# unexpected value is translated to `errors.ValidationError`
# here rather than escaping raw, matching this backend's own
# existing translation discipline for every other native
# driver exception in this file.
```

## CH-0372

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.read`)
- parent commit: `4d45fc6`
- kind: comment

```
# WP-3e rework T1 (追補2 M-1): mirrors `backend_postgres.
# PostgresBackend.read`'s own identical site -- same
# literal denial `cell.ApplicationCell._bind_order_by`
# already carries, same 4-key treatment.
```

## CH-0373

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.delete`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 4: same pre-commit-hook structure as `create_collection`
# above -- `cell.ApplicationCell.delete` has already run this
# request through `_validate_delete_confirmation` before this is
# ever called.
```

## CH-0374

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.begin`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-7 (independent review round 2): defense in depth against ANY
# future case (not just the `OverflowError` this same round's fix
# closes off at `encode_value`) that raises an exception `cell.
# py::transact`'s own `except (...)` tuple does not list, leaving
# an earlier `BEGIN` transaction open on this connection --
# `sqlite3.Connection.execute("BEGIN")` on a connection that
# ALREADY has an open transaction raises `sqlite3.
# OperationalError: cannot start a transaction within a
# transaction`, permanently wedging every future `transact()`
# call on this cell. Rolling back any stray open transaction
# FIRST makes starting a fresh one always safe, regardless of
# what left the previous one open.
```

## CH-0375

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend`)
- parent commit: `4d45fc6`
- kind: comment

```
# ------------------------------------------------------------------
# Phase 9 WP-3c (design D-5, 追補 R-a; 監督裁定集約 rulings-r5-r6.md
# I-1): the process-local `self._idempotency` dict this backend keeps
# -- see `backend.StorageBackend`'s own docstrings for the full
# contract each method below implements.
# ------------------------------------------------------------------
```

## CH-0376

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend`)
- parent commit: `4d45fc6`
- kind: comment

```
# Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): thin
# wrappers -- `cell.py::ApplicationCell._idempotency_check` calls
# THESE now, not the three methods directly above. `conn` (code-
# review fix F6, Opus review 2, ruled in) is accepted (the
# `_idempotency_check` call sites need one uniform signature across
# backends) and ignored: this backend has no connection concept at
# all (`idempotency_connection` below always returns `None`), and
# `ApplicationCell._lock` (an `RLock`, widened by WP-6d/narrowed
# again by F5 to cover this method's own caller's ENTIRE lookup ->
# execute -> store window for a keyed, real request) already
# serializes every concurrent thread sharing this cell -- there is
# nothing left for a PostgreSQL-style advisory lock to add on this
# backend.
```

## CH-0377

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.idempotency_begin`)
- parent commit: `4d45fc6`
- kind: comment

```
# `deadline` (code-review fix F2, Opus review 2): accepted for
# the same uniform-signature reason `conn` is, above, and
# ignored identically -- this backend never takes a lock a
# deadline could bound.
```

## CH-0378

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.idempotency_unlock`)
- parent commit: `4d45fc6`
- kind: docstring

```
No-op -- `PostgresBackend`'s own counterpart releases the two
session-scoped `pg_advisory_lock`s `idempotency_begin`/
`idempotency_reserve` may have taken, on the SAME `conn` handle
those methods used (code-review fix F6); this backend never
takes any (see `idempotency_begin`'s own comment above), and
`conn` is always `None` here regardless of what `idempotency_
connection` returns to a caller from this backend.
```

## CH-0379

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.record_idempotency`)
- parent commit: `4d45fc6`
- kind: comment

```
# `transact()`'s own single-batch path: `ApplicationCell.transact`
# calls this directly (not through a DDL method's own
# `idempotency_record` parameter), immediately before its own
# `self._backend.commit()` -- a failed batch never reaches this
# line at all (the execution loop above it raises first), so this
# write and the batch's own commit share the identical fate,
# UNLESS `self._backend.commit()` itself is what fails -- see
# `idempotency_discard_pending` below (K-5, N-8), the cleanup
# `ApplicationCell.transact`'s own `except Exception:` calls for
# exactly that case.
```

## CH-0380

- moved from: `src/mitatedb_api/backend_sqlite.py` (`SQLiteBackend.idempotency_discard_pending`)
- parent commit: `4d45fc6`
- kind: comment

```
# Phase 9 WP-3cd closure (K-5, N-8): this dict write above is NOT
# part of `self._db`'s own real transaction -- `self.rollback()`
# (`self._db.rollback()`) cannot undo it, so `ApplicationCell.
# transact`'s `except Exception:` handler calls this directly,
# unconditionally, right after its own `self.rollback()` -- a
# `key` this dict never held (the ordinary case: SOME earlier
# step failed, before `record_idempotency` was ever reached) is a
# silent no-op, exactly like `create_collection`/`add_field`/
# `alter_field_constraints`'s own identical `self._idempotency.
# pop(idempotency_record[0], None)` cleanup.
```
