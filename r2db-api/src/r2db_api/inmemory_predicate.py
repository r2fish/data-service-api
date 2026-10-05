"""r2db in-memory predicate evaluation: `matches` wildcard compilation,
row-value text rendering, and the `Predicate` vs. row comparison (ST3).

This is a pure leaf: `_wildcard_pattern` compiles a `matches` pattern to a
regex from its own literal text alone, `_predicate_text` renders an
already-typed Python value into the same text form PostgreSQL's own
`::text`/`#>> '{}'` output uses (via `pg_text_format`), and `_matches`
compares one already-fetched row against one already-validated
`Predicate` -- none of the three opens a connection, reads a catalog, or
consults any request/limits/principal state. The choke points that decide
which rows and which predicates reach this leaf (`ApplicationCell.query`
and `_transact_locked`, in `structured.py`) remain in their own module.
"""
from __future__ import annotations

import re
from typing import Any

from .errors import fail, violation
from .pg_text_format import _float8out_text, _jsonb_scalar_text, _jsonb_text


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
                fail("VALIDATION_FAILED", "matches pattern must not end with an unescaped backslash.", details=violation("request_schema"))
            continue
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("(?s)\\A" + "".join(out) + "\\Z")


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
    scientific-notation expansion) decides which rule a TOP-LEVEL float or
    int uses: `float8out` only when this field is itself a typed `"number"`
    column (matching `PostgresCell._text_expression`'s plain `::text`
    cast); jsonb's own numeric rules for everything else, including an
    untyped top-level column. An int in a typed `"number"` column is a
    `double precision` value like any float there, so it takes `float8out`
    too (`10**15` is `"1e+15"`); an untyped int keeps its own digits. A top-level dict/list
    (`_jsonb_text`) and any NESTED position inside one always use jsonb's own rules regardless of
    `field_type` -- nesting only exists inside jsonb storage, which has no
    "typed number" concept at all beneath its own root.

    History: CH-1132
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return _jsonb_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and field_type == "number":
        return _float8out_text(float(value))
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
