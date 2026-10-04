"""Where `PostgresBackend` and `SQLiteBackend` check a request's execution budget, what a spent budget maps to, and where they do not check.

A request carries one deadline, fixed when the request is accepted. `PostgresBackend` checks it with a clock comparison (no database round trip) before every statement it sends: the connections a request holds carry its deadline for as long as it holds them, and the one statement helper, `_execute`, refuses a spent budget before `cursor.execute` (`SET LOCAL` included). `_timeout_ms` refuses a remaining budget under 1 ms and never returns a bound of 0. It does not check after the last statement, because the next thing the request does is commit and a commit is never refused for time. A failed connection attempt is judged by the clock alone: a spent budget is `LIMIT_EXCEEDED` / `execution_ms`, anything else, an immediate refusal included, stays a storage failure. `SQLiteBackend` checks the same way before every statement (`_execute_statement`), and a progress handler stops a statement that is still running once the budget is spent; the handler is armed for one statement and never covers a commit or a rollback.

Every test here that moves time drives a clock the test owns (`clock`): `time` in `backend_postgres`, `backend_sqlite` and `cell` is replaced by a stand-in whose `monotonic` is that clock, so a PostgreSQL round trip need not land on a chosen side of a real deadline; the statements sent after the clock moves are read off `backend_postgres._execute` (`_Trace`) and off the idle connections' own counters. The exceptions are the SQLite progress-handler tests (`test_sqlite_stops_a_statement_that_is_still_running_when_the_budget_ends`, `test_sqlite_rolls_back_the_transaction_of_a_stopped_statement_with_the_handler_already_removed`, `test_sqlite_lets_a_statement_that_finishes_within_its_budget_finish` and `test_sqlite_removes_the_bound_when_a_statement_ends_so_the_next_request_is_not_cut`), which use the real clock because the handler runs inside SQLite's own statement. Nothing in the product code is there for the tests.

Real PostgreSQL for the `PostgresBackend` tests that take `backend` or `cell`; the tests that take `offline_backend` open no connection, and the SQLite tests need none.

Measured by mutation (61 mutations in the change that put these checks in, each turns the test it names red, every restore verified; 56 name a test in this file, 2 name one in `test_r102_request_scope.py` and 3 one in `test_application_audit.py`). Removing `_execute`'s check together with `_timeout_ms`'s refusal turns red `test_a_request_with_a_spent_budget_sends_no_statement_after_the_pool_checkout[dml]` and both lock-wait tests that expect no statement after the wait; removing `_execute`'s check alone turns red `test_the_set_local_that_opens_a_request_is_checked_by_the_statement_helper`, `test_the_bound_set_again_after_a_lock_wait_is_checked_by_the_statement_helper` and the four between-statement tests (the select after the catalog read, the second operation, the idempotency store, the statement after the DDL). Not putting the deadline on the connections turns red the select test, and leaving it there after the request turns red `test_a_pooled_connection_carries_a_request_deadline_only_while_that_request_holds_it`. Replacing the refusal in `_timeout_ms` by `max(1, ...)` or testing `<= 0` there turns red the under-one-millisecond case of `test_timeout_ms_refuses_under_one_millisecond_remaining_and_never_returns_a_zero_bound`; testing `<= 0` in `_budget_spent` turns red `test_the_statement_helper_refuses_a_request_with_less_than_a_millisecond_left`; returning the constructed bound or one millisecond too many turns red the bound tests. Computing the deadline again after the pool wait turns red `test_the_wait_for_a_connection_counts_against_the_budget`, and not setting the bound again after a lock wait turns red `test_the_wait_for_a_lock_shortens_the_bound_of_the_statements_that_follow`. Dropping the cancel mapping of the opening `SET LOCAL`, of the `SET LOCAL` after a lock wait, or of the batch's record write (and, separately, the `LockNotAvailable` half of each, and the record write's other-driver-error clause) turns red the matching mapping test. Dropping the clock judgment of a failed connection attempt, applying it to every failure, mapping `PoolExhausted` to a storage failure, or asking the pool to wait for the constructed time turns red the matching connection or pool test. Putting the record write after `audit_hook.pre_commit()` again in any of the three schema operations turns red its order test and its cancelled-store test, and for `create_collection` also `test_application_audit.py::test_a_cancelled_schema_record_write_leaves_no_audit_row_because_it_comes_before_the_pre_commit_row`. Calling the untranslated record write in a schema operation turns red its test for a driver error that is not a cancel (and, for all three together, `test_application_audit.py::test_a_failed_schema_record_write_that_is_not_a_cancel_is_a_storage_failure_and_leaves_no_audit_row`). Putting a check after the select or before the commit turns red the two "even if the budget ends right after" tests. SQLite: removing the check before a statement turns red the between-statements, DDL and first-statement tests; a strict `>` threshold, leaving the refused request's transaction open and forgetting the outer deadline when a nested scope ends each turn red their test; removing the progress handler turns red `test_sqlite_stops_a_statement_that_is_still_running_when_the_budget_ends` (the statement then runs to the end, about 5.4 s in that run); arming the handler for the commit or for the rollback, or leaving it armed after a statement (finished or stopped), turns red the matching test. Dropping the rollback of a stopped statement turns red `test_sqlite_stops_a_statement_that_is_still_running_when_the_budget_ends` and `test_sqlite_rolls_back_the_transaction_of_a_stopped_statement_with_the_handler_already_removed`; removing the handler after that rollback instead of before it turns red the second.
"""
from __future__ import annotations

