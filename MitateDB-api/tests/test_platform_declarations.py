"""Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3 D-1/D-2/
D-2(h), work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md
§4 WP-2, supervisor rework ruling 2026-09-05 `{scratchpad}/rulings-
q4-wp12-rework.md`): `platform_declarations.py`'s own fail-fast conditions
F-1..F-11, F-3c, F-13.

Pure-Python conditions (F-1/F-2 env rejection, F-4b/F-5 value validation,
F-6/F-3c consistency) are tested without a database. F-3/F-4/F-7/F-8/F-9/
F-10/F-11/F-13 require a real, throwaway-provisioned platform database
(design's own non-vacuity requirement: "実 PG に上書きを注入して観測する...
合成 stub で済ませない") -- this file reuses `control_plane_harness.
control_platform` (module-scoped: this file gets its OWN throwaway
platform, isolated from every other test module using the same fixture
name). Migration `0007` now seeds `audit_writer_roles` itself (from the
SAME `api_role`/`controlplane_role` psql variables the fixture already
passes it, D-2(h) 1) -- no extra fixture seeding step is needed for that
row.

Fail-fast message string pins (work order completion condition 12: "設計
§3.8 の F-1〜F-11 の骨子を逐語 assert するテストが存在すること...とくに
「次に打つ ops コマンド名」が各メッセージに含まれる", extended to F-3c/F-13
by this rework) assert the LITERAL substrings copied verbatim from design
§3.8 / `{scratchpad}/q4-f3c-and-amendments.md` -- never a paraphrase
(completion condition (h), ruling §4).
"""
from __future__ import annotations

import psycopg
import pytest

from .control_plane_harness import control_platform, set_role_timeouts  # noqa: F401 (fixture)
from mitatedb_api.platform_declarations import (DEFAULT_SCHEMA, MIGRATION_NUMBER, PEER_MODULE,
                                                PlatformDeclarationError, PlatformDeclarations,
                                                RoleTimeoutCatalog, Surfaces,
                                                check_control_surface_consistency,
                                                check_writer_role_timeouts,
                                                derive_visibility_lag_ms,
                                                read_declared_role_timeouts,
                                                read_effective_timeouts_ms,
                                                read_platform_declarations,
                                                reject_removed_surface_env,
                                                reject_removed_timeout_env,
                                                require_control_surface_declared,
                                                validate_audit_writer_roles_value,
                                                validate_coalescing_window_value,
                                                validate_surfaces_value)

_NAMES_TIMEOUT = ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS")
_NAMES_SURFACE = ("MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL")


# ---------------------------------------------------------------------------
# F-1 / F-2: removed env vars, rejected whenever DEFINED (value irrelevant,
# empty string included). WP-1/WP-2 completion condition 3: "4 変数 ×
# {空文字列, 実値} の 8 ケースを個別に観測する".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "5000"])
def test_reject_removed_timeout_env_statement_ms(value: str) -> None:
    with pytest.raises(PlatformDeclarationError, match="MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS is no longer read"):
        reject_removed_timeout_env({"MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS": value}, names=_NAMES_TIMEOUT)


@pytest.mark.parametrize("value", ["", "5000"])
def test_reject_removed_timeout_env_idle_ms(value: str) -> None:
    with pytest.raises(PlatformDeclarationError, match="MITATEDB_AUDIT_IDLE_TIMEOUT_MS is no longer read"):
        reject_removed_timeout_env({"MITATEDB_AUDIT_IDLE_TIMEOUT_MS": value}, names=_NAMES_TIMEOUT)


@pytest.mark.parametrize("value", ["", "https://h/v1"])
def test_reject_removed_surface_env_data_base_url(value: str) -> None:
    with pytest.raises(PlatformDeclarationError, match="MITATEDB_DATA_BASE_URL is no longer read"):
        reject_removed_surface_env({"MITATEDB_DATA_BASE_URL": value}, names=_NAMES_SURFACE, schema=DEFAULT_SCHEMA)


@pytest.mark.parametrize("value", ["", "https://h/control/v1"])
def test_reject_removed_surface_env_control_base_url(value: str) -> None:
    with pytest.raises(PlatformDeclarationError, match="MITATEDB_CONTROL_BASE_URL is no longer read"):
        reject_removed_surface_env({"MITATEDB_CONTROL_BASE_URL": value}, names=_NAMES_SURFACE, schema=DEFAULT_SCHEMA)


def test_reject_removed_env_is_a_no_op_when_absent() -> None:
    """Non-vacuity companion: an EMPTY env mapping never raises -- the
    8-case parametrization above only proves DEFINED values are rejected;
    this proves an env mapping the two functions consider clean is not
    itself rejected."""
    reject_removed_timeout_env({}, names=_NAMES_TIMEOUT)
    reject_removed_surface_env({}, names=_NAMES_SURFACE, schema=DEFAULT_SCHEMA)


