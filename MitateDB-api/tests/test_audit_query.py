"""Phase 4 WP-3(b): `audit_query` on the control HTTP host -- reader pair
(`audit_query.InMemoryAuditQueryStore`/`PostgresAuditQueryStore`), the
`ControlPlaneService.audit_query` service method, the `audit_requests_per_
minute` pre-auth window, `contract_version` 1.4.0, and the two HTTP paths
(`control_http.py`).

Mirrors r2db-api's own `test_audit_query.py` in STRENGTH (same completion
conditions: two-path response identity, application-credential FORBIDDEN,
audit-role allow/other-FORBIDDEN, unavailable x audit-role, cursor paging
under concurrent writes, load-bearing delayed-tx visibility, cross-table
same-event_id cursor boundary, plane ordering tiebreaker, control-window
non-consumption + pre-auth at the HTTP layer, reader-DSN INSERT refusal,
forbidden_fields absence, plane not client-settable, coalesced/alert rows
never carrying count 0/1, coalescing_window_ms derived from the real
constant) -- independently written against this peer's own credential_id+
secret model (never r2db's bare-secret model) and its own dual event-class
vocabulary (control-plane `_denial`/application-plane `_denied` spelling,
`audit_query.DECLARED_AUDIT_EVENT_CLASSES`'s own union).

Design: docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-5/D-6/D-7. Work
order: docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-3(b).
Known pitfalls this file deliberately avoids from the start (r2db-api's own
WP-2(b) review findings, scratchpad/audit-wp2b.md): a coalesced/alert row
ever carrying a literal `count=1`; `audit_events` reservation checked only
at creation; the declared-vocabulary AST scan missing positional/keyword/
`.append(event_class=...)` emit forms; control-window non-consumption and
pre-auth only fixed at the service layer, never the real HTTP layer; total
order missing `plane` as a real tiebreaker; a conformance adapter's writer
connection missing the two session timeouts; a "delayed tx" test whose
hold time is capped below the configured lag (never load-bearing); a
cross-table same-`event_id` x cursor-paging boundary never actually
exercised; the `unavailable` x `audit`-role combination never tested;
`coalescing_window_ms` declared as an uncoupled literal.
"""
from __future__ import annotations

import asyncio
import secrets
import threading
import time
import types
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator

import httpx
import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.application_audit import DEFAULT_DENIAL_COALESCE_WINDOW_S, ApplicationAuditSink
from mitatedb_api.audit_query import (DECLARED_AUDIT_EVENT_CLASSES,
                                      DECLARED_AUDIT_OPERATIONS,
                                      DECLARED_AUDIT_TARGET_KINDS,
                                      DEFAULT_COALESCING_WINDOW_MS,
                                      InMemoryAuditQueryStore,
                                      PostgresAuditQueryStore,
                                      decode_cursor)
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.control_http import _ROUTES, create_control_app
from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService,
                                        InMemoryControlBackend,
                                        PostgresApplicationRegistry,
                                        PostgresControlBackend,
                                        PostgresCredentialRegistry,
                                        _AUDIT_ROLE_ALLOWED_OPERATIONS,
                                        bootstrap_control_credential)
from mitatedb_api.errors import AuthorizationError, CapabilityError, ValidationError

_APP_PEPPER = "audit-query-app-pepper-x0000000"
_CONTROL_PEPPER = "audit-query-ctl-pepper-x0000000"
_GENEROUS_LIMITS = ControlPlaneLimits(
    applications=50, credentials_per_application=10, control_requests_per_minute=200,
    audit_requests_per_minute=200,
)

BASE_URL = "http://mitatedb-audit-query.example.invalid"


def _auth(credential_id: str, secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {credential_id}.{secret}"}


# ---------------------------------------------------------------------------
# in-memory harness
# ---------------------------------------------------------------------------


def _memory_harness(limits: ControlPlaneLimits | None = None) -> types.SimpleNamespace:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    application_audit = ApplicationAuditSink()
    audit_reader = InMemoryAuditQueryStore(backend.audit_sink, application_audit)
    service = ControlPlaneService(
        backend, limits=limits or _GENEROUS_LIMITS,
        audit_reader=audit_reader, audit_visibility_lag_ms=0,
        audit_coalescing_window_ms=DEFAULT_COALESCING_WINDOW_MS,
    )
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotated = service.rotate_credential(cid, secret, cid)
    return types.SimpleNamespace(
        service=service, backend=backend, control_audit=backend.audit_sink, application_audit=application_audit,
        control_credential_id=cid, control_credential_secret=rotated["secret"],
        seed_app_pepper=_APP_PEPPER, audit_reader=audit_reader,
    )


def _write_application_audit_row(h, *, event_class="data_operation", request_id=None, application_id="probeapp",
                                  event_id=None, recorded_at=None, count=None) -> None:
    h.application_audit._events.append(  # noqa: SLF001 -- direct fixture injection, test-only
        __import__("mitatedb_api.application_audit", fromlist=["ApplicationAuditEvent"]).ApplicationAuditEvent(
            event_id=event_id or uuid.uuid4().hex, event_class=event_class,
            occurred_at=(recorded_at or datetime.now(timezone.utc)).isoformat(),
            request_id=request_id, application_id=application_id, actor_type="application_credential",
            actor_id="crd_probe", role="runtime", operation="query", target_kind="collection",
            outcome="allow", reason_code=None, target_id=None, count=count,
        )
    )


# ---------------------------------------------------------------------------
# postgres harness
# ---------------------------------------------------------------------------


def _postgres_harness(control_platform, *, limits: ControlPlaneLimits | None = None,
                       audit_statement_timeout_ms: int | None = None,
                       audit_idle_timeout_ms: int | None = None) -> types.SimpleNamespace:
    applications = PostgresApplicationRegistry(control_platform.controlplane_dsn, schema=control_platform.registry_schema)
    credentials = PostgresCredentialRegistry(control_platform.controlplane_dsn, pepper=_APP_PEPPER, schema=control_platform.registry_schema)
    control_credentials = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER, schema=control_platform.registry_schema)
    backend = PostgresControlBackend(
        applications=applications, credentials=credentials, control_credentials=control_credentials,
        audit_schema=control_platform.registry_schema, dsn=control_platform.controlplane_dsn,
        audit_statement_timeout_ms=audit_statement_timeout_ms, audit_idle_in_transaction_session_timeout_ms=audit_idle_timeout_ms,
    )
    audit_reader = PostgresAuditQueryStore(control_platform.auditreader_dsn, schema=control_platform.registry_schema)
    statement_ms = audit_statement_timeout_ms if audit_statement_timeout_ms is not None else 5000
    idle_ms = audit_idle_timeout_ms if audit_idle_timeout_ms is not None else 5000
    visibility_lag_ms = statement_ms + idle_ms + 1000
    service = ControlPlaneService(
        backend, limits=limits or _GENEROUS_LIMITS,
        audit_reader=audit_reader, audit_visibility_lag_ms=visibility_lag_ms,
        audit_coalescing_window_ms=DEFAULT_COALESCING_WINDOW_MS,
    )
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotated = service.rotate_credential(cid, secret, cid)
    return types.SimpleNamespace(
        service=service, backend=backend, platform=control_platform,
        control_credential_id=cid, control_credential_secret=rotated["secret"],
        visibility_lag_ms=visibility_lag_ms, audit_reader=audit_reader,
    )


def _cleanup_postgres(control_platform) -> None:
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
            cur.execute(f"DELETE FROM {schema}.control_audit")
            cur.execute(f"DELETE FROM {schema}.application_audit")
    finally:
        conn.close()


@pytest.fixture
def pg(control_platform) -> Iterator[types.SimpleNamespace]:
    h = _postgres_harness(control_platform)
    try:
        yield h
    finally:
        _cleanup_postgres(control_platform)


def _write_application_audit_row_pg(control_platform, *, event_id, request_id, application_id, recorded_at,
                                    event_class="data_operation", operation="query", outcome="allow", count=None) -> None:
    conn = psycopg.connect(control_platform.api_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
                    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count, recorded_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ).format(table=sql.Identifier(control_platform.registry_schema, "application_audit")),
                [event_id, event_class, recorded_at, request_id, application_id, "application_credential", "crd_probe",
                 "runtime", operation, "collection", outcome, None, None, count, recorded_at],
            )
    finally:
        conn.close()


def _write_control_audit_row_pg(control_platform, *, event_id, request_id, recorded_at, operation="rotate_credential") -> None:
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
                    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, recorded_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ).format(table=sql.Identifier(control_platform.registry_schema, "control_audit")),
                [event_id, "control_credential_lifecycle", recorded_at, request_id, None, "control_credential",
                 "ctl_probe", "control", operation, "control_credential", "allow", None, None, recorded_at],
            )
    finally:
        conn.close()


BACKENDS = ["memory", "postgres"]


def _build_harness(kind: str, control_platform=None, **kwargs):
    if kind == "memory":
        return _memory_harness(**kwargs)
    return _postgres_harness(control_platform, **kwargs)


# ---------------------------------------------------------------------------
# D-6: order / cursor / filter / limit
# ---------------------------------------------------------------------------


def test_invalid_cursor_is_validation_failed() -> None:
    h = _memory_harness()
    with pytest.raises(ValidationError):
        h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"after": "not-a-real-cursor"})


def test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes() -> None:
    """D-6 completion condition (r2db pitfall avoided): a background writer
    thread keeps inserting rows WHILE a reader thread pages with cursor --
    never a single upfront write-then-page."""
    h = _memory_harness()
    total_rows = 40
    written_ids: set[str] = set()
    write_lock = threading.Lock()
    stop = threading.Event()

    def _writer() -> None:
        for i in range(total_rows):
            with write_lock:
                event_id = uuid.uuid4().hex
                _write_application_audit_row(h, request_id=f"pagewrite{i}", event_id=event_id)
                written_ids.add(event_id)
            time.sleep(0.002)
        stop.set()

    thread = threading.Thread(target=_writer)
    thread.start()

    seen: list[str] = []
    after = None
    # Poll with small pages WHILE the writer is still active -- exercising
    # genuinely concurrent cursor paging, not a static upfront snapshot.
    idle_polls = 0
    while not stop.is_set():
        result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 5, "after": after})
        events = result["events"]
        if not events:
            idle_polls += 1
            time.sleep(0.005)
            continue
        for event in events:
            seen.append(event["event_id"])
        after = events[-1]["cursor"]
    thread.join(timeout=5)
    assert not thread.is_alive()

    # Explicit, bounded catch-up pass once the writer has fully finished --
    # `visibility_lag_ms=0` still requires `recorded_at < now()` strictly,
    # so a brief settle is given room here rather than being folded into
    # the concurrent-polling loop's own exit condition above.
    for _ in range(50):
        if set(seen) >= written_ids:
            break
        result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 5, "after": after})
        events = result["events"]
        if not events:
            time.sleep(0.005)
            continue
        for event in events:
            seen.append(event["event_id"])
        after = events[-1]["cursor"]

    assert len(seen) == len(set(seen)), f"cursor paging produced duplicates: {seen!r}"
    assert set(seen) >= written_ids, f"cursor paging missed rows: {written_ids - set(seen)!r}"


