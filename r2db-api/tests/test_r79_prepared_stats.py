"""R-79 (docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md
§2, WP-1; rework 2026-09-23): `r2db_api.psycopg_counting` (`CountingCursor`/
`CountingConnection`, `probe_prepared_statements`, `prepared_stats_
skeleton`, D-1/D-2) and `r2db_api.postgres`'s own `_RolePool.prepared_
stats`/`SharedPoolManager.prepared_stats` (the probe's own caller, D-2),
tested against a REAL PostgreSQL server -- every
completion condition this file covers requires observing the counter/probe
against real PostgreSQL, never a stand-in counter or a source-text proxy
(work order §1.5 の 52, echoing `OPERATING_CONDITIONS.md`).

Each test connects directly to `R2DB_TEST_ADMIN_DSN` (the same throwaway-
cluster admin DSN `tests/test_postgres.py` uses, set by `tools/testpg/
dsa_testpg.py` for the whole run) -- this file needs no per-application
database/role provisioning (no `platform`/`provision_app` fixture): every
test here exercises `CountingConnection`/`_RolePool`/`SharedPoolManager`/
the probe directly against the admin connection's own database, never
`r2db-api`'s own migrated schema, since none of what this WP added reads
or writes application data.

Never reads psycopg's own private `_prepared`/`_counts`/`_names` attributes
anywhere in this file (work order §1.1 (e)) -- every observation here goes
through `pg_prepared_statements` (via the probe under test) or a public
`psycopg.Connection` property (`.info.transaction_status`, `.prepare_
threshold`, `.prepared_max`).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from psycopg.pq import TransactionStatus

from r2db_api.postgres import SharedPoolManager, _RolePool
from r2db_api.psycopg_counting import CountingConnection, CountingCursor, probe_prepared_statements

ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


_ELEVEN_KEYS = {
    "label", "transaction_status", "probed", "execute_count", "executemany_count",
    "prepared", "prepared_execs", "prepare_threshold", "prepared_max",
    "prepared_statements", "error",
}


# ---------------------------------------------------------------------
# D-1: CountingCursor / CountingConnection (completion conditions 1-4, 7)
# ---------------------------------------------------------------------


def test_counting_cursor_execute_increments_execute_count():
    """Completion condition 1: `CountingCursor.execute` adds 1 to the
    owning connection's `execute_count` per call, observed against a real
    PostgreSQL connection driven N times, never a stand-in counter.

    mutation M1 (`r2db_api/psycopg_counting.py`): drop the `self.
    connection.execute_count += 1` line from `CountingCursor.execute`
    (`super()` stays) -- this test's own `execute_count == 3` assertion
    goes red (observes 0)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            for _ in range(3):
                cur.execute("SELECT 1")
        assert conn.execute_count == 3
    finally:
        conn.close()


def test_counting_cursor_executemany_increments_executemany_count():
    """Completion condition 2: `CountingCursor.executemany` adds 1 to
    `executemany_count` per call. `src`'s own real-traffic paths never
    call `executemany` (WO §1.3 (8)) -- this unit test is the only
    observation point.

    mutation M2 (`r2db_api/psycopg_counting.py`): drop the `self.
    connection.executemany_count += 1` line from `CountingCursor.
    executemany` -- this test's own `executemany_count == 1` assertion
    goes red (observes 0)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMPORARY TABLE r79_executemany_probe (n int)")
            cur.executemany("INSERT INTO r79_executemany_probe (n) VALUES (%s)", [(1,), (2,)])
        assert conn.executemany_count == 1
    finally:
        conn.close()


def test_counting_connection_cursor_factory_is_counting_cursor():
    """Completion condition 3: `conn.cursor()` returns an actual
    `CountingCursor` instance -- `psycopg.Connection.__init__` assigns
    `self.cursor_factory = Cursor` unconditionally (WO §1.3 (6)), so a
    bare class attribute on `CountingConnection` would be shadowed; this
    observes the runtime TYPE, not source text.

    mutation M3 (`r2db_api/psycopg_counting.py`): drop the `self.
    cursor_factory = CountingCursor` line from `CountingConnection.
    __init__` -- `conn.cursor()` falls back to psycopg's own base
    `Cursor`, and this test's own `type(cur) is CountingCursor`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            assert type(cur) is CountingCursor
    finally:
        conn.close()


