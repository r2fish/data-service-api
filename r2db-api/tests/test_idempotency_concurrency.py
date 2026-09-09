"""Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): SAME-key and
DIFFERENT-key CONCURRENT requests, real threads, deterministic ordering via
a monkeypatched hook + `threading.Event`s -- never a bare `time.sleep()`
race. `test_idempotency_records.py` already pins the SEQUENTIAL (one
request at a time) idempotency semantics; this file is what proves the
race F-① found (two requests interleaved between lookup and store) is
actually closed, on BOTH backends this peer ships:

- `ApplicationCell` (in-memory): the cell-wide `threading.Lock`
  (`_idempotency_lock`) added by WP-6d, held for the ENTIRE
  lookup -> execute -> store window of `_transact_locked`/
  `_apply_schema_locked`.
- `PostgresCell` (real PostgreSQL): the per-key `pg_advisory_xact_lock`
  (`_idempotency_key_lock`) and the table-level `pg_advisory_xact_lock`
  (`_idempotency_reserve_lock`), both added by WP-6d.

Hook used: the EXISTING `_idempotency_lookup` method (cases i/ii) and the
EXISTING `_idempotency_reserve` method (case iii) are monkeypatched --
no new hook is added to the source; a wrapper runs the real method, then
(on the FIRST call only) signals "the lock is held" and blocks on a
second event until the test's own main thread releases it. Because the
lock is taken immediately BEFORE either of these methods runs (both
backends, ruling U-7), pausing INSIDE them holds the lock throughout the
pause -- a concurrent second call for the SAME key (case i/ii) or the
SAME capacity slot (case iii) genuinely blocks on that same lock while
paused, exactly the condition this file measures.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.structured import ApplicationCell

import r2db_api.postgres as pg_module
from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()

# How long the main thread waits for "the first call has taken the lock and
# is paused" before concluding the hook never fired (a real bug, not mere
# slowness) -- generous for CI/local machine variance.
_LOCK_TIMEOUT_S = 10.0
# How long the main thread waits, WHILE the first call is deliberately
# paused, to confirm the second call has NOT completed -- proof the second
# call is genuinely blocked on the same lock, not merely slower by luck.
_BLOCKED_PROOF_WINDOW_S = 0.3


def _mutate_plan_request(entity: str, operations: list[dict[str, Any]], *, idempotency_key: str | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {"entity": entity, "operations": operations}
    if idempotency_key is not None:
        request["idempotency_key"] = idempotency_key
    return request


class _FirstCallGate:
    """Lets exactly the FIRST call through a monkeypatched method pause,
    signalling `holding` the instant it is paused (lock already taken by
    then, in both backends) and waiting on `release` before returning the
    real result. Every OTHER call passes straight through -- by the time a
    second, concurrent call for the SAME key/slot reaches this same
    method, it has necessarily already blocked (for real, at the DB or
    `threading.Lock` level) until the first call's own transaction/lock
    scope ends, so there is nothing left to gate for it."""

    def __init__(self) -> None:
        self._used = threading.Event()
        self.holding = threading.Event()
        self.release = threading.Event()

    def wrap(self, original):
        def _wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            if not self._used.is_set():
                self._used.set()
                self.holding.set()
                assert self.release.wait(timeout=_LOCK_TIMEOUT_S), "test setup: release was never signaled"
            return result

        return _wrapped


def _assert_second_call_is_blocked(done_event: threading.Event) -> None:
    time.sleep(_BLOCKED_PROOF_WINDOW_S)
    assert not done_event.is_set(), (
        "the second, concurrent request completed WHILE the first was still holding the idempotency "
        "lock -- the lock is not actually serializing these two requests"
    )


# ===========================================================================
# In-memory backend (`ApplicationCell`) -- cell-wide `threading.Lock`.
# ===========================================================================


def _memory_cell_with_widgets() -> ApplicationCell:
    cell = ApplicationCell(application_id="app-conc-mem")
    cell.apply_schema(
        {"operation": "create_entity", "entity": "widgets", "fields": ["label"], "field_types": {"label": "string"}},
        developer=True, limits=LIMITS,
    )
    return cell


def test_memory_same_key_same_digest_concurrent_executes_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (i), in-memory: two threads submit the IDENTICAL request under
    the SAME idempotency key at the same time -- exactly one insert lands
    (`len(cell.entities["widgets"]) == 1`), and the second response is a
    REPLAY carrying the FIRST response's own `request_id`."""
    cell = _memory_cell_with_widgets()
    gate = _FirstCallGate()
    original = ApplicationCell._idempotency_lookup
    monkeypatch.setattr(ApplicationCell, "_idempotency_lookup", gate.wrap(original))

    ops = [{"operation": "insert", "values": {"label": "same"}}]
    results: dict[str, Any] = {}
    b_done = threading.Event()

    def worker(name: str, request_id: str) -> None:
        try:
            results[name] = cell.transact(
                "widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops),
                idempotency_key="mem-same-1", request_id=request_id,
            )
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A", "rid-A"))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused lookup"

    thread_b = threading.Thread(target=worker, args=("B", "rid-B"))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    assert len(cell.entities["widgets"]) == 1, "exactly one execution must have landed"
    outcome_a, outcome_b = results["A"], results["B"]
    executed, replayed = (outcome_a, outcome_b) if not outcome_a.replayed else (outcome_b, outcome_a)
    assert executed.replayed is False
    assert replayed.replayed is True
    assert replayed.request_id == executed.request_id, "the replay must carry the ORIGINAL execution's own request_id"


