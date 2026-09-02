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


def test_declared_event_classes_cover_every_emittable_class() -> None:
    """Property 5. AST-scans EVERY `src/mitatedb_api/*.py` file (never a
    hand-maintained file list) for a real durable `event_class=` call
    site (keyword/`.append(...)` forms alike) and requires the declared
    union (`audit_query.DECLARED_AUDIT_EVENT_CLASSES`) to be a superset of
    everything actually emittable.

    WP-3(b) review round 2 finding 2 (supervisor-forwarded fix): a prior
    version of this scan enumerated an explicit file list
    (`control_plane.py`, `ops.py`) -- WP-3(b) review finding E's own fix
    for the FIRST such gap (`ops.py` missing). But a hand-maintained list
    is the same class of gap by construction: `http.py:419`'s own real
    `AuditRouter.route_denial(..., event_class="authentication_denied",
    ...)` call site (the pre-auth AUTH_REQUIRED denial) was OUTSIDE that
    list too, and mutating it to an undeclared literal passed this test
    green (confirmed). Scanning every file under `src/mitatedb_api/`
    (`Path.glob("*.py")`, no enumeration at all) closes this class of gap
    structurally -- a future new module with its own emit site is picked
    up automatically."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    declared = set(document["capabilities"]["audit_query"]["event_classes"])
    assert declared == DECLARED_AUDIT_EVENT_CLASSES

    import ast
    from pathlib import Path

    # Scans EVERY `Call` node's `event_class=` keyword, unfiltered by
    # callee name AND by source file -- deliberately more robust than
    # either a callee-name allowlist (r2db-api's own WP-2(b) review gap:
    # missed a `.append(event_class=...)` form) or a hand-enumerated file
    # list (this file's own WP-3(b) round-1 gap: missed `ops.py`, then
    # round-2's own `http.py:419`).
    src_dir = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    literals: set[str] = set()
    unresolved: list[str] = []
    for path in sorted(src_dir.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=path.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = next((k for k in node.keywords if k.arg == "event_class"), None)
            if kw is None:
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                literals.add(kw.value.value)
            elif isinstance(kw.value, ast.Name) and kw.value.id == "event_class":
                # `_deny_audit`'s own generic `self._backend.append_audit(
                # work=work, event_class=event_class, ...)` forward -- ITS
                # OWN call sites (`self._deny_audit(event_class="<literal>",
                # ...)`, caught directly by this same unfiltered scan) are
                # what carry the real literals; this one internal forward
                # of the enclosing function's own parameter is a KNOWN,
                # deliberate pass-through, not an unresolved site.
                continue
            else:
                unresolved.append(f"{path.name}:{node.lineno}")
    assert not unresolved, f"unresolvable event_class call site(s): {unresolved!r}"
    assert literals, "the AST scanner found zero event_class literals across src/mitatedb_api/*.py -- it is itself broken"
    assert literals <= declared, f"emittable but undeclared (package-wide scan): {literals - declared!r}"

    # The application-plane's own declared vocabulary (already AST-fixed
    # against real emit sites by WP-3(a)'s own `test_declared_event_
    # classes_cover_every_emittable_class`) must also be a subset of the
    # union this WP declares.
    from mitatedb_api.application_audit import DECLARED_AUDIT_EVENT_CLASSES as APP_CLASSES
    assert APP_CLASSES <= declared


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


def test_control_capabilities_declares_contract_version_1_4_0() -> None:
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    assert document["contract_version"] == "1.4.0"


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
