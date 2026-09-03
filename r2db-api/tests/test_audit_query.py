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

_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "r2db_api"


def _iter_src_files() -> list[Path]:
    """Every `*.py` file anywhere under `src/r2db_api/`, found by a
    RECURSIVE `rglob` -- P4-D16 v3(a): a hand-maintained file list, and a
    non-recursive top-level-only `glob`, are both banned by design. A
    future new subpackage's own emission call sites can never silently
    fall outside this guard's coverage. Sorted for deterministic
    iteration order. (`contract/`'s packaged JSON schema copy is not
    `.py`, so it is never picked up regardless of recursion.)"""
    return sorted(_SRC_DIR.rglob("*.py"))


def _collect_direct_shadow_names(body: list) -> set[str]:
    """WP-B1 acceptance-audit round 2 (M8): redesigned around a GENERAL
    principle -- 'any name binding of "event_class" anywhere in a
    function's OWN direct body (never descending into a nested `def`/
    `async def`/`lambda`/`class` -- those are separate scopes) shadows
    it' -- rather than an enumeration of individual statement shapes.
    The PRIOR enumeration (`Assign`/`AugAssign`/`AnnAssign`/`For`/
    `AsyncFor`/`NamedExpr`/`Global`/`Nonlocal`) missed `with ... as
    event_class:`, `except ... as event_class:`, `match` capture
    patterns, `import ... as event_class`, a nested `def event_class`/
    `class event_class`, and `del event_class`. Implementation:

    (i) every `Name(id="event_class")` node whose `ctx` is `Store` or
        `Del` -- this ALONE covers `Assign`/`AugAssign`/`AnnAssign`
        targets, `for`/`async for` targets, comprehension targets,
        walrus (`:=`) targets, `with ... as` targets, and tuple/list/
        starred destructuring of any of the above, and `del
        event_class` -- none of these need a dedicated per-statement
        visitor once `ctx`-based `Name` matching is the rule (a plain
        default `generic_visit` traversal reaches every one of them).
    (ii) `alias.asname == "event_class"` (`import ... as event_class` /
         `from x import y as event_class`).
    (iii) `ExceptHandler.name == "event_class"` (`except ... as
          event_class:` -- a plain string attribute, not a `Name` node,
          so `ctx`-based matching alone cannot see it).
    (iv) `MatchAs.name` / `MatchStar.name` / `MatchMapping.rest` equal
         to `"event_class"` (`match` statement capture patterns -- also
         plain string attributes, not `Name` nodes).
    (v) a NESTED `def`/`async def`/`class` (directly inside this
        function's own body) whose OWN `.name` is `"event_class"` --
        this binds a function/class object under that name in the
        enclosing scope, same as any other local. (An inner lambda's or
        nested function's OWN `event_class` PARAMETER needs no separate
        handling here: `_EventClassForwardResolver`'s stack-based scope
        resolution already resolves a `Name` reference inside that
        inner scope against the INNERMOST frame first, correctly
        blocking it from ever being attributed to an outer function's
        parameter -- the "遮る" ("blocks") relationship is structural,
        not something `_collect_direct_shadow_names` needs to encode.)
    (vi) `Global`/`Nonlocal` names (unchanged).

    Mirrors Python's own scoping rule: a name bound ANYWHERE in a
    function's body (compile-time, not execution-order) is that
    function's local for the WHOLE body, regardless of whether it is
    ALSO a formal parameter of that same function."""
    shadowed: set[str] = set()

    class _ShadowScan(_ast.NodeVisitor):
        def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
            if node.name == "event_class":
                shadowed.add(node.name)
            # do not descend -- separate scope

        def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
            if node.name == "event_class":
                shadowed.add(node.name)
            # do not descend -- separate scope

        def visit_Lambda(self, node: "_ast.Lambda") -> None:
            pass  # separate scope; lambdas have no `.name` to bind -- do not descend

        def visit_ClassDef(self, node: "_ast.ClassDef") -> None:
            if node.name == "event_class":
                shadowed.add(node.name)
            # do not descend -- separate scope

        def visit_Name(self, node: "_ast.Name") -> None:
            if node.id == "event_class" and isinstance(node.ctx, (_ast.Store, _ast.Del)):
                shadowed.add(node.id)

        def visit_alias(self, node: "_ast.alias") -> None:
            if node.asname == "event_class":
                shadowed.add(node.asname)

        def visit_ExceptHandler(self, node: "_ast.ExceptHandler") -> None:
            if node.name == "event_class":
                shadowed.add(node.name)
            self.generic_visit(node)

        def visit_MatchAs(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == "event_class":
                shadowed.add("event_class")
            self.generic_visit(node)

        def visit_MatchStar(self, node: "_ast.AST") -> None:
            if getattr(node, "name", None) == "event_class":
                shadowed.add("event_class")
            self.generic_visit(node)

        def visit_MatchMapping(self, node: "_ast.AST") -> None:
            if getattr(node, "rest", None) == "event_class":
                shadowed.add("event_class")
            self.generic_visit(node)

        def visit_Global(self, node: "_ast.Global") -> None:
            shadowed.update(node.names)

        def visit_Nonlocal(self, node: "_ast.Nonlocal") -> None:
            shadowed.update(node.names)

    scanner = _ShadowScan()
    for stmt in body:
        scanner.visit(stmt)
    return shadowed


class _EventClassForwardResolver(_ast.NodeVisitor):
    """WP-B1 review round 2 (M3/M6): a single, scope-tracking traversal
    that determines, for EVERY `Name(id="event_class", ctx=Load())` node
    in a tree, whether it is a genuine forward of an ENCLOSING function's
    own `event_class` formal parameter -- walked innermost-to-outermost
    over a stack of `(param_names, shadowed_names)` per enclosing
    function/lambda. A name that is local-but-shadowed in the innermost
    scope that claims it (a plain local variable, a `for` target, a
    walrus target, or a `global`/`nonlocal` declaration -- see
    `_collect_direct_shadow_names` above) STOPS resolution there and is
    NEVER treated as a safe forward, even if that same function also
    happens to declare `event_class` as a parameter, and even if an
    OUTER function's own parameter of the same name exists. This closes
    the gap the previous (unscoped) `Name(id="event_class")`-only check
    had: a local variable coincidentally named `event_class` could
    silently carry an undeclared literal straight past both the literal
    -discipline check (b) and the dict-smuggling check (d)."""

    def __init__(self) -> None:
        self.safe_forward_ids: set[int] = set()
        self._stack: list[tuple[set[str], set[str]]] = []

    def _param_names(self, node: "_ast.AST") -> set[str]:
        args = node.args
        names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)}
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
        return names

    def visit_FunctionDef(self, node: "_ast.FunctionDef") -> None:
        self._stack.append((self._param_names(node), _collect_direct_shadow_names(node.body)))
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: "_ast.AsyncFunctionDef") -> None:
        self._stack.append((self._param_names(node), _collect_direct_shadow_names(node.body)))
        self.generic_visit(node)
        self._stack.pop()

    def visit_Lambda(self, node: "_ast.Lambda") -> None:
        # No emit definition in this package is ever a lambda, but a
        # correct frame is still pushed so a lambda parameter named
        # `event_class` cannot be falsely resolved against an OUTER
        # frame instead of its own.
        self._stack.append((self._param_names(node), set()))
        self.generic_visit(node)
        self._stack.pop()

    def visit_Name(self, node: "_ast.Name") -> None:
        if node.id == "event_class" and isinstance(node.ctx, _ast.Load):
            for param_names, shadowed_names in reversed(self._stack):
                if "event_class" in shadowed_names:
                    break  # locally rebound in this scope -- never a safe forward
                if "event_class" in param_names:
                    self.safe_forward_ids.add(id(node))
                    break
                # not local to this frame at all -- Python's own scoping
                # would keep looking outward, so we do too.
        self.generic_visit(node)


