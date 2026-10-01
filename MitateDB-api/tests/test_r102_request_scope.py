"""Request scope and application-wide serialization of `PostgresBackend`
(docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md D-1 .. D-6): a
request borrows its connections once, runs as one transaction on its main
connection, takes its advisory locks at fixed points of one order, and
returns the connections rolled back. One test per property; each is
red when only its own mechanism is removed.

Stop technique (no hook in product code): a test-local stall wraps the
module-level `backend_postgres._execute` (or one backend method) and pauses
ONE armed thread on an `Event` when the statement about to run is the named
one; every other thread passes through.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from typing import Any, Callable

import psycopg
import pytest

import mitatedb_api.backend_postgres as bp_module
from mitatedb_api import FoundationConfig, Role
from mitatedb_api.auth import Principal
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, Filter
from mitatedb_api.errors import (ConflictError, FoundationError, ResourceLimitError,
                                 StorageTransientError)
from mitatedb_api.http import _classify

from .scoped_backend import scoped
from .test_postgres import app_a, close_cell, make_cell, platform, sessions_for  # noqa: F401 (fixtures)

_SRC = Path(__file__).resolve().parent.parent / "src" / "mitatedb_api"
_WAIT_S = 10.0


# ---------------------------------------------------------------- helpers
def _cell(app, *, pool_size: int | None = None, max_execution_ms: int | None = None) -> ApplicationCell:
    config = FoundationConfig(max_execution_ms=max_execution_ms) if max_execution_ms else FoundationConfig()
    kwargs = {} if pool_size is None else {"pool_size": pool_size}
    backend = PostgresBackend(runtime_dsn=app.runtime_dsn, developer_dsn=app.developer_dsn, **kwargs)
    return ApplicationCell(app.app_id, config, backend=backend)


def _sessions(cell: ApplicationCell, app) -> tuple[ApplicationDeveloper, ApplicationRuntime]:
    return sessions_for(cell, app.app_id)


class _Run:
    """Runs `fn` on a thread; `.join()` returns its result or raises its error."""

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.result: Any = None
        self.error: BaseException | None = None
        self.done = threading.Event()

        def body() -> None:
            try:
                self.result = fn()
            except BaseException as exc:  # noqa: BLE001 -- handed back to the test
                self.error = exc
            finally:
                self.done.set()

        self.thread = threading.Thread(target=body, daemon=True)
        self.thread.start()

    def finish(self, timeout: float = 20.0) -> Any:
        assert self.done.wait(timeout), "the request never finished"
        if self.error is not None:
            raise self.error
        return self.result


class _StatementStall:
    """Pauses the armed thread once, just before the first statement that
    starts with `prefix` (containing `needle`) reaches the database."""

    def __init__(self, prefix: str, needle: str = "") -> None:
        self.prefix, self.needle = prefix, needle
        self.holding = threading.Event()
        self.release = threading.Event()
        self.thread: threading.Thread | None = None
        self._used = False

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = bp_module._execute
        stall = self

        def wrapped(cursor, statement, params=()):
            if not stall._used and threading.current_thread() is stall.thread:
                text = statement.as_string(cursor) if hasattr(statement, "as_string") else str(statement)
                if text.strip().upper().startswith(stall.prefix) and stall.needle in text:
                    stall._used = True
                    stall.holding.set()
                    assert stall.release.wait(_WAIT_S), "test setup: the stall was never released"
            return original(cursor, statement, params)

        monkeypatch.setattr(bp_module, "_execute", wrapped)

    def run_armed(self, fn: Callable[[], Any]) -> _Run:
        started = threading.Event()

        def armed() -> Any:
            self.thread = threading.current_thread()
            started.set()
            return fn()

        run = _Run(armed)
        assert started.wait(_WAIT_S)
        assert self.holding.wait(_WAIT_S), "the armed request never reached its stall point"
        return run


def _setup(app, *entities: str, pool_size: int | None = None):
    cell = _cell(app, pool_size=pool_size)
    dev, rt = _sessions(cell, app)
    for name in entities:
        dev.create_collection(name, {"title": "text"})
    return cell, dev, rt


# ------------------------------------------------------ 37 / 38: static
def _code_attribute_refs(path: Path, owner: str, names: set[str]) -> list[str]:
    tree = ast.parse(path.read_text())
    return [f"{path.name}:{n.lineno} {owner}.{n.attr}" for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == owner
            and n.attr in names]


def test_backend_postgres_names_no_persistent_connection_attribute() -> None:
    """The backend holds no connection between requests: no `self._developer`
    / `self._runtime` attribute is read or written (counted over the AST's
    `Attribute` nodes, so the pool attributes `_developer_pool` /
    `_runtime_pool` are different names and do not collide). Non-vacuous:
    the same scan finds the two pool attributes."""
    assert _code_attribute_refs(_SRC / "backend_postgres.py", "self", {"_developer", "_runtime"}) == []
    assert len(_code_attribute_refs(_SRC / "backend_postgres.py", "self", {"_developer_pool", "_runtime_pool"})) >= 4


def test_cell_py_code_names_no_lock_and_no_concrete_backend() -> None:
    """`cell.py` serializes nothing itself and does not branch on the kind
    of backend: in its code (comments and docstrings excluded) no
    `self._lock`, `_CountingRLock`, `PostgresBackend` or
    `isinstance(self._backend`; `SQLiteBackend` only in its import and the
    default backend construction."""
    source = (_SRC / "cell.py").read_text()
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.extend(alias.name for alias in node.names)
    assert "_CountingRLock" not in names and "PostgresBackend" not in names
    assert "_lock" not in [n for n in names if n == "_lock"], "a `_lock` attribute is read in cell.py"
    assert names.count("SQLiteBackend") == 2, names.count("SQLiteBackend")
    assert "isinstance(self._backend" not in ast.unparse(tree)


# --------------------------------------------- 46: concurrency in pass 2
def test_two_requests_of_one_application_are_in_pass_2_at_the_same_time(app_a, monkeypatch) -> None:
    """Both requests reach `insert_in_transaction` and wait there for each
    other (a two-party barrier): they are inside their transactions at the
    same moment. Serialized, the first would wait for the second forever and
    the barrier would break."""
    cell, _dev, rt = _setup(app_a, "pair")
    barrier = threading.Barrier(2, timeout=8)
    original = PostgresBackend.insert_in_transaction
    arrived: list[str] = []

    def meeting(self, *args, **kwargs):
        arrived.append(threading.current_thread().name)
        barrier.wait()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PostgresBackend, "insert_in_transaction", meeting)
    try:
        runs = [_Run(lambda i=i: rt.transact([{"type": "insert", "collection": "pair", "values": {"title": f"t{i}"}}]))
                for i in range(2)]
        for run in runs:
            run.finish()
        assert len(arrived) == 2
        assert len(rt.read("pair")) == 2
    finally:
        close_cell(cell)


# --------------------------------------- 49: lock order, no 40P01 between
def test_keyed_create_collection_and_keyed_add_field_do_not_deadlock(app_a, monkeypatch) -> None:
    """A (keyed `create_collection`) is held at the ENTRY of its idempotency
    admission; B (keyed `add_field`) runs its admission and goes on. B holds
    the capacity lock while it waits for the schema lock only if the order
    were broken somewhere: with the order key -> capacity -> schema lock ->
    entity lock for every schema operation, B finishes while A waits, and A
    then finishes; with `create_collection` taking the schema lock before its
    admission, A would hold the schema lock B needs while A needs the
    capacity lock B holds, and PostgreSQL ends one of them with 40P01."""
    cell, dev, _rt = _setup(app_a, "e1")
    original = ApplicationCell._idempotency_check
    holding, release = threading.Event(), threading.Event()

    def gated(self, key, digest_request, **kwargs):
        if key == "k-create":
            holding.set()
            assert release.wait(_WAIT_S)
        return original(self, key, digest_request, **kwargs)

    monkeypatch.setattr(ApplicationCell, "_idempotency_check", gated)
    try:
        a = _Run(lambda: dev.create_entity("e2", {"title": "text"}, idempotency_key="k-create"))
        assert holding.wait(_WAIT_S)
        b = _Run(lambda: dev.add_field("e1", "extra", "text", idempotency_key="k-add"))
        b.done.wait(1.5)
        release.set()
        assert b.finish()["committed"] is True
        assert a.finish()["committed"] is True
    finally:
        release.set()
        close_cell(cell)


# -------------------------------- 50 / 51 / 52: entity-granular locking
def _stalled_add_field(app, monkeypatch, *entities: str):
    cell, dev, rt = _setup(app, *entities)
    stall = _StatementStall("ALTER TABLE", '"ea" ADD COLUMN')
    stall.install(monkeypatch)
    a = stall.run_armed(lambda: dev.add_field("ea", "extra", "text"))
    return cell, dev, rt, stall, a


def test_a_schema_operation_on_one_entity_does_not_hold_up_data_writes_to_another(app_a, monkeypatch) -> None:
    """A is stopped holding the schema lock and entity A's exclusive entity
    lock; a write to entity B is not held up by either."""
    cell, dev, rt, stall, a = _stalled_add_field(app_a, monkeypatch, "ea", "eb")
    try:
        b = _Run(lambda: rt.insert("eb", {"title": "x"}))
        b.done.wait(3.0)
        b_done_while_a_stopped = b.done.is_set()
        stall.release.set()
        a.finish()
        b.finish()
        assert b_done_while_a_stopped, "a write to entity B waited for a schema operation on entity A"
    finally:
        stall.release.set()
        close_cell(cell)


def test_a_query_is_not_held_by_a_schema_operations_locks(app_a, monkeypatch) -> None:
    """A is stopped before its DDL, holding the schema lock and entity A's
    exclusive entity lock (no table lock yet); a query on that very entity
    takes neither lock and is answered."""
    cell, dev, rt, stall, a = _stalled_add_field(app_a, monkeypatch, "ea")
    try:
        q = _Run(lambda: rt.read("ea"))
        q.done.wait(3.0)
        answered_while_a_stopped = q.done.is_set()
        stall.release.set()
        a.finish()
        q.finish()
        assert answered_while_a_stopped, "a query waited for a lock a schema operation holds"
    finally:
        stall.release.set()
        close_cell(cell)


def test_a_write_waiting_for_an_entity_lock_is_cut_by_the_deadline(app_a, monkeypatch) -> None:
    """A holds entity A's exclusive entity lock; a write to the same entity
    from a request with a 300 ms budget waits for the shared lock and is
    answered `LIMIT_EXCEEDED(execution_ms)` when the budget is spent."""
    cell, dev, rt, stall, a = _stalled_add_field(app_a, monkeypatch, "ea")
    cell_b = _cell(app_a, max_execution_ms=300)
    _dev_b, rt_b = _sessions(cell_b, app_a)
    try:
        b = _Run(lambda: rt_b.insert("ea", {"title": "x"}))
        if not b.done.wait(4.0):
            stall.release.set()  # safety: never hang the suite
        stall.release.set()
        a.finish()
        with pytest.raises(ResourceLimitError) as excinfo:
            b.finish()
        assert excinfo.value.details == {"limit_class": "execution_ms"}
    finally:
        stall.release.set()
        close_cell(cell)
        close_cell(cell_b)


# ------------------------------------------- 53 / 54: pool failure mapping
def test_a_pool_wait_that_outlasts_the_deadline_is_limit_exceeded_execution_ms(app_a) -> None:
    cell = _cell(app_a, pool_size=1, max_execution_ms=300)
    dev, rt = _sessions(cell, app_a)
    held = cell._backend._developer_pool.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(ResourceLimitError) as excinfo:
            rt.catalog()
        assert excinfo.value.details == {"limit_class": "execution_ms"}
        assert time.monotonic() - started < 5.0
    finally:
        cell._backend._developer_pool.release(held)
        close_cell(cell)


def test_a_database_that_cannot_be_reached_is_service_unavailable(app_a) -> None:
    unreachable = "postgresql://nobody:unused@127.0.0.1:1/none"
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=unreachable)
    cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend)
    _dev, rt = _sessions(cell, app_a)
    try:
        with pytest.raises(StorageTransientError) as excinfo:
            rt.catalog()
        assert _classify(excinfo.value) == "SERVICE_UNAVAILABLE"
    finally:
        close_cell(cell)


# --------------------------------------------- 55 / 56: 40P01 and 40001
def test_a_deadlock_between_two_batches_is_service_unavailable_not_a_client_error(app_a, monkeypatch) -> None:
    """Two batches update the same two rows in opposite orders, each holding
    its first row when the other asks for it: PostgreSQL ends one with 40P01.
    The loser is answered with the transient-storage error (503), never
    `VALIDATION_FAILED`; the winner commits."""
    cell, dev, rt = _setup(app_a)
    dev.create_collection("dl", {"id": "integer", "v": "integer"})
    rt.insert("dl", {"id": 1, "v": 0})
    rt.insert("dl", {"id": 2, "v": 0})
    barrier = threading.Barrier(2, timeout=8)
    original = PostgresBackend.update_in_transaction
    seen = threading.local()

    def meeting(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        seen.n = getattr(seen, "n", 0) + 1
        if seen.n == 1:
            barrier.wait()
        return result

    monkeypatch.setattr(PostgresBackend, "update_in_transaction", meeting)

    def batch(first: int, second: int):
        return lambda: rt.transact([
            {"type": "update", "collection": "dl", "values": {"v": 1}, "filters": [Filter("id", "eq", first)]},
            {"type": "update", "collection": "dl", "values": {"v": 2}, "filters": [Filter("id", "eq", second)]},
        ])

    try:
        runs = [_Run(batch(1, 2)), _Run(batch(2, 1))]
        outcomes = []
        for run in runs:
            assert run.done.wait(30)
            outcomes.append(run.error)
        losers = [e for e in outcomes if e is not None]
        assert len(losers) == 1, outcomes
        assert isinstance(losers[0], StorageTransientError), repr(losers[0])
        assert _classify(losers[0]) == "SERVICE_UNAVAILABLE"
    finally:
        close_cell(cell)


def test_a_serialization_failure_is_service_unavailable_not_a_client_error(app_a, monkeypatch) -> None:
    cell, _dev, rt = _setup(app_a, "sf")
    original = bp_module._execute

    def failing(cursor, statement, params=()):
        text = statement.as_string(cursor) if hasattr(statement, "as_string") else str(statement)
        if text.startswith("INSERT INTO"):
            raise psycopg.errors.SerializationFailure("synthetic")
        return original(cursor, statement, params)

    monkeypatch.setattr(bp_module, "_execute", failing)
    try:
        with pytest.raises(StorageTransientError):
            rt.transact([{"type": "insert", "collection": "sf", "values": {"title": "x"}}])
    finally:
        close_cell(cell)


# ----------------------------------------------- 57: catalog reads in scope
def test_catalog_reads_run_inside_the_scope_transaction_without_committing_or_setting_timeouts(app_a, monkeypatch) -> None:
    """All eight catalog reads run in the request's one open transaction:
    none commits it (it is still in a transaction afterwards) and none sets
    a timeout of its own (the one `SET LOCAL` pair is the scope's)."""
    cell, _dev, _rt = _setup(app_a, "cat")
    backend = cell._backend
    timeouts: list[int] = []
    original = PostgresBackend._set_timeouts
    monkeypatch.setattr(PostgresBackend, "_set_timeouts",
                        lambda self, cur, ms: (timeouts.append(ms), original(self, cur, ms))[1])
    try:
        with backend.request_scope("schema") as scope:
            commits = []
            real_commit = scope.main.commit
            scope.main.commit = lambda: (commits.append(1), real_commit())[1]
            try:
                backend.schema_count(scope=scope)
                backend.field_domains("cat", scope=scope)
                backend.field_types("cat", scope=scope)
                backend.all_field_types(scope=scope)
                backend.field_constraints("cat", scope=scope)
                backend.field_types_and_constraints("cat", scope=scope)
                backend.all_field_constraints(scope=scope)
                backend.schema_revision(scope=scope)
            finally:
                scope.main.commit = real_commit
            assert commits == []
            main_conn = scope.main
            assert main_conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        assert len(timeouts) == 1, timeouts
    finally:
        close_cell(cell)


# ---------------------------------------- 58: timeout from the deadline
def test_the_scope_sets_its_timeouts_from_the_deadline_not_the_constructed_value(app_a, monkeypatch) -> None:
    """A schema operation of a deployment whose constructed bound is 60 s
    but whose request has 2 s runs with statement and lock timeouts of at
    most 2 s on every connection it borrowed."""
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn,
                              max_execution_ms=60_000)
    cell = ApplicationCell(app_a.app_id, FoundationConfig(max_execution_ms=2000), backend=backend)
    dev, _rt = _sessions(cell, app_a)
    seen: list[int] = []
    original = PostgresBackend._set_timeouts
    monkeypatch.setattr(PostgresBackend, "_set_timeouts",
                        lambda self, cur, ms: (seen.append(ms), original(self, cur, ms))[1])
    try:
        dev.create_collection("dd", {"title": "text"})
        assert seen, "no timeout was set (空振り)"
        assert all(0 < ms <= 2000 for ms in seen), seen
    finally:
        close_cell(cell)


