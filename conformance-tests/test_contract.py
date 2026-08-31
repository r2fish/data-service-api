"""Implementation-independent smoke checks for the common machine contract."""
import copy
import json
import re
from pathlib import Path

from schema_check import validate


ROOT = Path(__file__).parents[1]


def test_contract_is_machine_readable_and_has_required_sections():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    for section in ("security", "versioning", "endpoints", "structured_operations", "transactions", "errors", "limits", "lifecycle", "audit"):
        assert section in contract
    assert contract["limits"]["finite_required"] is True
    sql_rule = contract["structured_operations"]["sql"]
    assert sql_rule.startswith("No public operation accepts SQL")
    assert all("sql" not in endpoint["path"].lower() for endpoint in contract["endpoints"].values())
    assert contract["schemas"]["MutationRequest"]["properties"]["operations"]["items"]["$ref"] == "#/definitions/Mutation"
    assert contract["definitions"]["Mutation"]["additionalProperties"] is False
    assert all(value > 0 for value in contract["limits"]["example_profile"].values())


def test_contract_has_separate_control_and_application_authority():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert contract["security"]["roles"] == ["runtime", "developer", "control", "audit"]
    assert contract["endpoints"]["audit_query"]["auth"] == "control or audit"
    assert contract["endpoints"]["schema"]["auth"] == "developer"


def test_contract_defines_peer_neutral_capability_status_and_response_shape():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    status = contract["capability_status"]
    assert set(status["status_enum"]) == {"enabled", "partial", "unavailable", "planned"}
    assert "deployment_required" in status["enforcement_enum"]
    capability = contract["schemas"]["CapabilityDocument"]
    assert capability["properties"]["capabilities"]["additionalProperties"]["required"] == ["status"]
    assert capability["properties"]["limit_enforcement"]["additionalProperties"]["enum"] == status["enforcement_enum"]


def test_contract_requires_published_authorization_propagation_bound():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    capability = contract["schemas"]["CapabilityDocument"]
    assert "authorization_propagation_bound_ms" in capability["required"]
    bound_schema = capability["properties"]["authorization_propagation_bound_ms"]
    assert bound_schema["type"] == "integer"
    assert bound_schema["minimum"] == 0
    assert "propagation_bound" in contract["lifecycle"]


def test_contract_states_audit_sink_failure_policy():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    policy = contract["audit"]["sink_failure_policy"]
    assert isinstance(policy, str) and policy
    assert "fails the operation closed" in policy
    assert "bounded buffer" in policy
    assert "explicit operational alert" in policy


def test_all_ccrs_have_disposition_records():
    # CCR ids are discovered from the change-request documents themselves, not
    # hardcoded: a newly raised CCR must not be able to slip past this check
    # merely because nobody remembered to widen a range here.
    requests = sorted((ROOT).glob("*/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md"))
    assert requests, "no common contract change-request document was found"
    raised = set()
    for document in requests:
        raised.update(re.findall(r"CCR-\d{2}", document.read_text()))
    assert len(raised) >= 12
    text = (ROOT / "spec" / "CCR_DISPOSITION.md").read_text()
    missing = sorted(identifier for identifier in raised if identifier not in text)
    assert not missing, f"raised CCRs without a disposition record: {missing}"
    assert "却下・保留となるCCRはない" in text


def test_contract_declares_1_3_0():
    # Phase 3.5 WP-1 (docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
    # §1-G, CCR_DISPOSITION.md subordinate ruling 8): the version bump itself,
    # pinned so a future revert of just this one line is caught here rather
    # than only by whichever other test happens to touch contract_version.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert contract["contract_version"] == "1.3.0"


def test_contract_audit_fields_include_optional_target_id_and_it_is_not_forbidden():
    # §1-C: target_id is an additive, OPTIONAL member of audit.fields (present
    # only for single-target events), and must not collide with the separate
    # forbidden_fields vocabulary (an identifier, not a secret).
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    audit = contract["audit"]
    assert "target_id" in audit["fields"]
    assert "target_id" not in audit["forbidden_fields"]


