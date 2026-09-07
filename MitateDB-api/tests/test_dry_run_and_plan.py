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
from mitatedb_api.cell import (ApplicationCell, ApplicationDeveloper, ApplicationRuntime,
                               compute_plan_token, normalize_request_for_plan)
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import (AuthorizationError, DestructiveConfirmationRequired,
                                 PreconditionFailedError)
from mitatedb_api.http import _mutation_digest_item, _mutation_item, _problem_for_exception

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


def test_plan_digest_covers_transaction_not_only_operations(sessions) -> None:
    """WP-3b rework (M-4/G-1): `MutationRequest.transaction` is part of
    what the token commits to, exactly like `budget` immediately above --
    reproduced against the pre-rework digest (`cell.py:1784`'s own
    `request = {"operations": operations}`, never carrying `transaction`
    at all, so this exact scenario used to commit silently). Driven
    through `ApplicationRuntime.transact` itself (unlike `budget`,
    `transaction` names no still-`unavailable` capability -- `http.py::
    post_mutate` already accepts and forwards `"atomic"` today)."""
    dev, runtime = sessions
    entity = _make_entity(dev)

    dry = runtime.transact(
        [{"type": "insert", "collection": entity, "values": {"label": "transaction-row"}}], dry_run=True,
    )
    plan = dry[-1]["plan"]

    with pytest.raises(PreconditionFailedError) as ei:
        runtime.transact(
            [{"type": "insert", "collection": entity, "values": {"label": "transaction-row"}}],
            plan=plan, transaction="atomic",
        )
    assert ei.value.details == {"violated_declaration": "plan"}
    assert runtime.read(entity) == []


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


# ===========================================================================
# Phase 9 WP-3b rework (code review 2026-09-07, 監督裁定 G-1..G-5/F-2..F-8):
# regression tests for the 6 return-to-sender items.
# ===========================================================================


# --- G-2: pin the 3 normalization rules `normalize_request_for_plan` (S-a)
# states -- token equality can never catch a broken rule on its own (M-5:
# `sort_keys=True` -> `False` and loosened `separators`/`ensure_ascii` both
# survived the pre-rework suite at 860 passed), so this asserts the
# canonical BYTES themselves against a known input. ---


def test_normalize_request_for_plan_pins_sort_keys_no_whitespace_and_unescaped_non_ascii() -> None:
    request = {"b": 1, "a": "café", "c": [3, 2, 1]}
    encoded = normalize_request_for_plan(request)
    assert encoded == b'{"a":"caf\xc3\xa9","b":1,"c":[3,2,1]}'
    # Key-order independence: an equal mapping presented with keys in a
    # DIFFERENT insertion order must digest identically (`sort_keys`).
    reordered = {"c": [3, 2, 1], "a": "café", "b": 1}
    assert normalize_request_for_plan(reordered) == encoded
    # Every one of the 3 rules, isolated: (i) sort_keys -- a manually
    # key-sorted `json.dumps` with the SAME separators/ensure_ascii must
    # match exactly. (ii) no insignificant whitespace -- the default
    # `json.dumps` separators (`", "`/`": "`) would NOT match. (iii)
    # non-ASCII left unescaped -- `ensure_ascii=True` would emit `é`
    # instead of the raw UTF-8 bytes for `é`, and would NOT match.
    import json as _json
    assert encoded == _json.dumps(request, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False).encode("utf-8")
    assert encoded != _json.dumps(request, sort_keys=True, ensure_ascii=False).encode("utf-8"), (
        "default (whitespace-carrying) separators must NOT match -- rule (ii) is unpinned otherwise"
    )
    assert encoded != _json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8"), (
        "ensure_ascii=True (the json.dumps default) must NOT match -- rule (iii) is unpinned otherwise"
    )


