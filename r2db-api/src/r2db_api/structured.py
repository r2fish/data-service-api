"""A small structured-operation reference engine (no database-native command path)."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
import re
from typing import Any, Callable

from .errors import fail
from .limits import ResourceLimits

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# PostgreSQL's own identifier limit, and the bound MitateDB-api already
# enforces (`^[a-z][a-z0-9_]{0,62}$`). This is a structural syntax policy on
# identifiers, not a deployment-tunable resource class from the contract's
# `limits.classes`, so it lives here as a constant rather than in
# ResourceLimits; the contract permits a stricter per-implementation
# identifier policy.
MAX_IDENTIFIER_LENGTH = 63
OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "matches", "is_null"}
# Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication, docs/design/
# R2DB_CCR13_STORAGE_V1.md): `contains` is literal substring containment
# (no wildcard interpretation) and `matches` is a case-sensitive wildcard
# pattern (`%`/`_`/`\`). Both operators' *value* is always a plain string,
# independent of the target field's own declared type (a typed non-string
# column is matched against its text representation) -- checked once here,
# ahead of the per-column `_check_type` declared-type check below, since
# this constraint is about the operator, not the column.
_TEXT_ONLY_OPERATORS = {"contains", "matches"}

# Contract 1.1.0 (CCR-13, R2DB_CCR13_STORAGE_V1.md R-3): the server-assigned
# row address `id` and any implementation-internal name starting with this
# prefix (e.g. the invisible revision column `_r2db_revision`) are reserved.
# A client may never declare a field, entity, or index using either form --
# this is what keeps the reservation a checked, fail-closed property instead
# of a convention two backends could silently drift on (R-3, M-9: both cells
# share this exact policy; R-5 extends the `_r2db` prefix reservation to
# index names too -- WP-2 review minor (d)).
_RESERVED_PREFIX = "_r2db"


def validate_identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or len(value) > MAX_IDENTIFIER_LENGTH:
        fail("IDENTIFIER_INVALID", "Identifier has an unsupported format.", details={"field": "identifier"})
    return value


def _reject_reserved_field(name: str) -> None:
    if name == "id" or name.startswith(_RESERVED_PREFIX):
        fail("IDENTIFIER_INVALID", "Identifier is reserved for internal use.", details={"field": "identifier"})


def _reject_reserved_prefix(name: str) -> None:
    """Prefix-only reservation, used for entity names and (WP-2 review
    minor (d)) index names -- unlike `_reject_reserved_field`, `id` itself
    is not reserved here (an entity or index literally named `id` does not
    collide with the per-row address column)."""
    if name.startswith(_RESERVED_PREFIX):
        fail("IDENTIFIER_INVALID", "Identifier is reserved for internal use.", details={"field": "identifier"})


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("VALIDATION_FAILED", message)
    return value


def parse_predicate(value: Any) -> "Predicate":
    item = _mapping(value, "Filter must be an object.")
    if not {"field", "operator"}.issubset(item) or set(item) - {"field", "operator", "value"}:
        fail("VALIDATION_FAILED", "Filter shape is not supported.")
    return Predicate(field=item["field"], operator=item["operator"], value=item.get("value"))


@dataclass(frozen=True)
class Predicate:
    field: str
    operator: str
    value: Any = None

    def validate(self) -> None:
        validate_identifier(self.field)
        if self.operator not in OPERATORS:
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details={"field": self.field})


# --- Shared validation/planning boundary (design D-1) -----------------------
#
# Everything below this point is the boundary every `StorageBackend` MUST
# cross before touching stored data: identifier syntax, the operator/
# operation allowlists, mutation/schema shape checks, and destructive
# confirmation. `ApplicationCell` (below) and `PostgresCell`
# (`r2db_api.postgres`) both call these same functions -- neither backend
# reimplements this logic privately. A backend still performs its own
# catalog-existence checks (NOT_FOUND/CONFLICT against its real stored
# entities/fields) and its own execution, because those are inherently
# backend-specific; but "is this identifier/operator/shape/confirmation
# valid at all" is decided exactly once, here, for every backend.
#
# What is deliberately NOT decided here (because it needs live catalog
# knowledge only a backend has): whether an entity's declared uniqueness
# key count makes `upsert` executable (R-5), and how `expected_revision`
# resolves against stored rows (R-4). Both are pure-shape-checked here
# (well-formed string, not paired with `insert`, not silently discarded on
# an empty-values `update`) and then executed by each backend's own code.
#
# CCR-13 WP-5b: this shared boundary structurally *accepts* the full
# vocabulary (`expected_revision`, `upsert`, `create_index`/`drop_index`,
# `field_type`, `matches`) unconditionally -- it never gated any of it
# itself. `DataService` (service.py) carried a provisional gate through
# WP-2〜WP-5 that kept the HTTP-observable surface matching the then-
# current `capabilities()` declaration while this boundary and both cells
# were being built out; that gate is removed in the same commit that
# updates the declaration (design R2DB_CCR13_STORAGE_V1.md §3), so
# `DataService` now exposes exactly what this boundary and the cells
# themselves decide.


def validate_projection(select: Any, known_fields: set[str]) -> list[str]:
    """Bounded, non-empty, identifier-checked, catalog-checked field list."""
    if not isinstance(select, list) or not select or len(select) > 100:
        fail("VALIDATION_FAILED", "A bounded non-empty projection is required.")
    for field_name in select:
        validate_identifier(field_name)
    if any(field_name not in known_fields for field_name in select):
        fail("NOT_FOUND", "Field was not found.", status=404)
    return select


def validate_predicates(where: list["Predicate"], known_fields: set[str]) -> list["Predicate"]:
    """Operator-allowlist- and catalog-checked predicates (already parsed)."""
    for predicate in where:
        predicate.validate()
        if predicate.field not in known_fields:
            fail("NOT_FOUND", "Field was not found.", status=404)
    return where


MUTATION_OPERATIONS = {"insert", "update", "upsert", "delete"}
_MUTATION_KEYS = {"operation", "values", "where", "destructive", "confirmation", "expected_revision", "idempotency_key", "unique_key"}
MAX_EXPECTED_REVISION_LENGTH = 128


@dataclass(frozen=True)
class BoundMutation:
    """A single mutation item that has crossed the shared validation
    boundary: shape, operator allowlist, identifiers, and value bounds are
    settled. `destructive`/`confirmation` are carried through unevaluated --
    see `require_destructive_confirmation` for why that check is deliberately
    left to each backend's own call site rather than folded in here.
    `expected_revision` is similarly carried through unevaluated: whether it
    can be honoured at all (a backend may not yet implement the revision
    column) and how it resolves against stored rows (R-4) is each backend's
    own execution concern.
    """

    operation: str
    where: list["Predicate"]
    values: dict[str, Any]
    destructive: bool
    confirmation: Any = None
    expected_revision: str | None = None
    # Contract 1.1.0 addendum (Q-1 adjudication, 案B, 2026-08-28): names the
    # declared uniqueness key `upsert` should use as its existence test when
    # an entity declares more than one. Only `upsert` accepts it (§0.5 Q-1 /
    # R-5); which key is actually available/selected is catalog knowledge
    # only a backend has, so -- like `expected_revision` above -- this
    # shared, catalog-agnostic function only validates its shape/placement
    # and carries it through unevaluated.
    unique_key: str | None = None


def bind_mutation(operation: Any, known_fields: set[str]) -> BoundMutation:
    if not isinstance(operation, dict) or set(operation) - _MUTATION_KEYS:
        fail("VALIDATION_FAILED", "Mutation shape is not supported.")
    name = operation.get("operation")
    if name not in MUTATION_OPERATIONS:
        fail("CAPABILITY_UNSUPPORTED", "Mutation operation is not supported.")
    if "idempotency_key" in operation:
        fail("CAPABILITY_UNSUPPORTED", "Idempotency semantics are not enabled by this foundation.")
    if name == "insert" and "where" in operation:
        # WP-2 review M-4: `insert`'s `where` was previously parsed and then
        # silently never used by any backend's insert path -- the same
        # silent-ignore shape upsert's own `where` rejection closes (M-3
        # below), now closed symmetrically for insert.
        fail("VALIDATION_FAILED", "insert does not accept a filter.")
    # Whether a `where` on `upsert` is rejected (R-5, corrigendum M-3:
    # upsert's existence test is the entity's declared uniqueness key, never
    # a client-supplied predicate) needs live catalog knowledge -- an
    # entity with zero declared uniqueness keys must still be refused with
    # CAPABILITY_UNSUPPORTED first, even if a stray `where` also came along
    # (a capability that is not available at all takes precedence over a
    # shape complaint about a request against it). That ordering can only
    # be decided once a backend has looked at the entity's own declared
    # keys, so this shared, catalog-agnostic function only parses `where`
    # here; each backend's own upsert execution path (`ApplicationCell.
    # _apply_upsert`) rejects a non-empty `where` itself, once it already
    # knows upsert is actually executable for this entity.
    raw_where = operation.get("where", [])
    if not isinstance(raw_where, list):
        fail("VALIDATION_FAILED", "Mutation filter must be a list.")
    where = validate_predicates([parse_predicate(item) for item in raw_where], known_fields)
    raw_values = operation.get("values", {})
    if not isinstance(raw_values, dict):
        fail("VALIDATION_FAILED", "Mutation values must be an object.")
    if len(raw_values) > 100:
        # Contract 1.2.0 (subordinate ruling 7(B), Q1-D8): this mirrors the
        # contract's own fixed `Mutation.values.maxProperties: 100` shape
        # bound, not a deployment-tunable `limits.classes` resource -- so it
        # is `VALIDATION_FAILED` (400), never `LIMIT_EXCEEDED` (which would
        # be unable to name a `limit_class` member for this, since no such
        # class exists).
        fail("VALIDATION_FAILED", "Mutation contains too many fields.", details={"field": "values"})
    for key in raw_values:
        validate_identifier(key)
        if key not in known_fields:
            fail("NOT_FOUND", "Field was not found.", status=404)
    if name in {"insert", "update", "upsert"} and "id" in raw_values:
        # R-3, property 4: the row address is always server-assigned. A
        # client may read `id` (select/where/order_by) freely but can never
        # write it, on insert (it would forge an address) or update/upsert
        # (it would move an existing row's address).
        fail("VALIDATION_FAILED", "The id field is server-assigned and cannot be supplied.", details={"field": "id"})
    if "destructive" in operation and not isinstance(operation["destructive"], bool):
        fail("VALIDATION_FAILED", "Destructive flag must be boolean.")
    expected_revision: str | None = None
    if "expected_revision" in operation:
        expected_revision = operation["expected_revision"]
        if not isinstance(expected_revision, str) or len(expected_revision) > MAX_EXPECTED_REVISION_LENGTH:
            fail("VALIDATION_FAILED", "expected_revision must be a string.", details={"field": "expected_revision"})
        if "\x00" in expected_revision:
            # R-7 addendum (WP-3 review blocker-2): a NUL byte here would
            # otherwise reach PostgreSQL's `uuid`/`text` comparison and be
            # rejected at execution time, not deterministically here.
            fail("VALIDATION_FAILED", "expected_revision must not contain a NUL character.", details={"field": "expected_revision"})
        if name == "insert":
            # R-4, contract's revision-precondition clause 6: a precondition
            # asserts an existing row's identity; insert creates one, so the
            # combination is never meaningful.
            fail("VALIDATION_FAILED", "insert does not support a revision precondition.")
        if name == "update" and not raw_values:
            # R-4, corrigendum M-1: the empty-`values` `update` branch below
            # does not write anything, so a precondition riding along with
            # it would be silently discarded rather than evaluated -- one
            # of the "precondition asserted, then quietly ignored" gaps this
            # foundation must not have.
            fail("VALIDATION_FAILED", "A revision precondition requires values to apply.")
    if name in {"update", "delete"} and not where:
        fail("VALIDATION_FAILED", "This operation requires a non-empty filter.")
    unique_key: str | None = None
    if "unique_key" in operation:
        if name != "upsert":
            fail("VALIDATION_FAILED", "unique_key is only supported by upsert.")
        unique_key = validate_identifier(operation["unique_key"])
    return BoundMutation(name, where, dict(raw_values), bool(operation.get("destructive")), operation.get("confirmation"), expected_revision, unique_key)


# --- destructive confirmation phrase construction (design docs/design/
# DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1, contract 1.2.0
# `destructive_confirmation.phrase_construction`) --------------------------
#
# One shared definition for every one of this codebase's three surfaces
# (data/schema plane here, control plane in `control_plane.py`, and the
# ceremony CLI's own `ops.py` in a later work package) -- none of them
# re-derives its own spelling. Every phrase is: (a) deterministic given only
# the operation/target/consequence class (never request_id, timestamps, or
# the request's own destructive/confirmation fields), (b) scope-included
# (`delete`'s own selection/where predicate is part of the derivation), (c)
# state-fingerprinted for a re-creatable target (`drop_entity`/`drop_index`
# carry the application's current `schema_revision`, so re-creating the same
# name -- or any other schema change -- invalidates a stale phrase), (d)
# built only from already identifier-validated target names (never an
# unvalidated client-supplied string reflected back), and (e) bounded well
# within `confirmation`'s contract maxLength (256).

# r2db's own identifier limit (`MAX_IDENTIFIER_LENGTH` above), not a contract
# figure -- used only to assert the worst-case phrase length stays bounded.
_PHRASE_MAX_LENGTH = 256
# int64 (`_INT64_MAX` below in this same module) has at most 19 decimal
# digits; `schema_revision` is a monotonic counter starting at 0 and is
# always representable in that range for the lifetime of any real
# deployment, so 20 digits (one more than the true worst case) is a safe,
# round upper bound for the length assertions below.
_MAX_REVISION_DIGITS = 20


def _canonical_where_json(where: "list[Predicate]") -> str:
    """Key-order-fixed JSON serialization of a bound (identifier- and
    operator-validated) predicate list, the input to `_where_digest16`
    below. Defined for an empty list too (a `delete` with no `where` selects
    every row -- design R-2 item 1's own "where 空にも digest は定まる").

    Opus review minor m-7: deliberately NO `default=str` fallback. Every
    `predicate.value` reaching this function today is JSON-native (str/
    int/float/bool/None/list/dict, from `parse_predicate`'s own JSON-body
    parsing) and serializes exactly here without one. A `default=str`
    escape hatch would silently coerce any FUTURE non-JSON-native value
    (e.g. a `Decimal`, `datetime`, or `bytes` a later `bind_mutation` change
    might admit) into whatever `str(value)` happens to produce -- and two
    genuinely different values whose `str()` forms coincide (a real
    possibility across types, e.g. `Decimal("1")` and the string `"1"`)
    would then silently collide onto the identical digest, silently merging
    two different scopes' phrases into one. Without the fallback, such a
    value raises `TypeError` here immediately and loudly instead -- a
    finding for whoever introduces it to fix at the type's own admission
    point, not a probability-dependent security gap in this hash.
    """
    payload = [{"field": p.field, "operator": p.operator, "value": p.value} for p in where]
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def _where_digest16(where: "list[Predicate]") -> str:
    """SHA-256, first 16 hex characters, of `_canonical_where_json`'s
    output -- the delete phrase's own state-fingerprint-free scope digest
    (design Q1-D9/WP-0 MA-4: a probed narrow selection must never validate a
    broader one, since the digest changes whenever the selection does)."""
    blob = _canonical_where_json(where).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def delete_confirmation_phrase(entity: str, where: "list[Predicate]", schema_revision: int) -> str:
    """`DELETE <entity> @where=<digest16> @schema_revision=<n>` -- `entity`
    must already be identifier-validated by the caller (every caller of
    this function is downstream of `validate_identifier(entity)` in
    `transact()`).

    Monitor decision Q1-D10 (Opus review minor m-2, measured): the
    `schema_revision` fingerprint was originally omitted here on the
    reasoning that "a row is not a target identifiable by a re-creatable
    name, so it needs no state fingerprint" -- but the where-digest alone
    is a pure function of the (field, operator, value) tuples in the
    caller's own selection, independent of whether `entity` currently
    declares those fields at all. A probed phrase for `delete ... where
    id=5` against `widgets`, followed by `drop_entity widgets` + `create_
    entity widgets` (a genuinely different entity, same name, contract
    `phrase_construction` rule (b): "対象の再作成...により旧句が無効になる
    こと"), would otherwise still validate an echo of the OLD phrase
    against the NEW entity's identical-looking delete request -- the old
    phrase never actually became invalid, contradicting rule (b)'s literal
    text even though delete's own target (a row set) is not itself a
    re-created name. Including `schema_revision` closes this: any schema
    change to the Application (including this exact drop-then-recreate)
    invalidates every previously-issued delete phrase for every entity, not
    only the recreated one -- broader invalidation than strictly necessary,
    but safe (Q1-D3's own precedent: over-invalidating a stale phrase is
    the safe direction, under-invalidating is not) and now uniform across
    all three phrase-construction functions in this module.
    """
    # Worst-case length check, symmetric with `drop_index_confirmation_
    # phrase`'s own: `"DELETE "` (7) + entity (<= MAX_IDENTIFIER_LENGTH) +
    # `" @where="` (8) + 16-hex digest (16) + `" @schema_revision="` (18) +
    # up to `_MAX_REVISION_DIGITS` digits = 7 + 63 + 8 + 16 + 18 + 20 = 132,
    # comfortably within 256.
    worst_case = 7 + MAX_IDENTIFIER_LENGTH + 8 + 16 + 18 + _MAX_REVISION_DIGITS
    assert worst_case <= _PHRASE_MAX_LENGTH, "delete_confirmation_phrase's own worst-case bound no longer fits confirmation's maxLength"
    phrase = f"DELETE {entity} @where={_where_digest16(where)} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "delete_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def drop_entity_confirmation_phrase(entity: str, schema_revision: int) -> str:
    """`DROP_ENTITY <entity> @schema_revision=<n>` -- `n` is the
    Application's current schema_revision (monotonic, bumped by every
    schema operation on either backend), so re-creating an entity under the
    same name -- which necessarily bumps the revision again -- invalidates
    any phrase computed before the drop."""
    phrase = f"DROP_ENTITY {entity} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "drop_entity_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def drop_index_confirmation_phrase(entity: str, index: str, schema_revision: int) -> str:
    """`DROP_INDEX <entity>.<index> @schema_revision=<n>` -- the index name
    is scoped by entity in the phrase (design R-2 item 1: index names live
    in an entity-scoped namespace, `indexes[entity][index]`/the physical
    `<table>__<index>` name), not because the phrase needs to be invertible,
    only because two different entities' indexes of the same local name
    must never collide onto the same phrase.

    Worst-case length check (design R-2 item 1; nit n-1 corrected the
    arithmetic below -- the trailing segment is 18 characters, not 19, so
    the true worst case is 176, not 177; the assert itself was always
    conservative/safe either way, this corrects what the number MEANS):
    `"DROP_INDEX "` (11) + entity (<= MAX_IDENTIFIER_LENGTH) + `"."` (1) +
    index (<= MAX_IDENTIFIER_LENGTH) + `" @schema_revision="` (18) + up to
    `_MAX_REVISION_DIGITS` digits = 11 + 63 + 1 + 63 + 18 + 20 = 176,
    comfortably within the contract's 256 maxLength -- asserted here as a
    standing regression guard, not merely documented.
    """
    worst_case = 11 + MAX_IDENTIFIER_LENGTH + 1 + MAX_IDENTIFIER_LENGTH + 18 + _MAX_REVISION_DIGITS
    assert worst_case <= _PHRASE_MAX_LENGTH, "drop_index_confirmation_phrase's own worst-case bound no longer fits confirmation's maxLength"
    phrase = f"DROP_INDEX {entity}.{index} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "drop_index_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def revoke_last_control_credential_confirmation_phrase(credential_id: str) -> str:
    """`REVOKE_LAST_CONTROL_CREDENTIAL <credential_id>` -- the control
    plane's own destructive-confirmation phrase (design R-3), sharing this
    module's phrase-construction definitions even though the gate itself
    lives in `control_plane.py`, not here. No state fingerprint is needed:
    `credential_id` is itself a random, never-reused value (`control_plane.
    _new_control_credential_id`), so it already serves as its own fingerprint --
    a revoked id can never legitimately reappear as a *different* live
    credential the way an entity/index name can be re-created under the
    same name.
    """
    phrase = f"REVOKE_LAST_CONTROL_CREDENTIAL {credential_id}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "revoke_last_control_credential_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def require_destructive_confirmation(
    destructive: bool,
    confirmation: Any,
    phrase: str,
    message: str,
    *,
    consequence: str,
    reversible_alternative: str | None,
    recovery: str | None,
) -> None:
    """Shared SI-09 gate for every destructive operation (`delete`,
    `drop_entity`, `drop_index`). Deliberately NOT called from inside
    `bind_mutation`/`bind_schema_operation`: each backend calls it at the
    point in its own execution where it is about to destroy rows/objects,
    which for `ApplicationCell` is after existence/match computation
    (matching this foundation's pre-existing, tested error precedence) and
    strictly before any revision-precondition evaluation (R-4, corrigendum
    m-5: failure-before-execution means an unconfirmed destructive
    operation is refused before a precondition is even looked at).

    Contract 1.2.0 (`destructive_confirmation.valid_confirmation`/`denial`):
    `phrase` is this exact request's own, freshly (re)computed
    `required_confirmation` (one of the `*_confirmation_phrase` functions
    above) -- a valid confirmation is `destructive is True` AND
    `confirmation` equal to `phrase` as an exact Unicode code point sequence
    (no normalization). On denial, `details` carries all four contract-
    required keys (`required_confirmation`/`consequence`/
    `reversible_alternative`/`recovery`); `reversible_alternative`/`recovery`
    are `None` exactly when the caller declares no such path genuinely
    exists (never fabricated -- Q1-D6/design R-2 item 2).
    """
    if not destructive or confirmation != phrase:
        fail(
            "DESTRUCTIVE_CONFIRMATION_REQUIRED",
            message,
            status=409,
            details={
                "required_confirmation": phrase,
                "consequence": consequence,
                "reversible_alternative": reversible_alternative,
                "recovery": recovery,
            },
        )


FIELD_TYPES = {"string", "integer", "number", "boolean", "object", "array"}
MAX_INDEX_FIELDS = 16

SCHEMA_OPERATIONS = {"create_entity", "add_field", "drop_entity", "create_index", "drop_index"}
_SCHEMA_KEYS = {"operation", "entity", "field", "fields", "destructive", "confirmation", "revision", "index", "unique", "field_type"}


@dataclass(frozen=True)
class BoundSchemaOperation:
    operation: str
    entity: str
    field: str | None
    fields: tuple[str, ...]
    destructive: bool
    confirmation: Any = None
    field_type: str | None = None
    index: str | None = None
    index_fields: tuple[str, ...] = ()
    unique: bool = False


def bind_schema_operation(operation: Any, *, developer: bool) -> BoundSchemaOperation:
    if not developer:
        fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
    if not isinstance(operation, dict):
        fail("VALIDATION_FAILED", "Schema operation must be an object.")
    if set(operation) - _SCHEMA_KEYS:
        fail("VALIDATION_FAILED", "Schema operation shape is not supported.")
    name = operation.get("operation")
    entity = validate_identifier(operation.get("entity", ""))
    if "revision" in operation:
        # WP-2 review minor (e): `revision` was previously an accepted-but-
        # unused key (schema-level optimistic locking has no implementation
        # here) -- silently accepting and ignoring it is exactly the kind
        # of gap `field_type`'s own precedent below closes, so stop
        # tolerating it instead of leaving it a silent no-op.
        fail("CAPABILITY_UNSUPPORTED", "Schema operation optimistic locking is not available.")
    if name != "add_field" and "field_type" in operation:
        # R-2 (corrigendum m-1): `field_type` is accepted only by
        # `add_field`; every other operation rejects it exactly as before
        # this contract version did (this key simply didn't exist in
        # `_SCHEMA_KEYS` then), so this is not new external behaviour.
        fail("VALIDATION_FAILED", "field_type is only supported by add_field.")
    if name != "create_index":
        # WP-2 review M-3: `index`/`unique` are meaningful only to
        # `create_index` (`drop_index` additionally accepts `index` as the
        # name to drop, but never `unique`) -- the same "don't silently
        # tolerate a key this operation does not use" principle as
        # `field_type` above, applied to this pair.
        if "unique" in operation:
            fail("VALIDATION_FAILED", "unique is only supported by create_index.")
        if "index" in operation and name != "drop_index":
            fail("VALIDATION_FAILED", "index is only supported by create_index/drop_index.")
    if "destructive" in operation and not isinstance(operation["destructive"], bool):
        # Review blocker B-1: symmetric with `bind_mutation`'s identical
        # check above -- a non-boolean truthy `destructive` (a string, an
        # int, an object) must never be silently coerced into `True` by a
        # loose `bool(...)` cast downstream. This is a shape check (contract
        # `SchemaOperationRequest.destructive: {"type": "boolean"}`), so it
        # runs here, before the destructive-confirmation gate itself, per
        # contract `evaluation_order` (shape validation precedes
        # confirmation evaluation).
        fail("VALIDATION_FAILED", "Destructive flag must be boolean.")
    fields: tuple[str, ...] = ()
    field_name: str | None = None
    field_type: str | None = None
    index_name: str | None = None
    index_fields: tuple[str, ...] = ()
    unique = False
    if name == "create_entity":
        _reject_reserved_prefix(entity)
        raw_fields = operation.get("fields", [])
        if not isinstance(raw_fields, list) or len(raw_fields) > 100:
            fail("VALIDATION_FAILED", "Schema fields must be a bounded list.")
        validated: list[str] = []
        for candidate in raw_fields:
            validate_identifier(candidate)
            _reject_reserved_field(candidate)
            if candidate in validated:
                fail("CONFLICT", "Field already exists.", status=409)
            validated.append(candidate)
        fields = tuple(validated)
    elif name == "add_field":
        field_name = validate_identifier(operation.get("field", ""))
        _reject_reserved_field(field_name)
        if "field_type" in operation:
            field_type = operation["field_type"]
            if field_type not in FIELD_TYPES:
                fail("VALIDATION_FAILED", "Unsupported field type.", details={"field": field_name})
    elif name == "create_index":
        # R-5: the physical index name is `{entity}__{index}` (double
        # underscore separated), so a client index name containing `__`
        # would make that composition ambiguous to invert -- rejected
        # outright (corrigendum m-2), as is a composed name over the
        # identifier length limit.
        index_name = validate_identifier(operation.get("index", ""))
        _reject_reserved_prefix(index_name)
        if "__" in index_name:
            fail("VALIDATION_FAILED", "Index name must not contain a double underscore.")
        composed_length = len(entity.encode("utf-8")) + 2 + len(index_name.encode("utf-8"))
        if composed_length > MAX_IDENTIFIER_LENGTH:
            fail("VALIDATION_FAILED", "The composed index name exceeds the identifier length limit.")
        raw_fields = operation.get("fields", [])
        if not isinstance(raw_fields, list) or not (1 <= len(raw_fields) <= MAX_INDEX_FIELDS):
            fail("VALIDATION_FAILED", "Index fields must list between 1 and 16 fields.")
        validated = []
        for candidate in raw_fields:
            validate_identifier(candidate)
            if candidate == "id":
                # WP-2 review M-5: `id` is the address, not a domain
                # uniqueness declaration (§2) -- allowing it here would let
                # a peer publish a `unique_keys` entry upsert can never
                # actually use (values.id is always rejected, R-3), which
                # would also make C-17's positive control unsatisfiable.
                fail("VALIDATION_FAILED", "Address fields cannot be declared as a uniqueness key.", details={"field": "id"})
            if candidate in validated:
                fail("VALIDATION_FAILED", "Index fields must not repeat.")
            validated.append(candidate)
        index_fields = tuple(validated)
        raw_unique = operation.get("unique", False)
        if not isinstance(raw_unique, bool):
            fail("VALIDATION_FAILED", "Unique flag must be boolean.")
        unique = raw_unique
    elif name == "drop_index":
        index_name = validate_identifier(operation.get("index", ""))
        _reject_reserved_prefix(index_name)
    elif name != "drop_entity":
        fail("CAPABILITY_UNSUPPORTED", "Schema operation is not supported by this foundation.")
    return BoundSchemaOperation(name, entity, field_name, fields, bool(operation.get("destructive")), operation.get("confirmation"), field_type, index_name, index_fields, unique)


# --- CCR-13 return shapes (design R2DB_CCR13_STORAGE_V1.md §3, revised per
# WP-2 review M-10) ----------------------------------------------------------
#
# `StorageBackend.query`/`.transact` now carry more than a bare list/count:
# per-row revisions + a continuation signal for query, and resolved insert
# addresses for transact. These are plain frozen dataclasses -- an earlier
# revision made them `list`/`int` subclasses so old equality comparisons
# (`rows == [...]`, `affected == 3`) would keep passing unchanged, but that
# is exactly the "empty green" M-10 flagged: an assertion that never looks
# at `.revisions`/`.assigned_addresses` cannot fail when those fields are
# wrong. Every caller (`service.py`, `postgres.py`'s shim, `ApplicationCell`
# itself, and both `test_foundation.py` and `test_postgres.py`'s direct
# `query()`/`transact()` call sites) is updated to read `.items`/`.affected`
# explicitly instead.


@dataclass(frozen=True)
class QueryOutcome:
    """`query()`'s result: projected rows, plus (CCR-13) their per-row
    revisions (index-aligned with `items`) and pagination continuation.
    `revisions` is `None` when a backend does not maintain revisions yet
    (e.g. `PostgresCell`'s WP-2 shim, which has no revision column until
    WP-3) -- never a wrong-length placeholder list, which `__post_init__`
    enforces as a checked invariant rather than a convention. `has_more` is
    the boolean signal from R-6 (`page.size` window was exceeded by the
    look-ahead fetch); `next_cursor`, when not `None`, is the ready-to-
    return opaque cursor a caller can hand straight to `next_page`.
    """

    items: list[dict[str, Any]]
    revisions: list[str] | None = None
    has_more: bool = False
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if self.revisions is not None and len(self.revisions) != len(self.items):
            raise ValueError("QueryOutcome.revisions must be None (unmaintained) or index-aligned with items")


@dataclass(frozen=True)
class MutationOutcome:
    """`transact()`'s result: the affected-row count, plus (CCR-13) the
    addresses `transact` resolved for insert (and insert-resolved upsert)
    operations, in operation order.

    `assigned_addresses` is `None` when a backend does not maintain
    addresses yet (`PostgresCell`'s WP-2 shim, symmetric with `QueryOutcome.
    revisions`'s own `None` sentinel) -- distinct from `[]`, which means the
    backend does maintain them and this particular batch simply resolved no
    insert (every operation was an update/delete, or an upsert that
    resolved to update).
    """

    affected: int
    assigned_addresses: list[dict[str, Any]] | None = None


# --- value type validation (R-7) -------------------------------------------

# R-7 addendum (WP-3 review blocker-2): PostgreSQL's `bigint` range. A JSON
# integer outside this range passes every existing type check (Python `int`
# has no fixed width) but PostgreSQL rejects it at execution time with a
# non-deterministic-looking `numeric_value_out_of_range` -- a decisive
# client bug that must not surface as a retryable-looking server failure.
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _contains_nul(value: Any) -> bool:
    """`True` if `value` (or, recursively, any string nested inside a
    dict/list) contains a U+0000 (NUL) character. PostgreSQL's `text`/
    `jsonb` storage cannot hold a NUL byte at all (`invalid byte sequence
    for encoding`/`unsupported Unicode escape sequence`) -- another
    decisive client bug (R-7 addendum, WP-3 review blocker-2) that must be
    refused deterministically here, not discovered as a database error.
    """
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_contains_nul(key) or _contains_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_nul(item) for item in value)
    return False


def _check_type(value: Any, field_type: str | None, field_name: str) -> None:
    """Validate `value` against a declared column type before it is bound.

    `field_type` of `None` means the field is untyped (JSONB-equivalent):
    any JSON value is accepted, exactly like before typed columns existed.
    `null` is always accepted regardless of declared type (NOT NULL is out
    of scope for this contract version). A mismatch fails `VALIDATION_
    FAILED` naming only the field -- never the value itself (`errors.
    disclosure`).

    R-7 addendum (WP-3 review blocker-2): beyond the JSON-type check, a
    value's own *domain* is validated too -- an `integer` outside signed
    64-bit range, or a NUL byte anywhere inside a `string`/`object`/`array`/
    untyped value -- both of which `_check_type` alone (a bare `isinstance`
    check) would let through, but PostgreSQL's own storage cannot. Same
    error code/disclosure shape as the type check itself.
    """
    if value is None:
        return
    if field_type is None:
        if _contains_nul(value):
            fail("VALIDATION_FAILED", "Value must not contain a NUL character.", details={"field": field_name})
        return
    if field_type == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
        if ok and not (_INT64_MIN <= value <= _INT64_MAX):
            fail("VALIDATION_FAILED", "Value is out of range for the field's declared type.", details={"field": field_name})
    elif field_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif field_type == "boolean":
        ok = isinstance(value, bool)
    elif field_type == "string":
        ok = isinstance(value, str)
    elif field_type == "object":
        ok = isinstance(value, dict)
    elif field_type == "array":
        ok = isinstance(value, list)
    else:  # pragma: no cover - field_type is always one of FIELD_TYPES or None
        ok = True
    if not ok:
        fail("VALIDATION_FAILED", "Value does not match the field's declared type.", details={"field": field_name})
    if field_type in ("string", "object", "array") and _contains_nul(value):
        fail("VALIDATION_FAILED", "Value must not contain a NUL character.", details={"field": field_name})


def _validate_wildcard_pattern(pattern: str, field_name: str) -> None:
    """`matches`'s grammar check (contract 1.1.0, CCR-13 §0.5 Q-2
    adjudication 5, WP-3 review blocker-2): a pattern ending in a lone,
    unescaped backslash is malformed -- PostgreSQL's own `LIKE` grammar
    does not reject this deterministically at parse time; whether it
    errors depends on the *stored data* it is compared against at
    execution time, which would make an identical request sometimes
    succeed and sometimes fail with `SERVICE_UNAVAILABLE` depending on
    which rows exist. The contract resolves this by requiring
    `VALIDATION_FAILED` up front, in the shared boundary, before any
    backend ever executes the pattern.
    """
    trailing_backslashes = len(pattern) - len(pattern.rstrip("\\"))
    if trailing_backslashes % 2 == 1:
        fail("VALIDATION_FAILED", "matches pattern must not end with an unescaped backslash.", details={"field": field_name})


def _validate_predicate_types(where: list["Predicate"], field_types: dict[str, str | None]) -> None:
    """Type-check every predicate's value up front, independent of which
    rows (if any) it will end up matching (R-7, corrigendum M-9: type
    validation happens before target-row search/precondition resolution --
    see the call sites in `ApplicationCell.query`/`_apply`)."""
    for predicate in where:
        if predicate.operator in _TEXT_ONLY_OPERATORS:
            # Q-2: the operator's own value type is fixed (string), never
            # the target column's declared type -- a typed non-string
            # column is still matched via its text representation, so the
            # column's own declared type is irrelevant to this check.
            if not isinstance(predicate.value, str):
                fail("VALIDATION_FAILED", "This operator's value must be a string.", details={"field": predicate.field})
            if _contains_nul(predicate.value):
                fail("VALIDATION_FAILED", "This operator's value must not contain a NUL character.", details={"field": predicate.field})
            if predicate.operator == "matches":
                _validate_wildcard_pattern(predicate.value, predicate.field)
            continue
        if predicate.operator in ("eq", "ne") and predicate.value is None:
            # WP-3 confirmation review N-3: `= NULL`/`<> NULL` is always
            # UNKNOWN in SQL -- silently, permanently matching zero rows,
            # never what a caller means. `is_null` exists precisely for
            # this comparison; refusing here is more diagnostic to an AI
            # agent client than quietly returning an empty result forever.
            fail("VALIDATION_FAILED", "eq/ne do not accept a null value; use is_null instead.", details={"field": predicate.field})
        declared_type = field_types.get(predicate.field)
        if predicate.operator == "in":
            if isinstance(predicate.value, list):
                for item in predicate.value:
                    _check_type(item, declared_type, predicate.field)
        elif predicate.operator != "is_null":
            _check_type(predicate.value, declared_type, predicate.field)


# --- page size (contract `Page.size`) ---------------------------------------

# `spec/data-service-api.v1.json`'s `Page.size` schema: `{"minimum": 1,
# "maximum": 1000}` -- a fixed contract ceiling, independent of
# `ResourceLimits.result_items` (a deployment-tunable resource class that
# could in principle be configured to any positive value). A client
# request for a page larger than the contract itself allows is a request
# outside the contract's own vocabulary (`VALIDATION_FAILED`), not a
# resource a deployment could simply raise (WP-4 review minor-1).
MAX_PAGE_SIZE = 1000


def validate_page_size(page_size: int, limits: ResourceLimits) -> None:
    if page_size <= 0:
        fail("LIMIT_EXCEEDED", "Page size must be positive.", status=413, details={"resource": "result_items", "limit_class": "result_items", "limit": limits.result_items})
    if page_size > MAX_PAGE_SIZE:
        fail("VALIDATION_FAILED", "Page size exceeds the contract maximum.", details={"limit": MAX_PAGE_SIZE})


# --- order_by / cursor pagination (R-6) ------------------------------------

MAX_ORDER_BY_FIELDS = 10
MAX_CURSOR_OFFSET = 10**9
# PostgreSQL's own jsonb cross-type ordering (ascending: String < Number <
# Boolean < Array < Object), used by `_sort_key` below for an untyped
# (JSONB-equivalent) column whose stored values happen to differ in JSON
# type (WP-2 review M-6). Typed columns never exercise more than one of
# these ranks, since R-7 already guarantees a uniform type there.
_JSON_TYPE_RANK = {"string": 0, "number": 1, "boolean": 2, "array": 3, "object": 4}


def _resolve_order_by(order_by: Any, known_fields: set[str]) -> list[tuple[str, str]]:
    spec: list[tuple[str, str]] = []
    if order_by is not None:
        if not isinstance(order_by, list) or len(order_by) > MAX_ORDER_BY_FIELDS:
            fail("VALIDATION_FAILED", "order_by must be a bounded list.")
        seen_fields: set[str] = set()
        for item in order_by:
            if not isinstance(item, dict) or "field" not in item or set(item) - {"field", "direction"}:
                fail("VALIDATION_FAILED", "order_by entry shape is not supported.")
            field_name = validate_identifier(item["field"])
            if field_name not in known_fields:
                fail("NOT_FOUND", "Field was not found.", status=404)
            if field_name in seen_fields:
                # WP-2 review minor (b): a field named twice is always
                # either redundant or self-contradictory (opposite
                # directions) -- reject rather than silently keep only one.
                fail("VALIDATION_FAILED", "order_by must not repeat a field.")
            seen_fields.add(field_name)
            direction = item.get("direction", "asc")
            if direction not in ("asc", "desc"):
                fail("VALIDATION_FAILED", "order_by direction must be asc or desc.")
            spec.append((field_name, direction))
    if not any(field_name == "id" for field_name, _ in spec):
        # R-6: deterministic ordering requires a total order; `id` is the
        # one column every row differs on, so it is appended (ascending)
        # whenever the caller's own order_by does not already mention it.
        spec.append(("id", "asc"))
    return spec


def _sort_key(value: Any) -> tuple[Any, ...]:
    """A total ordering key matching PostgreSQL's own defaults (WP-2 review
    M-6): a `NULL` sorts as if larger than any non-null value (`NULLS LAST`
    for ascending, `NULLS FIRST` for descending -- both fall out of giving
    it the single highest rank here and reusing `_sort_rows`'s existing
    per-field `reverse=(direction == "desc")`, with no direction-specific
    branch needed in this function). Non-null values are additionally
    grouped by jsonb type rank first, so two rows whose values for the same
    untyped (JSONB-equivalent) column differ in JSON type never reach a
    native `<` comparison between incompatible Python types.
    """
    if value is None:
        return (1, 0, "")
    if isinstance(value, bool):
        return (0, _JSON_TYPE_RANK["boolean"], int(value))
    if isinstance(value, (int, float)):
        return (0, _JSON_TYPE_RANK["number"], value)
    if isinstance(value, str):
        return (0, _JSON_TYPE_RANK["string"], value)
    if isinstance(value, list):
        return (0, _JSON_TYPE_RANK["array"], json.dumps(value, sort_keys=True, default=str))
    if isinstance(value, dict):
        return (0, _JSON_TYPE_RANK["object"], json.dumps(value, sort_keys=True, default=str))
    return (0, _JSON_TYPE_RANK["string"], str(value))  # pragma: no cover - values are always JSON-shaped


def _sort_rows(rows: list[dict[str, Any]], spec: list[tuple[str, str]]) -> list[dict[str, Any]]:
    result = list(rows)
    for field_name, direction in reversed(spec):
        result.sort(key=lambda row, f=field_name: _sort_key(row.get(f)), reverse=(direction == "desc"))
    return result


def _shape_hash(application_id: str, entity: str, select: list[str], where: list[Predicate], order_spec: list[tuple[str, str]], size: int) -> str:
    payload = {
        # WP-2 review minor (a): binding the hash to the Application scope
        # and entity too (not just select/where/order_by/size) means a
        # cursor minted under one application/entity can never even
        # coincidentally validate against another's query of the same
        # select/where/order_by/size shape.
        "application": application_id,
        "entity": entity,
        "select": list(select),
        "where": [[p.field, p.operator, p.value] for p in where],
        "order_by": [list(item) for item in order_spec],
        "size": size,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _encode_cursor(offset: int, shape: str) -> str:
    payload = json.dumps({"o": offset, "q": shape}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: Any, expected_shape: str) -> int:
    if not isinstance(cursor, str) or not cursor:
        fail("VALIDATION_FAILED", "Cursor is not valid.")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception:
        fail("VALIDATION_FAILED", "Cursor could not be decoded.")
    if not isinstance(payload, dict) or set(payload) != {"o", "q"}:
        fail("VALIDATION_FAILED", "Cursor shape is not supported.")
    offset = payload["o"]
    shape = payload["q"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset > MAX_CURSOR_OFFSET:
        fail("VALIDATION_FAILED", "Cursor offset is out of range.")
    if not isinstance(shape, str) or shape != expected_shape:
        # R-6, corrigendum m-3: a cursor minted for a different query shape
        # (different select/where/order_by/size) never silently pages
        # through the wrong result set -- it fails loudly instead.
        fail("VALIDATION_FAILED", "Cursor does not match the current query shape.")
    return offset


@dataclass
class ApplicationCell:
    application_id: str
    entities: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # entity -> {field_name: declared type, or None if untyped/JSONB-
    # equivalent}. Always includes "id" -> "integer"; never includes the
    # invisible "_r2db_revision" (R-3/R-4: never a known/selectable field).
    schema: dict[str, dict[str, str | None]] = field(default_factory=dict)
    # entity -> client index name -> {"fields": (...), "unique": bool}
    # (R-5). Declared uniqueness keys are exactly the unique=True entries.
    indexes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    schema_revision: int = 0
    # entity -> highest `id` ever assigned. Monotonic, never decremented by
    # delete, and deliberately NOT rolled back when a `transact()` batch
    # containing an insert later fails (R-1: address_reuse is "never" --
    # this mirrors PostgreSQL's own `GENERATED ALWAYS AS IDENTITY`, whose
    # sequence is non-transactional and does not rewind on ROLLBACK either).
    # Popped when the entity is dropped and starts fresh at 1 if the same
    # name is later recreated (R-1: reuse is scoped to one entity's
    # lifetime, and `apply_schema`'s own atomic rollback below *does*
    # restore this on a failed drop_entity, since DDL itself is
    # transactional even though sequence consumption is not).
    _next_id: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for entity, rows in list(self.entities.items()):
            validate_identifier(entity)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                fail("VALIDATION_FAILED", "Entity rows must be a list of objects.")
            user_fields: set[str] = set()
            for row in rows:
                if "id" in row:
                    fail("VALIDATION_FAILED", "The id field is server-assigned and cannot be supplied.", details={"field": "id"})
                user_fields.update(row.keys())
            for name in user_fields:
                validate_identifier(name)
                _reject_reserved_field(name)
            declared = self.schema.setdefault(entity, {})
            for name in user_fields:
                declared.setdefault(name, None)
            declared.setdefault("id", "integer")
            self.indexes.setdefault(entity, {})
            seed_rows = rows
            self.entities[entity] = []
            # m-9: seed rows go through the same insertion path as a normal
            # insert, so they receive server-assigned id/revision exactly
            # like any client-issued insert would.
            for seed in seed_rows:
                self._insert_row(entity, dict(seed))

    # ---- query -----------------------------------------------------------

    def query(
        self,
        entity: str,
        *,
        select: list[str],
        where: list[Predicate],
        page_size: int,
        limits: ResourceLimits,
        order_by: list[dict[str, Any]] | None = None,
        cursor: str | None = None,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> QueryOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        validate_page_size(page_size, limits)
        if entity not in self.entities:
            fail("NOT_FOUND", "Entity was not found.", status=404)
        field_types = self.schema.get(entity, {})
        known_fields = set(field_types.keys())
        validate_projection(select, known_fields)
        validate_predicates(where, known_fields)
        order_spec = _resolve_order_by(order_by, known_fields)
        # WP-2 review minor (c): order_by clauses count toward query
        # complexity like select/where terms already do (the raw, caller-
        # supplied count -- not the implicit trailing `id asc` `
        # _resolve_order_by` may have appended, which is bookkeeping this
        # engine adds, not complexity the caller asked for).
        order_by_count = len(order_by) if order_by else 0
        limits.check("query_complexity", len(where) + len(select) + order_by_count)
        # R-7, corrigendum M-9: validate every predicate's value type before
        # touching stored rows at all (a type mismatch is a client bug, and
        # letting a query with one execute far enough to hit some other
        # error first is misleading, not merely unnecessary work).
        _validate_predicate_types(where, field_types)
        try:
            rows = [row for row in self.entities[entity] if all(_matches(row, p, field_types) for p in where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
        rows = _sort_rows(rows, order_spec)
        shape = _shape_hash(self.application_id, entity, select, where, order_spec, page_size)
        offset = 0
        if cursor is not None:
            offset = _decode_cursor(cursor, shape)
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        window = rows[offset : offset + page_size + 1]
        has_more = len(window) > page_size
        page_rows = window[:page_size]
        items = [{field_name: row.get(field_name) for field_name in select} for row in page_rows]
        revisions = [row["_r2db_revision"] for row in page_rows]
        next_cursor = _encode_cursor(offset + page_size, shape) if has_more else None
        return QueryOutcome(items=items, revisions=revisions, has_more=has_more, next_cursor=next_cursor)

    def catalog(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name in sorted(self.entities):
            fields = sorted(self.schema.get(name, {}).keys())
            unique_keys = [
                {"name": index_name, "fields": list(info["fields"])}
                for index_name, info in sorted(self.indexes.get(name, {}).items())
                if info["unique"]
            ]
            result.append(
                {
                    "entity": name,
                    "fields": fields,
                    "mutation_class": "mutable",
                    "address_fields": ["id"],
                    "address_reuse": "never",
                    "unique_keys": unique_keys,
                }
            )
        return result

    def transact(self, entity: str, operations: list[dict[str, Any]], limits: ResourceLimits, *, deadline: float | None = None, clock: Callable[[], float] | None = None) -> MutationOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.")
        limits.check("batch_items", len(operations))
        if entity not in self.entities:
            fail("NOT_FOUND", "Entity was not found.", status=404)
        before = deepcopy(self.entities[entity])
        try:
            affected = 0
            assigned_addresses: list[dict[str, Any]] = []
            for operation in operations:
                if deadline is not None and clock is not None:
                    # WP-2 review M-2: per-operation deadline check, not
                    # only before/after the whole batch -- a unique-index
                    # write check is O(rows) per operation, so an O(N^2)-ish
                    # batch (many operations against a large, uniquely-
                    # indexed entity) could otherwise run well past the
                    # execution budget before the next checkpoint.
                    limits.check_deadline(deadline, clock)
                count, address = self._apply(entity, operation)
                affected += count
                if address is not None:
                    assigned_addresses.append(address)
                limits.check("result_items", affected)
            if deadline is not None and clock is not None:
                limits.check_deadline(deadline, clock)
            return MutationOutcome(affected=affected, assigned_addresses=assigned_addresses)
        except Exception:
            self.entities[entity] = before
            raise

    def _apply(self, entity: str, operation: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        field_types = self.schema.get(entity, {})
        known_fields = set(field_types.keys())
        bound = bind_mutation(operation, known_fields)

        if bound.operation == "insert":
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), key)
            self._check_unique_conflict(entity, bound.values, exclude_id=None)
            row = self._insert_row(entity, bound.values)
            return 1, {"address": {"id": row["id"]}}

        if bound.operation == "upsert":
            return self._apply_upsert(entity, bound, field_types)

        # update / delete: R-7, corrigendum M-9 -- validate every value's
        # type (predicate values, and for `update` the write values too)
        # before resolving a precondition or searching for target rows at
        # all, symmetric with the `insert` branch above.
        _validate_predicate_types(bound.where, field_types)
        if bound.operation == "update":
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), key)

        try:
            matches = [row for row in self.entities[entity] if all(_matches(row, p, field_types) for p in bound.where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")

        if bound.operation == "delete":
            # m-5: destructive confirmation is checked before any
            # precondition evaluation -- an unconfirmed delete is refused
            # before a revision precondition is even looked at.
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                delete_confirmation_phrase(entity, bound.where, self.schema_revision),
                "Delete requires explicit destructive confirmation.",
                consequence="Rows matching the filter are permanently deleted; there is no in-band restore.",
                reversible_alternative=None,
                recovery=None,
            )
            if bound.expected_revision is not None:
                target = [row for row in matches if row["_r2db_revision"] == bound.expected_revision]
                if not target:
                    self._fail_precondition(matches)
                self.entities[entity].remove(target[0])
                return 1, None
            for row in matches:
                self.entities[entity].remove(row)
            return len(matches), None

        # update
        if bound.expected_revision is not None:
            target = [row for row in matches if row["_r2db_revision"] == bound.expected_revision]
            if not target:
                self._fail_precondition(matches)
            row = target[0]
            self._check_unique_conflict(entity, {**row, **bound.values}, exclude_id=row["id"])
            row.update(bound.values)
            row["_r2db_revision"] = str(uuid.uuid4())
            return 1, None
        if not bound.values:
            return len(matches), None
        for row in matches:
            self._check_unique_conflict(entity, {**row, **bound.values}, exclude_id=row["id"])
            row.update(bound.values)
            row["_r2db_revision"] = str(uuid.uuid4())
        return len(matches), None

    def _apply_upsert(self, entity: str, bound: BoundMutation, field_types: dict[str, str | None]) -> tuple[int, dict[str, Any] | None]:
        declared = {name: info for name, info in self.indexes.get(entity, {}).items() if info["unique"]}
        if not declared:
            # R-5 / §0.5 Q-1 (adjudicated 案B): an entity declaring no
            # uniqueness key at all has no existence test upsert could use.
            fail("CAPABILITY_UNSUPPORTED", "Upsert requires a declared domain uniqueness key.")
        if bound.unique_key is not None:
            # Q-1 案B: an explicit `unique_key` always names the deciding
            # key by catalog name, whether the entity has one declared key
            # or several -- a name that does not match any of them is
            # NOT_FOUND, never silently ignored in favour of a default.
            if bound.unique_key not in declared:
                fail("NOT_FOUND", "No declared uniqueness key matches unique_key.", status=404)
            key_name = bound.unique_key
        elif len(declared) == 1:
            key_name = next(iter(declared))
        else:
            fail("VALIDATION_FAILED", "unique_key is required when an entity declares more than one uniqueness key.")
        if bound.where:
            fail("VALIDATION_FAILED", "Upsert does not accept a filter; its existence test is the entity's declared uniqueness key.")
        key_fields = declared[key_name]["fields"]
        for key_field in key_fields:
            if bound.values.get(key_field) is None:
                fail("VALIDATION_FAILED", "Upsert values must include every uniqueness key field.", details={"field": key_field})
        # R-7, corrigendum M-9: type-check before searching for an existing
        # row (symmetric with insert/update above).
        for key, value in bound.values.items():
            _check_type(value, field_types.get(key), key)
        existing = [row for row in self.entities[entity] if all(row.get(f) == bound.values[f] for f in key_fields)]
        update_values = {k: v for k, v in bound.values.items() if k not in key_fields}
        if bound.expected_revision is not None:
            # R-5: a precondition never resolves an upsert to an insert --
            # no key match is NOT_FOUND, exactly like update/delete.
            if not existing:
                fail("NOT_FOUND", "No row matches the supplied uniqueness key.", status=404)
            row = existing[0]
            if row["_r2db_revision"] != bound.expected_revision:
                fail("PRECONDITION_FAILED", "The row's revision no longer matches the supplied precondition.", status=412)
            self._check_unique_conflict(entity, {**row, **update_values}, exclude_id=row["id"])
            row.update(update_values)
            row["_r2db_revision"] = str(uuid.uuid4())
            return 1, None
        if existing:
            row = existing[0]
            self._check_unique_conflict(entity, {**row, **update_values}, exclude_id=row["id"])
            row.update(update_values)
            row["_r2db_revision"] = str(uuid.uuid4())
            return 1, None
        self._check_unique_conflict(entity, bound.values, exclude_id=None)
        row = self._insert_row(entity, bound.values)
        return 1, {"address": {"id": row["id"]}}

    def _fail_precondition(self, matches: list[dict[str, Any]]) -> None:
        # R-4, corrigendum M-2: the target of an `expected_revision`
        # mutation is "predicate match AND revision match" -- a predicate
        # match with no revision match means the precondition's assertion
        # about a *known* row was wrong (PRECONDITION_FAILED); no predicate
        # match at all means there was no row to assert about (NOT_FOUND).
        if matches:
            fail("PRECONDITION_FAILED", "The row's revision no longer matches the supplied precondition.", status=412)
        fail("NOT_FOUND", "No row matches the supplied filter.", status=404)

    def _insert_row(self, entity: str, values: dict[str, Any]) -> dict[str, Any]:
        next_id = self._next_id.get(entity, 0) + 1
        self._next_id[entity] = next_id
        row: dict[str, Any] = {"id": next_id, "_r2db_revision": str(uuid.uuid4())}
        row.update(values)
        self.entities[entity].append(row)
        return row

    def _check_unique_conflict(self, entity: str, candidate: dict[str, Any], *, exclude_id: int | None) -> None:
        for name, info in self.indexes.get(entity, {}).items():
            if not info["unique"]:
                continue
            key = tuple(candidate.get(f) for f in info["fields"])
            if any(v is None for v in key):
                # SQL unique-index convention: NULL is distinct from NULL,
                # so a row with any null key field never conflicts.
                continue
            for row in self.entities[entity]:
                if row["id"] == exclude_id:
                    continue
                if tuple(row.get(f) for f in info["fields"]) == key:
                    fail("CONFLICT", "A declared uniqueness key would be violated.", status=409, details={"index": name})

    def _existing_duplicate(self, entity: str, fields: tuple[str, ...]) -> bool:
        seen: set[tuple[Any, ...]] = set()
        for row in self.entities.get(entity, []):
            key = tuple(row.get(f) for f in fields)
            if any(v is None for v in key):
                continue
            if key in seen:
                return True
            seen.add(key)
        return False

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        bound = bind_schema_operation(operation, developer=developer)
        # WP-2 review M-2: indexes count toward `schema_objects` too, like
        # entities/fields already did (SI-08: an index is a real resource,
        # and every write against a uniquely-indexed entity pays a
        # per-index scan cost proportional to the index count).
        current_objects = sum(len(fields) + 1 for fields in self.schema.values()) + sum(len(idx) for idx in self.indexes.values())
        if bound.operation == "create_entity":
            projected_objects = current_objects + 1 + len(bound.fields)
        elif bound.operation == "add_field":
            projected_objects = current_objects + 1
        elif bound.operation == "drop_entity":
            projected_objects = current_objects - (len(self.schema.get(bound.entity, {})) + 1) - len(self.indexes.get(bound.entity, {}))
        elif bound.operation == "create_index":
            projected_objects = current_objects + 1
        else:  # drop_index
            projected_objects = current_objects - 1
        limits.check("schema_objects", projected_objects)
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        before_entities = deepcopy(self.entities)
        before_schema = deepcopy(self.schema)
        before_indexes = deepcopy(self.indexes)
        before_next_id = dict(self._next_id)
        before_revision = self.schema_revision
        if bound.operation == "create_entity":
            if bound.entity in self.entities:
                fail("CONFLICT", "Entity already exists.", status=409)
            self.entities[bound.entity] = []
            self.schema[bound.entity] = {name: None for name in bound.fields}
            self.schema[bound.entity]["id"] = "integer"
            self.indexes[bound.entity] = {}
        elif bound.operation == "drop_entity":
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                drop_entity_confirmation_phrase(bound.entity, self.schema_revision),
                "Drop requires explicit destructive confirmation.",
                consequence="The entity and all of its rows and indexes are permanently destroyed; re-creating an entity of the same name creates a new entity, not a restore.",
                reversible_alternative=None,
                recovery=None,
            )
            self.entities.pop(bound.entity, None)
            self.schema.pop(bound.entity, None)
            self.indexes.pop(bound.entity, None)
            # R-1: address_reuse is scoped to one entity's lifetime; a drop
            # ends that lifetime, so a later create_entity of the same name
            # is a new entity and its addresses start at 1 again.
            self._next_id.pop(bound.entity, None)
        elif bound.operation == "add_field":
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.field in self.schema.setdefault(bound.entity, {}):
                fail("CONFLICT", "Field already exists.", status=409)
            self.schema[bound.entity][bound.field] = bound.field_type
        elif bound.operation == "create_index":
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            known = set(self.schema.get(bound.entity, {}).keys())
            for index_field in bound.index_fields:
                if index_field not in known:
                    fail("NOT_FOUND", "Field was not found.", status=404)
            if bound.index in self.indexes.get(bound.entity, {}):
                fail("CONFLICT", "Index already exists.", status=409)
            if bound.unique and self._existing_duplicate(bound.entity, bound.index_fields):
                # WP-2 review M-1: unify with every other CONFLICT in this
                # module at HTTP 409 (this one previously fell through to
                # `fail`'s 400 default).
                fail("CONFLICT", "Existing data violates the requested uniqueness.", status=409)
            self.indexes.setdefault(bound.entity, {})[bound.index] = {"fields": bound.index_fields, "unique": bound.unique}
        else:  # drop_index
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.index not in self.indexes.get(bound.entity, {}):
                fail("NOT_FOUND", "Index was not found.", status=404)
            # R-5, corrigendum M-6: dropping a unique index removes a
            # guardrail (uniqueness) and can silently re-enable upsert's
            # CAPABILITY_UNSUPPORTED gate to flip -- SI-09 destructive
            # confirmation applies exactly like drop_entity.
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                drop_index_confirmation_phrase(bound.entity, bound.index, self.schema_revision),
                "Dropping an index requires explicit destructive confirmation.",
                consequence="The index is destroyed; query semantics are unaffected, only performance (and any uniqueness guarantee it enforced) are lost.",
                reversible_alternative=None,
                recovery="create_index with the same definition restores it -- an index carries no data of its own, so this fully restores a non-unique index; recreating a UNIQUE index re-validates existing rows against that uniqueness and can instead fail with CONFLICT if data written after the drop now violates it.",
            )
            del self.indexes[bound.entity][bound.index]
        if deadline is not None and clock is not None:
            try:
                limits.check_deadline(deadline, clock)
            except Exception:
                self.entities = before_entities
                self.schema = before_schema
                self.indexes = before_indexes
                self._next_id = before_next_id
                self.schema_revision = before_revision
                raise
        self.schema_revision += 1
        return self.schema_revision


# Contract 1.1.0 (CCR-13, §0.5 Q-2): `matches`'s wildcard grammar is
# `%` (any sequence, including empty), `_` (exactly one character), and
# `\` (escapes the following character, including a literal `%`/`_`/`\`
# itself). Compiled to a Python regex, anchored full-match, case-sensitive
# (Q-2: "両演算子とも大文字小文字を区別") -- `re.escape` on every literal
# character/escaped character means no client-supplied text can inject
# regex metacharacters, so this never raises on arbitrary input.
def _wildcard_pattern(pattern: str) -> "re.Pattern[str]":
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            if i + 1 < n:
                out.append(re.escape(pattern[i + 1]))
                i += 2
            else:
                # WP-3 review blocker-2 (Q-2 adjudication 5): a trailing
                # lone, unescaped backslash is malformed grammar, not a
                # literal backslash to match -- `_validate_wildcard_pattern`
                # (called by `_validate_predicate_types`, upstream of every
                # caller of this function) already rejects it with
                # `VALIDATION_FAILED` before this function ever runs, so
                # this branch is unreachable in practice. No permissive
                # "treat as literal" fallback remains here: the reference
                # implementation must not silently accept something the
                # deployed backend (PostgreSQL's own `LIKE` grammar) cannot
                # reliably execute.
                fail("VALIDATION_FAILED", "matches pattern must not end with an unescaped backslash.")
            continue
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("(?s)\\A" + "".join(out) + "\\Z")


def _float8out_text(value: float) -> str:
    """PostgreSQL `double precision`'s own text-output function,
    `float8out` (WP-3 confirmation review N-1) -- reproduced ONLY for a
    TYPED `"number"` column's TOP-LEVEL scalar (`PostgresCell._text_
    expression`'s plain `::text` cast on a real `double precision` column
    invokes this natively; nothing else in this file does). An integer-
    valued float drops its Python-repr trailing `.0` (`100.0` -> `"100"`).
    A value already in scientific notation (`repr`'s own choice for
    sufficiently large/small magnitudes, e.g. `1e+20`) never ends in `.0`
    to begin with, and PostgreSQL's own `float8out` for such magnitudes
    also uses scientific notation matching Python's -- so it passes
    through unchanged.
    """
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def _jsonb_numeric_text(value: float) -> str:
    """PostgreSQL jsonb's own numeric storage/output (WP-3 confirmation
    review N-1) -- used for every OTHER float position: an UNTYPED top-
    level column, or ANY nested position inside a dict/list, regardless of
    the enclosing field's own declared type (jsonb storage is jsonb either
    way, whether the column is bare or one of this backend's `_r2db_json_
    object`/`_r2db_json_array` DOMAINs over it). Confirmed empirically
    against a real server: jsonb preserves a number's original literal
    text almost verbatim, INCLUDING trailing zeros (`'100.0'::jsonb #>>
    '{}'` stays `"100.0"`, never drops the `.0` the way `float8out` does),
    but always EXPANDS scientific notation to full plain-decimal digits
    (`'1e+20'::jsonb #>> '{}'` -> `"100000000000000000000"`, never
    `"1e+20"`).

    `json.dumps(value)` reproduces the exact text psycopg's `Jsonb` adapter
    sends at INSERT time (this project's own round-trip) -- confirmed
    empirically to match jsonb's stored/re-emitted text byte-for-byte for
    every case that does not need exponent expansion. `Decimal` expands
    the scientific-notation case the same way PostgreSQL's own numeric
    parser does (exact decimal arithmetic, no float re-rounding): `Decimal
    (json.dumps(value))` parses the very same text, and `format(...,
    "f")` renders it in fixed (non-exponential) notation.
    """
    text = json.dumps(value)
    if "e" in text or "E" in text:
        return format(Decimal(text), "f")
    return text


def _jsonb_scalar_text(value: Any) -> str:
    """A JSON scalar's PostgreSQL `jsonb` text-output form for a NESTED
    position (inside a dict/list), or for an untyped, non-float, top-level
    scalar: `boolean` is the lowercase `true`/`false` literal; `float` uses
    `_jsonb_numeric_text` above (jsonb's own numeric rules, never
    `float8out` -- a nested float is never affected by the enclosing
    field's own declared type, since nesting only exists inside jsonb
    storage to begin with).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _jsonb_numeric_text(value)
    if value is None:
        return "null"
    return str(value)  # pragma: no cover - value is always JSON-shaped


def _jsonb_text(value: Any) -> str:
    """PostgreSQL's own `jsonb` text-output rendering for a dict/list value
    (WP-3 review N-1/N-2), used both directly (`_predicate_text`, below)
    and recursively for a nested dict/list. Object key order is
    PostgreSQL's own storage order -- *not* the order the keys were
    written in JSON source, and not Python's default string sort either:
    `(byte length, byte value)`, ascending (confirmed empirically against a
    real server). Nested strings are quoted (`json.dumps`, `ensure_ascii=
    False` to keep non-ASCII characters literal like PostgreSQL's own jsonb
    text output does, rather than Python's default `\\uXXXX` escaping);
    nested scalars reuse `_jsonb_scalar_text` above (never `_float8out_
    text`: nesting only exists inside jsonb storage, so a nested float is
    always jsonb's own numeric rules, independent of whatever the
    enclosing top-level field's own declared type is).
    """
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: (len(k.encode("utf-8")), k.encode("utf-8")))
        parts = [f"{json.dumps(key, ensure_ascii=False)}: {_jsonb_text(value[key])}" for key in keys]
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_jsonb_text(item) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return _jsonb_scalar_text(value)


def _predicate_text(value: Any, field_type: str | None) -> str:
    """The text representation `contains`/`matches` compare a non-string
    row value against (WP-3 review D-1~D-4: "型付き非文字列列にも text
    表現で適用可") -- matching `PostgresCell._text_expression`'s own text
    form (a typed column's `::text` cast, or an untyped JSONB scalar's
    `#>> '{}'` unwrap) as closely as Python's/PostgreSQL's differing native
    formatting allows.

    `field_type` (WP-3 confirmation review N-1 correction: this parameter
    did not exist in the first pass, which applied `float8out`-style
    formatting unconditionally -- correct for a typed `"number"` column,
    but WRONG for an untyped one, where jsonb's own numeric storage rules
    apply instead and disagree with `float8out` on both trailing zeros and
    scientific-notation expansion) decides which rule a TOP-LEVEL float
    uses: `float8out` only when this field is itself a typed `"number"`
    column (matching `PostgresCell._text_expression`'s plain `::text`
    cast); jsonb's own numeric rules for everything else, including an
    untyped top-level column. A top-level dict/list (`_jsonb_text`) and any
    NESTED position inside one always use jsonb's own rules regardless of
    `field_type` -- nesting only exists inside jsonb storage, which has no
    "typed number" concept at all beneath its own root.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return _jsonb_text(value)
    if isinstance(value, float) and field_type == "number":
        return _float8out_text(value)
    return _jsonb_scalar_text(value)


def _matches(row: dict[str, Any], predicate: Predicate, field_types: dict[str, str | None]) -> bool:
    """Pure comparison -- value type validation is done up front by
    `_validate_predicate_types` (R-7, corrigendum M-9), not per-row here.

    WP-3 review D-1~D-4: predicate semantics are unified with PostgreSQL's
    own SQL three-valued logic rather than Python's -- a NULL row is never
    made to raise (`contains`/`matches`) or to look "not equal"/"in the
    list" (`ne`/`in`) just because Python's own `is None` comparisons
    happen to differ from SQL's "comparison against NULL is UNKNOWN,
    excluded from the result" rule. `eq`/`lt`/`lte`/`gt`/`gte` are
    deliberately left as-is: this reference implementation's own
    documented, accepted cross-backend divergence (see `postgres.py`'s
    module docstring) for ordering comparisons against mismatched/absent
    values is unaffected by this fix.

    `field_types` (WP-3 confirmation review N-1 correction): needed so
    `contains`/`matches` can pass the predicate's OWN field's declared
    type to `_predicate_text`, which is what decides whether a top-level
    float uses `float8out` (typed `"number"` column) or jsonb's own
    numeric rules (everything else) -- see `_predicate_text`'s docstring.
    """
    actual = row.get(predicate.field)
    expected = predicate.value
    if predicate.operator == "eq":
        return actual == expected
    if predicate.operator == "ne":
        if actual is None:
            return False
        return actual != expected
    if predicate.operator == "lt":
        return actual < expected
    if predicate.operator == "lte":
        return actual <= expected
    if predicate.operator == "gt":
        return actual > expected
    if predicate.operator == "gte":
        return actual >= expected
    if predicate.operator == "in":
        if actual is None:
            # SQL: `NULL IN (...)` is always UNKNOWN/excluded, even if the
            # list itself contains a literal null.
            return False
        return actual in expected
    if predicate.operator == "contains":
        # Q-2 (案i): literal substring containment, no wildcard
        # interpretation -- Python's `in` on strings is already exactly
        # this (no wildcard semantics exist for it).
        if actual is None:
            return False
        return expected in _predicate_text(actual, field_types.get(predicate.field))
    if predicate.operator == "matches":
        if actual is None:
            return False
        return _wildcard_pattern(expected).match(_predicate_text(actual, field_types.get(predicate.field))) is not None
    return actual is None  # is_null
