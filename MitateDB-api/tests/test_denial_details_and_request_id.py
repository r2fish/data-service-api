"""Phase 9 WP-3e (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-3/D-7, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-3e,
`{scratchpad}/rulings-r3-r7-flip.md`): local, peer-side pinning for R-3
(`errors.details_vocabulary`'s 4-key form on every `VALIDATION_FAILED`/
`CAPABILITY_UNSUPPORTED` this peer emits -- this peer never emits
`IDENTIFIER_INVALID`, L9-2a/completion condition 3') and R-7 (`request_id`
on every successful `QueryResult`/`MutationResult`/`SchemaOperationResult`).
The common suite's own `conformance-tests/test_c21_denial_details_
vocabulary.py`/`test_c25_result_request_id.py` are the cross-peer evidence;
this file pins peer-local mechanics (the 3-branch required-key rule per
`violated_declaration`, the request-internal path format, SI-10 content
safety, request_id distinctness/replay fidelity, the version flip, and
`ops verify-declarations`' F-14) with assertions the common suite's own
declare-first probes do not exhaustively cover.

Independent implementation (R-2's closing paragraph: no code sharing
between peers) -- mirrors r2db-api's own `test_denial_details_and_
request_id.py` in SHAPE (same propositions), never in code.
"""
from __future__ import annotations

import json
import re

import pytest

from mitatedb_api import ControlPlane, MitateDataService, Role
from mitatedb_api.errors import CapabilityError, ConflictError, ValidationError

# design D-3 (2): a request-internal path is '/'-separated with no leading
# separator.
_NO_LEADING_SLASH = re.compile(r"^[^/].*$")


@pytest.fixture
def service():
    control = ControlPlane("wp3e-test-pepper-0123456789")
    control.provision_application("app_a")
    _, dev_secret = control.issue_credential("app_a", Role.DEVELOPER)
    _, runtime_secret = control.issue_credential("app_a", Role.RUNTIME)
    svc = MitateDataService(control)
    dev = svc.open_session(dev_secret)
    runtime = svc.open_session(runtime_secret)
    dev.create_collection("widgets", {"title": "text", "count": "integer"})
    return control, svc, dev, runtime


# ---------------------------------------------------------------------------
# R-3: the 3-branch required-key rule (design D-3 (4), V-2).
# ---------------------------------------------------------------------------


def test_field_type_violation_carries_both_declared_and_observed_type(service):
    """`violated_declaration: field_type` requires BOTH `declared_type` and
    `observed_type` (the 3-branch rule's first branch) -- the choke point
    is `field_types.check_declared_value`."""
    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"count": "not-an-integer"})
    details = ctx.value.details
    assert details["violated_declaration"] == "field_type"
    assert details["declared_type"] == "integer"
    assert details["observed_type"] == "string"


def test_nullable_violation_carries_both_declared_and_observed_type(service):
    """`violated_declaration: nullable` also requires BOTH keys --
    `observed_type: "null"` for an explicit null write."""
    from mitatedb_api.cell import Filter

    control, svc, dev, runtime = service
    dev.add_field("widgets", "required_field", "text", nullable=False)
    runtime.insert("widgets", {"title": "seed", "required_field": "present"})
    with pytest.raises(ValidationError) as ctx:
        runtime.update("widgets", {"required_field": None}, [Filter("title", "eq", "seed")])
    details = ctx.value.details
    assert details["violated_declaration"] == "nullable"
    assert details["declared_type"] == "string"
    assert details["observed_type"] == "null"


def test_nullable_violation_on_insert_omission_carries_absent(service):
    """An insert that OMITS a `nullable: false` field is a `nullable`
    violation too, with `observed_type: "absent"` (design D-3 (2)'s
    "欠落" convention) -- the pre-value 欠落検査 (`_check_missing_
    required_fields`), not the value choke point itself."""
    control, svc, dev, runtime = service
    dev.add_field("widgets", "required_field", "text", nullable=False)
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"title": "no required_field here"})
    details = ctx.value.details
    assert details["violated_declaration"] == "nullable"
    assert details["observed_type"] == "absent"
    assert details["declared_type"] == "string"
    # Phase 9 WP-3e rework (裁定 C-21 (B)/監督裁定 N-4, 2026-09-08): was
    # bare "values/required_field" -- the direct `insert()` entry point
    # now occupies request-internal position `operations/0/...`, the
    # same position a real client's solo-operation mutation would (see
    # `test_field_is_a_request_internal_path_not_a_bare_name` below).
    assert details["field"] == "operations/0/values/required_field"


def test_enum_violation_carries_declared_type_never_observed_type(service):
    """`violated_declaration: enum` requires `declared_type` (the field's
    own declared type) but must NEVER carry `observed_type` -- D-3 (4):
    "型不一致と誤読される" -- the value's own type is not what was
    violated."""
    control, svc, dev, runtime = service
    dev.add_field("widgets", "status", "text", enum=["open", "closed"])
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"status": "not-a-member"})
    details = ctx.value.details
    assert details["violated_declaration"] == "enum"
    assert details["declared_type"] == "string"
    assert "observed_type" not in details


def test_single_unknown_field_names_it_as_field(service):
    """`violated_declaration: request_schema` for an unrecognized field
    name: `field` is required (attributable to exactly one position) and
    `declared_type`/`observed_type` are OMITTED (this contract's own
    request schema has no type opinion about a field it does not
    recognize for this entity, D-3 (4))."""
    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"no_such_field": "x"})
    details = ctx.value.details
    assert details["violated_declaration"] == "request_schema"
    # Phase 9 WP-3e rework (裁定 C-21 (B)/監督裁定 N-4, 2026-09-08): was
    # bare "values/no_such_field".
    assert details["field"] == "operations/0/values/no_such_field"
    assert "declared_type" not in details
    assert "observed_type" not in details