def _iter_name_or_attribute_targets(target: "_ast.AST"):
    """WP-B1 acceptance-audit finding M7: decomposes an assignment
    TARGET (including tuple/list/starred unpacking, e.g. `a, event_class
    = ...`) into every leaf `Name`/`Attribute` node it assigns to.
    `Subscript` targets (`d["event_class"] = ...`) are NOT decomposed
    here -- those are the existing, separately-handled dict-smuggling
    scan's own job."""
    if isinstance(target, (_ast.Name, _ast.Attribute)):
        yield target
    elif isinstance(target, (_ast.Tuple, _ast.List)):
        for elt in target.elts:
            yield from _iter_name_or_attribute_targets(elt)
    elif isinstance(target, _ast.Starred):
        yield from _iter_name_or_attribute_targets(target.value)


def _is_event_class_assignment_target(leaf: "_ast.AST") -> bool:
    if isinstance(leaf, _ast.Name):
        return leaf.id == "event_class"
    if isinstance(leaf, _ast.Attribute):
        return leaf.attr == "event_class"
    return False


def _scan_source_event_class_sites(source: str, filename: str) -> tuple[
    list[tuple[int, "_ast.AST", bool]], list[tuple[int, str, "_ast.AST", bool]], list[tuple[int, str, "_ast.AST", bool]]
]:
    """One parse, one `_EventClassForwardResolver` pass over `source`.
    Returns `(keyword_sites, dict_sites, assignment_sites)`:
    - `keyword_sites`: `(lineno, value_node, is_safe_forward)` for every
      `Call` carrying an `event_class=` keyword (P4-D16 v3(b)'s input).
    - `dict_sites`: `(lineno, kind, value_node, is_safe_forward)` for
      every `Dict` literal keyed `"event_class"` (`kind="dict"`) and
      every `x["event_class"] = ...` `Subscript` assignment
      (`kind="subscript"`) (P4-D16 v3(d)'s input).
    - `assignment_sites`: `(lineno, kind, value_node, is_safe_forward)`
      for every `Assign`/`AnnAssign`/`AugAssign` anywhere in `source`
      (EVERY scope -- module top-level, class body, function body alike;
      this is a plain, unconditional `ast.walk`, never scope-restricted)
      whose TARGET (decomposed through tuple/list/starred unpacking) is
      `Name(id="event_class")` (`kind="name_assign"`, e.g. a MODULE- or
      CLASS-level `event_class = "..."`) or `Attribute(attr=
      "event_class")` (`kind="attribute_assign"`, e.g. `self.event_class
      = "..."`). WP-B1 acceptance-audit finding M7: without this, `class
      _Cfg: event_class = "zz"` followed by `event_class=_Cfg.event_class`
      at a real emit call site passed (b)/(c)/(d)/(e) all green -- the
      unconditional `Attribute(attr="event_class")` passthrough in
      `is_forward` below (added for the READ-path case, see the third
      bullet) legitimately accepted the READ `_Cfg.event_class`, but
      nothing was checking what value the WRITE `event_class = "zz"`
      that fed it had actually assigned. This closes that: the value
      side of every such assignment, anywhere, is checked with the SAME
      `is_forward` rule (b)/(d) already use.

    `is_safe_forward` recognizes THREE shapes, none of which can ever
    author a brand-new value -- each only re-exposes something already
    unambiguously named/keyed `event_class` elsewhere:
    - `Name(id="event_class")` bound to an ENCLOSING function's own
      `event_class` PARAMETER (`_EventClassForwardResolver` above; WP-B1
      review round 2 M3/M6 -- a local variable/global/for-target/walrus
      of the identical name is explicitly NOT this and IS a violation).
    - `Attribute(attr="event_class")` (e.g. `event.event_class`) --
      reading an already-durable event/row OBJECT's own `event_class`
      field back out for a READ-path response (r2db-api
      `audit_query.py`'s `_event_dict`, `control_plane.py`'s
      `_shape_audit_query_row`). This is the READ side of D-6/D-7, the
      structural opposite of an emit site: the value it copies was
      already validated wherever it was ORIGINALLY durably written: no
      new literal can be authored by attribute access alone -- PROVIDED
      the assignment_sites check above also holds (an `Attribute` read
      is only as safe as every WRITE that could have produced it).
    - `Subscript` keyed by the literal `"event_class"` (e.g.
      `row["event_class"]`) -- the same READ-path passthrough, one
      layer removed (a dict/row field lookup instead of an attribute)."""
    tree = _ast.parse(source, filename=filename)
    resolver = _EventClassForwardResolver()
    resolver.visit(tree)
    safe_ids = resolver.safe_forward_ids

    def is_forward(value: "_ast.AST") -> bool:
        if isinstance(value, _ast.Name):
            return id(value) in safe_ids
        if isinstance(value, _ast.Attribute):
            return value.attr == "event_class"
        if isinstance(value, _ast.Subscript):
            key_node = value.slice
            return isinstance(key_node, _ast.Constant) and key_node.value == "event_class"
        return False

    keyword_sites: list[tuple[int, "_ast.AST", bool]] = []
    dict_sites: list[tuple[int, str, "_ast.AST", bool]] = []
    assignment_sites: list[tuple[int, str, "_ast.AST", bool]] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            kw = next((k for k in node.keywords if k.arg == "event_class"), None)
            if kw is not None:
                keyword_sites.append((node.lineno, kw.value, is_forward(kw.value)))
        elif isinstance(node, _ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, _ast.Constant) and key.value == "event_class":
                    dict_sites.append((node.lineno, "dict", value, is_forward(value)))
        elif isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Subscript):
                    key_node = target.slice
                    if isinstance(key_node, _ast.Constant) and key_node.value == "event_class":
                        dict_sites.append((node.lineno, "subscript", node.value, is_forward(node.value)))
                for leaf in _iter_name_or_attribute_targets(target):
                    if _is_event_class_assignment_target(leaf):
                        kind = "name_assign" if isinstance(leaf, _ast.Name) else "attribute_assign"
                        assignment_sites.append((node.lineno, kind, node.value, is_forward(node.value)))
        elif isinstance(node, (_ast.AnnAssign, _ast.AugAssign)):
            if node.value is None:
                continue  # a bare annotation (`event_class: str`) with no assigned value at all
            for leaf in _iter_name_or_attribute_targets(node.target):
                if _is_event_class_assignment_target(leaf):
                    kind = "name_assign" if isinstance(leaf, _ast.Name) else "attribute_assign"
                    assignment_sites.append((node.lineno, kind, node.value, is_forward(node.value)))
    return keyword_sites, dict_sites, assignment_sites


