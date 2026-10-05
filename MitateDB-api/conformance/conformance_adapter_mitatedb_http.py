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
import asyncio
import copy
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
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
    ENUM_CLEAR,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    AdmissionHold,
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
    fold_batch_idempotency_key,
    fresh_identifier,
    resolve_valid_confirmation,
)
from adapter import _EnumClear  # noqa: E402  -- type-hint only, mirrors ConformanceAdapter's own signature

from mitatedb_api.application_audit import PostgresApplicationAuditSink  # noqa: E402
from mitatedb_api.audit_dispatch import AuditRouter  # noqa: E402
from mitatedb_api.auth import Role  # noqa: E402
from mitatedb_api.backend_postgres import PostgresBackend  # noqa: E402
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, _LimitStateHolder  # noqa: E402
from mitatedb_api.concurrency_slots import HostSharedConcurrencySlots  # noqa: E402
from mitatedb_api.config import FoundationConfig, role_pool_size  # noqa: E402
from mitatedb_api.control_audit import read_control_audit_events  # noqa: E402
from mitatedb_api.control_composition import build_control_service  # noqa: E402
from mitatedb_api.control_http import create_control_app  # noqa: E402
from mitatedb_api.credential_store_postgres import PostgresCredentialStore  # noqa: E402
from mitatedb_api.errors import AuthorizationStateUnavailable  # noqa: E402
from mitatedb_api.http import DEFAULT_THREAD_LIMIT, PROBLEM_CONTENT_TYPE, HttpService, create_app  # noqa: E402
from mitatedb_api.pool import BoundedConnectionPool  # noqa: E402

BASE_URL = "http://mitatedb-http-pg.conformance.invalid"

# Phase 6 WP-3 (design D-2): the `surfaces` this plug declares -- built
# from the SAME `BASE_URL` its own `self._client`/`self._control_client`
# are constructed against (`versioning.base_path`/`control_base_path`
# suffixed on), never a second, independently-chosen pair of strings.
_DATA_SURFACE_BASE_URL = BASE_URL + "/v1"
_CONTROL_SURFACE_BASE_URL = BASE_URL + "/control/v1"

# Phase 10 WP-6 isomorphism pass: same shape as r2db-api's own
# `conformance_adapter_r2db_http.py::_SURFACES` module constant (built
# from the two base URLs directly above, never a second, independently-
# chosen pair of strings) -- `_surfaces_value` below returns this
# constant directly rather than constructing the dict inline, so its own
# body is byte-identical to the sibling's after `_ISOMORPHIC_TARGETS`
# normalization (`tests/test_audit_query.py`), not merely equal in value.
_SURFACES = {
    "data": {"base_url": _DATA_SURFACE_BASE_URL},
    "control": {"base_url": _CONTROL_SURFACE_BASE_URL},
}

# Phase 11 WP-3 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-5):
# this HTTP (ASGI-transport) plug's own declared `operation_catalog_url` --
# same synthetic, non-dialable convention as `_SURFACES` immediately above
# (C-29's stage (i) never dials this string on an `"asgi"` plug; it calls
# `operation_catalog_document()`, which goes through this SAME running
# app's own real handler over the ASGI transport). The socket adapter
# (WP-4) overrides `_operation_catalog_url_value` below to report a real,
# dialable URL instead.
_OPERATION_CATALOG_URL = _DATA_SURFACE_BASE_URL + "/operation-catalog"

# port v1.11 addendum (supervisor ruling 2026-09-06 item 1): `isolated_
# control_surface(limits_override=...)`'s only way to inject a small
# control-plane limits profile on this plug -- unlike the in-process plug
# and r2db-api's own HTTP plug (both of which construct a real
# `ControlPlaneLimits` object directly and can `dataclasses.replace` it),
# this peer's `build_control_service` (`mitatedb_api.control_composition`)
# derives `ControlPlaneLimits` from environment variable NAMES, read from
# its own `env` argument -- never from a `limits=` parameter (it has none).
# This maps the 3 `ControlPlaneLimits` field names `apply_limits_override`
# (the shared, type-agnostic helper) is ever asked to override to the exact
# env var name `build_control_service`'s own docstring documents for it.
_CONTROL_LIMIT_ENV_NAMES: Mapping[str, str] = {
    "applications": "MITATEDB_CONTROL_APPLICATIONS_LIMIT",
    "credentials_per_application": "MITATEDB_CONTROL_CREDENTIALS_PER_APPLICATION_LIMIT",
    "control_requests_per_minute": "MITATEDB_CONTROL_REQUESTS_PER_MINUTE_LIMIT",
}

# R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-1): this
# adapter's own declared writer-connection timeouts for the conformance
# deployment -- NOT migration `0007_platform_declarations.sql`'s shipped
# 5000ms/5000ms default. `_bootstrap_platform` issues `ALTER ROLE ... SET`
# for both values, on both service writer roles, over its own admin
# connection right after `0007` runs (same SQL shape as `tests/control_
# plane_harness.py::set_role_timeouts`), so the peer's composition root
# still derives `visibility_lag_ms` from the catalog unchanged -- only the
# seeded numbers differ. The platform DB unit_of_work here is a handful of
# ms-scale statements with no subprocess/external wait between them, so a
# much smaller pair is sufficient for this deployment; see design D-1 for
# the measurement that backs these two values.
CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS = 1000
CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS = 2000

# The exact set of denial codes that mean "the cached control credential is
# genuinely no longer live" (an authority refusal), as opposed to a
# transient/unrelated denial (`LIMIT_EXCEEDED`, `AUTH_STATE_UNAVAILABLE`,
# ...) that must never trigger a destructive `ops.py reset` -- see
# `control_credential`/`_privileged_control_send`'s own call sites, both of
# which share this one set rather than each hand-rolling their own copy.
_REPAIRABLE_AUTH_DENIAL_CODES = frozenset({"AUTH_INVALID", "AUTH_REVOKED", "AUTH_REQUIRED", "FORBIDDEN"})

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

_SCHEMA_REVISION_TABLE = "_mdb_schema_revision"
# Phase 6 WP-3 (design D-3): the declared-type registry table itself --
# `backend_postgres._FIELD_TYPES_TABLE`'s own identical name, kept as a
# separate literal here rather than importing that module-private
# constant (this file already has its own, deliberately independent copy
# of `_SCHEMA_REVISION_TABLE` above, for the same reason -- an adapter
# does not reach into a peer's own module internals for a bookkeeping
# name it needs to exclude from its own privileged reach-around).
_FIELD_TYPES_TABLE = "_mdb_field_types"
# Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(a)/(e)(i),
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
# WP-4 変更対象 C): the per-application platform-upgrade ledger -- a
# THIRD bookkeeping table this adapter's own `entities()` reach-around
# must exclude, same reasoning as the two above (independent literal
# copy, never importing `backend_postgres`'s/`platform_upgrades`'s own
# module-private constant). Discovered by this WP's own conformance run:
# without this exclusion, `test_c01_scope_binding.py`'s `entities()`-
# driven snapshot treats the ledger table as if it were a real,
# client-created entity and attempts to `POST /v1/data/_mdb_platform_
# upgrades/query` against it -- which `VALIDATION_FAILED`s (the reserved
# leading-underscore prefix, `identifiers._IDENTIFIER`), not because of a
# scope-binding defect.
_PLATFORM_UPGRADES_TABLE = "_mdb_platform_upgrades"

# port's own two-member field-type vocabulary (`adapter.COMMON_FIELD_TYPES`)
# -> this peer's real `SchemaOperationRequest.field_type` wire enum member
# (mirrors r2db-http's own `_PORT_FIELD_TYPE_TO_R2DB` table, independently
# defined here for this peer's own wire vocabulary).
_PORT_FIELD_TYPE_TO_WIRE = {"text": "string", "integer": "integer"}


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


