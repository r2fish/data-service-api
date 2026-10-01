"""Peer-local pins for MitateDB-api's multi-process worker wiring (design
docs/design/MULTI_PROCESS_WORKER_V0_1.md D-1/D-3/D-4): `mitatedb_api.
concurrency_slots` (the host-shared `concurrency` slot directory), the
PostgreSQL-backed `requests_per_minute` rate row (migration `0016`), the
2-strategy `limit_enforcement` mapping helper, the `--workers`/
`MITATEDB_SLOT_DIR` startup validation, the `--preflight` one-shot,
`application_name` tagging, the thread-limit-derived pool dimension, and
the http conformance plug's own instance-scoped wiring.

Reuses `test_postgres.py`'s own real-PostgreSQL `platform`/`provision_app`
(the data plane), `control_plane_harness.py`'s own `control_platform` (the
control plane) and `test_ops_verify_declarations.py`'s own FUNCTION-scoped
`platform` (aliased `verify_platform`) rather than duplicating any
bootstrap -- the same relative-import-for-fixture-reuse pattern
`test_process_ceilings_declaration.py` already uses.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import fcntl
import json
import logging
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from .test_ops_verify_declarations import (  # noqa: F401 (fixture re-export)
    _FakeHeadroomConn,
    _declare_provision_role_as_the_writer as _verify_declare_writer,
    _set_row as _verify_set_row,
    platform as verify_platform,
)
from .test_postgres import _dsn_with, platform, provision_app  # noqa: F401 (fixture, relative import)

import mitatedb_api.http as http_module
from mitatedb_api import concurrency_slots
from mitatedb_api import pool as pool_module
from mitatedb_api.auth import Role
from mitatedb_api.capabilities_document import resolve_limit_enforcement
from mitatedb_api.cell import ApplicationCell, ApplicationRuntime, _LimitStateHolder
from mitatedb_api.config import FoundationConfig, role_pool_size
from mitatedb_api.credential_store_postgres import PostgresCredentialStore
from mitatedb_api.errors import AuthenticationError, FoundationError, StorageConfigurationError
from mitatedb_api.pool import BoundedConnectionPool

_CONFORMANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "conformance")
if _CONFORMANCE_DIR not in sys.path:
    sys.path.insert(0, _CONFORMANCE_DIR)
import conformance_adapter_mitatedb_http as _http_adapter_module  # noqa: E402

RATE_TABLE = "credential_request_rate"
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
_PEPPER = "synthetic-test-pepper-mitatedb-r113-0000"
_CONTROL_PEPPER = "synthetic-test-pepper-mitatedb-r113-ctl-0000"
_PROBE_APP_ID = "r113_probe"

#: every wait below is bounded (a blocked child process, lock, lifespan,
#: or held request never hangs this module).
_WAIT_S = 10.0


def _rate_fn(schema: str) -> "sql.Composed":
    return sql.SQL("SELECT {}(%s, %s)").format(sql.Identifier(schema, "credential_request_rate_admit"))


def _platform_admin_dsn(platform_info: types.SimpleNamespace) -> str:
    """`admin_dsn` pinned to this fixture's own throwaway platform
    database."""
    return _dsn_with(platform_info.admin_dsn, dbname=platform_info.platform_db)


def _write_store(platform_info: types.SimpleNamespace) -> PostgresCredentialStore:
    return PostgresCredentialStore(platform_info.controlplane_dsn, pepper=_PEPPER, schema=platform_info.registry_schema)


def _read_store(platform_info: types.SimpleNamespace, *, max_size: int = 4) -> PostgresCredentialStore:
    return PostgresCredentialStore(
        platform_info.api_dsn, pepper=_PEPPER, schema=platform_info.registry_schema,
        pool=BoundedConnectionPool(platform_info.api_dsn, max_size=max_size),
    )


def _issue(platform_info: types.SimpleNamespace, app_id: str) -> tuple[str, str]:
    """A freshly issued runtime credential -- `(credential_id, bearer)`."""
    return _write_store(platform_info).issue(app_id, Role.RUNTIME)


def _rate_row_count(platform_info: types.SimpleNamespace, credential_id: str) -> int:
    with psycopg.connect(platform_info.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(
                    sql.Identifier(platform_info.registry_schema, RATE_TABLE)
                ),
                [credential_id],
            )
            (count,) = cur.fetchone()
    return count


@pytest.fixture(scope="module")
def r113_app(platform):
    """This module's own dedicated application, never deprovisioned (see
    `test_main.py`'s own module docstring for why a `build_app()`
    composition's persistent connections make that unsafe) -- the module-
    scoped `platform` fixture's own final sweep removes it."""
    return provision_app(platform, _PROBE_APP_ID)


def _main_env(platform_info, app, *, workers: str = "1") -> dict[str, str]:
    """A fresh `mkdtemp` slot directory (mode 0700) per call."""
    return {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_PLATFORM_DSN": platform_info.api_dsn,
        "MITATEDB_PLATFORM_SCHEMA": platform_info.registry_schema,
        "MITATEDB_SERVE_APPS": app.app_id,
        "MITATEDB_WORKERS": workers,
        "MITATEDB_SLOT_DIR": tempfile.mkdtemp(prefix="mitatedb-test-slots-r113-"),
        f"MITATEDB_APP_{app.app_id.upper()}_RUNTIME_DSN": app.runtime_dsn,
        f"MITATEDB_APP_{app.app_id.upper()}_DEVELOPER_DSN": app.developer_dsn,
    }


def _main_module(platform_info, app):
    """Guarded first import of `mitatedb_api.main` (its own module-level
    `app = build_app()` runs once per test process, `test_main.py`'s own
    identical precedent)."""
    if "mitatedb_api.main" not in sys.modules:
        previous = dict(os.environ)
        try:
            os.environ.update(_main_env(platform_info, app))
            import mitatedb_api.main  # noqa: F401
        finally:
            os.environ.clear()
            os.environ.update(previous)
            pool_module.set_connection_application_name(None)
    import mitatedb_api.main as main_module
    return main_module


def _close_built_app(main_module, app) -> None:
    """Closes every connection a `build_app()` result holds, through the
    same lifespan-shutdown path `--preflight` uses, then clears the
    process-wide `application_name` the build set."""
    try:
        asyncio.run(asyncio.wait_for(main_module._run_lifespan_once(app), timeout=_WAIT_S))
    finally:
        pool_module.set_connection_application_name(None)


def _set_process_ceilings(platform_info, value: dict) -> None:
    with psycopg.connect(platform_info.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform_info.registry_schema, "platform_declarations")),
                [json.dumps(value)],
            )
        conn.commit()


def _delete_process_ceilings(platform_info) -> None:
    with psycopg.connect(platform_info.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE key = 'process_ceilings'").format(
                    sql.Identifier(platform_info.registry_schema, "platform_declarations")
                ),
            )
        conn.commit()


def _run_preflight_subprocess(module: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith(("R2DB_", "MITATEDB_"))}
    full_env.update(env)
    existing = full_env.get("PYTHONPATH")
    full_env["PYTHONPATH"] = str(_SRC_DIR) if not existing else f"{_SRC_DIR}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-m", module, "--preflight"], capture_output=True, text=True, env=full_env, timeout=60,
    )


# ===========================================================================
# completion conditions 83-85, 140: migration 0016
# ===========================================================================


def test_0016_rate_row_cascades_on_credential_delete(platform, r113_app) -> None:
    """Completion condition 83 -- mutation M83 (drop `ON DELETE CASCADE`):
    a rate row admitted for a credential is gone once that credential is
    deleted."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    with psycopg.connect(platform.api_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.registry_schema), [credential_id, 100])
            (admitted,) = cur.fetchone()
    assert admitted is True
    assert _rate_row_count(platform, credential_id) == 1  # non-空振り: the row exists before the delete
    with psycopg.connect(platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE credential_id = %s").format(
                    sql.Identifier(platform.registry_schema, "credentials")
                ),
                [credential_id],
            )
        conn.commit()
    assert _rate_row_count(platform, credential_id) == 0


def test_0016_api_role_has_select_insert_update_only_no_delete_or_truncate(platform, r113_app, control_platform) -> None:
    """Completion condition 84 -- mutation M84 (grant DELETE to the api
    role): `<prefix>svc_api` holds exactly SELECT/INSERT/UPDATE on the
    rate table, never DELETE/TRUNCATE, and every other role -- the
    controlplane role, a provisioned application's own runtime and
    developer roles, and (on `control_platform`, the fixture that
    applies `0005`) the auditreader role -- holds nothing on it."""
    all_privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")

    def _held(dsn: str, schema: str, role: str) -> list[str]:
        table = f"{schema}.{RATE_TABLE}"
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                held = []
                for privilege in all_privileges:
                    cur.execute("SELECT has_table_privilege(%s, %s, %s)", [role, table, privilege])
                    if cur.fetchone()[0]:
                        held.append(privilege)
        return held

    assert _held(_platform_admin_dsn(platform), platform.registry_schema, platform.api_role) == [
        "SELECT", "INSERT", "UPDATE",
    ]
    others = [
        (_platform_admin_dsn(platform), platform.registry_schema, platform.controlplane_role),
        (_platform_admin_dsn(platform), platform.registry_schema, r113_app.runtime_role),
        (_platform_admin_dsn(platform), platform.registry_schema, r113_app.developer_role),
        (control_platform.provision_dsn, control_platform.registry_schema, f"{control_platform.prefix}svc_auditreader"),
    ]
    for dsn, schema, role in others:
        assert _held(dsn, schema, role) == [], role
    assert len(others) == 4


def test_ops_accepts_0016_as_a_known_platform_migration() -> None:
    """Completion condition 85 -- mutation M85 (drop 0016 from `ops.py`'s
    accepted list)."""
    import mitatedb_api.ops as ops

    assert "0016_credential_request_rate.sql" in ops._PLATFORM_MIGRATION_FILENAMES
    assert ops._PLATFORM_MIGRATION_VARIABLE_TABLE["0016_credential_request_rate.sql"] == ()


def test_0016_is_a_platform_single_shot_migration_never_an_upgrade_script() -> None:
    """Completion condition 140 -- mutation M140 (the accepted 0016 name
    ends in `_upgrade.sql`): the 0016 file `apply-platform-migration`
    accepts exists, does not end in `_upgrade.sql`, and is not one of the
    per-application upgrade numbers the upgrade ledger tracks."""
    import mitatedb_api.ops as ops
    from mitatedb_api import platform_upgrades

    names = [name for name in ops._PLATFORM_MIGRATION_FILENAMES if name.startswith("0016_")]
    assert names, "no 0016 platform migration accepted (空振り)"
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    upgrade_numbers = set(platform_upgrades.PLATFORM_UPGRADE_NUMBERS)
    for name in names:
        assert not name.endswith("_upgrade.sql"), name
        assert (migrations_dir / name).is_file(), name
        assert int(name[:4]) not in upgrade_numbers, name


# ===========================================================================
# completion conditions 86-95: the rate statement
# ===========================================================================


def test_pg_rate_admits_up_to_limit_then_denies(platform, r113_app) -> None:
    """Completion condition 86 -- mutation M86 (the admit test becomes
    "total <= L"): with the PostgreSQL rate wired into `_LimitStateHolder`,
    exactly L admissions succeed for one credential and the L+1th raises
    the SAME `ResourceLimitError` (message and `details`) the in-memory
    window raises for its own L+1th request."""
    from mitatedb_api.errors import ResourceLimitError

    credential_id, _bearer = _issue(platform, r113_app.app_id)
    limit = 3
    store = _read_store(platform)
    try:
        wired = _LimitStateHolder(rate=store)
        for _ in range(limit):
            wired.acquire_rate(credential_id, limit)
        with pytest.raises(ResourceLimitError) as wired_denial:
            wired.acquire_rate(credential_id, limit)
    finally:
        store.close()
    in_memory = _LimitStateHolder()
    for _ in range(limit):
        in_memory.acquire_rate(credential_id, limit)
    with pytest.raises(ResourceLimitError) as in_memory_denial:
        in_memory.acquire_rate(credential_id, limit)
    assert wired_denial.value.details == {"limit_class": "requests_per_minute"}
    assert (str(wired_denial.value), wired_denial.value.details) == (
        str(in_memory_denial.value), in_memory_denial.value.details,
    )
    _base_s, counts = _read_rate_row(platform, credential_id)
    assert sum(counts) == limit


def test_pg_rate_db_failure_maps_to_503(platform, r113_app, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 92 -- mutation M92 (a DB failure is passed
    through as an admission): a PostgreSQL failure during the rate
    statement raises the store's own existing fail-closed exception,
    which this peer's HTTP layer maps to 503."""
    from mitatedb_api import credential_store_postgres

    credential_id, _bearer = _issue(platform, r113_app.app_id)
    store = _read_store(platform)
    try:
        def _boom(cur, statement, params=()):
            raise psycopg.errors.QueryCanceled("synthetic failure for M92")

        monkeypatch.setattr(credential_store_postgres, "_execute", _boom)
        with pytest.raises(FoundationError) as excinfo:
            store.record_rate_and_check(credential_id, 100)
        assert http_module._STATUS_BY_CODE[http_module._classify(excinfo.value)] == 503
    finally:
        store.close()