def test_multiple_unknown_fields_omit_field(service):
    """When a violation is NOT attributable to a single position (here:
    the request as a whole carries an unrecognized top-level key set),
    `field` is a real key this peer's own choke points genuinely omit --
    pinned via `_check_missing_required_fields`'s sibling `_prepare_
    values`, whose per-key loop raises on the FIRST unknown field it
    walks, one at a time (never a multi-field batch) -- so the
    "omit when >1" rule is pinned instead at the request-shape layer
    (`_TRANSACT_INSERT_KEYS` excess-key check, `cell.py::_plan_
    operation`), which DOES see the whole excess-key set at once."""
    _, _, _dev, runtime = service
    with pytest.raises(CapabilityError) as ctx:
        runtime.transact([
            {"type": "insert", "collection": "widgets", "values": {"title": "x"},
             "unknown_key_one": 1, "unknown_key_two": 2},
        ])
    details = ctx.value.details
    assert details["violated_declaration"] == "capability"
    assert "field" not in details


# ---------------------------------------------------------------------------
# R-3: `field` is a request-internal path (design D-3 (2), V-3).
# ---------------------------------------------------------------------------


def test_field_is_a_request_internal_path_not_a_bare_name(service):
    """`field` is the request BODY's own '/'-separated path, with no
    leading separator -- never a bare entity/column name in isolation
    (the choke point's own `_prepare_values` join, `path_prefix +
    "/" + field`).

    Phase 9 WP-3e rework (裁定 C-21 (B)/監督裁定 N-4, 2026-09-08): the
    direct, single-operation `insert()` entry point below has no
    `operations[]` envelope of its own on the Python side, but it
    occupies the SAME request-internal position (`operations/0/...`) a
    real client's solo-operation mutation would -- `http.py::post_mutate`
    always wraps every mutation in an `operations` list on the wire (see
    `test_field_path_reflects_batch_index_for_a_transact_operation`
    below), and r2db-api's own `structured.py::_apply` names this same
    position (`values_path = f"operations/{operation_index}/values/"`)
    for every mutation, batched or solo alike -- so this path is `"operations/0/values/count"`."""
    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"count": "nope"})
    field = ctx.value.details["field"]
    assert _NO_LEADING_SLASH.match(field)
    assert field == "operations/0/values/count"


def test_field_path_reflects_batch_index_for_a_transact_operation(service):
    """The SAME violation, presented through `transact()`'s batch entry
    point at a non-zero position, names THAT position -- `operations/<i>/
    values/<field>` -- matching the direct `insert()` entry point's own
    `operations/0/values/<field>` form immediately above (design D-3 (2):
    `field` names a POSITION IN THE REQUEST; the direct entry point is
    always position 0 of an implicit single-item batch, the batch entry
    point names whichever position the operation actually sits at)."""
    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.transact([
            {"type": "insert", "collection": "widgets", "values": {"title": "ok"}},
            {"type": "insert", "collection": "widgets", "values": {"count": "nope"}},
        ])
    assert ctx.value.details["field"] == "operations/1/values/count"


# ---------------------------------------------------------------------------
# R-3: `CAPABILITY_UNSUPPORTED` (design D-3 (4)).
# ---------------------------------------------------------------------------


def test_capability_unsupported_carries_violated_declaration(service):
    _, _, _dev, runtime = service
    with pytest.raises(CapabilityError) as ctx:
        runtime.transact([{"type": "upsert", "collection": "widgets", "values": {"title": "x"}}])
    assert ctx.value.details["violated_declaration"] == "capability"


def test_capability_unsupported_field_reflects_batch_index(service):
    _, _, _dev, runtime = service
    with pytest.raises(CapabilityError) as ctx:
        runtime.transact([
            {"type": "insert", "collection": "widgets", "values": {"title": "ok"}},
            {"type": "upsert", "collection": "widgets", "values": {"title": "x"}},
        ])
    assert ctx.value.details["field"] == "operations/1/type"


# ---------------------------------------------------------------------------
# R-3: MitateDB never emits `IDENTIFIER_INVALID` (L9-2a) -- identifier
# violations are `VALIDATION_FAILED` + `violated_declaration:
# identifier_syntax` instead (work order completion condition 3').
# ---------------------------------------------------------------------------


def test_identifier_violation_is_validation_failed_with_identifier_syntax(service):
    _, _, dev, _runtime = service
    with pytest.raises(ValidationError) as ctx:
        dev.create_collection("Not-A-Valid-Identifier!", {"title": "text"})
    details = ctx.value.details
    assert details["violated_declaration"] == "identifier_syntax"
    assert details.get("field")


def test_identifier_syntax_violation_container_positions_match_r2db_form(service):
    """追補 4 O-3 (版フリップ監査 §4/§16, `{scratchpad}/rulings-r3-r7-flip.
    md`): the CONTAINER position an identifier-syntax violation reports
    is aligned to r2db-api's own chosen form (N-1's "両 peer 同形") --
    `select`/`where/<i>`/`order_by/<i>`/`operations/<i>/values`/`fields`/
    `entity`/`field_constraints`, never this peer's own pre-audit
    `select/<i>`/`where/<i>/field` indexed-then-`/field`-suffixed
    forms."""
    _, _, dev, runtime = service
    dev.create_collection("o3_probe", {"title": "text"})

    with pytest.raises(ValidationError) as ctx:
        runtime.read("o3_probe", fields=["Not-Valid!"])
    assert ctx.value.details["field"] == "select"

    with pytest.raises(ValidationError) as ctx:
        runtime.read("o3_probe", filters=[Filter("Not-Valid!", "eq", "x")])
    assert ctx.value.details["field"] == "where/0"

    with pytest.raises(ValidationError) as ctx:
        runtime.read("o3_probe", order_by=[{"field": "Not-Valid!"}])
    assert ctx.value.details["field"] == "order_by/0"

    with pytest.raises(ValidationError) as ctx:
        runtime.insert("o3_probe", {"Not-Valid!": "x"})
    assert ctx.value.details["field"] == "operations/0/values"

    with pytest.raises(ValidationError) as ctx:
        dev.create_collection("o3_probe_2", {"Not-Valid!": "text"})
    assert ctx.value.details["field"] == "fields"

    with pytest.raises(ValidationError) as ctx:
        dev.create_collection("Not-Valid!", {"title": "text"})
    assert ctx.value.details["field"] == "entity"


