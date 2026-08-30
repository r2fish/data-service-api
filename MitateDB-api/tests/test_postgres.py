"""`backend_postgres.PostgresBackend` tested against a real PostgreSQL
server -- design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.1,
R-1/R-2/R-4, WP-1.

Everything this file creates in the cluster -- the platform bootstrap
(provisioning role + platform database + registry schema), and every
per-application *database* + role pair it provisions -- is named under one
random-per-run prefix (`mtdbtest<8 hex chars>`, deliberately a SHORTER and
differently-spelled stem than both r2db-api's own test prefixes
(`r2dbtest`/`r2dbhttp`) and this phase's own future HTTP-adapter prefix
(`mitatedbtest`/`mitatedbhttp`, design R-8) -- so none of the three can
ever collide with each other on a shared local cluster) and is dropped in
a module-scoped fixture finalizer that runs even if a test fails.

The platform bootstrap and per-application provisioning are exercised by
actually running the real `MitateDB-api/migrations/0001_bootstrap_
platform.sql` through `0004_deprovision_application.sql` files (with the
literal token `mitatedb` textually replaced by this run's throwaway
prefix) through the real `psql` binary, exactly as an operator would.
This is deliberately not a Python reimplementation of what those files
do: it is the actual migration SQL, proving the files themselves work,
not a parallel approximation of them.

If PostgreSQL is not reachable, every test in this module fails loudly
(module-scoped fixture error) naming the DSN that failed -- it does not
skip (design R-8's own "skip 禁止" condition, mirroring r2db-api's
`tests/test_postgres.py` identical policy, independently applied here).
"""
from __future__ import annotations

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

from mitatedb_api.auth import Principal, Role
from mitatedb_api.backend_postgres import PostgresBackend, _execute
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, Filter
from mitatedb_api.config import FoundationConfig
from mitatedb_api.errors import (ConflictError, DestructiveConfirmationRequired,
                                 NotFoundError, ValidationError)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"

