# r2db-api/postgres.py -- code-comment history (change set 1, v0.5 rule)

Companion for `r2db-api/src/r2db_api/postgres.py` per `docs/code-history/README.md`.

## CH-0001

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: docstring

```
`PostgresCell`: a `StorageBackend` (design D-1) over PostgreSQL via psycopg 3.

Design constraints this file is written to satisfy (design D-4):

- Values reach PostgreSQL exclusively through server-side bind parameters
  (via `psycopg.sql.Placeholder()` and a parameter list passed to
  `cursor.execute(...)`) or, for JSON-shaped values, `psycopg.types.json.Jsonb`
  -- never through string interpolation.
- Identifiers (table/column names) are composed only with `psycopg.sql.
  Identifier`, and only after (a) the shared syntax allowlist in
  `r2db_api.structured` and (b) verification against this application's
  *live* PostgreSQL catalog (`information_schema`), via `_load_catalog`.
  Syntax validation alone would still admit a well-formed but unknown
  identifier; the catalog check is what closes that gap.
- Operators and sort directions map to a fixed table of `sql.SQL` literals
  (`_COMPARISON_OPERATORS`); no operator string from a request is ever
  written into SQL text.
- No method on this class -- public or private -- accepts request-derived
  content and executes it as a `str`. `_run`, the single choke point every
  *client-influenced* statement passes through, is typed to accept only
  `psycopg.sql.Composed`/`psycopg.sql.SQL` and raises `TypeError` for
  anything else. Every SQL fragment built anywhere below that carries a
  client-supplied identifier/operator/value is constructed via
  `sql.SQL(...)`/`sql.Identifier`/`sql.Literal`/`sql.Placeholder`, never an
  f-string or `%`-formatted plain string, and never bypasses `_run`. The
  one exception, by design, not oversight: `_RolePool._liveness_check`'s
  pool-health probe (`cur.execute("SELECT 1")`) is a fixed, zero-argument
  literal with no request content anywhere near it -- a connection-pool
  implementation detail unrelated to any application-plane operation, and
  the only `.execute(...)` call in this file that does not go through
  `_run`.

This module does not duplicate validation. Identifier syntax, the operator
allowlist, mutation shape, and destructive-confirmation logic are imported
from `r2db_api.structured` and are the exact same functions `ApplicationCell`
uses -- see that module's "Shared validation/planning boundary" section.
This file only adds what is inherently PostgreSQL-specific: catalog lookup
against a live schema, SQL composition, session/transaction/timeout
handling, and per-role connection pooling.

Data model (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-2/R-4/R-7):
`create_entity` always provisions a server-assigned `id bigint GENERATED
ALWAYS AS IDENTITY PRIMARY KEY` (the row address) and an invisible
`_r2db_revision uuid NOT NULL DEFAULT gen_random_uuid()` (the per-row
optimistic-concurrency token), ahead of the caller's own declared fields.
Those own fields default to `JSONB` (`create_entity` never carries a
`field_type` -- rejected at the shared `bind_schema_operation` boundary);
`add_field`'s own optional `field_type` maps `string`/`integer`/`number`/
`boolean` to `TEXT`/`BIGINT`/`DOUBLE PRECISION`/`BOOLEAN` respectively, and
`object`/`array` to the two DOMAINs `migrations/0003_provision_application.
sql` provisions per application database, `_r2db_json_object`/
`_r2db_json_array` -- each a `jsonb` DOMAIN with a `jsonb_typeof(VALUE)`
CHECK, so PostgreSQL's own catalog (`information_schema.columns.
domain_name`) is what lets `_load_catalog` tell "declared as object" apart
from "declared as array" apart from "untyped JSONB" (WP-3 review, "object/
array の DOMAIN 型統一": a bare `jsonb` column cannot report this
distinction at all). `id`/`_r2db_revision` require PostgreSQL 13+
(`gen_random_uuid()` is a built-in as of that version).

Two layers validate a value written to an `object`/`array` column: `_check_
type` (shared with `ApplicationCell`, `r2db_api.structured`) refuses a
non-dict/non-list value with `VALIDATION_FAILED` naming only the field --
this is what a well-behaved client actually sees. The DOMAIN's own
`jsonb_typeof` CHECK is a second, defence-in-depth layer underneath that:
a real server-side invariant that should never fire if `_check_type` is
doing its job, so a CHECK violation is left to fall through to this
module's ordinary `SERVICE_UNAVAILABLE` mapping (a true "this should never
happen" backstop, not a validation response) rather than being decoded and
re-surfaced as a second `VALIDATION_FAILED` path.

Two legitimate, accepted cross-backend semantic differences remain: an
untyped (JSONB) column has no per-column type in the shared `r2db_api.
structured` vocabulary (`None`), so `lt`/`lte`/`gt`/`gte` comparisons that
would raise `TypeError` against mismatched Python types in `ApplicationCell`
typically do not raise here -- PostgreSQL's own jsonb ordering is total
across JSON types, producing a deterministic (if occasionally surprising)
`ORDER`-consistent boolean instead. And a `jsonb` (or `_r2db_json_object`/
`_r2db_json_array`-domain) column's own storage normalizes the value it is
given -- an object's key order is not the order it was written in JSON
source (PostgreSQL's own `(byte length, byte value)` order, `r2db_api.
structured._jsonb_text` reproduces this for `contains`/`matches`'s own
text-form comparison, WP-3 review N-1/N-2), and a duplicate key collapses
to its last-written value, silently, the same way a plain Python `dict`
literal with a repeated key would -- `ApplicationCell`, storing the Python
value directly with no serialization round-trip, does not normalize either
of these at write time, though a query response's item order/shape is
otherwise identical between the two backends for every value this
contract's type vocabulary can express. Both are what the Security
Invariants allow (implementations are not required to share a physical
data model), not validation gaps: both backends still reject bad
identifiers/operators/shapes, and the exact same errors/precedence for
every other checked property (addressability, uniqueness, revision
preconditions, `contains`/`matches` literal/wildcard semantics against
SQL's own three-valued logic, and object/array typing), identically.
```

## CH-0002

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# `_FIELD_TYPE_SQL`/`_JSONB_SQL` are not used directly in this module; the
# import exists only as a facade-compat re-export (design D-2) for callers
# that still import them from `postgres`.
```

## CH-0003

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): two-int
# `pg_advisory_xact_lock(namespace, hashtext(key))` namespace for the
# PER-KEY idempotency lock -- see `_idempotency_key_lock` below.
#
# Code-review fix F7 (Opus review 2): the rationale this comment
# carried before this fix was FALSE and is corrected here (the constant
# itself is unaffected). It claimed a namespace of 0 would land in the
# SAME lock space the single-bigint form `ops.py::_RITUAL_ADVISORY_
# LOCK_KEY` (1414141) uses, risking a collision between a bootstrap/
# reset ritual's lock and an idempotency-key lock. PostgreSQL actually
# keeps those two key spaces disjoint by construction, regardless of
# namespace value: the 1-argument `pg_advisory_xact_lock(bigint)` form
# and the 2-argument `pg_advisory_xact_lock(int, int)` form record
# different `objsubid` values in `pg_locks` (1 for the 1-argument form,
# 2 for the 2-argument form) -- so `pg_advisory_xact_lock(1414141)` and
# `pg_advisory_xact_lock(0, 1414141)` are two DIFFERENT locks, never the
# same one, even though they would superficially "look like" the same
# 64-bit id under a naive `(namespace << 32 | key2)` encoding. This
# namespace constant is still a large, distinctive value, far from both
# `_RITUAL_ADVISORY_LOCK_KEY` values (r2db 1414141, MitateDB 761761761)
# and from `_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY` below -- kept for
# HUMAN legibility (so two DIFFERENT lock families never share a
# suspiciously similar-looking id in a `pg_locks` dump), not because a
# collision with the 1-argument form was ever actually possible.
```

## CH-0004

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling U-7: table-level (not per-key) advisory lock serializing
# `_idempotency_reserve`'s COUNT-then-write across DIFFERENT keys (D-5
# (iii)) -- same family as `ops.py::_RITUAL_ADVISORY_LOCK_KEY` (a
# single, fixed 64-bit `pg_advisory_xact_lock` key), a DIFFERENT
# constant from it (that lock guards bootstrap/reset ritual ordering;
# this one guards `idempotency_entries` capacity accounting -- two
# independent serialization points that must never share one lock id).
```

