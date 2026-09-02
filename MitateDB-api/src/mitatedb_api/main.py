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
    MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS   optional, default 5000 (Phase 4,
                                           design docs/design/
                                           PHASE4_DURABLE_AUDIT_SINK_V1.md
                                           D-6/N-3) -- SESSION-level
                                           `statement_timeout` on the
                                           connection that writes
                                           `application_audit`. Changing
                                           this changes the derived
                                           `visibility_lag_ms` a future
                                           WP-3(b) `audit_query`
                                           declaration would publish
                                           (`control_composition.
                                           build_control_service` reads
                                           the IDENTICAL env-var name for
                                           the `control_audit` writer
                                           connection -- both must agree).
    MITATEDB_AUDIT_IDLE_TIMEOUT_MS        optional, default 5000 --
                                           SESSION-level `idle_in_
                                           transaction_session_timeout` on
                                           the same connection; see the
                                           note above.
    MITATEDB_AUDIT_BUFFER_CAPACITY        optional, default 1000 -- D-4's
                                           bounded in-memory buffer
                                           capacity for ordinary
                                           (buffer-class) data-operation
                                           success events, per process.
    MITATEDB_AUDIT_FLUSH_INTERVAL_S       optional, default 2.0 -- how
                                           often this process' own
                                           background thread calls
                                           `audit_dispatch.AuditRouter.
                                           flush()` (D-4's periodic flush
                                           trigger); a latency knob only,
                                           never a correctness one.

Startup failure policy: every `RuntimeError` below is an intentional,
loud "refuse to start" -- there is no partial-startup mode.
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Mapping

import psycopg
from psycopg import sql
from starlette.types import ASGIApp

from .application_audit import (DEFAULT_AUDIT_BUFFER_CAPACITY,
                                DEFAULT_AUDIT_FLUSH_INTERVAL_S,
                                DEFAULT_AUDIT_IDLE_TIMEOUT_MS,
                                DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
                                PostgresApplicationAuditSink)
from .audit import AuditSink
from .audit_dispatch import AuditRouter
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


