"""The application-wide schema serialization lock of `PostgresCell.apply_schema`
(`_schema_serialization_lock`): the place in a request where it is taken.

The lock is taken after the idempotency lookup, so a resent schema operation
whose key already has a record answers from the record at once and never
waits behind a schema operation that is still running. The windows the lock
closes (plan, confirmation phrase, `schema_objects`) are pinned by
`test_r102_schema_windows.py`.
"""
from __future__ import annotations

import threading
import time
import types
from typing import Any

import psycopg
import pytest

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
