"""Cross-cell (process-to-process) check-then-act windows of the
PostgreSQL data plane, reproduced deterministically with TWO independent
`ApplicationCell` instances (each its own `PostgresBackend` connection
pair) pointed at ONE provisioned application database -- the shape of two
server processes serving the same application. Nothing in-process can
serialize the two cells (each has its own `_lock`), so only what
PostgreSQL itself enforces across connections can.

The four windows (design docs/design/MITATEDB_APPLICATION_SERIALIZATION_
V0_1.md section 2.5):

- window 1: a plan token is checked against the current revision by one
  transaction, and the DDL that follows runs in another; a schema change
  of a DIFFERENT entity landing in between leaves the stale plan applied.
- window 2: `alter_field` reads the registry row before it takes its table
  lock and writes both `enum_json` and `nullable` afterwards; a concurrent
  `alter_field` of the same field loses its half of the update.
- window 3: a data write validates against the declared constraints in
  pass 1 and executes in pass 2; an `alter_field` landing in between
  leaves a row that violates the new constraint.
- window 4: `create_collection` compares the table count with
  `max_schema_objects` and creates the table in a later step; a concurrent
  `create_collection` lands in between and the count exceeds the bound.

Stop technique: no hook exists in product code. A test-local `_Stall`
wraps the module-level `backend_postgres._execute` and, for ONE armed
thread only (thread A), pauses inside the wrapper on a `threading.Event`
when the statement about to run is the one named by the test (the DDL or
DML statement itself, or `LOCK TABLE` for window 2). Whatever lock, plan
check or validation a request takes or does, it does before that
statement, so the stop point does not depend on how the request is built.
The wait for A to arrive is bounded and fails with an `AssertionError`
naming the wrap point. B's not-having-completed is observed through a
bounded window (`_B_WINDOW_S`) and then confirmed by finding a backend of
the application database waiting on a PostgreSQL lock
(`pg_stat_activity.wait_event_type = 'Lock'`, bounded wait); a B that is
neither finished nor lock-waiting fails the test.

Every test asserts the same two-branch shape. If B completed while A was
stopped, A must have been refused and must have done nothing (or the
invariant the window breaks must still hold). If B did not complete while
A was stopped, then after the release A and B both run, in that order, and
their results must agree with each other.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

import psycopg
import pytest

import mitatedb_api.backend_postgres as backend_postgres_module
from mitatedb_api import FoundationConfig, Role
from mitatedb_api.auth import Principal
from mitatedb_api.cell import ApplicationDeveloper, ApplicationRuntime
from mitatedb_api.errors import ConflictError, FoundationError, PreconditionFailedError, ResourceLimitError

from .test_postgres import app_a, close_cell, make_cell, platform  # noqa: F401 (fixtures) -- RELATIVE import, see test_idempotency_concurrency.py's identical import

# Bound on how long the test waits for thread A to arrive at its stop point
# before concluding the wrap point is never reached (a wrong wrap target is a
# test defect, not slowness).
_LOCK_TIMEOUT_S = 10.0
# Bound on how long the test waits, while A is stopped, to see whether B
# completes. Longer than `test_idempotency_concurrency.py`'s 0.3 s: here a
# B that is NOT blocked must be seen to finish (a few DDL round trips), and
# a window shorter than that would misread a slow, unblocked B as blocked.
_B_WINDOW_S = 1.0


def _pair(app, config: FoundationConfig | None = None):
    """TWO INDEPENDENT `ApplicationCell`s, each with its own
    `PostgresBackend` connection pair, on the same application database --
    `test_idempotency_concurrency.py::_pg_pair`'s own shape, see its
    docstring for why a single shared cell would serialize on the cell's
    own Python lock and hide every window below."""
    cell_a = make_cell(app, config)
    cell_b = make_cell(app, config)
    dev_a = ApplicationDeveloper(cell_a, Principal(application_id=app.app_id, credential_id="dev-a", role=Role.DEVELOPER))
    dev_b = ApplicationDeveloper(cell_b, Principal(application_id=app.app_id, credential_id="dev-b", role=Role.DEVELOPER))
    rt_a = ApplicationRuntime(cell_a, Principal(application_id=app.app_id, credential_id="rt-a", role=Role.RUNTIME))
    return cell_a, cell_b, dev_a, dev_b, rt_a


class _Stall:
    """Pauses ONE armed thread (A), once, at a named wrap point, and lets
    every other thread (B, the main thread) pass straight through."""

    def __init__(self) -> None:
        self.holding = threading.Event()
        self.release = threading.Event()
        self.thread: threading.Thread | None = None
        self.point = "<not installed>"
        self._used = False

    def install(self, monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, *,
                when: Callable[[tuple, dict], bool] | None = None, statement: str = "") -> None:
        original = getattr(owner, name)
        self.point = f"{getattr(owner, '__name__', repr(owner))}.{name}" + (f" at its {statement} statement" if statement else "")
        stall = self

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if (not stall._used and threading.current_thread() is stall.thread
                    and (when is None or when(args, kwargs))):
                stall._used = True
                stall.holding.set()
                assert stall.release.wait(timeout=_LOCK_TIMEOUT_S), "test setup: release was never signaled"
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, _wrapped)


class _Outcome:
    def __init__(self) -> None:
        self.results: dict[str, Any] = {}
        self.errors: dict[str, BaseException] = {}
        self.b_done_while_a_stopped = False


def _lock_waiters(admin_dsn: str, database: str) -> int:
    """Backends of `database` currently waiting on a PostgreSQL lock,
    counted over a separate superuser connection (outside every product
    path)."""
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND pid <> pg_backend_pid()", [database])
            return cur.fetchone()[0]


def _run_window(stall: _Stall, a_call: Callable[[], Any], b_call: Callable[[], Any], *,
                admin_dsn: str, database: str) -> _Outcome:
    """Runs A until it stops at the wrap point, then runs B. B is given
    `_B_WINDOW_S`; if it has not finished by then it must be seen waiting
    on a PostgreSQL lock (bounded by `_LOCK_TIMEOUT_S`; a B that finishes
    during that wait counts as finished). Then releases A and joins both."""
    outcome = _Outcome()
    done = {"A": threading.Event(), "B": threading.Event()}

    def worker(name: str, call: Callable[[], Any]) -> None:
        try:
            outcome.results[name] = call()
        except BaseException as exc:  # noqa: BLE001 -- recorded and judged by the test body
            outcome.errors[name] = exc
        finally:
            done[name].set()

    thread_a = threading.Thread(target=worker, args=("A", a_call))
    stall.thread = thread_a
    threads = [thread_a]
    thread_a.start()
    try:
        assert stall.holding.wait(timeout=_LOCK_TIMEOUT_S), f"thread A never reached the stall point {stall.point}"
        thread_b = threading.Thread(target=worker, args=("B", b_call))
        threads.append(thread_b)
        thread_b.start()
        outcome.b_done_while_a_stopped = done["B"].wait(timeout=_B_WINDOW_S)
        if not outcome.b_done_while_a_stopped:
            give_up_at = time.monotonic() + _LOCK_TIMEOUT_S
            while not outcome.b_done_while_a_stopped and not _lock_waiters(admin_dsn, database):
                assert time.monotonic() < give_up_at, (
                    f"B neither completed nor is waiting on a PostgreSQL lock while A is stopped at {stall.point}")
                outcome.b_done_while_a_stopped = done["B"].wait(timeout=0.05)
    finally:
        stall.release.set()
        for thread in threads:
            thread.join(timeout=_LOCK_TIMEOUT_S)
    assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
    return outcome


def _raw(app, query: str, params: list | None = None) -> list[tuple]:
    """A fresh autocommit connection as the application's own developer
    role (the owner of every table), independent of both cells."""
    with psycopg.connect(app.developer_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            return cur.fetchall()


def _revision(app) -> int:
    return _raw(app, "SELECT revision FROM _mdb_schema_revision WHERE id = TRUE")[0][0]


def _columns(app, table: str) -> set[str]:
    return {row[0] for row in _raw(
        app, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s", [table])}


def _schema_object_count(app) -> int:
    return _raw(
        app, "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name NOT LIKE %s",
        [r"\_mdb\_%"])[0][0]


def _statement_starts_with(prefix: str, *, containing: str = "") -> Callable[[tuple, dict], bool]:
    """A `_Stall.install` filter for `backend_postgres._execute(cursor,
    statement, ...)`: the rendered statement starts with `prefix` and
    contains `containing` (used to pick one table's quoted name)."""
    def _when(args: tuple, kwargs: dict) -> bool:
        cursor, statement = args[0], args[1]
        text = statement if isinstance(statement, str) else statement.as_string(cursor)
        text = text.lstrip()
        return text.upper().startswith(prefix) and containing in text
    return _when


def test_window1_plan_is_checked_against_the_revision_inside_the_ddl_serialization(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Window 1. A: `add_field` on entity e1 carrying a dry-run plan,
    stopped at its `ALTER TABLE ... ADD COLUMN` statement -- after the plan
    was checked against the current revision, before the DDL runs. B:
    `add_field` on a DIFFERENT entity e2 (no plan), which advances the
    revision by one. B is a different entity so only an application-wide
    schema serialization (not a per-entity one) can close this window."""
    cell_a, cell_b, dev_a, dev_b, _ = _pair(app_a)
    try:
        dev_a.create_collection("e1", {"title": "text"})
        dev_a.create_collection("e2", {"title": "text"})
        revision_0 = _revision(app_a)
        plan = dev_a.add_field("e1", "extra", "text", dry_run=True)["plan"]
        assert plan, "the dry run must have produced a plan token"
        assert _revision(app_a) == revision_0, "a dry run must not advance the revision"

        stall = _Stall()
        stall.install(monkeypatch, backend_postgres_module, "_execute",
                      when=_statement_starts_with("ALTER TABLE", containing='"e1" ADD COLUMN'),
                      statement="ALTER TABLE e1 ADD COLUMN")
        outcome = _run_window(
            stall,
            lambda: dev_a.add_field("e1", "extra", "text", plan=plan),
            lambda: dev_b.add_field("e2", "other", "text"),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        assert "B" in outcome.results, f"B must succeed in either branch: {outcome.errors}"
        assert "other" in _columns(app_a, "e2")
        if outcome.b_done_while_a_stopped:
            error = outcome.errors.get("A")
            assert isinstance(error, PreconditionFailedError), (
                f"B completed while A held its plan: A must be refused with PRECONDITION_FAILED, got "
                f"{error!r} / {outcome.results.get('A')!r}")
            assert error.details == {"violated_declaration": "plan"}
            assert "extra" not in _columns(app_a, "e1"), "a refused A must add nothing to e1"
            assert _revision(app_a) == revision_0 + 1
        else:
            assert "A" in outcome.results, f"B did not complete while A held: A must then succeed, got {outcome.errors}"
            assert "extra" in _columns(app_a, "e1")
            assert _revision(app_a) == revision_0 + 2, "A and B both committed: the revision advances by two"
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_window2_concurrent_alter_field_calls_do_not_lose_each_others_update(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Window 2. A: `alter_field(e, f, enum=[x, y])`, stopped at the
    `LOCK TABLE` statement of `backend_postgres._execute` -- after the
    registry row was read, before the UPDATE. B: `alter_field(e, f,
    nullable=False)` on the SAME field. Whichever way the two interleave,
    the registry row for `f` must carry A's enum AND B's nullable."""
    cell_a, cell_b, dev_a, dev_b, _ = _pair(app_a)
    try:
        dev_a.create_collection("e", {"f": "text"})

        stall = _Stall()
        stall.install(monkeypatch, backend_postgres_module, "_execute", when=_statement_starts_with("LOCK TABLE"), statement="LOCK TABLE")
        outcome = _run_window(
            stall,
            lambda: dev_a.alter_field("e", "f", enum=["x", "y"]),
            lambda: dev_b.alter_field("e", "f", nullable=False),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        assert not outcome.errors, f"both alters are valid and must succeed: {outcome.errors}"
        assert set(outcome.results) == {"A", "B"}
        ((enum_json, nullable),) = _raw(
            app_a, "SELECT enum_json, nullable FROM _mdb_field_types WHERE entity = %s AND field = %s", ["e", "f"])
        assert enum_json is not None and json.loads(enum_json) == ["x", "y"], (
            f"A's enum was lost (registry enum_json={enum_json!r}, B completed while A stopped: "
            f"{outcome.b_done_while_a_stopped})")
        assert not nullable, (
            f"B's nullable=False was lost (registry nullable={nullable!r}, B completed while A stopped: "
            f"{outcome.b_done_while_a_stopped})")
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_window3_data_write_validated_before_an_alter_is_not_committed_against_the_new_constraint(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Window 3. A: `transact([insert title=v])` on `notes` (`title` has
    enum [v, w]), stopped at its `INSERT INTO notes` statement -- the
    request was validated against the old enum, the row is not yet written. B:
    `alter_field(notes, title, enum=[w])`, which removes `v`."""
    cell_a, cell_b, dev_a, dev_b, rt_a = _pair(app_a)
    try:
        dev_a.create_collection("notes", {"title": "text"})
        dev_a.alter_field("notes", "title", enum=["v", "w"])

        stall = _Stall()
        stall.install(monkeypatch, backend_postgres_module, "_execute",
                      when=_statement_starts_with("INSERT INTO", containing='"notes"'),
                      statement="INSERT INTO notes")
        outcome = _run_window(
            stall,
            lambda: rt_a.transact([{"type": "insert", "collection": "notes", "values": {"title": "v"}}]),
            lambda: dev_b.alter_field("notes", "title", enum=["w"]),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        titles = [row[0] for row in _raw(app_a, "SELECT title FROM notes")]
        a_ok = "A" in outcome.results
        b_ok = "B" in outcome.results
        if outcome.b_done_while_a_stopped:
            assert b_ok, f"B had no row to conflict with and must succeed: {outcome.errors.get('B')!r}"
            assert isinstance(outcome.errors.get("A"), FoundationError), (
                f"B narrowed the enum while A was stopped: A must be refused, got {outcome.results.get('A')!r}")
            assert titles == [], f"a refused A must leave no row, found {titles!r}"
        else:
            assert a_ok, f"B did not complete while A held: A must then succeed, got {outcome.errors.get('A')!r}"
            assert titles == ["v"]
            assert isinstance(outcome.errors.get("B"), ConflictError), (
                f"B's scan must see A's row and refuse, got {outcome.results.get('B')!r} / {outcome.errors.get('B')!r}")
        # The invariant the window breaks, in both branches: the stored rows agree with the declared enum.
        ((enum_json,),) = _raw(
            app_a, "SELECT enum_json FROM _mdb_field_types WHERE entity = %s AND field = %s", ["notes", "title"])
        declared = json.loads(enum_json)
        assert all(title in declared for title in titles), f"rows {titles!r} violate the declared enum {declared!r}"
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_window4_concurrent_create_collection_cannot_exceed_max_schema_objects(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Window 4. `max_schema_objects` is the current table count plus one.
    A: `create_collection(e1)`, stopped at its
    `CREATE TABLE e1` statement -- after the limit check, before the DDL. B: `create_collection(e2)`. Exactly one of the two may
    succeed and the other must be `LIMIT_EXCEEDED` (`schema_objects`)."""
    current = _schema_object_count(app_a)
    assert current == 0, "a freshly provisioned application holds no entity table"
    limit = current + 1
    config = FoundationConfig(max_schema_objects=limit)
    cell_a, cell_b, dev_a, dev_b, _ = _pair(app_a, config)
    try:
        stall = _Stall()
        stall.install(monkeypatch, backend_postgres_module, "_execute",
                      when=_statement_starts_with("CREATE TABLE", containing='"e1"'),
                      statement="CREATE TABLE e1")
        outcome = _run_window(
            stall,
            lambda: dev_a.create_collection("e1", {"title": "text"}),
            lambda: dev_b.create_collection("e2", {"title": "text"}),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        limit_errors = [name for name, error in outcome.errors.items() if isinstance(error, ResourceLimitError)]
        assert len(outcome.results) == 1 and len(limit_errors) == 1, (
            f"exactly one create must succeed and one be LIMIT_EXCEEDED: results={sorted(outcome.results)} "
            f"errors={ {name: repr(error) for name, error in outcome.errors.items()} } "
            f"(B completed while A stopped: {outcome.b_done_while_a_stopped})")
        assert outcome.errors[limit_errors[0]].details == {"limit_class": "schema_objects"}
        assert _schema_object_count(app_a) <= limit, (
            f"schema objects exceeded the bound {limit}: {_schema_object_count(app_a)} "
            f"(B completed while A stopped: {outcome.b_done_while_a_stopped})")
    finally:
        close_cell(cell_a)
        close_cell(cell_b)