def test_ordering_uses_plane_as_a_tiebreaker_not_event_id_alone() -> None:
    """WP-3(b) (mirrors r2db-api WP-2(b) review M-6, avoided from the
    start): the total order is `(recorded_at, plane, event_id)` -- `plane`
    must be a REAL tiebreaker at an identical `recorded_at`, not
    incidental. WP-3(b) review finding A (supervisor-forwarded fix): the
    `event_id` values must be chosen so an `event_id`-ONLY order would put
    `control` FIRST (control's event_id sorts LOWER) -- only then does
    requiring `application` first (via `(plane, event_id)`, since
    `'application' < 'control'` lexicographically) actually exercise
    `plane` as a real tiebreaker. The original values here had this
    backwards (application's event_id already sorted lower on its own),
    so removing `plane` from the sort key left the assertion passing by
    coincidence -- confirmed load-bearing now by mutation (dropping
    `plane` from `InMemoryAuditQueryStore.query`'s own sort key genuinely
    reverses the expected order below)."""
    h = _memory_harness()
    tied_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    marker = "planeorder" + secrets.token_hex(4)
    control_event = __import__("mitatedb_api.control_audit", fromlist=["ControlAuditEvent"]).ControlAuditEvent(
        event_id="00000000000000000000000000000000", event_class="control_credential_lifecycle",
        occurred_at=tied_at.isoformat(), request_id=f"{marker}-control", application_id=None,
        actor_type="control_credential", actor_id="ctl_x", role="control", operation="rotate_credential",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=None,
    )
    h.control_audit._events.append(control_event)  # noqa: SLF001 -- direct fixture injection
    _write_application_audit_row(h, request_id=f"{marker}-application", event_id="ffffffffffffffffffffffffffffffff", recorded_at=tied_at)

    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000})
    matched = [e for e in result["events"] if e.get("request_id", "").startswith(marker)]
    assert len(matched) == 2, f"expected exactly the 2 probe rows, got {matched!r}"
    assert [e["plane"] for e in matched] == ["application", "control"], (
        f"expected the application-plane row before the control-plane row DESPITE its event_id sorting "
        f"higher than control's own -- plane is not acting as the tiebreaker: {matched!r}"
    )


def test_cursor_boundary_on_identical_cross_table_event_id_has_no_loss_stall_or_duplicate() -> None:
    """WP-3(b) (r2db pitfall avoided from the start): a control_audit row
    and an application_audit row sharing the SAME `event_id` must not
    cause the cursor to stall, skip, or duplicate when paging with
    `limit=1` straight across that boundary."""
    h = _memory_harness()
    tied_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    shared_id = "shared" + secrets.token_hex(10)
    marker = "xboundary" + secrets.token_hex(4)
    control_event = __import__("mitatedb_api.control_audit", fromlist=["ControlAuditEvent"]).ControlAuditEvent(
        event_id=shared_id, event_class="control_credential_lifecycle", occurred_at=tied_at.isoformat(),
        request_id=f"{marker}-control", application_id=None, actor_type="control_credential", actor_id="ctl_x",
        role="control", operation="rotate_credential", target_kind="control_credential", outcome="allow",
        reason_code=None, target_id=None,
    )
    h.control_audit._events.append(control_event)  # noqa: SLF001
    _write_application_audit_row(h, request_id=f"{marker}-application", event_id=shared_id, recorded_at=tied_at)

    # WP-3(b) review finding B (supervisor-forwarded fix): `limit=1` is
    # LOAD-BEARING here -- a `limit` large enough for both probe rows to
    # land on the SAME page (the original bug: `limit=1000`) never crosses
    # a cursor boundary at all, so it cannot exercise the shared-event_id
    # ordering tie this test's own name promises. Every `request_id` seen
    # is appended UNCONDITIONALLY (no de-dup on the way in) so a genuine
    # duplicate delivery is caught by the final assertion, not silently
    # absorbed by an `if ... not in seen` guard.
    after = None
    seen_request_ids: list[str] = []
    for _ in range(6):
        result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1, "after": after})
        events = result["events"]
        if not events:
            break
        matched = [e for e in events if e.get("request_id", "").startswith(marker)]
        seen_request_ids.extend(e["request_id"] for e in matched)
        after = events[-1]["cursor"]
    assert sorted(seen_request_ids) == sorted([f"{marker}-control", f"{marker}-application"]), (
        f"the shared event_id boundary lost or duplicated a row (limit=1 paging straight across "
        f"the boundary): {seen_request_ids!r}"
    )


def test_application_audit_rows_always_read_back_as_plane_application() -> None:
    """D-6/property 11: `plane` is a DERIVED value -- a durable row cannot
    be made to read back as `plane="control"` no matter what a writer
    stores (there is no `plane` column at all, migration 0005's own DDL)."""
    h = _memory_harness()
    marker = "planederived" + secrets.token_hex(4)
    _write_application_audit_row(h, request_id=marker)
    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000})
    matched = [e for e in result["events"] if e.get("request_id") == marker]
    assert len(matched) == 1
    assert matched[0]["plane"] == "application"
    # Never a real, client-settable column: a request naming an unknown
    # "plane" field is silently ignored (there is no writable `plane`
    # parameter to accept in the first place) -- the row above still reads
    # back as "application" regardless.
    still = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"plane": "control", "limit": 1000})
    still_matched = [e for e in still["events"] if e.get("request_id") == marker]
    assert still_matched and still_matched[0]["plane"] == "application"


def test_in_memory_and_postgres_audit_query_semantics_have_parity(pg) -> None:
    """D-10 parity: order, filter, limit, and cursor round-tripping behave
    identically on both readers."""
    hm = _memory_harness()
    for i in range(3):
        _write_application_audit_row(hm, request_id=f"paritym{i}", application_id="parityapp")
    for i in range(3):
        _write_application_audit_row_pg(
            pg.platform, event_id=uuid.uuid4().hex, request_id=f"parityp{i}", application_id="parityapp",
            recorded_at=datetime.now(timezone.utc) - timedelta(seconds=3),
        )
    time.sleep(pg.visibility_lag_ms / 1000 + 0.3)

    for h in (hm, pg):
        result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1, "event_classes": ["data_operation"]})
        assert len(result["events"]) == 1
        first_cursor = result["events"][0]["cursor"]
        second = h.service.audit_query(h.control_credential_id, h.control_credential_secret,
                                       {"limit": 1, "event_classes": ["data_operation"], "after": first_cursor})
        assert len(second["events"]) == 1
        assert second["events"][0]["cursor"] != first_cursor
        # after decodes to a real (recorded_at, plane, event_id) triple.
        decode_cursor(first_cursor)
        empty = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"event_classes": ["no_such_class_at_all"]})
        assert empty["events"] == []


def test_writer_tx_held_near_the_lag_still_returns_on_the_next_page(control_platform) -> None:
    """D-6 (r2db pitfall avoided from the start: the hold time is NEVER
    capped below the configured lag -- `hold_s = lag_s + 0.5`,
    unconditionally, so this assertion is genuinely load-bearing, not
    merely restating the visibility-lag threshold)."""
    _run_delayed_tx_vector(control_platform, dsn=control_platform.api_dsn, table="application_audit",
                           insert_sql=(
                               "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
                               "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) "
                               "VALUES (gen_random_uuid()::text, 'data_operation', now(), %s, 'delaytxapp', "
                               "'application_credential', 'crd_x', 'runtime', 'query', 'collection', 'allow', NULL, NULL, NULL)"
                           ))


def test_control_audit_row_from_a_delayed_control_tx_returns_on_the_next_page(control_platform) -> None:
    _run_delayed_tx_vector(control_platform, dsn=control_platform.provision_dsn, table="control_audit",
                           insert_sql=(
                               "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, "
                               "actor_type, actor_id, role, operation, target_kind, outcome) "
                               "VALUES (gen_random_uuid()::text, 'credential_lifecycle', now(), %s, "
                               "'control_credential', 'ctl_x', 'control', 'rotate_credential', 'control_credential', 'allow')"
                           ))


def _run_delayed_tx_vector(control_platform, *, dsn: str, table: str, insert_sql: str) -> None:
    h = _postgres_harness(control_platform, audit_statement_timeout_ms=1_000, audit_idle_timeout_ms=1_000)
    try:
        lag_s = h.visibility_lag_ms / 1000  # ~3s at these timeouts
        hold_s = lag_s + 0.5
        probe_at_s = lag_s + 0.2
        assert probe_at_s < hold_s, "test's own timing assumption does not hold"
        marker = "delaytx" + secrets.token_hex(6)

        # WP-3(b) review finding C (supervisor-forwarded fix): a BASELINE
        # cursor captured BEFORE the delayed writer even starts -- the
        # "next page" assertion below pages FORWARD from this cursor
        # (never a fresh limit=1000 re-read of everything), so it
        # genuinely exercises D-6's own cursor-based visibility semantics
        # ("a delayed commit's own row returns on the NEXT PAGE"), not
        # merely PostgreSQL's MVCC (which a blanket re-read conflates
        # with lag-based visibility -- the original form of this test).
        baseline = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000})
        baseline_events = baseline["events"]
        baseline_cursor = baseline_events[-1]["cursor"] if baseline_events else None

        result_holder: dict = {}
        start = time.monotonic()

        def _hold_and_write() -> None:
            conn = psycopg.connect(dsn, autocommit=False)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL(insert_sql).format(table=sql.Identifier(control_platform.registry_schema, table)), [marker])
                time.sleep(hold_s)
                conn.commit()
            finally:
                conn.close()
            result_holder["done"] = True

        writer = threading.Thread(target=_hold_and_write)
        writer.start()
        time.sleep(max(0.0, probe_at_s - (time.monotonic() - start)))
        assert writer.is_alive(), "writer already finished before the load-bearing probe point"
        probe = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000, "after": baseline_cursor})
        assert not any(e.get("request_id") == marker for e in probe["events"]), (
            "the row became visible before its writer transaction committed -- load-bearing assertion"
        )
        writer.join(timeout=15)
        assert result_holder.get("done"), "writer thread did not finish in time"
        time.sleep(0.5)

        # Page FORWARD from the SAME baseline cursor, one row at a time,
        # until the delayed row is found or a page comes back empty -- the
        # genuine "next page" retrieval D-6 requires, never a blanket
        # limit=1000 re-read from `after=None`.
        after = baseline_cursor
        found = False
        for _ in range(20):
            page = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1, "after": after})
            events = page["events"]
            if not events:
                break
            if any(e.get("request_id") == marker for e in events):
                found = True
                break
            after = events[-1]["cursor"]
        assert found, (
            "the delayed row never appeared while paging FORWARD from the pre-write baseline cursor -- "
            "D-6's own 'a delayed commit returns on the next page' property is not holding"
        )
    finally:
        _cleanup_postgres(control_platform)


