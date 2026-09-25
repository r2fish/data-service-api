"""r2db per-value declared-type/domain validation and predicate-value
checks: `_check_type`'s type/domain/NUL/enum gate, `_declared_type_label`'s
detail-vocabulary translation, `_validate_wildcard_pattern`'s `matches`
grammar check, `_validate_predicate_types`'s up-front predicate-value pass,
and the `_TEXT_ONLY_OPERATORS` set only `_validate_predicate_types` reads
(ST6).

This is a pure leaf: every function is a total, deterministic check over
its own explicitly-passed arguments (a value, a declared type, an
already-bound `FieldConstraints`/`Predicate` list), consulting no
connection, catalog, clock, or global state. The choke points that decide
*which* values reach this leaf (`ApplicationCell._apply`/`query`/
`_fail_constraint_declaration`, in `structured.py` (now in `schema_binding.py`)) remain in their own
module.
"""
from __future__ import annotations

import math
from typing import Any

from .errors import fail, observed_type_of, violation
from .value_nul import _contains_nul


def _contains_lone_surrogate(value: str) -> bool:
    """Whether `value` holds a UTF-16 surrogate code point (U+D800-DFFF)
    -- always unpaired at the Python `str` level, since a JSON `\\uD83D\\uDE00`-
    style escaped pair is already combined into one supplementary-plane
    character by the JSON decoder before this function ever sees it; a
    lone one only ever reaches here from a request that spelled a single,
    unmatched `\\uD800`-range escape. `psycopg` cannot encode it (a client-
    supplied-value bug, the same class `_check_type` already refuses for
    an out-of-range integer or a NUL byte), and letting it through to a
    driver-level `UnicodeEncodeError` would surface as `SERVICE_UNAVAILABLE`
    instead of `VALIDATION_FAILED`."""
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)


# Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication, docs/design/
# R2DB_CCR13_STORAGE_V1.md): `contains` is literal substring containment
# (no wildcard interpretation) and `matches` is a case-sensitive wildcard
# pattern (`%`/`_`/`\`). Both operators' *value* is always a plain string,
# independent of the target field's own declared type (a typed non-string
# column is matched against its text representation) -- checked once here,
# ahead of the per-column `_check_type` declared-type check below, since
# this constraint is about the operator, not the column.
_TEXT_ONLY_OPERATORS = {"contains", "matches"}


# --- value type validation (R-7) -------------------------------------------

# R-7 addendum (WP-3 review blocker-2): PostgreSQL's `bigint` range. A JSON
# integer outside this range passes every existing type check (Python `int`
# has no fixed width) but PostgreSQL rejects it at execution time with a
# non-deterministic-looking `numeric_value_out_of_range` -- a decisive
# client bug that must not surface as a retryable-looking server failure.
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _declared_type_label(field_type: str | None) -> str:
    """The D-3 `declared_type` detail value for a field's own internal
    declared type -- `None` (untyped/JSONB-equivalent) reports as `json`,
    the same translation `catalog()`'s own `field_types` output already
    uses (Phase 6 WP-2, decision (ii))."""
    return field_type or "json"


