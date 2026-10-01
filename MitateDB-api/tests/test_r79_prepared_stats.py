"""R-79 (docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md
§2, WP-1; rework 2026-09-23): `mitatedb_api.psycopg_counting`
(`CountingCursor`/`CountingConnection`, `probe_prepared_statements`, D-1)
and this peer's own `PostgresBackend.prepared_stats`/`cell.py::Application
Cell.prepared_stats` (D-2), tested against a REAL PostgreSQL server where
a completion condition names one (5, 6) -- never a stand-in counter or a
source-text proxy (work order §1.5 の 52). The probe itself (`probe_
prepared_statements`) now lives in `psycopg_counting.py`, shared with
r2db-api (rework 指摘 3) -- this file exercises it only
through `PostgresBackend.prepared_stats`, this peer's own caller.

Each real-PostgreSQL test connects directly to `MITATEDB_TEST_ADMIN_DSN`
(set by `tools/testpg/dsa_testpg.py` for the whole run, same admin DSN
`tests/test_postgres.py` uses) -- no per-application database/role
provisioning: `PostgresBackend`/`BoundedConnectionPool` are constructed
directly against the admin connection's own database, since none of what
this WP added reads or writes application data.

`ApplicationCell.prepared_stats`'s own delegation (completion
conditions 9, 17) is tested with a FAKE backend (a plain object carrying
only the attribute under test) -- the property under test does not depend
on the backend being a real PostgreSQL connection.

Never reads psycopg's own private `_prepared`/`_counts`/`_names` attributes
anywhere in this file (work order §1.1 (e))."""
from __future__ import annotations

import ast
import inspect
import os
import secrets
import textwrap
import threading
import time

import psycopg
import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from mitatedb_api.application_audit import PostgresApplicationAuditSink
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import AuthorizationStateUnavailable
from mitatedb_api.pool import BoundedConnectionPool
from mitatedb_api.psycopg_counting import CountingConnection, probe_prepared_statements

ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


# ---------------------------------------------------------------------
# D-1: CountingConnection wiring (completion conditions 5, 6)
# ---------------------------------------------------------------------


def test_postgres_backend_runtime_and_developer_are_counting_connections():
    """Completion condition 5: the connections `PostgresBackend`'s two
    role pools (`_runtime_pool`/`_developer_pool`) hand out are actual
    `CountingConnection` instances, observed by the connection's own TYPE
    against a real PostgreSQL server (not source text, §1.5 の 52)."""
    backend = PostgresBackend(_admin_dsn(), _admin_dsn())
    try:
        for pool in (backend._runtime_pool, backend._developer_pool):
            conn = pool.acquire()
            try:
                assert isinstance(conn, CountingConnection)
            finally:
                pool.release(conn)
    finally:
        backend.close()


def test_bounded_connection_pool_new_connection_returns_counting_connection():
    """Completion condition 6: `BoundedConnectionPool._new_connection`
    (reached through `acquire()`) returns an actual `CountingConnection`,
    observed from a connection the pool itself handed out.

    mutation M6 (`mitatedb_api/pool.py`): change `_new_connection` back to
    a bare `psycopg.connect(...)` -- this test's own `isinstance(conn,
    CountingConnection)` assertion goes red."""
    pool = BoundedConnectionPool(_admin_dsn(), max_size=1)
    conn = pool.acquire()
    try:
        assert isinstance(conn, CountingConnection)
    finally:
        pool.release(conn)


# ---------------------------------------------------------------------
# D-2: ApplicationCell.prepared_stats delegation (completion conditions
# 9, 17) -- a fake backend is enough; the property under test is the
# cell's own delegation, not the backend's own connections.
# ---------------------------------------------------------------------


class _FakeBackend:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def prepared_stats(self):
        self.calls += 1
        return self._rows