def test_visibility_lag_ms_actually_filters_rows_inside_the_window() -> None:
    """WP-3(b) review finding C (supervisor-forwarded fix): none of this
    file's other tests directly exercise `threshold = now() -
    visibility_lag_ms` (as opposed to a bare `now()`) -- mutating BOTH
    `InMemoryAuditQueryStore.query` and `PostgresAuditQueryStore.query` to
    drop the `visibility_lag_ms` term entirely passed all 27 pre-fix
    tests. Directly injects one row recorded WELL inside a large
    `visibility_lag_ms` window (must be EXCLUDED) and one row recorded
    WELL outside it (must be INCLUDED), calling the reader with an
    explicit `visibility_lag_ms` so this needs no real wall-clock wait."""
    h = _memory_harness()
    now = datetime.now(timezone.utc)
    marker_fresh = "lagfresh" + secrets.token_hex(4)
    marker_old = "lagold" + secrets.token_hex(4)
    _write_application_audit_row(h, request_id=marker_fresh, event_id=uuid.uuid4().hex, recorded_at=now)
    _write_application_audit_row(h, request_id=marker_old, event_id=uuid.uuid4().hex, recorded_at=now - timedelta(seconds=100))

    rows = h.audit_reader.query(event_classes=None, after=None, limit=1000, visibility_lag_ms=50_000)
    ids = {r["request_id"] for r in rows}
    assert marker_old in ids, "a row recorded well before the threshold must be visible"
    assert marker_fresh not in ids, (
        "a row recorded INSIDE visibility_lag_ms must NOT be visible yet -- threshold is not being applied"
    )

    # `visibility_lag_ms=0` (this harness's own default) makes both rows
    # visible immediately -- confirms the exclusion above is genuinely
    # about the lag window, not some unrelated filter.
    rows_no_lag = h.audit_reader.query(event_classes=None, after=None, limit=1000, visibility_lag_ms=0)
    ids_no_lag = {r["request_id"] for r in rows_no_lag}
    assert marker_fresh in ids_no_lag and marker_old in ids_no_lag


def test_postgres_visibility_lag_ms_actually_filters_rows_inside_the_window(control_platform) -> None:
    """Postgres twin of the in-memory test immediately above -- same
    property, against `PostgresAuditQueryStore.query`'s own `threshold`
    computation and real `application_audit`/`control_audit` rows with
    explicit `recorded_at` values (never relying on `clock_timestamp()`
    timing)."""
    h = _postgres_harness(control_platform)
    try:
        now = datetime.now(timezone.utc)
        marker_fresh = "pglagfresh" + secrets.token_hex(4)
        marker_old = "pglagold" + secrets.token_hex(4)
        _write_application_audit_row_pg(control_platform, event_id=uuid.uuid4().hex, request_id=marker_fresh,
                                        application_id="lagapp", recorded_at=now)
        _write_application_audit_row_pg(control_platform, event_id=uuid.uuid4().hex, request_id=marker_old,
                                        application_id="lagapp", recorded_at=now - timedelta(seconds=100))

        rows = h.audit_reader.query(event_classes=None, after=None, limit=1000, visibility_lag_ms=50_000)
        ids = {r["request_id"] for r in rows}
        assert marker_old in ids, "a row recorded well before the threshold must be visible"
        assert marker_fresh not in ids, (
            "a row recorded INSIDE visibility_lag_ms must NOT be visible yet -- threshold is not being applied"
        )

        rows_no_lag = h.audit_reader.query(event_classes=None, after=None, limit=1000, visibility_lag_ms=0)
        ids_no_lag = {r["request_id"] for r in rows_no_lag}
        assert marker_fresh in ids_no_lag and marker_old in ids_no_lag
    finally:
        _cleanup_postgres(control_platform)


# ---------------------------------------------------------------------------
# D-5: authority / capability-unsupported / declared event_classes
# ---------------------------------------------------------------------------


def test_control_and_audit_credentials_are_accepted_on_audit_query() -> None:
    h = _memory_harness()
    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1})
    assert "events" in result

    audit_id, audit_secret = h.backend._control_credentials.issue(role="audit")  # noqa: SLF001
    audit_secret = h.backend._control_credentials.rotate(audit_id, secret=audit_secret)  # noqa: SLF001
    audit_result = h.service.audit_query(audit_id, audit_secret, {"limit": 1})
    assert "events" in audit_result


def test_application_credential_is_forbidden_on_the_control_host_audit_query() -> None:
    h = _memory_harness()
    h.backend.register_application("fbdapp", work=None) if False else None
    with h.backend.unit_of_work() as work:
        h.backend.register_application("fbdapp", work=work)
    with h.backend.unit_of_work() as work:
        h.backend.issue_credential("fbdapp", "runtime", credential_id="crd_fbd1", secret="app-secret-1234567890", work=work)
    with pytest.raises(AuthorizationError):
        h.service.audit_query("crd_fbd1", "app-secret-1234567890", {"limit": 1})


def test_audit_query_without_audit_dsn_refuses_with_capability_unsupported_not_404() -> None:
    """D-5 M-4: no reader configured -- the SERVICE method answers
    `CAPABILITY_UNSUPPORTED` for a genuinely authenticated caller, both for
    a control credential AND an audit credential (contract 1.4.0
    unconditional obligation (b)'s own explicit combination)."""
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend, limits=_GENEROUS_LIMITS)  # no audit_reader
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotated = service.rotate_credential(cid, secret, cid)
    secret = rotated["secret"]

    with pytest.raises(CapabilityError):
        service.audit_query(cid, secret, {"limit": 1})

    document = service.control_capabilities(cid, secret)
    assert document["capabilities"]["audit_query"] == {"status": "unavailable"}

    audit_id, audit_secret = backend._control_credentials.issue(role="audit")  # noqa: SLF001
    audit_secret = backend._control_credentials.rotate(audit_id, secret=audit_secret)  # noqa: SLF001
    with pytest.raises(CapabilityError) as excinfo:
        service.audit_query(audit_id, audit_secret, {"limit": 1})
    assert not isinstance(excinfo.value, AuthorizationError)


# WP-B1 (P4-D16 v3, docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md
# §1/§4): this whole block replaces the earlier package-wide scan (which
# lived only in THIS function) with the SAME four independent,
# callee-name-FILTER-FREE checks r2db-api's own `test_audit_query.py`
# uses (same helper names, same shapes -- "両 peer の走査ヘルパは同型に
# する"):
#
#   (a) `_iter_src_files()` -- every `*.py` under `src/mitatedb_api/`,
#       found by a RECURSIVE `rglob`.
#   (b) literal discipline -- every `Call` anywhere in the package that
#       carries a `<field>=` keyword must pass a string `Constant`, or be
#       the recognized parameter-forward shape.
#   (c) definition-side keyword-only guarantee -- every `def`/`async def`
#       anywhere under `src/mitatedb_api/` that takes `<field>` as a
#       formal parameter must declare it keyword-only.
#   (d) dict-smuggling ban -- no `{"<field>": "<literal>"}` dict literal
#       or `x["<field>"] = "<literal>"` subscript assignment anywhere in
#       the package.
#   (e) exact vocabulary-relation match -- the full literal union U found
#       by (b)'s own walk must equal `D | N` with `D & N == set()`.
#
# Phase 5 WP-3 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
# D-1, work order docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md
# WP-3 変更対象 D): generalizes this SAME "global invariant" method (never
# the withdrawn "resolve every call site's value" method -- design §3 D-1
# explicitly rejects that alternative) by PARAMETERIZING every rule over a
# field name, and adds exactly three new rules the generalization itself
# makes necessary (design's own accounting -- `event_class`'s emit surface
# is uniformly keyword-only in this package, so these gaps never showed up
# for it). Independent implementation of r2db-api's own WP-2 generalization
# (R-2's closing paragraph: no code sharing between peers) -- same helper
# names/shapes, ported by copying text and substituting peer names (常設
# 規律 6):
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
#        named `"operation"` (this peer's own `http.py`, `SchemaOperation
#        Request.operation`), so an unrestricted `foo(operation=
#        body["operation"])` would let client-supplied text reach a durable
#        audit column unlit by (b)'s own literal-discipline scan or by U.
#        Verified (design N-6): every real read-path site in THIS peer
#        already uses the dict-literal form, so (b''') requires zero
#        product-code changes here.
#
# `_FIELDS` below is the pinned set this whole block is parameterized over
# -- `test_scanner_is_parameterized_over_exactly_these_three_fields` fixes
# its CONTENT directly (a scanner silently narrowed back down to `event_
# class` alone would go undetected by every other test in this block, since
# every rule's own violation collectors would simply never be called for
# the missing field(s)).
import ast as _ast  # noqa: E402 -- kept local to this test-support block, mirrors r2db-api's own test_audit_query.py
from pathlib import Path  # noqa: E402

_FIELDS: tuple[str, ...] = ("event_class", "operation", "target_kind")

_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"


def test_scanner_is_parameterized_over_exactly_these_three_fields() -> None:
    """Pins `_FIELDS` directly (WP-3 変更対象 D, 監督裁定 2026-09-04 --
    an explicit發注項目, not implementer discretion). Mutation 10: drop
    `target_kind` from this tuple and every rule test below silently stops
    exercising it -- this test is the only thing that turns that into a
    failure."""
    assert _FIELDS == ("event_class", "operation", "target_kind")


