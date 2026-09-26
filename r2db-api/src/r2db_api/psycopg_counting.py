"""R-79 (docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md
§2.1, D-1/D-2): `CountingCursor`/`CountingConnection` count every
`execute()`/`executemany()` call on a connection, and `probe_prepared_
statements` (with its own two small helpers, `PREPARED_STATEMENTS_SQL`/
`prepared_stats_skeleton`) reads `pg_prepared_statements` for one
connection, so a per-peer caller (`r2db_api.postgres._RolePool.prepared_
stats`, `mitatedb_api.backend_postgres.PostgresBackend.prepared_stats`)
can divide a connection's observed prepared-statement execution count by
its total `execute()` count (`share`, WO §1.2 D-3) to see how much of a
connection's own traffic is actually landing on a prepared statement.

Rework (指摘 3, 2026-09-23): the probe used to be duplicated,
nearly verbatim, in both peers' own `postgres.py`/`backend_postgres.py`.
It lives here instead now, in the ONE module already required to be
byte-identical between peers (WO §1.2 D-1, WO §6.1 H-1/H-5) -- a single
copy of the probe logic, not two copies that could silently drift. Every
name the probe needs is PUBLIC here (`PREPARED_STATEMENTS_SQL`,
`prepared_stats_skeleton`, `probe_prepared_statements`, no leading
underscore) so each peer's own module can import it directly.

Byte-identical between `r2db-api/src/r2db_api/psycopg_counting.py` and
`MitateDB-api/src/mitatedb_api/psycopg_counting.py` (WO §1.2 D-1, WO
§6.1 H-1/H-5) -- a same-named test in each peer's own `tests/` pins
the sha256 match directly; `_ISOMORPHIC_TARGETS` is never touched for it
(that table normalizes away a leading docstring before comparing, so it
cannot pin whole-module identity as tightly as a straight sha256 compare
does, and doing both would be redundant for a module this is the entire
content of).

`cursor_factory` must be assigned inside `__init__`, never as a class
attribute: `psycopg.Connection.__init__` unconditionally overwrites
`self.cursor_factory` with the base `Cursor` class (`psycopg/connection.
py:78`) every time a connection is constructed -- a class attribute on a
subclass is shadowed by that instance attribute the moment `__init__`
runs, so the override below happens AFTER `super().__init__()`, not as a
`CountingConnection`-level class attribute (WO §1.3 (6): the work order's
own prototype hit exactly this -- `statement_count` stayed 0 until the
assignment moved into `__init__`).

No lock anywhere in this module: every connection either class ever wraps
is used by exactly one caller at a time already (pool checkout / cell
lock serializes it upstream, WO §1.2 D-1's own docstring on the four call
sites this applies to) -- every counter/wall-time update below runs on
that one caller's own thread, needing no lock of its own, whether it is a
plain increment or a `time.perf_counter()` pair wrapped in `try`/`finally`
around a delegated call that may itself raise. `probe_prepared_statements`
itself is read-only and runs strictly after the measured operation, never
on the hot path (WO §1.2 D-2).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus


class CountingCursor(psycopg.Cursor):
    """A `psycopg.Cursor` that increments its own connection's
    `execute_count`/`executemany_count` before delegating to the base
    implementation -- counted whether or not the call goes on to raise,
    since a failed statement is still one attempt at execution. The
    connection's `db_wall_ms` also rises by the wall time the delegated
    call itself takes, added in a `finally` so a raised exception still
    counts the round trip that failed."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.connection.execute_count += 1
        start = time.perf_counter()
        try:
            return super().execute(*args, **kwargs)
        finally:
            self.connection.db_wall_ms += (time.perf_counter() - start) * 1000.0

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        self.connection.executemany_count += 1
        start = time.perf_counter()
        try:
            return super().executemany(*args, **kwargs)
        finally:
            self.connection.db_wall_ms += (time.perf_counter() - start) * 1000.0


