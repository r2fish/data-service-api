"""MitateDB-api plug for the common conformance port.

Module name matters here: `conformance-tests/registry.json` declares this
peer's module as `conformance_adapter_mitatedb`, and
`conformance-tests/conftest.py` discovers it by adding this file's
directory to `sys.path` and calling
`importlib.import_module("conformance_adapter_mitatedb")` -- a plain name
lookup, not a path load -- so this file must keep this exact basename.

This module owns the connection between the common port
(`conformance-tests/adapter.py`, importable as top-level module `adapter`,
NORMATIVE per docs/design/CONFORMANCE_ADAPTER_V1.md section 4) and this
peer's own foundation. It does not redefine or reinterpret the port's value
types or ABC signatures; it only implements them against `mitatedb_api`.

Synthetic values only: application ids, credential ids and secrets used
here are conformance-suite fixtures, never real deployment values (CLAUDE.md
Public Repository Security Gate). Identifiers are kept lowercase
(`^[a-z][a-z0-9_]{0,62}$`) per this peer's stricter catalog policy and per
design doc section 4.2 / section 8 finding 2.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

# The common port lives at conformance-tests/adapter.py. When the combined
# suite runs from the repository root (root pyproject.toml pythonpath,
# or conftest.py's own top-level `from adapter import ConformanceAdapter`
# which runs before any peer conformance/ directory is added to sys.path),
# `import adapter` already resolves there and is cached in sys.modules.
# This fallback only matters when this file is loaded standalone (e.g. a
# direct file load for local exercising of this adapter alone).
if "adapter" not in sys.modules:
    _conformance_tests = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests) and _conformance_tests not in sys.path:
        sys.path.insert(0, _conformance_tests)

from adapter import (  # noqa: E402
    CATALOG_SURFACE_ABSENT,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ControlCredentialHandle,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    resolve_valid_confirmation,
)

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role  # noqa: E402
from mitatedb_api.cell import ApplicationDeveloper, ApplicationRuntime  # noqa: E402
from mitatedb_api.config import FoundationConfig  # noqa: E402
from mitatedb_api.control_audit import ControlAuditSink  # noqa: E402
from mitatedb_api.control_auth import ControlCredentialStore, _InMemoryWork  # noqa: E402
from mitatedb_api.control_plane import (  # noqa: E402
    ControlPlaneLimits,
    ControlPlaneService,
    bootstrap_control_credential,
    reset_control_credentials,
)
from mitatedb_api.errors import (  # noqa: E402
    AuthenticationError,
    AuthorizationError,
    AuthorizationStateUnavailable,
    CapabilityError,
    ConflictError,
    DestructiveConfirmationRequired,
    FoundationError,
    NotFoundError,
    ResourceLimitError,
    ValidationError,
)
from mitatedb_api.service import MitateDataService as _MitateDataServiceClass  # noqa: E402,F401

_CLASSIFY_ORDER = (
    (AuthorizationStateUnavailable, "AUTH_STATE_UNAVAILABLE"),
    (AuthenticationError, "AUTH_INVALID"),
    (AuthorizationError, "FORBIDDEN"),
    (CapabilityError, "CAPABILITY_UNSUPPORTED"),
    (ValidationError, "VALIDATION_FAILED"),
    (ResourceLimitError, "LIMIT_EXCEEDED"),
    # WP-5 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5): no shared
    # inheritance with any neighbor above/below, so this entry's exact
    # position in the tuple does not affect classification -- placed here,
    # matching the real evaluation order `ApplicationCell.delete` itself
    # follows (shape/identifier validation, then confirmation, then
    # execution).
    (DestructiveConfirmationRequired, "DESTRUCTIVE_CONFIRMATION_REQUIRED"),
    (ConflictError, "CONFLICT"),
    (NotFoundError, "NOT_FOUND"),
)


class _ReconciledControlBackend:
    """WP-5 flip -- `control_plane.ControlPlaneService` backend built
    directly on THIS adapter's own `ProvisioningFacade`/`auth.
    CredentialStore` (design v1.2 R-8, WP-4 handoff item i "2ストア突合").

    Deliberately NOT `control_plane.InMemoryControlBackend`: that class is
    WP-4's own self-contained pair of registries (`InMemoryApplication
    Registry`/`InMemoryCredentialRegistry`), independent from `auth.
    CredentialStore` by design (its own module docstring: "keeps every
    existing, already-reviewed application-plane file untouched"). Using
    it here would give this adapter two disconnected representations of
    "which applications/credentials exist" -- an in-band `issue_credential_
    inband` would mint a row `MitateDataService.open_session`'s own real
    `authenticate()` could never see, which is exactly the gap the design
    document flags as a WP-5 completion condition, not a cosmetic
    difference. Every application/credential method below instead calls
    `auth.CredentialStore`'s own methods (several added this WP purely to
    give `ControlPlaneService` the read/write surface it needs, `auth.py`'s
    own WP-5 docstring notes) -- the SAME dict `authenticate()` reads.

    Control credentials and durable audit have no application-plane
    analogue at all (a control credential belongs to no Application, and
    an in-memory audit trail exists nowhere else on this peer) -- those two
    delegate to the product's own, genuinely self-contained `control_auth.
    ControlCredentialStore`/`control_audit.ControlAuditSink` unchanged.
    """

    def __init__(self, control: "ControlPlane", control_credentials: ControlCredentialStore,
                 audit: ControlAuditSink) -> None:
        self._control = control
        self._control_credentials = control_credentials
        self._audit = audit

    @property
    def control_credential_store(self) -> ControlCredentialStore:
        return self._control_credentials

    @property
    def audit_sink(self) -> ControlAuditSink:
        return self._audit

    @contextmanager
    def unit_of_work(self):
        work = _InMemoryWork()
        try:
            yield work
        except BaseException:
            work.rollback()
            raise

    def application_exists(self, application_id: str) -> bool:
        return self._control.credentials.application_exists(application_id)

    def applications_count(self) -> int:
        return self._control.credentials.applications_count()

    def list_applications(self):
        return self._control.credentials.list_applications()

    def register_application(self, application_id: str, *, work) -> None:
        self._control.provision_application(application_id)

        def _undo() -> None:
            self._control.cells.pop(application_id, None)
            self._control.credentials.unregister_application(application_id)
        work.on_rollback(_undo)

    def set_application_enabled(self, application_id: str, enabled: bool, *, work) -> None:
        current = dict(self._control.credentials.list_applications()).get(application_id)
        if current is None:
            raise NotFoundError("application not found")
        (self._control.credentials.enable_application if enabled
         else self._control.credentials.disable_application)(application_id)
        work.on_rollback(
            lambda: (self._control.credentials.enable_application if current
                     else self._control.credentials.disable_application)(application_id)
        )

    def credential_state(self, credential_id: str):
        return self._control.credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._control.credentials.credentials_active_count(application_id)

    def list_credentials(self):
        return self._control.credentials.list_credentials()

    def issue_credential(self, application_id: str, role: str, *, credential_id: str, secret: str, work) -> None:
        self._control.credentials.issue(application_id, role, credential_id=credential_id, secret=secret)
        work.on_rollback(lambda: self._control.credentials.forget_credential(credential_id))

    def rotate_credential(self, credential_id: str, secret: str, *, work) -> None:
        snapshot = self._control.credentials.snapshot_credential_state(credential_id)
        if snapshot is None:
            raise NotFoundError("credential not found")
        self._control.credentials.rotate(credential_id, secret)
        work.on_rollback(lambda: self._control.credentials.restore_credential_state(credential_id, snapshot))

    def set_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        snapshot = self._control.credentials.snapshot_credential_state(credential_id)
        if snapshot is None:
            raise NotFoundError("credential not found")
        if enabled is not None:
            (self._control.credentials.enable if enabled else self._control.credentials.disable)(credential_id)
        if revoked:
            self._control.credentials.revoke(credential_id)
        work.on_rollback(lambda: self._control.credentials.restore_credential_state(credential_id, snapshot))

    def control_credential_state(self, credential_id: str):
        state = self._control_credentials.get_state(credential_id)
        return None if state is None else (state[0], state[1])

    def list_control_credentials(self):
        return self._control_credentials.list_all()

    def control_credentials_locked(self, work):
        return self._control_credentials.locked_for_update(work)

    def rotate_control_credential(self, credential_id: str, secret: str, *, work) -> None:
        self._control_credentials.rotate(credential_id, secret=secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        if enabled is not None:
            (self._control_credentials.enable if enabled else self._control_credentials.disable)(credential_id, work=work)
        if revoked:
            self._control_credentials.revoke(credential_id, work=work)

    def authenticate_control(self, credential_id, secret):
        return self._control_credentials.authenticate(credential_id, secret)

    def append_audit(self, *, work=None, **fields):
        return self._audit.append(work=work, **fields)


class MitateDBConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to the MitateDB-api foundation.

    A "session" for this peer is an `ApplicationRuntime` /
    `ApplicationDeveloper`. Control-plane operations go through
    `ControlPlane`, which a session object has no way to reach (cell.py
    sessions only ever hold a cell handle and a Principal).
    """

    name = "MitateDB-api"

    def __init__(self) -> None:
        # Synthetic pepper for this conformance run only; never a real
        # deployment secret and never read from the environment.
        # WP-5 flip (design v1.2 R-7): `control_plane_status="enabled"` is
        # a real constructor injection into the SAME `FoundationConfig`
        # every provisioned cell shares (R-3: single source of truth) --
        # not a value this adapter fabricates only inside
        # `capability_document()`.
        self._control = ControlPlane(
            "synthetic-conformance-pepper-mitatedb-0000000",
            config=FoundationConfig(control_plane_status="enabled"),
        )
        self._service = MitateDataService(self._control)
        self._counter = 0
        # port v1.6 declare-and-echo (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): cached after the
        # first real `capability_document()` call, mirroring both r2db-api
        # plugs' identical cache -- this peer's declared `contract_version`
        # is static for this adapter instance's whole lifetime.
        self._contract_version_cache: str | None = None
        # WP-5 (design v1.2 R-8 second-round M-1): `capability_document()`
        # used to provision a fresh, throwaway probe Application on EVERY
        # call (measured: 39 of 155 applications this adapter provisioned
        # across one full conformance session were probe-only churn). A
        # single reused probe session removes that churn entirely and
        # directly relieves headroom pressure on the `applications`
        # resource bound C-14 vector 5 drives to its exact declared limit.
        self._capability_probe_session: object | None = None

        # ------------------------------------------------------------
        # control plane (WP-5 provided branch): `ControlPlaneService`
        # backed by `_ReconciledControlBackend` (this module, above) --
        # application/credential writes land in THIS adapter's own
        # `ControlPlane`/`auth.CredentialStore` (2ストア突合); control
        # credentials and durable audit use the product's own
        # self-contained `control_auth.ControlCredentialStore`/
        # `control_audit.ControlAuditSink`.
        #
        # Limits (mirrors r2db-api's own WP-5 measured rationale,
        # `conformance_adapter_r2db.py`'s identical comment): design v1.2
        # R-6's own example ("20") does not account for every OTHER
        # condition test's own `build_fixture()` -> `provision_application()`
        # also registering a real application against this SAME adapter
        # instance's shared state for the rest of the session.
        # `applications=100/credentials_per_application=5/
        # control_requests_per_minute=200` satisfies R-6's numeric
        # constraints (each <=200; `200 > 100 + 2*5 + 67`) with the SAME
        # margin r2db-api measured sufficient for its own, larger combined
        # suite; WP-5's own completion condition requires recording this
        # adapter's real measured `n_existing` (both at C-14 vector 5 and
        # at session end) -- see the WP-5 completion report.
        # ------------------------------------------------------------
        self._control_credential_pepper = "synthetic-conformance-pepper-mitatedb-ctl-0000000"
        self._control_credentials = ControlCredentialStore(self._control_credential_pepper)
        self._control_audit = ControlAuditSink()
        self._control_backend = _ReconciledControlBackend(self._control, self._control_credentials, self._control_audit)
        self._control_limits = ControlPlaneLimits(
            applications=100, credentials_per_application=5, control_requests_per_minute=200)
        self._control_service = ControlPlaneService(self._control_backend, limits=self._control_limits)
        # `control_credential()`'s own maintained handle (memoize + call-
        # time validity check -- port v1.5 WP-1 independent review major
        # M-4: "MUST return a handle that is genuinely valid AT CALL
        # TIME...never a memoized value"), mirroring both r2db-api plugs'
        # identical mechanism.
        self._control_credential_ref: str | None = None
        self._control_credential_secret: str | None = None

    # ------------------------------------------------------------------
    # control plane
    # ------------------------------------------------------------------
    def provision_application(self, application_id: str) -> None:
        self._control.provision_application(application_id)

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        role_enum = role if isinstance(role, Role) else Role(role)
        credential_id, secret = self._control.issue_credential(application_id, role_enum)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role_enum.value, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._control.revoke_credential(handle.credential_ref)

    def disable_application(self, application_id: str) -> None:
        self._control.disable_application(application_id)

    def enable_application(self, application_id: str) -> None:
        # ControlPlane exposes no facade method for this (see
        # service.py); the credential store itself does.
        self._control.credentials.enable_application(application_id)

    def set_authorization_state_available(self, available: bool) -> None:
        self._control.credentials.authorization_state_available = bool(available)

    def propagation_bound_ms(self) -> int:
        # CredentialStore.assert_active() is invoked by the session's guard
        # on every single operation (cell.py ApplicationRuntime.__authorize),
        # re-checking enabled/revoked/disabled/expiry state each time. There
        # is no cache, so propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # `ApplicationRuntime.capabilities()` is scoped to an authenticated
        # session (contract `endpoints.capabilities.auth`: "application or
        # control"), so this provisions a disposable application/credential
        # solely to obtain the peer's own real capability document -- it
        # does not fabricate one in the adapter. WP-5 (design v1.2 R-8
        # second-round M-1): the probe application/session is provisioned
        # ONCE and reused for every later call, not re-provisioned per call
        # (this peer's own `capabilities()` reads no per-request state --
        # `assert_active` re-checks the SAME session's authorization on
        # every call, so a reused session observes the peer's current
        # capability document exactly as faithfully as a fresh one would).
        if self._capability_probe_session is None:
            self._counter += 1
            probe_app = f"conf_capability_probe_{self._counter}_{uuid.uuid4().hex[:8]}"
            self.provision_application(probe_app)
            handle = self.issue_credential(probe_app, "runtime")
            self._capability_probe_session = self.authenticate(handle)
        session = self._capability_probe_session
        return self._call(lambda: session.capabilities())

    def _declared_contract_version(self) -> str:
        # port v1.6 declare-and-echo (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): cached after the
        # first real `capability_document()` call, mirroring both r2db-api
        # plugs' identical cache.
        if self._contract_version_cache is None:
            self._contract_version_cache = str(self.capability_document()["contract_version"])
        return self._contract_version_cache

    def _resolve_confirmation(self, confirmation: Any, *, probe: Callable[[], Any], legacy_token: Any) -> Any:
        """`VALID_CONFIRMATION` sentinel resolution (design R-6 item 1,
        `adapter.resolve_valid_confirmation`) -- identical contract to both
        r2db-api plugs' own method of the same name. `legacy_token` is this
        peer's own pre-1.2.0 boolean `confirm=True` (not a string -- this
        peer's `confirm` parameter is boolean until the WP-5 declare-and-
        echo flip, design R-5)."""
        if confirmation is not VALID_CONFIRMATION:
            return confirmation
        return resolve_valid_confirmation(
            contract_version=self._declared_contract_version(), legacy_token=legacy_token, probe=probe
        )

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5) -- PROVIDED branch (WP-5 flip)
    # ------------------------------------------------------------------
    #
    # `control_plane.ControlPlaneService` (design v1.2 R-6, WP-4) is now a
    # real, constructed facade on this adapter (`self._control_service`,
    # `__init__` above) -- every one of the 14 port v1.5 in-band/ritual/
    # privileged operations below presents its request to that same real
    # service object, exactly as a real `/control/v1`-equivalent caller
    # would (this adapter never pre-filters by credential kind/role before
    # presenting a request). `_call` (this file's own existing helper,
    # used by every application-plane method already) is reused unchanged:
    # `ControlPlaneService` raises the identical `errors.FoundationError`
    # every other service method raises, so `classify()` needs no
    # control-plane-specific branch at all.

    def _actor_id_secret(self, actor: "CredentialHandle | ControlCredentialHandle") -> tuple[str, str]:
        # Both port handle types carry `.credential_ref`/`.secret`
        # (application `CredentialHandle` and control-plane
        # `ControlCredentialHandle` alike) -- this adapter never inspects
        # which kind `actor` is before presenting it: `ControlPlaneService.
        # _authenticate` tries the control-credential store only, so an
        # application credential's id/secret simply fails to match there,
        # exactly the fail-closed behavior C-14 vector 1 measures.
        return actor.credential_ref, actor.secret

    # port v1.5
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.control_capabilities(credential_id, secret))

    # port v1.5
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.register_application(credential_id, secret, application_id))

    # port v1.5
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        credential_id, secret = self._actor_id_secret(actor)
        result = self._call(lambda: self._control_service.list_applications(credential_id, secret))
        return result["applications"]

    # port v1.5
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.set_application_enabled(credential_id, secret, application_id, enabled))

    # port v1.5
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        credential_id, secret = self._actor_id_secret(actor)
        result = self._call(lambda: self._control_service.issue_credential(credential_id, secret, application_id, role))
        return CredentialHandle(
            credential_ref=result["credential_id"], application_id=result["application_id"],
            role=result["role"], secret=result["secret"],
        )

    # port v1.5
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        credential_id, secret = self._actor_id_secret(actor)
        result = self._call(lambda: self._control_service.list_credentials(credential_id, secret))
        return result["credentials"]

    # port v1.5
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.rotate_credential(credential_id, secret, credential_ref))

    # port v1.5
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.revoke_credential(
            credential_id, secret, credential_ref, destructive=destructive, confirmation=confirmation))

    # port v1.5
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        credential_id, secret = self._actor_id_secret(actor)
        return self._call(lambda: self._control_service.set_credential_enabled(credential_id, secret, credential_ref, enabled))

    @contextmanager
    def _control_ritual_unit_of_work(self):
        """`control_auth.ControlCredentialStore` (unlike `_ReconciledControl
        Backend`/`control_plane.InMemoryControlBackend`) is a plain store
        with no `unit_of_work()` of its own -- the ceremony core
        (`bootstrap_control_credential`/`reset_control_credentials`) needs
        an `_InMemoryWork` token to pass as `work`, so this adapter builds
        one directly, the same shape `InMemoryControlBackend.unit_of_work`
        constructs internally."""
        work = _InMemoryWork()
        try:
            yield work
        except BaseException:
            work.rollback()
            raise

    # port v1.5 (ritual -- design R-6, no in-band actor by contract)
    def bootstrap(self) -> ControlCredentialHandle:
        # Real ceremony core (`control_plane.bootstrap_control_credential`)
        # against this adapter's own in-memory control-credential store --
        # the SAME product function `ops.py::cmd_bootstrap` calls against
        # PostgreSQL (R-6: "儀式意味論の正本は再利用可能な product code に
        # 置き...双方が同一コアを呼ぶ" -- this adapter never re-implements
        # ceremony logic of its own).
        def op() -> ControlCredentialHandle:
            with self._control_ritual_unit_of_work() as work:
                credential_id, secret = bootstrap_control_credential(
                    self._control_credentials, self._control_audit.append, work=work)
            return ControlCredentialHandle(credential_ref=credential_id, secret=secret)
        return self._call(op)

    # port v1.5 (ritual -- design R-6, no in-band actor by contract)
    def reset(self) -> ControlCredentialHandle:
        def op() -> ControlCredentialHandle:
            credential_id, secret = self._reset_control_credentials_now()
            return ControlCredentialHandle(credential_ref=credential_id, secret=secret)
        return self._call(op)

    def _reset_control_credentials_now(self) -> tuple[str, str]:
        """Runs the real reset ceremony to completion, resolving its own
        declare-and-echo gate (`control_plane.reset_control_credentials`
        recomputes and requires the CURRENT confirmation phrase, contract
        `destructive_confirmation`) via the same probe -> echo pattern this
        file's own `delete()`/batch-mutation methods already use for the
        application-plane's identical gate: a first attempt with no
        confirmation reads the real, currently-required phrase off the
        denial, then a second attempt echoes it back exactly."""
        def attempt(confirmation: str | None) -> tuple[str, str]:
            with self._control_ritual_unit_of_work() as work:
                return reset_control_credentials(
                    self._control_credentials, self._control_audit.append, work=work,
                    destructive=True, confirmation=confirmation,
                )
        try:
            return attempt(None)
        except DestructiveConfirmationRequired as exc:
            return attempt(exc.details["required_confirmation"])

    def _mint_or_repair_control_credential(self) -> None:
        """Ensures `self._control_credential_ref`/`_secret` name a
        currently-valid, must-rotate-cleared control credential (port v1.5
        `control_credential()`'s own obligation, WP-1 independent review
        major M-4: never a memoized value that might already be dead).
        First call bootstraps (or, if a control-credential row already
        exists -- some other test on this session-scoped adapter ran
        first -- resets, to obtain a handle this adapter itself actually
        knows the secret for). Every later call re-validates the tracked
        secret directly against the real store (never assumed still
        valid): C-15's own vectors deliberately revoke/reset control
        credentials mid-suite, and a call here after one of those must
        repair via a real `reset`, not keep handing out a now-dead handle.
        Either path finishes with a genuine self-rotate (`ControlPlane
        Service.rotate_credential`) to clear `must_rotate` -- never
        bypassed, exactly like a real operator completing the ritual
        would have to.
        """
        if self._control_credential_ref is not None:
            try:
                self._control_credentials.authenticate(self._control_credential_ref, self._control_credential_secret)
                return  # still live, and already rotated by a prior call to this method
            except FoundationError:
                pass  # revoked/disabled since last use -- repair via reset below
        if self._control_credentials.has_any(include_revoked=True):
            credential_id, secret = self._reset_control_credentials_now()
        else:
            with self._control_ritual_unit_of_work() as work:
                credential_id, secret = bootstrap_control_credential(
                    self._control_credentials, self._control_audit.append, work=work)
        rotated = self._control_service.rotate_credential(credential_id, secret, credential_id)
        self._control_credential_ref = credential_id
        self._control_credential_secret = rotated["secret"]

    # port v1.5 (privileged setup)
    def control_credential(self) -> ControlCredentialHandle:
        self._mint_or_repair_control_credential()
        return ControlCredentialHandle(credential_ref=self._control_credential_ref, secret=self._control_credential_secret)

    # port v1.5 (privileged observation)
    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        # Reads the DURABLE sink (`ControlAuditSink.snapshot()`) -- never
        # `AuditSink` (foundation's own 6-field, application-plane-only
        # trail), which is not the R-6 durable audit this port operation
        # observes.
        return [event.as_dict() for event in self._control_audit.snapshot()]

    # port v1.5 (fix-round): the inverse of `provision_application` --
    # operator-privileged test-harness cleanup, never a public capability
    # (there is no `deprovision`/`unregister` entry point anywhere on this
    # peer's own contract surface -- `application_deletion` is out of
    # scope for contract 1.2.0). Implemented via direct adapter-privileged
    # state removal, mirroring r2db-api's own identical WP-5 choice for the
    # structurally identical case.
    def deprovision_application(self, application_id: str) -> None:
        self._control.cells.pop(application_id, None)
        self._control.credentials.unregister_application(application_id)

    # ------------------------------------------------------------------
    # application plane
    # ------------------------------------------------------------------
    def authenticate(self, handle: CredentialHandle) -> object:
        return self._call(lambda: self._service.open_session(handle.credential_ref, handle.secret))

    def scope_of(self, session: object) -> ScopeView:
        principal = session.principal
        role_value = principal.role.value if isinstance(principal.role, Role) else principal.role
        return ScopeView(application_id=principal.application_id, role=role_value)

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        def op() -> None:
            if not hasattr(session, "create_collection"):
                # A runtime session genuinely has no schema-mutation method;
                # this is the same authority boundary the real developer
                # path enforces (cell.py _require_developer), spelled out
                # explicitly rather than relying on AttributeError.
                raise AuthorizationError("developer authority required")
            session.create_collection(entity, dict(fields))
        self._call(op)

    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None:
        self._call(lambda: session.insert(entity, dict(values)))

    def select_eq(self, session, entity: str, select: Sequence[str], field: str | None, value: Any) -> list[dict]:
        filters = [Filter(field, "eq", value)] if field is not None else None
        return self._call(lambda: session.read(entity, fields=list(select), filters=filters))

    def attempt_filter(
        self, session, entity: str, select: Sequence[str], field: str, operator: str, value: Any
    ) -> list[dict]:
        # Same real `session.read()` entry point `select_eq` above already
        # uses, generalized to an arbitrary operator -- an operator this
        # peer does not implement (`contains`/`matches`/`is_null`, all
        # declared `unsupported` in its own `structured_query` capability
        # entry) is presented here exactly as a real client attempting it
        # would be, and whatever `cell.py::_where` itself produces is
        # returned, never fabricated.
        filters = [Filter(field, operator, value)]
        return self._call(lambda: session.read(entity, fields=list(select), filters=filters))

    def delete(self, session, entity: str, field: str, value: Any, *, destructive: bool, confirmation: str | None) -> int:
        # VALID_CONFIRMATION sentinel protocol (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1, port v1.6
        # declare-and-echo), faithful pass-through mirroring both r2db-api
        # plugs' own `delete()` (`conformance_adapter_r2db.py`): `destructive`
        # always passes through exactly as given (WP-5 gave this peer's own
        # `session.delete()` a real `destructive` keyword -- prior to WP-5
        # this peer's deletion was unconditionally destructive with no such
        # parameter at all, so this flag had nothing to reach; it now does).
        # `confirmation=None` supplies no confirmation, `VALID_CONFIRMATION`
        # resolves to a real, currently-valid confirmation for this exact
        # request via `_resolve_confirmation` (declare-and-echo now that this
        # peer declares `contract_version >= 1.2.0`; `legacy_token=True`
        # remains this peer's own pre-1.2.0 fixed value, kept only as the
        # dead fallback `_resolve_confirmation` would take for a peer
        # declaring < 1.2.0 -- unreachable here post-flip, same as r2db-api
        # keeping its own literal "DELETE" legacy_token in place after its
        # WP-3 flip), and any other string passes through verbatim so a
        # wrong token is still observable as a wrong token to this peer's
        # own validation rather than silently upgraded.
        filters = [Filter(field, "eq", value)]

        def probe() -> None:
            self._call(lambda: session.delete(entity, filters, destructive=True))

        peer_confirm = self._resolve_confirmation(confirmation, probe=probe, legacy_token=True)

        def op() -> int:
            result = session.delete(entity, filters, destructive=destructive, confirm=peer_confirm)
            return result["deleted"]
        return self._call(op)

    def count(self, session, entity: str) -> int:
        # session.read() already re-checks authorization on every call
        # (cell.py ApplicationRuntime.__authorize -> assert_active), so a
        # revoked/disabled/unavailable session correctly denies here too.
        return self._call(lambda: len(session.read(entity)))

    def entities(self, session) -> set[str]:
        # There is no public "list collections" operation on this peer
        # (cell.py exposes create/insert/read/update/delete/transact only),
        # so this reaches into the cell's own storage handle for the actual
        # listing -- but only after an explicit assert_active() call, so a
        # revoked/disabled/unavailable session is denied here exactly as it
        # would be for any other session operation, instead of silently
        # reading internal state past the authorization boundary.
        def op() -> set[str]:
            principal = session.principal
            self._control.credentials.assert_active(principal)
            cell = self._control.cells.get(principal.application_id)
            if cell is None:
                return set()
            rows = cell._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            return {row["name"] for row in rows}
        return self._call(op)

    def catalog_document(self, session) -> str:
        # There is no public "list collections"/catalog operation anywhere
        # on this peer's surface (cell.py exposes create_collection/insert/
        # read/update/delete/transact only -- confirmed by source
        # inspection, and `capabilities()` itself declares
        # `application_catalog: unavailable`, cell.py's own comment: "No
        # public 'list collections' operation exists on this peer"). This
        # is a structural absence, not a denial this adapter observed from
        # a real call, so per the port's contract this returns the
        # sentinel rather than assembling a `CatalogDocument`-shaped dict
        # out of `entities()`'s own internal sqlite_master reach-around
        # (which exists only to serve this adapter's own `entities()`
        # port method, not as a peer-provided discovery surface an
        # application caller could reach).
        return CATALOG_SURFACE_ABSENT

    def _attempt_mutation_outcome(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None,
        unique_key: str | None,
    ) -> int:
        filters = [Filter(where_field, "eq", where_value)] if where_field is not None else None

        if expected_revision is not None or unique_key is not None:
            # Conformance-review finding (correction B-2): this is a real,
            # present entry point for a revision precondition (and, port
            # v1.3, for `unique_key`), not a structural absence.
            # `ApplicationRuntime.transact`/`ApplicationCell.transact`
            # already accepts an arbitrary operation-dict shape (exactly
            # what the `upsert` branch below relies on) -- so either extra
            # key is presented as a real field on that dict, exactly as a
            # real client attempting the contract's vocabulary would, and
            # this adapter returns whatever `transact()` itself produces.
            # An earlier revision of this method instead raised
            # `SurfaceAbsent` for `expected_revision` on the strength of
            # `session.insert`/`.update`/`.delete` alone having no such
            # parameter -- but `transact()` is a real, present dispatcher
            # those three dedicated methods do not exhaust, and (before
            # `cell.py` was fixed) it silently ignored this exact key on an
            # "insert" operation, committing the row with the precondition
            # never even inspected. That was the real non-conformance C-18
            # exists to catch; declaring it `SurfaceAbsent` would have
            # hidden it behind a fabricated claim of absence, which design
            # principle 4 forbids as surely as fabricating a denial does.
            # This peer has no uniqueness-key concept at all, so a real
            # `unique_key` value here is expected to be refused (there is
            # no declared key it could ever name) -- but that refusal must
            # still come from presenting it to this real dispatcher, not
            # from this adapter deciding the answer itself.
            item: dict[str, Any] = {"type": operation, "collection": entity, "values": dict(values or {})}
            if expected_revision is not None:
                item["expected_revision"] = expected_revision
            if unique_key is not None:
                item["unique_key"] = unique_key
            if filters is not None:
                item["filters"] = filters

            def dispatched_op() -> int:
                results = session.transact([item])
                return len(results)
            return self._call(dispatched_op)

        if operation == "insert":
            def insert_op() -> int:
                session.insert(entity, dict(values or {}))
                return 1
            return self._call(insert_op)

        if operation == "update":
            def update_op() -> int:
                if filters is None:
                    raise ValidationError("update requires a non-empty filter")
                result = session.update(entity, dict(values or {}), filters)
                return result["updated"]
            return self._call(update_op)

        if operation == "delete":
            # This generic dispatcher (used by C-17/C-18 for delete
            # attempts that are not themselves testing confirmation
            # semantics -- C-12 deliberately excludes delete from its own
            # `_EXERCISED_OPERATIONS`, "delete is left to C-06") must still
            # present a genuinely valid confirmation to this peer's own
            # real `session.delete()` post-WP-5, the same probe -> echo
            # round trip `delete()` above performs, rather than a bare
            # `confirm=True` (invalid now that `confirm` is a str -- WP-5
            # R-5 -- not this peer's former bool).
            def delete_op() -> int:
                if filters is None:
                    raise ValidationError("delete requires a non-empty filter")

                def probe() -> None:
                    self._call(lambda: session.delete(entity, filters, destructive=True))

                peer_confirm = self._resolve_confirmation(VALID_CONFIRMATION, probe=probe, legacy_token=True)
                result = session.delete(entity, filters, destructive=True, confirm=peer_confirm)
                return result["deleted"]
            return self._call(delete_op)

        if operation == "upsert":
            # There is no dedicated `upsert` method anywhere on this peer,
            # but `ApplicationRuntime.transact`/`ApplicationCell.transact`
            # *is* a real, present operation dispatcher that accepts an
            # arbitrary `"type"` string -- so this presents `"upsert"` to
            # it exactly as a real client attempting the contract's
            # `upsert` vocabulary would (review finding: an adapter that
            # denies this without ever presenting it to the peer hides
            # whatever the peer's own dispatcher actually does with it,
            # which is precisely what C-12 exists to observe. See `cell.
            # py::transact` / `errors.CapabilityError` for this peer's own
            # real answer).
            def upsert_op() -> int:
                results = session.transact([
                    {"type": "upsert", "collection": entity, "values": dict(values or {})}
                ])
                return len(results)
            return self._call(upsert_op)

        # Any other operation name is outside the common contract's
        # mutation vocabulary entirely (insert/update/upsert/delete);
        # there is no peer call this adapter could present it to that
        # would mean anything.
        raise ConformanceDenial(code="CAPABILITY_UNSUPPORTED", adapter=self.name, native_type="")

    def attempt_mutation(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> int:
        return self._attempt_mutation_outcome(
            session, entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )

    def attempt_mutation_with_addresses(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        affected = self._attempt_mutation_outcome(
            session, entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        # None, always: none of `session.insert`/`.update`/`.delete`/
        # `.transact`'s real return shapes (`{"rowid": ...}`, `{"updated":
        # ...}`, `{"deleted": ...}`, a results list) carry anything shaped
        # like the contract's `assigned_addresses` -- consistent with this
        # peer declaring `row_addressability: unavailable`. `insert()`'s
        # own `rowid` is a SQLite-internal artifact, not a published
        # address; synthesizing `[{"address": {"rowid": ...}}]` from it
        # would be this adapter fabricating an addressability concept the
        # peer itself does not declare or publish to a real caller.
        return affected, None

    def attempt_batch_with_addresses(
        self, session, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        # `ApplicationRuntime.transact`/`ApplicationCell.transact` is the
        # *only* real multi-operation atomic dispatcher this peer has --
        # there is no other call that could receive more than one operation
        # at once -- so every operation in the batch is presented to it
        # together, in one real call, exactly as `_attempt_mutation_
        # outcome`'s own `expected_revision`/`unique_key` branch already
        # does for a single operation.
        #
        # P3-D2 (design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
        # R-5, WP-1.5): before this WP, `transact()` only ever truly
        # executed an `"insert"` item -- every other type in the same
        # vocabulary (`update`/`delete`/`upsert`) was refused with
        # `CapabilityError` regardless of what else was in the batch, so a
        # real mixed batch (insert alongside update/delete) was genuinely
        # refused here. As of WP-1.5, `insert`/`update`/`delete` all
        # execute for real, atomically, converging real behavior onto the
        # existing `atomic_mutation.operations` declaration (unchanged by
        # this WP -- no capability-envelope expansion); a batch-embedded
        # `delete` goes through the identical declare-and-echo
        # confirmation choke the dedicated `delete()` method above uses.
        # `upsert` alone remains a real capability gap (`CapabilityError`),
        # unaffected by this WP -- no execution path for it exists
        # anywhere on this peer, batched or not. A real mixed batch is
        # therefore genuinely executed here now, never silently split into
        # several single-operation calls this adapter stitches together
        # itself, which would prove nothing real about this peer's own
        # batch-mixing support either way.
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"type": op.operation, "collection": entity, "values": dict(op.values or {})}
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            if op.where_field is not None:
                item["filters"] = [Filter(op.where_field, "eq", op.where_value)]
            if op.destructive:
                item["destructive"] = True
            # V2b-wire (C-06, WP-5 review recommendation already realized
            # by both r2db-api plugs in WP-3): `confirmation` is set
            # whenever the caller supplies one, INDEPENDENT of `destructive`
            # -- an earlier revision of this method only ever set it
            # inside the `if op.destructive:` branch above, which made it
            # impossible to construct a request whose wire OMITS
            # `destructive` entirely (not merely `false`) while still
            # carrying a real, currently-valid `confirmation` phrase for
            # the identical request, exactly the literal wire-omission
            # shape contract `valid_confirmation`'s "a missing destructive
            # field is equivalent to false, never to true" rule requires
            # this peer to still deny.
            if op.confirmation is not None:
                if op.confirmation is VALID_CONFIRMATION:
                    # Same VALID_CONFIRMATION sentinel protocol as
                    # `delete()` above (port v1.6 declare-and-echo),
                    # extended to batch operations (port v1.4). The probe
                    # always presents `destructive: True` regardless of
                    # this call's own `destructive` argument -- a probe
                    # must reliably trigger the peer's own denial to read
                    # the real phrase back, independent of whether the
                    # OUTER request under construction carries
                    # `destructive: True` or omits it.
                    probe_item = dict(item)
                    probe_item["destructive"] = True

                    def probe(_probe_item=probe_item) -> None:
                        self._call(lambda: session.transact([dict(_probe_item)]))

                    peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token=True)
                    item["confirm"] = peer_confirm
                else:
                    item["confirm"] = op.confirmation
            items.append(item)

        def op() -> int:
            results = session.transact(items)
            return len(results)
        affected = self._call(op)
        return affected, None

    def create_unique_index(self, session, entity: str, index: str, fields: Sequence[str]) -> None:
        # `session` is unavailable-regardless of *any* session (the answer
        # is peer-wide, not session-scoped), kept only to match this ABC
        # method's signature -- the same convention `catalog_document`
        # above already follows for its own unused `session` parameter.
        # `entity`/`index`/`fields` are named in the raised exception's
        # `reason` immediately below rather than left unused: a caller
        # debugging why a *specific* index attempt reported "absent" can
        # see what was actually asked for, not just that something was.
        #
        # `ApplicationDeveloper`'s schema-mutation calls -- `create_
        # collection`, and (P3-D1, WP-1) `create_entity`/`add_field` -- have
        # no parameter for indexes of any kind -- unlike `r2db-api`'s single
        # generic `schema()` dispatcher, there is no entry point on this
        # peer's public surface (confirmed by source inspection of cell.py:
        # no other developer-facing method exists either) that could even
        # receive an index-creation request. Structurally absent, not
        # denied -- see `SurfaceAbsent`'s docstring for why this must not
        # become a fabricated `ConformanceDenial` instead.
        raise SurfaceAbsent(
            self.name, "create_unique_index",
            "ApplicationDeveloper's schema-mutation calls (create_collection/create_entity/add_field) have "
            "no index/uniqueness parameter, and no other schema-operation call exists on this peer "
            f"(requested: entity={entity!r}, index={index!r}, fields={list(fields)!r})",
            # This peer's entire public application-facing surface (the
            # same list `public_operation_callables()` below declares for
            # C-03's native-command-surface check), so a consumer can
            # independently verify -- via `signature_forbids_parameters` --
            # that none of it accepts an index/uniqueness-shaped parameter,
            # rather than take this claim on its word (design section 4.3 /
            # `SurfaceAbsent`'s own docstring).
            surface=self.public_operation_callables(),
            forbidden_parameters=["index", "unique"],
        )

    def drop_entity(self, session, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        # port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
        # item 3): same structural-absence reasoning as `create_unique_
        # index` immediately above -- `ApplicationDeveloper`'s
        # schema-mutation calls (`create_collection`, and, P3-D1/WP-1,
        # `create_entity`/`add_field`) have no drop/destroy parameter of any
        # kind. No other developer-facing method exists on this peer's
        # public surface (confirmed by source inspection of cell.py) that
        # could even receive a destructive drop request, so this is a
        # structural absence, not a denial this adapter observed from a
        # real call -- exactly the honest form `SurfaceAbsent`'s own
        # docstring requires, not a fabricated `ConformanceDenial`.
        # `destructive`/`confirmation` are accepted only to match this ABC
        # method's signature (the same convention `create_unique_index`
        # above follows for its own unused `session` parameter) -- there is
        # no real entry point to pass them through to.
        raise SurfaceAbsent(
            self.name, "drop_entity",
            "ApplicationDeveloper's schema-mutation calls (create_collection/create_entity/add_field) have "
            "no drop/destroy parameter, and no other schema-operation call exists on this peer "
            f"(requested: entity={entity!r})",
            surface=self.public_operation_callables(),
            forbidden_parameters=["drop", "destroy"],
        )

    def query_with_revisions(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        # `ApplicationCell.read()`'s own return type is a bare
        # `[dict(row) for row in rows]` list, not a wrapping object -- so
        # `None` here observes that real return shape having structurally
        # no slot a `revisions` key could ever occupy, the same reasoning
        # as `conformance_adapter_r2db.py`'s identical comment (contrast
        # `conformance_adapter_r2db_http.py`, whose response *is* a JSON
        # object and which inspects a real `result.get("revisions")`
        # instead of asserting `None` unlooked-at -- conformance-review
        # correction M-1).
        items = self.select_eq(session, entity, select, field, value)
        return items, None

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------
    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        # The genuine application-facing surface: everything an
        # authenticated application credential can reach. ControlPlane is
        # deliberately excluded; a session object has no reference to it.
        #
        # WP-2.5 review M-1: this list is the evidence surface every
        # independent absence claim on this peer checks against
        # (`signature_forbids_parameters` for C-03's native-command-surface
        # check and every `SurfaceAbsent` re-verification; `declared_
        # surface >= public_surface_set` for C-11/C-14/C-15's own re-
        # verification of this adapter's `SurfaceAbsent` claims). It had
        # drifted out of sync with `ApplicationRuntime`/`ApplicationDeveloper`'s
        # own real public methods -- missing `capabilities` (always public,
        # pre-existing) and `create_entity`/`add_field` (P3-D1, WP-1,
        # missed at the time) -- which meant those downstream checks were
        # silently inspecting less than this peer's actual public surface.
        # `MitateDB-api/tests/test_conformance_public_surface_coverage.py`
        # now pins this list to match those two classes' own real,
        # non-underscore, plain-function members mechanically, so a future
        # method addition here without a matching list update fails that
        # test immediately.
        return [
            _MitateDataServiceClass.open_session,
            ApplicationRuntime.insert,
            ApplicationRuntime.read,
            ApplicationRuntime.update,
            ApplicationRuntime.delete,
            ApplicationRuntime.transact,
            ApplicationRuntime.capabilities,
            # m-2 (independent WP-3 review): `schema_revision()`, added so
            # the HTTP surface's `SchemaOperationResult.revision` can
            # report a real, observable value instead of a hardcoded
            # placeholder.
            ApplicationRuntime.schema_revision,
            ApplicationDeveloper.create_collection,
            ApplicationDeveloper.create_entity,
            ApplicationDeveloper.add_field,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        runtime_a = fixture.runtime_a

        def forged_scope_attempt() -> None:
            # Reach the target application's cell directly and construct a
            # runtime bound to a forged Principal: same (real) credential
            # id, application_id renamed to the other application. This is
            # exactly the guidance for this peer in the task brief, since
            # Principal (unlike r2db's AuthContext) is never itself handed
            # to a public method as a request argument.
            principal = runtime_a.principal
            forged_principal = replace(principal, application_id=fixture.app_b)
            target_cell = self._control.cells[fixture.app_b]

            def op() -> None:
                forged_runtime = ApplicationRuntime(target_cell, forged_principal, self._control.credentials.assert_active)
                forged_runtime.read(fixture.shared_entity)
            self._call(op)

        def role_elevation_attempt() -> None:
            # Same real runtime credential id, role self-declared as
            # developer.
            principal = runtime_a.principal
            forged_principal = replace(principal, role=Role.DEVELOPER)
            own_cell = self._control.cells[fixture.app_a]

            def op() -> None:
                forged_developer = ApplicationDeveloper(own_cell, forged_principal, self._control.credentials.assert_active)
                forged_developer.create_collection("conf_role_elevation_probe", {"id": "integer"})
            self._call(op)

        def request_field_scope_attempt() -> None:
            # A legitimate, untampered session, but the request body itself
            # carries a smuggled scope-looking field. Unknown-field
            # validation rejects it the same way it would reject any other
            # bogus column name.
            self._call(lambda: runtime_a.insert(fixture.shared_entity, {"probe_value": "x", "application_id": fixture.app_b}))

        def cross_application_handle_attempt() -> None:
            # A legitimate, untampered session for A reaching straight for
            # a collection that only exists in B's cell.
            self._call(lambda: runtime_a.read(fixture.b_only_entity))

        return [
            TamperVector(
                kind="forged_scope_object",
                name="mitatedb_forged_principal_application_id",
                disposition="must_deny",
                attempt=forged_scope_attempt,
            ),
            TamperVector(
                kind="role_elevation",
                name="mitatedb_forged_principal_developer_role",
                disposition="must_deny",
                attempt=role_elevation_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="mitatedb_smuggled_application_id_in_insert_values",
                disposition="must_deny",
                attempt=request_field_scope_attempt,
            ),
            TamperVector(
                kind="cross_application_handle",
                name="mitatedb_runtime_a_reaches_b_only_collection",
                disposition="must_deny",
                attempt=cross_application_handle_attempt,
            ),
        ]

    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        # WP-5 flip (design v1.2 R-8 second-round M-4): the prior
        # `structurally_absent` vector's own premise ("no reactivation call
        # exists on this peer at all") became false the instant
        # `enable_credential` was wired through to a real, in-band
        # control-plane operation (`set_credential_enabled_inband` ->
        # `ControlPlaneService.set_credential_enabled` -> THIS SAME `auth.
        # CredentialStore`, 2ストア突合) -- so it is rewritten here to the
        # real `must_deny` vector the design's own R-8 citation calls for:
        # revoke -> in-band enable(True) -> re-authenticate denied.
        def enable_application_after_revoke_attempt() -> None:
            # `enable_application` only ever flips the *application*-level
            # flag (`_applications[...]`); it never touches a credential's
            # own state at all, so this call itself never raises -- a real,
            # no-op-for-this-purpose control-plane call, not a denied one.
            # `must_ignore` is the correct disposition: C-13's own
            # must_ignore handling re-authenticates afterward and asserts
            # the credential is still refused, which is the actual proof
            # this attempt did not reactivate anything.
            self._control.credentials.enable_application(handle.application_id)

        def inband_enable_credential_after_revoke_then_reauthenticate_denied_attempt() -> None:
            # `enable_credential` itself is NOT refused (contract `enable_
            # credential.semantics`: "Reverses disable only" -- the call
            # succeeds, `revoked` stays untouched) -- the proof this is a
            # real `must_deny` vector, not a disguised `must_ignore` one,
            # is that the SAME `attempt()` chains a real re-authenticate of
            # `handle` afterward: `self.authenticate` raises via `_call`
            # exactly like every other denial this file already surfaces,
            # so a genuinely non-reactivating peer makes `attempt()` itself
            # raise `ConformanceDenial` -- `must_deny`'s own contract.
            control_actor = self.control_credential()
            self._call(lambda: self._control_service.set_credential_enabled(
                control_actor.credential_ref, control_actor.secret, handle.credential_ref, True))
            self.authenticate(handle)

        return [
            TamperVector(
                kind="credential_reactivation",
                name="mitatedb_enable_application_does_not_reactivate_revoked_credential",
                disposition="must_ignore",
                attempt=enable_application_after_revoke_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="mitatedb_inband_enable_credential_after_revoke_then_reauthenticate_denied",
                disposition="must_deny",
                attempt=inband_enable_credential_after_revoke_then_reauthenticate_denied_attempt,
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        developer_a = fixture.developer_a

        def entity_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(payload))

        def select_field_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(fixture.shared_entity, fields=[payload]))

        def filter_field_probe(payload: Any) -> Any:
            return self._call(lambda: runtime_a.read(fixture.shared_entity, filters=[Filter(payload, "eq", 1)]))

        def _require_hashable(position: str, payload: Any) -> None:
            # An unhashable NON_STRING payload (e.g. [], {}) cannot even be
            # placed at a mapping-key position -- the request can't be
            # constructed, so this is a harness-level impossibility, not an
            # observation of this peer's validation (design section 10.3).
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    position, payload, "payload is unhashable and this position is a mapping key"
                ) from exc

        def insert_field_probe(payload: Any) -> Any:
            _require_hashable("insert_field", payload)
            return self._call(lambda: runtime_a.insert(fixture.shared_entity, {payload: "x"}))

        def schema_entity_probe(payload: Any) -> Any:
            return self._call(lambda: developer_a.create_collection(payload, {"id": "integer"}))

        def schema_field_probe(payload: Any) -> Any:
            _require_hashable("schema_field", payload)
            name = "conf_schema_field_probe_" + uuid.uuid4().hex[:8]
            return self._call(lambda: developer_a.create_collection(name, {payload: "text"}))

        return {
            "entity": entity_probe,
            "select_field": select_field_probe,
            "filter_field": filter_field_probe,
            "insert_field": insert_field_probe,
            "schema_entity": schema_entity_probe,
            "schema_field": schema_field_probe,
        }

    def value_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        # Round-tripping a value payload means genuinely writing a row into
        # shared_entity itself. That is intentional: C-03's structural
        # integrity check (design section 5.2 item 5) only requires the
        # *identifier* corpus to leave shared_entity's row count untouched;
        # the value corpus is expected to grow it as proof of a successful,
        # safely-bound write (only the entity *set* must stay stable across
        # the value corpus too).
        runtime_a = fixture.runtime_a
        entity = fixture.shared_entity

        def insert_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = "probe-" + uuid.uuid4().hex
                runtime_a.insert(entity, {"probe_key": marker, "probe_value": payload})
                rows = runtime_a.read(entity, fields=["probe_value"], filters=[Filter("probe_key", "eq", marker)])
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        def filter_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = "probe-" + uuid.uuid4().hex
                runtime_a.insert(entity, {"probe_key": marker, "probe_value": payload})
                rows = runtime_a.read(entity, fields=["probe_value"], filters=[
                    Filter("probe_key", "eq", marker),
                    Filter("probe_value", "eq", payload),
                ])
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        return {
            "insert_value": insert_value_probe,
            "filter_value": filter_value_probe,
        }

    # ------------------------------------------------------------------
    # normalization
    # ------------------------------------------------------------------
    def classify(self, exc: BaseException) -> str:
        # Only this peer's own declared error base class (FoundationError,
        # via the type-ordered table above) is converted to a contract
        # code. Anything else -- e.g. a raw sqlite3.Error that escaped this
        # peer's FoundationError boundary -- is not a denial this adapter
        # can vouch for; laundering it into VALIDATION_FAILED would hide a
        # peer crash (or an unclassified defect) behind a passing test
        # (design section 10.2). Report it as unclassified instead.
        if isinstance(exc, FoundationError):
            for exc_type, code in _CLASSIFY_ORDER:
                if isinstance(exc, exc_type):
                    return code
        return UNCLASSIFIED

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def build_fixture(self) -> Fixture:
        # conftest.py's `adapter` fixture is session-scoped but `fx` (which
        # calls this method) is function-scoped, so build_fixture() runs
        # once per test function against the same long-lived adapter
        # instance. Application ids must therefore be fresh on every call,
        # not fixed literals, or the second call's provision_application()
        # raises "application already provisioned". Identifiers stay
        # lowercase per this peer's stricter catalog policy.
        self._counter += 1
        suffix = f"{self._counter}_{uuid.uuid4().hex[:8]}"
        app_a, app_b = f"conf_app_a_{suffix}", f"conf_app_b_{suffix}"
        self.provision_application(app_a)
        self.provision_application(app_b)

        # `item_key`, not `id`: the common fixture must not use `id` as an
        # ordinary field name (port v1.2 coordinated revision, docs/design/
        # CONFORMANCE_ADAPTER_V1.md section 12 / docs/design/
        # R2DB_CCR13_STORAGE_V1.md R-3) -- `r2db-api` reserves it as its
        # server-assigned address column. `MitateDB-api` itself does not
        # reserve `id` (this peer's own throwaway probe entities elsewhere
        # in this file may still use it freely), but the *shared* fixture
        # entities below must use a name safe on every registered peer.
        fields = {"item_key": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
        shared_entity = "shared_items"
        a_only_entity = "a_only_items"
        b_only_entity = "b_only_items"

        dev_a_handle = self.issue_credential(app_a, "developer")
        dev_b_handle = self.issue_credential(app_b, "developer")
        developer_a = self.authenticate(dev_a_handle)
        developer_b = self.authenticate(dev_b_handle)

        self.create_entity(developer_a, shared_entity, fields)
        self.create_entity(developer_a, a_only_entity, fields)
        self.create_entity(developer_b, shared_entity, fields)
        self.create_entity(developer_b, b_only_entity, fields)

        self.insert(developer_a, shared_entity, {"item_key": 1, "label": "seed-a", "probe_key": "seed", "probe_value": "seed-a"})
        self.insert(developer_b, shared_entity, {"item_key": 1, "label": "seed-b", "probe_key": "seed", "probe_value": "seed-b"})
        self.insert(developer_a, a_only_entity, {"item_key": 1, "label": "a-only", "probe_key": "seed", "probe_value": "a-only"})
        self.insert(developer_b, b_only_entity, {"item_key": 1, "label": "b-only", "probe_key": "seed", "probe_value": "b-only"})

        runtime_a_handle = self.issue_credential(app_a, "runtime")
        runtime_b_handle = self.issue_credential(app_b, "runtime")
        runtime_a = self.authenticate(runtime_a_handle)
        runtime_b = self.authenticate(runtime_b_handle)

        return Fixture(
            adapter=self,
            app_a=app_a,
            app_b=app_b,
            runtime_a=runtime_a,
            developer_a=developer_a,
            runtime_b=runtime_b,
            shared_entity=shared_entity,
            a_only_entity=a_only_entity,
            b_only_entity=b_only_entity,
        )

    def close(self) -> None:
        # In-memory sqlite (":memory:") per cell; nothing external to
        # release, and each build_adapter() call gets a fresh ControlPlane.
        pass

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except FoundationError as exc:
            raise self._deny(exc) from exc
        except (TypeError, ValueError, sqlite3.Error) as exc:
            # TypeError/ValueError: malformed structural input at the
            # Python level (e.g. an unhashable field-name payload).
            # sqlite3.Error: this peer's storage driver rejects some
            # malformed values (e.g. an embedded NUL byte) below the
            # FoundationError boundary; cell.py only translates
            # sqlite3.IntegrityError/DatabaseError, not the full driver
            # hierarchy, so this adapter must still classify it rather than
            # let it leak past the port as a raw driver exception.
            raise self._deny(exc) from exc

    def _deny(self, exc: BaseException) -> ConformanceDenial:
        # port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
        # item 2). mi-3 correction (independent review): this comment used
        # to say this peer's `FoundationError` hierarchy had no `details`
        # attribute at all -- true before WP-5, false since. WP-5 gave
        # `errors.ResourceLimitError` (`limit_class`) and the new
        # `errors.DestructiveConfirmationRequired` (the contract's 4
        # declared keys) a real `details` dict each. `getattr(exc,
        # "details", None)` is this adapter's ONLY wiring for surfacing
        # either onto `ConformanceDenial.details` -- there is no other call
        # site translating them -- so this line is the real, load-bearing
        # bridge C-06's `_assert_four_declarations`/`assert_no_payload_
        # echo_in_details` and the limit-class behavioral tests all
        # ultimately depend on, not a forward-looking no-op. Every OTHER
        # `FoundationError` subclass still has no `details` attribute, so
        # `getattr` still falls through to `None` (-> an empty mapping) for
        # those, exactly as before.
        return ConformanceDenial(
            code=self.classify(exc), adapter=self.name, native_type=type(exc).__name__,
            details=getattr(exc, "details", None),
        )


def build_adapter() -> ConformanceAdapter:
    return MitateDBConformanceAdapter()
