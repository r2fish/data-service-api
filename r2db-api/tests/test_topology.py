from r2db_api.topology import AuthorityTopology, PLANES
from pathlib import Path


def test_topology_has_all_planes_and_denies_application_escape():
    topology = AuthorityTopology()
    topology.validate()
    assert set(PLANES) == {"application_data", "application_development", "application_identity", "control", "provisioning", "audit"}
    assert not topology.can_reach("application_data", "application_development")
    assert not topology.can_reach("application_data", "control")
    assert not topology.can_reach("application_data", "provisioning")
    assert not topology.can_reach("application_development", "control")
    assert topology.can_reach("control", "provisioning")


def test_deployment_skeleton_declares_denied_privileged_egress():
    config = Path(__file__).parents[1] / "config" / "authority-topology.yaml"
    text = config.read_text()
    assert "egress_deny: [application_development, control, provisioning, audit]" in text
    assert "egress_deny: [control, provisioning, audit]" in text
    assert "mode: append_only" in text