def test_normalize_request_for_plan_excludes_only_plan_and_dry_run() -> None:
    """G-4: the 2-key exclusion happens INSIDE the helper now, not the
    caller -- `plan` is never askable to include its own digest, and
    `dry_run` always differs between a dry run and the request it plans;
    every other key (`budget`/`transaction`/`confirmation`/`idempotency_
    key` included) is committed to."""
    without = normalize_request_for_plan({"operations": [1], "budget": {"execution_ms": 5}})
    with_plan_and_dry_run = normalize_request_for_plan(
        {"operations": [1], "budget": {"execution_ms": 5}, "plan": "whatever-opaque-value", "dry_run": True},
    )
    assert without == with_plan_and_dry_run
    # But a DIFFERENT `budget` (a real, non-excluded field) changes it.
    different_budget = normalize_request_for_plan({"operations": [1], "budget": {"execution_ms": 6}})
    assert different_budget != without


def test_compute_plan_token_format_is_sha256_hex_dot_revision() -> None:
    """G-3/F-7: `"<sha256hex>.<schema_revision>"` -- the dot separator,
    not `:`."""
    import hashlib
    token = compute_plan_token({"a": 1}, 7)
    digest, _, revision = token.rpartition(".")
    assert revision == "7"
    assert digest == hashlib.sha256(normalize_request_for_plan({"a": 1})).hexdigest()
    assert ":" not in token


# --- M-1 (Major): the add_field plan digest must commit to the CONTRACT-
# level field_type, not this foundation's own internal storage vocabulary
# (which folds object/array/json onto one physical `json` column) ---


def test_add_field_plan_is_refused_when_the_apply_changes_only_the_contract_field_type(sessions) -> None:
    """Reproduces WP-3b review M-1 directly: a dry run taken for
    `field_type: "object"` must NOT validate against an apply presenting
    `field_type: "json"` (or vice versa) -- pre-rework, both foundation-
    mapped to the SAME internal `json` storage type and therefore digested
    identically, so this exact apply used to be silently ACCEPTED, with
    the entity ending up declaring `json`, not the `object` the dry run's
    own `descriptor` had previewed."""
    dev, runtime = sessions
    entity = _make_entity(dev)

    dry = dev.add_field(entity, "payload", "json", contract_type="object", dry_run=True)
    assert dry["descriptor"]["field_types"]["payload"] == "object"
    plan = dry["plan"]

    with pytest.raises(PreconditionFailedError) as ei:
        dev.add_field(entity, "payload", "json", contract_type="json", plan=plan)
    assert ei.value.details == {"violated_declaration": "plan"}

    catalog = {row["entity"]: row for row in dev.catalog()}
    assert "payload" not in catalog[entity]["fields"], "the mismatched apply must not have executed"

    # Positive control: the IDENTICAL contract_type validates and commits.
    real = dev.add_field(entity, "payload", "json", contract_type="object", plan=plan)
    assert real["committed"] is True
    catalog_after = {row["entity"]: row for row in dev.catalog()}
    assert catalog_after[entity]["field_types"]["payload"] == "object"


# --- M-2 (Major): the create_entity/add_field/alter_field plan digest
# must commit to the request as presented, never a resolved/defaulted
# value -- an omitted field_constraints and one spelling out the SAME
# defaults explicitly must NOT collide on one token ---


def test_create_entity_plan_is_refused_when_the_apply_adds_explicit_default_field_constraints(sessions) -> None:
    """Reproduces WP-3b review M-2 directly: a dry run taken WITHOUT
    `field_constraints` must NOT validate against an apply presenting the
    SAME resolved defaults (`{"nullable": True}` for every field) as an
    EXPLICIT `field_constraints` -- pre-rework, `create_collection`
    digested the post-resolution `resolved_constraints` (defaults already
    backfilled) rather than the caller's own raw argument, so an omitting
    request and a defaults-spelling-out one were indistinguishable."""
    dev, runtime = sessions
    entity = "m2_regression_entity"

    dry = dev.create_entity(entity, fields={"label": "text"}, field_types={"label": "string"}, dry_run=True)
    plan = dry["plan"]

    with pytest.raises(PreconditionFailedError) as ei:
        dev.create_entity(
            entity, fields={"label": "text"}, field_types={"label": "string"},
            field_constraints={"label": {"nullable": True}}, plan=plan,
        )
    assert ei.value.details == {"violated_declaration": "plan"}
    assert not any(row["entity"] == entity for row in dev.catalog()), "the mismatched apply must not have executed"

    # Positive control: omitting field_constraints, matching the dry run
    # exactly, validates and commits.
    real = dev.create_entity(entity, fields={"label": "text"}, field_types={"label": "string"}, plan=plan)
    assert real["committed"] is True


