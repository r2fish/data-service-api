"""`MitateDB-api/src/mitatedb_api/ops.py`'s per-application-upgrade/
deprovision psql-invocation helpers (`_run_upgrade_script`/`_run_
deprovision_script`) and the platform migration files' own re-
applicability -- direct, real-subprocess and real-PostgreSQL tests,
duplicated from `test_ops_upgrade.py`'s/`test_migration_0007_ddl.py`'s
own established fixture shapes rather than imported (this repository's
own precedent of not taking cross-test-module import dependencies).

Covers: 0011/0012 (platform single-shot migrations) applied twice with a
diff-0/exit-0 comparison; `declare-surfaces`/`declare-process-ceilings`
applied twice through the CLI with the same comparison; one per-
application upgrade applied twice through `upgrade-applications`, the
second run applying nothing; the two `ON_ERROR_STOP` layers (the psql
argv `_run_upgrade_script`/`_run_deprovision_script` build, and each
platform migration file's own `\\set ON_ERROR_STOP on`); a dependency-
missing apply (0011 without 0007) failing by exit code; the two psql-
invocation helpers' own now-required `--lock-timeout` (passed to psql via
`PGOPTIONS`, rejected by the CLI when absent, value-validated before any
psql subprocess starts).
"""
from __future__ import annotations

import os
import re
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

import mitatedb_api.ops as ops

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"