## CH-0005

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# The two DOMAIN types' own bare names (as `information_schema.columns.
# domain_name` reports them -- unqualified, WP-3 review confirmed
# empirically), mapped back to the shared `r2db_api.structured` vocabulary
# string `_load_catalog` reports for such a column's declared type.
```

## CH-0006

- moved from: `src/r2db_api/postgres.py` (`_TableInfo`)
- parent commit: `944e86b`
- kind: docstring

```
One entity table's live shape, as re-derived from PostgreSQL's own
catalog by `PostgresCell._load_catalog` on every call (never cached
across calls, never trusted as a standing assumption -- D-4/R-1).

`columns`: declared field name -> declared type in the shared
`r2db_api.structured` vocabulary (`"string"`/`"integer"`/`"number"`/
`"boolean"`/`"object"`/`"array"`), or `None` for an untyped/JSONB-
equivalent column. `"object"`/`"array"` are recovered from PostgreSQL's
own `information_schema.columns.domain_name` (WP-3 review, "object/
array の DOMAIN 型統一") -- a plain `jsonb` column with no domain
reports `None`. Includes `"id"` (always `"integer"`); never includes
the invisible `"_r2db_revision"` column (R-3/R-4).

`indexes`: client index name -> `{"physical": <table>__<index> name,
"fields": (declared field name, ...), "unique": bool}`, covering every
index `PostgresCell.apply_schema`'s own `create_index` has created on
this table (both unique and non-unique -- SI-08/R-5: both count toward
`schema_objects`), excluding the primary key on `id` (R-1/§2: an
address, not a domain uniqueness declaration).
```

## CH-0007

- moved from: `src/r2db_api/postgres.py` (`_run`)
- parent commit: `944e86b`
- kind: docstring

```
The single execution choke point. Typed to accept only a composed
psycopg SQL object -- never `str` -- so a raw string cannot reach the
database from anywhere in this file, as a checked property rather than a
convention (design D-4).
```

## CH-0008

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.__init__`)
- parent commit: `944e86b`
- kind: comment

```
# Q4 WP-3 (design D-3(f)): kept as a plain attribute, separate from
# `self._runtime` below, so `verify_platform_upgrades_applied` can
# open a single, UNPOOLED, explicitly-closed connection for its own
# one-shot cell open time check -- never through the shared pool
# manager. Reaching through `self._runtime`'s own pool instead
# would leave a live connection sitting in that pool indefinitely
# (pools are released only by `close()`/idle eviction, never by
# this class itself), which would needlessly hold every served
# application's runtime database open from the moment its cell is
# constructed, before a single real request against it ever
# arrives -- exactly the standing-connection cost this class' own
# "no pool is created here at construction time" design (this
# docstring's own paragraph above) exists to avoid.
```

## CH-0009

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._describe_table`)
- parent commit: `944e86b`
- kind: docstring

```
One entity's `EntityDescriptor` (contract shape) -- factored
out of `catalog()` below (WP-2b) so `apply_schema`'s own `dry_run`
response can build the identical descriptor for the ONE entity a
schema operation targets (D-4 (3)), re-reading `table_info` from
the SAME open transaction/connection a tentative (not yet
committed, and about to be rolled back) DDL/registry write just
ran in -- mirrors `ApplicationCell._describe_entity`'s identical
role for the in-memory backend, without sharing code with it.
```

## CH-0010

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._describe_table`)
- parent commit: `944e86b`
- kind: comment

```
# Phase 6 WP-2 (design D-3(iii)): `table_info.columns`
# is already `{field_name: declared_type_or_None}` --
# `None` (untyped/JSONB) reports as `json`, decision
# (ii)'s own default.
```

## CH-0011

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._load_catalog`)
- parent commit: `944e86b`
- kind: comment

```
# Never a known/selectable field (R-3/R-4).
```

## CH-0012

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._load_catalog`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling M-4 (rulings-wp2a-review.md): the side-table read
# (a nested SAVEPOINT + SELECT + RELEASE SAVEPOINT, `_load_field_
# constraints` below) is skipped entirely when `with_constraints`
# is `False` -- `query` (D-2 (2): "query の predicate 値は enum を
# 検査しない") never uses `table_info.constraints` at all, so
# paying for that read on every read-only request is pure waste.
```

## CH-0013

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._load_field_constraints`)
- parent commit: `944e86b`
- kind: docstring

```
Contract 1.7.0 (D-2 (4), WP-2a): reads the side-table registry
(`public._r2db_field_constraints`, migration `0010_field_
constraints_upgrade.sql`) -- the declaration's own source of truth
(physical column constraints are never added, §4 A-1). `conn` is
already inside the caller's own `with conn.transaction():` block
(`catalog`/`transact`/`apply_schema` above), so this method opens a
NESTED transaction (a real PostgreSQL SAVEPOINT once already inside
one) around its own read: if the table does not exist yet (an
application that has never run `python -m r2db_api.ops upgrade-
applications` for upgrade 10, WP-2a completion condition 10), that
one savepoint rolls back to a clean, still-usable state and this
method returns `{}` -- every entity/field then reports the
version-wide default (`nullable: true`, no `enum`). An application
that never declares any `field_constraints`/`enum`/`nullable` at
all keeps working unmodified without ever needing that upgrade;
only an attempt to WRITE a declaration (`_write_field_constraints`
below) actually needs the table to exist -- that failure is left
to propagate to this class' own existing `except psycopg.Error`
handling (`transact`/`apply_schema`), which already maps it to a
safe `SERVICE_UNAVAILABLE` with no rows changed (the enclosing
`with conn.transaction():` rolls the whole operation back).
```

## CH-0014

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._clear_field_constraints`)
- parent commit: `944e86b`
- kind: docstring

```
Monitor ruling B-3 (rulings-wp2a-review.md): `drop_entity`'s own
registry cleanup, protected the same way `_load_field_constraints`
above protects its own read -- a real PostgreSQL SAVEPOINT (a
NESTED transaction, `conn` is already inside `apply_schema`'s own
outer `with conn.transaction():`) around the `DELETE`, swallowing
`UndefinedTable` if the side table itself was never created (an
application that has never run upgrade `10`). `drop_entity` must
succeed for such an application regardless -- dropping an entity
that never had a `field_constraints` row is unrelated to whether
the registry TABLE exists at all, unlike `alter_field`/`create_
entity`/`add_field` actually WRITING a declaration, which legitimately
needs the table and is left to fail closed (`SERVICE_UNAVAILABLE`,
`_write_field_constraints`'s own docstring) if it is missing.
```

## CH-0015

- moved from: `src/r2db_api/postgres.py` (`PostgresCell`)
- parent commit: `944e86b`
- kind: comment

```
# ---- idempotency (contract 1.7.0 D-5, WP-2c) --------------------------
#
# Ruling I-1/U-3 = (A): the Postgres-backend counterpart of `Application
# Cell`'s process-internal dict -- the `public._r2db_idempotency` side
# table, migration `0011_idempotency_records_upgrade.sql`, read/written
# inside the SAME `with conn.transaction():` block `transact`/`apply_
# schema` already open (D-5 (1)/(3): "同一 tx で書く"). Expiry uses
# PostgreSQL's own `now()`, never a client-supplied clock value -- this
# is a durable side table shared by concurrent requests, unlike
# `ApplicationCell`'s single-process dict, so the DATABASE's own notion
# of "now" is what a lazy reclaim compares against.
#
# Read (`_idempotency_lookup`) fails CLOSED on a missing table (ruling
# J-5, WP-2cd audit N-6) -- an application that has never run upgrade
# 11 gets `SERVICE_UNAVAILABLE` right here, before target-existence/
# execution, exactly like the WRITE (`_idempotency_store`) already did:
# `UndefinedTable` is left to propagate to `transact`/`apply_schema`'s
# own `except psycopg.Error` clause, rolling back the (as yet empty)
# transaction and touching no row. This method runs FIRST on the
# idempotent path (before `catalog`/target-existence in `transact`;
# right after `catalog` but before any operation-specific work in
# `apply_schema`), so nothing has executed yet when it raises. Before
# this ruling, this method instead caught `UndefinedTable` and
# returned `None` ("no record found"), which let a request pay for
# target-existence/execution before failing at `_store` regardless --
# same eventual `SERVICE_UNAVAILABLE`, strictly more work done first.
# `_idempotency_reserve` (below) can therefore no longer actually
# observe `UndefinedTable` in practice: on this same path it always
# runs after this method has already succeeded (or already raised),
# in the SAME transaction, so the table's existence cannot change in
# between -- its own guard is kept anyway (defense in depth, and it
# matches `_load_field_constraints`'s own posture of not depending on
# a caller having gotten the ordering right).
```

## CH-0016

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_key_lock`)
- parent commit: `944e86b`
- kind: docstring

