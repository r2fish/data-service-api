"""`python -m mitatedb_api.ops {set-platform-timeouts,declare-surfaces,
declare-coalescing-window,show-declarations}` (Q4 phase, design docs/design/
Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work order docs/work-orders/
WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-2 変更対象 C) -- direct,
real-subprocess tests, mirroring `test_ops.py`'s own established
convention for this module (placement confirmed by supervisor ruling
2026-09-05: declaration-system subcommands get their own file, separate
from `test_ops_upgrade.py`, which a later WP owns).

Uses `control_plane_harness.py`'s shared throwaway-platform fixture --
already applies migration `0007_platform_declarations.sql` and seeds a
`surfaces` row (both `data`/`control`), the SAME fixture `test_ops.py`/
`test_control_main.py` use.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform, set_role_timeouts  # noqa: F401 (fixture)

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _run_ops(control_platform, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["MITATEDB_PROVISION_DSN"] = control_platform.provision_dsn
    env["MITATEDB_PLATFORM_SCHEMA"] = control_platform.registry_schema
    # Defensive: this subprocess must observe the SAME removed-env-var
    # rejection any other caller does, never a silently-inherited
    # leftover from the parent `os.environ` this dict is copied from.
    for removed in (
        "MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL",
        "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS",
    ):
        env.pop(removed, None)
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args],
        capture_output=True, text=True, env=env,
    )


def _read_declaration(control_platform, key: str):
    conn = psycopg.connect(control_platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT value FROM {table} WHERE key = %s").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
                [key],
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _role_setting(control_platform, role: str) -> "list[str] | None":
    conn = psycopg.connect(control_platform.provision_dsn)
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


@pytest.fixture(autouse=True)
def _restore_defaults(control_platform):
    """Every test in this module shares ONE throwaway platform
    (`control_platform` is module-scoped) -- restores the shipped
    5000ms/5000ms role setting and the fixture's own original `surfaces`/
    window declarations after each test, so tests do not leak state into
    each other regardless of order."""
    yield
    set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
    set_role_timeouts(control_platform.admin_dsn, control_platform.controlplane_role, statement_ms=5000, idle_ms=5000)
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET value = %s WHERE key = 'surfaces'").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
                [
                    '{"data":{"base_url":"https://data.mitatedb-control-platform.example.invalid/v1"},'
                    '"control":{"base_url":"https://control.mitatedb-control-platform.example.invalid/control/v1"}}'
                ],
            )
            cur.execute(
                sql.SQL("UPDATE {table} SET value = to_jsonb(60000) WHERE key = 'audit_coalescing_window_ms'").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {table} (key, value) VALUES ('audit_writer_roles', to_jsonb(ARRAY[%s, %s])) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                ).format(table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
                [control_platform.api_role, control_platform.controlplane_role],
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# set-platform-timeouts
# ---------------------------------------------------------------------------


def test_set_platform_timeouts_updates_both_roles_together(control_platform) -> None:
    result = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "3000", "--idle-ms", "4000")
    assert result.returncode == 0, result.stderr
    assert _role_setting(control_platform, control_platform.api_role) == [
        "statement_timeout=3000ms", "idle_in_transaction_session_timeout=4000ms",
    ]
    assert _role_setting(control_platform, control_platform.controlplane_role) == [
        "statement_timeout=3000ms", "idle_in_transaction_session_timeout=4000ms",
    ]


def test_set_platform_timeouts_rejects_zero_statement_ms(control_platform) -> None:
    result = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "0", "--idle-ms", "4000")
    assert result.returncode == 2
    assert "positive" in result.stderr


def test_set_platform_timeouts_rejects_negative_idle_ms(control_platform) -> None:
    result = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "3000", "--idle-ms", "-1")
    assert result.returncode == 2
    assert "positive" in result.stderr


def test_set_platform_timeouts_targets_come_from_the_declared_row_not_a_hardcoded_pair(control_platform) -> None:
    """WP-1/WP-2 completion condition 22 (D-2(h) 4): the target role set
    comes from the `audit_writer_roles` row itself, never a naming-
    convention derivation or a hardcoded 2-role pair. Narrows the
    declaration to ONLY `api_role` and observes that `set-platform-
    timeouts` changes ONLY that role -- `controlplane_role` (excluded
    from the declared set) must be left untouched."""
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET value = to_jsonb(ARRAY[%s]) WHERE key = 'audit_writer_roles'").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
                [control_platform.api_role],
            )
    finally:
        conn.close()
    result = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "7000", "--idle-ms", "8000")
    assert result.returncode == 0, result.stderr
    assert _role_setting(control_platform, control_platform.api_role) == [
        "statement_timeout=7000ms", "idle_in_transaction_session_timeout=8000ms",
    ]
    # controlplane_role was NOT in the declared set -- untouched, still at
    # the shipped default this module's own tests all start from.
    assert _role_setting(control_platform, control_platform.controlplane_role) == [
        "statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms",
    ]


def test_set_platform_timeouts_dies_when_audit_writer_roles_row_is_absent(control_platform) -> None:
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE key = 'audit_writer_roles'").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")))
        result = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "1000", "--idle-ms", "1000")
        assert result.returncode == 2
        assert "audit_writer_roles" in result.stderr
    finally:
        conn.close()


def test_set_platform_timeouts_has_no_per_role_flag(control_platform) -> None:
    """Design §3.10: "role 別の指定は設けない" -- there is no argparse
    flag naming a specific role; the single `--statement-ms`/`--idle-ms`
    pair is this subcommand's ENTIRE surface."""
    result = _run_ops(control_platform, "set-platform-timeouts", "--help")
    assert result.returncode == 0
    assert "--statement-ms" in result.stdout
    assert "--idle-ms" in result.stdout
    assert "--role" not in result.stdout