class CountingConnection(psycopg.Connection):
    """A `psycopg.Connection` whose `cursor_factory` is `CountingCursor`
    and that carries its own `execute_count`/`executemany_count`
    integers, both starting at 0 and rising only through a `CountingCursor`
    this connection itself produced. Construct via `CountingConnection.
    connect(dsn, ...)` -- the same classmethod plain `psycopg.connect` is
    itself an alias for (`psycopg/__init__.py`: `connect = Connection.
    connect`).

    Also carries `db_wall_ms` (float, milliseconds) and `txn_count` (int),
    both starting at 0/0.0 and rising through `CountingCursor.execute`/
    `executemany` above and the `commit`/`rollback`/`transaction`
    overrides below -- together the total time this one connection spends
    waiting on PostgreSQL and the number of transaction boundaries it
    opens or closes (`transaction()`'s own enter side counts one boundary
    for `BEGIN`, its exit side counts a second for `COMMIT`/`ROLLBACK`/
    `RELEASE`/`ROLLBACK TO SAVEPOINT`). A statement's own implicit `BEGIN`
    (psycopg opens one silently before the first statement of a new
    transaction) lands inside that statement's own `execute()` wall time
    above and is never counted as a separate entry in `txn_count`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.execute_count = 0
        self.executemany_count = 0
        self.db_wall_ms = 0.0
        self.txn_count = 0
        self.cursor_factory = CountingCursor

    def commit(self) -> None:
        """Times the delegated `commit()` into `db_wall_ms` and counts it
        as one transaction boundary, in a `finally` so a raised exception
        still counts the round trip that was attempted."""
        start = time.perf_counter()
        try:
            super().commit()
        finally:
            self.db_wall_ms += (time.perf_counter() - start) * 1000.0
            self.txn_count += 1

    def rollback(self) -> None:
        """Same accounting as `commit` above, for `rollback()`."""
        start = time.perf_counter()
        try:
            super().rollback()
        finally:
            self.db_wall_ms += (time.perf_counter() - start) * 1000.0
            self.txn_count += 1

    @contextmanager
    def transaction(self, *args: Any, **kwargs: Any) -> Any:
        """Wraps the base `Connection.transaction()` context manager
        (never psycopg's own private internal command machinery) by
        driving its `__enter__`/`__exit__` directly rather than through a
        nested `with`, so the wall time and transaction count on either
        side of `yield` are each attributed to exactly the boundary that
        produced them: entering this context sends `BEGIN` (one round
        trip, one `txn_count`), leaving it sends `COMMIT`/`ROLLBACK`/
        `RELEASE`/`ROLLBACK TO SAVEPOINT` (a second round trip, a second
        `txn_count`). Exception handling on the exit side is delegated
        entirely to the base `__exit__`'s own return value, so `psycopg.
        Rollback` raised inside the `with` block is swallowed exactly as
        the base class swallows it, and any other exception propagates
        with its original type unchanged."""
        base_cm = super().transaction(*args, **kwargs)
        enter_start = time.perf_counter()
        try:
            tx = base_cm.__enter__()
        finally:
            # Counted even if BEGIN itself raises (the round trip was still
            # attempted), matching `commit`/`rollback` above rather than
            # only counting a round trip that succeeded.
            self.db_wall_ms += (time.perf_counter() - enter_start) * 1000.0
            self.txn_count += 1
        try:
            yield tx
        except BaseException as exc:
            exit_start = time.perf_counter()
            try:
                suppressed = base_cm.__exit__(type(exc), exc, exc.__traceback__)
            finally:
                # Counted even if the exit round trip (ROLLBACK/ROLLBACK TO
                # SAVEPOINT) itself raises; that raised exception still
                # propagates below unchanged.
                self.db_wall_ms += (time.perf_counter() - exit_start) * 1000.0
                self.txn_count += 1
            if not suppressed:
                raise
        else:
            exit_start = time.perf_counter()
            try:
                base_cm.__exit__(None, None, None)
            finally:
                # Counted even if the exit round trip (COMMIT/RELEASE) itself
                # raises; that raised exception still propagates unchanged.
                self.db_wall_ms += (time.perf_counter() - exit_start) * 1000.0
                self.txn_count += 1


# R-79 (WO §1.2 D-2): read-only probe of `pg_prepared_statements`, shared
# by both peers' own `prepared_stats()` (rework 指摘 3 --
# formerly duplicated per peer). `ORDER BY prepare_time` matches the work
# order's own literal SQL text (§1.2 D-2); `name`/`statement`/`generic_
# plans`/`custom_plans` are the four columns this module reads, `prepare_
# time` only orders the read and is never surfaced.
PREPARED_STATEMENTS_SQL = (
    "SELECT name, statement, prepare_time, generic_plans, custom_plans "
    "FROM pg_prepared_statements ORDER BY prepare_time"
)


def prepared_stats_skeleton(conn: "psycopg.Connection[Any]", label: str, *, error: str | None = None) -> dict[str, Any]:
    """The 13-key dict shape `probe_prepared_statements` (below) and its
    caller's own exception branch both build from -- kept as one function
    so the key set can never drift between the "everything worked",
    "left alone because not IDLE", and "probe itself raised" cases. Reads
    only PUBLIC `psycopg.Connection` surface (`.info.transaction_status`,
    `.prepare_threshold`, `.prepared_max`) plus the four plain integer/
    float attributes `CountingConnection` itself defines -- never the
    private `_prepared`/`_counts`/`_names` psycopg keeps internally (WO
    §1.1 (e)). `db_wall_ms`/`txn_count` read the connection's own running
    totals, unaffected by this read itself."""
    return {
        "label": label,
        "transaction_status": TransactionStatus(conn.info.transaction_status).name,
        "probed": False,
        "execute_count": conn.execute_count,
        "executemany_count": conn.executemany_count,
        "prepared": 0,
        "prepared_execs": 0,
        "prepare_threshold": conn.prepare_threshold,
        "prepared_max": conn.prepared_max,
        "prepared_statements": [],
        "error": error,
        "db_wall_ms": conn.db_wall_ms,
        "txn_count": conn.txn_count,
    }


def probe_prepared_statements(conn: "psycopg.Connection[Any]", label: str) -> dict[str, Any]:
    """R-79 (WO §1.2 D-2): probe exactly one connection. Only probes when
    `conn.info.transaction_status` is already IDLE at entry (WO §6.1
    L-13) -- a non-IDLE connection is left completely alone (`probed=
    False`, `transaction_status` names that state) rather than probed,
    since this function's own `commit()` below on a connection some caller
    left mid-transaction would silently finish that caller's transaction.

    The read itself is a bare `psycopg.Cursor(conn)` (never `conn.cursor()`
    -- that would go through `CountingConnection`'s own `CountingCursor`
    and count the probe's own SELECT as application traffic), with
    `prepare=False` (WO §1.1 F3: a key still lands in psycopg's client-side
    bookkeeping either way, but `prepare=False` keeps the probe's own
    SELECT from ever becoming a SERVER-side prepared statement, so it never
    shows up in the very view it reads -- completion condition 12).
    Immediately followed by `psycopg.Connection.commit(conn)` -- the BASE
    class method, called directly rather than through this connection's
    own `commit()` override, so probing a connection never counts the
    probe's own commit into that connection's `db_wall_ms`/`txn_count`.
    Never `rollback()` either way (WO §1.1 F2: a rollback on a non-IDLE
    connection clears every prepared statement on it -- this function
    must not destroy the very thing it observes).

    Raises whatever the database round trip itself raises (a real driver
    error, a mocked failure injected by a test) -- this function does NOT
    catch anything itself; the CALLER (`r2db_api.postgres._RolePool.
    prepared_stats`, `mitatedb_api.backend_postgres.PostgresBackend.
    prepared_stats`) is the one that catches per connection, reports
    `probed=False`/`error=type(exc).__name__` (never the exception's
    message, WO §1.1 (d)), rolls the connection back first if the failure
    left it mid-transaction (rework 指摘 5 -- an aborted
    connection must never rejoin a pool/cell still aborted), and is
    responsible for returning `conn` to wherever it came from regardless
    of what this call raises (WO §1.2 D-2, WO §6.1 H-4) -- catching here
    instead would make that caller-side handling unreachable dead code,
    since nothing would ever escape this function to trigger it."""
    result = prepared_stats_skeleton(conn, label)
    if conn.info.transaction_status != TransactionStatus.IDLE:
        return result
    with psycopg.Cursor(conn) as cur:
        cur.execute(PREPARED_STATEMENTS_SQL, prepare=False)
        rows = cur.fetchall()
    psycopg.Connection.commit(conn)
    statements = [
        {"name": name, "generic_plans": generic, "custom_plans": custom, "statement": statement[:80]}
        for name, statement, _prepare_time, generic, custom in rows
    ]
    result["probed"] = True
    result["prepared"] = len(statements)
    result["prepared_execs"] = sum(s["generic_plans"] + s["custom_plans"] for s in statements)
    result["prepared_statements"] = statements
    return result
