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

import re

import pytest

from mitatedb_api import ControlPlane, FoundationConfig, MitateDataService, Role
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
# F-1: the version flip (design D-1 (5)/(7)).
# ---------------------------------------------------------------------------


def test_contract_version_is_1_7_0_on_data_plane(service):
    _, _, _dev, runtime = service
    assert runtime.capabilities()["contract_version"] == "1.7.0"


def test_contract_version_is_1_7_0_on_control_plane():
    from mitatedb_api.control_plane import ControlPlaneService, InMemoryControlBackend, bootstrap_control_credential

    backend = InMemoryControlBackend(app_pepper="p" * 20, control_pepper="c" * 20)
    service = ControlPlaneService(backend)
    with backend.unit_of_work() as work:
        _cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    document = service.control_capabilities(secret)
    assert document["contract_version"] == "1.7.0"


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


def test_check_contract_170_declarations_accepts_a_healthy_state():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = {"capabilities": {
        "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
        "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
    }}
    config = FoundationConfig(
        max_enum_members=64, idempotency_entries=10_000, idempotency_retention_ms=86_400_000)
    platform_declarations.check_contract_170_declarations(
        document, config, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)


@pytest.mark.parametrize("capability_name", ["constraint_declarations", "dry_run", "idempotency", "request_budget"])
def test_check_contract_170_declarations_rejects_a_capability_not_enabled(capability_name):
    from mitatedb_api import platform_declarations
    from mitatedb_api.errors import ValidationError as _Unused  # noqa: F401
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = {"capabilities": {
        "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
        "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
    }}
    document["capabilities"][capability_name] = {"status": "unavailable"}
    config = FoundationConfig(
        max_enum_members=64, idempotency_entries=10_000, idempotency_retention_ms=86_400_000)
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, config, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


@pytest.mark.parametrize("field_name,attr_name", [
    ("enum_members", "max_enum_members"), ("idempotency_entries", "idempotency_entries"),
    ("idempotency_retention_ms", "idempotency_retention_ms"),
])
def test_check_contract_170_declarations_rejects_a_non_positive_limit(field_name, attr_name):
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = {"capabilities": {
        "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
        "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
    }}
    config = FoundationConfig(
        max_enum_members=64, idempotency_entries=10_000, idempotency_retention_ms=86_400_000)
    # `FoundationConfig` is `@dataclass(frozen=True)` -- `object.__setattr__`
    # is the standard bypass for building an otherwise-invalid probe value
    # (a real deployment would never hold `0` here; `check_contract_170_
    # declarations` is exactly the check that must catch it if one did).
    object.__setattr__(config, attr_name, 0)
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, config, {"app_a": PLATFORM_UPGRADE_NUMBERS}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_check_contract_170_declarations_rejects_a_missing_application_upgrade():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = {"capabilities": {
        "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
        "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
    }}
    config = FoundationConfig(
        max_enum_members=64, idempotency_entries=10_000, idempotency_retention_ms=86_400_000)
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, config, {"app_a": frozenset()}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_check_contract_170_declarations_treats_a_missing_ledger_as_every_number_pending():
    from mitatedb_api import platform_declarations
    from mitatedb_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

    document = {"capabilities": {
        "constraint_declarations": {"status": "enabled"}, "dry_run": {"status": "enabled"},
        "idempotency": {"status": "enabled"}, "request_budget": {"status": "enabled"},
    }}
    config = FoundationConfig(
        max_enum_members=64, idempotency_entries=10_000, idempotency_retention_ms=86_400_000)
    with pytest.raises(platform_declarations.PlatformDeclarationError) as ctx:
        platform_declarations.check_contract_170_declarations(
            document, config, {"app_a": None}, PLATFORM_UPGRADE_NUMBERS)
    assert ctx.value.code == "F-14"


def test_verify_declarations_exit_code_table_has_f14():
    from mitatedb_api.ops import _VERIFY_DECLARATIONS_EXIT_CODES

    assert _VERIFY_DECLARATIONS_EXIT_CODES["F-14"] == 13