def test_credentials_result_with_must_rotate_is_invalid_under_1_2_0_shape_valid_under_1_3_0():
    """Positive control for §1-B/§1-G (design doc's own m-1 correction):
    an additive-only contract change can never make a previously-VALID
    instance invalid (the accepted set only grows), so the meaningful
    regression check runs the other direction -- a `CredentialsResult` row
    carrying the NEW `must_rotate` field must be REJECTED by the 1.2.0-era
    closed schema shape (`additionalProperties: false` with no `must_rotate`
    property) and ACCEPTED by the current (1.3.0) schema.

    The 1.2.0-shape half is not read from git history (there is no repo
    convention for checking out a prior contract revision inside this
    suite); instead it is reconstructed by deep-copying the CURRENT
    `CredentialsResult` schema and deleting the `must_rotate` property this
    WP just added. This reconstruction is exact for this one property
    because `must_rotate` is the only 1.3.0 change to `CredentialsResult`'s
    row schema (§1 lists no other edit to this schema) -- removing it
    recovers the 1.2.0 closure being tested against.
    """
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    current_row_schema = contract["schemas"]["CredentialsResult"]["properties"]["credentials"]["items"]

    legacy_row_schema = copy.deepcopy(current_row_schema)
    assert "must_rotate" in legacy_row_schema["properties"], (
        "CredentialsResult.credentials[] no longer declares must_rotate -- this reconstruction "
        "of the 1.2.0-era shape (current schema minus must_rotate) is no longer meaningful"
    )
    del legacy_row_schema["properties"]["must_rotate"]

    row_with_must_rotate = {
        "credential_id": "c1", "role": "control", "enabled": True, "revoked": False,
        "must_rotate": True,
    }

    legacy_violations = validate(row_with_must_rotate, legacy_row_schema, contract)
    assert legacy_violations, (
        "a CredentialsResult row carrying must_rotate must be rejected by the reconstructed "
        "1.2.0-era schema (additionalProperties: false, no must_rotate property) -- got no violations"
    )

    current_violations = validate(row_with_must_rotate, current_row_schema, contract)
    assert not current_violations, (
        f"a CredentialsResult row carrying must_rotate must be accepted by the current (1.3.0) "
        f"schema -- got violations: {current_violations}"
    )

    # must_rotate stays optional: a row omitting it entirely remains valid too
    # (application credentials, where the concept does not exist -- §1-B).
    row_without_must_rotate = {"credential_id": "c2", "role": "runtime", "enabled": True, "revoked": False}
    assert not validate(row_without_must_rotate, current_row_schema, contract)


def test_control_endpoint_audit_role_acceptance_matches_1_3_0_declaration():
    # Independent-review M-2 (i): §1-D's auth flip has no other regression pin
    # -- a future accidental revert of just these three "auth" values (or a
    # widening of issue_credential's) would otherwise go unnoticed by any
    # other test in this suite.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    control_endpoints = contract["control_endpoints"]
    assert control_endpoints["control_capabilities"]["auth"] == "control or audit"
    assert control_endpoints["list_applications"]["auth"] == "control or audit"
    assert control_endpoints["list_credentials"]["auth"] == "control or audit"
    # Every other control endpoint -- issue_credential included -- stays
    # control-only; audit role is not granted anywhere beyond the three
    # read-only endpoints above.
    assert control_endpoints["issue_credential"]["auth"] == "control"


def test_contract_1_3_0_prose_pins():
    # Independent-review M-2 (ii): substring pins for §1 A/D/E/F, following
    # this file's existing style (see test_contract_has_separate_control_and_
    # application_authority's exact-match pin at :29 and test_contract_states_
    # audit_sink_failure_policy's substring pins at :57-59) -- each of these
    # sentences currently has no dedicated regression test of its own.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # §1-A: batch_entities bounds DISTINCT entity names, not operation count.
    cross_entity_semantics = contract["endpoints"]["cross_entity_mutate"]["semantics"]
    assert "distinct entity names" in cross_entity_semantics

    # §1-E: per-application issuance freeze refusal code.
    issue_credential_semantics = contract["control_endpoints"]["issue_credential"]["semantics"]
    assert "frozen application is refused with FORBIDDEN" in issue_credential_semantics

    # §1-F: atomic_mutation's operations vocabulary clarification.
    atomic_mutation = contract["capability_status"]["defined"]["atomic_mutation"]
    assert "the mutation vocabulary the batch execution surface executes" in atomic_mutation

    # §1-D: audit role is fail-closed (FORBIDDEN) on every control endpoint
    # other than the three read-only ones.
    authority = contract["control_plane"]["authority"]
    assert "fails it closed with FORBIDDEN" in authority