def _check_type(value: Any, field_type: str | None, field_name: str, *, constraints: "FieldConstraints | None" = None) -> None:
    """Validate `value` against a declared column type before it is bound.

    `field_type` of `None` means the field is untyped (JSONB-equivalent):
    any JSON value is accepted, exactly like before typed columns existed.
    `null` is always accepted regardless of declared type (NOT NULL is out
    of scope for this contract version, UNLESS `constraints` below says
    otherwise). A mismatch fails `VALIDATION_FAILED` naming only the field
    -- never the value itself (`errors.disclosure`).

    R-7 addendum (WP-3 review blocker-2): beyond the JSON-type check, a
    value's own *domain* is validated too -- an `integer` outside signed
    64-bit range, or a NUL byte anywhere inside a `string`/`object`/`array`/
    untyped value -- both of which `_check_type` alone (a bare `isinstance`
    check) would let through, but PostgreSQL's own storage cannot. Same
    error code/disclosure shape as the type check itself.

    Contract 1.7.0 (D-2, WP-2a): `constraints`, a keyword-only, `None`-
    default argument (addendum R-b: this file's choke point) -- the field's
    declared `enum`/`nullable`, or `None` when this call site never checks
    constraints at all (the 2 predicate-value call sites, addendum 2 S-k:
    `enum`/`nullable` bind writes only, never a query predicate, D-2 (2)'s
    own negative disclosure). `None` here behaves exactly like the pre-
    1.7.0 default `FieldConstraints()` would (nullable, no enum) -- the 6
    write call sites (insert/update/upsert x 2 backends) always pass the
    field's real constraints (a lookup miss there also yields `None`,
    naturally the same default). Checked in the WP-2a/D-3 four-key form:
    `field` + `violated_declaration` always, `declared_type` (the field's
    own type, `field_type` translated through `_declared_type_label`)
    alongside it for `nullable` (`observed_type: "null"`), and `declared_
    type` alone (never `observed_type`, D-3 (4): a `enum` mismatch is not
    a type mismatch) for `enum`.
    """
    if value is None:
        if constraints is not None and not constraints.nullable:
            fail(
                "VALIDATION_FAILED",
                "Value must not be null for a field declared nullable: false.",
                details={"field": field_name, "violated_declaration": "nullable", "declared_type": _declared_type_label(field_type), "observed_type": "null"},
            )
        return
    if field_type is None:
        if _contains_nul(value):
            fail("VALIDATION_FAILED", "Value must not contain a NUL character.", details=violation("request_schema", field=field_name))
        # Monitor ruling B-1 (rulings-wp2a-review.md): an untyped/JSONB-
        # equivalent field can NEVER declare an `enum` at all (`validate_
        # enum_declaration`'s own `_ENUM_ELIGIBLE_TYPES` gate above (in `structured.py`) already
        # refuses the declaration itself) -- so `constraints.enum` is
        # never non-`None` here, and this branch never needs its own enum
        # check (removed: the pre-rework "untyped field can still declare
        # enum" reasoning this comment used to carry was the very type-
        # inference bug B-1 reports).
        return
    if field_type == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
        if ok and not (_INT64_MIN <= value <= _INT64_MAX):
            # Contract 1.7.0 (D-3, WP-2e): out-of-range is a `field_type`
            # violation like any other -- the value's JSON type matches
            # (`observed_type` == `declared_type` == "integer"), but the
            # field's own declared type does not admit this value's
            # magnitude. `errors.details_vocabulary` has no separate word
            # for "domain"/"range"; this choke point's own docstring
            # already treats range/NUL-byte violations as the same error
            # code/disclosure shape as the type check itself.
            fail(
                "VALIDATION_FAILED", "Value is out of range for the field's declared type.",
                details=violation("field_type", field=field_name, declared_type=_declared_type_label(field_type), observed_type=observed_type_of(value)),
            )
    elif field_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if ok:
            try:
                representable = math.isfinite(float(value))
            except (OverflowError, ValueError):
                representable = False
            if not representable:
                # design PHASE11_KEYSET_PAGING_V1 D-3 (4a) (shared choke
                # point, so `where` and `page/cursor` refuse alike): a
                # magnitude/inf/nan PostgreSQL's own `float8` cannot hold
                # would otherwise reach the driver as a raw bind value and
                # come back as a `NumericValueOutOfRange`, surfacing as
                # `SERVICE_UNAVAILABLE` instead of this refusal.
                fail("VALIDATION_FAILED", "Value is out of range for the field's declared type.", details=violation("request_schema", field=field_name))
    elif field_type == "boolean":
        ok = isinstance(value, bool)
    elif field_type == "string":
        ok = isinstance(value, str)
        if ok and _contains_lone_surrogate(value):
            fail("VALIDATION_FAILED", "Value contains an unpaired UTF-16 surrogate.", details=violation("request_schema", field=field_name))
    elif field_type == "object":
        ok = isinstance(value, dict)
    elif field_type == "array":
        ok = isinstance(value, list)
    else:  # pragma: no cover - field_type is always one of FIELD_TYPES or None
        ok = True
    if not ok:
        # Contract 1.7.0 (D-3, WP-2e): the plain JSON-type mismatch --
        # `violated_declaration: field_type`, both `declared_type` (the
        # field's own declared type) and `observed_type` (the JSON type of
        # the value actually received) required (D-3 (4)'s first branch).
        fail(
            "VALIDATION_FAILED", "Value does not match the field's declared type.",
            details=violation("field_type", field=field_name, declared_type=_declared_type_label(field_type), observed_type=observed_type_of(value)),
        )
    if field_type in ("string", "object", "array") and _contains_nul(value):
        fail(
            "VALIDATION_FAILED", "Value must not contain a NUL character.",
            details=violation("field_type", field=field_name, declared_type=_declared_type_label(field_type), observed_type=observed_type_of(value)),
        )
    # Contract 1.7.0 (D-2, WP-2a): checked LAST, only once `value` has
    # already passed the basic type/domain/NUL checks above -- a value of
    # the WRONG type is `violated_declaration: field_type` (the existing,
    # unmodified branch above), never misreported as an `enum` violation.
    if constraints is not None and constraints.enum is not None and value not in constraints.enum:
        fail(
            "VALIDATION_FAILED",
            "Value is not a member of the field's declared enum.",
            details={"field": field_name, "violated_declaration": "enum", "declared_type": _declared_type_label(field_type)},
        )


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
        fail("VALIDATION_FAILED", "matches pattern must not end with an unescaped backslash.", details=violation("request_schema", field=field_name))


