"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-7a, C1-7b): `constraint_resolution._resolve_field_constraints` called
directly, for two refusals `test_constraints_declaration.py` does not fix
-- which key is named when a field's constraint entry carries several
unrecognized keys, and an integer `nullable`.

The unrecognized key is echoed into `details.field` and the message
without a syntax check (client input echoed back; recorded in the work
order, section 4). Each test also resolves a valid neighbouring input so
the refusal is not the only outcome observed.
"""
from __future__ import annotations

import pytest

from mitatedb_api.constraint_resolution import _resolve_field_constraints
from mitatedb_api.errors import ValidationError


def _resolve(entry: dict):
    return _resolve_field_constraints(["status"], {"status": "string"}, {"status": entry}, max_enum_members=10)


def test_several_unrecognized_keys_report_the_alphabetically_first() -> None:
    """C1-7a: `{"zz": 1, "aa": 2}` -> `request_schema` at
    `field_constraints/status/aa`; a single recognized key resolves."""
    with pytest.raises(ValidationError) as excinfo:
        _resolve({"zz": 1, "aa": 2})
    assert excinfo.value.details == {"violated_declaration": "request_schema", "field": "field_constraints/status/aa"}

    assert _resolve({"nullable": False}) == {"status": {"nullable": False}}


def test_an_integer_nullable_is_refused_while_a_boolean_resolves() -> None:
    """C1-7b: `{"nullable": 1}` -> `request_schema` at
    `field_constraints/status/nullable`, `declared_type: boolean`,
    `observed_type: integer`; `{"nullable": True}` resolves."""
    with pytest.raises(ValidationError) as excinfo:
        _resolve({"nullable": 1})
    assert excinfo.value.details == {
        "violated_declaration": "request_schema",
        "field": "field_constraints/status/nullable",
        "declared_type": "boolean",
        "observed_type": "integer",
    }

    assert _resolve({"nullable": True}) == {"status": {"nullable": True}}
