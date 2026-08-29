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
from .auth import ControlAuthContext, ControlCredentialStore, CredentialStore, _InMemoryWork
from .errors import FoundationError, fail
from .limits import ControlPlaneLimits
from .service import ControlAuthority

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
    def list_control_credentials(self) -> list[tuple[str, bool, bool]]: ...
    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None: ...
    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None: ...


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

    def authenticate(self, secret: str | None) -> ControlAuthContext:
        return self._control_credentials.authenticate(secret)

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
        work = _InMemoryWork()
        try:
            yield work
        except BaseException:
            service._cells = cells_snapshot  # noqa: SLF001
            service._disabled_apps = disabled_snapshot  # noqa: SLF001
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

    def list_control_credentials(self) -> list[tuple[str, bool, bool]]:
        return [(r.credential_id, r.enabled, r.revoked) for r in self._control_credentials.list_all()]

    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        self._control_credentials.rotate(credential_id, secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._control_credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)


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

    def list_control_credentials(self) -> list[tuple[str, bool, bool]]:
        return self._control_credentials.list_all()

    def rotate_control_credential(self, credential_id: str, secret: str, *, work: Any) -> None:
        self._control_credentials.rotate(credential_id, secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled: bool | None, revoked: bool | None, work: Any) -> None:
        self._control_credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)


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
    ) -> None:
        self._backend = backend
        self._audit = audit
        self._limits = limits or ControlPlaneLimits()
        self._clock = clock or time.monotonic
        self._rate_lock = threading.Lock()
        self._rate_window: list[float] = []

    # =====================================================================
    # Public operations (design §1's operation catalog / §2's endpoint map)
    # =====================================================================

    def capabilities(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "control_capabilities", request_id=request_id)
        limits = self._limits.as_dict()
        return {
            "contract_version": "1.1.0",
            "capabilities": {
                "control_plane": {"status": "enabled"},
                "audit_query": {"status": "unavailable"},
            },
            "limits": limits,
            "limit_enforcement": {name: "enforced" for name in limits},
            "authorization_propagation_bound_ms": 0,
            "role": "control",
        }

    def register_application(self, secret: str | None, application_id: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "register_application", request_id=request_id)
        self._validate_application_id(application_id)
        if self._backend.application_exists(application_id):
            fail("CONFLICT", "Application already exists.", status=409)
        if self._backend.applications_count() >= self._limits.applications:
            fail("LIMIT_EXCEEDED", "Application registration limit exceeded.", status=413, details={"resource": "applications", "limit": self._limits.applications})

        def _body(work: Any) -> dict[str, Any]:
            self._backend.register_application(application_id, work=work)
            self._write_state_audit(work, event_class="application_lifecycle", operation="register_application", target_kind="application", application_id=application_id, actor=context, request_id=request_id)
            return {"application_id": application_id, "enabled": True}

        return self._run_state_change(self._backend.applications_unit_of_work, _body)

    def list_applications(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "list_applications", request_id=request_id)
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
        self._gate_must_rotate(context, operation, request_id=request_id)
        if not self._backend.application_exists(application_id):
            fail("NOT_FOUND", "Application was not found.", status=404)

        def _body(work: Any) -> dict[str, Any]:
            self._backend.set_application_enabled(application_id, enabled, work=work)
            self._write_state_audit(work, event_class="application_lifecycle", operation=operation, target_kind="application", application_id=application_id, actor=context, request_id=request_id)
            return {"application_id": application_id, "enabled": enabled}

        return self._run_state_change(self._backend.applications_unit_of_work, _body)

    def issue_credential(self, secret: str | None, application_id: Any, role: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "issue_credential", request_id=request_id)
        # (4) semantic/shape validation -- `role=control` is a *shape-valid*
        # enum member (contract `CredentialIssueRequest`), so it must pass
        # this check before the (5) capability refusal below can reject it
        # specifically as a capability question, not a shape one.
        if role not in _ALL_ISSUABLE_ROLES:
            fail("VALIDATION_FAILED", "role must be one of runtime, developer, control.")
        self._validate_application_id(application_id)
        # (5) capability denial -- BEFORE target resolution/limit (§8 M-1,
        # §2 evaluation-order ruling): must refuse `role=control` even when
        # the named application does not exist, is disabled, or is already
        # at its credential limit -- none of those questions are reached.
        if role == "control":
            self._deny_role_control(context, application_id, request_id=request_id)
        # (6) target resolution
        if not self._backend.application_exists(application_id):
            fail("NOT_FOUND", "Application was not found.", status=404)
        # (8) limit check -- disabled Applications are NOT refused here
        # (design §6 supervisor decision (3): issuance to a disabled
        # Application is permitted; enforcement already lives in `enabled`).
        if self._backend.credentials_active_count(application_id) >= self._limits.credentials_per_application:
            fail("LIMIT_EXCEEDED", "Credentials-per-application limit exceeded.", status=413, details={"resource": "credentials_per_application", "limit": self._limits.credentials_per_application})

        credential_id = _new_credential_id()
        secret_value = _new_secret()

        def _body(work: Any) -> dict[str, Any]:
            self._backend.issue_credential(credential_id, application_id, role, secret_value, work=work)
            self._write_state_audit(work, event_class="credential_lifecycle", operation="issue_credential", target_kind="credential", application_id=application_id, actor=context, request_id=request_id)
            return {"credential_id": credential_id, "application_id": application_id, "role": role, "secret": secret_value}

        return self._run_state_change(self._backend.credentials_unit_of_work, _body)

    def list_credentials(self, secret: str | None, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "list_credentials", request_id=request_id)
        rows: list[dict[str, Any]] = []
        for credential_id, application_id, role, enabled, revoked in self._backend.list_credentials():
            rows.append({"credential_id": credential_id, "application_id": application_id, "role": role, "enabled": enabled, "revoked": revoked})
        for credential_id, enabled, revoked in self._backend.list_control_credentials():
            # No `application_id` key at all (design §2: "control行はapplication_id無し"),
            # and `must_rotate` is never included (design §8 m-9).
            rows.append({"credential_id": credential_id, "role": "control", "enabled": enabled, "revoked": revoked})
        return {"credentials": rows}

    def rotate_credential(self, secret: str | None, credential_id: Any, *, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self_rotate = isinstance(credential_id, str) and credential_id == context.credential_id
        self._gate_must_rotate(context, "rotate_credential", request_id=request_id, self_rotate=self_rotate)
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
                self._write_state_audit(work, event_class="credential_lifecycle", operation="rotate_credential", target_kind="credential", actor=context, request_id=request_id)
                return {"credential_id": credential_id, "secret": new_secret}

            return self._run_state_change(self._backend.credentials_unit_of_work, _body)

        def _control_body(work: Any) -> dict[str, Any]:
            self._backend.rotate_control_credential(credential_id, new_secret, work=work)
            self._write_state_audit(work, event_class="control_credential_lifecycle", operation="rotate_credential", target_kind="control_credential", actor=context, request_id=request_id)
            return {"credential_id": credential_id, "secret": new_secret}

        return self._run_state_change(self._backend.control_credentials_unit_of_work, _control_body)

    def revoke_credential(self, secret: str | None, credential_id: Any, *, destructive: Any = None, confirmation: Any = None, request_id: str | None = None, rate_precharged: bool = False) -> dict[str, Any]:
        # Q-1 (design §0.5): the contract's own destructive-confirmation
        # semantics are an undecided, not-yet-effective contract question --
        # `destructive`/`confirmation` are accepted here exactly as the
        # `CredentialRevokeRequest` schema allows, and deliberately NOT
        # inspected. Inventing a bespoke confirmation rule to fill that gap
        # would repeat the exact defect an earlier phase's own Q-1
        # correction was about; the design record is explicit that this
        # implementation must not do that. When the contract decision lands,
        # enforcing it is an additive change to this one method.
        del destructive, confirmation
        request_id = request_id or _uuid()
        if not rate_precharged:
            self._check_rate()
        context = self._authenticate(secret, request_id)
        self._gate_must_rotate(context, "revoke_credential", request_id=request_id)
        return self._set_credential_state(context, credential_id, revoked=True, operation="revoke_credential", request_id=request_id)

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
        self._gate_must_rotate(context, operation, request_id=request_id)
        return self._set_credential_state(context, credential_id, enabled=enabled, operation=operation, request_id=request_id)

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
                self._write_state_audit(work, event_class="credential_lifecycle", operation=operation, target_kind="credential", actor=context, request_id=request_id)
                return {"credential_id": credential_id, "enabled": result_enabled, "revoked": result_revoked}

            return self._run_state_change(self._backend.credentials_unit_of_work, _body)

        def _control_body(work: Any) -> dict[str, Any]:
            self._backend.set_control_credential_state(credential_id, enabled=enabled, revoked=revoked, work=work)
            self._write_state_audit(work, event_class="control_credential_lifecycle", operation=operation, target_kind="control_credential", actor=context, request_id=request_id)
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

    def _write_state_audit(self, work: Any, *, event_class: str, operation: str, target_kind: str, actor: ControlAuthContext, request_id: str, application_id: str | None = None) -> None:
        # Round-2 review MI-6 (supervisor ruling): `role` always names the
        # ACTOR's role, never the target's -- every control-plane operation
        # is performed by a control credential, so this is unconditionally
        # "control" (matching `ControlAuthority._control_event`'s own
        # existing convention, `role="control"`). Earlier code passed the
        # *issued* credential's role (`runtime`/`developer`) through here for
        # `issue_credential`'s own audit row, conflating actor and target --
        # fixed by dropping the caller-supplied override entirely; there is
        # no longer a `role` parameter to misuse.
        self._audit.append(
            event_class=event_class,
            request_id=request_id,
            application_id=application_id,
            actor_type="control_credential",
            actor_id=actor.credential_id,
            role="control",
            operation=operation,
            target_kind=target_kind,
            outcome="allow",
            reason_code=None,
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
                self._deny(
                    code=exc.code, status=exc.status, message=exc.message,
                    event_class="authentication_denial", operation="control_authenticate", target_kind="control_credential",
                    request_id=request_id,
                    actor_id=identified_credential_id,
                    actor_type="control_credential" if identified_credential_id else "unknown",
                    role="control" if identified_credential_id else None,
                )
            raise

    def _gate_must_rotate(self, context: ControlAuthContext, operation: str, *, request_id: str, self_rotate: bool = False) -> None:
        """R-5/§7: allow-list gate -- only `control_capabilities` and a
        self-targeted `rotate_credential` pass while `must_rotate` is true;
        every other operation is `FORBIDDEN`. Deliberately an allow-list, not
        a deny-list (design's own explicit warning: a deny-list silently
        fails open the moment a new operation is added and nobody remembers
        to list it)."""
        if not context.must_rotate:
            return
        if operation == "control_capabilities" or (operation == "rotate_credential" and self_rotate):
            return
        self._deny(
            code="FORBIDDEN", status=403,
            message="This control credential must be rotated (GET /control/v1/capabilities and self-rotate are the only operations available until then).",
            event_class="authorization_denial", operation=operation, target_kind="control_credential", role="control",
            actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
        )

    def _deny_role_control(self, context: ControlAuthContext, application_id: Any, *, request_id: str) -> None:
        self._deny(
            code="CAPABILITY_UNSUPPORTED", status=400,
            message="Issuing a role=control credential in-band is not supported; control credentials are created only by the operator bootstrap/reset ceremony.",
            event_class="capability_denial", operation="issue_credential", target_kind="credential", role="control",
            actor_id=context.credential_id, actor_type="control_credential", request_id=request_id,
            application_id=application_id if isinstance(application_id, str) else None,
            extra_details={"futility": _FUTILITY_DECLARATION},
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
        extra_details: dict[str, Any] | None = None,
    ) -> None:
        """R-6/R-11: writes one durable denial event in its own, independent
        transaction (no state change to share one with -- design §4), then
        raises the original denial with an R-11 declaration attached. If the
        durable write itself fails, the *whole response* becomes `SERVICE_
        UNAVAILABLE` (503) instead -- the original denial code/message/
        declaration are discarded, not merely supplemented, which is what
        keeps "audited: true" truthful by construction (a response can never
        claim durable attribution for an event that was not, in fact,
        durably recorded).

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
                target_kind=target_kind, outcome="deny", reason_code=code,
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
                fail("LIMIT_EXCEEDED", "Control-plane request rate limit exceeded.", status=429, details={"resource": "control_requests_per_minute", "limit": self._limits.control_requests_per_minute})
            self._rate_window.append(now)


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
        target_kind="control_credential", outcome="allow", reason_code=None, work=work,
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
        target_kind="control_credential", outcome="allow", reason_code=None, work=work,
    )
    return credential_id, secret


__all__ = [
    "ControlBackend",
    "ControlPlaneService",
    "InMemoryControlBackend",
    "PostgresControlBackend",
    "bootstrap_control_credential",
    "reset_control_credentials",
]