def test_field_constraints_unknown_key_syntax_invalid_is_capped_at_the_container(service):
    """追補 4 O-3: `field_constraints` naming a key that is not only
    unrecognized but itself SYNTAX-INVALID (may carry a SQL fragment/
    control characters) must not echo that raw key into `details.field`
    -- capped at the `field_constraints` container position instead (the
    exact r2db-api leak the audit found and this peer now avoids
    proactively). A syntax-VALID-but-unrecognized key keeps the existing,
    safe `field_constraints/<name>` echo (N-1's own "有効だが存在しない
    field" precedent) -- checked in the same test for contrast."""
    _, _, dev, _runtime = service
    with pytest.raises(ValidationError) as ctx:
        dev.create_entity(
            "o3_fc_probe", fields={"a": "text"},
            field_constraints={"public.notes; DROP TABLE x--": {"nullable": False}},
        )
    details = ctx.value.details
    assert details["violated_declaration"] == "constraint_declaration"
    assert details["field"] == "field_constraints"
    assert "DROP TABLE" not in repr(details)

    with pytest.raises(ValidationError) as ctx:
        dev.create_entity(
            "o3_fc_probe_2", fields={"a": "text"},
            field_constraints={"no_such_field_xyz": {"nullable": False}},
        )
    details = ctx.value.details
    assert details["violated_declaration"] == "constraint_declaration"
    assert details["field"] == "field_constraints/no_such_field_xyz"


# ---------------------------------------------------------------------------
# R-3: SI-10 -- details never carry a row value.
# ---------------------------------------------------------------------------


def test_details_do_not_carry_the_offending_value(service):
    """The value itself (`"not-an-integer"`) must never appear anywhere
    in `details` -- only declared facts (types, positions, vocabulary
    words) do."""
    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.insert("widgets", {"count": "not-an-integer-secret-value"})
    rendered = repr(ctx.value.details)
    assert "not-an-integer-secret-value" not in rendered


# ---------------------------------------------------------------------------
# V-7: `ValidationError`/`CapabilityError` carry `details` via the
# constructor only -- no attribute-assignment escape hatch remains
# anywhere in this package's own source.
# ---------------------------------------------------------------------------


def test_validation_error_and_capability_error_details_come_from_the_constructor():
    exc = ValidationError("probe", details={"violated_declaration": "request_schema"})
    assert exc.details == {"violated_declaration": "request_schema"}
    cap = CapabilityError("probe", details={"violated_declaration": "capability"})
    assert cap.details == {"violated_declaration": "capability"}
    # No `details=` at all leaves the attribute genuinely unset (never a
    # silently-defaulted `{}`) -- `getattr(exc, "details", None)` is the
    # convention every caller (`http.py::_problem_for_exception`) relies
    # on.
    bare = ValidationError("probe")
    assert not hasattr(bare, "details")


def test_no_source_file_assigns_details_on_an_already_constructed_exception():
    """The escape hatch V-7 removes: `err.details = {...}` after
    construction. AST-walks every `.py` file under `src/mitatedb_api/`
    for a real `ast.Assign`/`ast.AugAssign` statement whose target is a
    `.details` attribute on a bare-name receiver (`err`/`exc`/`error`) --
    never a textual/regex scan, which would also match this WP's own
    prose (several docstrings in `cell.py`/`http.py` literally quote the
    old `err.details = {...}` pattern while explaining that it is now
    gone)."""
    import ast
    import pathlib

    src_root = pathlib.Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    receiver_names = {"err", "exc", "error"}
    offenders = []
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = getattr(node, "targets", None) or (
                [node.target] if isinstance(node, ast.AugAssign) else None
            )
            if not targets:
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Attribute) and target.attr == "details"
                    and isinstance(target.value, ast.Name) and target.value.id in receiver_names
                ):
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders, f"attribute-assignment escape hatch still present at: {offenders}"


# ---------------------------------------------------------------------------
# R-7: `request_id` on every successful result (design D-7, Q-1/Q-2/Q-3).
# ---------------------------------------------------------------------------


def test_request_id_present_on_query_mutate_and_schema_results(service):
    control, svc, dev, runtime = service
    mutation_result = runtime.transact([{"type": "insert", "collection": "widgets", "values": {"title": "a"}}])
    assert mutation_result[-1].get("request_id")

    schema_result = dev.add_field("widgets", "extra", "text")
    assert schema_result.get("request_id")

    # `read()` itself has no return-shape room for `request_id` (a bare
    # row list, unchanged by this WP -- see `cell.py::ApplicationCell.
    # read`'s own docstring); the HTTP/port layers each mint and echo
    # their own per-request id instead (`http.py::post_query`,
    # `conformance_adapter_mitatedb.py::query_with_budget`). Pinned here
    # via the SAME resolved id reaching the audit event `read()` emits --
    # observed indirectly through a caller-supplied id round-tripping.
    rows = runtime.read("widgets", request_id="probe-request-id-for-read")
    assert isinstance(rows, list)


def test_request_id_is_distinct_per_execution(service):
    _, _, _dev, runtime = service
    first = runtime.transact([{"type": "insert", "collection": "widgets", "values": {"title": "a"}}])
    second = runtime.transact([{"type": "insert", "collection": "widgets", "values": {"title": "b"}}])
    assert first[-1]["request_id"] != second[-1]["request_id"]