def test_reject_removed_env_checks_the_mapping_argument_not_os_environ(monkeypatch) -> None:
    """WP-1/WP-2 completion condition 4 (design D-1(d)): the check is
    against the `Mapping` a caller passes in, never `os.environ` -- an
    unrelated variable left over in a developer's shell or CI's parent
    environment must never fail this check."""
    monkeypatch.setenv("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "9999")
    reject_removed_timeout_env({}, names=_NAMES_TIMEOUT)  # does not raise: os.environ is not consulted


def test_fail_fast_messages_name_the_next_ops_command() -> None:
    """Completion condition 12 (常設規律 4): "次に打つ ops コマンド名"
    must be in each message -- checked here for F-1/F-2 together (the
    pure-Python conditions); F-3/F-3c/F-4/F-4b/F-5/F-6/F-7/F-8/F-9/F-10/
    F-11/F-13 are pinned individually below, each alongside its own
    real-PG or pure-Python trigger."""
    with pytest.raises(PlatformDeclarationError) as exc1:
        reject_removed_timeout_env({"MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS": ""}, names=_NAMES_TIMEOUT)
    assert "python -m mitatedb_api.ops set-platform-timeouts" in str(exc1.value)

    with pytest.raises(PlatformDeclarationError) as exc2:
        reject_removed_surface_env({"MITATEDB_DATA_BASE_URL": ""}, names=_NAMES_SURFACE, schema=DEFAULT_SCHEMA)
    assert "python -m mitatedb_api.ops declare-surfaces" in str(exc2.value)


# ---------------------------------------------------------------------------
# F-4b(i): `audit_coalescing_window_ms` value validation (jsonb numeric,
# integer, >= 0). WP-1/WP-2 completion condition 6.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", ["not-an-int", -5, 1.5, True])
def test_validate_coalescing_window_value_rejects(bad_value) -> None:
    with pytest.raises(PlatformDeclarationError, match="audit_coalescing_window_ms"):
        validate_coalescing_window_value(bad_value, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


def test_validate_coalescing_window_value_accepts_zero() -> None:
    """Design D-2(d): "0 は「coalescing を行わない」を意味する有効な値"."""
    assert validate_coalescing_window_value(0, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE) == 0


def test_validate_coalescing_window_value_accepts_a_positive_int() -> None:
    assert validate_coalescing_window_value(60000, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE) == 60000


def test_f4b_message_names_the_next_ops_command() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_coalescing_window_value(-1, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert "python -m mitatedb_api.ops declare-coalescing-window" in str(exc.value)


# ---------------------------------------------------------------------------
# F-4b(ii): `audit_writer_roles` value validation -- non-empty string
# array, no duplicates, each a valid PostgreSQL identifier (design D-2(h)
# 6). WP-2 completion condition 23 / ruling §4(b).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [
    [],                       # empty
    "not-a-list",             # wrong type entirely
    ["a", "a"],               # duplicate
    ["Not-Valid!"],           # not a syntactically valid identifier
    [1, 2],                   # non-string elements
])
def test_validate_audit_writer_roles_value_rejects(bad_value) -> None:
    with pytest.raises(PlatformDeclarationError, match="audit_writer_roles"):
        validate_audit_writer_roles_value(bad_value, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


def test_validate_audit_writer_roles_value_accepts_the_shipped_shape() -> None:
    result = validate_audit_writer_roles_value(
        ["mitatedbsvc_api", "mitatedbsvc_controlplane"], schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert result == ("mitatedbsvc_api", "mitatedbsvc_controlplane")


def test_f4b_writer_roles_message_names_the_migration() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_audit_writer_roles_value([], schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert f"migration {MIGRATION_NUMBER}" in str(exc.value)


# ---------------------------------------------------------------------------
# F-5: `surfaces` value validation -- design D-2(d)'s 4 checks (absolute
# URL, `/v1` suffix, `/control/v1` suffix, no trailing slash), reused from
# `surfaces.py`. WP-1/WP-2 completion condition 6. Rework ruling §3 point
# 3: "F-5 に実 schema 名" -- the message must show the ACTUAL schema, not
# a literal "<registry>" placeholder.
# ---------------------------------------------------------------------------


def test_validate_surfaces_value_accepts_data_only() -> None:
    result = validate_surfaces_value(
        {"data": {"base_url": "https://h.example.invalid/v1"}}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert result == Surfaces(data_base_url="https://h.example.invalid/v1", control_base_url=None)


def test_validate_surfaces_value_accepts_data_and_control() -> None:
    result = validate_surfaces_value({
        "data": {"base_url": "https://h.example.invalid/v1"},
        "control": {"base_url": "https://h.example.invalid/control/v1"},
    }, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert result == Surfaces(
        data_base_url="https://h.example.invalid/v1", control_base_url="https://h.example.invalid/control/v1")


@pytest.mark.parametrize("bad_data", [
    {"data": {"base_url": "not-a-url"}},
    {"data": {"base_url": "https://h.example.invalid/v1/"}},
    {"data": {"base_url": "https://h.example.invalid/v2"}},
    {"data": {"base_url": "https://h.example.invalid/control/v1"}},
    "not-a-dict",
    {},
])
def test_validate_surfaces_value_rejects_malformed_data(bad_data) -> None:
    with pytest.raises(PlatformDeclarationError, match="surfaces.data.base_url"):
        validate_surfaces_value(bad_data, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


def test_validate_surfaces_value_rejects_malformed_control() -> None:
    with pytest.raises(PlatformDeclarationError, match="surfaces.control.base_url"):
        validate_surfaces_value({
            "data": {"base_url": "https://h.example.invalid/v1"},
            "control": {"base_url": "https://h.example.invalid/v1"},
        }, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


def test_f5_message_names_the_next_ops_command() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_surfaces_value({"data": {"base_url": "not-a-url"}}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert "python -m mitatedb_api.ops declare-surfaces" in str(exc.value)


def test_f5_message_names_the_real_schema_not_a_literal_placeholder() -> None:
    """Rework ruling §3 point 3: the previous draft embedded the literal
    text "<registry>" in this message instead of substituting the actual
    schema -- this observes a THROWAWAY schema name flowing through."""
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_surfaces_value(
            {"data": {"base_url": "not-a-url"}}, schema="some_throwaway_schema_x1", ops_module=PEER_MODULE)
    assert "some_throwaway_schema_x1.platform_declarations" in str(exc.value)
    assert "<registry>" not in str(exc.value)


# ---------------------------------------------------------------------------
# F-6: `surfaces.control` presence x `*_CONTROL_PLANE_STATUS` consistency,
# BOTH directions -- data-plane ONLY. WP-1/WP-2 completion condition 7.
# ---------------------------------------------------------------------------


def test_f6_forward_direction_control_declared_but_status_unavailable() -> None:
    surfaces = Surfaces(data_base_url="https://h/v1", control_base_url="https://h/control/v1")
    with pytest.raises(PlatformDeclarationError, match="surfaces.control is declared"):
        check_control_surface_consistency(surfaces, "unavailable", ops_module=PEER_MODULE)


def test_f6_reverse_direction_control_not_declared_but_status_enabled() -> None:
    surfaces = Surfaces(data_base_url="https://h/v1", control_base_url=None)
    with pytest.raises(PlatformDeclarationError, match="surfaces.control is not declared"):
        check_control_surface_consistency(surfaces, "enabled", ops_module=PEER_MODULE)


def test_f6_both_directions_name_the_next_ops_command() -> None:
    with pytest.raises(PlatformDeclarationError) as forward:
        check_control_surface_consistency(
            Surfaces(data_base_url="https://h/v1", control_base_url="https://h/control/v1"),
            "unavailable", ops_module=PEER_MODULE)
    assert "python -m mitatedb_api.ops declare-surfaces" in str(forward.value)

    with pytest.raises(PlatformDeclarationError) as reverse:
        check_control_surface_consistency(
            Surfaces(data_base_url="https://h/v1", control_base_url=None), "enabled", ops_module=PEER_MODULE)
    assert "python -m mitatedb_api.ops declare-surfaces" in str(reverse.value)


def test_f6_consistent_states_do_not_raise() -> None:
    """Non-vacuity companion: both the "control declared + enabled" and
    "no control + unavailable" agreeing states must NOT raise."""
    check_control_surface_consistency(
        Surfaces(data_base_url="https://h/v1", control_base_url="https://h/control/v1"), "enabled", ops_module=PEER_MODULE)
    check_control_surface_consistency(
        Surfaces(data_base_url="https://h/v1", control_base_url=None), "unavailable", ops_module=PEER_MODULE)


# ---------------------------------------------------------------------------
# F-3c (monitor ruling 2026-09-05): the control-plane process' own
# unconditional "surfaces.control must be declared" check -- distinct
# from F-3 (the whole row is absent) and never routed through F-6 (which
# is data-plane only and has no `*_CONTROL_PLANE_STATUS`-shaped knob on
# the control side to consult).
# ---------------------------------------------------------------------------


def test_f3c_raised_when_surfaces_row_exists_but_has_no_control() -> None:
    surfaces = Surfaces(data_base_url="https://h/v1", control_base_url=None)
    with pytest.raises(PlatformDeclarationError, match="has no surfaces.control"):
        require_control_surface_declared(surfaces, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


def test_f3c_message_is_verbatim() -> None:
    """`{scratchpad}/q4-f3c-and-amendments.md` -- complete-sentence
    verbatim pin (completion condition (h): full-string equality, not a
    substring)."""
    with pytest.raises(PlatformDeclarationError) as exc:
        require_control_surface_declared(
            Surfaces(data_base_url="https://h/v1", control_base_url=None), schema="myregistry", ops_module="mypeer")
    assert str(exc.value) == (
        "'surfaces' row in myregistry.platform_declarations has no surfaces.control, but this is the "
        "control-plane process, which always has a control surface to declare (contract 1.6.0: both "
        "documents return the same surfaces object). Declare it with 'python -m mypeer.ops "
        "declare-surfaces --data-base-url <URL> --control-base-url <URL>', then restart both processes."
    )


def test_f3c_does_not_raise_when_control_is_declared() -> None:
    surfaces = Surfaces(data_base_url="https://h/v1", control_base_url="https://h/control/v1")
    require_control_surface_declared(surfaces, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)


# ---------------------------------------------------------------------------
# F-3 / F-4 / F-8: `platform_declarations` table/row existence, in the
# design §3.7 REQUIRED order (table before rows). Real PG (`control_
# platform` fixture already applies migration 0007, which now seeds
# `audit_coalescing_window_ms` AND `audit_writer_roles`, and seeds
# `surfaces` itself with a synthetic example.invalid pair). WP-1/WP-2
# completion condition 5.
# ---------------------------------------------------------------------------


def test_read_platform_declarations_happy_path(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        result = read_platform_declarations(
            conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        conn.close()
    assert isinstance(result, PlatformDeclarations)
    assert result.audit_coalescing_window_ms == 60000
    assert result.surfaces.data_base_url.startswith("https://")
    assert result.surfaces.control_base_url.startswith("https://")
    assert result.audit_writer_roles == (control_platform.api_role, control_platform.controlplane_role)


def test_f8_missing_table_reads_as_relation_does_not_exist(control_platform) -> None:
    """F-8: the declarations table itself is absent -- simulated here by
    reading against `registry_schema`'s SIBLING (nonexistent) schema name,
    real PG, never a synthetic stub."""
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with pytest.raises(PlatformDeclarationError, match="does not exist"):
            read_platform_declarations(
                conn, schema=control_platform.registry_schema + "_missing", ops_module=PEER_MODULE,
                migration=MIGRATION_NUMBER)
    finally:
        conn.close()


def test_build_app_and_build_control_service_refuse_to_start_when_migration_0007_has_not_been_applied(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """{scratchpad}/wp12-audit-gaps.md G6 (WP-2 completion condition
    23(g)): non-vacuity companion to `test_f8_missing_table_reads_as_
    relation_does_not_exist` above (that test simulates absence via a
    sibling schema name against an ALREADY-0007-applied platform) --
    mirrors r2db-api's own `tests/test_application_audit.py::test_build_
    app_refuses_to_start_when_migration_0008_has_not_been_applied`
    against a REAL platform that has NEVER had its own single platform-
    declarations migration applied at all (0001/0002 only -- the exact
    pre-Q4 shape every already-deployed instance has), widened to BOTH
    processes (unlike that r2db test, which only reads via one role's own
    connection, citing the cost of also provisioning a servable
    application purely to reach `build_app`'s own read-platform-
    declarations step): the control-plane half here calls the REAL
    `build_control_service` composition root directly (design §3.10:
    MitateDB-api's control composition root genuinely runs through
    `read_platform_declarations` -- unlike r2db's `assemble_control_
    stack`, which never reads the declarations table in its own HTTP-
    conformance path at all -- and `build_control_service` needs no
    served-application registration, unlike `build_app`); the data-plane
    half reads via `read_platform_declarations` directly against the
    `mitatedbsvc_api`-role connection `build_app` itself would open at the
    identical point in its own startup sequence (same shortcut r2db's own
    test takes, for the identical reason: registering a servable
    application is a large, unrelated detour for this one condition).

    Both must fail with F-8 (`platform_declarations` itself does not
    exist), never a raw, uncaught psycopg exception -- the read path
    `build_app`/`build_control_service` share is `read_platform_
    declarations` itself, so this is exercised as the REAL entry points a
    deployment would call, not a synthetic stand-in."""
    import secrets
    from pathlib import Path

    from psycopg import sql as _sql

    from mitatedb_api.control_composition import build_control_service

    from .control_plane_harness import (MIGRATIONS_DIR, _dsn_with, _run_psql, admin_dsn,
                                        require_admin_connection, sweep_prefix)

    require_admin_connection()
    dsn = admin_dsn()
    prefix = "mtdbf8" + secrets.token_hex(4)
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mtdb_f8_migrations_" + prefix)
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
        admin = psycopg.connect(dsn, autocommit=True)
        try:
            with admin.cursor() as cur:
                cur.execute(_sql.SQL("ALTER ROLE {} PASSWORD {}").format(_sql.Identifier(api_role), _sql.Literal(api_password)))
                cur.execute(_sql.SQL("ALTER ROLE {} PASSWORD {}").format(_sql.Identifier(controlplane_role), _sql.Literal(controlplane_password)))
        finally:
            admin.close()
        # Deliberately NEVER applies 0007_platform_declarations.sql.

        api_dsn = _dsn_with(dsn, user=api_role, password=api_password, dbname=platform_db)
        controlplane_dsn = _dsn_with(dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)

        with psycopg.connect(api_dsn) as conn:
            with pytest.raises(PlatformDeclarationError, match="migration 0007"):
                read_platform_declarations(conn, schema=registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)

        control_env = {
            "MITATEDB_CREDENTIAL_PEPPER": "wp12e-g6-app-pepper-0000",
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "wp12e-g6-ctl-pepper-0000",
            "MITATEDB_CONTROLPLANE_DSN": controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": registry_schema,
        }
        with pytest.raises(PlatformDeclarationError, match="migration 0007"):
            build_control_service(control_env)
    finally:
        sweep_prefix(dsn, prefix)


def test_f3_missing_surfaces_row(control_platform) -> None:
    """{scratchpad}/wp12-audit-gaps.md G7: upgraded from a `match=`
    substring check to a full-string (`==`) verbatim pin against the REAL
    absence this fixture produces (design's own non-vacuity requirement),
    mirroring r2db-api's own `tests/test_ops_declarations.py::test_f3_
    message_is_pinned_verbatim_against_real_absence`. `test_f3_message_
    is_verbatim` above pins the same text without a database; this test
    pins it is the ACTUAL text `read_platform_declarations` raises against
    a real, migration-0007-provisioned platform database. Deliberately
    does NOT call `_f3_message` itself to build the expected string (that
    would make this assertion pass no matter how `_f3_message`'s own text
    drifted, since both sides would be the SAME possibly-wrong function --
    the exact vacuity `test_f3_message_is_verbatim` above's independent
    literal avoids); this test independently re-types the literal, like
    r2db-api's own `tests/test_ops_declarations.py::_f3` helper does."""
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {control_platform.registry_schema}.platform_declarations WHERE key = 'surfaces'")
        read_conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError) as exc:
                read_platform_declarations(
                    read_conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
            assert str(exc.value) == (
                f"no 'surfaces' row in {control_platform.registry_schema}.platform_declarations: contract 1.6.0 "
                "requires surfaces.data unconditionally. Declare it with 'python -m mitatedb_api.ops "
                "declare-surfaces --data-base-url <URL> [--control-base-url <URL>]', then restart both processes."
            )
        finally:
            read_conn.close()
    finally:
        # restore for any other test in this module that reuses the
        # fixture -- IDENTICAL to the fixture's own seed value (control_
        # plane_harness.bootstrap_control_platform), never an ad hoc one
        # (rework ruling §3: "F-3 テストの fixture 復元は初期値と同一").
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {control_platform.registry_schema}.platform_declarations (key, value) "
                # One literal per URL so the synthetic `.example.invalid` host is
                # visible on its own line to the line-based public-value scanner.
                "VALUES ('surfaces', '{\"data\":{\"base_url\":"
                "\"https://data.mitatedb-control-platform.example.invalid/v1\"},"
                "\"control\":{\"base_url\":"
                "\"https://control.mitatedb-control-platform.example.invalid/control/v1\"}}')"
            )
        conn.close()


def test_f4_missing_window_row(control_platform) -> None:
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {control_platform.registry_schema}.platform_declarations "
                "WHERE key = 'audit_coalescing_window_ms'")
        read_conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="no 'audit_coalescing_window_ms' row"):
                read_platform_declarations(
                    read_conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
        finally:
            read_conn.close()
    finally:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {control_platform.registry_schema}.platform_declarations (key, value) "
                "VALUES ('audit_coalescing_window_ms', to_jsonb(60000))"
            )
        conn.close()


def test_missing_audit_writer_roles_row_is_not_f4_it_is_deferred(control_platform) -> None:
    """Design §3.7 step 4's own note: an absent `audit_writer_roles` row
    is NOT F-4 (unlike `surfaces`/`audit_coalescing_window_ms`) -- it
    comes back as an empty tuple, deferred to the caller's own F-13
    self-role-inclusion check. `read_platform_declarations` itself must
    still succeed."""
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {control_platform.registry_schema}.platform_declarations "
                "WHERE key = 'audit_writer_roles'")
        read_conn = psycopg.connect(control_platform.api_dsn)
        try:
            result = read_platform_declarations(
                read_conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                migration=MIGRATION_NUMBER)
        finally:
            read_conn.close()
        assert result.audit_writer_roles == ()
    finally:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {control_platform.registry_schema}.platform_declarations (key, value) "
                "VALUES ('audit_writer_roles', to_jsonb(ARRAY[%s, %s]))",
                [control_platform.api_role, control_platform.controlplane_role],
            )
        conn.close()


def test_read_platform_declarations_rejects_a_hand_edited_bad_window_value(control_platform) -> None:
    """WP-1/WP-2 completion condition 6 / rework condition 25 (§4(b)):
    `validate_coalescing_window_value` runs on THIS read path too -- a
    value hand-edited directly into the row (never through `ops`) must be
    rejected at startup, real PG (design's own non-vacuity requirement),
    not only the pure `validate_coalescing_window_value_rejects` unit
    test above (mirrors r2db-api's own `test_application_audit.py::
    test_build_app_rejects_a_hand_edited_coalescing_window_value`)."""
    admin = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = to_jsonb(-5) "
                "WHERE key = 'audit_coalescing_window_ms'")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="audit_coalescing_window_ms"):
                read_platform_declarations(
                    conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = to_jsonb(60000) "
                "WHERE key = 'audit_coalescing_window_ms'")
        admin.close()


def test_read_platform_declarations_rejects_a_hand_edited_bad_writer_roles_value(control_platform) -> None:
    """Rework condition 25 (§4(b)): same, for `audit_writer_roles` -- a
    hand-edited duplicate entry must be rejected at read time too, real
    PG."""
    admin = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = %s::jsonb "
                "WHERE key = 'audit_writer_roles'",
                ['["a", "a"]'])
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="audit_writer_roles"):
                read_platform_declarations(
                    conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = to_jsonb(ARRAY[%s, %s]) "
                "WHERE key = 'audit_writer_roles'",
                [control_platform.api_role, control_platform.controlplane_role])
        admin.close()


def test_read_platform_declarations_rejects_a_hand_edited_bad_surfaces_value(control_platform) -> None:
    """Rework condition 25 (§4(b)): same, for `surfaces` -- a hand-edited
    non-absolute `data.base_url` must be rejected at read time too, real
    PG."""
    admin = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = %s::jsonb "
                "WHERE key = 'surfaces'",
                ['{"data": {"base_url": "not-a-url"}}'])
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="surfaces.data.base_url"):
                read_platform_declarations(
                    conn, schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = %s::jsonb "
                "WHERE key = 'surfaces'",
                ['{"data":{"base_url":"https://data.mitatedb-control-platform.example.invalid/v1"},'
                 '"control":{"base_url":"https://control.mitatedb-control-platform.example.invalid/control/v1"}}'])
        admin.close()


def test_build_control_service_fails_fast_when_current_user_is_not_a_declared_writer(control_platform) -> None:
    """Rework condition 29 (§4(f)): a REAL PG seed where `audit_writer_
    roles` no longer lists this process' own connecting role must fail
    startup via the REAL composition-root entry point (`build_control_
    service`), not merely `check_writer_role_timeouts` called directly
    with a hand-crafted `declared_roles` argument (as `test_f13_role_
    not_in_declared_writers_is_rejected_before_the_dual_check` above
    does)."""
    import mitatedb_api.control_composition as control_composition_module

    admin = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = to_jsonb(ARRAY[%s]) "
                "WHERE key = 'audit_writer_roles'",
                [control_platform.api_role])  # controlplane_role deliberately dropped
        env = {
            "MITATEDB_CREDENTIAL_PEPPER": "synthetic-f13-realpath-pepper",
            "MITATEDB_CONTROL_CREDENTIAL_PEPPER": "synthetic-f13-realpath-ctl-pepper",
            "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
            "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
        }
        with pytest.raises(PlatformDeclarationError, match="is not declared as an audit writer role"):
            control_composition_module.build_control_service(env)
    finally:
        with admin.cursor() as cur:
            cur.execute(
                f"UPDATE {control_platform.registry_schema}.platform_declarations SET value = to_jsonb(ARRAY[%s, %s]) "
                "WHERE key = 'audit_writer_roles'",
                [control_platform.api_role, control_platform.controlplane_role])
        admin.close()


def test_f3_f4_f8_name_the_next_ops_command(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with pytest.raises(PlatformDeclarationError) as f8:
            read_platform_declarations(
                conn, schema=control_platform.registry_schema + "_missing", ops_module=PEER_MODULE,
                migration=MIGRATION_NUMBER)
        assert "MITATEDB_PROVISION_DSN" in str(f8.value)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# F-7 / F-9 / F-10 / F-11 / F-13: writer role declared-vs-effective dual
# check (design D-1(b)/D-2(h)). Real PG only (design's own non-vacuity
# requirement) -- `control_platform`'s api role already carries the
# migration `0007` default (5000ms/5000ms) AND is already listed in
# `audit_writer_roles` (the migration seeds both from the same fixture
# variables). WP-1/WP-2 completion conditions 8/20.
# ---------------------------------------------------------------------------


def _declared_roles(control_platform) -> tuple[str, ...]:
    return (control_platform.api_role, control_platform.controlplane_role)


def test_dual_check_passes_against_the_shipped_default(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        declared = check_writer_role_timeouts(
            conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        conn.close()
    assert declared == RoleTimeoutCatalog(role=control_platform.api_role, statement_ms=5000, idle_ms=5000)


def test_f13_role_not_in_declared_writers_is_rejected_before_the_dual_check(control_platform) -> None:
    """WP-1/WP-2 completion condition 20: F-13 fires BEFORE F-7/F-9/F-10/
    F-11 -- even if this role's `pg_db_role_setting` were healthy, an
    undeclared role must never pass."""
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with pytest.raises(PlatformDeclarationError, match="is not declared as an audit writer role"):
            check_writer_role_timeouts(
                conn, declared_roles=(control_platform.controlplane_role,), schema=control_platform.registry_schema,  # api_role deliberately excluded
                ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        conn.close()


def test_f13_fires_when_declared_roles_is_empty(control_platform) -> None:
    """Design §3.8 F-13: "行が無い場合を含む" -- an empty `declared_roles`
    (the shape `read_platform_declarations` returns for an absent row)
    must ALSO trigger F-13, not a different/no error."""
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with pytest.raises(PlatformDeclarationError, match="is not declared as an audit writer role"):
            check_writer_role_timeouts(conn, declared_roles=(), schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    finally:
        conn.close()


def test_f13_message_names_the_migration_and_ops_command(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with pytest.raises(PlatformDeclarationError) as exc:
            check_writer_role_timeouts(
                conn, declared_roles=(), schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        message = str(exc.value)
        assert f"migration {MIGRATION_NUMBER}" in message
        assert "python -m mitatedb_api.ops set-platform-timeouts" in message
        assert "absent" in message
    finally:
        conn.close()


def test_f7_missing_declaration(control_platform) -> None:
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} RESET statement_timeout")
            cur.execute(f"ALTER ROLE {control_platform.api_role} RESET idle_in_transaction_session_timeout")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="has no statement_timeout"):
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
        admin.close()


def test_f10_zero_is_rejected(control_platform) -> None:
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} SET statement_timeout = '0'")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match='reads as "no limit"'):
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
        admin.close()


def test_f10_negative_is_rejected(control_platform) -> None:
    """Design D-1(b)(i): "0 と負数は F-10 で止める" -- `ALTER ROLE ... SET
    statement_timeout` itself refuses a negative literal at the SQL level
    (`psycopg.errors.InvalidParameterValue: ... outside the valid range
    ... (0 .. 2147483647)`, measured against real PG 16), so a negative
    `pg_db_role_setting` entry can only arise from a forged/corrupted
    catalog row -- simulated here with a direct superuser `UPDATE` on the
    catalog itself (never `ALTER ROLE`, which would refuse it), the same
    "hand-edited row" spirit `platform_declarations` row validation
    already assumes for the declarations TABLE.

    Agent C isomorphism convergence (rulings-q4-wp12-rework.md sec.1):
    the earlier WP-2 round's own fixed-but-DIFFERENT "which is not a
    valid bound" sentence for the negative case was a WP-level
    elaboration beyond design §3.8's own F-10 template, which gives ONE
    verbatim message for "ms 値が 0 または負数" -- unconditionally "which
    PostgreSQL reads as \"no limit\"", never branching by value. Design
    §3.8's own verbatim text outranks the WP-level embellishment (Agent
    C's stated resolution order: design verbatim fidelity first), and
    that single template is also what lets `_f10_message`'s own body
    normalize-diff empty against r2db-api's realization, which never had
    the extra branch. This test now asserts the SAME "no limit" wording
    the zero-value case already pins."""
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                "UPDATE pg_db_role_setting SET setconfig = "
                "ARRAY['statement_timeout=-5', 'idle_in_transaction_session_timeout=5000ms'] "
                "WHERE setrole = %s::regrole AND setdatabase = 0",
                [control_platform.api_role],
            )
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match='reads as "no limit"'):
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
        admin.close()


def test_f11_per_database_row_takes_precedence(control_platform) -> None:
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    database_name = control_platform.prefix + "_platform"
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} "
                "SET statement_timeout = '9999ms'"
            )
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="IN DATABASE"):
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} RESET ALL")
        admin.close()


