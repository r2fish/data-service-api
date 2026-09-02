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
from r2db_api.audit_query import DECLARED_AUDIT_EVENT_CLASSES, DECLARED_COALESCING_WINDOW_MS, InMemoryAuditQueryStore
from r2db_api.auth import AuthContext, ControlCredentialStore, CredentialStore

# `r2db_api.control_main` ends with a module-level `app = build_control_
# app()` (design §8 m-10) that reads `os.environ` the instant it is first
# imported -- mirrors `conformance_adapter_r2db_http.py`'s own identical
# `setdefault` guard for the same reason (this file never uses that
# module-level `app`, only `assemble_control_stack`, and every harness
# below builds its own real, per-test/per-module DSNs).
os.environ.setdefault("R2DB_CONTROLPLANE_DSN", "host=/tmp port=1 dbname=r2db_audit_query_test_import_placeholder")
os.environ.setdefault("R2DB_CONTROL_CREDENTIAL_PEPPER", "r2db-audit-query-test-import-placeholder-ctl-pepper")
os.environ.setdefault("R2DB_CREDENTIAL_PEPPER", "r2db-audit-query-test-import-placeholder-app-pepper")

import r2db_api.control_main as control_main  # noqa: E402 -- module object itself (not just `assemble_control_stack`), see `test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env` below
from r2db_api.control_http import _ROUTES, create_control_app  # noqa: E402
from r2db_api.control_main import assemble_control_stack  # noqa: E402
from r2db_api.control_plane import ControlPlaneService, InMemoryControlBackend  # noqa: E402
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
)

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
        control_credential_secret=control_secret, control_credential_id=control_credential_id,
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
    service, stores = assemble_control_stack(
        controlplane_dsn=platform.controlplane_dsn, app_pepper=APP_PEPPER, control_pepper=CONTROL_PEPPER,
        schema=platform.schema, pool_size=2, limits=limits,
        audit_statement_timeout_ms=audit_statement_timeout_ms if audit_statement_timeout_ms is not None else 200,
        audit_idle_timeout_ms=audit_idle_timeout_ms if audit_idle_timeout_ms is not None else 200,
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
        control_credential_secret=control_secret, control_credential_id=control_credential_id,
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
        audit_result = h.service.audit_query(audit_secret, {"limit": 1})
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
        service.audit_query(secret, {"limit": 1})
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"

    document = service.capabilities(secret)
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
        service.audit_query(audit_secret, {"limit": 1})
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.code not in ("FORBIDDEN", "NOT_FOUND")


# WP-2(b) review M-3 (major, supervisor ruling 2026-09-03): a regex over
# `event_class="..."` misses every POSITIONAL call site -- `service.py`'s
# own `_event`/`_control_event` calls pass `event_class` positionally
# (`self._event(context, "authorization_denial", ...)`), never as a
# keyword, so the old `re.findall(r'event_class="...")` scan silently saw
# zero of them (confirmed by mutation: deleting `operation_denial` from
# `DECLARED_AUDIT_EVENT_CLASSES` stayed green). This AST-based scanner
# extracts the real literal from EVERY known emission call site, positional
# or keyword, the same way `test_limit_class_vocabulary.py`'s own AST scan
# fixes `limit_class` against real call sites rather than trusting a regex.
#
# [MitateDB WP-3(b) 対称 evidence-hardening item 1] the scan used to walk
# ONLY service.py/control_plane.py's own source text -- a hand-picked file
# enumeration, not structural coverage. `ops.py`'s `_write_control_audit`
# (a plain module-level function, called positionally-as-`Name`, e.g.
# `_write_control_audit(work.connection, event_class="credential_lifecycle",
# ...)`, never as `something.attr(...)`) is a REAL durable `control_audit`
# emission site that lived entirely outside that two-file enumeration --
# its own literals happen to already be a subset of `DECLARED_AUDIT_EVENT_
# CLASSES` today, so the old scan's blind spot was silent (see this file's
# own `test_ast_scan_now_covers_files_the_old_hardcoded_enumeration_missed`
# below, which mutates one of `ops.py`'s literals to prove the point). Both
# `_scan_event_class_literals` (now also matching plain-`Name` calls, not
# only `Attribute` calls) and `test_declared_event_classes_cover_every_
# emittable_class` below now walk EVERY `*.py` file directly under `src/
# r2db_api/` (`_iter_src_files()`) instead of a hardcoded two-file list, so
# a future new file with its own emission call site can never silently
# fall outside this guard's coverage again.
import ast as _ast  # noqa: E402 -- kept local to this test-support block, mirrors this file's own late-import style

_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "r2db_api"


def _iter_src_files() -> list[Path]:
    """Every top-level `*.py` module in `src/r2db_api/` (never recursive --
    the `contract/` subpackage is data/schema, not emission-call-bearing
    code, and this scan's own job is `r2db_api/*.py`, not a package-wide
    walk). Sorted for deterministic iteration order."""
    return sorted(_SRC_DIR.glob("*.py"))


# (method/function name) -> ("positional", arg_index) | ("keyword", None) |
# ("keyword_optional", None). Every real, DURABLE-ELIGIBLE `event_class`-
# carrying call site anywhere under `src/r2db_api/*.py` is named here --
# `test_every_known_emission_method_name_is_still_called` below is this
# list's own vacuity guard (a renamed/removed method would otherwise
# silently shrink coverage to zero for that site). `_control_event`
# (service.py, `ControlAuthority`'s own PRE-PHASE-4 legacy trail) is
# deliberately NOT here -- its `self._service._audit.append(...)` call
# writes only to the non-durable legacy `AuditSink` (`DataService._audit`),
# never to the durable `application_audit`/`control_audit` tables
# `audit_query` reads, so its own literals (`"control_failure"`/
# `"control_state"`, confirmed by direct AST probe during WP-2(b) review
# M-3's fix) are correctly OUTSIDE the declared vocabulary's scope -- same
# category as `_event`'s own excluded `"authentication"` literal, not an
# omission.
_EVENT_CLASS_CALL_SPECS: dict[str, tuple[str, int | None]] = {
    "_event": ("positional", 1),  # service.py: def _event(self, context, event_class, ...)
    "_denial_event": ("keyword", None),  # service.py: def _denial_event(self, *, event_class, ...)
    "_write_state_audit": ("keyword", None),  # control_plane.py: def _write_state_audit(self, work, *, event_class, ...)
    "_deny": ("keyword", None),  # control_plane.py: def _deny(self, *, ..., event_class, ...)
    # ops.py: def _write_control_audit(conn, *, event_class, ...) -- a
    # plain module-level function (called as `_write_control_audit(...)`,
    # an `ast.Name`, never `something._write_control_audit(...)`, an
    # `ast.Attribute`), the CLI's own direct `control_audit` INSERT for
    # every `python -m r2db_api.ops <cmd>` state-changing command
    # (issue/rotate/revoke-credential, register/enable/disable-application,
    # issue/rotate/revoke-control-credential). This is the file-enumeration
    # gap this test file's own evidence-hardening item 1 closes.
    "_write_control_audit": ("keyword", None),
    # WP-2(b) fix round 2 (audit finding §4-B): sink-DIRECT writes --
    # `self._sink.append(event_class="security_control_failure", ...)`
    # (service.py's overflow-alert path) bypass every method above
    # entirely. "keyword_optional" (not "keyword"): `.append(...)` is also
    # a completely ordinary list/dict method used all over this codebase
    # with NO `event_class` keyword at all (`self._events.append(event)`,
    # `rows.append({...})`, `self._rate_window.append(now)`, ...) -- those
    # must be silently SKIPPED (not flagged as "unresolved"), never
    # confused with a genuine, missed audit emission site.
    "append": ("keyword_optional", None),
}

# `_denial_event`'s OWN two call sites: one passes a literal
# (`service.py`'s `authenticate` except-clause, already captured by this
# scan), the other (`_event`'s own deny-branch) purely FORWARDS the
# `event_class` parameter `_event` itself already received -- not a new
# literal source, since every real caller of `_event` is itself scanned via
# the `"_event"` entry above. Narrow, explicit, verified-by-hand allowlist
# (mirrors `test_limit_class_vocabulary.py`'s own `_KNOWN_DYNAMIC_LIMIT_
# CLASS_NAMES` idiom) -- never a blanket "skip anything unresolved" escape
# hatch.
_KNOWN_DYNAMIC_EVENT_CLASS_FORWARDS = {
    ("service.py", "_denial_event", "event_class"),
    # WP-2(b) fix round 2 (§4-B's own "append" addition surfaced these):
    # every `.append(event_class=event_class, ...)` site in either file
    # forwards an ALREADY-SCANNED enclosing function's own `event_class`
    # parameter -- `_event`/`_write_state_audit`/`_deny` each forward their
    # own parameter to their sink via this exact pattern (their literal
    # callers are captured by those methods' own spec entries above), and
    # `_control_event` (service.py) forwards its own parameter to the
    # LEGACY, deliberately-excluded non-durable trail (same exclusion
    # rationale as its own literals, `_EVENT_CLASS_CALL_SPECS`'s comment
    # above) -- none of these four `.append(...)` call sites is a NEW
    # literal source.
    ("service.py", "append", "event_class"),
    ("control_plane.py", "append", "event_class"),
}


def _scan_event_class_literals(source: str, filename: str) -> tuple[set[str], list[str]]:
    """Returns `(literals, unresolved)` -- `literals` is every string
    literal found at a known call site's `event_class` position;
    `unresolved` describes any matched call site whose `event_class` is
    NOT a plain string literal and not in `_KNOWN_DYNAMIC_EVENT_CLASS_
    FORWARDS` (a future dynamic emission this scanner cannot statically
    resolve -- treated as a finding, not silently skipped).

    Matches BOTH method calls (`node.func` an `ast.Attribute`, e.g.
    `self._sink.append(...)`) AND plain function calls (`node.func` an
    `ast.Name`, e.g. `ops.py`'s own `_write_control_audit(conn, ...)`) --
    the file-enumeration gap this scanner's own evidence-hardening item 1
    closed (see `_EVENT_CLASS_CALL_SPECS`'s header comment) turned out to
    be paired with a call-shape gap too: the pre-existing `Attribute`-only
    check would have kept missing `_write_control_audit`'s own call sites
    even after `ops.py` was added to the scanned file set, since every one
    of them is a bare-name call, never a `.method(...)` one.
    """
    tree = _ast.parse(source, filename=filename)
    literals: set[str] = set()
    unresolved: list[str] = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        if isinstance(node.func, _ast.Attribute):
            call_name = node.func.attr
        elif isinstance(node.func, _ast.Name):
            call_name = node.func.id
        else:
            continue
        spec = _EVENT_CLASS_CALL_SPECS.get(call_name)
        if spec is None:
            continue
        kind, index = spec
        value_node: _ast.AST | None = None
        if kind == "positional":
            if len(node.args) > index:
                value_node = node.args[index]
        else:
            value_node = next((kw.value for kw in node.keywords if kw.arg == "event_class"), None)
        if value_node is None:
            if kind == "keyword_optional":
                continue  # an ordinary, unrelated .append(...) call -- not a match at all
            unresolved.append(f"{filename}:{node.lineno}: {call_name}(...) call has no resolvable event_class argument at all")
            continue
        if isinstance(value_node, _ast.Constant) and isinstance(value_node.value, str):
            literals.add(value_node.value)
        elif isinstance(value_node, _ast.Name) and (filename, call_name, value_node.id) in _KNOWN_DYNAMIC_EVENT_CLASS_FORWARDS:
            continue
        else:
            unresolved.append(f"{filename}:{node.lineno}: {call_name}(...)'s event_class is not a string literal ({_ast.dump(value_node)})")
    return literals, unresolved


def test_every_known_emission_method_name_is_still_called():
    """Vacuity guard for `_EVENT_CLASS_CALL_SPECS` itself -- if a method
    named there is renamed/removed, `_scan_event_class_literals` would
    silently stop finding it and this whole regression guard would degrade
    back to under-coverage without anyone noticing. Checked against every
    file `_iter_src_files()` itself scans (not a hardcoded two-file list
    any more), so a name whose only real definition moved to a THIRD file
    (e.g. `ops.py`'s `_write_control_audit`) is still found."""
    sources = {path.name: path.read_text() for path in _iter_src_files()}
    for name in _EVENT_CLASS_CALL_SPECS:
        if name == "append":
            # Not a locally-defined method (it is called ON sink objects
            # defined elsewhere) -- checked as a literal call-site
            # substring instead of a `def` line.
            assert any(".append(" in text for text in sources.values()), "no .append( call site found in any src/r2db_api/*.py file"
            continue
        assert any(f"def {name}(" in text for text in sources.values()), (
            f"{name!r} is in _EVENT_CLASS_CALL_SPECS but no longer defined anywhere in src/r2db_api/*.py"
        )


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_event_classes_cover_every_emittable_class(kind, platform):
    """§9.2 property 5. `DECLARED_AUDIT_EVENT_CLASSES` (audit_query.py) is
    fixed against every REAL `event_class` literal anywhere in `src/
    r2db_api/*.py`, positional or keyword (`_scan_event_class_literals`
    above) -- a regression guard against a future new emission call site
    with no corresponding declared-vocabulary entry. [MitateDB WP-3(b)
    対称 evidence-hardening item 1] this now walks EVERY file `_iter_src_
    files()` returns, not a hardcoded `service.py`/`control_plane.py`
    enumeration -- see that helper's own header comment and `test_ast_
    scan_now_covers_files_the_old_hardcoded_enumeration_missed` below for
    the mutation proof that this structurally closes the old blind spot.
    """
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["event_classes"])
        assert declared == DECLARED_AUDIT_EVENT_CLASSES

        emitted: set[str] = set()
        unresolved: list[str] = []
        for path in _iter_src_files():
            literals, file_unresolved = _scan_event_class_literals(path.read_text(), path.name)
            emitted |= literals
            unresolved += file_unresolved
        assert not unresolved, f"unresolvable event_class call site(s), investigate manually: {unresolved!r}"
        assert emitted, "the AST scanner found zero event_class literals -- it is itself broken"
        # "authentication" (service.py) is the one real literal deliberately
        # excluded -- it never reaches the durable/buffered sink at all
        # (service.py's own `_event` comment). Every other real literal
        # must be a subset of the declared vocabulary.
        durable_eligible = emitted - {"authentication"}
        assert durable_eligible <= declared, f"emittable but undeclared: {durable_eligible - declared!r}"
    finally:
        h.cleanup()