# R-4 "prefix-anchored sweep + advisory lock": a fixed, arbitrary 63-bit
# advisory-lock key, held only around this module's own enumerate-then-drop
# sweep so two sweeps against the same cluster (e.g. this file's own
# module-scoped teardown racing a stray concurrent run) serialize instead
# of racing each other's `DROP DATABASE`/`DROP ROLE` enumeration.
_SWEEP_LOCK_KEY = 0x4D544442535750  # ASCII "MTDBSWP", arbitrary but stable


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
            "(e.g. 'host=/tmp port=5432 dbname=postgres'). These tests must "
            "not be skipped (design docs/design/"
            "MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-8).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    """Drop everything a run under `prefix` created: every database whose
    name starts with it (the platform database and every per-application
    database), then every role whose name starts with it. Serialized with
    an advisory lock (R-4) so a concurrent sweep against the same cluster
    cannot race this one's own enumerate-then-drop sequence.
    """
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", [_SWEEP_LOCK_KEY])
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
                leftover_databases = [row[0] for row in cur.fetchall()]
                for database in leftover_databases:
                    for attempt in range(5):
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
            with admin.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [_SWEEP_LOCK_KEY])
    finally:
        admin.close()


def _bootstrap_platform(admin_dsn: str, prefix: str, tmp_path_factory: pytest.TempPathFactory):
    """Runs 0001+0002 under `prefix`, sets real passwords on the two
    process roles (0002 deliberately creates them with `PASSWORD NULL` --
    an operator sets one out of band; this test harness IS that operator
    for test purposes), and returns everything a test needs. Raises (does
    not swallow) on failure, after sweeping whatever partially applied.
    """
    provision_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("mitatedb_migrations_" + prefix)
    rewritten: dict[str, Path] = {}
    for name in (
        "0001_bootstrap_platform.sql",
        "0002_registry_and_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
    ):
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
        _run_psql(admin_dsn, rewritten["0001_bootstrap_platform.sql"], {"provision_password": provision_password})
        provision_dsn = _dsn_with(admin_dsn, user=provision_role, password=provision_password, dbname=platform_db)
        _run_psql(provision_dsn, rewritten["0002_registry_and_functions.sql"])
        admin = psycopg.connect(admin_dsn, autocommit=True)
        try:
            # `ALTER ROLE ... PASSWORD` does not accept a server-side bind
            # parameter for the password clause (it is DDL, not DML) --
            # `sql.Literal` composes a safely quoted SQL literal from a
            # Python value at COMPOSITION time (still never raw string
            # concatenation of untrusted input; these two passwords are
            # this test harness's own freshly generated synthetic
            # secrets, not client-controlled data).
            with admin.cursor() as cur:
                _execute(cur, sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(api_role), sql.Literal(api_password)))
                _execute(cur, sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(controlplane_role), sql.Literal(controlplane_password)))
        finally:
            admin.close()
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    return types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        provision_dsn=provision_dsn,
        provision_role=provision_role,
        platform_db=platform_db,
        registry_schema=registry_schema,
        api_dsn=_dsn_with(admin_dsn, user=api_role, password=api_password, dbname=platform_db),
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        provision_script=rewritten["0003_provision_application.sql"],
        deprovision_script=rewritten["0004_deprovision_application.sql"],
    )


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[object]:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"mtdbtest{secrets.token_hex(4)}"
    info = _bootstrap_platform(admin_dsn, prefix, tmp_path_factory)
    try:
        yield info
    finally:
        _sweep_prefix(admin_dsn, prefix)


def provision_app(platform, app_id: str):
    runtime_password = secrets.token_urlsafe(24)
    developer_password = secrets.token_urlsafe(24)
    _run_psql(
        platform.provision_dsn,
        platform.provision_script,
        {"app_id": app_id, "runtime_password": runtime_password, "developer_password": developer_password},
    )
    database = f"{platform.prefix}_app_{app_id}"
    runtime_role = f"{database}_rt"
    developer_role = f"{database}_dv"
    return types.SimpleNamespace(
        app_id=app_id,
        database=database,
        runtime_role=runtime_role,
        developer_role=developer_role,
        runtime_dsn=_dsn_with(platform.admin_dsn, user=runtime_role, password=runtime_password, dbname=database),
        developer_dsn=_dsn_with(platform.admin_dsn, user=developer_role, password=developer_password, dbname=database),
    )


def deprovision_app(platform, app_id: str) -> None:
    """Retries on PostgreSQL's `database "..." is being accessed by other
    users` (a connection this test just closed can take a brief moment to
    fully disappear from `pg_stat_activity`), matching r2db-api's own
    `tests/test_postgres.py::deprovision_app` policy for the identical
    race, independently applied here (R-2's own "no shared code between
    peers" principle, applied to test harnesses too).
    """
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})
            return
        except RuntimeError as exc:
            if "is being accessed by other users" not in str(exc):
                raise
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


@pytest.fixture
def app_a(platform) -> Iterator[object]:
    app = provision_app(platform, "iso_a")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_a")


@pytest.fixture
def app_b(platform) -> Iterator[object]:
    app = provision_app(platform, "iso_b")
    try:
        yield app
    finally:
        deprovision_app(platform, "iso_b")


def make_cell(app, config: FoundationConfig | None = None) -> ApplicationCell:
    backend = PostgresBackend(runtime_dsn=app.runtime_dsn, developer_dsn=app.developer_dsn)
    return ApplicationCell(app.app_id, config or FoundationConfig(), backend=backend)


def close_cell(cell: ApplicationCell) -> None:
    cell._backend.close()


def sessions_for(cell: ApplicationCell, app_id: str):
    developer_principal = Principal(app_id, "test-dev-credential", Role.DEVELOPER)
    runtime_principal = Principal(app_id, "test-runtime-credential", Role.RUNTIME)
    developer = ApplicationDeveloper(cell, developer_principal)
    runtime = ApplicationRuntime(cell, runtime_principal)
    return developer, runtime


# --- same-semantics tests (both backends, R-3's own regression claim) -----


def test_create_collection_insert_query_update_delete_match_sqlite_backend_semantics(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text", "rank": "integer"})
        result = runtime.insert("widgets", {"title": "hello", "rank": 1})
        assert "rowid" in result
        rows = runtime.read("widgets", filters=[Filter("rank", "eq", 1)])
        assert rows[0]["title"] == "hello"

        updated = runtime.update("widgets", {"title": "updated"}, [Filter("rank", "eq", 1)])
        assert updated == {"updated": 1}
        assert runtime.read("widgets")[0]["title"] == "updated"

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.delete("widgets", [Filter("rank", "eq", 1)])
        phrase = ctx.value.details["required_confirmation"]
        assert runtime.delete("widgets", [Filter("rank", "eq", 1)], destructive=True, confirm=phrase) == {"deleted": 1}
        assert runtime.read("widgets") == []
    finally:
        close_cell(cell)


def test_transact_only_executes_insert_and_rolls_back_the_whole_batch_on_failure(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("notes", {"title": "text"})
        with pytest.raises(ValidationError):
            runtime.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "first"}},
                {"type": "unsupported", "collection": "notes", "values": {"title": "second"}},
            ])
        assert runtime.read("notes") == []
        # Same seam-level semantics as the SQLite backend (P3 WP-1 round 2
        # instruction #3): `update`/`delete`/`upsert` presented to
        # `transact` are refused, not partially executed.
        from mitatedb_api.errors import CapabilityError
        with pytest.raises(CapabilityError):
            runtime.transact([{"type": "update", "collection": "notes", "values": {"title": "x"}}])
    finally:
        close_cell(cell)


def test_in_operator_and_batch_insert_via_transact(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("tags", {"label": "text"})
        results = runtime.transact([
            {"type": "insert", "collection": "tags", "values": {"label": "a"}},
            {"type": "insert", "collection": "tags", "values": {"label": "b"}},
        ])
        assert len(results) == 2
        rows = runtime.read("tags", filters=[Filter("label", "in", ["a", "b"])], order_by={"field": "label", "direction": "asc"})
        assert [r["label"] for r in rows] == ["a", "b"]
    finally:
        close_cell(cell)


# --- add_field (P3-D1) -----------------------------------------------------


def test_add_field_is_declared_and_usable_on_postgres_backend(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("things", {"name": "text"})
        declared = developer.capabilities()["capabilities"]["schema_operations"]
        assert declared["operations"] == ["create_entity", "add_field"]
        assert "add_field" not in declared["unsupported"]

        developer.add_field("things", "score", "integer")
        runtime.insert("things", {"name": "a", "score": 5})
        rows = runtime.read("things", filters=[Filter("score", "eq", 5)])
        assert rows[0]["name"] == "a"

        with pytest.raises(ConflictError):
            developer.add_field("things", "score", "integer")
        with pytest.raises(NotFoundError):
            developer.add_field("missing_collection", "x", "text")
    finally:
        close_cell(cell)


def test_add_field_and_create_entity_are_forbidden_for_runtime_at_application_level(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("locked", {"name": "text"})
        assert not hasattr(runtime, "add_field")
        assert not hasattr(runtime, "create_entity")
    finally:
        close_cell(cell)


def test_create_entity_defaults_to_a_base_id_field_when_fields_omitted(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_entity("bare")
        runtime.insert("bare", {"id": 1})
        assert runtime.read("bare")[0]["id"] == 1
        # `create_collection` itself is UNCHANGED (P3 WP-1 round 2
        # instruction #6): still rejects an empty/missing `fields`.
        with pytest.raises(ValidationError):
            developer.create_collection("still_strict", {})
    finally:
        close_cell(cell)


# --- B-1 (independent review, blocker): value-domain escape + connection ---
# --- poisoning -------------------------------------------------------------


def test_type_mismatched_values_are_rejected_deterministically_and_never_poison_the_connection(app_a) -> None:
    """B-1 blocker (independent review): a value whose Python-level SHAPE
    is acceptable but MISMATCHES its declared field_type used to escape
    `errors.FoundationError` as a raw `psycopg.errors.
    InvalidTextRepresentation`/`NumericValueOutOfRange`, AND left the
    connection in PostgreSQL's own aborted-transaction state
    (`InFailedSqlTransaction`) for every subsequent call on the same cell,
    because only the narrower `UniqueViolation`/`UndefinedTable` handlers
    called `rollback()`. This is the reviewer's own 5 repro cases, in one
    test so the FINAL assertions also prove the cell recovers after all
    five -- not just that each one individually raises the right type.
    """
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection(
            "typed", {"n": "integer", "flag": "boolean", "amount": "real", "label": "text"}
        )

        # m-8 (ii, independent review round 2): every assertion below
        # checks the SPECIFIC layer-(i) message text ("does not match"/
        # "is out of range"), not just "some ValidationError" -- the
        # layer-(ii) backstop's own message ("storage backend rejected
        # the request", every DML/DDL method's final `except psycopg.
        # Error`) is deliberately worded differently, so a test that
        # checks the EXACT message can tell whether the PRE-execution
        # gate actually caught it, versus PostgreSQL itself having caught
        # a mismatch layer (i) let through (the reviewer's own finding:
        # 3 of 4 injected mutations survived because no test distinguished
        # the two).
        #
        # (a) integer field given a non-numeric string.
        with pytest.raises(ValidationError, match="does not match the declared field type"):
            runtime.insert("typed", {"n": "not-a-number"})
        # (b) integer field given a value outside PostgreSQL's own bigint
        # range (this foundation's `integer` field type -> `BIGINT`).
        with pytest.raises(ValidationError, match="is out of range for the declared field type"):
            runtime.insert("typed", {"n": 10 ** 30})
        # (c) boolean field given a string (this foundation's `boolean`
        # field type -> physically `INTEGER`, per `backend_postgres.
        # PostgresBackend`'s own `_TYPES` comment).
        with pytest.raises(ValidationError, match="does not match the declared field type"):
            runtime.insert("typed", {"flag": "not-a-bool"})
        # (d) real field given a non-numeric string.
        with pytest.raises(ValidationError, match="does not match the declared field type"):
            runtime.insert("typed", {"amount": "not-a-float"})
        # (e) a FILTER comparison value mismatches the column's own
        # domain (not just an insert/update value -- the same domain gate
        # applies to `_bind_filters`, `cell.py`).
        runtime.insert("typed", {"n": 1})
        with pytest.raises(ValidationError, match="does not match the declared field type"):
            runtime.read("typed", filters=[Filter("n", "eq", "not-a-number")])

        # Connection recovery (B-1 (ii)): every one of the 5 rejections
        # above must leave the cell fully usable for ordinary operations
        # afterward -- NOT stuck in `InFailedSqlTransaction`.
        runtime.insert("typed", {"n": 2, "flag": True, "amount": 1.5, "label": "ok"})
        rows = runtime.read("typed", filters=[Filter("n", "eq", 2)])
        assert rows[0]["label"] == "ok"
        assert rows[0]["flag"] == 1
        assert len(runtime.read("typed")) == 2
    finally:
        close_cell(cell)


