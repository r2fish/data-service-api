"""The application-wide schema serialization lock of `PostgresCell.apply_schema`
(`_schema_serialization_lock`): the place in a request where it is taken,
and what it is distinct from.

The lock is taken after the idempotency lookup and before the count lock, so
a resent schema operation whose key already has a record answers from the
record and never waits behind the schema lock, and a keyed schema operation
that is only waiting for the schema lock holds no count lock and blocks no
keyed data operation. (A lookup that reaps expired records can still wait on
a row lock another transaction holds on such a record; the lock order does not
change that.) The windows the lock closes (plan, confirmation phrase,
`schema_objects`) are pinned by `test_r102_schema_windows.py`; that a dry run
reads under the lock is pinned below.
"""
from __future__ import annotations

import threading
import time
import types
from typing import Any

import psycopg
import pytest

from r2db_api import ops as ops_module
from r2db_api import postgres as postgres_module
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell

from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()
_WAIT_S = 10.0
# How long a replay is given to answer while another schema operation holds
# the lock. A replay that is not blocked answers in a few round trips.
_REPLAY_WINDOW_S = 5.0


def _advisory_lock_waiters(admin_dsn: str, database: str) -> int:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND wait_event = 'advisory' AND pid <> pg_backend_pid()", [database])
            return cur.fetchone()[0]


def _create(entity: str) -> dict[str, Any]:
    return {"operation": "create_entity", "entity": entity, "fields": ["name"], "field_types": {"name": "string"}}


