"""r2db-api (http+postgres) plug for the common conformance port.

This is a *second* adapter for the same peer as `conformance_adapter_r2db.py`
(design `docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` step 5): where that
module drives `DataService` directly, in-process, over an in-memory
`ApplicationCell`, this module drives the exact same conditions over the
**real** stack -- the ASGI HTTP boundary (`r2db_api.http`) in front of a
`DataService` backed by `PostgresCell` (`r2db_api.postgres`) against a real
local PostgreSQL 16 server. Same condition IDs (C-01/C-03/C-08), same port,
different plug (design `docs/design/CONFORMANCE_ADAPTER_V1.md` principle 1).

Module name matters: `conformance-tests/registry.json` declares this peer
entry's module as `conformance_adapter_r2db_http`, and `conftest.py`
discovers it by adding this file's directory to `sys.path` and doing a
plain `importlib.import_module("conformance_adapter_r2db_http")` -- so this
file must keep this exact basename, alongside its sibling
`conformance_adapter_r2db.py` in the same directory.

Application plane vs. control plane (design R2DB_SERVICE_LAYER_ARCHITECTURE
Task 2): every application-facing operation on `ConformanceAdapter`
(`authenticate`, `scope_of`, `create_entity`, `insert`, `select_eq`,
`delete`, `count`, `entities`, `capability_document`) goes over real HTTP,
through the ASGI app, using `httpx.AsyncClient` with `httpx.ASGITransport`
in-process -- no network listener, no port binding. Control-plane operations
(`provision_application`, `issue_credential`, `revoke_credential`,
`disable_application`, `enable_application`,
`set_authorization_state_available`) legitimately call `ControlAuthority`
directly: the contract keeps control authority separate from the
application API on purpose, and there is no application-facing HTTP route
to it (see `spec/data-service-api.v1.json`'s `endpoints` table -- there is
no "authenticate" or "provision" endpoint at all; authentication is
per-request `Authorization: Bearer`, resolved identically by every handler).

This module does not compensate for gaps in `r2db_api.http` or
`r2db_api.postgres` (design CONFORMANCE_ADAPTER_V1 section 10.5). If a
condition fails here because the HTTP layer or `PostgresCell` genuinely
lacks something, that surfaces as a real, visible test failure -- it is not
papered over in this adapter.

Synthetic values only: application ids, credential ids/secrets, and the
throwaway PostgreSQL role/schema/database names created here are
conformance-suite fixtures, torn down at `close()`, never real deployment
values (CLAUDE.md Public Repository Security Gate).
"""
from __future__ import annotations

import asyncio
import atexit
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, NoReturn, Sequence
from urllib.parse import quote

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

# The common port lives at conformance-tests/adapter.py. See
# conformance_adapter_r2db.py's identical comment for why this fallback is
# needed only when this file is exercised standalone.
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
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    load_contract_error_codes,
)

from r2db_api import ControlAuthority, DataService  # noqa: E402
from r2db_api.credential_store import PostgresCredentialStore  # noqa: E402
from r2db_api.errors import FoundationError  # noqa: E402
from r2db_api.http import PROBLEM_CONTENT_TYPE, create_app  # noqa: E402
from r2db_api.postgres import PostgresCell  # noqa: E402

BASE_URL = "http://r2db-http-pg.conformance.invalid"

# --------------------------------------------------------------------------
# PostgreSQL bootstrap/provisioning (mirrors r2db-api/tests/test_postgres.py
# -- same admin DSN knob, same throwaway-prefix convention, same real
# migration SQL run through the real `psql` binary. Deliberately
# self-contained rather than importing from that test module: this file
# must not depend on another agent's test file remaining import-stable, and
# `r2db-api/tests/test_postgres.py` is explicitly out of scope for this
# module to modify).
# --------------------------------------------------------------------------

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

# Same environment variable `r2db-api/tests/test_postgres.py` already uses,
# deliberately reused rather than inventing a second name: one knob governs
# "where is the PostgreSQL admin connection for this repository's tests",
# for both the PostgresCell unit tests and this conformance adapter.
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _require_reachable_postgres(dsn: str) -> None:
    """PostgreSQL-availability policy for this adapter (design
    R2DB_SERVICE_LAYER_ARCHITECTURE Task 3 / §5.3 C-5).

    This adapter is registered `required: true` in
    `conformance-tests/registry.json`, matching the two existing entries
    and `conftest.py`'s own stated principle: a `required: true` adapter
    that fails to build makes the whole suite FAIL, never skip (`design
    CONFORMANCE_ADAPTER_V1.md` section 3: "skip is 'silent permission of
    the unknown'"). A skip here would silently convert "the
    PostgreSQL-backed conditions are unverified" into "permitted" -- exactly
    what design principle 4 forbids, and it is impossible to get a green
    suite out of that failure mode: it is a hard collection error, not a
    quietly-shrunk parametrization list.

    The "would also break a checkout with no database" concern is real but
    is resolved by making the failure *actionable* rather than by making it
    silent: connectivity is checked explicitly, up front, against a DSN
    that is itself governed by an explicit environment variable
    (`R2DB_TEST_ADMIN_DSN`, shared with `test_postgres.py` for one
    consistent "where is Postgres" knob across this repository's test
    suites). When unreachable, this raises immediately with the exact DSN
    that was tried and concrete remediation steps, instead of a bare
    connection traceback. This mirrors `test_postgres.py`'s own established
    precedent (`_require_admin_connection`) for the identical dependency,
    so this adapter introduces no new policy -- it applies the one this
    repository already adopted for PostgresCell's own tests to the
    conformance suite as well.
    """
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "r2db-api (http+postgres) conformance adapter requires a reachable "
            f"local PostgreSQL server. Connecting with {ADMIN_DSN_ENV}={dsn!r} "
            f"failed: {exc}. This adapter is registered as required: true in "
            "conformance-tests/registry.json, so the suite fails rather than "
            "silently skips the HTTP+PostgreSQL C-01/C-03/C-08 coverage "
            "(design principle 4). To fix: start a local PostgreSQL server "
            f"reachable at that DSN (see r2db-api/tests/test_postgres.py, "
            f"which has the identical requirement), or set {ADMIN_DSN_ENV} to "
            "a reachable admin/superuser DSN."
        ) from exc


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


@dataclass(frozen=True)
class _Platform:
    prefix: str
    admin_dsn: str
    control_dsn: str
    api_dsn: str
    platform_db: str
    provision_script: Path
    deprovision_script: Path


@dataclass(frozen=True)
class _PgAppInfo:
    slug: str
    database: str
    schema: str
    runtime_role: str
    developer_role: str
    runtime_dsn: str
    developer_dsn: str


def _bootstrap_platform(prefix: str, admin_dsn: str, script_dir: Path) -> _Platform:
    """Run the real `0001_bootstrap_control_plane.sql` /
    `0002_provisioning_functions.sql` / `0005_credential_store.sql`
    migrations (with `r2dbsvc` textually replaced by this run's unique
    prefix) through the real `psql` binary -- the actual runbook an
    operator would use, not a Python reimplementation of it (§5.3 C-5),
    exactly as `test_postgres.py`'s `platform` fixture does. `0005` is
    control-plane bootstrap exactly like `0001`/`0002` (independent of any
    one application), so it runs here, once, rather than per-application --
    it is what makes `PostgresCredentialStore` usable at all below (P2-D7:
    this adapter must exercise the real, DB-backed credential store, not
    the in-memory `CredentialStore` the previous revision of this file
    used). Also rewrites `0003_provision_application.sql`/`0004_deprovision_
    application.sql` the same way and keeps them (in `script_dir`, which the
    caller keeps alive for this adapter's whole lifetime -- unlike
    `test_postgres.py`'s `tmp_path_factory`-backed fixture, this adapter has
    no per-test temporary directory to borrow) for `_provision_pg_app`/
    `close()` to run once per application, since database-per-application
    (architecture §8) means provisioning one application is itself now a
    multi-statement script, not a single function call -- see 0002/0003's
    own header comments for why.
    """
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    platform_db = f"{prefix}_platform"
    control_password = secrets.token_urlsafe(24)
    # `0005_credential_store.sql` needs an `api_password` to create the
    # read-only `<prefix>_api` role -- this adapter's own `DataService` now
    # connects as exactly this role (review "逸脱(a)の改善": the request-
    # time read path must run under the same least-privilege grants a real
    # deployment's `r2dbsvc_api` role has, not the full-privilege control
    # role), see `__init__` below.
    api_password = secrets.token_urlsafe(24)

    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        "0005_credential_store.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = script_dir / name
        out.write_text(text)
        rewritten[name] = out
    _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
    control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
    _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        api_dsn=api_dsn,
        platform_db=platform_db,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
    )