# ---------------------------------------------------------------------------
# declare-surfaces
# ---------------------------------------------------------------------------


def test_declare_surfaces_writes_data_and_control(control_platform) -> None:
    result = _run_ops(
        control_platform, "declare-surfaces",
        "--data-base-url", "https://data.example.invalid/v1",
        "--control-base-url", "https://control.example.invalid/control/v1",
    )
    assert result.returncode == 0, result.stderr
    value = _read_declaration(control_platform, "surfaces")
    assert value == {
        "data": {"base_url": "https://data.example.invalid/v1"},
        "control": {"base_url": "https://control.example.invalid/control/v1"},
    }


def test_declare_surfaces_no_control_removes_the_control_key(control_platform) -> None:
    result = _run_ops(
        control_platform, "declare-surfaces", "--data-base-url", "https://data.example.invalid/v1", "--no-control",
    )
    assert result.returncode == 0, result.stderr
    value = _read_declaration(control_platform, "surfaces")
    assert value == {"data": {"base_url": "https://data.example.invalid/v1"}}


def test_declare_surfaces_control_base_url_is_optional(control_platform) -> None:
    """Supervisor ruling correction 2026-09-05 (`{scratchpad}/
    q4-f3c-and-amendments.md`): omitting BOTH `--control-base-url` and
    `--no-control` is now valid -- it declares no control row (the SAME
    effect `--no-control` produces explicitly). The old ruling ("one is
    always required") is superseded; this test replaces the one that
    asserted omission was a usage error."""
    result = _run_ops(control_platform, "declare-surfaces", "--data-base-url", "https://data.example.invalid/v1")
    assert result.returncode == 0, result.stderr
    value = _read_declaration(control_platform, "surfaces")
    assert value == {"data": {"base_url": "https://data.example.invalid/v1"}}


def test_declare_surfaces_no_control_is_equivalent_to_omission(control_platform) -> None:
    omitted = _run_ops(control_platform, "declare-surfaces", "--data-base-url", "https://data.example.invalid/v1")
    assert omitted.returncode == 0, omitted.stderr
    omitted_value = _read_declaration(control_platform, "surfaces")

    explicit = _run_ops(
        control_platform, "declare-surfaces", "--data-base-url", "https://data.example.invalid/v1", "--no-control")
    assert explicit.returncode == 0, explicit.stderr
    explicit_value = _read_declaration(control_platform, "surfaces")

    assert omitted_value == explicit_value == {"data": {"base_url": "https://data.example.invalid/v1"}}


def test_declare_surfaces_rejects_both_control_base_url_and_no_control(control_platform) -> None:
    """Passing both is a usage error (exit 2) -- neither flag is
    required, but they remain mutually exclusive."""
    result_both = _run_ops(
        control_platform, "declare-surfaces", "--data-base-url", "https://data.example.invalid/v1",
        "--control-base-url", "https://control.example.invalid/control/v1", "--no-control",
    )
    assert result_both.returncode == 2


@pytest.mark.parametrize("bad_url", ["/v1", "https://h.example.invalid/v2", "https://h.example.invalid/v1/"])
def test_declare_surfaces_rejects_malformed_data_url(control_platform, bad_url: str) -> None:
    result = _run_ops(control_platform, "declare-surfaces", "--data-base-url", bad_url, "--no-control")
    assert result.returncode == 2
    assert "MITATEDB_DATA_BASE_URL" not in result.stderr  # this is the ops path, not the removed env var's F-2
    assert "surfaces.data.base_url" in result.stderr


def test_declare_surfaces_does_not_write_on_validation_failure(control_platform) -> None:
    before = _read_declaration(control_platform, "surfaces")
    result = _run_ops(control_platform, "declare-surfaces", "--data-base-url", "not-a-url", "--no-control")
    assert result.returncode == 2
    assert _read_declaration(control_platform, "surfaces") == before


