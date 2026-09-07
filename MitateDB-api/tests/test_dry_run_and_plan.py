"""Phase 9 WP-3b peer-local tests (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-4, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-3b): `dry_run`
+ the stateless `plan` token, and the new `errors.PreconditionFailedError`
-- the MitateDB-specific completion conditions and mechanics
`conformance-tests/test_c22_dry_run_and_plan.py` (peer-independent, common
port) cannot itself observe or is not the right place to pin (an in-memory
audit-sink event count, the exact `_problem_for_exception` HTTP mapping,
the plan digest's own scope proven directly against `ApplicationCell.
transact` while `request_budget` is still gated one level up).

Completion conditions 1-10 here are the SAME propositions C-22 checks
against the real, real-time-flipped MitateDB plugs (mirrors `test_
constraints_declaration.py`'s own WP-3a precedent: exercised directly
against `ApplicationCell`/`ApplicationDeveloper`/`ApplicationRuntime`, the
SQLite in-process backend, faster and finer-grained than a full
conformance round trip). Completion condition 11 (`PRECONDITION_FAILED`
same code/details on both the HTTP and in-process paths) is the shared
suite's own territory (C-22 runs against both registered MitateDB plugs);
this file instead pins the narrower, cheaper unit fact the HTTP path
itself depends on -- `http.py::_problem_for_exception`'s own code/status/
message mapping for `errors.PreconditionFailedError` -- without spinning
up a real ASGI/PostgreSQL stack for it.

Non-vacuity (常設規律 1): every test below asserts a real, directly
observed outcome (a real row that was or was not written, a real audit
sink's own event count, an exact `details`/response-body shape) -- never a
bare pass-through.
"""
from __future__ import annotations

from typing import Any

import pytest

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role
from mitatedb_api.application_audit import ApplicationAuditSink
from mitatedb_api.audit_dispatch import AuditRouter
from mitatedb_api.auth import Principal
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import (AuthorizationError, DestructiveConfirmationRequired,
                                 PreconditionFailedError)
from mitatedb_api.http import _problem_for_exception

# ===========================================================================
# Fixtures -- mirrors test_constraints_declaration.py's own WP-3a precedent.
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


def _make_entity(dev, entity="dryrunwidgets"):
    dev.create_entity(entity, fields={"label": "text"}, field_types={"label": "string"})
    return entity


def make_router(sink=None, **kwargs):
    return AuditRouter(sink if sink is not None else ApplicationAuditSink(), **kwargs)


def make_developer(cell, application_id, credential_id="devone"):
    principal = Principal(application_id=application_id, credential_id=credential_id, role=Role.DEVELOPER)
    return ApplicationDeveloper(cell, principal)


def make_runtime(cell, application_id, credential_id="rtone"):
    principal = Principal(application_id=application_id, credential_id=credential_id, role=Role.RUNTIME)
    return ApplicationRuntime(cell, principal)


# --- completion condition 1: refusal-side decision agreement ---


def test_dry_run_matches_real_refusal_for_authorization() -> None:
    """`ApplicationDeveloper` wrapped around a RUNTIME-role principal --
    `cell.py::_require_developer` raises `AuthorizationError` for it,
    developer-only schema operation or not -- the SAME real, present
    denial `dry_run=True` and `dry_run=False` alike must reach, with zero
    side effect either way (design D-4(2): dry_run walks every gate a
    real request does, authorization included)."""
    control = ControlPlane("synthetic-test-pepper-0123456789")
    control.provision_application("app_a")
    service = MitateDataService(control)
    dev_id, dev_secret = control.issue_credential("app_a", Role.DEVELOPER)
    dev = service.open_session(dev_secret)
    entity = _make_entity(dev)

    runtime_id, runtime_secret = control.issue_credential("app_a", Role.RUNTIME)
    runtime_principal = Principal(application_id="app_a", credential_id=runtime_id, role=Role.RUNTIME)
    impostor = ApplicationDeveloper(dev._ApplicationRuntime__cell, runtime_principal)

    with pytest.raises(AuthorizationError):
        impostor.add_field(entity, "impostor_dry", "text", dry_run=True)
    with pytest.raises(AuthorizationError):
        impostor.add_field(entity, "impostor_real", "text", dry_run=False)

    catalog = {row["entity"]: row for row in dev.catalog()}
    assert "impostor_dry" not in catalog[entity]["fields"]
    assert "impostor_real" not in catalog[entity]["fields"]


