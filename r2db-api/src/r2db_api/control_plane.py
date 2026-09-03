"""`ControlPlaneService` (CCR-14 WP-3): the control-plane semantics layer.

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.5, §2 (endpoint/service mapping and the common processing order), §3
(service-layer composition), R-5 (must_rotate gate)/R-6 (durable audit)/R-7
(limits)/R-9 (capability discovery)/R-11 (deterrence declarations), §5's
WP-3 row, §7 (risk/review focus), and §10/§11 (WP-1/WP-2 supervisor
decisions this WP inherits: required `work` on every store's state-changing
method, the `applications` two-state registry, `ControlCredentialStore`'s
own revoked-refusing `rotate`).

Architecture (§0/§3, a bound supervisor decision): `ControlPlaneService` is a
*shared semantics layer* -- processing order, authentication, the
must_rotate gate, `role=control` issuance refusal, R-7 limits, R-6 audit
(including the same-transaction guarantee and durable denial recording), and
the R-11 deterrence declarations all live *here*, never in a backend and
never (in a later WP) in the HTTP binding layer. This mirrors the exact
"拒否の所在" lesson design §3/§7 calls out from an earlier phase (a prior
B-1 defect: a refusal implemented in the bind layer instead of the service
layer silently stopped applying through a second, in-process call path).

Two backend implementations share one call surface (`ControlBackend`,
below), the same pairing convention CCR-13 established for storage cells:

- `InMemoryControlBackend` wraps `ControlAuthority` (+ the in-memory
  `CredentialStore`/`ControlCredentialStore`). Every operation `Control
  Authority` already implements (register/enable/disable application,
  issue/set-state credential) is delegated to it, not reimplemented here --
  this is what keeps `ControlAuthority`'s own semantics (and its own,
  pre-existing in-memory audit trail, used by the in-process conformance
  adapter and this repository's own tests) authoritative for both callers
  instead of forking into two implementations of "register an application".
  Operations `ControlAuthority` has no concept of at all (list, rotate,
  control-credential lifecycle) talk to the in-memory stores directly.
- `PostgresControlBackend` talks to the WP-2 Postgres store trio directly
  (`PostgresCredentialStore`/`PostgresControlCredentialStore`/the new
  `PostgresApplicationRegistry`) -- there is no `DataService`/`ControlAuthority`
  in a real WP-4+ deployment of this surface at all (it is a *separate*
  process from the application-plane API, R-1/R-3), so direct-to-store is
  the only option, not a shortcut.

Both backends are deliberately dumb: everything a backend method raises
(`NOT_FOUND`/`CONFLICT`/`VALIDATION_FAILED` from the underlying stores) is
allowed to surface through unchanged; `ControlPlaneService` never asks a
backend "is this allowed" -- it decides that itself, then tells the backend
what to persist.

Single-commit rule (design §5, still binding for this WP): `control_plane`
stays declared `unavailable` in every public capability document this
codebase already emits (`DataService.capabilities`, `config/capabilities.
json`) -- neither of those files is touched here. This module connects to no
HTTP surface, ASGI app, or composition root; `control_http.py`/`control_main.
py` do not exist yet (WP-4). Constructing a `ControlPlaneService` is, as of
this WP, something only this module's own tests do.
"""
from __future__ import annotations

from contextlib import contextmanager
import re
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Iterator, Protocol, runtime_checkable
import uuid

from .audit import ControlAuditSink
from .audit_query import (
    DECLARED_AUDIT_EVENT_CLASSES,
    DECLARED_AUDIT_OPERATIONS,
    DECLARED_AUDIT_TARGET_KINDS,
    DECLARED_COALESCING_WINDOW_MS,
    AuditQueryReader,
    decode_cursor,
    encode_cursor,
)
from .auth import AuthContext, ControlAuthContext, ControlCredentialStore, CredentialStore, _InMemoryWork
from .errors import FoundationError, fail
from .limits import ControlPlaneLimits
from .service import ControlAuthority
from .structured import revoke_last_control_credential_confirmation_phrase

# Round-2 review MI-10: `credential_store.py` imports `psycopg` unconditionally
# -- importing its Postgres classes at module level here would make this
# module (and therefore `PostgresControlBackend`) require `psycopg` just to
# *import*, even for a caller that only ever constructs `InMemoryControlBackend`.
# `from __future__ import annotations` (top of this file) already makes every
# annotation in this module a lazy string (PEP 563), so these names are safe
# to use in type hints below without ever being evaluated at runtime; the
# real import only happens for a type checker (`TYPE_CHECKING`), never at
# import time. `PostgresControlBackend.__init__` never constructs these
# classes itself -- it only stores already-constructed instances a caller
# passed in -- so no runtime reference to the real classes is needed at all.
if TYPE_CHECKING:
    from .credential_store import (
        PostgresApplicationRegistry,
        PostgresControlAuditSink,
        PostgresControlCredentialStore,
        PostgresCredentialStore,
    )

# Contract `control_plane.identifiers` / `ApplicationRegistrationRequest`/
# `CredentialIssueRequest` (`spec/data-service-api.v1.json`): the stricter
# lowercase-slug rule, shared verbatim with the Postgres provisioning
# functions' own identical check (0002's `begin_provision_application`).
_APPLICATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,32}$")

_ALL_ISSUABLE_ROLES = ("runtime", "developer", "control")

# R-11 (design v1.3, §2/§5): fixed, verbatim deterrence text -- "宣言=実挙動"
# means these strings are conformance-testable literals, never regenerated
# per call. Round-2 review MA-2: two distinct forms, not one -- a denial
# audit row is only ever "attributed" (actor_type/actor_id identify a real
# credential) when the store actually identified one before refusing it
# (AUTH_REVOKED, or a matching-but-disabled AUTH_INVALID); an *unattributed*
# denial (no matching secret at all, or no secret presented) must not claim
# attribution it does not have -- that would itself be a false R-11
# declaration (R-11 v1.3 forbids exactly this). `_deny()` below picks
# whichever form matches the actual audit row it just wrote. `futility` is
# attached only to a `role=control` issuance refusal, on top of whichever
# form applies (issuance refusals are always attributed -- the actor is
# always already authenticated by the time that check runs).
_RECORDED_DECLARATION = "This request is durably recorded; not even a control credential can erase that record."
_ATTRIBUTED_DECLARATION = (
    "This request is durably recorded and attributed to the credential that made it; "
    "not even a control credential can erase that record."
)
_FUTILITY_DECLARATION = (
    "No in-band path exists to create a control credential; issuance is limited to the "
    "operator bootstrap/reset ceremony, with no exceptions."
)

# Contract 1.2.0 `destructive_confirmation` (design docs/design/
# DESTRUCTIVE_CONFIRMATION_V1.md R-3): the last-active-control-credential
# revoke gate's own four declarations. Fixed, verbatim text -- like R-11's
# declarations above, these are conformance-testable literals, never
# regenerated per call. `reversible_alternative` is truthful about a real
# limitation (WP-0 m-7, precision corrected by Opus review minor m-6):
# `disable_credential` genuinely reverses this specific revoke (a disable,
# not a revoke), but re-enabling the LAST disabled control credential is
# itself gated behind its OWN separate out-of-band break-glass procedure
# (`enable-control-credential`) -- distinct from `recovery`'s own `reset`
# ceremony below, not "the same" one (an earlier revision of this text
# conflated the two, which is not truthful: `reset` mints a fresh
# credential and revokes every prior one, while `enable-control-credential`
# re-enables the SAME still-existing, merely-disabled row -- two different
# procedures, not one). Either way, the "alternative" does not actually
# avoid needing an out-of-band step, it only defers which one. `recovery`
# matches `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13 (WP-0
# m-2: that runbook, not DEPLOYMENT_RUNBOOK).
_REVOKE_LAST_CONTROL_CREDENTIAL_CONSEQUENCE = (
    "The last remaining active control credential is revoked; every in-band control-plane "
    "management credential is then unusable until the out-of-band break-glass reset ceremony "
    "runs (an audit credential, if any, remains usable but is read-only and cannot manage "
    "credentials)."
)
_REVOKE_LAST_CONTROL_CREDENTIAL_REVERSIBLE_ALTERNATIVE = (
    "disable_credential reverses (this specific revoke is terminal, a disable is not) -- but "
    "re-enabling the last disabled control credential still requires its own separate out-of-band "
    "break-glass procedure (enable-control-credential, distinct from this denial's own recovery, the "
    "reset ceremony), so disabling instead only defers needing an out-of-band step, it does not avoid it."
)
_REVOKE_LAST_CONTROL_CREDENTIAL_RECOVERY = (
    "The out-of-band operator reset ceremony (r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md "
    "§12/§13) issues a fresh control credential."
)

# R-6 (design §4): exactly the denial codes design's own enumeration names
# as requiring durable audit (authentication failure, the must_rotate gate,
# and the `role=control` capability refusal). `AUTH_STATE_UNAVAILABLE` is
# deliberately excluded -- it is a service-health outcome (the store itself
# is unreachable/unavailable), not an adversarial denial, and attempting a
# durable write in that same moment is likely to fail too, compounding the
# outage into a second 503 for no benefit. Round-2 review MA-1 (supervisor
# ruling): `AUTH_REQUIRED` (no secret presented at all) is INCLUDED here --
# it is the cheapest possible probe against this surface, and the rate
# limiter already runs before this check (design §4's own "監査増幅の防止"
# reasoning already covers it), so there is no audit-amplification concern
# left to justify excluding it; leaving it out created exactly the asymmetry
# R-11 exists to close (a garbage-secret probe left a trace, a no-header
# probe left none).
_AUDITED_AUTH_FAILURE_CODES = frozenset({"AUTH_INVALID", "AUTH_REVOKED", "AUTH_REQUIRED"})

# Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-D/§4,
# P35-D12): contract `control_plane.authority` -- "An audit credential is
# accepted only on the read-only control_capabilities, list_applications,
# and list_credentials endpoints; every other control endpoint fails it
# closed with FORBIDDEN." An allow-list (not a deny-list), for the identical
# reason `_gate_must_rotate` below is one: a deny-list silently fails open
# the moment a new control endpoint is added and nobody remembers to list it
# (design's own explicit warning, carried over from R-5's must_rotate gate).
#
# Phase 4 WP-2(b) (design D-5, work order P4-D4 item 5, contract 1.4.0
# subordinate ruling 9(b)): `audit_query` joins this allow-list -- an
# `audit`-role principal may now read audit evidence too, alongside the
# three pre-existing read-only endpoints. Every other control endpoint
# remains fail-closed FORBIDDEN for this role, unchanged.
_AUDIT_ROLE_ALLOWED_OPERATIONS = frozenset({"control_capabilities", "list_applications", "list_credentials", "audit_query"})

