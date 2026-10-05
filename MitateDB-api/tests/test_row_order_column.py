"""Phase 11 WP-3 (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2, work
order docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md §5): the
internal row-order column `_mdb_row` -- present on every collection table
of both backends, never declarable or visible to a client request.

Covers: the column exists with the declared type on a NEW collection, on
both backends (completion conditions 1/2); `ApplicationCell._visible_
field_domains` is the single choke point that hides it from a select-all
read, on both backends (completion condition 3); migration `0015_row_
order_column_upgrade.sql` is idempotent, enumerates by table scan (not
the declared-type registry -- exercised directly against a zero-field
collection), and leaves this package's own bookkeeping tables and the
reserved name `audit_events` untouched (completion conditions 6/7);
declaring a field literally named `_mdb_row` is refused by the shared
identifier-syntax gate, not a dedicated check (completion condition 8).

Real-PostgreSQL fixtures mirror `tests/test_postgres.py`'s/`tests/test_
platform_upgrades.py`'s own established pattern (duplicated rather than
imported -- this repository's own precedent of not taking cross-test-
module import dependencies, independently applied here). Design R-8:
these tests must not be skipped -- a missing/unreachable local PostgreSQL
server fails loudly.
"""
from __future__ import annotations

import base64
import json
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

from mitatedb_api import paging
from mitatedb_api.auth import Principal, Role
from mitatedb_api.backend_postgres import PostgresBackend
from mitatedb_api.backend_sqlite import SQLiteBackend
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime
from mitatedb_api.errors import ValidationError

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"

ROW_ORDER_COLUMN = "_mdb_row"

# ---------------------------------------------------------------------------
# In-process fixtures (no PostgreSQL) -- completion conditions 2, 3 (SQLite
# half), 8.
# ---------------------------------------------------------------------------


def _sessions_for(cell: ApplicationCell, app_id: str):
    developer_principal = Principal(app_id, "test-dev-credential", Role.DEVELOPER)
    runtime_principal = Principal(app_id, "test-runtime-credential", Role.RUNTIME)
    developer = ApplicationDeveloper(cell, developer_principal)
    runtime = ApplicationRuntime(cell, runtime_principal)
    return developer, runtime


def test_sqlite_backend_create_collection_has_an_integer_primary_key_row_order_column() -> None:
    """完了条件 2: SQLite backend で新規 collection に `_mdb_row` があり、
    `INTEGER PRIMARY KEY` である (design D-2 の表)。`PRAGMA table_info`
    の `type` 列と `pk` フラグの両方を観測する -- `INTEGER PRIMARY KEY` は
    SQLite の rowid alias で、`pk` は 1 になる。"""
    backend = SQLiteBackend()
    backend.create_collection("widgets", {"name": "text"})
    rows = backend.raw_connection.execute('PRAGMA table_info("widgets")').fetchall()
    by_name = {row["name"]: row for row in rows}
    assert ROW_ORDER_COLUMN in by_name
    assert by_name[ROW_ORDER_COLUMN]["type"] == "INTEGER"
    assert by_name[ROW_ORDER_COLUMN]["pk"] == 1


