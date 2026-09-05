"""`python -m mitatedb_api.ops {upgrade-applications,upgrade-status}` (Q4
phase, design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-4/D-5, work
order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-4
変更対象 E) -- direct, real-subprocess tests, in their own file (placement
confirmed by supervisor ruling 2026-09-05: upgrade-system subcommands get
their own file, separate from `test_ops_declarations.py`, which an
earlier WP already owns).

Duplicates a real-PostgreSQL bootstrap harness (rather than importing
`test_platform_upgrades.py`'s own -- this repository's own established
precedent of not taking cross-test-module import dependencies). Requires
its own copy of the migrations set rewritten under `MITATEDB_MIGRATIONS_
DIR` -- the real installed package `migrations/` directory names the
literal `mitatedb_registry`/`mitatedb_platform` this throwaway-prefixed
platform does not use (design R-4's own prefix-replacement convention);
`ops.py`'s own `_migrations_dir()` docstring documents this exact escape
hatch.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql_ok(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_ops_upgrade.py requires a reachable local PostgreSQL server. "
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
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbopsu{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    registry_schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_ops_upgrade_migrations")

    def _rewrite(name: str) -> Path:
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        return out

    rewritten = {
        name: _rewrite(name)
        for name in (
            "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
            "0003_provision_application.sql", "0004_deprovision_application.sql",
            "0006_declared_field_types_upgrade.sql", "0008_platform_upgrades_upgrade.sql",
        )
    }

    try:
        _run_psql_ok(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql_ok(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, provision_role=provision_role,
        platform_db=platform_db, registry_schema=registry_schema, migrations_dir=rewritten_dir,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform: types.SimpleNamespace, app_id: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql_ok(
        platform.provision_dsn, platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{app_id}"
    return types.SimpleNamespace(app_id=app_id, database=database)


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


def disable_application(platform: types.SimpleNamespace, app_id: str) -> None:
    """D-4(a) non-vacuity: `enabled` must not affect target selection."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET enabled = FALSE WHERE application_id = %s").format(
                    table=sql.Identifier(platform.registry_schema, "applications")),
                [app_id],
            )
    finally:
        conn.close()


def delete_ledger_row(admin_dsn: str, database: str, upgrade_number: int) -> None:
    conn = psycopg.connect(_dsn_with(admin_dsn, dbname=database), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public._mdb_platform_upgrades WHERE upgrade_number = %s", [upgrade_number])
    finally:
        conn.close()


def ledger_numbers(admin_dsn: str, database: str) -> frozenset[int]:
    conn = psycopg.connect(_dsn_with(admin_dsn, dbname=database))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT upgrade_number FROM public._mdb_platform_upgrades")
            return frozenset(row[0] for row in cur.fetchall())
    finally:
        conn.close()


def _run_ops(platform: types.SimpleNamespace, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["MITATEDB_PROVISION_DSN"] = platform.provision_dsn
    env["MITATEDB_PLATFORM_SCHEMA"] = platform.registry_schema
    env["MITATEDB_MIGRATIONS_DIR"] = str(platform.migrations_dir)
    for removed in (
        "MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL",
        "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS",
    ):
        env.pop(removed, None)
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args],
        capture_output=True, text=True, env=env,
    )


# ===========================================================================
# upgrade-applications
# ===========================================================================


def test_upgrade_applications_reports_no_pending_for_freshly_provisioned_apps(platform: types.SimpleNamespace) -> None:
    """完了条件 5 の帰結: 新規 provision (現行 0003) は既に `{6, 8}` を
    seed 済みなので、一括適用は何もせず終了コード 0。"""
    app = provision_app(platform, "opsclean")
    try:
        result = _run_ops(platform, "upgrade-applications")
        assert result.returncode == 0, result.stderr
        assert "0 failed" in result.stdout
    finally:
        deprovision_app(platform, "opsclean")


