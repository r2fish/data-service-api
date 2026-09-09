"""Phase 4 WP-2(b): `audit_query` -- the read surface (D-5/D-6), its
`audit_requests_per_minute` window (M-8/P4-D4 item 8), its `event_classes`
declaration (D-7), and the `contract_version` 1.4.0 flip.

Design this file is written against: docs/design/
PHASE4_DURABLE_AUDIT_SINK_V1.md D-5/D-6/D-7, work order docs/work-orders/
PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-2(b).

WP-2(a) scope (durable sink, pre-commit hook, dispatch, buffer/alert, the
two writer-connection timeouts) is `test_application_audit.py`'s own file
and is NOT re-tested here -- this file starts from a durable sink that
already works and tests the READ side built on top of it.
"""
from __future__ import annotations

import os
import json
import secrets
import subprocess
import threading
import time
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.testclient import TestClient

from r2db_api.audit import ApplicationAuditSink, AuditEvent, ControlAuditSink
from r2db_api.audit_query import (
    DECLARED_AUDIT_EVENT_CLASSES,
    DECLARED_AUDIT_OPERATIONS,
    DECLARED_AUDIT_TARGET_KINDS,
    DECLARED_COALESCING_WINDOW_MS,
    InMemoryAuditQueryStore,
)
from r2db_api.auth import AuthContext, ControlCredentialStore, CredentialStore, compose_bearer_locator

# `r2db_api.control_main` ends with a module-level `app = build_control_
# app()` (design §8 m-10) that reads `os.environ` the instant it is first
# imported -- mirrors `conformance_adapter_r2db_http.py`'s own identical
# `setdefault` guard for the same reason (this file never uses that
# module-level `app`, only `assemble_control_stack`, and every harness
# below builds its own real, per-test/per-module DSNs).
os.environ.setdefault("R2DB_CONTROLPLANE_DSN", "host=/tmp port=1 dbname=r2db_audit_query_test_import_placeholder")
os.environ.setdefault("R2DB_CONTROL_CREDENTIAL_PEPPER", "r2db-audit-query-test-import-placeholder-ctl-pepper")
os.environ.setdefault("R2DB_CREDENTIAL_PEPPER", "r2db-audit-query-test-import-placeholder-app-pepper")
# Q4 phase WP-1 (design D-2(f)): `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_
# URL` are REMOVED -- `build_control_app` now rejects them outright (F-2)
# if defined at all, so the two `setdefault` calls a prior phase placed
# here are gone; `build_control_app()` itself remains zero-network after
# this phase too (see `control_main.py`'s own docstring), so this module's
# bare import still never touches the network.

import r2db_api.control_main as control_main  # noqa: E402 -- module object itself (not just `assemble_control_stack`), see `test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env` below
from r2db_api.control_http import _ROUTES, create_control_app  # noqa: E402
from r2db_api.control_main import assemble_control_stack  # noqa: E402
from r2db_api.control_plane import _AUDIT_ROLE_ALLOWED_OPERATIONS, ControlPlaneService, InMemoryControlBackend  # noqa: E402
from r2db_api.credential_store import PostgresApplicationAuditSink, PostgresControlCredentialStore  # noqa: E402
from r2db_api.errors import FoundationError  # noqa: E402
from r2db_api.limits import ControlPlaneLimits  # noqa: E402
from r2db_api.service import ControlAuthority, DataService  # noqa: E402

pytestmark = pytest.mark.anyio

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
APP_PEPPER = "synthetic-test-pepper-audit-query-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-audit-query-ctl-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
    "0007_application_audit.sql",
    "0008_platform_declarations_and_writer_timeouts.sql",
    # Phase 10 WP-6a (design D-5(ii)): widens `platform_declarations_key_
    # check` to admit `process_ceilings` -- required so this file's own
    # `platform` fixture can seed that row below (F-15 is unconditional,
    # like F-3 for `surfaces`, since WP-6a).
    "0012_process_ceilings.sql",
)

# Q4 phase WP-1 (design D-2(c)): this file's own `platform` fixture seeds a
# `surfaces` row WITH `control` (unlike `test_credential_persistence.py`'s
# own control-less default) -- every real `control_main.build_control_app`
# built below is a genuine control-plane process, which unconditionally
# requires `surfaces.control` (design §3.7 control-plane 1-5).
_DEFAULT_SURFACES_VALUE = {
    "data": {"base_url": "https://r2db-audit-query-test.example.invalid/v1"},
    "control": {"base_url": "https://r2db-audit-query-control-test.example.invalid/control/v1"},
}

# Generous enough that no test below accidentally trips a limit it is not
# specifically testing (mirrors test_control_plane_service.py's own
# `_GENEROUS_LIMITS` convention) -- the rate-window tests build their own
# tight `ControlPlaneLimits` explicitly.
_GENEROUS_LIMITS = ControlPlaneLimits(
    applications=100_000, credentials_per_application=100_000,
    control_requests_per_minute=100_000, audit_requests_per_minute=100_000,
)


# ===========================================================================
# PostgreSQL platform fixture (duplicated per this repository's own
# established precedent of not taking cross-test-module import dependencies
# -- test_application_audit.py/test_control_plane_service.py both do the
# same).
# ===========================================================================


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


def _require_admin_connection() -> None:
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_audit_query.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            leftover_databases = [row[0] for row in cur.fetchall()]
            for database in leftover_databases:
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbauditq{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    auditreader_role = f"{prefix}_auditreader"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)
    auditreader_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_auditq_migrations")
    rewritten: dict[str, Path] = {}
    for name in MIGRATION_NAMES:
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
        _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
        _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
        _run_psql(control_dsn, rewritten["0007_application_audit.sql"], {"auditreader_password": auditreader_password})
        _run_psql(control_dsn, rewritten["0008_platform_declarations_and_writer_timeouts.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(control_dsn, rewritten["0012_process_ceilings.sql"])
        with psycopg.connect(control_dsn) as _seed_conn:
            with _seed_conn.cursor() as _seed_cur:
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps(_DEFAULT_SURFACES_VALUE)],
                )
                # Phase 10 WP-6a (design D-5(ii)): `process_ceilings` is
                # unconditionally required, like `surfaces` above (F-15) --
                # single-process ceiling for both planes, matching every
                # `build_app`/`build_control_app` this fixture drives
                # (neither uses `--workers`).
                _seed_cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            _seed_conn.commit()
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    api_dsn = _dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db)
    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)
    auditreader_dsn = _dsn_with(admin_dsn, user=auditreader_role, password=auditreader_password, dbname=platform_db)

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        api_dsn=api_dsn, api_role=api_role, controlplane_dsn=controlplane_dsn, controlplane_role=controlplane_role,
        auditreader_dsn=auditreader_dsn, auditreader_role=auditreader_role, platform_db=platform_db, schema=schema,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


# ===========================================================================
# Harnesses -- in-memory and Postgres, both wired with a real `audit_reader`
# (D-10 parity).
# ===========================================================================


def _memory_harness(*, clock=None) -> types.SimpleNamespace:
    credentials = CredentialStore(pepper=APP_PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    control_audit = ControlAuditSink()
    application_audit: ApplicationAuditSink = data_service._durable_audit  # noqa: SLF001 -- D-10 reach-in, established convention
    reader = InMemoryAuditQueryStore(control_audit, application_audit)
    service = ControlPlaneService(
        backend, audit=control_audit, limits=_GENEROUS_LIMITS, clock=clock,
        audit_reader=reader, audit_visibility_lag_ms=0,
    )
    control_credential_id = "ctl_" + secrets.token_hex(8)
    control_secret = "audit-query-memory-control-" + secrets.token_urlsafe(8)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(control_credential_id, control_secret, work=work)
        control_credentials.rotate(control_credential_id, control_secret, work=work)

    def seed_audit_credential(credential_id: str, secret: str) -> None:
        with control_credentials.unit_of_work() as work:
            control_credentials.add(credential_id, secret, role="audit", work=work)
            control_credentials.rotate(credential_id, secret, work=work)

    return types.SimpleNamespace(
        kind="memory", service=service, data_service=data_service, authority=authority, credentials=credentials,
        # Composed locator form (Phase 6 WP-2, design D-1(c)) -- every
        # caller below presents this straight as a bearer.
        control_credential_secret=compose_bearer_locator(control_credential_id, control_secret),
        control_credential_id=control_credential_id,
        seed_audit_credential=seed_audit_credential, cleanup=lambda: None,
    )


def _postgres_harness(platform: types.SimpleNamespace, *, clock=None, audit_statement_timeout_ms=None, audit_idle_timeout_ms=None, audit_requests_per_minute=None) -> types.SimpleNamespace:
    limits = ControlPlaneLimits(
        applications=100_000, credentials_per_application=100_000, control_requests_per_minute=100_000,
        audit_requests_per_minute=audit_requests_per_minute or 100_000,
    )
    # A small, explicit timeout pair by default (200ms/200ms -> ~1.4s
    # derived visibility lag) -- most tests in this file care about
    # ORDERING/FILTERING/CURSOR semantics, not the lag derivation itself
    # (that is `test_declared_visibility_lag_ms_is_derived_from_the_two_
    # timeouts`'s own job, and the two dedicated delayed-tx vectors pass
    # their own explicit, larger values). The product default (5000ms/
    # 5000ms -> 11s) would make every other test here wait 11 real seconds
    # per write before a row becomes visible.
    #
    # Q4 phase WP-1 (design D-1(c)): `assemble_control_stack` no longer
    # derives `audit_visibility_lag_ms` internally from a timeout pair (it
    # now derives from `pg_db_role_setting`, a real composition root's own
    # job -- `r2db_api.control_main.build_control_app`'s `_lifespan`) --
    # this test helper keeps its own pre-existing public parameter names
    # (`audit_statement_timeout_ms`/`audit_idle_timeout_ms`) and performs
    # the SAME `+ 1000` derivation formula itself before calling
    # `assemble_control_stack`, so every existing call site below (and the
    # exact `3_000 + 4_000 + 1_000` arithmetic `test_declared_visibility_
    # lag_ms_is_derived_from_the_two_timeouts` asserts) is unchanged.
    _statement_ms = audit_statement_timeout_ms if audit_statement_timeout_ms is not None else 200
    _idle_ms = audit_idle_timeout_ms if audit_idle_timeout_ms is not None else 200
    service, stores = assemble_control_stack(
        controlplane_dsn=platform.controlplane_dsn, app_pepper=APP_PEPPER, control_pepper=CONTROL_PEPPER,
        schema=platform.schema, pool_size=2, limits=limits,
        audit_visibility_lag_ms=_statement_ms + _idle_ms + 1_000,
        audit_dsn=platform.auditreader_dsn,
    )
    service._clock = clock or service._clock  # noqa: SLF001 -- test-only clock injection, mirrors test_control_plane_service.py's own pattern

    credentials = CredentialStore(pepper=APP_PEPPER)  # unused; DataService below owns the real Postgres one
    data_service = DataService(
        credentials, cell_factory=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("not used")),
        control_plane_status="enabled",
        durable_audit=PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool_size=2),
    )

    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    control_credential_id = "ctl_" + secrets.token_hex(8)
    control_secret = "audit-query-pg-control-" + secrets.token_urlsafe(8)
    with seed_store.unit_of_work() as work:
        seed_store.add(control_credential_id, control_secret, work=work)
        seed_store.rotate(control_credential_id, control_secret, work=work)

    def seed_audit_credential(credential_id: str, secret: str) -> None:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, role="audit", work=work)
            seed_store.rotate(credential_id, secret, work=work)

    def cleanup() -> None:
        for store in stores:
            if store is not None:
                store.close()
        seed_store.close()
        data_service._durable_audit.close()  # noqa: SLF001

    return types.SimpleNamespace(
        kind="postgres", service=service, data_service=data_service, credentials=credentials,
        # Composed locator form (Phase 6 WP-2, design D-1(c)) -- every
        # caller below presents this straight as a bearer.
        control_credential_secret=compose_bearer_locator(control_credential_id, control_secret),
        control_credential_id=control_credential_id,
        seed_audit_credential=seed_audit_credential, cleanup=cleanup, platform=platform,
    )


BACKENDS = ("memory", "postgres")


def _build_harness(kind: str, platform: types.SimpleNamespace | None, **kwargs) -> types.SimpleNamespace:
    if kind == "memory":
        return _memory_harness(**kwargs)
    assert platform is not None, "postgres harness requires the `platform` fixture"
    return _postgres_harness(platform, **kwargs)


def _write_application_audit_row(h: types.SimpleNamespace, **fields) -> None:
    """Writes one row directly to the durable application-plane sink (never
    through `DataService.mutate`/`query` -- this file tests `audit_query`'s
    own READ semantics, not the WP-2(a) dispatch logic `test_application_
    audit.py` already covers)."""
    base = dict(
        event_class="data_operation", request_id=str(uuid.uuid4()), application_id="app_probe",
        actor_type="application_credential", actor_id="crd_probe", role="runtime", operation="query",
        target_kind="entity", outcome="allow", reason_code=None, target_id=None, count=None,
    )
    base.update(fields)
    h.data_service._durable_audit.append(**base)  # noqa: SLF001


def _write_control_audit_row(h: types.SimpleNamespace, *, event_id: str, request_id: str, recorded_at: datetime) -> None:
    """WP-2(b) review M-6: a LOW-LEVEL write, bypassing `ControlAuditSink`/
    `PostgresControlAuditSink.append` (both auto-generate `event_id` and
    stamp `recorded_at`/`occurred_at` at call time) -- needed to construct
    a row with an EXPLICIT, chosen `event_id`/`recorded_at` for the total-
    order tiebreaker test."""
    if h.kind == "memory":
        event = AuditEvent(
            event_id=event_id, event_class="authorization_denial", occurred_at=recorded_at.isoformat(),
            request_id=request_id, application_id=None, actor_type="control_credential", actor_id=None,
            role="control", operation="probe", target_kind="control_credential", outcome="deny", reason_code="PROBE",
        )
        h.service._audit._events.append(event)  # noqa: SLF001
        return
    with psycopg.connect(h.platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, "
                    "operation, target_kind, outcome, reason_code, recorded_at) VALUES "
                    "(%s, 'authorization_denial', %s, %s, 'control_credential', 'probe', 'control_credential', 'deny', 'PROBE', %s)"
                ).format(table=sql.Identifier(h.platform.schema, "control_audit")),
                [event_id, recorded_at, request_id, recorded_at],
            )
        conn.commit()


def _write_application_audit_row_with_identity(h: types.SimpleNamespace, *, event_id: str, request_id: str, recorded_at: datetime) -> None:
    """`_write_control_audit_row`'s application-plane counterpart."""
    if h.kind == "memory":
        event = AuditEvent(
            event_id=event_id, event_class="data_operation", occurred_at=recorded_at.isoformat(),
            request_id=request_id, application_id="app_probe", actor_type="application_credential",
            actor_id="crd_probe", role="runtime", operation="query", target_kind="entity", outcome="allow", reason_code=None,
        )
        h.data_service._durable_audit._events.append(event)  # noqa: SLF001
        return
    with psycopg.connect(h.platform.api_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
                    "actor_type, actor_id, role, operation, target_kind, outcome, recorded_at) VALUES "
                    "(%s, 'data_operation', %s, %s, 'app_probe', 'application_credential', 'crd_probe', 'runtime', 'query', 'entity', 'allow', %s)"
                ).format(table=sql.Identifier(h.platform.schema, "application_audit")),
                [event_id, recorded_at, request_id, recorded_at],
            )
        conn.commit()


def _wait_for_visibility(h: types.SimpleNamespace) -> None:
    """Sleeps past this harness's own declared `visibility_lag_ms` (never a
    fixed literal -- work order §6 item 9's own discipline, mirrored here
    even though this file is peer-local, not common-suite) plus a small
    margin. `0` for the in-memory harness (synchronous writes -- an
    immediate no-op sleep)."""
    time.sleep(h.service._audit_visibility_lag_ms / 1000 + 0.3)  # noqa: SLF001


# ===========================================================================
# D-6: order, cursor, event_classes filter, limit.
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes(kind, platform):
    """WP-2(b) review m-1 (supervisor ruling 2026-09-03): GENUINE
    concurrent writes -- a background thread keeps inserting rows WHILE
    the main thread pages through results (never write-everything-then-
    page, which the completion condition and design D-6's own verification
    method both explicitly call for). A bounded final catch-up pass (past
    `visibility_lag_ms`) guarantees full coverage regardless of how much
    the concurrent phase itself managed to observe -- the concurrency
    requirement is that the poll loop genuinely runs WHILE writes are
    in flight, not that it alone captures every row without help.
    """
    h = _build_harness(kind, platform)
    try:
        marker = "cursorpage" + secrets.token_hex(4)
        total_rows = 20

        def _writer() -> None:
            for i in range(total_rows):
                _write_application_audit_row(h, event_class="data_operation", request_id=f"{marker}-{i}", application_id=marker)
                time.sleep(0.05)

        writer_thread = threading.Thread(target=_writer)
        writer_thread.start()

        seen: list[str] = []
        after: str | None = None
        # Concurrent phase: poll WHILE the writer is still running. Bounded
        # iteration count (never unbounded -- a regression must fail loudly,
        # not hang the suite).
        for _ in range(30):
            if not writer_thread.is_alive():
                break
            request = {"limit": 3, "event_classes": ["data_operation"]}
            if after is not None:
                request["after"] = after
            result = h.service.audit_query(h.control_credential_secret, request)
            for event in result["events"]:
                if event.get("application_id") == marker:
                    seen.append(event["request_id"])
                after = event["cursor"]
            time.sleep(0.05)

        writer_thread.join(timeout=10)
        assert not writer_thread.is_alive(), "writer thread did not finish in time"

        # Catch-up phase: past visibility lag, so anything the concurrent
        # phase missed (written too close to the last poll to be visible
        # yet) is guaranteed to surface here.
        _wait_for_visibility(h)
        for _ in range(50):
            request = {"limit": 3, "event_classes": ["data_operation"]}
            if after is not None:
                request["after"] = after
            result = h.service.audit_query(h.control_credential_secret, request)
            if not result["events"]:
                break
            for event in result["events"]:
                if event.get("application_id") == marker:
                    seen.append(event["request_id"])
                after = event["cursor"]

        assert len(seen) == len(set(seen)) == total_rows, f"{kind}: expected {total_rows} unique rows, got {seen!r} (len={len(seen)})"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_invalid_cursor_is_validation_failed(kind, platform):
    h = _build_harness(kind, platform)
    try:
        with pytest.raises(FoundationError) as exc:
            h.service.audit_query(h.control_credential_secret, {"after": "not-a-real-cursor"})
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_ordering_uses_plane_as_a_tiebreaker_not_event_id_alone(kind, platform):
    """WP-2(b) review M-6 (major, supervisor ruling 2026-09-03): the total
    order is `(recorded_at, plane, event_id)` (D-6 / contract 1.4.0
    conditional obligation 2) -- `plane` must be a REAL tiebreaker, not
    incidental. Two rows are written with the IDENTICAL `recorded_at` (a
    real tie) and event_id values chosen so that comparing `event_id`
    ALONE gives the OPPOSITE order from comparing `(plane, event_id)`:
    the control-plane row's event_id sorts BELOW the application-plane
    row's, but `'application' < 'control'` lexicographically means the
    application row must still come first. If a future change drops
    `plane` from the ordering/cursor comparison (mutation M10), this
    flips and the assertion below fails.
    """
    h = _build_harness(kind, platform)
    try:
        marker = "planeorder" + secrets.token_hex(4)
        tied_at = datetime.now(timezone.utc) - timedelta(seconds=5)  # safely older than any harness's visibility lag
        control_event_id = "00000000-0000-0000-0000-000000000000"  # smallest possible event_id
        application_event_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"  # largest possible event_id
        _write_control_audit_row(h, event_id=control_event_id, request_id=f"{marker}-control", recorded_at=tied_at)
        _write_application_audit_row_with_identity(h, event_id=application_event_id, request_id=f"{marker}-application", recorded_at=tied_at)
        _wait_for_visibility(h)

        result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
        matched = [e for e in result["events"] if e.get("request_id", "").startswith(marker)]
        assert len(matched) == 2, f"expected exactly the 2 probe rows, got {matched!r}"
        assert [e["plane"] for e in matched] == ["application", "control"], (
            f"expected the application-plane row before the control-plane row despite its event_id sorting "
            f"higher -- plane is not acting as the tiebreaker: {matched!r}"
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_cursor_boundary_on_identical_cross_table_event_id_has_no_loss_stall_or_duplicate(kind, platform):
    """WP-2(b) fix round 2 (coordinator item F). M-6's own named "壊れる
    シナリオ": `control_audit` and `application_audit` rows sharing the
    SAME `event_id` (each table's own PK guarantees uniqueness only
    WITHIN itself, never across the UNION, design D-6 / review M-10(b)),
    placed EXACTLY at a cursor boundary (identical `recorded_at` too) --
    the first row's own `cursor` is fed back as `after`, and the second
    row (same event_id, different plane) must still come back exactly
    once: no loss, no stall (infinite-loop-shaped: repeating the same
    `after` returns the same nothing forever), no duplicate.
    """
    h = _build_harness(kind, platform)
    try:
        marker = "sameid" + secrets.token_hex(4)
        tied_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        shared_event_id = str(uuid.uuid4())
        _write_control_audit_row(h, event_id=shared_event_id, request_id=f"{marker}-control", recorded_at=tied_at)
        _write_application_audit_row_with_identity(h, event_id=shared_event_id, request_id=f"{marker}-application", recorded_at=tied_at)
        _wait_for_visibility(h)

        # `platform`/the in-memory harness's sinks are shared across every
        # test in this module (module-scoped fixture) -- a bare `limit: 1`
        # with no filter would return whatever the globally-oldest visible
        # row happens to be, not necessarily either probe row. Filtering by
        # marker prefix (the same defensive pattern `test_ordering_uses_
        # plane_as_a_tiebreaker_not_event_id_alone` and the cursor-walk
        # parity test already use) is what makes this reliable regardless
        # of other tests' own residue.
        baseline = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
        matched_baseline = [e for e in baseline["events"] if e.get("request_id", "").startswith(marker)]
        assert len(matched_baseline) == 2, f"expected exactly the 2 probe rows, got {matched_baseline!r}"
        # (plane, event_id) is the real tiebreaker at a tied recorded_at --
        # 'application' < 'control' lexicographically, so the application
        # row is first regardless of the (here, identical) event_id.
        assert [e["request_id"] for e in matched_baseline] == [f"{marker}-application", f"{marker}-control"]
        assert matched_baseline[0]["event_id"] == matched_baseline[1]["event_id"] == shared_event_id
        first_event, second_event = matched_baseline

        second_page = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "after": first_event["cursor"]})
        matched_second = [e for e in second_page["events"] if e.get("request_id", "").startswith(marker)]
        assert len(matched_second) == 1, f"expected exactly the control-plane row (same event_id) once, got {matched_second!r}"
        assert matched_second[0]["request_id"] == f"{marker}-control"
        assert matched_second[0]["event_id"] == shared_event_id
        assert matched_second[0]["cursor"] == second_event["cursor"]

        # No stall: re-querying with the SECOND row's own cursor never
        # returns either probe row again (never loops back to the same
        # position).
        third_page = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "after": matched_second[0]["cursor"]})
        assert not any(e.get("request_id", "").startswith(marker) for e in third_page["events"]), (
            "a query past the second row's own cursor must never return either probe row again"
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_application_audit_rows_always_read_back_as_plane_application(kind, platform):
    """m-2: `plane` is derived from the source table, never a stored
    column -- even a row whose OTHER fields try to look like a control-
    plane event still reads back `plane="application"` because it was
    inserted through the application-plane sink."""
    h = _build_harness(kind, platform)
    try:
        marker = "planecheck" + secrets.token_hex(4)
        _write_application_audit_row(h, event_class="control_credential_lifecycle", request_id=marker, application_id=marker)
        _wait_for_visibility(h)
        result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
        matches = [e for e in result["events"] if e.get("request_id") == marker]
        assert len(matches) == 1
        assert matches[0]["plane"] == "application"
    finally:
        h.cleanup()


def _run_delayed_tx_vector(h: types.SimpleNamespace, *, dsn: str, table: str, insert_sql: str, marker: str) -> None:
    """WP-2(b) fix round 2 (coordinator ruling, item A): a SMALL, test-
    friendly lag (harness timeouts set to 1000ms/1000ms -> lag ~3s) and a
    hold time LONGER than the lag (`lag_s + 0.5`) -- the two properties
    that make the "row not yet visible" assertion below GENUINELY load-
    bearing, not merely restating the visibility-lag threshold:

    The probe below runs at `lag_s + 0.2` after the INSERT -- PAST the
    naive `recorded_at < now() - lag` threshold -- while the writer
    transaction is (by construction, `hold_s > lag_s + 0.2`) still
    demonstrably open. If a future change removed the hold (mutated to an
    immediate commit), the row would already be committed AND would
    already satisfy the threshold at this exact probe point, so it WOULD
    appear -- flipping this assertion to red. What is actually being
    proven here is that MVCC invisibility, not the threshold alone, is
    still doing real work at this boundary; a fixed `sleep` alone (with no
    real transaction hold) cannot make this assertion fail, so a hold that
    silently stopped holding would be caught here.
    """
    lag_s = h.service._audit_visibility_lag_ms / 1000  # noqa: SLF001
    hold_s = lag_s + 0.5
    probe_at_s = lag_s + 0.2
    assert probe_at_s < hold_s, "test's own timing assumption (probe before commit) does not hold"

    result_holder: dict = {}
    start = time.monotonic()

    def _hold_and_write() -> None:
        conn = psycopg.connect(dsn, autocommit=False)
        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL(insert_sql).format(table=sql.Identifier(h.platform.schema, table)), [marker])
            time.sleep(hold_s)
            conn.commit()
        finally:
            conn.close()
        result_holder["done"] = True

    writer = threading.Thread(target=_hold_and_write)
    writer.start()

    time.sleep(max(0.0, probe_at_s - (time.monotonic() - start)))
    assert writer.is_alive(), "writer already finished before the load-bearing probe point -- hold_s must exceed probe_at_s"
    probe = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
    assert not any(e.get("request_id") == marker for e in probe["events"]), (
        "the row became visible before its writer transaction committed -- "
        "this is the load-bearing assertion (see this helper's own docstring)"
    )

    writer.join(timeout=10)
    assert result_holder.get("done"), "writer thread did not finish in time"
    time.sleep(0.5)  # margin past commit
    after_commit = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
    assert any(e.get("request_id") == marker for e in after_commit["events"]), (
        "the delayed row never became visible through audit_query after its writer transaction committed"
    )


