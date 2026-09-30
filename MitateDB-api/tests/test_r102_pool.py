r"""`mitatedb_api.pool.BoundedConnectionPool` as the per-application connection
pool the data plane borrows from (design docs/design/
MITATEDB_APPLICATION_SERIALIZATION_V0_1.md D-2 (i)-(iii) and the idle
sweep; work order docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_
V1.md section 2.3, completion conditions 26-34).

What is pinned here:

* 26: `acquire(timeout=...)` bounds one call's wait and the connect of a
  connection it opens; no `timeout` keeps the construction-time values.
* 27: the pool's own exceptions (`PoolError`, `PoolExhausted`,
  `PoolConnectFailed`) are not `FoundationError`s, and `pool.py` never names
  `AuthorizationStateUnavailable`.
* 28 / 29: the credential store's and the audit sink's borrow points map
  them to `AuthorizationStateUnavailable` with the messages those callers
  always answered.
* 30 / 31: `release()` rolls back what a returned connection left open (a
  real PostgreSQL server: transaction status, a `SET` value, and an aborted
  transaction), and discards
  a connection whose rollback fails.
* 32 / 33 / 34: the idle sweep closes another pool's stale idle connections
  and never an in-use one, runs at most once per second in the process, and
  holds pools weakly.

The pool's own bookkeeping runs against fake connections (no I/O) and a fake
clock (`pool.time` replaced for the test); the rollback tests use a real
connection to the test cluster's admin DSN, which they only read and `SET` in
a transaction they roll back.

Run directly:
    ./.venv/bin/python -m pytest MitateDB-api/tests/test_r102_pool.py -q
"""
from __future__ import annotations

import gc
import os
import threading
import time
import weakref
from types import SimpleNamespace
from typing import Iterator

import psycopg
import pytest

import mitatedb_api.pool as pool_module
from mitatedb_api.application_audit import PostgresApplicationAuditSink
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import AuthorizationStateUnavailable, FoundationError
from mitatedb_api.pool import (
    IDLE_CLOSE_THRESHOLD_S,
    BoundedConnectionPool,
    PoolConnectFailed,
    PoolError,
    PoolExhausted,
)

ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
_EXHAUSTED_MESSAGE = "platform registry connection pool exhausted (max_size reached)"
_CONNECT_FAILED_MESSAGE = "authorization state unavailable"


class _FakeConnection:
    """The attributes `BoundedConnectionPool` itself reads: `closed`,
    `close()`, `info.transaction_status`, `rollback()`, and the counters its
    statistics fold reads. `rollback_error`, when set, is raised by
    `rollback()`."""

    def __init__(
        self, *, transaction_status: "psycopg.pq.TransactionStatus" = psycopg.pq.TransactionStatus.IDLE,
        rollback_error: "BaseException | None" = None, db_wall_ms: float = 0.0, txn_count: int = 0,
        execute_count: int = 0,
    ) -> None:
        self.closed = False
        self.info = SimpleNamespace(transaction_status=transaction_status)
        self.rollback_error = rollback_error
        self.rollback_calls = 0
        self.db_wall_ms = db_wall_ms
        self.txn_count = txn_count
        self.execute_count = execute_count
        self.executemany_count = 0

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        self.rollback_calls += 1
        if self.rollback_error is not None:
            raise self.rollback_error


def _fake_pool(max_size: int = 1, *, acquire_timeout: float = 5.0, factory=_FakeConnection) -> BoundedConnectionPool:
    pool = BoundedConnectionPool(
        "dsn-unused-fake-pool-r102-test.invalid", max_size=max_size, connect_timeout=1, acquire_timeout=acquire_timeout,
    )
    pool._new_connection = lambda: factory()  # type: ignore[method-assign]  # noqa: SLF001
    return pool


