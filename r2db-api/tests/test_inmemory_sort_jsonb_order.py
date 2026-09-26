"""`_sort_key`'s list/dict branches against PostgreSQL 16.14's own measured
jsonb structural total order (work order appendix A): array comparison is
by element count first then element-by-element, object comparison is by
pair count first then by the object's own storage-order pairs (key, then
value), and nested values rank Null < String < Number < Boolean < Array <
Object. `test_postgres.py`'s `test_parity_order_by_jsonb_*` tests exercise
the same values against a real server; this module is the leaf-only,
PostgreSQL-free half. A9's two multi-byte keys and the two large numbers
near 2**60 near the end of this file are measured against the same real
server (work order section 4 correction notes 1-2), not appendix A itself.
"""
from __future__ import annotations

from r2db_api.inmemory_sort import _sort_key

# Appendix A values, written in the ascending order PostgreSQL 16.14
# returns them in (work order appendix A). `_shuffled` below feeds
# `sorted()` a permutation of each column so the assertion is non-vacuous.
A1 = [[], "x", 0, False, True, [0], {}, {"a": 0}]
A2 = [[None], ["a"], [-1], [0], [1.5], [False], [True], [[]], [{}]]
A3 = [[], [None], ["b"], [3], [9], [10], [True], [[1]], [{"a": 1}], ["a", "b"], ["a", 1], [1, "a"], [1, 2], [1, 2, 3]]
A4 = [[{"a": 1}], [{"a": 2}], [{"b": 0}], [{"a": 1, "b": 1}]]
A5 = [{}, {"a": 1}, {"a": 2}, {"b": 0}, {"b": 1}, {"a": 1, "b": 2}]
A6 = [
    {"a": 1, "b": 2},
    {"a": 1, "bb": 0},
    {"a": 1, "c": 0},
    {"a": 9, "c": 0},
    {"b": 0, "c": 0},
    {"b": 1, "aa": 2},
    {"b": 2, "aa": 1},
    {"c": 0, "ab": 1},
]
A7 = [{"a": None}, {"a": "s"}, {"a": 0}, {"a": True}, {"a": [3]}, {"a": [1, 2]}, {"a": {"x": 1}}]
A8 = [-0.00001, 0.0, 0, 1, 1.0, 1.5, 9, 10, 12345678901234567890, 100000000000000000000]
A9 = [{"a": 1, "é": 2}, {"a": 2, "é": 1}, {"ab": 1, "é": 2}, {"ab": 2, "é": 1}]


def _shuffled(column: list) -> list:
    """A permutation that is never already in ascending order (reversed),
    so a `sorted(..., key=_sort_key)` that happened to be the identity
    function on an already-sorted input could not pass by accident."""
    return list(reversed(column))


def test_inmemory_sort_jsonb_array_order_matches_postgres():
    assert sorted(_shuffled(A3), key=_sort_key) == A3
    assert sorted(_shuffled(A8), key=_sort_key) == A8
    assert _sort_key([3]) < _sort_key([1, 2])
    assert _sort_key([9]) < _sort_key([10])
    assert _sort_key(1) == _sort_key(1.0)
    assert _sort_key(0) == _sort_key(-0.0)
    # Measured against a real server (work order section 4 correction
    # note 1): PostgreSQL reads a float through its own JSON text, not
    # Python's binary float value, so this int/float pair near 2**60
    # orders the opposite way Python's own native comparison would.
    assert _sort_key([1152921504606846990]) < _sort_key([2.0**60])


def test_inmemory_sort_jsonb_object_order_matches_postgres():
    assert sorted(_shuffled(A4), key=_sort_key) == A4
    assert sorted(_shuffled(A5), key=_sort_key) == A5
    assert sorted(_shuffled(A6), key=_sort_key) == A6
    assert _sort_key({"a": 1, "b": 2}) == _sort_key({"b": 2, "a": 1})
    # A9 (work order section 4 correction note 2): a real server's pair
    # storage order is by UTF-8 byte length, not codepoint count -- this
    # column's multi-byte key only ever ties its counterpart pair's key,
    # so the comparison itself stays collation-independent (D-2).
    assert sorted(_shuffled(A9), key=_sort_key) == A9


def test_inmemory_sort_jsonb_nested_type_order_and_null_minimum():
    assert sorted(_shuffled(A2), key=_sort_key) == A2
    assert sorted(_shuffled(A7), key=_sort_key) == A7


def test_inmemory_sort_jsonb_top_level_empty_array_below_scalars():
    assert sorted(_shuffled(A1), key=_sort_key) == A1
    for value in A1:
        assert _sort_key(None) > _sort_key(value)
    # Same real-server measurement as the array test above, for a
    # top-level (rather than nested) int/float pair near 2**60.
    assert _sort_key(1152921504606846990) < _sort_key(2.0**60)