def test_control_audit_row_from_a_delayed_control_tx_returns_on_the_next_page(platform):
    """D-6 (review N-3): a control-plane state-change transaction held open
    LONGER than the derived visibility lag still surfaces its `control_
    audit` row once it commits -- never permanently skipped. Small,
    test-friendly timeouts (1000ms/1000ms -> lag ~3s) keep this fast
    (coordinator ruling, item A: previously 60000ms/2000ms -> lag 63s with
    a hold capped at 1.8s, which made the load-bearing assertion vacuous)."""
    h = _postgres_harness(platform, audit_statement_timeout_ms=1000, audit_idle_timeout_ms=1000)
    try:
        marker = "delayedctl" + secrets.token_hex(4)
        _run_delayed_tx_vector(
            h, dsn=h.platform.control_dsn, table="control_audit", marker=marker,
            insert_sql=(
                "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, "
                "operation, target_kind, outcome) VALUES (gen_random_uuid(), 'authorization_denial', "
                "now(), %s, 'control_credential', 'audit_query', 'control_credential', 'deny')"
            ),
        )
    finally:
        h.cleanup()


def test_writer_tx_held_near_the_lag_still_returns_on_the_next_page(platform):
    """Same vector as above, application plane (`application_audit`)."""
    h = _postgres_harness(platform, audit_statement_timeout_ms=1000, audit_idle_timeout_ms=1000)
    try:
        marker = "delayedapp" + secrets.token_hex(4)
        _run_delayed_tx_vector(
            h, dsn=h.platform.api_dsn, table="application_audit", marker=marker,
            insert_sql=(
                "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, actor_type, "
                "operation, target_kind, outcome) VALUES (gen_random_uuid(), 'data_operation', now(), "
                "%s, 'application_credential', 'query', 'entity', 'allow')"
            ),
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_in_memory_and_postgres_audit_query_semantics_have_parity(kind, platform):
    """D-10: order, event_classes filter, limit, and cursor round-tripping
    behave identically on both backends.

    WP-2(b) review m-2 (supervisor ruling 2026-09-03): the docstring used
    to claim "cursor round-tripping" while the body only ever exercised
    filter/unknown-class/limit -- now genuinely exercised below (a
    `limit=1` walk through the 3 marker rows via repeated `after`, and an
    explicit exclusive-boundary check: re-querying with a given event's own
    `cursor` never returns that same event again). Cross-plane total order
    itself (the `plane` tiebreaker) is NOT re-tested here -- that is
    `test_ordering_uses_plane_as_a_tiebreaker_not_event_id_alone`'s own,
    more targeted job; this test's job is confirming the two BACKENDS agree
    with each other on cursor/order/filter/limit, not re-deriving the
    ordering property itself.
    """
    h = _build_harness(kind, platform)
    try:
        marker = "parity" + secrets.token_hex(4)
        for i, cls in enumerate(["data_operation", "privilege_sensitive", "data_operation"]):
            _write_application_audit_row(h, event_class=cls, request_id=f"{marker}-{i}", application_id=marker)
        _wait_for_visibility(h)

        only_data_ops = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "event_classes": ["data_operation"]})
        matched = [e for e in only_data_ops["events"] if e.get("application_id") == marker]
        assert len(matched) == 2 and all(e["event_class"] == "data_operation" for e in matched)

        unknown_class = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "event_classes": ["no_such_class_at_all"]})
        assert not any(e.get("application_id") == marker for e in unknown_class["events"])

        limited = h.service.audit_query(h.control_credential_secret, {"limit": 1})
        assert len(limited["events"]) <= 1

        # Cursor round-tripping: walk the 3 marker rows one at a time via
        # repeated `after`, using each page's own last `cursor` as the next
        # request's `after` -- the real client-side pagination protocol
        # (D-6 completeness_note), never `limit=1000` in one shot.
        walked: list[str] = []
        after: str | None = None
        # Generous iteration bound: `platform`/the in-memory harness's
        # sinks are shared across every test in this module (module-scoped
        # fixture), so unrelated rows from other tests can legitimately
        # interleave chronologically -- `after` is advanced on EVERY row
        # returned (relevant or not), never only on a marker match, or an
        # interleaved unrelated row would stall the walk without ever
        # reaching the 3 marker rows.
        for _ in range(200):
            request = {"limit": 1, "event_classes": ["data_operation", "privilege_sensitive"]}
            if after is not None:
                request["after"] = after
            page = h.service.audit_query(h.control_credential_secret, request)
            if not page["events"]:
                break
            event = page["events"][0]
            after = event["cursor"]
            if event.get("application_id") == marker:
                walked.append(event["request_id"])
                if len(walked) == 3:
                    break
        assert walked == [f"{marker}-0", f"{marker}-1", f"{marker}-2"], f"{kind}: cursor walk did not recover all 3 rows in order: {walked!r}"

        # Exclusive boundary: re-querying with the FIRST row's own cursor
        # as `after` must never return that same row again.
        first_cursor = None
        for event in only_data_ops["events"]:
            if event.get("application_id") == marker:
                first_cursor = event["cursor"]
                break
        assert first_cursor is not None
        after_first = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "after": first_cursor})
        assert not any(e.get("request_id") == f"{marker}-0" for e in after_first["events"]), (
            f"{kind}: after= must be exclusive -- the cursor's own event reappeared"
        )
    finally:
        h.cleanup()


# ===========================================================================
# D-5: authority, capability-unsupported, declared event_classes.
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_control_and_audit_credentials_are_accepted_on_audit_query(kind, platform):
    h = _build_harness(kind, platform)
    try:
        result = h.service.audit_query(h.control_credential_secret, {"limit": 1})
        assert "events" in result

        audit_id = "ctl_" + secrets.token_hex(8)
        audit_secret = "audit-role-" + secrets.token_urlsafe(8)
        h.seed_audit_credential(audit_id, audit_secret)
        audit_result = h.service.audit_query(compose_bearer_locator(audit_id, audit_secret), {"limit": 1})
        assert "events" in audit_result
    finally:
        h.cleanup()