# Phase 4 WP-2(b) (design D-5): `audit_query`'s own default/maximum page
# size -- contract `AuditQueryRequest.limit` bounds the wire value to
# `[1, 1000]`; `_DEFAULT_AUDIT_QUERY_LIMIT` is what an omitted `limit`
# defaults to.
_DEFAULT_AUDIT_QUERY_LIMIT = 100
_MAX_AUDIT_QUERY_LIMIT = 1000
_MAX_AUDIT_QUERY_EVENT_CLASSES = 20


def _new_credential_id() -> str:
    return "crd_" + secrets.token_hex(8)


def _new_control_credential_id() -> str:
    return "ctl_" + secrets.token_hex(8)


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


@runtime_checkable
class ControlBackend(Protocol):
    """The shared call surface `InMemoryControlBackend`/`PostgresControl
    Backend` both implement (CCR-13's cell-pair precedent, design §0). Pure
    storage/authenticate plumbing -- see this module's own header for why
    `ControlPlaneService` never asks a backend for a policy judgment.
    """

    def authenticate(self, secret: str | None) -> ControlAuthContext: ...

    # Phase 4 WP-2(b) (design D-5): a SEPARATE probe against the
    # APPLICATION-credential universe (`credentials`, never `control_
    # credentials`) -- `audit_query`'s own authority check needs to
    # recognize "this secret genuinely belongs to a real, active
    # application credential" BEFORE ever presenting it to `authenticate`
    # above, so it can answer an identified, attributed `FORBIDDEN` rather
    # than let it fall through as an ordinary, unattributed `AUTH_INVALID`
    # against the control-credential store it was never issued against
    # (contract `control_endpoints.audit_query.semantics`: "Application
    # credentials are denied"). Returns `None` for every failure mode
    # (missing/unknown/revoked/disabled secret) -- never raises -- so the
    # caller can use it as a pure probe without a `try/except` at every
    # call site.
    def authenticate_application(self, secret: str | None) -> AuthContext | None: ...

    # -- applications --
    def applications_unit_of_work(self) -> ContextManager[Any]: ...
    def application_exists(self, application_id: str) -> bool: ...
    def applications_count(self) -> int: ...
    def list_applications(self) -> list[tuple[str, bool]]: ...
    def register_application(self, application_id: str, *, work: Any) -> None: ...
    def set_application_enabled(self, application_id: str, enabled: bool, *, work: Any) -> None: ...

    # -- application credentials --
    def credentials_unit_of_work(self) -> ContextManager[Any]: ...
    def credential_state(self, credential_id: str) -> tuple[bool, bool] | None: ...
    def credentials_active_count(self, application_id: str) -> int: ...
    def list_credentials(self) -> list[tuple[str, str, str, bool, bool]]: ...
    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str, *, work: Any) -> None: ...
    def rotate_credential(self, credential_id: str, secret: str, *, work: Any) -> None: ...
    def set_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None: ...

    # -- control credentials --
    def control_credentials_unit_of_work(self) -> ContextManager[Any]: ...
    def control_credential_state(self, credential_id: str) -> tuple[bool, bool] | None: ...
    # Phase 3.5 WP-4: rows now carry `must_rotate`/`role` too (§1-B/§1-D) --
    # `(credential_id, enabled, revoked, must_rotate, role)`.
    def list_control_credentials(self) -> list[tuple[str, bool, bool, bool, str]]: ...
    # `(credential_id, enabled, revoked, role)` -- `role` is what lets the
    # last-active-CONTROL-credential revoke gate (§4) exclude `role="audit"`
    # rows from its own "active" count.
    def control_credentials_locked(self, work: Any) -> list[tuple[str, bool, bool, str]]: ...
    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None: ...
    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None: ...

    # -- issuance freeze (Phase 3.5 WP-4, §4/§1-E, P35-D6) --
    def application_issuance_frozen(self, application_id: str) -> bool: ...
    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work: Any) -> None: ...


class InMemoryControlBackend:
    """`ControlBackend`'s in-memory implementation. Wraps a `ControlAuthority`
    (whose `DataService`/`CredentialStore` must themselves be the in-memory
    implementations -- this backend never checks that, matching how
    `ControlAuthority` itself is backend-agnostic; a caller that hands this
    class a Postgres-backed `ControlAuthority` gets undefined behaviour, not
    a defended error) plus a standalone in-memory `ControlCredentialStore`
    (control credentials have no relationship to `ControlAuthority` at all --
    design R-2: a control credential belongs to no Application, and
    `ControlAuthority`'s pre-existing surface has no concept of one).

    There is no separate in-memory "applications registry" store class: this
    backend reads/restores `ControlAuthority`'s own `DataService`'s `_cells`/
    `_disabled_apps` directly (design §0: "in-memory側はControlAuthority/
    DataServiceの既存状態に整合する形--backend内で表現してよい"). Every
    *mutation* still goes through `ControlAuthority.register_application`/
    `.set_application_enabled` -- never a direct dict write -- so `Control
    Authority`'s own pre-existing in-memory audit trail observes every
    control-plane application change too (this is what the WP-3 work
    order's test item 9, "ControlAuthority委譲", checks for).
    """

    def __init__(self, authority: ControlAuthority, control_credentials: ControlCredentialStore) -> None:
        self._authority = authority
        # `ControlAuthority` has no public accessor for the `CredentialStore`
        # it holds (by design -- it is the trusted lifecycle authority, not
        # a data-access facade); reaching `._service._credentials` directly
        # mirrors `ControlAuthority._control_event`'s own established
        # precedent of reading `self._service`'s private state from inside
        # this package (service.py is not modified to add a new public
        # accessor here -- the WP-3 work order scopes service.py's only
        # change to the `work=` keyword argument addition).
        self._credentials: CredentialStore = authority._service._credentials  # noqa: SLF001
        self._control_credentials = control_credentials
        # Phase 3.5 WP-4 (§4/§1-E, P35-D6): per-application issuance freeze
        # has no home in `DataService`/`ControlAuthority` at all (it is a
        # control-plane-only concept `DataService` has never needed to know
        # about) -- unlike every other piece of state this backend reads off
        # `ControlAuthority`'s own `DataService` (class docstring above), this
        # one small set is genuinely new backend-local state, mutated only
        # through `set_application_issuance_frozen` below (the CLI's
        # `freeze-issuance`/`unfreeze-issuance`, or this repository's own
        # tests reaching in directly the same way they already do for
        # `revoke_control_credential_directly`-style harness helpers).
        self._frozen_applications: set[str] = set()

    def authenticate(self, secret: str | None) -> ControlAuthContext:
        return self._control_credentials.authenticate(secret)

    def authenticate_application(self, secret: str | None) -> AuthContext | None:
        # Phase 4 WP-2(b): `self._credentials` (the SAME application-
        # credential store `issue_credential`/`rotate_credential`/`set_
        # credential_state` already reach via `ControlAuthority`, see
        # __init__'s own docstring) -- reused for a READ-only probe here,
        # never mutated. `FoundationError` (AUTH_REQUIRED/AUTH_INVALID/
        # AUTH_REVOKED/AUTH_STATE_UNAVAILABLE) collapses to `None`
        # uniformly -- this probe only ever answers "yes, this is a real,
        # currently-usable application credential" or "no".
        if not secret:
            return None
        try:
            return self._credentials.authenticate(secret)
        except FoundationError:
            return None

    # ---- applications --------------------------------------------------

    @contextmanager
    def applications_unit_of_work(self) -> Iterator[_InMemoryWork]:
        """No store backs the in-memory "applications registry" (see class
        docstring) -- this context manager snapshots `DataService._cells`/
        `._disabled_apps` itself, exactly mirroring `CredentialStore.
        unit_of_work()`'s own snapshot/restore pattern one level up, so a
        fault injected into the audit sink append that follows a `register_
        application`/`set_application_enabled` call inside this block still
        leaves no partially-applied registry change behind (R-6's "同一トラ
        ンザクション" guarantee, realized here without a real store).

        Round-2 review MI-1: `register_application`/`set_application_enabled`
        (via `ControlAuthority`) also append an "allow" event to `ControlAuth
        ority`'s own pre-existing in-memory audit trail (`DataService._audit`)
        *before* this block's own `control_audit` append runs -- if that
        later append then faults and this block rolls back, the secondary
        trail must not be left claiming an "allow" that, from `control_audit`
        's point of view, never durably happened. Snapshotting its length and
        truncating back to that length on rollback keeps the two trails
        consistent (`ControlAuthority`'s trail is not itself durable/gated by
        R-6 -- it is the pre-existing in-process observability the conformance
        adapter reads -- but it must never contradict `control_audit`)."""
        service = self._authority._service  # noqa: SLF001 -- see __init__
        cells_snapshot = dict(service._cells)  # noqa: SLF001
        disabled_snapshot = set(service._disabled_apps)  # noqa: SLF001
        authority_audit_len = len(service._audit._events)  # noqa: SLF001
        # Phase 3.5 WP-4 (round-2 independent review n-2): `_frozen_
        # applications` (§4/§1-E) is this block's own state too --
        # `set_application_issuance_frozen` is a state-changing method
        # reachable through this same `work` handle, so it needs the same
        # snapshot/rollback coverage as `_cells`/`_disabled_apps` above, or a
        # fault injected after a freeze/unfreeze call inside this block would
        # leave the frozen-set change applied despite the block rolling back
        # everything else.
        frozen_snapshot = set(self._frozen_applications)
        work = _InMemoryWork()
        try:
            yield work
        except BaseException:
            service._cells = cells_snapshot  # noqa: SLF001
            service._disabled_apps = disabled_snapshot  # noqa: SLF001
            self._frozen_applications = frozen_snapshot
            del service._audit._events[authority_audit_len:]  # noqa: SLF001
            raise

    def application_exists(self, application_id: str) -> bool:
        return application_id in self._authority._service._cells  # noqa: SLF001

    def applications_count(self) -> int:
        return len(self._authority._service._cells)  # noqa: SLF001

    def list_applications(self) -> list[tuple[str, bool]]:
        service = self._authority._service  # noqa: SLF001
        return [(app_id, app_id not in service._disabled_apps) for app_id in service._cells]  # noqa: SLF001

    def register_application(self, application_id: str, *, work: Any) -> None:
        del work  # rollback is `applications_unit_of_work`'s job, not this call's
        self._authority.register_application(application_id)

    def set_application_enabled(self, application_id: str, enabled: bool, *, work: Any) -> None:
        del work
        self._authority.set_application_enabled(application_id, enabled)

    # ---- application credentials ---------------------------------------

    @contextmanager
    def credentials_unit_of_work(self) -> Iterator[Any]:
        """Round-2 review MI-1: `issue_credential`/`set_credential_state`
        (`ControlPlaneService` -> `ControlAuthority`, below) also write to
        `ControlAuthority`'s own secondary in-memory audit trail -- same
        rollback-consistency concern as `applications_unit_of_work` above,
        same fix. `self._credentials.unit_of_work()` (WP-2, `auth.
        CredentialStore`) already owns snapshot/restore of `_records` itself
        on any exception; this wraps that with the *additional* secondary-
        trail truncation, rather than duplicating the store's own rollback
        logic here."""
        service = self._authority._service  # noqa: SLF001 -- see __init__
        authority_audit_len = len(service._audit._events)  # noqa: SLF001
        try:
            with self._credentials.unit_of_work() as work:
                yield work
        except BaseException:
            del service._audit._events[authority_audit_len:]  # noqa: SLF001
            raise

    def credential_state(self, credential_id: str) -> tuple[bool, bool] | None:
        return self._credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._credentials.count_active_for_application(application_id)

    def list_credentials(self) -> list[tuple[str, str, str, bool, bool]]:
        return [(r.credential_id, r.application_id, r.role, r.enabled, r.revoked) for r in self._credentials.list_all()]

    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str, *, work: Any) -> None:
        # Duplicate operation with `ControlAuthority` -- always delegated
        # (design §0/§3: "重複操作...は必ずControlAuthority経由").
        self._authority.issue_credential(credential_id, application_id, role, secret, work=work)

    def rotate_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        # `ControlAuthority` has no `rotate` concept at all -- not a
        # duplicate operation, so this talks to the store directly (design
        # §3: "ControlAuthorityに無い操作...はControlPlaneServiceに実装").
        self._credentials.rotate(credential_id, secret, work=work)

    def set_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._authority.set_credential_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    # ---- control credentials -------------------------------------------

    def control_credentials_unit_of_work(self) -> ContextManager[Any]:
        return self._control_credentials.unit_of_work()

    def control_credential_state(self, credential_id: str) -> tuple[bool, bool] | None:
        return self._control_credentials.get_state(credential_id)

    def list_control_credentials(self) -> list[tuple[str, bool, bool, bool, str]]:
        return [(r.credential_id, r.enabled, r.revoked, r.must_rotate, r.role) for r in self._control_credentials.list_all()]

    def control_credentials_locked(self, work: Any) -> list[tuple[str, bool, bool, str]]:
        # design R-3/WP-0 MA-2: the in-memory store's own `unit_of_work()`
        # (auth.ControlCredentialStore) already holds a `threading.Lock` for
        # this whole `work`'s duration -- see that method's own docstring --
        # so a plain read here is already serialized against a concurrent
        # revoke/rotate/set_state racing the same decision; `work` itself
        # carries no separate handle to lock on for this backend.
        del work
        return [(r.credential_id, r.enabled, r.revoked, r.role) for r in self._control_credentials.list_all()]

    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        self._control_credentials.rotate(credential_id, secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._control_credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    # ---- issuance freeze (Phase 3.5 WP-4) -------------------------------

    def application_issuance_frozen(self, application_id: str) -> bool:
        return application_id in self._frozen_applications

    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work: Any) -> None:
        del work  # no separate transaction to participate in for this backend
        if frozen:
            self._frozen_applications.add(application_id)
        else:
            self._frozen_applications.discard(application_id)


