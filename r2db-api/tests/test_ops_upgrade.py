"""Q4 phase WP-3 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-4/D-5,
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-3
change table E): `ops upgrade-applications`/`ops upgrade-status` --
placement confirmed by `tests/test_ops_declarations.py`'s own header
comment (supervisor ruling 2026-09-05, work order §7 prohibition 7): the
upgrade-series subcommands' own file, separate from the declaration-series
subcommands' own `test_ops_declarations.py` (WP-1/WP-2 territory).

Real PostgreSQL throughout (§5.3 C-5): this file runs the actual
`0001_bootstrap_control_plane.sql` through `0004_deprovision_application.
sql` migration files (with `r2dbsvc` textually replaced by a random,
per-module throwaway prefix, `test_postgres.py`'s own convention) so both
subcommands exercise the real provisioning ritual, never a hand-built
substitute registry.

Synthetic (`tmp_path`) per-application upgrade scripts, never `0009`
itself, are used wherever a test needs a NUMBER this shipped package does
not actually know about (design completion condition 14's own "パッケージ
定数が{9, 9999}(合成)"): `platform_upgrades.PLATFORM_UPGRADE_NUMBERS` is
monkeypatched to include that synthetic number, and `R2DB_MIGRATIONS_DIR`
(ops.py's own test-only escape hatch, mirroring `R2DB_PLATFORM_SCHEMA`)
points `_migrations_dir()` at a throwaway directory holding just that one
synthetic script -- the REAL `r2db-api/migrations/` directory is never
copied or mutated by any test below.
"""
from __future__ import annotations

import secrets
import subprocess
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import r2db_api.ops as ops
import r2db_api.platform_upgrades as platform_upgrades


@pytest.fixture(autouse=True)
def _clear_ambient_pg_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """design D-2: this
    file's own throwaway-cluster launcher (`tools/testpg/dsa_testpg.py`)
    deliberately exports `PGPORT`/`PGUSER`/`PGPASSFILE` at the PROCESS
    level so a bare `psql`/libpq call defaults to the same cluster --
    convenient for manual use, but every DSN in this file already carries
    its own host/port/user/password explicitly, so those ambient exports
    are pure interference for `_psql_connection_env`'s own A-13 fail-
    closed check (a connection-setting variable the DSN itself does not
    override). Cleared once per test, for every test in this file, since
    this peer's own tests call `ops.cmd_upgrade_applications`/`ops.main`
    in-process and read `os.environ` directly."""
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"

#: コードレビュー1低9: this file's own default for `upgrade-applications`'
#: required `--lock-timeout` (design D-7) -- every caller here is a
#: per-test PostgreSQL exercise, never a real deployment, so any accepted
#: value does; a caller exercising `--lock-timeout` itself passes its own
#: value instead. Mirrors MitateDB-api's own same-named constant
#: (`MitateDB-api/tests/test_ops_upgrade.py::_TEST_LOCK_TIMEOUT`).
_TEST_LOCK_TIMEOUT = "5000ms"