def test_memory_same_key_different_digest_concurrent_conflicts_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (ii), in-memory: two threads submit DIFFERENT bodies under the
    SAME idempotency key at the same time -- exactly one insert lands, and
    the other is refused CONFLICT / `violated_declaration: idempotency_key`
    (never a second, silently-accepted execution -- F-①'s own observed
    failure mode without the WP-6d lock)."""
    cell = _memory_cell_with_widgets()
    gate = _FirstCallGate()
    original = ApplicationCell._idempotency_lookup
    monkeypatch.setattr(ApplicationCell, "_idempotency_lookup", gate.wrap(original))

    ops_a = [{"operation": "insert", "values": {"label": "from-a"}}]
    ops_b = [{"operation": "insert", "values": {"label": "from-b"}}]
    results: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}
    b_done = threading.Event()

    def worker(name: str, ops: list[dict[str, Any]]) -> None:
        try:
            results[name] = cell.transact(
                "widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops),
                idempotency_key="mem-diff-1", request_id=f"rid-{name}",
            )
        except FoundationError as exc:
            errors[name] = exc
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A", ops_a))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused lookup"

    thread_b = threading.Thread(target=worker, args=("B", ops_b))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    assert len(cell.entities["widgets"]) == 1, "exactly one of the two conflicting bodies must have executed"
    succeeded = [n for n in ("A", "B") if n in results]
    conflicted = [n for n in ("A", "B") if n in errors]
    assert len(succeeded) == 1 and len(conflicted) == 1, (results, errors)
    assert errors[conflicted[0]].code == "CONFLICT"
    assert errors[conflicted[0]].details.get("violated_declaration") == "idempotency_key"


def test_memory_two_different_keys_concurrent_at_capacity_exactly_one_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (iii), in-memory: `idempotency_entries` is one below its limit;
    two threads submit DIFFERENT idempotency keys at the same time -- the
    COUNT-then-write race (D-5 (iii)) must not let both through. Exactly
    one succeeds, the other is refused `LIMIT_EXCEEDED` /
    `limit_class: idempotency_entries`."""
    tiny_limits = ResourceLimits(idempotency_entries=2)
    cell = _memory_cell_with_widgets()
    # Pre-seed one record, one below the limit of 2.
    seed_ops = [{"operation": "insert", "values": {"label": "seed"}}]
    cell.transact("widgets", seed_ops, tiny_limits, plan_request=_mutate_plan_request("widgets", seed_ops), idempotency_key="mem-cap-seed")
    assert len(cell._idempotency) == 1

    gate = _FirstCallGate()
    original = ApplicationCell._idempotency_reserve
    monkeypatch.setattr(ApplicationCell, "_idempotency_reserve", gate.wrap(original))

    results: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}
    b_done = threading.Event()

    def worker(name: str, key: str) -> None:
        ops = [{"operation": "insert", "values": {"label": name}}]
        try:
            results[name] = cell.transact(
                "widgets", ops, tiny_limits, plan_request=_mutate_plan_request("widgets", ops),
                idempotency_key=key, request_id=f"rid-{name}",
            )
        except FoundationError as exc:
            errors[name] = exc
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A", "mem-cap-a"))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused reserve check"

    thread_b = threading.Thread(target=worker, args=("B", "mem-cap-b"))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    succeeded = [n for n in ("A", "B") if n in results]
    refused = [n for n in ("A", "B") if n in errors]
    assert len(succeeded) == 1 and len(refused) == 1, (results, errors)
    assert errors[refused[0]].code == "LIMIT_EXCEEDED"
    assert errors[refused[0]].details.get("limit_class") == "idempotency_entries"
    assert len(cell._idempotency) == 2, "capacity must land at exactly the limit, never over it"


# ===========================================================================
# PostgreSQL backend (`PostgresCell`) -- `pg_advisory_xact_lock`.
# ===========================================================================