def test_audit_query_without_audit_dsn_refuses_with_capability_unsupported_not_404():
    """D-5 M-4: no reader configured -- the SERVICE method (not an HTTP
    404) answers `CAPABILITY_UNSUPPORTED` for a genuinely authenticated
    caller."""
    credentials = CredentialStore(pepper=APP_PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    audit = ControlAuditSink()
    service = ControlPlaneService(backend, audit=audit, limits=_GENEROUS_LIMITS)  # no audit_reader
    credential_id = "ctl_" + secrets.token_hex(8)
    secret = "no-audit-dsn-" + secrets.token_urlsafe(8)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(credential_id, secret, work=work)
        control_credentials.rotate(credential_id, secret, work=work)

    with pytest.raises(FoundationError) as exc:
        service.audit_query(compose_bearer_locator(credential_id, secret), {"limit": 1})
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"

    document = service.capabilities(compose_bearer_locator(credential_id, secret))
    assert document["capabilities"]["audit_query"] == {"status": "unavailable"}

    # WP-2(b) fix round 2 (coordinator item G): contract 1.4.0 unconditional
    # obligation (b)'s own literal combination -- "an unavailable audit_
    # query still answers an AUTHORIZED AUDIT-ROLE caller with CAPABILITY_
    # UNSUPPORTED" -- the case above used a control credential; an audit
    # credential must reach the identical outcome, never FORBIDDEN (the
    # role IS authorized for this operation, `_AUDIT_ROLE_ALLOWED_
    # OPERATIONS`) and never a 404-shaped answer.
    audit_credential_id = "ctl_" + secrets.token_hex(8)
    audit_secret = "no-audit-dsn-role-audit-" + secrets.token_urlsafe(8)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(audit_credential_id, audit_secret, role="audit", work=work)
        control_credentials.rotate(audit_credential_id, audit_secret, work=work)
    with pytest.raises(FoundationError) as exc:
        service.audit_query(compose_bearer_locator(audit_credential_id, audit_secret), {"limit": 1})
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.code not in ("FORBIDDEN", "NOT_FOUND")


# WP-2(b) review M-3 (major, supervisor ruling 2026-09-03): a regex over
# `event_class="..."` misses every POSITIONAL call site -- this AST-based
# scanner extracts the real literal from every real emission call site,
# the same way `test_limit_class_vocabulary.py`'s own AST scan fixes
# `limit_class` against real call sites rather than trusting a regex.
#
# WP-B1 (P4-D16 v3, docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md
# §1/§4): this whole block was rewritten from a CALLEE-NAME-KEYED scan
# (`_EVENT_CLASS_CALL_SPECS`, a hand-maintained `{name: ("positional"|
# "keyword", index)}` map a human had to keep in sync with every real
# emission call site -- exactly the class of gap L4-5's diagnostic found)
# to FOUR independent, callee-name-FILTER-FREE checks that together close
# every literal-hiding path a human-maintained spec could silently miss:
#
#   (a) `_iter_src_files()` -- every `*.py` under `src/r2db_api/`, found by
#       a RECURSIVE `rglob` (never a hardcoded file list, never a
#       non-recursive top-level-only `glob`).
#   (b) literal discipline (`test_every_event_class_keyword_argument_is_a_
#       string_literal`) -- every `Call` ANYWHERE in the package that
#       carries an `event_class=` keyword must pass a string `Constant`,
#       or be the one recognized parameter-forward shape (`event_class=
#       event_class`, an enclosing function forwarding its OWN parameter
#       verbatim). No callee-name filter at all.
#   (c) definition-side keyword-only guarantee (`test_every_definition_
#       taking_event_class_declares_it_keyword_only`) -- every `def`/
#       `async def` anywhere under `src/r2db_api/` whose formal parameters
#       include `event_class` must declare it AFTER a bare `*` (keyword-
#       only). This makes a POSITIONALLY-PASSED emit site syntactically
#       impossible to write -- (b)'s literal scan can never be bypassed by
#       positional passing, because nothing compiles that way any more.
#   (d) dict-smuggling ban (`test_no_event_class_string_literal_is_
#       smuggled_through_a_dict`) -- no `{"event_class": "<literal>"}`
#       dict literal or `x["event_class"] = "<literal>"` subscript
#       assignment anywhere in the package (a `**{"event_class": ...}`
#       expansion would otherwise let a literal bypass (b)'s keyword-arg
#       walk entirely). Values that are `Name`/`Attribute` (forwards) stay
#       allowed, same rule as (b).
#   (e) exact vocabulary-relation match
#       (`test_declared_event_classes_cover_every_emittable_class`) --
#       with (b) closing the callee-name blind spot, (c) closing
#       positional passing, and (d) closing dict smuggling, EVERY real
#       `event_class` literal in the package is now reachable by (b)'s own
#       walk with nothing left unaccounted for. This test computes that
#       full literal union U and requires `U == D | N` AND `D & N == set()`
#       where D is the declared vocabulary (`DECLARED_AUDIT_EVENT_CLASSES`,
#       unchanged by this WP) and N is an EXPLICIT, name-by-name,
#       rationale-commented set of literals that are real but deliberately
#       non-durable (never reach the table `audit_query` reads). A new
#       literal appearing anywhere now forces a choice -- declare it (D)
#       or name it with a reason (N) -- there is no silent third path.
#
# v2 of this WP ("three-way match": a name-derived "emit definition set"
# cross-checked against call sites) was PROPOSED AND WITHDRAWN before
# implementation -- round-1 independent review found it cannot go green
# against the real codebase: (i) `append` (the durable sinks' own keyword-
# only `event_class` parameter) would enter the definition set and flag
# EVERY unrelated `list.append()` call in the package (36 in r2db, 46 in
# MitateDB) as a violation; (ii) MitateDB's `control_audit` writes route
# through forwarding wrappers (`append_audit(**fields)`) that never
# themselves declare `event_class` as a parameter, so 13 real emit sites
# would register as "unknown emit surfaces"; (iii) r2db's `_control_event`
# carries two literals (`control_failure`/`control_state`) that are real
# but reach ONLY the legacy in-memory sink, never the durable table -- v2
# had no way to represent "real but intentionally undeclared" other than
# adding them to `DECLARED_AUDIT_EVENT_CLASSES`, which would have made
# `audit_query`'s own declaration lie about what it can return. (b)-(e)
# above route around all three: no definition SET is ever cross-matched
# against callee names at all (closing i/ii), and N gives (iii) a
# principled, explicit home instead of the declared vocabulary.
import ast as _ast  # noqa: E402 -- kept local to this test-support block, mirrors this file's own late-import style

# Phase 5 WP-2 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
# D-1, work order docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md
# WP-2 変更対象 C): P4-D16 v3's own (a)-(e) block above this comment
# described a scanner hardcoded to the single field `event_class`. This WP
# generalizes that SAME "global invariant" method (never the withdrawn
# "resolve every call site's value" method -- design §3 D-1 explicitly
# rejects that alternative) by PARAMETERIZING every rule over a field name,
# and adds exactly three new rules the generalization itself makes
# necessary (design's own accounting -- `event_class`'s emit surface is
# uniformly keyword-only in this package, so these gaps never showed up for
# it):
#
#   (b') `IfExp` values (`"enable_application" if enabled else
#        "disable_application"`) are recognized -- allowed when BOTH
#        branches are themselves string `Constant`s (or nested `IfExp`s
#        that reduce the same way), contributing every `Constant` leaf to
#        U. Applies at BOTH the keyword-argument-value position and the
#        (name-assignment-only, see (b'') below) assignment-value position.
#   (b'') A `Name` reference to a variable BOUND, in its own direct scope,
#        by exactly ONE binding form -- a single-target `Assign` (`<field>
#        = ...`) whose value is a string `Constant` or (b')-recognized
#        `IfExp` -- is treated as a safe forward, on par with an enclosing
#        function's own `<field>` parameter, closure-crossing included.
#        ANY other binding form for that name in the same scope (a second
#        assignment, a `for`/`with-as`/`except-as`/walrus/`match-as`/
#        `global`/`nonlocal`, or a same-named nested `def`/`class`) forfeits
#        the exemption -- the name reverts to being a plain, non-forward
#        local, exactly as P4-D16 v3's original shadow rule already treated
#        every other local variable.
#   (b''') Read-path passthrough (`.{field}` `Attribute` / `["{field}"]`
#        `Subscript`) is allowed ONLY at a dict-literal value, a subscript-
#        assignment value (`x["{field}"] = ...`), or an attribute-
#        assignment value (`obj.{field} = ...`) -- NEVER at a `{field}=`
#        keyword-argument-value position. Closes a hole the generalization
#        itself opens: a request body can genuinely carry a key literally
#        named `"operation"` (MitateDB's `http.py`, WP-3), so an unrestricted
#        `foo(operation=body["operation"])` would let client-supplied text
#        reach a durable audit column unlit by (b)'s own literal-discipline
#        scan or by U. Verified (design N-6): every real read-path site in
#        THIS peer already uses the dict-literal form, so (b''') requires
#        zero product-code changes here.
#
# `_FIELDS` below is the pinned set this whole block is parameterized over
# -- `test_scanner_is_parameterized_over_exactly_these_three_fields` fixes
# its CONTENT directly (a scanner silently narrowed back down to `event_
# class` alone would go undetected by every other test in this block, since
# every rule's own violation collectors would simply never be called for
# the missing field(s)).
_FIELDS: tuple[str, ...] = ("event_class", "operation", "target_kind")

_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "r2db_api"


def test_scanner_is_parameterized_over_exactly_these_three_fields() -> None:
    """Pins `_FIELDS` directly (WP-2 変更対象 C, 監督裁定 2026-09-04 --
    an explicit發注項目, not implementer discretion). Mutation 9: drop
    `target_kind` from this tuple and every rule test below silently stops
    exercising it -- this test is the only thing that turns that into a
    failure."""
    assert _FIELDS == ("event_class", "operation", "target_kind")


def _iter_src_files() -> list[Path]:
    """Every `*.py` file anywhere under `src/r2db_api/`, found by a
    RECURSIVE `rglob` -- P4-D16 v3(a): a hand-maintained file list, and a
    non-recursive top-level-only `glob`, are both banned by design. Shared,
    unparameterized -- unchanged by this WP."""
    return sorted(_SRC_DIR.rglob("*.py"))


def _literal_leaves(node: "_ast.AST") -> set[str]:
    """(b) + (b'): every string `Constant` leaf reachable from `node`
    through zero or more `IfExp` layers whose branches are BOTH themselves
    recognized this same way -- an `IfExp` with even one non-Constant,
    non-fully-reducible branch contributes NOTHING (the whole expression
    then falls through to being treated as a plain unresolved value, not
    as a partial literal source) -- this is what makes mutation 3 (one
    branch replaced by an undeclared-but-still-Constant word) detectable
    by the (e) equality rather than swallowed silently at this layer."""
    if isinstance(node, _ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, _ast.IfExp):
        left = _literal_leaves(node.body)
        right = _literal_leaves(node.orelse)
        if left and right:
            return left | right
        return set()
    return set()


def _iter_name_or_attribute_targets(target: "_ast.AST"):
    """WP-B1 acceptance-audit finding M7: decomposes an assignment TARGET
    (including tuple/list/starred unpacking) into every leaf `Name`/
    `Attribute` node it assigns to. `Subscript` targets are NOT decomposed
    here -- the dict-smuggling scan handles those separately. Unchanged by
    this WP (already field-agnostic)."""
    if isinstance(target, (_ast.Name, _ast.Attribute)):
        yield target
    elif isinstance(target, (_ast.Tuple, _ast.List)):
        for elt in target.elts:
            yield from _iter_name_or_attribute_targets(elt)
    elif isinstance(target, _ast.Starred):
        yield from _iter_name_or_attribute_targets(target.value)


def _is_field_assignment_target(leaf: "_ast.AST", field: str) -> bool:
    if isinstance(leaf, _ast.Name):
        return leaf.id == field
    if isinstance(leaf, _ast.Attribute):
        return leaf.attr == field
    return False


def _collect_direct_shadow_names(body: list, field: str) -> set[str]:
    """Generalized P4-D16 v3 acceptance-audit-round-2 shadow detector: any
    name binding of `field` anywhere in a function's OWN direct body (never
    descending into a nested `def`/`async def`/`lambda`/`class`) shadows
    it -- every binding SHAPE `_analyze_field_scope` below also enumerates
    for its own, narrower (b'') purpose, kept here as the plain yes/no
    "is this name local to this scope at all" question the forward
    resolver needs first."""
    shadowed: set[str] = set()

    class _ShadowScan(_ast.NodeVisitor):
        def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
            if node.name == field:
                shadowed.add(node.name)

        def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
            if node.name == field:
                shadowed.add(node.name)

        def visit_Lambda(self, node: "_ast.Lambda") -> None:
            pass  # separate scope; do not descend

        def visit_ClassDef(self, node: "_ast.ClassDef") -> None:
            if node.name == field:
                shadowed.add(node.name)

        def visit_Name(self, node: "_ast.Name") -> None:
            if node.id == field and isinstance(node.ctx, (_ast.Store, _ast.Del)):
                shadowed.add(node.id)

        def visit_alias(self, node: "_ast.alias") -> None:
            if node.asname == field:
                shadowed.add(node.asname)

        def visit_ExceptHandler(self, node: "_ast.ExceptHandler") -> None:
            if node.name == field:
                shadowed.add(node.name)
            self.generic_visit(node)

        def visit_MatchAs(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == field:
                shadowed.add(field)
            self.generic_visit(node)

        def visit_MatchStar(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == field:
                shadowed.add(field)
            self.generic_visit(node)

        def visit_MatchMapping(self, node: "_ast.AST") -> None:
            if getattr(node, "rest", None) == field:
                shadowed.add(field)
            self.generic_visit(node)

        def visit_Global(self, node: "_ast.Global") -> None:
            shadowed.update(n for n in node.names if n == field)

        def visit_Nonlocal(self, node: "_ast.Nonlocal") -> None:
            shadowed.update(n for n in node.names if n == field)

    scanner = _ShadowScan()
    for stmt in body:
        scanner.visit(stmt)
    return shadowed


def _analyze_field_scope(body: list, field: str) -> tuple[set[str], "_ast.AST | None"]:
    """(b''): returns `(shadow_names, const_bound_value_or_None)` for
    `field` within one function's own DIRECT body (same non-descent rule as
    `_collect_direct_shadow_names`). `const_bound_value` is set ONLY when
    `field`'s SOLE binding touch anywhere in this direct body is a single-
    target `Assign` (`field = ...`, never `AnnAssign`/`AugAssign`, never a
    tuple/attribute/subscript target) whose value satisfies `_literal_
    leaves` -- ANY other touch (a second assign of any shape, a for/with-
    as/except-as/walrus/match-as/global/nonlocal, or a same-named nested
    def/class) forfeits the exemption entirely, even if this qualifying
    assign is also present."""
    touches: list[tuple[str, "_ast.AST | None"]] = []

    class _Scan(_ast.NodeVisitor):
        def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
            if node.name == field:
                touches.append(("other", None))

        def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
            if node.name == field:
                touches.append(("other", None))

        def visit_Lambda(self, node: "_ast.Lambda") -> None:
            pass  # separate scope; do not descend

        def visit_ClassDef(self, node: "_ast.ClassDef") -> None:
            if node.name == field:
                touches.append(("other", None))

        def visit_Assign(self, node: "_ast.Assign") -> None:
            if len(node.targets) == 1 and isinstance(node.targets[0], _ast.Name) and node.targets[0].id == field:
                touches.append(("assign", node.value))
            else:
                for target in node.targets:
                    for leaf in _iter_name_or_attribute_targets(target):
                        if isinstance(leaf, _ast.Name) and leaf.id == field:
                            touches.append(("other", None))
            self.visit(node.value)

        def visit_Name(self, node: "_ast.Name") -> None:
            if node.id == field and isinstance(node.ctx, (_ast.Store, _ast.Del)):
                touches.append(("other", None))

        def visit_alias(self, node: "_ast.alias") -> None:
            if node.asname == field:
                touches.append(("other", None))

        def visit_ExceptHandler(self, node: "_ast.ExceptHandler") -> None:
            if node.name == field:
                touches.append(("other", None))
            self.generic_visit(node)

        def visit_MatchAs(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == field:
                touches.append(("other", None))
            self.generic_visit(node)

        def visit_MatchStar(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == field:
                touches.append(("other", None))
            self.generic_visit(node)

        def visit_MatchMapping(self, node: "_ast.AST") -> None:
            if getattr(node, "rest", None) == field:
                touches.append(("other", None))
            self.generic_visit(node)

        def visit_Global(self, node: "_ast.Global") -> None:
            if field in node.names:
                touches.append(("other", None))

        def visit_Nonlocal(self, node: "_ast.Nonlocal") -> None:
            if field in node.names:
                touches.append(("other", None))

    scanner = _Scan()
    for stmt in body:
        scanner.visit(stmt)

    if not touches:
        return set(), None
    if len(touches) == 1 and touches[0][0] == "assign" and _literal_leaves(touches[0][1]):
        return {field}, touches[0][1]
    return {field}, None


class _FieldForwardResolver(_ast.NodeVisitor):
    """Generalized `_EventClassForwardResolver`: a single, scope-tracking
    traversal determining, for every `Name(id=field, ctx=Load())` node,
    whether it is a genuine forward -- either of an ENCLOSING function's own
    `field` formal parameter (unchanged from P4-D16 v3), OR (b'') of a
    same-scope-or-enclosing-scope local variable bound by exactly one
    qualifying constant-or-`IfExp`-of-constants `Assign`. A name that is
    locally shadowed in the innermost scope that claims it, WITHOUT
    qualifying for (b''), stops resolution there and is never a safe
    forward -- identical in spirit to P4-D16 v3's own shadow rule, just
    with one narrow, mechanically-verified exception carved out."""

    def __init__(self, field: str) -> None:
        self.field = field
        self.safe_forward_ids: set[int] = set()
        self._stack: list[tuple[set[str], set[str], "_ast.AST | None"]] = []

    def _param_names(self, node: "_ast.AST") -> set[str]:
        args = node.args
        names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)}
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
        return names

    def _push_and_visit(self, node: "_ast.AST") -> None:
        shadow_names, const_bound = _analyze_field_scope(node.body, self.field)
        self._stack.append((self._param_names(node), shadow_names, const_bound))
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
        self._push_and_visit(node)

    def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
        self._push_and_visit(node)

    def visit_Lambda(self, node: "_ast.Lambda") -> None:
        self._stack.append((self._param_names(node), set(), None))
        self.generic_visit(node)
        self._stack.pop()

    def visit_Name(self, node: "_ast.Name") -> None:
        if node.id == self.field and isinstance(node.ctx, _ast.Load):
            for param_names, shadow_names, const_bound in reversed(self._stack):
                if self.field in shadow_names:
                    if const_bound is not None:
                        self.safe_forward_ids.add(id(node))
                    break  # locally rebound in this scope -- resolution stops here either way
                if self.field in param_names:
                    self.safe_forward_ids.add(id(node))
                    break
        self.generic_visit(node)


def _scan_source_field_sites(source: str, filename: str, field: str) -> tuple[
    list[tuple[int, "_ast.AST", bool]], list[tuple[int, str, "_ast.AST", bool]], list[tuple[int, str, "_ast.AST", bool]]
]:
    """Generalized `_scan_source_event_class_sites`. One parse, one
    `_FieldForwardResolver` pass. Returns `(keyword_sites, dict_sites,
    assignment_sites)`, each `(..., value_node, ok)`:

    - `keyword_sites`: every `Call` carrying a `field=` keyword. `ok` is
      True for a `_literal_leaves`-bearing value ((b)/(b') -- literal
      AUTHORSHIP is legal only here) or a safe `Name` forward. `Attribute`/
      `Subscript` are NEVER `ok` here (b''' -- no read-path passthrough at
      a keyword-value position).
    - `dict_sites`: every `Dict` literal keyed `field` (`kind="dict"`) and
      every `x["field"] = ...` subscript assignment (`kind="subscript"`).
      `ok` is True ONLY for a safe `Name` forward or `Attribute`/
      `Subscript` read-path passthrough (b''') -- a literal here is NEVER
      `ok` (unchanged from P4-D16 v3 -- literal authorship must go through
      a real keyword call site, not be smuggled into a dict).
    - `assignment_sites`: every `Assign`/`AnnAssign`/`AugAssign` anywhere
      (every scope) whose target is `Name(id=field)` (`kind="name_assign"`)
      or `Attribute(attr=field)` (`kind="attribute_assign"`). `name_assign`
      additionally allows `_literal_leaves` values `ok` (b''/b' -- this is
      the exact shape the (b'') exemption's OWN qualifying assignment
      takes, e.g. `operation = "enable_application" if enabled else
      "disable_application"`; a plain string `Constant` there is likewise
      `ok`, on par with a fully-reduced `IfExp`). `attribute_assign` never
      allows a bare literal (`self.field = "literal"` stays banned, same as
      P4-D16 v3) but DOES allow `Attribute`/`Subscript` read-path
      passthrough (b''').
    """
    tree = _ast.parse(source, filename=filename)
    resolver = _FieldForwardResolver(field)
    resolver.visit(tree)
    safe_ids = resolver.safe_forward_ids

    def is_ok(value: "_ast.AST", *, position: str) -> bool:
        if position in ("keyword", "name_assign") and _literal_leaves(value):
            return True
        if isinstance(value, _ast.Name):
            return id(value) in safe_ids
        if position in ("dict", "subscript", "attribute_assign"):
            if isinstance(value, _ast.Attribute):
                return value.attr == field
            if isinstance(value, _ast.Subscript):
                key_node = value.slice
                return isinstance(key_node, _ast.Constant) and key_node.value == field
        return False

    keyword_sites: list[tuple[int, "_ast.AST", bool]] = []
    dict_sites: list[tuple[int, str, "_ast.AST", bool]] = []
    assignment_sites: list[tuple[int, str, "_ast.AST", bool]] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            kw = next((k for k in node.keywords if k.arg == field), None)
            if kw is not None:
                keyword_sites.append((node.lineno, kw.value, is_ok(kw.value, position="keyword")))
        elif isinstance(node, _ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, _ast.Constant) and key.value == field:
                    dict_sites.append((node.lineno, "dict", value, is_ok(value, position="dict")))
        elif isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Subscript):
                    key_node = target.slice
                    if isinstance(key_node, _ast.Constant) and key_node.value == field:
                        dict_sites.append((node.lineno, "subscript", node.value, is_ok(node.value, position="subscript")))
                for leaf in _iter_name_or_attribute_targets(target):
                    if _is_field_assignment_target(leaf, field):
                        kind = "name_assign" if isinstance(leaf, _ast.Name) else "attribute_assign"
                        assignment_sites.append((node.lineno, kind, node.value, is_ok(node.value, position=kind)))
        elif isinstance(node, (_ast.AnnAssign, _ast.AugAssign)):
            if node.value is None:
                continue
            for leaf in _iter_name_or_attribute_targets(node.target):
                if _is_field_assignment_target(leaf, field):
                    kind = "name_assign" if isinstance(leaf, _ast.Name) else "attribute_assign"
                    assignment_sites.append((node.lineno, kind, node.value, is_ok(node.value, position=kind)))
    return keyword_sites, dict_sites, assignment_sites


def _scan_file_field_sites(path: Path, field: str):
    return _scan_source_field_sites(path.read_text(), path.name, field)


def _field_keyword_call_sites(paths: list[Path], field: str) -> list[tuple[str, int, "_ast.AST", bool]]:
    """(b)'s own input, aggregated across files: `(filename, lineno,
    value_node, ok)` for every `Call` anywhere in the given files carrying
    a `field=` keyword -- UNFILTERED by callee name."""
    sites: list[tuple[str, int, "_ast.AST", bool]] = []
    for path in paths:
        keyword_sites, _dict_sites, _assignment_sites = _scan_file_field_sites(path, field)
        for lineno, value, ok in keyword_sites:
            sites.append((path.name, lineno, value, ok))
    return sites


def _scan_field_literals(source: str, filename: str, field: str) -> tuple[set[str], list[str]]:
    """Single-file variant kept for the `ops.py`-specific regression tests
    and this WP's own synthetic-source tests. Returns `(literals,
    unresolved)`."""
    keyword_sites, _dict_sites, _assignment_sites = _scan_source_field_sites(source, filename, field)
    literals: set[str] = set()
    unresolved: list[str] = []
    for lineno, value, ok in keyword_sites:
        leaves = _literal_leaves(value)
        if leaves:
            literals |= leaves
        elif ok:
            continue
        else:
            unresolved.append(f"{filename}:{lineno}")
    return literals, unresolved


def _field_literal_union(paths: list[Path], field: str) -> set[str]:
    """The full literal union U for `field` across `paths` -- every
    `_literal_leaves`-bearing value found at a keyword-argument position
    (b/b'), PLUS every one found at a `name_assign` position (b''/b') --
    the latter is what lets a (b'')-qualifying local-variable assignment
    (e.g. `operation = "enable_application" if enabled else "disable_
    application"`) contribute its own literals to U even though the
    keyword site that FORWARDS that variable contributes none itself (the
    literal's true origin is the assignment, not the forward)."""
    literals: set[str] = set()
    for path in paths:
        keyword_sites, _dict_sites, assignment_sites = _scan_file_field_sites(path, field)
        for _lineno, value, _ok in keyword_sites:
            literals |= _literal_leaves(value)
        for _lineno, kind, value, _ok in assignment_sites:
            if kind == "name_assign":
                literals |= _literal_leaves(value)
    return literals


def _iter_field_definitions(paths: list[Path], field: str) -> list[tuple[str, Path, "_ast.AST", bool]]:
    """P4-D16 v3(c)'s own definition-side enumeration, generalized and
    widened to also expose a QUALIFIED name (`module[.Class].function`) per
    definition -- the exclusion list (below) is keyed by this qualified
    name. Returns `(qualified_name, path, node, is_kwonly)` for every
    `def`/`async def` anywhere in the given files whose formal parameters
    include `field`, positional-or-keyword-only alike."""
    results: list[tuple[str, Path, "_ast.AST", bool]] = []
    for path in paths:
        tree = _ast.parse(path.read_text(), filename=path.name)
        class_stack: list[str] = []

        class _Walk(_ast.NodeVisitor):
            def visit_ClassDef(self, node: "_ast.ClassDef") -> None:
                class_stack.append(node.name)
                self.generic_visit(node)
                class_stack.pop()

            def _record(self, node: "_ast.AST") -> None:
                positional_names = {a.arg for a in node.args.posonlyargs + node.args.args}
                kwonly_names = {a.arg for a in node.args.kwonlyargs}
                if field in positional_names or field in kwonly_names:
                    qualified = ".".join([path.stem, *class_stack, node.name])
                    results.append((qualified, path, node, field in kwonly_names))

            def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
                self._record(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
                self._record(node)
                self.generic_visit(node)

        _Walk().visit(tree)
    return results


# WP-2 変更対象 B: regla (c) is name-BASED, not callee-name-based, so it
# reacts to every definition anywhere under `src/r2db_api/` whose formal
# parameters include `operation` -- and `operation` is not an audit-only
# word (335 identifier occurrences in this package, design §3 D-1). The 8
# definitions below all take a CLIENT-SUPPLIED mutation/schema-operation
# dict named `operation` -- never an audit field -- and keyword-only-ifying
# them would change a public/semi-public call signature (an ABC's own
# abstract signature, or `DataService.schema`'s established `service.schema
# (context, body, request_id=...)` positional-call convention, `http.py:
# 355`) for no audit-safety benefit. Each entry names its qualified
# definition and its rationale; the two validation tests immediately below
# hold this list itself accountable: (i) every entry must still resolve to
# a real `operation`-parameter definition (a renamed/removed function goes
# red here, not silently), and (ii') no excluded definition's own body may
# forward ITS OWN `operation` parameter into an audit emit call (design
# N-1 -- NOT "carries no operation= Constant at all": `DataService.schema`
# legitimately both takes this client dict AND separately authors literal
# `operation="schema"` Constants elsewhere in its own body; excluding it
# does not, and must not, hide a genuine client-value forward if one were
# ever added).
_NON_AUDIT_OPERATION_PARAMETERS: frozenset[str] = frozenset(
    {
        # Client-supplied schema-mutation dict, an ABC's own abstract
        # signature -- `operation` here is never an audit field.
        "backend.StorageBackend.apply_schema",
        "postgres.PostgresCell._apply",
        "postgres.PostgresCell.apply_schema",
        "service.DataService.schema",
        "structured.bind_mutation",
        "structured.bind_schema_operation",
        "structured.ApplicationCell._apply",
        "structured.ApplicationCell.apply_schema",
    }
)

# `event_class`/`target_kind` need no such exclusion list -- neither name
# collides with an unrelated client-supplied parameter anywhere in this
# package (`test_every_definition_taking_the_field_declares_it_keyword_
# only`'s own zero-violation result for both, WITH an empty exclusion set,
# is the proof; see that test's own assertion below).
_NON_AUDIT_FIELD_PARAMETERS: dict[str, frozenset[str]] = {
    "event_class": frozenset(),
    "operation": _NON_AUDIT_OPERATION_PARAMETERS,
    "target_kind": frozenset(),
}


def _field_positional_definitions(paths: list[Path], field: str) -> list[str]:
    """P4-D16 v3(c)'s own violation collector, generalized: every
    definition taking `field` NOT keyword-only AND not on this field's
    exclusion list."""
    exclusions = _NON_AUDIT_FIELD_PARAMETERS.get(field, frozenset())
    violations: list[str] = []
    for qualified, path, node, is_kwonly in _iter_field_definitions(paths, field):
        if is_kwonly or qualified in exclusions:
            continue
        violations.append(f"{path.name}:{node.lineno}: {node.name}(...) takes {field} positionally, not keyword-only")
    return violations


def _excluded_definition_forwards_its_own_parameter(node: "_ast.AST", field: str) -> bool:
    """(ii'): True if `node`'s own body contains a `Call` passing
    `field=<Name>` where the Name resolves to THIS definition's OWN
    `field` parameter -- a genuine client-value-into-audit-emit transfer, as
    opposed to a `Constant`/`IfExp` audit literal the same body might also,
    legitimately, author elsewhere."""
    resolver = _FieldForwardResolver(field)
    if isinstance(node, _ast.AsyncFunctionDef):
        resolver.visit_AsyncFunctionDef(node)
    else:
        resolver.visit_FunctionDef(node)
    safe_ids = resolver.safe_forward_ids
    for sub in _ast.walk(node):
        if isinstance(sub, _ast.Call):
            for kw in sub.keywords:
                if kw.arg == field and isinstance(kw.value, _ast.Name) and id(kw.value) in safe_ids:
                    return True
    return False


def _field_dict_smuggling_violations(paths: list[Path], field: str) -> list[str]:
    violations: list[str] = []
    for path in paths:
        _keyword_sites, dict_sites, _assignment_sites = _scan_file_field_sites(path, field)
        for lineno, kind, value, ok in dict_sites:
            if ok:
                continue
            violations.append(f"{path.name}:{lineno}: {kind} sets {field} to a non-allowed value ({_ast.dump(value)})")
    return violations


def _field_assignment_violations(paths: list[Path], field: str) -> list[str]:
    violations: list[str] = []
    for path in paths:
        _keyword_sites, _dict_sites, assignment_sites = _scan_file_field_sites(path, field)
        for lineno, kind, value, ok in assignment_sites:
            if ok:
                continue
            violations.append(f"{path.name}:{lineno}: {kind} sets {field} to a non-allowed value ({_ast.dump(value)})")
    return violations


@pytest.mark.parametrize("field", _FIELDS)
def test_every_field_keyword_argument_is_a_string_literal_ifexp_or_forward(field):
    """(b)/(b'). Every `Call` anywhere under `src/r2db_api/` carrying a
    `field=` keyword must pass a plain string literal, an `IfExp` reducing
    to string literals on both branches, or a genuine bound forward -- no
    callee-name filter of any kind. Violations reported by file:line."""
    paths = _iter_src_files()
    violations: list[str] = []
    for filename, lineno, value, ok in _field_keyword_call_sites(paths, field):
        if ok:
            continue
        violations.append(f"{filename}:{lineno}: {field}= is not a string literal, IfExp-of-literals, or a bound forward ({_ast.dump(value)})")
    assert not violations, f"non-literal, non-forwarded {field}= call site(s): {violations!r}"


@pytest.mark.parametrize("field", _FIELDS)
def test_every_definition_taking_the_field_declares_it_keyword_only(field):
    """(c). Every function/method anywhere under `src/r2db_api/` that takes
    `field` as a formal parameter must declare it keyword-only, UNLESS it is
    named on that field's own exclusion list (`_NON_AUDIT_FIELD_PARAMETERS`
    -- empty for `event_class`/`target_kind`, proven by this same
    assertion going green for them with nothing excluded)."""
    paths = _iter_src_files()
    violations = _field_positional_definitions(paths, field)
    assert not violations, f"definition(s) with a non-keyword-only {field} parameter: {violations!r}"


def test_non_audit_operation_parameters_exclusion_list_entries_exist():
    """(i). Every `_NON_AUDIT_OPERATION_PARAMETERS` entry must resolve to a
    real, current `operation`-parameter definition -- a renamed or removed
    function must turn this red, not silently stop being checked at all."""
    paths = _iter_src_files()
    known_qualified = {qualified for qualified, _p, _n, _kw in _iter_field_definitions(paths, "operation")}
    missing = sorted(name for name in _NON_AUDIT_OPERATION_PARAMETERS if name not in known_qualified)
    assert missing == [], f"exclusion-list entries that no longer resolve to a real operation-parameter definition: {missing!r}"
    assert _NON_AUDIT_OPERATION_PARAMETERS, "the exclusion list itself must be non-empty for this test to observe anything"


def test_event_class_and_target_kind_need_no_exclusion_list():
    """Fix-round M-4 (Opus review): completion condition 5's "除外リストが
    event_class/target_kind には不要であることも確認すること" was, before
    this test, proven only by `test_every_definition_taking_the_field_
    declares_it_keyword_only[event_class]`/`[target_kind]` going green WITH
    an empty exclusion set -- a future 1-line addition to either field's
    entry in `_NON_AUDIT_FIELD_PARAMETERS` would silently reopen (c)'s own
    escape hatch for that field without any test noticing. Pins both
    frozensets' emptiness directly."""
    assert _NON_AUDIT_FIELD_PARAMETERS["event_class"] == frozenset()
    assert _NON_AUDIT_FIELD_PARAMETERS["target_kind"] == frozenset()


def test_non_audit_operation_parameters_never_forward_their_own_parameter_into_an_emit_call():
    """(ii'). No excluded definition's own body forwards its OWN
    client-supplied `operation` parameter into an audit emit call --
    (ii), the withdrawn predecessor rule ("no Constant operation= at all
    in the body"), is deliberately NOT implemented (design N-1:
    `DataService.schema` both needs the exclusion AND legitimately authors
    `operation="schema"` literals in its own body -- (ii) cannot go green
    against the real codebase)."""
    paths = _iter_src_files()
    defs = {qualified: node for qualified, _p, node, _kw in _iter_field_definitions(paths, "operation")}
    violations: list[str] = []
    for qualified in _NON_AUDIT_OPERATION_PARAMETERS:
        node = defs.get(qualified)
        if node is None:
            continue  # covered by the existence test above
        if _excluded_definition_forwards_its_own_parameter(node, "operation"):
            violations.append(qualified)
    assert not violations, (
        f"excluded definition(s) that forward their own client-supplied operation parameter into an audit emit call: {violations!r}"
    )


@pytest.mark.parametrize("field", _FIELDS)
def test_no_field_string_literal_is_smuggled_through_a_dict(field):
    """(d). No `Dict` literal or `x["field"] = ...` subscript assignment
    anywhere under `src/r2db_api/` sets `field` to anything other than a
    genuine forward or read-path passthrough (b''')."""
    paths = _iter_src_files()
    violations = _field_dict_smuggling_violations(paths, field)
    assert not violations, f"dict/subscript {field} literal smuggling site(s): {violations!r}"


@pytest.mark.parametrize("field", _FIELDS)
def test_no_field_string_literal_is_smuggled_through_an_assignment(field):
    """(d'). No `Assign`/`AnnAssign`/`AugAssign` anywhere (every scope)
    assigns a non-allowed value to a target named/keyed `field`. A plain
    `name_assign` MAY carry a `_literal_leaves` value (b''/b') -- this is
    exactly the shape the (b'') exemption's own qualifying assignment
    takes; an `attribute_assign` may not (unchanged from P4-D16 v3)."""
    paths = _iter_src_files()
    violations = _field_assignment_violations(paths, field)
    assert not violations, f"{field} assignment-target literal smuggling site(s): {violations!r}"


def test_event_class_forward_exclusion_requires_genuine_parameter_binding():
    """WP-B1 review round 2 (M3/M6), unchanged by this WP: a local variable/
    global/for-target/walrus of the identical name is explicitly NOT a
    forward and IS a violation. Kept event_class-specific (the original
    synthetic-source regression) -- `_scan_field_literals`/`_scan_source_
    field_sites` are the generalized functions it now calls."""
    source_local_var = (
        "def f(sink):\n"
        "    event_class = \"__WPB1_SYNTHETIC_FIXTURE_LOCAL__\"\n"
        "    sink.append(event_class=event_class)\n"
    )
    # NOTE: this local variable IS a qualifying (b'') const-bound name (a
    # single Assign of a plain string Constant, no other binding form) --
    # WP-B1's original claim ("must be rejected, flagged unresolved") no
    # longer holds verbatim under the Phase 5 generalization: (b'') was
    # deliberately designed to accept exactly this shape (design N-6's
    # sibling reasoning -- a same-scope, singly-bound Constant/IfExp local
    # is now ON PAR with a parameter forward). The literal is instead
    # picked up as authored AT THE ASSIGNMENT (`_field_literal_union`'s own
    # `name_assign` contribution), and the keyword-site forward itself
    # contributes nothing further -- so the net U is identical to the
    # pre-Phase-5 accounting, just attributed to a different site.
    literals, unresolved = _scan_field_literals(source_local_var, "synthetic_local_var.py", "event_class")
    assert not literals, "a keyword-site forward of a (b'')-qualifying local must contribute nothing directly to U at THIS site"
    assert not unresolved, "a (b'')-qualifying local-variable forward must resolve, not be flagged unresolved"

    # (ii) a dict literal with an f-string (`JoinedStr`) value, smuggled
    # into a call via `**{...}` expansion -- must be caught by (d)'s
    # dict-smuggling scan. An f-string is not a plain string `Constant`.
    source_dict_fstring = (
        "def g(sink, suffix):\n"
        "    sink.append(**{\"event_class\": f\"__WPB1_SYNTHETIC_FIXTURE_FSTRING_{suffix}__\"})\n"
    )
    _keyword_sites, dict_sites, _assignment_sites = _scan_source_field_sites(source_dict_fstring, "synthetic_dict_fstring.py", "event_class")
    dict_violations = [f"synthetic_dict_fstring.py:{lineno}" for lineno, _kind, _value, ok in dict_sites if not ok]
    assert dict_violations == ["synthetic_dict_fstring.py:2"], (
        f"an f-string value smuggled through a dict literal's event_class key must be flagged as a violation: "
        f"{dict_violations!r} (raw sites: {dict_sites!r})"
    )

    # (iii) `with ... as event_class:` -- the context manager's bound
    # variable is NOT a parameter forward and does NOT qualify for (b'')
    # (its binding form is a `withitem`, not a plain `Assign`), even though
    # `h` also declares `event_class` as its own keyword-only parameter.
    source_with_as = (
        "from contextlib import nullcontext\n"
        "def h(sink, *, event_class):\n"
        "    with nullcontext(\"__WPB1_SYNTHETIC_FIXTURE_WITH__\") as event_class:\n"
        "        sink.append(event_class=event_class)\n"
    )
    literals_with, unresolved_with = _scan_field_literals(source_with_as, "synthetic_with_as.py", "event_class")
    assert not literals_with, f"a with-as-rebound event_class must never be collected as a literal: {literals_with!r}"
    assert unresolved_with == ["synthetic_with_as.py:4"], (
        f"a with-as-rebound event_class=event_class must be flagged unresolved, not silently accepted as the function's own parameter forward: {unresolved_with!r}"
    )

    # (iv) `except ... as event_class:` -- `ExceptHandler.name` is a plain
    # STRING attribute, not a `Name` node, and (like with-as) is not a
    # (b'')-qualifying binding form either.
    source_except_as = (
        "def k(sink, *, event_class):\n"
        "    try:\n"
        "        raise ValueError(\"__WPB1_SYNTHETIC_FIXTURE_EXCEPT__\")\n"
        "    except Exception as event_class:\n"
        "        sink.append(event_class=event_class)\n"
    )
    literals_except, unresolved_except = _scan_field_literals(source_except_as, "synthetic_except_as.py", "event_class")
    assert not literals_except, f"an except-as-rebound event_class must never be collected as a literal: {literals_except!r}"
    assert unresolved_except == ["synthetic_except_as.py:5"], (
        f"an except-as-rebound event_class=event_class must be flagged unresolved, not silently accepted as the function's own parameter forward: {unresolved_except!r}"
    )


def test_field_forward_exclusion_rejects_a_second_binding_form_even_with_a_qualifying_assign():
    """(b'') acceptance-audit-round-2-style boundary case, new for Phase 5:
    a qualifying single-`Assign`-of-`Constant` local, ALSO reassigned by a
    non-qualifying second binding (a `for` target reusing the same name) in
    the SAME scope, must forfeit the (b'') exemption entirely -- design's
    own "同スコープに他の束縛形が1つでもあれば違反のまま" requirement.
    Mirrors mutation 4 (同名変数へ Call 束縛) but with a `for`-target rebind
    instead, proving the "any other form" wording, not merely "any other
    Call", is enforced."""
    source = (
        "def f(sink, items):\n"
        "    operation = \"__WPB2_SYNTHETIC_QUALIFYING__\"\n"
        "    for operation in items:\n"
        "        pass\n"
        "    sink.append(operation=operation)\n"
    )
    literals, unresolved = _scan_field_literals(source, "synthetic_second_binding.py", "operation")
    assert not literals, f"a variable with a second, non-qualifying binding form must never be treated as (b'')-eligible: {literals!r}"
    assert unresolved == ["synthetic_second_binding.py:5"], (
        f"a variable rebound by a for-target after a qualifying assign must be flagged unresolved, not silently accepted: {unresolved!r}"
    )


def test_field_keyword_position_never_accepts_attribute_or_subscript_read_passthrough():
    """(b'''), new for Phase 5: `.field`/`["field"]` read-path passthrough
    is legal at a dict-literal/subscript-assignment/attribute-assignment
    value position but NEVER at a `field=` keyword-argument-value
    position -- the hole the generalization itself opens (a request body
    key literally named `"operation"`, closed structurally rather than by
    convention)."""
    source_attribute = (
        "def f(sink, event):\n"
        "    sink.append(operation=event.operation)\n"
    )
    literals, unresolved = _scan_field_literals(source_attribute, "synthetic_kw_attr.py", "operation")
    assert not literals
    assert unresolved == ["synthetic_kw_attr.py:2"], (
        f"an Attribute read-passthrough at a keyword-value position must be rejected, not silently accepted: {unresolved!r}"
    )

    source_subscript = (
        "def g(sink, row):\n"
        "    sink.append(operation=row[\"operation\"])\n"
    )
    literals2, unresolved2 = _scan_field_literals(source_subscript, "synthetic_kw_sub.py", "operation")
    assert not literals2
    assert unresolved2 == ["synthetic_kw_sub.py:2"], (
        f"a Subscript read-passthrough at a keyword-value position must be rejected, not silently accepted: {unresolved2!r}"
    )

    # Sanity/contrast (常設規律1, 空振り禁止): the SAME passthrough shapes
    # ARE allowed at a dict-literal value position -- proves the rejection
    # above is positional, not a blanket ban on Attribute/Subscript.
    source_dict_ok = (
        "def h(sink, event, row):\n"
        "    return {\"operation\": event.operation, \"other\": row[\"operation\"]}\n"
    )
    _kw, dict_sites, _assign = _scan_source_field_sites(source_dict_ok, "synthetic_dict_ok.py", "operation")
    assert dict_sites, "the dict-literal site itself must be observed by the scanner for this contrast to mean anything"
    assert all(ok for _lineno, _kind, _value, ok in dict_sites), (
        f"Attribute/Subscript read-path passthrough must remain legal at a dict-literal value position: {dict_sites!r}"
    )


# P4-D16 v3(e)'s own N for `event_class`, UNCHANGED by this WP (content
# and rationale identical to the pre-Phase-5 file -- kept here, next to its
# `operation`/`target_kind` siblings below, purely for locality).
_NON_DURABLE_EVENT_CLASSES: frozenset[str] = frozenset(
    {
        # `_event` (service.py, `event_class="authentication"`) --
        # `authenticate()`'s own success event. `_event`'s own dispatch
        # body (the `if event_class != "data_operation": return` guard
        # right before the buffer-class enqueue) keeps this literal in the
        # legacy in-memory `self._audit` sink only; it never reaches the
        # buffer or the denial-coalescer.
        "authentication",
        # `_control_event` (service.py) writes ONLY to the legacy
        # in-memory `self._service._audit` sink -- never to the durable
        # `control_audit` table (that table is written exclusively by
        # `ops.py`'s own `_write_control_audit`, a structurally separate
        # call path). `control_failure` is one of `_control_event`'s two
        # non-durable-only literals (every `except FoundationError` deny
        # branch across register/enable/disable-application,
        # set_credential_state, issue_credential, delete_audit, and
        # set_authorization_state_available).
        "control_failure",
        # Same call path/rationale as `control_failure` above --
        # `_control_event`'s own `set_authorization_state_available`
        # SUCCESS literal (the one `_control_event` call site whose
        # `outcome` is `"allow"` rather than `"deny"`).
        "control_state",
    }
)

# P4-D16 v3(e)'s own N, generalized: the explicit, non-durable exclusion
# set per field. Each element is real (found by the scanner's own
# unfiltered walk) but reaches ONLY the legacy in-memory `AuditSink`
# (`ControlAuthority._control_event`'s own docstring: "ControlAuthority's
# own audit trail stays on the existing in-memory AuditSink ... not on the
# new control_audit table" -- `service.py`), never the durable `application_
# audit`/`control_audit` tables `audit_query` reads.
# `test_operation_and_target_kind_non_durable_exclusions_never_reach_the_
# durable_tables` below is the REQUIRED runtime proof (design §3 D-1: "N
# は実行時テストで確定する" -- a structural/docstring argument alone is a
# starting point, never proof by itself).
#
# Design's own worked example of why EVERY one of the 8 original
# candidate words (§1.4 の 8) needed individual, not blanket, treatment:
# `enable_application`/`disable_application`/`issue_credential`/`register_
# application` ALL also appear on `ControlPlaneService`'s OWN durable
# `_write_state_audit`/`_deny` call sites (a structurally SEPARATE class
# from `ControlAuthority`, backed by a real `ControlAuditSink`/
# `PostgresControlAuditSink`) -- so all four are D, not N, even though
# `ControlAuthority` ALSO happens to emit the identical literal string on
# its own non-durable path. `authenticate` needed the SAME per-site care in
# the OTHER direction, and static reasoning alone got it wrong on the first
# pass: its SUCCESS site (`DataService._event(operation="authenticate",
# event_class="authentication")`) is genuinely non-durable-only, but its
# FAILURE site (`authenticate`'s own `except FoundationError`, `_denial_
# event(event_class="authentication_denial", operation="authenticate",
# ...)`) durably routes through the coalescing denial router whenever
# `exc.code` is one of `_DURABLE_DENIAL_CODES` (`AUTH_INVALID` among them,
# the ordinary "bad secret" case) -- an ACTUALLY-OBSERVED durable row is
# what caught this (`conformance-tests/test_c09_audit_evidence.py`'s own
# declaration-agreement vector, run against this WP's first draft
# declaration), not a re-reading of the docstring. `authenticate` is
# therefore D, not N (`DECLARED_AUDIT_OPERATIONS`'s own comment carries the
# same correction). Only a word with NO durable emit site anywhere in the
# package may be N.
_NON_DURABLE_OPERATIONS: frozenset[str] = frozenset(
    {
        # `ControlAuthority.delete_audit` -> `_control_event(operation=
        # "delete_audit", ...)` -- the in-memory `AuditSink`'s own
        # append-only enforcement failure path; no `ControlPlaneService`
        # method (the durable class) ever names this operation.
        "delete_audit",
        # `ControlAuthority.set_authorization_state_available` ->
        # `_control_event(operation="set_authorization_state_available",
        # ...)` -- this literal never appears in control_plane.py at all.
        "set_authorization_state_available",
        # `ControlAuthority.set_credential_state` -> `_control_event(
        # operation="set_credential_state", ...)` -- `ControlPlaneService.
        # _set_credential_state` (the durable class's OWN, differently-
        # named method) forwards its caller's `operation` parameter
        # verbatim (always "enable_credential"/"disable_credential"/etc.)
        # and never itself passes the literal "set_credential_state".
        "set_credential_state",
        # `ControlPlaneService.capabilities()`'s own 2 emit sites
        # (`_authorize_role(context, operation="control_capabilities",
        # ...)` / `_gate_must_rotate(context, operation=
        # "control_capabilities", ...)`) -- a DIFFERENT shape of non-
        # durability from the 3 words above (fix-round M-1, Opus review):
        # there is no reachable `_deny` call for this operation AT ALL, on
        # any role or must_rotate state, so this word has no failure mode
        # to durably record in the first place -- not merely "the only
        # emit path is the legacy sink". `_AUDIT_ROLE_ALLOWED_OPERATIONS`
        # permanently includes it (closing `_authorize_role`'s own deny
        # condition), and `_gate_must_rotate` opens with an unconditional
        # `if operation == "control_capabilities": return`. Structural,
        # not exercised for observed-absence purposes by `test_operation_
        # and_target_kind_non_durable_exclusions_never_reach_the_durable_
        # tables` above (there is nothing to durably fail INTO) -- fixed
        # instead by `test_control_capabilities_operation_has_no_
        # reachable_deny_branch` below, which pins both structural facts
        # directly and behaviorally proves the must_rotate early return
        # (a must_rotate=True credential can still call `capabilities()`
        # successfully).
        "control_capabilities",
    }
)
_NON_DURABLE_TARGET_KINDS: frozenset[str] = frozenset(
    {
        # `ControlAuthority._control_event`'s own hardcoded target_kind --
        # every `ControlAuthority` call site funnels through this one
        # non-durable emit function; no durable emit site anywhere in the
        # package ever passes this literal.
        "application_or_credential",
    }
)


def test_control_capabilities_operation_has_no_reachable_deny_branch() -> None:
    """Fix-round M-1 (Opus review): `operation="control_capabilities"` is in
    `_NON_DURABLE_OPERATIONS` for a DIFFERENT reason than its 3 siblings --
    not "reaches only the legacy sink", but "reaches no `_deny` call at
    all". Pins BOTH structural facts directly, plus a behavioral proof:

    (a) `_authorize_role`'s own deny condition (`control_plane.py`) is
    `context.role == "audit" and operation not in _AUDIT_ROLE_ALLOWED_
    OPERATIONS` -- `"control_capabilities"` is a PERMANENT member of that
    allow-list, so the condition can never be true for it, regardless of
    role.
    (b) `_gate_must_rotate`'s own body (`control_plane.py`) opens with `if
    operation == "control_capabilities": return` -- an unconditional early
    return before its own `_deny` call is ever reached. Proven both
    structurally (the source literally starts this way, verified by (a)'s
    sibling fact holding) and BEHAVIORALLY here: a credential with `must_
    rotate=True` (freshly `add()`-ed, never `rotate()`-d -- `Control
    CredentialRecord`'s own `must_rotate: bool = True` default) must still
    be able to call `capabilities()` successfully -- if `_gate_must_rotate`
    ever reached its own `_deny` for this operation, this call would raise
    `FORBIDDEN` instead.
    """
    assert "control_capabilities" in _AUDIT_ROLE_ALLOWED_OPERATIONS

    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    authority = ControlAuthority(DataService(CredentialStore(pepper=APP_PEPPER)))
    backend = InMemoryControlBackend(authority, control_credentials)
    service = ControlPlaneService(backend, audit=ControlAuditSink(), limits=_GENEROUS_LIMITS)
    credential_id = "ctl_" + secrets.token_hex(8)
    secret = "m1-must-rotate-" + secrets.token_urlsafe(8)
    with control_credentials.unit_of_work() as work:
        control_credentials.add(credential_id, secret, work=work)  # must_rotate=True by construction; deliberately never rotated
    document = service.capabilities(compose_bearer_locator(credential_id, secret))  # must NOT raise FORBIDDEN -- the observable half of _gate_must_rotate's early return
    assert document["contract_version"] == "1.7.0"  # contract 1.7.0, WP-2e version flip
    assert document["capabilities"]["audit_query"]["status"] == "unavailable"


@pytest.mark.parametrize("kind", BACKENDS)
def test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables(kind, platform):
    """N の実行時実測 (design §3 D-1). Exercises the REAL, non-durable call
    path for every `_NON_DURABLE_OPERATIONS`/`_NON_DURABLE_TARGET_KINDS`
    word directly (a fresh `ControlAuthority(h.data_service)` -- never
    mocked), then queries the SAME durable `audit_query` surface every
    other test in this file uses, and asserts none of these words is EVER
    observable there. A sanity/contrast assertion (常設規律1, 空振り禁止)
    proves the harness itself CAN observe a durable row at all --
    `register_application`/`enable_application`/`issue_credential` (through
    `h.service`, the REAL, durable `ControlPlaneService`) AND a FAILED
    `DataService.authenticate` call (`authenticate` is D, not N -- its own
    denial path is what this same runtime discipline caught during WP-2,
    see `_NON_DURABLE_OPERATIONS`'s own comment). For `kind="postgres"`,
    `h.service` is architecturally a SEPARATE backend from `h.data_service`,
    so the D-word contrast is deliberately driven through `h.service`'s own
    public methods, never through `ControlAuthority`, which for
    `kind="postgres"` would touch an unrelated, throwaway `DataService`
    whose `cell_factory` intentionally raises if invoked. Deliberately does
    NOT exercise `"control_capabilities"` (also in `_NON_DURABLE_
    OPERATIONS` as of fix-round M-1) -- that word has no reachable `_deny`
    call to exercise in the first place (structural, not "reaches a
    non-durable sink"); see `test_control_capabilities_operation_has_no_
    reachable_deny_branch` for its own dedicated structural + behavioral
    proof instead.
    """
    h = _build_harness(kind, platform)
    try:
        # ---- D-word sanity/contrast: genuinely DURABLE control-plane
        # writes, through the REAL `ControlPlaneService` this harness's own
        # `audit_query` reads from. ----
        durable_app_id = "n_word_durable_app_" + secrets.token_hex(4)
        h.service.register_application(h.control_credential_secret, durable_app_id)
        h.service.set_application_enabled(h.control_credential_secret, durable_app_id, True)
        h.service.issue_credential(h.control_credential_secret, durable_app_id, "runtime")

        # ---- N-word exercise: the REAL, non-durable `ControlAuthority`
        # call path, driven directly against this harness's own `data_
        # service` (`service.py`'s own docstring: this class's audit trail
        # never lands in control_audit/application_audit, regardless of
        # which concrete `DataService` instance backs it). Deliberately
        # avoids `ControlAuthority.register_application`/`set_application_
        # enabled` (which touch `DataService._cells` via `cell_factory` --
        # for `kind="postgres"`, `h.data_service`'s own `cell_factory` is
        # built to raise if ever invoked, since that harness's `data_
        # service` exists only to hold a real `_durable_audit`/
        # `_credentials`, not a usable cell catalog) -- none of the four
        # N-words need `_cells` to exercise their real non-durable path.
        authority = ControlAuthority(h.data_service)
        legacy_app_id = "n_word_legacy_app_" + secrets.token_hex(4)

        authority.set_authorization_state_available(True)  # -> N-word "set_authorization_state_available"

        try:
            authority.delete_audit()  # -> N-word "delete_audit" (append-only sink refuses; PermissionError)
        except PermissionError:
            pass

        credential_id = "crd_" + secrets.token_hex(8)
        credential_secret = "n-word-cred-" + secrets.token_urlsafe(8)
        with h.credentials.unit_of_work() as work:
            h.credentials.add(credential_id, legacy_app_id, "runtime", credential_secret, work=work)
        authority.set_credential_state(credential_id, enabled=False)  # -> N-word "set_credential_state"

        # `authenticate` D-word contrast: its SUCCESS path (`DataService.
        # authenticate`, `event_class="authentication"`) is non-durable, but
        # its FAILURE path durably records `operation="authenticate"` under
        # `event_class="authentication_denial"` whenever the failure code is
        # in `_DURABLE_DENIAL_CODES` -- `AUTH_INVALID` (a bad secret) is one.
        # Never through `ControlAuthority` -- `authenticate` is a `DataService`
        # method, always.
        context, secret = _seed_application_credential(h.credentials, legacy_app_id, "runtime")
        h.data_service.authenticate(secret)  # success -- legacy in-memory sink only
        with pytest.raises(FoundationError):
            h.data_service.authenticate("wrong-" + secret)  # -> D-word "authenticate" via authentication_denial (durable)

        h.data_service.flush_audit_buffer()
        _wait_for_visibility(h)

        # ---- Read back through the DURABLE surface every other test in
        # this file uses -- large limit, no event_classes filter, so every
        # durable row this exercise could possibly have produced is
        # included. ----
        result = h.service.audit_query(h.control_credential_secret, {"limit": 200})
        events = result["events"]
        assert events, "the harness itself must have produced at least one durable row for this test to observe anything (常設規律1)"

        observed_operations = {event["operation"] for event in events}
        observed_target_kinds = {event["target_kind"] for event in events}

        # Sanity/contrast: the exercise above DOES reach the durable
        # tables for genuinely durable operations -- proves the read side
        # of this test is not itself vacuous. Includes `authenticate`
        # itself, specifically: it is D, not N, and this same failed-
        # authenticate exercise is what the runtime discipline uses to
        # prove that (design §3 D-1's own "N は実行時テストで確定する").
        assert observed_operations & {"register_application", "enable_application", "issue_credential"}, (
            f"the harness must observe at least one genuinely durable D-word from this same exercise: {observed_operations!r}"
        )
        assert "authenticate" in observed_operations, (
            f"a failed DataService.authenticate() must durably record operation='authenticate' via the "
            f"authentication_denial path -- if not, `authenticate`'s own D classification is unproven: {observed_operations!r}"
        )

        leaked_operations = observed_operations & _NON_DURABLE_OPERATIONS
        assert not leaked_operations, (
            f"MUTATION SHOULD HAVE BEEN CAUGHT (or N is wrong): non-durable-exclusion operation word(s) actually reached "
            f"the durable audit_query surface: {leaked_operations!r}"
        )
        leaked_target_kinds = observed_target_kinds & _NON_DURABLE_TARGET_KINDS
        assert not leaked_target_kinds, (
            f"MUTATION SHOULD HAVE BEEN CAUGHT (or N is wrong): non-durable-exclusion target_kind word(s) actually reached "
            f"the durable audit_query surface: {leaked_target_kinds!r}"
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_event_classes_cover_every_emittable_class(kind, platform):
    """§9.2 property 5 / P4-D16 v3(e), unchanged in substance -- now calls
    the generalized `_field_literal_union` instead of an inline
    keyword-sites-only loop (the two are equivalent for `event_class`,
    which has no `name_assign`-position IfExp/Constant sites in this
    package)."""
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["event_classes"])
        assert declared == DECLARED_AUDIT_EVENT_CLASSES

        emitted = _field_literal_union(_iter_src_files(), "event_class")
        assert emitted, "the AST scanner found zero event_class literals -- it is itself broken"

        d = DECLARED_AUDIT_EVENT_CLASSES
        n = _NON_DURABLE_EVENT_CLASSES
        assert not (d & n), f"declared vocabulary and non-durable exclusion set N overlap (should be disjoint): {d & n!r}"
        assert emitted == d | n, (
            f"emittable-vs-(declared|N) mismatch: "
            f"emitted but neither declared nor in N: {emitted - (d | n)!r}; "
            f"declared or in N but never actually emitted: {(d | n) - emitted!r}"
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_operations_cover_every_emittable_operation(kind, platform):
    """P4-D16 v3(e) for `operation` (design D-1). Same `U == D | N`, `D & N
    == set()` equality as `event_class` above, now load-bearing (this WP
    flips `contract_version` to 1.5.0 in the same commit)."""
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["operations"])
        assert declared == DECLARED_AUDIT_OPERATIONS

        emitted = _field_literal_union(_iter_src_files(), "operation")
        assert emitted, "the AST scanner found zero operation literals -- it is itself broken"

        d = DECLARED_AUDIT_OPERATIONS
        n = _NON_DURABLE_OPERATIONS
        assert not (d & n), f"declared vocabulary and non-durable exclusion set N overlap (should be disjoint): {d & n!r}"
        assert emitted == d | n, (
            f"emittable-vs-(declared|N) mismatch: "
            f"emitted but neither declared nor in N: {emitted - (d | n)!r}; "
            f"declared or in N but never actually emitted: {(d | n) - emitted!r}"
        )
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_target_kinds_cover_every_emittable_target_kind(kind, platform):
    """P4-D16 v3(e) for `target_kind` (design D-1)."""
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["target_kinds"])
        assert declared == DECLARED_AUDIT_TARGET_KINDS

        emitted = _field_literal_union(_iter_src_files(), "target_kind")
        assert emitted, "the AST scanner found zero target_kind literals -- it is itself broken"

        d = DECLARED_AUDIT_TARGET_KINDS
        n = _NON_DURABLE_TARGET_KINDS
        assert not (d & n), f"declared vocabulary and non-durable exclusion set N overlap (should be disjoint): {d & n!r}"
        assert emitted == d | n, (
            f"emittable-vs-(declared|N) mismatch: "
            f"emitted but neither declared nor in N: {emitted - (d | n)!r}; "
            f"declared or in N but never actually emitted: {(d | n) - emitted!r}"
        )
    finally:
        h.cleanup()


# ===========================================================================
# Phase 4 ledger closure WP-B3 addendum, generalized for Phase 5: `U == D |
# N` cannot detect D SHRINKING while a matching word simultaneously moves
# into N. Pins each declared vocabulary's own CONTENT directly.
# ===========================================================================


def test_declared_audit_event_classes_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_EVENT_CLASSES` (`audit_query.py`)
    currently holds exactly these 11 words."""
    assert DECLARED_AUDIT_EVENT_CLASSES == frozenset(
        {
            "data_operation",
            "privilege_sensitive",
            "authorization_denial",
            "operation_denial",
            "privilege_denial",
            "authentication_denial",
            "security_control_failure",
            "application_lifecycle",
            "capability_denial",
            "control_credential_lifecycle",
            "credential_lifecycle",
        }
    )


def test_declared_audit_operations_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_OPERATIONS` (`audit_query.py`)
    currently holds exactly these 27 words -- the full emitted union U (31
    words, `_field_literal_union`) minus N's 4 words (`_NON_DURABLE_
    OPERATIONS`: `delete_audit`/`set_authorization_state_available`/
    `set_credential_state`, all legacy-sink-only, plus `control_
    capabilities`, structurally deny-unreachable -- fix-round M-1, Opus
    review). `authenticate` is D, not N (its own denial path durably
    routes); see `_NON_DURABLE_OPERATIONS`'s own comments for both
    corrections' rationale."""
    assert DECLARED_AUDIT_OPERATIONS == frozenset(
        {
            "audit_buffer",
            "audit_query",
            "authenticate",
            "bootstrap_control_credential",
            "catalog",
            "control_authenticate",
            "cross_entity_mutate",
            "delete_credential",
            "disable_application",
            "disable_credential",
            "enable_application",
            "enable_control_credential",
            "enable_credential",
            "freeze_issuance",
            "issue_audit_credential",
            "issue_credential",
            "list_applications",
            "list_credentials",
            "mutate",
            "query",
            "register_application",
            "reset_control_credentials",
            "revoke_credential",
            "rotate_control_credential",
            "rotate_credential",
            "schema",
            "unfreeze_issuance",
        }
    )


def test_declared_audit_target_kinds_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_TARGET_KINDS` (`audit_query.py`)
    currently holds exactly these 5 words."""
    assert DECLARED_AUDIT_TARGET_KINDS == frozenset(
        {
            "application",
            "audit_sink",
            "control_credential",
            "credential",
            "entity",
        }
    )


def test_audit_query_declares_operations_and_target_kinds_over_http(platform):
    """完了条件9 (宣言キーの露出): the `operations`/`target_kinds` keys
    reach a real HTTP client, not merely the in-process `capabilities()`
    dict -- mirrors this file's own existing in-process/HTTP-parity
    pattern for `event_classes`. Reuses `_postgres_harness`'s own already-
    seeded `control_credential_secret` (that harness's own `PostgresControl
    CredentialStore` seeding, mirrored here, is a separate object from
    `assemble_control_stack`'s returned `stores` tuple -- `stores[0]` is a
    `PostgresApplicationRegistry`, not a credential store)."""
    h = _postgres_harness(platform)
    try:
        app = create_control_app(h.service)
        with TestClient(app) as client:
            response = client.get("/control/v1/capabilities", headers=_auth(h.control_credential_secret))
            assert response.status_code == 200
            document = response.json()
            declared = document["capabilities"]["audit_query"]
            assert set(declared["operations"]) == DECLARED_AUDIT_OPERATIONS
            assert set(declared["target_kinds"]) == DECLARED_AUDIT_TARGET_KINDS
    finally:
        h.cleanup()


def test_ast_scan_now_covers_files_the_old_hardcoded_enumeration_missed():
    """[MitateDB WP-3(b) 対称 evidence-hardening item 1] structural proof
    that `_iter_src_files()` + `_scan_field_literals` reach `ops.py`'s
    `_write_control_audit(...)` call sites."""
    ops_py = _SRC_DIR / "ops.py"
    assert ops_py in _iter_src_files(), "ops.py must be part of the scanned file set for this proof to be meaningful"
    literals, unresolved = _scan_field_literals(ops_py.read_text(), "ops.py", "event_class")
    assert not unresolved
    assert literals == {"credential_lifecycle", "application_lifecycle", "control_credential_lifecycle"}


def test_mutating_an_ops_py_event_class_literal_to_an_undeclared_value_turns_the_declared_vocabulary_check_red(platform):
    """[MitateDB WP-3(b) 対称 evidence-hardening item 1] the actual mutation
    proof: writes a throwaway copy of `ops.py`'s TEXT (never the real
    source file) with ONE `_write_control_audit(...,
    event_class="credential_lifecycle", ...)` literal changed to an
    undeclared value, then re-runs the same emittable-vs-declared
    comparison against `_iter_src_files()` with the mutated copy
    substituted in for the real `ops.py`.
    """
    real_source = (_SRC_DIR / "ops.py").read_text()
    assert 'event_class="credential_lifecycle"' in real_source, (
        "test's own fixture assumption about ops.py's literal text no longer holds -- update this test"
    )
    mutated_source = real_source.replace('event_class="credential_lifecycle"', 'event_class="undeclared_mutant_event_class"', 1)
    assert mutated_source != real_source

    h = _memory_harness()
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["event_classes"])
        assert declared == DECLARED_AUDIT_EVENT_CLASSES

        emitted: set[str] = set()
        unresolved: list[str] = []
        for path in _iter_src_files():
            source = mutated_source if path.name == "ops.py" else path.read_text()
            literals, file_unresolved = _scan_field_literals(source, path.name, "event_class")
            emitted |= literals
            unresolved += file_unresolved
        assert not unresolved
        durable_eligible = emitted - {"authentication"}

        assert "undeclared_mutant_event_class" in durable_eligible, (
            "the mutated literal must actually be found by the scan -- if not, this test is not exercising what it claims to"
        )
        assert not (durable_eligible <= declared), (
            "MUTATION SHOULD HAVE BEEN CAUGHT: an event_class literal mutated in ops.py (a file the pre-hardening "
            "scan never read at all) is undeclared, yet the emittable-vs-declared comparison did not go red -- the "
            "file-enumeration widening in this test file did not actually close the coverage gap"
        )
    finally:
        h.cleanup()


# ===========================================================================
# Peer isomorphism (常設規律 6, WP-2 完了条件16 / WP-3 完了条件17): the
# scanner-support helpers above are re-implemented (never shared/imported)
# in MitateDB-api's own `tests/test_audit_query.py` (WP-3). WP-2 registered
# this as `xfail(strict=True)` since nothing existed yet on the MitateDB
# side to diff against; WP-3 adds the matching helpers there and removes
# the `xfail` in the SAME commit (this one) -- an accidental green while
# still `xfail`-marked would have meant the isomorphism was never actually
# checked, and `strict=True` would have caught that (XPASS -> failure).
#
# Phase 6 WP-0 (design D-4(c), L5-5/L5-6): the single-file/named-tuple
# mechanism this section describes is generalized below into the
# `_ISOMORPHIC_TARGETS` (r2db relative path, MitateDB relative path,
# symbol name) table, which now also covers `src/r2db_api/main.py::
# _optional_float` and `tests/test_http.py`'s byte-identical-contract test
# function, not only this file's own 11 scanner-support helpers -- see
# that table's own comment for the full rationale.
#
# Phase 6 WP-3 追補 (isomorphism table extension, supervisor ruling
# 2026-09-04): the table widens from a (relative path, symbol name) PAIR
# to a (r2db relative path, MitateDB relative path, symbol name) TRIPLE --
# the earlier `{package}` template slot only ever solved the ONE row whose
# two peers' source trees differ by package name alone (`main.py`); it had
# no way to name a row whose two peers keep the same symbol under
# DIFFERENT relative paths (`compose_bearer_locator`/`split_bearer_
# locator` live in `src/r2db_api/auth.py` on this peer, `src/mitatedb_api/
# credential_wire.py` on MitateDB-api -- a real, intentional per-peer
# module split, not a naming accident). The 15 pre-existing rows migrate
# MECHANICALLY: every row whose path was peer-name-independent repeats
# that same literal path in both slots; the `main.py` row's `{package}`
# template resolves to its two now-literal paths.
# ===========================================================================


# ---------------------------------------------------------------------------
# Phase 6 WP-0 (design D-4(c), work order §4 WP-0 変更対象 C, L5-5/L5-6):
# the mechanism above (WP-2/WP-3, "1 file + a tuple of helper names") is
# generalized below into a table -- the row form is the object that now
# defines the full set of peer-local symbols this repository pins
# isomorphic, rather than one hardcoded sibling file. The 11 rows below
# are the WP-2/WP-3 helpers, carried over UNCHANGED (not one dropped); 4
# rows are the Phase 6 WP-0 additions (`main.py::_optional_float`, `tests/
# test_http.py`'s byte-identical-contract test function, plus the
# mechanism's OWN two pieces of test-support code -- `_isomorphic_symbol_
# source`, the row resolver below, and this table's own pin test -- added
# by supervisor review ruling 2026-09-04 so the generalized mechanism pins
# itself the same way it pins everything else it was built to check,
# rather than being exempt from its own guarantee). 3 rows are the Phase 6
# WP-3 追補 additions (supervisor ruling 2026-09-04): `compose_bearer_
# locator`/`split_bearer_locator` (contract 1.6.0 subordinate ruling 11
# item 1's shared bearer-locator realization, WP-2 on this peer / WP-3 追補
# on MitateDB-api), and the unconditional-`compare_digest` timing-pin
# test (coordinator item 7(i)) -- each peer's 4 `authenticate` methods live
# under DIFFERENT file/class names, so that test's own per-peer {filename:
# {class names}} map is kept OUTSIDE the pinned function body (module-level
# `_TIMING_PIN_TARGETS` in `tests/test_control_plane_store.py`, not
# isomorphism-checked) precisely so the pinned function ITSELF stays
# byte-identical after normalization. This tuple's own literal text is
# peer-name-free (both path slots are now literal per-peer paths, no
# `{package}` template survives), so it is intended to read identically in
# MitateDB-api's own copy of this file.
# ---------------------------------------------------------------------------

_ISOMORPHIC_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_src_files"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_literal_leaves"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_name_or_attribute_targets"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_is_field_assignment_target"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_collect_direct_shadow_names"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_analyze_field_scope"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_FieldForwardResolver"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_scan_source_field_sites"),
    # WP-3 fix-round L-4 (Opus review): completion condition 17 names the
    # exclusion-list validators ((i)/(ii') judgment) as part of this same
    # isomorphism check -- omitting them let a peer change (ii')'s own
    # judgment (e.g. dropping the safe-forward id check) go undetected.
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_field_definitions"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_field_positional_definitions"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_excluded_definition_forwards_its_own_parameter"),
    # Phase 6 WP-0 additions (design D-4(a)/(b)):
    ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_optional_float"),
    ("tests/test_http.py", "tests/test_http.py", "test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth"),
    # Phase 6 WP-0 additions, round 2 (supervisor review ruling
    # 2026-09-04): the mechanism's own row resolver and pin test, so the
    # generalized mechanism is itself pinned isomorphic, not exempt.
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "_isomorphic_symbol_source"),
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_97_rows"),
    # Phase 6 WP-3 追補 additions (supervisor ruling 2026-09-04, contract
    # 1.6.0 subordinate ruling 11 item 1's bearer-locator realization and
    # coordinator item 7(i)'s timing-pin test):
    ("src/r2db_api/auth.py", "src/mitatedb_api/credential_wire.py", "compose_bearer_locator"),
    ("src/r2db_api/auth.py", "src/mitatedb_api/credential_wire.py", "split_bearer_locator"),
    (
        "tests/test_control_plane_store.py",
        "tests/test_control_plane_store.py",
        "test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest",
    ),
    # Q4 phase WP-0 additions (design docs/design/Q4_DB_SIDE_SINGLE_
    # TRUTH_V1.md D-1 (b)(ii), D-3 (d); work order §4 WP-0 変更対象 A/C;
    # supervisor ruling 2026-09-05, first pass): the ms-normalization
    # helper promoted from three independent per-peer test-file copies to
    # `src/<package>/pg_timeouts.py`, and the static per-application-
    # upgrade-ledger scanner's own walking helper (`tests/
    # test_platform_upgrade_ledger_scan.py`), each now a single peer-local
    # symbol pinned isomorphic to its sibling instead of an unchecked
    # duplicate.
    ("src/r2db_api/pg_timeouts.py", "src/mitatedb_api/pg_timeouts.py", "ms_from_pg_timeout_text"),
    (
        "tests/test_platform_upgrade_ledger_scan.py",
        "tests/test_platform_upgrade_ledger_scan.py",
        "scan_platform_upgrade_ledger_script",
    ),
    # Q4 phase WP-0 差し戻し round addition (supervisor ruling 2026-09-05,
    # 裁定 A): WP-0's own first-pass three-way-match test asserted three
    # hand-written literal sets (`{9} == {9} == {9}`) and executed NONE of
    # the scanner's own extraction logic (a vacuity finding, code review
    # round 1 + acceptance audit). `template_seed_numbers` is the named
    # helper the rework round's synthetic three-way-match test now calls
    # for real, alongside `_classify_migrations_dir`'s own
    # `applicable_numbers` -- 裁定 A permits EXACTLY this ONE extra row
    # (WP-0's total is 3, never more): the rows WP-1/WP-2/WP-3/WP-4
    # themselves introduce are still added by the later half of each pair
    # (WP-2, WP-4), not here.
    (
        "tests/test_platform_upgrade_ledger_scan.py",
        "tests/test_platform_upgrade_ledger_scan.py",
        "template_seed_numbers",
    ),
    # Q4 phase WP-0 最終追補 (supervisor ruling 2026-09-05, 裁定 4): the
    # THREE peer-local helpers the two pinned scanner functions above
    # (`scan_platform_upgrade_ledger_script`, `template_seed_numbers`)
    # themselves call -- `_strip_sql_comments`, `_iter_ledger_statements`,
    # `_strip_string_literals` -- are added here, superseding the earlier
    # "WP-0's total is 3, never more" ruling (裁定 A above): the table's
    # own purpose is pinning peer-duplicated HELPERS, and leaving a pinned
    # function's own sub-helpers outside the table lets one peer loosen
    # just the sub-helper (never the pinned function's own body) without
    # either the isomorphism check or the pinned function's own text
    # changing -- exactly what the acceptance audit's independent mutation
    # (`_strip_sql_comments`'s string-literal tracking disabled) found:
    # every existing test, isomorphism check included, stayed green.
    (
        "tests/test_platform_upgrade_ledger_scan.py",
        "tests/test_platform_upgrade_ledger_scan.py",
        "_strip_sql_comments",
    ),
    (
        "tests/test_platform_upgrade_ledger_scan.py",
        "tests/test_platform_upgrade_ledger_scan.py",
        "_iter_ledger_statements",
    ),
    (
        "tests/test_platform_upgrade_ledger_scan.py",
        "tests/test_platform_upgrade_ledger_scan.py",
        "_strip_string_literals",
    ),
    # Q4 phase WP-1/WP-2 additions (design docs/design/Q4_DB_SIDE_SINGLE_
    # TRUTH_V1.md D-1(b)/(c), D-2(d); work order §4 WP-1/WP-2 変更対象;
    # monitor ruling 2026-09-05, 裁定 5: the pair's LATER half, WP-2 for
    # this pair, adds the rows both WPs introduce, in the SAME commit as
    # the pin-test rename below): the platform-declarations read/validate
    # helpers and the `pg_db_role_setting`-derived visibility-lag helper --
    # each peer's own new `platform_declarations.py` module (D-1(b)(i)'s
    # catalog-declaration read, D-2(d)'s "書き込み時と読み出し時の両方で
    # 同じ Python の検証関数を通る" value validators, D-1(c)'s derivation
    # formula), plus the ops-side declaration-write helper both peers'
    # `ops.py` now carry. Agent C (supervisor integration pass,
    # rulings-q4-wp12-rework.md sec.5) brought r2db-api's own realization's
    # body isomorphic to MitateDB-api's reference implementation before
    # adding this table's own rows -- see this WP's completion report for
    # the per-symbol convergence direction (which peer's body each row's
    # text was reconciled onto, and why).
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "PlatformDeclarationError"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "reject_removed_timeout_env"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "reject_removed_surface_env"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "Surfaces"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "PlatformDeclarations"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_surfaces_value"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_coalescing_window_value"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_audit_writer_roles_value"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_platform_declarations"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "RoleTimeoutCatalog"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_declared_role_timeouts"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "derive_visibility_lag_ms"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_effective_timeouts_ms"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_writer_role_timeouts"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_control_surface_consistency"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "require_control_surface_declared"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f1_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f2_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f3_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f3c_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4b_window_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4b_writer_roles_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f5_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f6_forward_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f6_reverse_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f7_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f8_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f9_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f10_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f11_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f13_message"),
    # Contract 1.7.0 (WP-2e rework, `{scratchpad}/audit-wp2e.md` I-5,
    # ruling `{scratchpad}/rulings-r3-r7-flip.md` L-2/L-8): F-14's own
    # check function and its peer-isomorphic message-hint helper -- ruling
    # I-5's original two rows, updated for L-2's rename (`check_
    # contract_170_resource_limits` -> `check_contract_170_declarations`,
    # the pre-rework name never having been added here at all, the exact
    # I-5 finding). MitateDB-api's own WP-3e has not landed these yet
    # (`{scratchpad}/rulings-r3-r7-flip.md` L-8: "pair-closing の対象に
    # する") -- these two rows are therefore part of the SAME known-red
    # `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`
    # mismatch this whole rework's own verification step already expects
    # and reports as pre-existing, not a new regression.
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_contract_170_declarations"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "ops_module_hint"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_upsert_declaration"),
    # WP-1/WP-2 audit-gaps round (supervisor ruling 2026-09-05, wp12-audit-
    # gaps.md G4): the derivation formula's own margin constant was a
    # "載せる" row in design §3.10's 同型性の面 table (the ONLY exclusion
    # is "peer 名を含む定数", which this is not) but had never actually
    # been added here. `_isomorphic_symbol_source` above is extended to
    # resolve a module-level `Assign` (not only a function/class def) so
    # this row -- a bare constant, not a def -- can resolve at all.
    (
        "src/r2db_api/platform_declarations.py",
        "src/mitatedb_api/platform_declarations.py",
        "VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS",
    ),
    # Q4 phase WP-3/WP-4 additions (design docs/design/Q4_DB_SIDE_SINGLE_
    # TRUTH_V1.md D-3(d)/(f); work order docs/work-orders/
    # WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-3/WP-4 変更対象;
    # surface pinned by monitor ruling 2026-09-05 (design docs/design/
    # Q4_DB_SIDE_SINGLE_TRUTH_V1.md §5 U-1 / U-2, §3.8 F-12): the pair's
    # LATER half (this WP, WP-4)
    # adds both WP-3's and WP-4's own new rows in one commit (work order
    # §3: "対応表への行追加は「対」の後半WPのみが行う"). Each peer's own new
    # `platform_upgrades.py` module carries the SAME 8 symbols -- the
    # cell-open-time ledger-vs-package-constant set difference (D-3(f)),
    # the F-12 message builder, and the `ops upgrade-applications`
    # summarizer/result shape (D-4/D-5). `LEDGER_TABLE_NAME`/`PLATFORM_
    # UPGRADE_NUMBERS`/`UPGRADE_SCRIPT_VARIABLE`/`PEER_MODULE` are
    # peer-specific VALUES (rulings surface doc: "対応表に載せない") and are
    # NOT added here, mirroring `platform_declarations.REMOVED_TIMEOUT_ENV`
    # / `.PEER_MODULE`'s own established exclusion.
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "PlatformUpgradeError"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "discover_upgrade_scripts"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "read_applied_upgrade_numbers"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "pending_upgrade_numbers"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "require_application_upgrades_applied"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "_f12_message"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "summarize_upgrade_run"),
    ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "ApplicationUpgradeResult"),
    # Phase 7 WP-4 addition (design docs/design/PHASE7_EVIDENCE_
    # REPRODUCIBILITY_AND_PUBLICATION_V1.md D-6.6 (e); supervisor
    # supplement 2026-09-06, 差し戻し指示 9; WP-4 rework 完了条件 15/F1,
    # 差し戻し 2 巡目): `_live_pg_backend_count` is a byte-identical,
    # independently-authored helper on BOTH peers' own HTTP conformance
    # plug (counts real PostgreSQL backends matching a caller-supplied
    # `datname_like` pattern via `pg_stat_activity`, used only by C-05's
    # own (e) resource-release check -- the caller scopes the pattern to
    # ONLY the per-application database the isolated instance itself
    # provisioned, `<prefix>_app_<application_id>`, never the shared
    # PLATFORM database the control stack's own connections live against)
    # -- exactly the kind of accidentally-duplicated logic this table
    # exists to pin, so a future edit to one side's counting query cannot
    # silently drift from the other's.
    (
        "conformance/conformance_adapter_r2db_http.py",
        "conformance/conformance_adapter_mitatedb_http.py",
        "_live_pg_backend_count",
    ),
    # Phase 8 WP-4 (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_
    # V1.md D-5 decision 1/2; work order docs/work-orders/
    # WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md §2 WP-4 "同型性テストの対
    # 象"): `ops verify-declarations`'s own peer-independent pieces -- the
    # F-number -> exit code table, the `read_platform_declarations` check
    # order, and the two print/lookup helpers the command's own driver
    # calls. `cmd_verify_declarations` itself is deliberately NOT a row
    # here -- it calls this peer's own provision-DSN accessor (`_control_
    # dsn` on this peer, `_provision_dsn` on MitateDB-api), a real
    # per-peer name the isomorphism normalizer (package-name substitution
    # only) does not paper over.
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_VERIFY_DECLARATIONS_EXIT_CODES"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_VERIFY_DECLARATIONS_READ_ORDER"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_ok"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_fail"),
    # WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #8): the
    # code review's own normalize-and-diff run found these 8 same-named
    # symbols in the two new `tests/test_ops_verify_declarations.py` files
    # (fixture helpers this WP's own test file needed, plus 3 `test_*`
    # bodies whose text is identical once `_normalize` strips each side's
    # own docstring and package name) actually match byte-for-byte after
    # normalization -- verified directly (`_isomorphic_symbol_source` +
    # `_normalize`, both sides) before adding these rows, not assumed from
    # the row's own name. The work order's own "同型性テストの対象" text
    # ("`ops verify-declarations` のテストと、その中で使う同名ヘルパ")
    # covers both halves of that sentence: the fixture helpers below ARE
    # "同名ヘルパ", and these 3 `test_*` functions ARE part of "`ops
    # verify-declarations` のテスト" itself -- so both halves are pinned,
    # not only the helpers. The file's OWN remaining 19 same-named `test_*`
    # functions (one per F-number, `_run_verify`, the two fixtures, etc.)
    # are NOT rows here: their bodies carry real per-peer differences
    # (env var names, `platform.control_dsn` vs `platform.provision_dsn`/
    # `platform.dsn`, migration file names) that `_normalize` does not fold
    # away, so a normalize-and-diff run against them is a real (and
    # correct) mismatch, not an oversight.
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_admin_dsn"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_dsn_with"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_run_psql"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_require_admin_connection"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_sweep_prefix"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_platform_declaration_error_code_attribute_is_not_paraphrased"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_verify_declarations_f9_when_effective_value_disagrees_with_declared"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_verify_declarations_exits_0_when_every_check_passes"),
    # WP-4 rework round 2 (supervisor ruling 2026-09-06, wp4-rework-2.md
    # #1, acceptance audit completion condition 9 finding): the audit's
    # own 変異 B (renaming a loop variable INSIDE `_verify_declarations_
    # checks` on one peer only, behavior unchanged) left every existing
    # test green, including this isomorphism check -- `ops.py`'s own
    # header comment above already NAMED `_verify_declarations_checks` as
    # "pinned isomorphic" (and, after this round, `cmd_verify_
    # declarations` too, once its own env-var-name literal was replaced
    # with a reference to `platform_declarations.PROVISION_DSN_ENV`, the
    # same peer-specific-VALUE-constant technique `PEER_MODULE`/
    # `MIGRATION_NUMBER`/`CONTROL_PLANE_STATUS_ENV` already use) but
    # neither row had actually been added here -- a claim in a comment,
    # unchecked. Verified normalize-and-diff equal (`_isomorphic_symbol_
    # source` + `_normalize`, both sides) before adding. The audit's own
    # 変異 A (rewriting ONLY the F-1/F-2/F-12 out-of-scope reason text on
    # one peer, inside `cmd_verify_declarations`'s own trailing `print`)
    # is now caught by this same new `cmd_verify_declarations` row, not a
    # separate one -- that reason text is part of this function's own
    # body, not a standalone symbol.
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_checks"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "cmd_verify_declarations"),
    # Same round, same ruling item 1's second half: five same-named
    # `tests/test_ops_verify_declarations.py` module-level constants the
    # rework round's own normalize-and-diff run found byte-identical
    # after normalization but never added -- `ADMIN_DSN_DEFAULT` (the
    # shared throwaway-admin-connection fallback DSN, identical literal
    # both sides), `MIGRATIONS_DIR` (identical `Path(__file__).resolve()
    # .parents[1] / "migrations"` expression -- the migration FILE NAMES
    # it is later indexed with, `MIGRATION_NAMES`, are real per-peer data
    # and stay unpinned), `MIGRATION_NAMES_WITHOUT_DECLARATIONS` (a bare
    # `MIGRATION_NAMES[:-1]` slice expression referencing that same
    # per-peer tuple by name only, so its OWN text does not carry the
    # per-peer difference), and `_CONTROL_URL`/`_DATA_URL` (identical
    # `*.example.invalid` synthetic fixture URLs both sides).
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "ADMIN_DSN_DEFAULT"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "MIGRATIONS_DIR"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "MIGRATION_NAMES_WITHOUT_DECLARATIONS"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_CONTROL_URL"),
    ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_DATA_URL"),
    # Phase 9 pair-closing commit (裁定 T-2, work order §4 の 12 / §6 訂正註
    # 10, monitor ruling m-3/m-1): WP-2a's own `structured.
    # validate_enum_declaration`/`enum_member_matches_type` and WP-3a's
    # `field_types.validate_enum_declaration`/`enum_member_matches_type`
    # -- the two constraint-declaration validators both peers place under
    # the identical names m-3 fixed ahead of time so this pairing could be
    # added once both WPs merged. Verified normalize-and-diff equal
    # (`_isomorphic_symbol_source` + `_normalize`, both sides) before
    # adding: the two peers' own exception vocabulary (r2db's `fail()`,
    # MitateDB's `errors.ValidationError`) is kept OUT of the pinned
    # function bodies on both sides -- each peer raises its own locally
    # named `_ConstraintDeclarationError` (never surfaced past its own
    # module) from inside the pinned function, and each peer's own direct
    # caller (`structured._fail_constraint_declaration` / `cell._validate_
    # enum_declaration_with_path`) is the one place that translates it to
    # the peer's own public denial shape -- so the difference the two
    # peers' error handling genuinely has never enters text this
    # comparison reads.
    ("src/r2db_api/structured.py", "src/mitatedb_api/field_types.py", "validate_enum_declaration"),
    ("src/r2db_api/structured.py", "src/mitatedb_api/field_types.py", "enum_member_matches_type"),
    # Phase 9 R-4 pair-closing commit (design docs/design/PHASE9_CONTRACT_
    # 170_DECLARATION_AND_VERIFICATION_V1.md D-4 (7), 追補 2 S-a; work
    # order §2 WP-2b/WP-3b 完了条件 13(iii); 監督裁定 F-7): WP-2b's own
    # `structured.normalize_request_for_plan`/`compute_plan_token` and
    # WP-3b's own `cell.normalize_request_for_plan`/`compute_plan_token`
    # -- the two `plan`-token helpers both peers place under the
    # identical names, F-7 fixed ahead of time so this pairing could be
    # added once both WPs merged. Verified normalize-and-diff equal
    # (`_isomorphic_symbol_source` + `_normalize`, both sides) before
    # adding: both bodies already matched byte-for-byte after
    # normalization, no peer-local rework needed.
    ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "normalize_request_for_plan"),
    ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "compute_plan_token"),
    # Phase 9 R-5/R-6 pair-closing commit (design docs/design/PHASE9_
    # CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-5, 追補 2 S-a /
    # D-6, 追補 R-g; 監督裁定集約 {scratchpad}/rulings-r5-r6.md I-2/I-10/
    # B-1..B-6; work order §2 WP-2c/WP-3c 完了条件 13(iii) 相当、WP-2d/
    # WP-3d 同型性テストの対象): WP-2c's own `structured.normalize_
    # request_for_idempotency`/`idempotency_digest` and WP-3c's own
    # `cell.normalize_request_for_idempotency`/`idempotency_digest` --
    # verified normalize-and-diff equal (`_isomorphic_symbol_source` +
    # `_normalize`, both sides) before adding: both bodies already
    # matched byte-for-byte after normalization, no peer-local rework
    # needed (same precedent as R-4's `normalize_request_for_plan`/
    # `compute_plan_token` pair immediately above). WP-2d's own `limits.
    # narrow_limits_by_budget` and WP-3d's own `config.narrow_limits_by_
    # budget` needed real convergence first, done in THIS commit: `_budget_
    # denied`/`_BUDGET_CLASS_TO_FIELD` (new, both sides) absorb the two
    # peers' own exception vocabulary (`fail()` / `errors.ValidationError`)
    # and dataclass-field-naming difference (`ResourceLimits`'s fields
    # already equal the budget class names; `FoundationConfig`'s do not)
    # OUTSIDE the pinned body -- `_normalize` above is widened the same way
    # the package-name substitution already works, folding both peers' own
    # `ResourceLimits`/`FoundationConfig` class names together -- and the
    # one remaining real behavioural gap (`budget == {}` reconstructing a
    # freshly-equal-but-not-identical object on this peer, versus returning
    # the SAME already-deployed object unchanged on MitateDB-api) is fixed
    # here (`if not budget:`, matching MitateDB's own established
    # behaviour) so both peers now return `deployed` itself, unchanged, for
    # BOTH `None` and `{}`.
    ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "normalize_request_for_idempotency"),
    ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "idempotency_digest"),
    ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "narrow_limits_by_budget"),
    # Phase 9 O-7 pair-closing commit (版フリップ監査, ruling
    # `{scratchpad}/rulings-r3-r7-flip.md` 追補4 O-7): `errors.violation`/
    # `observed_type_of` (the shared 4-key `details` builder / `observed_
    # type` classifier both peers' own `errors.py` carry under this same
    # name, O-7 prep already left in place, unregistered, on both sides)
    # and `platform_declarations.check_contract_170_declarations`/`ops_
    # module_hint` (WP-2e/WP-3e rework's own F-14 check and its PEER_
    # MODULE-reading hint, L-8: "pair-closing の対象にする"). Verified
    # normalize-and-diff equal (`_isomorphic_symbol_source` + `_normalize`,
    # both sides) before adding. `ops._served_capabilities_document` is
    # deliberately NOT a row here: O-7's own text extracts it out of
    # `_verify_declarations_checks` under a shared name so THAT function's
    # body stops carrying peer-specific complexity -- the helper itself
    # keeps each peer's own real construction path (this peer's plain
    # `DataService`, MitateDB's own `FoundationConfig`-fronted
    # `ApplicationCell`) and is not, and was never meant to be, isomorphic.
    ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "violation"),
    ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "observed_type_of"),
)


