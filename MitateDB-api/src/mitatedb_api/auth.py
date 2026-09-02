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
from .audit_dispatch import AuditRouter
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

    def __init__(self, pepper, audit=None, *, audit_router=None):
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError("credential pepper must be supplied externally")
        self._pepper = pepper.encode("utf-8")
        self._credentials = {}
        self._applications = {}
        self._lock = RLock()
        self.audit = audit or AuditSink()
        # Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
        # D-3): the shared durable-audit dispatch router (see `cell.
        # ApplicationCell.__init__`'s identical parameter for the full
        # rationale) -- defaults to a private, unshared one so every
        # pre-Phase-4 caller of this constructor keeps working unchanged.
        self._audit_router = audit_router if audit_router is not None else AuditRouter()
        self.authorization_state_available = True

    def provision_application(self, application_id):
        with self._lock:
            self._applications[application_id] = True

    def issue(self, application_id, role, expires_at=None, *, credential_id=None, secret=None):
        """WP-5 (design v1.2 R-8/§3 WP-5 row, item i "2ストア突合"):
        `credential_id`/`secret` are now optional overrides -- when
        omitted (every pre-existing call site), behavior is byte-for-byte
        unchanged (both are still freshly random-generated here). When
        supplied, this store records EXACTLY the given id/secret rather
        than minting its own -- what lets `control_plane.ControlPlaneService`
        (which always pre-generates the credential_id/secret it is about
        to both store AND return to its own caller, so the two never
        drift apart) issue a credential into THIS SAME store instead of a
        second, disconnected in-memory registry. This is the reconciliation
        the in-process conformance adapter's own control-plane backend
        needs: a credential issued in-band (`issue_credential_inband`)
        must be the exact row `authenticate()` below can read back.
        """
        with self._lock:
            if application_id not in self._applications:
                raise AuthenticationError("unknown application")
            if not isinstance(role, Role):
                role = Role(role)
            if expires_at is not None and (not isinstance(expires_at, datetime) or
                                           expires_at.tzinfo is None):
                raise ValueError("expiry must be timezone-aware")
            credential_id = credential_id or secrets.token_hex(12)
            secret = secret or secrets.token_urlsafe(32)
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

    def application_exists(self, application_id):
        """WP-5 (2ストア突合): read-only existence check, mirroring
        `control_plane.InMemoryApplicationRegistry.exists`'s own call
        surface so this store can serve as (part of) a real `ControlPlane
        Service` backend without that service having to know it is
        talking to the application-plane's own store instead of a
        dedicated control-only registry."""
        with self._lock:
            return application_id in self._applications

    def applications_count(self):
        """WP-5 (2ストア突合): total registered applications -- the same
        count `control_plane.ControlPlaneService.register_application`'s
        own `applications` resource bound is checked against, now backed
        by the SAME dict `authenticate()`/`assert_active` above already
        consult (not a second, adapter-only shadow count)."""
        with self._lock:
            return len(self._applications)

    def list_applications(self):
        """WP-5 (2ストア突合): `[(application_id, enabled), ...]` -- the
        shape `control_plane.ControlPlaneService.list_applications` needs
        from its backend."""
        with self._lock:
            return list(self._applications.items())

    def credentials_active_count(self, application_id):
        """WP-5 (2ストア突合): counts non-revoked credentials only (R-6:
        "credentials_per_application は revoked 行を数えない")."""
        with self._lock:
            return sum(
                1 for item in self._credentials.values()
                if item.application_id == application_id and not item.revoked
            )

    def list_credentials(self):
        """WP-5 (2ストア突合): `[(credential_id, application_id, role,
        enabled, revoked), ...]` -- the shape `control_plane.
        ControlPlaneService.list_credentials` needs from its backend."""
        with self._lock:
            return [
                (item.credential_id, item.application_id, item.role.value, item.enabled, item.revoked)
                for item in self._credentials.values()
            ]

    def unregister_application(self, application_id):
        """WP-5 (2ストア突合): rollback-only primitive -- undoes
        `provision_application` when a control-plane `register_application`
        transaction's own same-transaction audit write fails after this
        store's row was already written (R-6's fail-closed same-tx
        guarantee: a failed operation must leave no trace, not merely no
        SUCCESSFUL trace). Never reachable from any public in-band
        capability -- there is no `deregister`/`unprovision` operation on
        this peer's own contract surface; this exists solely so a
        `ControlPlaneService` backend built on this store can honor an
        undo-log rollback the same way `control_plane.
        InMemoryApplicationRegistry.register`'s own `work.on_rollback`
        already does for its self-contained registry."""
        with self._lock:
            self._applications.pop(application_id, None)

    def forget_credential(self, credential_id):
        """WP-5 (2ストア突合): rollback-only counterpart to `issue` --
        undoes a fresh issuance whose accompanying same-transaction audit
        write failed. Never reachable from any public in-band capability
        (there is no credential-deletion operation on this peer's own
        contract surface -- deleting a row outright is a stronger
        operation than `revoke`, which this store already refuses to
        reverse)."""
        with self._lock:
            self._credentials.pop(credential_id, None)

    def snapshot_credential_state(self, credential_id):
        """WP-5 (2ストア突合): rollback-only. Captures exactly enough
        state (`digest`/`enabled`/`revoked`) to restore this credential to
        its current row via `restore_credential_state` below, for a
        control-plane transaction's own undo-log (`rotate_credential`/
        `set_credential_state`'s own same-transaction-audit-failure case).
        Returns `None` for an unknown id."""
        with self._lock:
            item = self._credentials.get(credential_id)
            return None if item is None else (item.digest, item.enabled, item.revoked)

    def restore_credential_state(self, credential_id, snapshot):
        """WP-5 (2ストア突合): rollback-only counterpart to `snapshot_
        credential_state`. A no-op for a `None` snapshot (the credential
        did not exist when the snapshot was taken) or an id that has since
        disappeared. Deliberately capable of restoring `revoked=False` --
        this is an undo of a FAILED, never-committed operation (R-6's
        same-transaction fail-closed guarantee: nothing about a failed
        attempt should remain in effect, including a revoke it performed),
        not a public un-revoke capability; no in-band operation on this
        peer's contract surface ever calls this method."""
        if snapshot is None:
            return
        digest, enabled, revoked = snapshot
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is not None:
                item.digest = digest
                item.enabled = enabled
                item.revoked = revoked

    def rotate(self, credential_id, secret=None):
        """WP-5 (design v1.2 R-6, 2ストア突合): replaces an existing
        credential's digest in place -- this peer's application-plane
        store never needed a rotate operation before the in-band
        control-plane surface (`control_plane.ControlPlaneService.
        rotate_credential`) existed; that service is this method's first
        caller. `credential_id`/`application_id`/`role` are unchanged;
        only the secret (and therefore the stored digest) changes,
        mirroring `control_auth.ControlCredentialStore.rotate`'s own
        contract for the control-credential store. Fails closed on an
        unknown id."""
        secret = secret or secrets.token_urlsafe(32)
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("credential not found")
            item.digest = self._digest(secret)
            self.audit.record("credential_rotated", item.application_id, credential_id)
        return secret

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

    def authenticate(self, credential_id, secret, *, request_id=None):
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
            # Review B-1 (supervisor ruling 2026-09-03): tracked
            # SEPARATELY from the final `valid` flag below -- `authenticated`
            # is `True` only once the secret has matched a REAL, known
            # credential's stored digest. This is what the durable-audit
            # dispatch below keys its actor identity on: a subsequent
            # state check (disabled/revoked/app-disabled/expired) failing
            # is a REAL, known credential being refused (D-3's own
            # "credential の revoked" table entry, safe to record); an
            # unknown `credential_id` or a mismatched secret never reaches
            # `authenticated = True` at all, however `valid` itself is computed.
            authenticated = item is not None and digest_matches
            valid = authenticated
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
                # Phase 4 (design D-3): `AUTH_INVALID` is a durable-range
                # denial code (`http.py::_CLASSIFY_ORDER` maps every
                # `AuthenticationError` this class raises to it) -- routed
                # (coalesced) alongside the pre-existing 6-field-sink
                # record above, unconditionally (D-10).
                #
                # Review B-1 (blocker, supervisor ruling 2026-09-03): a
                # PRE-AUTH failure (`authenticated` is `False` -- unknown
                # `credential_id`, or a secret that did not match any
                # stored digest) must NEVER record the client-claimed id
                # as `actor_id`/`target_id`, and must NEVER let it into the
                # D-3 coalescing key -- `credential_id` here is untrusted,
                # unvalidated (no length/charset check anywhere upstream)
                # input. Doing so lets an attacker (a) defeat coalescing
                # entirely by varying the claimed id per attempt (id
                # rotation: N distinct ids -> N distinct durable rows, not
                # one coalesced window) and (b) flip the response from
                # `AUTH_INVALID` to `SERVICE_UNAVAILABLE` at will, once the
                # claimed id exceeds the `application_audit` length CHECK
                # (migration 0005) and the first-occurrence INSERT itself
                # starts failing. Only once `authenticated` is `True` (the
                # secret matched a real row, and ONLY its state refused it)
                # is the real, resolved `item.credential_id`/`item.
                # application_id` recorded -- matching r2db-api's own
                # identical pre-auth treatment (`actor_id=None`).
                if authenticated:
                    self._audit_router.route_denial(
                        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=request_id,
                        application_id=item.application_id, actor_type="application_credential",
                        actor_id=item.credential_id, role=None, operation="authenticate",
                        target_kind="credential", target_id=item.credential_id,
                    )
                else:
                    self._audit_router.route_denial(
                        reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=request_id,
                        application_id=None, actor_type="unknown", actor_id=None, role=None,
                        operation="authenticate", target_kind="credential", target_id=None,
                    )
                raise AuthenticationError("authentication failed")
            self.audit.record("authentication_succeeded", item.application_id,
                              item.credential_id, detail="role=" + item.role.value)
            return Principal(item.application_id, item.credential_id, item.role)

    def _route_reauth_denial(self, application_id, credential_id, *, request_id=None):
        """Phase 4 (design D-3): `assert_active`'s own re-check failure is
        `AUTH_INVALID` too (`http.py::_CLASSIFY_ORDER`) -- routed
        (coalesced) alongside the pre-existing 6-field-sink record, from
        each of `assert_active`'s four call sites below (a distinct
        `operation` value, `"assert_active"`, from `authenticate`'s own
        `"authenticate"` -- these coalesce separately, one window per call
        site, since D-3's key includes `operation`)."""
        self._audit_router.route_denial(
            reason_code="AUTH_INVALID", event_class="authentication_denied", request_id=request_id,
            application_id=application_id, actor_type="application_credential", actor_id=credential_id,
            role=None, operation="assert_active", target_kind="credential", target_id=credential_id,
        )

    def assert_active(self, principal, *, request_id=None):
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
                # Phase 4 (design D-3): `AUTH_STATE_UNAVAILABLE` is
                # explicitly OUTSIDE the durable-range inclusion set (D-3's
                # own confirmation text names it among the non-durable
                # codes) -- no durable/coalesced routing here, matching
                # `authenticate`'s own identical `authorization_state_
                # available` branch (which raises the same exception with
                # no durable routing either).
                raise AuthorizationStateUnavailable("authorization unavailable")
            item = self._credentials.get(getattr(principal, "credential_id", None))
            if item is None or item.application_id != getattr(principal, "application_id", None):
                self.audit.record("authentication_denied",
                                  getattr(principal, "application_id", None),
                                  getattr(principal, "credential_id", None),
                                  outcome="denied", detail="invalid_or_disabled")
                self._route_reauth_denial(
                    getattr(principal, "application_id", None), getattr(principal, "credential_id", None),
                    request_id=request_id)
                raise AuthenticationError("authentication failed")
            # WP-2 (design v1.2 R-4): `revoked` gates independently of
            # `enabled`, same reasoning as `authenticate` above -- an
            # already-open session's re-check must not survive a revoke
            # being masked by a later `enable`.
            if item.role != getattr(principal, "role", None) or not item.enabled or item.revoked:
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                self._route_reauth_denial(item.application_id, item.credential_id, request_id=request_id)
                raise AuthenticationError("authentication failed")
            if not self._applications.get(item.application_id, False):
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                self._route_reauth_denial(item.application_id, item.credential_id, request_id=request_id)
                raise AuthenticationError("authentication failed")
            if item.expires_at is not None and item.expires_at <= datetime.now(timezone.utc):
                self.audit.record("authentication_denied", item.application_id,
                                  item.credential_id, outcome="denied",
                                  detail="invalid_or_disabled")
                self._route_reauth_denial(item.application_id, item.credential_id, request_id=request_id)
                raise AuthenticationError("authentication failed")

    def _digest(self, secret):
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()