def _scan_file_event_class_sites(path: Path):
    return _scan_source_event_class_sites(path.read_text(), path.name)


def _event_class_keyword_call_sites(paths: list[Path]) -> list[tuple[str, int, "_ast.AST", bool]]:
    """P4-D16 v3(b)'s own input, aggregated across files: `(filename,
    lineno, value_node, is_safe_forward)` for every `Call` node anywhere
    in the given files that carries an `event_class=` keyword argument --
    UNFILTERED by callee name."""
    sites: list[tuple[str, int, "_ast.AST", bool]] = []
    for path in paths:
        keyword_sites, _dict_sites, _assignment_sites = _scan_file_event_class_sites(path)
        for lineno, value, is_forward in keyword_sites:
            sites.append((path.name, lineno, value, is_forward))
    return sites


def _scan_event_class_literals(source: str, filename: str) -> tuple[set[str], list[str]]:
    """Single-file variant of the same unfiltered walk (b) performs,
    kept for the `ops.py`-specific regression/mutation-proof tests below
    that substitute a mutated copy of ONE file's text in isolation, and
    for this WP's own new synthetic-source regression tests. Returns
    `(literals, unresolved)`: `literals` is every string literal found at
    an `event_class=` keyword position; `unresolved` describes any such
    call whose value is neither a string literal nor a genuine bound
    parameter forward (`_EventClassForwardResolver` above)."""
    keyword_sites, _dict_sites, _assignment_sites = _scan_source_event_class_sites(source, filename)
    literals: set[str] = set()
    unresolved: list[str] = []
    for lineno, value, is_forward in keyword_sites:
        if isinstance(value, _ast.Constant) and isinstance(value.value, str):
            literals.add(value.value)
        elif is_forward:
            continue
        else:
            unresolved.append(f"{filename}:{lineno}")
    return literals, unresolved