_TEST_LOCK_TIMEOUT = "5000ms"


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
            "test_platform_migration_reapply.py requires a reachable local PostgreSQL server. "
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
    """`0001`+`0002`+`0005`+`0012`+`0013`+`0007`+`0011`, in the same order
    `control_plane_harness.bootstrap_control_platform` already applies
    them (0011 depends on 0007's own table; 0013 depends on 0005/0012;
    the rest are order-independent, design D-5 (ii)/0012's own header) --
    plus rewritten
    copies of `0003`/`0004`/`0006`/`0008`/`0009` in the SAME migrations
    directory, for the per-application-upgrade/deprovision tests below
    (never applied by this fixture itself; `provision_app`/`deprovision_
    app`/`upgrade-applications` apply them per test)."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbmreap{secrets.token_hex(4)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    registry_schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_migration_reapply_" + prefix)
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql", "0002_registry_and_functions.sql",
        "0003_provision_application.sql", "0004_deprovision_application.sql",
        "0005_application_audit.sql", "0006_declared_field_types_upgrade.sql",
        "0007_platform_declarations.sql", "0008_platform_upgrades_upgrade.sql",
        "0009_field_constraints_upgrade.sql", "0011_process_ceilings.sql",
        "0012_role_connection_limits.sql", "0013_role_statement_timeouts.sql",
    ):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql_ok(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql_ok(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        _run_psql_ok(provision_dsn, rewritten["0005_application_audit.sql"])
        _run_psql_ok(provision_dsn, rewritten["0012_role_connection_limits.sql"])
        _run_psql_ok(provision_dsn, rewritten["0013_role_statement_timeouts.sql"])
        _run_psql_ok(provision_dsn, rewritten["0007_platform_declarations.sql"],
                     {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql_ok(provision_dsn, rewritten["0011_process_ceilings.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix, admin_dsn=admin_dsn, provision_dsn=provision_dsn, provision_role=provision_role,
        platform_db=platform_db, registry_schema=registry_schema, api_role=api_role,
        controlplane_role=controlplane_role, migrations_dir=rewritten_dir,
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
        migration_paths=rewritten,
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


def _read_declaration(platform: types.SimpleNamespace, key: str):
    conn = psycopg.connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT value FROM {table} WHERE key = %s").format(
                    table=sql.Identifier(platform.registry_schema, "platform_declarations")),
                [key],
            )
            row = cur.fetchone()
            return row[0] if row else None
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
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args],
        capture_output=True, text=True, env=env,
    )


# ===========================================================================
# migration-column classification (実測、着手時の手順): 各 migration
# ファイルの種別。0004 (deprovision) は運用の起点の列から除く -- 適用する
# と、この列の他のファイルが作った application を消してしまうため
# (下の `_REAPPLY_MIGRATION_SEQUENCE` 参照)。
#
# | file | 種別 | 実測の根拠 (ヘッダ・本文) |
# |---|---|---|
# | 0001_bootstrap_platform.sql | bootstrap | cluster administrator が一度だけ実行、role/DB を新設 |
# | 0002_registry_and_functions.sql | bootstrap | provision role 接続、"Run once, after 0001"、`:app_id` を取らない |
# | 0003_provision_application.sql | provisioning | `:app_id` を取り、application を 1 件新設 ("once per application") |
# | 0004_deprovision_application.sql | deprovision | `:app_id` を取り、application を丸ごと削除 -- 起点の列から除外 |
# | 0005_application_audit.sql | platform migration | `:app_id` を取らない、"naturally idempotent"/`CREATE TABLE IF NOT EXISTS` と自己記載 |
# | 0006_declared_field_types_upgrade.sql | per-application upgrade | `:app_id` を取り、"harmless no-op"、`PLATFORM_UPGRADE_NUMBERS` の一員 |
# | 0007_platform_declarations.sql | platform migration | `:app_id` を取らない、`ALTER ROLE`/`CREATE TABLE IF NOT EXISTS`/`ON CONFLICT` で再適用可 |
# | 0008_platform_upgrades_upgrade.sql | per-application upgrade | 同上 (0006 と同型) |
# | 0009_field_constraints_upgrade.sql | per-application upgrade | 同上 |
# | 0010_idempotency_records_upgrade.sql | per-application upgrade | 同上 |
# | 0011_process_ceilings.sql | platform migration | `:app_id` を取らない、ヘッダに "IDEMPOTENCY" 明記 |
# | 0012_role_connection_limits.sql | platform migration | `:app_id` を取らない、ヘッダに "IDEMPOTENCY" 明記 (既存 application ロールを更新する内部ループを持つが `:app_id` 引数は取らない) |
# | 0013_role_statement_timeouts.sql | platform migration | `:app_id` を取らない、ヘッダに "IDEMPOTENCY" 明記 (0012 と同型の内部ループを持つ) |
# ===========================================================================

_REAPPLY_EXCLUDED_FILENAME = "0004_deprovision_application.sql"
_REAPPLY_MIGRATION_SEQUENCE = [p for p in MIGRATIONS_DIR.glob("*.sql") if p.name != _REAPPLY_EXCLUDED_FILENAME]
_REAPPLY_MIGRATION_SEQUENCE.sort()
_REAPPLY_STARTING_POINTS = range(len(_REAPPLY_MIGRATION_SEQUENCE) + 1)

#: platform migrations (種別実測により 0005 も含む) -- 2 回目の適用は
#: それぞれの psql 呼出しを直接もう一度行う。
_REAPPLY_PLATFORM_MIGRATION_FILENAMES = (
    "0005_application_audit.sql", "0007_platform_declarations.sql",
    "0011_process_ceilings.sql", "0012_role_connection_limits.sql",
    "0013_role_statement_timeouts.sql",
)
#: per-application upgrade (種別実測) -- 2 回目の適用は運用の経路
#: (`upgrade-applications --lock-timeout`) を通す。生の psql では呼ばない。
_REAPPLY_PER_APPLICATION_UPGRADE_NUMBER_BY_FILENAME = {
    "0006_declared_field_types_upgrade.sql": 6,
    "0008_platform_upgrades_upgrade.sql": 8,
    "0009_field_constraints_upgrade.sql": 9,
    "0010_idempotency_records_upgrade.sql": 10,
}
_REAPPLY_TEST_APP_ID = "reapp"


# ===========================================================================
# Historical content per starting point (Q-5 (b): a real deployment already
# at prefix N saw the first N files as they stood before the (N+1)th file
# arrived, not today's HEAD -- 0002/0003/0012 (among others) have all been
# edited in place after their own commit added them.)
# ===========================================================================

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_relpath(path: Path) -> str:
    return str(path.relative_to(_REPO_ROOT))


def _added_commit(path: Path) -> "str | None":
    """The oldest commit that added `path`, or `None` when `path` is not
    tracked by git yet (a migration file still only in the working tree)
    -- `_historical_files_for_prefix` treats that the same way it treats a
    prefix boundary this repository's own recorded history does not reach
    at all: there is no earlier state to read, so every file at that
    prefix uses its own current content. A TRACKED file whose own `git
    log --diff-filter=A` comes back empty (a shallow clone or otherwise
    incomplete local history) raises rather than silently falling back to
    current content, same as any other git failure below."""
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", _repo_relpath(path)],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if tracked.returncode != 0:
        return None
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", _repo_relpath(path)],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not determine the commit that added {path.name}: {result.stderr}")
    commits = result.stdout.strip().splitlines()
    if not commits:
        raise RuntimeError(
            f"{path.name} is tracked by git but its own history has no commit that added it "
            "(a shallow clone or otherwise incomplete local checkout)"
        )
    return commits[-1]  # oldest listed line is the original add


def _parent_commit(commit: str) -> str:
    result = subprocess.run(["git", "rev-parse", f"{commit}^"], cwd=_REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"could not resolve the commit preceding {commit}: {result.stderr}")
    return result.stdout.strip()


def _file_content_at_commit(commit: str, path: Path) -> "str | None":
    """`None` only when the path genuinely did not exist yet at `commit`
    (git's own "exists on disk, but not in <commit>" message) -- any OTHER
    failure to read (an incomplete or unreadable local checkout of the
    repository's own commit history) raises instead of silently falling
    back, so a broken checkout fails this test rather than skipping it."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{_repo_relpath(path)}"], cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout
    if "exists on disk, but not in" in result.stderr:
        return None
    raise RuntimeError(f"could not read {path.name} as of {commit}: {result.stderr}")


def _historical_files_for_prefix(prefix_n: int) -> dict:
    """The first `prefix_n` files of `_REAPPLY_MIGRATION_SEQUENCE`, each
    read from the repository's own recorded commit history as of the
    parent of the commit that added file number `prefix_n` (0-indexed) in
    that same sequence -- i.e. the repository state right before that
    file arrived. A file that did not exist yet at that point (it and the
    boundary file were introduced together) falls back to its own current
    content -- there is no earlier state to read. Empty for `prefix_n ==
    0` (nothing precedes the sequence), `prefix_n == len(_REAPPLY_
    MIGRATION_SEQUENCE)` (the largest starting point IS candidate HEAD;
    this function is never called for it), or a boundary file with no
    commit adding it yet (`_added_commit` returns `None`)."""
    if prefix_n <= 0 or prefix_n >= len(_REAPPLY_MIGRATION_SEQUENCE):
        return {}
    boundary = _REAPPLY_MIGRATION_SEQUENCE[prefix_n]
    added_commit = _added_commit(boundary)
    if added_commit is None:
        return {}
    parent = _parent_commit(added_commit)
    historical: dict = {}
    for i in range(prefix_n):
        target = _REAPPLY_MIGRATION_SEQUENCE[i]
        content = _file_content_at_commit(parent, target)
        historical[target.name] = target.read_text() if content is None else content
    return historical


#: `GRANT USAGE ON SCHEMA public TO :"runtime_role"` has always been
#: there (a different role); the one that matters here is the one that
#: lets the PROVISION role itself (`SESSION_USER` at apply time,
#: `_app_dsn`'s own login for `read_applied_upgrade_numbers`) see the
#: schema at all -- real files space-align their keywords (two spaces
#: after `GRANT`/`USAGE`), so this matches on whitespace, not an exact
#: string.
_GRANT_PUBLIC_SCHEMA_USAGE_TO_SESSION_USER_RE = re.compile(
    r"GRANT\s+USAGE\s+ON\s+SCHEMA\s+public\s+TO\s+SESSION_USER")


def _public_schema_grant_diagnosis(prefix_n: int) -> "tuple[bool, bool] | None":
    """`(has_grant, covers_0008)` for the historical `0003` content this
    starting point would use, or `None` when `0003` is not part of this
    prefix's own history at all (HEAD's own content applies to it
    later, unconditionally correct). Shared by the exclusion predicate
    below and by its own pinned test, so a mutation to either half is
    visible from the test, not only from the predicate's own combined
    return value."""
    if prefix_n <= 0 or prefix_n >= len(_REAPPLY_MIGRATION_SEQUENCE):
        return None
    historical = _historical_files_for_prefix(prefix_n)
    historical_0003 = historical.get("0003_provision_application.sql")
    if historical_0003 is None:
        return None
    has_grant = bool(_GRANT_PUBLIC_SCHEMA_USAGE_TO_SESSION_USER_RE.search(historical_0003))
    covers_0008 = "0008_platform_upgrades_upgrade.sql" in historical
    return has_grant, covers_0008


def _prefix_predates_the_public_schema_usage_grant(prefix_n: int) -> bool:
    """A starting point is excluded from parametrize (never run at all,
    not skipped) exactly when both hold: the historical `0003` content
    this starting point would use does not yet contain the provision
    role's own `GRANT USAGE ON SCHEMA public`, AND the historical prefix
    itself does not reach as far as `0008` (which would otherwise grant
    it before any per-application upgrade script runs). 0003 に public
    schema の USAGE 付与が入る前の版で provision した application は、
    現行の ops の upgrade が台帳を読めず失敗するので対象外 (roadmap
    R-47)."""
    diagnosis = _public_schema_grant_diagnosis(prefix_n)
    if diagnosis is None:
        return False
    has_grant, covers_0008 = diagnosis
    return (not has_grant) and (not covers_0008)


_REAPPLY_EXCLUDED_STARTING_POINTS = frozenset(
    n for n in _REAPPLY_STARTING_POINTS if _prefix_predates_the_public_schema_usage_grant(n)
)
_REAPPLY_PARAMETRIZED_STARTING_POINTS = [
    n for n in _REAPPLY_STARTING_POINTS if n not in _REAPPLY_EXCLUDED_STARTING_POINTS
]


def test_excluded_starting_points_are_pinned() -> None:
    """`_prefix_predates_the_public_schema_usage_grant` が機械的に除外する
    起点の集合は今のところ {3, 4, 5, 6} である。空振り防止: 除外される起点
    (6) では両方の条件が実際に偽、除外されない起点 (8) では両方が実際に真
    であること、かつ HEAD 自身の 0003 がこの正規表現に一致することを
    確かめる (0 件・常に偽の正規表現では通らない)。"""
    assert _REAPPLY_EXCLUDED_STARTING_POINTS == frozenset({3, 4, 5, 6})
    assert _public_schema_grant_diagnosis(6) == (False, False)
    assert _public_schema_grant_diagnosis(8) == (True, True)
    head_0003 = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text()
    assert _GRANT_PUBLIC_SCHEMA_USAGE_TO_SESSION_USER_RE.search(head_0003)


# ===========================================================================
# W3-1: the reapplicability evidence's own starting-point coverage
# ===========================================================================


def test_reapply_starting_points_cover_every_migration_file_as_a_contiguous_prefix() -> None:
    """W3-1 (design W-3/W-8): 起点の列は `_REAPPLY_
    MIGRATION_SEQUENCE` そのもの (parametrize と同じモジュール定数) であり、
    件数は「`migrations/*.sql` の総数 − 1 (0004 を除く) + 1」に一致し、
    番号順の先頭からの連続である。実際に parametrize される件数は、そこから
    機械的な対象外 (`_REAPPLY_EXCLUDED_STARTING_POINTS`) を引いたもの。"""
    all_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert len(all_files) > 0
    assert len(_REAPPLY_MIGRATION_SEQUENCE) == len(all_files) - 1
    assert _REAPPLY_MIGRATION_SEQUENCE == sorted(
        p for p in all_files if p.name != _REAPPLY_EXCLUDED_FILENAME)
    numbers = [int(p.name[:4]) for p in _REAPPLY_MIGRATION_SEQUENCE]
    assert numbers == sorted(numbers)
    starting_points = list(_REAPPLY_STARTING_POINTS)
    assert len(starting_points) == len(all_files) - 1 + 1
    assert starting_points == list(range(len(starting_points)))
    assert len(_REAPPLY_PARAMETRIZED_STARTING_POINTS) == len(starting_points) - len(_REAPPLY_EXCLUDED_STARTING_POINTS)


def test_at_least_one_starting_point_uses_content_that_differs_from_head() -> None:
    """空振り防止: `_historical_files_for_prefix` が読む過去の内容は、
    対象外 (`_REAPPLY_EXCLUDED_STARTING_POINTS`) を除いた起点のうち
    少なくとも 1 つで HEAD の内容と実際に異なる (0002/0003/0012 の
    ように追加後に書き換えられたファイルがある限り、この assert は毎回
    自明に成り立つのではなく、実測に依存する)。"""
    differing_by_prefix: dict[int, list[str]] = {}
    for prefix_n in _REAPPLY_PARAMETRIZED_STARTING_POINTS:
        historical = _historical_files_for_prefix(prefix_n)
        differing = [
            name for name, content in historical.items()
            if content != (MIGRATIONS_DIR / name).read_text()
        ]
        if differing:
            differing_by_prefix[prefix_n] = differing
    assert differing_by_prefix, "no starting point used content that differs from HEAD"


# ===========================================================================
# 39/40/41: 0005/0007/0011/0012 (platform migration) と 0006/0008-0010
# (per-application upgrade、`upgrade-applications` の経路) を、migration 列
# のすべての起点から候補 HEAD まで適用したうえで、もう一度適用する。
# ===========================================================================


def _constraint_definition(dsn: str, conname: str) -> str:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s", [conname])
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _role_connection_limits(dsn: str, api_role: str, controlplane_role: str) -> dict:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname IN (%s, %s)",
                [api_role, controlplane_role],
            )
            return dict(cur.fetchall())
    finally:
        conn.close()


