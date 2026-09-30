"""The refusal-window counter (migration `0016_denial_window_counter.sql`):
the table `r2dbsvc_registry.denial_window_counter`, the SECURITY DEFINER
function `denial_window_record` that is the only way the data plane reaches
it, `PostgresApplicationAuditSink.record_denial`, the `audit_query` UNION
branch that returns a closed window's summary event, and the startup /
`verify-declarations` check (F-21) that names each way the function can
fail to be safe.

Runs against a real PostgreSQL (like every other platform-migration test in
this directory) through `test_credential_persistence.py`'s own `platform`
fixture, which applies every platform migration under a throwaway prefix.
"""
from __future__ import annotations

import secrets
import threading
import time
import types
from datetime import timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from starlette.testclient import TestClient

from test_credential_persistence import (  # noqa: F401 -- imported for fixture re-export
    MIGRATIONS_DIR,
    _dsn_with,
    _main_env,
    _run_psql,
    main_module,
    platform,
    provisioned_app,
)

import r2db_api.ops as ops
import r2db_api.platform_declarations as platform_declarations
from r2db_api.auth import CredentialStore
from r2db_api.credential_store import PostgresApplicationAuditSink, PostgresAuditQueryStore
from r2db_api.errors import FoundationError
from r2db_api.platform_declarations import PlatformDeclarationError
from r2db_api.service import DataService

_SIGNATURE = "denial_window_record(integer, text, timestamptz, text, text, text, text, text, text, text, text, text)"
_MIGRATION = "0016_denial_window_counter.sql"
_HOUR_MS = 3_600_000


def _platform_dsn(platform: types.SimpleNamespace, *, user: str | None = None, password: str | None = None) -> str:
    return _dsn_with(platform.admin_dsn, dbname=platform.platform_db, **({"user": user, "password": password} if user else {}))


def _fn(platform: types.SimpleNamespace) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(platform.schema), sql.SQL(_SIGNATURE))


def _table(platform: types.SimpleNamespace) -> sql.Identifier:
    return sql.Identifier(platform.schema, "denial_window_counter")


def _admin(platform: types.SimpleNamespace, statement: "sql.Composable | str", params: "list[Any] | None" = None) -> "list[tuple]":
    with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
        cur = conn.execute(statement, params)
        return cur.fetchall() if cur.description else []


def _auditreader_dsn(platform: types.SimpleNamespace) -> str:
    return _platform_dsn(platform, user=f"{platform.prefix}_auditreader", password=platform.auditreader_password)


def _fields(operation: str, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = dict(
        event_class="authorization_denial", request_id=f"req-{secrets.token_hex(4)}", application_id="app-window",
        actor_type="application_credential", actor_id="cred-window", role="runtime", operation=operation,
        target_kind="entity", reason_code="FORBIDDEN", target_id=None,
    )
    fields.update(overrides)
    return fields


def _new_operation() -> str:
    return "op_" + secrets.token_hex(6)


def _sink(platform: types.SimpleNamespace) -> PostgresApplicationAuditSink:
    return PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool_size=2)


def _counter_rows(platform: types.SimpleNamespace, operation: str) -> "list[tuple]":
    return _admin(
        platform,
        sql.SQL(
            "SELECT window_start, window_end, occurrences, summary_event_id::text, request_id, actor_id, application_id "
            "FROM {} WHERE operation = %s ORDER BY window_start"
        ).format(_table(platform)),
        [operation],
    )


def _audit_rows(platform: types.SimpleNamespace, operation: str) -> "list[tuple]":
    return _admin(
        platform,
        sql.SQL("SELECT event_id::text, request_id, outcome, count FROM {} WHERE operation = %s ORDER BY audit_seq").format(
            sql.Identifier(platform.schema, "application_audit")
        ),
        [operation],
    )


def _wait_for_room_in_window(window_ms: int, need_ms: int) -> None:
    """Sleeps into the next window when fewer than `need_ms` remain in the
    current one, so a burst of calls cannot straddle a window boundary."""
    remaining = window_ms - int(time.time() * 1000) % window_ms
    if remaining < need_ms:
        time.sleep((remaining + 50) / 1000)


def _sleep_until_window_closes(window_ms: int) -> None:
    remaining = window_ms - int(time.time() * 1000) % window_ms
    time.sleep((remaining + 150) / 1000)