def test_visible_field_domains_excludes_the_row_order_column_on_sqlite() -> None:
    """完了条件 3 (SQLite 側): 宣言 field 全部を select した read の key
    集合が宣言 field と一致し、`_mdb_row` を含まない。非空振り: 宣言
    collection 1 件 (`widgets`, 2 field) を実際に観測する。

    コードレビュー差し戻し (指摘 1): 明示 `fields=[...]` の read は除外の
    有無に関わらず `_mdb_row` を返さない (`_select_fields` が `requested`
    を `available` に対して検証するだけで、除外そのものは観測しない) --
    漏れが実際に起きうる経路は select-all (`fields` 省略) であり、
    `_select_fields` の `requested is None` 分岐が `list(available)` を
    そのまま返す (`cell.py::_select_fields`)。ここではその経路を実際に
    read して観測する。"""
    cell = ApplicationCell("app1", backend=SQLiteBackend())
    developer, runtime = _sessions_for(cell, "app1")
    developer.create_collection("widgets", {"name": "text", "score": "integer"})
    runtime.insert("widgets", {"name": "a", "score": 5})
    rows = runtime.read("widgets", fields=["name", "score"])
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"name", "score"}
    assert ROW_ORDER_COLUMN not in rows[0]
    # select-all (`fields` 省略) -- the real leak path (指摘 1).
    select_all_rows = runtime.read("widgets")
    assert len(select_all_rows) == 1
    assert set(select_all_rows[0].keys()) == {"name", "score"}
    assert ROW_ORDER_COLUMN not in select_all_rows[0]
    # The select-all path (`fields=None`) goes through the SAME helper
    # (`cell.py::ApplicationCell._select_fields` -> `_visible_field_
    # domains`) -- observed directly here, not merely inferred.
    with cell._backend.request_scope("schema") as scope:  # noqa: SLF001
        assert cell._visible_field_domains("widgets", scope=scope) == {"name": None, "score": None}  # noqa: SLF001


def test_declaring_the_row_order_column_name_as_a_field_is_rejected_by_identifier_syntax() -> None:
    """完了条件 8: `_mdb_row` を field として宣言する要求が識別子の構文
    (`identifiers.py::_IDENTIFIER` の `^[a-z][a-z0-9_]{0,62}$`, 先頭 `_` を拒む) で
    拒否される -- 追加の専用拒否経路は無い (design D-2 の add_field 行)。
    `add_field` 経由で確認する (design が名指す call site)。"""
    cell = ApplicationCell("app1", backend=SQLiteBackend())
    developer, _runtime = _sessions_for(cell, "app1")
    developer.create_collection("widgets", {"name": "text"})
    with pytest.raises(ValidationError) as excinfo:
        developer.add_field("widgets", ROW_ORDER_COLUMN, "text")
    assert excinfo.value.details["violated_declaration"] == "identifier_syntax"


