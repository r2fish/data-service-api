"""R-71 WP-1 (docs/work-orders/WORK_ORDER_R71_MITATEDB_CATALOG_READ_
CANCEL_MAPPING_V1.md D-1/D-3): the 8 developer-connection catalog reads
in `backend_postgres.py` -- `schema_count`, `field_domains`, `field_
types`, `all_field_types`, `field_constraints`, `field_types_and_
constraints`, `all_field_constraints`, `schema_revision` -- map a
statement `statement_timeout`/`lock_timeout` cancel (`QueryCanceled`/
`LockNotAvailable`) to the SAME trailing `except psycopg.Error` ->
`ValidationError` backstop every OTHER `psycopg.Error` on these reads
hits -- a resource-limit condition answered as a client REQUEST-SHAPE
fault (`VALIDATION_FAILED`). Each of the 8 carries its own
`except (QueryCanceled, LockNotAvailable):` branch, identical in shape
and message to the 12 pre-existing `backend_postgres.py` sites that
already had it. R-87 correction (2026-09-23): since R-87, each of the 8
also issues its own per-transaction `SET LOCAL statement_timeout`/
`lock_timeout` (`backend_postgres.py`, R-87 D-2) -- `LockNotAvailable` is
therefore no longer a branch that never fires in production; the role
level itself still declares no `lock_timeout`, only the per-transaction
`SET LOCAL` does (see the inline comment above `_SYNTHETIC_CASES` below
for the same correction, kept in sync with this one).

Completion condition 1 (per-method mapping + rollback + message +
`limit_class`): `test_catalog_read_cancel_synthetic_injection_maps_to_
resource_limit_error` below, parametrized over the 8 methods and both
exception classes (`LockNotAvailable` synthetic for all 8;
`QueryCanceled` synthetic for the 7 that are not `all_field_types`).
`all_field_types`'s own `QueryCanceled` case is carried by the REAL
PostgreSQL precedent test `test_r87_catalog_read_execution_ms.py::
test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_
role_value` instead (moved there by R-87 D-5 (2) -- that work order's own
review found the role-mutation type this test used to run here no longer
demonstrates a bound, since a role mutation is now overridden by every
one of the 8 reads' own `SET LOCAL`), matching `test_audit_query_reader_
errors.py::_query_canceled_scenario`'s own type: an ACCESS EXCLUSIVE lock
on the target table held from a separate connection, never a sleep raced
against a query. `schema_count` reads only `information_schema.tables`,
not `_mdb_field_types`/`_mdb_schema_revision`, so it cannot be blocked
that way (this work order's own §1「実効の上限について」) -- it stays
synthetic for both exception classes.

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

# `all_field_types`'s own `QueryCanceled` case is carried by the real
# PostgreSQL precedent test in `test_r87_catalog_read_execution_ms.py`
# instead (moved there, R-87 -- see this file's own module docstring)
# -- every combination below is a synthetic injection. R-87 correction
# (2026-09-23): `LockNotAvailable` is synthetic HERE for all 8, but is NO
# LONGER a branch that never fires in production -- each of the 8 now
# issues its own per-transaction `SET LOCAL lock_timeout` (`backend_
# postgres.py`, R-87 D-2), so a real lock wait on one of these reads can
# reach this exact branch in a real deployment (the role level itself
# still declares no `lock_timeout`, only the per-transaction `SET LOCAL`
# does).
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
