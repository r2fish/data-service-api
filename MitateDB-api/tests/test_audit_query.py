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

from .control_plane_harness import control_platform, set_role_timeouts  # noqa: F401 (fixture)
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
from mitatedb_api.credential_wire import split_bearer_locator
from mitatedb_api.errors import AuthorizationError, CapabilityError, ValidationError
from mitatedb_api.platform_declarations import (PEER_MODULE, MIGRATION_NUMBER,
                                                derive_visibility_lag_ms, read_declared_role_timeouts)

_APP_PEPPER = "audit-query-app-pepper-x0000000"
_CONTROL_PEPPER = "audit-query-ctl-pepper-x0000000"
_GENEROUS_LIMITS = ControlPlaneLimits(
    applications=50, credentials_per_application=10, control_requests_per_minute=200,
    audit_requests_per_minute=200,
)

BASE_URL = "http://mitatedb-audit-query.example.invalid"


def _auth(credential_id: str, secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {credential_id}.{secret}"}


def _bearer_auth(bearer: str) -> dict[str, str]:
    """Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): for a bearer already
    composed by a real issue/rotate response (or the ceremony core) --
    used verbatim, never recomposed via `_auth` above (which is for
    building a bearer out of two SEPARATE, not-yet-composed halves,
    still needed by the one test that constructs a synthetic literal
    credential_id/secret pair)."""
    return {"authorization": f"Bearer {bearer}"}


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
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    # Phase 6 WP-3 追補, round 2 (supervisor ruling 2026-09-04,
    # corrected after empirical finding): `control_auth.
    # ControlCredentialStore.authenticate` takes the RAW secret only
    # now (it can also be reached via a real HTTP boundary that always
    # pre-splits, `tests/test_control_http_unmounted.py`'s own
    # topology) -- this harness is a direct in-process caller, so it
    # splits ONCE here, same as the Postgres-backed harness below.
    secret = bearer
    rotated = service.rotate_credential(secret, cid)
    rotated_secret = rotated["secret"]
    return types.SimpleNamespace(
        service=service, backend=backend, control_audit=backend.audit_sink, application_audit=application_audit,
        control_credential_id=cid, control_credential_secret=rotated_secret,
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
    """Q4 phase (design D-1(b), work order §4 WP-2 変更対象 E): the two
    writer timeouts are no longer `PostgresControlBackend` constructor
    arguments (the SESSION-level `SET` mechanism they configured is
    removed product code, D-1(b)) -- a caller that wants a NON-default
    value now issues `ALTER ROLE ... SET` against both service roles
    (`control_plane_harness.set_role_timeouts`, the SAME mechanism `ops
    set-platform-timeouts`/migration `0007` use) BEFORE constructing
    anything, then reads the real, resulting `visibility_lag_ms` back via
    `platform_declarations.derive_visibility_lag_ms` -- this harness no
    longer computes that value in Python; it is measured against the
    actual role-setting catalog, so a caller overriding these timeouts to
    keep a visibility-lag-dependent test's own wall-clock wait short
    (`audit_statement_timeout_ms=1_000, audit_idle_timeout_ms=1_000`
    style call sites already in this file) still gets a correct, real
    `visibility_lag_ms`."""
    # Always (re)asserted, never only when an override is given: role
    # settings are GLOBAL to the role, unlike the removed per-connection
    # `SET SESSION` this replaces -- `control_platform` is a module-scoped
    # fixture (shared across every test in this file), so a prior test's
    # override would otherwise leak into a later test that asks for the
    # default.
    statement_ms = audit_statement_timeout_ms if audit_statement_timeout_ms is not None else 5000
    idle_ms = audit_idle_timeout_ms if audit_idle_timeout_ms is not None else 5000
    set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=statement_ms, idle_ms=idle_ms)
    set_role_timeouts(
        control_platform.admin_dsn, control_platform.controlplane_role, statement_ms=statement_ms, idle_ms=idle_ms)
    applications = PostgresApplicationRegistry(control_platform.controlplane_dsn, schema=control_platform.registry_schema)
    credentials = PostgresCredentialRegistry(control_platform.controlplane_dsn, pepper=_APP_PEPPER, schema=control_platform.registry_schema)
    control_credentials = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER, schema=control_platform.registry_schema)
    backend = PostgresControlBackend(
        applications=applications, credentials=credentials, control_credentials=control_credentials,
        audit_schema=control_platform.registry_schema, dsn=control_platform.controlplane_dsn,
    )
    audit_reader = PostgresAuditQueryStore(control_platform.auditreader_dsn, schema=control_platform.registry_schema)
    lag_conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        catalogs = [
            read_declared_role_timeouts(lag_conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
            for role in (control_platform.api_role, control_platform.controlplane_role)
        ]
        visibility_lag_ms = derive_visibility_lag_ms(catalogs)
    finally:
        lag_conn.close()
    service = ControlPlaneService(
        backend, limits=limits or _GENEROUS_LIMITS,
        audit_reader=audit_reader, audit_visibility_lag_ms=visibility_lag_ms,
        audit_coalescing_window_ms=DEFAULT_COALESCING_WINDOW_MS,
    )
    with backend.unit_of_work() as work:
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    # Phase 6 WP-3 追補, round 2 (supervisor ruling 2026-09-04): see the
    # in-memory harness's own identical comment above -- this Postgres
    # harness is ALSO a direct in-process caller, so it splits ONCE here.
    secret = bearer
    rotated = service.rotate_credential(secret, cid)
    rotated_secret = rotated["secret"]
    return types.SimpleNamespace(
        service=service, backend=backend, platform=control_platform,
        control_credential_id=cid, control_credential_secret=rotated_secret,
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
    # R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-4): the
    # SAME small-timeout pair this file's own module-scoped `control_
    # platform`-consuming call sites already pass (`_postgres_harness`'s
    # own docstring). This fixture's only lag-dependent consumer reads
    # the lag back from `pg.visibility_lag_ms` (measured from the role
    # catalog by `_postgres_harness`, never a literal), so lowering the
    # seeded pair (11,000 -> 3,000 derived) shortens its wait without
    # changing what it observes (acceptance audit 2026-09-24 corrected
    # this comment's former claim that consumers hold explicit values).
    h = _postgres_harness(control_platform, audit_statement_timeout_ms=1000, audit_idle_timeout_ms=1000)
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
        h.service.audit_query(h.control_credential_secret, {"after": "not-a-real-cursor"})


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
        result = h.service.audit_query(h.control_credential_secret, {"limit": 5, "after": after})
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
        result = h.service.audit_query(h.control_credential_secret, {"limit": 5, "after": after})
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

    result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
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
        result = h.service.audit_query(h.control_credential_secret, {"limit": 1, "after": after})
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
    result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
    matched = [e for e in result["events"] if e.get("request_id") == marker]
    assert len(matched) == 1
    assert matched[0]["plane"] == "application"
    # Never a real, client-settable column: a request naming an unknown
    # "plane" field is silently ignored (there is no writable `plane`
    # parameter to accept in the first place) -- the row above still reads
    # back as "application" regardless.
    still = h.service.audit_query(h.control_credential_secret, {"plane": "control", "limit": 1000})
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
        result = h.service.audit_query(h.control_credential_secret, {"limit": 1, "event_classes": ["data_operation"]})
        assert len(result["events"]) == 1
        first_cursor = result["events"][0]["cursor"]
        second = h.service.audit_query(h.control_credential_secret,
                                       {"limit": 1, "event_classes": ["data_operation"], "after": first_cursor})
        assert len(second["events"]) == 1
        assert second["events"][0]["cursor"] != first_cursor
        # after decodes to a real (recorded_at, plane, event_id) triple.
        decode_cursor(first_cursor)
        empty = h.service.audit_query(h.control_credential_secret, {"event_classes": ["no_such_class_at_all"]})
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
    """R-34 (mirrors r2db-api's own `test_audit_query.py` fix, same
    semantics, no shared code): wall-clock `hold_s`/`probe_at_s` sleeps
    replaced with explicit synchronization, because under machine load
    the writer thread's INSERT could be delayed or the main thread's
    probe could slip independently, producing a spurious red ("the row
    became visible before its writer transaction committed") even though
    the row was still genuinely invisible at the intended probe point.

    The writer signals `inserted` right after its INSERT executes (tx
    open, and the main thread now knows the INSERT's own wall-clock
    time); the main thread waits on it, sleeps only `lag_s + 0.2`
    measured from that INSERT time, probes, asserts invisibility, and
    only then sets `release` so the writer may commit -- "still open" is
    thus guaranteed by the writer never having been told it may commit,
    not by a hold duration guessed in advance.
    """
    h = _postgres_harness(control_platform, audit_statement_timeout_ms=1_000, audit_idle_timeout_ms=1_000)
    try:
        lag_s = h.visibility_lag_ms / 1000  # ~3s at these timeouts
        probe_delay_s = lag_s + 0.2
        marker = "delaytx" + secrets.token_hex(6)

        # WP-3(b) review finding C (supervisor-forwarded fix): a BASELINE
        # cursor captured BEFORE the delayed writer even starts -- the
        # "next page" assertion below pages FORWARD from this cursor
        # (never a fresh limit=1000 re-read of everything), so it
        # genuinely exercises D-6's own cursor-based visibility semantics
        # ("a delayed commit's own row returns on the NEXT PAGE"), not
        # merely PostgreSQL's MVCC (which a blanket re-read conflates
        # with lag-based visibility -- the original form of this test).
        baseline = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
        baseline_events = baseline["events"]
        baseline_cursor = baseline_events[-1]["cursor"] if baseline_events else None

        result_holder: dict = {}
        inserted = threading.Event()
        release = threading.Event()

        def _hold_and_write() -> None:
            conn = psycopg.connect(dsn, autocommit=False)
            try:
                # Q4 phase (design §3.11 point 1: "ALTER ROLE ... SET は
                # role の全接続に効く" -- an empirically-hit consequence,
                # not a hypothetical one): `dsn`'s login role now carries
                # a role-level `idle_in_transaction_session_timeout`
                # (`_postgres_harness` above just set it to
                # `audit_idle_timeout_ms`, e.g. 1000ms) that applies to
                # EVERY connection made as this role -- this test's own
                # simulated "held open" writer connection included, which
                # would otherwise be killed by PostgreSQL itself well
                # before the release event is ever set, never reaching
                # `conn.commit()` at all. This SESSION-level override is
                # test-only scaffolding for one ad hoc connection this
                # test constructs to simulate a slow writer -- not the
                # PRODUCT code path D-1(b) removed `SET SESSION` from.
                with conn.cursor() as cur:
                    cur.execute("SET idle_in_transaction_session_timeout = 0")
                with conn.cursor() as cur:
                    cur.execute(sql.SQL(insert_sql).format(table=sql.Identifier(control_platform.registry_schema, table)), [marker])
                result_holder["inserted_at"] = time.monotonic()
                inserted.set()
                # Bounded wait: if the main thread's probe assertion
                # fails (raises) before calling release.set(), do not
                # hang forever.
                release.wait(timeout=30)
                conn.commit()
            finally:
                conn.close()
            result_holder["done"] = True

        writer = threading.Thread(target=_hold_and_write)
        writer.start()
        assert inserted.wait(timeout=10), "writer did not signal after INSERT in time"
        inserted_at = result_holder["inserted_at"]
        time.sleep(max(0.0, (inserted_at + probe_delay_s) - time.monotonic()))
        assert writer.is_alive() and not release.is_set(), (
            "writer already released/finished before the load-bearing probe point -- "
            "the transaction must still be open (not yet told to commit) at probe time"
        )
        try:
            probe = h.service.audit_query(h.control_credential_secret, {"limit": 1000, "after": baseline_cursor})
            assert not any(e.get("request_id") == marker for e in probe["events"]), (
                "the row became visible before its writer transaction committed -- load-bearing assertion"
            )
        finally:
            # Always release the writer so it can commit and the thread
            # can exit, even if the assertion above raised.
            release.set()
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
            page = h.service.audit_query(h.control_credential_secret, {"limit": 1, "after": after})
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
    result = h.service.audit_query(h.control_credential_secret, {"limit": 1})
    assert "events" in result

    audit_id, audit_bearer = h.backend._control_credentials.issue(role="audit")  # noqa: SLF001
    # Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): `.issue()` returns a
    # COMPOSED bearer; the `secret=` kwarg to `.rotate()` below is a RAW
    # new secret VALUE to set (its own composition precondition rejects a
    # value already containing "."), so this recovers the raw part before
    # rotating to it (a degenerate rotate-to-the-same-value, exercising
    # the rotate mechanism only) -- this is unrelated to the `authenticate`
    # boundary's own one-bearer-in contract; `rotate`'s `secret=` kwarg
    # never was, and still is not, an authentication input.
    _audit_locator_id, audit_raw_secret = split_bearer_locator(audit_bearer)
    audit_bearer2 = h.backend._control_credentials.rotate(audit_id, secret=audit_raw_secret)  # noqa: SLF001
    audit_secret = audit_bearer2
    audit_result = h.service.audit_query(audit_secret, {"limit": 1})
    assert "events" in audit_result


def test_application_credential_is_forbidden_on_the_control_host_audit_query() -> None:
    h = _memory_harness()
    h.backend.register_application("fbdapp", work=None) if False else None
    with h.backend.unit_of_work() as work:
        h.backend.register_application("fbdapp", work=work)
    with h.backend.unit_of_work() as work:
        h.backend.issue_credential("fbdapp", "runtime", credential_id="crd_fbd1", secret="app-secret-1234567890", work=work)
    with pytest.raises(AuthorizationError):
        h.service.audit_query("crd_fbd1.app-secret-1234567890", {"limit": 1})


def test_audit_query_without_audit_dsn_refuses_with_capability_unsupported_not_404() -> None:
    """D-5 M-4: no reader configured -- the SERVICE method answers
    `CAPABILITY_UNSUPPORTED` for a genuinely authenticated caller, both for
    a control credential AND an audit credential (contract 1.4.0
    unconditional obligation (b)'s own explicit combination)."""
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    service = ControlPlaneService(backend, limits=_GENEROUS_LIMITS)  # no audit_reader
    with backend.unit_of_work() as work:
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    rotated = service.rotate_credential(secret, cid)
    secret = rotated["secret"]
    with pytest.raises(CapabilityError):
        service.audit_query(secret, {"limit": 1})

    document = service.control_capabilities(secret)
    assert document["capabilities"]["audit_query"] == {"status": "unavailable"}

    audit_id, audit_bearer = backend._control_credentials.issue(role="audit")  # noqa: SLF001
    # `rotate`'s own `secret=` kwarg is a RAW new secret VALUE to set, not
    # an authentication input -- recover the raw part before rotating to
    # it (degenerate rotate-to-the-same-value, exercising the mechanism).
    _audit_locator_id, audit_raw_secret = split_bearer_locator(audit_bearer)
    audit_bearer2 = backend._control_credentials.rotate(audit_id, secret=audit_raw_secret)  # noqa: SLF001
    audit_secret = audit_bearer2
    with pytest.raises(CapabilityError) as excinfo:
        service.audit_query(audit_secret, {"limit": 1})
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
# D-1). `cell.ApplicationCell._plan_operation` and (WP-3b closure)
# `cell._reconstruct_digest_operation` are the definitions this package
# has whose `operation` parameter is a CLIENT-SUPPLIED mutation value,
# never an audit field -- keyword-only-ifying either would change an
# established positional-call convention (`self._plan_operation(operation)`
# for the first; `_reconstruct_digest_operation`'s own `{"operation":
# operation, ...}` dict-literal forward, which needs a genuine parameter
# to resolve safely either way, for the second) for no audit-safety
# benefit. Each entry names its qualified definition and its
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
        # WP-3b closure (H-1/H-2, 追補 2 監査後): `_reconstruct_digest_
        # operation` is `ApplicationCell.transact`'s own in-process-port
        # fallback for building ONE contract-shaped `operations[]` element
        # the PLAN digest commits to (`cell.py`'s own module level, not a
        # method) -- its `operation` parameter is this one mutation item's
        # contract operation name (`"insert"`/`"update"`/`"delete"`), read
        # from the caller's own internal execution item (`op["type"]`,
        # never a literal), the SAME "plan-digest vocabulary, not audit
        # vocabulary" category `_plan_operation` above already documents.
        # Positional (not keyword-only) is deliberate here too: this
        # function's own `{"operation": operation, ...}` dict-literal use
        # (below) needs `operation` to resolve as a genuine PARAMETER
        # forward for `test_no_field_string_literal_is_smuggled_through_a_
        # dict` to accept it -- a keyword-only parameter would still need
        # this same entry (rule (c) does not distinguish), and its ONE
        # call site (`ApplicationCell.transact`) has no `operation`-named
        # local of its own to forward through a `operation=` keyword call
        # (H-4 -- see `_NON_AUDIT_OPERATION_LITERALS`'s own removal note
        # above -- rules out reintroducing one there).
        "cell._reconstruct_digest_operation",
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

# WP-3b closure (H-4, 追補 2 監査後): NO value-literal exclusion set for
# `operation` -- unlike `_NON_AUDIT_OPERATION_PARAMETERS` above (a real,
# permanent exemption: `_plan_operation`'s own `operation` PARAMETER is a
# client-supplied mutation-item dict, genuinely never an audit field, no
# matter how it is spelled), the WP-3b review round's own `_NON_AUDIT_
# OPERATION_LITERALS = frozenset({"create_entity"})` was a scanner
# work-around for one SPECIFIC name_assign site (`cell.py::Application
# Cell.create_collection` used to bind a local variable literally named
# `operation` to the string `"create_entity"` for its own plan-digest
# object) -- removed by the closure round, per 監督裁定 H-4 ("採らない"):
# `create_collection` now carries that value as its own keyword-only
# PARAMETER default (`operation="create_entity"`, invisible to this
# scanner -- a parameter default lives in `ast.arguments`, never an
# `ast.Assign`/`ast.Call` node `_scan_source_field_sites` below visits at
# all) instead of a local `Assign`, and the client's own request-received
# value (`http.py::post_schema`'s `schema_operation`) is threaded through
# as a real argument on the one path that has it. No literal "create_
# entity" tied to keyword/dict-key "operation" remains anywhere in
# `src/mitatedb_api/` for `_field_literal_union` to find, so `U == D | N`
# (no `N` term at all) holds without any exclusion -- verified by the
# unfiltered assertion in `test_declared_operations_cover_every_
# emittable_operation` below. Reverting this exclusion-set-based
# work-around in favor of the alternative already used elsewhere in this
# same file (`http.py::post_schema`'s own `schema_operation` rename) was
# the precedent WP-3b's own audit round pointed to (C-1).


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
        cid, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    document = service.control_capabilities(secret)  # must NOT raise -- the observable half of _gate_must_rotate's early return
    assert document["contract_version"] == "1.11.0"
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
    document = h.service.control_capabilities(h.control_credential_secret)
    assert document["contract_version"] == "1.11.0"

    fresh_backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    with fresh_backend.unit_of_work() as work:
        # `bootstrap_control_credential` always issues a fresh must_rotate=
        # True credential -- deliberately never rotated here (same
        # construction as `test_control_capabilities_operation_has_no_
        # reachable_deny_branch` above).
        fresh_cid, fresh_bearer = bootstrap_control_credential(fresh_backend.control_credential_store, fresh_backend.append_audit, work=work)
    fresh_secret = fresh_bearer
    fresh_service = ControlPlaneService(fresh_backend, limits=_GENEROUS_LIMITS)
    fresh_document = fresh_service.control_capabilities(fresh_secret)  # must_rotate=True path
    assert fresh_document["contract_version"] == "1.11.0"

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
        store.authenticate("no-such-credential-" + secrets.token_hex(4) + ".wrong-secret")
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
        store.authenticate(real_secret)  # -> auth.py's `if authenticated:` branch (a real, known, but disabled credential)
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
    from mitatedb_api.credential_wire import split_bearer_locator

    h = _postgres_harness(control_platform, audit_statement_timeout_ms=200, audit_idle_timeout_ms=200)
    try:
        pg_sink = PostgresApplicationAuditSink(control_platform.api_dsn, schema=control_platform.registry_schema)
        pg_router = AuditRouter(pg_sink)
        pg_store = PostgresCredentialStore(control_platform.api_dsn, pepper=_APP_PEPPER, schema=control_platform.registry_schema, audit_router=pg_router)

        with pytest.raises(Exception):
            pg_store.authenticate("no-such-credential-pg-" + secrets.token_hex(4) + ".wrong-secret")
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
        h.service.register_application(h.control_credential_secret, real_app_pg)
        h.service.set_application_enabled(h.control_credential_secret, real_app_pg, True)
        issued = h.service.issue_credential(h.control_credential_secret, real_app_pg, "runtime")
        # Phase 6 WP-3 追補 (brief item A): `issued["secret"]` is now the
        # COMPOSED bearer (`ControlPlaneService.issue_credential`'s own
        # response composes it) -- `PostgresCredentialStore.authenticate`
        # below is called DIRECTLY (bypassing the real HTTP boundary,
        # which never splits the bearer itself in the first place, per
        # Phase 6 WP-3 差し戻し 最終ラウンド 裁定 1 -- the store's own
        # `authenticate` is the real receiving boundary that splits it),
        # so this test recovers the raw secret itself, mirroring `test_
        # postgres.py`'s own `_PostgresCredentialHarness.issue` wrapper.
        real_credential_id_pg, real_bearer_pg = issued["credential_id"], issued["secret"]
        real_secret_pg = real_bearer_pg
        h.service.set_credential_enabled(h.control_credential_secret, real_credential_id_pg, False)
        with pytest.raises(Exception):
            pg_store.authenticate(real_secret_pg)  # -> credential_store_postgres.py:445's `if not valid:` branch

        time.sleep(h.visibility_lag_ms / 1000 + 0.5)
        result = h.service.audit_query(h.control_credential_secret, {"limit": 200})
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
    document = h.service.control_capabilities(h.control_credential_secret)
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
    == set()` equality as `event_class` above, load-bearing (contract
    `1.5.0`).

    WP-3b closure (H-4, 追補 2 監査後): the WP-3b review round's own `U`
    filtering step (`_NON_AUDIT_OPERATION_LITERALS`, a work-around for one
    plan-digest `name_assign` site the scanner could not otherwise tell
    apart from a real audit-vocabulary literal) is REMOVED -- `cell.py`
    no longer contains that site at all (moved to a keyword-only
    parameter default, invisible to this scanner by construction; see
    `_NON_AUDIT_OPERATION_LITERALS`'s own former docstring, still present
    immediately above as a removal note). `U` is therefore compared
    directly against `D | N`, unfiltered, exactly like `event_class`
    above."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_secret)
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
    document = h.service.control_capabilities(h.control_credential_secret)
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
    OPERATIONS`) currently holds exactly these 30 words (Phase 9 WP-3a
    adds `alter_field`, design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (5)) --
    the full emitted union U (31 words, `_field_literal_union`) minus N's
    1 word (`_NON_DURABLE_OPERATIONS`: `control_capabilities`,
    structurally deny-unreachable). Pins the UNION, not either half alone
    (mutation 13 must go red whichever half loses a word)."""
    assert DECLARED_AUDIT_OPERATIONS == frozenset(
        {
            "access",
            "add_field",
            "alter_field",
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
        response = await client.get("/control/v1/capabilities", headers=_bearer_auth(h.control_credential_secret))
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
# `_ISOMORPHIC_TARGETS` (r2db relative path, MitateDB relative path,
# symbol name) table, which now also covers `src/mitatedb_api/main.py::
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
# locator` live in `src/r2db_api/auth.py` on r2db-api, `src/mitatedb_api/
# credential_wire.py` on this peer -- a real, intentional per-peer module
# split, not a naming accident). The 15 pre-existing rows migrate
# MECHANICALLY: every row whose path was peer-name-independent repeats
# that same literal path in both slots; the `main.py` row's `{package}`
# template resolves to its two now-literal paths.
# ===========================================================================


# ---------------------------------------------------------------------------
# Phase 6 WP-0 (design D-4(c), work order §4 WP-0 変更対象 C, L5-5/L5-6):
# the mechanism above (WP-3, "1 file + a tuple of helper names") is
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
# item 1's shared bearer-locator realization, WP-2 on r2db-api / WP-3 追補
# on this peer), and the unconditional-`compare_digest` timing-pin test
# (coordinator item 7(i)) -- each peer's 4 `authenticate` methods live
# under DIFFERENT file/class names, so that test's own per-peer {filename:
# {class names}} map is kept OUTSIDE the pinned function body (module-level
# `_TIMING_PIN_TARGETS` in `tests/test_control_plane_store.py`, not
# isomorphism-checked) precisely so the pinned function ITSELF stays
# byte-identical after normalization. This tuple's own literal text is
# peer-name-free (both path slots are now literal per-peer paths, no
# `{package}` template survives), so it reads identically in r2db-api's
# own copy of this file.
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
    ("tests/test_audit_query.py", "tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_198_rows"),
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
    # hand-written literal sets (`{6, 8} == {6, 8} == {6, 8}`) and executed
    # NONE of the scanner's own extraction logic (a vacuity finding, code
    # review round 1 + acceptance audit). `template_seed_numbers` is the
    # named helper the rework round's synthetic three-way-match test now
    # calls for real, alongside `_classify_migrations_dir`'s own
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
    # `ops.py` now carry. WP-1 (r2db-api) implements this same D-1/D-2
    # surface in a PARALLEL worktree not yet merged into this one at WP-2
    # authoring time -- `_isomorphic_symbol_source` reports the r2db-side
    # file as absent (not a content mismatch) until that merge lands; see
    # this WP's own completion report for the explicit acknowledgment
    # that the supervisor confirms green post-merge, not this WP.
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
    # here -- it calls this peer's own provision-DSN accessor (`_provision_
    # dsn` on this peer, `_control_dsn` on r2db-api), a real per-peer name
    # the isomorphism normalizer (package-name substitution only) does not
    # paper over.
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
    # R-45 WP-A (design D-2, supervisor ruling A-2, 2026-09-16): the
    # connection-parameter redaction helper both peers' own `_upgrade_
    # one_application`/`cmd_upgrade_applications` and `_run_deprovision_
    # script` now call before folding a psql failure's own stdout/stderr
    # (or a raw connection exception's own `str(exc)`) into output --
    # verified normalize-and-diff equal before adding.
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_redact_connection_values"),
    # R-45 WP-A 差し戻し 1 (supervisor ruling A-11, 2026-09-16): the psql
    # subprocess environment-builder helper, isomorphic with the redaction
    # helper immediately above (verified normalize-and-diff equal before
    # adding). `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY` (a module-level `dict`
    # constant, `ast.AnnAssign`) is deliberately NOT a row here --
    # `_isomorphic_symbol_source`'s own module-level matcher (below) only
    # resolves an `ast.FunctionDef`/`ast.AsyncFunctionDef`/`ast.ClassDef`
    # or a bare `ast.Assign` target, never an annotated assignment, so a
    # `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY` row would not resolve against its
    # own tree at all.
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_psql_connection_env"),
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
    # 追記 2026-09-16 (R-44 WP-3、D-4): `ADMIN_DSN_DEFAULT` はこの変更セットで
    # 削除された。上の経緯コメントは書き換えない。登録行のみここで消す。
    # 追記 2026-09-20 (R-56 WP-1): `MIGRATION_NAMES_WITHOUT_DECLARATIONS` の
    # 本体は `MIGRATION_NAMES[:-1]` 位置 slice から
    # `tuple(name for name in MIGRATION_NAMES if name not in
    # _MIGRATION_NAMES_DECLARATIONS_ONLY)` (名前選択) に両 peer 同時に直っ
    # た。上の経緯コメントは書き換えない。行 (シンボル名) はそのまま。
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
    # keeps each peer's own real construction path (r2db-api's plain
    # `DataService`, this peer's own `FoundationConfig`-fronted
    # `ApplicationCell`) and is not, and was never meant to be, isomorphic.
    # Phase 10 WP-6 pair-closing (design D-5 (ii), work order §4/WP-6a/
    # WP-6b): the `process_ceilings` declaration mechanism's own peer-
    # duplicated pure-Python pieces (`platform_declarations.py`'s
    # `ProcessCeilings` shape, its `validate_process_ceilings_value` shape
    # check, and the two F-15 message builders it calls), the region-(iii)
    # advisory-lock helper (`credential_store.py` on this peer, `control_
    # plane.py` on MitateDB-api -- same purpose, different module split,
    # same triple form the bearer-locator row above already uses), and
    # the HTTP conformance adapter's own `_build_client`/`_surfaces_value`/
    # `_reset_surface_state` hooks (WP-3) -- verified normalize-and-diff
    # equal (`_isomorphic_symbol_source` + `_normalize`, both sides)
    # before adding; MitateDB-api's own `_surfaces_value` body was
    # refactored to return a module-level `_SURFACES` constant (same
    # shape as this peer's own, no value change) so the two bodies match
    # after normalization rather than merely returning the same value.
    # `cmd_declare_process_ceilings` was NOT added: beyond the DSN-helper-
    # name difference (`_control_dsn` here, `_provision_dsn` on
    # MitateDB-api) that normalization does not fold away on its own, the
    # two bodies differ in statement order, exception handling shape (this
    # peer's context-managed `psycopg.connect`, MitateDB-api's explicit
    # try/except/finally with rollback), and the printed restart message
    # -- real structural differences, not addressed by this WP.
    ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "violation"),
    ("src/r2db_api/errors.py", "src/mitatedb_api/errors.py", "observed_type_of"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "ProcessCeilings"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_process_ceilings_value"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f15_shape_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f15_value_message"),
    ("src/r2db_api/credential_store.py", "src/mitatedb_api/control_plane.py", "_take_bound_advisory_lock"),
    ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_build_client"),
    ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_surfaces_value"),
    ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_reset_surface_state"),
    # Phase 10 WP-9a pair-closing commit (design docs/design/PHASE10_
    # DEPLOYMENT_EVIDENCE_V1.md D-1 (b), section 7; work order Class D):
    # (a) the C-26 composition-root launcher's own same-named helpers
    # (WP-6a/WP-6b's `RealServerR2db`/`RealServerMitateDB`, WP-6c's own
    # rework rounds) verified normalize-and-diff equal before adding --
    # `_control_env`'s own dict was reordered on this peer to match
    # MitateDB-api's own key order (behavior-unchanged: env-var
    # application never depends on dict insertion order) and `_normalize`
    # above widened, the SAME "both known spellings, symmetrically"
    # technique already used for `r2db_api`/`mitatedb_api` and
    # `ResourceLimits`/`FoundationConfig`, to also fold each peer's own
    # UPPERCASE env-var-name prefix (`R2DB_`/`MITATEDB_`). The launcher's
    # OWN composition/lifecycle methods (`__init__`, `_ensure_
    # provisioned`, `_app_env`, `start`, `restart`, `read_declared_
    # surfaces`, `attempt_start_without_process_ceilings`, `attempt_
    # start_with_lowered_role_limit`, `_Platform`, `_AppInfo`,
    # `_bootstrap_platform`, `_provision_app`, `_ops_env`) and the class
    # attribute `name` are deliberately NOT rows here: each carries a
    # real per-peer difference `_normalize` does not fold away (this
    # peer's `slug`-keyed application identity vs MitateDB-api's own
    # `application_id`, `control_dsn` vs `provision_dsn`, MitateDB-api's
    # own extra `_issue_runtime_credential` extraction and `shutil.
    # rmtree` cleanup, `name`'s own peer-specific literal value) -- same
    # category as the already-excluded `cmd_declare_process_ceilings`.
    # (b) F-16's own peer-duplicated pure-Python pieces (`platform_
    # declarations.py`'s `_table_owner`, `_roles_with_table_privilege`,
    # the three role-class/floor constants, and the `_f16_message`
    # builder) -- `_roles_with_table_privilege`'s return type hint
    # widened to `list[str]` on MitateDB-api (matching this peer, cosmetic
    # only) and `_f16_message`'s own trailing sentence on this peer
    # rewritten to the peer-generic wording every other `_fN_message`
    # builder already uses (dropping the `POSTGRES_PROVISIONING_RUNBOOK.
    # md` filename reference, not pinned by any existing test) before
    # adding. `check_role_connection_limits` itself is NOT a row: its own
    # `application_slugs`/`application_ids` parameter and the SQL column
    # name it filters by (`application_slug` vs `application_id`) are a
    # real per-peer application-identity difference threading through the
    # whole function body, the same category of gap that keeps
    # `_bootstrap_platform`/`_provision_app` above unpinned. (c) WP-8c's
    # own AST-scanning test helpers in `test_preauth_concurrency_bound.py`
    # (`_parse_handler`, `_authenticate_call_nodes`) -- the F-7 rework's
    # three same-NAMED `test_*` functions in that same file are NOT rows
    # here: verified normalize-and-diff UNEQUAL (each peer exercises a
    # different endpoint via a differently-shaped fixture, a real test
    # body difference, not a naming coincidence `_normalize` should paper
    # over). (d) WP-4e's `role_pool_size` (`limits.py`/`config.py`) was
    # checked and is NOT a row: its parameter name (`limits` vs `config`)
    # and the attribute it reads (`.concurrency` vs `.max_concurrency`)
    # both differ, and folding either away would require a site-wide
    # rename of a real dataclass field, beyond this WP's alignment scope.
    # (e) Phase 10 WP-7 (`tools/perf_baseline.py` and its own test file)
    # added no peer-duplicated helper at all -- both files are single,
    # peer-agnostic modules shared by both peers' conformance plugs, not
    # a same-named pair under `r2db-api/`/`MitateDB-api/` -- confirmed,
    # no row added for it.
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_with_pythonpath"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_scrub_peer_env_prefixes"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_peer_env_prefixes_removed_from_os_environ"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "LauncherStartupError"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_admin_dsn"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_dsn_with"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_lock_path"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_claim_prefix_lock"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_release_prefix_lock"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_run_psql"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_run_ops"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_sweep_prefix"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_sweep_stale"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_parse_issued_secret"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "startup_events"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_record"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_control_env"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_best_effort_stop_processes"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "stop"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "data_base_url"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "control_base_url"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "runtime_bearer"),
    ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "control_bearer"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_table_owner"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_roles_with_table_privilege"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_ROLE_CLASSES"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_API_ROLE_STORE_COUNT"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_CONTROLPLANE_ROLE_POOL_FLOOR"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_AUDITREADER_ROLE_POOL_FLOOR"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f16_message"),
    # R-56 WP-2 review (差し戻し 2, 2026-09-20): F-17's own peer-duplicated
    # pieces -- `_f17_message` and `check_auditreader_statement_timeout`
    # itself. Unlike `check_role_connection_limits` (excluded above: real
    # per-peer parameter/column differences thread through its whole
    # body), `check_auditreader_statement_timeout` carries no
    # peer-specific literal on either peer (its leading docstring is
    # dropped before comparison, `_strip_leading_docstring`) -- verified
    # normalize-and-diff equal before adding both rows.
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f17_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_auditreader_statement_timeout"),
    ("tests/test_preauth_concurrency_bound.py", "tests/test_preauth_concurrency_bound.py", "_parse_handler"),
    ("tests/test_preauth_concurrency_bound.py", "tests/test_preauth_concurrency_bound.py", "_authenticate_call_nodes"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_LOCK_TIMEOUT_VALUE_RE"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_validate_lock_timeout_value"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_with_lock_timeout_option"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_resolve_platform_migration_file"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_validate_platform_migration_run"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_platform_migration_variables"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_deprovision_confirmation_phrase"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_PSQL_VARIABLE_RE"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_strip_sql_line_comments"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_extract_psql_variables"),
    # R-91 (work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_
    # HEADROOM_CHECK_V1.md §2.2 completion condition 12): the declared
    # process_ceilings' own connection-headroom check -- none of the three
    # takes a peer-specific argument, verified normalize-and-diff equal
    # before adding all six rows.
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "headroom_lower_bound"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_max_connections_headroom"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f18_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_count_registered_applications"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_read_connection_headroom_settings"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "HeadroomReport"),
    ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "encode_page_cursor"),
    ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "decode_page_cursor"),
    ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "canonical_page_binding"),
    # R-101 WP-1: the `DSA_PERF_THREAD_LIMIT` env reader and the
    # `perf_thread_limit()` accessor the measurement harness reads it
    # back through, verified normalize-and-diff equal before adding (a
    # peer-specific comment naming r2db-api's own unrelated `_PERF_POOL_
    # SIZE_ENV` constant was reworded to a generic sentence so both
    # copies stay byte-identical). `platform_db_time_stats()` is NOT a
    # row: its body differs structurally between peers (r2db-api sums two
    # `_RolePool.platform_stats()` calls, this peer sums its own `_read_
    # pool`'s `platform_stats()` and `_application_durable_audit`'s
    # `platform_stats()`), the same carve-out already applied to `pool_
    # stats()` elsewhere in this table.
    ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_perf_thread_limit_value"),
    ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "perf_thread_limit"),
    # R-101 WP-3 (D-8/D-9/D-10): the production thread-limit middleware
    # and its default constant (`http.py`), and the composition root's
    # own strict env parser (`main.py`) -- `_PerfThreadLimitWrapper`
    # (WP-1's harness-only wrapper) is removed from this table: `create_
    # app`'s own middleware replaces it, so both adapters now pass an
    # already-resolved `thread_limit=` int through instead of wrapping
    # the app themselves.
    ("src/r2db_api/http.py", "src/mitatedb_api/http.py", "ThreadLimitMiddleware"),
    ("src/r2db_api/http.py", "src/mitatedb_api/http.py", "DEFAULT_THREAD_LIMIT"),
    ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_thread_limit_from_env"),
    # R-101 WP-1 completion condition 26 (supervisor ruling 3): the AST
    # static pin's own three helpers (`_self_attr`, `_find_with_lock_body`,
    # `_body_contains`) placed identically in both peers' own `tests/
    # test_r79_prepared_stats.py`, per OC §1.5 の 38.
    ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_self_attr"),
    ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_find_with_lock_body"),
    ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_body_contains"),
    # R-112 D-2/訂正註1: the new application-collation check (F-19) and
    # its own message builder -- neither carries a peer-specific literal
    # (both peers' `applications` table is read by `database_name` only,
    # never the differently-spelled slug/id column), verified
    # normalize-and-diff equal before adding both rows.
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f19_message"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_application_collations"),
    # The multi-process worker helpers (design docs/design/MULTI_PROCESS_
    # WORKER_V0_1.md D-1/D-3/D-4): `concurrency_slots.py`'s own 16
    # symbols (the host-shared `concurrency` slot directory, its `scan`
    # lock, and the interval-bounded writer of its failure line),
    # `resolve_limit_enforcement` (the 2-strategy `limit_enforcement`
    # mapping), the thread-limit pool sizing trio (`limits.py` on r2db-api,
    # `config.py` on MitateDB-api), both composition roots' own
    # `_workers_from_env`/`_require_slot_dir`/`_run_lifespan_once` (both
    # peers' `main.py`, and `_workers_from_env`/`_run_lifespan_once` in
    # both peers' `control_main.py`), the
    # `application_name` toggle pair (`postgres.py` / `pool.py`),
    # `ops._declared_pool_size` (the pool dimension `verify-declarations`
    # checks F-16/F-18 against) and `platform_declarations.check_request_
    # rate_function` (the startup check of the rate function) -- each
    # verified normalize-and-diff equal before adding. `record_rate_and_
    # check` keeps a peer-IDENTICAL name and a peer-SPECIFIC body (each
    # store's own borrow and error mapping) and is NOT added.
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SELFCHECK_FILENAME"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SCAN_FILENAME"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_SCAN_LOCK_TIMEOUT_S"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_SCAN_LOCK_INTERVAL_S"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_FAILURE_LOG_INTERVAL_S"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_OPEN_FLAGS"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_FILE_MODE"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_HELD_ERRNOS"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SlotDirectoryError"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "LimitExceeded"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SlotBackendError"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "BackendFailureLog"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "check_slot_directory"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "selfcheck_slot_locking"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_slot_path"),
    ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "HostSharedConcurrencySlots"),
    ("src/r2db_api/capabilities_document.py", "src/mitatedb_api/capabilities_document.py", "resolve_limit_enforcement"),
    ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "_POOL_SIZE_HEADROOM"),
    ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "thread_limit_from_env"),
    ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "role_pool_size"),
    ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_workers_from_env"),
    ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_require_slot_dir"),
    ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_run_lifespan_once"),
    ("src/r2db_api/control_main.py", "src/mitatedb_api/control_main.py", "_run_lifespan_once"),
    ("src/r2db_api/control_main.py", "src/mitatedb_api/control_main.py", "_workers_from_env"),
    ("src/r2db_api/postgres.py", "src/mitatedb_api/pool.py", "set_connection_application_name"),
    ("src/r2db_api/postgres.py", "src/mitatedb_api/pool.py", "_application_name_connect_kwargs"),
    ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_declared_pool_size"),
    ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_request_rate_function"),
)


def test_isomorphic_target_table_is_pinned_to_its_current_198_rows() -> None:
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
    `observed_type_of` had both merged to main (this peer's own copy also
    gained `platform_declarations.check_contract_170_declarations`/`ops_
    module_hint`, already rows on r2db-api's own copy of this table);
    widened a tenth time by the phase 10 WP-6 pair-closing commit (design
    D-5 (ii), work order §4/WP-6a/WP-6b), once WP-6a and WP-6b's own
    same-named `process_ceilings` declaration mechanism (`ProcessCeilings`,
    `validate_process_ceilings_value`, `_f15_shape_message`, `_f15_value_
    message`, `_take_bound_advisory_lock`) and WP-3's own same-named HTTP
    conformance adapter hooks (`_build_client`, `_surfaces_value`,
    `_reset_surface_state`) had all merged to main on both peers; widened
    an eleventh time by the phase 10 WP-9a pair-closing commit (design
    docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (b)/§7, work order
    Class D), registering the C-26 launcher's own same-named helpers
    (WP-6a/WP-6b/WP-6c), F-16's own peer-duplicated pure-Python pieces
    (WP-4f/WP-4g), and WP-8c's own `_parse_handler`/`_authenticate_call_
    nodes` AST-scanning test helpers (WP-8c's own F-7 rework) all at once,
    each verified normalize-and-diff equal before adding -- see this
    table's own comment immediately above the new rows for the candidates
    checked and deliberately NOT added; widened a twelfth time by R-45
    WP-A (design D-2, supervisor ruling A-2, 2026-09-16), once the
    connection-parameter redaction helper (`_redact_connection_values`)
    landed identically on both peers, verified normalize-and-diff equal
    before adding; widened a thirteenth time by the R-45 WP-A 差し戻し 1
    round (supervisor ruling A-11), once the psql-subprocess environment
    builder (`_psql_connection_env`) was found isomorphic too (its own
    module-level allow-list constant, `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY`,
    is an annotated assignment this table's own matcher cannot resolve,
    so it stays unregistered -- see the comment beside its own row);
    widened a fourteenth time once the cursor codec (`encode_page_cursor`/
    `decode_page_cursor`) and the binding-hash helper
    (`canonical_page_binding`) had landed identically on both peers,
    verified normalize-and-diff equal before adding; widened a
    fifteenth time (R-112 D-2/訂正註1) once the application-collation
    check (`check_application_collations`) and its own message builder
    (`_f19_message`) had landed identically on both peers, neither
    reading either peer's own differently-spelled `applications` slug/id
    column, verified normalize-and-diff equal before adding;
    widened a sixteenth
    time by R-101 WP-1, once the `DSA_PERF_THREAD_LIMIT` env reader
    (`_perf_thread_limit_value`), the wrapper class that applies it to a
    data-plane app's own event loop (`_PerfThreadLimitWrapper`), the
    `perf_thread_limit()` accessor the measurement harness reads it back
    through, and the closed-connection-fold static pin's own three
    helpers (`_self_attr`, `_find_with_lock_body`, `_body_contains`,
    `tests/test_r79_prepared_stats.py` on both peers) had all landed
    identically on both peers, verified normalize-and-diff equal before
    adding:
    a bare `len(_ISOMORPHIC_TARGETS) == 57` check would not
    catch a row silently DROPPED and a different, coincidentally-same-
    length row added in its place -- only pinning the table's own full
    CONTENT (not merely its length) catches that. One-time human
    fixation, same character as Phase 5's "走査対象フィールド集合を pin
    する" test -- a future WP that adds/removes a row edits this
    assertion deliberately, not by accident.
    Widened a seventeenth time by R-101 WP-3 (D-8/D-9/D-10): `_PerfThread
    LimitWrapper` (WP-1's own harness-only wrapper) is REMOVED -- `create
    _app`'s own production middleware (`ThreadLimitMiddleware`, its
    default `DEFAULT_THREAD_LIMIT`) and the composition root's strict env
    parser (`_thread_limit_from_env`) replace it, all three verified
    normalize-and-diff equal before adding; `_perf_thread_limit_value`
    and `perf_thread_limit` keep their own rows, unchanged in name.
    The last 29 rows are the multi-process worker helpers named in the
    comment right above them in `_ISOMORPHIC_TARGETS`, each verified
    normalize-and-diff equal before adding.

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
        ("tests/test_audit_query.py", "tests/test_audit_query.py", "test_isomorphic_target_table_is_pinned_to_its_current_198_rows"),
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
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_redact_connection_values"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_psql_connection_env"),
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
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "ProcessCeilings"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "validate_process_ceilings_value"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f15_shape_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f15_value_message"),
        ("src/r2db_api/credential_store.py", "src/mitatedb_api/control_plane.py", "_take_bound_advisory_lock"),
        ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_build_client"),
        ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_surfaces_value"),
        ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_reset_surface_state"),
        # Phase 10 WP-9a pair-closing commit (design docs/design/PHASE10_
        # DEPLOYMENT_EVIDENCE_V1.md D-1 (b), section 7; work order Class D):
        # (a) the C-26 composition-root launcher's own same-named helpers
        # (WP-6a/WP-6b's `RealServerR2db`/`RealServerMitateDB`, WP-6c's own
        # rework rounds) verified normalize-and-diff equal before adding --
        # `_control_env`'s own dict was reordered on this peer to match
        # MitateDB-api's own key order (behavior-unchanged: env-var
        # application never depends on dict insertion order) and `_normalize`
        # above widened, the SAME "both known spellings, symmetrically"
        # technique already used for `r2db_api`/`mitatedb_api` and
        # `ResourceLimits`/`FoundationConfig`, to also fold each peer's own
        # UPPERCASE env-var-name prefix (`R2DB_`/`MITATEDB_`). The launcher's
        # OWN composition/lifecycle methods (`__init__`, `_ensure_
        # provisioned`, `_app_env`, `start`, `restart`, `read_declared_
        # surfaces`, `attempt_start_without_process_ceilings`, `attempt_
        # start_with_lowered_role_limit`, `_Platform`, `_AppInfo`,
        # `_bootstrap_platform`, `_provision_app`, `_ops_env`) and the class
        # attribute `name` are deliberately NOT rows here: each carries a
        # real per-peer difference `_normalize` does not fold away (this
        # peer's `slug`-keyed application identity vs MitateDB-api's own
        # `application_id`, `control_dsn` vs `provision_dsn`, MitateDB-api's
        # own extra `_issue_runtime_credential` extraction and `shutil.
        # rmtree` cleanup, `name`'s own peer-specific literal value) -- same
        # category as the already-excluded `cmd_declare_process_ceilings`.
        # (b) F-16's own peer-duplicated pure-Python pieces (`platform_
        # declarations.py`'s `_table_owner`, `_roles_with_table_privilege`,
        # the three role-class/floor constants, and the `_f16_message`
        # builder) -- `_roles_with_table_privilege`'s return type hint
        # widened to `list[str]` on MitateDB-api (matching this peer, cosmetic
        # only) and `_f16_message`'s own trailing sentence on this peer
        # rewritten to the peer-generic wording every other `_fN_message`
        # builder already uses (dropping the `POSTGRES_PROVISIONING_RUNBOOK.
        # md` filename reference, not pinned by any existing test) before
        # adding. `check_role_connection_limits` itself is NOT a row: its own
        # `application_slugs`/`application_ids` parameter and the SQL column
        # name it filters by (`application_slug` vs `application_id`) are a
        # real per-peer application-identity difference threading through the
        # whole function body, the same category of gap that keeps
        # `_bootstrap_platform`/`_provision_app` above unpinned. (c) WP-8c's
        # own AST-scanning test helpers in `test_preauth_concurrency_bound.py`
        # (`_parse_handler`, `_authenticate_call_nodes`) -- the F-7 rework's
        # three same-NAMED `test_*` functions in that same file are NOT rows
        # here: verified normalize-and-diff UNEQUAL (each peer exercises a
        # different endpoint via a differently-shaped fixture, a real test
        # body difference, not a naming coincidence `_normalize` should paper
        # over). (d) WP-4e's `role_pool_size` (`limits.py`/`config.py`) was
        # checked and is NOT a row: its parameter name (`limits` vs `config`)
        # and the attribute it reads (`.concurrency` vs `.max_concurrency`)
        # both differ, and folding either away would require a site-wide
        # rename of a real dataclass field, beyond this WP's alignment scope.
        # (e) Phase 10 WP-7 (`tools/perf_baseline.py` and its own test file)
        # added no peer-duplicated helper at all -- both files are single,
        # peer-agnostic modules shared by both peers' conformance plugs, not
        # a same-named pair under `r2db-api/`/`MitateDB-api/` -- confirmed,
        # no row added for it.
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_with_pythonpath"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_scrub_peer_env_prefixes"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_peer_env_prefixes_removed_from_os_environ"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "LauncherStartupError"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_admin_dsn"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_dsn_with"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_lock_path"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_claim_prefix_lock"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_release_prefix_lock"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_run_psql"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_run_ops"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_sweep_prefix"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_sweep_stale"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_parse_issued_secret"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "startup_events"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_record"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_control_env"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_best_effort_stop_processes"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "stop"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "data_base_url"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "control_base_url"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "runtime_bearer"),
        ("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "control_bearer"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_table_owner"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_roles_with_table_privilege"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_ROLE_CLASSES"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_API_ROLE_STORE_COUNT"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_CONTROLPLANE_ROLE_POOL_FLOOR"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_AUDITREADER_ROLE_POOL_FLOOR"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f16_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f17_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_auditreader_statement_timeout"),
        ("tests/test_preauth_concurrency_bound.py", "tests/test_preauth_concurrency_bound.py", "_parse_handler"),
        ("tests/test_preauth_concurrency_bound.py", "tests/test_preauth_concurrency_bound.py", "_authenticate_call_nodes"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_LOCK_TIMEOUT_VALUE_RE"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_validate_lock_timeout_value"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_with_lock_timeout_option"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_resolve_platform_migration_file"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_validate_platform_migration_run"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_platform_migration_variables"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_deprovision_confirmation_phrase"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_PSQL_VARIABLE_RE"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_strip_sql_line_comments"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_extract_psql_variables"),
        # R-91 (work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_
        # HEADROOM_CHECK_V1.md §2.2 completion condition 12): the declared
        # process_ceilings' own connection-headroom check -- none of the
        # three takes a peer-specific argument, verified normalize-and-diff
        # equal before adding all six rows.
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "headroom_lower_bound"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_max_connections_headroom"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f18_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_count_registered_applications"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_read_connection_headroom_settings"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "HeadroomReport"),
        ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "encode_page_cursor"),
        ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "decode_page_cursor"),
        ("src/r2db_api/paging.py", "src/mitatedb_api/paging.py", "canonical_page_binding"),
        ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "_perf_thread_limit_value"),
        ("conformance/conformance_adapter_r2db_http.py", "conformance/conformance_adapter_mitatedb_http.py", "perf_thread_limit"),
        ("src/r2db_api/http.py", "src/mitatedb_api/http.py", "ThreadLimitMiddleware"),
        ("src/r2db_api/http.py", "src/mitatedb_api/http.py", "DEFAULT_THREAD_LIMIT"),
        ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_thread_limit_from_env"),
        # R-101 WP-1 completion condition 26 (supervisor ruling 3): the AST
        # static pin's own three helpers (`_self_attr`, `_find_with_lock_body`,
        # `_body_contains`) placed identically in both peers' own `tests/
        # test_r79_prepared_stats.py`, per OC §1.5 の 38.
        ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_self_attr"),
        ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_find_with_lock_body"),
        ("tests/test_r79_prepared_stats.py", "tests/test_r79_prepared_stats.py", "_body_contains"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "_f19_message"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_application_collations"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SELFCHECK_FILENAME"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SCAN_FILENAME"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_SCAN_LOCK_TIMEOUT_S"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_SCAN_LOCK_INTERVAL_S"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_FAILURE_LOG_INTERVAL_S"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_OPEN_FLAGS"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_FILE_MODE"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_HELD_ERRNOS"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SlotDirectoryError"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "LimitExceeded"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "SlotBackendError"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "BackendFailureLog"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "check_slot_directory"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "selfcheck_slot_locking"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "_slot_path"),
        ("src/r2db_api/concurrency_slots.py", "src/mitatedb_api/concurrency_slots.py", "HostSharedConcurrencySlots"),
        ("src/r2db_api/capabilities_document.py", "src/mitatedb_api/capabilities_document.py", "resolve_limit_enforcement"),
        ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "_POOL_SIZE_HEADROOM"),
        ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "thread_limit_from_env"),
        ("src/r2db_api/limits.py", "src/mitatedb_api/config.py", "role_pool_size"),
        ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_workers_from_env"),
        ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_require_slot_dir"),
        ("src/r2db_api/main.py", "src/mitatedb_api/main.py", "_run_lifespan_once"),
        ("src/r2db_api/control_main.py", "src/mitatedb_api/control_main.py", "_run_lifespan_once"),
        ("src/r2db_api/control_main.py", "src/mitatedb_api/control_main.py", "_workers_from_env"),
        ("src/r2db_api/postgres.py", "src/mitatedb_api/pool.py", "set_connection_application_name"),
        ("src/r2db_api/postgres.py", "src/mitatedb_api/pool.py", "_application_name_connect_kwargs"),
        ("src/r2db_api/ops.py", "src/mitatedb_api/ops.py", "_declared_pool_size"),
        ("src/r2db_api/platform_declarations.py", "src/mitatedb_api/platform_declarations.py", "check_request_rate_function"),
    )
    assert len(_ISOMORPHIC_TARGETS) == 198


_ISOMORPHIC_PARSE_CACHE: dict[Path, tuple[str, _ast.Module]] = {}


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
    which class each peer happens to name it under.

    R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-5): caches
    the `read_text` + `ast.parse` pair in `_ISOMORPHIC_PARSE_CACHE`, keyed
    by the resolved ABSOLUTE path (`peer_root / relative_path`), never by
    `relative_path` alone -- the same relative path resolves to a
    DIFFERENT file depending on which side's `peer_root` it is joined
    against, so a relative-path-only key would return one side's own tree
    for the other side's lookup too, silently comparing a peer against
    ITSELF and turning every diff in this module permanently green (the
    isomorphism check's own worst failure mode). One entry serves every
    `_ISOMORPHIC_TARGETS` row that shares a path, on either side, across
    every call this test module makes -- `test_peer_local_helpers_are_
    isomorphic_to_the_sibling_peer` alone re-parses each of the 156 rows'
    files four times (self/sibling x two directions) without this cache."""
    path = peer_root / relative_path
    if not path.exists():
        return None
    cached = _ISOMORPHIC_PARSE_CACHE.get(path)
    if cached is None:
        source = path.read_text()
        tree = _ast.parse(source, filename=str(path))
        _ISOMORPHIC_PARSE_CACHE[path] = (source, tree)
    else:
        source, tree = cached
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
    names itself "this peer's own X", the other "r2db-api's own X";
    see e.g. `compose_bearer_locator`'s two docstrings). Located via
    `ast` (the docstring statement's own `lineno`/`end_lineno` against
    THIS already-extracted, syntactically self-contained segment),
    then deleted as TEXT -- never `ast.unparse`, which would also
    reformat everything else the docstring did not touch (quote
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
    pinned_to_its_current_66_rows` literally asserts that whole table
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
    # dataclass names (`FoundationConfig` here, `ResourceLimits` on
    # r2db-api) -- `narrow_limits_by_budget`'s own pinned signature names
    # its `deployed`/return type as this peer's own class, the sibling's
    # row names ITS own class, and neither name is peer-name-free the way
    # every pre-existing pinned symbol's signature happened to be.
    text = text.replace("ResourceLimits", "<PEER_TYPE>").replace("FoundationConfig", "<PEER_TYPE>")
    # Phase 10 WP-9a pair-closing commit: the same "both known spellings,
    # symmetrically, on either side" technique the package-name line above
    # already uses, extended to the two peers' own UPPERCASE env-var name
    # prefixes (`MITATEDB_` here, `R2DB_` on r2db-api) -- the C-26
    # composition-root launcher's own `_control_env` builds a dict of real
    # environment variable names each peer's own `control_main.py`/
    # `control_composition.py` reads at process startup, and those names
    # necessarily carry the peer's own package name as an UPPERCASE
    # prefix, a spelling the lowercase `r2db_api`/`mitatedb_api`
    # substitution above never touches.
    text = text.replace("R2DB_", "<PEER_ENV_PREFIX>").replace("MITATEDB_", "<PEER_ENV_PREFIX>")
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
    against r2db-api's own same-named symbols at each row's own r2db-side
    relative path, after normalizing peer package name / the symbol's own
    leading docstring / trailing whitespace / blank-line runs -- proving
    the two independently (never shared-module) implementations agree,
    without sharing code between peers.

    Table-driven generalization of the WP-2/WP-3 mechanism (design D-4(c),
    L5-5/L5-6): the prior form read one hardcoded sibling file
    (`tests/test_audit_query.py`) and diffed 11 named helpers found inside
    it; `_ISOMORPHIC_TARGETS` above widens that to 57 rows spanning NINE
    files per side (measured, not asserted ahead of counting -- a plain
    `ast`-driven `len()` + unique-path count against the table actually
    defined above: `tests/test_audit_query.py`,
    `src/<package>/main.py`, `tests/test_http.py`, the bearer-locator
    module (`credential_wire.py` on this peer, `auth.py` on r2db-api,
    Phase 6 WP-3 追補), `tests/test_control_plane_store.py`, `src/
    <package>/pg_timeouts.py` and `tests/
    test_platform_upgrade_ledger_scan.py` (Q4 phase WP-0; WP-0 最終追補,
    supervisor ruling 2026-09-05, 裁定 4: three more rows in this SAME
    already-counted file -- the two pinned scanner functions' own peer-duplicated
    sub-helpers -- so the file count stayed SEVEN there, only the row
    count grew; Q4 phase WP-2 (monitor ruling 2026-09-05, 裁定 5) adds two
    MORE files -- `src/<package>/platform_declarations.py` (D-1/D-2's new
    read/validate/derive helpers) and `src/<package>/ops.py` (the
    declaration-write helper) -- bringing the file count to NINE), so each
    WP's own new same-named symbols fall under the SAME peer-symmetry
    guarantee a product file (not just a test-support helper) would
    otherwise have had none of. (常設規律 3 / acceptance-
    audit finding: an earlier draft of this docstring claimed "18 rows
    spanning FOUR files" -- already inaccurate for the 18-row table that
    predates Q4 WP-0, which in fact spanned FIVE files, `tests/
    test_control_plane_store.py` having been omitted from the count --
    and was never caught by either the isomorphism check itself, which
    normalizes docstrings out before comparing, or the row-count pin test
    above, which pins the table's
    DATA, not this prose describing it.)

    Q4 phase WP-3/WP-4 (monitor ruling 2026-09-05, design docs/design/
    Q4_DB_SIDE_SINGLE_TRUTH_V1.md §5 U-1 / U-2, §3.8 F-12) widens the
    table again, to 66 rows spanning a TENTH file per side --
    `src/<package>/platform_upgrades.py`
    (the per-application platform-upgrade ledger's cell-open-time set
    difference, F-12 message, and `ops upgrade-applications` result/
    summary shapes, design D-3(f)/D-4/D-5). WP-4 adds this pair's rows for
    both WPs in the same commit (work order §3), consistent with the
    established "later half of the pair" convention above.

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
    self_root = Path(__file__).resolve().parents[1]
    sibling_root = Path(__file__).resolve().parents[2] / "r2db-api"
    assert "r2db-api" in sibling_root.parts, f"sibling root must resolve under r2db-api, not self: {sibling_root}"
    assert "MitateDB-api" not in sibling_root.parts, f"sibling root must never resolve back into MitateDB-api: {sibling_root}"

    mismatches: list[str] = []
    for sibling_relative_path, self_relative_path, symbol in _ISOMORPHIC_TARGETS:
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


def test_isomorphic_symbol_source_cache_key_is_the_resolved_absolute_path() -> None:
    """R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-5):
    guards `_ISOMORPHIC_PARSE_CACHE`'s own key choice -- a relative-path-
    only key would collapse the self-side and sibling-side lookups below
    onto the SAME cache entry (whichever side's `peer_root` is resolved
    first "wins" for every later call, on either side), silently turning
    this whole module's isomorphism check into a comparison of a peer
    against ITSELF (the mechanism's own worst failure mode, see this
    file's own `_isomorphic_symbol_source` docstring). `_postgres_
    harness` is used, at THIS file's own relative path (`tests/test_
    audit_query.py`) -- THE SAME STRING on both sides -- because it is
    module-level (matched by the same node-matcher `_ISOMORPHIC_TARGETS`
    rows use), it is NOT itself an `_ISOMORPHIC_TARGETS` row (its two
    peer bodies are not asserted equal anywhere, unlike `_isomorphic_
    symbol_source` itself -- R-105 made that ONE symbol's body byte-
    identical between the two peers on purpose, so it cannot be used
    here: a same-relative-path row whose real content happens to already
    be equal on both sides could pass this assertion even with a broken,
    relative-path-only cache key, for the wrong reason), and its two
    peer bodies genuinely differ (each peer's own writer-timeout harness
    talks to a differently-shaped backend). So a broken (relative-path-
    only) cache key would collide the two lookups below and silently
    return the same cached tree for both, making the assertion below
    pass for the wrong reason; a genuinely path-keyed cache returns two
    different trees, and the two reads below differ. A path that differs
    textually between the two sides (a `src/` row) would not catch a
    broken key at all -- there would be no collision to observe (design
    D-5's own note on this)."""
    self_root = Path(__file__).resolve().parents[1]
    sibling_root = Path(__file__).resolve().parents[2] / "r2db-api"
    self_src = _isomorphic_symbol_source(self_root, "tests/test_audit_query.py", "_postgres_harness")
    sibling_src = _isomorphic_symbol_source(sibling_root, "tests/test_audit_query.py", "_postgres_harness")
    assert self_src is not None
    assert sibling_src is not None
    assert self_src != sibling_src


def test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts(control_platform) -> None:
    h = _postgres_harness(control_platform, audit_statement_timeout_ms=3_000, audit_idle_timeout_ms=4_000)
    try:
        document = h.service.control_capabilities(h.control_credential_secret)
        assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 3_000 + 4_000 + 1_000
    finally:
        _cleanup_postgres(control_platform)


def test_in_memory_visibility_lag_ms_is_zero_by_construction() -> None:
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_secret)
    assert document["capabilities"]["audit_query"]["visibility_lag_ms"] == 0


def test_declared_coalescing_window_ms_matches_the_single_source_constant() -> None:
    """WP-3(b) (r2db-api WP-2(b) review item H, avoided from the start):
    the declared value is derived from `application_audit.DEFAULT_DENIAL_
    COALESCE_WINDOW_S` -- the SAME constant `audit_dispatch.AuditRouter`'s
    own default falls back to -- via `audit_query.DEFAULT_COALESCING_
    WINDOW_MS`, never a second, independently-maintained literal."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_secret)
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
    result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
    matched = [e for e in result["events"] if e.get("request_id") == "countnone"]
    assert len(matched) == 1
    assert "count" not in matched[0]


def test_forbidden_fields_never_appear_as_keys_or_reusable_secret_values() -> None:
    """SI-10. `_shape_audit_query_row` is a whitelist-construction function
    -- structurally cannot emit `credential`/`token`/`password`/`secret`/
    `private_key`/`sql`/`row_value` as keys."""
    h = _memory_harness()
    _write_application_audit_row(h, request_id="forbiddenprobe")
    result = h.service.audit_query(h.control_credential_secret, {"limit": 1000})
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

    result = h.service.audit_query(h.control_credential_secret, {})
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
    h.service.audit_query(h.control_credential_secret, {"limit": 1})
    h.service.audit_query(h.control_credential_secret, {"limit": 1})
    with pytest.raises(ResourceLimitError) as excinfo:
        h.service.audit_query(h.control_credential_secret, {"limit": 1})
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
        h.service.audit_query(h.control_credential_secret, {"limit": 1})
    successful = 0
    exceeded = False
    for _ in range(_TIGHT_CONTROL_WINDOW.control_requests_per_minute + 5):
        try:
            h.service.control_capabilities(h.control_credential_secret)
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
    document = h.service.control_capabilities(h.control_credential_secret)
    assert document["limits"]["audit_requests_per_minute"] == _GENEROUS_LIMITS.audit_requests_per_minute
    assert document["limit_enforcement"]["audit_requests_per_minute"] == "enforced"


# ---------------------------------------------------------------------------
# contract_version 1.4.0
# ---------------------------------------------------------------------------


def test_control_capabilities_declares_contract_version_1_5_0() -> None:
    """Phase 5 WP-3 (design D-4/§8, subordinate ruling 10): re-flipped to
    1.5.0 in the same commit as the `operations`/`target_kinds`
    declaration keys (flip and behavior land together, never separately).

    Phase 10 WP-6b/pair-closing (design D-5 (v)): re-flipped again to
    1.8.0 in the same commit as this host's own `process_ceilings`
    mapping -- function name kept, same precedent as the sibling peer's
    own re-flipped pins."""
    h = _memory_harness()
    document = h.service.control_capabilities(h.control_credential_secret)
    assert document["contract_version"] == "1.11.0"


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
        headers = _bearer_auth(h.control_credential_secret)
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
    headers = _bearer_auth(h.control_credential_secret)
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
