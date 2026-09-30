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

# Phase 9 WP-3a rework (code review §2 A, 監督裁定 A 2026-09-07): sentinel
# default for `alter_field_constraints`'s own `enum` parameter (and
# `cell.ApplicationCell.alter_field`'s identical one), distinguishing "the
# request omitted `enum`" (leave the field's current `enum` exactly as it
# is) from an explicit `enum: null` ("clear the field's `enum`" -- the
# ONLY way the contract's own `SchemaOperationRequest.enum` -- already
# `["array", "null"]` in the packaged contract copy -- can express "no
# enum" on an operation that must also be able to mean "leave it alone").
# A plain `None` default cannot carry this third state: Python
# collapses "the caller didn't pass this keyword at all" and "the caller
# passed `None`" into the identical value the callee sees. A bare `enum`
# (a non-empty `list`) means set/replace, exactly as before this rework.
UNCHANGED = object()


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

    def create_collection(self, name, fields, *, field_types=None, field_constraints=None, audit_hook=None,
                          deadline=None, dry_run=False):
        """WP-3b rework (F-2): ``deadline`` -- both ``backend_sqlite.
        SQLiteBackend`` and ``backend_postgres.PostgresBackend`` have
        always accepted this keyword (``ApplicationCell._limit_gate``'s
        own wall-clock deadline, ``execution_ms``); this Protocol
        declaration previously omitted it, undocumenting a parameter
        every real backend already required.

        ``fields``: ``{field_name: declared_type}`` using this
        foundation's own vocabulary (``cell._FIELD_TYPE_VOCABULARY``).
        Raises ``errors.ConflictError`` if ``name`` already exists. Bumps
        the schema revision atomically with the DDL. Returns ``(revision,
        descriptor)`` -- ``revision`` an ``int``, ``descriptor`` a
        ``definitions.EntityDescriptor``-shaped dict.

        Phase 9 WP-3b (design D-4): ``dry_run`` executes the DDL and
        every refusal check for real (the SAME ``ConflictError`` a real
        call raises), then rolls back instead of committing -- no
        ``field_types``/``field_constraints`` registry write, no
        revision bump, no ``audit_hook.pre_commit()`` call at all. The
        returned ``revision`` is then the CURRENT (unbumped) value and
        ``descriptor`` is the entity as it WOULD read afterwards.

        Phase 6 WP-3 (design D-3): ``field_types``, when given, is
        ``{field_name: contract_type}`` (the 7-word contract vocabulary,
        ``field_types.CONTRACT_TYPES``) -- written to this application's
        own declared-type registry, atomically with the DDL above. Every
        real caller (``cell.ApplicationCell.create_collection``) always
        supplies one entry per field in ``fields`` (deriving it from the
        foundation type when its own caller did not supply an explicit
        contract type) -- ``None``/a partial map is tolerated defensively
        but should not occur.

        Phase 9 WP-3a (design docs/design/
        PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/
        (4)): ``field_constraints``, when given, is ``{field_name:
        {"nullable": bool, "enum": [...]}}`` (partial -- a name in
        ``fields`` it omits gets ``{"nullable": True}``, no ``enum``) --
        written to this application's own constraint registry, in the
        SAME transaction as the DDL and the ``field_types`` registry
        write above.

        Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
        D-2/D-10): ``audit_hook``, when given, is called (``pre_commit()``)
        as the LAST thing this method does before its own commit point --
        every schema operation is unconditionally fail-closed class (D-2
        item 2). See ``audit_hook.py`` for the full call contract."""
        raise NotImplementedError

    def add_field(self, collection, field, field_type, *, contract_type=None, enum=None, nullable=None,
                  audit_hook=None, deadline=None, dry_run=False):
        """Raises ``errors.NotFoundError`` if ``collection`` does not
        exist, ``errors.ConflictError`` if ``field`` already exists on it.
        Bumps the schema revision atomically with the DDL. Returns
        ``(revision, descriptor)`` -- see ``create_collection``'s own
        identical return shape.

        Phase 6 WP-3 (design D-3): ``contract_type`` (one of
        ``field_types.CONTRACT_TYPES``) is written to the declared-type
        registry for ``field``, atomically with the DDL above -- see
        ``create_collection``'s own identical parameter.

        Phase 9 WP-3a (design D-2 (1)/(4)): ``enum``/``nullable``, when
        given, are this one new field's own constraint declaration --
        written to the constraint registry in the same transaction as
        the DDL. ``nullable=None`` (the common case, no explicit
        declaration) resolves to the contract default ``True``.

        Phase 4: same ``audit_hook`` contract as ``create_collection``
        above. Phase 9 WP-3b: same ``dry_run`` contract too."""
        raise NotImplementedError

    def field_constraints(self, collection):
        """Phase 9 WP-3a (design D-2 (1)/(4)): live ``{field_name:
        {"nullable": bool, "enum": [...]}}`` registry mapping for
        ``collection`` -- total over every field of ``collection``
        (``"enum"`` present only where declared). Raises ``errors.
        NotFoundError`` if ``collection`` does not exist, mirroring
        ``field_types``. The single source of truth ``GET /v1/catalog``
        and the cell-layer choke point (``cell.py::_prepare_values``,
        never ``_bind_filters``) both read."""
        raise NotImplementedError

    def all_field_constraints(self):
        """Phase 9 WP-3a (design D-2 (1)/(4)): ``{collection: {field:
        {"nullable": bool, "enum": [...]}}}`` for EVERY collection this
        backend currently has -- ``GET /v1/catalog``'s own sole data
        source for ``field_constraints``, alongside ``all_field_types``."""
        raise NotImplementedError

    def field_types_and_constraints(self, collection):
        """Phase 9 WP-3a rework (code review §2 C, P-8/G-4 performance
        finding): ``field_types(collection)`` and ``field_constraints(
        collection)`` combined into the ONE read both already make
        against the identical registry row (the PostgreSQL backend's own
        ``_mdb_field_types`` row, one per field) -- returns ``(types,
        constraints)``, the exact pair those two calls would each
        return on their own. Raises ``errors.NotFoundError`` if
        ``collection`` does not exist, mirroring both. ``cell.py::
        _prepare_values`` (and, via its own returned pair,
        ``_check_missing_required_fields``) is the sole caller -- this
        method exists to cut a write's own backend round trips, not to
        replace ``field_types``/``field_constraints`` for every other
        caller (``alter_field``'s own enum-type lookup, ``_decode_rows``,
        ``_bind_filters``, and this package's own tests all keep calling
        one or the other alone)."""
        raise NotImplementedError

    def alter_field_constraints(self, collection, field, *, enum=UNCHANGED, nullable=None, audit_hook=None,
                                deadline=None, dry_run=False):
        """Phase 9 WP-3a (design D-2 (5)/(6), 実装の形 4, 監督裁定 S-g;
        code review §2 A, 監督裁定 A 2026-09-07 for the tri-state ``enum``
        below): redeclares ``field``'s own ``enum``/``nullable``
        constraints. ``nullable=None`` leaves it unchanged (the contract
        gives it no null state to distinguish from omission -- it is a
        plain ``boolean`` property). ``enum`` is tri-state: the sentinel
        default ``UNCHANGED`` (this module's own) leaves the field's
        current ``enum`` exactly as it is; ``None`` CLEARS it (the field
        declares no ``enum`` afterward); any other value (a non-empty
        ``list``, already validated by the caller) SETS/REPLACES it.
        Raises ``errors.NotFoundError`` if ``collection``/``field`` does
        not exist.

        MUST perform, inside ONE transaction -- never a separate
        pre-flight scan followed by a separate commit (the ``create_
        collection``/``add_field`` "read, then DDL in another tx" shape
        does not apply here): (1) SELECT every existing row of
        ``collection`` and check it against the constraints this call
        would establish: raise ``errors.ConflictError`` with
        ``details={"field": "enum"|"nullable", "violated_declaration":
        "enum"|"nullable"}`` (the SAME value on both keys -- ``field``
        names the request's own top-level key this violation is
        attributable to, design D-3 (2); never a row value or a row
        count, SI-10) and change NOTHING -- neither the registry nor the
        schema revision -- if even one row would violate them; (2)
        otherwise, write the new constraints to the registry and bump
        the schema revision; (3) commit. Returns ``(revision, descriptor)``
        on success -- see ``create_collection``'s own identical return
        shape. Phase 9 WP-3b: ``dry_run`` performs the SAME scan (and its
        possible ``ConflictError``), then rolls back instead of writing
        the registry/bumping the revision/committing -- see
        ``create_collection``'s own identical ``dry_run`` contract.
        A PostgreSQL implementation additionally
        locks ``collection`` (``LOCK TABLE ... IN SHARE ROW EXCLUSIVE
        MODE`` -- plain ``SHARE MODE`` does not conflict with itself and
        can deadlock two concurrent callers at their own later
        ``ALTER TABLE``, R-35, Phase 10, WP-6d-i review) BEFORE step (1)'s
        own scan, inside the SAME transaction -- closing the READ
        COMMITTED phantom-write window between that scan and this
        method's own COMMIT (code review §2 F, 監督裁定 F 2026-09-07); an
        in-process backend needs no such lock (a single Python call is
        already atomic with respect to any other operation on the same
        process).

        Phase 4: same ``audit_hook`` contract as ``create_collection``
        above -- called (``pre_commit()``) as the LAST thing before this
        method's own commit point, only on the non-conflicting path."""
        raise NotImplementedError

    def field_types(self, collection):
        """Phase 6 WP-3 (design D-3): live ``{field_name: contract_type}``
        registry mapping for ``collection`` -- the 7-word contract
        vocabulary (``field_types.CONTRACT_TYPES``), NEVER derived from
        this backend's own physical column types (`object`/`array`/`json`
        are physically indistinguishable, and PostgreSQL's own declared
        `boolean` is physically an `INTEGER` column -- design §1.5 finding
        2). Raises ``errors.NotFoundError`` if ``collection`` does not
        exist, mirroring ``field_domains``. This is the SAME registry
        ``GET /v1/catalog`` (``http.py::get_catalog``) reads, and the
        single source of truth the ``cell.py`` choke point
        (``_prepare_values``/``_bind_filters``) validates every value
        against, backend-independently."""
        raise NotImplementedError

    def all_field_types(self):
        """Phase 6 WP-3 (design D-3): ``{collection: {field: contract_
        type}}`` for EVERY collection this backend currently has --
        ``GET /v1/catalog``'s (``http.py::get_catalog``) sole data
        source. A collection with zero registry rows is simply absent
        from the result (cannot occur for one this backend's own
        ``create_collection`` created -- every field always gets a
        registry row)."""
        raise NotImplementedError

    def encode_value(self, value, domain=None, *, field=None, declared_type=None):
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
        driver's own runtime error.

        ``field``/``declared_type`` (追補 4 O-2, ``{scratchpad}/rulings-r3-
        r7-flip.md``): ``cell.py``'s own 3 call sites always pass both --
        ``field`` the caller's own request-internal path, ``declared_type``
        the contract vocabulary word already resolved there -- so a value-
        domain denial reaching a normal client request carries the same
        D-3 (4) 4-key ``errors.details_vocabulary`` form every other
        choke-point denial does, never an empty ``details``. Both default
        to ``None`` for a direct, no-request-context call (a unit test
        exercising this mechanism in isolation)."""
        raise NotImplementedError

    def read(self, collection, selected, filters, order_by, limit, *, cursor_values=None):
        """``filters``: list of already-bound ``cell.Filter`` (field
        verified to exist, operator verified supported, value already
        encoded). ``order_by``: ``None`` or a non-empty list of
        ``(field, "asc"|"desc")`` tuples (WP-3: multi-field sort;
        ``cell.py::_bind_order_by`` always normalizes to this shape, a
        single-field caller included). Returns a list of ``dict`` rows.

        Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2b.4/D-3 (4):
        ``cursor_values``, when not ``None``, is a list already count/
        type-checked and index-aligned with ``order_by`` (the row-order
        tie-break column included) -- the keyset predicate this backend
        builds from it AND-ed onto ``filters``' own WHERE clause, replacing
        the old OFFSET. ``None`` (the default) means "no cursor position",
        matching this method's own pre-D-2b external behavior."""
        raise NotImplementedError

    def delete(self, collection, filters, audit_hook=None):
        """Returns ``{"deleted": <row count>}``.

        Phase 4 (design D-2/D-10): ``cell.ApplicationCell`` has already
        run this request through the confirmation choke
        (``_validate_delete_confirmation``) before this is ever called --
        ``audit_hook``, when given, is called (``pre_commit()``) as the
        LAST thing this method does before its own commit point. See
        ``audit_hook.py`` for the full call contract."""
        raise NotImplementedError

    def begin(self):
        """Open a multi-statement transaction for ``transact()``."""
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

    def rollback(self):
        raise NotImplementedError

    def insert_in_transaction(self, collection, fields, params):
        """Inserts one row inside the transaction opened by ``begin()``
        (no implicit commit). Returns ``{"rowid": <backend-assigned row
        identifier>}``."""
        raise NotImplementedError

    def update_in_transaction(self, collection, fields, params, filters):
        """P3-D2 (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
        R-5, WP-1.5): updates rows inside the transaction ``begin()``
        already opened (no implicit commit) -- the ``transact()`` batch
        dispatcher's own update branch. Returns ``{"updated": <row
        count>}``."""
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

    # ------------------------------------------------------------------
    # Phase 9 WP-3c (design D-5, 追補 2 S-a/S-b; 監督裁定集約
    # rulings-r5-r6.md I-1): idempotency record storage. `PostgresBackend`
    # keeps these in an application-scoped side table (`_mdb_idempotency`,
    # per-application upgrade 0010); `SQLiteBackend` keeps them in a
    # private, process-local dict (this backend IS the process -- R-a).
    # `ApplicationCell` is the sole caller: it looks these up (`idempotency_
    # get`/`idempotency_reap_expired`/`idempotency_count`) BEFORE it ever
    # calls `begin()`/a schema-mutating method, and writes exactly one
    # (`record_idempotency`) as the LAST thing before its own commit point
    # -- mirroring `audit_hook.pre_commit()`'s own "last thing before
    # commit" placement, so a failed attempt (anything that keeps this
    # backend's own transaction from committing) leaves no record.
    # ------------------------------------------------------------------

    def idempotency_get(self, key):
        """Returns `{"digest": str, "response_json": str}` for `key`, or
        `None` if this Application has no (unexpired) record for it.
        Callers reap expired records first (`idempotency_reap_expired`),
        so a non-`None` result here is always still within its own
        retention window."""
        raise NotImplementedError

    def idempotency_reap_expired(self, now_ms, retention_ms):
        """Deletes every record whose own `created_at_ms` is older than
        `retention_ms` relative to `now_ms` -- lazy reclamation only, no
        background thread/timer anywhere (design D-5: "an implementation
        may delete elapsed records lazily")."""
        raise NotImplementedError

    def idempotency_count(self):
        """Number of records THIS Application currently retains (after
        the caller's own `idempotency_reap_expired` call) -- compared
        against `FoundationConfig.idempotency_entries` at the lookup
        stage, before execution."""
        raise NotImplementedError

    # Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): the two
    # methods below are what `ApplicationCell._idempotency_check`
    # ACTUALLY calls now, replacing direct calls to the three methods
    # above for the SAME purpose. `SQLiteBackend` implements them as
    # thin wrappers over its own `idempotency_reap_expired`/`
    # idempotency_get`/`idempotency_count` above (`for_developer` is
    # accepted and ignored -- no separate connections; `ApplicationCell.
    # _lock`, held by every caller for this method's ENTIRE lookup ->
    # execute -> store window, already serializes concurrent threads).
    # `PostgresBackend` implements them as the fused, locked,
    # SAME-transaction-as-the-eventual-write versions that close F-①'s
    # race for real, and no longer implements the three methods above
    # at all (see `backend_postgres.py`'s own `idempotency_begin`/
    # `idempotency_reserve` docstrings).

    def idempotency_connection(self, *, for_developer=False):
        """Code-review fix F6 (Opus review 2, ruled in -- forward-safety
        for WP-8b pooling): resolves the connection handle THIS request's
        own keyed critical section will use for its ENTIRE idempotency
        lock lifetime. Called EXACTLY ONCE by `cell.py`'s `_idempotency_
        pg_scope`, before `idempotency_begin` ever runs, and the SAME
        returned handle is threaded through `idempotency_begin`/
        `idempotency_reserve`/`idempotency_unlock` as their own `conn`
        argument below -- none of those three methods resolve `self.
        _developer`/`self._runtime` (or an equivalent) themselves any
        more. Without this, `idempotency_unlock` used to re-resolve
        `for_developer` independently, at a LATER point in the request;
        if a future change makes those attributes per-request checkouts
        (a connection pool, WP-8b), that later re-resolution could return
        a DIFFERENT connection than the one that actually took the lock
        -- leaking a session lock onto whatever connection happens to be
        checked out at unlock time, which could ride into a completely
        unrelated FUTURE request. Binding the handle once, at scope-open,
        closes that whole class of bug structurally, before it can exist.
        `for_developer` has the same meaning it always has: `False`
        (default) is `transact`'s own writing connection, `True` is the 3
        DDL methods' own writing connection. `SQLiteBackend` returns
        `None` (no connection concept; every idempotency method below is
        a no-op with respect to this handle on that backend)."""
        raise NotImplementedError

    def idempotency_begin(self, key, now_ms, retention_ms, *, conn, deadline=None):
        """Reaps expired records, then looks up `key`, over `conn` --
        see `idempotency_get`/`idempotency_reap_expired` above for the
        return shape and reclamation rule, both preserved exactly. `conn`
        (code-review fix F6) is the handle `idempotency_connection` above
        returned for this SAME request, at the start of its own keyed
        critical section -- not re-resolved here. `deadline` (code-review
        fix F2, Opus review 2): the SAME wall-clock deadline every other
        backend call on this request already receives (`cell.py`'s own
        `_gate`/`_limit_gate` context managers) -- `PostgresBackend` uses
        it to bound how long this call's own `pg_advisory_lock` may wait
        before giving up, mirroring every other backend method's own `SET
        LOCAL lock_timeout` (`_timeout_ms`/`_set_timeouts`).
        `SQLiteBackend` accepts and ignores both `conn` and `deadline`
        (no connection, no lock either could bound)."""
        raise NotImplementedError

    def idempotency_reserve(self, *, conn, deadline=None):
        """Number of records THIS Application currently retains, after
        `idempotency_begin`'s own reap -- see `idempotency_count` above.
        `conn` (code-review fix F6) must be the SAME handle a paired
        `idempotency_begin` call in this same request just used --
        `idempotency_connection`'s own docstring explains why this is
        passed through rather than re-resolved. `deadline` (code-review
        fix F2): identical meaning and purpose as `idempotency_begin`'s
        own parameter of the same name."""
        raise NotImplementedError

    def idempotency_unlock(self, key, *, conn):
        """Ruling U-7 (WP-6d): releases whatever `idempotency_begin`/
        `idempotency_reserve` locked for `key` in this request -- called
        unconditionally by `ApplicationCell._idempotency_pg_scope` in a
        `finally`, on EVERY exit from a keyed critical section. `conn`
        (code-review fix F6) is the SAME handle `_idempotency_pg_scope`
        obtained from `idempotency_connection` at scope-open and passed
        to `idempotency_begin`/`idempotency_reserve` above -- this method
        unlocks on THAT object, never by re-resolving `for_developer`
        itself (see `idempotency_connection`'s own docstring for why).
        `SQLiteBackend` implements this as a no-op (nothing was locked;
        `conn` is always `None` there). `PostgresBackend` implements it
        as the paired release of the two SESSION-scoped `pg_advisory_
        lock`s those methods take -- see its own docstring for why
        session-, not transaction-, scoped locks are this backend's
        correct realization of ruling U-7."""
        raise NotImplementedError

    def record_idempotency(self, key, digest, response_json, now_ms):
        """Writes (or replaces) one record, over the SAME connection/
        transaction this backend is currently mid-commit on -- called by
        `ApplicationCell.transact` immediately before `self.commit()`.
        A backend method that manages its OWN internal transaction
        (`create_collection`/`add_field`/`alter_field_constraints`) takes
        an `idempotency_record` tuple instead (see each method's own
        docstring) and writes it itself, at the identical "last thing
        before commit" point, over whichever connection that DDL already
        runs on."""
        raise NotImplementedError

    def idempotency_discard_pending(self, key):
        """Phase 9 WP-3cd closure (監督裁定集約 rulings-r5-r6.md K-5, N-8):
        undoes a `record_idempotency` write that turned out NOT to share
        the data's own fate after all -- `ApplicationCell.transact`'s own
        `except Exception:` handler calls this (unconditionally, whenever
        `idempotency_key is not None`) immediately after `self.rollback()`,
        mirroring the identical `self._idempotency.pop(idempotency_record
        [0], None)` cleanup the 3 schema-mutating DDL methods' own
        `except Exception:` blocks already perform. `key` not currently
        pending is a no-op (never raises) -- exactly like those 3 DDL
        methods' own `dict.pop(key, None)`, since the common, ordinary
        case (an EARLIER failure, before `record_idempotency` was ever
        reached) must not raise here either.

        Necessary specifically because `transact`'s own `record_
        idempotency`/`self.commit()` are two SEPARATE calls (unlike the
        DDL methods' own single atomic backend call) -- on `PostgresBackend`
        both already run on the SAME connection/transaction `self.rollback
        ()` undoes together (a real no-op override is correct there); on
        `SQLiteBackend`/the in-memory backend, `record_idempotency` writes
        to a private, NON-transactional process-local dict (R-a) that a
        SUBSEQUENT `self.commit()` failure's own `self.rollback()` cannot
        retroactively undo -- without this method, that specific ordering
        (`record_idempotency` succeeds, `self.commit()` then raises) would
        leak a durable-looking idempotency record for data that was never
        actually committed, so a resend under the SAME key would be
        wrongly answered from that phantom record instead of executing
        fresh."""
        raise NotImplementedError