def _role_setting(dsn: str, role: str) -> "list[str] | None":
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.setconfig FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole "
                "WHERE r.rolname = %s AND s.setdatabase = 0",
                [role],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _declaration_rows_excluding_updated_at(dsn: str, schema: str) -> dict:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT key, value FROM {table} ORDER BY key").format(
                    table=sql.Identifier(schema, "platform_declarations")))
            return dict(cur.fetchall())
    finally:
        conn.close()


def _table_acl(dsn: str, schema: str, table: str) -> list:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s",
                [schema, table],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _function_def_and_acl(dsn: str, schema: str, function_name: str) -> tuple:
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_get_functiondef(p.oid), p.proacl FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = %s AND p.proname = %s",
                [schema, function_name],
            )
            row = cur.fetchone()
            return (row[0], row[1]) if row else (None, None)
    finally:
        conn.close()


def _role_connlimit(dsn: str, role: str) -> "int | None":
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname = %s", [role])
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _drift_platform_objects_before_reapplication(
    admin_dsn: str, provision_dsn: str, registry_schema: str, api_role: str, controlplane_role: str,
    auditreader_role: str, runtime_role: str,
) -> None:
    """manually drifts, for EACH platform migration file
    `apply-platform-migration` is about to re-apply, the ONE object
    that file's own header says it (re)asserts unconditionally on every
    run -- an ACL (0005), a role setting (0007), a declared CHECK
    constraint (0011), a function body (0012), and two role settings
    (0013: `mitatedbsvc_auditreader` and one already-provisioned
    application's own runtime role). Mirrors the SAME drift shapes
    `test_ops_apply_platform_migration.py`'s own per-file tests use."""
    # 0005: application_audit's own `REVOKE ALL ... FROM PUBLIC` runs
    # every time -- add a PUBLIC grant by hand.
    conn = psycopg.connect(provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("GRANT SELECT ON {table} TO PUBLIC").format(
                table=sql.Identifier(registry_schema, "application_audit")))
    finally:
        conn.close()
    # 0007: controlplane_role's own `ALTER ROLE ... SET statement_timeout`
    # runs every time -- hand-change it.
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9999ms'").format(
                sql.Identifier(controlplane_role)))
    finally:
        admin.close()
    # 0011: `platform_declarations_key_check`'s own DROP/ADD CONSTRAINT
    # runs every time -- hand-narrow it, admitting only the rows 0007
    # already seeded so the narrowed CHECK itself does not fail to add.
    conn = psycopg.connect(provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT platform_declarations_key_check").format(
                sql.Identifier(registry_schema, "platform_declarations")))
            cur.execute(
                sql.SQL(
                    "ALTER TABLE {} ADD CONSTRAINT platform_declarations_key_check "
                    "CHECK (key IN ('surfaces', 'audit_coalescing_window_ms', 'audit_writer_roles'))"
                ).format(sql.Identifier(registry_schema, "platform_declarations")))
    finally:
        conn.close()
    # 0012: `begin_provision_application`'s own `CREATE OR REPLACE
    # FUNCTION` runs every time -- hand-edit the body.
    conn = psycopg.connect(provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION {fn}(p_app_id text, p_runtime_password text, "
                    "p_developer_password text) RETURNS TABLE(database_name text, runtime_role text, "
                    "developer_role text) LANGUAGE plpgsql AS $fn$ BEGIN RAISE EXCEPTION 'drifted stub'; END; $fn$"
                ).format(fn=sql.Identifier(registry_schema, "begin_provision_application")))
    finally:
        conn.close()
    # 0013: `mitatedbsvc_auditreader`'s and one already-provisioned
    # application's own runtime role's `ALTER ROLE ... SET statement_
    # timeout` both run every time -- hand-change them.
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '9999ms'").format(
                sql.Identifier(auditreader_role)))
            cur.execute(sql.SQL("ALTER ROLE {} RESET statement_timeout").format(
                sql.Identifier(runtime_role)))
    finally:
        admin.close()


