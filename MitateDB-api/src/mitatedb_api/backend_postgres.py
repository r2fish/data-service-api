"""PostgreSQL storage backend (R-2/R-3).

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
differences from that peer's own design: no pooling (this foundation
serializes every operation through ``cell.ApplicationCell``'s own lock
already, so a single persistent connection per role is sufficient for this
WP; connection pooling/limits are future-work, design v1.1 §7), no row
addressability (``row_addressability`` stays declared ``unavailable`` --
see ``insert``'s own docstring for why its ``rowid`` return value uses
PostgreSQL's ``ctid`` rather than a stable published address), and no Row
Level Security (this foundation's primary isolation wall is
database-per-application, R-1 -- RLS as an additional layer is future-work,
design v1.1 §7, not this WP's own containment boundary).
"""

import psycopg
from psycopg import sql

from .backend import SQL_OPERATOR_TOKENS
from .errors import ConflictError, NotFoundError, ValidationError
from .identifiers import validate_identifier

# R-3 (design v1.1 §0/R-4 WP-0 m-7): backend-specific reserved names.
# `audit_events` mirrors the SQLite backend's own defensive reservation
# (against a future local audit-table name collision); the `pg_` PREFIX
# rule is PostgreSQL-specific -- every name PostgreSQL's own system
# catalog uses starts with it (`pg_class`, `pg_attribute`, ...), and it is
# not expressible as a plain set-membership check, which is why
# `check_reserved` is a method rather than a published `frozenset` (unlike
# the exact-match-only SQLite backend).
_RESERVED_EXACT = frozenset({"audit_events"})
_RESERVED_PREFIX = "pg_"

# Foundation field-type vocabulary -> this backend's own native column
# type. `boolean` maps to `INTEGER`, not PostgreSQL's native `BOOLEAN`
# type, DELIBERATELY: PostgreSQL has no implicit (nor even explicit,
# `::boolean`/`::integer`) cast between `boolean` and any integer type, so
# a bound Python `bool` (this module's own `encode_value` below converts
# every `bool` to `int`, matching the SQLite backend's own already-
# existing conversion) would fail to bind against a genuinely
# `BOOLEAN`-typed column. Using `INTEGER` for both backends' own
# `boolean` field type keeps their observable behavior identical (both
# backends store and round-trip a declared-boolean field as 0/1) without
# either backend needing to know the OTHER exists.
#
# m-7 (independent review): every value here is precomposed as a
# `sql.SQL` constant (not a bare Python string later joined with `+`), so
# every call site that uses one composes SQL exclusively via `.format()`
# placeholders -- no method in this module builds a statement fragment by
# Python string concatenation.
_TYPES = {"text": "TEXT", "integer": "BIGINT", "real": "DOUBLE PRECISION",
          "boolean": "INTEGER", "json": "TEXT"}
_TYPE_SQL = {name: sql.SQL(native) for name, native in _TYPES.items()}

# B-1 (i): reverse map from PostgreSQL's own `information_schema.columns.
# data_type` string back to a DOMAIN category `encode_value` validates
# against. `text` covers both this foundation's own `text` AND `json`
# field types (both physically `TEXT` columns, per `_TYPES` above) --
# `encode_value`'s own `"text"` domain (str-shaped, NUL-free) is identical
# for either declared vocabulary word, so the two-way ambiguity here is
# harmless: nothing downstream needs to recover which of the two a column
# was originally declared as, only what VALUE SHAPE it accepts.
_DOMAIN_BY_DATA_TYPE = {
    "bigint": "int64",           # this foundation's own `integer`
    "integer": "int32",          # this foundation's own `boolean`
    "double precision": "float",  # this foundation's own `real`
    "text": "text",              # this foundation's own `text` or `json`
}
_INT_DOMAIN_RANGES = {
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
}