def test_backend_defense_in_depth_recovers_the_connection_after_an_unanticipated_postgres_error(app_a) -> None:
    """B-1 (ii): calling `PostgresBackend.insert()` directly (bypassing
    `cell.py`'s own domain pre-check entirely, simulating a defect or a
    case layer (i) does not cover) with a value PostgreSQL itself rejects
    still (a) raises a classified `ValidationError` carrying the
    layer-(ii) BACKSTOP's own distinct message ("storage backend rejected
    the request" -- m-8 (ii), never the layer-(i) "does not match"/"is out
    of range" wording, since layer (i) was never even consulted here),
    never a raw `psycopg.Error`, and (b) leaves the connection usable for
    the very next call -- proving the broad `except psycopg.Error:
    rollback()` backstop in `insert()` works even when the seam's own
    pre-check is bypassed."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("raw_backend_probe", {"n": "integer"})
        with pytest.raises(ValidationError, match="storage backend rejected the request"):
            cell._backend.insert("raw_backend_probe", ["n"], [10 ** 30])
        # The connection must not be poisoned by the direct call above.
        runtime.insert("raw_backend_probe", {"n": 1})
        assert runtime.read("raw_backend_probe")[0]["n"] == 1
    finally:
        close_cell(cell)


def test_backend_defense_in_depth_recovers_the_connection_for_update_delete_and_read(app_a) -> None:
    """m-8 (iii, independent review round 2): the SAME defense-in-depth
    property as the `insert()` test above, generalized to the other three
    DML methods -- the reviewer's own mutation (D) removed the generic
    `except psycopg.Error` backstop specifically from `read`/`update`/
    `delete` (leaving only their narrower `UndefinedTable` handler), which
    the pre-round-2 test suite never caught because nothing exercised
    those three methods' OWN backstop directly.

    `update`'s own trigger is the same out-of-bigint-range ASSIGNMENT the
    `insert` test above uses (confirmed empirically: `UPDATE ... SET n =
    10**30` forces a hard coercion into the `bigint` column and fails;
    unlike an assignment, a plain WHERE-clause COMPARISON against an
    out-of-range value does NOT error at all -- PostgreSQL compares
    cross-type instead of coercing, confirmed empirically, so `delete`/
    `read` need a DIFFERENT trigger). `delete`/`read`'s own trigger is a
    `Filter` naming a column that does not exist (bypassing `cell.py`'s
    own field-existence check, `_bind_filters`'s `field_domains` call) --
    a real `psycopg.errors.UndefinedColumn`, confirmed empirically NOT
    to be `UndefinedTable` (the only other handler these two methods
    have), so it is only ever caught by the generic backstop."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("raw_backend_probe2", {"n": "integer"})
        runtime.insert("raw_backend_probe2", {"n": 1})

        with pytest.raises(ValidationError, match="storage backend rejected the request"):
            cell._backend.update("raw_backend_probe2", ["n"], [10 ** 30], [])
        runtime.insert("raw_backend_probe2", {"n": 2})  # connection must still work

        with pytest.raises(ValidationError, match="storage backend rejected the request"):
            cell._backend.delete("raw_backend_probe2", [Filter("no_such_column", "eq", 1)])
        assert len(runtime.read("raw_backend_probe2")) == 2  # connection recovered, nothing deleted

        with pytest.raises(ValidationError, match="storage backend rejected the request"):
            cell._backend.read("raw_backend_probe2", ["n"], [Filter("no_such_column", "eq", 1)], None, 10)
        assert len(runtime.read("raw_backend_probe2")) == 2  # connection recovered again
    finally:
        close_cell(cell)


# --- M-5 (independent review round 2, regression from B-1's own first -----
# --- round): NULL must remain writable/filterable on the PostgreSQL --------
# --- backend -----------------------------------------------------------------


def test_null_value_can_be_written_and_filtered_on_the_postgres_backend(app_a) -> None:
    """M-5: `_check_domain` used to reject `None` unconditionally for
    every domain (every branch's own `isinstance` check is `False` for
    `None`) -- SQL `NULL` is a valid value for any column here (this
    foundation defines no `NOT NULL` constraint anywhere,
    `migrations/0003_provision_application.sql`), and SQLite already
    accepted it (no domain concept at all), so this was a real regression
    B-1's own first round introduced, not a pre-existing restriction."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("nullable", {"title": "text", "rank": "integer"})
        runtime.insert("nullable", {"title": None, "rank": 1})
        assert runtime.read("nullable")[0]["title"] is None
        # An `eq` filter against `None` must not raise (ordinary SQL
        # three-valued-logic semantics apply -- `title = NULL` is never
        # true on any SQL engine, so this correctly returns no rows, not
        # the NULL row itself; `is_null`, a different, `unsupported`
        # operator, is what would be needed for that, and is out of this
        # fix's scope).
        assert runtime.read("nullable", filters=[Filter("title", "eq", None)]) == []
        assert runtime.read("nullable", filters=[Filter("rank", "eq", 1)])[0]["title"] is None
    finally:
        close_cell(cell)


def test_validate_value_domain_accepts_none_for_every_domain() -> None:
    """M-5, at the mechanism level (m-8 (i), no DB connection needed):
    `_validate_value_domain`/`_check_domain` are plain, connection-
    independent functions -- called here directly to pin the fix at its
    own source, independent of the full insert/read round trip above."""
    from mitatedb_api.backend_postgres import _validate_value_domain

    assert _validate_value_domain(None, domain=None) is None
    assert _validate_value_domain(None, domain="text") is None
    assert _validate_value_domain(None, domain="int32") is None
    assert _validate_value_domain(None, domain="int64") is None


def test_validate_value_domain_actually_invokes_the_domain_check() -> None:
    """m-8 (i), closing a real gap: this is what independently catches the
    reviewer's own mutation (B) (removing `_validate_value_domain`'s own
    call to `_check_domain` entirely) AT THE MECHANISM LEVEL --
    `test_check_domain_type_mismatches_are_rejected_at_the_mechanism_
    level`/`test_check_domain_range_boundaries_at_the_mechanism_level`
    call `_check_domain` DIRECTLY and are therefore blind to mutation (B)
    (which leaves `_check_domain` itself untouched, only skipping the call
    to it); only a direct call to `_validate_value_domain` -- the actual
    function `PostgresBackend.encode_value` invokes -- with a value that
    legitimately mismatches its domain, closes that gap."""
    from mitatedb_api.backend_postgres import _validate_value_domain

    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _validate_value_domain("not-a-number", domain="int64")
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _validate_value_domain(10 ** 30, domain="int64")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _validate_value_domain(123, domain="text")
    # `None` still bypasses everything (M-5), and a matching value still
    # passes through unchanged -- this test is about the CHECK actually
    # running, not about over-tightening it.
    assert _validate_value_domain(None, domain="int64") is None
    assert _validate_value_domain(42, domain="int64") == 42
    assert _validate_value_domain(None, domain="float") is None


# --- m-8 (i, independent review round 2): connection-independent unit -----
# --- tests of the domain-validation MECHANISM itself ------------------------


def test_check_domain_type_mismatches_are_rejected_at_the_mechanism_level() -> None:
    """m-8 (i): direct unit tests of `_check_domain` -- no `platform`/
    `app_a` fixture, no live PostgreSQL server. These are what actually
    catch the reviewer's own mutation (B) (removing the `_check_domain`
    call from `_validate_value_domain` entirely): with the call removed,
    THESE assertions get no exception at all (rather than the masked
    `ValidationError` the full integration path would still produce via
    the layer-(ii) backstop), which is a hard failure at the mechanism
    level, not merely a differently-worded one."""
    from mitatedb_api.backend_postgres import _check_domain

    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-number", "int64")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-bool", "int32")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-float", "float")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain(123, "text")


def test_check_domain_range_boundaries_at_the_mechanism_level() -> None:
    """m-8 (i): this is what actually catches the reviewer's own mutation
    (A) (removing the range check inside `_check_domain`'s int branch,
    keeping only the `isinstance(value, int)` type check) -- with the
    range check removed, `10 ** 30`/an out-of-int32-range value would
    pass this function with NO exception at all, a hard, unmasked failure
    (unlike the full integration path, where PostgreSQL's own driver
    would still raise SOME error the layer-(ii) backstop reclassifies
    into an indistinguishable `ValidationError`)."""
    from mitatedb_api.backend_postgres import _check_domain

    # int64 (this foundation's own `integer` field type): exactly at the
    # bigint boundary succeeds (negative control); one past it fails.
    assert _check_domain(9223372036854775807, "int64") == 9223372036854775807
    assert _check_domain(-9223372036854775808, "int64") == -9223372036854775808
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _check_domain(9223372036854775808, "int64")
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _check_domain(10 ** 30, "int64")
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _check_domain(-(10 ** 30), "int64")

    # int32 (this foundation's own `boolean` field type, physically
    # `INTEGER`): same boundary proof at the narrower width.
    assert _check_domain(2147483647, "int32") == 2147483647
    assert _check_domain(-2147483648, "int32") == -2147483648
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _check_domain(2147483648, "int32")
    with pytest.raises(ValidationError, match="is out of range for the declared field type"):
        _check_domain(-2147483649, "int32")

    # float and text: type-check only (no range concept for either).
    assert _check_domain(1, "float") == 1.0
    assert _check_domain(1.5, "float") == 1.5
    assert _check_domain("hello", "text") == "hello"
    # An unrecognized domain string is passed through unchanged (matches
    # `_DOMAIN_BY_DATA_TYPE`'s own fallback of `"text"` for anything not
    # explicitly mapped -- this function itself has no "unknown domain"
    # error path, by design: an unmapped PostgreSQL `data_type` is
    # deliberately treated as `"text"` by the CALLER, `field_domains`,
    # never reaching `_check_domain` with a truly unknown domain string).
    assert _check_domain("anything", "not-a-real-domain") == "anything"


# --- m-1 (independent review correction): _mdb_schema_revision's real ------
# --- defenses ----------------------------------------------------------------


def test_schema_revision_bookkeeping_table_is_unreachable_via_identifier_syntax(app_a) -> None:
    """m-1: `field_domains` does NOT special-case-exclude `_mdb_schema_
    revision` from its own catalog view (the previous comment claiming
    otherwise was wrong) -- the REAL defense at the application level is
    that the shared identifier syntax allowlist rejects a leading
    underscore before `cell.py` ever calls into the backend at all."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("anything", {"x": "text"})
        with pytest.raises(ValidationError):
            runtime.read("_mdb_schema_revision")
    finally:
        close_cell(cell)