# ---------------------------------------- 59 / 60: lock statements & keys
def test_a_batch_takes_its_entity_locks_in_one_sorted_deduplicated_statement(app_a, monkeypatch) -> None:
    cell, _dev, rt = _setup(app_a, "ea", "eb", "ec")
    seen: list[tuple[str, list]] = []
    original = bp_module._execute

    def spying(cursor, statement, params=()):
        text = statement.as_string(cursor) if hasattr(statement, "as_string") else str(statement)
        if "advisory_xact_lock_shared" in text:
            seen.append((text, list(params)))
        return original(cursor, statement, params)

    monkeypatch.setattr(bp_module, "_execute", spying)
    try:
        rt.transact([{"type": "insert", "collection": name, "values": {"title": "x"}} for name in ("eb", "ea", "eb", "ec")])
        assert len(seen) == 1, seen
        text, params = seen[0]
        assert "pg_try_advisory_xact_lock_shared" in text and "unnest" in text
        assert params == [76176101, ["ea", "eb", "ec"]]
    finally:
        close_cell(cell)


def test_the_schema_and_entity_lock_keys_are_the_documented_values_and_distinct(app_a) -> None:
    assert bp_module._SCHEMA_SERIALIZATION_LOCK_KEY == 761761763
    assert bp_module._ENTITY_LOCK_NAMESPACE == 76176101
    others = {bp_module._IDEMPOTENCY_KEY_LOCK_NAMESPACE, bp_module._IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY, 761761761}
    assert not others & {bp_module._SCHEMA_SERIALIZATION_LOCK_KEY, bp_module._ENTITY_LOCK_NAMESPACE}
    cell = _cell(app_a)
    try:
        with cell._backend.request_scope("schema") as scope:
            cell._backend.lock_schema(scope=scope)
            with scope.main.cursor() as cur:
                cur.execute("SELECT classid, objid, objsubid FROM pg_locks "
                            "WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
                rows = cur.fetchall()
        assert rows == [(0, 761761763, 1)], rows
    finally:
        close_cell(cell)


# ------------------------------------------------- 61: replay at the bound
def test_a_resend_at_the_schema_object_bound_is_answered_from_its_record(app_a) -> None:
    cell = ApplicationCell(app_a.app_id, FoundationConfig(max_schema_objects=1),
                           backend=PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn))
    dev, _rt = _sessions(cell, app_a)
    try:
        first = dev.create_entity("only", {"title": "text"}, idempotency_key="bound-1")
        assert first["committed"] is True
        replay = dev.create_entity("only", {"title": "text"}, idempotency_key="bound-1")
        assert replay == first
        with pytest.raises(ConflictError):
            dev.create_entity("other", {"title": "text"}, idempotency_key="bound-1")
        with pytest.raises(ResourceLimitError) as excinfo:
            dev.create_collection("another", {"title": "text"})
        assert excinfo.value.details == {"limit_class": "schema_objects"}
    finally:
        close_cell(cell)