def test_postgres_same_key_same_digest_concurrent_executes_exactly_once(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (i), PostgreSQL: identical to the in-memory case above, but the
    lock under test is `_idempotency_key_lock`'s real `pg_advisory_xact_
    lock`, taken on the pooled `_runtime`/`_developer` connection each
    thread's own `transact` call checks out -- `make_cell(app_a, pool_
    size=2)` guarantees the two concurrent threads never share (and
    therefore never accidentally serialize on) the SAME connection."""
    cell = make_cell(app_a, pool_size=2)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "cwidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        gate = _FirstCallGate()
        original = pg_module.PostgresCell._idempotency_lookup
        monkeypatch.setattr(pg_module.PostgresCell, "_idempotency_lookup", gate.wrap(original))

        ops = [{"operation": "insert", "values": {"label": "same"}}]
        results: dict[str, Any] = {}
        b_done = threading.Event()

        def worker(name: str, request_id: str) -> None:
            try:
                results[name] = cell.transact(
                    "cwidgets", ops, LIMITS, plan_request=_mutate_plan_request("cwidgets", ops),
                    idempotency_key="pg-same-1", request_id=request_id,
                )
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", "rid-A"))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused lookup"

        thread_b = threading.Thread(target=worker, args=("B", "rid-B"))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        import psycopg

        with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM public.cwidgets")
                assert cur.fetchone()[0] == 1, "exactly one execution must have landed"

        outcome_a, outcome_b = results["A"], results["B"]
        executed, replayed = (outcome_a, outcome_b) if not outcome_a.replayed else (outcome_b, outcome_a)
        assert executed.replayed is False
        assert replayed.replayed is True
        assert replayed.request_id == executed.request_id
    finally:
        cell.close()


def test_postgres_same_key_different_digest_concurrent_conflicts_exactly_once(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (ii), PostgreSQL: same shape as the in-memory case above."""
    cell = make_cell(app_a, pool_size=2)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "dwidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        gate = _FirstCallGate()
        original = pg_module.PostgresCell._idempotency_lookup
        monkeypatch.setattr(pg_module.PostgresCell, "_idempotency_lookup", gate.wrap(original))

        ops_a = [{"operation": "insert", "values": {"label": "from-a"}}]
        ops_b = [{"operation": "insert", "values": {"label": "from-b"}}]
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        b_done = threading.Event()

        def worker(name: str, ops: list[dict[str, Any]]) -> None:
            try:
                results[name] = cell.transact(
                    "dwidgets", ops, LIMITS, plan_request=_mutate_plan_request("dwidgets", ops),
                    idempotency_key="pg-diff-1", request_id=f"rid-{name}",
                )
            except FoundationError as exc:
                errors[name] = exc
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", ops_a))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused lookup"

        thread_b = threading.Thread(target=worker, args=("B", ops_b))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        import psycopg

        with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM public.dwidgets")
                assert cur.fetchone()[0] == 1, "exactly one of the two conflicting bodies must have executed"

        succeeded = [n for n in ("A", "B") if n in results]
        conflicted = [n for n in ("A", "B") if n in errors]
        assert len(succeeded) == 1 and len(conflicted) == 1, (results, errors)
        assert errors[conflicted[0]].code == "CONFLICT"
        assert errors[conflicted[0]].details.get("violated_declaration") == "idempotency_key"
    finally:
        cell.close()


def test_postgres_two_different_keys_concurrent_at_capacity_exactly_one_limit_exceeded(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (iii), PostgreSQL: same shape as the in-memory case above, but
    the lock under test is `_idempotency_reserve_lock`'s table-level
    `pg_advisory_xact_lock`."""
    tiny_limits = ResourceLimits(idempotency_entries=2)
    cell = make_cell(app_a, pool_size=2)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "ewidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        seed_ops = [{"operation": "insert", "values": {"label": "seed"}}]
        cell.transact("ewidgets", seed_ops, tiny_limits, plan_request=_mutate_plan_request("ewidgets", seed_ops), idempotency_key="pg-cap-seed")

        gate = _FirstCallGate()
        original = pg_module.PostgresCell._idempotency_reserve
        monkeypatch.setattr(pg_module.PostgresCell, "_idempotency_reserve", gate.wrap(original))

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        b_done = threading.Event()

        def worker(name: str, key: str) -> None:
            ops = [{"operation": "insert", "values": {"label": name}}]
            try:
                results[name] = cell.transact(
                    "ewidgets", ops, tiny_limits, plan_request=_mutate_plan_request("ewidgets", ops),
                    idempotency_key=key, request_id=f"rid-{name}",
                )
            except FoundationError as exc:
                errors[name] = exc
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", "pg-cap-a"))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused reserve check"

        thread_b = threading.Thread(target=worker, args=("B", "pg-cap-b"))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        succeeded = [n for n in ("A", "B") if n in results]
        refused = [n for n in ("A", "B") if n in errors]
        assert len(succeeded) == 1 and len(refused) == 1, (results, errors)
        assert errors[refused[0]].code == "LIMIT_EXCEEDED"
        assert errors[refused[0]].details.get("limit_class") == "idempotency_entries"

        import psycopg

        with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM public._r2db_idempotency")
                assert cur.fetchone()[0] == 2, "capacity must land at exactly the limit, never over it"
    finally:
        cell.close()
