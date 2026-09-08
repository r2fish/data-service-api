"""Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): SAME-key and
DIFFERENT-key CONCURRENT requests, real threads, deterministic ordering via
a monkeypatched hook + `threading.Event`s -- never a bare `time.sleep()`
race. `test_idempotency_records.py` already pins the SEQUENTIAL (one
request at a time) idempotency semantics; this file is what proves the
race F-① found (two requests interleaved between lookup and store) is
actually closed, on BOTH backends this peer ships.

`ApplicationCell._idempotency_check` is this peer's ONE shared choke point
for both backends (SQLite/in-memory AND PostgreSQL) -- it is the single
method every one of the 4 keyed entry points (`transact`, `create_
collection`, `add_field`, `alter_field`) calls, and it is where WP-6d's own
locking now lives: `self._lock` (a cell-wide `RLock`, widened by WP-6d to
cover this method's ENTIRE lookup -> execute -> store window) for BOTH
backends, plus (`PostgresBackend` only) the two session-scoped `pg_
advisory_lock`s `idempotency_begin`/`idempotency_reserve` take internally,
BEFORE this method itself returns. Hook used: this SAME `_idempotency_
check` method is monkeypatched -- no new hook is added to the source; a
wrapper runs the real method, then (on the FIRST call that returns WITHOUT
raising -- i.e. the winner, never a loser that just got CONFLICT/
LIMIT_EXCEEDED) signals "the lock is held" and blocks on a second event
until the test's own main thread releases it. Because every lock this
method's own callers rely on is already held by the time it returns
normally, pausing right there holds all of them throughout the pause.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import psycopg
import pytest

from mitatedb_api import FoundationConfig, Role
from mitatedb_api.auth import Principal
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from mitatedb_api.errors import ConflictError, FoundationError, ResourceLimitError

from .test_postgres import app_a, close_cell, make_cell, platform  # noqa: F401 (fixtures) -- RELATIVE import, see test_http.py's own identical comment for why a bare `from test_postgres import ...` would be wrong here

_LOCK_TIMEOUT_S = 10.0
_BLOCKED_PROOF_WINDOW_S = 0.3


class _FirstCallGate:
    """See `r2db-api/tests/test_idempotency_concurrency.py`'s identical
    class docstring -- same technique, same reasoning, independent
    implementation (peer code sharing is out of scope, requester decision
    2026-09-03)."""

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


def _memory_pair(config: FoundationConfig | None = None) -> tuple[ApplicationDeveloper, ApplicationRuntime]:
    cell = ApplicationCell("app_conc_mem", config or FoundationConfig())
    dev = ApplicationDeveloper(cell, Principal(application_id="app_conc_mem", credential_id="dev", role=Role.DEVELOPER))
    runtime = ApplicationRuntime(cell, Principal(application_id="app_conc_mem", credential_id="rt", role=Role.RUNTIME))
    return dev, runtime


# ===========================================================================
# In-memory backend (`SQLiteBackend`, default) -- cell-wide `threading.Lock`.
# ===========================================================================


def test_memory_same_key_same_digest_concurrent_executes_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (i), in-memory (SQLite): two threads submit the IDENTICAL
    request under the SAME idempotency key at the same time -- exactly one
    insert lands, and the second response is a REPLAY carrying the FIRST
    response's own `request_id`."""
    dev, runtime = _memory_pair()
    dev.create_collection("notes", {"title": "text"})
    gate = _FirstCallGate()
    monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

    results: dict[str, Any] = {}
    b_done = threading.Event()

    def worker(name: str) -> None:
        try:
            results[name] = runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "same"}}],
                idempotency_key="mem-same-1", request_id=f"rid-{name}",
            )
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A",))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

    thread_b = threading.Thread(target=worker, args=("B",))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    assert len(runtime.read("notes")) == 1, "exactly one execution must have landed"
    request_ids = {results["A"][-1]["request_id"], results["B"][-1]["request_id"]}
    assert len(request_ids) == 1, "the replay must carry the ORIGINAL execution's own request_id"