def test_isomorphic_target_table_is_pinned_to_its_current_97_rows() -> None:
    """WP-0 completion condition 8 (widened by the WP-3 追補, supervisor
    ruling 2026-09-04; widened again by Q4 phase WP-0, supervisor ruling
    2026-09-05, first pass and 差し戻し round / 裁定 A; widened a third
    time by the WP-0 最終追補, supervisor ruling 2026-09-05, 裁定 4;
    widened a fourth time by Q4 phase WP-2, monitor ruling 2026-09-05, 裁定
    5 -- the pair's later half adds both WP-1's and WP-2's own new rows in
    one commit; widened a fifth time by phase 7 WP-4, supervisor supplement
    2026-09-06, 差し戻し指示 9: `_live_pg_backend_count`, byte-identical on
    both peers' own HTTP conformance plug; widened a sixth time by phase 8
    WP-4 rework round 2, supervisor ruling 2026-09-06, wp4-rework-2.md #1
    (acceptance audit completion condition 9 finding): `_verify_
    declarations_checks`/`cmd_verify_declarations` and five same-named
    `tests/test_ops_verify_declarations.py` constants, verified normalize-
    and-diff equal before adding, not assumed from `ops.py`'s own header
    comment that already claimed them "pinned"); widened a seventh time by
    the phase 9 R-2 pair-closing commit (裁定 T-2, work order §4 の 12 / §6
    訂正註 10), once WP-2a and WP-3a's own same-named `validate_enum_
    declaration`/`enum_member_matches_type` pair had both merged to main;
    widened an eighth time by the phase 9 R-4 pair-closing commit (design
    D-4 (7)/追補 2 S-a, 監督裁定 F-7), once WP-2b and WP-3b's own
    same-named `normalize_request_for_plan`/`compute_plan_token` pair had
    both merged to main; widened again by the phase 9 O-7 pair-closing
    commit (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
    追補4 O-7), once WP-2e and WP-3e's own same-named `errors.violation`/
    `observed_type_of` had both merged to main (`platform_declarations.
    check_contract_170_declarations`/`ops_module_hint` were already rows
    here on this peer; only MitateDB-api's own copy of this table needed
    those two added):
    a bare `len(_ISOMORPHIC_TARGETS) == 57` check would not
    catch a row silently DROPPED and a different, coincidentally-same-
    length row added in its place -- only pinning the table's own full
    CONTENT (not merely its length) catches that. One-time human
    fixation, same character as Phase 5's "走査対象フィールド集合を pin
    する" test -- a future WP that adds/removes a row edits this
    assertion deliberately, not by accident.

    Self-referential by supervisor ruling (2026-09-04): this function's own
    row, and `_isomorphic_symbol_source`'s, are both IN the table below --
    the table fixes its own driving code isomorphic too, rather than
    treating the mechanism as exempt from the guarantee it enforces on
    every other row. This is not circular: the assertion below is a NAME
    pinned as data (a 3-tuple of strings), evaluated once at call time
    against the already-fully-defined `_ISOMORPHIC_TARGETS` above -- it
    does not recurse into calling itself."""
    assert _ISOMORPHIC_TARGETS == (
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_src_files"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_literal_leaves"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_name_or_attribute_targets"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_is_field_assignment_target"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_collect_direct_shadow_names"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_analyze_field_scope"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_FieldForwardResolver"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_scan_source_field_sites"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_iter_field_definitions"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_field_positional_definitions"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_excluded_definition_forwards_its_own_parameter"),
        ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_optional_float"),
        ("tests/test_http.py", "tests/test_http.py", "test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "_isomorphic_symbol_source"),
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_97_rows"),
        ("src/r2db_api/auth.py", "src/mitatedb_api/credential_wire.py", "compose_bearer_locator"),
        ("src/r2db_api/auth.py", "src/mitatedb_api/credential_wire.py", "split_bearer_locator"),
        (
            "tests/test_control_plane_store.py",
            "tests/test_control_plane_store.py",
            "test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest",
        ),
        ("src/r2db_api/pg_timeouts.py", "src/mitatedb_api/pg_timeouts.py", "ms_from_pg_timeout_text"),
        (
            "tests/test_platform_upgrade_ledger_scan.py",
            "tests/test_platform_upgrade_ledger_scan.py",
            "scan_platform_upgrade_ledger_script",
        ),
        (
            "tests/test_platform_upgrade_ledger_scan.py",
            "tests/test_platform_upgrade_ledger_scan.py",
            "template_seed_numbers",
        ),
        (
            "tests/test_platform_upgrade_ledger_scan.py",
            "tests/test_platform_upgrade_ledger_scan.py",
            "_strip_sql_comments",
        ),
        (
            "tests/test_platform_upgrade_ledger_scan.py",
            "tests/test_platform_upgrade_ledger_scan.py",
            "_iter_ledger_statements",
        ),
        (
            "tests/test_platform_upgrade_ledger_scan.py",
            "tests/test_platform_upgrade_ledger_scan.py",
            "_strip_string_literals",
        ),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "PlatformDeclarationError"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "reject_removed_timeout_env"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "reject_removed_surface_env"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "Surfaces"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "PlatformDeclarations"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_surfaces_value"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_coalescing_window_value"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_audit_writer_roles_value"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_platform_declarations"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "RoleTimeoutCatalog"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_declared_role_timeouts"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "derive_visibility_lag_ms"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "read_effective_timeouts_ms"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_writer_role_timeouts"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_control_surface_consistency"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "require_control_surface_declared"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f1_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f2_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f3_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f3c_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4b_window_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f4b_writer_roles_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f5_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f6_forward_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f6_reverse_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f7_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f8_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f9_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f10_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f11_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f13_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_contract_170_declarations"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "ops_module_hint"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_upsert_declaration"),
        (
            "src/r2db_api/platform_declarations.py",
            "src/mitatedb_api/platform_declarations.py",
            "VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS",
        ),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "PlatformUpgradeError"),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "discover_upgrade_scripts"),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "read_applied_upgrade_numbers"),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "pending_upgrade_numbers"),
        (
            "src/r2db_api/platform_upgrades.py",
            "src/mitatedb_api/platform_upgrades.py",
            "require_application_upgrades_applied",
        ),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "_f12_message"),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "summarize_upgrade_run"),
        ("src/r2db_api/platform_upgrades.py", "src/mitatedb_api/platform_upgrades.py", "ApplicationUpgradeResult"),
        (
            "conformance/conformance_adapter_r2db_http.py",
            "conformance/conformance_adapter_mitatedb_http.py",
            "_live_pg_backend_count",
        ),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_VERIFY_DECLARATIONS_EXIT_CODES"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_VERIFY_DECLARATIONS_READ_ORDER"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_ok"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_fail"),
        # WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #8): the
        # code review's own normalize-and-diff run found these 8 same-named
        # symbols in the two new `tests/test_ops_verify_declarations.py` files
        # (fixture helpers this WP's own test file needed, plus 3 `test_*`
        # bodies whose text is identical once `_normalize` strips each side's
        # own docstring and package name) actually match byte-for-byte after
        # normalization -- verified directly (`_isomorphic_symbol_source` +
        # `_normalize`, both sides) before adding these rows, not assumed from
        # the row's own name. The work order's own "同型性テストの対象" text
        # ("`ops verify-declarations` のテストと、その中で使う同名ヘルパ")
        # covers both halves of that sentence: the fixture helpers below ARE
        # "同名ヘルパ", and these 3 `test_*` functions ARE part of "`ops
        # verify-declarations` のテスト" itself -- so both halves are pinned,
        # not only the helpers. The file's OWN remaining 19 same-named `test_*`
        # functions (one per F-number, `_run_verify`, the two fixtures, etc.)
        # are NOT rows here: their bodies carry real per-peer differences
        # (env var names, `platform.control_dsn` vs `platform.provision_dsn`/
        # `platform.dsn`, migration file names) that `_normalize` does not fold
        # away, so a normalize-and-diff run against them is a real (and
        # correct) mismatch, not an oversight.
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_admin_dsn"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_dsn_with"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_run_psql"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_require_admin_connection"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_sweep_prefix"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_platform_declaration_error_code_attribute_is_not_paraphrased"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_verify_declarations_f9_when_effective_value_disagrees_with_declared"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "test_verify_declarations_exits_0_when_every_check_passes"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_verify_declarations_checks"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "cmd_verify_declarations"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "ADMIN_DSN_DEFAULT"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "MIGRATIONS_DIR"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "MIGRATION_NAMES_WITHOUT_DECLARATIONS"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_CONTROL_URL"),
        ("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_DATA_URL"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/field_types.py", "validate_enum_declaration"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/field_types.py", "enum_member_matches_type"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "normalize_request_for_plan"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "compute_plan_token"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "normalize_request_for_idempotency"),
        ("src/r2db_api/structured.py", "src/mitatedb_api/cell.py", "idempotency_digest"),
        ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "narrow_limits_by_budget"),
        ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "violation"),
        ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "observed_type_of"),
    )
    assert len(_ISOMORPHIC_TARGETS) == 97