def test_application_cell_prepared_stats_delegates_to_the_backend():
    """Completion condition 9 (起草時の裁定 4): `ApplicationCell.
    prepared_stats()` delegates to `self._backend.prepared_stats()` and
    returns `[]` when the backend has no such method (`SQLiteBackend`, and
    any other non-PostgreSQL backend) -- checked here by an equally-shaped
    fake `SQLiteBackend`-like object with no `prepared_stats` attribute at
    all."""
    fake_rows = [{"label": "runtime@1", "prepared": 0}]
    backend = _FakeBackend(fake_rows)
    cell = ApplicationCell("r79app", backend=backend)

    result = cell.prepared_stats()

    assert result == fake_rows
    assert backend.calls == 1

    class _NoProbeBackend:
        pass

    cell_without_probe = ApplicationCell("r79app2", backend=_NoProbeBackend())
    assert cell_without_probe.prepared_stats() == []


def test_application_cell_prepared_stats_probes_once_per_call():
    """Completion condition 17 (design review 1 H-3): calling `Application
    Cell.prepared_stats()` N times makes EXACTLY N backend probes -- one
    per call, never more, never fewer."""
    backend = _FakeBackend([])
    cell = ApplicationCell("r79app3", backend=backend)

    for _ in range(3):
        cell.prepared_stats()

    assert backend.calls == 3


# ---------------------------------------------------------------------
# rework item (A): PostgresBackend.prepared_stats() observed
# directly against a real PostgreSQL server
# ---------------------------------------------------------------------


def test_postgres_backend_prepared_stats_labels_runtime_and_developer_by_pid():
    """Rework item (A): `PostgresBackend.prepared_stats()`
    returns exactly 2 rows, labelled `runtime@<pid>`/`developer@<pid>`
    with the pid matching that connection's own `conn.info.backend_pid`,
    and the two pids differ (2 distinct real connections).

    mutation M21 (`mitatedb_api/backend_postgres.py`): drop the `@{conn.
    info.backend_pid}` suffix from `PostgresBackend.prepared_stats`'s own
    label -- this test's own pid-parsing assertions go red (no `@` to
    split on).
    mutation M22 (`mitatedb_api/backend_postgres.py`): drop the
    `("developer", self._developer_pool)` entry from `prepared_stats`'s own
    iteration -- this test's own `len(rows) == 2` assertion goes red.

    Completion condition 13 (MitateDB side, 空振り禁止, §1.5 の 32):
    running the SAME statement on a runtime-pool connection 6 times (crossing psycopg's
    own default `prepare_threshold=5`) before probing makes the
    `runtime@<pid>` row's own `prepared`/`prepared_execs` genuinely
    positive -- the same positive-observation property `test_repeated_
    same_statement_prepares_and_probe_observes_it` pins directly against
    `probe_prepared_statements` in `r2db-api/tests/test_r79_prepared_
    stats.py`; no separate mutation here (same property as M13, already
    covered by that test)."""
    backend = PostgresBackend(_admin_dsn(), _admin_dsn())
    try:
        runtime_conn = backend._runtime_pool.acquire()
        developer_conn = backend._developer_pool.acquire()
        runtime_pid = runtime_conn.info.backend_pid
        developer_pid = developer_conn.info.backend_pid
        try:
            with runtime_conn.cursor() as cur:
                for _ in range(6):
                    cur.execute("SELECT 1 WHERE 1 = 1")
            runtime_conn.commit()  # back to IDLE -- the probe skips a non-IDLE connection entirely (WO §6.1 L-13)
        finally:
            backend._runtime_pool.release(runtime_conn)
            backend._developer_pool.release(developer_conn)
        rows = backend.prepared_stats()  # each pool has only that one connection to hand out
        assert len(rows) == 2
        by_role = {row["label"].split("@", 1)[0]: row for row in rows}
        assert set(by_role) == {"runtime", "developer"}
        assert int(by_role["runtime"]["label"].split("@", 1)[1]) == runtime_pid
        assert int(by_role["developer"]["label"].split("@", 1)[1]) == developer_pid
        assert by_role["runtime"]["label"] != by_role["developer"]["label"]
        assert by_role["runtime"]["prepared"] >= 1
        assert by_role["runtime"]["prepared_execs"] >= 1
    finally:
        backend.close()