import socket
import threading
import time
import types
from typing import Any, Callable

import psycopg
import pytest

import mitatedb_api.backend_postgres as bp_module
import mitatedb_api.backend_sqlite as sqlite_module
import mitatedb_api.cell as cell_module
from mitatedb_api import FoundationConfig
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.errors import FoundationError, NotFoundError, ResourceLimitError, StorageTransientError
from mitatedb_api.pg_timeouts import ms_from_pg_timeout_text
from mitatedb_api.pool import PoolConnectFailed, PoolExhausted

from .test_postgres import app_a, platform, sessions_for  # noqa: F401 (fixtures)

_WAIT_S = 10.0
_LIMIT = {"limit_class": "execution_ms"}


# ---- the owned clock, and the statements a request sent ---------------------


class _Clock:
    """The time a request is judged against. `now` is whatever the test sets; `expire()` moves it far past any deadline a request of this test carries."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def expire(self) -> None:
        self.now += 3600.0


class _ClockedTime:
    """`time` as a backend or the cell sees it while a test owns the clock: `monotonic` is the clock's, everything else is the real module's."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock

    def monotonic(self) -> float:
        return self._clock.monotonic()

    def __getattr__(self, name: str) -> Any:
        return getattr(time, name)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    owned = _Clock()
    stand_in = _ClockedTime(owned)
    for module in (bp_module, sqlite_module, cell_module):
        monkeypatch.setattr(module, "time", stand_in)
    return owned


class _Trace:
    """The statements `backend_postgres._execute` really sent, in order (a statement it refused is not in the list), and the points where the clock was moved: `expire_after(needle)` moves it once, as soon as a statement containing `needle` has been sent."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
        self.sent: list[str] = []
        self.marks: list[int] = []
        self._needle: str | None = None
        real = bp_module._execute

        def traced(cursor: Any, statement: Any, params: Any = ()) -> Any:
            result = real(cursor, statement, params)
            text = statement.as_string(cursor)
            self.sent.append(text)
            if self._needle is not None and self._needle in text:
                self._needle = None
                self.marks.append(len(self.sent))
                clock.expire()
            return result

        monkeypatch.setattr(bp_module, "_execute", traced)

    def expire_after(self, needle: str) -> None:
        self._needle = needle

    def nothing_sent_after_the_mark(self) -> bool:
        return len(self.marks) == 1 and len(self.sent) == self.marks[0]


def _idle_counts(backend: PostgresBackend) -> dict[str, tuple[int, int]]:
    """Per role: how many connections are idle in its pool and how many statements those connections have executed in their lifetime."""
    counts = {}
    for role, pool in (("developer", backend._developer_pool), ("runtime", backend._runtime_pool)):
        counters = pool.map_idle(lambda conn: conn.execute_count + conn.executemany_count)
        counts[role] = (len(counters), sum(counters))
    return counts


def _bounds(scope: Any) -> set[int]:
    """The `statement_timeout` and `lock_timeout` (ms) in force on every connection the scope holds."""
    found = set()
    for conn in {id(c): c for c in (scope.main, scope.developer) if c is not None}.values():
        with conn.cursor() as cur:
            for setting in ("statement_timeout", "lock_timeout"):
                cur.execute(f"SHOW {setting}")
                found.add(ms_from_pg_timeout_text(cur.fetchone()[0]))
    return found


# ---- the backend and the cell under test --------------------------------------


@pytest.fixture
def backend(app_a: types.SimpleNamespace) -> Any:  # noqa: F811
    one = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    try:
        yield one
    finally:
        one.close()


@pytest.fixture
def offline_backend() -> PostgresBackend:
    """A backend for the tests that never reach a database: it opens no connection until a request borrows one."""
    return PostgresBackend(runtime_dsn="postgresql://runtime@db.example.invalid/app", developer_dsn="postgresql://developer@db.example.invalid/app")


@pytest.fixture
def cell(app_a: types.SimpleNamespace, backend: PostgresBackend, clock: _Clock) -> Any:  # noqa: F811
    one = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend)
    developer, runtime = sessions_for(one, app_a.app_id)
    developer.create_collection("widgets", {"label": "text"})
    runtime.transact([{"type": "insert", "collection": "widgets", "values": {"label": "seed"}}])
    return types.SimpleNamespace(cell=one, developer=developer, runtime=runtime)


def _labels(session: Any) -> list[str]:
    return sorted(row["label"] for row in session.runtime.read("widgets"))


def _insert(label: str) -> dict[str, Any]:
    return {"type": "insert", "collection": "widgets", "values": {"label": label}}


def _warm(backend: PostgresBackend) -> None:
    """One request of every kind, so each pool holds an idle connection."""
    for kind in ("query", "dml", "schema"):
        with backend.request_scope(kind):
            pass


# ---- the first statement of a request ---------------------------------------


@pytest.mark.parametrize("kind", ["query", "dml", "schema"])
def test_a_request_with_a_spent_budget_sends_no_statement_after_the_pool_checkout(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    """A spent request takes an idle connection from the pool and sends nothing on it: not `SET LOCAL`, not any other statement. The pool holds idle connections here, so the checkout cannot be what refuses it."""
    _warm(backend)
    trace = _Trace(monkeypatch, clock)
    before = _idle_counts(backend)
    assert before["developer"][0] >= 1 and before["runtime"][0] >= 1, "the pools hold no idle connection (空振り)"
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope(kind, deadline=clock.now - 1.0):
            pytest.fail("the scope of a request with a spent budget was entered")
    assert exc.value.details == _LIMIT
    assert trace.sent == []
    assert _idle_counts(backend) == before


def test_the_set_local_that_opens_a_request_is_checked_by_the_statement_helper(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_timeout_ms` passes (the budget is still there when the bound is computed) and the clock then moves past the deadline: the first `SET LOCAL` is still not sent. The refusal comes from `_execute`, not from `_timeout_ms`."""
    _warm(backend)
    trace = _Trace(monkeypatch, clock)
    before = _idle_counts(backend)
    real = backend._timeout_ms

    def then_expire(deadline: Any) -> Any:
        value = real(deadline)
        clock.expire()
        return value

    monkeypatch.setattr(backend, "_timeout_ms", then_expire)
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("query", deadline=clock.now + 5.0):
            pytest.fail("the scope was entered")
    assert exc.value.details == _LIMIT
    assert trace.sent == []
    assert _idle_counts(backend) == before


