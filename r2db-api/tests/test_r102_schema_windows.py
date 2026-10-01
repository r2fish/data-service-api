"""Schema-operation check-then-act windows of `PostgresCell`, reproduced
deterministically with TWO independent `PostgresCell` instances (each with
its own `SharedPoolManager`, so its own connections) on ONE provisioned
application database -- the shape of two service instances serving the
same application. Only what PostgreSQL itself enforces across connections
can serialize them.

The three windows (design docs/design/MITATEDB_APPLICATION_SERIALIZATION_
V0_1.md section 2.6), each in `apply_schema`:

- plan: a `plan` token is checked against a revision read at the start of
  the transaction, with no lock held; a schema change of a DIFFERENT
  entity landing after that read leaves the stale plan applied.
- confirmation: a `drop_entity` confirmation phrase is compared against a
  revision read in the same unlocked way; a schema change landing after
  the read leaves the stale phrase accepted and the entity dropped.
- `schema_objects`: the bound is checked against the object count of a
  catalog read taken before the DDL; a concurrent `create_entity` landing
  in between pushes the count past the bound.

Stop technique: no hook exists in product code. A test-local `_Stall` wraps
one named method and, for ONE armed thread only (thread A), pauses inside
the wrapper on a `threading.Event` until the test releases it. The wait
for A to arrive is bounded and fails with an `AssertionError` naming the
wrap point. B's not-having-completed is observed through a bounded window
(`_B_WINDOW_S`) and then confirmed by finding a backend of the application
database waiting on a PostgreSQL lock (`pg_stat_activity.wait_event_type =
'Lock'`, bounded wait); a B that is neither finished nor lock-waiting fails
the test.

Every test asserts the same two-branch shape. If B completed while A was
stopped, A must have been refused and must have done nothing. If B did
not complete while A was stopped, then after the release A and B both
run, in that order, and both succeed (or, for `schema_objects`, exactly
one is refused).
"""
from __future__ import annotations

import threading
import time
import types
from typing import Any, Callable

import psycopg
import pytest

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell, SharedPoolManager
from r2db_api.structured import drop_entity_confirmation_phrase

from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()

# Bound on how long the test waits for thread A to arrive at its stop point
# before concluding the wrap point is never reached (a wrong wrap target is a
# test defect, not slowness).
_LOCK_TIMEOUT_S = 10.0
# Bound on how long the test waits, while A is stopped, to see whether B
# completes. Longer than `test_idempotency_concurrency.py`'s 0.3 s: here a
# B that is NOT blocked must be seen to finish (a few DDL round trips), and
# a window shorter than that would misread a slow, unblocked B as blocked.
_B_WINDOW_S = 1.0
# Bound on how long the test looks for B waiting on a PostgreSQL lock after
# `_B_WINDOW_S` has passed. B's own lock wait ends by itself when the product's
# `lock_timeout` (derived from the request deadline, default execution_ms
# 5000 ms: r2db-api/src/r2db_api/postgres.py `_set_timeouts` (SET LOCAL lock_timeout = the request's remaining deadline) and limits.py `execution_ms = 5_000`) fires and B fails with LIMIT_EXCEEDED(execution_ms) -- a B that
# then counts as "completed" would send a blind observation into the wrong
# branch. So `_B_WINDOW_S + _LOCK_OBSERVE_S` stays below 5 s, and every other
# bound (`_LOCK_TIMEOUT_S`, used for A's arrival, A's release wait and the
# joins) stays above it.
_LOCK_OBSERVE_S = 3.0
assert _B_WINDOW_S + _LOCK_OBSERVE_S < 5.0 < _LOCK_TIMEOUT_S


def _pair(app: types.SimpleNamespace) -> tuple[PostgresCell, PostgresCell]:
    """TWO INDEPENDENT `PostgresCell`s on the same application database,
    each with a `SharedPoolManager` of its own (the default process-wide
    manager is keyed by application id and would hand both cells the same
    pooled connections)."""
    cells = []
    for _ in range(2):
        manager = SharedPoolManager(idle_seconds=300, cache_max=4, pool_size=2, pool_max_overflow=0)
        cells.append(make_cell(app, pool_manager=manager))
    return cells[0], cells[1]