def _isomorphic_symbol_source(peer_root: Path, relative_path: str, symbol: str) -> str | None:
    """Resolves ONE `_ISOMORPHIC_TARGETS` row's own per-side relative path
    against `peer_root` (either this peer's own root or the sibling's) via
    a plain TEXT read + `ast.parse` -- used for BOTH sides now (WP-0's own
    L5-6 fix: previously this peer's own side used `inspect.getsource` --
    which includes any decorator line -- while the sibling side used
    `ast.get_source_segment` -- whose `FunctionDef.lineno` starts at the
    `def`/`class` keyword, never the decorator, per CPython's own AST docs
    -- so a future decorator on either side alone would have flipped this
    test red/green on THAT ASYMMETRY, not on an actual implementation
    difference. Only top-level (`tree.body`) definitions are matched, same
    restriction the WP-2/WP-3 mechanism already applied -- deliberately
    not `ast.walk`, which would also match a same-named symbol nested
    inside an unrelated class/function and silently diff the wrong one.
    Returns `None` if the file does not exist or does not define `symbol`
    at module level (the caller decides what that means for each side).

    Phase 6 WP-3 追補 (supervisor ruling 2026-09-04): takes the row's own
    already-resolved relative path directly -- no `package`/`{package}`
    template parameter -- now that `_ISOMORPHIC_TARGETS` carries one
    literal path per side (a (r2db path, MitateDB path, symbol) triple)
    rather than a single peer-name-independent path plus a template slot
    only one row ever needed.

    WP-1/WP-2 audit-gaps round (supervisor ruling 2026-09-05, wp12-audit-
    gaps.md G4): also matches a module-level `Assign` whose target is a
    bare `Name` equal to `symbol` -- `_ISOMORPHIC_TARGETS` rows are not
    only function/class definitions any more (`VISIBILITY_LAG_CLOCK_SKEW_
    MARGIN_MS = 1000` is a plain module constant), and the prior form
    returned `None` for any such row, silently excusing it from the
    isomorphism check rather than comparing it.

    Phase 7 WP-4 (supervisor supplement 2026-09-06, 差し戻し指示 9): if no
    module-level match is found, ALSO matches a method defined directly in
    a top-level class's own body (one explicit level of nesting, never
    deeper -- still not `ast.walk`, which would also match a same-named
    method nested arbitrarily deep inside an unrelated class and silently
    diff the wrong one). `_live_pg_backend_count` is a method of each
    peer's own HTTP conformance adapter class (`R2DBHttpConformance
    Adapter` / `MitateDBHttpConformanceAdapter`) -- those two classes are
    named DIFFERENTLY per peer, so the table's own single shared `symbol`
    string cannot itself be class-qualified; searching every top-level
    class's own direct body for a same-named method keeps this exactly as
    deliberate as the module-level match above, while staying agnostic to
    which class each peer happens to name it under."""
    path = peer_root / relative_path
    if not path.exists():
        return None
    source = path.read_text()
    tree = _ast.parse(source, filename=str(path))
    node = next(
        (
            n
            for n in tree.body
            if (isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)) and n.name == symbol)
            or (isinstance(n, _ast.Assign) and any(isinstance(t, _ast.Name) and t.id == symbol for t in n.targets))
        ),
        None,
    )
    if node is None:
        node = next(
            (
                m
                for c in tree.body
                if isinstance(c, _ast.ClassDef)
                for m in c.body
                if isinstance(m, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and m.name == symbol
            ),
            None,
        )
    if node is None:
        return None
    return _ast.get_source_segment(source, node)


import re  # noqa: E402 -- kept local to this test-support block, mirrors this file's own late-import style; Q4 phase WP-0 差し戻し round (裁定 D): hoisted from inside `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` to module level, alongside `_strip_leading_docstring`/`_normalize` below, so `_normalize`'s own strictness (does it ever fold two DIFFERENT numeric literals together?) can be pinned by a standalone test without duplicating its body.


def _strip_leading_docstring(source: str) -> str:
    """Phase 6 WP-3 追補 (isomorphism table extension, supervisor
    ruling 2026-09-04): removes the function/class body's own leading
    docstring (a bare `Expr(Constant(str))` as the first body
    statement) BEFORE comparison -- prose is not shape, and the two
    peers' own docstrings for the same symbol legitimately differ (one
    names itself "this peer's own X", the other "MitateDB-api's own
    X"; see e.g. `compose_bearer_locator`'s two docstrings). Located
    via `ast` (the docstring statement's own `lineno`/`end_lineno`
    against THIS already-extracted, syntactically self-contained
    segment), then deleted as TEXT -- never `ast.unparse`, which would
    also reformat everything else the docstring did not touch (quote
    style, line wrapping, trailing commas) and so could paper over a
    real shape difference this comparison exists to catch. A symbol
    with no leading docstring is returned unchanged."""
    tree = _ast.parse(source)
    target = tree.body[0]
    body = getattr(target, "body", None)
    if not body:
        return source
    first = body[0]
    if not (isinstance(first, _ast.Expr) and isinstance(first.value, _ast.Constant) and isinstance(first.value.value, str)):
        return source
    lines = source.splitlines(keepends=True)
    del lines[first.lineno - 1 : first.end_lineno]
    return "".join(lines)


def _normalize(source: str) -> str:
    """WP-3 fix-round M-2 (Opus review): normalizes ONLY (a) the
    symbol's own leading docstring (dropped entirely -- WP-3 追補,
    supervisor ruling 2026-09-04), (b) BOTH peers' own package names
    (each substituted for the SAME neutral placeholder), (c) TRAILING
    whitespace at the end of each line, and (d) the number of
    consecutive blank lines (collapsed to none) -- NEVER leading
    indentation, NEVER in-line token spacing, and NEVER a numeric
    literal's own digits (pinned by `test_isomorphic_normalizer_does_
    not_absorb_numeric_literals` below -- acceptance-audit 変異 A:
    loosening this normalizer to ALSO fold numeric literals together let
    a peer's silently-drifted hour-to-ms multiplier go undetected by
    `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`). The
    PRIOR form (`re.sub(r"[ \t]+", " ", text)`) collapsed every run of
    spaces/tabs ANYWHERE, including a line's own leading indentation --
    which made a nesting-depth-only mutation (moving a branch one `if`/
    `else` level deeper, or shallower, with the exact same token
    sequence and no operator/condition change at all) invisible to
    this comparison: Python's own semantics are indentation-sensitive,
    so an indentation-only edit is a REAL logic change this test must
    catch, not whitespace noise to discard. WP-0 drops the separate
    `peer_module` substitution the WP-2/WP-3 form also took: none of
    the target symbols' own source text (verified when this table was
    assembled) references either peer's test-module name at all, only
    (occasionally) its own package name, so a second substitution
    parameter that never fires is dead generality, not a real need.

    WP-3 追補 round 2 (empirical finding, supervisor ruling
    2026-09-04): switched from a single "this side's own package
    name" substitution to BOTH known package names, symmetrically, on
    EITHER side. A one-name-per-side substitution worked fine while
    every pinned symbol's own text mentioned at most its OWN peer's
    package name -- but this WP's new `_ISOMORPHIC_TARGETS` rows for
    `compose_bearer_locator`/`split_bearer_locator`/the main.py row
    each carry BOTH peers' package names as literal path DATA in the
    SAME tuple (e.g. `"src/r2db_api/main.py"` next to `"src/
    mitatedb_api/main.py"`), and `test_isomorphic_target_table_is_
    pinned_to_its_current_58_rows` literally asserts that whole table
    -- so its own body mentions both names too. A single-name
    substitution leaves the OTHER peer's name untouched differently
    on each side (r2db's own normalization leaves "mitatedb_api"
    alone, MitateDB-api's own leaves "r2db_api" alone), so two
    raw-identical texts would normalize to two DIFFERENT strings --
    a false mismatch this fix removes, without weakening the check
    (both substitutions still collapse to the exact same placeholder,
    so a REAL difference elsewhere in the text is still caught)."""
    text = _strip_leading_docstring(source)
    text = text.replace("r2db_api", "<PEER_PACKAGE>").replace("mitatedb_api", "<PEER_PACKAGE>")
    # Phase 9 R-5/R-6 pair-closing commit: the same "both known spellings,
    # symmetrically, on either side" technique the package-name line above
    # already uses, extended to the two peers' own deployment-limits
    # dataclass names (`ResourceLimits` here, `FoundationConfig` on
    # MitateDB-api) -- `narrow_limits_by_budget`'s own pinned signature
    # names its `deployed`/return type as this peer's own class, the
    # sibling's row names ITS own class, and neither name is peer-name-free
    # the way every pre-existing pinned symbol's signature happened to be.
    text = text.replace("ResourceLimits", "<PEER_TYPE>").replace("FoundationConfig", "<PEER_TYPE>")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def test_isomorphic_normalizer_does_not_absorb_numeric_literals() -> None:
    """Q4 phase WP-0 差し戻し round (supervisor ruling 2026-09-05, 裁定 D
    / acceptance-audit 変異 A): pins that `_normalize` above never folds
    two DIFFERENT numeric literals into the same normalized text. The
    audit demonstrated this empirically -- loosening `_normalize` with an
    extra `re.sub(r"\\b\\d[\\d_]*\\b", "AUDITMUT_NUMLIT", text)` step, then
    drifting one peer's `h`-to-ms multiplier from `3_600_000` to
    `3_500_000`, left `test_peer_local_helpers_are_isomorphic_to_the_
    sibling_peer` GREEN on the loosened side -- a real safety-relevant
    constant could drift undetected. No prior test in this file pinned
    the normalizer's OWN strictness in isolation, only the end-to-end
    isomorphism check's current pass/fail against today's source tree,
    which says nothing about whether a FUTURE loosening would still be
    caught.

    Contrasted with a second assertion proving identifiers, whitespace,
    and a differing leading docstring ARE still absorbed -- this is a
    targeted pin on numeric-literal strictness specifically, not a claim
    that `_normalize` performs no normalization at all."""
    numeric_change_a = 'def _sample():\n    """doc"""\n    return 3_600_000\n'
    numeric_change_b = 'def _sample():\n    """doc"""\n    return 3_500_000\n'
    assert _normalize(numeric_change_a) != _normalize(numeric_change_b)

    absorbed_a = 'def _sample():\n    """doc A"""\n    x = 3_600_000\n    return x\n\n\n'
    absorbed_b = 'def _sample():\n    """doc B, worded completely differently"""\n    x = 3_600_000\n    return x   \n'
    assert _normalize(absorbed_a) == _normalize(absorbed_b)


def test_peer_local_helpers_are_isomorphic_to_the_sibling_peer() -> None:
    """常設規律6: diffs this peer's own `_ISOMORPHIC_TARGETS` symbols
    against MitateDB-api's own same-named symbols at each row's own
    MitateDB-side relative path, after normalizing peer package name /
    the symbol's own leading docstring / trailing whitespace / blank-line
    runs -- proving the two independently (never shared-module)
    implementations agree, without sharing code between peers.

    Table-driven generalization of the WP-2/WP-3 mechanism (design D-4(c),
    L5-5/L5-6): the prior form read one hardcoded sibling file
    (`tests/test_audit_query.py`) and diffed 11 named helpers found inside
    it; `_ISOMORPHIC_TARGETS` above widens that to 24 rows spanning SEVEN
    files per side (measured, not asserted ahead of counting --
    `scratchpad/audit_rows.py`'s own `len()` + unique-path count against
    the table actually defined above: `tests/test_audit_query.py`,
    `src/<package>/main.py`, `tests/test_http.py`, the bearer-locator
    module (`auth.py` on this peer, `credential_wire.py` on MitateDB-api,
    Phase 6 WP-3 追補), `tests/test_control_plane_store.py`, and -- Q4
    phase WP-0 -- `src/<package>/pg_timeouts.py` and `tests/
    test_platform_upgrade_ledger_scan.py` (WP-0 最終追補, supervisor
    ruling 2026-09-05, 裁定 4: three more rows in this SAME already-
    counted file -- the two pinned scanner functions' own peer-duplicated
    sub-helpers -- so the file count stays SEVEN, only the row count
    grows)), so each WP's own new same-named symbols fall under the SAME
    peer-symmetry guarantee a product file (not just a test-support
    helper) would otherwise have had none of. (常設規律 3 / acceptance-
    audit finding: an earlier draft of this docstring claimed "18 rows
    spanning FOUR files" -- already inaccurate for the 18-row table that
    predates Q4 WP-0, which in fact spanned FIVE files, `tests/
    test_control_plane_store.py` having been omitted from the count --
    and was never caught by either the isomorphism check itself, which
    normalizes docstrings out before comparing, or the row-count pin test
    above, which pins the table's
    DATA, not this prose describing it.)

    Fix-round M-2 (Opus review, WP-2/WP-3): the sibling side is read as
    TEXT from its real file path (never `importlib.import_module` -- the
    two peers' packages are not cross-importable from each other's test
    environment without a cross-peer path hack this repository's own
    no-code-sharing convention avoids). A missing sibling file, or a
    present file lacking one of the target symbols (or defining it with
    different content after normalization), each count as a mismatch. The
    resolved sibling root is asserted to point at the MitateDB-api sibling,
    never back at this peer's own root, so a future edit cannot
    accidentally make this a self-comparison."""
    self_root = Path(__file__).resolve().parents[1]
    sibling_root = Path(__file__).resolve().parents[2] / "MitateDB-api"
    assert "MitateDB-api" in sibling_root.parts, f"sibling root must resolve under MitateDB-api, not self: {sibling_root}"
    assert "r2db-api" not in sibling_root.parts, f"sibling root must never resolve back into r2db-api: {sibling_root}"

    mismatches: list[str] = []
    for self_relative_path, sibling_relative_path, symbol in _ISOMORPHIC_TARGETS:
        self_src = _isomorphic_symbol_source(self_root, self_relative_path, symbol)
        if self_src is None:
            raise AssertionError(
                f"this peer's own table row does not resolve against its own tree -- a table bug, not a sibling "
                f"mismatch: {self_relative_path}::{symbol}"
            )
        sibling_src = _isomorphic_symbol_source(sibling_root, sibling_relative_path, symbol)
        if sibling_src is None:
            mismatches.append(f"{sibling_relative_path}::{symbol}")  # not (yet) present on the sibling side
            continue
        if _normalize(self_src) != _normalize(sibling_src):
            mismatches.append(f"{sibling_relative_path}::{symbol}")
    assert not mismatches, f"peer-local symbol(s) not isomorphic after normalization (or missing on the sibling side): {mismatches!r}"


def test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts(platform):
    """Postgres-only (never `pytest.skip` -- design principle 4's "skip is
    fail" applies to this file too): the in-memory backend's own identical
    property (`visibility_lag_ms == 0`, by construction -- no real writer-
    connection timeouts to derive anything from) is asserted directly by
    `test_in_memory_visibility_lag_ms_is_zero_by_construction` below,
    never skipped."""
    h = _postgres_harness(platform, audit_statement_timeout_ms=3_000, audit_idle_timeout_ms=4_000)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 3_000 + 4_000 + 1_000
    finally:
        h.cleanup()


def test_in_memory_visibility_lag_ms_is_zero_by_construction():
    h = _memory_harness()
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 0
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_coalescing_window_ms_matches_the_design_value(kind, platform):
    """WP-2(b) fix round 2 (coordinator item H): `DECLARED_COALESCING_
    WINDOW_MS` is now DERIVED from `service._DENIAL_COALESCE_WINDOW_S`
    (`audit_query.py`'s own import), so this checks the declaration
    against the REAL source value directly, not two independently-
    maintained literals that happen to agree today."""
    from r2db_api.service import _DENIAL_COALESCE_WINDOW_S

    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["capabilities"]["audit_query"]["coalescing_window_ms"] == int(_DENIAL_COALESCE_WINDOW_S * 1000)
        assert DECLARED_COALESCING_WINDOW_MS == int(_DENIAL_COALESCE_WINDOW_S * 1000)
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_count_note_documents_the_never_zero_or_one_rule(kind, platform):
    """WP-2(b) review B-1 (supervisor ruling): the declaration itself
    documents that `count`, when present, is never 0 or 1."""
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        note = document["capabilities"]["audit_query"]["count_note"]
        assert "never" in note.lower()
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_cursor_note_and_cross_filter_cursor_reuse(kind, platform):
    """WP-2(b) fix round 2 (coordinator ruling, item E): the declaration
    documents that `cursor` is a filter-independent position token, and a
    cursor obtained under one `event_classes` filter is genuinely accepted
    (never VALIDATION_FAILED) as `after` under a DIFFERENT filter --
    exercising the more-permissive-than-required conformance the ruling
    itself calls out."""
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        note = document["capabilities"]["audit_query"]["cursor_note"]
        assert "filter" in note.lower()

        marker = "cursorreuse" + secrets.token_hex(4)
        _write_application_audit_row(h, event_class="data_operation", request_id=f"{marker}-0", application_id=marker)
        _write_application_audit_row(h, event_class="privilege_sensitive", request_id=f"{marker}-1", application_id=marker)
        _wait_for_visibility(h)

        filtered = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "event_classes": ["data_operation"]})
        first_cursor = next(e["cursor"] for e in filtered["events"] if e.get("request_id") == f"{marker}-0")

        # Reused under a DIFFERENT filter (privilege_sensitive, not
        # data_operation) -- must resolve, never VALIDATION_FAILED, and
        # must correctly return the second (later) row.
        reused = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "after": first_cursor, "event_classes": ["privilege_sensitive"]})
        assert any(e.get("request_id") == f"{marker}-1" for e in reused["events"]), (
            f"{kind}: a cursor reused under a different filter must still resolve to the correct position"
        )
    finally:
        h.cleanup()


