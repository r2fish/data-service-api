"""Backend-independent storage seam (R-3, docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md).

``cell.ApplicationCell`` owns every backend-independent concern on its own:
request shape/limit validation, principal authorization, capability
declaration (single source, ``ApplicationRuntime.capabilities()``), error
classification (the ``errors.FoundationError`` hierarchy), and
declare-and-echo confirmation-phrase construction. A storage backend
(``backend_sqlite.SQLiteBackend`` / ``backend_postgres.PostgresBackend``)
owns only EXECUTION: turning an already-validated, already-encoded request
into the target engine's own statements.

This module holds the two things both backends legitimately share:

- ``StorageBackend``, documenting (not enforcing via ``abc`` -- the seam
  only ever duck-types a backend) every method ``ApplicationCell`` calls,
  so a future third backend has one place that names its whole required
  surface.
- ``SQL_OPERATOR_TOKENS``, the ``eq``/``ne``/``lt``/``lte``/``gt``/``gte``/
  ``in`` -> native infix-operator-token mapping. This is genuinely
  engine-independent (``=``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``IN``
  are the identical tokens in both SQLite's and PostgreSQL's own SQL
  grammars), unlike R-2's choke-point EXECUTION discipline itself, which
  is deliberately never shared with r2db-api (the whole point of two
  independent peer implementations, R-2's own closing paragraph) --
  sharing a literal string-constant table between MitateDB-api's own two
  backends is a different question from sharing code with a different
  peer, and does not weaken either backend's own independent choke point.
"""

# Filter.operator -> native SQL infix token. `in` is handled specially by
# each backend (a parenthesized placeholder list, one per value), but is
# listed here too so a backend's operator dispatch has one shared table to
# consult for every operator name ``cell.py`` itself considers valid.
SQL_OPERATOR_TOKENS = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "in": "IN",
}


