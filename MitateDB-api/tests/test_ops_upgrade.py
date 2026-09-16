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

# In-process unit tests
# for `_run_upgrade_script`/`_run_deprovision_script`/`_redact_connection_
# values` below call these module-level names directly -- this is the
# first use of an in-process `mitatedb_api.ops` import in this file (every
# other test here drives the CLI as a real subprocess via `_run_ops`).
import mitatedb_api.ops as ops

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


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
            # Phase 9 WP-3a (design docs/design/
            # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/
            # (4)): this rewritten `MITATEDB_MIGRATIONS_DIR` is what `ops.py`'s
            # own `discover_upgrade_scripts` scans for every subprocess this
            # file's own `_run_ops` launches -- omitting this file here would
            # make `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` (imported
            # normally, not path-dependent) require number 9 that no script
            # in this directory can ever resolve to.
            "0009_field_constraints_upgrade.sql",
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
    # design D-2: this
    # file's own throwaway-cluster launcher (`tools/testpg/dsa_testpg.
    # py`) exports `PGPORT`/`PGUSER`/`PGPASSFILE` ambiently so a bare
    # `psql`/libpq call defaults to the SAME cluster -- convenient, but
    # `platform.provision_dsn` above already carries every connection
    # parameter this subcommand needs explicitly, so those ambient
    # exports are pure interference for `_psql_connection_env`'s own
    # A-13 fail-closed check inside the CHILD process spawned below
    # (never for THIS process' own `os.environ`, which other helpers in
    # this file still rely on for their own direct `psycopg.connect`
    # admin access).
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args],
        capture_output=True, text=True, env=env,
    )


# ===========================================================================
# upgrade-applications
# ===========================================================================


