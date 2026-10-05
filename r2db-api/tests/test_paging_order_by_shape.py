"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-5a..C1-5d): `paging._resolve_order_by` and
`paging.decode_and_check_page_cursor` called directly, for four refusals
and one rule no earlier test fixed -- an `order_by` entry carrying a key
other than `field`/`direction`, a `direction` outside `asc`/`desc`, the
`id` tie-break appended only when `order_by` does not already name `id`,
and a boolean ordering value inside a page cursor over an `integer`
column (`_check_type` does not admit a `bool` as an integer).

Every refusal is asserted against its literal code and details; each
positive control returns a non-empty result.

Peer difference, pinned as the current value and not a contract claim
(filed as R-124, work order section 5): this peer reports an invalid
`direction` at `order_by/direction` and a malformed entry at `order_by`,
where `MitateDB-api`'s cell layer reports `order_by/<i>/direction` and
`order_by/<i>`.
"""
from __future__ import annotations

import pytest

from r2db_api.errors import FoundationError
from r2db_api.paging import _resolve_order_by, decode_and_check_page_cursor, encode_page_cursor

KNOWN = {"id", "f0"}


def test_order_by_entry_with_an_extra_key_is_refused() -> None:
    """C1-5a: `{"field": "f0", "x": 1}` -> `VALIDATION_FAILED` /
    `request_schema` / `order_by`; the same entry without the extra key is
    accepted."""
    with pytest.raises(FoundationError) as excinfo:
        _resolve_order_by([{"field": "f0", "x": 1}], KNOWN)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "request_schema", "field": "order_by"}

    assert _resolve_order_by([{"field": "f0"}], KNOWN) == [("f0", "asc"), ("id", "asc")]


def test_order_by_direction_outside_asc_and_desc_is_refused() -> None:
    """C1-5b: `"sideways"` -> `VALIDATION_FAILED`, details exactly the
    `enum` form naming `order_by/direction` with `declared_type: string`;
    `asc` and `desc` are accepted."""
    with pytest.raises(FoundationError) as excinfo:
        _resolve_order_by([{"field": "f0", "direction": "sideways"}], KNOWN)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "enum", "field": "order_by/direction", "declared_type": "string"}

    assert _resolve_order_by([{"field": "f0", "direction": "asc"}], KNOWN) == [("f0", "asc"), ("id", "asc")]
    assert _resolve_order_by([{"field": "f0", "direction": "desc"}], KNOWN) == [("f0", "desc"), ("id", "asc")]


def test_id_tie_break_is_appended_only_when_order_by_does_not_name_id() -> None:
    """C1-5c: an `order_by` that names `id` keeps its own direction and
    gains no second `id`; one that does not name it gains `("id", "asc")`
    last."""
    assert _resolve_order_by([{"field": "id", "direction": "desc"}], KNOWN) == [("id", "desc")]
    assert _resolve_order_by([{"field": "f0"}, {"field": "id"}], KNOWN) == [("f0", "asc"), ("id", "asc")]
    assert _resolve_order_by([{"field": "f0", "direction": "desc"}], KNOWN) == [("f0", "desc"), ("id", "asc")]
    assert _resolve_order_by(None, KNOWN) == [("id", "asc")]


def test_page_cursor_with_a_boolean_ordering_value_over_an_integer_column_is_refused() -> None:
    """C1-5d: a cursor carrying `[True, 1]` against an `integer` first
    column is refused as `VALIDATION_FAILED` / `request_schema` /
    `page/cursor` (a `bool` is not an integer); `[5, 1]` decodes."""
    spec = [("n", "asc"), ("id", "asc")]
    field_types = {"n": "integer", "id": "integer"}
    binding = "binding-r39"

    with pytest.raises(FoundationError) as excinfo:
        decode_and_check_page_cursor(encode_page_cursor([True, 1], binding), binding, spec, field_types)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {"violated_declaration": "request_schema", "field": "page/cursor"}

    assert decode_and_check_page_cursor(encode_page_cursor([5, 1], binding), binding, spec, field_types) == [5, 1]
