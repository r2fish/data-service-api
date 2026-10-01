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
import copy
import atexit
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
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
    ENUM_CLEAR,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ControlCredentialHandle,
    CredentialHandle,
    Fixture,
    IdempotencyHold,
    IsolatedControlHandle,
    PayloadNotExpressible,
    PlanVerificationHold,
    ScopedBatchOperation,
    ScopeView,
    SurfaceAbsent,
    TamperVector,
    WireEntry,
    apply_limits_override,
    fold_batch_idempotency_key,
    fresh_identifier,
    load_contract_error_codes,
    resolve_valid_confirmation,
)
from adapter import _EnumClear  # noqa: E402  -- type-hint only, mirrors ConformanceAdapter's own signature

# CCR-14 WP-5 round 2 (MINOR-3): `r2db_api.control_main` now ends with a
# module-level `app = build_control_app()` (design §8 m-10) -- a bare
# `import r2db_api.control_main` (needed below for `assemble_control_
# stack`, the shared assembly core this adapter and `build_control_app`
# both now use) reads `os.environ` the instant it first runs. This
# adapter's own control-plane composition happens per-instance, later, in
# `__init__` (a real, throwaway-provisioned platform database whose DSN
# does not exist yet at *module* import time) -- it never uses this
# module-level `app` at all. `setdefault` supplies harmless, unreachable
# placeholder values purely so the import itself does not raise
# (`build_control_app`'s own construction is zero-network -- see that
# function's docstring -- so these values are never actually connected
# to); `setdefault` (not a plain assignment) so a caller that legitimately
# has these set in its real environment for some other reason is never
# clobbered.
os.environ.setdefault("R2DB_CONTROLPLANE_DSN", "host=/tmp port=1 dbname=r2db_http_conformance_import_placeholder")
os.environ.setdefault("R2DB_CONTROL_CREDENTIAL_PEPPER", "r2db-http-conformance-import-placeholder-ctl-pepper")
os.environ.setdefault("R2DB_CREDENTIAL_PEPPER", "r2db-http-conformance-import-placeholder-app-pepper")
# Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-2(f)):
# the two surfaces-base-URL env vars main.py/control_main.py used to read
# are REMOVED -- both composition roots now reject either outright (F-2)
# if still defined, whatever its value, so the two `os.environ.setdefault`
# calls a prior phase placed here (to satisfy `build_control_app`'s own
# then-required env vars at import time) are gone (completion condition 14:
# neither name appears anywhere in this file below this point).
# `assemble_control_stack`'s own `surfaces` parameter -- explicitly
# injected below as `_SURFACES` -- was always this adapter's real source
# for its own control stack; only the now-deleted placeholder values
# existed purely to satisfy the OTHER, unused module-level `app = build_
# control_app()` statement `r2db_api.control_main` ends with (still true
# after Q4 WP-1: `build_control_app()` itself remains zero-network -- see
# that module's own docstring -- so this import-time construction still
# never actually reads either variable for anything this adapter uses).

from r2db_api import ControlAuthority, DataService  # noqa: E402
from r2db_api.concurrency_slots import HostSharedConcurrencySlots  # noqa: E402
from r2db_api.control_http import create_control_app  # noqa: E402
from r2db_api.control_main import assemble_control_stack  # noqa: E402
from r2db_api.credential_store import (  # noqa: E402
    PostgresApplicationAuditSink,
    PostgresControlAuditSink,
    PostgresCredentialStore,
)
from r2db_api.errors import FoundationError  # noqa: E402
from r2db_api.http import DEFAULT_THREAD_LIMIT, PROBLEM_CONTENT_TYPE, create_app  # noqa: E402
from r2db_api.limits import ControlPlaneLimits, ResourceLimits, role_pool_size  # noqa: E402
from r2db_api.platform_declarations import VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS  # noqa: E402
from r2db_api.postgres import PostgresCell, default_pool_manager  # noqa: E402

BASE_URL = "http://r2db-http-pg.conformance.invalid"

# R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-1): this
# adapter's own declared writer-connection timeouts for the conformance
# deployment -- NOT the product defaults in `r2db_api.credential_store`
# (`DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`DEFAULT_AUDIT_IDLE_TIMEOUT_MS`,
# 5000/5000, unchanged), which this adapter no longer reads. The platform
# DB unit_of_work here is a handful of ms-scale statements with no
# subprocess/external wait between them, so a much smaller pair is
# sufficient for this deployment; see design D-1 for the measurement that
# backs these two values.
CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS = 1000
CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS = 2000