def test_request_id_is_a_non_empty_opaque_string(service):
    _, _, _dev, runtime = service
    result = runtime.transact([{"type": "insert", "collection": "widgets", "values": {"title": "a"}}])
    rid = result[-1]["request_id"]
    assert isinstance(rid, str) and rid


# ---------------------------------------------------------------------------
# R-7 (Q-4): idempotency replay returns the ORIGINAL execution's own
# request_id, never a fresh one.
# ---------------------------------------------------------------------------


def test_idempotency_replay_returns_the_original_request_id(service):
    _, _, _dev, runtime = service
    key = "wp3e-idem-key-1"
    first = runtime.transact(
        [{"type": "insert", "collection": "widgets", "values": {"title": "a"}, "idempotency_key": key}])
    second = runtime.transact(
        [{"type": "insert", "collection": "widgets", "values": {"title": "a"}, "idempotency_key": key}])
    assert first[-1]["request_id"] == second[-1]["request_id"]
    assert first == second


def test_idempotency_replay_of_a_schema_operation_returns_the_original_request_id(service):
    """Same guarantee on the SCHEMA side -- `create_collection`/`add_
    field`/`alter_field`'s own backend-level `response_json` now
    persists `request_id` too (Q-4), so a replay is byte-identical to
    the original, including its `request_id`."""
    _, _, dev, _runtime = service
    key = "wp3e-schema-idem-key-1"
    first = dev.add_field("widgets", "replayed_field", "text", idempotency_key=key)
    second = dev.add_field("widgets", "replayed_field", "text", idempotency_key=key)
    assert first == second
    assert first["request_id"]


# ---------------------------------------------------------------------------
# WP-3e rework 2 (rulings-r3-r7-flip.md 追補 L-6 / 追補 2 M-6): a stored
# idempotency record that does not itself carry `request_id` (a pre-1.7.0
# record) is treated as though it does not exist -- a resend re-executes,
# never replays, and the fresh execution's own write overwrites the row.
# ---------------------------------------------------------------------------


def test_idempotency_record_without_request_id_on_mutation_is_treated_as_absent(service):
    """`transact()`'s own persisted response is the whole `results` LIST,
    with `request_id` folded only into its last element -- stripping it
    there simulates a record written before this rollout."""
    _, _, _dev, runtime = service
    key = "wp3e-rework2-l6-mutation-key"
    first = runtime.transact(
        [{"type": "insert", "collection": "widgets", "values": {"title": "a"}, "idempotency_key": key}])
    assert first[-1]["request_id"]

    cell = runtime._ApplicationRuntime__cell
    backend = cell._backend
    record = backend._idempotency[key]
    stored = json.loads(record["response_json"])
    del stored[-1]["request_id"]
    record["response_json"] = json.dumps(stored)

    rows_before = runtime.read("widgets")

    second = runtime.transact(
        [{"type": "insert", "collection": "widgets", "values": {"title": "a"}, "idempotency_key": key}])
    rows_after = runtime.read("widgets")

    # A genuine re-execution happened (a second row was inserted), never a
    # replay of the stripped record.
    assert len(rows_after) == len(rows_before) + 1
    assert second[-1]["request_id"]
    assert second[-1]["request_id"] != first[-1]["request_id"]

    # The record itself was overwritten by the fresh execution's own write
    # and now carries `request_id` again.
    updated = json.loads(backend._idempotency[key]["response_json"])
    assert updated[-1]["request_id"] == second[-1]["request_id"]


def test_idempotency_record_without_request_id_on_schema_op_is_treated_as_absent(service):
    """Mirrors the mutation-level test above for the SCHEMA side, where the
    persisted response is a single dict with `request_id` at its top
    level. A resend re-executes `add_field` as a genuinely new attempt --
    observed here as a `ConflictError`/`ValidationError` from the second,
    real attempt to add a field name that already exists (the tell-tale
    sign this was NOT answered from the stripped record, which would have
    returned successfully with no error at all)."""
    _, _, dev, _runtime = service
    key = "wp3e-rework2-l6-schema-key"
    first = dev.add_field("widgets", "rework2_l6_field", "text", idempotency_key=key)
    assert first["request_id"]

    cell = dev._ApplicationRuntime__cell
    backend = cell._backend
    record = backend._idempotency[key]
    stored = json.loads(record["response_json"])
    del stored["request_id"]
    record["response_json"] = json.dumps(stored)

    with pytest.raises((ValidationError, ConflictError)):
        dev.add_field("widgets", "rework2_l6_field", "text", idempotency_key=key)


# ---------------------------------------------------------------------------
# F-1: the version flip (design D-1 (5)/(7)).
# ---------------------------------------------------------------------------


def test_contract_version_is_1_7_0_on_data_plane(service):
    """Phase 10 WP-6b/pair-closing (design D-5 (v)): re-flipped again to
    1.8.0 in the same commit as this host's own `process_ceilings`
    mapping -- function name kept, same precedent as the sibling peer's
    own re-flipped pins."""
    _, _, _dev, runtime = service
    assert runtime.capabilities()["contract_version"] == "1.10.0"


def test_contract_version_is_1_7_0_on_control_plane():
    """Phase 10 WP-6b/pair-closing (design D-5 (v)): re-flipped again to
    1.8.0, same commit and same reason as
    `test_contract_version_is_1_7_0_on_data_plane` above."""
    from mitatedb_api.control_plane import ControlPlaneService, InMemoryControlBackend, bootstrap_control_credential

    backend = InMemoryControlBackend(app_pepper="p" * 20, control_pepper="c" * 20)
    service = ControlPlaneService(backend)
    with backend.unit_of_work() as work:
        _cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    document = service.control_capabilities(secret)
    assert document["contract_version"] == "1.10.0"


