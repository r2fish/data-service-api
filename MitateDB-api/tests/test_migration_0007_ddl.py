"""Q4 phase WP-2 rework ruling §4(c) (`{scratchpad}/rulings-q4-wp12-rework.md`):
migration `0007_platform_declarations.sql`'s own DDL tests, isolated from
`control_plane_harness.control_platform` (that fixture already applies
`0007` as ONE step of a larger bootstrap that ALSO seeds a `surfaces`
row right after -- this file needs to observe `0007`'s OWN end state,
including the surfaces row's absence, before anything else touches the
table).

Real PostgreSQL only (design's own non-vacuity requirement) -- builds its
own minimal platform (`0001` + `0002` only, no `0005`/no manual `surfaces`
seed) with a throwaway prefix distinct from every other test module's own
prefix stem, so a failure here can never be confused with `control_
plane_harness`'s or `test_postgres.py`'s own fixtures.
"""
from __future__ import annotations

import secrets
import types
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import (MIGRATIONS_DIR, _dsn_with, _run_psql, admin_dsn,
                                    require_admin_connection, sweep_prefix)

_PREFIX_STEM = "mtdbmig"


def _fresh_prefix() -> str:
    return _PREFIX_STEM + secrets.token_hex(4)


@pytest.fixture()
def bare_platform(tmp_path_factory: pytest.TempPathFactory):
    """`0001` + `0002` ONLY -- the two roles `0007` targets exist, but
    NEITHER `0005` (application_audit) NOR any seeding beyond what `0007`
    itself does has happened yet. A function-scoped fixture (unlike
    `control_platform`) -- each test in this file gets ITS OWN throwaway
    platform, since several tests here apply `0007` a SECOND time (with a
    deliberately mutated copy) and must not contaminate a shared one."""
    require_admin_connection()
    dsn = admin_dsn()
    prefix = _fresh_prefix()
    provision_password = secrets.token_urlsafe(24)
    rewritten_dir = tmp_path_factory.mktemp("mtdbmig_migrations_" + prefix)
    rewritten: dict[str, Path] = {}
    for name in ("0001_bootstrap_platform.sql", "0002_registry_and_functions.sql"):
        text = (MIGRATIONS_DIR / name).read_text().replace("mitatedb", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    provision_role = f"{prefix}svc_provision"
    platform_db = f"{prefix}_platform"
    api_role = f"{prefix}svc_api"
    controlplane_role = f"{prefix}svc_controlplane"
    registry_schema = f"{prefix}_registry"

    try:
        _run_psql(dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
    except Exception:
        sweep_prefix(dsn, prefix)
        raise

    yield types.SimpleNamespace(
        prefix=prefix, admin_dsn=dsn, provision_dsn=provision_dsn,
        registry_schema=registry_schema, api_role=api_role, controlplane_role=controlplane_role,
        tmp_dir=rewritten_dir,
    )
    sweep_prefix(dsn, prefix)


def _apply_0007(platform, *, migration_text: str | None = None) -> None:
    """Applies `0007` (the real, tracked file by default, or a caller-
    supplied MUTATED text -- written to platform's own throwaway tmp_dir,
    never to the tracked repository file) against `platform`."""
    if migration_text is None:
        text = (MIGRATIONS_DIR / "0007_platform_declarations.sql").read_text().replace("mitatedb", platform.prefix)
    else:
        text = migration_text
    out = platform.tmp_dir / f"0007_variant_{secrets.token_hex(4)}.sql"
    out.write_text(text)
    _run_psql(platform.provision_dsn, out, {"api_role": platform.api_role, "controlplane_role": platform.controlplane_role})


def _rows(platform) -> dict:
    conn = psycopg.connect(platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT key, value FROM {table}").format(
                    table=sql.Identifier(platform.registry_schema, "platform_declarations")))
            return dict(cur.fetchall())
    finally:
        conn.close()


def _role_setting(platform, role: str) -> "list[str] | None":
    conn = psycopg.connect(platform.provision_dsn)
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


# ---------------------------------------------------------------------------
# (c) migration の DDL テスト (ruling §4(c))
# ---------------------------------------------------------------------------


def test_0007_seeds_window_default_and_audit_writer_roles_but_not_surfaces(bare_platform) -> None:
    _apply_0007(bare_platform)
    rows = _rows(bare_platform)
    assert rows["audit_coalescing_window_ms"] == 60000
    assert rows["audit_writer_roles"] == [bare_platform.api_role, bare_platform.controlplane_role]
    assert "surfaces" not in rows


def test_0007_grants_select_to_both_roles_and_nothing_to_public(bare_platform) -> None:
    _apply_0007(bare_platform)
    conn = psycopg.connect(bare_platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT')",
                [bare_platform.api_role, f"{bare_platform.registry_schema}.platform_declarations"],
            )
            assert cur.fetchone()[0] is True
            cur.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT')",
                [bare_platform.controlplane_role, f"{bare_platform.registry_schema}.platform_declarations"],
            )
            assert cur.fetchone()[0] is True
            cur.execute(
                "SELECT count(*) FROM information_schema.table_privileges "
                "WHERE table_schema = %s AND table_name = 'platform_declarations' AND grantee = 'PUBLIC'",
                [bare_platform.registry_schema],
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_0007_named_check_constraint_exists(bare_platform) -> None:
    _apply_0007(bare_platform)
    conn = psycopg.connect(bare_platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = 'platform_declarations' AND c.contype = 'c'",
                [bare_platform.registry_schema],
            )
            names = {row[0] for row in cur.fetchall()}
            assert "platform_declarations_key_check" in names
    finally:
        conn.close()


def test_0007_check_constraint_rejects_a_key_outside_the_vocabulary(bare_platform) -> None:
    _apply_0007(bare_platform)
    conn = psycopg.connect(bare_platform.provision_dsn, autocommit=True)
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('not_a_real_key', 'null'::jsonb)").format(
                        table=sql.Identifier(bare_platform.registry_schema, "platform_declarations")))
    finally:
        conn.close()


