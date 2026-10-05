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
import threading
import uuid
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Callable, Iterator, Mapping, Sequence

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
    ENUM_CLEAR,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    AdmissionHold,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ControlCredentialHandle,
    CredentialHandle,
    Fixture,
    IdempotencyHold,
    IsolatedControlHandle,
    PayloadNotExpressible,
    PlanVerificationHold,
    ScopedBatchOperation,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    WireEntry,
    apply_limits_override,
    fold_batch_idempotency_key,
    fresh_identifier,
    resolve_valid_confirmation,
)
from adapter import _EnumClear  # noqa: E402  -- type-hint only, mirrors ConformanceAdapter's own signature

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role  # noqa: E402
from mitatedb_api.application_audit import ApplicationAuditSink  # noqa: E402
from mitatedb_api.audit_dispatch import AuditRouter  # noqa: E402
from mitatedb_api.audit_query import InMemoryAuditQueryStore  # noqa: E402
from mitatedb_api.cell import ApplicationDeveloper, ApplicationRuntime  # noqa: E402
from mitatedb_api.config import FoundationConfig  # noqa: E402
from mitatedb_api.control_audit import ControlAuditSink  # noqa: E402
from mitatedb_api.control_auth import ControlCredentialStore, _InMemoryWork  # noqa: E402
from mitatedb_api.operation_catalog import load_operation_catalog_bytes  # noqa: E402
from mitatedb_api.control_plane import (  # noqa: E402
    ControlPlaneLimits,
    ControlPlaneService,
    bootstrap_control_credential,
    reset_control_credentials,
)
from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE  # noqa: E402
from mitatedb_api.errors import (  # noqa: E402
    AuthenticationError,
    AuthorizationError,
    AuthorizationStateUnavailable,
    CapabilityError,
    ConflictError,
    DestructiveConfirmationRequired,
    FoundationError,
    NotFoundError,
    PreconditionFailedError,
    ResourceLimitError,
    ValidationError,
)
from mitatedb_api.service import MitateDataService as _MitateDataServiceClass  # noqa: E402,F401
from mitatedb_api.surfaces import build_surfaces  # noqa: E402

# Phase 6 WP-3 (design D-2, §6.1 (b)): this plug's own synthetic,
# unreachable pair of `surfaces` base URLs -- see `__init__`'s own
# comment for why a real one is neither possible nor required here.
_SYNTHETIC_DATA_BASE_URL = "http://mitatedb-inprocess.example.invalid/v1"
_SYNTHETIC_CONTROL_BASE_URL = "http://mitatedb-inprocess.example.invalid/control/v1"
# Phase 11 WP-3 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5):
# this in-process plug's own declared `operation_catalog_url` -- synthetic,
# non-dialable (this plug has no real HTTP layer at all, the SAME honest
# limit the two constants immediately above already carry), shared by the
# data-plane `FoundationConfig` and the control-plane `ControlPlaneService`
# below, exactly as `_SYNTHETIC_DATA_BASE_URL`/`_SYNTHETIC_CONTROL_BASE_URL`
# already are.
_SYNTHETIC_OPERATION_CATALOG_URL = "http://mitatedb-inprocess.example.invalid/v1/operation-catalog"

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
    # Phase 9 WP-3b (design D-4/D-3 (6), 追補 2 S-h): a stale `plan` --
    # no shared inheritance with any neighbor here either, matching
    # `http.py::_CLASSIFY_ORDER`'s own identical addition (F-10, this
    # peer's two error-classification tables kept in agreement).
    (PreconditionFailedError, "PRECONDITION_FAILED"),
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
        # Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
        # V1.md §4/§1-E, P35-D6): per-application issuance freeze -- like
        # `control_plane.InMemoryControlBackend`'s own identical addition,
        # this concept has no home on `self._control.credentials` at all
        # (a control-plane-only concept the application-plane read view has
        # never needed to know about), so it is genuinely new backend-local
        # state here too, mutated only through `set_application_issuance_
        # frozen` below via the same `work.on_rollback(...)` undo-log
        # convention every other write method in this class already uses.
        self._frozen_applications: set[str] = set()

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

    def applications_count_locked(self, work) -> int:
        """Phase 10 WP-6b (design D-5 (ii) region (iii)): a plain forward
        to `applications_count` -- this adapter's own `unit_of_work()`
        above (unlike `control_plane.InMemoryControlBackend`'s) takes NO
        lock at all: it yields a bare `_InMemoryWork()` with no
        `threading.Lock`/`RLock` of its own. This is disclosed, not
        asserted safe -- the C-05 conformance harness's own bound tests
        (`hold_in_flight`) currently drive this adapter's plug in-process,
        single-threaded, per its own isolation profile, so the absence of
        a lock here has not caused an observed race; it has not been
        exercised under genuine multi-threaded contention either. `work`
        is accepted only so `ControlPlaneService.register_application`'s
        single, backend-agnostic call site works against every backend,
        this one included."""
        del work
        return self.applications_count()

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

    def application_issuance_frozen(self, application_id: str) -> bool:
        return application_id in self._frozen_applications

    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work) -> None:
        # Review m-2 (Phase 3.5 WP-5): mirrors `set_application_enabled`
        # above -- an unknown `application_id` must fail closed with
        # `NotFoundError`, not silently record a freeze/unfreeze against an
        # application that does not exist (the product registries,
        # `InMemoryApplicationRegistry`/`PostgresApplicationRegistry`, both
        # already refuse this the same way; this adapter's own local
        # `_frozen_applications` set had no such check and would otherwise
        # accept an application_id nothing else in this adapter recognizes).
        current = dict(self._control.credentials.list_applications()).get(application_id)
        if current is None:
            raise NotFoundError("application not found")
        was_frozen = application_id in self._frozen_applications
        if frozen:
            self._frozen_applications.add(application_id)
        else:
            self._frozen_applications.discard(application_id)

        def _undo() -> None:
            if was_frozen:
                self._frozen_applications.add(application_id)
            else:
                self._frozen_applications.discard(application_id)
        work.on_rollback(_undo)

    def credential_state(self, credential_id: str):
        return self._control.credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._control.credentials.credentials_active_count(application_id)

    def credentials_active_count_locked(self, application_id: str, work) -> int:
        """The `credentials_per_application` counterpart of
        `applications_count_locked` above -- same disclosure, same
        no-lock `unit_of_work()`."""
        del work
        return self.credentials_active_count(application_id)

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

    def authenticate_control(self, secret):
        """Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
        裁定 1): this adapter never splits a bearer it did not itself
        compose (design D-1(d), port v1.10's own "no composition, no
        decomposition" fixture) -- `secret` here is the composed bearer
        this adapter's own `ControlCredentialHandle.secret` carries,
        passed straight through, UNSPLIT, to `control_auth.
        ControlCredentialStore.authenticate`, which is the single choke
        point that calls `split_bearer_locator` exactly once."""
        return self._control_credentials.authenticate(secret)

    def authenticate_application(self, secret):
        """Phase 4 WP-3(b) (design D-5): `self._control.credentials` is
        this adapter's own `auth.CredentialStore` (2ストア突合, this
        module's own header) -- `peek()` (not `authenticate()`) is used
        deliberately: see `CredentialStore.peek`'s own docstring for why
        `authenticate()` would durably record a spurious denial row on
        every `audit_query` call made with a control/audit credential.
        Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): `secret` is the full
        presented bearer, passed straight through, unsplit -- `peek`
        itself is the single choke point that splits it."""
        principal = self._control.credentials.peek(secret)
        if principal is None:
            return None
        return principal.credential_id, principal.application_id, principal.role.value

    def append_audit(self, *, work=None, **fields):
        return self._audit.append(work=work, **fields)


class _StalledGateContextManager:
    """The per-call context-manager object `_stalled_limit_gate` (below)
    returns -- delegates BOTH `__enter__`/`__exit__` to the REAL `_limit_
    gate` generator context manager it wraps, but blocks on a shared
    `threading.Event` INSIDE `__enter__`, after the real gate's own
    `__enter__` has already run (rate acquire + in-flight counter
    increment + request_bytes/operation_depth checks, `cell.py::
    ApplicationCell._limit_gate`) and returned its own `deadline` value,
    and BEFORE returning that value back to the real caller (`catalog`/
    `insert`/.../`ApplicationRuntime.capabilities`'s own `with self.
    _limit_gate(...) as deadline:` block) -- which is exactly what lets
    the backend's request scope (opened by the caller only AFTER that
    `with` block's own body starts) stay unopened for as long as this
    stalls."""

    __slots__ = ("_inner", "_entered", "_release")

    def __init__(self, inner_cm, entered: threading.Semaphore, release: threading.Event) -> None:
        self._inner = inner_cm
        self._entered = entered
        self._release = release

    def __enter__(self):
        value = self._inner.__enter__()
        self._entered.release()
        self._release.wait()
        return value

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)


# Phase 8 WP-1 rework 2 (裁定 3, 監督裁定 2026-09-07): a bounded wait for
# the background threads to reach the stall point, in place of an
# unbounded `entered.acquire()`. If the gate this probe depends on ever
# stops stalling calls where this helper expects (a genuine product
# regression, or a future change to this stall point's own placement --
# this peer's 2 plugs are exactly the ones review finding 3 measured
# actually deadlocking pre-fix, since `hold_in_flight`'s own `with`
# block waits for `n` real threads to finish, and those threads in turn
# wait on `release`, which this context manager only ever sets after
# its own body runs -- a probe assertion failing INSIDE that body used
# to leave the `finally` unreached only in the sense that it still ran,
# but the N+1 probe itself never got a chance to observe anything before
# the whole test process hung on `entered.acquire()` if the stall point
# moved outside the counter), the previous unbounded wait hung the WHOLE
# test process forever -- `.github/workflows/ci.yml` has no
# `timeout-minutes` and this repository has no pytest-timeout plugin,
# so that hang was never observed as a red test, only as an indefinite
# CI job. 30s is generous for a handful of already-started local threads
# to reach a stall point that is normally reached in well under a
# second.
_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S = 30.0


