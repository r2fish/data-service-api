"""`build_control_service`: the control-plane assembly core (design v1.2
§3 WP-4 row, moved here in WP-5).

Originally written directly inside `main.py` (WP-4) since, at that point,
nothing else needed it. WP-5 adds a second caller -- `control_main.py`'s own
`build_control_app` (the literal `uvicorn mitatedb_api.control_main:app`
entry point) -- and that caller must NOT transitively trigger `main.py`'s
own module-level `app = build_app()` statement merely by importing this
function (that statement demands `MITATEDB_CREDENTIAL_PEPPER`/
`MITATEDB_PLATFORM_DSN`/`MITATEDB_SERVE_APPS` etc., the APPLICATION-plane
process' own required environment, which a control-plane-only process has
no reason to ever set). This function is a NEW file specifically so
`control_main.py` can import it without importing `main.py` at all --
`main.py` itself keeps re-exporting the same name (`from .control_
composition import build_control_service`) purely for the pre-existing
`test_main.py` call sites (`main_module.build_control_service(...)`) that
predate this split; `main.py`'s own module-level `app` never calls it
(unchanged from WP-4 -- `test_main.py::test_build_app_never_references_
the_control_plane_at_all` still fixes that fact against `build_app`'s own
source).
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

import psycopg

from .audit_query import PostgresAuditQueryStore
from .control_credential_store_postgres import PostgresControlCredentialStore
from .control_plane import (ControlPlaneLimits, ControlPlaneService, PostgresApplicationRegistry,
                            PostgresControlBackend, PostgresCredentialRegistry)
from .credential_store_postgres import DEFAULT_SCHEMA, assert_pepper_separation
from . import platform_declarations
from .platform_declarations import (check_writer_role_timeouts, derive_visibility_lag_ms,
                                    read_declared_role_timeouts, read_platform_declarations,
                                    reject_removed_surface_env, reject_removed_timeout_env,
                                    require_control_surface_declared)
from .surfaces import build_surfaces


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to start mitatedb_api's control-plane composition")
    return value


def build_control_service(env: Mapping[str, str] | None = None) -> ControlPlaneService:
    """WP-4/WP-5 (design v1.2 §3 WP-4 row, §5 flip): assembles a real,
    working `control_plane.ControlPlaneService` against PostgreSQL.

    Environment variable contract:

        MITATEDB_CREDENTIAL_PEPPER          required -- shared with
                                             `main.build_app`
        MITATEDB_CONTROL_CREDENTIAL_PEPPER  required -- the control plane
                                             cannot exist without it
        MITATEDB_CONTROLPLANE_DSN           required -- `mitatedbsvc_
                                             controlplane` role DSN against
                                             `mitatedb_platform`
        MITATEDB_PLATFORM_SCHEMA            optional, default
                                             `credential_store_postgres.
                                             DEFAULT_SCHEMA` (same knob
                                             `main.build_app` reads)
        MITATEDB_CONTROL_APPLICATIONS_LIMIT,
        MITATEDB_CONTROL_CREDENTIALS_PER_APPLICATION_LIMIT,
        MITATEDB_CONTROL_REQUESTS_PER_MINUTE_LIMIT,
        MITATEDB_CONTROL_REQUEST_BYTES_LIMIT
                                             optional -- see `control_plane.
                                             ControlPlaneLimits`'s own
                                             defaults when unset.
        MITATEDB_CONTROL_AUDIT_REQUESTS_PER_MINUTE_LIMIT
                                             optional (Phase 4 WP-3(b),
                                             design D-5) -- `audit_query`'s
                                             OWN pre-auth window, never
                                             shared with `MITATEDB_CONTROL_
                                             REQUESTS_PER_MINUTE_LIMIT`.
        MITATEDB_AUDIT_DSN                  optional (Phase 4 WP-3(b),
                                             design D-5) -- the
                                             `mitatedbsvc_auditreader` role
                                             DSN (migration `0005_
                                             application_audit.sql` §1.3),
                                             read-only over BOTH `control_
                                             audit` and `application_audit`.
                                             Unset means `audit_query` stays
                                             declared `unavailable` (the
                                             route still exists and still
                                             authenticates, answering
                                             `CAPABILITY_UNSUPPORTED`).
    """
    env = env if env is not None else os.environ

    # Resolved before the removed-env rejection below (not just before the
    # declarations read) so F-2's own message can name the REAL configured
    # schema (design amendment 2026-09-05, N-7) rather than this module's
    # `DEFAULT_SCHEMA` -- zero-network, so moving it earlier changes
    # nothing about the startup-sequence design.
    schema = env.get("MITATEDB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA

    # Q4 phase (design D-1(d)/D-2(f), §3.7 control-plane steps 1-2): same
    # order/mapping `main.build_app` follows -- checked against `env`,
    # never `os.environ`.
    reject_removed_timeout_env(env, names=platform_declarations.REMOVED_TIMEOUT_ENV)
    reject_removed_surface_env(env, names=platform_declarations.REMOVED_SURFACE_ENV, schema=schema)

    app_pepper = _require(env, "MITATEDB_CREDENTIAL_PEPPER")
    control_pepper = _require(env, "MITATEDB_CONTROL_CREDENTIAL_PEPPER")
    assert_pepper_separation(app_pepper, control_pepper)

    controlplane_dsn = _require(env, "MITATEDB_CONTROLPLANE_DSN")

    # Q4 phase (design §3.7 control-plane steps 4-6): single source of
    # `surfaces`/`audit_coalescing_window_ms`/`audit_writer_roles`.
    # Opened via `psycopg.connect` directly (mirrors `PostgresControl
    # Backend`'s own per-call-connection convention, `control_plane.py`)
    # -- this SAME connection is reused below for the writer-role dual
    # check (F-13/F-7/F-9/F-10/F-11), since it IS the connection this
    # process' own `control_audit` writes go through (`backend`'s own
    # `dsn=controlplane_dsn` below).
    conn = psycopg.connect(controlplane_dsn, connect_timeout=5, autocommit=False)
    try:
        declarations = read_platform_declarations(
            conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            migration=platform_declarations.MIGRATION_NUMBER,
        )
        # monitor ruling 2026-09-05 (design §3.8 F-3c): this IS the
        # control process -- it ALWAYS has a control surface of its own to
        # declare, unconditionally, unlike `main.build_app`'s data-plane
        # check (F-6, which cross-references THAT process' own `*_
        # CONTROL_PLANE_STATUS`). `check_control_surface_consistency`
        # (F-6) is never called here -- it is a data-plane-only check.
        require_control_surface_declared(declarations.surfaces, schema=schema, ops_module=platform_declarations.PEER_MODULE)
        # This process' OWN writer role's self-inclusion (F-13) + dual
        # check (F-7/F-9/F-10/F-11) -- `controlplane_dsn`'s login role IS
        # `mitatedbsvc_controlplane`, the role that writes `control_audit`.
        # `*_api`'s own effective value can only be checked by the
        # data-plane process itself (design §3.11 point 9).
        check_writer_role_timeouts(
            conn, declared_roles=declarations.audit_writer_roles, schema=schema,
            ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
        )
        # D-2(h) 3: control derives `visibility_lag_ms` from EVERY role in
        # `audit_writer_roles` (never a naming-convention-derived sibling)
        # -- read while this connection is still open, reused below by
        # the `audit_dsn` branch instead of opening a second connection.
        writer_catalogs = [
            read_declared_role_timeouts(
                conn, role, ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
            )
            for role in declarations.audit_writer_roles
        ]
    finally:
        conn.close()

    def _limit(name: str, default: int) -> int:
        raw = env.get(name)
        return int(raw) if raw else default

    defaults = ControlPlaneLimits()
    limits = ControlPlaneLimits(
        applications=_limit("MITATEDB_CONTROL_APPLICATIONS_LIMIT", defaults.applications),
        credentials_per_application=_limit(
            "MITATEDB_CONTROL_CREDENTIALS_PER_APPLICATION_LIMIT", defaults.credentials_per_application),
        control_requests_per_minute=_limit(
            "MITATEDB_CONTROL_REQUESTS_PER_MINUTE_LIMIT", defaults.control_requests_per_minute),
        request_bytes=_limit("MITATEDB_CONTROL_REQUEST_BYTES_LIMIT", defaults.request_bytes),
        # Phase 4 WP-3(b) (design D-5, P4-D4 item 8): `audit_query`'s OWN
        # window -- a separate env var, mirroring the 4 lines above, never
        # sharing `MITATEDB_CONTROL_REQUESTS_PER_MINUTE_LIMIT`.
        audit_requests_per_minute=_limit(
            "MITATEDB_CONTROL_AUDIT_REQUESTS_PER_MINUTE_LIMIT", defaults.audit_requests_per_minute),
    )

    applications = PostgresApplicationRegistry(controlplane_dsn, schema=schema)
    credentials_registry = PostgresCredentialRegistry(controlplane_dsn, pepper=app_pepper, schema=schema)
    control_credentials = PostgresControlCredentialStore(controlplane_dsn, pepper=control_pepper, schema=schema)
    # Q4 phase (design D-1(b)): the two writer timeouts are no longer
    # passed here at all -- `mitatedbsvc_controlplane`'s OWN role setting
    # (just dual-checked above) applies to this connection automatically.
    backend = PostgresControlBackend(
        applications=applications, credentials=credentials_registry, control_credentials=control_credentials,
        audit_schema=schema, dsn=controlplane_dsn,
    )

    # Phase 4 WP-3(b) (design D-5): the `mitatedbsvc_auditreader` read
    # surface -- a genuinely SEPARATE DSN/role from `controlplane_dsn`
    # above (never `mitatedbsvc_controlplane`, which migration 0005 grants
    # no access to either audit table at all) and from `credentials`/
    # `applications`'s own roles. `audit_reader`/`audit_visibility_lag_ms`
    # stay at their `ControlPlaneService` defaults (`None`/`0`, i.e.
    # `audit_query` declares `unavailable`) whenever `MITATEDB_AUDIT_DSN`
    # is not given -- the route still exists (`control_http.py`'s own
    # unconditional registration), it just answers `CAPABILITY_UNSUPPORTED`
    # (D-5 M-4). `PostgresAuditQueryStore` opens one connection per call
    # (no pool, no persistent handle to close at shutdown -- mirrors this
    # peer's own established `PostgresApplicationAuditSink`/`Postgres
    # ControlBackend` per-call-connection convention, not r2db-api's own
    # pooled reader).
    audit_dsn = env.get("MITATEDB_AUDIT_DSN") or None
    audit_reader: Optional[PostgresAuditQueryStore] = None
    audit_visibility_lag_ms = 0
    if audit_dsn:
        audit_reader = PostgresAuditQueryStore(audit_dsn, schema=schema)
        # Q4 phase (design D-1(c)/D-2(h) 3): DERIVED (pure function) from
        # the `RoleTimeoutCatalog` rows already read above for EVERY role
        # in `audit_writer_roles` (never a bare constant, an env-sourced
        # value, a naming-convention-derived sibling, or this process' own
        # effective connection alone).
        audit_visibility_lag_ms = derive_visibility_lag_ms(writer_catalogs)

    # Q4 phase (design D-2(e)): `surfaces` comes from the SAME
    # `platform_declarations` read at the top of this function (F-3c/F-5
    # already validated it) -- `MITATEDB_DATA_BASE_URL`/`MITATEDB_
    # CONTROL_BASE_URL` are REMOVED env vars (F-2, rejected above).
    surfaces = build_surfaces(
        data_url=declarations.surfaces.data_base_url,
        control_url=declarations.surfaces.control_base_url,
    )

    return ControlPlaneService(
        backend, limits=limits,
        audit_reader=audit_reader, audit_visibility_lag_ms=audit_visibility_lag_ms,
        surfaces=surfaces,
        # Q4 phase (design D-2(e)): the SAME single-source declaration
        # `main.build_app`'s own `AuditRouter` reads (`platform_
        # declarations.read_platform_declarations`) -- both processes now
        # describe the SAME window, closing the drift design §1.2
        # describes ("別プロセスだから読めない").
        audit_coalescing_window_ms=declarations.audit_coalescing_window_ms,
    )


__all__ = ["build_control_service"]
