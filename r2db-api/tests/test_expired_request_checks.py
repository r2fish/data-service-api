"""Where `PostgresCell` and the in-memory `ApplicationCell` check a request's execution budget, what a spent budget maps to, and where they do not check.

A request carries one deadline, fixed when the request is accepted. `PostgresCell` checks it with a clock comparison (no database round trip) at the points where the next thing the request does is send a statement: the `BEGIN` of the outermost transaction and the `SAVEPOINT` of a nested one (`_transaction`), and every statement sent through `_run`. It does not check after the last statement, because the next thing the request does is commit and a commit is never refused for time. `_timeout_ms` refuses a remaining budget under 1 ms and never returns a bound of 0. The pool wait and a new connection are bounded by the remaining budget, and a failed acquisition is judged by the clock alone: a spent budget is `LIMIT_EXCEEDED` / `execution_ms`, anything else keeps the failure it had.

Every test that carries a deadline, except the two pool-wait tests, drives a clock the test owns (`_Request.clock`, the `clock=` argument of the cell methods; the two pool-wait tests use the real clock and a real wait): a PostgreSQL round trip cannot be made to land on a chosen side of a real deadline, but the clock can be moved at an exact point (`_Request.expire`, called from a wrapper around the function that precedes the point under test) and the statements sent after that point are read off the connection's own counters (`_Meter`). Nothing in the product code is there for the tests.

Real PostgreSQL for the `PostgresCell` and `_RolePool` tests; the `ApplicationCell` tests need none.

Measured by mutation (41 mutations, each turns its named test red; every restore verified). Replacing `_transaction(conn)` with `conn.transaction()` at one of the three outermost `BEGIN` sites turns `test_the_check_before_the_outermost_begin_is_its_own_check` red for that method alone, and at one of the four `SAVEPOINT` sites turns `test_a_nested_transaction_is_not_opened_once_the_budget_is_spent` red for that site alone. Removing the check from `_run` turns red the three tests that expect no statement after the clock moves (`..._does_not_send_the_select`, `..._does_not_send_its_write`, `..._does_not_send_the_idempotency_store`) and the lock-wait test; not attaching the budget to the connection, or leaving it there after the checkout, turns red `..._does_not_send_the_select` and `test_a_pooled_connection_carries_a_request_budget_only_while_that_request_holds_it`. Removing `_timeout_ms`'s refusal (and flooring its bound at 1) turns the under-one-millisecond test red, and returning the full `execution_ms` as the bound turns the bound test red. Restoring the old threshold (`clock() > deadline`) turns red the `0.5` case of `test_the_deadline_check_refuses_under_one_millisecond_remaining` and the in-memory one-millisecond test; putting a check back after the select, after the last operation of a mutation without a key, or after the last operation of an in-memory query, mutation or schema operation turns the matching "still succeeds" or "not after the last" test red. Taking the pool wait's budget judgment out, letting the wait ignore the remaining budget, judging every failed attempt as `LIMIT_EXCEEDED`, or dropping the judgment from any of the three connection sites (a new connection, a closed one, a dead one) turns the matching pool or connection test red. Computing the deadline again after the pool checkout in `query`, `transact` or `apply_schema` turns `test_the_wait_for_a_pooled_connection_counts_against_the_budget` red for that method. Removing the in-memory `ApplicationCell.apply_schema` check before its operation turns `test_the_in_memory_backend_refuses_under_one_millisecond_remaining[apply_schema]` red, and moving it behind the idempotency lookup turns `test_the_in_memory_schema_operation_refuses_a_replay_whose_budget_is_spent` red. Setting the timeouts again after the wait for an entity lock turns `test_the_wait_for_a_lock_is_followed_by_a_clock_check_and_no_second_bound` red.
"""
from __future__ import annotations

import re
import threading
import time
import types
from contextlib import contextmanager
from typing import Any, Callable

import psycopg
import pytest

from r2db_api import postgres as postgres_module
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell, _RequestBudget, _RolePool
from r2db_api.structured import ApplicationCell