# ===========================================================================
# audit_requests_per_minute -- its own, separate window (M-8 / P4-D4 item 8).
# ===========================================================================


def test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute():
    clock_state = {"now": 0.0}
    h = _memory_harness(clock=lambda: clock_state["now"])
    try:
        h.service._limits = ControlPlaneLimits(  # noqa: SLF001 -- test-only tight window
            applications=100_000, credentials_per_application=100_000,
            control_requests_per_minute=100_000, audit_requests_per_minute=3,
        )
        for _ in range(3):
            h.service.audit_query(h.control_credential_secret, {"limit": 1})
        with pytest.raises(FoundationError) as exc:
            h.service.audit_query(h.control_credential_secret, {"limit": 1})
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.details["limit_class"] == "audit_requests_per_minute"
    finally:
        h.cleanup()


def test_audit_query_does_not_consume_the_control_requests_per_minute_window():
    """M-8: hammering `audit_query` up to its own window's limit must never
    exhaust `control_requests_per_minute` -- a break-glass `revoke_
    credential` must still succeed right after."""
    clock_state = {"now": 0.0}
    h = _memory_harness(clock=lambda: clock_state["now"])
    try:
        h.service._limits = ControlPlaneLimits(  # noqa: SLF001
            applications=100_000, credentials_per_application=100_000,
            control_requests_per_minute=2, audit_requests_per_minute=100_000,
        )
        for _ in range(50):
            h.service.audit_query(h.control_credential_secret, {"limit": 1})
        # `control_requests_per_minute` is still fresh -- register_application
        # (an ordinary control-window-charging operation) succeeds twice,
        # exactly its own configured ceiling, proving audit_query spent
        # nothing from this window.
        h.service.register_application(h.control_credential_secret, "auditwin" + secrets.token_hex(4))
        h.service.register_application(h.control_credential_secret, "auditwin" + secrets.token_hex(4))
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(h.control_credential_secret, "auditwin" + secrets.token_hex(4))
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.details["limit_class"] == "control_requests_per_minute"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_audit_requests_per_minute_is_declared_enforced_in_control_capabilities(kind, platform):
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["limits"]["audit_requests_per_minute"] == 100_000
        assert document["limit_enforcement"]["audit_requests_per_minute"] == "enforced"
    finally:
        h.cleanup()