def _admin_dsn() -> str:
    import os

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


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    try:
        conn = psycopg.connect(_admin_dsn(), connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(f"test_ops_upgrade.py requires a reachable local PostgreSQL server: {exc}", pytrace=False)


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            for (database,) in cur.fetchall():
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
            for (role,) in cur.fetchall():
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbopsupg{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    platform_db = f"{prefix}_platform"
    control_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_ops_upgrade_migrations")
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        # M-4 (supervisor ruling 2026-09-05, review): `applications.
        # enabled` is added by 0005, not 0001-0004 -- WITHOUT this
        # migration applied, the throwaway registry this file's own
        # `platform`/`ops_env` fixture builds has NO `enabled` column at
        # all, so a mutation that adds `AND enabled` to `_registry_
        # applications_for_upgrade`'s own default-enumeration query fails
        # with a SQL error (rc == 1, "enumeration failure") rather than
        # actually excluding a disabled application -- an INCIDENTAL red,
        # not an observation of design D-4(a)'s own "enabledは対象選択に
        # 影響しない" property (review finding: r2db had NO coverage of
        # this property at all; MitateDB already did, `test_ops_upgrade.
        # py::test_upgrade_applications_enabled_does_not_affect_target_
        # selection`).
        "0005_credential_store.sql",
        # M-4 (supervisor ruling 2026-09-05, review): rewritten (its own
        # literal `r2dbsvc_registry` textually replaced, same as every
        # other migration file here) so a REAL (non-synthetic) `ops.
        # main(["upgrade-applications", ...])` re-run against a database
        # whose ledger has had `9` deleted can actually re-apply it --
        # `test_upgrade_applications_enabled_does_not_affect_target_
        # selection` is the only test in this file that needs this (every
        # OTHER test either dry-runs, never deletes `9` at all, or uses a
        # SYNTHETIC script number instead, this file's own module
        # docstring). Never applied at PLATFORM level by this fixture
        # (per-application upgrade script, run against one application's
        # own database).
        "0009_platform_upgrades_ledger_upgrade.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
        _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": secrets.token_urlsafe(24)})
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, control_dsn=control_dsn, control_role=control_role,
        platform_db=platform_db, schema=f"{prefix}_registry",
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        upgrade_migrations_dir=rewritten_dir,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.control_dsn, platform.provision_script,
        {"app_slug": slug, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{slug}"
    return types.SimpleNamespace(
        slug=slug, database=database,
        runtime_role=f"{database}_runtime", developer_role=f"{database}_developer",
        developer_dsn=_dsn_with(platform.admin_dsn, user=f"{database}_developer", password=developer_password, dbname=database),
    )


def deprovision_app(platform: types.SimpleNamespace, slug: str) -> None:
    import time

    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql(platform.control_dsn, platform.deprovision_script, {"app_slug": slug})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


@pytest.fixture
def ops_env(platform: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    monkeypatch.setenv("R2DB_CONTROL_DSN", platform.control_dsn)
    monkeypatch.setenv("R2DB_PLATFORM_SCHEMA", platform.schema)
    return platform


def _ledger_numbers(dsn: str) -> frozenset[int]:
    conn = psycopg.connect(dsn)
    try:
        return platform_upgrades.read_applied_upgrade_numbers(conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME) or frozenset()
    finally:
        conn.close()


def disable_application(platform: types.SimpleNamespace, slug: str) -> None:
    """M-4 (supervisor ruling 2026-09-05): design D-4(a) non-vacuity --
    `enabled` must not affect target selection. Mirrors MitateDB-api's
    own identically-named `test_ops_upgrade.py::disable_application`
    (independently maintained, no cross-peer sharing)."""
    conn = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET enabled = FALSE WHERE application_slug = %s").format(
                    table=sql.Identifier(platform.schema, "applications")),
                [slug],
            )
    finally:
        conn.close()


# ===========================================================================
# 完了条件 14: 集合差 (set difference, never "max number")
# ===========================================================================


def test_upgrade_applications_dry_run_pending_is_a_set_difference(
    ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """台帳が `{9, 10}` (通常の `0003` provisioning -- Phase 9 WP-2a で
    `10` も加わった) でパッケージ定数が `{9, 9999}` (合成) のとき、
    pending は `{9999}` になる (集合差 -- 台帳に無い `10` は available
    側に無いので pending 計算に現れない)。"""
    app = provision_app(ops_env, "upga")
    try:
        assert _ledger_numbers(app.developer_dsn) == frozenset({9, 10, 11})
        monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
        rc = ops.main(["upgrade-applications", "--application", "upga", "--dry-run", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 4
        assert "pending=[9999]" in out
    finally:
        deprovision_app(ops_env, "upga")


def test_upgrade_applications_pending_detects_a_hole_not_just_the_max(
    ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """台帳が `{9999}` で `9` が欠けている状態でも `9` が pending として出る
    こと (v1.0 の「台帳の最大番号より大きい」方式では検出できない穴)。
    Phase 9 WP-2a/WP-2c で通常の provisioning が台帳に `10`/`11` も足すよ
    うになったので、この test 専用の isolation として両方とも明示的に削除
    する (この test が固定したいのは「台帳がちょうど `{9999}` のときの穴
    検出」そのもの)。"""
    app = provision_app(ops_env, "upgb")
    try:
        with psycopg.connect(app.developer_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number IN (9, 10, 11)")
                cur.execute(
                    "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name) VALUES (9999, 'synthetic')"
                )
            conn.commit()
        assert _ledger_numbers(app.developer_dsn) == frozenset({9999})
        monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
        rc = ops.main(["upgrade-applications", "--application", "upgb", "--dry-run", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 4
        assert "pending=[9]" in out
    finally:
        deprovision_app(ops_env, "upgb")


# ===========================================================================
# 完了条件 15/16: 全 DB 走査、失敗の列挙、REVOKE 出力
# ===========================================================================


@pytest.fixture
def synthetic_script_9999(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic per-application upgrade script for number `9999` --
    conforms to design D-3(c)/§8.1 (ledger `INSERT ... ON CONFLICT` in one
    statement, atomic `BEGIN...COMMIT`, no `\\q`) -- that deliberately
    FAILS for exactly one application (`app_slug = 'failapp'`, a plain SQL
    `CASE`/division-by-zero evaluated server-side, never psql's own `\\if`
    boolean parsing) so a single `ops upgrade-applications` invocation can
    exercise "one DB fails, the OTHER is still processed and succeeds" in
    one real run (design D-4(c))."""
    script = tmp_path / "9999_synthetic_upgrade.sql"
    script.write_text(
        "\\set ON_ERROR_STOP on\n"
        "SELECT database_name, runtime_role, developer_role FROM " + "REGISTRY_SCHEMA" + ".applications "
        "WHERE application_slug = :'app_slug' \\gset\n"
        "\\c :database_name\n"
        "GRANT :\"developer_role\" TO CURRENT_USER WITH SET TRUE;\n"
        "BEGIN;\n"
        "SET LOCAL ROLE :\"developer_role\";\n"
        "SELECT CASE WHEN :'app_slug' = 'failapp' THEN 1/0 ELSE 1 END;\n"
        "CREATE TABLE IF NOT EXISTS public._r2db_platform_upgrades (\n"
        "    upgrade_number integer PRIMARY KEY, script_name text NOT NULL,\n"
        "    applied_at timestamptz NOT NULL DEFAULT now()\n"
        ");\n"
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "    VALUES (9999, '9999_synthetic_upgrade.sql') ON CONFLICT (upgrade_number) DO NOTHING;\n"
        "COMMIT;\n"
        "REVOKE :\"developer_role\" FROM CURRENT_USER;\n"
    )
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(tmp_path))
    monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
    return script


def test_upgrade_applications_one_failure_does_not_stop_the_others(
    ops_env: types.SimpleNamespace, synthetic_script_9999: Path, capsys: pytest.CaptureFixture
) -> None:
    # `REGISTRY_SCHEMA` placeholder above must name THIS run's real schema
    # -- fixed up here since the fixture itself has no access to `platform`.
    synthetic_script_9999.write_text(synthetic_script_9999.read_text().replace("REGISTRY_SCHEMA", ops_env.schema))
    good = provision_app(ops_env, "goodapp")
    bad = provision_app(ops_env, "failapp")
    try:
        rc = ops.main(["upgrade-applications", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 3
        assert "goodapp" in out and "failapp" in out
        assert _ledger_numbers(good.developer_dsn) == frozenset({9, 10, 11, 9999}), "the OTHER application must still be upgraded"
        assert _ledger_numbers(bad.developer_dsn) == frozenset({9, 10, 11}), "the failed application's ledger must not gain a row for 9999"
        # 完了条件 16: REVOKE cleanup line for the failed application only.
        assert f"REVOKE {bad.developer_role} FROM {ops_env.control_role};" in out
        assert f"REVOKE {good.developer_role} FROM {ops_env.control_role};" not in out
    finally:
        deprovision_app(ops_env, "goodapp")
        deprovision_app(ops_env, "failapp")


def test_upgrade_applications_is_idempotent(ops_env: types.SimpleNamespace) -> None:
    """完了条件 15: 2 回目の実行で何も起きず 0 で終わる (`0009`/`0010` は
    既に台帳付きで provision されているので、追加手順なしに冪等)。"""
    app = provision_app(ops_env, "idemapp")
    try:
        assert ops.main(["upgrade-applications", "--application", "idemapp", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 0
        before = _ledger_numbers(app.developer_dsn)
        assert ops.main(["upgrade-applications", "--application", "idemapp", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 0
        after = _ledger_numbers(app.developer_dsn)
        assert before == after == frozenset({9, 10, 11})
    finally:
        deprovision_app(ops_env, "idemapp")


# ===========================================================================
# 完了条件 17: 終了コードの 5 値
# ===========================================================================


def test_upgrade_applications_exit_codes(ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    app = provision_app(ops_env, "exitapp")
    try:
        # 0 -- nothing pending.
        assert ops.main(["upgrade-applications", "--application", "exitapp", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 0
        # 1 -- enumeration failure (bad provision DSN).
        monkeypatch.setenv("R2DB_CONTROL_DSN", "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1")
        assert ops.main(["upgrade-applications", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 1
        monkeypatch.setenv("R2DB_CONTROL_DSN", ops_env.control_dsn)
        # 2 -- usage error (provision DSN entirely unset).
        monkeypatch.delenv("R2DB_CONTROL_DSN")
        with pytest.raises(SystemExit) as exc:
            ops.main(["upgrade-applications", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        assert exc.value.code == 2
        monkeypatch.setenv("R2DB_CONTROL_DSN", ops_env.control_dsn)
        # 4 -- dry-run, something pending.
        monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
        assert ops.main(["upgrade-applications", "--application", "exitapp", "--dry-run", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 4
    finally:
        deprovision_app(ops_env, "exitapp")


def test_upgrade_applications_exit_code_3_on_failure(
    ops_env: types.SimpleNamespace, synthetic_script_9999: Path
) -> None:
    synthetic_script_9999.write_text(synthetic_script_9999.read_text().replace("REGISTRY_SCHEMA", ops_env.schema))
    bad = provision_app(ops_env, "failapp")
    try:
        assert ops.main(["upgrade-applications", "--application", "failapp", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 3
    finally:
        deprovision_app(ops_env, "failapp")


# ===========================================================================
# 完了条件 18: `--script` は未適用限定 (recorded, skipped)
# ===========================================================================


def test_upgrade_applications_script_on_an_already_recorded_database_is_skipped_not_reapplied(
    ops_env: types.SimpleNamespace, capsys: pytest.CaptureFixture
) -> None:
    app = provision_app(ops_env, "scriptapp")
    try:
        rc = ops.main(["upgrade-applications", "--application", "scriptapp", "--script", "9", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 0
        assert "recorded, skipped" in out
        assert "9" in out
    finally:
        deprovision_app(ops_env, "scriptapp")


# ===========================================================================
# 完了条件 19: `upgrade-status`
# ===========================================================================


def test_upgrade_status_reports_applied_pending_and_database_name(
    ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    app = provision_app(ops_env, "statusapp")
    try:
        rc = ops.main(["upgrade-status", "--application", "statusapp"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "database_name=" in out and app.database in out
        assert "applied=[9, 10, 11]" in out
        assert "pending=[]" in out

        monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
        rc = ops.main(["upgrade-status", "--application", "statusapp"])
        out = capsys.readouterr().out
        assert rc == 4
        assert "pending=[9999]" in out
    finally:
        deprovision_app(ops_env, "statusapp")


def test_upgrade_status_reports_applied_empty_for_an_application_with_no_ledger(
    ops_env: types.SimpleNamespace, capsys: pytest.CaptureFixture
) -> None:
    """設計 D-5: 台帳が無い application は `applied=[]` になる。"""
    app = provision_app(ops_env, "noledgerapp")
    try:
        with psycopg.connect(app.developer_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._r2db_platform_upgrades")
            conn.commit()
        rc = ops.main(["upgrade-status", "--application", "noledgerapp"])
        out = capsys.readouterr().out
        assert rc == 4
        assert "applied=[]" in out
        assert "pending=[9, 10, 11]" in out
    finally:
        deprovision_app(ops_env, "noledgerapp")


# ===========================================================================
# M-1/M-2 (supervisor ruling 2026-09-05, 差し戻し裁定 2/3): 4 つの exit-code
# ケースと `database_name` NULL の失敗扱い -- 同名テストを MitateDB-api の
# `test_ops_upgrade.py` にも置く (独立実装、cross-peer 共有なし)。
# ===========================================================================


def test_upgrade_applications_unknown_application_is_a_usage_error(ops_env: types.SimpleNamespace) -> None:
    """M-2(a): レジストリに存在しない `--application` は使い方の誤り
    (exit 2) であり、無音の exit 0 やエラー無視であってはならない。"""
    with pytest.raises(SystemExit) as exc:
        ops.main(["upgrade-applications", "--application", "totally_unregistered_slug", "--lock-timeout", _TEST_LOCK_TIMEOUT])
    assert exc.value.code == 2


def test_upgrade_status_unknown_application_is_a_usage_error(ops_env: types.SimpleNamespace) -> None:
    """M-2(a) の `upgrade-status` 側: 同じ `_registry_applications_for_
    upgrade` を経由するので同じ exit 2 になること。"""
    with pytest.raises(SystemExit) as exc:
        ops.main(["upgrade-status", "--application", "totally_unregistered_slug"])
    assert exc.value.code == 2


def test_upgrade_applications_missing_script_file_is_a_usage_error(ops_env: types.SimpleNamespace) -> None:
    """M-2(b): `migrations/` 配下に存在しない番号の `--script` は使い方の
    誤り (exit 2)。"""
    app = provision_app(ops_env, "scriptmiss")
    try:
        with pytest.raises(SystemExit) as exc:
            ops.main(["upgrade-applications", "--application", "scriptmiss", "--script", "1234", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        assert exc.value.code == 2
    finally:
        deprovision_app(ops_env, "scriptmiss")


def test_upgrade_applications_script_number_unknown_to_the_package_is_a_usage_error(
    ops_env: types.SimpleNamespace, capsys: pytest.CaptureFixture,
) -> None:
    """M-2(c): `PLATFORM_UPGRADE_NUMBERS` に無い番号を `--script` に渡す
    のも (b) と同じ経路で exit 2 になること -- 「skipped (already
    recorded)」の偽報告(=無音の成功)であってはならない (U-7, supervisor
    ruling 2026-09-05 差し戻し後 delta 監査: MitateDB-api's own same-named
    test asserts this directly -- this peer's own version was exit-code
    only). `42` は `migrations/` にファイルが無い番号であると同時に、この
    peer の `PLATFORM_UPGRADE_NUMBERS` (`{9}`) にも含まれない番号である。
    `_die` raises before the per-application loop is ever reached, so no
    application-level output (this peer's own skip line, `recorded,
    skipped=...`, from `_print_upgrade_result`) can have been printed."""
    app = provision_app(ops_env, "scriptunk")
    try:
        with pytest.raises(SystemExit) as exc:
            ops.main(["upgrade-applications", "--application", "scriptunk", "--script", "42", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        assert exc.value.code == 2
        assert "recorded, skipped=" not in capsys.readouterr().out
    finally:
        deprovision_app(ops_env, "scriptunk")


def test_upgrade_status_reports_a_never_provisioned_application_as_pending_everything(
    ops_env: types.SimpleNamespace,
) -> None:
    """M-2(d): レジストリに登録済みだが未 provision (`database_name`が
    NULL) の application を `--application` で名指しした `upgrade-status`
    は、行を出し (`database_name=None`、`pending`=全番号) つつ exit 4 で
    終わること -- 空の結果集合で無音の exit 0 になってはならない。

    r2db 自身の出荷済みスキーマは `applications.database_name` を
    `NOT NULL` として定義しており (`migrations/0002_provisioning_
    functions.sql`)、この状態へ至る実 provisioning 経路は存在しない
    (`begin_provision_application`はレジストリ行を書かず、行を書く唯一の
    関数`finish_provision_application`は必ず`database_name`を伴う --
    MitateDB の二段階レジストリ, design R-4, とは非対称)。このテストは
    その状態をこの THROWAWAY レジストリコピーの上だけで直接構成する
    (出荷済み migration には触れない) -- 将来この制約が緩められた場合の
    防御でもある。
    """
    conn = psycopg.connect(ops_env.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER TABLE {table} ALTER COLUMN database_name DROP NOT NULL").format(
                    table=sql.Identifier(ops_env.schema, "applications")
                )
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (application_slug, database_name, runtime_role, developer_role) "
                    "VALUES (%s, NULL, %s, %s)"
                ).format(table=sql.Identifier(ops_env.schema, "applications")),
                ["ghoststatus", "ghoststatus_runtime_synthetic", "ghoststatus_developer_synthetic"],
            )
    finally:
        conn.close()

    import io
    from contextlib import redirect_stdout

    out_buf = io.StringIO()
    with redirect_stdout(out_buf):
        rc = ops.main(["upgrade-status", "--application", "ghoststatus"])
    out = out_buf.getvalue()
    assert rc == 4
    assert "database_name=None" in out
    assert "pending=[9, 10, 11]" in out


def test_upgrade_applications_a_never_provisioned_application_named_explicitly_is_a_failure(
    ops_env: types.SimpleNamespace,
) -> None:
    """M-1 (supervisor ruling 2026-09-05, review): design D-4(e)'s own
    exit-code table names `database_name`がNULL explicitly as ONE of the
    two conditions exit code `3` covers ("psql exit 3、または
    `database_name`がNULL") -- a REAL (non-dry-run) `upgrade-applications`
    naming such an application explicitly must fail (exit 3), not
    silently succeed (the prior bug this ruling closes: `summarize_
    upgrade_run` was called on a results list with these rows already
    filtered OUT, so it always returned `0`, review M-1). See `test_
    upgrade_status_reports_a_never_provisioned_application_as_pending_
    everything`'s own docstring, immediately above, for why this state
    is constructed directly rather than via a real provisioning path."""
    conn = psycopg.connect(ops_env.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER TABLE {table} ALTER COLUMN database_name DROP NOT NULL").format(
                    table=sql.Identifier(ops_env.schema, "applications")
                )
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (application_slug, database_name, runtime_role, developer_role) "
                    "VALUES (%s, NULL, %s, %s)"
                ).format(table=sql.Identifier(ops_env.schema, "applications")),
                ["ghostapply", "ghostapply_runtime_synthetic", "ghostapply_developer_synthetic"],
            )
    finally:
        conn.close()

    rc = ops.main(["upgrade-applications", "--application", "ghostapply", "--lock-timeout", _TEST_LOCK_TIMEOUT])
    assert rc == 3


def test_upgrade_applications_enabled_does_not_affect_target_selection(
    ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-4 (supervisor ruling 2026-09-05, review): design D-4(a)
    "`enabled`は対象選択に影響しない...無効化中のapplicationのDBも一括適用
    の対象に含める" -- same name as MitateDB-api's own `test_ops_upgrade.
    py::test_upgrade_applications_enabled_does_not_affect_target_
    selection` (independent realization, no cross-peer sharing). Requires
    the `ops_env`/`platform` fixture's own `0005_credential_store.sql`
    application (the migration that actually adds `applications.enabled`)
    -- without it, a mutation adding `AND enabled` to the default-
    enumeration query fails with `rc == 1` (a SQL error against a
    throwaway registry with no such column at all), an INCIDENTAL red the
    original review flagged as no real coverage of this property."""
    monkeypatch.setenv("R2DB_MIGRATIONS_DIR", str(ops_env.upgrade_migrations_dir))
    app = provision_app(ops_env, "enabledapp")
    try:
        disable_application(ops_env, "enabledapp")
        # A disabled application's own database must still be targeted by
        # the DEFAULT (no `--application`) enumeration.
        rc = ops.main(["upgrade-applications", "--application", "enabledapp", "--dry-run", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        assert rc == 0, "a fully-seeded, disabled application must still report nothing pending"

        with psycopg.connect(app.developer_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
            conn.commit()
        rc = ops.main(["upgrade-applications", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        assert rc == 0, "the disabled application must still be upgraded by the default (no --application) run"
        assert _ledger_numbers(app.developer_dsn) == frozenset({9, 10, 11})
    finally:
        deprovision_app(ops_env, "enabledapp")


def test_upgrade_applications_failure_output_includes_the_psql_stderr_tail(
    ops_env: types.SimpleNamespace, synthetic_script_9999: Path, capsys: pytest.CaptureFixture,
) -> None:
    """M-3 (supervisor ruling 2026-09-05, review): a failed `psql`
    invocation's own stderr is the ONLY place the actual PostgreSQL error
    text lives -- before this fix `_run_upgrade_script`'s own
    `CompletedProcess` was discarded except for `.returncode`. Reuses
    `synthetic_script_9999`'s own deliberate `SELECT CASE WHEN :'app_slug'
    = 'failapp' THEN 1/0 ELSE 1 END;` division-by-zero failure -- its own
    real `psql` stderr names PostgreSQL's own `division_by_zero` error
    text, which must now appear in this application's own output block."""
    synthetic_script_9999.write_text(synthetic_script_9999.read_text().replace("REGISTRY_SCHEMA", ops_env.schema))
    provision_app(ops_env, "failapp")
    try:
        rc = ops.main(["upgrade-applications", "--application", "failapp", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 3
        assert "psql stderr (tail)" in out
        assert "division by zero" in out
    finally:
        deprovision_app(ops_env, "failapp")


# ===========================================================================
# U-1 (supervisor ruling 2026-09-05, 差し戻し後 delta 監査): 集計行の計数
# 規則 -- 両 peer で統一する。同名テストを MitateDB-api の
# `test_ops_upgrade.py` にも置く (独立実装、cross-peer 共有なし)。
# ===========================================================================


def test_upgrade_applications_tally_line_counts_one_of_each_outcome(
    ops_env: types.SimpleNamespace, synthetic_script_9999: Path, capsys: pytest.CaptureFixture,
) -> None:
    """U-1: pins the trailing tally line's own COUNTING rule, not merely
    its string template -- 3 applications, one of each outcome, in a
    single bulk (no `--application`) run, must read exactly `1 succeeded,
    1 failed, 1 skipped (applied)`.

    `goodagg` has `9999` pending and applies it for the first time in THIS
    run (succeeded, 適用を実行して成功した). `failapp` is `synthetic_
    script_9999`'s own hardcoded failing application slug -- `9999` is
    attempted and fails (failed). `skipagg` already has `9999` applied, via
    its OWN prior, individually-targeted run before this test's own bulk
    invocation -- this run's own `to_apply` is empty for it, so it
    applies nothing at all (未適用なし、既に記録済み -> skipped, never a
    success, since nothing was actually run)."""
    synthetic_script_9999.write_text(synthetic_script_9999.read_text().replace("REGISTRY_SCHEMA", ops_env.schema))
    good = provision_app(ops_env, "goodagg")
    provision_app(ops_env, "failapp")
    skip = provision_app(ops_env, "skipagg")
    try:
        assert ops.main(["upgrade-applications", "--application", "skipagg", "--lock-timeout", _TEST_LOCK_TIMEOUT]) == 0
        assert _ledger_numbers(skip.developer_dsn) == frozenset({9, 10, 11, 9999})

        rc = ops.main(["upgrade-applications", "--lock-timeout", _TEST_LOCK_TIMEOUT])
        out = capsys.readouterr().out
        assert rc == 3
        assert "1 succeeded, 1 failed, 1 skipped (applied)" in out
        assert _ledger_numbers(good.developer_dsn) == frozenset({9, 10, 11, 9999})
    finally:
        deprovision_app(ops_env, "goodagg")
        deprovision_app(ops_env, "failapp")
        deprovision_app(ops_env, "skipagg")


# ===========================================================================
# Completion conditions 19-4/19-5: in-process unit tests, monkeypatching `subprocess.run` and the
# registry/ledger lookups rather than requiring a real failing migration
# script or a live registry -- the property under test (argv/env shape,
# redaction of a psql failure's own captured output) does not depend on
# which SQL actually ran. `_run_deprovision_script` has no r2db-api
# counterpart (design D-9's own asymmetry, confirmed by static inventory) so there is no 19-6 row on this peer.
# ===========================================================================

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
    calls: list[tuple[list[str], dict]] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001 -- matches subprocess.run's own loose signature
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1", _TEST_LOCK_TIMEOUT)

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


class _FakeControlConn:
    """Bare stand-in for `with psycopg.connect(provision_dsn) as conn:` --
    only `.info.user` and context-manager protocol are ever touched on
    this peer's own `cmd_upgrade_applications`, before this test's own
    monkeypatches take over every registry/ledger read."""

    def __enter__(self) -> "_FakeControlConn":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    @property
    def info(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(user="fake_provision_role")


def test_cmd_upgrade_applications_redacts_connection_values_from_a_failed_psql_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Completion condition 19-4 (r2db-api side): `cmd_upgrade_applications`'s
    own `failure_detail` (a failed psql invocation's stdout/stderr tail)
    has every one of the DSN's 4 sentinel values redacted before it is
    folded into this application's own printed output block -- the SQL-
    level part of the diagnostic (unrelated to any of the 4 values)
    survives untouched."""
    monkeypatch.setattr(ops, "_control_dsn", lambda: _SENTINEL_DSN)
    monkeypatch.setattr(ops.psycopg, "connect", lambda dsn, **kw: _FakeControlConn())
    monkeypatch.setattr(
        ops, "_registry_applications_for_upgrade",
        lambda conn, *, application: [
            {"application_slug": "app1", "database_name": "app1_db", "runtime_role": "app1_rt", "developer_role": "app1_dv"},
        ],
    )
    monkeypatch.setattr(ops, "_read_ledger_applied", lambda app_dsn: frozenset())
    monkeypatch.setattr(
        ops.platform_upgrades, "discover_upgrade_scripts",
        lambda migrations_dir: {9: migrations_dir / "0009_does_not_matter.sql"},
    )

    def _fake_run_upgrade_script(app_dsn, script, app_slug, lock_timeout):  # noqa: ANN001
        raw = (
            f"psql: error: connection to server at \"sentinel-host-b91d.invalid\", port 6543 failed\n"
            f"FATAL:  password authentication failed for user \"sentinel_user_c3f1\"\n"
            f"detail: database \"sentinel_db_44de\" pending; secret sentinel_pw_7a2e rejected\n"
            f"ERROR:  syntax error at or near \"CREATE\""
        )
        return subprocess.CompletedProcess(["psql"], 1, stdout="", stderr=raw)

    monkeypatch.setattr(ops, "_run_upgrade_script", _fake_run_upgrade_script)

    args = types.SimpleNamespace(application=None, script=9, dry_run=False, lock_timeout=_TEST_LOCK_TIMEOUT)
    rc = ops.cmd_upgrade_applications(args)
    captured = capsys.readouterr()

    assert rc != 0  # a real per-application failure, not a clean run
    for value in _SENTINEL_VALUES:
        assert value not in captured.out, f"{value!r} leaked into cmd_upgrade_applications output: {captured.out!r}"
    assert "<redacted>" in captured.out
    assert "syntax error at or near" in captured.out  # SQL-level diagnostic survives


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


def test_psql_connection_env_accepts_new_allow_listed_keys() -> None:
    """`sslrootcert`/`connect_timeout` are in the expanded allow-list
    (local PostgreSQL 16 libpq documentation) and reach the child
    environment under their own `PG*` names."""
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
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1", _TEST_LOCK_TIMEOUT)
    assert version_calls == 1
    assert main_calls == 1


# ===========================================================================
# design D-7 (work order R-66 WP-2): `upgrade-applications`'s own required
# `--lock-timeout` -- argument presence, value validation, and the
# `PGOPTIONS` it reaches `_run_upgrade_script` through.
# ===========================================================================


def test_upgrade_applications_without_lock_timeout_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """完了条件1: `--lock-timeout` を省略すると argparse が使用法エラー
    (exit 2) で拒否する -- 既定値が無いことを実行で確かめる。"""
    with pytest.raises(SystemExit) as exc:
        ops.main(["upgrade-applications"])
    assert exc.value.code == 2
    assert "--lock-timeout" in capsys.readouterr().err


def test_upgrade_applications_without_lock_timeout_is_a_usage_error_with_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """完了条件1: `--dry-run` を付けても同じく exit 2 になる。"""
    with pytest.raises(SystemExit) as exc:
        ops.main(["upgrade-applications", "--dry-run"])
    assert exc.value.code == 2
    assert "--lock-timeout" in capsys.readouterr().err


def test_validate_lock_timeout_value_accepts_well_formed_values() -> None:
    """完了条件3: `5000`・`5000ms`・`5s`・`1min` は受理され、値そのものが
    そのまま返る。空振り禁止: ループ 4 回すべてで assert が走る。"""
    for value in ("5000", _TEST_LOCK_TIMEOUT, "5s", "1min"):
        assert ops._validate_lock_timeout_value(value) == value


def test_validate_lock_timeout_value_rejects_ill_formed_values(capsys: pytest.CaptureFixture[str]) -> None:
    """完了条件3: `0`・`0ms`・負・`1h`・`1d`・非数字は拒否され (exit 2)、
    拒否した値そのものは echo されない。空振り禁止: ループ 6 回すべてで
    assert が走る。"""
    for value in ("0", "0ms", "-5", "1h", "1d", "not-a-value"):
        with pytest.raises(SystemExit) as exc:
            ops._validate_lock_timeout_value(value)
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--lock-timeout" in err
        assert value not in err


def test_run_upgrade_script_passes_lock_timeout_via_pgoptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件4: `_run_upgrade_script` は `lock_timeout` を
    `_with_lock_timeout_option` 経由で `PGOPTIONS` に足す (DSN 自身が
    `options` を持たない場合)。"""
    calls: list[dict] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1", "42s")
    assert len(calls) == 1
    assert calls[0]["env"]["PGOPTIONS"] == "-c lock_timeout=42s"


def test_run_upgrade_script_keeps_the_dsns_own_pgoptions_alongside_lock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完了条件4: DSN 自身の `options` (`PGOPTIONS` に既に載る値) と
    `lock_timeout` の両方が effect を持つよう連結され、上書きされない。"""
    calls: list[dict] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    dsn_with_options = make_conninfo(_SENTINEL_DSN, options="-c search_path=foo")
    ops._run_upgrade_script(dsn_with_options, Path("/nonexistent/0099_does_not_matter.sql"), "app1", "42s")
    assert len(calls) == 1
    assert calls[0]["env"]["PGOPTIONS"] == "-c search_path=foo -c lock_timeout=42s"


# ===========================================================================
# コードレビュー1 高1: `cmd_upgrade_applications` 自身の CLI 経路で
# `--lock-timeout` の値検証と配線が効いていることの固定 (`_validate_lock_
# timeout_value`/`_run_upgrade_script` を直接呼ぶだけの上のテスト群は
# `cmd_upgrade_applications` のこの 2 行 (検証呼び出し・`_run_upgrade_
# script` への引き渡し) 自体が抜けても緑のままだった)。
# ===========================================================================


def test_upgrade_applications_rejects_an_ill_formed_lock_timeout_through_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """コードレビュー1 高1: `--lock-timeout` の値検証が `cmd_upgrade_
    applications` の CLI 経路自身でも、`psycopg.connect` より前に効いて
    いることを、到達不能な provision DSN で固定する -- 検証を通れば `_die`
    が先に exit 2 で止まるので、この DSN へ実際に接続を試みることは無い
    (実 PostgreSQL 不要)。"""
    monkeypatch.setenv("R2DB_CONTROL_DSN", "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1")
    with pytest.raises(SystemExit) as exc:
        ops.main(["upgrade-applications", "--lock-timeout", "0", "--dry-run"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--lock-timeout value must be a positive integer" in err  # 接続前に止まった証拠
    assert "0" not in err


def test_upgrade_applications_cli_lock_timeout_value_reaches_pgoptions(
    ops_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, synthetic_script_9999: Path,
) -> None:
    """コードレビュー1 高1 (RM2 の穴): `ops.main` の argv で渡した
    `--lock-timeout` の値が、その値のまま `_run_upgrade_script` を経由して
    実際の psql invocation の `PGOPTIONS` に届くことを、`cmd_upgrade_
    applications` 経由 (CLI 全体) で固定する -- `_run_upgrade_script` を
    直接呼ぶ既存テストと異なり、argv からの配線そのものを見る。"""
    app = provision_app(ops_env, "cliwireapp")
    calls: list[dict] = []

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        calls.append(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    try:
        rc = ops.main(["upgrade-applications", "--application", "cliwireapp", "--lock-timeout", "7500ms"])
        assert rc == 0
        assert len(calls) == 1
        assert calls[0]["env"]["PGOPTIONS"] == "-c lock_timeout=7500ms"
    finally:
        deprovision_app(ops_env, "cliwireapp")