def test_upgrade_applications_applies_a_pending_number_and_updates_the_ledger(platform: types.SimpleNamespace) -> None:
    """完了条件 14/15: 台帳から 1 番号を落とし (穴を作る)、一括適用が
    集合差でそれを検出して当て、台帳が元に戻ること。"""
    app = provision_app(platform, "opspend")
    try:
        delete_ledger_row(platform.admin_dsn, app.database, 8)
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6})

        result = _run_ops(platform, "upgrade-applications", "--application", "opspend")
        assert result.returncode == 0, result.stderr
        assert "applied_after=[6, 8]" in result.stdout
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8})

        # idempotent: a second run with nothing pending does nothing.
        second = _run_ops(platform, "upgrade-applications", "--application", "opspend")
        assert second.returncode == 0, second.stderr
    finally:
        deprovision_app(platform, "opspend")


def test_upgrade_applications_visits_every_database_even_when_one_fails(platform: types.SimpleNamespace) -> None:
    """完了条件 15: 1 DB を失敗させても他 DB は処理され、失敗 DB が
    列挙されて終了コード 3 になる。失敗させる方法: 台帳から 8 を落とし、
    かつ台帳表の所有者を admin (superuser) に差し替えて developer role が
    `INSERT`/`REVOKE` できないようにする (実 PG での失敗注入、stub 不使用)。
    """
    ok_app = provision_app(platform, "opsok")
    bad_app = provision_app(platform, "opsbad")
    try:
        delete_ledger_row(platform.admin_dsn, ok_app.database, 8)
        delete_ledger_row(platform.admin_dsn, bad_app.database, 8)

        # Force the bad app's own script to fail: REVOKE the developer
        # role's privilege to write the ledger table it itself owns, by
        # reassigning ownership to the admin (superuser) role -- a
        # developer-role `INSERT` then fails with InsufficientPrivilege.
        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=bad_app.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("ALTER TABLE public._mdb_platform_upgrades OWNER TO CURRENT_USER")
                cur.execute("REVOKE ALL ON public._mdb_platform_upgrades FROM PUBLIC")
        finally:
            admin.close()

        result = _run_ops(platform, "upgrade-applications")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "opsok" in result.stdout and "opsbad" in result.stdout
        assert "FAILED to apply" in result.stdout
        assert "REVOKE" in result.stdout

        # the OK app was still processed despite the bad one failing.
        assert ledger_numbers(platform.admin_dsn, ok_app.database) == frozenset({6, 8})
    finally:
        deprovision_app(platform, "opsok")
        deprovision_app(platform, "opsbad")


def test_upgrade_applications_dry_run_reports_without_applying(platform: types.SimpleNamespace) -> None:
    """完了条件 17: `--dry-run` で未適用があれば終了コード 4、実際には
    何も適用しない。"""
    app = provision_app(platform, "opsdry")
    try:
        delete_ledger_row(platform.admin_dsn, app.database, 6)
        result = _run_ops(platform, "upgrade-applications", "--dry-run")
        assert result.returncode == 4, result.stdout + result.stderr
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({8})
    finally:
        deprovision_app(platform, "opsdry")


def test_upgrade_applications_dry_run_with_nothing_pending_returns_zero(platform: types.SimpleNamespace) -> None:
    app = provision_app(platform, "opsdry0")
    try:
        result = _run_ops(platform, "upgrade-applications", "--dry-run")
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        deprovision_app(platform, "opsdry0")


def test_upgrade_applications_script_flag_skips_already_recorded_databases(platform: types.SimpleNamespace) -> None:
    """完了条件 18: `--script` は未適用の DB にだけ当て、記録済みの DB
    では `recorded, skipped` 扱いで成功と数える。"""
    app = provision_app(platform, "opsskip")
    try:
        # already fully seeded ({6, 8}) -- --script 8 must be a no-op skip.
        result = _run_ops(platform, "upgrade-applications", "--application", "opsskip", "--script", "8")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "skipped (already recorded)" in result.stdout
    finally:
        deprovision_app(platform, "opsskip")


