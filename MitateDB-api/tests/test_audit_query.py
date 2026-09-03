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


# WP-B1 (P4-D16 v3, docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md
# §1/§4): this whole block replaces the earlier package-wide scan (which
# lived only in THIS function) with the SAME four independent,
# callee-name-FILTER-FREE checks r2db-api's own `test_audit_query.py`
# uses (same helper names, same shapes -- "両 peer の走査ヘルパは同型に
# する"):
#
#   (a) `_iter_src_files()` -- every `*.py` under `src/mitatedb_api/`,
#       found by a RECURSIVE `rglob` (this file's own prior version used
#       a non-recursive top-level-only `glob` -- widened here to match
#       r2db-api and to guarantee a future new subpackage's own emission
#       call sites can never silently fall outside this guard).
#   (b) literal discipline (`test_every_event_class_keyword_argument_is_a_
#       string_literal`) -- every `Call` anywhere in the package that
#       carries an `event_class=` keyword must pass a string `Constant`,
#       or be the recognized parameter-forward shape (`event_class=
#       event_class`). Unfiltered by callee name, as this file's own scan
#       already was before this WP.
#   (c) definition-side keyword-only guarantee (`test_every_definition_
#       taking_event_class_declares_it_keyword_only`) -- every `def`/
#       `async def` anywhere under `src/mitatedb_api/` that takes
#       `event_class` as a formal parameter must declare it keyword-only.
#       MitateDB's product code already satisfies this everywhere (every
#       real definition -- `AuditRouter.make_pre_commit_hook`/
#       `.route_denial`/`.push_buffer_event`, `control_plane.py`'s
#       `_deny_audit`, the durable sinks' own `.append`/
#       `insert_control_audit_row` -- declares `event_class` after a bare
#       `*`), so this WP makes NO product-code change here; the test only
#       fixes that this stays true.
#   (d) dict-smuggling ban (`test_no_event_class_string_literal_is_
#       smuggled_through_a_dict`) -- no `{"event_class": "<literal>"}`
#       dict literal or `x["event_class"] = "<literal>"` subscript
#       assignment anywhere in the package. Zero violations today.
#   (e) exact vocabulary-relation match (this function, kept under its
#       original name) -- with (b)/(c)/(d) closing every literal-hiding
#       path, the full literal union U found by (b)'s own walk must equal
#       `D | N` with `D & N == set()`, where D is the declared vocabulary
#       (`audit_query.DECLARED_AUDIT_EVENT_CLASSES`, unchanged by this WP)
#       and N is an explicit non-durable exclusion set. **MitateDB's own
#       N is EMPTY** -- the diagnostic behind this WP confirmed every real
#       MitateDB emit site reaches a durable table (unlike r2db's
#       `_control_event`, whose `control_failure`/`control_state`
#       literals stay in a legacy in-memory-only sink).
#
# v2 of this WP ("three-way match": a name-derived "emit definition set"
# cross-checked against call sites) was proposed and withdrawn before
# implementation -- round-1 independent review found it would falsely
# flag every unrelated `list.append()` call (46 in this package alone,
# since the durable sinks' own `.append` shares that name) AND would miss
# `control_audit`'s real emit sites entirely (they route through
# `append_audit(**fields)` forwarding wrappers that never themselves
# declare `event_class` as a parameter). (b)-(e) above route around both
# failure modes without any callee-name-keyed definition set at all.
import ast as _ast  # noqa: E402 -- kept local to this test-support block, mirrors r2db-api's own test_audit_query.py
from pathlib import Path  # noqa: E402

_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"