def _iter_src_files() -> list[Path]:
    """Every `*.py` file anywhere under `src/mitatedb_api/`, found by a
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


# WP-3 変更対象 C: rule (c) is name-BASED, not callee-name-based, so it
# reacts to every definition anywhere under `src/mitatedb_api/` whose
# formal parameters include `operation` -- and `operation` is not an
# audit-only word (280 identifier occurrences in this package, design §3
# D-1). `cell.ApplicationCell._plan_operation` is the ONLY definition this
# package has whose `operation` parameter is a CLIENT-SUPPLIED mutation
# dict, never an audit field -- keyword-only-ifying it would change
# `transact()`'s own pass-1 planning loop's established positional-call
# convention (`self._plan_operation(operation)`, `cell.py`) for no
# audit-safety benefit. This entry names its qualified definition and its
# rationale; the two validation tests immediately below hold this list
# itself accountable: (i) the entry must still resolve to a real
# `operation`-parameter definition (a renamed/removed function goes red
# here, not silently), and (ii') the excluded definition's own body may
# not forward ITS OWN `operation` parameter into an audit emit call
# (design N-1 -- NOT "carries no operation= Constant at all").
_NON_AUDIT_OPERATION_PARAMETERS: frozenset[str] = frozenset(
    {
        # Client-supplied mutation-item dict (`transact()`'s pass-1
        # planning loop) -- `operation` here is never an audit field.
        "cell.ApplicationCell._plan_operation",
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
    """(b)/(b'). Every `Call` anywhere under `src/mitatedb_api/` carrying a
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
    """(c). Every function/method anywhere under `src/mitatedb_api/` that
    takes `field` as a formal parameter must declare it keyword-only,
    UNLESS it is named on that field's own exclusion list
    (`_NON_AUDIT_FIELD_PARAMETERS` -- empty for `event_class`/`target_kind`,
    proven by this same assertion going green for them with nothing
    excluded)."""
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
    """Completion condition 5 (WP-2 fix-round M-4 の対称): "除外リストが
    event_class/target_kind には不要であることも確認すること" は、この
    テストが無ければ `test_every_definition_taking_the_field_declares_it_
    keyword_only[event_class]`/`[target_kind]` が空の除外集合で緑になる
    ことだけが証拠になり、`_NON_AUDIT_FIELD_PARAMETERS` への将来の1行追加
    がどちらのフィールドにも気付かれず (c) の抜け道を再び開けてしまう。
    両 frozenset の空であることを直接 pin する。"""
    assert _NON_AUDIT_FIELD_PARAMETERS["event_class"] == frozenset()
    assert _NON_AUDIT_FIELD_PARAMETERS["target_kind"] == frozenset()


def test_non_audit_operation_parameters_never_forward_their_own_parameter_into_an_emit_call():
    """(ii'). No excluded definition's own body forwards its OWN
    client-supplied `operation` parameter into an audit emit call --
    (ii), the withdrawn predecessor rule ("no Constant operation= at all
    in the body"), is deliberately NOT implemented (design N-1)."""
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
    anywhere under `src/mitatedb_api/` sets `field` to anything other than
    a genuine forward or read-path passthrough (b''')."""
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
    literals, unresolved = _scan_field_literals(source_local_var, "synthetic_local_var.py", "event_class")
    assert not literals, "a keyword-site forward of a (b'')-qualifying local must contribute nothing directly to U at THIS site"
    assert not unresolved, "a (b'')-qualifying local-variable forward must resolve, not be flagged unresolved"

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
    """(b'') boundary case: a qualifying single-`Assign`-of-`Constant`
    local, ALSO reassigned by a non-qualifying second binding (a `for`
    target reusing the same name) in the SAME scope, must forfeit the
    (b'') exemption entirely -- design's own "同スコープに他の束縛形が1つ
    でもあれば違反のまま" requirement. Mirrors mutation 4 (同名変数へ Call
    束縛) but with a `for`-target rebind instead, proving the "any other
    form" wording, not merely "any other Call", is enforced."""
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
    """(b'''): `.field`/`["field"]` read-path passthrough is legal at a
    dict-literal/subscript-assignment/attribute-assignment value position
    but NEVER at a `field=` keyword-argument-value position -- the hole the
    generalization itself opens (a request body key literally named
    `"operation"`, closed structurally rather than by convention)."""
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

    source_dict_ok = (
        "def h(sink, event, row):\n"
        "    return {\"operation\": event.operation, \"other\": row[\"operation\"]}\n"
    )
    _kw, dict_sites, _assign = _scan_source_field_sites(source_dict_ok, "synthetic_dict_ok.py", "operation")
    assert dict_sites, "the dict-literal site itself must be observed by the scanner for this contrast to mean anything"
    assert all(ok for _lineno, _kind, _value, ok in dict_sites), (
        f"Attribute/Subscript read-path passthrough must remain legal at a dict-literal value position: {dict_sites!r}"
    )


# P4-D16 v3(e)'s own N for MitateDB: EMPTY, unchanged by this WP -- the
# diagnostic behind WP-3(a) confirmed every real MitateDB `event_class`
# literal reaches a durable table (`application_audit` via `AuditRouter`,
# or `control_audit` via `_deny_audit`/`append_audit`).
_NON_DURABLE_EVENT_CLASSES: frozenset[str] = frozenset()

# Phase 5 WP-3 (design D-1, work order WP-3 変更対象 E): the `operation`
# vocabulary's non-durable exclusion set. MitateDB's design-time hypothesis
# was N = ∅ (design §3 D-1's own "N の初期仮説は「該当なし」" -- this
# peer's control plane has no legacy in-memory-only sink the way r2db-api's
# `ControlAuthority` does: `ControlPlaneService._deny_audit`/`append_audit`
# ALWAYS durably write to `control_audit`). Runtime measurement (this WP)
# confirmed the hypothesis for `auth.CredentialStore`/`credential_store_
# postgres.PostgresCredentialStore`'s own `authenticate`/`assert_active`
# denial paths (`test_authenticate_and_assert_active_denials_are_durable_
# not_excluded` below) -- both route through the SAME shared `AuditRouter.
# route_denial` machinery with `reason_code="AUTH_INVALID"` (a member of
# `DURABLE_DENIAL_CODES`), and are durably observable. It did NOT hold for
# `control_capabilities` -- a DIFFERENT shape of non-durability (the same
# one r2db-api's own WP-2 fix-round M-1 found for the identical literal):
# `ControlPlaneService.control_capabilities`'s own 2 emit sites
# (`_authorize_role(principal, operation="control_capabilities", ...)` /
# `_gate_must_rotate(principal, operation="control_capabilities", ...)`)
# can NEVER reach a `_deny_audit` call for this operation AT ALL, on any
# role or must_rotate state -- `_AUDIT_ROLE_ALLOWED_OPERATIONS` permanently
# includes it (closing `_authorize_role`'s own deny condition), and
# `_gate_must_rotate` opens with an unconditional `if operation ==
# "control_capabilities": return`. Structural, not exercised for
# observed-absence purposes by the runtime test above (there is nothing to
# durably fail INTO) -- fixed instead by `test_control_capabilities_
# operation_has_no_reachable_deny_branch` below, which pins both structural
# facts directly and behaviorally proves the must_rotate early return (a
# must_rotate=True credential can still call `control_capabilities()`
# successfully).
_NON_DURABLE_OPERATIONS: frozenset[str] = frozenset(
    {
        "control_capabilities",
    }
)

# `target_kind`'s non-durable exclusion set: EMPTY. No candidate site for
# this field has the `control_capabilities`-shaped structural unreachability
# (every `target_kind` literal this peer emits accompanies an `operation`
# that DOES reach a `_deny_audit`/`route_denial`/`append_audit` call for at
# least one caller).
_NON_DURABLE_TARGET_KINDS: frozenset[str] = frozenset()


def test_control_capabilities_operation_has_no_reachable_deny_branch() -> None:
    """WP-3 対称 (r2db-api WP-2 fix-round M-1): `operation=
    "control_capabilities"` is in `_NON_DURABLE_OPERATIONS` for a
    DIFFERENT reason than a legacy-sink-only word -- it reaches no
    `_deny_audit` call at all. Pins BOTH structural facts directly, plus a
    behavioral proof:

    (a) `_authorize_role`'s own deny condition (`control_plane.py`) is
    `principal.role == "audit" and operation not in _AUDIT_ROLE_ALLOWED_
    OPERATIONS` -- `"control_capabilities"` is a PERMANENT member of that
    allow-list, so the condition can never be true for it, regardless of
    role.
    (b) `_gate_must_rotate`'s own body (`control_plane.py`) opens with `if
    operation == "control_capabilities": return` -- an unconditional early
    return before its own `_deny_audit` call is ever reached. Proven both
    structurally (the source literally starts this way, verified by (a)'s
    sibling fact holding) and BEHAVIORALLY here: a credential with `must_
    rotate=True` (freshly `issue()`-ed via `bootstrap_control_credential`,
    never `rotate_credential()`-d) must still be able to call `control_
    capabilities()` successfully -- if `_gate_must_rotate` ever reached its
    own `_deny_audit` for this operation, this call would raise
    `AuthorizationError` instead.

    Known limitation (WP-3 fix-round L-5, Opus review; same shape as
    r2db-api's own identical proof): the exercise below drives only the
    `role="control"` principal `_gate_must_rotate` produces. It does NOT
    separately drive a `role="audit"` principal through `_authorize_role`'s
    own `role == "audit"` branch -- fact (a) above is pinned structurally
    (the allow-list membership assert), not behaviorally, for that role.
    This does not weaken the proof (the allow-list membership is what
    makes the condition false for EVERY role, `"audit"` included), but it
    is disclosed here as an unexercised path, not silently assumed.
    """
    assert "control_capabilities" in _AUDIT_ROLE_ALLOWED_OPERATIONS

    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend, limits=_GENEROUS_LIMITS)
    with backend.unit_of_work() as work:
        # `bootstrap_control_credential` always issues a fresh must_rotate=
        # True credential (`control_auth.ControlCredentialStore.issue`'s own
        # default) -- deliberately never rotated here.
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    document = service.control_capabilities(cid, secret)  # must NOT raise -- the observable half of _gate_must_rotate's early return
    assert document["contract_version"] == "1.5.0"
    assert document["capabilities"]["audit_query"]["status"] == "unavailable"


def test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables() -> None:
    """N の実行時実測 (design §3 D-1). Same name as r2db-api's own
    identically-shaped test (`r2db-api/tests/test_audit_query.py`) --
    WP-3 fix-round M-3 (Opus review) corrects `audit_query.py`'s own
    `_CONTROL_PLANE_TARGET_KINDS` comment, which cited THIS test's name
    before it existed on this peer. `_NON_DURABLE_OPERATIONS`'s only
    member, `"control_capabilities"`, is exercised through TWO real
    principal states -- an ORDINARY, rotated control credential (`h.
    service`, this peer's own general harness), and a FRESH, never-rotated
    (`must_rotate=True`) one (mirroring `test_control_capabilities_
    operation_has_no_reachable_deny_branch`'s own construction) -- and the
    resulting `control_audit` rows are read back DIRECTLY (never through
    `audit_query`, which this WP's own `control_capabilities()` calls do
    not even reach `_gate_must_rotate`'s sibling deny for), confirming
    neither exercise ever durably records `operation="control_
    capabilities"`.

    Known limitation (WP-3 fix-round L-5, same shape as r2db-api's own
    equivalent): neither exercise below drives `_authorize_role`'s own
    `role == "audit"` branch (see `test_control_capabilities_operation_
    has_no_reachable_deny_branch`'s own docstring for the same disclosed
    limitation) -- `"control_capabilities"` is a PERMANENT `_AUDIT_ROLE_
    ALLOWED_OPERATIONS` member, so that branch's own condition is false
    regardless of role, and this omission does not weaken the proof."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["contract_version"] == "1.5.0"

    fresh_backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with fresh_backend.unit_of_work() as work:
        # `bootstrap_control_credential` always issues a fresh must_rotate=
        # True credential -- deliberately never rotated here (same
        # construction as `test_control_capabilities_operation_has_no_
        # reachable_deny_branch` above).
        fresh_cid, fresh_secret = bootstrap_control_credential(fresh_backend.control_credential_store, fresh_backend.append_audit, work=work)
    fresh_service = ControlPlaneService(fresh_backend, limits=_GENEROUS_LIMITS)
    fresh_document = fresh_service.control_capabilities(fresh_cid, fresh_secret)  # must_rotate=True path
    assert fresh_document["contract_version"] == "1.5.0"

    durable_operations = {event.operation for event in h.control_audit.snapshot()}
    durable_operations |= {event.operation for event in fresh_backend.audit_sink.snapshot()}
    assert durable_operations, "the harnesses above must have produced at least one durable control_audit row (常設規律1)"
    leaked = durable_operations & _NON_DURABLE_OPERATIONS
    assert not leaked, (
        f"MUTATION SHOULD HAVE BEEN CAUGHT (or N is wrong): non-durable-exclusion operation word(s) actually "
        f"reached the durable control_audit surface: {leaked!r}"
    )


def test_authenticate_and_assert_active_denials_are_durable_not_excluded() -> None:
    """N の実行時実測 (design §3 D-1, WP-3 変更対象 E). Exercises the REAL,
    application-plane denial path for BOTH `auth.CredentialStore` (the
    in-memory implementation) and `credential_store_postgres.
    PostgresCredentialStore` (the Postgres-backed one) directly -- never
    mocked -- then reads back through a real `audit_query` and confirms
    `operation="authenticate"`/`"assert_active"` and `target_kind=
    "credential"` are all actually observable. This is the runtime
    confirmation design's own worry (a possible non-durable path the same
    shape as r2db-api's `ControlAuthority`) does NOT hold for this peer."""
    from mitatedb_api.audit_dispatch import AuditRouter
    from mitatedb_api.application_audit import ApplicationAuditSink
    from mitatedb_api.audit_query import InMemoryAuditQueryStore
    from mitatedb_api.auth import CredentialStore, Principal
    from mitatedb_api.control_audit import ControlAuditSink

    # ---- in-memory `auth.CredentialStore` ----
    application_audit = ApplicationAuditSink()
    router = AuditRouter(application_audit)
    store = CredentialStore(_APP_PEPPER, audit_router=router)
    store.provision_application("n_word_probe_app")

    with pytest.raises(Exception):
        store.authenticate("no-such-credential-" + secrets.token_hex(4), "wrong-secret")
    bogus_principal = Principal("n_word_probe_app", "no-such-credential-" + secrets.token_hex(4), None)
    with pytest.raises(Exception):
        store.assert_active(bogus_principal)

    # WP-3 fix-round M-1 (Opus review): the exercise above only ever
    # reaches `auth.py`'s PRE-AUTH branch (`authenticated=False` -- an
    # unknown `credential_id`, `auth.py`'s own `else:` route_denial). It
    # never reaches the SIBLING branch immediately above it (`if
    # authenticated:` -- a REAL, known credential whose secret matched,
    # refused only by its own state: disabled/revoked/its application
    # disabled/expired). Both branches durably route through the SAME
    # `AuditRouter.route_denial`/`AUTH_INVALID` machinery, but they are
    # DIFFERENT lines of product code -- a regression that removes only
    # the `authenticated=True` branch's durable write left both `Mitate
    # DB-api/tests` (488) and `conformance-tests` (422) fully green before
    # this fix (the review's own reproduction). Exercised here directly: a
    # REAL credential, issued then DISABLED, authenticated with its own
    # (still-correct) secret.
    real_app = "n_word_real_app_" + secrets.token_hex(4)
    store.provision_application(real_app)
    real_credential_id, real_secret = store.issue(real_app, "runtime")
    store.disable(real_credential_id)
    with pytest.raises(Exception):
        store.authenticate(real_credential_id, real_secret)  # -> auth.py's `if authenticated:` branch (a real, known, but disabled credential)
    real_principal = Principal(real_app, real_credential_id, None)
    with pytest.raises(Exception):
        store.assert_active(real_principal)

    reader = InMemoryAuditQueryStore(ControlAuditSink(), application_audit)
    memory_events = reader.query(event_classes=None, after=None, limit=200, visibility_lag_ms=0)
    assert memory_events, "the in-memory exercise above must have produced at least one durable row (常設規律1)"
    memory_operations = {row["operation"] for row in memory_events}
    memory_target_kinds = {row["target_kind"] for row in memory_events}
    assert "authenticate" in memory_operations, (
        f"a failed auth.CredentialStore.authenticate() must durably record operation='authenticate': {memory_operations!r}"
    )
    assert "assert_active" in memory_operations, (
        f"a failed auth.CredentialStore.assert_active() must durably record operation='assert_active': {memory_operations!r}"
    )
    assert "credential" in memory_target_kinds, f"both denials must durably record target_kind='credential': {memory_target_kinds!r}"

    # WP-3 fix-round M-1: site-level proof -- a durable row carrying the
    # REAL, resolved credential/application identity (`auth.py:424-429`'s
    # own `if authenticated:` branch specifically; the PRE-AUTH branch
    # above NEVER records a real `actor_id`, by design, B-1) must exist.
    assert any(
        row.get("actor_id") == real_credential_id and row.get("application_id") == real_app and row["operation"] == "authenticate"
        for row in memory_events
    ), (
        f"a disabled-but-real credential's failed authenticate() must durably record the REAL credential_id/"
        f"application_id (auth.py's `if authenticated:` branch), not only the pre-auth branch's attributionless "
        f"row: {memory_events!r}"
    )


def test_postgres_authenticate_and_assert_active_denials_are_durable_not_excluded(control_platform) -> None:
    """Postgres-backed sibling of `test_authenticate_and_assert_active_
    denials_are_durable_not_excluded` above -- `credential_store_postgres.
    PostgresCredentialStore.authenticate`/`.assert_active` route through the
    SAME shared `AuditRouter.route_denial` machinery (`credential_store_
    postgres.py`'s own `_route_denial` helper -- identical `reason_code=
    "AUTH_INVALID"`), so this confirms the mechanism the in-memory test
    proves is durable is genuinely reached by the Postgres-backed class
    too, not merely by the in-memory one."""
    from mitatedb_api.audit_dispatch import AuditRouter
    from mitatedb_api.application_audit import PostgresApplicationAuditSink
    from mitatedb_api.credential_store_postgres import PostgresCredentialStore

    h = _postgres_harness(control_platform, audit_statement_timeout_ms=200, audit_idle_timeout_ms=200)
    try:
        pg_sink = PostgresApplicationAuditSink(control_platform.api_dsn, schema=control_platform.registry_schema)
        pg_router = AuditRouter(pg_sink)
        pg_store = PostgresCredentialStore(control_platform.api_dsn, pepper=_APP_PEPPER, schema=control_platform.registry_schema, audit_router=pg_router)

        with pytest.raises(Exception):
            pg_store.authenticate("no-such-credential-pg-" + secrets.token_hex(4), "wrong-secret")
        with pytest.raises(Exception):
            pg_store.assert_active(types.SimpleNamespace(application_id=None, credential_id="no-such-credential-pg-" + secrets.token_hex(4), role=None))

        # WP-3 fix-round M-1 (Opus review): site-level sibling of the
        # in-memory test's own addition -- `credential_store_postgres.py`'s
        # `authenticate`'s PRE-AUTH branch (row is None) above is
        # structurally distinct product code from its own `if not valid:`
        # branch a few lines down (`credential_store_postgres.py:445` --
        # a REAL, digest-matched row refused only by its own enabled/
        # revoked/app-enabled/expiry state). A real application + credential
        # is provisioned through the control plane (the SAME `applications`/
        # `credentials` tables this store reads, `control_platform.
        # registry_schema`), then the credential is DISABLED before
        # authenticating with its own still-correct secret.
        real_app_pg = "n_word_real_app_pg_" + secrets.token_hex(4)
        h.service.register_application(h.control_credential_id, h.control_credential_secret, real_app_pg)
        h.service.set_application_enabled(h.control_credential_id, h.control_credential_secret, real_app_pg, True)
        issued = h.service.issue_credential(h.control_credential_id, h.control_credential_secret, real_app_pg, "runtime")
        real_credential_id_pg, real_secret_pg = issued["credential_id"], issued["secret"]
        h.service.set_credential_enabled(h.control_credential_id, h.control_credential_secret, real_credential_id_pg, False)
        with pytest.raises(Exception):
            pg_store.authenticate(real_credential_id_pg, real_secret_pg)  # -> credential_store_postgres.py:445's `if not valid:` branch

        time.sleep(h.visibility_lag_ms / 1000 + 0.5)
        result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 200})
        events = result["events"]
        assert events, "the postgres exercise above must have produced at least one durable row (常設規律1)"
        observed_operations = {e["operation"] for e in events}
        observed_target_kinds = {e["target_kind"] for e in events}
        assert "authenticate" in observed_operations, (
            f"a failed PostgresCredentialStore.authenticate() must durably record operation='authenticate': {observed_operations!r}"
        )
        assert "assert_active" in observed_operations, (
            f"a failed PostgresCredentialStore.assert_active() must durably record operation='assert_active': {observed_operations!r}"
        )
        assert "credential" in observed_target_kinds, f"both denials must durably record target_kind='credential': {observed_target_kinds!r}"

        # WP-3 fix-round M-1: site-level proof -- a durable row carrying the
        # REAL, resolved credential/application identity (`credential_
        # store_postgres.py:445`'s own `if not valid:` branch specifically)
        # must exist.
        assert any(
            event.get("actor_id") == real_credential_id_pg and event.get("application_id") == real_app_pg
            and event["operation"] == "authenticate"
            for event in events
        ), (
            f"a disabled-but-real credential's failed authenticate() must durably record the REAL credential_id/"
            f"application_id (credential_store_postgres.py's `if not valid:` branch), not only the pre-auth "
            f"branch's attributionless row: {events!r}"
        )
    finally:
        _cleanup_postgres(control_platform)


