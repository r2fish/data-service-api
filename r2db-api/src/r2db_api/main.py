"""Composition root: `r2db_api.main:app` is what uvicorn/systemd starts.

Design this file implements (docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, P2-D5). Before this
file, nothing in this package assembled a runnable PostgreSQL-backed
process at all -- every existing entry point (`tests/test_http.py`, both
conformance adapters) builds its own throwaway `DataService`/`PostgresCell`
wiring by hand, none of it meant to run as a long-lived deployment. This
module is that missing assembly, reading its entire configuration from the
environment (§0 of the design doc: no HTTP control plane is introduced
here -- CCR-14 is undecided -- application slugs served are declared by
*configuration*, a static control-plane form CCR-14 already anticipates as
legitimate).

Environment variable contract (P2-D5):

    R2DB_CREDENTIAL_PEPPER               required -- verifier HMAC pepper
    R2DB_PLATFORM_DSN                    required -- `r2dbsvc_api` role DSN
                                          against `r2dbsvc_platform`
    R2DB_SERVE_APPS                      required -- comma-separated
                                          application slugs this process
                                          serves
    R2DB_APP_<SLUG_UPPER>_RUNTIME_DSN    required per served slug
    R2DB_APP_<SLUG_UPPER>_DEVELOPER_DSN  required per served slug
    R2DB_POOL_*                          optional -- see `r2db_api.postgres.
                                          SharedPoolManager`
    R2DB_PLATFORM_POOL_SIZE              optional -- platform pool cap
                                          (`r2db_api.credential_store.
                                          PostgresCredentialStore`)
    R2DB_PLATFORM_SCHEMA                 optional, default
                                          `r2dbsvc_registry` -- not part of
                                          the design doc's table; added
                                          solely so this repository's own
                                          tests (which run the real
                                          migration files with `r2dbsvc`
                                          textually replaced by a random
                                          throwaway prefix, to avoid
                                          colliding with anything else in a
                                          shared local cluster) can point
                                          `build_app` at their own rewritten
                                          schema name. A real deployment
                                          never sets this -- the default is
                                          the literal name
                                          `0005_credential_store.sql`
                                          actually creates.

Startup failure policy (P2-D5): missing configuration, an application slug
named in `R2DB_SERVE_APPS` that is not registered in the platform registry,
and a registered-but-disabled slug are all import-time (`build_app`)
failures -- "uzurusaku ochiru" (loudly failing to start) rather than
silently serving a subset. There is no partial-startup mode.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Mapping

import psycopg
from psycopg import sql
from starlette.types import ASGIApp

from .credential_store import DEFAULT_SCHEMA, PostgresCredentialStore
from .http import create_app
from .postgres import PostgresCell, default_pool_manager
from .service import ControlAuthority, DataService

_PLATFORM_CONNECT_TIMEOUT_S = 5


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to start r2db_api.main:app")
    return value


def _optional_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Same degrade-to-default discipline as `r2db_api.postgres._env_int`
    (an unset, empty, or unparsable value silently falls back to `default`
    rather than raising -- pool-tuning knobs like `R2DB_PLATFORM_POOL_SIZE`
    are optional configuration, and a malformed value at startup should
    degrade to a sane default, not crash the process). Not `_env_int`
    itself: that function reads `os.environ` directly, whereas `build_app`
    below accepts an arbitrary `env: Mapping[str, str]` for testability
    (not only the real process environment), so this operates on that
    parameter instead.
    """
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_served_apps(raw: str) -> list[str]:
    slugs = [item.strip() for item in raw.split(",")]
    slugs = [item for item in slugs if item]
    if not slugs:
        raise RuntimeError("R2DB_SERVE_APPS must name at least one application slug")
    return slugs


def _app_dsn_env_names(slug: str) -> tuple[str, str]:
    prefix = f"R2DB_APP_{slug.upper()}"
    return f"{prefix}_RUNTIME_DSN", f"{prefix}_DEVELOPER_DSN"