```
Ruling U-7 (WP-6d): transaction-scoped advisory lock keyed on
this idempotency key -- taken directly in the OUTER `with conn.
transaction():` (`transact`/`apply_schema`), immediately BEFORE
calling `_idempotency_lookup`, never inside `_idempotency_
lookup`'s own nested `with conn.transaction():` (a SAVEPOINT).
`pg_advisory_xact_lock` auto-releases only at the enclosing
(outer) transaction's own commit/rollback, never at a savepoint
rollback or a savepoint's own commit -- taking it here, before
the savepoint even opens, makes that lifetime obvious by
construction rather than relying on that Postgres-specific
savepoint/advisory-lock interaction.

Effect: a second concurrent request for the SAME key blocks here
until the first's transaction commits or rolls back. It then
proceeds to `_idempotency_lookup` and sees either the first
request's now-committed record (same digest -> replay, different
digest -> CONFLICT) or nothing at all (first request rolled
back -- e.g. `NOT_FOUND`/a refused confirmation -- so this
request executes as new). The DB is per-Application (module
docstring), so the raw idempotency key alone is Application-
scoped already -- no extra scoping component is needed here.

Two-int form (`_IDEMPOTENCY_KEY_LOCK_NAMESPACE`, `hashtext(key)`)
chosen over a plain `hashtext(key)::bigint`: `hashtext` alone is
only a 32-bit hash, so a bare-bigint lock would put every key's
lock in the SAME narrow 32-bit-sized space `_IDEMPOTENCY_COUNT_
ADVISORY_LOCK_KEY` and `ops.py::_RITUAL_ADVISORY_LOCK_KEY` also
occupy (all three are small positive integers); namespacing the
high 32 bits keeps per-key locks in a visibly separate space.
`hashtext` collisions between two DIFFERENT keys are accepted
(ruling U-7): a collision only over-serializes (two unrelated
keys briefly wait on each other), it can never under-serialize.
```

## CH-0017

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_reserve_lock`)
- parent commit: `944e86b`
- kind: docstring

```
Ruling U-7 (WP-6d): table-level advisory lock serializing
`_idempotency_reserve`'s COUNT-then-write across DIFFERENT keys
(D-5 (iii)) -- taken directly in the OUTER transaction, BEFORE
calling `_idempotency_reserve`, never inside that method's own
nested `with conn.transaction():` savepoint (same reasoning as
`_idempotency_key_lock` above: the lock's lifetime should not
depend on savepoint/advisory-lock interaction being understood
by a future reader). A constant lock id (not keyed on anything)
because this guards the TABLE'S row count, not any one key.

`LOCK TABLE public.<idempotency table> IN SHARE MODE` was
considered and rejected for this same purpose: two concurrent
SHARE lock holders never conflict with EACH OTHER (SHARE only
conflicts with ROW EXCLUSIVE and stronger), so both would pass
the COUNT and only then deadlock against each other's own
subsequent INSERT (which needs ROW EXCLUSIVE, which SHARE does
conflict with) -- see the WP-6d report for the Phase 9 R-2
precedent's own lock mode finding. `pg_advisory_xact_lock` has
no such self-conflict-free class: a second holder of the SAME
key always waits for the first, full stop.
```

## CH-0018

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_reserve`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling J-6 (WP-2cd audit N-7): the lazy-reclaim DELETE this method
# used to also issue here is dropped -- `_idempotency_lookup`, this
# same transaction, always runs first on this path and already
# reclaimed every expired record moments earlier; a second DELETE
# here was always a 0-row no-op (measured, WP-2cd closure: `_run`
# count for a keyed write drops from 11 to 10; a replay never
# reaches this method at all and stays at 4).
```

## CH-0019

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_reserve`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling I-6/D-5 (5): checked BEFORE this request executes anything
# -- reusing the SAME generic `ResourceLimits.check()` every other
# COUNT-valued class already uses (`ApplicationCell`'s identical
# `_idempotency_reserve` comment).
```

## CH-0020

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_store`)
- parent commit: `944e86b`
- kind: comment

```
# M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2, WP-2e
# closure audit R-1): `ON CONFLICT (idempotency_key) DO UPDATE`,
# not a bare `INSERT` -- a resend of a key whose stored record was
# just treated as absent (`_idempotency_record_has_request_id`
# returned false, at both call sites below) reaches this SAME
# method for the SAME key, and must overwrite the stale row
# rather than fail on the primary key it still holds -- an
# expired-but-not-yet-reaped row, or a pre-1.7.0-shaped row with
# no `request_id` at all, are the only ways a live row can still
# be sitting under this key when this INSERT runs. Mirrors
# `ApplicationCell._idempotency_store`'s plain dict assignment,
# which overwrites unconditionally by construction.
#
# Ruling U-7 (WP-6d, `{scratchpad}/review2/frame.md` F-①): this
# `ON CONFLICT DO UPDATE` is NOT what makes concurrent same-key
# requests safe -- `_idempotency_key_lock` (taken by every caller
# before `_idempotency_lookup`, in the same outer transaction)
# is what closes that race, by making the second concurrent
# request wait for the first's commit/rollback before either one
# reaches this method at all. Once that lock serializes entry,
# nothing else can be racing THIS INSERT for the SAME key: the
# conflict this clause resolves is only ever this key's own
# prior (already-committed, sequential) row -- never a row a
# peer transaction is concurrently trying to write right now.
# Kept as `DO UPDATE` (not narrowed to a bare `INSERT`) purely
# for that stale-row-still-present case above, not for
# concurrency.
```

## CH-0021

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.query`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling M-4: `query` never reads `table_info.
# constraints` (D-2 (2): predicates are not bound by
# `enum`/`nullable`) -- skip the side-table read.
```

## CH-0022

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.query`)
- parent commit: `944e86b`
- kind: comment

```
# R-6: identifier/catalog-checked order_by, with a
# deterministic trailing `id ASC` tie-break appended
# whenever the caller's own order_by does not already
# mention `id` -- the exact same shared function
# `ApplicationCell.query` uses, so both backends accept/
# reject the same order_by shapes identically.
```

## CH-0023

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.query`)
- parent commit: `944e86b`
- kind: comment

```
# R-7, corrigendum M-9: validate every predicate's value
# type before touching stored rows at all -- the same
# shared function and the same ordering `ApplicationCell.
# query` uses.
```

## CH-0024

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.query`)
- parent commit: `944e86b`
- kind: comment

```
# R-6: the cursor's opaque shape hash binds the
# Application scope, entity, and the full query shape
# (select/where/order_by/size) -- decoded (and
# validated) here, before any SQL referencing it runs.
```

## CH-0025

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.query`)
- parent commit: `944e86b`
- kind: comment

```
# R-6: `rows` was fetched with `LIMIT page_size + 1` (the look-ahead
# row, if present, is never returned to the caller -- it only
# signals `has_more`); `min(len(rows), page_size)` therefore equals
# `page_size` whenever at least `page_size` rows matched, or the
# true (smaller) match count otherwise -- exactly the quantity
# `ApplicationCell.query`'s own equivalent check computes from its
# full (unbounded) in-memory match list, before it slices to a
# window.
```

## CH-0026

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._select_statement`)
- parent commit: `944e86b`
- kind: comment

```
# R-6: NULL placement (ASC -> NULLS LAST, DESC -> NULLS FIRST) is
# PostgreSQL's own default when no NULLS clause is given, which is
# exactly the semantics `ApplicationCell._sort_key` was written to
# match -- no explicit NULLS FIRST/LAST needed here. Likewise, a
# plain (untyped/JSONB) column's own cross-type ordering (ascending:
# String < Number < Boolean < Array < Object) falls directly out of
# PostgreSQL's native `jsonb` comparison operators.
#
# `offset`/`page_size` are always server-computed, already-validated
# non-negative integers (never client-supplied text) by this point
# -- `sql.Literal` here is composing a trusted value, the same
# pattern `_set_timeouts` already uses for its own computed values.
```

