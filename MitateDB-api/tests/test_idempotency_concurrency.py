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