# --- M-6 (Medium): the HTTP boundary must build the identical `values`-key
# presence the in-process port always does (`dict(values or {})`, port
# `attempt_mutation_with_result`), so the two plugs' plan digests agree for
# a delete/where-only update ---


def test_http_mutation_item_always_carries_a_values_key_matching_the_in_process_port() -> None:
    """Reproduces WP-3b review M-6 directly, at the unit level (no ASGI
    server needed): pre-rework, `http.py::_mutation_item` only set
    `item["values"]` when the wire body itself carried a `values` key --
    the in-process port's own `attempt_mutation_with_result`/`attempt_
    batch_with_result` (`conformance/conformance_adapter_mitatedb.py`)
    build EVERY item with `"values": dict(values or {})` UNCONDITIONALLY,
    so a `delete`/`where`-only `update` used to digest to two DIFFERENT
    `request_object`s depending on which plug presented it -- a plan taken
    on one plug could never validate on the other (design D-4 (7): "HTTP
    層から来ても in-process port から来ても同じ object になる")."""
    delete_without_values = _mutation_item("entity_x", {"operation": "delete", "where": [
        {"field": "id", "operator": "eq", "value": 1},
    ]})
    assert delete_without_values["values"] == {}, delete_without_values
    assert "values" in delete_without_values

    # And an insert that DOES carry values still passes them through
    # untouched -- this rework only changes the omitted case.
    insert_with_values = _mutation_item("entity_x", {"operation": "insert", "values": {"label": "x"}})
    assert insert_with_values["values"] == {"label": "x"}


# --- G-5(b): a schema operation's OWN plan (not only a mutation's) is
# refused after an unrelated schema change bumps the Application's shared
# revision counter -- peer-local coverage `transact()`'s own staleness
# test (`test_plan_stale_after_schema_change_is_precondition_failed` above)
# does not give: that one takes and re-presents a MUTATION plan, never a
# SCHEMA operation's own. ---


