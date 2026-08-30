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

from .backend import SQL_OPERATOR_TOKENS
from .errors import ConflictError, NotFoundError, ValidationError
from .identifiers import quote_identifier, validate_identifier

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

    def create_collection(self, name, fields):
        definitions = []
        for field, field_type in fields.items():
            definitions.append(quote_identifier(field) + " " + _TYPES[field_type])
        statement = "CREATE TABLE " + quote_identifier(name) + " (" + \
            ", ".join(definitions) + ")"
        try:
            self._db.execute(statement)
            self._db.commit()
        except sqlite3.DatabaseError:
            raise ConflictError("collection already exists")
        self._schema_revision += 1

    def add_field(self, collection, field, field_type):
        table = quote_identifier(collection)
        statement = "ALTER TABLE " + table + " ADD COLUMN " + \
            quote_identifier(field) + " " + _TYPES[field_type]
        try:
            self._db.execute(statement)
            self._db.commit()
        except sqlite3.OperationalError as exc:
            # sqlite3 reports both "no such table" and "duplicate column
            # name" as OperationalError with no separate exception class
            # to distinguish them by type -- the caller (`cell.py`) has
            # already confirmed the collection exists via `field_domains`
            # immediately before calling this, so by the time control
            # reaches here the only way ALTER TABLE can still fail is a
            # duplicate column name.
            raise ConflictError("field already exists") from exc
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        self._schema_revision += 1

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
        return value

    def insert(self, collection, fields, params):
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

    def read(self, collection, selected, filters, order_by, limit):
        table = quote_identifier(collection)
        statement = "SELECT " + ", ".join(quote_identifier(x) for x in selected) + " FROM " + table
        where, params = self._where_sql(filters)
        statement += where
        if order_by is not None:
            field, direction = order_by
            statement += " ORDER BY " + quote_identifier(field) + " " + direction.upper()
        statement += " LIMIT ?"
        params = list(params) + [limit]
        try:
            rows = self._db.execute(statement, params).fetchall()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return [dict(row) for row in rows]

    def update(self, collection, fields, params, filters):
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

    def delete(self, collection, filters):
        table = quote_identifier(collection)
        where, params = self._where_sql(filters)
        statement = "DELETE FROM " + table + where
        try:
            cursor = self._db.execute(statement, params)
            self._db.commit()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        return {"deleted": cursor.rowcount}

    def begin(self):
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