def test_schema_revision_bookkeeping_table_is_unreachable_via_absent_grants(app_a) -> None:
    """m-1: the SECOND, independent defense -- even bypassing the
    identifier syntax gate entirely (a raw connection, not through
    `ApplicationCell`), the runtime role has no grant of any kind on
    `_mdb_schema_revision` (created before `migrations/0003_provision_
    application.sql`'s own `ALTER DEFAULT PRIVILEGES` statement runs, so
    that statement's future-tables grant never reaches it)."""
    conn = psycopg.connect(app_a.runtime_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier("_mdb_schema_revision")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("UPDATE {} SET revision = 999").format(sql.Identifier("_mdb_schema_revision")))
    finally:
        conn.rollback()
        conn.close()


# --- M-2 (independent review): crash-retry safety of role creation --------


def test_begin_provision_application_retries_safely_after_a_partial_crash_leaves_ghost_roles(platform) -> None:
    """M-2: a previous attempt at the SAME application_id may already have
    created the two login roles (a crash/abandonment between role
    creation and `finish_provision_application`, before any database
    exists). Retrying `begin_provision_application` with NEW passwords
    must succeed (not fail on `duplicate_object`) AND the new passwords
    must actually work -- this exercises the REAL crash-retry code path
    directly (unlike the two-state cleanup test, which inserts the ghost
    row directly and never calls this function at all).

    Cleanup uses `deprovision_app` (0004) directly, not manual `DROP
    ROLE` (m-11, independent review round 2: `begin_provision_application`
    now records the derived role names in the registry row even while
    `database_name` stays NULL, so 0004 can discover and drop them
    itself -- see `test_ghost_roles_from_an_incomplete_provisioning_
    attempt_are_dropped_by_deprovision` below for that fix's own direct
    test).
    """
    app_id = "crash_retry_app"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id, "FirstAttemptRuntimePassword1", "FirstAttemptDeveloperPassword1"],
            )
            first = cur.fetchone()
        # Simulate a crash: `finish_provision_application` is deliberately
        # never called. Retry exactly as an operator/deploy-tooling would,
        # with FRESH passwords.
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id, "RetryRuntimePassword2222", "RetryDeveloperPassword2222"],
            )
            second = cur.fetchone()
        assert first == second, "derived names must be identical across retries"
        runtime_role = first[1]

        # The retry's NEW password must actually work (not the first
        # attempt's abandoned one).
        new_dsn = _dsn_with(platform.admin_dsn, user=runtime_role, password="RetryRuntimePassword2222", dbname="postgres")
        probe = psycopg.connect(new_dsn, connect_timeout=5)
        probe.close()

        # The application was never finished/provisioned, but the roles
        # ARE now recorded (m-11).
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT database_name, runtime_role FROM {}.applications WHERE application_id = %s").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id],
            )
            row = cur.fetchone()
            assert row[0] is None
            assert row[1] == runtime_role
    finally:
        conn.close()
    _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})