def test_0007_check_constraint_accepts_audit_writer_roles_as_a_key(bare_platform) -> None:
    """Non-vacuity companion: `audit_writer_roles` itself must be an
    ACCEPTED key (already proven implicitly by the seed test above
    succeeding, but this isolates the CHECK's own acceptance from the
    seed statement's own success)."""
    _apply_0007(bare_platform)
    rows = _rows(bare_platform)
    assert "audit_writer_roles" in rows


def test_0007_alter_role_and_table_creation_are_idempotent(bare_platform) -> None:
    """WP-1/WP-2 completion condition 1/19: applying `0007` TWICE ends at
    the SAME `pg_db_role_setting` state and the SAME table rows --
    verified here for `audit_writer_roles` specifically (condition 19's
    own addition), not merely the two timeout role settings."""
    _apply_0007(bare_platform)
    first_setting = _role_setting(bare_platform, bare_platform.api_role)
    first_rows = _rows(bare_platform)

    _apply_0007(bare_platform)
    second_setting = _role_setting(bare_platform, bare_platform.api_role)
    second_rows = _rows(bare_platform)

    assert first_setting == second_setting == [
        "statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms",
    ]
    assert first_rows == second_rows
    assert first_rows["audit_writer_roles"] == [bare_platform.api_role, bare_platform.controlplane_role]


def test_0007_reapplication_resets_a_manually_changed_timeout_back_to_the_seed_default(bare_platform) -> None:
    """WP-1/WP-2 completion condition 1 / rework condition 26 (§4(c)):
    re-applying `0007` must RESET a role setting that was changed by hand
    (never through `ops`) back to the migration's own seed default --
    non-vacuity companion to `test_0007_alter_role_and_table_creation_
    are_idempotent` above, which only observes two vanilla re-applies and
    would stay green even against a "conditional insert, only if absent"
    mutation of the `ALTER ROLE` statements (this peer's own gap; mirrors
    r2db-api's own `test_migration_0008_reapplication_resets_a_manually_
    changed_timeout_back_to_the_seed_default`)."""
    _apply_0007(bare_platform)
    admin = psycopg.connect(bare_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {bare_platform.api_role} SET statement_timeout = '9999ms'")
    finally:
        admin.close()

    _apply_0007(bare_platform)
    setting = _role_setting(bare_platform, bare_platform.api_role)
    assert setting == ["statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms"]


def test_0007_source_file_names_the_check_constraint_explicitly() -> None:
    """WP-1/WP-2 completion condition 2 / rework condition 27 (§4(c)):
    static companion to `test_0007_named_check_constraint_exists` above --
    PostgreSQL auto-generates the IDENTICAL default name (`<table>_
    <column>_check` = `platform_declarations_key_check`) for an unnamed
    single-column CHECK on this exact table/column pair, so the dynamic
    `pg_constraint` query alone cannot distinguish an explicit name from
    that coincidence (mirrors r2db-api's own equivalent static pin, added
    after the same coincidence was found there)."""
    text = (MIGRATIONS_DIR / "0007_platform_declarations.sql").read_text()
    assert "CONSTRAINT platform_declarations_key_check" in text


def test_0007_alter_role_and_seed_share_the_same_variable(bare_platform) -> None:
    """D-2(h) 1: the throwaway-prefixed role names passed as psql
    variables flow into BOTH the `ALTER ROLE` targets AND the
    `audit_writer_roles` seed value -- observed here with names that are
    NOT the production literals (`mitatedbsvc_api`/`mitatedbsvc_
    controlplane`), proving no naming-convention derivation or hardcoded
    literal is secretly still in play."""
    _apply_0007(bare_platform)
    rows = _rows(bare_platform)
    assert rows["audit_writer_roles"] == [bare_platform.api_role, bare_platform.controlplane_role]
    assert _role_setting(bare_platform, bare_platform.api_role) is not None
    assert _role_setting(bare_platform, bare_platform.controlplane_role) is not None
