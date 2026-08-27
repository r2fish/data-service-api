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
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
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
    ConformanceAdapter,
    ConformanceDenial,
    CredentialHandle,
    Fixture,
    PayloadNotExpressible,
    ScopeView,
    TamperVector,
    load_contract_error_codes,
)

from r2db_api import ControlAuthority, CredentialStore, DataService  # noqa: E402
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
    platform_db: str
    registry_schema: str


@dataclass(frozen=True)
class _PgAppInfo:
    slug: str
    schema: str
    runtime_role: str
    developer_role: str
    runtime_dsn: str
    developer_dsn: str


def _bootstrap_platform(prefix: str, admin_dsn: str) -> _Platform:
    """Run the real `0001_bootstrap_control_plane.sql` /
    `0002_provisioning_functions.sql` migrations (with `r2dbsvc` textually
    replaced by this run's unique prefix) through the real `psql` binary --
    the actual runbook an operator would use, not a Python reimplementation
    of it (§5.3 C-5), exactly as `test_postgres.py`'s `platform` fixture
    does.
    """
    import tempfile

    control_role = f"{prefix}_control"
    platform_db = f"{prefix}_platform"
    registry_schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)

    with tempfile.TemporaryDirectory() as tmp:
        rewritten: dict[str, Path] = {}
        for name in ("0001_bootstrap_control_plane.sql", "0002_provisioning_functions.sql"):
            text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
            out = Path(tmp) / name
            out.write_text(text)
            rewritten[name] = out
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        platform_db=platform_db,
        registry_schema=registry_schema,
    )


def _provision_pg_app(platform: _Platform, slug: str) -> _PgAppInfo:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    conn = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT {}.provision_application(%s, %s, %s)").format(sql.Identifier(platform.registry_schema)),
                [slug, runtime_password, developer_password],
            )
    finally:
        conn.close()
    schema = f"{platform.prefix}_app_{slug}"
    runtime_role = f"{schema}_runtime"
    developer_role = f"{schema}_developer"
    return _PgAppInfo(
        slug=slug,
        schema=schema,
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=platform.platform_db),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=platform.platform_db),
    )


def _sweep_prefix(admin_dsn: str, platform_db: str, prefix: str) -> None:
    """Drop everything this run created -- the platform database (which
    takes every per-application schema/table/grant inside it with it), then
    every cluster-global role whose name starts with this run's unique
    prefix. Never touches any object outside this run's prefix. Identical
    in spirit to `test_postgres.py::_sweep_prefix`, duplicated here rather
    than imported so this module has no import-time dependency on that test
    file.

    `DROP DATABASE` is retried a few times with a short backoff: a
    connection this adapter itself just closed (e.g. one of
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
    is attempted even if the database drop ultimately fails -- residue in
    two categories is worse than residue in one -- but the database's
    failure is still re-raised at the end so it is never silently lost
    (design requirement: cleanup failures must be visible). A leftover role
    that still holds a `GRANT CONNECT ON DATABASE` on a platform database
    that, for whatever reason, was not dropped here (the drop failed above,
    or this role has no corresponding database at all -- see
    `_sweep_stale_artifacts`) cannot be dropped directly: PostgreSQL only
    lets the original grantor revoke that privilege, not `DROP ROLE`
    itself, exactly the failure mode `migrations/0002_provisioning_
    functions.sql`'s `deprovision_application` already had to handle. On
    that specific failure this issues the matching `REVOKE CONNECT` and
    retries once, rather than giving up.
    """
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            db_error: Exception | None = None
            for attempt in range(5):
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                    [platform_db],
                )
                try:
                    cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(platform_db)))
                    db_error = None
                    break
                except psycopg.errors.ObjectInUse as exc:
                    db_error = exc
                    admin.rollback()
                    time.sleep(0.2 * (attempt + 1))

            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                try:
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
                except psycopg.errors.DependentObjectsStillExist:
                    admin.rollback()
                    cur.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                            sql.Identifier(platform_db), sql.Identifier(role)
                        )
                    )
                    cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

            if db_error is not None:
                raise db_error
    finally:
        admin.close()


