"""Application-bound structured data cell.

Each cell owns one storage handle. Sessions never accept an application ID;
the application scope comes from the authenticated Principal and the cell
selected by the service. No database-native command is part of this API.

R-3 seam (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md, WP-1): this
module owns every backend-INDEPENDENT concern -- principal authorization,
request shape/limit validation, identifier syntax validation, capability
declaration (the single source of truth is `ApplicationRuntime.
capabilities()` below), error classification (the `errors.FoundationError`
hierarchy), and declare-and-echo confirmation-phrase construction. Actual
storage EXECUTION is delegated to a `backend.StorageBackend`-shaped object
(`backend_sqlite.SQLiteBackend` -- the default, and the only backend this
WP wires into the public in-process composition -- or
`backend_postgres.PostgresBackend`, exercised directly by
`tests/test_postgres.py`). Swapping which backend answers a given
`ApplicationCell`'s calls is therefore a single-argument change
(`ApplicationCell(..., backend=...)`); this file itself never imports
`sqlite3`/`psycopg` or references either driver's own exception types.
"""

from dataclasses import dataclass
import hashlib
import json
from threading import RLock

from .audit import AuditSink
from .auth import Principal, Role
from .backend import SQL_OPERATOR_TOKENS
from .backend_sqlite import SQLiteBackend
from .config import FoundationConfig
from .errors import (AuthorizationError, CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, NotFoundError,
                     ResourceLimitError, ValidationError)
from .identifiers import validate_identifier

# The common contract's own mutation vocabulary
# (`structured_operations.allowed_mutations`). Of the four names, only
# `upsert` is still refused unconditionally by `transact()` below -- this
# peer has no `upsert` anywhere on its public surface, dedicated method or
# batch alike. Presenting `upsert` to `transact()` is a capability gap in
# this entry point, not a malformed/unrecognized request, so it is
# distinguished from a name outside this vocabulary entirely (still
# `ValidationError`).
#
# P3 WP-1 (round 2 instruction #3), UPDATE by P3-D2 (design v1.2 R-5,
# WP-1.5): this seam refactor originally kept `transact()`'s own
# mixed-batch semantics IDENTICAL to before the refactor -- `update`/
# `delete`/`upsert` were ALL refused unconditionally here, on BOTH
# backends, regardless of what else shared the batch. That was a known,
# tracked, open contract-interpretation question
# (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b): is the contract's
# "A batch is atomic unless explicitly declared best_effort" language
# scoped to whichever operation types a given peer's OWN batch dispatcher
# happens to execute, or to the general mutation vocabulary regardless of
# batch-specific support?) that WP-1 deliberately left open, ordering its
# resolution separately as "WP-1.5". WP-1.5 (P3-D2, design v1.2 second
# round B-2) resolves it for THIS peer by converging real behavior onto
# the existing declaration (`atomic_mutation.operations: ["insert",
# "update", "delete"]`, unchanged by this WP -- no capability envelope
# expansion): `transact()` now executes `update`/`delete` for real,
# atomically with everything else in the same batch, through the
# identical backend-independent validation/confirmation logic the
# dedicated `update`/`delete` methods already use (`_update_in_
# transaction`/`_delete_in_transaction` below, sharing `_bind_filters`/
# `_prepare_values`/`_validate_delete_confirmation` with those methods --
# there is no second, batch-specific copy of any of that logic). Both
# contract readings §8.1(b) considers are therefore simultaneously true
# for this peer post-WP-1.5 (the batch dispatcher itself executes
# update/delete, AND the general vocabulary is executed via a real entry
# point) -- the interpretation question itself is not resolved at the
# contract level (that CCR stays on the tracked-questions ledger for the
# requester), but it no longer has any REAL consequence on this peer,
# because both answers now agree. `upsert` alone remains a real capability
# gap (`CapabilityError`), since no execution path for it exists anywhere
# on this peer, batched or not. The actual EXECUTION each of `insert`/
# `update`/`delete` delegates to (`self._backend.insert_in_transaction`/
# `update_in_transaction`/`delete_in_transaction`) is backend-swappable,
# as it already was for `insert` alone before this WP.
_CONTRACT_MUTATION_VOCABULARY = {"insert", "update", "upsert", "delete"}

# The only operation-dict keys `transact()`'s "insert" branch below actually
# reads. Any other key (`expected_revision`, `idempotency_key`, or any other
# capability this entry point does not implement) must be rejected before
# `_insert_in_transaction` ever touches the database -- silently ignoring an
# unrecognized key would let a request carrying a real semantic (a revision
# precondition, in particular) execute as if that semantic were honored,
# when it was never even inspected. Contract `versioning.unknown_capability`:
# "The service returns CAPABILITY_UNSUPPORTED without executing a fallback."
_TRANSACT_INSERT_KEYS = {"type", "collection", "values"}