@contextmanager
def _hold_in_flight_via_stalled_gate(cell_obj: object, make_request: Callable[[], None], n: int):
    """port v1.12 `hold_in_flight` realization (adapter-internal plumbing,
    never port-visible -- design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_
    HYGIENE_V1.md D-2 実装の形 (b)). Wraps `cell_obj`'s (an `Application
    Cell`) own `_limit_gate` bound method -- the single choke EVERY
    application-plane operation on this peer passes through (`cell.py::
    ApplicationCell._limit_gate`'s own docstring lists every caller) --
    with an instance-attribute proxy returning `_StalledGateContextManager`
    above, rather than wrapping any ONE operation method wholesale: this
    peer's own gate (rate/concurrency/request_bytes/operation_depth) is
    entered FROM INSIDE an operation method's own body (unlike r2db-api,
    whose equivalent `_slot` wraps the CELL DISPATCH from the OUTSIDE,
    `conformance_adapter_r2db.py`'s own identical-named helper), so
    stalling before delegating to the whole original operation method
    would stall BEFORE the gate's own counter increment ever ran --
    exactly the "operation methods 入口 (lock 取得前)" placement D-2's own
    table requires must sit AFTER the counter, not before it. Wrapping
    `_backend` instead would hang permanently at `n >= 2` (D-2's own
    explicit prohibition: a second held thread would block forever
    trying to open the backend's request scope while the first one holds
    it stalled inside `_backend`, never reaching this proxy's own release
    wait at all).

    `n` real background OS threads each issue one genuine, full port-
    level request (`make_request()`, e.g. `session.catalog()` -- needs no
    pre-existing entity/row) that reaches this stall point via the SAME
    real `_limit_gate` call its own real operation method already makes.
    Waits for every one of the `n` threads to have genuinely entered the
    stalled gate (a `threading.Semaphore`, not a fixed sleep) before
    yielding. Releases and joins every thread before returning control,
    re-raising the first background thread exception (if any) only after
    the gate is restored and every thread has been joined -- never
    swallowed."""
    original_gate = cell_obj._limit_gate  # noqa: SLF001 -- adapter-internal plumbing, same convention this file's own `isolated_application_surface()` teardown already uses (`cell._backend.close()`).
    entered = threading.Semaphore(0)
    release = threading.Event()
    errors: list[BaseException] = []

    # `*args, **kwargs`, forwarded verbatim to `original_gate`: this stall
    # point holds the request AFTER the real gate's own `__enter__`
    # (rate/concurrency/request_bytes/operation_depth already checked)
    # and BEFORE that value reaches the caller, without needing to know
    # `_limit_gate`'s own current keyword signature.
    def _stalled_limit_gate(*args, **kwargs):
        inner = original_gate(*args, **kwargs)
        return _StalledGateContextManager(inner, entered, release)

    cell_obj._limit_gate = _stalled_limit_gate  # noqa: SLF001

    def _run() -> None:
        try:
            make_request()
        except BaseException as exc:  # noqa: BLE001 -- collected, never swallowed; re-raised below after every thread is joined and the gate is restored.
            errors.append(exc)

    threads = [threading.Thread(target=_run, daemon=True) for _ in range(n)]
    for t in threads:
        t.start()
    entered_count = 0
    for entered_count in range(n):
        if not entered.acquire(timeout=_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S):
            break
    else:
        entered_count = n
    try:
        if entered_count < n:
            raise AssertionError(
                f"hold_in_flight: only {entered_count} of {n} held requests reached "
                f"the stalled `_limit_gate` within {_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S}s "
                "(expected every one of them to stall inside ApplicationCell."
                "_limit_gate's own counter increment, AFTER the real gate's __enter__ "
                "-- see this helper's own docstring); failing loud instead of hanging "
                "(裁定 3, 監督裁定 2026-09-07)"
            )
        # Phase 8 WP-1 rework 3 (裁定 5, 監督裁定 2026-09-07): yields the
        # REAL measured count of held requests (`entered_count`, from the
        # semaphore-acquire loop above) -- never a bare `None` a caller
        # could only pair with a tautological `n >= 1` check. By this
        # point `entered_count == n` always holds (the `AssertionError`
        # above already fired otherwise), but the caller sees the
        # MEASUREMENT, not an echo of its own input.
        yield entered_count
    finally:
        release.set()
        for t in threads:
            t.join(timeout=_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S)
        cell_obj._limit_gate = original_gate  # noqa: SLF001
    if errors:
        raise errors[0]


# port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
# WP-6d-ii): `hold_after_idempotency_lookup` realization for this
# in-process plug. `ApplicationCell._idempotency_check` (`cell.py::ApplicationCell._idempotency_check`)
# is the ONE choke every keyed entry point calls -- it performs BOTH the
# lookup AND the `idempotency_entries` reservation and returns `(replay_
# response, digest, now_ms)`; a fresh admission is exactly the case
# `replay_response is None`. Every public entry point already holds this
# SAME backend's request scope (the SQLite backend's own `RLock`) for its
# ENTIRE call -- lookup -> pass-1 -> pass-2 -- so a second,
# key-matching request ("B") never even reaches `_idempotency_check`
# while "A" is held: B blocks opening its own request scope at the top of
# whatever public method it calls instead (design D-13 "実装の形
# (6d-ii) の確定" (4) 表, `MitateDB-api` row). This function only needs
# to recognize the ONE call that is both key-matching and a fresh
# admission, and stall its RETURN -- the end of the admission window,
# after the reservation, before the caller executes anything.


@contextmanager
def _hold_after_idempotency_check(cell_obj: object, idempotency_key: str) -> Iterator[IdempotencyHold]:
    original_check = cell_obj._idempotency_check  # noqa: SLF001
    entered = threading.Semaphore(0)
    release = threading.Event()

    def _checked(key, digest_request, **kwargs):
        result = original_check(key, digest_request, **kwargs)
        replay_response, _digest, _now_ms = result
        # A fresh admission (`replay_response is None`) for the key this
        # hold is watching -- a replay, a CONFLICT/LIMIT_EXCEEDED
        # (raised, never reaching this point), or a different key passes
        # straight through (design's own "idempotency_key に一致しない
        # 要求は素通しする").
        if replay_response is None and key == idempotency_key:
            entered.release()
            release.wait()
        return result

    setattr(cell_obj, "_idempotency_check", _checked)

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_idempotency_lookup: the held request never reached the end of its "
                f"idempotency admission window within {timeout_s}s (expected it to stall right after "
                "_idempotency_check returns a fresh admission -- see this helper's own module comment)"
            )
        return 1

    try:
        yield IdempotencyHold(_wait_until_held)
    finally:
        release.set()
        setattr(cell_obj, "_idempotency_check", original_check)


# port v1.20 (docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
# section 9's `conformance-tests/` paragraph, Q-5): `hold_after_plan_
# verification` realization for this in-process plug. A schema operation
# on `ApplicationCell` (`create_entity` / `add_field` / `alter_field`,
# `cell.py`) that presents a `plan` or `dry_run` reads the Application's
# current revision and checks its `plan` against it in the cell
# (`check_plan_precondition`), and only then calls the backend's
# DDL-carrying method -- `create_collection` / `add_field` /
# `alter_field_constraints` -- which is the first thing that changes the
# schema. The stall point is the ENTRY of that backend call, on the
# Application's own backend instance: after the revision read and the
# plan check (and after every lock the cell took for them), before the
# first DDL statement. The cell's own `create_collection` / `create_entity`
# / `add_field` / `alter_field` are wrapped only to mark the calling
# thread while a call that presents a `plan` or `dry_run` is in progress;
# a schema operation presenting neither passes through, unmarked. One
# armed hold claims the first marked call that reaches the stall point (a
# `threading.Lock` nobody releases) and lets every later call through, so
# exactly ONE schema operation is held. Data operations never reach the
# three backend methods. The adapter replaces these product methods on
# the instance and restores them on exit; no product source changes.


@contextmanager
def _hold_after_plan_verification(cell_obj: object) -> Iterator[PlanVerificationHold]:
    backend = cell_obj._backend  # noqa: SLF001 -- adapter-internal plumbing, same convention `_hold_after_idempotency_check` above uses.
    backend_names = ("create_collection", "add_field", "alter_field_constraints")
    cell_names = ("create_collection", "create_entity", "add_field", "alter_field")
    backend_originals = {name: getattr(backend, name) for name in backend_names}
    cell_originals = {name: getattr(cell_obj, name) for name in cell_names}
    claimed = threading.Lock()
    entered = threading.Semaphore(0)
    release = threading.Event()
    marked = threading.local()

    def _marking(original):
        def _marked(*args, **kwargs):
            previous = getattr(marked, "presents_plan_or_dry_run", False)
            marked.presents_plan_or_dry_run = previous or kwargs.get("plan") is not None or bool(kwargs.get("dry_run"))
            try:
                return original(*args, **kwargs)
            finally:
                marked.presents_plan_or_dry_run = previous

        return _marked

    def _stalling(original):
        def _stalled(*args, **kwargs):
            if getattr(marked, "presents_plan_or_dry_run", False) and claimed.acquire(blocking=False):
                entered.release()
                release.wait()
            return original(*args, **kwargs)

        return _stalled

    for name, original in cell_originals.items():
        setattr(cell_obj, name, _marking(original))
    for name, original in backend_originals.items():
        setattr(backend, name, _stalling(original))

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_plan_verification: no schema operation reached the entry of the backend's "
                f"DDL-carrying method within {timeout_s}s (expected the next schema operation presenting a "
                "plan or dry_run on this Application to stall there -- see this helper's own module comment)"
            )
        return 1

    try:
        yield PlanVerificationHold(_wait_until_held)
    finally:
        release.set()
        for name, original in backend_originals.items():
            setattr(backend, name, original)
        for name, original in cell_originals.items():
            setattr(cell_obj, name, original)


# port v1.22 (design docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md D-7 and
# section 6.4): `hold_after_admission` realization for this in-process
# plug. `ApplicationCell._limit_gate` is where a request's rate and
# concurrency gates run, its request-size and depth checks run, its `budget`
# narrows the bounds and the deadline is computed from them; it yields that
# deadline, and the caller opens the backend's request scope -- the
# request's first connection -- only after that. A stall just after the
# gate has yielded is therefore the point after the bounds are fixed and
# before the first connection acquisition, and holds the request's
# concurrency slot as the contract point requires. The gate is entered by
# every kind of request; the three the primitive holds -- a query, a
# mutation and a schema operation -- are exactly the ones whose caller
# names an `endpoint_kind` (`query`, `mutate`, `schema`) so that `budget`
# narrows for them, and a request that names none (a catalog read, a
# single-row write) passes through. The wrap replaces the gate on the cell
# instance and restores it on exit, like `_hold_in_flight_via_stalled_gate`
# above; no product source changes. The first caller to reach the stall
# claims it (a `threading.Lock` nobody releases), every later call goes
# through, so exactly ONE request is held. This plug's backend is SQLite
# and issues no PostgreSQL statement, so the yielded handle keeps
# `AdmissionHold`'s default `statements_after_release` (`None`).


class _AdmissionGateContextManager:
    """The per-call context-manager object `_hold_after_admission_via_
    stalled_gate` returns for a request that names an `endpoint_kind`:
    delegates to the REAL `_limit_gate` context manager it wraps, and
    inside `__enter__`, after the real gate has run and returned its
    `deadline`, the first such request to arrive claims the stall and
    blocks on a shared `threading.Event` before the value reaches the
    caller."""

    __slots__ = ("_inner", "_claimed", "_entered", "_release")

    def __init__(self, inner_cm, claimed: threading.Lock, entered: threading.Semaphore, release: threading.Event) -> None:
        self._inner = inner_cm
        self._claimed = claimed
        self._entered = entered
        self._release = release

    def __enter__(self):
        value = self._inner.__enter__()
        if self._claimed.acquire(blocking=False):
            self._entered.release()
            self._release.wait()
        return value

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)


@contextmanager
def _hold_after_admission_via_stalled_gate(cell_obj: object) -> Iterator[AdmissionHold]:
    original_gate = cell_obj._limit_gate  # noqa: SLF001 -- adapter-internal plumbing, same convention `_hold_in_flight_via_stalled_gate` above uses.
    claimed = threading.Lock()
    entered = threading.Semaphore(0)
    release = threading.Event()

    def _admission_limit_gate(*args, **kwargs):
        inner = original_gate(*args, **kwargs)
        if kwargs.get("endpoint_kind") is None:
            return inner
        return _AdmissionGateContextManager(inner, claimed, entered, release)

    cell_obj._limit_gate = _admission_limit_gate  # noqa: SLF001

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_admission: no request reached the stalled `_limit_gate` within {timeout_s}s "
                "(expected the next query, mutation or schema operation on this Application to stall just "
                "after the gate yielded its deadline -- see this helper's own module comment)"
            )
        return 1

    try:
        yield AdmissionHold(_wait_until_held)
    finally:
        release.set()
        cell_obj._limit_gate = original_gate  # noqa: SLF001


class MitateDBConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to the MitateDB-api foundation.

    A "session" for this peer is an `ApplicationRuntime` /
    `ApplicationDeveloper`. Control-plane operations go through
    `ControlPlane`, which a session object has no way to reach (cell.py
    sessions only ever hold a cell handle and a Principal).
    """

    name = "MitateDB-api"
    # port v1.14 (design D-1 (A) 4, WP-3): drives `MitateDataService`/
    # `ApplicationCell` directly, no ASGI/HTTP boundary at all.
    transport_kind = "in_process"

    def __init__(self, *, config: FoundationConfig | None = None) -> None:
        # port v1.11 (design D-6.1/D-6.5 addendum (1)): `config` is how
        # `isolated_application_surface()` below gives its own fresh
        # instance a SMALL conformance profile (the `max_*` fields) while
        # keeping the SAME `control_plane_status`/synthetic `surfaces`
        # every pre-WP-4 caller (this repository's own session-scoped
        # construction included) already used. `None` keeps this
        # constructor's own long-standing default, unchanged.
        #
        # Synthetic pepper for this conformance run only; never a real
        # deployment secret and never read from the environment.
        # WP-5 flip (design v1.2 R-7): `control_plane_status="enabled"` is
        # a real constructor injection into the SAME `FoundationConfig`
        # every provisioned cell shares (R-3: single source of truth) --
        # not a value this adapter fabricates only inside
        # `capability_document()`.
        # Phase 4 WP-3(b) (design D-5/D-10, work order "in-process adapter
        # は... WP-1 で r2db in-process がどう PROVIDED になっているかを参照
        # して同型に実現する"): a real, shared `AuditRouter` -- an in-memory
        # durable sink (`ApplicationAuditSink`) -- wired into BOTH `self.
        # _control.credentials` and every cell `self._control.provision_
        # application` builds (`ControlPlane.__init__`/`provision_
        # application`'s own WP-3(b) propagation, `service.py`). Without
        # this, this adapter's application-plane durable audit events would
        # never exist at all (each component would build its own private,
        # unshared default router), and this control surface could never
        # take the PROVIDED `audit_query` branch -- it would stay
        # `SurfaceAbsent` forever, unlike r2db-api's own in-process adapter.
        self._application_durable_audit = ApplicationAuditSink()
        self._audit_router = AuditRouter(durable_sink=self._application_durable_audit)
        self._control = ControlPlane(
            "synthetic-conformance-pepper-mitatedb-0000000",
            config=config or FoundationConfig(
                control_plane_status="enabled",
                # Phase 6 WP-3 (design D-2, §6.1 (b)): this plug has no
                # real host at all -- a synthetic, unreachable pair of
                # base URLs satisfies contract 1.6.0's own unconditional
                # `surfaces.data` obligation without claiming a real
                # address this plug never answers requests at (the
                # declare-and-echo vector is HTTP-plug-only, design §6.2
                # (2)(iii)).
                data_base_url=_SYNTHETIC_DATA_BASE_URL,
                control_base_url=_SYNTHETIC_CONTROL_BASE_URL,
                operation_catalog_url=_SYNTHETIC_OPERATION_CATALOG_URL,
            ),
            audit_router=self._audit_router,
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
        # control_requests_per_minute=200` are this adapter's own
        # CONFIGURED construction values, not an upper bound the product
        # enforces (Phase 5 D-3, Q3 案A, WP-4 removed `ControlPlaneLimits`'
        # former `[1, 200]` ceiling on all four request-count classes --
        # these numbers are a still-valid choice, no longer the only legal
        # one). They still satisfy R-6's own relational check
        # (`200 > 100 + 2*5 + 67`, unaffected by the ceiling removal) with
        # the SAME margin r2db-api measured sufficient for its own, larger
        # combined suite; WP-5's own completion condition requires
        # recording this adapter's real measured `n_existing` (both at
        # C-14 vector 5 and at session end) -- see the WP-5 completion
        # report.
        # ------------------------------------------------------------
        self._control_credential_pepper = "synthetic-conformance-pepper-mitatedb-ctl-0000000"
        self._control_credentials = ControlCredentialStore(self._control_credential_pepper)
        self._control_audit = ControlAuditSink()
        self._control_backend = _ReconciledControlBackend(self._control, self._control_credentials, self._control_audit)
        self._control_limits = ControlPlaneLimits(
            applications=100, credentials_per_application=5, control_requests_per_minute=200)
        # Phase 4 WP-3(b) (design D-5/D-10): the in-memory `audit_query`
        # reader -- UNIONs `self._control_audit` (control plane) with
        # `self._application_durable_audit` (application plane, the SAME
        # sink `self._audit_router` above writes through) -- `visibility_
        # lag_ms=0` (in-memory writes are synchronous; no real writer-
        # connection timeout basis exists to derive a lag from, mirrors
        # r2db-api's own in-process adapter).
        self._audit_reader = InMemoryAuditQueryStore(self._control_audit, self._application_durable_audit)
        self._control_service = ControlPlaneService(
            self._control_backend, limits=self._control_limits,
            audit_reader=self._audit_reader, audit_visibility_lag_ms=0,
            audit_coalescing_window_ms=int(self._audit_router.denial_coalesce_window_s * 1000),
            # Phase 6 WP-3 (design D-2): the SAME synthetic pair the
            # data-plane `FoundationConfig` above declares -- both this
            # plug's own "processes" agree on `surfaces` structurally
            # (one Python object literally shares the values), never by
            # cross-checking two independently-configured copies.
            surfaces=build_surfaces(data_url=_SYNTHETIC_DATA_BASE_URL, control_url=_SYNTHETIC_CONTROL_BASE_URL),
            operation_catalog_url=_SYNTHETIC_OPERATION_CATALOG_URL,
        )
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

    def tampered_bearer(self, handle: "CredentialHandle | ControlCredentialHandle") -> str:
        """port v1.10 追補 (supervisor ruling 2026-09-04, brief item C):
        this peer's own locator bearer shape (`credential_wire.split_bearer_locator`, split once inside the store)
        is `<credential_id>.<secret>` -- a bearer naming the SAME real
        `credential_id` with a fresh, never-issued secret authenticates
        as `credential_id`-known-but-digest-mismatched, exactly the
        "bogus secret on a real credential_ref" vector `test_c15` needs.
        Composition ALLOWLISTED at this one line (test_c19_client_self_
        sufficiency.py's own `_COMPOSITION_ALLOWLIST`, port docstring's
        own "the ONLY place ANY adapter composes a bearer" rule)."""
        return f"{handle.credential_ref}.{fresh_identifier('tampered')}"

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

    def _actor_secret(self, actor: "CredentialHandle | ControlCredentialHandle") -> str:
        # Both port handle types carry `.secret` (application
        # `CredentialHandle` and control-plane `ControlCredentialHandle`
        # alike) -- this adapter never inspects which kind `actor` is
        # before presenting it: `ControlPlaneService._authenticate` tries
        # the control-credential store only, so an application
        # credential's bearer simply fails to match there, exactly the
        # fail-closed behavior C-14 vector 1 measures. Phase 6 WP-3 差し
        # 戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 1): `actor.
        # secret` is already the full composed bearer (port v1.10, this
        # adapter never composes/decomposes it) -- returned verbatim, no
        # separate `credential_id` extraction any more (every
        # `ControlPlaneService` public method now takes this ONE value).
        return actor.secret

    # port v1.5
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.control_capabilities(secret))

    # port v1.5
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.register_application(secret, application_id))

    # port v1.5
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        secret = self._actor_secret(actor)
        result = self._call(lambda: self._control_service.list_applications(secret))
        return result["applications"]

    # port v1.5
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.set_application_enabled(secret, application_id, enabled))

    # port v1.5
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        secret = self._actor_secret(actor)
        result = self._call(lambda: self._control_service.issue_credential(secret, application_id, role))
        return CredentialHandle(
            credential_ref=result["credential_id"], application_id=result["application_id"],
            role=result["role"], secret=result["secret"],
        )

    # port v1.5
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        secret = self._actor_secret(actor)
        result = self._call(lambda: self._control_service.list_credentials(secret))
        return result["credentials"]

    # port v1.5
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.rotate_credential(secret, credential_ref))

    # port v1.5
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.revoke_credential(
            secret, credential_ref, destructive=destructive, confirmation=confirmation))

    # port v1.5
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.set_credential_enabled(secret, credential_ref, enabled))

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
                # Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling
                # 2026-09-04, 裁定 1): `control_auth.ControlCredentialStore.
                # authenticate` now takes the FULL composed bearer -- `self.
                # _control_credential_secret` (`ControlPlaneService.
                # rotate_credential`'s own response) is passed straight
                # through, unsplit, exactly like `authenticate_control`
                # above.
                self._control_credentials.authenticate(self._control_credential_secret)
                return  # still live, and already rotated by a prior call to this method
            except FoundationError:
                pass  # revoked/disabled since last use -- repair via reset below
        if self._control_credentials.has_any(include_revoked=True):
            credential_id, secret = self._reset_control_credentials_now()
        else:
            with self._control_ritual_unit_of_work() as work:
                credential_id, secret = bootstrap_control_credential(
                    self._control_credentials, self._control_audit.append, work=work)
        rotated = self._control_service.rotate_credential(secret, credential_id)
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

    # port v1.10 addendum A (supervisor ruling 2026-09-04, C-14 vector 5's
    # own test primitive -- mirrors conformance_adapter_r2db.py's identical
    # method). A fresh `ControlPlaneService` sharing THIS adapter's own real
    # `self._control_backend`/`self._control_limits`/`self._audit_reader`
    # (the same objects `self._control_service` -- the SHARED surface -- is
    # built from), so the SAME credentials/applications authenticate
    # against it, but its own `_rate_window` starts empty. No real resource
    # to release on exit (in-memory construction only).
    @contextmanager
    def isolated_control_surface(self, *, limits_override: Mapping[str, int] | None = None):
        # port v1.11 addendum (supervisor ruling 2026-09-06 item 1): the
        # ONLY change from the pre-addendum construction above is `limits=
        # effective_limits` instead of `limits=self._control_limits` --
        # `apply_limits_override` returns `self._control_limits` itself,
        # unchanged, when `limits_override` is `None` (every pre-addendum
        # call site), so this is behavior-preserving for the `control_
        # requests_per_minute` vector.
        effective_limits = apply_limits_override(self._control_limits, limits_override)
        fresh_service = ControlPlaneService(
            self._control_backend, limits=effective_limits,
            audit_reader=self._audit_reader, audit_visibility_lag_ms=0,
            audit_coalescing_window_ms=int(self._audit_router.denial_coalesce_window_s * 1000),
            surfaces=build_surfaces(data_url=_SYNTHETIC_DATA_BASE_URL, control_url=_SYNTHETIC_CONTROL_BASE_URL),
            operation_catalog_url=_SYNTHETIC_OPERATION_CATALOG_URL,
        )
        # This primitive's OWN residue list (supervisor ruling 2026-09-06
        # item 2): applications `register_application` below registers
        # successfully are recorded here and deprovisioned on exit -- never
        # left for a caller to clean up itself (that would risk a double
        # deprovision attempt against an application this primitive already
        # removed).
        driven_applications: list[str] = []

        def call(actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
            secret = self._actor_secret(actor)
            return self._call(lambda: fresh_service.control_capabilities(secret))

        def register_application(
            actor: "CredentialHandle | ControlCredentialHandle", application_id: str
        ) -> Mapping[str, Any]:
            secret = self._actor_secret(actor)
            result = self._call(lambda: fresh_service.register_application(secret, application_id))
            driven_applications.append(application_id)
            return result

        def list_applications(actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
            secret = self._actor_secret(actor)
            result = self._call(lambda: fresh_service.list_applications(secret))
            return result["applications"]

        try:
            yield IsolatedControlHandle(
                capabilities=call, register_application=register_application, list_applications=list_applications,
            )
        finally:
            errors: list[str] = []
            for application_id in driven_applications:
                try:
                    self.deprovision_application(application_id)
                except Exception as exc:  # noqa: BLE001 - report, never swallow.
                    errors.append(f"{application_id!r}: {exc!r}")
            if errors:
                raise RuntimeError(
                    "isolated_control_surface() failed to deprovision one or more applications its own "
                    "handle registered:\n" + "\n".join(f"  - {e}" for e in errors)
                )

    # port v1.11 (design D-6.1 V2/D-6.5 addendum (1)/(4)): a genuinely
    # FRESH, throwaway `MitateDBConformanceAdapter` -- true self-
    # similarity, built via this class's own ordinary constructor with a
    # SMALL `FoundationConfig` profile. "Q4の宣言表・role設定はこの経路に
    # 一切現れない" (addendum (4)) -- this never touches platform DB
    # declarations at all, `FoundationConfig` is a pure, local dataclass.
    # Shares nothing with the shared surface: its own `ControlPlane`/
    # `MitateDataService`/`cells` dict are entirely separate objects.
    #
    # On exit: this adapter's own `close()` (below) is a documented
    # no-op ("in-memory sqlite; nothing external to release... each
    # build_adapter() call gets a fresh ControlPlane") -- correct for the
    # SESSION-scoped adapter (the whole process exits anyway), but this
    # primitive's own (e) resource check (D-6.6's supervisor note: "in-
    # memory plug は...cellごとのsqlite3.connect(':memory:')...計数対象は
    # このlive なsqlite接続数") needs a REAL release to be observable, so
    # this closes every real per-cell `SQLiteBackend` connection this
    # isolated instance provisioned directly, rather than relying on
    # `close()`.
    @contextmanager
    def isolated_application_surface(self):
        small_config = FoundationConfig(
            control_plane_status="enabled",
            data_base_url=_SYNTHETIC_DATA_BASE_URL,
            control_base_url=_SYNTHETIC_CONTROL_BASE_URL,
            operation_catalog_url=_SYNTHETIC_OPERATION_CATALOG_URL,
            max_batch_items=10,
            max_batch_entities=5,
            max_result_rows=5,
            max_fields=64,
            max_filter_terms=5,
            max_request_bytes=4096,
            max_schema_objects=20,
            # Phase 8 WP-1a (design D-1 実装の形 7): all 4 new count values
            # stay <= `_MAX_EXERCISABLE_LIMIT` (200, `test_c05_limit_
            # declaration_agreement.py::_MAX_EXERCISABLE_LIMIT`). `concurrency=3`: `hold_in_
            # flight` (WP-1b) genuinely holds this many threads/connections
            # open, so a small, realistic count keeps the drive cheap.
            # `requests_per_minute=50` matches r2db's own 2 plug isolated
            # values (`conformance_adapter_r2db.py::_ISOLATED_APPLICATION_LIMITS`/`conformance_
            # adapter_r2db_http.py::_ISOLATED_APPLICATION_LIMITS`) -- the rate-headroom assert WP-1b
            # adds needs room above `concurrency`'s own bound. `execution_
            # ms=5000` mirrors this same profile's r2db counterpart
            # (unused by any V2 driver -- `reference_wall_clock`, never
            # `enforced` -- but must stay comfortably larger than a slow
            # CI iteration to avoid a false peer-local `execution_ms`
            # denial). `operation_depth=5` (Phase 8 WP-1b, R-A 監督裁定
            # 2026-09-06, raised from 4): `_drive_operation_depth`
            # (`test_c05_limit_declaration_agreement.py`) asserts this
            # EXACT value against its own update+where recipe's measured
            # real depth (entity/request -> operations[] -> operation
            # dict -> where[] -> predicate dict = depth 5) -- at the
            # pre-WP-1b value of 4, EVERY `where`-carrying mutation
            # (`update`/`delete`) was spuriously `LIMIT_EXCEEDED`(
            # `operation_depth`) on this surface, not merely a
            # deliberately-oversized N+1 probe (measured, WP-1a rework:
            # `MitateDB-api-http`'s own `delete()` probe in
            # `test_c04_unsupported_and_safe_errors.py` sits at this same
            # real depth 5 and was failing for exactly this reason before
            # this raise). Matches both r2db plugs' identical isolated
            # profile value.
            max_requests_per_minute=50,
            max_concurrency=3,
            max_execution_ms=5000,
            max_operation_depth=5,
            # Phase 9 WP-3a (design §5 U-1 = (β)): small and genuinely
            # exercisable (`test_c05_limit_declaration_agreement.py`'s own
            # `_MAX_EXERCISABLE_LIMIT` bound, 200) -- an `enum` this small
            # is cheap to drive past in a V2 limit-declaration-agreement
            # probe, matching every other small isolated-profile value
            # above (`max_batch_entities`/`max_result_rows`/`max_filter_
            # terms`, all 5).
            max_enum_members=5,
            # Phase 9 WP-3c (design D-5, 追補 2 S-f; 監督裁定集約
            # rulings-r5-r6.md I-10, 裁定 J-7): small like every other
            # COUNT-valued field above (<= `_MAX_EXERCISABLE_LIMIT`, 200)
            # -- `test_c23_idempotency_semantics.py`'s own (full) leg
            # reads this deployment's own declared `idempotency_entries`
            # back out of `capabilities()` and drives exactly that many
            # distinct-key inserts before asserting the (declared + 1)-th
            # distinct key is refused `LIMIT_EXCEEDED`/`idempotency_
            # entries`. `idempotency_retention_ms=60_000` (60s) is
            # declared-only on this leg (never driven -- waiting it out
            # for real would make the suite itself slow, `test_c23`'s own
            # module docstring), so this value only needs to outlast one
            # test run, not match any production number.
            idempotency_entries=20,
            idempotency_retention_ms=60_000,
        )
        fresh = MitateDBConformanceAdapter(config=small_config)
        try:
            yield fresh
        finally:
            for cell in fresh._control.cells.values():  # noqa: SLF001
                cell._backend.close()  # noqa: SLF001

    # port v1.12 (design D-2 実装の形 (b), work order WP-1b): wraps this
    # cell's own `_limit_gate` (see `_hold_in_flight_via_stalled_gate`'s
    # own docstring above for why the gate itself, not any one operation
    # method, is the correct wrap point on THIS peer). Each held request
    # is a real `session.catalog()` call -- parameterless, needs no
    # pre-existing entity, and is a genuine gated operation (`cell.py::
    # ApplicationCell.catalog`'s own Phase 8 WP-1a rework 1 comment).
    def hold_in_flight(self, session, n: int):
        """See `ConformanceAdapter.hold_in_flight`'s own docstring
        (`adapter.py`) for this primitive's port-level meaning; this
        realization's own stall point is documented on `_hold_in_flight_
        via_stalled_gate` and the comment immediately above this
        method."""
        cell = self._control.cells[session.principal.application_id]
        return _hold_in_flight_via_stalled_gate(cell, lambda: self._call(lambda: session.catalog()), n)

    # port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
    # WP-6d-ii): wraps this SAME cell's own `_idempotency_check` --
    # see `_hold_after_idempotency_check`'s own module comment for why
    # the backend's request scope (not this hook) is what a concurrent
    # second request actually waits on.
    def hold_after_idempotency_lookup(self, session, idempotency_key: str):
        """See `ConformanceAdapter.hold_after_idempotency_lookup`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_idempotency_check` and the comment immediately
        above this method."""
        cell = self._control.cells[session.principal.application_id]
        return _hold_after_idempotency_check(cell, idempotency_key)

    # port v1.20: wraps this Application's own backend's DDL-carrying
    # methods -- see `_hold_after_plan_verification`'s own module comment
    # for why the stall point sits at their entry and what a concurrent
    # second schema operation waits on.
    def hold_after_plan_verification(self, session):
        """See `ConformanceAdapter.hold_after_plan_verification`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_plan_verification` and the comment immediately above
        it."""
        cell = self._control.cells[session.principal.application_id]
        return _hold_after_plan_verification(cell)

    # port v1.22: wraps this cell's own `_limit_gate` -- see `_hold_after_admission_via_stalled_gate`'s
    # own module comment for why the point just after the gate yields is the point after the bounds
    # are fixed and before the first connection acquisition.
    def hold_after_admission(self, session):
        """See `ConformanceAdapter.hold_after_admission`'s own docstring
        (`adapter.py`) for this primitive's port-level meaning; this
        realization's own stall point is documented on
        `_hold_after_admission_via_stalled_gate` and the comment
        immediately above it."""
        cell = self._control.cells[session.principal.application_id]
        return _hold_after_admission_via_stalled_gate(cell)

    def wire_entry(self, application_id: str) -> WireEntry:
        """See `ConformanceAdapter.wire_entry`'s own docstring
        (`adapter.py`). This plug's `transport_kind` is `"in_process"`: it
        drives the peer's product objects directly and has no wire, so a
        call is a port-usage error and raises `AssertionError` -- it never
        returns a send function and never skips."""
        raise AssertionError(
            "wire_entry: this plug's transport_kind is 'in_process' and it has no wire; "
            "only a plug that dials a transport (asgi or socket) has a wire entry"
        )

    # ------------------------------------------------------------------
    # audit_query surface (port v1.8, phase 4 WP-3(b) PROVIDED branch).
    # `ControlPlaneService.control_capabilities()` now declares `audit_
    # query: {"status": "enabled", ...}` (the real reader wired in
    # `__init__` above), so every one of the three methods below takes the
    # PROVIDED branch.
    # ------------------------------------------------------------------

    def _audit_query_status(self) -> str:
        """Reads via this adapter's OWN privileged control credential
        (`control_credential()`), never via the `actor` a caller of
        `audit_query` supplies -- `control_plane.authority` fails an
        APPLICATION credential closed on `control_capabilities` itself, so
        gating on `actor`'s own authority would make C-09 vector 3
        (application credential -> FORBIDDEN on `audit_query` once
        enabled) unreachable.
        """
        control_actor = self.control_credential()
        secret = self._actor_secret(control_actor)
        document = self._call(lambda: self._control_service.control_capabilities(secret))
        return document.get("capabilities", {}).get("audit_query", {}).get("status", "unavailable")

    def _audit_surface_absent(self, operation: str, reason: str) -> SurfaceAbsent:
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
        secret = self._actor_secret(actor)
        return self._call(lambda: self._control_service.audit_query(secret, dict(request)))

    # port v1.8
    def audit_visibility_lag_ms(self) -> int:
        control_actor = self.control_credential()
        secret = self._actor_secret(control_actor)
        document = self._call(lambda: self._control_service.control_capabilities(secret))
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
    # directly -- `MitateDataService.open_session` (the SAME `auth.
    # CredentialStore.authenticate` call `HttpService.authenticate` itself
    # makes first, `service.py`'s own `open_session`) then a `Capability
    # Error` denial, mirroring `http.py::post_audit_query`'s own second
    # step -- rather than a mere authentication-surface fallback: this
    # in-process plug has no ASGI `Request` to route through the real
    # handler with, but it can call the exact same authenticate entry
    # point the real handler's own body calls. No declare-first `Surface
    # Absent` gate for `control_plane` here: every application this
    # adapter's own `provision_application` (above) provisions is
    # constructed with `FoundationConfig(control_plane_status="enabled")`
    # unconditionally -- a fixed fact of this adapter's own harness
    # construction, never a live-varying declaration the way `audit_
    # query`'s own status is.
    def audit_query_on_data_plane_host(
        self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        # Fix-round F-4 (disclosed limit, CONDITIONS.md C-09 limit (c)):
        # `MitateDataService.open_session` reaches the SAME `auth.
        # CredentialStore.authenticate` call `HttpService.authenticate`
        # itself makes first -- a real product-code call, not hand-
        # written. `request_id` is not threaded through this in-process
        # call (this harness call has no ASGI `Request` to read one from).
        secret = self._actor_secret(actor)
        self._call(lambda: self._service.open_session(secret))
        # Unreached by any currently-registered adapter: this foundation's
        # application-only `auth.CredentialStore` never recognizes a
        # control/audit credential's id/secret -- a genuinely separate
        # store from the control-plane one (`control_auth.
        # ControlCredentialStore`) -- so `open_session` above always
        # raises AUTH_INVALID first. The SECOND step below, unlike the
        # first, is HAND-WRITTEN, not a call into a real product
        # function: `http.py::post_audit_query`'s own second step (`raise
        # CapabilityError("audit evidence query requires control/audit
        # authority this peer does not expose here")`) is written inline
        # in that HTTP handler's own body, with no separate importable
        # product-code callable this in-process plug could invoke instead
        # -- unlike r2db-api's own `DataService.deny_unsupported`, a real,
        # reusable product method this port revision's r2db plug calls
        # directly. This message is a literal copy of that inline string,
        # disclosed as a limit (CONDITIONS.md C-09 limit (c)) rather than
        # left to look like a real call.
        native = CapabilityError("audit evidence query requires control/audit authority this peer does not expose here")
        raise ConformanceDenial(code=self.classify(native), adapter=self.name, native_type=type(native).__name__) from native

    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    # pre-1.6.0 topology-declaration method this adapter once implemented
    # here is removed -- the port's own `surfaces_cohosted` free function
    # is now surfaces-derived only (both peers declare 1.6.0
    # unconditionally).

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
        return self._call(lambda: self._service.open_session(handle.secret))

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

    def select_eq(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any, *, limit: int | None = None
    ) -> list[dict]:
        filters = [Filter(field, "eq", value)] if field is not None else None
        # port v1.12 (L7-21): `limit` maps directly onto `session.read()`'s
        # own pre-existing `limit` keyword (`cell.py::ApplicationCell.read`,
        # unchanged by this WP -- `None` -> that method's own default,
        # `config.max_result_rows`, exactly as every pre-v1.12 caller here
        # already observed).
        return self._call(lambda: session.read(entity, fields=list(select), filters=filters, limit=limit))

    def attempt_filter(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
    ) -> list[dict]:
        # Same real `session.read()` entry point `select_eq` above already
        # uses, generalized to an arbitrary operator -- an operator this
        # peer does not implement (`contains`/`matches`/`is_null`, all
        # declared `unsupported` in its own `structured_query` capability
        # entry) is presented here exactly as a real client attempting it
        # would be, and whatever `cell.py::_where` itself produces is
        # returned, never fabricated.
        filters = [Filter(field, operator, value)]
        # port v1.12 (L7-21): additional predicates appended to the SAME
        # real `filters` list `session.read()` already accepts
        # (`len(filters)` is this peer's OWN `query_complexity` metric,
        # `cell.py::_bind_filters`) -- never a second query.
        if extra_predicates:
            filters.extend(Filter(f, o, v) for f, o, v in extra_predicates)
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
        # session.read_page() already re-checks authorization on every
        # call (cell.py ApplicationRuntime.__authorize -> assert_active),
        # so a revoked/disabled/unavailable session correctly denies here
        # too.
        #
        # port v1.18 (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-4):
        # a single unbounded `session.read(entity)` silently truncated to
        # this deployment's own `max_result_rows` bound once a collection
        # held more rows than that (C-30's own concurrent-insert node
        # inserts a 6th row past the isolated surface's own `max_result_
        # rows=5`) -- `limit` omitted walks the entry point's own default
        # page (design D-2b.3), which stays within ANY positive deployment
        # bound while costing roughly one request per `max_result_rows`
        # rows rather than one per row (a `limit=1` walk would multiply
        # this suite's own rate budget by the row count and collide with
        # `max_requests_per_minute` on the `full` idempotency leg). A
        # page count that outruns the rows actually
        # counted, plus one, means the cursor stopped advancing; that is
        # this adapter's own bug, not a rate-limit condition, so it is
        # raised here rather than left to surface as a misleading
        # `LIMIT_EXCEEDED`.
        def op() -> int:
            total = 0
            cursor = None
            pages = 0
            while True:
                rows, cursor = session.read_page(entity, cursor=cursor)
                total += len(rows)
                pages += 1
                if pages > total + 1:
                    raise AssertionError(
                        f"count({entity!r}) did not terminate: {pages} pages for {total} rows"
                    )
                if cursor is None:
                    break
            return total
        return self._call(op)

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

    def catalog_document(self, session) -> "Mapping[str, Any] | str":
        # Phase 6 WP-3 (design D-3): `application_catalog: enabled` --
        # `ApplicationRuntime.catalog()` (`cell.py`, inherited by
        # `ApplicationDeveloper` too) is now a real, public operation.
        # Shape mirrors `http.py::get_catalog`'s own response exactly
        # (`CatalogDocument`: `application_scope` + `entities`) -- never a
        # second, independently-built dict.
        def op() -> Mapping[str, Any]:
            return {"application_scope": session.principal.application_id, "entities": session.catalog()}
        return self._call(op)

    # port v1.10 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
    # V1.md section 6.1 item 3, D-3). Presents the contract's own
    # `fields`/`field_types` -- CONTRACT vocabulary words (`string`/
    # `integer`/`number`/`boolean`/`object`/`array`/`json`), verbatim and
    # PARTIAL where the caller gave a partial `field_types` -- to this
    # peer's real `session.create_collection()`, the same real entry
    # point `create_entity` above already uses. This method never fills
    # in `json` for an undeclared name itself (mirrors `conformance_
    # adapter_r2db.py`'s identical method and its own reasoning: D-3(ii)'s
    # default is the PEER's own job to apply on a partial request; this
    # in-process plug's real `create_collection` has no partial-fields
    # concept of its own yet, so as of THIS WP it is presented the raw
    # `field_types` mapping AS GIVEN via a synthetic dict -- WP-3 is where
    # this peer's own product code gains the real "partial field_types,
    # server fills json" behavior this method targets). Unreachable as of
    # this WP (declare-first gated at 1.6.0; `cell.py`'s own pre-1.6.0
    # `_FIELD_TYPE_VOCABULARY` (now in `request_vocabulary.py`) is a DIFFERENT five-word set -- `text`/
    # `integer`/`real`/`boolean`/`json`, not the contract's seven -- so a
    # real call presenting `string`/`number`/`object`/`array` today denies
    # with `ValidationError`, surfaced as `VALIDATION_FAILED` by
    # `classify()`); written for WP-3's real eventual shape, not a stub.
    def create_entity_with_declared_types(
        self, session, entity: str, fields: Sequence[str], field_types: Mapping[str, str] | None
    ) -> None:
        # Phase 6 WP-3 (design D-3): `ApplicationCell.create_collection`
        # now carries a REAL, separate `field_types` parameter (the
        # contract's own 7-word vocabulary, written to the declared-type
        # registry) -- `fields` itself stays this peer's own FOUNDATION
        # vocabulary (`cell._FIELD_TYPE_VOCABULARY`, physical/DDL-facing),
        # mapped from the contract word via `field_types.CONTRACT_TYPE_TO_
        # FOUNDATION_TYPE`. This replaces the pre-WP-3 workaround (passing
        # the contract word directly as if it were a foundation type,
        # which only ever worked for the one word the two vocabularies
        # happen to share verbatim, `json`).
        declared = {name: field_types.get(name, "json") if field_types else "json" for name in fields}
        full_fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[contract_type] for name, contract_type in declared.items()}

        def op() -> None:
            if not hasattr(session, "create_collection"):
                raise AuthorizationError("developer authority required")
            session.create_collection(entity, full_fields, field_types=declared)
        self._call(op)

    # port v1.10 (same WP as above). `field_type` is the contract's own
    # seven-word vocabulary word, verbatim.
    def add_field_with_declared_type(self, session, entity: str, field: str, field_type: str) -> None:
        def op() -> None:
            if not hasattr(session, "add_field"):
                raise AuthorizationError("developer authority required")
            session.add_field(entity, field, CONTRACT_TYPE_TO_FOUNDATION_TYPE.get(field_type, field_type), contract_type=field_type)
        self._call(op)

    def schema_operation_with_result(
        self,
        session,
        entity: str,
        operation: str,
        *,
        field: str | None = None,
        field_type: str | None = None,
        fields: Sequence[str] | None = None,
        field_types: Mapping[str, str] | None = None,
        field_constraints: Mapping[str, Mapping[str, Any]] | None = None,
        enum: Sequence[Any] | _EnumClear | None = None,
        nullable: bool | None = None,
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        """port v1.13 (design D-2/D-4/D-5/D-6/D-8, §6.1 items 1-5, 7, 8): one
        general schema-operation primitive. Unlike `r2db-api` (a single
        generic dict-shaped `schema()` dispatcher), this peer's public
        surface is a family of DEDICATED session methods -- `create_
        collection`/`create_entity`, `add_field` -- with no generic
        fallthrough for an operation name neither recognizes at all.
        `create_entity`/`add_field` are real, present entry points this
        method extends with the new keyword args those methods themselves
        gate (mirrors `create_entity_with_declared_types`'s own `field_
        types` kwarg). `alter_field`/`drop_entity` have no session method
        on this peer as of this port revision (confirmed by source
        inspection, `create_unique_index`/`drop_entity` above make the
        identical claim for the schema-mutation surface as a whole) --
        this method raises `SurfaceAbsent` for either UNTIL a future WP
        adds a real `session.alter_field`/`session.drop_entity` method,
        checked via `hasattr` rather than a peer-name branch (the same
        forward-compatible pattern `add_field_with_declared_type` already
        uses for `hasattr(session, "add_field")`), so this method picks up
        that future method automatically with no edit here.

        `enum` is tri-state (port v1.13 追補, `adapter.ENUM_CLEAR`):
        omitted -> no `enum` kwarg is built into `kwargs` at all;
        `ENUM_CLEAR` -> `kwargs["enum"] = None` is set EXPLICITLY; a
        `Sequence` -> `kwargs["enum"] = [...]`, unchanged from before this
        addendum. Disclosed limit (read directly off this peer's own real
        in-process entry point, `mitatedb_api.cell.ApplicationDeveloper.
        add_field`'s keyword signature, `enum=None` default): a plain
        Python keyword call cannot itself distinguish "omitted" from
        "explicitly passed as None" the way a wire-level dict/JSON body
        can -- `session.add_field(..., enum=None)` and `session.add_field
        (...)` (no `enum` kwarg at all) are the identical call from the
        callee's point of view. This adapter still resolves the sentinel
        faithfully as far as its OWN request-shaping goes (the `kwargs`
        dict this method builds is presence/absence-sensitive, exactly
        like every other keyword here); carrying that distinction further,
        into a real behavioral difference on this peer's `add_field` (or a
        future `alter_field`), would require that peer-side signature to
        grow its own tri-state sentinel, which is peer-side territory this
        port change does not reach.
        """
        if operation == "create_entity":
            declared = {name: (field_types or {}).get(name, "json") for name in (fields or [])}
            full_fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[t] for name, t in declared.items()}

            # Phase 9 WP-3b (design D-4(2), C-22 (1)'s own new authorization
            # sub-leg): checked BEFORE `self._call(op)` below, not inside
            # `op()` -- matching `alter_field`/`drop_entity`'s own existing
            # pattern immediately below. WP-1b rework (review point I) used
            # to assume every caller of this method presents a real
            # `developer` session and raised a plain `AssertionError`
            # otherwise ("port-usage error, not a peer denial") -- C-22's
            # own new authorization sub-leg is the first real, INTENTIONAL
            # caller to present a non-developer (`runtime`) session here,
            # specifically to observe that this peer's session-type family
            # has no real per-role entry point for a runtime credential to
            # reach a developer-only schema operation at all (a genuine
            # structural absence, `SurfaceAbsent`, not a port-usage error --
            # `test_c22_dry_run_and_plan.py`'s own `_assert_dry_run_
            # matches_real_refusal` explicitly anticipates and accepts this
            # from BOTH the dry_run and the real probe alike).
            if not hasattr(session, "create_entity"):
                raise SurfaceAbsent(
                    self.name, "schema_operation_with_result(create_entity)",
                    f"no session.create_entity method exists on this session (entity={entity!r})",
                    surface=self.public_operation_callables(),
                    forbidden_parameters=["create_entity"],
                )

            def op() -> Any:
                kwargs: dict[str, Any] = {"field_types": declared}
                if field_constraints:
                    kwargs["field_constraints"] = {k: dict(v) for k, v in field_constraints.items()}
                if dry_run:
                    kwargs["dry_run"] = True
                if plan is not None:
                    kwargs["plan"] = plan
                if budget:
                    kwargs["budget"] = dict(budget)
                if idempotency_key is not None:
                    kwargs["idempotency_key"] = idempotency_key
                return session.create_entity(entity, full_fields, **kwargs)
            result = self._call(op)
        elif operation == "add_field":
            # Phase 9 WP-3b: same reasoning as `create_entity` above -- a
            # `SurfaceAbsent`, not a port-usage `AssertionError`, checked
            # BEFORE `self._call(op)`.
            if not hasattr(session, "add_field"):
                raise SurfaceAbsent(
                    self.name, "schema_operation_with_result(add_field)",
                    f"no session.add_field method exists on this session (entity={entity!r}, field={field!r})",
                    surface=self.public_operation_callables(),
                    forbidden_parameters=["add_field"],
                )

            def op() -> Any:
                kwargs: dict[str, Any] = {}
                if field_type is not None:
                    kwargs["contract_type"] = field_type
                if enum is ENUM_CLEAR:
                    kwargs["enum"] = None
                elif enum is not None:
                    kwargs["enum"] = list(enum)
                if nullable is not None:
                    kwargs["nullable"] = nullable
                if dry_run:
                    kwargs["dry_run"] = True
                if plan is not None:
                    kwargs["plan"] = plan
                if budget:
                    kwargs["budget"] = dict(budget)
                if idempotency_key is not None:
                    kwargs["idempotency_key"] = idempotency_key
                # C-23 (iv)(v): an unrecognized `field_type` (not one of
                # this peer's own seven contract words) must reach
                # `session.add_field` as a VALIDATION_FAILED refusal from
                # the peer itself, not a port-side KeyError raised by this
                # adapter pre-judging the word (adapters do not decide
                # validity on the peer's behalf). `.get(field_type,
                # field_type)` maps only known contract words; an unknown
                # one is passed through UNCHANGED as the foundation-type
                # positional argument, which is itself not a member of
                # `cell._FIELD_TYPE_VOCABULARY` for any real unrecognized
                # word, so `session.add_field` raises `ValidationError` on
                # its own first gate (`cell.py`'s own `add_field`, "field_type
                # not in _FIELD_TYPE_VOCABULARY" check) -- before any
                # idempotency record is written, so a same-key resend
                # after this failure is a genuinely new execution.
                foundation_type = (
                    CONTRACT_TYPE_TO_FOUNDATION_TYPE.get(field_type, field_type)
                    if field_type is not None else "json"
                )
                return session.add_field(entity, field, foundation_type, **kwargs)
            result = self._call(op)
        elif operation == "alter_field":
            if not hasattr(session, "alter_field"):
                raise SurfaceAbsent(
                    self.name, "schema_operation_with_result(alter_field)",
                    "no session.alter_field method exists on this peer as of this port revision "
                    f"(requested: entity={entity!r}, field={field!r})",
                    surface=self.public_operation_callables(),
                    forbidden_parameters=["alter_field", "enum", "nullable"],
                )

            def op() -> Any:
                kwargs: dict[str, Any] = {}
                if enum is ENUM_CLEAR:
                    kwargs["enum"] = None
                elif enum is not None:
                    kwargs["enum"] = list(enum)
                if nullable is not None:
                    kwargs["nullable"] = nullable
                if dry_run:
                    kwargs["dry_run"] = True
                if plan is not None:
                    kwargs["plan"] = plan
                if budget:
                    kwargs["budget"] = dict(budget)
                if idempotency_key is not None:
                    kwargs["idempotency_key"] = idempotency_key
                return session.alter_field(entity, field, **kwargs)
            result = self._call(op)
        elif operation == "drop_entity":
            if not hasattr(session, "drop_entity"):
                raise SurfaceAbsent(
                    self.name, "schema_operation_with_result(drop_entity)",
                    f"no session.drop_entity method exists on this peer as of this port revision (entity={entity!r})",
                    surface=self.public_operation_callables(),
                    forbidden_parameters=["drop", "destroy"],
                )

            def op() -> Any:
                kwargs: dict[str, Any] = {"destructive": destructive}
                if confirmation is not None:
                    if confirmation is VALID_CONFIRMATION:
                        def probe() -> None:
                            self._call(lambda: session.drop_entity(entity, destructive=True))
                        kwargs["confirm"] = self._resolve_confirmation(confirmation, probe=probe, legacy_token=True)
                    else:
                        kwargs["confirm"] = confirmation
                if dry_run:
                    kwargs["dry_run"] = True
                if plan is not None:
                    kwargs["plan"] = plan
                if idempotency_key is not None:
                    kwargs["idempotency_key"] = idempotency_key
                return session.drop_entity(entity, **kwargs)
            result = self._call(op)
        else:
            # WP-1b rework (review point I): an operation name none of
            # `create_entity`/`add_field`/`alter_field`/`drop_entity`
            # recognizes has no session method AT ALL on this peer's
            # dedicated-method-family surface -- a structural absence, not
            # a peer denial this adapter may fabricate by inventing a
            # `ConformanceDenial(code="CAPABILITY_UNSUPPORTED", ...)` no
            # real dispatch ever produced. Raised the same way `alter_
            # field`/`drop_entity` above raise it for their own genuinely-
            # absent surfaces.
            raise SurfaceAbsent(
                self.name, f"schema_operation_with_result({operation!r})",
                f"no session method exists on this peer for operation {operation!r} -- only create_entity/"
                f"add_field/alter_field/drop_entity are recognized (entity={entity!r})",
                surface=self.public_operation_callables(),
                forbidden_parameters=[operation],
            )

        if isinstance(result, int) or result is None:
            return {"revision": (str(result) if result is not None else None), "descriptor": None, "plan": None, "request_id": None}
        if isinstance(result, Mapping):
            rev = result.get("revision")
            return {
                "revision": str(rev) if rev is not None else None,
                "descriptor": result.get("descriptor"),
                "plan": result.get("plan"),
                "request_id": result.get("request_id"),
            }
        rev = getattr(result, "revision", None)
        return {
            "revision": str(rev) if rev is not None else None,
            "descriptor": getattr(result, "descriptor", None),
            "plan": getattr(result, "plan", None),
            "request_id": getattr(result, "request_id", None),
        }

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

        # Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06): a `filters`
        # value on an "insert" attempt is now ALSO routed to `transact()`
        # below, not silently dropped -- `session.insert()` (the plain-
        # mutation branch further down) has no parameter position for a
        # `where`/`filters` clause at all, so silently ignoring it here
        # would hide whatever the peer's own real dispatcher does with an
        # insert-plus-filter shape, exactly the failure mode this
        # function's own pre-existing comment on `expected_revision`/
        # `unique_key` already rejects ("an adapter that denies this
        # without ever presenting it to the peer hides whatever the peer's
        # own dispatcher actually does with it").
        #
        # Phase 8 WP-1b (R-A 監督裁定 2026-09-06): `operation == "update"`
        # is now ALSO routed to `transact()` when a filter is present, for
        # the identical structural reason -- `session.update()` (the
        # dedicated real entry point the plain-mutation branch below
        # would otherwise use) has NO `operations[]` wrapping at all
        # (its own request dict is `{"collection":..., "values":...,
        # "filters":...}`, real depth 3 for an ordinary scalar filter
        # value), so it sits at a STRUCTURALLY SHALLOWER depth than the
        # real wire shape a real HTTP client presents for the identical
        # request (`http.py::post_mutate`'s own `_mutation_item` always
        # builds `{"operations": [{"type": "update", "collection":...,
        # "values":..., "filters":...}]}`, and dispatches through this
        # SAME `transact()` -- real depth 5 for the identical scalar
        # filter value, MEASURED, `_check_operation_depth`'s own
        # counting: request(1)->operations list(2)->operation dict(3)
        # ->filters list(4)->predicate-as-dict(5)). Routing this
        # in-process plug's own "update"+filter attempt through the SAME
        # `transact()` entry point the HTTP plug's real wire dispatch
        # already uses makes `test_c05_limit_declaration_agreement.py::
        # _drive_operation_depth`'s own update+where recipe sit at the
        # IDENTICAL real depth on every one of the 4 plugs (contract-
        # level meaning agreement, P-6) -- exactly the same rationale as
        # the pre-existing "insert"+filter routing immediately above,
        # generalized to the class of operation the new recipe uses.
        # Corrected 2026-09-07 (裁定 2, 監督裁定 2026-09-07; supersedes the
        # WP-1a rework comment this replaces, which the review found
        # factually wrong -- its single-line `grep -rn 'attempt_mutation(
        # .*"update"'` regex only matches a call whose `"update"` literal
        # sits on the SAME source line as `attempt_mutation(`, so it
        # silently missed every multi-line call (the dominant style in
        # this repository) and undercounted). Real measurement (AST walk
        # of every `conformance-tests/*.py` file, every `Call` node whose
        # callee is `attempt_mutation`, keeping calls whose `where_field`
        # keyword is present and not the literal `None`, then narrowing
        # the `operation` argument to "update" either from its own string
        # literal or -- for `test_c12_capability_agreement.py:95` only --
        # from the single enclosing `elif operation == "update":` branch,
        # a purely static narrowing that needs no capability-document
        # knowledge; script kept at
        # {scratchpad}/ast_scan_where_field2.py): a real, non-`None`
        # `where_field` on an "update" attempt occurs at TWELVE call
        # sites across FOUR files, not "two" in "one, fully-gated file":
        # `test_c05_limit_declaration_agreement.py:371,379`,
        # `test_c12_capability_agreement.py:95`,
        # `test_c17_declaration_agreement.py:283`, and
        # `test_c18_revision_precondition_semantics.py:81,124,145,190,
        # 209,294,326,337` (a further call, `test_c18_...py:360`, carries
        # a real `where_field` but is a "delete", which this `if` never
        # routes here in the first place -- `operation in ("insert",
        # "update")` -- so it is excluded from this tally as irrelevant
        # to this branch, not missed).
        #
        # Of those twelve, `test_c12_capability_agreement.py:95` is the
        # one that actually matters for this change: it is NOT gated
        # behind `revision_preconditions` at all (that guard is
        # `test_c18`'s own, not `test_c12`'s) and it IS a positive
        # control that must observe a real, successful, non-fabricated
        # affected-row count (`:125-130`'s `assert affected and affected
        # >= 1`) -- exactly the call this fix's `dispatched_op` change
        # above (裁定 1) makes correct again (it was silently returning a
        # constant `1` via `len(results)` before this fix, which this
        # positive control could not distinguish from a real update). The
        # eight `test_c18` call sites remain gated behind
        # `_revision_preconditions_enabled(adapter)` (this peer declares
        # `revision_preconditions: unavailable`, unchanged by this WP),
        # so all eight still take the early-return branch to
        # `_assert_expected_revision_is_capability_unsupported_and_
        # state_unchanged` and never reach this dispatcher's success path
        # on this peer; `test_c05:371,379` and `test_c17:283` are
        # unaffected by 裁定 1 (`test_c05` exercises `operation_depth`, a
        # count-blind LIMIT_EXCEEDED probe; `test_c17:283` -- see its own
        # call site -- is itself a denial expectation, not a
        # success-path count assertion). `wp1b-report.md`'s "設計への疑義
        # 2" repeated the same undercounted grep conclusion and is
        # corrected the same way in this WP's report.
        if expected_revision is not None or unique_key is not None or (
            operation in ("insert", "update") and filters is not None
        ):
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

            # Phase 8 WP-1 rework 2 (裁定 1, 監督裁定 2026-09-07): return the
            # real number of rows affected (port `adapter.py`'s own
            # `attempt_mutation` docstring (`adapter.py::ConformanceAdapter.attempt_mutation`): "return the number of
            # rows affected"), not `len(results)` (= the number of batch
            # OPERATIONS, always 1 here since this dispatcher only ever
            # submits a single-item batch). `results[0]` is exactly the
            # dict `ApplicationCell.transact`'s own pass-2 execution loop
            # appends for this one operation (`cell.py`'s own
            # `insert_in_transaction`/`update_in_transaction`/
            # `delete_in_transaction` call sites) -- `{"rowid": ...}` for
            # "insert" (always exactly 1 row), `{"updated": n}` for
            # "update", `{"deleted": n}` for "delete" (both backends'
            # own `cursor.rowcount`/`RETURNING`-derived real count, never
            # fabricated by this adapter). "upsert" never reaches this
            # `return` at all -- `ApplicationCell._plan_operation` raises
            # `CapabilityError` for it during `transact()`'s own pass-1
            # validation (this peer has no upsert execution path), which
            # `self._call` below translates to `ConformanceDenial` before
            # `dispatched_op` could ever produce a value.
            def dispatched_op() -> int:
                result = session.transact([item])[0]
                if operation == "update":
                    return result["updated"]
                if operation == "delete":
                    return result["deleted"]
                return 1
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

    def _mutation_result_to_mapping(self, results: Sequence[Any], items: Sequence[Mapping[str, Any]], *, dry_run: bool) -> Mapping[str, Any]:
        """Shared by `attempt_mutation_with_result`/`attempt_batch_with_
        result` (port v1.13): normalizes `session.transact()`'s own
        per-item results list the same way `attempt_batch_with_addresses`'
        `op()` already sums real per-item outcomes, plus the new `dry_run`/
        `plan`/`budget`/`request_id` outcomes -- observed via a dict-shaped
        result item where present (`.get(..., default)`), never assumed."""
        affected = 0
        for item, result in zip(items, results):
            if item["type"] == "insert":
                affected += 1
            elif isinstance(result, Mapping):
                affected += result.get("updated", result.get("deleted", 0))
        envelope = results[-1] if results and isinstance(results[-1], Mapping) else {}
        return {
            "affected": affected,
            "assigned_addresses": None,
            "committed": envelope.get("committed", not dry_run),
            "plan": envelope.get("plan"),
            "request_id": envelope.get("request_id"),
        }

    def attempt_mutation_with_result(
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
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        transaction: str | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        """port v1.13 (design D-4/D-6): always routed through `session.
        transact()` (the same real atomic dispatcher `attempt_batch_with_
        addresses` uses), never through the plain `session.insert`/
        `.update`/`.delete` methods `_attempt_mutation_outcome`'s own
        fast-path branches use -- `dry_run`/`plan`/`budget` are request-
        unit keywords on the request as a whole, and `transact()` is this
        peer's one entry point that has ever taken such a keyword
        (`request_id`, pre-existing). port v1.13 追補: `destructive`/
        `confirmation` follow the IDENTICAL `VALID_CONFIRMATION` declare-
        and-echo protocol `attempt_batch_with_result`'s own per-operation
        loop already applies to `BatchOperation.destructive`/`.confirmation`
        below -- needed for C-22's `_confirm_probe` (destructive delete
        under dry_run). port v1.13 追補 2 (C-22 leg (10)): `transaction`
        carries the contract's PRE-EXISTING `MutationRequest.transaction`
        key through to `transact()` the SAME way `dry_run`/`plan`/`budget`
        already are -- written for this peer's own real eventual entry
        point (mirrors this class's `create_entity_with_declared_types`/
        `add_field_with_declared_type` convention: real shape, not a
        stub), defaulting to `None` (omitted, byte-compatible with every
        pre-addendum caller). WP-1 addendum (C-25 (4)): `idempotency_key`
        is carried through on `item`, exactly like `attempt_batch_with_
        addresses`'s own per-operation loop already places its folded
        value -- this peer's real `transact()` reads it off each item, not
        off a request-level keyword."""
        filters = [Filter(where_field, "eq", where_value)] if where_field is not None else None
        item: dict[str, Any] = {"type": operation, "collection": entity, "values": dict(values or {})}
        if expected_revision is not None:
            item["expected_revision"] = expected_revision
        if unique_key is not None:
            item["unique_key"] = unique_key
        if idempotency_key is not None:
            # port v1.11 (design D-6.7 C-07 (ii)): `_plan_operation`'s own
            # `_TRANSACT_*_KEYS` excess-key check (cell.py) already
            # recognizes this key on this peer's per-operation item shape
            # and refuses it with a real, present `CapabilityError` before
            # execution (`idempotency: unavailable`) -- carried through
            # exactly like `expected_revision`/`unique_key` above, never
            # interpreted by this adapter.
            item["idempotency_key"] = idempotency_key
        if filters is not None:
            item["filters"] = filters
        if destructive:
            # `destructive` is only ever meaningful when true (mirrors
            # `attempt_batch_with_addresses`'s identical `if op.destructive:`
            # gate above).
            item["destructive"] = True
        # V2b-wire (C-06): `confirm` is set whenever the caller supplies a
        # `confirmation`, INDEPENDENT of `destructive` -- identical
        # rationale and identical VALID_CONFIRMATION sentinel resolution as
        # `attempt_batch_with_addresses`'s own per-operation loop above.
        if confirmation is not None:
            if confirmation is VALID_CONFIRMATION:
                probe_item = dict(item)
                probe_item["destructive"] = True

                def probe(_probe_item=probe_item) -> None:
                    self._call(lambda: session.transact([dict(_probe_item)]))

                peer_confirm = self._resolve_confirmation(confirmation, probe=probe, legacy_token=True)
                item["confirm"] = peer_confirm
            else:
                item["confirm"] = confirmation
        kwargs: dict[str, Any] = {}
        if dry_run:
            kwargs["dry_run"] = True
        if plan is not None:
            kwargs["plan"] = plan
        if budget:
            kwargs["budget"] = dict(budget)
        if transaction is not None:
            kwargs["transaction"] = transaction

        def op() -> Sequence[Any]:
            return session.transact([item], **kwargs)

        results = self._call(op)
        return self._mutation_result_to_mapping(results, [item], dry_run=dry_run)

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
        #
        # port v1.13 (design §6.1 "port docstring に書く限界" item (v)):
        # folded through the shared `fold_batch_idempotency_key`, exactly
        # like `attempt_batch_with_result` below -- never each op's own
        # raw `idempotency_key`, which would silently reach the peer as
        # "whichever op the loop below builds last" rather than enforcing
        # the uniform-or-absent rule that function exists for.
        idempotency_key = fold_batch_idempotency_key(operations)
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
            if idempotency_key is not None:
                # port v1.11 (design D-6.7 C-07 (ii)): `_plan_operation`'s
                # own `_TRANSACT_*_KEYS` excess-key check (cell.py) already
                # refuses ANY unrecognized operation-dict key -- including
                # this one -- with a real, present `CapabilityError`
                # BEFORE this operation's own row is ever built (`idempotency:
                # unavailable`). Carried through unevaluated, exactly like
                # `expected_revision`/`unique_key` above. port v1.13: the
                # folded request-level value (see method docstring), not
                # `op.idempotency_key` -- identical on every item in this
                # batch by construction.
                item["idempotency_key"] = idempotency_key
            items.append(item)

        def op() -> int:
            results = session.transact(items)
            return len(results)
        affected = self._call(op)
        return affected, None

    def attempt_batch_with_result(
        self,
        session,
        entity: str,
        operations: Sequence[BatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """port v1.13: `attempt_batch_with_addresses`'s exact request shape
        (identical per-item construction, including the VALID_CONFIRMATION
        declare-and-echo protocol and the folded `idempotency_key`),
        extended with the same request-level `dry_run`/`plan`/`budget`
        top-level `transact()` keywords `attempt_mutation_with_result`
        establishes."""
        idempotency_key = fold_batch_idempotency_key(operations)
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
            if op.confirmation is not None:
                if op.confirmation is VALID_CONFIRMATION:
                    probe_item = dict(item)
                    probe_item["destructive"] = True

                    def probe(_probe_item=probe_item) -> None:
                        self._call(lambda: session.transact([dict(_probe_item)]))

                    peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token=True)
                    item["confirm"] = peer_confirm
                else:
                    item["confirm"] = op.confirmation
            if idempotency_key is not None:
                item["idempotency_key"] = idempotency_key
            items.append(item)

        kwargs: dict[str, Any] = {}
        if dry_run:
            kwargs["dry_run"] = True
        if plan is not None:
            kwargs["plan"] = plan
        if budget:
            kwargs["budget"] = dict(budget)

        def op() -> Sequence[Any]:
            return session.transact(items, **kwargs)

        results = self._call(op)
        return self._mutation_result_to_mapping(results, items, dry_run=dry_run)

    def attempt_cross_entity_batch(self, session, operations: Sequence[ScopedBatchOperation]) -> int:
        # P35 WP-2/WP-3 (design docs/design/PHASE35_CROSS_ENTITY_AND_
        # CONTRACT_130_V1.md section 2/3): `cross_entity_mutation` is now
        # declared `partial` (`operations: insert/update/delete`,
        # `unsupported: upsert`), backed by the SAME `transact()` dispatcher
        # `attempt_batch_with_addresses` above already uses -- the only
        # difference here is that each operation carries its OWN
        # `collection`, read from `op.entity`, rather than one shared
        # `entity` argument for the whole call. `transact()`'s own two-pass
        # restructuring (R-1) validates every operation across every named
        # entity before executing any of them, so this single real call is
        # what gives C-16 its atomicity/validation-ordering observations --
        # never split into several single-entity calls this adapter
        # stitches together itself.
        #
        # port v1.13 (design §6.1 "port docstring に書く限界" item (v)):
        # folded through the shared `fold_batch_idempotency_key`, exactly
        # like `attempt_cross_entity_batch_with_result` below -- never each
        # op's own raw `idempotency_key`.
        idempotency_key = fold_batch_idempotency_key(operations)
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"type": op.operation, "collection": op.entity, "values": dict(op.values or {})}
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            if op.where_field is not None:
                item["filters"] = [Filter(op.where_field, "eq", op.where_value)]
            if op.destructive:
                item["destructive"] = True
            # Same V2b-wire independence (C-06) as `attempt_batch_with_
            # addresses` above: `confirmation` is set whenever supplied,
            # independent of `destructive`.
            if op.confirmation is not None:
                if op.confirmation is VALID_CONFIRMATION:
                    # The probe always presents `destructive: True` and the
                    # SAME real cross-entity entry point (`session.
                    # transact`) this outer batch is itself presented to --
                    # never a per-entity substitute -- so the phrase read
                    # back is genuinely the one this exact request would
                    # need.
                    probe_item = dict(item)
                    probe_item["destructive"] = True

                    def probe(_probe_item=probe_item) -> None:
                        self._call(lambda: session.transact([dict(_probe_item)]))

                    peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token=True)
                    item["confirm"] = peer_confirm
                else:
                    item["confirm"] = op.confirmation
            if idempotency_key is not None:
                # port v1.11 (design D-6.7 C-07 (ii)): same real
                # `_TRANSACT_*_KEYS` excess-key rejection as `attempt_
                # batch_with_addresses` above -- this dispatcher is the
                # identical `session.transact` entry point. port v1.13:
                # the folded request-level value (see method docstring),
                # not `op.idempotency_key`.
                item["idempotency_key"] = idempotency_key
            items.append(item)

        # m-1 (phase 3.5 WP-3 review): the real summed `affected` -- 1 per
        # insert, plus each update/delete's own real `updated`/`deleted`
        # row count from `transact()`'s own per-item result -- matching
        # both the port's own docstring ("return the whole unit's affected
        # count") and this method's real HTTP sibling
        # (`conformance_adapter_mitatedb_http.py`'s `_cross_mutate`/
        # `http.py::post_cross_entity_mutate`'s identical computation).
        # `len(results)` (this method's own prior revision) undercounts
        # any update/delete matching more than one row -- it counts
        # OPERATIONS, not rows affected. Deliberately NOT applied to
        # `attempt_batch_with_addresses` above: that method's own
        # `affected`/`assigned_addresses` come from `DataService.mutate_
        # result`'s real `MutationResult.affected` (r2db-api's own
        # sibling) or this peer's own pre-existing `len(results)`
        # convention (C-17's `test_assigned_addresses_membership_holds_
        # when_mixed_in_one_batch` already depends on that exact
        # per-operation-affects-exactly-one-row shape) -- changing it
        # there is out of this review's scope.
        def op() -> int:
            results = session.transact(items)
            affected = 0
            for item, result in zip(items, results):
                if item["type"] == "insert":
                    affected += 1
                elif isinstance(result, dict):
                    affected += result.get("updated", result.get("deleted", 0))
            return affected
        return self._call(op)

    def attempt_cross_entity_batch_with_result(
        self,
        session,
        operations: Sequence[ScopedBatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """port v1.13: `attempt_cross_entity_batch`'s exact request shape,
        extended with the same request-level `dry_run`/`plan`/`budget`/
        (folded) `idempotency_key` machinery `attempt_batch_with_result`
        uses -- `cross_entity_mutation: partial` is real on this peer, so
        these new fields are genuinely reachable here once `dry_run`/
        `request_budget` flip."""
        idempotency_key = fold_batch_idempotency_key(operations)
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"type": op.operation, "collection": op.entity, "values": dict(op.values or {})}
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            if op.where_field is not None:
                item["filters"] = [Filter(op.where_field, "eq", op.where_value)]
            if op.destructive:
                item["destructive"] = True
            if op.confirmation is not None:
                if op.confirmation is VALID_CONFIRMATION:
                    probe_item = dict(item)
                    probe_item["destructive"] = True

                    def probe(_probe_item=probe_item) -> None:
                        self._call(lambda: session.transact([dict(_probe_item)]))

                    peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token=True)
                    item["confirm"] = peer_confirm
                else:
                    item["confirm"] = op.confirmation
            if idempotency_key is not None:
                item["idempotency_key"] = idempotency_key
            items.append(item)

        kwargs: dict[str, Any] = {}
        if dry_run:
            kwargs["dry_run"] = True
        if plan is not None:
            kwargs["plan"] = plan
        if budget:
            kwargs["budget"] = dict(budget)

        def op() -> Sequence[Any]:
            return session.transact(items, **kwargs)

        results = self._call(op)
        outcome = self._mutation_result_to_mapping(results, items, dry_run=dry_run)
        outcome.pop("assigned_addresses", None)
        return outcome

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

    def query_with_budget(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str | None,
        value: Any,
        *,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """port v1.13 (design D-6): `budget` is a QueryRequest top-level
        keyword on `session.read()`, exactly like `limit` (port v1.12)
        already is there.

        C-25 (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_
        VERIFICATION_V1.md D-7, supervisor ruling on the query path):
        `ApplicationCell.read()` itself is a bare `list[dict]` with no slot
        a `request_id` could ever occupy, so this peer's own runtime gains
        a second, additive entry point -- `session.read_with_result(...)`
        (WP-3e), same arguments as `read()`, returning a contract-shaped
        `{"items": [...], "next_page": ..., "request_id": ...}` dict --
        instead of `read()` growing that shape itself. Detected via
        `hasattr`, the same capability-detection convention this file
        already uses for `create_collection`/`add_field`/`create_entity`/
        `alter_field`/`drop_entity`: while WP-3e has not landed on a given
        checkout, the session has no `read_with_result` attribute at all
        and this falls straight through to the pre-existing `read()` path
        below, where `request_id` stays `None` -- never fabricated on the
        peer's behalf (M-1 convention)."""
        filters = [Filter(field, "eq", value)] if field is not None else None
        kwargs: dict[str, Any] = {}
        if budget:
            kwargs["budget"] = dict(budget)
        if hasattr(session, "read_with_result"):
            result = self._call(lambda: session.read_with_result(entity, fields=list(select), filters=filters, **kwargs))
            return {"items": list(result.get("items", [])), "revisions": result.get("revisions"), "request_id": result.get("request_id")}
        result = self._call(lambda: session.read(entity, fields=list(select), filters=filters, **kwargs))
        if isinstance(result, Mapping):
            # Structurally has a place for `revisions`/`request_id` --
            # observed, not assumed absent (M-1 convention). Not exercised
            # by any currently-registered call (`session.read()` returns a
            # bare list today), kept for the real eventual shape a future
            # WP may give it.
            return {"items": list(result.get("items", [])), "revisions": result.get("revisions"), "request_id": result.get("request_id")}
        return {"items": result, "revisions": None, "request_id": None}

    def attempt_filter_with_result(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[Mapping[str, Any]] | None = None,
        page_size: int | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """port v1.16 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        §7 段 (9)): `attempt_filter`'s own `filters` construction, presented
        to `session.read_with_result` (`cell.py::ApplicationRuntime.read_with_result`) together with that
        SAME method's pre-existing `order_by`/`limit`/`budget` keywords --
        all three already live there (unchanged by this WP), exactly as
        `query_with_budget` above already presents `budget` alone to the
        same real entry point (including its own `hasattr` fallback to the
        pre-`read_with_result` `session.read` for a checkout where WP-3e
        has not landed)."""
        filters = [Filter(field, operator, value)]
        if extra_predicates:
            filters.extend(Filter(f, o, v) for f, o, v in extra_predicates)
        kwargs: dict[str, Any] = {}
        if order_by:
            kwargs["order_by"] = list(order_by)
        if page_size is not None:
            kwargs["limit"] = page_size
        if budget:
            kwargs["budget"] = dict(budget)
        if hasattr(session, "read_with_result"):
            result = self._call(lambda: session.read_with_result(entity, fields=list(select), filters=filters, **kwargs))
            return {"items": list(result.get("items", [])), "request_id": result.get("request_id")}
        result = self._call(lambda: session.read(entity, fields=list(select), filters=filters, **kwargs))
        if isinstance(result, Mapping):
            return {"items": list(result.get("items", [])), "request_id": result.get("request_id")}
        return {"items": result, "request_id": None}

    def operation_catalog_document(self, session) -> bytes:
        """port v1.17 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        D-5, §7.1 item 2): the SAME `ApplicationRuntime.operation_catalog`
        authorization/rate gate `http.py::get_operation_catalog` goes
        through, followed by the identical packaged-bytes read this in-
        process plug has no HTTP handler to delegate to -- see `mitatedb_
        api.operation_catalog.load_operation_catalog_bytes`'s own
        docstring for why both paths read the same source and can never
        silently re-encode it differently."""
        self._call(lambda: session.operation_catalog())
        return load_operation_catalog_bytes()

    def query_page(
        self,
        session,
        entity: str,
        select: Sequence[str],
        *,
        where: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[tuple[str, str]] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> tuple[list[dict], str | None]:
        """port v1.18 (design docs/design/PHASE11_KEYSET_PAGING_V1.md
        D-2b.4): calls the runtime's own cursor-carrying entry point,
        `session.read_page(...)`, directly (`cell.py::ApplicationRuntime.
        read_page`), passing `cursor` verbatim -- `cell.py::
        ApplicationCell.read_page`'s own body decodes and executes a
        non-`None` cursor (design D-2b.1); this adapter fabricates
        nothing on its own. `order_by` is the SAME wire-shaped
        `[{"field":..., "direction":...}]` list `_bind_order_by` already
        accepts (`cell.py::ApplicationCell._bind_order_by`)."""
        filters = [Filter(f, op, v) for f, op, v in where] if where else None
        order = [{"field": f, "direction": d} for f, d in order_by] if order_by else None
        kwargs: dict[str, Any] = {}
        if page_size is not None:
            kwargs["limit"] = page_size
        if budget:
            kwargs["budget"] = dict(budget)
        rows, next_page = self._call(lambda: session.read_page(
            entity, fields=list(select), filters=filters, order_by=order, cursor=cursor, **kwargs
        ))
        return list(rows), next_page

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
            # WP-2 (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2b.4):
            # the cursor-carrying counterpart of `read` above -- `http.py`'s
            # own `post_query` and this file's own `query_page` (port
            # v1.18) both call it now. Same list-maintenance discipline as
            # `read_with_result` immediately below (this file's own module-
            # level comment: pinned to match `ApplicationRuntime`/
            # `ApplicationDeveloper`'s real public methods mechanically).
            ApplicationRuntime.read_page,
            # Phase 9 WP-3e (design D-7 / 裁定 C-25 (A)): the contract-
            # shaped, request_id-carrying counterpart of `read` above --
            # same isolated surface, same argument-passing convention
            # (`query_with_budget` above calls it the same way `read` is
            # called elsewhere in this file). A genuine additional public
            # method on `ApplicationRuntime`, not a variant dispatch of
            # `read` itself, so it gets its own entry here (this file's
            # own module-level comment: this list is pinned to match
            # `ApplicationRuntime`/`ApplicationDeveloper`'s real public
            # methods mechanically).
            ApplicationRuntime.read_with_result,
            ApplicationRuntime.update,
            ApplicationRuntime.delete,
            ApplicationRuntime.transact,
            ApplicationRuntime.capabilities,
            # m-2 (independent WP-3 review): `schema_revision()`, added so
            # the HTTP surface's `SchemaOperationResult.revision` can
            # report a real, observable value instead of a hardcoded
            # placeholder.
            ApplicationRuntime.schema_revision,
            # Phase 6 WP-3 (design D-3): `application_catalog` flipped to
            # `enabled` -- `catalog()` is a new, real public method, same
            # commit.
            ApplicationRuntime.catalog,
            # Phase 11 WP-3 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
            # D-5): `operation_catalog()` is a new, real public method,
            # same commit as `GET /v1/operation-catalog` (`http.py`) and
            # port v1.17 `operation_catalog_document()` -- see this list's
            # own module-level comment above.
            ApplicationRuntime.operation_catalog,
            ApplicationDeveloper.create_collection,
            ApplicationDeveloper.create_entity,
            ApplicationDeveloper.add_field,
            # Phase 9 WP-3a (design docs/design/
            # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2
            # (5)): `alter_field` is a new, real public method, same commit
            # as `constraint_declarations` flipping to `enabled` -- see
            # this list's own module-level comment above (`tests/
            # test_conformance_public_surface_coverage.py` pins this list
            # to match `ApplicationDeveloper`'s real public methods
            # mechanically).
            ApplicationDeveloper.alter_field,
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
                control_actor.secret, handle.credential_ref, True))
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
