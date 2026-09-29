"""R-113 WP-2 (design docs/design/MULTI_PROCESS_WORKER_V0_1.md, work order
docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md WP-2): peer-
local pins for the region (ii) rewiring this WP lands on r2db-api --
`r2db_api.concurrency_slots` (host-shared `concurrency`), the PostgreSQL-
backed `requests_per_minute` rate row (migration `0015`), the 2-strategy
`limit_enforcement` mapping helper, `--workers`/`R2DB_SLOT_DIR` startup
validation, the `--preflight` one-shot, `application_name` tagging, and
the thread-limit-derived pool dimension.

Reuses `test_credential_persistence.py`'s own real-PostgreSQL fixtures
(`platform`/`provisioned_app`/`main_module`/`_main_env`) rather than
duplicating that bootstrap -- the same import-for-fixture-reuse pattern
`test_surfaces_env.py` already establishes.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
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

from test_credential_persistence import (  # noqa: F401 -- imported for fixture re-export
    MIGRATIONS_DIR,
    PEPPER,
    _admin_dsn,
    _DEFAULT_SURFACES_VALUE,
    _dsn_with,
    _fresh_slug,
    _main_env,
    _register_application,
    _run_psql,
    _write_store,
    main_module,
    platform,
    provisioned_app,
)

# WO 裁定 40: completion conditions 76/77's own primary observation goes
# through the SAME session `conformance-tests` itself drives (never a
# hand-built fake) -- `conformance-tests/registry.json`'s own `r2db-api-
# http` entry names this exact module. Mirrors the established `sys.path`
# + import pattern `test_r78_pool_wait_stats.py` already uses for the
# same module.
_CONFORMANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "conformance")
if _CONFORMANCE_DIR not in sys.path:
    sys.path.insert(0, _CONFORMANCE_DIR)
import conformance_adapter_r2db_http as _http_module  # noqa: E402

from test_ops_verify_declarations import (  # noqa: F401 -- imported for fixture re-export
    _declare_control_role_as_the_writer as _verify_declare_control_role_as_the_writer,
    _set_row as _verify_set_row,
    platform as verify_platform,
)

from r2db_api import concurrency_slots
from r2db_api.capabilities_document import build_capabilities_document, resolve_limit_enforcement
from r2db_api.credential_store import PostgresCredentialStore
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits, role_pool_size
from r2db_api.platform_declarations import headroom_lower_bound

RATE_TABLE = "credential_request_rate"


def _rate_fn(schema: str) -> "sql.Composed":
    return sql.SQL("SELECT {}(%s, %s)").format(sql.Identifier(schema, "credential_request_rate_admit"))


def _platform_dsn(platform: types.SimpleNamespace) -> str:
    """`platform.admin_dsn` alone does not name this fixture's own
    throwaway database -- every direct-SQL helper below needs `dbname`
    pinned to it explicitly."""
    return _dsn_with(platform.admin_dsn, dbname=platform.platform_db)


def _declare_control_surface(platform: types.SimpleNamespace) -> None:
    """`test_credential_persistence.py`'s own `platform` fixture seeds
    `surfaces` WITHOUT a `control` key (that file's own comment: kept
    consistent with a real "both surfaces" deployment being data-plane-
    only by default) -- `build_control_app()` unconditionally requires
    one (F-3c). Tests below that build a REAL control-plane app add it
    here first."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({
                    "data": {"base_url": "https://r113-wiring-data.example.invalid/v1"},
                    "control": {"base_url": "https://r113-wiring-control.example.invalid/control/v1"},
                })],
            )
        conn.commit()


def _restore_data_only_surface(platform: types.SimpleNamespace) -> None:
    """Undoes `_declare_control_surface` above -- `platform` is module-
    scoped (shared by every test in this file), so a test that adds a
    `control` surface must remove it again before other tests in this
    same module (which assume the fixture's own default, data-only
    `surfaces`) run."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('surfaces', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps(_DEFAULT_SURFACES_VALUE)],
            )
        conn.commit()


def _issue_credential(platform: types.SimpleNamespace, app_slug: str) -> str:
    """Registers a fresh runtime credential against `app_slug` and returns
    its `credential_id` -- the FK `credential_request_rate.credential_id`
    references."""
    credential_id = "crd_" + secrets.token_hex(8)
    store = _write_store(platform)
    try:
        with store.unit_of_work() as work:
            store.add(credential_id, app_slug, "runtime", "secret-" + secrets.token_hex(4), work=work)
    finally:
        store.close()
    return credential_id


# ===========================================================================
# completion conditions 25-26: migration 0015's own table shape/grants
# ===========================================================================


def test_0015_rate_row_cascades_on_credential_delete(platform: types.SimpleNamespace) -> None:
    """完了条件 25 -- 変異 M25 (`ON DELETE CASCADE` を外す): a rate row
    inserted for a credential is gone once that credential is deleted
    (never left as an orphan FK violation, never surviving)."""
    _register_application(platform, "r113r25", enabled=True)
    credential_id = _issue_credential(platform, "r113r25")
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 100])
            (admitted,) = cur.fetchone()
            assert admitted is True
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(platform.schema, RATE_TABLE)),
            )
            # non-空振り: a row genuinely exists before the delete below.
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                [credential_id],
            )
            (before,) = cur.fetchone()
            assert before == 1
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, "credentials")),
                [credential_id],
            )
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                [credential_id],
            )
            (after,) = cur.fetchone()
        conn.commit()
    assert after == 0


def test_0015_api_role_has_select_insert_update_only_no_delete_or_truncate(platform: types.SimpleNamespace) -> None:
    """完了条件 26 -- 変異 M26 (api role に DELETE を与える): `r2dbsvc_api`
    (this fixture's own `<prefix>_api`) has exactly SELECT/INSERT/UPDATE
    on `credential_request_rate`, never DELETE/TRUNCATE; every OTHER role
    (application runtime/developer, controlplane, auditreader) has
    nothing on it at all."""
    with psycopg.connect(_platform_dsn(platform)) as conn:
        with conn.cursor() as cur:
            def _priv(role: str, privilege: str) -> bool:
                cur.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    [role, f"{platform.schema}.{RATE_TABLE}", privilege],
                )
                return bool(cur.fetchone()[0])

            for privilege in ("SELECT", "INSERT", "UPDATE"):
                assert _priv(platform.api_role, privilege), f"{platform.api_role} lacks {privilege}"
            for privilege in ("DELETE", "TRUNCATE"):
                assert not _priv(platform.api_role, privilege), f"{platform.api_role} unexpectedly has {privilege}"


# ===========================================================================
# completion condition 27: `ops apply-platform-migration` accepts 0015
# (real CLI invocation is peer-local territory too -- structural table
# membership is pinned here; the real subprocess round trip is exercised
# by `test_ops_apply_platform_migration.py`'s own generic closure tests,
# which iterate `ops._PLATFORM_MIGRATION_FILENAMES`)
# ===========================================================================


def test_ops_accepts_0015_as_a_known_platform_migration() -> None:
    """完了条件 27 -- 変異 M27 (`ops.py` の受け付けから 0015 を外す)."""
    import r2db_api.ops as ops

    assert "0015_credential_request_rate.sql" in ops._PLATFORM_MIGRATION_FILENAMES
    assert ops._PLATFORM_MIGRATION_VARIABLE_TABLE["0015_credential_request_rate.sql"] == ()


# ===========================================================================
# completion conditions 28-37: the rate statement itself
# ===========================================================================


def test_pg_rate_admits_up_to_limit_then_denies(platform: types.SimpleNamespace) -> None:
    """完了条件 28 -- 変異 M28 (WHERE を「合計 <= L」に): with the PG rate
    wired, exactly L admissions succeed for one credential, the L+1th is
    denied -- `record_rate_and_check`'s own boolean, the same shape
    `DataService._acquire_rate` reads."""
    _register_application(platform, "r113r28", enabled=True)
    credential_id = _issue_credential(platform, "r113r28")
    store = PostgresCredentialStore(platform.api_dsn, pepper=PEPPER, schema=platform.schema, pool_size=4)
    try:
        limit = 3
        results = [store.record_rate_and_check(credential_id, limit) for _ in range(limit + 1)]
    finally:
        store.close()
    assert results == [True, True, True, False], results


def test_pg_rate_db_failure_maps_to_service_unavailable_503(
    platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完了条件 34 -- 変異 M34 (DB 失敗を素通しする): a PostgreSQL failure
    during the rate statement raises the SAME `SERVICE_UNAVAILABLE`/503 an
    existing DB failure already produces, never a silent pass-through."""
    _register_application(platform, "r113r34", enabled=True)
    credential_id = _issue_credential(platform, "r113r34")
    store = PostgresCredentialStore(platform.api_dsn, pepper=PEPPER, schema=platform.schema, pool_size=4)
    try:
        from r2db_api import credential_store as cs

        def _boom(cur, statement, params):
            raise psycopg.errors.QueryCanceled("synthetic failure for M34")

        monkeypatch.setattr(cs, "_execute", _boom)
        with pytest.raises(FoundationError) as excinfo:
            store.record_rate_and_check(credential_id, 100)
        assert excinfo.value.code == "SERVICE_UNAVAILABLE"
        assert excinfo.value.status == 503
    finally:
        store.close()


def test_pg_rate_concurrent_first_admissions_for_a_new_credential_never_race(platform: types.SimpleNamespace) -> None:
    """完了条件 29 の監査照合 (裁定 22 の差し戻し, F1) -- 変異 M29b (0015
    の分岐を `INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE`
    の再読みから、素の `IF NOT FOUND THEN INSERT` に戻す): a brand-new
    credential (no rate row yet) admits deterministically when the FIRST
    two admissions for it race -- one connection holds its own INSERT
    open (uncommitted), a second connection's own call for the SAME
    credential blocks behind it rather than racing a duplicate `INSERT`
    into a unique-violation 503 (the M29b-reverted branch: both miss the
    uncommitted row, both `INSERT`, the second fails its unique key). The
    first caller commits only once `pg_stat_activity` shows the second
    caller's backend waiting on a lock (bounded), so the two calls always
    overlap."""
    _register_application(platform, "r113r29race", enabled=True)
    credential_id = _issue_credential(platform, "r113r29race")

    conn_a = psycopg.connect(platform.api_dsn)
    conn_a.autocommit = False
    ready = threading.Event()
    hold_release = threading.Event()
    b_connected = threading.Event()
    b_pid: list[int] = []
    result_b: list[object] = []

    def _first_caller() -> None:
        with conn_a.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 100])
            cur.fetchone()
        ready.set()
        hold_release.wait(timeout=5)
        conn_a.commit()

    def _second_caller() -> None:
        ready.wait(timeout=5)
        try:
            with psycopg.connect(platform.api_dsn) as conn_b:
                conn_b.autocommit = True
                b_pid.append(conn_b.info.backend_pid)
                b_connected.set()
                with conn_b.cursor() as cur:
                    cur.execute(_rate_fn(platform.schema), [credential_id, 100])
                    (admitted,) = cur.fetchone()
            result_b.append(admitted)
        except Exception as exc:  # captured for the assertion below, never re-raised on the wrong thread
            result_b.append(exc)

    t1 = threading.Thread(target=_first_caller)
    t2 = threading.Thread(target=_second_caller)
    t1.start()
    assert ready.wait(timeout=5), "the first caller never reached its own uncommitted INSERT"
    t2.start()
    try:
        assert b_connected.wait(timeout=5), "the second caller never connected"
        assert _wait_until_backend_waits_on_a_lock(_platform_dsn(platform), b_pid[0], 5.0), (
            "the second caller never waited on the first caller's uncommitted row"
        )
    finally:
        hold_release.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    conn_a.close()

    assert result_b, "the second admission's own thread never returned -- non-空振り guard"
    assert result_b[0] is True, f"second concurrent first-admission must be cleanly admitted, not an exception: {result_b[0]!r}"
    _base_after, counts_after = _read_rate_row(platform, credential_id)
    assert sum(counts_after) == 2, "both concurrent first admissions for this credential must be counted exactly once each"


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


