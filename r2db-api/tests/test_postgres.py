"""`PostgresCell` (`r2db_api.postgres`) tested against a real PostgreSQL
server -- design D-3/D-4/D-5, §5.3 C-5 ("this work machine has PostgreSQL
16 running; PostgresCell and the provisioning SQL must be verified against
it, not skipped").

Everything this file creates in the cluster -- the control-plane bootstrap
(role + database + registry schema), and every per-application schema/role
it provisions -- is named under one random-per-run prefix
(`r2dbtest_<8 hex chars>_...`) so it can never collide with anything else in
this shared local cluster, and is dropped in a module-scoped fixture
finalizer that runs even if a test fails. Nothing outside that prefix is
ever read, listed, or touched.

The control-plane bootstrap is exercised by actually running the real
`r2db-api/migrations/0001_bootstrap_control_plane.sql` and
`0002_provisioning_functions.sql` files (with `r2dbsvc` textually replaced
by this run's throwaway prefix) through the real `psql` binary, exactly as
an operator would per `r2db-api/docs/`. This is deliberately not a Python
reimplementation of what those files do: it is the actual migration SQL,
proving the runbook's own documented commands work, not a parallel
approximation of them.

If PostgreSQL is not reachable, every test in this module fails loudly
(module-scoped fixture error) naming the DSN that failed -- it does not
skip. A skip would turn "we could not verify this" into "this is allowed",
which is exactly what §5.3 C-5 forbids.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell
from r2db_api.structured import Predicate

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
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
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_postgres.py requires a reachable local PostgreSQL server. "
            f"Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. "
            f"Set {ADMIN_DSN_ENV} to a reachable admin/superuser DSN "
            "(e.g. 'host=/tmp port=5432 dbname=postgres' or "
            "'postgresql://user:pass@example.invalid:5432/postgres' against "
            "the VPS). These tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, platform_db: str, prefix: str) -> None:
    """Drop everything this run created: the platform database (which takes
    every schema/table/grant inside it with it), then every role whose name
    starts with this run's unique prefix (roles are cluster-global objects,
    independent of any one database, so they need their own sweep). Never
    touches any object outside this run's prefix.
    """
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                [platform_db],
            )
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(platform_db)))
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
    prefix = f"r2dbtest{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    platform_db = f"{prefix}_platform"
    registry_schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_migrations")
    rewritten: dict[str, Path] = {}
    for name in ("0001_bootstrap_control_plane.sql", "0002_provisioning_functions.sql"):
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
    except Exception:
        _sweep_prefix(admin_dsn, platform_db, prefix)
        raise

    info = types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        control_role=control_role,
        platform_db=platform_db,
        registry_schema=registry_schema,
    )
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, platform_db, prefix)


def provision_app(platform: types.SimpleNamespace, slug: str) -> types.SimpleNamespace:
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    conn = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT {}.provision_application(%s, %s, %s)").format(sql.Identifier(platform.registry_schema)),
                [slug, runtime_password, developer_password],
            )
    finally:
        conn.close()
    schema = f"{platform.prefix}_app_{slug}"
    runtime_role = f"{schema}_runtime"
    developer_role = f"{schema}_developer"
    return types.SimpleNamespace(
        slug=slug,
        schema=schema,
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=platform.platform_db),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=platform.platform_db),
    )


def deprovision_app(platform: types.SimpleNamespace, slug: str) -> None:
    conn = psycopg.connect(platform.control_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT {}.deprovision_application(%s)").format(sql.Identifier(platform.registry_schema)), [slug])
    finally:
        conn.close()


def make_cell(app: types.SimpleNamespace, *, pool_size: int = 2) -> PostgresCell:
    return PostgresCell(
        app.slug,
        app.schema,
        runtime_dsn=app.runtime_dsn,
        developer_dsn=app.developer_dsn,
        runtime_role=app.runtime_role,
        developer_role=app.developer_role,
        pool_size=pool_size,
    )


@pytest.fixture
def app_a(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "iso_a")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_a")


@pytest.fixture
def app_b(platform: types.SimpleNamespace) -> Iterator[types.SimpleNamespace]:
    app = provision_app(platform, "iso_b")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_b")


LIMITS = ResourceLimits()


def P(field: str, operator: str, value: object = None) -> Predicate:
    """`PostgresCell.query`'s `where` parameter, per the `StorageBackend`
    protocol, is `list[Predicate]` -- already parsed. In the real request
    path `DataService.query` does that parsing (`parse_predicate`) before
    ever calling the cell; these tests call `PostgresCell` directly, so they
    do that same parsing step themselves rather than passing raw dicts.
    """
    return Predicate(field=field, operator=operator, value=value)


# --- cross-application isolation, verified at the database level ----------


def test_cross_application_isolation_at_database_level(app_a: types.SimpleNamespace, app_b: types.SimpleNamespace) -> None:
    cell_a = make_cell(app_a)
    try:
        cell_a.apply_schema({"operation": "create_entity", "entity": "secrets", "fields": ["value"]}, developer=True, limits=LIMITS)
        cell_a.transact("secrets", [{"operation": "insert", "values": {"value": "app-a-only"}}], LIMITS)
    finally:
        cell_a.close()

    # B's own runtime role, connecting directly (not through PostgresCell,
    # per Task 4: "verify at the database level, not just the application
    # level") must be unable to even see A's table exists, let alone read
    # its rows -- there is no grant anywhere naming B's role on A's schema.
    b_conn = psycopg.connect(app_b.runtime_dsn, autocommit=True)
    try:
        with b_conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                [app_a.schema, "secrets"],
            )
            assert cur.fetchall() == []

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(app_a.schema), sql.Identifier("secrets")))
    finally:
        b_conn.rollback()
        b_conn.close()

    # And B's developer role -- elevated within its *own* schema -- fares no
    # better against A's schema: developer authority does not generalize
    # across applications (SI-00/SI-01).
    b_dev_conn = psycopg.connect(app_b.developer_dsn, autocommit=True)
    try:
        with b_dev_conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(app_a.schema), sql.Identifier("secrets")))
    finally:
        b_dev_conn.rollback()
        b_dev_conn.close()

    # The application-level path agrees: B's own PostgresCell simply does
    # not know "secrets" exists (it is not in B's catalog at all).
    cell_b = make_cell(app_b)
    try:
        assert cell_b.catalog() == []
        with pytest.raises(FoundationError) as exc:
            cell_b.query("secrets", select=["value"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell_b.close()


def test_row_level_security_is_enabled_and_forced_on_created_tables(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name"]}, developer=True, limits=LIMITS)
    finally:
        cell.close()
    # Must connect to the platform database itself (not the bootstrap
    # `_admin_dsn()`, which points at `postgres`) to see this table's
    # catalog row at all.
    admin = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s",
                [app_a.schema, "widgets"],
            )
            row = cur.fetchone()
            assert row == (True, True)
    finally:
        admin.close()


# --- runtime cannot perform DDL, verified at the database level -----------


def test_runtime_role_cannot_perform_ddl(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
    finally:
        cell.close()

    conn = psycopg.connect(app_a.runtime_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("CREATE TABLE {}.{} (x INT)").format(sql.Identifier(app_a.schema), sql.Identifier("sneaky")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("ALTER TABLE {}.{} ADD COLUMN sneaky INT").format(sql.Identifier(app_a.schema), sql.Identifier("items")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("DROP TABLE {}.{}").format(sql.Identifier(app_a.schema), sql.Identifier("items")))
    finally:
        conn.rollback()
        conn.close()

    # The application-level path is consistent with this: PostgresCell
    # itself refuses to even attempt DDL for a non-developer caller, before
    # any SQL is sent (design D-1's shared `bind_schema_operation`).
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "should_not_exist", "fields": []}, developer=False, limits=LIMITS)
        assert exc.value.code == "FORBIDDEN"
    finally:
        cell.close()


# --- injection payloads: identifier positions rejected --------------------

# This corpus intentionally mirrors the categorized coverage in
# `conformance-tests/payloads.py` (`IDENTIFIER_PAYLOAD_CATEGORIES`) rather
# than importing it. `conformance-tests` is only on `sys.path` when pytest
# resolves its inifile from the *root* `pyproject.toml`
# (`pythonpath = [..., "conformance-tests"]`, `testpaths` covering all three
# suites). Invoke pytest directly against this file or this package instead
# -- e.g. `pytest r2db-api/tests/test_postgres.py` -- and pytest's rootdir
# search finds `r2db-api/pyproject.toml` first (it also declares
# `[tool.pytest.ini_options]`), whose `pythonpath` is only `["src"]`;
# confirmed empirically (`pytest --collect-only` from the two starting
# points resolves two different inifiles). Importing `payloads` here would
# make this file's collectability depend on the invoking directory, which
# is exactly the fragility this suite should not have, so the categories
# are reproduced locally instead.
#
# Two categories from that corpus are deliberately not reproduced: an
# embedded NUL byte (`embedded_nul`) makes psycopg itself raise
# `DataError` on any parameter carrying it -- including the plain
# `information_schema` verification queries these tests run -- before the
# payload ever reaches `structured.validate_identifier`, so it cannot
# exercise the DDL path this file is adding coverage for; and an empty
# string (`empty_string`) is a PostgreSQL *parser* error ("zero-length
# delimited identifier") once quoted, not an outcome the identifier
# validator controls, so it would not cleanly prove "no side effect" the
# way every other payload below does (verified empirically: every payload
# below, and only these two, behave differently under a bypassed
# validator).
IDENTIFIER_INJECTION_PAYLOADS: list[tuple[str, str]] = [
    ("statement_terminator", "items; DROP TABLE items; --"),
    ("quote_escape_double_then_statement", '"; DROP TABLE items; --'),
    ("quote_escape_single_then_comment", "items'--"),
    ("quote_escape_double", "items\""),
    ("path_traversal", "../items"),
    ("tautology_bare", "items OR 1=1"),
    ("comment_dash", "items--"),
    ("comment_block", "items/*comment*/"),
    ("tautology_quoted", "' OR '1'='1"),
    ("identifier_quote_backtick", "`items`"),
    ("identifier_quote_bracket", "[items]"),
    ("embedded_newline", "items\nname"),
    ("embedded_whitespace", "items name"),
    ("qualified_name", "a.b"),
    ("wildcard", "*"),
    ("starts_with_digit", "1items"),
    ("long_string", "a" * 300),
    ("non_ascii", "usérs"),
    ("fullwidth", "ユーザー"),
]
IDENTIFIER_INJECTION_PAYLOAD_VALUES = [payload for _, payload in IDENTIFIER_INJECTION_PAYLOADS]
IDENTIFIER_INJECTION_PAYLOAD_IDS = [name for name, _ in IDENTIFIER_INJECTION_PAYLOADS]


_REVISION_TABLE = "_r2db_schema_revision"  # provisioned by
# `r2db-api/migrations/0002_provisioning_functions.sql` for every
# application schema, independent of anything these tests create --
# excluded below the same way `PostgresCell._load_catalog` excludes it, so
# it does not read as a false "something was created" side effect.


def _real_table_names(dsn: str, schema: str) -> set[str]:
    """The live set of base-table names PostgreSQL itself reports for
    `schema`, queried independently of `PostgresCell.catalog()` -- so a bug
    in `catalog()`'s own filtering could never hide a table that a broken
    identifier validator let through onto the DDL path.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE' AND table_name <> %s",
                [schema, _REVISION_TABLE],
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _real_column_names(dsn: str, schema: str, table: str) -> set[str]:
    """The live set of column names PostgreSQL itself reports for
    `schema.table`, queried independently of `PostgresCell.catalog()` for
    the same reason as `_real_table_names` above.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
                [schema, table],
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


@pytest.mark.parametrize("entity", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payloads_in_identifier_positions_are_rejected(app_a: types.SimpleNamespace, entity: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query(entity, select=["label"], where=[], page_size=10, limits=LIMITS)
        # Tightened per the mutation finding that motivated this change:
        # every payload in this corpus is, by construction, syntactically
        # invalid under the contract's identifier pattern, so acceptance of
        # `NOT_FOUND` alongside `IDENTIFIER_INVALID` here (as this
        # assertion used to read) made the test pass identically whether
        # the shared syntax validator ran at all or was replaced with
        # `^.*$` -- PostgresCell's catalog check produces `NOT_FOUND` for
        # an unknown name either way, so the old assertion could never
        # distinguish "rejected by identifier policy" from "happened not to
        # exist". See `test_syntactically_valid_but_nonexistent_identifier_
        # is_not_found` below for the legitimately-`NOT_FOUND` case this is
        # now distinguishable from.
        assert exc.value.code == "IDENTIFIER_INVALID"
        # No side effect: the legitimate table is still there, untouched.
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


def test_syntactically_valid_but_nonexistent_identifier_is_not_found(app_a: types.SimpleNamespace) -> None:
    """The counterpart to the tightened assertion above: a name that *is* a
    syntactically valid identifier under the contract's pattern, but simply
    does not exist as an entity, legitimately yields `NOT_FOUND` -- proving
    the two outcomes are actually distinguishable rather than both folded
    into one accepted code set.
    """
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("does_not_exist_but_syntactically_valid", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "NOT_FOUND"
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_a_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.query("items", select=[field_name], where=[], page_size=10, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


# --- injection payloads: DDL identifier positions --------------------------
#
# The read-path tests above pass even with a broken syntax validator
# (proven by the mutation this module's fix responds to: replacing
# `structured.IDENTIFIER` with `re.compile(r"^.*$")` left all of them
# green) because `PostgresCell.query` independently verifies the identifier
# against the live `information_schema` catalog on every read -- an unknown
# name is rejected regardless of whether the syntax validator did anything.
# DDL has no such backstop: `create_entity`'s `entity` and `fields`, and
# `add_field`'s `field`, name objects that do not exist *yet*, by
# definition, so there is no catalog to check them against.
# `structured.bind_schema_operation` -- called before `PostgresCell` opens
# any database connection at all -- is the only guard on this path. Each
# test below was confirmed, via that same mutation, to fail without it:
# with the syntax check disabled, PostgreSQL's own identifier quoting
# (`psycopg.sql.Identifier`) happily creates a real table or column named
# exactly the payload instead of raising anything.


@pytest.mark.parametrize("entity", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_create_entity_name_is_rejected(app_a: types.SimpleNamespace, entity: str) -> None:
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": entity, "fields": ["label"]}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        # Checked against PostgreSQL's own information_schema, not
        # `cell.catalog()`: nothing landed in the database at all, under
        # any name.
        assert _real_table_names(app_a.developer_dsn, app_a.schema) == set()
        assert cell.catalog() == []
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_create_entity_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", field_name]}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        # `bind_schema_operation` validates every field in `fields` up
        # front, before any connection opens, so the whole operation is
        # rejected -- not even the otherwise-legitimate "items" table
        # should exist.
        assert _real_table_names(app_a.developer_dsn, app_a.schema) == set()
        assert cell.catalog() == []
    finally:
        cell.close()


@pytest.mark.parametrize("field_name", IDENTIFIER_INJECTION_PAYLOAD_VALUES, ids=IDENTIFIER_INJECTION_PAYLOAD_IDS)
def test_injection_payload_as_add_field_name_is_rejected(app_a: types.SimpleNamespace, field_name: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "add_field", "entity": "items", "field": field_name}, developer=True, limits=LIMITS)
        assert exc.value.code == "IDENTIFIER_INVALID"
        assert _real_column_names(app_a.developer_dsn, app_a.schema, "items") == {"label"}
        assert cell.catalog() == [{"entity": "items", "fields": ["label"]}]
    finally:
        cell.close()


# --- injection payloads: value positions round-trip byte-equal ------------


@pytest.mark.parametrize(
    "payload",
    [
        "'; DROP TABLE items; --",
        "\" OR \"1\"=\"1",
        "line1\nline2\ttabbed",
        "back\\slash and 'quote' and \"doublequote\"",
        "unicode: éè龍\U0001F600",
        "null-byte-ish: \\x00 not a real null",
        "%s %% percent literal",
    ],
)
def test_injection_payloads_in_value_positions_round_trip_byte_equal(app_a: types.SimpleNamespace, payload: str) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"label": payload}}], LIMITS)
        rows = cell.query("items", select=["label"], where=[P("label", "eq", payload)], page_size=10, limits=LIMITS)
        assert rows == [{"label": payload}]
        # And the table is provably intact -- a real injection would have
        # dropped it.
        assert any(item["entity"] == "items" for item in cell.catalog())
    finally:
        cell.close()


# --- transaction rollback --------------------------------------------------


def test_transaction_rollback_leaves_no_partial_effect(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError):
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "first"}},
                    {"operation": "insert", "values": {"unknown_field": "boom"}},
                ],
                LIMITS,
            )
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == []

        # A destructive operation without confirmation also rolls back
        # anything earlier in the same batch (SI-09 + SI-11 together).
        with pytest.raises(FoundationError) as exc:
            cell.transact(
                "items",
                [
                    {"operation": "insert", "values": {"label": "second"}},
                    {"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "second"}]},
                ],
                LIMITS,
            )
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == []
    finally:
        cell.close()


# --- pool-reset hazard (design D-3) ----------------------------------------


def test_pool_never_leaks_role_or_schema_across_applications(app_a: types.SimpleNamespace, app_b: types.SimpleNamespace) -> None:
    """This project's chosen mitigation for D-3's pool-reset hazard is a
    dedicated per-role connection pool (`r2db_api.postgres._RolePool`) that
    never issues `SET ROLE`/`SET search_path` after connect-time, rather
    than a shared pool with a release-time reset -- see that class's
    docstring for the full reasoning. This test is the executable check: it
    interleaves heavy, repeated use of two different applications' pools and
    asserts every connection drawn from either one reports exactly its own
    fixed role and schema, never the other's, even immediately after the
    other pool was exercised.
    """
    cell_a = make_cell(app_a, pool_size=2)
    cell_b = make_cell(app_b, pool_size=2)
    try:
        for _ in range(20):
            with cell_a._runtime.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false)")
                    user, schemas = cur.fetchone()
                    assert user == app_a.runtime_role
                    assert schemas == [app_a.schema]
                conn.rollback()
            with cell_b._runtime.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false)")
                    user, schemas = cur.fetchone()
                    assert user == app_b.runtime_role
                    assert schemas == [app_b.schema]
                conn.rollback()
            with cell_a._developer.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, current_schemas(false)")
                    user, schemas = cur.fetchone()
                    assert user == app_a.developer_role
                    assert schemas == [app_a.schema]
                conn.rollback()
    finally:
        cell_a.close()
        cell_b.close()


def test_statement_timeout_is_wired_to_resource_limits(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        with cell._runtime.connection() as conn:
            with conn.transaction():
                cell._set_timeouts(conn, 200)
                with conn.cursor() as cur:
                    with pytest.raises(psycopg.errors.QueryCanceled):
                        cur.execute("SELECT pg_sleep(2)")
    finally:
        cell.close()


# --- ordinary correctness: catalog, schema ops, mutation semantics --------


def test_catalog_reflects_entities_and_excludes_internal_bookkeeping_table(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        assert cell.catalog() == []
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["name", "qty"]}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        assert catalog == [{"entity": "widgets", "fields": ["name", "qty"]}]

        cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "color"}, developer=True, limits=LIMITS)
        catalog = cell.catalog()
        assert catalog == [{"entity": "widgets", "fields": ["color", "name", "qty"]}]
    finally:
        cell.close()


def test_schema_revision_increments_and_create_entity_conflict(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        first = cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        second = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "name"}, developer=True, limits=LIMITS)
        assert second == first + 1
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        assert exc.value.code == "CONFLICT"
    finally:
        cell.close()


def test_drop_entity_requires_destructive_confirmation(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": []}, developer=True, limits=LIMITS)
        with pytest.raises(FoundationError) as exc:
            cell.apply_schema({"operation": "drop_entity", "entity": "widgets"}, developer=True, limits=LIMITS)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert any(item["entity"] == "widgets" for item in cell.catalog())
        cell.apply_schema({"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": "DROP_ENTITY"}, developer=True, limits=LIMITS)
        assert cell.catalog() == []
    finally:
        cell.close()


def test_mutation_operations_insert_update_upsert_delete(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "qty"]}, developer=True, limits=LIMITS)
        affected = cell.transact("items", [{"operation": "insert", "values": {"label": "a", "qty": 1}}], LIMITS)
        assert affected == 1
        affected = cell.transact(
            "items",
            [{"operation": "update", "where": [{"field": "label", "operator": "eq", "value": "a"}], "values": {"qty": 2}}],
            LIMITS,
        )
        assert affected == 1
        rows = cell.query("items", select=["qty"], where=[P("label", "eq", "a")], page_size=10, limits=LIMITS)
        assert rows == [{"qty": 2}]

        affected = cell.transact(
            "items",
            [{"operation": "upsert", "where": [{"field": "label", "operator": "eq", "value": "b"}], "values": {"label": "b", "qty": 9}}],
            LIMITS,
        )
        assert affected == 1
        rows = cell.query("items", select=["label", "qty"], where=[P("label", "eq", "b")], page_size=10, limits=LIMITS)
        assert rows == [{"label": "b", "qty": 9}]

        affected = cell.transact(
            "items",
            [{"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "b"}], "destructive": True, "confirmation": "DELETE"}],
            LIMITS,
        )
        assert affected == 1
        rows = cell.query("items", select=["label"], where=[], page_size=10, limits=LIMITS)
        assert rows == [{"label": "a"}]
    finally:
        cell.close()


def test_query_operators_in_and_contains_and_is_null(app_a: types.SimpleNamespace) -> None:
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label", "tag"]}, developer=True, limits=LIMITS)
        cell.transact(
            "items",
            [
                {"operation": "insert", "values": {"label": "alpha", "tag": "x"}},
                {"operation": "insert", "values": {"label": "beta", "tag": "y"}},
                {"operation": "insert", "values": {"label": "gamma"}},
            ],
            LIMITS,
        )
        rows = cell.query("items", select=["label"], where=[P("label", "in", ["alpha", "beta"])], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"alpha", "beta"}

        rows = cell.query("items", select=["label"], where=[P("label", "contains", "et")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"beta"}

        rows = cell.query("items", select=["label"], where=[P("tag", "is_null")], page_size=10, limits=LIMITS)
        assert {r["label"] for r in rows} == {"gamma"}
    finally:
        cell.close()