def _reader(platform: types.SimpleNamespace) -> PostgresAuditQueryStore:
    return PostgresAuditQueryStore(_auditreader_dsn(platform), schema=platform.schema, pool_size=1)


def _summaries(platform: types.SimpleNamespace, operation: str, *, visibility_lag_ms: int = 0) -> "list[dict[str, Any]]":
    reader = _reader(platform)
    try:
        rows = reader.query(event_classes=None, after=None, limit=1000, visibility_lag_ms=visibility_lag_ms)
    finally:
        reader.close()
    return [row for row in rows if row["operation"] == operation and row["outcome"] == "deny" and row["plane"] == "application"]


# ===========================================================================
# grants: the runtime role reaches the counter only through the function
# ===========================================================================


def test_runtime_role_has_execute_on_the_function_and_no_privilege_on_the_counter_table(platform: types.SimpleNamespace) -> None:
    """The data-plane role holds EXECUTE on `denial_window_record` and no
    privilege at all on `denial_window_counter`: a direct UPDATE (lowering
    a count), DELETE, INSERT and SELECT are each refused by privilege, so
    the runtime role cannot reduce or erase audit evidence."""
    fn = _fn(platform).as_string()
    table = f"{platform.schema}.denial_window_counter"
    with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
        assert conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", [platform.api_role, fn]).fetchone()[0] is True
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert conn.execute("SELECT has_table_privilege(%s, %s, %s)", [platform.api_role, table, privilege]).fetchone()[0] is False, privilege
    # non-空振り: a counter row exists to be UPDATEd/DELETEd.
    operation = _new_operation()
    sink = _sink(platform)
    try:
        sink.record_denial(window_ms=_HOUR_MS, **_fields(operation))
    finally:
        sink.close()
    assert len(_counter_rows(platform, operation)) == 1
    with psycopg.connect(platform.api_dsn, autocommit=True) as conn:
        for statement in (
            sql.SQL("UPDATE {} SET occurrences = 0").format(_table(platform)),
            sql.SQL("DELETE FROM {}").format(_table(platform)),
            sql.SQL("SELECT count(*) FROM {}").format(_table(platform)),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    assert _counter_rows(platform, operation)[0][2] == 1, "a refused UPDATE/DELETE changed the count"


def test_other_roles_hold_nothing_on_the_counter_and_only_the_auditreader_reads_it(platform: types.SimpleNamespace) -> None:
    table = f"{platform.schema}.denial_window_counter"
    controlplane_role = f"{platform.prefix}_controlplane"
    auditreader_role = f"{platform.prefix}_auditreader"
    with psycopg.connect(_platform_dsn(platform), autocommit=True) as conn:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert conn.execute("SELECT has_table_privilege(%s, %s, %s)", [controlplane_role, table, privilege]).fetchone()[0] is False, privilege
        assert conn.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", [auditreader_role, table]).fetchone()[0] is True
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert conn.execute("SELECT has_table_privilege(%s, %s, %s)", [auditreader_role, table, privilege]).fetchone()[0] is False, privilege


# ===========================================================================
# SECURITY DEFINER hygiene
# ===========================================================================


def test_function_is_security_definer_with_a_pinned_search_path(platform: types.SimpleNamespace) -> None:
    rows = _admin(
        platform,
        "SELECT p.prosecdef, p.proconfig FROM pg_proc p WHERE p.oid = to_regprocedure(%s)::oid",
        [_fn(platform).as_string()],
    )
    assert rows, "the function does not exist"
    security_definer, config = rows[0]
    assert security_definer is True
    assert [entry.replace(" ", "") for entry in config or []] == ["search_path=pg_catalog,pg_temp"]


def test_public_holds_no_execute_on_the_function_and_another_role_cannot_call_it(platform: types.SimpleNamespace) -> None:
    rows = _admin(
        platform,
        "SELECT p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE') "
        "FROM pg_proc p WHERE p.oid = to_regprocedure(%s)::oid",
        [_fn(platform).as_string()],
    )
    assert rows and rows[0][0] is False, "PUBLIC may execute the function"
    controlplane_dsn = platform.controlplane_dsn
    fields = _fields(_new_operation())
    with psycopg.connect(controlplane_dsn, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                sql.SQL("SELECT {}(%s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)").format(
                    sql.SQL("{}.denial_window_record").format(sql.Identifier(platform.schema))
                ),
                [_HOUR_MS, fields["event_class"], fields["request_id"], fields["application_id"], fields["actor_type"],
                 fields["actor_id"], fields["role"], fields["operation"], fields["target_kind"], fields["reason_code"], fields["target_id"]],
            )


def test_migration_run_by_another_role_leaves_the_function_and_table_owned_by_the_schema_owner(
    platform: types.SimpleNamespace, tmp_path: Path,
) -> None:
    """The functions and the table are owned by the schema's owner role,
    whichever role runs the migration: dropping both and applying the file
    as the cluster's administrative role (not the schema owner) still
    leaves the owner the schema owner."""
    schema_owner = _admin(
        platform, "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = %s", [platform.schema],
    )[0][0]
    assert schema_owner == platform.control_role
    admin_role = _admin(platform, "SELECT current_user")[0][0]
    assert admin_role != schema_owner, "the administrative role must differ from the schema owner for this test to mean anything"
    _admin(platform, sql.SQL("DROP FUNCTION {}").format(_fn(platform)))
    _admin(platform, sql.SQL("DROP TABLE {}").format(_table(platform)))
    text = (MIGRATIONS_DIR / _MIGRATION).read_text().replace("r2dbsvc", platform.prefix)
    path = tmp_path / _MIGRATION
    path.write_text(text)
    _run_psql(_platform_dsn(platform), path)
    function_owner = _admin(
        platform, "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid = to_regprocedure(%s)::oid", [_fn(platform).as_string()],
    )[0][0]
    table_owner = _admin(
        platform, "SELECT tableowner FROM pg_tables WHERE schemaname = %s AND tablename = 'denial_window_counter'", [platform.schema],
    )[0][0]
    assert (function_owner, table_owner) == (schema_owner, schema_owner)
    # The migration applies again on top of itself (idempotent) and keeps the state.
    _run_psql(_platform_dsn(platform), path)
    assert _admin(
        platform, "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid = to_regprocedure(%s)::oid", [_fn(platform).as_string()],
    )[0][0] == schema_owner


# ===========================================================================
# the startup / verify check names each lost property
# ===========================================================================


def _check(platform: types.SimpleNamespace) -> None:
    with psycopg.connect(platform.api_dsn) as conn:
        platform_declarations.check_denial_window_function(
            conn, schema=platform.schema, ops_module=platform_declarations.PEER_MODULE, migration=_MIGRATION,
        )


def test_the_check_passes_on_the_migrated_platform(platform: types.SimpleNamespace) -> None:
    _check(platform)


@pytest.mark.parametrize(
    ("break_statement", "restore_statement", "fragment"),
    [
        ("ALTER FUNCTION {fn} SECURITY INVOKER", "ALTER FUNCTION {fn} SECURITY DEFINER", "SECURITY DEFINER"),
        ("ALTER FUNCTION {fn} RESET search_path", "ALTER FUNCTION {fn} SET search_path = pg_catalog, pg_temp", "search_path"),
        ("GRANT EXECUTE ON FUNCTION {fn} TO PUBLIC", "REVOKE ALL ON FUNCTION {fn} FROM PUBLIC", "PUBLIC"),
        ("ALTER FUNCTION {fn} OWNER TO {api_role}", "ALTER FUNCTION {fn} OWNER TO {control_role}", "it is not owned by the schema's owner role"),
        ("ALTER TABLE {table} OWNER TO {api_role}", "ALTER TABLE {table} OWNER TO {control_role}", "table is not owned"),
    ],
    ids=["security_invoker", "search_path_unpinned", "public_execute", "function_owner", "table_owner"],
)
def test_the_check_names_each_lost_property(
    platform: types.SimpleNamespace, break_statement: str, restore_statement: str, fragment: str,
) -> None:
    names = dict(
        fn=_fn(platform).as_string(), table=f"{platform.schema}.denial_window_counter",
        api_role=platform.api_role, control_role=platform.control_role,
    )
    _check(platform)  # the healthy state passes, so the failure below is the property's own
    _admin(platform, break_statement.format(**names))
    try:
        with pytest.raises(PlatformDeclarationError) as excinfo:
            _check(platform)
        assert excinfo.value.code == "F-21"
        assert fragment in str(excinfo.value), str(excinfo.value)
        assert _MIGRATION in str(excinfo.value)
    finally:
        _admin(platform, restore_statement.format(**names))
        _admin(platform, sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(_fn(platform), sql.Identifier(platform.api_role)))
    _check(platform)


def test_the_check_names_a_missing_function(platform: types.SimpleNamespace) -> None:
    with psycopg.connect(platform.api_dsn) as conn:
        with pytest.raises(PlatformDeclarationError) as excinfo:
            platform_declarations.check_denial_window_function(
                conn, schema=f"{platform.prefix}_no_such_schema", ops_module=platform_declarations.PEER_MODULE, migration=_MIGRATION,
            )
    assert excinfo.value.code == "F-21"
    assert "does not exist" in str(excinfo.value)


# ===========================================================================
# the window: aligned to the clock, one counter row and one first row per key
# ===========================================================================


def test_concurrent_first_refusals_of_one_key_leave_one_counter_row_and_one_first_row(platform: types.SimpleNamespace) -> None:
    operation = _new_operation()
    callers = 6
    _wait_for_room_in_window(_HOUR_MS, 10_000)
    barrier = threading.Barrier(callers)
    errors: list[BaseException] = []

    def _call() -> None:
        try:
            sink = _sink(platform)
            try:
                barrier.wait(timeout=10)
                sink.record_denial(window_ms=_HOUR_MS, **_fields(operation))
            finally:
                sink.close()
        except BaseException as exc:  # noqa: BLE001 -- surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=_call) for _ in range(callers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    counters = _counter_rows(platform, operation)
    assert len(counters) == 1, counters
    assert counters[0][2] == callers, f"the counter holds {counters[0][2]}, expected {callers}"
    assert len(_audit_rows(platform, operation)) == 1


def test_the_window_is_aligned_to_the_clock_and_null_application_folds_to_one_key(platform: types.SimpleNamespace) -> None:
    operation = _new_operation()
    window_ms = 600_000
    _wait_for_room_in_window(window_ms, 5_000)
    sink = _sink(platform)
    try:
        sink.record_denial(window_ms=window_ms, **_fields(operation, application_id=None, actor_id=None, actor_type="unknown", role=None))
        sink.record_denial(window_ms=window_ms, **_fields(operation, application_id=None, actor_id=None, actor_type="unknown", role=None))
        sink.record_denial(window_ms=window_ms, **_fields(operation, application_id="app-window"))
    finally:
        sink.close()
    counters = _counter_rows(platform, operation)
    assert len(counters) == 2, f"a NULL application is one key, a real one another -- got {counters!r}"
    by_application = {row[6]: row for row in counters}
    assert by_application[None][2] == 2
    assert by_application["app-window"][2] == 1
    for window_start, window_end, *_rest in counters:
        assert int(window_start.timestamp() * 1000) % window_ms == 0, f"the window starts at {window_start}, off the {window_ms} ms grid"
        assert window_end - window_start == timedelta(milliseconds=window_ms)
    # A zero length is not a window: every refusal is an ordinary row.
    zero_operation = _new_operation()
    sink = _sink(platform)
    try:
        sink.record_denial(window_ms=0, **_fields(zero_operation))
        sink.record_denial(window_ms=0, **_fields(zero_operation))
    finally:
        sink.close()
    assert _counter_rows(platform, zero_operation) == []
    assert len(_audit_rows(platform, zero_operation)) == 2


# ===========================================================================
# one statement: the first refusal writes the counter row and its audit row
# together; the summary event keeps one identity
# ===========================================================================


def test_the_first_refusal_writes_both_rows_in_one_statement_and_commits_before_returning(platform: types.SimpleNamespace) -> None:
    operation = _new_operation()
    fields = _fields(operation)
    call = sql.SQL("SELECT {}.denial_window_record(%s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)").format(sql.Identifier(platform.schema))
    params = [_HOUR_MS, fields["event_class"], fields["request_id"], fields["application_id"], fields["actor_type"],
              fields["actor_id"], fields["role"], fields["operation"], fields["target_kind"], fields["reason_code"], fields["target_id"]]
    # Inside a transaction that is rolled back, neither row survives: the two
    # writes are one unit.
    with psycopg.connect(platform.api_dsn) as conn:
        conn.execute(call, params)
        conn.rollback()
    assert _counter_rows(platform, operation) == []
    assert _audit_rows(platform, operation) == []
    # Through the sink (autocommit), both rows exist as soon as it returns,
    # seen from a different connection.
    sink = _sink(platform)
    try:
        sink.record_denial(window_ms=_HOUR_MS, **fields)
    finally:
        sink.close()
    assert len(_counter_rows(platform, operation)) == 1
    audit_rows = _audit_rows(platform, operation)
    assert len(audit_rows) == 1 and audit_rows[0][1] == fields["request_id"] and audit_rows[0][2] == "deny" and audit_rows[0][3] is None


def test_a_closed_windows_summary_event_keeps_the_same_event_id_across_reads(platform: types.SimpleNamespace) -> None:
    operation = _new_operation()
    window_ms = 1000
    _wait_for_room_in_window(window_ms, 700)
    sink = _sink(platform)
    try:
        for _ in range(3):
            sink.record_denial(window_ms=window_ms, **_fields(operation))
    finally:
        sink.close()
    _sleep_until_window_closes(window_ms)
    first_read = _summaries(platform, operation)
    second_read = _summaries(platform, operation)
    summaries_first = [row for row in first_read if row["count"] is not None]
    summaries_second = [row for row in second_read if row["count"] is not None]
    assert len(summaries_first) == 1 and len(summaries_second) == 1
    assert summaries_first[0]["event_id"] == summaries_second[0]["event_id"]
    assert summaries_first[0]["event_id"] == _counter_rows(platform, operation)[0][3]


# ===========================================================================
# what the count means, and what audit_query returns
# ===========================================================================


@pytest.mark.parametrize(("occurrences", "expected_count", "expected_summary"), [(1, None, False), (2, None, True), (5, 4, True)])
def test_the_count_of_a_closed_window_is_the_repeats_and_the_total_is_n(
    platform: types.SimpleNamespace, occurrences: int, expected_count: "int | None", expected_summary: bool,
) -> None:
    operation = _new_operation()
    window_ms = 1000
    _wait_for_room_in_window(window_ms, 800)
    sink = _sink(platform)
    try:
        for _ in range(occurrences):
            sink.record_denial(window_ms=window_ms, **_fields(operation))
    finally:
        sink.close()
    _sleep_until_window_closes(window_ms)
    rows = _summaries(platform, operation)
    first_rows = [row for row in rows if row["event_id"] in {r[0] for r in _audit_rows(platform, operation)}]
    summaries = [row for row in rows if row["event_id"] not in {r[0] for r in _audit_rows(platform, operation)}]
    assert len(first_rows) == 1, f"the first refusal is its own row: {rows!r}"
    assert (len(summaries) == 1) is expected_summary, f"{occurrences} occurrences -> summaries {summaries!r}"
    if summaries:
        assert summaries[0]["count"] == expected_count
        assert "count" in summaries[0]
    total = 1 + (0 if not summaries else (summaries[0]["count"] or 1))
    assert total == occurrences


def test_audit_query_returns_only_closed_windows_as_application_plane_events_ending_at_the_window_end(platform: types.SimpleNamespace) -> None:
    operation = _new_operation()
    open_operation = _new_operation()
    window_ms = 1000
    _wait_for_room_in_window(window_ms, 800)
    sink = _sink(platform)
    try:
        for _ in range(3):
            sink.record_denial(window_ms=window_ms, **_fields(operation))
        for _ in range(3):
            sink.record_denial(window_ms=_HOUR_MS, **_fields(open_operation))
    finally:
        sink.close()
    _sleep_until_window_closes(window_ms)
    summaries = [row for row in _summaries(platform, operation) if row["count"] is not None]
    assert len(summaries) == 1
    (window_start, window_end, *_rest) = _counter_rows(platform, operation)[0]
    assert summaries[0]["plane"] == "application"
    assert summaries[0]["recorded_at"] == window_end
    assert summaries[0]["count"] == 2
    # A window that is still open contributes no summary event ...
    assert [row for row in _summaries(platform, open_operation) if row["count"] is not None] == []
    # ... and neither does a closed one until the visibility lag has passed.
    assert [row for row in _summaries(platform, operation, visibility_lag_ms=_HOUR_MS) if row["count"] is not None] == []


def test_a_service_over_the_postgres_sink_counts_refusals_and_a_failed_count_is_a_503(platform: types.SimpleNamespace) -> None:
    credentials = CredentialStore(pepper="test-pepper-denial-window")
    sink = PostgresApplicationAuditSink(platform.api_dsn, schema=platform.schema, pool_size=2)
    service = DataService(credentials, durable_audit=sink, denial_coalesce_window_s=1.0)
    operation = "authenticate"
    marker = "wrong-secret-" + secrets.token_hex(4)
    try:
        _wait_for_room_in_window(1000, 800)
        before = len(_admin(platform, sql.SQL("SELECT 1 FROM {} WHERE operation = %s AND reason_code = 'AUTH_INVALID'").format(
            sql.Identifier(platform.schema, "application_audit")), [operation]))
        for _ in range(4):
            with pytest.raises(FoundationError) as exc:
                service.authenticate(marker)
            assert exc.value.code == "AUTH_INVALID"
        # A count that cannot be recorded makes the refusal a 503.
        _admin(platform, sql.SQL("REVOKE EXECUTE ON FUNCTION {} FROM {}").format(_fn(platform), sql.Identifier(platform.api_role)))
        try:
            with pytest.raises(FoundationError) as failure:
                service.authenticate(marker)
            assert (failure.value.code, failure.value.status) == ("SERVICE_UNAVAILABLE", 503)
        finally:
            _admin(platform, sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(_fn(platform), sql.Identifier(platform.api_role)))
        after = len(_admin(platform, sql.SQL("SELECT 1 FROM {} WHERE operation = %s AND reason_code = 'AUTH_INVALID'").format(
            sql.Identifier(platform.schema, "application_audit")), [operation]))
        assert after - before == 1, "four refusals in one window wrote more than the window's first row"
        newest = _admin(platform, sql.SQL("SELECT occurrences FROM {} WHERE operation = %s AND actor_id IS NULL ORDER BY window_start DESC LIMIT 1").format(_table(platform)), [operation])
        assert newest == [(4,)], newest
    finally:
        sink.close()


# ===========================================================================
# startup: `build_app` runs the same check on its own writer connection
# ===========================================================================


def _start_and_stop(main_module: types.ModuleType, env: dict[str, str]) -> None:
    """Builds the app and runs its lifespan once, which releases every pool
    the build opened."""
    with TestClient(main_module.build_app(env=env)):
        pass


def test_build_app_refuses_to_start_when_the_refusal_window_function_is_unsafe_or_missing(
    platform: types.SimpleNamespace, provisioned_app: types.SimpleNamespace, main_module: types.ModuleType,
) -> None:
    env = _main_env(platform, provisioned_app)
    fn = _fn(platform).as_string()
    _start_and_stop(main_module, env)  # healthy: starts
    _admin(platform, f"ALTER FUNCTION {fn} RESET search_path")
    try:
        with pytest.raises(PlatformDeclarationError) as excinfo:
            main_module.build_app(env=env)
        assert excinfo.value.code == "F-21"
        assert "search_path" in str(excinfo.value)
    finally:
        _admin(platform, f"ALTER FUNCTION {fn} SET search_path = pg_catalog, pg_temp")
    _admin(platform, f"REVOKE EXECUTE ON FUNCTION {fn} FROM {platform.api_role}")
    try:
        with pytest.raises(PlatformDeclarationError) as excinfo:
            main_module.build_app(env=env)
        assert excinfo.value.code == "F-21"
        assert "may not EXECUTE" in str(excinfo.value)
    finally:
        _admin(platform, f"GRANT EXECUTE ON FUNCTION {fn} TO {platform.api_role}")
    _start_and_stop(main_module, env)


# ===========================================================================
# the migration is enumerated wherever migrations are applied
# ===========================================================================

_NOT_PLATFORM_ENUMERATED = frozenset({
    # bootstrap-only, once ever
    "0001_bootstrap_control_plane.sql", "0002_provisioning_functions.sql",
    # per-application scripts
    "0003_provision_application.sql", "0004_deprovision_application.sql",
    "0009_platform_upgrades_ledger_upgrade.sql", "0010_field_constraints_upgrade.sql", "0011_idempotency_records_upgrade.sql",
    # carry a password variable, never accepted by `apply-platform-migration`
    "0005_credential_store.sql", "0006_control_plane_http.sql", "0007_application_audit.sql",
})


def test_every_platform_migration_file_is_accepted_by_apply_platform_migration_or_named_as_excluded() -> None:
    files = {path.name for path in MIGRATIONS_DIR.glob("*.sql")}
    accepted = set(ops._PLATFORM_MIGRATION_FILENAMES)
    assert accepted <= files
    assert files - accepted == _NOT_PLATFORM_ENUMERATED, sorted((files - accepted) ^ _NOT_PLATFORM_ENUMERATED)
    assert _MIGRATION in accepted
    assert ops._PLATFORM_MIGRATION_VARIABLE_TABLE[_MIGRATION] == ()