## CH-0027

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: docstring

```
`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
the single tx-exit point sits right before the pre-commit hook,
inside the SAME `with conn.transaction():` block every operation
already writes its (uncommitted) row changes in. A `dry_run`
forces a real ROLLBACK via `psycopg.Rollback` (caught and
swallowed by `conn.transaction()`'s own `__exit__`, never
surfacing as an error -- `ApplicationCell.transact`'s in-memory
`before`-restore, realized with a real transaction instead of a
`deepcopy`) rather than committing; `committed` below carries the
decided result out of that block, since a raise cannot itself
return a value.
```

## CH-0028

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-5 (8), addendum 2 S-b, ruling I-3,
# WP-2c): the idempotency lookup -- see `Application
# Cell.transact`'s identical comment for the ordering
# rationale (after bounds, before target existence). A
# `dry_run` never consults or writes a record (ruling
# I-7/D-4).
```

## CH-0029

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling U-7 (WP-6d): taken in THIS outer
# transaction, before `_idempotency_lookup` opens
# its own nested savepoint -- see `_idempotency_
# key_lock`'s own docstring for why the lock must
# sit here and not inside that savepoint.
```

## CH-0030

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# L-6/M-6: a record with no `request_id` (pre-1.7.0)
# is not a usable replay source -- treated as
# absent, checked before the digest comparison.
```

## CH-0031

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling I-3/I-8: answered from the record --
# target existence, confirmation, precondition
# and execution never run for a replay.
```

## CH-0032

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# M-6: the ORIGINAL execution's own
# `request_id` (guaranteed present), no
# fallback to this resend's own.
```

## CH-0033

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling I-6/D-5 (5): capacity checked before this
# request executes anything. Ruling U-7: the
# table-level count lock is likewise taken in
# THIS outer transaction, before `_idempotency_
# reserve` opens its own nested savepoint.
```

## CH-0034

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a, WP-2b):
# read ONCE, before any row change this transaction is
# about to (tentatively) make -- mutations never
# advance this counter, but reading it here (rather
# than after the loop) keeps this identical in spirit
# to `apply_schema`'s own "before this operation's own
# tentative write" read. Review round F-5: gated on
# `dry_run or plan is not None` too -- an ordinary
# apply (neither) skips both the digest computation
# AND this method's own extra `_read_schema_revision`
# round trip, which `delete` would otherwise pay
# twice over (once here, once for its own confirmation
# phrase).
```

## CH-0035

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# WP-2 review M-2 parity: per-operation deadline
# check, not only before/after the whole batch.
```

## CH-0036

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling M-3/D (rulings-wp2a-review.md):
# this operation's own position in the request's
# `operations` list -- `_apply` composes `details.
# field` as a request-internal path from it
# (`operations/<i>/values/<field>`, D-3 (2)).
```

## CH-0037

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# Phase 4 (design D-2): the pre-commit hook is the LAST
# statement inside this `with conn.transaction():`
# block -- a raise here propagates straight through the
# block's own `__exit__`, which rolls the data
# transaction back exactly like any other exception
# raised inside it (no special-casing needed at this
# call site: fail-closed by construction).
```

## CH-0038

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `944e86b`
- kind: comment

```
# `conn.transaction()` rolls back the *entire* batch on any
# exception (including a `FoundationError` raised by a later
# operation), giving the whole batch one real database transaction
# (D-5) in place of `ApplicationCell`'s in-memory deepcopy/restore.
# `assigned_addresses` (CCR-13, R-5) lists, in operation order, the
# address of every operation that resolved to an insert (a plain
# `insert`, or an `upsert` whose declared key found no existing
# row) -- an `upsert` that resolved to an update contributes
# nothing here, exactly like `ApplicationCell.transact`. `plan`
# (D-4 (3)) is surfaced only for a `dry_run` -- `None` for a real
# commit (`committed=True`), matching `ApplicationCell.transact`.
```

## CH-0039

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._fail_unique_conflict`)
- parent commit: `944e86b`
- kind: docstring

```
R-5, corrigendum M-5: map a real PostgreSQL `UniqueViolation`
(raised naturally by any INSERT/UPDATE that collides with a
`create_index(unique=True)`-declared index -- including one other
than the key an `upsert` used for its own existence test, R-5's
"既存重複は CONFLICT") to the contract's `CONFLICT`, disclosing at
most the client-recognizable index name and never PostgreSQL's own
DETAIL text, constraint/index internals, or any row value. `exc.
diag.constraint_name` is PostgreSQL's own (physical) index name; it
is only ever used here to look up the corresponding client name by
stripping this backend's own `{entity}__` naming convention -- never
surfaced to the caller directly.
```

## CH-0040

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._fail_client_value`)
- parent commit: `944e86b`
- kind: docstring

```
R-7 addendum (WP-3 review blocker-2): a `psycopg.errors.
DataError` (SQLSTATE class 22 -- e.g. `NumericValueOutOfRange`, or
a NUL byte PostgreSQL's `text`/`jsonb` storage cannot hold at all)
is always a decisive, deterministic client-supplied-value bug, not
a transient server condition -- `VALIDATION_FAILED`, never
`SERVICE_UNAVAILABLE` (which reads as "retry", and an AI agent
client retrying an identical, never-succeeding request is exactly
the failure mode this refusal exists to prevent). This is a second,
defence-in-depth layer underneath the shared boundary's own value-
domain checks (`r2db_api.structured._check_type`'s integer-range/
NUL-byte validation, `_validate_wildcard_pattern`'s grammar check)
-- those already refuse every value this maps today before it ever
reaches SQL, so reaching this handler in practice means either
check has a gap, not that this handler is the primary defence.
Fixed message, no `details`: unlike `_fail_unique_conflict` above,
a single `DataError` from a whole batch/statement cannot be
reliably attributed to one specific field from this generic catch
site, so no field name is guessed at (`errors.disclosure`: never
wrong information is safer than no information).
```

## CH-0041

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._bind_value`)
- parent commit: `944e86b`
- kind: docstring

```
R-7 addendum (WP-2 review M-B, confirmed empirically against a
real server): a JSON `null` must bind as SQL `NULL` for every
column shape, typed or untyped -- `Jsonb(None)` would instead
produce the JSONB literal `'null'::jsonb` for an untyped column,
which would make `is_null` predicates and `order_by` NULL placement
diverge from `ApplicationCell`'s own null semantics. A non-null
value binds as a native parameter for a scalar-typed column
(`string`/`integer`/`number`/`boolean`) or wrapped in `Jsonb(...)`
for an untyped column *or* an `object`/`array` one -- the latter
two are still physically `jsonb` underneath their DOMAIN (WP-3
review, object/array DOMAIN unification), so psycopg must still be
told to serialize the value as jsonb, exactly as for an untyped
column.
```

## CH-0042

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply`)
- parent commit: `944e86b`
- kind: comment

```
# R-7, corrigendum M-9: value types are validated before
# anything is sent to the database.
```

## CH-0043

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply`)
- parent commit: `944e86b`
- kind: comment

```
# R-4, corrigendum m-5: destructive confirmation is checked
# before any precondition-related outcome (never resolves to a
# PRECONDITION_FAILED/NOT_FOUND).
```

## CH-0044

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply`)
- parent commit: `944e86b`
- kind: comment

```
# Phase 4 (design D-2): reaching this point means the
# confirmation choke above did not raise -- confirmed-
# destructive, same signal `ApplicationCell._apply` returns.
```

## CH-0045

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._append_revision_predicate`)
- parent commit: `944e86b`
- kind: docstring

```
R-4: an `expected_revision` precondition is folded into the same
WHERE clause as the caller's own predicate (`<predicate> AND
_r2db_revision::text = $expected`), so the comparison and the write
are one atomic statement (the contract's revision-precondition
clause 5) rather than a separate read-then-write.

The comparison casts the `uuid` column to `text` rather than
binding `expected_revision` as a (contextually inferred) `uuid`
parameter: `expected_revision` is an arbitrary contract-opaque
client string (`bind_mutation` only bounds its length, since the
contract never requires it to look like a UUID), and PostgreSQL
raises a hard `invalid input syntax for type uuid` error -- not
just "does not match" -- for a non-UUID-shaped one. `ApplicationCell`
stores/compares revisions as plain Python strings, so a garbage
`expected_revision` there simply fails to match any row (resolving
to `PRECONDITION_FAILED`/`NOT_FOUND` the normal way); casting to
`text` here is what keeps that same "never matches, never raises"
behaviour on this backend too, instead of a `SERVICE_UNAVAILABLE`
this predicate's own value should never be able to trigger.
```