# P3-D2 (WP-1.5): same "reject an unread capability-shaped key before
# execution" reasoning as `_TRANSACT_INSERT_KEYS` above, for the two
# newly-converged operation types. `values` is accepted on the "delete"
# key set even though `_delete_in_transaction` never reads it -- contract
# `Mutation` (spec `definitions.Mutation`) declares `values` as a generic
# property of every mutation operation, delete included (no per-operation
# `if`/`then` narrows it away for `"operation": "delete"`), so a
# well-formed delete request naming an empty `values: {}` is ordinary wire
# shape, not a capability-gap signal -- exactly the same treatment r2db-api
# independently gives the identical wire shape for its own delete.
# m-4 (independent review, WP-1.5 follow-up): this is also a real
# IMPLEMENTATION-LEVEL necessity, not merely a contract-shape nicety --
# `conformance/conformance_adapter_mitatedb.py::attempt_batch_with_
# addresses` builds every batch item's `"values"` key unconditionally
# (`dict(op.values or {})`, regardless of `op.operation`), so a `delete`
# BatchOperation ALWAYS carries a `"values"` key on the wire, empty or
# not. If this key set rejected it, the C-06 V2b-wire vector (and
# `_batch_delete_capability_absent`'s own probe) could never reach this
# peer's real batch-delete entry point at all -- accepting `values` here
# is therefore a necessary condition for that adapter's batch-delete path
# to be exercisable, not just a permissive reading of the contract shape.
# Neither key set lists `expected_revision`/`unique_key`: those remain a
# real capability gap on `update`/`delete` here exactly as they already
# are on `insert` above (this peer implements no revision-precondition/
# uniqueness concept anywhere).
_TRANSACT_UPDATE_KEYS = {"type", "collection", "values", "filters"}
_TRANSACT_DELETE_KEYS = {"type", "collection", "values", "filters", "destructive", "confirm"}

# Foundation field-type vocabulary. This is a shared, backend-independent
# VOCABULARY (which declared type names this API accepts at all) -- the
# mapping from one of these names to a backend's own NATIVE column type
# syntax is each backend's own concern (`backend_sqlite._TYPES` /
# `backend_postgres._TYPES`), since the two engines' native type systems
# differ (R-3: execution, including physical schema, is backend-specific;
# only the request-level vocabulary is shared).
_FIELD_TYPE_VOCABULARY = frozenset({"text", "integer", "real", "boolean", "json"})

# Conformance-review finding (WP-5a, C-12 reverse condition): every one of
# these three is a real member of the common contract's own filter-operator
# vocabulary (`structured_operations.allowed_query_operators`) that this
# peer declares `unsupported` in its own `structured_query` capability
# entry below -- `capability_status.rules`: "optional target operations
# ... must fail with CAPABILITY_UNSUPPORTED". `matches` already raised
# `CapabilityError` correctly; `contains`/`is_null` used to fall through to
# the generic "not a filter operator this peer implements at all" branch
# below and raise `ValidationError` (-> `VALIDATION_FAILED`) instead -- a
# real, observable mismatch between this peer's own declaration and its
# own behavior, discovered by the common conformance suite's C-12 reverse
# direction (`conformance-tests/test_c12_capability_agreement.py`)
# presenting a real, contract-shaped request rather than assuming this
# peer's behavior. All three now share one code path in `_bind_filters`
# below.
_UNSUPPORTED_CONTRACT_OPERATORS = {"contains", "matches", "is_null"}

# WP-5 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5, contract
# `destructive_confirmation`): declare-and-echo confirmation for `delete`,
# this peer's only destructive operation (`drop_entity`/`drop_index` are
# `SurfaceAbsent` -- `create_collection` has no drop parameter anywhere on
# this peer's public surface -- and `revoke_credential`'s "last control
# credential" gate is a control-plane concept this peer's provisioning
# facade does not implement at all, per its own `control_plane:
# unavailable` capability declaration).
#
# P3 WP-1 (round 2 instruction #5) UPDATE: the paragraph immediately below
# this one used to conclude that NO state fingerprint was needed in the
# delete phrase, on the strength of this peer having no way to mutate an
# existing collection's shape at all. `add_field` (this same WP) breaks
# that premise directly -- it IS "another schema change" on an existing
# collection, the exact dimension the original argument depended on being
# absent. The phrase construction below therefore now DOES include a
# state fingerprint (`@schema_revision=<n>`, `_delete_confirmation_phrase`),
# bumped by both `create_collection` and `add_field` (`backend.
# StorageBackend.schema_revision`/each backend's own bump-on-DDL) -- the
# same shape as r2db-api's own Q1-D10 answer to an analogous question for
# ITS OWN, different, real capability (that peer's own drop+recreate of an
# entity under the same name), independently arrived at here for a
# different real capability (`add_field`) reaching the same underlying
# risk (a delete confirmation issued against one schema shape, then
# replayed after the schema changed underneath it). Contract
# `phrase_construction` does not fix the phrase's own spelling (Q1-D2), so
# adding this segment is not a compatibility break.
#
# ORIGINAL REASONING (kept for its own continuing scope -- collection
# EXISTENCE/RE-CREATION, as opposed to an existing collection's shape):
# this peer still has no `drop_entity`/`drop_collection` of any kind
# (`create_collection` raises `ConflictError` if the name already exists,
# and there is no `drop_entity` anywhere on this peer's public surface --
# confirmed by source inspection: `capabilities().schema_operations.
# unsupported` lists `drop_entity` itself), so a collection can still never
# be dropped and recreated under the same name for the rest of this
# process's lifetime -- unlike r2db-api's own re-creatable entities, which
# is what Q1-D10 was originally answering. The schema-revision fingerprint
# added by this WP subsumes that concern anyway (a collection's own
# revision only ever increases; there is no operation on this peer that
# could make an old revision number become live again).
_DELETE_CONSEQUENCE = (
    "The rows matching this delete's filters are permanently removed from "
    "the collection; there is no in-band restore path."
)
# No reversible_alternative and no recovery for the same reason r2db-api's
# OWN data-plane delete declares both null (Q1-D6): this peer has no
# durable, queryable audit trail an operator could use to reconstruct
# removed rows, and no soft-delete/undo mechanism of any kind -- claiming
# either would be untrue.