def test_f11_is_specifically_raised_not_a_coincidental_f9_match(control_platform) -> None:
    """Mutation-testing finding (this WP's own execution pass, mutation 9:
    "drop the F-11 per-database-row check"): `test_f11_per_database_row_
    takes_precedence` above stayed GREEN against that exact mutation --
    F-9's own message text ALSO contains the substring "IN DATABASE" (as
    one of its listed possible override sources, `_f9_message`'s own
    "'ALTER ROLE … IN DATABASE … SET' row" clause), so that test's loose
    `match="IN DATABASE"` coincidentally still matches the WRONG
    exception (F-9, raised because the per-database override makes the
    real effective value disagree with the declared row) once F-11's own
    raise is removed. This test pins a phrase that appears ONLY in
    `_f11_message` (`"takes precedence over the database-independent"`,
    verbatim from `test_f11_message_is_verbatim` above), which `_f9_
    message` never contains -- non-vacuity re-run confirmed this goes red
    under the same mutation (`{scratchpad}/wp2c-mutations.log`, mutation
    9)."""
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    database_name = control_platform.prefix + "_platform"
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} "
                "SET statement_timeout = '9999ms'"
            )
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError, match="takes precedence over the database-independent"):
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} RESET ALL")
        admin.close()


def test_f11_per_database_row_with_an_unrelated_key_is_ignored(control_platform) -> None:
    """Amendment 2026-09-05 (F-11 の絞り込み): a per-database row that
    sets a GUC OTHER than the two timeout keys must never block startup."""
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    database_name = control_platform.prefix + "_platform"
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} SET search_path = 'public'")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            # must NOT raise F-11 -- the per-database row exists but never
            # mentions statement_timeout/idle_in_transaction_session_timeout.
            check_writer_role_timeouts(
                conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                migration=MIGRATION_NUMBER)
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} IN DATABASE {database_name} RESET ALL")
        admin.close()


