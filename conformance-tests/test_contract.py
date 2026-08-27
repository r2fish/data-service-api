"""Implementation-independent smoke checks for the common machine contract."""
import json
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


def test_all_ccrs_have_disposition_records():
    text = (ROOT / "spec" / "CCR_DISPOSITION.md").read_text()
    for number in range(1, 13):
        assert f"CCR-{number:02d}" in text
    assert "却下・保留となるCCRはない" in text