def _canonical_where_json(filters):
    """Canonical JSON serialization of a `delete` request's own selection
    (contract `phrase_construction` rule "scope-included"): each `Filter`
    becomes a key-sorted object; the outer list's own ORDER is preserved,
    not sorted (an intentional choice, matching r2db-api's own documented
    n-6 finding: two requests presenting the identical predicate set in a
    different order are treated as different requests, not folded onto one
    phrase -- this peer does not treat where-clause order as insignificant
    on the caller's behalf).

    Deliberately no `default=str` (r2db-api WP-3 followup m-7): every
    `Filter.value` reaching this point has already passed `_bind_filters`'s
    own `ApplicationCell._normalize_value` (dict/list/bool/str/int/float/
    None only, raising `ValidationError` for anything else) by
    construction -- `delete` below always calls this on the caller's own,
    un-encoded `filters` argument BEFORE `_bind_filters` runs, but the same
    shape guarantee already holds because `delete` requires `filters` be a
    non-empty list of `Filter` instances first -- so a value this
    `json.dumps` cannot serialize natively would mean that invariant broke
    elsewhere; surfacing that as an immediate `TypeError` here is more
    honest than silently collapsing it into a string that could coincide
    with a different value's own string form.
    """
    payload = [{"field": f.field, "operator": f.operator, "value": f.value} for f in filters]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _delete_confirmation_phrase(collection, filters, schema_revision):
    """`DELETE <collection> @where=<digest16> @schema_revision=<n>` --
    digest16 is the first 16 hex characters of the SHA-256 of
    `_canonical_where_json(filters)`; `schema_revision` is this
    application's current schema-revision counter (P3 WP-1 round 2
    instruction #5 -- see the module-level comment above
    `_DELETE_CONSEQUENCE` for why this was added). `collection` must
    already be identifier-validated by the caller (contract
    `phrase_construction` rule "only identifier-validated target names")
    -- `ApplicationCell.delete` below always calls this only after
    `ApplicationCell._identifier(collection, ...)` has succeeded.

    Length: identifiers are bounded to 63 characters
    (`identifiers._IDENTIFIER`), so `"DELETE " (7) + collection (63) +
    " @where=" (8) + digest16 (16) = 94` (the original, pre-schema-
    revision proof) `+ " @schema_revision=" (18) + digits(schema_revision)`.
    `schema_revision` is a plain, monotonically-increasing non-negative
    counter incremented once per `create_collection`/`add_field` call this
    process ever makes -- bounding its own decimal digit count to 144
    (`94 + 18 + 144 = 256`, exactly the contract `confirmation` field's own
    `maxLength`) covers every value up to `10**144`, a number of schema
    mutations no real process could ever perform (bounded, in this
    foundation, by `FoundationConfig.max_schema_objects`/`max_fields`
    per application in the first place) -- so the bounded-digest escape
    hatch contract `phrase_construction` rule "bounded" describes is never
    actually needed on this peer, exactly as the original (pre-schema-
    revision) proof already concluded. n-1 correction (independent
    review, carried forward unchanged): the `assert` below is NOT itself
    what proves this invariant -- `assert` statements are stripped
    entirely when Python runs under `-O`/`PYTHONOPTIMIZE`, so it must
    never be the only thing standing between this function and an
    over-length phrase. The real proof is the arithmetic above; the assert
    is a development-time backstop that fixes this reasoning in an
    executable form, not a substitute for it, and not load-bearing under
    `-O`.
    """
    digest = hashlib.sha256(_canonical_where_json(filters).encode("utf-8")).hexdigest()[:16]
    phrase = "DELETE " + collection + " @where=" + digest + " @schema_revision=" + str(schema_revision)
    assert len(phrase) <= 256, "delete confirmation phrase exceeds contract confirmation maxLength"
    return phrase


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: object


