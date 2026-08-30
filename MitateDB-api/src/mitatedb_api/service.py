"""Control-plane and application-facing service composition."""

from .audit import AuditSink
from .auth import CredentialStore, Role
from .cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from .config import FoundationConfig
from .errors import AuthenticationError, ConflictError
from .identifiers import validate_identifier


class ProvisioningFacade:
    """Privileged provisioning facade, never reachable through a session.

    R-3/WP-0 m-8 (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md):
    renamed from `ControlPlane` -- this class is an in-process,
    SQLite-backed application/credential lifecycle facade used by the
    local foundation composition and the in-process conformance adapter;
    it is NOT the wire-level `/control/v1` control plane the design
    document's own R-6 describes (a separate, not-yet-built component,
    WP-4/5). The old name invited exactly that confusion. `ControlPlane`
    is kept below as a backward-compatible alias -- every existing caller
    (`tests/test_foundation.py`, `conformance/conformance_adapter_
    mitatedb.py`) keeps working unchanged; new code should prefer
    `ProvisioningFacade`.
    """

    def __init__(self, pepper, config=None, audit=None):
        self.audit = audit or AuditSink()
        self.config = config or FoundationConfig()
        self.credentials = CredentialStore(pepper, self.audit)
        self.cells = {}

    def provision_application(self, application_id):
        validate_identifier(application_id, "application_id")
        if application_id in self.cells:
            # WP-0 m-8: a legitimate "this id is already provisioned"
            # outcome must land on this foundation's own safe error
            # classification hierarchy (`errors.FoundationError`), not an
            # unclassified `ValueError` that would fall through every
            # adapter's own `classify()` and surface as `SERVICE_
            # UNAVAILABLE`/UNCLASSIFIED instead of `CONFLICT`.
            raise ConflictError("application already provisioned")
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


# Backward-compatible alias (see `ProvisioningFacade`'s own docstring).
ControlPlane = ProvisioningFacade


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