def test_schema_plan_stale_after_unrelated_schema_change_is_precondition_failed(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    other_entity = _make_entity(dev, entity="dryrunwidgets_sibling")

    dry = dev.add_field(entity, "late_field", "text", contract_type="string", dry_run=True)
    plan = dry["plan"]

    # A schema change on a DIFFERENT entity of the SAME Application still
    # invalidates it (design D-4 (7): "対象 entity に無関係な entity への
    # schema 操作も plan を失効させる" -- the revision is per-Application).
    dev.add_field(other_entity, "unrelated", "text")

    with pytest.raises(PreconditionFailedError) as ei:
        dev.add_field(entity, "late_field", "text", contract_type="string", plan=plan)
    assert ei.value.details == {"violated_declaration": "plan"}
    catalog = {row["entity"]: row for row in dev.catalog()}
    assert "late_field" not in catalog[entity]["fields"], "the stale-plan apply must not have executed"


# --- F-3/G-5(e): a schema dry_run writes NO audit event -- durable AND
# legacy sinks both, counted directly (§5 U-2 = (A): "dry_run が実行段階に
# 達した場合、監査行を一切書かない"). `test_dry_run_writes_no_audit_event_
# destructive`/`_non_destructive` above cover `transact()`'s own two audit
# paths; neither exercises a SCHEMA operation's own audit hook
# (`_make_audit_hook(event_class="schema_change", ...)`, `create_
# collection`/`add_field`/`alter_field`'s own `hook = None if dry_run
# else ...`). ---


def test_schema_dry_run_writes_no_audit_event(sessions) -> None:
    durable = ApplicationAuditSink()
    router = make_router(durable)
    cell = ApplicationCell("app_schema_audit", FoundationConfig(), backend=SQLiteBackend(), audit_router=router)
    developer = make_developer(cell, "app_schema_audit")
    developer.create_collection("things", {"id": "integer", "label": "text"})
    # `create_collection` above already wrote its own durable + legacy
    # events -- reset both counters so every assertion below is about
    # what happens FROM this point on.
    durable._events.clear()
    legacy_calls: list[Any] = []
    real_record = cell._ApplicationCell__record  # noqa: SLF001 -- the legacy 6-field-sink emit site itself

    def _counting_record(*args: Any, **kwargs: Any) -> Any:
        legacy_calls.append((args, kwargs))
        return real_record(*args, **kwargs)

    cell._ApplicationCell__record = _counting_record  # noqa: SLF001
    try:
        dry = developer.add_field("things", "new_field", "text", contract_type="string", dry_run=True)
        assert dry["committed"] is False
        assert durable._events == [], (
            f"a schema dry run must write no DURABLE audit event -- {durable._events!r}"
        )
        assert legacy_calls == [], (
            f"a schema dry run must not even ATTEMPT the legacy 6-field-sink record -- {legacy_calls!r}"
        )

        # Positive control: the IDENTICAL real (non-dry-run) add_field DOES
        # write both -- proving the zero counts above are because of
        # `dry_run`, not because this schema operation is inert on audit.
        real = developer.add_field("things", "new_field", "text", contract_type="string")
        assert real["committed"] is True
        assert len(durable._events) == 1
        assert durable._events[0].event_class == "schema_change", durable._events[0]
        assert len(legacy_calls) == 1
    finally:
        cell._ApplicationCell__record = real_record  # noqa: SLF001


# --- F-5: a request presenting NEITHER `plan` NOR `dry_run` makes no
# extra digest computation and no extra schema-revision read -- measured
# directly by call-counting `self._backend.schema_revision()` before and
# after this rework (the design's own pre-existing comment already
# documented the INTENT; this test is the actual round-trip-count proof
# `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md`'s
# own §6.2 mutation table asks for). ---


def test_ordinary_request_without_plan_or_dry_run_makes_no_extra_schema_revision_read() -> None:
    cell = ApplicationCell("app_roundtrip", FoundationConfig(), backend=SQLiteBackend())
    developer = make_developer(cell, "app_roundtrip")
    runtime = make_runtime(cell, "app_roundtrip")

    calls: list[Any] = []
    real_schema_revision = cell._backend.schema_revision  # noqa: SLF001

    def _counting_schema_revision(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return real_schema_revision(*args, **kwargs)

    cell._backend.schema_revision = _counting_schema_revision  # noqa: SLF001
    try:
        # `insert`/`transact` (no `plan`/`dry_run` path touches them at
        # all -- neither ever calls `_schema_revision_uncounted`) make
        # ZERO calls, an absolute (not relative) count -- there is no
        # backend-internal revision bump for either to confound the
        # measurement with, unlike the 3 schema operations below.
        developer.create_collection("roundtrip_things", {"label": "text"})
        calls.clear()
        runtime.insert("roundtrip_things", {"label": "x"})
        assert len(calls) == 0, f"a plain insert must make ZERO schema_revision() calls -- {calls!r}"

        calls.clear()
        runtime.transact([{"type": "insert", "collection": "roundtrip_things", "values": {"label": "y"}}])
        assert len(calls) == 0, f"an ordinary transact (no dry_run/plan) must make ZERO extra calls -- {calls!r}"

        # For `add_field`/`alter_field` (both bump the schema revision as
        # part of their own real DDL, so their OWN baseline call count is
        # a backend-internal implementation detail this test does not
        # assume a fixed number for) the proof is RELATIVE: the ordinary
        # (no `dry_run`/`plan`) call and the `dry_run=True` call for the
        # SAME operation shape must differ by EXACTLY one -- the digest
        # mechanism's own single `_schema_revision_uncounted()` read,
        # neither more (an extra round trip the design's own comment
        # claims does not happen) nor zero (which would mean the counter
        # is not actually sensitive to what this test claims to measure).
        calls.clear()
        developer.add_field("roundtrip_things", "ordinary_field", "text")
        ordinary_add_field_count = len(calls)

        calls.clear()
        developer.add_field("roundtrip_things", "dry_probe_field", "text", dry_run=True)
        dry_add_field_count = len(calls)
        assert dry_add_field_count == ordinary_add_field_count + 1, (
            f"add_field(dry_run=True) must make EXACTLY one MORE schema_revision() call than an ordinary "
            f"add_field -- ordinary={ordinary_add_field_count}, dry_run={dry_add_field_count}"
        )

        # `nullable=True` (not `False`): both `ordinary_field`/`dry_probe_
        # field` were added AFTER the 2 rows above, which therefore carry
        # NULL for them -- `alter_field(..., nullable=False)` would
        # (correctly) refuse with `ConflictError` before ever reaching
        # this test's own measurement; `nullable=True` exercises the SAME
        # existing-row-scan/registry-write/revision-bump path with no
        # conflict to get in the way of what this test actually measures.
        calls.clear()
        developer.alter_field("roundtrip_things", "ordinary_field", nullable=True)
        ordinary_alter_field_count = len(calls)

        # `"ordinary_field"` again (not `"dry_probe_field"`) -- the
        # earlier `add_field(..., dry_run=True)` above rolled its own
        # column back, so `"dry_probe_field"` does not really exist on
        # this entity to `alter_field` against.
        calls.clear()
        developer.alter_field("roundtrip_things", "ordinary_field", nullable=True, dry_run=True)
        dry_alter_field_count = len(calls)
        assert dry_alter_field_count == ordinary_alter_field_count + 1, (
            f"alter_field(dry_run=True) must make EXACTLY one MORE schema_revision() call than an ordinary "
            f"alter_field -- ordinary={ordinary_alter_field_count}, dry_run={dry_alter_field_count}"
        )
    finally:
        cell._backend.schema_revision = real_schema_revision  # noqa: SLF001


# --- F-6: dry_run responses never carry an `assigned_addresses` key at
# all, on every mutation entry point this peer has (not merely the one
# `test_dry_run_insert_matches_real_affected_leaves_no_row_and_no_addresses`
# above already covers) ---


def test_dry_run_transact_update_and_delete_never_carry_assigned_addresses(sessions) -> None:
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"label": "seed"})

    update_dry = runtime.transact(
        [{"type": "update", "collection": entity, "values": {"label": "updated"},
          "filters": [Filter("label", "eq", "seed")]}],
        dry_run=True,
    )
    assert "assigned_addresses" not in update_dry[-1], update_dry[-1]
    assert runtime.read(entity) == [{"label": "seed"}], "the dry-run update must not have executed"


