"""Implementation-independent smoke checks for the common machine contract."""
import json
import re
from pathlib import Path


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