def _validate_value_domain(value, domain=None):
    """B-1 value-domain gate (independent review, both rounds). A pure,
    connection-independent function (m-8, round 2: "layer (i) 単体テスト
    は接続不要であるべき") -- `PostgresBackend.encode_value` is a thin
    wrapper that just calls this; `tests/test_postgres.py` also calls it
    directly, with no live server involved, to pin the mechanism itself
    independent of any integration-level round trip (round 2's own
    finding: 3 of the reviewer's 4 mutations survived because the only
    tests exercising this logic went through the FULL insert/read/update/
    delete path, where the layer (ii) backstop produces the identical
    `ValidationError` a layer (i) bypass would have -- masking the
    regression at the black-box level).

    `domain`: one of `field_domains`'s own `"text"`/`"int32"`/`"int64"`/
    `"float"` category strings, or `None` when the caller has no column
    context -- `None` skips domain validation entirely, matching this
    function's own pre-B-1 behavior for that case (shape-checked-but-not-
    domain-checked), never silently WIDENING what a real column call site
    accepts.
    """
    # M-5 (independent review round 2, regression from B-1's own first
    # round): SQL `NULL` is a valid value for ANY column regardless of its
    # declared type (this foundation defines no `NOT NULL` constraint
    # anywhere, `migrations/0003_provision_application.sql`) -- domain
    # validation must never apply to it. The pre-fix `_check_domain`
    # rejected `None` unconditionally (every domain branch's own
    # `isinstance` check is `False` for `None`, falling through to "value
    # does not match the declared field type"), which made writing OR
    # filtering on `NULL` impossible on this backend even though SQLite
    # (no domain concept at all) and the schema itself both allow it --
    # checked FIRST, before anything else in this function, so nothing
    # below ever sees `None`.
    if value is None:
        return None
    # Deterministic, pre-execution rejection (independent-review
    # finding, WP-1 P3 round 2 instruction #1): PostgreSQL's `text`
    # storage cannot represent an embedded NUL (U+0000) codepoint at
    # all -- the common conformance corpus (`conformance-tests/
    # payloads.py`'s `nul_byte = "value\x00tail"`) presents exactly
    # this as a real value-position payload. The SQLite backend's own
    # round-trip-accepts behavior for the identical payload is
    # UNCHANGED (`backend_sqlite.py` has no equivalent check) -- a
    # genuine, backend-specific value domain difference, not a bug.
    #
    # A dict/list value has already become a JSON string by this
    # point (`cell.ApplicationCell._normalize_value`), and `json.
    # dumps` always escapes a NUL codepoint as the 6-character
    # backslash-u-0000 sequence in its OWN output text -- never a raw
    # NUL byte -- so nothing further is needed for the dict/list case;
    # only a value that is ALREADY a plain `str` at this point can
    # carry a literal NUL through to a bind parameter.
    if isinstance(value, str) and "\x00" in value:
        raise ValidationError(
            "value contains an embedded NUL character, which PostgreSQL text storage cannot represent"
        )
    # See this module's own `_TYPES` comment: `boolean` fields are
    # physically `INTEGER` columns on this backend (as on SQLite's),
    # so a Python `bool` is converted here too -- keeping both
    # backends' own observable value representation identical. This
    # runs BEFORE the domain check below so an `int32`/`int64` domain
    # check sees a plain `int`, never a `bool` (`isinstance(True,
    # int)` is `True` in Python, which would otherwise let a stray
    # `bool` slip through an `int` domain check unconverted).
    if isinstance(value, bool):
        value = int(value)
    if domain is not None:
        value = _check_domain(value, domain)
    return value


def _check_domain(value, domain):
    """B-1 (i): the actual value-domain gate, a pure function (m-8).
    Runs BEFORE any statement reaches PostgreSQL, so a type-mismatched
    value never gets the chance to raise `InvalidTextRepresentation`/
    `NumericValueOutOfRange`/etc. at the driver level. Every rejection
    message here starts with "value" and says "does not match"/"is out of
    range" -- deliberately worded differently from the layer (ii)
    backstop's own generic "storage backend rejected the request" (every
    DML/DDL method's final `except psycopg.Error` branch), so a test can
    tell WHICH layer actually caught a given case (m-8 (ii))."""
    if domain == "text":
        if not isinstance(value, str):
            raise ValidationError("value does not match the declared field type")
        return value
    if domain in _INT_DOMAIN_RANGES:
        if not isinstance(value, int):
            raise ValidationError("value does not match the declared field type")
        low, high = _INT_DOMAIN_RANGES[domain]
        if not (low <= value <= high):
            raise ValidationError("value is out of range for the declared field type")
        return value
    if domain == "float":
        if not isinstance(value, (int, float)):
            raise ValidationError("value does not match the declared field type")
        return float(value)
    return value


# m-7: operator-token and ORDER BY direction lookups, precomposed as
# `sql.SQL` constants (never a bare Python string concatenated with `+`
# into a statement fragment).
_OPERATOR_SQL = {name: sql.SQL(token) for name, token in SQL_OPERATOR_TOKENS.items()}
_DIRECTION_SQL = {"asc": sql.SQL("ASC"), "desc": sql.SQL("DESC")}