def _optional_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-6/
    N-3): same lenient-degrade discipline as `config.FoundationConfig.
    from_env`'s OTHER tuning knobs -- an unset/empty/unparsable value
    silently falls back to `default` rather than raising."""
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _optional_float(env: Mapping[str, str], name: str, default: float) -> float:
    """`_optional_int`'s `float` counterpart, for the audit-buffer flush
    interval (Phase 4) -- identical degrade-to-default discipline."""
    raw = env.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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

    # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-6, work order
    # WP-3(a)): the durable application-plane audit sink -- writes to the
    # SAME `MITATEDB_PLATFORM_DSN` (already `mitatedbsvc_api`, which
    # migration `0005_application_audit.sql` grants INSERT-only on
    # `application_audit`) `PostgresCredentialStore` above also connects
    # with (D-1(c): "書き手 = data-plane プロセスが既に保持している
    # platform 接続"). The two SESSION-level timeouts are set on every
    # connection this sink ever opens (D-6/N-3's visibility-lag basis).
    audit_statement_timeout_ms = _optional_int(env, "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS)
    audit_idle_timeout_ms = _optional_int(env, "MITATEDB_AUDIT_IDLE_TIMEOUT_MS", DEFAULT_AUDIT_IDLE_TIMEOUT_MS)
    durable_audit = PostgresApplicationAuditSink(
        platform_dsn, schema=schema, statement_timeout_ms=audit_statement_timeout_ms,
        idle_in_transaction_session_timeout_ms=audit_idle_timeout_ms,
    )
    audit_buffer_capacity = _optional_int(env, "MITATEDB_AUDIT_BUFFER_CAPACITY", DEFAULT_AUDIT_BUFFER_CAPACITY)
    audit_flush_interval_s = _optional_float(env, "MITATEDB_AUDIT_FLUSH_INTERVAL_S", DEFAULT_AUDIT_FLUSH_INTERVAL_S)
    # ONE shared router (design D-3/D-4's own "process-local" scoping) --
    # handed to `credentials` below AND to every `ApplicationCell` this
    # process builds, so denial coalescing and the buffer are shared
    # process-wide, not duplicated per credential store/cell.
    audit_router = AuditRouter(
        durable_audit, buffer_capacity=audit_buffer_capacity, alert_min_interval_s=audit_flush_interval_s,
    )

    credentials = PostgresCredentialStore(
        platform_dsn, pepper=app_pepper, schema=schema, pool=platform_pool, audit_router=audit_router,
    )

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
            application_id, config, audit, guard=credentials.assert_active, backend=backend,
            audit_router=audit_router,
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

    # Review m-1/M-3 (supervisor ruling 2026-09-03): the same shared
    # `audit_router` every `ApplicationCell`/`PostgresCredentialStore`
    # already receives -- `HttpService.authenticate` is the ONLY call
    # site that can ever durably record `AUTH_REQUIRED` (no bearer token
    # presented at all).
    service = HttpService(credentials, _cell_factory, audit_router=audit_router)

    # Phase 4 (design D-4, "実装裁量" -- periodic flush trigger): a daemon
    # thread that calls `audit_router.flush()` on a fixed interval for
    # the lifetime of this process, so buffered/coalesced evidence does
    # not sit un-durable indefinitely on a served application that
    # happens to receive no further traffic. Purely a latency knob --
    # correctness of D-3/D-4's own bounds does not depend on this thread
    # running at all. The stop `Event` and `Thread` are created FRESH
    # inside `_lifespan` on every entry (mirroring r2db-api's own
    # `main.py::_lifespan` identical reasoning, independently arrived at
    # here): `threading.Thread.start()` may only be called once per
    # object, so constructing them once outside `_lifespan` would raise
    # on a second ASGI startup against the same built app (this
    # repository's own tests re-entering lifespan on the same app object).
    @asynccontextmanager
    async def _lifespan(_app: Any):
        audit_flush_stop = threading.Event()

        def _audit_flush_loop() -> None:
            while not audit_flush_stop.wait(audit_flush_interval_s):
                try:
                    audit_router.flush()
                except Exception:
                    # A flush failure must never kill this thread (there
                    # would then be nothing left to retry the next
                    # interval) -- D-4's own sticky/backoff retry logic
                    # already lives inside `AuditRouter.flush()`; this is
                    # only a defensive backstop against a truly
                    # unexpected exception escaping it.
                    pass

        audit_flush_thread = threading.Thread(target=_audit_flush_loop, name="mitatedb-audit-flush", daemon=True)
        audit_flush_thread.start()
        try:
            yield
        finally:
            audit_flush_stop.set()
            audit_flush_thread.join(timeout=5.0)
            # One final synchronous flush before this process stops --
            # without this, up to `buffer_capacity` buffered events and
            # every still-open denial-coalescing window's accumulated
            # repeat count are silently discarded on a graceful shutdown
            # (the periodic thread has just stopped, and nothing else
            # will ever call this again for this process).
            # `force_expire_denial_windows=True`: a window that has not
            # YET reached its own window_s at this exact moment still
            # gets its repeat-summary row written here -- shutdown is not
            # a crash, so D-3 only sanctions losing counts to an actual
            # crash, never to an orderly stop.
            try:
                audit_router.flush(force_expire_denial_windows=True)
            except Exception:
                # Best-effort, like every other flush attempt -- shutdown
                # must still complete and release connections below even
                # if the sink happens to be down at this exact moment.
                pass
            # Release every connection this process holds on shutdown: the
            # platform registry's bounded pool, and every served
            # application's own two persistent PostgreSQL connections.
            # `durable_audit` opens a fresh connection per call (no pool
            # of its own -- `application_audit.PostgresApplicationAuditSink`'s
            # own docstring) and so needs no explicit close here.
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