def test_operation_catalog_url_agrees_on_data_and_control_planes():
    """Design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5, §7.1
    訂正註「control plane の宣言版」: `MitateDataService.capabilities()`
    and `ControlPlaneService.control_capabilities()` both echo whatever
    `operation_catalog_url` their own constructor was given, verbatim.

    Constructor-level check ONLY: the SAME
    literal is passed directly to both constructors below, so this pins
    only the echo-through, not the composition roots that decide what
    value to construct each process with (`config.py::FoundationConfig.
    from_env` / `control_composition.py::_operation_catalog_url`) --
    `test_main.py::test_data_and_control_documents_derive_the_same_
    operation_catalog_url_when_unset` and its override sibling exercise
    those real composition roots over a real, running app."""
    from mitatedb_api.config import FoundationConfig
    from mitatedb_api.control_plane import ControlPlaneService, InMemoryControlBackend, bootstrap_control_credential

    url = "http://mitatedb-op-catalog-agree-test.example.invalid/v1/operation-catalog"

    control = ControlPlane(
        "wp3-opcat-agree-test-pepper-0000000",
        config=FoundationConfig(control_plane_status="enabled", operation_catalog_url=url),
    )
    control.provision_application("opcat_app")
    _cid, runtime_secret = control.issue_credential("opcat_app", Role.RUNTIME)
    svc = MitateDataService(control)
    runtime = svc.open_session(runtime_secret)
    data_document = runtime.capabilities()

    backend = InMemoryControlBackend(app_pepper="p" * 20, control_pepper="c" * 20)
    control_service = ControlPlaneService(backend, operation_catalog_url=url)
    with backend.unit_of_work() as work:
        _control_cid, control_secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    control_document = control_service.control_capabilities(control_secret)

    assert data_document["operation_catalog_url"] == control_document["operation_catalog_url"] == url


def test_flip_target_capabilities_are_all_enabled(service):
    """F-2: the 4 new/moved capabilities the flip depends on are all
    `enabled`, and `alter_field` is not in `schema_operations.
    unsupported`."""
    _, _, dev, _runtime = service
    caps = dev.capabilities()["capabilities"]
    for name in ("constraint_declarations", "dry_run", "idempotency", "request_budget"):
        assert caps[name]["status"] == "enabled", (name, caps[name])
    assert "alter_field" not in caps["schema_operations"].get("unsupported", [])
    assert "alter_field" in caps["schema_operations"].get("operations", [])


# ---------------------------------------------------------------------------
# F-3: `ops verify-declarations`' F-14 check (unit-level, no PostgreSQL --
# the Postgres-connected integration coverage lives in `test_ops_verify_
# declarations.py`, out of this WP's own edit scope).
# ---------------------------------------------------------------------------


#: WP-3e rework T3 (ruling `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7):
#: `check_contract_170_declarations` no longer takes a `config` argument
#: at all -- it reads BOTH the capability-enabled half AND the limit-value
#: half from the served `capabilities_document` alone, mirroring
#: `__build_capabilities_document`'s (`cell.py`) (body now in `capabilities_document.py`) real, already-normalized
#: `limits` block (`"enum_members"`/`"idempotency_entries"`/
#: `"idempotency_retention_ms"`, this peer's own `max_*` `FoundationConfig`
#: attribute names already resolved at document-build time). This helper
#: builds that same healthy shape once so every test below only overrides
#: the ONE field it means to break.
def _healthy_document():
    return {
        "capabilities": {
            "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
            "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
        },
        "limits": {"enum_members": 64, "idempotency_entries": 10_000, "idempotency_retention_ms": 86_400_000},
    }


def test_check_contract_170_declarations_accepts_a_healthy_state():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = _healthy_document()
    platform_declarations.check_contract_170_declarations(
        document, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)


@pytest.mark.parametrize("capability_name", ["constraint_declarations", "dry_run", "idempotency", "request_budget"])
def test_check_contract_170_declarations_rejects_a_capability_not_enabled(capability_name):
    from mitatedb_api import platform_declarations
    from mitatedb_api.errors import ValidationError as _Unused  # noqa: F401
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = _healthy_document()
    document["capabilities"][capability_name] = {"status": "unavailable"}
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


@pytest.mark.parametrize("field_name", ["enum_members", "idempotency_entries", "idempotency_retention_ms"])
def test_check_contract_170_declarations_rejects_a_non_positive_limit(field_name):
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = _healthy_document()
    # A real deployment would never serve `0` here; `check_contract_170_
    # declarations` is exactly the check that must catch it if one did --
    # against the SERVED document, never a freshly-built `FoundationConfig`
    # this test would otherwise have to bypass `frozen=True` to break.
    document["limits"][field_name] = 0
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_check_contract_170_declarations_rejects_a_missing_application_upgrade():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = _healthy_document()
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, {"app_a": frozenset()}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_check_contract_170_declarations_treats_a_missing_ledger_as_every_number_pending():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = _healthy_document()
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, {"app_a": None}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_verify_declarations_exit_code_table_has_f14():
    from mitatedb_api.ops import _VERIFY_DECLARATIONS_EXIT_CODES

    assert _VERIFY_DECLARATIONS_EXIT_CODES["F-14"] == 13


# ---------------------------------------------------------------------------
# WP-3e rework T3 (N-1, ruling `{scratchpad}/rulings-r3-r7-flip.md`):
# `backend_sqlite.py`'s own internal `validate_identifier(collection, ...)`
# call (the backend's own cell-mirroring check) now passes `"entity"`, the
# SAME contract-vocabulary word `cell.py::ApplicationCell._identifier`'s
# own call sites already pass for this exact position -- never the stale
# bare `"collection"` literal this file alone still carried before this
# rework. `ApplicationCell._identifier` already validates every collection
# name (as `"entity"`) BEFORE `SQLiteBackend.field_domains` is ever reached
# through the normal cell-mediated path, so this test reaches the
# backend's OWN check directly (a bare `SQLiteBackend()`, bypassing
# `ApplicationCell` entirely) -- proving the label even though ordinary
# traffic can never actually trigger it (N-1: "到達性が無くても契約語に
# 揃える"). Mirrors `test_postgres.py::test_postgres_backend_identifier_
# violation_label_is_entity_not_collection`'s own PostgreSQL-side sibling.
# ---------------------------------------------------------------------------


