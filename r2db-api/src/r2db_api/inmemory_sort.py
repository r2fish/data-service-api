"""r2db in-memory `order_by` sort key and row-sorting (ST2).

This is a pure leaf: `_sort_key` is a total, deterministic ordering key
over an already-typed Python value, and `_sort_rows` is a total,
deterministic multi-field stable sort over already-fetched rows using
that key. Neither opens a connection, reads a catalog, nor consults any
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
