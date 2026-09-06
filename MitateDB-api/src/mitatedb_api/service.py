"""Control-plane and application-facing service composition."""

from .audit import AuditSink
from .auth import CredentialStore, Role
from .cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, _LimitStateHolder
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

    def __init__(self, pepper, config=None, audit=None, *, audit_router=None):
        self.audit = audit or AuditSink()
        self.config = config or FoundationConfig()
        # Phase 4 WP-3(b): propagates the SAME shared `audit_dispatch.
        # AuditRouter` instance (when the caller provides one) into both
        # `self.credentials` and every cell this facade provisions --
        # mirrors `main.build_app`'s own identical wiring (`audit_router`
        # passed to `PostgresCredentialStore`/`ApplicationCell` alike, one
        # instance for the whole process). `audit_router=None` (every
        # pre-Phase-4 caller) leaves `CredentialStore`/`ApplicationCell`
        # to build their own private, unshared default router each --
        # unchanged behavior for every caller that does not opt in.
        self._audit_router = audit_router
        # Phase 8 WP-1a (design D-1 "置き場は実装WPが新設する (1プロセス
        # 1個)"): exactly one limit-state holder for this whole facade --
        # the SAME one-per-composition-root injection shape `audit_router`
        # immediately above already established. Every `ApplicationCell`
        # this facade ever provisions (below) shares this single instance,
        # so `requests_per_minute`/`concurrency` are bounded across the
        # WHOLE facade, never re-initialized per application.
        self._limit_holder = _LimitStateHolder()
        self.credentials = CredentialStore(pepper, self.audit, audit_router=audit_router)
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
            guard=self.credentials.assert_active, audit_router=self._audit_router,
            limit_holder=self._limit_holder)

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

    def open_session(self, secret):
        """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
        裁定 1): `secret` is the FULL presented bearer (the composed
        string `CredentialStore.issue`/`.rotate` return, verbatim) --
        this method is this peer's own in-process receiving boundary; it
        never splits the bearer itself, passing it straight through to
        `auth.CredentialStore.authenticate`, which is the single choke
        point that calls `split_bearer_locator` exactly once. See `auth.
        CredentialStore.authenticate`'s own docstring for the full
        reasoning."""
        principal = self._control.credentials.authenticate(secret)
        cell = self._control.cells.get(principal.application_id)
        if cell is None:
            # Do not permit an authorization record without a storage boundary.
            raise AuthenticationError("application unavailable")
        if principal.role == Role.DEVELOPER:
            return ApplicationDeveloper(cell, principal, self._control.credentials.assert_active)
        return ApplicationRuntime(cell, principal, self._control.credentials.assert_active)