# ===========================================================================
# contract_version 1.5.0 (Phase 5 WP-2 flip -- design D-4/§8: lands in the
# same commit as the `operations`/`target_kinds` declaration keys and the
# generalized scanner above; both plane declarations move together).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_control_capabilities_declares_contract_version_1_5_0(kind, platform):
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["contract_version"] == "1.7.0"  # contract 1.7.0, WP-2e version flip
    finally:
        h.cleanup()


def _seed_application_credential(credentials: CredentialStore, application_id: str, role: str) -> "AuthContext":
    """`CredentialStore.add` directly (never `ControlAuthority.issue_
    credential`, which requires an already-generated `credential_id`/
    `secret` pair -- `ControlPlaneService.issue_credential` is what
    normally generates those; these tests only need a real, authenticable
    application credential to exist, not the full issuance flow).

    Phase 6 WP-2 (design D-1(c)): the second element returned is the
    COMPOSED `<credential_id>.<secret_part>` locator, not the raw secret
    half `.add` was seeded with -- every caller below presents it straight
    as a bearer.
    """
    credential_id = "crd_" + secrets.token_hex(8)
    secret = "audit-query-app-cred-" + secrets.token_urlsafe(8)
    with credentials.unit_of_work() as work:
        credentials.add(credential_id, application_id, role, secret, work=work)
    return AuthContext(credential_id, application_id, role), compose_bearer_locator(credential_id, secret)