def test_upgrade_applications_reports_no_pending_for_freshly_provisioned_apps(platform: types.SimpleNamespace) -> None:
    """完了条件 5 の帰結: 新規 provision (現行 0003) は既に `{6, 8, 9, 10}`
    (Phase 9 WP-3a の 9 = `0009_field_constraints_upgrade.sql` を含む) を
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
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 9, 10})

        result = _run_ops(platform, "upgrade-applications", "--application", "opspend")
        assert result.returncode == 0, result.stderr
        assert "applied_after=[6, 8, 9, 10]" in result.stdout
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8, 9, 10})

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
        assert ledger_numbers(platform.admin_dsn, ok_app.database) == frozenset({6, 8, 9, 10})
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
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({8, 9, 10})
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
        # already fully seeded ({6, 8, 9, 10}) -- --script 8 must be a no-op skip.
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
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 9, 10})

        result = _run_ops(platform, "upgrade-applications", "--application", "opsonly", "--script", "8")
        assert result.returncode == 0, result.stdout + result.stderr
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8, 9, 10})
    finally:
        deprovision_app(platform, "opsonly")


def test_upgrade_applications_script_0006_skips_a_database_that_already_has_a_ledger(platform: types.SimpleNamespace) -> None:
    """完了条件 27 (design D-4(f)): `--script 0006` の危険 -- 台帳表が
    既にある DB (このテストでは現行 0003 で新規 provision した DB、台帳
    `{6, 8, 9, 10}`) に `--script 6` を指定しても `0006` は実行されず
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
        assert ledger_numbers(platform.admin_dsn, app.database) == frozenset({6, 8, 9, 10})
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
        assert "applied=[8, 9, 10]" in result.stdout
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
        assert "pending=[6, 8, 9, 10]" in result.stdout
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
    """M-2(c): `PLATFORM_UPGRADE_NUMBERS` (`{6, 8, 9, 10}`) に無い番号を
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
    assert "pending=[6, 8, 9, 10]" in result.stdout


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
    `0003` provisioned it (`{6, 8, 9, 10}`, nothing pending at all) -- this run
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
        assert ledger_numbers(platform.admin_dsn, ok_app.database) == frozenset({6, 8, 9, 10})
    finally:
        deprovision_app(platform, "aggok")
        deprovision_app(platform, "aggbad")
        deprovision_app(platform, "aggskip")


# ===========================================================================
# Completion conditions 19-4/19-5/19-6: in-process unit tests for the psql-invocation helpers,
# monkeypatching `subprocess.run` rather than requiring a real failing
# migration script -- the property under test (argv/env shape, and
# redaction of a psql failure's own captured output) does not depend on
# which SQL actually ran.
# ===========================================================================

def _clear_ambient_pg_connection_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """design D-2: this
    file's own throwaway-cluster launcher (`tools/testpg/dsa_testpg.py`)
    exports `PGPORT`/`PGUSER`/`PGPASSFILE` at the PROCESS level for a
    bare `psql`/libpq default -- OTHER helpers in this file (e.g.
    `delete_ledger_row`'s own `psycopg.connect(admin_dsn, ...)`) rely on
    that ambient `PGPASSFILE` for authentication and must keep seeing it,
    so this is called explicitly by the handful of tests below that
    exercise `_psql_connection_env`'s own A-13 fail-closed check
    in-process, never as a file-wide autouse fixture."""
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)


_SENTINEL_DSN = "postgresql://sentinel_user_c3f1:sentinel_pw_7a2e@sentinel-host-b91d.invalid:6543/sentinel_db_44de"
_SENTINEL_VALUES = ("sentinel_user_c3f1", "sentinel_pw_7a2e", "sentinel-host-b91d.invalid", "sentinel_db_44de")
#: A-14 (rework 2): a canned `psql --version` output the fakes below
#: return so a mocked `subprocess.run` still satisfies the version gate
#: `_run_upgrade_script`/`_run_deprovision_script` now check first.
_FAKE_PSQL_VERSION_STDOUT = "psql (PostgreSQL) 16.14 (Homebrew)\n"


def test_run_upgrade_script_passes_connection_params_via_env_never_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 19-5: none of the DSN's own 4 sentinel values
    reach the psql subprocess's own argv; all 4 reach it through the
    matching libpq environment variable instead. Non-空振り: `calls` is
    asserted non-empty before inspecting its content."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    calls: list[tuple[list[str], dict]] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001 -- matches subprocess.run's own loose signature
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1")

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    argv_text = " ".join(cmd)
    for value in _SENTINEL_VALUES:
        assert value not in argv_text, f"{value!r} leaked into psql argv: {cmd!r}"
    env = kwargs["env"]
    assert env["PGUSER"] == "sentinel_user_c3f1"
    assert env["PGPASSWORD"] == "sentinel_pw_7a2e"
    assert env["PGHOST"] == "sentinel-host-b91d.invalid"
    assert env["PGDATABASE"] == "sentinel_db_44de"


def test_run_deprovision_script_passes_connection_params_via_env_never_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Completion condition 19-5, `_run_deprovision_script`'s own psql
    call. Uses a real (empty) file for the script path -- this function
    checks `script.exists()` before invoking psql at all."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    script = tmp_path / "0004_deprovision_application.sql"
    script.write_text("-- empty\n")
    monkeypatch.setattr(ops, "_migrations_dir", lambda: tmp_path)
    calls: list[tuple[list[str], dict]] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_deprovision_script(_SENTINEL_DSN, "app1")

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    argv_text = " ".join(cmd)
    for value in _SENTINEL_VALUES:
        assert value not in argv_text, f"{value!r} leaked into psql argv: {cmd!r}"
    env = kwargs["env"]
    assert env["PGUSER"] == "sentinel_user_c3f1"
    assert env["PGHOST"] == "sentinel-host-b91d.invalid"


def test_run_upgrade_script_redacts_connection_values_from_a_failed_psql_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 19-4: a failed psql invocation's own stdout/
    stderr (simulating libpq echoing connection details in a diagnostic,
    design §3.1) has every one of the DSN's 4 sentinel values replaced by
    the fixed `<redacted>` marker before `_run_upgrade_script` returns it
    -- the SQL-level part of the message (unrelated to any of the 4
    values) survives untouched."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        raw = (
            f"psql: error: connection to server at \"sentinel-host-b91d.invalid\", port 6543 failed\n"
            f"FATAL:  password authentication failed for user \"sentinel_user_c3f1\"\n"
            f"detail: database \"sentinel_db_44de\" pending; secret sentinel_pw_7a2e rejected\n"
            f"ERROR:  syntax error at or near \"CREATE\""
        )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=raw)

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ok, output = ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1")

    assert ok is False
    for value in _SENTINEL_VALUES:
        assert value not in output, f"{value!r} leaked into redacted output: {output!r}"
    assert "<redacted>" in output
    assert "syntax error at or near" in output  # SQL-level diagnostic survives


def test_run_deprovision_script_redacts_connection_values_before_dying(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Completion condition 19-6: `_run_deprovision_script`'s own `_die`
    call on a failed psql invocation carries the SAME redaction as 19-4 --
    exercised through the real `_die`/`SystemExit(2)` path, not a mock."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    script = tmp_path / "0004_deprovision_application.sql"
    script.write_text("-- empty\n")
    monkeypatch.setattr(ops, "_migrations_dir", lambda: tmp_path)

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        raw = f"FATAL:  role \"sentinel_user_c3f1\" does not exist on host sentinel-host-b91d.invalid"
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=raw)

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    with pytest.raises(SystemExit) as excinfo:
        ops._run_deprovision_script(_SENTINEL_DSN, "app1")
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    for value in _SENTINEL_VALUES:
        assert value not in captured.err, f"{value!r} leaked into _die output: {captured.err!r}"
    assert "<redacted>" in captured.err


def test_redact_connection_values_leaves_unrelated_text_untouched() -> None:
    """Direct unit test of `_redact_connection_values` itself: all 4
    sentinel values disappear, and text that shares no substring with any
    of them survives byte-for-byte."""
    text = "before " + " ".join(_SENTINEL_VALUES) + " after; unique-marker-9f21 stays"
    redacted = ops._redact_connection_values(text, _SENTINEL_DSN)
    for value in _SENTINEL_VALUES:
        assert value not in redacted
    assert "unique-marker-9f21 stays" in redacted
    assert redacted.count("<redacted>") == 4


def test_upgrade_one_application_redacts_connection_values_on_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion condition 19-4 (MitateDB-api's own connection-failure
    sub-path): `_upgrade_one_application`'s own `failure_detail=str(exc)`
    branch (a failed `psycopg.connect(app_dsn)`) has every one of the
    DSN's 4 sentinel values redacted before the result is returned."""
    sentinel_dsn = _SENTINEL_DSN
    raw_message = (
        'connection to server at "sentinel-host-b91d.invalid", port 6543 failed: '
        'FATAL:  password authentication failed for user "sentinel_user_c3f1"'
    )
    # user/host appear in raw_message; password never does (§3.1's own
    # probed fact: "正しい形の DSN で接続に失敗したときは、password は
    # 例外文字列に載らない") -- redaction of password is still checked
    # below via the DSN-derived value, not via its presence here.
    for value in (_SENTINEL_VALUES[0], _SENTINEL_VALUES[2]):  # user, host
        assert value in raw_message

    def _fake_connect(dsn, **kwargs):  # noqa: ANN001
        raise psycopg.OperationalError(raw_message)

    monkeypatch.setattr(ops.psycopg, "connect", _fake_connect)
    result = ops._upgrade_one_application(
        provision_dsn=sentinel_dsn, provision_role="prov_role", application_id="app1",
        database_name="sentinel_db_44de", developer_role="app1_dv",
        migrations_by_number={}, script_filter=None, dry_run=False,
    )
    assert result.failure_detail is not None
    for value in _SENTINEL_VALUES:
        assert value not in result.failure_detail, f"{value!r} leaked into failure_detail: {result.failure_detail!r}"
    assert "<redacted>" in result.failure_detail


# ===========================================================================
# A code-review probe (synthetic values only) found 3 gaps in the
# first pass -- a sequential per-value `str.replace` could leave a
# longer/more-sensitive value's own tail exposed when a shorter value is
# its literal prefix; a multi-host DSN's own comma-joined `host`/
# `hostaddr`/`port` conninfo value never matches the raw diagnostic text
# (which names each host/port separately); the allow-list only covered 7
# keys and the child psql process inherited the PARENT's own `PG*`
# environment for any parameter the DSN itself did not set.
# ===========================================================================


def test_redact_connection_values_handles_prefix_overlap_and_multi_host_dsn() -> None:
    """user (`svcuser`) is a literal PREFIX of both password
    (`svcuser_SECRETTAIL9x3f`) and dbname (`svcuser_DBTAIL7e2a`); host/port
    are a 2-element, comma-joined multi-host DSN. Checking only the 3
    FULL values would pass even with the prefix-overlap bug this test
    exists to catch (a sequential, non-length-ordered replace redacts the
    SHORT `svcuser` prefix first and leaves each longer value's own TAIL
    -- `_SECRETTAIL9x3f`/`_DBTAIL7e2a` -- exposed as leftover plain text
    beside the `<redacted>` marker); asserting the tails absent directly
    is what actually exercises the longest-first ordering."""
    dsn = "postgresql://svcuser:svcuser_SECRETTAIL9x3f@hostA.invalid:5432,hostB.invalid:5433/svcuser_DBTAIL7e2a"
    text = (
        'FATAL: password authentication failed for user "svcuser"; '
        "secret was svcuser_SECRETTAIL9x3f; "
        'connection to server at "hostA.invalid", port 5432 failed; '
        'connection to server at "hostB.invalid", port 5433 failed; '
        'dbname "svcuser_DBTAIL7e2a" pending'
    )
    redacted = ops._redact_connection_values(text, dsn)
    for value in (
        "svcuser_SECRETTAIL9x3f", "svcuser_DBTAIL7e2a", "svcuser",
        "_SECRETTAIL9x3f", "_DBTAIL7e2a",  # the TAILS alone -- see docstring
        "hostA.invalid", "hostB.invalid", "5432", "5433",
    ):
        assert value not in redacted, f"{value!r} leaked into redacted output: {redacted!r}"


def test_psql_connection_env_rejects_a_dsn_key_with_no_libpq_env_var_form(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`keepalives` is a real libpq connection parameter with NO `PG*`
    environment-variable form (absent from the local PostgreSQL 16
    `libpq-envars` documentation) -- rejected via `_die` (SystemExit(2)),
    naming the key but never the value."""
    dsn = "host=h.invalid dbname=d keepalives=sentinel_value_should_not_leak_7f3a"
    with pytest.raises(SystemExit) as excinfo:
        ops._psql_connection_env(dsn)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "keepalives" in captured.err
    assert "sentinel_value_should_not_leak_7f3a" not in captured.err


def test_psql_connection_env_accepts_new_allow_listed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sslrootcert`/`connect_timeout` are in the expanded allow-list
    (local PostgreSQL 16 libpq documentation) and reach the child
    environment under their own `PG*` names."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    dsn = "host=h.invalid dbname=d sslrootcert=/etc/ssl/root.pem connect_timeout=5"
    env = ops._psql_connection_env(dsn)
    assert env["PGSSLROOTCERT"] == "/etc/ssl/root.pem"
    assert env["PGCONNECT_TIMEOUT"] == "5"


def test_psql_connection_env_strips_parent_pg_star_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """A-9: `PGUSER`/`PGPASSWORD` the parent process happens to carry are
    overridden by the DSN's own values (never merely left in place), and
    `PGTZ` -- a parent `PG*` variable with NO `conninfo` keyword at all,
    so it is outside A-13's own fail-closed check below and exercises
    the GENERAL `PG*`-stripping step on its own -- must not survive
    either."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGUSER", "parent_user_should_not_survive")
    monkeypatch.setenv("PGPASSWORD", "parent_password_should_not_survive")
    monkeypatch.setenv("PGTZ", "parent_tz_should_not_survive")
    dsn = "host=h.invalid dbname=d user=real_user password=real_password"
    env = ops._psql_connection_env(dsn)
    assert env["PGUSER"] == "real_user"
    assert env["PGPASSWORD"] == "real_password"
    assert "PGTZ" not in env
    assert "parent_tz_should_not_survive" not in env.values()


def test_psql_connection_env_rejects_a_parent_connection_var_the_dsn_does_not_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """A-13: `PGSSLMODE` set in the parent's own environment, with no
    `sslmode` in the DSN to override it, fails closed -- the psql child
    must never silently inherit a connection setting the DSN itself never
    described. Names the variable, never a value."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    dsn = "host=h.invalid dbname=d"
    with pytest.raises(SystemExit) as excinfo:
        ops._psql_connection_env(dsn)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "PGSSLMODE" in captured.err


def test_psql_connection_env_accepts_when_dsn_overrides_the_parent_connection_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A-13: the SAME parent `PGSSLMODE` is fine once the DSN itself
    provides `sslmode=`."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    dsn = "host=h.invalid dbname=d sslmode=require"
    env = ops._psql_connection_env(dsn)
    assert env["PGSSLMODE"] == "require"


def test_psql_connection_env_rejects_a_parent_pgservicefile_the_dsn_can_never_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """`PGSERVICEFILE` has no `conninfo` keyword of its own, so no DSN can
    ever override it -- confirms it is still checked even though it is
    absent from `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY`'s own values. Names the
    variable, never a value."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGSERVICEFILE", "/some/path/pg_service.conf")
    dsn = "host=h.invalid dbname=d"
    with pytest.raises(SystemExit) as excinfo:
        ops._psql_connection_env(dsn)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "PGSERVICEFILE" in captured.err
    assert "/some/path/pg_service.conf" not in captured.err


