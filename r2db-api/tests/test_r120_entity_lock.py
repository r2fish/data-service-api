"""The entity-scoped advisory lock of `PostgresCell`: a data operation
(`transact`) takes it SHARED, every schema operation (`apply_schema`) takes
it EXCLUSIVE, both before the catalog is read.

Without it a data operation validates its values against the declaration it
read in `_load_catalog` and writes them later with no lock on the entity in
between, so a schema operation that narrows the same entity's declaration
(`alter_field` with a smaller `enum`, `add_field` with `nullable: false`)
can commit in that gap and leave a row that breaks the declaration. The
window is reproduced below with TWO independent `PostgresCell` instances on
one application database (the shape of two service instances), the data
operation stopped at the entry of `PostgresCell._insert`, i.e. after
validation and before the first write.

Stop technique, bounds and the two-cell pair are `test_r102_schema_
windows.py`'s (`_Stall`, `_pair`). The observation here is narrower than
that file's: B's wait must be seen as `wait_event = 'advisory'` (the entity
lock), not as any lock wait, and an unobserved wait fails the test.

Each of the two window tests asserts the invariant first (the stored rows
agree with the declaration the catalog reports) and then that B was seen
waiting while A was stopped, so a run without the lock fails on the data it
leaves behind, not only on the wait. The order test pins where in a request
every advisory lock is taken.
"""
from __future__ import annotations

import threading
import time
import types
from typing import Any, Callable

import psycopg
import pytest
from psycopg import sql

from r2db_api import postgres as postgres_module
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell

from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)
from test_r102_schema_windows import _B_WINDOW_S, _LOCK_OBSERVE_S, _LOCK_TIMEOUT_S, _Stall, _pair

LIMITS = ResourceLimits()


def _advisory_waiters(admin_dsn: str, database: str) -> int:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND wait_event = 'advisory' AND pid <> pg_backend_pid()", [database])
            return cur.fetchone()[0]


class _Window:
    def __init__(self) -> None:
        self.results: dict[str, Any] = {}
        self.errors: dict[str, BaseException] = {}
        self.b_done_while_a_stopped = False
        self.advisory_waiters_seen = 0


def _run_entity_window(stall: _Stall, a_call: Callable[[], Any], b_call: Callable[[], Any], *, admin_dsn: str, database: str) -> _Window:
    """Runs A until it stops at the wrap point, then runs B. B is given `_B_WINDOW_S`; if it has not finished by then, the number of backends waiting on an ADVISORY lock is read (bounded by `_LOCK_OBSERVE_S`) while A is still stopped. Then A is released and both are joined. Nothing is asserted about B here: the caller judges the outcome."""
    window = _Window()
    done = {"A": threading.Event(), "B": threading.Event()}

    def worker(name: str, call: Callable[[], Any]) -> None:
        try:
            window.results[name] = call()
        except BaseException as exc:  # noqa: BLE001 -- recorded and judged by the test body
            window.errors[name] = exc
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
        window.b_done_while_a_stopped = done["B"].wait(timeout=_B_WINDOW_S)
        if not window.b_done_while_a_stopped:
            give_up_at = time.monotonic() + _LOCK_OBSERVE_S
            while not window.advisory_waiters_seen and not window.b_done_while_a_stopped and time.monotonic() < give_up_at:
                window.advisory_waiters_seen = _advisory_waiters(admin_dsn, database)
                window.b_done_while_a_stopped = done["B"].wait(timeout=0.05)
        assert not done["A"].is_set(), f"A finished while it was to be stopped at {stall.point}"
    finally:
        stall.release.set()
        for thread in threads:
            thread.join(timeout=_LOCK_TIMEOUT_S)
    assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
    return window


