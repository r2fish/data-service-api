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


def _reset_rate_row(platform: types.SimpleNamespace, credential_id: str, *, base_s: int, counts: list[int]) -> None:
    assert len(counts) == 61
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (credential_id, base_s, counts) VALUES (%s, %s, %s) "
                    "ON CONFLICT (credential_id) DO UPDATE SET base_s = EXCLUDED.base_s, counts = EXCLUDED.counts"
                ).format(table=sql.Identifier(platform.schema, RATE_TABLE)),
                [credential_id, base_s, counts],
            )
        conn.commit()


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
    newer_base = now_s + 5  # simulates "a newer request already committed"
    counts = [0] * 61
    counts[newer_base % 61] = 1
    _reset_rate_row(platform, credential_id, base_s=newer_base, counts=counts)
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
    """完了条件 31 -- 変異 M31 (shift = 61 の全 0 化を外す): a row whose
    `base_s` is 61+ seconds stale is treated as fully expired -- the next
    admission starts counting from a clean slate."""
    _register_application(platform, "r113r31", enabled=True)
    credential_id = _issue_credential(platform, "r113r31")
    now_s = int(time.time())
    stale_base = now_s - 120
    counts = [61] * 61  # deliberately "full" -- would deny if not reset
    _reset_rate_row(platform, credential_id, base_s=stale_base, counts=counts)
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 5])
            (admitted,) = cur.fetchone()
    assert admitted is True, "a row stale by >= 61 s must reset to 0 and admit"
    _base_after, counts_after = _read_rate_row(platform, credential_id)
    assert sum(counts_after) == 1


def test_rate_ring_full_count_60_seconds_ago_still_denies(platform: types.SimpleNamespace) -> None:
    """完了条件 32 (int[61], 裁定34) -- 変異 M32 (配列の長さを 60 に): a
    row with the declared limit already reached at exactly 60 seconds ago
    (still inside the 61-slot ring) denies the next request -- an
    `int[60]` array would instead zero that position and wrongly admit."""
    _register_application(platform, "r113r32", enabled=True)
    credential_id = _issue_credential(platform, "r113r32")
    now_s = int(time.time())
    old_base = now_s - 60
    counts = [0] * 61
    counts[old_base % 61] = 5
    _reset_rate_row(platform, credential_id, base_s=old_base, counts=counts)
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 5])
            (admitted,) = cur.fetchone()
    assert admitted is False, "a full count 60s ago must still be inside the 61-slot window and deny"


def test_rate_ring_shift_zeroes_only_the_shifted_range(platform: types.SimpleNamespace) -> None:
    """完了条件 33 (監督裁定3 の環) -- 変異 M33 (0 にする範囲を base_s ..
    base_s+shift-1 にずらす): a row with known counts at every position,
    `base_s` moved forward by a known `k` seconds, zeroes exactly the `k`
    positions `(base_s+1 .. base_s+k) mod 61` -- every other position's
    own count survives untouched."""
    _register_application(platform, "r113r33", enabled=True)
    credential_id = _issue_credential(platform, "r113r33")
    now_s = int(time.time())
    k = 5
    old_base = now_s - k
    counts = [i + 1 for i in range(61)]  # every position has a distinct, known, non-zero value
    _reset_rate_row(platform, credential_id, base_s=old_base, counts=counts)
    with psycopg.connect(platform.api_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_rate_fn(platform.schema), [credential_id, 10_000])
            (admitted,) = cur.fetchone()
    assert admitted is True
    base_after, counts_after = _read_rate_row(platform, credential_id)
    expected_zeroed = {(old_base + i) % 61 for i in range(1, k + 1)}
    incremented_idx = base_after % 61
    for idx in range(61):
        if idx == incremented_idx:
            # the incremented position: `(zeroed if it was in range else its
            # own original value) + 1` -- checked separately below, never
            # folded into either branch here (it is always the LAST
            # position of the zeroed range when shift < 61, so it would
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
        captured_flags.append(flags)
        return original_open(path, flags, mode)

    monkeypatch.setattr(concurrency_slots.os, "open", _spy_open)
    with slots.acquire(1):
        pass
    assert captured_flags, "no os.open call observed (空振り)"
    assert captured_flags[0] & os.O_CLOEXEC, f"slot fd was opened without O_CLOEXEC: {oct(captured_flags[0])}"


def test_flock_unexpected_errno_maps_to_backend_error_not_admitted_or_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完了条件 45 -- 変異 M45 (どの errno も「塞がっている」と読む)."""
    import errno as errno_module
    import fcntl

    slot_dir = tmp_path / "slots"
    slot_dir.mkdir(mode=0o700)
    slots = concurrency_slots.HostSharedConcurrencySlots(slot_dir)

    def _fake_flock(fd, op):
        if op & fcntl.LOCK_NB:
            raise OSError(errno_module.EPERM, "synthetic EPERM for M45")

    monkeypatch.setattr(concurrency_slots.fcntl, "flock", _fake_flock)
    with pytest.raises(concurrency_slots.SlotBackendError):
        with slots.acquire(1):
            pass


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
    """完了条件 70 -- 変異 M70 (pool を `DEFAULT_THREAD_LIMIT` から導く)."""
    assert role_pool_size(6) == 8


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


def test_http_adapter_wires_an_instance_scoped_slot_directory() -> None:
    """完了条件 76 -- 変異 M76 (adapter が slot を配線しない): a static pin
    of `conformance_adapter_r2db_http.py`'s own `DataService(...)` call
    site -- it passes `concurrency_slots=HostSharedConcurrencySlots(self.
    _slot_dir)`, the instance's own `mkdtemp`ed directory (real end-to-end
    coverage of this wiring is `conformance-tests/test_c32_shared_limits.
    py`'s own job, driven against the REAL launcher, never the in-process
    http plug -- this adapter's own construction is what this WP's own
    touched-file boundary actually owns)."""
    source = (Path(__file__).resolve().parents[1] / "conformance" / "conformance_adapter_r2db_http.py").read_text()
    assert "concurrency_slots=HostSharedConcurrencySlots(self._slot_dir)," in source


def test_http_adapter_wires_the_credential_store_as_the_rate_backend() -> None:
    """完了条件 77 -- 変異 M77 (adapter が PG の rate を配線しない): the
    SAME `DataService(...)` call site passes `rate=self._credentials`
    (the adapter's own `PostgresCredentialStore` -- the identical store
    its own read path already uses, 裁定15: no second pool)."""
    source = (Path(__file__).resolve().parents[1] / "conformance" / "conformance_adapter_r2db_http.py").read_text()
    assert "rate=self._credentials," in source
