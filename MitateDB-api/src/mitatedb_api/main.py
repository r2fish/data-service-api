"""Composition root: `mitatedb_api.main:app` is what uvicorn starts (WP-3,
docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-7/R-8).

Independent implementation (R-2's closing paragraph: no code sharing
between peers) of the SAME general shape r2db-api's own composition root
(`r2db_api.main`, read-only reference per the task brief) already
established for this repository: no HTTP control plane exists yet
(control_plane stays `unavailable`, R-7 -- the flip is WP-5), so the set of
applications this process serves is declared by static *configuration*
(environment variables), not discovered from an in-band registration
endpoint. Startup failure policy mirrors that same precedent: missing
configuration, a served slug that is not registered, not enabled, or not
yet provisioned in the platform registry are all import-time (`build_app`)
failures -- loud, not a silently-reduced serving set.

Environment variable contract:

    MITATEDB_CREDENTIAL_PEPPER            required -- application
                                           credential digest HMAC pepper
                                           (`credential_store_postgres.
                                           PostgresCredentialStore`)
    MITATEDB_CONTROL_CREDENTIAL_PEPPER     optional -- the future control-
                                           credential pepper (WP-4/5,
                                           unused by anything this WP
                                           mounts). Read here only so
                                           `assert_pepper_separation` can
                                           run at startup (R-7's own
                                           instruction) and catch an
                                           operator who copy-pasted the
                                           same secret-manager value into
                                           both names, even before the
                                           control-plane process that
                                           would actually use it exists.
    MITATEDB_PLATFORM_DSN                 required -- `mitatedbsvc_api`
                                           role DSN against
                                           `mitatedb_platform`
    MITATEDB_PLATFORM_SCHEMA              optional, default
                                           `mitatedb_registry` -- not part
                                           of a real deployment's own
                                           configuration surface; exists
                                           solely so this repository's own
                                           tests (throwaway-prefixed
                                           schema names, R-4/R-8) can point
                                           `build_app` at their own
                                           rewritten schema.
    MITATEDB_PLATFORM_POOL_SIZE           optional, default
                                           `pool.DEFAULT_MAX_SIZE` (20,
                                           matching `mitatedbsvc_api`'s own
                                           `CONNECTION LIMIT 20`, migration
                                           `0002_registry_and_functions.
                                           sql`) -- the WP-3 completion
                                           condition's own bounded pool
                                           (`pool.BoundedConnectionPool`).
    MITATEDB_SERVE_APPS                   required -- comma-separated
                                           application ids this process
                                           serves
    MITATEDB_APP_<ID_UPPER>_RUNTIME_DSN   required per served id
    MITATEDB_APP_<ID_UPPER>_DEVELOPER_DSN required per served id
    MITATEDB_MAX_*                        optional -- see
                                           `config.FoundationConfig.
                                           from_env` (batch/result/field/
                                           filter/request-byte/schema-
                                           object bounds)

Startup failure policy: every `RuntimeError` below is an intentional,
loud "refuse to start" -- there is no partial-startup mode.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Mapping

import psycopg
from psycopg import sql
from starlette.types import ASGIApp

from .audit import AuditSink
from .backend_postgres import PostgresBackend
from .cell import ApplicationCell
from .config import FoundationConfig
from .credential_store_postgres import DEFAULT_SCHEMA, PostgresCredentialStore
from .http import HttpService, create_app
from .identifiers import validate_identifier
from .pool import BoundedConnectionPool, pool_size_from_env

_PLATFORM_CONNECT_TIMEOUT_S = 5


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to start mitatedb_api.main:app")
    return value


def _parse_served_apps(raw: str) -> list[str]:
    ids = [item.strip() for item in raw.split(",")]
    ids = [item for item in ids if item]
    if not ids:
        raise RuntimeError("MITATEDB_SERVE_APPS must name at least one application id")
    for app_id in ids:
        validate_identifier(app_id, "application_id")
    return ids


def _app_dsn_env_names(application_id: str) -> tuple[str, str]:
    prefix = f"MITATEDB_APP_{application_id.upper()}"
    return f"{prefix}_RUNTIME_DSN", f"{prefix}_DEVELOPER_DSN"


def _load_registry_rows(platform_dsn: str, schema: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """One short-lived, unpooled connection used exactly once at startup to
    validate every served application id against the platform registry --
    deliberately separate from `PostgresCredentialStore`'s own bounded
    pool (that pool exists to serve per-request reads for the process'
    entire lifetime; this is a one-shot startup check with no reason to
    hold a pooled connection open)."""
    validate_identifier(schema, "schema")
    statement = sql.SQL(
        "SELECT application_id, enabled, database_name FROM {table} WHERE application_id = ANY(%s)"
    ).format(table=sql.Identifier(schema, "applications"))
    try:
        conn = psycopg.connect(platform_dsn, connect_timeout=_PLATFORM_CONNECT_TIMEOUT_S)
    except psycopg.Error as exc:
        raise RuntimeError(f"could not connect to MITATEDB_PLATFORM_DSN to validate MITATEDB_SERVE_APPS: {exc}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(statement, [ids])
            rows = cur.fetchall()
    finally:
        conn.close()
    return {row[0]: {"enabled": row[1], "provisioned": row[2] is not None} for row in rows}


def build_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assemble the ASGI app from `env` (defaults to `os.environ`).

    Factored out of module-level `app = build_app()` below so this
    repository's own tests can exercise the full startup-validation and
    assembly logic against a real, throwaway-provisioned local PostgreSQL
    platform without mutating `os.environ` for the whole test process.
    """
    env = env if env is not None else os.environ

    app_pepper = _require(env, "MITATEDB_CREDENTIAL_PEPPER")
    control_pepper = env.get("MITATEDB_CONTROL_CREDENTIAL_PEPPER")
    # R-7: called at startup regardless of whether a control-plane process
    # exists yet on this deployment -- an operator who will eventually run
    # one alongside this process must not be able to configure both
    # peppers identically even before that second process exists.
    from .credential_store_postgres import assert_pepper_separation
    assert_pepper_separation(app_pepper, control_pepper)

    platform_dsn = _require(env, "MITATEDB_PLATFORM_DSN")
    schema = env.get("MITATEDB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA
    ids = _parse_served_apps(_require(env, "MITATEDB_SERVE_APPS"))

    app_dsns: dict[str, tuple[str, str]] = {}
    for application_id in ids:
        runtime_name, developer_name = _app_dsn_env_names(application_id)
        runtime_dsn = env.get(runtime_name)
        developer_dsn = env.get(developer_name)
        if not runtime_dsn or not developer_dsn:
            raise RuntimeError(f"{runtime_name} and {developer_name} are both required for application {application_id!r} named in MITATEDB_SERVE_APPS")
        app_dsns[application_id] = (runtime_dsn, developer_dsn)

    registry = _load_registry_rows(platform_dsn, schema, ids)
    for application_id in ids:
        row = registry.get(application_id)
        if row is None:
            raise RuntimeError(f"application {application_id!r} named in MITATEDB_SERVE_APPS is not registered in the platform registry ({schema}.applications)")
        if not row["enabled"]:
            raise RuntimeError(f"application {application_id!r} named in MITATEDB_SERVE_APPS is disabled in the platform registry")
        if not row["provisioned"]:
            raise RuntimeError(f"application {application_id!r} named in MITATEDB_SERVE_APPS is registered but not yet provisioned (migrations/0003_provision_application.sql)")

    pool_size = pool_size_from_env(env.get("MITATEDB_PLATFORM_POOL_SIZE"))
    platform_pool = BoundedConnectionPool(platform_dsn, max_size=pool_size)
    credentials = PostgresCredentialStore(platform_dsn, pepper=app_pepper, schema=schema, pool=platform_pool)

    config = FoundationConfig.from_env(env)
    audit = AuditSink()

    # Every served application's own `PostgresBackend` (two persistent
    # connections, one per role -- `backend_postgres.PostgresBackend`'s
    # own documented, deliberate choice not to pool data-plane connections
    # this WP, design v1.1 §7 future-work ledger) is built once, eagerly,
    # at startup -- the served set is static configuration for this WP
    # (no in-band `register_application`/`provision_application` exists
    # yet), so there is no "unknown application shows up later" case to
    # handle lazily.
    cells: dict[str, ApplicationCell] = {}
    for application_id in ids:
        runtime_dsn, developer_dsn = app_dsns[application_id]
        backend = PostgresBackend(runtime_dsn, developer_dsn)
        cells[application_id] = ApplicationCell(
            application_id, config, audit, guard=credentials.assert_active, backend=backend
        )

    def _cell_factory(application_id: str) -> ApplicationCell:
        cell = cells.get(application_id)
        if cell is None:
            # A credential authenticated successfully (it belongs to a
            # real, enabled application in the platform registry) but this
            # PROCESS was not configured to serve that application's own
            # data -- a deployment-topology mismatch (this application is
            # served by a DIFFERENT process), not a credential problem.
            # `NotFoundError` mirrors `MitateDataService.open_session`'s
            # own choice for the structurally identical in-process case
            # ("Do not permit an authorization record without a storage
            # boundary.").
            from .errors import NotFoundError
            raise NotFoundError("application is not served by this process")
        return cell

    service = HttpService(credentials, _cell_factory)

    @asynccontextmanager
    async def _lifespan(_app: Any):
        try:
            yield
        finally:
            # Release every connection this process holds on shutdown: the
            # platform registry's bounded pool, and every served
            # application's own two persistent PostgreSQL connections.
            credentials.close()
            for cell in cells.values():
                cell._backend.close()

    return create_app(service, request_bytes_limit=config.max_request_bytes, lifespan=_lifespan)


# WP-5: the real assembly logic now lives in `control_composition.py` (its
# own module docstring explains why: `control_main.py`'s own module-level
# `app = build_control_app()` must be able to reach this function WITHOUT
# transitively importing `main.py` -- and therefore without transitively
# running `main.py`'s own module-level `app = build_app()` below, which
# demands the APPLICATION-plane process' own required environment). This
# name is kept as a re-export purely for this repository's own pre-existing
# `test_main.py` call sites (`main_module.build_control_service(...)`,
# WP-4) -- `build_app`'s own source still never references it at all
# (`test_main.py::test_build_app_never_references_the_control_plane_at_all`
# fixes that against `build_app`'s literal source text, unaffected by
# where the re-exported function's OWN implementation lives).
from .control_composition import build_control_service  # noqa: E402,F401

app = build_app()