def _iter_src_files() -> list[Path]:
    """Every `*.py` file anywhere under `src/mitatedb_api/`, found by a
    RECURSIVE `rglob` -- P4-D16 v3(a). Sorted for deterministic iteration
    order."""
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
      field back out for a READ-path response (this package's own
      `audit_query.py`, whose row-shaping helpers read `event.
      event_class`/`row["event_class"]` for the `audit_query` READ API).
      This is the READ side of D-6/D-7, the structural opposite of an
      emit site: the value it copies was already validated wherever it
      was ORIGINALLY durably written: no new literal can be authored by
      attribute access alone -- PROVIDED the assignment_sites check
      above also holds (an `Attribute` read is only as safe as every
      WRITE that could have produced it).
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
    """P4-D16 v3(b). Every `Call` anywhere under `src/mitatedb_api/` that
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
    """P4-D16 v3(c). Every function/method anywhere under `src/mitatedb_api/`
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
    `Subscript` assignment anywhere under `src/mitatedb_api/` sets an
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
    `AugAssign` anywhere under `src/mitatedb_api/` (module top-level, class
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

# P4-D16 v3(e)'s own N for MitateDB: EMPTY. The diagnostic behind this WP
# confirmed every real MitateDB `event_class` literal reaches a durable
# table (`application_audit` via `AuditRouter`, or `control_audit` via
# `_deny_audit`/`append_audit`) -- unlike r2db's `_control_event`, no
# MitateDB emit path writes a real literal to a legacy/non-durable sink
# only. `D ∩ N == ∅` is trivially true with N empty; kept as an explicit,
# named constant (not simply omitted) so a future non-durable literal, if
# one is ever introduced, has an obvious, symmetric place to be named
# with a rationale rather than silently added to `DECLARED_AUDIT_EVENT_
# CLASSES`.
_NON_DURABLE_EVENT_CLASSES: frozenset[str] = frozenset()


def test_declared_event_classes_cover_every_emittable_class() -> None:
    """Property 5 / P4-D16 v3(e). With (b) closing the callee-name blind
    spot, (c) closing positional passing, and (d) closing dict smuggling,
    every real `event_class` literal anywhere under `src/mitatedb_api/`
    is reachable by (b)'s own unfiltered walk. This test computes that
    full literal union U and fixes `U == D | N` AND `D & N == set()`,
    where D is `audit_query.DECLARED_AUDIT_EVENT_CLASSES` (unchanged by
    this WP) and N is the explicit non-durable exclusion set above
    (empty for MitateDB).

    WP-3(b) review round 2 finding 2 (supervisor-forwarded fix): a prior
    version of this scan enumerated an explicit file list
    (`control_plane.py`, `ops.py`) -- WP-3(b) review finding E's own fix
    for the FIRST such gap (`ops.py` missing). But a hand-maintained list
    is the same class of gap by construction: `http.py:419`'s own real
    `AuditRouter.route_denial(..., event_class="authentication_denied",
    ...)` call site (the pre-auth AUTH_REQUIRED denial) was OUTSIDE that
    list too, and mutating it to an undeclared literal passed this test
    green (confirmed). Scanning every file under `src/mitatedb_api/`
    (RECURSIVE `rglob`, no enumeration at all) closes this class of gap
    structurally -- a future new module's own emit site is picked up
    automatically."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_id, h.control_credential_secret)
    declared = set(document["capabilities"]["audit_query"]["event_classes"])
    assert declared == DECLARED_AUDIT_EVENT_CLASSES

    paths = _iter_src_files()
    emitted: set[str] = set()
    for _filename, _lineno, value, _is_forward in _event_class_keyword_call_sites(paths):
        if isinstance(value, _ast.Constant) and isinstance(value.value, str):
            emitted.add(value.value)
    assert emitted, "the AST scanner found zero event_class literals across src/mitatedb_api/*.py -- it is itself broken"

    d = DECLARED_AUDIT_EVENT_CLASSES
    n = _NON_DURABLE_EVENT_CLASSES
    assert not (d & n), f"declared vocabulary and non-durable exclusion set N overlap (should be disjoint): {d & n!r}"
    assert emitted == d | n, (
        f"emittable-vs-(declared|N) mismatch: "
        f"emitted but neither declared nor in N: {emitted - (d | n)!r}; "
        f"declared or in N but never actually emitted: {(d | n) - emitted!r}"
    )

    # The application-plane's own declared vocabulary (already AST-fixed
    # against real emit sites by WP-3(a)'s own `test_declared_event_
    # classes_cover_every_emittable_class`, now the SOLE surviving test of
    # that name after WP-B1's dedup -- see test_application_audit.py's own
    # removal note) must also be a subset of the union this WP declares.
    from mitatedb_api.application_audit import DECLARED_AUDIT_EVENT_CLASSES as APP_CLASSES
    assert APP_CLASSES <= declared


# ===========================================================================
# Phase 4 ledger closure WP-B3 addendum (監督裁定、WP-B1 監査 M5b 由来,
# design §11.1 未起票 -- 作業指示書 WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md
# §4 WP-B3 追加項目 (e) が正本): `test_declared_event_classes_cover_every_
# emittable_class` above fixes `U == D ∪ N` -- it can never detect D
# SHRINKING while a matching word simultaneously moves into N (a
# "downgrade": declaring a word non-durable without that being a genuine,
# reviewed decision), because that edit keeps `U == D ∪ N` satisfied. This
# test pins `DECLARED_AUDIT_EVENT_CLASSES`'s own CONTENT directly, as a
# frozenset literal, so any change to D -- shrink, grow, or downgrade --
# must touch this test in the same commit as a deliberate, reviewed act.
# Same name as r2db-api's own equivalent (peer-symmetric).
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