@pytest.mark.parametrize("prefix_n", _REAPPLY_PARAMETRIZED_STARTING_POINTS)
def test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix(
    prefix_n: int, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """完了条件39/40/41 (design W-3/W-8): `prefix_n` は
    `_REAPPLY_MIGRATION_SEQUENCE` (0004 を除く migration 列) の先頭から
    N 個を適用した状態 -- その N 個は、その時点で実在した内容 (`_historical_
    files_for_prefix`、Q-5 (b): 稼働中の古い状態) で適用し、platform 用の
    ファイルは platform DB に直接、per-application upgrade は
    `upgrade-applications --script <N>` で、provisioning (0003) は 1 件の
    application として適用する。`prefix_n` が 3 以上の起点では application
    が存在する (0003 が列の先頭寄りにあるため)。候補 HEAD まで残りを
    (今日の内容で) 適用したのち、台帳から per-application の番号
    (6/8/9/10) を消して `upgrade-applications` を実際に走らせ (未適用が
    無ければ本文は実行されない)、platform migration (0005/0007/0011/0012/
    0013、`apply-platform-migration` 経由) はもう一度適用し、per-
    application upgrade は `upgrade-applications` (`--lock-timeout` 付き、
    `--script` 無し) をもう一度実行し、すべての終了コードが 0 であること
    と、`updated_at` を除いた宣言の値・widened 制約定義・ロールの
    `CONNECTION LIMIT`・タイムアウト設定 (auditreader・application の
    runtime role を含む)・台帳の差分が 0 であることを確かめる。bootstrap
    (0001/0002) と provisioning (0003) は一度だけ流す設計であり、2 回目
    の適用の対象に含めない。"""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbmreapn{prefix_n}{secrets.token_hex(3)}"
    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    registry_schema = f"{prefix}_registry"
    provision_password = secrets.token_urlsafe(24)
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    app_database = f"{prefix}_app_{_REAPPLY_TEST_APP_ID}"

    rewritten_dir = tmp_path_factory.mktemp(f"mitatedb_reapply_seq_{prefix_n}_" + prefix)
    rewritten: dict[str, Path] = {src.name: rewritten_dir / src.name for src in _REAPPLY_MIGRATION_SEQUENCE}
    head_text: dict[str, str] = {
        src.name: src.read_text().replace("mitatedb", prefix) for src in _REAPPLY_MIGRATION_SEQUENCE
    }
    historical_text_raw = _historical_files_for_prefix(prefix_n)
    historical_text = {name: text.replace("mitatedb", prefix) for name, text in historical_text_raw.items()}

    state = {"provision_dsn": None}
    applied_content: dict[str, str] = {}

    def _apply_one(name: str, migration_text: str) -> None:
        applied_content[name] = migration_text
        target = rewritten[name]
        target.write_text(migration_text)
        if name == "0001_bootstrap_platform.sql":
            _run_psql_ok(admin_dsn, target, {"provision_password": provision_password})
            state["provision_dsn"] = _dsn_with(
                admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        elif name == "0002_registry_and_functions.sql":
            _run_psql_ok(state["provision_dsn"], target)
        elif name == "0003_provision_application.sql":
            _run_psql_ok(state["provision_dsn"], target, {
                "app_id": _REAPPLY_TEST_APP_ID, "runtime_password": runtime_password,
                "developer_password": developer_password,
            })
        elif name == "0007_platform_declarations.sql":
            _run_psql_ok(state["provision_dsn"], target,
                        {"api_role": api_role, "controlplane_role": controlplane_role})
        elif name in _REAPPLY_PER_APPLICATION_UPGRADE_NUMBER_BY_FILENAME:
            number = _REAPPLY_PER_APPLICATION_UPGRADE_NUMBER_BY_FILENAME[name]
            ns = types.SimpleNamespace(
                provision_dsn=state["provision_dsn"], registry_schema=registry_schema, migrations_dir=rewritten_dir)
            result = _run_ops(ns, "upgrade-applications", "--application", _REAPPLY_TEST_APP_ID,
                              "--script", str(number), "--lock-timeout", _TEST_LOCK_TIMEOUT)
            assert result.returncode == 0, result.stdout + result.stderr
        else:  # remaining platform migrations (0005/0011/0012), no variables
            _run_psql_ok(state["provision_dsn"], target)

    try:
        for i in range(prefix_n):
            name = _REAPPLY_MIGRATION_SEQUENCE[i].name
            _apply_one(name, historical_text.get(name, head_text[name]))
        for i in range(prefix_n, len(_REAPPLY_MIGRATION_SEQUENCE)):
            name = _REAPPLY_MIGRATION_SEQUENCE[i].name
            _apply_one(name, head_text[name])

        # A file whose historical content genuinely differs from HEAD must
        # have been applied with that HISTORICAL content, not silently
        # substituted with HEAD's own -- end-state comparisons alone
        # (the snapshot below) cannot tell the two apart once later
        # migrations converge the database to the same terminal state.
        for name, historical in historical_text.items():
            if historical != head_text[name]:
                assert applied_content[name] == historical, name

        provision_dsn = state["provision_dsn"]

        # Force the per-application upgrade scripts to actually run their
        # own bodies (a freshly provisioned application already carries
        # 6/8/9/10 in its own ledger, seeded by 0003 itself, so every
        # `--script N` call above was a no-op "already recorded" skip):
        # clear the ledger, then run the bulk operational path with
        # today's own file content already in place, and check its own
        # output shows real work, not a silent no-op.
        for number in (6, 8, 9, 10):
            delete_ledger_row(admin_dsn, app_database, number)
        ns = types.SimpleNamespace(
            provision_dsn=provision_dsn, registry_schema=registry_schema, migrations_dir=rewritten_dir)
        r_real = _run_ops(ns, "upgrade-applications", "--application", _REAPPLY_TEST_APP_ID,
                          "--lock-timeout", _TEST_LOCK_TIMEOUT)
        assert r_real.returncode == 0, r_real.stdout + r_real.stderr
        assert "1 succeeded" in r_real.stdout, r_real.stdout
        assert ledger_numbers(admin_dsn, app_database) == frozenset({6, 8, 9, 10})

        runtime_role = f"{app_database}_rt"
        auditreader_role = f"{prefix}svc_auditreader"

        def _snapshot() -> tuple:
            return (
                _role_setting(provision_dsn, api_role),
                _role_setting(provision_dsn, controlplane_role),
                _declaration_rows_excluding_updated_at(provision_dsn, registry_schema),
                _constraint_definition(provision_dsn, "platform_declarations_key_check"),
                _table_acl(provision_dsn, registry_schema, "platform_declarations"),
                _table_acl(provision_dsn, registry_schema, "application_audit"),
                _function_def_and_acl(provision_dsn, registry_schema, "begin_provision_application"),
                _role_connection_limits(provision_dsn, api_role, controlplane_role),
                _role_connlimit(provision_dsn, runtime_role),
                _role_setting(provision_dsn, auditreader_role),
                _role_setting(provision_dsn, runtime_role),
                ledger_numbers(admin_dsn, app_database),
            )

        first = _snapshot()

        # second (deliberate) re-application: platform migrations through
        # `apply-platform-migration` -- each file's
        # own object is manually drifted immediately beforehand,
        # so this comparison proves apply-platform-migration actually RESTORES each one, not
        # merely that a bare re-apply happens to be a no-op. Per-
        # application upgrades stay on the operational `upgrade-
        # applications` path (bulk, no `--script`) -- everything is
        # already recorded by now, so this run's own output must show
        # nothing newly applied.
        _drift_platform_objects_before_reapplication(
            admin_dsn, provision_dsn, registry_schema, api_role, controlplane_role, auditreader_role, runtime_role)
        for name in _REAPPLY_PLATFORM_MIGRATION_FILENAMES:
            if name == "0007_platform_declarations.sql":
                r = _run_ops(ns, "apply-platform-migration", name, "--lock-timeout", _TEST_LOCK_TIMEOUT,
                            "--api-role", api_role, "--controlplane-role", controlplane_role)
            else:
                r = _run_ops(ns, "apply-platform-migration", name, "--lock-timeout", _TEST_LOCK_TIMEOUT)
            assert r.returncode == 0, f"{name}: {r.stdout + r.stderr}"
        r_upgrade = _run_ops(ns, "upgrade-applications", "--application", _REAPPLY_TEST_APP_ID,
                             "--lock-timeout", _TEST_LOCK_TIMEOUT)
        assert r_upgrade.returncode == 0, r_upgrade.stdout + r_upgrade.stderr
        assert "0 succeeded" in r_upgrade.stdout, r_upgrade.stdout

        second = _snapshot()
        assert first == second
    finally:
        _sweep_prefix(admin_dsn, prefix)


def _acl_has_public_grantee(acl: "list | None") -> bool:
    """`aclitem` text form is `grantee=privileges/grantor`; an EMPTY
    grantee (the literal starts with `=`) is PostgreSQL's own encoding
    for the pseudo-role PUBLIC -- never a real role name to look up."""
    return any(str(item).startswith("=") for item in (acl or []))


def test_0007_reapplication_resets_a_manually_drifted_public_grant(platform: types.SimpleNamespace) -> None:
    """A manually added PUBLIC grant on `platform_declarations` (drift
    outside this migration's own control) does not survive a reapplication
    of 0007 -- its `REVOKE ALL ... FROM PUBLIC` runs every time, not only
    on first creation. This is the property `_table_acl` in the combined
    snapshot above exists to protect: an exit-code-only check would miss a
    GRANT/REVOKE statement quietly dropped from the file, since granting
    and revoking are themselves idempotent and never fail."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("GRANT SELECT ON {table} TO PUBLIC").format(
                table=sql.Identifier(platform.registry_schema, "platform_declarations")))
    finally:
        conn.close()
    assert _acl_has_public_grantee(
        _table_acl(platform.provision_dsn, platform.registry_schema, "platform_declarations"))

    result = _run_psql(platform.provision_dsn, platform.migration_paths["0007_platform_declarations.sql"],
                       {"api_role": platform.api_role, "controlplane_role": platform.controlplane_role})
    assert result.returncode == 0, result.stdout + result.stderr

    assert not _acl_has_public_grantee(
        _table_acl(platform.provision_dsn, platform.registry_schema, "platform_declarations"))


def test_0012_reapplication_resets_a_manually_drifted_public_execute_grant(
    platform: types.SimpleNamespace,
) -> None:
    """Same property as above, for `begin_provision_application`'s own
    `proacl` -- PostgreSQL grants EXECUTE to PUBLIC by default on function
    creation, so 0012's own explicit `REVOKE ALL ... FROM PUBLIC` (after
    `CREATE OR REPLACE FUNCTION`, which does not reset an existing
    function's ACL) is what keeps that closed on every reapplication."""
    function_signature = f"{platform.registry_schema}.begin_provision_application(text, text, text)"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {fn} TO PUBLIC").format(fn=sql.SQL(function_signature)))
    finally:
        conn.close()
    _, acl = _function_def_and_acl(platform.provision_dsn, platform.registry_schema, "begin_provision_application")
    assert _acl_has_public_grantee(acl)

    result = _run_psql(platform.provision_dsn, platform.migration_paths["0012_role_connection_limits.sql"])
    assert result.returncode == 0, result.stdout + result.stderr

    _, acl = _function_def_and_acl(platform.provision_dsn, platform.registry_schema, "begin_provision_application")
    assert not _acl_has_public_grantee(acl)


def test_0007_reapplication_resets_a_manually_drifted_controlplane_role_setting(
    platform: types.SimpleNamespace,
) -> None:
    """Same property as `test_migration_0007_ddl.py`'s own api_role
    companion, for `controlplane_role` -- a role-level setting changed by
    hand (never through `ops`) is reset back to 0007's own seed value on
    reapplication."""
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {platform.controlplane_role} SET statement_timeout = '9999ms'")
    finally:
        admin.close()
    drifted = _role_setting(platform.provision_dsn, platform.controlplane_role)
    assert drifted == ["statement_timeout=9999ms", "idle_in_transaction_session_timeout=5000ms"]

    result = _run_psql(platform.provision_dsn, platform.migration_paths["0007_platform_declarations.sql"],
                       {"api_role": platform.api_role, "controlplane_role": platform.controlplane_role})
    assert result.returncode == 0, result.stdout + result.stderr

    reset = _role_setting(platform.provision_dsn, platform.controlplane_role)
    assert reset == ["statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms"]


def test_0012_reapplication_resets_a_manually_drifted_function_body(platform: types.SimpleNamespace) -> None:
    """A hand-edited `begin_provision_application` body (drift outside
    this migration's own control, e.g. an operator patching it live to
    chase an incident) does not survive a reapplication of 0012 --
    `CREATE OR REPLACE FUNCTION` always rewrites the body back to this
    file's own definition. This is the property `_function_def_and_acl`
    in the combined snapshot above exists to protect: a hand edit that
    left the function's own signature and ACL untouched would be invisible
    to every other check."""
    marker = "NAMEDATALEN"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION {fn}(p_app_id text, p_runtime_password text, "
                    "p_developer_password text) RETURNS TABLE(database_name text, runtime_role text, "
                    "developer_role text) LANGUAGE plpgsql AS $fn$ BEGIN RAISE EXCEPTION 'drifted stub'; END; $fn$"
                ).format(fn=sql.Identifier(platform.registry_schema, "begin_provision_application")))
    finally:
        conn.close()
    drifted_def, _ = _function_def_and_acl(
        platform.provision_dsn, platform.registry_schema, "begin_provision_application")
    assert marker not in drifted_def
    assert "drifted stub" in drifted_def

    result = _run_psql(platform.provision_dsn, platform.migration_paths["0012_role_connection_limits.sql"])
    assert result.returncode == 0, result.stdout + result.stderr

    reset_def, _ = _function_def_and_acl(
        platform.provision_dsn, platform.registry_schema, "begin_provision_application")
    assert marker in reset_def
    assert "drifted stub" not in reset_def


# ===========================================================================
# 42/43: declare-surfaces/declare-process-ceilings, applied twice through
# the CLI
# ===========================================================================


def test_declare_surfaces_reapplication_is_idempotent(platform: types.SimpleNamespace) -> None:
    """完了条件42: `declare-surfaces` を同じ値で 2 回適用し、2 回目の終了
    コードが 0、宣言の値 (`updated_at` を含まない列だけを読む) の差分が 0
    であることを確かめる。"""
    url = "https://data.mitatedb-migration-reapply.example.invalid/v1"
    first_run = _run_ops(platform, "declare-surfaces", "--data-base-url", url)
    assert first_run.returncode == 0, first_run.stdout + first_run.stderr
    first_value = _read_declaration(platform, "surfaces")
    second_run = _run_ops(platform, "declare-surfaces", "--data-base-url", url)
    assert second_run.returncode == 0, second_run.stdout + second_run.stderr
    second_value = _read_declaration(platform, "surfaces")
    assert first_value == second_value == {"data": {"base_url": url}}


def test_declare_process_ceilings_reapplication_is_idempotent(platform: types.SimpleNamespace) -> None:
    """完了条件43: `declare-process-ceilings` を同じ値で 2 回適用し、
    同じ条件を確かめる。"""
    first_run = _run_ops(platform, "declare-process-ceilings", "--data", "4", "--control", "2")
    assert first_run.returncode == 0, first_run.stdout + first_run.stderr
    first_value = _read_declaration(platform, "process_ceilings")
    second_run = _run_ops(platform, "declare-process-ceilings", "--data", "4", "--control", "2")
    assert second_run.returncode == 0, second_run.stdout + second_run.stderr
    second_value = _read_declaration(platform, "process_ceilings")
    assert first_value == second_value == {"data": 4, "control": 2}


# ===========================================================================
# 44: per-application upgrade, applied twice through `upgrade-applications`
# ===========================================================================


def test_per_application_upgrade_reapplication_is_idempotent(platform: types.SimpleNamespace) -> None:
    """完了条件44: 1 件だけ台帳から欠けさせた application に対して
    `upgrade-applications` を 2 回適用する。1 回目は欠けた番号を適用し
    (`1 succeeded` を含む)、2 回目は終了コード 0・適用件数 0
    (`0 succeeded` を含む)・台帳の差分 0 であることを確かめる。"""
    app = provision_app(platform, "reapp1")
    try:
        delete_ledger_row(platform.admin_dsn, app.database, 8)
        first_run = _run_ops(
            platform, "upgrade-applications", "--application", "reapp1", "--lock-timeout", _TEST_LOCK_TIMEOUT)
        assert first_run.returncode == 0, first_run.stdout + first_run.stderr
        assert "1 succeeded" in first_run.stdout
        ledger_after_first = ledger_numbers(platform.admin_dsn, app.database)
        assert ledger_after_first == frozenset({6, 8, 9, 10})

        second_run = _run_ops(
            platform, "upgrade-applications", "--application", "reapp1", "--lock-timeout", _TEST_LOCK_TIMEOUT)
        assert second_run.returncode == 0, second_run.stdout + second_run.stderr
        assert "0 succeeded" in second_run.stdout
        ledger_after_second = ledger_numbers(platform.admin_dsn, app.database)
        assert ledger_after_first == ledger_after_second
    finally:
        deprovision_app(platform, "reapp1")


# ===========================================================================
# 45b: the migration files' own `\\set ON_ERROR_STOP on` (static)
# ===========================================================================


def test_platform_migrations_declare_on_error_stop_in_the_file() -> None:
    """Every file `apply-platform-migration` accepts
    (`ops._PLATFORM_MIGRATION_FILENAMES`) carries its own `\\set
    ON_ERROR_STOP on` -- a real `apply-platform-migration` invocation
    never puts this layer on the psql argv itself, so the file itself is
    the only guarantee. Derived from the pinned constant (never a
    hand-written list) so a future accepted file is covered without an
    edit here."""
    assert len(ops._PLATFORM_MIGRATION_FILENAMES) == 5
    for name in ops._PLATFORM_MIGRATION_FILENAMES:
        text = (MIGRATIONS_DIR / name).read_text()
        assert "\\set ON_ERROR_STOP on" in text, name


# ===========================================================================
# 45c: a dependency-missing apply (0011 without 0007) fails by exit code
# ===========================================================================


@pytest.fixture()
def bare_platform_without_0007(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    """`0001`+`0002` only -- `0011`'s own dependency (0007's table) is
    deliberately absent."""
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbmreapbare{secrets.token_hex(4)}"
    provision_password = secrets.token_urlsafe(24)
    rewritten_dir = tmp_path_factory.mktemp("mitatedb_migration_reapply_bare_" + prefix)
    rewritten: dict[str, Path] = {}
    for name in ("0001_bootstrap_platform.sql", "0002_registry_and_functions.sql", "0011_process_ceilings.sql"):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out
    try:
        _run_psql_ok(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(
            admin_dsn, user=f"{prefix}svc_provision", password=provision_password, dbname=f"{prefix}_platform")
        _run_psql_ok(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise
    try:
        yield types.SimpleNamespace(admin_dsn=admin_dsn, provision_dsn=provision_dsn, prefix=prefix,
                                    migration_paths=rewritten)
    finally:
        _sweep_prefix(admin_dsn, prefix)


def test_0011_fails_by_exit_code_when_its_dependency_0007_is_missing(
    bare_platform_without_0007: types.SimpleNamespace,
) -> None:
    """完了条件45c: 0011 は自分自身の `\\set ON_ERROR_STOP on` (45b) だけに
    頼る (運用の適用例が argv にこの層を持たないため、45b のテストと同じ
    前提)。依存先 (0007 のテーブル) が無い状態で適用すると、
    `DROP CONSTRAINT` が失敗し、`ON_ERROR_STOP` がスクリプト全体を
    停止させ、終了コードが非 0 になる。argv に `ON_ERROR_STOP` を渡さない
    (`_run_psql` は使わない) ことで、ファイル側だけが保護層であることを
    確かめる。"""
    command = ["psql", bare_platform_without_0007.provision_dsn, "-f",
              str(bare_platform_without_0007.migration_paths["0011_process_ceilings.sql"])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr


# ===========================================================================
# 45a'/W1-C1/W1-C2/W7-C1/W7-C2: the two psql-invocation helpers' own argv
# and `--lock-timeout` handling -- in-process, monkeypatching
# `subprocess.run` (the property under test does not depend on which SQL
# actually runs).
# ===========================================================================

_SENTINEL_DSN = "postgresql://sentinel_user_c3f1:sentinel_pw_7a2e@sentinel-host-b91d.invalid:6543/sentinel_db_44de"
_FAKE_PSQL_VERSION_STDOUT = "psql (PostgreSQL) 16.14 (Homebrew)\n"


def _clear_ambient_pg_connection_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)


def _spy_on_the_main_psql_call(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patches `ops.subprocess.run` so the version-gate call still
    succeeds, and captures the SECOND (main) call's own `cmd`/`env`."""
    captured: dict = {}

    def _fake_run(cmd, **kwargs):  # noqa: ANN001 -- matches subprocess.run's own loose signature
        if cmd[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=_FAKE_PSQL_VERSION_STDOUT, stderr="")
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", _fake_run)
    return captured


def test_run_upgrade_script_argv_carries_on_error_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件45a' (1/2)。"""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    captured = _spy_on_the_main_psql_call(monkeypatch)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1", _TEST_LOCK_TIMEOUT)
    assert "ON_ERROR_STOP=1" in captured["cmd"]


def test_run_deprovision_script_argv_carries_on_error_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """完了条件45a' (2/2)。"""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    script = tmp_path / "0004_deprovision_application.sql"
    script.write_text("-- empty\n")
    monkeypatch.setattr(ops, "_migrations_dir", lambda: tmp_path)
    captured = _spy_on_the_main_psql_call(monkeypatch)
    ops._run_deprovision_script(_SENTINEL_DSN, "app1", _TEST_LOCK_TIMEOUT)
    assert "ON_ERROR_STOP=1" in captured["cmd"]


def test_run_upgrade_script_passes_lock_timeout_via_pgoptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """完了条件W1-C1。"""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    captured = _spy_on_the_main_psql_call(monkeypatch)
    ops._run_upgrade_script(_SENTINEL_DSN, Path("/nonexistent/0099_does_not_matter.sql"), "app1", "42s")
    assert captured["env"].get("PGOPTIONS") == "-c lock_timeout=42s"


def test_run_deprovision_script_passes_lock_timeout_via_pgoptions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """完了条件W1-C2。"""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    script = tmp_path / "0004_deprovision_application.sql"
    script.write_text("-- empty\n")
    monkeypatch.setattr(ops, "_migrations_dir", lambda: tmp_path)
    captured = _spy_on_the_main_psql_call(monkeypatch)
    ops._run_deprovision_script(_SENTINEL_DSN, "app1", "42s")
    assert captured["env"].get("PGOPTIONS") == "-c lock_timeout=42s"


def test_run_upgrade_script_keeps_the_dsns_own_pgoptions_alongside_lock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSN 自身の `options` (`PGOPTIONS` に既に載る値) と
    `lock_timeout` の両方が effect を持つよう連結され、上書きされない。"""
    _clear_ambient_pg_connection_env_vars(monkeypatch)
    dsn_with_options = make_conninfo(_SENTINEL_DSN, options="-c search_path=foo")
    captured = _spy_on_the_main_psql_call(monkeypatch)
    ops._run_upgrade_script(dsn_with_options, Path("/nonexistent/0099_does_not_matter.sql"), "app1", "42s")
    assert captured["env"].get("PGOPTIONS") == "-c search_path=foo -c lock_timeout=42s"


def test_upgrade_applications_without_lock_timeout_is_a_usage_error(platform: types.SimpleNamespace) -> None:
    """完了条件W7-C1: `--lock-timeout` を省略すると argparse が使用法
    エラーで拒否する (既定値が無いことを実行で確かめる) -- 拒否は引数解析の
    時点で起きるので、psql は起動しようがない。"""
    result = _run_ops(platform, "upgrade-applications")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--lock-timeout" in result.stderr


def test_deprovision_without_lock_timeout_is_a_usage_error(platform: types.SimpleNamespace) -> None:
    """完了条件W7-C2: 同じく `deprovision` 側。"""
    result = _run_ops(platform, "deprovision", "does-not-matter")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--lock-timeout" in result.stderr


# ===========================================================================
# --lock-timeout の値の検証
# ===========================================================================


def test_upgrade_applications_rejects_a_malformed_lock_timeout_value(platform: types.SimpleNamespace) -> None:
    result = _run_ops(platform, "upgrade-applications", "--lock-timeout", "0")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--lock-timeout" in result.stderr


def test_deprovision_rejects_a_malformed_lock_timeout_value(platform: types.SimpleNamespace) -> None:
    result = _run_ops(platform, "deprovision", "does_not_exist_yet", "--lock-timeout", "not-a-value")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--lock-timeout" in result.stderr


def test_lock_timeout_rejection_message_never_echoes_the_rejected_value(
    platform: types.SimpleNamespace,
) -> None:
    """The rejected `--lock-timeout` value itself must never appear in the
    error output -- only the fixed usage message."""
    sentinel_value = "sentinel-lock-timeout-b7e2"
    result = _run_ops(platform, "deprovision", "does_not_exist_yet", "--lock-timeout", sentinel_value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert sentinel_value not in result.stdout
    assert sentinel_value not in result.stderr


def test_deprovision_accepts_a_well_formed_lock_timeout_value(platform: types.SimpleNamespace) -> None:
    """検証を通過することの非空振り companion: 検証さえ通れば、次の関門
    (確認フレーズ) まで進む -- 拒否の理由が変わることで区別する。"""
    app = provision_app(platform, "goodlock1")
    try:
        result = _run_ops(platform, "deprovision", "goodlock1", "--lock-timeout", "45s")
        assert result.returncode == 2, result.stdout + result.stderr
        assert "DESTRUCTIVE_CONFIRMATION_REQUIRED" in result.stderr
        assert "--lock-timeout" not in result.stderr
    finally:
        deprovision_app(platform, "goodlock1")