def _event_class_positional_definitions(paths: list[Path]) -> list[str]:
    """P4-D16 v3(c)'s own violation collector: every `def`/`async def`
    anywhere in the given files whose formal parameters include
    `event_class` NOT declared keyword-only (i.e. not in `kwonlyargs`).
    `self`/`cls` (a bound method's own first parameter) is never itself
    named `event_class`, so no separate exclusion is needed beyond a
    plain by-name membership check across every parameter list."""
    violations: list[str] = []
    for path in paths:
        tree = _ast.parse(path.read_text(), filename=path.name)
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            kwonly_names = {arg.arg for arg in node.args.kwonlyargs}
            if "event_class" in kwonly_names:
                continue
            positional_names = {arg.arg for arg in node.args.posonlyargs + node.args.args}
            if "event_class" in positional_names:
                violations.append(f"{path.name}:{node.lineno}: {node.name}(...) takes event_class positionally, not keyword-only")
    return violations


def _event_class_dict_smuggling_violations(paths: list[Path]) -> list[str]:
    """P4-D16 v3(d)'s own violation collector -- WP-B1 review round 2
    (M3/M6) INVERTED this from "flag only a plain string `Constant`
    value" to "allow ONLY the three passthrough shapes
    `_scan_source_event_class_sites` recognizes (a bound parameter
    forward, an `event.event_class` attribute read, or a
    `row["event_class"]` subscript read -- see that function's own
    docstring) and flag everything else": a string `Constant`, an
    f-string (`JoinedStr`), string concatenation (`BinOp`), a function
    `Call` result, an unbound/shadowed `Name`, or an `Attribute`/
    `Subscript` that does NOT read a field literally named
    `event_class` are ALL violations now -- not merely a plain literal
    string. Closes the gap where a non-Constant, non-forward value (an
    f-string smuggled via `**{"event_class": f"..."}`, for instance)
    silently passed the old, narrower check."""
    violations: list[str] = []
    for path in paths:
        _keyword_sites, dict_sites, _assignment_sites = _scan_file_event_class_sites(path)
        for lineno, kind, value, is_forward in dict_sites:
            if is_forward:
                continue
            violations.append(f"{path.name}:{lineno}: {kind} sets event_class to a non-forward value ({_ast.dump(value)})")
    return violations


