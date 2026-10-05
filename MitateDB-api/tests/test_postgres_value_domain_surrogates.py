"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-9): `postgres_value_domain._validate_value_domain` called directly with
a lone UTF-16 surrogate at both ends of both halves of the surrogate range.

Earlier tests use only `"\\ud800"`, so narrowing the check to the high
half stayed green. Here the high half (`\\ud800`, `\\udbff`) and the low
half (`\\udc00`, `\\udfff`) are each refused with the `field_type` details,
and the code points just outside the range (`\\ud7ff`, `\\ue000`) are
accepted.
"""
from __future__ import annotations

import pytest

from mitatedb_api.errors import ValidationError
from mitatedb_api.postgres_value_domain import _validate_value_domain


def test_a_lone_surrogate_is_refused_across_the_whole_range_and_its_neighbours_are_not() -> None:
    """C1-9: `\\ud800`, `\\udbff`, `\\udc00`, `\\udfff` -> `ValidationError`
    (`field_type`, `observed_type: string`); `\\ud7ff` and `\\ue000` are
    returned unchanged."""
    for lone in ("\ud800", "\udbff", "\udc00", "\udfff"):
        with pytest.raises(ValidationError) as excinfo:
            _validate_value_domain(lone, "string", field="f", declared_type="string")
        assert excinfo.value.details == {"violated_declaration": "field_type", "field": "f", "declared_type": "string", "observed_type": "string"}, repr(lone)

    for neighbour in ("\ud7ff", "\ue000"):
        assert _validate_value_domain(neighbour, "string", field="f", declared_type="string") == neighbour