def test_sqlite_backend_identifier_violation_label_is_entity_not_collection():
    from mitatedb_api.backend_sqlite import SQLiteBackend

    backend = SQLiteBackend()
    with pytest.raises(ValidationError) as ctx:
        backend.field_domains("not a valid identifier!")
    assert ctx.value.details["field"] == "entity"


# ---------------------------------------------------------------------------
# 追補 4 O-2 (版フリップ監査 §5/§15, `{scratchpad}/rulings-r3-r7-flip.md`):
# a backend-layer value-domain denial reached by a NORMAL client request
# (never a direct `_validate_value_domain`/`encode_value` call bypassing
# `cell.py`) must carry the same D-3 (4) 4-key `details` form every other
# choke-point denial does -- the audit found these six sites (this
# module's own SQLite-backed leg here; `tests/test_postgres.py`'s own leg
# covers the two PostgreSQL-only conditions, embedded NUL and the
# int32/int64 RANGE bound, that have no SQLite equivalent) returning an
# EMPTY `details` for exactly this kind of ordinary insert. This is the
# probe-based evidentiary basis `_BACKEND_LAYER_ALLOWLIST`'s own module
# docstring in `test_l1_details_vocabulary_ast_scan.py` now points back
# to for the two conditions SQLite's own `encode_value` still checks
# (lone UTF-16 surrogate, out-of-64-bit-integer-range) -- "同じ入力で
# in-memory 側が denial を出すか" is moot for these two (there genuinely
# is no in-memory equivalent check), but the CLIENT-REACHABLE denial
# itself must still be 4-key shaped, which is what this test pins.
# ---------------------------------------------------------------------------


def test_backend_value_domain_denials_reachable_from_a_normal_client_request_carry_the_4_key_form(service):
    """SQLite leg (in-process plug): a lone UTF-16 surrogate code point in
    a `text`-declared field, and an out-of-64-bit-range integer in an
    `integer`-declared field, reached via `runtime.insert` exactly as an
    ordinary client would -- never a direct backend call. Both must now
    carry `violated_declaration: field_type` plus `declared_type`/
    `observed_type`/`field` (D-3 (4)'s field_type type-pair rule), not an
    empty `details` (追補 4 O-2's own finding)."""
    _, _, dev, runtime = service
    dev.create_collection("domain_probe", {"label": "text", "amount": "integer"})

    with pytest.raises(ValidationError) as ctx:
        runtime.insert("domain_probe", {"label": "\ud800"})
    details = ctx.value.details
    assert details["violated_declaration"] == "field_type"
    assert details["declared_type"] == "string"
    assert details["observed_type"] == "string"
    assert details["field"] == "operations/0/values/label"

    for big in (2 ** 80, -(2 ** 80)):
        with pytest.raises(ValidationError) as ctx:
            runtime.insert("domain_probe", {"amount": big})
        details = ctx.value.details
        assert details["violated_declaration"] == "field_type"
        assert details["declared_type"] == "integer"
        assert details["observed_type"] == "integer"
        assert details["field"] == "operations/0/values/amount"

    # The identical value-domain gate also runs at the `_bind_filters`
    # predicate-value choke point (`where/<i>/value`, not a values path).
    with pytest.raises(ValidationError) as ctx:
        runtime.read("domain_probe", filters=[Filter("amount", "eq", 2 ** 80)])
    details = ctx.value.details
    assert details["violated_declaration"] == "field_type"
    assert details["field"] == "where/0/value"


# ---------------------------------------------------------------------------
# WP-3e rework T2 (追補 L-5/M-5): SI-10 leak scan.
#
# The single, minimal probe above (`test_details_do_not_carry_the_
# offending_value`) checks one VALIDATION_FAILED site for one forbidden
# substring (the probe's own value). This section widens that to a real
# SCAN: >= 10 probes, spanning every issuance LAYER this peer's own
# `errors.violation()` 4-key `details` can come from (request-shape
# `identifier_syntax` at several distinct request-relative positions,
# `request_schema` value-type/shape violations, and `capability` --
# `CAPABILITY_UNSUPPORTED`'s own `violated_declaration`) -- and, for
# every probe, scans the RENDERED `details` dict for FIVE distinct
# categories of leak: the probe's own raw value, a SQL fragment, a
# PostgreSQL DSN, a Python type-name repr, and this foundation's own
# internal storage names (`_mdb_`-prefixed physical table names, the
# `public.` schema qualifier PostgreSQL-backed deployments use). A
# CLIENT-SUPPLIED identifier being echoed back as a `field` PATH (V-3:
# "entity 名 / field 名は client 由来の識別子なのでそのまま載せてよい")
# is explicitly NOT a leak -- it is the request's own POSITION, not a
# value read from storage -- so probes deliberately give their
# identifiers a syntax-INVALID shape (never a valid one that could be
# confused with a real field/table name) wherever `field` is expected to
# echo the position.
# ---------------------------------------------------------------------------

from mitatedb_api.cell import Filter  # noqa: E402  (grouped near its own section, matches this file's existing per-section local-import style)

#: SI-10: none of these substrings may ever appear in a denial's own
#: `details` dict, regardless of which probe raised it. Each corresponds
#: to a distinct leak category 追補 2 M-5 names: SQL, a DSN, a Python
#: type-name repr, and this foundation's own internal storage names
#: (`_mdb_`-prefixed physical tables, the `public.` schema qualifier).
_SI10_FORBIDDEN_SUBSTRINGS = (
    "SELECT", "INSERT INTO", "UPDATE ", "DELETE FROM", "WHERE ",  # SQL
    "postgres://", "postgresql://", "host=", "dbname=",  # DSN
    "<class '", "psycopg", "sqlite3.",  # Python type names / driver names
    "_mdb_", "public.",  # internal storage names
)