def test_rate_call_is_lexically_outside_the_authentication_borrow() -> None:
    """完了条件 35 (AST pin) -- 変異 M35 (rate の呼び出しを認証の借用の内側
    へ): `DataService._slot`'s own `self._acquire_rate(canonical)` call is
    a direct statement of that method's body, never nested inside any
    `with` block (in particular, never inside the `assert_active` borrow
    `self._check(context)` performs)."""
    import ast
    import inspect
    import textwrap

    from r2db_api import service as service_module

    source = textwrap.dedent(inspect.getsource(service_module.DataService._slot))
    tree = ast.parse(source)
    method = tree.body[0]
    assert isinstance(method, ast.FunctionDef)

    top_level_calls = []
    for stmt in method.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_acquire_rate":
                # `stmt` itself must not be (or be nested inside) an `ast.With`.
                top_level_calls.append(stmt)
    assert top_level_calls, "no self._acquire_rate(...) call found in _slot's source"
    for stmt in top_level_calls:
        assert not isinstance(stmt, ast.With), f"_acquire_rate call sits inside a `with` statement: {ast.dump(stmt)}"


def test_record_rate_and_check_borrows_and_executes_exactly_once() -> None:
    """完了条件 35 後半 (AST pin, レビュー F6 の (h)): `PostgresCredentialStore.
    record_rate_and_check`'s own body borrows `self._pool.connection()`
    exactly ONCE and runs `_execute(...)` exactly ONCE -- a single round
    trip per call (design D-3 (1)'s own "1 文"), never two statements on
    the same borrow and never a second, nested borrow."""
    import ast
    import inspect
    import textwrap

    from r2db_api import credential_store as credential_store_module

    source = textwrap.dedent(inspect.getsource(credential_store_module.PostgresCredentialStore.record_rate_and_check))
    tree = ast.parse(source)
    method = tree.body[0]
    assert isinstance(method, ast.FunctionDef)

    pool_borrow_calls = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connection"
        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "_pool"
    ]
    execute_calls = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_execute"
    ]
    assert len(pool_borrow_calls) == 1, f"expected exactly 1 self._pool.connection() borrow, found {len(pool_borrow_calls)}"
    assert len(execute_calls) == 1, f"expected exactly 1 _execute(...) call, found {len(execute_calls)}"


def test_denied_authentication_never_writes_a_rate_row(platform: types.SimpleNamespace) -> None:
    """完了条件 36 -- 変異 M36 (rate を認証の前に数える): a request with an
    invalid credential never reaches `_acquire_rate` at all -- no rate row
    is ever created for a credential_id that never successfully
    authenticated."""
    from r2db_api.auth import AuthContext
    from r2db_api.errors import FoundationError as _FE
    from r2db_api.service import DataService

    _register_application(platform, "r113r36", enabled=True)
    real_credential_id = _issue_credential(platform, "r113r36")
    never_used_credential_id = "crd_" + secrets.token_hex(8)  # never added to `credentials`
    store = PostgresCredentialStore(platform.api_dsn, pepper=PEPPER, schema=platform.schema, pool_size=4)
    try:
        service = DataService(store, rate=store)
        with pytest.raises(_FE) as excinfo:
            service.capabilities(AuthContext(never_used_credential_id, "r113r36", "runtime"))
        assert excinfo.value.code == "AUTH_INVALID"
        with psycopg.connect(_platform_dsn(platform)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                    [never_used_credential_id],
                )
                (count,) = cur.fetchone()
        assert count == 0
        # non-空振り: the real credential id (successfully authenticated
        # elsewhere in this test module) DOES get a row once admitted --
        # proving this accessor genuinely observes real rows, not an
        # always-empty table.
        assert store.record_rate_and_check(real_credential_id, 100) is True
    finally:
        store.close()


def test_denied_authentication_of_a_revoked_registered_credential_never_writes_a_rate_row(
    platform: types.SimpleNamespace,
) -> None:
    """完了条件 36 の補強 (レビュー F6 (g)): `test_denied_authentication_
    never_writes_a_rate_row` above uses a credential_id that never exists
    in `credentials` at all, so a mutation moving the rate call BEFORE
    authentication (M36) would already turn that test red for the WRONG
    reason -- the rate row's own FK to `credentials` rejects the INSERT
    (a different failure mode, never `_acquire_rate` genuinely not being
    reached). This uses a REAL, REGISTERED credential that has been
    revoked (the FK is satisfied; only `assert_active` denies it), so a
    successful INSERT is genuinely possible and its absence is what this
    test observes.

    変異 M35c (`assert_active` の借用の内側で rate を数える): `store` holds
    ONE pooled connection (`pool_size=1`, acquire timeout 2 s), so the
    authentication borrow and the rate borrow can only run one after the
    other -- a rate call nested inside the authentication borrow waits
    out the acquire timeout and the request fails with a 503 instead of
    `AUTH_REVOKED`; the sibling
    credential below is admitted through `DataService._slot` itself (the
    real `_check` then `_acquire_rate` order) on that same single-
    connection pool."""
    from r2db_api.auth import AuthContext
    from r2db_api.errors import FoundationError as _FE
    from r2db_api.service import DataService

    _register_application(platform, "r113r36rev", enabled=True)
    revoked_credential_id = _issue_credential(platform, "r113r36rev")
    # `set_state` (a write against `credentials`) needs the control role's
    # own pool -- the `api` role (`store`, below) has only SELECT/INSERT/
    # UPDATE on the rate table and SELECT on `credentials`, matching
    # least privilege (`test_credential_persistence.py`'s own `_write_
    # store`/`_read_store` split).
    revoker = PostgresCredentialStore(platform.control_dsn, pepper=PEPPER, schema=platform.schema, pool_size=2)
    try:
        with revoker.unit_of_work() as work:
            revoker.set_state(revoked_credential_id, revoked=True, work=work)
    finally:
        revoker.close()
    store = PostgresCredentialStore(platform.api_dsn, pepper=PEPPER, schema=platform.schema, pool_size=1, acquire_timeout=2.0)
    try:
        service = DataService(store, rate=store, initial_cells={"r113r36rev": object()})
        with pytest.raises(_FE) as excinfo:
            service.capabilities(AuthContext(revoked_credential_id, "r113r36rev", "runtime"))
        assert excinfo.value.code == "AUTH_REVOKED"
        with psycopg.connect(_platform_dsn(platform)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                    [revoked_credential_id],
                )
                (count,) = cur.fetchone()
        assert count == 0
        # non-空振り: a SIBLING credential registered against the SAME
        # application (so the same FK target exists) but never revoked
        # genuinely IS rate-table-eligible -- the FK the first assertion
        # above relied on is real, not incidentally always-satisfiable.
        sibling_credential_id = _issue_credential(platform, "r113r36rev")
        with service._slot(AuthContext(sibling_credential_id, "r113r36rev", "runtime")) as canonical:  # noqa: SLF001
            assert canonical.credential_id == sibling_credential_id
        with psycopg.connect(_platform_dsn(platform)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                    [sibling_credential_id],
                )
                (sibling_count,) = cur.fetchone()
        assert sibling_count == 1
    finally:
        store.close()


def _read_db_now_s(platform: types.SimpleNamespace) -> int:
    """The DB's OWN current second (`clock_timestamp()`, same reading the
    admission function itself uses) -- 差し戻し1b item4 (F10): every
    second-boundary-sensitive test below anchors its own arithmetic to
    THIS, never `time.time()` (a separate clock read, racing the DB's own
    by however long the round trip to set the row up takes)."""
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
            (now_s,) = cur.fetchone()
    return int(now_s)


def _prime_and_ring_length(platform: types.SimpleNamespace, credential_id: str) -> int:
    """Primes `credential_id`'s own row through the SAME admission
    function (`credential_request_rate_admit`) the tests below exercise
    directly -- never a raw INSERT hardcoded to a specific ring length
    (差し戻し1b item2) -- then returns the row's CURRENT `counts` array
    length, read back, never assumed to be 61: a mutation that changes
    the ring's own length (M32) is reflected automatically, so this
    helper's own row-creation step never trips a tightened `CHECK`."""
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 2_000_000_000])
    _base_s, counts = _read_rate_row(platform, credential_id)
    return len(counts)


