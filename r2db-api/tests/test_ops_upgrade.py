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

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    import os

    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


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
        rc = ops.main(["upgrade-applications", "--application", "upga", "--dry-run"])
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
        rc = ops.main(["upgrade-applications", "--application", "upgb", "--dry-run"])
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
        rc = ops.main(["upgrade-applications"])
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
        assert ops.main(["upgrade-applications", "--application", "idemapp"]) == 0
        before = _ledger_numbers(app.developer_dsn)
        assert ops.main(["upgrade-applications", "--application", "idemapp"]) == 0
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
        assert ops.main(["upgrade-applications", "--application", "exitapp"]) == 0
        # 1 -- enumeration failure (bad provision DSN).
        monkeypatch.setenv("R2DB_CONTROL_DSN", "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1")
        assert ops.main(["upgrade-applications"]) == 1
        monkeypatch.setenv("R2DB_CONTROL_DSN", ops_env.control_dsn)
        # 2 -- usage error (provision DSN entirely unset).
        monkeypatch.delenv("R2DB_CONTROL_DSN")
        with pytest.raises(SystemExit) as exc:
            ops.main(["upgrade-applications"])
        assert exc.value.code == 2
        monkeypatch.setenv("R2DB_CONTROL_DSN", ops_env.control_dsn)
        # 4 -- dry-run, something pending.
        monkeypatch.setattr(platform_upgrades, "PLATFORM_UPGRADE_NUMBERS", frozenset({9, 9999}))
        assert ops.main(["upgrade-applications", "--application", "exitapp", "--dry-run"]) == 4
    finally:
        deprovision_app(ops_env, "exitapp")


def test_upgrade_applications_exit_code_3_on_failure(
    ops_env: types.SimpleNamespace, synthetic_script_9999: Path
) -> None:
    synthetic_script_9999.write_text(synthetic_script_9999.read_text().replace("REGISTRY_SCHEMA", ops_env.schema))
    bad = provision_app(ops_env, "failapp")
    try:
        assert ops.main(["upgrade-applications", "--application", "failapp"]) == 3
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
        rc = ops.main(["upgrade-applications", "--application", "scriptapp", "--script", "9"])
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
        ops.main(["upgrade-applications", "--application", "totally_unregistered_slug"])
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
            ops.main(["upgrade-applications", "--application", "scriptmiss", "--script", "1234"])
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
            ops.main(["upgrade-applications", "--application", "scriptunk", "--script", "42"])
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

    rc = ops.main(["upgrade-applications", "--application", "ghostapply"])
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
        rc = ops.main(["upgrade-applications", "--application", "enabledapp", "--dry-run"])
        assert rc == 0, "a fully-seeded, disabled application must still report nothing pending"

        with psycopg.connect(app.developer_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public._r2db_platform_upgrades WHERE upgrade_number = 9")
            conn.commit()
        rc = ops.main(["upgrade-applications"])
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
        rc = ops.main(["upgrade-applications", "--application", "failapp"])
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
        assert ops.main(["upgrade-applications", "--application", "skipagg"]) == 0
        assert _ledger_numbers(skip.developer_dsn) == frozenset({9, 10, 11, 9999})

        rc = ops.main(["upgrade-applications"])
        out = capsys.readouterr().out
        assert rc == 3
        assert "1 succeeded, 1 failed, 1 skipped (applied)" in out
        assert _ledger_numbers(good.developer_dsn) == frozenset({9, 10, 11, 9999})
    finally:
        deprovision_app(ops_env, "goodagg")
        deprovision_app(ops_env, "failapp")
        deprovision_app(ops_env, "skipagg")
