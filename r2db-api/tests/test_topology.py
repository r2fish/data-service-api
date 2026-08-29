from r2db_api.topology import ALL_PLANES, AuthorityTopology, CONTROL_HTTP_PLANE_NAME, PLANES
from pathlib import Path


def test_topology_has_all_planes_and_denies_application_escape():
    topology = AuthorityTopology()
    topology.validate()
    # CCR-14 WP-5 (§13.3/§5 WP-5 row): `control_plane_http` is folded into
    # `PLANES` itself now (the WP-4 freeze that kept this a 6-name strict
    # set, deferring the 7th name to the additive-only `ALL_PLANES`, ends
    # with this WP -- see topology.py's own comment). `can_reach`'s results
    # for every one of the original 6 planes are unchanged by this --
    # `test_control_plane_http_reaches_only_control_and_audit` below pins
    # the 7th plane's own pairwise results exactly as WP-4 established them.
    assert set(PLANES) == {
        "application_data", "application_development", "application_identity",
        "control", "provisioning", "audit", "control_plane_http",
    }
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


# ---------------------------------------------------------------------------
# CCR-14 WP-4 (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md v1.6, §3/§8 m-8):
# the new `control_plane_http` node (R-1's independent `/control/v1` HTTP
# process). Additive only -- the two tests above are byte-identical to
# before this WP (§8 m-8's own completion condition).
# ---------------------------------------------------------------------------


def test_control_plane_http_node_is_consolidated_into_planes():
    # CCR-14 WP-5: `control_plane_http` is now a full `PLANES` member (the
    # WP-4-era "additive, not in PLANES" split is over -- see topology.py's
    # own comment and the first test above). `ALL_PLANES` is kept only as a
    # plain alias for backward compatibility, so the two names are, and
    # stay, identical rather than one being a subset of the other.
    assert CONTROL_HTTP_PLANE_NAME in PLANES
    assert CONTROL_HTTP_PLANE_NAME in ALL_PLANES
    assert ALL_PLANES == PLANES


def test_control_plane_http_reaches_only_control_and_audit():
    topology = AuthorityTopology()
    topology.validate()
    # R-1: the HTTP surface's own authority is the pre-existing `control`
    # plane it front-ends.
    assert topology.can_reach("control_plane_http", "control")
    # Round-2 review MAJOR-2: the process holds `GRANT INSERT ON
    # control_audit` (0006_control_plane_http.sql, R-3) and R-6 requires it
    # to write durable events there -- append-only, same shape as `control`'s
    # own `-> audit` edge (asserted `not reachable` in WP-4's first pass,
    # which contradicted the migration's own GRANT; corrected here).
    assert topology.can_reach("control_plane_http", "audit")
    # public/developer -> control_plane_http: unreachable either direction
    # the design names explicitly.
    assert not topology.can_reach("application_data", "control_plane_http")
    assert not topology.can_reach("application_development", "control_plane_http")
    assert not topology.can_reach("control_plane_http", "application_data")
    # R-3: the control-plane HTTP process has no route to Application real
    # data -- neither the runtime/query plane nor the developer/schema one.
    assert not topology.can_reach("control_plane_http", "application_development")
    # Unknown/unrelated pairs stay unreachable, same as every other plane.
    assert not topology.can_reach("control_plane_http", "provisioning")