def _write_rate_row(platform: types.SimpleNamespace, credential_id: str, *, base_s: int, counts: list[int]) -> None:
    """Overwrites an ALREADY-EXISTING row (primed by `_prime_and_ring_
    length` above) with an exact `base_s`/`counts` -- never the INSERT
    itself, so this never needs to know or assume the ring length."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET base_s = %s, counts = %s WHERE credential_id = %s").format(
                    sql.Identifier(platform.schema, RATE_TABLE)
                ),
                [base_s, counts, credential_id],
            )
        conn.commit()


def _reset_rate_row(
    platform: types.SimpleNamespace, credential_id: str, *, base_s: int, at: dict[int, int] | None = None, fill: int = 0
) -> int:
    """差し戻し1b item2: primes the row via `_prime_and_ring_length` (the
    admission function itself, never a raw INSERT), then overwrites it
    with `base_s` and a `counts` array derived from the CURRENT ring
    length -- never a literal `61`. Returns the ring length used. `at`
    maps a ring OFFSET (taken mod the actual, current length) to the
    count placed there; every other position is `fill`."""
    n = _prime_and_ring_length(platform, credential_id)
    counts = [fill] * n
    for offset, value in (at or {}).items():
        counts[offset % n] = value
    _write_rate_row(platform, credential_id, base_s=base_s, counts=counts)
    return n


def _read_rate_row(platform: types.SimpleNamespace, credential_id: str) -> tuple[int, list[int]]:
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT base_s, counts FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                [credential_id],
            )
            row = cur.fetchone()
    assert row is not None
    return row[0], list(row[1])


def test_rate_ring_base_s_never_rewinds_after_a_lock_wait(platform: types.SimpleNamespace) -> None:
    """完了条件 30/37 -- 変異 M30 (`GREATEST` を外す): a row whose `base_s`
    is already at a NEWER second than the call's own clock read (as if
    this call's own request had waited behind the row lock while a
    newer-second request already committed) never rewinds `base_s`
    backward, and the total admitted never exceeds the limit."""
    _register_application(platform, "r113r30", enabled=True)
    credential_id = _issue_credential(platform, "r113r30")
    now_s = int(time.time())
    newer_base = now_s + 5  # comfortably future -- no second-boundary risk
    _reset_rate_row(platform, credential_id, base_s=newer_base, at={newer_base: 1})
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 2])
            (admitted,) = cur.fetchone()
    assert admitted is True
    base_after, counts_after = _read_rate_row(platform, credential_id)
    assert base_after == newer_base, "base_s must never rewind below its own already-stored value"
    assert sum(counts_after) == 2


def test_rate_ring_stale_base_s_beyond_61_seconds_resets_from_zero(platform: types.SimpleNamespace) -> None:
    """完了条件 31 -- 変異 M31 (shift >= 61 の全 0 化の本体を `NULL;` に:
    F6 の等価変異指摘 -- `IF` の条件自体を外すのではなく分岐の本体を no-op
    にする、ELSIF の loop が shift=61 では二度と走らない no-op のみでは殺
    せないため): a row whose `base_s` is 61+ seconds stale is treated as
    fully expired -- the next admission starts counting from a clean
    slate."""
    _register_application(platform, "r113r31", enabled=True)
    credential_id = _issue_credential(platform, "r113r31")
    now_s = int(time.time())
    stale_base = now_s - 120  # comfortably past -- no second-boundary risk
    _reset_rate_row(platform, credential_id, base_s=stale_base, fill=61)  # deliberately "full" -- would deny if not reset
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 5])
            (admitted,) = cur.fetchone()
    assert admitted is True, "a row stale by >= 61 s must reset to 0 and admit"
    _base_after, counts_after = _read_rate_row(platform, credential_id)
    assert sum(counts_after) == 1


def test_rate_ring_full_count_60_seconds_ago_still_denies(platform: types.SimpleNamespace) -> None:
    """完了条件 32 (int[61], 裁定34) -- 変異 M32 (関数本体の `61` を `60`
    に揃えて下げる: CHECK、両方の `array_fill`、`IF`/`LEAST` の閾値、両方の
    `% 61`、loop の上限): a row with the declared limit already reached at
    exactly 60 seconds before the ADMIT CALL's own DB-side second denies
    that call -- a ring shrunk to `int[60]` wraps its own zeroing loop
    exactly once around that position and wrongly admits instead.

    差し戻し1b item2: `_reset_rate_row` never assumes the ring is 61 long
    (it primes the row through `credential_request_rate_admit` itself and
    reads the length back), so M32's own tightened `CHECK` never rejects
    this row's own setup -- the observation is the ring math, not a setup
    `CheckViolation` (F6's 代理 finding).
    差し戻し1b item4 (F10): retries up to 3 times, anchored to the DB's
    OWN clock (`_read_db_now_s`), detected via the row's own `base_s`
    after the call -- a call landing one second later than assumed is
    redone rather than flaking."""
    _register_application(platform, "r113r32", enabled=True)
    credential_id = _issue_credential(platform, "r113r32")
    admitted = None
    for _attempt in range(3):
        db_now_s = _read_db_now_s(platform)
        old_base = db_now_s - 60
        _reset_rate_row(platform, credential_id, base_s=old_base, at={old_base: 5})
        with psycopg.connect(platform.api_dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(_rate_fn(platform.schema), [credential_id, 5])
                (admitted,) = cur.fetchone()
        # bracketing check (never the row's own `base_s`: a DENIED call
        # persists NOTHING at all, so `base_s` legitimately never advances
        # on the very outcome this test asserts -- checking it here would
        # make a correctly-denied call look like a missed second, always).
        db_now_s_after = _read_db_now_s(platform)
        if db_now_s_after == db_now_s:
            break
    else:
        pytest.fail("the setup+call sequence never landed within one DB second after 3 attempts (差し戻し1b item4 flake guard)")
    assert admitted is False, "a full count 60s ago must still be inside the 61-slot window and deny"


def test_rate_ring_shift_zeroes_only_the_shifted_range(platform: types.SimpleNamespace) -> None:
    """完了条件 33 (監督裁定3 の環) -- 変異 M33 (0 にする範囲を base_s ..
    base_s+shift-1 にずらす): a row with known counts at every position,
    `base_s` moved forward by a known `k` seconds, zeroes exactly the `k`
    positions `(base_s+1 .. base_s+k) mod n` (`n` = the CURRENT ring
    length, read back from the row `_prime_and_ring_length` itself just
    created -- 差し戻し1b item2, never a literal 61) -- every other
    position's own count survives untouched.

    差し戻し1b item4 (F10): same second-boundary retry guard as 完了条件
    32 above."""
    _register_application(platform, "r113r33", enabled=True)
    credential_id = _issue_credential(platform, "r113r33")
    k = 5
    admitted = base_after = counts_after = counts = old_base = n = None
    for _attempt in range(3):
        db_now_s = _read_db_now_s(platform)
        old_base = db_now_s - k
        n = _prime_and_ring_length(platform, credential_id)
        counts = [i + 1 for i in range(n)]  # every position has a distinct, known, non-zero value
        _write_rate_row(platform, credential_id, base_s=old_base, counts=counts)
        with psycopg.connect(platform.api_dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(_rate_fn(platform.schema), [credential_id, 10_000])
                (admitted,) = cur.fetchone()
        base_after, counts_after = _read_rate_row(platform, credential_id)
        # bracketing check (never `base_after` alone -- consistent with
        # 完了条件 32's own guard immediately above, so both tests share
        # one robust shape rather than depending on the row's own
        # post-call state, which differs by outcome).
        db_now_s_after = _read_db_now_s(platform)
        if db_now_s_after == db_now_s:
            break
    else:
        pytest.fail("the setup+call sequence never landed within one DB second after 3 attempts (差し戻し1b item4 flake guard)")
    assert admitted is True
    expected_zeroed = {(old_base + i) % n for i in range(1, k + 1)}
    incremented_idx = base_after % n
    for idx in range(n):
        if idx == incremented_idx:
            # the incremented position: `(zeroed if it was in range else its
            # own original value) + 1` -- checked separately below, never
            # folded into either branch here (it is always the LAST
            # position of the zeroed range when shift < n, so it would
            # otherwise wrongly be asserted `== 0`).
            continue
        if idx in expected_zeroed:
            assert counts_after[idx] == 0, f"position {idx} should have been zeroed"
        else:
            assert counts_after[idx] == counts[idx], f"position {idx} must survive untouched"
    incremented_base = 0 if incremented_idx in expected_zeroed else counts[incremented_idx]
    assert counts_after[incremented_idx] == incremented_base + 1, (
        f"incremented position {incremented_idx} must be its own (possibly zeroed) prior value + 1"
    )


# ===========================================================================
# completion conditions 38-53: `r2db_api.concurrency_slots`
# ===========================================================================


def test_slot_dir_env_missing_raises_naming_the_variable(main_module: types.ModuleType) -> None:
    """完了条件 38 -- R2DB_SLOT_DIR 未設定なら変数名を含む例外."""
    with pytest.raises(RuntimeError, match="R2DB_SLOT_DIR"):
        main_module._require_slot_dir({}, "R2DB_SLOT_DIR")
    with pytest.raises(RuntimeError, match="R2DB_SLOT_DIR"):
        main_module._require_slot_dir({"R2DB_SLOT_DIR": ""}, "R2DB_SLOT_DIR")


def test_slot_dir_missing_path_raises(tmp_path: Path) -> None:
    """完了条件 39 -- 変異 なし (監査照合扱いだが直接検査): a slot
    directory that does not exist on disk fails `check_slot_directory`,
    never silently created."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(concurrency_slots.SlotDirectoryError):
        concurrency_slots.check_slot_directory(missing)
    assert not missing.exists()


def test_slot_dir_wrong_owner_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件 40 -- 変異 M40 (所有者の検査を外す)."""
    target = tmp_path / "slots"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(concurrency_slots.os, "geteuid", lambda: target.stat().st_uid + 1)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="uid"):
        concurrency_slots.check_slot_directory(target)


def test_slot_dir_wrong_mode_raises(tmp_path: Path) -> None:
    """完了条件 41 -- 変異 M41 (mode の検査を外す)."""
    target = tmp_path / "slots"
    target.mkdir(mode=0o755)
    os.chmod(target, 0o755)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="0700|mode"):
        concurrency_slots.check_slot_directory(target)


def test_slot_file_symlink_open_fails(tmp_path: Path) -> None:
    """完了条件 42 -- 変異 M42 (`O_NOFOLLOW` を外す): a `slot-0` path that
    is a symlink is refused at open() time (`SlotBackendError`), never
    silently followed."""
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("")
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    (slot_dir / "slot-0").symlink_to(real_target)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError):
        with slots.acquire(1):
            pass


def test_slot_file_created_with_mode_0600(tmp_path: Path) -> None:
    """完了条件 43 -- 変異 M43 (mode 0644 で作る)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with slots.acquire(1):
        mode = stat.S_IMODE((slot_dir / "slot-0").stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_slot_fd_is_close_on_exec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件 44 -- 変異 M44 (`O_CLOEXEC` を外す): the REAL fd `Host
    SharedConcurrencySlots.acquire()` opens (never a second, independent
    `os.open()` call of this test's own) carries `O_CLOEXEC` -- a slot fd
    held during a `with` block must not survive into a forked+exec'd
    child. `os.open` is spied on (never replaced -- the real call still
    runs) so this observes the ACTUAL flags `_OPEN_FLAGS` passes."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    captured_flags: list[int] = []
    original_open = os.open

    def _spy_open(path, flags, mode=0o777):
        if os.path.basename(path) == "slot-0":
            captured_flags.append(flags)
        return original_open(path, flags, mode)

    monkeypatch.setattr(concurrency_slots.os, "open", _spy_open)
    with slots.acquire(1):
        pass
    assert captured_flags, "no os.open call of slot-0 observed (空振り)"
    assert captured_flags[0] & os.O_CLOEXEC, f"slot fd was opened without O_CLOEXEC: {oct(captured_flags[0])}"


def test_flock_unexpected_errno_maps_to_backend_error_not_admitted_or_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完了条件 45 -- 変異 M45 (どの errno も「塞がっている」と読む): the
    `slot-0` lock returns `EPERM` (injected; the `scan` lock runs for
    real) -- `SlotBackendError` naming the slot file."""
    import errno as errno_module
    import fcntl

    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    real_flock = fcntl.flock
    slot_attempts: list[int] = []

    def _fake_flock(fd, op):
        slot_path = slot_dir / "slot-0"
        if op & fcntl.LOCK_NB and slot_path.exists() and os.fstat(fd).st_ino == os.stat(slot_path).st_ino:
            slot_attempts.append(op)
            raise OSError(errno_module.EPERM, "synthetic EPERM for M45")
        return real_flock(fd, op)

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _fake_flock)
    with pytest.raises(concurrency_slots.SlotBackendError, match="slot file"):
        with slots.acquire(1):
            pass
    assert slot_attempts, "no slot-0 lock attempt observed (空振り)"


def test_selfcheck_detects_a_faked_flock_that_never_excludes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件 46 -- 変異 M46 (自己検査を外す)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)

    real_flock = concurrency_slots.fcntl.flock
    calls = {"n": 0}

    def _fake_flock(fd, op):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_flock(fd, op)
        return None  # second lock "succeeds" -- a faked/no-op flock

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _fake_flock)
    with pytest.raises(concurrency_slots.SlotDirectoryError, match="NOT rejected"):
        concurrency_slots.selfcheck_slot_locking(slot_dir)


def test_selfcheck_uses_the_dedicated_selfcheck_file_never_slot_0(tmp_path: Path) -> None:
    """完了条件 47 -- 変異 M47 (自己検査に `slot-0` を使う)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    concurrency_slots.selfcheck_slot_locking(slot_dir)
    assert not (slot_dir / "slot-0").exists(), "selfcheck must never touch slot-0"
    assert (slot_dir / concurrency_slots.SELFCHECK_FILENAME).exists()


def test_two_threads_l_c_1_second_is_refused(tmp_path: Path) -> None:
    """完了条件 48 -- 変異 M48 (fd を process 内で共有する): two threads in
    the SAME process, `limit=1` -- the first holds the slot, the second is
    refused (`LimitExceeded`), never both admitted."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    first_holds = threading.Event()
    release = threading.Event()
    second_outcome: list[bool] = []

    def _holder() -> None:
        with slots.acquire(1):
            first_holds.set()
            release.wait(timeout=5.0)

    def _second() -> None:
        first_holds.wait(timeout=5.0)
        try:
            with slots.acquire(1):
                second_outcome.append(True)
        except concurrency_slots.LimitExceeded:
            second_outcome.append(False)

    t1 = threading.Thread(target=_holder)
    t2 = threading.Thread(target=_second)
    t1.start()
    t2.start()
    t2.join(timeout=5.0)
    release.set()
    t1.join(timeout=5.0)
    assert second_outcome == [False], second_outcome


def test_slot_released_even_when_the_body_raises(tmp_path: Path) -> None:
    """完了条件 49 -- 変異 M49 (例外経路で close しない)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(ValueError):
        with slots.acquire(1):
            raise ValueError("synthetic body failure")
    # If the slot were not released, this second acquisition would raise
    # `LimitExceeded` instead of succeeding.
    with slots.acquire(1):
        pass


def test_rejected_candidate_fds_do_not_accumulate(tmp_path: Path) -> None:
    """完了条件 50 -- 変異 M50 (拒否した fd を閉じない): when every slot
    among `limit` is already held, the open-fd count after the refusal
    equals the count before it (every rejected candidate was closed)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    limit = 4
    holders = [slots.acquire(limit) for _ in range(limit)]
    entered = [h.__enter__() for h in holders]
    try:
        before = _open_fd_count()
        with pytest.raises(concurrency_slots.LimitExceeded):
            with slots.acquire(limit):
                pass
        after = _open_fd_count()
        assert after == before, f"open fd count grew from {before} to {after} after a refusal"
    finally:
        for h in holders:
            h.__exit__(None, None, None)


def _open_fd_count() -> int:
    return len(os.listdir(f"/proc/self/fd")) if os.path.isdir("/proc/self/fd") else len(os.listdir("/dev/fd"))


def test_slot_search_start_point_follows_the_injected_random_source(tmp_path: Path) -> None:
    """完了条件 51 -- 変異 M51 (始点を 0 に固定): the search start point is
    whatever the injected `random_below` callable returns, observed
    directly (never hardcoded to 0)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 3)
    with slots.acquire(8):
        assert (slot_dir / "slot-3").exists()
        assert not (slot_dir / "slot-0").exists()


def test_full_slots_refuse_immediately_never_blocking(tmp_path: Path) -> None:
    """完了条件 52 -- 変異 M52 (`LOCK_NB` を外す): with every slot already
    held, a further `acquire()` call refuses in well under a second --
    proving it never *waits* on the lock (an `LOCK_NB`-less `flock()`
    would block until the holder releases -- which, held by the SAME
    process/thread here, never happens at all: a real self-deadlock, not
    merely "seconds later"). The second attempt therefore runs in a
    SEPARATE thread, bounded by `join(timeout=...)`, rather than being
    called directly on this test's own thread: a direct call under the
    mutated (`LOCK_NB`-less) code hangs this test permanently instead of
    failing fast."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
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
        assert not thread.is_alive(), (
            f"the second acquire() call was still blocked after {elapsed}s -- acquire() must never wait "
            f"on a held lock"
        )
    assert outcome == ["refused"], outcome
    assert elapsed < 1.0, f"refusal took {elapsed}s -- acquire() must never wait on a held lock"


def test_one_http_request_holds_exactly_one_slot(tmp_path: Path) -> None:
    """完了条件 53 -- 変異 M53 (1 要求で slot を 2 回取る): `DataService`'s
    own pre-auth (`acquire_concurrency_slot`) and post-auth
    (`_slot(concurrency_precharged=True)`) paths together take the slot
    exactly ONCE per request -- with `limit=1`, ONE simulated request
    (pre-charge, then the precharged post-auth path) succeeds start to
    finish without ever seeing `LIMIT_EXCEEDED` from a second, spurious
    acquisition of its own."""
    from r2db_api.auth import AuthContext
    from r2db_api.service import DataService

    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)

    class _FakeCredentials:
        def assert_active(self, context):
            return context

    service = DataService(_FakeCredentials(), limits=ResourceLimits(concurrency=1), initial_cells={"app": object()}, concurrency_slots=slots, concurrency_configured=True)
    context = AuthContext("crd", "app", "runtime")
    with service.acquire_concurrency_slot():
        with service._slot(context, concurrency_precharged=True) as canonical:  # noqa: SLF001
            assert canonical is context


def test_slot_is_reacquirable_after_a_holding_child_process_is_sigkilled_and_after_a_plain_close(tmp_path: Path) -> None:
    """完了条件 54 (監督裁定 6, 監査照合 -- WO §4.3's own "29・37・54・67・
    73・75・78-82: 監査照合" row, no paired mutation): design D-3 (2)'s own
    crash-safety claim ("process が死ねば kernel が解放する"), confirmed on
    THIS development machine -- a CHILD process holds `slot-0` (writes a
    ready-marker file once held, then sleeps); the PARENT observes
    `LimitExceeded` while the child holds it; `proc.kill()` (SIGKILL)
    followed by a TIMED `proc.wait()` (every process-wait below carries a
    timeout, never unbounded); the PARENT then re-acquires the SAME slot.
    Separately, an ordinary `with ... .acquire(1):` release (a plain
    `close()`, no process death at all) is immediately re-acquirable too.

    `sysconfig.get_config_var("HAVE_FLOCK")`'s own value on this
    development machine (whether `fcntl.flock` here calls the real
    `flock(2)` syscall directly rather than an `fcntl()`-based emulation,
    design §1.4 (4)/§9 (r)) is reported in the report body, not this
    docstring."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    ready_path = tmp_path / "child_ready"
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    child_src = (
        "import sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {src_dir!r})\n"
        "from r2db_api import concurrency_slots\n"
        f"slots = concurrency_slots.HostSharedConcurrencySlots(Path({str(slot_dir)!r}))\n"
        "with slots.acquire(1):\n"
        f"    open({str(ready_path)!r}, 'w').close()\n"
        "    time.sleep(30)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        deadline = time.time() + 10.0
        while not ready_path.exists():
            assert time.time() < deadline, "child process never signalled it holds the slot"
            time.sleep(0.05)

        slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
        with pytest.raises(concurrency_slots.LimitExceeded):
            with slots.acquire(1):
                pass  # unreachable -- the child still holds slot-0

        proc.kill()  # SIGKILL
        proc.wait(timeout=10.0)

        # crash safety: the kernel released the child's flock on process death.
        with slots.acquire(1):
            pass

        # a plain close() (no process death at all) is also immediately re-acquirable.
        with slots.acquire(1):
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10.0)


# ===========================================================================
# the `scan` lock that serialises every slot search on this host
# (design 裁定 43)
# ===========================================================================

#: every wait in the `scan` tests below is bounded by this many seconds.
_SCAN_WAIT_S = 10.0

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
    observe and to stop S; every wait is bounded by `_SCAN_WAIT_S`."""
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
                    ctl.s_continue.wait(timeout=_SCAN_WAIT_S)
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
                ctl.finish.wait(timeout=_SCAN_WAIT_S)
        except concurrency_slots.LimitExceeded:
            ctl.s_outcome.append("refused")
        except Exception as exc:  # recorded for the caller's own assertion
            ctl.s_outcome.append(repr(exc))
        finally:
            ctl.s_done.set()

    s_thread = threading.Thread(target=_s, daemon=True)
    s_thread.start()
    try:
        assert ctl.s_saw_held.wait(timeout=_SCAN_WAIT_S), "S never reached slot-0 while X held it (空振り)"
        x_hold.__exit__(None, None, None)
        x_open = False
        yield ctl
    finally:
        ctl.s_continue.set()
        ctl.finish.set()
        if x_open:
            x_hold.__exit__(None, None, None)
        s_thread.join(timeout=_SCAN_WAIT_S)


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
    """裁定 43 (s1-a) -- 変異 Ms1 (`scan` の lock を外す) と Ms1f (`scan` の
    fd を process で 1 本開いて使い回す): L = 2. X holds `slot-0`; S's scan
    sees `slot-0` held and is stopped there; X releases `slot-0`; Y, a
    second thread of THIS process whose search starts at `slot-1`, starts
    acquiring. Y must not get a slot while S's scan is stopped (it waits
    on `scan`); once S resumes, S is admitted (`slot-1`) -- never
    `LimitExceeded`, since at most one slot was held at any instant -- and
    Y is admitted after it (`slot-0`). Without the `scan` lock (Ms1), or
    with one `scan` fd shared by every thread of the process (Ms1f, where
    a second `LOCK_EX` on the same open file description succeeds), Y
    takes `slot-1` during S's scan and S is refused."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", _SCAN_WAIT_S)
    with _scan_paused_after_seeing_slot_0_held(slot_dir, monkeypatch) as ctl:
        y_acquired = threading.Event()

        y_outcome: list[str] = []

        def _y() -> None:
            ctl.roles[threading.get_ident()] = "Y"
            try:
                with concurrency_slots.HostSharedConcurrencySlots(slot_dir, random_below=lambda n: 1).acquire(_RACE_LIMIT):
                    y_acquired.set()
                    ctl.y_progressed.set()
                    ctl.finish.wait(timeout=_SCAN_WAIT_S)
                y_outcome.append("acquired")
            except Exception as exc:  # recorded for the assertion below
                y_outcome.append(repr(exc))
            finally:
                ctl.y_progressed.set()

        y_thread = threading.Thread(target=_y, daemon=True)
        y_thread.start()
        try:
            assert ctl.y_progressed.wait(timeout=_SCAN_WAIT_S), "Y never reached the scan lock nor a slot (空振り)"
            y_during_scan = y_acquired.is_set()
            ctl.s_continue.set()
            assert ctl.s_done.wait(timeout=_SCAN_WAIT_S), "S never finished its scan"
            y_after_scan = y_acquired.wait(timeout=_SCAN_WAIT_S)
        finally:
            ctl.finish.set()
            y_thread.join(timeout=_SCAN_WAIT_S)
    violations = _race_violations(ctl.s_outcome, y_during_scan, y_after_scan)
    assert not violations, (violations, y_outcome)


def test_scan_serialises_another_process_behind_a_paused_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """裁定 43 (s1-b) -- 変異 Ms1p (`scan` の file lock を process 内の
    `threading.Lock` に置き換える): the same race as the test above, with
    Y in a SECOND process (`multiprocessing` `spawn`; its progress and its
    admission are `multiprocessing.Event`s). A process-local lock excludes
    only this process' own threads, so under Ms1p Y takes `slot-1` during
    S's stopped scan and S is refused. The child reports its own
    `concurrency_slots.__file__`, checked equal to this process' own (the
    child ran this tree's module)."""
    import multiprocessing

    import slot_scan_child

    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", _SCAN_WAIT_S)
    context = multiprocessing.get_context("spawn")
    progressed, acquired, release = context.Event(), context.Event(), context.Event()
    report = context.Queue()
    messages: dict[str, str] = {}
    with _scan_paused_after_seeing_slot_0_held(slot_dir, monkeypatch) as ctl:
        proc = context.Process(
            target=slot_scan_child.acquire_after_scan,
            args=(str(slot_dir), _RACE_LIMIT, 1, _SCAN_WAIT_S, progressed, acquired, release, report),
            daemon=True,
        )
        proc.start()
        try:
            assert progressed.wait(timeout=3 * _SCAN_WAIT_S), "the second process never reached the scan lock nor a slot (空振り)"
            y_during_scan = acquired.is_set()
            ctl.s_continue.set()
            assert ctl.s_done.wait(timeout=_SCAN_WAIT_S), "S never finished its scan"
            y_after_scan = acquired.wait(timeout=_SCAN_WAIT_S)
            release.set()
            for _ in range(2):
                key, value = report.get(timeout=_SCAN_WAIT_S)
                messages[key] = value
        finally:
            release.set()
            proc.join(timeout=_SCAN_WAIT_S)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=_SCAN_WAIT_S)
    assert messages.get("module") == os.path.realpath(concurrency_slots.__file__), messages
    violations = _race_violations(ctl.s_outcome, y_during_scan, y_after_scan)
    assert not violations, (violations, messages.get("outcome"))


def test_scan_is_closed_before_the_with_body_so_another_acquisition_succeeds_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """裁定 43 (s7) -- 変異 Ms7 (`scan` の close を `yield` の後に移す):
    while an acquisition holds its slot (inside its own `with` body),
    another acquisition of the same directory succeeds in far less than
    the `scan` deadline -- `scan` was already closed when the first
    acquisition's body began. Under Ms7 the first acquisition still holds
    `scan`, so the second waits out the (here 0.5 s) deadline and raises
    `SlotBackendError`."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
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
    """裁定 43 (s2) -- 変異 Ms2 (期限切れを `LimitExceeded` にする) と Ms2n
    (期限を無くす): another holder keeps `scan` for longer than the
    deadline (set to 0.2 s here through the module constant). `acquire`
    returns within a bounded wait, raising `SlotBackendError` whose message
    names the expired `scan` deadline, after at least the deadline; the
    same failure reaches `DataService.acquire_concurrency_slot()`'s own
    caller as `SERVICE_UNAVAILABLE`/503 -- never `LIMIT_EXCEEDED`, never an
    admission. Under Ms2n the call has not returned when the bounded wait
    ends; the holder is released in `finally`, so the thread then ends."""
    from r2db_api.errors import FoundationError as _FE
    from r2db_api.service import DataService

    class _FakeCredentials:
        def assert_active(self, context):
            return context

    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.2)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    service = DataService(
        _FakeCredentials(), limits=ResourceLimits(concurrency=1), initial_cells={"app": object()},
        concurrency_slots=slots, concurrency_configured=True,
    )

    def _through_the_caller() -> str:
        with service.acquire_concurrency_slot():
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
            thread.join(timeout=_SCAN_WAIT_S)
    (direct, direct_elapsed), (through_caller, _elapsed) = results
    assert direct[0] == "raised" and isinstance(direct[1], concurrency_slots.SlotBackendError), direct
    assert "scan" in str(direct[1]) and "deadline" in str(direct[1]), str(direct[1])
    assert direct_elapsed >= 0.2, direct_elapsed
    assert through_caller[0] == "raised" and isinstance(through_caller[1], _FE), through_caller
    assert (through_caller[1].code, through_caller[1].status) == ("SERVICE_UNAVAILABLE", 503)


def test_scan_flock_unexpected_errno_raises_backend_error_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """裁定 43 (s2e) -- 変異 Ms2e (他の errno も「握られている」と読んで
    待つ): an injected `EPERM` from the `scan` lock (every `slot-<i>` lock
    runs for real) raises `SlotBackendError` naming the errno within 1 s,
    with the deadline set to 5 s -- never retried until the deadline."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
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
        thread.join(timeout=_SCAN_WAIT_S)
    assert scan_attempts, "no scan lock attempt observed (空振り)"
    assert outcome[0] == "raised" and isinstance(outcome[1], concurrency_slots.SlotBackendError), outcome
    assert f"errno {errno.EPERM}" in str(outcome[1]), str(outcome[1])
    assert elapsed < 1.0, elapsed


def test_scan_open_failure_raises_backend_error(tmp_path: Path) -> None:
    """裁定 43 (s2e): `scan` cannot be opened (a directory planted under
    its name) -- `SlotBackendError`, never an admission and never
    `LimitExceeded`."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    (slot_dir / concurrency_slots.SCAN_FILENAME).mkdir()
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError, match="could not open scan file"):
        _acquire_one(slots)


def test_scan_symlink_is_refused_at_open(tmp_path: Path) -> None:
    """裁定 43 (s2e) -- 変異 Ms2s (`scan` の open から `O_NOFOLLOW` を外す):
    `scan` planted as a symlink to a regular file elsewhere is refused at
    open (`SlotBackendError`), never followed and locked."""
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("")
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    (slot_dir / concurrency_slots.SCAN_FILENAME).symlink_to(real_target)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with pytest.raises(concurrency_slots.SlotBackendError, match="could not open scan file"):
        _acquire_one(slots)


def test_scan_fd_is_closed_on_every_path_out_of_acquire(tmp_path: Path) -> None:
    """裁定 43 (s3) -- 変異 Ms3 (拒否の経路の close を外す): the process'
    own open-fd count does not grow across an admission, a `LimitExceeded`,
    a `SlotBackendError` raised during the search (a `slot-0` symlink) and
    an exception raised during the search (the injected random source) --
    and inside an admission's `with` body exactly one fd more is open (the
    held slot's; `scan` is already closed)."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
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


def test_scan_lock_held_by_a_sigkilled_child_process_is_released_by_the_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """裁定 43 (s4, 監査照合 -- kernel の性質、変異なし): a CHILD process
    holds the `scan` lock (opened with the module's own flags and mode)
    and signals it; this process' acquisition then fails with the `scan`
    deadline (0.3 s here) -- the child really holds it; after SIGKILL and
    a bounded wait for the child, this process acquires."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    ready_path = tmp_path / "child_ready"
    monkeypatch.setattr(concurrency_slots, "_SCAN_LOCK_TIMEOUT_S", 0.3)
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    child_src = (
        "import fcntl, os, sys, time\n"
        f"sys.path.insert(0, {src_dir!r})\n"
        "from r2db_api import concurrency_slots\n"
        f"fd = os.open(os.path.join({str(slot_dir)!r}, concurrency_slots.SCAN_FILENAME), "
        "concurrency_slots._OPEN_FLAGS, concurrency_slots._FILE_MODE)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        f"open({str(ready_path)!r}, 'w').close()\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        deadline = time.monotonic() + _SCAN_WAIT_S
        while not ready_path.exists():
            assert time.monotonic() < deadline, "the child never signalled it holds scan"
            assert proc.poll() is None, f"the child exited early ({proc.returncode})"
            time.sleep(0.05)
        slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
        with pytest.raises(concurrency_slots.SlotBackendError, match="deadline"):
            _acquire_one(slots)
        proc.kill()  # SIGKILL
        proc.wait(timeout=_SCAN_WAIT_S)
        assert _acquire_one(slots) == "admitted"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=_SCAN_WAIT_S)


def test_scan_file_is_distinct_from_every_slot_file_and_never_counted_as_held(tmp_path: Path) -> None:
    """裁定 43 (s5) -- 変異 Ms5 (`scan` の名を `slot-0` にする): with
    `limit = 1`, one acquisition is admitted and, while it is held, the
    held-slot probe (`_probe_slot_dir_held_names`, the same count the
    adapter tests use) finds exactly `slot-0` held -- `scan` is closed and
    is not a `slot-*` file -- and the directory holds exactly `scan` and
    `slot-0`, `scan` with mode 0600. Named `slot-0`, `scan` would hold the
    lock on the very slot it searches, so the acquisition is refused."""
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)
    with slots.acquire(1):
        held = _probe_slot_dir_held_names(slot_dir)
        names = sorted(entry.name for entry in slot_dir.iterdir())
    assert held == ["slot-0"], held
    assert names == sorted([concurrency_slots.SCAN_FILENAME, "slot-0"]), names
    assert concurrency_slots.SCAN_FILENAME != concurrency_slots.SELFCHECK_FILENAME
    assert not concurrency_slots.SCAN_FILENAME.startswith("slot-")
    assert stat.S_IMODE((slot_dir / concurrency_slots.SCAN_FILENAME).stat().st_mode) == 0o600


def test_data_service_rejects_concurrency_configured_true_without_slots() -> None:
    """完了条件 56 の補強 (訂正註 56b, F13) -- 変異なし (`concurrency_
    slots=None` かつ `concurrency_configured=True` を渡すと `DataService.
    __init__` が `ValueError` を送出する): `concurrency_configured=True`
    は「host-shared slot が配線されている」ことを`capabilities().limit_
    enforcement.concurrency` に対して意味するので、slot オブジェクトが
    無いのにこのフラグだけ真にする呼び出し元を構造で拒む。"""
    from r2db_api.service import DataService

    class _FakeCredentials:
        def assert_active(self, context):
            return context

    with pytest.raises(ValueError, match="concurrency_configured"):
        DataService(
            _FakeCredentials(), limits=ResourceLimits(concurrency=1), initial_cells={"app": object()},
            concurrency_slots=None, concurrency_configured=True,
        )


def test_slot_backend_error_maps_to_service_unavailable_through_data_service() -> None:
    """完了条件 45 (レビュー F6 (i)): a `concurrency_slots.SlotBackendError`
    (design 裁定 28 -- an unexpected `flock` errno, fail-closed) reaches
    the SAME `SERVICE_UNAVAILABLE`/503 mapping through BOTH `DataService.
    acquire_concurrency_slot()` (pre-auth) and `DataService._slot()`
    (post-auth, `concurrency_precharged=False`) -- never `LIMIT_EXCEEDED`/
    429 (a genuine "all slots taken") and never silently admitted."""
    from contextlib import contextmanager

    from r2db_api.auth import AuthContext
    from r2db_api.errors import FoundationError as _FE
    from r2db_api.service import DataService

    class _FakeCredentials:
        def assert_active(self, context):
            return context

    class _BackendErrorSlots:
        @contextmanager
        def acquire(self, limit: int):
            raise concurrency_slots.SlotBackendError("synthetic backend failure for condition 45")
            yield  # pragma: no cover -- unreachable, makes this a generator function

    service = DataService(
        _FakeCredentials(), limits=ResourceLimits(concurrency=1), initial_cells={"app": object()},
        concurrency_slots=_BackendErrorSlots(), concurrency_configured=True,
    )
    context = AuthContext("crd", "app", "runtime")

    with pytest.raises(_FE) as excinfo_pre_auth:
        with service.acquire_concurrency_slot():
            pass  # pragma: no cover -- acquire() raises before yielding
    assert excinfo_pre_auth.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo_pre_auth.value.status == 503

    with pytest.raises(_FE) as excinfo_post_auth:
        with service._slot(context, concurrency_precharged=False):  # noqa: SLF001
            pass  # pragma: no cover -- acquire() raises before yielding
    assert excinfo_post_auth.value.code == "SERVICE_UNAVAILABLE"
    assert excinfo_post_auth.value.status == 503


def test_real_http_request_holds_the_shared_slot_and_writes_a_rate_row(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 76a (WO 裁定 40: supplementary composition-root evidence,
    never a substitute for 76/77's own adapter-session primary
    observation -- `test_http_adapter_session_holds_the_shared_slot_and_
    writes_a_rate_row` below): a REAL `build_app()` (host-shared slot
    directory AND the PostgreSQL-backed rate row both wired, exactly the
    production composition -- never a hand-built fake) proves, over a
    real HTTP round trip (`starlette.testclient.TestClient`), that
    exactly one of the declared `concurrency` slot files is held (a
    second, independent `flock(LOCK_EX|LOCK_NB)` on it fails with
    EWOULDBLOCK/EAGAIN) for the duration of a request stalled inside its
    own synchronous section, and free again once it completes, and the
    request leaves a `credential_request_rate` row for the authenticating
    credential."""
    import errno
    import fcntl

    from r2db_api import service as service_module

    env = _preflight_env(platform, provisioned_app)
    app = main_module.build_app(env=env)
    slot_dir = Path(env["R2DB_SLOT_DIR"])
    bearer = _issue_and_rotate_bearer(platform, provisioned_app)
    credential_id = bearer.split(".", 1)[0]

    # `capabilities()` (`service.py`) runs its own body -- the module-
    # level `build_capabilities_document` call -- LEXICALLY INSIDE the
    # `with self._slot(...)` block, so blocking THIS call (rather than
    # `DataService.capabilities` itself, which would block BEFORE the
    # slot is ever entered) holds the slot for the stall's own duration,
    # the same way `test_threadpool_offload.py`'s own `query_page` stub
    # does for a data-plane query. Chosen over an actual entity query so
    # this test needs no schema/entity-type setup for `provisioned_app`'s
    # own real per-application database at all -- `/v1/capabilities`
    # goes through the SAME `_slot`/rate/concurrency gate (`capabilities`'s
    # own docstring, `operation_catalog`'s docstring) as every other
    # endpoint.
    entered = threading.Event()
    release = threading.Event()
    original_build_capabilities_document = service_module.build_capabilities_document

    def blocking_build_capabilities_document(*args, **kwargs):
        entered.set()
        release.wait(timeout=5.0)
        return original_build_capabilities_document(*args, **kwargs)

    service_module.build_capabilities_document = blocking_build_capabilities_document

    from starlette.testclient import TestClient

    result: list[object] = []
    held_names: list[str] = []
    try:
        with TestClient(app.app) as client:
            def _hold() -> None:
                response = client.get(
                    "/v1/capabilities",
                    headers={"authorization": f"Bearer {bearer}"},
                )
                result.append(response)

            holder = threading.Thread(target=_hold)
            holder.start()
            assert entered.wait(timeout=5.0), "the held request never reached its own blocking sync section"

            # 完了条件 76: exactly one slot file is exclusively held right now.
            for candidate in sorted(slot_dir.glob("slot-*")):
                probe_fd = os.open(str(candidate), os.O_RDWR)
                try:
                    fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(probe_fd, fcntl.LOCK_UN)
                except OSError as exc:
                    assert exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN), exc
                    held_names.append(candidate.name)
                finally:
                    os.close(probe_fd)
            assert held_names, "no slot file was found exclusively held during the stalled request"
            assert len(held_names) == 1, f"expected exactly 1 held slot, found {held_names}"

            release.set()
            holder.join(timeout=5.0)
    finally:
        service_module.build_capabilities_document = original_build_capabilities_document

    assert result and result[0].status_code == 200, result

    # The slot is free again once the request has completed.
    freed_fd = os.open(str(slot_dir / held_names[0]), os.O_RDWR)
    try:
        fcntl.flock(freed_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(freed_fd, fcntl.LOCK_UN)
    finally:
        os.close(freed_fd)

    # 完了条件 77: the request left a rate row for the authenticating credential.
    with psycopg.connect(_platform_dsn(platform)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(sql.Identifier(platform.schema, RATE_TABLE)),
                [credential_id],
            )
            (count,) = cur.fetchone()
    assert count == 1, "the http request must leave exactly one rate row for its own credential"


# ===========================================================================
# completion conditions 55-57: the 2-strategy mapping helper
# ===========================================================================


def test_resolve_limit_enforcement_configured_is_always_enforced_regardless_of_ceiling() -> None:
    """完了条件 55 -- 変異 M55 (rate の写像を配線に依らず `enforced`; the
    generic helper's own `configured=True` branch, which every ceiling
    value must resolve to `enforced`)."""
    for ceiling in (1, 2, 99):
        assert resolve_limit_enforcement(configured=True, ceiling=ceiling) == "enforced"


def test_resolve_limit_enforcement_unconfigured_follows_the_legacy_ceiling_rule() -> None:
    """完了条件 56/57 の共有経路 -- 変異 M56 (ceiling <= workers を外す。
    ここでは helper 自身の unconfigured 側の式): `configured=False` keeps
    the pre-existing single-process rule."""
    assert resolve_limit_enforcement(configured=False, ceiling=1) == "enforced"
    assert resolve_limit_enforcement(configured=False, ceiling=2) == "deployment_required"


def test_build_capabilities_document_concurrency_mapping_enforced_only_at_ceiling_le_workers() -> None:
    """完了条件 56 -- ceiling<=workers (配線済み) は enforced、それ以外は
    deployment_required。"""
    limits = ResourceLimits()
    enforced_doc = build_capabilities_document(
        role="runtime", application_id="app", limits=limits, control_plane_status="unavailable",
        process_ceiling=2, surfaces=None, concurrency_configured=True,
    )
    assert enforced_doc["limit_enforcement"]["concurrency"] == "enforced"
    not_enforced_doc = build_capabilities_document(
        role="runtime", application_id="app", limits=limits, control_plane_status="unavailable",
        process_ceiling=2, surfaces=None, concurrency_configured=False,
    )
    assert not_enforced_doc["limit_enforcement"]["concurrency"] == "deployment_required"


def test_build_capabilities_document_rate_mapping_ignores_ceiling_when_wired() -> None:
    """完了条件 55 (data 側): `requests_per_minute` reads `enforced` at
    ceiling 2 once `rate_configured=True`, unlike `concurrency` (previous
    test) which still needs `concurrency_configured` for ITS OWN separate
    workers comparison."""
    limits = ResourceLimits()
    doc = build_capabilities_document(
        role="runtime", application_id="app", limits=limits, control_plane_status="unavailable",
        process_ceiling=2, surfaces=None, rate_configured=True, concurrency_configured=False,
    )
    assert doc["limit_enforcement"]["requests_per_minute"] == "enforced"
    assert doc["limit_enforcement"]["concurrency"] == "deployment_required"


def test_build_app_concurrency_configured_reflects_workers_vs_ceiling(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 56 -- 変異 M56 (ceiling <= workers を外す): a REAL
    `build_app()` with `process_ceilings.data=2`, `R2DB_WORKERS=1`
    (workers < ceiling, a valid, successful startup) declares `concurrency`
    `deployment_required` -- `main.py`'s own `concurrency_configured =
    workers >= process_ceiling` computation, observed end to end through
    a real served `capabilities()` document."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({"data": 2, "control": 1})],
            )
        conn.commit()
    env = _preflight_env(platform, provisioned_app, workers="1")
    app = main_module.build_app(env=env)
    try:
        service = app.app.state.service
        context = service.authenticate(_issue_and_rotate_bearer(platform, provisioned_app))
        doc = service.capabilities(context)
        assert doc["limit_enforcement"]["concurrency"] == "deployment_required", doc["limit_enforcement"]
    finally:
        app.app.state.service._durable_audit.close()  # noqa: SLF001
        app.app.state.service._credentials.close()  # noqa: SLF001
        from r2db_api.postgres import default_pool_manager, set_connection_application_name

        default_pool_manager.dispose_all()
        set_connection_application_name(None)
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()


def _issue_and_rotate_bearer(platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace) -> str:
    """A real, freshly issued runtime credential's bearer locator, with a
    KNOWN secret (`_issue_credential` alone never returns the random one
    `PostgresCredentialStore.add` generates internally -- rotating to a
    chosen secret right after is simpler than plumbing that value back)."""
    from r2db_api.auth import compose_bearer_locator

    credential_id = _issue_credential(platform, provisioned_app.slug)
    store = _write_store(platform)
    try:
        secret = "r113-m56-" + secrets.token_hex(4)
        with store.unit_of_work() as work:
            store.rotate(credential_id, secret, work=work)
    finally:
        store.close()
    return compose_bearer_locator(credential_id, secret)


def test_control_plane_mapping_goes_through_the_same_helper_unconfigured(platform: types.SimpleNamespace) -> None:
    """完了条件 57 -- 変異 M57 (control の写像を helper を通さず常に
    `enforced`): a REAL `build_control_app()` at `process_ceilings.
    control=2` declares `control_requests_per_minute`/`audit_requests_
    per_minute` `deployment_required` -- the control plane's own 2
    region-(ii) classes keep the unwired `ceiling <= 1` rule regardless
    of this WP's data-plane rate/concurrency wiring (裁定4 -- control
    stays in-process on both peers)."""
    import importlib
    import sys as sys_module

    from r2db_api.credential_store import PostgresControlCredentialStore

    _declare_control_surface(platform)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES (\'process_ceilings\', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({"data": 1, "control": 2})],
            )
        conn.commit()
    # 裁定 28 (i): controlplane's own F-16 floor is now * `process_
    # ceilings.control` (2) -- 16*2=32 -- raise its real CONNECTION LIMIT
    # (20 by 0013) so F-16 does not fire before this test's own
    # control-mapping assertion runs.
    with psycopg.connect(platform.admin_dsn) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 32").format(sql.Identifier(f"{platform.prefix}_controlplane")))
        _conn.commit()
    env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-r113-m57",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    mp = pytest.MonkeyPatch()
    for key, value in env.items():
        mp.setenv(key, value)
    try:
        if "r2db_api.control_main" in sys_module.modules:
            control_main = importlib.reload(sys_module.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as control_main
        app = control_main.build_control_app(env=env)

        seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper="synthetic-test-pepper-r113-m57", schema=platform.schema, pool_size=4)
        credential_id = "ctl_" + secrets.token_hex(8)
        secret = "r113-m57-" + secrets.token_hex(4)
        try:
            with seed_store.unit_of_work() as work:
                seed_store.add(credential_id, secret, work=work)
                seed_store.rotate(credential_id, secret, work=work)
        finally:
            seed_store.close()
        from r2db_api.auth import compose_bearer_locator
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            response = client.get(
                "/control/v1/capabilities",
                headers={"authorization": f"Bearer {compose_bearer_locator(credential_id, secret)}"},
            )
        assert response.status_code == 200, response.text
        enforcement = response.json()["limit_enforcement"]
        assert enforcement["control_requests_per_minute"] == "deployment_required", enforcement
        assert enforcement["audit_requests_per_minute"] == "deployment_required", enforcement
    finally:
        mp.undo()
        _restore_data_only_surface(platform)
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES (\'process_ceilings\', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()
        from r2db_api.postgres import set_connection_application_name

        set_connection_application_name(None)


# ===========================================================================
# completion conditions 58-61: workers env validation
# ===========================================================================


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "abc"])
def test_data_workers_env_rejects_unset_empty_zero_negative_non_numeric(main_module: types.ModuleType, raw) -> None:
    """完了条件 58 -- 変異 M58 (未設定で1に落ちる)."""
    env: dict[str, str] = {} if raw is None else {"R2DB_WORKERS": raw}
    with pytest.raises(RuntimeError, match="R2DB_WORKERS"):
        main_module._workers_from_env(env, "R2DB_WORKERS")


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "abc"])
def test_control_workers_env_rejects_unset_empty_zero_negative_non_numeric(raw) -> None:
    """完了条件 59 -- 変異 M59 (未設定で1に落ちる)."""
    import r2db_api.control_main as control_main

    env: dict[str, str] = {} if raw is None else {"R2DB_CONTROL_WORKERS": raw}
    with pytest.raises(RuntimeError, match="R2DB_CONTROL_WORKERS"):
        control_main._workers_from_env(env, "R2DB_CONTROL_WORKERS")


