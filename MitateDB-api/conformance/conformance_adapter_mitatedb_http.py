"""MitateDB-api (http+postgres) plug for the common conformance port
(WP-3, docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-8).

This is a *second* adapter for the same peer as `conformance_adapter_
mitatedb.py`: where that module drives `MitateDataService`/`ApplicationCell`
directly, in-process, over an in-memory SQLite backend, this module drives
the same conditions over the real stack -- the ASGI HTTP boundary
(`mitatedb_api.http`) in front of sessions backed by `PostgresBackend`
against a real, throwaway-provisioned local PostgreSQL 16 database. Same
port, same condition IDs, different plug (design principle 1).

Independent implementation (R-2's closing paragraph, applied here to
conformance harnesses too): this file follows the same GENERAL shape as
`r2db-api/conformance/conformance_adapter_r2db_http.py` (read-only
reference per the task brief -- httpx ASGITransport, throwaway-prefixed
PostgreSQL provisioning via the real migration files, a prefix-anchored
startup sweep with an advisory-lock liveness guard) because both peers
share the same conformance-harness *pattern* by design decision, not
because any of this file's own code was copied from that one.

Module name matters: `conformance-tests/registry.json` declares this
peer's module as `conformance_adapter_mitatedb_http`, and `conftest.py`
discovers it by adding `MitateDB-api/conformance/` to `sys.path` (via the
PRECEDING `MitateDB-api` registry entry -- WP-0 m-1: this entry's own
`name` field, "MitateDB-api-http", does not itself resolve a directory
that exists) and doing a plain `importlib.import_module(...)`.

Control-plane surface (R-8 / design's WP-3 scope): the `/control/v1`
surface does not exist yet (WP-5's own flip). Every control-plane port
operation below takes the SAME `SurfaceAbsent` branch the in-process
adapter takes, using the SAME evidence surface (`ApplicationRuntime`/
`ApplicationDeveloper`'s real methods, plus this composition's own
`HttpService.authenticate`) -- honest, since the seven mounted HTTP routes
are a thin wire wrapper around exactly those same session objects, and none
of the seven route handlers themselves accept any per-operation named
parameter at all (they all just read `request: Request`, a Starlette
convention distinct from anything control-plane-shaped).

C-17 present-denial form (R-8 item 1): `create_unique_index`/`drop_entity`
do NOT raise `SurfaceAbsent` on this adapter (unlike the in-process one) --
`/v1/schema/operations` is mounted here, with a real dispatcher that
receives `create_index`/`drop_entity` and refuses them with a real,
present `CAPABILITY_UNSUPPORTED` denial. Likewise `catalog_document`
presents a real `GET /v1/catalog` and lets its real `CAPABILITY_UNSUPPORTED`
denial propagate, rather than returning `CATALOG_SURFACE_ABSENT` (R-3's
own known difference (2)).

Synthetic values only: application ids, credential ids/secrets, and the
throwaway PostgreSQL role/database names created here are conformance-suite
fixtures, torn down at `close()`, never real deployment values (CLAUDE.md
Public Repository Security Gate).
"""
from __future__ import annotations

import atexit
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

if "adapter" not in sys.modules:
    _conformance_tests = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests")
    )
    if os.path.isdir(_conformance_tests) and _conformance_tests not in sys.path:
        sys.path.insert(0, _conformance_tests)

from adapter import (  # noqa: E402
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ControlCredentialHandle,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopedBatchOperation,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    fresh_identifier,
    resolve_valid_confirmation,
)

from mitatedb_api.application_audit import PostgresApplicationAuditSink  # noqa: E402
from mitatedb_api.audit_dispatch import AuditRouter  # noqa: E402
from mitatedb_api.auth import Role  # noqa: E402
from mitatedb_api.backend_postgres import PostgresBackend  # noqa: E402
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime  # noqa: E402
from mitatedb_api.config import FoundationConfig  # noqa: E402
from mitatedb_api.control_audit import read_control_audit_events  # noqa: E402
from mitatedb_api.control_composition import build_control_service  # noqa: E402
from mitatedb_api.control_http import create_control_app  # noqa: E402
from mitatedb_api.credential_store_postgres import PostgresCredentialStore  # noqa: E402
from mitatedb_api.errors import AuthorizationStateUnavailable  # noqa: E402
from mitatedb_api.http import PROBLEM_CONTENT_TYPE, HttpService, create_app  # noqa: E402

BASE_URL = "http://mitatedb-http-pg.conformance.invalid"

# Phase 6 WP-3 (design D-2): the `surfaces` this plug declares -- built
# from the SAME `BASE_URL` its own `self._client`/`self._control_client`
# are constructed against (`versioning.base_path`/`control_base_path`
# suffixed on), never a second, independently-chosen pair of strings.
_DATA_SURFACE_BASE_URL = BASE_URL + "/v1"
_CONTROL_SURFACE_BASE_URL = BASE_URL + "/control/v1"

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

# WP-5 (design v1.2 R-8): `MitateDB-api` is not pip-installed anywhere this
# suite runs from -- the real CLI ritual (`python -m mitatedb_api.ops
# bootstrap`/`reset`) needs its own explicit `PYTHONPATH` injection to be
# importable as a subprocess (WP-0 m-11).
SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Same admin-DSN knob `MitateDB-api/tests/test_postgres.py` already uses:
# one shared convention across every PostgreSQL-backed test/harness in this
# package for "where is the local admin/superuser connection".
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

_SCHEMA_REVISION_TABLE = "_mdb_schema_revision"
# Phase 6 WP-3 (design D-3): the declared-type registry table itself --
# `backend_postgres._FIELD_TYPES_TABLE`'s own identical name, kept as a
# separate literal here rather than importing that module-private
# constant (this file already has its own, deliberately independent copy
# of `_SCHEMA_REVISION_TABLE` above, for the same reason -- an adapter
# does not reach into a peer's own module internals for a bookkeeping
# name it needs to exclude from its own privileged reach-around).
_FIELD_TYPES_TABLE = "_mdb_field_types"

# port's own two-member field-type vocabulary (`adapter.COMMON_FIELD_TYPES`)
# -> this peer's real `SchemaOperationRequest.field_type` wire enum member
# (mirrors r2db-http's own `_PORT_FIELD_TYPE_TO_R2DB` table, independently
# defined here for this peer's own wire vocabulary).
_PORT_FIELD_TYPE_TO_WIRE = {"text": "string", "integer": "integer"}


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_reachable_postgres(dsn: str) -> None:
    """R-8 / WP-0 m-9: this adapter is registered `required: true` --
    skip is never permitted here (design principle 4). An unreachable
    PostgreSQL fails the whole suite loudly, with the exact DSN and
    concrete remediation, rather than silently shrinking the suite."""
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "MitateDB-api (http+postgres) conformance adapter requires a reachable local "
            f"PostgreSQL server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. This "
            "adapter is registered required: true in conformance-tests/registry.json, so the "
            "suite fails rather than silently skips the HTTP+PostgreSQL coverage (design "
            f"principle 4). Start a local PostgreSQL server reachable at that DSN, or set "
            f"{ADMIN_DSN_ENV} to a reachable admin/superuser DSN."
        ) from exc


@dataclass(frozen=True)
class _Platform:
    prefix: str
    admin_dsn: str
    provision_dsn: str
    api_dsn: str
    controlplane_dsn: str
    schema: str
    platform_db: str
    provision_script: Path
    deprovision_script: Path
    # Phase 4 WP-3(b) (design D-5): the `<prefix>svc_auditreader` role's
    # own DSN -- migration `0005_application_audit.sql`'s reader, SELECT-
    # only over `control_audit` + `application_audit`.
    auditreader_dsn: str


@dataclass(frozen=True)
class _PgAppInfo:
    application_id: str
    database: str
    runtime_role: str
    developer_role: str
    runtime_dsn: str
    developer_dsn: str


def _bootstrap_platform(prefix: str, admin_dsn: str, script_dir: Path) -> _Platform:
    """Runs the real `0001_bootstrap_platform.sql`..`0004_deprovision_
    application.sql` (with the literal token `mitatedb` textually replaced
    by this run's unique prefix, per those files' own header comments) --
    the actual runbook an operator would use, not a Python reimplementation
    of it, exactly as `tests/test_postgres.py::_bootstrap_platform` does
    (mirrors that established convention within this same peer; not code
    sharing with r2db-api). `script_dir` is kept alive for this adapter
    instance's whole lifetime (unlike `test_postgres.py`'s pytest-scoped
    temp dir) since `provision_application`/`deprovision_application` run
    the rewritten 0003/0004 scripts repeatedly, long after this returns.
    """
    # WP-3(b) review finding F (supervisor-forwarded fix): a duplicate
    # generation of these same 3 passwords was accidentally introduced
    # here during WP-3(b) (dead code -- the first 3 lines were
    # unconditionally shadowed by the next 3). Removed back to one block.
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    # Phase 4 WP-3(b) (design D-5): the reader role's own throwaway
    # password -- mirrors the 3 above, never a real credential.
    auditreader_password = secrets.token_urlsafe(24)

    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql",
        "0002_registry_and_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        # Phase 4 WP-3(b): application_audit table + mitatedbsvc_
        # auditreader role -- `_run_psql` below runs this AFTER 0002,
        # exactly the order the file's own header requires.
        "0005_application_audit.sql",
        # Q4 phase (design D-1/D-2, work order §4 WP-2 変更対象 D):
        # platform declarations table + the two service writer roles'
        # timeout role settings -- THIS adapter's own `build_control_
        # service(control_env)` call (design §6.1 α, §1.5 finding 10)
        # goes through the composition root's real startup path, so the
        # declarations table's own read is load-bearing here (unlike
        # r2db-api's HTTP plug, which injects `surfaces` directly).
        # Without this migration applied + a `surfaces` row seeded below,
        # `build_control_service` fails F-8/F-3 at construction time.
        "0007_platform_declarations.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = script_dir / name
        out.write_text(text)
        rewritten[name] = out

    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    auditreader_role = f"{prefix}svc_auditreader"
    schema = f"{prefix}_registry"

    _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
    provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
    _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    # Phase 4 WP-3(b): 0005 creates `application_audit` + the reader role
    # (`WHO RUNS THIS: mitatedbsvc_provision`, migration 0005's own
    # header) -- runs as the SAME `provision_dsn` 0002 already ran as.
    _run_psql(provision_dsn, rewritten["0005_application_audit.sql"])
    # Q4 phase: platform declarations + writer-role timeouts -- only
    # depends on 0002's two roles, run here (before the password-ALTER
    # block below, order-independent either way).
    _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
    # `surfaces` (D-2(c)): BOTH `data`/`control` -- this adapter's own
    # `build_control_service` call requires `control` unconditionally
    # (design §3.7: "control プロセスは自らの control surface を必ず持
    # つ"), and its data-plane `FoundationConfig` construction below uses
    # the SAME `_DATA_SURFACE_BASE_URL`/`_CONTROL_SURFACE_BASE_URL`
    # constants as the value SOURCE this row's own values are seeded
    # from -- keeping both origins textually visible at this one seed
    # site, rather than only inside a composition-root env var.
    surfaces_conn = psycopg.connect(provision_dsn, autocommit=True)
    try:
        with surfaces_conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', {value})").format(
                    table=sql.Identifier(schema, "platform_declarations"),
                    value=sql.Literal(
                        '{"data":{"base_url":"' + _DATA_SURFACE_BASE_URL + '"},'
                        '"control":{"base_url":"' + _CONTROL_SURFACE_BASE_URL + '"}}'
                    ),
                ),
            )
    finally:
        surfaces_conn.close()

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        # `ALTER ROLE ... PASSWORD` is DDL (no server-side bind parameter
        # for that clause); `sql.Literal` composes a safely quoted literal
        # at composition time from this harness's own freshly generated
        # synthetic secrets, never client-controlled input.
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(auditreader_role), sql.Literal(auditreader_password)))
    finally:
        admin.close()

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        schema=schema,
        platform_db=platform_db,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        auditreader_dsn=_dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db),
    )