# ===========================================================================
# Phase 9 WP-3b closure (WP-3b acceptance audit, 監督裁定 追補 2 H-1..H-5,
# `{scratchpad}/audit-wp3b.md`/`rulings-r4.md`): regression tests for the
# remaining unfulfilled items -- G-1's 3 residual deviations (A-1/A-2/A-3),
# G-4's load-bearing `default=` hook, and (indirectly, via `test_audit_
# query.py`'s own restored, unfiltered `U == D | N` equality) H-4's
# scanner-exception removal.
# ===========================================================================


# --- H-1/H-2/A-3: the mutation plan digest commits to the CONTRACT-level
# request object (`_mutation_digest_item`, `http.py`), never `_mutation_
# item`'s own internal execution-item shape (`type`/`collection`/`filters`/
# `confirm`) -- key names, an omitted `values` vs an explicit `values: {}`,
# and (via `ApplicationCell.transact`'s new `entity=` keyword) the request's
# own target entity. ---


def test_mutation_digest_item_uses_contract_key_names_never_the_internal_item_shape() -> None:
    """A-3.1: `_mutation_digest_item` (unlike `_mutation_item` immediately
    above it in `http.py`) must NOT rename `operation`->`type`, `where`->
    `filters`, `confirmation`->`confirm`, and must NOT inject the URL path
    `entity` as a `collection` key `MutationRequest`/`Mutation` never
    declare (A-3.2 -- `entity` is threaded separately, via `transact`'s own
    `entity=` keyword, proven by `test_plan_digest_covers_entity_not_only_
    operations` below)."""
    raw = {
        "operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "s"}],
        "destructive": True, "confirmation": "X",
    }
    digest_item = _mutation_digest_item(raw)
    assert digest_item == raw, digest_item
    assert digest_item is not raw, "must be a copy, not the SAME mapping object"
    assert {"type", "collection", "filters", "confirm"}.isdisjoint(digest_item), (
        f"internal execution-item key names leaked into the digest object: {digest_item!r}"
    )