def test_build_app_fails_when_workers_exceeds_declared_data_ceiling(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 60 -- 変異 M60 (data の workers 検査を外す)."""
    env = _main_env(platform, provisioned_app)
    env["R2DB_WORKERS"] = "5"  # platform fixture declares process_ceilings.data = 1
    with pytest.raises(RuntimeError, match="R2DB_WORKERS"):
        main_module.build_app(env=env)


def test_build_control_app_fails_when_workers_exceeds_declared_control_ceiling(
    platform: types.SimpleNamespace,
) -> None:
    """完了条件 61 -- 変異 M61 (control の workers 検査を外す)."""
    import importlib
    import sys as sys_module

    _declare_control_surface(platform)
    env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-r113-ctl",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "5",  # platform fixture declares process_ceilings.control = 1
    }
    mp = pytest.MonkeyPatch()
    for key, value in env.items():
        mp.setenv(key, value)
    try:
        if "r2db_api.control_main" in sys_module.modules:
            control_main = importlib.reload(sys_module.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as control_main
        with pytest.raises(RuntimeError, match="R2DB_CONTROL_WORKERS"):
            control_main.build_control_app(env=env)
    finally:
        mp.undo()
        _restore_data_only_surface(platform)


def test_build_app_workers_check_raises_synchronously_never_needing_asgi_lifespan(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 62 -- 変異 M62 (検査を lifespan へ移す): the workers-vs-
    ceiling failure is raised by the plain, synchronous `build_app(...)`
    call itself -- no `asyncio.run`/ASGI lifespan driving is needed to
    observe it, proving the check lives inside `build_app()`, never
    deferred to lifespan startup."""
    env = _main_env(platform, provisioned_app)
    env["R2DB_WORKERS"] = "9"
    with pytest.raises(RuntimeError):
        main_module.build_app(env=env)  # a plain function call -- no coroutine involved at all


# ===========================================================================
# completion conditions 63-66: `--preflight`
# ===========================================================================


def _preflight_env(platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, *, workers: str = "1") -> dict[str, str]:
    slot_dir = tempfile.mkdtemp(prefix="r2db-test-slots-preflight-")
    env = dict(_main_env(platform, provisioned_app))
    env["R2DB_WORKERS"] = workers
    env["R2DB_SLOT_DIR"] = slot_dir
    return env


def _run_preflight_subprocess(module: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith(("R2DB_", "MITATEDB_"))}
    full_env.update(env)
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    existing = full_env.get("PYTHONPATH")
    full_env["PYTHONPATH"] = src_dir if not existing else f"{src_dir}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-m", module, "--preflight"], capture_output=True, text=True, env=full_env, timeout=60,
    )


