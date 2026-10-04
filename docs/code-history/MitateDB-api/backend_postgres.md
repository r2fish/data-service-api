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

### correction: 2026-10-04

- reason: R-82 -- `field_types_and_constraints` no longer reads the single query itself: it answers from the collection snapshot (`_collection_snapshot`); only the DDL methods still read `_field_types_and_constraints_locked`

old:
```
merged into the single query `_field_types_and_constraints_locked` above makes
```

new:
```
answered from the collection snapshot `_collection_snapshot` returns (the DDL methods read the single query `_field_types_and_constraints_locked` above makes)
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


## CH-0565

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.create_collection`)
- parent commit: `62136cd`
- kind: comment

```
# Phase 9 WP-3c (design D-5, I-1/I-8): the idempotency
# record is written as the LAST statement before this
# backend's own commit -- same connection, same
# transaction as the DDL above, exactly like `audit_hook.
# pre_commit()` immediately above it. `new_revision` was
# already read back for real, inside this SAME
# transaction, above -- unlike `backend_sqlite.
# SQLiteBackend`'s own in-process counterpart, nothing
# here is a prediction. The stored response mirrors this
# method's own final `return` below verbatim (same
# `name`/`fields`/`field_types`/`resolved_constraints`
# locals), so a later replay is byte-identical to what an
# uncached call would have returned.
```

### correction: 2026-10-03

- reason: R-42 -- the idempotency record is now written before the pre-commit audit hook (store, then hook, then commit), so the hook is not above the record write

old:
```
exactly like `audit_hook.pre_commit()` immediately above it
```

new:
```
before `audit_hook.pre_commit()` (which follows it and sends nothing on this connection)
```

## CH-0581

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.field_domains`)
- parent commit: `9a65cbc`
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

## CH-0582

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.add_field`)
- parent commit: `9a65cbc`
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

## CH-0568

- moved from: `src/mitatedb_api/backend_postgres.py` (`PostgresBackend.field_domains`)
- parent commit: `9a65cbc`
- kind: docstring

```
Live catalog lookup (R-2 stage 2) doubling as the value-domain
source B-1 (i) needs: for every column of `collection`, this
database's own `information_schema.columns.data_type` is mapped
back to a domain category `encode_value` can validate a bound
value against. Raises `errors.NotFoundError` if `collection` does
not exist -- the same existence-check role the pre-B-1
`field_names` method played.

