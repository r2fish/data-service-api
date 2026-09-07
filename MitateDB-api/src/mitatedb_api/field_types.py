"""Contract field-type vocabulary and declared-type value validation
(Phase 6 WP-3, design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md
D-3, G3).

Contract 1.6.0's `field_type` enum gains a seventh member, `json` (any
JSON value); this module is the ONE place that vocabulary lives on this
peer, and the ONE place a value is checked against a DECLARED member of it
-- the `_prepare_values`/`_bind_filters` choke point in `cell.py` (R-2/B-1
style: this is the same kind of backend-independent, single-point
validation `r2db_api.structured._check_type` already is for that peer,
independently arrived at here, R-2's own closing paragraph). Backend
domain checks (`backend_postgres.py`) stay as defence-in-depth UNDER this
layer, never instead of it.

``CONTRACT_TYPES`` is this peer's own copy of the contract's
``schemas.SchemaOperationRequest.properties.field_type`` enum -- kept as a
literal tuple (not read from the packaged contract at runtime) because it
is also this module's own registry vocabulary, load-bearing for the SQL
this peer writes (a CHECK constraint) -- `tests/test_foundation.py`'s
sibling contract-vocabulary pin tests (e.g. `test_conformance_public_
surface_coverage.py`) are what catches this copy drifting from the
contract itself.
"""
from __future__ import annotations

from typing import Any

from .errors import ValidationError, violation

#: Contract 1.6.0 `field_type` enum (`schemas.SchemaOperationRequest.
#: properties.field_type.enum` / `definitions.EntityDescriptor.properties.
#: field_types` values) -- 7 members, `json` the newest.
CONTRACT_TYPES = ("string", "integer", "number", "boolean", "object", "array", "json")

#: This peer's own foundation/physical vocabulary (`cell._FIELD_TYPE_
#: VOCABULARY`) that a contract type maps onto for DDL purposes. `object`/
#: `array`/`json` all share the physical `json` (TEXT) column -- the
#: declared-type REGISTRY (not this map, and not the physical column) is
#: what recovers which of the three a field actually is (design §1.5
#: finding 1b/2).
CONTRACT_TYPE_TO_FOUNDATION_TYPE = {
    "string": "text",
    "integer": "integer",
    "number": "real",
    "boolean": "boolean",
    "object": "json",
    "array": "json",
    "json": "json",
}

#: The inverse, used ONLY as the derived/default declared contract type
#: for a field created through a pre-1.6.0-shaped call that names a
#: FOUNDATION type directly and supplies no explicit contract type
#: (`cell.ApplicationCell.create_collection`/`add_field`'s own direct
#: callers -- this repository's own tests, the in-process conformance
#: adapter's `create_collection`). `object`/`array` cannot be recovered
#: this way (both collapse to foundation `json`); a caller that needs
#: that distinction must supply an explicit contract type instead. This
#: is the SAME backfill rule the `0006` upgrade script applies to
#: existing columns (design §1.5 finding 2a) -- one table, two use sites.
FOUNDATION_TYPE_TO_CONTRACT_TYPE = {
    "text": "string",
    "integer": "integer",
    "real": "number",
    "boolean": "boolean",
    "json": "json",
}


#: Declared field types an `enum` constraint may be attached to (design
#: D-2 (2): "要素は field の宣言型...の値のみであり、object/array/json の
#: field には宣言できない").
_ENUM_ELIGIBLE_TYPES = ("string", "integer", "number", "boolean")