def test_the_statement_helper_refuses_a_request_with_less_than_a_millisecond_left(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_timeout_ms` passes and the clock then moves to 0.977 ms before the deadline: the first `SET LOCAL` is not sent, because a statement bound cannot be less than a millisecond."""
    _warm(backend)
    trace = _Trace(monkeypatch, clock)
    real = backend._timeout_ms
    deadline = clock.now + 5.0

    def then_move_close_to_the_deadline(value: Any) -> Any:
        bound = real(value)
        clock.now = deadline - 0.0009765625
        return bound

    monkeypatch.setattr(backend, "_timeout_ms", then_move_close_to_the_deadline)
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("query", deadline=deadline):
            pytest.fail("the scope was entered")
    assert exc.value.details == _LIMIT
    assert trace.sent == []


def test_a_pooled_connection_carries_a_request_deadline_only_while_that_request_holds_it(backend: PostgresBackend, clock: _Clock) -> None:
    """The deadline sits on the connections of the request that holds them and on no other: a connection that went back to its pool carries none, so the next borrower (or a pool's own maintenance) is not judged by a request that is over."""
    _warm(backend)
    deadline = clock.now + 5.0
    with backend.request_scope("dml", deadline=deadline) as scope:
        assert scope.main.request_deadline == deadline and scope.developer.request_deadline == deadline
    assert [d for d in _idle_deadlines(backend)] and set(_idle_deadlines(backend)) == {None}
    with backend.request_scope("query"):
        pass
    assert set(_idle_deadlines(backend)) == {None}


def _idle_deadlines(backend: PostgresBackend) -> list[Any]:
    found: list[Any] = []
    for pool in (backend._developer_pool, backend._runtime_pool):
        found.extend(pool.map_idle(lambda conn: getattr(conn, "request_deadline", "absent")))
    return found


# ---- the check before every later statement -----------------------------------


def test_a_query_whose_budget_ends_after_the_catalog_read_does_not_send_the_select(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    trace = _Trace(monkeypatch, clock)
    # R-82: a warm cache would answer without a live catalog read, so the read this test stops the clock after is made on an empty one.
    cell.cell._backend._catalog_cache = bp_module._RevisionKeyedCache()
    trace.expire_after('FROM "_mdb_field_types"')
    with pytest.raises(ResourceLimitError) as exc:
        cell.runtime.read("widgets")
    assert exc.value.details == _LIMIT
    assert trace.marks and trace.marks[0] > 0, "statements were sent before the clock moved"
    assert trace.nothing_sent_after_the_mark()
    assert not any('FROM "widgets"' in text for text in trace.sent)


def test_a_mutation_whose_budget_ends_after_its_first_operation_does_not_send_the_second(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    """The statements of a batch are separate statements: the check sits before each, so a request whose budget ends between two operations commits neither."""
    trace = _Trace(monkeypatch, clock)
    trace.expire_after('INSERT INTO "widgets"')
    with pytest.raises(ResourceLimitError) as exc:
        cell.runtime.transact([_insert("a"), _insert("b")])
    assert exc.value.details == _LIMIT
    assert trace.nothing_sent_after_the_mark()
    assert [text for text in trace.sent if text.startswith('INSERT INTO "widgets"')] == [trace.sent[trace.marks[0] - 1]]
    monkeypatch.undo()
    assert _labels(cell) == ["seed"]


def test_a_keyed_mutation_whose_budget_ends_after_its_last_operation_does_not_send_the_idempotency_store(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    """The statement after the last operation of a keyed request is the idempotency record's write, so that is the one point after the last operation where the clock is checked. The refused request leaves no row and no record: the same key sent again is a new attempt, not a replay."""
    trace = _Trace(monkeypatch, clock)
    trace.expire_after('INSERT INTO "widgets"')
    with pytest.raises(ResourceLimitError) as exc:
        cell.runtime.transact([_insert("keyed")], idempotency_key="k-store")
    assert exc.value.details == _LIMIT
    assert trace.nothing_sent_after_the_mark()
    assert not any("_mdb_idempotency" in text and text.startswith("INSERT") for text in trace.sent)
    monkeypatch.undo()
    assert _labels(cell) == ["seed"]
    cell.runtime.transact([_insert("keyed")], idempotency_key="k-store")
    assert _labels(cell) == ["keyed", "seed"]


def test_a_schema_operation_whose_budget_ends_after_its_ddl_sends_no_further_statement_and_leaves_nothing(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    trace = _Trace(monkeypatch, clock)
    trace.expire_after("CREATE TABLE")
    with pytest.raises(ResourceLimitError) as exc:
        cell.developer.create_collection("gadgets", {"label": "text"})
    assert exc.value.details == _LIMIT
    assert trace.nothing_sent_after_the_mark()
    monkeypatch.undo()
    cell.developer.create_collection("gadgets", {"label": "text"})  # a refused request left no table behind: this is not a conflict


def test_a_query_that_finishes_its_last_statement_is_answered_even_if_the_budget_ends_right_after(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    """The clock moves past the deadline just after the select that answers the query. The next thing a query does is commit its read-only transaction, so there is no statement left to refuse: the answer is returned."""
    trace = _Trace(monkeypatch, clock)
    trace.expire_after('FROM "widgets"')
    rows = cell.runtime.read("widgets")
    assert [row["label"] for row in rows] == ["seed"]
    assert trace.marks and trace.nothing_sent_after_the_mark()


def test_a_mutation_that_finishes_its_last_operation_commits_even_if_the_budget_ends_right_after(cell: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    """A mutation without an idempotency key has no statement after its last operation: it commits, and the budget that ended after the last statement does not undo it."""
    trace = _Trace(monkeypatch, clock)
    trace.expire_after('INSERT INTO "widgets"')
    cell.runtime.transact([_insert("late")])
    assert trace.marks and trace.nothing_sent_after_the_mark()
    monkeypatch.undo()
    assert _labels(cell) == ["late", "seed"]


# ---- the bound of the statements ---------------------------------------------


@pytest.mark.parametrize("remaining_s", [0.0009765625, 0.0, -2000.0])
def test_timeout_ms_refuses_under_one_millisecond_remaining_and_never_returns_a_zero_bound(offline_backend: PostgresBackend, clock: _Clock, remaining_s: float) -> None:
    """Less than 1 ms is a spent budget. A bound of 0 would disable `statement_timeout`, and rounding it up to 1 ms would run a statement with a budget that does not exist: neither is returned."""
    with pytest.raises(ResourceLimitError) as exc:
        offline_backend._timeout_ms(clock.now + remaining_s)
    assert exc.value.details == _LIMIT


@pytest.mark.parametrize(("remaining_s", "expected_ms"), [(0.001953125, 1), (0.0029296875, 2), (1.5, 1500), (5.0, 5000)])
def test_timeout_ms_returns_the_whole_milliseconds_that_remain_and_never_more(offline_backend: PostgresBackend, clock: _Clock, remaining_s: float, expected_ms: int) -> None:
    """A deployment whose constructed bound is 5 s and a request with 1.5 s left get 1500 ms, not 5000: the bound is what remained when it was computed, rounded down."""
    bound = offline_backend._timeout_ms(clock.now + remaining_s)
    assert bound == expected_ms
    assert 0 < bound <= remaining_s * 1000
    assert offline_backend._timeout_ms(None) is None


def test_the_scope_sets_a_bound_no_longer_than_what_remained_when_it_opened(backend: PostgresBackend, clock: _Clock) -> None:
    with backend.request_scope("query", deadline=clock.now + 1.5) as scope:
        assert _bounds(scope) == {1500}


def test_the_wait_for_a_connection_counts_against_the_budget(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The budget is fixed before the request asks for a connection and is not computed again afterwards: each pool wait takes 0.625 s here, and what the statements are bounded by is what remains after both. The second wait is also asked for no more than what remained when it began."""
    asked: list[float] = []
    for pool in (backend._developer_pool, backend._runtime_pool):
        real = pool.acquire

        def waiting(timeout: Any = None, _real: Callable[..., Any] = real) -> Any:
            asked.append(timeout)
            conn = _real(timeout=timeout)
            clock.now += 0.625
            return conn

        monkeypatch.setattr(pool, "acquire", waiting)
    with backend.request_scope("query", deadline=clock.now + 2.0) as scope:
        assert _bounds(scope) == {750}
    assert asked == [2.0, 1.375]


# ---- the wait for a lock ------------------------------------------------------


def test_the_wait_for_a_lock_shortens_the_bound_of_the_statements_that_follow(backend: PostgresBackend, clock: _Clock) -> None:
    with backend.request_scope("schema", deadline=clock.now + 2.0) as scope:
        assert _bounds(scope) == {2000}
        clock.now += 0.5  # the wait for a lock
        backend._retime(scope)
        assert _bounds(scope) == {1500}


def test_a_lock_wait_that_used_the_whole_budget_ends_the_request_before_it_sends_another_statement(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    with backend.request_scope("schema", deadline=clock.now + 2.0) as scope:
        trace = _Trace(monkeypatch, clock)
        clock.now += 2.0  # the wait ended exactly at the deadline
        with pytest.raises(ResourceLimitError) as exc:
            backend._retime(scope)
        assert exc.value.details == _LIMIT
        assert trace.sent == []


def test_the_bound_set_again_after_a_lock_wait_is_checked_by_the_statement_helper(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_timeout_ms` passes and the clock moves before the second `SET LOCAL`: it is not sent. The refusal comes from `_execute`."""
    with backend.request_scope("schema", deadline=clock.now + 2.0) as scope:
        trace = _Trace(monkeypatch, clock)
        real = backend._timeout_ms

        def then_expire(deadline: Any) -> Any:
            value = real(deadline)
            clock.expire()
            return value

        monkeypatch.setattr(backend, "_timeout_ms", then_expire)
        with pytest.raises(ResourceLimitError):
            backend._retime(scope)
        assert trace.sent == []


def test_a_real_wait_for_a_lock_that_spends_the_budget_is_followed_by_no_statement(app_a: types.SimpleNamespace, backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Another session holds the application-wide schema lock; the request blocks on it. The clock passes the deadline while it waits and the session lets go: the request is refused and sends no statement after the one that waited."""
    trace = _Trace(monkeypatch, clock)
    holder = psycopg.connect(app_a.developer_dsn, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", [bp_module._SCHEMA_SERIALIZATION_LOCK_KEY])
    outcome: list[BaseException | None] = []

    def wait_for_the_lock() -> None:
        try:
            with backend.request_scope("schema", deadline=clock.now + 5.0) as scope:
                backend.lock_schema(scope=scope)
            outcome.append(None)
        except FoundationError as error:
            outcome.append(error)

    waiter = threading.Thread(target=wait_for_the_lock, daemon=True)
    try:
        waiter.start()
        watching = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            limit = time.time() + _WAIT_S
            while time.time() < limit:
                if watching.execute("SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND NOT granted").fetchone():
                    break
                time.sleep(0.01)
            else:
                pytest.fail("the request never waited for the lock (空振り)")
        finally:
            watching.close()
        clock.expire()
    finally:
        holder.close()
    waiter.join(_WAIT_S)
    assert not waiter.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], ResourceLimitError) and outcome[0].details == _LIMIT
    assert trace.sent and "pg_advisory_xact_lock(%s)" in trace.sent[-1] and "try_" not in trace.sent[-1], trace.sent