def test_declared_event_classes_cover_every_emittable_class() -> None:
    """Property 5 / P4-D16 v3(e), now calling the generalized `_field_
    literal_union` instead of an inline keyword-sites-only loop (the two
    are equivalent for `event_class`, which has no `name_assign`-position
    IfExp/Constant sites in this package)."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
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

    from mitatedb_api.application_audit import DECLARED_AUDIT_EVENT_CLASSES as APP_CLASSES
    assert APP_CLASSES <= declared


def test_declared_operations_cover_every_emittable_operation() -> None:
    """P4-D16 v3(e) for `operation` (design D-1). Same `U == D | N`, `D & N
    == set()` equality as `event_class` above, now load-bearing (this WP
    flips `contract_version` to 1.5.0 in the same commit)."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
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


def test_declared_target_kinds_cover_every_emittable_target_kind() -> None:
    """P4-D16 v3(e) for `target_kind` (design D-1)."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
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


# ===========================================================================
# Phase 4 ledger closure WP-B3 addendum, generalized for Phase 5: `U == D |
# N` cannot detect D SHRINKING while a matching word simultaneously moves
# into N. Pins each declared vocabulary's own CONTENT directly. 2-module
# construction (control half + application half, `audit_query.py`/
# `application_audit.py`) -- these snapshots pin the UNION public
# definition, never one half alone, so a change to EITHER half is caught
# (WP-3 変更対象 E's own instruction, mutation 13).
# ===========================================================================


def test_declared_audit_event_classes_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_EVENT_CLASSES` (`audit_query.py:76`,
    `_CONTROL_PLANE_EVENT_CLASSES | application_audit.DECLARED_AUDIT_EVENT_
    CLASSES`) currently holds exactly these 12 words. Dropping a word out
    of D and into N (WP-B1's (e), `test_declared_event_classes_cover_
    every_emittable_class` above -- N is `set()` for this peer today) is
    NOT detected by that test alone -- `U == D ∪ N` stays satisfied either
    way, so a downgrade could land silently. This test's only job is to
    force the declaration itself to be a deliberate, single-commit edit:
    changing `DECLARED_AUDIT_EVENT_CLASSES` (or either half it is built
    from) without updating this literal here fails immediately."""
    assert DECLARED_AUDIT_EVENT_CLASSES == frozenset(
        {
            "authentication_denial",
            "authorization_denial",
            "capability_denial",
            "application_lifecycle",
            "credential_lifecycle",
            "control_credential_lifecycle",
            "schema_change",
            "destructive_data_operation",
            "data_operation",
            "authentication_denied",
            "authorization_denied",
            "security_control_failure",
        }
    )


