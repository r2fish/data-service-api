"""Server-bound credential and lifecycle authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from typing import Mapping

from .errors import fail


@dataclass(frozen=True)
class CredentialRecord:
    credential_id: str
    application_id: str
    role: str
    verifier: str
    enabled: bool = True
    revoked: bool = False


@dataclass(frozen=True)
class AuthContext:
    credential_id: str
    application_id: str
    role: str


class CredentialStore:
    def __init__(self, records: Mapping[str, CredentialRecord] | None = None, *, pepper: str | None = None) -> None:
        self._records = dict(records or {})
        pepper = pepper or os.environ.get("R2DB_CREDENTIAL_PEPPER")
        if not pepper:
            raise ValueError("R2DB_CREDENTIAL_PEPPER is required")
        self._pepper = pepper.encode()
        self.available = True

    def verifier(self, secret: str) -> str:
        if not isinstance(secret, str):
            fail("VALIDATION_FAILED", "Credential secret has an invalid type.")
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    def add(self, credential_id: str, application_id: str, role: str, secret: str) -> None:
        if role not in {"runtime", "developer"}:
            fail("VALIDATION_FAILED", "Application credentials require runtime or developer role.")
        self._records[credential_id] = CredentialRecord(credential_id, application_id, role, self.verifier(secret))

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        record = self._records.get(credential_id)
        if record is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        self._records[credential_id] = CredentialRecord(record.credential_id, record.application_id, record.role, record.verifier, record.enabled if enabled is None else enabled, record.revoked if revoked is None else revoked)

    def authenticate(self, secret: str | None) -> AuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        for record in self._records.values():
            if hmac.compare_digest(record.verifier, self.verifier(secret)):
                if record.revoked:
                    fail("AUTH_REVOKED", "Credential is not active.", status=401)
                if not record.enabled:
                    fail("AUTH_INVALID", "Credential is not active.", status=401)
                return AuthContext(record.credential_id, record.application_id, record.role)
        fail("AUTH_INVALID", "Credential is not valid.", status=401)

    def assert_active(self, context: AuthContext) -> AuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        record = self._records.get(context.credential_id)
        if record is None or not record.enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        if record.revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if record.application_id != context.application_id or record.role != context.role:
            fail("SCOPE_MISMATCH", "Credential scope is not valid for this request.", status=403)
        return AuthContext(record.credential_id, record.application_id, record.role)

    def canonical_context(self, context: AuthContext) -> AuthContext | None:
        record = self._records.get(getattr(context, "credential_id", ""))
        if record is None:
            return None
        return AuthContext(record.credential_id, record.application_id, record.role)

    def application_id_for(self, credential_id: str) -> str | None:
        record = self._records.get(credential_id)
        return record.application_id if record else None
