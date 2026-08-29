"""Application-bound structured data cell.

Each cell owns one storage handle. Sessions never accept an application ID;
the application scope comes from the authenticated Principal and the cell
selected by the service. No database-native command is part of this API.
"""

from dataclasses import dataclass
import hashlib
import json
import sqlite3
from threading import RLock

from .audit import AuditSink
from .auth import Principal, Role
from .config import FoundationConfig
from .errors import (AuthorizationError, CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, NotFoundError,
                     ResourceLimitError, ValidationError)
from .identifiers import quote_identifier, validate_identifier

# The common contract's own mutation vocabulary
# (`structured_operations.allowed_mutations`). `transact()` below only
# executes "insert" itself; the other three names are real operations this
# peer provides elsewhere (`update`/`delete` as their own dedicated
# methods) or nowhere at all (`upsert`) -- either way, presenting one of
# them to `transact()` specifically is a capability gap in this entry
# point, not a malformed/unrecognized request, so it is distinguished from
# a name outside this vocabulary entirely (still `ValidationError`).
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

_TYPES = {"text": "TEXT", "integer": "INTEGER", "real": "REAL",
          "boolean": "INTEGER", "json": "TEXT"}
_OPS = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">",
        "gte": ">=", "in": "IN"}

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
# peer's behavior. All three now share one code path in `_where` below.
_UNSUPPORTED_CONTRACT_OPERATORS = {"contains", "matches", "is_null"}