def _validate_predicate_types(where: list["Predicate"], field_types: dict[str, str | None], *, path_prefix: str = "where") -> None:
    """Type-check every predicate's value up front, independent of which
    rows (if any) it will end up matching (R-7, corrigendum M-9: type
    validation happens before target-row search/precondition resolution --
    see the call sites in `ApplicationCell.query`/`_apply`).

    `path_prefix` (WP-2e rework, rulings R-5/M-4): the identical request-
    internal path `validate_predicates` places this same `where` list at
    (`"where"` for a top-level query, `f"operations/{i}/where"` for a
    mutation's own `where`) -- every VALUE-position denial below names
    `<path_prefix>/<i>/value` (or `.../value/<j>` for one `in` element),
    never the bare field name (`predicate.field` names a column, not a
    request-internal path -- `errors.details_vocabulary`'s `field` is
    defined as the latter only)."""
    for i, predicate in enumerate(where):
        base_path = f"{path_prefix}/{i}/value"
        if predicate.operator in _TEXT_ONLY_OPERATORS:
            # Q-2: the operator's own value type is fixed (string), never
            # the target column's declared type -- a typed non-string
            # column is still matched via its text representation, so the
            # column's own declared type is irrelevant to this check.
            if not isinstance(predicate.value, str):
                fail("VALIDATION_FAILED", "This operator's value must be a string.", details=violation("field_type", field=base_path, declared_type="string", observed_type=observed_type_of(predicate.value)))
            if _contains_nul(predicate.value):
                fail("VALIDATION_FAILED", "This operator's value must not contain a NUL character.", details=violation("request_schema", field=base_path))
            if predicate.operator == "matches":
                _validate_wildcard_pattern(predicate.value, base_path)
            continue
        if predicate.operator in ("eq", "ne") and predicate.value is None:
            # WP-3 confirmation review N-3: `= NULL`/`<> NULL` is always
            # UNKNOWN in SQL -- silently, permanently matching zero rows,
            # never what a caller means. `is_null` exists precisely for
            # this comparison; refusing here is more diagnostic to an AI
            # agent client than quietly returning an empty result forever.
            # R-4: `nullable` requires BOTH `declared_type` and
            # `observed_type` (D-3 (4)'s first branch, contract text
            # `declared_type` is "required where violated_declaration is
            # field_type or nullable").
            fail("VALIDATION_FAILED", "eq/ne do not accept a null value; use is_null instead.", details=violation("nullable", field=base_path, declared_type=_declared_type_label(field_types.get(predicate.field)), observed_type="null"))
        declared_type = field_types.get(predicate.field)
        if predicate.operator == "in":
            # M-3 (rulings addendum 2): an empty (or non-list) `in` value
            # is refused here, at the shared choke point -- both cells now
            # agree (the in-memory side used to accept it silently; the
            # Postgres side's own bare `fail()` this mirrors is replaced
            # by this same call, R-2).
            if not isinstance(predicate.value, list) or not predicate.value:
                fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.", details=violation("request_schema", field=base_path))
            for j, item in enumerate(predicate.value):
                _check_type(item, declared_type, f"{base_path}/{j}")
        elif predicate.operator != "is_null":
            _check_type(predicate.value, declared_type, base_path)