def _bootstrap_platform(
    prefix: str, admin_dsn: str, script_dir: Path, surfaces: Mapping[str, Any],
) -> _Platform:
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
        # Phase 10 WP-4f (supervisor ruling 2026-09-09; peer-symmetric with
        # r2db-api's own `0013_role_connection_limits.sql`): raises
        # `<prefix>svc_api`/`<prefix>svc_controlplane`'s own `CONNECTION
        # LIMIT` to match their real pool composition -- the same
        # production migration a real deployment would apply (the
        # ruling's own constraint: "throwaway platform は本番 migration
        # をそのまま適用する -- adapter 専用に limit を上げない"). Depends
        # only on 0002/0005 above, so it is applied here BEFORE the
        # declarations-table migrations below (order-independent either
        # way, mirroring r2db-api's own adapter).
        "0012_role_connection_limits.sql",
        # Sets a role-level `statement_timeout` on `mitatedbsvc_
        # auditreader` and every application's own runtime/developer role
        # -- depends only on 0005/0012 above, applied here right after
        # 0012 (order-independent relative to the declarations-table
        # migrations below).
        "0013_role_statement_timeouts.sql",
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
        # Phase 10 WP-6b (design D-5 (ii)): widens `platform_declarations.
        # key`'s own CHECK constraint to accept `process_ceilings` --
        # without this migration applied + the row seeded below, BOTH
        # `main.build_app` and `build_control_service` fail F-15 at
        # construction time (design's own "宣言表を通る全経路で、宣言を
        # 先に書く").
        "0011_process_ceilings.sql",
        # design D-3 (1): the credential-keyed `requests_per_minute` rate
        # table -- depends only on 0002 above (`credentials`), so it is
        # applied right after 0002/0005 below, independent of the
        # declarations-table migrations.
        "0016_credential_request_rate.sql",
        # the refusal-window counter and its function -- depends on 0005
        # below (`application_audit`, the `auditreader` role), which this
        # adapter's data plane writes every refusal count through.
        "0017_denial_window_counter.sql",
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
    _run_psql(provision_dsn, rewritten["0016_credential_request_rate.sql"])
    _run_psql(provision_dsn, rewritten["0017_denial_window_counter.sql"])
    # Phase 10 WP-4f: unconditional, like 0002/0005 above -- depends only
    # on those two, so it always runs here regardless of the declarations-
    # table migrations below.
    _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
    _run_psql(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])
    # Q4 phase: platform declarations + writer-role timeouts -- only
    # depends on 0002's two roles, run here (before the password-ALTER
    # block below, order-independent either way).
    _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
    # R-105 (design D-1): overwrite 0007's shipped 5000ms/5000ms role
    # settings with this plug's own conformance-deployment values, on
    # BOTH service writer roles 0007 just seeded into `audit_writer_
    # roles` -- the SAME `ALTER ROLE ... SET` shape `tests/control_plane_
    # harness.py::set_role_timeouts`/`ops set-platform-timeouts` use, over
    # this adapter's own admin connection (autocommit, closed right after
    # -- never kept open). The peer's composition root still derives
    # `visibility_lag_ms` from `pg_db_role_setting` unchanged; only the
    # seeded numbers differ from what 0007 alone would have left in place.
    _admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with _admin.cursor() as _cur:
            for _role in (api_role, controlplane_role):
                _cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                    sql.Identifier(_role), sql.Literal(f"{CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS}ms")))
                _cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = {}").format(
                    sql.Identifier(_role), sql.Literal(f"{CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS}ms")))
    finally:
        _admin.close()
    # Phase 10 WP-6b (design D-5 (ii)): widens the CHECK constraint --
    # takes no psql variables (this migration only alters the key
    # vocabulary; it seeds no row of its own, `process_ceilings` is
    # deployment-specific just like `surfaces`, seeded below instead).
    _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
    # `surfaces` (D-2(c)): BOTH `data`/`control` -- this adapter's own
    # `build_control_service` call requires `control` unconditionally
    # (design §3.7: "control プロセスは自らの control surface を必ず持
    # つ"). port v1.14 (design D-1 (A) 6, WP-3): `surfaces` is now a
    # PARAMETER (the caller's own `_surfaces_value()` hook result) rather
    # than this function reaching for the module-level `_DATA_SURFACE_
    # BASE_URL`/`_CONTROL_SURFACE_BASE_URL` constants directly -- the
    # DEFAULT hook still returns exactly those two constants (byte-for-
    # byte the same JSON this literal string concatenation used to build,
    # now via `json.dumps` on the dict), so this is behavior-preserving;
    # the socket adapter (WP-4) overrides the hook to seed its own real,
    # dialable URLs here instead.
    surfaces_conn = psycopg.connect(provision_dsn, autocommit=True)
    try:
        with surfaces_conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', {value})").format(
                    table=sql.Identifier(schema, "platform_declarations"),
                    value=sql.Literal(json.dumps(surfaces)),
                ),
            )
            # Phase 10 WP-6b (design D-5 (ii)): seeded alongside `surfaces`
            # -- both this HTTP plug's own `build_app`/`build_control_
            # service` calls now require this row (F-15). `{"data": 1,
            # "control": 1}` mirrors this plug's own single-process
            # reality (one `main.build_app`/`build_control_service` call
            # each, in-process, never more than one concurrently-serving
            # process) -- `limit_enforcement` for `concurrency`/`requests_
            # per_minute`/`control_requests_per_minute`/`audit_requests_
            # per_minute` stays `enforced`, unchanged from before this WP.
            # The socket subclass (WP-4b) inherits this seed unchanged.
            cur.execute(
                sql.SQL("INSERT INTO {table} (key, value) VALUES ('process_ceilings', {value})").format(
                    table=sql.Identifier(schema, "platform_declarations"),
                    value=sql.Literal(json.dumps({"data": 1, "control": 1})),
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


class _StalledGateContextManager:
    """port v1.12 `hold_in_flight` plumbing (adapter-internal, never
    port-visible) -- identical shape/rationale to `conformance_adapter_
    mitatedb.py`'s own identical-named class (this peer's own `ApplicationCell.
    _limit_gate` is the correct wrap point on BOTH plugs, not any one
    operation method wholesale, for the identical structural reason that
    file's own docstring states -- see `_hold_in_flight_via_http_requests_
    over_stalled_gate` below)."""

    __slots__ = ("_inner", "_entered", "_release")

    def __init__(self, inner_cm, entered: threading.Semaphore, release: threading.Event) -> None:
        self._inner = inner_cm
        self._entered = entered
        self._release = release

    def __enter__(self):
        value = self._inner.__enter__()
        self._entered.release()
        self._release.wait()
        return value

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)


# Phase 8 WP-1 rework 2 (裁定 3, 監督裁定 2026-09-07): see
# `conformance_adapter_mitatedb.py`'s own identical-named constant for
# the full rationale (a bounded wait for the background threads to
# reach the stalled `_limit_gate`, in place of an unbounded `entered.
# acquire()`, so a stall-point regression fails loud instead of hanging
# the whole test process -- `.github/workflows/ci.yml` has no
# `timeout-minutes` and this repository has no pytest-timeout plugin,
# review finding 3).
_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S = 30.0


@contextmanager
def _hold_in_flight_via_http_requests_over_stalled_gate(
    cell_obj: object, app: Any, bearer: str, path: str, n: int,
    classify: Callable[[BaseException], str], adapter_name: str,
    build_client: Callable[[Any, str], httpx.AsyncClient],
):
    """port v1.12 `hold_in_flight` realization for the HTTP plug
    (adapter-internal plumbing, never port-visible -- design docs/design/
    PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-2 実装の形 (b)). Wraps
    `cell_obj`'s own `_limit_gate` (see `conformance_adapter_mitatedb.py`'s
    own identical-named helper for the full "why the gate, not an
    operation method" rationale -- IDENTICAL on this plug: the real HTTP
    dispatch (`http.py::get_catalog` -> `session.catalog()` ->
    `ApplicationRuntime.catalog()` -> `ApplicationCell.catalog()`) reaches
    the SAME `_limit_gate` call, on the SAME `ApplicationCell` class).
    Each of the `n` held requests is a REAL `GET <path>` HTTP round trip,
    issued from its own OS thread against its OWN fresh event loop + a
    client built through `build_client(app, base_url)` -- the calling
    adapter's own `_build_client` hook (monitor 裁定 2026-09-08, F-10),
    never a direct, hook-bypassing `httpx.AsyncClient(ASGITransport(
    app=app))` construction, so a socket-adapter override of `_build_client`
    (WP-4) reaches `hold_in_flight`'s own held requests too. The shared
    adapter's single `self._loop.run_until_complete` cannot itself hold
    more than one request in flight (D-2's own "HTTP plug の単一loop構造
    との折り合い"), so genuine concurrency needs one loop per held
    request, never the shared one."""
    original_gate = cell_obj._limit_gate  # noqa: SLF001 -- adapter-internal plumbing, same convention this file's own isolated_application_surface() already uses.
    entered = threading.Semaphore(0)
    release = threading.Event()
    errors: list[BaseException] = []

    # `*args, **kwargs`, forwarded verbatim to `original_gate` -- see
    # `conformance_adapter_mitatedb.py`'s own identical-named function.
    # This stall point holds the request AFTER the real gate's own
    # `__enter__` (rate/concurrency/request_bytes/operation_depth already
    # checked) and BEFORE that value reaches the caller, without needing
    # to know `_limit_gate`'s own current keyword signature.
    def _stalled_limit_gate(*args, **kwargs):
        inner = original_gate(*args, **kwargs)
        return _StalledGateContextManager(inner, entered, release)

    cell_obj._limit_gate = _stalled_limit_gate  # noqa: SLF001

    def _run() -> None:
        loop = asyncio.new_event_loop()
        try:
            async def _once() -> None:
                async with build_client(app, BASE_URL) as client:
                    response = await client.get(path, headers=[("authorization", f"Bearer {bearer}")])
                    if response.status_code >= 400:
                        failure = _HttpFailure(response)
                        raise ConformanceDenial(
                            code=classify(failure), adapter=adapter_name, native_type=type(failure).__name__,
                            details=_failure_details(failure),
                        ) from failure

            loop.run_until_complete(_once())
        except BaseException as exc:  # noqa: BLE001 -- collected, never swallowed; re-raised below after every thread is joined and the gate is restored.
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
                f"reached the stalled `_limit_gate` within "
                f"{_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S}s (expected every one of them to "
                "stall inside ApplicationCell._limit_gate's own counter increment, "
                "AFTER the real gate's __enter__ -- see this helper's own "
                "docstring); failing loud instead of hanging (裁定 3, 監督裁定 "
                "2026-09-07)"
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
        cell_obj._limit_gate = original_gate  # noqa: SLF001
    if errors:
        raise errors[0]


# port v1.22 (design docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md D-7 and
# section 6.4): the statement count the three `hold_after_*` handles of this
# HTTP plug return from `statements_after_release()`. It counts the
# statements the Application's own two pools (`_runtime_pool`,
# `_developer_pool`) carried for the held request after the `with` block
# released it:
#
#   per pool: the `execute()` / `executemany()` calls its connections have
#   made (`CountingConnection.execute_count` + `executemany_count`, which a
#   connection that was closed since keeps in the pool's own
#   `_closed_db_calls`), plus the transactions and savepoints its
#   connections have opened (`CountingConnection.txn_open_count`, the enter
#   side of `transaction()` only -- this backend never calls it, its `BEGIN`
#   is the implicit one that goes out with a connection's first statement
#   and is part of that statement's `execute()`).
#
# This backend's pool sends no counted statement on its own account: its
# idle ping goes through `pgconn.exec_` and is not an `execute()`, and a new
# connection issues no `SET`, so nothing is subtracted (the r2db plug's
# `_RolePoolStatementMeter` subtracts the two statements that its pool does
# send).
#
# The figure is taken twice: at the release, and when the caller reads the
# handle. The release-time figure adds the counters of the connection(s) the
# held request still has checked out -- a connection that is checked out is
# in neither the idle queue nor the closed totals, so a request held in the
# middle of its transaction would otherwise have its earlier statements
# counted as later ones. The stalled wrappers below hand over the request
# scope they were given, which carries them (`RequestScope.main` and
# `.developer`). Reading a pool's idle queue takes a snapshot under the
# queue's own mutex and drains nothing, so a request that checks a
# connection out at the same moment is never starved of one. A request that
# was already running on these pools when the hold was released is not
# attributable and is outside what the figure means; the conformance
# vectors that read it run exactly one request.


def _scope_connections(scope: Any) -> list[Any]:
    """The distinct connections a `RequestScope` holds (`main` and
    `developer` are the same object for a schema operation)."""
    conns: list[Any] = []
    for conn in (getattr(scope, "main", None), getattr(scope, "developer", None)):
        if conn is not None and not any(conn is seen for seen in conns):
            conns.append(conn)
    return conns


class _BoundedPoolStatementMeter:
    def __init__(self, cell_obj: object) -> None:
        backend = cell_obj._backend  # noqa: SLF001 -- adapter-internal plumbing, read-only.
        self._pools = (backend._runtime_pool, backend._developer_pool)  # noqa: SLF001
        self._base: int | None = None
        self._base_error: BaseException | None = None

    def _statements(self, held: Sequence[Any] = ()) -> int:
        total = 0
        for pool in self._pools:
            with pool._idle.mutex:  # noqa: SLF001
                idle = list(pool._idle.queue)  # noqa: SLF001
            with pool._stats_lock:  # noqa: SLF001
                total += pool._closed_db_calls  # noqa: SLF001
            for conn in idle:
                total += conn.execute_count + conn.executemany_count + conn.txn_open_count
        for conn in held:
            total += conn.execute_count + conn.executemany_count + conn.txn_open_count
        return total

    def mark_release(self, held: Sequence[Any]) -> None:
        try:
            self._base = self._statements(held)
        except BaseException as exc:  # noqa: BLE001 -- kept and raised by `statements_after_release`, never lost; the release itself must still happen.
            self._base_error = exc

    def statements_after_release(self) -> int:
        if self._base_error is not None:
            raise AssertionError("the statement count could not be taken at the release") from self._base_error
        assert self._base is not None, "statements_after_release was read before the hold was released"
        return self._statements() - self._base


# port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
# WP-6d-ii): `hold_after_idempotency_lookup` realization for this HTTP
# plug -- see `conformance_adapter_mitatedb.py`'s own identical-named
# helper for the full rationale (this peer's own `ApplicationCell._
# idempotency_check` is the single choke both plugs share; only the
# transport differs). This same running process's cell is reached
# in-process here too (`self._cells[app_id]`, same object every real
# `POST` request against this Application dispatches into), so this
# realization needs no HTTP-specific plumbing beyond locating the cell.
# The per-key advisory lock (`pg_advisory_xact_lock`) the held request
# keeps until its transaction ends is what a concurrent second request for
# the same key actually waits on, in this process or another.


@contextmanager
def _hold_after_idempotency_check(cell_obj: object, idempotency_key: str) -> Iterator[IdempotencyHold]:
    original_check = cell_obj._idempotency_check  # noqa: SLF001
    entered = threading.Semaphore(0)
    release = threading.Event()
    held: list[Any] = []
    meter = _BoundedPoolStatementMeter(cell_obj)

    def _checked(key, digest_request, **kwargs):
        result = original_check(key, digest_request, **kwargs)
        replay_response, _digest, _now_ms = result
        if replay_response is None and key == idempotency_key:
            held.extend(_scope_connections(kwargs.get("scope")))
            entered.release()
            release.wait()
        return result

    setattr(cell_obj, "_idempotency_check", _checked)

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_idempotency_lookup: the held request never reached the end of its "
                f"idempotency admission window within {timeout_s}s (expected it to stall right after "
                "_idempotency_check returns a fresh admission -- see this helper's own module comment)"
            )
        return 1

    try:
        yield IdempotencyHold(_wait_until_held, meter.statements_after_release)
    finally:
        try:
            meter.mark_release(held)
        finally:
            release.set()
            setattr(cell_obj, "_idempotency_check", original_check)