## CH-0046

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._resolve_precondition_miss`)
- parent commit: `944e86b`
- kind: docstring

```
R-4, corrigendum M-2: when a revision-qualified UPDATE/DELETE
affects zero rows, re-evaluate the caller's own predicate alone (no
revision clause), in the same transaction, to decide which of the
two failures applies -- `PRECONDITION_FAILED` (a row exists, but its
revision was not the one asserted) or `NOT_FOUND` (no row matches
the predicate at all, so there was no row to assert about).
```

## CH-0047

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._update`)
- parent commit: `944e86b`
- kind: comment

```
# R-4, corrigendum M-1: this branch is only reachable without a
# precondition -- `bind_mutation` already rejects an empty-
# `values` `update` carrying `expected_revision` outright, so a
# precondition is never silently discarded here.
```

## CH-0048

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `944e86b`
- kind: comment

```
# R-7, corrigendum M-9: type-check before any SQL runs, symmetric
# with insert/update above.
```

## CH-0049

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-2 (3)(ii), contract text: "An upsert that
# resolves to an insert is refused on the same rule [as insert];
# an upsert that resolves to an update is not"). Unlike `_apply`'s
# plain `insert` branch, this backend cannot know ahead of the two
# real SQL statements below whether THIS upsert will resolve to an
# insert or an update (corrigendum M-4: no separate existence
# check drives that choice) -- so the missing-field question is
# only even asked (one extra, targeted `SELECT ... LIMIT 1`,
# skipped entirely when every non-nullable field IS present, the
# common case) when it can actually change the outcome: a
# precondition (`expected_revision`) already guarantees this
# upsert can never resolve to an insert (R-5, `_apply_upsert`'s own
# docstring), so this check does not apply there at all.
```

## CH-0050

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling M-2 (rulings-wp2a-review.md): `FOR UPDATE`
# locks the row this existence check found, inside this
# same transaction, for the rest of it -- without this, a
# concurrent session could DELETE this exact row and
# commit between this `SELECT` (finds it, "resolves to
# update") and the `INSERT ... ON CONFLICT DO NOTHING`
# below, letting that INSERT actually insert (the key is
# free again) -- a row missing a `nullable: false` field,
# never caught, because this check already concluded
# "resolves to update, skip it". Locking the row means the
# concurrent DELETE blocks until this transaction commits
# or rolls back, so the row this SELECT saw is still there
# (or the whole transaction serializes behind it) when the
# INSERT/UPDATE below actually run -- the missing-field
# verdict this check reaches can no longer go stale.
```

## CH-0051

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `944e86b`
- kind: comment

```
# R-5: a precondition never resolves an upsert to an insert --
# no key match is NOT_FOUND (via `_resolve_precondition_miss`),
# exactly like update/delete.
```

## CH-0052

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `944e86b`
- kind: comment

```
# M-4: the row this INSERT's ON CONFLICT saw was removed by a
# concurrent transaction before this UPDATE could find it --
# neither statement resolved, so the whole batch rolls back as
# a concurrent-modification conflict rather than silently
# inserting a second time.
```

## CH-0053

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._text_expression`)
- parent commit: `944e86b`
- kind: docstring

```
The text form of `column` that `contains`/`matches` compare
against. R-7: "非 text 列は従来どおり ::text に対して適用" -- a
typed non-text column's plain `::text` cast is exactly this (a
numeric/boolean column's text representation carries no quoting
ambiguity). An *untyped* (JSONB-equivalent) column is different:
PostgreSQL's own `::text` cast on jsonb returns the JSON text
representation, which wraps a JSON **string** value in literal
double quotes (`"hello"`, not `hello`) -- silently breaking a full-
string-anchored `matches` pattern and shifting every `contains`
substring offset by one quote character, for exactly the columns
most likely to hold free-text data. `#>> '{}'` (the same "unwrap a
top-level jsonb scalar to text" idiom `->>`/`#>>` use for a keyed
value) recovers the bare string PostgreSQL's own client already
knows, and returns the same non-quoted text `::text` would for a
non-string JSON scalar (number/boolean/null) or an object/array --
it only differs from `::text` in the case that would otherwise be
wrong. This is what keeps the two backends' behaviour for a string-
typed field in parity, whether the client declared it via `add_field
field_type: "string"` or left it untyped.
```

## CH-0054

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._predicate_sql`)
- parent commit: `944e86b`
- kind: comment

```
# R-7, corrigendum m-7: each element gets the same per-column
# type-aware bind (native for a typed column, `Jsonb(...)` for
# an untyped one, SQL NULL for a JSON null) as every other
# value position -- never a blanket `Jsonb(v)`.
```

## CH-0055

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._predicate_sql`)
- parent commit: `944e86b`
- kind: comment

```
# Q-2 (案i): literal substring containment -- `%`/`_`/`\`
# in the value are escaped before being wrapped in
# `%...%`, so no character of the value is ever
# interpreted as a wildcard. `_validate_predicate_types`
# (called by every caller of this method) has already
# required `predicate.value` to be a string by this point.
```

## CH-0056

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._predicate_sql`)
- parent commit: `944e86b`
- kind: comment

```
# Q-2 (補足案): the client's pattern already uses exactly
# SQL LIKE's own wildcard grammar (`%`/`_`/`\`-escape) --
# bound as-is, no transformation.
```

## CH-0057

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._predicate_sql`)
- parent commit: `944e86b`
- kind: comment

```
# Unreachable in practice: `predicate.validate()` (called by
# `validate_predicates`, upstream of every caller here) already
# rejects any operator outside `structured.OPERATORS`. Kept as
# an explicit, fixed-literal-only fallback rather than trusting
# that invariant silently (D-4: "operators map to fixed
# literals"). M-1: this is a redundant application-level shape
# backstop, not a storage-rejection translation -- so it is
# NOT allowlist-eligible (`layer_rule`'s defence-in-depth
# exemption is for backend/storage denials only); it carries
# the same 4-key vocabulary `Predicate.validate`'s own operator
# check uses (`errors.violation("capability", ...)`), no field-
# index available this deep, so a generic `"where"` path.
```

## CH-0058

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: docstring

```
`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
identical single tx-exit-point discipline to `transact` above --
the exit point sits right before `_bump_revision`/the pre-commit
hook, inside the SAME `with conn.transaction():` block every
operation branch already writes its (uncommitted) DDL/registry
changes in. A `dry_run` forces a real ROLLBACK via `psycopg.
Rollback` (caught and swallowed by `conn.transaction()`'s own
`__exit__`, never surfacing as an error) rather than committing --
`outcome_*` locals below carry the decided result out of that
block, since a raise cannot itself return a value. Always returns
`SchemaOutcome` (review round F-8, `{scratchpad}/rulings-r4.md`;
mirrors `ApplicationCell.apply_schema`'s identical unification) --
this method's own direct callers (`tests/test_constraints_
declaration.py`'s many `cell.apply_schema(...)` call sites among
them) read `.revision` off the result.
```

## CH-0059

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-4, WP-2b): the tx-exit-point's own decided
# outcome, set inside `with conn.transaction():` below (a `dry_
# run`'s own `return` cannot come from inside that block -- normal
# exit COMMITS -- so `psycopg.Rollback` is raised instead, and
# these locals carry the already-decided result past it).
```

## CH-0060

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-5 (8)/(9), addendum 2 S-b, ruling
# I-3, WP-2c): the idempotency lookup -- as early as
# possible after loading the catalog, before ANY
# operation-specific accounting or target-dependent
# computation (including the `schema_objects`
# projection below, which for `drop_entity`/`add_
# field`/etc. reads `catalog.get(bound.entity)`'s
# CURRENT state -- reading it for an entity a replay's
# own key already dropped would compute nonsense, not
# merely skip a check the design allows skipping; see
# `ApplicationCell.apply_schema`'s identical comment).
# `dry_run` never consults/writes a record (ruling
# I-7/D-4).
```

## CH-0061

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling U-7 (WP-6d): see `transact`'s identical
# comment -- taken in THIS outer transaction,
# before `_idempotency_lookup`'s own nested
# savepoint.
```