def test_upgrade_applications_script_flag_applies_only_that_number(platform: types.SimpleNamespace) -> None:
    """`--script` limits which SCRIPT ops chooses to run (design D-4(a)) --
    it does not itself constrain what that script's own body records.
    `0008`'s own body unconditionally backfills 6 whenever `_mdb_field_
    types` exists (this app's does, since it was provisioned via the
    current `0003`), so recording 8 alongside an already-present 6, or a
    freshly backfilled one, is the SCRIPT's own documented behavior, not
    this flag's."""
    app = provision_app(platform, "opsonly")
    try:
        delete_ledger_row(platform.admin_dsn, app.database, 8)
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6})

        result = _run_ops(platform, "upgrade-applications", "--application", "opsonly", "--script", "8")
        assert result.returncode == 0, result.stdout + result.stderr
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8})
    finally:
        deprovision_app(platform, "opsonly")


def test_upgrade_applications_script_0006_skips_a_database_that_already_has_a_ledger(platform: types.SimpleNamespace) -> None:
    """完了条件 27 (design D-4(f)): `--script 0006` の危険 -- 台帳表が
    既にある DB (このテストでは現行 0003 で新規 provision した DB、台帳
    `{6, 8}`) に `--script 6` を指定しても `0006` は実行されず
    `recorded, skipped` になり、`_mdb_field_types` に台帳表の 3 列
    (`upgrade_number`/`script_name`/`applied_at`) が混入しないこと。この
    防御は ops 側の「--script は未適用の DB にだけ当てる」だけに依存する
    (`0006` 自体は出荷済みで in-place 改訂できない、制約 1)。"""
    app = provision_app(platform, "opssix")
    try:
        result = _run_ops(platform, "upgrade-applications", "--application", "opssix", "--script", "6")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "skipped (already recorded)" in result.stdout

        conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database))
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND table_name = '_mdb_field_types' ORDER BY column_name"
                )
                columns = {row[0] for row in cur.fetchall()}
        finally:
            conn.close()
        assert "upgrade_number" not in columns
        assert "script_name" not in columns
        assert "applied_at" not in columns
    finally:
        deprovision_app(platform, "opssix")


def test_upgrade_applications_enabled_does_not_affect_target_selection(platform: types.SimpleNamespace) -> None:
    """design D-4(a): "enabled は対象選択に影響しない...無効化中の
    application の DB も一括適用の対象に含める"。"""
    app = provision_app(platform, "opsdis")
    try:
        disable_application(platform, "opsdis")
        delete_ledger_row(platform.admin_dsn, app.database, 8)
        result = _run_ops(platform, "upgrade-applications", "--application", "opsdis")
        assert result.returncode == 0, result.stdout + result.stderr
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8})
    finally:
        deprovision_app(platform, "opsdis")


