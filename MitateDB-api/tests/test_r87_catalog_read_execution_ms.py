"""R-87 WP-1 (docs/work-orders/WORK_ORDER_R87_MITATEDB_CATALOG_READ_
EXECUTION_MS_V1.md D-1/D-2/D-4): the 8 developer-connection catalog reads
in `backend_postgres.py` -- `schema_count`, `field_domains`, `field_
types`, `all_field_types`, `field_constraints`, `field_types_and_
constraints`, `all_field_constraints`, `schema_revision` -- run inside the
request scope that opened the transaction they read in, and that scope set
`statement_timeout`/`lock_timeout` when it opened: from the request's
deadline, or, for a scope with no deadline (these tests call the backend
with no request around it), from `self._default_timeout_ms` --
`PostgresBackend.__init__`'s keyword `max_execution_ms` when given, else
`FoundationConfig`'s own class-attribute default (5000). So the effective
bound on these 8 reads is always the CONSTRUCTED value, never the role-
level `statement_timeout` `0013_role_statement_timeouts.sql` sets
(`test_application_audit.py`'s own `test_developer_connection_used_by_the_
catalog_path_carries_the_role_level_statement_timeout` still observes that
role-level value, but only on a connection outside a scope).

Completion condition 2 (per-method wiring): `test_catalog_reads_in_a_
scope_without_a_deadline_use_the_constructed_statement_and_lock_timeout`
below, parametrized over the 8 methods, wraps `backend_postgres._execute`
to read `pg_settings.setting` (raw ms, never `SHOW`) on the SAME cursor
immediately before the first non-`SET LOCAL` statement each method
issues, in a scope the call opened for itself.

Completion condition 3 (bare construction): `test_bare_construction_
uses_the_foundation_config_default_execution_ms` below -- no `max_
execution_ms` kwarg, same probe, expects `FoundationConfig`'s own
default.

Completion condition 4 (D-5 (2), moved here from `test_r71_catalog_read_
cancel_mapping.py` -- see that file's own module docstring for why):
`test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_
role_value` below replaces R-71's `test_all_field_types_real_postgresql_
query_canceled_becomes_resource_limit_error`, which drove the real
`QueryCanceled` by shortening the developer ROLE's own `statement_
timeout` (`ALTER ROLE ... SET statement_timeout = '200ms'`) -- a role
mutation `SET LOCAL` now overrides on every one of these 8 reads, so
that type no longer demonstrates a bound at all. The replacement sets
the developer role's own `statement_timeout` to `5000ms` itself (`app_a`'s
own `platform` fixture never applies migration `0013_role_statement_
timeouts.sql`, so the role otherwise starts unbounded) and constructs the
backend with `max_execution_ms=200`, so "role 5000ms vs. constructed
200ms" is a real comparison; the block is real (an ACCESS EXCLUSIVE lock
on `_mdb_field_types` from a separate admin connection), so the
`QueryCanceled` this drives is genuinely PostgreSQL's, not synthetic.

Completion condition 6 (D-4): `test_build_app_passes_the_declared_
execution_ms_to_the_constructed_backend` below drives a real `main.
build_app(...)` and reads the constructed cell's own backend attribute.
"""
from __future__ import annotations

import threading
import time

import psycopg
import pytest
from psycopg import sql

from mitatedb_api import backend_postgres as bp_module
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import ResourceLimitError

from .scoped_backend import scoped
from .test_main import _base_env, main_module, probe_app  # noqa: F401 (fixtures)
from .test_postgres import _dsn_with, app_a, platform, sessions_for  # noqa: F401 (fixtures)

# Above 5000 (both the role-level default, `0013_role_statement_
# timeouts.sql`, and `FoundationConfig`'s own class-attribute default) --
# a coincidental match against either default cannot pass these tests by
# accident (mirrors `test_main.py`'s own `MITATEDB_MAX_CONCURRENCY=7`
# precedent for the identical reason), and directly measures `:685`'s own
# claim that a deployment declaring `execution_ms` above 5000 also raises
# the effective bound on these 8 reads above 5000 (`security/CONTROL_
# MAPPING.md`, R-87 (1b)/(ii)).
_CONSTRUCTED_MS = 7654

_METHOD_CALLS = {
    "schema_count": lambda backend, entity: scoped(backend).schema_count(),
    "field_domains": lambda backend, entity: scoped(backend).field_domains(entity),
    "field_types": lambda backend, entity: scoped(backend).field_types(entity),
    "all_field_types": lambda backend, entity: scoped(backend).all_field_types(),
    "field_constraints": lambda backend, entity: scoped(backend).field_constraints(entity),
    "field_types_and_constraints": lambda backend, entity: scoped(backend).field_types_and_constraints(entity),
    "all_field_constraints": lambda backend, entity: scoped(backend).all_field_constraints(),
    "schema_revision": lambda backend, entity: scoped(backend).schema_revision(),
}


