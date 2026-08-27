"""Control-plane and application-facing service composition."""

from .audit import AuditSink
from .auth import CredentialStore, Role
from .cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from .config import FoundationConfig
from .errors import AuthenticationError
from .identifiers import validate_identifier


class ControlPlane:
    """Privileged provisioning facade, never reachable through a session."""

    def __init__(self, pepper, config=None, audit=None):
        self.audit = audit or AuditSink()
        self.config = config or FoundationConfig()
        self.credentials = CredentialStore(pepper, self.audit)
        self.cells = {}

    def provision_application(self, application_id):
        validate_identifier(application_id, "application_id")
        if application_id in self.cells:
            raise ValueError("application already provisioned")
        self.credentials.provision_application(application_id)
        self.cells[application_id] = ApplicationCell(
            application_id, self.config, self.audit,
            guard=self.credentials.assert_active)

    def issue_credential(self, application_id, role, expires_at=None):
        return self.credentials.issue(application_id, role, expires_at)

    def revoke_credential(self, credential_id):
        self.credentials.revoke(credential_id)

    def disable_application(self, application_id):
        self.credentials.disable_application(application_id)


class MitateDataService:
    """Application-facing composition with server-bound scope resolution."""

    def __init__(self, control_plane):
        self._control = control_plane

    def open_session(self, credential_id, secret):
        principal = self._control.credentials.authenticate(credential_id, secret)
        cell = self._control.cells.get(principal.application_id)
        if cell is None:
            # Do not permit an authorization record without a storage boundary.
            raise AuthenticationError("application unavailable")
        if principal.role == Role.DEVELOPER:
            return ApplicationDeveloper(cell, principal, self._control.credentials.assert_active)
        return ApplicationRuntime(cell, principal, self._control.credentials.assert_active)
