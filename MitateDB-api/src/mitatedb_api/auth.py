"""Server-bound credential and application lifecycle state."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import secrets
from threading import RLock
from typing import Optional

from .audit import AuditSink
from .errors import AuthenticationError, AuthorizationStateUnavailable, NotFoundError


class Role(str, Enum):
    RUNTIME = "runtime"
    DEVELOPER = "developer"


@dataclass(frozen=True)
class Principal:
    application_id: str
    credential_id: str
    role: Role


@dataclass
class _Credential:
    credential_id: str
    application_id: str
    role: Role
    digest: bytes
    enabled: bool = True
    expires_at: Optional[datetime] = None


class CredentialStore:
    """In-memory control-plane registry for local tests and development.

    Only a digest is retained. The production implementation must replace
    this store with an external secret/control service and preserve the same
    fail-closed behavior.
    """

    def __init__(self, pepper, audit=None):
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError("credential pepper must be supplied externally")
        self._pepper = pepper.encode("utf-8")
        self._credentials = {}
        self._applications = {}
        self._lock = RLock()
        self.audit = audit or AuditSink()
        self.authorization_state_available = True

    def provision_application(self, application_id):
        with self._lock:
            self._applications[application_id] = True

    def issue(self, application_id, role, expires_at=None):
        with self._lock:
            if application_id not in self._applications:
                raise AuthenticationError("unknown application")
            if not isinstance(role, Role):
                role = Role(role)
            if expires_at is not None and (not isinstance(expires_at, datetime) or
                                           expires_at.tzinfo is None):
                raise ValueError("expiry must be timezone-aware")
            credential_id = secrets.token_hex(12)
            secret = secrets.token_urlsafe(32)
            self._credentials[credential_id] = _Credential(
                credential_id=credential_id,
                application_id=application_id,
                role=role,
                digest=self._digest(secret),
                expires_at=expires_at,
            )
            self.audit.record("credential_issued", application_id,
                              credential_id, detail="role=" + role.value)
            # The secret is returned once and never stored or returned again.
            return credential_id, secret

    def revoke(self, credential_id):
        with self._lock:
            item = self._credentials.get(credential_id) if isinstance(credential_id, str) else None
            if item is None:
                # Fail closed rather than silently accepting an unknown id:
                # a control-plane operator must not be able to believe a
                # credential was revoked when no such credential exists.
                raise NotFoundError("credential not found")
            item.enabled = False
            self.audit.record("credential_revoked", item.application_id,
                              credential_id)

    def disable_application(self, application_id):
        with self._lock:
            if application_id in self._applications:
                self._applications[application_id] = False
                self.audit.record("application_disabled", application_id)

    def enable_application(self, application_id):
        with self._lock:
            if application_id in self._applications:
                self._applications[application_id] = True

    def authenticate(self, credential_id, secret):
        with self._lock:
            if not self.authorization_state_available:
                self.audit.record("authorization_state_failure",
                                  outcome="denied", detail="state_unavailable")
                raise AuthorizationStateUnavailable("authorization unavailable")
            item = self._credentials.get(credential_id)
            valid = item is not None
            if valid:
                valid = hmac.compare_digest(item.digest, self._digest(secret))
                valid = valid and item.enabled
                valid = valid and self._applications.get(item.application_id, False)
                valid = valid and (item.expires_at is None or
                                   item.expires_at > datetime.now(timezone.utc))
            if not valid:
                self.audit.record("authentication_denied", outcome="denied",
                                  detail="invalid_or_disabled")
                raise AuthenticationError("authentication failed")
            self.audit.record("authentication_succeeded", item.application_id,
                              item.credential_id, detail="role=" + item.role.value)
            return Principal(item.application_id, item.credential_id, item.role)

    def assert_active(self, principal):
        """Re-check authorization state for every session operation.

        This closes the window where an already-open session could continue
        after credential revocation or Application disable.
        """
        with self._lock:
            if not self.authorization_state_available:
                self.audit.record("authorization_state_failure",
                                  getattr(principal, "application_id", None),
                                  getattr(principal, "credential_id", None),
                                  outcome="denied", detail="state_unavailable")
                raise AuthorizationStateUnavailable("authorization unavailable")
            item = self._credentials.get(getattr(principal, "credential_id", None))
            if item is None or item.application_id != getattr(principal, "application_id", None):
                self.audit.record("authentication_denied",
                                  getattr(principal, "application_id", None),
                                  getattr(principal, "credential_id", None),
                                  outcome="denied", detail="invalid_or_disabled")
                raise AuthenticationError("authentication failed")
            if item.role != getattr(principal, "role", None) or not item.enabled:
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                raise AuthenticationError("authentication failed")
            if not self._applications.get(item.application_id, False):
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                raise AuthenticationError("authentication failed")
            if item.expires_at is not None and item.expires_at <= datetime.now(timezone.utc):
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                raise AuthenticationError("authentication failed")

    def _digest(self, secret):
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()