def test_mutation_digest_item_distinguishes_omitted_values_from_explicit_empty_object() -> None:
    """A-3.3 (WP-3b review M-6's own defect class, reopened by the fix that
    closed it): an omitted `values` and an explicit `values: {}` must stay
    two DIFFERENT digest objects -- unlike `_mutation_item`'s own
    unconditional `dict(raw.get("values") or {})` (`test_http_mutation_
    item_always_carries_a_values_key_matching_the_in_process_port` above
    pins that THAT forcing is correct for the EXECUTION item), `_mutation_
    digest_item` must NOT force `values` present."""
    without_values = _mutation_digest_item({
        "operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "s"}],
        "destructive": True, "confirmation": "X",
    })
    with_empty_values = _mutation_digest_item({
        "operation": "delete", "values": {}, "where": [{"field": "label", "operator": "eq", "value": "s"}],
        "destructive": True, "confirmation": "X",
    })
    assert "values" not in without_values
    assert with_empty_values["values"] == {}
    assert without_values != with_empty_values
    token_revision = 1
    assert (compute_plan_token(without_values, token_revision)
            != compute_plan_token(with_empty_values, token_revision)), (
        "an omitted `values` and an explicit `values: {}` must produce DIFFERENT plan tokens"
    )


def test_plan_digest_covers_entity_not_only_operations(sessions) -> None:
    """H-1 (追補 2, WP-3b acceptance audit): the plan digest for a single-
    entity mutation commits to the request's own TARGET entity -- the URL
    path segment `http.py::post_mutate` hoists to `ApplicationCell.
    transact`'s new `entity=` keyword (contract "computed from the request
    itself": the request's own path IS part of "the request itself"). A
    plan taken for entity A must be refused, `PRECONDITION_FAILED`, when
    presented against the SAME body applied to entity B (fail-closed) --
    reproduced here directly against `ApplicationCell.transact` (mirrors
    `test_plan_digest_covers_budget_not_only_operations`'s own style
    above: bypasses the HTTP layer, proves the digest MECHANISM itself).

    `digest_operations` is supplied explicitly here, contract-shaped with
    NO `entity` key of its own (`Mutation` has none -- exactly what
    `http.py::post_mutate`'s own `_mutation_digest_item` builds) -- this
    isolates the TOP-LEVEL `entity=` keyword as the ONLY source of the
    entity signal in the digest; the execution `items`' own `collection`
    key (mutated to differ too, matching a real request) would otherwise
    let `ApplicationCell.transact`'s in-process FALLBACK reconstruction
    (`_reconstruct_digest_operation`, which always embeds `entity` per
    operation from `item["collection"]`) mask a broken top-level `entity=`
    -- confirmed by mutation testing (`{scratchpad}/wp3b-closure.log`):
    dropping the `if entity is not None: digest_request["entity"] = entity`
    line while still passing `digest_operations` here turns this test red,
    but leaves it green if `digest_operations` is omitted (the fallback's
    OWN per-operation `entity` masks that specific mutation)."""
    dev, runtime = sessions
    entity_a = _make_entity(dev, "entity_a_h1")
    entity_b = _make_entity(dev, "entity_b_h1")
    cell = runtime._ApplicationRuntime__cell  # noqa: SLF001
    principal = runtime._ApplicationRuntime__principal  # noqa: SLF001

    digest_ops = [{"operation": "insert", "values": {"label": "h1-row"}}]
    item_a = {"type": "insert", "collection": entity_a, "values": {"label": "h1-row"}}
    dry = cell.transact(principal, [item_a], dry_run=True, entity=entity_a, digest_operations=digest_ops)
    plan = dry[-1]["plan"]

    # Same body, DIFFERENT entity -- must be refused, and must leave no row.
    item_b = {"type": "insert", "collection": entity_b, "values": {"label": "h1-row"}}
    with pytest.raises(PreconditionFailedError) as ei:
        cell.transact(principal, [item_b], plan=plan, entity=entity_b, digest_operations=digest_ops)
    assert ei.value.details == {"violated_declaration": "plan"}
    assert cell.read(principal, entity_b, fields=["label"], filters=None, order_by=None, limit=None) == []

    # Positive control: presenting the SAME entity validates and commits.
    cell.transact(principal, [dict(item_a)], plan=plan, entity=entity_a, digest_operations=digest_ops)
    assert cell.read(principal, entity_a, fields=["label"], filters=None, order_by=None, limit=None) == [
        {"label": "h1-row"}
    ]