def test_psql_connection_env_rejects_a_parent_pgsysconfdir_the_dsn_can_never_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """`PGSYSCONFDIR` has no `conninfo` keyword of its own either -- same
    check as `PGSERVICEFILE` above, for the other of the two variables
    named explicitly in `_LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_
    KEY`."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    monkeypatch.setenv("PGSYSCONFDIR", "/some/etc/postgresql-common")
    dsn = "host=h.invalid dbname=d"
    with pytest.raises(SystemExit) as excinfo:
        ops._psql_connection_env(dsn)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "PGSYSCONFDIR" in captured.err
    assert "/some/etc/postgresql-common" not in captured.err


def test_require_psql_16_or_newer_rejects_an_older_or_unparseable_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A-14: `psql --version` output naming a pre-16 major version, or
    one this module cannot parse at all, ends the run via `_die`."""

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        assert cmd == ["psql", "--version"]
        return subprocess.CompletedProcess(cmd, 0, stdout="psql (PostgreSQL) 15.4\n", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    with pytest.raises(SystemExit) as excinfo:
        ops._require_psql_16_or_newer()
    assert excinfo.value.code == 2


def test_require_psql_16_or_newer_rejects_unparseable_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 0, stdout="not a version string\n", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    with pytest.raises(SystemExit) as excinfo:
        ops._require_psql_16_or_newer()
    assert excinfo.value.code == 2


def test_require_psql_16_or_newer_accepts_16(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 0, stdout="psql (PostgreSQL) 16.14 (Homebrew)\n", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._require_psql_16_or_newer()  # must not raise


def test_require_psql_16_or_newer_rejects_when_the_binary_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing psql binary (`FileNotFoundError`, the OS-level failure a
    real `subprocess.run` raises when the executable is absent from
    `PATH`) ends the run via `_die`, the same as an unparseable/too-old
    version."""

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        raise FileNotFoundError(2, "No such file or directory", "psql")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    with pytest.raises(SystemExit) as excinfo:
        ops._require_psql_16_or_newer()
    assert excinfo.value.code == 2


def test_run_upgrade_script_calls_the_psql_version_gate_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """A-14: `_run_upgrade_script` calls `_require_psql_16_or_newer` (a
    `["psql", "--version"]` subprocess call) before its own real psql
    invocation -- removing that call site would leave an old/broken psql
    binary undetected."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    version_calls = 0
    main_calls = 0

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        nonlocal version_calls, main_calls
        if cmd[:2] == ["psql", "--version"]:
            version_calls += 1
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        main_calls += 1
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1")
    assert version_calls == 1
    assert main_calls == 1


def test_run_deprovision_script_calls_the_psql_version_gate_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A-14: `_run_deprovision_script`'s own version gate call."""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    script = tmp_path / "0004_deprovision_application.sql"
    script.write_text("-- empty\n")
    monkeypatch.setattr(ops, "_migrations_dir", lambda: tmp_path)
    version_calls = 0
    main_calls = 0

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        nonlocal version_calls, main_calls
        if cmd[:2] == ["psql", "--version"]:
            version_calls += 1
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        main_calls += 1
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_deprovision_script(_SENTINEL_DSN, "app1")
    assert version_calls == 1
    assert main_calls == 1
