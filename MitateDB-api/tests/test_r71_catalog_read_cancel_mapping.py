"""R-71 WP-1 (docs/work-orders/WORK_ORDER_R71_MITATEDB_CATALOG_READ_
CANCEL_MAPPING_V1.md D-1/D-3): the 8 developer-connection catalog reads
in `backend_postgres.py` -- `schema_count`, `field_domains`, `field_
types`, `all_field_types`, `field_constraints`, `field_types_and_
constraints`, `all_field_constraints`, `schema_revision` -- used to map a
role-level `statement_timeout` cancel (`QueryCanceled`) or the (never
reached in production on this path, migrations declare no `lock_timeout`
here) `LockNotAvailable` to the SAME trailing `except psycopg.Error` ->
`ValidationError` backstop every OTHER `psycopg.Error` on these reads
hits -- a resource-limit condition answered as a client REQUEST-SHAPE
fault (`VALIDATION_FAILED`). Each of the 8 now carries its own new
`except (QueryCanceled, LockNotAvailable):` branch, identical in shape
and message to the 12 pre-existing `backend_postgres.py` sites that
already had it.

Completion condition 1 (per-method mapping + rollback + message +
`limit_class`): `test_catalog_read_cancel_synthetic_injection_maps_to_
resource_limit_error` below, parametrized over the 8 methods and both
exception classes (`LockNotAvailable` synthetic for all 8;
`QueryCanceled` synthetic for the 7 that are not `all_field_types`,
which gets the REAL PostgreSQL precedent instead --
`test_all_field_types_real_postgresql_query_canceled_becomes_resource_
limit_error` below, matching `test_audit_query_reader_errors.py::_query_
canceled_scenario`'s own type: an ACCESS EXCLUSIVE lock on the target
table held from a separate connection while the developer role's own
`statement_timeout` is shortened, never a sleep raced against a query).
`schema_count` reads only `information_schema.tables`, not `_mdb_field_
types`/`_mdb_schema_revision`, so it cannot be blocked that way (this
work order's own §1「実効の上限について」) -- it stays synthetic for both
exception classes.

Completion condition 2 (client-visible result): `test_get_catalog_
returns_limit_exceeded_not_validation_failed_when_the_read_is_canceled`
drives a real `GET /v1/catalog` request (`all_field_types` is that
route's sole data source, per its own docstring) through a synthetic
cancel and checks the HTTP response, not just the Python exception.
"""
from __future__ import annotations

import contextlib

import psycopg
import pytest
from psycopg import sql

from mitatedb_api import backend_postgres as bp_module
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import ResourceLimitError

from .test_http import _get, app_a_stack  # noqa: F401 (fixture)
from .test_postgres import _dsn_with, app_a, platform, sessions_for  # noqa: F401 (fixtures)

_EXPECTED_MESSAGE = "operation exceeds the execution budget"
_EXPECTED_DETAILS = {"limit_class": "execution_ms"}