def test_ast_scan_now_covers_files_the_old_hardcoded_enumeration_missed():
    """[MitateDB WP-3(b) 対称 evidence-hardening item 1] structural proof,
    not merely an assertion, that `_iter_src_files()` + `_scan_event_class_
    literals`'s plain-`Name`-call support together actually reach `ops.py`'s
    `_write_control_audit(...)` call sites -- the OLD scan (hardcoded
    `service.py`/`control_plane.py` file list) would never have found these
    at all, regardless of the `Attribute`-vs-`Name` call-shape fix, simply
    because `ops.py` itself was never read.
    """
    ops_py = _SRC_DIR / "ops.py"
    assert ops_py in _iter_src_files(), "ops.py must be part of the scanned file set for this proof to be meaningful"
    literals, unresolved = _scan_event_class_literals(ops_py.read_text(), "ops.py")
    assert not unresolved
    # The three real literals `ops.py`'s own `_write_control_audit(...)`
    # call sites carry (confirmed by direct source inspection during this
    # hardening work) -- all three already happen to be members of
    # `DECLARED_AUDIT_EVENT_CLASSES` today (why the old, narrower scan's
    # blind spot was silent rather than red), which is exactly why the
    # broader mutation test below is the one that actually proves the new
    # coverage is load-bearing.
    assert literals == {"credential_lifecycle", "application_lifecycle", "control_credential_lifecycle"}


