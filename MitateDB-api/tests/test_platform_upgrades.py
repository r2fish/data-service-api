"""Q4 phase WP-4 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3;
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
WP-4): the per-application platform-upgrade ledger (`public._mdb_
platform_upgrades`, created by the revised `0003_provision_application.
sql` for a NEW application and by `0008_platform_upgrades_upgrade.sql`
for an EXISTING one), the pure helpers `platform_upgrades.py` exposes
(`discover_upgrade_scripts`/`read_applied_upgrade_numbers`/`pending_
upgrade_numbers`/`require_application_upgrades_applied`/`summarize_
upgrade_run`), the backend bookkeeping-exclusion widening (`backend_
postgres.py::schema_count`), and the cell-open-time check (F-12, design
D-3(f)) `backend_postgres.PostgresBackend.__init__` now performs.

Real-PostgreSQL fixtures mirror `tests/test_postgres.py`'s own
established pattern (duplicated rather than imported -- this repository's
own precedent of not taking cross-test-module import dependencies,
independently applied here). Design R-8: these tests must not be
skipped -- a missing/unreachable local PostgreSQL server fails loudly.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.errors import StorageConfigurationError
from mitatedb_api.platform_upgrades import (LEDGER_TABLE_NAME, PEER_MODULE, PLATFORM_UPGRADE_NUMBERS,
                                            ApplicationUpgradeResult, PlatformUpgradeError,
                                            discover_upgrade_scripts, pending_upgrade_numbers,
                                            read_applied_upgrade_numbers,
                                            require_application_upgrades_applied, summarize_upgrade_run)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

# 常設規律 6 (Q4 phase, work order §4 変更対象 D): the two BEGIN/END
# marker comments `0003_provision_application.sql` itself carries around
# its own Q4-WP4 ledger block -- stripped below to reconstruct a
# synthetic "pre-Q4-WP4" provisioning template, for a legacy-application
# backfill test. Never derived from git history (this worktree's own
# HEAD moves as later WPs land) -- derived from the CURRENT file's own
# marker pair instead, so this fixture stays correct regardless of when
# it runs.
_LEDGER_BLOCK_BEGIN = "-- Q4-WP4-LEDGER-BEGIN"
_LEDGER_BLOCK_END = "-- Q4-WP4-LEDGER-END"


def _legacy_0003_text() -> str:
    text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text()
    start = text.index(_LEDGER_BLOCK_BEGIN)
    end = text.index(_LEDGER_BLOCK_END) + len(_LEDGER_BLOCK_END)
    # Also drop the trailing newline right after the END marker so the
    # reconstructed text reads exactly as if the block had never been
    # inserted (matching the surrounding blank-line rhythm the CURRENT
    # file keeps around it).
    return text[:start] + text[end + 1 :]


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    return subprocess.run(command, capture_output=True, text=True)


def _run_psql_ok(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    result = _run_psql(dsn, path, variables)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_platform_upgrades.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests must not be skipped "
            "(design R-8).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            leftover_databases = [row[0] for row in cur.fetchall()]
            for database in leftover_databases:
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """Bootstraps `0001`/`0002` under one throwaway prefix -- everything
    downstream (`provision_app`/`provision_legacy_app`) provisions
    per-test application databases against this SAME platform."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbupg{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_upgrades_migrations")

    def _rewrite(name: str, text: str) -> Path:
        out = rewritten_dir / name
        out.write_text(text.replace("mitatedb", prefix))
        return out

    rewritten: dict[str, Path] = {}
    rewritten["0001_bootstrap_platform.sql"] = _rewrite(
        "0001_bootstrap_platform.sql", (MIGRATIONS_DIR / "0001_bootstrap_platform.sql").read_text())
    rewritten["0002_registry_and_functions.sql"] = _rewrite(
        "0002_registry_and_functions.sql", (MIGRATIONS_DIR / "0002_registry_and_functions.sql").read_text())
    rewritten["0003_provision_application.sql"] = _rewrite(
        "0003_provision_application.sql", (MIGRATIONS_DIR / "0003_provision_application.sql").read_text())
    rewritten["0003_legacy_provision_application.sql"] = _rewrite(
        "0003_legacy_provision_application.sql", _legacy_0003_text())
    rewritten["0004_deprovision_application.sql"] = _rewrite(
        "0004_deprovision_application.sql", (MIGRATIONS_DIR / "0004_deprovision_application.sql").read_text())
    rewritten["0006_declared_field_types_upgrade.sql"] = _rewrite(
        "0006_declared_field_types_upgrade.sql",
        (MIGRATIONS_DIR / "0006_declared_field_types_upgrade.sql").read_text())
    rewritten["0008_platform_upgrades_upgrade.sql"] = _rewrite(
        "0008_platform_upgrades_upgrade.sql",
        (MIGRATIONS_DIR / "0008_platform_upgrades_upgrade.sql").read_text())

    try:
        _run_psql_ok(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql_ok(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        provision_role=provision_role,
        platform_db=platform_db,
        provision_script=rewritten["0003_provision_application.sql"],
        legacy_provision_script=rewritten["0003_legacy_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        backfill_script=rewritten["0006_declared_field_types_upgrade.sql"],
        upgrade_script=rewritten["0008_platform_upgrades_upgrade.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _app_namespace(platform: types.SimpleNamespace, app_id: str, runtime_password: str, developer_password: str) -> types.SimpleNamespace:
    database = f"{platform.prefix}_app_{app_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return types.SimpleNamespace(
        app_id=app_id, database=database, runtime_role=runtime_role, developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def provision_app(platform: types.SimpleNamespace, app_id: str) -> types.SimpleNamespace:
    """A NEW application, via the CURRENT (Q4-WP4-revised) `0003` --
    ledger seeded `{6, 8}` (design D-3(b)(i))."""
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql_ok(
        platform.provision_dsn, platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    return _app_namespace(platform, app_id, runtime_password, developer_password)


def provision_legacy_app(platform: types.SimpleNamespace, app_id: str) -> types.SimpleNamespace:
    """An EXISTING application -- provisioned via the RECONSTRUCTED
    pre-Q4-WP4 `0003` (no ledger table at all yet), the real state
    `0008_platform_upgrades_upgrade.sql` is meant to retrofit."""
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql_ok(
        platform.provision_dsn, platform.legacy_provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    return _app_namespace(platform, app_id, runtime_password, developer_password)


def deprovision_app(platform: types.SimpleNamespace, app_id: str) -> None:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql_ok(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


@pytest.fixture
def new_app(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "newapp")
    try:
        yield app
    finally:
        deprovision_app(platform, "newapp")


def _ledger_numbers(admin_dsn: str, database: str) -> frozenset[int] | None:
    conn = psycopg.connect(_dsn_with(admin_dsn, dbname=database))
    try:
        return read_applied_upgrade_numbers(conn, ledger_table_name=LEDGER_TABLE_NAME)
    finally:
        conn.close()


def _drop_field_types_table(admin_dsn: str, database: str) -> None:
    """Simulates an application that predates Phase 6 WP-3 entirely (its
    own `_mdb_field_types` table never existed) -- superuser DROP bypasses
    ordinary ownership rules, so this works regardless of which role
    created the table."""
    conn = psycopg.connect(_dsn_with(admin_dsn, dbname=database), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE public._mdb_field_types")
    finally:
        conn.close()


# ===========================================================================
# Pure-function tests (no PostgreSQL) -- discover/pending/summarize/F-12
# message. 常設規律 1: each observes at least one real, non-trivial case.
# ===========================================================================


def test_discover_upgrade_scripts_maps_number_to_path(tmp_path: Path) -> None:
    (tmp_path / "0006_declared_field_types_upgrade.sql").write_text("-- 6\n")
    (tmp_path / "0008_platform_upgrades_upgrade.sql").write_text("-- 8\n")
    (tmp_path / "0003_provision_application.sql").write_text("-- not an upgrade script\n")
    discovered = discover_upgrade_scripts(tmp_path)
    assert discovered == {
        6: tmp_path / "0006_declared_field_types_upgrade.sql",
        8: tmp_path / "0008_platform_upgrades_upgrade.sql",
    }


def test_pending_upgrade_numbers_with_no_ledger_table_is_everything() -> None:
    assert pending_upgrade_numbers(None, frozenset({6, 8})) == (6, 8)


def test_pending_upgrade_numbers_is_a_set_difference_not_a_maximum() -> None:
    """design D-4(b)'s own non-vacuity requirement: a ledger holding `{8}`
    (6 missing -- a HOLE, not merely "nothing recorded yet") must report 6
    as pending, proving this is a set difference, never a "largest applied
    number" comparison (which would see 8 >= 6 and wrongly call 6 done)."""
    assert pending_upgrade_numbers(frozenset({8}), frozenset({6, 8})) == (6,)
    assert pending_upgrade_numbers(frozenset({6, 8}), frozenset({6, 8})) == ()


def test_summarize_upgrade_run_dry_run_exit_codes() -> None:
    no_pending = ApplicationUpgradeResult("a", "db", (6, 8), (6, 8), (), (), (), None)
    has_pending = ApplicationUpgradeResult("a", "db", (8,), (8,), (6,), (), (), None)
    assert summarize_upgrade_run([no_pending], dry_run=True) == 0
    assert summarize_upgrade_run([has_pending], dry_run=True) == 4


def test_summarize_upgrade_run_apply_exit_codes() -> None:
    all_applied = ApplicationUpgradeResult("a", "db", (), (6, 8), (), (), (), None)
    one_failed = ApplicationUpgradeResult("a", "db", (), (6,), (8,), (8,), (), "REVOKE ...")
    assert summarize_upgrade_run([all_applied], dry_run=False) == 0
    assert summarize_upgrade_run([all_applied, one_failed], dry_run=False) == 3


def test_f12_message_matches_design_section_3_8_verbatim() -> None:
    """設計 §3.8 F-12 の骨子を逐語で assert する (常設規律 4, work order
    §4 WP-4 完了条件 11)。番号列挙・`ops upgrade-applications`・
    `--dry-run` の案内をすべて含み、DSN・資格情報・内部ホスト名・宣言値を
    含まない (SI-10)。"""
    try:
        require_application_upgrades_applied(
            _FakeConnMissingLedger(), ledger_table_name=LEDGER_TABLE_NAME, expected=PLATFORM_UPGRADE_NUMBERS,
            application_id="acme", ops_module=PEER_MODULE,
        )
    except PlatformUpgradeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected PlatformUpgradeError")
    assert message == (
        "This application's storage is missing platform upgrade(s) 6, 8: the deployment must apply them "
        "before this application can serve requests. Run 'python -m mitatedb_api.ops upgrade-applications' "
        "(its '--dry-run' shows applied and pending per application), then retry."
    )
    for forbidden in ("dsn", "DSN=", "password", "://", "host="):
        assert forbidden not in message


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        raise psycopg.errors.UndefinedTable("relation does not exist")


class _FakeConnMissingLedger:
    """A minimal stand-in for a `psycopg.Connection` whose own ledger
    table does not exist -- used only to exercise `require_application_
    upgrades_applied`'s pure control flow (no real PostgreSQL round trip
    needed for THIS particular case, which is also covered against a real
    server below)."""
    def cursor(self):
        return _FakeCursor()

    def rollback(self):
        pass


def test_require_application_upgrades_applied_passes_when_nothing_pending() -> None:
    class _EmptyPendingConn:
        def cursor(self):
            class _Cur:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *exc):
                    return False

                def execute(self_inner, *args, **kwargs):
                    pass

                def fetchall(self_inner):
                    return [(6,), (8,)]
            return _Cur()

    require_application_upgrades_applied(
        _EmptyPendingConn(), ledger_table_name=LEDGER_TABLE_NAME, expected=PLATFORM_UPGRADE_NUMBERS,
        application_id="acme", ops_module=PEER_MODULE,
    )  # must not raise


# ===========================================================================
# Real-PostgreSQL tests -- design D-3/D-4, work order §4 WP-4 completion
# conditions 1-11 (MitateDB numbering: r2db-api's own condition 9, the
# RLS-monitoring-VIEW check, does not exist on this peer, design §3.10:
# "MitateDB に同型のビューは無い").
# ===========================================================================


def test_template_seeds_the_full_number_set_for_a_new_application(new_app: types.SimpleNamespace, platform: types.SimpleNamespace) -> None:
    """完了条件 5: a NEWLY provisioned application's own ledger already
    carries `{6, 8}` -- `0003`'s own revision seeds it directly, no
    per-application upgrade script ever needs to run against it."""
    assert _ledger_numbers(platform.admin_dsn, new_app.database) == frozenset({6, 8})


def test_runtime_role_has_select_only_on_the_ledger(new_app: types.SimpleNamespace) -> None:
    """完了条件 6 (U-2 逐語: runtime role には SELECT のみ)."""
    conn = psycopg.connect(new_app.runtime_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT upgrade_number FROM public.{}").format(sql.Identifier(LEDGER_TABLE_NAME)))
            assert set(row[0] for row in cur.fetchall()) == {6, 8}
        conn.rollback()
        for statement in (
            sql.SQL("INSERT INTO public.{} (upgrade_number, script_name) VALUES (99, 'x')").format(sql.Identifier(LEDGER_TABLE_NAME)),
            sql.SQL("UPDATE public.{} SET script_name = 'x' WHERE upgrade_number = 6").format(sql.Identifier(LEDGER_TABLE_NAME)),
            sql.SQL("DELETE FROM public.{} WHERE upgrade_number = 6").format(sql.Identifier(LEDGER_TABLE_NAME)),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.cursor() as cur:
                    cur.execute(statement)
            conn.rollback()
    finally:
        conn.close()


def test_provision_role_can_read_the_ledger_via_dbname_swap(new_app: types.SimpleNamespace, platform: types.SimpleNamespace) -> None:
    """完了条件 7 (design D-3(a) の `GRANT SELECT ... TO SESSION_USER`):
    `ops upgrade-status`/`--dry-run` の唯一の読み出し経路。付与が無いと
    `permission denied` になる。"""
    app_dsn = _dsn_with(platform.provision_dsn, dbname=new_app.database)
    conn = psycopg.connect(app_dsn)
    try:
        assert read_applied_upgrade_numbers(conn, ledger_table_name=LEDGER_TABLE_NAME) == frozenset({6, 8})
    finally:
        conn.close()


def test_ledger_table_has_no_row_level_security(new_app: types.SimpleNamespace, platform: types.SimpleNamespace) -> None:
    """完了条件 8 (design D-3(a) 監督裁定: FORCE RLS だと provision ->
    SET ROLE developer の書き込みが拒まれる)。"""
    conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=new_app.database))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", [LEDGER_TABLE_NAME])
            relrowsecurity, relforcerowsecurity = cur.fetchone()
        assert relrowsecurity is False
        assert relforcerowsecurity is False
    finally:
        conn.close()


def test_schema_count_excludes_the_ledger_table(new_app: types.SimpleNamespace) -> None:
    """完了条件 10 (design D-3(e)(i): 台帳表を作ったことで `schema_
    objects` 会計が +1 ずれてはならない)。新規 provision 直後は 0、実
    entity を 1 つ作ると 1 になる -- 台帳・schema_revision・field_types
    のいずれも数えられていないことの実測。"""
    backend = PostgresBackend(new_app.runtime_dsn, new_app.developer_dsn)
    try:
        assert backend.schema_count() == 0
        backend.create_collection("widgets", {"title": "text"})
        assert backend.schema_count() == 1
    finally:
        backend.close()


def test_catalog_never_lists_the_ledger_table(new_app: types.SimpleNamespace) -> None:
    """design §3.10 の非対称記録の裏取り: MitateDB の catalog は
    `_mdb_field_types` 由来であり、`_mdb_platform_upgrades` は entity
    列挙に現れない (r2db の `_load_catalog` 除外とは異なる経路)。"""
    backend = PostgresBackend(new_app.runtime_dsn, new_app.developer_dsn)
    try:
        assert backend.all_field_types() == {}
    finally:
        backend.close()


def test_upgrade_script_is_idempotent(platform: types.SimpleNamespace) -> None:
    """完了条件 2: 2 回適用して終状態が同一。"""
    app = provision_legacy_app(platform, "idem")
    try:
        _run_psql_ok(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        first = _ledger_numbers(platform.admin_dsn, app.database)
        _run_psql_ok(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        second = _ledger_numbers(platform.admin_dsn, app.database)
        # legacy provisioning still creates `_mdb_field_types` (that table
        # predates Q4 phase entirely) -- so `0008` backfills 6 too.
        assert first == second == frozenset({6, 8})
    finally:
        deprovision_app(platform, "idem")


def test_upgrade_script_has_no_q_skip_path() -> None:
    """完了条件 3: 監査照合 -- `grep -n '\\q' 0008_*.sql` が 0 件。"""
    text = (MIGRATIONS_DIR / "0008_platform_upgrades_upgrade.sql").read_text()
    assert "\\q" not in text


def test_failed_upgrade_script_leaves_no_ledger_row(platform: types.SimpleNamespace) -> None:
    """完了条件 4: 本体に失敗を注入 (台帳表を先に別所有者で作っておき、
    developer role が REVOKE/INSERT できないようにする) すると psql が
    非 0 で終わり、台帳表に行が無いこと (作られていたとしても 0 行)。"""
    app = provision_legacy_app(platform, "failinj")
    try:
        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(
                    "CREATE TABLE public._mdb_platform_upgrades "
                    "(upgrade_number integer PRIMARY KEY, script_name text NOT NULL, "
                    "applied_at timestamptz NOT NULL DEFAULT now())"
                )
        finally:
            admin.close()

        result = _run_psql(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        assert result.returncode != 0

        conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database))
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM public._mdb_platform_upgrades")
                assert cur.fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        deprovision_app(platform, "failinj")


def test_ledger_insert_and_backfill_share_one_atomic_transaction(platform: types.SimpleNamespace) -> None:
    """完了条件 4 の追加実測 (レビュー観点 3, §10 の非 vacuity: 「トラン
    ザクション内の位置は静的には検査しない...実 PG テストが担保する」):
    自番号 (8) の INSERT と backfill (6) の INSERT が同じトランザクション
    に入っていること -- 台帳表を developer role の所有として先に作り、
    backfill 側だけを CHECK 制約で失敗させると、自番号 INSERT も一緒に
    ロールバックされ、台帳が 0 行のまま残ること (「自番号だけは生き残る」
    ような部分適用にならないこと)。台帳 INSERT が `COMMIT` の外や別
    トランザクションへ移動すると、この観測は破れる (変異 3 の対象)。"""
    app = provision_legacy_app(platform, "atomic")
    try:
        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(app.developer_role)))
                cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(app.developer_role)))
                cur.execute(
                    "CREATE TABLE public._mdb_platform_upgrades ("
                    "upgrade_number integer PRIMARY KEY, "
                    "script_name text NOT NULL CHECK (script_name <> '0006_declared_field_types_upgrade.sql'), "
                    "applied_at timestamptz NOT NULL DEFAULT now())"
                )
                cur.execute("RESET ROLE")
        finally:
            admin.close()

        result = _run_psql(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        assert result.returncode != 0

        conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database))
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM public._mdb_platform_upgrades")
                assert cur.fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        deprovision_app(platform, "atomic")


def test_backfill_records_6_when_field_types_table_exists(platform: types.SimpleNamespace) -> None:
    """完了条件 25 (a): `_mdb_field_types` が既にある DB -- `0006` は
    既に適用済みだったと backfill され、台帳は `{6, 8}` になる."""
    app = provision_legacy_app(platform, "bkfyes")
    try:
        _run_psql_ok(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        assert _ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8})
    finally:
        deprovision_app(platform, "bkfyes")


def test_backfill_leaves_6_pending_when_field_types_table_is_absent(platform: types.SimpleNamespace) -> None:
    """完了条件 25 (b) / 26: `_mdb_field_types` が無い DB (Phase 6 WP-3
    以前からの真に古いアプリケーションを模す) -- `0008` は 6 を記録せず、
    台帳は `{8}` のみになる。集合差の定義により 6 は pending として残る
    (最大番号方式なら `8 >= 6` で誤って済んだことにされるところ)。"""
    app = provision_legacy_app(platform, "bkfno")
    try:
        _drop_field_types_table(platform.admin_dsn, app.database)
        _run_psql_ok(platform.provision_dsn, platform.upgrade_script, {"app_id": app.app_id})
        applied = _ledger_numbers(platform.admin_dsn, app.database)
        assert applied == frozenset({8})
        assert pending_upgrade_numbers(applied, PLATFORM_UPGRADE_NUMBERS) == (6,)

        # 完了条件 26 の後半: 後から 0006 を実際に当てれば 6 も記録される
        # (0006 自身の CREATE TABLE IF NOT EXISTS が今度こそ実行される)。
        _run_psql_ok(platform.provision_dsn, platform.backfill_script, {"app_id": app.app_id})
        applied_after = _ledger_numbers(platform.admin_dsn, app.database)
        assert applied_after is None or 6 not in applied_after  # 0006 自体は台帳に自番号 INSERT を持たない (許可リスト免除)
    finally:
        deprovision_app(platform, "bkfno")


def test_cell_open_check_raises_service_unavailable_for_missing_upgrade(platform: types.SimpleNamespace) -> None:
    """完了条件 11 (F-12), Q4 rework (supervisor ruling 2026-09-05, H-1 =
    (a)): 台帳に未適用番号がある DB (台帳表そのものが無い場合を含む) で、
    `PostgresBackend(...)` 構築 (= cell open) 自体は例外を送出しない
    (H-1(a): 起動は止めない) -- 構築後の実操作 (`all_field_types()`) が
    `StorageConfigurationError` (具体的には `errors.PlatformUpgradePending`
    のサブクラスインスタンス -- `isinstance` は基底クラスにもマッチする)
    を送出し、メッセージが未適用の番号と `ops upgrade-applications` を
    示すこと。"""
    # (a) ledger table entirely absent (a legacy app, never upgraded).
    legacy = provision_legacy_app(platform, "f12nol")
    try:
        backend = PostgresBackend(legacy.runtime_dsn, legacy.developer_dsn, application_id=legacy.app_id)
        try:
            with pytest.raises(StorageConfigurationError) as excinfo:
                backend.all_field_types()
            assert "missing platform upgrade(s) 6, 8" in str(excinfo.value)
            assert "ops upgrade-applications" in str(excinfo.value)
        finally:
            backend.close()
    finally:
        deprovision_app(platform, "f12nol")

    # (b) ledger table present but missing one number (delete a row from
    # an otherwise-fully-seeded new application).
    partial = provision_app(platform, "f12part")
    try:
        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=partial.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM public.{} WHERE upgrade_number = 8").format(sql.Identifier(LEDGER_TABLE_NAME)))
        finally:
            admin.close()
        backend = PostgresBackend(partial.runtime_dsn, partial.developer_dsn, application_id=partial.app_id)
        try:
            with pytest.raises(StorageConfigurationError) as excinfo:
                backend.all_field_types()
            assert "missing platform upgrade(s) 8" in str(excinfo.value)
        finally:
            backend.close()
    finally:
        deprovision_app(platform, "f12part")


def test_build_app_style_construction_never_raises_even_when_a_ledger_is_incomplete(
    platform: types.SimpleNamespace,
) -> None:
    """裁定 1 (H-1 = (a), supervisor ruling 2026-09-05, review H-1): the
    headline claim at the `PostgresBackend` unit level -- constructing a
    backend for an application whose own ledger is missing an upgrade
    must NOT raise (a mutation reverting `__init__` back to raising
    `StorageConfigurationError`/`PlatformUpgradePending` directly would
    fail this test at construction time, before any operation is ever
    attempted). The full real-HTTP observation (`build_app` itself
    starting, `GET /v1/catalog` returning 200 for a healthy sibling
    application and 503 with the F-12 message for this one) lives in
    `test_main.py::test_build_app_h1_serves_every_application_and_
    refuses_only_the_one_with_a_pending_upgrade`."""
    legacy = provision_legacy_app(platform, "f12ctor")
    try:
        backend = PostgresBackend(legacy.runtime_dsn, legacy.developer_dsn, application_id=legacy.app_id)
        try:
            assert backend._pending_platform_upgrade_message is not None
            assert "missing platform upgrade(s) 6, 8" in backend._pending_platform_upgrade_message
        finally:
            backend.close()
    finally:
        deprovision_app(platform, "f12ctor")


def test_cell_open_check_passes_for_a_fully_upgraded_application(new_app: types.SimpleNamespace) -> None:
    """非空振り companion: a fully-seeded application must NOT raise --
    proves the check above is discriminating, not merely always-fail."""
    backend = PostgresBackend(new_app.runtime_dsn, new_app.developer_dsn, application_id=new_app.app_id)
    backend.close()


def test_cell_open_check_is_skipped_when_no_application_id_is_given(new_app: types.SimpleNamespace, platform: types.SimpleNamespace) -> None:
    """非 vacuity companion: a bare, application-context-free
    `PostgresBackend` (test/tooling callers, `application_id=None`
    default) must never perform this check -- proven by deliberately
    leaving a number missing and constructing the backend with no
    `application_id` anyway, which must succeed."""
    admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=new_app.database), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM public.{} WHERE upgrade_number = 8").format(sql.Identifier(LEDGER_TABLE_NAME)))
    finally:
        admin.close()
    backend = PostgresBackend(new_app.runtime_dsn, new_app.developer_dsn)
    backend.close()