# --- H-3 (a)/A-1: the `add_field` plan digest must distinguish an omitted
# `field_type` from an explicit `field_type: "json"` -- both back-fill to
# the SAME foundation storage type, but `field_type` itself must stay
# ABSENT from the digest (never backfilled) when the request omitted it. ---


def test_add_field_plan_digest_distinguishes_omitted_field_type_from_explicit_json(sessions) -> None:
    """A-1 (WP-3b acceptance audit, reproduces `audit_probe_wp3b.py` P-B):
    pre-closure, `http.py::post_schema` passed its OWN backfilled local
    (`field_type`, `"json"` even when the request omitted the key) as
    `add_field`'s `contract_type=` argument, so an omitting dry run's
    `plan` validated against an apply spelling out `field_type: "json"`
    explicitly -- a real, observable peer/contract divergence (G-1's own
    "省略された optional は key ごと無し"). `contract_type=None` here is
    what `http.py` now forwards for an omitted `field_type` (the RAW
    value, never backfilled) -- `dev.add_field(..., contract_type="json")`
    is the explicit-`field_type: "json"` request."""
    dev, runtime = sessions
    entity = _make_entity(dev)

    omitted = dev.add_field(entity, "untyped_field", "json", contract_type=None, dry_run=True)
    explicit_json = dev.add_field(entity, "untyped_field", "json", contract_type="json", dry_run=True)
    assert omitted["plan"] != explicit_json["plan"], (
        "an omitted field_type and an explicit field_type: \"json\" must NOT collide on one plan token"
    )

    # The omitting dry run's plan must be refused against the explicit-
    # "json" apply (and vice versa is exercised by the positive control).
    with pytest.raises(PreconditionFailedError) as ei:
        dev.add_field(entity, "untyped_field", "json", contract_type="json", plan=omitted["plan"])
    assert ei.value.details == {"violated_declaration": "plan"}
    catalog = {row["entity"]: row for row in dev.catalog()}
    assert "untyped_field" not in catalog[entity]["fields"], "the mismatched apply must not have executed"

    # Positive control: the IDENTICAL (omitted) contract_type validates.
    real = dev.add_field(entity, "untyped_field", "json", contract_type=None, plan=omitted["plan"])
    assert real["committed"] is True


# --- H-3 (b)/A-2: `destructive`/`confirmation`/`revision`/`index`/`unique`
# are real `SchemaOperationRequest` properties `add_field`/`alter_field`/
# `create_entity` never read for their own purposes, but the contract still
# requires the plan token to commit to them ("Every other field ... is part
# of what the token commits to") -- `digest_extra` (`http.py::post_schema`,
# forwarded unread) is the fix. ---