def test_role_pool_connect_returns_counting_connection():
    """Completion condition 4: `_RolePool._connect` (reached through
    `connection()`) returns an actual `CountingConnection`, observed from
    a connection the pool itself handed out -- not source text or an
    environment proxy (§1.5 の 52).

    mutation M4 (`r2db_api/postgres.py`): change `_RolePool._connect` back
    to a bare `psycopg.connect(...)` -- this test's own `isinstance(conn,
    CountingConnection)` assertion goes red."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        with pool.connection() as conn:
            assert isinstance(conn, CountingConnection)
    finally:
        pool.close_all()


def test_psycopg_counting_sha256_matches_across_peers():
    """Completion condition 7 (design review 1 H-1/H-5): the two peers'
    own copies of `psycopg_counting.py` are byte-identical -- pinned by
    sha256 directly, not by `_ISOMORPHIC_TARGETS` (that table normalizes
    away a leading docstring before comparing, so it cannot pin whole-
    module identity as tightly as a straight sha256 compare does).

    mutation M7: change one character in either peer's own copy's
    docstring -- this test's own hex-digest equality assertion goes red."""
    here = Path(__file__).resolve().parents[2]
    r2db_copy = (here / "r2db-api" / "src" / "r2db_api" / "psycopg_counting.py").read_bytes()
    mitatedb_copy = (here / "MitateDB-api" / "src" / "mitatedb_api" / "psycopg_counting.py").read_bytes()
    assert hashlib.sha256(r2db_copy).hexdigest() == hashlib.sha256(mitatedb_copy).hexdigest()


# ---------------------------------------------------------------------
# D-2: the probe itself, driven directly (completion conditions 10-16)
# ---------------------------------------------------------------------