def test_upgrade_applications_usage_error_without_provision_dsn() -> None:
    """完了条件 17 の終了コード 2 (使い方の誤り): provision DSN が env に
    無い。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    env.pop("MITATEDB_PROVISION_DSN", None)
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", "upgrade-applications"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 2, result.stdout + result.stderr


# ===========================================================================
# upgrade-status
# ===========================================================================


def test_upgrade_status_reports_applied_and_pending(platform: types.SimpleNamespace) -> None:
    """完了条件 19: provision DSN のみで動き、applied/pending/database_name
    を出す。"""
    app = provision_app(platform, "statusone")
    try:
        delete_ledger_row(platform.admin_dsn, app.database, 6)
        result = _run_ops(platform, "upgrade-status", "--application", "statusone")
        assert result.returncode == 4, result.stdout + result.stderr
        assert "applied=[8]" in result.stdout
        assert "pending=[6]" in result.stdout
        assert app.database in result.stdout
    finally:
        deprovision_app(platform, "statusone")


def test_upgrade_status_returns_zero_when_nothing_pending(platform: types.SimpleNamespace) -> None:
    app = provision_app(platform, "statuszero")
    try:
        result = _run_ops(platform, "upgrade-status", "--application", "statuszero")
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        deprovision_app(platform, "statuszero")


def test_upgrade_status_reports_empty_applied_for_an_application_with_no_ledger(platform: types.SimpleNamespace) -> None:
    """完了条件 19: 台帳が無い application は `applied = []`."""
    app = provision_app(platform, "statusnoled")
    try:
        conn = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=app.database), autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._mdb_platform_upgrades")
        finally:
            conn.close()
        result = _run_ops(platform, "upgrade-status", "--application", "statusnoled")
        assert result.returncode == 4, result.stdout + result.stderr
        assert "applied=[]" in result.stdout
        assert "pending=[6, 8]" in result.stdout
    finally:
        deprovision_app(platform, "statusnoled")


def test_upgrade_status_does_not_apply_anything() -> None:
    """非 vacuity companion, 静的照合: `cmd_upgrade_status` の本体に
    `_run_upgrade_script`/`subprocess` 呼び出しが無いこと (読み取り専用の
    実装であることのソース検査)。"""
    import ast

    source = (SRC_DIR / "mitatedb_api" / "ops.py").read_text()
    tree = ast.parse(source)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cmd_upgrade_status")
    calls = {n.func.id for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_run_upgrade_script" not in calls


# ===========================================================================
# M-1/M-2/M-3 (supervisor ruling 2026-09-05, 差し戻し裁定 2/3/4): 4 つの
# exit-code ケースと `database_name` NULL の失敗扱い、psql stderr の断片
# -- 同名テストを r2db-api の `test_ops_upgrade.py` にも置く (独立実装、
# cross-peer 共有なし)。
# ===========================================================================


def test_upgrade_applications_unknown_application_is_a_usage_error(platform: types.SimpleNamespace) -> None:
    """M-2(a): レジストリに存在しない `--application` は使い方の誤り
    (exit 2) であり、無音の exit 0 やエラー無視であってはならない。"""
    result = _run_ops(platform, "upgrade-applications", "--application", "totally_unregistered_id")
    assert result.returncode == 2, result.stdout + result.stderr


def test_upgrade_status_unknown_application_is_a_usage_error(platform: types.SimpleNamespace) -> None:
    """M-2(a) の `upgrade-status` 側: 同じ `_registry_applications_for_
    upgrade` を経由するので同じ exit 2 になること。"""
    result = _run_ops(platform, "upgrade-status", "--application", "totally_unregistered_id")
    assert result.returncode == 2, result.stdout + result.stderr


def test_upgrade_applications_missing_script_file_is_a_usage_error(platform: types.SimpleNamespace) -> None:
    """M-2(b): `_migrations_dir()` 配下に存在しない番号の `--script` は
    使い方の誤り (exit 2)。"""
    app = provision_app(platform, "scriptmiss")
    try:
        result = _run_ops(platform, "upgrade-applications", "--application", "scriptmiss", "--script", "1234")
        assert result.returncode == 2, result.stdout + result.stderr
    finally:
        deprovision_app(platform, "scriptmiss")


def test_upgrade_applications_script_number_unknown_to_the_package_is_a_usage_error(
    platform: types.SimpleNamespace,
) -> None:
    """M-2(c): `PLATFORM_UPGRADE_NUMBERS` (`{6, 8}`) に無い番号を
    `--script` に渡すのも (b) と同じ経路で exit 2 になること --
    「skipped (already recorded)」の偽報告(=無音の成功)であってはならない
    (review finding: この fix 以前は `_upgrade_one_application`'s own
    `script_filter not in pending_full` 分岐が真になり、`skipped` として
    偽の成功報告をしていた)。`42` はこの peer の `_migrations_dir()` に
    ファイルが無い番号であると同時に `PLATFORM_UPGRADE_NUMBERS` にも
    含まれない番号である。"""
    app = provision_app(platform, "scriptunk")
    try:
        result = _run_ops(platform, "upgrade-applications", "--application", "scriptunk", "--script", "42")
        assert result.returncode == 2, result.stdout + result.stderr
        assert "skipped (already recorded)" not in result.stdout
    finally:
        deprovision_app(platform, "scriptunk")


def test_upgrade_status_reports_a_never_provisioned_application_as_pending_everything(
    platform: types.SimpleNamespace,
) -> None:
    """M-2(d): レジストリに登録済みだが未 provision (`database_name`が
    NULL) の application を `--application` で名指しした `upgrade-status`
    は、行を出し (`database_name=None`、`pending`=全番号) つつ exit 4 で
    終わること -- 空の結果集合で無音の exit 0 になってはならない。

    MitateDB 自身の TWO-STATE レジストリ (design R-4) の下ではこの状態は
    実 provisioning 経路で自然に起こり得る -- `begin_provision_
    application` だけを呼び (`finish_provision_application`/完了した
    `0003` 実行を経ない)、そのまま残された行がこれである。"""
    conn = psycopg.connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {fn}(%s, %s, %s)").format(
                    fn=sql.Identifier(platform.registry_schema, "begin_provision_application")
                ),
                ["ghoststatus", secrets.token_urlsafe(24), secrets.token_urlsafe(24)],
            )
        conn.commit()
    finally:
        conn.close()

    result = _run_ops(platform, "upgrade-status", "--application", "ghoststatus")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "database None" in result.stdout
    assert "pending=[6, 8]" in result.stdout


def test_upgrade_applications_a_never_provisioned_application_named_explicitly_is_a_failure(
    platform: types.SimpleNamespace,
) -> None:
    """M-1 (supervisor ruling 2026-09-05, review): design D-4(e)'s own
    exit-code table names `database_name`がNULL explicitly as ONE of the
    two conditions exit code `3` covers ("psql exit 3、または
    `database_name`がNULL") -- a REAL (non-dry-run) `upgrade-applications`
    naming such an application explicitly must fail (exit 3), not
    silently succeed. See `test_upgrade_status_reports_a_never_
    provisioned_application_as_pending_everything`'s own docstring,
    immediately above, for why this state is naturally reachable on this
    peer (`begin_provision_application` alone, design R-4)."""
    conn = psycopg.connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {fn}(%s, %s, %s)").format(
                    fn=sql.Identifier(platform.registry_schema, "begin_provision_application")
                ),
                ["ghostapply", secrets.token_urlsafe(24), secrets.token_urlsafe(24)],
            )
        conn.commit()
    finally:
        conn.close()

    result = _run_ops(platform, "upgrade-applications", "--application", "ghostapply")
    assert result.returncode == 3, result.stdout + result.stderr


def test_upgrade_applications_failure_output_includes_the_psql_stderr_tail(platform: types.SimpleNamespace) -> None:
    """M-3 (supervisor ruling 2026-09-05, review): a failed `psql`
    invocation's own stderr is the ONLY place the actual PostgreSQL error
    text lives -- before this fix `_run_upgrade_script`'s own `(ok,
    output)` tuple was bound to `_output` and dropped by the caller.
    Reuses `test_upgrade_applications_visits_every_database_even_when_
    one_fails`'s own real failure-injection technique (REVOKE the
    developer role's own privilege on the ledger table it owns, forcing a
    real `InsufficientPrivilege` from a real `psql` subprocess) -- its own
    real stderr must now appear in this application's own output block."""
    bad_app = provision_app(platform, "stderrtail")
    try:
        delete_ledger_row(platform.admin_dsn, bad_app.database, 8)
        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=bad_app.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("ALTER TABLE public._mdb_platform_upgrades OWNER TO CURRENT_USER")
                cur.execute("REVOKE ALL ON public._mdb_platform_upgrades FROM PUBLIC")
        finally:
            admin.close()

        result = _run_ops(platform, "upgrade-applications", "--application", "stderrtail")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "psql stderr (tail)" in result.stdout
        assert "permission denied" in result.stdout
    finally:
        deprovision_app(platform, "stderrtail")


def test_upgrade_applications_enumeration_failure_is_exit_code_1(platform: types.SimpleNamespace) -> None:
    """監査 GAP A / 裁定 8 (supervisor ruling 2026-09-05): design D-4(e)'s
    own exit code `1` ("列挙に失敗した -- registryが読めない、provision
    DSNへ接続できない") was never observed by this file before this test --
    every existing case here asserts `0`/`2`/`3`/`4` only. An unreachable
    `MITATEDB_PROVISION_DSN` (a real, immediate connection-refused/timeout
    failure, never a stub) reaches `main()`'s own generic `except psycopg.
    Error: return 1` handler."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    env["MITATEDB_PROVISION_DSN"] = "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1"
    env["MITATEDB_PLATFORM_SCHEMA"] = platform.registry_schema
    env["MITATEDB_MIGRATIONS_DIR"] = str(platform.migrations_dir)
    for removed in (
        "MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL",
        "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS",
    ):
        env.pop(removed, None)
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", "upgrade-applications"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1, result.stdout + result.stderr


def test_upgrade_status_enumeration_failure_is_exit_code_1(platform: types.SimpleNamespace) -> None:
    """裁定 8 の `upgrade-status` 側: 同じ列挙経路 (`_registry_
    applications_for_upgrade`) を通るので同じ exit 1 になること。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    env["MITATEDB_PROVISION_DSN"] = "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1"
    env["MITATEDB_PLATFORM_SCHEMA"] = platform.registry_schema
    env["MITATEDB_MIGRATIONS_DIR"] = str(platform.migrations_dir)
    for removed in (
        "MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL",
        "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS",
    ):
        env.pop(removed, None)
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", "upgrade-status"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1, result.stdout + result.stderr


# ===========================================================================
# U-1 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査): 集計行の計数
# 規則 -- 両 peer で統一する。同名テストを r2db-api の `test_ops_upgrade.
# py` にも置く (独立実装、cross-peer 共有なし)。
# ===========================================================================