def _event_class_assignment_violations(paths: list[Path]) -> list[str]:
    """WP-B1 acceptance-audit finding M7's own violation collector: every
    `Assign`/`AnnAssign`/`AugAssign` anywhere in the given files (EVERY
    scope, never restricted to function bodies) whose target is
    `Name(id="event_class")` (a MODULE- or CLASS-level assignment, e.g.
    `class _Cfg: event_class = "zz"`) or `Attribute(attr="event_class")`
    (e.g. `self.event_class = "zz"`) must assign a genuine passthrough
    value (the SAME `is_forward` rule (b)/(d) use) -- a string `Constant`,
    f-string, `BinOp`, `Call` result, or unbound/shadowed `Name` is a
    violation. Closes the gap where `_scan_source_event_class_sites`'s
    own unconditional `Attribute(attr="event_class")` READ-passthrough
    (added for legitimate cases like `event.event_class`) could be fed by
    an UNCHECKED write -- `class _Cfg: event_class = "zz"` followed by
    `event_class=_Cfg.event_class` at a real emit site passed every other
    check green before this."""
    violations: list[str] = []
    for path in paths:
        _keyword_sites, _dict_sites, assignment_sites = _scan_file_event_class_sites(path)
        for lineno, kind, value, is_forward in assignment_sites:
            if is_forward:
                continue
            violations.append(f"{path.name}:{lineno}: {kind} sets event_class to a non-forward value ({_ast.dump(value)})")
    return violations