# ---------------------------------------------------------------------
# rework item (B): probe never counts itself as an
# application execute()
# ---------------------------------------------------------------------


def test_probe_does_not_increase_execute_count():
    """Rework item (B): probing a connection does not raise
    its own `execute_count` -- the probe reads through a bare `psycopg.
    Cursor(conn)`, never `conn.cursor()` (which would go through
    `CountingConnection`'s own `CountingCursor` and count the probe's own
    SELECT as application traffic).

    mutation M23 (`mitatedb_api/psycopg_counting.py`): change `probe_
    prepared_statements`'s own `with psycopg.Cursor(conn) as cur:` to
    `with conn.cursor() as cur:` -- this test's own `after == before`
    assertion goes red (`execute_count` rises by 1)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        before = conn.execute_count
        probe_prepared_statements(conn, "r79probe@test")
        after = conn.execute_count
        assert after == before
    finally:
        conn.close()


# ---------------------------------------------------------------------
# rework (item 2 / 指摘 5): a probe failure never leaves a
# connection aborted for the next caller
# ---------------------------------------------------------------------


def test_postgres_backend_prepared_stats_exception_rolls_back_a_non_idle_connection(monkeypatch: pytest.MonkeyPatch):
    """Rework 指摘 5: when the probe itself fails (a real
    driver error, injected here by pointing the probe's own SQL at a
    nonexistent table) AFTER it already opened a transaction (its own
    SELECT), `PostgresBackend.prepared_stats` rolls that connection back
    before reporting `probed=False`/`error=<class name>` -- so the row
    reports an idle connection and the connection is never returned
    mid-transaction (aborted) for the NEXT real request on it.

    mutation M25 (`mitatedb_api/backend_postgres.py`, `r2db-api/src/
    r2db_api/postgres.py`): drop the `if conn.info.transaction_status !=
    TransactionStatus.IDLE: conn.rollback()` guard from each peer's own
    `except` branch in `prepared_stats` -- this test's own post-call IDLE
    assertions go red (the connections stay aborted)."""
    import mitatedb_api.psycopg_counting as pc_module

    backend = PostgresBackend(_admin_dsn(), _admin_dsn())
    try:
        monkeypatch.setattr(pc_module, "PREPARED_STATEMENTS_SQL", "SELECT * FROM r79_nonexistent_probe_table_2")
        rows = backend.prepared_stats()
        assert len(rows) == 2
        for row in rows:
            assert row["probed"] is False
            assert row["error"] == "UndefinedTable"
            assert row["transaction_status"] == "IDLE"
        for pool in (backend._runtime_pool, backend._developer_pool):
            conn = pool.acquire()
            try:
                assert conn.info.transaction_status == TransactionStatus.IDLE
            finally:
                pool.release(conn)
    finally:
        backend.close()


# ---------------------------------------------------------------------
# acceptance audit item 1: the 80-character truncation of `statement`
# ---------------------------------------------------------------------

_LONG_QUERY = "SELECT 1 WHERE 1 = 1 AND " + " AND ".join(f"{i} = {i}" for i in range(1, 20))
assert len(_LONG_QUERY) > 80  # space check: the fixture query itself must exceed 80 chars


def test_probe_truncates_statement_text_to_80_characters():
    """Completion condition 14a (`prepared_statements[*]["statement"]` is
    the first 80 characters of the real statement, never the whole
    thing): running a query LONGER than 80 characters 6 times (crossing
    psycopg's own default `prepare_threshold=5`) and probing observes a
    `statement` value whose own length is exactly 80 and matches the
    query's own first 80 characters.

    mutation M26b (`mitatedb_api/psycopg_counting.py`): change `probe_
    prepared_statements`'s own `statement[:80]` to bare `statement` --
    this test's own `len(stmt) == 80` assertion goes red (observes the
    real, longer length instead)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            for _ in range(6):
                cur.execute(_LONG_QUERY)
        result = probe_prepared_statements(conn, "r79probe@test")
        assert result["prepared"] >= 1
        stmt = result["prepared_statements"][0]["statement"]
        assert len(stmt) == 80
        assert stmt == _LONG_QUERY[:80]
    finally:
        conn.close()


