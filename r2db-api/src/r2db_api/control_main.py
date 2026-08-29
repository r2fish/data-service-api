"""Composition root for the CCR-14 control-plane HTTP surface: `build_control_app`.

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.6, R-1 (independent process, separate listen address by default -- bind
is an operator decision this module does not make), R-2/R-3 (dedicated pool,
dedicated pepper, `r2dbsvc_controlplane` role), R-9 (capability status is a
*deployer* declaration, injected by `r2db_api.main` from
`R2DB_CONTROL_PLANE_STATUS` -- untouched by this WP), §5's WP-4 row, and §8
m-10 (no module-level `app` here yet -- WP-5 places it in the same commit
that flips the application-plane's `control_plane` declaration to
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

Environment variable contract (design §5's WP-4 row / §1 R-2/R-3/R-7):

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

**Deviation from the design's env-var table (`R2DB_CREDENTIAL_PEPPER`)**:
design §5's WP-4 row describes this variable as present-if-configured, used
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

**No startup DSN reachability check (design §2, by contrast with `r2db_api.
main`'s registry-row validation)**: `r2db_api.main.build_app` connects once
at startup to validate `R2DB_SERVE_APPS` against the platform registry,
because a served application's DSNs are static configuration this process
commits to for its entire lifetime. This control-plane composition root has
no equivalent commitment to validate -- authentication and every operation
below it are already a fresh per-request DB round-trip with no cache
(R-8: "リクエスト毎 DB 参照", `authorization_propagation_bound_ms: 0`), so a
DSN that is unreachable at process start is exactly as fail-closed (`AUTH_
STATE_UNAVAILABLE`/503, never silently permissive) as one that becomes
unreachable five minutes into serving traffic. Adding a startup check here
would only turn one of those two failure timings into a hard crash for no
safety benefit `main.py`'s own serving-set commitment doesn't already need.
`_RolePool.__init__` (postgres.py) does not connect eagerly either --
constructing every store below is itself a zero-network operation, which is
what lets this module's own tests build a full app against a bogus DSN
without needing a reachable PostgreSQL server at all.

**No module-level `app` (design §8 m-10, binding for this WP)**: unlike
`r2db_api.main`, which ends with `app = build_app()`, this file stops at
`build_control_app` itself. Placing a module-level `app = build_control_app()`
here would make this control-plane surface *importable and constructible*
by any composition root (or ASGI server pointed at this module) while the
application-plane's own `control_plane` capability declaration is still
`unavailable` -- exactly the "deployable but undeclared" window the CCR-14
single-commit rule (design §5) exists to prevent. WP-5 places `app = build_
control_app()` here in the same commit that flips that declaration, not
before.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Mapping

from starlette.types import ASGIApp

from .control_http import create_control_app
from .control_plane import ControlPlaneService, PostgresControlBackend
from .credential_store import (
    DEFAULT_SCHEMA,
    PostgresApplicationRegistry,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
    validate_control_pepper_separation,
)
from .limits import ControlPlaneLimits

_DEFAULT_LIMITS = ControlPlaneLimits()


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


def build_control_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assemble the control-plane ASGI app from `env` (defaults to `os.environ`).

    Factored out of a module-level `app = build_control_app()` (design §8
    m-10 -- deliberately not placed in this file yet, see this module's own
    header) so this repository's own tests can exercise the full
    environment-validation and assembly logic -- including the required-env
    and pepper-separation failure paths -- without needing a reachable
    PostgreSQL server at all (constructing every store below is a zero-
    network operation; see the header's note on `_RolePool`).
    """
    env = env if env is not None else os.environ

    controlplane_dsn = _require(env, "R2DB_CONTROLPLANE_DSN")
    control_pepper = _require(env, "R2DB_CONTROL_CREDENTIAL_PEPPER")
    # See this module's header ("Deviation from the design's env-var table")
    # for why this is `_require`d rather than read as optional, unlike
    # `ops.py`'s control-credential-only commands.
    app_pepper = _require(env, "R2DB_CREDENTIAL_PEPPER")
    try:
        validate_control_pepper_separation(app_pepper, control_pepper)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    schema = env.get("R2DB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA
    pool_size = _optional_int(env, "R2DB_PLATFORM_POOL_SIZE", 4)

    limits = ControlPlaneLimits(
        applications=_optional_int(env, "R2DB_CONTROL_LIMIT_APPLICATIONS", _DEFAULT_LIMITS.applications),
        credentials_per_application=_optional_int(env, "R2DB_CONTROL_LIMIT_CREDENTIALS_PER_APPLICATION", _DEFAULT_LIMITS.credentials_per_application),
        control_requests_per_minute=_optional_int(env, "R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE", _DEFAULT_LIMITS.control_requests_per_minute),
    )

    applications = PostgresApplicationRegistry(controlplane_dsn, schema=schema, pool_size=pool_size)
    credentials = PostgresCredentialStore(controlplane_dsn, pepper=app_pepper, schema=schema, pool_size=pool_size)
    control_credentials = PostgresControlCredentialStore(controlplane_dsn, pepper=control_pepper, schema=schema, pool_size=pool_size)
    audit = PostgresControlAuditSink(controlplane_dsn, schema=schema, pool_size=pool_size)

    backend = PostgresControlBackend(applications=applications, credentials=credentials, control_credentials=control_credentials)
    service = ControlPlaneService(backend, audit=audit, limits=limits)

    @asynccontextmanager
    async def _lifespan(_app: Any):
        try:
            yield
        finally:
            # Mirrors `r2db_api.main.build_app`'s own shutdown lifespan:
            # release every pooled connection this process holds. None of
            # these 4 stores registers with `postgres.default_pool_manager`
            # (each owns its own dedicated `_RolePool`, like `PostgresCredentialStore`
            # already does for the application plane) -- so each needs its
            # own explicit `close()`, not a single shared-manager `dispose_all()`.
            applications.close()
            credentials.close()
            control_credentials.close()
            audit.close()

    return create_control_app(service, lifespan=_lifespan)


# Design §8 m-10 (binding for this WP): no `app = build_control_app()` here.
# WP-5 places that line in the same single commit that flips the
# application-plane's `control_plane` capability declaration to `enabled`
# (design §5's single-commit rule) -- until then, this composition root is
# reachable only by explicitly calling `build_control_app()` (this
# repository's own tests do; no deployment entry point does).