def _provision_pg_app(platform: _Platform, application_id: str) -> _PgAppInfo:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.provision_dsn, platform.provision_script,
        {"app_id": application_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{application_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return _PgAppInfo(
        application_id=application_id,
        database=database,
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def _deprovision_pg_app(platform: _Platform, application_id: str) -> None:
    """Retries on `... is being accessed by other users`, mirroring
    `tests/test_postgres.py::deprovision_app`'s identical, already-measured
    race (a connection this adapter itself just closed can take a brief
    moment to fully disappear from `pg_stat_activity`)."""
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": application_id})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


# --------------------------------------------------------------------------
# Prefix-anchored sweep + advisory lock (R-4/R-8): drop everything a run
# under this adapter's own prefix shape created, and guard against a
# concurrent process racing an in-progress build (WP-0 "L2"-class hazard,
# already solved once for r2db-http and for `tests/test_postgres.py`'s own
# simpler single-lock-key form -- this uses the latter's simpler,
# per-prefix `pg_advisory_lock(hashtext(prefix))` shape rather than a fixed
# shared key, so a concurrent sweep of a DIFFERENT stale prefix is never
# serialized behind this run's own long-lived guard connection).
# --------------------------------------------------------------------------

_STALE_PLATFORM_DB_PATTERN = r"^mitatedbhttp[0-9a-f]{8}_platform$"
_STALE_APP_DB_PATTERN = r"^mitatedbhttp[0-9a-f]{8}_app_"
_STALE_ROLE_PATTERN = r"^mitatedbhttp[0-9a-f]{8}"
_PREFIX_LENGTH = len("mitatedbhttp") + 8


def _lock_key(prefix: str) -> list[str]:
    return [prefix]


def _prefix_like_pattern(prefix: str) -> str:
    """The SQL `LIKE` pattern `_sweep_prefix` scopes its own enumeration
    to. Factored out into its own pure function (mutation-tested
    separately from the real, destructive `DROP DATABASE`/`DROP ROLE`
    calls around it, which must never actually run against an
    unconditional `%` pattern in a test -- doing so against a real,
    shared local cluster would drop every unrelated database/role on it).
    `prefix` must be non-empty: an accidentally empty prefix here would
    silently widen this pattern to match everything, exactly the
    unconditional-sweep defect this function's own separation exists to
    make independently testable.
    """
    if not prefix:
        raise ValueError("_prefix_like_pattern requires a non-empty prefix")
    return f"{prefix}%"


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [_prefix_like_pattern(prefix)])
            databases = [row[0] for row in cur.fetchall()]
            db_error: Exception | None = None
            surviving: set[str] = set()
            for database in databases:
                dropped = False
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        dropped = True
                        break
                    except psycopg.errors.ObjectInUse as exc:
                        if db_error is None:
                            db_error = exc
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
                if not dropped:
                    surviving.add(database)

            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [_prefix_like_pattern(prefix)])
            roles = [row[0] for row in cur.fetchall()]
            for role in roles:
                try:
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
                except psycopg.errors.DependentObjectsStillExist:
                    admin.rollback()
                    for database in surviving:
                        try:
                            cur.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                                sql.Identifier(database), sql.Identifier(role)
                            ))
                        except psycopg.Error:
                            admin.rollback()
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
            if db_error is not None:
                raise db_error
    finally:
        admin.close()


def _sweep_stale_artifacts(admin_dsn: str) -> None:
    import re

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname ~ %s", [_STALE_PLATFORM_DB_PATTERN])
            stale = {row[0][: -len("_platform")] for row in cur.fetchall()}
            cur.execute("SELECT datname FROM pg_database WHERE datname ~ %s", [_STALE_APP_DB_PATTERN])
            stale |= {row[0][:_PREFIX_LENGTH] for row in cur.fetchall()}
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname ~ %s", [_STALE_ROLE_PATTERN])
            stale |= {row[0][:_PREFIX_LENGTH] for row in cur.fetchall()}
    finally:
        admin.close()

    for stale_prefix in stale:
        guard = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with guard.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", _lock_key(stale_prefix))
                (acquired,) = cur.fetchone()
            if not acquired:
                continue  # a live run owns this prefix
            _sweep_prefix(admin_dsn, stale_prefix)
        finally:
            guard.close()  # releases the advisory lock too (session-scoped)


# --------------------------------------------------------------------------
# HTTP session / failure plumbing.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Session:
    bearer: str  # "<credential_id>.<secret>" (http.py's own composite bearer form)
    application_id: str
    role: str


class _HttpFailure(Exception):
    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        self.is_problem_json = content_type.split(";")[0].strip() == PROBLEM_CONTENT_TYPE
        body: Any = None
        if self.is_problem_json:
            try:
                body = response.json()
            except ValueError:
                body = None
                self.is_problem_json = False
        self.body: dict[str, Any] | None = body if isinstance(body, dict) else None
        self.code: str | None = self.body.get("code") if self.body else None
        super().__init__(self._safe_summary())

    def _safe_summary(self) -> str:
        message = self.body.get("message") if self.body else None
        if isinstance(message, str):
            return f"HTTP {self.status_code} code={self.code!r}: {message}"
        return f"HTTP {self.status_code} (non-problem+json response)"


def _failure_details(failure: "_HttpFailure") -> Mapping[str, Any]:
    if failure.body is None:
        return {}
    details = failure.body.get("details")
    return details if isinstance(details, dict) else {}


class _AuthGate:
    """Wraps the real, read-only `PostgresCredentialStore` this composition's
    `HttpService` authenticates through, adding one adapter-only,
    test-harness toggle: `available=False` makes every call fail exactly
    the way a genuinely unreachable store already does
    (`AuthorizationStateUnavailable`), for `set_authorization_state_
    available` -- the same testing convenience `auth.CredentialStore`'s own
    in-memory boolean flag already gives the in-process adapter, applied
    here without touching `credential_store_postgres.py` itself (that
    module's own store has no such flag; production code should not carry
    a "pretend I am down" switch)."""

    def __init__(self, store: PostgresCredentialStore) -> None:
        self._store = store
        self.available = True

    def authenticate(self, secret: str, *, request_id=None):
        if not self.available:
            raise AuthorizationStateUnavailable("authorization unavailable")
        return self._store.authenticate(secret, request_id=request_id)

    def assert_active(self, principal, *, request_id=None) -> None:
        if not self.available:
            raise AuthorizationStateUnavailable("authorization unavailable")
        self._store.assert_active(principal, request_id=request_id)


class MitateDBHttpConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to MitateDB-api's real HTTP +
    PostgreSQL stack: `mitatedb_api.http.create_app` in front of an
    `HttpService` whose sessions are backed by `PostgresBackend` against a
    real, throwaway-provisioned local PostgreSQL 16 database.
    """

    name = "MitateDB-api (http+postgres)"

    def __init__(self) -> None:
        self._counter = 0
        admin_dsn = _admin_dsn()
        _require_reachable_postgres(admin_dsn)
        _sweep_stale_artifacts(admin_dsn)

        prefix = f"mitatedbhttp{secrets.token_hex(4)}"

        self._prefix_guard = psycopg.connect(admin_dsn, autocommit=True)
        with self._prefix_guard.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", _lock_key(prefix))

        self._script_dir = tempfile.mkdtemp(prefix="mitatedb_http_migrations_")
        try:
            self._platform = _bootstrap_platform(prefix, admin_dsn, Path(self._script_dir))
        except Exception:
            _sweep_prefix(admin_dsn, prefix)
            shutil.rmtree(self._script_dir, ignore_errors=True)
            self._prefix_guard.close()
            raise

        self._cleaned_up = False
        atexit.register(self._cleanup)

        try:
            self._app_pg: dict[str, _PgAppInfo] = {}
            # R-1's own risk note ("接続数の有限性... adapter は接続を確実に
            # 閉じる"): `backend_postgres.PostgresBackend` deliberately holds
            # TWO PERSISTENT connections per application for this WP's own
            # small, static-deployment use case (its own module docstring).
            # A conformance session provisions many dozens of short-lived
            # THROWAWAY applications (every `build_fixture()` call adds a
            # fresh pair), which would otherwise accumulate open connections
            # without bound and exhaust the local cluster's own
            # `max_connections` well before the suite finishes. `self._cells`
            # is therefore an LRU-bounded cache (`collections.OrderedDict`):
            # `_cell_factory` moves an entry to the end on every access,
            # and `provision_application` evicts (closes) the LEAST
            # recently used entry once the cap is exceeded -- bounding this
            # adapter's own steady-state connection count to
            # `2 * _MAX_OPEN_CELLS` regardless of how many total
            # applications this session ever provisions. Every conformance
            # test's own fixture apps stay at the "most recently used" end
            # for the whole duration of that one test (nothing else is
            # provisioned in between), so this never evicts an app a test
            # is actively using.
            from collections import OrderedDict
            self._cells: "OrderedDict[str, ApplicationCell]" = OrderedDict()
            self._contract_version_cache: str | None = None
            self._capability_probe_session: "_Session | None" = None
            self._capability_probe_app_id: "str | None" = None

            # Two PostgresCredentialStore instances against the SAME
            # platform database, matching R-4's own two-role architecture:
            # `self._read_store` (`<prefix>svc_api`, SELECT-only) is what
            # the real HTTP app authenticates every request through;
            # `self._write_store` (`<prefix>svc_controlplane`, full DML on
            # credentials/applications) is used directly by this adapter's
            # own privileged setup methods (`issue_credential`/
            # `revoke_credential`/...), mirroring r2db-http's identical
            # two-store split and its own documented reasoning (the read
            # path must run under the same least-privilege grants a real
            # deployment's application-plane process has).
            # WP-3 review finding (measured, not theoretical): a bounded
            # POOL was tried here too at first, but this adapter's own
            # workload is sequential (one pytest test body at a time, no
            # concurrent requests), unlike the HTTP composition root
            # (`main.py`) the WP-3 completion condition's bounded-pool
            # requirement actually targets. For a sequential caller, WP-2's
            # original per-call `connect()`/`close()` never holds more than
            # one credential-store connection open AT ONCE; a pool instead
            # holds up to `max_size` IDLE connections open continuously
            # between calls, which is a net INCREASE in this adapter's own
            # steady-state connection footprint against the shared local
            # cluster's `max_connections` -- exactly the resource this
            # adapter's own `_MAX_OPEN_CELLS` cap (above) exists to
            # protect. Measured directly: `r2db-api-http`'s own tests
            # (registered alongside this adapter in the SAME combined root
            # suite) intermittently failed on cluster-wide connection
            # exhaustion when this adapter pooled its credential stores;
            # reverting to `pool=None` (WP-2's original behavior) resolved
            # it. `pool.BoundedConnectionPool` remains genuinely used and
            # exercised by `main.py`'s own composition root, where the
            # concurrency it is actually for exists.
            # Q4 phase (design D-1(b), work order §4 WP-2 変更対象 D): a
            # real Postgres `application_audit` writer -- the SAME
            # `<prefix>svc_api` role/DSN `self._read_store` above already
            # connects with (migration 0005 grants it INSERT-only on this
            # table). No longer carries ANY timeout constructor argument
            # (the former per-connection `SET SESSION` this class used is
            # REMOVED product code) -- the two writer timeouts now come
            # from `<prefix>svc_api`'s own PostgreSQL role setting
            # (`_bootstrap_platform`'s own `0007_platform_declarations.
            # sql` run, the SAME shipped 5000ms/5000ms default `main.
            # build_app` relies on), applied automatically at login.
            self._application_durable_audit = PostgresApplicationAuditSink(
                self._platform.api_dsn, schema=self._platform.schema,
            )
            self._audit_router = AuditRouter(durable_sink=self._application_durable_audit)

            self._read_store = PostgresCredentialStore(
                self._platform.api_dsn, pepper="synthetic-conformance-pepper-mitatedb-http-0000",
                schema=self._platform.schema, audit_router=self._audit_router,
            )
            self._write_store = PostgresCredentialStore(
                self._platform.controlplane_dsn, pepper="synthetic-conformance-pepper-mitatedb-http-0000",
                schema=self._platform.schema,
            )
            self._gate = _AuthGate(self._read_store)

            def _cell_factory(application_id: str) -> ApplicationCell:
                cell = self._cells.get(application_id)
                if cell is None:
                    raise AssertionError(f"no PostgresBackend cell provisioned for {application_id!r}")
                self._cells.move_to_end(application_id)
                return cell

            self._service = HttpService(self._gate, _cell_factory, audit_router=self._audit_router)
            app = create_app(self._service, request_bytes_limit=1_048_576)
            self._app = app
            self._loop_owner = True
            import asyncio
            self._loop = asyncio.new_event_loop()
            self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)

            # ------------------------------------------------------------
            # control plane (WP-5 provided branch): the real `/control/v1`
            # ASGI app, assembled via THIS peer's own product composition
            # core (`control_composition.build_control_service` +
            # `control_http.create_control_app`) against the SAME
            # `mitatedbsvc_controlplane` role/DSN `_bootstrap_platform`
            # already provisioned above (R-4/R-8, mirrors r2db-http's own
            # `assemble_control_stack` reuse -- "peer の不足を埋めない":
            # this adapter never re-implements control-plane composition
            # logic of its own).
            #
            # Limits: mirrors the in-process adapter's own measured
            # rationale (`conformance_adapter_mitatedb.py`'s identical
            # comment) -- `applications=100/credentials_per_application=5/
            # control_requests_per_minute=200` are this adapter's own
            # CONFIGURED construction values, not an upper bound the
            # product enforces (Phase 5 D-3, Q3 案A, WP-4 removed
            # `ControlPlaneLimits`' former `[1, 200]` ceiling on all four
            # request-count classes). They still satisfy R-6's own
            # relational check with the same margin r2db-api measured
            # sufficient for its own combined suite.
            # ------------------------------------------------------------
            self._control_app_pepper = "synthetic-conformance-pepper-mitatedb-http-0000"
            self._control_pepper = "synthetic-conformance-pepper-mitatedb-http-ctl-0000"
            control_env = {
                "MITATEDB_CREDENTIAL_PEPPER": self._control_app_pepper,
                "MITATEDB_CONTROL_CREDENTIAL_PEPPER": self._control_pepper,
                "MITATEDB_CONTROLPLANE_DSN": self._platform.controlplane_dsn,
                "MITATEDB_PLATFORM_SCHEMA": self._platform.schema,
                "MITATEDB_CONTROL_APPLICATIONS_LIMIT": "100",
                "MITATEDB_CONTROL_CREDENTIALS_PER_APPLICATION_LIMIT": "5",
                "MITATEDB_CONTROL_REQUESTS_PER_MINUTE_LIMIT": "200",
                # Phase 4 WP-3(b) (design D-5): the real `<prefix>svc_
                # auditreader` DSN -- `visibility_lag_ms` is now DERIVED
                # by `build_control_service` from `pg_db_role_setting`
                # (design D-1(c), `platform_declarations.derive_
                # visibility_lag_ms`) -- the SAME shipped 5000ms/5000ms
                # role-level default `_bootstrap_platform`'s own `0007`
                # run seeds, matching `self._application_durable_audit`'s
                # own (now argument-free) writer connection above.
                "MITATEDB_AUDIT_DSN": self._platform.auditreader_dsn,
                # Q4 phase (design D-2, work order §4 WP-2 変更対象 D):
                # `MITATEDB_DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL` are
                # REMOVED env vars (F-2) -- `surfaces` now comes from
                # `<registry>.platform_declarations`, seeded by
                # `_bootstrap_platform` above with the SAME `_DATA_
                # SURFACE_BASE_URL`/`_CONTROL_SURFACE_BASE_URL` values
                # this control_env dict used to pass directly. This is
                # the load-bearing half of design §6.1 α / §1.5 finding
                # 10: `build_control_service` is a REAL composition root
                # call, so the declarations table's own read matters here
                # (unlike r2db-api's HTTP plug, which injects `surfaces`
                # directly and never exercises this read at all).
            }
            # Port v1.10 addendum A: kept on the instance (not just this
            # local `control_env`) so `isolated_control_surface()` can
            # call `build_control_service` a SECOND time later, against
            # the identical environment, without reconstructing it.
            self._control_env = control_env
            self._control_service = build_control_service(control_env)
            self._control_app = create_control_app(
                self._control_service, request_bytes_limit=self._control_service.limits.request_bytes)
            self._control_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._control_app), base_url=BASE_URL)

            # `control_credential()`'s own maintained handle (memoize +
            # call-time validity check -- port v1.5 WP-1 independent review
            # major M-4), mirroring both the in-process adapter's and
            # r2db-http's identical mechanism.
            self._control_credential_ref: str | None = None
            self._control_credential_secret: str | None = None
        except Exception:
            self._cleanup()
            atexit.unregister(self._cleanup)
            raise

    def _cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        try:
            for cell in self._cells.values():
                try:
                    cell._backend.close()
                except Exception:
                    pass
            try:
                self._read_store.close()
                self._write_store.close()
            except Exception:
                pass
            _sweep_prefix(self._platform.admin_dsn, self._platform.prefix)
        finally:
            shutil.rmtree(self._script_dir, ignore_errors=True)
            self._prefix_guard.close()

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    def _run(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)

    def _send(
        self, method: str, path: str, session: "_Session | None", *,
        json_body: dict[str, Any] | None = None,
        extra_header_pairs: Sequence[tuple[str, str]] = (),
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        header_pairs: list[tuple[str, str]] = []
        if session is not None:
            header_pairs.append(("authorization", f"Bearer {session.bearer}"))
        header_pairs.extend(extra_header_pairs)
        request = self._client.build_request(method, path, json=json_body, headers=header_pairs, params=params)
        response = self._run(self._client.send(request))
        if response.status_code >= 400:
            failure = _HttpFailure(response)
            raise ConformanceDenial(
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                details=_failure_details(failure),
            ) from failure
        if not response.content:
            return {}
        return response.json()

    def _data_path(self, entity: str, suffix: str) -> str:
        return f"/v1/data/{quote(entity, safe='')}/{suffix}"

    def _query(self, session: _Session, entity: str, *, select, where=None, order_by=None, page_size=None) -> dict[str, Any]:
        body: dict[str, Any] = {"select": list(select)}
        if where is not None:
            body["where"] = where
        if order_by is not None:
            body["order_by"] = order_by
        if page_size is not None:
            body["page"] = {"size": page_size}
        return self._send("POST", self._data_path(entity, "query"), session, json_body=body)

    def _mutate(self, session: _Session, entity: str, operations: list[dict[str, Any]], *, extra_body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"operations": operations}
        if extra_body:
            body.update(extra_body)
        return self._send("POST", self._data_path(entity, "mutations"), session, json_body=body)

    def _cross_mutate(self, session: _Session, operations: list[dict[str, Any]]) -> dict[str, Any]:
        # P35 WP-2/WP-3: the cross-entity counterpart of `_mutate` above --
        # a fixed path (`POST /v1/data/mutations`, no per-request entity
        # segment), each operation dict carrying its OWN `entity` key
        # instead. `http.py::post_cross_entity_mutate` is the real, mounted
        # dispatcher this composition genuinely receives the request
        # through (`cross_entity_mutation: partial` as of WP-2's flip).
        return self._send("POST", "/v1/data/mutations", session, json_body={"operations": operations})

    def _schema(self, session: _Session, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/v1/schema/operations", session, json_body=dict(body))

    # ------------------------------------------------------------------
    # control plane (privileged, out-of-band setup)
    # ------------------------------------------------------------------

    # See `self._cells`'s own docstring (`__init__`) for why this is
    # bounded: 6 concurrently-open application cells (12 persistent
    # PostgreSQL connections) comfortably covers this suite's own
    # per-test working set (almost always 2 apps, occasionally 3), while
    # keeping this adapter's own steady-state connection footprint small
    # relative to a local cluster's `max_connections` -- kept
    # deliberately tight (measured down from an initial 16/32 during this
    # WP's own development: the FULL combined root suite runs FOUR real-
    # Postgres-backed adapters/compositions at once now (`r2db-api`,
    # `r2db-api-http`, and both MitateDB adapters), and r2db-api-http's
    # own already-tight connection budget was observed to intermittently
    # fail under the combined load at the higher cap) -- regardless of
    # how many THROWAWAY applications this session provisions in total.
    _MAX_OPEN_CELLS = 6

    def _evict_cells_over_cap(self) -> None:
        while len(self._cells) > self._MAX_OPEN_CELLS:
            _evicted_id, evicted_cell = self._cells.popitem(last=False)
            evicted_cell._backend.close()

    def provision_application(self, application_id: str) -> None:
        info = _provision_pg_app(self._platform, application_id)
        self._app_pg[application_id] = info
        self._cells[application_id] = ApplicationCell(
            application_id, FoundationConfig(
                control_plane_status="enabled",
                # Phase 6 WP-3 (design D-2): the SAME pair `control_env`
                # above declares to the control-plane process -- one
                # Python module constant, never two independently-
                # configured copies (this plug's own analogue of "the
                # deployer configured both processes consistently").
                data_base_url=_DATA_SURFACE_BASE_URL, control_base_url=_CONTROL_SURFACE_BASE_URL,
            ),
            backend=PostgresBackend(info.runtime_dsn, info.developer_dsn),
            audit_router=self._audit_router,
        )
        self._evict_cells_over_cap()
        # Registry row: written by `mitatedb_registry.begin_provision_
        # application`/`finish_provision_application` inside the 0003
        # script this call already ran -- `enabled` defaults `TRUE`
        # (migration 0002's own column default).

    def deprovision_application(self, application_id: str) -> None:
        # WP-5 flip: operator-privileged test-harness cleanup (never a
        # public capability -- there is no `deprovision`/`unregister`
        # entry point anywhere on this peer's own contract surface).
        # Real, full teardown (drops the database + 2 roles) via the same
        # migration script this adapter's own `close()` sweep uses --
        # C-14 vector 5's own `applications`-bound drive must genuinely
        # free registry+database+role state, not merely hide a row.
        self._cells.pop(application_id, None)
        self._app_pg.pop(application_id, None)
        _deprovision_pg_app(self._platform, application_id)

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        # Phase 6 WP-3 (design D-1(d)): `PostgresCredentialStore.issue`
        # itself now returns the complete, ready-to-present bearer as its
        # second element -- this adapter presents it verbatim (port
        # v1.10's own regulation), never composing it from `credential_id`
        # + a bare secret itself.
        role_enum = role if isinstance(role, Role) else Role(role)
        credential_id, bearer = self._write_store.issue(application_id, role_enum)
        return CredentialHandle(
            credential_ref=credential_id, application_id=application_id, role=role_enum.value,
            secret=bearer,
        )

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._write_store.revoke(handle.credential_ref)

    def tampered_bearer(self, handle: "CredentialHandle | ControlCredentialHandle") -> str:
        """port v1.10 追補 (supervisor ruling 2026-09-04, brief item C):
        this peer's own locator bearer shape (`credential_wire.split_bearer_locator`, called once inside
        each store's authenticate; HTTP boundaries pass the bearer verbatim) is `<credential_id>.<secret>` --
        a bearer naming the SAME real `credential_id` with a fresh,
        never-issued secret authenticates as `credential_id`-known-but-
        digest-mismatched, exactly the "bogus secret on a real
        credential_ref" vector `test_c15` needs. Composition ALLOWLISTED
        at this one line (test_c19_client_self_sufficiency.py's own
        `_COMPOSITION_ALLOWLIST`, port docstring's own "the ONLY place
        ANY adapter composes a bearer" rule)."""
        return f"{handle.credential_ref}.{fresh_identifier('tampered')}"

    def disable_application(self, application_id: str) -> None:
        self._write_store.disable_application(application_id)

    def enable_application(self, application_id: str) -> None:
        self._write_store.enable_application(application_id)

    def set_authorization_state_available(self, available: bool) -> None:
        self._gate.available = bool(available)

    def propagation_bound_ms(self) -> int:
        # Every single HTTP request re-authenticates and re-checks
        # authorization state from scratch (`HttpService.authenticate`,
        # `ApplicationRuntime.__authorize` -> `assert_active`, called by
        # every handler on every request) -- there is no session cache
        # anywhere in this stack, so propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # WP-5 (design v1.2 R-8 second-round M-1): the probe Application
        # (a real database + 2 roles on this composition) is provisioned
        # ONCE and its session reused for every later call -- mirrors the
        # in-process adapter's identical fix. Directly relieves this
        # adapter's own real Postgres DB/role churn (each probe used to
        # cost one real `CREATE DATABASE` + 2 `CREATE ROLE`).
        #
        # First-execution finding (this WP): a bare "provision once, reuse
        # forever" cache is UNSAFE on this specific adapter -- unlike the
        # in-process adapter's unbounded dict, `self._cells` is a bounded
        # LRU cache (`_MAX_OPEN_CELLS`, `__init__`'s own comment) that
        # evicts (and CLOSES) the least-recently-used entry once another
        # `provision_application` call pushes it over the cap. A probe
        # cell that goes long enough between `capability_document()` calls
        # (measured directly: running the combined suite reproduced this)
        # gets evicted like any other application's cell, and every LATER
        # reuse then crashes `_cell_factory`'s own `AssertionError` --
        # surfaced as a generic 503 `SERVICE_UNAVAILABLE`, not a
        # deliberate denial. Re-provisioning when the cached probe's own
        # cell is no longer present -- the same self-healing shape
        # `_ensure_control_actor` already uses for a stale control
        # credential -- fixes this without giving up the steady-state
        # savings the cache exists for.
        if self._capability_probe_session is None or self._capability_probe_app_id not in self._cells:
            self._counter += 1
            # application_id is bound by the control-plane's stricter
            # 33-byte rule (`^[a-z][a-z0-9_]{0,32}$`, migration 0002's own
            # `begin_provision_application` check) -- kept short so
            # `self._counter` growing over a long test session never risks
            # overflowing it.
            probe_app = f"cap_probe_{self._counter}_{uuid.uuid4().hex[:8]}"
            self.provision_application(probe_app)
            handle = self.issue_credential(probe_app, "runtime")
            self._capability_probe_session = self.authenticate(handle)
            self._capability_probe_app_id = probe_app
        return self._send("GET", "/v1/capabilities", self._capability_probe_session)

    def _declared_contract_version(self) -> str:
        if self._contract_version_cache is None:
            self._contract_version_cache = str(self.capability_document()["contract_version"])
        return self._contract_version_cache

    def _resolve_confirmation(self, confirmation: Any, *, probe: Callable[[], Any], legacy_token: Any) -> Any:
        if confirmation is not VALID_CONFIRMATION:
            return confirmation
        return resolve_valid_confirmation(
            contract_version=self._declared_contract_version(), legacy_token=legacy_token, probe=probe
        )

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5) -- PROVIDED branch (WP-5 flip)
    # ------------------------------------------------------------------
    #
    # The real, mounted `/control/v1` ASGI app (`self._control_app`/
    # `self._control_client`, `__init__` above) -- every one of the 14
    # port v1.5 operations below presents its request to that same real
    # surface over real HTTP, exactly as a genuine `/control/v1` caller
    # would. `bootstrap`/`reset`/the internal handle-repair path drive the
    # real out-of-band CLI ritual as a subprocess (`python -m mitatedb_api.
    # ops bootstrap`/`reset`, R-8: "実 CLI subprocess") -- never this
    # adapter re-implementing ceremony logic against the stores directly.

    def _control_send(
        self, method: str, path: str, actor: "CredentialHandle | ControlCredentialHandle", *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Phase 6 WP-3 (design D-1(d), port v1.10 (a)): `.secret` on
        # EITHER handle type is now already the complete, ready-to-present
        # bearer -- every real issuance point (`PostgresCredentialStore.
        # issue`, the `/control/v1` issue/rotate JSON response, `ops.py`'s
        # own CLI output for bootstrap/reset/self-rotate) hands one back
        # pre-composed. This adapter presents it verbatim; it never
        # composes a bearer from `credential_ref` + `secret` itself
        # (port v1.10's own regulation -- the static fixture this same WP
        # un-xfails on this file scans for exactly this kind of
        # composition).
        bearer = actor.secret
        headers = {"authorization": f"Bearer {bearer}"}
        request = self._control_client.build_request(method, path, json=json_body, headers=headers)
        response = self._run(self._control_client.send(request))
        if response.status_code >= 400:
            failure = _HttpFailure(response)
            raise ConformanceDenial(
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                details=_failure_details(failure),
            ) from failure
        if not response.content:
            return {}
        return response.json()

    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        return self._control_send("GET", "/control/v1/capabilities", actor)

    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        return self._control_send(
            "POST", "/control/v1/applications", actor, json_body={"application_id": application_id})

    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        result = self._control_send("GET", "/control/v1/applications", actor)
        return result["applications"]

    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        verb = "enable" if enabled else "disable"
        path = f"/control/v1/applications/{quote(application_id, safe='')}/{verb}"
        return self._control_send("POST", path, actor)

    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        result = self._control_send(
            "POST", "/control/v1/credentials", actor, json_body={"application_id": application_id, "role": role})
        return CredentialHandle(
            credential_ref=result["credential_id"], application_id=result["application_id"], role=result["role"],
            # Phase 6 WP-3 (design D-1(d)): `POST /control/v1/credentials`
            # itself now returns the complete bearer as `secret`
            # (`control_http.py::_with_composed_secret`) -- used verbatim.
            secret=result["secret"],
        )

    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        result = self._control_send("GET", "/control/v1/credentials", actor)
        return result["credentials"]

    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        path = f"/control/v1/credentials/{quote(credential_ref, safe='')}/rotate"
        return self._control_send("POST", path, actor)

    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        path = f"/control/v1/credentials/{quote(credential_ref, safe='')}/revoke"
        body: dict[str, Any] = {}
        if destructive is not None:
            body["destructive"] = destructive
        if confirmation is not None:
            body["confirmation"] = confirmation
        return self._control_send("POST", path, actor, json_body=body or None)

    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        verb = "enable" if enabled else "disable"
        path = f"/control/v1/credentials/{quote(credential_ref, safe='')}/{verb}"
        return self._control_send("POST", path, actor)

    # ---- ritual (out-of-band CLI subprocess, R-8) --------------------

    def _run_ops_cli(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["MITATEDB_CONTROLPLANE_DSN"] = self._platform.controlplane_dsn
        env["MITATEDB_CONTROL_CREDENTIAL_PEPPER"] = self._control_pepper
        env["MITATEDB_CREDENTIAL_PEPPER"] = self._control_app_pepper
        env["MITATEDB_PLATFORM_SCHEMA"] = self._platform.schema
        return subprocess.run(
            [sys.executable, "-m", "mitatedb_api.ops", *args], capture_output=True, text=True, env=env)

    def _run_reset_ops_cli(self) -> subprocess.CompletedProcess:
        """`python -m mitatedb_api.ops reset` self-gates on the ceremony
        core's own declare-and-echo check (`ops.py`'s own module
        docstring): a first, unconfirmed invocation is refused (exit 2,
        the declaration as one line of JSON on stderr); this reads
        `required_confirmation` from that declaration and echoes it back
        on a second invocation -- this adapter's own equivalent of an
        operator following the CLI's own printed instructions by hand.
        Returns the SECOND (confirmed) invocation's own `CompletedProcess`
        on the ordinary path."""
        probe = self._run_ops_cli("reset")
        if probe.returncode != 2:
            # Not this gate's own refusal shape at all (e.g. a genuine
            # database/environment failure) -- surface it unmodified.
            return probe
        lines = [line for line in probe.stderr.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError(f"mitatedb_api.ops reset exited 2 with no parseable declaration on stderr: {probe.stderr!r}")
        try:
            declaration = json.loads(lines[-1])
            phrase = declaration["details"]["required_confirmation"]
        except Exception as exc:
            raise RuntimeError(f"could not parse mitatedb_api.ops reset's own declaration: {probe.stderr!r}") from exc
        return self._run_ops_cli("reset", "--confirm", phrase)

    def _parse_issued_stdout(self, stdout: str) -> tuple[str, str]:
        credential_id: str | None = None
        secret: str | None = None
        for line in stdout.splitlines():
            if line.startswith("credential_id: "):
                credential_id = line[len("credential_id: "):].strip()
            elif line.startswith("secret: "):
                secret = line[len("secret: "):].strip()
        if not credential_id or not secret:
            raise RuntimeError(f"could not parse credential_id/secret from mitatedb_api.ops stdout: {stdout!r}")
        return credential_id, secret

    def _ops_cli_denial(self, result: subprocess.CompletedProcess) -> ConformanceDenial:
        """Translates a non-zero `python -m mitatedb_api.ops` exit into a
        `ConformanceDenial` -- `ops.py`'s own `main()` prints one line of
        JSON (`{"code": ..., "message": ...}`) on stderr for every
        `FoundationError` (this WP's own addition to that module,
        specifically so this adapter has a stable machine interface to
        parse rather than pattern-matching free text). `message` is never
        placed on `ConformanceDenial` itself (design section 4.1: the
        native message text is deliberately excluded from that type) --
        only `details` (structured, non-free-text) is passed through, here
        always empty (`ops.py`'s own JSON line carries no separate
        `details` object outside the destructive-confirmation gate, which
        this adapter's `_run_reset_ops_cli` already resolves before ever
        reaching this path)."""
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        code = UNCLASSIFIED
        if lines:
            try:
                body = json.loads(lines[-1])
                if isinstance(body, dict) and isinstance(body.get("code"), str):
                    code = body["code"]
            except Exception:
                pass
        return ConformanceDenial(code=code, adapter=self.name, native_type="mitatedb_api.ops")

    def bootstrap(self) -> ControlCredentialHandle:
        result = self._run_ops_cli("bootstrap")
        if result.returncode != 0:
            raise self._ops_cli_denial(result)
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        return ControlCredentialHandle(credential_ref=credential_id, secret=secret)

    def reset(self) -> ControlCredentialHandle:
        result = self._run_reset_ops_cli()
        if result.returncode != 0:
            raise self._ops_cli_denial(result)
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        return ControlCredentialHandle(credential_ref=credential_id, secret=secret)

    def _control_credentials_has_any(self) -> bool:
        """Read-only existence probe used only to choose `bootstrap` vs
        `reset` in `_repair_control_actor` -- a direct, privileged read of
        `control_credentials`' row count via `mitatedbsvc_controlplane`
        (which DOES hold `SELECT` on this one table, migration 0002 --
        unlike `control_audit`, R-4)."""
        statement = sql.SQL("SELECT count(*) FROM {table}").format(
            table=sql.Identifier(self._platform.schema, "control_credentials"))
        with psycopg.connect(self._platform.controlplane_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(statement)
                (count,) = cur.fetchone()
        return count > 0

    def _control_actor_is_live(self, credential_ref: str, secret: str) -> bool:
        try:
            self._control_send(
                "GET", "/control/v1/capabilities", ControlCredentialHandle(credential_ref=credential_ref, secret=secret))
            return True
        except ConformanceDenial:
            return False

    def _ensure_control_actor(self) -> ControlCredentialHandle:
        """R-8 (`adapter の control credential handle はキャッシュし毎回
        probe しない` -- read literally as "do not re-PROVISION a fresh
        one every call", not "never re-validate the one already cached").
        First-execution finding (this WP): a bare, unconditional cache
        (this method's own original WP-5 revision) goes stale silently the
        moment a LATER test's own real `adapter.reset()` call revokes
        every existing control credential including the one this cache
        still names -- `control_credential()` then hands out a dead handle
        to whichever test asks next, which fails downstream with a
        confusing `AUTH_INVALID` unrelated to what that test was actually
        checking (measured directly: `test_c15...audit_and_denials_are_
        recorded`, which runs after `test_c15...reset...atomically` in the
        same session-scoped adapter). One cheap `GET .../capabilities`
        against the CACHED handle -- not a fresh mint -- confirms liveness
        before handing it out; only a genuinely dead cache pays the cost
        of `_repair_control_actor`'s own real ritual run."""
        if self._control_credential_ref is not None and self._control_actor_is_live(
                self._control_credential_ref, self._control_credential_secret):
            return ControlCredentialHandle(credential_ref=self._control_credential_ref, secret=self._control_credential_secret)
        return self._repair_control_actor()

    def _repair_control_actor(self) -> ControlCredentialHandle:
        """Mints a genuinely fresh, must-rotate-cleared control credential
        via the real out-of-band CLI ritual, then clears `must_rotate` via
        one real in-band self-rotate HTTP call, and updates the tracked
        cache (WP-1 M-4: never a memoized value past validity)."""
        has_any = self._control_credentials_has_any()
        result = self._run_reset_ops_cli() if has_any else self._run_ops_cli("bootstrap")
        if result.returncode != 0:
            raise RuntimeError(f"mitatedb_api.ops {'reset' if has_any else 'bootstrap'} failed: {result.stderr}")
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        rotated = self._control_send(
            "POST", f"/control/v1/credentials/{quote(credential_id, safe='')}/rotate",
            ControlCredentialHandle(credential_ref=credential_id, secret=secret),
        )
        self._control_credential_ref = credential_id
        self._control_credential_secret = rotated["secret"]
        return ControlCredentialHandle(credential_ref=credential_id, secret=self._control_credential_secret)

    def control_credential(self) -> ControlCredentialHandle:
        return self._ensure_control_actor()

    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        # `mitatedbsvc_controlplane` has INSERT-only on `control_audit`
        # (R-4) -- reads with `provision_dsn` (the schema owner), the same
        # separate reader R-8 calls for.
        return read_control_audit_events(self._platform.provision_dsn, self._platform.schema)

    # port v1.10 addendum A (supervisor ruling 2026-09-04, C-14 vector 5's
    # own test primitive -- see adapter.py's own docstring for the full
    # rationale). Real HTTP `/control/v1` app/client, built via THIS
    # peer's own product composition core (`build_control_service`, the
    # SAME real function `__init__` above already calls) against the
    # SAME `self._control_env` (identical DSN/schema/pepper/limits) --
    # so the same registered applications/credentials authenticate --
    # but a genuinely fresh `ControlPlaneService`, whose own rate window
    # starts empty. No pooled connections to release on exit (`build_
    # control_service`'s own registries/backend open one connection per
    # call, mirrored from this peer's own established convention, per
    # that function's own docstring) -- only the fresh httpx client.
    #
    # Phase 6 WP-3 (design D-1(d)): `.secret` on either handle type is
    # already the complete bearer (this file's own module-level note) --
    # presented verbatim, never recomposed here.
    @contextmanager
    def isolated_control_surface(self):
        service = build_control_service(self._control_env)
        app = create_control_app(service, request_bytes_limit=service.limits.request_bytes)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)
        try:
            def call(actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
                bearer = actor.secret
                request = client.build_request(
                    "GET", "/control/v1/capabilities", headers=[("authorization", f"Bearer {bearer}")]
                )
                response = self._run(client.send(request))
                if response.status_code >= 400:
                    failure = _HttpFailure(response)
                    raise ConformanceDenial(
                        code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                        details=_failure_details(failure),
                    ) from failure
                return response.json()

            yield call
        finally:
            self._run(client.aclose())

    # ------------------------------------------------------------------
    # audit_query surface (port v1.8, phase 4 WP-3(b) PROVIDED branch).
    # Real HTTP POST /v1/audit/query -- against the CONTROL client (`self.
    # _control_client`), never the data-plane client (design R1 / work
    # order instruction: exercises the alias path, never `/control/v1/
    # audit/query`).
    # ------------------------------------------------------------------

    def _audit_query_status(self) -> str:
        # Reads via this adapter's OWN privileged control credential
        # (`control_credential()`), never via the `actor` a caller of
        # `audit_query` supplies -- see conformance_adapter_r2db_http.py's
        # identical method for the full C-09-vector-3 rationale.
        control_actor = self.control_credential()
        document = self.control_capabilities(control_actor)
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
                "declare-first discipline does not send an HTTP request to the real /v1/audit/query alias "
                "(design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md §8.4's extended SurfaceAbsent meaning)",
            )
        # design R1 / work order WP-1 §"変更対象": exercises the /v1/
        # audit/query alias against the control base URL, matching
        # conformance_adapter_r2db_http.py's own identical choice.
        return self._control_send("POST", "/v1/audit/query", actor, json_body=dict(request))

    # port v1.8
    def flush_audit_buffer(self) -> None:
        if self._audit_query_status() not in ("enabled", "partial"):
            raise self._audit_surface_absent(
                "flush_audit_buffer",
                "audit_query is not declared enabled/partial -- there is no bounded buffer to flush on this "
                "deployment's own declared posture",
            )
        # Privileged, out-of-band hook -- calls the real, shared `Audit
        # Router` DIRECTLY (never a wire call: there is no HTTP endpoint
        # for this on either host, by design). `force_expire_denial_
        # windows=True`: flushes every currently-open denial-coalescing
        # window too, not only expired ones.
        self._audit_router.flush(force_expire_denial_windows=True)

    # port v1.8
    def audit_visibility_lag_ms(self) -> int:
        control_actor = self.control_credential()
        document = self.control_capabilities(control_actor)
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
    # V1.md §6.2): `_control_send`'s own twin, built specifically for
    # `audit_query_on_data_plane_host` -- reaches this adapter's OWN
    # DATA-plane app/client (`self._client`), never the control one (the
    # mirror image of `audit_query` above, which never reaches the data-
    # plane client). Phase 6 WP-3 (design D-1(d)): `.secret` on either
    # handle type is already the complete bearer, presented verbatim
    # (the data-plane host's own store-internal `split_bearer_locator`/`CredentialStore.
    # authenticate` still expects the identical composite wire form, but
    # that form now arrives pre-composed, never assembled here). No
    # declare-first `SurfaceAbsent` gate here: `/v1/audit/query` is
    # unconditionally mounted on the data-plane app regardless of
    # `audit_query`'s own declared status (`http.py`'s own `_ROUTES`), so
    # a real request always reaches a real handler.
    def audit_query_on_data_plane_host(
        self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        bearer = actor.secret
        headers = {"authorization": f"Bearer {bearer}"}
        req = self._client.build_request("POST", "/v1/audit/query", json=dict(request), headers=headers)
        response = self._run(self._client.send(req))
        if response.status_code >= 400:
            failure = _HttpFailure(response)
            raise ConformanceDenial(
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                details=_failure_details(failure),
            ) from failure
        if not response.content:
            return {}
        return response.json()

    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    # pre-1.6.0 topology-declaration method this adapter once implemented
    # here is removed -- the port's own `surfaces_cohosted` free function
    # is now surfaces-derived only (both peers declare 1.6.0
    # unconditionally).

    # ------------------------------------------------------------------
    # application plane
    # ------------------------------------------------------------------

    def authenticate(self, handle: "CredentialHandle | ControlCredentialHandle") -> object:
        # A real HTTP round trip validates the bearer up front (fail fast,
        # same as a real client discovering an invalid credential
        # immediately) -- `GET /v1/capabilities` is application-authed
        # (M-9) and touches nothing but authentication + `assert_active`.
        #
        # WP-5 flip (first-execution finding): C-14 vector 2 presents a
        # REAL `ControlCredentialHandle` here (`control_plane_status:
        # enabled` is exercised for the first time this WP) -- that type
        # has no `application_id`/`role` attribute at all (design: a
        # control credential belongs to no Application). `getattr(...,
        # None)` avoids a harness-level `AttributeError` on that access;
        # the actual rejection this vector requires still comes from the
        # real server -- a control credential's digest matches no row in
        # `<schema>.credentials` at all (it lives in the separate
        # `control_credentials` table, R-4), so `_send` below still raises
        # a genuine `ConformanceDenial` from the real HTTP response.
        session = _Session(
            bearer=handle.secret,
            application_id=getattr(handle, "application_id", None),
            role=getattr(handle, "role", None),
        )
        self._send("GET", "/v1/capabilities", session)
        return session

    def scope_of(self, session: object) -> ScopeView:
        assert isinstance(session, _Session)
        return ScopeView(application_id=session.application_id, role=session.role)

    def create_entity(self, session: object, entity: str, fields: Mapping[str, str]) -> None:
        assert isinstance(session, _Session)
        # P3-D1: fields omitted on `create_entity` (this peer's own base
        # `id: integer` column) + one `add_field` per named field -- the
        # only contract-shaped way to build a mixed-type entity over this
        # peer's own HTTP surface (design v1.2 §0 exception).
        self._schema(session, {"operation": "create_entity", "entity": entity})
        for field_name, port_type in fields.items():
            wire_type = _PORT_FIELD_TYPE_TO_WIRE[port_type]
            self._schema(session, {"operation": "add_field", "entity": entity, "field": field_name, "field_type": wire_type})

    def insert(self, session: object, entity: str, values: Mapping[str, Any]) -> None:
        assert isinstance(session, _Session)
        self._mutate(session, entity, [{"operation": "insert", "values": dict(values)}])

    def select_eq(self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any) -> list[dict]:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        result = self._query(session, entity, select=select, where=where)
        return result["items"]

    def attempt_filter(self, session: object, entity: str, select: Sequence[str], field: str, operator: str, value: Any) -> list[dict]:
        assert isinstance(session, _Session)
        result = self._query(session, entity, select=select, where=[{"field": field, "operator": operator, "value": value}])
        return result["items"]

    def delete(self, session: object, entity: str, field: str, value: Any, *, destructive: bool, confirmation: str | None) -> int:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}]

        def probe() -> None:
            self._mutate(session, entity, [{"operation": "delete", "where": where, "destructive": True}])

        peer_confirm = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
        op: dict[str, Any] = {"operation": "delete", "where": where, "destructive": destructive}
        if peer_confirm is not None:
            op["confirmation"] = peer_confirm
        result = self._mutate(session, entity, [op])
        return result["affected"]

    def count(self, session: object, entity: str) -> int:
        assert isinstance(session, _Session)
        # No catalog to discover field names from (`application_catalog:
        # unavailable`, and `GET /v1/catalog` itself is a real,
        # present `CAPABILITY_UNSUPPORTED` denial on this composition --
        # see `catalog_document` below). Every entity this adapter's own
        # `create_entity` builds always carries the base `id` column
        # (P3-D1's own default), so `id` is always a safe, minimal
        # `select` for counting rows.
        # No `page.size` override: the server's own configured
        # `result_items` default bound (500, `config.FoundationConfig.
        # max_result_rows`) already comfortably covers this suite's own
        # small fixtures, and requesting MORE than that bound would itself
        # trigger a real `LIMIT_EXCEEDED` -- this method counts rows, it
        # does not need to probe the limit.
        result = self._query(session, entity, select=["id"])
        return len(result["items"])

    def entities(self, session: object) -> set[str]:
        assert isinstance(session, _Session)
        # Phase 6 WP-3 (design D-3): `application_catalog` is now
        # `enabled` and `GET /v1/catalog` is real, but THIS method stays a
        # privileged, direct-Postgres reach-around deliberately -- several
        # callers (this file's own C-01 scope-binding use in particular)
        # need a ground truth independent of the peer's own self-reported
        # catalog, precisely so a bug in the peer's own catalog reporting
        # cannot mask a real scope-binding leak by omission. Via a direct,
        # adapter-privileged Postgres connection to this application's own
        # developer role/database (never through the real API), after an
        # explicit re-authentication check so a revoked/disabled/
        # unavailable session is denied here exactly as it would be for
        # any other session operation. Excludes BOTH this peer's own
        # bookkeeping tables -- `_mdb_schema_revision` (schema-revision
        # counter) and `_mdb_field_types` (the declared-type registry
        # itself, this same WP) -- neither of which is a real entity a
        # `create_entity`/`create_collection` caller ever created.
        self._send("GET", "/v1/capabilities", session)
        info = self._app_pg[session.application_id]
        conn = psycopg.connect(info.developer_dsn, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name NOT IN (%s, %s)",
                    [_SCHEMA_REVISION_TABLE, _FIELD_TYPES_TABLE],
                )
                return {row[0] for row in cur.fetchall()}
        finally:
            conn.close()

    def catalog_document(self, session: object) -> Mapping[str, Any] | str:
        assert isinstance(session, _Session)
        # R-3 known difference (2): unlike the in-process adapter
        # (`CATALOG_SURFACE_ABSENT`), `GET /v1/catalog` IS a real, mounted
        # entry point on this composition -- it always denies with a real
        # `CAPABILITY_UNSUPPORTED`, which this lets propagate naturally
        # rather than fabricating the structural-absence sentinel.
        return self._send("GET", "/v1/catalog", session)

    # port v1.10 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
    # V1.md section 6.1 item 3, D-3). Real HTTP POST to this peer's real
    # schema-operation endpoint, carrying the contract's own `fields`/
    # `field_types` verbatim and PARTIAL where the caller gave a partial
    # `field_types` -- mirrors `conformance_adapter_r2db_http.py`'s
    # identical method (this port method never fills in `json` for an
    # undeclared name itself: D-3(ii)'s default is the PEER's own job to
    # apply on a partial request, and the round-trip vector's own
    # "undeclared field reports json" check (design section 6.2 item 3
    # (iii)) requires a genuinely partial request to reach the peer, not
    # one this method pre-filled). Unreachable as of this WP (declare-
    # first gated at 1.6.0; `application_catalog`/`schema_operations` are
    # also still `unavailable` on this composition today, so a real call
    # here currently denies with `CAPABILITY_UNSUPPORTED` before the
    # peer's own field-type vocabulary is even consulted) -- written for
    # WP-3's real eventual shape, not a stub.
    def create_entity_with_declared_types(
        self, session: object, entity: str, fields: Sequence[str], field_types: Mapping[str, str] | None
    ) -> None:
        assert isinstance(session, _Session)
        body: dict[str, Any] = {"operation": "create_entity", "entity": entity, "fields": list(fields)}
        if field_types:
            body["field_types"] = dict(field_types)
        self._schema(session, body)

    # port v1.10 (same WP as above).
    def add_field_with_declared_type(self, session: object, entity: str, field: str, field_type: str) -> None:
        assert isinstance(session, _Session)
        self._schema(session, {"operation": "add_field", "entity": entity, "field": field, "field_type": field_type})

    def _attempt_mutation_item(
        self, entity: str, operation: str, *, values, where_field, where_value,
        expected_revision, unique_key,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"operation": operation}
        if values is not None:
            item["values"] = dict(values)
        if where_field is not None:
            item["where"] = [{"field": where_field, "operator": "eq", "value": where_value}]
        if expected_revision is not None:
            item["expected_revision"] = expected_revision
        if unique_key is not None:
            item["unique_key"] = unique_key
        return item

    def attempt_mutation(
        self, session: object, entity: str, operation: str, *, values, where_field, where_value,
        expected_revision=None, unique_key=None,
    ) -> int:
        assert isinstance(session, _Session)
        item = self._attempt_mutation_item(
            entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        result = self._mutate(session, entity, [item])
        return result["affected"]

    def attempt_mutation_with_addresses(
        self, session: object, entity: str, operation: str, *, values, where_field, where_value,
        expected_revision=None, unique_key=None,
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        assert isinstance(session, _Session)
        item = self._attempt_mutation_item(
            entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        result = self._mutate(session, entity, [item])
        # `row_addressability: unavailable` (unchanged this WP) -- the real
        # `MutationResult` this composition returns carries no
        # `assigned_addresses` key at all (`http.py::post_mutate` never
        # sets one), an OBSERVED fact about the real dict response, not an
        # assumption (M-1 correction precedent).
        return result["affected"], result.get("assigned_addresses")

    def attempt_batch_with_addresses(
        self, session: object, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        assert isinstance(session, _Session)
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"operation": op.operation}
            if op.values is not None:
                item["values"] = dict(op.values)
            if op.where_field is not None:
                item["where"] = [{"field": op.where_field, "operator": "eq", "value": op.where_value}]
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            if op.destructive:
                item["destructive"] = True
            if op.confirmation is not None:
                if op.confirmation is VALID_CONFIRMATION:
                    probe_item = dict(item)
                    probe_item["destructive"] = True

                    def probe(_probe_item=probe_item) -> None:
                        self._mutate(session, entity, [dict(_probe_item)])

                    peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token="DELETE")
                    item["confirmation"] = peer_confirm
                else:
                    item["confirmation"] = op.confirmation
            items.append(item)
        result = self._mutate(session, entity, items)
        return result["affected"], result.get("assigned_addresses")

    def _scoped_batch_item(self, session: _Session, op: ScopedBatchOperation) -> dict[str, Any]:
        item: dict[str, Any] = {"operation": op.operation, "entity": op.entity}
        if op.values is not None:
            item["values"] = dict(op.values)
        if op.where_field is not None:
            item["where"] = [{"field": op.where_field, "operator": "eq", "value": op.where_value}]
        if op.expected_revision is not None:
            item["expected_revision"] = op.expected_revision
        if op.unique_key is not None:
            item["unique_key"] = op.unique_key
        if op.destructive:
            item["destructive"] = True
        if op.confirmation is not None:
            if op.confirmation is VALID_CONFIRMATION:
                probe_item = dict(item)
                probe_item["destructive"] = True

                def probe(_probe_item=probe_item) -> None:
                    self._cross_mutate(session, [dict(_probe_item)])

                peer_confirm = self._resolve_confirmation(op.confirmation, probe=probe, legacy_token="DELETE")
                item["confirmation"] = peer_confirm
            else:
                item["confirmation"] = op.confirmation
        return item

    def attempt_cross_entity_batch(self, session: object, operations: Sequence[ScopedBatchOperation]) -> int:
        # P35 WP-2/WP-3 (design docs/design/PHASE35_CROSS_ENTITY_AND_
        # CONTRACT_130_V1.md section 2/3): `cross_entity_mutation: partial`
        # -- `POST /v1/data/mutations` (`_cross_mutate` above) is a real,
        # mounted dispatcher on this composition. Same per-op declare-and-
        # echo probe discipline as `attempt_batch_with_addresses` above: a
        # batch-embedded delete's probe is presented to the SAME real
        # cross-entity entry point this whole batch goes to, never a
        # per-entity substitute.
        assert isinstance(session, _Session)
        items = [self._scoped_batch_item(session, op) for op in operations]
        result = self._cross_mutate(session, items)
        return result["affected"]

    def create_unique_index(self, session: object, entity: str, index: str, fields: Sequence[str]) -> None:
        assert isinstance(session, _Session)
        # R-8 item 1 / C-17 present-denial form: `/v1/schema/operations` is
        # mounted and has a real `create_index` branch that refuses this
        # uniformly -- never `SurfaceAbsent` on this composition.
        self._schema(session, {"operation": "create_index", "entity": entity, "index": index, "fields": list(fields), "unique": True})

    def drop_entity(self, session: object, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        assert isinstance(session, _Session)
        # M-1 (WP-2.5c follow-up): `/v1/schema/operations` genuinely
        # receives `drop_entity` and refuses it uniformly with
        # `CAPABILITY_UNSUPPORTED` (`http.py::post_schema`'s own present-
        # denial fallthrough) -- a real, present entry point, not a
        # structural absence (no code path anywhere in `cell.py`/
        # `backend_postgres.py` could ever execute a drop, but the WIRE
        # dispatcher itself is real and does receive this request). This
        # is the "declared_unavailable" honest form `test_c06_destructive_
        # confirmation.py`'s own `_drop_entity_form_and_probe` now
        # distinguishes from `SurfaceAbsent` (WP-2.5c widening, mirroring
        # `test_c17_declaration_agreement.py`'s identical present-denial
        # form for `create_unique_index` below) -- presenting the real
        # request and letting its real denial propagate is what design
        # principle 4 requires once a real entry point exists; claiming
        # `SurfaceAbsent` here would now be the dishonest choice.
        body: dict[str, Any] = {"operation": "drop_entity", "entity": entity, "destructive": destructive}
        if confirmation is not None:
            body["confirmation"] = confirmation
        self._schema(session, body)

    def query_with_revisions(
        self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        result = self._query(session, entity, select=select, where=where)
        # `revision_preconditions: unavailable` -- the real dict response
        # never carries a `revisions` key (`http.py::post_query` omits it
        # entirely), observed via `.get(...)` rather than assumed `None`.
        return result["items"], result.get("revisions")

    # ------------------------------------------------------------------
    # optional raw-accessor methods (WP-2.5 widening, `test_c11_response_
    # schema_conformance.py`'s own `_find_all_adapters_with`): non-
    # normative, duck-typed extensions returning the real wire response
    # body unmodified, so C-11's response-schema reverse-validation
    # exercises a SECOND real provider, not only `r2db-api (http+postgres)`.
    # ------------------------------------------------------------------

    def raw_query_result(self, session: object, entity: str, select: Sequence[str], where: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._query(session, entity, select=select, where=where)

    def raw_mutation_result(self, session: object, entity: str, operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._mutate(session, entity, [dict(op) for op in operations])

    def raw_cross_entity_mutation_result(self, session: object, operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        # P35 WP-3 (design section 5): the cross-entity counterpart of
        # `raw_mutation_result` above -- lets `test_c11_response_schema_
        # conformance.py` reverse-validate a real `POST /v1/data/mutations`
        # response against the contract's `MutationResult` schema too
        # (design R-3: `{"committed", "affected"}` only, no
        # `assigned_addresses`). `r2db-api-http` does not implement this
        # accessor -- its own `cross_entity_mutation` stays unavailable, so
        # it has no real document of this shape to offer.
        assert isinstance(session, _Session)
        return self._cross_mutate(session, [dict(op) for op in operations])

    def raw_schema_operation_result(self, session: object, body: Mapping[str, Any]) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._schema(session, body)

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------

    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        return [
            HttpService.authenticate,
            ApplicationRuntime.insert,
            ApplicationRuntime.read,
            ApplicationRuntime.update,
            ApplicationRuntime.delete,
            ApplicationRuntime.transact,
            ApplicationRuntime.capabilities,
            # m-2 (independent WP-3 review): mirrors the in-process
            # adapter's identical addition.
            ApplicationRuntime.schema_revision,
            ApplicationDeveloper.create_collection,
            ApplicationDeveloper.create_entity,
            ApplicationDeveloper.add_field,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        runtime_a = fixture.runtime_a
        assert isinstance(runtime_a, _Session)

        def forged_scope_body_attempt() -> None:
            # `QueryRequest` is `additionalProperties: false` -- a
            # scope-looking object smuggled into the body is rejected
            # outright before any session/entity logic runs.
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"], "scope": {"application_id": fixture.app_b, "role": "developer"}},
            )

        def duplicate_authorization_header_attempt() -> None:
            runtime_b = fixture.runtime_b
            assert isinstance(runtime_b, _Session)
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"]},
                extra_header_pairs=[("authorization", f"Bearer {runtime_b.bearer}")],
            )

        def role_header_attempt() -> None:
            # `http.py::_extract_bearer` reads only the `Authorization`
            # header; no handler anywhere reads any role-spoofing header.
            self._send(
                "POST", "/v1/schema/operations", runtime_a,
                json_body={"operation": "create_entity", "entity": "conf_http_role_elevation_probe"},
                extra_header_pairs=[("x-role", "developer"), ("x-requested-role", "developer")],
            )

        def smuggled_application_id_attempt() -> None:
            self._mutate(runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {"item_key": 999}}], extra_body={"application_id": fixture.app_b})

        def smuggled_entity_in_operation_attempt() -> None:
            # `definitions.Mutation` is `additionalProperties: false` and
            # has no `entity` property -- a smuggled per-operation `entity`
            # field is rejected as an unknown field before any write.
            self._mutate(runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {"item_key": 999}, "entity": fixture.b_only_entity}])

        def scope_like_query_parameter_attempt() -> None:
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"]}, params={"application_id": fixture.app_b, "role": "developer"},
            )

        def cross_application_path_attempt() -> None:
            self._send("POST", self._data_path(fixture.b_only_entity, "query"), runtime_a, json_body={"select": ["item_key"]})

        return [
            TamperVector(kind="forged_scope_object", name="mitatedb_http_forged_scope_object_field_in_query_body", disposition="must_deny", attempt=forged_scope_body_attempt),
            TamperVector(kind="forged_scope_object", name="mitatedb_http_duplicate_authorization_header_does_not_switch_scope", disposition="must_ignore", attempt=duplicate_authorization_header_attempt),
            TamperVector(kind="role_elevation", name="mitatedb_http_role_header_does_not_elevate_runtime_to_developer", disposition="must_deny", attempt=role_header_attempt),
            TamperVector(kind="request_field_scope", name="mitatedb_http_smuggled_application_id_in_mutation_body", disposition="must_deny", attempt=smuggled_application_id_attempt),
            TamperVector(kind="request_field_scope", name="mitatedb_http_smuggled_entity_field_in_mutation_operation_body", disposition="must_deny", attempt=smuggled_entity_in_operation_attempt),
            TamperVector(kind="request_field_scope", name="mitatedb_http_scope_like_query_parameter_is_ignored", disposition="must_ignore", attempt=scope_like_query_parameter_attempt),
            TamperVector(kind="cross_application_handle", name="mitatedb_http_runtime_a_path_segment_reaches_b_only_entity", disposition="must_deny", attempt=cross_application_path_attempt),
        ]

    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        def enable_application_after_revoke_attempt() -> None:
            # `enable_application` only ever flips the APPLICATION-level
            # flag; it never touches a credential's own `revoked` column
            # (no SQL statement anywhere sets `revoked` back to `FALSE`,
            # `credential_store_postgres.py`'s own module docstring) -- a
            # real, no-op-for-this-purpose control-plane call, not denied.
            self._write_store.enable_application(handle.application_id)

        def inband_enable_credential_after_revoke_then_reauthenticate_denied_attempt() -> None:
            # WP-5 flip (design v1.2 R-8 second-round M-4): `/control/v1`'s
            # own in-band enable is now real on this composition too --
            # `set_credential_enabled_inband` and `handle` (minted via the
            # privileged `_write_store`) both ultimately act on the SAME
            # `<schema>.credentials` row (R-4: the control-writer registry
            # and the application-plane's own read-only store are two
            # Python representations of one PostgreSQL table -- 2ストア
            # 突合 is structural here, no adapter-side reconciliation shim
            # needed the way the in-process adapter's own separate dicts
            # required). `enable` itself succeeds (contract `enable_
            # credential.semantics`: reverses disable only); the proof this
            # is `must_deny`, not `must_ignore`, is that a genuine
            # re-authenticate is chained inside this SAME `attempt()`.
            control_actor = self.control_credential()
            self.set_credential_enabled_inband(control_actor, handle.credential_ref, True)
            self.authenticate(handle)

        return [
            TamperVector(
                kind="credential_reactivation", name="mitatedb_http_enable_application_does_not_reactivate_revoked_credential",
                disposition="must_ignore", attempt=enable_application_after_revoke_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="mitatedb_http_inband_enable_credential_after_revoke_then_reauthenticate_denied",
                disposition="must_deny",
                attempt=inband_enable_credential_after_revoke_then_reauthenticate_denied_attempt,
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        developer_a = fixture.developer_a
        assert isinstance(runtime_a, _Session) and isinstance(developer_a, _Session)

        def entity_probe(payload: Any) -> Any:
            # A URL path segment is always text on the wire (mirrors
            # r2db-http's own `_stringify_for_path`/identical comment):
            # unlike every other identifier position below (native JSON
            # body fields, which pass a non-string payload through
            # unchanged), a real HTTP client has no other choice here.
            path_entity = payload if isinstance(payload, str) else str(payload)
            return self._query(runtime_a, path_entity, select=["item_key"])

        def select_field_probe(payload: Any) -> Any:
            return self._query(runtime_a, fixture.shared_entity, select=[payload])

        def filter_field_probe(payload: Any) -> Any:
            return self._query(runtime_a, fixture.shared_entity, select=["item_key"], where=[{"field": payload, "operator": "eq", "value": 1}])

        def insert_field_probe(payload: Any) -> Any:
            # A JSON object key must be hashable at the Python level to
            # even build the request body dict; an unhashable payload
            # ([]/{}) cannot be placed here at all (design section 10.3).
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    "insert_field", payload, "payload is unhashable and this position is a JSON object key"
                ) from exc
            return self._mutate(runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {payload: "x"}}])

        def schema_entity_probe(payload: Any) -> Any:
            # Single atomic call (unlike `schema_field_probe` below, which
            # deliberately targets an ALREADY-EXISTING entity for the same
            # reason): a denied `entity` payload here creates nothing at
            # all, so this can safely use a throwaway name every time.
            return self._schema(developer_a, {"operation": "create_entity", "entity": payload})

        def schema_field_probe(payload: Any) -> Any:
            # C-03 structural-integrity requirement (design section 5.2
            # item 5): a denied identifier payload must leave NO side
            # effect. `add_field` against a FRESH, throwaway entity would
            # still leave that entity itself behind even when the field
            # name is denied (`create_entity` and `add_field` are two
            # separate, non-atomic HTTP calls on this peer's own wire
            # shape -- P3-D1's own "no per-field type slot" design note).
            # Targeting the fixture's own, already-existing `shared_entity`
            # instead (mirrors r2db-http's identical choice) means a
            # denied payload creates nothing new at all; a rare payload
            # that happens to be a VALID field name merely adds a column
            # to `shared_entity`, which changes neither the entity SET nor
            # `shared_entity`'s own ROW COUNT -- the two invariants the
            # structural-integrity check actually verifies.
            return self._schema(developer_a, {"operation": "add_field", "entity": fixture.shared_entity, "field": payload, "field_type": "string"})

        return {
            "entity": entity_probe,
            "select_field": select_field_probe,
            "filter_field": filter_field_probe,
            "insert_field": insert_field_probe,
            "schema_entity": schema_entity_probe,
            "schema_field": schema_field_probe,
        }

    def value_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        assert isinstance(runtime_a, _Session)
        entity = fixture.shared_entity

        def insert_value_probe(payload: Any) -> Any:
            marker = "probe-" + uuid.uuid4().hex
            self._mutate(runtime_a, entity, [{"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}])
            result = self._query(runtime_a, entity, select=["probe_value"], where=[{"field": "probe_key", "operator": "eq", "value": marker}])
            items = result["items"]
            return items[0]["probe_value"] if items else None

        def filter_value_probe(payload: Any) -> Any:
            marker = "probe-" + uuid.uuid4().hex
            self._mutate(runtime_a, entity, [{"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}])
            result = self._query(runtime_a, entity, select=["probe_value"], where=[
                {"field": "probe_key", "operator": "eq", "value": marker},
                {"field": "probe_value", "operator": "eq", "value": payload},
            ])
            items = result["items"]
            return items[0]["probe_value"] if items else None

        return {"insert_value": insert_value_probe, "filter_value": filter_value_probe}

    # ------------------------------------------------------------------
    # normalization
    # ------------------------------------------------------------------
    def classify(self, exc: BaseException) -> str:
        if isinstance(exc, _HttpFailure) and exc.is_problem_json and isinstance(exc.code, str):
            return exc.code
        return UNCLASSIFIED

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def build_fixture(self) -> Fixture:
        self._counter += 1
        suffix = f"{self._counter}_{uuid.uuid4().hex[:8]}"
        app_a, app_b = f"conf_http_a_{suffix}", f"conf_http_b_{suffix}"
        self.provision_application(app_a)
        self.provision_application(app_b)

        fields = {"item_key": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
        shared_entity, a_only_entity, b_only_entity = "shared_items", "a_only_items", "b_only_items"

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
            adapter=self, app_a=app_a, app_b=app_b, runtime_a=runtime_a, developer_a=developer_a,
            runtime_b=runtime_b, shared_entity=shared_entity, a_only_entity=a_only_entity, b_only_entity=b_only_entity,
        )

    def close(self) -> None:
        self._cleanup()
        atexit.unregister(self._cleanup)
        try:
            self._run(self._client.aclose())
        except Exception:
            pass
        try:
            self._run(self._control_client.aclose())
        except Exception:
            pass
        self._loop.close()


def build_adapter() -> ConformanceAdapter:
    return MitateDBHttpConformanceAdapter()
