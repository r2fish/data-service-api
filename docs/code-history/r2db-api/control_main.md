# src/r2db_api/control_main.py -- code-comment history (change set 6)

Companion for `src/r2db_api/control_main.py` per `docs/code-history/README.md`.

## CH-0504

- moved from: `src/r2db_api/control_main.py` (`<module>`)
- parent commit: `80fad55`
- kind: docstring

```
Composition root for the CCR-14 control-plane HTTP surface: `build_control_app`.

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
```

## CH-0509

- moved from: `src/r2db_api/control_main.py` (`build_control_app`)
- parent commit: `80fad55`
- kind: comment

```
# Phase 10 WP-4e (supervisor ruling 2026-09-09) investigated deriving
# this default from a declared concurrency ceiling too (mirroring
# `r2db_api.main`'s data-plane platform pool fix, `role_pool_size`) --
# this process' own 4 platform-plane stores (`applications`/
# `credentials`/`control_credentials`/`audit`, all against the SAME
# `r2dbsvc_controlplane` role) share one hard PostgreSQL `CONNECTION
# LIMIT` -- 10 at the time of this measurement (`0006_control_plane_
# http.sql`'s own shipped value); WP-4f's own later migration
# (`0013_role_connection_limits.sql`, L-3 correction, WP-4 integration
# review 2026-09-10) has since raised this to 20 -- see that
# migration's own header for why (4 stores x this same fixed
# `pool_size` 4 = 16, already exceeding the pre-0013 limit of 10 with
# a SINGLE process, no test harness involved). The conclusion below
# (leave `pool_size` at the fixed `4`, do not derive it from declared
# concurrency) is UNCHANGED by that migration -- the actual failure
# mode this comment documents is about pool LIFECYCLE (connections
# never released), not the specific CONNECTION LIMIT number, and 0013
# raising the ceiling does not fix a lifecycle problem, only postpones
# when it bites. Measured directly against the conformance HTTP
# adapter's own identical stores (`conformance_adapter_r2db_http.py::
# self._control_pool_size`, same 4-stores-one-role shape): raising
# `pool_size` does NOT fix a pool-exhaustion timeout (`_RolePool`'s
# own `acquire_timeout` never fired) -- the measured failure was a
# REAL `psycopg.OperationalError` ("FATAL: too many connections for
# role"), a hard PostgreSQL refusal, on the FIRST-ever connection of a
# brand-new pool. `_RolePool` never shrinks (no idle eviction) -- a
# larger `pool_size` only lets this process permanently retain MORE
# real, cached-idle connections after any historical burst, worsening
# the real exposure against the role's own CONNECTION LIMIT (now 20,
# not 10) rather than helping it. Left at the original fixed `4` for
# this reason -- unlike `r2db_api.main`'s data-plane platform pool
# (only 2 stores share `r2dbsvc_api`'s own CONNECTION LIMIT, and no
# second, concurrently-alive stack of stores exists for that role the
# way `isolated_control_surface` builds one here) -- see the
# conformance adapter's own comment for the measured detail. A genuine
# fix needs either a higher `r2dbsvc_controlplane` `CONNECTION LIMIT`
# (0013 is exactly that, and does help in practice -- it just does not
# change the ANALYSIS above, which is about lifecycle, not headroom)
# or an idle-eviction mechanism on `_RolePool` itself, the latter
# outside this WP's own scope (pool SIZING/composition only, not pool
# LIFECYCLE) -- reported for a separate ruling. `R2DB_PLATFORM_
# POOL_SIZE` still wins outright when set explicitly.
```

## CH-0512

- moved from: `src/r2db_api/control_main.py` (`build_control_app`)
- parent commit: `80fad55`
- kind: comment

```
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
```