# ---------------------------------------------------------------------
# R-101 WP-1: MitateDB's own per-call (no-pool) platform DB-time folding
# -- `credential_store_postgres.PostgresCredentialStore`/`application_
# audit.PostgresApplicationAuditSink`, both `CountingConnection`-backed
# per-call connections mirroring `_RolePool`'s own pooled fold (tested
# directly against `r2db-api/tests/test_r79_prepared_stats.py`).
# ---------------------------------------------------------------------

_R101_PEPPER = "r101-platform-stats-test-pepper-value"


def test_credential_store_authenticate_increases_platform_session_and_wall_stats():
    """Completion condition 20 (訂正 2026-09-26, 作業指示書 §6.1 の 1):
    calling `authenticate` once increases the store's own `platform_
    stats()` -- `sessions` by exactly 1, `connect_wall_ms` and `db_wall_
    ms` by more than 0, `txn_count` stays at 0 -- observed against a real
    PostgreSQL connect + query attempt, whether or not the `credentials`/
    `applications` tables exist at the target DSN (`authenticate` fails
    closed either way; the connect and the query attempt both still
    happen and both still count, since the fold runs in a `finally`).
    `txn_count` stays 0 because `authenticate`'s own body is a single
    read-only `SELECT`, with no `commit()`/`rollback()` call anywhere on
    its own path -- the per-call connection closes without ever sending
    either.

    mutation M19 (`credential_store_postgres.py`): drop the `_fold_
    closed_connection_stats` call from `_borrow_connection`'s no-pool
    branch -- this test's own `db_wall_ms > 0` assertion goes red (stays
    at 0, since the closed connection's own total is never folded in)."""
    store = PostgresCredentialStore(_admin_dsn(), pepper=_R101_PEPPER, schema="public")
    before = store.platform_stats()
    assert before == {"sessions": 0, "connect_wall_ms": 0.0, "db_wall_ms": 0.0, "txn_count": 0, "db_calls": 0}
    with pytest.raises(AuthorizationStateUnavailable):
        store.authenticate("r101-probe-id.r101-probe-secret")
    after = store.platform_stats()
    assert after["sessions"] == 1
    assert after["connect_wall_ms"] > 0
    assert after["db_wall_ms"] > 0
    assert after["txn_count"] == 0
    assert after["db_calls"] >= 1


def test_application_audit_sink_append_increases_platform_stats():
    """Completion condition 21: calling `append` once increases the
    sink's own `platform_stats()` -- `sessions` by exactly 1, `db_wall_
    ms` and `txn_count` by more than 0 (the INSERT's own real `commit()`
    is what raises `txn_count`) -- against a real, successfully written
    PostgreSQL row on a throwaway schema/table this test creates and drops
    (same column set as migration `0005_application_audit.sql`, minus the
    defaulted `audit_seq`/`recorded_at`).

    mutation M20 (`application_audit.py`): drop the `_fold_closed_
    connection_stats` call from `append`'s own `finally` block -- this
    test's own `db_wall_ms > 0` assertion goes red first (stays at 0;
    `txn_count > 0`, asserted right after it, would go red too)."""
    schema = f"r101appaud{secrets.token_hex(4)}"
    admin = psycopg.connect(_admin_dsn(), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL(
                "CREATE TABLE {} (audit_seq bigserial, event_id text PRIMARY KEY, "
                "event_class text NOT NULL, occurred_at timestamptz NOT NULL, request_id text, "
                "application_id text, actor_type text, actor_id text, role text, "
                "operation text NOT NULL, target_kind text, outcome text NOT NULL, "
                "reason_code text, target_id text, count integer)"
            ).format(sql.Identifier(schema, "application_audit")))
        sink = PostgresApplicationAuditSink(_admin_dsn(), schema=schema)
        before = sink.platform_stats()
        assert before == {"sessions": 0, "connect_wall_ms": 0.0, "db_wall_ms": 0.0, "txn_count": 0, "db_calls": 0}
        sink.append(
            event_class="probe", request_id=None, application_id=None, actor_type=None,
            actor_id=None, role=None, operation="r101_probe", target_kind=None, outcome="ok",
        )
        after = sink.platform_stats()
        assert after["sessions"] == 1
        assert after["connect_wall_ms"] > 0
        assert after["db_wall_ms"] > 0
        assert after["txn_count"] > 0
        assert after["db_calls"] == 1
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def _self_attr(node: ast.AST, attr: str) -> bool:
    """`True` iff `node` is exactly the attribute access `self.<attr>`."""
    return isinstance(node, ast.Attribute) and node.attr == attr and isinstance(node.value, ast.Name) and node.value.id == "self"