# port v1.20 (docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
# section 9's `conformance-tests/` paragraph, Q-5): `hold_after_plan_
# verification` realization for this HTTP plug (the same running
# process's cell, reached the same way `_hold_after_idempotency_check`
# above reaches it). A schema operation
# on `ApplicationCell` (`create_entity` / `add_field` / `alter_field`,
# `cell.py`) that presents a `plan` or `dry_run` reads the Application's
# current revision and checks its `plan` against it in the cell
# (`check_plan_precondition`), and only then calls the backend's
# DDL-carrying method -- `create_collection` / `add_field` /
# `alter_field_constraints` -- which is the first thing that changes the
# schema. The stall point is the ENTRY of that backend call, on the
# Application's own backend instance: after the revision read and the
# plan check (and after every lock the cell took for them), before the
# first DDL statement. The cell's own `create_collection` / `create_entity`
# / `add_field` / `alter_field` are wrapped only to mark the calling
# thread while a call that presents a `plan` or `dry_run` is in progress;
# a schema operation presenting neither passes through, unmarked. One
# armed hold claims the first marked call that reaches the stall point (a
# `threading.Lock` nobody releases) and lets every later call through, so
# exactly ONE schema operation is held. Data operations never reach the
# three backend methods. The adapter replaces these product methods on
# the instance and restores them on exit; no product source changes.


@contextmanager
def _hold_after_plan_verification(cell_obj: object) -> Iterator[PlanVerificationHold]:
    backend = cell_obj._backend  # noqa: SLF001 -- adapter-internal plumbing, same convention `_hold_after_idempotency_check` above uses.
    backend_names = ("create_collection", "add_field", "alter_field_constraints")
    cell_names = ("create_collection", "create_entity", "add_field", "alter_field")
    backend_originals = {name: getattr(backend, name) for name in backend_names}
    cell_originals = {name: getattr(cell_obj, name) for name in cell_names}
    claimed = threading.Lock()
    entered = threading.Semaphore(0)
    release = threading.Event()
    marked = threading.local()
    held: list[Any] = []
    meter = _BoundedPoolStatementMeter(cell_obj)

    def _marking(original):
        def _marked(*args, **kwargs):
            previous = getattr(marked, "presents_plan_or_dry_run", False)
            marked.presents_plan_or_dry_run = previous or kwargs.get("plan") is not None or bool(kwargs.get("dry_run"))
            try:
                return original(*args, **kwargs)
            finally:
                marked.presents_plan_or_dry_run = previous

        return _marked

    def _stalling(original):
        def _stalled(*args, **kwargs):
            if getattr(marked, "presents_plan_or_dry_run", False) and claimed.acquire(blocking=False):
                held.extend(_scope_connections(kwargs.get("scope")))
                entered.release()
                release.wait()
            return original(*args, **kwargs)

        return _stalled

    for name, original in cell_originals.items():
        setattr(cell_obj, name, _marking(original))
    for name, original in backend_originals.items():
        setattr(backend, name, _stalling(original))

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_plan_verification: no schema operation reached the entry of the backend's "
                f"DDL-carrying method within {timeout_s}s (expected the next schema operation presenting a "
                "plan or dry_run on this Application to stall there -- see this helper's own module comment)"
            )
        return 1

    try:
        yield PlanVerificationHold(_wait_until_held, meter.statements_after_release)
    finally:
        try:
            meter.mark_release(held)
        finally:
            release.set()
            for name, original in backend_originals.items():
                setattr(backend, name, original)
            for name, original in cell_originals.items():
                setattr(cell_obj, name, original)


# port v1.22 (design docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md D-7 and
# section 6.4): `hold_after_admission` realization for this HTTP plug (the
# same running process's cell, reached the same way
# `_hold_after_idempotency_check` above reaches it). See
# `conformance_adapter_mitatedb.py`'s identically named helper for the full
# rationale: `ApplicationCell._limit_gate` yields the request's deadline
# after the rate and concurrency gates, the request-size and depth checks and the
# narrowing by `budget`, and the caller opens the backend's request scope
# -- the first connection -- only after that, so a stall just after the
# gate yields is the point the contract names. The wrap replaces the gate on
# the cell instance and restores it on exit; no product source changes. A
# request that names no `endpoint_kind` (a catalog read, a single-row
# write) passes through; the first one that does claims the stall, so
# exactly ONE request is held. It holds no connection there, so the
# statement count (`_BoundedPoolStatementMeter`) has nothing to add to its
# release-time figure.


class _AdmissionGateContextManager:
    """The per-call context-manager object `_hold_after_admission_via_
    stalled_gate` returns for a request that names an `endpoint_kind`:
    delegates to the REAL `_limit_gate` context manager it wraps, and
    inside `__enter__`, after the real gate has run and returned its
    `deadline`, the first such request to arrive claims the stall and
    blocks on a shared `threading.Event` before the value reaches the
    caller."""

    __slots__ = ("_inner", "_claimed", "_entered", "_release")

    def __init__(self, inner_cm, claimed: threading.Lock, entered: threading.Semaphore, release: threading.Event) -> None:
        self._inner = inner_cm
        self._claimed = claimed
        self._entered = entered
        self._release = release

    def __enter__(self):
        value = self._inner.__enter__()
        if self._claimed.acquire(blocking=False):
            self._entered.release()
            self._release.wait()
        return value

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)


@contextmanager
def _hold_after_admission_via_stalled_gate(cell_obj: object) -> Iterator[AdmissionHold]:
    original_gate = cell_obj._limit_gate  # noqa: SLF001 -- adapter-internal plumbing, same convention `_hold_after_idempotency_check` above uses.
    claimed = threading.Lock()
    entered = threading.Semaphore(0)
    release = threading.Event()
    meter = _BoundedPoolStatementMeter(cell_obj)

    def _admission_limit_gate(*args, **kwargs):
        inner = original_gate(*args, **kwargs)
        if kwargs.get("endpoint_kind") is None:
            return inner
        return _AdmissionGateContextManager(inner, claimed, entered, release)

    cell_obj._limit_gate = _admission_limit_gate  # noqa: SLF001

    def _wait_until_held(timeout_s: float) -> int:
        if not entered.acquire(timeout=timeout_s):
            raise AssertionError(
                f"hold_after_admission: no request reached the stalled `_limit_gate` within {timeout_s}s "
                "(expected the next query, mutation or schema operation on this Application to stall just "
                "after the gate yielded its deadline -- see this helper's own module comment)"
            )
        return 1

    try:
        yield AdmissionHold(_wait_until_held, meter.statements_after_release)
    finally:
        try:
            meter.mark_release([])
        finally:
            release.set()
            cell_obj._limit_gate = original_gate  # noqa: SLF001


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


class _ControlCredentialHolder:
    """Holds the one control credential handle a
    `MitateDBHttpConformanceAdapter` instance believes is currently valid.
    Kept as one small mutable object (rather than two bare attributes
    directly on the adapter) so `isolated_application_surface`'s shallow
    `copy.copy(self)` shares this SAME object with every isolated copy it
    yields: neither side keeps a value-copied cache the other cannot see a
    repair against."""

    __slots__ = ("ref", "secret")

    def __init__(self) -> None:
        self.ref: str | None = None
        self.secret: str | None = None