def _load_registry_rows(platform_dsn: str, schema: str, slugs: list[str]) -> dict[str, dict[str, Any]]:
    """One short-lived, unpooled connection, used exactly once at startup
    to look up `enabled`/`runtime_role`/`developer_role` for every slug
    named in `R2DB_SERVE_APPS` -- deliberately separate from
    `PostgresCredentialStore`'s own pool (that pool exists to serve
    per-request reads for the process' entire lifetime; this is a one-shot
    startup check that has no reason to hold a pooled connection open).
    `schema`/table names are composed via `sql.Identifier`, never string-
    interpolated (D-4), even though both are fixed, code-authored/env-
    configured values here, never client input.
    """
    statement = sql.SQL("SELECT application_slug, enabled, runtime_role, developer_role FROM {table} WHERE application_slug = ANY({slugs})").format(
        table=sql.Identifier(schema, "applications"), slugs=sql.Placeholder()
    )
    try:
        conn = psycopg.connect(platform_dsn, connect_timeout=_PLATFORM_CONNECT_TIMEOUT_S)
    except psycopg.Error as exc:
        raise RuntimeError(f"could not connect to R2DB_PLATFORM_DSN to validate R2DB_SERVE_APPS: {exc}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(statement, [slugs])
            rows = cur.fetchall()
    finally:
        conn.close()
    return {row[0]: {"enabled": row[1], "runtime_role": row[2], "developer_role": row[3]} for row in rows}


def build_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assemble the ASGI app from `env` (defaults to `os.environ`).

    Factored out of module-level `app = build_app()` below so this
    repository's own tests can exercise the full startup-validation and
    assembly logic against a real, throwaway-provisioned local PostgreSQL
    platform database without needing to reload this module or mutate
    `os.environ` for the whole test process.
    """
    env = env if env is not None else os.environ

    pepper = _require(env, "R2DB_CREDENTIAL_PEPPER")
    platform_dsn = _require(env, "R2DB_PLATFORM_DSN")
    schema = env.get("R2DB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA
    slugs = _parse_served_apps(_require(env, "R2DB_SERVE_APPS"))

    app_dsns: dict[str, tuple[str, str]] = {}
    for slug in slugs:
        runtime_name, developer_name = _app_dsn_env_names(slug)
        runtime_dsn = env.get(runtime_name)
        developer_dsn = env.get(developer_name)
        if not runtime_dsn or not developer_dsn:
            raise RuntimeError(f"{runtime_name} and {developer_name} are both required for application {slug!r} named in R2DB_SERVE_APPS")
        app_dsns[slug] = (runtime_dsn, developer_dsn)

    registry = _load_registry_rows(platform_dsn, schema, slugs)
    for slug in slugs:
        row = registry.get(slug)
        if row is None:
            raise RuntimeError(f"application {slug!r} named in R2DB_SERVE_APPS is not registered in the platform registry ({schema}.applications)")
        if not row["enabled"]:
            raise RuntimeError(f"application {slug!r} named in R2DB_SERVE_APPS is disabled in the platform registry -- re-enable it (python -m r2db_api.ops enable-app {slug}) or remove it from R2DB_SERVE_APPS")

    # Computed from `env` (this function's own parameter), and always
    # passed explicitly below -- not left as `None` for `PostgresCredential
    # Store` to default on its own, which would silently read the real
    # process `os.environ` instead of `env` (`PostgresCredentialStore`'s
    # own default lookup is `os.environ`-based, since it has no `env`
    # parameter of its own) and defeat `build_app(env=...)`'s whole point
    # of being fully driven by its argument for testability.
    platform_pool_size = _optional_int(env, "R2DB_PLATFORM_POOL_SIZE", 4)
    credentials = PostgresCredentialStore(platform_dsn, pepper=pepper, schema=schema, pool_size=platform_pool_size)

    def _cell_factory(application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> PostgresCell:
        if entities:
            # The composition root never pre-populates entities -- every
            # entity a served application has goes through the real
            # `POST /v1/schema/operations` + `.../mutations` HTTP endpoints,
            # exactly as a real client would (same reasoning as both
            # conformance adapters' own `_make_cell`).
            raise AssertionError("composition root does not pre-populate entities")
        runtime_dsn, developer_dsn = app_dsns[application_id]
        row = registry[application_id]
        return PostgresCell(
            application_id,
            "public",
            runtime_dsn=runtime_dsn,
            developer_dsn=developer_dsn,
            runtime_role=row["runtime_role"],
            developer_role=row["developer_role"],
        )

    service = DataService(credentials, cell_factory=_cell_factory)
    control = ControlAuthority(service)
    for slug in slugs:
        control.register_application(slug)

    @asynccontextmanager
    async def _lifespan(_app: Any):
        try:
            yield
        finally:
            # P2-D5: release every PostgreSQL connection this process holds
            # on shutdown -- the per-application pools shared through
            # `default_pool_manager` (`PostgresCell`'s own pooling) and the
            # platform credential store's dedicated pool (P2-D4), which is
            # never registered with `default_pool_manager` in the first
            # place and so needs its own explicit close.
            default_pool_manager.dispose_all()
            credentials.close()

    return create_app(service, lifespan=_lifespan)


app = build_app()
