"""Phase 9 WP-3a peer-local tests (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-3a): `enum`/
`nullable` field constraints and `alter_field` -- the MitateDB-specific
completion conditions and mechanics `conformance-tests/
test_c20_constraint_declaration_agreement.py` (peer-independent, common
port) cannot itself observe or is not the right place to pin.

Completion conditions 1-9/11/12 here are the SAME propositions C-20 checks
against the real, real-time-flipped MitateDB plugs (this file exercises
them directly against `ApplicationCell`/`ApplicationDeveloper`/
`ApplicationRuntime`, the SQLite in-process backend, faster and finer-
grained than a full conformance round trip -- e.g. asserting the exact
`details` dict shape, not only the refusal code). Completion condition 10
(per-application upgrade script safety) and 13 (single-transaction
existing-row scan) are real-PostgreSQL-only propositions with no SQLite
equivalent, in their own section below (design D-2 実装の形 4, F-6):
`conformance-tests/test_c20_constraint_declaration_agreement.py`'s own
module docstring explicitly discloses that condition 13's proposition is
NOT observable from the common suite ("Disclosed scope limit (MitateDB
`alter_field` transaction boundary)").

Non-vacuity (常設規律 1): every test below asserts a real, directly
observed outcome (a `details` dict's exact keys/values, a real row that
was or was not written, a real commit-call count) -- never a bare
pass-through.
"""
from __future__ import annotations

import types

import psycopg
import pytest
from psycopg import sql

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import ConflictError, ResourceLimitError, ValidationError
from mitatedb_api.auth import Principal

# ===========================================================================
# In-process (SQLite backend) fixtures -- completion conditions 1-9, 11, 12.
# ===========================================================================


def _sessions():
    control = ControlPlane("synthetic-test-pepper-0123456789")
    control.provision_application("app_a")
    dev_id, dev_secret = control.issue_credential("app_a", Role.DEVELOPER)
    runtime_id, runtime_secret = control.issue_credential("app_a", Role.RUNTIME)
    service = MitateDataService(control)
    return service.open_session(dev_secret), service.open_session(runtime_secret)


@pytest.fixture
def sessions():
    return _sessions()


def _make_entity(dev, entity="widgets"):
    # `fields`, at this direct/in-process ApplicationDeveloper API level,
    # is `{field_name: foundation_type}` (`cell._FIELD_TYPE_VOCABULARY`:
    # text/integer/real/boolean/json) -- NOT the wire-shaped bare name
    # array `SchemaOperationRequest.fields` uses (`http.py::post_schema`
    # is what translates between the two). `field_types` carries the
    # separate 7-word CONTRACT vocabulary this WP's `field_constraints`
    # validation checks `enum` members against.
    dev.create_entity(
        entity, fields={"status": "text", "req": "text", "label": "text"},
        field_types={"status": "string", "req": "string", "label": "string"},
        field_constraints={"status": {"enum": ["a", "b"]}, "req": {"nullable": False}},
    )
    return entity


# --- completion condition 1/2: enum enforced on insert/update, positive control ---


def test_enum_violation_on_insert_carries_d3_details(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "z", "req": "ok", "label": "x"})
    details = excinfo.value.details
    assert details.get("violated_declaration") == "enum", details
    assert details.get("declared_type") == "string", details
    assert "observed_type" not in details, details


def test_enum_violation_on_update_carries_d3_details(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "seed"})
    with pytest.raises(ValidationError) as excinfo:
        runtime.update(entity, {"status": "not-a-member"}, [Filter("label", "eq", "seed")])
    assert excinfo.value.details.get("violated_declaration") == "enum"


def test_enum_positive_control_all_three_write_routes(sessions) -> None:
    """Completion condition 2's "3 経路" (the positive control read
    against 3 write routes each accepting an in-set value) does NOT
    include `upsert`: MitateDB has no `upsert` at all -- both
    `atomic_mutation` and `cross_entity_mutation` declare it
    `unsupported` (`unsupported: ["upsert"]`) -- so there is no fourth
    write route to observe an upsert-that-resolves-to-insert against. The
    3 routes actually exercised below are insert / update / transact
    insert (`transact()`'s own insert branch, `_plan_operation`, the
    SECOND real insert entry point alongside `insert()` itself, design
    D-2 (3))."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "p1"})
    runtime.update(entity, {"status": "b"}, [Filter("label", "eq", "p1")])
    rows = runtime.read(entity, filters=[Filter("label", "eq", "p1")])
    assert rows and rows[0]["status"] == "b", rows
    # transact()'s own insert branch (`_plan_operation`) -- the SECOND real
    # insert entry point (design D-2 (3), this file's own module docstring).
    runtime.transact([{"type": "insert", "collection": entity, "values": {"status": "a", "req": "ok", "label": "p2"}}])
    assert runtime.read(entity, filters=[Filter("label", "eq", "p2")])


# --- completion condition 3: query predicate outside enum is not refused ---


def test_query_predicate_outside_enum_is_not_refused_and_matches_nothing(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "only-row"})
    rows = runtime.read(entity, filters=[Filter("status", "eq", "not-a-member")])
    assert rows == []


# --- completion condition 4: explicit null on nullable:false ---


def test_explicit_null_on_nullable_false_field_is_refused(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "a", "req": None, "label": "x"})
    details = excinfo.value.details
    assert details.get("violated_declaration") == "nullable", details
    assert details.get("observed_type") == "null", details
    assert details.get("declared_type") == "string", details


def test_explicit_null_on_nullable_false_field_is_refused_on_update(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "u1"})
    with pytest.raises(ValidationError) as excinfo:
        runtime.update(entity, {"req": None}, [Filter("label", "eq", "u1")])
    assert excinfo.value.details.get("violated_declaration") == "nullable"


# --- completion condition 5: omission on insert vs update ---


def test_insert_omitting_nullable_false_field_is_refused_absent(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "a", "label": "x"})
    details = excinfo.value.details
    assert details.get("violated_declaration") == "nullable", details
    assert details.get("observed_type") == "absent", details
    assert details.get("declared_type") == "string", details


def test_transact_insert_branch_omitting_nullable_false_field_is_refused_absent(sessions) -> None:
    """The SECOND real insert entry point (`_plan_operation`'s own insert
    branch, design D-2 (3)'s own file:line) -- proves the 欠落検査 is not
    only on `ApplicationCell.insert` above."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.transact([{"type": "insert", "collection": entity, "values": {"status": "a", "label": "x"}}])
    details = excinfo.value.details
    assert details.get("violated_declaration") == "nullable"
    assert details.get("observed_type") == "absent"


def test_update_omitting_nullable_false_field_is_not_rejected(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "keep"})
    # Omits `req` entirely -- update never requires a field it does not
    # name; this must succeed and leave `req`'s existing value untouched.
    runtime.update(entity, {"status": "b"}, [Filter("label", "eq", "keep")])
    row = runtime.read(entity, filters=[Filter("label", "eq", "keep")])[0]
    assert row["req"] == "ok", row


