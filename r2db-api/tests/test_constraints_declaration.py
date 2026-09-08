"""Contract 1.7.0 R-2 (`field_constraints` / `enum` / `nullable` / `alter_
field`) -- design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_
VERIFICATION_V1.md §3 D-2, work order docs/work-orders/
WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2a.

Peer-local coverage underneath `conformance-tests/test_c20_constraint_
declaration_agreement.py`'s own cross-peer declaration-agreement test:
this file exercises `ApplicationCell` (in-memory) and `PostgresCell`
(real PostgreSQL) directly, one completion condition (§2 WP-2a) at a
time, plus the two backend-specific mechanisms C-20 itself cannot see
(WP-2a "実装の指示" 4 / D-2 開示事項): the side-table registry's own
per-application-upgrade gate (completion condition 10), and the exact
`schema()`-level capability gate/declaration (condition 12).

Real PostgreSQL throughout the `PostgresCell` half (§5.3 C-5, matching
`tests/test_postgres.py`'s own convention): reuses that file's own
`platform`/`app_a` module fixtures and `make_cell` helper directly
(imported, not duplicated) -- one extra platform-bootstrap ritual per
test session, the same cost every other `test_*.py` file in this
directory that needs real PostgreSQL already pays independently.
"""
from __future__ import annotations

import threading
import types
from pathlib import Path
from typing import Any

import pytest

import httpx

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError
from r2db_api.http import create_app
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell
from r2db_api.structured import ApplicationCell, Predicate, drop_entity_confirmation_phrase

from test_postgres import P, app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()


def _small_enum_limits(bound: int) -> ResourceLimits:
    return ResourceLimits(enum_members=bound)


# ===========================================================================
# In-memory (`ApplicationCell`) -- completion conditions 1-9, 11.
# ===========================================================================


def _memory_cell_with_enum_and_nullable() -> ApplicationCell:
    cell = ApplicationCell(application_id="app-mem")
    cell.apply_schema(
        {
            "operation": "create_entity",
            "entity": "widgets",
            "fields": ["label", "status"],
            "field_types": {"status": "string"},
            "field_constraints": {"status": {"enum": ["draft", "live"], "nullable": False}},
        },
        developer=True,
        limits=LIMITS,
    )
    return cell


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_memory_enum_violation_refused_on_every_write_path(mutation: str) -> None:
    """Completion condition 1 (WP-2a): a value outside a field's declared
    `enum` is refused on insert/update/upsert alike -- `declared_type` is
    present, `observed_type` is not (D-3 (4))."""
    cell = _memory_cell_with_enum_and_nullable()
    if mutation == "insert":
        operation = {"operation": "insert", "values": {"label": "x", "status": "bogus"}}
    elif mutation == "update":
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        operation = {"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": "bogus"}}
    else:
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        operation = {"operation": "upsert", "values": {"label": "x", "status": "bogus"}}
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [operation], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details["violated_declaration"] == "enum"
    assert exc.value.details["declared_type"] == "string"
    assert "observed_type" not in exc.value.details


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_memory_enum_positive_control_writable_on_every_path(mutation: str) -> None:
    """Completion condition 2: a value INSIDE the declared `enum` is
    accepted on every write path (the positive control C-20 (2) needs)."""
    cell = _memory_cell_with_enum_and_nullable()
    if mutation == "insert":
        outcome = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        assert outcome.affected == 1
    elif mutation == "update":
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        outcome = cell.transact("widgets", [{"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": "live"}}], LIMITS)
        assert outcome.affected == 1
    else:
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        outcome = cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        assert outcome.affected == 1


def test_memory_predicate_outside_enum_is_not_refused_but_matches_nothing() -> None:
    """Completion condition 3 (D-2 (2) negative disclosure): a query
    predicate carrying a value outside a field's `enum` is never refused
    -- it simply matches zero rows."""
    cell = _memory_cell_with_enum_and_nullable()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
    outcome = cell.query("widgets", select=["id"], where=[Predicate(field="status", operator="eq", value="not-a-member")], page_size=10, limits=LIMITS)
    assert outcome.items == []


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_memory_nullable_false_refuses_explicit_null(mutation: str) -> None:
    """Completion condition 4: a null written to a `nullable: false`
    field is refused with `observed_type: null`, on insert/update/upsert."""
    cell = _memory_cell_with_enum_and_nullable()
    if mutation == "insert":
        operation = {"operation": "insert", "values": {"label": "x", "status": None}}
    elif mutation == "update":
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        operation = {"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": None}}
    else:
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        operation = {"operation": "upsert", "values": {"label": "x", "status": None}}
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [operation], LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    # Monitor ruling M-3/D (rulings-wp2a-review.md, D-3 (2)): `field` is
    # the request-internal PATH (`operations/0/values/status`), not the
    # bare entity field name -- the single operation under test here is
    # always index 0 of the `operations` list `transact` is called with.
    assert exc.value.details == {"field": "operations/0/values/status", "violated_declaration": "nullable", "declared_type": "string", "observed_type": "null"}


def test_memory_nullable_false_insert_omission_refused_absent() -> None:
    """Completion condition 5 (insert branch): omitting a `nullable:
    false` field on insert is refused with `observed_type: absent`."""
    cell = _memory_cell_with_enum_and_nullable()
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
    assert exc.value.details == {"field": "operations/0/values/status", "violated_declaration": "nullable", "declared_type": "string", "observed_type": "absent"}
    assert cell.entities["widgets"] == []  # nothing written


def test_memory_nullable_false_upsert_insert_resolution_omission_refused() -> None:
    """Completion condition 5 (upsert -> insert branch): an upsert that
    RESOLVES to an insert is held to the same rule."""
    cell = _memory_cell_with_enum_and_nullable()
    cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x"}}], LIMITS)
    assert exc.value.details["violated_declaration"] == "nullable"
    assert exc.value.details["observed_type"] == "absent"
    assert cell.entities["widgets"] == []


def test_memory_nullable_false_upsert_update_resolution_omission_is_not_refused() -> None:
    """Completion condition 5 (upsert -> update branch): an upsert that
    resolves to an UPDATE is NOT held to the insert-only rule -- it
    writes no value to the omitted field, leaving the existing one."""
    cell = _memory_cell_with_enum_and_nullable()
    cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
    outcome = cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x"}}], LIMITS)
    assert outcome.affected == 1
    assert cell.entities["widgets"][0]["status"] == "draft"  # untouched


def test_memory_catalog_field_constraints_round_trips_and_is_total() -> None:
    """Completion condition 6: `catalog()`'s `field_constraints` reports
    exactly what was declared, and is total over the entity's fields (a
    field with no declaration reports `nullable: true`, no `enum`)."""
    cell = _memory_cell_with_enum_and_nullable()
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"] == {
        "id": {"nullable": True},
        "label": {"nullable": True},
        "status": {"nullable": False, "enum": ["draft", "live"]},
    }


def test_memory_alter_field_refuses_when_existing_rows_violate_and_changes_nothing() -> None:
    """Completion condition 7: an `alter_field` whose new constraints an
    EXISTING row would violate is refused whole with CONFLICT -- no row,
    no catalog entry, and no revision change."""
    cell = _memory_cell_with_enum_and_nullable()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
    before_rows = [dict(r) for r in cell.entities["widgets"]]
    before_catalog = cell.catalog()
    before_revision = cell.schema_revision
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["live"]}, developer=True, limits=LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"field": "status", "violated_declaration": "enum"}
    assert cell.entities["widgets"] == before_rows
    assert cell.catalog() == before_catalog
    assert cell.schema_revision == before_revision