class _Stall:
    """Pauses ONE armed thread (A), once, at a named wrap point, and lets
    every other thread (B, the main thread) pass straight through.
    `after=True` runs the wrapped method first and pauses once it has
    returned (so the stop point is just after a read)."""

    def __init__(self) -> None:
        self.holding = threading.Event()
        self.release = threading.Event()
        self.thread: threading.Thread | None = None
        self.point = "<not installed>"
        self._used = False

    def install(self, monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, *, after: bool = False) -> None:
        original = getattr(owner, name)
        self.point = f"{getattr(owner, '__name__', repr(owner))}.{name}"
        stall = self

        def _pause_if_armed() -> None:
            if not stall._used and threading.current_thread() is stall.thread:
                stall._used = True
                stall.holding.set()
                assert stall.release.wait(timeout=_LOCK_TIMEOUT_S), "test setup: release was never signaled"

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if after:
                result = original(*args, **kwargs)
                _pause_if_armed()
                return result
            _pause_if_armed()
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
    on a PostgreSQL lock (bounded by `_LOCK_OBSERVE_S`; a B that finishes
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
            give_up_at = time.monotonic() + _LOCK_OBSERVE_S
            while not outcome.b_done_while_a_stopped and not _lock_waiters(admin_dsn, database):
                assert time.monotonic() < give_up_at, (
                    f"B neither completed nor is waiting on a PostgreSQL lock while A is stopped at {stall.point}")
                outcome.b_done_while_a_stopped = done["B"].wait(timeout=0.05)
        assert not done["A"].is_set(), f"A finished while it was to be stopped at {stall.point}"
    finally:
        stall.release.set()
        for thread in threads:
            thread.join(timeout=_LOCK_TIMEOUT_S)
    assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish after the release"
    return outcome


def _create(cell: PostgresCell, entity: str, *, limits: ResourceLimits = LIMITS) -> Any:
    return cell.apply_schema(
        {"operation": "create_entity", "entity": entity, "fields": ["name"], "field_types": {"name": "string"}},
        developer=True, limits=limits)


def _add_field(cell: PostgresCell, entity: str, field: str, **kwargs: Any) -> Any:
    operation = {"operation": "add_field", "entity": entity, "field": field}
    return cell.apply_schema(operation, developer=True, limits=LIMITS, plan_request=operation, **kwargs)


def _revision(cell: PostgresCell) -> int:
    """The current schema revision, through a dry-run `add_field` (a dry
    run reports the revision as it stood and commits nothing)."""
    return _add_field(cell, "e2", "probe", dry_run=True).revision


def _fields(cell: PostgresCell) -> dict[str, list[str]]:
    return {entry["entity"]: entry["fields"] for entry in cell.catalog()}


def test_plan_window_plan_is_checked_against_the_revision_inside_the_ddl_serialization(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Plan. A: `apply_schema(add_field e1.extra)` carrying a dry-run plan,
    stopped right after `_read_schema_revision` returned the revision the
    plan is checked against -- before any DDL. B: `apply_schema(add_field
    e2.other)` on a DIFFERENT entity (no plan), which advances the
    revision by one."""
    cell_a, cell_b = _pair(app_a)
    try:
        _create(cell_a, "e1")
        _create(cell_a, "e2")
        operation = {"operation": "add_field", "entity": "e1", "field": "extra"}
        dry = cell_a.apply_schema(operation, developer=True, limits=LIMITS, dry_run=True, plan_request=operation)
        assert dry.plan, "the dry run must have produced a plan token"
        revision_0 = dry.revision
        assert _revision(cell_a) == revision_0, "a dry run must not advance the revision"

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_read_schema_revision", after=True)
        outcome = _run_window(
            stall,
            lambda: cell_a.apply_schema(operation, developer=True, limits=LIMITS, plan=dry.plan, plan_request=operation),
            lambda: _add_field(cell_b, "e2", "other"),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        assert "B" in outcome.results, f"B must succeed in either branch: {outcome.errors}"
        assert "other" in _fields(cell_a)["e2"]
        if outcome.b_done_while_a_stopped:
            error = outcome.errors.get("A")
            assert isinstance(error, FoundationError) and error.code == "PRECONDITION_FAILED", (
                f"B completed while A held its plan: A must be refused with PRECONDITION_FAILED, got "
                f"{error!r} / {outcome.results.get('A')!r}")
            assert error.details == {"violated_declaration": "plan"}
            assert "extra" not in _fields(cell_a)["e1"], "a refused A must add nothing to e1"
            assert _revision(cell_a) == revision_0 + 1
        else:
            assert "A" in outcome.results, f"B did not complete while A held: A must then succeed, got {outcome.errors}"
            assert "extra" in _fields(cell_a)["e1"]
            assert _revision(cell_a) == revision_0 + 2, "A and B both committed: the revision advances by two"
    finally:
        cell_a.close()
        cell_b.close()


def test_confirmation_window_drop_entity_confirmation_is_checked_against_the_revision_inside_the_ddl_serialization(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Confirmation. A: `apply_schema(drop_entity e1)` carrying the
    confirmation phrase of the revision current when it was made, stopped
    right after `_read_schema_revision` returned the revision the phrase is
    recomputed from -- before the DROP. B: `apply_schema(add_field
    e2.other)` on a different entity, which advances the revision."""
    cell_a, cell_b = _pair(app_a)
    try:
        _create(cell_a, "e1")
        _create(cell_a, "e2")
        revision_0 = _revision(cell_a)
        drop = {
            "operation": "drop_entity", "entity": "e1", "destructive": True,
            "confirmation": drop_entity_confirmation_phrase("e1", revision_0),
        }

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_read_schema_revision", after=True)
        outcome = _run_window(
            stall,
            lambda: cell_a.apply_schema(drop, developer=True, limits=LIMITS),
            lambda: _add_field(cell_b, "e2", "other"),
            admin_dsn=platform.admin_dsn, database=app_a.database,
        )

        assert "B" in outcome.results, f"B must succeed in either branch: {outcome.errors}"
        fields = _fields(cell_a)
        assert "other" in fields["e2"]
        if outcome.b_done_while_a_stopped:
            error = outcome.errors.get("A")
            assert isinstance(error, FoundationError) and error.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
                f"B advanced the revision while A held its confirmation: A must be refused with "
                f"DESTRUCTIVE_CONFIRMATION_REQUIRED, got {error!r} / {outcome.results.get('A')!r}")
            assert "e1" in fields, "a refused drop must leave e1 in place"
        else:
            assert "A" in outcome.results, f"B did not complete while A held: A must then succeed, got {outcome.errors}"
            assert "e1" not in fields, "A's confirmed drop must have removed e1"
    finally:
        cell_a.close()
        cell_b.close()


def test_schema_objects_window_concurrent_create_entity_cannot_exceed_schema_objects(platform, app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """`schema_objects`. The bound is exactly the object count of ONE more
    entity (an entity with one declared field is 3 objects, see
    `test_backend_excludes_the_ledger_from_catalog_and_schema_objects_
    accounting`). A: `apply_schema(create_entity e1)`, stopped at the entry
    of `PostgresCell._create_entity` -- after the bound was checked, before
    the DDL. B: `create_entity e2`. Exactly one of the two may succeed and
    the other must be `LIMIT_EXCEEDED` (`schema_objects`)."""
    cell_a, cell_b = _pair(app_a)
    try:
        assert cell_a.catalog() == [], "a freshly provisioned application holds no entity"
        limits = ResourceLimits(schema_objects=3)

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_create_entity")
        outcome = _run_window(
            stall, lambda: _create(cell_a, "e1", limits=limits), lambda: _create(cell_b, "e2", limits=limits),
            admin_dsn=platform.admin_dsn, database=app_a.database)

        limit_errors = [
            name for name, error in outcome.errors.items()
            if isinstance(error, FoundationError) and error.code == "LIMIT_EXCEEDED"
        ]
        assert len(outcome.results) == 1 and len(limit_errors) == 1, (
            f"exactly one create must succeed and one be LIMIT_EXCEEDED: results={sorted(outcome.results)} "
            f"errors={ {name: repr(error) for name, error in outcome.errors.items()} } "
            f"(B completed while A stopped: {outcome.b_done_while_a_stopped})")
        assert outcome.errors[limit_errors[0]].details["limit_class"] == "schema_objects"
        objects = sum(len(fields) + 1 for fields in _fields(cell_a).values())
        assert objects <= limits.schema_objects, (
            f"schema objects exceeded the bound {limits.schema_objects}: {objects} "
            f"(B completed while A stopped: {outcome.b_done_while_a_stopped})")
    finally:
        cell_a.close()
        cell_b.close()