# --- completion condition 6: catalog round-trip, total over fields ---


def test_catalog_field_constraints_round_trips_and_is_total(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    constraints = row["field_constraints"]
    assert set(row["fields"]) <= set(constraints.keys()), (row["fields"], constraints)
    for field in row["fields"]:
        assert "nullable" in constraints[field], constraints
    assert constraints["status"]["enum"] == ["a", "b"], constraints
    assert constraints["req"]["nullable"] is False, constraints
    # `label` declared no constraints at all -- contract default.
    assert constraints["label"] == {"nullable": True}, constraints


# --- WP-3a rework 2, M-6 (監督裁定, 2026-09-07): add_field(nullable:
# false) on an entity that already holds rows is refused with CONFLICT,
# the same rule alter_field already applies to an EXISTING field's own
# nullable:false redeclaration -- a NEW column always starts every
# existing row at null, so there is no way for such an add_field to
# succeed honestly. ---


def test_add_field_nullable_false_on_entity_with_rows_conflicts(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "existing-row"})
    revision_before = dev.schema_revision()
    with pytest.raises(ConflictError) as excinfo:
        dev.add_field(entity, "score", "text", contract_type="string", nullable=False)
    details = excinfo.value.details
    assert details.get("violated_declaration") == "nullable", details
    assert details.get("field") == "nullable", details
    assert "existing-row" not in str(details), details
    # Non-vacuity: nothing changed -- no column, no registry row, no
    # revision bump.
    assert dev.schema_revision() == revision_before
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert "score" not in row["fields"], row


def test_add_field_nullable_false_on_empty_entity_succeeds(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    # No rows inserted -- zero existing rows means the new column can
    # honestly be `nullable: false` from the start.
    dev.add_field(entity, "score", "text", contract_type="string", nullable=False)
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["score"] == {"nullable": False}, row
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "x", "score": None})
    assert excinfo.value.details.get("violated_declaration") == "nullable"


def test_add_field_success_result_carries_a_revision(sessions) -> None:
    """WP-3a rework 3 (real, measured bug): contract `schemas.
    SchemaOperationResult.required` includes `revision` unconditionally --
    not only for `alter_field`, whose own in-process result already
    carried one (`test_alter_field_success_advances_revision_and_round_
    trips` below). A successful `add_field` used to return nothing at all
    (`cell.ApplicationCell.add_field` had no `return` statement, even
    though the backend beneath it already bumped the schema revision) --
    an in-process caller's own `add_field` result could never report one,
    the exact gap `conformance-tests/test_c20_constraint_declaration_
    agreement.py`'s `MitateDB-api` (in-process) plug surfaced."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_before = dev.schema_revision()
    result = dev.add_field(entity, "extra", "text", contract_type="string")
    assert result.get("revision") is not None, result
    assert dev.schema_revision() != revision_before
    assert result.get("revision") == str(dev.schema_revision())


def test_postgres_add_field_nullable_false_on_entity_with_rows_conflicts(app_pg) -> None:
    """Real-PostgreSQL counterpart -- also pins that the existing-row
    scan runs inside the SAME transaction as the (never-executed) DDL:
    a conflicting `add_field` leaves the column entirely absent from
    `information_schema`, not merely absent from this peer's own
    registry."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "addfieldwidgets")
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "existing-row"})
        revision_before = dev.schema_revision()
        with pytest.raises(ConflictError) as excinfo:
            dev.add_field(entity, "score", "text", contract_type="string", nullable=False)
        details = excinfo.value.details
        assert details.get("violated_declaration") == "nullable", details
        assert details.get("field") == "nullable", details
        assert dev.schema_revision() == revision_before
        row = {r["entity"]: r for r in dev.catalog()}[entity]
        assert "score" not in row["fields"], row
        with backend._developer.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
                [entity, "score"],
            )
            (present,) = cur.fetchone()
        backend._developer.commit()
        assert present == 0, "a conflicting add_field must leave the column entirely absent"
    finally:
        backend.close()


def test_postgres_add_field_nullable_false_on_empty_entity_succeeds(app_pg) -> None:
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "addfieldwidgetsempty")
        dev.add_field(entity, "score", "text", contract_type="string", nullable=False)
        row = {r["entity"]: r for r in dev.catalog()}[entity]
        assert row["field_constraints"]["score"] == {"nullable": False}, row
    finally:
        backend.close()