class _FakeClock:
    """Replaces the `time` name inside `pool.py`: the pool only calls
    `time.monotonic()`, so this is the pool's whole clock."""

    def __init__(self, now: float) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeClock]:
    """A fake pool clock starting at 0.0 (below any real `time.monotonic()`
    stamp another live pool carries, so no other pool's idle connection can
    read as stale while this test advances time), with the process-wide
    sweep state cleared before and after."""
    fake = _FakeClock(0.0)
    monkeypatch.setattr(pool_module, "time", fake)
    monkeypatch.setattr(pool_module, "_last_sweep_monotonic", None)
    yield fake
    monkeypatch.undo()
    pool_module._last_sweep_monotonic = None  # noqa: SLF001


@pytest.fixture
def admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        pytest.fail(f"{ADMIN_DSN_ENV} is not set; tools/testpg/dsa_testpg.py sets it for each test run", pytrace=False)
    return dsn


# --- 26 ---------------------------------------------------------------------


def test_acquire_timeout_bounds_one_call_and_none_keeps_the_construction_value() -> None:
    """Completion condition 26: on a pool built with a 3.0 s wait, a call
    `acquire(timeout=0.2)` gives up after about 0.2 s; a call with no
    `timeout` on a pool built with 0.2 s also gives up after about 0.2 s;
    and a call `acquire(timeout=3.0)` on a pool built with 0.2 s outwaits the
    construction value and gets the connection a holder returns after 0.5
    s. Every wait is real (the fake holds the pool's only slot), and each
    bound is asserted on both sides.

    mutation (`pool.py`, `acquire`): ignore the call's `timeout` (`wait_limit
    = self._acquire_timeout if timeout is None else timeout` becomes `wait_limit
    = self._acquire_timeout`) -- the first call waits the constructed 3.0 s
    and the elapsed-time bound fails."""
    long_pool = _fake_pool(1, acquire_timeout=3.0)
    held = long_pool.acquire()
    start = time.monotonic()
    with pytest.raises(PoolExhausted):
        long_pool.acquire(timeout=0.2)
    elapsed = time.monotonic() - start
    assert 0.15 <= elapsed < 1.5, elapsed
    long_pool.release(held)

    short_pool = _fake_pool(1, acquire_timeout=0.2)
    held = short_pool.acquire()
    start = time.monotonic()
    with pytest.raises(PoolExhausted):
        short_pool.acquire()
    elapsed = time.monotonic() - start
    assert 0.15 <= elapsed < 1.5, elapsed

    releaser = threading.Timer(0.5, short_pool.release, args=(held,))
    releaser.start()
    try:
        start = time.monotonic()
        got = short_pool.acquire(timeout=3.0)
        waited = time.monotonic() - start
    finally:
        releaser.join()
    assert got is held
    assert 0.3 <= waited < 2.5, waited
    short_pool.release(got)
    assert short_pool.stats()["wait_count"] == 2  # non-vacuous: the exhausted call and the one that got `held` both waited


class _RecordingConnect:
    """Stands in for `pool.CountingConnection`: records the keyword arguments
    of each `connect()` call and returns a fake connection."""

    calls: "list[dict]" = []

    @classmethod
    def connect(cls, dsn: str, **kwargs: object) -> _FakeConnection:
        cls.calls.append(kwargs)
        return _FakeConnection()