def test_data_preflight_exits_0_on_a_sound_env(platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace) -> None:
    """完了条件 63 -- 変異 M63 (data の preflight が例外を握って0; ここで
    は正常系: `python -m r2db_api.main --preflight` exits 0 on a valid
    env)."""
    env = _preflight_env(platform, provisioned_app)
    result = _run_preflight_subprocess("r2db_api.main", env)
    assert result.returncode == 0, result.stderr


def test_data_preflight_exits_nonzero_with_f15_when_process_ceilings_missing(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace,
) -> None:
    """完了条件 63 -- 異常系 (F-15)."""
    env = _preflight_env(platform, provisioned_app)
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE key = 'process_ceilings'").format(sql.Identifier(platform.schema, "platform_declarations")),
            )
        conn.commit()
    try:
        result = _run_preflight_subprocess("r2db_api.main", env)
        assert result.returncode != 0
        assert "F-15" in result.stderr, result.stderr
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()

@contextlib.contextmanager
def _rate_function_withheld(platform: types.SimpleNamespace) -> Iterator[None]:
    """Renames the platform's own `credential_request_rate_admit(text,
    integer)` for the duration of the block (as the admin role) and
    renames it back in `finally` -- a platform the rate migration was
    never applied to, as far as the startup check can see."""
    signature = "(text, integer)"
    with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
        conn.execute(
            sql.SQL("ALTER FUNCTION {}" + signature + " RENAME TO credential_request_rate_admit_withheld").format(
                sql.Identifier(platform.schema, "credential_request_rate_admit")
            )
        )
    try:
        yield
    finally:
        with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
            conn.execute(
                sql.SQL("ALTER FUNCTION {}" + signature + " RENAME TO credential_request_rate_admit").format(
                    sql.Identifier(platform.schema, "credential_request_rate_admit_withheld")
                )
            )


