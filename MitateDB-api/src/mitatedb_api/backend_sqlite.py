"""SQLite storage backend (R-3 seam execution side).

This is the extracted, backend-specific half of what used to be
``cell.ApplicationCell`` before the WP-1 seam refactor: nothing here
validates a request's SHAPE or a principal's AUTHORITY any more (that
stayed in ``cell.py``, unchanged) -- this module only ever turns an
already-validated request into SQLite statements against one private,
in-memory (``:memory:``) connection.

Kept as "a deterministic local foundation backend" only (`architecture/
DATA_SERVICE_FOUNDATION.md`) -- never the production persistence topology
(that is ``backend_postgres.PostgresBackend``).
"""

import sqlite3
import time

from .backend import SQL_OPERATOR_TOKENS, UNCHANGED
from .errors import ConflictError, NotFoundError, ResourceLimitError, ValidationError
from .field_types import FOUNDATION_TYPE_TO_CONTRACT_TYPE
from .identifiers import quote_identifier, validate_identifier


def _check_deadline(deadline):
    """Phase 8 WP-1a (design D-1 "実装の形" 5: "変更はapp側deadline検査の
    呼び出しのみ"): this backend has no native query-timeout API
    (`sqlite3` offers none) -- unlike `backend_postgres.py`'s own real
    `SET LOCAL statement_timeout`/`lock_timeout`, this is the app-side
    wall-clock check `cell.ApplicationCell._limit_gate`'s own computed
    `deadline` (`time.monotonic()` seconds) is handed to. `deadline=None`
    (a direct caller of this backend that supplies no deadline -- this
    repository's own tests) skips the check entirely, mirroring `backend_
    postgres.py`'s identical `None`-means-unbounded convention."""
    if deadline is not None and time.monotonic() > deadline:
        raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")

# R-3 (design v1.1, WP-0 m-7): this set is backend-specific, unlike the
# shared syntax allowlist in identifiers.py. `sqlite_sequence` is a real
# SQLite-internal table name (created automatically by an AUTOINCREMENT
# column); `audit_events` is reserved defensively against a future local
# audit-table name collision on this backend specifically.
_RESERVED = frozenset({"sqlite_sequence", "audit_events"})

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
_SQLITE_INT64_MIN = -9223372036854775808
_SQLITE_INT64_MAX = 9223372036854775807

# Foundation field-type vocabulary (`cell._FIELD_TYPE_VOCABULARY`) -> this
# backend's own native column type. `boolean` maps to `INTEGER` (SQLite's
# own dynamic typing has no dedicated boolean storage class); `json` maps
# to `TEXT` (values are stored as the seam's own canonical JSON text, see
# `cell.ApplicationCell._normalize_value`).
_TYPES = {"text": "TEXT", "integer": "INTEGER", "real": "REAL",
          "boolean": "INTEGER", "json": "TEXT"}

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
_DIRECTION_TOKENS = {"asc": "ASC", "desc": "DESC"}