# The exact shape this module's own generated prefixes take: the literal
# 8-character string "r2dbhttp" followed by 8 lowercase hex digits
# (`secrets.token_hex(4)`, see `__init__` below) -- 16 characters total,
# e.g. "r2dbhttp8130a23c". Matched two ways below: a platform database name
# is exactly `<prefix>_platform`; a role name merely starts with
# `<prefix>_` (control role, or `<prefix>_app_<slug>_runtime`/`_developer`).
# Anchored at the start on the literal "r2dbhttp" and constrained to
# exactly 8 trailing hex digits, so this can never match any of this local
# cluster's many pre-existing, unrelated objects -- `r2db_control`,
# `r2db_admin`, `auth_api`, or any of this repository's other `app_*`
# databases from unrelated work all fail at the 5th character (`_`, `_`,
# `u`, `p` respectively, none of them `h`), and `r2dbtest*`/`r2dbsvc*`
# (this repository's *other* two throwaway-prefix conventions, from
# `tests/test_postgres.py` and the raw migration files before textual
# substitution) fail at the same position for the same reason ("test"/"svc"
# where this pattern requires "http").
_STALE_PLATFORM_DB_PATTERN = r"^r2dbhttp[0-9a-f]{8}_platform$"
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
        try:
            self._platform = _bootstrap_platform(prefix, admin_dsn)
        except Exception:
            # Bootstrap can partially succeed (e.g. 0001 ran, 0002 failed);
            # sweep unconditionally so a failed build never leaves residue
            # in the local cluster.
            _sweep_prefix(admin_dsn, f"{prefix}_platform", prefix)
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
            self._credentials = CredentialStore(pepper="synthetic-conformance-pepper-r2db-http-0000")
            self._service = DataService(self._credentials, cell_factory=self._make_cell)
            self._control = ControlAuthority(self._service)

            app = create_app(self._service)
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
        _sweep_prefix(self._platform.admin_dsn, self._platform.platform_db, self._platform.prefix)

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
        # `provision_application`): `^[a-z][a-z0-9_]{0,32}$`. Kept well
        # under that bound so the decorated schema/role names
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
        self._control.issue_credential(credential_id, application_id, role, secret)
        return CredentialHandle(credential_ref=credential_id, application_id=application_id, role=role, secret=secret)

    def revoke_credential(self, handle: CredentialHandle) -> None:
        self._control.set_credential_state(handle.credential_ref, revoked=True)

    def disable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=False)

    def enable_application(self, application_id: str) -> None:
        self._control.set_application_enabled(application_id, enabled=True)

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
        self._send("POST", self._schema_path(), session, json_body={"operation": "create_entity", "entity": entity})
        for field_name in fields:
            self._send(
                "POST", self._schema_path(), session,
                json_body={"operation": "add_field", "entity": entity, "field": field_name},
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
                json_body={"select": ["id"], "scope": {"application_id": fixture.app_b, "role": "developer"}},
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
                json_body={"select": ["id"]},
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
                runtime_a, fixture.shared_entity, [{"operation": "insert", "values": {"id": 999}}],
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
                json_body={"select": ["id"]},
                params={"application_id": fixture.app_b, "role": "developer"},
            )

        # -- cross_application_handle ---------------------------------------

        def cross_application_path_attempt() -> None:
            # A legitimate, untampered credential for A, reaching straight
            # for an entity name that only exists in B's schema, via the
            # URL path segment naming it.
            self._send("POST", self._data_path(fixture.b_only_entity, "query"), runtime_a, json_body={"select": ["id"]})

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
            return self._send("POST", path, runtime_a, json_body={"select": ["id"]})

        def select_field_probe(payload: Any) -> Any:
            return self._query_request(runtime_a, fixture.shared_entity, select=[payload])

        def filter_field_probe(payload: Any) -> Any:
            return self._query_request(
                runtime_a, fixture.shared_entity, select=["id"],
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

        fields = {"id": "integer", "label": "text", "probe_key": "text", "probe_value": "text"}
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

        self.insert(developer_a, shared_entity, {"id": 1, "label": "seed-a", "probe_key": "seed", "probe_value": "seed-a"})
        self.insert(developer_b, shared_entity, {"id": 1, "label": "seed-b", "probe_key": "seed", "probe_value": "seed-b"})
        self.insert(developer_a, a_only_entity, {"id": 1, "label": "a-only", "probe_key": "seed", "probe_value": "a-only"})
        self.insert(developer_b, b_only_entity, {"id": 1, "label": "b-only", "probe_key": "seed", "probe_value": "b-only"})

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
            self._loop.close()
            try:
                # Drops the platform database (every schema/table/grant
                # created this session with it) and sweeps every role under
                # this run's unique prefix. Runs even if something above
                # raised, so a failed/partial run never leaves residue in
                # the local cluster. `_cleanup` is idempotent, so if
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