# WP-5 round-2 review MINOR-1: the exact set of denial codes that mean "the
# cached control credential is genuinely no longer live" (an authority
# refusal), as opposed to a transient/unrelated denial (`LIMIT_EXCEEDED`,
# `AUTH_STATE_UNAVAILABLE`, ...) that must never trigger a destructive
# `ops.py reset` -- see `_privileged_control_send`/`control_credential`'s
# own call sites, both of which now share this one set rather than each
# hand-rolling (and risking drifting) their own copy.
_REPAIRABLE_AUTH_DENIAL_CODES = frozenset({"AUTH_INVALID", "AUTH_REVOKED", "AUTH_REQUIRED", "FORBIDDEN"})

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
SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Same environment variable `r2db-api/tests/test_postgres.py` already uses,
# deliberately reused rather than inventing a second name: one knob governs
# "where is the PostgreSQL admin connection for this repository's tests",
# for both the PostgresCell unit tests and this conformance adapter.
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


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
    controlplane_dsn: str
    # Phase 4 WP-2(b) (design D-5): the `<prefix>_auditreader` role DSN --
    # migration `0007_application_audit.sql`'s own read-only surface.
    auditreader_dsn: str
    schema: str
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
    `0002_provisioning_functions.sql` / `0005_credential_store.sql` /
    `0006_control_plane_http.sql` migrations (with `r2dbsvc` textually
    replaced by this run's unique prefix) through the real `psql` binary --
    the actual runbook an operator would use, not a Python reimplementation
    of it (§5.3 C-5), exactly as `test_postgres.py`'s `platform` fixture
    does. `0005`/`0006` are control-plane bootstrap exactly like
    `0001`/`0002` (independent of any one application), so they run here,
    once, rather than per-application -- `0005` is what makes
    `PostgresCredentialStore` usable at all below (P2-D7: this adapter must
    exercise the real, DB-backed credential store, not the in-memory
    `CredentialStore` the previous revision of this file used); `0006`
    (CCR-14 WP-5) is what makes the real `/control/v1` control-plane
    surface (`r2dbsvc_controlplane` role, `control_credentials`/
    `control_audit` tables) usable. Also rewrites `0003_provision_
    application.sql`/`0004_deprovision_application.sql` the same way and
    keeps them (in `script_dir`, which the caller keeps alive for this
    adapter's whole lifetime -- unlike `test_postgres.py`'s
    `tmp_path_factory`-backed fixture, this adapter has no per-test
    temporary directory to borrow) for `_provision_pg_app`/`close()` to run
    once per application, since database-per-application (architecture §8)
    means provisioning one application is itself now a multi-statement
    script, not a single function call -- see 0002/0003's own header
    comments for why.
    """
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    # Phase 4 WP-2(b) (design D-5): the `auditreader` role migration 0007
    # creates -- SELECT-only on BOTH `control_audit` and `application_audit`.
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    # `0005_credential_store.sql` needs an `api_password` to create the
    # read-only `<prefix>_api` role -- this adapter's own `DataService` now
    # connects as exactly this role (review "逸脱(a)の改善": the request-
    # time read path must run under the same least-privilege grants a real
    # deployment's `r2dbsvc_api` role has, not the full-privilege control
    # role), see `__init__` below.
    api_password = secrets.token_urlsafe(24)
    # `0006_control_plane_http.sql` needs a `controlplane_password` to
    # create the least-privilege `<prefix>_controlplane` role (R-3) -- the
    # role the WP-5 control-plane ASGI app connects as (`control_main.
    # build_control_app`, `__init__` below), never `<prefix>_control`.
    controlplane_password = secrets.token_urlsafe(24)
    # Phase 4 WP-2(b) (design D-5): `0007_application_audit.sql` needs an
    # `auditreader_password` to create the SELECT-only `<prefix>_
    # auditreader` role -- this adapter's own `audit_query` reader
    # (`__init__` below) connects as exactly this role, never `<prefix>_
    # control`/`<prefix>_controlplane` (D-5's own "別 DSN" requirement).
    auditreader_password = secrets.token_urlsafe(24)

    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        "0005_credential_store.sql",
        "0006_control_plane_http.sql",
        "0007_application_audit.sql",
        # R-56 WP-1: role-level `statement_timeout` on `<prefix>_
        # auditreader` -- depends only on 0007 above, so it is safe to
        # apply here even though this adapter's own control stack never
        # reads the DB-side `platform_declarations` table at all.
        "0014_auditreader_statement_timeout.sql",
        # Phase 10 WP-4f (supervisor ruling 2026-09-09): raises `<prefix>_
        # api`/`<prefix>_controlplane`'s own `CONNECTION LIMIT` to match
        # their real pool composition -- WP-4e's own investigation found
        # this adapter's `[r2db-api-socket]` plug tripping the pre-existing
        # `r2dbsvc_controlplane` gap (`CONNECTION LIMIT 10` vs. a real
        # worst case of 16), a genuine production defect this migration
        # fixes, not an adapter-only workaround (the ruling's own
        # constraint: "throwaway platform は本番 migration をそのまま適用
        # する -- adapter 専用に limit を上げない"). Depends only on
        # 0002/0005/0006/0007 above (never on 0008, which this adapter
        # deliberately never runs -- see this function's own docstring),
        # so it is safe to apply here even though this adapter's own
        # control stack never reads the DB-side `platform_declarations`
        # table at all.
        "0013_role_connection_limits.sql",
        # design D-3 (1): the credential-keyed
        # `requests_per_minute` rate table -- depends only on 0005 above
        # (`credentials`), so it is safe to apply here even though this
        # adapter's own control stack never reads the DB-side `platform_
        # declarations` table at all (same reasoning as 0013/0014 above).
        "0015_credential_request_rate.sql",
        # the refusal-window counter and its function -- depends on 0007
        # above (`application_audit`, the `auditreader` role), which this
        # adapter's data plane writes every refusal count through.
        "0016_denial_window_counter.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = script_dir / name
        out.write_text(text)
        rewritten[name] = out
    _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
    control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
    _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
    _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
    _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
    _run_psql(control_dsn, rewritten["0014_auditreader_statement_timeout.sql"])
    _run_psql(control_dsn, rewritten["0013_role_connection_limits.sql"])
    _run_psql(control_dsn, rewritten["0015_credential_request_rate.sql"])
    _run_psql(control_dsn, rewritten["0016_denial_window_counter.sql"])
    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)
    auditreader_dsn = _dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db)

    return _Platform(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        api_dsn=api_dsn,
        controlplane_dsn=controlplane_dsn,
        auditreader_dsn=auditreader_dsn,
        schema=schema,
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


def _prefix_guard_key_param(prefix: str) -> list[str]:
    # A single, obvious place naming the exact SQL parameter every
    # `pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock` call
    # site below passes -- see `_sweep_stale_artifacts`'s own docstring
    # (ledger item L2) for the full rationale. `hashtext(text)` (a stock
    # PostgreSQL builtin, no extension required) maps the prefix string to
    # a stable int4, which the single-`bigint`-argument advisory-lock
    # functions accept via PostgreSQL's own implicit int4->bigint cast --
    # this is the standard idiom for string-keyed advisory locks, not a
    # bespoke hashing scheme this file invents.
    return [prefix]


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

    **Ledger item L2 (WP-5 round-2 independent review, reproduced
    deterministically): pattern-matching alone cannot tell a genuinely dead
    prior run from THIS run's own sibling -- another process's adapter
    construction, still alive, mid-provisioning.** A second process building
    its own registered adapters (even a bare `pytest --collect-only`, which
    constructs every registered adapter at collection time, `conftest.py`'s
    `_discover_and_build`) calling this function while a first process's
    run is between two `_run_psql` migration subprocess calls would --
    before this fix -- see the first run's own prefix as abandoned (it
    matches the pattern the instant its `_control` role/`_platform`
    database exist) and drop it out from under it. A point-in-time activity
    snapshot (`pg_stat_database.numbackends`, the reviewer's first-suggested
    check) does not close this gap either: `numbackends` for a run's own
    platform database can legitimately read 0 in that exact same window
    (no `psql` subprocess connected at that instant, no pooled store
    connections opened yet), which is precisely when the race was measured
    to bite.

    The actual fix is a **held lock, not a snapshot**: every live run
    acquires a session-scoped PostgreSQL advisory lock keyed by its own
    prefix (`__init__`'s `self._prefix_guard`) the moment its prefix is
    chosen -- before anything under that prefix is created, so the lock is
    already in place by the time the prefix becomes pattern-matchable at
    all -- and holds it continuously (a dedicated connection kept open for
    the run's entire lifetime, released only in `_cleanup`) until that run
    is completely torn down. PostgreSQL itself releases a session-scoped
    advisory lock the instant the owning connection's backend terminates,
    for ANY reason including `SIGKILL`/a crash -- exactly the crash-safety
    property this sweep still needs for genuinely dead residue, so a lock
    is strictly stronger than the activity-snapshot alternative, not merely
    different. Before touching any candidate prefix, this function tries to
    take that same lock itself (`pg_try_advisory_lock`): a live owner still
    holds it -> the attempt fails -> that prefix is skipped, sweep or no
    sweep; a dead run's lock is already gone -> the attempt succeeds -> this
    really is unowned residue -> sweep it, then release.
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
        # Ledger item L2: liveness guard -- see this function's own
        # docstring above for the full rationale. A fresh, short-lived
        # connection is enough here (unlike the OWNING run's own
        # long-lived `self._prefix_guard`): acquiring and immediately
        # releasing the lock within one connection's session is exactly
        # the "is anyone else holding this" probe `pg_try_advisory_lock`
        # is for, and holding it for the duration of this prefix's own
        # sweep (closing the connection only after `_sweep_prefix`
        # returns) additionally serializes two sweepers racing the same
        # dead prefix against each other.
        guard = psycopg.connect(admin_dsn, autocommit=True)
        try:
            with guard.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", _prefix_guard_key_param(stale_prefix))
                (acquired,) = cur.fetchone()
            if not acquired:
                continue  # a live process owns this prefix -- never touch it
            _sweep_prefix(admin_dsn, f"{stale_prefix}_platform", stale_prefix)
        finally:
            guard.close()  # releases the advisory lock too (session-scoped)


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


def _failure_details(failure: "_HttpFailure") -> Mapping[str, Any]:
    """port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
    item 2): the real problem+json response's own `details` object, exactly
    as `errors.py`'s `FoundationError.to_dict()` publishes it over HTTP --
    never assembled or interpreted by this adapter. Empty when the response
    was not a well-formed problem+json body at all (`failure.body is None`)
    or carried no `details` key."""
    if failure.body is None:
        return {}
    details = failure.body.get("details")
    return details if isinstance(details, dict) else {}


# Phase 8 WP-1 rework 2 (裁定 3, 監督裁定 2026-09-07): see
# `conformance_adapter_r2db.py`'s own identical-named constant for the
# full rationale (a bounded wait for the background threads to reach
# the stall point, in place of an unbounded `entered.acquire()`, so a
# stall-point regression fails loud instead of hanging the whole test
# process -- `.github/workflows/ci.yml` has no `timeout-minutes` and
# this repository has no pytest-timeout plugin, review finding 3).
_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S = 30.0


@contextmanager
def _hold_in_flight_via_http_requests(
    cell_obj: object, method_name: str, app: Any, secret: str, path: str, n: int,
    classify: Callable[[BaseException], str], adapter_name: str,
    build_client: Callable[[Any, str], httpx.AsyncClient],
):
    """port v1.12 `hold_in_flight` realization for the HTTP plug
    (adapter-internal plumbing, never port-visible -- design docs/design/
    PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-2 実装の形 (b)): identical
    stall-and-wait shape to `conformance_adapter_r2db.py`'s own in-process
    twin, except each of the `n` held requests is a REAL `GET <path>` HTTP
    round trip, issued from its own OS thread against its OWN fresh event
    loop + a client built through `build_client(app, base_url)` -- the
    calling adapter's own `_build_client` hook (monitor 裁定 2026-09-08,
    F-10), never a direct, hook-bypassing `httpx.AsyncClient(ASGITransport(
    app=app))` construction, so a socket-adapter override of `_build_client`
    (WP-4) reaches `hold_in_flight`'s own held requests too, not only the
    shared/isolated surfaces' own clients. The shared adapter's single
    `self._loop.run_until_complete` cannot itself hold more than one
    request in flight (D-2's own "HTTP plug の単一loop構造との折り合い"),
    so genuine concurrency needs one loop per held request, never the
    shared one."""
    original = getattr(cell_obj, method_name)
    entered = threading.Semaphore(0)
    release = threading.Event()
    errors: list[BaseException] = []

    def _stalled(*args: Any, **kwargs: Any) -> Any:
        entered.release()
        release.wait()
        return original(*args, **kwargs)

    setattr(cell_obj, method_name, _stalled)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        try:
            async def _once() -> None:
                async with build_client(app, BASE_URL) as client:
                    response = await client.get(path, headers=[("authorization", f"Bearer {secret}")])
                    if response.status_code >= 400:
                        failure = _HttpFailure(response)
                        raise ConformanceDenial(
                            code=classify(failure), adapter=adapter_name, native_type=type(failure).__name__,
                            details=_failure_details(failure),
                        ) from failure

            loop.run_until_complete(_once())
        except BaseException as exc:  # noqa: BLE001 -- collected, never swallowed; re-raised below after every thread is joined and the method is restored.
            errors.append(exc)
        finally:
            loop.close()

    threads = [threading.Thread(target=_run, daemon=True) for _ in range(n)]
    for t in threads:
        t.start()
    entered_count = 0
    for entered_count in range(n):
        if not entered.acquire(timeout=_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S):
            break
    else:
        entered_count = n
    try:
        if entered_count < n:
            raise AssertionError(
                f"hold_in_flight: only {entered_count} of {n} held HTTP requests "
                f"reached the concurrency-gate stall point within "
                f"{_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S}s (expected every one of them to "
                "stall inside DataService._slot's own counter increment -- see this "
                "helper's own docstring); failing loud instead of hanging (裁定 3, "
                "監督裁定 2026-09-07)"
            )
        # Phase 8 WP-1 rework 3 (裁定 5, 監督裁定 2026-09-07): yields the
        # REAL measured count of held requests (`entered_count`, from the
        # semaphore-acquire loop above) -- never a bare `None` a caller
        # could only pair with a tautological `n >= 1` check. By this
        # point `entered_count == n` always holds (the `AssertionError`
        # above already fired otherwise), but the caller sees the
        # MEASUREMENT, not an echo of its own input.
        yield entered_count
    finally:
        release.set()
        for t in threads:
            t.join(timeout=_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S)
        setattr(cell_obj, method_name, original)
    if errors:
        raise errors[0]


# port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
# WP-6d-ii): `hold_after_idempotency_lookup` realization for this HTTP
# plug. `PostgresCell._idempotency_key_lock` (`postgres.py:1566`/`:2264`)
# takes a `pg_advisory_xact_lock` on this key BEFORE `_idempotency_
# lookup` is ever called, so a second, key-matching request ("B") blocks
# at the DATABASE level -- inside its own `_idempotency_key_lock` call --
# for as long as this hold keeps A's transaction open; it never reaches
# this wrapper's own `_idempotency_lookup`/`_idempotency_reserve` at all
# while A is held (design D-13 "実装の形 (6d-ii) の確定" (4) 表,
# `r2db-api-http` row). `PostgresCell` carries no in-process cell lock of
# its own (its `threading.Lock`s belong to `_RolePool`/
# `SharedPoolManager`, never the request path), so this real advisory
# lock is what B actually waits on, not any Python-level state this
# function holds.


@contextmanager
def _hold_after_idempotency_lookup_via_stalled_cell_methods(cell_obj: object, idempotency_key: str) -> Iterator[IdempotencyHold]:
    original_lookup = cell_obj._idempotency_lookup  # noqa: SLF001
    original_reserve = cell_obj._idempotency_reserve  # noqa: SLF001
    entered = threading.Semaphore(0)
    release = threading.Event()
    armed = threading.local()

    def _lookup(conn: Any, key: str):
        record = original_lookup(conn, key)
        if record is None and key == idempotency_key:
            armed.hold = True
        return record

    def _reserve(conn: Any, limits: Any):
        if getattr(armed, "hold", False):
            armed.hold = False
            entered.release()
            release.wait()
        return original_reserve(conn, limits)

    setattr(cell_obj, "_idempotency_lookup", _lookup)
    setattr(cell_obj, "_idempotency_reserve", _reserve)

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_idempotency_lookup: the held request never reached the end of its "
                f"idempotency admission window within {timeout_s}s (expected it to stall right after "
                "_idempotency_reserve returns -- see this helper's own module comment)"
            )
        return 1

    try:
        yield IdempotencyHold(_wait_until_held)
    finally:
        release.set()
        setattr(cell_obj, "_idempotency_lookup", original_lookup)
        setattr(cell_obj, "_idempotency_reserve", original_reserve)


# port v1.20 (docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
# section 9's `conformance-tests/` paragraph, Q-5): `hold_after_plan_
# verification` realization for this HTTP plug. `PostgresCell.apply_
# schema` reads the revision its `plan` is checked against ONCE, with
# `_read_schema_revision`, inside its transaction and before any DDL
# statement (`postgres.py`, the `revision_before` read; the `plan`
# comparison itself follows the DDL, against the token built from that
# read). The stall point is the return of that `_read_schema_revision`
# call made inside a schema operation presenting a `plan` or `dry_run`:
# after the revision read and after every lock the operation has taken by
# then, before the first DDL statement. `PostgresCell` has no in-process
# cell lock, so what a second schema operation ("B") waits on while the
# first ("A") is held is whatever the database-level serialization of
# schema operations takes -- with none, B runs straight through while A
# is held. The wrap replaces two product methods on the cell instance and
# restores them on exit; no product source changes. It is gated on a
# thread-local mark only this cell's own `apply_schema` wrapper sets, and
# only for a call presenting a `plan` or `dry_run`, and on a claim the
# first caller takes, so `_read_schema_revision` calls made by a data
# operation's delete confirmation, by a schema operation presenting
# neither `plan` nor `dry_run`, a later call and another cell pass
# straight through and exactly ONE schema operation is held.


@contextmanager
def _hold_after_plan_verification_via_stalled_cell_methods(cell_obj: object) -> Iterator[PlanVerificationHold]:
    original_apply_schema = cell_obj.apply_schema  # noqa: SLF001
    original_read = cell_obj._read_schema_revision  # noqa: SLF001
    claimed = threading.Lock()
    entered = threading.Semaphore(0)
    release = threading.Event()
    marked = threading.local()

    def _apply_schema(*args: Any, **kwargs: Any):
        marked.schema_operation = kwargs.get("plan") is not None or bool(kwargs.get("dry_run"))
        try:
            return original_apply_schema(*args, **kwargs)
        finally:
            marked.schema_operation = False

    def _read(conn: Any):
        revision = original_read(conn)
        if getattr(marked, "schema_operation", False) and claimed.acquire(blocking=False):
            entered.release()
            release.wait()
        return revision

    setattr(cell_obj, "apply_schema", _apply_schema)
    setattr(cell_obj, "_read_schema_revision", _read)

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_plan_verification: no schema operation reached the end of its revision read "
                f"within {timeout_s}s (expected the next schema operation presenting a plan or dry_run on this "
                "Application to stall right after _read_schema_revision returns -- see this helper's own "
                "module comment)"
            )
        return 1

    try:
        yield PlanVerificationHold(_wait_until_held)
    finally:
        release.set()
        setattr(cell_obj, "_read_schema_revision", original_read)
        setattr(cell_obj, "apply_schema", original_apply_schema)


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

# Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-2): this HTTP plug's own declared `surfaces` -- same synthetic,
# non-dialable, DIFFERENT-origin convention as `conformance_adapter_r2db.
# py`'s own `_SURFACES` (see that constant's docstring for why the two
# hosts must stay different: `adapter.surfaces_cohosted`'s own origin
# comparison over these two different-host `surfaces` values resolves
# `False` structurally (Phase 6 WP-3 追補, supervisor ruling 2026-09-04:
# the topology-declaration method that once stated this explicitly is
# removed), and
# C-19/test_c09's own declare-and-echo/cohosting vectors are realized as
# repeated real calls to this SAME
# running app, not a literal dial against these strings -- design section
# 6.2 item 2(iii)'s own scope decision, `test_c19_client_self_sufficiency.
# py`'s module docstring).
_SURFACES = {
    "data": {"base_url": "https://r2db-http-pg-data.conformance.invalid/v1"},
    "control": {"base_url": "https://r2db-http-pg-control.conformance.invalid/control/v1"},
}

# Phase 11 WP-3 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5):
# this HTTP (ASGI-transport) plug's own declared `operation_catalog_url` --
# same synthetic, non-dialable convention as `_SURFACES` immediately above
# (C-29's stage (i) never dials this string on an `"asgi"` plug; it calls
# `operation_catalog_document()`, which goes through this SAME running
# app's own real handler over the ASGI transport, not a literal dial
# against this constant). The socket adapter (WP-4) overrides `_operation_
# catalog_url_value` below to report a real, dialable URL instead.
_OPERATION_CATALOG_URL = "https://r2db-http-pg-data.conformance.invalid/v1/operation-catalog"

# port v1.12 (Phase 8 WP-1b, R-A/R-C 監督裁定 2026-09-06) -- same small
# profile, same `operation_depth=5`/`concurrency=3` reasoning, as
# `conformance_adapter_r2db.py`'s own identical constant (this peer's
# `ResourceLimits.check_depth` is backend-independent, `service.py`, so
# the position is identical over HTTP; see the sibling in-process
# adapter's identical constant for the full measured reason). Every
# COUNT-valued class <= C-14's `_MAX_EXERCISABLE_LIMIT` (200) --
# `request_bytes` (byte-valued) is 4096.
_ISOLATED_APPLICATION_LIMITS = ResourceLimits(
    request_bytes=4096,
    batch_items=5,
    result_items=5,
    query_complexity=5,
    execution_ms=5_000,
    concurrency=3,
    requests_per_minute=50,
    schema_objects=20,
    operation_depth=5,
    # Contract 1.7.0 (D-2 (7), U-1 = (β), WP-2a, 監査照合項目 3): small
    # like every other COUNT-valued class above (<= C-14's own
    # `_MAX_EXERCISABLE_LIMIT`, 200) -- a peer-local `enum_members` test
    # can exercise the bound with a handful of members instead of the
    # production default's 64.
    enum_members=5,
    # Contract 1.7.0 (D-5 (5)/S-f, WP-2c, 裁定 J-7 / rulings-r5-r6.md 追補
    # 2): same value/rationale as the in-process plug's own identical
    # constant (`conformance_adapter_r2db.py::_ISOLATED_APPLICATION_
    # LIMITS`) -- small enough for `test_c23_idempotency_semantics.py`'s
    # own (full) leg to drive `declared_entries` distinct-key inserts
    # plus one overflow over HTTP too (`ResourceLimits.check` is
    # backend-independent, `service.py`).
    idempotency_entries=20,
    idempotency_retention_ms=60_000,
)

# Phase 10 WP-4e (supervisor ruling 2026-09-09): the DATA-plane platform
# pools this adapter constructs (`self._credentials`/`self._write_
# credentials`/`self._application_durable_audit`, all against the
# `<prefix>_api` role, migration `0005`) used to be sized `pool_size=2`
# (or the credential store's own internal default of 4) -- a fixed figure
# left over from before WP-8a's `run_in_threadpool` delegation (`r2db_api.
# http`) let concurrent requests' authentication reads genuinely reach
# these pools at once, exactly the F-1 shape `r2db_api.limits.role_pool_
# size` already fixed for the per-application role pools. `_RolePool`
# (`r2db_api.postgres`) creates connections LAZILY up to `maxconn` --
# raising this ceiling does not itself open more real connections against
# `<prefix>_api`'s own `CONNECTION LIMIT` (migration `0005`); it only
# removes the artificial wait/timeout a genuine (if modest) burst of
# concurrent auth traffic used to hit well under that real ceiling.
# design D-3 (5): derived from `DEFAULT_THREAD_LIMIT`
# (never the small `_ISOLATED_APPLICATION_LIMITS` profile above, which
# governs a PostgresCell's own per-application pool -- `_make_cell`'s
# pool_size=2 -- not this platform-plane one) via the SAME `role_pool_
# size` production code (`r2db_api.main`) already uses, so the two can
# never drift apart. `role_pool_size` takes the per-process thread limit,
# not a `ResourceLimits` instance -- see that function's own docstring for
# why the per-process simultaneous-borrow ceiling is the thread limit
# rather than `concurrency`.
#
# Deliberately NOT reused for the control stack's own stores below
# (`self._control_pool_size`, `r2dbsvc_controlplane`, migration `0006`)
# -- WP-4e measured that separately and found raising it does not fix,
# and actively worsens the exposure behind, a DIFFERENT, real bug (a hard
# PostgreSQL `CONNECTION LIMIT` refusal, not a local pool timeout) -- see
# `self._control_pool_size`'s own assignment below for the measured
# detail and why it stays at its original value.
_DEFAULT_PLATFORM_POOL_SIZE = role_pool_size(DEFAULT_THREAD_LIMIT)

# R-78 (D-2 追補): this adapter's own pre-existing per-application data-plane
# pool size, unconditionally `2` until now (`_make_cell` below). `DSA_PERF_
# POOL_SIZE` is a harness-only escape hatch `tools/perf_baseline.py` sets so
# a K-sweep can measure this same plug at the production dimension (`role_
# pool_size(DEFAULT_THREAD_LIMIT)`) as well as
# the existing default -- production code never reads this variable, and
# this function returns the unchanged default `2` whenever it is absent,
# empty, or not a positive integer.
_PERF_POOL_SIZE_ENV = "DSA_PERF_POOL_SIZE"


def _perf_pool_size() -> int:
    raw = os.environ.get(_PERF_POOL_SIZE_ENV)
    if raw is None or raw == "":
        return 2
    try:
        value = int(raw)
    except ValueError:
        return 2
    return value if value > 0 else 2


# Harness-only escape hatch: `tools/perf_baseline.py` sets this so a
# thread-limit sweep can measure this same plug at a size other than
# `create_app`'s own production default, never production code. Absent,
# empty, or not a positive integer all resolve to `DEFAULT_THREAD_LIMIT`
# (`create_app`'s own default) -- the data-plane app is built with the
# SAME effective value either way, never left with anyio's untouched
# default.
_PERF_THREAD_LIMIT_ENV = "DSA_PERF_THREAD_LIMIT"


def _perf_thread_limit_value() -> int:
    raw = os.environ.get(_PERF_THREAD_LIMIT_ENV)
    if raw is None or raw == "":
        return DEFAULT_THREAD_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_THREAD_LIMIT
    return value if value > 0 else DEFAULT_THREAD_LIMIT


class R2DBHttpConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to r2db-api's real HTTP +
    PostgreSQL stack: `r2db_api.http.create_app` in front of a
    `DataService` whose cells are `PostgresCell` instances against a real,
    throwaway-provisioned local PostgreSQL 16 database.
    """

    name = "r2db-api (http+postgres)"
    # port v1.14 (design D-1 (A) 4, WP-3): drives the real ASGI app
    # through `httpx.ASGITransport` (in-process, no real socket) by
    # default -- the socket adapter (WP-4) subclasses this adapter and
    # overrides `transport_kind`/`_build_client`/`_surfaces_value` below,
    # never the other way around.
    transport_kind = "asgi"

    # ------------------------------------------------------------------
    # hooks (design D-1 (A) 6, WP-3): the socket adapter (WP-4) overrides
    # BOTH of these -- `_build_client` to dial a real loopback socket
    # fronted by a real nginx (`conformance-tests/socket_harness.py`)
    # instead of an in-process ASGI transport, and `_surfaces_value` to
    # report that real, dialable URL instead of this module's synthetic,
    # non-dialable `_SURFACES` constant. Every construction site below
    # that used to build a client or inject `surfaces` directly now goes
    # through one of these two hooks, so a subclass overriding them
    # changes EVERY site at once (`__init__`'s data/control clients, the
    # control-stack rebuild path, `isolated_control_surface`, and
    # `isolated_application_surface`) -- extraction is behavior-
    # preserving: the default bodies below are byte-for-byte what every
    # call site constructed directly before this hook existed.
    # ------------------------------------------------------------------

    def _build_client(self, app: Any, base_url: str) -> httpx.AsyncClient:
        """Default: an in-process ASGI-transport client against `app`
        (unchanged behavior). Takes `base_url` even though the default
        body's own choice of host is irrelevant to an ASGI transport (no
        real DNS/TCP happens) -- a real-socket override needs exactly
        this same (app, base_url) shape to dial a real address instead."""
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)

    def _surfaces_value(self) -> dict:
        """Default: this module's own synthetic, non-dialable `_SURFACES`
        constant (unchanged behavior)."""
        return _SURFACES

    def _operation_catalog_url_value(self) -> str:
        """Phase 11 WP-3 (design D-5): same hook shape as `_surfaces_
        value` immediately above -- default: this module's own synthetic,
        non-dialable `_OPERATION_CATALOG_URL` constant. The socket
        adapter (WP-4) overrides this to report a real, dialable URL."""
        return _OPERATION_CATALOG_URL

    def _wire_transport_factory(self) -> Callable[[], httpx.AsyncBaseTransport]:
        """Default: a factory of in-process ASGI transports over this
        surface's own data app -- the transport `wire_entry`'s send
        function hands each request to, one fresh transport per request
        (no state crosses a send). The socket adapter overrides this to
        start its data surface and to return a factory of real-socket
        transports that dial a declared URL exactly as given. Called once,
        from `wire_entry`, before that method returns."""
        app = self._app
        return lambda: httpx.ASGITransport(app=app)

    def _reset_surface_state(self) -> None:
        """Hook (monitor 裁定 2026-09-08, F-2 (b)): called on the ISOLATED
        COPY inside `isolated_application_surface()`, immediately after
        `copy.copy(self)` and before that copy's own composition begins.
        Default: no-op -- this adapter holds no per-surface OS-level
        resource (port reservation, server handle) that a shallow copy
        needs re-initializing on its own; every field the ASGI default
        cares about is either shared read-only state (fine to alias) or
        freshly overwritten a few lines below `isolated_application_
        surface`'s own call site (`_app_pg`/`_provisioned_cells`/
        `_counter`/`_service`/`_control`/`_app`/`_loop`/`_client`). A
        socket-adapter override (WP-4) uses this hook to give its OWN
        copy a dedicated port reservation / server state instead of
        silently sharing whatever `copy.copy` carried over from the
        parent surface (design D-1 (A) 6: `copy.copy` is a SHALLOW copy --
        without an explicit reset hook, a subclass with real per-surface
        handles has no documented, hook-driven place to replace them)."""
        return None

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

        # Ledger item L2 (WP-5 round-2 independent review, reproduced
        # deterministically): acquire this run's own liveness guard --
        # a session-scoped PostgreSQL advisory lock keyed by `prefix`,
        # held on a dedicated connection kept open for this adapter's
        # entire lifetime (released only in `_cleanup`) -- BEFORE anything
        # under this prefix is created, so the lock is already in place
        # the instant this prefix becomes pattern-matchable (the moment
        # `_bootstrap_platform` below creates the `_control` role) and a
        # concurrent process' own `_sweep_stale_artifacts` can see it at
        # all. See `_sweep_stale_artifacts`'s own docstring for the full
        # race this closes and why a held lock, not a point-in-time
        # `pg_stat_database.numbackends` snapshot, is what actually closes
        # it. PostgreSQL releases this lock automatically the instant this
        # connection's backend terminates for ANY reason (including a
        # crash), so a run that dies without running `_cleanup` at all
        # still stops guarding its own (now genuinely dead) prefix
        # immediately -- the sweep's own crash-safety purpose is preserved.
        self._prefix_guard = psycopg.connect(admin_dsn, autocommit=True)
        with self._prefix_guard.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", _prefix_guard_key_param(prefix))

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
        # design D-3 (2')/(4): instance-per-`mkdtemp`
        # slot directory -- a subdirectory of `self._script_dir` so `_cleanup`
        # above (which already `shutil.rmtree`s `self._script_dir`) removes
        # it too, with no separate teardown call needed. Mode 0700
        # explicitly (never trusting the parent's own mode, which `mkdtemp`
        # already gives 0700 by default -- the explicit mode states the
        # requirement here rather than relying on that default silently).
        self._slot_dir = Path(self._script_dir) / "slots"
        self._slot_dir.mkdir(mode=0o700)
        os.chmod(self._slot_dir, 0o700)  # `mkdir(mode=...)` is masked by umask; this is not.
        try:
            self._platform = _bootstrap_platform(prefix, admin_dsn, Path(self._script_dir))
        except Exception:
            # Bootstrap can partially succeed (e.g. 0001 ran, 0002 failed);
            # sweep unconditionally so a failed build never leaves residue
            # in the local cluster. Still holding `self._prefix_guard`
            # throughout this cleanup (closed only afterward) -- exactly
            # the same "hold the lock while sweeping this prefix" discipline
            # `_sweep_stale_artifacts` itself follows for a dead prefix.
            _sweep_prefix(admin_dsn, f"{prefix}_platform", prefix)
            shutil.rmtree(self._script_dir, ignore_errors=True)
            self._prefix_guard.close()
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
            # port v1.6 declare-and-echo (design docs/design/
            # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): cached after the
            # first real `capability_document()` call, mirroring
            # conformance_adapter_r2db.py's identical cache -- this peer's
            # declared `contract_version` is static for this adapter
            # instance's whole lifetime.
            self._contract_version_cache: str | None = None

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
                pool_size=_DEFAULT_PLATFORM_POOL_SIZE,
            )
            self._write_credentials = PostgresCredentialStore(
                self._platform.control_dsn,
                pepper="synthetic-conformance-pepper-r2db-http-0000",
                schema=f"{prefix}_registry",
                pool_size=_DEFAULT_PLATFORM_POOL_SIZE,
            )
            # Phase 4 WP-2(b) (design D-1/D-6): a REAL Postgres `application_
            # audit` writer -- the SAME `<prefix>_api` role/DSN `self.
            # _credentials` above already connects with (migration 0007
            # grants it INSERT-only on this table). Without this, this
            # adapter's own durable application-plane
            # events would stay in-memory only, and C-09 vector 1
            # (observing a destructive delete through `audit_query`) could
            # never see them for THIS (HTTP) adapter -- only for the in-
            # process one.
            # Q4 phase WP-1 (design D-1(b)): `PostgresApplicationAuditSink`
            # no longer accepts or issues a per-connection SESSION `SET`
            # for either timeout -- a REAL deployment's `r2dbsvc_api` role
            # now carries both as a `pg_db_role_setting` role setting
            # (migration `0008`), double-checked at startup by `r2db_api.
            # main.build_app`. This adapter's own throwaway platform
            # database is provisioned only through migration `0007`
            # (`MIGRATION_NAMES` below), never `0008` -- it deliberately
            # never exercises that DB-side declaration/double-check path at
            # all (design §3.11 point 4: "r2db HTTP plugは...宣言表の読み出
            # し経路を通らない"; peer-local real-PG tests, `r2db-api/tests/
            # test_ops_declarations.py`/`test_application_audit.py`, cover
            # that path instead). This writer connection therefore now runs
            # with whatever `statement_timeout`/`idle_in_transaction_
            # session_timeout` the bare PostgreSQL cluster default happens
            # to be -- ordinary, since this adapter's own conformance
            # traffic never depends on either timeout actually firing.
            self._application_durable_audit = PostgresApplicationAuditSink(
                self._platform.api_dsn, schema=self._platform.schema, pool_size=_DEFAULT_PLATFORM_POOL_SIZE,
            )
            self._service = DataService(
                self._credentials, cell_factory=self._make_cell, control_plane_status="enabled",
                durable_audit=self._application_durable_audit, surfaces=self._surfaces_value(),
                operation_catalog_url=self._operation_catalog_url_value(),
                # (design D-3 (4), plug table): `rate` is
                # `self._credentials` itself (the SAME `PostgresCredentialStore`
                # its own read path already uses -- no second, dedicated pool
                # is created for the rate statement). `concurrency_slots` is this instance's own
                # `mkdtemp`ed directory. `concurrency_configured=True`: this
                # plug's `process_ceiling` stays the default `1` (never
                # passed above) and this in-process "supervisor" always has
                # exactly 1 worker, so `ceiling <= workers` always holds.
                rate=self._credentials,
                concurrency_slots=HostSharedConcurrencySlots(self._slot_dir),
                concurrency_configured=True,
            )
            self._control = ControlAuthority(self._service)

            # `DSA_PERF_THREAD_LIMIT` (harness-only, absent in every real
            # conformance run): resolved to its effective value BEFORE
            # `create_app` builds the app, and passed straight through as
            # `thread_limit=` -- `create_app`'s own middleware configures
            # the loop's limiter; this adapter passes the effective value
            # through without wrapping the app itself. `self._perf_
            # thread_limit` always holds that same effective int
            # (`DEFAULT_THREAD_LIMIT` when the env is absent, invalid, or
            # non-positive), so the accessor and `create_app`'s own
            # argument never disagree.
            self._perf_thread_limit = _perf_thread_limit_value()
            app = create_app(self._service, thread_limit=self._perf_thread_limit)
            # Kept on the instance (not just the local `app` above) so
            # `_control_surface_absent` (port v1.5) can inspect this exact,
            # live running app's own route table -- not a second app built
            # separately, and not the module-level `_ROUTES` constant --
            # when it claims no `/control` route exists.
            self._app = app
            self._loop = asyncio.new_event_loop()
            self._client = self._build_client(app, BASE_URL)

            # ------------------------------------------------------------
            # control plane (WP-5 provided branch): the real `/control/v1`
            # ASGI app.
            #
            # WP-5 round-2 review MINOR-3: assembled via `r2db_api.
            # control_main.assemble_control_stack` -- the same shared
            # product-code assembly core `build_control_app` itself calls
            # -- rather than calling `build_control_app` directly. That
            # function returns only the finished ASGI app, with no handle
            # back to the 4 Postgres stores it constructs internally --
            # their `close()` (pool release) is wired only into the app's
            # own ASGI `lifespan` protocol. This repository's conformance
            # adapters do not drive ASGI lifespan at all (the installed
            # httpx 0.28's `ASGITransport` has no `lifespan` parameter;
            # `self._client`/`app` above -- the pre-existing DATA-plane
            # wiring -- already establishes the same "no lifespan,
            # `close()` releases pools directly" pattern this file uses
            # throughout). §13.3's own measured R-7 rate-window problem
            # (below) requires this adapter to be able to rebuild a fresh
            # `ControlPlaneService` (a fresh, empty in-memory rate window)
            # periodically -- WITHOUT leaking the old one's pooled
            # connections, which a bare `build_control_app` call cannot
            # support at all. `assemble_control_stack` returning `(service,
            # stores)` instead of a finished app is exactly what lets this
            # adapter hold real, closeable references while still using
            # the same product assembly code a real deployment does.
            # ------------------------------------------------------------
            self._control_pepper = "synthetic-conformance-pepper-r2db-http-ctl-0000"
            self._control_app_pepper = "synthetic-conformance-pepper-r2db-http-0000"
            # Conformance-build limits profile -- see `_build_control_stack`'s
            # own `applications` comment (mirrors `conformance_adapter_r2db.
            # py`'s identical, measured rationale: the design's own "20"
            # example does not account for every OTHER condition test's
            # `build_fixture()` -> `provision_application()` also writing a
            # real `applications` row on this same, session-scoped platform
            # database). Phase 3.5 WP-3: `115` (raised from `100`) -- see
            # `conformance_adapter_r2db.py`'s own constructor comment for
            # the full, independent-review-corrected causal analysis (m-6):
            # the binding failure (`test_c15_lifecycle_changes_emit_
            # canonical_audit_and_denials_are_recorded`) was NOT caused by
            # `test_c16_cross_entity_atomicity.py` (which runs strictly
            # AFTER `test_c14`/`test_c15` in file-collection order) -- it
            # was `test_c12_capability_agreement.py`'s own new
            # cross_entity_mutation test (`+2` applications, runs BEFORE
            # `test_c14`/`test_c15`) landing `n_existing` at `99`, with
            # `test_c15_...`'s own `fx` fixture (`+2` more) then crossing
            # `100` at its own in-band `register_application_inband` call --
            # minimum sufficient was `~102`. `115` leaves only a 7-unit
            # margin under this class's own hard ceiling (`apps_limit <=
            # 122`, from `rate_limit=200 > (apps_limit+2) + (2*5+1) + 64`,
            # `rate_limit` already at the port's `_MAX_EXERCISABLE_LIMIT`)
            # -- the fix once THAT margin is exhausted is fixture teardown,
            # not another bump (design ledger, §7).
            # Phase 4 WP-2(b): `audit_requests_per_minute` generously
            # headroomed too -- mirrors `conformance_adapter_r2db.py`'s
            # identical constant.
            self._control_limits = ControlPlaneLimits(applications=115, credentials_per_application=5, control_requests_per_minute=200, audit_requests_per_minute=200)
            # `pool_size=2` per store (8 total across the 4 stores) --
            # `r2dbsvc_controlplane`'s own `CONNECTION LIMIT 10` (0006) is
            # the real, enforced ceiling here; the default `pool_size` (4,
            # `R2DB_PLATFORM_POOL_SIZE`'s own default) would let 4 stores'
            # pools alone threaten that limit before even accounting for a
            # rebuild's old-and-new pools briefly coexisting.
            #
            # Phase 10 WP-4e (supervisor ruling 2026-09-09) investigated
            # raising this the same way as the platform-plane pools above
            # (`_DEFAULT_PLATFORM_POOL_SIZE`, derived from `role_pool_
            # size`) and measured it directly against the real 6-plug
            # conformance gate: it does NOT fix, and does not need to fix,
            # the `AUTH_STATE_UNAVAILABLE`/`SERVICE_UNAVAILABLE` failures
            # this WP was diagnosing (`test_c14_resource_bounds_published_
            # and_enforced`/`test_c24_request_budget`/`test_c25_result_
            # request_id`, all `[r2db-api-socket]`) -- debug instrumentation
            # on `_RolePool._connect` (WP-4e report) caught the real
            # underlying exception verbatim: `psycopg.OperationalError`
            # "FATAL: too many connections for role
            # \"<prefix>_controlplane\"", raised on the FIRST-ever
            # connection attempt of a brand-new pool (`created=1`,
            # `elapsed<0.01s`) -- a REAL PostgreSQL `CONNECTION LIMIT`
            # refusal, never a local pool-acquire timeout (`_RolePool`'s
            # own `acquire_timeout` path never fires here). This is a
            # DIFFERENT failure mode from the one `role_pool_size` fixes
            # (WP-8a's F-1: a LOCAL pool sized below declared `concurrency`
            # timing out under genuine in-process contention) -- raising
            # THIS pool's own `maxconn` cannot help, and actively worsens
            # the real exposure: `_RolePool` never shrinks (no idle
            # eviction, unlike `SharedPoolManager`), so a larger `maxconn`
            # lets the SHARED stack's own 4 pools permanently retain more
            # real, cached-idle connections after any historical burst,
            # leaving LESS of the role's hard 10-connection budget for
            # `isolated_control_surface`'s own fresh stack (4 MORE pools,
            # briefly alive alongside the shared one) to open even its
            # first connection. Kept at the original, deliberately small
            # `2` -- a genuine fix needs either a higher `r2dbsvc_
            # controlplane` `CONNECTION LIMIT` (migration change) or an
            # idle-eviction mechanism on `_RolePool` itself, both outside
            # this WP's own scope (pool SIZING/composition only, not pool
            # LIFECYCLE) -- reported for a separate ruling.
            #
            # Phase 10 WP-4f (supervisor ruling 2026-09-09) supplied the
            # "genuine fix" the paragraph above named as out of WP-4e's own
            # scope: `0013_role_connection_limits.sql` (this adapter's own
            # `_bootstrap_platform` now applies it, unconditionally, like
            # every other platform migration -- never an adapter-only
            # override) raises `<prefix>_controlplane`'s own `CONNECTION
            # LIMIT` from 10 to 20. `self._control_pool_size` stays at the
            # SAME deliberately small `2` -- this adapter's own worst case
            # (4 stores x 2 stacks x `pool_size` 2 = 16) now fits with 4
            # connections of headroom under the new limit, matching a real
            # single-process deployment's own worst case (4 stores x fixed
            # `pool_size` 4 = 16, the SAME 16, `0013`'s own migration
            # header) -- raising `_control_pool_size` itself remains
            # unnecessary (and, per the paragraph above, still actively
            # counter-productive against `_RolePool`'s own no-idle-eviction
            # behavior) now that the real constraint it was hitting is
            # fixed at its actual source, the role's own `CONNECTION
            # LIMIT`, not the pool's local `maxconn`.
            self._control_pool_size = 2
            self._control_app, self._control_stores = self._build_control_stack()
            self._control_client = self._build_client(self._control_app, BASE_URL)

            # Durable audit observation (design §12.5(iv)/§4: "Postgres は
            # control_audit に SELECT を持つ r2dbsvc_control 相当DSNの別
            # インスタンスが要る" -- `r2dbsvc_controlplane` itself has no
            # SELECT grant on `control_audit` at all, R-3, so this
            # deliberately connects with `self._platform.control_dsn`
            # instead of `controlplane_dsn`).
            self._control_audit_reader = PostgresControlAuditSink(self._platform.control_dsn, schema=self._platform.schema, pool_size=2)

            # `control_credential()`'s own maintained handle -- same
            # memoize + call-time-validity-check contract as the in-process
            # adapter's identical mechanism (WP-1 M-4).
            self._control_credential_ref: str | None = None
            self._control_credential_secret: str | None = None
            # R-7 rate-window rebuild counter -- see `_privileged_control_
            # send`'s own docstring.
            self._control_request_count = 0
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
            # Ledger item L2: release this run's own liveness guard only
            # now, after this run's own prefix has actually been swept --
            # holding it through our own teardown (rather than releasing it
            # first and sweeping second) means a concurrent sweeper
            # elsewhere can never observe a half-torn-down prefix as
            # "unowned" and race our own cleanup. PostgreSQL releases the
            # advisory lock itself the instant this connection closes;
            # there is no separate `pg_advisory_unlock` call to make.
            self._prefix_guard.close()

    # ------------------------------------------------------------------
    # backend wiring (design R2DB_SERVICE_LAYER_ARCHITECTURE Task 1)
    # ------------------------------------------------------------------

    def _build_control_stack(self, *, limits: "ControlPlaneLimits | None" = None):
        """Assembles one real `/control/v1` ASGI app via `r2db_api.
        control_main.assemble_control_stack` (WP-5 round-2 review MINOR-3)
        -- the exact same shared product-code assembly core `build_control_
        app` itself calls -- and returns `(app, stores)` so the caller can
        `close()` `stores` explicitly later. `create_control_app(service)`
        is called with no `lifespan` argument: this adapter does not drive
        ASGI lifespan at all (see `__init__`'s own note on why), so `stores`
        is closed directly by this adapter's own code instead (`close()`/
        the rebuild path in `_privileged_control_send`).

        `limits` (port v1.11 addendum, supervisor ruling 2026-09-06 item 1):
        defaults to `self._control_limits` (every pre-addendum call site,
        `__init__`'s own rebuild path, and `_privileged_control_send`'s own
        rebuild all omit it, so behavior there is unchanged) -- `isolated_
        control_surface(limits_override=...)` below is this parameter's
        only caller that ever passes something else, a `dataclasses.
        replace`d copy from `apply_limits_override`."""
        service, stores = assemble_control_stack(
            controlplane_dsn=self._platform.controlplane_dsn,
            app_pepper=self._control_app_pepper,
            control_pepper=self._control_pepper,
            schema=self._platform.schema,
            pool_size=self._control_pool_size,
            limits=limits if limits is not None else self._control_limits,
            # Phase 4 WP-2(b) (design D-5): the real `<prefix>_auditreader`
            # DSN -- `visibility_lag_ms` is derived (D-6 point 3) from the
            # two writer-connection timeout defaults `assemble_control_
            # stack` itself falls back to (neither is overridden here, same
            # as the real composition root's own defaults).
            audit_dsn=self._platform.auditreader_dsn,
            audit_reader_pool_size=self._control_pool_size,
            surfaces=self._surfaces_value(),
            # Q4 phase WP-1 (design D-1(c)): this adapter's control stack
            # never reads the DB-side writer-role catalog (design §3.11
            # point 4, see this file's own note at `_application_durable_
            # audit`'s construction site above) -- it passes a fixed value
            # instead. R-105 (design SLOW_CALL_PHASE_TESTS_V0_1 D-1): that
            # fixed value is this adapter's own conformance-deployment
            # value (`CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS` +
            # `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS` + margin), not the
            # product defaults `r2db_api.credential_store` ships (role-
            # level timeout is still not placed on the writer role -- Q4
            # §3.11 point 4 is unchanged). The margin itself is imported
            # from `platform_declarations` (rulings-q4-wp12-rework.md §2),
            # never a repeated literal `1000`.
            audit_visibility_lag_ms=CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS + CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS,
            operation_catalog_url=self._operation_catalog_url_value(),
        )
        app = create_control_app(service)
        return app, stores

    def _make_cell(self, application_id: str, entities: dict[str, list[dict[str, Any]]] | None) -> PostgresCell:
        if entities:
            # This adapter never pre-populates entities at provisioning
            # time (unlike the in-memory `ApplicationCell` default); every
            # entity this adapter creates goes through the real
            # `POST /v1/schema/operations` + `POST .../mutations` HTTP
            # endpoints, exactly as a real client would.
            raise AssertionError("PostgresCell-backed provisioning does not pre-populate entities")
        info = self._app_pg[application_id]
        # R-78 (D-2 追補): harness-only override. `_perf_pool_size()` returns
        # `2` (this adapter's own established `pool_size=2`, unchanged)
        # unless the harness-only `DSA_PERF_POOL_SIZE` environment variable
        # names a positive integer -- production dimensions (`role_pool_
        # size`/`ResourceLimits.concurrency`/role `CONNECTION LIMIT`) are
        # untouched by this env var; conformance's own default plug
        # behaviour is unchanged when it is absent.
        cell = PostgresCell(
            application_id,
            info.schema,
            runtime_dsn=info.runtime_dsn,
            developer_dsn=info.developer_dsn,
            runtime_role=info.runtime_role,
            developer_role=info.developer_role,
            pool_size=_perf_pool_size(),
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
        if self._loop.is_running():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                # Same-thread re-entrancy: THIS thread is already inside
                # a running loop (necessarily `self._loop`, since a
                # second, distinct loop cannot be running concurrently
                # on the same thread) and a coroutine on it called back
                # into `_run`. `asyncio` refuses to drive one loop object
                # from within itself regardless of which loop object is
                # named, so let the normal call below raise its loud,
                # original `RuntimeError('This event loop is already
                # running')` instead of masking it with a throwaway loop.
                return self._loop.run_until_complete(coro)
            # A genuinely different OS thread reached here while this
            # SAME shared adapter instance's own `self._loop` is already
            # mid-flight on ANOTHER thread -- `hold_after_idempotency_
            # lookup`'s own "B" probe, issued by a C-27 test while "A" is
            # held. `asyncio` refuses to drive one loop object from two
            # threads at once (`run_until_complete` raises `RuntimeError
            # ('This event loop is already running')` immediately,
            # measured), so this call gets its OWN throwaway loop
            # instead. Reusing `self._client` itself across loops here is
            # safe on every plug this adapter builds: on the ASGI-
            # transport plugs its transport is `httpx.ASGITransport`, an
            # in-process function call into `app(scope, receive, send)`
            # with no real socket and no per-loop connection pool to
            # mismatch; on this repo's real-socket subclass (`R2DBSocket
            # ConformanceAdapter`), `_LazySocketClient.send` (`conformance_
            # adapter_r2db_socket.py:389-472`, WP-4a) opens a FRESH,
            # one-shot `httpx.AsyncHTTPTransport` per call instead of
            # holding a persistent pool on `self`, so there is likewise no
            # loop-affine state to cross a loop boundary -- every PRE-
            # EXISTING (sequential, single-thread) call path never takes
            # this branch at all, since `self._loop` sits idle between
            # calls.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
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
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                details=_failure_details(failure),
            ) from failure
        if not response.content:
            return {}
        return response.json()

    def _control_send(
        self,
        method: str,
        path: str,
        actor: "CredentialHandle | ControlCredentialHandle | None",
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """`_send`'s exact twin against the control-plane app/client
        (`self._control_client`) instead of the data-plane one -- the same
        Bearer-header/status/problem+json handling, deliberately duplicated
        rather than parameterizing `_send` itself (R-1: no shared code path
        between the two planes beyond the generic HTTP-failure/classify
        machinery every method on this adapter already reuses)."""
        self._control_request_count += 1
        header_pairs: list[tuple[str, str]] = []
        if actor is not None:
            header_pairs.append(("authorization", f"Bearer {actor.secret}"))
        request = self._control_client.build_request(method, path, json=json_body, headers=header_pairs)
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
            raise ConformanceDenial(
                code=exc.code, adapter=self.name, native_type=type(exc).__name__,
                details=getattr(exc, "details", None),
            ) from exc

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
        order_by: list[dict[str, Any]] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        extra_body: Mapping[str, Any] | None = None,
        extra_header_pairs: Sequence[tuple[str, str]] = (),
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"select": select}
        if where is not None:
            body["where"] = where
        # port v1.18 (design D-4, C-30): `order_by` is the SAME wire-shaped
        # `QueryRequest.order_by` array `post_query` already accepts
        # (`r2db-api/src/r2db_api/http.py:468`) -- no prior caller of this
        # method carried it.
        if order_by is not None:
            body["order_by"] = order_by
        # `cursor` (WP-1 correction, sup8): added alongside the
        # pre-existing `page_size`-only shape so `count()`'s own
        # `next_page`-following fallback (see that method) can request a
        # specific page WITHOUT paying for a separate `extra_body={"page":
        # ...}` merge that would silently clobber `page.size` (`body.
        # update(extra_body)` below replaces the whole `page` key, not a
        # per-field merge) -- both fields land in the SAME `page` object
        # the wire body (`QueryRequest.page`, `spec/data-service-
        # api.v1.json`) already carries.
        if page_size is not None or cursor is not None:
            page: dict[str, Any] = {}
            if page_size is not None:
                page["size"] = page_size
            if cursor is not None:
                page["cursor"] = cursor
            body["page"] = page
        # port v1.13 (design docs/design/
        # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-6):
        # `budget` is a QueryRequest top-level field -- carried the same way
        # `attempt_batch_with_addresses`' own `extra_body={"idempotency_
        # key": ...}` already carries a request-level field through.
        if extra_body:
            body.update(extra_body)
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
        # UNCHANGED by the WP-5 C-08 upgrade (design §4: "置き換えられない
        # もの...provision_applicationの実DB provisioning...は特権のまま残
        # す") -- the real PostgreSQL database/role creation this performs
        # (`_provision_pg_app`, 0003) has no in-band equivalent at all
        # (design R-4: `/control/v1` registration only ever produces a
        # "registered, not yet provisioned" row; the contract keeps real
        # provisioning an operator runbook step). `0003`'s own `finish_
        # provision_application` (0006-revised) is what actually writes the
        # real `applications` registry row here (the "operator-first" flow
        # the two-state registry design explicitly keeps working) -- this
        # is why `issue_credential`/etc. below can safely presents an
        # in-band request against `application_id` immediately afterward,
        # without this method separately calling `register_application_
        # inband` at all.
        info = _provision_pg_app(self._platform, application_id)
        self._app_pg[application_id] = info
        self._control.register_application(application_id)

    def _ensure_control_actor(self) -> ControlCredentialHandle:
        """Privileged internal helper (not a port method itself): returns a
        control credential this adapter believes is currently valid and
        must-rotate-cleared (WP-1 M-4's own contract for the PUBLIC
        `control_credential()` method, which delegates here). Trusts the
        cached handle without a preflight probe -- an extra `GET .../
        capabilities` before every real call would double this adapter's
        own control-plane HTTP traffic for no correctness benefit (measured,
        this WP: exhausted the R-7 rate window purely from ordinary
        `build_fixture()` setup traffic, well before any condition test's
        own deliberate rate-boundary vector ran at all). A caller that
        actually needs certainty the returned handle still authenticates
        (`control_credential()` itself, C-15's own vectors) gets that from
        the real operation it performs next -- `_repair_control_actor`
        (below) is what `_privileged_control_send` calls on an actual
        auth-denial, not this method preemptively.
        """
        if self._control_credential_ref is not None:
            return ControlCredentialHandle(credential_ref=self._control_credential_ref, secret=self._control_credential_secret)
        return self._repair_control_actor()

    def _repair_control_actor(self) -> ControlCredentialHandle:
        """Mints a genuinely fresh, must-rotate-cleared control credential
        via the real out-of-band CLI ritual (`python -m r2db_api.ops
        bootstrap`/`reset`, §5 WP-5 handoff's own recommendation: "実
        CLI...実スタック証拠が最強"), then clears `must_rotate` via one real
        in-band self-rotate HTTP call, and updates the tracked cache.
        Called on first use (no cached handle at all) and whenever a
        privileged setup call discovers -- from a real denial, not a
        preflight guess -- that the cached handle is no longer live (WP-1
        M-4: "never memoized past validity")."""
        has_any = self._control_credentials_has_any()
        # Q-1 WP-4: `reset` (unlike `bootstrap`) now goes through the
        # gate's own probe->echo resolution (`_run_reset_ops_cli`) --
        # `bootstrap` is unaffected (never gated; refusing an already-
        # populated store is `CONFLICT`, not a `destructive_confirmation`
        # matter).
        result = self._run_reset_ops_cli() if has_any else self._run_ops_cli("bootstrap")
        if result.returncode != 0:
            raise RuntimeError(f"r2db_api.ops {'reset' if has_any else 'bootstrap'} failed: {result.stderr}")
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        rotated = self._control_send(
            "POST", f"/control/v1/credentials/{quote(credential_id, safe='')}/rotate",
            ControlCredentialHandle(credential_ref=credential_id, secret=secret),
        )
        self._control_credential_ref = credential_id
        self._control_credential_secret = rotated["secret"]
        return ControlCredentialHandle(credential_ref=credential_id, secret=self._control_credential_secret)

    # R-7/§13.3 (this WP's own measurement): the R-7 `control_requests_
    # per_minute` window is process-global on `self._control_app`'s own
    # `ControlPlaneService` instance (design R-7/round-2 review MI-7 --
    # deliberately global, not per-credential, matching the real product).
    # The WP-5 C-08 upgrade routes every ordinary `build_fixture()` setup
    # call (issue_credential x4, occasional disable/enable) through this
    # SAME rate-limited surface across the ENTIRE, long-running conformance
    # session -- measured to exhaust a conformance-buildable (`<= 200`,
    # `test_c14...`'s own `_MAX_EXERCISABLE_LIMIT`) window purely from
    # ordinary fixture churn, well before any test's own deliberate rate
    # vector runs. Design §12.5(ii)'s own anticipated mitigation for this
    # exact "session-scoped adapter shares one window with everything else"
    # shape (there, for the identical concern about C-08 traffic) is
    # "rate を十分大きく取るか service を再構築する" -- raising is maxed out
    # by the port's own SI-08 exercisability ceiling, so this rebuilds a
    # fresh `ControlPlaneService` (a fresh, empty in-memory rate window)
    # periodically. Real, persisted state (`applications`/`credentials`/
    # `control_credentials`/`control_audit`, all in Postgres) is completely
    # unaffected by rebuilding the ASGI app object -- only the in-memory
    # counter resets, exactly as a real deployment's own 60-second sliding
    # window already does continuously on its own. Only ever called from
    # the C-08-upgraded PRIVILEGED setup helpers below
    # (`issue_credential`/`revoke_credential`/`_set_registry_application_
    # enabled`) -- never from any C-14/C-15 test's own direct measurement
    # of this exact rate class (those call `_control_send`/`control_
    # credential()` directly, never these three setup methods), so a
    # rebuild here can never perturb an in-progress SI-08 rate observation.
    _CONTROL_REBUILD_THRESHOLD = 40

    def _privileged_control_send(self, method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._control_request_count >= self._CONTROL_REBUILD_THRESHOLD:
            # WP-5 round-2 review MINOR-2: build the NEW stack/client first,
            # only close the OLD ones after the new ones exist -- pools are
            # lazy (`_RolePool.__init__` opens no connection at all, see
            # `control_main.py`'s own note), so a brief overlap between old
            # and new pools costs nothing. The previous order (close old,
            # then build new) left this adapter permanently bricked -- no
            # working control client at all -- if `_build_control_stack()`
            # itself ever raised.
            old_client = self._control_client
            old_stores = self._control_stores
            self._control_app, self._control_stores = self._build_control_stack()
            self._control_client = self._build_client(self._control_app, BASE_URL)
            self._control_request_count = 0
            # The OLD stack's pooled connections must be released, not
            # merely dereferenced -- see `_build_control_stack`'s own
            # docstring: without this, every rebuild leaks up to `4 *
            # self._control_pool_size` connections against `r2dbsvc_
            # controlplane`'s own real, enforced `CONNECTION LIMIT 10`
            # (0006), which this WP measured failing loudly as `AUTH_STATE_
            # UNAVAILABLE` after only a couple of rebuilds.
            self._run(old_client.aclose())
            for store in old_stores:
                # WP-2(b) fix round 2 (audit finding m-7): `assemble_
                # control_stack`'s 5th tuple element (`audit_reader`) is
                # `None` whenever `audit_dsn` is not given -- this adapter
                # always passes one (`self._build_control_stack`), so this
                # guard is currently unreachable here, but `control_main.
                # build_control_app`'s own identical loop already guards it
                # this way; matching that discipline here removes the
                # asymmetry rather than leaving it to rely on this
                # adapter's own construction-time invariant alone.
                if store is not None:
                    store.close()
        actor = self._ensure_control_actor()
        try:
            return self._control_send(method, path, actor, json_body=json_body)
        except ConformanceDenial as exc:
            if exc.code not in _REPAIRABLE_AUTH_DENIAL_CODES:
                raise
            # The cached handle was not actually live (revoked/disabled by
            # some other test's own C-15 vector, or still must_rotate) --
            # repair via a real ritual run and retry exactly once, never in
            # a loop (a second failure is a genuine problem, not staleness).
            actor = self._repair_control_actor()
            return self._control_send(method, path, actor, json_body=json_body)

    def _control_credentials_has_any(self) -> bool:
        """Read-only existence probe used only to choose `bootstrap` vs
        `reset` in `_ensure_control_actor` -- a direct, privileged read of
        `control_credentials`' row count (never a public capability; this
        adapter's own equivalent of `python -m r2db_api.ops list-apps`-style
        operator tooling, connected as `r2dbsvc_control`, the only role with
        `SELECT` on this table at all -- R-3)."""
        statement = sql.SQL("SELECT count(*) FROM {table}").format(table=sql.Identifier(self._platform.schema, "control_credentials"))
        with psycopg.connect(self._platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(statement)
                (count,) = cur.fetchone()
        return count > 0

    def _run_ops_cli(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["R2DB_CONTROL_DSN"] = self._platform.control_dsn
        env["R2DB_CONTROL_CREDENTIAL_PEPPER"] = self._control_pepper
        env["R2DB_PLATFORM_SCHEMA"] = self._platform.schema
        return subprocess.run([sys.executable, "-m", "r2db_api.ops", *args], capture_output=True, text=True, env=env)

    def _run_reset_ops_cli(self) -> subprocess.CompletedProcess:
        """Q-1 WP-4 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4):
        `python -m r2db_api.ops reset` is now gated by `--confirm
        RESET_CONTROL_CREDENTIALS` -- this is this adapter's own CLI-caller
        equivalent of the wire surfaces' probe->echo resolution (`_resolve_
        confirmation`/`resolve_valid_confirmation`, used elsewhere in this
        same file), not a change to what this adapter asks the ritual to
        do or a new conformance semantic. A first, unconfirmed invocation
        is refused (exit 2, the declaration as one line of JSON on stderr,
        `ops._require_cli_confirmation`'s own shape); this reads
        `required_confirmation` from that declaration and echoes it back on
        a second invocation -- exactly what an operator following
        `POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13 or `CONTROL_PLANE_
        COMPROMISE_PLAYBOOK.md` step 1 does by hand. `RESET_CONTROL_
        CREDENTIALS` happens to be a fixed constant in this WP's own
        implementation, but this adapter deliberately does not hardcode it
        (contract `destructive_confirmation.client_obligation`: "Guessing,
        memorizing, or hardcoding a phrase is not a supported integration
        pattern") -- it is read fresh from the declaration every time,
        exactly like every other `VALID_CONFIRMATION` resolution in this
        file.

        Every caller of this method previously called `self._run_ops_cli
        ("reset")` directly and used the returned `CompletedProcess`
        exactly as `_run_ops_cli`'s own docstring promises (`returncode`/
        `stdout`/`stderr`) -- this method preserves that same external
        contract, returning the SECOND (confirmed) invocation's own
        `CompletedProcess` on the ordinary path so no caller needs to
        change anything beyond the one call site.
        """
        probe = self._run_ops_cli("reset")
        if probe.returncode != 2:
            # Not this gate's own refusal shape at all (e.g. a genuine
            # database/environment failure, or a future implementation
            # change) -- surface it exactly as before, unmodified, so every
            # caller's existing error handling (returncode/stderr parsing)
            # is completely unaffected.
            return probe
        try:
            # nit N-2 (Opus review): the declaration is the LAST non-empty
            # line of stderr, not "the whole stripped stream is one JSON
            # document" -- robust to some other line (a warning a
            # dependency prints, etc.) appearing before it, while still
            # failing loud (M-F's own concern) if the actual last line
            # isn't parseable JSON at all: this does not silently scan
            # backwards past a genuinely malformed final line.
            lines = [line for line in probe.stderr.splitlines() if line.strip()]
            if not lines:
                raise ValueError("empty stderr")
            declaration = json.loads(lines[-1])
            phrase = declaration["details"]["required_confirmation"]
            if not isinstance(phrase, str):
                raise TypeError("required_confirmation must be a string")
        except (ValueError, KeyError, TypeError):
            # Exit code 2 but not a declaration this adapter recognizes --
            # return the original failed CompletedProcess unmodified rather
            # than fabricating a phrase or masking the real problem.
            return probe
        return self._run_ops_cli("reset", "--confirm", phrase)

    @staticmethod
    def _parse_issued_stdout(stdout: str) -> tuple[str, str]:
        credential_id: str | None = None
        secret: str | None = None
        for line in stdout.splitlines():
            if line.startswith("credential_id: "):
                credential_id = line[len("credential_id: "):].strip()
            elif line.startswith("secret: "):
                secret = line[len("secret: "):].strip()
        if not credential_id or not secret:
            raise RuntimeError(f"could not parse issued credential from CLI output:\n{stdout}")
        return credential_id, secret

    def issue_credential(self, application_id: str, role: str) -> CredentialHandle:
        # WP-5 C-08 upgrade (design §4): a real in-band `POST /control/v1/
        # credentials` request, replacing the previous direct `self.
        # _write_credentials.add` DB write -- this out-of-band setup
        # primitive's own EXTERNAL contract (return a real, usable
        # `CredentialHandle`) is unchanged, but it now goes through the
        # same real entry point C-14/C-15's own in-band operations exercise
        # (§4's own "既存条件が...実スタック検証へ自動的に格上げされる").
        result = self._privileged_control_send(
            "POST", "/control/v1/credentials", json_body={"application_id": application_id, "role": role},
        )
        return CredentialHandle(credential_ref=result["credential_id"], application_id=result["application_id"], role=result["role"], secret=result["secret"])

    def revoke_credential(self, handle: CredentialHandle) -> None:
        # WP-5 C-08 upgrade: real in-band `POST .../credentials/{id}/revoke`.
        self._privileged_control_send("POST", f"/control/v1/credentials/{quote(handle.credential_ref, safe='')}/revoke")

    def tampered_bearer(self, handle: "CredentialHandle | ControlCredentialHandle") -> str:
        """port v1.10 追補 (supervisor ruling 2026-09-04, brief item C):
        this peer's own locator bearer shape (`auth.split_bearer_locator`'s
        own inverse) is `<credential_id>.<secret>` -- a bearer naming the
        SAME real `credential_id` with a fresh, never-issued secret
        authenticates as `credential_id`-known-but-digest-mismatched,
        exactly the "bogus secret on a real credential_ref" vector
        `test_c15` needs. Composition ALLOWLISTED at this one line
        (test_c19_client_self_sufficiency.py's own `_COMPOSITION_
        ALLOWLIST`, port docstring's own "the ONLY place ANY adapter
        composes a bearer" rule)."""
        return f"{handle.credential_ref}.{fresh_identifier('tampered')}"

    def disable_application(self, application_id: str) -> None:
        self._set_registry_application_enabled(application_id, False)

    def enable_application(self, application_id: str) -> None:
        self._set_registry_application_enabled(application_id, True)

    def _set_registry_application_enabled(self, application_id: str, enabled: bool) -> None:
        """WP-5 C-08 upgrade (design §4): real in-band `POST .../
        applications/{id}/enable`/`.../disable`, replacing the previous
        direct `UPDATE applications SET enabled = ...` this method used to
        issue itself. Same external contract (an application's real,
        database-backed `enabled` column changes, observed by every C-08
        condition exactly as before -- see this method's own prior
        docstring, preserved below, for why a DB-backed change is the
        property that actually matters here); the *mechanism* now goes
        through the real `/control/v1` surface instead of a hand-rolled
        SQL statement this adapter no longer needs to reproduce.

        Review-reported gap this fixes (pre-WP-5, still true of the real
        entry point used here): an earlier revision of this method *also*
        called `ControlAuthority.set_application_enabled` (which only ever
        toggles `DataService`'s private in-memory `_disabled_apps` set --
        `DataService._check`/`.authenticate` still consult it as a second,
        legacy layer). That in-memory toggle alone was enough to make every
        C-08 disablement condition pass, which meant the real DB-backed
        change could regress to a silent no-op without any conformance test
        noticing -- confirmed by review. `PostgresCredentialStore.
        authenticate`/`assert_active` decide `APPLICATION_DISABLED` from
        the *database* `applications.enabled` column alone (P2-D4); calling
        `ControlAuthority.set_application_enabled` here would only ever
        mask a bug in that DB-backed path, never actually exercise it, so
        it is still deliberately not called from this method at all.
        """
        suffix = "enable" if enabled else "disable"
        self._privileged_control_send("POST", f"/control/v1/applications/{quote(application_id, safe='')}/{suffix}")

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

    def _declared_contract_version(self) -> str:
        # port v1.6 declare-and-echo (design docs/design/
        # DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1): cached after the
        # first real `capability_document()` call over HTTP, mirroring
        # conformance_adapter_r2db.py's identical cache.
        if self._contract_version_cache is None:
            self._contract_version_cache = str(self.capability_document()["contract_version"])
        return self._contract_version_cache

    def _resolve_confirmation(self, confirmation: Any, *, probe: Callable[[], Any], legacy_token: str) -> Any:
        """`VALID_CONFIRMATION` sentinel resolution (design R-6 item 1,
        `adapter.resolve_valid_confirmation`) -- identical contract to
        `conformance_adapter_r2db.py`'s own method of the same name."""
        if confirmation is not VALID_CONFIRMATION:
            return confirmation
        return resolve_valid_confirmation(
            contract_version=self._declared_contract_version(), legacy_token=legacy_token, probe=probe
        )

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5) -- provided branch (WP-5)
    # ------------------------------------------------------------------
    #
    # The real `/control/v1` ASGI app (`self._control_app`/`self.
    # _control_client`, `__init__`/`_build_control_stack`) is assembled via
    # `r2db_api.control_main.assemble_control_stack` (WP-5 round-2 review
    # MINOR-3) -- the SAME shared product-code assembly core `build_control_
    # app` (the real composition root a real deployment runs) calls
    # internally, not a duplicated hand-assembly. This adapter still stops
    # short of calling `build_control_app` itself: that function returns
    # only the finished ASGI app, with no closeable handle back to its own
    # 4 Postgres stores, which this adapter needs to periodically rebuild
    # `ControlPlaneService` and reset its in-memory R-7 rate window without
    # leaking connections (see `_privileged_control_send`'s own docstring)
    # -- `create_control_app(service)` is called directly on the service
    # `assemble_control_stack` returns, with no `lifespan` argument (this
    # adapter does not drive ASGI lifespan at all, closing the 4 stores
    # itself instead). Every in-band method below is a real HTTP request
    # through `_control_send`, exactly as a genuine `/control/v1` caller
    # would issue it -- this adapter never pre-filters by credential kind
    # before presenting a request (design's own "Authorization is the
    # peer's own decision to make, not this port's").

    # port v1.5
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        return self._control_send("GET", "/control/v1/capabilities", actor)

    # port v1.5
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        return self._control_send("POST", "/control/v1/applications", actor, json_body={"application_id": application_id})

    # port v1.5
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        # Response-shape normalization (M-2): unwraps the real
        # `{"applications": [...]}` envelope (port docstring).
        result = self._control_send("GET", "/control/v1/applications", actor)
        return result["applications"]

    # port v1.5
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        suffix = "enable" if enabled else "disable"
        return self._control_send("POST", f"/control/v1/applications/{quote(application_id, safe='')}/{suffix}", actor)

    # port v1.5
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        result = self._control_send(
            "POST", "/control/v1/credentials", actor, json_body={"application_id": application_id, "role": role},
        )
        return CredentialHandle(credential_ref=result["credential_id"], application_id=result["application_id"], role=result["role"], secret=result["secret"])

    # port v1.5
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        result = self._control_send("GET", "/control/v1/credentials", actor)
        return result["credentials"]

    # port v1.5
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        return self._control_send("POST", f"/control/v1/credentials/{quote(credential_ref, safe='')}/rotate", actor)

    # port v1.5
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        body: dict[str, Any] = {}
        if destructive is not None:
            body["destructive"] = destructive
        if confirmation is not None:
            body["confirmation"] = confirmation
        return self._control_send(
            "POST", f"/control/v1/credentials/{quote(credential_ref, safe='')}/revoke", actor,
            json_body=body or None,
        )

    # port v1.5
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        suffix = "enable" if enabled else "disable"
        return self._control_send("POST", f"/control/v1/credentials/{quote(credential_ref, safe='')}/{suffix}", actor)

    @staticmethod
    def _ops_cli_denial_code(stderr: str) -> str:
        """Extracts a contract error code from `ops.py main()`'s own
        `print(f"error: {exc.code}: {exc.message}", file=sys.stderr)`
        format (a `FoundationError` the CLI itself raised, e.g.
        `cmd_bootstrap`'s `CONFLICT`). Anything else (a raw `psycopg.Error`,
        an argparse usage error) does not match this shape and maps to
        `UNCLASSIFIED` -- the identical "a native failure this adapter
        cannot vouch for as a deliberate denial is never laundered into a
        plausible-looking code" discipline `classify()` already applies to
        every other native failure on this adapter."""
        match = re.match(r"error: ([A-Z_]+): ", stderr.strip())
        return match.group(1) if match else UNCLASSIFIED

    # port v1.5 (ritual -- design R-5, no in-band actor by contract): the
    # real out-of-band CLI (`python -m r2db_api.ops bootstrap`), connected
    # as `r2dbsvc_control`-equivalent -- design §3 work order's own
    # recommendation ("実 CLI...実スタック証拠が最強").
    def bootstrap(self) -> ControlCredentialHandle:
        result = self._run_ops_cli("bootstrap")
        if result.returncode != 0:
            code = self._ops_cli_denial_code(result.stderr)
            raise ConformanceDenial(code=code, adapter=self.name, native_type="OpsCliFailure") from RuntimeError(result.stderr)
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        return ControlCredentialHandle(credential_ref=credential_id, secret=secret)

    # port v1.5 (ritual -- design R-5, no in-band actor by contract)
    def reset(self) -> ControlCredentialHandle:
        # Q-1 WP-4: `reset` is now gated -- see `_run_reset_ops_cli`'s own
        # docstring for the probe->echo resolution this delegates to.
        result = self._run_reset_ops_cli()
        if result.returncode != 0:
            code = self._ops_cli_denial_code(result.stderr)
            raise ConformanceDenial(code=code, adapter=self.name, native_type="OpsCliFailure") from RuntimeError(result.stderr)
        credential_id, secret = self._parse_issued_stdout(result.stdout)
        return ControlCredentialHandle(credential_ref=credential_id, secret=secret)

    # port v1.5 (privileged setup)
    def control_credential(self) -> ControlCredentialHandle:
        """Unlike `_ensure_control_actor` (this adapter's own internal
        helper for the C-08-upgraded setup primitives, which deliberately
        trusts its cache to keep ordinary fixture-building traffic cheap --
        see that method's own docstring), this PUBLIC port method verifies
        liveness with one real preflight call before returning: WP-1 M-4's
        contract ("genuinely valid AT CALL TIME") is load-bearing here
        specifically, since C-15's own vectors revoke/reset control
        credentials mid-suite and a LATER, unrelated test calling this
        method must never receive a silently-dead handle it cannot itself
        detect or retry around (unlike the setup primitives, which always
        immediately use the actor for a real operation and can retry on
        failure)."""
        if self._control_credential_ref is not None:
            probe = ControlCredentialHandle(credential_ref=self._control_credential_ref, secret=self._control_credential_secret)
            try:
                self._control_send("GET", "/control/v1/capabilities", probe)
                return probe
            except ConformanceDenial as exc:
                # WP-5 round-2 review MINOR-1: only an actual authority
                # denial means "repair via a destructive reset" -- a
                # transient `LIMIT_EXCEEDED`/`AUTH_STATE_UNAVAILABLE` must
                # propagate as-is (a `reset` in response to either would
                # revoke a still-perfectly-live control credential and mask
                # the real failure as a false "it was stale" story).
                if exc.code not in _REPAIRABLE_AUTH_DENIAL_CODES:
                    raise
        return self._repair_control_actor()

    # port v1.5 (privileged observation)
    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        # Design §12.5(iv)/§4: reads the DURABLE Postgres sink directly
        # (`PostgresControlAuditSink.events()`, connected with
        # `r2dbsvc_control`-equivalent privilege -- `r2dbsvc_controlplane`
        # itself has no SELECT on `control_audit` at all, R-3).
        rows = self._control_audit_reader.events()
        columns = (
            "event_id", "event_class", "occurred_at", "request_id", "application_id",
            "actor_type", "actor_id", "role", "operation", "target_kind", "outcome", "reason_code", "recorded_at",
        )
        return [{col: value for col, value in zip(columns, row) if value is not None} for row in rows]

    # port v1.10 addendum A (supervisor ruling 2026-09-04, C-14 vector 5's
    # own test primitive -- see adapter.py's own docstring for the full
    # rationale). Real HTTP `/control/v1` app/client, built via THIS
    # adapter's own `_build_control_stack()` (the SAME real product
    # assembly `__init__`/`_privileged_control_send`'s own rebuild path
    # already use) against the SAME real Postgres `controlplane_dsn`/
    # `schema` -- so the same registered applications/credentials
    # authenticate -- but a genuinely fresh `ControlPlaneService`, whose
    # own `_rate_window` starts empty. On exit: closes the fresh client
    # and every one of the 4 fresh stores `_build_control_stack()` opened
    # (mirrors `_privileged_control_send`'s own rebuild-path cleanup
    # exactly, including its `store is not None` guard) -- never touches
    # `self._control_app`/`self._control_client`/`self._control_stores`,
    # the SHARED surface every other control-plane method on this adapter
    # still targets.
    @contextmanager
    def isolated_control_surface(self, *, limits_override: Mapping[str, int] | None = None):
        # port v1.11 addendum (supervisor ruling 2026-09-06 item 1): the
        # only change from the pre-addendum construction is passing the
        # (possibly overridden) `limits` through to `_build_control_stack`
        # -- `apply_limits_override` returns `self._control_limits` itself,
        # unchanged, when `limits_override` is `None` (every pre-addendum
        # call site), so this is behavior-preserving for the `control_
        # requests_per_minute` vector.
        effective_limits = apply_limits_override(self._control_limits, limits_override)
        app, stores = self._build_control_stack(limits=effective_limits)
        client = self._build_client(app, BASE_URL)
        # This primitive's OWN residue list (supervisor ruling 2026-09-06
        # item 2): applications `register_application` below registers
        # successfully are recorded here and deprovisioned on exit -- never
        # left for a caller to clean up itself (that would risk a double
        # deprovision attempt against an application this primitive already
        # removed).
        driven_applications: list[str] = []

        def _isolated_send(
            method: str, path: str, actor: "CredentialHandle | ControlCredentialHandle", *,
            json_body: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            request = client.build_request(
                method, path, json=json_body, headers=[("authorization", f"Bearer {actor.secret}")]
            )
            response = self._run(client.send(request))
            if response.status_code >= 400:
                failure = _HttpFailure(response)
                raise ConformanceDenial(
                    code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                    details=_failure_details(failure),
                ) from failure
            if not response.content:
                return {}
            return response.json()

        def call(actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
            return _isolated_send("GET", "/control/v1/capabilities", actor)

        def register_application(
            actor: "CredentialHandle | ControlCredentialHandle", application_id: str
        ) -> Mapping[str, Any]:
            result = _isolated_send(
                "POST", "/control/v1/applications", actor, json_body={"application_id": application_id}
            )
            driven_applications.append(application_id)
            return result

        def list_applications(actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
            result = _isolated_send("GET", "/control/v1/applications", actor)
            return result["applications"]

        try:
            yield IsolatedControlHandle(
                capabilities=call, register_application=register_application, list_applications=list_applications,
            )
        finally:
            self._run(client.aclose())
            for store in stores:
                if store is not None:
                    store.close()
            errors: list[str] = []
            for application_id in driven_applications:
                try:
                    self.deprovision_application(application_id)
                except Exception as exc:  # noqa: BLE001 - report, never swallow.
                    errors.append(f"{application_id!r}: {exc!r}")
            if errors:
                raise RuntimeError(
                    "isolated_control_surface() failed to deprovision one or more applications its own "
                    "handle registered:\n" + "\n".join(f"  - {e}" for e in errors)
                )

    # port v1.11 (design D-6.1 V2/D-6.5 addendum (1)/(4)): unlike
    # `isolated_control_surface()` above, this does NOT reuse `_build_
    # control_stack()`-style product code and does NOT go through
    # `main.py`'s `build_app` composition root -- addendum (1)'s own
    # per-plug table: "data plane は直接構築...composition root を通らな
    # い", and `build_app` has no `limits=` parameter to inject a small
    # profile through in the first place (addendum (1)). Instead, a
    # SECOND, throwaway `DataService`/`ControlAuthority`/ASGI app/httpx
    # client, constructed the SAME way `__init__` above constructs the
    # SHARED ones -- true self-similarity -- but bound to the SMALL
    # `_ISOLATED_APPLICATION_LIMITS` profile and its OWN, empty `_app_pg`/
    # `_provisioned_cells` registries (so a fresh `provision_application`
    # here never collides with the shared surface's own churn).
    #
    # REUSES the shared, already-bootstrapped PG platform (`self._
    # platform`/`self._credentials`/`self._write_credentials`/`self._
    # application_durable_audit`) rather than re-provisioning a second
    # platform database from scratch -- addendum (1): "この経路が要求す
    # るものは無し" (no additional platform-DB seed) is exactly this:
    # `_provision_pg_app` (the real per-application PostgreSQL
    # provisioning this isolated instance's own `provision_application`
    # still goes through, via `_make_cell` below) only ever needs the
    # ALREADY-bootstrapped platform/migrations, never a second bootstrap.
    # Built via `object.__new__` (not `R2DBHttpConformanceAdapter()`)
    # specifically so it does NOT repeat the real, expensive PostgreSQL
    # platform bootstrap (`_bootstrap_platform`: fresh prefix, advisory
    # lock, migrations 0001-0007) on every call -- this primitive is
    # expected to be entered once per D-6.2 driven class, so repeating
    # that bootstrap each time would make the common suite's own runtime
    # scale with the number of driven classes for no real isolation
    # benefit (the platform itself carries no per-application state this
    # isolated instance's OWN small `DataService.limits`/empty cell
    # registry does not already isolate).
    #
    # On exit: closes ONLY what this isolated instance itself opened (its
    # own httpx client, its own event loop, its own `PostgresCell` pools
    # -- `pool_size=2` each, `_make_cell`'s own real per-application
    # connection pool, D-6.5 addendum (3)) -- never `self.close()` (which
    # would drop the SHARED platform database this isolated instance
    # borrows).
    @contextmanager
    def isolated_application_surface(self):
        # `copy.copy(self)` (shallow) rather than `object.__new__` +
        # selective attribute assignment: this peer's `issue_credential`
        # (WP-5 C-08 upgrade) is itself an IN-BAND `/control/v1/
        # credentials` HTTP call -- it needs the SAME real control-plane
        # client/app/credential-ref state `self` already holds (borrowing
        # the shared control surface for setup is explicitly fine here,
        # D-6.5 addendum's own table: "無し" -- no extra control seed is
        # needed to build the ISOLATED APPLICATION surface). A shallow
        # copy shares every one of those references by construction
        # (control client/app/pepper/credential-ref/stores, `self.
        # _platform`, `self._credentials`/`self._write_credentials`,
        # `self._application_durable_audit`) so nothing about the control
        # plane needs to be named here at all -- only the DATA-plane
        # pieces below are deliberately overwritten with fresh, isolated
        # ones.
        iso = copy.copy(self)
        iso._reset_surface_state()
        # `_control_send`/`_privileged_control_send` are ordinary bound
        # methods, so an unqualified `iso._control_send(...)` call runs
        # with `self` bound to `iso`
        # itself, not to the parent this comment above says the control
        # plane is merely "borrowed" from. Once `iso`'s own request
        # count on that borrowed-but-`iso`-bound path reaches the
        # control-rebuild threshold, `iso._build_control_stack()` builds
        # a NEW control app from `iso`'s own (isolated) data surface and
        # then rebinds it onto `iso._control_surface` -- which is the
        # SAME object the parent holds (shared by the shallow copy
        # above), so the parent's real control dispatch silently starts
        # answering with `iso`'s isolated surfaces, and the rebuild path
        # closes the PARENT's own control client/store out from under it
        # (measured: `test_c29_data_and_control_planes_declare_the_same_
        # url[r2db-api-socket]` reproduces this deterministically with
        # the rebuild threshold lowered). Rebinding these two methods to
        # the PARENT's own bound instances here makes every control call
        # `iso` makes run with `self` == the parent, so any rebuild the
        # borrowed request count triggers happens on the real owner, not
        # on this transient, isolated copy.
        iso._control_send = self._control_send
        iso._privileged_control_send = self._privileged_control_send
        iso._app_pg = {}
        iso._provisioned_cells = []
        iso._counter = 0
        # design D-3 (2')/§1.4 (6): a SEPARATE, freshly
        # `mkdtemp`ed slot directory for this isolated instance -- never
        # `self._slot_dir` (the shared surface's own), so this isolated
        # surface's own concurrency admission never contends with (or is
        # confused for) the shared one's. Removed in the `finally` block
        # below, alongside this instance's own other isolated teardown.
        iso_slot_dir = Path(tempfile.mkdtemp(prefix="r2db_http_isolated_slots_"))
        iso._slot_dir = iso_slot_dir
        iso._service = DataService(
            iso._credentials, limits=_ISOLATED_APPLICATION_LIMITS, cell_factory=iso._make_cell,
            control_plane_status="enabled", durable_audit=iso._application_durable_audit,
            surfaces=iso._surfaces_value(), operation_catalog_url=iso._operation_catalog_url_value(),
            rate=iso._credentials,
            concurrency_slots=HostSharedConcurrencySlots(iso_slot_dir),
            concurrency_configured=True,
        )
        iso._control = ControlAuthority(iso._service)
        app = create_app(iso._service)
        iso._app = app
        iso._loop = asyncio.new_event_loop()
        iso._client = iso._build_client(app, BASE_URL)
        try:
            yield iso
        finally:
            # WP-4 fix (first-execution finding): this isolated instance's
            # own `provision_application` writes into the SHARED platform
            # database's `applications` registry table (D-6.5 addendum
            # (1): "この経路が要求するものは無し" means no EXTRA seed is
            # needed, not that writes stay private) -- the SAME table
            # C-14 vector 5's own `n_existing < apps_limit` precondition
            # reads. Left uncleaned, C-05's own repeated per-class isolated
            # surfaces silently saturate that shared bound for every LATER
            # test in the session. Deprovisioned the same way C-14 vector
            # 5 cleans up its own throwaway Applications. Cells' own pool
            # connections are closed FIRST -- `deprovision_application`
            # drops the per-application PostgreSQL database, which fails
            # ("being accessed by other users") while this instance's own
            # pool still holds live connections to it.
            iso._run(iso._client.aclose())
            for cell in iso._provisioned_cells:
                cell.close()
            for app_id in list(iso._app_pg):
                iso.deprovision_application(app_id)
            iso._loop.close()
            shutil.rmtree(iso_slot_dir, ignore_errors=True)

    # port v1.12 (design D-2 実装の形 (b), work order WP-1b): wraps the
    # SAME per-application `PostgresCell.catalog()` `DataService._slot`'s
    # own dispatch calls into (`service.py:942`), after the concurrency
    # counter's own increment and BEFORE any backend/DB call (`catalog()`
    # opens its own live connection, bounded by the same per-transaction
    # `statement_timeout`/`lock_timeout` the other 3 operations carry).
    # Each held request is a REAL `GET /v1/catalog` HTTP round trip,
    # issued from its OWN OS thread
    # with its OWN event loop + `httpx.AsyncClient(ASGITransport(...))`
    # against the SAME running ASGI app (`self._loop.run_until_complete`
    # on the shared, single loop `_send()` uses cannot itself hold more
    # than one request in flight -- design D-2's own "HTTP plug の単一
    # loop 構造との折り合い"). Never touches the shared adapter's own
    # `self._loop`/`self._client` -- entirely self-contained within this
    # call.
    def hold_in_flight(self, session, n: int):
        """See `ConformanceAdapter.hold_in_flight`'s own docstring
        (`adapter.py`) for this primitive's port-level meaning; this
        realization's own stall point and line references are documented
        on the comment immediately above this method."""
        assert isinstance(session, _Session)
        app_id = self.scope_of(session).application_id
        cell = self._service._cells[app_id]  # noqa: SLF001 -- adapter-internal plumbing, same convention isolated_application_surface() above already uses.
        app = self._app
        secret = session.secret
        classify = self.classify
        adapter_name = self.name
        return _hold_in_flight_via_http_requests(
            cell, "catalog", app, secret, "/v1/catalog", n, classify, adapter_name, self._build_client,
        )

    # port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
    # WP-6d-ii): wraps the SAME per-application `PostgresCell`'s own
    # `_idempotency_lookup`/`_idempotency_reserve` (`postgres.py:1283`/
    # `:1296`). See `_hold_after_idempotency_lookup_via_stalled_cell_
    # methods`'s own module comment for why the REAL `pg_advisory_xact_
    # lock` this cell already takes (WP-6d-i), not any state this hook
    # holds, is what a concurrent second request actually waits on.
    def hold_after_idempotency_lookup(self, session, idempotency_key: str):
        """See `ConformanceAdapter.hold_after_idempotency_lookup`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_idempotency_lookup_via_stalled_cell_methods` and the
        comment immediately above this method."""
        assert isinstance(session, _Session)
        app_id = self.scope_of(session).application_id
        cell = self._service._cells[app_id]  # noqa: SLF001
        return _hold_after_idempotency_lookup_via_stalled_cell_methods(cell, idempotency_key)

    # port v1.20: wraps this SAME per-application `PostgresCell`'s `apply_schema` and
    # `_read_schema_revision` -- see `_hold_after_plan_verification_via_stalled_cell_methods`'s own
    # module comment for the stall point.
    def hold_after_plan_verification(self, session):
        """See `ConformanceAdapter.hold_after_plan_verification`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_plan_verification_via_stalled_cell_methods` and the
        comment immediately above it."""
        assert isinstance(session, _Session)
        app_id = self.scope_of(session).application_id
        cell = self._service._cells[app_id]  # noqa: SLF001
        return _hold_after_plan_verification_via_stalled_cell_methods(cell)

    def wire_entry(self, application_id: str) -> WireEntry:
        """See `ConformanceAdapter.wire_entry`'s own docstring
        (`adapter.py`) for this method's port-level meaning. Both
        credentials come from `issue_credential`, this adapter's own
        bootstrap path. The send function builds an `httpx.Request` from
        exactly the four values it is given and hands it straight to a
        fresh transport from `_wire_transport_factory` -- never through an
        `httpx.AsyncClient`, whose default headers, cookie jar and redirect
        handling would otherwise act on the request."""
        runtime = self.issue_credential(application_id, "runtime")
        developer = self.issue_credential(application_id, "developer")
        transport_factory = self._wire_transport_factory()
        base_url = self._surfaces_value()["data"]["base_url"]
        run = self._run

        async def _carry(
            method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None
        ) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
            transport = transport_factory()
            try:
                request = httpx.Request(method, url, headers=list(headers), content=body)
                if request.method != method or str(request.url) != url or request.url.fragment or request.url.userinfo:
                    raise ValueError(
                        "send: the method or URL is not in the HTTP library's own normal form, "
                        "so it would not be carried as given: method=%r url=%r" % (method, url)
                    )
                response = await transport.handle_async_request(request)
                await response.aread()
            finally:
                await transport.aclose()
            received = tuple(
                (name.decode("latin-1"), value.decode("latin-1")) for name, value in response.headers.raw
            )
            return response.status_code, received, response.content

        def send(
            method: str, url: str, headers: tuple[tuple[str, str], ...], body: bytes | None
        ) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
            return run(_carry(method, url, headers, body))

        return WireEntry(
            base_url=base_url,
            send=send,
            runtime_secret=runtime.secret,
            developer_secret=developer.secret,
        )

    # ------------------------------------------------------------------
    # audit_query surface (port v1.8, phase 4 WP-2(b) PROVIDED branch).
    # Real HTTP POST /v1/audit/query -- against the CONTROL client (`self.
    # _control_client`), never the data-plane client (design docs/design/
    # PHASE4_DURABLE_AUDIT_SINK_V1.md
    # §8.3/D-5: the contract's application-surface path string is served
    # by the control host as an alias of control_endpoints.audit_query,
    # not by the data-plane host at all -- data-plane's own POST /v1/
    # audit/query stays the pre-existing CAPABILITY_UNSUPPORTED stub,
    # unreached by this method). Since WP-2(b)'s flip r2db-api's control
    # host declares `audit_query: {"status": "enabled", ...}` whenever the
    # reader DSN is configured -- which this adapter's own harness does --
    # so every one of the three methods below takes the PROVIDED branch.
    # They were written in WP-1 against this real, eventual dispatch shape,
    # so the flip needed no restructuring here; the `SurfaceAbsent`
    # declare-first branch is retained and remains the correct dispatch for
    # a deployment that declares no audit surface.
    # ------------------------------------------------------------------

    def _audit_query_status(self) -> str:
        # Reads via this adapter's OWN privileged control credential
        # (`control_credential()`), never via the `actor` a caller of
        # `audit_query` supplies -- `control_plane.authority` fails an
        # APPLICATION credential closed on `control_capabilities` itself,
        # so gating on `actor`'s own authority would make C-09 vector 3
        # (application credential -> FORBIDDEN on `audit_query` once
        # enabled) unreachable.
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
        # design R1 / work order WP-1 §"変更対象": the CONTROL base URL
        # serves this application-surface path string as an alias
        # (control_endpoints.audit_query's own real handler) -- not the
        # data-plane client, which stays the pre-existing unavailable
        # stub. `/v1/audit/query`, not `/control/v1/audit/query`: this
        # adapter deliberately exercises the alias path, matching the
        # work order's own explicit instruction for this WP; both paths
        # resolve to the identical handler once a peer implements D-5.
        return self._control_send("POST", "/v1/audit/query", actor, json_body=dict(request))

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
    # plane client). No declare-first `SurfaceAbsent` gate here: `/v1/
    # audit/query` is unconditionally mounted on the data-plane app
    # regardless of `audit_query`'s own declared status (`http.py`'s own
    # `_ROUTES`), so a real request always reaches a real handler.
    def _data_send_with_actor(
        self, method: str, path: str, actor: "CredentialHandle | ControlCredentialHandle", *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        header_pairs = [("authorization", f"Bearer {actor.secret}")]
        request = self._client.build_request(method, path, json=json_body, headers=header_pairs)
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

    def audit_query_on_data_plane_host(
        self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._data_send_with_actor("POST", "/v1/audit/query", actor, json_body=dict(request))

    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    # pre-1.6.0 topology-declaration method this adapter once implemented
    # here is removed -- the port's own `surfaces_cohosted` free function
    # is now surfaces-derived only (both peers declare 1.6.0
    # unconditionally).

    # port v1.5 (fix-round): the inverse of `provision_application` --
    # operator-privileged test-harness cleanup, never a public capability.
    # Design §12.5(iii)/work order §3: handles BOTH shapes this adapter's
    # own `provision_application`/`register_application_inband` can leave
    # behind --
    #
    #   (a) registered-only (`database_name IS NULL` -- an in-band-only
    #       registration, e.g. C-14 vector 5's own `applications` bound
    #       drive): `0004`'s own `begin_deprovision_application` explicitly
    #       REFUSES such a row (0006's own revision: "登録済みのみの行は
    #       deprovision対象にならない") -- the registry-row-only DELETE the
    #       work order itself prescribes ("0004は provisioned前提") is the
    #       only correct removal for this shape.
    #   (b) fully DB-provisioned (via the out-of-band `provision_
    #       application` setup primitive, e.g. C-14 vector 5's own
    #       `credentials_per_application` drive's `cred_app`): the real
    #       0004 script, which additionally requires no surviving
    #       `credentials` row for this slug at all (even a revoked one --
    #       `assert_no_credentials_for_deprovision`) -- this method clears
    #       any residual in-band-issued credential rows for the slug first
    #       (the drive's own cleanup only ever revokes, never deletes, the
    #       credentials it issued), mirroring what an operator's real
    #       deprovisioning runbook step would do.
    def deprovision_application(self, application_id: str) -> None:
        # Phase 7 WP-5 rework (supervisor ruling 2026-09-06 item 1): closes
        # any of THIS instance's own `_provisioned_cells` that belong to
        # `application_id` before the DROP DATABASE below -- previously
        # only `isolated_application_surface()`'s own hand-written exit
        # sequence did this (that context manager's own `_provisioned_
        # cells`/`_app_pg` are private to the isolated instance it
        # constructs, never these attributes). A cell's own two pools are
        # cached in the module-level `SharedPoolManager`
        # (`r2db_api.postgres.default_pool_manager`) keyed by
        # `application_id`, independent of the `PostgresCell` Python
        # object's own lifetime -- dropping the object (or this method's
        # own pre-existing `self._app_pg.pop(...)` below) does not, by
        # itself, release those pooled connections back to the manager;
        # only `PostgresCell.close()` does. Without this, any caller that
        # deprovisions an application this SHARED, session-scoped adapter
        # already served real data-plane traffic for (every ordinary
        # `fx`-based test's own `app_a`/`app_b`, once WP-5's own generic
        # residue-cleanup teardown starts calling this on every test's
        # applications, not just this file's own already-cell-free
        # control-plane-only throwaway apps) hits a real `DROP DATABASE
        # ... is being accessed by other users` failure -- exactly the
        # failure WP-5 round 3 measured and, before this fix, could only
        # route around by using `isolated_application_surface()` instead
        # of this method directly. Fixing it here, once, makes this
        # method itself safe for every caller (this WP-5 rework's own
        # residue-cleanup teardown included) rather than requiring each
        # caller to separately rediscover the same close-then-deprovision
        # ordering `isolated_application_surface()`'s exit already knew.
        remaining_cells = []
        for cell in self._provisioned_cells:
            if cell.application_id == application_id:
                cell.close()
            else:
                remaining_cells.append(cell)
        self._provisioned_cells = remaining_cells

        provisioned_statement = sql.SQL("SELECT database_name IS NOT NULL FROM {table} WHERE application_slug = {ph}").format(
            table=sql.Identifier(self._platform.schema, "applications"), ph=sql.Placeholder()
        )
        with psycopg.connect(self._platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(provisioned_statement, [application_id])
                row = cur.fetchone()
            if row is None:
                return  # already gone -- nothing to clean up
            provisioned = row[0]
            delete_credentials_statement = sql.SQL("DELETE FROM {table} WHERE application_slug = {ph}").format(
                table=sql.Identifier(self._platform.schema, "credentials"), ph=sql.Placeholder()
            )
            with conn.cursor() as cur:
                cur.execute(delete_credentials_statement, [application_id])
            if not provisioned:
                # Phase 7 WP-5 rework (supervisor ruling 2026-09-06 item 1,
                # first-execution finding): a "registered, not yet
                # provisioned" Application can still have real in-band
                # credentials issued against it (design R-4: "登録済みだが
                # 未 provisioning の Application への credential 発行は許
                # す") -- `test_c14_authority_boundary.py::test_c14_
                # declared_status_agrees_with_actual_surface` and
                # `test_c15_bootstrap_reset_lifecycle.py`'s own audit test
                # both do exactly this. Before this fix, this branch's own
                # `DELETE FROM applications` ran with no credentials
                # cleanup first, and hit `credentials_application_slug_
                # fkey` (`ForeignKeyViolation`) the moment WP-5's own
                # generic residue-cleanup teardown started calling this
                # method on such an application for the first time -- the
                # existing, narrower callers of this method (this file's
                # own `test_c14_authority_boundary.py`) never happened to
                # combine "registered-only" with "has a live credential"
                # in one call site before. The credentials delete above now
                # runs unconditionally, before this branch's own
                # applications-row delete, exactly mirroring the
                # already-provisioned branch below.
                delete_statement = sql.SQL("DELETE FROM {table} WHERE application_slug = {ph}").format(
                    table=sql.Identifier(self._platform.schema, "applications"), ph=sql.Placeholder()
                )
                with conn.cursor() as cur:
                    cur.execute(delete_statement, [application_id])
                conn.commit()
                return
            conn.commit()
        _run_psql(self._platform.control_dsn, self._platform.deprovision_script, {"app_slug": application_id})
        self._app_pg.pop(application_id, None)

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
        self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any, *, limit: int | None = None
    ) -> list[dict]:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        # port v1.12 (L7-21): `limit` maps directly onto `_query_request`'s
        # own pre-existing `page_size` keyword (`:1308`, unchanged by this
        # WP), which in turn puts `{"page": {"size": page_size}}` on the
        # real wire body (`QueryRequest.page.size`, `spec/data-service-
        # api.v1.json`) -- `None` omits it, exactly as every pre-v1.12
        # caller here already observed.
        result = self._query_request(session, entity, select=list(select), where=where, page_size=limit)
        return result["items"]

    def attempt_filter(
        self,
        session: object,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
    ) -> list[dict]:
        assert isinstance(session, _Session)
        # Same real query endpoint `select_eq` above already uses,
        # generalized to an arbitrary operator -- see
        # conformance_adapter_r2db.py's identical method for the full
        # rationale.
        where = [{"field": field, "operator": operator, "value": value}]
        # port v1.12 (L7-21): additional predicates appended to the SAME
        # real `where` array the wire body already carries (`QueryRequest.
        # where`, `maxItems: 50`) -- never a second request.
        if extra_predicates:
            where.extend({"field": f, "operator": o, "value": v} for f, o, v in extra_predicates)
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
        # VALID_CONFIRMATION sentinel protocol (design section 10.1,
        # updated port v1.6 for declare-and-echo -- identical to
        # conformance_adapter_r2db.py's own `delete()`): `destructive`
        # always passes through faithfully; this adapter never upgrades a
        # non-destructive/unconfirmed request into a confirmed destructive
        # one.
        def probe() -> None:
            self._mutate_request(session, entity, [{
                "operation": "delete",
                "where": [{"field": field, "operator": "eq", "value": value}],
                "destructive": True,
            }])

        peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
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
        # WP-1 correction (sup8, C-23 http full-store leg diagnosis): a
        # single `page_size=1000` request assumed the matched-row count
        # always stays within whatever `result_items` bound THIS
        # deployment declares -- true everywhere else this method is
        # called, but not on the isolated HTTP surface's own C-23 (full)
        # leg (`test_c23_idempotency_semantics.py`), which deliberately
        # inserts this deployment's declared `idempotency_entries`
        # (isolated profile: 20) distinct rows into a fresh entity -- more
        # than the SAME isolated profile's own small `result_items` (5).
        # `ResourceLimits.check("result_items", ...)` (`postgres.py::
        # query`, `min(len(rows), page_size)`) bounds a SINGLE page's
        # returned item count, not the query's total match count -- a real
        # HTTP client pages through `next_page` to enumerate more matches
        # than `result_items` allows per page, exactly what this now does
        # on that denial, instead of assuming one page always suffices.
        try:
            result = self._query_request(session, entity, select=list(fields), page_size=1000)
            return len(result["items"])
        except ConformanceDenial as exc:
            if exc.details.get("limit_class") != "result_items":
                raise
            bound = exc.details.get("limit")
            if not isinstance(bound, int) or bound <= 0:
                raise
        total = 0
        cursor: str | None = None
        while True:
            result = self._query_request(session, entity, select=list(fields), page_size=bound, cursor=cursor)
            total += len(result["items"])
            cursor = result.get("next_page")
            if not cursor:
                return total

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

    # port v1.10 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
    # V1.md section 6.1 item 3, D-3). Real HTTP POST to this peer's real
    # schema-operation endpoint, carrying the contract's own `field_types`
    # object verbatim -- mirrors `conformance_adapter_r2db.py`'s identical
    # in-process twin. Unreachable as of this WP (declare-first gated at
    # 1.6.0, no peer there yet); a real call today would get a real
    # `VALIDATION_FAILED` from this peer's pre-1.6.0 schema-operation
    # validation, which does not yet recognize `field_types` -- written
    # for WP-2's real eventual shape, not a stub.
    def create_entity_with_declared_types(
        self, session: object, entity: str, fields: Sequence[str], field_types: Mapping[str, str] | None
    ) -> None:
        assert isinstance(session, _Session)
        body: dict[str, Any] = {"operation": "create_entity", "entity": entity, "fields": list(fields)}
        if field_types:
            body["field_types"] = dict(field_types)
        self._send("POST", self._schema_path(), session, json_body=body)

    def schema_operation_with_result(
        self,
        session: object,
        entity: str,
        operation: str,
        *,
        field: str | None = None,
        field_type: str | None = None,
        fields: Sequence[str] | None = None,
        field_types: Mapping[str, str] | None = None,
        field_constraints: Mapping[str, Mapping[str, Any]] | None = None,
        enum: Sequence[Any] | _EnumClear | None = None,
        nullable: bool | None = None,
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        # port v1.13 (design D-2/D-4/D-5/D-6/D-8, §6.1 items 1-5, 7, 8): one
        # general schema-operation primitive, presented to the same real,
        # single schema-operations endpoint every other schema method on
        # this adapter already uses. `destructive`/`confirmation` follow
        # the identical VALID_CONFIRMATION sentinel protocol `drop_entity`
        # below uses. `enum` is tri-state (port v1.13 追補, `adapter.
        # ENUM_CLEAR`): omitted -> no `enum` key on the wire; `ENUM_CLEAR`
        # -> a literal JSON `enum: null`; a `Sequence` -> `enum: [...]`,
        # exactly as before this addendum.
        assert isinstance(session, _Session)
        body: dict[str, Any] = {"operation": operation, "entity": entity}
        if field is not None:
            body["field"] = field
        if field_type is not None:
            body["field_type"] = field_type
        if fields is not None:
            body["fields"] = list(fields)
        if field_types:
            body["field_types"] = dict(field_types)
        if field_constraints:
            body["field_constraints"] = {k: dict(v) for k, v in field_constraints.items()}
        if enum is ENUM_CLEAR:
            body["enum"] = None
        elif enum is not None:
            body["enum"] = list(enum)
        if nullable is not None:
            body["nullable"] = nullable
        if destructive:
            body["destructive"] = True
        if confirmation is not None:
            if confirmation is VALID_CONFIRMATION:
                probe_body = dict(body)
                probe_body["destructive"] = True

                def probe(_probe_body=probe_body) -> None:
                    self._send("POST", self._schema_path(), session, json_body=dict(_probe_body))

                peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DROP_ENTITY")
            else:
                peer_confirmation = confirmation
            if peer_confirmation is not None:
                body["confirmation"] = peer_confirmation
        if dry_run:
            body["dry_run"] = True
        if plan is not None:
            body["plan"] = plan
        if budget:
            body["budget"] = dict(budget)
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        result = self._send("POST", self._schema_path(), session, json_body=body)
        return {
            "revision": str(result.get("revision")) if result.get("revision") is not None else None,
            "descriptor": result.get("descriptor"),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

    # port v1.10 (same WP as above).
    def add_field_with_declared_type(self, session: object, entity: str, field: str, field_type: str) -> None:
        assert isinstance(session, _Session)
        self._send(
            "POST", self._schema_path(), session,
            json_body={"operation": "add_field", "entity": entity, "field": field, "field_type": field_type},
        )

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
        session: object = None,
        entity: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"operation": operation}
        if values is not None:
            item["values"] = dict(values)
        if where_field is not None:
            item["where"] = [{"field": where_field, "operator": "eq", "value": where_value}]
        if destructive:
            # `destructive` is only ever meaningful when true (bind_
            # mutation's own default is false), so it is only set here
            # rather than always present.
            item["destructive"] = True
        # port v1.6 declare-and-echo (WP-3, C-06 V2b-wire -- mirrors
        # conformance_adapter_r2db.py's identical fix and its identical
        # rationale comment): `confirmation` is set whenever the caller
        # supplies one, INDEPENDENT of `destructive`, so a request whose
        # wire OMITS `destructive` entirely (not merely `false`) can still
        # carry a real, currently-valid `confirmation` phrase for the
        # identical request. `session`/`entity` are only required when
        # `confirmation is VALID_CONFIRMATION`.
        if confirmation is not None:
            if confirmation is VALID_CONFIRMATION:
                assert session is not None and entity is not None, (
                    "_build_mutation_item: VALID_CONFIRMATION requires session/entity to build its probe"
                )
                probe_item = dict(item)
                probe_item["destructive"] = True

                def probe(_session=session, _entity=entity, _probe_item=probe_item) -> None:
                    self._mutate_request(_session, _entity, [dict(_probe_item)])

                peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
            else:
                peer_confirmation = confirmation
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

    def attempt_mutation_with_result(
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
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        transaction: str | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        # port v1.13 (design D-4/D-6): `dry_run`/`plan`/`budget` are
        # MutationRequest top-level fields -- carried through `_mutate_
        # request`'s own `extra_body`, the same real mechanism `attempt_
        # batch_with_addresses` already uses for `idempotency_key`. port
        # v1.13 追補: `destructive`/`confirmation` are carried through
        # `_build_mutation_item` exactly as `attempt_batch_with_result`
        # already carries `BatchOperation.destructive`/`.confirmation` --
        # the SAME `VALID_CONFIRMATION` declare-and-echo protocol `delete`
        # above uses, needed for C-22's `_confirm_probe`. port v1.13 追補 2
        # (C-22 leg (10)): `transaction` is `MutationRequest`'s own PRE-
        # EXISTING top-level key -- carried through `extra_body` the same
        # way, defaulting to `None` (omitted, `http.py::post_mutate`'s own
        # `body.get("transaction", "atomic")` default then applies exactly
        # as every pre-addendum caller already gets). WP-1 addendum (C-25
        # (4)): `idempotency_key` is a `MutationRequest` top-level field on
        # this peer too (`additionalProperties: false` on the per-
        # operation `Mutation` shape has no slot for it) -- carried through
        # `extra_body` the same way `attempt_batch_with_addresses` already
        # does with its own folded value, never per-item.
        assert isinstance(session, _Session)
        item = self._build_mutation_item(
            operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
            destructive=destructive, confirmation=confirmation, session=session, entity=entity,
        )
        extra_body: dict[str, Any] = {}
        if dry_run:
            extra_body["dry_run"] = True
        if plan is not None:
            extra_body["plan"] = plan
        if budget:
            extra_body["budget"] = dict(budget)
        if transaction is not None:
            extra_body["transaction"] = transaction
        if idempotency_key is not None:
            extra_body["idempotency_key"] = idempotency_key
        result = self._mutate_request(session, entity, [item], extra_body=extra_body or None)
        return {
            "affected": result["affected"],
            "assigned_addresses": result.get("assigned_addresses"),
            "committed": result.get("committed", not dry_run),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

    def attempt_batch_with_addresses(
        self, session: object, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        assert isinstance(session, _Session)
        items = [
            self._build_mutation_item(
                op.operation, values=op.values, where_field=op.where_field, where_value=op.where_value,
                expected_revision=op.expected_revision, unique_key=op.unique_key,
                destructive=op.destructive, confirmation=op.confirmation,
                session=session, entity=entity,
            )
            for op in operations
        ]
        # port v1.11 (design D-6.7 C-07 (ii)): the contract's own
        # `idempotency_key` is a REQUEST-level field
        # (`MutationRequest.idempotency_key`, `additionalProperties:
        # false` on the per-operation `Mutation` shape has no slot for
        # it) -- never placed inside an individual operation item. port
        # v1.13 (design §6.1 item (v)): folded through the shared
        # `fold_batch_idempotency_key`, exactly like `attempt_batch_with_
        # result` below -- never an unguarded `next(...)` over each op's
        # own value, which would silently pick "whichever op happens
        # first" on a genuine mix instead of enforcing the uniform-or-
        # absent rule that function exists for.
        idempotency_key = fold_batch_idempotency_key(operations)
        # Same real HTTP mutation endpoint as `attempt_mutation_with_
        # addresses` above, given every operation in one request body --
        # exactly what a real client sending a multi-operation atomic batch
        # over HTTP would do.
        result = self._mutate_request(
            session, entity, items,
            extra_body={"idempotency_key": idempotency_key} if idempotency_key is not None else None,
        )
        return result["affected"], result.get("assigned_addresses")

    def attempt_batch_with_result(
        self,
        session: object,
        entity: str,
        operations: Sequence[BatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        # port v1.13: `attempt_batch_with_addresses`'s exact request shape,
        # extended with the same request-level `dry_run`/`plan`/`budget`/
        # (folded) `idempotency_key` machinery `attempt_mutation_with_
        # result`/`attempt_batch_with_addresses` already establish.
        assert isinstance(session, _Session)
        items = [
            self._build_mutation_item(
                op.operation, values=op.values, where_field=op.where_field, where_value=op.where_value,
                expected_revision=op.expected_revision, unique_key=op.unique_key,
                destructive=op.destructive, confirmation=op.confirmation,
                session=session, entity=entity,
            )
            for op in operations
        ]
        idempotency_key = fold_batch_idempotency_key(operations)
        extra_body: dict[str, Any] = {}
        if idempotency_key is not None:
            extra_body["idempotency_key"] = idempotency_key
        if dry_run:
            extra_body["dry_run"] = True
        if plan is not None:
            extra_body["plan"] = plan
        if budget:
            extra_body["budget"] = dict(budget)
        result = self._mutate_request(session, entity, items, extra_body=extra_body or None)
        return {
            "affected": result["affected"],
            "assigned_addresses": result.get("assigned_addresses"),
            "committed": result.get("committed", not dry_run),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

    def attempt_cross_entity_batch(self, session: object, operations: Sequence[ScopedBatchOperation]) -> int:
        # P35 WP-3 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_
        # 130_V1.md section 3, M-5): unlike the in-process plug's
        # `SurfaceAbsent` claim, `POST /v1/data/mutations` IS a real,
        # mounted route on this composition (`http.py`'s own
        # `post_cross_entity_mutate`, R-3's stub) -- it genuinely
        # authenticates the request and then uniformly refuses with
        # `CAPABILITY_UNSUPPORTED` via `service.deny_unsupported(...)`,
        # never a 404/405 that would look like the route does not exist at
        # all. This is therefore a present-denial claim, not a structural
        # absence: the real request is built and sent exactly as a genuine
        # client attempting a cross-entity batch would (each operation
        # carrying its OWN `entity` field, per `ScopedMutation`'s own
        # shape, distinct from the per-entity endpoint's URL-scoped body),
        # and whatever the peer's real denial is is let propagate
        # unmodified -- never fabricated by this adapter.
        assert isinstance(session, _Session)
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"operation": op.operation, "entity": op.entity}
            if op.values is not None:
                item["values"] = dict(op.values)
            if op.where_field is not None:
                item["where"] = [{"field": op.where_field, "operator": "eq", "value": op.where_value}]
            if op.destructive:
                item["destructive"] = True
            if op.confirmation is not None:
                # No real per-request confirmation phrase exists to declare-
                # and-echo against on this peer (the stub never executes
                # anything) -- a caller supplying VALID_CONFIRMATION here
                # would have no real probe to resolve it against, so this
                # adapter passes through only a literal string. Every
                # currently-registered caller of this method against THIS
                # adapter (C-16 V5) never exercises a destructive delete
                # against it, since the whole capability is unavailable.
                item["confirmation"] = (
                    op.confirmation if op.confirmation is not VALID_CONFIRMATION else "DELETE"
                )
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            items.append(item)
        # port v1.11 (design D-6.7 C-07 (ii)): `idempotency_key` is a
        # REQUEST-level field on `ScopedMutationRequest`
        # (`additionalProperties: false` on the per-operation
        # `ScopedMutation` shape has no slot for it). port v1.13 (design
        # §6.1 item (v)): folded through the shared `fold_batch_
        # idempotency_key`, exactly like `attempt_cross_entity_batch_
        # with_result` below -- same fold, not an unguarded `next(...)`.
        idempotency_key = fold_batch_idempotency_key(operations)
        body: dict[str, Any] = {"operations": items}
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        result = self._send("POST", "/v1/data/mutations", session, json_body=body)
        return result["affected"]

    def attempt_cross_entity_batch_with_result(
        self,
        session: object,
        operations: Sequence[ScopedBatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        # port v1.13: `attempt_cross_entity_batch`'s exact request shape
        # (same real `POST /v1/data/mutations` route, same present-denial
        # reasoning -- this peer's `cross_entity_mutation` stays
        # `unavailable`, P35-D1, so every call here observes CAPABILITY_
        # UNSUPPORTED regardless of the new fields), extended with the
        # same request-level `dry_run`/`plan`/`budget`/(folded)
        # `idempotency_key` machinery `attempt_batch_with_result` uses.
        assert isinstance(session, _Session)
        items: list[dict[str, Any]] = []
        for op in operations:
            item: dict[str, Any] = {"operation": op.operation, "entity": op.entity}
            if op.values is not None:
                item["values"] = dict(op.values)
            if op.where_field is not None:
                item["where"] = [{"field": op.where_field, "operator": "eq", "value": op.where_value}]
            if op.destructive:
                item["destructive"] = True
            if op.confirmation is not None:
                item["confirmation"] = (
                    op.confirmation if op.confirmation is not VALID_CONFIRMATION else "DELETE"
                )
            if op.expected_revision is not None:
                item["expected_revision"] = op.expected_revision
            if op.unique_key is not None:
                item["unique_key"] = op.unique_key
            items.append(item)
        idempotency_key = fold_batch_idempotency_key(operations)
        body: dict[str, Any] = {"operations": items}
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if dry_run:
            body["dry_run"] = True
        if plan is not None:
            body["plan"] = plan
        if budget:
            body["budget"] = dict(budget)
        result = self._send("POST", "/v1/data/mutations", session, json_body=body)
        return {
            "affected": result["affected"],
            "committed": result.get("committed", not dry_run),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

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

    def drop_entity(self, session: object, entity: str, *, destructive: bool, confirmation: str | None) -> None:
        assert isinstance(session, _Session)
        # port v1.6 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6
        # item 3): the HTTP-boundary twin of conformance_adapter_r2db.py's
        # `drop_entity` -- same real, single schema-operations endpoint,
        # same VALID_CONFIRMATION sentinel protocol as `delete()` above.
        def probe() -> None:
            self._send(
                "POST", self._schema_path(), session,
                json_body={"operation": "drop_entity", "entity": entity, "destructive": True},
            )

        peer_confirmation = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DROP_ENTITY")
        body: dict[str, Any] = {"operation": "drop_entity", "entity": entity, "destructive": destructive}
        if peer_confirmation is not None:
            body["confirmation"] = peer_confirmation
        self._send("POST", self._schema_path(), session, json_body=body)

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

    def query_with_budget(
        self,
        session: object,
        entity: str,
        select: Sequence[str],
        field: str | None,
        value: Any,
        *,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        # port v1.13 (design D-6, §6.1 item 3): `budget` is a QueryRequest
        # top-level field, carried through `_query_request`'s own
        # `extra_body` exactly as `query_with_revisions` above carries
        # `select`/`where`. `request_id` is observed off the real response
        # the same way `revisions` already is.
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        extra_body = {"budget": dict(budget)} if budget else None
        result = self._query_request(session, entity, select=list(select), where=where, extra_body=extra_body)
        return {
            "items": result["items"],
            "revisions": result.get("revisions"),
            "request_id": result.get("request_id"),
        }

    def attempt_filter_with_result(
        self,
        session: object,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[Mapping[str, Any]] | None = None,
        page_size: int | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """port v1.16 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        §7 段 (9)): `attempt_filter`'s own `where` construction, presented
        to `_query_request` (`:1672`) together with that SAME helper's
        pre-existing `page_size` keyword and its `extra_body` merge -- the
        latter carries `order_by` (`_query_request` has no dedicated
        keyword for it) and `budget` onto the real wire body's top level,
        exactly as `query_with_budget` above already carries `budget`
        alone the same way."""
        assert isinstance(session, _Session)
        where: list[dict[str, Any]] = [{"field": field, "operator": operator, "value": value}]
        if extra_predicates:
            where.extend({"field": f, "operator": o, "value": v} for f, o, v in extra_predicates)
        extra: dict[str, Any] = {}
        if order_by:
            extra["order_by"] = list(order_by)
        if budget:
            extra["budget"] = dict(budget)
        result = self._query_request(
            session, entity, select=list(select), where=where, page_size=page_size,
            extra_body=extra or None,
        )
        return {"items": result["items"], "request_id": result.get("request_id")}

    def operation_catalog_document(self, session) -> bytes:
        """port v1.17 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        D-5, §7.1 item 2): a real `GET /v1/operation-catalog` over this
        adapter's own transport (`_build_client`'s ASGI transport by
        default; a real socket for the socket adapter, WP-4) -- unlike
        `_send`, this reads `response.content` (raw bytes) rather than
        `.json()`, so C-29's own byte-for-byte comparison has no re-
        encoding step of this adapter's own to drift from."""
        assert isinstance(session, _Session)
        header_pairs = [("authorization", f"Bearer {session.secret}")]
        request = self._client.build_request("GET", "/v1/operation-catalog", headers=header_pairs)
        response = self._run(self._client.send(request))
        if response.status_code >= 400:
            failure = _HttpFailure(response)
            raise ConformanceDenial(
                code=self.classify(failure), adapter=self.name, native_type=type(failure).__name__,
                details=_failure_details(failure),
            ) from failure
        return response.content

    def query_page(
        self,
        session: object,
        entity: str,
        select: Sequence[str],
        *,
        where: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[tuple[str, str]] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> tuple[list[dict], str | None]:
        """port v1.18 (design D-4, C-30): presents the wire body's own
        `where`/`order_by`/`page.size`/`page.cursor`/`budget` fields
        through `_query_request`'s own real `POST .../query` entry point,
        verbatim -- `cursor` maps onto that method's own pre-existing
        keyword (`:1680`, added for `count()`'s own `next_page`-following
        fallback), `order_by` onto the keyword this WP added immediately
        above."""
        assert isinstance(session, _Session)
        where_body = [{"field": f, "operator": op, "value": v} for f, op, v in where] if where else None
        order_body = [{"field": f, "direction": d} for f, d in order_by] if order_by else None
        extra_body = {"budget": dict(budget)} if budget else None
        result = self._query_request(
            session, entity, select=list(select), where=where_body, order_by=order_body,
            page_size=page_size, cursor=cursor, extra_body=extra_body,
        )
        return result["items"], result.get("next_page")

    # ------------------------------------------------------------------
    # WP-1 (contract 1.2.0, docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-1,
    # subordinate ruling 7(A) reverse-validation) -- thin, NON-normative raw
    # response accessors.
    #
    # These are deliberately NOT part of the abstract `ConformanceAdapter`
    # port: extending that frozen surface is a coordinated design revision
    # (R-6/port v1.6, a later work package), not this one. Every method
    # above this block already goes through `_send`/`_query_request`/
    # `_mutate_request`/`_control_send` and then unwraps or normalizes the
    # real response for the port's own typed return shape (an `int`, a
    # `(items, revisions)` tuple, an unwrapped envelope row-sequence, ...).
    # That normalization is exactly what a reverse schema-conformance check
    # (`conformance-tests/test_c11_response_schema_conformance.py`'s new
    # response-schema tests) must NOT go through: it needs the real,
    # unmodified JSON body the peer's own HTTP handler produced, to check it
    # against the contract's now-closed response schemas
    # (`additionalProperties: false`). Each method below calls the exact
    # same private transport helper the corresponding normalized port method
    # already uses, and returns its body untouched -- no new HTTP surface,
    # no behavior change, pure observation. A future adapter (this one or a
    # peer's) may optionally grow the same method names; the reverse-
    # validation test duck-types their presence via `getattr(...)` rather
    # than requiring them.
    def raw_query_result(
        self, session: object, entity: str, select: Sequence[str], where: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._query_request(session, entity, select=list(select), where=where)

    def raw_mutation_result(
        self, session: object, entity: str, operations: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._mutate_request(session, entity, [dict(op) for op in operations])

    def raw_schema_operation_result(self, session: object, body: Mapping[str, Any]) -> dict[str, Any]:
        assert isinstance(session, _Session)
        return self._send("POST", self._schema_path(), session, json_body=dict(body))

    def raw_list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> dict[str, Any]:
        return self._control_send("GET", "/control/v1/applications", actor)

    def raw_issue_credential(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> dict[str, Any]:
        return self._control_send(
            "POST", "/control/v1/credentials", actor, json_body={"application_id": application_id, "role": role},
        )

    def raw_list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> dict[str, Any]:
        return self._control_send("GET", "/control/v1/credentials", actor)

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
            # `structured.py`'s `bind_mutation` (now in `mutation_binding.py`) enforces the equivalent
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
        # `work` is a required keyword-only argument on `set_state` (CCR-14
        # WP-2 round-2 review, ruling (A)) -- each attempt below opens its
        # own `unit_of_work()` and passes the handle through. This must
        # keep raising a `FoundationError` (never a bare `TypeError`) for
        # `_control_call` to convert into a `ConformanceDenial` as before:
        # `unit_of_work()`'s own `except BaseException: ... raise` re-raises
        # `set_state`'s `FoundationError` unchanged through the `with`
        # block, so `_control_call`'s `except FoundationError` still catches
        # it exactly as it did when `set_state` raised directly.
        def revoked_false_attempt() -> None:
            def _attempt() -> None:
                with self._write_credentials.unit_of_work() as work:
                    self._write_credentials.set_state(handle.credential_ref, revoked=False, work=work)

            self._control_call(_attempt)

        def enabled_true_attempt() -> None:
            def _attempt() -> None:
                with self._write_credentials.unit_of_work() as work:
                    self._write_credentials.set_state(handle.credential_ref, enabled=True, work=work)

            self._control_call(_attempt)

        # CCR-14 WP-5 (design §4/§8 M-3): `/control/v1`'s own in-band
        # enable/rotate -- see `conformance_adapter_r2db.py`'s identical
        # addition/rationale (this is the real-HTTP twin). WP-5 round-2
        # review NIT-1: every vector below fetches its own control actor
        # LAZILY, inside its own `attempt()` -- never captured eagerly at
        # vector-construction time -- so a later vector in this same list
        # revoking/resetting the tracked control credential (the control-
        # credential-targeting vector does exactly that) can never leave an
        # earlier-constructed-but-not-yet-attempted vector holding a stale
        # actor if a future change reorders this list.
        def inband_enable_attempt() -> None:
            actor = self.control_credential()
            self._control_send("POST", f"/control/v1/credentials/{quote(handle.credential_ref, safe='')}/enable", actor)

        def inband_rotate_attempt() -> None:
            actor = self.control_credential()
            self._control_send("POST", f"/control/v1/credentials/{quote(handle.credential_ref, safe='')}/rotate", actor)

        # WP-5 round-2 review MINOR-7 (observed denial code): because actor
        # and target are the SAME now-revoked credential, the real HTTP
        # `rotate` call's own authentication step denies this with
        # `AUTH_REVOKED` -- never reaching the rotate handler's own "revoked
        # target" `VALIDATION_FAILED` refusal, since the caller itself never
        # authenticates in the first place. This vector's real detection
        # power is therefore "a revoked control credential can no longer
        # authenticate at all", not the target-revocation check the sibling
        # application-credential vector (`inband_rotate_attempt`, above)
        # exercises with a still-live, distinct actor.
        def inband_rotate_revoked_control_credential_attempt() -> None:
            actor = self.control_credential()
            # port v1.6 declare-and-echo (WP-3, design docs/design/
            # DESTRUCTIVE_CONFIRMATION_V1.md R-3): revoking the sole live
            # control credential now requires a valid confirmation -- this
            # is a SETUP step of this vector, not its own assertion target
            # (the real target is the `rotate` call below, against a
            # now-genuinely-revoked control credential), so it probes ->
            # echoes the real phrase to actually complete the revoke,
            # exactly as a real client would, rather than assuming an
            # unconfirmed revoke still succeeds the way it did before this
            # WP.
            revoke_path = f"/control/v1/credentials/{quote(actor.credential_ref, safe='')}/revoke"
            try:
                self._control_send("POST", revoke_path, actor, json_body={"destructive": True})
            except ConformanceDenial as denial:
                # Opus review minor m-4: only the gate's own denial code is
                # a probe to echo past -- any OTHER denial must propagate.
                if denial.code != "DESTRUCTIVE_CONFIRMATION_REQUIRED":
                    raise
                phrase = denial.details["required_confirmation"]
                revoked = self._control_send("POST", revoke_path, actor, json_body={"destructive": True, "confirmation": phrase})
                assert revoked.get("revoked") is True, f"echoing the real phrase did not actually revoke the credential: {revoked!r}"
            self._control_send("POST", f"/control/v1/credentials/{quote(actor.credential_ref, safe='')}/rotate", actor)

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
            TamperVector(
                kind="credential_reactivation",
                name="r2db_http_inband_enable_revoked_application_credential",
                disposition="must_ignore",
                attempt=inband_enable_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_http_inband_rotate_revoked_application_credential",
                disposition="must_deny",
                attempt=inband_rotate_attempt,
            ),
            TamperVector(
                kind="credential_reactivation",
                name="r2db_http_inband_rotate_revoked_control_credential",
                disposition="must_deny",
                attempt=inband_rotate_revoked_control_credential_attempt,
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

    # port v1.11 (design D-6.6 (e)): non-normative, duck-typed accessor
    # (mirrors the existing "optional raw-accessor methods" convention
    # below, e.g. `_find_all_adapters_with`) -- counts REAL PostgreSQL
    # backends, used only by C-05's own (e) resource-release check
    # (`test_c05_limit_declaration_agreement.py`), never by any other
    # condition test. WP-4 rework (完了条件 15 / F1 差し戻し 2 巡目): a bare
    # `f"{prefix}%"` pattern ALSO matched the shared PLATFORM database
    # (`<prefix>_platform`), where the shared control stack's own lazily-
    # opened connections live -- counting those made the (e) assertion
    # depend on whether an earlier test in the same worker process had
    # already warmed that shared pool (a cold process measured `after !=
    # before` even with no leak at all; a warm one did not). The caller
    # now supplies a pattern scoped to ONLY the per-application database(s)
    # the isolated instance itself provisioned (`<prefix>_app_<application_
    # id>`, `_provision_pg_app`'s own naming, never the bare prefix), so
    # this accessor never sees the shared control pool's own connections.
    def _live_pg_backend_count(self, datname_like: str) -> int:
        with psycopg.connect(self._platform.admin_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname LIKE %s",
                    (datname_like,),
                )
                return cur.fetchone()[0]

    def pool_stats(self) -> dict[str, dict[str, int | float]]:
        """R-78 (D-2): `default_pool_manager.stats()` -- every cell this
        adapter's own `_make_cell` builds shares that same process-wide
        `SharedPoolManager` (it never passes its own `pool_manager`), so
        this reflects every one of this adapter's own role pools, keyed by
        `"<application_id>/<role>"` (`SharedPoolManager.stats()`'s own
        docstring)."""
        return default_pool_manager.stats()

    def prepared_stats(self) -> list[dict]:
        """R-79 (WO §1.2 D-2/D-3): the data-plane counterpart of `pool_
        stats()` immediately above -- same process-wide `SharedPoolManager`
        this adapter's own cells all share, so this is every idle
        connection currently sitting in any of this adapter's own role
        pools, probed for `pg_prepared_statements` content
        (`SharedPoolManager.prepared_stats()`'s own docstring)."""
        return default_pool_manager.prepared_stats()

    def perf_thread_limit(self) -> int:
        """The effective `thread_limit` the data-plane app's own
        `create_app` call was built with: the resolved `DSA_PERF_THREAD_
        LIMIT` value when the env names a positive integer, `DEFAULT_
        THREAD_LIMIT` otherwise (absent, empty, or not a positive
        integer)."""
        return self._perf_thread_limit

    def platform_db_time_stats(self) -> dict[str, int | float]:
        """Sums `self._credentials`/`self._application_durable_audit`'s
        own `_RolePool.platform_stats()` -- the two platform-side pools
        the data-plane measurement path actually uses (`self._write_
        credentials` is provisioning-only, never touched by a measured
        request). Read-only: neither pool's `_acquire()` runs, so `_RolePool.
        stats()`'s own `acquire_count` for either pool is untouched by
        calling this."""
        credentials_stats = self._credentials._pool.platform_stats()  # noqa: SLF001 -- read-only accessor, same discipline as pool_stats() above
        audit_stats = self._application_durable_audit._pool.platform_stats()  # noqa: SLF001
        return {
            "sessions": credentials_stats["sessions"] + audit_stats["sessions"],
            "connect_wall_ms": credentials_stats["connect_wall_ms"] + audit_stats["connect_wall_ms"],
            "db_wall_ms": credentials_stats["db_wall_ms"] + audit_stats["db_wall_ms"],
            "txn_count": credentials_stats["txn_count"] + audit_stats["txn_count"],
            "db_calls": credentials_stats["db_calls"] + audit_stats["db_calls"],
        }

    def close(self) -> None:
        try:
            self._run(self._client.aclose())
            self._run(self._control_client.aclose())
        finally:
            for cell in self._provisioned_cells:
                cell.close()
            self._credentials.close()
            self._write_credentials.close()
            self._application_durable_audit.close()
            for store in self._control_stores:
                if store is not None:  # WP-2(b) fix round 2, m-7 -- see `_privileged_control_send`'s identical guard
                    store.close()
            self._control_audit_reader.close()
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