def _read_role_statement_timeout(admin_dsn: str, role: str) -> str | None:
    """Reads `role`'s own PRE-existing `statement_timeout` straight from
    `pg_roles.rolconfig` -- `None` if the role never had one set (this
    peer's own `platform` fixture in `test_postgres.py` deliberately never
    applies migration `0013_role_statement_timeouts.sql`, so a freshly
    provisioned application's developer role starts with none) -- so the
    scenario below can restore EXACTLY the value (or absence of one) that
    was in place before it shortened the timeout. Mirrors `test_audit_
    query_reader_errors.py::_read_auditreader_statement_timeout`, applied
    to an application's own developer role instead of the platform-wide
    auditreader."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT rolconfig FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
            row = cur.fetchone()
    finally:
        admin.close()
    rolconfig = row[0] if row else None
    if rolconfig:
        for entry in rolconfig:
            if entry.startswith("statement_timeout="):
                return entry.split("=", 1)[1]
    return None


def _set_role_statement_timeout(admin_dsn: str, role: str, value: str | None) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            if value is None:
                cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(sql.Identifier(role)))
            else:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                    sql.Identifier(role), sql.Literal(value)))
    finally:
        admin.close()


@contextlib.contextmanager
def _raise_on_next_execute(exc: Exception):
    """Monkeypatches `backend_postgres._execute` (the module's own R-2
    choke point -- "the ONLY call to `cursor.execute` in this module",
    that function's own docstring) to raise `exc` on every call for the
    duration of the `with` block, then restores the real function --
    mirrors `test_constraints_declaration.py::test_alter_field_
    constraints_lock_table_blocks_concurrent_write`'s own `_patched_
    execute` monkeypatch of the same module-level function, applied here
    to drive a synthetic cancel rather than to pause on a lock.

    Before raising `exc`, issues one genuinely invalid statement (`SELECT
    1/0`, a real server-side `DivisionByZero`) straight through the SAME
    real cursor -- this is what makes the "rollback happened, the next
    real call succeeds" property (completion condition 1) actually
    observable against a synthetic exception: without it, `exc` is a pure
    Python-level raise that never touches the real connection, so a
    missing `self._developer.rollback()` in the branch under test would
    leave the connection in a state indistinguishable from a rolled-back
    one, and a subsequent real call would succeed either way."""
    original = bp_module._execute
    def _raising(cursor, statement, params=()):
        try:
            cursor.execute("SELECT 1/0")
        except psycopg.Error:
            pass
        raise exc
    bp_module._execute = _raising
    try:
        yield
    finally:
        bp_module._execute = original


_METHOD_CALLS = {
    "schema_count": lambda backend, entity: backend.schema_count(),
    "field_domains": lambda backend, entity: backend.field_domains(entity),
    "field_types": lambda backend, entity: backend.field_types(entity),
    "all_field_types": lambda backend, entity: backend.all_field_types(),
    "field_constraints": lambda backend, entity: backend.field_constraints(entity),
    "field_types_and_constraints": lambda backend, entity: backend.field_types_and_constraints(entity),
    "all_field_constraints": lambda backend, entity: backend.all_field_constraints(),
    "schema_revision": lambda backend, entity: backend.schema_revision(),
}

# `all_field_types`'s own `QueryCanceled` case is carried by the REAL
# PostgreSQL precedent test below instead (work order docs/work-orders/
# WORK_ORDER_R71_MITATEDB_CATALOG_READ_CANCEL_MAPPING_V1.md §2.2 完了条件
# 1's own "少なくとも1本は実 PostgreSQL の本物の QueryCanceled で通す"
# requirement) -- every other combination here is a synthetic injection
# (`LockNotAvailable` is synthetic for all 8, since migrations declare no
# `lock_timeout` on this path and the branch never fires in production,
# that same work order's own §1「実効の上限について」).
_SYNTHETIC_CASES = [
    pytest.param(name, psycopg.errors.QueryCanceled, id=f"{name}-QueryCanceled")
    for name in _METHOD_CALLS
    if name != "all_field_types"
] + [
    pytest.param(name, psycopg.errors.LockNotAvailable, id=f"{name}-LockNotAvailable")
    for name in _METHOD_CALLS
]


@pytest.mark.parametrize(("method_name", "exc_cls"), _SYNTHETIC_CASES)
def test_catalog_read_cancel_synthetic_injection_maps_to_resource_limit_error(app_a, method_name, exc_cls) -> None:
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend)
        dev, _runtime = sessions_for(cell, app_a.app_id)
        dev.create_collection("r71cat", {"title": "text"})

        call = _METHOD_CALLS[method_name]
        with _raise_on_next_execute(exc_cls("synthetic cancel -- never a real backend rejection")):
            with pytest.raises(ResourceLimitError) as excinfo:
                call(backend, "r71cat")

        assert str(excinfo.value) == _EXPECTED_MESSAGE
        assert excinfo.value.details == _EXPECTED_DETAILS

        # Rollback happened on the SAME developer connection: the next
        # real call over it succeeds instead of hitting `psycopg.errors.
        # InFailedSqlTransaction` (an aborted, un-rolled-back transaction).
        assert backend.schema_count() >= 0
    finally:
        backend.close()


def test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error(platform, app_a) -> None:
    """work order docs/work-orders/WORK_ORDER_R71_MITATEDB_CATALOG_READ_
    CANCEL_MAPPING_V1.md §2.2 完了条件 1 (実 PostgreSQL の本物の
    QueryCanceled):
    `all_field_types` reads `_mdb_field_types` directly and is one of the
    7 catalog reads a real lock can block (`schema_count` cannot -- it
    only ever reads `information_schema.tables`). An ACCESS EXCLUSIVE
    lock on `_mdb_field_types`, held from a separate ADMIN connection
    (never the developer role itself, so shortening the developer role's
    own `statement_timeout` below cannot also cut the lock-holding
    connection short), blocks the developer connection's own read until
    ITS OWN (shortened) `statement_timeout` cancels it -- never a sleep
    raced against a query, mirroring `test_audit_query_reader_errors.py::
    _query_canceled_scenario`'s own type."""
    role = app_a.developer_role
    original_timeout = _read_role_statement_timeout(platform.admin_dsn, role)
    lock_dsn = _dsn_with(platform.admin_dsn, dbname=app_a.database)
    backend = None
    lock_conn = None
    try:
        _set_role_statement_timeout(platform.admin_dsn, role, "200ms")
        # `PostgresBackend.__init__` opens the developer connection right
        # away -- it must be opened AFTER the ALTER ROLE above, since a
        # role-level `SET` only takes effect for sessions started after it.
        backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)

        lock_conn = psycopg.connect(lock_dsn)
        with lock_conn.cursor() as cur:
            cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier("_mdb_field_types")))

        with pytest.raises(ResourceLimitError) as excinfo:
            backend.all_field_types()

        assert str(excinfo.value) == _EXPECTED_MESSAGE
        assert excinfo.value.details == _EXPECTED_DETAILS

        lock_conn.rollback()
        lock_conn.close()
        lock_conn = None

        # Rollback happened on the developer connection -- the next real
        # call over the SAME connection succeeds (still under the
        # shortened 200ms timeout, an information-only read with nothing
        # left to block on).
        assert backend.all_field_types() == {}
    finally:
        if lock_conn is not None:
            lock_conn.rollback()
            lock_conn.close()
        if backend is not None:
            backend.close()
        _set_role_statement_timeout(platform.admin_dsn, role, original_timeout)


def test_get_catalog_returns_limit_exceeded_not_validation_failed_when_the_read_is_canceled(app_a_stack) -> None:
    """完了条件 2: `GET /v1/catalog`'s sole data source is `all_field_
    types` (that method's own docstring) -- a cancel on it must reach the
    client as `LIMIT_EXCEEDED`/`limit_class=execution_ms` (`http.py`'s own
    `ResourceLimitError` -> 413 mapping), never `VALIDATION_FAILED`. No
    audit-row assertion here: D-3's own reading of `audit_dispatch.py`'s
    `DURABLE_DENIAL_CODES` found `LIMIT_EXCEEDED` is not a durable-denial
    code on this peer."""
    with _raise_on_next_execute(psycopg.errors.QueryCanceled("synthetic cancel -- never a real backend rejection")):
        response = _get(app_a_stack, "/v1/catalog", bearer=app_a_stack.runtime_bearer)

    assert response.status_code == 413, response.text
    body = response.json()
    assert body["code"] == "LIMIT_EXCEEDED"
    assert body["code"] != "VALIDATION_FAILED"
    assert body["details"]["limit_class"] == "execution_ms"
