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


# WP-2 review m-4: a fixed-length (32 bytes, matching `_digest`'s own
# SHA-256 output), never-matching stand-in digest -- `CredentialStore.
# authenticate` below always performs an `hmac.compare_digest` call
# against SOME 32-byte value, whether or not `credential_id` is present in
# `self._credentials`, so an unknown `credential_id` does not return via a
# measurably cheaper code path than a known one that only fails the
# secret comparison. This value carries no security property of its own
# (it is not derived from any pepper or secret) -- its only job is to
# keep the comparison's *shape* identical across both cases. Independent
# of `credential_store_postgres._DUMMY_DIGEST` (same value, same
# rationale, deliberately duplicated rather than shared -- R-2's own
# "no code sharing" principle applied here to MitateDB's own two stores,
# not only to the two peers).
_DUMMY_DIGEST = hashlib.sha256(b"mitatedb-credential-store-timing-parity-dummy").digest()


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
    # WP-2 (design v1.2 R-4/§3): independent from `enabled`. `enabled` is
    # the reversible operational state (`disable`/`enable` toggle it);
    # `revoked` is terminal (contract `lifecycle.credential`: "Revocation
    # is terminal: a revoked credential can never be made valid again, and
    # enable reverses disable only"). Before this WP the two were
    # conflated -- `revoke()` set `enabled = False` and there was no
    # separate `revoked` field at all, which made a revoked credential
    # indistinguishable from a merely-disabled one and therefore
    # resurrectable by a future `enable` call. `CredentialsResult`/
    # `CredentialStateResult` (spec/data-service-api.v1.json) both require
    # `enabled` and `revoked` as two independent, always-present booleans
    # -- this field brings the in-memory store's own internal state shape
    # in line with that contract shape, not merely its external behavior.
    revoked: bool = False
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
            # WP-2 (design v1.2 R-4): sets `revoked` only -- `enabled` is
            # deliberately left untouched (whatever it already was). Before
            # this WP this method conflated the two states by setting
            # `enabled = False` instead; `authenticate`/`assert_active`
            # below now check `revoked` independently, so a subsequent
            # `enable()` call can never make this credential valid again
            # (contract `lifecycle.credential`: "Revocation is terminal").
            # Idempotent: revoking an already-revoked credential succeeds
            # silently (no un-revoke path exists anywhere in this class to
            # accidentally trigger, and re-asserting an already-true fact
            # is not itself a lifecycle violation).
            item.revoked = True
            self.audit.record("credential_revoked", item.application_id,
                              credential_id)

    def disable(self, credential_id):
        """Reversible operational state (contract `lifecycle.credential`).
        Touches `enabled` only -- never `revoked` -- so a later `enable()`
        can always reverse THIS call specifically, regardless of whether
        the credential was ever revoked (see `enable`'s own docstring for
        why that reversal can still be a no-op in effect).

        Fails closed on an unknown credential id, mirroring `revoke`'s own
        reasoning: an operator must not be told (by silence) that a
        credential was disabled when no such credential exists.
        """
        with self._lock:
            item = self._credentials.get(credential_id) if isinstance(credential_id, str) else None
            if item is None:
                raise NotFoundError("credential not found")
            item.enabled = False
            self.audit.record("credential_disabled", item.application_id,
                              credential_id)

    def enable(self, credential_id):
        """Reverses `disable` only (contract `enable_credential.semantics`:
        "Reverses disable only. A revoked credential is not resurrected.").
        Sets `enabled = True` unconditionally -- including when `revoked`
        is already `True` -- but never touches `revoked` itself: a
        previously-revoked credential's `enabled` flag flips back to
        `True` here (the call itself is not refused), yet `authenticate`/
        `assert_active` below gate on `not item.revoked` independently of
        `enabled`, so the credential still cannot authenticate afterward.
        This is the structural guarantee the design calls for ("`enable`
        は disable のみを戻し、revoked を決して復活させない") -- there is
        no branch anywhere in this method that reads or clears `revoked`.

        Fails closed on an unknown credential id, mirroring `disable`.
        """
        with self._lock:
            item = self._credentials.get(credential_id) if isinstance(credential_id, str) else None
            if item is None:
                raise NotFoundError("credential not found")
            item.enabled = True
            self.audit.record("credential_enabled", item.application_id,
                              credential_id)

    def get_state(self, credential_id):
        """`(enabled, revoked)` for `credential_id`, or `None` if it does
        not exist. Read-only; used by parity tests (and, in a future WP,
        `list_credentials`/`CredentialStateResult` responses) to observe
        both independent booleans without reaching into `_Credential`
        directly."""
        with self._lock:
            item = self._credentials.get(credential_id)
            return (item.enabled, item.revoked) if item is not None else None

    def disable_application(self, application_id):
        """WP-2 review m-1: returns `True` if `application_id` is a known
        application, `False` otherwise -- parity with `credential_store_
        postgres.PostgresCredentialStore.disable_application`'s own
        `RETURNING application_id`-derived boolean (same "row matched"
        meaning: the return value reports whether the id existed, not
        whether the flag's value actually changed). Still not fail-closed
        for an unknown id (this method's own existing, non-fail-closed
        choice is preserved) -- but the caller can now tell the two
        outcomes apart instead of both looking identically silent.
        """
        with self._lock:
            if application_id in self._applications:
                self._applications[application_id] = False
                self.audit.record("application_disabled", application_id)
                return True
            return False

    def enable_application(self, application_id):
        """See `disable_application` above -- identical reasoning, opposite
        value, same `bool` return (WP-2 review m-1)."""
        with self._lock:
            if application_id in self._applications:
                self._applications[application_id] = True
                return True
            return False

    def authenticate(self, credential_id, secret):
        with self._lock:
            if not self.authorization_state_available:
                self.audit.record("authorization_state_failure",
                                  outcome="denied", detail="state_unavailable")
                raise AuthorizationStateUnavailable("authorization unavailable")
            item = self._credentials.get(credential_id)
            # WP-2 review m-4: compute `hmac.compare_digest` against a
            # fixed-shape 32-byte value UNCONDITIONALLY, whether or not
            # `item` was found -- see `_DUMMY_DIGEST`'s own module-level
            # docstring for why an unknown `credential_id` must not skip
            # this call on a cheaper early-exit path.
            stored_digest = item.digest if item is not None else _DUMMY_DIGEST
            digest_matches = hmac.compare_digest(stored_digest, self._digest(secret))
            valid = item is not None and digest_matches
            if valid:
                # WP-2 (design v1.2 R-4): `enabled` and `revoked` are
                # checked independently -- `revoked` is terminal and is
                # never reversed by `enable` (see `enable`'s docstring), so
                # this check must survive even after `item.enabled` has
                # been flipped back to `True`.
                valid = valid and item.enabled and not item.revoked
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
            # WP-2 (design v1.2 R-4): `revoked` gates independently of
            # `enabled`, same reasoning as `authenticate` above -- an
            # already-open session's re-check must not survive a revoke
            # being masked by a later `enable`.
            if item.role != getattr(principal, "role", None) or not item.enabled or item.revoked:
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