# -------------------------------------------- 64: construction is lazy
def test_constructing_a_postgres_backend_opens_no_connection(app_a) -> None:
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn,
                              application_id=app_a.app_id)
    try:
        for pool in (backend._runtime_pool, backend._developer_pool):
            assert pool._created == 0
            assert pool.platform_stats()["sessions"] == 0
        backend.verify_platform_upgrades()
        assert backend._runtime_pool.platform_stats()["sessions"] == 1
        assert backend._developer_pool.platform_stats()["sessions"] == 0
    finally:
        backend.close()


# --------------------------------------------------- 66: borrowing order
def test_a_write_and_a_schema_operation_on_one_entity_with_pools_of_one_do_not_wait_in_a_ring(app_a, monkeypatch) -> None:
    """Pools of one connection per role. A (schema operation on entity E)
    holds the developer connection and is held just before it takes its
    entity lock; B (write to E) needs the developer connection too. Every
    connection is borrowed before any lock, so B waits for the connection
    holding no lock and A is never blocked by B: after A is released both
    finish within their budget. Were B to take its shared entity lock
    before borrowing the developer connection, A would wait for that lock
    and B for A's connection until the deadline."""
    cell, dev, rt = _setup(app_a, "ea", pool_size=1)
    original = PostgresBackend.lock_entities
    holding, release = threading.Event(), threading.Event()
    armed: list[threading.Thread] = []

    def held(self, names, *, shared, scope):
        if not shared and armed and threading.current_thread() is armed[0] and not holding.is_set():
            holding.set()
            assert release.wait(_WAIT_S)
        return original(self, names, shared=shared, scope=scope)

    monkeypatch.setattr(PostgresBackend, "lock_entities", held)
    try:
        def a_call():
            armed.append(threading.current_thread())
            return dev.add_field("ea", "extra", "text")

        a = _Run(a_call)
        assert holding.wait(_WAIT_S)
        b = _Run(lambda: rt.insert("ea", {"title": "x"}))
        time.sleep(0.3)
        release.set()
        assert a.finish()["committed"] is True
        b.finish()
    finally:
        release.set()
        close_cell(cell)