# --- M-3/M-6 (independent review, R-1 explicit requirement, generalized --
# --- round 2): role attribute + zero-memberships guard ---------------------


def test_provisioning_guard_passes_for_a_freshly_created_role(app_a, platform) -> None:
    """M-3/M-6 positive control: `provision_app` (app_a's own fixture)
    already succeeded, which means `assert_role_has_no_memberships`
    passed for both of its roles during provisioning -- this calls it
    again directly to pin that a normal, uncontaminated role passes."""
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT {}.assert_role_has_no_memberships(%s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_a.runtime_role],
            )
    finally:
        conn.close()


def test_provisioning_guard_detects_an_unexpected_group_membership(app_a, platform) -> None:
    """M-6 negative control (direct): the guard's own detection logic
    fires when the target role has ANY group membership at all --
    exercised with a synthetic group (not `cloudsqlsuperuser` itself,
    which cannot be created on a local cluster), proving the
    generalized, parameter-free "zero memberships" check works (m-9's own
    `pg_has_role`/transitive-detection concern is absorbed by this: zero
    DIRECT memberships implies zero transitive memberships in anything,
    `cloudsqlsuperuser` included)."""
    forbidden = "synthetic_forbidden_" + secrets.token_hex(4)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(forbidden)))
            cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(forbidden), sql.Identifier(app_a.runtime_role)))
        try:
            with conn.cursor() as cur:
                with pytest.raises(psycopg.errors.RaiseException, match="unexpected group membership"):
                    cur.execute(
                        sql.SQL("SELECT {}.assert_role_has_no_memberships(%s)").format(
                            sql.Identifier(platform.registry_schema)
                        ),
                        [app_a.runtime_role],
                    )
            conn.rollback()
        finally:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(forbidden), sql.Identifier(app_a.runtime_role)))
                cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(forbidden)))
    finally:
        conn.close()