def test_pg_rate_concurrent_first_admissions_for_a_new_credential_never_race(platform, r113_app) -> None:
    """Completion condition 87 (audit companion) -- mutation M87b (0016's
    first admission falls back to a plain `IF NOT FOUND THEN INSERT`): a
    brand-new credential admits deterministically when its FIRST two
    admissions race -- one connection holds its own INSERT open, a second
    connection's call for the SAME credential waits behind it instead of
    racing a duplicate INSERT into a unique-key failure. The first caller
    commits only once `pg_stat_activity` shows the second caller's backend
    waiting on a lock (bounded), so the two calls always overlap."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    conn_a = psycopg.connect(platform.api_dsn)
    conn_a.autocommit = False
    ready = threading.Event()
    hold_release = threading.Event()
    b_connected = threading.Event()
    b_pid: list[int] = []
    result_b: list[object] = []

    def _first_caller() -> None:
        with conn_a.cursor() as cur:
            cur.execute(_rate_fn(platform.registry_schema), [credential_id, 100])
            cur.fetchone()
        ready.set()
        hold_release.wait(timeout=_WAIT_S)
        conn_a.commit()

    def _second_caller() -> None:
        ready.wait(timeout=_WAIT_S)
        try:
            with psycopg.connect(platform.api_dsn, autocommit=True) as conn_b:
                b_pid.append(conn_b.info.backend_pid)
                b_connected.set()
                with conn_b.cursor() as cur:
                    cur.execute(_rate_fn(platform.registry_schema), [credential_id, 100])
                    (admitted,) = cur.fetchone()
            result_b.append(admitted)
        except Exception as exc:  # collected for the assertion below
            result_b.append(exc)

    t1 = threading.Thread(target=_first_caller)
    t2 = threading.Thread(target=_second_caller)
    t1.start()
    assert ready.wait(timeout=_WAIT_S), "the first caller never reached its own uncommitted INSERT"
    t2.start()
    try:
        assert b_connected.wait(timeout=_WAIT_S), "the second caller never connected"
        assert _wait_until_backend_waits_on_a_lock(_platform_admin_dsn(platform), b_pid[0], _WAIT_S), (
            "the second caller never waited on the first caller's uncommitted row"
        )
    finally:
        hold_release.set()
    t1.join(timeout=_WAIT_S)
    t2.join(timeout=_WAIT_S)
    conn_a.close()
    assert result_b, "the second admission's own thread never returned (空振り)"
    assert result_b[0] is True, f"the second concurrent first admission must be admitted: {result_b[0]!r}"
    _base_after, counts_after = _read_rate_row(platform, credential_id)
    assert sum(counts_after) == 2


def _wait_until_backend_waits_on_a_lock(dsn: str, pid: int, timeout_s: float) -> bool:
    """True once `pg_stat_activity` shows backend `pid` waiting on a
    lock (`wait_event_type = 'Lock'`), False if `timeout_s` passes
    first -- a bounded wait on the observed state, never a fixed pause."""
    deadline = time.monotonic() + timeout_s
    with psycopg.connect(dsn, autocommit=True) as observer:
        while time.monotonic() < deadline:
            row = observer.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid]).fetchone()
            if row is not None and row[0] == "Lock":
                return True
            time.sleep(0.01)
    return False


def test_rate_call_is_lexically_outside_every_with_block_in_the_limit_gate() -> None:
    """Completion condition 93 (AST pin) -- mutation M93 (the rate call
    moves inside a `with` block): `ApplicationCell._limit_gate`'s own
    `acquire_rate(...)` call is a direct statement of that method's body,
    never nested inside a `with` -- the authentication borrow
    (`_require_data`'s own `assert_active`) has already returned its
    connection before the gate runs, and the rate borrow never overlaps
    another borrow held open by the gate."""
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(ApplicationCell._limit_gate))
    method = ast.parse(source).body[0]
    assert isinstance(method, ast.FunctionDef)
    statements = [
        stmt for stmt in method.body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "acquire_rate"
    ]
    assert statements, "no acquire_rate(...) call found in _limit_gate (空振り)"
    for stmt in statements:
        assert not isinstance(stmt, ast.With), ast.dump(stmt)


def test_record_rate_and_check_borrows_and_executes_exactly_once() -> None:
    """Completion condition 93 (second half, AST pin) -- mutation M93b (a
    second `_execute` in the same borrow): `record_rate_and_check` borrows
    through `self._borrow_connection()` exactly once and runs `_execute`
    exactly once -- one round trip per call."""
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(PostgresCredentialStore.record_rate_and_check))
    method = ast.parse(source).body[0]
    borrows = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_borrow_connection"
    ]
    executes = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_execute"
    ]
    assert len(borrows) == 1, len(borrows)
    assert len(executes) == 1, len(executes)


def test_denied_authentication_never_writes_a_rate_row(platform, r113_app) -> None:
    """Completion condition 94 -- mutation M94 (`HttpService.authenticate`
    counts the rate before the credential store authenticates): a bearer
    naming a real, registered credential with the wrong secret is refused
    with `AuthenticationError` and leaves no rate row for that credential.
    Non-空振り: the SAME credential presented with its real secret, through
    the SAME service, does get its row once it reaches a cell operation.

    The store's platform pool holds ONE connection, so the authentication
    borrow and the rate borrow can only ever run one after the other: a
    rate call made inside the authentication borrow waits out the pool's
    own acquire timeout and fails instead of being admitted (mutation
    M93c, on the sibling test below)."""
    from mitatedb_api.credential_wire import compose_bearer_locator
    from mitatedb_api.http import HttpService

    store = _read_store(platform, max_size=1)
    try:
        holder = _LimitStateHolder(rate=store)

        def _cell_factory(application_id: str) -> ApplicationCell:
            return ApplicationCell(application_id, FoundationConfig(), guard=store.assert_active, limit_holder=holder)

        service = HttpService(store, _cell_factory, limit_holder=holder, max_concurrency=FoundationConfig().max_concurrency)
        credential_id, bearer = _issue(platform, r113_app.app_id)
        wrong = compose_bearer_locator(credential_id, "wrong" + secrets.token_hex(16))
        with pytest.raises(AuthenticationError):
            service.authenticate(wrong)
        assert _rate_row_count(platform, credential_id) == 0

        service.authenticate(bearer).capabilities()
        assert _rate_row_count(platform, credential_id) == 1
    finally:
        store.close()


def test_denied_session_recheck_of_a_revoked_credential_never_writes_a_rate_row(platform, r113_app) -> None:
    """Completion condition 94 -- mutation M94b (the rate is counted before
    the session re-check): a real, registered credential authenticated
    once and then revoked is refused by `_require_data`'s own
    `assert_active` re-check before `_limit_gate` is ever reached, so no
    rate row is written for it. Non-空振り: a sibling credential of the
    SAME application, never revoked, does get its row through the same
    cell.

    Mutation M93c (`assert_active` counts the rate inside its own
    `_borrow_connection()` block): the store's platform pool holds ONE
    connection, so the nested rate borrow waits out the pool's acquire
    timeout and the re-check fails with `AuthorizationStateUnavailable`
    (503) instead of `AuthenticationError` -- the borrows nest, and the
    request is not served. With a larger pool the nested borrow would
    succeed and only the lexical pin above would see it."""
    store = _read_store(platform, max_size=1)
    try:
        holder = _LimitStateHolder(rate=store)
        cell = ApplicationCell(r113_app.app_id, FoundationConfig(), guard=store.assert_active, limit_holder=holder)
        revoked_id, revoked_bearer = _issue(platform, r113_app.app_id)
        principal = store.authenticate(revoked_bearer)
        _write_store(platform).revoke(revoked_id)
        with pytest.raises(AuthenticationError):
            ApplicationRuntime(cell, principal).capabilities()
        assert _rate_row_count(platform, revoked_id) == 0

        sibling_id, sibling_bearer = _issue(platform, r113_app.app_id)
        ApplicationRuntime(cell, store.authenticate(sibling_bearer)).capabilities()
        assert _rate_row_count(platform, sibling_id) == 1
    finally:
        store.close()


def _read_db_now_s(platform_info) -> int:
    with psycopg.connect(platform_info.api_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
            (now_s,) = cur.fetchone()
    return int(now_s)


def _read_rate_row(platform_info, credential_id: str) -> tuple[int, list[int]]:
    with psycopg.connect(platform_info.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT base_s, counts FROM {} WHERE credential_id = %s").format(
                    sql.Identifier(platform_info.registry_schema, RATE_TABLE)
                ),
                [credential_id],
            )
            row = cur.fetchone()
    assert row is not None
    return row[0], list(row[1])


def _prime_and_ring_length(platform_info, credential_id: str) -> int:
    """Creates the row through the admission function itself (never a raw
    INSERT that assumes a ring length) and returns the row's current ring
    length, read back."""
    with psycopg.connect(platform_info.api_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform_info.registry_schema), [credential_id, 2_000_000_000])
    _base_s, counts = _read_rate_row(platform_info, credential_id)
    return len(counts)


def _write_rate_row(platform_info, credential_id: str, *, base_s: int, counts: list[int]) -> None:
    with psycopg.connect(platform_info.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET base_s = %s, counts = %s WHERE credential_id = %s").format(
                    sql.Identifier(platform_info.registry_schema, RATE_TABLE)
                ),
                [base_s, counts, credential_id],
            )
        conn.commit()


def _reset_rate_row(platform_info, credential_id: str, *, base_s: int, at: dict[int, int] | None = None, fill: int = 0) -> int:
    n = _prime_and_ring_length(platform_info, credential_id)
    counts = [fill] * n
    for offset, value in (at or {}).items():
        counts[offset % n] = value
    _write_rate_row(platform_info, credential_id, base_s=base_s, counts=counts)
    return n


def _admit(platform_info, credential_id: str, limit: int) -> bool:
    with psycopg.connect(platform_info.api_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform_info.registry_schema), [credential_id, limit])
            (admitted,) = cur.fetchone()
    return admitted


def test_rate_ring_base_s_never_rewinds_after_a_lock_wait(platform, r113_app) -> None:
    """Completion condition 88 -- mutation M88 (drop `GREATEST`): a row
    whose `base_s` is already at a NEWER second than the call's own clock
    read never rewinds, and the total admitted stays within the limit."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    newer_base = int(time.time()) + 5
    _reset_rate_row(platform, credential_id, base_s=newer_base, at={newer_base: 1})
    assert _admit(platform, credential_id, 2) is True
    base_after, counts_after = _read_rate_row(platform, credential_id)
    assert base_after == newer_base
    assert sum(counts_after) == 2


def test_rate_ring_stale_base_s_beyond_61_seconds_resets_from_zero(platform, r113_app) -> None:
    """Completion condition 89 -- mutation M89 (the `shift >= 61` branch
    becomes a no-op): a row whose `base_s` is 61+ seconds stale is treated
    as fully expired."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    _reset_rate_row(platform, credential_id, base_s=int(time.time()) - 120, fill=61)
    assert _admit(platform, credential_id, 5) is True
    _base_after, counts_after = _read_rate_row(platform, credential_id)
    assert sum(counts_after) == 1


def test_rate_ring_full_count_60_seconds_ago_still_denies(platform, r113_app) -> None:
    """Completion condition 90 (`int[61]`) -- mutation M90 (every `61` in
    0016 becomes `60`): a row with the limit already reached exactly 60
    seconds before the call's own DB second still denies. Anchored to the
    DB's own clock and redone (at most 3 times) when setup and call span
    two DB seconds."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    admitted = None
    for _attempt in range(3):
        db_now_s = _read_db_now_s(platform)
        old_base = db_now_s - 60
        _reset_rate_row(platform, credential_id, base_s=old_base, at={old_base: 5})
        admitted = _admit(platform, credential_id, 5)
        if _read_db_now_s(platform) == db_now_s:
            break
    else:
        pytest.fail("the setup and call never landed within one DB second after 3 attempts")
    assert admitted is False


def test_rate_ring_shift_zeroes_only_the_shifted_range(platform, r113_app) -> None:
    """Completion condition 91 (the ring) -- mutation M91 (the zeroed range
    starts at `base_s` instead of `base_s + 1`): with `base_s` moved `k`
    seconds forward, exactly positions `(base_s+1 .. base_s+k) mod n` are
    zeroed and every other position survives."""
    credential_id, _bearer = _issue(platform, r113_app.app_id)
    k = 5
    for _attempt in range(3):
        db_now_s = _read_db_now_s(platform)
        old_base = db_now_s - k
        n = _prime_and_ring_length(platform, credential_id)
        counts = [i + 1 for i in range(n)]
        _write_rate_row(platform, credential_id, base_s=old_base, counts=counts)
        admitted = _admit(platform, credential_id, 10_000)
        base_after, counts_after = _read_rate_row(platform, credential_id)
        if _read_db_now_s(platform) == db_now_s:
            break
    else:
        pytest.fail("the setup and call never landed within one DB second after 3 attempts")
    assert admitted is True
    expected_zeroed = {(old_base + i) % n for i in range(1, k + 1)}
    incremented_idx = base_after % n
    for idx in range(n):
        if idx == incremented_idx:
            continue
        if idx in expected_zeroed:
            assert counts_after[idx] == 0, idx
        else:
            assert counts_after[idx] == counts[idx], idx
    incremented_base = 0 if incremented_idx in expected_zeroed else counts[incremented_idx]
    assert counts_after[incremented_idx] == incremented_base + 1


# ===========================================================================
# completion conditions 96-112, 114b: `mitatedb_api.concurrency_slots`
# ===========================================================================


def _slot_dir(tmp_path: Path) -> Path:
    target = tmp_path / "slots"
    target.mkdir(mode=0o700)
    os.chmod(target, 0o700)
    return target


def test_slot_dir_env_missing_raises_naming_the_variable(platform, r113_app) -> None:
    """Completion condition 96 -- mutation M96 (unset falls back to a
    default path)."""
    main_module = _main_module(platform, r113_app)
    for env in ({}, {"MITATEDB_SLOT_DIR": ""}):
        with pytest.raises(RuntimeError, match="MITATEDB_SLOT_DIR"):
            main_module._require_slot_dir(env, "MITATEDB_SLOT_DIR")


def test_slot_dir_missing_path_raises(tmp_path: Path) -> None:
    """Completion condition 97 -- mutation M97 (the check creates the
    directory): a slot directory that does not exist fails the check and
    is never created."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(concurrency_slots.SlotDirectoryError):
        concurrency_slots.check_slot_directory(missing)
    assert not missing.exists()


def test_slot_dir_wrong_owner_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 98 -- mutation M98 (drop the owner check)."""
    target = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots.os, "geteuid", lambda: target.stat().st_uid + 1)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="uid"):
        concurrency_slots.check_slot_directory(target)


