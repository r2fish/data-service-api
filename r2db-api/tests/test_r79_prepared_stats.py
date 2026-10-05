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

import ast
import hashlib
import inspect
import os
import textwrap
from pathlib import Path

import psycopg
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


_THIRTEEN_KEYS = {
    "label", "transaction_status", "probed", "execute_count", "executemany_count",
    "prepared", "prepared_execs", "prepare_threshold", "prepared_max",
    "prepared_statements", "error", "db_wall_ms", "txn_count",
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
    runs (`psycopg`'s `_connection_base.py::BaseConnection._rollback_gen`'s own early return) -- in `autocommit
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


def test_prepared_stats_dict_has_exactly_thirteen_keys():
    """Completion condition 14a (design review 1 L-9), updated by R-101
    WP-1 completion condition 16: the probe's own dict carries EXACTLY the
    13 keys (the original 11, plus `db_wall_ms`/`txn_count`) -- no more,
    no fewer.

    mutation M14a (`r2db_api/psycopg_counting.py`): add a 14th key (e.g.
    `statement`) to `prepared_stats_skeleton`'s own returned dict -- this
    test's own `set(...) == _THIRTEEN_KEYS` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        result = probe_prepared_statements(conn, "r79probe@test")
        assert set(result.keys()) == _THIRTEEN_KEYS
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


# ---------------------------------------------------------------------
# WP-3 (work order §3.4): the liveness ping no longer clears prepared
# statements on every checkout -- completion conditions 33-37, 40
# ---------------------------------------------------------------------


def test_six_checkouts_through_the_pool_leave_prepared_statements_in_place():
    """Completion condition 33 (空振り禁止, §1.5 の 32): checking the SAME
    connection out of the pool 6+ times, running the SAME statement once
    per checkout and closing each checkout the way a real request does
    (`with conn.transaction():`, ending in a commit), crosses psycopg's
    own default `prepare_threshold` (5) -- the probe observes `prepared
    >= 1` and `prepared_execs >= 1` on that connection afterwards.
    `maxconn=1` forces the same connection to be reused across all 6
    checkouts (pool sizing is an implementation detail here, not the
    point under test).

    mutation M27 (`r2db_api/postgres.py`, `edits`): revert `_liveness_
    check` to its pre-WP-3 form -- `conn.autocommit = True` and the
    `finally: conn.autocommit = False` dropped, `conn.rollback()` placed
    right after the ping's own `SELECT 1` instead. Every checkout's ping
    then opens a transaction (`SELECT 1` under `autocommit=False`) that
    `rollback()` immediately closes, clearing every prepared statement on
    the connection each time (`rollback()` on a non-IDLE connection is
    not the early-return case); this test's own `prepared >= 1` assertion
    goes red (observes 0)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        pid = None
        for _ in range(6):
            with pool.connection() as conn:
                pid = conn.info.backend_pid
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 WHERE 1 = 1")
        rows = pool.prepared_stats("r79app/runtime")
        assert len(rows) == 1
        row = rows[0]
        assert row["label"] == f"r79app/runtime@{pid}"
        assert row["prepared"] >= 1
        assert row["prepared_execs"] >= 1
        assert any("WHERE 1 = 1" in st["statement"] for st in row["prepared_statements"]), row["prepared_statements"]
    finally:
        pool.close_all()


def test_connection_handed_out_by_the_pool_is_idle_with_autocommit_false():
    """Completion condition 34: the connection `pool.connection()` hands
    to its caller -- observed directly on that same object, not a copy or
    a proxy -- is IDLE (`conn.info.transaction_status`) and has
    `autocommit is False` after the ping has run. `_liveness_check` runs
    on every checkout (including the first, freshly-`_connect()`-ed one),
    so a single checkout is enough to exercise the ping's own `autocommit`
    flip and its `finally` reset.

    mutation M28 (`r2db_api/postgres.py`): drop `_liveness_check`'s own
    `finally: conn.autocommit = False` -- the connection is handed out
    still in `autocommit=True` mode, and this test's own `conn.autocommit
    is False` assertion goes red."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        with pool.connection() as conn:
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert conn.autocommit is False
    finally:
        pool.close_all()


def test_ping_select_1_never_opens_a_transaction():
    """Completion condition 35: the ping's own `SELECT 1`, observed FROM
    INSIDE `_liveness_check` itself (immediately after `super().execute()`
    returns, before whatever runs after it), never leaves the connection
    non-IDLE -- a `cursor_factory` subclass records `conn.info.
    transaction_status` at that exact point, and `_liveness_check` is
    called directly (not through `connection()`) so the observation point
    is the ping itself, not the connection after hand-off.

    mutation M29 (`r2db_api/postgres.py`): change the ping's own leading
    `conn.autocommit = True` to `conn.autocommit = False` -- `SELECT 1`
    then runs under `autocommit=False` and opens a transaction. Measured
    (2026-09-23): the test goes red at `assert ok is True` -- the ping's
    `finally` sets `autocommit = False` on an INTRANS connection, psycopg
    raises `ProgrammingError`, and `_liveness_check` reports the connection
    dead -- before the recorded-status assertion is reached. A mutation
    that instead wraps the ping in raw `BEGIN`/`ROLLBACK` reds the
    recorded-status assertion itself (INTRANS observed, not IDLE)."""
    recorded: list[TransactionStatus] = []

    class _RecordingCursor(psycopg.Cursor):
        def execute(self, *args, **kwargs):
            result = super().execute(*args, **kwargs)
            owning_conn = self.connection
            recorded.append(TransactionStatus(owning_conn.info.transaction_status))
            return result

    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        conn = pool._connect()
        try:
            conn.cursor_factory = _RecordingCursor
            ok = pool._liveness_check(conn)
            assert ok is True
            assert len(recorded) == 1
            assert recorded[0] == TransactionStatus.IDLE
        finally:
            conn.close()
    finally:
        pool.close_all()


def test_dead_connection_is_discarded_for_one_with_a_different_backend_pid():
    """Completion condition 36 (空振り禁止, §1.5 の 32): the existing tests
    that touch `_liveness_check` (`test_threadpool_offload.py`'s 2
    monkeypatches) both replace it outright and never exercise a real
    ping failure, so this is the first test of the actual failure
    behaviour -- a connection whose server-side backend is killed
    (`pg_terminate_backend`) while idle in the pool's own queue is not
    handed back to a caller: `_liveness_check` reports it dead, `pool.
    connection()` opens a fresh one instead, usable, with a DIFFERENT
    `backend_pid`.

    mutation M30 (`r2db_api/postgres.py`): drop the `except` branch's own
    `conn.close()` call and return `True` instead of `False` -- the dead
    connection is reported alive and handed straight back to a caller
    instead of being replaced. Measured (2026-09-23): the test goes red
    with `OperationalError: the connection is closed` on the reused dead
    connection, before the `new_pid != dead_pid` assertion is reached --
    either way the dead connection was handed out instead of a fresh
    one."""
    admin = psycopg.connect(_admin_dsn(), autocommit=True)
    try:
        pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
        try:
            with pool.connection() as conn:
                dead_pid = conn.info.backend_pid
            with admin.cursor() as cur:
                cur.execute("SELECT pg_terminate_backend(%s)", [dead_pid])
            with pool.connection() as conn:
                new_pid = conn.info.backend_pid
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    assert cur.fetchone() == (1,)
            assert new_pid != dead_pid
        finally:
            pool.close_all()
    finally:
        admin.close()


def test_liveness_ping_raises_execute_count_by_exactly_one_per_checkout():
    """Completion condition 37 (D-1 の計数の解釈用): the ping's own
    contribution to `CountingConnection.execute_count` is EXACTLY 1 per
    checkout through `pool.connection()` -- observed as the difference
    between two successive checkouts of the SAME connection (`maxconn=1`)
    with nothing executed inside either `with` block; the second
    checkout's own ping is the only thing that can have raised the count
    between the two observations.

    mutation M31 (`r2db_api/postgres.py`): make the ping run `cur.execute
    ("SELECT 1")` twice -- this test's own `after - before == 1`
    assertion goes red (observes 2)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        with pool.connection() as conn:
            before = conn.execute_count  # already reflects this checkout's own ping
        with pool.connection() as conn:
            after = conn.execute_count  # reflects the SECOND checkout's own ping, and nothing else
        assert after - before == 1
    finally:
        pool.close_all()


def test_non_idle_dequeued_connection_is_rolled_back_and_reused():
    """Completion condition 40 (監督裁定 2026-09-23): a connection dequeued
    non-IDLE -- pushed back into `_queue` directly, bypassing `connection(
    )`'s own defence-in-depth rollback in its `finally` block, to isolate
    `_liveness_check`'s OWN pre-check -- is rolled back and REUSED: same
    `backend_pid`, IDLE, not discarded for a fresh connection. The
    pre-check exists precisely so `conn.autocommit = True` (which
    requires an IDLE connection) never raises on it.

    mutation M32 (`r2db_api/postgres.py`): drop the `if conn.info.
    transaction_status != TransactionStatus.IDLE: conn.rollback()`
    pre-check -- `conn.autocommit = True` on the still-INTRANS connection
    raises `ProgrammingError`, `_liveness_check` discards it (closes it,
    returns `False`), and `connection()` opens a brand-new one instead;
    this test's own `backend_pid` equality assertion goes red (observes a
    DIFFERENT pid)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        conn = pool._connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")  # left open on purpose -- non-IDLE
        assert conn.info.transaction_status != TransactionStatus.IDLE
        before_pid = conn.info.backend_pid
        pool._queue.put_nowait(conn)  # bypass connection()'s own finally-time rollback
        with pool.connection() as reused:
            assert reused.info.backend_pid == before_pid
            assert reused.info.transaction_status == TransactionStatus.IDLE
    finally:
        pool.close_all()


# ---------------------------------------------------------------------
# R-101 WP-1: `db_wall_ms`/`txn_count` on `CountingConnection`, and their
# fold into `_RolePool`'s own platform accounting
# ---------------------------------------------------------------------


class _R101ProbeError(Exception):
    """A distinct exception type for the `transaction()` override's
    exception-propagation tests below -- never `psycopg.Rollback`, so the
    override must not swallow it."""


class _R101ProbeExitError(Exception):
    """A SECOND distinct exception type, used only where the exit round
    trip itself (`base_cm.__exit__`) raises while a block-body exception
    is also in flight -- distinct from `_R101ProbeError` so a test can
    tell which of the two the caller actually observes."""


def test_counting_cursor_execute_increases_db_wall_ms():
    """Completion condition 1: `CountingCursor.execute` increases the
    owning connection's `db_wall_ms` by the real round-trip wall time --
    `pg_sleep` gives the round trip a floor duration well above
    measurement noise.

    mutation M1 (`psycopg_counting.py`): drop the `db_wall_ms`
    accumulation from `CountingCursor.execute` -- this test's own
    `after > before` assertion goes red (observes no change)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        before = conn.db_wall_ms
        with conn.cursor() as cur:
            cur.execute("SELECT pg_sleep(0.05)")
        after = conn.db_wall_ms
        assert after > before
    finally:
        conn.close()


def test_counting_cursor_executemany_increases_db_wall_ms():
    """Completion condition 2: `CountingCursor.executemany` increases
    `db_wall_ms` too, observed on a real round trip.

    mutation M2 (`psycopg_counting.py`): drop the `db_wall_ms`
    accumulation from `CountingCursor.executemany` -- this test's own
    `after > before` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        before = conn.db_wall_ms
        with conn.cursor() as cur:
            cur.executemany("SELECT pg_sleep(%s)", [(0.02,), (0.02,)])
        after = conn.db_wall_ms
        assert after > before
    finally:
        conn.close()


def test_commit_override_increases_db_wall_ms():
    """Completion condition 3: calling `commit()` once increases
    `db_wall_ms`.

    mutation M3 (`psycopg_counting.py`): drop the `db_wall_ms`
    accumulation from `commit()` -- this test's own `after > before`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        before = conn.db_wall_ms
        conn.commit()
        after = conn.db_wall_ms
        assert after > before
    finally:
        conn.close()


def test_commit_override_increases_txn_count_by_one():
    """Completion condition 4: calling `commit()` once increases
    `txn_count` by exactly 1.

    mutation M4 (`psycopg_counting.py`): drop the `txn_count`
    accumulation from `commit()` -- this test's own `after - before == 1`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        before = conn.txn_count
        conn.commit()
        after = conn.txn_count
        assert after - before == 1
    finally:
        conn.close()


def test_rollback_override_increases_db_wall_ms():
    """Completion condition 5: calling `rollback()` once increases
    `db_wall_ms`.

    mutation M5 (`psycopg_counting.py`): drop the `db_wall_ms`
    accumulation from `rollback()` -- this test's own `after > before`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        before = conn.db_wall_ms
        conn.rollback()
        after = conn.db_wall_ms
        assert after > before
    finally:
        conn.close()


def test_rollback_override_increases_txn_count_by_one():
    """Completion condition 6: calling `rollback()` once increases
    `txn_count` by exactly 1.

    mutation M6 (`psycopg_counting.py`): drop the `txn_count`
    accumulation from `rollback()` -- this test's own `after - before ==
    1` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        before = conn.txn_count
        conn.rollback()
        after = conn.txn_count
        assert after - before == 1
    finally:
        conn.close()


def test_transaction_enter_increases_db_wall_ms():
    """Completion condition 7: entering `with conn.transaction():`
    increases `db_wall_ms`, observed from INSIDE the block so only the
    enter side (`BEGIN`) is captured.

    mutation M7 (`psycopg_counting.py`): drop the enter-side `db_wall_ms`
    accumulation from `transaction()` -- this test's own `inside > before`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        before = conn.db_wall_ms
        with conn.transaction():
            inside = conn.db_wall_ms
        assert inside > before
    finally:
        conn.close()


def test_transaction_enter_increases_txn_count_by_one():
    """Completion condition 8: entering the block increases `txn_count`
    by exactly 1, observed from inside.

    mutation M8 (`psycopg_counting.py`): drop the enter-side `txn_count`
    accumulation from `transaction()` -- this test's own `inside - before
    == 1` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        before = conn.txn_count
        with conn.transaction():
            inside = conn.txn_count
        assert inside - before == 1
    finally:
        conn.close()


def test_transaction_exit_increases_db_wall_ms():
    """Completion condition 9: leaving the block increases `db_wall_ms`
    again, beyond whatever the enter side already added -- compares the
    value observed just inside the block to the value observed right
    after it exits.

    mutation M9 (`psycopg_counting.py`): drop the exit-side `db_wall_ms`
    accumulation from `transaction()` -- this test's own `after > inside`
    assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.transaction():
            inside = conn.db_wall_ms
        after = conn.db_wall_ms
        assert after > inside
    finally:
        conn.close()


def test_transaction_exit_increases_txn_count_by_one():
    """Completion condition 10: leaving the block increases `txn_count`
    by exactly 1 beyond the enter side's own +1 -- 2 total for one full
    `with` block.

    mutation M10 (`psycopg_counting.py`): drop the exit-side `txn_count`
    accumulation from `transaction()` -- this test's own `after - before
    == 2` assertion goes red (observes 1)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        before = conn.txn_count
        with conn.transaction():
            pass
        after = conn.txn_count
        assert after - before == 2
    finally:
        conn.close()


def test_transaction_swallows_psycopg_rollback():
    """Completion condition 11 (守る条件 (b)): raising `psycopg.Rollback`
    inside `with conn.transaction():` is swallowed by the override exactly
    as the base class swallows it -- the block completes normally, no
    exception reaches the caller, and the connection is left IDLE.

    mutation M11 (`psycopg_counting.py`): make the override's own
    exit-side re-raise unconditionally, ignoring `base_cm.__exit__`'s own
    return value -- this test's own "no exception raised" observation
    goes red (`psycopg.Rollback` escapes)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with conn.transaction():
            raise psycopg.Rollback()
        assert conn.info.transaction_status == TransactionStatus.IDLE
    finally:
        conn.close()


def test_transaction_propagates_non_rollback_exception():
    """Completion condition 12: raising a non-`psycopg.Rollback` exception
    inside the block propagates unchanged to the caller, with its own
    original type.

    mutation M12 (`psycopg_counting.py`): make the override return
    (swallow) instead of re-raising -- this test's own `pytest.raises(
    _R101ProbeError)` assertion goes red (no exception observed)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        with pytest.raises(_R101ProbeError):
            with conn.transaction():
                raise _R101ProbeError("boom")
    finally:
        conn.close()


def test_transaction_exception_path_still_accumulates_exit_side():
    """Completion condition 13: even on the exception path, the exit
    side's own `db_wall_ms`/`txn_count` accumulation still runs -- 2 total
    `txn_count` for one block, whether it exits normally or via an
    exception.

    mutation M13 (`psycopg_counting.py`): move the exit-side accumulation
    in the override to the success-only branch -- this test's own `after -
    before == 2` assertion goes red (observes 1: only the enter side
    counted)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        before = conn.txn_count
        with pytest.raises(_R101ProbeError):
            with conn.transaction():
                raise _R101ProbeError("boom")
        after = conn.txn_count
        assert after - before == 2
    finally:
        conn.close()


def test_transaction_enter_still_accumulates_when_begin_itself_raises(monkeypatch):
    """Code review 1 F8: when BEGIN itself (`base_cm.__enter__()`) raises
    (a stub failure here, not a real PostgreSQL round-trip failure), the
    enter side's own `db_wall_ms`/`txn_count` accumulation still runs --
    matching `commit`/`rollback`'s own finally-based accounting above, so
    a round trip that was attempted and failed is not silently dropped
    from the totals.

    mutation M103 (`psycopg_counting.py`): drop the `try`/`finally` around
    `base_cm.__enter__()` in `transaction()`'s enter side -- this test's
    own `db_wall_ms > before_wall` / `txn_count - before_txn == 1`
    assertions go red (stay unchanged; the raised exception skips the
    accumulation entirely)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        class _StubTransactionCM:
            def __enter__(self):
                raise _R101ProbeError("R-101 WP-1 test: simulated BEGIN failure")

            def __exit__(self, *exc_info):
                return False

        monkeypatch.setattr(psycopg.Connection, "transaction", lambda self, *a, **kw: _StubTransactionCM())
        before_wall = conn.db_wall_ms
        before_txn = conn.txn_count
        with pytest.raises(_R101ProbeError):
            with conn.transaction():
                pass
        assert conn.db_wall_ms > before_wall
        assert conn.txn_count - before_txn == 1
    finally:
        conn.close()


def test_transaction_exit_still_accumulates_when_the_success_path_exit_itself_raises(monkeypatch):
    """コードレビュー 2 差し戻し 3 指摘 4: when the exit round trip itself
    (`base_cm.__exit__(None, None, None)`, e.g. COMMIT failing) raises on
    the success path -- a stub failure here, not a real PostgreSQL
    round-trip failure -- the exit side's own `db_wall_ms`/`txn_count`
    accumulation still runs (matching `test_transaction_enter_still_
    accumulates_when_begin_itself_raises` above, for the exit side of the
    success branch), and the stub's own exception propagates with its
    original type.

    mutation M109 (`psycopg_counting.py`, both copies): drop the `try`/
    `finally` around `base_cm.__exit__(None, None, None)` in `transaction(
    )`'s success-path exit side -- this test's own `txn_count - before_
    txn == 2` assertion goes red (observes 1: only the enter side
    counted)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        class _StubTransactionCM:
            def __enter__(self):
                return None

            def __exit__(self, *exc_info):
                raise _R101ProbeError("R-101 WP-1 test: simulated exit-side COMMIT failure")

        monkeypatch.setattr(psycopg.Connection, "transaction", lambda self, *a, **kw: _StubTransactionCM())
        before_wall = conn.db_wall_ms
        before_txn = conn.txn_count
        with pytest.raises(_R101ProbeError):
            with conn.transaction():
                pass
        assert conn.db_wall_ms > before_wall
        assert conn.txn_count - before_txn == 2
    finally:
        conn.close()


def test_transaction_exit_still_accumulates_when_the_exception_path_exit_itself_raises(monkeypatch):
    """コードレビュー 2 差し戻し 3 指摘 4: when the block itself raises AND
    the exit round trip (`base_cm.__exit__(type, exc, tb)`, e.g. ROLLBACK
    failing) also raises -- a stub failure here -- the exit side's own
    `db_wall_ms`/`txn_count` accumulation still runs, and the exit's own
    exception (not the block's own) is what the caller observes, with its
    original type (ordinary context-manager semantics: an `__exit__` that
    raises replaces the exception already in flight).

    mutation M110 (`psycopg_counting.py`, both copies): drop the `try`/
    `finally` around `base_cm.__exit__(...)` in `transaction()`'s
    exception-path exit side -- this test's own `txn_count - before_txn
    == 2` assertion goes red (observes 1: only the enter side counted)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        class _StubTransactionCM:
            def __enter__(self):
                return None

            def __exit__(self, *exc_info):
                raise _R101ProbeExitError("R-101 WP-1 test: simulated exit-side ROLLBACK failure")

        monkeypatch.setattr(psycopg.Connection, "transaction", lambda self, *a, **kw: _StubTransactionCM())
        before_wall = conn.db_wall_ms
        before_txn = conn.txn_count
        with pytest.raises(_R101ProbeExitError):
            with conn.transaction():
                raise _R101ProbeError("boom")
        assert conn.db_wall_ms > before_wall
        assert conn.txn_count - before_txn == 2
    finally:
        conn.close()


def test_failed_statement_still_increases_db_wall_ms_and_execute_count():
    """Completion condition 14: a statement PostgreSQL itself rejects (a
    real driver error, not a mocked one) still counts as one attempt --
    `execute_count` and `db_wall_ms` both rise, and the original exception
    still propagates to the caller.

    mutation M14 (`psycopg_counting.py`): move the `db_wall_ms`
    accumulation in `CountingCursor.execute` to the success-only branch --
    this test's own `db_wall_ms` `after > before` assertion goes red
    (observes no change on the failed call)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        before_wall = conn.db_wall_ms
        before_count = conn.execute_count
        with pytest.raises(psycopg.errors.UndefinedTable):
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM r101_nonexistent_table_probe")
        assert conn.execute_count - before_count == 1
        assert conn.db_wall_ms > before_wall
    finally:
        conn.close()


def test_probe_does_not_change_db_wall_ms_or_txn_count():
    """Completion condition 15: probing a connection once leaves its own
    `db_wall_ms`/`txn_count` unchanged -- the probe's own SELECT runs
    through a bare `psycopg.Cursor` (never `CountingCursor`), and its own
    commit calls the BASE `commit()`, never the override.

    mutation M15 (`psycopg_counting.py`): change the probe's own commit
    back to `conn.commit()` (through the override) -- this test's own
    `after == before` assertion on `txn_count` goes red (rises by 1)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        before_wall = conn.db_wall_ms
        before_txn = conn.txn_count
        probe_prepared_statements(conn, "r101probe@test")
        assert conn.db_wall_ms == before_wall
        assert conn.txn_count == before_txn
    finally:
        conn.close()


def test_skeleton_db_wall_ms_and_txn_count_match_connection_attributes():
    """Completion condition 17: after running a `pg_sleep` statement,
    `prepared_stats_skeleton`'s own `db_wall_ms`/`txn_count` match the
    connection's own attributes exactly, and `db_wall_ms` is positive.

    mutation M17 (`psycopg_counting.py`): replace `prepared_stats_
    skeleton`'s own `db_wall_ms` with a constant `0.0` -- this test's own
    `result["db_wall_ms"] > 0` assertion goes red."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_sleep(0.05)")
        result = probe_prepared_statements(conn, "r101probe@test")
        assert result["db_wall_ms"] == conn.db_wall_ms
        assert result["txn_count"] == conn.txn_count
        assert result["db_wall_ms"] > 0
    finally:
        conn.close()


def test_role_pool_platform_stats_does_not_decrease_when_a_connection_closes():
    """Completion condition 24: after a real PostgreSQL round trip on a
    pooled connection, retiring the pool (closing every idle connection)
    does not decrease `platform_stats()`'s own `db_wall_ms`/`txn_count` --
    the connection's own totals are folded into the pool's accumulator
    before it closes.

    mutation M62 (`r2db_api/postgres.py`): drop the `_fold_closed_
    connection_stats` call from `close_all`'s own drain loop -- this
    test's own `after["db_wall_ms"] >= before["db_wall_ms"]` assertion
    goes red (drops to 0, since the closed connection's own totals are
    lost).

    mutation M100 (code review 1 F4(d), `r2db_api/postgres.py`): drop
    JUST the `self._closed_db_calls += db_calls` line from `_fold_closed_
    connection_stats`, leaving the `db_wall_ms`/`txn_count` folding
    otherwise intact -- `before["db_calls"]` is read from the connection
    while it is still LIVE in the queue (unaffected by this mutation), so
    this test's own `after["db_calls"] >= before["db_calls"]` assertion is
    the one that goes red on its own (the other two `after` assertions
    above stay green), proving `db_calls` folding is independently
    observed, not merely incidental to the `db_wall_ms`/`txn_count`
    mutation above."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_sleep(0.05)")
        before = pool.platform_stats()
        assert before["db_wall_ms"] > 0
        assert before["txn_count"] > 0
        assert before["db_calls"] > 0
        pool.retire()
        after = pool.platform_stats()
        assert after["db_wall_ms"] >= before["db_wall_ms"]
        assert after["txn_count"] >= before["txn_count"]
        assert after["db_calls"] >= before["db_calls"]
    finally:
        pool.close_all()


def test_role_pool_platform_stats_does_not_decrease_when_liveness_check_kills_a_connection():
    """コードレビュー 2 差し戻し 3 指摘 8: `_liveness_check`'s own `except`
    branch (a real server-side termination, discovered by a failed ping --
    never `retire()`'s own drain loop above, nor a pre-closed dequeue
    below) also folds the dying connection's own accumulated stats into
    the pool's accumulator before closing it -- `platform_stats()` does
    not drop when that path runs.

    mutation M112 (`r2db_api/postgres.py`): drop the `self._fold_closed_
    connection_stats(conn)` call from `_liveness_check`'s own `except`
    branch -- this test's own `after["db_wall_ms"] >= before["db_wall_
    ms"]` assertion goes red (drops to 0, since the terminated
    connection's own totals are lost)."""
    admin = psycopg.connect(_admin_dsn(), autocommit=True)
    try:
        pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_sleep(0.05)")
                dead_pid = conn.info.backend_pid
            before = pool.platform_stats()
            assert before["db_wall_ms"] > 0
            assert before["txn_count"] > 0
            with admin.cursor() as cur:
                cur.execute("SELECT pg_terminate_backend(%s)", [dead_pid])
            with pool.connection() as conn:
                new_pid = conn.info.backend_pid
            assert new_pid != dead_pid
            after = pool.platform_stats()
            assert after["db_wall_ms"] >= before["db_wall_ms"]
            assert after["txn_count"] >= before["txn_count"]
        finally:
            pool.close_all()
    finally:
        admin.close()


def test_role_pool_connection_folds_stats_from_an_already_closed_dequeued_connection():
    """Code review 1 F7(a): a connection dequeued from `_queue` already
    `.closed` (the server closed it; discovered here, before even
    reaching `_liveness_check`'s own round trip) still has its own
    accumulated `db_wall_ms`/`txn_count`/`db_calls` folded into the
    pool's own totals -- `platform_stats()` never drops when that
    connection is discarded and replaced.

    mutation M101 (`r2db_api/postgres.py`): drop the `self._fold_closed_
    connection_stats(conn)` call from the `conn.closed` branch of
    `connection()` -- this test's own `after["db_wall_ms"] >=
    before["db_wall_ms"]` assertion goes red (drops below `before`,
    since the pre-closed connection's own totals vanish on discard)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        conn = pool._connect()  # noqa: SLF001 -- real connection, bypasses connection()
        with conn.cursor() as cur:
            cur.execute("SELECT pg_sleep(0.02)")
        assert conn.db_wall_ms > 0
        conn.close()
        assert conn.closed
        pool._queue.put_nowait(conn)  # noqa: SLF001 -- queue it already-closed, bypassing _liveness_check
        before = pool.platform_stats()
        assert before["db_wall_ms"] > 0  # still "live" (queued) despite being closed
        with pool.connection():
            pass  # dequeues the closed connection, folds it, replaces it
        after = pool.platform_stats()
        assert after["db_wall_ms"] >= before["db_wall_ms"]
        assert after["txn_count"] >= before["txn_count"]
        assert after["db_calls"] >= before["db_calls"]
    finally:
        pool.close_all()


def test_role_pool_connection_does_not_double_fold_when_replacement_connect_fails(monkeypatch):
    """Code review 1 F7(b): when `_liveness_check` reports a connection
    dead (folding and closing it itself, as it already does) and the
    REPLACEMENT `_connect()` call that `connection()` then makes itself
    fails, `connection()`'s own `finally` block must not fold that SAME
    already-folded connection's stats a second time.

    mutation M102 (`r2db_api/postgres.py`): drop the `if conn is not
    already_folded_conn:` guard so `finally` always folds `conn` when
    not recycled -- this test's own `platform_stats()["db_wall_ms"] ==
    pytest.approx(stale_db_wall_ms)` assertion goes red (reads roughly
    double the single-fold value)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        conn = pool._connect()  # noqa: SLF001 -- real connection, bypasses connection()
        with conn.cursor() as cur:
            cur.execute("SELECT pg_sleep(0.02)")
        stale_db_wall_ms = conn.db_wall_ms
        assert stale_db_wall_ms > 0
        pool._queue.put_nowait(conn)  # noqa: SLF001 -- queue it IDLE, real, so _liveness_check runs on it

        def fake_liveness_check(candidate):
            pool._fold_closed_connection_stats(candidate)  # noqa: SLF001
            candidate.close()
            return False

        def fake_connect():
            raise psycopg.OperationalError("R-101 WP-1 test: simulated replacement connect failure")

        monkeypatch.setattr(pool, "_liveness_check", fake_liveness_check)
        monkeypatch.setattr(pool, "_connect", fake_connect)

        with pytest.raises(psycopg.OperationalError):
            with pool.connection():
                pass  # never reached -- _connect() raises before yield
        stats = pool.platform_stats()
        assert stats["db_wall_ms"] == pytest.approx(stale_db_wall_ms)
    finally:
        pool.close_all()


def test_role_pool_platform_stats_counts_one_session_on_first_connect():
    """Completion condition 25: opening one new pooled connection
    increases `platform_stats()`'s own `sessions` by exactly 1 and
    `connect_wall_ms` by more than 0.

    mutation M63 (`r2db_api/postgres.py`): drop the connect-timing
    accumulation from `_RolePool._connect` -- this test's own `connect_
    wall_ms > 0` assertion goes red (stays at 0)."""
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1)
    try:
        before = pool.platform_stats()
        assert before["sessions"] == 0
        with pool.connection():
            pass
        after = pool.platform_stats()
        assert after["sessions"] == 1
        assert after["connect_wall_ms"] > 0
    finally:
        pool.close_all()


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


def test_role_pool_fold_is_lexically_inside_the_stats_lock():
    """Completion condition 26 (守る条件 (b)): `_RolePool.
    _fold_closed_connection_stats`'s three accumulator increments (`self.
    _closed_db_wall_ms += db_wall_ms`, `self._closed_txn_count +=
    txn_count`, `self._closed_db_calls += db_calls`) must be lexically
    inside the SAME `with self._stats_lock:` block. A source-shape pin,
    not a running-thread race: mirroring the peer's own finding for the
    same shape (`MitateDB-api/tests/test_r79_prepared_stats.py`'s own
    `test_platform_stats_fold_is_lexically_inside_the_platform_stats_
    lock`), CPython's GIL does not reliably turn this unguarded accumulate
    into an observable lost update at achievable call rates -- so this
    deterministic AST pin is used instead.

    mutation M64c (`r2db_api/postgres.py`): drop the `with self._stats_
    lock:` around the three accumulator additions in `_fold_closed_
    connection_stats` -- this test's own assertions go red (the three
    `AugAssign` nodes are no longer inside any `with self._stats_lock:`
    block)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(_RolePool._fold_closed_connection_stats)))
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



def test_txn_open_count_counts_only_the_enter_of_transaction():
    """One enter of `with conn.transaction():` raises `txn_open_count` by
    exactly 1, observed from inside the block; leaving the block, a
    `commit()` and a `rollback()` raise it by nothing. `execute_count`
    plus `executemany_count` plus `txn_open_count` is the number of
    statements the connection sent, so an exit that counted would count
    the same transaction twice.

    Dropping the `txn_open_count` increment from `transaction()` in this
    peer's `psycopg_counting.py` turns this test red on
    `assert (0 - 0) == 1` and nothing else is edited (mutation run:
    `1 failed` for each peer, restores verified)."""
    conn = CountingConnection.connect(_admin_dsn(), autocommit=False)
    try:
        start = conn.txn_open_count
        with conn.transaction():
            inside = conn.txn_open_count
        after_exit = conn.txn_open_count
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.commit()
        after_commit = conn.txn_open_count
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        after_rollback = conn.txn_open_count
        assert inside - start == 1
        assert after_exit == inside
        assert after_commit == after_exit
        assert after_rollback == after_commit
    finally:
        conn.close()