def test_begin_provision_application_aborts_when_a_preexisting_role_was_contaminated(platform) -> None:
    """M-6 (independent review round 2, real finding): if a role bearing
    an application's own EXPECTED derived name already exists (e.g. from
    an earlier, legitimate provisioning attempt for the SAME application
    id that was never fully deprovisioned/reset) and has since been
    contaminated with `INHERIT` + a foreign group membership -- something
    M-2's own `ALTER ROLE` fallback does NOT strip (it only ever touches
    `LOGIN`/`PASSWORD`/`CONNECTION LIMIT`) -- a RETRY of `begin_provision_
    application` over that same name must ABORT (fail-closed), not
    silently adopt the contaminated role as this application's own.
    """
    app_id = "hijack_test_app"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        # A first, legitimate `begin_provision_application` call creates
        # the roles normally (owned/alterable by the provisioning role).
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id, "HijackRuntimePassword1", "HijackDeveloperPassword1"],
            )
            runtime_role, developer_role = cur.fetchone()[1:3]
    finally:
        conn.close()

    # Contaminate the runtime role from OUTSIDE this call path (e.g. an
    # operator mistake, or a stray manual GRANT) -- `ALTER ROLE ...
    # INHERIT` plus membership in an unrelated group.
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    foreign_group = "foreign_group_" + secrets.token_hex(4)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} INHERIT").format(sql.Identifier(runtime_role)))
            cur.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(foreign_group)))
            cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(foreign_group), sql.Identifier(runtime_role)))

        # A retry (simulating an operator re-running provisioning for the
        # same application id after a crash) must now ABORT.
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                with pytest.raises(psycopg.errors.RaiseException, match="unexpected attributes"):
                    cur.execute(
                        sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                            sql.Identifier(platform.registry_schema)
                        ),
                        [app_id, "RetryRuntimePassword2", "RetryDeveloperPassword2"],
                    )
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(foreign_group), sql.Identifier(runtime_role)))
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(foreign_group)))
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(runtime_role)))
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(developer_role)))
        admin.close()
        conn = psycopg.connect(platform.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {}.applications WHERE application_id = %s").format(
                        sql.Identifier(platform.registry_schema)
                    ),
                    [app_id],
                )
        finally:
            conn.close()


# --- m-11 (independent review round 2): ghost role reclaim -----------------


def test_ghost_roles_from_an_incomplete_provisioning_attempt_are_dropped_by_deprovision(platform) -> None:
    """m-11: `begin_provision_application` now records the derived role
    names in the registry row even while `database_name` stays NULL (the
    unprovisioned marker) -- so 0004's own deprovisioning script can look
    up and DROP those roles for a row that was begun but never finished
    (simulating a crash before `finish_provision_application` ran),
    instead of leaking them forever."""
    app_id = "ghost_role_reclaim_app"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    runtime_role = developer_role = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id, "GhostReclaimRuntimePwd1", "GhostReclaimDeveloperPwd1"],
            )
            row = cur.fetchone()
        runtime_role, developer_role = row[1], row[2]
        # Simulate a crash: `finish_provision_application` never runs.
        with conn.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", [runtime_role, developer_role])
            assert {r[0] for r in cur.fetchall()} == {runtime_role, developer_role}
    finally:
        conn.close()

    _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})

    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", [runtime_role, developer_role])
            assert cur.fetchall() == []
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.applications WHERE application_id = %s").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id],
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


# --- M-4 (independent review, adjudicated): deprovision removes -----------
# --- credentials in the same step, no separate guard ----------------------


def test_deprovisioning_removes_credential_rows_in_the_same_step(platform) -> None:
    """M-4: the previous revision's separate `assert_no_credentials_for_
    deprovision` guard is gone -- `finish_deprovision_application` now
    deletes this application's own `credentials` rows itself, in the same
    step it removes the `applications` row. Uses its OWN throwaway
    application (not `app_a`/`app_b`, whose fixtures manage their own
    teardown) so this test's own deprovision call cannot conflict with a
    fixture's finalizer."""
    app = provision_app(platform, "cred_cleanup_app")
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.credentials (credential_id, application_id, role, digest) "
                    "VALUES (%s, %s, %s, %s)"
                ).format(sql.Identifier(platform.registry_schema)),
                ["cred-" + secrets.token_hex(4), app.app_id, "runtime", b"synthetic-digest"],
            )
    finally:
        conn.close()

    deprovision_app(platform, "cred_cleanup_app")

    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.credentials WHERE application_id = %s").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app.app_id],
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


# --- m-3 (independent review): platform database's own `public` schema ----


def test_platform_database_public_schema_default_privileges_are_closed(platform) -> None:
    """m-3: symmetry with 0003's own tenant-database treatment -- the
    PLATFORM database's own `public` schema (created automatically by
    `CREATE DATABASE` in 0001) must not be left with PostgreSQL's default
    wide-open `PUBLIC` privileges either."""
    conn = psycopg.connect(platform.api_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("CREATE TABLE public.{} (x int)").format(sql.Identifier("sneaky_" + secrets.token_hex(4))))
    finally:
        conn.rollback()
        conn.close()