from test_postgres import _admin_dsn, _drop_entity_phrase, app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()
_WAIT_S = 10.0


# ---- the owned clock, and the statements a request sent ---------------------


class _Request:
    """One request's budget under a clock the test owns: `deadline` is fixed at `start + execution_ms`, and `expire()` moves the clock a second past it (and marks how many statements the request had sent by then, when a `_Meter` is attached)."""

    def __init__(self, meter: "_Meter | None" = None, limits: ResourceLimits = LIMITS, start: float = 1000.0) -> None:
        self.limits = limits
        self.now = start
        self.deadline = start + limits.execution_ms / 1000
        self.meter = meter

    def clock(self) -> float:
        return self.now

    def expire(self) -> None:
        if self.meter is not None:
            self.meter.mark()
        self.now = self.deadline + 1.0

    def expire_without_mark(self) -> None:
        self.now = self.deadline + 1.0

    def budget(self) -> _RequestBudget:
        return _RequestBudget(self.limits, self.deadline, self.clock)


def _sent(conn: Any) -> int:
    return conn.execute_count + conn.executemany_count + conn.txn_open_count


class _Meter:
    """For each pool checkout a cell makes: the statements sent on the checked-out connection while it was held (`sent`, one entry per checkout, counted after the pool's own liveness ping), and the count at each `mark()` (`marks`)."""

    def __init__(self, cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
        self.sent: list[int] = []
        self.marks: list[int] = []
        self._conn: Any = None
        self._base = 0
        for handle in (cell._runtime, cell._developer):
            monkeypatch.setattr(handle, "connection", self._metered(handle.connection))

    def _metered(self, original: Callable[..., Any]) -> Callable[..., Any]:
        meter = self

        @contextmanager
        def connection(budget: Any = None) -> Any:
            with original(budget) as conn:
                meter._conn, meter._base = conn, _sent(conn)
                try:
                    yield conn
                finally:
                    meter.sent.append(_sent(conn) - meter._base)

        return connection

    def mark(self) -> None:
        self.marks.append(_sent(self._conn) - self._base)

    def nothing_sent_after_the_mark(self) -> bool:
        return len(self.marks) == 1 and len(self.sent) == 1 and self.sent[0] == self.marks[0]


def _wrap(monkeypatch: pytest.MonkeyPatch, target: Any, name: str, *, before: Callable[[], None] | None = None, after: Callable[[], None] | None = None) -> None:
    """Replaces `target.<name>` with a call to the real one that runs `before` ahead of it and `after` behind it."""
    real = getattr(target, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if before is not None:
            before()
        result = real(*args, **kwargs)
        if after is not None:
            after()
        return result

    monkeypatch.setattr(target, name, wrapper)


def _wrap_run(monkeypatch: pytest.MonkeyPatch, *, after_statement: Callable[[str], bool], then: Callable[[], None]) -> list[str]:
    """Wraps the single execution choke point: every statement's text is appended to the returned list as it completes, and `then()` runs once a statement for which `after_statement(text)` is true has completed."""
    seen: list[str] = []
    real = postgres_module._run

    def run(cursor: Any, statement: Any, params: Any = ()) -> None:
        real(cursor, statement, params)
        text = statement.as_string(cursor)
        seen.append(text)
        if after_statement(text):
            then()

    monkeypatch.setattr(postgres_module, "_run", run)
    return seen


# ---- the cell under test ------------------------------------------------------


_METHODS = ("query", "transact", "apply_schema")


def _prepare(cell: PostgresCell) -> None:
    cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"], "field_types": {"label": "string"}}, developer=True, limits=LIMITS)
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "seed"}}], LIMITS)


def _call(cell: PostgresCell, method: str, request: _Request) -> Any:
    """One request of each kind, under `request`'s deadline and clock."""
    if method == "query":
        return cell.query("widgets", select=["id", "label"], where=[], page_size=10, limits=request.limits, deadline=request.deadline, clock=request.clock)
    if method == "transact":
        return cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], request.limits, deadline=request.deadline, clock=request.clock)
    return cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "extra"}, developer=True, limits=request.limits, deadline=request.deadline, clock=request.clock)


