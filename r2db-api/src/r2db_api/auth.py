"""Server-bound credential and lifecycle authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import os
import threading
from typing import Iterator, Mapping

from .errors import FoundationError, fail


def _fail_identified(code: str, message: str, *, status: int, credential_id: str, role: str | None = None) -> None:
    """Like `errors.fail`, but attaches the store's own identified
    `credential_id` onto the raised `FoundationError` as a plain dynamic
    attribute (`identified_credential_id`) -- never a dataclass field, so
    `FoundationError.problem()` (which only ever serializes `type`/`code`/
    `message`/`request_id`/`details`) cannot leak it into a response even by
    accident (R-8/§8 m-7: no existence-distinction disclosure). Round-2
    review (MA-2): `ControlPlaneService`'s durable denial audit needs a real
    actor to attribute an `AUTH_REVOKED`/identified-`AUTH_INVALID` denial to
    -- a truthful `attributed` R-11 declaration requires it. Used only for
    the "a matching verifier was found, but the credential is revoked/
    disabled" cases below; "no matching verifier at all" has no credential to
    identify and keeps using plain `errors.fail`.

    Phase 3.5 WP-4: `role`, when given, is attached the same way
    (`identified_role`) -- `ControlPlaneService._authenticate`'s denial audit
    needs the identified credential's actual role (never a hardcoded
    `"control"`) now that a control-credential-table row may be `"audit"`.
    """
    exc = FoundationError(code, message, {}, status)
    exc.identified_credential_id = credential_id
    if role is not None:
        exc.identified_role = role
    raise exc


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


@dataclass(frozen=True)
class ControlCredentialRecord:
    """`credentials`/`CredentialRecord`'s counterpart for control
    credentials (R-2) -- deliberately carries no `application_id` field at
    all: a control credential belongs to no Application (design docs/design/
    R2DB_CCR14_CONTROL_PLANE_V1.md R-2). `must_rotate` (R-5) is one addition
    beyond the shape `CredentialRecord` already has.

    Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
    §1-D/§4, P35-D12): `role` is a second addition -- `"control"` (the only
    value that existed before this WP) or `"audit"`. Both kinds share this
    one table/dataclass (contract `control_plane.authority`: "control
    credentials are rejected on data/schema endpoints" applies identically to
    either role -- neither is an application credential). Defaults to
    `"control"` so every pre-WP-4 caller (`bootstrap_control_credential`/
    `reset_control_credentials`, this repository's own pre-existing tests)
    is unaffected.
    """

    credential_id: str
    verifier: str
    enabled: bool = True
    revoked: bool = False
    must_rotate: bool = True
    role: str = "control"


@dataclass(frozen=True)
class ControlAuthContext:
    """`AuthContext`'s counterpart for control credentials -- `must_rotate`
    is exposed here (R-5: "must_rotate ... authenticate 結果に露出") so a
    caller (`ControlPlaneService`) can gate every operation except
    `capabilities`/self-`rotate` on it without a second lookup.

    Phase 3.5 WP-4: `role` (`"control"` or `"audit"`) is exposed the same
    way, so `ControlPlaneService` can authorize per-endpoint (design §1-D:
    an audit principal is accepted only on the 3 read-only control
    endpoints) without a second lookup either.
    """

    credential_id: str
    must_rotate: bool
    role: str = "control"


class _InMemoryWork:
    """The in-memory pair's (`CredentialStore`/`ControlCredentialStore`)
    unit-of-work handle (R-6/§8 B-2). Carries no state of its own -- the
    in-memory stores' `unit_of_work()` below implements "roll back on
    exception" by snapshotting `self._records` before entering and
    restoring that snapshot if the `with` block raises, not through
    anything this handle holds. It exists purely so every state-changing
    method's call surface matches `PostgresCredentialStore`'s (which does
    need its handle to carry a real connection) -- a caller that is generic
    over both store implementations (`ops.py`, `ControlAuthority`) can pass
    whatever `unit_of_work()` handed it straight through without knowing
    which implementation it is holding.
    """

    __slots__ = ()


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

    @contextmanager
    def unit_of_work(self) -> Iterator[_InMemoryWork]:
        """R-6/§8 B-2: a pseudo-transaction for the in-memory store --
        snapshots `self._records` before the `with` block runs and restores
        that exact snapshot if the block raises, so a fault injected
        partway through a caller's sequence of state-changing calls (e.g.
        `ops.py`'s bootstrap: issue a control credential, then write its
        audit event, both inside one `with unit_of_work()`) leaves no
        partially-applied change behind -- the same guarantee `conn.
        rollback()` gives the Postgres pair's `unit_of_work()` below.
        """
        snapshot = dict(self._records)
        work = _InMemoryWork()
        try:
            yield work
        except BaseException:
            self._records = snapshot
            raise

    def add(self, credential_id: str, application_id: str, role: str, secret: str, *, work: _InMemoryWork) -> None:
        """`work` is a required keyword-only argument (R-6/§8 B-2, round-2
        review ruling (A)): every caller must hold a handle from `self.
        unit_of_work()` before calling this. Omitting it is a `TypeError`
        (Python enforces this at the call boundary -- no default value is
        given). Round 1 of this WP made `work` optional with an auto-
        managed fallback (a second, internally-opened `unit_of_work()` per
        call) specifically to avoid touching `r2db-api/conformance/
        conformance_adapter_r2db_http.py` -- the independent review (round
        2) measured that fallback actually splitting a caller's own
        multi-call transaction onto a second connection/snapshot silently
        (and hard-failing outright at `pool_size=1` for the Postgres pair),
        which is exactly the hazard design §7 warns about. The scope for
        this WP was extended to include that adapter (and `test_http.py`,
        `test_foundation.py`) specifically so this could be fixed properly
        instead of worked around -- see the WP-2 implementation report's
        Round 2 section for the full history and the call-site follow-up.
        """
        if role not in {"runtime", "developer"}:
            fail("VALIDATION_FAILED", "Application credentials require runtime or developer role.")
        self._records[credential_id] = CredentialRecord(credential_id, application_id, role, self.verifier(secret))

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: _InMemoryWork) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        record = self._records.get(credential_id)
        if record is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        # Revocation is terminal (contract 1.1.0 lifecycle.credential): once
        # a credential is revoked, no control-plane call -- including this
        # one -- may clear that flag again. `enabled` remains freely
        # settable (disable/re-enable is a distinct, non-terminal state),
        # but `revoked=False` against an already-revoked record is refused
        # rather than silently applied.
        if revoked is False and record.revoked:
            fail("VALIDATION_FAILED", "Revocation is terminal; a revoked credential cannot be un-revoked.")
        self._records[credential_id] = CredentialRecord(record.credential_id, record.application_id, record.role, record.verifier, record.enabled if enabled is None else enabled, record.revoked if revoked is None else revoked)

    def rotate(self, credential_id: str, secret: str, *, work: _InMemoryWork) -> None:
        """§8 M-2's remediation: the in-memory store had no `rotate` at all
        before this WP -- only `PostgresCredentialStore.rotate` existed.
        Semantics deliberately match that existing Postgres implementation
        exactly (read, not re-derived): replaces `verifier` only, touches no
        other field, and does **not** refuse a revoked credential (the
        existing Postgres `rotate` never checked `revoked` either -- see
        `credential_store.py::PostgresCredentialStore.rotate`). This is
        distinct from the *new* `ControlCredentialStore.rotate` below, which
        does refuse a revoked control credential (§2 M-2 of the control-
        plane design) -- that rule is specific to the new control-credential
        HTTP `rotate` endpoint's semantics (WP-3), not a retrofit onto this
        pre-existing application-credential store method. `work` is required
        (see `add`'s docstring above for the round-2 ruling this follows).
        """
        record = self._records.get(credential_id)
        if record is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        self._records[credential_id] = CredentialRecord(record.credential_id, record.application_id, record.role, self.verifier(secret), record.enabled, record.revoked)

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
        if record is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        # revoked before enabled, matching authenticate()'s own order above
        # and PostgresCredentialStore.assert_active's identical order
        # (credential_store.py): a credential that is both revoked and
        # disabled must report AUTH_REVOKED here, not AUTH_INVALID, so the
        # two stores never disagree on which code an identical state
        # combination produces.
        if record.revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not record.enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
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

    def get_state(self, credential_id: str) -> tuple[bool, bool] | None:
        """Read-only existence/state probe (CCR-14 WP-3, `ControlPlaneService`):
        returns `(enabled, revoked)` for `credential_id`, or `None` if no such
        row exists. Not part of this store's pre-WP-3 call surface -- added so
        the control-plane service can (a) resolve a `credential_id` against
        this store without mutating it, as half of the "query both stores,
        never trust the `crd_`/`ctl_` prefix as semantics" dual-store
        resolution design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md §2 calls
        for, and (b) enforce its own revoked-refusal on `rotate` (this store's
        own `rotate` deliberately does not check `revoked` -- see its
        docstring -- so the control-plane HTTP `rotate` endpoint's *own*
        VALIDATION_FAILED-on-revoked rule, §2 M-2, reads this first rather
        than duplicating a check into this store that would change its
        existing, deliberately-unchecked behaviour for `ops.py`'s callers).
        """
        record = self._records.get(credential_id)
        if record is None:
            return None
        return (record.enabled, record.revoked)

    def list_all(self) -> tuple[CredentialRecord, ...]:
        """Read-only full enumeration (CCR-14 WP-3): `ControlPlaneService.
        list_credentials`'s application-credential half. Returns the typed
        `CredentialRecord` dataclass, never a raw dict -- callers read
        `.credential_id`/`.application_id`/`.role`/`.enabled`/`.revoked`
        only, so there is no way to accidentally forward `.verifier` into an
        API response or audit event (it is a real field on the dataclass,
        but nothing this WP touches ever reads it off a `list_all()` result)."""
        return tuple(self._records.values())

    def count_active_for_application(self, application_id: str) -> int:
        """Count of *not-yet-revoked* credentials for one application (CCR-14
        WP-3, R-7 `credentials_per_application`: "失効済みは数えない" -- a
        revoked credential must never count against this limit, or revoking
        credentials would perversely make onboarding harder)."""
        return sum(1 for record in self._records.values() if record.application_id == application_id and not record.revoked)


class ControlCredentialStore:
    """In-memory counterpart to `credential_store.
    PostgresControlCredentialStore` -- same call surface (design docs/
    design/R2DB_CCR14_CONTROL_PLANE_V1.md §3: "同一 call surface"), used
    wherever a control-plane store is needed without PostgreSQL (tests, the
    in-process conformance path). A control credential belongs to no
    Application (R-2) -- this store's records carry no `application_id` at
    all, unlike `CredentialStore` above.
    """

    def __init__(self, records: Mapping[str, ControlCredentialRecord] | None = None, *, pepper: str | None = None) -> None:
        self._records = dict(records or {})
        pepper = pepper or os.environ.get("R2DB_CONTROL_CREDENTIAL_PEPPER")
        if not pepper:
            raise ValueError("R2DB_CONTROL_CREDENTIAL_PEPPER is required")
        self._pepper = pepper.encode()
        self.available = True
        # design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3/WP-0 MA-2:
        # the last-active-control-credential revoke gate's count-then-write
        # must be serialized against a concurrent revoke of a DIFFERENT
        # credential racing the exact same decision (two concurrent revokes
        # of the last two active rows could otherwise both observe "count =
        # 2" and both proceed unconfirmed, leaving zero active control
        # credentials). `PostgresControlCredentialStore`'s equivalent is a
        # real `SELECT ... FOR UPDATE` inside the caller's own transaction
        # (`list_all_for_update`); this in-memory store has no separate
        # connection/transaction to lock rows on, so `unit_of_work` itself
        # holds this lock for its entire duration instead -- every state-
        # changing control-credential operation already goes through
        # exactly one `unit_of_work()` call, so this serializes all of them
        # against each other, not only the revoke gate.
        self._lock = threading.Lock()

    def verifier(self, secret: str) -> str:
        if not isinstance(secret, str):
            fail("VALIDATION_FAILED", "Credential secret has an invalid type.")
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    @contextmanager
    def unit_of_work(self) -> Iterator[_InMemoryWork]:
        with self._lock:
            snapshot = dict(self._records)
            work = _InMemoryWork()
            try:
                yield work
            except BaseException:
                self._records = snapshot
                raise

    def add(self, credential_id: str, secret: str, *, role: str = "control", work: _InMemoryWork) -> None:
        """Only the out-of-band CLI ceremonies (`ops.py`, connected with
        `R2DB_CONTROL_DSN`) ever call this -- there is no in-band issuance
        path for control OR audit credentials at all (spec/CCR_DISPOSITION.md
        "案B"; Phase 3.5 §1-D extends the same rule to `role="audit"`, P35-
        D12); this method exists on the store because the ritual needs it,
        not because anything else is meant to reach it. `work` is required
        (round-2 ruling (A) -- see `CredentialStore.add`'s docstring above).

        Phase 3.5 WP-4: `role` defaults to `"control"` (every pre-WP-4 caller
        is unaffected); `"audit"` is the one other accepted value.
        """
        if role not in {"control", "audit"}:
            fail("VALIDATION_FAILED", "Control-table credentials require control or audit role.")
        self._records[credential_id] = ControlCredentialRecord(credential_id, self.verifier(secret), role=role)

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: _InMemoryWork) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        record = self._records.get(credential_id)
        if record is None:
            fail("NOT_FOUND", "Control credential was not found.", status=404)
        # Same terminal-revocation rule as `CredentialStore.set_state`
        # (un-revoke is always refused) -- R-10's break-glass `enable-
        # control-credential` subcommand relies on this refusing exactly
        # the un-revoke case while still allowing a plain `enabled=True`
        # against a disabled-but-not-revoked row.
        if revoked is False and record.revoked:
            fail("VALIDATION_FAILED", "Revocation is terminal; a revoked control credential cannot be un-revoked.")
        self._records[credential_id] = ControlCredentialRecord(
            record.credential_id,
            record.verifier,
            record.enabled if enabled is None else enabled,
            record.revoked if revoked is None else revoked,
            record.must_rotate,
            record.role,
        )

    def rotate(self, credential_id: str, secret: str, *, work: _InMemoryWork) -> None:
        """R-5/§2 M-2: verifier replacement + `must_rotate=False` +
        (Postgres side) `updated_at` refresh, in one step. Unlike
        `CredentialStore.rotate` above, a revoked control credential
        refuses rotation outright (`VALIDATION_FAILED` -- §2 M-2's ruling:
        rotating a terminal-state row would return a "successfully
        rotated" secret that can never actually authenticate, which is a
        disguised failure). `work` is required (round-2 ruling (A)).

        Phase 3.5 WP-4: unchanged for `role="audit"` rows -- the out-of-band
        audit-credential issuance ceremony (`issue_audit_credential_ceremony`,
        below) calls this same method to clear `must_rotate` before the
        secret is ever printed (design §4 M-1: no in-band self-rotate exists
        for an audit principal, so the ceremony itself must complete the
        rotate half before distribution).
        """
        record = self._records.get(credential_id)
        if record is None:
            fail("NOT_FOUND", "Control credential was not found.", status=404)
        if record.revoked:
            fail("VALIDATION_FAILED", "A revoked control credential cannot be rotated.")
        self._records[credential_id] = ControlCredentialRecord(record.credential_id, self.verifier(secret), record.enabled, record.revoked, False, record.role)

    def has_any(self, *, include_revoked: bool = True, work: _InMemoryWork | None = None) -> bool:
        """§8 M-6: bootstrap's existence check must count revoked rows too
        -- "行が1件でも存在するか (失効済み含む)". `include_revoked=False` is
        kept as an explicit opt-out (unused by `ops.py` today) rather than
        removed, so a future caller that genuinely needs "any *live* row"
        is not tempted to hand-roll a second query against this store.

        `work` is a **read-only** parameter, deliberately optional (this is
        not one of the state-changing methods ruling (A) requires `work`
        on) -- it exists so a caller can run this check *inside* an
        already-open `unit_of_work()` (MA-3, round-2 review: the TOCTOU gap
        between a standalone existence check and the subsequent `add`) and
        have it participate in that same pseudo-transaction. For the
        in-memory store this makes no behavioural difference (there is no
        separate connection/snapshot to diverge from -- `self._records` is
        read directly either way), but the parameter is accepted here too
        so callers generic over both store implementations (`ops.py`) can
        pass it uniformly without an `isinstance` check.
        """
        del work  # no-op for the in-memory store; see docstring above
        if include_revoked:
            return bool(self._records)
        return any(not record.revoked for record in self._records.values())

    def revoke_all(self, *, work: _InMemoryWork) -> None:
        """Reset's "revoke every existing control credential" step (R-5) --
        called inside the same `unit_of_work()` as the new credential's
        `add()` and the canonical audit write, by `ops.py cmd_reset`, so
        the whole reset is one atomic transaction (design §7: "reset の原子
        性"). `work` is required (round-2 ruling (A)).
        """
        for credential_id, record in list(self._records.items()):
            self._records[credential_id] = ControlCredentialRecord(record.credential_id, record.verifier, record.enabled, True, record.must_rotate, record.role)

    def authenticate(self, secret: str | None) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        for record in self._records.values():
            if hmac.compare_digest(record.verifier, self.verifier(secret)):
                if record.revoked:
                    _fail_identified("AUTH_REVOKED", "Credential is not active.", status=401, credential_id=record.credential_id, role=record.role)
                if not record.enabled:
                    _fail_identified("AUTH_INVALID", "Credential is not active.", status=401, credential_id=record.credential_id, role=record.role)
                return ControlAuthContext(record.credential_id, record.must_rotate, record.role)
        fail("AUTH_INVALID", "Credential is not valid.", status=401)

    def assert_active(self, context: ControlAuthContext) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        record = self._records.get(context.credential_id)
        if record is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        if record.revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not record.enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        return ControlAuthContext(record.credential_id, record.must_rotate, record.role)

    def get_state(self, credential_id: str) -> tuple[bool, bool] | None:
        """`CredentialStore.get_state`'s control-credential counterpart
        (CCR-14 WP-3) -- see that docstring for why this exists."""
        record = self._records.get(credential_id)
        if record is None:
            return None
        return (record.enabled, record.revoked)

    def list_all(self) -> tuple[ControlCredentialRecord, ...]:
        """`CredentialStore.list_all`'s control-credential counterpart (CCR-14
        WP-3): `ControlPlaneService.list_credentials`'s control-credential
        half. `must_rotate` is a real field on the returned records, but
        design §2/§8 m-9 forbids exposing it in the `list_credentials`
        response -- `ControlPlaneService` itself is what omits it, not this
        method (this is a plain, complete read)."""
        return tuple(self._records.values())