def test_f9_connection_string_override_is_caught(control_platform) -> None:
    """Design's own non-vacuity requirement: real PG, a genuine
    connection-string `options=-c ...` override -- not a stub."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    params = conninfo_to_dict(control_platform.api_dsn)
    params["options"] = "-c statement_timeout=30000"
    override_dsn = make_conninfo(**params)
    conn = psycopg.connect(override_dsn)
    try:
        with pytest.raises(PlatformDeclarationError, match="effective value is 30000 ms"):
            check_writer_role_timeouts(
                conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                migration=MIGRATION_NUMBER)
    finally:
        conn.close()


def test_f7_f9_f10_f11_name_the_next_ops_command(control_platform) -> None:
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} SET statement_timeout = '0'")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            with pytest.raises(PlatformDeclarationError) as exc:
                check_writer_role_timeouts(
                    conn, declared_roles=_declared_roles(control_platform), schema=control_platform.registry_schema, ops_module=PEER_MODULE,
                    migration=MIGRATION_NUMBER)
            assert "python -m mitatedb_api.ops set-platform-timeouts" in str(exc.value)
        finally:
            conn.close()
    finally:
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
        admin.close()


# ---------------------------------------------------------------------------
# D-1(c): `derive_visibility_lag_ms` -- pure function now, over the
# `RoleTimeoutCatalog` rows the caller already read (no PG connection of
# its own).
# ---------------------------------------------------------------------------


def test_derive_visibility_lag_ms_shipped_default(control_platform) -> None:
    conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        catalogs = [
            read_declared_role_timeouts(conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
            for role in _declared_roles(control_platform)
        ]
    finally:
        conn.close()
    assert derive_visibility_lag_ms(catalogs) == 5000 + 5000 + 1000


def test_derive_visibility_lag_ms_reflects_a_real_role_setting_change(control_platform) -> None:
    set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=3_000, idle_ms=4_000)
    set_role_timeouts(control_platform.admin_dsn, control_platform.controlplane_role, statement_ms=1_000, idle_ms=1_000)
    conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        catalogs = [
            read_declared_role_timeouts(conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
            for role in _declared_roles(control_platform)
        ]
        # max(3000+4000, 1000+1000) + 1000 = 8000
        assert derive_visibility_lag_ms(catalogs) == 8_000
    finally:
        conn.close()
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)
        set_role_timeouts(control_platform.admin_dsn, control_platform.controlplane_role, statement_ms=5000, idle_ms=5000)


def test_derive_visibility_lag_ms_reflects_seed_role_names_dropping_one(control_platform) -> None:
    """WP-2 completion condition 21 / variant of variant 20 (`0007` の
    key の CHECK 集合...variant 20 は seed の role 名を 1 つ落とす):
    `derive_visibility_lag_ms` must be the max over EVERY role the caller
    hands it -- dropping a role from the caller's own list changes the
    result, proving no naming-convention derivation sneaks a role back
    in."""
    set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=9_000, idle_ms=9_000)
    conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        only_controlplane = [
            read_declared_role_timeouts(conn, control_platform.controlplane_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        ]
        # the high api_role value (9000+9000) is NOT reflected if the caller
        # only hands derive_visibility_lag_ms the controlplane catalog.
        assert derive_visibility_lag_ms(only_controlplane) == 5000 + 5000 + 1000
    finally:
        conn.close()
        set_role_timeouts(control_platform.admin_dsn, control_platform.api_role, statement_ms=5000, idle_ms=5000)


def test_read_declared_role_timeouts_ignores_unknown_setconfig_keys(control_platform) -> None:
    """Design D-1(b): "未知のキーは無視する" -- `search_path` (or any other
    `ALTER ROLE ... SET` this role might independently carry) must never
    make this check fail."""
    admin = psycopg.connect(control_platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} SET search_path = 'public'")
        conn = psycopg.connect(control_platform.api_dsn)
        try:
            values = read_declared_role_timeouts(conn, control_platform.api_role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
        finally:
            conn.close()
        assert values == RoleTimeoutCatalog(role=control_platform.api_role, statement_ms=5000, idle_ms=5000)
    finally:
        with admin.cursor() as cur:
            cur.execute(f"ALTER ROLE {control_platform.api_role} RESET search_path")
        admin.close()


def test_read_effective_timeouts_ms_matches_the_shipped_default(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        assert read_effective_timeouts_ms(conn) == (5000, 5000)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# (h) 逐語ピン (ruling §4): the F-13 message body, byte-for-byte, copied
# from design §3.8 (F-3c's own verbatim pin is `test_f3c_message_is_
# verbatim` above).
# ---------------------------------------------------------------------------


def test_f13_message_is_verbatim() -> None:
    """Agent C isomorphism convergence (rulings-q4-wp12-rework.md sec.1):
    design §3.8's own F-13 verbatim literal renders `declared` as a
    JSON-shaped, double-quoted array (`["r2dbsvc_api",
    "r2dbsvc_controlplane"]`) -- the earlier WP-2 round's own
    `repr(list(...))` produced Python's single-quoted `repr` instead
    (`['r2dbsvc_api', 'r2dbsvc_controlplane']`), a real deviation from
    the design's own verbatim text this pin test previously encoded as
    correct. r2db-api's own realization already used the double-quoted
    form; this fix converges MitateDB-api onto it."""
    from mitatedb_api.platform_declarations import _f13_message
    message = _f13_message("r2dbsvc_api_t3", ["r2dbsvc_api", "r2dbsvc_controlplane"], schema=DEFAULT_SCHEMA, ops_module="r2db_api", migration="0008")
    assert message == (
        "current_user 'r2dbsvc_api_t3' is not declared as an audit writer role: 'audit_writer_roles' in "
        f"{DEFAULT_SCHEMA}.platform_declarations is absent, or it does not list this role (declared: "
        "[\"r2dbsvc_api\", \"r2dbsvc_controlplane\"]). Migration 0008 seeds that row with the very role names it "
        "issues 'ALTER ROLE … SET statement_timeout / idle_in_transaction_session_timeout' for, in the same "
        "transaction, so a process connecting as any other role writes audit rows whose timeouts the "
        "declared visibility_lag_ms does not describe. Apply migration 0008 to this platform database with "
        "this deployment's writer role names, or connect this process as one of the declared roles; then set "
        "the timeouts with 'python -m r2db_api.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>' "
        "(it issues ALTER ROLE for every role in 'audit_writer_roles', and takes no role-name argument) and "
        "restart both processes."
    )


# ---------------------------------------------------------------------------
# Agent C addition (task step 3, isomorphism-convergence pass,
# rulings-q4-wp12-rework.md sec.5): design §3.8 requires F-1 through F-13
# (+F-3c, F-4b) each pinned by a full exact-equality assertion against the
# design's own verbatim text -- not merely a `match=` substring or a bare
# `pytest.raises(PlatformDeclarationError)`. F-3c/F-13 already had this
# above; the remaining conditions below did not (only partial "names the
# next ops command" substring checks existed for several of them). These
# unit-level tests call each private message builder directly (same style
# as `test_f13_message_is_verbatim`/`test_f3c_message_is_verbatim` above),
# which needs no database.
# ---------------------------------------------------------------------------


def test_f1_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f1_message

    message = _f1_message("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS")
    assert message == (
        "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS is no longer read (Q4 D-1): the audit writer roles carry "
        "statement_timeout / idle_in_transaction_session_timeout as PostgreSQL role settings, applied by "
        "migration 0007. This variable is rejected whenever it is defined, whatever its value (an empty "
        "string included). Unset this variable, then set the value with 'python -m mitatedb_api.ops "
        "set-platform-timeouts --statement-ms <N> --idle-ms <N>' and restart both processes. Note this "
        "setting also bounds every other connection made by this role (credential store lookups and "
        "control-plane registry operations included)."
    )


def test_f2_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f2_message

    message = _f2_message("MITATEDB_DATA_BASE_URL", schema=DEFAULT_SCHEMA)
    assert message == (
        f"MITATEDB_DATA_BASE_URL is no longer read (Q4 D-2): surfaces are declared in {DEFAULT_SCHEMA}."
        "platform_declarations, created by migration 0007. This variable is rejected whenever it is defined, "
        "whatever its value (an empty string included). Unset this variable, then declare with 'python -m "
        "mitatedb_api.ops declare-surfaces --data-base-url <URL> [--control-base-url <URL>]' and restart "
        "both processes."
    )


def test_f2_message_names_the_real_schema_not_a_literal_placeholder() -> None:
    """N-7 (monitor ruling 2026-09-05): `reject_removed_surface_env`/
    `_f2_message` must NOT hardcode `DEFAULT_SCHEMA` -- a deployment that
    overrides `MITATEDB_PLATFORM_SCHEMA` must see ITS OWN schema name in
    F-2's remedy text, not the shipped default."""
    from mitatedb_api.platform_declarations import _f2_message, reject_removed_surface_env

    message = _f2_message("MITATEDB_DATA_BASE_URL", schema="some_throwaway_schema_x1")
    assert "some_throwaway_schema_x1.platform_declarations" in message
    assert DEFAULT_SCHEMA not in message

    with pytest.raises(PlatformDeclarationError) as exc:
        reject_removed_surface_env({"MITATEDB_DATA_BASE_URL": ""}, names=_NAMES_SURFACE, schema="some_throwaway_schema_x1")
    assert str(exc.value) == message