def test_schema_revision_bumps_durably_and_invalidates_a_stale_delete_confirmation(app_a) -> None:
    """P3 WP-1 round 2 instruction #5: `add_field` is "another schema
    change" that must invalidate a delete confirmation phrase issued
    before it. `schema_revision` is read back directly from the real
    PostgreSQL bookkeeping table (`backend_postgres.PostgresBackend.
    schema_revision`), proving the bump is durable (a real row in a real
    table), not merely an in-process counter."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("gated", {"title": "text"})
        runtime.insert("gated", {"title": "keep-me"})

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.delete("gated", [Filter("title", "eq", "keep-me")])
        stale_phrase = ctx.value.details["required_confirmation"]

        before = cell._backend.schema_revision()
        developer.add_field("gated", "extra", "text")
        after = cell._backend.schema_revision()
        assert after == before + 1

        with pytest.raises(DestructiveConfirmationRequired):
            runtime.delete("gated", [Filter("title", "eq", "keep-me")], destructive=True, confirm=stale_phrase)

        with pytest.raises(DestructiveConfirmationRequired) as ctx2:
            runtime.delete("gated", [Filter("title", "eq", "keep-me")])
        fresh_phrase = ctx2.value.details["required_confirmation"]
        assert fresh_phrase != stale_phrase
        assert runtime.delete("gated", [Filter("title", "eq", "keep-me")], destructive=True, confirm=fresh_phrase) == {"deleted": 1}
    finally:
        close_cell(cell)


# --- R-2 choke point --------------------------------------------------------


def test_choke_point_rejects_a_raw_string_and_accepts_a_composed_statement() -> None:
    class _RecordingCursor:
        def __init__(self) -> None:
            self.called = False

        def execute(self, statement, params=()):
            self.called = True

    cur = _RecordingCursor()
    with pytest.raises(TypeError):
        _execute(cur, "SELECT 1")  # type: ignore[arg-type]
    assert cur.called is False, "a rejected raw string must never reach cursor.execute"

    _execute(cur, sql.SQL("SELECT 1"))
    assert cur.called is True


def test_injection_shaped_values_round_trip_byte_equal_never_executed_as_sql(app_a) -> None:
    """R-2: values are always bound as psycopg parameters, never
    string-interpolated into SQL text. A value that LOOKS like a SQL
    injection payload must round-trip byte-for-byte (proving it was bound,
    not executed) and must never actually drop/alter anything."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    payloads = [
        "'; DROP TABLE injection_target; --",
        "x' OR '1'='1",
        "\"; DELETE FROM injection_target WHERE \"1\"=\"1",
        "value with a literal % percent and _ underscore",
    ]
    try:
        developer.create_collection("injection_target", {"value": "text"})
        for index, payload in enumerate(payloads):
            runtime.insert("injection_target", {"value": payload})
            rows = runtime.read("injection_target", filters=[Filter("value", "eq", payload)])
            assert len(rows) == 1, f"payload {payload!r} did not round-trip"
            assert rows[0]["value"] == payload
        # The table must still exist with exactly `len(payloads)` rows --
        # none of the DROP/DELETE-shaped payloads executed as SQL.
        assert len(runtime.read("injection_target")) == len(payloads)
    finally:
        close_cell(cell)