## CH-0062

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# L-6/M-6: a record with no `request_id` (pre-1.7.0)
# is not a usable replay source -- treated as
# absent, checked before the digest comparison.
```

## CH-0063

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling I-3/I-8/I-9: applies to schema
# operations too -- a resent `drop_entity`
# answers from the record even though the
# entity, and any confirmation phrase computed
# against it, are both long gone.
```

## CH-0064

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# M-6: the ORIGINAL execution's own
# `request_id` (guaranteed present), no
# fallback to this resend's own.
```

## CH-0065

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Ruling I-6/D-5 (5): capacity checked before this
# request executes anything. Ruling U-7: table-
# level count lock, same outer-transaction
# placement as `transact` above.
```

## CH-0066

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a/S-j,
# WP-2b): read ONCE, before any DDL/registry write this
# transaction is about to (tentatively) make -- "the
# revision as it stood when the request was decided"
# (D-4 (7)), the SAME value a dry run's own `revision`
# reports (S-j) and a real apply's `plan` verification
# is checked against. Review round F-5: read only when
# actually needed -- `dry_run` always needs it for
# `outcome_revision` below (S-j), and a caller-
# presented `plan` needs it to verify; an ordinary
# apply (neither) needs neither, and skips this extra
# round trip entirely (`plan_request` is otherwise
# built unconditionally by `service.py`, so gating on
# `plan_request is not None` alone would not have
# helped).
```

## CH-0067

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# WP-2(b) review B-2 (supervisor ruling): defense-
# in-depth -- `bind_schema_operation` above already
# rejects this exact name (structured.py's own
# `_reject_reserved_entity_name`, the real, load-
# bearing check for BOTH cell implementations), but
# this backend's own physical-DDL layer re-checks
# it directly too, mirroring MitateDB's per-backend
# `check_reserved` redundancy rather than relying
# solely on the shared caller never being bypassed.
```

## CH-0068

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): the registry is
# scoped to the entity's own lifetime, symmetric
# with `ApplicationCell.apply_schema`'s identical
# `field_constraints.pop` -- a later `create_
# entity` of the same name must never inherit a
# dropped entity's own constraints. Monitor ruling
# B-3 (rulings-wp2a-review.md): this cleanup runs
# ONLY when the side table itself exists -- an
# application that has never run upgrade `10` has
# no such table at all, and `drop_entity` (an
# operation wholly unrelated to whether that table
# exists) must still succeed for it, exactly like
# every other schema/data operation that never
# touches `field_constraints`.
```

## CH-0069

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling M-6 (rulings-wp2a-review.md,
# contract corrigendum): "An add_field declaring
# nullable: false on an entity that already holds
# rows is refused with CONFLICT on the same rule" --
# the SAME tx + lock `alter_field`'s own existing-
# row scan uses below (M-1/F): `LOCK TABLE ... IN
# SHARE ROW EXCLUSIVE MODE` before the existence
# check, so a concurrent INSERT cannot slip a row
# in between this check and the DDL/registry write
# below.
#
# R-35 (Phase 10, WP-6d-i review): plain `SHARE
# MODE` does not conflict with itself, so two
# concurrent `add_field`/`alter_field` calls on the
# SAME entity could both acquire it, then each
# block at its own later `ALTER TABLE` (ACCESS
# EXCLUSIVE) waiting on the other's SHARE lock --
# a guaranteed mutual wait, broken only by
# PostgreSQL's deadlock detector aborting one side
# with an error instead of the two calls simply
# serializing. `SHARE ROW EXCLUSIVE` conflicts with
# itself, so the second caller instead waits here,
# at LOCK TABLE, and proceeds only once the first
# transaction commits or rolls back -- it still
# excludes concurrent row writers (ROW EXCLUSIVE)
# exactly as plain SHARE did, so the R-2 existing-
# row-scan property above is unchanged.
```

## CH-0070

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling A/B-2 (rulings-wp3a-review.md,
# rulings-wp2a-review.md): compose the request's
# PATCH against the field's EXISTING declared
# constraints -- only known here (`table_info.
# constraints`, never at bind time, addendum R-b/
# R-c, D-2 (3)). `enum`/`nullable` omitted each
# LEAVE the existing value as it is; `enum: null`
# CLEARS it; an explicit list is fully validated
# against the field's real declared type now.
```

## CH-0071

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Monitor ruling F/M-1 (rulings-wp3a-review.md,
# rulings-wp2a-review.md): lock the entity's own
# table (SHARE ROW EXCLUSIVE -- blocks concurrent
# writers, never concurrent readers) BEFORE the
# scan below, inside this SAME transaction. Without
# this, READ COMMITTED lets another session
# INSERT/UPDATE a row that violates the new
# constraints, commit it AFTER this scan sees zero
# violations but BEFORE this transaction's own
# `_write_field_constraints` commits -- `alter_
# field` would then succeed while a violating row
# already exists, making the catalog's own
# declaration false (G-3) the instant it is
# published. A table-level lock (not a row lock)
# because the scan below reads the WHOLE table, not
# a single identified row (contrast the upsert
# TOCTOU fix below, M-2, which locks one row).
#
# R-35 (Phase 10, WP-6d-i review): the original fix
# used plain `SHARE MODE`, which does not conflict
# with itself -- two concurrent `alter_field`/`add_
# field` calls on the SAME entity could both
# acquire it here, then each block at its own later
# `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on the
# other's SHARE lock, a guaranteed mutual wait
# broken only by PostgreSQL's deadlock detector
# aborting one side with an error rather than the
# two calls simply serializing. `SHARE ROW
# EXCLUSIVE` conflicts with itself, so the second
# caller instead waits here, at LOCK TABLE, and
# proceeds only once the first transaction commits
# or rolls back -- it still excludes concurrent row
# writers (ROW EXCLUSIVE) exactly as plain SHARE
# did, so the R-2 existing-row-scan property above
# is unchanged.
```

## CH-0072

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# R-5, corrigendum M-6: dropping a unique index
# removes a guardrail and can silently re-enable
# upsert -- SI-09 destructive confirmation applies
# exactly like drop_entity.
```

## CH-0073

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# D-4 (3): `descriptor` is the target entity's own
# descriptor as it would read afterwards -- built
# from a FRESH `_load_catalog` re-read inside this
# SAME (still open, uncommitted) transaction, which
# sees this operation's own tentative writes;
# `None` for a dry-run `drop_entity` (the entity no
# longer appears in that re-read). `revision`
# (S-j) is `revision_before`, never a bumped value
# -- `_bump_revision` below is never reached here.
```

## CH-0074

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# R-5: `create_index(unique=True)` against data that
# already violates the requested uniqueness.
```

## CH-0075

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `944e86b`
- kind: comment

```
# Review round F-8: always `SchemaOutcome`, dry_run/plan or
# neither (mirrors `ApplicationCell.apply_schema`'s identical
# unification) -- every pre-1.7.0 direct caller of this method
# (`tests/test_constraints_declaration.py`'s many `cell.
# apply_schema(...)` call sites among them) now reads `.revision`
# off the result instead of comparing the result itself to an
# `int`.
```

## CH-0076

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._create_entity`)
- parent commit: `944e86b`
- kind: comment

```
# R-1/R-4: every entity table gets a server-assigned `id` address
# (`GENERATED ALWAYS AS IDENTITY`, so the sequence is never
# rewound by any statement reachable through this public API -- see
# R-1's "採番識別子の非推論条項"/property-5 note) and an invisible,
# per-row `_r2db_revision` (PostgreSQL 13+'s built-in
# `gen_random_uuid()`), ahead of the caller's own declared fields.
# `"id"`/`"_r2db_revision"` are hardcoded server literals here,
# never client input, so composing them as fixed SQL text (rather
# than through `sql.Identifier`) does not reopen the
# identifier-injection surface D-4 closes for client-supplied names.
#
# Phase 6 WP-2 (design D-3, r2db decision (c)): a field named in
# `field_types` gets that declared type's real PostgreSQL column
# type (the same `_FIELD_TYPE_SQL` mapping `_add_field` below
# already uses); every other field keeps the pre-WP-2 default,
# JSONB (`field_types` defaults to `None`/empty, so an ordinary
# 1.5.0-shaped `create_entity` -- `fields` only, no `field_types` --
# creates every column JSONB, unchanged).
```