def test_every_event_class_keyword_argument_is_a_string_literal():
    """P4-D16 v3(b). Every `Call` anywhere under `src/r2db_api/` that
    carries an `event_class=` keyword must pass a plain string literal or
    a genuine bound parameter forward of an ENCLOSING function's own
    `event_class` parameter (`_EventClassForwardResolver` above) -- no
    callee-name filter of any kind. Violations are reported by
    file:line."""
    paths = _iter_src_files()
    violations: list[str] = []
    for filename, lineno, value, is_forward in _event_class_keyword_call_sites(paths):
        if isinstance(value, _ast.Constant) and isinstance(value.value, str):
            continue
        if is_forward:
            continue
        violations.append(f"{filename}:{lineno}: event_class= is not a string literal or a bound parameter forward ({_ast.dump(value)})")
    assert not violations, f"non-literal, non-forwarded event_class= call site(s): {violations!r}"


def test_every_definition_taking_event_class_declares_it_keyword_only():
    """P4-D16 v3(c). Every function/method anywhere under `src/r2db_api/`
    that takes `event_class` as a formal parameter must declare it
    keyword-only -- this is the product-code invariant `_event` (:1112)
    and `_control_event` (:1356) were converted to satisfy (this WP's
    only product-code change). Makes a positionally-passed emit site
    syntactically unwritable, closing the historical "positional call
    sites are invisible to a keyword-only-oriented scan" gap
    structurally rather than by convention."""
    paths = _iter_src_files()
    violations = _event_class_positional_definitions(paths)
    assert not violations, f"definition(s) with a non-keyword-only event_class parameter: {violations!r}"


def test_no_event_class_string_literal_is_smuggled_through_a_dict():
    """P4-D16 v3(d) (WP-B1 review round 2, M3/M6). No `Dict` literal or
    `Subscript` assignment anywhere under `src/r2db_api/` sets an
    `"event_class"` key to anything other than a genuine passthrough of
    an existing `event_class` value (a bound parameter forward, or a
    READ-path `event.event_class`/`row["event_class"]` field read -- see
    `_scan_source_event_class_sites`'s own docstring) -- a plain string
    literal, an f-string, string concatenation, a call result, or an
    unbound/shadowed name are ALL violations, closing the path
    (`**{"event_class": ...}` expansion, or building the sink's field
    dict via subscript assignment) that could otherwise let a
    non-literal, non-forward value reach the durable sink invisibly to
    (b)'s keyword-argument walk."""
    paths = _iter_src_files()
    violations = _event_class_dict_smuggling_violations(paths)
    assert not violations, f"dict/subscript event_class literal smuggling site(s): {violations!r}"


def test_no_event_class_string_literal_is_smuggled_through_an_assignment():
    """WP-B1 acceptance-audit finding M7. No `Assign`/`AnnAssign`/
    `AugAssign` anywhere under `src/r2db_api/` (module top-level, class
    body, or function body -- EVERY scope) assigns a non-forward value to
    a target named/keyed `event_class` (`Name(id="event_class")` or
    `Attribute(attr="event_class")`, tuple/list/starred-unpacked targets
    included). Closes the hole a class/module-level `event_class = "..."`
    (or `self.event_class = "..."`) constant left open: an unconditional
    `Attribute(attr="event_class")` READ passthrough is only as safe as
    every WRITE that could have produced it."""
    paths = _iter_src_files()
    violations = _event_class_assignment_violations(paths)
    assert not violations, f"event_class assignment-target literal smuggling site(s): {violations!r}"