def test_tampered_page_cursor_row_order_tie_break_type_mismatch_is_validation_failed_on_sqlite() -> None:
    """受け入れ監査 2026-09-25 観察 1: 契約 1.10.0 義務 (5) (`page/cursor`
    の順序値が declared type と数で合わないとき `VALIDATION_FAILED` /
    `request_schema` / `page/cursor`) を、SQLite backend の tie-break
    `_mdb_row` について固定する。`_mdb_row` は `_mdb_field_types` に登録
    が無いため、`cell.py::_decode_and_check_page_cursor` はこの列の
    declared type を `"integer"` に明示して検査する
    (`field_name == self._ROW_ORDER_COLUMN` の特別扱い) -- この検査が
    無ければ、SQLite backend は動的な列 affinity のため非整数の tie-
    break 値を検査で弾かず、PostgreSQL backend (物理 `bigint` domain が
    別途弾く) と結果が割れる。PostgreSQL 側の同じ tamper は
    `test_http.py::test_tampered_page_cursor_count_and_type_and_domain_
    mismatches_are_validation_failed` の脚 (f) が固定するので、ここは
    SQLite backend だけを対象にする。"""
    cell = ApplicationCell("app1", backend=SQLiteBackend())
    developer, runtime = _sessions_for(cell, "app1")
    developer.create_collection("widgets", {"name": "text"})
    runtime.insert("widgets", {"name": "a"})
    runtime.insert("widgets", {"name": "b"})
    items, next_page = runtime.read_page(
        "widgets", fields=["name"], order_by=[{"field": "name", "direction": "asc"}], limit=1)
    assert len(items) == 1
    assert next_page is not None, "a 1-of-2 page reported a null next_page"
    padded = next_page + "=" * (-len(next_page) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    binding = payload["b"]
    values = payload["v"]
    # design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2b.1: `values` is
    # `[name, _mdb_row]` -- the order-by term plus the row-order tie-break,
    # index-aligned with `order_spec`.
    assert len(values) == 2, values
    for tampered_row_order in ("x", 1.5):
        tampered_cursor = paging.encode_page_cursor([values[0], tampered_row_order], binding)
        with pytest.raises(ValidationError) as excinfo:
            runtime.read_page(
                "widgets", fields=["name"], order_by=[{"field": "name", "direction": "asc"}],
                limit=1, cursor=tampered_cursor)
        assert excinfo.value.details == {"violated_declaration": "request_schema", "field": "page/cursor"}, tampered_row_order


# ---------------------------------------------------------------------------
# Real-PostgreSQL fixtures -- completion conditions 1, 3 (PostgreSQL half),
# 6, 7. Mirrors tests/test_postgres.py / tests/test_platform_upgrades.py.
# ---------------------------------------------------------------------------


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
            "test_row_order_column.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These tests must not be "
            "skipped (design R-8).",
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
    """Bootstraps `0001`/`0002` under one throwaway prefix, plus a SECOND
    copy of `0003` whose ledger seed omits `15` -- a "pre-WP-3" `0003`
    stand-in (this WP's own real `0003` seeds `15` unconditionally, since
    a NEW application's own collections already carry the column via
    `create_collection`; the omitted-`15` copy provisions an application
    whose LEDGER has something for `0015` to still apply, matching an
    existing-application upgrade scenario)."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbrow{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_row_order_migrations")

    def _rewrite(name: str, text: str) -> Path:
        out = rewritten_dir / name
        out.write_text(text.replace("mitatedb", prefix))
        return out

    current_0003_text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text()
    pre_wp3_seed_line = "    (15, '0015_row_order_column_upgrade.sql')\n"
    assert pre_wp3_seed_line in current_0003_text, (
        "0003_provision_application.sql's own seed list no longer ends with the 15 line this "
        "fixture strips -- update this fixture's own string alongside it"
    )
    pre_wp3_0003_text = current_0003_text.replace(
        "    (10, '0010_idempotency_records_upgrade.sql'),\n" + pre_wp3_seed_line,
        "    (10, '0010_idempotency_records_upgrade.sql')\n",
    )
    assert "15" not in pre_wp3_0003_text.split("_mdb_platform_upgrades (upgrade_number", 1)[1].split(
        "ON CONFLICT", 1)[0]

    rewritten_0003 = _rewrite("0003_provision_application.sql", current_0003_text)
    rewritten_0003_pre_wp3 = _rewrite("0003_pre_wp3_provision_application.sql", pre_wp3_0003_text)
    rewritten_0004 = _rewrite(
        "0004_deprovision_application.sql", (MIGRATIONS_DIR / "0004_deprovision_application.sql").read_text())
    rewritten_0015 = _rewrite(
        "0015_row_order_column_upgrade.sql",
        (MIGRATIONS_DIR / "0015_row_order_column_upgrade.sql").read_text())

    try:
        _run_psql_ok(admin_dsn, _rewrite(
            "0001_bootstrap_platform.sql", (MIGRATIONS_DIR / "0001_bootstrap_platform.sql").read_text()),
            {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql_ok(provision_dsn, _rewrite(
            "0002_registry_and_functions.sql", (MIGRATIONS_DIR / "0002_registry_and_functions.sql").read_text()))
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        provision_script=rewritten_0003,
        pre_wp3_provision_script=rewritten_0003_pre_wp3,
        deprovision_script=rewritten_0004,
        upgrade_0015_script=rewritten_0015,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _app_namespace(platform: types.SimpleNamespace, app_id: str, runtime_password: str, developer_password: str):
    database = f"{platform.prefix}_app_{app_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return types.SimpleNamespace(
        app_id=app_id, database=database, runtime_role=runtime_role, developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
        # Carried alongside the per-application namespace (unlike `tests/
        # test_postgres.py`'s own `provision_app`) so a test that needs to
        # run a SECOND per-application upgrade script (`0015`) against
        # this SAME application, after its own fixture has returned, does
        # not need to reach back into `platform` at all.
        provision_dsn=platform.provision_dsn,
        upgrade_0015_script=platform.upgrade_0015_script,
    )


@pytest.fixture
def pg_app(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    """One application, provisioned via the pre-WP-3 `0003` stand-in
    (ledger carries `{6, 8, 9, 10}`, NOT `15`) -- `0015` still has
    something to apply against it."""
    app_id = "roworder"
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql_ok(
        platform.provision_dsn, platform.pre_wp3_provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    app = _app_namespace(platform, app_id, runtime_password, developer_password)
    try:
        yield app
    finally:
        last_error: Exception | None = None
        for attempt in range(8):
            try:
                _run_psql_ok(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})
                last_error = None
                break
            except RuntimeError as exc:
                if "is being accessed by other users" not in str(exc):
                    raise
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        if last_error is not None:
            raise last_error


def _columns(dsn: str, table_name: str) -> dict[str, dict]:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_identity, identity_generation "
                "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                [table_name],
            )
            return {row[0]: {"data_type": row[1], "is_identity": row[2], "identity_generation": row[3]}
                    for row in cur.fetchall()}
    finally:
        conn.close()


def test_postgres_backend_create_collection_has_a_generated_identity_row_order_column(pg_app) -> None:
    """完了条件 1: PostgreSQL backend で新規 collection に `_mdb_row` が
    あり、`GENERATED ALWAYS AS IDENTITY` である。非空振り: 宣言 collection
    1 件 (`widgets`) を実際に観測する。"""
    backend = PostgresBackend(runtime_dsn=pg_app.runtime_dsn, developer_dsn=pg_app.developer_dsn)
    try:
        with backend.request_scope("schema") as scope:
            backend.create_collection("widgets", {"name": "text"}, scope=scope)
        columns = _columns(pg_app.developer_dsn, "widgets")
        assert ROW_ORDER_COLUMN in columns
        assert columns[ROW_ORDER_COLUMN]["data_type"] == "bigint"
        assert columns[ROW_ORDER_COLUMN]["is_identity"] == "YES"
        assert columns[ROW_ORDER_COLUMN]["identity_generation"] == "ALWAYS"
    finally:
        backend.close()


def test_visible_field_domains_excludes_the_row_order_column_on_postgres(pg_app) -> None:
    """完了条件 3 (PostgreSQL 側): 完了条件 3 の SQLite テストと対の観測。
    非空振り: 宣言 collection 1 件 (`widgets`, 2 field) を実際に観測する。

    コードレビュー差し戻し (指摘 1): 明示 `fields=[...]` の read は除外の
    有無に関わらず `_mdb_row` を返さないため、漏れの実際の経路である
    select-all (`fields` 省略) を実際に read して観測する。加えて
    `cell._visible_field_domains("widgets")` の戻り値をドメイン値まで
    含めて等値で assert する -- 除外をやめる変異 (M3-3) がこの assert を
    単独で赤にする (select 経路を経ずに helper 自体の戻り値を直接見る)。
    """
    backend = PostgresBackend(runtime_dsn=pg_app.runtime_dsn, developer_dsn=pg_app.developer_dsn)
    cell = ApplicationCell(pg_app.app_id, backend=backend)
    try:
        developer, runtime = _sessions_for(cell, pg_app.app_id)
        developer.create_collection("widgets", {"name": "text", "score": "integer"})
        runtime.insert("widgets", {"name": "a", "score": 5})
        rows = runtime.read("widgets", fields=["name", "score"])
        assert len(rows) == 1
        assert set(rows[0].keys()) == {"name", "score"}
        assert ROW_ORDER_COLUMN not in rows[0]
        # select-all (`fields` 省略) -- the real leak path (指摘 1).
        select_all_rows = runtime.read("widgets")
        assert len(select_all_rows) == 1
        assert set(select_all_rows[0].keys()) == {"name", "score"}
        assert ROW_ORDER_COLUMN not in select_all_rows[0]
        # `PostgresBackend.field_domains` の実測値 (`postgres_types.py`
        # `_DOMAIN_BY_DATA_TYPE`/`_TEXT_DOMAIN_BY_DECLARED_TYPE`): `text`
        # 型・`string` 宣言は `"string"`、`integer` 物理型 (`BIGINT`) は
        # `"int64"`。除外をやめる変異はこの等値を単独で赤にする。
        with backend.request_scope("schema") as scope:
            assert cell._visible_field_domains("widgets", scope=scope) == {"name": "string", "score": "int64"}  # noqa: SLF001
    finally:
        backend.close()


def test_migration_0015_is_idempotent_and_enumerates_by_table_scan(pg_app) -> None:
    """完了条件 5 の帰結 (三方一致テストは他 file が持つ)、6 (0015 の
    2 回適用が成功する)、7 (0015 適用後、`_mdb_` の表と予約名 `audit_
    events` に `_mdb_row` が無く、宣言 collection にはある)。設計 §11 の
    実測 (D-2 の適用行) も兼ねる: `_mdb_field_types` の `DISTINCT entity`
    と列挙元 (`information_schema.tables`) は、0 field の collection
    (`_mdb_field_types` に行を持たない) では食い違う -- 列挙元は table
    scan であり `_mdb_field_types` 由来ではないことを、その食い違いその
    ものによって実測する。

    非空振り: `widgets` (宣言 collection, `_mdb_row` を得る) と `_mdb_
    field_types` (`_mdb_` の表, `_mdb_row` を得ない) を実際に観測する。
    """
    admin_dsn = pg_app.developer_dsn  # developer role owns every collection table it creates directly below
    conn = psycopg.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            # A pre-existing declared collection -- created via raw DDL
            # (not `create_collection`, which already includes the
            # column as of this WP) to model a collection that predates
            # this migration.
            cur.execute("CREATE TABLE public.widgets (id text PRIMARY KEY, name text)")
            # A zero-field collection: `_mdb_field_types` never gets a
            # row for it (no declared field), but it IS a real BASE
            # TABLE -- the exact case design §11 asks to be measured.
            cur.execute("CREATE TABLE public.emptycol ()")
            # The reserved name -- excluded from enumeration by name,
            # regardless of any registry state.
            cur.execute("CREATE TABLE public.audit_events (id text PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    # Applied TWICE -- completion condition 6 (idempotent).
    for _ in range(2):
        _run_psql_ok(pg_app.provision_dsn, pg_app.upgrade_0015_script, {"app_id": pg_app.app_id})

    widgets_columns = _columns(pg_app.developer_dsn, "widgets")
    emptycol_columns = _columns(pg_app.developer_dsn, "emptycol")
    field_types_columns = _columns(pg_app.developer_dsn, "_mdb_field_types")
    audit_events_columns = _columns(pg_app.developer_dsn, "audit_events")

    # Completion condition 7 -- present on the declared collection...
    assert ROW_ORDER_COLUMN in widgets_columns
    assert widgets_columns[ROW_ORDER_COLUMN]["data_type"] == "bigint"
    assert widgets_columns[ROW_ORDER_COLUMN]["is_identity"] == "YES"
    # ...present on the zero-field collection too (table-scan enumeration,
    # not the declared-type registry: `emptycol` has zero rows in `_mdb_
    # field_types`, yet still gets the column)...
    assert ROW_ORDER_COLUMN in emptycol_columns
    # ...but absent from this package's own bookkeeping table...
    assert ROW_ORDER_COLUMN not in field_types_columns
    # ...and absent from the reserved name `audit_events`.
    assert ROW_ORDER_COLUMN not in audit_events_columns

    # §11's own DISTINCT entity measurement: `emptycol` is a real
    # collection table but carries no row in `_mdb_field_types` at all
    # (0 declared fields) -- the enumeration source (`information_
    # schema.tables`) and `_mdb_field_types`'s own `DISTINCT entity` set
    # therefore differ by exactly this one name.
    conn = psycopg.connect(pg_app.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT entity FROM public._mdb_field_types")
            distinct_entities = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert "widgets" not in distinct_entities  # raw DDL above never wrote a row to the registry either
    assert "emptycol" not in distinct_entities
    assert "emptycol" in {"widgets", "emptycol", "audit_events"} - distinct_entities

    # Ledger idempotency -- exactly one row for upgrade_number 15 despite
    # two applications.
    conn = psycopg.connect(pg_app.developer_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public._mdb_platform_upgrades WHERE upgrade_number = 15")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()
