"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-6a, C1-6b): `value_types._check_type`'s order of checks and the path of
an `in` element, through the in-memory `ApplicationCell` (the shared
choke point both of r2db-api's cells, in-memory and PostgreSQL, use; no
PostgreSQL needed here).

A field declared `string` with `enum ["a", "b"]`: a value of the wrong JSON
type is a `field_type` violation naming the declared and the observed
type, not an `enum` violation (the enum check runs last, once the type has
passed); and an `in` predicate's offending element is named by its own
index (`where/0/value/1`). Each test also drives the neighbouring accepted
or differently-refused case so the asserted details are not the only
outcome observed.
"""
from __future__ import annotations

import pytest

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.structured import ApplicationCell, Predicate

LIMITS = ResourceLimits()


def _widgets() -> ApplicationCell:
    cell = ApplicationCell("enum-order-app", {})
    cell.apply_schema(
        {
            "operation": "create_entity",
            "entity": "widgets",
            "fields": ["status"],
            "field_types": {"status": "string"},
            "field_constraints": {"status": {"enum": ["a", "b"]}},
        },
        developer=True,
        limits=LIMITS,
    )
    cell.transact("widgets", [{"operation": "insert", "values": {"status": "a"}}], LIMITS)
    return cell


def test_enum_field_given_a_value_of_the_wrong_type_reports_field_type_not_enum() -> None:
    """C1-6a: `insert {"status": 5}` -> `field_type`, `declared_type:
    string`, `observed_type: integer`, at `operations/0/values/status`; a
    string outside the enum is the `enum` violation (no `observed_type`)
    at the same path."""
    cell = _widgets()
    with pytest.raises(FoundationError) as excinfo:
        cell.transact("widgets", [{"operation": "insert", "values": {"status": 5}}], LIMITS)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {
        "field": "operations/0/values/status",
        "violated_declaration": "field_type",
        "declared_type": "string",
        "observed_type": "integer",
    }

    with pytest.raises(FoundationError) as excinfo:
        cell.transact("widgets", [{"operation": "insert", "values": {"status": "zz"}}], LIMITS)
    assert excinfo.value.details == {"field": "operations/0/values/status", "violated_declaration": "enum", "declared_type": "string"}


def test_in_predicate_names_the_offending_element_by_its_index() -> None:
    """C1-6b: `where [{status in ["a", 5]}]` -> `field_type` at
    `where/0/value/1` (`declared_type: string`, `observed_type: integer`);
    an `in` list whose members are all strings, even outside the enum, is
    accepted (a predicate carries no enum check) and returns the stored
    row."""
    cell = _widgets()
    with pytest.raises(FoundationError) as excinfo:
        cell.query("widgets", select=["status"], where=[Predicate("status", "in", ["a", 5])], page_size=10, limits=LIMITS)
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert excinfo.value.details == {
        "violated_declaration": "field_type",
        "field": "where/0/value/1",
        "declared_type": "string",
        "observed_type": "integer",
    }

    items = cell.query("widgets", select=["status"], where=[Predicate("status", "in", ["a", "zz"])], page_size=10, limits=LIMITS).items
    assert items == [{"status": "a"}]