## CH-0077

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_row_level_security`)
- parent commit: `944e86b`
- kind: docstring

```
D-3's third layer: RLS as defence-in-depth underneath the
database boundary and the two distinct DB roles (architecture §8,
"D-3 改訂": each application now owns its own PostgreSQL database,
not merely its own schema inside one shared database -- the
database boundary is the primary wall, since PostgreSQL admits no
cross-database query path at all without FDW/dblink, which this
deployment never grants). This policy's job is to survive a
*future* misconfiguration of that primary wall -- e.g. an
accidental broader `CONNECT` grant -- rather than to be the
primary control itself. It restricts every row in every table this
cell creates to being visible/writable only by this application's
own two roles, checked by PostgreSQL itself via `current_user`, not
by anything this Python process asserts about itself.
```

## CH-0078

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._add_field`)
- parent commit: `944e86b`
- kind: comment

```
# R-2: `field_type` maps to a real typed column; omitted keeps the
# pre-CCR-13 default, JSONB.
```

## CH-0079

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._create_index`)
- parent commit: `944e86b`
- kind: comment

```
# R-5: the physical index name is `{entity}__{index}` -- `bind_
# schema_operation` has already rejected any client index name
# containing `__` or whose composed length would exceed the
# identifier limit, so this composition is unambiguous to invert
# (`_load_catalog` does exactly that). `entity`/`index_name` are
# plain Python strings built from already-validated identifiers;
# `sql.Identifier` below is what actually makes this safe to send
# to PostgreSQL (it quotes/escapes the resulting name regardless of
# content), not the string concatenation itself.
```

## CH-0080

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._read_schema_revision`)
- parent commit: `944e86b`
- kind: docstring

```
Read-only counterpart to `_bump_revision` below (design docs/
design/DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1, WP-0 m-1): a plain
`SELECT` of the current `schema_revision`, in the SAME transaction
as the pending schema operation, used to compute a `drop_entity`/
`drop_index` confirmation phrase's own state fingerprint before the
destructive-confirmation gate runs (and therefore before this same
transaction's own `_bump_revision` call increments it again).
`migrations/0003_provision_application.sql` inserts this table's one
row (`revision = 0`) at provisioning time, so the `SELECT` always
finds it in practice; the `0` fallback below exists only so this
method never raises on a row that -- against that expectation --
turns out to be missing, mirroring `_bump_revision`'s own
insert-if-missing defensiveness without itself writing anything.
```

## CH-0081

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._set_timeouts`)
- parent commit: `944e86b`
- kind: docstring

```
One request = one transaction (D-5): `statement_timeout` and
`lock_timeout` are set with `SET LOCAL`, so they apply only to the
current transaction and are automatically discarded on commit or
rollback -- never leaking onto the next transaction this pooled
connection is reused for. The timeout value passed here is always a
server-computed `int` (derived from `ResourceLimits.execution_ms`
and the caller's deadline, never from request content), so
`sql.Literal` -- necessary because PostgreSQL's `SET` grammar does
not accept a bind placeholder in this position -- is composing a
trusted value, not interpolating untrusted text.
```

## CH-0082

- moved from: `src/r2db_api/postgres.py` (`_RefusingPlatformUpgradeCell`)
- parent commit: `944e86b`
- kind: docstring

```
Q4 rework (supervisor ruling 2026-09-05, H-1(a)): stands in for one
served application's own `PostgresCell` when `main.py::build_app`'s
own `_cell_factory` finds, at cell-open time, that this application's
per-application platform-upgrade ledger is missing an entry
`platform_upgrades.PLATFORM_UPGRADE_NUMBERS` requires.

Before this rework, `_cell_factory` called `PostgresCell.verify_
platform_upgrades_applied()` and let the `SERVICE_UNAVAILABLE`
`FoundationError` it raises propagate straight out of `_cell_
factory`, out of `ControlAuthority.register_application`, out of
`build_app`'s own eager `for slug in slugs` registration loop -- so
ONE served application with a pending upgrade took the WHOLE PROCESS
down, refusing every OTHER served application too (review H-1).

Now `_cell_factory` catches that same `FoundationError` and registers
one of these instead: this process still starts, every OTHER served
application's `PostgresCell` opens and serves exactly as before, and
ONLY this one application's cell -- carrying the identical
`StorageBackend` face (`query`/`transact`/`apply_schema`/`catalog`,
`r2db_api.backend.StorageBackend`, asserted below exactly like
`PostgresCell` itself is) -- refuses every real request against it
with the SAME F-12 message (design §3.8, verbatim, `SERVICE_
UNAVAILABLE`, HTTP 503) `verify_platform_upgrades_applied` would have
raised. The message is captured once, at cell-open time (a startup
snapshot, matching D-1(e)/D-2(g)/U-3's own "起動時スナップショット"
discipline for every other Q4 declared value) -- never re-derived per
request.
```

## CH-0083

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# Checked, not just claimed: `PostgresCell` must present the exact same call
# surface as `ApplicationCell` (design D-1). See `backend.py` for the
# equivalent assertion covering `ApplicationCell`.
```

## CH-0084

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `944e86b`
- kind: comment

```
# H-1(a): the refusing cell registered in its place must present that same
# face too -- `DataService` (and every conformance/test caller) cannot tell
# the two apart at the type level.
```

## CH-0085

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._idempotency_reserve`)
- parent commit: `944e86b`
- kind: comment

```
# Phase 10 WP-6a (design docs/design/
# PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-5(ii) region
# (iii)): `idempotency_entries` stays a declared DB-side
# `enforced` class (region (iii)) via this count-then-
# check, but the same-key serialization AND the count
# lock that would close this count's TOCTOU window are
# WP-6d-i's scope (both peers, one pass) -- not added
# here. See supervisory ruling 2026-09-08.
```

## CH-0087

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2, error-row rule): see `transact`'s
# identical comment.
```

## CH-0088

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2, item 2): unconditional -- every
# schema operation is fail-closed class. Last statement
# inside this `with conn.transaction():` block, same
# reasoning as `transact`'s identical comment.
```

## CH-0089

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-2 (6)): every existing row is
# checked against the constraints this operation
# would establish, INSIDE this same `with conn.
# transaction():` block, before anything commits --
# one violating row refuses the WHOLE operation
# with CONFLICT via `fail()`, which unwinds this
# entire transaction (nothing has been written yet
# at this point, so there is nothing to roll back
# beyond PostgreSQL's own transactional DDL/DML).
# Two separate, targeted queries (never a combined
# OR) so the CONFLICT can name exactly which
# declaration a violating row breaks, without ever
# naming the row itself or how many there are
# (SI-10, contract text).
```

## CH-0090

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.apply_schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2/D-10): see `transact`'s identical `hook_fired`
# comment -- `True` only once the durable pre-commit row has
# already committed on its own connection, which is what lets the
# `except psycopg.Error` clause below tell a post-hook data-commit
# failure apart from every other failure.
```

## CH-0091

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply_upsert`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): this entity's own declared
# constraints, same source `_apply` above reads.
```

## CH-0092

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply`)
- parent commit: `3a4c018`
- kind: comment

```
# Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): every
# `details.field` this method raises for a VALUE-position defect
# in `bound.values` names the request-internal PATH to that value.
```

## CH-0093

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._apply`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): this entity's own declared
# constraints, already read by `_load_catalog` into `table_info`
# (addendum 2 S-k's 6 write call sites all pass this through to
# `_check_type`; the 2 predicate call sites never do).
```

## CH-0094

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2, error-row rule): `hook_fired` is only
# `True` once the durable pre-commit row has already
# committed on its own (separate) connection -- so an
# exception reaching here after that point can only be this
# method's own data commit failing. Record the durable
# `outcome="error"` row for the same `request_id` (still
# fail-closed: this call may itself raise `FoundationError`
# SERVICE_UNAVAILABLE, which is exactly what happens next
# regardless of whether it does).
```

## CH-0095

- moved from: `src/r2db_api/postgres.py` (`PostgresCell.transact`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2/D-10): whether this batch passed through the
# DESTRUCTIVE_CONFIRMATION_V1 choke -- see `ApplicationCell.
# transact`'s identical comment (D-10 parity).
```

## CH-0096

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._write_field_constraints`)
- parent commit: `3a4c018`
- kind: docstring