def _raw_column(app: types.SimpleNamespace, entity: str, column: str) -> list[Any]:
    with psycopg.connect(app.developer_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT {c} FROM public.{t} ORDER BY id").format(c=sql.Identifier(column), t=sql.Identifier(entity)))
            return [row[0] for row in cur.fetchall()]


def _constraints(cell: PostgresCell, entity: str, field: str) -> dict[str, Any] | None:
    for entry in cell.catalog():
        if entry["entity"] == entity:
            return entry["field_constraints"].get(field)
    return None


def test_a_narrowing_alter_field_cannot_commit_between_a_data_operations_validation_and_its_write(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """A: an unkeyed `transact` inserting `title = v` into `notes` (declared
    `enum: [v, w]`), stopped at the entry of `PostgresCell._insert` -- the
    values were validated against the old enum, nothing is written. B:
    `alter_field(notes.title, enum=[w])`, which removes `v`, through the
    other cell. B must wait on the entity lock until A has committed; B's
    scan then finds A's row and refuses with CONFLICT, and no row outside
    the declared enum remains."""
    cell_a, cell_b = _pair(app_a)
    try:
        cell_a.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["title"], "field_types": {"title": "string"}}, developer=True, limits=LIMITS)
        cell_a.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["v", "w"]}, developer=True, limits=LIMITS)

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_insert")
        window = _run_entity_window(
            stall,
            lambda: cell_a.transact("notes", [{"operation": "insert", "values": {"title": "v"}}], LIMITS),
            lambda: cell_b.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["w"]}, developer=True, limits=LIMITS),
            admin_dsn=platform.admin_dsn, database=app_a.database)

        titles = _raw_column(app_a, "notes", "title")
        declared = (_constraints(cell_a, "notes", "title") or {}).get("enum")
        assert declared is None or all(title in declared for title in titles), (
            f"rows {titles!r} break the declared enum {declared!r} (B completed while A was stopped: {window.b_done_while_a_stopped})")
        assert window.advisory_waiters_seen >= 1 and not window.b_done_while_a_stopped, (
            f"B was not seen waiting on an advisory lock while A was stopped between validation and write "
            f"(B completed while A stopped: {window.b_done_while_a_stopped}, advisory waiters seen: {window.advisory_waiters_seen})")
        assert "A" in window.results, f"A held the entity first and must succeed: {window.errors.get('A')!r}"
        assert titles == ["v"]
        refusal = window.errors.get("B")
        assert isinstance(refusal, FoundationError) and refusal.code == "CONFLICT", f"B must be refused with CONFLICT, got {refusal!r} / {window.results.get('B')!r}"
        assert refusal.details == {"field": "title", "violated_declaration": "enum"}
        assert declared == ["v", "w"], "a refused B must leave the enum as it was"
    finally:
        cell_a.close()
        cell_b.close()


def test_an_add_field_nullable_false_cannot_commit_between_a_data_operations_validation_and_its_write(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """A: a keyed `transact` inserting a row into `notes` (no `extra` field
    yet), stopped at the entry of `PostgresCell._insert`. B:
    `add_field(notes.extra, nullable=false)` through the other cell. B must
    wait on the entity lock until A has committed; B's existing-row check
    then finds A's row and refuses with CONFLICT, so no row holds null in a
    field declared `nullable: false`. (A is keyed so that the keyed path is
    also driven; the order of the locks is pinned by
    ::test_every_request_takes_its_advisory_locks_in_the_one_global_order.)"""
    cell_a, cell_b = _pair(app_a)
    try:
        cell_a.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["title"], "field_types": {"title": "string"}}, developer=True, limits=LIMITS)
        insert = [{"operation": "insert", "values": {"title": "t"}}]

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_insert")
        window = _run_entity_window(
            stall,
            lambda: cell_a.transact("notes", insert, LIMITS, plan_request={"entity": "notes", "operations": insert}, idempotency_key="key-a", request_id="rid-a"),
            lambda: cell_b.apply_schema({"operation": "add_field", "entity": "notes", "field": "extra", "nullable": False}, developer=True, limits=LIMITS),
            admin_dsn=platform.admin_dsn, database=app_a.database)

        titles = _raw_column(app_a, "notes", "title")
        declared = _constraints(cell_a, "notes", "extra")
        if declared is not None and declared["nullable"] is False:
            extras = _raw_column(app_a, "notes", "extra")
            assert all(value is not None for value in extras), f"{len(extras)} row(s) hold null in `extra`, declared nullable: false (B completed while A was stopped: {window.b_done_while_a_stopped})"
        assert window.advisory_waiters_seen >= 1 and not window.b_done_while_a_stopped, (
            f"B was not seen waiting on an advisory lock while A was stopped between validation and write "
            f"(B completed while A stopped: {window.b_done_while_a_stopped}, advisory waiters seen: {window.advisory_waiters_seen})")
        assert "A" in window.results, f"A held the entity first and must succeed: {window.errors.get('A')!r}"
        assert titles == ["t"]
        refusal = window.errors.get("B")
        assert isinstance(refusal, FoundationError) and refusal.code == "CONFLICT", f"B must be refused with CONFLICT, got {refusal!r} / {window.results.get('B')!r}"
        assert refusal.details == {"field": "extra", "violated_declaration": "nullable"}
        assert declared is None, "a refused B must not have added the field"
    finally:
        cell_a.close()
        cell_b.close()