def test_dry_run_matches_real_refusal_for_destructive_confirmation(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"label": "keep-me"})

    with pytest.raises(DestructiveConfirmationRequired) as dry_ei:
        runtime.transact(
            [{"type": "delete", "collection": entity, "filters": [Filter("label", "eq", "keep-me")]}],
            dry_run=True,
        )
    with pytest.raises(DestructiveConfirmationRequired) as real_ei:
        runtime.transact(
            [{"type": "delete", "collection": entity, "filters": [Filter("label", "eq", "keep-me")]}],
            dry_run=False,
        )
    assert type(dry_ei.value) is type(real_ei.value)
    assert runtime.read(entity) == [{"label": "keep-me"}]


# --- completion conditions 2/3/4: success-side agreement, external
# effects, no assigned_addresses ---


def test_dry_run_insert_matches_real_affected_leaves_no_row_and_no_addresses(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_before = runtime.schema_revision()

    results = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "dry-row"}}], dry_run=True,
    )
    envelope = results[-1]
    assert envelope["committed"] is False
    assert "assigned_addresses" not in envelope
    # `affected` is this port's own conformance-adapter concern
    # (`_mutation_result_to_mapping`); this direct in-process call instead
    # observes the per-item outcome list itself: exactly one real "insert"
    # entry (the row this call WOULD have produced), same length a real
    # apply's own results list carries for the identical request.
    assert len(results) == 2  # 1 real per-item outcome + the dry-run envelope
    assert "rowid" in results[0]

    assert runtime.read(entity) == []  # no row left behind
    assert runtime.schema_revision() == revision_before  # unaffected (data op, not schema)

    real_results = runtime.transact([{"type": "insert", "collection": entity, "values": {"label": "dry-row"}}])
    assert len(real_results) == 1
    assert runtime.read(entity) == [{"label": "dry-row"}]


