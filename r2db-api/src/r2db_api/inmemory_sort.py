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

from decimal import Decimal
from typing import Any

# PostgreSQL's own jsonb cross-type ordering (ascending: String < Number <
# Boolean < Array < Object), used by `_sort_key` below for an untyped
# (JSONB-equivalent) column whose stored values happen to differ in JSON
# type (WP-2 review M-6). Typed columns never exercise more than one of
# these ranks, since R-7 already guarantees a uniform type there.
_JSON_TYPE_RANK = {"string": 0, "number": 1, "boolean": 2, "array": 3, "object": 4}


def _numeric_key(value: int | float) -> Decimal:
    """The number a real PostgreSQL server actually receives and compares,
    for an `int`/`float` value (never `bool`, which branches before this is
    called): `psycopg`'s `Jsonb` binds it through `json.dumps`, so a real
    server never sees the Python `float`'s own binary value, only
    `repr(value)`'s decimal text (`json.dumps`'s own shortest round-
    tripping form) -- comparing that same text as a `Decimal` matches a
    real server for a value near/beyond 2**53, where a `float`'s decimal
    text and a same-sized `int`'s own decimal text can round to different
    values. An `int` already has no such representation gap, so it is
    read as a `Decimal` directly. `Decimal(1) == Decimal("1.0")` and
    `Decimal("-0.0") == Decimal(0)` keep `_sort_key`/`_jsonb_value_key`'s
    existing numeric equivalences.
    """
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def _sort_key(value: Any) -> tuple[Any, ...]:
    """A total ordering key matching PostgreSQL's own defaults (WP-2 review
    M-6, and for a list/dict value's own internal structure, a real
    PostgreSQL server's measured `jsonb` comparison): a `NULL` sorts as if
    larger than any non-null value (`NULLS LAST` for ascending, `NULLS
    FIRST` for descending -- both fall out of giving it the single highest
    rank here and reusing `_sort_rows`'s existing per-field
    `reverse=(direction == "desc")`, with no direction-specific branch
    needed in this function). Non-null values are additionally grouped by
    jsonb type rank first, so two rows whose values for the same untyped
    (JSONB-equivalent) column differ in JSON type never reach a native `<`
    comparison between incompatible Python types.

    A list or dict value's own internal order (once two values share the
    array/object rank) matches PostgreSQL's own `jsonb` comparison: an
    array compares by element count first, then element by element; an
    object compares by pair count first, then by its own storage-order
    pairs (shortest key first, ties broken by key byte order), each pair
    comparing its key before its value -- so two objects holding the same
    pairs in a different insertion order compare equal. A nested value's
    own type ranks Null < String < Number < Boolean < Array < Object
    (`_jsonb_value_key` below); this differs from a *top-level* `None`,
    which this function gives the single highest rank instead, matching
    SQL `NULL` rather than a nested JSON `null`. A top-level empty array is
    the one exception to sharing the array rank with other arrays: it
    sorts below every non-null scalar, matching a real server's measured
    output (`[] < "x" < 0 < ... < [0] < {} < ...`).

    This array/object ordering is checked leaf-only, against values a real
    PostgreSQL 16 server has measured, by `test_inmemory_sort_jsonb_
    order.py`'s 4 tests, and against a real PostgreSQL 16 server directly
    (for an untyped, an `array`-typed, and an `object`-typed column, plus
    the keyset cursor built on the same key) by `test_postgres.py`'s 4
    `test_parity_order_by_jsonb_*` tests -- 8 tests total, all passing.

    A number (top-level or nested) compares as the `Decimal` of the same
    JSON text a real server actually receives through `psycopg`'s
    `Jsonb` binding (`repr(value)` for a `float`, matching `json.dumps`'s
    own shortest round-tripping form; the value itself for an `int`), not
    Python's own binary float comparison, which a real server can
    disagree with near/beyond 2**53.

    String comparison (top-level or nested) is Python's own codepoint
    order; application databases are provisioned with `LC_COLLATE 'C'`
    (`0003_provision_application.sql`), so a real PostgreSQL server's own
    string ordering matches this key byte-for-byte, including for a typed
    `string` column, an untyped (jsonb) column, keyset-cursor paging, and
    `gt`/`lt` comparisons over strings mixing case and non-ASCII
    characters -- checked against a real PostgreSQL server by `test_
    postgres.py`'s `test_parity_string_collation_order_by_string_column`,
    `test_parity_string_collation_order_by_untyped_column`, `test_parity_
    string_collation_keyset_cursor_walk`, and `test_parity_string_
    collation_where_gt_lt` (11 passed together with this module's own
    pre-existing jsonb-order tests, `-k "collation or parity_order"`).
    """
    if value is None:
        return (1, 0, "")
    if isinstance(value, bool):
        return (0, _JSON_TYPE_RANK["boolean"], int(value))
    if isinstance(value, (int, float)):
        return (0, _JSON_TYPE_RANK["number"], _numeric_key(value))
    if isinstance(value, str):
        return (0, _JSON_TYPE_RANK["string"], value)
    if isinstance(value, list):
        if not value:
            # A top-level empty array is, uniquely among non-null values,
            # smaller than every scalar (measured against a real server:
            # `[] < "x" < 0 < ... < [0] < {} < ...`), so it cannot share
            # `_JSON_TYPE_RANK["array"]`'s rank with a non-empty array.
            return (0, -1)
        return (0, _JSON_TYPE_RANK["array"], len(value), tuple(_jsonb_value_key(item) for item in value))
    if isinstance(value, dict):
        return (0, _JSON_TYPE_RANK["object"], len(value), _dict_pair_key(value))
    return (0, _JSON_TYPE_RANK["string"], str(value))  # pragma: no cover - values are always JSON-shaped


def _dict_pair_key(value: dict[str, Any]) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    """The comparison key for a jsonb object's own pairs: `sorted` puts the
    pairs in the object's own storage order (shortest key first, then byte
    order for a tie -- jsonb's own key layout), and the resulting tuple of
    `(key, value_key)` pairs then compares key-first-then-value at each
    position, which is what makes two objects holding the same pairs in a
    different insertion order compare equal.
    """
    ordered = sorted(value.items(), key=lambda pair: (len(pair[0].encode("utf-8")), pair[0].encode("utf-8")))
    return tuple((key, _jsonb_value_key(item)) for key, item in ordered)


def _jsonb_value_key(value: Any) -> tuple[Any, ...]:
    """The ordering key for a value nested inside a jsonb array/object
    (used by `_sort_key`'s own list/dict branches above): a JSON `null`
    ranks below every other type here (unlike a *top-level* `None`, which
    `_sort_key` gives the single highest rank -- a nested `null` and a
    top-level SQL `NULL` are different things), and the remaining types
    keep `_JSON_TYPE_RANK`'s own String < Number < Boolean < Array <
    Object order (offset by one to make room for `null`'s rank 0).
    """
    if value is None:
        return (0,)
    if isinstance(value, bool):
        return (_JSON_TYPE_RANK["boolean"] + 1, int(value))
    if isinstance(value, (int, float)):
        return (_JSON_TYPE_RANK["number"] + 1, _numeric_key(value))
    if isinstance(value, str):
        return (_JSON_TYPE_RANK["string"] + 1, value)
    if isinstance(value, list):
        return (_JSON_TYPE_RANK["array"] + 1, len(value), tuple(_jsonb_value_key(item) for item in value))
    if isinstance(value, dict):
        return (_JSON_TYPE_RANK["object"] + 1, len(value), _dict_pair_key(value))
    return (_JSON_TYPE_RANK["string"] + 1, str(value))  # pragma: no cover - values are always JSON-shaped


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