def test_declared_audit_operations_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_OPERATIONS` (`audit_query.py`,
    `_CONTROL_PLANE_OPERATIONS | application_audit.DECLARED_AUDIT_
    OPERATIONS`) currently holds exactly these 29 words -- the full
    emitted union U (30 words, `_field_literal_union`) minus N's 1 word
    (`_NON_DURABLE_OPERATIONS`: `control_capabilities`, structurally
    deny-unreachable). Pins the UNION, not either half alone (mutation 13
    must go red whichever half loses a word)."""
    assert DECLARED_AUDIT_OPERATIONS == frozenset(
        {
            "access",
            "add_field",
            "assert_active",
            "audit_buffer",
            "audit_query",
            "authenticate",
            "bootstrap_control_credential",
            "control_authenticate",
            "create_collection",
            "delete",
            "disable_application",
            "disable_credential",
            "enable_application",
            "enable_credential",
            "freeze_issuance",
            "insert",
            "issue_audit_credential",
            "issue_credential",
            "list_applications",
            "list_credentials",
            "query",
            "register_application",
            "reset_control_credentials",
            "revoke_credential",
            "rotate_credential",
            "schema",
            "transact",
            "unfreeze_issuance",
            "update",
        }
    )


def test_declared_audit_target_kinds_change_only_deliberately() -> None:
    """Snapshot guard: `DECLARED_AUDIT_TARGET_KINDS` (`audit_query.py`,
    `_CONTROL_PLANE_TARGET_KINDS | application_audit.DECLARED_AUDIT_
    TARGET_KINDS`) currently holds exactly these 5 words."""
    assert DECLARED_AUDIT_TARGET_KINDS == frozenset(
        {
            "application",
            "audit_sink",
            "collection",
            "control_credential",
            "credential",
        }
    )


async def _async_test_audit_query_declares_operations_and_target_kinds_over_http() -> None:
    h, app = _memory_control_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/control/v1/capabilities", headers=_auth(h.control_credential_id, h.control_credential_secret))
        assert response.status_code == 200
        document = response.json()
        declared = document["capabilities"]["audit_query"]
        assert set(declared["operations"]) == DECLARED_AUDIT_OPERATIONS
        assert set(declared["target_kinds"]) == DECLARED_AUDIT_TARGET_KINDS


def test_audit_query_declares_operations_and_target_kinds_over_http() -> None:
    """完了条件9 (宣言キーの露出): the `operations`/`target_kinds` keys
    reach a real HTTP client, not merely the in-process `control_
    capabilities()` dict."""
    asyncio.run(_async_test_audit_query_declares_operations_and_target_kinds_over_http())


# ===========================================================================
# Peer isomorphism (常設規律 6, WP-3 完了条件17): the scanner-support
# helpers above are re-implementations (never shared/imported) of
# r2db-api's own `tests/test_audit_query.py` helpers (WP-2). This test
# COMPLETES the isomorphism check WP-2 registered `xfail(strict=True)` on
# the r2db side (that `xfail` is removed in this SAME commit, work order
# WP-3 完了条件17) -- both peers now carry this identical-shaped test.
#
# Phase 6 WP-0 (design D-4(c), L5-5/L5-6): the single-file/named-tuple
# mechanism this section describes is generalized below into the
# `_ISOMORPHIC_TARGETS` (relative path, symbol name) table, which now also
# covers `src/mitatedb_api/main.py::_optional_float` and `tests/test_http.
# py`'s byte-identical-contract test function, not only this file's own 11
# scanner-support helpers -- see that table's own comment for the full
# rationale.
# ===========================================================================


# ---------------------------------------------------------------------------
# Phase 6 WP-0 (design D-4(c), work order §4 WP-0 変更対象 C, L5-5/L5-6):
# the mechanism above (WP-3, "1 file + a tuple of helper names") is
# generalized into a (relative path, symbol name) TABLE -- the pair-per-row
# form is the object that now defines the full set of peer-local symbols
# this repository pins isomorphic, rather than one hardcoded sibling file.
# The 11 rows below are the WP-2/WP-3 helpers, carried over UNCHANGED (not
# one dropped); 4 rows are new this WP: `main.py::_optional_float` and
# `tests/test_http.py`'s byte-identical-contract test function (design
# D-4(a)/(b)), plus the mechanism's OWN two new pieces of test-support code
# -- `_isomorphic_symbol_source` (the row resolver below) and this table's
# own pin test -- added by supervisor review ruling (2026-09-04) so the
# generalized mechanism pins itself the same way it pins everything else it
# was built to check, rather than being exempt from its own guarantee.
# `{package}` is a template slot resolved per side (this peer's own package
# name on the self side, the sibling's on the sibling side) -- the ONLY row
# that needs it is the `main.py` one, since the two peers' package names
# differ but both source trees are `src/<package>/main.py`; every other
# relative path here is peer-name-independent (`tests/test_audit_query.py`,
# `tests/test_http.py` name the same file in both peer checkouts). This
# tuple's own literal text is peer-name-free, so it reads identically in
# r2db-api's own copy of this file.
# ---------------------------------------------------------------------------

_ISOMORPHIC_TARGETS: tuple[tuple[str, str], ...] = (
    ("tests/test_audit_query.py", "_iter_src_files"),
    ("tests/test_audit_query.py", "_literal_leaves"),
    ("tests/test_audit_query.py", "_iter_name_or_attribute_targets"),
    ("tests/test_audit_query.py", "_is_field_assignment_target"),
    ("tests/test_audit_query.py", "_collect_direct_shadow_names"),
    ("tests/test_audit_query.py", "_analyze_field_scope"),
    ("tests/test_audit_query.py", "_FieldForwardResolver"),
    ("tests/test_audit_query.py", "_scan_source_field_sites"),
    # WP-3 fix-round L-4 (Opus review): completion condition 17 names the
    # exclusion-list validators ((i)/(ii') judgment) as part of this same
    # isomorphism check -- omitting them let a peer change (ii')'s own
    # judgment (e.g. dropping the safe-forward id check) go undetected.
    ("tests/test_audit_query.py", "_iter_field_definitions"),
    ("tests/test_audit_query.py", "_field_positional_definitions"),
    ("tests/test_audit_query.py", "_excluded_definition_forwards_its_own_parameter"),
    # Phase 6 WP-0 additions (design D-4(a)/(b)):
    ("src/{package}/main.py", "_optional_float"),
    ("tests/test_http.py", "test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth"),
    # Phase 6 WP-0 additions, round 2 (supervisor review ruling
    # 2026-09-04): the mechanism's own row resolver and pin test, so the
    # generalized mechanism is itself pinned isomorphic, not exempt.
    ("tests/test_audit_query.py", "_isomorphic_symbol_source"),
    ("tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_15_rows"),
)