Phase 6 WP-3 (design D-3, L6-1 (v)): a physical `text` column's
own domain is no longer a single shared `"text"` bucket
(`_DOMAIN_BY_DATA_TYPE`'s own corrected comment above) (in `postgres_types.py`) -- it is
looked up in the declared-type REGISTRY instead
(`_TEXT_DOMAIN_BY_DECLARED_TYPE`), which is the only place that
can recover which of `string`/`object`/`array`/`json` the column
actually is. A `text`-physical column absent from the registry
(should not occur for any field this peer's own `create_
collection`/`add_field` created after this WP -- see
`create_collection`'s own registry-write below) degrades to
`"string"`, never a crash.
```

### correction: 2026-10-04

- reason: R-82 -- the four per-collection catalog reads are answered from a process copy of the live read while the schema revision is unchanged, so the lookup is no longer a live read on every call

old:
```
Live catalog lookup (R-2 stage 2)
```

new:
```
Catalog lookup (R-2 stage 2; a live read, kept as a process copy while the schema revision is unchanged)
```

## CH-0569

- moved from: `src/mitatedb_api/backend_postgres.py` (`<module>`)
- parent commit: `9a65cbc`
- kind: docstring

```
PostgreSQL storage backend (R-2/R-3).

R-2 choke point: values are always bound as psycopg parameters, never
string-interpolated into SQL text. Identifiers reach this module already
syntax-checked by the shared allowlist (``identifiers.validate_identifier``,
re-applied here defensively as this module's own first gate too -- cheap,
and keeps this file's own safety property self-contained rather than
depending entirely on the caller having done it) and, for every identifier
that names something ALREADY EXPECTED TO EXIST (a collection/field a
read/write/filter references), additionally checked against this
database's own live catalog by ``field_domains`` before it is ever used --
only *new* names (``create_collection``/``add_field``) skip that second
stage, for the obvious reason that a name being created cannot already be
in the catalog; PostgreSQL's own ``DuplicateTable``/``DuplicateColumn``
still catches a collision there. Every identifier is composed into a
statement exclusively via ``psycopg.sql.Identifier`` -- this module never
builds a statement by embedding a name into a plain Python string.

Execution itself is centralized in ``_execute``, the ONLY function in this
module allowed to call ``cursor.execute`` directly: it rejects (``TypeError``,
at runtime, not merely by convention) anything that is not already a
``psycopg.sql.SQL``/``psycopg.sql.Composed`` object -- a bare Python
``str`` in particular -- so no method anywhere in this file has a route to
execute raw, string-interpolated SQL even by future accident.

WP-1 independent review B-1 (blocker): a value whose Python-level SHAPE
was acceptable (`cell.ApplicationCell._normalize_value`'s own
str/int/float/bool/None/dict/list check) can still MISMATCH the declared
PostgreSQL column type it is bound against (e.g. a string bound to a
`BIGINT` column, or an out-of-range integer bound to one) -- PostgreSQL
then raises a driver-level error (`InvalidTextRepresentation`,
`NumericValueOutOfRange`, ...) that used to escape this module's own
`errors.FoundationError` boundary entirely, AND left the connection in
PostgreSQL's own aborted-transaction state (every subsequent statement on
that connection failing with `InFailedSqlTransaction` until an explicit
`ROLLBACK`) because only the narrower `UniqueViolation`/`UndefinedTable`
handlers called `rollback()`. Fixed with two independent layers, per the
review's own two-layer split:

(i) ``field_domains`` reports each column's own DOMAIN category (`"text"`/
`"int32"`/`"int64"`/`"float"`, derived from this backend's own `_TYPES`
mapping via a live `information_schema.columns.data_type` query -- the
SAME live-catalog query `field_domains` already performs for stage-2
identifier validation, now also answering "what domain does this column
accept" in the same round trip). `encode_value(value, domain=...)`
deterministically rejects a value outside its target column's domain
BEFORE any statement reaches the database -- the SQLite backend's own
`encode_value` ignores `domain` entirely (matching WP-1 P3 round 2
instruction #1's own precedent: SQLite's more permissive behavior for the
embedded-NUL case stays UNCHANGED here too; SQLite's column affinity is
dynamic, so there is no equivalent mismatch to detect there).

(ii) every DML/DDL method below now has a FINAL, catch-all
``except psycopg.Error`` (after any more specific handler) that always
calls the correct connection's own `rollback()` before re-raising a
classified `errors.ValidationError` -- so a genuinely unanticipated
PostgreSQL-level rejection (anything layer (i) did not already catch)
still (a) never leaves a connection aborted for the next call on the same
cell, and (b) never leaks a raw `psycopg.Error` past this module's own
boundary. This is a deliberately conservative, defensive backstop, not a
precise error classification -- by the time layer (i) is in place, this
branch should be effectively unreachable for realistic client input; it
exists only so an unanticipated case still fails safely (connection
recovers, caller gets a classified exception) rather than poisoning the
connection for every future call.

This is not a port of r2db-api's own ``postgres.py`` (R-2's closing
paragraph: "the peer implementations are never shared" -- two independent
implementations of the same safety property is what gives the common
conformance suite its own detection power). Notable, deliberate
differences from that peer's own design: no row
addressability (``row_addressability`` stays declared ``unavailable`` --
see ``insert_in_transaction``'s own comment for why its ``rowid`` return value uses
PostgreSQL's ``ctid`` rather than a stable published address), and no Row
Level Security (this foundation's primary isolation wall is
database-per-application, R-1 -- RLS as an additional layer is future-work,
design v1.1 §7, not this WP's own containment boundary).

Connections and requests: each application has one bounded pool per role
(runtime, developer). A request borrows what it needs once, at its start
(``request_scope``), runs as ONE transaction on its main connection and
returns the connections when it ends, rolling back whatever is
uncommitted -- so no two requests ever share a connection or a
transaction, and nothing one request set on a connection reaches the next.
Requests on the same application run concurrently; what PostgreSQL
serializes for them is named at each lock (``lock_schema``,
``lock_entities``, the two idempotency locks).
```

### correction: 2026-10-04

- reason: R-82 -- the identifier check against the catalog uses a process copy of the live read while the schema revision is unchanged

old:
```
database's own live catalog by ``field_domains``
```

new:
```
database's own catalog (a live read, kept as a process copy while the schema revision is unchanged) by ``field_domains``
```

### correction: 2026-10-04

- reason: R-82 -- `field_domains` answers from a process copy of its live read while the schema revision is unchanged

old:
```
the SAME live-catalog query `field_domains` already performs
```

new:
```
the SAME live-catalog query `field_domains` already answers (from a process copy of its live read while the schema revision is unchanged)
```