def test_upgrade_applications_tally_line_counts_one_of_each_outcome(platform: types.SimpleNamespace) -> None:
    """U-1: pins the trailing tally line's own COUNTING rule, not merely
    its string template -- 3 applications, one of each outcome, in a
    single bulk (no `--application`) run, must read exactly `1 succeeded,
    1 failed, 1 skipped (applied)`.

    `aggok` has `8` deleted from its own ledger before this run, so this
    run applies it back (succeeded, 適用を実行して成功した). `aggbad` also
    has `8` deleted, but its own ledger table's ownership is reassigned to
    the admin (superuser) role first, so the developer role's own
    `INSERT` fails with `InsufficientPrivilege` (failed -- same real
    failure-injection technique as `test_upgrade_applications_visits_
    every_database_even_when_one_fails`). `aggskip` is left exactly as
    `0003` provisioned it (`{6, 8}`, nothing pending at all) -- this run
    applies nothing to it at all (未適用なし、既に記録済み -> skipped,
    never a success, since nothing was actually run)."""
    ok_app = provision_app(platform, "aggok")
    bad_app = provision_app(platform, "aggbad")
    provision_app(platform, "aggskip")
    try:
        delete_ledger_row(platform.admin_dsn, ok_app.database, 8)
        delete_ledger_row(platform.admin_dsn, bad_app.database, 8)

        admin = psycopg.connect(_dsn_with(platform.admin_dsn, dbname=bad_app.database), autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute("ALTER TABLE public._mdb_platform_upgrades OWNER TO CURRENT_USER")
                cur.execute("REVOKE ALL ON public._mdb_platform_upgrades FROM PUBLIC")
        finally:
            admin.close()

        result = _run_ops(platform, "upgrade-applications")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "1 succeeded, 1 failed, 1 skipped (applied)" in result.stdout
        assert ledger_numbers(platform.admin_dsn, ok_app.database) == frozenset({6, 8})
    finally:
        deprovision_app(platform, "aggok")
        deprovision_app(platform, "aggbad")
        deprovision_app(platform, "aggskip")
