"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-3a..C1-3f): `request_limits._measure_request_bytes`'s per-type costs
and its ancestor-path cycle rule, called directly (no connection, no
gate).

`test_application_plane_limits.py` already fixes a string at `len * 4`,
the list and dict element-count early-reject, depth and a self-referential
cycle. This file fixes what it does not: a scalar and an unknown type cost
8, `bytes`/`bytearray` cost their length, an empty container costs 2 (for
`list`, and separately for `tuple` and `set`), a dict key is walked and
costed like any child, and one container appearing twice as unrelated
siblings is not a cycle.

Each cost is pinned at a bound boundary: the same input is refused at
`bound = cost - 1` (`ResourceLimitError`, `limit_class: request_bytes`)
and accepted at `bound = cost`. Both calls are made in every test, so a
test cannot pass by observing only one side.
"""
from __future__ import annotations

import pytest

from mitatedb_api.errors import ResourceLimitError, ValidationError
from mitatedb_api.request_limits import _measure_request_bytes


def _assert_cost(request, cost: int) -> None:
    with pytest.raises(ResourceLimitError) as excinfo:
        _measure_request_bytes(request, cost - 1)
    assert excinfo.value.details == {"limit_class": "request_bytes"}, (request, cost)
    assert _measure_request_bytes(request, cost) is None, (request, cost)


def test_a_scalar_and_an_unknown_type_cost_eight_each() -> None:
    """C1-3a: `None`, `True`, `1`, `1.5` and a plain `object()` each cost
    8 (refused at bound 7, accepted at bound 8)."""
    for scalar in (None, True, 1, 1.5, object()):
        _assert_cost(scalar, 8)


def test_bytes_and_bytearray_cost_their_length() -> None:
    """C1-3b: ten bytes cost 10 (refused at bound 9, accepted at 10), as a
    `bytes` and as a `bytearray`."""
    _assert_cost(b"x" * 10, 10)
    _assert_cost(bytearray(b"x" * 10), 10)


def test_an_empty_list_costs_the_container_constant_two() -> None:
    """C1-3c: an empty list costs 2 (refused at bound 1, accepted at 2)."""
    _assert_cost([], 2)


def test_tuple_and_set_are_containers_not_unknown_types() -> None:
    """C1-3d: an empty tuple and an empty set cost 2 like a list (an
    unknown type would cost 8); a one-element tuple and set cost 2 + 8."""
    _assert_cost((), 2)
    _assert_cost(set(), 2)
    _assert_cost((1,), 10)
    _assert_cost({1}, 10)


def test_a_dict_key_is_walked_and_costed_like_a_value() -> None:
    """C1-3e: `{"a": 1}` costs 2 + 4 + 8 = 14 (a one-character string key
    costs 4) and `{1: 1}` costs 2 + 8 + 8 = 18 (an integer key costs 8)."""
    _assert_cost({"a": 1}, 14)
    _assert_cost({1: 1}, 18)


def test_one_container_shared_by_two_siblings_is_not_a_cycle_but_a_self_reference_is() -> None:
    """C1-3f: the same list placed twice in a parent (`[shared, shared]`)
    is measured without error; a list that contains itself raises
    `ValidationError` with the bare `request_schema` violation."""
    shared = [1, 2]
    assert _measure_request_bytes([shared, shared], 1000) is None
    assert _measure_request_bytes({"a": shared, "b": shared}, 1000) is None

    cyclic: list = []
    cyclic.append(cyclic)
    with pytest.raises(ValidationError) as excinfo:
        _measure_request_bytes(cyclic, 1000)
    assert excinfo.value.details == {"violated_declaration": "request_schema"}