def test_data_plane_capabilities_declares_contract_version_1_5_0_and_audit_query_unavailable():
    credentials = CredentialStore(pepper=APP_PEPPER)
    service = DataService(credentials)
    application_id = "dpver" + secrets.token_hex(4)
    from r2db_api.service import ControlAuthority as _CA

    authority = _CA(service)
    authority.register_application(application_id)
    context, _secret = _seed_application_credential(credentials, application_id, "runtime")
    document = service.capabilities(context)
    assert document["contract_version"] == "1.7.0"  # contract 1.7.0, WP-2e version flip
    assert document["capabilities"]["audit_query"] == {"status": "unavailable", "authority": "control_or_audit"}


# ===========================================================================
# HTTP route table -- two paths, one handler; CAPABILITY_UNSUPPORTED not
# 404; application credential FORBIDDEN.
# ===========================================================================


def _auth(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


async def test_control_host_serves_both_audit_query_paths_with_one_handler():
    """WP-2(b) review m-5 (supervisor ruling 2026-09-03; scratchpad/
    wp2-extra-requirements.md item 2's own "応答同一性" requirement): the
    two paths' response BODIES must be identical, not merely share the
    same top-level key set -- a bug that shaped the response differently
    per path (while both still validated as `{"events": [...]}`) would
    have passed the old, weaker `set(...) == {"events"}` assertion."""
    h = _memory_harness()
    try:
        route_map = {route.path: route.endpoint for route in _ROUTES if route.path.endswith("audit/query")}
        assert set(route_map) == {"/control/v1/audit/query", "/v1/audit/query"}
        assert route_map["/control/v1/audit/query"] is route_map["/v1/audit/query"]

        # A real, durable row so the two responses have actual content to
        # compare, not just an empty `{"events": []}` both ways (which
        # would trivially satisfy body equality without proving anything).
        marker = "twopaths" + secrets.token_hex(4)
        _write_application_audit_row(h, event_class="data_operation", request_id=marker, application_id=marker)
        _wait_for_visibility(h)

        transport = httpx.ASGITransport(app=create_control_app(h.service))
        async with httpx.AsyncClient(transport=transport, base_url="http://r2db-audit.example.invalid") as client:
            headers = _auth(h.control_credential_secret)
            canonical = await client.post("/control/v1/audit/query", headers=headers, json={"limit": 1000})
            alias = await client.post("/v1/audit/query", headers=headers, json={"limit": 1000})
            assert canonical.status_code == alias.status_code == 200
            assert canonical.json() == alias.json(), "the two paths must answer with the byte-identical response body"
            assert any(e.get("request_id") == marker for e in canonical.json()["events"]), "the probe row must actually be present"
    finally:
        h.cleanup()


async def test_application_credential_is_forbidden_on_the_control_host_audit_query():
    h = _memory_harness()
    try:
        app_id = "fbdapp" + secrets.token_hex(4)
        h.authority.register_application(app_id)
        _context, app_secret = _seed_application_credential(h.credentials, app_id, "runtime")

        transport = httpx.ASGITransport(app=create_control_app(h.service))
        async with httpx.AsyncClient(transport=transport, base_url="http://r2db-audit.example.invalid") as client:
            response = await client.post("/control/v1/audit/query", headers=_auth(app_secret), json={"limit": 1})
            assert response.status_code == 403
            assert response.json()["code"] == "FORBIDDEN"
    finally:
        h.cleanup()


async def test_data_plane_host_audit_query_still_refuses_with_capability_unsupported():
    from r2db_api.http import create_app

    credentials = CredentialStore(pepper=APP_PEPPER)
    service = DataService(credentials)
    from r2db_api.service import ControlAuthority as _CA

    authority = _CA(service)
    app_id = "dpstub" + secrets.token_hex(4)
    authority.register_application(app_id)
    _context, app_secret = _seed_application_credential(credentials, app_id, "runtime")

    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://r2db-data.example.invalid") as client:
        response = await client.post("/v1/audit/query", headers=_auth(app_secret), json={})
        assert response.status_code == 400
        assert response.json()["code"] == "CAPABILITY_UNSUPPORTED"


# Phase 4 ledger closure WP-B3 review fix (M4, 監督採用): the vocabulary
# below is grounded in a real `grep` of this peer's own source tree, not
# guessed. r2db-api has no dedicated `control_auth.py`/`control_
# credential_store_postgres.py` modules the way MitateDB-api does -- its
# in-memory `ControlCredentialStore` lives inside `auth.py` (alongside the
# data-plane's own, legitimately-imported `CredentialStore`/`AuthContext`)
# and its `PostgresControlCredentialStore` lives inside `credential_
# store.py` (alongside the data-plane's own, legitimately-imported
# `PostgresCredentialStore`/`PostgresApplicationAuditSink`) -- so checking
# EITHER module name here would false-positive on `main.py`'s own real,
# required imports. `control_plane` is the one module name safe to check:
# `main.py` (the DATA-plane root) has no legitimate reason to import
# anything from it at all.
_R2DB_FORBIDDEN_CONTROL_CREDENTIAL_IDENTIFIERS = frozenset(
    {"ControlCredentialStore", "PostgresControlCredentialStore", "ControlPlaneService"}
)
_R2DB_FORBIDDEN_CONTROL_CREDENTIAL_MODULES = frozenset({"control_plane"})


def _control_credential_vocabulary_hits(source: str, *, forbidden_identifiers: frozenset, forbidden_modules: frozenset) -> list[str]:
    """AST-based replacement (review fix M4) for the prior bare
    case-insensitive substring check. Reasons this is a strictly STRONGER
    form than string-containment, not merely a different one:

    - A source-level string check cannot distinguish an actual Python
      reference (`ControlPlaneService(...)`) from an unrelated string
      literal that happens to contain the same characters (e.g. this
      peer's own `MITATEDB_CONTROL_CREDENTIAL_PEPPER`-shaped env-var
      names on MitateDB-api's sibling test -- those only ever appear as
      `ast.Constant` string arguments, e.g. `env.get("...")`, which this
      walk never inspects at all: no special-case stripping is needed
      here, unlike the substring form it replaces).
    - `ast.parse` is used, never `import` -- `r2db_api.main` ends with a
      module-level `app = build_app()` that reads `os.environ` immediately
      on import (this function's own docstring explains why below).
    - Checks BOTH import statements (`Import`/`ImportFrom` -- the module
      path itself, split on ".", and every imported name's own original
      AND locally-bound (`asname or name`) spelling) AND every other
      reference anywhere in the module body (`ast.Name.id`, `ast.
      Attribute.attr` -- catching `some_module.ControlPlaneService`-style
      access after a bare `import some_module`, which an import-statement-
      only check would miss)."""
    tree = _ast.parse(source)
    hits: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                if any(part in forbidden_modules for part in alias.name.split(".")):
                    hits.append(f"line {node.lineno}: import {alias.name!r}")
                bound = alias.asname or alias.name.split(".")[-1]
                if bound in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: import bound as {bound!r}")
        elif isinstance(node, _ast.ImportFrom):
            module = node.module or ""
            if any(part in forbidden_modules for part in module.split(".")):
                hits.append(f"line {node.lineno}: from {module!r} import ...")
            for alias in node.names:
                if alias.name in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: from {module!r} import {alias.name!r}")
                bound = alias.asname or alias.name
                if bound in forbidden_identifiers:
                    hits.append(f"line {node.lineno}: bound as {bound!r}")
        elif isinstance(node, _ast.Name):
            if node.id in forbidden_identifiers:
                hits.append(f"line {node.lineno}: Name {node.id!r}")
        elif isinstance(node, _ast.Attribute):
            if node.attr in forbidden_identifiers:
                hits.append(f"line {node.lineno}: Attribute .{node.attr!r}")
    return hits


def test_data_plane_composition_root_does_not_import_the_control_credential_store():
    """D-5's own "壊れるシナリオ" (i): the application-plane composition
    root must never gain a reference to the control-credential universe.
    Reads the SOURCE FILE directly (never `import r2db_api.main` -- that
    module ends with a module-level `app = build_app()` that reads
    `os.environ` at import time and would require yet another placeholder-
    env dance for a test that only wants to inspect its syntax tree), then
    `ast.parse`s it (never regex/substring, review fix M4 -- see
    `_control_credential_vocabulary_hits`'s own docstring)."""
    main_py = Path(__file__).resolve().parents[1] / "src" / "r2db_api" / "main.py"
    source = main_py.read_text()
    hits = _control_credential_vocabulary_hits(
        source,
        forbidden_identifiers=_R2DB_FORBIDDEN_CONTROL_CREDENTIAL_IDENTIFIERS,
        forbidden_modules=_R2DB_FORBIDDEN_CONTROL_CREDENTIAL_MODULES,
    )
    assert not hits, f"r2db_api/main.py references the control-credential universe: {hits!r}"


# ===========================================================================
# [MitateDB WP-3(b) 対称 evidence-hardening item 2] `control_main.build_
# control_app` -- the composition root's own `R2DB_AUDIT_DSN` env-var
# wiring, pinned down through the REAL `build_control_app(env)` entry
# point (never `assemble_control_stack` directly, which every harness
# above already exercises via its own explicit `audit_dsn=` argument --
# that is a DIFFERENT claim, "the service layer respects an audit_dsn it
# is given", not "the composition root's own env-var reading reaches it").
# ===========================================================================


def test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env(platform):
    """`control_main.py`'s own `audit_dsn = env.get("R2DB_AUDIT_DSN") or
    None` (composition-root env-var read, not the `assemble_control_stack`
    parameter test coverage above already provides) must reach a real
    `GET /control/v1/capabilities` response two ways: `R2DB_AUDIT_DSN`
    unset -> `audit_query: {"status": "unavailable"}` (D-5 M-4's declared
    default), and set to this module's own real `auditreader` DSN ->
    `audit_query.status == "enabled"`. Built through `build_control_app`
    itself (the literal uvicorn/systemd entry point's own factory), not a
    lower-level helper, mirroring `test_credential_persistence.py`'s own
    `test_build_app_serves_capabilities_over_real_http_and_shuts_down_
    cleanly` pattern for `r2db_api.main`'s composition root.
    """
    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    credential_id = "ctl_" + secrets.token_hex(8)
    secret = "audit-dsn-env-" + secrets.token_urlsafe(8)
    try:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, work=work)
            seed_store.rotate(credential_id, secret, work=work)  # clears must_rotate (R-5)

        base_env = {
            "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": CONTROL_PEPPER,
            "R2DB_CREDENTIAL_PEPPER": APP_PEPPER,
            "R2DB_PLATFORM_SCHEMA": platform.schema,
            # Q4 phase WP-1 (design D-2(f)): surfaces are now a DB-side
            # declaration (this file's own `platform` fixture seeds a
            # working `surfaces` row, `_DEFAULT_SURFACES_VALUE`) -- these
            # two env vars are REMOVED and would now fail startup (F-2) if
            # still set here.
        }
        headers = {"authorization": f"Bearer {compose_bearer_locator(credential_id, secret)}"}

        # R2DB_AUDIT_DSN unset entirely -- the D-5 M-4 default.
        unavailable_app = control_main.build_control_app(dict(base_env))
        with TestClient(unavailable_app) as client:
            response = client.get("/control/v1/capabilities", headers=headers)
            assert response.status_code == 200
            assert response.json()["capabilities"]["audit_query"] == {"status": "unavailable"}

        # R2DB_AUDIT_DSN set to the real r2dbsvc_auditreader DSN this
        # module's own `platform` fixture provisions.
        enabled_env = dict(base_env)
        enabled_env["R2DB_AUDIT_DSN"] = platform.auditreader_dsn
        enabled_app = control_main.build_control_app(enabled_env)
        with TestClient(enabled_app) as client:
            response = client.get("/control/v1/capabilities", headers=headers)
            assert response.status_code == 200
            assert response.json()["capabilities"]["audit_query"]["status"] == "enabled"
    finally:
        seed_store.close()


# ===========================================================================
# Phase 4 ledger closure WP-B3 (L4-10, design §11.1 未起票 -- 作業指示書
# WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-10 が正本): `control_main.
# build_control_app` previously never read `request_bytes` from `env` at
# all -- `ControlPlaneLimits(...)`'s construction (§4 lines ~315-323) built
# every field except `request_bytes` from an env var, leaving that one
# field permanently pinned to the dataclass default (1_048_576). MitateDB's
# `control_composition.py:128` (`MITATEDB_CONTROL_REQUEST_BYTES_LIMIT`)
# already wired the equivalent env var; this was the one peer-asymmetric
# gap the ledger closure fixes. Same name as MitateDB-api's own
# `tests/test_control_main.py:165` `test_build_control_app_request_bytes_
# limit_matches_the_declared_one` (work order §4 WP-B3 completion condition
# 7: "MitateDB tests/test_control_main.py:165 と同名・同形").
# ===========================================================================


def test_build_control_app_request_bytes_limit_matches_the_declared_one(platform):
    """R-7's "宣言値と enforce 値が同一ソースから出ることを構造で保証する"
    rule, applied to `R2DB_CONTROL_LIMIT_REQUEST_BYTES`: a custom value
    must change BOTH (i) the declared `limits.request_bytes` a real `GET
    /control/v1/capabilities` response reports, AND (ii) the byte bound
    `RequestByteBoundMiddleware` actually enforces against a real oversized
    request (never only the declaration -- a composition root that wired
    the declared number without also wiring what `create_control_app`
    passes to the middleware would pass a naive "declaration changed" check
    while leaving the OLD bound silently enforced). `create_control_app`
    (`control_http.py:430`) reads `control_service.limits` directly -- the
    SAME `ControlPlaneLimits` instance `capabilities()` reports from -- so
    both readings are, structurally, one source; this test is the
    behavioral proof of that, not a second, independent assumption."""
    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    credential_id = "ctl_" + secrets.token_hex(8)
    secret = "request-bytes-env-" + secrets.token_urlsafe(8)
    try:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, work=work)
            seed_store.rotate(credential_id, secret, work=work)  # clears must_rotate (R-5)

        headers = {"authorization": f"Bearer {compose_bearer_locator(credential_id, secret)}"}
        base_env = {
            "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
            "R2DB_CONTROL_CREDENTIAL_PEPPER": CONTROL_PEPPER,
            "R2DB_CREDENTIAL_PEPPER": APP_PEPPER,
            "R2DB_PLATFORM_SCHEMA": platform.schema,
            # Q4 phase WP-1 (design D-2(f)): surfaces are now a DB-side
            # declaration (this file's own `platform` fixture seeds a
            # working `surfaces` row, `_DEFAULT_SURFACES_VALUE`) -- these
            # two env vars are REMOVED and would now fail startup (F-2) if
            # still set here.
        }

        # (i) declaration: env unset -> the untouched default (1_048_576,
        # behavior-preserving); env set -> the custom value.
        default_app = control_main.build_control_app(dict(base_env))
        with TestClient(default_app) as client:
            response = client.get("/control/v1/capabilities", headers=headers)
            assert response.status_code == 200
            assert response.json()["limits"]["request_bytes"] == 1_048_576

        custom_env = dict(base_env)
        custom_env["R2DB_CONTROL_LIMIT_REQUEST_BYTES"] = "256"
        custom_app = control_main.build_control_app(custom_env)
        with TestClient(custom_app) as client:
            response = client.get("/control/v1/capabilities", headers=headers)
            assert response.status_code == 200
            assert response.json()["limits"]["request_bytes"] == 256

            # (ii) enforcement: the SAME custom app, a real oversized (for
            # the CUSTOM 256-byte bound only -- 1024 bytes stays well
            # UNDER the old 1_048_576 default) `POST /control/v1/
            # applications` body. Review fix (M3, matches measured
            # behavior): 413/`LIMIT_EXCEEDED` is the actual discriminator
            # between "the custom bound is really enforced" and "the OLD
            # bound is still silently in effect" -- a composition root
            # that wires the declaration but not the enforcement (this
            # WP's own mutation 4, second variant) does NOT read back as
            # "still accepted"; `RequestByteBoundMiddleware` never
            # triggers at all under the old, much larger bound, and this
            # 1024-byte body instead fails ordinary `application_id`
            # length validation with a plain 400 -- so 413 is exactly the
            # signal this test needs, not merely "any non-2xx".
            oversized = {"application_id": "a" * 1024}
            response = client.post("/control/v1/applications", headers=headers, json=oversized)
            assert response.status_code == 413
            assert response.json()["code"] == "LIMIT_EXCEEDED"
    finally:
        seed_store.close()
