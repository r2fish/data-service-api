"""Authority topology model used by deployment checks and conformance tests."""
from __future__ import annotations

from dataclasses import dataclass


PLANES = ("application_data", "application_development", "application_identity", "control", "provisioning", "audit")


@dataclass(frozen=True)
class AuthorityTopology:
    """The application-facing authority has no control/provisioning egress."""

    public_plane: str = "application_data"
    developer_plane: str = "application_development"
    control_plane: str = "control"
    provisioning_plane: str = "provisioning"
    audit_plane: str = "audit"

    def can_reach(self, source: str, target: str) -> bool:
        if source not in PLANES or target not in PLANES:
            return False
        if source == self.public_plane and target in {self.control_plane, self.provisioning_plane, self.developer_plane}:
            return False
        if source == self.developer_plane and target in {self.control_plane, self.provisioning_plane}:
            return False
        if source in {self.public_plane, self.developer_plane} and target == self.audit_plane:
            return False  # emission is brokered; direct mutation/query is not allowed
        return source == target or (source == self.control_plane and target in {self.provisioning_plane, self.audit_plane})

    def validate(self) -> None:
        assert not self.can_reach(self.public_plane, self.control_plane)
        assert not self.can_reach(self.public_plane, self.provisioning_plane)
        assert not self.can_reach(self.public_plane, self.developer_plane)
        assert not self.can_reach(self.developer_plane, self.control_plane)