class PostgresControlBackend:
    """`ControlBackend`'s Postgres implementation -- talks to the WP-2 store
    trio directly, no `DataService`/`ControlAuthority` involved at all (a
    real deployment of this surface is a separate process, R-1/R-3, which
    never constructs an application-plane `DataService`)."""

    def __init__(
        self,
        *,
        applications: PostgresApplicationRegistry,
        credentials: PostgresCredentialStore,
        control_credentials: PostgresControlCredentialStore,
    ) -> None:
        self._applications = applications
        self._credentials = credentials
        self._control_credentials = control_credentials

    def authenticate(self, secret: str | None) -> ControlAuthContext:
        return self._control_credentials.authenticate(secret)

    def authenticate_application(self, secret: str | None) -> AuthContext | None:
        # Phase 4 WP-2(b): identical rationale to `InMemoryControlBackend.
        # authenticate_application` above -- `self._credentials` is the
        # SAME `PostgresCredentialStore` `issue_credential`/`rotate_
        # credential`/`set_credential_state` already use.
        if not secret:
            return None
        try:
            return self._credentials.authenticate(secret)
        except FoundationError:
            return None

    # ---- applications --------------------------------------------------

    def applications_unit_of_work(self) -> ContextManager[Any]:
        return self._applications.unit_of_work()

    def application_exists(self, application_id: str) -> bool:
        return self._applications.exists(application_id)

    def applications_count(self) -> int:
        return self._applications.count()

    def list_applications(self) -> list[tuple[str, bool]]:
        return self._applications.list_all()

    def register_application(self, application_id: str, *, work: Any) -> None:
        self._applications.register(application_id, work=work)

    def set_application_enabled(self, application_id: str, enabled: bool, *, work: Any) -> None:
        self._applications.set_enabled(application_id, enabled, work=work)

    # ---- application credentials ---------------------------------------

    def credentials_unit_of_work(self) -> ContextManager[Any]:
        return self._credentials.unit_of_work()

    def credential_state(self, credential_id: str) -> tuple[bool, bool] | None:
        return self._credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._credentials.count_active_for_application(application_id)

    def list_credentials(self) -> list[tuple[str, str, str, bool, bool]]:
        return self._credentials.list_all()

    def issue_credential(self, credential_id: str, application_id: str, role: str, secret: str, *, work: Any) -> None:
        self._credentials.add(credential_id, application_id, role, secret, work=work)

    def rotate_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        self._credentials.rotate(credential_id, secret, work=work)

    def set_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    # ---- control credentials -------------------------------------------

    def control_credentials_unit_of_work(self) -> ContextManager[Any]:
        return self._control_credentials.unit_of_work()

    def control_credential_state(self, credential_id: str) -> tuple[bool, bool] | None:
        return self._control_credentials.get_state(credential_id)

    def list_control_credentials(self) -> list[tuple[str, bool, bool, bool, str]]:
        return self._control_credentials.list_all()

    def control_credentials_locked(self, work: Any) -> list[tuple[str, bool, bool, str]]:
        return self._control_credentials.list_all_for_update(work)

    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        self._control_credentials.rotate(credential_id, secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._control_credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    # ---- issuance freeze (Phase 3.5 WP-4) -------------------------------

    def application_issuance_frozen(self, application_id: str) -> bool:
        return self._applications.issuance_frozen(application_id)

    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work: Any) -> None:
        self._applications.set_issuance_frozen(application_id, frozen, work=work)