def test_dry_run_writes_no_audit_event_destructive(sessions) -> None:
    """§5 U-2 = (A): a dry run that reaches execution writes NO audit
    event at all -- observed here directly against the durable pre-commit
    sink a real confirmed delete would otherwise write to (`AuditRouter`/
    `ApplicationAuditSink`, the same pure in-memory machinery `test_
    application_audit.py`'s own SQLite-backed tests use)."""
    durable = ApplicationAuditSink()
    router = make_router(durable)
    cell = ApplicationCell("appone", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    developer = make_developer(cell, "appone")
    developer.create_collection("things", {"id": "integer", "label": "text"})
    runtime = make_runtime(cell, "appone")
    runtime.insert("things", {"id": 1, "label": "keep-me"})
    # `create_collection` above is itself a real, non-dry-run schema
    # operation and legitimately wrote its OWN durable event to this
    # SAME router/sink -- reset the sink here so every assertion below is
    # about what happens FROM this point on.
    durable._events.clear()

    with pytest.raises(DestructiveConfirmationRequired) as ei:
        runtime.transact(
            [{"type": "delete", "collection": "things", "filters": [Filter("id", "eq", 1)]}], dry_run=True,
        )
    phrase = ei.value.details["required_confirmation"]
    # design §5 U-2 = (A): "実行前の拒否は現行どおり監査される" -- an
    # UNCONFIRMED destructive attempt never reaches execution at all (it
    # is refused at the confirmation choke, `_route_delete_confirmation_
    # denial`), so it is audited exactly as a real one would be, dry_run
    # or not; only a CONFIRMED dry run (below) reaches execution and is
    # the one this test's own proposition is about.
    assert len(durable._events) == 1
    assert durable._events[0].reason_code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    durable._events.clear()

    dry_result = runtime.transact(
        [{"type": "delete", "collection": "things", "filters": [Filter("id", "eq", 1)],
          "destructive": True, "confirm": phrase}],
        dry_run=True,
    )
    assert dry_result[-1]["committed"] is False
    assert durable._events == [], (
        f"a CONFIRMED destructive dry run must write no audit event at all -- {durable._events!r}"
    )
    assert runtime.read("things") == [{"id": 1, "label": "keep-me"}]  # nothing deleted

    # Positive control: the identical real (non-dry-run) delete DOES write
    # the durable audit row -- proving `durable._events == []` above is
    # because of `dry_run`, not because this sink/router is inert.
    runtime.transact(
        [{"type": "delete", "collection": "things", "filters": [Filter("id", "eq", 1)],
          "destructive": True, "confirm": phrase}],
    )
    assert len(durable._events) == 1
    assert runtime.read("things") == []


def test_dry_run_writes_no_audit_event_non_destructive(sessions) -> None:
    """Same proposition as the destructive test above, for the OTHER
    audit path a non-destructive batch uses -- `_push_data_operation_
    event`, which dispatches through `AuditRouter.push_buffer_event`
    (buffer-class, not immediately durable, so call-counted here rather
    than read back from the sink, which may not reflect an unflushed
    buffer yet)."""
    durable = ApplicationAuditSink()
    router = make_router(durable)
    cell = ApplicationCell("apptwo", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    developer = make_developer(cell, "apptwo")
    developer.create_collection("widgets", {"label": "text"})
    runtime = make_runtime(cell, "apptwo")

    calls: list[Any] = []
    real_push = router.push_buffer_event

    def _counting_push(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return real_push(*args, **kwargs)

    router.push_buffer_event = _counting_push
    try:
        runtime.transact([{"type": "insert", "collection": "widgets", "values": {"label": "x"}}], dry_run=True)
        assert calls == [], "a non-destructive dry run must not even ATTEMPT a buffer-class audit event"

        runtime.transact([{"type": "insert", "collection": "widgets", "values": {"label": "x"}}])
        assert len(calls) == 1, "the identical REAL insert must still push its one buffer-class event"
    finally:
        router.push_buffer_event = real_push


# --- completion condition 5: schema dry run descriptor + PRE-apply revision ---


def test_schema_dry_run_descriptor_matches_post_apply_and_revision_is_pre_apply(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    revision_r = dev.add_field(entity, "sibling", "text")["revision"]

    dry = dev.add_field(entity, "new_field", "text", contract_type="string", dry_run=True)
    assert dry["committed"] is False
    assert dry["revision"] == revision_r, "a dry-run schema op must report the PRE-apply (current) revision"
    assert "new_field" in dry["descriptor"]["fields"]
    assert dry["descriptor"]["field_types"]["new_field"] == "string"

    catalog_after_dry = {row["entity"]: row for row in dev.catalog()}
    assert "new_field" not in catalog_after_dry[entity]["fields"], "a dry-run add_field left a real field behind"

    real = dev.add_field(entity, "new_field", "text", contract_type="string")
    assert real["descriptor"]["fields"] == dry["descriptor"]["fields"]
    assert real["descriptor"]["field_types"] == dry["descriptor"]["field_types"]
    assert int(real["revision"]) == int(revision_r) + 1, "the dry run must not itself have advanced the revision"


# --- completion conditions 6/7/8/9: plan determinism, validity, staleness
# (schema change), mismatch (different body) ---


def test_plan_is_deterministic_and_valid_against_unchanged_schema(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    kwargs = dict(type="insert", collection=entity, values={"label": "plan-row"})

    dry1 = runtime.transact([dict(kwargs)], dry_run=True)[-1]
    dry2 = runtime.transact([dict(kwargs)], dry_run=True)[-1]
    plan = dry1["plan"]
    assert plan, "a dry run must carry a 'plan'"
    assert dry2["plan"] == plan, "two dry runs of the identical request must return the identical plan"

    real = runtime.transact([dict(kwargs)], plan=plan)
    assert real[0].get("rowid") is not None or "rowid" in real[0]
    assert runtime.read(entity) == [{"label": "plan-row"}]


def test_plan_stale_after_schema_change_is_precondition_failed(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    kwargs = dict(type="insert", collection=entity, values={"label": "stale-row"})
    plan = runtime.transact([dict(kwargs)], dry_run=True)[-1]["plan"]

    dev.add_field(entity, "unrelated", "text")  # advances the Application's own schema revision

    with pytest.raises(PreconditionFailedError) as ei:
        runtime.transact([dict(kwargs)], plan=plan)
    assert ei.value.details == {"violated_declaration": "plan"}
    assert runtime.read(entity) == [], "the stale-plan apply must not have executed"


def test_plan_mismatch_different_body_is_precondition_failed(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    plan = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "body-a"}}], dry_run=True,
    )[-1]["plan"]

    with pytest.raises(PreconditionFailedError) as ei:
        runtime.transact([{"type": "insert", "collection": entity, "values": {"label": "body-b"}}], plan=plan)
    assert ei.value.details == {"violated_declaration": "plan"}
    assert runtime.read(entity) == []


def test_plan_never_required_real_request_omitting_it_still_executes(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.transact([{"type": "insert", "collection": entity, "values": {"label": "no-plan"}}])
    assert runtime.read(entity) == [{"label": "no-plan"}]


# --- completion condition 10 (digest scope): a budget-only change under
# the SAME plan is also refused -- proof the digest is not operations-
# only. Driven directly against `ApplicationCell.transact` (bypassing
# `ApplicationRuntime`'s own still-active `budget` provisional gate,
# WP-3d territory) -- the digest/plan MECHANISM this WP builds is what is
# under test here, not whether `budget` is itself a usable request field
# yet (it is not, until WP-3d) ---


def test_plan_digest_covers_budget_not_only_operations(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    cell = runtime._ApplicationRuntime__cell  # noqa: SLF001 -- direct backend-level digest proof, see docstring above
    principal = runtime._ApplicationRuntime__principal  # noqa: SLF001

    item = {"type": "insert", "collection": entity, "values": {"label": "budget-row"}}
    dry_results = cell.transact(principal, [item], dry_run=True)
    plan = dry_results[-1]["plan"]

    # The SAME plan, the SAME operations, but a request object that ALSO
    # carries `budget` this time -- if the digest were `operations`-only,
    # this would silently commit; it must instead refuse.
    with pytest.raises(PreconditionFailedError) as ei:
        cell.transact(principal, [dict(item)], plan=plan, budget={"execution_ms": 1_000_000})
    assert ei.value.details == {"violated_declaration": "plan"}
    assert cell.read(principal, entity, fields=["label"], filters=None, order_by=None, limit=None) == []


# --- unit coverage for completion condition 11's own HTTP half (the
# shared C-22 test itself is what proves the in-process/HTTP AGREEMENT,
# run against both registered MitateDB plugs; this pins the narrower,
# ASGI/PostgreSQL-free fact the HTTP path's own mapping table depends on)
# ---


def test_precondition_failed_http_mapping() -> None:
    exc = PreconditionFailedError(
        "The plan token does not match this request and the current schema state.",
        details={"violated_declaration": "plan"},
    )
    response = _problem_for_exception(exc, "req-123")
    assert response.status_code == 412
    body = response.body
    import json as _json
    payload = _json.loads(body)
    assert payload["code"] == "PRECONDITION_FAILED"
    assert payload["details"] == {"violated_declaration": "plan"}
    assert payload["request_id"] == "req-123"
    # SI-10: no row value/SQL/internal name -- the fixed, static message,
    # never `str(exc)`.
    assert payload["message"] == "The declared precondition no longer holds."
