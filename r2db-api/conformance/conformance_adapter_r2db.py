"""r2db-api plug for the common conformance port.

Module name matters here: `conformance-tests/registry.json` declares this
peer's module as `conformance_adapter_r2db`, and
`conformance-tests/conftest.py` discovers it by adding this file's
directory to `sys.path` and calling
`importlib.import_module("conformance_adapter_r2db")` -- a plain name
lookup, not a path load -- so this file must keep this exact basename.

This module owns the connection between the common port
(`conformance-tests/adapter.py`, importable as top-level module `adapter`,
NORMATIVE per docs/design/CONFORMANCE_ADAPTER_V1.md section 4) and this
peer's own foundation. It does not redefine or reinterpret the port's value
types or ABC signatures; it only implements them against `r2db_api`.

Synthetic values only: application ids, credential ids and secrets used
here are conformance-suite fixtures, never real deployment values (CLAUDE.md
Public Repository Security Gate).
"""
from __future__ import annotations

import os
import sys
import uuid
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
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ControlCredentialHandle,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopedBatchOperation,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    resolve_valid_confirmation,
)

from r2db_api import ControlAuthority, CredentialStore, DataService  # noqa: E402
from r2db_api.audit import ControlAuditSink  # noqa: E402
from r2db_api.audit_query import InMemoryAuditQueryStore  # noqa: E402
from r2db_api.auth import ControlCredentialStore  # noqa: E402
from r2db_api.control_plane import (  # noqa: E402
    ControlPlaneService,
    InMemoryControlBackend,
    bootstrap_control_credential,
    reset_control_credentials,
)
from r2db_api.errors import FoundationError  # noqa: E402
from r2db_api.limits import ControlPlaneLimits  # noqa: E402


# port v1.3 (WP-5a, design docs/design/R2DB_CCR13_STORAGE_V1.md M-8
# activation): the port's own two-member field-type vocabulary
# (`adapter.COMMON_FIELD_TYPES`, `"text"`/`"integer"`) is deliberately not
# spelled the same as the common contract's own `field_type` enum
# (`spec/data-service-api.v1.json`: `string`/`integer`/`number`/`boolean`/
# `object`/`array`) -- the port's vocabulary exists to name the two types
# every registered peer can plausibly support at all, independent of how
# each peer's own real schema surface spells them. This is the explicit
# mapping from the port's vocabulary to this peer's real `add_field`
# `field_type` parameter.
_PORT_FIELD_TYPE_TO_R2DB = {"text": "string", "integer": "integer"}


