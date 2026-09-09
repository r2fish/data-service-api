"""Composition root for the CCR-14 control-plane HTTP surface: `build_control_app`.

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.6, R-1 (independent process, separate listen address by default -- bind
is an operator decision this module does not make), R-2/R-3 (dedicated pool,
dedicated pepper, `r2dbsvc_controlplane` role), R-9 (capability status is a
*deployer* declaration, injected by `r2db_api.main` from
`R2DB_CONTROL_PLANE_STATUS` -- untouched by this WP), §5's WP-4 row, and §8
m-10 (no module-level `app` here yet -- WP-5 places it in the same commit
that flips the application-plane's own `control_plane` declaration to
`enabled`, so this surface is never deployable-but-undeclared).

**Deployment default (R-1)**: this process is meant to run separately from
`r2db_api.main:app` (the application-plane process) -- its own listener, its
own bind address, chosen by the operator's runbook, not by this module.
Co-locating both apps behind one server process is permitted (design R-1's
own SI-00 boundary evidence list -- separate auth stores/DB roles/`Authority
Topology` registration already make that safe), but nothing here assumes it.

**Deployment authority (R-9)**: whether the application-plane process
*declares* `control_plane: enabled` is that process' own composition root's
job (`r2db_api.main`, reading `R2DB_CONTROL_PLANE_STATUS`) -- this module
has no say in that declaration and does not need to know it exists. The
authority for "is a control plane actually reachable" in a separated
deployment is this surface's own `GET /control/v1/capabilities`, which
`ControlPlaneService.capabilities` already answers unconditionally
(`control_plane: enabled` is hardcoded there -- if this process is running
at all, its own control plane is, by definition, enabled).

Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work
order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1;
REWORK ROUND, supervisor ruling 2026-09-05, rulings-q4-wp12-rework.md
sec.2): `surfaces`, `audit_visibility_lag_ms`, and the coalescing window
this process declares are no longer read from env vars -- they are
DB-side declarations read from `r2dbsvc_registry.platform_declarations`
and `pg_db_role_setting` (migration `0008`). `R2DB_DATA_BASE_URL`/`R2DB_
CONTROL_BASE_URL`/`R2DB_AUDIT_STATEMENT_TIMEOUT_MS`/`R2DB_AUDIT_IDLE_
TIMEOUT_MS` are REJECTED outright if still defined, whatever their value
(F-1/F-2, inside `build_control_app` -- runs first).

**Where the DB-side checks run, and why (design SS3.7 control-plane 1-8;
REWORK ROUND -- supersedes the previous round's lifespan-deferred shape)**:
the previous round of this module ran these checks inside ASGI `_lifespan`,
deferred out of `build_control_app()` itself, specifically to preserve that
function's own pre-Q4 zero-network contract. The supervisor's rework
ruling REJECTED that shape: design SS3.7's own "起動シーケンス" already
requires these checks to run as part of composition-root startup, and this
composition root is explicitly ALLOWED to become network-dependent at
`build_control_app()` call time (unlike WP-1's other module, `r2db_api.
main.build_app`, which already was network-dependent pre-Q4 for an
unrelated reason -- `_load_registry_rows` -- and so never needed this
carve-out to begin with). `build_control_app()` now runs the DB-side
declaration read (F-8/F-3/F-3c/F-4/F-4b) and the writer-role double-check
(F-13/F-7/F-9/F-10/F-11) SYNCHRONOUSLY, before constructing `service` at
all -- `surfaces`/`audit_visibility_lag_ms`/`audit_coalescing_window_ms`
are passed straight into `assemble_control_stack(...)`'s constructor
arguments, never assigned onto `service` after the fact (the previous
round's `service._surfaces = ...`/etc. reach-in is REMOVED entirely: there
is no longer any private-field mutation from this module into `service`).
`test_control_http.py::test_build_control_app_returns_asgi_app_without_
connecting` (and any other test relying on a zero-network `build_control_
app()`) is REWRITTEN by this rework round to use `assemble_control_stack(
...)` directly with explicit injected values instead -- the env-driven
`build_control_app(env)` builder is now exercised ONLY by this repository's
own real-PostgreSQL tests (`tests/test_ops_declarations.py`-adjacent
fixtures), never by a zero-network unit test.

Environment variable contract (design SS5's WP-4 row / SS1 R-2/R-3/R-7,
updated Q4 WP-1):

    R2DB_CONTROLPLANE_DSN                 required -- `r2dbsvc_controlplane`
                                           role DSN against `r2dbsvc_platform`
    R2DB_CONTROL_CREDENTIAL_PEPPER        required -- control-credential
                                           verifier HMAC pepper (R-2)
    R2DB_CREDENTIAL_PEPPER                required -- see the note below;
                                           the design's own env-var table
                                           calls this one conditional
                                           ("存在すれば pepper 同値検査"),
                                           but this composition root departs
                                           from that reading (documented
                                           deviation, WP-4 implementation
                                           report) -- see `_require`'s call
                                           site below
    R2DB_CONTROL_LIMIT_APPLICATIONS                    optional, default
                                                        `ControlPlaneLimits.
                                                        applications`
    R2DB_CONTROL_LIMIT_CREDENTIALS_PER_APPLICATION     optional, default
                                                        `ControlPlaneLimits.
                                                        credentials_per_
                                                        application`
    R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE     optional, default
                                                        `ControlPlaneLimits.
                                                        control_requests_
                                                        per_minute`
    R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE       optional, default
                                                        `ControlPlaneLimits.
                                                        audit_requests_
                                                        per_minute` (Phase 4
                                                        WP-2(b), design D-5)
                                                        -- `audit_query`'s
                                                        OWN pre-auth window,
                                                        never shared with
                                                        the class above.
    R2DB_CONTROL_LIMIT_REQUEST_BYTES                   optional, default
                                                        `ControlPlaneLimits.
                                                        request_bytes`
                                                        (1_048_576, Phase 4
                                                        ledger closure L4-10)
                                                        -- was previously
                                                        unwired here (the
                                                        dataclass default was
                                                        the only source);
                                                        `create_control_app`
                                                        derives BOTH the
                                                        declared limit and
                                                        the ASGI enforcement
                                                        bound from this SAME
                                                        `ControlPlaneLimits.
                                                        request_bytes` value
                                                        (R-7's "宣言値と
                                                        enforce 値が同一
                                                        ソースから出る"
                                                        rule), mirroring
                                                        MitateDB-api's
                                                        `MITATEDB_CONTROL_
                                                        REQUEST_BYTES_LIMIT`
                                                        (`control_
                                                        composition.py`).
    R2DB_AUDIT_DSN                        optional (Phase 4 WP-2(b), design
                                           D-5) -- the `r2dbsvc_auditreader`
                                           role DSN (migration `0007_
                                           application_audit.sql` SS1.3),
                                           read-only over BOTH `control_
                                           audit` and `application_audit`.
                                           Unset means `audit_query` stays
                                           declared `unavailable` (the
                                           route still exists and still
                                           authenticates, answering
                                           `CAPABILITY_UNSUPPORTED`).
    R2DB_PLATFORM_SCHEMA                  optional, default `r2dbsvc_
                                           registry` -- identical escape
                                           hatch to `r2db_api.main`'s own
                                           (see that module's docstring);
                                           a real deployment never sets this
    R2DB_PLATFORM_POOL_SIZE               optional -- per-store pool cap,
                                           same knob `r2db_api.main` and
                                           `credential_store.py`'s classes
                                           already read; computed from `env`
                                           here (not left to each store's own
                                           `os.environ`-reading default) for
                                           the exact reason `r2db_api.main.
                                           build_app` does the same -- see
                                           that function's own comment

REMOVED (Q4 WP-1, rejected outright if still defined -- see
`reject_removed_timeout_env`/`reject_removed_surface_env`, called inside
`build_control_app`): `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`, `R2DB_AUDIT_IDLE_
TIMEOUT_MS`, `R2DB_DATA_BASE_URL`, `R2DB_CONTROL_BASE_URL`.

**Deviation from the design's env-var table (`R2DB_CREDENTIAL_PEPPER`)**:
design SS5's WP-4 row describes this variable as present-if-configured, used
only for `validate_control_pepper_separation`'s equality check. That framing
holds for `ops.py`'s control-credential subcommands (which never touch the
`credentials` table at all -- `R2DB_CREDENTIAL_PEPPER` is genuinely optional
there). It does not hold here: `ControlPlaneService.issue_credential`/
`rotate_credential`/`set_credential_enabled` operate on *application*
credentials too (`PostgresCredentialStore`, via `PostgresControlBackend`),
and `PostgresCredentialStore.__init__` unconditionally raises `ValueError`
without a pepper -- there is no way to construct the store this composition
root needs without one. Beyond that constructor requirement, the value
itself must be the *same* pepper the running `r2db_api.main` process uses:
a control-plane-issued application credential's verifier is computed with
this pepper and has to authenticate later against the data-plane process,
which verifies with its own `R2DB_CREDENTIAL_PEPPER`. So this module treats
it as required, not optional -- verified against `PostgresCredentialStore`'s
actual constructor before writing this, not assumed from the design
document's own summary table (WP-4 implementation report records this as a
supervisor-reviewable deviation, not a silent one).

**Module-level `app` (design SS8 m-10, WP-5 flip)**: this file now ends with
`app = build_control_app()`, the same pattern `r2db_api.main` already
establishes (`app = build_app()`) -- placed in the exact same single commit
that flips the application-plane's own `control_plane` capability
declaration to `enabled` (`main.py`'s `R2DB_CONTROL_PLANE_STATUS` handling),
per the CCR-14 single-commit rule (design SS5): this control-plane surface
was never deployable-but-undeclared even for one commit. Importing this
module now reads `os.environ` immediately, exactly like `r2db_api.main`
already does -- any caller that needs to import this module without a real
control-plane environment configured (this repository's own tests) must set
one up first, via `pytest.MonkeyPatch`, before the first import, the same
established pattern `test_credential_persistence.py`'s `main_module` fixture
already uses for `r2db_api.main` (see `test_control_http.py`'s own
`control_main_module` fixture).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Mapping

import psycopg
from starlette.types import ASGIApp

from .audit_query import DECLARED_COALESCING_WINDOW_MS
from .control_http import create_control_app
from .control_plane import ControlPlaneService, PostgresControlBackend
from .credential_store import (
    DEFAULT_SCHEMA,
    PostgresApplicationRegistry,
    PostgresAuditQueryStore,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
    validate_control_pepper_separation,
)
from .limits import ControlPlaneLimits, ResourceLimits
from . import platform_declarations
from .platform_declarations import (
    check_role_connection_limits,
    check_writer_role_timeouts,
    derive_visibility_lag_ms,
    read_declared_role_timeouts,
    read_platform_declarations,
    reject_removed_surface_env,
    reject_removed_timeout_env,
    require_control_surface_declared,
)

_DEFAULT_LIMITS = ControlPlaneLimits()
_CONNECT_TIMEOUT_S = 5


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to start r2db_api.control_main:build_control_app")
    return value


def _optional_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Same degrade-to-default discipline as `r2db_api.main._optional_int`
    (this module's own composed-`env`-mapping counterpart, not `os.environ`
    directly -- see that function's docstring for why): an unset, empty, or
    unparsable value falls back to `default` rather than raising.
    """
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def assemble_control_stack(
    *,
    controlplane_dsn: str,
    app_pepper: str,
    control_pepper: str,
    schema: str = DEFAULT_SCHEMA,
    pool_size: int | None = None,
    limits: ControlPlaneLimits | None = None,
    audit_dsn: str | None = None,
    audit_reader_pool_size: int | None = None,
    surfaces: dict[str, Any] | None = None,
    audit_visibility_lag_ms: int = 0,
    audit_coalescing_window_ms: int = DECLARED_COALESCING_WINDOW_MS,
    audit: "PostgresControlAuditSink | None" = None,
    process_ceiling: int = 1,
) -> tuple[ControlPlaneService, tuple[PostgresApplicationRegistry, PostgresCredentialStore, PostgresControlCredentialStore, PostgresControlAuditSink, PostgresAuditQueryStore | None]]:
    """WP-5 round-2 review (MINOR-3): the 4-Postgres-store + `ControlPlaneService`
    assembly core, shared by `build_control_app` below AND the WP-5
    conformance HTTP adapter (`conformance_adapter_r2db_http.py`) -- the
    adapter's own reason for needing this factored out at all: it must
    periodically rebuild `ControlPlaneService` to reset the in-memory R-7
    rate window, which means it needs a closeable handle back to the 4
    stores this function constructs.

    Q4 phase WP-1 rework round (design D-1(b)/D-2(e), rulings-q4-wp12-
    rework.md sec.2): NEVER computes `audit_visibility_lag_ms`/`surfaces`
    internally -- callers pass the fully-resolved values straight through
    (`build_control_app` below derives both from the DB-side declarations
    and the writer-role dual check BEFORE calling this function; the r2db
    HTTP conformance adapter passes its own fixed constant/injected value,
    since its own control stack deliberately never reads the DB-side
    declaration at all, design SS3.11 point 4).

    `audit`: an already-constructed `PostgresControlAuditSink`, OPTIONAL --
    `build_control_app` constructs this sink itself, BEFORE calling this
    function, so it can borrow a connection from that sink's own pool (login
    role = the actual `control_audit` writer role) to run the writer-role
    dual check ahead of constructing `service` (rework round: no `service.
    _audit_visibility_lag_ms = ...`-style post-construction mutation any
    longer). When omitted (every other caller, e.g. the conformance
    adapter), this function constructs its own, exactly as before.

    Validates pepper separation (R-2) unconditionally -- every caller gets
    this check, not just `build_control_app`; the adapter's own two
    peppers are genuinely distinct (`conformance_adapter_r2db_http.py`'s
    `_control_pepper`/`_control_app_pepper`), so this call passes there too,
    it does not merely skip the check.

    Returns `(service, stores)` -- `stores` is `(applications, credentials,
    control_credentials, audit, audit_reader)`, in the exact order each
    caller's own shutdown/rebuild logic closes them. `audit_reader` is
    `None` whenever `audit_dsn` is not given (D-5 M-4: AUDIT DSN
    unconfigured) -- callers must guard its `close()` accordingly; `audit_
    visibility_lag_ms` is likewise forced to `0` in that case, regardless
    of what the caller passed in (matching this function's own pre-Q4
    behavior). Building the ASGI app itself (`create_control_app(service,
    ...)`) is left to the caller: `build_control_app` below wraps it with a
    real ASGI `lifespan` hook (shutdown-only in this rework round -- see
    this module's own header); the conformance adapter does not drive ASGI
    lifespan at all (see that adapter's own docstring) and calls `create_
    control_app(service)` with no `lifespan` argument, closing `stores`
    directly instead.
    """
    try:
        validate_control_pepper_separation(app_pepper, control_pepper)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    applications = PostgresApplicationRegistry(controlplane_dsn, schema=schema, pool_size=pool_size)
    credentials = PostgresCredentialStore(controlplane_dsn, pepper=app_pepper, schema=schema, pool_size=pool_size)
    control_credentials = PostgresControlCredentialStore(controlplane_dsn, pepper=control_pepper, schema=schema, pool_size=pool_size)
    # Q4 phase WP-1 (design D-1(b)): no timeout kwargs -- `r2dbsvc_
    # controlplane`'s `statement_timeout`/`idle_in_transaction_session_
    # timeout` are now a role setting (migration `0008`), never a
    # per-connection SESSION `SET` this constructor issues. Rework round:
    # accepts an already-built sink from the caller (see this function's
    # own docstring) instead of always constructing a fresh one.
    if audit is None:
        audit = PostgresControlAuditSink(controlplane_dsn, schema=schema, pool_size=pool_size)

    # Phase 4 WP-2(b) (design D-5): the `r2dbsvc_auditreader` read surface
    # -- a genuinely SEPARATE DSN/role from `controlplane_dsn` above (never
    # `r2dbsvc_controlplane`, which migration 0007 grants no access to
    # either audit table at all) and from `credentials`/`applications`'s
    # own roles. `audit_reader`/`audit_visibility_lag_ms` stay at their
    # `ControlPlaneService` defaults (`None`/`0`, i.e. `audit_query`
    # declares `unavailable`) whenever `audit_dsn` is not given -- the
    # route still exists (`control_http.py`'s own unconditional
    # registration), it just answers `CAPABILITY_UNSUPPORTED` (D-5 M-4).
    audit_reader: PostgresAuditQueryStore | None = None
    effective_visibility_lag_ms = 0
    if audit_dsn:
        audit_reader = PostgresAuditQueryStore(audit_dsn, schema=schema, pool_size=audit_reader_pool_size)
        effective_visibility_lag_ms = audit_visibility_lag_ms

    backend = PostgresControlBackend(applications=applications, credentials=credentials, control_credentials=control_credentials)
    service = ControlPlaneService(
        backend, audit=audit, limits=limits or _DEFAULT_LIMITS,
        audit_reader=audit_reader, audit_visibility_lag_ms=effective_visibility_lag_ms,
        audit_coalescing_window_ms=audit_coalescing_window_ms,
        surfaces=surfaces,
        process_ceiling=process_ceiling,
    )
    return service, (applications, credentials, control_credentials, audit, audit_reader)