def _keyed_transact(cell: PostgresCell, request: _Request, key: str) -> Any:
    ops = [{"operation": "insert", "values": {"label": "keyed"}}]
    return cell.transact("widgets", ops, request.limits, deadline=request.deadline, clock=request.clock, plan_request={"entity": "widgets", "operations": ops}, idempotency_key=key)


def _row_count(cell: PostgresCell) -> int:
    return len(cell.query("widgets", select=["id"], where=[], page_size=100, limits=LIMITS).items)


def _is_budget_refusal(exc: FoundationError) -> bool:
    return exc.code == "LIMIT_EXCEEDED" and exc.details["limit_class"] == "execution_ms" and exc.details["resource"] == "execution_ms"


@pytest.fixture
def cell(app_a: types.SimpleNamespace) -> Any:  # noqa: F811
    one = make_cell(app_a)
    try:
        _prepare(one)
        yield one
    finally:
        one.close()


# ---- the check before the statement that opens a transaction ------------------


@pytest.mark.parametrize("method", _METHODS)
def test_a_request_with_a_spent_budget_sends_no_statement_after_the_pool_checkout(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    """An already-spent request takes its pool checkout and then sends nothing: not the `BEGIN`, not `SET LOCAL`."""
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    request.expire_without_mark()
    with pytest.raises(FoundationError) as exc:
        _call(cell, method, request)
    assert _is_budget_refusal(exc.value)
    assert meter.sent == [0]


@pytest.mark.parametrize("method", _METHODS)
def test_the_check_before_the_outermost_begin_is_its_own_check(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    """`_timeout_ms` passes (the budget is still there when the bound is computed) and the clock then moves past the deadline: the `BEGIN` is still not sent. The refusal comes from `_transaction`, not from `_timeout_ms`."""
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    _wrap(monkeypatch, cell, "_timeout_ms", after=request.expire)
    with pytest.raises(FoundationError) as exc:
        _call(cell, method, request)
    assert _is_budget_refusal(exc.value)
    assert meter.marks == [0], "the clock moved after `_timeout_ms` and before any statement"
    assert meter.sent == [0]


# ---- the check before every statement `_run` sends -----------------------------


def test_a_query_whose_budget_ends_after_the_catalog_read_does_not_send_the_select(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    _wrap(monkeypatch, cell, "_load_catalog", after=request.expire)
    with pytest.raises(FoundationError) as exc:
        _call(cell, "query", request)
    assert _is_budget_refusal(exc.value)
    assert meter.marks and meter.marks[0] > 0, "statements were sent before the clock moved"
    assert meter.nothing_sent_after_the_mark()


def test_a_mutation_whose_budget_ends_after_the_catalog_read_does_not_send_its_write(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _row_count(cell)
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    _wrap(monkeypatch, cell, "_load_catalog", after=request.expire)
    with pytest.raises(FoundationError) as exc:
        _call(cell, "transact", request)
    assert _is_budget_refusal(exc.value)
    assert meter.marks and meter.marks[0] > 0
    assert meter.nothing_sent_after_the_mark()
    monkeypatch.undo()
    assert _row_count(cell) == before


def test_a_keyed_mutation_whose_budget_ends_after_its_last_operation_does_not_send_the_idempotency_store(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
    """The statement after the last operation of a keyed request is the idempotency record's write, so that is the one point after the last operation where the clock is checked. The refused request leaves no record: the same key sent again is a new attempt, not a replay."""
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    _wrap(monkeypatch, cell, "_apply", after=request.expire)
    with pytest.raises(FoundationError) as exc:
        _keyed_transact(cell, request, "k-store")
    assert _is_budget_refusal(exc.value)
    assert meter.nothing_sent_after_the_mark()
    monkeypatch.undo()
    again = _keyed_transact(cell, _Request(), "k-store")
    assert again.replayed is False and again.affected == 1


def test_the_wait_for_a_lock_is_followed_by_a_clock_check_and_no_second_bound(cell: PostgresCell, app_a: types.SimpleNamespace, platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """A schema operation waits for the application-wide schema lock while another session holds it. The clock passes the deadline during the wait: the next statement is not sent, and the request does not read the budget again to set a new bound (`SET LOCAL` was sent twice, at the start, and not again)."""
    for expire in (True, False):
        meter = _Meter(cell, monkeypatch)
        request = _Request(meter)
        seen = _wrap_run(monkeypatch, after_statement=lambda text: False, then=lambda: None)
        _wrap(monkeypatch, cell, "_schema_serialization_lock", after=meter.mark)
        field = "waited_expired" if expire else "waited_on_time"
        outcome: list[Any] = []

        def run() -> None:
            try:
                outcome.append(cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": field}, developer=True, limits=request.limits, deadline=request.deadline, clock=request.clock))
            except FoundationError as error:
                outcome.append(error)

        holder = psycopg.connect(app_a.developer_dsn, autocommit=True)
        try:
            holder.execute("SELECT pg_advisory_lock(%s)", [postgres_module._SCHEMA_SERIALIZATION_ADVISORY_LOCK_KEY])
            worker = threading.Thread(target=run)
            worker.start()
            deadline = time.monotonic() + _WAIT_S
            while not _advisory_lock_waiters(platform.admin_dsn, app_a.database):
                assert time.monotonic() < deadline, "the request never reached the lock wait"
                time.sleep(0.02)
            if expire:
                request.expire_without_mark()
            holder.execute("SELECT pg_advisory_unlock(%s)", [postgres_module._SCHEMA_SERIALIZATION_ADVISORY_LOCK_KEY])
            worker.join(timeout=_WAIT_S)
        finally:
            holder.close()
        assert not worker.is_alive()
        (result,) = outcome
        set_local = [text for text in seen if text.startswith("SET LOCAL")]
        assert len(set_local) == 2, "one `statement_timeout` and one `lock_timeout`, set before the wait"
        if expire:
            assert isinstance(result, FoundationError) and _is_budget_refusal(result)
            assert meter.nothing_sent_after_the_mark()
        else:
            assert not isinstance(result, Exception), result
        monkeypatch.undo()


def _advisory_lock_waiters(admin_dsn: str, database: str) -> int:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND wait_event = 'advisory' AND pid <> pg_backend_pid()", [database])
            return cur.fetchone()[0]


# ---- the check before each nested transaction -----------------------------------


_NESTED_SITES = ("_idempotency_lookup", "_idempotency_reserve", "_load_field_constraints", "_clear_field_constraints")


@pytest.mark.parametrize("site", _NESTED_SITES)
def test_a_nested_transaction_is_not_opened_once_the_budget_is_spent(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch, site: str) -> None:
    """Each of the four functions that open a nested transaction (a `SAVEPOINT`) begins with that transaction. The clock moves just before the function is called: the `SAVEPOINT` is not sent. The next statement in each function would be refused too, so the statement count after the move is what tells the two checks apart."""
    drop_phrase = _drop_entity_phrase(cell, "widgets") if site == "_clear_field_constraints" else None
    meter = _Meter(cell, monkeypatch)
    request = _Request(meter)
    _wrap(monkeypatch, cell, site, before=request.expire)
    with pytest.raises(FoundationError) as exc:
        if drop_phrase is not None:
            operation = {"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_phrase}
            cell.apply_schema(operation, developer=True, limits=request.limits, deadline=request.deadline, clock=request.clock)
        elif site == "_load_field_constraints":
            _call(cell, "transact", request)
        else:
            _keyed_transact(cell, request, f"k-{site}")
    assert _is_budget_refusal(exc.value)
    assert meter.marks and meter.marks[0] > 0
    assert meter.nothing_sent_after_the_mark()


@pytest.mark.parametrize("method", _METHODS)
def test_a_pooled_connection_carries_a_request_budget_only_while_that_request_holds_it(cell: PostgresCell, method: str) -> None:
    """A call that carries no deadline (`catalog`, the credential and audit work on other pools) is never checked against the budget of an earlier request on the same pooled connection."""
    handle = cell._developer if method == "apply_schema" else cell._runtime
    request = _Request()
    request.expire_without_mark()
    with handle.connection(request.budget()) as first:
        assert first.request_budget is not None
    with handle.connection() as second:
        assert second is first
        assert second.request_budget is None
    with pytest.raises(FoundationError):
        _call(cell, method, request)
    with handle.connection() as third:
        assert third.request_budget is None
    assert [entry["entity"] for entry in cell.catalog()] == ["widgets"]


# ---- no check after the last statement ------------------------------------------


def test_a_query_whose_budget_ends_after_its_select_still_succeeds(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _Request()
    _wrap_run(monkeypatch, after_statement=lambda text: " LIMIT " in text, then=request.expire)
    outcome = _call(cell, "query", request)
    assert request.now > request.deadline, "the clock really passed the deadline after the select"
    assert len(outcome.items) == 1


def test_a_mutation_without_a_key_whose_budget_ends_after_its_last_operation_commits(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _row_count(cell)
    request = _Request()
    _wrap(monkeypatch, cell, "_apply", after=request.expire)
    outcome = _call(cell, "transact", request)
    assert request.now > request.deadline
    assert outcome.affected == 1 and outcome.committed is True
    monkeypatch.undo()
    assert _row_count(cell) == before + 1


# ---- the bound of each statement ---------------------------------------------------


@pytest.mark.parametrize(("remaining_s", "expected_ms"), [(0.5205, 520), (60.0, LIMITS.execution_ms)], ids=["under-execution_ms", "over-execution_ms"])
def test_the_statement_bound_is_the_smaller_of_execution_ms_and_the_whole_milliseconds_remaining(cell: PostgresCell, monkeypatch: pytest.MonkeyPatch, remaining_s: float, expected_ms: int) -> None:
    request = _Request()
    request.now = request.deadline - remaining_s
    seen = _wrap_run(monkeypatch, after_statement=lambda text: False, then=lambda: None)
    _call(cell, "query", request)
    bounds = [int(re.search(r"'(\d+)ms'", text).group(1)) for text in seen if text.startswith("SET LOCAL")]
    assert bounds == [expected_ms, expected_ms]


@pytest.mark.parametrize("remaining_ms", [0.0, 0.25, 0.9, -5.0])
def test_a_remaining_budget_under_one_millisecond_is_refused_and_never_becomes_a_bound_of_zero(remaining_ms: float) -> None:
    with pytest.raises(FoundationError) as exc:
        PostgresCell._timeout_ms(None, LIMITS, remaining_ms / 1000, lambda: 0.0)  # type: ignore[arg-type]
    assert _is_budget_refusal(exc.value)


@pytest.mark.parametrize(("remaining_ms", "expected"), [(1.0, 1), (1.9, 1), (120.5, 120), (60_000.0, LIMITS.execution_ms)])
def test_the_bound_is_whole_milliseconds_and_at_least_one(remaining_ms: float, expected: int) -> None:
    assert PostgresCell._timeout_ms(None, LIMITS, remaining_ms / 1000, lambda: 0.0) == expected  # type: ignore[arg-type]


def test_a_call_without_a_deadline_keeps_the_declared_execution_ms() -> None:
    assert PostgresCell._timeout_ms(None, LIMITS, None, None) == LIMITS.execution_ms  # type: ignore[arg-type]


# ---- the threshold ---------------------------------------------------------------


@pytest.mark.parametrize(("remaining_ms", "refused"), [(0.5, True), (0.9765625, True), (1.0, False), (1.953125, False), (0.0, True), (-3.0, True)])
def test_the_deadline_check_refuses_under_one_millisecond_remaining(remaining_ms: float, refused: bool) -> None:
    if refused:
        with pytest.raises(FoundationError) as exc:
            LIMITS.check_deadline(remaining_ms / 1000, lambda: 0.0)
        assert _is_budget_refusal(exc.value)
    else:
        LIMITS.check_deadline(remaining_ms / 1000, lambda: 0.0)


# ---- a pool wait and a new connection ----------------------------------------------


def test_a_pool_wait_that_ends_with_the_budget_spent_is_limit_exceeded_and_is_bounded_by_the_budget() -> None:
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1, acquire_timeout=5.0)
    try:
        with pool.connection():
            budget = _RequestBudget(LIMITS, time.monotonic() + 0.15, time.monotonic)
            started = time.monotonic()
            with pytest.raises(FoundationError) as exc:
                with pool.connection(budget):
                    pass
            waited = time.monotonic() - started
        assert _is_budget_refusal(exc.value)
        assert waited < 2.5, f"waited {waited:.2f}s: the wait must end with the budget, not with the pool's own 5 s"
    finally:
        pool.close_all()


def test_a_pool_wait_that_times_out_with_budget_left_stays_the_pool_failure() -> None:
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=1, acquire_timeout=0.1)
    try:
        with pool.connection():
            budget = _RequestBudget(LIMITS, time.monotonic() + 30.0, time.monotonic)
            with pytest.raises(psycopg.OperationalError):
                with pool.connection(budget):
                    pass
    finally:
        pool.close_all()


class _FailingConnect:
    """Stands in for `_RolePool._connect`: records the `connect_timeout` it was given, optionally moves the request's clock past its deadline, and fails."""

    def __init__(self, request: _Request, *, spends_the_budget: bool) -> None:
        self.request = request
        self.spends_the_budget = spends_the_budget
        self.timeouts: list[int | None] = []

    def __call__(self, connect_timeout: int | None = None) -> Any:
        self.timeouts.append(connect_timeout)
        if self.spends_the_budget:
            self.request.expire_without_mark()
        raise psycopg.OperationalError("connection to the database could not be opened")


def _pool_with_failing_connect(monkeypatch: pytest.MonkeyPatch, failing: _FailingConnect, **kwargs: Any) -> _RolePool:
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=2, **kwargs)
    monkeypatch.setattr(pool, "_connect", failing)
    return pool


def test_a_failed_connection_attempt_after_the_budget_is_spent_is_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _Request()
    failing = _FailingConnect(request, spends_the_budget=True)
    pool = _pool_with_failing_connect(monkeypatch, failing)
    with pytest.raises(FoundationError) as exc:
        with pool.connection(request.budget()):
            pass
    assert _is_budget_refusal(exc.value)
    assert len(failing.timeouts) == 1
    assert pool._created == 0, "the failed attempt gave its reservation back"


def test_a_failed_connection_attempt_with_budget_left_stays_the_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _Request()
    failing = _FailingConnect(request, spends_the_budget=False)
    pool = _pool_with_failing_connect(monkeypatch, failing)
    with pytest.raises(psycopg.OperationalError):
        with pool.connection(request.budget()):
            pass
    assert len(failing.timeouts) == 1


@pytest.mark.parametrize(("remaining_s", "expected_timeout"), [(2.5, 3), (0.2, 1), (30.0, 5)])
def test_a_new_connection_is_given_the_smaller_of_its_constructed_timeout_and_the_remaining_budget(monkeypatch: pytest.MonkeyPatch, remaining_s: float, expected_timeout: int) -> None:
    request = _Request()
    request.now = request.deadline - remaining_s
    failing = _FailingConnect(request, spends_the_budget=False)
    pool = _pool_with_failing_connect(monkeypatch, failing, connect_timeout=5)
    with pytest.raises(psycopg.OperationalError):
        with pool.connection(request.budget()):
            pass
    assert failing.timeouts == [expected_timeout]


def _terminate(admin_dsn: str, pid: int) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", [pid])
        deadline = time.monotonic() + _WAIT_S
        while admin.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = %s", [pid]).fetchone()[0]:
            assert time.monotonic() < deadline, "the backend did not go away"
            time.sleep(0.02)


@pytest.mark.parametrize("how", ["closed", "server_terminated"])
def test_a_replacement_connection_that_fails_after_the_budget_is_spent_is_limit_exceeded(monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    """A pooled connection found closed, or found dead by the pool's own liveness ping, is replaced by a new one: that attempt is judged like any other."""
    request = _Request()
    pool = _RolePool(_admin_dsn(), schema="public", maxconn=2)
    try:
        with pool.connection():
            pass
        idle = pool._queue.get_nowait()
        if how == "closed":
            idle.close()
        else:
            _terminate(_admin_dsn(), idle.info.backend_pid)
        pool._queue.put_nowait(idle)
        failing = _FailingConnect(request, spends_the_budget=True)
        monkeypatch.setattr(pool, "_connect", failing)
        with pytest.raises(FoundationError) as exc:
            with pool.connection(request.budget()):
                pass
        assert _is_budget_refusal(exc.value)
        assert len(failing.timeouts) == 1
    finally:
        monkeypatch.undo()
        pool.close_all()


# ---- the budget starts at the acceptance point -----------------------------------------


@pytest.mark.parametrize("method", _METHODS)
def test_the_wait_for_a_pooled_connection_counts_against_the_budget(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, method: str) -> None:  # noqa: F811
    """The deadline is fixed before the pool wait and not computed again after it: a request that waited for the only connection of a pool of one until its budget was gone is refused without sending a statement."""
    one = make_cell(app_a, pool_size=1)
    try:
        _prepare(one)
        hold = (one._developer if method == "apply_schema" else one._runtime).connection
        meter = _Meter(one, monkeypatch)
        request = _Request(meter)
        outcome: list[Any] = []

        def run() -> None:
            try:
                outcome.append(_call(one, method, request))
            except FoundationError as error:
                outcome.append(error)

        with hold():
            worker = threading.Thread(target=run)
            worker.start()
            time.sleep(0.3)
            request.expire_without_mark()
        worker.join(timeout=_WAIT_S)
        assert not worker.is_alive()
        (result,) = outcome
        assert isinstance(result, FoundationError) and _is_budget_refusal(result)
        assert meter.sent == [0]
    finally:
        monkeypatch.undo()
        one.close()


# ---- the in-memory backend ------------------------------------------------------------


class _ReadsThenExpired:
    """A clock that reads `ok` for its first `ok_reads` reads and `expired` after that."""

    def __init__(self, ok_reads: int, ok: float = 0.0, expired: float = 100.0) -> None:
        self.reads = 0
        self.ok_reads = ok_reads
        self.ok = ok
        self.expired = expired

    def __call__(self) -> float:
        self.reads += 1
        return self.ok if self.reads <= self.ok_reads else self.expired


def _memory_cell() -> ApplicationCell:
    memory = ApplicationCell("budget-app", {})
    memory.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"]}, developer=True, limits=LIMITS)
    memory.transact("widgets", [{"operation": "insert", "values": {"label": "seed"}}], LIMITS)
    return memory


_MEMORY_DEADLINE = LIMITS.execution_ms / 1000


def test_the_in_memory_query_checks_before_its_work_and_not_after() -> None:
    memory = _memory_cell()
    clock = _ReadsThenExpired(ok_reads=1)
    outcome = memory.query("widgets", select=["label"], where=[], page_size=10, limits=LIMITS, deadline=_MEMORY_DEADLINE, clock=clock)
    assert len(outcome.items) == 1
    assert clock.reads == 1, "one check, before the work"


def test_the_in_memory_mutation_checks_before_each_operation_and_not_after_the_last() -> None:
    memory = _memory_cell()
    clock = _ReadsThenExpired(ok_reads=2)
    outcome = memory.transact("widgets", [{"operation": "insert", "values": {"label": "one"}}], LIMITS, deadline=_MEMORY_DEADLINE, clock=clock)
    assert outcome.affected == 1
    assert clock.reads == 2, "the entry and the one operation; nothing after the last"


def test_the_in_memory_schema_operation_checks_before_its_operation_and_not_after() -> None:
    memory = _memory_cell()
    clock = _ReadsThenExpired(ok_reads=1)
    outcome = memory.apply_schema({"operation": "add_field", "entity": "widgets", "field": "extra"}, developer=True, limits=LIMITS, deadline=_MEMORY_DEADLINE, clock=clock)
    assert outcome.committed is True
    assert "extra" in memory.schema["widgets"], "the operation took effect"
    assert clock.reads == 1, "one check, before the operation; nothing after it"


def test_the_in_memory_mutation_refuses_the_operation_that_would_start_after_the_budget_is_spent() -> None:
    memory = _memory_cell()
    clock = _ReadsThenExpired(ok_reads=2)
    ops = [{"operation": "insert", "values": {"label": "one"}}, {"operation": "insert", "values": {"label": "two"}}]
    with pytest.raises(FoundationError) as exc:
        memory.transact("widgets", ops, LIMITS, deadline=_MEMORY_DEADLINE, clock=clock)
    assert _is_budget_refusal(exc.value)
    assert len(memory.query("widgets", select=["label"], where=[], page_size=10, limits=LIMITS).items) == 1, "the first operation is undone with the request"


def test_the_in_memory_mutation_refuses_a_replay_whose_budget_is_spent() -> None:
    """The entry check also covers a request answered from an idempotency record, which reaches no operation."""
    memory = _memory_cell()
    ops = [{"operation": "insert", "values": {"label": "keyed"}}]
    plan_request = {"entity": "widgets", "operations": ops}
    first = memory.transact("widgets", ops, LIMITS, plan_request=plan_request, idempotency_key="k-replay", request_id="request-1")
    assert first.replayed is False
    assert memory.transact("widgets", ops, LIMITS, plan_request=plan_request, idempotency_key="k-replay", request_id="request-2").replayed is True
    with pytest.raises(FoundationError) as exc:
        memory.transact("widgets", ops, LIMITS, deadline=0.0005, clock=lambda: 0.0, plan_request=plan_request, idempotency_key="k-replay", request_id="request-3")
    assert _is_budget_refusal(exc.value)


def test_the_in_memory_schema_operation_refuses_a_replay_whose_budget_is_spent() -> None:
    """The entry check sits before the idempotency lookup, so a keyed schema request whose key has a record is refused and not answered from the record."""
    memory = _memory_cell()
    operation = {"operation": "add_field", "entity": "widgets", "field": "extra"}
    plan_request = {"operation": operation}
    first = memory.apply_schema(operation, developer=True, limits=LIMITS, plan_request=plan_request, idempotency_key="k-schema-replay", request_id="request-1")
    assert first.replayed is False
    resent = memory.apply_schema(operation, developer=True, limits=LIMITS, plan_request=plan_request, idempotency_key="k-schema-replay", request_id="request-2")
    assert resent.replayed is True, "the record exists, so a request with budget left is answered from it"
    with pytest.raises(FoundationError) as exc:
        memory.apply_schema(operation, developer=True, limits=LIMITS, deadline=0.0005, clock=lambda: 0.0, plan_request=plan_request, idempotency_key="k-schema-replay", request_id="request-3")
    assert _is_budget_refusal(exc.value)


@pytest.mark.parametrize("method", _METHODS)
def test_the_in_memory_backend_refuses_under_one_millisecond_remaining(method: str) -> None:
    memory = _memory_cell()
    with pytest.raises(FoundationError) as exc:
        if method == "query":
            memory.query("widgets", select=["label"], where=[], page_size=10, limits=LIMITS, deadline=0.0005, clock=lambda: 0.0)
        elif method == "transact":
            memory.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS, deadline=0.0005, clock=lambda: 0.0)
        else:
            memory.apply_schema({"operation": "add_field", "entity": "widgets", "field": "extra"}, developer=True, limits=LIMITS, deadline=0.0005, clock=lambda: 0.0)
    assert _is_budget_refusal(exc.value)