def test_event_class_forward_exclusion_requires_genuine_parameter_binding():
    """WP-B1 review round 2 (M3/M6): the predecessor `_is_forwarded_
    event_class` treated ANY `Name(id="event_class")` as a safe forward,
    regardless of whether that name was actually bound to an ENCLOSING
    function's own `event_class` parameter -- a local variable, global,
    for-loop target, or walrus binding of the identical name could
    silently carry an undeclared literal straight past both (b) and (d).
    Builds SYNTHETIC source text (never touches a real repository file)
    reproducing exactly those two shapes and fixes that both are now
    rejected -- run this test against the PRE-fix resolver (a bare
    `isinstance(value_node, ast.Name) and value_node.id == "event_class"`
    check) to see it go red; that is the round-2 review finding this
    test is load-bearing against.
    """
    # (i) a local variable named `event_class` (never a parameter of the
    # enclosing function `f`), forwarded via `event_class=event_class` --
    # must be rejected by (b)'s own literal-discipline scan, not silently
    # accepted as a forward.
    source_local_var = (
        "def f(sink):\n"
        "    event_class = \"__WPB1_SYNTHETIC_FIXTURE_LOCAL__\"\n"
        "    sink.append(event_class=event_class)\n"
    )
    literals, unresolved = _scan_event_class_literals(source_local_var, "synthetic_local_var.py")
    assert not literals, f"a local-variable-shadowed event_class must never be collected as a literal: {literals!r}"
    assert unresolved == ["synthetic_local_var.py:3"], (
        f"a local-variable-shadowed event_class=event_class must be flagged unresolved, not silently accepted as a forward: {unresolved!r}"
    )

    # (ii) a dict literal with an f-string (`JoinedStr`) value, smuggled
    # into a call via `**{...}` expansion -- must be caught by (d)'s
    # dict-smuggling scan. An f-string is not a plain string `Constant`,
    # so the PRE-round-2 dict check (which flagged only string
    # `Constant` values) silently missed this shape entirely.
    source_dict_fstring = (
        "def g(sink, suffix):\n"
        "    sink.append(**{\"event_class\": f\"__WPB1_SYNTHETIC_FIXTURE_FSTRING_{suffix}__\"})\n"
    )
    _keyword_sites, dict_sites, _assignment_sites = _scan_source_event_class_sites(source_dict_fstring, "synthetic_dict_fstring.py")
    dict_violations = [f"synthetic_dict_fstring.py:{lineno}" for lineno, _kind, _value, is_forward in dict_sites if not is_forward]
    assert dict_violations == ["synthetic_dict_fstring.py:2"], (
        f"an f-string value smuggled through a dict literal's event_class key must be flagged as a violation: "
        f"{dict_violations!r} (raw sites: {dict_sites!r})"
    )

    # (iii) WP-B1 acceptance-audit round 2 (M8): `with ... as event_class:`
    # -- the context manager's bound variable is NOT a parameter forward,
    # even though it is a plain `Name(id="event_class")`. The prior
    # per-statement-shape enumeration in `_collect_direct_shadow_names`
    # never visited `withitem.optional_vars` at all.
    # `h` deliberately DECLARES `event_class` as its own keyword-only
    # PARAMETER too -- the bug this reproduces only manifests when a
    # `with ... as event_class:` REBINDS a name that is ALSO a genuine
    # parameter of the enclosing function: an incomplete shadow-detector
    # would see "event_class is a parameter of h" and stop there,
    # wrongly treating the REBOUND (with-as) value as if it were still
    # the untouched parameter.
    source_with_as = (
        "from contextlib import nullcontext\n"
        "def h(sink, *, event_class):\n"
        "    with nullcontext(\"__WPB1_SYNTHETIC_FIXTURE_WITH__\") as event_class:\n"
        "        sink.append(event_class=event_class)\n"
    )
    literals_with, unresolved_with = _scan_event_class_literals(source_with_as, "synthetic_with_as.py")
    assert not literals_with, f"a with-as-rebound event_class must never be collected as a literal: {literals_with!r}"
    assert unresolved_with == ["synthetic_with_as.py:4"], (
        f"a with-as-rebound event_class=event_class must be flagged unresolved, not silently accepted as the function's own parameter forward: {unresolved_with!r}"
    )

    # (iv) WP-B1 acceptance-audit round 2 (M8): `except ... as
    # event_class:` -- `ExceptHandler.name` is a plain STRING attribute,
    # not a `Name` node, so `ctx`-based `Name` matching alone cannot see
    # it; the prior enumeration never checked `ExceptHandler.name` either.
    # `k` likewise declares `event_class` as its own keyword-only
    # parameter, then an `except ... as event_class:` clause rebinds it
    # to the caught exception object -- the same "parameter exists, but
    # was locally rebound" shape as above, this time via a plain string
    # attribute (`ExceptHandler.name`) rather than a `Name` node.
    source_except_as = (
        "def k(sink, *, event_class):\n"
        "    try:\n"
        "        raise ValueError(\"__WPB1_SYNTHETIC_FIXTURE_EXCEPT__\")\n"
        "    except Exception as event_class:\n"
        "        sink.append(event_class=event_class)\n"
    )
    literals_except, unresolved_except = _scan_event_class_literals(source_except_as, "synthetic_except_as.py")
    assert not literals_except, f"an except-as-rebound event_class must never be collected as a literal: {literals_except!r}"
    assert unresolved_except == ["synthetic_except_as.py:5"], (
        f"an except-as-rebound event_class=event_class must be flagged unresolved, not silently accepted as the function's own parameter forward: {unresolved_except!r}"
    )