def test_build_app_and_preflight_fail_naming_the_rate_migration_when_the_rate_function_is_missing(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """F5 (m1) -- 変異 Mm1 (起動時の検査を外す): with the platform's own
    rate function absent, `build_app()` and `python -m r2db_api.main
    --preflight` both fail naming `0015_credential_request_rate.sql`,
    instead of starting a data plane whose every request would be a 503.
    Non-空振り: once the function is back, the same check passes on a
    connection of the data plane's own role."""
    from r2db_api import platform_declarations

    migration = platform_declarations.REQUEST_RATE_MIGRATION_FILENAME
    assert migration == "0015_credential_request_rate.sql"
    with _rate_function_withheld(platform):
        with pytest.raises(RuntimeError, match=migration):
            main_module.build_app(env=_preflight_env(platform, provisioned_app))
        result = _run_preflight_subprocess("r2db_api.main", _preflight_env(platform, provisioned_app))
    assert result.returncode != 0
    assert migration in result.stderr, result.stderr
    with psycopg.connect(platform.api_dsn) as conn:
        platform_declarations.check_request_rate_function(conn, schema=platform.schema, migration=migration)


def test_build_app_fails_naming_the_rate_migration_when_the_data_plane_role_may_not_execute_the_rate_function(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """F5 (m2) -- 変異 Mm2 (権限の読み取りを外す): the rate function exists
    but the data plane's own role (the `R2DB_PLATFORM_DSN` login role)
    has lost EXECUTE on it -- `build_app()` fails naming
    `0015_credential_request_rate.sql`. EXECUTE is granted back in
    `finally`."""
    from r2db_api import platform_declarations

    with psycopg.connect(platform.api_dsn) as conn:
        (api_role,) = conn.execute("SELECT current_user").fetchone()
    function = sql.SQL("{}(text, integer)").format(sql.Identifier(platform.schema, "credential_request_rate_admit"))
    with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
        conn.execute(sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM {}").format(function, sql.Identifier(api_role)))
    try:
        with pytest.raises(RuntimeError, match="may not EXECUTE") as excinfo:
            main_module.build_app(env=_preflight_env(platform, provisioned_app))
        assert platform_declarations.REQUEST_RATE_MIGRATION_FILENAME in str(excinfo.value)
    finally:
        with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
            conn.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(function, sql.Identifier(api_role)))



def test_control_preflight_exits_0_on_a_sound_env(platform: types.SimpleNamespace) -> None:
    """完了条件 64 の監査照合 (レビュー F6 (j)): `python -m r2db_api.
    control_main --preflight` exits 0, over a real subprocess, on a
    genuinely sound env (surfaces declared, `process_ceilings.control`
    present and >= `R2DB_CONTROL_WORKERS`) -- the positive control this
    file's own `test_control_preflight_exits_nonzero_with_f15_when_
    process_ceilings_missing` (below) needs to show the anomaly path is
    genuinely anomalous, not merely "always non-zero"."""
    _declare_control_surface(platform)
    env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-r113-ctl-preflight-ok",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    try:
        result = _run_preflight_subprocess("r2db_api.control_main", env)
        assert result.returncode == 0, result.stderr
    finally:
        _restore_data_only_surface(platform)


def test_control_preflight_exits_nonzero_with_f15_when_process_ceilings_missing(platform: types.SimpleNamespace) -> None:
    """完了条件 64 -- 変異 M64 (control の preflight が例外を握って0)."""
    env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-r113-ctl-preflight",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE key = 'process_ceilings'").format(sql.Identifier(platform.schema, "platform_declarations")),
            )
        conn.commit()
    try:
        result = _run_preflight_subprocess("r2db_api.control_main", env)
        assert result.returncode != 0
        assert "F-15" in result.stderr, result.stderr
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()