def json_type_name(value: Any) -> str:
    """WP-3a closure (監督裁定 2026-09-07, audit `wp3a-closure` §3 G3):
    names the JSON type of an already-decoded request value, using the
    identical vocabulary word `CONTRACT_TYPES` already uses for each type
    except `null` (JSON has no `field_type` member for it, since no field
    can be DECLARED that type -- but a request VALUE can still observe
    it, e.g. `field_constraints.<field>.nullable: null`). Used only to
    fill a D-3 `details.observed_type` for a request-shape violation
    that IS about a value's own type (contract `errors.details_vocabulary`
    D-3 (3): declared_type/observed_type are included only for "a
    violation about the type of a value", never for a missing key or an
    unrecognized field name). `bool` is checked before `int` -- the same
    ordering `check_declared_value`/`enum_member_matches_type` already
    use, since `isinstance(True, int)` is `True` in Python."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"  # pragma: no cover -- unreachable: upstream JSON decoding never produces any other type


def enum_member_matches_type(value: Any, declared_type: str | None) -> bool:
    """WP-3a rework 2 (監督裁定 m-3, 2026-09-07 -- helper name shared
    with r2db-api's own isomorphism-tested counterpart, isomorphism
    pairing added by the supervisor's own pair-closing commit, work
    order §4 の 12 / §6 訂正註 10): the scalar type-membership test both
    `check_declared_value`'s own `string`/`integer`/`number`/`boolean`
    branches AND `validate_enum_declaration`'s own per-member check
    need -- extracted to one place so the two never drift (previously
    `validate_enum_declaration` called `check_declared_value` itself for
    this, which worked but hid this test as a side effect of a function
    whose real job is choke-point VALUE validation, not enum-member
    type-checking in isolation).

    Never accepts `None` here -- callers reject a null member up front
    (`enum` constrains non-null values only). `declared_type` outside
    `_ENUM_ELIGIBLE_TYPES` never reaches this function at all --
    `validate_enum_declaration` below rejects the declaration itself
    first, so this function's own fallback is unreachable in practice
    (kept as a plain `False`, never a raise, since a predicate function
    has no `details` shape of its own to attach).

    `bool` is checked before `int` (Python's `isinstance(True, int)` is
    `True`) so an unguarded `integer`/`number` branch never silently
    accepts a `bool` member -- same precedent `check_declared_value`'s
    own docstring already states."""
    if declared_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared_type == "boolean":
        return isinstance(value, bool)
    if declared_type == "string":
        return isinstance(value, str)
    return False


def check_declared_value(value: Any, declared_type: "str | None", *, constraints: "dict | None" = None) -> None:
    """The cell-layer choke point itself (design G3): raises `errors.
    ValidationError` when `value` does not match `declared_type` (one of
    `CONTRACT_TYPES`). `declared_type` of `None` (no registry row -- must
    not occur for a field this peer itself created after this WP, but
    tolerated defensively) skips the check entirely, matching this
    foundation's own pre-D-3 behaviour for that field. `json` never
    rejects: it is "any JSON value", and every value reaching this point
    has ALREADY passed `ApplicationCell._normalize_value`'s own upstream
    shape check (str/int/float/bool/None/dict/list only), so it is
    already JSON-representable by construction.

    `bool` is checked before `int` in every branch that needs it -- in
    Python, `isinstance(True, int)` is `True`, so an unguarded `integer`/
    `number` check would silently accept a `bool` (mirrors r2db-api's own
    `structured._check_type`, independently applied here).

    Phase 9 WP-3a (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (3),
    keyword-only `constraints` per the design's own fixed new signature
    for this function): `constraints`, when given, is this field's own
    `{"nullable": bool, "enum": [...]}` declaration (the "enum" key
    present only when one is declared) -- `None` (every caller reading a
    query predicate, `cell.py::_bind_filters`) means this call enforces
    type ONLY, exactly as before this WP (D-2 (3): "query の predicate
    値は enum を検査しない"). A caller writing a value (`cell.py::
    _prepare_values`, the ONE call site design D-2 (3)'s own table
    marks "渡す") always passes the field's resolved constraints, `enum`
    key included or omitted as the registry itself carries it.

    A `null` value is checked against `constraints["nullable"]` BEFORE
    the type branches below (SQL NULL passes every declared type
    otherwise, M-5 precedent) -- `nullable: false` raises with the D-3
    four-key shape this WP gives every denial it newly introduces
    (`violated_declaration: nullable`, `observed_type: null`,
    `declared_type`: this field's own declared type). A non-null value
    is then checked against `constraints["enum"]`, when declared, AFTER
    the type branches (an enum member is only meaningful once the value
    is already known to be of the field's own declared type) -- raises
    with `violated_declaration: enum`, `declared_type` only (D-3 (4):
    "`observed_type` は載せない ... 型不一致と誤読される" -- the value's
    own type was never what this violation is about).
    """
    if declared_type is None or declared_type == "json":
        return
    # M-5 precedent (`backend_postgres._validate_value_domain`): SQL NULL
    # is valid for any column regardless of its declared type -- this
    # foundation defines no NOT NULL constraint anywhere
    # (`migrations/0003_provision_application.sql`), so a value that
    # normalized to `None` must never be rejected here, for any declared
    # type, UNLESS this field's own constraints declare `nullable: false`
    # (Phase 9 WP-3a, design D-2 (2)/(3)).
    if value is None:
        if constraints is not None and constraints.get("nullable") is False:
            raise ValidationError(
                f"null is not accepted by field declared type {declared_type!r} (nullable: false)",
                details={"violated_declaration": "nullable", "declared_type": declared_type, "observed_type": "null"},
            )
        return
    if declared_type in _ENUM_ELIGIBLE_TYPES:
        ok = enum_member_matches_type(value, declared_type)
    elif declared_type == "object":
        ok = isinstance(value, dict)
    elif declared_type == "array":
        ok = isinstance(value, list)
    else:
        # Unreachable in practice: `declared_type` reaching this point is
        # always a member of `CONTRACT_TYPES` (the registry never holds
        # anything else, `_FIELD_TYPE_VOCABULARY`/`CONTRACT_TYPES` are
        # validated at schema-operation time) -- never a `pragma: no
        # cover` removal, matching this module's own pre-existing
        # defensive style. WP-3e rework T1 (追補 L-1): "免除は layer_rule
        # の backend 層のみ" leaves this choke-point site no exemption
        # either, even though it is unreachable -- best-effort
        # `request_schema` (no closer 11-word member names an
        # unrecognized REGISTRY entry, as opposed to a value the request
        # itself sent; no `field`, this function's own fixed 3-argument
        # signature has no request-relative path of its own, D-2 (3)).
        raise ValidationError(
            f"unknown declared field type {declared_type!r}",
            details=violation("request_schema"),
        )
    if not ok:
        # Phase 9 WP-3e (design D-3 (2)/(4), V-1/V-2): the primary
        # `field_type` choke point -- `violated_declaration: "field_type"`
        # requires BOTH `declared_type` and `observed_type` (the 3-branch
        # rule's first branch). `cell.py::_prepare_values`'s own catch
        # clause (design D-3 (2)) fills in `details["field"]` with this
        # value's own request-relative path once it re-raises -- this
        # choke point itself has no path context (`check_declared_value`'s
        # own fixed 3-argument signature, D-2 (3)).
        raise ValidationError(
            f"value does not match the declared field type {declared_type!r}",
            details={
                "violated_declaration": "field_type",
                "declared_type": declared_type,
                "observed_type": json_type_name(value),
            },
        )
    if constraints is not None:
        allowed = constraints.get("enum")
        if allowed is not None and value not in allowed:
            raise ValidationError(
                f"value is not a member of the declared enum for field type {declared_type!r}",
                details={"violated_declaration": "enum", "declared_type": declared_type},
            )


class _ConstraintDeclarationError(Exception):
    """WP-3a rework 2 (監督裁定 m-1, 2026-09-07 -- isomorphism pairing
    added by the supervisor's own pair-closing commit, work order §4 の
    12 / §6 訂正註 10): internal-only signal `validate_enum_declaration`
    below raises when an `enum` declaration is itself invalid -- never
    surfaced outside this module. `cell.py`'s own
    `_validate_enum_declaration_with_path` catches this at every one of
    `validate_enum_declaration`'s 3 call sites and re-raises `errors.
    ValidationError` with the `details` shape (`field` as the request-
    relative PATH, `violated_declaration: "constraint_declaration"`,
    `declared_type`) that only the CALL SITE -- never this shared
    validator -- knows how to compose, mirroring r2db-api's own
    `structured._ConstraintDeclarationError`/`_fail_constraint_
    declaration` split (same reasoning, independently arrived at)."""


def validate_enum_declaration(enum_values: Any, declared_type: str | None) -> tuple[Any, ...]:
    """Phase 9 WP-3a (design D-2 (2), contract `SchemaOperationRequest.
    field_constraints.description`): validates an `enum` value carried on
    `create_entity`'s `field_constraints`, `add_field`, or `alter_field`
    BEFORE it is ever written to a backend's own constraint registry --
    "an `enum` on an `object`/`array`/`json` field, an empty or
    duplicated `enum`, [or] an `enum` member outside the field's declared
    type ... fails `VALIDATION_FAILED`; none of them is silently
    ignored." Returns the validated members as a tuple, in the order
    declared (round-trip fidelity for the constraint registry entry).

    WP-3a rework 2 (監督裁定 m-1, 2026-09-07): this function's own
    fixed two-argument signature (`enum_values`, `declared_type` --
    m-3, shared with r2db-api's own isomorphism-tested counterpart) has
    no way to know the REQUEST-relative path a violation is attributable
    to (`field_constraints/<field>/enum` from `create_collection`'s own
    `field_constraints`, or the bare `enum` top-level key from `add_
    field`/`alter_field` -- three different callers, three different
    paths, for the identical malformed declaration) -- so it raises
    `_ConstraintDeclarationError` (never `errors.ValidationError`
    directly -- see that class' own docstring) for each of the three
    checks below; `cell.py`'s own `_validate_enum_declaration_with_path`
    wraps every call site and attaches the actual `details` shape (`{"
    violated_declaration": "constraint_declaration", "field": <path>,
    "declared_type": declared_type}` -- errors.details_vocabulary's own
    11th vocabulary word, already part of the published contract) there
    instead.
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