# Bookkeeping table name (provisioned by `migrations/0003_provision_
# application.sql`, mirroring r2db-api's own `_r2db_schema_revision`
# table -- an independently-designed table of the same SHAPE, not shared
# code, matching R-2's own "no code sharing between peers" principle
# applied here to the migrations set instead).
#
# m-1 (independent review correction): this table is NOT excluded from
# `field_domains`'s own visible catalog by any special-case filter in this
# module (unlike r2db-api's own `_r2db_schema_revision` exclusion, which
# IS filtered out of that peer's catalog view) -- an application-level
# `field_domains("_mdb_schema_revision")` call would in fact return its
# real columns if one were ever issued. The REAL defenses that keep it
# unreachable from application code are two independent, structural ones:
# (a) `identifiers._IDENTIFIER` requires a name to start with `[a-z]`, so
# the leading underscore alone makes `"_mdb_schema_revision"` fail the
# SHARED syntax allowlist before this module is ever consulted (`cell.py`'s
# own `_identifier` gate), and (b) even if that gate were bypassed, the
# runtime role this backend's own `_runtime` connection authenticates as
# has NO grant of any kind on this table (`migrations/0003_provision_
# application.sql` creates it BEFORE the `ALTER DEFAULT PRIVILEGES`
# statement runs, so that statement's future-tables grant never reaches
# it) -- `tests/test_postgres.py`'s own dedicated tests exercise both of
# these directly.
_SCHEMA_REVISION_TABLE = "_mdb_schema_revision"