class ControlPlaneService:
    """CCR-14 control-plane facade (WP-3). Constructed with a `ControlBackend`
    (either implementation above), a durable audit sink (`ControlAuditSink`/
    `PostgresControlAuditSink`), an optional `ControlPlaneLimits` profile
    (defaults to the contract's own `example_profile` values), and an
    optional monotonic clock callable (rate-limiter testability, mirroring
    `DataService`'s own `clock` parameter).

    See this module's header for the architecture this class embodies: every
    processing-order/authorization/limit/audit/deterrence judgment lives
    here; backends are dumb storage plumbing.

    CCR-14 WP-4 round-2 (independent review MAJOR-1): every one of the 9
    public operation methods below accepts a keyword-only `rate_precharged:
    bool = False`. `False` (the default -- what every direct in-process
    caller, including the WP-5 in-process conformance adapter, keeps using)
    means the method charges the R-7 rate window itself, exactly as before
    this fix. `True` means the caller already charged it via `check_rate()`
    (see that method's own docstring) and this call must not charge it
    again -- `control_http.py` is the one caller that does this, because it
    has to charge the window before it can even read a request body.
    """

    def __init__(
        self,
        backend: ControlBackend,
        *,
        audit: ControlAuditSink | PostgresControlAuditSink,
        limits: ControlPlaneLimits | None = None,
        clock: Callable[[], float] | None = None,
        audit_reader: AuditQueryReader | None = None,
        audit_visibility_lag_ms: int = 0,
        audit_event_classes: frozenset[str] = DECLARED_AUDIT_EVENT_CLASSES,
        audit_operations: frozenset[str] = DECLARED_AUDIT_OPERATIONS,
        audit_target_kinds: frozenset[str] = DECLARED_AUDIT_TARGET_KINDS,
        audit_default_limit: int = _DEFAULT_AUDIT_QUERY_LIMIT,
        audit_max_limit: int = _MAX_AUDIT_QUERY_LIMIT,
        audit_coalescing_window_ms: int = DECLARED_COALESCING_WINDOW_MS,
    ) -> None:
        self._backend = backend
        self._audit = audit
        self._limits = limits or ControlPlaneLimits()
        self._clock = clock or time.monotonic
        self._rate_lock = threading.Lock()
        self._rate_window: list[float] = []
        # Phase 4 WP-2(b) (design D-5/D-6): `audit_query`'s own state.
        # `audit_reader is None` is this instance's true, complete posture
        # for "AUDIT DSN not configured" (D-5 M-4) -- `capabilities()`
        # below declares `audit_query: {"status": "unavailable"}` exactly
        # when this holds, and `audit_query()` refuses with `CAPABILITY_
        # UNSUPPORTED` (never a bare 404/`AttributeError`) on that same
        # condition. A SEPARATE pre-auth rate window from `_rate_window`
        # above (`_audit_rate_window`) -- `audit_query`'s own window must
        # never share a counter with `control_requests_per_minute`
        # (design M-8 / P4-D4 item 8): a high-frequency audit poller must
        # never be able to exhaust the window a break-glass `revoke_
        # credential` depends on.
        self._audit_reader = audit_reader
        self._audit_visibility_lag_ms = audit_visibility_lag_ms
        self._audit_event_classes = frozenset(audit_event_classes)
        self._audit_operations = frozenset(audit_operations)
        self._audit_target_kinds = frozenset(audit_target_kinds)
        self._audit_default_limit = audit_default_limit
        self._audit_max_limit = audit_max_limit
        self._audit_coalescing_window_ms = audit_coalescing_window_ms
        self._audit_rate_lock = threading.Lock()
        self._audit_rate_window: list[float] = []

    @property
    def limits(self) -> ControlPlaneLimits:
        """Phase 3.5 WP-4 (design §4 "L4", single-source rule): the exact
        `ControlPlaneLimits` instance this service enforces internally --
        `control_http.create_control_app` reads `.request_bytes` off THIS
        object to size `RequestByteBoundMiddleware`, rather than constructing
        a second, independently-defaulted `ResourceLimits()` the way it did
        before this WP. There is exactly one source for the declared limit
        and the enforced bound: this property."""
        return self._limits

    # =====================================================================
    # Public operations (design §1's operation catalog / §2's endpoint map)
    # =====================================================================

    def capabilities(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="control_capabilities", request_id=request_id)
        self._gate_must_rotate(context, operation="control_capabilities", request_id=request_id)
        limits = self._limits.as_dict()
        limit_enforcement = {name: "enforced" for name in limits}
        # Phase 3.5 WP-4 (§4 "L4", MitateDB-parity two-layer form, review
        # M-3): this service alone cannot enforce a byte bound -- there is no
        # HTTP boundary at this layer -- so the service-layer default is
        # `"unavailable"`; `control_http.py`'s own handler overrides this one
        # key to `"enforced"` once the real `RequestByteBoundMiddleware` is
        # actually mounted in front of it (same single-source instance, see
        # the `limits` property above).
        limit_enforcement["request_bytes"] = "unavailable"
        # Phase 4 WP-2(b) (design D-5, contract 1.4.0 subordinate ruling 9):
        # `audit_requests_per_minute` is a pre-auth fixed window that always
        # exists once this process is running (the route is always
        # registered, D-5 M-4) -- "enforced" regardless of whether
        # `audit_query` itself is `enabled`, exactly like every other
        # `ControlPlaneLimits` field the generic comprehension above already
        # marks "enforced".
        return {
            # Phase 4 WP-2(b) (P4-D4, contract 1.4.0 `versioning.
            # version_binding`): the flip lands in the SAME commit as the
            # real `audit_query` behavior below -- unconditional (every
            # instance of this service declares 1.4.0 now, whether or not
            # `audit_query` itself is `enabled` on this deployment; the
            # 1.4.0 obligations that are conditional on `audit_query` being
            # provided stay conditional per version_binding's own text).
            "contract_version": "1.5.0",
            "capabilities": {
                "control_plane": {"status": "enabled"},
                "audit_query": self._audit_capability_declaration(),
            },
            "limits": limits,
            "limit_enforcement": limit_enforcement,
            "authorization_propagation_bound_ms": 0,
            "role": context.role,
        }

    def _audit_capability_declaration(self) -> dict[str, Any]:
        """Phase 4 WP-2(b) (design D-5's own JSON shape). `status`'s
        vocabulary is the contract's own `capability_status.status_enum` (4
        values) -- never the word `"available"`, which is not a member.
        AUDIT DSN unconfigured (`self._audit_reader is None`) keeps the
        declaration at exactly `{"status": "unavailable"}` (D-5 M-4) --
        every other key below is published only once there is a real
        reader to back it, so a client never reads a `visibility_lag_ms`/
        `event_classes` for a capability that cannot actually answer a
        request.
        """
        if self._audit_reader is None:
            return {"status": "unavailable"}
        return {
            "status": "enabled",
            "authority": "control_or_audit",
            "event_classes": sorted(self._audit_event_classes),
            # Phase 5 WP-2 (design D-1, contract 1.5.0 subordinate ruling 10
            # item 1, conditional on `audit_query` being provided): the
            # `operation`/`target_kind` vocabulary this reader can ever
            # surface -- same declare-the-hazard posture as `event_classes`
            # above, not the `capability_status.defined.atomic_mutation.
            # operations` execution vocabulary (contract's own disambiguation
            # note).
            "operations": sorted(self._audit_operations),
            "target_kinds": sorted(self._audit_target_kinds),
            "default_limit": self._audit_default_limit,
            "max_limit": self._audit_max_limit,
            # D-6 point 3: a DERIVED value (composition root's own two
            # writer-connection timeouts + 1s clock-skew margin), never a
            # bare constant this class invents on its own -- `control_main.
            # build_control_app` computes it from `statement_timeout_ms` +
            # `idle_in_transaction_session_timeout_ms` and passes the sum
            # in via `audit_visibility_lag_ms` (this class's own
            # constructor parameter).
            "visibility_lag_ms": self._audit_visibility_lag_ms,
            "coalescing_window_ms": self._audit_coalescing_window_ms,
            "completeness_note": (
                "A page shorter than limit does not mean the log is exhausted -- rows within "
                "visibility_lag_ms of the current time are not yet returned. Keep polling with the "
                "cursor of the last event received (the opaque per-event 'cursor' field, passed back "
                "as the next request's 'after') until a page comes back empty."
            ),
            "outcome_note": (
                "outcome=allow means the operation was authorized and submitted; a later outcome=error "
                "row sharing the same request_id means it did not commit. An allow row with no "
                "corresponding error row usually means the operation committed, but -- if the process "
                "was lost between recording allow and committing -- can also mean it did not; the audit "
                "trail alone cannot distinguish the two in that one case."
            ),
            # WP-2(b) review B-1 (supervisor ruling): the durable `count`
            # column's real semantics, matching contract `audit.
            # query_event_fields_note` verbatim ("present only on an event
            # representing more than one coalesced occurrence, absent --
            # never zero or one -- otherwise"). A denial-coalescing window
            # or a buffer-overflow drop that ends up representing exactly
            # one occurrence is written as an ordinary row with count
            # absent, not count=1 -- a consumer must never read "count is
            # present" as "this row alone represents 2+ occurrences" being
            # the ONLY way to represent 2+; it is, but the converse
            # (absent implies exactly 1) is what this note pins down.
            "count_note": (
                "count is the number of occurrences the ONE row represents; a row representing exactly "
                "one occurrence never carries it (never 0, never 1) -- absence means one occurrence, "
                "same as an ordinary uncoalesced event."
            ),
            # WP-2(b) fix round 2 (coordinator ruling, item E): this
            # implementation's cursor is a pure KEYSET position
            # (`(recorded_at, plane, event_id)`, opaque-encoded) -- it
            # always resolves to a real position in the total order
            # regardless of which `event_classes` filter accompanies it,
            # so a cursor obtained under one filter is accepted under a
            # DIFFERENT filter too. Contract `AuditQueryRequest.after`'s
            # own text ("valid only under the request's own filters") is
            # an UPPER bound on what an implementation must guarantee, not
            # a floor an implementation may not exceed -- a MORE permissive
            # cursor (valid under any filter) is conformant, and the
            # contract's own next sentence explicitly leaves reuse across
            # filters undefined by that version rather than forbidding it.
            "cursor_note": (
                "cursor is a filter-independent position token (a keyset position in the total order, "
                "opaque-encoded) -- it always resolves, and may be reused as 'after' under a different "
                "event_classes filter than the one that produced it."
            ),
        }

    def register_application(self, secret: str | None, application_id: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="register_application", request_id=request_id)
        self._gate_must_rotate(context, operation="register_application", request_id=request_id)
        self._validate_application_id(application_id)
        if self._backend.application_exists(application_id):
            fail("CONFLICT", "Application already exists.", status=409)
        if self._backend.applications_count() >= self._limits.applications:
            fail("LIMIT_EXCEEDED", "Application registration limit exceeded.", status=413, details={"resource": "applications", "limit_class": "applications", "limit": self._limits.applications})

        def _body(work: Any) -> dict[str, Any]:
            self._backend.register_application(application_id, work=work)
            self._write_state_audit(work, event_class="application_lifecycle", operation="register_application", target_kind="application", application_id=application_id, target_id=application_id, actor=context, request_id=request_id)
            return {"application_id": application_id, "enabled": True}

        return self._run_state_change(self._backend.applications_unit_of_work, _body)

    def list_applications(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="list_applications", request_id=request_id)
        self._gate_must_rotate(context, operation="list_applications", request_id=request_id)
        return {"applications": [{"application_id": app_id, "enabled": enabled} for app_id, enabled in self._backend.list_applications()]}

    def set_application_enabled(self, secret: str | None, application_id: Any, enabled: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        # Nit (round-2 review): `enabled`'s own bool-ness must be checked
        # *before* it is used to pick an `operation` name at all -- unlike
        # every other operation's shape validation (which the canonical (3)
        # gate -> (4) validate order defers past the gate on purpose), this
        # one specific field is an input to the gate call itself (which
        # `operation` name to check), so there is no way to gate first
        # without first deciding what a non-bool `enabled` even means for
        # audit/gate purposes. Both `enable_application`/`disable_
        # application` are refused identically under must_rotate regardless,
        # so this ordering has no observable effect on gate outcomes -- it
        # only avoids deriving an operation name from a value that was never
        # validated as meaningful in the first place.
        if not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "enabled must be a boolean.")
        operation = "enable_application" if enabled else "disable_application"
        self._authorize_role(context, operation=operation, request_id=request_id, target_id=application_id if isinstance(application_id, str) else None)
        self._gate_must_rotate(context, operation=operation, request_id=request_id)
        if not self._backend.application_exists(application_id):
            fail("NOT_FOUND", "Application was not found.", status=404)

        def _body(work: Any) -> dict[str, Any]:
            self._backend.set_application_enabled(application_id, enabled, work=work)
            self._write_state_audit(work, event_class="application_lifecycle", operation=operation, target_kind="application", application_id=application_id, target_id=application_id, actor=context, request_id=request_id)
            return {"application_id": application_id, "enabled": enabled}

        return self._run_state_change(self._backend.applications_unit_of_work, _body)

    def issue_credential(self, secret: str | None, application_id: Any, role: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="issue_credential", request_id=request_id)
        self._gate_must_rotate(context, operation="issue_credential", request_id=request_id)
        # (4) semantic/shape validation -- `role=control` is a *shape-valid*
        # enum member (contract `CredentialIssueRequest`), so it must pass
        # this check before the (5) capability refusal below can reject it
        # specifically as a capability question, not a shape one.
        if role not in _ALL_ISSUABLE_ROLES:
            fail("VALIDATION_FAILED", "role must be one of runtime, developer, control.")
        self._validate_application_id(application_id)
        # (5) capability denial -- BEFORE target resolution/limit/freeze (§8
        # M-1, §2 evaluation-order ruling; Phase 3.5 §1-E/M-8 extends the
        # same precedence to the freeze refusal below): must refuse
        # `role=control` even when the named application does not exist, is
        # disabled, is frozen, or is already at its credential limit -- none
        # of those questions are reached.
        if role == "control":
            self._deny_role_control(context, application_id, request_id=request_id)
        # (6) target resolution
        if not self._backend.application_exists(application_id):
            fail("NOT_FOUND", "Application was not found.", status=404)
        # (6.5) Phase 3.5 WP-4 (§4/§1-E, P35-D6/D13): per-application
        # issuance freeze -- an out-of-band (CLI-only) deployer operation.
        # `FORBIDDEN`/fail-closed/durably audited, evaluated after target
        # resolution (a freeze on a nonexistent application is meaningless)
        # but before the credentials_per_application limit check (grouped
        # with "application existence/state" resolution, contract `issue_
        # credential.semantics`' own precedence sentence).
        if self._backend.application_issuance_frozen(application_id):
            self._deny_issuance_frozen(context, application_id, request_id=request_id)
        # (8) limit check -- disabled Applications are NOT refused here
        # (design §6 supervisor decision (3): issuance to a disabled
        # Application is permitted; enforcement already lives in `enabled`).
        if self._backend.credentials_active_count(application_id) >= self._limits.credentials_per_application:
            fail("LIMIT_EXCEEDED", "Credentials-per-application limit exceeded.", status=413, details={"resource": "credentials_per_application", "limit_class": "credentials_per_application", "limit": self._limits.credentials_per_application})

        credential_id = _new_credential_id()
        secret_value = _new_secret()

        def _body(work: Any) -> dict[str, Any]:
            self._backend.issue_credential(credential_id, application_id, role, secret_value, work=work)
            self._write_state_audit(work, event_class="credential_lifecycle", operation="issue_credential", target_kind="credential", application_id=application_id, target_id=credential_id, actor=context, request_id=request_id)
            return {"credential_id": credential_id, "application_id": application_id, "role": role, "secret": secret_value}

        return self._run_state_change(self._backend.credentials_unit_of_work, _body)

    def list_credentials(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="list_credentials", request_id=request_id)
        self._gate_must_rotate(context, operation="list_credentials", request_id=request_id)
        rows: list[dict[str, Any]] = []
        for credential_id, application_id, role, enabled, revoked in self._backend.list_credentials():
            # Application-credential rows never carry `must_rotate` at all --
            # the concept does not exist for them (P35-D7, contract
            # `CredentialsResult.credentials[].must_rotate` description).
            rows.append({"credential_id": credential_id, "application_id": application_id, "role": role, "enabled": enabled, "revoked": revoked})
        for credential_id, enabled, revoked, must_rotate, role in self._backend.list_control_credentials():
            # No `application_id` key at all (design §2: "control行はapplication_id無し",
            # unchanged for `role="audit"` rows too -- neither kind belongs
            # to an Application). Phase 3.5 WP-4 (§4/§1-B, P35-D7 reversal of
            # the original §8 m-9 omission): `must_rotate` is now exposed
            # here with its real value for every control-table row (control
            # OR audit) -- the store has the value and contract 1.3.0 makes
            # the field optional-additive, so there is no longer a reason to
            # withhold it (m-4: this does widen who can observe a not-yet-
            # rotated credential's existence -- an `audit`-role principal can
            # now read this same listing -- but no secret/verifier is ever
            # included, and this is documented, intended operational
            # visibility, not a leak; see CONTROL_MAPPING.md SI-10/SI-02).
            # `role` reads the real column (design §4 review m-6) instead of
            # a hardcoded `"control"` literal.
            rows.append({"credential_id": credential_id, "role": role, "enabled": enabled, "revoked": revoked, "must_rotate": must_rotate})
        return {"credentials": rows}

    def rotate_credential(self, secret: str | None, credential_id: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self_rotate = isinstance(credential_id, str) and credential_id == context.credential_id
        self._authorize_role(context, operation="rotate_credential", request_id=request_id, target_id=credential_id if isinstance(credential_id, str) else None)
        self._gate_must_rotate(context, operation="rotate_credential", request_id=request_id, self_rotate=self_rotate)
        kind, state = self._locate_credential(credential_id)
        if kind is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        _enabled, revoked = state
        if revoked:
            fail("VALIDATION_FAILED", "A revoked credential cannot be rotated.")
        new_secret = _new_secret()

        if kind == "application":
            def _body(work: Any) -> dict[str, Any]:
                self._backend.rotate_credential(credential_id, new_secret, work=work)
                self._write_state_audit(work, event_class="credential_lifecycle", operation="rotate_credential", target_kind="credential", target_id=credential_id, actor=context, request_id=request_id)
                return {"credential_id": credential_id, "secret": new_secret}

            return self._run_state_change(self._backend.credentials_unit_of_work, _body)

        def _control_body(work: Any) -> dict[str, Any]:
            self._backend.rotate_control_credential(credential_id, new_secret, work=work)
            self._write_state_audit(work, event_class="control_credential_lifecycle", operation="rotate_credential", target_kind="control_credential", target_id=credential_id, actor=context, request_id=request_id)
            return {"credential_id": credential_id, "secret": new_secret}

        return self._run_state_change(self._backend.control_credentials_unit_of_work, _control_body)

    def revoke_credential(self, secret: str | None, credential_id: Any, *, destructive: Any = None, confirmation: Any = None, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        """Contract 1.2.0 `destructive_confirmation` (design docs/design/
        DESTRUCTIVE_CONFIRMATION_V1.md R-3): revoking an application
        credential, or a control credential that is not the last remaining
        active one, is never gated -- `destructive`/`confirmation` are not
        even inspected on those paths (contract `non_destructive_requests`),
        exactly as before this WP. Revoking the LAST remaining active
        (enabled and not revoked) control credential requires a valid
        confirmation; the judgment "is this the last active one" is made
        inside the SAME `control_credentials_unit_of_work` transaction as
        the state change itself, under a lock (`control_credentials_
        locked`), so two concurrent revoke attempts against two different
        credentials can never both observe "not last" and both proceed
        unconfirmed (WP-0 MA-2's TOCTOU concern). Processing order:
        authenticate -> must_rotate gate -> [confirmation gate, control
        credentials only] -> execute (design R-3's own ordering).
        """
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="revoke_credential", request_id=request_id, target_id=credential_id if isinstance(credential_id, str) else None)
        self._gate_must_rotate(context, operation="revoke_credential", request_id=request_id)
        # Review blocker B-1: shape validation of the request's own
        # `destructive`/`confirmation` fields (contract `CredentialRevoke
        # Request.destructive: {"type": "boolean"}` / `.confirmation:
        # {"type": "string", ...}`) -- applied unconditionally, regardless
        # of whether this particular revoke ever meets the gate condition
        # below. This is the same "request schema enforce" `bind_mutation`
        # already applies to every data-plane mutation's own `destructive`
        # field (structured.py); it is not part of the destructive-
        # confirmation *semantics* the contract's own `non_destructive_
        # requests` clause says a non-gated revoke never inspects -- a
        # non-boolean truthy `destructive` (e.g. the string `"false"`,
        # which a loose `bool(...)` cast would silently coerce to `True`)
        # must be rejected as a shape defect before that semantic question
        # is even reached, exactly per contract `evaluation_order` (shape
        # validation precedes confirmation evaluation).
        if destructive is not None and not isinstance(destructive, bool):
            fail("VALIDATION_FAILED", "destructive must be boolean.")
        if confirmation is not None and not isinstance(confirmation, str):
            fail("VALIDATION_FAILED", "confirmation must be a string.")
        kind, state = self._locate_credential(credential_id)
        if kind is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        if kind != "control":
            # Q1-D1: an application credential's revocation is never gated.
            del destructive, confirmation
            return self._set_credential_state(context, credential_id, revoked=True, operation="revoke_credential", request_id=request_id)

        def _body(work: Any) -> dict[str, Any]:
            rows = self._backend.control_credentials_locked(work)
            matching = next((row for row in rows if row[0] == credential_id), None)
            if matching is None:
                fail("NOT_FOUND", "Credential was not found.", status=404)
            _credential_id, enabled_now, revoked_now, _matching_role = matching
            # `active_ids` (enabled AND not revoked) naturally excludes
            # `credential_id` itself when `revoked_now` is already true, so
            # an idempotent re-revoke of an already-revoked row never hits
            # this gate -- no separate branch is needed for that case.
            #
            # Phase 3.5 WP-4: filtered to `role == "control"` rows only -- the
            # destructive-confirmation gate exists to protect the LAST
            # remaining active CONTROL credential (the only kind that can
            # perform any control-plane management operation at all). An
            # `"audit"` row existing alongside the sole active control
            # credential must not be able to mask it as "not the last one":
            # revoking that control credential would still leave zero
            # credentials capable of management, even though an audit
            # credential remains active. Symmetrically, revoking an audit
            # credential itself never trips this gate at all (it is excluded
            # from `active_ids`, so `active_ids[0] == credential_id` can
            # never hold for one) -- an ordinary, unconfirmed revoke, exactly
            # like an application credential's.
            active_ids = [row[0] for row in rows if row[1] and not row[2] and row[3] == "control"]
            if len(active_ids) == 1 and active_ids[0] == credential_id:
                phrase = revoke_last_control_credential_confirmation_phrase(credential_id)
                if destructive is not True or confirmation != phrase:
                    self._deny(
                        code="DESTRUCTIVE_CONFIRMATION_REQUIRED", status=409,
                        message="Revoking the last remaining active control credential requires explicit destructive confirmation.",
                        event_class="control_credential_lifecycle", operation="revoke_credential", target_kind="control_credential",
                        request_id=request_id, actor_id=context.credential_id, actor_type="control_credential", role=context.role,
                        target_id=credential_id,
                        extra_details={
                            "required_confirmation": phrase,
                            "consequence": _REVOKE_LAST_CONTROL_CREDENTIAL_CONSEQUENCE,
                            "reversible_alternative": _REVOKE_LAST_CONTROL_CREDENTIAL_REVERSIBLE_ALTERNATIVE,
                            "recovery": _REVOKE_LAST_CONTROL_CREDENTIAL_RECOVERY,
                        },
                    )
            self._backend.set_control_credential_state(credential_id, enabled=None, revoked=True, work=work)
            self._write_state_audit(work, event_class="control_credential_lifecycle", operation="revoke_credential", target_kind="control_credential", target_id=credential_id, actor=context, request_id=request_id)
            return {"credential_id": credential_id, "enabled": enabled_now, "revoked": True}

        return self._run_state_change(self._backend.control_credentials_unit_of_work, _body)

    def set_credential_enabled(self, secret: str | None, credential_id: Any, enabled: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        # Symmetric with `set_application_enabled`'s identical fix above --
        # same reasoning (an operation-name-selecting field must be
        # validated before it selects one).
        if not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "enabled must be a boolean.")
        operation = "enable_credential" if enabled else "disable_credential"
        self._authorize_role(context, operation=operation, request_id=request_id, target_id=credential_id if isinstance(credential_id, str) else None)
        self._gate_must_rotate(context, operation=operation, request_id=request_id)
        return self._set_credential_state(context, credential_id, enabled=enabled, operation=operation, request_id=request_id)

    def audit_query(self, secret: str | None, request: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        """Phase 4 WP-2(b) (design D-5/D-6). Processing order: `audit_
        requests_per_minute` (its OWN window, never `control_requests_
        per_minute`) -> application-credential probe (identified FORBIDDEN,
        BEFORE the control-credential store ever sees this secret -- see
        `_deny_application_credential_on_audit_query`'s own docstring for
        why the ordering matters) -> ordinary control/audit authentication
        -> role authorization (`_AUDIT_ROLE_ALLOWED_OPERATIONS` now
        includes `audit_query`) -> must_rotate gate -> `CAPABILITY_
        UNSUPPORTED` when no reader is configured (D-5 M-4: the route
        answers this AFTER authenticating, never a bare 404) -> request
        shape/semantic validation -> the real read.
        """
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_audit_rate()
        # D-5's own authority-separation requirement: probe the
        # APPLICATION-credential universe first. If this secret genuinely
        # authenticates there, deny it here -- attributed, `FORBIDDEN` --
        # without ever presenting it to `self._authenticate` below (which
        # would otherwise durably record an unattributed `AUTH_INVALID`
        # denial for a secret that, in fact, belongs to a real credential,
        # a confusing and duplicative record for one request).
        app_context = self._backend.authenticate_application(secret)
        if app_context is not None:
            self._deny_application_credential_on_audit_query(app_context, request_id=request_id)
        context = self._authenticate(secret, request_id)
        self._authorize_role(context, operation="audit_query", request_id=request_id)
        self._gate_must_rotate(context, operation="audit_query", request_id=request_id)
        if self._audit_reader is None:
            self._deny_audit_capability_unsupported(context, request_id=request_id)
        if not isinstance(request, dict):
            fail("VALIDATION_FAILED", "AuditQueryRequest must be an object.")
        event_classes = self._validate_audit_event_classes(request.get("event_classes"))
        after = self._validate_audit_after(request.get("after"))
        limit = self._validate_audit_limit(request.get("limit"))
        rows = self._audit_reader.query(event_classes=event_classes, after=after, limit=limit, visibility_lag_ms=self._audit_visibility_lag_ms)
        return {"events": [self._shape_audit_query_row(row) for row in rows]}

    def _validate_audit_event_classes(self, value: Any) -> list[str] | None:
        # D-6: `event_classes` is a FILTER, not a vocabulary check -- an
        # unknown class is never `VALIDATION_FAILED`, it simply matches no
        # row (D-7: the vocabulary is declared, not contract-enumerated).
        if value is None:
            return None
        if not isinstance(value, list) or len(value) > _MAX_AUDIT_QUERY_EVENT_CLASSES or not all(isinstance(item, str) for item in value):
            fail("VALIDATION_FAILED", f"event_classes must be an array of at most {_MAX_AUDIT_QUERY_EVENT_CLASSES} strings.")
        return value

    def _validate_audit_after(self, value: Any) -> tuple[Any, str, str] | None:
        if value is None:
            return None
        if not isinstance(value, str):
            fail("VALIDATION_FAILED", "after must be a string.")
        try:
            return decode_cursor(value)
        except ValueError:
            fail("VALIDATION_FAILED", "after is not a valid opaque cursor.")
            raise  # unreachable; fail() always raises

    def _validate_audit_limit(self, value: Any) -> int:
        if value is None:
            return self._audit_default_limit
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > self._audit_max_limit:
            fail("VALIDATION_FAILED", f"limit must be an integer between 1 and {self._audit_max_limit}.")
        return value

    def _shape_audit_query_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Turns one reader row (`AuditQueryReader.query`'s own dict shape
        -- 13 contract `audit.fields` + `count` + `recorded_at` + `plane`)
        into one `AuditResult.events[]` element: adds the opaque `cursor`
        (D-6), formats `recorded_at` as ISO-8601, and omits every optional
        field that is `None` (mirrors `audit.AuditEvent.as_dict()`'s own
        None-filtering convention -- `events[]` is contract-open, but a
        `null`-valued key is still needless noise no existing reader emits
        elsewhere in this codebase)."""
        recorded_at = row["recorded_at"]
        cursor = encode_cursor(recorded_at, row["plane"], row["event_id"])
        out: dict[str, Any] = {
            "event_id": row["event_id"],
            "event_class": row["event_class"],
            "occurred_at": row["occurred_at"],
            "request_id": row["request_id"],
            "actor_type": row["actor_type"],
            "operation": row["operation"],
            "outcome": row["outcome"],
            # D-6: `plane` is the read surface's own derived value (which
            # UNION half a row came from) -- never a stored column a writer
            # could have set (m-2's own "書き手が指定できてはならない").
            "plane": row["plane"],
            "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else recorded_at,
            "cursor": cursor,
        }
        for key in ("application_id", "actor_id", "role", "target_kind", "reason_code", "target_id", "count"):
            value = row.get(key)
            if value is not None:
                out[key] = value
        return out

    def _deny_application_credential_on_audit_query(self, app_context: AuthContext, *, request_id: str) -> None:
        """Contract `control_endpoints.audit_query.semantics`: "Application
        credentials are denied." Always attributed (`app_context` names a
        real, currently-active application credential this call already
        confirmed) -- see `audit_query`'s own docstring for why this must
        run BEFORE `self._authenticate` ever sees the same secret."""
        self._deny(
            code="FORBIDDEN", status=403,
            message="Application credentials are denied on audit_query; audit evidence requires control or audit authority.",
            event_class="authorization_denial", operation="audit_query", target_kind="credential",
            actor_id=app_context.credential_id, actor_type="application_credential", role=app_context.role,
            application_id=app_context.application_id, request_id=request_id,
        )

    def _deny_audit_capability_unsupported(self, context: ControlAuthContext, *, request_id: str) -> None:
        """D-5 M-4: AUDIT DSN not configured -- the route is always
        registered and always authenticates first (never a bare 404), and
        this refusal is durably recorded like every other control-plane
        capability denial (`_deny_role_control`'s identical `CAPABILITY_
        UNSUPPORTED` precedent)."""
        self._deny(
            code="CAPABILITY_UNSUPPORTED", status=400,
            message="Audit evidence query is not available on this deployment.",
            event_class="capability_denial", operation="audit_query", target_kind="control_credential",
            actor_id=context.credential_id, actor_type="control_credential", role=context.role, request_id=request_id,
        )

    # =====================================================================
    # Shared machinery
    # =====================================================================

    def _validate_application_id(self, application_id: Any) -> None:
        if not isinstance(application_id, str) or not _APPLICATION_ID_PATTERN.fullmatch(application_id):
            fail("VALIDATION_FAILED", "application_id must match ^[a-z][a-z0-9_]{0,32}$.")

    def _locate_credential(self, credential_id: Any) -> tuple[str | None, tuple[bool, bool] | None]:
        """Dual-store resolution (design §2: "探索はidでなく両ストア照会とし、
        prefixを意味論に昇格させない") -- tries the application-credential
        store, then the control-credential store. Neither store's id prefix
        (`crd_`/`ctl_`) is inspected; a non-string/malformed `credential_id`
        simply matches neither store's `get_state` and resolves to
        `(None, None)`, same as any other unknown id."""
        if not isinstance(credential_id, str):
            return None, None
        state = self._backend.credential_state(credential_id)
        if state is not None:
            return "application", state
        state = self._backend.control_credential_state(credential_id)
        if state is not None:
            return "control", state
        return None, None

    def _set_credential_state(self, context: ControlAuthContext, credential_id: Any, *, operation: str, request_id: str, enabled: bool | None = None, revoked: bool | None = None) -> dict[str, Any]:
        kind, state = self._locate_credential(credential_id)
        if kind is None:
            fail("NOT_FOUND", "Credential was not found.", status=404)
        original_enabled, original_revoked = state
        result_enabled = enabled if enabled is not None else original_enabled
        result_revoked = revoked if revoked is not None else original_revoked

        if kind == "application":
            def _body(work: Any) -> dict[str, Any]:
                self._backend.set_credential_state(credential_id, enabled=enabled, revoked=revoked, work=work)
                self._write_state_audit(work, event_class="credential_lifecycle", operation=operation, target_kind="credential", target_id=credential_id, actor=context, request_id=request_id)
                return {"credential_id": credential_id, "enabled": result_enabled, "revoked": result_revoked}

            return self._run_state_change(self._backend.credentials_unit_of_work, _body)

        def _control_body(work: Any) -> dict[str, Any]:
            self._backend.set_control_credential_state(credential_id, enabled=enabled, revoked=revoked, work=work)
            self._write_state_audit(work, event_class="control_credential_lifecycle", operation=operation, target_kind="control_credential", target_id=credential_id, actor=context, request_id=request_id)
            return {"credential_id": credential_id, "enabled": result_enabled, "revoked": result_revoked}

        return self._run_state_change(self._backend.control_credentials_unit_of_work, _control_body)

    def _run_state_change(self, uow_factory: Callable[[], ContextManager[Any]], body: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
        """R-6: runs `body` inside one `uow_factory()`-opened transaction --
        the state change and its same-transaction audit append both happen
        inside `body`. A `FoundationError` raised by the state change itself
        (e.g. a race-condition `NOT_FOUND`) propagates unchanged. Any *other*
        exception -- a real `psycopg.Error` from the Postgres audit `INSERT`,
        or an in-memory `ControlAuditSink.inject_fault` fault -- is mapped to
        `SERVICE_UNAVAILABLE` (503): the enclosing `with uow_factory() as
        work:` block has already rolled the state change back by the time
        this except-clause runs (fail-closed by construction, not by this
        method remembering to check anything)."""
        try:
            with uow_factory() as work:
                return body(work)
        except FoundationError:
            raise
        except Exception:
            # MI-9: cause-neutral message -- does not assert the audit trail
            # specifically was the failing part (SI-10: no internal
            # architecture detail beyond what 503 itself already implies).
            fail("SERVICE_UNAVAILABLE", "The state change could not be durably recorded.", status=503)
            raise  # unreachable; fail() always raises

    def _write_state_audit(self, work: Any, *, event_class: str, operation: str, target_kind: str, actor: ControlAuthContext, request_id: str, application_id: str | None = None, target_id: str | None = None) -> None:
        # Round-2 review MI-6 (supervisor ruling): `role` always names the
        # ACTOR's role, never the target's -- every control-plane operation
        # is performed by a control credential (`role="control"` -- and,
        # since Phase 3.5 WP-4, possibly `role="audit"` for a read-only
        # operation, though every *state-changing* call site this method
        # actually serves is itself unreachable for an audit principal, see
        # `_authorize_role` below; `actor.role` is still read here rather
        # than re-hardcoding `"control"`, for correctness independent of
        # that other gate ever changing). Earlier code passed the *issued*
        # credential's role (`runtime`/`developer`) through here for
        # `issue_credential`'s own audit row, conflating actor and target --
        # fixed by dropping the caller-supplied override entirely; there is
        # no longer a `role` parameter to misuse.
        #
        # Phase 3.5 WP-4 (§1-C/§4): `target_id` -- the single target
        # credential_id/application_id this state change acted on, when the
        # caller supplied one (every real call site above does).
        self._audit.append(
            event_class=event_class,
            request_id=request_id,
            application_id=application_id,
            actor_type="control_credential",
            actor_id=actor.credential_id,
            role=actor.role,
            operation=operation,
            target_kind=target_kind,
            outcome="allow",
            reason_code=None,
            target_id=target_id,
            work=work,
        )

    def _authenticate(self, secret: str | None, request_id: str) -> ControlAuthContext:
        try:
            return self._backend.authenticate(secret)
        except FoundationError as exc:
            if exc.code in _AUDITED_AUTH_FAILURE_CODES:
                # Round-2 review MA-2: the store identifies a real credential
                # before refusing it for AUTH_REVOKED and for a matching-but-
                # disabled AUTH_INVALID (`auth._fail_identified` -- see its
                # docstring); an AUTH_INVALID/AUTH_REQUIRED with no match at
                # all carries no such attribute. `getattr(..., None)` treats
                # both "attribute absent" and "attribute None" as unattributed
                # -- `_deny` picks the truthful declaration form either way.
                identified_credential_id = getattr(exc, "identified_credential_id", None)
                # Phase 3.5 WP-4 (design §4 review m-6): the identified
                # credential's REAL role (`auth._fail_identified`'s own new
                # `identified_role` attribute), never a hardcoded `"control"`
                # -- an audit credential that is revoked/disabled must be
                # attributed as `role="audit"` in its own denial row, not
                # misreported as a control credential.
                identified_role = getattr(exc, "identified_role", None)
                self._deny(
                    code=exc.code, status=exc.status, message=exc.message,
                    event_class="authentication_denial", operation="control_authenticate", target_kind="control_credential",
                    request_id=request_id,
                    actor_id=identified_credential_id,
                    actor_type="control_credential" if identified_credential_id else "unknown",
                    role=identified_role,
                )
            raise

    def _authorize_role(self, context: ControlAuthContext, *, operation: str, request_id: str, target_id: str | None = None) -> None:
        """Phase 3.5 WP-4 (design §1-D/§4, P35-D12): contract `control_plane.
        authority` -- an `audit`-role principal is accepted ONLY on the 3
        read-only control endpoints (`_AUDIT_ROLE_ALLOWED_OPERATIONS` above);
        every other control endpoint fails it closed with `FORBIDDEN`,
        durably audited (same discipline as `_gate_must_rotate` below, and
        deliberately checked as a SEPARATE, orthogonal gate from it: this is
        a role-authorization question, not a rotate-pending question -- a
        `role="control"` principal is never affected by this method at all,
        `must_rotate` or not).

        Called BEFORE `_gate_must_rotate` at every one of the 9 call sites
        above (both gates ultimately agree that a rotate-pending audit
        principal may reach only `control_capabilities`, since `_gate_must_
        rotate`'s own allow-list for `role="audit"` is `control_capabilities`
        only too -- see that method's docstring -- but this one runs first
        so a non-rotate-pending audit principal calling a write endpoint
        gets the role-authorization denial, not a confusing must_rotate one).
        """
        if context.role == "audit" and operation not in _AUDIT_ROLE_ALLOWED_OPERATIONS:
            self._deny(
                code="FORBIDDEN", status=403,
                message="This audit credential is not authorized for this operation; audit credentials are accepted only on the read-only control_capabilities, list_applications, and list_credentials endpoints.",
                event_class="authorization_denial", operation=operation, target_kind="control_credential", role=context.role,
                actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
                target_id=target_id,
            )

    def _gate_must_rotate(self, context: ControlAuthContext, *, operation: str, request_id: str, self_rotate: bool = False) -> None:
        """R-5/§7: allow-list gate -- only `control_capabilities` and a
        self-targeted `rotate_credential` (`role="control"` only) pass while
        `must_rotate` is true; every other operation is `FORBIDDEN`.
        Deliberately an allow-list, not a deny-list (design's own explicit
        warning: a deny-list silently fails open the moment a new operation
        is added and nobody remembers to list it).

        Phase 3.5 WP-4 (design §4 M-1): a `role="audit"` principal's own
        allow-list while `must_rotate` is true is `control_capabilities`
        ONLY -- self-rotate is deliberately NOT extended to it. This is not
        a dead end: the out-of-band audit-credential issuance ceremony
        (`issue_audit_credential_ceremony` below) issues AND rotates the
        credential in the same transaction before ever printing a secret, so
        a distributed audit credential's `must_rotate` is already `false` by
        the time anyone can authenticate with it -- an in-band audit
        principal is never actually stuck behind this gate in practice.
        """
        if not context.must_rotate:
            return
        if operation == "control_capabilities":
            return
        if context.role == "control" and operation == "rotate_credential" and self_rotate:
            return
        self._deny(
            code="FORBIDDEN", status=403,
            message="This control credential must be rotated (GET /control/v1/capabilities and self-rotate are the only operations available until then).",
            event_class="authorization_denial", operation=operation, target_kind="control_credential", role=context.role,
            actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
        )

    def _deny_role_control(self, context: ControlAuthContext, application_id: Any, *, request_id: str) -> None:
        self._deny(
            code="CAPABILITY_UNSUPPORTED", status=400,
            message="Issuing a role=control credential in-band is not supported; control credentials are created only by the operator bootstrap/reset ceremony.",
            event_class="capability_denial", operation="issue_credential", target_kind="credential", role=context.role,
            actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
            application_id=application_id if isinstance(application_id, str) else None,
            extra_details={"futility": _FUTILITY_DECLARATION},
        )

    def _deny_issuance_frozen(self, context: ControlAuthContext, application_id: str, *, request_id: str) -> None:
        """Phase 3.5 WP-4 (design §4/§1-E, P35-D6/D13): `FORBIDDEN` -- the
        contract's own chosen code for this refusal (M-8: no existing
        application-disabled issuance refusal exists to match, so the design
        stage fixed this one directly; `CONFLICT` was rejected as easily
        confused with the two-state application registry). Fail-closed,
        durably audited, same `_deny` machinery as every other refusal here.
        """
        self._deny(
            code="FORBIDDEN", status=403,
            message="Credential issuance for this application is frozen (an out-of-band deployer operation); only an operator can lift the freeze.",
            event_class="authorization_denial", operation="issue_credential", target_kind="credential", role=context.role,
            actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
            application_id=application_id,
        )

    def _deny(
        self,
        *,
        code: str,
        status: int,
        message: str,
        event_class: str,
        operation: str,
        target_kind: str,
        request_id: str,
        actor_id: str | None = None,
        actor_type: str = "unknown",
        role: str | None = None,
        application_id: str | None = None,
        target_id: str | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> None:
        """R-6/R-11: writes one durable denial event in its own, independent
        transaction, then raises the original denial with an R-11
        declaration attached. "No state change to share one with" (design
        §4) describes the ordinary call sites (`_authenticate`/`_gate_must_
        rotate`/`_deny_role_control`), which run before any state-changing
        `unit_of_work` is even opened. The last-active-control-credential
        revoke gate (design R-3, WP-3) calls `_deny` from a different
        position -- from INSIDE an already-open `control_credentials_unit_
        of_work` transaction (`revoke_credential`'s own `_body`) -- but the
        "independent transaction" property still holds in practice: `self.
        _audit` (`ControlAuditSink`/`PostgresControlAuditSink`) is backed by
        its own, separate connection/pool from the one `control_credentials_
        unit_of_work` holds open (see `PostgresControlAuditSink.__init__`'s
        own dedicated `_RolePool`), so the audit row this call writes
        commits independently of, and is never rolled back by, the
        enclosing `_body`'s own transaction aborting after `_deny` raises
        (which it always does -- `_deny` never returns normally). Durably
        recorded audit evidence for a denial made from inside an open
        transaction survives that transaction's own rollback for the same
        reason two ordinary, unrelated database connections' commits are
        independent of each other.

        If the durable write itself fails, the *whole response* becomes
        `SERVICE_UNAVAILABLE` (503) instead -- the original denial code/
        message/declaration are discarded, not merely supplemented, which
        is what keeps "audited: true" truthful by construction (a response
        can never claim durable attribution for an event that was not, in
        fact, durably recorded).

        Round-2 review MA-2: the declaration text itself must be truthful
        about *attribution*, not just about durability -- the attributed
        form ("...attributed to the credential that made it...") is only
        used when `actor_id` identifies a real credential (the audit row
        this call is about to write actually names one); every other denial
        gets the plain "recorded" form, which claims durability but no
        attribution. Both forms are still `details["attribution"]` -- the
        key name is unchanged, only its value differs by case.
        """
        declaration = _ATTRIBUTED_DECLARATION if actor_id is not None else _RECORDED_DECLARATION
        try:
            self._audit.append(
                event_class=event_class, request_id=request_id, application_id=application_id,
                actor_type=actor_type, actor_id=actor_id, role=role, operation=operation,
                target_kind=target_kind, outcome="deny", reason_code=code, target_id=target_id,
            )
        except Exception:
            # MI-9: cause-neutral -- does not assert the audit trail
            # specifically was what failed to write (SI-10: no internal
            # architecture detail in a public-facing message beyond what is
            # already implied by 503 itself).
            fail("SERVICE_UNAVAILABLE", "The request could not be durably recorded and was refused.", status=503)
        details = {"audited": True, "attribution": declaration}
        if extra_details:
            details.update(extra_details)
        fail(code, message, status=status, details=details)

    def check_rate(self) -> None:
        """CCR-14 WP-4 round-2 (independent review MAJOR-1): public wrapper
        around `_check_rate` below, charging exactly one token against the
        R-7 `control_requests_per_minute` window (or raising `LIMIT_EXCEEDED`/
        429, same as every internal call site).

        Exists so an HTTP binding layer (`control_http.py`) can charge the
        window *before* it does anything else -- including reading/parsing a
        request body -- for the 3 endpoints whose request schema is read off
        the body before the corresponding service method is called at all
        (design §12.5: those methods take already-extracted arguments, so
        the HTTP layer must shape-check the body first; see `control_http.
        py`'s own module docstring for why that ordering is otherwise
        correct). Without a way to charge the window ahead of that shape
        check, a malformed/unauthenticated body flood against `register_
        application`/`issue_credential`/`revoke_credential` never touched
        `_check_rate` at all -- an unbounded, unauthenticated path under a
        `limit_enforcement: "enforced"` capability declaration (round-2
        review MAJOR-1, measured).

        A caller that calls `check_rate()` itself and then calls one of the
        9 operation methods below **must** pass `rate_precharged=True` to
        that call -- otherwise the window is charged twice for one logical
        request. Every operation method's own default (`rate_precharged=
        False`) keeps every *other* caller (this repository's own tests,
        the in-process conformance adapter WP-5 will wire up) fully charged
        exactly as before this fix: the in-process path calls a method
        directly, once, with no separate `check_rate()` call, so the
        internal `_check_rate()` below still runs and still charges one
        token per call, unchanged.
        """
        self._check_rate()

    def _check_rate(self) -> None:
        """R-7 `control_requests_per_minute` -- a single, global window
        (never keyed per-credential/actor, unlike the data plane's
        `DataService._acquire_rate`): this check runs *before*
        authentication (design §4/R-6's own "監査増幅の防止" -- an
        unauthenticated caller must not be able to generate unbounded durable
        audit rows), so there is no `credential_id` to key on yet even in
        principle. Rate-limit refusals are deliberately never durably
        audited at all (design §4: "拒否には状態変更が無い...rate limit超過
        は監査しない(認証前・実行者不明。監査増幅DoSの防止)") -- this is the
        one denial category with no R-11 `audited: true` declaration.

        Round-2 review MI-7 (supervisor ruling): this is a *sliding* window
        (every call re-filters to "within the last 60s of `self._clock()`"),
        not the fixed/bucketed window design §1 R-7 says merely "suffices"
        (固定窓で足りる) -- a fixed window is a permissive floor, not a
        ceiling, and the sliding form is strictly stricter (no boundary
        double-burst at a bucket edge) while staying bounded (this list can
        never hold more than `control_requests_per_minute` entries, by the
        `fail()` below). Kept deliberately rather than downgraded to match
        the design's minimum; noted here so a future reader does not "fix"
        this back down to a fixed window under the mistaken impression the
        design requires it."""
        now = self._clock()
        with self._rate_lock:
            self._rate_window[:] = [stamp for stamp in self._rate_window if now - stamp < 60]
            if len(self._rate_window) >= self._limits.control_requests_per_minute:
                fail("LIMIT_EXCEEDED", "Control-plane request rate limit exceeded.", status=429, details={"resource": "control_requests_per_minute", "limit_class": "control_requests_per_minute", "limit": self._limits.control_requests_per_minute})
            self._rate_window.append(now)

    def check_audit_rate(self) -> None:
        """Phase 4 WP-2(b) (design D-5, `check_rate`'s own public-wrapper
        precedent above): lets `control_http.py` charge `audit_query`'s own
        window before it even reads a request body, for the SAME
        `rate_precharged=True` reason `check_rate` documents. A caller that
        calls this itself and then `audit_query(..., rate_precharged=True)`
        must not also call `check_rate()` for the same request -- `audit_
        query` never touches `control_requests_per_minute` at all, by
        design (M-8 / P4-D4 item 8)."""
        self._check_audit_rate()

    def _check_audit_rate(self) -> None:
        """`audit_requests_per_minute` -- a SEPARATE global window from
        `_check_rate`'s `control_requests_per_minute` above (own lock, own
        list, own limit field), reusing the identical sliding-window
        mechanism (never a new one -- work order §6 item 5: "制約・制限の
        追加で問題を回避しない...新機構を発明しない"). Pre-auth, exactly
        like `_check_rate` (this window governs BOTH `/control/v1/audit/
        query` and its `/v1/audit/query` alias, before either path even
        extracts a bearer token) -- and, identically, never durably
        audited (rate-limit refusals carry no attributable actor yet; the
        same "監査増幅の防止" reasoning `_check_rate` documents applies
        unchanged to this second window).
        """
        now = self._clock()
        with self._audit_rate_lock:
            self._audit_rate_window[:] = [stamp for stamp in self._audit_rate_window if now - stamp < 60]
            if len(self._audit_rate_window) >= self._limits.audit_requests_per_minute:
                fail(
                    "LIMIT_EXCEEDED", "Audit query request rate limit exceeded.", status=429,
                    details={"resource": "audit_requests_per_minute", "limit_class": "audit_requests_per_minute", "limit": self._limits.audit_requests_per_minute},
                )
            self._audit_rate_window.append(now)


def _uuid() -> str:
    return str(uuid.uuid4())


# ===========================================================================
# Ceremony core (CCR-14 WP-5, design §5 WP-5 row / §2 item 2 of the work
# order): the bootstrap/reset ritual's actual decision logic (existence
# check, atomic revoke-all+add, same-transaction canonical audit), extracted
# out of `ops.py` into real, reusable product code. Two callers share this
# exact code, never two independent reimplementations of "what does
# bootstrap/reset mean": `ops.py cmd_bootstrap`/`cmd_reset` (Postgres store,
# wrapped in `_lock_ritual`'s advisory lock -- the Postgres-only
# serialization guard the work order requires) and the WP-5 in-process
# conformance adapter (in-memory store, no lock -- a single adapter instance
# has no concurrent daemons to serialize against, design §5 item 2: "advisory
# lock は Postgres 経路のみ").
#
# `control_credentials`/`audit` are duck-typed against the exact call
# surfaces `ControlCredentialStore`/`PostgresControlCredentialStore`
# (`has_any`/`add`/`revoke_all`) and `ControlAuditSink`/
# `PostgresControlAuditSink` (`append(..., work=...)`) already share --
# these two functions work unmodified against either backend pairing, same
# as `ControlBackend`/`ControlPlaneService` above never branch on which
# concrete store they were given.
# ===========================================================================


def bootstrap_control_credential(
    control_credentials: Any,
    audit: Any,
    *,
    work: Any,
    credential_id: str | None = None,
    secret: str | None = None,
    request_id: str | None = None,
    actor_type: str = "operator_cli",
) -> tuple[str, str]:
    """R-5 bootstrap ceremony core. Refuses (`CONFLICT`) when *any*
    control-credential row exists, including a fully-revoked one (§8 M-6:
    the contract's own text is "while a control credential exists", not
    "while an unrevoked one exists"). Issues one credential and writes the
    canonical `bootstrap_control_credential` audit event inside the same
    `work` transaction the caller already opened -- a fault in `audit.
    append` therefore aborts the issuance too (fail-closed by construction,
    R-6's "同一トランザクション" guarantee), through the caller's own
    enclosing `unit_of_work()` rollback, not through any handling here.

    Returns `(credential_id, secret)`. `credential_id`/`secret` may be
    supplied by the caller (parity/replay tests); by default both are
    freshly generated.
    """
    credential_id = credential_id or _new_control_credential_id()
    secret = secret or _new_secret()
    if control_credentials.has_any(include_revoked=True, work=work):
        fail("CONFLICT", "a control credential already exists; bootstrap runs at most once -- use `reset` to recover", status=409)
    control_credentials.add(credential_id, secret, work=work)
    audit.append(
        event_class="control_credential_lifecycle", request_id=request_id or _uuid(), application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="bootstrap_control_credential",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id, work=work,
    )
    return credential_id, secret


def reset_control_credentials(
    control_credentials: Any,
    audit: Any,
    *,
    work: Any,
    credential_id: str | None = None,
    secret: str | None = None,
    request_id: str | None = None,
    actor_type: str = "operator_cli",
) -> tuple[str, str]:
    """R-5 reset ceremony core -- see `bootstrap_control_credential`'s
    docstring immediately above for the shared-code rationale. Revokes
    every existing control credential and issues one new one, both inside
    the same `work` transaction (R-5/§7 "reset の原子性": no fault-injected
    or crashed moment can ever leave the old credentials revoked but no new
    one minted, or vice versa)."""
    credential_id = credential_id or _new_control_credential_id()
    secret = secret or _new_secret()
    control_credentials.revoke_all(work=work)
    control_credentials.add(credential_id, secret, work=work)
    audit.append(
        event_class="control_credential_lifecycle", request_id=request_id or _uuid(), application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="reset_control_credentials",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id, work=work,
    )
    return credential_id, secret


def issue_audit_credential_ceremony(
    control_credentials: Any,
    audit: Any,
    *,
    work: Any,
    credential_id: str | None = None,
    request_id: str | None = None,
    actor_type: str = "operator_cli",
) -> tuple[str, str]:
    """Phase 3.5 WP-4 out-of-band audit-credential issuance ceremony (design
    PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4/§1-D, P35-D12/M-1). Same
    extraction rationale as `bootstrap_control_credential`/`reset_control_
    credentials` above (reusable product code, not hand-rolled per caller --
    `ops.py cmd_issue_audit_credential` is this WP's own only caller today).

    Unlike bootstrap/reset, this ceremony issues AND rotates the credential
    in the SAME transaction, before a secret is ever handed back to the
    caller: an `audit`-role principal has no in-band self-rotate path at all
    (`ControlPlaneService._gate_must_rotate`'s own allow-list for `role=
    "audit"` while `must_rotate` is true is `control_capabilities` ONLY --
    design's own explicit decision not to extend self-rotate to it, since
    the whole point of completing the rotation here is that no in-band path
    should ever need to). Issuing with `must_rotate=true` and leaving it to
    the operator to somehow clear it out-of-band-again would be a dead end;
    this ceremony closes that gap structurally by never printing a secret
    whose `must_rotate` is still true. The intermediate `add()`-time secret
    is generated, used once to satisfy `add`'s own required `secret`
    parameter, and immediately discarded -- only the final, post-`rotate()`
    secret is ever returned (and therefore ever printed by `ops.py`).

    Returns `(credential_id, secret)` -- `secret` is the one that actually
    authenticates (post-rotation); `must_rotate` is `false` for it already.
    """
    credential_id = credential_id or _new_control_credential_id()
    issuance_secret = _new_secret()
    distributed_secret = _new_secret()
    control_credentials.add(credential_id, issuance_secret, role="audit", work=work)
    control_credentials.rotate(credential_id, distributed_secret, work=work)
    audit.append(
        event_class="control_credential_lifecycle", request_id=request_id or _uuid(), application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="issue_audit_credential",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id, work=work,
    )
    return credential_id, distributed_secret


__all__ = [
    "ControlBackend",
    "ControlPlaneService",
    "InMemoryControlBackend",
    "PostgresControlBackend",
    "bootstrap_control_credential",
    "reset_control_credentials",
    "issue_audit_credential_ceremony",
]