def test_isomorphic_target_table_is_pinned_to_its_current_15_rows() -> None:
    """WP-0 completion condition 8: a bare `len(_ISOMORPHIC_TARGETS) == 15`
    check would not catch a row silently DROPPED and a different,
    coincidentally-same-length row added in its place -- only pinning the
    table's own full CONTENT (not merely its length) catches that. One-time
    human fixation, same character as Phase 5's "走査対象フィールド集合を
    pin する" test -- a future WP that adds/removes a row edits this
    assertion deliberately, not by accident.

    Self-referential by supervisor ruling (2026-09-04): this function's own
    row, and `_isomorphic_symbol_source`'s, are both IN the table below --
    the table fixes its own driving code isomorphic too, rather than
    treating the mechanism as exempt from the guarantee it enforces on
    every other row. This is not circular: the assertion below is a NAME
    pinned as data (a 2-tuple of strings), evaluated once at call time
    against the already-fully-defined `_ISOMORPHIC_TARGETS` above -- it
    does not recurse into calling itself."""
    assert _ISOMORPHIC_TARGETS == (
        ("tests/test_audit_query.py", "_iter_src_files"),
        ("tests/test_audit_query.py", "_literal_leaves"),
        ("tests/test_audit_query.py", "_iter_name_or_attribute_targets"),
        ("tests/test_audit_query.py", "_is_field_assignment_target"),
        ("tests/test_audit_query.py", "_collect_direct_shadow_names"),
        ("tests/test_audit_query.py", "_analyze_field_scope"),
        ("tests/test_audit_query.py", "_FieldForwardResolver"),
        ("tests/test_audit_query.py", "_scan_source_field_sites"),
        ("tests/test_audit_query.py", "_iter_field_definitions"),
        ("tests/test_audit_query.py", "_field_positional_definitions"),
        ("tests/test_audit_query.py", "_excluded_definition_forwards_its_own_parameter"),
        ("src/{package}/main.py", "_optional_float"),
        ("tests/test_http.py", "test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth"),
        ("tests/test_audit_query.py", "_isomorphic_symbol_source"),
        ("tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_15_rows"),
    )
    assert len(_ISOMORPHIC_TARGETS) == 15


def _isomorphic_symbol_source(peer_root: Path, relative_path_template: str, package: str, symbol: str) -> str | None:
    """Resolves ONE `_ISOMORPHIC_TARGETS` row against `peer_root` (either
    this peer's own root or the sibling's) via a plain TEXT read + `ast.
    parse` -- used for BOTH sides now (WP-0's own L5-6 fix: previously this
    peer's own side used `inspect.getsource` -- which includes any
    decorator line -- while the sibling side used `ast.get_source_segment`
    -- whose `FunctionDef.lineno` starts at the `def`/`class` keyword,
    never the decorator, per CPython's own AST docs -- so a future
    decorator on either side alone would have flipped this test red/green
    on THAT ASYMMETRY, not on an actual implementation difference. Only
    top-level (`tree.body`) definitions are matched, same restriction the
    WP-2/WP-3 mechanism already applied -- deliberately not `ast.walk`,
    which would also match a same-named symbol nested inside an unrelated
    class/function and silently diff the wrong one. Returns `None` if the
    file does not exist or does not define `symbol` at module level (the
    caller decides what that means for each side)."""
    path = peer_root / relative_path_template.format(package=package)
    if not path.exists():
        return None
    source = path.read_text()
    tree = _ast.parse(source, filename=str(path))
    node = next(
        (n for n in tree.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)) and n.name == symbol),
        None,
    )
    if node is None:
        return None
    return _ast.get_source_segment(source, node)


def test_peer_local_helpers_are_isomorphic_to_the_sibling_peer() -> None:
    """常設規律6: diffs this peer's own `_ISOMORPHIC_TARGETS` symbols
    against r2db-api's own same-named symbols at the same relative paths,
    after normalizing peer package name / trailing whitespace / blank-line
    runs -- proving the two independently (never shared-module)
    implementations agree, without sharing code between peers.

    Table-driven generalization of the WP-2/WP-3 mechanism (design D-4(c),
    L5-5/L5-6): the prior form read one hardcoded sibling file
    (`tests/test_audit_query.py`) and diffed 11 named helpers found inside
    it; `_ISOMORPHIC_TARGETS` above widens that to 15 rows spanning THREE
    files (`tests/test_audit_query.py`, `src/<package>/main.py`,
    `tests/test_http.py`), so this WP's own new same-named symbols
    (`_optional_float`, the byte-identical-contract test function) fall
    under the SAME peer-symmetry guarantee `_optional_float` (a product
    file, not a test-support helper) would otherwise have had none of.

    The sibling side is read as TEXT from its real file path (never
    `importlib.import_module` -- r2db-api's own package name is
    `r2db_api`, not importable from this peer's own test environment
    without adding a cross-peer path hack this repository's own
    no-code-sharing convention avoids). A missing sibling file, or a
    present file lacking one of the target symbols (or defining it with
    different content after normalization), each count as a mismatch. The
    resolved sibling root is asserted to point at the r2db-api sibling,
    never back at this peer's own root, so a future edit cannot
    accidentally make this a self-comparison."""
    import re

    def _normalize(source: str, *, package: str) -> str:
        """WP-3 fix-round M-2 (Opus review): normalizes ONLY (a) this
        peer's own package name (substituted for a neutral placeholder),
        (b) TRAILING whitespace at the end of each line, and (c) the
        number of consecutive blank lines (collapsed to none) -- NEVER
        leading indentation and NEVER in-line token spacing. The PRIOR
        form (`re.sub(r"[ \t]+", " ", text)`) collapsed every run of
        spaces/tabs ANYWHERE, including a line's own leading indentation --
        which made a nesting-depth-only mutation (moving a branch one
        `if`/`else` level deeper, or shallower, with the exact same token
        sequence and no operator/condition change at all) invisible to
        this comparison: Python's own semantics are indentation-sensitive,
        so an indentation-only edit is a REAL logic change this test must
        catch, not whitespace noise to discard. WP-0 drops the separate
        `peer_module` substitution the WP-2/WP-3 form also took: none of
        the 15 target symbols' own source text (verified when this table
        was assembled) references either peer's test-module name at all,
        only (occasionally) its own package name, so a second substitution
        parameter that never fires is dead generality, not a real need."""
        text = source.replace(package, "<PEER_PACKAGE>")
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()

    self_root = Path(__file__).resolve().parents[1]
    sibling_root = Path(__file__).resolve().parents[2] / "r2db-api"
    assert "r2db-api" in sibling_root.parts, f"sibling root must resolve under r2db-api, not self: {sibling_root}"
    assert "MitateDB-api" not in sibling_root.parts, f"sibling root must never resolve back into MitateDB-api: {sibling_root}"

    mismatches: list[str] = []
    for relative_path_template, symbol in _ISOMORPHIC_TARGETS:
        self_src = _isomorphic_symbol_source(self_root, relative_path_template, "mitatedb_api", symbol)
        if self_src is None:
            raise AssertionError(
                f"this peer's own table row does not resolve against its own tree -- a table bug, not a sibling "
                f"mismatch: {relative_path_template}::{symbol}"
            )
        sibling_src = _isomorphic_symbol_source(sibling_root, relative_path_template, "r2db_api", symbol)
        if sibling_src is None:
            mismatches.append(f"{relative_path_template}::{symbol}")  # not (yet) present on the sibling side
            continue
        if _normalize(self_src, package="mitatedb_api") != _normalize(sibling_src, package="r2db_api"):
            mismatches.append(f"{relative_path_template}::{symbol}")
    assert not mismatches, f"peer-local symbol(s) not isomorphic after normalization (or missing on the sibling side): {mismatches!r}"


def test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts(control_platform) -> None:
    h = _postgres_harness(control_platform, audit_statement_timeout_ms=3_000, audit_idle_timeout_ms=4_000)
    try:
        document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
        assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 3_000 + 4_000 + 1_000
    finally:
        _cleanup_postgres(control_platform)


def test_in_memory_visibility_lag_ms_is_zero_by_construction() -> None:
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 0