def _find_with_lock_body(tree: ast.AST, *, lock_attr: str) -> "list[ast.stmt] | None":
    """The `body` of the first `with self.<lock_attr>:` statement found
    anywhere in `tree`, or `None` if there is no such statement at all."""
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                if _self_attr(item.context_expr, lock_attr):
                    return node.body
    return None


def _body_contains(body: "list[ast.stmt]", predicate) -> bool:
    """`True` iff any statement in `body` (searched recursively) contains
    a node matching `predicate`."""
    for stmt in body:
        for node in ast.walk(stmt):
            if predicate(node):
                return True
    return False


def test_platform_stats_fold_is_lexically_inside_the_platform_stats_lock():
    """Completion condition 26 (守る条件 (b)): `PostgresCredentialStore.
    _fold_closed_connection_stats`'s three accumulator increments (`self.
    _platform_db_wall_ms += db_wall_ms`, `self._platform_txn_count +=
    txn_count`, `self._platform_db_calls += db_calls`) must be lexically
    inside the SAME `with self._platform_stats_lock:` block. A source-shape
    pin, not a running-thread race: a 32-thread x 1000-iteration `sys.
    setswitchinterval(1e-6)` trial against this same method, run with the
    lock actually removed, still passed -- CPython's GIL does not
    reliably turn this unguarded accumulate into an observable lost update
    at this call rate, mirroring this repository's own prior finding for a
    different check-then-act race (`r2db-api/tests/test_threadpool_
    offload.py`, item 6's own header comment) -- so this deterministic AST
    pin is used instead.

    mutation M64 (`credential_store_postgres.py`): drop the `with self.
    _platform_stats_lock:` around the three accumulator additions in `_fold_
    closed_connection_stats` -- this test's own assertions go red (the
    three `AugAssign` nodes are no longer inside any `with self._platform_
    stats_lock:` block)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(PostgresCredentialStore._fold_closed_connection_stats)))
    body = _find_with_lock_body(tree, lock_attr="_platform_stats_lock")
    assert body is not None, "no `with self._platform_stats_lock:` block found in `_fold_closed_connection_stats`"
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_db_wall_ms") and isinstance(n.op, ast.Add)), (
        "the db_wall_ms accumulation is not lexically inside `with self._platform_stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_txn_count") and isinstance(n.op, ast.Add)), (
        "the txn_count accumulation is not lexically inside `with self._platform_stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_db_calls") and isinstance(n.op, ast.Add)), (
        "the db_calls accumulation is not lexically inside `with self._platform_stats_lock:`"
    )


def test_audit_sink_fold_is_lexically_inside_the_platform_stats_lock():
    """Completion condition 26 (守る条件 (b)): `PostgresApplicationAuditSink.
    _fold_closed_connection_stats`'s three accumulator increments (`self.
    _platform_db_wall_ms += db_wall_ms`, `self._platform_txn_count +=
    txn_count`, `self._platform_db_calls += db_calls`) must be lexically
    inside the SAME `with self._platform_stats_lock:` block, mirroring the
    credential store's own pin above (both classes fold a closed
    connection's counters the same way, under a statistics-only lock).

    mutation M64b (`application_audit.py`): drop the `with self.
    _platform_stats_lock:` around the three accumulator additions in `_fold_
    closed_connection_stats` -- this test's own assertions go red (the
    three `AugAssign` nodes are no longer inside any `with self._platform_
    stats_lock:` block)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(PostgresApplicationAuditSink._fold_closed_connection_stats)))
    body = _find_with_lock_body(tree, lock_attr="_platform_stats_lock")
    assert body is not None, "no `with self._platform_stats_lock:` block found in `_fold_closed_connection_stats`"
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_db_wall_ms") and isinstance(n.op, ast.Add)), (
        "the db_wall_ms accumulation is not lexically inside `with self._platform_stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_txn_count") and isinstance(n.op, ast.Add)), (
        "the txn_count accumulation is not lexically inside `with self._platform_stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_platform_db_calls") and isinstance(n.op, ast.Add)), (
        "the db_calls accumulation is not lexically inside `with self._platform_stats_lock:`"
    )