class R2DBConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to the r2db-api foundation.

    A "session" for this peer is an `AuthContext`. Control-plane operations
    go through `ControlAuthority`, which is never reachable from the
    application-facing `DataService` surface (see r2db_api.topology).
    """

    name = "r2db-api"

    def __init__(self) -> None:
        # Synthetic pepper for this conformance run only; never a real
        # deployment secret and never read from the environment.
        self._credentials = CredentialStore(pepper="synthetic-conformance-pepper-r2db-0000")
        # CCR-14 WP-5 (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
        # §4's adapter x phase table): `control_plane: enabled` -- this
        # adapter now takes the "provided" branch of C-14/C-15. The
        # declaration is a real constructor injection (R-9), not a value
        # this adapter fabricates only in `capability_document()` -- see
        # `service.py`'s own `DataService.__init__` docstring for why this
        # is the one honest way to make that declaration.
        self._service = DataService(self._credentials, control_plane_status="enabled")
        self._control = ControlAuthority(self._service)
        self._counter = 0

        # ------------------------------------------------------------
        # control plane (WP-5 provided branch): `ControlPlaneService` +
        # `InMemoryControlBackend`, constructed directly on top of this
        # same `DataService`/`ControlAuthority`/`CredentialStore` (design
        # §3 architecture: in-band operations on this port are service-
        # method direct calls, never a second, adapter-invented
        # implementation of what "register an application" means -- work
        # order §3 "ControlPlaneService...をadapterの既存DataService/
        # ControlAuthority/ストア上に構成し...service メソッド直呼び").
        # Limits: design §5's WP-5 handoff (§12.5/§13.3) suggests
        # `applications=20` as an EXAMPLE conformance-build value, headroom-
        # checked only against C-14 vector 5's own arithmetic (rate >
        # applications-drive + credentials-drive + 64). It did not account
        # for `applications_count()` reading THIS adapter's own shared
        # `DataService._cells` (design's own prescribed WP-3 architecture,
        # `InMemoryControlBackend`'s docstring: "in-memory側はControlAuthority
        # /DataServiceの既存状態に整合する形") on a SESSION-scoped adapter
        # instance shared across every OTHER condition test's own
        # `build_fixture()` calls (every test function registers 2 more
        # Applications via the shared out-of-band `provision_application`
        # setup primitive -- C14 vector 5's own `n_existing < apps_limit`
        # precondition measures this real, non-zero baseline directly, it
        # does not assume a zero-application start). Measured empirically
        # (WP-5 round-2 independent review, instrumented against the real
        # `conformance-tests/` run): `n_existing` is **80** on BOTH r2db-api
        # adapters (in-process and http) by the time C-14 vector 5 itself
        # reads it, and **89** by the end of the whole session (later
        # conditions, e.g. C-17/C-18, add more registered-only fixture
        # churn afterward without ever driving this bound). `applications=20`
        # would make `n_existing < apps_limit` false before vector 5 even
        # starts driving anything -- not a vector weakening (the vector's
        # own position-exact-refusal assertion is unchanged), a conformance-
        # build parameter raised to fit this adapter's real, measured
        # fixture churn, same category of adjustment the work order
        # explicitly permits for the rate class (§4: "rate と
        # _MAX_EXERCISABLE_LIMIT の引き上げで対処してよい"). `100` left a
        # margin of 20 over the measured `n_existing=80` at vector 5 itself
        # (11 by session end) while keeping the rate-headroom arithmetic
        # satisfiable under the port's own <=200 hard cap
        # (100 + 2 + (2*5+1) + 64 = 177 < 200).
        #
        # Phase 3.5 WP-3 (docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_
        # 130_V1.md §3): `100` stopped being enough --
        # `test_c15_lifecycle_changes_emit_canonical_audit_and_denials_
        # are_recorded` started failing with a genuine in-band
        # LIMIT_EXCEEDED. CORRECTED causal analysis (independent review
        # m-6; the first-pass comment here over-attributed this to
        # `test_c16_cross_entity_atomicity.py`, which is WRONG): pytest
        # collects test files in the order listed in `conftest.py`'s own
        # discovery / alphabetically by module, so `test_c16_...` and
        # `test_c17_...` etc. run STRICTLY AFTER `test_c14_authority_
        # boundary.py`/`test_c15_bootstrap_reset_lifecycle.py` -- C-16's own
        # `fx`-driven `provision_application` churn had not happened yet at
        # the point this failure occurred and did not cause it. The actual
        # binding event, measured directly: `test_c12_capability_
        # agreement.py`'s own new cross_entity_mutation test (`test_c12_...`
        # runs BEFORE `test_c14_...`/`test_c15_...`) adds `+2` applications
        # via its own `fx` fixture, pushing `n_existing` to `99` by the time
        # `test_c15_lifecycle_changes_emit_canonical_audit_and_denials_
        # are_recorded` starts; that test's OWN `fx` fixture then adds `+2`
        # more, landing at `101` -- one past `100` -- exactly at its own
        # in-band `register_application_inband` call. The minimum bump that
        # would have been SUFFICIENT was therefore `~102`, not the larger
        # jump this comment originally reasoned toward from an inflated
        # "roughly a dozen" estimate. `115` was chosen anyway for headroom
        # against ordinary future suite growth (`115 + 2 + (2*5+1) + 64 =
        # 192 < 200`, still safely under the rate-headroom ceiling), but
        # leaves only a 7-unit margin under this class's own hard ceiling
        # (`apps_limit <= 122`, the largest value that inequality can ever
        # satisfy at `rate_limit=200`/`credentials_per_application=5`/
        # `margin=64` -- `rate_limit` is already at the port's own
        # `_MAX_EXERCISABLE_LIMIT`, so it cannot be raised further to buy
        # more room here). The correct fix once that 7-unit margin is
        # exhausted is NOT another bump (there are only 7 left before the
        # ceiling) -- it is giving the fixture/application churn itself a
        # teardown path (deprovisioning throwaway `build_fixture()`
        # Applications the way `deprovision_application` already lets
        # vector 5 clean up its own), tracked as future work in the design
        # ledger (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`
        # §7), not attempted in this WP.
        # ------------------------------------------------------------
        self._control_credentials = ControlCredentialStore(pepper="synthetic-conformance-pepper-r2db-ctl-0000")
        self._control_backend = InMemoryControlBackend(self._control, self._control_credentials)
        self._control_audit = ControlAuditSink()
        # Phase 4 WP-2(b) (design D-5): `audit_requests_per_minute`
        # generously headroomed too (same reasoning as `control_requests_
        # per_minute` above) -- C-09's own vectors call `audit_query` a
        # handful of times per test, but this is a SESSION-scoped adapter
        # shared across the whole conformance run.
        self._control_limits = ControlPlaneLimits(applications=115, credentials_per_application=5, control_requests_per_minute=200, audit_requests_per_minute=200)
        # Phase 4 WP-2(b) (design D-5/D-6, D-10): the in-process `audit_
        # query` reader -- UNIONs THIS SAME `self._control_audit` (control
        # plane) and `self._service`'s own in-memory `application_audit`
        # half (`DataService.__init__`'s default `ApplicationAuditSink()`,
        # reached the same `# noqa: SLF001` way `InMemoryControlBackend`
        # itself already reaches into `DataService` private state). Real
        # writes go through this exact `DataService`/`ControlPlaneService`
        # pair -- there is no separate "conformance-only" audit path.
        # `visibility_lag_ms=0`: in-memory writes are synchronous, so there
        # is no real transaction-lag hazard to model (`audit_query.py`'s
        # own module docstring).
        self._audit_reader = InMemoryAuditQueryStore(self._control_audit, self._service._durable_audit)  # noqa: SLF001
        self._control_service = ControlPlaneService(
            self._control_backend, audit=self._control_audit, limits=self._control_limits,
            audit_reader=self._audit_reader, audit_visibility_lag_ms=0,
        )
        # `control_credential()`'s own maintained handle (memoize +
        # call-time validity check -- see that method's docstring below;
        # WP-1 M-4's "never memoized, must be valid AT CALL TIME"
        # obligation).
        self._control_credential_ref: str | None = None
        self._control_credential_secret: str | None = None
        # port v1.6 declare-and-echo (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): this peer's own
        # declared `contract_version` is static for the lifetime of this
        # adapter instance (it never changes at runtime), so it is safe to
        # cache after the first real `capability_document()` call rather
        # than provisioning a fresh disposable Application on every single
        # destructive-operation call site that needs it.
        self._contract_version_cache: str | None = None

    # ------------------------------------------------------------------
    # control plane
    # ------------------------------------------------------------------
    def provision_application(self, application_id: str) -> None:
        self._control.register_application(application_id, entities={})

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        self._counter += 1
        credential_id = f"conf-cred-{application_id}-{role}-{self._counter}"
        secret = f"conf-secret-{self._counter}-{uuid.uuid4().hex}"
        self._control.issue_credential(credential_id, application_id, role, secret)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._control.set_credential_state(handle.credential_ref, revoked=True)

    def disable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=False)

    def enable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=True)

    def set_authorization_state_available(self, available: bool) -> None:
        self._control.set_authorization_state_available(available)

    def propagation_bound_ms(self) -> int:
        # DataService._check() calls CredentialStore.assert_active() on
        # every single application-plane operation (see service.py _slot /
        # _check); there is no cached/derived authorization state, so
        # revoke/disable/state-unavailable propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # `DataService.capabilities()` is scoped to an authenticated
        # session (contract `endpoints.capabilities.auth`: "application or
        # control"), so this provisions a disposable application/credential
        # solely to obtain the peer's own real capability document -- it
        # does not fabricate one in the adapter.
        self._counter += 1
        probe_app = f"conf_capability_probe_{self._counter}_{uuid.uuid4().hex[:8]}"
        self.provision_application(probe_app)
        handle = self.issue_credential(probe_app, "runtime")
        session = self.authenticate(handle)
        return self._call(lambda: self._service.capabilities(session))

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5) -- provided branch (WP-5)
    # ------------------------------------------------------------------
    #
    # `ControlPlaneService` (design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md,
    # WP-3) is now a real, constructed facade on this adapter (`self.
    # _control_service`, `__init__` above) -- every one of the 13 port
    # v1.5 in-band/ritual/privileged operations below presents its request
    # to that same real service object, exactly as a real
    # `/control/v1`-equivalent caller would (this adapter never pre-filters
    # by credential kind/role before presenting a request -- design's own
    # "Authorization is the peer's own decision to make, not this port's").
    # `_call` (this file's own existing helper, used by every application-
    # plane method below already) is reused unchanged: `ControlPlaneService`
    # raises the identical `r2db_api.errors.FoundationError` every other
    # service method raises, so `classify()` needs no control-plane-specific
    # branch at all.

    def _actor_secret(self, actor: "CredentialHandle | ControlCredentialHandle") -> str | None:
        # Both port handle types carry `.secret` (application `CredentialHandle`
        # and control-plane `ControlCredentialHandle` alike) -- this adapter
        # never inspects which kind `actor` is before presenting it (see
        # this section's own header comment): `ControlPlaneService.
        # authenticate` tries the control-credential store only, so an
        # application credential's secret simply fails to match there,
        # exactly the fail-closed behavior C-14 vector 1 measures.
        return actor.secret

    # port v1.5
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        return self._call(lambda: self._control_service.capabilities(self._actor_secret(actor)))

    # port v1.5
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        return self._call(lambda: self._control_service.register_application(self._actor_secret(actor), application_id))

    # port v1.5
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        # Response-shape normalization (M-2): unwraps the real
        # `{"applications": [...]}` envelope into the row sequence itself
        # (port docstring).
        result = self._call(lambda: self._control_service.list_applications(self._actor_secret(actor)))
        return result["applications"]

    # port v1.5
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        return self._call(lambda: self._control_service.set_application_enabled(self._actor_secret(actor), application_id, enabled))

    # port v1.5
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        # Response-shape normalization (M-2): the real success response
        # (`{"credential_id", "application_id", "role", "secret"}`) is
        # unwrapped into this port's own `CredentialHandle` type -- only
        # reached on a genuine `runtime`/`developer` success; `role=
        # "control"` raises `CAPABILITY_UNSUPPORTED` before ever returning
        # here (C-14 vector 3), propagated unchanged by `_call`.
        result = self._call(lambda: self._control_service.issue_credential(self._actor_secret(actor), application_id, role))
        return CredentialHandle(credential_ref=result["credential_id"], application_id=result["application_id"], role=result["role"], secret=result["secret"])

    # port v1.5
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        # Response-shape normalization (M-2): unwraps the real
        # `{"credentials": [...]}` envelope; row keys (`credential_id`,
        # `application_id`, `role`, `enabled`, `revoked`) are already the
        # contract's own vocabulary, untouched.
        result = self._call(lambda: self._control_service.list_credentials(self._actor_secret(actor)))
        return result["credentials"]

    # port v1.5
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        return self._call(lambda: self._control_service.rotate_credential(self._actor_secret(actor), credential_ref))

    # port v1.5
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        return self._call(lambda: self._control_service.revoke_credential(
            self._actor_secret(actor), credential_ref, destructive=destructive, confirmation=confirmation
        ))

    # port v1.5
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        return self._call(lambda: self._control_service.set_credential_enabled(self._actor_secret(actor), credential_ref, enabled))

    # port v1.5 (ritual -- design R-5, no in-band actor by contract)
    def bootstrap(self) -> ControlCredentialHandle:
        # Real ceremony core (`control_plane.bootstrap_control_credential`)
        # against this adapter's own in-memory control-credential store --
        # the SAME product code `ops.py cmd_bootstrap` calls against
        # Postgres (work order §2: "adapter が peer の不足を埋めないため...
        # adapterはこの同じ製品コードをin-memoryストアで呼ぶ -- adapter自作
        # の儀式模倣は禁止"). No advisory lock: Postgres-only serialization
        # concern (design §5 item 2), irrelevant to a single, non-concurrent
        # in-process adapter instance.
        def op() -> ControlCredentialHandle:
            with self._control_credentials.unit_of_work() as work:
                credential_id, secret = bootstrap_control_credential(self._control_credentials, self._control_audit, work=work)
            return ControlCredentialHandle(credential_ref=credential_id, secret=secret)
        return self._call(op)

    # port v1.5 (ritual -- design R-5, no in-band actor by contract)
    def reset(self) -> ControlCredentialHandle:
        def op() -> ControlCredentialHandle:
            with self._control_credentials.unit_of_work() as work:
                credential_id, secret = reset_control_credentials(self._control_credentials, self._control_audit, work=work)
            return ControlCredentialHandle(credential_ref=credential_id, secret=secret)
        return self._call(op)

    def _mint_or_repair_control_credential(self) -> None:
        """Ensures `self._control_credential_ref`/`_secret` name a
        currently-valid, must-rotate-cleared control credential (port v1.5
        `control_credential()`'s own obligation, WP-1 independent review
        major M-4: "MUST return a handle that is genuinely valid AT CALL
        TIME...never a memoized value"). First call bootstraps (or, if a
        control-credential row already exists -- some other test on this
        session-scoped adapter ran first -- resets, to obtain a handle this
        adapter itself actually knows the secret for). Every later call
        re-validates the tracked secret directly against the real store
        (never assumed still valid): C-15's own vectors deliberately revoke/
        reset control credentials mid-suite, and a call here after one of
        those must repair via a real `reset`, not keep handing out a now-
        dead handle. Either path finishes with a genuine self-rotate
        (`ControlPlaneService.rotate_credential`) to clear `must_rotate` --
        never bypassed, exactly like a real operator completing the ritual
        would have to.
        """
        if self._control_credential_ref is not None:
            try:
                self._control_backend.authenticate(self._control_credential_secret)
                return  # still live, and already rotated by a prior call to this method
            except FoundationError:
                pass  # revoked/disabled since last use -- repair via reset below
        if self._control_credentials.has_any(include_revoked=True):
            with self._control_credentials.unit_of_work() as work:
                credential_id, secret = reset_control_credentials(self._control_credentials, self._control_audit, work=work)
        else:
            with self._control_credentials.unit_of_work() as work:
                credential_id, secret = bootstrap_control_credential(self._control_credentials, self._control_audit, work=work)
        rotated = self._control_service.rotate_credential(secret, credential_id)
        self._control_credential_ref = credential_id
        self._control_credential_secret = rotated["secret"]

    # port v1.5 (privileged setup)
    def control_credential(self) -> ControlCredentialHandle:
        self._mint_or_repair_control_credential()
        return ControlCredentialHandle(credential_ref=self._control_credential_ref, secret=self._control_credential_secret)

    # port v1.5 (privileged observation)
    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        # Design §12.5(iv)/§4: reads the DURABLE sink
        # (`ControlAuditSink.events()`) -- never `ControlAuthority`'s own
        # pre-existing, in-memory-only secondary trail (`self._service._audit`),
        # which is not the R-6 durable audit this port operation observes.
        return list(self._control_audit.events())

    # ------------------------------------------------------------------
    # audit_query surface (port v1.8, phase 4 WP-2(b) PROVIDED branch).
    # `ControlPlaneService` now declares `audit_query: {"status":
    # "enabled", ...}` (the real in-memory reader wired in `__init__`
    # above), so `_audit_query_status()` reads `"enabled"` and every one of
    # the three methods below takes the PROVIDED branch. They were written
    # in WP-1 against the REAL, eventual dispatch shape (read the live
    # declaration, then present a real request), so WP-2(b)'s flip needed
    # no port-adapter restructuring here -- only `ControlPlaneService.
    # capabilities()`/`.audit_query()` began telling a different, real
    # story. The `SurfaceAbsent` declare-first branch is retained and is
    # still the correct dispatch for a deployment that declares no audit
    # surface.
    # ------------------------------------------------------------------

    def _audit_query_status(self) -> str:
        """Reads this deployment's own `audit_query` capability status via
        this adapter's OWN privileged control credential (`control_
        credential()`, the same privileged-setup category as `control_
        audit_events()`) -- never via the `actor` a caller of `audit_query`
        supplies. `control_plane.authority` fails an APPLICATION credential
        closed on `control_capabilities` itself, so gating the declare-first
        check on `actor`'s own authority would make C-09 vector 3
        (application credential -> FORBIDDEN on `audit_query` once enabled)
        unreachable: this read is about the DEPLOYMENT's own posture, not
        about whichever `actor` is about to be presented to the real
        `audit_query` call below.
        """
        control_actor = self.control_credential()
        document = self._call(lambda: self._control_service.capabilities(self._actor_secret(control_actor)))
        return document.get("capabilities", {}).get("audit_query", {}).get("status", "unavailable")

    def _audit_surface_absent(self, operation: str, reason: str) -> SurfaceAbsent:
        # Same convention every other `SurfaceAbsent` raise on this adapter
        # follows (e.g. `attempt_cross_entity_batch` above): `surface` is
        # this adapter's own declared public evidence surface, so a
        # consumer can independently confirm none of it accepts an
        # audit-shaped parameter (`signature_forbids_parameters`), rather
        # than take the claim on faith.
        return SurfaceAbsent(
            self.name, operation, reason,
            surface=self.public_operation_callables(),
            forbidden_parameters=["audit"],
        )

    # port v1.8
    def audit_query(self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._audit_query_status() not in ("enabled", "partial"):
            raise self._audit_surface_absent(
                "audit_query",
                "control_capabilities().capabilities.audit_query.status is not enabled/partial -- WP-1 "
                "declare-first discipline does not present a request to ControlPlaneService.audit_query "
                "(design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md §8.4's extended SurfaceAbsent meaning)",
            )
        return self._call(lambda: self._control_service.audit_query(self._actor_secret(actor), dict(request)))

    # port v1.8
    def flush_audit_buffer(self) -> None:
        if self._audit_query_status() not in ("enabled", "partial"):
            raise self._audit_surface_absent(
                "flush_audit_buffer",
                "audit_query is not declared enabled/partial -- there is no bounded buffer to flush on this "
                "deployment's own declared posture",
            )
        # Phase 4 WP-2(b): D-4's bounded buffer (ordinary data-operation
        # success events) and D-3's denial-coalescing windows both live on
        # `self._service` (`DataService.flush_audit_buffer`, service.py) --
        # the SAME method the real composition root's periodic background
        # thread calls (`r2db_api.main.build_app`'s own `_audit_flush_loop`).
        # `force_expire_denial_windows` stays at its own default (False):
        # this hook exists so a test can make a just-buffered/just-
        # coalesced event visible without waiting, not to force-flush an
        # UNEXPIRED denial window early (a different, narrower concern that
        # default already serves correctly).
        self._call(lambda: self._service.flush_audit_buffer())

    # port v1.8
    def audit_visibility_lag_ms(self) -> int:
        control_actor = self.control_credential()
        document = self._call(lambda: self._control_service.capabilities(self._actor_secret(control_actor)))
        audit_query_capability = document.get("capabilities", {}).get("audit_query", {})
        if audit_query_capability.get("status") not in ("enabled", "partial"):
            raise self._audit_surface_absent(
                "audit_visibility_lag_ms",
                "audit_query is not declared enabled/partial -- there is no real declared visibility_lag_ms "
                "to read on this deployment's own declared posture",
            )
        lag_ms = audit_query_capability.get("visibility_lag_ms")
        assert isinstance(lag_ms, int) and lag_ms >= 0, (
            f"{self.name}: audit_query is declared enabled/partial but visibility_lag_ms is not a real "
            f"non-negative int -- got {lag_ms!r}"
        )
        return lag_ms

    # port v1.9 (phase 5 WP-1, D-2/CCR_DISPOSITION.md subordinate ruling
    # 10 item 2, design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_
    # V1.md §6.2): reaches `http.py::post_audit_query`'s own real body
    # directly -- `DataService.authenticate` then `DataService.deny_
    # unsupported`, in the same order, with the same arguments -- rather
    # than a mere authentication-surface fallback: this in-process plug
    # has no ASGI `Request` to route through the real handler with, but it
    # can call the exact same two methods the real handler's own body
    # calls, reaching the alias handler's own real behavior, not an
    # approximation of it.
    def audit_query_on_data_plane_host(
        self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if self._service._control_plane_status == "unavailable":  # noqa: SLF001
            raise self._audit_surface_absent(
                "audit_query_on_data_plane_host",
                "this data-plane host declares control_plane unavailable -- no control/audit credential "
                "could ever be presented to its own audit_query alias",
            )
        # Fix-round F-4 (disclosed limit, CONDITIONS.md C-09 limit (c)):
        # `request_id` is not threaded through this in-process call, unlike
        # the real `http.py::post_audit_query`'s own `_authenticate(request,
        # service)`, which passes the real ASGI request's own `_request_id
        # (request)`. This harness call has no ASGI `Request` to read one
        # from; the gap is disclosed rather than silently present.
        context = self._call(lambda: self._service.authenticate(actor.secret))
        # Unreached by any currently-registered adapter: this foundation's
        # application-only CredentialStore (`auth.py`) never recognizes a
        # control/audit credential's secret -- a genuinely separate store
        # from the control-plane one -- so `authenticate` above always
        # raises AUTH_INVALID first. A future co-hosted deployment whose
        # data-plane store DID recognize it would reach here, mirroring
        # `http.py::post_audit_query`'s own second step exactly.
        self._call(lambda: self._service.deny_unsupported(
            context,
            "audit_query",
            "Audit evidence query requires separately authenticated control/audit authority "
            "that this foundation does not expose over the application-facing HTTP surface.",
        ))
        raise AssertionError("unreachable")  # deny_unsupported always raises

    # port v1.9 fix-round (F-2/F-3): declares this in-process plug's own
    # topology fact -- `DataService` (data plane) and `ControlPlaneService`
    # (control plane) are two genuinely separate objects on this adapter,
    # constructed with no shared credential store (`self._credentials` is
    # application-only; the control plane's own credential store is a
    # separate object entirely) -- never co-hosted.
    def control_surface_cohosted_with_data_plane(self) -> bool:
        return False

    # port v1.5 (fix-round): the inverse of `provision_application` --
    # operator-privileged test-harness cleanup, never a public capability.
    # Design §12.5(iii): "port deprovision_application は service に対応物
    # を作らない...adapter は運用者特権経路で実装 (in-process: DataService
    # 内部状態)". This adapter's `provision_application`/in-band
    # `register_application_inband` both ultimately create one `DataService`
    # cell (no separate "registered but not DB-provisioned" state exists
    # in-memory -- see `DataService._register_application`), so undoing
    # either is the identical direct-state removal below; there is no
    # `ControlAuthority`/`ControlPlaneService` method for this at all
    # (consistent with the contract's application-deletion-out-of-v1-scope
    # stance -- this is exactly the "运用者特権の逆操作であり公開API能力
    # では決してない" setup primitive WP-1's port docstring already
    # describes).
    def deprovision_application(self, application_id: str) -> None:
        self._service._cells.pop(application_id, None)  # noqa: SLF001
        self._service._disabled_apps.discard(application_id)  # noqa: SLF001

    # ------------------------------------------------------------------
    # application plane
    # ------------------------------------------------------------------
    def authenticate(self, handle: CredentialHandle) -> object:
        return self._call(lambda: self._service.authenticate(handle.secret))

    def scope_of(self, session: object) -> ScopeView:
        return ScopeView(application_id=session.application_id, role=session.role)

    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        # port v1.3 (WP-5a activation of M-8): `create_entity` no longer
        # takes its fields inline (which would leave every column
        # untyped/JSONB, discarding `fields`'s own type values entirely).
        # This peer's own real create_entity + add_field(field_type=...)
        # sequence -- the same two-call shape
        # `conformance_adapter_r2db_http.py`'s HTTP twin already used, now
        # with the type actually wired through both plugs -- is what a real
        # client building a typed entity issues (design docs/design/
        # R2DB_CCR13_STORAGE_V1.md R-2: create_entity has no per-field type
        # slot in the common contract).
        self._call(lambda: self._service.schema(session, {"operation": "create_entity", "entity": entity}))
        for field_name, port_type in fields.items():
            operation: dict[str, Any] = {"operation": "add_field", "entity": entity, "field": field_name}
            contract_type = _PORT_FIELD_TYPE_TO_R2DB.get(port_type)
            if contract_type is None:
                raise ValueError(f"unmapped port field type {port_type!r} for field {field_name!r}")
            operation["field_type"] = contract_type
            self._call(lambda op=operation: self._service.schema(session, op))

    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None:
        self._call(lambda: self._service.mutate(
            session, entity, [{"operation": "insert", "values": dict(values)}]
        ))

    def select_eq(self, session, entity: str, select: Sequence[str], field: str | None, value: Any) -> list[dict]:
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        return self._call(lambda: self._service.query(session, entity, select=list(select), where=where))

    def attempt_filter(
        self, session, entity: str, select: Sequence[str], field: str, operator: str, value: Any
    ) -> list[dict]:
        # The same real, single query entry point `select_eq` above already
        # uses, generalized to an arbitrary operator -- an operator this
        # peer does not declare (`structured_query.operators`) is presented
        # here exactly as a real client attempting it would be, and
        # whatever `DataService.query` itself produces (success or
        # `ConformanceDenial`) is returned, never fabricated.
        where = [{"field": field, "operator": operator, "value": value}]
        return self._call(lambda: self._service.query(session, entity, select=list(select), where=where))

    def _declared_contract_version(self) -> str:
        # port v1.6 declare-and-echo (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): cached after the
        # first real `capability_document()` call -- this peer's declared
        # `contract_version` is static for this adapter instance's whole
        # lifetime, so re-fetching it on every destructive-operation call
        # site would only add cost, never change the answer.
        if self._contract_version_cache is None:
            self._contract_version_cache = str(self.capability_document()["contract_version"])
        return self._contract_version_cache

    def _resolve_confirmation(self, confirmation: Any, *, probe: Callable[[], Any], legacy_token: str) -> Any:
        """`VALID_CONFIRMATION` sentinel resolution (design R-6 item 1,
        `adapter.resolve_valid_confirmation`): a peer declaring
        `contract_version >= 1.2.0` gets a real probe -> echo round trip;
        a peer still on 1.1.0 gets its legacy fixed token, unchanged. Any
        other `confirmation` value (`None`, or a caller-supplied string)
        passes straight through -- this method only ever interprets the
        `VALID_CONFIRMATION` sentinel itself.
        """
        if confirmation is not VALID_CONFIRMATION:
            return confirmation
        return resolve_valid_confirmation(
            contract_version=self._declared_contract_version(), legacy_token=legacy_token, probe=probe
        )

    def delete(self, session, entity: str, field: str, value: Any, *, destructive: bool, confirmation: str | None) -> int:
        # VALID_CONFIRMATION sentinel protocol (design section 10.1,
        # updated port v1.6 for declare-and-echo -- design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): `destructive` always
        # passes through faithfully; `confirmation` None means "supply
        # nothing", VALID_CONFIRMATION resolves to a real, currently-valid
        # confirmation for this exact request via `_resolve_confirmation`
        # (declare-and-echo for a >= 1.2.0 peer, this peer's legacy fixed
        # token "DELETE" otherwise), and any other string passes through
        # verbatim so a wrong token is still observable as a wrong token to
        # this peer's own validation.
        def probe() -> None:
            self._call(lambda: self._service.mutate(session, entity, [{
                "operation": "delete",
                "where": [{"field": field, "operator": "eq", "value": value}],
                "destructive": True,
            }]))

        peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
        operation: dict[str, Any] = {
            "operation": "delete",
            "where": [{"field": field, "operator": "eq", "value": value}],
            "destructive": destructive,
        }
        if peer_confirmation is not None:
            operation["confirmation"] = peer_confirmation
        return self._call(lambda: self._service.mutate(session, entity, [operation]))

    def count(self, session, entity: str) -> int:
        def op() -> int:
            canonical = self._service._check(session)
            cell = self._service._cells.get(canonical.application_id)
            return len(cell.entities.get(entity, [])) if cell is not None else 0
        return self._call(op)

    def entities(self, session) -> set[str]:
        # Uses the peer's public catalog operation. This previously reached
        # into DataService's private cell map because no public catalog
        # existed -- an adapter compensating for a peer gap, which design
        # section 10.5 forbids. DataService.catalog() now exists, so the
        # adapter observes the peer the way an application caller does.
        def op() -> set[str]:
            document = self._service.catalog(session)
            return {item["entity"] for item in document["entities"]}
        return self._call(op)

    def catalog_document(self, session) -> Mapping[str, Any]:
        # The peer's own real `CatalogDocument` (DataService.catalog),
        # returned exactly as `entities()` above already consumes it --
        # this is a real, present discovery surface for this peer (contract
        # capability `application_catalog: enabled`), never a fabricated
        # document.
        return self._call(lambda: self._service.catalog(session))

    def _build_mutation_item(
        self,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None,
        unique_key: str | None,
        destructive: bool = False,
        confirmation: Any = None,
        session: object = None,
        entity: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"operation": operation}
        if values is not None:
            item["values"] = dict(values)
        if where_field is not None:
            item["where"] = [{"field": where_field, "operator": "eq", "value": where_value}]
        if destructive:
            # `destructive` is only ever meaningful when true (bind_
            # mutation's own default is false), so it is only set here
            # rather than always present.
            item["destructive"] = True
        # port v1.6 declare-and-echo (WP-3, C-06 V2b-wire, review
        # recommendation from port v1.6's own review): `confirmation` is set
        # whenever the caller supplies one, INDEPENDENT of `destructive` --
        # an earlier revision of this method only ever set `confirmation`
        # inside the `if destructive:` branch above, which made it
        # impossible to construct a request whose wire OMITS `destructive`
        # entirely (not merely `false`) while still carrying a real,
        # currently-valid `confirmation` phrase for the identical request --
        # exactly the literal wire-omission shape contract `valid_
        # confirmation`'s "a missing destructive field is equivalent to
        # false, never to true" rule requires this peer to still deny.
        # `session`/`entity` are only required when `confirmation is VALID_
        # CONFIRMATION` (the probe needs a real entry point to present
        # itself to); every other caller of this batch operation on this
        # peer passes a real confirmation string or `None` directly.
        if confirmation is not None:
            if confirmation is VALID_CONFIRMATION:
                assert session is not None and entity is not None, (
                    "_build_mutation_item: VALID_CONFIRMATION requires session/entity to build its probe"
                )
                # Snapshot of `item` as it stands right now (operation/
                # values/where/destructive, no confirmation yet). The probe
                # itself always presents `destructive: True` regardless of
                # this call's own `destructive` argument -- a probe must
                # reliably trigger the peer's own denial to read the real
                # phrase back, independent of whether the OUTER request
                # under construction carries `destructive: True` or omits
                # it entirely.
                probe_item = dict(item)
                probe_item["destructive"] = True

                def probe(_session=session, _entity=entity, _probe_item=probe_item) -> None:
                    self._call(lambda: self._service.mutate(_session, _entity, [dict(_probe_item)]))

                peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
            else:
                peer_confirmation = confirmation
            if peer_confirmation is not None:
                item["confirmation"] = peer_confirmation
        if expected_revision is not None:
            # A real parameter position on this peer's single mutation
            # dispatcher (`Mutation.expected_revision`, `structured.py`'s
            # `_MUTATION_KEYS`) -- carried through exactly like `values`/
            # `where` above, never interpreted here. As of work package
            # WP-5b this peer declares `revision_preconditions: enabled`
            # and genuinely evaluates it (R-4); before that it was a real,
            # present `CAPABILITY_UNSUPPORTED` denial rather than a
            # `SurfaceAbsent` one either way.
            item["expected_revision"] = expected_revision
        if unique_key is not None:
            # port v1.3: `Mutation.unique_key` (CCR-13 §0.5 Q-1 plan B),
            # same real parameter position, same "never interpreted here"
            # treatment.
            item["unique_key"] = unique_key
        return item

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
        item = self._build_mutation_item(
            operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        return self._call(lambda: self._service.mutate(session, entity, [item]))

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
        item = self._build_mutation_item(
            operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        # `DataService.mutate_result` is the real, present entry point that
        # actually observes `assigned_addresses` (`MutationResult`,
        # service.py) -- `mutate()` above deliberately stays byte-for-byte
        # backward compatible with every pre-CCR13 caller and never exposes
        # them at all, so this is a genuinely different call, not the same
        # one re-read.
        result = self._call(lambda: self._service.mutate_result(session, entity, [item]))
        return result.affected, list(result.assigned_addresses)

    def attempt_batch_with_addresses(
        self, session, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        items = [
            self._build_mutation_item(
                op.operation, values=op.values, where_field=op.where_field, where_value=op.where_value,
                expected_revision=op.expected_revision, unique_key=op.unique_key,
                destructive=op.destructive, confirmation=op.confirmation,
                session=session, entity=entity,
            )
            for op in operations
        ]
        # The same real, single `mutate_result` entry point
        # `attempt_mutation_with_addresses` above uses, given every
        # operation in one call -- exactly what a real client sending a
        # multi-operation atomic batch would do, never several separate
        # single-operation calls this adapter stitches together itself.
        result = self._call(lambda: self._service.mutate_result(session, entity, items))
        return result.affected, list(result.assigned_addresses)

    def attempt_cross_entity_batch(self, session, operations: Sequence[ScopedBatchOperation]) -> int:
        # P35 WP-3 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_
        # 130_V1.md, P35-D1): this peer's `cross_entity_mutation` stays
        # `unavailable` -- no real per-request demand exists on this peer,
        # only on `MitateDB-api` -- and `DataService` genuinely has no
        # cross-entity entry point at all: `query`/`mutate` each take a
        # single `entity` positional argument; `schema` takes ONE
        # operation dict whose `entity` is a key within it, not a second
        # entity argument or slot for more than one; there is no generic
        # dispatcher anywhere on this peer that could carry more than one
        # entity name in a single call the way `MitateDB-api`'s `transact`
        # does (confirmed by source inspection of `service.py`, not
        # assumed -- review correction n-3 (phase 3.5 WP-3): the prior
        # revision of this comment additionally cited `mutate_result` here,
        # which is real but is NOT part of `public_operation_callables()`
        # -- this peer's declared application-facing evidence surface below
        # -- and so does not itself belong in this claim's own reasoning).
        # This is a structural absence, not a denial this adapter observed
        # from a real call -- exactly the honest form `SurfaceAbsent`'s own
        # docstring requires, matching the identical reasoning `create_
        # unique_index`/`drop_entity` use on `conformance_adapter_
        # mitatedb.py` for their own genuinely absent surfaces. `session`/
        # `operations` are accepted only to match this ABC method's
        # signature -- there is no real entry point to pass them through to.
        raise SurfaceAbsent(
            self.name, "attempt_cross_entity_batch",
            "DataService has no cross-entity mutation entry point -- query/mutate each take a single entity "
            "argument, schema takes one operation dict whose entity is a key (not a second entity slot), and "
            "no generic multi-entity dispatcher exists on this peer "
            f"(requested {len(operations)} operation(s) across "
            f"{sorted({op.entity for op in operations})!r})",
            surface=self.public_operation_callables(),
            forbidden_parameters=["entities", "cross_entity", "scoped"],
        )

    def create_unique_index(self, session, entity: str, index: str, fields: Sequence[str]) -> None:
        # Presented to the same real, single generic schema dispatcher every
        # other schema operation on this peer goes through (`DataService.
        # schema`) -- there is no separate "unique index" entry point,
        # exactly like `attempt_mutation`'s `upsert` branch above.
        # `create_index` is real, executable vocabulary on this peer as of
        # docs/design/R2DB_CCR13_STORAGE_V1.md work package WP-3, so a
        # well-formed request against a real entity/fields genuinely
        # succeeds here; a malformed or conflicting one still gets a real
        # `ConformanceDenial` from this same dispatcher, never fabricated.
        self._call(lambda: self._service.schema(session, {
            "operation": "create_index",
            "entity": entity,
            "index": index,
            "fields": list(fields),
            "unique": True,
        }))

    def drop_entity(self, session, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        # port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
        # item 3): the destructive twin of `create_unique_index` above --
        # same real, single `DataService.schema()` dispatcher, `drop_entity`
        # being real, executable vocabulary on this peer already
        # (`structured.py`'s `bind_schema_operation`/execution branches).
        # `destructive`/`confirmation` follow the identical VALID_
        # CONFIRMATION sentinel protocol as `delete()` above.
        def probe() -> None:
            self._call(lambda: self._service.schema(session, {
                "operation": "drop_entity", "entity": entity, "destructive": True,
            }))

        peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DROP_ENTITY")
        operation: dict[str, Any] = {"operation": "drop_entity", "entity": entity, "destructive": destructive}
        if peer_confirmation is not None:
            operation["confirmation"] = peer_confirmation
        self._call(lambda: self._service.schema(session, operation))

    def query_with_revisions(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        # `DataService.query()` (what `select_eq` above uses) deliberately
        # stays byte-for-byte backward compatible with every pre-CCR13
        # caller and returns a bare `list[dict]` with structurally no place
        # a `revisions` key could occupy -- so this method observes the
        # *other* real, present entry point instead: `DataService.
        # query_page()`, whose `QueryPage.revisions` is genuinely populated
        # as of work package WP-5b (`revision_preconditions: enabled`).
        # This is the same "observe the real response, don't hardcode a
        # claim about it" principle conformance-review correction M-1
        # already established for `conformance_adapter_r2db_http.py`'s
        # sibling method, applied here now that a real revisions-bearing
        # entry point exists on this plug too.
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        page = self._call(lambda: self._service.query_page(session, entity, select=list(select), where=where))
        return page.items, list(page.revisions)

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------
    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        # The genuine application-facing surface: everything an
        # authenticated application credential can reach through
        # DataService. ControlAuthority is deliberately excluded; it is a
        # separate, non-application-facing authority (topology.py).
        return [
            self._service.authenticate,
            self._service.capabilities,
            self._service.query,
            self._service.mutate,
            self._service.schema,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        session_a = fixture.runtime_a

        def forged_scope_attempt() -> None:
            # Same credential id, application_id renamed to the other
            # application: exactly the r2db-specific guidance in the task
            # brief and the scenario r2db-api/tests/test_foundation.py
            # already exercises for its own suite.
            forged = replace(session_a, application_id=fixture.app_b)
            self._call(lambda: self._service.query(forged, fixture.shared_entity, select=["item_key"]))

        def role_elevation_attempt() -> None:
            # Same credential id, role self-declared as "developer" while
            # the backing credential is actually "runtime".
            forged = replace(session_a, role="developer")
            self._call(lambda: self._service.schema(
                forged, {"operation": "create_entity", "entity": "conf_role_elevation_probe", "fields": ["item_key"]}
            ))

        def request_field_scope_attempt() -> None:
            # A legitimate, untampered session, but the request body itself
            # carries a smuggled scope-looking field. The mutation shape
            # validator rejects any key outside its known operation shape.
            operation = {"operation": "insert", "values": {"item_key": 999}, "application_id": fixture.app_b}
            self._call(lambda: self._service.mutate(session_a, fixture.shared_entity, [operation]))

        def cross_application_handle_attempt() -> None:
            # A legitimate, untampered session for A reaching straight for
            # an entity that only exists in B's cell.
            self._call(lambda: self._service.query(session_a, fixture.b_only_entity, select=["item_key"]))

        return [
            TamperVector(
                kind="forged_scope_object",
                name="r2db_forged_application_id_on_auth_context",
                disposition="must_deny",
                attempt=forged_scope_attempt,
            ),
            TamperVector(
                kind="role_elevation",
                name="r2db_forged_developer_role_on_auth_context",
                disposition="must_deny",
                attempt=role_elevation_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="r2db_smuggled_application_id_in_mutation_body",
                disposition="must_deny",
                attempt=request_field_scope_attempt,
            ),
            TamperVector(
                kind="cross_application_handle",
                name="r2db_runtime_a_reaches_b_only_entity",
                disposition="must_deny",
                attempt=cross_application_handle_attempt,
            ),
        ]

    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        # `ControlAuthority.set_credential_state` is the only control-plane
        # surface on this peer that could conceivably reactivate a revoked
        # credential; it takes `enabled`/`revoked` as two independent
        # booleans (auth.py's `CredentialStore.set_state`), so both are
        # exercised as real attempts rather than declared structurally
        # absent (design docs/design/CONFORMANCE_CONDITIONS_V1_1.md
        # section 2's stated minimum for this peer).
        def revoked_false_attempt() -> None:
            self._call(lambda: self._control.set_credential_state(handle.credential_ref, revoked=False))

        def enabled_true_attempt() -> None:
            # `enabled=True` alone (no `revoked=False`) is a distinct,
            # non-terminal flag (auth.py: `revoked` is checked before
            # `enabled` in both `authenticate`/`assert_active`) -- this
            # call is expected to succeed without raising, but must not
            # actually let the credential authenticate again.
            self._call(lambda: self._control.set_credential_state(handle.credential_ref, enabled=True))

        # CCR-14 WP-5 (design §4/§8 M-3): `/control/v1`'s own in-band
        # enable/rotate are a NEW candidate reactivation surface this
        # peer did not have before CCR-14 (`ControlAuthority` had no
        # `rotate` concept at all, and its own `set_credential_state` is
        # already covered by the two vectors above) -- the reactivation
        # network's "this peer's control-plane surface is exhausted"
        # declaration must widen to cover it too, or it would silently
        # become an unguarded reactivation path the moment it existed.
        #
        # WP-5 round-2 review NIT-1: every vector below fetches its own
        # control actor LAZILY, inside its own `attempt()` -- never
        # captured eagerly at vector-construction time -- so a later vector
        # in this same list revoking/resetting the tracked control
        # credential (the control-credential-targeting vector does exactly
        # that) can never leave an earlier-constructed-but-not-yet-attempted
        # vector holding a stale actor if a future change reorders this list.
        def inband_enable_attempt() -> None:
            # `set_credential_enabled_inband` reaches `ControlPlaneService.
            # set_credential_enabled`, which -- correctly -- only ever
            # touches `enabled`, never `revoked` (see `control_plane.py`'s
            # `_set_credential_state`). Expected to succeed (revoked stays
            # untouched); `must_ignore`'s own post-condition (this
            # condition test's own re-`authenticate(handle)` check) is what
            # actually proves it never reactivated `handle`.
            control_actor = self.control_credential()
            self._call(lambda: self._control_service.set_credential_enabled(control_actor.secret, handle.credential_ref, True))

        def inband_rotate_attempt() -> None:
            # `ControlPlaneService.rotate_credential` explicitly refuses a
            # revoked credential (`VALIDATION_FAILED`) before ever touching
            # the store -- this control-plane call itself refuses to act on
            # an already-revoked credential (`must_deny`'s own definition).
            control_actor = self.control_credential()
            self._call(lambda: self._control_service.rotate_credential(control_actor.secret, handle.credential_ref))

        # The CONTROL-credential half of this coverage (work order §4:
        # "application/control 両 credential"). Plan B/reset semantics mean
        # there is only ever ONE live control-credential lineage on this
        # peer at a time (bootstrap refuses when any row exists; reset
        # revokes every row before minting its one replacement) -- there is
        # therefore no way to hold a second, independently-live control
        # credential to act as "the authorized caller" against a first one
        # being revoked. This attempt uses the SAME credential for both
        # roles instead: it fetches the currently-live tracked control
        # credential, revokes it (a real, successful in-band call), and
        # then immediately attempts to rotate that now-revoked credential
        # -- deferred to `attempt()` time (never done eagerly here at
        # vector-construction time), so this vector's own side effect
        # (killing the live control credential) never reaches outside its
        # own `v.attempt()` call. `self._control_credential_ref` is left
        # pointing at now-revoked state deliberately: `control_credential()`'s
        # own re-validation (`_mint_or_repair_control_credential`) detects
        # this the next time anything asks for a live control actor and
        # repairs via a real `reset()`, exactly as it already does after
        # C-15's own revoke/reset vectors run mid-suite.
        #
        # WP-5 round-2 review MINOR-7 (observed denial code): because actor
        # and target are the SAME now-revoked credential, `rotate_credential`'s
        # own `authenticate(secret)` step (`ControlPlaneService._authenticate`,
        # which runs before any target-state check at all) is what actually
        # denies this call -- `AUTH_REVOKED`, not `rotate_credential`'s own
        # "revoked target" `VALIDATION_FAILED` refusal (that check is never
        # reached, since the caller itself never gets past authentication).
        # This vector's real detection power is therefore "a revoked control
        # credential can no longer authenticate at all" -- still a genuine,
        # `must_deny`-shaped property this peer must uphold, just via the
        # authentication gate rather than the target-revocation check the
        # sibling application-credential vector (`inband_rotate_attempt`,
        # above) exercises with a still-live, distinct actor.
        def inband_rotate_revoked_control_credential_attempt() -> None:
            actor = self.control_credential()
            # port v1.6 declare-and-echo (WP-3, design docs/design/
            # DESTRUCTIVE_CONFIRMATION_V1.md R-3): same fix as
            # conformance_adapter_r2db_http.py's identical vector -- the
            # revoke here is a SETUP step (this vector's real target is the
            # `rotate` call below, against a now-genuinely-revoked control
            # credential), so it probes -> echoes the real phrase to
            # actually complete the revoke.
            try:
                self._call(lambda: self._control_service.revoke_credential(actor.secret, actor.credential_ref, destructive=True))
            except ConformanceDenial as denial:
                # Opus review minor m-4: only the gate's own denial code is
                # a probe to echo past -- any OTHER denial here is a real,
                # unexpected finding (e.g. an auth failure) and must
                # propagate, never be silently swallowed as if it were the
                # gate.
                if denial.code != "DESTRUCTIVE_CONFIRMATION_REQUIRED":
                    raise
                phrase = denial.details["required_confirmation"]
                revoked = self._call(lambda: self._control_service.revoke_credential(actor.secret, actor.credential_ref, destructive=True, confirmation=phrase))
                assert revoked.get("revoked") is True, f"echoing the real phrase did not actually revoke the credential: {revoked!r}"
            self._call(lambda: self._control_service.rotate_credential(actor.secret, actor.credential_ref))

        return [
            TamperVector(
                kind="credential_reactivation",
                name="r2db_set_credential_state_revoked_false",
                disposition="must_deny",
                attempt=revoked_false_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_set_credential_state_enabled_true_after_revoke",
                disposition="must_ignore",
                attempt=enabled_true_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_inband_enable_revoked_application_credential",
                disposition="must_ignore",
                attempt=inband_enable_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_inband_rotate_revoked_application_credential",
                disposition="must_deny",
                attempt=inband_rotate_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_inband_rotate_revoked_control_credential",
                disposition="must_deny",
                attempt=inband_rotate_revoked_control_credential_attempt,
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        developer_a = fixture.developer_a

        def entity_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.query(runtime_a, payload, select=["id"]))

        def select_field_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.query(runtime_a, fixture.shared_entity, select=[payload]))

        def filter_field_probe(payload: Any) -> Any:
            # `select` must name a real field of `shared_entity` (`id` is no
            # longer one -- see `build_fixture`'s comment) so this probe's
            # denial is genuinely attributable to the malicious `payload`
            # filter field, not an incidental unknown-select-field NOT_FOUND
            # that would mask whether `payload` itself was ever validated.
            return self._call(lambda: self._service.query(
                runtime_a, fixture.shared_entity, select=["item_key"],
                where=[{"field": payload, "operator": "eq", "value": 1}],
            ))

        def insert_field_probe(payload: Any) -> Any:
            # `payload` becomes a dict key here; an unhashable NON_STRING
            # payload (e.g. [], {}) cannot even be placed at this position --
            # the request can't be constructed, so this is a harness-level
            # impossibility, not an observation of this peer's validation
            # (design section 10.3).
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    "insert_field", payload, "payload is unhashable and this position is a mapping key"
                ) from exc
            return self._call(lambda: self._service.mutate(
                runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {payload: "x"}}]
            ))

        def schema_entity_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.schema(
                developer_a, {"operation": "create_entity", "entity": payload, "fields": ["item_key"]}
            ))

        def schema_field_probe(payload: Any) -> Any:
            return self._call(lambda: self._service.schema(
                developer_a, {"operation": "add_field", "entity": fixture.shared_entity, "field": payload}
            ))

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
                marker = f"probe-{uuid.uuid4().hex}"
                self._service.mutate(runtime_a, entity, [
                    {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
                ])
                rows = self._service.query(
                    runtime_a, entity, select=["probe_value"],
                    where=[{"field": "probe_key", "operator": "eq", "value": marker}],
                )
                return rows[0]["probe_value"] if rows else None
            return self._call(op)

        def filter_value_probe(payload: Any) -> Any:
            def op() -> Any:
                marker = f"probe-{uuid.uuid4().hex}"
                self._service.mutate(runtime_a, entity, [
                    {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
                ])
                rows = self._service.query(
                    runtime_a, entity, select=["probe_value"],
                    where=[
                        {"field": "probe_key", "operator": "eq", "value": marker},
                        {"field": "probe_value", "operator": "eq", "value": payload},
                    ],
                )
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
        if isinstance(exc, FoundationError):
            return exc.code
        # A native, non-FoundationError failure is not a denial this
        # adapter can vouch for as a rejection -- laundering it into a
        # plausible-looking contract code would hide a peer crash behind a
        # passing test (design section 10.2). Report it as unclassified so
        # the suite's code-membership check fails loudly instead.
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
        # collides with the first (CONFLICT).
        self._counter += 1
        suffix = f"{self._counter}_{uuid.uuid4().hex[:8]}"
        app_a, app_b = f"conf_app_a_{suffix}", f"conf_app_b_{suffix}"
        self.provision_application(app_a)
        self.provision_application(app_b)

        # `item_key`, not `id`: `id` is reserved on `r2db-api` (design
        # docs/design/R2DB_CCR13_STORAGE_V1.md R-3 -- the server-assigned
        # address column) and is not to be used as an ordinary field name by
        # the common fixture/probes (port v1.2 coordinated revision,
        # docs/design/CONFORMANCE_ADAPTER_V1.md section 12).
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
        # In-memory-only foundation; nothing external to release.
        pass

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except FoundationError as exc:
            raise self._deny(exc) from exc
        except (TypeError, ValueError) as exc:
            raise self._deny(exc) from exc

    def _deny(self, exc: BaseException) -> ConformanceDenial:
        # port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
        # item 2): `FoundationError.details` is this peer's own real
        # structured details mapping (`errors.py`'s `to_dict()` -- the
        # same object a real problem+json response's `details` field
        # carries); any other native exception (`TypeError`/`ValueError`)
        # has none, so this maps to an empty mapping rather than `None`.
        return ConformanceDenial(
            code=self.classify(exc), adapter=self.name, native_type=type(exc).__name__,
            details=getattr(exc, "details", None),
        )


def build_adapter() -> ConformanceAdapter:
    return R2DBConformanceAdapter()