def test_declared_coalescing_window_ms_matches_the_single_source_constant() -> None:
    """WP-3(b) (r2db-api WP-2(b) review item H, avoided from the start):
    the declared value is derived from `application_audit.DEFAULT_DENIAL_
    COALESCE_WINDOW_S` -- the SAME constant `audit_dispatch.AuditRouter`'s
    own default falls back to -- via `audit_query.DEFAULT_COALESCING_
    WINDOW_MS`, never a second, independently-maintained literal."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["capabilities"]["audit_query"]["coalescing_window_ms"] == int(DEFAULT_DENIAL_COALESCE_WINDOW_S * 1000)
    assert DEFAULT_COALESCING_WINDOW_MS == int(DEFAULT_DENIAL_COALESCE_WINDOW_S * 1000)


def test_coalesced_and_alert_rows_never_carry_a_literal_count_of_0_or_1() -> None:
    """D-3/D-4 property 10(ii)/property 3 (never zero or one). Exercises
    `application_audit.coalesced_count` directly (WP-3(a)'s own structural
    guard) plus confirms `audit_query`'s own row-shaping never re-injects a
    literal 1 for an absent count."""
    from mitatedb_api.application_audit import coalesced_count
    assert coalesced_count(0) is None
    assert coalesced_count(1) is None
    assert coalesced_count(2) == 2
    h = _memory_harness()
    _write_application_audit_row(h, request_id="countnone", count=None)
    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000})
    matched = [e for e in result["events"] if e.get("request_id") == "countnone"]
    assert len(matched) == 1
    assert "count" not in matched[0]


def test_forbidden_fields_never_appear_as_keys_or_reusable_secret_values() -> None:
    """SI-10. `_shape_audit_query_row` is a whitelist-construction function
    -- structurally cannot emit `credential`/`token`/`password`/`secret`/
    `private_key`/`sql`/`row_value` as keys."""
    h = _memory_harness()
    _write_application_audit_row(h, request_id="forbiddenprobe")
    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1000})
    forbidden = {"credential", "token", "password", "secret", "private_key", "sql", "row_value"}
    for event in result["events"]:
        assert not (forbidden & set(event)), f"forbidden field key present: {event!r}"
        for value in event.values():
            if isinstance(value, str):
                assert h.control_credential_secret not in value


# ---------------------------------------------------------------------------
# default page size (coordinator instruction 9)
# ---------------------------------------------------------------------------


def test_omitted_limit_applies_the_declared_default_limit_not_the_full_set() -> None:
    """Coordinator instruction 9 (review finding I): `_DEFAULT_AUDIT_QUERY_
    LIMIT` is D-6's own declared default (100) for an OMITTED `limit` --
    mutation E1 (100 -> 7) previously passed all 27 pre-fix tests
    undetected. Two assertions, deliberately NOT sharing one import-and-
    compare-to-itself value: (1) the constant itself is pinned against the
    literal `100` D-6 declares (a mutation of the constant alone fails
    here even if nothing else changes), and (2) writing more than 100 rows
    and calling `audit_query` with no `limit` key returns EXACTLY the
    literal `100`, proving the constant is genuinely applied, not merely
    declared. A mutation that moves the constant AND leaves the applied
    behavior consistent with the new value still fails assertion (1)."""
    from mitatedb_api.control_plane import _DEFAULT_AUDIT_QUERY_LIMIT

    assert _DEFAULT_AUDIT_QUERY_LIMIT == 100, (
        f"D-6 declares the default audit_query page size as 100; got {_DEFAULT_AUDIT_QUERY_LIMIT!r}"
    )

    h = _memory_harness()
    marker = "defaultlimit" + secrets.token_hex(4)
    total_written = 105
    for i in range(total_written):
        _write_application_audit_row(h, request_id=f"{marker}-{i}", event_id=uuid.uuid4().hex)

    result = h.service.audit_query(h.control_credential_id, h.control_credential_secret, {})
    assert len(result["events"]) == 100, (
        f"omitting 'limit' must return exactly 100 events when more are available, got {len(result['events'])}"
    )
    matched = [e for e in result["events"] if e.get("request_id", "").startswith(marker)]
    assert len(matched) < total_written, (
        "every probe row came back on one page -- the default limit is not actually capping the result"
    )


def test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute() -> None:
    from mitatedb_api.errors import ResourceLimitError
    h = _memory_harness(limits=ControlPlaneLimits(
        applications=50, credentials_per_application=10, control_requests_per_minute=200, audit_requests_per_minute=2))
    h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1})
    h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1})
    with pytest.raises(ResourceLimitError) as excinfo:
        h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1})
    assert excinfo.value.details["limit_class"] == "audit_requests_per_minute"


# `ControlPlaneLimits.__post_init__`'s own bound (design v1.5 WP-0 M-5):
# `control_requests_per_minute` must exceed `applications + 2 *
# credentials_per_application + 67`, independent of this WP -- with the
# smallest legal `applications`/`credentials_per_application` (1 each),
# the smallest legal `control_requests_per_minute` is 71.
_TIGHT_CONTROL_WINDOW = ControlPlaneLimits(
    applications=1, credentials_per_application=1, control_requests_per_minute=71, audit_requests_per_minute=200)


def test_audit_query_does_not_consume_the_control_requests_per_minute_window() -> None:
    """M-4 (mirrors r2db-api's own equivalent, avoided-pitfall list item
    "control 窓非消費...未固定"): 200 `audit_query` calls must leave the
    SEPARATE `control_requests_per_minute` window's own full budget intact
    -- if `audit_query` wrongly shared the counter, the very FIRST `control_
    capabilities` call below would already be refused (the 200 calls would
    have exhausted it first); this test distinguishes that from the
    genuine, expected exhaustion point."""
    from mitatedb_api.errors import ResourceLimitError
    h = _memory_harness(limits=_TIGHT_CONTROL_WINDOW)
    for _ in range(200):
        h.service.audit_query(h.control_credential_id, h.control_credential_secret, {"limit": 1})
    successful = 0
    exceeded = False
    for _ in range(_TIGHT_CONTROL_WINDOW.control_requests_per_minute + 5):
        try:
            h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
            successful += 1
        except ResourceLimitError as exc:
            assert exc.details["limit_class"] == "control_requests_per_minute"
            exceeded = True
            break
    assert exceeded, "control_requests_per_minute never tripped at all"
    # `_memory_harness`'s own setup already consumed 1 token (`rotate_
    # credential`), so the genuine budget remaining is `limit - 1` -- a
    # PREMATURE exhaustion (far fewer successful calls) would mean the 200
    # audit_query calls above wrongly ate into this window too.
    assert successful >= _TIGHT_CONTROL_WINDOW.control_requests_per_minute - 2, (
        f"control_requests_per_minute exhausted after only {successful} calls -- "
        f"the 200 audit_query calls appear to have consumed it"
    )


def test_audit_requests_per_minute_is_declared_enforced_in_control_capabilities() -> None:
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["limits"]["audit_requests_per_minute"] == _GENEROUS_LIMITS.audit_requests_per_minute
    assert document["limit_enforcement"]["audit_requests_per_minute"] == "enforced"


# ---------------------------------------------------------------------------
# contract_version 1.4.0
# ---------------------------------------------------------------------------


def test_control_capabilities_declares_contract_version_1_5_0() -> None:
    """Phase 5 WP-3 (design D-4/§8, subordinate ruling 10): re-flipped to
    1.5.0 in the same commit as the `operations`/`target_kinds`
    declaration keys (flip and behavior land together, never separately)."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["contract_version"] == "1.5.0"


# ---------------------------------------------------------------------------
# HTTP route table (real ASGI app, in-memory backend for speed)
# ---------------------------------------------------------------------------


def _memory_control_app():
    h = _memory_harness()
    app = create_control_app(h.service, request_bytes_limit=1_048_576)
    return h, app


async def _async_test_control_host_serves_both_audit_query_paths_with_one_handler() -> None:
    h, app = _memory_control_app()
    route_map = {route.path: route.endpoint for route in _ROUTES if route.path.endswith("audit/query")}
    assert set(route_map) == {"/control/v1/audit/query", "/v1/audit/query"}
    assert route_map["/control/v1/audit/query"] is route_map["/v1/audit/query"]

    marker = "twopaths" + secrets.token_hex(4)
    _write_application_audit_row(h, request_id=marker)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _auth(h.control_credential_id, h.control_credential_secret)
        canonical = await client.post("/control/v1/audit/query", headers=headers, json={"limit": 1000})
        alias = await client.post("/v1/audit/query", headers=headers, json={"limit": 1000})
        assert canonical.status_code == alias.status_code == 200
        assert canonical.json() == alias.json(), "the two paths must answer with the byte-identical response body"
        assert any(e.get("request_id") == marker for e in canonical.json()["events"])


def test_control_host_serves_both_audit_query_paths_with_one_handler() -> None:
    asyncio.run(_async_test_control_host_serves_both_audit_query_paths_with_one_handler())


async def _async_test_application_credential_is_forbidden_over_http() -> None:
    h, app = _memory_control_app()
    with h.backend.unit_of_work() as work:
        h.backend.register_application("fbdhttpapp", work=work)
        h.backend.issue_credential("fbdhttpapp", "runtime", credential_id="crd_fbdhttp", secret="httpsecret1234567890", work=work)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/control/v1/audit/query", headers=_auth("crd_fbdhttp", "httpsecret1234567890"), json={"limit": 1})
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"


def test_application_credential_is_forbidden_on_the_control_host_audit_query_over_http() -> None:
    asyncio.run(_async_test_application_credential_is_forbidden_over_http())


async def _async_test_audit_query_wire_calls_never_consume_the_control_requests_per_minute_window() -> None:
    limits = ControlPlaneLimits(
        applications=1, credentials_per_application=1, control_requests_per_minute=71, audit_requests_per_minute=200)
    h = _memory_harness(limits=limits)
    app = create_control_app(h.service, request_bytes_limit=1_048_576)
    transport = httpx.ASGITransport(app=app)
    headers = _auth(h.control_credential_id, h.control_credential_secret)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        for path in ("/control/v1/audit/query", "/v1/audit/query"):
            for _ in range(50):
                response = await client.post(path, headers=headers, json={"limit": 1})
                assert response.status_code == 200, response.json()
        # `control_requests_per_minute`'s own full budget (minus the 1
        # token `_memory_harness`'s own setup already spent) is still
        # available -- 68 more `GET /control/v1/capabilities` succeed.
        statuses = []
        for _ in range(limits.control_requests_per_minute + 2):
            response = await client.get("/control/v1/capabilities", headers=headers)
            statuses.append(response.status_code)
            if response.status_code == 413:
                assert response.json()["details"]["limit_class"] == "control_requests_per_minute"
                break
    assert 413 in statuses, "control_requests_per_minute never tripped at all"
    assert statuses.count(200) >= limits.control_requests_per_minute - 2, (
        f"control_requests_per_minute exhausted prematurely (only {statuses.count(200)} 200s) -- "
        f"the 100 audit_query wire calls above appear to have consumed it"
    )


def test_audit_query_wire_calls_never_consume_the_control_requests_per_minute_window() -> None:
    asyncio.run(_async_test_audit_query_wire_calls_never_consume_the_control_requests_per_minute_window())


async def _async_test_audit_query_rate_limit_is_pre_auth_and_reaches_http_as_413() -> None:
    """WP-3(b) (r2db-api WP-2(b) review M-5, avoided from the start):
    `audit_requests_per_minute` is charged BEFORE authentication, over
    real HTTP -- no `Authorization` header at all still trips the window."""
    h = _memory_harness(limits=ControlPlaneLimits(
        applications=1, credentials_per_application=1, control_requests_per_minute=200, audit_requests_per_minute=2))
    app = create_control_app(h.service, request_bytes_limit=1_048_576)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        first = await client.post("/control/v1/audit/query")
        second = await client.post("/control/v1/audit/query")
        third = await client.post("/control/v1/audit/query")
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 413
    body = third.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["details"]["limit_class"] == "audit_requests_per_minute"


def test_audit_query_rate_limit_is_pre_auth_and_reaches_http_as_413() -> None:
    asyncio.run(_async_test_audit_query_rate_limit_is_pre_auth_and_reaches_http_as_413())


# ---------------------------------------------------------------------------
# reader DSN INSERT refusal (real Postgres, migration 0005's own GRANT)
# ---------------------------------------------------------------------------


def test_auditreader_role_can_select_both_audit_tables_and_cannot_insert(control_platform) -> None:
    conn = psycopg.connect(control_platform.auditreader_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(control_platform.registry_schema, "control_audit")))
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(control_platform.registry_schema, "application_audit")))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(sql.SQL(
                    "INSERT INTO {} (event_id, event_class, occurred_at, request_id, application_id, actor_type, "
                    "actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) VALUES "
                    "('x', 'data_operation', now(), NULL, NULL, NULL, NULL, NULL, 'query', NULL, 'allow', NULL, NULL, NULL)"
                ).format(sql.Identifier(control_platform.registry_schema, "application_audit")))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# control/data-plane route table disjointness
# ---------------------------------------------------------------------------


def test_control_and_data_plane_route_tables_are_disjoint_except_the_audit_query_alias() -> None:
    """control_http.py's own comment above `_ROUTES` claims this test by
    name -- fixed here so that claim is never a dangling reference (r2db-
    api WP-2(b) review §4-H's own "comment cites a nonexistent test"
    pitfall, avoided from the start): `/v1/audit/query` is the ONE
    deliberate `/v1/...`-shaped path in the control route table, and it is
    the SAME path the data-plane's own `http.py::_ROUTES` also registers
    (as its own, permanently-`CAPABILITY_UNSUPPORTED`-answering stub,
    unchanged by this WP)."""
    from mitatedb_api.http import _ROUTES as DATA_ROUTES

    control_paths = {route.path for route in _ROUTES}
    assert all(path.startswith("/control/v1") or path == "/v1/audit/query" for path in control_paths)
    data_paths = {route.path for route in DATA_ROUTES}
    assert not any(path.startswith("/control") for path in data_paths)
    assert "/v1/audit/query" in data_paths
    assert "/v1/audit/query" in control_paths