def test_bounded_connection_pool_new_connection_increases_platform_session_and_wall_stats():
    """Completion condition 156 (R-101 WP-3 D-11): acquiring a connection
    that opens a brand-new session (nothing idle yet) increases `platform_
    stats()`'s own `sessions` by exactly 1 and `connect_wall_ms` by more
    than 0, observed against a real PostgreSQL connect.

    mutation M194 (`pool.py`): drop the `sessions`/`connect_wall_ms`
    accumulation from `_new_connection` -- this test's own `sessions == 1`
    assertion goes red (stays at 0)."""
    pool = BoundedConnectionPool(_admin_dsn(), max_size=1)
    before = pool.platform_stats()
    assert before == {"sessions": 0, "connect_wall_ms": 0.0, "db_wall_ms": 0.0, "txn_count": 0, "db_calls": 0}
    conn = pool.acquire()
    try:
        after = pool.platform_stats()
        assert after["sessions"] == 1
        assert after["connect_wall_ms"] > 0
    finally:
        pool.release(conn)


def test_bounded_connection_pool_discard_preserves_db_wall_ms_and_txn_count():
    """Completion condition 157 (R-101 WP-3 D-11): a connection that has
    run a real query and a real transaction, then discarded, still shows
    up in `platform_stats()`'s own `db_wall_ms`/`txn_count`/`db_calls` --
    discarding a connection never loses the time/transactions/statements
    it already spent, observed against a real PostgreSQL round trip.

    mutation M195 (`pool.py`): drop the `_fold_closed_connection_stats`
    call from `discard` -- this test's own `db_wall_ms > 0`/`txn_count ==
    1` assertions go red (drop back to 0, the discarded connection's own
    totals are never folded in)."""
    pool = BoundedConnectionPool(_admin_dsn(), max_size=1)
    conn = pool.acquire()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    conn.commit()
    pool.discard(conn)
    after = pool.platform_stats()
    assert after["db_wall_ms"] > 0
    assert after["txn_count"] == 1
    assert after["db_calls"] >= 1


def test_bounded_connection_pool_closeall_preserves_db_wall_ms_and_txn_count():
    """Completion condition 158 (R-101 WP-3 D-11): same property as 157
    above, reached through `closeall()` instead of `discard()` -- a
    connection released back to idle, then closed by `closeall()`, still
    shows up in `platform_stats()`'s own `db_wall_ms`/`txn_count`/
    `db_calls`, against a real PostgreSQL round trip.

    mutation M196 (`pool.py`): drop the `_fold_closed_connection_stats`
    call from `closeall` -- this test's own `db_wall_ms > 0`/`txn_count ==
    1` assertions go red (drop back to 0, the closed connection's own
    totals are never folded in)."""
    pool = BoundedConnectionPool(_admin_dsn(), max_size=1)
    conn = pool.acquire()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    conn.commit()
    pool.release(conn)
    pool.closeall()
    after = pool.platform_stats()
    assert after["db_wall_ms"] > 0
    assert after["txn_count"] == 1
    assert after["db_calls"] >= 1