def build_control_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assemble the control-plane ASGI app from `env` (defaults to `os.environ`).

    Factored out of a module-level `app = build_control_app()` (design SS8
    m-10 -- deliberately not placed in this file yet, see this module's own
    header) so this repository's own tests can exercise the full
    environment-validation and assembly logic -- including the required-env
    and pepper-separation failure paths -- against a real, throwaway-
    provisioned local PostgreSQL platform database.

    Q4 phase WP-1 rework round (rulings-q4-wp12-rework.md sec.2): runs the
    DB-side declaration read (F-8/F-3/F-3c/F-4/F-4b) and the writer-role
    dual check (F-13/F-7/F-9/F-10/F-11) SYNCHRONOUSLY, right here, in this
    exact order, before `service` is ever constructed -- NOT deferred to
    ASGI lifespan startup (the previous round's shape, rejected by the
    supervisor). This mirrors `r2db_api.main.build_app`'s own startup
    sequence (design SS3.7 control-plane 1-8):

    1. required env reads;
    2. reject the four removed env vars (F-1/F-2), whatever their value;
    3. read `platform_declarations` (F-8/F-3/F-4/F-4b/F-5, and, Phase 10
       WP-6a, F-15 for `process_ceilings`), then require `surfaces.control`
       unconditionally (F-3c: this process, by definition, always has a
       control surface to declare -- unlike the data-plane process, whose
       equivalent requirement is conditional on `R2DB_CONTROL_PLANE_
       STATUS`, F-6, `r2db_api.main`-only);
    4. construct the `control_audit` writer sink, then run the writer-role
       dual check on a connection BORROWED FROM THAT SINK'S OWN POOL (login
       role = the actual writer role, design D-1(c)) -- self-role inclusion
       (F-13) first, then this role's own catalog/effective check (F-7/
       F-9/F-10/F-11);
    5. read EVERY declared `audit_writer_roles` role's catalog (not only
       this process' own) to derive `visibility_lag_ms` -- UNCONDITIONALLY
       (rulings-q4-wp12-rework.md sec.2: "control の sibling role catalog
       検査は audit_reader の有無に依らず無条件"), regardless of whether
       `R2DB_AUDIT_DSN` is even configured on this process;
    5b. (Phase 10 WP-4g, supervisor ruling 2026-09-09) F-16, on the same
       borrowed connection: this process' own `r2dbsvc_controlplane` role
       (plus `r2dbsvc_auditreader` too when `R2DB_AUDIT_DSN` is
       configured) must have a real `CONNECTION LIMIT` of `-1` or at
       least its own pool-composition floor -- scoped to exactly the
       role(s) THIS process pools connections against, never the sibling
       data-plane process' own role or any application's;
    6. assemble the rest of the stack via `assemble_control_stack(...)`,
       passing the already-built audit sink and the fully-resolved
       `surfaces`/`audit_visibility_lag_ms`/`audit_coalescing_window_ms` as
       constructor arguments -- never mutated onto `service` afterward.
    """
    env = env if env is not None else os.environ

    controlplane_dsn = _require(env, "R2DB_CONTROLPLANE_DSN")
    control_pepper = _require(env, "R2DB_CONTROL_CREDENTIAL_PEPPER")
    # See this module's header ("Deviation from the design's env-var table")
    # for why this is `_require`d rather than read as optional, unlike
    # `ops.py`'s control-credential-only commands.
    app_pepper = _require(env, "R2DB_CREDENTIAL_PEPPER")

    # Resolved before step 2 (not just before step 3) so F-2's own message
    # can name the REAL configured schema (design amendment 2026-09-05,
    # N-7) rather than this module's `DEFAULT_SCHEMA` -- zero-network, so
    # moving it earlier changes nothing about the startup-sequence design.
    schema = env.get("R2DB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA

    # Step 2 (F-1/F-2): a deployer who left one of these four defined must
    # find out immediately.
    reject_removed_timeout_env(env, names=platform_declarations.REMOVED_TIMEOUT_ENV)
    reject_removed_surface_env(env, names=platform_declarations.REMOVED_SURFACE_ENV, schema=schema)

    # Pepper separation (R-2): validated here, BEFORE the DB-side
    # declaration read below, so this remains a zero-network config check
    # -- exactly where it ran pre-Q4 (inside `assemble_control_stack`,
    # called early). `assemble_control_stack` still re-validates it too
    # (that function's own contract: every caller gets this check, not
    # just this one) -- redundant here, harmless, and keeps `assemble_
    # control_stack` safe to call independently (the conformance adapter
    # never goes through `build_control_app` at all).
    try:
        validate_control_pepper_separation(app_pepper, control_pepper)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    # Phase 10 WP-4e (supervisor ruling 2026-09-09) investigated deriving
    # this default from a declared concurrency ceiling too (mirroring
    # `r2db_api.main`'s data-plane platform pool fix, `role_pool_size`) --
    # this process' own 4 platform-plane stores (`applications`/
    # `credentials`/`control_credentials`/`audit`, all against the SAME
    # `r2dbsvc_controlplane` role) share one hard PostgreSQL `CONNECTION
    # LIMIT 10` (`0006_control_plane_http.sql`). Measured directly against
    # the conformance HTTP adapter's own identical stores (`conformance_
    # adapter_r2db_http.py::self._control_pool_size`, same 4-stores-one-
    # role shape): raising this ceiling does NOT fix a pool-exhaustion
    # timeout (`_RolePool`'s own `acquire_timeout` never fired) -- the
    # measured failure was a REAL `psycopg.OperationalError` ("FATAL: too
    # many connections for role"), a hard PostgreSQL refusal, on the
    # FIRST-ever connection of a brand-new pool. `_RolePool` never shrinks
    # (no idle eviction) -- a larger ceiling only lets this process
    # permanently retain MORE real, cached-idle connections after any
    # historical burst, worsening the real exposure against that same
    # 10-connection budget rather than helping it. Left at the original
    # fixed `4` for this reason -- unlike `r2db_api.main`'s data-plane
    # platform pool (only 2 stores share `r2dbsvc_api`'s own CONNECTION
    # LIMIT 10, and no second, concurrently-alive stack of stores exists
    # for that role the way `isolated_control_surface` builds one here) --
    # see the conformance adapter's own comment for the measured detail.
    # A genuine fix needs either a higher `r2dbsvc_controlplane`
    # `CONNECTION LIMIT` (migration change) or an idle-eviction mechanism
    # on `_RolePool` itself, both outside this WP's own scope (pool
    # SIZING/composition only, not pool LIFECYCLE) -- reported for a
    # separate ruling. `R2DB_PLATFORM_POOL_SIZE` still wins outright when
    # set explicitly.
    pool_size = _optional_int(env, "R2DB_PLATFORM_POOL_SIZE", 4)

    limits = ControlPlaneLimits(
        applications=_optional_int(env, "R2DB_CONTROL_LIMIT_APPLICATIONS", _DEFAULT_LIMITS.applications),
        credentials_per_application=_optional_int(env, "R2DB_CONTROL_LIMIT_CREDENTIALS_PER_APPLICATION", _DEFAULT_LIMITS.credentials_per_application),
        control_requests_per_minute=_optional_int(env, "R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE", _DEFAULT_LIMITS.control_requests_per_minute),
        # Phase 4 WP-2(b) (design D-5, P4-D4 item 8): `audit_query`'s OWN
        # window -- a separate env var, mirroring the 3 lines above, never
        # sharing `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE`.
        audit_requests_per_minute=_optional_int(env, "R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE", _DEFAULT_LIMITS.audit_requests_per_minute),
        # Phase 4 ledger closure L4-10 (work order WP-B3): previously
        # unwired -- `ControlPlaneLimits.request_bytes`'s dataclass default
        # (1_048_576) was the only source, so no deployer could ever change
        # it here (MitateDB-api's `control_composition.py` already wires
        # its own `MITATEDB_CONTROL_REQUEST_BYTES_LIMIT` equivalent).
        # Default is the SAME 1_048_576 (`_DEFAULT_LIMITS.request_bytes`),
        # so leaving this env var unset changes nothing (behavior-preserving).
        request_bytes=_optional_int(env, "R2DB_CONTROL_LIMIT_REQUEST_BYTES", _DEFAULT_LIMITS.request_bytes),
    )
    # Phase 4 WP-2(b) (design D-5): the `r2dbsvc_auditreader` DSN -- OPTIONAL.
    # Unset means `audit_query` stays declared `unavailable` (D-5 M-4); the
    # route is still registered and still authenticates, answering
    # `CAPABILITY_UNSUPPORTED` for a genuinely authorized caller.
    audit_dsn = env.get("R2DB_AUDIT_DSN") or None

    # Step 3 (F-8/F-3/F-3c/F-4/F-4b/F-5): the DB-side declaration read, on
    # a short-lived, dedicated connection (never the writer sink's own
    # pool -- that pool is reserved for step 4's login-role-specific dual
    # check below).
    try:
        _decl_conn = psycopg.connect(controlplane_dsn, connect_timeout=_CONNECT_TIMEOUT_S)
    except psycopg.Error as exc:
        raise RuntimeError(f"could not connect to read {schema}.platform_declarations: {exc}") from exc
    try:
        declarations = read_platform_declarations(
            _decl_conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            migration=platform_declarations.MIGRATION_NUMBER,
        )
    finally:
        _decl_conn.close()
    # F-3c: unconditionally required for THIS process (unlike `r2db_api.
    # main`'s F-6, which is conditional on `R2DB_CONTROL_PLANE_STATUS`).
    require_control_surface_declared(declarations.surfaces, schema=schema, ops_module=platform_declarations.PEER_MODULE)

    surfaces: dict[str, Any] = {
        "data": {"base_url": declarations.surfaces.data_base_url},
        "control": {"base_url": declarations.surfaces.control_base_url},
    }

    # Step 4 (F-13/F-7/F-9/F-10/F-11): construct the writer sink FIRST (so
    # its own pool exists to borrow a login-role-correct connection from),
    # then run the dual check on a connection actually logged in as
    # `r2dbsvc_controlplane`.
    audit = PostgresControlAuditSink(controlplane_dsn, schema=schema, pool_size=pool_size)
    with audit.borrow_connection() as _writer_conn:
        own_catalog = check_writer_role_timeouts(
            _writer_conn, declared_roles=declarations.audit_writer_roles, schema=schema,
            ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
        )

        # Step 5: EVERY declared role's catalog, unconditionally (rework
        # round -- no longer gated on `audit_dsn`/`audit_reader`
        # presence). `pg_db_role_setting` is a world-readable shared
        # catalog (design SS1.5 finding 6): this SAME connection can read
        # any role's entry, not only its own login role's.
        all_catalogs = [own_catalog]
        for role in declarations.audit_writer_roles:
            if role == own_catalog.role:
                continue
            all_catalogs.append(
                read_declared_role_timeouts(
                    _writer_conn, role, ops_module=platform_declarations.PEER_MODULE,
                    migration=platform_declarations.MIGRATION_NUMBER,
                )
            )
        visibility_lag_ms = derive_visibility_lag_ms(all_catalogs)

        # Phase 10 WP-4g (supervisor ruling 2026-09-09, following WP-4f's
        # own `ops verify-declarations` F-16 aggregate check): this
        # process' own startup now ALSO fails fast on F-16, scoped to
        # exactly the role(s) THIS process' own pool composition uses --
        # `r2dbsvc_controlplane` always (`role_classes` always contains
        # `"controlplane"`), plus `r2dbsvc_auditreader` too whenever
        # `R2DB_AUDIT_DSN` is configured (this process then genuinely
        # pools a connection against that role too, via `audit_reader`
        # below) -- never the sibling data-plane process' own `r2dbsvc_
        # api` role, and never any application's runtime/developer role
        # (`application_slugs=()`: this process serves no application at
        # all). Run on this same borrowed connection (login role = the
        # real `r2dbsvc_controlplane` writer role).
        _own_role_classes = {"controlplane"}
        if audit_dsn:
            _own_role_classes.add("auditreader")
        check_role_connection_limits(
            _writer_conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            concurrency=ResourceLimits().concurrency,
            role_classes=frozenset(_own_role_classes), application_slugs=(),
        )

    # Step 6: assemble the rest of the stack -- `surfaces`/`audit_
    # visibility_lag_ms`/`audit_coalescing_window_ms` are already fully
    # resolved constructor arguments; `assemble_control_stack` never
    # mutates `service`'s fields after construction, and neither does this
    # function.
    service, (applications, credentials, control_credentials, audit, audit_reader) = assemble_control_stack(
        controlplane_dsn=controlplane_dsn, app_pepper=app_pepper, control_pepper=control_pepper,
        schema=schema, pool_size=pool_size, limits=limits,
        audit_dsn=audit_dsn, audit=audit,
        surfaces=surfaces, audit_visibility_lag_ms=visibility_lag_ms,
        audit_coalescing_window_ms=declarations.audit_coalescing_window_ms,
        # Phase 10 WP-6a (design D-5(ii), contract 1.8.0): the CONTROL
        # plane's own ceiling -- `declarations.process_ceilings.control`,
        # never `.data` (that one is `r2db_api.main`'s own, a separate
        # process/plane). Drives `ControlPlaneService.capabilities()`'s
        # own `limit_enforcement` mapping for `control_requests_per_
        # minute`/`audit_requests_per_minute`.
        process_ceiling=declarations.process_ceilings.control,
    )

    @asynccontextmanager
    async def _lifespan(_app: Any):
        # Rework round: shutdown-only. Every startup-time DB check now
        # runs synchronously above, inside `build_control_app` itself, so
        # this lifespan hook has nothing left to do before `yield`.
        try:
            yield
        finally:
            # Mirrors `r2db_api.main.build_app`'s own shutdown lifespan:
            # release every pooled connection this process holds. None of
            # these stores registers with `postgres.default_pool_manager`
            # (each owns its own dedicated `_RolePool`, like `PostgresCredentialStore`
            # already does for the application plane) -- so each needs its
            # own explicit `close()`, not a single shared-manager `dispose_all()`.
            applications.close()
            credentials.close()
            control_credentials.close()
            audit.close()
            if audit_reader is not None:
                audit_reader.close()

    return create_control_app(service, lifespan=_lifespan)


# Design SS8 m-10, WP-5 flip: the literal uvicorn/systemd entry point,
# `python -m uvicorn r2db_api.control_main:app` (or any ASGI server pointed
# at this module) -- landed in the same single commit that flips
# `main.py`'s `control_plane` declaration (design SS5's single-commit rule).
#
# Rework round, in-session implementer judgment call (report this as a
# deviation for supervisor review, not a silent choice): `app` is built
# LAZILY, via a PEP 562 module-level `__getattr__`, rather than by a plain
# eager `app = build_control_app()` assignment. This is now REQUIRED
# because `build_control_app()` is no longer zero-network (design SS3.7's
# own startup-sequence checks now run synchronously inside it, per this
# module's own header) -- an eager assignment would mean MERELY IMPORTING
# this module (e.g. `from r2db_api.control_main import assemble_control_
# stack`, which this repository's own `tests/test_audit_query.py` and
# `conformance/conformance_adapter_r2db_http.py` both do at THEIR OWN
# module level, with placeholder env values that -- by both files' own
# existing comments -- were only ever meant to satisfy this previously
# zero-network construction) attempts a real PostgreSQL connection using
# whatever `os.environ` happens to hold at import time. A REAL deployment
# is unaffected: `uvicorn r2db_api.control_main:app` accesses `.app`
# immediately after import, exactly as before -- this changes nothing
# about when a real deployment's `app` is built or when a bad env is
# discovered, and a second access after the first returns the SAME
# already-built object (cached into this module's own namespace on first
# access, below), not a freshly rebuilt one.
# `importlib.reload()` re-executes this module's top-level code against
# its EXISTING namespace dict -- it does NOT clear an attribute that was
# only ever set at RUNTIME (by `__getattr__` below caching into
# `globals()`), since nothing in the top-level source assigns `app`
# directly any longer. Without this explicit `pop`, a test suite that
# reloads this module with a NEW environment after some earlier test
# already triggered a successful `.app` access would silently keep
# serving the OLD, stale app object -- this line is what makes a reload
# behave like a fresh import for this one lazily-cached attribute.
globals().pop("app", None)


def __getattr__(name: str) -> Any:
    if name == "app":
        value = build_control_app()
        globals()["app"] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