# ---- what a spent budget maps to ----------------------------------------------


def _fail_on(monkeypatch: pytest.MonkeyPatch, prefix: str, error: BaseException) -> None:
    """`_execute` raises `error` for the statements that start with `prefix`; every other statement goes through."""
    real = bp_module._execute

    def failing(cursor: Any, statement: Any, params: Any = ()) -> Any:
        if statement.as_string(cursor).startswith(prefix):
            raise error
        return real(cursor, statement, params)

    monkeypatch.setattr(bp_module, "_execute", failing)


_CANCELS = [psycopg.errors.QueryCanceled("synthetic cancel"), psycopg.errors.LockNotAvailable("synthetic lock timeout")]


@pytest.mark.parametrize("cancel", _CANCELS, ids=lambda e: type(e).__name__)
def test_a_cancelled_set_local_when_a_request_opens_is_execution_ms(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, cancel: BaseException) -> None:
    _fail_on(monkeypatch, "SET LOCAL", cancel)
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("query", deadline=time.monotonic() + 5.0):
            pytest.fail("the scope was entered")
    assert exc.value.details == _LIMIT


def test_a_set_local_that_fails_for_any_other_reason_is_still_a_storage_failure(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    _fail_on(monkeypatch, "SET LOCAL", psycopg.errors.OperationalError("synthetic connection loss"))
    with pytest.raises(StorageTransientError):
        with backend.request_scope("query", deadline=time.monotonic() + 5.0):
            pytest.fail("the scope was entered")


@pytest.mark.parametrize("cancel", _CANCELS, ids=lambda e: type(e).__name__)
def test_a_cancelled_set_local_after_a_lock_wait_is_execution_ms(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, cancel: BaseException) -> None:
    with backend.request_scope("schema", deadline=time.monotonic() + 5.0) as scope:
        _fail_on(monkeypatch, "SET LOCAL", cancel)
        with pytest.raises(ResourceLimitError) as exc:
            backend._retime(scope)
        assert exc.value.details == _LIMIT


def test_a_set_local_after_a_lock_wait_that_fails_for_any_other_reason_is_still_a_storage_failure(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    with backend.request_scope("schema", deadline=time.monotonic() + 5.0) as scope:
        _fail_on(monkeypatch, "SET LOCAL", psycopg.errors.OperationalError("synthetic connection loss"))
        with pytest.raises(StorageTransientError):
            backend._retime(scope)


@pytest.mark.parametrize("cancel", _CANCELS, ids=lambda e: type(e).__name__)
def test_a_cancelled_idempotency_record_write_of_a_batch_is_execution_ms(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, cancel: BaseException) -> None:
    _fail_on(monkeypatch, 'INSERT INTO "_mdb_idempotency"', cancel)
    with backend.request_scope("dml", deadline=time.monotonic() + 5.0) as scope:
        with pytest.raises(ResourceLimitError) as exc:
            backend.record_idempotency("k", "digest", "{}", 1, scope=scope)
        assert exc.value.details == _LIMIT


@pytest.mark.parametrize("failure", [psycopg.errors.DeadlockDetected("synthetic deadlock"), psycopg.errors.SerializationFailure("synthetic serialization failure"), psycopg.errors.OperationalError("synthetic connection loss")], ids=lambda e: type(e).__name__)
def test_any_other_failure_of_an_idempotency_record_write_of_a_batch_is_a_storage_failure(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, failure: BaseException) -> None:
    _fail_on(monkeypatch, 'INSERT INTO "_mdb_idempotency"', failure)
    with backend.request_scope("dml", deadline=time.monotonic() + 5.0) as scope:
        with pytest.raises(StorageTransientError):
            backend.record_idempotency("k", "digest", "{}", 1, scope=scope)


# ---- the pool wait and the connection attempt ----------------------------------


def _acquire_that(monkeypatch: pytest.MonkeyPatch, backend: PostgresBackend, failure: BaseException, *, expire: _Clock | None = None) -> list[Any]:
    """Both pools' `acquire` raises `failure` (after moving the clock past every deadline when `expire` is given), recording what it was asked to wait."""
    asked: list[Any] = []

    def failing(timeout: Any = None) -> Any:
        asked.append(timeout)
        if expire is not None:
            expire.expire()
        raise failure

    for pool in (backend._developer_pool, backend._runtime_pool):
        monkeypatch.setattr(pool, "acquire", failing)
    return asked


def test_a_connection_attempt_that_fails_after_the_budget_is_spent_is_execution_ms(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """A destination that does not answer shows up as a connection attempt that times out, and by then the budget is spent: the clock alone decides, so it is `LIMIT_EXCEEDED` and not a storage failure."""
    _acquire_that(monkeypatch, backend, PoolConnectFailed("synthetic"), expire=clock)
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("query", deadline=clock.now + 5.0):
            pytest.fail("the scope was entered")
    assert exc.value.details == _LIMIT


def test_a_connection_attempt_that_fails_with_budget_left_is_a_storage_failure(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """An immediate refusal leaves the budget where it was: it is `SERVICE_UNAVAILABLE`, whatever the budget."""
    _acquire_that(monkeypatch, backend, PoolConnectFailed("synthetic"))
    with pytest.raises(StorageTransientError):
        with backend.request_scope("query", deadline=clock.now + 5.0):
            pytest.fail("the scope was entered")


def test_a_database_that_refuses_the_connection_at_once_is_a_storage_failure_not_a_spent_budget() -> None:
    """The real thing, with no clock of the test's: nothing listens on the port, the connection is refused immediately, the request has 5 s left."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    refused = PostgresBackend(runtime_dsn=f"postgresql://runtime@127.0.0.1:{port}/app", developer_dsn=f"postgresql://developer@127.0.0.1:{port}/app")
    try:
        with pytest.raises(StorageTransientError):
            with refused.request_scope("query", deadline=time.monotonic() + 5.0):
                pytest.fail("the scope was entered")
    finally:
        refused.close()


def test_a_pool_wait_that_ran_out_is_execution_ms_whatever_the_clock_says(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    _acquire_that(monkeypatch, backend, PoolExhausted("synthetic"))
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("query", deadline=clock.now + 5.0):
            pytest.fail("the scope was entered")
    assert exc.value.details == _LIMIT


@pytest.mark.parametrize(("deadline_offset", "expected_wait"), [(5.0, 5.0), (0.25, 0.25), (None, None)])
def test_the_pool_is_asked_to_wait_no_longer_than_what_remains(backend: PostgresBackend, clock: _Clock, monkeypatch: pytest.MonkeyPatch, deadline_offset: float | None, expected_wait: float | None) -> None:
    asked = _acquire_that(monkeypatch, backend, PoolExhausted("synthetic"))
    deadline = None if deadline_offset is None else clock.now + deadline_offset
    with pytest.raises(ResourceLimitError):
        with backend.request_scope("query", deadline=deadline):
            pytest.fail("the scope was entered")
    assert asked == [expected_wait]


# ---- the order of a schema operation's last statements -------------------------


class _Hook:
    """What a schema operation's audit hook is to the backend: `pre_commit()` writes the durable `allow` row on a connection of its own."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def pre_commit(self) -> None:
        self.events.append("pre_commit")

    def commit_failed(self) -> None:
        self.events.append("commit_failed")


def _create(backend: PostgresBackend, name: str) -> None:
    with backend.request_scope("schema") as scope:
        backend.create_collection(name, {"label": "text"}, scope=scope)


def _schema_operation(kind: str, backend: PostgresBackend, hook: _Hook) -> Callable[[Any], Any]:
    """The schema operation `kind` (one of the three that carry an idempotency record) as a call that takes a scope; `add_field` and `alter_field_constraints` find their collection already there."""
    record = ("k-" + kind, "digest", 1, "req-" + kind)
    if kind == "create_collection":
        return lambda scope: backend.create_collection("gadgets", {"label": "text"}, audit_hook=hook, idempotency_record=record, scope=scope)
    _create(backend, "things")
    if kind == "add_field":
        return lambda scope: backend.add_field("things", "extra", "text", audit_hook=hook, idempotency_record=record, scope=scope)
    return lambda scope: backend.alter_field_constraints("things", "label", nullable=False, audit_hook=hook, idempotency_record=record, scope=scope)


def _left_nothing(kind: str, backend: PostgresBackend) -> bool:
    """Whether the schema operation `kind` changed nothing that a later request can see."""
    with backend.request_scope("schema") as scope:
        if kind == "create_collection":
            try:
                backend.field_domains("gadgets", scope=scope)
            except NotFoundError:
                return True
            return False
        if kind == "add_field":
            return "extra" not in backend.field_types("things", scope=scope)
        return backend.field_constraints("things", scope=scope)["label"]["nullable"] is True


_SCHEMA_OPERATIONS = ["create_collection", "add_field", "alter_field_constraints"]


@pytest.mark.parametrize("kind", _SCHEMA_OPERATIONS)
def test_a_schema_operation_stores_its_idempotency_record_before_the_pre_commit_row(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    """Store, then `pre_commit`, then COMMIT, as a batch does: once the audit row is durable the only statement left is the commit, so a statement cancelled by its bound can no longer leave an `allow` row for data that never committed."""
    events: list[str] = []
    operation = _schema_operation(kind, backend, _Hook(events))
    real = backend._write_idempotency_row

    def storing(conn: Any, key: Any, digest: Any, response_json: Any, now_ms: Any) -> Any:
        events.append("store")
        return real(conn, key, digest, response_json, now_ms)

    monkeypatch.setattr(backend, "_write_idempotency_row", storing)
    with backend.request_scope("schema") as scope:
        operation(scope)
    assert events == ["store", "pre_commit"]
    assert not _left_nothing(kind, backend), "the operation did not take effect (空振り)"


@pytest.mark.parametrize("kind", _SCHEMA_OPERATIONS)
def test_a_cancelled_idempotency_record_write_of_a_schema_operation_never_reaches_the_audit_hook(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    events: list[str] = []
    operation = _schema_operation(kind, backend, _Hook(events))
    monkeypatch.setattr(backend, "_write_idempotency_row", lambda *args: (_ for _ in ()).throw(psycopg.errors.QueryCanceled("synthetic cancel")))
    with pytest.raises(ResourceLimitError) as exc:
        with backend.request_scope("schema") as scope:
            operation(scope)
    assert exc.value.details == _LIMIT
    assert events == []
    assert _left_nothing(kind, backend)


@pytest.mark.parametrize("failure", [psycopg.errors.DiskFull("synthetic disk full"), psycopg.errors.OperationalError("synthetic connection loss")], ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("kind", _SCHEMA_OPERATIONS)
def test_any_other_failure_of_an_idempotency_record_write_of_a_schema_operation_is_a_storage_failure_and_never_reaches_the_audit_hook(backend: PostgresBackend, monkeypatch: pytest.MonkeyPatch, kind: str, failure: BaseException) -> None:
    events: list[str] = []
    operation = _schema_operation(kind, backend, _Hook(events))
    monkeypatch.setattr(backend, "_write_idempotency_row", lambda *args: (_ for _ in ()).throw(failure))
    with pytest.raises(StorageTransientError):
        with backend.request_scope("schema") as scope:
            operation(scope)
    assert events == []
    assert _left_nothing(kind, backend)


# ---- SQLite -------------------------------------------------------------------


def _sqlite_with_widgets() -> SQLiteBackend:
    backend = SQLiteBackend()
    with backend.request_scope("schema") as scope:
        backend.create_collection("widgets", {"label": "text"}, scope=scope)
    return backend


def _sqlite_rows(backend: SQLiteBackend) -> int:
    return backend._db.execute("SELECT count(*) FROM widgets").fetchone()[0]


@pytest.mark.parametrize("remaining_s", [0.0009765625, 0.0, -1.0])
def test_sqlite_refuses_a_request_with_less_than_a_millisecond_left_before_its_first_statement(clock: _Clock, remaining_s: float) -> None:
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + remaining_s) as scope:
        with pytest.raises(ResourceLimitError) as exc:
            backend.begin(scope=scope)
        assert exc.value.details == _LIMIT
    assert not backend._db.in_transaction


def test_sqlite_sends_a_statement_with_a_millisecond_or_more_left(clock: _Clock) -> None:
    """The threshold is on the right side: 1.953 ms left is not a spent budget."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 0.001953125) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        backend.commit(scope=scope)
    assert _sqlite_rows(backend) == 1


def test_sqlite_refuses_the_next_statement_of_a_request_whose_budget_ends_between_two_statements(clock: _Clock) -> None:
    """The second insert is not sent, and the refusal rolls the request's open transaction back: nothing of the first insert is left for the next request to see."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 5.0) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        assert _sqlite_rows(backend) == 1, "the first insert was not sent (空振り)"
        clock.expire()
        with pytest.raises(ResourceLimitError) as exc:
            backend.insert_in_transaction("widgets", ["label"], ["b"], scope=scope)
        assert exc.value.details == _LIMIT
        assert not backend._db.in_transaction
    assert _sqlite_rows(backend) == 0


def test_sqlite_refuses_the_ddl_of_a_request_whose_budget_ends_after_its_begin(clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = SQLiteBackend()
    real = backend._begin_pseudo_tx

    def begin_then_expire() -> None:
        real()
        clock.expire()

    monkeypatch.setattr(backend, "_begin_pseudo_tx", begin_then_expire)
    with backend.request_scope("schema", deadline=clock.now + 5.0) as scope:
        with pytest.raises(ResourceLimitError) as exc:
            backend.create_collection("widgets", {"label": "text"}, scope=scope)
        assert exc.value.details == _LIMIT
    assert not backend._db.in_transaction
    assert backend._db.execute("PRAGMA table_info(widgets)").fetchall() == [], "the refused request left a table behind"


def test_sqlite_a_nested_scope_gives_the_outer_requests_deadline_back_when_it_ends(clock: _Clock) -> None:
    """An internal read with no deadline inside a request does not leave the request unbounded: when its scope ends the request's own deadline is the one in force again."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 5.0) as outer:
        with backend.request_scope("query"):
            backend._execute_statement("SELECT 1", fetch=True)
        clock.expire()
        with pytest.raises(ResourceLimitError) as exc:
            backend.begin(scope=outer)
        assert exc.value.details == _LIMIT


def test_sqlite_answers_a_read_whose_budget_ends_after_its_last_statement(clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read has no statement after its select: the clock moving past the deadline once the select is done does not turn the answer into a refusal."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 5.0) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        backend.commit(scope=scope)
    real = backend._execute_statement
    sent: list[str] = []

    def then_expire(statement: str, params: Any = (), *, fetch: bool = False) -> Any:
        result = real(statement, params, fetch=fetch)
        sent.append(statement)
        clock.expire()
        return result

    monkeypatch.setattr(backend, "_execute_statement", then_expire)
    with backend.request_scope("query", deadline=clock.now + 5.0) as scope:
        rows = backend.read("widgets", ["label"], [], None, 10, scope=scope)
    assert rows == [{"label": "a"}] and len(sent) == 1


_LONG_STATEMENT = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 80000000) SELECT count(*) FROM c"


def _stop_a_long_statement_inside_a_transaction(budget_s: float) -> tuple[SQLiteBackend, ResourceLimitError, float]:
    """Real clock: a request opens a transaction, inserts a row, then sends a statement that outlasts its budget. Returns the backend, the refusal and how long the stop took, after the request's scope ended."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=time.monotonic() + budget_s) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        assert backend._db.in_transaction and _sqlite_rows(backend) == 1, "the request has no open transaction with a row in it (空振り)"
        started = time.monotonic()
        with pytest.raises(ResourceLimitError) as exc:
            backend._execute_statement(_LONG_STATEMENT, fetch=True)
        elapsed = time.monotonic() - started
    return backend, exc.value, elapsed


def test_sqlite_stops_a_statement_that_is_still_running_when_the_budget_ends() -> None:
    """Real clock: eighty million rows of a recursive query take seconds, the request has a quarter of a second. The statement is stopped, the request refused, the transaction the request had open is rolled back (the row it inserted is gone), and the stop takes about the budget, not the statement's own time."""
    backend, refusal, elapsed = _stop_a_long_statement_inside_a_transaction(0.25)
    assert refusal.details == _LIMIT
    assert elapsed < 3.0, elapsed
    assert not backend._db.in_transaction
    assert _sqlite_rows(backend) == 0


def test_sqlite_rolls_back_the_transaction_of_a_stopped_statement_with_the_handler_already_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The interval is 1, so the handler looks at the clock on every instruction and would stop the rollback too if it were still armed when the rollback ran: the statement would end in SQLite's own interrupt error and the transaction would stay open. It ends in the refusal, and the transaction is closed."""
    monkeypatch.setattr(sqlite_module, "_PROGRESS_INTERVAL_OPS", 1)
    backend, refusal, _ = _stop_a_long_statement_inside_a_transaction(0.2)
    assert refusal.details == _LIMIT
    assert not backend._db.in_transaction
    assert _sqlite_rows(backend) == 0


def test_sqlite_lets_a_statement_that_finishes_within_its_budget_finish() -> None:
    """The handler stops only what outlasts the budget: a short statement under a generous one returns its answer."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("query", deadline=time.monotonic() + 30.0):
        (row,) = backend._execute_statement("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 200000) SELECT count(*) FROM c", fetch=True)
    assert row[0] == 200000


@pytest.mark.parametrize("how_it_ended", ["finished", "stopped"])
def test_sqlite_removes_the_bound_when_a_statement_ends_so_the_next_request_is_not_cut(how_it_ended: str) -> None:
    """A statement that finished and one that was stopped leave no handler behind: a statement of a request with no deadline runs for as long as it needs, even after the deadline of the request before it has long passed."""
    backend = _sqlite_with_widgets()
    with backend.request_scope("query", deadline=time.monotonic() + 0.1):
        if how_it_ended == "stopped":
            with pytest.raises(ResourceLimitError):
                backend._execute_statement(_LONG_STATEMENT, fetch=True)
        else:
            backend._execute_statement("SELECT 1", fetch=True)
    time.sleep(0.15)
    with backend.request_scope("query"):
        (row,) = backend._execute_statement("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 3000000) SELECT count(*) FROM c", fetch=True)
    assert row[0] == 3000000


def test_sqlite_commits_a_request_whose_budget_ended_right_after_its_last_statement(clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The progress handler looks at the clock every instruction here (the interval is 1), so a handler that were armed for the commit would stop it: it is not, and the row is committed."""
    monkeypatch.setattr(sqlite_module, "_PROGRESS_INTERVAL_OPS", 1)
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 5.0) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        clock.expire()
        backend.commit(scope=scope)
    assert _sqlite_rows(backend) == 1
    assert not backend._db.in_transaction


def test_sqlite_rolls_back_a_request_whose_budget_ended_without_the_handler_in_the_way(clock: _Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same for a rollback: the interval is 1 and the budget has ended, and the rollback still undoes the insert."""
    monkeypatch.setattr(sqlite_module, "_PROGRESS_INTERVAL_OPS", 1)
    backend = _sqlite_with_widgets()
    with backend.request_scope("dml", deadline=clock.now + 5.0) as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        clock.expire()
        backend.rollback(scope=scope)
    assert _sqlite_rows(backend) == 0
    assert not backend._db.in_transaction


def test_sqlite_statements_of_a_request_with_no_deadline_are_not_checked(clock: _Clock) -> None:
    backend = _sqlite_with_widgets()
    clock.expire()
    with backend.request_scope("dml") as scope:
        backend.begin(scope=scope)
        backend.insert_in_transaction("widgets", ["label"], ["a"], scope=scope)
        backend.commit(scope=scope)
    assert _sqlite_rows(backend) == 1
