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

Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work
order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1):
`surfaces` and the two `application_audit` writer-connection timeouts are
no longer configured from this process' own environment at all -- both are
now DB-side declarations this process reads at startup from
`r2dbsvc_registry.platform_declarations` (`surfaces`, `audit_coalescing_
window_ms`, migration `0008`) and `pg_db_role_setting` (`r2dbsvc_api`'s own
`statement_timeout`/`idle_in_transaction_session_timeout` role setting,
same migration). `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_URL`/`R2DB_AUDIT_
STATEMENT_TIMEOUT_MS`/`R2DB_AUDIT_IDLE_TIMEOUT_MS` are REJECTED outright if
still defined in this process' env mapping, whatever their value (design
D-1(d)/D-2(f); see `_reject_removed_env_vars` below) -- the only way to
change either declaration is now `python -m r2db_api.ops set-platform-
timeouts`/`declare-surfaces`/`declare-coalescing-window`, followed by
restarting both this process and `r2db_api.control_main` (design §9.2; the
read is a startup-time snapshot, U-3).

Environment variable contract (P2-D5, updated Q4 WP-1):

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
    R2DB_CONTROL_PLANE_STATUS            optional, default `unavailable`
                                          (CCR-14 WP-5, R-9) -- the deployer's
                                          own declaration of whether a
                                          `/control/v1` control-plane process
                                          (`r2db_api.control_main`) is running
                                          alongside this application-plane
                                          process at all. Allowed values are
                                          exactly `enabled`/`unavailable`; any
                                          other value (including a silently
                                          mistyped one) is a startup failure,
                                          never a silent fallback to
                                          `unavailable` -- see
                                          `_control_plane_status` below. Set
                                          this to `enabled` only when
                                          `control_main` is genuinely
                                          deployed reachably; this process
                                          cannot verify that fact on its own
                                          (R-9's own architecture note: a
                                          separated deployment's own
                                          `/control/v1` `GET .../capabilities`
                                          is the actual authority for whether
                                          a control plane is reachable, this
                                          declaration is only ever the
                                          deployer's stated intent). Q4 WP-1
                                          adds a startup cross-check (F-6)
                                          against the DB-side `surfaces.
                                          control` declaration -- see
                                          `platform_declarations.require_
                                          control_status_matches_surfaces`.
    R2DB_AUDIT_BUFFER_CAPACITY            optional, default 1000 -- D-4's
                                          bounded in-memory buffer capacity
                                          for ordinary (buffer-class)
                                          data-operation success events,
                                          per process.
    R2DB_AUDIT_FLUSH_INTERVAL_S           optional, default 2.0 -- how
                                          often the composition root's own
                                          background thread calls
                                          `DataService.flush_audit_buffer()`
                                          (D-4's periodic flush trigger); a
                                          latency knob only, never a
                                          correctness one.

REMOVED (Q4 WP-1, rejected outright if still defined -- see
`_reject_removed_env_vars`): `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`, `R2DB_
AUDIT_IDLE_TIMEOUT_MS`, `R2DB_DATA_BASE_URL`, `R2DB_CONTROL_BASE_URL`.

Startup failure policy (P2-D5): missing configuration, an application slug
named in `R2DB_SERVE_APPS` that is not registered in the platform registry,
and a registered-but-disabled slug are all import-time (`build_app`)
failures -- "uzurusaku ochiru" (loudly failing to start) rather than
silently serving a subset. There is no partial-startup mode. Q4 WP-1 adds
the DB-side declaration/role-setting checks above to this same fail-fast
policy -- this process is ALREADY network-dependent at `build_app()` time
(`_load_registry_rows`, pre-Q4), so folding the new checks into the same
synchronous call adds no new architectural property (contrast with
`r2db_api.control_main`, which defers its own equivalent checks to ASGI
lifespan startup specifically to preserve THAT module's own pre-existing
zero-network `build_control_app()` contract -- see that module's
docstring).
"""
from __future__ import annotations

import logging
import math
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Mapping

import psycopg
from psycopg import sql
from starlette.types import ASGIApp

from .credential_store import (
    DEFAULT_SCHEMA,
    PostgresApplicationAuditSink,
    PostgresCredentialStore,
)
from .http import create_app
from . import platform_declarations
from .platform_declarations import (
    check_control_surface_consistency,
    check_writer_role_timeouts,
    read_platform_declarations,
    reject_removed_surface_env,
    reject_removed_timeout_env,
)
from .errors import FoundationError
from .postgres import PostgresCell, _RefusingPlatformUpgradeCell, default_pool_manager
from .service import _DEFAULT_AUDIT_FLUSH_INTERVAL_S, ControlAuthority, DataService

_PLATFORM_CONNECT_TIMEOUT_S = 5

# U-6 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査): the H-1
# startup-time F-12 log line (`_cell_factory`'s own `except FoundationError`
# branch, below) goes through the standard `logging` module, not a bare
# `print(..., file=sys.stderr)`, so it can be pinned by a `caplog`-based
# test (verbatim text, same as the API response body) instead of only a
# visual stderr check.
_logger = logging.getLogger(__name__)

# R-9 (CCR-14 WP-5): the only two values `DataService.__init__`'s own
# `control_plane_status` parameter accepts -- kept in sync deliberately
# (service.py's constructor validates independently too, so a caller other
# than this composition root gets the identical guard).
_VALID_CONTROL_PLANE_STATUSES = {"enabled", "unavailable"}

def _control_plane_status(env: Mapping[str, str]) -> str:
    """Reads `R2DB_CONTROL_PLANE_STATUS` (default `unavailable`) and fails
    loudly (`RuntimeError`, P2-D5's "uzurusaku ochiru" startup-failure
    policy) on anything other than the two allowed values -- deliberately
    NOT a silent round-down to `unavailable` on an invalid value: a deployer
    who mistyped this variable must find out at startup, not have their
    typo quietly become the safe default while believing they configured
    something else."""
    value = env.get("R2DB_CONTROL_PLANE_STATUS") or "unavailable"
    if value not in _VALID_CONTROL_PLANE_STATUSES:
        raise RuntimeError(
            f"R2DB_CONTROL_PLANE_STATUS must be one of {sorted(_VALID_CONTROL_PLANE_STATUSES)!r}, got {value!r}"
        )
    return value


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


def _optional_float(env: Mapping[str, str], name: str, default: float) -> float:
    """Phase 6 WP-0 (design D-4(a)): unlike `_optional_int`, this
    function's only consumer is the audit-buffer flush interval, and a
    misconfigured value there does not degrade gracefully --
    `threading.Event.wait(0)`, `.wait(-1)`, and `.wait(float("nan"))` all
    return immediately (`False`), so a value that is unset or empty is
    fine (falls back to `default`, same discipline as `_optional_int`),
    but a *non-empty* value that is not a finite, positive float turns the
    flush thread into a silent hot loop -- something a deployer who
    mistyped the variable would never notice, since nothing about a hot
    flush loop looks alarming on its own. So this fails loudly at startup
    instead (`ValueError` naming the variable), the same discipline this
    module's own other env-var validity checks already use."""
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a finite, positive number, got {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite, positive number, got {raw!r}")
    return value


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
    # `database_name` is selected too (CCR-14 WP-2, R-4) purely to answer
    # "is this slug provisioned yet" (`database_name IS NOT NULL` -- the
    # same test `0006_control_plane_http.sql`'s own CHECK constraint and
    # revised provisioning functions use; no separate status column exists)
    # -- its actual value is never used below, only whether it is `None`.
    statement = sql.SQL("SELECT application_slug, enabled, runtime_role, developer_role, database_name FROM {table} WHERE application_slug = ANY({slugs})").format(
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
    return {row[0]: {"enabled": row[1], "runtime_role": row[2], "developer_role": row[3], "provisioned": row[4] is not None} for row in rows}


def build_app(env: Mapping[str, str] | None = None) -> ASGIApp:
    """Assemble the ASGI app from `env` (defaults to `os.environ`).

    Factored out of module-level `app = build_app()` below so this
    repository's own tests can exercise the full startup-validation and
    assembly logic against a real, throwaway-provisioned local PostgreSQL
    platform database without needing to reload this module or mutate
    `os.environ` for the whole test process.

    Q4 phase WP-1 startup sequence (design §3.7, data-plane 1-8): (1) basic
    env reads, (2) reject the four removed env vars (F-1/F-2) whatever
    their value, (3) the platform connection this process already made
    eagerly pre-Q4 (`_load_registry_rows`), (4) read `platform_
    declarations` (F-8 if the table itself is missing), (5) validate
    `surfaces`/`audit_coalescing_window_ms` (F-3/F-4 if a row is missing,
    F-5/F-4b/F-6 if a present value is malformed), (6) the writer-role
    double-check (F-7/F-10/F-11 against `pg_db_role_setting`, F-9 against
    this process' own writer pool's effective `pg_settings` value), (7)
    build the audit sink (no SESSION `SET` -- design D-1(b)), (8) wire
    `surfaces`/the coalescing window into `DataService`.
    """
    env = env if env is not None else os.environ

    pepper = _require(env, "R2DB_CREDENTIAL_PEPPER")
    platform_dsn = _require(env, "R2DB_PLATFORM_DSN")
    schema = env.get("R2DB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA
    slugs = _parse_served_apps(_require(env, "R2DB_SERVE_APPS"))
    control_plane_status = _control_plane_status(env)

    # Step 2 (F-1/F-2): must run before anything else touches the network
    # -- a deployer who left one of these four defined must find out
    # immediately, not after this process has already opened a platform
    # connection for an unrelated reason.
    reject_removed_timeout_env(env, names=platform_declarations.REMOVED_TIMEOUT_ENV)
    reject_removed_surface_env(env, names=platform_declarations.REMOVED_SURFACE_ENV, schema=schema)

    app_dsns: dict[str, tuple[str, str]] = {}
    for slug in slugs:
        runtime_name, developer_name = _app_dsn_env_names(slug)
        runtime_dsn = env.get(runtime_name)
        developer_dsn = env.get(developer_name)
        if not runtime_dsn or not developer_dsn:
            raise RuntimeError(f"{runtime_name} and {developer_name} are both required for application {slug!r} named in R2DB_SERVE_APPS")
        app_dsns[slug] = (runtime_dsn, developer_dsn)

    # Step 3 (existing, pre-Q4): the platform connection this process
    # already made eagerly to validate R2DB_SERVE_APPS.
    registry = _load_registry_rows(platform_dsn, schema, slugs)
    for slug in slugs:
        row = registry.get(slug)
        if row is None:
            raise RuntimeError(f"application {slug!r} named in R2DB_SERVE_APPS is not registered in the platform registry ({schema}.applications)")
        if not row["enabled"]:
            raise RuntimeError(f"application {slug!r} named in R2DB_SERVE_APPS is disabled in the platform registry -- re-enable it (python -m r2db_api.ops enable-app {slug}) or remove it from R2DB_SERVE_APPS")
        # R-4 (CCR-14 WP-2): a *registered-only* row (no provisioning
        # columns set -- 0006's two-state `applications`) has no real
        # database/roles to serve at all. Without this check, `_cell_
        # factory` below would build a `PostgresCell` against DSNs this
        # slug's `R2DB_APP_<SLUG>_*_DSN` env vars name, which reference a
        # database/roles that were never actually provisioned -- every
        # request against it would fail at connect time instead of this
        # process refusing to start at all (P2-D5's "uzurusaku ochiru"
        # startup-failure policy, same as the two checks above).
        if not row["provisioned"]:
            raise RuntimeError(f"application {slug!r} named in R2DB_SERVE_APPS is registered but not yet provisioned in the platform registry ({schema}.applications) -- provision it (0003_provision_application.sql) or remove it from R2DB_SERVE_APPS")

    # Steps 4-5 (Q4 D-2, F-8/F-3/F-4/F-5/F-4b/F-6): the DB-side
    # declarations, replacing the pre-Q4 env-based `_surfaces(env, ...)`.
    # `read_platform_declarations` needs only a SELECT-granted connection
    # (never the writer sink's own pool) -- this is a short-lived,
    # dedicated connection, closed immediately after, mirroring `_load_
    # registry_rows`'s own one-shot-connection pattern above.
    try:
        _declarations_conn = psycopg.connect(platform_dsn, connect_timeout=_PLATFORM_CONNECT_TIMEOUT_S)
    except psycopg.Error as exc:
        raise RuntimeError(f"could not connect to read {schema}.platform_declarations: {exc}") from exc
    try:
        declarations = read_platform_declarations(
            _declarations_conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            migration=platform_declarations.MIGRATION_NUMBER,
        )
    finally:
        _declarations_conn.close()
    check_control_surface_consistency(declarations.surfaces, control_plane_status, ops_module=platform_declarations.PEER_MODULE)
    surfaces: dict[str, Any] = {"data": {"base_url": declarations.surfaces.data_base_url}}
    if declarations.surfaces.control_base_url is not None:
        surfaces["control"] = {"base_url": declarations.surfaces.control_base_url}
    coalescing_window_ms = declarations.audit_coalescing_window_ms

    # Computed from `env` (this function's own parameter), and always
    # passed explicitly below -- not left as `None` for `PostgresCredential
    # Store` to default on its own, which would silently read the real
    # process `os.environ` instead of `env` (`PostgresCredentialStore`'s
    # own default lookup is `os.environ`-based, since it has no `env`
    # parameter of its own) and defeat `build_app(env=...)`'s whole point
    # of being fully driven by its argument for testability.
    platform_pool_size = _optional_int(env, "R2DB_PLATFORM_POOL_SIZE", 4)
    credentials = PostgresCredentialStore(platform_dsn, pepper=pepper, schema=schema, pool_size=platform_pool_size)
    # Step 7 (Q4 D-1(b)): the durable application-plane audit sink -- the
    # SAME `R2DB_PLATFORM_DSN` (already `r2dbsvc_api`, which migration
    # `0007_application_audit.sql` grants INSERT-only on `application_
    # audit`) `PostgresCredentialStore` above already connects with; this
    # is a second, independent pool against that same role/database, not a
    # shared connection (D-1(c): "書き手 = data-planeプロセスが既に保持して
    # いるplatform接続"). No SESSION `SET` for either timeout -- both are
    # now a `pg_db_role_setting` role setting, migration `0008` (D-1(a)).
    durable_audit = PostgresApplicationAuditSink(platform_dsn, schema=schema, pool_size=platform_pool_size)

    # Step 6 (Q4 D-1(b), F-13/F-7/F-9/F-10/F-11; rework D-2(h)): the
    # self-role inclusion check (F-13) followed by the writer-role double
    # check, run on a connection BORROWED FROM `durable_audit`'S OWN POOL
    # (login role = the actual `application_audit` writer role -- a role
    # setting only takes effect at login time, design D-1(c)) -- never a
    # naming-convention-derived role name (rejected, rulings-q4-writer-
    # roles.md): the role set comes exclusively from the declared
    # `audit_writer_roles` row this process just read above.
    with durable_audit.borrow_connection() as _writer_conn:
        check_writer_role_timeouts(
            _writer_conn, declared_roles=declarations.audit_writer_roles, schema=schema,
            ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
        )

    audit_buffer_capacity = _optional_int(env, "R2DB_AUDIT_BUFFER_CAPACITY", 1000)
    audit_flush_interval_s = _optional_float(env, "R2DB_AUDIT_FLUSH_INTERVAL_S", _DEFAULT_AUDIT_FLUSH_INTERVAL_S)

    def _cell_factory(application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> PostgresCell | _RefusingPlatformUpgradeCell:
        if entities:
            # The composition root never pre-populates entities -- every
            # entity a served application has goes through the real
            # `POST /v1/schema/operations` + `.../mutations` HTTP endpoints,
            # exactly as a real client would (same reasoning as both
            # conformance adapters' own `_make_cell`).
            raise AssertionError("composition root does not pre-populate entities")
        runtime_dsn, developer_dsn = app_dsns[application_id]
        row = registry[application_id]
        cell = PostgresCell(
            application_id,
            "public",
            runtime_dsn=runtime_dsn,
            developer_dsn=developer_dsn,
            runtime_role=row["runtime_role"],
            developer_role=row["developer_role"],
        )
        # Q4 WP-3 (design D-3(f), requester ruling 2026-09-05 U-2; reworked
        # by supervisor ruling 2026-09-05 H-1(a)): "cell open time" IS this
        # call -- every served application's cell is opened eagerly, right
        # here, in the `for slug in slugs` loop below, not lazily on first
        # request. `verify_platform_upgrades_applied()` no longer gets to
        # propagate its `SERVICE_UNAVAILABLE`/F-12 `FoundationError` out of
        # this factory -- before this rework that took the WHOLE PROCESS
        # down (`ControlAuthority.register_application` -> `build_app`'s
        # own eager registration loop -> the caller of `build_app` itself)
        # the moment even ONE served application's ledger had a pending
        # upgrade, refusing every OTHER served application too (review
        # H-1). Instead, THIS application alone gets a `_Refusing
        # PlatformUpgradeCell` in place of its real `PostgresCell` --
        # every other served application's cell (this same loop, other
        # iterations) still opens and serves normally, and this process
        # itself still starts.
        try:
            cell.verify_platform_upgrades_applied()
        except FoundationError as exc:
            # F-12 is logged once, here, at cell-open time -- the SAME
            # text this application's own requests will see in every
            # `SERVICE_UNAVAILABLE` response from here on (H-1: "起動時
            # にはログへ F-12 を1行出す (API 応答と同じ文面)"). This is the
            # only way an operator would otherwise learn of the refusal
            # without waiting for a client to report one, since this
            # rework deliberately no longer crashes the process to surface
            # it.
            _logger.warning("r2db_api: application '%s' cell refusing requests: %s", application_id, exc.message)
            return _RefusingPlatformUpgradeCell(application_id, exc.message)
        return cell

    service = DataService(
        credentials, cell_factory=_cell_factory, control_plane_status=control_plane_status,
        durable_audit=durable_audit, audit_buffer_capacity=audit_buffer_capacity,
        surfaces=surfaces,
        # Step 8 (Q4 D-2(e)): the DB-declared coalescing window, ms ->
        # seconds -- replaces the pre-Q4 hardcoded default (`DataService`'s
        # own `_DENIAL_COALESCE_WINDOW_S` default, still used as the
        # migration `0008` seed value's SOURCE constant, `r2db_api.
        # audit_query.DECLARED_COALESCING_WINDOW_MS`, but no longer read
        # directly by this composition root).
        denial_coalesce_window_s=coalescing_window_ms / 1000.0,
        # WP-2(a) fix round 2 review N-2: the alert-row rate floor tracks
        # the ACTUAL configured flush interval (which `R2DB_AUDIT_FLUSH_
        # INTERVAL_S` may have overridden away from the default), not a
        # second, independently-defaulted value that could silently stop
        # matching it.
        audit_alert_min_interval_s=audit_flush_interval_s,
    )
    control = ControlAuthority(service)
    for slug in slugs:
        control.register_application(slug)

    # Phase 4 (design D-4, "実装裁量" -- periodic flush trigger): a daemon
    # thread that calls `service.flush_audit_buffer()` on a fixed interval
    # for the lifetime of this process, so buffered/coalesced evidence does
    # not sit un-durable indefinitely on a served application that happens
    # to receive no further traffic. Purely a latency knob (see this
    # module's own `_DEFAULT_AUDIT_FLUSH_INTERVAL_S` comment) -- correctness
    # of D-3/D-4's own bounds does not depend on this thread running at all.
    #
    # WP-2(a) review M-3: both the stop `Event` and the `Thread` are now
    # created FRESH inside `_lifespan`, on every entry, rather than once at
    # `build_app()` call time -- `threading.Thread.start()` may only be
    # called once per `Thread` object ("threads can only be started once");
    # constructing them once outside `_lifespan` meant a second ASGI
    # startup against the same built app (this repository's own tests, or
    # any host that re-enters lifespan on the same app object) would raise
    # on the second `start()`. A fresh pair per entry has no such limit.
    @asynccontextmanager
    async def _lifespan(_app: Any):
        audit_flush_stop = threading.Event()

        def _audit_flush_loop() -> None:
            while not audit_flush_stop.wait(audit_flush_interval_s):
                try:
                    service.flush_audit_buffer()
                except Exception:
                    # A flush failure must never kill this thread (there
                    # would then be nothing left to retry the next
                    # interval) -- D-4's own sticky/backoff retry logic
                    # already lives inside `flush_audit_buffer()`; this is
                    # only a defensive backstop against a truly unexpected
                    # exception escaping it.
                    pass

        audit_flush_thread = threading.Thread(target=_audit_flush_loop, name="r2db-audit-flush", daemon=True)
        audit_flush_thread.start()
        try:
            yield
        finally:
            audit_flush_stop.set()
            audit_flush_thread.join(timeout=5.0)
            # WP-2(a) review M-3/N-4: one final synchronous flush before
            # the sink's pool closes below -- without this, up to
            # `capacity` buffered events and every still-open denial-
            # coalescing window's accumulated repeat count are silently
            # discarded on a graceful shutdown (the periodic thread has
            # just stopped, and nothing else will ever call this again for
            # this process). `force_expire_denial_windows=True` (N-4): a
            # window that has not YET reached its own `window_s` at this
            # exact moment still gets its repeat-summary row written here
            # -- shutdown is not a crash, so D-3's "crash loses only the
            # in-progress window's count" allowance does not apply; an
            # orderly stop must not discard it.
            try:
                service.flush_audit_buffer(force_expire_denial_windows=True)
            except Exception:
                # Best-effort, like every other flush attempt -- shutdown
                # must still complete and release connections below even
                # if the sink happens to be down at this exact moment.
                pass
            # P2-D5: release every PostgreSQL connection this process holds
            # on shutdown -- the per-application pools shared through
            # `default_pool_manager` (`PostgresCell`'s own pooling) and the
            # platform credential store's dedicated pool (P2-D4), which is
            # never registered with `default_pool_manager` in the first
            # place and so needs its own explicit close. Phase 4:
            # `durable_audit` is the same kind of dedicated pool and needs
            # the same explicit close.
            default_pool_manager.dispose_all()
            credentials.close()
            durable_audit.close()

    return create_app(service, lifespan=_lifespan)


app = build_app()