def test_probe_leaves_connection_idle_after_commit():
    """Completion condition 10: after a probe, the connection's own
    `transaction_status` is IDLE (`conn.info.transaction_status`),
    observed directly on the SAME connection object the probe touched.

    mutation M10 (`r2db_api/psycopg_counting.py`): drop the probe's own trailing
    `conn.commit()` -- the connection is left INTRANS after the probe's
    own SELECT, and this test's own IDLE assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        probe_prepared_statements(conn, "r79probe@test")
        assert conn.info.transaction_status == TransactionStatus.IDLE
    finally:
        conn.close()


def test_probe_does_not_clear_prepared_statements():
    """Completion condition 11: probing the same connection 6 times in a
    row never decreases `prepared` -- the probe's own `conn.commit()`
    (never `rollback()`) leaves whatever is already prepared untouched
    (WO §1.1 F2).

    mutation M11 (`r2db_api/psycopg_counting.py`): change the probe's `conn.
    commit()` to `conn.rollback()` -- a rollback on a NON-IDLE connection
    clears every prepared statement (F2); this test's own `prepared`
    observation drops to 0 on a later probe, red.

    Uses `autocommit=False` deliberately (not `True`, unlike the sibling
    tests below): F2's `rollback()`-clears-prepared behaviour only fires
    when the connection is NOT already IDLE at the moment `rollback()`
    runs (`_connection_base.py`:617's own early return) -- in `autocommit
    =True` mode a connection is IDLE again immediately after every
    statement, so `rollback()` there would always take that early-return
    path and never actually exercise F2, making mutation M11
    undetectable. `conn.commit()` after the 6 setup executions returns
    the connection to IDLE so the probe below's own SELECT is what opens
    the transaction `commit()`/`rollback()` then closes."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            for _ in range(6):
                cur.execute("SELECT 1 WHERE 1 = 1")
        conn.commit()  # 6 real executions cross psycopg's own default prepare_threshold (5); back to IDLE
        first = probe_prepared_statements(conn, "r79probe@test")["prepared"]
        assert first >= 1
        for _ in range(5):
            again = probe_prepared_statements(conn, "r79probe@test")["prepared"]
            assert again == first
    finally:
        conn.close()


def test_probe_select_itself_never_appears_in_view():
    """Completion condition 12: the probe's own SELECT (against `pg_
    prepared_statements`) never shows up in that same view, even after 6
    probes on the same connection -- `prepare=False` keeps it from ever
    becoming a server-side prepared statement.

    mutation M12 (`r2db_api/psycopg_counting.py`): drop `prepare=False` from the
    probe's own `cur.execute(...)` call -- 6 probes on the SAME connection
    cross the default threshold (5) and the probe's own SELECT starts
    showing up in `prepared_statements`, red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        result = None
        for _ in range(6):
            result = probe_prepared_statements(conn, "r79probe@test")
        assert result["prepared"] == 0
        assert result["prepared_statements"] == []
    finally:
        conn.close()


def test_repeated_same_statement_prepares_and_probe_observes_it():
    """Completion condition 13 (空振り禁止, §1.5 の 32): after the SAME
    statement runs on a connection 6 times (crossing psycopg's own
    default prepare_threshold=5), the probe genuinely observes `prepared
    >= 1` and `prepared_execs >= 1` -- proof the measurement apparatus can
    see a positive case, not merely a negative one.

    mutation M13 (`r2db_api/psycopg_counting.py`): replace `prepared_execs`'s own
    `generic_plans + custom_plans` sum with a constant 0 -- this test's
    own `prepared_execs >= 1` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            for _ in range(6):
                cur.execute("SELECT 1 WHERE 1 = 1")
        result = probe_prepared_statements(conn, "r79probe@test")
        assert result["prepared"] >= 1
        assert result["prepared_execs"] >= 1
    finally:
        conn.close()


def test_prepared_stats_dict_has_exactly_eleven_keys():
    """Completion condition 14a (design review 1 L-9): the probe's own
    dict carries EXACTLY the 11 keys WO §1.2 D-2 names -- no more, no
    fewer.

    mutation M14a (`r2db_api/psycopg_counting.py`): add a 12th key (e.g.
    `statement`) to `prepared_stats_skeleton`'s own returned dict -- this
    test's own `set(...) == _ELEVEN_KEYS` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        result = probe_prepared_statements(conn, "r79probe@test")
        assert set(result.keys()) == _ELEVEN_KEYS
    finally:
        conn.close()


def test_prepared_stats_label_distinguishes_connections_by_pid():
    """Completion condition 14b: two connections drawn from the SAME pool
    get DIFFERENT labels, differing by `@<backend_pid>` -- observed by
    drawing 2 real connections from a 2-slot pool.

    mutation M14b (`r2db_api/postgres.py`): drop the `@{conn.info.
    backend_pid}` suffix from `_RolePool.prepared_stats`'s own label --
    both connections report the identical label, and this test's own
    `len(labels) == 2` assertion goes red."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=2)
    try:
        with pool.connection(), pool.connection():
            pass  # both slots opened at least once -- 2 distinct backends exist
        rows = pool.prepared_stats("r79app/runtime")
        assert len(rows) == 2
        labels = {row["label"] for row in rows}
        assert len(labels) == 2
        assert all(label.startswith("r79app/runtime@") for label in labels)
    finally:
        pool.close_all()


def test_probe_exception_still_returns_connection_to_pool(monkeypatch: pytest.MonkeyPatch):
    """Completion condition 15 (design review 1 H-4): a probe that raises
    (a real driver error, injected here by pointing the probe's own SQL at
    a nonexistent table) still returns its connection to the pool via
    `finally`, reports `probed=False`/`error=<exception class name>`
    (never the message), and the pool can still hand out the same NUMBER
    of connections afterward.

    mutation M15 (`r2db_api/postgres.py`): drop the `finally:` around
    `self._queue.put_nowait(conn)` in `_RolePool.prepared_stats` -- the
    excepted connection is never returned, so this test's own
    re-acquisition (`with pool.connection():`) times out instead of
    succeeding, red."""
    import r2db_api.psycopg_counting as pc_module

    pool = _RolePool(_admin_dsn(), schema="public", acquire_timeout=2.0, maxconn=1)
    try:
        with pool.connection():
            pass  # leaves one idle connection in the pool's own queue
        monkeypatch.setattr(pc_module, "PREPARED_STATEMENTS_SQL", "SELECT * FROM r79_nonexistent_probe_table")
        rows = pool.prepared_stats("r79probe")
        assert len(rows) == 1
        assert rows[0]["probed"] is False
        assert rows[0]["error"] == "UndefinedTable"
        assert "r79_nonexistent_probe_table" not in rows[0]["error"]  # class name only, never the message
        monkeypatch.undo()
        with pool.connection() as conn:  # the pool's own one slot must still be usable
            assert conn is not None
    finally:
        pool.close_all()


def test_probe_skips_non_idle_connection():
    """Completion condition 16 (design review 1 L-13): a connection whose
    `transaction_status` is not IDLE at probe time is left completely
    alone -- `probed=False`, `transaction_status` names that state, and
    its own `prepared`/`prepared_execs` stay 0 (unread), never committed
    into or read from.

    mutation M16 (`r2db_api/psycopg_counting.py`): drop the `!= TransactionStatus.
    IDLE` guard in `probe_prepared_statements` -- a non-IDLE connection
    gets probed (and committed) instead of skipped, and this test's own
    `probed is False` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")  # left open on purpose -- never committed/rolled back
        assert conn.info.transaction_status != TransactionStatus.IDLE
        result = probe_prepared_statements(conn, "r79probe@test")
        assert result["probed"] is False
        assert result["transaction_status"] == TransactionStatus(conn.info.transaction_status).name
        assert result["prepared"] == 0
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------
# D-2: SharedPoolManager.prepared_stats (completion condition 8)
# ---------------------------------------------------------------------


def test_shared_pool_manager_prepared_stats_leaves_r78_stats_unchanged():
    """Completion condition 8: `SharedPoolManager.prepared_stats()` drains
    idle connections via `get_nowait` (never `_acquire()`) and returns
    them via `put_nowait` -- R-78's own `acquire_count`/`wait_count`/
    `in_use_peak` for the pool it probes are UNCHANGED before/after, and
    the probe itself genuinely observes >=1 connection (空振り禁止).

    mutation M8 (`r2db_api/postgres.py`): make `_RolePool.prepared_stats`
    borrow via `self._acquire()` instead of draining the queue directly
    -- this test's own `before == after` assertion on `acquire_count`
    goes red (an extra acquisition is recorded)."""
    manager = SharedPoolManager(idle_seconds=300, cache_max=8, pool_size=1, pool_max_overflow=0)
    try:
        pool = manager.get_pool(("r79app", "runtime"), _admin_dsn(), schema="public", maxconn=1)
        with pool.connection():
            pass  # leaves one idle connection in the pool's own queue
        before = pool.stats()
        rows = manager.prepared_stats()
        after = pool.stats()
        assert len(rows) >= 1  # space check: an idle connection is really probed
        assert before == after
    finally:
        manager.dispose_all()


# ---------------------------------------------------------------------
# rework (item (B)): probe never counts itself as an
# application execute()
# ---------------------------------------------------------------------


def test_probe_does_not_increase_execute_count():
    """Rework item (B): probing a connection does not raise
    its own `execute_count` -- the probe reads through a bare `psycopg.
    Cursor(conn)`, never `conn.cursor()` (which would go through
    `CountingConnection`'s own `CountingCursor` and count the probe's own
    SELECT as application traffic).

    mutation M23 (`r2db_api/psycopg_counting.py`): change `probe_prepared_
    statements`'s own `with psycopg.Cursor(conn) as cur:` to `with conn.
    cursor() as cur:` -- this test's own `after == before` assertion goes
    red (`execute_count` rises by 1)."""
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


def test_probe_exception_rolls_back_a_non_idle_connection_before_returning(monkeypatch: pytest.MonkeyPatch):
    """Rework 指摘 5: when the probe itself fails (a real
    driver error, injected here by pointing the probe's own SQL at a
    nonexistent table) AFTER it already opened a transaction (its own
    SELECT), `_RolePool.prepared_stats` rolls that connection back before
    reporting `probed=False`/`error=<class name>` -- so the connection
    the pool later hands to a real caller is never left mid-transaction
    (aborted) because of a probe failure.

    mutation M25 (`r2db_api/postgres.py`, `MitateDB-api/src/mitatedb_api/
    backend_postgres.py`): drop the `if conn.info.transaction_status !=
    TransactionStatus.IDLE: conn.rollback()` guard from each peer's own
    `except` branch in `prepared_stats` -- this test's own post-call IDLE
    assertion goes red (the connection stays aborted)."""
    import r2db_api.psycopg_counting as pc_module

    pool = _RolePool(_admin_dsn(), schema="public", acquire_timeout=2.0, maxconn=1)
    try:
        with pool.connection() as conn:
            held = conn
        monkeypatch.setattr(pc_module, "PREPARED_STATEMENTS_SQL", "SELECT * FROM r79_nonexistent_probe_table_2")
        rows = pool.prepared_stats("r79probe")
        assert len(rows) == 1
        assert rows[0]["probed"] is False
        assert rows[0]["error"] == "UndefinedTable"
        assert held.info.transaction_status == TransactionStatus.IDLE
    finally:
        pool.close_all()


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

    mutation M26a (`r2db_api/psycopg_counting.py`): change `probe_
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