def test_slot_dir_wrong_mode_raises(tmp_path: Path) -> None:
    """Completion condition 99 -- mutation M99 (drop the mode check)."""
    target = tmp_path / "slots"
    target.mkdir(mode=0o755)
    os.chmod(target, 0o755)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="0700|mode"):
        concurrency_slots.check_slot_directory(target)


def test_slot_file_symlink_open_fails(tmp_path: Path) -> None:
    """Completion condition 100 -- mutation M100 (drop `O_NOFOLLOW`)."""
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("")
    slot_dir = _slot_dir(tmp_path)
    (slot_dir / "slot-0").symlink_to(real_target)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError):
        with slots.acquire(1):
            pass


def test_slot_file_created_with_mode_0600(tmp_path: Path) -> None:
    """Completion condition 101 -- mutation M101 (create with mode 0644)."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with slots.acquire(1):
        mode = stat.S_IMODE((slot_dir / "slot-0").stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_slot_fd_is_close_on_exec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 102 -- mutation M102 (drop `O_CLOEXEC`) -- and
    ruling 43 (s2c) -- mutation Ms2c (drop `O_CLOEXEC` from the `scan`
    open only): the REAL fds `acquire()` opens for `slot-0` AND for `scan`
    both carry `O_CLOEXEC` (`os.open` is spied on, never replaced); both
    opens must be observed."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    captured_flags: dict[str, list[int]] = {"slot-0": [], concurrency_slots.SCAN_FILENAME: []}
    original_open = os.open

    def _spy_open(path, flags, mode=0o777):
        name = os.path.basename(path)
        if name in captured_flags:
            captured_flags[name].append(flags)
        return original_open(path, flags, mode)

    monkeypatch.setattr(concurrency_slots.os, "open", _spy_open)
    with slots.acquire(1):
        pass
    for name, flags_seen in captured_flags.items():
        assert flags_seen, f"no os.open call of {name} observed (空振り)"
        assert flags_seen[0] & os.O_CLOEXEC, (name, oct(flags_seen[0]))


def test_flock_unexpected_errno_maps_to_backend_error_not_admitted_or_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 103 -- mutation M103 (every errno reads as
    "held"): the `slot-0` lock returns `EPERM` (injected; the `scan` lock
    runs for real) -- `SlotBackendError` naming the slot file."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    real_flock = fcntl.flock
    slot_attempts: list[int] = []

    def _fake_flock(fd, op):
        slot_path = slot_dir / "slot-0"
        if op & fcntl.LOCK_NB and slot_path.exists() and os.fstat(fd).st_ino == os.stat(slot_path).st_ino:
            slot_attempts.append(op)
            raise OSError(errno.EPERM, "synthetic EPERM for M103")
        return real_flock(fd, op)

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _fake_flock)
    with pytest.raises(concurrency_slots.SlotBackendError, match="slot file"):
        with slots.acquire(1):
            pass
    assert slot_attempts, "no slot-0 lock attempt observed (空振り)"


def test_slot_backend_error_maps_to_503_through_the_limit_state_holder() -> None:
    """Completion condition 103 (through `cell.py`) -- mutation M103b
    (`acquire_concurrency_slot` drops its `SlotBackendError` mapping): a slot
    backend failure reaches `StorageConfigurationError` -- this peer's
    503 `SERVICE_UNAVAILABLE` -- through BOTH `acquire_concurrency_slot`
    (pre-authentication) and `concurrency_slot` (post-authentication,
    never reserved), never `LIMIT_EXCEEDED` and never an admission."""
    class _BackendErrorSlots:
        @contextlib.contextmanager
        def acquire(self, limit: int):
            raise concurrency_slots.SlotBackendError("synthetic backend failure")
            yield  # pragma: no cover

    holder = _LimitStateHolder(concurrency_slots=_BackendErrorSlots(), concurrency_configured=True)
    outcomes = []
    for entry in (holder.acquire_concurrency_slot, holder.concurrency_slot):
        with pytest.raises(StorageConfigurationError) as excinfo:
            with entry(1):
                pass  # pragma: no cover
        outcomes.append(http_module._STATUS_BY_CODE[http_module._classify(excinfo.value)])
    assert outcomes == [503, 503], outcomes


def test_slot_backend_failure_is_logged_as_a_warning_at_both_503_mapping_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """Ruling 43 (s9) -- mutations Ms9a (`acquire_concurrency_slot` does
    not call the log writer) and Ms9s (`concurrency_slot` does not call
    it): another holder keeps `scan` past its deadline (0.2 s here). Each
    of `_LimitStateHolder`'s two mapping points -- `acquire_concurrency_
    slot` (before authentication) and `concurrency_slot` (after it, never
    reserved) -- raises its unchanged `StorageConfigurationError` (this
    peer's 503) and writes exactly one WARNING line to the
    `mitatedb_api.cell` logger through the module's one
    `BackendFailureLog` (its clock replaced and moved on by one interval
    between the two points): the fixed prefix, the `SlotBackendError`
    message naming the expired `scan` deadline, and a count of 0. Before
    the replacement, the production instance's own clock is the real
    `time.monotonic` (mutation Ms9m: a `time.time` default leaves this
    assertion alone). Calling the post-auth mapping point again with the
    clock unmoved writes no further line, because the two mapping points
    share the ONE module-level instance (mutation Ms9sh: the post-auth
    point writing through a fresh instance of its own would not share
    that suppression); the failure it did not log there surfaces with a
    count of 1 once the pre-auth mapping point is called a further
    interval later."""
    from mitatedb_api import cell as cell_module

    prefix = "mitatedb_api: concurrency slot backend failed, answering SERVICE_UNAVAILABLE"
    assert cell_module._SLOT_FAILURE_LOG_PREFIX == prefix
    writer = cell_module._SLOT_FAILURE_LOG
    assert isinstance(writer, concurrency_slots.BackendFailureLog)
    assert writer._clock is time.monotonic  # noqa: SLF001
    clock = [1000.0]
    monkeypatch.setattr(writer, "_clock", lambda: clock[0])
    monkeypatch.setattr(writer, "_last_line_at", None)
    monkeypatch.setattr(writer, "_not_logged", 0)
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.2)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    holder = _LimitStateHolder(concurrency_slots=slots, concurrency_configured=True)

    def _through(entry):
        def _call() -> str:
            with entry(1):
                return "admitted"
        return _call

    caplog.set_level(logging.WARNING, logger="mitatedb_api.cell")
    holder_fd = _hold_scan_directly(slot_dir)
    threads: list[threading.Thread] = []
    results: dict[str, tuple] = {}
    try:
        finished, direct, elapsed, thread = _call_bounded(lambda: _acquire_one(slots), 5.0)
        threads.append(thread)
        assert finished, f"acquire() had not returned after {elapsed:.2f}s with scan held"
        mapping_points = (("acquire_concurrency_slot", holder.acquire_concurrency_slot), ("concurrency_slot", holder.concurrency_slot))
        for index, (label, entry) in enumerate(mapping_points):
            caplog.clear()
            finished, outcome, elapsed, thread = _call_bounded(_through(entry), 5.0)
            threads.append(thread)
            assert finished, f"{label} had not returned after {elapsed:.2f}s with scan held"
            results[label] = (outcome, [r for r in caplog.records if r.name == "mitatedb_api.cell"])
            if index + 1 < len(mapping_points):
                clock[0] += concurrency_slots._FAILURE_LOG_INTERVAL_S
        # the same instance backs both mapping points: calling the post-auth
        # one again with the clock unmoved falls inside the interval its own
        # previous call just started, so it writes no line of its own.
        caplog.clear()
        finished, repeat_outcome, elapsed, thread = _call_bounded(_through(holder.concurrency_slot), 5.0)
        threads.append(thread)
        assert finished, f"concurrency_slot had not returned after {elapsed:.2f}s with scan held (repeat)"
        repeat_records = [r for r in caplog.records if r.name == "mitatedb_api.cell"]
        clock[0] += concurrency_slots._FAILURE_LOG_INTERVAL_S
        caplog.clear()
        finished, pre_auth_repeat, elapsed, thread = _call_bounded(_through(holder.acquire_concurrency_slot), 5.0)
        threads.append(thread)
        assert finished, f"acquire_concurrency_slot had not returned after {elapsed:.2f}s with scan held (repeat)"
        pre_auth_repeat_records = [r for r in caplog.records if r.name == "mitatedb_api.cell"]
    finally:
        os.close(holder_fd)
        for thread in threads:
            thread.join(timeout=_WAIT_S)
    assert direct[0] == "raised" and isinstance(direct[1], concurrency_slots.SlotBackendError), direct
    backend_message = str(direct[1])
    assert "scan" in backend_message and "deadline" in backend_message, backend_message
    expected_line = f"{prefix}: {backend_message} (0 more failures not logged since the previous line)"
    assert list(results) == ["acquire_concurrency_slot", "concurrency_slot"], results
    for label, (outcome, records) in results.items():
        assert outcome[0] == "raised" and isinstance(outcome[1], StorageConfigurationError), (label, outcome)
        assert str(outcome[1]) == "the concurrency slot directory could not be used", (label, outcome[1])
        assert http_module._STATUS_BY_CODE[http_module._classify(outcome[1])] == 503, label
        assert [(r.levelno, r.getMessage()) for r in records] == [(logging.WARNING, expected_line)], (label, records)
    assert repeat_records == [], repeat_records
    assert repeat_outcome[0] == "raised" and isinstance(repeat_outcome[1], StorageConfigurationError), repeat_outcome
    assert pre_auth_repeat[0] == "raised" and isinstance(pre_auth_repeat[1], StorageConfigurationError), pre_auth_repeat
    suppressed_line = f"{prefix}: {backend_message} (1 more failures not logged since the previous line)"
    assert [(r.levelno, r.getMessage()) for r in pre_auth_repeat_records] == [
        (logging.WARNING, suppressed_line),
    ], pre_auth_repeat_records


def _failure_log_lines(caplog: pytest.LogCaptureFixture, logger_name: str) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == logger_name]


def test_backend_failure_log_writes_at_most_one_line_per_interval(caplog: pytest.LogCaptureFixture) -> None:
    """Ruling 43 (s9) -- mutation Ms9i (the interval bound
    dropped): three failures noted within one `_FAILURE_LOG_INTERVAL_S`
    (1 s) on the replaced clock write one WARNING line -- the fixed
    prefix, the first failure's message, and a count of 0 -- and the
    clock moving on with no further failure writes nothing."""
    assert concurrency_slots._FAILURE_LOG_INTERVAL_S == 1.0
    logger_name = "mitatedb_api.test_backend_failure_log"
    clock = [1000.0]
    writer = concurrency_slots.BackendFailureLog(logging.getLogger(logger_name), "fixed prefix", clock=lambda: clock[0])
    caplog.set_level(logging.WARNING, logger=logger_name)
    for offset, text in ((0.0, "first failure"), (0.5, "second failure"), (0.999, "third failure")):
        clock[0] = 1000.0 + offset
        writer.note(concurrency_slots.SlotBackendError(text))
    clock[0] = 1005.0
    assert _failure_log_lines(caplog, logger_name) == [
        (logging.WARNING, "fixed prefix: first failure (0 more failures not logged since the previous line)"),
    ]


def test_backend_failure_log_counts_the_failures_it_did_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """Ruling 43 (s9) -- mutation Ms9c (the failures not logged
    are not counted): on the replaced clock, the first failure writes a
    line; the three noted within the next second write none and are
    counted; the first failure at or after one interval writes a line
    with its own message and that count (3); one more inside the
    interval and one after it give a count of 1."""
    logger_name = "mitatedb_api.test_backend_failure_log"
    clock = [1000.0]
    writer = concurrency_slots.BackendFailureLog(logging.getLogger(logger_name), "fixed prefix", clock=lambda: clock[0])
    caplog.set_level(logging.WARNING, logger=logger_name)
    for now, text in (
        (1000.0, "a"), (1000.2, "b"), (1000.4, "c"), (1000.6, "d"),
        (1001.0, "e"), (1001.5, "f"),
        (1002.0, "g"),
    ):
        clock[0] = now
        writer.note(concurrency_slots.SlotBackendError(text))
    suffix = "more failures not logged since the previous line"
    assert _failure_log_lines(caplog, logger_name) == [
        (logging.WARNING, f"fixed prefix: a (0 {suffix})"),
        (logging.WARNING, f"fixed prefix: e (3 {suffix})"),
        (logging.WARNING, f"fixed prefix: g (1 {suffix})"),
    ]


def test_backend_failure_log_from_two_threads_writes_one_line_and_keeps_the_count(caplog: pytest.LogCaptureFixture) -> None:
    """Ruling 43 (s9) -- mutation Ms9l (the lock dropped): the
    first `note` stops inside the replaced clock (bounded, 1 s) and a
    second `note` starts on another thread meanwhile; the second does
    not read the clock until the first has decided (the lock), so one
    line is written, and the second failure is counted in the next line
    (1)."""
    logger_name = "mitatedb_api.test_backend_failure_log"
    now = [1000.0]
    guard = threading.Lock()
    inside = [0]
    first_inside = threading.Event()
    overlap = threading.Event()

    def _clock() -> float:
        with guard:
            inside[0] += 1
            if inside[0] > 1:
                overlap.set()
            first = not first_inside.is_set()
            if first:
                first_inside.set()
        if first:
            overlap.wait(timeout=1.0)
        with guard:
            inside[0] -= 1
        return now[0]

    writer = concurrency_slots.BackendFailureLog(logging.getLogger(logger_name), "fixed prefix", clock=_clock)
    caplog.set_level(logging.WARNING, logger=logger_name)
    first = threading.Thread(target=writer.note, args=(concurrency_slots.SlotBackendError("thread one"),), daemon=True)
    first.start()
    assert first_inside.wait(timeout=_WAIT_S), "the first note never read the clock (空振り)"
    second = threading.Thread(target=writer.note, args=(concurrency_slots.SlotBackendError("thread two"),), daemon=True)
    second.start()
    first.join(timeout=_WAIT_S)
    second.join(timeout=_WAIT_S)
    assert not first.is_alive() and not second.is_alive(), "a note had not returned"
    assert not overlap.is_set(), "a second note read the clock while the first one was still deciding"
    now[0] = 1001.0
    writer.note(concurrency_slots.SlotBackendError("after the interval"))
    suffix = "more failures not logged since the previous line"
    assert _failure_log_lines(caplog, logger_name) == [
        (logging.WARNING, f"fixed prefix: thread one (0 {suffix})"),
        (logging.WARNING, f"fixed prefix: after the interval (1 {suffix})"),
    ]


def test_selfcheck_detects_a_faked_flock_that_never_excludes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 104 -- mutation M104 (drop the self-check)."""
    slot_dir = _slot_dir(tmp_path)
    real_flock = concurrency_slots.fcntl.flock
    calls = {"n": 0}

    def _fake_flock(fd, op):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_flock(fd, op)
        return None

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _fake_flock)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="NOT rejected"):
        concurrency_slots.selfcheck_slot_locking(slot_dir)


def test_selfcheck_uses_the_dedicated_selfcheck_file_never_slot_0(tmp_path: Path) -> None:
    """Completion condition 105 -- mutation M105 (the self-check uses
    `slot-0`)."""
    slot_dir = _slot_dir(tmp_path)
    concurrency_slots.selfcheck_slot_locking(slot_dir)
    assert not (slot_dir / "slot-0").exists()
    assert (slot_dir / concurrency_slots.SELFCHECK_FILENAME).exists()


def test_two_threads_l_c_1_second_is_refused(tmp_path: Path) -> None:
    """Completion condition 106 -- mutation M106 (share one fd per slot
    within the process): two threads of the SAME process, `limit=1` --
    the second is refused while the first holds."""
    slots = concurrency_slots.HostSharedConcurrencySlots(_slot_dir(tmp_path))
    first_holds = threading.Event()
    release = threading.Event()
    second_outcome: list[bool] = []

    def _holder() -> None:
        with slots.acquire(1):
            first_holds.set()
            release.wait(timeout=_WAIT_S)

    def _second() -> None:
        first_holds.wait(timeout=_WAIT_S)
        try:
            with slots.acquire(1):
                second_outcome.append(True)
        except concurrency_slots.LimitExceeded:
            second_outcome.append(False)

    t1 = threading.Thread(target=_holder)
    t2 = threading.Thread(target=_second)
    t1.start()
    t2.start()
    t2.join(timeout=_WAIT_S)
    release.set()
    t1.join(timeout=_WAIT_S)
    assert second_outcome == [False], second_outcome


def test_slot_released_even_when_the_body_raises(tmp_path: Path) -> None:
    """Completion condition 107 -- mutation M107 (no close on the
    exception path)."""
    slots = concurrency_slots.HostSharedConcurrencySlots(_slot_dir(tmp_path))
    with pytest.raises(ValueError):
        with slots.acquire(1):
            raise ValueError("synthetic body failure")
    with slots.acquire(1):
        pass


def _open_fd_count() -> int:
    return len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else len(os.listdir("/dev/fd"))


def test_rejected_candidate_fds_do_not_accumulate(tmp_path: Path) -> None:
    """Completion condition 108 -- mutation M108 (a rejected candidate's fd
    stays open)."""
    slots = concurrency_slots.HostSharedConcurrencySlots(_slot_dir(tmp_path))
    limit = 4
    holders = [slots.acquire(limit) for _ in range(limit)]
    for held in holders:
        held.__enter__()
    try:
        before = _open_fd_count()
        with pytest.raises(concurrency_slots.LimitExceeded):
            with slots.acquire(limit):
                pass
        after = _open_fd_count()
        assert after == before, (before, after)
    finally:
        for held in holders:
            held.__exit__(None, None, None)


def test_slot_search_start_point_follows_the_injected_random_source(tmp_path: Path) -> None:
    """Completion condition 109 -- mutation M109 (start at 0)."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 3)
    with slots.acquire(8):
        assert (slot_dir / "slot-3").exists()
        assert not (slot_dir / "slot-0").exists()


def test_full_slots_refuse_immediately_never_blocking(tmp_path: Path) -> None:
    """Completion condition 110 -- mutation M110 (drop `LOCK_NB`): with
    every slot held, a further `acquire()` refuses in well under a second,
    observed from a separate, join-bounded thread (a blocking `flock`
    would self-deadlock the calling thread)."""
    slots = concurrency_slots.HostSharedConcurrencySlots(_slot_dir(tmp_path))
    with slots.acquire(1):
        outcome: list[str] = []

        def _try_second() -> None:
            try:
                with slots.acquire(1):
                    outcome.append("admitted")
            except concurrency_slots.LimitExceeded:
                outcome.append("refused")

        started = time.monotonic()
        thread = threading.Thread(target=_try_second, daemon=True)
        thread.start()
        thread.join(timeout=2.0)
        elapsed = time.monotonic() - started
        assert not thread.is_alive(), f"acquire() was still blocked after {elapsed}s"
    assert outcome == ["refused"], outcome
    assert elapsed < 1.0, elapsed


def test_one_request_holds_exactly_one_slot_through_the_reserved_marker(tmp_path: Path) -> None:
    """Completion condition 111 -- mutation M111 (the pre-authentication
    slot does not set `_CONCURRENCY_RESERVED`): with `limit=1`, one
    request's pre-authentication slot plus its nested post-authentication
    `concurrency_slot` succeed start to finish -- the nested call never
    takes a second slot of the same request."""
    holder = _LimitStateHolder(
        concurrency_slots=concurrency_slots.HostSharedConcurrencySlots(_slot_dir(tmp_path)), concurrency_configured=True,
    )
    entered = []
    with holder.acquire_concurrency_slot(1):
        with holder.concurrency_slot(1):
            entered.append(True)
    assert entered == [True]


def test_slot_is_reacquirable_after_a_holding_child_process_is_sigkilled_and_after_a_plain_close(tmp_path: Path) -> None:
    """Completion condition 112 (audit): a CHILD process holds `slot-0`;
    the parent sees `LimitExceeded`; after SIGKILL and a bounded wait the
    parent re-acquires the SAME slot, and a plain close is immediately
    re-acquirable too."""
    slot_dir = _slot_dir(tmp_path)
    ready_path = tmp_path / "child_ready"
    child_src = (
        "import sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(_SRC_DIR)!r})\n"
        "from mitatedb_api import concurrency_slots\n"
        f"slots = concurrency_slots.HostSharedConcurrencySlots(Path({str(slot_dir)!r}))\n"
        "with slots.acquire(1):\n"
        f"    open({str(ready_path)!r}, 'w').close()\n"
        "    time.sleep(30)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        deadline = time.time() + _WAIT_S
        while not ready_path.exists():
            assert time.time() < deadline, "the child never signalled it holds the slot"
            time.sleep(0.05)
        slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
        with pytest.raises(concurrency_slots.LimitExceeded):
            with slots.acquire(1):
                pass
        proc.kill()
        proc.wait(timeout=_WAIT_S)
        with slots.acquire(1):
            pass
        with slots.acquire(1):
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=_WAIT_S)


# ===========================================================================
# the `scan` lock that serialises every slot search on this host
# (design ruling 43)
# ===========================================================================

#: the slot count the paused-scan race below runs with (L = 2).
_RACE_LIMIT = 2


def _call_bounded(fn, timeout_s: float):
    """Runs `fn()` on a daemon thread and waits for it at most `timeout_s`
    seconds. Returns `(finished, outcome, elapsed, thread)`; `outcome` is
    `("returned", value)` or `("raised", exc)`, or `None` if `fn` has not
    finished. The caller joins `thread` (bounded) once whatever blocks it
    has been released."""
    outcome: list[tuple[str, object]] = []

    def _run() -> None:
        try:
            outcome.append(("returned", fn()))
        except BaseException as exc:  # handed back to the caller's own assertions
            outcome.append(("raised", exc))

    started = time.monotonic()
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    elapsed = time.monotonic() - started
    return (not thread.is_alive(), outcome[0] if outcome else None, elapsed, thread)


def _acquire_one(slots: "concurrency_slots.HostSharedConcurrencySlots", limit: int = 1) -> str:
    with slots.acquire(limit):
        return "admitted"


def _hold_scan_directly(slot_dir: Path) -> int:
    """Another holder of `scan`: an fd of this test's own with `LOCK_EX`
    on it, released by closing it."""
    holder_fd = os.open(str(slot_dir / concurrency_slots.SCAN_FILENAME), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    return holder_fd


@contextlib.contextmanager
def _scan_paused_after_seeing_slot_0_held(slot_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    """X (this thread) holds `slot-0`; S (a thread of this process, its
    search starting at `slot-0`) is stopped right after its own `flock`
    finds `slot-0` held -- S holds `scan` at that point -- and X then
    releases `slot-0`. Yields the control object: set `s_continue` to let
    S finish its scan; `s_done` is set once S has a slot or has failed,
    and `s_outcome` records which. A thread registered in `roles` as "Y"
    sets `y_progressed` whenever its own `scan` lock attempt finds `scan`
    held. `fcntl.flock` is wrapped (the real call always runs) only to
    observe and to stop S; every wait is bounded by `_WAIT_S`."""
    scan_path = slot_dir / concurrency_slots.SCAN_FILENAME
    real_flock = fcntl.flock
    ctl = types.SimpleNamespace(
        s_saw_held=threading.Event(), s_continue=threading.Event(), s_done=threading.Event(), s_outcome=[],
        finish=threading.Event(), y_progressed=threading.Event(), roles={},
    )

    def _is_scan(fd: int) -> bool:
        return os.fstat(fd).st_ino == os.stat(scan_path).st_ino

    def _observing_flock(fd, operation):
        role = ctl.roles.get(threading.get_ident())
        try:
            return real_flock(fd, operation)
        except OSError as exc:
            if exc.errno in concurrency_slots._HELD_ERRNOS:
                if role == "S" and not _is_scan(fd) and not ctl.s_saw_held.is_set():
                    ctl.s_saw_held.set()
                    ctl.s_continue.wait(timeout=_WAIT_S)
                elif role == "Y" and _is_scan(fd):
                    ctl.y_progressed.set()
            raise

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _observing_flock)
    x_hold = concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 0).acquire(_RACE_LIMIT)
    x_hold.__enter__()
    x_open = True

    def _s() -> None:
        ctl.roles[threading.get_ident()] = "S"
        try:
            with concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 0).acquire(_RACE_LIMIT):
                ctl.s_outcome.append("acquired")
                ctl.s_done.set()
                ctl.finish.wait(timeout=_WAIT_S)
        except concurrency_slots.LimitExceeded:
            ctl.s_outcome.append("refused")
        except Exception as exc:  # recorded for the caller's own assertion
            ctl.s_outcome.append(repr(exc))
        finally:
            ctl.s_done.set()

    s_thread = threading.Thread(target=_s, daemon=True)
    s_thread.start()
    try:
        assert ctl.s_saw_held.wait(timeout=_WAIT_S), "S never reached slot-0 while X held it (空振り)"
        x_hold.__exit__(None, None, None)
        x_open = False
        yield ctl
    finally:
        ctl.s_continue.set()
        ctl.finish.set()
        if x_open:
            x_hold.__exit__(None, None, None)
        s_thread.join(timeout=_WAIT_S)


def _race_violations(s_outcome: list, y_during_scan: bool, y_after_scan: bool) -> list[str]:
    violations: list[str] = []
    if s_outcome != ["acquired"]:
        violations.append(
            f"S was not admitted ({s_outcome}) although at most 1 of the {_RACE_LIMIT} slots was held at any instant"
        )
    if y_during_scan:
        violations.append("Y took a slot while S's scan was still in progress")
    if not y_after_scan:
        violations.append("Y never took a slot after S's scan ended")
    return violations


def test_scan_serialises_a_same_process_thread_behind_a_paused_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 43 (s1-a) -- mutations Ms1 (drop the `scan` lock) and Ms1f
    (one `scan` fd opened once per process and reused): L = 2. X holds `slot-0`; S's scan
    sees `slot-0` held and is stopped there; X releases `slot-0`; Y, a
    second thread of THIS process whose search starts at `slot-1`, starts
    acquiring. Y must not get a slot while S's scan is stopped (it waits
    on `scan`); once S resumes, S is admitted (`slot-1`) -- never
    `LimitExceeded`, since at most one slot was held at any instant -- and
    Y is admitted after it (`slot-0`). Without the `scan` lock (Ms1), or
    with one `scan` fd shared by every thread of the process (Ms1f, where
    a second `LOCK_EX` on the same open file description succeeds), Y
    takes `slot-1` during S's scan and S is refused."""
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", _WAIT_S)
    with _scan_paused_after_seeing_slot_0_held(slot_dir, monkeypatch) as ctl:
        y_acquired = threading.Event()

        y_outcome: list[str] = []

        def _y() -> None:
            ctl.roles[threading.get_ident()] = "Y"
            try:
                with concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 1).acquire(_RACE_LIMIT):
                    y_acquired.set()
                    ctl.y_progressed.set()
                    ctl.finish.wait(timeout=_WAIT_S)
                y_outcome.append("acquired")
            except Exception as exc:  # recorded for the assertion below
                y_outcome.append(repr(exc))
            finally:
                ctl.y_progressed.set()

        y_thread = threading.Thread(target=_y, daemon=True)
        y_thread.start()
        try:
            assert ctl.y_progressed.wait(timeout=_WAIT_S), "Y never reached the scan lock nor a slot (空振り)"
            y_during_scan = y_acquired.is_set()
            ctl.s_continue.set()
            assert ctl.s_done.wait(timeout=_WAIT_S), "S never finished its scan"
            y_after_scan = y_acquired.wait(timeout=_WAIT_S)
        finally:
            ctl.finish.set()
            y_thread.join(timeout=_WAIT_S)
    violations = _race_violations(ctl.s_outcome, y_during_scan, y_after_scan)
    assert not violations, (violations, y_outcome)


def test_scan_serialises_another_process_behind_a_paused_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 43 (s1-b) -- mutation Ms1p (the `scan` file lock replaced by a
    process-local `threading.Lock`): the same race as the test above, with
    Y in a SECOND process (`multiprocessing` `spawn`; its progress and its
    admission are `multiprocessing.Event`s). A process-local lock excludes
    only this process' own threads, so under Ms1p Y takes `slot-1` during
    S's stopped scan and S is refused. The child reports its own
    `concurrency_slots.__file__`, checked equal to this process' own (the
    child ran this tree's module)."""
    import multiprocessing

    from . import slot_scan_child

    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", _WAIT_S)
    context = multiprocessing.get_context("spawn")
    progressed, acquired, release = context.Event(), context.Event(), context.Event()
    report = context.Queue()
    messages: dict[str, str] = {}
    with _scan_paused_after_seeing_slot_0_held(slot_dir, monkeypatch) as ctl:
        proc = context.Process(
            target=slot_scan_child.acquire_after_scan,
            args=(str(slot_dir), _RACE_LIMIT, 1, _WAIT_S, progressed, acquired, release, report),
            daemon=True,
        )
        proc.start()
        try:
            assert progressed.wait(timeout=3 * _WAIT_S), "the second process never reached the scan lock nor a slot (空振り)"
            y_during_scan = acquired.is_set()
            ctl.s_continue.set()
            assert ctl.s_done.wait(timeout=_WAIT_S), "S never finished its scan"
            y_after_scan = acquired.wait(timeout=_WAIT_S)
            release.set()
            for _ in range(2):
                key, value = report.get(timeout=_WAIT_S)
                messages[key] = value
        finally:
            release.set()
            proc.join(timeout=_WAIT_S)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=_WAIT_S)
    assert messages.get("module") == os.path.realpath(concurrency_slots.__file__), messages
    violations = _race_violations(ctl.s_outcome, y_during_scan, y_after_scan)
    assert not violations, (violations, messages.get("outcome"))


def test_scan_is_closed_before_the_with_body_so_another_acquisition_succeeds_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s7) -- mutation Ms7 (`scan` is closed after the `yield`):
    while an acquisition holds its slot (inside its own `with` body),
    another acquisition of the same directory succeeds in far less than
    the `scan` deadline -- `scan` was already closed when the first
    acquisition's body began. Under Ms7 the first acquisition still holds
    `scan`, so the second waits out the (here 0.5 s) deadline and raises
    `SlotBackendError`."""
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.5)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with slots.acquire(2):
        started = time.monotonic()
        with slots.acquire(2):
            elapsed = time.monotonic() - started
    assert elapsed < 0.25, f"the second acquisition took {elapsed:.3f}s while the first one held its slot"


def test_scan_held_past_its_deadline_raises_backend_error_and_the_caller_answers_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s2) -- mutations Ms2 (an expired deadline reads as
    `LimitExceeded`) and Ms2n (no deadline at all): another holder keeps
    `scan` for longer than the deadline (set to 0.2 s here through the
    module constant). `acquire` returns within a bounded wait, raising
    `SlotBackendError` whose message names the expired `scan` deadline,
    after at least the deadline; the same failure reaches
    `_LimitStateHolder.acquire_concurrency_slot`'s own caller as
    `StorageConfigurationError`, this peer's 503 -- never
    `ResourceLimitError`, never an admission. Under Ms2n the call has not
    returned when the bounded wait ends; the holder is released in
    `finally`, so the thread then ends."""
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.2)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    holder = _LimitStateHolder(concurrency_slots=slots, concurrency_configured=True)

    def _through_the_caller() -> str:
        with holder.acquire_concurrency_slot(1):
            return "admitted"

    holder_fd = _hold_scan_directly(slot_dir)
    threads: list[threading.Thread] = []
    results = []
    try:
        for fn in (lambda: _acquire_one(slots), _through_the_caller):
            finished, outcome, elapsed, thread = _call_bounded(fn, 5.0)
            threads.append(thread)
            assert finished, f"acquire() had not returned after {elapsed:.2f}s with scan held -- the scan wait has no deadline"
            results.append((outcome, elapsed))
    finally:
        os.close(holder_fd)
        for thread in threads:
            thread.join(timeout=_WAIT_S)
    (direct, direct_elapsed), (through_caller, _elapsed) = results
    assert direct[0] == "raised" and isinstance(direct[1], concurrency_slots.SlotBackendError), direct
    assert "scan" in str(direct[1]) and "deadline" in str(direct[1]), str(direct[1])
    assert direct_elapsed >= 0.2, direct_elapsed
    assert through_caller[0] == "raised" and isinstance(through_caller[1], StorageConfigurationError), through_caller
    assert http_module._STATUS_BY_CODE[http_module._classify(through_caller[1])] == 503


def test_scan_flock_unexpected_errno_raises_backend_error_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s2e) -- mutation Ms2e (every errno reads as "held" and is
    waited on): an injected `EPERM` from the `scan` lock (every `slot-<i>` lock
    runs for real) raises `SlotBackendError` naming the errno within 1 s,
    with the deadline set to 5 s -- never retried until the deadline."""
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 5.0)
    scan_path = slot_dir / concurrency_slots.SCAN_FILENAME
    real_flock = fcntl.flock
    scan_attempts: list[int] = []

    def _eperm_on_scan(fd, operation):
        if os.fstat(fd).st_ino == os.stat(scan_path).st_ino:
            scan_attempts.append(operation)
            raise OSError(errno.EPERM, "synthetic EPERM on scan")
        return real_flock(fd, operation)

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _eperm_on_scan)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    finished, outcome, elapsed, thread = _call_bounded(lambda: _acquire_one(slots), 2.0)
    try:
        assert finished, f"acquire() was still waiting after {elapsed:.2f}s on an EPERM from scan"
    finally:
        thread.join(timeout=_WAIT_S)
    assert scan_attempts, "no scan lock attempt observed (空振り)"
    assert outcome[0] == "raised" and isinstance(outcome[1], concurrency_slots.SlotBackendError), outcome
    assert f"errno {errno.EPERM}" in str(outcome[1]), str(outcome[1])
    assert elapsed < 1.0, elapsed


def test_scan_open_failure_raises_backend_error(tmp_path: Path) -> None:
    """Ruling 43 (s2e): `scan` cannot be opened (a directory planted under
    its name) -- `SlotBackendError`, never an admission and never
    `LimitExceeded`."""
    slot_dir = _slot_dir(tmp_path)
    (slot_dir / concurrency_slots.SCAN_FILENAME).mkdir()
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError, match="could not open scan file"):
        _acquire_one(slots)


def test_scan_symlink_is_refused_at_open(tmp_path: Path) -> None:
    """Ruling 43 (s2e) -- mutation Ms2s (`O_NOFOLLOW` dropped from the
    `scan` open):
    `scan` planted as a symlink to a regular file elsewhere is refused at
    open (`SlotBackendError`), never followed and locked."""
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("")
    slot_dir = _slot_dir(tmp_path)
    (slot_dir / concurrency_slots.SCAN_FILENAME).symlink_to(real_target)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError, match="could not open scan file"):
        _acquire_one(slots)


def test_scan_fd_is_closed_on_every_path_out_of_acquire(tmp_path: Path) -> None:
    """Ruling 43 (s3) -- mutation Ms3 (no `scan` close on the refusal
    path): the process'
    own open-fd count does not grow across an admission, a `LimitExceeded`,
    a `SlotBackendError` raised during the search (a `slot-0` symlink) and
    an exception raised during the search (the injected random source) --
    and inside an admission's `with` body exactly one fd more is open (the
    held slot's; `scan` is already closed)."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)

    def _assert_not_grown(path: str, before: int) -> None:
        after = _open_fd_count()
        assert after == before, f"open fd count grew from {before} to {after} on the {path} path"

    before = _open_fd_count()
    with slots.acquire(1):
        during = _open_fd_count()
    _assert_not_grown("admitted", before)
    assert during == before + 1, (before, during)

    holder = slots.acquire(1)
    holder.__enter__()
    try:
        before = _open_fd_count()
        with pytest.raises(concurrency_slots.LimitExceeded):
            _acquire_one(slots)
        _assert_not_grown("LimitExceeded", before)
    finally:
        holder.__exit__(None, None, None)

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir(mode=0o700)
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("")
    (broken_dir / "slot-0").symlink_to(real_target)
    before = _open_fd_count()
    with pytest.raises(concurrency_slots.SlotBackendError, match="slot file"):
        _acquire_one(concurrency_slots.HostSharedConcurrencySlots(broken_dir))
    _assert_not_grown("SlotBackendError", before)

    def _failing_random_source(n: int) -> int:
        raise RuntimeError("synthetic failure inside the search")

    before = _open_fd_count()
    with pytest.raises(RuntimeError, match="synthetic failure inside the search"):
        _acquire_one(concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=_failing_random_source))
    _assert_not_grown("exception", before)


def test_scan_wait_interrupted_by_keyboard_interrupt_leaks_no_fd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 43 (s3b) -- mutations Ms3b (the `scan` wait's handler
    narrowed to `Exception`) and Ms3bw (that handler's close dropped):
    another holder keeps `scan`, and the waiting acquisition's second
    pause between two attempts raises `KeyboardInterrupt` (this module's
    own `time.sleep` replaced; the deadline is 5 s, so the interrupt, not
    the deadline, ends the wait). The interrupt propagates out of
    `acquire`, and the process' open-fd count is the same as before the
    call -- the waiting `scan` fd was closed."""
    slot_dir = _slot_dir(tmp_path)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 5.0)
    pauses: list[float] = []

    def _interrupting_sleep(seconds: float) -> None:
        pauses.append(seconds)
        if len(pauses) == 2:
            raise KeyboardInterrupt("synthetic interrupt during the scan wait")

    monkeypatch.setattr(concurrency_slots, "time", types.SimpleNamespace(monotonic=time.monotonic, sleep=_interrupting_sleep))
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    holder_fd = _hold_scan_directly(slot_dir)
    try:
        before = _open_fd_count()
        finished, outcome, elapsed, thread = _call_bounded(lambda: _acquire_one(slots), 5.0)
        thread.join(timeout=_WAIT_S)
        after = _open_fd_count()
    finally:
        os.close(holder_fd)
    assert finished, f"acquire() had not returned after {elapsed:.2f}s"
    assert len(pauses) == 2, f"the interrupt was not raised inside the scan wait (空振り): {pauses}"
    assert outcome[0] == "raised" and isinstance(outcome[1], KeyboardInterrupt), outcome
    assert after == before, f"open fd count grew from {before} to {after} on the interrupted scan wait"


def test_candidate_flock_interrupted_by_keyboard_interrupt_leaks_no_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s3b) -- mutation Ms3bc (the candidate fd's
    `BaseException` handler dropped): the `slot-0` candidate's own
    `flock()` raises `KeyboardInterrupt` (injected; the `scan` lock runs
    for real). The interrupt propagates out of `acquire`, and the
    process' open-fd count is the same as before the call -- the
    candidate's fd and `scan` were both closed."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    real_flock = fcntl.flock
    slot_attempts: list[int] = []

    def _interrupting_flock(fd, operation):
        slot_path = slot_dir / "slot-0"
        if slot_path.exists() and os.fstat(fd).st_ino == os.stat(slot_path).st_ino:
            slot_attempts.append(operation)
            raise KeyboardInterrupt("synthetic interrupt during a candidate's flock")
        return real_flock(fd, operation)

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _interrupting_flock)
    before = _open_fd_count()
    finished, outcome, elapsed, thread = _call_bounded(lambda: _acquire_one(slots), 5.0)
    thread.join(timeout=_WAIT_S)
    after = _open_fd_count()
    assert finished, f"acquire() had not returned after {elapsed:.2f}s"
    assert slot_attempts, "no slot-0 lock attempt observed (空振り)"
    assert outcome[0] == "raised" and isinstance(outcome[1], KeyboardInterrupt), outcome
    assert after == before, f"open fd count grew from {before} to {after} on the interrupted candidate flock"


def test_held_slot_fd_is_closed_when_an_interrupt_follows_the_scan_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s3c) -- mutation Ms3c (the outer handler's
    `os.close(held_fd)` dropped): with `limit = 1` the search locks
    `slot-0`, and the `scan` close right after the search raises
    `KeyboardInterrupt` once the real close has run (this module's own
    `os` replaced by a namespace whose `close` does that for the `scan`
    fd only). The interrupt propagates out of `acquire`, the process'
    open-fd count is the same as before the call, and `slot-0` is free
    -- a fresh fd takes `LOCK_EX | LOCK_NB` on it."""
    slot_dir = _slot_dir(tmp_path)
    scan_path = slot_dir / concurrency_slots.SCAN_FILENAME
    scan_closes: list[int] = []

    def _interrupting_close(fd: int) -> None:
        is_scan = scan_path.exists() and os.fstat(fd).st_ino == os.stat(scan_path).st_ino
        os.close(fd)
        if is_scan:
            scan_closes.append(fd)
            raise KeyboardInterrupt("synthetic interrupt right after the scan close")

    patched_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith("__")})
    patched_os.close = _interrupting_close
    monkeypatch.setattr(concurrency_slots, "os", patched_os)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 0)
    before = _open_fd_count()
    finished, outcome, elapsed, thread = _call_bounded(lambda: _acquire_one(slots), 5.0)
    thread.join(timeout=_WAIT_S)
    after = _open_fd_count()
    probe_fd = os.open(str(slot_dir / "slot-0"), os.O_RDWR)
    try:
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            slot_0_free = False
        else:
            slot_0_free = True
    finally:
        os.close(probe_fd)
    assert finished, f"acquire() had not returned after {elapsed:.2f}s"
    assert len(scan_closes) == 1, f"the scan close was not observed (空振り): {scan_closes}"
    assert outcome[0] == "raised" and isinstance(outcome[1], KeyboardInterrupt), outcome
    assert (after, slot_0_free) == (before, True), (
        f"open fd count went from {before} to {after} after the interrupted scan close; slot-0 free: {slot_0_free}"
    )


def test_scan_lock_held_by_a_sigkilled_child_process_is_released_by_the_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 43 (s4, audit -- a kernel property, no mutation): a CHILD process
    holds the `scan` lock (opened with the module's own flags and mode)
    and signals it; this process' acquisition then fails with the `scan`
    deadline (0.3 s here) -- the child really holds it; after SIGKILL and
    a bounded wait for the child, this process acquires."""
    slot_dir = _slot_dir(tmp_path)
    ready_path = tmp_path / "child_ready"
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.3)
    src_dir = str(_SRC_DIR)
    child_src = (
        "import fcntl, os, sys, time\n"
        f"sys.path.insert(0, {src_dir!r})\n"
        "from mitatedb_api import concurrency_slots\n"
        f"fd = os.open(os.path.join({str(slot_dir)!r}, concurrency_slots.SCAN_FILENAME), "
        "concurrency_slots._OPEN_FLAGS, concurrency_slots._FILE_MODE)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        f"open({str(ready_path)!r}, 'w').close()\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        deadline = time.monotonic() + _WAIT_S
        while not ready_path.exists():
            assert time.monotonic() < deadline, "the child never signalled it holds scan"
            assert proc.poll() is None, f"the child exited early ({proc.returncode})"
            time.sleep(0.05)
        slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
        with pytest.raises(concurrency_slots.SlotBackendError, match="deadline"):
            _acquire_one(slots)
        proc.kill()  # SIGKILL
        proc.wait(timeout=_WAIT_S)
        assert _acquire_one(slots) == "admitted"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=_WAIT_S)


def test_scan_file_is_distinct_from_every_slot_file_and_never_counted_as_held(tmp_path: Path) -> None:
    """Ruling 43 (s5) -- mutation Ms5 (`scan` named `slot-0`): with
    `limit = 1`, one acquisition is admitted and, while it is held, the
    held-slot probe (`_held_slot_names`, the same count the
    adapter tests use) finds exactly `slot-0` held -- `scan` is closed and
    is not a `slot-*` file -- and the directory holds exactly `scan` and
    `slot-0`, `scan` with mode 0600. Named `slot-0`, `scan` would hold the
    lock on the very slot it searches, so the acquisition is refused."""
    slot_dir = _slot_dir(tmp_path)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with slots.acquire(1):
        held = _held_slot_names(slot_dir)
        names = sorted(entry.name for entry in slot_dir.iterdir())
    assert held == ["slot-0"], held
    assert names == sorted([concurrency_slots.SCAN_FILENAME, "slot-0"]), names
    assert concurrency_slots.SCAN_FILENAME != concurrency_slots.SELFCHECK_FILENAME
    assert not concurrency_slots.SCAN_FILENAME.startswith("slot-")
    assert stat.S_IMODE((slot_dir / concurrency_slots.SCAN_FILENAME).stat().st_mode) == 0o600


def test_limit_state_holder_rejects_concurrency_configured_true_without_slots() -> None:
    """Completion condition 114b -- mutation M114b (drop the guard):
    declaring the host-shared bound configured without the mechanism that
    shares it is refused at construction."""
    with pytest.raises(ValueError, match="concurrency_configured"):
        _LimitStateHolder(concurrency_slots=None, concurrency_configured=True)


# ===========================================================================
# completion condition 113: the 2-strategy mapping helper
# ===========================================================================


def test_resolve_limit_enforcement_configured_is_always_enforced_regardless_of_ceiling() -> None:
    """Completion condition 113 (the helper's configured branch)."""
    assert [resolve_limit_enforcement(configured=True, ceiling=c) for c in (1, 2, 99)] == ["enforced"] * 3


def test_resolve_limit_enforcement_unconfigured_follows_the_single_process_rule() -> None:
    """Completion condition 113 -- mutation M113 (the mapping reads
    `enforced` whether or not the mechanism is wired): `configured=False`
    keeps the single-process rule."""
    assert resolve_limit_enforcement(configured=False, ceiling=1) == "enforced"
    assert resolve_limit_enforcement(configured=False, ceiling=2) == "deployment_required"


def test_build_app_concurrency_mapping_follows_workers_vs_ceiling_on_all_three_forms(platform, r113_app) -> None:
    """Completion condition 114 -- mutation M114 (`main.py` drops the
    `workers >= ceiling` condition): a REAL `build_app()` (slot directory
    wired) serves `concurrency` `enforced` at (ceiling, workers) = (1, 1)
    and (2, 2), and `deployment_required` at (2, 1) -- each read from the
    capability document the built app serves to an authenticated
    session."""
    main_module = _main_module(platform, r113_app)
    observed: dict[tuple[int, int], str] = {}
    try:
        for ceiling, workers in ((1, 1), (2, 2), (2, 1)):
            _set_process_ceilings(platform, {"data": ceiling, "control": 1})
            app = main_module.build_app(_main_env(platform, r113_app, workers=str(workers)))
            try:
                _credential_id, bearer = _issue(platform, r113_app.app_id)
                document = app.app.state.service.authenticate(bearer).capabilities()
                observed[(ceiling, workers)] = document["limit_enforcement"]["concurrency"]
            finally:
                _close_built_app(main_module, app)
    finally:
        _set_process_ceilings(platform, {"data": 1, "control": 1})
        pool_module.set_connection_application_name(None)
    assert observed == {
        (1, 1): "enforced",
        (2, 2): "enforced",
        (2, 1): "deployment_required",
    }, observed


# ===========================================================================
# completion conditions 116-120: workers env validation
# ===========================================================================


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "abc"])
def test_data_workers_env_rejects_unset_empty_zero_negative_non_numeric(platform, r113_app, raw) -> None:
    """Completion condition 116 -- mutation M116 (unset falls back to 1)."""
    main_module = _main_module(platform, r113_app)
    env = {} if raw is None else {"MITATEDB_WORKERS": raw}
    with pytest.raises(RuntimeError, match="MITATEDB_WORKERS"):
        main_module._workers_from_env(env, "MITATEDB_WORKERS")


def _load_isolated(module_file: str, name: str, namespace: dict | None = None):
    """`<name>` from `<module_file>` via AST + isolated exec -- never a
    plain import, which would run that module's own module-level `app =
    build_app()`/`build_control_app()` (needs a real environment). The
    functions loaded this way reference nothing else at module scope
    beyond `namespace`."""
    import ast

    path = _SRC_DIR / "mitatedb_api" / module_file
    tree = ast.parse(path.read_text())
    node = next(
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    scope: dict = dict(namespace or {})
    exec(compile(isolated, str(path), "exec"), scope)
    return scope[name]


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "abc"])
def test_control_workers_env_rejects_unset_empty_zero_negative_non_numeric(raw) -> None:
    """Completion condition 117 -- mutation M117 (unset falls back to 1)."""
    workers_from_env = _load_isolated("control_main.py", "_workers_from_env")
    env = {} if raw is None else {"MITATEDB_CONTROL_WORKERS": raw}
    with pytest.raises(RuntimeError, match="MITATEDB_CONTROL_WORKERS"):
        workers_from_env(env, "MITATEDB_CONTROL_WORKERS")


def test_build_app_fails_when_workers_exceeds_declared_data_ceiling(platform, r113_app) -> None:
    """Completion condition 118 -- mutation M118 (drop the data-plane
    workers check): the fixture declares `process_ceilings.data` = 1."""
    main_module = _main_module(platform, r113_app)
    try:
        with pytest.raises(RuntimeError, match="MITATEDB_WORKERS"):
            main_module.build_app(_main_env(platform, r113_app, workers="5"))
    finally:
        pool_module.set_connection_application_name(None)


def test_build_app_workers_check_raises_synchronously_never_needing_asgi_lifespan(platform, r113_app) -> None:
    """Completion condition 120 -- mutation M120 (the check moves into the
    lifespan): the workers-vs-ceiling failure is raised by the plain,
    synchronous `build_app(...)` call itself -- no ASGI lifespan is driven
    here at all."""
    main_module = _main_module(platform, r113_app)
    try:
        with pytest.raises(RuntimeError, match="exceeds process_ceilings.data"):
            main_module.build_app(_main_env(platform, r113_app, workers="9"))
    finally:
        pool_module.set_connection_application_name(None)


def _control_env(control_platform_info, **overrides) -> dict[str, str]:
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": control_platform_info.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": control_platform_info.registry_schema,
        "MITATEDB_CONTROL_WORKERS": "1",
    }
    env.update(overrides)
    return env


def _control_main_module(control_platform_info):
    """Guarded first import of `mitatedb_api.control_main` (its own
    module-level `app = build_control_app()`), `test_control_main.py`'s
    own identical precedent."""
    if "mitatedb_api.control_main" not in sys.modules:
        previous = dict(os.environ)
        try:
            os.environ.update(_control_env(control_platform_info))
            import mitatedb_api.control_main  # noqa: F401
        finally:
            os.environ.clear()
            os.environ.update(previous)
            pool_module.set_connection_application_name(None)
    import mitatedb_api.control_main as control_main_module
    return control_main_module


def test_build_control_app_fails_when_workers_exceeds_declared_control_ceiling(control_platform) -> None:
    """Completion condition 119 -- mutation M119 (drop the control-plane
    workers check): the fixture declares `process_ceilings.control` = 1."""
    control_main = _control_main_module(control_platform)
    try:
        with pytest.raises(RuntimeError, match="MITATEDB_CONTROL_WORKERS"):
            control_main.build_control_app(_control_env(control_platform, MITATEDB_CONTROL_WORKERS="5"))
    finally:
        pool_module.set_connection_application_name(None)


# ===========================================================================
# completion conditions 121-124: `--preflight`
# ===========================================================================


def test_data_preflight_exits_0_on_a_sound_env(platform, r113_app) -> None:
    """Completion condition 121 (sound env): `python -m mitatedb_api.main
    --preflight` exits 0."""
    result = _run_preflight_subprocess("mitatedb_api.main", _main_env(platform, r113_app))
    assert result.returncode == 0, result.stderr


def test_data_preflight_exits_nonzero_with_f15_when_process_ceilings_missing(platform, r113_app) -> None:
    """Completion condition 121 (F-15) -- mutation M121b (a failing
    module-level `build_app()` exits 0 under `--preflight`)."""
    _delete_process_ceilings(platform)
    try:
        result = _run_preflight_subprocess("mitatedb_api.main", _main_env(platform, r113_app))
        assert result.returncode != 0
        assert "F-15" in result.stderr, result.stderr
    finally:
        _set_process_ceilings(platform, {"data": 1, "control": 1})

@contextlib.contextmanager
def _rate_function_withheld(platform_info) -> Iterator[None]:
    """Renames the platform's own `credential_request_rate_admit(text,
    integer)` for the duration of the block (as the admin role) and
    renames it back in `finally` -- a platform the rate migration was
    never applied to, as far as the startup check can see."""
    signature = "(text, integer)"
    with psycopg.connect(_platform_admin_dsn(platform_info), autocommit=True) as conn:
        conn.execute(
            sql.SQL("ALTER FUNCTION {}" + signature + " RENAME TO credential_request_rate_admit_withheld").format(
                sql.Identifier(platform_info.registry_schema, "credential_request_rate_admit")
            )
        )
    try:
        yield
    finally:
        with psycopg.connect(_platform_admin_dsn(platform_info), autocommit=True) as conn:
            conn.execute(
                sql.SQL("ALTER FUNCTION {}" + signature + " RENAME TO credential_request_rate_admit").format(
                    sql.Identifier(platform_info.registry_schema, "credential_request_rate_admit_withheld")
                )
            )


def test_build_app_and_preflight_fail_naming_the_rate_migration_when_the_rate_function_is_missing(platform, r113_app) -> None:
    """F5 (m1) -- mutation Mm1 (drop the startup check): with the
    platform's own rate function absent, `build_app()` and `python -m
    mitatedb_api.main --preflight` both fail naming
    `0016_credential_request_rate.sql`, instead of starting a data plane
    whose every request would be a 503. Non-空振り: once the function is
    back, the same check passes on a connection of the data plane's own
    role."""
    from mitatedb_api import platform_declarations

    migration = platform_declarations.REQUEST_RATE_MIGRATION_FILENAME
    assert migration == "0016_credential_request_rate.sql"
    main_module = _main_module(platform, r113_app)
    try:
        with _rate_function_withheld(platform):
            with pytest.raises(RuntimeError, match=migration):
                main_module.build_app(_main_env(platform, r113_app))
            result = _run_preflight_subprocess("mitatedb_api.main", _main_env(platform, r113_app))
    finally:
        pool_module.set_connection_application_name(None)
    assert result.returncode != 0
    assert migration in result.stderr, result.stderr
    with psycopg.connect(platform.api_dsn) as conn:
        platform_declarations.check_request_rate_function(conn, schema=platform.registry_schema, migration=migration)


def test_build_app_fails_naming_the_rate_migration_when_the_data_plane_role_may_not_execute_the_rate_function(
    platform, r113_app,
) -> None:
    """F5 (m2) -- mutation Mm2 (drop the privilege read): the rate function
    exists but the data plane's own role (the `MITATEDB_PLATFORM_DSN`
    login role) has lost EXECUTE on it -- `build_app()` fails naming
    `0016_credential_request_rate.sql`. EXECUTE is granted back in
    `finally`."""
    from mitatedb_api import platform_declarations

    with psycopg.connect(platform.api_dsn) as conn:
        (api_role,) = conn.execute("SELECT current_user").fetchone()
    function = sql.SQL("{}(text, integer)").format(
        sql.Identifier(platform.registry_schema, "credential_request_rate_admit")
    )
    main_module = _main_module(platform, r113_app)
    with psycopg.connect(_platform_admin_dsn(platform), autocommit=True) as conn:
        conn.execute(sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM {}").format(function, sql.Identifier(api_role)))
    try:
        with pytest.raises(RuntimeError, match="may not EXECUTE") as excinfo:
            main_module.build_app(_main_env(platform, r113_app))
        assert platform_declarations.REQUEST_RATE_MIGRATION_FILENAME in str(excinfo.value)
    finally:
        pool_module.set_connection_application_name(None)
        with psycopg.connect(_platform_admin_dsn(platform), autocommit=True) as conn:
            conn.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(function, sql.Identifier(api_role)))



def test_control_preflight_exits_0_on_a_sound_env(control_platform) -> None:
    """Completion condition 122 (sound env): `python -m mitatedb_api.
    control_main --preflight` exits 0 -- the positive control for the F-15
    test below."""
    result = _run_preflight_subprocess("mitatedb_api.control_main", _control_env(control_platform))
    assert result.returncode == 0, result.stderr


def test_control_preflight_exits_nonzero_with_f15_when_process_ceilings_missing(control_platform) -> None:
    """Completion condition 122 (F-15) -- mutation M122b (a failing
    module-level `build_control_app()` exits 0 under `--preflight`)."""
    _delete_process_ceilings(control_platform)
    try:
        result = _run_preflight_subprocess("mitatedb_api.control_main", _control_env(control_platform))
        assert result.returncode != 0
        assert "F-15" in result.stderr, result.stderr
    finally:
        _set_process_ceilings(control_platform, {"data": 1, "control": 1})


def test_control_preflight_exits_nonzero_when_control_workers_exceed_the_declared_ceiling(control_platform) -> None:
    """Completion condition 122 (workers > ceiling): with `process_
    ceilings.control` = 1 declared, `MITATEDB_CONTROL_WORKERS=2` makes
    `python -m mitatedb_api.control_main --preflight` exit non-zero,
    naming the variable on stderr."""
    result = _run_preflight_subprocess(
        "mitatedb_api.control_main", _control_env(control_platform, MITATEDB_CONTROL_WORKERS="2"),
    )
    assert result.returncode != 0
    assert "MITATEDB_CONTROL_WORKERS" in result.stderr and "exceeds process_ceilings.control" in result.stderr, result.stderr


class _FakeAsgiLifespanApp:
    """A minimal ASGI app whose `lifespan` scope answers with a
    caller-chosen startup result."""

    def __init__(self, *, startup_failed: bool = False) -> None:
        self.startup_failed = startup_failed

    async def __call__(self, scope, receive, send) -> None:
        message = await receive()
        assert message["type"] == "lifespan.startup"
        if self.startup_failed:
            await send({"type": "lifespan.startup.failed", "message": "synthetic startup failure"})
            return
        await send({"type": "lifespan.startup.complete"})
        message = await receive()
        assert message["type"] == "lifespan.shutdown"
        await send({"type": "lifespan.shutdown.complete"})


@pytest.mark.parametrize("module_file", ["main.py", "control_main.py"])
def test_run_lifespan_once_propagates_a_startup_failure(module_file: str) -> None:
    """Completion conditions 121/122 -- mutations M121 (the data preflight
    swallows a startup failure) and M122 (the control preflight does): each
    entry's own `_run_lifespan_once` re-raises a `lifespan.startup.failed`
    message (bounded: a swallowed failure would wait forever for a
    shutdown answer)."""
    run_once = _load_isolated(module_file, "_run_lifespan_once", {"asyncio": asyncio, "ASGIApp": object})
    with pytest.raises((RuntimeError, asyncio.TimeoutError)) as excinfo:
        asyncio.run(asyncio.wait_for(run_once(_FakeAsgiLifespanApp(startup_failed=True)), timeout=5.0))
    assert isinstance(excinfo.value, RuntimeError) and "synthetic startup failure" in str(excinfo.value), repr(excinfo.value)


@pytest.mark.parametrize("module_file", ["main.py", "control_main.py"])
def test_preflight_entry_source_reuses_the_bare_module_app_variable(module_file: str) -> None:
    """Completion condition 123 -- mutation M123 (the data entry builds a
    second app): both entries drive `_run_lifespan_once` against the bare
    module-level `app`, never a fresh build of their own."""
    source = (_SRC_DIR / "mitatedb_api" / module_file).read_text()
    match = re.search(r'if __name__ == "__main__" and "--preflight" in sys\.argv:\n(.*)', source, re.DOTALL)
    assert match is not None, f"no --preflight entry block in {module_file}"
    entry = match.group(1)
    assert "asyncio.run(_run_lifespan_once(app))" in entry, entry
    assert "build_app(" not in entry and "build_control_app(" not in entry, entry


def test_preflight_lifespan_closes_the_platform_pool_and_every_persistent_connection(platform, r113_app) -> None:
    """Completion condition 124 -- mutation M124 (the lifespan shutdown
    skips `credentials.close()`): after one real authentication forces a
    pooled platform connection, one preflight lifespan cycle leaves the
    platform pool with no connection and both role pools of every served
    application with no connection (the startup ledger check left one
    runtime connection idle in its pool)."""
    main_module = _main_module(platform, r113_app)
    app = main_module.build_app(_main_env(platform, r113_app))
    try:
        service = app.app.state.service
        _credential_id, bearer = _issue(platform, r113_app.app_id)
        service.authenticate(bearer)
        store_pool = service._credentials._pool  # noqa: SLF001
        cell = service._cell_factory(r113_app.app_id)  # noqa: SLF001
        assert store_pool._created >= 1, "the platform pool holds no connection yet (空振り)"  # noqa: SLF001
        assert cell._backend._runtime_pool._created >= 1, "the application's runtime pool holds no connection yet (空振り)"  # noqa: SLF001
    finally:
        _close_built_app(main_module, app)
    assert store_pool._created == 0, store_pool._created  # noqa: SLF001
    assert cell._backend._runtime_pool._created == 0 and cell._backend._developer_pool._created == 0  # noqa: SLF001


# ===========================================================================
# completion conditions 126-127: `application_name`
# ===========================================================================


def test_data_plane_connections_carry_the_documented_application_name(platform, r113_app) -> None:
    """Completion condition 126 -- mutation M126 (the served application's
    pooled connections omit `application_name`): after `build_app()`, the
    two sessions a data request borrows (runtime and developer) read
    `MitateDB-api:data:<pid>`."""
    main_module = _main_module(platform, r113_app)
    app = main_module.build_app(_main_env(platform, r113_app))
    try:
        backend = app.app.state.service._cell_factory(r113_app.app_id)._backend  # noqa: SLF001
        with backend.request_scope("dml") as scope:
            runtime_conn, developer_conn = scope.main, scope.developer
            pids = [runtime_conn.info.backend_pid, developer_conn.info.backend_pid]
            with psycopg.connect(platform.admin_dsn) as probe:
                with probe.cursor() as cur:
                    cur.execute("SELECT application_name FROM pg_stat_activity WHERE pid = ANY(%s)", [pids])
                    names = [row[0] for row in cur.fetchall()]
    finally:
        _close_built_app(main_module, app)
    assert len(names) == 2, ("both persistent sessions must be visible (空振り)", names)
    for name in names:
        assert re.fullmatch(r"MitateDB-api:data:\d+", name), name


def test_control_plane_connections_carry_the_documented_application_name(control_platform, monkeypatch) -> None:
    """Completion condition 127 -- mutation M127 (the control entry tags
    its connections as `data`): `build_control_service`'s own startup
    connection -- a real session of this control-plane build -- is read
    back from `pg_stat_activity` by its own backend pid, from a second
    connection, while it is still open (the F-18 call site is wrapped to
    look first)."""
    from mitatedb_api import control_composition

    control_main = _control_main_module(control_platform)
    observed: list[str] = []
    original = control_composition.check_max_connections_headroom

    def _observing(conn, *args, **kwargs):
        with psycopg.connect(control_platform.admin_dsn) as probe:
            with probe.cursor() as cur:
                cur.execute("SELECT application_name FROM pg_stat_activity WHERE pid = %s", [conn.info.backend_pid])
                observed.extend(row[0] for row in cur.fetchall())
        return original(conn, *args, **kwargs)

    monkeypatch.setattr(control_composition, "check_max_connections_headroom", _observing)
    try:
        control_main.build_control_app(_control_env(control_platform))
    finally:
        pool_module.set_connection_application_name(None)
    assert observed, "the startup connection was never observed (空振り)"
    assert len(observed) == 1 and re.fullmatch(r"MitateDB-api:control:\d+", observed[0]), observed


# ===========================================================================
# completion conditions 128-130, 144: thread-limit-derived pool dimension
# ===========================================================================


def test_role_pool_size_is_thread_limit_plus_two() -> None:
    """Completion condition 128 (the helper's arithmetic)."""
    assert role_pool_size(6) == 8
    assert role_pool_size(4) == 6


def test_build_app_sizes_the_platform_pool_from_mitatedb_thread_limit(platform, r113_app) -> None:
    """Completion condition 128 -- mutation M128 (`main.py` sizes from
    `DEFAULT_THREAD_LIMIT`): `MITATEDB_THREAD_LIMIT=6` (no pool override)
    gives a platform pool of `role_pool_size(6)` = 8."""
    main_module = _main_module(platform, r113_app)
    env = _main_env(platform, r113_app)
    env["MITATEDB_THREAD_LIMIT"] = "6"
    app = main_module.build_app(env)
    try:
        size = app.app.state.service._credentials._pool._max_size  # noqa: SLF001
    finally:
        _close_built_app(main_module, app)
    assert size == 8, size


def test_platform_pool_default_does_not_follow_mitatedb_max_concurrency(platform, r113_app) -> None:
    """Completion condition 144 -- mutation M144 (the default follows
    `MITATEDB_MAX_CONCURRENCY`): with `MITATEDB_MAX_CONCURRENCY=7` and no
    thread-limit or pool override, the platform pool is `role_pool_size(
    DEFAULT_THREAD_LIMIT)` = 6, never 7."""
    main_module = _main_module(platform, r113_app)
    env = _main_env(platform, r113_app)
    env["MITATEDB_MAX_CONCURRENCY"] = "7"
    app = main_module.build_app(env)
    try:
        size = app.app.state.service._credentials._pool._max_size  # noqa: SLF001
    finally:
        _close_built_app(main_module, app)
    assert size == role_pool_size(http_module.DEFAULT_THREAD_LIMIT) == 6, size


def test_f18_check_max_connections_headroom_uses_pool_size_not_concurrency() -> None:
    """Completion condition 129 -- mutation M129 (the F-18 floors stay at
    `2 x 32`): the lower bound derives from the given `pool_size`."""
    from mitatedb_api.platform_declarations import ProcessCeilings, check_max_connections_headroom

    report = check_max_connections_headroom(
        _FakeHeadroomConn(application_count=1, max_connections=1_000_000, superuser_reserved=0, reserved=0),
        schema="s", ops_module="test", process_ceilings=ProcessCeilings(data=4, control=0), pool_size=6,
    )
    assert report.lower_bound == 4 * (12 + 12) == 96, report.lower_bound


def test_build_control_service_f18_uses_thread_limit_pool_size_not_max_concurrency(control_platform) -> None:
    """Completion condition 129c -- mutation M129c (control's own
    `pool_size` is the declared concurrency 32): the test declares the
    largest `data` ceiling whose F-18 lower bound with `pool_size` 6 fits
    this cluster's own headroom but whose bound with 32 does not, so a
    REAL `build_control_service` succeeds only on the thread-limit basis."""
    from mitatedb_api import control_composition
    from mitatedb_api.platform_declarations import headroom_lower_bound

    with psycopg.connect(control_platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, setting FROM pg_settings WHERE name = ANY(%s)",
                [["max_connections", "superuser_reserved_connections", "reserved_connections"]],
            )
            settings = {name: int(value) for name, value in cur.fetchall()}
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(control_platform.registry_schema, "applications")))
            (registered,) = cur.fetchone()
    headroom = settings["max_connections"] - settings["superuser_reserved_connections"] - settings.get("reserved_connections", 0)

    def _bound(data: int, pool_size: int) -> int:
        return headroom_lower_bound(
            data_processes=data, control_processes=1, platform_pool_floor=2 * pool_size,
            application_pair_floor=2 * pool_size, control_plane_floor=16, registered_applications=registered,
        )

    data_ceiling = 0
    while _bound(data_ceiling + 1, 6) <= headroom:
        data_ceiling += 1
    assert data_ceiling >= 1, headroom
    assert _bound(data_ceiling, 32) > headroom, (data_ceiling, headroom)
    _set_process_ceilings(control_platform, {"data": data_ceiling, "control": 1})
    try:
        control_composition.build_control_service(_control_env(control_platform))
    finally:
        _set_process_ceilings(control_platform, {"data": 1, "control": 1})


def test_f16_startup_floor_scales_with_process_ceilings_data(platform, r113_app) -> None:
    """Completion condition 130 -- mutation M130 (the application roles'
    F-16 floor is not multiplied by `process_ceilings.data`): with
    `process_ceilings.data` = 3 (and `MITATEDB_WORKERS=3`), the served
    application's runtime role floor is 6 x 3 = 18; its real limit
    lowered to 10 (between the unscaled 6 and the scaled 18) makes
    `build_app()` fail fast naming floor 18."""
    main_module = _main_module(platform, r113_app)
    _set_process_ceilings(platform, {"data": 3, "control": 1})
    with psycopg.connect(platform.admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname = %s", [r113_app.runtime_role])
            (original,) = cur.fetchone()
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(sql.Identifier(r113_app.runtime_role)))
    try:
        with pytest.raises(RuntimeError, match="floor 18"):
            main_module.build_app(_main_env(platform, r113_app, workers="3"))
    finally:
        with psycopg.connect(platform.admin_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("ALTER ROLE {} CONNECTION LIMIT {}").format(
                        sql.Identifier(r113_app.runtime_role), sql.Literal(int(original))
                    )
                )
        _set_process_ceilings(platform, {"data": 1, "control": 1})
        pool_module.set_connection_application_name(None)


# ===========================================================================
# completion condition 132: `ops verify-declarations` workers check
# ===========================================================================


def test_verify_declarations_reports_workers_exceeding_ceiling_with_a_dedicated_exit_code(
    verify_platform, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 132 -- mutation M132 (drop the workers check):
    `MITATEDB_WORKERS` (this CLI invocation's own env) above the declared
    ceiling reports a dedicated exit code (19), distinct from every other
    F-number."""
    import mitatedb_api.ops as ops

    _verify_declare_writer(verify_platform)
    _verify_set_row(verify_platform, "surfaces", {"data": {"base_url": "https://r113-f20.example.invalid/v1"}})
    _verify_set_row(verify_platform, "process_ceilings", {"data": 1, "control": 1})
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", verify_platform.provision_dsn)
    monkeypatch.setenv("MITATEDB_PLATFORM_SCHEMA", verify_platform.schema)
    monkeypatch.setenv("MITATEDB_WORKERS", "99")
    monkeypatch.delenv("MITATEDB_CONTROL_PLANE_STATUS", raising=False)
    assert ops.main(["verify-declarations"]) == 19


# ===========================================================================
# completion conditions 134-135, 142-143: the http plug's own wiring
# ===========================================================================


def _held_slot_names(slot_dir: Path) -> list[str]:
    held: list[str] = []
    for candidate in sorted(slot_dir.glob("slot-*")):
        probe_fd = os.open(str(candidate), os.O_RDWR)
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
        except OSError as exc:
            assert exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN), exc
            held.append(candidate.name)
        finally:
            os.close(probe_fd)
    return held


def _adapter_rate_rows(adapter_like, credential_id: str) -> int:
    with psycopg.connect(adapter_like._platform.api_dsn) as conn:  # noqa: SLF001
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(
                    sql.Identifier(adapter_like._platform.schema, RATE_TABLE)  # noqa: SLF001
                ),
                [credential_id],
            )
            (count,) = cur.fetchone()
    return count


def test_real_http_request_holds_the_shared_slot_and_writes_a_rate_row(platform, r113_app, monkeypatch) -> None:
    """Completion condition 134a (composition-root companion of 134/135,
    never a substitute for the adapter-session observation below) --
    mutation M134a (`main.py` wires no slot directory into the limit
    holder, `concurrency_configured=False`): a REAL `build_app()` serving
    one real HTTP `GET /v1/capabilities`, stalled inside its own
    synchronous section, holds exactly one `slot-*` file of its own
    `MITATEDB_SLOT_DIR` for the stall's duration (a second, independent
    `flock(LOCK_EX | LOCK_NB)` on it fails), that file is free again once
    the request completes, and the authenticating credential has exactly
    one rate row."""
    from starlette.testclient import TestClient

    import mitatedb_api.cell as cell_module

    main_module = _main_module(platform, r113_app)
    env = _main_env(platform, r113_app)
    slot_dir = Path(env["MITATEDB_SLOT_DIR"])
    credential_id, bearer = _issue(platform, r113_app.app_id)
    entered = threading.Event()
    release = threading.Event()
    original = cell_module.build_capabilities_document

    def _blocking_build_capabilities_document(*args, **kwargs):
        entered.set()
        release.wait(timeout=_WAIT_S)
        return original(*args, **kwargs)

    monkeypatch.setattr(cell_module, "build_capabilities_document", _blocking_build_capabilities_document)
    responses: list[object] = []
    held: list[str] = []
    app = main_module.build_app(env)
    try:
        with TestClient(app) as client:
            def _hold() -> None:
                responses.append(client.get("/v1/capabilities", headers={"authorization": f"Bearer {bearer}"}))

            holder = threading.Thread(target=_hold)
            holder.start()
            try:
                assert entered.wait(timeout=_WAIT_S), "the request never reached its own stalled synchronous section"
                held = _held_slot_names(slot_dir)
            finally:
                release.set()
                holder.join(timeout=_WAIT_S)
    finally:
        pool_module.set_connection_application_name(None)
    assert held, "no slot file was exclusively held during the stalled request"
    assert len(held) == 1, held
    assert responses and responses[0].status_code == 200, responses
    assert not _held_slot_names(slot_dir)
    assert _rate_row_count(platform, credential_id) == 1


def test_http_adapter_session_holds_the_shared_slot_and_writes_a_rate_row() -> None:
    """Completion conditions 134/135 -- the SAME session `conformance-tests`
    drives (`MitateDBHttpConformanceAdapter()`), through its own
    `hold_in_flight` (held after the gate's `__enter__`): exactly one
    `slot-*` file of this session's own `mkdtemp` directory is held for
    the hold's duration and free again after it, and the authenticating
    credential has exactly one rate row. Mutation M134 (the session wires
    no slot directory, declared `concurrency_configured=False`): no slot
    file is held. Mutation M135 (the session wires no PG rate): no rate
    row is written."""
    adapter = _http_adapter_module.MitateDBHttpConformanceAdapter()
    app_id = f"r113s{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        session = adapter.authenticate(handle)
        with adapter.hold_in_flight(session, 1) as entered:
            assert entered == 1
            held = _held_slot_names(adapter._slot_dir)  # noqa: SLF001
            assert held, "no slot file was exclusively held during the held request"
            assert len(held) == 1, held
        assert not _held_slot_names(adapter._slot_dir)  # noqa: SLF001
        assert _adapter_rate_rows(adapter, handle.credential_ref) == 1
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_http_adapter_hold_in_flight_holds_no_platform_pool_connection() -> None:
    """Completion condition 142 -- mutation M142 (the rate borrow is held
    across the hold's own stall point): while `hold_in_flight` holds
    requests after the gate's `__enter__` (authentication, the rate
    statement and the slot all already done), the platform pool lends out
    no connection -- a held request never pins a pooled connection.
    Non-空振り: the held requests genuinely borrowed from that pool."""
    adapter = _http_adapter_module.MitateDBHttpConformanceAdapter()
    app_id = f"r113p{secrets.token_hex(4)}"
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        session = adapter.authenticate(handle)
        before = adapter._read_pool.stats()["acquire_count"]  # noqa: SLF001
        with adapter.hold_in_flight(session, 2) as entered:
            assert entered == 2
            in_use_during_hold = adapter._read_pool._in_use  # noqa: SLF001
        after = adapter._read_pool.stats()["acquire_count"]  # noqa: SLF001
        assert after > before, "the held requests never borrowed from the platform pool (空振り)"
        assert in_use_during_hold == 0, in_use_during_hold
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_http_adapter_isolated_surface_wires_a_separate_slot_directory_and_still_gates() -> None:
    """Completion conditions 143/134/135 (isolated surface): `isolated_
    application_surface()` wires a DIFFERENT `mkdtemp` slot directory than
    the session's own, the held-request observation holds against it, and
    its own credential gets exactly one rate row. Mutation M143 (the
    isolated surface's slots are built on the session's directory) and
    mutation M134i (the isolated surface wires no slot directory): no
    `slot-*` file of the isolated surface's own directory is held.
    Mutation M135i (the isolated surface wires no PG rate): the rate-row
    count goes red."""
    adapter = _http_adapter_module.MitateDBHttpConformanceAdapter()
    try:
        with adapter.isolated_application_surface() as iso:
            assert iso._slot_dir != adapter._slot_dir  # noqa: SLF001
            app_id = f"r113i{secrets.token_hex(4)}"
            iso.provision_application(app_id)
            handle = iso.issue_credential(app_id, "runtime")
            session = iso.authenticate(handle)
            with iso.hold_in_flight(session, 1) as entered:
                assert entered == 1
                held = _held_slot_names(iso._slot_dir)  # noqa: SLF001
                assert len(held) == 1, held
            assert _adapter_rate_rows(iso, handle.credential_ref) == 1
    finally:
        adapter.close()