class MitateDBHttpConformanceAdapter(ConformanceAdapter):
    """Connects the common conformance port to MitateDB-api's real HTTP +
    PostgreSQL stack: `mitatedb_api.http.create_app` in front of an
    `HttpService` whose sessions are backed by `PostgresBackend` against a
    real, throwaway-provisioned local PostgreSQL 16 database.
    """

    name = "MitateDB-api (http+postgres)"
    # port v1.14 (design D-1 (A) 4, WP-3): drives the real ASGI app
    # through `httpx.ASGITransport` (in-process, no real socket) by
    # default -- the socket adapter (WP-4) subclasses this adapter and
    # overrides `transport_kind`/`_build_client`/`_surfaces_value` below,
    # never the other way around.
    transport_kind = "asgi"

    # ------------------------------------------------------------------
    # hooks (design D-1 (A) 6, WP-3) -- see the identically-named hooks on
    # `r2db-api/conformance/conformance_adapter_r2db_http.py`'s own
    # `R2DBHttpConformanceAdapter` for the full rationale (independent
    # implementation of the same hook SHAPE, P-6: peer code is never
    # shared, only the common port's own contract for these two names is).
    # ------------------------------------------------------------------

    def _build_client(self, app: Any, base_url: str) -> httpx.AsyncClient:
        """Default: an in-process ASGI-transport client against `app`
        (unchanged behavior)."""
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)

    def _surfaces_value(self) -> dict:
        """Default: this module's own synthetic, non-dialable `_SURFACES`
        constant (unchanged behavior). Feeds BOTH the `platform_
        declarations` DB row `_bootstrap_platform` seeds (the control-
        plane's own real composition-root read, `build_control_service`)
        and this adapter's own `FoundationConfig` (the data-plane's own
        capability document) from the exact same values, so the two
        documents' `surfaces` can never silently diverge."""
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
        """Hook (monitor 裁定 2026-09-08, F-2 (b)) -- see the identically-
        named hook on `r2db-api/conformance/conformance_adapter_r2db_http.
        py`'s own `R2DBHttpConformanceAdapter` for the full rationale
        (independent implementation of the same hook SHAPE, P-6). Default:
        no-op; called on the isolated copy, right after `copy.copy(self)`
        and before that copy's own composition begins."""
        return None

    def __init__(self) -> None:
        self._counter = 0
        admin_dsn = _admin_dsn()
        _require_reachable_postgres(admin_dsn)
        _sweep_stale_artifacts(admin_dsn)

        prefix = f"mitatedbhttp{secrets.token_hex(4)}"

        self._prefix_guard = psycopg.connect(admin_dsn, autocommit=True)
        with self._prefix_guard.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", _lock_key(prefix))

        # port v1.14 (design D-1 (A) 6, WP-3): computed ONCE and reused for
        # both the DB-seeded control-plane row (`_bootstrap_platform`
        # below) and this adapter's own data-plane `FoundationConfig`
        # (below) -- never re-derived independently at each site, so the
        # two documents' `surfaces` cannot silently diverge even if a
        # future override's own hook body were not perfectly idempotent.
        surfaces = self._surfaces_value()

        self._script_dir = tempfile.mkdtemp(prefix="mitatedb_http_migrations_")
        # design D-3 (2')/(4): this instance's own `mkdtemp`ed slot
        # directory -- a subdirectory of `self._script_dir`, so `_cleanup`
        # (which `shutil.rmtree`s `self._script_dir`) removes it too. Mode
        # 0700 set explicitly (`mkdir(mode=...)` is masked by umask).
        self._slot_dir = Path(self._script_dir) / "slots"
        self._slot_dir.mkdir(mode=0o700)
        os.chmod(self._slot_dir, 0o700)
        try:
            self._platform = _bootstrap_platform(prefix, admin_dsn, Path(self._script_dir), surfaces)
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
            # 閉じる"): each `backend_postgres.PostgresBackend` holds one
            # runtime and one developer pool per application, each opening
            # its connections on first use up to its `pool_size`.
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
            # `2 * pool_size * _MAX_OPEN_CELLS` regardless of how many total
            # applications this session ever provisions. Every conformance
            # test's own fixture apps stay at the "most recently used" end
            # for the whole duration of that one test (nothing else is
            # provisioned in between), so this never evicts an app a test
            # is actively using.
            from collections import OrderedDict
            self._cells: "OrderedDict[str, ApplicationCell]" = OrderedDict()
            # port v1.11 (design D-6.1/D-6.5 addendum): the per-cell
            # `FoundationConfig` every `provision_application` call below
            # builds a fresh cell from -- named on the instance (not an
            # inline literal) so `isolated_application_surface()` can
            # override just this one attribute on its own copy.
            self._application_config = FoundationConfig(
                control_plane_status="enabled",
                data_base_url=surfaces["data"]["base_url"], control_base_url=surfaces["control"]["base_url"],
                operation_catalog_url=self._operation_catalog_url_value(),
            )
            # Phase 8 WP-1a (design D-1 "置き場は実装WPが新設する (1プロセス
            # 1個)"): this adapter (unlike the in-process one, which routes
            # every cell through `service.ProvisioningFacade` -- now the
            # single place that constructs and shares its own holder
            # internally) builds `ApplicationCell` instances directly in
            # `provision_application` below, so this instance owns the
            # holder explicitly -- exactly one, shared by every cell THIS
            # adapter provisions. `isolated_application_surface()` below
            # gives its own `iso` a FRESH one (never this shared surface's
            # own instance). Built below, once `self._read_store` (its own
            # `rate`) exists.
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
            # `self._read_store` carries a real `pool.BoundedConnectionPool`
            # (`self._read_pool`, below), matching the HTTP composition
            # root's identical wiring (`main.py`'s own `platform_pool`):
            # every authenticated request this adapter sends through
            # `_gate`/`_read_store.authenticate` reuses a pooled connection
            # instead of opening a fresh one, so this adapter's `DBTIME
            # scope=platform` reading reflects the same connection shape a
            # real deployment's application-plane process has. The pool's
            # own size is derived the same way `main.py` derives its
            # production pool's size (`role_pool_size`, `config.py`), from
            # the thread limit (`DEFAULT_THREAD_LIMIT`, the same per-process
            # simultaneous-borrow ceiling `main.build_app` sizes from) --
            # never a fixed literal. `self._write_store` (below) stays per-call/
            # unpooled: it is this adapter's own privileged setup path
            # (`issue_credential`/`revoke_credential`/...), never touched
            # by a measured request, matching `main.py`'s own audit sink
            # (no pool either, `application_audit.py`'s module docstring).
            # Q4 phase (design D-1(b), work order §4 WP-2 変更対象 D): a
            # real Postgres `application_audit` writer -- the SAME
            # `<prefix>svc_api` role/DSN `self._read_store` above already
            # connects with (migration 0005 grants it INSERT-only on this
            # table). No longer carries ANY timeout constructor argument
            # (the former per-connection `SET SESSION` this class used is
            # REMOVED product code) -- the two writer timeouts now come
            # from `<prefix>svc_api`'s own PostgreSQL role setting
            # (`_bootstrap_platform`'s own `0007_platform_declarations.
            # sql` run, immediately overwritten by this adapter's own
            # `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS`/`_IDLE_TIMEOUT_MS`
            # `ALTER ROLE` -- R-105 -- rather than the shipped 5000ms/
            # 5000ms default `main.build_app` relies on), applied
            # automatically at login.
            # The sink borrows from a pool of its own, the way `main.
            # build_app` wires it (`audit_pool`, sized `role_pool_size(
            # thread_limit)` like the credential pool below): every
            # ordinary event is written before the response, so a sink that
            # opened a connection per event would charge every measured
            # request a connection handshake the composition root never
            # pays.
            self._audit_pool = BoundedConnectionPool(
                self._platform.api_dsn,
                max_size=role_pool_size(DEFAULT_THREAD_LIMIT),
            )
            self._application_durable_audit = PostgresApplicationAuditSink(
                self._platform.api_dsn, schema=self._platform.schema, pool=self._audit_pool,
            )
            self._audit_router = AuditRouter(durable_sink=self._application_durable_audit)

            self._read_pool = BoundedConnectionPool(
                self._platform.api_dsn,
                max_size=role_pool_size(DEFAULT_THREAD_LIMIT),
            )
            self._read_store = PostgresCredentialStore(
                self._platform.api_dsn, pepper="synthetic-conformance-pepper-mitatedb-http-0000",
                schema=self._platform.schema, audit_router=self._audit_router, pool=self._read_pool,
            )
            self._write_store = PostgresCredentialStore(
                self._platform.controlplane_dsn, pepper="synthetic-conformance-pepper-mitatedb-http-0000",
                schema=self._platform.schema,
            )
            self._gate = _AuthGate(self._read_store)
            # design D-3 (4), plug table: `rate` is `self._read_store`
            # itself (the SAME `PostgresCredentialStore` and platform pool
            # its own read path already uses -- no second, dedicated pool
            # for the rate statement), `concurrency_slots` is this
            # instance's own `mkdtemp`ed directory, and
            # `concurrency_configured=True`: this plug's `process_
            # ceilings` row is `{"data": 1, "control": 1}` (seeded by
            # `_bootstrap_platform`) and this in-process "supervisor" runs
            # exactly 1 worker, so `ceiling <= workers` always holds.
            self._limit_holder = _LimitStateHolder(
                rate=self._read_store,
                concurrency_slots=HostSharedConcurrencySlots(self._slot_dir),
                concurrency_configured=True,
            )

            def _cell_factory(application_id: str) -> ApplicationCell:
                cell = self._cells.get(application_id)
                if cell is None:
                    raise AssertionError(f"no PostgresBackend cell provisioned for {application_id!r}")
                self._cells.move_to_end(application_id)
                return cell

            # Phase 10 WP-4g (review F-2 fallout): `limit_holder` -- the
            # SAME `_LimitStateHolder` every `ApplicationCell` this surface
            # provisions already shares (`provision_application` above) --
            # and `max_concurrency` -- this surface's own declared
            # `self._application_config.max_concurrency` -- mirror `main.
            # build_app`'s identical wiring (`main.py`'s own comment on its
            # `HttpService(...)` call), so this adapter's pre-authentication
            # concurrency admission actually gates on this surface's real
            # cells instead of being unconstructable (`http.py`'s
            # fail-closed check).
            self._service = HttpService(
                self._gate, _cell_factory, audit_router=self._audit_router,
                limit_holder=self._limit_holder, max_concurrency=self._application_config.max_concurrency,
            )
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
            app = create_app(
                self._service, request_bytes_limit=1_048_576, thread_limit=self._perf_thread_limit,
            )
            self._app = app
            self._loop_owner = True
            import asyncio
            self._loop = asyncio.new_event_loop()
            self._client = self._build_client(app, BASE_URL)

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
                # visibility_lag_ms`) -- R-105: this adapter's own
                # conformance-deployment role-level default
                # (`CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS`/`_IDLE_
                # TIMEOUT_MS`, `_bootstrap_platform`'s own `ALTER ROLE`
                # issued right after the `0007` run that seeds the
                # shipped 5000ms/5000ms values), matching `self.
                # _application_durable_audit`'s own (now argument-free)
                # writer connection above.
                "MITATEDB_AUDIT_DSN": self._platform.auditreader_dsn,
                # Phase 11 WP-3 (design D-5, §7.1 訂正註): the SAME
                # synthetic (or, on the socket adapter, real dialable)
                # value `self._application_config` above carries -- both
                # this "process"' own control-plane document and the
                # data-plane document agree on `operation_catalog_url`
                # structurally (one hook call feeds both), never by
                # cross-checking two independently-configured copies.
                "MITATEDB_OPERATION_CATALOG_URL": self._operation_catalog_url_value(),
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
            self._control_client = self._build_client(self._control_app, BASE_URL)

            # `control_credential()`'s own maintained handle (memoize +
            # call-time validity check -- port v1.5 WP-1 independent review
            # major M-4), mirroring both the in-process adapter's and
            # r2db-http's identical mechanism. Held in one `_ControlCredentialHolder`
            # (not two bare attributes) so `isolated_application_surface`'s
            # shallow copy shares this same cache with every isolated copy.
            self._control_credential_holder = _ControlCredentialHolder()
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
        if self._loop.is_running():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                # Same-thread re-entrancy: THIS thread is already inside
                # a running loop (necessarily `self._loop`, since a
                # second, distinct loop cannot be running concurrently on
                # the same thread) and a coroutine on it called back into
                # `_run`. `asyncio` refuses this regardless of which loop
                # object is named, so let the normal call below raise its
                # loud, original `RuntimeError('This event loop is
                # already running')` instead of masking it with a
                # throwaway loop.
                return self._loop.run_until_complete(coro)
            # WP-6d-ii (design D-13 "実装の形 (6d-ii) の確定" (2)): see
            # `conformance_adapter_r2db_http.py`'s own identical fallback
            # for the full rationale -- a second, genuinely concurrent OS
            # thread (`hold_after_idempotency_lookup`'s own "B" probe)
            # reached here while this SAME shared adapter instance's own
            # `self._loop` is already mid-flight on another thread; give
            # this call its own throwaway loop instead of raising
            # `RuntimeError('This event loop is already running')`.
            # Reusing `self._client` itself across loops here is safe on
            # every plug this adapter builds: on the ASGI-transport plugs
            # its transport is `httpx.ASGITransport`, with no per-loop
            # connection state to mismatch; on the real-socket subclass,
            # `_LazyDialTransport.handle_async_request` (`conformance_
            # adapter_mitatedb_socket.py`) opens a FRESH, one-shot
            # `httpx.AsyncHTTPTransport` per request rather than holding
            # a persistent pool on `self`, so there is likewise no loop-
            # affine state to cross a loop boundary. Every PRE-EXISTING
            # (sequential, single-thread) call path never takes this
            # branch.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
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

    def _query(
        self, session: _Session, entity: str, *, select, where=None, order_by=None, page_size=None,
        cursor=None, extra_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"select": list(select)}
        if where is not None:
            body["where"] = where
        if order_by is not None:
            body["order_by"] = order_by
        # port v1.18 (design D-4, C-30): `cursor` joins `page_size` in the
        # SAME `page` wire object (`QueryRequest.page`) -- both land in one
        # `body.update`-safe dict, mirroring `conformance_adapter_r2db_
        # http.py::_query_request`'s own identical `page_size`/`cursor`
        # merge (independent realization, no code shared between peers).
        page: dict[str, Any] = {}
        if page_size is not None:
            page["size"] = page_size
        if cursor is not None:
            page["cursor"] = cursor
        if page:
            body["page"] = page
        # port v1.13 (design D-6): `budget` is a QueryRequest top-level
        # field, carried the same way `_mutate`'s own `extra_body` already
        # carries `idempotency_key`.
        if extra_body:
            body.update(extra_body)
        return self._send("POST", self._data_path(entity, "query"), session, json_body=body)

    def _mutate(self, session: _Session, entity: str, operations: list[dict[str, Any]], *, extra_body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"operations": operations}
        if extra_body:
            body.update(extra_body)
        return self._send("POST", self._data_path(entity, "mutations"), session, json_body=body)

    def _cross_mutate(
        self, session: _Session, operations: list[dict[str, Any]], *, extra_body: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        # P35 WP-2/WP-3: the cross-entity counterpart of `_mutate` above --
        # a fixed path (`POST /v1/data/mutations`, no per-request entity
        # segment), each operation dict carrying its OWN `entity` key
        # instead. `http.py::post_cross_entity_mutate` is the real, mounted
        # dispatcher this composition genuinely receives the request
        # through (`cross_entity_mutation: partial` as of WP-2's flip).
        body: dict[str, Any] = {"operations": operations}
        if extra_body:
            body.update(extra_body)
        return self._send("POST", "/v1/data/mutations", session, json_body=body)

    def _schema(self, session: _Session, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/v1/schema/operations", session, json_body=dict(body))

    # ------------------------------------------------------------------
    # control plane (privileged, out-of-band setup)
    # ------------------------------------------------------------------

    # See `self._cells`'s own docstring (`__init__`) for why this is
    # bounded: 6 concurrently-open application cells (two role pools
    # each) comfortably covers this suite's own
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

    def _new_backend(self, info: Any, application_id: str) -> PostgresBackend:
        """The backend of one provisioned application, built the way the
        composition root builds it (`main.py::build_app`): pools sized by
        the process's own thread limit (`role_pool_size(DEFAULT_THREAD_
        LIMIT)`), then the startup ledger check."""
        backend = PostgresBackend(
            info.runtime_dsn, info.developer_dsn, application_id=application_id,
            max_execution_ms=self._application_config.max_execution_ms,
            pool_size=role_pool_size(DEFAULT_THREAD_LIMIT),
        )
        backend.verify_platform_upgrades()
        return backend

    def provision_application(self, application_id: str) -> None:
        info = _provision_pg_app(self._platform, application_id)
        self._app_pg[application_id] = info
        self._cells[application_id] = ApplicationCell(
            # port v1.11 (design D-6.1/D-6.5 addendum): reads `self.
            # _application_config` rather than a literal `FoundationConfig(
            # ...)` constructed inline here -- so `isolated_application_
            # surface()` below can give its own fresh cells a SMALL
            # conformance profile (the `max_*` fields) just by overriding
            # this one attribute on its own copy, with no other change to
            # this method. The SHARED, session-scoped adapter's own value
            # (set in `__init__`) is byte-for-byte the same
            # `FoundationConfig(...)` this line used to construct inline.
            application_id, self._application_config,
            backend=self._new_backend(info, application_id),
            audit_router=self._audit_router, limit_holder=self._limit_holder,
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
        #
        # Phase 7 WP-5 rework (supervisor ruling 2026-09-06 item 1):
        # explicitly closes the popped cell's own two role pools
        # (`_evict_cells_over_cap`'s own `evicted_cell.
        # _backend.close()` pattern, reused here) BEFORE the real DROP
        # DATABASE below, rather than relying on Python reference-count
        # deallocation to close them in time -- this method is about to
        # gain callers (WP-5's own generic residue-cleanup teardown) that
        # deprovision applications this SHARED, session-scoped adapter
        # already served real data-plane traffic for, not only this
        # file's own already-narrowly-scoped throwaway apps, so closing
        # explicitly here removes any dependence on GC timing for a
        # not-yet-evicted cell still holding open connections to the
        # database this call is about to drop.
        cell = self._cells.pop(application_id, None)
        if cell is not None:
            cell._backend.close()  # noqa: SLF001
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
        except ConformanceDenial as exc:
            if exc.code not in _REPAIRABLE_AUTH_DENIAL_CODES:
                # A transient/unrelated denial (`LIMIT_EXCEEDED`,
                # `AUTH_STATE_UNAVAILABLE`, ...) never means the cached
                # handle itself is dead -- propagate it unchanged rather
                # than reading it as "repair via a destructive reset" (that
                # would revoke a still-perfectly-live control credential
                # and mask the real failure as a false "it was stale"
                # story).
                raise
            return False

    def _ensure_control_actor(self) -> ControlCredentialHandle:
        """Privileged internal helper (not a port method itself): returns a
        control credential this adapter believes is currently valid and
        must-rotate-cleared. Trusts the cached handle without a preflight
        probe -- an extra `GET .../capabilities` before every real call
        would double this adapter's own control-plane HTTP traffic for no
        correctness benefit. A caller that actually needs certainty the
        returned handle still authenticates (`control_credential()` itself)
        gets that from its own preflight probe; a caller that only needs a
        handle to perform a real privileged operation
        (`_privileged_control_send`, below) gets that from the real
        operation's own denial, repairing only when it is genuinely an
        authority refusal."""
        if self._control_credential_holder.ref is not None:
            return ControlCredentialHandle(
                credential_ref=self._control_credential_holder.ref, secret=self._control_credential_holder.secret)
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
        holder = self._control_credential_holder
        holder.ref = credential_id
        holder.secret = rotated["secret"]
        return ControlCredentialHandle(credential_ref=credential_id, secret=holder.secret)

    def _privileged_control_send(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Internal privileged control-plane call used by setup/observation
        primitives that immediately consume the returned actor for one real
        operation (never by `control_credential()` itself, whose own
        preflight-probe contract is separate, below). Trusts the cached
        handle (`_ensure_control_actor`, no probe) and only pays the cost of
        a real `ops.py reset`/re-send when the actual operation comes back
        with an authority denial -- a transient/unrelated denial
        propagates as-is, with no retry and no repair."""
        actor = self._ensure_control_actor()
        try:
            return self._control_send(method, path, actor, json_body=json_body)
        except ConformanceDenial as exc:
            if exc.code not in _REPAIRABLE_AUTH_DENIAL_CODES:
                raise
            # The cached handle was not actually live (revoked/disabled by
            # some other test's own C-15 vector, or still must_rotate) --
            # repair via a real ritual run and retry exactly once, never in
            # a loop (a second failure is a genuine problem, not
            # staleness).
            actor = self._repair_control_actor()
            return self._control_send(method, path, actor, json_body=json_body)

    def control_credential(self) -> ControlCredentialHandle:
        """Unlike `_ensure_control_actor` (this adapter's own internal
        helper for the privileged setup/observation primitives, which
        deliberately trusts its cache to keep ordinary traffic cheap -- see
        that method's own docstring), this PUBLIC port method verifies
        liveness with one real preflight call before returning: the port's
        call-time validity contract (`docs/design/CONFORMANCE_ADAPTER_V1.md`,
        Major M-4) ("genuinely valid AT CALL TIME") is load-bearing here
        specifically, since C-15's own vectors revoke/reset control
        credentials mid-suite and a LATER, unrelated caller of this method
        must never receive a silently-dead handle it cannot itself detect
        or retry around. A transient/unrelated denial (`LIMIT_EXCEEDED`,
        `AUTH_STATE_UNAVAILABLE`, ...) is never read as "the cache is
        dead" -- it propagates unchanged instead of triggering a
        destructive reset."""
        holder = self._control_credential_holder
        if holder.ref is not None and self._control_actor_is_live(holder.ref, holder.secret):
            return ControlCredentialHandle(credential_ref=holder.ref, secret=holder.secret)
        return self._repair_control_actor()

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
    def isolated_control_surface(self, *, limits_override: Mapping[str, int] | None = None):
        # port v1.11 addendum (supervisor ruling 2026-09-06 item 1): this
        # plug's own `build_control_service` derives `ControlPlaneLimits`
        # from environment variable NAMES (its own docstring's table), not
        # from a `limits=` parameter -- so overriding a field means passing
        # a COPY of `self._control_env` with that field's own env var name
        # set to the override value, via `_CONTROL_LIMIT_ENV_NAMES` above.
        # `limits_override=None` (every pre-addendum call site) leaves
        # `self._control_env` itself unchanged and unreferenced-by-copy,
        # so this is behavior-preserving for the `control_requests_per_
        # minute` vector.
        if limits_override:
            env = dict(self._control_env)
            for field_name, value in limits_override.items():
                env[_CONTROL_LIMIT_ENV_NAMES[field_name]] = str(value)
        else:
            env = self._control_env
        service = build_control_service(env)
        app = create_control_app(service, request_bytes_limit=service.limits.request_bytes)
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
            bearer = actor.secret
            request = client.build_request(
                method, path, json=json_body, headers=[("authorization", f"Bearer {bearer}")]
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

    # port v1.11 (design D-6.1 V2/D-6.5 addendum (1)/(4)): `copy.copy(self)`
    # (mirrors `conformance_adapter_r2db_http.py`'s identical pattern and
    # identical rationale) -- `issue_credential` above is a direct write
    # against `self._write_store` (out-of-band, not an in-band HTTP call
    # on this peer either), so sharing it costs nothing; borrowed for
    # simplicity/consistency with the sibling peer's own construction.
    # `self._platform`/`self._read_store`/`self._write_store`/`self.
    # _audit_router`/`self._application_durable_audit` are all shared
    # (the ALREADY-bootstrapped PG platform, addendum (1): "この経路が要
    # 求するものは無し") -- only the DATA-plane pieces below (`_cells`,
    # `_app_pg`, `_application_config`, `_service`/`_app`/`_client`/
    # `_loop`) are deliberately fresh, so a `provision_application` call
    # against the isolated instance never touches the shared surface's
    # own cells, and gets the SMALL profile below instead of the shared
    # surface's own (production-sized) `_application_config`.
    #
    # `request_bytes_limit` and `FoundationConfig.max_request_bytes` are
    # moved TOGETHER (addendum (4)'s own explicit warning: moving only one
    # of the two makes declaration and enforcement disagree).
    #
    # On exit: closes ONLY what this isolated instance itself opened --
    # its own httpx client, its own event loop, and every real per-cell
    # `PostgresBackend` connection pair it provisioned (D-6.5 addendum
    # (3): "cell 1個につきpersistent接続はちょうど2本") -- never `self.
    # close()`/`self._cleanup()` (which would drop the SHARED platform
    # database this isolated instance borrows).
    @contextmanager
    def isolated_application_surface(self):
        iso = copy.copy(self)
        iso._reset_surface_state()
        iso._app_pg = {}
        iso._cells = OrderedDict()
        # Phase 8 WP-1a (design D-1 "隔離instance は自分専用のホルダを1個
        # 持つ"): `copy.copy(self)` above is a SHALLOW copy -- without this
        # line `iso._limit_holder` would still be the SAME object as the
        # shared, session-scoped surface's own holder. A fresh instance
        # here is what keeps a `hold_in_flight`/rate-window drive against
        # `iso` from ever touching the shared surface's own in-flight
        # counter or rate windows. design D-3 (2')/§1.4 (6): its own,
        # SEPARATE `mkdtemp`ed slot directory -- never `self._slot_dir`,
        # so this surface's declared `concurrency` (3) never contends
        # with the shared surface's own slots; removed in the `finally`
        # block below. `rate` is the SAME shared platform store (the rate
        # row is keyed by the credential, and this surface issues its own
        # credentials).
        iso_slot_dir = Path(tempfile.mkdtemp(prefix="mitatedb_http_isolated_slots_"))
        iso._slot_dir = iso_slot_dir
        iso._limit_holder = _LimitStateHolder(
            rate=iso._read_store,
            concurrency_slots=HostSharedConcurrencySlots(iso_slot_dir),
            concurrency_configured=True,
        )
        # port v1.14 (design D-1 (A) 6, WP-3): `data_base_url`/
        # `control_base_url` are named explicitly here (via `iso`'s OWN
        # `_surfaces_value()` call, not inherited unnamed through
        # `replace()`'s pass-through of every field it does not mention)
        # so the isolated surface's construction goes through the same
        # hook the shared surface's own `__init__` does -- for the
        # DEFAULT hook this is behavior-preserving (`iso._surfaces_value()`
        # returns the identical constants `self._application_config`
        # already carries), but a socket-adapter override (WP-4) can now
        # give the isolated surface its own, separate URLs instead of
        # silently inheriting the parent's real address.
        _iso_surfaces = iso._surfaces_value()
        iso._application_config = replace(
            self._application_config,
            data_base_url=_iso_surfaces["data"]["base_url"],
            control_base_url=_iso_surfaces["control"]["base_url"],
            operation_catalog_url=iso._operation_catalog_url_value(),
            max_batch_items=10, max_batch_entities=5, max_result_rows=5,
            max_filter_terms=5, max_request_bytes=4096, max_schema_objects=20,
            # Phase 8 WP-1a: same values/rationale as the in-process
            # plug's own isolated profile (`conformance_adapter_mitatedb.
            # py::isolated_application_surface`) -- see that profile's own
            # comment for why each value was chosen. `max_requests_per_
            # minute=50` is safe on THIS surface too (unlike an earlier
            # draft of this profile, measured too low): `schema_revision`/
            # `catalog` are deliberately NOT wrapped by `ApplicationCell.
            # _limit_gate` (`cell.py`'s own comment on those two methods),
            # so `http.py::post_schema`'s own post-op revision read-back
            # costs nothing extra here -- a port `create_entity()` call
            # (1 `_schema` op + 1 `add_field` op per field) costs exactly
            # 2 gate hits on this surface, matching `_drive_schema_
            # objects`'s own `(bound // unit + 2) = 22` iterations *
            # 2 = 44, comfortably under 50.
            # `max_operation_depth=5` (Phase 8 WP-1b, R-A 監督裁定
            # 2026-09-06, raised from 4) -- see the in-process plug's own
            # isolated profile comment for the full measured reason (a
            # `where`-carrying mutation's real wire depth is 5, not 4).
            max_requests_per_minute=50, max_concurrency=3, max_execution_ms=5000, max_operation_depth=5,
            # Phase 9 WP-3a (design §5 U-1 = (β)): same value/rationale as
            # the in-process plug's own isolated profile immediately above
            # (`conformance_adapter_mitatedb.py::isolated_application_
            # surface`).
            max_enum_members=5,
            # Phase 9 WP-3c (design D-5, 追補 2 S-f; 監督裁定集約
            # rulings-r5-r6.md I-10, 裁定 J-7): same value/rationale as the
            # in-process plug's own isolated profile immediately above
            # (`conformance_adapter_mitatedb.py::isolated_application_
            # surface`) -- `test_c23_idempotency_semantics.py`'s own
            # (full) leg drives `declared_entries` distinct-key inserts
            # plus one overflow over HTTP too.
            idempotency_entries=20,
            idempotency_retention_ms=60_000,
        )

        def _cell_factory(application_id: str) -> ApplicationCell:
            cell = iso._cells.get(application_id)
            if cell is None:
                raise AssertionError(f"no PostgresBackend cell provisioned for {application_id!r}")
            iso._cells.move_to_end(application_id)
            return cell

        # Phase 10 WP-4g (review F-2 fallout): same wiring as the shared
        # surface's own `HttpService(...)` construction above, but with
        # `iso`'s OWN fresh `_limit_holder` (set above) and `iso`'s OWN
        # isolated-profile `max_concurrency=3` (`iso._application_config`,
        # `replace(...)` above) -- never the shared surface's holder or
        # concurrency value.
        iso._service = HttpService(
            iso._gate, _cell_factory, audit_router=iso._audit_router,
            limit_holder=iso._limit_holder, max_concurrency=iso._application_config.max_concurrency,
        )
        app = create_app(iso._service, request_bytes_limit=iso._application_config.max_request_bytes)
        iso._app = app
        iso._loop = asyncio.new_event_loop()
        iso._client = iso._build_client(app, BASE_URL)
        try:
            yield iso
        finally:
            # WP-4 fix (first-execution finding, mirrors conformance_
            # adapter_r2db_http.py's identical fix): deprovision every
            # application THIS isolated instance provisioned before
            # closing anything else -- `provision_application` writes
            # into the SHARED platform database's `applications` registry
            # table, the SAME one C-14 vector 5's own `n_existing <
            # apps_limit` precondition depends on staying small.
            for app_id in list(iso._app_pg):
                iso.deprovision_application(app_id)
            try:
                iso._run(iso._client.aclose())
            finally:
                for cell in iso._cells.values():
                    cell._backend.close()  # noqa: SLF001
                iso._loop.close()
                shutil.rmtree(iso_slot_dir, ignore_errors=True)

    # port v1.12 (design D-2 実装の形 (b), work order WP-1b): see
    # `_hold_in_flight_via_http_requests_over_stalled_gate`'s own
    # docstring above for the full rationale (wraps `ApplicationCell.
    # _limit_gate`, the SAME real gate the real `GET /v1/catalog` request
    # each held thread issues reaches).
    def hold_in_flight(self, session, n: int):
        """See `ConformanceAdapter.hold_in_flight`'s own docstring
        (`adapter.py`) for this primitive's port-level meaning; this
        realization's own stall point is documented on `_hold_in_flight_
        via_http_requests_over_stalled_gate` and the comment immediately
        above this method."""
        assert isinstance(session, _Session)
        cell = self._cells[session.application_id]
        return _hold_in_flight_via_http_requests_over_stalled_gate(
            cell, self._app, session.bearer, "/v1/catalog", n, self.classify, self.name, self._build_client,
        )

    # port v1.15 (design D-13 "実装の形 (6d-ii) の確定" (4), work order
    # WP-6d-ii): wraps this SAME per-application cell's own `_idempotency_
    # check` -- see `_hold_after_idempotency_check`'s own module comment.
    def hold_after_idempotency_lookup(self, session, idempotency_key: str):
        """See `ConformanceAdapter.hold_after_idempotency_lookup`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_idempotency_check` and the comment immediately
        above this method."""
        assert isinstance(session, _Session)
        cell = self._cells[session.application_id]
        return _hold_after_idempotency_check(cell, idempotency_key)

    # port v1.20: wraps this Application's own backend's DDL-carrying
    # methods -- see `_hold_after_plan_verification`'s own module comment
    # for why the stall point sits at their entry and what a concurrent
    # second schema operation waits on.
    def hold_after_plan_verification(self, session):
        """See `ConformanceAdapter.hold_after_plan_verification`'s own
        docstring (`adapter.py`) for this primitive's port-level meaning;
        this realization's own stall point is documented on
        `_hold_after_plan_verification` and the comment immediately above
        it."""
        assert isinstance(session, _Session)
        cell = self._cells[session.application_id]
        return _hold_after_plan_verification(cell)

    # port v1.22: wraps this SAME per-application cell's `_limit_gate` -- see
    # `_hold_after_admission_via_stalled_gate`'s own module comment for why the point just after
    # the gate yields is the point after the bounds are fixed and before the first connection
    # acquisition.
    def hold_after_admission(self, session):
        """See `ConformanceAdapter.hold_after_admission`'s own docstring
        (`adapter.py`) for this primitive's port-level meaning; this
        realization's own stall point is documented on
        `_hold_after_admission_via_stalled_gate` and the comment
        immediately above it."""
        assert isinstance(session, _Session)
        cell = self._cells[session.application_id]
        return _hold_after_admission_via_stalled_gate(cell)

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
    # audit_query surface (port v1.8, phase 4 WP-3(b) PROVIDED branch).
    # Real HTTP POST /v1/audit/query -- against the CONTROL client (`self.
    # _control_client`), never the data-plane client (design R1 / work
    # order instruction: exercises the alias path, never `/control/v1/
    # audit/query`).
    # ------------------------------------------------------------------

    def _audit_query_status(self) -> str:
        # Reads via this adapter's OWN privileged control credential
        # (the cache-trusting `_privileged_control_send`, never the public
        # probing `control_credential()`), and never via the `actor` a
        # caller of `audit_query` supplies -- see
        # conformance_adapter_r2db_http.py's `_audit_query_status` for the
        # C-09-vector-3 rationale; this adapter's own copy trusts the
        # cached actor and sends one request where r2db's probes first.
        document = self._privileged_control_send("GET", "/control/v1/capabilities")
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
    def audit_visibility_lag_ms(self) -> int:
        document = self._privileged_control_send("GET", "/control/v1/capabilities")
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

    def select_eq(
        self, session: object, entity: str, select: Sequence[str], field: str | None, value: Any, *, limit: int | None = None
    ) -> list[dict]:
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        # port v1.12 (L7-21): `limit` maps directly onto `_query`'s own
        # pre-existing `page_size` keyword (unchanged by this WP),
        # which puts `{"page": {"size": page_size}}` on the real wire body
        # (`QueryRequest.page.size`) -- `None` omits it.
        result = self._query(session, entity, select=select, where=where, page_size=limit)
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
        where = [{"field": field, "operator": operator, "value": value}]
        # port v1.12 (L7-21): additional predicates appended to the SAME
        # real `where` array the wire body already carries.
        if extra_predicates:
            where.extend({"field": f, "operator": o, "value": v} for f, o, v in extra_predicates)
        result = self._query(session, entity, select=select, where=where)
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
        # Supervisor ruling B (WP-3a review, {scratchpad}/rulings-wp3a-
        # review.md): this used to hardcode `select=["id"]`, on the
        # assumption every entity carries the base `id` column this
        # adapter's own pre-existing `create_entity_with_declared_types`
        # always supplies (P3-D1's own default) -- and on the stale claim
        # that `application_catalog` is `unavailable` here. Neither holds
        # any more: `application_catalog` is `enabled` unconditionally on
        # this composition (`MitateDB-api/src/mitatedb_api/capabilities_document.py::build_capabilities_document`),
        # `GET /v1/catalog` is real and mounted (see `catalog_document`
        # below), and port v1.13's `schema_operation_with_result` (D-2)
        # lets a caller `create_entity` with an arbitrary `fields` list
        # that omits `id` entirely -- counting such an entity by
        # selecting a column it does not have would fail. This mirrors
        # `conformance_adapter_r2db_http.py`'s own `count()` (same
        # GENERAL shape, independent implementation, design principle 1):
        # read the entity's own field list from the real catalog and
        # select those, rather than assuming any specific field name
        # exists.
        document = self._send("GET", "/v1/catalog", session)
        fields: list[str] | None = None
        for item in document["entities"]:
            if item["entity"] == entity:
                fields = item["fields"]
                break
        if not fields:
            return 0
        # port v1.18 (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-4):
        # a single `page.size`-less request used to rely on this
        # deployment's own default bound (500) "comfortably covering this
        # suite's own small fixtures" -- untrue on the isolated surface's
        # own smaller `max_result_rows` once a collection holds more rows
        # than that bound (C-30's own concurrent-insert node inserts a
        # 6th row). Omitting `page_size` walks the entry point's own
        # default page (design D-2b.3), which stays within ANY positive
        # deployment bound while costing roughly one request per `max_
        # result_rows` rows rather than one per row (a `page_size=1` walk
        # would multiply this suite's own rate budget by the row count
        # and collide with `max_requests_per_minute` on the `full`
        # idempotency leg). A page count that outruns
        # the rows actually counted, plus one, means the cursor stopped
        # advancing; that is this adapter's own bug, not a rate-limit
        # condition, so it is raised here rather than left to surface as
        # a misleading `LIMIT_EXCEEDED`.
        total = 0
        cursor: str | None = None
        pages = 0
        while True:
            result = self._query(session, entity, select=list(fields), cursor=cursor)
            total += len(result["items"])
            pages += 1
            if pages > total + 1:
                raise AssertionError(
                    f"count({entity!r}) did not terminate: {pages} pages for {total} rows"
                )
            cursor = result.get("next_page")
            if cursor is None:
                break
        return total

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
        # any other session operation. Excludes THREE of this peer's own
        # bookkeeping tables -- `_mdb_schema_revision` (schema-revision
        # counter), `_mdb_field_types` (the declared-type registry itself,
        # Phase 6 WP-3), and `_mdb_platform_upgrades` (the per-application
        # platform-upgrade ledger, Q4 phase WP-4, design D-3(a)) -- none
        # of which is a real entity a `create_entity`/`create_collection`
        # caller ever created.
        self._send("GET", "/v1/capabilities", session)
        info = self._app_pg[session.application_id]
        conn = psycopg.connect(info.developer_dsn, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name NOT IN (%s, %s, %s)",
                    [_SCHEMA_REVISION_TABLE, _FIELD_TYPES_TABLE, _PLATFORM_UPGRADES_TABLE],
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
        # general schema-operation primitive presented to the same real,
        # single `/v1/schema/operations` dispatcher `_schema` already uses.
        # `destructive`/`confirmation` follow the identical VALID_
        # CONFIRMATION sentinel protocol `attempt_batch_with_addresses`
        # above uses for a batch-embedded delete. `enum` is tri-state (port
        # v1.13 追補, `adapter.ENUM_CLEAR`): omitted -> no `enum` key on
        # the wire; `ENUM_CLEAR` -> a literal JSON `enum: null`; a
        # `Sequence` -> `enum: [...]`, unchanged from before this addendum.
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
                    self._schema(session, _probe_body)

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
        result = self._schema(session, body)
        return {
            "revision": str(result.get("revision")) if result.get("revision") is not None else None,
            "descriptor": result.get("descriptor"),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

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
        # MutationRequest top-level fields, carried through `_mutate`'s own
        # `extra_body` exactly as `attempt_batch_with_addresses` already
        # carries `idempotency_key`. port v1.13 追補: `destructive`/
        # `confirmation` follow the IDENTICAL `VALID_CONFIRMATION`
        # declare-and-echo protocol `attempt_batch_with_result`'s own
        # per-operation loop already applies to `BatchOperation.
        # destructive`/`.confirmation` below -- needed for C-22's `_confirm_
        # probe`. port v1.13 追補 2 (C-22 leg (10)): `transaction` is
        # `MutationRequest`'s own PRE-EXISTING top-level key, carried
        # through `extra_body` the same way, defaulting to `None`
        # (omitted, `http.py::post_mutate`'s own `body.get("transaction",
        # "atomic")` default then applies exactly as every pre-addendum
        # caller already gets). WP-1 addendum (C-25 (4)): `idempotency_key`
        # is carried through `extra_body` the same way -- a `MutationRequest`
        # top-level field on this peer too, never per-item.
        assert isinstance(session, _Session)
        item = self._attempt_mutation_item(
            entity, operation, values=values, where_field=where_field, where_value=where_value,
            expected_revision=expected_revision, unique_key=unique_key,
        )
        if destructive:
            item["destructive"] = True
        if confirmation is not None:
            if confirmation is VALID_CONFIRMATION:
                probe_item = dict(item)
                probe_item["destructive"] = True

                def probe(_probe_item=probe_item) -> None:
                    self._mutate(session, entity, [dict(_probe_item)])

                peer_confirm = self._resolve_confirmation(confirmation, probe=probe, legacy_token="DELETE")
                item["confirmation"] = peer_confirm
            else:
                item["confirmation"] = confirmation
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
        result = self._mutate(session, entity, [item], extra_body=extra_body or None)
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
        # port v1.11 (design D-6.7 C-07 (ii)): `idempotency_key` is a
        # REQUEST-level field on `MutationRequest` (`http.py::post_mutate`
        # refuses it as a top-level `body` key, `MutationRequest.
        # idempotency_key`, contract-closed on the per-operation shape) --
        # never placed inside an individual item. port v1.13 (design §6.1
        # item (v)): folded through the shared `fold_batch_idempotency_
        # key`, exactly like `attempt_batch_with_result` below -- never an
        # unguarded `next(...)` over each op's own value.
        idempotency_key = fold_batch_idempotency_key(operations)
        result = self._mutate(
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
        # result` above establishes.
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
        result = self._mutate(session, entity, items, extra_body=extra_body or None)
        return {
            "affected": result["affected"],
            "assigned_addresses": result.get("assigned_addresses"),
            "committed": result.get("committed", not dry_run),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

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
        # port v1.11 (design D-6.7 C-07 (ii)): `idempotency_key` is a
        # REQUEST-level field on `ScopedMutationRequest`
        # (`http.py::post_cross_entity_mutate` refuses it as a top-level
        # `body` key). port v1.13 (design §6.1 item (v)): folded through
        # the shared `fold_batch_idempotency_key`, exactly like `attempt_
        # cross_entity_batch_with_result` below -- never an unguarded
        # `next(...)`.
        idempotency_key = fold_batch_idempotency_key(operations)
        result = self._cross_mutate(
            session, items,
            extra_body={"idempotency_key": idempotency_key} if idempotency_key is not None else None,
        )
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
        # port v1.13: `attempt_cross_entity_batch`'s exact request shape,
        # extended with the same request-level `dry_run`/`plan`/`budget`/
        # (folded) `idempotency_key` machinery `attempt_batch_with_result`
        # uses. Unlike `r2db-api`, this composition's `cross_entity_
        # mutation: partial` is real, so these new fields are genuinely
        # reachable here once `dry_run`/`request_budget` flip.
        assert isinstance(session, _Session)
        items = [self._scoped_batch_item(session, op) for op in operations]
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
        result = self._cross_mutate(session, items, extra_body=extra_body or None)
        return {
            "affected": result["affected"],
            "committed": result.get("committed", not dry_run),
            "plan": result.get("plan"),
            "request_id": result.get("request_id"),
        }

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
        # port v1.13 (design D-6): `budget` is a QueryRequest top-level
        # field, carried through `_query`'s own `extra_body`.
        assert isinstance(session, _Session)
        where = [{"field": field, "operator": "eq", "value": value}] if field is not None else None
        extra_body = {"budget": dict(budget)} if budget else None
        result = self._query(session, entity, select=select, where=where, extra_body=extra_body)
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
        to `_query` together with that SAME helper's pre-existing
        `order_by`/`page_size` keywords and its `extra_body` merge (which
        carries `budget`, exactly as `query_with_budget` above already
        carries it alone)."""
        assert isinstance(session, _Session)
        where: list[dict[str, Any]] = [{"field": field, "operator": operator, "value": value}]
        if extra_predicates:
            where.extend({"field": f, "operator": o, "value": v} for f, o, v in extra_predicates)
        extra_body = {"budget": dict(budget)} if budget else None
        result = self._query(
            session, entity, select=select, where=where,
            order_by=list(order_by) if order_by else None, page_size=page_size, extra_body=extra_body,
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
        header_pairs = [("authorization", f"Bearer {session.bearer}")]
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
        through `_query`'s own real `POST .../query` entry point,
        verbatim -- never interpreted here."""
        assert isinstance(session, _Session)
        where_body = [{"field": f, "operator": op, "value": v} for f, op, v in where] if where else None
        order_body = [{"field": f, "direction": d} for f, d in order_by] if order_by else None
        extra_body = {"budget": dict(budget)} if budget else None
        result = self._query(
            session, entity, select=select, where=where_body, order_by=order_body,
            page_size=page_size, cursor=cursor, extra_body=extra_body,
        )
        return result["items"], result.get("next_page")

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
            # Phase 9 WP-3a: mirrors the in-process adapter's identical
            # addition (`conformance_adapter_mitatedb.py::public_operation_
            # callables`) -- `alter_field` is a new, real public method.
            ApplicationDeveloper.alter_field,
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
            # the in-band enable call and `handle` (minted via the
            # privileged `_write_store`) both ultimately act on the SAME
            # `<schema>.credentials` row (R-4: the control-writer registry
            # and the application-plane's own read-only store are two
            # Python representations of one PostgreSQL table -- 2ストア
            # 突合 is structural here, no adapter-side reconciliation shim
            # needed the way the in-process adapter's own separate dicts
            # required). `enable` itself succeeds (contract `enable_
            # credential.semantics`: reverses disable only); the proof this
            # is `must_deny`, not `must_ignore`, is that a genuine
            # re-authenticate is chained inside this SAME `attempt()`. Uses
            # the internal privileged path (`_privileged_control_send`),
            # never the public probing `control_credential()`.
            self._privileged_control_send(
                "POST", f"/control/v1/credentials/{quote(handle.credential_ref, safe='')}/enable")
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

    # port v1.11 (design D-6.6 (e)): non-normative, duck-typed accessor,
    # mirrors `conformance_adapter_r2db_http.py`'s identical addition --
    # counts REAL PostgreSQL backends, used only by C-05's own (e)
    # resource-release check. WP-4 rework (完了条件 15 / F1 差し戻し 2 巡
    # 目): a bare `f"{prefix}%"` pattern also matched the shared PLATFORM
    # database, where the shared control stack's own lazily-opened
    # connections live -- see the identical fix comment on the r2db-http
    # sibling. The caller now supplies a pattern scoped to ONLY the per-
    # application database(s) the isolated instance itself provisioned.
    def _live_pg_backend_count(self, datname_like: str) -> int:
        with psycopg.connect(self._platform.admin_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname LIKE %s",
                    (datname_like,),
                )
                return cur.fetchone()[0]

    def pool_stats(self) -> dict[str, dict[str, int | float]]:
        """The data-plane counterpart of `conformance_adapter_r2db_http.py`'s
        `pool_stats`. For each `ApplicationCell` in `self._cells`, two kinds
        of entries:

        - one per role pool (`backend_postgres.PostgresBackend.pool_stats`):
          the pool's own `stats()` dict (keys `size`/`acquire_count`/
          `wait_count`/`wait_total_ms`/`wait_max_ms`/`in_use_peak`), keyed
          `<application_id>/<role>` -- the same key as r2db's;
        - one for the application's schema lock (`PostgresBackend.schema_
          lock_stats`, the shared and exclusive entity-lock acquisitions and
          the application-wide one counted together): keys `acquire_count`/
          `wait_count`/`wait_total_ms`/`wait_max_ms`, keyed
          `<application_id>`. A wait is an acquisition the non-blocking
          attempt did not get.

        Empty when no cell is currently open."""
        stats: dict[str, dict[str, int | float]] = {}
        for application_id, cell in self._cells.items():
            for role, role_stats in cell._backend.pool_stats().items():  # noqa: SLF001 -- adapter-internal reach-in, same convention as this file's other `cell._...` accesses above
                stats[f"{application_id}/{role}"] = role_stats
            stats[application_id] = cell._backend.schema_lock_stats()  # noqa: SLF001 -- same reach-in
        return stats

    def prepared_stats(self) -> list[dict]:
        """R-79 (WO §1.2 D-2/D-3): the data-plane counterpart of
        `conformance_adapter_r2db_http.py`'s identical addition. Calls each
        open cell's own PUBLIC `prepared_stats()` (`cell.py::ApplicationCell.
        prepared_stats`) -- unlike `pool_stats`
        immediately above, this needs no `noqa: SLF001` reach-in, since
        `ApplicationCell.prepared_stats` is itself a public method. Flat
        list across every open cell (each connection's own `label` already
        carries its role and backend pid, so cells never need a separate
        key the way `pool_stats`'s dict does)."""
        rows: list[dict] = []
        for cell in self._cells.values():
            rows.extend(cell.prepared_stats())
        return rows

    def perf_thread_limit(self) -> int:
        """The effective `thread_limit` the data-plane app's own
        `create_app` call was built with: the resolved `DSA_PERF_THREAD_
        LIMIT` value when the env names a positive integer, `DEFAULT_
        THREAD_LIMIT` otherwise (absent, empty, or not a positive
        integer)."""
        return self._perf_thread_limit

    def platform_db_time_stats(self) -> dict[str, int | float]:
        """Sums `self._read_pool`/`self._application_durable_audit`'s own
        `platform_stats()` -- the two platform-side connection sources the
        data-plane measurement path actually uses. The credential-store
        share comes from `self._read_pool` (the pool `self._read_store`
        checks connections out of), never from `self._read_store.platform_
        stats()` itself: with a pool wired, `self._read_store` no longer
        opens its own per-call connections (`_borrow_connection`'s pool
        branch); `self._read_store`'s own no-pool accumulators stay at
        zero, and the pool is where the real traffic lands.
        `self._application_durable_audit` borrows from `self._audit_pool`
        (matches `main.py`'s own audit sink) and its `platform_stats()`
        folds that pool's own accounting in; `self._write_store` is
        provisioning-only, never touched by a measured request. Read-only: every value
        read here is a plain accumulated attribute, no new connection
        opens."""
        credentials_stats = self._read_pool.platform_stats()
        audit_stats = self._application_durable_audit.platform_stats()
        return {
            "sessions": credentials_stats["sessions"] + audit_stats["sessions"],
            "connect_wall_ms": credentials_stats["connect_wall_ms"] + audit_stats["connect_wall_ms"],
            "db_wall_ms": credentials_stats["db_wall_ms"] + audit_stats["db_wall_ms"],
            "txn_count": credentials_stats["txn_count"] + audit_stats["txn_count"],
            "db_calls": credentials_stats["db_calls"] + audit_stats["db_calls"],
        }

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
