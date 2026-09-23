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
sites this applies to) -- the two counters below are plain integer
increments, nothing more, matching the work order's own "hot path gets
one integer addition, nothing else" constraint (WO §1.1 (b)). `probe_
prepared_statements` itself is read-only and runs strictly after the
measured operation, never on the hot path (WO §1.2 D-2).
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.pq import TransactionStatus


class CountingCursor(psycopg.Cursor):
    """A `psycopg.Cursor` that increments its own connection's
    `execute_count`/`executemany_count` before delegating to the base
    implementation -- counted whether or not the call goes on to raise,
    since a failed statement is still one attempt at execution."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.connection.execute_count += 1
        return super().execute(*args, **kwargs)

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        self.connection.executemany_count += 1
        return super().executemany(*args, **kwargs)


class CountingConnection(psycopg.Connection):
    """A `psycopg.Connection` whose `cursor_factory` is `CountingCursor`
    and that carries its own `execute_count`/`executemany_count`
    integers, both starting at 0 and rising only through a `CountingCursor`
    this connection itself produced. Construct via `CountingConnection.
    connect(dsn, ...)` -- the same classmethod plain `psycopg.connect` is
    itself an alias for (`psycopg/__init__.py`: `connect = Connection.
    connect`)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.execute_count = 0
        self.executemany_count = 0
        self.cursor_factory = CountingCursor


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
    """The 11-key dict shape `probe_prepared_statements` (below) and its
    caller's own exception branch both build from -- kept as one function
    so the key set can never drift between the "everything worked",
    "left alone because not IDLE", and "probe itself raised" cases. Reads
    only PUBLIC `psycopg.Connection` surface (`.info.transaction_status`,
    `.prepare_threshold`, `.prepared_max`) plus the two plain integer
    attributes `CountingConnection` itself defines -- never the private
    `_prepared`/`_counts`/`_names` psycopg keeps internally (WO §1.1 (e))."""
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
    Immediately followed by `conn.commit()`, never `rollback()` (WO §1.1
    F2: a rollback on a non-IDLE connection clears every prepared statement
    on it -- this function must not destroy the very thing it observes).

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
    conn.commit()
    statements = [
        {"name": name, "generic_plans": generic, "custom_plans": custom, "statement": statement[:80]}
        for name, statement, _prepare_time, generic, custom in rows
    ]
    result["probed"] = True
    result["prepared"] = len(statements)
    result["prepared_execs"] = sum(s["generic_plans"] + s["custom_plans"] for s in statements)
    result["prepared_statements"] = statements
    return result