def test_mutating_an_ops_py_event_class_literal_to_an_undeclared_value_turns_the_declared_vocabulary_check_red(platform):
    """[MitateDB WP-3(b) 対称 evidence-hardening item 1] the actual mutation
    proof: writes a throwaway copy of `ops.py` (never the real source file
    -- this process never mutates its own checked-out tree) with ONE
    `_write_control_audit(..., event_class="credential_lifecycle", ...)`
    literal changed to a value that is NOT in `DECLARED_AUDIT_EVENT_
    CLASSES`, then re-runs the exact same emittable-vs-declared comparison
    `test_declared_event_classes_cover_every_emittable_class` performs, this
    time against `_iter_src_files()` with the mutated copy substituted in
    for the real `ops.py`. Before this file's own evidence-hardening item 1
    (a hardcoded `service.py`/`control_plane.py` file list, `Attribute`-
    call-only), this exact mutation would have stayed invisible to the old
    scan -- `ops.py` was never read at all -- and this assertion would have
    failed to fail. `platform` (module-scoped, real PostgreSQL) is needed
    only for a real `DECLARED_AUDIT_EVENT_CLASSES` capabilities-document
    round trip via the in-memory harness below, mirroring every other test
    in this section.
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
            literals, file_unresolved = _scan_event_class_literals(source, path.name)
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
# contract_version 1.4.0.
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_control_capabilities_declares_contract_version_1_4_0(kind, platform):
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        assert document["contract_version"] == "1.4.0"
    finally:
        h.cleanup()


def _seed_application_credential(credentials: CredentialStore, application_id: str, role: str) -> "AuthContext":
    """`CredentialStore.add` directly (never `ControlAuthority.issue_
    credential`, which requires an already-generated `credential_id`/
    `secret` pair -- `ControlPlaneService.issue_credential` is what
    normally generates those; these tests only need a real, authenticable
    application credential to exist, not the full issuance flow)."""
    credential_id = "crd_" + secrets.token_hex(8)
    secret = "audit-query-app-cred-" + secrets.token_urlsafe(8)
    with credentials.unit_of_work() as work:
        credentials.add(credential_id, application_id, role, secret, work=work)
    return AuthContext(credential_id, application_id, role), secret


def test_data_plane_capabilities_declares_contract_version_1_4_0_and_audit_query_unavailable():
    credentials = CredentialStore(pepper=APP_PEPPER)
    service = DataService(credentials)
    application_id = "dpver" + secrets.token_hex(4)
    from r2db_api.service import ControlAuthority as _CA

    authority = _CA(service)
    authority.register_application(application_id)
    context, _secret = _seed_application_credential(credentials, application_id, "runtime")
    document = service.capabilities(context)
    assert document["contract_version"] == "1.4.0"
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


def test_data_plane_composition_root_does_not_import_the_control_credential_store():
    """D-5's own "壊れるシナリオ" (i): the application-plane composition
    root must never gain a reference to the control-credential universe.
    Reads the SOURCE FILE directly (never `import r2db_api.main` -- that
    module ends with a module-level `app = build_app()` that reads
    `os.environ` at import time and would require yet another placeholder-
    env dance for a test that only wants to grep its source text)."""
    main_py = Path(__file__).resolve().parents[1] / "src" / "r2db_api" / "main.py"
    source = main_py.read_text()
    assert "control_credential" not in source.lower()
    assert "ControlCredentialStore" not in source
    assert "ControlPlaneService" not in source


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
        }
        headers = {"authorization": f"Bearer {secret}"}

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