def test_postgres_add_field_success_result_carries_a_revision(app_pg) -> None:
    """Real-PostgreSQL counterpart of `test_add_field_success_result_
    carries_a_revision` above -- pins `backend_postgres.PostgresBackend.
    add_field`'s own same-transaction revision readback (it used to bump
    `_SCHEMA_REVISION_TABLE` via `_bump_schema_revision` but never read
    the new value back, so this method returned nothing at all)."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "addfieldwidgetsrevision")
        revision_before = dev.schema_revision()
        result = dev.add_field(entity, "extra", "text", contract_type="string")
        assert result.get("revision") is not None, result
        assert dev.schema_revision() != revision_before
        assert result.get("revision") == str(dev.schema_revision())
    finally:
        backend.close()


# --- completion condition 7/8: alter_field CONFLICT / success ---


def test_alter_field_conflict_changes_nothing_and_does_not_advance_revision(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "b", "req": "ok", "label": "conflict-row"})
    revision_before = dev.schema_revision()
    catalog_before = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
    count_before = len(runtime.read(entity))
    with pytest.raises(ConflictError) as excinfo:
        dev.alter_field(entity, "status", enum=["a"])
    details = excinfo.value.details
    assert details.get("violated_declaration") in ("enum", "nullable"), details
    # Code review §2 D / 監督裁定 D (2026-09-07): `field` names a POSITION
    # IN THE REQUEST (design D-3 (2)), not the entity field name --
    # `alter_field`'s own request carries `enum`/`nullable` as its OWN
    # top-level keys, so the violated position IS that same key name,
    # identical to `violated_declaration` itself here.
    assert details.get("field") == details.get("violated_declaration"), details
    assert "conflict-row" not in str(details), details
    assert dev.schema_revision() == revision_before
    catalog_after = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
    assert catalog_after == catalog_before
    assert len(runtime.read(entity)) == count_before


def test_alter_field_success_advances_revision_and_round_trips(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_before = dev.schema_revision()
    result = dev.alter_field(entity, "status", enum=["a", "b", "z"])
    assert result.get("revision") is not None
    assert dev.schema_revision() != revision_before
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"]["enum"] == ["a", "b", "z"], row


def test_alter_field_nullable_switch_is_enforced_afterward(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    dev.alter_field(entity, "label", nullable=False)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "a", "req": "ok"})
    assert excinfo.value.details.get("violated_declaration") == "nullable"


# --- completion condition 9: alter_field with field_type ---


def test_alter_field_with_field_type_is_validation_failed_unsupported_field(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field(entity, "status", field_type="integer")
    assert excinfo.value.details.get("violated_declaration") == "unsupported_field"


def test_alter_field_field_type_rejection_runs_inside_the_limit_gate(sessions) -> None:
    """Code review §2 H / 監督裁定 H (2026-09-07): the `field_type`
    rejection now runs INSIDE `_limit_gate` (rate/concurrency/request_
    bytes/operation_depth), the same stage every other `alter_field`
    check runs at -- before this fix it ran BEFORE the gate entirely, so
    an oversized request carrying `field_type` could reach a definitive
    `VALIDATION_FAILED(unsupported_field)` answer without ever being
    measured against `request_bytes`. Verified here by observing WHICH
    denial an oversized `field_type` now produces: `LIMIT_EXCEEDED
    (request_bytes)`, not `VALIDATION_FAILED(unsupported_field)` -- proof
    the `request_bytes` gate now runs FIRST."""
    small_control = ControlPlane(
        "synthetic-test-pepper-0123456789", config=FoundationConfig(max_request_bytes=200))
    small_control.provision_application("app_gate")
    dev_id, dev_secret = small_control.issue_credential("app_gate", Role.DEVELOPER)
    service = MitateDataService(small_control)
    small_dev = service.open_session(dev_secret)
    entity = _make_entity(small_dev, "gatewidgets")
    with pytest.raises(ResourceLimitError) as excinfo:
        small_dev.alter_field(entity, "status", field_type="x" * 100)
    assert excinfo.value.details.get("limit_class") == "request_bytes", excinfo.value.details


# --- completion condition 9b (code review §2 A / 監督裁定 A 2026-09-07):
# alter_field's own enum tri-state (unchanged / cleared / set-replaced) ---


def test_alter_field_omitted_enum_leaves_the_current_enum_unchanged(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    # `status` already declares `enum: ["a", "b"]` (`_make_entity`).
    # Redeclaring only `nullable` (`enum` omitted -- the `UNCHANGED`
    # sentinel default) must leave `status`'s own `enum` untouched.
    dev.alter_field(entity, "req", nullable=True)
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"]["enum"] == ["a", "b"], row
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "z", "req": "ok", "label": "still-enforced"})
    assert excinfo.value.details.get("violated_declaration") == "enum"


def test_developer_session_alter_field_omitting_enum_on_the_same_field_leaves_it_unchanged(sessions) -> None:
    """WP-3a rework 2 (2026-09-07, real measured bug, not the previous
    test's own leg above -- that one redeclares a DIFFERENT field
    (`req`) and only checks `status`'s enum survives, which would hold
    even if the tri-state were broken): `ApplicationDeveloper.alter_
    field` (`cell.py`, the in-process PORT entry point -- distinct from
    `ApplicationCell.alter_field` underneath it) used to default `enum`
    to a bare `None` instead of `backend.UNCHANGED`, so ANY in-process
    caller that omitted `enum` while redeclaring `nullable` on the SAME
    field silently WIPED that field's own existing enum -- confirmed
    empirically before this fix: `status` (declares `enum: ["a", "b"]`
    via `_make_entity`) redeclared with `nullable=True` alone lost its
    enum entirely. `http.py`'s own HTTP dispatch already distinguished
    omission from `null` correctly (`body.get("enum", UNCHANGED)`); this
    was the one remaining in-process entry point that had not."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    dev.alter_field(entity, "status", nullable=True)
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"]["enum"] == ["a", "b"], row
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "not-a-member", "req": "ok", "label": "still-enforced"})
    assert excinfo.value.details.get("violated_declaration") == "enum"


def test_alter_field_explicit_enum_none_clears_the_enum(sessions) -> None:
    """Code review §2 A / 監督裁定 A (2026-09-07): `enum=None`, passed
    EXPLICITLY (distinguishable from omission only because the keyword's
    own default is the `backend.UNCHANGED` sentinel, never a bare
    `None`), clears `status`'s own `enum` entirely -- design D-2 (5)'s
    "sets, replaces or clears" completed. Verified directly against
    `ApplicationDeveloper.alter_field` (the in-process port, per code
    review §2 A / 監督裁定's own instruction: the wire-level `enum: null`
    round trip is a separate HTTP concern, `test_http.py`)."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_before = dev.schema_revision()
    result = dev.alter_field(entity, "status", enum=None)
    assert result.get("revision") is not None
    assert dev.schema_revision() != revision_before
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"] == {"nullable": True}, row
    # The enum is genuinely gone, not merely reported empty: a value that
    # was refused before this call now inserts cleanly.
    runtime.insert(entity, {"status": "not-in-the-old-enum", "req": "ok", "label": "cleared"})
    rows = runtime.read(entity, filters=[Filter("label", "eq", "cleared")])
    assert rows[0]["status"] == "not-in-the-old-enum", rows


def test_alter_field_enum_none_never_conflicts_on_the_cleared_field(sessions) -> None:
    """Clearing `status`'s own `enum` (`nullable` left `UNCHANGED`, still
    `true`, `_make_entity`'s own default) can never itself produce a
    `CONFLICT` -- there is nothing left to violate once the `enum` this
    call establishes is "none at all". A pre-existing row (any value)
    and a subsequent NULL insert (accepted because `nullable` was never
    redeclared away from its `true` default, not because of anything
    `enum=None` itself does) both go through untouched."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "keep"})
    revision_before = dev.schema_revision()
    dev.alter_field(entity, "status", enum=None)
    assert dev.schema_revision() != revision_before
    runtime.insert(entity, {"status": None, "req": "ok", "label": "null-status"})
    assert len(runtime.read(entity)) == 2


# --- code review §2 D / 監督裁定 D (2026-09-07): `details.field` is a
# request-relative path, never a bare entity field name ---


def test_insert_missing_required_field_details_field_is_request_relative_path(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "a", "label": "no-req"})
    # Phase 9 WP-3e rework (裁定 C-21 (B)/監督裁定 N-4, 2026-09-08): this
    # peer's own direct, single-operation `insert()` entry point now
    # occupies request-internal position `operations/0/...`, matching the
    # real wire shape (`http.py::post_mutate` always wraps in an
    # `operations` list) and r2db-api's own `structured.py::_apply`
    # (`values_path = f"operations/{operation_index}/values/"` for every
    # mutation, batched or solo) -- was bare `"values/req"`.
    assert excinfo.value.details.get("field") == "operations/0/values/req", excinfo.value.details


def test_prepare_values_enum_violation_details_field_is_request_relative_path(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.insert(entity, {"status": "not-a-member", "req": "ok", "label": "x"})
    assert excinfo.value.details.get("field") == "operations/0/values/status", excinfo.value.details


def test_update_values_violation_details_field_is_request_relative_path(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"status": "a", "req": "ok", "label": "row-1"})
    with pytest.raises(ValidationError) as excinfo:
        runtime.update(entity, {"status": "not-a-member"}, filters=[Filter("label", "eq", "row-1")])
    assert excinfo.value.details.get("field") == "operations/0/values/status", excinfo.value.details