def test_preflight_entry_source_reuses_the_bare_module_app_variable() -> None:
    """完了条件 65 -- 変異 M65 (entry で build をもう一度呼ぶ): a static
    check of `main.py`'s own `--preflight` entry -- it drives `_run_
    lifespan_once` against the bare `app` name (the module-level object
    `build_app()` already produced, on the line right above), never a
    fresh `build_app()` call of its own. A real subprocess round trip
    proving `build_app()` itself runs exactly once per real preflight
    invocation is impractical to observe (both a normal AND a doubled
    build succeed identically on a sound env, network side effects
    aside) -- this is the direct, unambiguous pin on the entry's own
    source instead."""
    import re

    source = (Path(__file__).resolve().parents[1] / "src" / "r2db_api" / "main.py").read_text()
    match = re.search(r'if __name__ == "__main__" and "--preflight" in sys\.argv:\n(.*)', source, re.DOTALL)
    assert match is not None, "no --preflight entry block found in main.py"
    entry_body = match.group(1)
    assert "asyncio.run(_run_lifespan_once(app))" in entry_body, entry_body


class _FakeAsgiLifespanApp:
    """A minimal ASGI app whose own `lifespan` scope answers with a
    caller-supplied startup/shutdown result -- drives `_run_lifespan_
    once` without any real network/PostgreSQL dependency, isolating
    completion conditions 63/64/66 to that function's own logic."""

    def __init__(self, *, startup_failed: bool = False, shutdown_failed: bool = False) -> None:
        self.startup_failed = startup_failed
        self.shutdown_failed = shutdown_failed
        self.shutdown_seen = False

    async def __call__(self, scope, receive, send) -> None:
        message = await receive()
        assert message["type"] == "lifespan.startup"
        if self.startup_failed:
            await send({"type": "lifespan.startup.failed", "message": "synthetic startup failure"})
            return
        await send({"type": "lifespan.startup.complete"})
        message = await receive()
        assert message["type"] == "lifespan.shutdown"
        self.shutdown_seen = True
        if self.shutdown_failed:
            await send({"type": "lifespan.shutdown.failed", "message": "synthetic shutdown failure"})
            return
        await send({"type": "lifespan.shutdown.complete"})


#: Both `_run_lifespan_once` tests below drive it against a FAKE app
#: whose own `lifespan.startup.failed` branch, under the mutation each
#: test targets (M63/M64: the swallowed-exception branch never raises),
#: is never actually read by `_run_lifespan_once` -- it falls through to
#: `await to_app.put({"type": "lifespan.shutdown"})` instead, a message
#: the fake app (already exited after sending `.failed`) never consumes,
#: so `shutdown_result = await from_app.get()` awaits a queue nothing
#: will ever fill -- a real `asyncio` deadlock, not merely a slow call.
#: `asyncio.wait_for(..., timeout=...)` is what turns that into a bounded
#: `asyncio.TimeoutError` instead of a permanent hang (observed directly:
#: a direct, unbounded `asyncio.run(...)` call here hung the pytest
#: subprocess under the real mutation and had to be killed).
_LIFESPAN_TIMEOUT_S = 5.0


def test_data_run_lifespan_once_propagates_a_startup_failure(main_module: types.ModuleType) -> None:
    """完了条件 63 -- 変異 M63 (data の preflight が例外を握って0): `_run_
    lifespan_once` re-raises a `lifespan.startup.failed` message, never
    swallowing it."""
    import asyncio

    fake_app = _FakeAsgiLifespanApp(startup_failed=True)
    with pytest.raises((RuntimeError, asyncio.TimeoutError)) as excinfo:
        asyncio.run(asyncio.wait_for(main_module._run_lifespan_once(fake_app), timeout=_LIFESPAN_TIMEOUT_S))
    assert isinstance(excinfo.value, RuntimeError) and "synthetic startup failure" in str(excinfo.value), (
        f"expected the real RuntimeError (never a timeout): {excinfo.value!r}"
    )


def test_control_run_lifespan_once_propagates_a_startup_failure() -> None:
    """完了条件 64 -- 変異 M64 (control の preflight が例外を握って0)."""
    import asyncio
    import r2db_api.control_main as control_main

    fake_app = _FakeAsgiLifespanApp(startup_failed=True)
    with pytest.raises((RuntimeError, asyncio.TimeoutError)) as excinfo:
        asyncio.run(asyncio.wait_for(control_main._run_lifespan_once(fake_app), timeout=_LIFESPAN_TIMEOUT_S))
    assert isinstance(excinfo.value, RuntimeError) and "synthetic startup failure" in str(excinfo.value), (
        f"expected the real RuntimeError (never a timeout): {excinfo.value!r}"
    )