```
Contract 1.7.0 (D-2 (4), WP-2a): persists (or clears) one
field's own row in the side-table registry -- the ONLY write path
into it, called from `apply_schema`'s `create_entity`/`add_field`/
`alter_field` branches, always inside that method's own outer `with
conn.transaction():` (never a separate commit). A field whose
constraints are no longer declared at all (`not constraints.is_
declared` -- `alter_field` clearing back to the version-wide
default) has its row DELETEd rather than left standing; `create_
entity`/`add_field` only ever call this for a field the request
gave an actual spec (never for the fully-default case, so a plain
`create_entity`/`add_field` that never mentions `field_constraints`
/`enum`/`nullable` never touches this table at all).
```

## CH-0097

- moved from: `src/r2db_api/postgres.py` (`PostgresCell._describe_table`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-2 (1), WP-2a): total over `table_info.
# columns` (like `field_types` below) -- `nullable` always
# present, `enum` only for a field the registry (`table_info.
# constraints`, read by `_load_catalog`'s own `_load_field_
# constraints`) actually carries a declaration for.
```

## CH-0098

- moved from: `src/r2db_api/postgres.py` (`PostgresCell`)
- parent commit: `3a4c018`
- kind: docstring

```
A `StorageBackend` over one application's own PostgreSQL database
(architecture §8, "D-3 改訂": database-per-application, not
schema-per-application -- each application's entities live in that
database's `public` schema; `schema` below is `"public"` for every
application, and the isolation boundary is which *database* a
connection's DSN names, not a schema name inside a shared one).

`application_id` and `schema` are supplied by the caller (the control
plane), never derived from client request content (D-3: "the physical
namespace is assigned by the control plane, not derived from client
input" -- true of both the database name and the schema name within
it). `runtime_dsn`/`developer_dsn` are two separate, already
fully-formed connection strings authenticating as this application's
`runtime` and `developer` PostgreSQL roles respectively, each already
naming this application's own database (provisioned by
`r2db-api/migrations/`, see `r2db-api/docs/`); this class never embeds a
control-plane credential and never widens a connection's role at
runtime, so schema-changing operations physically execute under the
`developer` role (DDL-capable on this database's `public` schema only)
while queries and data mutations physically execute under the `runtime`
role (DML only) -- a second, DB-enforced layer under the `developer:
bool` check already performed by `bind_schema_operation` (SI-03
defence in depth).

Connection pooling (D-3/§10.1, and the fix this class's `_runtime`/
`_developer` attributes are part of): each is a `_PoolHandle` onto a
pool owned by `pool_manager` -- `default_pool_manager` (module-level, a
single process-wide `SharedPoolManager`) unless a caller supplies its
own, e.g. a test that wants an isolated cache with a short idle
interval. No pool is created here at construction time; `PostgresCell`
itself now holds nothing heavier than DSNs and a pool-cache key
(`application_id`, role) until something actually calls `.connection()`.
Because the cache is shared across every `PostgresCell` instance rather
than private to each one, the number of live pools is bounded by
`pool_manager`'s own cap regardless of how many applications exist --
see `SharedPoolManager`'s docstring and `r2db-api/docs/
POSTGRES_PROVISIONING_RUNBOOK.md` §4 for the resulting arithmetic.
`pool_size`, same as before, is this cell's own requested per-pool
connection cap (`None` defers to `pool_manager`'s configured default,
itself `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW` unless overridden) --
it is only consulted the moment a pool is actually (re)created for this
cell's key, exactly like every other pool setting here.
```

## CH-0099

- moved from: `src/r2db_api/postgres.py` (`SharedPoolManager`)
- parent commit: `3a4c018`
- kind: docstring

```
The fix for this module's connection-pooling defect: a single,
process-wide cache of `_RolePool` instances keyed by `(application_id,
role)`, shared across every `PostgresCell` -- not one pair of pools per
cell, held forever, as before.

Design, adapted from the currently deployed reference implementation
(`r2-vps/apps/r2db-api/src/r2db_api/pools.py::AppPoolManager`, a
SQLAlchemy engine cache with the same two properties) to this package's
hand-rolled psycopg pooling:

- **Idle eviction.** A pool unused for `R2DB_POOL_IDLE_SECONDS` (default
  300) is retired the next time *any* key is looked up here -- eviction
  is swept lazily, on access, exactly like the reference implementation,
  not on a background timer.
- **An LRU cap on live pools (`R2DB_POOL_CACHE_MAX`, default 32).** This
  is the property that actually decouples the connection ceiling from
  the number of applications: `PostgresCell.__init__` no longer creates
  a pool eagerly at all, it only registers a `(dsn, schema, maxconn)`
  recipe with this manager and asks for the live pool by key on every
  use (`_PoolHandle`, below). However many applications exist, at most
  `cache_max` *pools* are ever open at once, each capped at
  `maxconn` connections (default `R2DB_POOL_SIZE + R2DB_POOL_MAX_
  OVERFLOW` = 2 + 2 = 4, matching the reference implementation's
  effective per-application capacity) -- an absolute ceiling of
  `cache_max * maxconn` connections cluster-wide (default 32 * 4 = 128,
  itself still an operator-facing figure to size against `max_
  connections`, but no longer one that grows with application count).

Eviction never closes a connection a caller currently has checked out
-- see `_RolePool.retire()`. It closes idle connections in the pool's
queue immediately and lets any in-flight one finish and be closed on
return.

A default instance (`default_pool_manager`, below) is what `PostgresCell`
uses when no `pool_manager` is supplied, so this behaves as a drop-in
fix with no caller changes required. Tests (and any caller that wants
isolated pool-cache behaviour, e.g. a short idle interval to make
eviction observable) construct their own `SharedPoolManager` and pass it
to `PostgresCell(..., pool_manager=...)` explicitly.
```

## CH-0100

- moved from: `src/r2db_api/postgres.py` (`_env_int`)
- parent commit: `3a4c018`
- kind: docstring

```
Read an `int`-valued setting the way the rest of this package does
(`R2DB_`-prefixed environment variables, e.g. `R2DB_CREDENTIAL_PEPPER`
in `auth.py`) -- a bare `os.environ.get` rather than a `pydantic`
settings object, since this package (unlike the SQLAlchemy-based
reference implementation this design is adapted from) has no
`Settings`/`get_settings()` of its own. An unset, empty, or unparsable
value silently falls back to `default` rather than raising: these are
pool-tuning knobs, not required configuration, and a malformed value at
startup should degrade to a sane default, not crash the process.
```

## CH-0101

- moved from: `src/r2db_api/postgres.py` (`_TableInfo`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-2 (4), WP-2a): this entity's own declared `enum`/
# `nullable` constraints, read from the side-table registry (`_load_
# field_constraints` below) -- field name -> `FieldConstraints`,
# present ONLY for a field something was actually declared on
# (`FieldConstraints.is_declared`), same "absence = default" convention
# `columns`/`indexes` above never needed (there is no "undeclared
# column"). Defaults to `{}` so every EXISTING call site that builds a
# `_TableInfo` without constraints in mind (there are none left after
# this WP, but a future one) keeps working.
```

## CH-0102

- moved from: `src/r2db_api/postgres.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
#: Contract 1.7.0 (D-5 (6), U-3 = (A), WP-2c): the per-application
#: idempotency-record side table -- a FOURTH backend bookkeeping table,
#: excluded from the application-visible catalog/RLS-coverage check the
#: same way the other three are (migration `0011_idempotency_records_
#: upgrade.sql`).
```

## CH-0181

- moved from: `src/r2db_api/postgres.py` (`_RolePool._acquire`)
- parent commit: `3a4c018`
- kind: comment

```
# Reserve a slot (increment `_created`) and release the lock
# *before* calling `_connect()` -- a real, previously-shipped bug
# this class had: `_connect()` used to run while `self._lock` was
# held, so every thread contending for a new connection against an
# unreachable target serialized on this lock for the full connect
# attempt, and a failed `_connect()` never rolled its reservation
# back. `maxconn` consecutive failures against an unreachable
# target therefore permanently pinned `_created` at `maxconn`, so
# every later `_acquire()` call fell straight through to the
# untimed `self._queue.get()` below and blocked forever -- even
# once the target became reachable again, since nothing ever put a
# connection back on this empty queue. `r2db_api/tests/
# test_postgres.py::test_role_pool_recovers_after_connect_failures_
# are_exhausted_and_target_becomes_reachable` and
# `test_credential_persistence.py::
# test_authenticate_never_hangs_across_repeated_pool_exhaustion_and_
# recovers_once_reachable` are the executable checks for this fix.
```