def test_memory_alter_field_succeeds_and_advances_revision() -> None:
    """Completion condition 8: an `alter_field` no existing row violates
    succeeds and advances `schema_revision`."""
    cell = _memory_cell_with_enum_and_nullable()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
    before_revision = cell.schema_revision
    revision = cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"]}, developer=True, limits=LIMITS).revision
    assert revision == before_revision + 1
    assert cell.schema_revision == revision
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"]["enum"] == ["draft", "live", "archived"]


def test_memory_alter_field_with_field_type_is_refused_unsupported_field() -> None:
    """Completion condition 9: `alter_field` carrying `field_type` is
    `VALIDATION_FAILED` + `violated_declaration: unsupported_field`."""
    cell = _memory_cell_with_enum_and_nullable()
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "field_type": "string"}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "field_type", "violated_declaration": "unsupported_field"}


def test_memory_alter_field_with_neither_enum_nor_nullable_is_refused_and_does_not_advance_revision() -> None:
    """Ruling N-1 (rulings-r2-closure.md, WP-2a closure): an `alter_field`
    carrying neither `enum` nor `nullable` declares nothing -- refused
    `VALIDATION_FAILED` / `violated_declaration: constraint_declaration` /
    `field: "operation"` (the missing declaration is not any one field's
    key, it is the whole operation), and the schema revision does not
    advance (mirrors completion condition 7's own "changes nothing"
    pattern: rows, catalog AND revision all asserted unchanged)."""
    cell = _memory_cell_with_enum_and_nullable()
    before_rows = [dict(r) for r in cell.entities["widgets"]]
    before_catalog = cell.catalog()
    before_revision = cell.schema_revision
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status"}, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "operation", "violated_declaration": "constraint_declaration"}
    assert cell.entities["widgets"] == before_rows
    assert cell.catalog() == before_catalog
    assert cell.schema_revision == before_revision


def test_memory_enum_members_limit_refuses_before_anything_is_created() -> None:
    """Completion condition 11: an `enum` over the deployed `enum_
    members` bound is refused with `LIMIT_EXCEEDED`/`limit_class:
    enum_members`, before the entity (or field, or alter) it would have
    established exists at all."""
    limits = _small_enum_limits(2)
    cell = ApplicationCell(application_id="app-mem-2")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enum": ["a", "b", "c"]}}},
            developer=True,
            limits=limits,
        )
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert exc.value.details["limit_class"] == "enum_members"
    assert "widgets" not in cell.entities

    cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}}, developer=True, limits=limits)
    with pytest.raises(FoundationError) as exc2:
        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "tier", "field_type": "string", "enum": ["a", "b", "c"]}, developer=True, limits=limits)
    assert exc2.value.details["limit_class"] == "enum_members"
    assert "tier" not in cell.schema["widgets"]

    with pytest.raises(FoundationError) as exc3:
        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["a", "b", "c"]}, developer=True, limits=limits)
    assert exc3.value.details["limit_class"] == "enum_members"
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": True}  # unchanged


# ===========================================================================
# `PostgresCell` -- the same completion conditions, real PostgreSQL,
# plus condition 10 (side-table per-application upgrade).
# ===========================================================================


def _pg_cell_with_enum_and_nullable(cell: PostgresCell) -> None:
    cell.apply_schema(
        {
            "operation": "create_entity",
            "entity": "widgets",
            "fields": ["label", "status"],
            "field_types": {"status": "string"},
            "field_constraints": {"status": {"enum": ["draft", "live"], "nullable": False}},
        },
        developer=True,
        limits=LIMITS,
    )


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_pg_enum_violation_refused_on_every_write_path(app_a: types.SimpleNamespace, mutation: str) -> None:
    """Completion condition 1, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        if mutation == "insert":
            operation = {"operation": "insert", "values": {"label": "x", "status": "bogus"}}
        elif mutation == "update":
            cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            operation = {"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": "bogus"}}
        else:
            cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
            operation = {"operation": "upsert", "values": {"label": "x", "status": "bogus"}}
        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", [operation], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details["violated_declaration"] == "enum"
        assert exc.value.details["declared_type"] == "string"
        assert "observed_type" not in exc.value.details
    finally:
        cell.close()


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_pg_enum_positive_control_writable_on_every_path(app_a: types.SimpleNamespace, mutation: str) -> None:
    """Completion condition 2, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        if mutation == "insert":
            outcome = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            assert outcome.affected == 1
        elif mutation == "update":
            cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            outcome = cell.transact("widgets", [{"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": "live"}}], LIMITS)
            assert outcome.affected == 1
        else:
            cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
            outcome = cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            assert outcome.affected == 1
    finally:
        cell.close()


def test_pg_predicate_outside_enum_is_not_refused_but_matches_nothing(app_a: types.SimpleNamespace) -> None:
    """Completion condition 3, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        outcome = cell.query("widgets", select=["id"], where=[P("status", "eq", "not-a-member")], page_size=10, limits=LIMITS)
        assert outcome.items == []
    finally:
        cell.close()


@pytest.mark.parametrize("mutation", ["insert", "update", "upsert"])
def test_pg_nullable_false_refuses_explicit_null(app_a: types.SimpleNamespace, mutation: str) -> None:
    """Completion condition 4, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        if mutation == "insert":
            operation = {"operation": "insert", "values": {"label": "x", "status": None}}
        elif mutation == "update":
            cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            operation = {"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "x"}], "values": {"status": None}}
        else:
            cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
            cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
            operation = {"operation": "upsert", "values": {"label": "x", "status": None}}
        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", [operation], LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"field": "operations/0/values/status", "violated_declaration": "nullable", "declared_type": "string", "observed_type": "null"}
    finally:
        cell.close()


def test_pg_nullable_false_insert_omission_refused_absent(app_a: types.SimpleNamespace) -> None:
    """Completion condition 5 (insert branch), `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
        assert exc.value.details == {"field": "operations/0/values/status", "violated_declaration": "nullable", "declared_type": "string", "observed_type": "absent"}
        outcome = cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS)
        assert outcome.items == []
    finally:
        cell.close()


def test_pg_nullable_false_upsert_insert_resolution_omission_refused(app_a: types.SimpleNamespace) -> None:
    """Completion condition 5 (upsert -> insert branch), `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x"}}], LIMITS)
        assert exc.value.details["violated_declaration"] == "nullable"
        assert exc.value.details["observed_type"] == "absent"
        outcome = cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS)
        assert outcome.items == []
    finally:
        cell.close()


def test_pg_nullable_false_upsert_update_resolution_omission_is_not_refused(app_a: types.SimpleNamespace) -> None:
    """Completion condition 5 (upsert -> update branch), `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        outcome = cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x"}}], LIMITS)
        assert outcome.affected == 1
        rows = cell.query("widgets", select=["status"], where=[P("label", "eq", "x")], page_size=10, limits=LIMITS)
        assert rows.items == [{"status": "draft"}]
    finally:
        cell.close()


def test_pg_catalog_field_constraints_round_trips_and_is_total(app_a: types.SimpleNamespace) -> None:
    """Completion condition 6, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"] == {
            "id": {"nullable": True},
            "label": {"nullable": True},
            "status": {"nullable": False, "enum": ["draft", "live"]},
        }
    finally:
        cell.close()


def test_pg_alter_field_refuses_when_existing_rows_violate_and_changes_nothing(app_a: types.SimpleNamespace) -> None:
    """Completion condition 7, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        before_rows = cell.query("widgets", select=["id", "label", "status"], where=[], page_size=10, limits=LIMITS).items
        before_catalog = cell.catalog()
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["live"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
        assert exc.value.details == {"field": "status", "violated_declaration": "enum"}
        after_rows = cell.query("widgets", select=["id", "label", "status"], where=[], page_size=10, limits=LIMITS).items
        assert after_rows == before_rows
        assert cell.catalog() == before_catalog
    finally:
        cell.close()


def test_pg_alter_field_succeeds_and_advances_revision(app_a: types.SimpleNamespace) -> None:
    """Completion condition 8, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        with cell._developer.connection() as conn:
            with conn.transaction():
                before_revision = cell._read_schema_revision(conn)
        revision = cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"]}, developer=True, limits=LIMITS).revision
        assert revision == before_revision + 1
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"]["enum"] == ["draft", "live", "archived"]
    finally:
        cell.close()


def test_pg_alter_field_with_field_type_is_refused_unsupported_field(app_a: types.SimpleNamespace) -> None:
    """Completion condition 9, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "field_type": "string"}, developer=True, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"field": "field_type", "violated_declaration": "unsupported_field"}
    finally:
        cell.close()


