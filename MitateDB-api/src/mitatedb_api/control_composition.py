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

from .application_audit import DEFAULT_AUDIT_IDLE_TIMEOUT_MS, DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
from .audit_query import DEFAULT_COALESCING_WINDOW_MS, PostgresAuditQueryStore
from .control_credential_store_postgres import PostgresControlCredentialStore
from .control_plane import (ControlPlaneLimits, ControlPlaneService, PostgresApplicationRegistry,
                            PostgresControlBackend, PostgresCredentialRegistry)
from .credential_store_postgres import DEFAULT_SCHEMA, assert_pepper_separation

# Phase 4 WP-3(b) (design D-6): "clock-skew margin" -- the third term
# `visibility_lag_ms` sums beyond the two writer-connection timeouts
# (`statement_timeout_ms + idle_in_transaction_session_timeout_ms + this`).
_VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS = 1000


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to start mitatedb_api's control-plane composition")
    return value


def _optional_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-6/
    N-3): same lenient-degrade discipline as `main.py`'s own identical
    helper (an unset/empty/unparsable value silently falls back to
    `default`) -- kept as a SEPARATE, small local copy rather than an
    import from `main.py`, since importing `main.py` here would
    transitively require every APPLICATION-plane env var at import time
    (this module's own docstring explains why `control_main.py` must
    never import `main.py`)."""
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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

    app_pepper = _require(env, "MITATEDB_CREDENTIAL_PEPPER")
    control_pepper = _require(env, "MITATEDB_CONTROL_CREDENTIAL_PEPPER")
    assert_pepper_separation(app_pepper, control_pepper)

    controlplane_dsn = _require(env, "MITATEDB_CONTROLPLANE_DSN")
    schema = env.get("MITATEDB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA

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
    # Phase 4 (design D-6/N-3, work order WP-3(a)): the SAME two env-var
    # names -- and the SAME shared defaults, `application_audit.
    # DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`DEFAULT_AUDIT_IDLE_TIMEOUT_MS`
    # -- `main.build_app` reads for the connection that writes
    # `application_audit`. Both processes must agree, or the visibility-
    # lag basis this WP's own `audit_query` declaration derives from these
    # two values no longer holds for BOTH planes.
    audit_statement_timeout_ms = _optional_int(env, "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS)
    audit_idle_timeout_ms = _optional_int(env, "MITATEDB_AUDIT_IDLE_TIMEOUT_MS", DEFAULT_AUDIT_IDLE_TIMEOUT_MS)
    backend = PostgresControlBackend(
        applications=applications, credentials=credentials_registry, control_credentials=control_credentials,
        audit_schema=schema, dsn=controlplane_dsn,
        audit_statement_timeout_ms=audit_statement_timeout_ms,
        audit_idle_in_transaction_session_timeout_ms=audit_idle_timeout_ms,
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
        # D-6 point 3: DERIVED, never a bare constant -- the SAME two
        # timeouts the writer connections above (and `main.build_app`'s own
        # `application_audit` writer) actually carry, plus a fixed 1s
        # clock-skew margin. Changing either timeout changes this value.
        audit_visibility_lag_ms = audit_statement_timeout_ms + audit_idle_timeout_ms + _VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS

    return ControlPlaneService(
        backend, limits=limits,
        audit_reader=audit_reader, audit_visibility_lag_ms=audit_visibility_lag_ms,
        # Phase 4 WP-3(b) (r2db-api WP-2(b) review item H): derived from the
        # SAME single-source constant `audit_query.DEFAULT_COALESCING_
        # WINDOW_MS` (itself derived from `application_audit.DEFAULT_
        # DENIAL_COALESCE_WINDOW_S`) that a data-plane composition root
        # falls back to when it does not override `AuditRouter`'s own
        # `denial_coalesce_window_s` -- see `docs/cloud-run-cloud-sql.md`
        # for the operational note that overriding the data-plane's window
        # requires updating this declaration too (this process cannot read
        # the data-plane process' own live `AuditRouter` -- separate
        # processes).
        audit_coalescing_window_ms=DEFAULT_COALESCING_WINDOW_MS,
    )


__all__ = ["build_control_service"]