def test_replay_of_a_recorded_schema_operation_answers_while_another_schema_operation_holds_the_lock(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """A holds the schema lock (an unkeyed `create_entity`, stopped at the
    entry of `_create_entity`, after the lock and the catalog read). B, a
    second unkeyed schema operation, is seen waiting on an advisory lock.
    A keyed `create_entity` that was executed earlier is then resent with
    the same key and the same request: it answers `replayed` with the
    original revision while A and B are still waiting."""
    cell = make_cell(app_a, pool_size=3)
    try:
        recorded_op = _create("recorded")
        executed = cell.apply_schema(
            recorded_op, developer=True, limits=LIMITS, plan_request=recorded_op,
            idempotency_key="replay-key-1", request_id="rid-original")
        assert executed.replayed is False

        holding = threading.Event()
        release = threading.Event()
        holder: dict[str, threading.Thread] = {}
        original = PostgresCell._create_entity

        def _stalled(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
            if threading.current_thread() is holder.get("a") and not holding.is_set():
                holding.set()
                assert release.wait(timeout=_WAIT_S), "test setup: release was never signaled"
            return original(self, *args, **kwargs)

        monkeypatch.setattr(PostgresCell, "_create_entity", _stalled)

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}

        def _worker(name: str, call: Any) -> None:
            try:
                results[name] = call()
            except BaseException as exc:  # noqa: BLE001 -- recorded and judged by the test body
                errors[name] = exc

        def _call_a() -> Any:
            return cell.apply_schema(_create("held_a"), developer=True, limits=LIMITS)

        def _call_b() -> Any:
            return cell.apply_schema(_create("held_b"), developer=True, limits=LIMITS)

        def _call_replay() -> Any:
            return cell.apply_schema(
                recorded_op, developer=True, limits=LIMITS, plan_request=recorded_op,
                idempotency_key="replay-key-1", request_id="rid-resend")

        thread_a = threading.Thread(target=_worker, args=("A", _call_a))
        holder["a"] = thread_a
        thread_b = threading.Thread(target=_worker, args=("B", _call_b))
        thread_r = threading.Thread(target=_worker, args=("R", _call_replay))
        threads = [thread_a, thread_b, thread_r]
        try:
            thread_a.start()
            assert holding.wait(timeout=_WAIT_S), "thread A never reached the stop point PostgresCell._create_entity"
            thread_b.start()
            give_up_at = time.monotonic() + _WAIT_S
            while not _advisory_lock_waiters(platform.admin_dsn, app_a.database):
                assert time.monotonic() < give_up_at, "B, a second schema operation, never waited on the schema lock held by A"
                time.sleep(0.05)
            assert "B" not in results and "B" not in errors, "B finished while A held the schema lock"

            thread_r.start()
            thread_r.join(timeout=_REPLAY_WINDOW_S)
            assert not thread_r.is_alive(), "the replay of a recorded key waited behind a schema operation that holds the schema lock"
            assert "R" in results, f"the replay failed: {errors.get('R')!r}"
            replayed = results["R"]
            assert replayed.replayed is True
            assert replayed.revision == executed.revision
            assert replayed.request_id == "rid-original"
        finally:
            release.set()
            for thread in threads:
                if thread.is_alive() or thread.ident is not None:
                    thread.join(timeout=_WAIT_S)
        assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
        assert not errors, f"A and B must both succeed after the release: {errors}"
        assert {entry["entity"] for entry in cell.catalog()} == {"recorded", "held_a", "held_b"}
    finally:
        cell.close()


def test_the_advisory_lock_ids_of_the_five_serialization_points_are_distinct() -> None:
    """Per-key namespace (2-argument form), entity namespace (2-argument
    form), count lock, schema lock and the bootstrap/reset ritual lock guard
    five independent serialization points: no two may share an id. The count
    lock and the schema lock are both 1-argument `pg_advisory_xact_lock(bigint)`
    keys, so a shared value would make a schema operation and a keyed data
    operation wait on each other; the per-key namespace and the entity
    namespace are both the first argument of the 2-argument form, so a
    shared value would put a client-chosen idempotency key and an entity
    name in one lock space."""
    ids = {
        "per-key namespace": postgres_module._IDEMPOTENCY_KEY_LOCK_NAMESPACE,
        "entity namespace": postgres_module._ENTITY_LOCK_NAMESPACE,
        "count lock": postgres_module._IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY,
        "schema lock": postgres_module._SCHEMA_SERIALIZATION_ADVISORY_LOCK_KEY,
        "ritual lock": ops_module._RITUAL_ADVISORY_LOCK_KEY,
    }
    assert len(set(ids.values())) == len(ids), f"two serialization points share a lock id: {ids}"


def test_the_per_key_lock_uses_the_two_argument_advisory_form() -> None:
    """The per-key lock lives in the 2-argument `pg_advisory_xact_lock(int,
    int)` space, which PostgreSQL records apart from the 1-argument
    `pg_advisory_xact_lock(bigint)` space the count lock and the schema lock
    use -- so a client-chosen key whose `hashtext` happens to equal one of
    those two ids can never wait on them. Pinned on the statement text
    itself, next to the id-distinctness test above.

    mutation: `_idempotency_key_lock` issues `pg_advisory_xact_lock(hashtext(%s))`
    (1-argument form) -- this test goes red."""
    import inspect

    source = inspect.getsource(PostgresCell._idempotency_key_lock)
    assert "pg_advisory_xact_lock(%s, hashtext(%s))" in source, source
    assert "pg_advisory_xact_lock(hashtext(%s))" not in source


def test_a_keyed_schema_operation_waiting_for_the_schema_lock_does_not_block_a_keyed_data_operation(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """A holds the schema lock (an unkeyed `create_entity`, stopped at the
    entry of `_create_entity`). S, a keyed `add_field`, is seen waiting on
    an advisory lock: it holds its per-key lock but no count lock. D, a
    keyed insert under another key, then completes while A and S are still
    waiting -- it needs the count lock, which S has not taken."""
    cell = make_cell(app_a, pool_size=4)
    try:
        cell.apply_schema(_create("widgets"), developer=True, limits=LIMITS)
        holding = threading.Event()
        release = threading.Event()
        holder: dict[str, threading.Thread] = {}
        original = PostgresCell._create_entity

        def _stalled(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
            if threading.current_thread() is holder.get("a") and not holding.is_set():
                holding.set()
                assert release.wait(timeout=_WAIT_S), "test setup: release was never signaled"
            return original(self, *args, **kwargs)

        monkeypatch.setattr(PostgresCell, "_create_entity", _stalled)

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}

        def _worker(name: str, call: Any) -> None:
            try:
                results[name] = call()
            except BaseException as exc:  # noqa: BLE001 -- recorded and judged by the test body
                errors[name] = exc

        add_field = {"operation": "add_field", "entity": "widgets", "field": "extra"}
        insert = [{"operation": "insert", "values": {"name": "n"}}]

        thread_a = threading.Thread(target=_worker, args=("A", lambda: cell.apply_schema(_create("held_a"), developer=True, limits=LIMITS)))
        holder["a"] = thread_a
        thread_s = threading.Thread(target=_worker, args=("S", lambda: cell.apply_schema(
            add_field, developer=True, limits=LIMITS, plan_request=add_field, idempotency_key="key-s", request_id="rid-s")))
        thread_d = threading.Thread(target=_worker, args=("D", lambda: cell.transact(
            "widgets", insert, LIMITS, plan_request={"entity": "widgets", "operations": insert},
            idempotency_key="key-d", request_id="rid-d")))
        threads = [thread_a, thread_s, thread_d]
        try:
            thread_a.start()
            assert holding.wait(timeout=_WAIT_S), "thread A never reached the stop point PostgresCell._create_entity"
            thread_s.start()
            give_up_at = time.monotonic() + _WAIT_S
            while not _advisory_lock_waiters(platform.admin_dsn, app_a.database):
                assert time.monotonic() < give_up_at, "S, a keyed schema operation, never waited on the schema lock held by A"
                time.sleep(0.05)
            assert "S" not in results and "S" not in errors, "S finished while A held the schema lock"

            thread_d.start()
            thread_d.join(timeout=_REPLAY_WINDOW_S)
            assert not thread_d.is_alive(), "a keyed data operation waited behind a keyed schema operation that only waits for the schema lock"
            assert "D" in results, f"the keyed data operation failed: {errors.get('D')!r}"
        finally:
            release.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(timeout=_WAIT_S)
        assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
        assert not errors, f"A and S must both succeed after the release: {errors}"
    finally:
        cell.close()


def test_a_dry_run_reads_the_revision_under_the_schema_lock(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """A dry-run `add_field` is stopped right after `_read_schema_revision`
    returned (catalog and revision read, nothing written). B, a schema
    operation on another entity, is seen waiting on an advisory lock: the
    dry run holds the schema lock like every other schema operation. After
    the release B commits, and the plan token the dry run produced (for
    the revision it read) is refused with `PRECONDITION_FAILED`."""
    cell = make_cell(app_a, pool_size=3)
    try:
        cell.apply_schema(_create("e1"), developer=True, limits=LIMITS)
        cell.apply_schema(_create("e2"), developer=True, limits=LIMITS)
        operation = {"operation": "add_field", "entity": "e1", "field": "extra"}
        holding = threading.Event()
        release = threading.Event()
        holder: dict[str, threading.Thread] = {}
        original = PostgresCell._read_schema_revision

        def _stalled(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
            result = original(self, *args, **kwargs)
            if threading.current_thread() is holder.get("a") and not holding.is_set():
                holding.set()
                assert release.wait(timeout=_WAIT_S), "test setup: release was never signaled"
            return result

        monkeypatch.setattr(PostgresCell, "_read_schema_revision", _stalled)

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}

        def _worker(name: str, call: Any) -> None:
            try:
                results[name] = call()
            except BaseException as exc:  # noqa: BLE001 -- recorded and judged by the test body
                errors[name] = exc

        b_operation = {"operation": "add_field", "entity": "e2", "field": "other"}
        thread_a = threading.Thread(target=_worker, args=("A", lambda: cell.apply_schema(
            operation, developer=True, limits=LIMITS, dry_run=True, plan_request=operation)))
        holder["a"] = thread_a
        thread_b = threading.Thread(target=_worker, args=("B", lambda: cell.apply_schema(
            b_operation, developer=True, limits=LIMITS, plan_request=b_operation)))
        threads = [thread_a, thread_b]
        try:
            thread_a.start()
            assert holding.wait(timeout=_WAIT_S), "the dry run never reached the stop point PostgresCell._read_schema_revision"
            thread_b.start()
            give_up_at = time.monotonic() + _WAIT_S
            while "B" not in results and not _advisory_lock_waiters(platform.admin_dsn, app_a.database):
                assert time.monotonic() < give_up_at, "B neither completed nor waited on a lock while the dry run was stopped"
                time.sleep(0.05)
            assert "B" not in results and "B" not in errors, "B completed while a dry run held its catalog and revision reads"
        finally:
            release.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(timeout=_WAIT_S)
        assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
        assert not errors, f"the dry run and B must both succeed: {errors}"
        dry = results["A"]
        assert dry.committed is False and dry.plan, "the dry run must have produced a plan token and committed nothing"
        assert dry.revision == results["B"].revision - 1, "the dry run read the revision as it stood before B committed"
        with pytest.raises(FoundationError) as refused:
            cell.apply_schema(operation, developer=True, limits=LIMITS, plan=dry.plan, plan_request=operation)
        assert refused.value.code == "PRECONDITION_FAILED"
    finally:
        cell.close()