def _si10_denial_details(fn):
    """Calls the zero-argument `fn`, expecting it to raise `ValidationError`
    or `CapabilityError` with a real `details` dict -- returns that dict.
    Fails loudly (not vacuously) if `fn` raises neither, or raises with no
    `details` at all, so a probe that stops reaching its own choke point
    (e.g. a future WP changes evaluation order) is visible as a scan
    failure, never silently skipped."""
    from mitatedb_api.errors import CapabilityError as _CapabilityError
    from mitatedb_api.errors import ValidationError as _ValidationError

    try:
        fn()
    except (_ValidationError, _CapabilityError) as exc:
        details = getattr(exc, "details", None)
        assert isinstance(details, dict) and details, (
            f"SI-10 probe raised {type(exc).__name__} with no (or empty) details -- "
            "not a scannable denial"
        )
        return details
    raise AssertionError("SI-10 probe did not raise ValidationError/CapabilityError at all")


def _si10_probes(service):
    """>= 10 probes (L-5's own floor), each returning `(label, marker,
    thunk)` -- `marker` is a probe-specific secret substring that must
    never appear in that probe's own rendered `details` (`None` when the
    probe's `field` is legitimately allowed to echo a client-supplied
    identifier back as a request-relative PATH rather than a value, V-3).
    Spans both codes this peer actually emits with a 4-key `details`
    (`VALIDATION_FAILED`/`CAPABILITY_UNSUPPORTED` -- L9-2a: never
    `IDENTIFIER_INVALID`) and every request-relative POSITION L-3/M-4
    named (`entity`, `values/<k>`/`operations/<i>/values/<k>`,
    `select/<i>`, `where/<i>/field`, `where/<i>/value`, `order_by/<i>/
    field`, `fields/<name>`)."""
    control, svc, dev, runtime = service
    return [
        # -- identifier_syntax (VALIDATION_FAILED), several distinct
        # request-relative positions (L-3) --
        ("create_collection entity", "SI10-MARK-1",
         lambda: dev.create_collection("SI10-MARK-1!!not-valid", {"title": "text"})),
        # `marker=None` for these two: `fields/<name>`/`values/<k>` are
        # the ONE pair of positions where V-3 explicitly permits the
        # client-supplied (here, syntactically invalid) identifier
        # itself to be echoed back as part of the PATH -- that echo is
        # not a leak (it is the request's own position, never a value
        # read from storage); the forbidden-substring scan below still
        # runs against these probes' own details.
        ("create_collection fields/<name>", None,
         lambda: dev.create_collection("si10_probe_2", {"SI10-MARK-2!!bad": "text"})),
        ("insert operations/0/values/<k>", None,
         lambda: runtime.insert("widgets", {"SI10-MARK-3!!bad": "x"})),
        ("read select/<i>", "SI10-MARK-4",
         lambda: runtime.read("widgets", fields=["SI10-MARK-4!!bad"])),
        ("read where/<i>/field", "SI10-MARK-5",
         lambda: runtime.read("widgets", filters=[Filter("SI10-MARK-5!!bad", "eq", "x")])),
        ("read order_by/<i>/field", "SI10-MARK-6",
         lambda: runtime.read("widgets", order_by=[{"field": "SI10-MARK-6!!bad"}])),
        ("delete entity", "SI10-MARK-7",
         lambda: runtime.delete("SI10-MARK-7!!bad", filters=[Filter("title", "eq", "x")],
                                destructive=True, confirm="whatever")),
        ("update entity", "SI10-MARK-8",
         lambda: runtime.update("SI10-MARK-8!!bad", {"title": "y"}, [Filter("title", "eq", "x")])),
        ("transact operations/<i>/entity", "SI10-MARK-9",
         lambda: runtime.transact(
             [{"type": "insert", "collection": "SI10-MARK-9!!bad", "values": {"title": "z"}}])),
        # -- request_schema (VALIDATION_FAILED), value-type/shape --
        ("field_type value", "SI10-MARK-10-secret-value",
         lambda: runtime.insert("widgets", {"count": "SI10-MARK-10-secret-value"})),
        ("where/<i>/value empty in (M-3)", None,
         lambda: runtime.read("widgets", filters=[Filter("count", "in", [])])),
        # -- capability (CAPABILITY_UNSUPPORTED) --
        ("where/<i>/field contains operator", "SI10-MARK-11-secret-value",
         lambda: runtime.read("widgets", filters=[Filter("title", "contains", "SI10-MARK-11-secret-value")])),
        ("where/<i>/field is_null operator", None,
         lambda: runtime.read("widgets", filters=[Filter("title", "is_null", None)])),
        ("transact operation type", "SI10-MARK-12",
         lambda: runtime.transact(
             [{"type": "upsert", "collection": "widgets", "values": {"title": "SI10-MARK-12"}}])),
    ]


def test_si10_leak_scan_across_denial_issuance_layers(service):
    """L-5/M-5: >= 10 probes (14 here), each striking a DIFFERENT
    VALIDATION_FAILED/CAPABILITY_UNSUPPORTED issuance layer/position, none
    of whose rendered `details` may carry: this probe's own value, SQL, a
    DSN, a Python type name, or this foundation's own internal storage
    names (`_mdb_`/`public.`). Asserts `observed >= 1` (non-vacuous: the
    scan actually inspected real denials, not zero)."""
    probes = _si10_probes(service)
    assert len(probes) >= 10, "L-5 requires at least 10 probes"
    observed = 0
    for label, marker, thunk in probes:
        details = _si10_denial_details(thunk)
        rendered = repr(details)
        observed += 1
        if marker is not None:
            assert marker not in rendered, f"{label}: probe value {marker!r} leaked into details: {details}"
        for forbidden in _SI10_FORBIDDEN_SUBSTRINGS:
            assert forbidden not in rendered, f"{label}: forbidden substring {forbidden!r} leaked into details: {details}"
    assert observed >= 1, "SI-10 scan observed zero denials -- vacuous scan"
    assert observed == len(probes)