class StorageBackend:
    """Documents the methods ``ApplicationCell`` calls on a backend.

    Every method below receives input the seam has ALREADY fully
    validated: identifiers have passed both the shared syntax allowlist
    (``identifiers.validate_identifier``) and this backend's own
    ``check_reserved``; values have already passed the seam's own
    universal shape check (``ApplicationCell._normalize_value``) AND this
    backend's own ``encode_value`` (the backend-specific value-domain gate,
    e.g. PostgreSQL's embedded-NUL rejection); filters have already been
    checked for field existence and operator support. A backend must still
    treat every value as untrusted for BINDING purposes (R-2) -- shape
    validation does not certify a value is safe to interpolate as SQL
    text, only that its type/format is acceptable at the API level. No
    backend method may ever build a statement by interpolating a value
    into SQL text; every value reaches the database only as a bound
    parameter.

    This class is never instantiated or subclassed for real -- it is pure
    documentation of the duck-typed contract both
    ``backend_sqlite.SQLiteBackend`` and ``backend_postgres.PostgresBackend``
    independently implement.
    """

    #: Frozen set of exact reserved names PLUS whatever additional pattern
    #: ``check_reserved`` itself enforces (e.g. PostgreSQL's ``pg_`` prefix
    #: rule cannot be expressed as a plain set membership test, which is
    #: why reservation is a *method*, not just a published set).
    def check_reserved(self, value, label):
        """Raise ``errors.ValidationError`` if ``value`` collides with a
        name this backend reserves for its own bookkeeping/catalog, after
        the shared syntax allowlist has already accepted it."""
        raise NotImplementedError

    def schema_count(self):
        """Number of collections/entities that currently exist."""
        raise NotImplementedError

    def field_domains(self, collection):
        """Live ``{field_name: domain}`` mapping for `collection`. Raises
        ``errors.NotFoundError`` if it does not exist -- this doubles as
        every read/write/filter path's own live-catalog existence check
        (R-2 stage 2 for PostgreSQL; the SQLite backend's ``PRAGMA
        table_info`` equivalent). ``domain`` is a backend-defined value-
        domain category ``encode_value`` can validate a bound value
        against (B-1, independent review round 2: PostgreSQL's own
        ``"text"``/``"int32"``/``"int64"``/``"float"``, derived from its
        live ``information_schema.columns.data_type``) or ``None`` when a
        backend has no such concept (the SQLite backend returns ``None``
        for every field -- its column affinity is dynamic, so there is no
        equivalent mismatch for it to detect, and its own external
        behavior must stay unchanged, WP-1 P3 round 2 instruction #1)."""
        raise NotImplementedError

    def schema_revision(self):
        """Current schema-revision counter for this application (bumped
        by every ``create_collection``/``add_field`` call -- see
        ``cell.py``'s own delete-confirmation-phrase comment for why this
        exists)."""
        raise NotImplementedError

    def create_collection(self, name, fields):
        """``fields``: ``{field_name: declared_type}`` using this
        foundation's own vocabulary (``cell._TYPES``). Raises
        ``errors.ConflictError`` if ``name`` already exists. Bumps the
        schema revision atomically with the DDL."""
        raise NotImplementedError

    def add_field(self, collection, field, field_type):
        """Raises ``errors.NotFoundError`` if ``collection`` does not
        exist, ``errors.ConflictError`` if ``field`` already exists on it.
        Bumps the schema revision atomically with the DDL."""
        raise NotImplementedError

    def encode_value(self, value, domain=None):
        """Backend-specific bind-safe encoding AND backend-specific
        value-domain validation (R-2/B-1 choke point) of an already
        shape-checked value (``cell.ApplicationCell._normalize_value``'s
        output: ``str``/``int``/``float``/``bool``/``None``, dict/list
        already flattened to a JSON string by the seam). ``domain`` is the
        target field's own domain category from this same backend's
        ``field_domains`` (or ``None`` when the seam has no field context,
        e.g. a value with nothing to check against). Must raise
        ``errors.ValidationError`` for a value this backend's own storage
        engine cannot represent at all (e.g. PostgreSQL rejecting an
        embedded NUL byte) OR that mismatches its own target column's
        domain (e.g. a string value for a declared-``integer`` column, or
        an out-of-range integer) -- deterministically, before any
        statement is ever sent, rather than surfacing the database
        driver's own runtime error."""
        raise NotImplementedError

    def insert(self, collection, fields, params):
        """Returns ``{"rowid": <backend-assigned row identifier>}``."""
        raise NotImplementedError

    def read(self, collection, selected, filters, order_by, limit):
        """``filters``: list of already-bound ``cell.Filter`` (field
        verified to exist, operator verified supported, value already
        encoded). ``order_by``: ``(field, "asc"|"desc")`` or ``None``.
        Returns a list of ``dict`` rows."""
        raise NotImplementedError

    def update(self, collection, fields, params, filters):
        """Returns ``{"updated": <row count>}``."""
        raise NotImplementedError

    def delete(self, collection, filters):
        """Returns ``{"deleted": <row count>}``."""
        raise NotImplementedError

    def begin(self):
        """Open a multi-statement transaction for ``transact()``."""
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

    def rollback(self):
        raise NotImplementedError

    def insert_in_transaction(self, collection, fields, params):
        """Same contract as ``insert`` but executes inside the
        transaction opened by ``begin()`` (no implicit commit)."""
        raise NotImplementedError

    def update_in_transaction(self, collection, fields, params, filters):
        """P3-D2 (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
        R-5, WP-1.5): same contract as ``update`` but executes inside the
        transaction ``begin()`` already opened (no implicit commit) --
        the ``transact()`` batch dispatcher's own update branch, mirroring
        ``insert_in_transaction``'s own split from ``insert``."""
        raise NotImplementedError

    def delete_in_transaction(self, collection, filters):
        """P3-D2 (WP-1.5): same contract as ``delete`` but executes
        inside the transaction ``begin()`` already opened (no implicit
        commit). ``cell.ApplicationCell`` has already run this exact
        request through the SAME declare-and-echo confirmation choke
        ``delete()`` itself uses (``_validate_delete_confirmation``)
        before this is ever called -- a backend never sees an
        unconfirmed destructive delete, whether it arrived through the
        dedicated method or through a batch."""
        raise NotImplementedError

    def close(self):
        """Release any held connections/resources. A no-op is
        acceptable for a backend with nothing to release."""
        raise NotImplementedError