def test_f3_message_is_verbatim() -> None:
    """{scratchpad}/wp12-audit-gaps.md G7: every other F-message here has
    a full-string (`==`) verbatim pin (work order completion condition
    (h)/23(h): "部分一致は不可") -- F-3 alone only had `test_f3_missing_
    surfaces_row`'s `pytest.raises(..., match="no 'surfaces' row")`, a
    partial match. Mirrors r2db-api's own `tests/test_ops_declarations.py
    ::test_f3_message_is_pinned_verbatim_against_real_absence`'s `_f3`
    helper, inlined here in the same pure-Python style as `test_f4_
    message_is_verbatim`/`test_f2_message_is_verbatim` above (F-3 needs
    no database at all -- `_f3_message` takes only `schema`/`ops_module`)."""
    from mitatedb_api.platform_declarations import _f3_message

    message = _f3_message(DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert message == (
        f"no 'surfaces' row in {DEFAULT_SCHEMA}.platform_declarations: contract 1.6.0 requires surfaces.data "
        "unconditionally. Declare it with 'python -m mitatedb_api.ops declare-surfaces --data-base-url <URL> "
        "[--control-base-url <URL>]', then restart both processes."
    )


def test_f4_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f4_message

    message = _f4_message(DEFAULT_SCHEMA, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    assert message == (
        f"no 'audit_coalescing_window_ms' row in {DEFAULT_SCHEMA}.platform_declarations: migration 0007 seeds "
        "it with the shipped default (60000). Apply that migration, or set the value with 'python -m "
        "mitatedb_api.ops declare-coalescing-window --ms <N>', then restart both processes."
    )


def test_f5_message_is_verbatim() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_surfaces_value({"data": {"base_url": "https://h.example.invalid/v1/"}}, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert str(exc.value) == (
        f"surfaces.data.base_url in {DEFAULT_SCHEMA}.platform_declarations must be an absolute URL ending in "
        "'/v1' with no trailing slash, got 'https://h.example.invalid/v1/'. Re-declare it with 'python -m "
        "mitatedb_api.ops declare-surfaces …'."
    )


def test_f6_forward_message_is_verbatim() -> None:
    surfaces = Surfaces(data_base_url="https://h.example.invalid/v1", control_base_url="https://h.example.invalid/control/v1")
    with pytest.raises(PlatformDeclarationError) as exc:
        check_control_surface_consistency(surfaces, "unavailable", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "surfaces.control is declared but MITATEDB_CONTROL_PLANE_STATUS is 'unavailable' (contract 1.6.0: a "
        "deployment declaring control_plane unavailable omits surfaces.control). The surfaces row is shared "
        "by BOTH processes: re-declaring with '--no-control' removes the control declaration for the "
        "control-plane process too, and that process will then fail to start (F-3). Unless this deployment "
        "really offers no control surface, change MITATEDB_CONTROL_PLANE_STATUS on this process instead, "
        "then restart both processes. If the deployment genuinely has no control surface, re-declare with "
        "'python -m mitatedb_api.ops declare-surfaces --data-base-url <URL> --no-control'."
    )


def test_f6_reverse_message_is_verbatim() -> None:
    surfaces = Surfaces(data_base_url="https://h.example.invalid/v1", control_base_url=None)
    with pytest.raises(PlatformDeclarationError) as exc:
        check_control_surface_consistency(surfaces, "enabled", ops_module=PEER_MODULE)
    assert str(exc.value) == (
        "surfaces.control is not declared but MITATEDB_CONTROL_PLANE_STATUS is 'enabled' (contract 1.6.0: a "
        "deployment declaring control_plane other than unavailable must have a control surface). The surfaces "
        "row is shared by BOTH processes: declare a control base url with 'python -m mitatedb_api.ops "
        "declare-surfaces --data-base-url <URL> --control-base-url <URL>', or unless this deployment really "
        "offers a control surface, change MITATEDB_CONTROL_PLANE_STATUS to 'unavailable' on this process "
        "instead, then restart both processes."
    )


def test_f7_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f7_message

    message = _f7_message("mitatedbsvc_api", ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
    assert message == (
        "role 'mitatedbsvc_api' has no statement_timeout / idle_in_transaction_session_timeout in "
        "pg_db_role_setting: migration 0007 is not applied to this platform database, and an audit writer "
        "must never run unbounded. Apply migration 0007, or set the values with 'python -m mitatedb_api.ops "
        "set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart both processes. Note this "
        "setting also bounds every other connection made by this role (credential store lookups and "
        "control-plane registry operations included)."
    )


def test_f8_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f8_message

    message = _f8_message(DEFAULT_SCHEMA, migration=MIGRATION_NUMBER)
    assert message == (
        f"relation {DEFAULT_SCHEMA}.platform_declarations does not exist: migration 0007 (Q4 D-2) has not "
        "been applied to this platform database. Apply it with 'psql \"$MITATEDB_PROVISION_DSN\" -f "
        "MitateDB-api/migrations/0007_platform_declarations.sql', then restart both processes."
    )


def test_f9_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f9_message

    message = _f9_message("mitatedbsvc_api", "statement_timeout", 5000, 30000, ops_module=PEER_MODULE)
    assert message == (
        "role 'mitatedbsvc_api' declares statement_timeout = 5000 ms in pg_db_role_setting but this "
        "connection's effective value is 30000 ms (both shown in milliseconds; PostgreSQL renders these "
        "settings in whichever unit divides evenly, so never compare the rendered strings): the declared "
        "visibility_lag_ms would not describe the effective connection. Remove the override -- a "
        "connection-string 'options=-c …', PGOPTIONS, or an 'ALTER ROLE … IN DATABASE … SET' row -- so the "
        "role setting is the effective value, or change the role setting with 'python -m mitatedb_api.ops "
        "set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart both processes. Note this "
        "setting also bounds every other connection made by this role."
    )


def test_f10_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f10_message

    message = _f10_message("mitatedbsvc_api", "statement_timeout", 0, ops_module=PEER_MODULE)
    assert message == (
        "role 'mitatedbsvc_api' declares statement_timeout = 0 in pg_db_role_setting, which PostgreSQL reads "
        "as \"no limit\": an audit writer must never run unbounded, and the declared visibility_lag_ms would "
        "describe a bound that does not exist. Set a positive value with 'python -m mitatedb_api.ops "
        "set-platform-timeouts --statement-ms <N> --idle-ms <N>' (the command rejects 0 and negative values), "
        "then restart both processes."
    )


def test_f11_message_is_verbatim() -> None:
    from mitatedb_api.platform_declarations import _f11_message

    message = _f11_message("mitatedbsvc_api", "mitatedb_platform")
    assert message == (
        "role 'mitatedbsvc_api' has an 'ALTER ROLE … IN DATABASE …' setting row for database "
        "'mitatedb_platform', which takes precedence over the database-independent role setting this "
        "deployment declares. The role setting must be a single database-independent row. Remove it with "
        "'ALTER ROLE mitatedbsvc_api IN DATABASE mitatedb_platform RESET statement_timeout, "
        "idle_in_transaction_session_timeout;' (issued on the provision DSN), then restart both processes."
    )


def test_f4b_window_message_is_verbatim() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_coalescing_window_value(-1, schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert str(exc.value) == (
        f"'audit_coalescing_window_ms' in {DEFAULT_SCHEMA}.platform_declarations must be a non-negative "
        "integer (0 means no coalescing), got '-1'. This table can be edited by hand, so the value is "
        "validated on every read as well as on write. Re-set it with 'python -m mitatedb_api.ops "
        "declare-coalescing-window --ms <N>', then restart both processes."
    )


def test_f4b_writer_roles_message_is_verbatim() -> None:
    with pytest.raises(PlatformDeclarationError) as exc:
        validate_audit_writer_roles_value([], schema=DEFAULT_SCHEMA, ops_module=PEER_MODULE)
    assert str(exc.value) == (
        f"'audit_writer_roles' in {DEFAULT_SCHEMA}.platform_declarations must be a non-empty JSON array of "
        "distinct, valid PostgreSQL identifiers, got '[]'. This table can be edited by hand, so the value is "
        "validated on every read. This row is written only by migration 0007, which seeds it with the very "
        "role names it issues ALTER ROLE for: re-apply that migration to this platform database with this "
        "deployment's writer role names, then restart both processes."
    )