def _execute(cursor, statement, params=()):
    """R-2 choke point. The ONLY call to `cursor.execute` in this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError(
            "PostgresBackend._execute refuses a %s; only psycopg.sql.SQL/"
            "Composed objects may reach the database (R-2 choke point)"
            % (type(statement).__name__,)
        )
    cursor.execute(statement, params)
    return cursor


class PostgresBackend:
    """Two persistent connections per application cell.

    `developer_conn` (this application's own PostgreSQL DEVELOPER role --
    schema owner, DDL authority) executes every schema-mutating and
    catalog-reading statement; `runtime_conn` (this application's own
    PostgreSQL RUNTIME role -- DML only, per R-1's provisioning grants)
    executes every data statement. This is R-1's own role separation
    enforced a second time, structurally, underneath this foundation's own
    application-level `_require_developer`/`_require_data` gates (`cell.
    py`): even a code defect that let a non-developer principal reach
    `create_collection` at the Python level would still hit PostgreSQL's
    own `InsufficientPrivilege` the moment it attempted DDL over
    `runtime_conn`, because this backend never even attempts DDL there.
    """

    def __init__(self, runtime_dsn, developer_dsn):
        self._runtime = psycopg.connect(runtime_dsn, autocommit=False)
        self._developer = psycopg.connect(developer_dsn, autocommit=False)

    def close(self):
        self._runtime.close()
        self._developer.close()

    def check_reserved(self, value, label):
        if value in _RESERVED_EXACT or value.startswith(_RESERVED_PREFIX):
            raise ValidationError("reserved " + label)

    # ------------------------------------------------------------------
    # catalog (developer connection -- schema owner)
    # ------------------------------------------------------------------
    def schema_count(self):
        try:
            with self._developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name <> %s"
                ), [_SCHEMA_REVISION_TABLE])
                count = cur.fetchone()[0]
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        return count

    def field_domains(self, collection):
        """Live catalog lookup (R-2 stage 2) doubling as the value-domain
        source B-1 (i) needs: for every column of `collection`, this
        database's own `information_schema.columns.data_type` is mapped
        back to a domain category (`_DOMAIN_BY_DATA_TYPE`) `encode_value`
        can validate a bound value against. Raises `errors.NotFoundError`
        if `collection` does not exist -- the same existence-check role
        the pre-B-1 `field_names` method played.
        """
        validate_identifier(collection, "collection")
        try:
            with self._developer.cursor() as cur:
                _execute(cur, sql.SQL(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position"
                ), [collection])
                rows = cur.fetchall()
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        if not rows:
            raise NotFoundError("collection not found")
        return {name: _DOMAIN_BY_DATA_TYPE.get(data_type, "text") for name, data_type in rows}

    def schema_revision(self):
        try:
            with self._developer.cursor() as cur:
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                row = cur.fetchone()
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        return row[0] if row else 0

    def _bump_schema_revision(self, cur):
        _execute(cur, sql.SQL("UPDATE {} SET revision = revision + 1 WHERE id = TRUE")
                  .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))

    # ------------------------------------------------------------------
    # DDL (developer connection only -- R-1)
    # ------------------------------------------------------------------
    def create_collection(self, name, fields):
        validate_identifier(name, "collection")
        definitions = []
        for field, field_type in fields.items():
            validate_identifier(field, "field")
            definitions.append(sql.SQL("{} {}").format(sql.Identifier(field), _TYPE_SQL[field_type]))
        statement = sql.SQL("CREATE TABLE {} ({})").format(
            sql.Identifier(name), sql.SQL(", ").join(definitions)
        )
        try:
            with self._developer.cursor() as cur:
                _execute(cur, statement)
                self._bump_schema_revision(cur)
        except psycopg.errors.DuplicateTable:
            self._developer.rollback()
            raise ConflictError("collection already exists")
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()

    def add_field(self, collection, field, field_type):
        validate_identifier(collection, "collection")
        validate_identifier(field, "field")
        statement = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
            sql.Identifier(collection), sql.Identifier(field), _TYPE_SQL[field_type]
        )
        try:
            with self._developer.cursor() as cur:
                _execute(cur, statement)
                self._bump_schema_revision(cur)
        except psycopg.errors.DuplicateColumn:
            self._developer.rollback()
            raise ConflictError("field already exists")
        except psycopg.errors.UndefinedTable:
            self._developer.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()

    # ------------------------------------------------------------------
    # values (R-2/B-1 value-domain gate) -- see the module-level
    # `_validate_value_domain`/`_check_domain` functions below, which hold
    # ALL of the actual logic. `encode_value` is a thin instance-method
    # wrapper only so it satisfies the shared `StorageBackend.encode_value`
    # call shape (`cell.py` always calls it as `self._backend.
    # encode_value(...)`); the real logic is deliberately free-standing,
    # connection-independent functions (m-8, independent review round 2:
    # "layer (i) 単体テストは接続不要であるべき" -- `tests/test_postgres.
    # py` calls these two directly, with no `platform`/`app_a` fixture and
    # no live PostgreSQL server involved at all).
    # ------------------------------------------------------------------
    def encode_value(self, value, domain=None):
        return _validate_value_domain(value, domain)

    # ------------------------------------------------------------------
    # DML (runtime connection only -- R-1)
    # ------------------------------------------------------------------
    def _where_sql(self, filters):
        if not filters:
            return sql.SQL(""), []
        clauses = []
        params = []
        for item in filters:
            column = sql.Identifier(item.field)
            if item.operator == "in":
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in item.value)
                clauses.append(sql.SQL("{} IN ({})").format(column, placeholders))
                params.extend(item.value)
            else:
                clauses.append(sql.SQL("{} {} %s").format(column, _OPERATOR_SQL[item.operator]))
                params.append(item.value)
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses), params

    def insert(self, collection, fields, params):
        # PostgreSQL 12+ has no per-row OID by default and this
        # foundation's own entity tables carry no server-assigned primary
        # key/serial column of any kind (unlike r2db-api's own `address`
        # concept -- this foundation declares `row_addressability:
        # unavailable`, and nothing in this return value is part of that
        # capability's own public surface: `conformance/
        # conformance_adapter_mitatedb.py::attempt_mutation_with_addresses`
        # already documents that this foundation's `insert()` return shape
        # carries nothing address-shaped and always reports `None`).
        # `ctid` is PostgreSQL's own always-present physical row locator
        # system column -- an opaque `(block,offset)` pair, returned here
        # as its string form purely as an "insert succeeded, here is SOME
        # backend-native handle" value. Unlike SQLite's own `rowid`
        # (stable across an `UPDATE`), PostgreSQL's `ctid` changes on
        # `UPDATE`/`VACUUM` -- a real, deliberate asymmetry between the
        # two backends' own `rowid` values, harmless here because no
        # caller (this test suite included) treats the returned value as
        # a stable long-term identity.
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in fields)
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING ctid").format(
            sql.Identifier(collection), columns, placeholders
        )
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                rowid = str(cur.fetchone()[0])
        except psycopg.errors.UniqueViolation:
            self._runtime.rollback()
            raise ConflictError("write conflicts with a constraint")
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): defensive backstop -- see this module's own
            # top-of-file docstring. Guarantees `self._runtime` is never
            # left aborted for the next call on this cell.
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return {"rowid": rowid}

    def insert_in_transaction(self, collection, fields, params):
        # No commit/rollback here (unlike `insert` above): this runs
        # inside a transaction the seam's own `transact()` already opened
        # via `begin()` and will `commit()`/`rollback()` once, after every
        # operation in the batch (`cell.py::transact`'s own `except`
        # clause calls `self._backend.rollback()`, which is sufficient to
        # clear a psycopg connection's own aborted-transaction state after
        # an exception raised here). Low-level driver errors are still
        # translated to this shared `errors.FoundationError` vocabulary
        # here (mirroring `insert()`'s own translation) so `cell.py`'s
        # `transact()` never needs to name a backend-native exception type
        # (R-3).
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in fields)
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING ctid").format(
            sql.Identifier(collection), columns, placeholders
        )
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                rowid = str(cur.fetchone()[0])
        except psycopg.errors.UniqueViolation:
            raise ConflictError("write conflicts with a constraint")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates,
            # which is the single rollback point for the whole batch.
            raise ValidationError("storage backend rejected the request") from exc
        return {"rowid": rowid}

    def update_in_transaction(self, collection, fields, params, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `update` below)
        # -- mirrors `insert_in_transaction`'s own reasoning above. Runs
        # inside the transaction the seam's own `transact()` already
        # opened via `begin()` and will `commit()`/`rollback()` once,
        # after every operation in the batch.
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(f)) for f in fields
        )
        statement = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(collection), assignments)
        where, where_params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, list(params) + where_params)
                updated = cur.rowcount
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates.
            raise ValidationError("storage backend rejected the request") from exc
        return {"updated": updated}

    def delete_in_transaction(self, collection, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `delete` below)
        # -- same reasoning as `update_in_transaction` immediately above.
        # `cell.ApplicationCell` has already run this request through the
        # same declare-and-echo confirmation choke `delete()` itself uses
        # before this is ever called.
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                deleted = cur.rowcount
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return {"deleted": deleted}

    def read(self, collection, selected, filters, order_by, limit):
        columns = sql.SQL(", ").join(sql.Identifier(x) for x in selected)
        statement = sql.SQL("SELECT {} FROM {}").format(columns, sql.Identifier(collection))
        where, where_params = self._where_sql(filters)
        statement = statement + where
        if order_by is not None:
            # WP-3: `order_by` is always `None` or a non-empty LIST of
            # `(field, direction)` tuples now (`cell.py::_bind_order_by`),
            # multi-field sort included -- a pre-WP-3 single-field caller
            # already reaches this as a one-element list.
            #
            # M-4 (independent review, consistency fix): an unexpected
            # `direction` here used to raise a raw, untranslated `KeyError`
            # (this dict lookup runs BEFORE the `try/except psycopg.Error`
            # block below, so that block never saw it) -- never reachable
            # through `cell.py`'s own allowlist today, but the identical
            # defense-in-depth reasoning `backend_sqlite.py`'s own
            # `_DIRECTION_TOKENS` lookup now documents applies here too:
            # this backend's own SQL-composition step should fail with a
            # classified `errors.ValidationError`, not an uncaught
            # `KeyError`, regardless of what `cell.py` currently allows
            # through.
            try:
                terms = sql.SQL(", ").join(
                    sql.SQL("{} {}").format(sql.Identifier(field), _DIRECTION_SQL[direction])
                    for field, direction in order_by
                )
            except KeyError as exc:
                raise ValidationError("invalid order direction") from exc
            statement = statement + sql.SQL(" ORDER BY ") + terms
        statement = statement + sql.SQL(" LIMIT %s")
        params = list(where_params) + [limit]
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                columns_desc = [c.name for c in cur.description]
                rows = [dict(zip(columns_desc, row)) for row in cur.fetchall()]
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return rows

    def update(self, collection, fields, params, filters):
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(f)) for f in fields
        )
        statement = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(collection), assignments)
        where, where_params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, list(params) + where_params)
                updated = cur.rowcount
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return {"updated": updated}

    def delete(self, collection, filters):
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                deleted = cur.rowcount
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return {"deleted": deleted}

    def begin(self):
        # psycopg3 connections (`autocommit=False`) already implicitly
        # start a transaction on first use; nothing to do beyond ensuring
        # no stale transaction is left open from a previous call.
        self._runtime.rollback()

    def commit(self):
        self._runtime.commit()

    def rollback(self):
        self._runtime.rollback()
