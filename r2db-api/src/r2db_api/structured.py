"""A small structured-operation reference engine (no database-native command path)."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .audit_hook import ApplicationAuditHook
from .delete_confirmation import (
    RESET_CONTROL_CREDENTIALS,
    _MAX_REVISION_DIGITS,
    _PHRASE_MAX_LENGTH,
    _canonical_where_json,
    _where_digest16,
    delete_confirmation_phrase,
    delete_credential_confirmation_phrase,
    drop_entity_confirmation_phrase,
    drop_index_confirmation_phrase,
    require_destructive_confirmation,
    revoke_last_control_credential_confirmation_phrase,
)
from .errors import fail, observed_type_of, violation
from .identifier_rules import (
    IDENTIFIER,
    MAX_IDENTIFIER_LENGTH,
    _RESERVED_ENTITY_NAMES,
    _RESERVED_PREFIX,
    _reject_reserved_entity_name,
    _reject_reserved_field,
    _reject_reserved_prefix,
    validate_identifier,
)
from .inmemory_predicate import _matches, _predicate_text, _wildcard_pattern
from .inmemory_sort import _JSON_TYPE_RANK, _after_page_cursor, _sort_key, _sort_rows
from .limits import ResourceLimits
from .mutation_binding import (
    BoundMutation,
    Predicate,
    bind_mutation,
    parse_predicate,
    validate_predicates,
    validate_projection,
)
from .paging import (
    MAX_ORDER_BY_FIELDS,
    MAX_PAGE_SIZE,
    _resolve_order_by,
    canonical_page_binding,
    decode_and_check_page_cursor,
    encode_page_cursor,
    validate_page_size,
)
from .pg_text_format import _float8out_text, _jsonb_numeric_text, _jsonb_scalar_text, _jsonb_text
from .schema_binding import (
    BoundSchemaOperation,
    ConstraintPatch,
    FIELD_TYPES,
    FieldConstraints,
    MAX_INDEX_FIELDS,
    _ConstraintDeclarationError,
    _ENUM_ELIGIBLE_TYPES,
    _SCHEMA_KEYS,
    _fail_constraint_declaration,
)
from .storage_outcomes import MutationOutcome, QueryOutcome, SchemaOutcome
from .value_nul import _contains_nul
from .value_types import (
    _INT64_MAX,
    _INT64_MIN,
    _TEXT_ONLY_OPERATORS,
    _check_type,
    _declared_type_label,
    _validate_predicate_types,
    _validate_wildcard_pattern,
)

# --- Shared validation/planning boundary (design D-1) -----------------------
#
# Everything below this point (`validate_projection` through `bind_mutation` now in `mutation_binding.py`) is the boundary every `StorageBackend` MUST
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


def enum_member_matches_type(value: Any, declared_type: str | None) -> bool:
    """Whether `value` is a legal `enum` member for a field of
    `declared_type` (D-2 (2): "要素は field の宣言型 ... の値のみ"). Never
    accepts `None` here -- callers reject a null member up front (`enum`
    constrains non-null values only). `declared_type` outside
    `_ENUM_ELIGIBLE_TYPES` never reaches this function at all --
    `validate_enum_declaration` below rejects the declaration itself
    first. m-3 (monitor ruling): renamed from `_enum_member_matches_type`
    to match MitateDB's own `field_types.enum_member_matches_type`
    (same name, same 2-argument signature) -- the isomorphism test's own
    same-named-helper pairing (work order §2 WP-2a "同型性テストの対象")."""
    if declared_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared_type == "boolean":
        return isinstance(value, bool)
    if declared_type == "string":
        return isinstance(value, str)
    return False


def validate_enum_declaration(enum_values: Any, declared_type: str | None) -> tuple[Any, ...]:
    """Contract 1.7.0 (D-2 (2), contract text `field_constraints`
    description; monitor ruling B-1, rulings-wp2a-review.md): the single
    validator for an `enum` declaration, called from every one of the
    three places one can appear (`create_entity`'s `field_constraints`,
    `add_field`'s top-level `enum`, both here at bind time since the
    field's own declared type is already known then; and `alter_field`'s
    top-level `enum`, deferred to `apply_schema` -- see that method's own
    comment -- since only there is the field's EXISTING declared type
    known).

    `declared_type` outside `_ENUM_ELIGIBLE_TYPES` above (`None`/
    untyped, `"object"`, `"array"` -- `"json"` is never a value this
    module's own internal vocabulary uses, see `FIELD_TYPES`'s own
    comment) is rejected OUTRIGHT (ruling B-1: no first-member type
    INFERENCE for an untyped field, unlike the pre-rework implementation
    -- MitateDB rejects the identical `declared_type` set the identical
    way, `field_types._ENUM_ELIGIBLE_TYPES`/`validate_enum_declaration`,
    so a `field_constraints`/`enum`/`field_types: json` combination the
    catalog can report is now refused by BOTH peers, never accepted by
    one and refused by the other).

    Raises `_ConstraintDeclarationError` (never `fail()` directly -- see
    that class' own docstring) for: `declared_type` outside the 4 eligible
    words, not a non-empty list, a `None` member, a member whose JSON
    type does not match `declared_type`, or a duplicate member. Returns
    the validated members as a tuple, in the order declared (round-trip
    fidelity for `EntityDescriptor.field_constraints`).
    """
    if declared_type not in _ENUM_ELIGIBLE_TYPES:
        raise _ConstraintDeclarationError("enum can only be declared on a field of type string, integer, number or boolean.")
    if not isinstance(enum_values, list) or not enum_values:
        raise _ConstraintDeclarationError("enum must be a non-empty list.")
    validated: list[Any] = []
    for member in enum_values:
        if member is None or not enum_member_matches_type(member, declared_type):
            raise _ConstraintDeclarationError("enum member does not match the field's declared type.")
        if member in validated:
            raise _ConstraintDeclarationError("enum must not contain duplicate members.")
        validated.append(member)
    return tuple(validated)


def bind_schema_operation(operation: Any, *, developer: bool) -> BoundSchemaOperation:
    if not developer:
        fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
    if not isinstance(operation, dict):
        fail("VALIDATION_FAILED", "Schema operation must be an object.", details=violation("request_schema"))
    if set(operation) - _SCHEMA_KEYS:
        fail("VALIDATION_FAILED", "Schema operation shape is not supported.", details=violation("request_schema"))
    name = operation.get("operation")
    entity = validate_identifier(operation.get("entity", ""), field="entity")
    # WP-2(b) fix round 2 (coordinator item C): reserved by EXACT match at
    # this ONE shared choke point -- every schema operation (create_entity/
    # add_field/drop_entity/create_index/drop_index) binds `entity` here,
    # so this single check covers all of them uniformly, matching
    # MitateDB's own `cell._identifier()` "reject at every identifier
    # position" line rather than only the `create_entity` creation path.
    _reject_reserved_entity_name(entity, field="entity")
    if "revision" in operation:
        # WP-2 review minor (e): `revision` was previously an accepted-but-
        # unused key (schema-level optimistic locking has no implementation
        # here) -- silently accepting and ignoring it is exactly the kind
        # of gap `field_type`'s own precedent below closes, so stop
        # tolerating it instead of leaving it a silent no-op.
        fail("CAPABILITY_UNSUPPORTED", "Schema operation optimistic locking is not available.", details=violation("capability", field="revision"))
    if name != "add_field" and "field_type" in operation:
        # R-2 (corrigendum m-1): `field_type` is accepted only by
        # `add_field`; every other operation rejects it exactly as before
        # this contract version did (this key simply didn't exist in
        # `_SCHEMA_KEYS` then), so this is not new external behaviour.
        #
        # Contract 1.7.0 (D-2 (5), work order §2 WP-2a "実装の指示"):
        # `alter_field` redeclares a field's `enum`/`nullable`, never its
        # type -- carrying `field_type` fails the SAME code but in the
        # WP-2a/D-3 four-key form (`violated_declaration: unsupported_
        # field`), the one existing branch this WP's own "実装の指示"
        # instructs be "載せ替える" rather than left generic.
        if name == "alter_field":
            fail(
                "VALIDATION_FAILED",
                "alter_field does not redeclare a field's type.",
                details={"field": "field_type", "violated_declaration": "unsupported_field"},
            )
        fail("VALIDATION_FAILED", "field_type is only supported by add_field.", details=violation("unsupported_field", field="field_type"))
    if name != "create_entity" and "field_types" in operation:
        # Phase 6 WP-2 (design D-3(iv)): `field_types` (the per-field map)
        # is accepted only by `create_entity` -- symmetric with `field_
        # type`'s (the scalar) `add_field`-only rule immediately above.
        fail("VALIDATION_FAILED", "field_types is only supported by create_entity.", details=violation("unsupported_field", field="field_types"))
    if name != "create_entity" and "field_constraints" in operation:
        # Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints` (the
        # per-field map) is accepted only by `create_entity` -- symmetric
        # with `field_types` immediately above.
        fail("VALIDATION_FAILED", "field_constraints is only supported by create_entity.", details=violation("unsupported_field", field="field_constraints"))
    if name not in ("add_field", "alter_field") and ("enum" in operation or "nullable" in operation):
        # Contract 1.7.0 (D-2 (1), WP-2a): the scalar `enum`/`nullable`
        # pair is accepted only by `add_field`/`alter_field` -- symmetric
        # with `field_type`'s own `add_field`-only rule above.
        fail("VALIDATION_FAILED", "enum/nullable are only supported by add_field/alter_field.", details=violation("unsupported_field", field="enum" if "enum" in operation else "nullable"))
    if name != "create_index":
        # WP-2 review M-3: `index`/`unique` are meaningful only to
        # `create_index` (`drop_index` additionally accepts `index` as the
        # name to drop, but never `unique`) -- the same "don't silently
        # tolerate a key this operation does not use" principle as
        # `field_type` above, applied to this pair.
        if "unique" in operation:
            fail("VALIDATION_FAILED", "unique is only supported by create_index.", details=violation("unsupported_field", field="unique"))
        if "index" in operation and name != "drop_index":
            fail("VALIDATION_FAILED", "index is only supported by create_index/drop_index.", details=violation("unsupported_field", field="index"))
    if "destructive" in operation and not isinstance(operation["destructive"], bool):
        # Review blocker B-1: symmetric with `bind_mutation`'s identical
        # check above (now in `mutation_binding.py`) -- a non-boolean truthy `destructive` (a string, an
        # int, an object) must never be silently coerced into `True` by a
        # loose `bool(...)` cast downstream. This is a shape check (contract
        # `SchemaOperationRequest.destructive: {"type": "boolean"}`), so it
        # runs here, before the destructive-confirmation gate itself, per
        # contract `evaluation_order` (shape validation precedes
        # confirmation evaluation).
        fail("VALIDATION_FAILED", "Destructive flag must be boolean.", details=violation("request_schema", field="destructive", declared_type="boolean", observed_type=observed_type_of(operation["destructive"])))
    fields: tuple[str, ...] = ()
    field_name: str | None = None
    field_type: str | None = None
    field_types: dict[str, str | None] = {}
    field_constraints: dict[str, FieldConstraints] = {}
    constraints: FieldConstraints | None = None
    constraint_patch: ConstraintPatch | None = None
    index_name: str | None = None
    index_fields: tuple[str, ...] = ()
    unique = False
    if name == "create_entity":
        _reject_reserved_prefix(entity, field="entity")
        raw_fields = operation.get("fields", [])
        if not isinstance(raw_fields, list) or len(raw_fields) > 100:
            fail("VALIDATION_FAILED", "Schema fields must be a bounded list.", details=violation("request_schema", field="fields"))
        validated: list[str] = []
        for i, candidate in enumerate(raw_fields):
            # Ruling N-1: identifier_syntax stops at the container
            # position ("fields", N-1's own example) -- never the
            # malformed candidate or its index. The reserved-name check
            # below operates on an already syntax-valid string (N-1: "有効
            # な識別子...予約名など はこれまでどおり path に含めてよい"), so it keeps
            # the precise per-index path as before.
            validate_identifier(candidate, field="fields")
            _reject_reserved_field(candidate, field=f"fields/{i}")
            if candidate in validated:
                fail("CONFLICT", "Field already exists.", status=409)
            validated.append(candidate)
        fields = tuple(validated)
        # Phase 6 WP-2 (design D-3(iv)): `field_types` is an OPTIONAL,
        # never-required key -- a `create_entity` carrying only `fields`
        # (1.5.0's own shape) stays valid unchanged (every field it creates
        # gets `field_types.get(name)` == `None` == `json`, decision (ii)'s
        # default). Three invalid shapes are `VALIDATION_FAILED` (design's
        # own enumeration, all three checked here so the field-name/word
        # checks below never run against a request this repository already
        # knows is malformed at a higher level):
        if "field_types" in operation:
            # (c) `field_types` sent without `fields` at all -- checked
            # against the RAW request key, not the (always-present, maybe-
            # empty) `raw_fields` local above, so a request that omits
            # `fields` entirely is caught here even though `operation.get(
            # "fields", [])` already defaulted it to `[]` for the loop
            # above.
            if "fields" not in operation:
                fail("VALIDATION_FAILED", "field_types requires fields.", details=violation("request_schema", field="field_types"))
            raw_field_types = operation["field_types"]
            if not isinstance(raw_field_types, dict):
                fail("VALIDATION_FAILED", "field_types must be an object.", details=violation("request_schema", field="field_types", declared_type="object", observed_type=observed_type_of(raw_field_types)))
            declared_types: dict[str, str | None] = {}
            for declared_field, declared_type in raw_field_types.items():
                # (a) a name field_types declares that `fields` never named.
                if declared_field not in fields:
                    fail("VALIDATION_FAILED", "field_types names a field that is not present in fields.", details=violation("unsupported_field", field="field_types/" + declared_field))
                # (b) a value outside the 7-word vocabulary. `isinstance`
                # checked FIRST (coordinator F2, 2026-09-04 review): `in`
                # against `FIELD_TYPES` (a `set`) raises `TypeError` for an
                # unhashable value (a list/dict) rather than returning
                # `False`, and `_endpoint` (http.py) maps an uncaught
                # `TypeError` to a bare 503 -- `_check_object_shape`'s own
                # JSON-Schema check does not constrain `field_types`'
                # VALUES (only that the object's own top-level shape
                # matches), so a list/dict/int/bool/null value reaches this
                # line from real HTTP input, not merely from a
                # bind_schema_operation direct call.
                if not isinstance(declared_type, str) or declared_type not in FIELD_TYPES:
                    fail("VALIDATION_FAILED", "Unsupported field type.", details=violation("enum", field="field_types/" + declared_field, declared_type="string"))
                # Decision (v1.3 G11): an explicitly declared `json` is the
                # SAME internal representation as untyped (`None`) -- see
                # `FIELD_TYPES`'s own module-level comment above (in `schema_binding.py`) for why
                # (NUL-check inclusion, JSONB-default DDL).
                declared_types[declared_field] = None if declared_type == "json" else declared_type
            field_types = declared_types
        # Contract 1.7.0 (D-2 (1), WP-2a): `field_constraints` is an
        # OPTIONAL, never-required key -- a `create_entity` carrying no
        # `field_constraints` at all stays valid unchanged (every field it
        # creates gets no `enum`, `nullable: true`, D-2 (2)'s own default).
        # Placed AFTER `field_types` above so each field's own declared
        # type (`field_types.get(name)`, `None`/json if that field was
        # never given one) is already resolved for `validate_enum_
        # declaration` below.
        if "field_constraints" in operation:
            if "fields" not in operation:
                # Mirrors `field_types`'s identical "sent without fields"
                # check above. Monitor ruling N-2 (rulings-r2-closure.md,
                # WP-2a closure): `field` names the request-internal key
                # this whole clause hangs off, mirrors the adjacent
                # per-entry branches below which already load this key.
                fail(
                    "VALIDATION_FAILED",
                    "field_constraints requires fields.",
                    details={"field": "field_constraints", "violated_declaration": "request_schema"},
                )
            raw_field_constraints = operation["field_constraints"]
            if not isinstance(raw_field_constraints, dict):
                # Monitor ruling N-2 (rulings-r2-closure.md): same key,
                # same reason as the "requires fields" branch above.
                fail(
                    "VALIDATION_FAILED",
                    "field_constraints must be an object.",
                    details={"field": "field_constraints", "violated_declaration": "request_schema"},
                )
            parsed_constraints: dict[str, FieldConstraints] = {}
            for declared_field, spec in raw_field_constraints.items():
                # Ruling O-3 (`{scratchpad}/rulings-r3-r7-flip.md` 追補4,
                # 版フリップ監査差し戻し): a `field_constraints` KEY that is
                # itself an identifier-syntax violation must not be echoed
                # into `field` (SI-10 -- the key can carry SQL fragments/
                # control characters, exactly the `values`-key regression
                # N-1 closed) -- checked FIRST, stopping at the container
                # position ("field_constraints", N-1's own container-
                # position convention -- `_reject_reserved_field`/
                # `_reject_reserved_prefix`-style reservation checks are
                # deliberately NOT run here, unlike `fields`'s own loop
                # above: `field_constraints` never creates a field by
                # itself, so a reserved-shaped key here is caught by the
                # "not present in fields" branch below instead, same as
                # any other key `fields` never declared). A syntactically
                # VALID identifier that simply is not in `fields` still
                # falls through to that branch unchanged (N-1: "有効な識別子
                # ...予約名など はこれまでどおり path に含めてよい").
                validate_identifier(declared_field, field="field_constraints")
                if declared_field not in fields:
                    # Monitor ruling m-1 (rulings-wp2a-review.md, contract
                    # corrigendum, verbatim list of `constraint_declaration`
                    # cases): "...or a declaration naming a field the
                    # request does not create" -- `field` is the request-
                    # internal PATH to the offending key (D-3 (2)), never
                    # the field name it names (which does not exist).
                    fail(
                        "VALIDATION_FAILED",
                        "field_constraints names a field that is not present in fields.",
                        details={"field": f"field_constraints/{declared_field}", "violated_declaration": "constraint_declaration"},
                    )
                if not isinstance(spec, dict):
                    fail(
                        "VALIDATION_FAILED",
                        "field_constraints entry shape is not supported.",
                        details={"field": f"field_constraints/{declared_field}", "violated_declaration": "request_schema"},
                    )
                unknown_keys = set(spec) - {"enum", "nullable"}
                if unknown_keys:
                    # Monitor ruling E (rulings-wp3a-review.md, applied to
                    # r2db by M-3/rulings-wp2a-review.md): an unknown key
                    # INSIDE one field's own constraint spec (as opposed to
                    # the field name itself, handled above) is a request-
                    # shape defect -- `field` names the unknown key's own
                    # path, mirrors MitateDB `cell.py`'s identical form.
                    bad_key = sorted(unknown_keys)[0]
                    fail(
                        "VALIDATION_FAILED",
                        "field_constraints entry has an unsupported key.",
                        details={"field": f"field_constraints/{declared_field}/{bad_key}", "violated_declaration": "request_schema"},
                    )
                raw_nullable = spec.get("nullable", True)
                if not isinstance(raw_nullable, bool):
                    fail(
                        "VALIDATION_FAILED",
                        "nullable must be boolean.",
                        details={
                            "field": f"field_constraints/{declared_field}/nullable",
                            "violated_declaration": "constraint_declaration",
                            "declared_type": _declared_type_label(field_types.get(declared_field)),
                        },
                    )
                enum_tuple = None
                if "enum" in spec:
                    try:
                        enum_tuple = validate_enum_declaration(spec["enum"], field_types.get(declared_field))
                    except _ConstraintDeclarationError as exc:
                        _fail_constraint_declaration(f"field_constraints/{declared_field}/enum", field_types.get(declared_field), exc)
                parsed_constraints[declared_field] = FieldConstraints(enum=enum_tuple, nullable=raw_nullable)
            field_constraints = parsed_constraints
    elif name == "add_field":
        field_name = validate_identifier(operation.get("field", ""), field="field")
        _reject_reserved_field(field_name, field="field")
        if "field_type" in operation:
            field_type = operation["field_type"]
            # Coordinator F2: same isinstance-first guard as create_entity's
            # field_types values above -- closes the identical, pre-existing
            # (not a WP-2 regression) hole on this scalar sibling in the
            # same fix, per the review's own instruction not to leave a new
            # vocabulary/peer asymmetry by fixing only one of the two.
            if not isinstance(field_type, str) or field_type not in FIELD_TYPES:
                fail("VALIDATION_FAILED", "Unsupported field type.", details=violation("enum", field="field_type", declared_type="string"))
            if field_type == "json":
                # Decision (v1.3 G11): same json->None translation as
                # create_entity's `field_types` values above.
                field_type = None
        # Contract 1.7.0 (D-2 (1), WP-2a): `add_field`'s own single-field
        # `enum`/`nullable`, validated against THIS SAME request's own
        # `field_type` (already resolved above -- `add_field` declares a
        # brand new field, so there is no "existing declared type" to
        # defer to, unlike `alter_field` below).
        if "enum" in operation or "nullable" in operation:
            raw_nullable = operation.get("nullable", True)
            if not isinstance(raw_nullable, bool):
                fail(
                    "VALIDATION_FAILED",
                    "nullable must be boolean.",
                    details={"field": "nullable", "violated_declaration": "constraint_declaration", "declared_type": _declared_type_label(field_type)},
                )
            enum_tuple = None
            # Monitor ruling A (rulings-wp3a-review.md, applied to r2db by
            # rulings-wp2a-review.md B-2): "add_field で enum: null = enum
            # 無し" -- an explicit `null` is the SAME as omitting `enum`
            # altogether, never a declaration-shape error. Anything else
            # non-list still fails inside `validate_enum_declaration`.
            if "enum" in operation and operation["enum"] is not None:
                try:
                    enum_tuple = validate_enum_declaration(operation["enum"], field_type)
                except _ConstraintDeclarationError as exc:
                    _fail_constraint_declaration("enum", field_type, exc)
            constraints = FieldConstraints(enum=enum_tuple, nullable=raw_nullable)
    elif name == "alter_field":
        # Contract 1.7.0 (D-2 (5), WP-2a; monitor ruling A/B-2): `alter_
        # field` redeclares one EXISTING field's `enum`/`nullable` as a
        # PATCH, never a wholesale replace -- omitting `enum` LEAVES it as
        # it is, `enum: null` CLEARS it, omitting `nullable` LEAVES it as
        # it is. `field_type` is rejected above (before this branch is
        # ever reached) in the D-3 four-key form.
        #
        # The field's own EXISTING declared type/constraints are not known
        # here (no catalog access at bind time) -- only this request's own
        # SHAPE is checked (a list, non-empty, no `None` member, no
        # duplicate); the member-type-vs-declared-type check (`validate_
        # enum_declaration`, called again with the real declared type),
        # the `enum_members` bound, and the omitted/clear/value COMPOSITION
        # against the field's existing constraints are all deferred to
        # `apply_schema` (addendum R-b/R-c, D-2 (3)) -- see `ConstraintPatch`.
        field_name = validate_identifier(operation.get("field", ""), field="field")
        _reject_reserved_field(field_name, field="field")
        if "nullable" not in operation and "enum" not in operation:
            # Monitor ruling N-1 (rulings-r2-closure.md, contract
            # corrigendum 3, verbatim): "An alter_field carrying neither
            # enum nor nullable declares nothing and is refused with
            # VALIDATION_FAILED; it does not advance the schema
            # revision." `field` names the operation itself (D-3 (2)) --
            # the missing declaration is not any one field's key, it is
            # the whole `alter_field` object carrying nothing to apply.
            # Rejected here (bind time, before any backend/revision
            # access) so neither backend ever sees this operation.
            fail(
                "VALIDATION_FAILED",
                "alter_field must declare enum or nullable.",
                details={"field": "operation", "violated_declaration": "constraint_declaration"},
            )
        nullable_omitted = "nullable" not in operation
        nullable_value = True
        if not nullable_omitted:
            nullable_value = operation["nullable"]
            if not isinstance(nullable_value, bool):
                fail("VALIDATION_FAILED", "nullable must be boolean.", details={"field": "nullable", "violated_declaration": "constraint_declaration"})
        enum_omitted = "enum" not in operation
        enum_clear = False
        enum_shape_checked: tuple[Any, ...] | None = None
        if not enum_omitted:
            raw_enum = operation["enum"]
            if raw_enum is None:
                # Monitor ruling A: `enum: null` clears the field's enum.
                enum_clear = True
            else:
                if not isinstance(raw_enum, list) or not raw_enum:
                    fail("VALIDATION_FAILED", "enum must be a non-empty list.", details={"field": "enum", "violated_declaration": "constraint_declaration"})
                shape_checked: list[Any] = []
                for member in raw_enum:
                    if member is None:
                        fail("VALIDATION_FAILED", "enum must not contain null.", details={"field": "enum", "violated_declaration": "constraint_declaration"})
                    if member in shape_checked:
                        fail("VALIDATION_FAILED", "enum must not contain duplicate members.", details={"field": "enum", "violated_declaration": "constraint_declaration"})
                    shape_checked.append(member)
                enum_shape_checked = tuple(shape_checked)
        constraint_patch = ConstraintPatch(
            enum_omitted=enum_omitted, enum_clear=enum_clear, enum_raw=enum_shape_checked,
            nullable_omitted=nullable_omitted, nullable=nullable_value,
        )
    elif name == "create_index":
        # R-5: the physical index name is `{entity}__{index}` (double
        # underscore separated), so a client index name containing `__`
        # would make that composition ambiguous to invert -- rejected
        # outright (corrigendum m-2), as is a composed name over the
        # identifier length limit.
        index_name = validate_identifier(operation.get("index", ""), field="index")
        _reject_reserved_prefix(index_name, field="index")
        if "__" in index_name:
            fail("VALIDATION_FAILED", "Index name must not contain a double underscore.", details=violation("request_schema", field="index"))
        composed_length = len(entity.encode("utf-8")) + 2 + len(index_name.encode("utf-8"))
        if composed_length > MAX_IDENTIFIER_LENGTH:
            fail("VALIDATION_FAILED", "The composed index name exceeds the identifier length limit.", details=violation("request_schema", field="index"))
        raw_fields = operation.get("fields", [])
        if not isinstance(raw_fields, list) or not (1 <= len(raw_fields) <= MAX_INDEX_FIELDS):
            fail("VALIDATION_FAILED", "Index fields must list between 1 and 16 fields.", details=violation("request_schema", field="fields"))
        validated = []
        for i, candidate in enumerate(raw_fields):
            # Ruling N-1: container position ("fields"), not the
            # per-index path -- same reasoning as create_entity's fields
            # loop above.
            validate_identifier(candidate, field="fields")
            if candidate == "id":
                # WP-2 review M-5: `id` is the address, not a domain
                # uniqueness declaration (§2) -- allowing it here would let
                # a peer publish a `unique_keys` entry upsert can never
                # actually use (values.id is always rejected, R-3), which
                # would also make C-17's positive control unsatisfiable.
                fail("VALIDATION_FAILED", "Address fields cannot be declared as a uniqueness key.", details=violation("unsupported_field", field="fields"))
            if candidate in validated:
                fail("VALIDATION_FAILED", "Index fields must not repeat.", details=violation("request_schema", field="fields"))
            validated.append(candidate)
        index_fields = tuple(validated)
        raw_unique = operation.get("unique", False)
        if not isinstance(raw_unique, bool):
            fail("VALIDATION_FAILED", "Unique flag must be boolean.", details=violation("request_schema", field="unique", declared_type="boolean", observed_type=observed_type_of(raw_unique)))
        unique = raw_unique
    elif name == "drop_index":
        index_name = validate_identifier(operation.get("index", ""), field="index")
        _reject_reserved_prefix(index_name, field="index")
    elif name != "drop_entity":
        fail("CAPABILITY_UNSUPPORTED", "Schema operation is not supported by this foundation.", details=violation("capability", field="operation"))
    return BoundSchemaOperation(
        name, entity, field_name, fields, bool(operation.get("destructive")), operation.get("confirmation"), field_type, index_name, index_fields, unique,
        field_types=field_types, field_constraints=field_constraints, constraints=constraints, constraint_patch=constraint_patch,
    )


# --- contract 1.7.0 dry_run/plan (D-4, WP-2b) --------------------------------
#
# Peer symmetry (work order §2 WP-2b "同型性テストの対象"): MitateDB-api
# places its own same-named, same-signature pair in `field_types.py`
# (the module its own D-2 constraint helpers already live in) -- no code
# is shared between the two peers (依頼者裁定 2026-09-03 案(a)); only the
# two names/signatures/behaviour are pinned isomorphic.


def normalize_request_for_plan(request: dict[str, Any]) -> bytes:
    """Contract 1.7.0 (D-4 (7), addendum 2 S-a): the canonical byte
    encoding a `plan` (and, per D-5 (1)(i), an `idempotency_key`'s own
    digest) commits to -- `request`'s keys in lexicographic order, no
    insignificant whitespace, non-ASCII left unescaped, encoded UTF-8.
    `request` is the contract-level request object as THIS peer's own
    `SchemaOperationRequest`/`MutationRequest` schema names it -- `plan`
    and `dry_run` themselves are excluded here defensively (S-a's own
    exclusion pair; every real caller already omits them before building
    the dict this function receives, `service.py`'s own `plan_request`/
    `apply_schema`'s `plan_request`), never a raw HTTP body (`service.py`
    assembles the same object whether a request arrived over HTTP or an
    in-process port, D-4 (7)'s own "同じ object になる" requirement).
    Mirrors `canonical_page_binding`'s identical `json.dumps(...,
    sort_keys=True)` + `hashlib.sha256` recipe (in `paging.py`), applied to
    a different payload shape.
    """
    filtered = {key: value for key, value in request.items() if key not in ("plan", "dry_run")}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_plan_token(request: dict[str, Any], schema_revision: int) -> str:
    """Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a, U-4 = (A)): `plan` --
    an opaque but deterministic token computed from `normalize_request_
    for_plan(request)` together with the Application's own schema
    revision (`SchemaOperationResult.revision`'s identical per-application
    monotonic counter, D-4 (7); never an entity-scoped value, since
    neither peer keeps one). Holds no server-side state: two calls with
    the identical `request` (modulo `plan`/`dry_run`) and the identical
    `schema_revision` always return the identical token; either input
    changing changes it. `maxLength: 256` (`schemas.MutationRequest.
    properties.plan`) comfortably bounds this -- a 64-hex-digit sha256
    plus a decimal revision separated by one character.

    Review round F-7 (`{scratchpad}/rulings-r4.md`): the format is
    FIXED as `"<sha256hex>.<schema_revision>"`, identically on both
    peers -- `revision` is not treated as secret (it is the exact value
    `SchemaOperationResult.revision` already reports back to any
    developer credential, and this token is never presented to a runtime
    credential's own schema-blind view). The contract's "opaque" means
    only that a client is expected to compare tokens for equality, never
    to parse or construct one -- it does not require the revision
    component to be hidden.
    """
    digest = hashlib.sha256(normalize_request_for_plan(request)).hexdigest()
    return f"{digest}.{schema_revision}"


# --- contract 1.7.0 idempotency (D-5, WP-2c) ---------------------------------
#
# Peer symmetry (work order §2 WP-2c "同型性テストの対象"): MitateDB-api
# places its own same-named, same-signature pair alongside `normalize_
# request_for_plan`/`compute_plan_token` -- no code is shared between the
# two peers (依頼者裁定 2026-09-03 案(a)); only the two names/signatures/
# behaviour are pinned isomorphic (`_ISOMORPHIC_TARGETS` row added by the
# supervisor's pair-closing commit, ruling T-2 -- not by this WP).


def normalize_request_for_idempotency(request: dict[str, Any]) -> bytes:
    """Contract 1.7.0 (D-5 (1)(i), addendum 2 S-a, ruling I-2): the
    canonical byte encoding an `idempotency_key`'s own digest commits to --
    IDENTICAL recipe to `normalize_request_for_plan` above (same key
    ordering / separator / `ensure_ascii=False` / UTF-8 rules), but a
    DIFFERENT exclusion set: `plan`, `dry_run` AND `idempotency_key`
    itself (three keys, not two) -- ruling I-2/I-13: `idempotency_key` is
    excluded from ITS OWN digest (a resend is identified by the key, not
    re-hashed into what it must match) but stays IN `normalize_request_
    for_plan`'s digest, so a `plan` token captured with one `idempotency_
    key` (or none) does not verify against a request presenting a
    different one. Deliberately not sharing a body with `normalize_
    request_for_plan` (work order §2 WP-2c: "本文を共有せず、除外key の
    違いだけの同型に保つ") -- the two are pinned isomorphic by name/
    signature/behaviour only, per the peer-symmetry convention above.
    """
    filtered = {key: value for key, value in request.items() if key not in ("plan", "dry_run", "idempotency_key")}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fold_operation_idempotency_keys(operations: list[dict[str, Any]]) -> str | None:
    """Ruling I-12/adapter port v1.11 compatibility: this peer's internal
    (non-HTTP) mutation-item shape carries a request-level `idempotency_
    key` duplicated onto EVERY operation item (`conformance/conformance_
    adapter_r2db.py`'s `_build_mutation_item`/`fold_batch_idempotency_
    key` -- the port's own "全 item 同一 key か全 item 無し" rule, D-5
    §6.1 (v)). `service.py`'s `_mutate_outcome` calls this ONLY when its
    own explicit `idempotency_key` parameter is `None` (an HTTP-originated
    call always supplies that parameter directly and never reaches here --
    `MutationRequest.idempotency_key` is a request-level contract field,
    never a per-operation one, `definitions.Mutation.properties` has no
    such key). Mirrors the adapter's own uniform-or-absent rule: every
    item sharing the identical key folds to that key; no item carrying one
    folds to `None`; anything else (a mix, or differing values) is a
    malformed request this peer refuses to guess about.
    """
    present_count = sum(1 for op in operations if isinstance(op, dict) and "idempotency_key" in op)
    if present_count == 0:
        return None
    keys = {op.get("idempotency_key") for op in operations if isinstance(op, dict) and "idempotency_key" in op}
    if len(keys) > 1 or present_count != len(operations):
        fail(
            "VALIDATION_FAILED", "idempotency_key must be identical across every operation in a batch, or absent from all of them.",
            details={"violated_declaration": "request_schema", "field": "operations"},
        )
    return next(iter(keys))


def idempotency_digest(request: dict[str, Any]) -> str:
    """Contract 1.7.0 (D-5 (1)(i), addendum 2 S-a): the sha256 hex digest
    `structured_operations.idempotency.record` describes -- "computed
    exactly as `structured_operations.dry_run.plan` describes" over
    `normalize_request_for_idempotency(request)`'s own filtered byte
    encoding. A resend's digest is compared against a retained record's
    stored digest for equality (`ApplicationCell`/`PostgresCell`'s own
    idempotency lookup): equal -> replay; unequal -> `CONFLICT`.
    """
    return hashlib.sha256(normalize_request_for_idempotency(request)).hexdigest()


@dataclass(frozen=True)
class _IdempotencyRecord:
    """One retained idempotency record -- `ApplicationCell`'s own
    process-internal store (ruling I-1: "in-memory 参照 cell はプロセス内
    dict"; `PostgresCell`'s Postgres-backend counterpart is the
    `public._r2db_idempotency` side table, migration `0011_idempotency_
    records_upgrade.sql`, same shape realized as a row).

    `payload` carries exactly what a replay needs to reconstruct the
    ORIGINAL `MutationOutcome`/`SchemaOutcome` verbatim (ruling I-8: "記録
    した応答 object 全体... をそのまま返す") -- never re-derived from
    current state. `kind` distinguishes the two payload shapes ("mutation":
    `affected`/`assigned_addresses`; "schema": `revision`/`descriptor`).
    """

    digest: str
    kind: str
    payload: dict[str, Any]
    expires_at: float


def _idempotency_record_has_request_id(payload: dict[str, Any]) -> bool:
    """Ruling L-6/M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2,
    WP-2e closure audit R-1): a record written before the 1.7.0 flip
    carries no `request_id` in its payload -- contract `versioning.
    version_binding`'s 1.7.0 condition (4) requires a replay to return
    "the original result... including the original request_id", which a
    request_id-less record cannot honour. Such a record is treated as
    though it were never found at all (never a fallback to the RESEND's
    own request_id, which would silently forge a value the original
    execution never produced) -- the resend falls through to a genuine
    new execution, whose result (including a freshly generated request_
    id) overwrites this same key's record (`_idempotency_store`'s plain
    dict assignment, `PostgresCell`'s row `UPSERT`, already do this).
    Both cells check this BEFORE the digest comparison: a stale, request_
    id-less record with a MISMATCHED digest must not become a spurious
    `CONFLICT` either -- it is simply not there."""
    return isinstance(payload.get("request_id"), str)


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
    # Contract 1.7.0 (D-2 (4), WP-2a): entity -> field_name -> FieldConstraints
    # -- the in-memory backend's own declaration registry ("プロセス内参照
    # cell の構造", no upgrade script needed, unlike Postgres's side table).
    # A field name is present here ONLY when SOMETHING was declared for it
    # (`FieldConstraints.is_declared`) -- absence means the version-wide
    # default (`nullable: true`, no `enum`), exactly like `schema`'s own
    # "省略 = json" convention. Never read/written directly by anything
    # outside this class; `catalog()`/`_apply`/`_apply_upsert`/`apply_
    # schema` below are its only callers.
    field_constraints: dict[str, dict[str, "FieldConstraints"]] = field(default_factory=dict)
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
    # Contract 1.7.0 (D-5 (6), U-3 = (A), ruling I-1, WP-2c): the in-memory
    # backend's own idempotency record store -- "プロセス内 dict" (never a
    # side table; `PostgresCell`'s Postgres-backend counterpart is the
    # `public._r2db_idempotency` side table). Application-scoped by
    # construction: this dict lives on ONE `ApplicationCell` instance
    # (`DataService._cells[application_id]`), so a lookup here is already
    # scoped to the Application regardless of which credential's request
    # reaches it (ruling I-5) -- no separate scoping code is needed.
    _idempotency: dict[str, "_IdempotencyRecord"] = field(default_factory=dict, repr=False)
    # Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): this
    # in-memory backend has no database transaction to take a
    # `pg_advisory_xact_lock` inside, so the analogous serialization is a
    # cell-wide `threading.Lock` (ruling U-7 explicitly allows "per cell")
    # held for the ENTIRE lookup -> execute -> store window of `transact`/
    # `apply_schema` (`_transact_locked`/`_apply_schema_locked` below) --
    # uvicorn (or a future threadpool, U-10) can run two requests against
    # the SAME `ApplicationCell` on different threads, and nothing before
    # this ruling prevented them from interleaving between the dict
    # lookup and the dict store. Not a dataclass-compared/repr'd field --
    # a `threading.Lock` supports neither.
    _idempotency_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        for entity, rows in list(self.entities.items()):
            validate_identifier(entity, field=f"entities/{entity}")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                fail("VALIDATION_FAILED", "Entity rows must be a list of objects.", details=violation("request_schema", field="entities/" + entity))
            user_fields: set[str] = set()
            for row in rows:
                if "id" in row:
                    fail("VALIDATION_FAILED", "The id field is server-assigned and cannot be supplied.", details=violation("unsupported_field", field="entities/" + entity + "/id"))
                user_fields.update(row.keys())
            for name in user_fields:
                validate_identifier(name, field=f"entities/{entity}/{name}")
                _reject_reserved_field(name, field=f"entities/{entity}/{name}")
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

    # ---- idempotency (contract 1.7.0 D-5, WP-2c) --------------------------

    def _idempotency_reclaim(self, *, now: float) -> None:
        """Ruling I-6: an elapsed record is "treated as absent"; deletion
        may be lazy. This is the lazy reclaim -- called from both the
        lookup and the capacity-reservation paths below, never from a
        background thread or timer (禁止事項 5: "背景スレッド・定期ジョブ
        を置かない")."""
        expired = [key for key, record in self._idempotency.items() if record.expires_at <= now]
        for key in expired:
            del self._idempotency[key]

    def _idempotency_lookup(self, key: str, *, now: float) -> "_IdempotencyRecord | None":
        self._idempotency_reclaim(now=now)
        return self._idempotency.get(key)

    def _idempotency_reserve(self, limits: ResourceLimits, *, now: float) -> None:
        """Ruling I-6/D-5 (5): the full-table refusal -- reclaim elapsed
        records first, THEN check capacity, BEFORE this request executes
        anything (this is called from `transact`/`apply_schema` before
        target existence, never after a tentative write). Reuses the
        SAME generic `ResourceLimits.check()` every other COUNT-valued
        class already uses, so the `LIMIT_EXCEEDED`/`limit_class` shape is
        identical to every other resource-exhaustion refusal in this
        codebase, not a bespoke one."""
        self._idempotency_reclaim(now=now)
        limits.check("idempotency_entries", len(self._idempotency) + 1)

    def _idempotency_store(self, key: str, *, digest: str, kind: str, payload: dict[str, Any], now: float, retention_ms: int) -> None:
        self._idempotency[key] = _IdempotencyRecord(digest=digest, kind=kind, payload=payload, expires_at=now + retention_ms / 1000)

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
        validate_identifier(entity, field="entity")
        # WP-2(b) fix round 2 (coordinator item C): reserved at every
        # identifier position, not only at creation time -- a query
        # against `entity="audit_events"` is refused as reserved, never
        # merely NOT_FOUND (no real entity of that name can ever exist,
        # since create_entity already refuses it, but the refusal reason
        # should say so directly rather than via a generic 404).
        _reject_reserved_entity_name(entity, field="entity")
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
            # M-2 (`{scratchpad}/audit-wp2e-2.md` R-3): `field_type`
            # (this catch's pre-M-2 `violated_declaration`) requires BOTH
            # `declared_type`/`observed_type` -- neither is attributable
            # here (`lt`/`lte`/`gt`/`gte` against an UNTYPED field is
            # never type-checked up front, module docstring's own
            # documented divergence; a raise here can come from ANY
            # predicate against ANY matching row, not one statically
            # knowable field/type pair). `request_schema` (like the
            # sibling empty/non-list `in` catch a few lines above)
            # correctly needs no type pair.
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.", details=violation("request_schema", field="where"))
        rows = _sort_rows(rows, order_spec)
        # keyset paging (design D-3 (3), D-6): the cursor's binding hash covers the Application scope, entity, and the normalized where/order_by only (never select/size) -- the same shared helper `PostgresCell.query` uses, so both backends bind/refuse a cursor identically.
        where_terms = [(p.field, p.operator, p.value) for p in where]
        binding = canonical_page_binding(self.application_id, entity, where_terms, order_spec)
        cursor_values: list[Any] | None = None
        if cursor is not None:
            cursor_values = decode_and_check_page_cursor(cursor, binding, order_spec, field_types)
        if cursor_values is not None:
            # keyset paging (design D-3 (5)): the keyset window, using `_sort_
            # key`-based position comparison -- the in-memory equivalent of
            # `PostgresCell`'s own keyset predicate, same NULL/direction
            # rules.
            rows = [row for row in rows if _after_page_cursor([row.get(field_name) for field_name, _direction in order_spec], cursor_values, order_spec)]
        # keyset paging: counted AFTER the cursor position narrows `rows`,
        # so this cell agrees with `PostgresCell.query` (whose own `rows`
        # is already the post-keyset, post-LIMIT fetch) on what a page
        # "returns" -- never the count of matches from the start of the
        # (unpaged) order, which page.size alone may have already left
        # behind a cursor.
        limits.check("result_items", min(len(rows), page_size))
        window = rows[: page_size + 1]
        has_more = len(window) > page_size
        page_rows = window[:page_size]
        items = [{field_name: row.get(field_name) for field_name in select} for row in page_rows]
        revisions = [row["_r2db_revision"] for row in page_rows]
        next_cursor = None
        if has_more:
            last_row = page_rows[-1]
            cursor_position = [last_row.get(field_name) for field_name, _direction in order_spec]
            next_cursor = encode_page_cursor(cursor_position, binding)
        return QueryOutcome(items=items, revisions=revisions, has_more=has_more, next_cursor=next_cursor)

    def _describe_entity(self, name: str) -> dict[str, Any]:
        """One entity's `EntityDescriptor` (contract shape) -- factored out
        of `catalog()` below (WP-2b) so `apply_schema`'s own `dry_run`
        response can build the identical descriptor for the ONE entity a
        schema operation targets (D-4 (3): "schema なら変更後の
        EntityDescriptor を descriptor に載せる"), without duplicating this
        construction logic a second time."""
        fields = sorted(self.schema.get(name, {}).keys())
        unique_keys = [
            {"name": index_name, "fields": list(info["fields"])}
            for index_name, info in sorted(self.indexes.get(name, {}).items())
            if info["unique"]
        ]
        # Phase 6 WP-2 (design D-3(iii)): every name in `fields` maps to
        # its real type, drawn from the same 7-word vocabulary --
        # `self.schema[name]`'s internal `None` (untyped) reports as
        # `json`, decision (ii)'s own default, never left un-translated.
        declared_field_types = self.schema.get(name, {})
        # Contract 1.7.0 (D-2 (1), WP-2a): total over `fields` --
        # `nullable` always present, `enum` only for a field the
        # registry (`self.field_constraints`) actually carries a row
        # for. Read from the registry itself, never re-derived from
        # any physical/stored value (D-2 (4): "catalog は...宣言
        # registry から報告する").
        declared_constraints = self.field_constraints.get(name, {})
        field_constraints_out: dict[str, Any] = {}
        for field_name in fields:
            constraints = declared_constraints.get(field_name, FieldConstraints())
            entry: dict[str, Any] = {"nullable": constraints.nullable}
            if constraints.enum is not None:
                entry["enum"] = list(constraints.enum)
            field_constraints_out[field_name] = entry
        return {
            "entity": name,
            "fields": fields,
            "field_types": {field_name: declared_field_types.get(field_name) or "json" for field_name in fields},
            "field_constraints": field_constraints_out,
            "mutation_class": "mutable",
            "address_fields": ["id"],
            "address_reuse": "never",
            "unique_keys": unique_keys,
        }

    def catalog(self, limits: ResourceLimits | None = None) -> list[dict[str, Any]]:
        return [self._describe_entity(name) for name in sorted(self.entities)]

    def transact(
        self,
        entity: str,
        operations: list[dict[str, Any]],
        limits: ResourceLimits,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> MutationOutcome:
        """Ruling U-7 (WP-6d): thin lock wrapper -- `self._idempotency_lock`
        is held for this call's entire duration, so a concurrent thread
        calling `transact`/`apply_schema` on this SAME cell cannot
        interleave with this one's own idempotency lookup -> execute ->
        store window (see `_idempotency_lock`'s own field comment above).
        All actual behavior lives in `_transact_locked` below, unchanged.
        """
        with self._idempotency_lock:
            return self._transact_locked(
                entity, operations, limits,
                deadline=deadline, clock=clock, audit_hook=audit_hook, dry_run=dry_run,
                plan=plan, plan_request=plan_request, idempotency_key=idempotency_key, request_id=request_id,
            )

    def _transact_locked(
        self,
        entity: str,
        operations: list[dict[str, Any]],
        limits: ResourceLimits,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> MutationOutcome:
        """`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
        `dry_run` walks every gate a real request would (no early-out
        anywhere above or inside this method) and this method's own
        SINGLE tx-exit point -- after the per-operation loop below, before
        this method's own commit point -- decides plan validity, then
        commit vs rollback; it never branches mid-loop (D-4 (2): a
        mid-loop branch would make "reaches the same decision" false).
        `plan_request`, when given, is the contract-level request object
        `service.py` assembled (`entity`/`operations`/`transaction`/
        `budget`, never `plan`/`dry_run` themselves -- H-1, `{scratchpad}/
        rulings-r4.md` addendum 2: `entity` is this request's own target,
        the URL path segment, at the object's own top level) --
        `expected_plan` below is
        computed from it together with THIS entity's Application's own
        `schema_revision`, read once, before the loop runs (mutations
        never advance it, so reading it before or after is the identical
        value; D-4 (7): the plan commits to the revision "as it stood
        when the request was decided", not a value the loop could still
        change). A caller-supplied `plan` that no longer matches is a
        precondition failure (D-4 (2): evaluated after confirmation --
        every confirmation check inside `_apply` below already raised, if
        it was going to, before this point is ever reached -- and before
        this method's own commit).

        Review round F-5 (`{scratchpad}/rulings-r4.md`): `service.py`
        builds `plan_request` unconditionally for every mutation, so the
        digest below is only computed when it is actually consumed --
        `dry_run`'s own response, or a caller-presented `plan` to verify
        -- never for the ordinary apply that carries neither. A plain
        apply pays no `json.dumps`/`sha256` cost it never uses.
        """
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity, field="entity")
        _reject_reserved_entity_name(entity, field="entity")  # WP-2(b) fix round 2, item C
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.", details=violation("request_schema", field="operations"))
        limits.check("batch_items", len(operations))
        # Contract 1.7.0 (D-5 (8), addendum 2 S-b, ruling I-3, WP-2c): the
        # idempotency lookup sits HERE -- after every bound this method's
        # own caller (`service.py`) and the batch-size bound just above
        # have already checked, before the entity-existence check right
        # below (this contract's own `target-existence` stage, the first
        # of `destructive_confirmation.evaluation_order`'s four). A
        # `dry_run` never consults or writes a record at all (ruling I-7 /
        # D-4): the guard below is `idempotency_key is not None and not
        # dry_run`, never merely `idempotency_key is not None`.
        idempotency_digest_value: str | None = None
        idempotency_now: float = 0.0
        if idempotency_key is not None and not dry_run:
            assert plan_request is not None  # service.py always builds this
            idempotency_digest_value = idempotency_digest(plan_request)
            idempotency_now = clock() if clock is not None else 0.0
            record = self._idempotency_lookup(idempotency_key, now=idempotency_now)
            # L-6/M-6: a record with no `request_id` (pre-1.7.0) is not a
            # usable replay source -- treated as absent, checked before
            # the digest comparison below.
            if record is not None and _idempotency_record_has_request_id(record.payload):
                if record.digest != idempotency_digest_value:
                    fail(
                        "CONFLICT", "This idempotency key was already used with a different request.", status=409,
                        details={"violated_declaration": "idempotency_key", "field": "idempotency_key"},
                    )
                # Ruling I-3/I-8: answered from the record -- target
                # existence, confirmation, precondition and execution
                # (everything below this point) never run for a replay.
                payload = record.payload
                return MutationOutcome(
                    affected=payload["affected"], assigned_addresses=payload["assigned_addresses"],
                    destructive=False, committed=True, plan=None, replayed=True,
                    # Contract 1.7.0 (D-7 (3), WP-2e): the ORIGINAL
                    # execution's own `request_id` -- read back from the
                    # record's own payload (guaranteed present, M-6: no
                    # fallback to this resend's own request_id).
                    request_id=payload["request_id"],
                )
            # Ruling I-6/D-5 (5): capacity is checked BEFORE this request
            # executes anything -- reclaiming elapsed records first.
            self._idempotency_reserve(limits, now=idempotency_now)
        if entity not in self.entities:
            fail("NOT_FOUND", "Entity was not found.", status=404)
        expected_plan = (
            compute_plan_token(plan_request, self.schema_revision)
            if plan_request is not None and (dry_run or plan is not None)
            else None
        )
        before = deepcopy(self.entities[entity])
        try:
            affected = 0
            assigned_addresses: list[dict[str, Any]] = []
            # Phase 4 (design D-2): whether this batch passed through the
            # DESTRUCTIVE_CONFIRMATION_V1 choke -- what
            # `MutationOutcome.destructive` reports. Tracked here (not re-derived
            # from `operations` after the fact) because it is `_apply`'s
            # own successful pass through `require_destructive_
            # confirmation` that establishes it, not merely the presence
            # of a `delete` key in the request.
            destructive = False
            for operation_index, operation in enumerate(operations):
                if deadline is not None and clock is not None:
                    # WP-2 review M-2: per-operation deadline check, not
                    # only before/after the whole batch -- a unique-index
                    # write check is O(rows) per operation, so an O(N^2)-ish
                    # batch (many operations against a large, uniquely-
                    # indexed entity) could otherwise run well past the
                    # execution budget before the next checkpoint.
                    limits.check_deadline(deadline, clock)
                # Monitor ruling M-3/D (rulings-wp2a-review.md, rulings-
                # wp3a-review.md D): `operation_index` is this operation's
                # own position in the request's `operations` list --
                # `_apply` below uses it to compose `details.field` as a
                # request-internal path (`operations/<i>/values/<field>`,
                # D-3 (2)) for any VALIDATION_FAILED it raises validating
                # this operation's own `values`.
                count, address, op_destructive = self._apply(entity, operation, operation_index)
                affected += count
                destructive = destructive or op_destructive
                if address is not None:
                    assigned_addresses.append(address)
                limits.check("result_items", affected)
            # Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit
            # point -- plan validity, then commit vs rollback. Reached
            # only once every operation above has tentatively succeeded
            # (every confirmation/precondition/value/limit refusal inside
            # the loop already raised and is handled by the `except
            # Exception` below, restoring `before` -- this point is never
            # reached for those).
            if plan is not None and plan != expected_plan:
                fail(
                    "PRECONDITION_FAILED", "The plan no longer matches this request or the Application's schema.",
                    status=412, details={"violated_declaration": "plan"},
                )
            if dry_run:
                # D-4 (4)/(6): rollback (never the audit hook -- `service.
                # py` never builds one for a dry_run in the first place,
                # so `audit_hook` is always `None` here) -- the identical
                # single-exit restore the `except Exception` clause below
                # uses for every OTHER refusal, just reached by a
                # successful decision instead of a raised one.
                self.entities[entity] = before
                return MutationOutcome(
                    affected=affected, assigned_addresses=assigned_addresses, destructive=destructive,
                    committed=False, plan=expected_plan, request_id=request_id,
                )
            # Phase 4 (design D-2/D-10): the pre-commit hook is called for
            # every real batch, not only a destructive one, as the LAST
            # thing this method does before its own commit point (here:
            # returning normally -- this in-memory backend has no separate
            # commit step that could itself fail once this call returns,
            # unlike `PostgresCell`, so there is no `commit_failed()`
            # counterpart call anywhere in this class). A raise here is
            # caught by the `except Exception` below, exactly like any
            # other mid-batch failure -- restoring `before` and propagating
            # (fail-closed by construction, no special-casing needed).
            if audit_hook is not None:
                audit_hook.pre_commit()
            # Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c): recorded
            # in the SAME critical section as the commit above -- this
            # in-memory backend has no separate transaction boundary
            # (`ApplicationCell` serves one operation at a time), so
            # "same tx" here means: written only once every operation in
            # the loop above has already tentatively succeeded, at the
            # identical point the real commit is decided, never before.
            # If anything below this point still raised, the `except
            # Exception` clause restores `before` -- but no code below
            # this comment can raise (`_idempotency_store` never fails),
            # so a written record and a committed batch are inseparable.
            if idempotency_key is not None and idempotency_digest_value is not None:
                self._idempotency_store(
                    idempotency_key, digest=idempotency_digest_value, kind="mutation",
                    # Contract 1.7.0 (D-7 (3), WP-2e): `request_id` rides
                    # in the same payload the replay branch above reads
                    # back from -- so a future replay returns THIS
                    # execution's own `request_id`, not a fresh one.
                    payload={"affected": affected, "assigned_addresses": assigned_addresses, "request_id": request_id},
                    now=idempotency_now, retention_ms=limits.idempotency_retention_ms,
                )
            return MutationOutcome(affected=affected, assigned_addresses=assigned_addresses, destructive=destructive, committed=True, request_id=request_id)
        except Exception:
            self.entities[entity] = before
            raise

    def _apply(self, entity: str, operation: dict[str, Any], operation_index: int) -> tuple[int, dict[str, Any] | None, bool]:
        field_types = self.schema.get(entity, {})
        known_fields = set(field_types.keys())
        bound = bind_mutation(operation, known_fields, operation_index=operation_index)
        # Contract 1.7.0 (D-2 (4), WP-2a): the registry's own entry for
        # this entity -- addendum 2 S-k's 6 write call sites (3 here, 3 in
        # `postgres.py`) all pass THIS through to `_check_type`; the 2
        # predicate call sites (`_validate_predicate_types`, below and in
        # `query`) never do (D-2 (2): a query predicate is not bound by
        # `enum`/`nullable`).
        entity_constraints = self.field_constraints.get(entity, {})
        # Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): every
        # `details.field` this method raises for a VALUE-position defect
        # in `bound.values` names the request-internal PATH to that value
        # (`operations/<operation_index>/values/<field>`), never the bare
        # entity field name -- mirrors the contract text's own example
        # verbatim ("operations/0/values/label").
        values_path = f"operations/{operation_index}/values/"

        if bound.operation == "insert":
            # Contract 1.7.0 (D-2 (3)(ii), addendum R-c): the "declared
            # non-nullable field was never given a value at all" check --
            # unlike a null VALUE (checked per-value by the choke point,
            # `_check_type` below), an OMITTED field never reaches that
            # choke point at all (it is simply absent from `bound.values`),
            # so this structural check runs first, insert-only.
            missing_non_nullable = sorted({name for name, c in entity_constraints.items() if not c.nullable} - set(bound.values))
            if missing_non_nullable:
                missing_field = missing_non_nullable[0]
                fail(
                    "VALIDATION_FAILED",
                    "A field declared nullable: false requires a value on insert.",
                    details={"field": values_path + missing_field, "violated_declaration": "nullable", "declared_type": _declared_type_label(field_types.get(missing_field)), "observed_type": "absent"},
                )
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))
            self._check_unique_conflict(entity, bound.values, exclude_id=None)
            row = self._insert_row(entity, bound.values)
            return 1, {"address": {"id": row["id"]}}, False

        if bound.operation == "upsert":
            count, address = self._apply_upsert(entity, bound, field_types, entity_constraints, values_path)
            return count, address, False

        # update / delete: R-7, corrigendum M-9 -- validate every value's
        # type (predicate values, and for `update` the write values too)
        # before resolving a precondition or searching for target rows at
        # all, symmetric with the `insert` branch above.
        _validate_predicate_types(bound.where, field_types, path_prefix=f"operations/{operation_index}/where")
        if bound.operation == "update":
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))

        try:
            matches = [row for row in self.entities[entity] if all(_matches(row, p, field_types) for p in bound.where)]
        except (TypeError, ValueError):
            # M-2 (`{scratchpad}/audit-wp2e-2.md` R-3): `field_type`
            # (this catch's pre-M-2 `violated_declaration`) requires BOTH
            # `declared_type`/`observed_type` -- neither is attributable
            # here (`lt`/`lte`/`gt`/`gte` against an UNTYPED field is
            # never type-checked up front, module docstring's own
            # documented divergence; a raise here can come from ANY
            # predicate against ANY matching row, not one statically
            # knowable field/type pair). `request_schema` (like the
            # sibling empty/non-list `in` catch a few lines above)
            # correctly needs no type pair.
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.", details=violation("request_schema", field="where"))

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
            # Phase 4 (design D-2): reaching this point means `require_
            # destructive_confirmation` above did not raise -- this
            # operation is confirmed-destructive, the fail-closed dispatch
            # signal `transact` aggregates across the whole batch.
            if bound.expected_revision is not None:
                target = [row for row in matches if row["_r2db_revision"] == bound.expected_revision]
                if not target:
                    self._fail_precondition(matches)
                self.entities[entity].remove(target[0])
                return 1, None, True
            for row in matches:
                self.entities[entity].remove(row)
            return len(matches), None, True

        # update
        if bound.expected_revision is not None:
            target = [row for row in matches if row["_r2db_revision"] == bound.expected_revision]
            if not target:
                self._fail_precondition(matches)
            row = target[0]
            self._check_unique_conflict(entity, {**row, **bound.values}, exclude_id=row["id"])
            row.update(bound.values)
            row["_r2db_revision"] = str(uuid.uuid4())
            return 1, None, False
        if not bound.values:
            return len(matches), None, False
        for row in matches:
            self._check_unique_conflict(entity, {**row, **bound.values}, exclude_id=row["id"])
            row.update(bound.values)
            row["_r2db_revision"] = str(uuid.uuid4())
        return len(matches), None, False

    def _apply_upsert(self, entity: str, bound: BoundMutation, field_types: dict[str, str | None], entity_constraints: "dict[str, FieldConstraints]", values_path: str) -> tuple[int, dict[str, Any] | None]:
        declared = {name: info for name, info in self.indexes.get(entity, {}).items() if info["unique"]}
        if not declared:
            # R-5 / §0.5 Q-1 (adjudicated 案B): an entity declaring no
            # uniqueness key at all has no existence test upsert could use.
            fail("CAPABILITY_UNSUPPORTED", "Upsert requires a declared domain uniqueness key.", details=violation("capability", field="operation"))
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
            fail("VALIDATION_FAILED", "unique_key is required when an entity declares more than one uniqueness key.", details=violation("request_schema", field="unique_key"))
        if bound.where:
            fail("VALIDATION_FAILED", "Upsert does not accept a filter; its existence test is the entity's declared uniqueness key.", details=violation("unsupported_field", field="where"))
        key_fields = declared[key_name]["fields"]
        for key_field in key_fields:
            if bound.values.get(key_field) is None:
                fail("VALIDATION_FAILED", "Upsert values must include every uniqueness key field.", details=violation("request_schema", field="values/" + key_field))
        # R-7, corrigendum M-9: type-check before searching for an existing
        # row (symmetric with insert/update above).
        for key, value in bound.values.items():
            _check_type(value, field_types.get(key), values_path + key, constraints=entity_constraints.get(key))
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
        # Contract 1.7.0 (D-2 (3)(ii), (contract text): "An upsert that
        # resolves to an insert is refused on the same rule [as insert];
        # an upsert that resolves to an update is not"). This point is
        # reached ONLY when `existing` (checked above) found no row AND
        # there was no `expected_revision` -- i.e. this upsert is now
        # KNOWN to resolve to an insert, so the insert-only absent-field
        # rule applies, symmetric with the plain `insert` branch in
        # `_apply` above (never applied to the update-resolving branches
        # above this one, which never reach this line at all).
        missing_non_nullable = sorted({name for name, c in entity_constraints.items() if not c.nullable} - set(bound.values))
        if missing_non_nullable:
            missing_field = missing_non_nullable[0]
            fail(
                "VALIDATION_FAILED",
                "A field declared nullable: false requires a value on an upsert that resolves to an insert.",
                details={"field": values_path + missing_field, "violated_declaration": "nullable", "declared_type": _declared_type_label(field_types.get(missing_field)), "observed_type": "absent"},
            )
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

    def apply_schema(
        self,
        operation: dict[str, Any],
        *,
        developer: bool,
        limits: ResourceLimits,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> "SchemaOutcome":
        """Ruling U-7 (WP-6d): thin lock wrapper -- see `transact`'s
        identical wrapper above and `_idempotency_lock`'s own field
        comment. All actual behavior lives in `_apply_schema_locked`
        below, unchanged.
        """
        with self._idempotency_lock:
            return self._apply_schema_locked(
                operation, developer=developer, limits=limits, deadline=deadline, clock=clock,
                audit_hook=audit_hook, dry_run=dry_run, plan=plan, plan_request=plan_request,
                idempotency_key=idempotency_key, request_id=request_id,
            )

    def _apply_schema_locked(
        self,
        operation: dict[str, Any],
        *,
        developer: bool,
        limits: ResourceLimits,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
        audit_hook: ApplicationAuditHook | None = None,
        dry_run: bool = False,
        plan: str | None = None,
        plan_request: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> "SchemaOutcome":
        """`dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4, WP-2b):
        identical single tx-exit-point discipline to `transact` above,
        adapted to this method's own pre-existing `before_*`-snapshot
        restore machinery (5 pieces of state, not one `deepcopy`d dict).
        Always returns `SchemaOutcome` -- review round F-8 (`{scratchpad}/
        rulings-r4.md`): a bare `int` for one request and a `SchemaOutcome`
        for the structurally identical request differing only in whether
        it happened to carry `plan` was two shapes for the same call, not
        a backward-compatibility rule. `DataService.schema` (`service.py`)
        is a pure passthrough of this return value and therefore now
        always returns `SchemaOutcome` too -- its own pre-1.7.0-shaped
        direct callers read `.revision` off it instead of comparing the
        result itself to an `int`.
        """
        bound = bind_schema_operation(operation, developer=developer)
        # Contract 1.7.0 (D-5 (8)/(9), addendum 2 S-b, ruling I-3, WP-2c):
        # the idempotency lookup sits HERE -- as early as possible after
        # binding the request's own shape, before ANY operation-specific
        # accounting or target-dependent computation (including the
        # `schema_objects` projection just below, which for `drop_entity`/
        # `add_field`/etc. reads `bound.entity`'s CURRENT state -- reading
        # it for an entity a replay's own key already dropped would
        # compute nonsense, not merely skip a check the design allows
        # skipping). `dry_run` never consults or writes a record (ruling
        # I-7/D-4).
        idempotency_digest_value: str | None = None
        idempotency_now: float = 0.0
        if idempotency_key is not None and not dry_run:
            assert plan_request is not None  # service.py always builds this
            idempotency_digest_value = idempotency_digest(plan_request)
            idempotency_now = clock() if clock is not None else 0.0
            record = self._idempotency_lookup(idempotency_key, now=idempotency_now)
            # L-6/M-6: a record with no `request_id` (pre-1.7.0) is not a
            # usable replay source -- treated as absent, checked before
            # the digest comparison below.
            if record is not None and _idempotency_record_has_request_id(record.payload):
                if record.digest != idempotency_digest_value:
                    fail(
                        "CONFLICT", "This idempotency key was already used with a different request.", status=409,
                        details={"violated_declaration": "idempotency_key", "field": "idempotency_key"},
                    )
                # Ruling I-3/I-8/I-9: applies to schema operations too --
                # a resent `drop_entity` answers from the record even
                # though the entity, and any confirmation phrase computed
                # against it, are both long gone.
                payload = record.payload
                return SchemaOutcome(
                    committed=True, revision=payload["revision"], descriptor=None, plan=None, replayed=True,
                    # M-6: the ORIGINAL execution's own `request_id`, no
                    # fallback to this resend's own (guaranteed present).
                    request_id=payload["request_id"],
                )
            self._idempotency_reserve(limits, now=idempotency_now)
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
        elif bound.operation == "alter_field":
            # Contract 1.7.0 (D-2 (7), U-1 = (β), WP-2a): `alter_field`
            # redeclares an EXISTING field's constraints -- it creates no
            # new entity/field/index, so it never changes `schema_objects`
            # (that bound is unrelated to `enum_members`, checked
            # separately below once the field's real declared type is
            # known).
            projected_objects = current_objects
        else:  # drop_index
            projected_objects = current_objects - 1
        limits.check("schema_objects", projected_objects)
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        before_entities = deepcopy(self.entities)
        before_schema = deepcopy(self.schema)
        before_indexes = deepcopy(self.indexes)
        before_next_id = dict(self._next_id)
        before_field_constraints = deepcopy(self.field_constraints)
        before_revision = self.schema_revision
        # Contract 1.7.0 (D-4 (7)/(3), addendum 2 S-a/S-j, WP-2b): computed
        # against `before_revision` -- the revision "as it stood when the
        # request was decided" (D-4 (7)), never a value the branch below
        # could still establish -- so a dry run's own reported `revision`
        # (S-j) and a real apply's `plan` verification agree on the SAME
        # pre-operation state. Review round F-5: only computed when
        # `dry_run`'s own response or a caller-presented `plan` actually
        # consumes it -- an ordinary schema apply pays no digest cost.
        expected_plan = (
            compute_plan_token(plan_request, before_revision)
            if plan_request is not None and (dry_run or plan is not None)
            else None
        )

        def _restore_before_snapshot() -> None:
            self.entities = before_entities
            self.schema = before_schema
            self.indexes = before_indexes
            self._next_id = before_next_id
            self.field_constraints = before_field_constraints
            self.schema_revision = before_revision

        if bound.operation == "create_entity":
            if bound.entity in self.entities:
                fail("CONFLICT", "Entity already exists.", status=409)
            # Contract 1.7.0 (D-2 (1)/(7), WP-2a): `enum_members` is
            # checked BEFORE any mutation below (limits.enum_members's own
            # text: "before anything is created or altered") -- `fail()`
            # raised from inside this method is not caught by anything
            # short of unwinding the whole call (only the plan, dry-run and
            # audit-hook points below restore `before_*`; the deadline is
            # checked once at entry, before anything is snapshotted, and
            # never after the operation), so this must run first, not merely
            # "before `schema_revision` advances".
            # history: CH-0552
            for constraints in bound.field_constraints.values():
                if constraints.enum is not None:
                    limits.check("enum_members", len(constraints.enum))
            self.entities[bound.entity] = []
            # a name present in `bound.
            # field_types` gets its declared type; every other name in
            # `bound.fields` keeps the pre-WP-2 default (`None` == `json`,
            # decision (ii)) via `dict.get`'s own implicit fallback.
            # history: CH-0553
            self.schema[bound.entity] = {name: bound.field_types.get(name) for name in bound.fields}
            self.schema[bound.entity]["id"] = "integer"
            self.indexes[bound.entity] = {}
            # Only fields the request itself gave a `field_constraints`
            # spec ever touch the registry (D-2 (1): "省略 = 制約なし").
            # history: CH-0554
            for field_name, constraints in bound.field_constraints.items():
                if constraints.is_declared:
                    self.field_constraints.setdefault(bound.entity, {})[field_name] = constraints
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
            # address_reuse is scoped to one entity's lifetime; a drop
            # ends that lifetime, so a later create_entity of the same name
            # is a new entity and its addresses start at 1 again.
            # history: CH-0555
            self._next_id.pop(bound.entity, None)
            # Contract 1.7.0 (D-2 (4)): the registry is scoped to
            # the entity's own lifetime too, symmetric with `schema`/
            # `indexes`/`_next_id` above -- a later `create_entity` of the
            # same name is a new entity with no inherited constraints.
            # history: CH-0556
            self.field_constraints.pop(bound.entity, None)
        elif bound.operation == "add_field":
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.field in self.schema.setdefault(bound.entity, {}):
                fail("CONFLICT", "Field already exists.", status=409)
            # Contract 1.7.0 (D-2 (1)/(7), WP-2a): `add_field`'s own
            # single-field declaration, mirroring `create_entity`'s enum_
            # members check above -- checked BEFORE the mutation just
            # below (`bound.constraints` is `None` when the request never
            # carried `enum`/`nullable` at all).
            # history: CH-0557
            if bound.constraints is not None and bound.constraints.enum is not None:
                limits.check("enum_members", len(bound.constraints.enum))
            # "An add_field declaring nullable: false on an
            # entity that already holds rows is refused with CONFLICT on
            # the same rule, because every existing row would hold null in
            # the new field" -- the SAME rule `alter_field`'s own existing-
            # row scan enforces (D-2 (6)), applied here since a brand new
            # field with no default always starts every existing row at
            # `null`. Checked BEFORE the field is created (fail-closed:
            # nothing has been mutated yet at this point).
            # history: CH-0558
            if bound.constraints is not None and not bound.constraints.nullable and self.entities[bound.entity]:
                fail(
                    "CONFLICT",
                    "Existing rows would hold null in a field declared nullable: false.",
                    status=409,
                    details={"field": bound.field, "violated_declaration": "nullable"},
                )
            self.schema[bound.entity][bound.field] = bound.field_type
            if bound.constraints is not None and bound.constraints.is_declared:
                self.field_constraints.setdefault(bound.entity, {})[bound.field] = bound.constraints
        elif bound.operation == "alter_field":
            # Contract 1.7.0 (D-2 (5)/(6), WP-2a): "redeclares the
            # constraints of one existing field" -- both the entity and
            # the field must already exist (`field_type` redeclaration is
            # rejected earlier, at bind time, `bind_schema_operation`).
            # history: CH-0559
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.field not in self.schema.get(bound.entity, {}):
                fail("NOT_FOUND", "Field was not found.", status=404)
            declared_type = self.schema[bound.entity][bound.field]
            patch = bound.constraint_patch
            assert patch is not None  # bind_schema_operation always sets this for alter_field
            # compose the request's PATCH against the field's
            # EXISTING declared constraints -- only known here, never at
            # bind time (addendum R-b/R-c, D-2 (3)). `enum` omitted/
            # `nullable` omitted each LEAVE the existing value as it is;
            # `enum: null` CLEARS it; an explicit list is fully validated
            # against the field's real declared type now.
            # history: CH-0560
            existing_constraints = self.field_constraints.get(bound.entity, {}).get(bound.field, FieldConstraints())
            new_nullable = existing_constraints.nullable if patch.nullable_omitted else patch.nullable
            if patch.enum_clear:
                new_enum: tuple[Any, ...] | None = None
            elif patch.enum_omitted:
                new_enum = existing_constraints.enum
            else:
                try:
                    new_enum = validate_enum_declaration(list(patch.enum_raw), declared_type)
                except _ConstraintDeclarationError as exc:
                    _fail_constraint_declaration("enum", declared_type, exc)
                limits.check("enum_members", len(new_enum))
            new_constraints = FieldConstraints(enum=new_enum, nullable=new_nullable)
            # Contract 1.7.0 (D-2 (6)): every existing row is checked
            # against the constraints this operation would establish,
            # BEFORE anything commits -- one violating row refuses the
            # WHOLE operation with CONFLICT, changing nothing (this
            # method's own fail-closed/`before_*`-restore machinery, never
            # reached here since nothing has been mutated yet at this
            # point).
            #
            # Monitor ruling F (rulings-wp3a-review.md, applied to r2db by
            # M-1/rulings-wp2a-review.md): `PostgresCell.apply_schema`'s
            # own alter_field branch takes `LOCK TABLE ... IN SHARE ROW
            # EXCLUSIVE MODE` (plain `SHARE MODE` does not conflict with
            # itself and can deadlock two concurrent callers at their own
            # later `ALTER TABLE`, R-35, Phase 10, WP-6d-i review) before
            # this same scan, closing a race where another transaction
            # commits a violating row between the scan and the registry
            # write. This in-memory backend needs no such lock:
            # `ApplicationCell` serves one process, one operation at a
            # time (there is no concurrent transaction that could commit a
            # row between this scan and `entity_registry[...]` below), so
            # the scan-then-write sequence is already atomic by
            # construction.
            # history: CH-0561
            violated_declaration: str | None = None
            for row in self.entities[bound.entity]:
                value = row.get(bound.field)
                if value is None:
                    if not new_constraints.nullable:
                        violated_declaration = "nullable"
                        break
                    continue
                if new_constraints.enum is not None and value not in new_constraints.enum:
                    violated_declaration = "enum"
                    break
            if violated_declaration is not None:
                fail(
                    "CONFLICT",
                    "Existing rows violate the constraints this alter_field would establish.",
                    status=409,
                    details={"field": bound.field, "violated_declaration": violated_declaration},
                )
            entity_registry = self.field_constraints.setdefault(bound.entity, {})
            if new_constraints.is_declared:
                entity_registry[bound.field] = new_constraints
            else:
                entity_registry.pop(bound.field, None)
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
                # unify with every other CONFLICT in this
                # module at HTTP 409 (this one previously fell through to
                # `fail`'s 400 default).
                # history: CH-0562
                fail("CONFLICT", "Existing data violates the requested uniqueness.", status=409)
            self.indexes.setdefault(bound.entity, {})[bound.index] = {"fields": bound.index_fields, "unique": bound.unique}
        else:  # drop_index
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.index not in self.indexes.get(bound.entity, {}):
                fail("NOT_FOUND", "Index was not found.", status=404)
            # dropping a unique index removes a
            # guardrail (uniqueness) and can silently re-enable upsert's
            # CAPABILITY_UNSUPPORTED gate to flip -- SI-09 destructive
            # confirmation applies exactly like drop_entity.
            # history: CH-0563
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                drop_index_confirmation_phrase(bound.entity, bound.index, self.schema_revision),
                "Dropping an index requires explicit destructive confirmation.",
                consequence="The index is destroyed; query semantics are unaffected, only performance (and any uniqueness guarantee it enforced) are lost.",
                reversible_alternative=None,
                recovery="create_index with the same definition restores it -- an index carries no data of its own, so this fully restores a non-unique index; recreating a UNIQUE index re-validates existing rows against that uniqueness and can instead fail with CONFLICT if data written after the drop now violates it.",
            )
            del self.indexes[bound.entity][bound.index]
        # Contract 1.7.0 (D-4 (2)/(4), WP-2b): the single tx-exit point --
        # plan validity, then commit vs rollback. Reached only once the
        # operation branch above has already tentatively succeeded (a
        # `require_destructive_confirmation` failure inside the
        # `drop_entity`/`drop_index` branches above already raised, and is
        # handled below, before this point is ever reached for it -- D-4
        # (2)'s own "confirmation の後、execution の前" ordering, and the
        # reason an unconfirmed `drop_entity` carrying a stale `plan` is
        # refused DESTRUCTIVE_CONFIRMATION_REQUIRED, never PRECONDITION_
        # FAILED).
        if plan is not None and plan != expected_plan:
            _restore_before_snapshot()
            fail(
                "PRECONDITION_FAILED", "The plan no longer matches this request or the Application's schema.",
                status=412, details={"violated_declaration": "plan"},
            )
        if dry_run:
            # D-4 (3)/(4): `descriptor` is the target entity's own
            # descriptor as it would read afterwards -- `None` for a
            # dry-run `drop_entity` (the entity no longer exists in the
            # tentative state at this point) -- built BEFORE restoring.
            # `revision` (S-j) is `before_revision`, never `schema_
            # revision + 1` (never reached here: this branch returns
            # before that increment). No audit hook call either way (D-4
            # (4): `service.py` never builds one for a dry_run).
            descriptor = self._describe_entity(bound.entity) if bound.entity in self.entities else None
            _restore_before_snapshot()
            return SchemaOutcome(committed=False, revision=before_revision, descriptor=descriptor, plan=expected_plan, request_id=request_id)
        # every schema operation is
        # fail-closed class, unconditionally (unlike `transact`, there is
        # no non-destructive schema operation) -- the pre-commit hook is
        # called as the last thing this method does before its own commit
        # point (here: `schema_revision += 1` and returning). A raise here
        # restores every piece of state this method may have mutated,
        # using the same `before_*` snapshots the dry-run and plan-mismatch
        # branches above use, and propagates -- fail-closed by
        # construction, no separate rollback path needed.
        # history: CH-0564
        if audit_hook is not None:
            try:
                audit_hook.pre_commit()
            except Exception:
                _restore_before_snapshot()
                raise
        self.schema_revision += 1
        # Contract 1.7.0 (D-5 (1)(i)/(3), ruling I-1, WP-2c): recorded in
        # the same critical section as the commit just above, mirroring
        # `transact`'s identical comment -- nothing below this point can
        # raise, so a written record and a committed operation are
        # inseparable.
        if idempotency_key is not None and idempotency_digest_value is not None:
            self._idempotency_store(
                idempotency_key, digest=idempotency_digest_value, kind="schema",
                # Contract 1.7.0 (D-7 (3), WP-2e): see `transact`'s
                # identical comment -- `request_id` rides in the payload a
                # future replay reads back.
                payload={"revision": self.schema_revision, "request_id": request_id},
                now=idempotency_now, retention_ms=limits.idempotency_retention_ms,
            )
        # Review round F-8: always `SchemaOutcome`, plan or no plan --
        # every pre-1.7.0 direct caller of this method (`test_constraints_
        # declaration.py`'s many `cell.apply_schema(...)` call sites among
        # them) now reads `.revision` off the result instead of comparing
        # the result itself to an `int`.
        return SchemaOutcome(committed=True, revision=self.schema_revision, request_id=request_id)