def _read_role_statement_timeout(admin_dsn: str, role: str) -> str | None:
    """Reads `role`'s own PRE-existing `statement_timeout` straight from
    `pg_roles.rolconfig` -- `None` if the role never had one set (`app_a`'s
    own `platform` fixture in `test_postgres.py` deliberately never applies
    migration `0013_role_statement_timeouts.sql`, so a freshly provisioned
    application's developer role starts with none) -- so the scenario below
    can restore EXACTLY the value (or absence of one) that was in place
    before it set the role-level timeout. Same shape as R-71's own deleted
    helper of the identical name (`test_r71_catalog_read_cancel_mapping.py`
    module docstring, R1-13 of that work order's design review)."""
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


def _probe_first_real_statement(captured: dict) -> None:
    """Monkeypatches `backend_postgres._execute` (the module's own R-2
    choke point) so that, on the FIRST call whose composed SQL text does
    not start with `SET LOCAL`, this reads `pg_settings.setting` for both
    `statement_timeout` and `lock_timeout` over the SAME cursor, before
    letting the real statement run -- observing the live session state a
    timeout would actually be enforced against (never the SQL text `_set_
    timeouts` issues, never `SHOW`). The caller's own `finally` restores
    `bp_module._execute` to the value it held before this call."""
    original = bp_module._execute

    def probing_execute(cursor, statement, params=()):
        text = statement.as_string(None)
        if not text.startswith("SET LOCAL") and "statement_timeout" not in captured:
            cursor.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
            captured["statement_timeout"] = cursor.fetchone()[0]
            cursor.execute("SELECT setting FROM pg_settings WHERE name = 'lock_timeout'")
            captured["lock_timeout"] = cursor.fetchone()[0]
        return original(cursor, statement, params)

    bp_module._execute = probing_execute


@pytest.mark.parametrize("method_name", list(_METHOD_CALLS))
def test_catalog_reads_in_a_scope_without_a_deadline_use_the_constructed_statement_and_lock_timeout(
    app_a, method_name,
) -> None:
    backend = PostgresBackend(
        runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn, max_execution_ms=_CONSTRUCTED_MS,
    )
    original = bp_module._execute
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend)
        dev, _runtime = sessions_for(cell, app_a.app_id)
        dev.create_collection("r87cat", {"title": "text"})

        captured: dict[str, str] = {}
        _probe_first_real_statement(captured)
        try:
            _METHOD_CALLS[method_name](backend, "r87cat")
        finally:
            bp_module._execute = original

        # 空振り禁止 (§1.5 の 32): both keys are always set together by
        # `_probe_first_real_statement`, so a non-empty dict is already
        # proof of at least one observation for this method.
        assert captured, f"{method_name} observed zero pg_settings reads"
        assert captured["statement_timeout"] == str(_CONSTRUCTED_MS)
        assert captured["lock_timeout"] == str(_CONSTRUCTED_MS)
    finally:
        backend.close()


def test_bare_construction_uses_the_foundation_config_default_execution_ms(app_a) -> None:
    """D-5 (3): no `max_execution_ms` kwarg -- the same construction every
    pre-existing test/tooling call site in this package already uses --
    still carries the `FoundationConfig` class-attribute default (5000),
    never a proxy such as "non-zero"."""
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    original = bp_module._execute
    try:
        cell = ApplicationCell(app_a.app_id, FoundationConfig(), backend=backend)
        dev, _runtime = sessions_for(cell, app_a.app_id)
        dev.create_collection("r87bare", {"title": "text"})

        captured: dict[str, str] = {}
        _probe_first_real_statement(captured)
        try:
            scoped(backend).schema_count()
        finally:
            bp_module._execute = original

        assert captured, "observed zero pg_settings reads"
        assert captured["statement_timeout"] == str(FoundationConfig.max_execution_ms)
        assert captured["lock_timeout"] == str(FoundationConfig.max_execution_ms)
    finally:
        backend.close()