def test_bounded_connection_pool_platform_stats_makes_no_round_trip():
    """Completion condition 159 (R-101 WP-3 D-11): calling `platform_
    stats()` never touches `stats()`'s own `acquire_count`, nor any live
    idle connection's own `execute_count`/`db_wall_ms` -- no DB round trip,
    observed against a real PostgreSQL connection sitting idle in the pool.

    mutation M197 (`pool.py`): route `platform_stats()` through `acquire()`
    (checks a connection out, reads it, puts it back) instead of draining
    `self._idle` directly with `get_nowait`/`put_nowait` -- this test's own
    `acquire_count` assertion goes red (rises with every `platform_stats()`
    call instead of staying fixed)."""
    pool = BoundedConnectionPool(_admin_dsn(), max_size=1)
    conn = pool.acquire()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    pool.release(conn)
    before_acquire_count = pool.stats()["acquire_count"]
    before_execute_count = conn.execute_count
    before_db_wall_ms = conn.db_wall_ms
    pool.platform_stats()
    pool.platform_stats()
    assert pool.stats()["acquire_count"] == before_acquire_count
    assert conn.execute_count == before_execute_count
    assert conn.db_wall_ms == before_db_wall_ms


def test_bounded_connection_pool_fold_is_lexically_inside_the_stats_lock():
    """Completion condition 160 (守る条件 (b), R-101 WP-3 D-11):
    `BoundedConnectionPool._fold_closed_connection_stats`'s three
    accumulator increments (`self._closed_db_wall_ms += db_wall_ms`,
    `self._closed_txn_count += txn_count`, `self._closed_db_calls +=
    db_calls`) must be lexically inside the SAME `with self._stats_lock:`
    block, mirroring the credential store's own pin above (§6.1 の監督裁定
    3 の前例, and `r2db_api.postgres._RolePool._fold_closed_connection_
    stats`'s identical shape). A source-shape pin, not a running-thread
    race, for the same reason the credential-store pin above gives.

    mutation M198 (`pool.py`): drop the `with self._stats_lock:` around
    the three accumulator additions in `_fold_closed_connection_stats` --
    this test's own assertions go red (the three `AugAssign` nodes are no
    longer inside any `with self._stats_lock:` block)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(BoundedConnectionPool._fold_closed_connection_stats)))
    body = _find_with_lock_body(tree, lock_attr="_stats_lock")
    assert body is not None, "no `with self._stats_lock:` block found in `_fold_closed_connection_stats`"
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_closed_db_wall_ms") and isinstance(n.op, ast.Add)), (
        "the db_wall_ms accumulation is not lexically inside `with self._stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_closed_txn_count") and isinstance(n.op, ast.Add)), (
        "the txn_count accumulation is not lexically inside `with self._stats_lock:`"
    )
    assert _body_contains(body, lambda n: isinstance(n, ast.AugAssign) and _self_attr(n.target, "_closed_db_calls") and isinstance(n.op, ast.Add)), (
        "the db_calls accumulation is not lexically inside `with self._stats_lock:`"
    )



class _FakeDeadConnection:
    """A minimal stand-in for a server-closed `psycopg.Connection`: only
    the attributes `BoundedConnectionPool.acquire()`/`_fold_closed_
    connection_stats` actually read (never a real socket, never a real
    PostgreSQL server) -- review round 1 finding F6 (deviation (a) from
    work order §8.1's own AST-pin-only default for this file, accepted by
    supervisor ruling 2026-09-28)."""

    def __init__(self, db_wall_ms: float, txn_count: int, execute_count: int, executemany_count: int) -> None:
        self.closed = True
        self.db_wall_ms = db_wall_ms
        self.txn_count = txn_count
        self.execute_count = execute_count
        self.executemany_count = executemany_count


class _FakeLiveConnection:
    """A minimal stand-in for a healthy, open `psycopg.Connection` --
    same reasoning as `_FakeDeadConnection` above."""

    closed = False


def test_bounded_connection_pool_acquire_folds_a_dead_idle_connection_found_at_the_top_of_acquire(monkeypatch: pytest.MonkeyPatch):
    """Review round 1 finding F6: a connection found dead (`closed=True`)
    at the TOP of `acquire()` (stage 1, the `get_nowait` loop that reuses
    an idle connection, before a new one is ever created) still has its
    own `db_wall_ms`/`txn_count`/`execute_count + executemany_count`
    folded into `platform_stats()` before it is discarded -- a connection
    the server closed while idle never silently drops the time,
    transactions, or statements it already spent.

    mutation M203 (`pool.py`): drop the `_fold_closed_connection_stats
    (conn)` call from stage (1)'s dead-connection branch -- this test's
    own `db_wall_ms`/`txn_count`/`db_calls` assertions go red (stay at 0,
    the dead connection's own totals are never folded in)."""
    pool = BoundedConnectionPool("postgresql://unit-test-pool/not-a-real-dsn", max_size=1)
    dead = _FakeDeadConnection(db_wall_ms=5.0, txn_count=2, execute_count=2, executemany_count=1)
    pool._idle.put_nowait(dead)
    live = _FakeLiveConnection()
    monkeypatch.setattr(pool, "_new_connection", lambda: live)

    conn = pool.acquire()

    assert conn is live
    stats = pool.platform_stats()
    assert stats["db_wall_ms"] >= 5.0
    assert stats["txn_count"] >= 2
    assert stats["db_calls"] >= 3


def test_bounded_connection_pool_acquire_folds_a_dead_connection_found_while_waiting_at_budget():
    """Review round 1 finding F6: a connection found dead (`closed=True`)
    in stage (3) (the pool already at `max_size`, waiting on `self._idle.
    get(timeout=...)` for a released connection) still has its own
    `db_wall_ms`/`txn_count`/`execute_count + executemany_count` folded
    into `platform_stats()` before it is discarded -- same property as
    the test above, reached through the wait branch instead of the
    top-of-`acquire()` branch.

    The idle queue starts EMPTY (stage (1)'s own `get_nowait` must find
    nothing, or `acquire()` never reaches stage (3) at all) -- a
    background thread delivers both connections only once `acquire()` is
    already blocked in stage (3)'s own wait loop. Review round 2 finding
    N1: `pool._idle.empty()` right after `acquire()` returns makes this
    deterministic -- without it, `acquire()`'s own wait-loop `get(timeout
    =...)` could fire between the two `put()` calls below, grab `live`
    straight away, and return BEFORE `dead` is ever delivered; `dead`
    would then sit unprocessed in `self._idle`, and `platform_stats()`'s
    own idle-scan (reading a still-idle connection's attributes directly,
    never through the fold path) would make the assertions below pass
    for the wrong reason, even under mutation M204.

    mutation M204 (`pool.py`): drop the `_fold_closed_connection_stats
    (conn)` call from stage (3)'s dead-connection branch -- this test's
    own `db_wall_ms`/`txn_count`/`db_calls` assertions go red (stay at 0,
    the dead connection's own totals are never folded in)."""
    pool = BoundedConnectionPool("postgresql://unit-test-pool/not-a-real-dsn", max_size=1)
    pool._created = pool._max_size  # already at budget: acquire() skips stage (2) and enters the stage (3) wait loop
    live = _FakeLiveConnection()
    dead = _FakeDeadConnection(db_wall_ms=7.0, txn_count=3, execute_count=4, executemany_count=0)

    def _deliver_once_acquire_is_already_waiting() -> None:
        time.sleep(0.1)
        # LIFO queue: put the live connection first so the dead one (put
        # last) is the first one `acquire()` pops.
        pool._idle.put(live)
        pool._idle.put(dead)

    threading.Thread(target=_deliver_once_acquire_is_already_waiting, daemon=True).start()
    conn = pool.acquire()

    assert conn is live
    assert pool._idle.empty(), "both delivered connections must already be drained by acquire() itself (dead folded+forgotten, live returned), never left for platform_stats() to find still idle"
    stats = pool.platform_stats()
    assert stats["db_wall_ms"] >= 7.0
    assert stats["txn_count"] >= 3
    assert stats["db_calls"] >= 4