def test_acquire_timeout_bounds_the_connect_of_a_connection_it_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 26 (connect leg): a connection a call opens is
    given the smaller of the constructed `connect_timeout` and the call's
    `timeout` rounded up to whole seconds (at least 1); a call with no
    `timeout` connects with the constructed value. The real `_new_connection`
    runs; only `CountingConnection.connect` is replaced, and its recorded
    keyword arguments are what is asserted.

    mutation (`pool.py`, `acquire`): connect with the constructed value
    whatever the call's `timeout` (`min(self._connect_timeout, max(1, math.
    ceil(timeout)))` becomes `self._connect_timeout`) -- the 0.3 s call
    connects with 5. Second mutation: drop the `max(1, ...)` floor -- the
    0.0 s call then connects with 0, which psycopg reads as its own
    default of 130 s, not as "no time left"."""
    _RecordingConnect.calls = []
    monkeypatch.setattr(pool_module, "CountingConnection", _RecordingConnect)
    pool = BoundedConnectionPool("dsn-unused-fake-pool-r102-test.invalid", max_size=5, connect_timeout=5)
    for timeout in (0.0, 0.3, 2.2, 30.0, None):
        pool.acquire(timeout=timeout)
    assert [call["connect_timeout"] for call in _RecordingConnect.calls] == [1, 1, 3, 5, 5]


# --- 27 ---------------------------------------------------------------------


def test_pool_exceptions_are_neutral_and_pool_py_does_not_name_the_platform_error() -> None:
    """Completion condition 27: an exhausted pool raises `PoolExhausted`; a
    connection that cannot be opened raises `PoolConnectFailed` (with the
    driver's error as `__cause__`, and the slot given back); both are under
    `PoolError` and neither is a `FoundationError`; and `pool.py` neither
    imports nor names `AuthorizationStateUnavailable`.

    mutation (`pool.py`, `acquire`): raise `AuthorizationStateUnavailable`
    where the pool is exhausted (the shape before the pool's own
    exceptions) -- `pytest.raises(PoolExhausted)` fails."""
    import ast
    import inspect

    assert issubclass(PoolExhausted, PoolError) and issubclass(PoolConnectFailed, PoolError)
    assert not issubclass(PoolError, FoundationError)
    assert PoolError.__mro__[1] is Exception

    pool = _fake_pool(1, acquire_timeout=0.1)
    held = pool.acquire()
    with pytest.raises(PoolExhausted) as exhausted:
        pool.acquire()
    assert not isinstance(exhausted.value, FoundationError)
    pool.release(held)

    cause = psycopg.OperationalError("synthetic connect failure")

    def _refuse() -> "psycopg.Connection":
        raise cause

    failing = BoundedConnectionPool("dsn-unused-fake-pool-r102-test.invalid", max_size=1)
    failing._new_connection = _refuse  # type: ignore[method-assign]  # noqa: SLF001
    with pytest.raises(PoolConnectFailed) as failed:
        failing.acquire()
    assert failed.value.__cause__ is cause
    assert not isinstance(failed.value, FoundationError)
    assert failing._created == 0  # noqa: SLF001 -- the failed attempt gave its slot back

    tree = ast.parse(inspect.getsource(pool_module))
    named = [
        node for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == "AuthorizationStateUnavailable")
        or (isinstance(node, ast.Attribute) and node.attr == "AuthorizationStateUnavailable")
        or (isinstance(node, ast.alias) and node.name == "AuthorizationStateUnavailable")
    ]
    assert named == []


# --- 28 / 29 ----------------------------------------------------------------


def _store_over(pool: BoundedConnectionPool) -> PostgresCredentialStore:
    return PostgresCredentialStore(
        "dsn-unused-fake-pool-r102-test.invalid", pepper="synthetic-test-pepper-wp4e-platform-pool-0000", pool=pool,
    )


def _refusing_pool() -> BoundedConnectionPool:
    pool = BoundedConnectionPool("dsn-unused-fake-pool-r102-test.invalid", max_size=1)

    def _refuse() -> "psycopg.Connection":
        raise psycopg.OperationalError("synthetic connect failure")

    pool._new_connection = _refuse  # type: ignore[method-assign]  # noqa: SLF001
    return pool


def test_credential_store_maps_pool_errors_to_the_unchanged_authorization_state_unavailable() -> None:
    """Completion condition 28: a credential store whose pool is exhausted
    raises `AuthorizationStateUnavailable` with exactly "platform registry
    connection pool exhausted (max_size reached)", and one whose pool cannot
    connect raises it with exactly "authorization state unavailable"; the
    pool's own exception is the `__cause__` of each.

    mutation (`credential_store_postgres.py`, `_borrow_connection`): drop the
    mapping (the `try`/`except PoolExhausted`/`except PoolError` block becomes
    a bare `conn = self._pool.acquire()`) -- the pool's `PoolExhausted`
    passes through unmapped and `pytest.raises(AuthorizationStateUnavailable)`
    fails."""
    pool = _fake_pool(1, acquire_timeout=0.1)
    held = pool.acquire()
    with pytest.raises(AuthorizationStateUnavailable) as exhausted:
        with _store_over(pool)._borrow_connection():  # noqa: SLF001 -- the one choke point every store method borrows through
            pytest.fail("the exhausted pool handed out a connection")
    assert str(exhausted.value) == _EXHAUSTED_MESSAGE
    assert isinstance(exhausted.value.__cause__, PoolExhausted)
    pool.release(held)

    with pytest.raises(AuthorizationStateUnavailable) as failed:
        with _store_over(_refusing_pool())._borrow_connection():  # noqa: SLF001
            pytest.fail("the refusing pool handed out a connection")
    assert str(failed.value) == _CONNECT_FAILED_MESSAGE
    assert isinstance(failed.value.__cause__, PoolConnectFailed)


def test_audit_sink_maps_pool_errors_to_the_unchanged_authorization_state_unavailable() -> None:
    """Completion condition 29: the audit sink's borrow point maps the pool's
    exceptions the same way (the sink propagates them to `audit_dispatch`,
    which decides how a failure becomes `AuditSinkUnavailable`): exhausted
    with "platform registry connection pool exhausted (max_size reached)",
    a connect failure with "authorization state unavailable".

    mutation (`application_audit.py`, `_borrow`): drop the mapping (the
    `try`/`except PoolExhausted`/`except PoolError` block becomes a bare
    `conn = self._pool.acquire()`) -- `PoolExhausted` passes through and
    `pytest.raises(AuthorizationStateUnavailable)` fails."""
    pool = _fake_pool(1, acquire_timeout=0.1)
    held = pool.acquire()
    sink = PostgresApplicationAuditSink("dsn-unused-fake-pool-r102-test.invalid", pool=pool)
    with pytest.raises(AuthorizationStateUnavailable) as exhausted:
        with sink._borrow():  # noqa: SLF001 -- the one place every sink call borrows through
            pytest.fail("the exhausted pool handed out a connection")
    assert str(exhausted.value) == _EXHAUSTED_MESSAGE
    assert isinstance(exhausted.value.__cause__, PoolExhausted)
    pool.release(held)

    refusing = PostgresApplicationAuditSink("dsn-unused-fake-pool-r102-test.invalid", pool=_refusing_pool())
    with pytest.raises(AuthorizationStateUnavailable) as failed:
        with refusing._borrow():  # noqa: SLF001
            pytest.fail("the refusing pool handed out a connection")
    assert str(failed.value) == _CONNECT_FAILED_MESSAGE
    assert isinstance(failed.value.__cause__, PoolConnectFailed)


# --- 30 / 31 ----------------------------------------------------------------


def test_release_rolls_back_so_the_next_borrower_gets_a_clean_connection(admin_dsn: str) -> None:
    """Completion condition 30: a connection returned with a transaction open
    and a `SET` made inside it comes back from the next `acquire()` (the same
    server session, the pool has one slot) with `transaction_status` IDLE and
    the `SET` value back at the session default. The default is read from a
    separate connection first, so the assertion compares against the server's
    value and not a constant.

    mutation (`pool.py`, `release`): drop the rollback (`conn.rollback()`
    becomes `pass`) -- the connection comes back inside its transaction
    (`transaction_status` INTRANS)."""
    probe = psycopg.connect(admin_dsn, autocommit=True)
    try:
        default_timeout = probe.execute("SHOW statement_timeout").fetchone()[0]
    finally:
        probe.close()
    assert default_timeout != "7s"

    pool = BoundedConnectionPool(admin_dsn, max_size=1)
    try:
        first = pool.acquire()
        first.execute("SET statement_timeout = '7s'")
        assert first.execute("SHOW statement_timeout").fetchone()[0] == "7s"
        assert first.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        backend_pid = first.info.backend_pid
        pool.release(first)

        second = pool.acquire()
        assert second is first and second.info.backend_pid == backend_pid  # non-vacuous: the same session came back
        assert second.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert second.execute("SHOW statement_timeout").fetchone()[0] == default_timeout
        pool.release(second)
    finally:
        pool.closeall()


def test_release_rolls_back_a_connection_left_in_an_aborted_transaction(admin_dsn: str) -> None:
    """Completion condition 30 (aborted leg): a connection returned after a
    statement failed inside its transaction (`transaction_status` INERROR)
    comes back from the next `acquire()` (same session) IDLE and able to run
    a statement, not failing with "current transaction is aborted".

    mutation (`pool.py`, `release`): roll back only a connection that is
    `INTRANS` (`!= psycopg.pq.TransactionStatus.IDLE` becomes `==
    psycopg.pq.TransactionStatus.INTRANS`) -- the INERROR connection goes
    back as it is and is INERROR when borrowed again."""
    pool = BoundedConnectionPool(admin_dsn, max_size=1)
    try:
        first = pool.acquire()
        with pytest.raises(psycopg.errors.DivisionByZero):
            first.execute("SELECT 1/0")
        assert first.info.transaction_status == psycopg.pq.TransactionStatus.INERROR
        backend_pid = first.info.backend_pid
        pool.release(first)

        second = pool.acquire()
        assert second is first and second.info.backend_pid == backend_pid  # non-vacuous: the same session came back
        assert second.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert second.execute("SELECT 1").fetchone() == (1,)
        pool.release(second)
    finally:
        pool.closeall()


def test_release_discards_a_connection_whose_rollback_fails() -> None:
    """Completion condition 31: a connection returned inside a transaction
    whose `rollback()` raises is closed and forgotten, not put in the idle
    queue; the pool's slot is free again and the next `acquire()` opens a
    new connection. A connection with no transaction open is returned
    without a rollback call.

    mutation (`pool.py`, `release`): return the connection to the idle queue
    when the rollback failed (the `except Exception:` branch's `self.discard(
    conn)` / `return` become `pass`) -- the broken connection is neither
    closed nor forgotten and `assert broken.closed` fails."""
    broken = _FakeConnection(
        transaction_status=psycopg.pq.TransactionStatus.INTRANS,
        rollback_error=psycopg.OperationalError("synthetic rollback failure"),
        db_wall_ms=4.0, txn_count=1, execute_count=2,
    )
    clean = _FakeConnection()
    handed_out = [broken, clean]
    pool = _fake_pool(1, factory=lambda: handed_out.pop(0))

    held = pool.acquire()
    assert held is broken
    pool.release(held)
    assert broken.rollback_calls == 1  # non-vacuous: the rollback really ran, and failed
    assert broken.closed
    assert pool._idle.empty()  # noqa: SLF001
    assert pool._created == 0  # noqa: SLF001
    assert pool.platform_stats()["db_calls"] == 2  # its statistics were folded in, not lost

    replacement = pool.acquire()
    assert replacement is clean
    pool.release(replacement)
    assert clean.rollback_calls == 0  # IDLE: nothing to roll back
    assert pool._idle.qsize() == 1  # noqa: SLF001


def test_release_discards_a_real_connection_the_server_ended_mid_transaction(admin_dsn: str) -> None:
    """Completion condition 31, against a real server: a connection inside a
    transaction whose backend was terminated fails its rollback on release
    and is discarded; the next borrower gets a new session."""
    pool = BoundedConnectionPool(admin_dsn, max_size=1)
    try:
        conn = pool.acquire()
        conn.execute("SELECT 1")
        backend_pid = conn.info.backend_pid
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            assert admin.execute("SELECT pg_terminate_backend(%s)", [backend_pid]).fetchone() == (True,)
        finally:
            admin.close()
        pool.release(conn)
        assert pool._idle.empty()  # noqa: SLF001
        assert pool._created == 0  # noqa: SLF001

        fresh = pool.acquire()
        assert fresh.info.backend_pid != backend_pid
        assert fresh.execute("SELECT 1").fetchone() == (1,)
        pool.release(fresh)
        assert pool.platform_stats()["sessions"] == 2
    finally:
        pool.closeall()


# --- 32 / 33 / 34 -----------------------------------------------------------


def test_another_pools_acquire_closes_stale_idle_connections_and_spares_in_use_ones(clock: _FakeClock) -> None:
    """Completion condition 32: two connections idle in pool A since t=10
    are closed by an `acquire()` on pool B once they are more than
    `IDLE_CLOSE_THRESHOLD_S` old (not at exactly that age), while a third
    connection A has checked out is not closed; A's slots are given back and
    its statistics folded in.

    mutation (`pool.py`, `_close_stale_idle_in_every_pool`): sweep only this
    pool (`pools = list(_live_pools)` becomes `pools = [self]`) -- B's
    acquire leaves A's idle connections open."""
    pool_a = _fake_pool(3, factory=lambda: _FakeConnection(db_wall_ms=2.5, txn_count=1, execute_count=3))
    pool_b = _fake_pool(1)
    clock.now = 10.0
    a1, a2, in_use = pool_a.acquire(), pool_a.acquire(), pool_a.acquire()
    pool_a.release(a1)
    pool_a.release(a2)
    assert pool_a._idle.qsize() == 2  # noqa: SLF001

    clock.now = 10.0 + IDLE_CLOSE_THRESHOLD_S
    pool_b.release(pool_b.acquire())
    assert not a1.closed and not a2.closed  # exactly the threshold: not stale

    clock.now = 10.0 + IDLE_CLOSE_THRESHOLD_S + 1.0
    pool_b.release(pool_b.acquire())
    assert a1.closed and a2.closed
    assert not in_use.closed
    assert pool_a._idle.qsize() == 0  # noqa: SLF001
    assert pool_a._created == 1  # noqa: SLF001 -- only the checked-out connection remains
    assert pool_a.platform_stats()["db_wall_ms"] == 5.0  # the two closed connections' statistics were folded in
    pool_a.release(in_use)


def test_the_idle_sweep_runs_at_most_once_per_second_in_the_process(
    clock: _FakeClock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 33: thirty `acquire()` calls on two pools inside
    one second start exactly one sweep of pool A (counted by wrapping its
    per-pool step); a call one second after that sweep started starts the
    next.

    mutation (`pool.py`, `_close_stale_idle_in_every_pool`): drop the
    suppression (`< _IDLE_SWEEP_MIN_INTERVAL_S` becomes `< 0.0`) -- every
    `acquire()` sweeps and the count is thirty, not one."""
    pool_a, pool_b = _fake_pool(1), _fake_pool(1)
    sweeps_of_a: list[float] = []
    original = BoundedConnectionPool._close_stale_idle

    def _counting(self: BoundedConnectionPool, now: float) -> None:
        if self is pool_a:
            sweeps_of_a.append(now)
        original(self, now)

    monkeypatch.setattr(BoundedConnectionPool, "_close_stale_idle", _counting)

    clock.now = 100.0
    for index in range(30):
        pool = pool_a if index % 2 == 0 else pool_b
        pool.release(pool.acquire())
    assert sweeps_of_a == [100.0]

    clock.now = 100.5
    pool_a.release(pool_a.acquire())
    assert sweeps_of_a == [100.0]

    clock.now = 101.0
    pool_b.release(pool_b.acquire())
    assert sweeps_of_a == [100.0, 101.0]


def test_a_pool_nothing_refers_to_leaves_the_sweep_list() -> None:
    """Completion condition 34: a pool is in the process list while it is
    referenced and gone from it once the last reference is dropped.

    mutation (`pool.py`): hold the list strongly (`weakref.WeakSet()`
    becomes `set()`) -- the dropped pool stays alive and listed."""
    pool = _fake_pool(1)
    pool.release(pool.acquire())
    assert pool in pool_module._live_pools  # noqa: SLF001 -- non-vacuous: it was listed
    reference = weakref.ref(pool)
    del pool
    gc.collect()
    assert reference() is None