def test_schema_plan_digest_covers_digest_extra_destructive_confirmation_revision_index_unique(sessions) -> None:
    """A-2 (WP-3b acceptance audit, reproduces `audit_probe_wp3b.py` P-D):
    pre-closure, none of these 5 keys ever reached the digest at all --
    `dev.add_field`'s own `digest_extra` keyword is what `http.py::post_
    schema` now uses to forward whichever of the 5 the wire request
    actually carried, unread and unvalidated (H-3 (b)); this test drives
    that keyword directly (no ASGI needed), one representative key
    (`revision` -- an always-legal `SchemaOperationRequest` property on
    every operation) standing in for all 5 (each is forwarded through the
    identical `if digest_extra: digest_request.update(digest_extra)` merge
    -- `cell.py::ApplicationCell.add_field`/`.alter_field`/`.create_
    collection`, all 3 sharing this same one-line mechanism)."""
    dev, runtime = sessions
    entity = _make_entity(dev)

    without_extra = dev.add_field(entity, "extra_field", "text", contract_type="string", dry_run=True)
    with_extra = dev.add_field(
        entity, "extra_field", "text", contract_type="string", dry_run=True,
        digest_extra={"revision": "5"},
    )
    assert without_extra["plan"] != with_extra["plan"], (
        "digest_extra must change the plan token -- destructive/confirmation/revision/index/unique are "
        "part of what the token commits to (H-3 (b))"
    )

    with pytest.raises(PreconditionFailedError) as ei:
        dev.add_field(entity, "extra_field", "text", contract_type="string", plan=without_extra["plan"],
                      digest_extra={"revision": "5"})
    assert ei.value.details == {"violated_declaration": "plan"}
    catalog = {row["entity"]: row for row in dev.catalog()}
    assert "extra_field" not in catalog[entity]["fields"], "the mismatched apply must not have executed"

    # Positive control: the IDENTICAL digest_extra validates and commits.
    real = dev.add_field(entity, "extra_field", "text", contract_type="string", plan=with_extra["plan"],
                         digest_extra={"revision": "5"})
    assert real["committed"] is True


# --- G-4: `normalize_request_for_plan`'s own body carries no `default=`
# hook any more -- a genuinely non-JSON-native value (the one this peer's
# own request objects could ever carry, a `Filter` dataclass) now raises
# the SAME bare `TypeError` `json.dumps` itself would raise with no hook at
# all, never silently absorbed. Reproduces WP-3b review B-2 directly (mutation
# M1: the pre-closure `default=_dataclass_default` was load-bearing, not
# the defensive backstop its own docstring claimed). ---


def test_normalize_request_for_plan_has_no_default_hook_for_non_json_native_values() -> None:
    request = {"operations": [{"operation": "update", "where": [Filter("label", "eq", "seed")]}]}
    with pytest.raises(TypeError):
        normalize_request_for_plan(request)


def test_dry_run_transact_succeeds_without_a_default_hook_because_filters_never_reach_the_digest(sessions) -> None:
    """The flip side of the test immediately above: a real `transact(...,
    dry_run=True)` call carrying `Filter` instances in its own `operations`
    (`ApplicationRuntime.transact`'s own public shape, unchanged) must NOT
    raise -- `ApplicationCell.transact`'s own fallback digest builder
    (`_reconstruct_digest_operation`, module level) converts each `Filter`
    to a plain `{"field", "operator", "value"}` dict BEFORE it ever reaches
    `normalize_request_for_plan`, so the `TypeError` the test above proves
    is reachable is never actually hit on this path."""
    dev, runtime = sessions
    entity = _make_entity(dev)
    runtime.insert(entity, {"label": "seed"})
    dry = runtime.transact(
        [{"type": "update", "collection": entity, "values": {"label": "updated"},
          "filters": [Filter("label", "eq", "seed")]}],
        dry_run=True,
    )
    assert dry[-1]["committed"] is False
    assert isinstance(dry[-1]["plan"], str) and dry[-1]["plan"], dry[-1]
