"""Authority topology model used by deployment checks and conformance tests."""
from __future__ import annotations

from dataclasses import dataclass


PLANES = ("application_data", "application_development", "application_identity", "control", "provisioning", "audit")

# CCR-14 WP-4 (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md v1.6, §3/§8 m-8):
# the new `/control/v1` HTTP surface (`control_http.create_control_app`,
# R-1) is a node distinct from the pre-existing `control` plane above --
# `control` already models the provisioning/administrative *authority*
# boundary this topology enforced before CCR-14 (the `ControlAuthority`/
# operator-CLI world), while this new node is specifically the public-facing
# HTTP process R-1/R-3 describe: a *separate* deployable process with its
# own least-privilege DB role (`r2dbsvc_controlplane`) that structurally has
# no route to Application real data at all.
#
# It is deliberately kept out of `PLANES` itself, in a second, additive
# tuple: `tests/test_topology.py`'s pre-existing
# `test_topology_has_all_planes_and_denies_application_escape` asserts
# `set(PLANES) == {...}` by strict equality, not a subset check, and this
# WP's own completion condition (§8 m-8) requires that assertion to stay
# byte-identical and green -- widening `PLANES` itself would fail it on the
# spot the moment a 7th name appeared in the set. `ALL_PLANES` is what
# `can_reach`'s membership guard checks against instead, so every pre-
# existing pairwise `can_reach` result among the original 6 planes is
# unchanged (the guard only ever gets *more* permissive, and the new plane
# is never a source/target any pre-existing call site names).
CONTROL_HTTP_PLANE_NAME = "control_plane_http"
ALL_PLANES = PLANES + (CONTROL_HTTP_PLANE_NAME,)


@dataclass(frozen=True)
class AuthorityTopology:
    """The application-facing authority has no control/provisioning egress."""

    public_plane: str = "application_data"
    developer_plane: str = "application_development"
    control_plane: str = "control"
    provisioning_plane: str = "provisioning"
    audit_plane: str = "audit"
    control_plane_http: str = CONTROL_HTTP_PLANE_NAME

    def can_reach(self, source: str, target: str) -> bool:
        # Round-2 review MINOR-6: the `if ...: return False` blocks below
        # are documentation over a default-deny allow list, not the actual
        # enforcement -- the final `return` statement at the bottom of this
        # method is the only place that can ever produce `True`, so every
        # pair not named there is already unreachable with or without these
        # blocks (reviewer verified: deleting all of them changes nothing
        # observable). They are kept because they name the specific denied
        # pairs design/CONTROL_MAPPING evidence cites, in one place, without
        # having to read the allow-list negatively.
        if source not in ALL_PLANES or target not in ALL_PLANES:
            return False
        if source == self.public_plane and target in {self.control_plane, self.provisioning_plane, self.developer_plane, self.control_plane_http}:
            return False
        if source == self.developer_plane and target in {self.control_plane, self.provisioning_plane, self.control_plane_http}:
            return False
        if source in {self.public_plane, self.developer_plane} and target == self.audit_plane:
            return False  # emission is brokered; direct mutation/query is not allowed
        if source == self.control_plane_http and target in {self.public_plane, self.developer_plane}:
            return False  # R-3: the control-plane HTTP process has no route to Application real data
        # Round-2 review MAJOR-2: `control_plane_http -> audit` is reachable,
        # mirroring the pre-existing `control -> audit` edge just above --
        # the control-plane HTTP process holds `GRANT INSERT ON control_audit`
        # (migration `0006_control_plane_http.sql`, R-3) and R-6 requires it
        # to write durable state-change/denial events there. Like `control`'s
        # own audit edge, this is an append-only write path (INSERT-only
        # GRANT, no SELECT/UPDATE/DELETE) -- reachability here models "can
        # emit an event", not "can read or alter the sink" (`boundaries.
        # audit` in `config/authority-topology.yaml` already states that
        # distinction for the pre-existing edge). Asserting this pair
        # unreachable (WP-4's first pass) contradicted the migration's own
        # GRANT and would have made a CONTROL_MAPPING SI-00/SI-02 evidence
        # citation of this test assert something the schema disproves.
        return (
            source == target
            or (source == self.control_plane and target in {self.provisioning_plane, self.audit_plane})
            or (source == self.control_plane_http and target in {self.control_plane, self.audit_plane})
        )

    def validate(self) -> None:
        assert not self.can_reach(self.public_plane, self.control_plane)
        assert not self.can_reach(self.public_plane, self.provisioning_plane)
        assert not self.can_reach(self.public_plane, self.developer_plane)
        assert not self.can_reach(self.developer_plane, self.control_plane)
        assert not self.can_reach(self.public_plane, self.control_plane_http)
        assert not self.can_reach(self.control_plane_http, self.public_plane)
