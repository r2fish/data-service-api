"""MitateDB field_constraints resolution (CE3).

This is a pure leaf: `_validate_enum_declaration_with_path` and
`_resolve_field_constraints` are total, deterministic checks over
already-passed arguments (an `enum`/`nullable` declaration, a field's own
declared type, `max_enum_members`), consulting no connection, catalog,
clock, or global state. The choke points that decide WHEN these run and
what the rest of a request does with the result (`ApplicationCell.
create_collection`/`add_field`/`alter_field`, in `cell.py`) remain in
their own module.
"""
from __future__ import annotations

from .errors import ResourceLimitError, ValidationError
from .field_types import _ConstraintDeclarationError, json_type_name, validate_enum_declaration


def _validate_enum_declaration_with_path(enum_values, declared_type, field_path):
    """WP-3a rework 2 (監督裁定 m-1, 2026-09-07): wraps `field_types.
    validate_enum_declaration` (whose own fixed two-argument signature,
    monopolized by m-3's isomorphism-tested naming, has no way to carry a
    request path) and attaches this WP's own `constraint_declaration`
    `details` shape to whatever `errors.ValidationError` it raises --
    covers all three of the "declaration is itself invalid" cases m-1
    names: an `enum` on a field whose declared type admits none, an
    empty or duplicated `enum`, and a member outside the field's own
    declared type. `field_path` is the request-relative position this
    violation is attributable to (design D-3 (2)) -- `field_constraints/
    <field>/enum` from `create_collection`'s own `field_constraints`
    (`_resolve_field_constraints` below), or the bare `enum` top-level
    key from `add_field`/`alter_field` (each redeclares exactly ONE
    field's own constraints, so there is no per-field path to build).
    `declared_type` is always known and included (`observed_type` is
    deliberately never set -- m-1: "型不一致と誤読される" applies here
    too, this is a declaration defect, not a value's own type).

    Phase 9 pair-closing isomorphism alignment (work order §4 の 12 /
    §6 訂正註 10): `validate_enum_declaration` itself now raises the
    internal-only `field_types._ConstraintDeclarationError` (never
    `errors.ValidationError` directly -- mirrors r2db-api's own
    `structured._ConstraintDeclarationError` split), so this wrapper is
    the one place that turns it into the public `errors.ValidationError`
    with this WP's own `details` shape. Same alignment also changed the
    shared function's own return shape (a tuple, round-trip fidelity,
    matching r2db-api's own `FieldConstraints.enum` field) -- `list(...)`
    here converts it back to this peer's own pre-existing `enum` shape
    (a plain list, every downstream caller/backend on this peer's own
    side already assumes) so no caller past THIS direct one needs to
    change."""
    try:
        return list(validate_enum_declaration(enum_values, declared_type))
    except _ConstraintDeclarationError as exc:
        raise ValidationError(
            str(exc),
            details={
                "violated_declaration": "constraint_declaration",
                "field": field_path,
                "declared_type": declared_type,
            },
        ) from exc


def _resolve_field_constraints(fields, declared_types, field_constraints, *, max_enum_members):
    """Phase 9 WP-3a (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/(2)/
    (7)): resolves a request's PARTIAL `field_constraints` (or `None`)
    into a TOTAL `{field: {"nullable": bool, "enum": [...]}}` map over
    `fields` -- the same "request is partial, resolved value is total"
    shape `create_collection`'s own `field_types` backfill already
    performs. `enum` members are checked against each field's own
    declared type (`field_types.validate_enum_declaration`) and counted
    against `max_enum_members` (`limits.enum_members`, §5 U-1 = (β)) --
    both BEFORE anything is created (design D-2 (7): "enum_members を
    超える enum 宣言が、何も作られる前に LIMIT_EXCEEDED...で拒否される").
    Callers have already confirmed every `field_constraints` key names a
    real member of `fields`."""
    resolved = {}
    for field in fields:
        declared = dict((field_constraints or {}).get(field) or {})
        # Code review §2 E / 監督裁定 E (2026-09-07): contract
        # `SchemaOperationRequest.field_constraints`'s own per-field
        # entry is `additionalProperties: false` over exactly `enum`/
        # `nullable` -- an unrecognized key here (a misspelling, e.g.
        # `"enumm"`) used to be silently dropped rather than refused,
        # the one shape this contract's own text calls out by name
        # ("none of them is silently ignored"). `field` names the
        # request position this violation is attributable to (design
        # D-3 (2)): `field_constraints/<field>/<unknown key>`.
        unknown_keys = set(declared) - {"nullable", "enum"}
        if unknown_keys:
            bad_key = sorted(unknown_keys)[0]
            raise ValidationError(
                f"field_constraints.{field} carries an unrecognized key {bad_key!r}",
                details={
                    "violated_declaration": "request_schema",
                    "field": f"field_constraints/{field}/{bad_key}",
                },
            )
        nullable = declared.get("nullable", True)
        if not isinstance(nullable, bool):
            # WP-3a closure (監督裁定 2026-09-07, audit §3 G3): D-3 details
            # for a request-shape violation about a VALUE's own type --
            # `field` is the request-relative path (design D-3 (2)),
            # `declared_type`/`observed_type` included per D-3 (3)'s
            # value-type-violation branch.
            raise ValidationError(
                "field_constraints.nullable must be a boolean",
                details={
                    "violated_declaration": "request_schema",
                    "field": f"field_constraints/{field}/nullable",
                    "declared_type": "boolean",
                    "observed_type": json_type_name(nullable),
                },
            )
        entry = {"nullable": nullable}
        enum_values = declared.get("enum")
        if enum_values is not None:
            validated_enum = _validate_enum_declaration_with_path(
                enum_values, declared_types[field], f"field_constraints/{field}/enum")
            if len(validated_enum) > max_enum_members:
                raise ResourceLimitError("enum member limit exceeded", limit_class="enum_members")
            entry["enum"] = validated_enum
        resolved[field] = entry
    return resolved