def test_transact_insert_violation_details_field_includes_operation_index(sessions) -> None:
    """Code review §2 D / 監督裁定 D (2026-09-07): a batch item's own
    violation is attributed to its OWN position in `operations[]`
    (design D-3 (2)'s own example `operations/0/values/label`) -- the
    second of two batch operations here (index 1) is the one that
    violates, and `details.field` must name THAT index, not the first."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.transact([
            {"type": "insert", "collection": entity, "values": {"status": "a", "req": "ok", "label": "ok-row"}},
            {"type": "insert", "collection": entity, "values": {"status": "not-a-member", "req": "ok", "label": "bad-row"}},
        ])
    assert excinfo.value.details.get("field") == "operations/1/values/status", excinfo.value.details
    # Atomic: the whole batch is refused, including the earlier valid item.
    assert len(runtime.read(entity)) == 0


def test_transact_insert_missing_required_field_details_field_includes_operation_index(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        runtime.transact([
            {"type": "insert", "collection": entity, "values": {"status": "a", "req": "ok", "label": "ok-row"}},
            {"type": "insert", "collection": entity, "values": {"status": "a", "label": "missing-req"}},
        ])
    assert excinfo.value.details.get("field") == "operations/1/values/req", excinfo.value.details


# --- code review §2 E / 監督裁定 E (2026-09-07): an unrecognized key in
# one field_constraints entry is refused, never silently dropped ---


def test_field_constraints_unknown_key_is_rejected(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcbadkey", fields={"status": "text"}, field_types={"status": "string"},
            field_constraints={"status": {"enumm": ["a"]}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "request_schema", details
    assert details.get("field") == "field_constraints/status/enumm", details
    assert "fcbadkey" not in {r["entity"] for r in dev.catalog()}, "a rejected field_constraints must create nothing"


# --- completion condition 11: enum_members limit ---


def test_enum_members_limit_exceeded_refuses_before_anything_is_created(sessions) -> None:
    dev, runtime = sessions
    small_control = ControlPlane("synthetic-test-pepper-0123456789", config=FoundationConfig(max_enum_members=3))
    small_control.provision_application("app_small")
    _, dev_secret = small_control.issue_credential("app_small", Role.DEVELOPER)
    service = MitateDataService(small_control)
    small_dev = service.open_session(dev_secret)
    entity = "capped"
    with pytest.raises(ResourceLimitError) as excinfo:
        small_dev.create_entity(
            entity, fields={"status": "text"}, field_types={"status": "string"},
            field_constraints={"status": {"enum": ["a", "b", "c", "d"]}},
        )
    assert excinfo.value.details.get("limit_class") == "enum_members"
    assert entity not in {r["entity"] for r in small_dev.catalog()}, "a LIMIT_EXCEEDED create_entity must create nothing"


def test_enum_members_limit_exceeded_on_add_field_and_alter_field(sessions) -> None:
    dev, runtime = sessions
    small_control = ControlPlane("synthetic-test-pepper-0123456789", config=FoundationConfig(max_enum_members=2))
    small_control.provision_application("app_small2")
    _, dev_secret = small_control.issue_credential("app_small2", Role.DEVELOPER)
    service = MitateDataService(small_control)
    small_dev = service.open_session(dev_secret)
    small_dev.create_entity("capped2", fields={"tag": "text"}, field_types={"tag": "string"})
    with pytest.raises(ResourceLimitError) as excinfo:
        small_dev.add_field("capped2", "status", "text", contract_type="string", enum=["a", "b", "c"])
    assert excinfo.value.details.get("limit_class") == "enum_members"
    assert "status" not in dict(small_dev.catalog()[0]["field_types"])

    small_dev.add_field("capped2", "status2", "text", contract_type="string", enum=["a", "b"])
    with pytest.raises(ResourceLimitError) as excinfo2:
        small_dev.alter_field("capped2", "status2", enum=["a", "b", "c"])
    assert excinfo2.value.details.get("limit_class") == "enum_members"
    row = {r["entity"]: r for r in small_dev.catalog()}["capped2"]
    assert row["field_constraints"]["status2"]["enum"] == ["a", "b"], "a LIMIT_EXCEEDED alter_field must change nothing"


# --- completion condition 12: capability enabled (peer-local companion to C-20) ---


def test_constraint_declarations_capability_is_enabled(sessions) -> None:
    dev, runtime = sessions
    status = runtime.capabilities()["capabilities"]["constraint_declarations"]["status"]
    assert status == "enabled"


def test_create_entity_field_constraints_naming_a_field_not_in_fields_is_refused(sessions) -> None:
    """WP-3a rework 2 (監督裁定 m-1, 2026-09-07): "a declaration naming a
    field the request does not create" is the 4th `constraint_
    declaration` case -- no `declared_type` (the named field is never
    created by this request, so it has none)."""
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "badfc", fields={"a": "text"}, field_types={"a": "string"},
            field_constraints={"not_a_field": {"nullable": False}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "field_constraints/not_a_field", details
    assert "declared_type" not in details, details
    assert "badfc" not in {r["entity"] for r in dev.catalog()}


def test_create_entity_field_constraints_without_fields_is_refused(sessions) -> None:
    """WP-3a closure (監督裁定 2026-09-07, audit `wp3a-closure` §3 G3): a
    `field_constraints` sent without `fields` is a missing-key
    request-shape violation -- `field` names the request's own top-level
    `field_constraints` key (design D-3 (2)); no `declared_type`/
    `observed_type` (D-3 (3): not a violation about a value's own
    type)."""
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity("nofields", fields=None, field_constraints={"id": {"nullable": False}})
    details = excinfo.value.details
    assert details.get("violated_declaration") == "request_schema", details
    assert details.get("field") == "field_constraints", details
    assert "declared_type" not in details, details
    assert "observed_type" not in details, details
    assert "nofields" not in {r["entity"] for r in dev.catalog()}, "a rejected create_entity must create nothing"


def test_field_constraints_nullable_not_a_boolean_is_refused(sessions) -> None:
    """WP-3a closure (監督裁定 2026-09-07, audit §3 G3): a `field_
    constraints.<field>.nullable` that is not a boolean IS a violation
    about a value's own type -- `declared_type`/`observed_type` are
    included (D-3 (3)), unlike the missing-`fields` case above."""
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcbadnullable", fields={"status": "text"}, field_types={"status": "string"},
            field_constraints={"status": {"nullable": "yes"}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "request_schema", details
    assert details.get("field") == "field_constraints/status/nullable", details
    assert details.get("declared_type") == "boolean", details
    assert details.get("observed_type") == "string", details
    assert "fcbadnullable" not in {r["entity"] for r in dev.catalog()}, "a rejected field_constraints must create nothing"


def test_alter_field_nullable_not_a_boolean_is_refused(sessions) -> None:
    """WP-3a closure (監督裁定 2026-09-07, audit §3 G3): `alter_field`'s
    own top-level `nullable`, when not a boolean, is the same kind of
    value-type violation as `field_constraints.nullable` above --
    `field` echoes the request's own top-level `nullable` key."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field(entity, "status", nullable="yes")
    details = excinfo.value.details
    assert details.get("violated_declaration") == "request_schema", details
    assert details.get("field") == "nullable", details
    assert details.get("declared_type") == "boolean", details
    assert details.get("observed_type") == "string", details
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"]["nullable"] is True, "a rejected alter_field must change nothing"


def test_alter_field_unknown_field_is_constraint_declaration(sessions) -> None:
    """WP-3a closure (監督裁定 2026-09-07, audit §3 G3): `alter_field`
    naming a field the entity does not have is `constraint_declaration`
    ("a declaration naming a field the request does not create") --
    `field` echoes the request's own top-level `field` key; no
    `declared_type`/`observed_type` (not a violation about a value's own
    type)."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field(entity, "not_a_real_field", nullable=False)
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "field", details
    assert "declared_type" not in details, details
    assert "observed_type" not in details, details


def test_alter_field_with_neither_enum_nor_nullable_is_refused_and_does_not_advance_revision(sessions) -> None:
    """監督裁定 N-1 (2026-09-07, wp3a-closure2): an `alter_field` carrying
    neither `enum` nor `nullable` declares nothing -- refused with
    `VALIDATION_FAILED` before the schema is touched at all, so the
    schema revision does not advance and the field's own constraints are
    unchanged. `field` is `"operation"` (the whole operation is
    defective, not any single top-level key)."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_before = dev.schema_revision()
    catalog_before = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field(entity, "status")
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "operation", details
    assert "declared_type" not in details, details
    assert "observed_type" not in details, details
    assert dev.schema_revision() == revision_before
    catalog_after = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
    assert catalog_after == catalog_before


def test_alter_field_with_neither_enum_nor_nullable_wins_over_unknown_collection(sessions) -> None:
    """N-1's own refusal runs before any collection/field lookup -- a
    request naming a collection that does not exist at all still answers
    `VALIDATION_FAILED(constraint_declaration/operation)`, never
    `NOT_FOUND`, when it also declares neither `enum` nor `nullable`: the
    request is defective on its own terms regardless of what it names."""
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field("no_such_entity_at_all", "status")
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "operation", details


def test_postgres_alter_field_with_neither_enum_nor_nullable_is_refused(app_pg) -> None:
    """Real-PostgreSQL counterpart of `test_alter_field_with_neither_
    enum_nor_nullable_is_refused_and_does_not_advance_revision` above --
    the refusal happens entirely inside `cell.ApplicationCell.alter_
    field`, before either backend is ever called, so it applies
    identically to both backends; this pins that it is not accidentally
    bypassed for the real Postgres backend specifically."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "pgalterneitherwidgets")
        revision_before = dev.schema_revision()
        catalog_before = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
        with pytest.raises(ValidationError) as excinfo:
            dev.alter_field(entity, "status")
        details = excinfo.value.details
        assert details.get("violated_declaration") == "constraint_declaration", details
        assert details.get("field") == "operation", details
        assert dev.schema_revision() == revision_before
        catalog_after = {r["entity"]: r for r in dev.catalog()}[entity]["field_constraints"]
        assert catalog_after == catalog_before
    finally:
        backend.close()


def test_create_entity_field_constraints_not_an_object_is_refused(sessions) -> None:
    """監督裁定 N-2 (2026-09-07, wp3a-closure2): `field_constraints` that
    is not an object (here, a list) is a `request_schema` violation
    naming the top-level `field_constraints` key -- no `declared_type`/
    `observed_type` (this position is a container the request declares,
    not a value checked against a field's own declared type)."""
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcnotobject", fields={"status": "text"}, field_types={"status": "string"},
            field_constraints=["status"],
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "request_schema", details
    assert details.get("field") == "field_constraints", details
    assert "declared_type" not in details, details
    assert "observed_type" not in details, details
    assert "fcnotobject" not in {r["entity"] for r in dev.catalog()}, "a rejected create_entity must create nothing"


# --- WP-3a rework 2, m-1 (監督裁定, 2026-09-07): a malformed enum
# DECLARATION itself (as opposed to a data VALUE that violates an
# already-accepted one, covered by completion condition 1/2 above) is
# refused as VALIDATION_FAILED + violated_declaration: constraint_
# declaration, field = the request-relative path, declared_type = the
# field's own declared type, observed_type never set. Covers the 4
# cases errors.details_vocabulary's own 11th vocabulary word names (the
# 4th, "a declaration naming a field the request does not create", is
# the test immediately above -- it has no declared_type to report). ---


def test_enum_on_json_typed_field_is_constraint_declaration(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcjson", fields={"payload": "json"}, field_types={"payload": "json"},
            field_constraints={"payload": {"enum": ["a"]}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "field_constraints/payload/enum", details
    assert details.get("declared_type") == "json", details
    assert "observed_type" not in details, details
    assert "fcjson" not in {r["entity"] for r in dev.catalog()}


def test_enum_on_object_typed_field_is_constraint_declaration(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcobject", fields={"payload": "json"}, field_types={"payload": "object"},
            field_constraints={"payload": {"enum": [{"a": 1}]}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("declared_type") == "object", details


def test_enum_on_untyped_field_is_constraint_declaration_via_add_field(sessions) -> None:
    """`field_type` omitted on `add_field` derives the contract type
    `json` (`FOUNDATION_TYPE_TO_CONTRACT_TYPE["json"]`) -- an `enum`
    declared alongside it is refused the same way, `field` reported as
    the bare top-level `enum` key (add_field/alter_field redeclare
    exactly ONE field, so there is no per-field path to build)."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        dev.add_field(entity, "blob", "json", enum=["a"])
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "enum", details
    assert details.get("declared_type") == "json", details
    assert "blob" not in {r["entity"]: r for r in dev.catalog()}[entity]["fields"]


def test_empty_enum_is_constraint_declaration(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcempty", fields={"status": "text"}, field_types={"status": "string"},
            field_constraints={"status": {"enum": []}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "field_constraints/status/enum", details
    assert details.get("declared_type") == "string", details


def test_duplicate_enum_member_is_constraint_declaration(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcdup", fields={"status": "text"}, field_types={"status": "string"},
            field_constraints={"status": {"enum": ["a", "a"]}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("declared_type") == "string", details


def test_enum_member_outside_declared_type_is_constraint_declaration(sessions) -> None:
    dev, runtime = sessions
    with pytest.raises(ValidationError) as excinfo:
        dev.create_entity(
            "fcbadmember", fields={"status": "integer"}, field_types={"status": "integer"},
            field_constraints={"status": {"enum": [1, "not-an-integer"]}},
        )
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "field_constraints/status/enum", details
    assert details.get("declared_type") == "integer", details


def test_enum_member_outside_declared_type_is_constraint_declaration_via_alter_field(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    with pytest.raises(ValidationError) as excinfo:
        dev.alter_field(entity, "status", enum=["a", 1])
    details = excinfo.value.details
    assert details.get("violated_declaration") == "constraint_declaration", details
    assert details.get("field") == "enum", details
    assert details.get("declared_type") == "string", details
    # Non-vacuity: the field's own PRE-EXISTING enum survives a rejected
    # redeclaration attempt.
    row = {r["entity"]: r for r in dev.catalog()}[entity]
    assert row["field_constraints"]["status"]["enum"] == ["a", "b"], row


# ===========================================================================
# Real-PostgreSQL tests -- completion conditions 10 (per-application
# upgrade safety) and 13 (single-transaction existing-row scan), plus the
# developer-connection SELECT-permission実測 (監査照合項目 3).
# ===========================================================================

import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator

from psycopg.conninfo import conninfo_to_dict, make_conninfo

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict | None = None) -> subprocess.CompletedProcess:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    return subprocess.run(command, capture_output=True, text=True)


def _run_psql_ok(dsn: str, path: Path, variables: dict | None = None) -> None:
    result = _run_psql(dsn, path, variables)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_constraints_declaration.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests must not be skipped "
            "(design R-8).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            leftover_databases = [row[0] for row in cur.fetchall()]
            for database in leftover_databases:
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbfc{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_fc_migrations")

    def _rewrite(name: str) -> Path:
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        return out

    rewritten = {
        name: _rewrite(name)
        for name in (
            "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
            "0003_provision_application.sql", "0004_deprovision_application.sql",
            "0009_field_constraints_upgrade.sql",
        )
    }

    try:
        _run_psql_ok(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql_ok(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        upgrade_script=rewritten["0009_field_constraints_upgrade.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _provision(platform, app_id: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql_ok(
        platform.provision_dsn, platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{app_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return types.SimpleNamespace(
        app_id=app_id, database=database, runtime_role=runtime_role, developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def _deprovision(platform, app_id: str) -> None:
    last_error = None
    for attempt in range(8):
        try:
            _run_psql_ok(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    raise last_error


@pytest.fixture
def app_pg(platform) -> Iterator[types.SimpleNamespace]:
    app = _provision(platform, "fc_a")
    try:
        yield app
    finally:
        _deprovision(platform, "fc_a")


def _sessions_for(cell: ApplicationCell, app_id: str):
    developer = ApplicationDeveloper(cell, Principal(app_id, "test-dev", Role.DEVELOPER))
    runtime = ApplicationRuntime(cell, Principal(app_id, "test-rt", Role.RUNTIME))
    return developer, runtime


def test_postgres_backend_enforces_and_round_trips_field_constraints(app_pg) -> None:
    """完了条件 1/4/6 realized against the REAL PostgreSQL backend (not
    only SQLite above) -- also the 監査照合項目 3 実測: `alter_field`'s own
    existing-row scan reads real application DATA over the DEVELOPER
    connection and succeeds with no explicit GRANT beyond table ownership
    (F-6) -- if the developer role lacked SELECT on its own entity table,
    every assertion below would raise `psycopg.errors.InsufficientPrivilege`
    (translated to `ValidationError`/`ConflictError` with a generic
    "storage backend rejected the request" message) instead of succeeding
    or raising the specific `ConflictError` this test expects."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "pgwidgets")

        with pytest.raises(ValidationError) as excinfo:
            runtime.insert(entity, {"status": "z", "req": "ok", "label": "x"})
        assert excinfo.value.details.get("violated_declaration") == "enum"

        runtime.insert(entity, {"status": "a", "req": "ok", "label": "row-b"})
        row = {r["entity"]: r for r in dev.catalog()}[entity]
        assert row["field_constraints"]["status"]["enum"] == ["a", "b"]
        assert row["field_constraints"]["req"]["nullable"] is False

        # 監査照合項目 3 実測 -- alter_field's existing-row SELECT over the
        # developer connection succeeds (developer role SELECTs its own
        # entity table by ownership, F-6): CONFLICT because "row-b" carries
        # "a", excluded by the narrower ["z"] (a value outside the CURRENT
        # rows, chosen so the conflict is genuine).
        revision_before = dev.schema_revision()
        with pytest.raises(ConflictError) as excinfo2:
            dev.alter_field(entity, "status", enum=["z"])
        assert excinfo2.value.details.get("violated_declaration") == "enum"
        assert dev.schema_revision() == revision_before

        result = dev.alter_field(entity, "status", enum=["a", "b", "c"])
        assert result["revision"] is not None
        assert dev.schema_revision() != revision_before
    finally:
        backend.close()


def test_alter_field_constraints_is_a_single_transaction(app_pg) -> None:
    """完了条件 13 (design D-2 実装の形 4, F-6, 監督裁定 S-g): the
    existing-row scan, the registry UPDATE, and the schema-revision bump
    all happen inside ONE `self._developer` transaction -- exactly ONE
    `commit()` call on the developer connection for the whole `backend.
    alter_field_constraints(...)` call itself. If the existing-row scan
    were moved to a separate pre-flight call (the `field_domains`-style
    "read, then DDL in a later transaction" shape `create_collection`/
    `add_field` use, which this method must NOT use), that pre-flight's
    own read would commit its own transaction FIRST, making this count
    >= 2 -- the mutation this test is built to catch (design D-2 実装の形
    4's own disclosed limit: the common suite cannot observe this, C-20
    (6) only sees "nothing changed").

    Calls `backend.alter_field_constraints` DIRECTLY (not `dev.alter_
    field`) -- `ApplicationCell.alter_field`'s own pre-checks (`field_
    domains` for existence, `field_types` for the declared type an `enum`
    is validated against) are legitimate, separate, read-only catalog
    round trips that commit their own transactions independently, and are
    not what this test's own proposition is about; isolating the
    backend call is what actually pins "this ONE method's own tx
    boundary", not an incidental count of every developer-connection
    round trip `dev.alter_field` happens to make."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "txwidgets")
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "tx-row"})

        commit_calls = []
        original_commit = backend._developer.commit

        def _counting_commit():
            commit_calls.append(1)
            return original_commit()

        backend._developer.commit = _counting_commit
        try:
            # Phase 9 WP-3b: `alter_field_constraints` now returns
            # `(revision, descriptor)` (design D-4) -- unpack rather than
            # capture the whole tuple under a name that implies a bare
            # revision.
            new_revision, _descriptor = backend.alter_field_constraints(entity, "status", enum=["a", "b", "z"])
        finally:
            backend._developer.commit = original_commit
        assert new_revision is not None
        assert len(commit_calls) == 1, (
            f"alter_field_constraints made {len(commit_calls)} commit() calls on the developer connection -- "
            "expected exactly 1 (existing-row scan, registry write, and revision bump all inside one "
            "transaction, design D-2 実装の形 4)"
        )
    finally:
        backend.close()


def test_insert_makes_one_merged_registry_round_trip_not_three(app_pg) -> None:
    """Code review §2 C / 監督裁定 C (2026-09-07, P-8/G-4 performance
    finding): a plain, non-conflicting `runtime.insert(...)` makes
    exactly TWO developer-connection round trips against this
    application's own catalog -- one `field_types_and_constraints`
    (the merged `declared_type`/`enum_json`/`nullable` read
    `_check_missing_required_fields` makes and `_prepare_values` reuses,
    `prefetched=`) and one `field_domains` (`_prepare_values`'s own
    value-domain lookup, unmerged -- out of this fix's own scope).
    BEFORE this rework, the identical insert made FOUR: `field_
    constraints` (in `_check_missing_required_fields`), `field_types` +
    `field_constraints` again (`_prepare_values`'s own two, THEN-separate
    calls against the identical `_mdb_field_types` row), and `field_
    domains` -- the `field_constraints` round trip made twice, and
    `field_types`/`field_constraints` never merged despite reading the
    same row (review §2 C's own two findings). `runtime.insert`'s own
    write itself runs on the SEPARATE `_runtime` connection (`backend_
    postgres.PostgresBackend.insert`, no `audit_hook`/developer
    involvement for a plain data insert), so counting `_developer.
    cursor()` invocations isolates exactly the catalog/registry round
    trips this fix targets."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "roundtripwidgets")

        cursor_calls: list = []
        original_cursor = backend._developer.cursor

        def _counting_cursor(*args, **kwargs):
            cursor_calls.append(1)
            return original_cursor(*args, **kwargs)

        backend._developer.cursor = _counting_cursor
        try:
            result = runtime.insert(entity, {"status": "a", "req": "ok", "label": "roundtrip-row"})
        finally:
            backend._developer.cursor = original_cursor
        assert result is not None
        assert len(cursor_calls) == 2, (
            f"a plain insert made {len(cursor_calls)} developer-connection round trips -- "
            "expected exactly 2 (one merged field_types_and_constraints, one field_domains); "
            "before this rework the identical insert made 4 (review §2 C)"
        )
    finally:
        backend.close()


def test_query_path_never_reads_field_constraints(app_pg) -> None:
    """WP-3a rework 2, M-4 相当 (監督裁定, 2026-09-07 -- "query 経路で制約
    を読まない...実測"): `runtime.read`'s own filter binding (`cell.py::
    _bind_filters`) calls `field_types` (declared TYPE, needed to bind a
    filter value's own domain) but never `field_constraints`/`field_
    types_and_constraints` (the `enum`/`nullable` registry, D-2 (3):
    "query の predicate 値は enum を検査しない" -- there being no value
    written for a query, `nullable: false` has nothing to enforce
    either). Pinned by INSTRUMENTING the backend's own constraint-reading
    methods directly (never invoked at all), not merely by counting
    total round trips (a coincidental equal count would not prove
    WHICH methods ran)."""
    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "querynoconstraints")
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "row-1"})

        constraint_calls: list = []
        original_field_constraints = backend.field_constraints
        original_field_types_and_constraints = backend.field_types_and_constraints

        def _counting_field_constraints(*args, **kwargs):
            constraint_calls.append("field_constraints")
            return original_field_constraints(*args, **kwargs)

        def _counting_field_types_and_constraints(*args, **kwargs):
            constraint_calls.append("field_types_and_constraints")
            return original_field_types_and_constraints(*args, **kwargs)

        backend.field_constraints = _counting_field_constraints
        backend.field_types_and_constraints = _counting_field_types_and_constraints
        try:
            rows = runtime.read(entity, filters=[Filter("status", "eq", "a")])
        finally:
            backend.field_constraints = original_field_constraints
            backend.field_types_and_constraints = original_field_types_and_constraints
        assert rows and rows[0]["label"] == "row-1", rows
        assert constraint_calls == [], (
            f"runtime.read made {constraint_calls} constraint-registry calls -- "
            "the query path must never read field_constraints (M-4 相当, D-2 (3))"
        )
    finally:
        backend.close()


def test_alter_field_constraints_lock_table_blocks_concurrent_write(app_pg) -> None:
    """Code review §2 F / 監督裁定 F (2026-09-07): `alter_field_
    constraints` locks its target table `IN SHARE ROW EXCLUSIVE MODE`
    (originally plain `SHARE MODE`, revised by R-35, Phase 10, WP-6d-i
    review -- see the deterministic two-connection serialization test
    below for that scenario) BEFORE scanning its existing rows, inside
    the SAME transaction -- this closes the READ COMMITTED phantom-write
    window a bare single transaction
    (完了条件 13, `test_alter_field_constraints_is_a_single_transaction`
    above) does not, on its own, close: absent the lock, a second
    session could COMMIT a newly-violating row in the gap between this
    scan and this same transaction's own COMMIT.

    Verified here by actually observing the lock, not merely reading the
    SQL text: a background thread runs `alter_field_constraints`, paused
    (a monkeypatched `backend_postgres._execute`) immediately AFTER its
    own `LOCK TABLE` statement executes and before its existing-row scan;
    while it is paused, a second, independent connection attempts a
    concurrent `INSERT` into the SAME entity with a short `lock_timeout`
    and observes `psycopg.errors.LockNotAvailable` -- the write is
    genuinely blocked by the lock this same transaction holds, not
    merely serialized after the fact by transaction isolation alone."""
    from mitatedb_api import backend_postgres as bp_module

    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "lockwidgets")
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "row-1"})

        lock_acquired = threading.Event()
        release_scan = threading.Event()
        original_execute = bp_module._execute

        def _patched_execute(cursor, statement, params=()):
            result = original_execute(cursor, statement, params)
            rendered = statement.as_string(cursor) if hasattr(statement, "as_string") else str(statement)
            if rendered.strip().upper().startswith("LOCK TABLE"):
                lock_acquired.set()
                # Held open until the concurrent-write probe below has run.
                assert release_scan.wait(timeout=10), "test-side release never arrived"
            return result

        bp_module._execute = _patched_execute
        thread_errors: list = []

        def _run_alter_field():
            try:
                backend.alter_field_constraints(entity, "status", enum=["a", "b", "c"])
            except Exception as exc:  # pragma: no cover - surfaced via thread_errors
                thread_errors.append(exc)

        thread = threading.Thread(target=_run_alter_field)
        thread.start()
        try:
            assert lock_acquired.wait(timeout=10), "alter_field_constraints never reached its own LOCK TABLE"
            writer = psycopg.connect(app_pg.runtime_dsn)
            try:
                with writer.cursor() as wcur:
                    wcur.execute("SET lock_timeout = '300ms'")
                    with pytest.raises(psycopg.errors.LockNotAvailable):
                        wcur.execute(
                            sql.SQL("INSERT INTO {} (status, req, label) VALUES (%s, %s, %s)")
                              .format(sql.Identifier(entity)),
                            ["z", "ok", "row-2"],
                        )
            finally:
                writer.rollback()
                writer.close()
        finally:
            release_scan.set()
            thread.join(timeout=10)
            bp_module._execute = original_execute
        assert not thread_errors, thread_errors
        assert thread.is_alive() is False
    finally:
        backend.close()


def test_two_concurrent_add_field_calls_on_same_entity_serialize_without_deadlock(app_pg, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-35 (Phase 10, WP-6d-i review): plain `LOCK TABLE ... IN SHARE
    MODE` does not conflict with itself, so two concurrent `add_field`
    calls declaring `nullable: false` on the SAME entity, from two
    INDEPENDENT developer connections, could both acquire it, then each
    block at their own later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on
    the other's SHARE lock -- a guaranteed mutual wait resolved only by
    PostgreSQL's deadlock detector aborting one side with an error.
    `SHARE ROW EXCLUSIVE` (self-conflicting) instead makes the second
    caller wait AT `LOCK TABLE` until the first commits.

    Verified against a REAL two-connection race (contrast the SQL-text-
    level M-1-style pins elsewhere in this file): two separate
    `PostgresBackend` instances (`backend_a`/`backend_b`, each its own
    developer connection, mirroring the concurrent-writer test above's
    own use of a wholly separate connection) both call `add_field` on
    the SAME entity. `backend_a`'s call is paused (a monkeypatched
    module-level `backend_postgres._execute`) immediately AFTER its own
    `LOCK TABLE` RETURNS and before its `ALTER TABLE`. While it is
    paused, `backend_b`'s `add_field` is issued from the main thread --
    if the two locks conflict, `backend_b`'s own `LOCK TABLE` blocks
    INSIDE `cursor.execute` itself and never reaches the line that would
    record it as returned, so it must not do so within a short window.
    Releasing `backend_a` lets both complete, in sequence, with no
    deadlock error, and the final catalog carries both new fields."""
    from mitatedb_api import backend_postgres as bp_module

    backend_a = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    backend_b = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend_a)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "lockrace")

        real_execute = bp_module._execute
        lock_call_count = {"n": 0}
        lock_acquired = threading.Event()  # backend_a's own LOCK TABLE has returned
        b_lock_started = threading.Event()  # backend_b's LOCK TABLE is about to be issued
        b_lock_returned = threading.Event()  # backend_b's own LOCK TABLE has returned
        release_a = threading.Event()

        def paced_execute(cursor, statement, params=()):
            rendered = statement.as_string(cursor) if hasattr(statement, "as_string") else str(statement)
            is_lock = rendered.strip().upper().startswith("LOCK TABLE")
            my_index = None
            if is_lock:
                lock_call_count["n"] += 1
                my_index = lock_call_count["n"]
                if my_index != 1:
                    b_lock_started.set()
            result = real_execute(cursor, statement, params)
            if is_lock:
                if my_index == 1:
                    lock_acquired.set()
                    assert release_a.wait(timeout=10), "test-side release never arrived"
                else:
                    b_lock_returned.set()
            return result

        monkeypatch.setattr(bp_module, "_execute", paced_execute)
        a_errors: list = []

        def _add_field_a():
            try:
                backend_a.add_field(entity, "field_a", "text", contract_type="string", nullable=False)
            except Exception as exc:  # pragma: no cover - surfaced via a_errors
                a_errors.append(exc)

        thread_a = threading.Thread(target=_add_field_a)
        thread_a.start()
        try:
            assert lock_acquired.wait(timeout=10), "backend_a never reached its own LOCK TABLE"

            b_errors: list = []

            def _add_field_b():
                try:
                    backend_b.add_field(entity, "field_b", "text", contract_type="string", nullable=False)
                except Exception as exc:  # pragma: no cover - surfaced via b_errors
                    b_errors.append(exc)

            thread_b = threading.Thread(target=_add_field_b)
            thread_b.start()
            try:
                assert b_lock_started.wait(timeout=10), "backend_b never reached its own LOCK TABLE"
                assert not b_lock_returned.wait(timeout=0.5), (
                    "backend_b's LOCK TABLE returned while backend_a still holds the lock -- "
                    "the two locks did not conflict (R-35 regression)"
                )
            finally:
                release_a.set()
                thread_b.join(timeout=10)
        finally:
            thread_a.join(timeout=10)

        assert not thread_a.is_alive(), "backend_a's thread never finished -- bounded-wait violated"
        assert not thread_b.is_alive(), "backend_b's thread never finished -- bounded-wait violated"
        assert not a_errors, a_errors
        assert not b_errors, b_errors
        assert b_lock_returned.is_set(), "backend_b's LOCK TABLE never returned even after release"

        catalog = {row["entity"]: row for row in dev.catalog()}
        assert {"field_a", "field_b"}.issubset(set(catalog[entity]["fields"])), catalog[entity]
    finally:
        backend_a.close()
        backend_b.close()


def test_alter_field_fails_safely_on_an_application_missing_the_0009_upgrade(app_pg) -> None:
    """完了条件 10: an application whose own ledger is missing upgrade 9
    (simulated by deleting its own ledger row, mirroring `test_platform_
    upgrades.py`'s own established technique for upgrade 8) refuses every
    storage-touching operation -- `alter_field` included -- with
    `StorageConfigurationError` (F-12, `_guard_pending_platform_upgrades`),
    changing NOTHING: the row this test inserts BEFORE deleting the ledger
    row is still there afterward, unit for unit, and `_mdb_field_types`'
    own `enum_json`/`nullable` columns (already added by `0003` at
    provisioning time, since a real deployment never has a HALF-applied
    `0003`) are untouched -- this proves the FAILURE MODE is "refuse
    safely", not "silently skip the constraint check"."""
    from mitatedb_api.errors import StorageConfigurationError

    backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=backend)
        dev, runtime = _sessions_for(cell, app_pg.app_id)
        entity = _make_entity(dev, "upgwidgets")
        runtime.insert(entity, {"status": "a", "req": "ok", "label": "pre-existing"})
    finally:
        backend.close()

    admin = psycopg.connect(_dsn_with(app_pg.developer_dsn, dbname=app_pg.database), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM public._mdb_platform_upgrades WHERE upgrade_number = 9")
    finally:
        admin.close()

    refusing_backend = PostgresBackend(
        runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn, application_id=app_pg.app_id,
    )
    try:
        cell2 = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=refusing_backend)
        dev2, runtime2 = _sessions_for(cell2, app_pg.app_id)
        with pytest.raises(StorageConfigurationError) as excinfo:
            dev2.alter_field(entity, "status", enum=["a", "z"])
        assert "missing platform upgrade(s)" in str(excinfo.value)
        assert "9" in str(excinfo.value)
    finally:
        refusing_backend.close()

    # Nothing changed: the pre-existing row is untouched, read through a
    # THIRD, non-refusing backend built fresh (no `application_id`, so the
    # F-12 guard never engages -- mirrors `test_platform_upgrades.py::
    # test_cell_open_check_is_skipped_when_no_application_id_is_given`'s
    # own established technique for reading through a refusing app).
    verify_backend = PostgresBackend(runtime_dsn=app_pg.runtime_dsn, developer_dsn=app_pg.developer_dsn)
    try:
        verify_cell = ApplicationCell(app_pg.app_id, FoundationConfig(), backend=verify_backend)
        _, verify_runtime = _sessions_for(verify_cell, app_pg.app_id)
        rows = verify_runtime.read(entity, filters=[Filter("label", "eq", "pre-existing")])
        assert len(rows) == 1, rows
    finally:
        verify_backend.close()