# WP-5 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5, contract
# `destructive_confirmation`): declare-and-echo confirmation for `delete`,
# this peer's only destructive operation (`drop_entity`/`drop_index` are
# `SurfaceAbsent` -- `create_collection` has no drop parameter anywhere on
# this peer's public surface -- and `revoke_credential`'s "last control
# credential" gate is a control-plane concept this peer's `ControlPlane`
# does not implement at all, per its own `control_plane: unavailable`
# capability declaration).
#
# No state fingerprint (contract `phrase_construction` rule "state-
# fingerprinted for re-creatable targets"): that rule only binds a target
# "identifiable by a name that can be destroyed and later recreated". This
# peer has no such path for a collection -- `create_collection` raises
# `ConflictError` if the name already exists (cell.py above) and there is
# no `drop_collection`/`drop_entity` method anywhere on this peer's public
# surface (confirmed by source inspection: `ApplicationDeveloper` exposes
# only `create_collection`; `capabilities().schema_operations.unsupported`
# lists `drop_entity` itself). Nor does this peer have any schema-mutation
# operation on an EXISTING collection (`add_field`/`alter_field`/
# `create_index` are likewise all declared `unsupported`, and there is no
# `schema_revision`-style counter anywhere on this peer), so there is no
# "other schema change" dimension either -- unlike r2db-api (Q1-D10, which
# added a schema-revision fingerprint to its OWN delete phrase precisely
# because its entities CAN be dropped and recreated under the same name).
# A collection's shape is therefore permanently fixed for the rest of this
# process's lifetime once created, so a `delete` phrase naming it can never
# be invalidated by a re-creation or schema change that does not exist as a
# capability on this peer -- omitting the fingerprint here is not an
# oversight, it is this peer's own real, evidenced answer to the same
# question r2db-api's Q1-D10 answered differently for r2db-api's own,
# different, real capability (design v1.5 §7 records this investigation).
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
    `Filter.value` reaching this point has already passed `_where`'s own
    `_encode_value` (dict/list/bool/str/int/float/None only, raising
    `ValidationError` for anything else) by construction -- `delete` below
    always calls `_where` before this function -- so a value this
    `json.dumps` cannot serialize natively would mean that invariant broke
    elsewhere; surfacing that as an immediate `TypeError` here is more
    honest than silently collapsing it into a string that could coincide
    with a different value's own string form.
    """
    payload = [{"field": f.field, "operator": f.operator, "value": f.value} for f in filters]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _delete_confirmation_phrase(collection, filters):
    """`DELETE <collection> @where=<digest16>` -- digest16 is the first 16
    hex characters of the SHA-256 of `_canonical_where_json(filters)`.
    `collection` must already be identifier-validated by the caller
    (contract `phrase_construction` rule "only identifier-validated target
    names") -- `ApplicationCell.delete` below always calls this only after
    `validate_identifier(collection, ...)` has succeeded.

    Length: identifiers are bounded to 63 characters
    (`identifiers._IDENTIFIER`), so the worst case is
    ``"DELETE " (7) + collection (63) + " @where=" (8) + digest16 (16) =
    94`` -- comfortably within `confirmation`'s contract `maxLength` of 256
    (R-1), so the bounded-digest escape hatch contract `phrase_construction`
    rule "bounded" describes is never actually needed on this peer. n-1
    correction (independent review): the `assert` below is NOT itself what
    proves this invariant -- `assert` statements are stripped entirely when
    Python runs under `-O`/`PYTHONOPTIMIZE`, so it must never be the only
    thing standing between this function and an over-length phrase. The
    real proof is the arithmetic above, grounded in `collection` already
    having passed `validate_identifier` (a hard 63-character regex bound)
    by the time this function is called (contract rule (c): only
    identifier-validated names ever reach a phrase). The assert is a
    development-time backstop that fixes this reasoning in an executable
    form (catching a future change to either bound, e.g. a longer
    identifier limit, immediately in a normal test run) -- not a
    substitute for it, and not load-bearing under `-O`.
    """
    digest = hashlib.sha256(_canonical_where_json(filters).encode("utf-8")).hexdigest()[:16]
    phrase = "DELETE " + collection + " @where=" + digest
    assert len(phrase) <= 256, "delete confirmation phrase exceeds contract confirmation maxLength"
    return phrase


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: object


class ApplicationCell:
    """A private application storage boundary.

    ``sqlite3`` is used only as a deterministic local foundation backend. The
    production Cloud SQL adapter must keep this authority shape and replace
    the storage driver without exposing its connection to Application code.
    """

    def __init__(self, application_id, config=None, audit=None, guard=None):
        validate_identifier(application_id, "application_id")
        self.application_id = application_id
        self.config = config or FoundationConfig()
        self.__record = (audit or AuditSink()).record
        self.__guard = guard
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = RLock()

    def _schema_count(self):
        row = self._db.execute(
            "SELECT count(*) AS count FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return row["count"]

    def create_collection(self, principal, name, fields, destructive=False):
        self._require_developer(principal)
        validate_identifier(name, "collection")
        if not isinstance(fields, dict) or not fields:
            raise ValidationError("fields must be a non-empty object")
        if len(fields) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7, supersedes the WP-5 body's own
            # `query_complexity` tagging): this bounds how many columns a
            # single collection DEFINITION may name in one `create_
            # collection` call -- a one-time shape bound on the request
            # itself, not a repeated, finite-resource consumption class.
            # r2db-api's own real precedent for the identical real-world
            # check (`create_entity`'s own field-count bound,
            # `structured.py::bind_schema_operation`) classifies it
            # `VALIDATION_FAILED` too, with no involvement in any resource
            # aggregate -- matched here rather than forcing a `limit_class`
            # whose declared `capabilities()` number could never agree with
            # what this check actually enforces.
            raise ValidationError("field limit exceeded")
        if self._schema_count() >= self.config.max_schema_objects:
            raise ResourceLimitError("schema object limit exceeded", limit_class="schema_objects")
        definitions = []
        for field, field_type in fields.items():
            validate_identifier(field, "field")
            if field_type not in _TYPES:
                raise ValidationError("unsupported field type")
            definitions.append(quote_identifier(field) + " " + _TYPES[field_type])
        statement = "CREATE TABLE " + quote_identifier(name) + " (" + \
            ", ".join(definitions) + ")"
        with self._lock:
            try:
                self._db.execute(statement)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise ConflictError("collection already exists")
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="create_collection")

    def insert(self, principal, collection, values):
        self._require_data(principal)
        table, fields, params = self._prepare_values(collection, values)
        columns = ", ".join(quote_identifier(field) for field in fields)
        marks = ", ".join("?" for _ in fields)
        with self._lock:
            try:
                cursor = self._db.execute("INSERT INTO " + table + " (" + columns + ") VALUES (" + marks + ")", params)
                self._db.commit()
            except sqlite3.IntegrityError:
                raise ConflictError("write conflicts with a constraint")
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return {"rowid": cursor.lastrowid}

    def read(self, principal, collection, fields=None, filters=None,
             order_by=None, limit=None):
        self._require_data(principal)
        table = quote_identifier(validate_identifier(collection, "collection"))
        selected = self._fields(collection, fields)
        statement = "SELECT " + ", ".join(quote_identifier(x) for x in selected) + " FROM " + table
        where, params = self._where(collection, filters)
        statement += where
        if order_by is not None:
            if not isinstance(order_by, dict):
                raise ValidationError("order_by must be an object")
            field = validate_identifier(order_by.get("field"), "order field")
            if field not in self._field_names(collection):
                raise ValidationError("unknown order field")
            direction = order_by.get("direction", "asc")
            if direction not in ("asc", "desc"):
                raise ValidationError("invalid order direction")
            statement += " ORDER BY " + quote_identifier(field) + " " + direction.upper()
        if limit is None:
            limit = self.config.max_result_rows
        if not isinstance(limit, int) or limit <= 0 or limit > self.config.max_result_rows:
            raise ResourceLimitError("result limit exceeded", limit_class="result_items")
        statement += " LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self._db.execute(statement, params).fetchall()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return [dict(row) for row in rows]

    def update(self, principal, collection, values, filters):
        self._require_data(principal)
        if not isinstance(filters, list) or not filters:
            raise ValidationError("update requires non-empty filters")
        table, fields, values_params = self._prepare_values(collection, values)
        if not fields:
            raise ValidationError("values must be non-empty")
        where, where_params = self._where(collection, filters)
        statement = "UPDATE " + table + " SET " + ", ".join(
            quote_identifier(field) + " = ?" for field in fields) + where
        with self._lock:
            try:
                cursor = self._db.execute(statement, values_params + where_params)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return {"updated": cursor.rowcount}

    def delete(self, principal, collection, filters, *, destructive=False, confirm=None):
        """Contract `destructive_confirmation`: `delete` is this peer's
        only destructive operation (see the module-level comment above
        `_DELETE_CONSEQUENCE` for why `drop_entity`/`drop_index`/the
        control-plane revoke gate are all structurally absent here, not
        merely unimplemented). `destructive` missing is equivalent to
        `False` (contract `valid_confirmation`); a valid confirmation
        requires BOTH `destructive is True` AND `confirm` to exactly equal
        the server's own currently-recomputed `required_confirmation` for
        this exact request (Unicode code point sequence, no normalization
        -- a plain `!=` string comparison already has this property). A
        non-bool `destructive`/non-str `confirm` is a shape defect
        (`ValidationError`), not a confirmation mismatch -- truthy
        acceptance of either is exactly the defect WP-0/WP-3's own B-1
        finding (r2db-api) forbids, applied here identically (WP-5 R-5).
        """
        self._require_data(principal)
        if not isinstance(destructive, bool):
            raise ValidationError("destructive must be a boolean")
        if confirm is not None and not isinstance(confirm, str):
            raise ValidationError("confirm must be a string")
        # B-3 (WP-0/WP-5): identifier + filter-shape validation (which,
        # via `_where`'s own `_field_names` call, also performs the
        # contract's own "target-existence checks" step) must complete
        # BEFORE the confirmation check below -- a phrase must never
        # reflect an unvalidated client-supplied collection name back to
        # the client, and evaluation_order requires target existence to be
        # settled before confirmation validity is evaluated.
        table = quote_identifier(validate_identifier(collection, "collection"))
        if not isinstance(filters, list) or not filters:
            raise ValidationError("delete requires non-empty filters")
        where, params = self._where(collection, filters)
        phrase = _delete_confirmation_phrase(collection, filters)
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
        statement = "DELETE FROM " + table + where
        with self._lock:
            try:
                cursor = self._db.execute(statement, params)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        self.__record("destructive_data_operation", self.application_id,
                      principal.credential_id, detail="delete_rows")
        return {"deleted": cursor.rowcount}

    def transact(self, principal, operations):
        self._require_data(principal)
        if not isinstance(operations, list) or not operations:
            raise ValidationError("operations must be a non-empty list")
        if len(operations) > self.config.max_batch_items:
            raise ResourceLimitError("batch limit exceeded", limit_class="batch_items")
        with self._lock:
            try:
                self._db.execute("BEGIN")
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
                            # same reasoning as the `update`/`upsert`/
                            # `delete` branch below, which already refuses
                            # this way for the operation *type* itself.
                            raise CapabilityError(
                                "transact does not support additional fields on operation type 'insert'"
                            )
                        results.append(self._insert_in_transaction(operation["collection"], operation["values"]))
                        continue
                    if op_type in _CONTRACT_MUTATION_VOCABULARY:
                        # Contract vocabulary (insert/update/upsert/delete),
                        # but this entry point does not execute it: no
                        # `upsert` exists anywhere on this peer, and
                        # `update`/`delete` are only ever provided through
                        # their own dedicated methods below, never through
                        # `transact`. Per `capability_status.rules`
                        # ("optional target operations ... must fail with
                        # CAPABILITY_UNSUPPORTED"), this is a capability
                        # gap, not a malformed request.
                        raise CapabilityError(f"transact does not support operation type {op_type!r}")
                    raise ValidationError("unsupported transaction operation")
                self._db.commit()
                return results
            except (ValidationError, ResourceLimitError, CapabilityError, DestructiveConfirmationRequired):
                # `DestructiveConfirmationRequired` is not currently
                # reachable from inside this loop (no operation type this
                # dispatcher itself executes -- "insert" -- is destructive,
                # and `delete`/`update`/`upsert` are refused by the
                # `CapabilityError` branch above before any destructive
                # check could run); added defensively (WP-5 R-5 m-8-style
                # precedent) so a future capability addition here cannot
                # silently skip this rollback.
                self._db.rollback()
                raise
            except sqlite3.IntegrityError:
                self._db.rollback()
                raise ConflictError("transaction rolled back")
            except sqlite3.DatabaseError:
                self._db.rollback()
                raise NotFoundError("transaction rolled back")

    def _insert_in_transaction(self, collection, values):
        table, fields, params = self._prepare_values(collection, values)
        statement = "INSERT INTO " + table + " (" + ", ".join(
            quote_identifier(field) for field in fields) + ") VALUES (" + \
            ", ".join("?" for _ in fields) + ")"
        cursor = self._db.execute(statement, params)
        return {"rowid": cursor.lastrowid}

    def _fields(self, collection, requested):
        available = self._field_names(collection)
        if requested is None:
            return available
        if not isinstance(requested, list) or not requested:
            raise ValidationError("fields must be a non-empty list")
        if len(requested) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): read-projection width is a shape
            # bound on the request's own `fields` list, mirroring contract
            # `QueryRequest.select.maxItems`. r2db-api's own real precedent
            # for the SAME real-world check, `validate_projection`
            # (`structured.py`), is a standalone `VALIDATION_FAILED` at its
            # own fixed ceiling -- entirely separate from, and never folded
            # into, its own `query_complexity` resource aggregate (which
            # additionally, independently sums `len(select)` alongside
            # `len(where)`/`order_by_count` against a stricter, deployment-
            # tunable bound). This peer implements no such aggregate for
            # this dimension at all -- there is only ever this one,
            # standalone count -- so nothing here plays the resource-
            # aggregate role `query_complexity` names; classifying it as a
            # finite resource would have left `limit_class` unable to agree
            # with any true `capabilities()` declaration (Q1-D11 supersedes
            # this call site's former `query_complexity` tagging).
            raise ValidationError("field limit exceeded")
        result = []
        for field in requested:
            field = validate_identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            result.append(field)
        return result

    def _field_names(self, collection):
        name = validate_identifier(collection, "collection")
        try:
            rows = self._db.execute("PRAGMA table_info(" + quote_identifier(name) + ")").fetchall()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        if not rows:
            raise NotFoundError("collection not found")
        return [row["name"] for row in rows]

    def _prepare_values(self, collection, values):
        table_name = validate_identifier(collection, "collection")
        available = self._field_names(table_name)
        if not isinstance(values, dict) or not values:
            raise ValidationError("values must be a non-empty object")
        if len(values) > self.config.max_fields:
            # Q1-D11 (design v1.5 §7): write-payload width (insert/update/
            # transact-insert) mirrors contract `Mutation.values.
            # maxProperties: 100` directly -- exactly the shape r2db-api's
            # own Q1-D8 already adjudicated for the identical contract
            # property (`structured.py`'s former `structured.py:212`,
            # reclassified `VALIDATION_FAILED` there for the same reason:
            # "mirrors the contract's own fixed ... shape bound, not a
            # deployment-tunable limits.classes resource"). Applied here
            # identically.
            raise ValidationError("field limit exceeded")
        fields = []
        params = []
        for field, value in values.items():
            field = validate_identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            fields.append(field)
            params.append(self._encode_value(value))
        return quote_identifier(table_name), fields, params

    def _where(self, collection, filters):
        if filters is None:
            return "", []
        if not isinstance(filters, list) or len(filters) > self.config.max_filter_terms:
            # Clean 1:1 correspondence: this is the same shape dimension
            # r2db-api's own `query_complexity` metric folds `len(where)`
            # into, and `capabilities()` below publishes this exact bound
            # (`config.max_filter_terms`) under the `query_complexity` key
            # (renamed from this peer's own former non-canonical
            # `filter_terms` vocabulary word, WP-5 Q1-D7(B)).
            raise ResourceLimitError("filter limit exceeded", limit_class="query_complexity")
        available = self._field_names(collection)
        clauses, params = [], []
        for item in filters:
            if not isinstance(item, Filter):
                raise ValidationError("filters must contain Filter values")
            field = validate_identifier(item.field, "filter field")
            if item.operator in _UNSUPPORTED_CONTRACT_OPERATORS:
                # Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication,
                # docs/design/R2DB_CCR13_STORAGE_V1.md): `contains`/
                # `matches`/`is_null` are real members of the common
                # contract's own filter-operator vocabulary
                # (`allowed_query_operators`), unlike a genuinely
                # unrecognized operator string -- this peer simply does
                # not execute any of the three. That is exactly
                # CapabilityError's own distinction from ValidationError
                # (see that class's docstring): a request outside the
                # contract's vocabulary entirely (ValidationError) versus a
                # contract operation this peer's own entry point does not
                # implement (CapabilityError, mapped to
                # CAPABILITY_UNSUPPORTED at the API boundary) -- a positive,
                # honest refusal, since this peer's filter grammar does have
                # an acceptance surface for the vocabulary (unlike a peer
                # with no filter DSL at all). Checked ahead of the
                # field-existence check below (WP-3 review minor, ordering
                # unified with r2db-api: there, `DataService.query`'s own
                # `matches` gate fires before the cell is ever called at
                # all, so field existence is never even considered -- a
                # refusal this unconditional must not depend on whether the
                # named field happens to exist). `contains`/`is_null` used
                # to fall through to the generic "not a filter operator this
                # peer implements" branch below and raise `ValidationError`
                # instead, disagreeing with their own declared
                # `unsupported` status -- fixed (conformance-review finding,
                # WP-5a): all three now share this one path.
                raise CapabilityError(f"{item.operator} is not supported by this foundation")
            if field not in available:
                raise ValidationError("invalid filter")
            if item.operator not in _OPS:
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
                    # separate `max_filter_terms`-style bound) -- an `in`
                    # filter's value list is, in real terms, a list of
                    # discrete items processed together in one call, the
                    # same resource `batch_items` already names for
                    # `transact`'s own operation list below; the numeric
                    # bound this check enforces is the exact same
                    # configured value `capabilities()` publishes under
                    # `batch_items`.
                    raise ResourceLimitError("filter value limit exceeded", limit_class="batch_items")
                clauses.append(quote_identifier(field) + " IN (" + ",".join("?" for _ in item.value) + ")")
                params.extend(self._encode_value(value) for value in item.value)
            else:
                clauses.append(quote_identifier(field) + " " + _OPS[item.operator] + " ?")
                params.append(self._encode_value(item.value))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _encode_value(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (str, int, float)) or value is None:
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
        """
        self.__authorize()
        principal = self.__principal
        is_developer = principal.role == Role.DEVELOPER
        config = self.__cell.config
        return {
            # 1.2.0 (WP-5, docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5):
            # `delete` now implements the contract's own declare-and-echo
            # `destructive_confirmation` semantics for real (see
            # `ApplicationCell.delete`) -- the flip to this version number
            # and the behavior it certifies land in the same commit (per-
            # peer single-commit flip rule). Every other 1.1.0/1.2.0
            # addition remains an optional capability this peer does not
            # (yet) provide, so conforming to those needs no further
            # behavior change here beyond declaring the new capability
            # names below as unavailable, mirroring r2db-api's declaration.
            "contract_version": "1.2.0",
            "capabilities": {
                # `_OPS` (this module) has no "contains" / "matches" /
                # "is_null" entry, so those three contract-listed operators
                # are not executable here: "enabled" would misrepresent
                # them as available. `_where` (above) refuses each of the
                # three honestly (CapabilityError for `matches`, which has
                # its own acceptance surface in the filter grammar;
                # ValidationError for `contains`/`is_null`, which do not).
                "structured_query": {"status": "partial", "operators": list(_OPS), "unsupported": ["contains", "matches", "is_null"]},
                # Independent-review finding MA-1 (design v1.5 §7):
                # `operations` here names every member of the contract's
                # own mutation vocabulary (`structured_operations.
                # allowed_mutations`) this peer executes for REAL through
                # SOME entry point a genuine client would actually use --
                # `insert`/`update`/`delete` each through their own
                # dedicated method (`ApplicationCell.insert`/`update`/
                # `delete`), matching the port-level `ConformanceAdapter.
                # attempt_mutation`'s own contract ("present one mutation-
                # vocabulary operation ... to the peer exactly as a real
                # client would", no batch-specific scoping) and C-12's own
                # `_declared_mutation_operations` check, which reads this
                # exact list against exactly that adapter method. `upsert`
                # alone has no dedicated method anywhere on this peer, so
                # it stays `unsupported`.
                #
                # This is a DELIBERATE reading, not the only one the
                # capability's own defined text supports: `capability_
                # status.defined.atomic_mutation` is "Single-entity atomic
                # mutation batches" (contract), and under a stricter,
                # literal reading of that text -- "which operations can
                # this peer's own MULTI-OPERATION atomic batch dispatcher
                # execute" -- only `insert` would qualify: `ApplicationCell.
                # transact`, this peer's only such dispatcher, refuses
                # `update`/`delete`/`upsert` unconditionally with
                # `CapabilityError`, before inspecting anything else about
                # the request. Investigated and NOT adopted here: making
                # this peer's declaration agree with that stricter reading
                # would require this adapter's own `attempt_mutation`
                # method to stop presenting `update`/`delete` through their
                # real, working, dedicated entry points and instead route
                # them through `transact` (the only way to make them
                # genuinely fail as that reading requires) -- which was
                # measured to make C-12 pass, but does so by making this
                # adapter misrepresent how a real client actually reaches
                # this peer's own update/delete behavior (no genuine client
                # would batch-wrap a single update), and would silently
                # stop exercising `update`'s real behavior everywhere else
                # in this suite that presents it as working. r2db-api's own
                # declaration (`"atomic_mutation": {"status": "enabled",
                # "operations": [...all four...]}`) does not disambiguate
                # between these two readings -- its single `mutate()`
                # dispatcher makes both readings coincide, a distinction
                # that only becomes observable on a peer whose single-
                # operation and batch entry points diverge, like this one.
                # Recorded as an open contract-clarification question
                # (design v1.5 §7, MA-1) rather than decided unilaterally.
                "atomic_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
                # No public "list collections" operation exists on this peer.
                "application_catalog": {"status": "unavailable"},
                "schema_operations": {"status": "partial", "operations": ["create_entity"] if is_developer else [], "unsupported": ["add_field", "alter_field", "create_index", "drop_index", "drop_entity", "jobs"]},
                "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                "best_effort_transactions": {"status": "unavailable"},
                "idempotency": {"status": "unavailable"},
                "revision_preconditions": {"status": "unavailable"},
                "row_addressability": {"status": "unavailable"},
                "cross_entity_mutation": {"status": "unavailable"},
                "control_plane": {"status": "unavailable"}
            },
            # WP-5 limits-vocabulary fix (Q1-D7(B): "capabilities().limits/
            # limit_enforcement keys must be limits.classes members"). This
            # peer's own former, non-canonical vocabulary words were
            # `fields`/`filter_terms` -- neither survives unchanged:
            #
            # - `filter_terms` -> `query_complexity`: a clean, true 1:1
            #   rename. `_where`'s own filter-count bound (`config.
            #   max_filter_terms`) is the exact same shape dimension r2db-
            #   api's own `query_complexity` metric folds `len(where)`
            #   into, and this is this class's ONLY declared numeric value
            #   below (the same config field, no other check shares it).
            #
            # - `fields` -> dropped entirely, not renamed, and not
            #   replaced by any other `limits.classes` member either
            #   (Q1-D11, design v1.5 §7, superseding this WP's own initial
            #   `query_complexity` tagging). `config.max_fields` gates
            #   THREE checks (`create_collection`'s schema-field count,
            #   `_fields`' read-projection width, `_prepare_values`'s
            #   write-payload width) that this peer's former declaration
            #   conflated under one key -- but on investigation none of the
            #   three is a finite-resource consumption bound at all: each
            #   mirrors a fixed contract SHAPE constraint on the request
            #   itself (`Mutation.values.maxProperties`-style; write-payload
            #   width matches that property directly, the other two mirror
            #   the same real-world checks r2db-api itself classifies
            #   `VALIDATION_FAILED` -- `create_entity`'s own field-count
            #   bound and `validate_projection`'s `select`-count bound,
            #   neither ever folded into any resource aggregate on that
            #   peer either). All three now raise `ValidationError`, not
            #   `ResourceLimitError` -- see each call site's own comment.
            #   There is therefore no declaration gap left to record here:
            #   a shape bound correctly has no `limits.classes` entry at
            #   all (unlike r2db-api's own genuine L4 `request_bytes` gap,
            #   which really is an unpublished RESOURCE bound).
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
