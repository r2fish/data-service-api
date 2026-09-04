"""In-memory control-credential store (design v1.2 R-4, WP-4).

The control plane's own credential kind is structurally distinct from an
application credential (`auth.CredentialStore`): no `application_id`, no
`role` (every row here IS a control credential), and one extra lifecycle
attribute no application credential has -- `must_rotate` (contract
`control_plane.bootstrap`/`reset`: "The initial control credential is not
permanent: it expires or requires rotation; the mechanism is
implementation-free").

Same-shape convention as `auth.CredentialStore` (issue/revoke/disable/
enable/get_state/authenticate), independently implemented for a genuinely
different row shape and lifecycle question set -- not a subclass or a
parameterized generalization of it (R-2's own "no code sharing" principle,
applied here within this one peer to its own two different credential
kinds; mirrors `credential_store_postgres.py`'s own identical choice to
duplicate `_DUMMY_DIGEST` rather than share it).

Also defines `_InMemoryWork`: a small, independent "unit of work" undo-log
token `control_plane.py` uses to make an in-memory state change and its
accompanying `control_audit.ControlAuditSink.append` call roll back
together as one unit (design R-6's "同一トランザクション" requirement,
realized for the in-memory backend without a real database transaction).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import RLock
from typing import Callable, Optional

from .credential_wire import compose_bearer_locator, split_bearer_locator
from .errors import AuthenticationError, NotFoundError, ValidationError

# WP-2's own `_DUMMY_DIGEST` rationale, restated for this store: a
# fixed-length (32 bytes), never-matching stand-in digest so `authenticate`
# below always performs a real `hmac.compare_digest` call, whether or not
# `credential_id` is present -- an unknown id must not return via a
# measurably cheaper code path than a known one that only fails the secret
# comparison.
_DUMMY_DIGEST = hashlib.sha256(b"mitatedb-control-credential-store-timing-parity-dummy").digest()


@dataclass(frozen=True)
class ControlPrincipal:
    credential_id: str
    must_rotate: bool
    # Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
    # V1.md §1-D/§4, P35-D12): `"control"` (the only value before this WP) or
    # `"audit"` -- lets `ControlPlaneService` authorize per-endpoint (an audit
    # principal is accepted only on the 3 read-only control endpoints) without
    # a second lookup. Defaulted so every pre-WP-5 positional/keyword
    # construction of this dataclass keeps working unchanged.
    role: str = "control"


class _InMemoryWork:
    """Shared undo-log transaction token. Any in-memory store's write
    method may call `on_rollback(fn)` to register how to undo the mutation
    it just made; `control_plane.py` (the sole opener of this token, always
    while holding its own coarse in-memory lock for the whole body) calls
    `rollback()` -- in reverse registration order -- if the body raises.
    Deliberately NOT tied to any one store class: this is what lets several
    different stores (`ControlCredentialStore` here, `control_audit.
    ControlAuditSink`, `control_plane.InMemoryApplicationRegistry`/
    `InMemoryCredentialRegistry`) all participate in one logical
    transaction despite being independent Python objects with no shared
    database connection to rely on.
    """

    __slots__ = ("_undo",)

    def __init__(self) -> None:
        self._undo: list[Callable[[], None]] = []

    def on_rollback(self, fn: Callable[[], None]) -> None:
        self._undo.append(fn)

    def rollback(self) -> None:
        while self._undo:
            fn = self._undo.pop()
            fn()


@dataclass
class _ControlCredential:
    credential_id: str
    digest: bytes
    must_rotate: bool = True
    enabled: bool = True
    revoked: bool = False
    # Phase 3.5 WP-5 (§1-D/§4, P35-D12): `"control"` or `"audit"` -- both
    # kinds share this one store/table (neither is an application
    # credential); issuance for both stays out-of-band only.
    role: str = "control"


class ControlCredentialStore:
    """Same-shape twin of `auth.CredentialStore` for control credentials.
    Every write method accepts an optional `work` (an `_InMemoryWork`): when
    given, the mutation registers its own undo with it (see `_InMemoryWork`
    above) instead of being permanent the instant this call returns; when
    omitted (the default), the mutation is immediately permanent -- exactly
    what a standalone parity test (this store used directly, with no
    enclosing `ControlPlaneService` transaction) needs.
    """

    def __init__(self, pepper: str) -> None:
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError("control credential pepper must be supplied externally (>=16 characters)")
        self._pepper = pepper.encode("utf-8")
        self._credentials: dict[str, _ControlCredential] = {}
        self._lock = RLock()

    def _digest(self, secret) -> bytes:
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def issue(self, *, must_rotate: bool = False, role: str = "control", credential_id: Optional[str] = None,
              secret: Optional[str] = None, work: Optional[_InMemoryWork] = None) -> tuple[str, str]:
        """Phase 3.5 WP-5: `role` defaults to `"control"` (every pre-WP-5
        caller -- `bootstrap_control_credential`/`reset_control_credentials`
        -- is unaffected); `"audit"` is the one other accepted value, used
        only by `control_plane.issue_audit_credential_ceremony`. Only the
        out-of-band CLI ceremonies ever call this method -- there is no
        in-band issuance path for either role (P35-D12).

        Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item A):
        returns a COMPOSED bearer now (`compose_bearer_locator`) -- this
        store's own "帯域外 store API" issuance point. `authenticate`
        below takes the RAW secret only (round 2 correction: real callers
        split it once at their own boundary -- see that method's own
        docstring). The stored `digest` is still computed from the RAW
        `secret`."""
        if role not in ("control", "audit"):
            raise ValidationError("control-table credentials require control or audit role")
        credential_id = credential_id or ("ctl_" + secrets.token_hex(12))
        secret = secret or secrets.token_urlsafe(32)
        with self._lock:
            self._credentials[credential_id] = _ControlCredential(
                credential_id=credential_id, digest=self._digest(secret), must_rotate=must_rotate, role=role)
        if work is not None:
            work.on_rollback(lambda: self._credentials.pop(credential_id, None))
        return credential_id, compose_bearer_locator(credential_id, secret)

    def revoke(self, credential_id: str, *, work: Optional[_InMemoryWork] = None) -> None:
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("control credential not found")
            previous = item.revoked
            # No code path anywhere in this class ever sets `revoked` back
            # to `False` -- the terminal-revocation invariant (SI-13,
            # contract `lifecycle.credential`) holds structurally.
            item.revoked = True
        if work is not None:
            work.on_rollback(lambda: setattr(item, "revoked", previous))

    def revoke_all(self, *, work: Optional[_InMemoryWork] = None) -> None:
        """R-6 reset ceremony primitive: revokes every row, including an
        already-revoked one (idempotent no-op for those). Phase 3.5 WP-5:
        deliberately stays role-agnostic -- `reset` revokes `role="audit"`
        rows too (the safe-side choice: reset is meant to wipe the whole
        control-table blast radius, not leave a stray audit credential
        live behind an operator's back)."""
        with self._lock:
            previous = {credential_id: item.revoked for credential_id, item in self._credentials.items()}
            for item in self._credentials.values():
                item.revoked = True
        if work is not None:
            def _undo() -> None:
                for credential_id, was_revoked in previous.items():
                    item = self._credentials.get(credential_id)
                    if item is not None:
                        item.revoked = was_revoked
            work.on_rollback(_undo)

    def disable(self, credential_id: str, *, work: Optional[_InMemoryWork] = None) -> None:
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("control credential not found")
            previous = item.enabled
            item.enabled = False
        if work is not None:
            work.on_rollback(lambda: setattr(item, "enabled", previous))

    def enable(self, credential_id: str, *, work: Optional[_InMemoryWork] = None) -> None:
        """Reverses `disable` only -- never touches `revoked` (contract
        `enable_credential.semantics`: "A revoked credential is not
        resurrected."). `authenticate` below gates on `revoked`
        independently, so a previously-revoked credential still cannot
        authenticate after this call even though `enabled` flips back to
        `True` unconditionally."""
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("control credential not found")
            previous = item.enabled
            item.enabled = True
        if work is not None:
            work.on_rollback(lambda: setattr(item, "enabled", previous))

    def rotate(self, credential_id: str, *, secret: Optional[str] = None,
               clear_must_rotate: bool = True, work: Optional[_InMemoryWork] = None) -> str:
        """Replaces the digest; by default also clears `must_rotate`
        (contract: "the mechanism is implementation-free" -- this store's
        own mechanism is "a real rotation completed"). A revoked
        credential's own row can still technically be rotated at the store
        level -- `control_plane.ControlPlaneService` is the one that
        refuses this at the policy layer (a revoked credential's rotation
        request is refused before this method is ever called), so this
        method itself stays a dumb primitive, mirroring `control_plane.py`'s
        module docstring on backends never re-deciding policy.

        Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item A):
        returns a COMPOSED bearer now -- same re-issuance discipline
        `issue` above follows. The stored `digest` is still computed from
        the RAW `secret`."""
        secret = secret or secrets.token_urlsafe(32)
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("control credential not found")
            previous_digest = item.digest
            previous_must_rotate = item.must_rotate
            item.digest = self._digest(secret)
            if clear_must_rotate:
                item.must_rotate = False
        if work is not None:
            def _undo() -> None:
                item.digest = previous_digest
                item.must_rotate = previous_must_rotate
            work.on_rollback(_undo)
        return compose_bearer_locator(credential_id, secret)

    def get_state(self, credential_id: str) -> Optional[tuple[bool, bool, bool]]:
        """`(enabled, revoked, must_rotate)` for `credential_id`, or `None`."""
        with self._lock:
            item = self._credentials.get(credential_id)
            return (item.enabled, item.revoked, item.must_rotate) if item is not None else None

    def list_all(self) -> list[tuple[str, bool, bool, bool, str]]:
        """`(credential_id, enabled, revoked, must_rotate, role)`.

        Phase 3.5 WP-5 (design §4/§1-B, P35-D7): `must_rotate` is now
        selected -- it was deliberately excluded before this WP (contract
        1.2.0's `CredentialsResult` item had no `must_rotate` property at
        all) -- `ControlPlaneService.list_credentials` exposes it on a
        control-table row now that contract 1.3.0 makes the field
        optional-additive. `role` is likewise now selected so that method's
        `role` key reads the real column instead of a hardcoded `"control"`
        literal.
        """
        with self._lock:
            return [(item.credential_id, item.enabled, item.revoked, item.must_rotate, item.role)
                   for item in self._credentials.values()]

    def locked_for_update(self, work: Optional[_InMemoryWork] = None) -> list[tuple[str, bool, bool, str]]:
        """Same rows as `list_all()` minus `must_rotate`, read while holding
        this store's own lock -- the in-memory analogue of a PostgreSQL
        `SELECT ... FOR UPDATE` (`control_plane.py`'s revoke-last-active-
        control-credential gate, and the reset ceremony's own confirmation-
        phrase fingerprint, both need to read this list atomically with
        respect to any other concurrent mutation of it). `work` is accepted
        for call-surface parity with `control_credential_store_postgres.
        PostgresControlCredentialStore.locked_for_update` (which requires
        an open transaction to run `FOR UPDATE` against) but is not needed
        here: this store's own `self._lock`, held for the duration of this
        call, already serializes every other write method above against
        this read.

        Phase 3.5 WP-5: `role` is now selected too -- the revoke gate's own
        "active" count (`ControlPlaneService.revoke_credential`) must count
        only `role="control"` rows; an `"audit"` credential existing
        alongside the sole active control credential must not be allowed to
        mask that control credential as "not the last one" (an audit
        credential cannot perform any control-plane management operation at
        all, so it does not relieve the lockout the gate exists to
        prevent).
        """
        del work
        with self._lock:
            return [(item.credential_id, item.enabled, item.revoked, item.role) for item in self._credentials.values()]

    def has_any(self, *, include_revoked: bool = True, work: Optional[_InMemoryWork] = None) -> bool:
        """Phase 3.5 WP-5: deliberately stays role-agnostic (any row, control
        OR audit, counts) -- `bootstrap`'s own existence check and `reset`'s
        recovery path both still need to see an orphan `role="audit"` row
        as "a control-table row exists" (an orphan audit row blocks
        bootstrap; `reset` recovers it, since `revoke_all` below is
        role-agnostic too)."""
        del work  # in-memory: the caller's own external lock already serializes this read
        with self._lock:
            if include_revoked:
                return bool(self._credentials)
            return any(not item.revoked for item in self._credentials.values())

    def authenticate(self, secret) -> ControlPrincipal:
        """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
        裁定 1): `secret` is the FULL presented bearer -- this method is
        this store's own single receiving boundary, splitting via `split_
        bearer_locator` exactly ONCE, HERE, matching every OTHER store on
        this peer (`auth.CredentialStore.authenticate`, `credential_store_
        postgres.PostgresCredentialStore.authenticate`, `control_
        credential_store_postgres.PostgresControlCredentialStore.
        authenticate`) and r2db-api's own `auth.ControlCredentialStore.
        authenticate` (same name, same one-bearer-in signature). Neither
        real receiving shape this store serves (HTTP-fronted, via `control_
        http.py`'s own `authenticate_control`; the in-process conformance
        adapter's `_ReconciledControlBackend.authenticate_control`) splits
        the bearer itself any more -- both now pass it through verbatim,
        exactly once, to this single choke point. A malformed `secret`
        (no `.`, an empty half, or a NUL byte in either half) fails BEFORE
        any lookup or digest comparison at all -- SI-15 fail-closed,
        mirroring `auth.CredentialStore.authenticate`'s identical `locator
        is None` branch."""
        locator = split_bearer_locator(secret)
        if locator is None:
            raise AuthenticationError("control authentication failed")
        credential_id, secret_part = locator
        with self._lock:
            item = self._credentials.get(credential_id)
            stored_digest = item.digest if item is not None else _DUMMY_DIGEST
            digest_matches = hmac.compare_digest(stored_digest, self._digest(secret_part))
            valid = item is not None and digest_matches and item.enabled and not item.revoked
            if not valid:
                raise AuthenticationError("control authentication failed")
            return ControlPrincipal(item.credential_id, item.must_rotate, item.role)


__all__ = ["ControlCredentialStore", "ControlPrincipal", "_InMemoryWork"]