def test_pg_alter_field_with_neither_enum_nor_nullable_is_refused_and_does_not_advance_revision(app_a: types.SimpleNamespace) -> None:
    """Ruling N-1, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)
        before_rows = cell.query("widgets", select=["id", "label", "status"], where=[], page_size=10, limits=LIMITS).items
        before_catalog = cell.catalog()
        with cell._developer.connection() as conn:
            with conn.transaction():
                before_revision = cell._read_schema_revision(conn)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status"}, developer=True, limits=LIMITS)
        assert exc.value.code == "VALIDATION_FAILED"
        assert exc.value.details == {"field": "operation", "violated_declaration": "constraint_declaration"}
        after_rows = cell.query("widgets", select=["id", "label", "status"], where=[], page_size=10, limits=LIMITS).items
        assert after_rows == before_rows
        assert cell.catalog() == before_catalog
        with cell._developer.connection() as conn:
            with conn.transaction():
                after_revision = cell._read_schema_revision(conn)
        assert after_revision == before_revision
    finally:
        cell.close()


def test_pg_enum_members_limit_refuses_before_anything_is_created(app_a: types.SimpleNamespace) -> None:
    """Completion condition 11, `PostgresCell`."""
    limits = _small_enum_limits(2)
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema(
                {"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enum": ["a", "b", "c"]}}},
                developer=True,
                limits=limits,
            )
        assert exc.value.details["limit_class"] == "enum_members"
        assert not any(e["entity"] == "widgets" for e in cell.catalog())

        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}}, developer=True, limits=limits)
        with pytest.raises(FoundationError) as exc2:
            cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "tier", "field_type": "string", "enum": ["a", "b", "c"]}, developer=True, limits=limits)
        assert exc2.value.details["limit_class"] == "enum_members"
        assert not any(e["entity"] == "widgets" and "tier" in e["fields"] for e in cell.catalog())

        with pytest.raises(FoundationError) as exc3:
            cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["a", "b", "c"]}, developer=True, limits=limits)
        assert exc3.value.details["limit_class"] == "enum_members"
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"nullable": True}
    finally:
        cell.close()


# ---------------------------------------------------------------------------
# Completion condition 10: the side-table registry is created by the
# per-application upgrade (`migrations/0010_field_constraints_upgrade.
# sql`, via `python -m r2db_api.ops upgrade-applications`), and an
# application that has NOT applied it fails safely (never a raw/uncaught
# exception, never a row changed).
# ---------------------------------------------------------------------------


def test_pg_side_table_exists_after_normal_provisioning(app_a: types.SimpleNamespace) -> None:
    """Non-vacuity for condition 10's positive half: `app_a` (provisioned
    through the real, WP-2a-revised `0003_provision_application.sql`)
    already carries the side table and its ledger row -- `alter_field`
    (and every other constraint-touching path) works without a separate
    `ops upgrade-applications` step for a BRAND NEW application."""
    import psycopg

    conn = psycopg.connect(app_a.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public._r2db_field_constraints')")
            assert cur.fetchone()[0] == "_r2db_field_constraints"
            cur.execute("SELECT upgrade_number FROM public._r2db_platform_upgrades ORDER BY upgrade_number")
            assert [row[0] for row in cur.fetchall()] == [9, 10, 11]
    finally:
        conn.close()


def test_pg_alter_field_fails_safely_when_the_upgrade_has_not_been_applied(app_a: types.SimpleNamespace) -> None:
    """Completion condition 10's negative half: simulates an application
    that has never run the `0010` upgrade (its side table is dropped
    here, standing in for "never applied") -- `alter_field` fails
    closed (a `FoundationError`, never an uncaught `psycopg` exception
    reaching this test), and no row anywhere is changed. `create_entity`/
    `add_field` that never mention `field_constraints`/`enum`/`nullable`
    at all keep working unmodified (the graceful-read half of the same
    completion condition -- an application that never exercises this
    capability never needs the upgrade)."""
    import psycopg

    conn = psycopg.connect(app_a.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE public._r2db_field_constraints")
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 10")
        conn.commit()
    finally:
        conn.close()

    cell = make_cell(app_a)
    try:
        # A plain create_entity that never mentions field_constraints
        # still works -- no dependency on the missing upgrade.
        cell.apply_schema({"operation": "create_entity", "entity": "plain", "fields": ["a"]}, developer=True, limits=LIMITS)
        cell.transact("plain", [{"operation": "insert", "values": {"a": 1}}], LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "plain")
        assert entry["field_constraints"] == {"id": {"nullable": True}, "a": {"nullable": True}}

        # alter_field -- which NEEDS to write the registry -- fails
        # closed rather than crashing uncaught.
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "alter_field", "entity": "plain", "field": "a", "nullable": False}, developer=True, limits=LIMITS)
        assert exc.value.code == "SERVICE_UNAVAILABLE"

        # Nothing was changed: the row inserted above is still there,
        # untouched, and the field carries no constraint.
        rows = cell.query("plain", select=["a"], where=[], page_size=10, limits=LIMITS).items
        assert rows == [{"a": 1}]
        entry_after = next(e for e in cell.catalog() if e["entity"] == "plain")
        assert entry_after["field_constraints"]["a"] == {"nullable": True}
    finally:
        cell.close()


def test_pg_ops_upgrade_applications_retrofits_the_side_table_and_unblocks_alter_field(
    app_a: types.SimpleNamespace, platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    """Completion condition 10's own `ops upgrade-applications` half
    (design D-2 (4): "per-application upgrade script + ops upgrade-
    applications 経路"): starting from a legacy-looking application (the
    side table and its ledger row 10 removed, simulating one provisioned
    before this WP shipped), `python -m r2db_api.ops upgrade-applications`
    -- the REAL CLI entry point -- retrofits `migrations/0010_field_
    constraints_upgrade.sql`, after which `alter_field` (which needed the
    table) works again. The REAL `0010` file is used verbatim (only its
    literal `r2dbsvc` registry-schema prefix is textually substituted for
    this test run's own throwaway prefix, into a temp copy pointed to via
    `R2DB_MIGRATIONS_DIR` -- the identical rewriting `tests/test_ops_
    upgrade.py`'s own `platform` fixture already does for `0009`, needed
    for the same reason: `0003`/`0009`/`0010`'s own `r2dbsvc_registry.
    applications` lookup is a literal, not a template). This is the one
    test in this file that actually exercises `r2db_api.ops`/`platform_
    upgrades.PLATFORM_UPGRADE_NUMBERS` rather than talking to the
    database directly."""
    import psycopg
    import r2db_api.ops as ops
    from r2db_api import platform_upgrades

    real_0010 = Path(__file__).resolve().parents[1] / "migrations" / "0010_field_constraints_upgrade.sql"
    rewritten = tmp_path / "0010_field_constraints_upgrade.sql"
    rewritten.write_text(real_0010.read_text().replace("r2dbsvc", platform.prefix))

    conn = psycopg.connect(app_a.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE public._r2db_field_constraints")
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 10")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", f"{platform.prefix}_registry")
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(tmp_path))
    assert 10 in platform_upgrades.PLATFORM_UPGRADE_NUMBERS  # this test observes the REAL package constant
    rc = ops.main(["upgrade-applications", "--application", app_a.slug])
    assert rc == 0

    conn = psycopg.connect(app_a.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public._r2db_field_constraints')")
            assert cur.fetchone()[0] is not None
            cur.execute("SELECT upgrade_number FROM public._r2db_platform_upgrades ORDER BY upgrade_number")
            assert [row[0] for row in cur.fetchall()] == [9, 10, 11]
    finally:
        conn.close()

    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "retrofitted", "fields": ["a"]}, developer=True, limits=LIMITS)
        revision = cell.apply_schema({"operation": "alter_field", "entity": "retrofitted", "field": "a", "nullable": False}, developer=True, limits=LIMITS).revision
        assert revision is not None
        entry = next(e for e in cell.catalog() if e["entity"] == "retrofitted")
        assert entry["field_constraints"]["a"] == {"nullable": False}
    finally:
        cell.close()


# ===========================================================================
# Completion condition 12: `constraint_declarations` is `enabled`, the
# gate is removed, and `schema_ops` names `alter_field` -- service-level,
# no PostgreSQL needed (mirrors `tests/test_foundation.py`'s own `service`
# fixture pattern).
# ===========================================================================


@pytest.fixture
def service() -> DataService:
    credentials = CredentialStore(pepper="test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(credentials)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={})
    return service


def test_capability_constraint_declarations_is_enabled_and_gate_is_removed(service: DataService) -> None:
    developer = service.authenticate("dev-a.dev-secret-a")
    document = service.capabilities(developer)
    assert document["capabilities"]["constraint_declarations"] == {"status": "enabled"}
    assert "alter_field" in document["capabilities"]["schema_operations"]["operations"]
    assert "alter_field" not in document["capabilities"]["schema_operations"].get("unsupported", [])

    # The gate is really gone: `field_constraints`/`enum`/`nullable` reach
    # real enforcement, never a provisional `CAPABILITY_UNSUPPORTED`.
    service.schema(developer, {"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enum": ["a"]}}})
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "alter_field", "entity": "widgets", "field": "status", "field_type": "string"})
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details["violated_declaration"] == "unsupported_field"


# ===========================================================================
# Review-rework coverage (rulings-wp2a-review.md B-1/A/B-2/B-3/M-1..M-5/
# m-1). Same in-memory/`PostgresCell` split as above.
# ===========================================================================


# ---- B-1: enum is declarable ONLY on string/integer/number/boolean ------


@pytest.mark.parametrize(
    "op",
    [
        {"operation": "create_entity", "entity": "untyped", "fields": ["status"], "field_constraints": {"status": {"enum": ["a", "b"]}}},
        {"operation": "create_entity", "entity": "jsontyped", "fields": ["status"], "field_types": {"status": "json"}, "field_constraints": {"status": {"enum": ["a", "b"]}}},
        {"operation": "create_entity", "entity": "objtyped", "fields": ["status"], "field_types": {"status": "object"}, "field_constraints": {"status": {"enum": ["a", "b"]}}},
    ],
    ids=["untyped", "field_types_json", "field_types_object"],
)
def test_memory_enum_declaration_rejected_on_non_scalar_field(op: dict[str, Any]) -> None:
    """Review ruling B-1: `enum` on an untyped/`json`/`object`/`array`
    field is refused outright -- no first-member type INFERENCE (the
    pre-rework bug). `violated_declaration` is the new `constraint_
    declaration` word (ruling m-1), never `enum` (that word is reserved
    for a VALUE outside an already-valid enum, D-3 (3))."""
    cell = ApplicationCell(application_id="app-b1")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(op, developer=True, limits=LIMITS)
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details["violated_declaration"] == "constraint_declaration"
    assert op["entity"] not in cell.entities


def test_memory_enum_declaration_rejected_on_add_field_and_alter_field_untyped() -> None:
    """B-1 for `add_field`/`alter_field`'s own single-field `enum` (never
    just `create_entity`'s `field_constraints`)."""
    cell = ApplicationCell(application_id="app-b1b")
    cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["a"]}, developer=True, limits=LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "add_field", "entity": "w", "field": "untyped2", "enum": ["a", "b"]}, developer=True, limits=LIMITS)
    assert exc.value.details == {"field": "enum", "violated_declaration": "constraint_declaration", "declared_type": "json"}
    assert "untyped2" not in cell.schema["w"]

    cell.apply_schema({"operation": "add_field", "entity": "w", "field": "b"}, developer=True, limits=LIMITS)
    with pytest.raises(FoundationError) as exc2:
        cell.apply_schema({"operation": "alter_field", "entity": "w", "field": "b", "enum": ["a", "b"]}, developer=True, limits=LIMITS)
    assert exc2.value.details == {"field": "enum", "violated_declaration": "constraint_declaration", "declared_type": "json"}
    entry = next(e for e in cell.catalog() if e["entity"] == "w")
    assert entry["field_constraints"]["b"] == {"nullable": True}  # unchanged


def test_pg_enum_declaration_rejected_on_non_scalar_field(app_a: types.SimpleNamespace) -> None:
    """B-1, `PostgresCell` -- both `create_entity` (untyped) and
    `alter_field` (the field's REAL declared type, only known in
    `apply_schema`, addendum R-b/R-c)."""
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema(
                {"operation": "create_entity", "entity": "untyped", "fields": ["status"], "field_constraints": {"status": {"enum": ["a", "b"]}}},
                developer=True,
                limits=LIMITS,
            )
        assert exc.value.details["violated_declaration"] == "constraint_declaration"
        assert not any(e["entity"] == "untyped" for e in cell.catalog())

        cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["a"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc2:
            cell.apply_schema({"operation": "alter_field", "entity": "w", "field": "a", "enum": ["a", "b"]}, developer=True, limits=LIMITS)
        assert exc2.value.details == {"field": "enum", "violated_declaration": "constraint_declaration", "declared_type": "json"}
        entry = next(e for e in cell.catalog() if e["entity"] == "w")
        assert entry["field_constraints"]["a"] == {"nullable": True}
    finally:
        cell.close()


# ---- ruling A/B-2: alter_field is a PATCH, not a wholesale replace ------


def test_memory_alter_field_omitted_key_leaves_existing_constraint_unchanged() -> None:
    """Ruling A verbatim: `enum` omitted = unchanged, `nullable` omitted =
    unchanged, `enum: null` = cleared. The pre-rework bug silently wiped
    whichever key the request omitted."""
    cell = _memory_cell_with_enum_and_nullable()  # status: enum [draft, live], nullable: false

    cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "nullable": False}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": False, "enum": ["draft", "live"]}  # enum untouched

    cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"]}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": False, "enum": ["draft", "live", "archived"]}  # nullable untouched

    cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": None}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": False}  # cleared, nullable still untouched
    assert "status" in cell.field_constraints["widgets"]  # nullable:false row still present

    # M-5 U-c (empty-swing gap): clearing the LAST declared constraint
    # (nullable back to its true default) must remove the registry ENTRY
    # itself -- direct dict inspection, since `catalog()` alone reports
    # the same default whether the entry is present-with-defaults or gone.
    cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "nullable": True}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": True}
    assert "status" not in cell.field_constraints.get("widgets", {}), "registry entry must be removed once the field carries no declaration at all"


def test_pg_alter_field_omitted_key_leaves_existing_constraint_unchanged(app_a: types.SimpleNamespace) -> None:
    """Ruling A, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)  # status: enum [draft, live], nullable: false

        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "nullable": False}, developer=True, limits=LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"nullable": False, "enum": ["draft", "live"]}

        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"]}, developer=True, limits=LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"nullable": False, "enum": ["draft", "live", "archived"]}

        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": None}, developer=True, limits=LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"nullable": False}

        import psycopg

        conn = psycopg.connect(app_a.developer_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT enum_values FROM public._r2db_field_constraints WHERE entity_name = 'widgets' AND field_name = 'status'")
                row = cur.fetchone()
                assert row is not None and row[0] is None  # nullable=false row remains, enum_values cleared to NULL

            # M-5 U-c (empty-swing gap): clearing the LAST remaining
            # declared constraint (nullable back to its true default) must
            # DELETE the registry ROW itself, not merely leave it standing
            # with default values -- direct side-table inspection (a
            # catalog()-only check cannot tell "row present with defaults"
            # apart from "row absent", since both report the same default).
            cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "nullable": True}, developer=True, limits=LIMITS)
            entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
            assert entry["field_constraints"]["status"] == {"nullable": True}
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM public._r2db_field_constraints WHERE entity_name = 'widgets' AND field_name = 'status'")
                assert cur.fetchone() is None, "registry row must be deleted once the field carries no declaration at all"
        finally:
            conn.close()
    finally:
        cell.close()


def test_memory_add_field_enum_null_is_the_same_as_omitting_it() -> None:
    """Ruling A: `add_field`'s own `enum: null` means the same as
    omitting `enum` altogether -- no declaration-invalid error."""
    cell = ApplicationCell(application_id="app-addnull")
    cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["a"]}, developer=True, limits=LIMITS)
    cell.apply_schema({"operation": "add_field", "entity": "w", "field": "s", "field_type": "string", "enum": None, "nullable": False}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "w")
    assert entry["field_constraints"]["s"] == {"nullable": False}  # no enum key at all


# ---- M-6: add_field nullable:false on an entity with existing rows -----


def test_memory_add_field_nullable_false_conflicts_when_rows_already_exist() -> None:
    """Monitor ruling M-6 (rulings-wp2a-review.md, contract corrigendum):
    `add_field` declaring `nullable: false` on an entity that already
    holds rows is refused with `CONFLICT` -- every existing row would
    hold `null` in the brand new field, same rule as `alter_field`'s own
    existing-row scan. Non-vacuity: a row is actually present first."""
    cell = ApplicationCell(application_id="app-m6")
    cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label"]}, developer=True, limits=LIMITS)
    cell.transact("w", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
    assert cell.entities["w"]  # non-vacuity
    before_schema = dict(cell.schema["w"])
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "add_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"field": "note", "violated_declaration": "nullable"}
    assert cell.schema["w"] == before_schema  # the field was never created
    assert "note" not in cell.schema["w"]


def test_memory_add_field_nullable_false_succeeds_on_an_empty_entity() -> None:
    """M-6 positive control: an entity with NO rows is unaffected --
    `add_field {nullable: false}` succeeds normally."""
    cell = ApplicationCell(application_id="app-m6b")
    cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label"]}, developer=True, limits=LIMITS)
    cell.apply_schema({"operation": "add_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "w")
    assert entry["field_constraints"]["note"] == {"nullable": False}


def test_pg_add_field_nullable_false_conflicts_when_rows_already_exist(app_a: types.SimpleNamespace) -> None:
    """M-6, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact("w", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
        rows = cell.query("w", select=["label"], where=[], page_size=10, limits=LIMITS).items
        assert rows  # non-vacuity
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "add_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
        assert exc.value.details == {"field": "note", "violated_declaration": "nullable"}
        entry = next(e for e in cell.catalog() if e["entity"] == "w")
        assert "note" not in entry["fields"]  # the field was never created
    finally:
        cell.close()


def test_pg_add_field_nullable_false_succeeds_on_an_empty_entity(app_a: types.SimpleNamespace) -> None:
    """M-6 positive control, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "add_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "w")
        assert entry["field_constraints"]["note"] == {"nullable": False}
    finally:
        cell.close()


# ---- ruling E / m-1: field_constraints declaration-shape defects --------


def test_memory_field_constraints_unknown_key_is_request_schema() -> None:
    """Ruling E: an unknown key INSIDE one field's own `field_constraints`
    entry (a typo of `enum`, say) is `request_schema`, `field` naming the
    unknown key's own request-internal path -- mirrors MitateDB `cell.py`'s
    identical form."""
    cell = ApplicationCell(application_id="app-e")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "w", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enu": ["a"]}}},
            developer=True,
            limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "field_constraints/status/enu", "violated_declaration": "request_schema"}
    assert "w" not in cell.entities


def test_memory_field_constraints_names_a_field_not_in_fields_is_constraint_declaration() -> None:
    """m-1 (contract corrigendum, verbatim list of `constraint_
    declaration` cases): "...or a declaration naming a field the request
    does not create"."""
    cell = ApplicationCell(application_id="app-m1")
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "w", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"ghost": {"enum": ["a"]}}},
            developer=True,
            limits=LIMITS,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "field_constraints/ghost", "violated_declaration": "constraint_declaration"}
    assert "w" not in cell.entities


def test_pg_field_constraints_unknown_key_is_request_schema(app_a: types.SimpleNamespace) -> None:
    """Ruling E, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema(
                {"operation": "create_entity", "entity": "w", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enu": ["a"]}}},
                developer=True,
                limits=LIMITS,
            )
        assert exc.value.details == {"field": "field_constraints/status/enu", "violated_declaration": "request_schema"}
        assert not any(e["entity"] == "w" for e in cell.catalog())
    finally:
        cell.close()


def test_memory_field_constraints_request_schema_violations_carry_details() -> None:
    """Ruling N-2 (rulings-r2-closure.md, WP-2a closure audit): the two
    `field_constraints`-shape rejections one level UP from the per-entry
    branches above -- `field_constraints` sent without `fields`, and a
    `field_constraints` that is not an object -- both carry the SAME D-3
    four-key form the adjacent per-entry branches already carry:
    `violated_declaration: request_schema`, `field: "field_constraints"`.
    Before this ruling both denials reached the client with `details ==
    {}` (audit WP-2a closure §7 D-1)."""
    cell = ApplicationCell(application_id="app-n2")

    # Case 1: `field_constraints` present, `fields` entirely absent.
    with pytest.raises(FoundationError) as exc_no_fields:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "w1", "field_constraints": {"status": {"enum": ["a"]}}},
            developer=True,
            limits=LIMITS,
        )
    assert exc_no_fields.value.code == "VALIDATION_FAILED"
    assert exc_no_fields.value.details == {"field": "field_constraints", "violated_declaration": "request_schema"}
    assert "w1" not in cell.entities

    # Case 2: `field_constraints` present but not an object.
    with pytest.raises(FoundationError) as exc_not_object:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "w2", "fields": ["status"], "field_constraints": "nope"},
            developer=True,
            limits=LIMITS,
        )
    assert exc_not_object.value.code == "VALIDATION_FAILED"
    assert exc_not_object.value.details == {"field": "field_constraints", "violated_declaration": "request_schema"}
    assert "w2" not in cell.entities


# ---- M-5 gap 1: the `nullable` branch of alter_field's own CONFLICT -----


def test_memory_alter_field_nullable_conflict_when_existing_row_holds_null() -> None:
    """M-5 (empty-swing U-a): a row ACTUALLY holding null in the target
    field (asserted below, non-vacuity) makes `alter_field {nullable:
    false}` refuse with `CONFLICT`/`violated_declaration: nullable` --
    the sibling of completion condition 7's own `enum` branch, previously
    unobserved (a mutation disabling only the `nullable` scan branch
    stayed green)."""
    cell = ApplicationCell(application_id="app-m5a")
    cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label", "note"]}, developer=True, limits=LIMITS)
    cell.transact("w", [{"operation": "insert", "values": {"label": "x", "note": None}}], LIMITS)
    # Non-vacuity: the row we are about to violate against really is null.
    assert cell.entities["w"][0]["note"] is None
    before_rows = [dict(r) for r in cell.entities["w"]]
    before_catalog = cell.catalog()
    before_revision = cell.schema_revision
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema({"operation": "alter_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"field": "note", "violated_declaration": "nullable"}
    assert cell.entities["w"] == before_rows
    assert cell.catalog() == before_catalog
    assert cell.schema_revision == before_revision


def test_pg_alter_field_nullable_conflict_when_existing_row_holds_null(app_a: types.SimpleNamespace) -> None:
    """M-5 gap 1, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "w", "fields": ["label", "note"]}, developer=True, limits=LIMITS)
        cell.transact("w", [{"operation": "insert", "values": {"label": "x", "note": None}}], LIMITS)
        rows = cell.query("w", select=["note"], where=[], page_size=10, limits=LIMITS).items
        assert rows == [{"note": None}]  # non-vacuity
        before_rows = cell.query("w", select=["label", "note"], where=[], page_size=10, limits=LIMITS).items
        before_catalog = cell.catalog()
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "alter_field", "entity": "w", "field": "note", "nullable": False}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
        assert exc.value.details == {"field": "note", "violated_declaration": "nullable"}
        after_rows = cell.query("w", select=["label", "note"], where=[], page_size=10, limits=LIMITS).items
        assert after_rows == before_rows
        assert cell.catalog() == before_catalog
    finally:
        cell.close()


# ---- M-5 gap 2: entity lifetime scope (drop -> recreate inherits none) --


def test_memory_drop_entity_then_recreate_does_not_inherit_constraints() -> None:
    """M-5 (empty-swing U-b): dropping an entity and recreating one of the
    SAME name must not carry over the dropped entity's own `field_
    constraints` -- the new entity's catalog reports the version-wide
    default, and a value outside the OLD enum now writes cleanly."""
    cell = _memory_cell_with_enum_and_nullable()  # widgets.status: enum [draft, live], nullable: false
    cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_entity_confirmation_phrase("widgets", cell.schema_revision)}, developer=True, limits=LIMITS)
    cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label", "status"]}, developer=True, limits=LIMITS)
    entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
    assert entry["field_constraints"]["status"] == {"nullable": True}  # no inherited enum/nullable:false
    outcome = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "not-in-old-enum"}}], LIMITS)
    assert outcome.affected == 1


def test_pg_drop_entity_then_recreate_does_not_inherit_constraints(app_a: types.SimpleNamespace) -> None:
    """M-5 gap 2, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        with cell._developer.connection() as conn:
            with conn.transaction():
                revision = cell._read_schema_revision(conn)
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_entity_confirmation_phrase("widgets", revision)}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label", "status"]}, developer=True, limits=LIMITS)
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"nullable": True}
        outcome = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "not-in-old-enum"}}], LIMITS)
        assert outcome.affected == 1
    finally:
        cell.close()


# ---- B-3: drop_entity must not fail on an un-upgraded application -------


def test_pg_drop_entity_succeeds_when_the_upgrade_has_not_been_applied(app_a: types.SimpleNamespace) -> None:
    """Monitor ruling B-3 (rulings-wp2a-review.md): `drop_entity`'s own
    side-table cleanup must not turn an operation UNRELATED to `field_
    constraints` into a `SERVICE_UNAVAILABLE` just because the side table
    was never created (mirrors `test_pg_alter_field_fails_safely_when_
    the_upgrade_has_not_been_applied`'s own un-upgraded simulation, but
    for the operation that must SUCCEED, not fail safely)."""
    import psycopg

    conn = psycopg.connect(app_a.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE public._r2db_field_constraints")
            cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 10")
        conn.commit()
    finally:
        conn.close()

    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "plain", "fields": ["a"]}, developer=True, limits=LIMITS)
        with cell._developer.connection() as pconn:
            with pconn.transaction():
                revision = cell._read_schema_revision(pconn)
        revision_after = cell.apply_schema(
            {"operation": "drop_entity", "entity": "plain", "destructive": True, "confirmation": drop_entity_confirmation_phrase("plain", revision)},
            developer=True,
            limits=LIMITS,
        ).revision
        assert revision_after == revision + 1
        assert not any(e["entity"] == "plain" for e in cell.catalog())
    finally:
        cell.close()


# ---- M-2: the upsert TOCTOU fix, pinned at the SQL level -----------------


def test_pg_upsert_missing_field_check_locks_the_row_for_update(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monitor ruling M-2 (rulings-wp2a-review.md): the existence-check
    `SELECT` the upsert-resolves-to-insert-or-update decision runs on is
    issued with `FOR UPDATE` -- pinned at the SQL text level (the actual
    race is not realistically triggerable from a single-connection test,
    per the ruling's own "現実的に書けない")."""
    import r2db_api.postgres as postgres_module

    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.apply_schema({"operation": "create_index", "entity": "widgets", "index": "uniq_label", "fields": ["label"], "unique": True}, developer=True, limits=LIMITS)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)

        captured: list[str] = []
        real_run = postgres_module._run

        def spy(cursor: Any, statement: Any, params: Any = ()) -> None:
            try:
                captured.append(statement.as_string(cursor))
            except Exception:
                pass
            real_run(cursor, statement, params)

        monkeypatch.setattr(postgres_module, "_run", spy)
        # Resolves to UPDATE (an existing row with label=x already exists)
        # -- the missing-field existence check DOES run (status, nullable:
        # false, is omitted).
        outcome = cell.transact("widgets", [{"operation": "upsert", "values": {"label": "x"}}], LIMITS)
        assert outcome.affected == 1
        select_statements = [s for s in captured if s.strip().upper().startswith("SELECT 1 FROM")]
        assert select_statements, "the existence-check SELECT never ran -- test setup is wrong"
        assert any("FOR UPDATE" in s.upper() for s in select_statements), captured
    finally:
        cell.close()


# ---- M-1: alter_field locks the table before scanning existing rows -----


def test_pg_alter_field_locks_the_table_in_share_mode_before_scanning(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monitor ruling M-1/F (rulings-wp2a-review.md, rulings-wp3a-
    review.md F): `alter_field` takes `LOCK TABLE ... IN SHARE ROW
    EXCLUSIVE MODE` before its own existing-row scan, inside the same
    transaction -- pinned at the SQL text level (the race itself needs
    two concurrent sessions, not realistically triggerable from a
    single-connection test, same reasoning as the M-2 test above).

    R-35 (Phase 10, WP-6d-i review): originally plain `SHARE MODE`,
    which does not conflict with itself and could deadlock two
    concurrent `add_field`/`alter_field` calls on the same entity at
    their own later `ALTER TABLE` -- see the deterministic two-
    connection race test right below this one for that scenario
    actually observed against real PostgreSQL, not merely at the SQL-
    text level."""
    import r2db_api.postgres as postgres_module

    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)

        captured: list[str] = []
        real_run = postgres_module._run

        def spy(cursor: Any, statement: Any, params: Any = ()) -> None:
            try:
                captured.append(statement.as_string(cursor))
            except Exception:
                pass
            real_run(cursor, statement, params)

        monkeypatch.setattr(postgres_module, "_run", spy)
        cell.apply_schema({"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"]}, developer=True, limits=LIMITS)

        lock_statements = [s for s in captured if "LOCK TABLE" in s.upper()]
        assert lock_statements, captured
        assert "SHARE ROW EXCLUSIVE MODE" in lock_statements[0].upper()
        # The lock precedes the row-existence scan (the same statement
        # list order `_run` recorded them in).
        scan_index = next(i for i, s in enumerate(captured) if s.strip().upper().startswith("SELECT 1 FROM"))
        lock_index = captured.index(lock_statements[0])
        assert lock_index < scan_index
    finally:
        cell.close()


# ---- R-35: the M-1/M-6 lock must not deadlock two concurrent schema ops --


def test_pg_concurrent_add_field_calls_on_same_entity_serialize_without_deadlock(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-35 (Phase 10, WP-6d-i review): plain `LOCK TABLE ... IN SHARE
    MODE` does not conflict with itself, so two concurrent `add_field`
    calls declaring `nullable: false` on the SAME entity could both
    acquire it, then each block at its own later `ALTER TABLE` (ACCESS
    EXCLUSIVE) waiting on the other's SHARE lock -- a guaranteed mutual
    wait resolved only by PostgreSQL's deadlock detector aborting one
    side with an error. `SHARE ROW EXCLUSIVE` (self-conflicting) instead
    makes the second caller wait AT `LOCK TABLE` until the first commits.

    Verified against a REAL two-connection race, never merely at the SQL-
    text level (contrast the M-1 test above, whose own docstring
    disclaims exactly this scenario as untestable from one connection):
    thread A's `add_field` is paused (a monkeypatched module-level
    `postgres_module._run`) immediately AFTER its own `LOCK TABLE`
    RETURNS and before its `ALTER TABLE`. While it is paused, thread B
    (the main thread) starts a second, independent `add_field` on the
    SAME entity -- if the two locks conflict, B's own `LOCK TABLE`
    blocks INSIDE `cursor.execute` itself and never reaches the line
    that would record it as returned, so it must not do so within a
    short window. Releasing A lets both complete, in sequence, with no
    deadlock error, and the final catalog carries both new fields."""
    import r2db_api.postgres as postgres_module

    cell = make_cell(app_a, pool_size=2)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "lockrace", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True,
            limits=LIMITS,
        )

        real_run = postgres_module._run
        lock_call_count = {"n": 0}
        lock_acquired = threading.Event()  # thread A's own LOCK TABLE has returned
        b_lock_returned = threading.Event()  # thread B's own LOCK TABLE has returned
        release_a = threading.Event()

        def paced_run(cursor: Any, statement: Any, params: Any = ()) -> Any:
            try:
                rendered = statement.as_string(cursor)
            except Exception:
                rendered = ""
            is_lock = rendered.strip().upper().startswith("LOCK TABLE")
            my_index = None
            if is_lock:
                lock_call_count["n"] += 1
                my_index = lock_call_count["n"]
            result = real_run(cursor, statement, params)
            if is_lock:
                if my_index == 1:
                    lock_acquired.set()
                    assert release_a.wait(timeout=10), "test-side release never arrived"
                else:
                    b_lock_returned.set()
            return result

        monkeypatch.setattr(postgres_module, "_run", paced_run)

        a_errors: list[Exception] = []

        def _add_field_a() -> None:
            try:
                cell.apply_schema(
                    {"operation": "add_field", "entity": "lockrace", "field": "field_a", "field_type": "string", "nullable": False},
                    developer=True,
                    limits=LIMITS,
                )
            except Exception as exc:  # pragma: no cover - surfaced via a_errors
                a_errors.append(exc)

        thread_a = threading.Thread(target=_add_field_a)
        thread_a.start()
        try:
            assert lock_acquired.wait(timeout=10), "thread A never reached its own LOCK TABLE"

            b_errors: list[Exception] = []

            def _add_field_b() -> None:
                try:
                    cell.apply_schema(
                        {"operation": "add_field", "entity": "lockrace", "field": "field_b", "field_type": "string", "nullable": False},
                        developer=True,
                        limits=LIMITS,
                    )
                except Exception as exc:  # pragma: no cover - surfaced via b_errors
                    b_errors.append(exc)

            thread_b = threading.Thread(target=_add_field_b)
            thread_b.start()
            try:
                assert not b_lock_returned.wait(timeout=0.5), (
                    "thread B's LOCK TABLE returned while thread A still holds the lock -- "
                    "the two locks did not conflict (R-35 regression)"
                )
            finally:
                release_a.set()
                thread_b.join(timeout=10)
        finally:
            thread_a.join(timeout=10)

        assert not thread_a.is_alive(), "thread A never finished -- bounded-wait violated"
        assert not thread_b.is_alive(), "thread B never finished -- bounded-wait violated"
        assert not a_errors, a_errors
        assert not b_errors, b_errors
        assert b_lock_returned.is_set(), "thread B's LOCK TABLE never returned even after release"

        catalog = {e["entity"]: e for e in cell.catalog()}
        assert {"field_a", "field_b"}.issubset(set(catalog["lockrace"]["fields"])), catalog["lockrace"]
    finally:
        cell.close()


# ---- M-4: `query` never reads the field_constraints side table ----------


def test_pg_query_never_reads_the_field_constraints_side_table(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monitor ruling M-4 (rulings-wp2a-review.md): `_load_field_
    constraints` (the side-table SAVEPOINT+SELECT+RELEASE round trip) is
    skipped entirely on the read-only `query` path -- pinned by counting
    calls to it directly -- while `transact`/`catalog` (which DO need
    `table_info.constraints`) still read it exactly once per call."""
    from r2db_api.postgres import PostgresCell

    cell = make_cell(app_a)
    try:
        _pg_cell_with_enum_and_nullable(cell)
        cell.transact("widgets", [{"operation": "insert", "values": {"label": "x", "status": "draft"}}], LIMITS)

        calls = {"n": 0}
        real = PostgresCell._load_field_constraints

        def spy(self: "PostgresCell", conn: Any) -> Any:
            calls["n"] += 1
            return real(self, conn)

        monkeypatch.setattr(PostgresCell, "_load_field_constraints", spy)

        cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS)
        assert calls["n"] == 0, "query() must not read the field_constraints side table (M-4)"

        cell.transact("widgets", [{"operation": "insert", "values": {"label": "y", "status": "draft"}}], LIMITS)
        assert calls["n"] == 1, "transact() (a write path) must still read it"

        cell.catalog()
        assert calls["n"] == 2, "catalog() must still read it"
    finally:
        cell.close()


# ---- m-2: HTTP round trip positive branch --------------------------------


@pytest.mark.anyio
async def test_http_constraint_declarations_enforced_end_to_end() -> None:
    """Monitor ruling m-2 (rulings-wp2a-review.md): a real HTTP positive
    branch -- `create_entity` with `field_constraints` -> `GET /v1/catalog`
    reports it -> an enum-violating `POST .../mutations` is refused with
    the D-3 four-key form, all over the real ASGI boundary (`test_http.
    py`'s own gate-removal coverage never added this positive leg -- it
    only deleted the provisional-gate case). A self-contained `service`/
    ASGI client (mirroring `test_http.py`'s own `_build_service`/`_client`
    pattern, not imported directly -- this file already defines its own
    `service` fixture, for the unrelated capability test above, under the
    same name) so this stays a single, independent test."""
    credentials = CredentialStore(pepper="constraints-http-test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(credentials)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={})

    def auth(secret: str) -> dict[str, str]:
        return {"authorization": f"Bearer {secret}"}

    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://r2db.example.invalid") as client:
        response = await client.post(
            "/v1/schema/operations",
            headers=auth("dev-a.dev-secret-a"),
            json={
                "operation": "create_entity",
                "entity": "http_constraints",
                "fields": ["status"],
                "field_types": {"status": "string"},
                "field_constraints": {"status": {"enum": ["draft", "live"], "nullable": False}},
            },
        )
        assert response.status_code == 200, response.text

        catalog_response = await client.get("/v1/catalog", headers=auth("cred-a.secret-a"))
        assert catalog_response.status_code == 200
        entry = next(e for e in catalog_response.json()["entities"] if e["entity"] == "http_constraints")
        assert entry["field_constraints"]["status"] == {"nullable": False, "enum": ["draft", "live"]}

        mutate_response = await client.post(
            "/v1/data/http_constraints/mutations",
            headers=auth("cred-a.secret-a"),
            json={"operations": [{"operation": "insert", "values": {"status": "bogus"}}]},
        )
        assert mutate_response.status_code == 400
        body = mutate_response.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert body["details"]["violated_declaration"] == "enum"
        assert body["details"]["declared_type"] == "string"
        assert "observed_type" not in body["details"]

        # Positive: a value INSIDE the enum, over the real HTTP boundary.
        ok_response = await client.post(
            "/v1/data/http_constraints/mutations",
            headers=auth("cred-a.secret-a"),
            json={"operations": [{"operation": "insert", "values": {"status": "draft"}}]},
        )
        assert ok_response.status_code == 200, ok_response.text


# ---- N-1: alter_field declaring neither enum nor nullable ---------------
# (rulings-r2-closure.md, WP-2a closure): the in-memory/`PostgresCell`
# pair above already covers this at the backend boundary; these two cover
# the two remaining entry points named by the ruling -- the real ASGI/
# HTTP boundary, and `DataService.schema` called in-process (mirrors
# `tests/test_http.py`'s own HTTP/in-process pair for the WP-1 provisional
# gate). Both assert the SAME two things: the denial's details, and that
# nothing changed (no catalog/`field_constraints` mutation, which is the
# only revision-observable surface either entry point exposes publicly).


@pytest.mark.anyio
async def test_http_alter_field_with_neither_enum_nor_nullable_is_refused() -> None:
    """Ruling N-1, real ASGI/HTTP boundary."""
    credentials = CredentialStore(pepper="n1-http-test-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-a", "app-a", "runtime", "secret-a", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-a", "app-a", "developer", "dev-secret-a", work=work)
    service = DataService(credentials)
    control = ControlAuthority(service)
    control.register_application("app-a", entities={})

    def auth(secret: str) -> dict[str, str]:
        return {"authorization": f"Bearer {secret}"}

    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://r2db.example.invalid") as client:
        create_response = await client.post(
            "/v1/schema/operations",
            headers=auth("dev-a.dev-secret-a"),
            json={"operation": "create_entity", "entity": "n1_http", "fields": ["status"], "field_types": {"status": "string"}},
        )
        assert create_response.status_code == 200, create_response.text

        catalog_before = (await client.get("/v1/catalog", headers=auth("cred-a.secret-a"))).json()

        alter_response = await client.post(
            "/v1/schema/operations",
            headers=auth("dev-a.dev-secret-a"),
            json={"operation": "alter_field", "entity": "n1_http", "field": "status"},
        )
        assert alter_response.status_code == 400, alter_response.text
        body = alter_response.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert body["details"] == {"field": "operation", "violated_declaration": "constraint_declaration"}

        catalog_after = (await client.get("/v1/catalog", headers=auth("cred-a.secret-a"))).json()
        assert catalog_after == catalog_before


def test_alter_field_with_neither_enum_nor_nullable_is_refused_in_process(service: DataService) -> None:
    """Ruling N-1, `DataService.schema` called in-process (bypassing
    `r2db_api.http`'s ASGI boundary entirely) -- reuses this file's own
    `service` fixture (completion condition 12 above), and additionally
    asserts the underlying cell's `schema_revision` directly (unlike the
    HTTP sibling, an in-process call CAN reach it), the strongest form of
    "does not advance the schema revision"."""
    developer = service.authenticate("dev-a.dev-secret-a")
    service.schema(developer, {"operation": "create_entity", "entity": "n1_proc", "fields": ["status"], "field_types": {"status": "string"}})

    cell = service._cells["app-a"]
    before_revision = cell.schema_revision
    catalog_before = service.catalog(developer)

    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "alter_field", "entity": "n1_proc", "field": "status"})
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"field": "operation", "violated_declaration": "constraint_declaration"}

    assert cell.schema_revision == before_revision
    assert service.catalog(developer) == catalog_before


# ---- m-3: same-named helper report (isomorphism pairing input) ----------


def test_helper_names_match_the_isomorphism_pairing_target() -> None:
    """m-3 (monitor ruling): `validate_enum_declaration(enum_values,
    declared_type)` and `enum_member_matches_type(value, declared_type)`
    exist under these exact names/signatures in `r2db_api.structured` --
    the supervisor's own pair-closing commit is what actually registers
    them in `_ISOMORPHIC_TARGETS` (work order §2 WP-2a "同型性テストの
    対象": "実装担当が行わない"), this only pins that the NAMES this WP
    committed to are the ones that commit will find."""
    import inspect

    from r2db_api import structured as structured_module

    sig = inspect.signature(structured_module.validate_enum_declaration)
    assert list(sig.parameters) == ["enum_values", "declared_type"]
    sig2 = inspect.signature(structured_module.enum_member_matches_type)
    assert list(sig2.parameters) == ["value", "declared_type"]
