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

`ApplicationCell.prepared_stats`'s own lock-delegation (completion
conditions 9, 17) is tested with a FAKE backend (a plain object carrying
only the attribute under test) -- the property under test (the cell's own
`with self._lock:`) does not depend on the backend being a real PostgreSQL
connection.

Never reads psycopg's own private `_prepared`/`_counts`/`_names` attributes
anywhere in this file (work order §1.1 (e))."""
from __future__ import annotations

import os

import pytest
from psycopg.pq import TransactionStatus

from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell
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
    """Completion condition 5: `PostgresBackend.__init__`'s own `_runtime`/
    `_developer` (`backend_postgres.py`:272-273 pre-edit) are actual
    `CountingConnection` instances, observed by the attribute's own TYPE
    against a real PostgreSQL server (not source text, §1.5 の 52).

    mutation M5 (`mitatedb_api/backend_postgres.py`): change `PostgresBackend
    .__init__`'s own `self._developer = CountingConnection.connect(...)`
    back to a bare `psycopg.connect(...)` -- this test's own `isinstance
    (backend._developer, CountingConnection)` assertion goes red."""
    backend = PostgresBackend(_admin_dsn(), _admin_dsn())
    try:
        assert isinstance(backend._runtime, CountingConnection)
        assert isinstance(backend._developer, CountingConnection)
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
# cell's own lock, not the backend's own connections.
# ---------------------------------------------------------------------


class _FakeBackend:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def prepared_stats(self):
        self.calls += 1
        return self._rows


def test_application_cell_prepared_stats_delegates_under_lock():
    """Completion condition 9 (起草時の裁定 4): `ApplicationCell.
    prepared_stats()` delegates to `self._backend.prepared_stats()` under
    `self._lock`, and returns `[]` when the backend has no such method
    (`SQLiteBackend`, and any other non-PostgreSQL backend) -- checked
    here by an equally-shaped fake `SQLiteBackend`-like object with no
    `prepared_stats` attribute at all.

    mutation M9 (`mitatedb_api/cell.py`): drop the `with self._lock:`
    around `ApplicationCell.prepared_stats`'s own delegation -- this
    test's own `lock_acquire_count` delta assertion goes red (the lock is
    never actually entered, so its own counter stays at 0)."""
    fake_rows = [{"label": "runtime@1", "prepared": 0}]
    backend = _FakeBackend(fake_rows)
    cell = ApplicationCell("r79app", backend=backend)

    before = cell._lock.stats()["lock_acquire_count"]
    result = cell.prepared_stats()
    after = cell._lock.stats()["lock_acquire_count"]

    assert result == fake_rows
    assert after == before + 1
    assert backend.calls == 1

    class _NoProbeBackend:
        pass

    cell_without_probe = ApplicationCell("r79app2", backend=_NoProbeBackend())
    assert cell_without_probe.prepared_stats() == []


def test_application_cell_prepared_stats_lock_acquire_count_matches_probe_count():
    """Completion condition 17 (design review 1 H-3): calling `Application
    Cell.prepared_stats()` N times increases `self._lock`'s own `lock_
    acquire_count` by EXACTLY N -- one cell-lock acquisition per probe,
    never more, never fewer (mirrors R-78's own `pool_stats()`-based
    before/after reads).

    mutation M17 (`mitatedb_api/cell.py`): duplicate `ApplicationCell.
    prepared_stats`'s own `with self._lock: ... return backend_probe()`
    body into a SECOND, separate `with self._lock:` block that calls
    `backend_probe()` again -- each call now acquires `self._lock` twice
    (not once) and calls the backend twice (not once), so this test's own
    `after == before + 3` assertion (for N=3 calls) goes red against
    `after == before + 6`."""
    backend = _FakeBackend([])
    cell = ApplicationCell("r79app3", backend=backend)

    before = cell._lock.stats()["lock_acquire_count"]
    for _ in range(3):
        cell.prepared_stats()
    after = cell._lock.stats()["lock_acquire_count"]

    assert after == before + 3
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
    `("developer", self._developer)` entry from `prepared_stats`'s own
    iteration -- this test's own `len(rows) == 2` assertion goes red.

    Completion condition 13 (MitateDB side, 空振り禁止, §1.5 の 32):
    running the SAME statement on `_runtime` 6 times (crossing psycopg's
    own default `prepare_threshold=5`) before probing makes the
    `runtime@<pid>` row's own `prepared`/`prepared_execs` genuinely
    positive -- the same positive-observation property `test_repeated_
    same_statement_prepares_and_probe_observes_it` pins directly against
    `probe_prepared_statements` in `r2db-api/tests/test_r79_prepared_
    stats.py`; no separate mutation here (same property as M13, already
    covered by that test)."""
    backend = PostgresBackend(_admin_dsn(), _admin_dsn())
    try:
        with backend._runtime.cursor() as cur:
            for _ in range(6):
                cur.execute("SELECT 1 WHERE 1 = 1")
        backend._runtime.commit()  # back to IDLE -- the probe skips a non-IDLE connection entirely (WO §6.1 L-13)
        rows = backend.prepared_stats()
        assert len(rows) == 2
        by_role = {row["label"].split("@", 1)[0]: row for row in rows}
        assert set(by_role) == {"runtime", "developer"}
        assert int(by_role["runtime"]["label"].split("@", 1)[1]) == backend._runtime.info.backend_pid
        assert int(by_role["developer"]["label"].split("@", 1)[1]) == backend._developer.info.backend_pid
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
    before reporting `probed=False`/`error=<class name>` -- so this
    backend's own persistent connection is never left mid-transaction
    (aborted) for the NEXT real request on it.

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
        assert backend._runtime.info.transaction_status == TransactionStatus.IDLE
        assert backend._developer.info.transaction_status == TransactionStatus.IDLE
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