def test_preflight_entry_reuses_the_module_app_never_calling_build_app_twice(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """非-mutation 監査照合: `_run_lifespan_once` (直接呼び出し) は
    `build_app` を一切呼ばない -- 完了条件 65 の動的な裏付け (静的 pin は
    上の `test_preflight_entry_source_reuses_the_bare_module_app_variable`
    が担う)。"""
    import asyncio

    calls = {"n": 0}
    original = main_module.build_app

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    main_module.build_app = _counting
    try:
        asyncio.run(main_module._run_lifespan_once(main_module.app))
    finally:
        main_module.build_app = original
    assert calls["n"] == 0, "_run_lifespan_once must never call build_app() itself"


def test_preflight_entry_closes_the_platform_pool_before_exiting(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 66 -- 変異 M66 (後始末の close を飛ばす): after driving the
    preflight lifespan cycle once, the credential store's own pool has
    released every connection it held (`_created` back to 0) -- proving
    the entry's own close path genuinely ran. `build_app()` alone never
    connects this pool (every startup-time read goes through a one-shot
    connection or `durable_audit`'s own pool instead) -- a real `service.
    authenticate(...)` call forces at least one real connection first, so
    `_created` is genuinely non-zero before the close this test checks."""
    import asyncio

    env = _preflight_env(platform, provisioned_app)
    app = main_module.build_app(env=env)
    service = app.app.state.service
    service.authenticate(_issue_and_rotate_bearer(platform, provisioned_app))
    assert service._credentials._pool._created >= 1, "non-空振り: the credential store's own pool must have a real connection before this test's own close check means anything"  # noqa: SLF001
    asyncio.run(asyncio.wait_for(main_module._run_lifespan_once(app), timeout=_LIFESPAN_TIMEOUT_S))
    assert service._credentials._pool._created == 0, "the credential store's own pool must be fully closed after preflight"  # noqa: SLF001


# ===========================================================================
# completion conditions 68-69: `application_name`
# ===========================================================================


def test_data_plane_connections_carry_the_documented_application_name(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 68 -- 変異 M68 (`_RolePool._connect` から application_name
    を外す)."""
    env = _preflight_env(platform, provisioned_app)
    app = main_module.build_app(env=env)
    try:
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT application_name FROM pg_stat_activity WHERE application_name LIKE 'r2db-api:data:%'"
                )
                names = [row[0] for row in cur.fetchall()]
        assert names, "no pg_stat_activity session carried the data-plane application_name (空振り)"
        import re

        for name in names:
            assert re.match(r"^r2db-api:data:\d+$", name), name
    finally:
        app.app.state.service._durable_audit.close()  # noqa: SLF001
        app.app.state.service._credentials.close()  # noqa: SLF001
        from r2db_api.postgres import default_pool_manager, set_connection_application_name

        default_pool_manager.dispose_all()
        set_connection_application_name(None)


def test_control_plane_connections_carry_the_documented_application_name(platform: types.SimpleNamespace) -> None:
    """完了条件 69 -- 変異 M69 (plane を `data` に固定)."""
    import importlib
    import sys as sys_module

    _declare_control_surface(platform)
    env = {
        "R2DB_CONTROLPLANE_DSN": platform.controlplane_dsn,
        "R2DB_CONTROL_CREDENTIAL_PEPPER": "synthetic-test-pepper-r113-ctl-appname",
        "R2DB_CREDENTIAL_PEPPER": PEPPER,
        "R2DB_PLATFORM_SCHEMA": platform.schema,
        "R2DB_CONTROL_WORKERS": "1",
    }
    mp = pytest.MonkeyPatch()
    for key, value in env.items():
        mp.setenv(key, value)
    try:
        if "r2db_api.control_main" in sys_module.modules:
            control_main = importlib.reload(sys_module.modules["r2db_api.control_main"])
        else:
            import r2db_api.control_main as control_main
        control_main.build_control_app(env=env)
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT application_name FROM pg_stat_activity WHERE application_name LIKE 'r2db-api:control:%'"
                )
                names = [row[0] for row in cur.fetchall()]
        assert names, "no pg_stat_activity session carried the control-plane application_name (空振り)"
        import re

        for name in names:
            assert re.match(r"^r2db-api:control:\d+$", name), name
    finally:
        mp.undo()
        _restore_data_only_surface(platform)
        from r2db_api.postgres import set_connection_application_name

        set_connection_application_name(None)


# ===========================================================================
# completion conditions 70-72: thread-limit-derived pool dimension
# ===========================================================================


def test_role_pool_size_is_thread_limit_plus_two() -> None:
    """完了条件 70 の helper の算術 (`role_pool_size`). composition root
    で `R2DB_THREAD_LIMIT` が pool の寸法に効くことの観測は、直後の
    `test_build_app_sizes_platform_and_application_pools_from_r2db_
    thread_limit` (変異 M70) が担う."""
    assert role_pool_size(6) == 8


def test_build_app_sizes_platform_and_application_pools_from_r2db_thread_limit(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 70 -- 変異 M70 (`main.py` の `role_pool_size(thread_limit)`
    2 か所を `role_pool_size(DEFAULT_THREAD_LIMIT)` にする): the REAL
    `build_app()` run with `R2DB_THREAD_LIMIT=6` (and no
    `R2DB_PLATFORM_POOL_SIZE` override) sizes the platform pool (the
    credential store and the durable audit sink) and the served
    application's own runtime/developer role pools all at
    `role_pool_size(6)` = 8, never the `DEFAULT_THREAD_LIMIT` (4)
    derived 6."""
    env = _preflight_env(platform, provisioned_app)
    env.pop("R2DB_PLATFORM_POOL_SIZE", None)
    env["R2DB_THREAD_LIMIT"] = "6"
    app = main_module.build_app(env=env)
    service = app.app.state.service
    try:
        platform_sizes = {
            "credentials": service._credentials._pool._maxconn,  # noqa: SLF001
            "durable_audit": service._durable_audit._pool._maxconn,  # noqa: SLF001
        }
        cells = dict(service._cells)  # noqa: SLF001
        assert cells, "build_app() registered no served application cell (空振り)"
        cell_sizes = {}
        for application_id, cell in cells.items():
            cell_sizes[(application_id, "runtime")] = cell._runtime._maxconn  # noqa: SLF001
            cell_sizes[(application_id, "developer")] = cell._developer._maxconn  # noqa: SLF001
        assert platform_sizes == {"credentials": 8, "durable_audit": 8}, platform_sizes
        assert cell_sizes and all(size == 8 for size in cell_sizes.values()), cell_sizes
    finally:
        service._durable_audit.close()  # noqa: SLF001
        service._credentials.close()  # noqa: SLF001
        from r2db_api.postgres import default_pool_manager, set_connection_application_name

        default_pool_manager.dispose_all()
        set_connection_application_name(None)


def test_f18_check_max_connections_headroom_uses_pool_size_not_concurrency() -> None:
    """完了条件 71 -- 変異 M71 (F-18 の下限を `2 × concurrency` のまま):
    `check_max_connections_headroom` -- the REAL function `ops.py`/`main.
    py`/`control_main.py` call -- derives its own floors from `pool_size`
    (here 6, deliberately far from `ResourceLimits().concurrency` = 32),
    never from the deployed `concurrency` bound."""
    from test_ops_verify_declarations import _FakeHeadroomConn
    from r2db_api.platform_declarations import ProcessCeilings, check_max_connections_headroom

    fake_conn = _FakeHeadroomConn(application_count=1, max_connections=1_000_000, superuser_reserved=0, reserved=0)
    ceilings = ProcessCeilings(data=4, control=0)
    report = check_max_connections_headroom(
        fake_conn, schema="s", ops_module="test", process_ceilings=ceilings, pool_size=6,
    )
    assert report.lower_bound == 4 * (12 + 12) == 96, report.lower_bound
    # a pool_size of `ResourceLimits().concurrency` (32) would instead give
    # 4 * (64 + 64) = 512 -- proving this reads the given `pool_size`, not
    # a hardcoded `concurrency`-shaped constant.
    assert report.lower_bound != 4 * (64 + 64)


def test_f16_startup_floor_scales_with_process_ceilings_data_times_pool_composition(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    """完了条件 72 -- 変異 M72 (F-16 の床に `process_ceilings.data` を掛け
    ない): `r2dbsvc_api`'s own real `CONNECTION LIMIT` is a CLUSTER-WIDE
    cap every one of `process_ceilings.data` data-plane processes shares
    -- `main.py`'s own F-16 call passes `pool_size=_role_pool_size *
    process_ceiling` (never the un-multiplied per-process value alone).
    With `process_ceilings.data=3` and the role's real limit lowered to a
    value BETWEEN the unscaled floor (2*6=12) and the scaled floor
    (2*6*3=36), `build_app()` fails fast (F-16); restoring the ceiling
    and the role limit afterward (module-scoped `platform` is shared)."""
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                [json.dumps({"data": 3, "control": 1})],
            )
        conn.commit()
    with psycopg.connect(platform.admin_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 20").format(sql.Identifier(platform.api_role)))
        conn.commit()
    try:
        env = _preflight_env(platform, provisioned_app, workers="3")
        with pytest.raises(RuntimeError, match="floor 36"):
            main_module.build_app(env=env)
    finally:
        with psycopg.connect(platform.admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 68").format(sql.Identifier(platform.api_role)))
            conn.commit()
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {table} (key, value, updated_at) VALUES ('process_ceilings', %s, now()) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                    ).format(table=sql.Identifier(platform.schema, "platform_declarations")),
                    [json.dumps({"data": 1, "control": 1})],
                )
            conn.commit()


# ===========================================================================
# completion condition 74: `ops verify-declarations` dedicated exit code
# ===========================================================================


def test_verify_declarations_reports_workers_exceeding_ceiling_with_a_dedicated_exit_code(
    verify_platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完了条件 74 -- 変異 M74 (`verify-declarations` の workers 検査を外
    す): `R2DB_WORKERS`/`R2DB_CONTROL_WORKERS` set (in this CLI
    invocation's own env) above the declared ceilings reports a dedicated
    FAIL line and a dedicated non-zero exit code, distinct from every
    other F-number. Uses `test_ops_verify_declarations.py`'s own
    FUNCTION-scoped `platform` fixture (aliased `verify_platform` here,
    never shared with this file's own module-scoped one) so declaring
    `control_role` as the sole audit writer -- needed to reach past F-13
    at all -- never pollutes any other test in this file."""
    import r2db_api.ops as ops

    _verify_declare_control_role_as_the_writer(verify_platform)
    _verify_set_row(verify_platform, "surfaces", {"data": {"base_url": "https://r113-f20.example.invalid/v1"}})
    _verify_set_row(verify_platform, "process_ceilings", {"data": 1, "control": 1})
    monkeypatch.setenv("R2DB_CONTROL_DSN", verify_platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", verify_platform.schema)
    monkeypatch.setenv("R2DB_WORKERS", "99")
    monkeypatch.delenv("R2DB_CONTROL_PLANE_STATUS", raising=False)
    rc = ops.main(["verify-declarations"])
    assert rc == 19, rc


# ===========================================================================
# completion conditions 76-77: the http plug's own instance-scoped wiring
# ===========================================================================


def _probe_slot_dir_held_names(slot_dir: Path) -> list[str]:
    """Every `slot-*` file under `slot_dir` a second, independent
    `flock(LOCK_EX|LOCK_NB)` cannot take right now (EWOULDBLOCK/EAGAIN) --
    the same direct-flock-probe shape `test_real_http_request_holds_the_
    shared_slot_and_writes_a_rate_row` (完了条件 76a) already uses."""
    import errno
    import fcntl

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


def test_http_adapter_session_holds_the_shared_slot_and_writes_a_rate_row() -> None:
    """完了条件 76/77 (WO 裁定 40): the SAME session `conformance-tests`
    itself drives (`R2DBHttpConformanceAdapter()`, the object `build_
    adapter()` -- the `r2db-api-http` entry `conformance-tests/registry.
    json` names -- returns; never a hand-built fake) proves, through the
    adapter's own `hold_in_flight` (1 request held AFTER the concurrency
    slot is acquired and BEFORE the DB catalog read, `adapter.py`'s own
    docstring), that (76) exactly one of this session's own instance-
    scoped `mkdtemp` slot directory's `slot-*` files is exclusively held
    for the hold's own duration and free again once released, and (77)
    the authenticating credential has exactly one `credential_request_
    rate` row once the hold is released.

    変異 M76 (adapter が session に slot directory を配線せず、宣言も
    `concurrency_configured=False` にそろえる): adapter construction
    succeeds and the held request is admitted by the in-process counter
    instead, so no `slot-*` file is held -- the "no slot file was
    exclusively held" assertion below goes red. 変異 M77 (adapter が PG
    の rate を配線しない): the held request still completes, but no rate
    row is ever written -- the `== 1` row-count assertion below goes red
    (stays 0)."""
    adapter = _http_module.R2DBHttpConformanceAdapter()
    app_id = adapter._fresh_slug("r76s")
    try:
        adapter.provision_application(app_id)
        handle = adapter.issue_credential(app_id, "runtime")
        session = adapter.authenticate(handle)

        with adapter.hold_in_flight(session, 1) as entered:
            assert entered == 1
            held_names = _probe_slot_dir_held_names(adapter._slot_dir)
            assert held_names, "no slot file was exclusively held during the held request"
            assert len(held_names) == 1, f"expected exactly 1 held slot, found {held_names}"

        # free again once the hold above released it
        assert not _probe_slot_dir_held_names(adapter._slot_dir)

        with psycopg.connect(adapter._platform.api_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(
                        sql.Identifier(adapter._platform.schema, RATE_TABLE)
                    ),
                    [handle.credential_ref],
                )
                (rate_row_count,) = cur.fetchone()
        assert rate_row_count == 1, "the http request must leave exactly one rate row for its own credential"
    finally:
        with contextlib.suppress(Exception):
            adapter.deprovision_application(app_id)
        adapter.close()


def test_http_adapter_isolated_surface_wires_a_separate_slot_directory_and_still_gates() -> None:
    """完了条件 76 (isolated surface, WO 裁定 40): `isolated_application_
    surface()` wires a DIFFERENT `mkdtemp` slot directory than the
    session's own (never the same path -- 裁定40's own "session と別の
    directory"), and the same held-request/flock observation holds
    against it, and (77) the isolated surface's own authenticating
    credential has exactly one `credential_request_rate` row once the
    hold is released.

    変異 M76i (隔離 surface に session と同じ directory を渡す): the
    `iso._slot_dir != adapter._slot_dir` assertion below goes red (both
    equal the parent's own directory). 変異 M77i (隔離 surface が PG の
    rate を配線しない): the held request is counted in-process instead,
    so the `== 1` rate-row assertion below goes red (stays 0)."""
    adapter = _http_module.R2DBHttpConformanceAdapter()
    try:
        with adapter.isolated_application_surface() as iso:
            assert iso._slot_dir != adapter._slot_dir, "the isolated surface must wire its OWN, separate slot directory"
            app_id = iso._fresh_slug("r76i")
            iso.provision_application(app_id)
            handle = iso.issue_credential(app_id, "runtime")
            session = iso.authenticate(handle)
            with iso.hold_in_flight(session, 1) as entered:
                assert entered == 1
                held_names = _probe_slot_dir_held_names(iso._slot_dir)
                assert len(held_names) == 1, f"expected exactly 1 held slot, found {held_names}"

            with psycopg.connect(iso._platform.api_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("SELECT count(*) FROM {} WHERE credential_id = %s").format(
                            sql.Identifier(iso._platform.schema, RATE_TABLE)
                        ),
                        [handle.credential_ref],
                    )
                    (rate_row_count,) = cur.fetchone()
            assert rate_row_count == 1, "the isolated surface's request must leave exactly one rate row for its own credential"
    finally:
        adapter.close()