class ApplicationCell:
    """A private application storage boundary.

    The default backend (`backend_sqlite.SQLiteBackend`) is used only as a
    deterministic local foundation backend. `backend_postgres.
    PostgresBackend` is the production-shaped Cloud SQL adapter (WP-1);
    both keep this class's own authority shape identical, never exposing a
    raw database connection to Application code.
    """

    def __init__(self, application_id, config=None, audit=None, guard=None, backend=None):
        validate_identifier(application_id, "application_id")
        self.application_id = application_id
        self.config = config or FoundationConfig()
        self.__record = (audit or AuditSink()).record
        self.__guard = guard
        self._backend = backend if backend is not None else SQLiteBackend()
        # Back-compat surface for `conformance/conformance_adapter_
        # mitatedb.py::entities()`'s own pre-existing direct `cell._db.
        # execute(...)` reach-around (predates this WP's seam refactor;
        # that adapter is unaffected by this WP and keeps working
        # unchanged because `SQLiteBackend.raw_connection` republishes the
        # exact same `sqlite3.Connection` this attribute used to hold
        # directly). Backends with no such raw handle (`PostgresBackend`)
        # leave this `None` -- nothing in this WP relies on it for that
        # backend.
        self._db = getattr(self._backend, "raw_connection", None)
        self._lock = RLock()

    def _identifier(self, value, label="identifier"):
        """The one place BOTH stages of identifier validation are always
        applied together (R-3): the shared syntax allowlist
        (`identifiers.validate_identifier`), then this cell's own active
        backend's reserved-name check (`backend.StorageBackend.
        check_reserved` -- backend-specific: SQLite's own `sqlite_
        sequence`/PostgreSQL's own `pg_`-prefixed catalog namespace mean
        nothing to the other engine, R-3 WP-0 m-7)."""
        validate_identifier(value, label)
        self._backend.check_reserved(value, label)
        return value

    def create_collection(self, principal, name, fields, destructive=False):
        self._require_developer(principal)
        name = self._identifier(name, "collection")
        if not isinstance(fields, dict) or not fields:
            raise ValidationError("fields must be a non-empty object")
        if len(fields) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7, supersedes the WP-5 body's own
            # `query_complexity` tagging): this bounds how many columns a
            # single collection DEFINITION may name in one `create_
            # collection` call -- a one-time shape bound on the request
            # itself, not a repeated, finite-resource consumption class.
            raise ValidationError("field limit exceeded")
        if self._backend.schema_count() >= self.config.max_schema_objects:
            raise ResourceLimitError("schema object limit exceeded", limit_class="schema_objects")
        validated_fields = {}
        for field, field_type in fields.items():
            field = self._identifier(field, "field")
            if field_type not in _FIELD_TYPE_VOCABULARY:
                raise ValidationError("unsupported field type")
            validated_fields[field] = field_type
        with self._lock:
            self._backend.create_collection(name, validated_fields)
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="create_collection")

    def create_entity(self, principal, name, fields=None):
        """Wire-shaped counterpart of `create_collection`, matching
        contract `SchemaOperationRequest`'s own OPTIONAL `fields` (P3 WP-1
        round 2 instruction #6): `SchemaOperationRequest` allows `fields`
        to be omitted for `create_entity` (present-time `minItems: 1`
        only constrains it when it IS supplied). This foundation has no
        row-addressability concept to build a genuinely columnless table
        around (`row_addressability: unavailable`, unchanged by this WP),
        so an omitted `fields` is accepted as "an entity carrying only a
        base identity column" -- realized here as the narrowest concrete
        shape this foundation already has a real, tested meaning for: a
        single `id: integer` field, via the SAME `create_collection` path
        every other shape uses (no new backend primitive, no new column
        concept). This is a NEW, ADDITIONAL method -- `create_collection`
        itself keeps rejecting an empty/missing `fields` outright
        (`ValidationError`) for every existing caller (direct foundation
        use, the in-process conformance adapter, `tests/test_foundation.
        py`); nothing about its own behavior changes.
        """
        if fields is None:
            fields = {"id": "integer"}
        return self.create_collection(principal, name, fields)

    def add_field(self, principal, collection, field, field_type):
        """P3-D1 (design v1.1 §0 exception, WP-1): the one capability-
        envelope addition this phase makes -- `schema_operations.add_field`,
        developer-only, on BOTH backends (declaration and implementation
        land in this same commit). Adds one column to an EXISTING
        collection; see the module-level comment above `_DELETE_
        CONSEQUENCE` for why this is also what makes a schema-revision
        fingerprint necessary in the `delete` confirmation phrase.
        """
        self._require_developer(principal)
        collection = self._identifier(collection, "collection")
        field = self._identifier(field, "field")
        if field_type not in _FIELD_TYPE_VOCABULARY:
            raise ValidationError("unsupported field type")
        # Q1-D11-consistent shape bound (same reasoning as `create_
        # collection`'s own field-count check above): the total column
        # count this collection would carry AFTER this call mirrors the
        # same fixed contract shape dimension `max_fields` already gates
        # at definition time -- not a repeated, finite-resource
        # consumption class, so `ValidationError`, not `ResourceLimitError`
        # (keeps `test_limit_class_vocabulary.py`'s own AST-scanned
        # `ResourceLimitError` call-site count unaffected by this WP).
        current = self._backend.field_domains(collection)  # NotFoundError if `collection` does not exist
        if len(current) >= self.config.max_fields:
            raise ValidationError("field limit exceeded")
        with self._lock:
            self._backend.add_field(collection, field, field_type)  # ConflictError if `field` already exists
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="add_field")

    def schema_revision(self, principal):
        """m-2 (independent WP-3 review): the SAME monotonically-increasing
        counter `_validate_delete_confirmation` already reads to fingerprint
        a delete confirmation phrase (`_delete_confirmation_phrase`), now
        also exposed as a read-only, authorized query -- so the HTTP
        surface's `SchemaOperationResult.revision` field can report this
        peer's REAL current schema-revision value after a `create_entity`/
        `add_field` call, rather than a hardcoded placeholder that would
        never actually change (a false declaration: the contract's own
        `SchemaOperationResult.revision` field implies a real, observable
        value, and always returning the same literal after every schema
        change is not honest about what the peer just did)."""
        self._require_data(principal)
        with self._lock:
            return self._backend.schema_revision()

    def insert(self, principal, collection, values):
        self._require_data(principal)
        collection, fields, params = self._prepare_values(collection, values)
        with self._lock:
            return self._backend.insert(collection, fields, params)

    def read(self, principal, collection, fields=None, filters=None,
             order_by=None, limit=None):
        self._require_data(principal)
        collection = self._identifier(collection, "collection")
        selected = self._select_fields(collection, fields)
        bound_filters = self._bind_filters(collection, filters)
        order = self._bind_order_by(collection, order_by)
        if limit is None:
            limit = self.config.max_result_rows
        if not isinstance(limit, int) or limit <= 0 or limit > self.config.max_result_rows:
            raise ResourceLimitError("result limit exceeded", limit_class="result_items")
        with self._lock:
            return self._backend.read(collection, selected, bound_filters, order, limit)

    def _validate_update(self, collection, values, filters):
        """m-1 (independent review, P3-D2 follow-up): the single choke
        BOTH `ApplicationCell.update` below AND `transact()`'s own
        batch-embedded update branch (`_update_in_transaction`) pass
        through -- identical four-step validation (non-empty `filters`
        shape check -> `_prepare_values` -> non-empty `fields` check ->
        `_bind_filters`), so a batch-embedded update is held to exactly
        the same mass-operation guard as the dedicated method, never a
        looser one. Mirrors `_validate_delete_confirmation`'s own role for
        `delete` -- there is no second definition of this validation
        anywhere in this file.

        Returns `(collection, fields, values_params, bound_filters)` on
        success. Does not execute the update itself and does not touch
        `self._lock`/the backend's own transaction state -- callers own
        both, same division of responsibility as
        `_validate_delete_confirmation`.
        """
        if not isinstance(filters, list) or not filters:
            raise ValidationError("update requires non-empty filters")
        collection, fields, values_params = self._prepare_values(collection, values)
        if not fields:
            raise ValidationError("values must be non-empty")
        bound_filters = self._bind_filters(collection, filters)
        return collection, fields, values_params, bound_filters

    def update(self, principal, collection, values, filters):
        self._require_data(principal)
        collection, fields, values_params, bound_filters = self._validate_update(collection, values, filters)
        with self._lock:
            return self._backend.update(collection, fields, values_params, bound_filters)

    def _validate_delete_confirmation(self, collection, filters, destructive, confirm):
        """P3-D2 (design v1.2 R-5, WP-1.5): the single choke BOTH
        `ApplicationCell.delete` below AND `transact()`'s own
        batch-embedded delete branch (`_delete_in_transaction`) pass
        through -- identical shape checks, identical schema-revision-
        fingerprinted phrase construction (`_delete_confirmation_phrase`),
        identical exact-match comparison, identical four-key `details`
        shape on failure. A batch-embedded delete is therefore held to
        EXACTLY the same declare-and-echo requirement as the dedicated
        method, never a looser one -- there is no second, batch-specific
        copy of this logic anywhere in this file.

        `destructive` missing is equivalent to `False` (contract
        `valid_confirmation`); a valid confirmation requires BOTH
        `destructive is True` AND `confirm` to exactly equal the server's
        own currently-recomputed `required_confirmation` for this exact
        request (Unicode code point sequence, no normalization -- a plain
        `!=` string comparison already has this property). A non-bool
        `destructive`/non-str `confirm` is a shape defect
        (`ValidationError`), not a confirmation mismatch -- truthy
        acceptance of either is exactly the defect WP-0/WP-3's own B-1
        finding (r2db-api) forbids, applied here identically (WP-5 R-5).

        Returns `(collection, bound_filters)` on success; raises
        `DestructiveConfirmationRequired` otherwise. Does not execute the
        delete itself and does not touch `self._lock`/the backend's own
        transaction state -- callers own both (the dedicated method wraps
        its own `with self._lock:`/no open batch transaction; `transact()`
        is already holding `self._lock` and has already called
        `self._backend.begin()` before this is ever reached).
        """
        if not isinstance(destructive, bool):
            raise ValidationError("destructive must be a boolean")
        if confirm is not None and not isinstance(confirm, str):
            raise ValidationError("confirm must be a string")
        # B-3 (WP-0/WP-5): identifier + filter-shape validation (which,
        # via `_bind_filters`'s own `field_domains` call, also performs the
        # contract's own "target-existence checks" step) must complete
        # BEFORE the confirmation check below -- a phrase must never
        # reflect an unvalidated client-supplied collection name back to
        # the client, and evaluation_order requires target existence to be
        # settled before confirmation validity is evaluated.
        collection = self._identifier(collection, "collection")
        if not isinstance(filters, list) or not filters:
            raise ValidationError("delete requires non-empty filters")
        bound_filters = self._bind_filters(collection, filters)
        schema_revision = self._backend.schema_revision()
        phrase = _delete_confirmation_phrase(collection, filters, schema_revision)
        if destructive is not True or confirm != phrase:
            raise DestructiveConfirmationRequired(
                "destructive operation requires the current confirmation phrase",
                details={
                    "required_confirmation": phrase,
                    "consequence": _DELETE_CONSEQUENCE,
                    "reversible_alternative": None,
                    "recovery": None,
                },
            )
        return collection, bound_filters

    def delete(self, principal, collection, filters, *, destructive=False, confirm=None):
        """Contract `destructive_confirmation`: `delete` is this peer's
        only destructive operation (see the module-level comment above
        `_DELETE_CONSEQUENCE` for why `drop_entity`/`drop_index`/the
        control-plane revoke gate are all structurally absent here, not
        merely unimplemented). See `_validate_delete_confirmation` above
        for the actual confirmation semantics -- shared verbatim with
        `transact()`'s own batch-embedded delete (P3-D2, WP-1.5).
        """
        self._require_data(principal)
        collection, bound_filters = self._validate_delete_confirmation(
            collection, filters, destructive, confirm)
        with self._lock:
            result = self._backend.delete(collection, bound_filters)
        self.__record("destructive_data_operation", self.application_id,
                      principal.credential_id, detail="delete_rows")
        return result

    def transact(self, principal, operations):
        """P3-D2 (design v1.2 R-5, WP-1.5): `insert`/`update`/`delete` all
        execute for real here, atomically with everything else in the
        same batch -- converging this entry point's real behavior onto
        the existing `atomic_mutation.operations` declaration (unchanged
        by this WP). `upsert` alone remains a real capability gap: no
        execution path for it exists anywhere on this peer.

        The whole batch commits or rolls back as one unit (contract "A
        batch is atomic unless explicitly declared best_effort" --
        `best_effort_transactions: unavailable`, unchanged): a mid-batch
        failure of ANY kind (a shape defect, a missing/wrong destructive
        confirmation, a unique-constraint conflict, a collection that does
        not exist) discards every write already performed earlier in the
        SAME batch, insert included -- `self._backend.rollback()` in the
        `except` clause below is the one and only rollback point for the
        whole batch, reached from every operation type's own failure path.
        """
        self._require_data(principal)
        if not isinstance(operations, list) or not operations:
            raise ValidationError("operations must be a non-empty list")
        if len(operations) > self.config.max_batch_items:
            raise ResourceLimitError("batch limit exceeded", limit_class="batch_items")
        with self._lock:
            self._backend.begin()
            # A batch-embedded delete's own `destructive_data_operation`
            # audit record must never claim a write that a LATER operation
            # in the same batch caused to roll back -- so recording is
            # deferred to these no-argument callables, drained only after
            # `self._backend.commit()` below has actually succeeded (the
            # dedicated `delete()` method above has no such concern: it
            # owns its own, single-operation transaction end-to-end, so it
            # records immediately after its own successful backend call).
            pending_audit = []
            try:
                results = []
                for operation in operations:
                    if not isinstance(operation, dict):
                        raise ValidationError("unsupported transaction operation")
                    op_type = operation.get("type")
                    if op_type == "insert":
                        if set(operation) - _TRANSACT_INSERT_KEYS:
                            # A well-formed "insert" carrying an extra,
                            # unrecognized key (e.g. `expected_revision`) is
                            # a capability gap, not a malformed request --
                            # same reasoning as the `update`/`delete`
                            # branches below, and the `upsert` branch
                            # further down, which refuse this way for the
                            # operation *type* itself.
                            raise CapabilityError(
                                "transact does not support additional fields on operation type 'insert'"
                            )
                        results.append(self._insert_in_transaction(operation["collection"], operation["values"]))
                        continue
                    if op_type == "update":
                        if set(operation) - _TRANSACT_UPDATE_KEYS:
                            raise CapabilityError(
                                "transact does not support additional fields on operation type 'update'"
                            )
                        results.append(self._update_in_transaction(
                            operation.get("collection"), operation.get("values"), operation.get("filters")))
                        continue
                    if op_type == "delete":
                        if set(operation) - _TRANSACT_DELETE_KEYS:
                            raise CapabilityError(
                                "transact does not support additional fields on operation type 'delete'"
                            )
                        results.append(self._delete_in_transaction(
                            operation.get("collection"), operation.get("filters"),
                            destructive=operation.get("destructive", False),
                            confirm=operation.get("confirm")))
                        # Deferred audit (see `pending_audit`'s own comment
                        # above): appended only once `_delete_in_transaction`
                        # has returned successfully for THIS operation --
                        # `principal` is this method's own parameter, still
                        # in scope here, so no extra plumbing into the
                        # helper itself is needed to capture it.
                        pending_audit.append(lambda: self.__record(
                            "destructive_data_operation", self.application_id,
                            principal.credential_id, detail="delete_rows"))
                        continue
                    if op_type in _CONTRACT_MUTATION_VOCABULARY:
                        # Only "upsert" ever reaches here now -- P3-D2
                        # converged `update`/`delete` to real execution
                        # above. Per `capability_status.rules` ("optional
                        # target operations ... must fail with
                        # CAPABILITY_UNSUPPORTED"), this is a capability
                        # gap, not a malformed request.
                        raise CapabilityError(f"transact does not support operation type {op_type!r}")
                    raise ValidationError("unsupported transaction operation")
                self._backend.commit()
            except (ValidationError, ResourceLimitError, CapabilityError,
                     DestructiveConfirmationRequired, ConflictError, NotFoundError):
                # P3-D2 (WP-1.5): `DestructiveConfirmationRequired` is now a
                # REAL, reachable outcome of this loop (a batch-embedded
                # delete missing/mismatching its own confirmation) -- no
                # longer merely a defensive listing for a hypothetical
                # future capability, as it was before this WP.
                # `ConflictError`/`NotFoundError` are raised by the active
                # backend itself (a unique-constraint conflict / a
                # collection dropped out from under this transaction) --
                # R-3: this file no longer names any backend-native
                # exception type at all, since every backend now translates
                # its own low-level failures into this shared
                # `errors.FoundationError` vocabulary before this `except`
                # clause ever sees them. `pending_audit` is simply
                # discarded here (never drained) -- correct, since nothing
                # in it actually committed.
                self._backend.rollback()
                raise
            for record in pending_audit:
                record()
            return results

    def _insert_in_transaction(self, collection, values):
        collection, fields, params = self._prepare_values(collection, values)
        return self._backend.insert_in_transaction(collection, fields, params)

    def _update_in_transaction(self, collection, values, filters):
        """P3-D2 (WP-1.5), m-1 fix: runs the identical validation choke
        `ApplicationCell.update` uses (`_validate_update`), then executes
        through the backend's own in-transaction update (no per-operation
        commit -- `transact()`'s single `commit()`/`rollback()` covers the
        whole batch). No second definition of update's own validation
        logic exists anywhere in this file."""
        collection, fields, values_params, bound_filters = self._validate_update(collection, values, filters)
        return self._backend.update_in_transaction(collection, fields, values_params, bound_filters)

    def _delete_in_transaction(self, collection, filters, *, destructive, confirm):
        """P3-D2 (WP-1.5): runs the identical confirmation choke
        `ApplicationCell.delete` uses (`_validate_delete_confirmation`),
        then executes through the backend's own in-transaction delete (no
        per-operation commit -- `transact()`'s single `commit()`/
        `rollback()` covers the whole batch). Audit recording for this
        delete is the CALLER's own concern (`transact()` appends to its
        own `pending_audit` list only after this returns successfully) --
        see `transact()`'s own comment above that list's declaration for
        why recording must be deferred past the batch's own commit."""
        collection, bound_filters = self._validate_delete_confirmation(
            collection, filters, destructive, confirm)
        return self._backend.delete_in_transaction(collection, bound_filters)

    def _select_fields(self, collection, requested):
        available = self._backend.field_domains(collection)
        if requested is None:
            return list(available)
        if not isinstance(requested, list) or not requested:
            raise ValidationError("fields must be a non-empty list")
        if len(requested) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): read-projection width is a shape
            # bound on the request's own `fields` list, mirroring contract
            # `QueryRequest.select.maxItems`.
            raise ValidationError("field limit exceeded")
        result = []
        for field in requested:
            field = self._identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            result.append(field)
        return result

    # WP-3 (design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2
    # R-5/§2): the HTTP `/v1/data/{entity}/query` endpoint maps contract
    # `QueryRequest.order_by` -- an ARRAY of `Order` objects
    # (`definitions.Order`, `maxItems: 10`), i.e. multi-field sort -- onto
    # this seam. `_bind_order_by` therefore accepts three shapes and always
    # returns either `None` or a non-empty LIST of `(field, direction)`
    # tuples (never a bare tuple any more): `None` (no ordering), a single
    # `{"field": ..., "direction": ...}` object (the pre-WP-3 shape --
    # `tests/test_postgres.py`'s own existing call and every other
    # pre-existing caller keep working unchanged, now normalized to a
    # one-element list internally), or a list of such objects (the new,
    # contract-shaped multi-field form). Both backends' own `read()` were
    # updated in the same commit to consume this unified list-or-None
    # shape (`backend_sqlite.py`/`backend_postgres.py`).
    _MAX_ORDER_BY_TERMS = 10  # mirrors contract `definitions.QueryRequest.order_by.maxItems`

    def _bind_order_by(self, collection, order_by):
        if order_by is None:
            return None
        if isinstance(order_by, dict):
            order_by = [order_by]
        if not isinstance(order_by, list) or not order_by:
            raise ValidationError("order_by must be an object or a non-empty list of objects")
        if len(order_by) > self._MAX_ORDER_BY_TERMS:
            raise ValidationError("order_by term limit exceeded")
        available = self._backend.field_domains(collection)
        bound = []
        for item in order_by:
            if not isinstance(item, dict):
                raise ValidationError("order_by must be an object or a non-empty list of objects")
            field = self._identifier(item.get("field"), "order field")
            if field not in available:
                raise ValidationError("unknown order field")
            direction = item.get("direction", "asc")
            if direction not in ("asc", "desc"):
                raise ValidationError("invalid order direction")
            bound.append((field, direction))
        return bound

    def _prepare_values(self, collection, values):
        collection = self._identifier(collection, "collection")
        available = self._backend.field_domains(collection)
        if not isinstance(values, dict) or not values:
            raise ValidationError("values must be a non-empty object")
        if len(values) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): write-payload width (insert/update/
            # transact-insert) mirrors contract `Mutation.values.
            # maxProperties: 100` directly.
            raise ValidationError("field limit exceeded")
        fields = []
        params = []
        for field, value in values.items():
            field = self._identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            fields.append(field)
            # B-1 (independent review round 2): `available[field]` is this
            # field's own value-domain category from the active backend's
            # live catalog (`None` on SQLite -- domain validation skipped
            # there, matching its own unchanged external behavior) --
            # passed through so a type-mismatched value (e.g. a string for
            # a declared-`integer` column) is rejected deterministically
            # here, before any statement reaches PostgreSQL.
            params.append(self._backend.encode_value(self._normalize_value(value), domain=available[field]))
        return collection, fields, params

    def _bind_filters(self, collection, filters):
        if filters is None:
            return []
        if not isinstance(filters, list) or len(filters) > self.config.max_filter_terms:
            # Clean 1:1 correspondence: this is the same shape dimension
            # r2db-api's own `query_complexity` metric folds `len(where)`
            # into, and `capabilities()` below publishes this exact bound
            # (`config.max_filter_terms`) under the `query_complexity` key.
            raise ResourceLimitError("filter limit exceeded", limit_class="query_complexity")
        available = self._backend.field_domains(collection)
        bound = []
        for item in filters:
            if not isinstance(item, Filter):
                raise ValidationError("filters must contain Filter values")
            field = self._identifier(item.field, "filter field")
            if item.operator in _UNSUPPORTED_CONTRACT_OPERATORS:
                # Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication): `contains`/
                # `matches`/`is_null` are real members of the common
                # contract's own filter-operator vocabulary but this peer
                # simply does not execute any of the three -- a positive,
                # honest refusal (`CapabilityError`), checked ahead of the
                # field-existence check below (a refusal this
                # unconditional must not depend on whether the named field
                # happens to exist).
                raise CapabilityError(f"{item.operator} is not supported by this foundation")
            if field not in available:
                raise ValidationError("invalid filter")
            if item.operator not in SQL_OPERATOR_TOKENS:
                # A genuinely unrecognized operator string, outside the
                # common contract's vocabulary entirely (every contract
                # member this peer does not implement is handled by the
                # `_UNSUPPORTED_CONTRACT_OPERATORS` branch above instead).
                raise ValidationError("invalid filter")
            if item.operator == "in":
                if not isinstance(item.value, list) or not item.value:
                    raise ValidationError("in filter requires values")
                if len(item.value) > self.config.max_batch_items:
                    # Reuses `config.max_batch_items` itself (not a
                    # separate `max_filter_terms`-style bound).
                    raise ResourceLimitError("filter value limit exceeded", limit_class="batch_items")
                # B-1: every element compares against the SAME column, so
                # they all share that column's own domain.
                domain = available[field]
                encoded = [self._backend.encode_value(self._normalize_value(v), domain=domain) for v in item.value]
                bound.append(Filter(field, "in", encoded))
            else:
                encoded = self._backend.encode_value(self._normalize_value(item.value), domain=available[field])
                bound.append(Filter(field, item.operator, encoded))
        return bound

    @staticmethod
    def _normalize_value(value):
        """Backend-independent shape check/normalization (R-3): a
        dict/list value becomes canonical JSON text; every other accepted
        Python type (`bool`/`str`/`int`/`float`/`None`) passes through
        unchanged for the active backend's own `encode_value` to finish
        (backend-specific bind encoding AND backend-specific value-domain
        validation, e.g. PostgreSQL's embedded-NUL rejection -- see
        `backend_postgres.PostgresBackend.encode_value`)."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        if isinstance(value, (bool, str, int, float)) or value is None:
            return value
        raise ValidationError("unsupported value")

    def _require_data(self, principal):
        if self.__guard is not None:
            self.__guard(principal)
        if not isinstance(principal, Principal) or principal.application_id != self.application_id:
            raise AuthorizationError("application scope denied")
        if principal.role not in (Role.RUNTIME, Role.DEVELOPER):
            raise AuthorizationError("role denied")

    def _require_developer(self, principal):
        self._require_data(principal)
        if principal.role != Role.DEVELOPER:
            self.__record("authorization_denied", self.application_id,
                          getattr(principal, "credential_id", None),
                          outcome="denied", detail="schema_change")
            raise AuthorizationError("developer authority required")


class ApplicationRuntime:
    """Runtime data authority; schema mutation is intentionally absent."""

    __slots__ = ("__cell", "__principal", "__guard")

    def __init__(self, cell, principal, guard=None):
        cell._require_data(principal)
        self.__cell, self.__principal, self.__guard = cell, principal, guard

    @property
    def principal(self):
        return self.__principal

    def __authorize(self):
        if self.__guard is not None:
            self.__guard(self.__principal)

    def schema_revision(self):
        self.__authorize()
        return self.__cell.schema_revision(self.__principal)

    def insert(self, collection, values):
        self.__authorize()
        return self.__cell.insert(self.__principal, collection, values)

    def read(self, collection, fields=None, filters=None, order_by=None, limit=None):
        self.__authorize()
        return self.__cell.read(self.__principal, collection, fields, filters, order_by, limit)

    def update(self, collection, values, filters):
        self.__authorize()
        return self.__cell.update(self.__principal, collection, values, filters)

    def delete(self, collection, filters, *, destructive=False, confirm=None):
        self.__authorize()
        return self.__cell.delete(self.__principal, collection, filters,
                                  destructive=destructive, confirm=confirm)

    def transact(self, operations):
        self.__authorize()
        return self.__cell.transact(self.__principal, operations)

    def capabilities(self):
        """Minimal capability/discovery document, per this session's own
        server-bound scope. Statuses reflect what this foundation actually
        executes today, not the common contract's peer-target surface: an
        operation this foundation cannot run is never advertised "enabled"
        (spec `capability_status.rules`).

        This is the single source of truth for this peer's declared
        capability document (R-3): both the SQLite-backed in-process
        composition and the PostgreSQL-backed composition
        (`tests/test_postgres.py`) share this exact method -- there is no
        second copy anywhere that could drift out of agreement with it.
        """
        self.__authorize()
        principal = self.__principal
        is_developer = principal.role == Role.DEVELOPER
        config = self.__cell.config
        return {
            "contract_version": "1.2.0",
            "capabilities": {
                "structured_query": {"status": "partial", "operators": list(SQL_OPERATOR_TOKENS), "unsupported": ["contains", "matches", "is_null"]},
                "atomic_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
                # No public "list collections" operation exists on this peer.
                "application_catalog": {"status": "unavailable"},
                # P3-D1 (design v1.1 §0 exception, WP-1): `add_field` is
                # now a real, developer-only, executed capability on both
                # backends -- declaration and implementation land in this
                # same commit (design v1.1 principle: "宣言と実挙動は単一
                # コミットでしか同時に動かさない").
                "schema_operations": {"status": "partial", "operations": ["create_entity", "add_field"] if is_developer else [], "unsupported": ["alter_field", "create_index", "drop_index", "drop_entity", "jobs"]},
                "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                "best_effort_transactions": {"status": "unavailable"},
                "idempotency": {"status": "unavailable"},
                "revision_preconditions": {"status": "unavailable"},
                "row_addressability": {"status": "unavailable"},
                "cross_entity_mutation": {"status": "unavailable"},
                "control_plane": {"status": "unavailable"}
            },
            "limits": {
                "batch_items": config.max_batch_items,
                "result_items": config.max_result_rows,
                "query_complexity": config.max_filter_terms,
                "request_bytes": config.max_request_bytes,
                "schema_objects": config.max_schema_objects
            },
            "limit_enforcement": {
                "batch_items": "enforced",
                "result_items": "enforced",
                "query_complexity": "enforced",
                # `FoundationConfig.validate_request_size` exists but is not
                # wired into any request path yet (no caller in `cell.py` /
                # `service.py`): reporting "enforced" here would be false.
                "request_bytes": "unavailable",
                "schema_objects": "enforced"
            },
            # `CredentialStore.assert_active` (auth.py) is invoked by
            # `__authorize` above on every single session operation, with
            # no cache: revoke/disable/state-unavailable propagation is
            # synchronous.
            "authorization_propagation_bound_ms": 0,
            "application_scope": principal.application_id,
            "role": principal.role.value
        }


class ApplicationDeveloper(ApplicationRuntime):
    """Developer authority adds structured schema operations only."""

    def create_collection(self, name, fields):
        self._ApplicationRuntime__authorize()
        return self._ApplicationRuntime__cell.create_collection(
            self._ApplicationRuntime__principal, name, fields)

    def create_entity(self, name, fields=None):
        self._ApplicationRuntime__authorize()
        return self._ApplicationRuntime__cell.create_entity(
            self._ApplicationRuntime__principal, name, fields)

    def add_field(self, collection, field, field_type):
        self._ApplicationRuntime__authorize()
        return self._ApplicationRuntime__cell.add_field(
            self._ApplicationRuntime__principal, collection, field, field_type)