class SQLiteBackend:
    """One private ``:memory:`` connection per application cell."""

    def __init__(self):
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # In-memory only, matching this backend's own already-non-durable
        # storage (the whole database disappears on process restart) --
        # unlike `backend_postgres.PostgresBackend`, whose schema revision
        # is persisted in the database itself precisely because PostgreSQL
        # storage IS durable across restarts (see that module's own
        # comment).
        self._schema_revision = 0
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
        self._declared_types = {}
        # Phase 9 WP-3a (design docs/design/
        # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (4)):
        # "SQLite backend は `_declared_types` と同じプロセス内構造に制約
        # を持つ" -- `{collection: {field: {"nullable": bool, "enum":
        # [...]}}}`, the SAME lazily-created, in-memory-only shape as
        # `_declared_types` immediately above (no upgrade script: this
        # backend is the `:memory:` process-local one, F-6). `"enum"` is
        # present only on a field that declares one; `"nullable"` is
        # always present (default `True`, the contract default, D-2 (2)).
        self._declared_constraints = {}

    @property
    def raw_connection(self):
        """Back-compat surface for `conformance/conformance_adapter_
        mitatedb.py::entities()`'s own direct `cell._db.execute(...)`
        reach-around (pre-existing, predates this WP's seam refactor) --
        `cell.ApplicationCell.__init__` republishes this as `self._db` when
        constructed with this backend, so that file needs no change."""
        return self._db

    def check_reserved(self, value, label):
        if value in _RESERVED:
            raise ValidationError("reserved " + label)

    def schema_count(self):
        row = self._db.execute(
            "SELECT count(*) AS count FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return row["count"]

    def schema_revision(self):
        return self._schema_revision

    def field_domains(self, collection):
        # B-1 (independent review round 2): SQLite's own column affinity
        # is dynamic (no equivalent to PostgreSQL's own type-mismatch
        # failure mode this backend's domain concept exists to catch), so
        # every field maps to domain `None` -- `ApplicationCell.
        # encode_value` calls skip domain validation entirely for `None`,
        # matching this backend's own pre-existing, unchanged external
        # behavior (WP-1 P3 round 2 instruction #1: "SQLite側の外部挙動は
        # 不変に保つこと").
        name = validate_identifier(collection, "collection")
        try:
            rows = self._db.execute("PRAGMA table_info(" + quote_identifier(name) + ")").fetchall()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        if not rows:
            raise NotFoundError("collection not found")
        return {row["name"]: None for row in rows}

    def _begin_pseudo_tx(self) -> None:
        """Phase 4 (design D-2/D-10, "擬似 tx"): SQLite's own `sqlite3`
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
        identical guard."""
        if self._db.in_transaction:
            self._db.rollback()
        self._db.execute("BEGIN")

    def create_collection(self, name, fields, *, field_types=None, field_constraints=None, audit_hook=None, deadline=None):
        _check_deadline(deadline)
        definitions = []
        for field, field_type in fields.items():
            definitions.append(quote_identifier(field) + " " + _TYPES[field_type])
        statement = "CREATE TABLE " + quote_identifier(name) + " (" + \
            ", ".join(definitions) + ")"
        self._begin_pseudo_tx()
        try:
            self._db.execute(statement)
        except sqlite3.DatabaseError:
            self._db.rollback()
            raise ConflictError("collection already exists")
        # Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
        # D-2/D-10): `audit_hook.pre_commit()` runs as the LAST thing
        # before this backend's own commit -- mirrored, "pseudo-tx"
        # parity counterpart to `backend_postgres.PostgresBackend`'s real
        # commit-inside-try structure (D-10's own parity-test target),
        # made real by `_begin_pseudo_tx` above (see that method's own
        # comment for why a bare `commit()`/`rollback()` alone is not
        # enough for DDL on this backend). This connection's `commit()`
        # realistically never fails once the statement above already
        # succeeded -- so there is no `commit_failed()` counterpart call
        # anywhere in this file, mirroring r2db-api's own in-memory
        # `ApplicationCell.transact`'s identical, documented absence of
        # one. A raise from `pre_commit()` itself (an `AuditSinkUnavailable`,
        # never a `sqlite3.Error`) is caught by the bare `except Exception`
        # below, which rolls back the still-uncommitted DDL before
        # propagating.
        try:
            if audit_hook is not None:
                audit_hook.pre_commit()
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._schema_revision += 1
        # Phase 6 WP-3 (design D-3): registry write lands only on this
        # success path -- an exception above already `raise`d, so a
        # rolled-back DDL never leaves a stray registry entry behind.
        # Robust to a direct caller (bypassing `cell.py`) supplying no
        # `field_types` at all, or only a partial one -- the SAME
        # backfill-rule fallback `cell.ApplicationCell.create_collection`
        # itself applies for every uncovered name.
        resolved = dict(field_types or {})
        for field, physical_type in fields.items():
            resolved.setdefault(field, FOUNDATION_TYPE_TO_CONTRACT_TYPE[physical_type])
        self._declared_types[name] = resolved
        # Phase 9 WP-3a (design D-2 (1)/(4)): registry write lands only on
        # this same success path -- total over `fields`, `field_constraints`
        # partial input backfilled to `{"nullable": True}` for any name it
        # omits (contract `SchemaOperationRequest.field_constraints.
        # description`: "any name in fields it omits is created with no
        # enum and nullable: true").
        resolved_constraints = {}
        for field in fields:
            declared = dict((field_constraints or {}).get(field) or {})
            declared.setdefault("nullable", True)
            resolved_constraints[field] = declared
        self._declared_constraints[name] = resolved_constraints

    def add_field(self, collection, field, field_type, *, contract_type=None, enum=None, nullable=None, audit_hook=None, deadline=None):
        _check_deadline(deadline)
        resolved_nullable = True if nullable is None else nullable
        if resolved_nullable is False:
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
            try:
                (existing_rows,) = self._db.execute(
                    "SELECT count(*) FROM " + quote_identifier(collection)
                ).fetchone()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
            if existing_rows > 0:
                raise ConflictError(
                    "add_field declaring nullable: false on an entity that already holds rows "
                    "would leave every existing row holding null in the new field",
                    details={"violated_declaration": "nullable", "field": "nullable"},
                )
        table = quote_identifier(collection)
        statement = "ALTER TABLE " + table + " ADD COLUMN " + \
            quote_identifier(field) + " " + _TYPES[field_type]
        self._begin_pseudo_tx()
        try:
            self._db.execute(statement)
        except sqlite3.OperationalError as exc:
            self._db.rollback()
            # sqlite3 reports both "no such table" and "duplicate column
            # name" as OperationalError with no separate exception class
            # to distinguish them by type -- the caller (`cell.py`) has
            # already confirmed the collection exists via `field_domains`
            # immediately before calling this, so by the time control
            # reaches here the only way ALTER TABLE can still fail is a
            # duplicate column name.
            raise ConflictError("field already exists") from exc
        except sqlite3.DatabaseError:
            self._db.rollback()
            raise NotFoundError("collection not found")
        # Phase 4: same pre-commit-hook structure as `create_collection`
        # above -- see that method's own comment.
        try:
            if audit_hook is not None:
                audit_hook.pre_commit()
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._schema_revision += 1
        if contract_type is None:
            contract_type = FOUNDATION_TYPE_TO_CONTRACT_TYPE[field_type]
        self._declared_types.setdefault(collection, {})[field] = contract_type
        # Phase 9 WP-3a (design D-2 (1)/(4)): same success-path-only
        # registry write as `create_collection` above, for this one new
        # field -- `nullable=None` (no explicit declaration) resolves to
        # the contract default `True`.
        declared = {"nullable": resolved_nullable}
        if enum is not None:
            declared["enum"] = list(enum)
        self._declared_constraints.setdefault(collection, {})[field] = declared
        # WP-3a rework 3 (real, measured bug -- SchemaOperationResult.
        # revision is `required` unconditionally, `contract/data-service-
        # api.v1.json`'s own `schemas.SchemaOperationResult.required`;
        # `alter_field_constraints` below already returns the bumped
        # revision, but this method used to return nothing at all, so the
        # in-process caller's own successful `add_field` result could
        # never report one -- see `cell.ApplicationCell.add_field`'s own
        # comment at its call site for the full chain this closes).
        return self._schema_revision

    def field_types(self, collection):
        """Phase 6 WP-3 (design D-3): see `backend.StorageBackend.
        field_types`'s own contract. `field_domains` is called only for
        its existence check -- its own return value (all-`None` domains,
        this backend's own unchanged behaviour) is discarded here."""
        self.field_domains(collection)  # NotFoundError if `collection` does not exist
        return dict(self._declared_types.get(collection, {}))

    def all_field_types(self):
        """Phase 6 WP-3 (design D-3): `{collection: {field: contract_
        type}}` for EVERY collection this backend currently has -- `GET
        /v1/catalog`'s own sole data source (`http.py::get_catalog`).
        Never includes a collection with no registry entries (cannot
        occur for one this backend's own `create_collection` created --
        every field always gets a registry row, `create_collection`'s own
        docstring)."""
        return {name: dict(types) for name, types in self._declared_types.items()}

    def field_constraints(self, collection):
        """Phase 9 WP-3a (design D-2 (1)/(4)): see `backend.
        StorageBackend.field_constraints`'s own contract. `field_domains`
        is called only for its existence check, matching `field_types`
        above."""
        self.field_domains(collection)  # NotFoundError if `collection` does not exist
        return {field: dict(value) for field, value in self._declared_constraints.get(collection, {}).items()}

    def field_types_and_constraints(self, collection):
        """Phase 9 WP-3a rework (code review §2 C, P-8/G-4): see
        `backend.StorageBackend.field_types_and_constraints`'s own
        contract. This backend has no round trip to cut -- `_declared_
        types`/`_declared_constraints` are already two plain in-process
        dicts -- so this exists purely to give `cell.py` the SAME method
        name on both backends; `field_domains` is still called only once
        here (not twice, as calling `field_types`+`field_constraints`
        separately would)."""
        self.field_domains(collection)  # NotFoundError if `collection` does not exist
        return (
            dict(self._declared_types.get(collection, {})),
            {field: dict(value) for field, value in self._declared_constraints.get(collection, {}).items()},
        )

    def all_field_constraints(self):
        """Phase 9 WP-3a (design D-2 (1)/(4)): `{collection: {field:
        {"nullable": bool, "enum": [...]}}}` for EVERY collection this
        backend currently has -- `GET /v1/catalog`'s own sole data
        source for `field_constraints`, matching `all_field_types`
        above."""
        return {
            name: {field: dict(value) for field, value in constraints.items()}
            for name, constraints in self._declared_constraints.items()
        }

    def alter_field_constraints(self, collection, field, *, enum=UNCHANGED, nullable=None, audit_hook=None, deadline=None):
        """Phase 9 WP-3a (design D-2 (5)/(6), 実装の形 4, 監督裁定 S-g):
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
        backend."""
        _check_deadline(deadline)
        if field not in self.field_domains(collection):  # NotFoundError if `collection` does not exist
            raise NotFoundError("field not found")
        current = dict(self._declared_constraints.get(collection, {}).get(field) or {"nullable": True})
        new_nullable = current.get("nullable", True) if nullable is None else nullable
        new_constraints = {"nullable": new_nullable}
        # Code review §2 A / 監督裁定 A (2026-09-07): tri-state `enum` --
        # `UNCHANGED` (default) keeps whatever this field's current
        # registry entry already carries; an explicit `None` clears it
        # (no "enum" key at all in `new_constraints`); any other value
        # (already a validated, non-empty list, `cell.py::alter_field`'s
        # own job) sets/replaces it.
        if enum is UNCHANGED:
            if "enum" in current:
                new_constraints["enum"] = list(current["enum"])
        elif enum is not None:
            new_constraints["enum"] = list(enum)
        declared_type = self._declared_types.get(collection, {}).get(field)
        self._begin_pseudo_tx()
        try:
            rows = self._db.execute(
                "SELECT " + quote_identifier(field) + " FROM " + quote_identifier(collection)
            ).fetchall()
        except sqlite3.DatabaseError:
            self._db.rollback()
            raise NotFoundError("collection not found")
        violation = None
        allowed_enum = new_constraints.get("enum")
        for row in rows:
            value = row[0]
            if value is None:
                if new_nullable is False:
                    violation = "nullable"
                    break
                continue
            if allowed_enum is not None:
                # `enum` can only ever be declared on a `string`/
                # `integer`/`number`/`boolean` field (`field_types.
                # validate_enum_declaration` refuses it on `object`/
                # `array`/`json` before it ever reaches a registry) --
                # this backend stores a declared-`boolean` value as a
                # native SQLite `0`/`1` integer, so it alone needs
                # decoding back before an `enum` (of real Python `bool`
                # members) can compare against it.
                decoded = bool(value) if declared_type == "boolean" else value
                if decoded not in allowed_enum:
                    violation = "enum"
                    break
        if violation is not None:
            self._db.rollback()
            # Code review §2 D / 監督裁定 D (2026-09-07): `field` names a
            # POSITION IN THE REQUEST (design D-3 (2)), not the entity
            # field name -- `alter_field`'s own request carries `enum`/
            # `nullable` as its OWN top-level keys (`{"collection": ...,
            # "field": <entity field name>, "enum": [...], "nullable":
            # ...}`), so the position a violated `enum`/`nullable`
            # declaration is attributable to IS that same top-level key
            # name -- the same value as `violated_declaration` itself.
            raise ConflictError(
                "existing rows violate the constraints this alter_field would establish",
                details={"field": violation, "violated_declaration": violation},
            )
        self._declared_constraints.setdefault(collection, {})[field] = new_constraints
        self._schema_revision += 1
        try:
            if audit_hook is not None:
                audit_hook.pre_commit()
            self._db.commit()
        except Exception:
            self._db.rollback()
            # Undo the in-memory registry/revision mutation above -- this
            # backend's own registries are plain Python dicts/ints, not
            # transactional storage, so a rollback of the SQL side alone
            # would otherwise leave them out of step with the database.
            self._declared_constraints[collection][field] = current
            self._schema_revision -= 1
            raise
        return self._schema_revision

    def encode_value(self, value, domain=None):
        # `domain` is accepted only to match the shared `StorageBackend`
        # call shape (`cell.py` always passes it) and is otherwise IGNORED
        # -- see `field_domains`'s own comment above for why (this
        # backend's own value acceptance is unchanged by B-1's own domain
        # concept: SQLite's dynamic column affinity has no equivalent
        # mismatch to detect).
        #
        # SQLite's own driver: an explicit `int(bool)` conversion (rather
        # than relying on `bool` being an `int` subclass the driver might
        # adapt implicitly) -- unchanged from this backend's pre-seam
        # behavior.
        if isinstance(value, bool):
            value = int(value)
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
        if isinstance(value, int) and not (_SQLITE_INT64_MIN <= value <= _SQLITE_INT64_MAX):
            raise ValidationError("value is out of range for 64-bit integer storage")
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
        # rejection `backend_postgres.py::_validate_value_domain` now
        # applies. Only a plain `str` can carry one through to this point
        # (a dict/list value already became NUL/surrogate-escaped JSON
        # text via `json.dumps` in `cell.ApplicationCell._normalize_
        # value`, before this method is ever called).
        if isinstance(value, str) and any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise ValidationError(
                "value contains a lone UTF-16 surrogate code point, which cannot be encoded as UTF-8"
            )
        return value

    def insert(self, collection, fields, params, *, deadline=None):
        _check_deadline(deadline)
        table = quote_identifier(collection)
        columns = ", ".join(quote_identifier(field) for field in fields)
        marks = ", ".join("?" for _ in fields)
        try:
            cursor = self._db.execute("INSERT INTO " + table + " (" + columns + ") VALUES (" + marks + ")", params)
            self._db.commit()
        except sqlite3.IntegrityError:
            raise ConflictError("write conflicts with a constraint")
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"rowid": cursor.lastrowid}

    def insert_in_transaction(self, collection, fields, params):
        # No commit/rollback here (unlike `insert` above): this runs
        # inside a transaction the seam's own `transact()` already opened
        # via `begin()` and will `commit()`/`rollback()` once, after every
        # operation in the batch. Low-level driver errors are still
        # translated to this shared `errors.FoundationError` vocabulary
        # here (mirroring `insert()`'s own translation) so `cell.py`'s
        # `transact()` never needs to name a backend-native exception type
        # (R-3).
        table = quote_identifier(collection)
        statement = "INSERT INTO " + table + " (" + ", ".join(
            quote_identifier(field) for field in fields) + ") VALUES (" + \
            ", ".join("?" for _ in fields) + ")"
        try:
            cursor = self._db.execute(statement, params)
        except sqlite3.IntegrityError:
            raise ConflictError("write conflicts with a constraint")
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"rowid": cursor.lastrowid}

    def update_in_transaction(self, collection, fields, params, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `update` above)
        # -- mirrors `insert_in_transaction`'s own reasoning above. Runs
        # inside the transaction `transact()` already opened via
        # `begin()` and will `commit()`/`rollback()` once, after every
        # operation in the batch.
        table = quote_identifier(collection)
        where, where_params = self._where_sql(filters)
        statement = "UPDATE " + table + " SET " + ", ".join(
            quote_identifier(field) + " = ?" for field in fields) + where
        try:
            cursor = self._db.execute(statement, list(params) + where_params)
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"updated": cursor.rowcount}

    def delete_in_transaction(self, collection, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `delete` above)
        # -- same reasoning as `update_in_transaction` immediately above.
        # `cell.ApplicationCell` has already run this request through the
        # same declare-and-echo confirmation choke `delete()` itself uses
        # before this is ever called.
        table = quote_identifier(collection)
        where, params = self._where_sql(filters)
        statement = "DELETE FROM " + table + where
        try:
            cursor = self._db.execute(statement, params)
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"deleted": cursor.rowcount}

    def _where_sql(self, filters):
        clauses, params = [], []
        for item in filters:
            column = quote_identifier(item.field)
            if item.operator == "in":
                clauses.append(column + " IN (" + ",".join("?" for _ in item.value) + ")")
                params.extend(item.value)
            else:
                clauses.append(column + " " + SQL_OPERATOR_TOKENS[item.operator] + " ?")
                params.append(item.value)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def read(self, collection, selected, filters, order_by, limit, *, deadline=None):
        _check_deadline(deadline)
        table = quote_identifier(collection)
        statement = "SELECT " + ", ".join(quote_identifier(x) for x in selected) + " FROM " + table
        where, params = self._where_sql(filters)
        statement += where
        if order_by is not None:
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
            try:
                order_terms = ", ".join(
                    quote_identifier(field) + " " + _DIRECTION_TOKENS[direction] for field, direction in order_by
                )
            except KeyError as exc:
                raise ValidationError("invalid order direction") from exc
            statement += " ORDER BY " + order_terms
        statement += " LIMIT ?"
        params = list(params) + [limit]
        try:
            rows = self._db.execute(statement, params).fetchall()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return [dict(row) for row in rows]

    def update(self, collection, fields, params, filters, *, deadline=None):
        _check_deadline(deadline)
        table = quote_identifier(collection)
        where, where_params = self._where_sql(filters)
        statement = "UPDATE " + table + " SET " + ", ".join(
            quote_identifier(field) + " = ?" for field in fields) + where
        try:
            cursor = self._db.execute(statement, list(params) + where_params)
            self._db.commit()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"updated": cursor.rowcount}

    def delete(self, collection, filters, audit_hook=None, *, deadline=None):
        _check_deadline(deadline)
        table = quote_identifier(collection)
        where, params = self._where_sql(filters)
        statement = "DELETE FROM " + table + where
        try:
            cursor = self._db.execute(statement, params)
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        # Phase 4: same pre-commit-hook structure as `create_collection`
        # above -- `cell.ApplicationCell.delete` has already run this
        # request through `_validate_delete_confirmation` before this is
        # ever called.
        try:
            if audit_hook is not None:
                audit_hook.pre_commit()
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        return {"deleted": cursor.rowcount}

    def begin(self, *, deadline=None):
        _check_deadline(deadline)
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
        if self._db.in_transaction:
            self._db.rollback()
        self._db.execute("BEGIN")

    def commit(self):
        self._db.commit()

    def rollback(self):
        self._db.rollback()

    def close(self):
        self._db.close()