def _provision_pg_app(platform: _Platform, slug: str) -> _PgAppInfo:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.control_dsn,
        platform.provision_script,
        {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{slug}"
    runtime_role = f"{database}_runtime"
    developer_role = f"{database}_developer"
    return _PgAppInfo(
        slug=slug,
        database=database,
        # Every application's entities live in that application's own
        # database's `public` schema now (architecture §8), not in a
        # control-plane-assigned schema name inside a shared database.
        schema="public",
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


# `platform.deprovision_script` (0004) is kept on `_Platform` for
# completeness/documentation of the provisioning pair this adapter's
# rewritten scripts represent, but is deliberately never invoked here:
# like the previous (schema-per-application) revision of this file, this
# adapter never deprovisions individual applications mid-run -- it relies
# entirely on `_sweep_prefix` at `close()`/`atexit` to drop everything this
# run created (now every per-application *database* under this run's
# prefix, not just the platform database's schemas -- see `_sweep_prefix`).


def _sweep_prefix(admin_dsn: str, platform_db: str, prefix: str) -> None:
    """Drop everything this run created -- every database whose name starts
    with this run's unique prefix (the platform database *and* every
    per-application database this run provisioned, database-per-application
    per architecture §8 -- each one takes every schema/table/grant inside
    it with it), then every cluster-global role whose name starts with the
    same prefix. Never touches any object outside this run's prefix.
    Identical in spirit to `test_postgres.py::_sweep_prefix`, duplicated
    here rather than imported so this module has no import-time dependency
    on that test file. `platform_db` is still accepted as a parameter (kept
    for backward-compatible callers within this file) but is now just one
    of the databases this function discovers by prefix, not the only one.

    `DROP DATABASE` is retried a few times with a short backoff, per
    database: a connection this adapter itself just closed (e.g. one of
    `PostgresCell`'s pooled connections, or an application-plane HTTP
    request's underlying connection) can take a brief moment to fully
    disappear from `pg_stat_activity` from the server's point of view even
    after the client-side `close()` call has returned, which can otherwise
    race a same-instant `DROP DATABASE` into `database "..." is being
    accessed by other users`. This is purely a same-process teardown
    ordering issue, not a real residual client -- `pg_terminate_backend` is
    re-issued on every attempt, so the retry converges quickly once the
    server catches up.

    Databases are dropped before roles (roles are cluster-global and
    outlive any one database, so they must be handled second). Role cleanup
    is attempted even if a database drop ultimately fails -- residue in two
    categories is worse than residue in one -- but the first database
    failure is still re-raised at the end so it is never silently lost
    (design requirement: cleanup failures must be visible). A leftover role
    that still holds a `GRANT CONNECT ON DATABASE` on some database under
    this prefix that, for whatever reason, was not dropped above (a drop
    that failed, most likely) cannot be dropped directly: PostgreSQL only
    lets the original grantor revoke that privilege, not `DROP ROLE`
    itself, exactly the failure mode `migrations/0004_deprovision_
    application.sql` avoids in the normal case by dropping the database
    first. On that specific failure this issues the matching `REVOKE
    CONNECT` against every surviving prefixed database and retries once,
    rather than giving up.
    """
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            candidate_databases = {row[0] for row in cur.fetchall()}
            candidate_databases.add(platform_db)

            db_error: Exception | None = None
            surviving_databases: set[str] = set()
            for database in sorted(candidate_databases):
                dropped = False
                for attempt in range(8):
                    # `backend_type = 'client backend'` deliberately excludes
                    # background workers (autovacuum in particular): this
                    # admin connection authenticates as the cluster
                    # superuser locally, so it *could* terminate one, but a
                    # freshly churned throwaway database routinely has an
                    # autovacuum worker visiting its system catalogs, and
                    # terminating it is unnecessary -- it finishes on its
                    # own well within this retry loop's backoff, which is
                    # what actually clears the subsequent `ObjectInUse` in
                    # that case. See `migrations/0004_deprovision_
                    # application.sql`'s identical comment for the same
                    # reasoning, and where this was first observed
                    # empirically (as `permission denied to terminate
                    # process` when this filter was missing).
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
                    surviving_databases.add(database)

            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                try:
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
                except psycopg.errors.DependentObjectsStillExist:
                    admin.rollback()
                    for database in surviving_databases:
                        try:
                            cur.execute(
                                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                                    sql.Identifier(database), sql.Identifier(role)
                                )
                            )
                        except psycopg.Error:
                            admin.rollback()
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

            if db_error is not None:
                raise db_error
    finally:
        admin.close()


# The exact shape this module's own generated prefixes take: the literal
# 8-character string "r2dbhttp" followed by 8 lowercase hex digits
# (`secrets.token_hex(4)`, see `__init__` below) -- 16 characters total,
# e.g. "r2dbhttp8130a23c". Matched three ways below: a platform database
# name is exactly `<prefix>_platform`; a per-application database name
# (architecture §8: database-per-application, one per application this
# adapter provisions) starts with `<prefix>_app_`; a role name merely
# starts with `<prefix>_` (control role, or `<prefix>_app_<slug>_runtime`/
# `_developer`). Anchored at the start on the literal "r2dbhttp" and
# constrained to exactly 8 trailing hex digits, so this can never match any
# of this local cluster's many pre-existing, unrelated objects --
# `r2db_control`, `r2db_admin`, `auth_api`, or any of this repository's
# other `app_*` databases from unrelated work all fail at the 5th character
# (`_`, `_`, `u`, `p` respectively, none of them `h`), and
# `r2dbtest*`/`r2dbsvc*`/`r2dbmig*` (this repository's *other* throwaway-
# prefix conventions, from `tests/test_postgres.py` and the raw migration
# files before textual substitution) fail at the same position for the
# same reason ("test"/"svc"/"mig" where this pattern requires "http").
_STALE_PLATFORM_DB_PATTERN = r"^r2dbhttp[0-9a-f]{8}_platform$"
_STALE_APP_DB_PATTERN = r"^r2dbhttp[0-9a-f]{8}_app_"
_STALE_ROLE_PATTERN = r"^r2dbhttp[0-9a-f]{8}_"
_PREFIX_LENGTH = len("r2dbhttp") + 8  # "r2dbhttp" + 8 hex digits


def _sweep_stale_artifacts(admin_dsn: str) -> None:
    """Startup sweep: drop anything left over from a *previous* run of this
    adapter, before this run creates its own fresh prefix.

    `_cleanup`/`atexit` below make teardown best-effort on an abnormal exit
    *of this process*, but some exits run no Python cleanup code at all --
    `SIGKILL`, a segfault, `os._exit`, a machine power-cycle mid-run. Those
    are the residue this repository's own review actually found sitting in
    the local cluster. The only way to guarantee an eventually-clean
    developer machine in the presence of that class of exit is to also
    sweep at the *start* of the next run, not only at the end of this one.

    Matches only this harness's own generated prefix shape (see the pattern
    constants above) -- never a broad `r2db%`/`r2dbhttp%` wildcard -- so it
    is safe to run unconditionally against a shared local cluster that also
    holds unrelated, permanent objects (`r2db_control`, `r2db_admin`,
    `auth_api`, and this repository's other `app_*` databases).
    """
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname ~ %s", [_STALE_PLATFORM_DB_PATTERN])
            stale_prefixes = {row[0][: -len("_platform")] for row in cur.fetchall()}
            cur.execute("SELECT datname FROM pg_database WHERE datname ~ %s", [_STALE_APP_DB_PATTERN])
            stale_prefixes |= {row[0][:_PREFIX_LENGTH] for row in cur.fetchall()}
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname ~ %s", [_STALE_ROLE_PATTERN])
            stale_prefixes |= {row[0][:_PREFIX_LENGTH] for row in cur.fetchall()}
    finally:
        admin.close()

    for stale_prefix in stale_prefixes:
        _sweep_prefix(admin_dsn, f"{stale_prefix}_platform", stale_prefix)


# --------------------------------------------------------------------------
# HTTP session / failure plumbing.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Session:
    """The "session handle" this adapter hands back from `authenticate()`.

    There is no server-side session concept in the real stack: every HTTP
    request carries its own `Authorization: Bearer` credential, resolved
    fresh by `DataService.authenticate`/`_check` on every call (see
    `r2db_api/http.py`'s `_authenticate`). This is therefore just a carrier
    for the bearer secret every subsequent HTTP call in this adapter uses --
    not a cache of anything the server remembers.
    """

    secret: str


class _HttpFailure(Exception):
    """The "native exception" this adapter classifies (design section 4.1 /
    10.2): a non-2xx HTTP response, captured without ever exposing raw
    response bytes to anything but `classify()` and the non-echo check.

    `str()` of this exception is deliberately built only from the response's
    safe, structured `message` field (never `details`' raw values, never the
    full response body) -- `r2db_api.http` already guarantees `message` is a
    static, non-interpolated string (SI-10), so this cannot itself become a
    payload-echo vector.
    """

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


def _stringify_for_path(payload: Any) -> str:
    """A URL path segment is always text on the wire: any real HTTP client
    placing a non-string value into a path must serialize it first. `str()`
    is the natural, unavoidable serialization -- not an adapter compensating
    for anything, since the wire format itself has no other option here
    (contrast with a JSON body position, where non-string payloads are
    passed through natively; see `identifier_positions` below).
    """
    return payload if isinstance(payload, str) else str(payload)


# port v1.3 (WP-5a, design docs/design/R2DB_CCR13_STORAGE_V1.md M-8
# activation): identical table and rationale to
# `conformance_adapter_r2db.py`'s own constant of the same name -- the
# explicit mapping from the port's own two-member field-type vocabulary
# (`adapter.COMMON_FIELD_TYPES`) to this peer's real `add_field`
# `field_type` parameter (`spec/data-service-api.v1.json`'s `field_type`
# enum).
_PORT_FIELD_TYPE_TO_R2DB = {"text": "string", "integer": "integer"}


class R2DBHttpConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to r2db-api's real HTTP +
    PostgreSQL stack: `r2db_api.http.create_app` in front of a
    `DataService` whose cells are `PostgresCell` instances against a real,
    throwaway-provisioned local PostgreSQL 16 database.
    """

    name = "r2db-api (http+postgres)"

    def __init__(self) -> None:
        admin_dsn = _admin_dsn()
        _require_reachable_postgres(admin_dsn)

        # Startup sweep (design requirement): drop anything a *previous*
        # run of this adapter left behind -- from an exit that ran no
        # Python cleanup code at all (a killed process, an interpreter
        # crash) -- before this run creates its own fresh prefix. See
        # `_sweep_stale_artifacts` for why its match pattern cannot touch
        # anything else in this shared local cluster.
        _sweep_stale_artifacts(admin_dsn)

        prefix = f"r2dbhttp{secrets.token_hex(4)}"
        # Unlike `test_postgres.py`'s `platform` fixture (which can borrow
        # pytest's own `tmp_path_factory`, scoped to that one test module's
        # run), this adapter's rewritten `0003_provision_application.sql`/
        # `0004_deprovision_application.sql` must stay on disk for this
        # adapter instance's entire lifetime -- `build_fixture` calls
        # `provision_application` (and therefore `_provision_pg_app`,
        # therefore `platform.provision_script`) repeatedly, long after
        # `__init__` returns. `mkdtemp` (not the `TemporaryDirectory`
        # context manager) is used deliberately so this directory outlives
        # this function; `close()`/`_cleanup` below remove it explicitly.
        self._script_dir = tempfile.mkdtemp(prefix="r2db_http_migrations_")
        try:
            self._platform = _bootstrap_platform(prefix, admin_dsn, Path(self._script_dir))
        except Exception:
            # Bootstrap can partially succeed (e.g. 0001 ran, 0002 failed);
            # sweep unconditionally so a failed build never leaves residue
            # in the local cluster.
            _sweep_prefix(admin_dsn, f"{prefix}_platform", prefix)
            shutil.rmtree(self._script_dir, ignore_errors=True)
            raise

        # From this point on, this instance owns real, cluster-global
        # objects (the platform database and its control role). Register
        # the best-effort teardown with `atexit` *immediately*, before any
        # further construction below that could itself raise -- an
        # abnormal exit past this line (an exception anywhere later in
        # `__init__`, in `build_fixture`, a `KeyboardInterrupt`, a crashed
        # process, or simply a caller that never calls `close()` -- exactly
        # what this repository's own review probes did) must still sweep
        # this run's prefix at interpreter shutdown. `_cleanup` is
        # idempotent (`self._cleaned_up`), so this can never race or
        # double-drop against the normal `close()` path.
        self._cleaned_up = False
        atexit.register(self._cleanup)

        try:
            self._app_pg: dict[str, _PgAppInfo] = {}
            self._provisioned_cells: list[PostgresCell] = []
            self._counter = 0

            # Synthetic pepper for this conformance run only; never a real
            # deployment secret and never read from the environment (mirrors
            # conformance_adapter_r2db.py).
            #
            # Two separate `PostgresCredentialStore` instances, matching the
            # real two-role production architecture (P2-D3) rather than
            # collapsing it into one connection for convenience (review
            # "逸脱(a)の改善"):
            #
            # - `self._credentials` (below): every real HTTP request this
            #   adapter drives authenticates through `DataService`, which
            #   holds exactly this store -- constructed against `<prefix>_
            #   api`, the strictly read-only role `0005` provisions
            #   (`SELECT` only on `applications`/`credentials`). If this
            #   store's read path (`authenticate`/`assert_active`) ever
            #   needed more than that role's grants, every single
            #   application-plane request in this conformance run would
            #   fail with `AUTH_STATE_UNAVAILABLE` -- a real, immediate
            #   regression signal that this role's grants (and the code
            #   that only ever reads through it) are actually sufficient,
            #   not merely a naming convention.
            # - `self._write_credentials`: constructed against `<prefix>_
            #   control` (full DML), used directly -- by `issue_credential`/
            #   `revoke_credential`/`disable_credential`-equivalent methods
            #   below -- for provisioning writes. `ControlAuthority.issue_
            #   credential`/`.set_credential_state` are *not* used for this:
            #   both only ever reach `self._service._credentials` (the
            #   read-only store above), which would refuse a write outright
            #   at the database privilege level. This trades away
            #   `ControlAuthority`'s own `credential_lifecycle` audit event
            #   for these two operations (a separate, in-memory `AuditSink`
            #   concern, orthogonal to what this adapter is actually
            #   verifying) in exchange for the read path genuinely running
            #   under least privilege -- the property this change is for.
            self._credentials = PostgresCredentialStore(
                self._platform.api_dsn,
                pepper="synthetic-conformance-pepper-r2db-http-0000",
                schema=f"{prefix}_registry",
            )
            self._write_credentials = PostgresCredentialStore(
                self._platform.control_dsn,
                pepper="synthetic-conformance-pepper-r2db-http-0000",
                schema=f"{prefix}_registry",
            )
            self._service = DataService(self._credentials, cell_factory=self._make_cell)
            self._control = ControlAuthority(self._service)

            app = create_app(self._service)
            # Kept on the instance (not just the local `app` above) so
            # `_control_surface_absent` (port v1.5) can inspect this exact,
            # live running app's own route table -- not a second app built
            # separately, and not the module-level `_ROUTES` constant --
            # when it claims no `/control` route exists.
            self._app = app
            self._loop = asyncio.new_event_loop()
            self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)
        except Exception:
            # Construction failed after the platform already exists: sweep
            # right now rather than waiting for interpreter shutdown, and
            # unregister the atexit hook so a later, unrelated interpreter
            # shutdown does not attempt a second (harmless but noisy) sweep
            # of an already-cleaned prefix.
            self._cleanup()
            atexit.unregister(self._cleanup)
            raise

    def _cleanup(self) -> None:
        """Best-effort teardown of everything this run created in the local
        PostgreSQL cluster. Idempotent: safe to call more than once (guarded
        by `self._cleaned_up`), so it can run from both the normal `close()`
        path and, as the last-resort net for an abnormal exit, from
        `atexit` -- without ever attempting a double drop or doubled log
        noise. Never swallows a failure: `_sweep_prefix` raises on a
        genuine, unresolved cleanup error, and this method does not catch
        that -- a cleanup that silently fails is exactly how the residue
        this was written for accumulated in the first place.
        """
        if self._cleaned_up:
            return
        self._cleaned_up = True
        try:
            _sweep_prefix(self._platform.admin_dsn, self._platform.platform_db, self._platform.prefix)
        finally:
            shutil.rmtree(self._script_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # backend wiring (design R2DB_SERVICE_LAYER_ARCHITECTURE Task 1)
    # ------------------------------------------------------------------

    def _make_cell(self, application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> PostgresCell:
        if entities:
            # This adapter never pre-populates entities at provisioning
            # time (unlike the in-memory `ApplicationCell` default); every
            # entity this adapter creates goes through the real
            # `POST /v1/schema/operations` + `POST .../mutations` HTTP
            # endpoints, exactly as a real client would.
            raise AssertionError("PostgresCell-backed provisioning does not pre-populate entities")
        info = self._app_pg[application_id]
        cell = PostgresCell(
            application_id,
            info.schema,
            runtime_dsn=info.runtime_dsn,
            developer_dsn=info.developer_dsn,
            runtime_role=info.runtime_role,
            developer_role=info.developer_role,
            pool_size=2,
        )
        self._provisioned_cells.append(cell)
        return cell

    def _fresh_slug(self, letter: str) -> str:
        # PostgreSQL provisioning's own slug policy (0002's
        # `begin_provision_application`): `^[a-z][a-z0-9_]{0,32}$`. Kept
        # well under that bound so the decorated database/role names
        # (`<prefix>_app_<slug>_developer` etc.) stay under PostgreSQL's
        # 63-byte identifier limit alongside the random per-run prefix.
        self._counter += 1
        return f"{letter}{self._counter}{secrets.token_hex(3)}"

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    def _run(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)

    def _send(
        self,
        method: str,
        path: str,
        session: _Session | None,
        *,
        json_body: dict[str, Any] | None = None,
        extra_header_pairs: Sequence[tuple[str, str]] = (),
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        header_pairs: list[tuple[str, str]] = []
        if session is not None:
            header_pairs.append(("authorization", f"Bearer {session.secret}"))
        header_pairs.extend(extra_header_pairs)
        request = self._client.build_request(method, path, json=json_body, headers=header_pairs, params=params)
        response = self._run(self._client.send(request))
        if response.status_code >= 400:
            failure = _HttpFailure(response)
            raise ConformanceDenial(
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__
            ) from failure
        if not response.content:
            return {}
        return response.json()

    def _control_call(self, fn: Callable[[], Any]) -> Any:
        """Wraps a *direct*, non-HTTP call into `PostgresCredentialStore`'s
        write path (used by `credential_reactivation_vectors`, below),
        converting a `FoundationError` into a `ConformanceDenial`.

        This deliberately does not go through `classify()`/`_HttpFailure`:
        those exist to interpret a real HTTP `application/problem+json`
        response, and this call never goes over HTTP at all (mirroring why
        `revoke_credential`/`issue_credential` above call
        `self._write_credentials` directly rather than through the ASGI
        app). The resulting code is already a genuine contract code
        straight from `r2db_api.errors.FoundationError.code`, not
        something this adapter infers.
        """
        try:
            return fn()
        except FoundationError as exc:
            raise ConformanceDenial(code=exc.code, adapter=self.name, native_type=type(exc).__name__) from exc

    def _data_path(self, entity: str, suffix: str) -> str:
        return f"/v1/data/{quote(entity, safe='')}/{suffix}"

    def _schema_path(self) -> str:
        return "/v1/schema/operations"

    def _query_request(
        self,
        session: _Session,
        entity: str,
        *,
        select: list[Any],
        where: list[dict[str, Any]] | None = None,
        page_size: int | None = None,
        extra_header_pairs: Sequence[tuple[str, str]] = (),
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"select": select}
        if where is not None:
            body["where"] = where
        if page_size is not None:
            body["page"] = {"size": page_size}
        return self._send(
            "POST", self._data_path(entity, "query"), session, json_body=body,
            extra_header_pairs=extra_header_pairs, params=params,
        )

    def _mutate_request(
        self,
        session: _Session,
        entity: str,
        operations: list[dict[str, Any]],
        *,
        extra_body: Mapping[str, Any] | None = None,
        extra_header_pairs: Sequence[tuple[str, str]] = (),
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"operations": operations}
        if extra_body:
            body.update(extra_body)
        return self._send(
            "POST", self._data_path(entity, "mutations"), session, json_body=body,
            extra_header_pairs=extra_header_pairs, params=params,
        )

    # ------------------------------------------------------------------
    # control plane (outside application authority, over HTTP)
    # ------------------------------------------------------------------

    def provision_application(self, application_id: str) -> None:
        info = _provision_pg_app(self._platform, application_id)
        self._app_pg[application_id] = info
        self._control.register_application(application_id)

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        self._counter += 1
        credential_id = f"httpconf-cred-{application_id}-{role}-{self._counter}"
        secret = f"httpconf-secret-{self._counter}-{uuid.uuid4().hex}"
        # `self._write_credentials`, not `self._control.issue_credential`:
        # `ControlAuthority` can only reach `self._service._credentials`
        # (`self._credentials`, the *read-only*-role store `DataService`
        # holds), which would refuse this `INSERT` at the database
        # privilege level -- see `__init__`'s comment on the two-store
        # split.
        self._write_credentials.add(credential_id, application_id, role, secret)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._write_credentials.set_state(handle.credential_ref, revoked=True)

    def disable_application(self, application_id: str) -> None:
        self._set_registry_application_enabled(application_id, False)

    def enable_application(self, application_id: str) -> None:
        self._set_registry_application_enabled(application_id, True)

    def _set_registry_application_enabled(self, application_id: str, enabled: bool) -> None:
        """The *only* mechanism this adapter uses to disable/enable an
        application -- a direct write to the database `applications.
        enabled` column, exactly what `python -m r2db_api.ops disable-app`/
        `enable-app` (P2-D6) does in a real deployment. This adapter
        reproduces the same SQL rather than shelling out to that CLI, for
        the same reason `_sweep_prefix` above is duplicated rather than
        imported (no import-time dependency on another module this adapter
        must not assume stays stable).

        Review-reported gap this fixes: an earlier revision of this method
        *also* called `ControlAuthority.set_application_enabled` (which
        only ever toggles `DataService`'s private in-memory `_disabled_
        apps` set -- `DataService._check`/`.authenticate` still consult it
        as a second, legacy layer). That in-memory toggle alone was enough
        to make every C-08 disablement condition pass, which meant this
        DB write could regress to a silent no-op without any conformance
        test noticing -- confirmed by review: neutralizing this method's DB
        write left the suite green while the in-memory call was still
        present. `PostgresCredentialStore.authenticate`/`assert_active`
        decide `APPLICATION_DISABLED` from the *database*
        `applications.enabled` column alone (P2-D4); calling
        `ControlAuthority.set_application_enabled` here would only ever
        mask a bug in that DB-backed path, never actually exercise it, so
        it is deliberately not called from this method at all.
        """
        statement = sql.SQL("UPDATE {table} SET enabled = {enabled_ph} WHERE application_slug = {slug_ph}").format(
            table=sql.Identifier(f"{self._platform.prefix}_registry", "applications"),
            enabled_ph=sql.Placeholder(),
            slug_ph=sql.Placeholder(),
        )
        with psycopg.connect(self._platform.control_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(statement, [enabled, application_id])

    def set_authorization_state_available(self, available: bool) -> None:
        self._control.set_authorization_state_available(available)

    def propagation_bound_ms(self) -> int:
        # Identical reasoning to conformance_adapter_r2db.py: every single
        # application-plane HTTP request re-authenticates and re-checks
        # authorization state from scratch (`DataService._check()`, called
        # by every handler in `r2db_api.http` on every request) -- there is
        # no session cache anywhere in this stack, in-process or over HTTP,
        # so revoke/disable/state-unavailable propagation is synchronous.
        return 0

    def capability_document(self) -> Mapping[str, Any]:
        # `/v1/capabilities` requires "application or control" auth per the
        # contract's endpoint table; there is no anonymous way to fetch it.
        # This provisions a disposable application/credential solely to
        # obtain the peer's own real capability document over real HTTP --
        # it does not fabricate one in the adapter.
        probe_app = self._fresh_slug("cap")
        self.provision_application(probe_app)
        handle = self.issue_credential(probe_app, "runtime")
        session = self.authenticate(handle)
        return self._send("GET", "/v1/capabilities", session)

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5) -- surface-absent branch
    # ------------------------------------------------------------------
    #
    # Control-plane HTTP work (CCR-14 design docs/design/
    # R2DB_CCR14_CONTROL_PLANE_V1.md, work packages WP-2 onward) has not
    # landed in `r2db_api.src` as of this port revision: `create_app`
    # (`r2db_api/http.py`) builds its `Starlette` app from the fixed
    # `_ROUTES` list, none of which is `/control`-prefixed. Every one of
    # the 13 port v1.5 operations therefore takes the surface-absent
    # branch (design section 4, form (a)) unconditionally, via one shared
    # helper (avoids 13 near-duplicate `SurfaceAbsent` call sites that
    # could drift out of sync with each other).
    #
    # This adapter's claim is stronger than a signature-only check: before
    # raising, it inspects `self._app.app.routes` -- the real, live route
    # table of the exact ASGI app HTTP requests in this adapter are
    # actually dispatched against (`self._app` is the
    # `RequestByteBoundMiddleware`-wrapped app `__init__` built via
    # `create_app`; `.app` is that middleware's own wrapped `Starlette`
    # instance, `RequestByteBoundMiddleware.__init__`'s `self.app = app` in
    # `r2db_api/http.py`) -- for any route whose `.path` starts with
    # `/control`. If one is found, the "absent" claim below would be false
    # against the peer's own live, running state, so this asserts loudly
    # (`AssertionError`, never a silently-wrong `SurfaceAbsent`) rather
    # than proceeding on stale reasoning. This turns the claim from a
    # comment into a measurement, exactly as design section 4's "confirmed
    # by source inspection, never assumed" standard requires -- here
    # "source inspection" is inspection of the actual running app object,
    # the strongest form available to this HTTP-boundary adapter.
    #
    # `public_operation_callables()` -- this adapter's own wrappers around
    # the real application-facing HTTP surface -- is passed as the
    # signature-level evidence for `signature_forbids_parameters`, exactly
    # as the in-process plug's identical helper does (C-17 precedent
    # density, `MitateDB-api/conformance/conformance_adapter_mitatedb.py:
    # 443-476`).
    def _control_surface_absent(self, operation: str, requested: str) -> NoReturn:
        control_routes = [r for r in self._app.app.routes if getattr(r, "path", "").startswith("/control")]
        if control_routes:
            raise AssertionError(
                f"{self.name}: claimed control-plane SurfaceAbsent for {operation!r}, but the live ASGI "
                f"app already has {len(control_routes)} route(s) starting with '/control': "
                f"{sorted(r.path for r in control_routes)!r}"
            )
        raise SurfaceAbsent(
            self.name, operation,
            f"no /control/v1 route exists in this peer's real, live ASGI app.routes (requested: {requested})",
            surface=self.public_operation_callables(),
            forbidden_parameters=["credential", "control", "bootstrap", "rotate", "revoke"],
        )

    # port v1.5
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        """No control-plane capabilities entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("control_capabilities", f"actor={actor!r}")

    # port v1.5
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        """No in-band application-registration entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("register_application_inband", f"application_id={application_id!r}")

    # port v1.5
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        """No in-band application-listing entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("list_applications", f"actor={actor!r}")

    # port v1.5
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        """No in-band application enable/disable entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent(
            "set_application_enabled_inband", f"application_id={application_id!r} enabled={enabled!r}"
        )

    # port v1.5
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        """No in-band credential-issuance entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent(
            "issue_credential_inband", f"application_id={application_id!r} role={role!r}"
        )

    # port v1.5
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        """No in-band credential-listing entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("list_credentials", f"actor={actor!r}")

    # port v1.5
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        """No in-band credential-rotation entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("rotate_credential", f"credential_ref={credential_ref!r}")

    # port v1.5
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        """No in-band credential-revocation entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent(
            "revoke_credential_inband",
            f"credential_ref={credential_ref!r} destructive={destructive!r} confirmation={confirmation!r}",
        )

    # port v1.5
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        """No in-band credential enable/disable entry point exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent(
            "set_credential_enabled_inband", f"credential_ref={credential_ref!r} enabled={enabled!r}"
        )

    # port v1.5
    def bootstrap(self) -> ControlCredentialHandle:
        """No out-of-band bootstrap ritual mechanism is wired into this adapter yet -- WP-2 has not landed; see
        `_control_surface_absent`."""
        self._control_surface_absent("bootstrap", "ritual bootstrap (no actor -- out-of-band by contract)")

    # port v1.5
    def reset(self) -> ControlCredentialHandle:
        """No out-of-band reset ritual mechanism is wired into this adapter yet; see `_control_surface_absent`."""
        self._control_surface_absent("reset", "ritual reset (no actor -- out-of-band by contract)")

    # port v1.5
    def control_credential(self) -> ControlCredentialHandle:
        """No control credential can be minted -- bootstrap/reset do not exist yet; see `_control_surface_absent`."""
        self._control_surface_absent("control_credential", "privileged control-credential setup")

    # port v1.5
    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        """No control-plane audit trail exists to observe yet; see `_control_surface_absent`."""
        self._control_surface_absent("control_audit_events", "control-plane audit observation")

    # port v1.5 (fix-round): the inverse of `provision_application`. The
    # in-band, control-plane sense of "registered Application" (design R-4:
    # a "registered, not yet provisioned" row created by `register_
    # application_inband`) has no real removal mechanism on this peer at
    # all -- consistent with the contract keeping application deletion out
    # of v1 scope. This is deliberately distinct from `platform.
    # deprovision_script` (0004, kept on `_Platform` in `__init__` but
    # never invoked): that script tears down a *fully DB-provisioned*
    # Application's real database/roles, a different, lower-level operation
    # this adapter's own `provision_application` performs directly (not
    # through any in-band control-plane surface) -- it is not a stand-in
    # for undoing an in-band `register_application_inband` call, which
    # never touches PostgreSQL provisioning at all (R-4's whole point).
    def deprovision_application(self, application_id: str) -> None:
        """No in-band application-removal mechanism exists on this peer yet; see `_control_surface_absent`."""
        self._control_surface_absent("deprovision_application", f"application_id={application_id!r}")

    # ------------------------------------------------------------------
    # application plane (over real HTTP)
    # ------------------------------------------------------------------

    def authenticate(self, handle: CredentialHandle) -> object:
        # There is no dedicated "authenticate" endpoint in the contract
        # (spec `endpoints` has none); every handler authenticates the
        # bearer credential identically. `GET /v1/capabilities` is the
        # cheapest real endpoint that requires only authentication, so it
        # doubles as the authentication probe here -- a real HTTP round
        # trip, not a bypass.
        session = _Session(secret=handle.secret)
        self._send("GET", "/v1/capabilities", session)
        return session

    def scope_of(self, session: object) -> ScopeView:
        assert isinstance(session, _Session)
        document = self._send("GET", "/v1/capabilities", session)
        return ScopeView(application_id=document["application_scope"], role=document["role"])

    def create_entity(self, session: object, entity: str, fields: Mapping[str, str]) -> None:
        assert isinstance(session, _Session)
        # The contract's `SchemaOperationRequest` has no plural "fields"
        # property -- only a single `field` per `add_field` operation (see
        # `spec/data-service-api.v1.json`'s schema). A real HTTP client
        # creating a multi-field entity must therefore issue one
        # `create_entity` call followed by one `add_field` call per column;
        # this is that same two-step sequence, not a workaround.
        #
        # port v1.3 (WP-5a activation of M-8): each `add_field` now also
        # carries `field_type`, mapped from the port's own two-member
        # vocabulary (`text`/`integer`) to this peer's real `field_type`
        # parameter via the same `_PORT_FIELD_TYPE_TO_R2DB` table
        # `conformance_adapter_r2db.py` uses -- duplicated here rather than
        # imported, matching this repository's existing convention of each
        # plug owning its own logic with no cross-plug import dependency.
        self._send("POST", self._schema_path(), session, json_body={"operation": "create_entity", "entity": entity})
        for field_name, port_type in fields.items():
            contract_type = _PORT_FIELD_TYPE_TO_R2DB.get(port_type)
            if contract_type is None:
                raise ValueError(f"unmapped port field type {port_type!r} for field {field_name!r}")
            self._send(
                "POST", self._schema_path(), session,
                json_body={"operation": "add_field", "entity": entity, "field": field_name, "field_type": contract_type},
            )

    def insert(self, session: object, entity: str, values: Mapping[str, Any]) -> None:
        assert isinstance(session, _Session)
        self._mutate_request(session, entity, [{"operation": "insert", "values": dict(values)}])

    def select_eq(
        self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> list[dict]:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        result = self._query_request(session, entity, select=list(select), where=where)
        return result["items"]

    def attempt_filter(
        self, session: object, entity: str, select: Sequence[str], field: str, operator: str, value: Any
    ) -> list[dict]:
        assert isinstance(session, _Session)
        # Same real query endpoint `select_eq` above already uses,
        # generalized to an arbitrary operator -- see
        # conformance_adapter_r2db.py's identical method for the full
        # rationale.
        where = [{"field": field, "operator": operator, "value": value}]
        result = self._query_request(session, entity, select=list(select), where=where)
        return result["items"]

    def delete(
        self,
        session: object,
        entity: str,
        field: str,
        value: Any,
        *,
        destructive: bool,
        confirmation: str | None,
    ) -> int:
        assert isinstance(session, _Session)
        # VALID_CONFIRMATION sentinel protocol (design section 10.1),
        # identical to conformance_adapter_r2db.py: `destructive` always
        # passes through faithfully; this adapter never upgrades a
        # non-destructive/unconfirmed request into a confirmed destructive
        # one.
        peer_confirmation = "DELETE" if confirmation is VALID_CONFIRMATION else confirmation
        operation: dict[str, Any] = {
            "operation": "delete",
            "where": [{"field": field, "operator": "eq", "value": value}],
            "destructive": destructive,
        }
        if peer_confirmation is not None:
            operation["confirmation"] = peer_confirmation
        result = self._mutate_request(session, entity, [operation])
        return result["affected"]

    def count(self, session: object, entity: str) -> int:
        assert isinstance(session, _Session)
        # There is no COUNT capability anywhere in the contract's endpoint
        # table -- a real HTTP client has no choice but to query and count
        # items, exactly as this does. `GET /v1/catalog` supplies the field
        # list a query's `select` must be a subset of.
        document = self._send("GET", "/v1/catalog", session)
        fields: list[str] | None = None
        for item in document["entities"]:
            if item["entity"] == entity:
                fields = item["fields"]
                break
        if not fields:
            return 0
        result = self._query_request(session, entity, select=list(fields), page_size=1000)
        return len(result["items"])

    def entities(self, session: object) -> set[str]:
        assert isinstance(session, _Session)
        document = self._send("GET", "/v1/catalog", session)
        return {item["entity"] for item in document["entities"]}

    def catalog_document(self, session: object) -> Mapping[str, Any]:
        assert isinstance(session, _Session)
        # `GET /v1/catalog`'s own real response, unmodified -- the exact
        # request `entities()` above already issues, this just returns the
        # whole document instead of projecting it down to an entity-name
        # set.
        return self._send("GET", "/v1/catalog", session)

    def _build_mutation_item(
        self,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None,
        unique_key: str | None,
        destructive: bool = False,
        confirmation: Any = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"operation": operation}
        if values is not None:
            item["values"] = dict(values)
        if where_field is not None:
            item["where"] = [{"field": where_field, "operator": "eq", "value": where_value}]
        if destructive:
            # Same VALID_CONFIRMATION sentinel protocol as `delete()` below,
            # extended to batch operations (port v1.4).
            item["destructive"] = True
            peer_confirmation = "DELETE" if confirmation is VALID_CONFIRMATION else confirmation
            if peer_confirmation is not None:
                item["confirmation"] = peer_confirmation
        if expected_revision is not None:
            # Same real parameter position as conformance_adapter_r2db.py's
            # identical comment: carried through over real HTTP exactly like
            # `values`/`where` above, never interpreted here.
            item["expected_revision"] = expected_revision
        if unique_key is not None:
            # port v1.3: `Mutation.unique_key` (CCR-13 §0.5 Q-1 plan B).
            item["unique_key"] = unique_key
        return item

    def attempt_mutation(
        self,
        session: object,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> int:
        assert isinstance(session, _Session)
        item = self._build_mutation_item(
            operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        result = self._mutate_request(session, entity, [item])
        return result["affected"]

    def attempt_mutation_with_addresses(
        self,
        session: object,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        assert isinstance(session, _Session)
        item = self._build_mutation_item(
            operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        # The real HTTP mutation response is a JSON object that already
        # carries `assigned_addresses` (`http.py::post_mutate`, work
        # package WP-5b) -- observed directly, exactly like
        # `query_with_revisions` below observes `revisions`.
        result = self._mutate_request(session, entity, [item])
        return result["affected"], result.get("assigned_addresses")

    def attempt_batch_with_addresses(
        self, session: object, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        assert isinstance(session, _Session)
        items = [
            self._build_mutation_item(
                op.operation, values=op.values, where_field=op.where_field, where_value=op.where_value,
                expected_revision=op.expected_revision, unique_key=op.unique_key,
                destructive=op.destructive, confirmation=op.confirmation,
            )
            for op in operations
        ]
        # Same real HTTP mutation endpoint as `attempt_mutation_with_
        # addresses` above, given every operation in one request body --
        # exactly what a real client sending a multi-operation atomic batch
        # over HTTP would do.
        result = self._mutate_request(session, entity, items)
        return result["affected"], result.get("assigned_addresses")

    def create_unique_index(self, session: object, entity: str, index: str, fields: Sequence[str]) -> None:
        assert isinstance(session, _Session)
        # Same real, single schema-operations endpoint every other schema
        # operation in this adapter already uses -- see
        # conformance_adapter_r2db.py's identical method for the full
        # rationale (this is the HTTP-boundary twin of that call). Real,
        # executable vocabulary on this peer as of work package WP-3: a
        # well-formed request against a real entity/fields genuinely
        # succeeds over real HTTP too.
        self._send(
            "POST", self._schema_path(), session,
            json_body={
                "operation": "create_index",
                "entity": entity,
                "index": index,
                "fields": list(fields),
                "unique": True,
            },
        )

    def query_with_revisions(
        self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        assert isinstance(session, _Session)
        # Unlike conformance_adapter_r2db.py's in-process twin (whose
        # `DataService.query()` returns a bare `list[dict]` with
        # structurally no place a `revisions` key could ever appear), this
        # plug's real `POST .../query` response *is* a JSON object -- so
        # this observes whatever key that real response actually carries
        # (`result.get("revisions")`) rather than asserting `None` without
        # looking (conformance-review correction M-1). As of work package
        # WP-5b the response genuinely carries `revisions`
        # (`revision_preconditions: enabled`), so this now returns real
        # data -- no edit was needed here to pick it up, which is the
        # point of observing rather than asserting.
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        result = self._query_request(session, entity, select=list(select), where=where)
        return result["items"], result.get("revisions")

    # ------------------------------------------------------------------
    # attack-surface declarations
    # ------------------------------------------------------------------

    def native_command_surface(self) -> None:
        return None

    def public_operation_callables(self) -> Sequence[Callable]:
        # This adapter's own wrappers around the real application-facing
        # HTTP surface -- the operations an authenticated application
        # credential can reach. (The underlying Starlette route handlers in
        # `r2db_api.http` all share the single `(request: Request)`
        # signature Starlette requires, which would make this inspection
        # vacuous if pointed at them directly; the request-shape allowlist
        # that actually forecloses a native-command escape hatch is
        # `_check_object_shape` against `QueryRequest`/`MutationRequest`/
        # `SchemaOperationRequest` in `spec/data-service-api.v1.json`, none
        # of which declare a raw/sql/command/script/expression/native
        # field. These per-field Python parameters are the faithful
        # analogue of that request shape for this inspection.)
        return [
            self.authenticate,
            self.capability_document,
            self.create_entity,
            self.insert,
            self.select_eq,
            self.delete,
            self.count,
            self.entities,
        ]

    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]:
        runtime_a = fixture.runtime_a
        assert isinstance(runtime_a, _Session)
        runtime_b = fixture.runtime_b
        assert isinstance(runtime_b, _Session)

        # -- forged_scope_object -------------------------------------------

        def forged_scope_body_attempt() -> None:
            # A full scope-looking object smuggled into the JSON body.
            # `QueryRequest` is `additionalProperties: false`, so this is
            # rejected outright before any application logic ever sees it.
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"], "scope": {"application_id": fixture.app_b, "role": "developer"}},
            )

        def duplicate_authorization_header_attempt() -> None:
            # A genuinely HTTP-specific attack surface with no in-process
            # analogue: two `Authorization` headers on the same request,
            # the real one for runtime_a first, a second one naming
            # application B's runtime credential. Whichever header the
            # server honors, the outcome must never be a blend of the two
            # scopes or a switch to B -- `must_ignore`'s invariant check
            # (server-bound scope of runtime_a unchanged, B's state
            # unchanged) is what actually proves that, regardless of which
            # header wins.
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"]},
                extra_header_pairs=[("authorization", f"Bearer {runtime_b.secret}")],
            )

        # -- role_elevation ---------------------------------------------

        def role_header_attempt() -> None:
            # runtime_a's real credential is genuinely runtime-scoped; this
            # additionally carries header-based role-spoofing attempts that
            # no handler in `r2db_api.http` ever reads (only the
            # `Authorization` header selects a credential -- see
            # `http.py`'s `_extract_bearer` docstring). Confirms role
            # really is server-bound to the credential, not influenced by
            # any header.
            self._send(
                "POST", self._schema_path(), runtime_a,
                json_body={"operation": "create_entity", "entity": "conf_http_role_elevation_probe"},
                extra_header_pairs=[("x-role", "developer"), ("x-requested-role", "developer")],
            )

        # -- request_field_scope ------------------------------------------

        def smuggled_application_id_attempt() -> None:
            # `MutationRequest` is also `additionalProperties: false`; a
            # smuggled `application_id` field is rejected outright, exactly
            # like `r2db-api/tests/test_http.py`'s
            # `test_body_scope_fields_are_rejected_outright_and_have_no_effect`.
            self._mutate_request(
                runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {"item_key": 999}}],
                extra_body={"application_id": fixture.app_b},
            )

        def scope_like_query_parameter_attempt() -> None:
            # A scope-looking query string on an endpoint that never reads
            # query parameters at all (`post_query` only reads the parsed
            # JSON body and the `entity` path parameter). Expected to
            # succeed as an ordinary, correctly-scoped request for A --
            # `must_ignore` proves the query string had zero effect on
            # scope.
            self._send(
                "POST", self._data_path(fixture.shared_entity, "query"), runtime_a,
                json_body={"select": ["item_key"]},
                params={"application_id": fixture.app_b, "role": "developer"},
            )

        # -- cross_application_handle ---------------------------------------

        def cross_application_path_attempt() -> None:
            # A legitimate, untampered credential for A, reaching straight
            # for an entity name that only exists in B's schema, via the
            # URL path segment naming it.
            self._send("POST", self._data_path(fixture.b_only_entity, "query"), runtime_a, json_body={"select": ["item_key"]})

        def body_entity_field_in_mutation_operation_attempt() -> None:
            # C-01 strengthening (design docs/design/
            # CONFORMANCE_CONDITIONS_V1_1.md section 4 / C-16 pull-forward):
            # a smuggled `entity` field inside one *operation* dict of a
            # per-entity mutation request body -- distinct from the
            # existing top-level `application_id`-smuggling vector above.
            # `Mutation`'s own schema (`definitions.Mutation`) is
            # `additionalProperties: false` and has no `entity` property;
            # `structured.py`'s `bind_mutation` enforces the equivalent
            # key-allowlist independently (`_MUTATION_KEYS`, which also
            # excludes "entity") since `http.py` never re-validates each
            # operation dict's shape against that schema itself. Either
            # enforcement point rejects this with VALIDATION_FAILED before
            # any write happens -- this is a real HTTP-wire-level probe an
            # in-process adapter has no body to represent at all.
            self._mutate_request(
                runtime_a, fixture.shared_entity,
                [{"operation": "insert", "values": {"item_key": 999}, "entity": fixture.b_only_entity}],
            )

        return [
            TamperVector(
                kind="forged_scope_object",
                name="http_forged_scope_object_field_in_query_body",
                disposition="must_deny",
                attempt=forged_scope_body_attempt,
            ),
            TamperVector(
                kind="forged_scope_object",
                name="http_duplicate_authorization_header_does_not_switch_scope",
                disposition="must_ignore",
                attempt=duplicate_authorization_header_attempt,
            ),
            TamperVector(
                kind="role_elevation",
                name="http_role_header_does_not_elevate_runtime_to_developer",
                disposition="must_deny",
                attempt=role_header_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="http_smuggled_application_id_in_mutation_body",
                disposition="must_deny",
                attempt=smuggled_application_id_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="http_scope_like_query_parameter_is_ignored",
                disposition="must_ignore",
                attempt=scope_like_query_parameter_attempt,
            ),
            TamperVector(
                kind="cross_application_handle",
                name="http_runtime_a_path_segment_reaches_b_only_entity",
                disposition="must_deny",
                attempt=cross_application_path_attempt,
            ),
            TamperVector(
                kind="request_field_scope",
                name="http_smuggled_entity_field_in_mutation_operation_body",
                disposition="must_deny",
                attempt=body_entity_field_in_mutation_operation_attempt,
            ),
        ]

    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        # Same minimum as `conformance_adapter_r2db.py` (design docs/design/
        # CONFORMANCE_CONDITIONS_V1_1.md section 2): `PostgresCredentialStore.
        # set_state` is the one control-plane surface that could reactivate
        # a revoked credential, via `self._write_credentials` (the
        # full-DML-role store -- see `__init__`'s comment on why this,
        # never `self._control`, is used for control-plane writes here).
        def revoked_false_attempt() -> None:
            self._control_call(lambda: self._write_credentials.set_state(handle.credential_ref, revoked=False))

        def enabled_true_attempt() -> None:
            self._control_call(lambda: self._write_credentials.set_state(handle.credential_ref, enabled=True))

        return [
            TamperVector(
                kind="credential_reactivation",
                name="r2db_http_set_state_revoked_false",
                disposition="must_deny",
                attempt=revoked_false_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_http_set_state_enabled_true_after_revoke",
                disposition="must_ignore",
                attempt=enabled_true_attempt,
            ),
        ]

    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]:
        runtime_a = fixture.runtime_a
        assert isinstance(runtime_a, _Session)
        developer_a = fixture.developer_a
        assert isinstance(developer_a, _Session)

        def entity_probe(payload: Any) -> Any:
            # A URL path segment: must be stringified (see
            # `_stringify_for_path`), unlike every other identifier
            # position below, which are native JSON body fields.
            path = self._data_path(_stringify_for_path(payload), "query")
            return self._send("POST", path, runtime_a, json_body={"select": ["item_key"]})

        def select_field_probe(payload: Any) -> Any:
            return self._query_request(runtime_a, fixture.shared_entity, select=[payload])

        def filter_field_probe(payload: Any) -> Any:
            # `select` must name a real field of `shared_entity` (`id` is no
            # longer one -- see `build_fixture`'s comment) so this probe's
            # denial is genuinely attributable to the malicious `payload`
            # filter field, not an incidental unknown-select-field NOT_FOUND.
            return self._query_request(
                runtime_a, fixture.shared_entity, select=["item_key"],
                where=[{"field": payload, "operator": "eq", "value": 1}],
            )

        def insert_field_probe(payload: Any) -> Any:
            # A JSON object key must be hashable at the Python level to
            # even build the request body dict; an unhashable payload
            # ([], {}) cannot be placed here at all -- design section 10.3.
            try:
                hash(payload)
            except TypeError as exc:
                raise PayloadNotExpressible(
                    "insert_field", payload, "payload is unhashable and this position is a JSON object key"
                ) from exc
            return self._mutate_request(
                runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {payload: "x"}}]
            )

        def schema_entity_probe(payload: Any) -> Any:
            return self._send(
                "POST", self._schema_path(), developer_a,
                json_body={"operation": "create_entity", "entity": payload},
            )

        def schema_field_probe(payload: Any) -> Any:
            return self._send(
                "POST", self._schema_path(), developer_a,
                json_body={"operation": "add_field", "entity": fixture.shared_entity, "field": payload},
            )

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
            marker = f"probe-{uuid.uuid4().hex}"
            self._mutate_request(runtime_a, entity, [
                {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
            ])
            result = self._query_request(
                runtime_a, entity, select=["probe_value"],
                where=[{"field": "probe_key", "operator": "eq", "value": marker}],
            )
            rows = result["items"]
            return rows[0]["probe_value"] if rows else None

        def filter_value_probe(payload: Any) -> Any:
            marker = f"probe-{uuid.uuid4().hex}"
            self._mutate_request(runtime_a, entity, [
                {"operation": "insert", "values": {"probe_key": marker, "probe_value": payload}}
            ])
            result = self._query_request(
                runtime_a, entity, select=["probe_value"],
                where=[
                    {"field": "probe_key", "operator": "eq", "value": marker},
                    {"field": "probe_value", "operator": "eq", "value": payload},
                ],
            )
            rows = result["items"]
            return rows[0]["probe_value"] if rows else None

        return {"insert_value": insert_value_probe, "filter_value": filter_value_probe}

    # ------------------------------------------------------------------
    # normalization
    # ------------------------------------------------------------------

    def classify(self, exc: BaseException) -> str:
        # design section 10.2: map only a genuine, well-formed
        # application/problem+json response with a contract-member `code`
        # to that code. Anything else -- a non-problem response, a
        # problem+json with a missing/foreign `code`, or (structurally
        # impossible to reach via `_send`, but checked anyway) a non-HTTP
        # native exception -- maps to UNCLASSIFIED rather than to a
        # plausible-looking contract code, so a genuine crash surfaces as a
        # finding instead of masquerading as a deliberate denial.
        if not isinstance(exc, _HttpFailure):
            return UNCLASSIFIED
        if not exc.is_problem_json or exc.body is None:
            return UNCLASSIFIED
        code = exc.code
        if not isinstance(code, str) or code not in load_contract_error_codes():
            return UNCLASSIFIED
        return code

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def build_fixture(self) -> Fixture:
        # `fx` is function-scoped but `adapter` is session-scoped
        # (conftest.py), so this runs once per test function against the
        # same long-lived adapter/platform. Every application id must be
        # fresh, real PostgreSQL-provisioned state each time.
        app_a = self._fresh_slug("ha")
        app_b = self._fresh_slug("hb")
        self.provision_application(app_a)
        self.provision_application(app_b)

        # `item_key`, not `id`: `id` is reserved on `r2db-api` (design
        # docs/design/R2DB_CCR13_STORAGE_V1.md R-3 -- the server-assigned
        # address column) and is not to be used as an ordinary field name by
        # the common fixture/probes (port v1.2 coordinated revision,
        # docs/design/CONFORMANCE_ADAPTER_V1.md section 12).
        fields = {"item_key": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
        shared_entity = "shared_items"
        a_only_entity = "a_only_items"
        b_only_entity = "b_only_items"

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
            adapter=self,
            app_a=app_a,
            app_b=app_b,
            runtime_a=runtime_a,
            developer_a=developer_a,
            runtime_b=runtime_b,
            shared_entity=shared_entity,
            a_only_entity=a_only_entity,
            b_only_entity=b_only_entity,
        )

    def close(self) -> None:
        try:
            self._run(self._client.aclose())
        finally:
            for cell in self._provisioned_cells:
                cell.close()
            self._credentials.close()
            self._write_credentials.close()
            self._loop.close()
            try:
                # Drops the platform database and every per-application
                # database this run provisioned (each takes every
                # schema/table/grant created inside it with it), and sweeps
                # every role under this run's unique prefix. Runs even if
                # something above raised, so a failed/partial run never
                # leaves residue in the local cluster. `_cleanup` is
                # idempotent, so if
                # `atexit` already ran this (e.g. a previous, unrelated
                # abnormal exit somehow left this same instance alive -- it
                # never does in practice, but the guard costs nothing) this
                # is a no-op rather than a second drop attempt.
                self._cleanup()
            finally:
                # This run cleaned up through the normal path; the
                # `atexit` hook registered in `__init__` is now
                # unnecessary. Unregistering it avoids a second, redundant
                # (if harmless) sweep attempt at interpreter shutdown and
                # keeps this instance from being held alive by `atexit`'s
                # own registry for longer than it needs to be.
                atexit.unregister(self._cleanup)


def build_adapter() -> ConformanceAdapter:
    return R2DBHttpConformanceAdapter()