def test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_role_value(
    platform, app_a,
) -> None:
    """D-5 (2), moved from `test_r71_catalog_read_cancel_mapping.py` (see
    this file's own module docstring): `app_a`'s own `platform` fixture
    (`test_postgres.py`) deliberately never applies migration `0013_role_
    statement_timeouts.sql`, so the developer role's own `statement_
    timeout` starts UNSET (no bound at all) -- for "role 5000ms vs.
    constructed 200ms" to be a real comparison, this test sets the
    developer role's own `statement_timeout` to `5000ms` itself, over a
    SEPARATE admin connection, BEFORE constructing `PostgresBackend`
    (opening the developer connection AFTER the `ALTER ROLE` -- a role-
    level `SET` only takes effect for sessions started after it, same
    ordering R-71's own deleted `_set_role_statement_timeout`-driven test
    used), and restores the role's own prior value in `finally`. Only the
    CONSTRUCTED value (200) binds. An ACCESS EXCLUSIVE lock on `_mdb_
    field_types`, held from a separate ADMIN connection (never the
    developer role itself), blocks `all_field_types()`'s own read until
    the construction-time `SET LOCAL` cancels it -- never a sleep raced
    against a query, mirroring `test_audit_query_reader_errors.py::
    _query_canceled_scenario`'s own type. The test name names no
    exception class deliberately (`statement_timeout`/`lock_timeout` are
    set to the SAME value here, so either could fire first depending on
    server timing) -- only `ResourceLimitError`/message/`details`/elapsed
    time are fixed."""
    role = app_a.developer_role
    lock_dsn = _dsn_with(platform.admin_dsn, dbname=app_a.database)
    original_role_timeout = _read_role_statement_timeout(platform.admin_dsn, role)
    _set_role_statement_timeout(platform.admin_dsn, role, "5000ms")
    backend = PostgresBackend(
        runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn, max_execution_ms=200,
    )
    lock_conn = None
    lock_conn_guard = threading.Lock()
    released = threading.Event()

    def _force_release_after_timeout() -> None:
        # Safety net, not part of the property under test: `app_a`'s own
        # `platform` fixture never applies migration `0013_role_
        # statement_timeouts.sql` (`test_postgres.py`'s own module
        # docstring), so a mutation that removes `all_field_types`'s own
        # `_set_timeouts` call leaves NO bound at all on this block --
        # without this thread, such a mutation would hang this test
        # forever instead of turning it red. 3s is well above the 200ms
        # bound under test, so this never fires on correct code.
        if not released.wait(timeout=3.0):
            with lock_conn_guard:
                if lock_conn is not None:
                    try:
                        lock_conn.rollback()
                        lock_conn.close()
                    except psycopg.Error:
                        pass

    try:
        lock_conn = psycopg.connect(lock_dsn)
        with lock_conn.cursor() as cur:
            cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier("_mdb_field_types")))

        watchdog = threading.Thread(target=_force_release_after_timeout, daemon=True)
        watchdog.start()
        try:
            started = time.monotonic()
            with pytest.raises(ResourceLimitError) as excinfo:
                scoped(backend).all_field_types()
            elapsed = time.monotonic() - started
        finally:
            released.set()
            watchdog.join(timeout=5)

        assert str(excinfo.value) == "operation exceeds the execution budget"
        assert excinfo.value.details == {"limit_class": "execution_ms"}
        # Sufficiently short of the 5000ms role default (D-5 (2)) that a
        # role-level cancel could not explain it, with generous margin
        # for CI scheduling jitter around the 200ms constructed bound.
        assert elapsed < 2.5, f"elapsed {elapsed}s is not sufficiently shorter than the 5s role default"

        with lock_conn_guard:
            if lock_conn is not None:
                lock_conn.rollback()
                lock_conn.close()
                lock_conn = None

        # Rollback happened on the developer connection -- the next real
        # call over the SAME connection succeeds (still under the
        # constructed 200ms bound, an information-only read with nothing
        # left to block on).
        assert scoped(backend).all_field_types() == {}
    finally:
        released.set()
        with lock_conn_guard:
            if lock_conn is not None:
                try:
                    lock_conn.rollback()
                    lock_conn.close()
                except psycopg.Error:
                    pass
        backend.close()
        _set_role_statement_timeout(platform.admin_dsn, role, original_role_timeout)


def test_build_app_passes_the_declared_execution_ms_to_the_constructed_backend(main_module, platform, probe_app) -> None:
    """D-4/D-5 (5): `main.build_app` wires `config.max_execution_ms`
    (`FoundationConfig.from_env`'s own `MITATEDB_MAX_EXECUTION_MS`) into
    every served application's own `PostgresBackend(...)` construction --
    read back off the constructed cell's own backend attribute, mirroring
    `test_main.py`'s own `MITATEDB_MAX_CONCURRENCY=7` precedent for the
    identical reason (a value distinct from every default in play)."""
    env = _base_env(platform, probe_app)
    env["MITATEDB_MAX_EXECUTION_MS"] = str(_CONSTRUCTED_MS)
    app = main_module.build_app(env)
    inner_app = app.app  # unwrap RequestByteBoundMiddleware -> the wrapped Starlette app
    service = inner_app.state.service
    cell = service._cell_factory(probe_app.app_id)
    assert cell._backend._default_timeout_ms == _CONSTRUCTED_MS