def test_postgres_backend_rejects_embedded_nul_deterministically_before_execution(app_a) -> None:
    """P3 WP-1 round 2 instruction #1: the common conformance corpus's own
    `nul_byte = "value\\x00tail"` (conformance-tests/payloads.py) must be
    refused as a deterministic `ValidationError`, never surfaced as an
    unclassified PostgreSQL/psycopg driver exception."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("nultest", {"value": "text"})
        with pytest.raises(ValidationError):
            runtime.insert("nultest", {"value": "value\x00tail"})
        assert runtime.read("nultest") == []
        runtime.insert("nultest", {"value": "control-row"})
        with pytest.raises(ValidationError):
            runtime.read("nultest", filters=[Filter("value", "eq", "value\x00tail")])
    finally:
        close_cell(cell)


# --- R-1 containment: raw connections, not through the foundation ---------


def test_cross_database_connect_is_refused_at_the_database_level(app_a, app_b) -> None:
    cross_dsn = _dsn_with(app_a.runtime_dsn, dbname=app_b.database)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(cross_dsn, connect_timeout=5)
    cross_dev_dsn = _dsn_with(app_a.developer_dsn, dbname=app_b.database)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(cross_dev_dsn, connect_timeout=5)


def test_runtime_role_cannot_perform_ddl(app_a) -> None:
    cell = make_cell(app_a)
    developer, _ = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("items", {"label": "text"})
    finally:
        close_cell(cell)

    conn = psycopg.connect(app_a.runtime_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("CREATE TABLE {} (x INT)").format(sql.Identifier("sneaky")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN sneaky INT").format(sql.Identifier("items")))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier("items")))
    finally:
        conn.rollback()
        conn.close()


def test_application_plane_process_role_cannot_select_control_tables(platform) -> None:
    """R-4: `{prefix}svc_api` may read `applications`/`credentials` (its
    own `authenticate()` path, WP-2) but has NO grant at all on
    `control_credentials`/`control_audit`."""
    conn = psycopg.connect(platform.api_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {}.applications").format(sql.Identifier(platform.registry_schema)))
            cur.execute(sql.SQL("SELECT count(*) FROM {}.credentials").format(sql.Identifier(platform.registry_schema)))
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT count(*) FROM {}.control_credentials").format(sql.Identifier(platform.registry_schema)))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT count(*) FROM {}.control_audit").format(sql.Identifier(platform.registry_schema)))
    finally:
        conn.rollback()
        conn.close()


def test_control_plane_process_role_can_insert_but_never_read_or_erase_control_audit(platform) -> None:
    """R-4: `control_audit` is append-only BY PRIVILEGE for
    `{prefix}svc_controlplane` -- no SELECT/UPDATE/DELETE grant of any
    kind, not merely an application-code convention."""
    conn = psycopg.connect(platform.controlplane_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.control_audit (event_id, event_class, occurred_at, operation, outcome) "
                    "VALUES (%s, %s, now(), %s, %s)"
                ).format(sql.Identifier(platform.registry_schema)),
                ["evt-" + secrets.token_hex(4), "test", "noop", "success"],
            )
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}.control_audit").format(sql.Identifier(platform.registry_schema)))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("DELETE FROM {}.control_audit").format(sql.Identifier(platform.registry_schema)))
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("UPDATE {}.control_audit SET outcome = 'tampered'").format(sql.Identifier(platform.registry_schema)))
    finally:
        conn.rollback()
        conn.close()


def test_control_audit_seq_exists_and_increases_monotonically(platform) -> None:
    """m-10 (independent review round 2): `audit_seq bigserial` (M-1)
    must actually exist and produce a strictly increasing value across
    two inserts -- the real property C-15's own prefix-strict comparison
    needs (a wall-clock `recorded_at`/`occurred_at` alone cannot promise
    this under concurrent inserts).

    Inserts via `controlplane_dsn` WITHOUT `RETURNING` (confirmed
    empirically: `INSERT ... RETURNING audit_seq` itself requires a
    SELECT-shaped privilege PostgreSQL does not fold into a plain
    `INSERT` grant, and this role deliberately has none at all, R-4 --
    "control_audit is INSERT-only ... no SELECT ... grant of any kind")
    -- reads the two rows back via `provision_dsn` (the schema owner)
    instead, the same way an operator/runbook tool auditing this table
    from outside the control-plane process itself would."""
    event_ids = ["evt-" + secrets.token_hex(4), "evt-" + secrets.token_hex(4)]
    conn = psycopg.connect(platform.controlplane_dsn, autocommit=True)
    try:
        for event_id in event_ids:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {}.control_audit (event_id, event_class, occurred_at, operation, outcome) "
                        "VALUES (%s, %s, now(), %s, %s)"
                    ).format(sql.Identifier(platform.registry_schema)),
                    [event_id, "test", "noop", "success"],
                )
    finally:
        conn.close()

    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT event_id, audit_seq FROM {}.control_audit WHERE event_id = ANY(%s) ORDER BY audit_seq").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [event_ids],
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == event_ids, "insertion order must match audit_seq order"
    assert rows[1][1] > rows[0][1]


# --- two-state registry (R-4, C-14 vector 5) -------------------------------


def test_two_state_registry_allows_deprovisioning_a_registered_but_unprovisioned_application(platform) -> None:
    """Simulates what a future `/control/v1 register_application` (WP-4)
    would do -- a pure bookkeeping row, `database_name IS NULL`, no roles
    or database ever created for it -- and proves 0004 can still fully
    remove it (C-14 vector 5's own requirement)."""
    app_id = "ghost_app"
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {}.applications (application_id) VALUES (%s)").format(sql.Identifier(platform.registry_schema)),
                [app_id],
            )
            cur.execute(
                sql.SQL("SELECT database_name FROM {}.applications WHERE application_id = %s").format(sql.Identifier(platform.registry_schema)),
                [app_id],
            )
            assert cur.fetchone()[0] is None
    finally:
        conn.close()

    _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})

    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.applications WHERE application_id = %s").format(sql.Identifier(platform.registry_schema)),
                [app_id],
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_deprovisioning_an_unregistered_application_fails_loudly(platform) -> None:
    with pytest.raises(RuntimeError, match="application not registered"):
        _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": "never_registered_app"})


def test_provisioning_a_maximum_length_application_id_stays_within_namedatalen(platform) -> None:
    """Positive control for P3 WP-1 round 2 instruction #2's own length
    guard: the contract's own `application_id` ceiling (33 characters,
    `^[a-z][a-z0-9_]{0,32}$`) combined with this test module's own
    (deliberately short) throwaway prefix must still fit PostgreSQL's own
    63-byte NAMEDATALEN limit for the longest derived name
    (`..._dv`) -- this is the real arithmetic `begin_provision_
    application`'s own guard asserts; this test proves it holds for the
    actual prefix this module uses, empirically, rather than only on
    paper."""
    app_id = "a" * 33
    app = provision_app(platform, app_id)
    try:
        assert len(app.developer_role.encode("utf-8")) <= 63
        cell = make_cell(app)
        developer, runtime = sessions_for(cell, app_id)
        try:
            developer.create_collection("ok", {"x": "text"})
            runtime.insert("ok", {"x": "1"})
        finally:
            close_cell(cell)
    finally:
        deprovision_app(platform, app_id)


def test_provisioning_guard_rejects_a_derived_role_name_that_would_exceed_namedatalen(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Negative control: a deliberately long throwaway prefix (its own
    isolated platform bootstrap, swept independently of the module-scoped
    `platform` fixture) combined with a near-maximum-length application_id
    pushes the derived developer-role name past 63 bytes -- proving
    `begin_provision_application`'s own `octet_length(...) > 63` guard
    actually fires (`RAISE EXCEPTION`), rather than silently letting
    PostgreSQL truncate two different applications' role names down to a
    colliding 63-byte prefix.
    """
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    # `mtdbnamelen` (11) + hex(4)->8 = 19, chosen so that combined with the
    # fixed `svc_provision`/`_app_.._dv` decoration and a near-maximum
    # application_id the derived name is pushed comfortably past 63 bytes.
    long_prefix = "mtdbnamelenguard" + secrets.token_hex(10)  # 16 + 20 = 36 chars
    info = _bootstrap_platform(admin_dsn, long_prefix, tmp_path_factory)
    try:
        conn = psycopg.connect(info.provision_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                with pytest.raises(psycopg.errors.RaiseException, match="NAMEDATALEN"):
                    cur.execute(
                        sql.SQL("SELECT * FROM {}.begin_provision_application(%s, %s, %s)").format(
                            sql.Identifier(info.registry_schema)
                        ),
                        ["a" * 33, secrets.token_urlsafe(24), secrets.token_urlsafe(24)],
                    )
        finally:
            conn.close()
    finally:
        _sweep_prefix(admin_dsn, long_prefix)
