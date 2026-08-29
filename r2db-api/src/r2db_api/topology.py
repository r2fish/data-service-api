"""Authority topology model used by deployment checks and conformance tests."""
from __future__ import annotations

from dataclasses import dataclass


CONTROL_HTTP_PLANE_NAME = "control_plane_http"

# CCR-14 WP-5 (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md v1.7, §5 WP-5 row
# / §13.3): `control_plane_http` (added WP-4, R-1's independent `/control/v1`
# HTTP process node) is now consolidated directly into `PLANES` -- the WP-4
# freeze that kept it in a second, additive `ALL_PLANES` tuple only (so as
# not to disturb `test_topology.py`'s then-existing strict-equality
# assertion, §8 m-8) ends with this WP: the work order explicitly calls for
# folding it in and updating that assertion to the resulting 7-name set.
# `ALL_PLANES` stays as a plain alias (not removed outright) purely so any
# reader/caller that still spells the older name keeps working unchanged --
# the two names are now, and will stay, identical.
PLANES = ("application_data", "application_development", "application_identity", "control", "provisioning", "audit", CONTROL_HTTP_PLANE_NAME)
ALL_PLANES = PLANES


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