# P4-D16 v3(e)'s own N: the explicit, non-durable exclusion set. Each
# element is real (found by (b)'s own unfiltered walk) but reaches ONLY
# the legacy in-memory `AuditSink` (`DataService._audit`), never the
# durable `application_audit`/`control_audit` tables `audit_query` reads
# -- adding these to `DECLARED_AUDIT_EVENT_CLASSES` would make
# `audit_query`'s own declaration lie about a vocabulary it can never
# actually return (禁止事項 9b). `D ∩ N == ∅` is fixed by the test below,
# not merely asserted here.
_NON_DURABLE_EVENT_CLASSES: frozenset[str] = frozenset({
    # `_event` (service.py:819, `event_class="authentication"`) --
    # `authenticate()`'s own success event. `_event`'s own dispatch body
    # (service.py, the `if event_class != "data_operation": return` guard
    # right before the buffer-class enqueue) keeps this literal in the
    # legacy in-memory `self._audit` sink only; it never reaches the
    # buffer or the denial-coalescer. `audit_query.py`'s own
    # `DECLARED_AUDIT_EVENT_CLASSES` docstring documents this same
    # exclusion.
    "authentication",
    # `_control_event` (service.py:1356) writes ONLY to the legacy
    # in-memory `self._service._audit` sink -- never to the durable
    # `control_audit` table (that table is written exclusively by
    # `ops.py`'s own `_write_control_audit`, a structurally separate call
    # path). `control_failure` is one of `_control_event`'s two
    # non-durable-only literals (every `except FoundationError` deny
    # branch across register/enable/disable-application,
    # set_credential_state, issue_credential, delete_audit, and
    # set_authorization_state_available).
    "control_failure",
    # Same call path/rationale as `control_failure` above --
    # `_control_event`'s own `set_authorization_state_available` SUCCESS
    # literal (the one `_control_event` call site whose `outcome` is
    # `"allow"` rather than `"deny"`).
    "control_state",
})


@pytest.mark.parametrize("kind", BACKENDS)
def test_declared_event_classes_cover_every_emittable_class(kind, platform):
    """§9.2 property 5 / P4-D16 v3(e). With (b) closing the callee-name
    blind spot, (c) closing positional passing, and (d) closing dict
    smuggling, every real `event_class` literal anywhere under `src/
    r2db_api/` is reachable by (b)'s own unfiltered walk. This test
    computes that full literal union U and fixes `U == D | N` AND
    `D & N == set()`, where D is `DECLARED_AUDIT_EVENT_CLASSES`
    (unchanged by this WP) and N is the explicit non-durable exclusion
    set above. A future new literal now forces a choice: declare it, or
    name it in N with a reason -- there is no silent third path.
    """
    h = _build_harness(kind, platform)
    try:
        document = h.service.capabilities(h.control_credential_secret)
        declared = set(document["capabilities"]["audit_query"]["event_classes"])
        assert declared == DECLARED_AUDIT_EVENT_CLASSES

        paths = _iter_src_files()
        emitted: set[str] = set()
        for _filename, _lineno, value, _is_forward in _event_class_keyword_call_sites(paths):
            if isinstance(value, _ast.Constant) and isinstance(value.value, str):
                emitted.add(value.value)
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
