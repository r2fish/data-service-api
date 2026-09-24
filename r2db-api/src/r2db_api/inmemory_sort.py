"""r2db in-memory `order_by` sort key, row-sorting, and keyset cursor
position comparison (ST2; keyset paging, design D-3 (5)).

This is a pure leaf: `_sort_key` is a total, deterministic ordering key
over an already-typed Python value, `_sort_rows` is a total,
deterministic multi-field stable sort over already-fetched rows using
that key, and `_after_page_cursor` is a total, deterministic dictionary
comparison (using that same key) between an already-sorted row's own
ordering values and a decoded cursor's own ordering values. None of the
three opens a connection, reads a catalog, nor consults any
request/limits/principal state; the choke point that decides which rows
and which `order_by` spec reach this leaf (`ApplicationCell.query`,
in `structured.py`) remains in its own module.
"""
from __future__ import annotations

import json
from typing import Any

# PostgreSQL's own jsonb cross-type ordering (ascending: String < Number <
# Boolean < Array < Object), used by `_sort_key` below for an untyped
# (JSONB-equivalent) column whose stored values happen to differ in JSON
# type (WP-2 review M-6). Typed columns never exercise more than one of
# these ranks, since R-7 already guarantees a uniform type there.
_JSON_TYPE_RANK = {"string": 0, "number": 1, "boolean": 2, "array": 3, "object": 4}


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


def _after_page_cursor(row_values: list[Any], cursor_values: list[Any], spec: list[tuple[str, str]]) -> bool:
    """Whether an already-sorted row sits strictly after a decoded page
    cursor's own position, in the order `spec` defines (design D-3 (5)):
    a dictionary comparison of `_sort_key(row_values[i])` against
    `_sort_key(cursor_values[i])`, term by term -- the first term that
    differs decides the row's position (`>` for `asc`, `<` for `desc`,
    matching `_sort_key`'s own NULL-as-largest total order); a row whose
    values tie the cursor on every term is the cursor's own row and is
    not "after" it. `row_values`/`cursor_values` are index-aligned with
    `spec` (tie-break included).
    """
    for (_field_name, direction), row_value, cursor_value in zip(spec, row_values, cursor_values):
        row_key = _sort_key(row_value)
        cursor_key = _sort_key(cursor_value)
        if row_key == cursor_key:
            continue
        if direction == "asc":
            return row_key > cursor_key
        return row_key < cursor_key
    return False