# ---------------------------------------------------------------------------
# declare-coalescing-window
# ---------------------------------------------------------------------------


def test_declare_coalescing_window_writes_the_value(control_platform) -> None:
    result = _run_ops(control_platform, "declare-coalescing-window", "--ms", "30000")
    assert result.returncode == 0, result.stderr
    assert _read_declaration(control_platform, "audit_coalescing_window_ms") == 30000


def test_declare_coalescing_window_accepts_zero() -> None:
    """Design D-2(d): 0 means "no coalescing", a valid value -- checked
    here at the validator level (already proven live above); this is the
    non-vacuity companion for "0 is accepted", not merely "negative is
    rejected"."""
    from mitatedb_api.platform_declarations import DEFAULT_SCHEMA, PEER_MODULE, validate_coalescing_window_value
    assert validate_coalescing_window_value(0, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE) == 0


def test_declare_coalescing_window_rejects_negative(control_platform) -> None:
    result = _run_ops(control_platform, "declare-coalescing-window", "--ms", "-1")
    assert result.returncode == 2
    assert "non-negative integer" in result.stderr


# ---------------------------------------------------------------------------
# show-declarations
# ---------------------------------------------------------------------------


def test_show_declarations_reports_rows_and_role_settings(control_platform) -> None:
    result = _run_ops(control_platform, "show-declarations")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    keys = {row["key"] for row in payload["platform_declarations"]}
    assert keys == {"surfaces", "audit_coalescing_window_ms", "audit_writer_roles"}
    assert control_platform.api_role in payload["role_settings"]
    assert control_platform.controlplane_role in payload["role_settings"]
    api_setting = payload["role_settings"][control_platform.api_role][0]
    assert api_setting["setconfig"] == ["statement_timeout=5000ms", "idle_in_transaction_session_timeout=5000ms"]


def test_show_declarations_reflects_a_real_set_platform_timeouts_change(control_platform) -> None:
    changed = _run_ops(control_platform, "set-platform-timeouts", "--statement-ms", "1111", "--idle-ms", "2222")
    assert changed.returncode == 0, changed.stderr
    result = _run_ops(control_platform, "show-declarations")
    payload = json.loads(result.stdout)
    api_setting = payload["role_settings"][control_platform.api_role][0]
    assert api_setting["setconfig"] == ["statement_timeout=1111ms", "idle_in_transaction_session_timeout=2222ms"]


def test_show_declarations_never_guesses_role_names_when_the_row_is_absent(control_platform) -> None:
    """N-6 (monitor ruling 2026-09-05, delta review §4): rulings-q4-
    writer-roles.md D-2(h) point 3 ("role 名の導出規則はコードから撤去
    する") applies to this DIAGNOSTIC command exactly as much as to a
    fail-fast one -- a deployment whose real writer roles are NOT the
    production seed names (`mitatedbsvc_api`/`mitatedbsvc_controlplane`)
    must never have `show-declarations` silently print settings for
    roles that do not exist on it. Deletes the `audit_writer_roles` row
    (restored in `finally`, so this file's shared `control_platform`
    fixture is not left corrupted for a later test) and asserts
    `role_settings` reports the absence as a message, containing NEITHER
    production seed role name, rather than falling back to guessing them."""
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE key = 'audit_writer_roles'").format(
                    table=sql.Identifier(control_platform.registry_schema, "platform_declarations")))
        try:
            result = _run_ops(control_platform, "show-declarations")
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            assert payload["role_settings"] == (
                f"(no audit_writer_roles row -- apply migration 0007 with this deployment's writer role names)"
            )
            assert "mitatedbsvc_api" not in payload["role_settings"]
            assert "mitatedbsvc_controlplane" not in payload["role_settings"]
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('audit_writer_roles', %s::jsonb)").format(
                        table=sql.Identifier(control_platform.registry_schema, "platform_declarations")),
                    [json.dumps([control_platform.api_role, control_platform.controlplane_role])],
                )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# All four subcommands: existing exit-code conventions (常設規律,
# completion condition 11) -- `_die` = 2, provision DSN missing = 2 (via
# `_require_env`/`_die`), never a bare traceback.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args", [
    ["set-platform-timeouts", "--statement-ms", "1000", "--idle-ms", "1000"],
    ["declare-surfaces", "--data-base-url", "https://h.example.invalid/v1", "--no-control"],
    ["declare-coalescing-window", "--ms", "1000"],
    ["show-declarations"],
])
def test_all_four_subcommands_require_provision_dsn(control_platform, args: list[str]) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env.pop("MITATEDB_PROVISION_DSN", None)
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 2
    assert "MITATEDB_PROVISION_DSN is required" in result.stderr