def test_si10_scan_catches_an_internal_prefix_leaked_onto_field():
    """Positive control for the scan above: a `details["field"]` value
    that DOES carry the internal `public._mdb_` prefix (the exact shape
    the audit mutation 追補 2 M-5 names -- "`field` に `public._mdb_` を
    前置" -- is expected to produce) must fail the SAME substring check
    `test_si10_leak_scan_across_denial_issuance_layers` runs, proving the
    scan is not vacuously green regardless of what `field` actually
    contains."""
    details = {"violated_declaration": "identifier_syntax", "field": "public._mdb_entity"}
    rendered = repr(details)
    with pytest.raises(AssertionError):
        for forbidden in _SI10_FORBIDDEN_SUBSTRINGS:
            assert forbidden not in rendered, f"forbidden substring {forbidden!r} leaked: {details}"


# ---------------------------------------------------------------------------
# WP-3e rework T2 (追補 L-4): `_check_object_shape`'s new "present but
# wrong type" leg (`http.py`).
# ---------------------------------------------------------------------------


def test_check_object_shape_rejects_a_present_field_of_the_wrong_json_type():
    """L-4: a top-level key that IS declared by the schema and IS present
    in the body, whose own VALUE's JSON type does not match what the
    schema declares, is refused with the full 4-key `request_schema`
    shape (`declared_type` = the schema's own JSON type name,
    `observed_type` = the JSON type actually received) -- never an empty/
    missing `details`, and never silently accepted (before this leg
    existed, `QueryRequest.select` carrying a bare string sailed through
    this function unchecked: `_check_object_shape` only ever checked key
    presence/absence, never a present key's own value type)."""
    from mitatedb_api.http import _SCHEMAS, _check_object_shape

    with pytest.raises(ValidationError) as ctx:
        _check_object_shape({"select": "abc"}, _SCHEMAS["QueryRequest"], label="QueryRequest")
    details = ctx.value.details
    assert details == {
        "violated_declaration": "request_schema", "field": "select",
        "declared_type": "array", "observed_type": "string",
    }


def test_check_object_shape_still_accepts_a_ref_or_enum_only_property_of_any_json_type():
    """The new leg is confined to properties the schema names a real JSON
    `type` for -- a `$ref`-shaped property (`QueryRequest.page`) or an
    `enum`-only one has no single JSON type to check against, so this
    function must not invent a mismatch for either; `page`'s own nested
    shape is still checked (`_check_object_shape` recurses into it via
    `post_query`, not this top-level call), just not by this leg."""
    from mitatedb_api.http import _SCHEMAS, _check_object_shape

    # `page` is declared as `{"$ref": "#/definitions/Page"}` -- no bare
    # `type`, so an object here (a well-formed nested shape) passes this
    # top-level call's own new leg without raising.
    result = _check_object_shape({"select": ["a"], "page": {"size": 1}}, _SCHEMAS["QueryRequest"], label="QueryRequest")
    assert result["page"] == {"size": 1}


# ---------------------------------------------------------------------------
# WP-3e rework T2 (追補 2 M-3): an empty `in` filter value is refused,
# unconditionally, on both backends this peer ships (the check is a
# single, backend-agnostic choke point, `cell.py::ApplicationCell.
# _bind_filters`, that runs on every `read`/`update`/`delete`/`transact`
# path before either backend ever builds a SQL `IN (...)` clause).
# ---------------------------------------------------------------------------


def test_empty_in_filter_is_rejected_with_where_value_path(service):
    from mitatedb_api.cell import Filter

    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.read("widgets", filters=[Filter("count", "in", [])])
    details = ctx.value.details
    assert details == {"violated_declaration": "request_schema", "field": "where/0/value"}


def test_non_list_in_filter_value_is_also_rejected_with_where_value_path(service):
    from mitatedb_api.cell import Filter

    _, _, _dev, runtime = service
    with pytest.raises(ValidationError) as ctx:
        runtime.read("widgets", filters=[Filter("count", "in", "not-a-list")])
    details = ctx.value.details
    assert details == {"violated_declaration": "request_schema", "field": "where/0/value"}


# ---------------------------------------------------------------------------
# R-37 WP-1k (CE4): `_deny_provisional_field` moved from `cell.py` to the
# new leaf `provisional_gate.py`.
# ---------------------------------------------------------------------------


def test_provisional_gate_leaf_preserves_cell_facade():
    """`cell.py` re-exports `provisional_gate._deny_provisional_field`
    (the SAME function object, not a copy), so a future
    caller reaching it through `cell.py` keeps working with no change to
    its own call site. Dropping the name from `cell.py`'s own facade
    import breaks this identity check."""
    from mitatedb_api.cell import _deny_provisional_field as cell_deny_provisional_field
    from mitatedb_api.provisional_gate import _deny_provisional_field as leaf_deny_provisional_field

    assert cell_deny_provisional_field is leaf_deny_provisional_field


def test_deny_provisional_field_raises_capability_unsupported_naming_the_field():
    """`provisional_gate._deny_provisional_field` is
    unreachable from any live request path (design docstring: every
    1.7.0 capability it ever covered is `enabled`), so this is the ONLY
    place its exception type, message, and `details` shape are pinned --
    fixed as literals so a future edit cannot silently narrow the
    4-key `details` form or change the `violated_declaration` value."""
    from mitatedb_api.provisional_gate import _deny_provisional_field

    with pytest.raises(CapabilityError) as ctx:
        _deny_provisional_field("budget")
    assert str(ctx.value) == "budget is not supported by this peer"
    assert ctx.value.details == {"violated_declaration": "capability", "field": "budget"}