class _LockTrace:
    """Records, in order, every advisory-lock statement `PostgresCell` issues
    and every `_load_catalog` call, as short labels. The statements are read
    off the single execution choke point (`postgres._run`), so the order is
    the order PostgreSQL received them on the request's connection."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        real_run = postgres_module._run
        real_catalog = PostgresCell._load_catalog
        real_token = PostgresCell._read_catalog_token
        trace = self

        def _run(cursor: Any, statement: Any, params: Any = ()) -> None:
            text = statement.as_string(cursor)
            args = list(params)
            if "pg_advisory_xact_lock_shared(%s, hashtext(%s))" in text:
                assert args[0] == postgres_module._ENTITY_LOCK_NAMESPACE
                trace.events.append(f"entity-shared:{args[1]}")
            elif "pg_advisory_xact_lock(%s, hashtext(%s))" in text:
                if args[0] == postgres_module._ENTITY_LOCK_NAMESPACE:
                    trace.events.append(f"entity-exclusive:{args[1]}")
                else:
                    assert args[0] == postgres_module._IDEMPOTENCY_KEY_LOCK_NAMESPACE
                    trace.events.append("per-key")
            elif "pg_advisory_xact_lock(%s)" in text:
                by_id = {
                    postgres_module._IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY: "count",
                    postgres_module._SCHEMA_SERIALIZATION_ADVISORY_LOCK_KEY: "schema",
                }
                trace.events.append(by_id[args[0]])
            elif "advisory" in text:
                trace.events.append(f"unclassified advisory statement: {text}")
            real_run(cursor, statement, params)

        def _catalog(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
            trace.events.append("catalog")
            return real_catalog(self, *args, **kwargs)

        monkeypatch.setattr(postgres_module, "_run", _run)
        def _token(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
            trace.events.append("catalog")
            return real_token(self, *args, **kwargs)

        monkeypatch.setattr(PostgresCell, "_load_catalog", _catalog)
        # R-82: a data operation reads the catalog through `_catalog`, which reads the (database oid, schema revision) token first and the live catalog only when its copy is not current -- both are catalog reads for the lock order, labelled "catalog" and folded into one by `take`. A schema operation reads the live catalog directly.
        monkeypatch.setattr(PostgresCell, "_read_catalog_token", _token)

    def take(self) -> list[str]:
        events, self.events = self.events, []
        folded: list[str] = []
        for event in events:
            if event == "catalog" and folded and folded[-1] == "catalog":
                continue
            folded.append(event)
        return folded


def test_every_request_takes_its_advisory_locks_in_the_one_global_order(
    app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """The order is per-key < schema < entity < count < catalog read (and
    the table and row locks after it). Pinned on the statements each request
    issues, one connection at a time, so the check does not depend on timing.

    Data operation: per-key, entity SHARED, count, catalog (keyed); entity
    SHARED, catalog (unkeyed); catalog only for a dry run (it writes nothing,
    so there is no window, and a dry run never takes the per-key lock either);
    the per-key lock alone for a replay. Schema operation, all six kinds:
    schema lock, entity EXCLUSIVE, catalog (and per-key before the schema
    lock and count after the entity lock when keyed; a dry run takes the
    schema and entity locks like any other)."""
    cell = make_cell(app_a, pool_size=2)
    trace = _LockTrace(monkeypatch)
    try:
        def schema(operation: dict[str, Any], **kwargs: Any) -> Any:
            return cell.apply_schema(operation, developer=True, limits=LIMITS, plan_request=operation, **kwargs)

        insert = [{"operation": "insert", "values": {"title": "t"}}]
        request = {"entity": "notes", "operations": insert}

        schema({"operation": "create_entity", "entity": "notes", "fields": ["title"], "field_types": {"title": "string"}})
        assert trace.take() == ["schema", "entity-exclusive:notes", "catalog"]
        schema({"operation": "add_field", "entity": "notes", "field": "extra"})
        assert trace.take() == ["schema", "entity-exclusive:notes", "catalog"]
        schema({"operation": "create_index", "entity": "notes", "index": "by_title", "fields": ["title"]})
        assert trace.take() == ["schema", "entity-exclusive:notes", "catalog"]
        schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["t", "u"]})
        assert trace.take() == ["schema", "entity-exclusive:notes", "catalog"]
        # the two destructive kinds are refused for want of a confirmation, which is decided after the catalog read: the locks came first.
        for refused in ({"operation": "drop_index", "entity": "notes", "index": "by_title"}, {"operation": "drop_entity", "entity": "notes"}):
            with pytest.raises(FoundationError):
                schema(refused)
            assert trace.take() == ["schema", "entity-exclusive:notes", "catalog"], refused["operation"]

        keyed_add = {"operation": "add_field", "entity": "notes", "field": "more"}
        schema(keyed_add, idempotency_key="schema-key", request_id="rid-s")
        assert trace.take() == ["per-key", "schema", "entity-exclusive:notes", "count", "catalog"]
        schema({"operation": "add_field", "entity": "notes", "field": "dry"}, dry_run=True)
        dry = trace.take()  # a dry run also reads the catalog once more to describe the result; no lock follows the first catalog read
        assert dry[:3] == ["schema", "entity-exclusive:notes", "catalog"] and set(dry[3:]) <= {"catalog"}, dry

        cell.transact("notes", insert, LIMITS, plan_request=request, idempotency_key="key-1", request_id="rid-1")
        assert trace.take() == ["per-key", "entity-shared:notes", "count", "catalog"]
        cell.transact("notes", insert, LIMITS)
        assert trace.take() == ["entity-shared:notes", "catalog"]
        cell.transact("notes", insert, LIMITS, dry_run=True)
        assert trace.take() == ["catalog"]
        replay = cell.transact("notes", insert, LIMITS, plan_request=request, idempotency_key="key-1", request_id="rid-2")
        assert replay.replayed is True
        assert trace.take() == ["per-key"]
    finally:
        cell.close()