def test_memory_same_key_different_digest_concurrent_conflicts_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (ii), in-memory (SQLite): two threads submit DIFFERENT bodies
    under the SAME idempotency key at the same time -- exactly one insert
    lands, and the other is refused CONFLICT / `violated_declaration:
    idempotency_key`."""
    dev, runtime = _memory_pair()
    dev.create_collection("notes", {"title": "text"})
    gate = _FirstCallGate()
    monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

    results: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}
    b_done = threading.Event()

    def worker(name: str, title: str) -> None:
        try:
            results[name] = runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": title}}],
                idempotency_key="mem-diff-1", request_id=f"rid-{name}",
            )
        except FoundationError as exc:
            errors[name] = exc
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A", "from-a"))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

    thread_b = threading.Thread(target=worker, args=("B", "from-b"))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    assert len(runtime.read("notes")) == 1, "exactly one of the two conflicting bodies must have executed"
    succeeded = [n for n in ("A", "B") if n in results]
    conflicted = [n for n in ("A", "B") if n in errors]
    assert len(succeeded) == 1 and len(conflicted) == 1, (results, errors)
    assert isinstance(errors[conflicted[0]], ConflictError)
    assert errors[conflicted[0]].details.get("violated_declaration") == "idempotency_key"


def test_memory_two_different_keys_concurrent_at_capacity_exactly_one_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """U-8 (iii), in-memory (SQLite): `idempotency_entries` is one below
    its limit; two threads submit DIFFERENT idempotency keys at the same
    time -- exactly one succeeds, the other is refused `LIMIT_EXCEEDED` /
    `limit_class: idempotency_entries` (D-5 (iii)'s own COUNT-then-write
    race, closed by widening `self._lock` over the reserve check too)."""
    dev, runtime = _memory_pair(FoundationConfig(idempotency_entries=2))
    dev.create_collection("notes", {"title": "text"})
    runtime.transact([{"type": "insert", "collection": "notes", "values": {"title": "seed"}}], idempotency_key="mem-cap-seed")

    gate = _FirstCallGate()
    monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

    results: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}
    b_done = threading.Event()

    def worker(name: str, key: str) -> None:
        try:
            results[name] = runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": name}}],
                idempotency_key=key, request_id=f"rid-{name}",
            )
        except FoundationError as exc:
            errors[name] = exc
        finally:
            if name == "B":
                b_done.set()

    thread_a = threading.Thread(target=worker, args=("A", "mem-cap-a"))
    thread_a.start()
    assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

    thread_b = threading.Thread(target=worker, args=("B", "mem-cap-b"))
    thread_b.start()
    _assert_second_call_is_blocked(b_done)

    gate.release.set()
    thread_a.join(timeout=_LOCK_TIMEOUT_S)
    thread_b.join(timeout=_LOCK_TIMEOUT_S)

    succeeded = [n for n in ("A", "B") if n in results]
    refused = [n for n in ("A", "B") if n in errors]
    assert len(succeeded) == 1 and len(refused) == 1, (results, errors)
    assert isinstance(errors[refused[0]], ResourceLimitError)
    assert errors[refused[0]].details.get("limit_class") == "idempotency_entries"


# ===========================================================================
# PostgreSQL backend (`PostgresBackend`) -- session-scoped `pg_advisory_lock`.
# ===========================================================================


def _pg_pair(app_a, config: FoundationConfig | None = None):  # noqa: F811
    """TWO INDEPENDENT `ApplicationCell` instances, each its OWN fresh
    `PostgresBackend` connection pair, both pointed at the SAME
    provisioned application database. This is deliberate, not
    incidental: `ApplicationCell.self._lock` (the Python-level `RLock`
    WP-6d also widened) is scoped to ONE INSTANCE -- a test built on a
    SINGLE shared cell would have both threads serialize on that SAME
    Python lock regardless of whether the PostgreSQL-level session
    advisory lock (`idempotency_begin`/`idempotency_reserve`,
    `backend_postgres.py`) does anything at all, which would make the
    PG-specific mutation-kill (removing the `pg_advisory_lock` call)
    silently NOT turn red (measured directly: it does not, with a
    single shared cell). Two independent cells -- exactly how two
    separate uvicorn WORKER PROCESSES would each hold their own
    `ApplicationCell`/connections against the same database in a real
    multi-process deployment -- means the ONLY thing left to serialize
    the two threads is the real, cross-connection PostgreSQL lock."""
    cell_a = make_cell(app_a, config)
    cell_b = make_cell(app_a, config)
    dev_a = ApplicationDeveloper(cell_a, Principal(application_id=app_a.app_id, credential_id="dev", role=Role.DEVELOPER))
    runtime_a = ApplicationRuntime(cell_a, Principal(application_id=app_a.app_id, credential_id="rt", role=Role.RUNTIME))
    runtime_b = ApplicationRuntime(cell_b, Principal(application_id=app_a.app_id, credential_id="rt", role=Role.RUNTIME))
    return cell_a, cell_b, dev_a, runtime_a, runtime_b


def test_postgres_same_key_same_digest_concurrent_executes_exactly_once(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (i), PostgreSQL: identical to the in-memory case above, but on
    TWO INDEPENDENT `ApplicationCell`s (see `_pg_pair`'s own docstring for
    why) -- the lock under test is `idempotency_begin`'s real, per-key,
    session-scoped `pg_advisory_lock` (`backend_postgres.py`)."""
    cell_a, cell_b, dev_a, runtime_a, runtime_b = _pg_pair(app_a)
    try:
        dev_a.create_collection("notes", {"title": "text"})

        gate = _FirstCallGate()
        monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

        results: dict[str, Any] = {}
        b_done = threading.Event()

        def worker(name: str, runtime: ApplicationRuntime) -> None:
            try:
                results[name] = runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": "same"}}],
                    idempotency_key="pg-same-1", request_id=f"rid-{name}",
                )
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", runtime_a))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

        thread_b = threading.Thread(target=worker, args=("B", runtime_b))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        assert len(runtime_a.read("notes")) == 1, "exactly one execution must have landed"
        request_ids = {results["A"][-1]["request_id"], results["B"][-1]["request_id"]}
        assert len(request_ids) == 1, "the replay must carry the ORIGINAL execution's own request_id"
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_postgres_same_key_different_digest_concurrent_conflicts_exactly_once(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (ii), PostgreSQL: same shape as the in-memory case above, two
    independent cells (see `_pg_pair`)."""
    cell_a, cell_b, dev_a, runtime_a, runtime_b = _pg_pair(app_a)
    try:
        dev_a.create_collection("notes", {"title": "text"})

        gate = _FirstCallGate()
        monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        b_done = threading.Event()

        def worker(name: str, runtime: ApplicationRuntime, title: str) -> None:
            try:
                results[name] = runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": title}}],
                    idempotency_key="pg-diff-1", request_id=f"rid-{name}",
                )
            except FoundationError as exc:
                errors[name] = exc
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", runtime_a, "from-a"))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

        thread_b = threading.Thread(target=worker, args=("B", runtime_b, "from-b"))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        assert len(runtime_a.read("notes")) == 1, "exactly one of the two conflicting bodies must have executed"
        succeeded = [n for n in ("A", "B") if n in results]
        conflicted = [n for n in ("A", "B") if n in errors]
        assert len(succeeded) == 1 and len(conflicted) == 1, (results, errors)
        assert isinstance(errors[conflicted[0]], ConflictError)
        assert errors[conflicted[0]].details.get("violated_declaration") == "idempotency_key"
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_postgres_two_different_keys_concurrent_at_capacity_exactly_one_limit_exceeded(app_a, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """U-8 (iii), PostgreSQL: same shape as the in-memory case above, two
    independent cells (see `_pg_pair`) -- the lock under test is
    `idempotency_reserve`'s table-level, session-scoped `pg_advisory_
    lock`."""
    cell_a, cell_b, dev_a, runtime_a, runtime_b = _pg_pair(app_a, FoundationConfig(idempotency_entries=2))
    try:
        dev_a.create_collection("notes", {"title": "text"})
        runtime_a.transact([{"type": "insert", "collection": "notes", "values": {"title": "seed"}}], idempotency_key="pg-cap-seed")

        gate = _FirstCallGate()
        monkeypatch.setattr(ApplicationCell, "_idempotency_check", gate.wrap(ApplicationCell._idempotency_check))

        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        b_done = threading.Event()

        def worker(name: str, runtime: ApplicationRuntime, key: str) -> None:
            try:
                results[name] = runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": name}}],
                    idempotency_key=key, request_id=f"rid-{name}",
                )
            except FoundationError as exc:
                errors[name] = exc
            finally:
                if name == "B":
                    b_done.set()

        thread_a = threading.Thread(target=worker, args=("A", runtime_a, "pg-cap-a"))
        thread_a.start()
        assert gate.holding.wait(timeout=_LOCK_TIMEOUT_S), "thread A never reached the paused check"

        thread_b = threading.Thread(target=worker, args=("B", runtime_b, "pg-cap-b"))
        thread_b.start()
        _assert_second_call_is_blocked(b_done)

        gate.release.set()
        thread_a.join(timeout=_LOCK_TIMEOUT_S)
        thread_b.join(timeout=_LOCK_TIMEOUT_S)

        succeeded = [n for n in ("A", "B") if n in results]
        refused = [n for n in ("A", "B") if n in errors]
        assert len(succeeded) == 1 and len(refused) == 1, (results, errors)
        assert isinstance(errors[refused[0]], ResourceLimitError)
        assert errors[refused[0]].details.get("limit_class") == "idempotency_entries"
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


# ===========================================================================
# Code-review fixes F1/F2/F3/F4 (Opus review 2, WP-6d rework) -- PostgreSQL
# only: F1's reap-commit regression, F2's advisory-lock timeout, F3's
# unlock-on-pass-1-failure, F4's unlock-on-execution-rollback. Each of
# these is a real, concrete behavior `_FirstCallGate`'s deterministic
# pause above cannot exercise (F1/F3/F4 are about a FAILURE path, F2 is
# about the lock ITSELF timing out) -- separate, direct tests.
# ===========================================================================


def test_postgres_reap_is_committed_not_discarded_by_begin(app_a) -> None:  # noqa: F811
    """Code-review fix F1 (Opus review 2, blocker): `idempotency_begin`'s
    own reap DELETE (retention-expired rows) used to run inside `self.
    _runtime`'s own currently open transaction and never commit itself --
    `cell.py::transact`'s own `self._backend.begin(deadline=deadline)`,
    called for pass 2 right after `idempotency_begin` returns, opens with
    `self._runtime.rollback()`, silently discarding that uncommitted
    DELETE. Reproduction (measured on the pre-fix code: with
    `idempotency_retention_ms=1`, BOTH keys' rows remained in the table
    after the second keyed `transact`, never reaped; with the fix,
    only the second key's own row does -- restoring the pre-WP-6d
    self-committing reap's own behavior, see `idempotency_begin`'s own
    docstring)."""
    cell = make_cell(app_a, FoundationConfig(idempotency_retention_ms=1))
    try:
        dev = ApplicationDeveloper(
            cell, Principal(application_id=app_a.app_id, credential_id="dev-f1", role=Role.DEVELOPER))
        runtime = ApplicationRuntime(
            cell, Principal(application_id=app_a.app_id, credential_id="rt-f1", role=Role.RUNTIME))
        dev.create_collection("notes_f1", {"title": "text"})

        runtime.transact(
            [{"type": "insert", "collection": "notes_f1", "values": {"title": "a"}}], idempotency_key="f1-reap-1")
        # `idempotency_retention_ms=1`: by the time the SECOND keyed
        # transact's own `idempotency_begin` reaps, this first record is
        # already older than the 1ms retention window.
        time.sleep(0.05)
        runtime.transact(
            [{"type": "insert", "collection": "notes_f1", "values": {"title": "b"}}], idempotency_key="f1-reap-2")

        conn = psycopg.connect(app_a.runtime_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key FROM _mdb_idempotency ORDER BY key")
                keys = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
        assert keys == ["f1-reap-2"], (
            f"expected only the second key's row to remain reaped, found {keys!r} -- the first "
            "key's row survives when idempotency_begin's own reap DELETE is discarded by begin()'s "
            "own rollback (F1 regression)"
        )
    finally:
        close_cell(cell)


def test_postgres_key_lock_timeout_maps_to_limit_exceeded(app_a) -> None:  # noqa: F811
    """Code-review fix F2 (Opus review 2, should-fix): before this fix,
    `idempotency_begin`'s own `pg_advisory_lock` had no `lock_timeout` --
    a second process contending for the SAME key's session lock waited
    UNBOUNDED, stalling every request this cell's own `self._lock` (an
    `RLock`, held for a keyed request's entire lookup -> execute -> store
    window) would otherwise let through too, not merely this one key.
    With a tiny `max_execution_ms` budget on the WAITING cell and a
    SECOND, independent cell already holding this key's session lock
    (a direct `idempotency_begin` call, never unlocked), the waiting
    request must fail promptly with the SAME `LIMIT_EXCEEDED`/
    `execution_ms` mapping every other PostgreSQL lock/statement-timeout
    site on this backend uses (`test_application_plane_limits.py`'s own
    `test_execution_ms_pg_lock_timeout_maps_to_limit_exceeded` is the
    row-lock counterpart of this same mapping) -- not hang forever."""
    key = "f2-lock-timeout-1"
    holder_cell = make_cell(app_a)
    waiter_cell = make_cell(app_a, FoundationConfig(max_execution_ms=300))
    try:
        now_ms = int(time.time() * 1000)
        holder_conn = holder_cell._backend.idempotency_connection(for_developer=False)
        held = holder_cell._backend.idempotency_begin(key, now_ms, 999_999_999, conn=holder_conn)
        assert held is None, "test setup: this key must start with no record"

        dev = ApplicationDeveloper(
            waiter_cell, Principal(application_id=app_a.app_id, credential_id="dev-f2", role=Role.DEVELOPER))
        runtime = ApplicationRuntime(
            waiter_cell, Principal(application_id=app_a.app_id, credential_id="rt-f2", role=Role.RUNTIME))
        dev.create_collection("notes_f2", {"title": "text"})

        start = time.monotonic()
        with pytest.raises(ResourceLimitError) as excinfo:
            runtime.transact(
                [{"type": "insert", "collection": "notes_f2", "values": {"title": "x"}}], idempotency_key=key)
        elapsed = time.monotonic() - start
        assert excinfo.value.details == {"limit_class": "execution_ms"}
        assert elapsed >= 0.05, f"denial returned suspiciously fast ({elapsed}s) for a 300ms budget"
        assert elapsed < _LOCK_TIMEOUT_S, f"denial took {elapsed}s -- looks like it actually hung"
    finally:
        holder_cell._backend.idempotency_unlock(key, conn=holder_conn)
        close_cell(holder_cell)
        close_cell(waiter_cell)


def test_postgres_unlock_runs_on_pass1_validation_failure(app_a) -> None:  # noqa: F811
    """Code-review fix F3 (Opus review 2, should-fix): a keyed request
    that fails during PASS 1 (a shape/target-existence validation, BEFORE
    any execution) must still release its session-scoped advisory lock --
    checked two ways: (1) `pg_locks` directly, against the failing
    cell's own runtime connection PID, shows zero advisory locks held
    afterward; (2) a SECOND, independent cell's request for the SAME key
    completes promptly, not blocked on a leaked lock.

    This is exactly the mutation-kill case named in the WP-6d rework
    instructions: moving `self._backend.idempotency_unlock(...)` out of
    the `finally` in `cell.py::_idempotency_pg_scope` must turn this test
    red (the lock then survives a pass-1 failure, since only a `finally`
    runs on every exit including a raise)."""
    cell_a = make_cell(app_a)
    cell_b = make_cell(app_a)
    try:
        dev_a = ApplicationDeveloper(
            cell_a, Principal(application_id=app_a.app_id, credential_id="dev-f3a", role=Role.DEVELOPER))
        runtime_a = ApplicationRuntime(
            cell_a, Principal(application_id=app_a.app_id, credential_id="rt-f3a", role=Role.RUNTIME))
        runtime_b = ApplicationRuntime(
            cell_b, Principal(application_id=app_a.app_id, credential_id="rt-f3b", role=Role.RUNTIME))
        dev_a.create_collection("notes_f3", {"title": "text"})

        key = "f3-unlock-1"
        # A target-existence failure -- `_plan_operation`'s own pass-1
        # check, NotFoundError, before `self._backend.begin()` is ever
        # called (`transact`'s own two-pass docstring) -- but reached
        # only AFTER `_idempotency_check` (and therefore `idempotency_
        # begin`'s own lock acquisition) already ran, since the widened
        # lock/`_idempotency_pg_scope` now covers pass 1 too for a keyed,
        # real request (code-review fix F5).
        with pytest.raises(FoundationError):
            runtime_a.transact(
                [{"type": "insert", "collection": "does_not_exist_f3", "values": {"title": "x"}}],
                idempotency_key=key,
            )

        with cell_a._backend._runtime.cursor() as cur:
            cur.execute("SELECT pg_backend_pid()")
            (pid,) = cur.fetchone()
        monitor = psycopg.connect(app_a.runtime_dsn)
        try:
            with monitor.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = %s", [pid])
                (advisory_lock_count,) = cur.fetchone()
        finally:
            monitor.close()
        assert advisory_lock_count == 0, (
            f"cell_a's own runtime connection (pid={pid}) still holds {advisory_lock_count} advisory "
            "lock(s) after a pass-1 validation failure -- idempotency_unlock did not run on this exit"
        )

        start = time.monotonic()
        result = runtime_b.transact(
            [{"type": "insert", "collection": "notes_f3", "values": {"title": "y"}}], idempotency_key=key)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"second cell's same-key request took {elapsed}s -- looks like it waited on a leaked lock"
        assert len(result) == 1
        assert len(runtime_b.read("notes_f3")) == 1
    finally:
        close_cell(cell_a)
        close_cell(cell_b)


def test_postgres_execution_failure_releases_lock_for_a_concurrent_retry(app_a) -> None:  # noqa: F811
    """Code-review fix F4 (Opus review 2, should-fix): mirrors
    `test_idempotency_records.py::test_execution_time_failure_after_
    begin_leaves_no_record`'s own technique (a destructive delete's
    pre-commit audit hook raising `AuditSinkUnavailable`, forcing a
    genuine rollback AFTER `begin()`/the idempotency lookup already ran)
    -- but here on `PostgresBackend`, with the RETRY issued from a
    SECOND, INDEPENDENT cell (see `_pg_pair`'s own docstring above for
    why that is the only way to prove the real, cross-connection session
    `pg_advisory_lock` was actually released, not merely this process's
    own `self._lock`). The retry must execute as a BRAND-NEW request --
    success, its own `request_id`, exactly one row's worth of effect --
    within a small `max_execution_ms` budget bounding this test's own
    wait (a leaked lock surfaces as `ResourceLimitError`, not a hang)."""
    from mitatedb_api import Filter
    from mitatedb_api.application_audit import ApplicationAuditSink
    from mitatedb_api.audit_dispatch import AuditRouter
    from mitatedb_api.backend_postgres import PostgresBackend
    from mitatedb_api.cell import _delete_confirmation_phrase
    from mitatedb_api.errors import AuditSinkUnavailable

    sink = ApplicationAuditSink()
    router = AuditRouter(sink)
    backend_a = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    cell_a = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend_a, audit_router=router)
    cell_b = make_cell(app_a, FoundationConfig(max_execution_ms=5_000))
    try:
        dev_a = ApplicationDeveloper(
            cell_a, Principal(application_id=app_a.app_id, credential_id="dev-f4a", role=Role.DEVELOPER))
        runtime_a = ApplicationRuntime(
            cell_a, Principal(application_id=app_a.app_id, credential_id="rt-f4a", role=Role.RUNTIME))
        runtime_b = ApplicationRuntime(
            cell_b, Principal(application_id=app_a.app_id, credential_id="rt-f4b", role=Role.RUNTIME))
        dev_a.create_collection("things_f4pg", {"id": "integer"})
        runtime_a.transact([{"type": "insert", "collection": "things_f4pg", "values": {"id": 1}}])

        sink.inject_fault(RuntimeError("sink down"))
        revision = cell_a._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things_f4pg", [Filter("id", "eq", 1)], revision)
        key = "f4-pg-rollback-1"
        delete_op = {
            "type": "delete", "collection": "things_f4pg", "destructive": True, "confirm": phrase,
            "filters": [Filter("id", "eq", 1)], "idempotency_key": key,
        }
        with pytest.raises(AuditSinkUnavailable):
            runtime_a.transact([delete_op])
        # The backend write already ran, on the SAME connection/
        # transaction the failed pre-commit hook aborted -- rolled back
        # together, so the row is still there.
        assert len(runtime_a.read("things_f4pg")) == 1

        start = time.monotonic()
        retried = runtime_b.transact([delete_op])
        elapsed = time.monotonic() - start
        assert len(retried) == 1
        assert "request_id" in retried[-1], "the retry must be a genuine execution, carrying its own request_id"
        assert len(runtime_b.read("things_f4pg")) == 0, "the retry's own delete must actually have executed"
        assert elapsed < 5.0, (
            f"retry from a second, independent cell took {elapsed}s -- looks like it waited on a leaked lock"
        )
    finally:
        close_cell(cell_a)
        close_cell(cell_b)
