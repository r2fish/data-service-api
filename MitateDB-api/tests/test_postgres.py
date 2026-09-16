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

from mitatedb_api.auth import CredentialStore, Principal, Role
from mitatedb_api.backend_postgres import PostgresBackend, _execute
from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, Filter
from mitatedb_api.config import FoundationConfig
from mitatedb_api.credential_wire import split_bearer_locator
from mitatedb_api.credential_store_postgres import (PostgresCredentialStore,
                                                    _role_or_state_unavailable,
                                                    assert_pepper_separation)
from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE
from mitatedb_api.errors import (AuthenticationError, AuthorizationStateUnavailable,
                                 ConflictError, DestructiveConfirmationRequired,
                                 NotFoundError, StorageConfigurationError, ValidationError)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"

# R-4 "prefix-anchored sweep + advisory lock": a fixed, arbitrary 63-bit
# advisory-lock key, held only around this module's own enumerate-then-drop
# sweep so two sweeps against the same cluster (e.g. this file's own
# module-scoped teardown racing a stray concurrent run) serialize instead
# of racing each other's `DROP DATABASE`/`DROP ROLE` enumeration.
_SWEEP_LOCK_KEY = 0x4D544442535750  # ASCII "MTDBSWP", arbitrary but stable


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def test_admin_dsn_requires_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-44 WP-3 (a) completion condition 8: `_admin_dsn()` raises when
    `MITATEDB_TEST_ADMIN_DSN` is unset or empty -- there is no
    shared-cluster default to fall back to any more (design D-4)."""
    monkeypatch.delenv(ADMIN_DSN_ENV, raising=False)
    with pytest.raises(RuntimeError):
        _admin_dsn()

    monkeypatch.setenv(ADMIN_DSN_ENV, "")
    with pytest.raises(RuntimeError):
        _admin_dsn()


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
            f"{ADMIN_DSN_ENV} is set by tools/testpg/dsa_testpg.py for each "
            "test run; there is no shared-cluster default. These tests must "
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
        # Phase 10 WP-4g (supervisor ruling 2026-09-09): `mitatedb_api.
        # main.build_app`/`mitatedb_api.control_composition.build_control_
        # service` now run F-16 (this process' own role CONNECTION LIMIT)
        # unconditionally at startup -- every test in this repository that
        # calls either (directly or via this shared `platform` fixture)
        # now depends on this migration too, or the api/controlplane
        # roles' own pre-WP-4f `CONNECTION LIMIT` (20/10, `0002_registry_
        # and_functions.sql`) sits below F-16's own real pool-composition
        # floor and fails startup for every consumer, not just the ones
        # actually about F-16.
        "0012_role_connection_limits.sql",
        # Q4 phase (design D-1/D-2, work order §4 WP-2): platform
        # declarations table + the two service writer roles' timeout role
        # settings -- every test in this repository that calls `main.
        # build_app`/`control_composition.build_control_service` (directly
        # or via this shared `platform` fixture) now depends on this
        # migration having been applied (F-3/F-7 otherwise).
        "0007_platform_declarations.sql",
        # Phase 10 WP-6b (design D-5 (ii)): widens `platform_declarations.
        # key`'s own CHECK constraint to accept `process_ceilings` --
        # every test that calls `main.build_app`/`control_composition.
        # build_control_service` (directly or via this shared `platform`
        # fixture) now depends on this migration + the row seeded below,
        # or it fails startup with F-15.
        "0011_process_ceilings.sql",
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
        _run_psql(provision_dsn, rewritten["0012_role_connection_limits.sql"])
        _run_psql(provision_dsn, rewritten["0007_platform_declarations.sql"], {"api_role": api_role, "controlplane_role": controlplane_role})
        _run_psql(provision_dsn, rewritten["0011_process_ceilings.sql"])
        # Q4 phase (design D-2(c)): synthetic example.invalid `surfaces` --
        # a real deployment declares this with `ops declare-surfaces`.
        # DATA ONLY (no `control` key) -- this shared fixture's own
        # consumers (`test_main.py`) default to `MITATEDB_CONTROL_PLANE_
        # STATUS` UNSET ("unavailable"), matching the design's own F-6
        # requirement that surfaces.control's presence and this process'
        # own declared status agree. A test that needs `control_plane:
        # enabled` (`test_main.py::test_build_app_control_plane_status_
        # env_flip_is_reflected_in_a_real_request`) re-declares this SAME
        # row with a `control` key added, first -- exactly what a real
        # deployment's own `ops declare-surfaces --control-base-url <URL>`
        # would do (§9.2), never a silent per-process env-only flip.
        surfaces_conn = psycopg.connect(provision_dsn, autocommit=True)
        try:
            with surfaces_conn.cursor() as cur:
                _execute(
                    cur,
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('surfaces', {value})").format(
                        table=sql.Identifier(registry_schema, "platform_declarations"),
                        value=sql.Literal(
                            '{"data":{"base_url":"https://data.mitatedb-postgres-test.example.invalid/v1"}}'
                        ),
                    ),
                )
                # Phase 10 WP-6b (design D-5 (ii)): seeded alongside
                # `surfaces` -- `main.build_app`/`build_control_service`
                # both now require this row too (F-15). `{"data": 1,
                # "control": 1}` matches this fixture's own single-process
                # reality -- `limit_enforcement` for `concurrency`/
                # `requests_per_minute` stays `enforced`, unchanged from
                # before this WP.
                _execute(
                    cur,
                    sql.SQL("INSERT INTO {table} (key, value) VALUES ('process_ceilings', {value})").format(
                        table=sql.Identifier(registry_schema, "platform_declarations"),
                        value=sql.Literal('{"data": 1, "control": 1}'),
                    ),
                )
        finally:
            surfaces_conn.close()
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
        api_role=api_role,
        controlplane_dsn=_dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db),
        controlplane_role=controlplane_role,
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


# ---------------------------------------------------------------------------
# WP-3e rework T3 (N-1, ruling `{scratchpad}/rulings-r3-r7-flip.md`):
# `backend_postgres.py`/`backend_sqlite.py`'s OWN internal `validate_
# identifier(collection, ...)` calls -- the backends' own cell-mirroring
# checks (WP-3e T2, git log "identifier / predicate fields are request
# paths") -- now pass `"entity"`, the SAME contract-vocabulary word `cell.
# py::ApplicationCell._identifier`'s own call sites already pass for this
# exact position (`identifiers.py::validate_identifier`'s own docstring:
# "`field` is `label` itself...cell.py's own call sites...stop passing a
# generic, position-blind literal like the pre-rework bare `"collection"`
# "), never the stale bare `"collection"` literal these two backend files
# alone still carried. `ApplicationCell._identifier` already validates
# every collection name (as `"entity"`) BEFORE either backend method below
# is ever reached through the normal cell-mediated path, so this test
# reaches the backend's OWN check directly (a raw `PostgresBackend.field_
# types(...)` call, bypassing `ApplicationCell` entirely) -- proving the
# label even though ordinary traffic can never actually trigger it (N-1:
# "到達性が無くても契約語に揃える").
# ---------------------------------------------------------------------------


def test_postgres_backend_identifier_violation_label_is_entity_not_collection(app_a) -> None:
    backend = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    try:
        with pytest.raises(ValidationError) as ctx:
            backend.field_types("not a valid identifier!")
        assert ctx.value.details["field"] == "entity"
    finally:
        backend.close()


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
        # P3-D2 (design v1.2 R-5, WP-1.5): `update` presented to `transact`
        # now executes for real, atomically with the rest of the batch --
        # this is the same seam-level convergence as the SQLite backend
        # (see `test_foundation.py`'s own equivalent). Same as `insert`
        # above: an unrelated failure later in the SAME batch still rolls
        # the whole thing back, the `update` included.
        from mitatedb_api.errors import CapabilityError
        updated = runtime.transact([{"type": "update", "collection": "notes", "values": {"title": "x"},
                                     "filters": [Filter("title", "eq", "first")]}])
        # Phase 9 WP-3e (design D-7 (3)/(4), Q-1/Q-2): the LAST (here,
        # only) item's own result dict now also carries `request_id`.
        assert updated[-1].pop("request_id")
        assert updated == [{"updated": 0}]  # "first" was rolled back above; nothing to match
        # `upsert` alone remains a real capability gap -- no execution path
        # for it exists anywhere on this peer, batched or not.
        with pytest.raises(CapabilityError):
            runtime.transact([{"type": "upsert", "collection": "notes", "values": {"title": "x"}}])
    finally:
        close_cell(cell)


def test_transact_executes_mixed_insert_update_delete_atomically(app_a) -> None:
    """P3-D2 (design v1.2 R-5, WP-1.5): a real mixed batch
    [insert, update, delete] executes as one atomic unit through
    `transact()` -- converging real behavior onto the existing
    `atomic_mutation.operations: ["insert", "update", "delete"]`
    declaration (unchanged by this WP). The batch-embedded delete goes
    through the identical declare-and-echo confirmation choke the
    dedicated `delete()` method uses."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text", "rank": "integer"})
        runtime.insert("widgets", {"title": "keep-updated", "rank": 1})
        runtime.insert("widgets", {"title": "to-delete", "rank": 2})

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.transact([
                {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 2)]},
            ])
        phrase = ctx.value.details["required_confirmation"]

        results = runtime.transact([
            {"type": "insert", "collection": "widgets", "values": {"title": "brand-new", "rank": 3}},
            {"type": "update", "collection": "widgets", "values": {"title": "renamed"}, "filters": [Filter("rank", "eq", 1)]},
            {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 2)],
             "destructive": True, "confirm": phrase},
        ])
        assert len(results) == 3
        assert "rowid" in results[0]
        assert results[1] == {"updated": 1}
        # Phase 9 WP-3e (design D-7 (3)/(4), Q-1/Q-2): the LAST item's own
        # result dict now also carries `request_id` (folded in, in place,
        # by `cell.py::ApplicationCell.transact`, never a new trailing
        # list entry -- see that method's own comment for why) -- checked
        # for presence, then popped before the exact-shape assert below,
        # which stays a precise pin of the REST of the shape.
        assert results[2].pop("request_id")
        assert results[2] == {"deleted": 1}
        rows = {row["rank"]: row["title"] for row in runtime.read("widgets")}
        assert rows == {1: "renamed", 3: "brand-new"}
    finally:
        close_cell(cell)


def test_transact_mixed_batch_rolls_back_everything_when_the_delete_confirmation_is_stale(app_a) -> None:
    """The whole batch -- including the insert and update that would
    otherwise have succeeded -- must roll back when a LATER operation in
    the same batch (here, the delete) fails its own declare-and-echo
    check. Proves atomicity, not merely that each operation is
    individually validated."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text", "rank": "integer"})
        runtime.insert("widgets", {"title": "seed", "rank": 1})

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.delete("widgets", [Filter("rank", "eq", 1)])
        stale_phrase = ctx.value.details["required_confirmation"]
        # Invalidate that phrase (P3-D1's own schema-revision fingerprint)
        # by bumping the schema revision underneath it.
        developer.add_field("widgets", "extra", "text")

        with pytest.raises(DestructiveConfirmationRequired):
            runtime.transact([
                {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist", "rank": 99}},
                {"type": "update", "collection": "widgets", "values": {"title": "should-not-persist-either"},
                 "filters": [Filter("rank", "eq", 1)]},
                {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
                 "destructive": True, "confirm": stale_phrase},
            ])

        rows = runtime.read("widgets")
        assert len(rows) == 1 and rows[0]["title"] == "seed", (
            "the insert and update earlier in the same batch must not have persisted"
        )
    finally:
        close_cell(cell)


def test_transact_delete_rejects_wire_omitted_destructive_with_valid_confirmation(app_a) -> None:
    """The batch-embedded delete's own confirmation choke must reject the
    exact V2b-wire shape (`destructive` key genuinely absent from the
    wire, a real, currently-valid `confirm` phrase still present) the same
    way the dedicated `delete()` method does -- a missing `destructive`
    field is equivalent to `False`, never to `True` (contract
    `valid_confirmation`)."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text", "rank": "integer"})
        runtime.insert("widgets", {"title": "keep-me", "rank": 1})

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.transact([{"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)]}])
        phrase = ctx.value.details["required_confirmation"]

        # `destructive` genuinely OMITTED from the operation dict (not
        # merely `False`), `confirm` present and currently valid.
        with pytest.raises(DestructiveConfirmationRequired):
            runtime.transact([{"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
                               "confirm": phrase}])
        assert runtime.read("widgets") == [{"title": "keep-me", "rank": 1}]
    finally:
        close_cell(cell)


def test_transact_upsert_rejected_regardless_of_other_batch_contents(app_a) -> None:
    """P3-D2 does not touch `upsert`: it remains refused with
    `CapabilityError` no matter what else shares the batch, and the whole
    batch (including a real insert alongside it) still rolls back."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text", "rank": "integer"})
        from mitatedb_api.errors import CapabilityError
        with pytest.raises(CapabilityError):
            runtime.transact([
                {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist", "rank": 1}},
                {"type": "upsert", "collection": "widgets", "values": {"title": "x", "rank": 2}},
            ])
        assert runtime.read("widgets") == []
    finally:
        close_cell(cell)


def test_transact_batch_update_and_delete_reject_the_same_mass_operation_shapes_as_dedicated_methods(app_a) -> None:
    """M-1 (independent review, WP-1.5 follow-up): the batch-embedded
    `update`/`delete` branches must apply the identical mass-operation
    guards the dedicated `update()`/`delete()` methods already enforce --
    an omitted/empty/`None` `filters` (a filter-less batch update/delete
    would otherwise mass-mutate/mass-delete every row) and empty `values`
    for `update` -- rejecting each of the 6 shapes below with
    `ValidationError` before any write, and leaving the WHOLE BATCH's own
    state unchanged (nothing commits, the well-formed `insert` sharing the
    batch included). Same shapes as the SQLite-backend equivalent in
    `test_foundation.py`, pinning the identical guard on the Postgres
    backend too (`_validate_update`/`_validate_delete_confirmation` are
    backend-independent, in `cell.py`)."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text"})
        runtime.insert("widgets", {"title": "seed"})

        bad_shapes = {
            "update: filters key omitted": {"type": "update", "collection": "widgets", "values": {"title": "x"}},
            "update: filters=[]": {"type": "update", "collection": "widgets", "values": {"title": "x"}, "filters": []},
            "update: filters=None": {"type": "update", "collection": "widgets", "values": {"title": "x"}, "filters": None},
            "update: values={}": {"type": "update", "collection": "widgets", "values": {},
                                   "filters": [Filter("title", "eq", "seed")]},
            "delete: filters key omitted": {"type": "delete", "collection": "widgets"},
            "delete: filters=[]": {"type": "delete", "collection": "widgets", "filters": []},
        }
        for label, bad_op in bad_shapes.items():
            with pytest.raises(ValidationError):
                runtime.transact([
                    {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist"}},
                    bad_op,
                ])
            assert runtime.read("widgets") == [{"title": "seed"}], (
                f"batch must not have written anything for shape {label!r}"
            )
    finally:
        close_cell(cell)


def test_transact_batch_delete_accepts_an_empty_values_key(app_a) -> None:
    """m-4 (independent review, WP-1.5 follow-up): a batch delete
    operation-dict carrying `values: {}` must be accepted (not a
    capability-gap `CapabilityError`) on the Postgres backend too --
    same wire shape `conformance_adapter_mitatedb.py::attempt_batch_with_
    addresses` always constructs, regardless of operation type."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("widgets", {"title": "text"})
        runtime.insert("widgets", {"title": "keep-me"})
        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.transact([
                {"type": "delete", "collection": "widgets", "values": {},
                 "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase = ctx.value.details["required_confirmation"]
        result = runtime.transact([
            {"type": "delete", "collection": "widgets", "values": {},
             "filters": [Filter("title", "eq", "keep-me")], "destructive": True, "confirm": phrase},
        ])
        # Phase 9 WP-3e (design D-7 (3)/(4), Q-1/Q-2): see the identical
        # comment above this test's own sibling assertion for why the
        # LAST item's own dict now also carries `request_id`.
        assert result[-1].pop("request_id")
        assert result == [{"deleted": 1}]
        assert runtime.read("widgets") == []
    finally:
        close_cell(cell)


# --- P35 WP-2 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §2): two-pass transact + batch_entities + cross-entity atomicity,
# on the real PostgreSQL backend. -------------------------------------------


def test_transact_two_pass_structure_zero_backend_calls_when_a_later_operation_fails_validation(app_a) -> None:
    """P35-D10 (structural, white-box), pinned on the real Postgres
    backend too: a batch whose first operation is individually valid must
    never reach the backend at all when a LATER operation fails
    VALIDATION -- not `begin()`, not `insert_in_transaction()`."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("two_pass_probe", {"title": "text"})
        backend = cell._backend
        calls = {"begin": 0, "insert_in_transaction": 0}
        real_begin = backend.begin
        real_insert = backend.insert_in_transaction

        def counting_begin():
            calls["begin"] += 1
            return real_begin()

        def counting_insert(collection, fields, params):
            calls["insert_in_transaction"] += 1
            return real_insert(collection, fields, params)

        backend.begin = counting_begin
        backend.insert_in_transaction = counting_insert
        try:
            with pytest.raises(ValidationError):
                runtime.transact([
                    {"type": "insert", "collection": "two_pass_probe", "values": {"title": "would-have-executed"}},
                    {"type": "unsupported", "collection": "two_pass_probe", "values": {"title": "invalid"}},
                ])
        finally:
            backend.begin = real_begin
            backend.insert_in_transaction = real_insert
        assert calls["begin"] == 0
        assert calls["insert_in_transaction"] == 0
        assert runtime.read("two_pass_probe") == []
    finally:
        close_cell(cell)


def test_transact_error_priority_validation_error_wins_over_an_earlier_execution_time_failure(app_a) -> None:
    """P35-D9, pinned on the real Postgres backend too: a batch mixing an
    operation that would fail at BACKEND EXECUTION time with a LATER
    operation that fails VALIDATION now surfaces the validation error --
    synthesized via a wrapped `insert_in_transaction`.

    M-2 correction (independent review, WP-2 follow-up): the earlier
    claim here ("no naturally-reachable execution-time failure") was
    false -- the one known natural execution-time failure (a lone UTF-16
    surrogate code point in a value, escaping as a raw
    `UnicodeEncodeError` on both backends) was reclassified to
    deterministic validation-time rejection by WP-2 review B-2; the
    synthesized `ConflictError` below remains the exercise vehicle for
    this test's own subject (error-type priority), now the only way to
    exercise an execution-time failure at all on either backend."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("priority_probe", {"title": "text"})
        backend = cell._backend
        real_insert = backend.insert_in_transaction

        def failing_insert(collection, fields, params):
            raise ConflictError("synthetic execution-time failure")

        backend.insert_in_transaction = failing_insert
        try:
            with pytest.raises(ValidationError):
                runtime.transact([
                    {"type": "insert", "collection": "priority_probe", "values": {"title": "would-fail-at-execution"}},
                    {"type": "unsupported", "collection": "priority_probe", "values": {"title": "invalid"}},
                ])
        finally:
            backend.insert_in_transaction = real_insert
        assert runtime.read("priority_probe") == []
    finally:
        close_cell(cell)


def test_transact_cross_entity_atomic_commit_across_two_entities(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("cross_a", {"title": "text"})
        developer.create_collection("cross_b", {"title": "text"})
        results = runtime.transact([
            {"type": "insert", "collection": "cross_a", "values": {"title": "a-row"}},
            {"type": "insert", "collection": "cross_b", "values": {"title": "b-row"}},
        ])
        assert len(results) == 2
        assert runtime.read("cross_a")[0]["title"] == "a-row"
        assert runtime.read("cross_b")[0]["title"] == "b-row"
    finally:
        close_cell(cell)


def test_transact_cross_entity_rollback_when_later_entity_operation_is_invalid(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("cross_c", {"title": "text"})
        developer.create_collection("cross_d", {"title": "text"})
        with pytest.raises(ValidationError):
            runtime.transact([
                {"type": "insert", "collection": "cross_c", "values": {"title": "should-not-persist"}},
                {"type": "update", "collection": "cross_d", "values": {"title": "x"}},  # filters omitted
            ])
        assert runtime.read("cross_c") == []
        assert runtime.read("cross_d") == []
    finally:
        close_cell(cell)


def test_transact_batch_entities_boundary_and_distinct_count_ignores_repeats(app_a) -> None:
    """P35-D2: `batch_entities` bounds DISTINCT collection names, not
    operation count. Uses a cheap config override (`max_batch_entities=2`)
    rather than constructing 11 real Postgres tables -- the SQLite-backed
    equivalent (`test_foundation.py`) separately pins the real declared
    default (10) directly, unmodified."""
    from mitatedb_api.errors import ResourceLimitError

    cell = make_cell(app_a, FoundationConfig(max_batch_entities=2))
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        for name in ("ent_one", "ent_two", "ent_three"):
            developer.create_collection(name, {"title": "text"})

        result = runtime.transact([
            {"type": "insert", "collection": "ent_one", "values": {"title": "1"}},
            {"type": "insert", "collection": "ent_two", "values": {"title": "1"}},
        ])
        assert len(result) == 2

        with pytest.raises(ResourceLimitError) as ctx:
            runtime.transact([
                {"type": "insert", "collection": "ent_one", "values": {"title": "2"}},
                {"type": "insert", "collection": "ent_two", "values": {"title": "2"}},
                {"type": "insert", "collection": "ent_three", "values": {"title": "1"}},
            ])
        assert ctx.value.details == {"limit_class": "batch_entities"}
        assert len(runtime.read("ent_one")) == 1
        assert len(runtime.read("ent_two")) == 1
        assert runtime.read("ent_three") == []

        many_same_entity = [{"type": "insert", "collection": "ent_one", "values": {"title": f"r{i}"}} for i in range(10)]
        result = runtime.transact(many_same_entity)
        assert len(result) == 10
    finally:
        close_cell(cell)


def test_transact_cross_entity_delete_wrong_entity_phrase_is_refused(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("phrase_a", {"title": "text"})
        developer.create_collection("phrase_b", {"title": "text"})
        runtime.insert("phrase_a", {"title": "keep-me"})
        runtime.insert("phrase_b", {"title": "keep-me"})

        with pytest.raises(DestructiveConfirmationRequired) as ctx_a:
            runtime.transact([
                {"type": "delete", "collection": "phrase_a", "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase_a = ctx_a.value.details["required_confirmation"]
        assert "phrase_a" in phrase_a

        with pytest.raises(DestructiveConfirmationRequired):
            runtime.transact([
                {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")],
                 "destructive": True, "confirm": phrase_a},
            ])
        assert runtime.read("phrase_a")[0]["title"] == "keep-me"
        assert runtime.read("phrase_b")[0]["title"] == "keep-me"

        with pytest.raises(DestructiveConfirmationRequired) as ctx_b:
            runtime.transact([
                {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase_b = ctx_b.value.details["required_confirmation"]
        assert phrase_b != phrase_a

        result = runtime.transact([
            {"type": "delete", "collection": "phrase_a", "filters": [Filter("title", "eq", "keep-me")],
             "destructive": True, "confirm": phrase_a},
            {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")],
             "destructive": True, "confirm": phrase_b},
        ])
        # Phase 9 WP-3e (design D-7 (3)/(4), Q-1/Q-2): see the identical
        # comment above this test's own sibling assertion for why the
        # LAST item's own dict now also carries `request_id`.
        assert result[-1].pop("request_id")
        assert result == [{"deleted": 1}, {"deleted": 1}]
        assert runtime.read("phrase_a") == []
        assert runtime.read("phrase_b") == []
    finally:
        close_cell(cell)


def test_transact_lone_surrogate_value_is_deterministic_validation_failure_and_earlier_entity_unchanged(app_a) -> None:
    """B-2 (independent review, WP-2 follow-up -- the atomicity hole,
    largest safety fix of that review), pinned on the real Postgres
    backend too: a lone UTF-16 surrogate code point in a LATER
    operation's own value (`"\\ud800"`) must be rejected deterministically
    at VALIDATION time (pass 1, `encode_value`, B-2(ii)) -- not escape as
    a raw `UnicodeEncodeError` from psycopg's own parameter binding during
    pass 2 execution, which pre-fix left the EARLIER, individually-valid
    operation's own write sitting uncommitted-but-visible (B-2(i)'s own
    atomicity hole)."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("surrogate_a", {"title": "text"})
        developer.create_collection("surrogate_b", {"title": "text"})
        with pytest.raises(ValidationError):
            runtime.transact([
                {"type": "insert", "collection": "surrogate_a", "values": {"title": "should-not-persist"}},
                {"type": "insert", "collection": "surrogate_b", "values": {"title": "\ud800"}},
            ])
        assert runtime.read("surrogate_a") == []
        assert runtime.read("surrogate_b") == []
    finally:
        close_cell(cell)


def test_transact_rollback_is_unconditional_for_a_non_foundation_error_raised_mid_pass_2(app_a) -> None:
    """B-2(i) (independent review, WP-2 follow-up), pinned on the real
    Postgres backend too: structural pin of the actual fix itself,
    independent of B-2(ii)'s currently-known trigger -- ANY exception
    raised mid pass-2 execution (here, a synthesized `RuntimeError` from
    a wrapped `insert_in_transaction`) must still trigger `self._backend.
    rollback()` exactly once before propagating, and must leave no
    partial effect from any EARLIER, individually-valid operation in the
    same batch."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("rollback_a", {"title": "text"})
        developer.create_collection("rollback_b", {"title": "text"})
        backend = cell._backend
        rollback_calls = {"count": 0}
        real_rollback = backend.rollback
        real_insert = backend.insert_in_transaction
        call_index = {"n": 0}

        def counting_rollback():
            rollback_calls["count"] += 1
            return real_rollback()

        def failing_second_insert(collection, fields, params):
            call_index["n"] += 1
            if call_index["n"] == 2:
                raise RuntimeError("synthetic non-FoundationError failure")
            return real_insert(collection, fields, params)

        backend.rollback = counting_rollback
        backend.insert_in_transaction = failing_second_insert
        try:
            with pytest.raises(RuntimeError):
                runtime.transact([
                    {"type": "insert", "collection": "rollback_a", "values": {"title": "should-not-persist"}},
                    {"type": "insert", "collection": "rollback_b", "values": {"title": "would-fail-mid-execution"}},
                ])
        finally:
            backend.rollback = real_rollback
            backend.insert_in_transaction = real_insert
        assert rollback_calls["count"] == 1, "rollback must fire exactly once for the non-FoundationError failure"
        assert runtime.read("rollback_a") == []
        assert runtime.read("rollback_b") == []
    finally:
        close_cell(cell)


def test_cross_entity_mutation_is_declared_partial_on_postgres_backend(app_a) -> None:
    """M-1 (independent review, WP-2 follow-up): status is `"partial"`,
    matching `atomic_mutation`'s own declared shape exactly."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        declared = runtime.capabilities()["capabilities"]["cross_entity_mutation"]
        assert declared == {
            "status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"],
        }
        assert runtime.capabilities()["limits"]["batch_entities"] == 10
        assert runtime.capabilities()["limit_enforcement"]["batch_entities"] == "enforced"
    finally:
        close_cell(cell)


def test_schema_revision_bump_on_one_entity_invalidates_stale_delete_confirmation_in_a_cross_entity_batch(app_a) -> None:
    """§2 PG note / §8 risk 2 (P35 WP-2): extends `test_schema_revision_
    bumps_durably_and_invalidates_a_stale_delete_confirmation` above to a
    two-pass, cross-entity batch -- a delete confirmation phrase probed
    BEFORE a schema change on its own entity must stay refused by pass 1
    even when it shares a batch with a well-formed insert on a DIFFERENT
    entity, and neither entity's own state changes."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("gated_cross", {"title": "text"})
        developer.create_collection("sibling_cross", {"title": "text"})
        runtime.insert("gated_cross", {"title": "keep-me"})

        with pytest.raises(DestructiveConfirmationRequired) as ctx:
            runtime.delete("gated_cross", [Filter("title", "eq", "keep-me")])
        stale_phrase = ctx.value.details["required_confirmation"]

        before = cell._backend.schema_revision()
        developer.add_field("gated_cross", "extra", "text")
        after = cell._backend.schema_revision()
        assert after == before + 1

        with pytest.raises(DestructiveConfirmationRequired):
            runtime.transact([
                {"type": "insert", "collection": "sibling_cross", "values": {"title": "should-not-persist"}},
                {"type": "delete", "collection": "gated_cross", "filters": [Filter("title", "eq", "keep-me")],
                 "destructive": True, "confirm": stale_phrase},
            ])
        assert runtime.read("gated_cross")[0]["title"] == "keep-me"
        assert runtime.read("sibling_cross") == []
    finally:
        close_cell(cell)


def test_transact_pass_boundary_schema_change_window_yields_not_found_and_sibling_entity_unchanged(app_a) -> None:
    """M-3 (independent review, WP-2 follow-up, §2 PG note v1.2
    correction): the real window between pass 1 (validation, run OUTSIDE
    `self._lock`) and pass 2 (execution, under `self._lock`/`begin()`)
    is measured directly -- a SEPARATE connection (simulating a genuinely
    concurrent actor, not this same session) drops one planned entity's
    own table in the instant `backend.begin()` is called, i.e. exactly at
    the pass 1/pass 2 boundary, after pass 1 already built a plan
    against the table's PRE-drop existence.

    The resulting failure is `NotFoundError` (`backend_postgres.
    PostgresBackend.insert_in_transaction`'s own translation of
    `psycopg.errors.UndefinedTable`) -- never `DestructiveConfirmationRequired`
    (m-2 correction: that check only ever runs in pass 1, never
    re-evaluated in pass 2). A sibling entity sharing the same batch is
    left entirely unchanged: rollback now fires unconditionally
    (B-2(i)), regardless of which exception type pass 2 raises."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    admin_conn = psycopg.connect(app_a.developer_dsn, autocommit=True)
    try:
        developer.create_collection("window_target", {"title": "text"})
        developer.create_collection("window_sibling", {"title": "text"})
        backend = cell._backend
        real_begin = backend.begin

        def dropping_begin(*, deadline=None):
            with admin_conn.cursor() as cur:
                cur.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier("window_target")))
            return real_begin(deadline=deadline)

        backend.begin = dropping_begin
        try:
            with pytest.raises(NotFoundError):
                runtime.transact([
                    {"type": "insert", "collection": "window_sibling", "values": {"title": "should-not-persist"}},
                    {"type": "insert", "collection": "window_target", "values": {"title": "would-fail-mid-window"}},
                ])
        finally:
            backend.begin = real_begin
        assert runtime.read("window_sibling") == []
    finally:
        admin_conn.close()
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
        # Phase 9 WP-3a (design D-2 (5)): `alter_field` joined `operations`
        # in this same commit as `constraint_declarations` -> `enabled`.
        assert declared["operations"] == ["create_entity", "add_field", "alter_field"]
        assert "add_field" not in declared["unsupported"]
        assert "alter_field" not in declared["unsupported"]

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


# --- Phase 9 WP-3b rework (G-5(d)/review §3 m-6(4)): the `dry_run` branch
# of `PostgresBackend.create_collection`/`.alter_field_constraints` -- C-22
# (the HTTP+PostgreSQL plug) only ever drives `add_field`/`transact`'s own
# dry_run branch through this backend; NO test, peer-local or conformance,
# had exercised these other two before this rework. ---


def test_create_collection_dry_run_rolls_back_ddl_and_registry_writes_on_postgres_backend(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        dry = developer.create_entity(
            "pgbackend_dry_things", fields={"label": "text"}, field_types={"label": "string"}, dry_run=True,
        )
        assert dry["committed"] is False
        assert "label" in dry["descriptor"]["fields"]
        assert dry["descriptor"]["field_types"]["label"] == "string"
        assert isinstance(dry.get("plan"), str) and dry["plan"]

        # The real DDL/registry write was genuinely rolled back -- the
        # entity does not exist for real (`NotFoundError`, not merely
        # "empty"), and a real `create_entity` for the SAME name
        # afterward succeeds cleanly (it would raise `ConflictError` if
        # the dry run's own DDL had actually committed).
        with pytest.raises(NotFoundError):
            runtime.read("pgbackend_dry_things")

        real = developer.create_entity(
            "pgbackend_dry_things", fields={"label": "text"}, field_types={"label": "string"}, plan=dry["plan"],
        )
        assert real["committed"] is True
        runtime.insert("pgbackend_dry_things", {"label": "x"})
        assert runtime.read("pgbackend_dry_things") == [{"label": "x"}]
    finally:
        close_cell(cell)


def test_alter_field_constraints_dry_run_rolls_back_the_existing_row_scan_and_registry_write_on_postgres_backend(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("pgbackend_dry_alter_things", {"label": "text"})
        runtime.insert("pgbackend_dry_alter_things", {"label": "kept"})

        dry = developer.alter_field("pgbackend_dry_alter_things", "label", nullable=False, dry_run=True)
        assert dry["committed"] is False
        assert dry["descriptor"]["field_constraints"]["label"]["nullable"] is False

        # Real catalog is unchanged: still nullable (`_backend.
        # alter_field_constraints`'s own existing-row scan ran for real
        # -- there was one non-null row, so it would NOT have conflicted
        # either way -- but the registry write and the revision bump were
        # both rolled back).
        catalog = {row["entity"]: row for row in developer.catalog()}
        assert catalog["pgbackend_dry_alter_things"]["field_constraints"]["label"]["nullable"] is True

        # The real (non-dry-run) alter_field for the SAME declaration
        # still commits for real, using the SAME plan the dry run
        # returned (the revision has not moved since -- this is the same
        # scenario `test_plan_is_deterministic_and_valid_against_
        # unchanged_schema` pins for a mutation, exercised here against
        # the Postgres backend's own alter_field_constraints dry_run
        # branch specifically).
        real = developer.alter_field("pgbackend_dry_alter_things", "label", nullable=False, plan=dry["plan"])
        assert real["committed"] is True
        catalog_after = {row["entity"]: row for row in developer.catalog()}
        assert catalog_after["pgbackend_dry_alter_things"]["field_constraints"]["label"]["nullable"] is False

        # A CONFLICTING dry run (an existing NULL row) still raises
        # `ConflictError` for real -- the existing-row scan is not
        # skipped for a dry run, only the registry write/commit are.
        developer.add_field("pgbackend_dry_alter_things", "optional_field", "text")
        runtime.insert("pgbackend_dry_alter_things", {"label": "has-null-optional"})
        with pytest.raises(ConflictError):
            developer.alter_field("pgbackend_dry_alter_things", "optional_field", nullable=False, dry_run=True)
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
        # PostgresBackend`'s own `_TYPES` comment) (in `postgres_types.py`).
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


# --- 追補 4 O-2 (版フリップ監査 §5/§15, `{scratchpad}/rulings-r3-r7-flip. --
# --- md`): embedded NUL / lone surrogate / int32/int64 RANGE denials -------
# --- reached from a NORMAL client request must carry the 4-key form -------


def test_postgres_only_value_domain_denials_reachable_from_a_normal_client_request_carry_the_4_key_form(app_a) -> None:
    """The two PostgreSQL-only value-domain conditions with NO SQLite
    equivalent (`tests/test_denial_details_and_request_id.py`'s own
    sibling test covers the two conditions both backends share: lone
    surrogate, out-of-range integer) -- embedded NUL, and the
    int32-range (`boolean` field type's own physical `INTEGER` column)
    bound -- reached via `runtime.insert`/`runtime.read` exactly as an
    ordinary client would, never a direct `_validate_value_domain`/
    `encode_value` call. Before this WP's own closure fix these returned
    `VALIDATION_FAILED` with an EMPTY `details` (版フリップ監査 §5's own
    finding, the http+postgres plug's 3 probed cases); now they must
    carry `violated_declaration: field_type` plus the full type-pair
    (`declared_type`/`observed_type`) and a request-internal `field`."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("domain_probe_pg", {"label": "text", "flag": "boolean", "n": "integer"})

        with pytest.raises(ValidationError) as ctx:
            runtime.insert("domain_probe_pg", {"label": "a\x00b"})
        details = ctx.value.details
        assert details["violated_declaration"] == "field_type"
        assert details["declared_type"] == "string"
        assert details["observed_type"] == "string"
        assert details["field"] == "operations/0/values/label"

        with pytest.raises(ValidationError) as ctx:
            runtime.insert("domain_probe_pg", {"label": "\ud800"})
        details = ctx.value.details
        assert details["violated_declaration"] == "field_type"
        assert details["declared_type"] == "string"
        assert details["field"] == "operations/0/values/label"

        for big in (2 ** 80, -(2 ** 80)):
            with pytest.raises(ValidationError) as ctx:
                runtime.insert("domain_probe_pg", {"n": big})
            details = ctx.value.details
            assert details["violated_declaration"] == "field_type"
            assert details["declared_type"] == "integer"
            assert details["observed_type"] == "integer"
            assert details["field"] == "operations/0/values/n"

        # `_bind_filters`'s own predicate-value choke point (`where/<i>/
        # value`), not a values path -- same gate, different caller.
        with pytest.raises(ValidationError) as ctx:
            runtime.read("domain_probe_pg", filters=[Filter("n", "eq", 2 ** 80)])
        details = ctx.value.details
        assert details["violated_declaration"] == "field_type"
        assert details["field"] == "where/0/value"

        # Connection recovery: every rejection above must leave the cell
        # usable for ordinary operations afterward, matching this file's
        # own established B-1 (ii) precedent.
        runtime.insert("domain_probe_pg", {"label": "ok", "flag": True, "n": 1})
        assert len(runtime.read("domain_probe_pg")) == 1
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


def test_postgres_backend_rejects_an_injection_shaped_order_by_direction(app_a) -> None:
    """M-4 (independent WP-3 review): a direct, backend-level test --
    bypassing `cell.py` entirely, exactly mirroring `MitateDB-api/tests/
    test_order_by_direction_hardening.py`'s identical SQLite-backend test
    -- proving `PostgresBackend.read()`'s own `_DIRECTION_SQL` (now in `postgres_sql.py`) closed dict
    lookup rejects an unexpected `direction` value with `errors.
    ValidationError` (a classified failure, not the raw, untranslated
    `KeyError` this call site used to raise before this fix -- that
    `KeyError` happened before the surrounding `try/except psycopg.Error`
    block, so it was never caught at all)."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("orderby_probe", {"item_key": "integer"})
        with pytest.raises(ValidationError):
            cell._backend.read("orderby_probe", ["item_key"], [], [("item_key", "asc); SELECT 1 --")], 10)
        with pytest.raises(ValidationError):
            cell._backend.read("orderby_probe", ["item_key"], [], [("item_key", "ASC, (SELECT 1)")], 10)
        # Regression guard: the two real directions still work.
        assert cell._backend.read("orderby_probe", ["item_key"], [], [("item_key", "asc")], 10) == []
        assert cell._backend.read("orderby_probe", ["item_key"], [], [("item_key", "desc")], 10) == []
    finally:
        close_cell(cell)


def test_validate_value_domain_accepts_none_for_every_domain() -> None:
    """M-5, at the mechanism level (m-8 (i), no DB connection needed):
    `_validate_value_domain`/`_check_domain` are plain, connection-
    independent functions -- called here directly to pin the fix at its
    own source, independent of the full insert/read round trip above."""
    from mitatedb_api.backend_postgres import _validate_value_domain

    assert _validate_value_domain(None, domain=None) is None
    assert _validate_value_domain(None, domain="string") is None
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
    # Phase 6 WP-3 (design D-3, L6-1 (v)): the shared "text" domain name
    # is retired -- `string`/`object`/`array`/`json` are now distinct
    # domain names (`_TEXT_DOMAIN_BY_DECLARED_TYPE`), all still checked
    # as `isinstance(value, str)` (the real object-vs-array-vs-json shape
    # check runs upstream, at the cell-layer choke point, design G3).
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _validate_value_domain(123, domain="string")
    # `None` still bypasses everything (M-5), and a matching value still
    # passes through unchanged -- this test is about the CHECK actually
    # running, not about over-tightening it.
    assert _validate_value_domain(None, domain="int64") is None
    assert _validate_value_domain(42, domain="int64") == 42
    assert _validate_value_domain(None, domain="float") is None


# --- BP2 (R-37 WP-1n): PostgreSQL value-domain gate, connection- ----------
# --- independent unit tests of the mechanism itself -------------------------


def test_postgres_value_domain_leaf_preserves_backend_postgres_facade() -> None:
    """Pins that `backend_postgres._validate_value_domain` is the same
    object as `postgres_value_domain._validate_value_domain` -- no live
    PostgreSQL server needed. `_check_domain`/`_INT_DOMAIN_RANGES`
    are already pinned as facade names by `test_check_domain_type_
    mismatches_are_rejected_at_the_mechanism_level`/`test_check_domain_
    range_boundaries_at_the_mechanism_level` below (Y-3), so this test
    does not repeat them."""
    from mitatedb_api import backend_postgres
    from mitatedb_api.postgres_value_domain import _validate_value_domain

    assert backend_postgres._validate_value_domain is _validate_value_domain


def test_validate_value_domain_converts_bool_to_int_before_the_domain_check() -> None:
    """Mechanism-level pin for the `bool`-before-domain-check conversion
    (`isinstance(True, int)` is `True` in Python, which would otherwise
    let a stray `bool` slip through an `int` domain check unconverted,
    see `_validate_value_domain`'s own comment) -- the converted value is
    a plain `int`, not `bool`, and compares equal to `1`."""
    from mitatedb_api.backend_postgres import _validate_value_domain

    converted = _validate_value_domain(True, domain="int32")
    assert converted == 1
    assert type(converted) is int


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
    from mitatedb_api.postgres_value_domain import _check_domain as leaf_check_domain

    assert _check_domain is leaf_check_domain

    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-number", "int64")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-bool", "int32")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain("not-a-float", "float")
    # Phase 6 WP-3 (design D-3, L6-1 (v)): see the identical comment in
    # `test_validate_value_domain_actually_invokes_the_domain_check` above.
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain(123, "string")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain(123, "object")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain(123, "array")
    with pytest.raises(ValidationError, match="does not match the declared field type"):
        _check_domain(123, "json")


def test_check_domain_range_boundaries_at_the_mechanism_level() -> None:
    """m-8 (i): this is what actually catches the reviewer's own mutation
    (A) (removing the range check inside `_check_domain`'s int branch,
    keeping only the `isinstance(value, int)` type check) -- with the
    range check removed, `10 ** 30`/an out-of-int32-range value would
    pass this function with NO exception at all, a hard, unmasked failure
    (unlike the full integration path, where PostgreSQL's own driver
    would still raise SOME error the layer-(ii) backstop reclassifies
    into an indistinguishable `ValidationError`)."""
    from mitatedb_api.backend_postgres import _INT_DOMAIN_RANGES, _check_domain
    from mitatedb_api.postgres_value_domain import _INT_DOMAIN_RANGES as leaf_int_domain_ranges

    assert _INT_DOMAIN_RANGES is leaf_int_domain_ranges

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

    # float and the four str-shaped domains: type-check only (no range
    # concept for any of them). Phase 6 WP-3 (design D-3, L6-1 (v)):
    # `string`/`object`/`array`/`json` replace the former single shared
    # `"text"` domain name (`_TEXT_DOMAIN_BY_DECLARED_TYPE`).
    assert _check_domain(1, "float") == 1.0
    assert _check_domain(1.5, "float") == 1.5
    assert _check_domain("hello", "string") == "hello"
    assert _check_domain("{}", "object") == "{}"
    assert _check_domain("[]", "array") == "[]"
    assert _check_domain('"x"', "json") == '"x"'
    # An unrecognized domain string is passed through unchanged -- this
    # function itself has no "unknown domain" error path, by design: a
    # `field_domains` caller only ever passes one of the domain names it
    # itself produces.
    assert _check_domain("anything", "not-a-real-domain") == "anything"


# --- BP1 (R-37 WP-1m): PostgreSQL type-mapping constants, connection- ------
# --- independent unit tests of the mechanism itself -------------------------


def test_postgres_types_pin_native_column_types_and_domains() -> None:
    """Pins the three type-mapping tables in `postgres_types.py`
    (`_TYPES` via `_TYPE_SQL`; `backend_postgres.py` does not re-export
    `_TYPES`, Y-7) as literal values, no live PostgreSQL server needed. `_TYPE_SQL`'s values are
    real `sql.SQL` constants (m-7), never a bare Python string or a
    `sql.Identifier` (that distinction matters: a column TYPE keyword is
    composed via `sql.SQL`, a catalog object name via `sql.Identifier`)."""
    from mitatedb_api.postgres_types import (_TYPE_SQL, _DOMAIN_BY_DATA_TYPE,
                                              _TEXT_DOMAIN_BY_DECLARED_TYPE)

    assert _TYPE_SQL == {
        "text": sql.SQL("TEXT"),
        "integer": sql.SQL("BIGINT"),
        "real": sql.SQL("DOUBLE PRECISION"),
        "boolean": sql.SQL("INTEGER"),
        "json": sql.SQL("TEXT"),
    }
    assert all(type(value) is sql.SQL for value in _TYPE_SQL.values())
    assert _DOMAIN_BY_DATA_TYPE == {
        "bigint": "int64",
        "integer": "int32",
        "double precision": "float",
    }
    assert _TEXT_DOMAIN_BY_DECLARED_TYPE == {
        "string": "string",
        "object": "object",
        "array": "array",
        "json": "json",
    }


# --- BP4 (R-37 WP-1l): PostgreSQL reserved-name checks, connection- --------
# --- independent unit tests of the mechanism itself -------------------------


def test_postgres_reserved_names_leaf_preserves_backend_postgres_facade() -> None:
    """WP-1l facade compatibility: `_RESERVED_EXACT`/`_RESERVED_PREFIX`/
    `_check_reserved_name` are re-exported, unchanged, from `backend_
    postgres.py` after their extraction into `postgres_reserved_names.py`
    -- no live PostgreSQL server needed."""
    from mitatedb_api import backend_postgres
    from mitatedb_api.postgres_reserved_names import (_RESERVED_EXACT, _RESERVED_PREFIX,
                                                       _check_reserved_name)

    assert backend_postgres._RESERVED_EXACT is _RESERVED_EXACT
    assert backend_postgres._RESERVED_PREFIX is _RESERVED_PREFIX
    assert backend_postgres._check_reserved_name is _check_reserved_name


def test_postgres_backend_check_reserved_refuses_pg_prefix_and_audit_events_exactly() -> None:
    """BP4: `PostgresBackend.check_reserved` does not read `self` (m-8),
    so this pins the reserved-name check directly, without a live
    PostgreSQL server -- closing the SI-04 gap this WP found (no existing
    test fixed the `pg_`-prefix / `audit_events`-exact-match behaviour):
    the `pg_` prefix and the exact name `audit_events` are refused, a
    name that merely starts with `audit_events` or merely ends with
    `pg_` is not, and the denial `details` are exactly the
    `identifier_syntax` violation form (`field` = the caller's own
    `label`, no `declared_type`/`observed_type`)."""
    with pytest.raises(ValidationError) as excinfo:
        PostgresBackend.check_reserved(None, "pg_x", "collection")
    assert excinfo.value.details == {"violated_declaration": "identifier_syntax", "field": "collection"}

    with pytest.raises(ValidationError) as excinfo:
        PostgresBackend.check_reserved(None, "audit_events", "entity")
    assert excinfo.value.details == {"violated_declaration": "identifier_syntax", "field": "entity"}

    assert PostgresBackend.check_reserved(None, "audit_events2", "entity") is None
    assert PostgresBackend.check_reserved(None, "audit_event", "entity") is None
    assert PostgresBackend.check_reserved(None, "xpg_", "entity") is None


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


# --- WP-2 (design v1.2 R-4/§3): credential store persistence + parity -----

_PARITY_PEPPER = "synthetic-parity-test-pepper-0123456789"


@pytest.fixture
def credential_app(platform) -> Iterator[str]:
    """A lightweight "registered, unprovisioned" application row (R-4
    two-state registry) -- exactly the shape `test_two_state_registry_
    allows_deprovisioning_a_registered_but_unprovisioned_application`
    above already proves 0004 can fully clean up. The credential-store
    parity tests below only exercise `mitatedb_registry.credentials`/
    `applications.enabled`, never a real per-application database or role
    pair, so provisioning one (`provision_app`) would only add cost with
    no additional coverage.
    """
    app_id = "credpar" + secrets.token_hex(4)
    conn = psycopg.connect(platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("INSERT INTO {}.applications (application_id) VALUES (%s)").format(
                    sql.Identifier(platform.registry_schema)
                ),
                [app_id],
            )
    finally:
        conn.close()
    try:
        yield app_id
    finally:
        _run_psql(platform.provision_dsn, platform.deprovision_script, {"app_id": app_id})


class _InMemoryCredentialHarness:
    """`mitatedb_api.auth.CredentialStore` side of the shared parity
    scenario below -- a fresh in-memory store + a single fresh
    application, so this harness never shares state with any other test.
    """

    def __init__(self) -> None:
        self.store = CredentialStore(_PARITY_PEPPER)
        self.app_id = "credparim"
        self.store.provision_application(self.app_id)

    def issue(self, role):
        return self.store.issue(self.app_id, role)

    def authenticate(self, secret):
        return self.store.authenticate(secret)

    def assert_active(self, principal):
        self.store.assert_active(principal)

    def disable(self, credential_id):
        self.store.disable(credential_id)

    def enable(self, credential_id):
        self.store.enable(credential_id)

    def revoke(self, credential_id):
        self.store.revoke(credential_id)

    def disable_application(self):
        return self.store.disable_application(self.app_id)

    def enable_application(self):
        return self.store.enable_application(self.app_id)


class _PostgresCredentialHarness:
    """`credential_store_postgres.PostgresCredentialStore` side of the
    shared parity scenario below. Mirrors R-4's own process-role
    separation for real: `writer` connects as `{prefix}svc_controlplane`
    (the only role with INSERT/UPDATE on `credentials`/`applications`,
    migration 0002) and is used for every lifecycle-changing call;
    `reader` connects as `{prefix}svc_api` (SELECT-only) and is used for
    every read (`authenticate`/`assert_active`) -- exactly the two
    process roles a real application-plane process and a real
    control-plane process would each hold in production, never the same
    connection performing both.
    """

    def __init__(self, platform, app_id: str) -> None:
        self.app_id = app_id
        self.writer = PostgresCredentialStore(
            platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema
        )
        self.reader = PostgresCredentialStore(
            platform.api_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema
        )

    def issue(self, role):
        # Phase 6 WP-3 (design D-1(d)): `PostgresCredentialStore.issue`
        # now returns the composed bearer, not the bare secret (this is
        # the store an HTTP bearer is actually built from -- unlike
        # `auth.CredentialStore`, see that class's own docstring). This
        # harness's own scenario script authenticates with the bare
        # secret directly (mirroring `authenticate`'s own unchanged,
        # raw-secret receiving side), so it recovers that raw secret
        # here, once, rather than pushing bearer-composition awareness
        # into the shared scenario script itself.
        credential_id, bearer = self.writer.issue(self.app_id, role)
        secret = bearer
        return credential_id, secret

    def authenticate(self, secret):
        return self.reader.authenticate(secret)

    def assert_active(self, principal):
        self.reader.assert_active(principal)

    def disable(self, credential_id):
        self.writer.disable(credential_id)

    def enable(self, credential_id):
        self.writer.enable(credential_id)

    def revoke(self, credential_id):
        self.writer.revoke(credential_id)

    def disable_application(self):
        return self.writer.disable_application(self.app_id)

    def enable_application(self):
        return self.writer.enable_application(self.app_id)


def _assert_contract_credential_lifecycle(harness) -> None:
    """WP-2 instruction #3: ONE scenario script, driven through the
    harness's shared call surface against BOTH `auth.CredentialStore` and
    `credential_store_postgres.PostgresCredentialStore` (see the two
    harness classes above). Parity is judged against the CONTRACT's own
    lifecycle rules (spec/data-service-api.v1.json `lifecycle.credential`
    / `enable_credential.semantics`) -- WP-2's own explicit instruction is
    that "現行 in-memory の挙動" is never the standard, so every assertion
    below cites the contract text it enforces, not "whatever the old code
    already did".
    """
    # issue -> authenticate succeeds.
    credential_id, secret = harness.issue(Role.RUNTIME)
    principal = harness.authenticate(secret)
    assert principal.role == Role.RUNTIME
    harness.assert_active(principal)  # must not raise

    # disable -> authenticate refused ("Disable/enable are reversible
    # operational states", lifecycle.credential).
    harness.disable(credential_id)
    with pytest.raises(AuthenticationError):
        harness.authenticate(secret)
    with pytest.raises(AuthenticationError):
        harness.assert_active(principal)

    # enable -> revived (disable's own reversal).
    harness.enable(credential_id)
    principal = harness.authenticate(secret)
    harness.assert_active(principal)

    # role mismatch -> refused: `assert_active` re-checks the caller's own
    # claimed role against the credential's real, server-bound role.
    tampered = Principal(principal.application_id, principal.credential_id, Role.DEVELOPER)
    with pytest.raises(AuthenticationError):
        harness.assert_active(tampered)

    # revoke -> authenticate refused ("Revocation is terminal: a revoked
    # credential can never be made valid again", lifecycle.credential).
    harness.revoke(credential_id)
    with pytest.raises(AuthenticationError):
        harness.authenticate(secret)

    # enable after revoke -> STILL refused. This is the parity-defining
    # assertion WP-2 exists for: "Reverses disable only. A revoked
    # credential is not resurrected." (enable_credential.semantics).
    harness.enable(credential_id)
    with pytest.raises(AuthenticationError):
        harness.authenticate(secret)
    with pytest.raises(AuthenticationError):
        harness.assert_active(principal)

    # unknown credential id -> refused, never a crash or a different
    # exception type than any other authentication failure.
    with pytest.raises(AuthenticationError):
        harness.authenticate("no-such-credential-id-ever-issued.whatever-secret")

    # disabled Application -> "A disabled Application rejects all
    # application-facing operations" (lifecycle.application) even for a
    # credential that was never itself disabled or revoked.
    other_id, other_secret = harness.issue(Role.DEVELOPER)
    other_principal = harness.authenticate(other_secret)
    # WP-2 review m-1: `disable_application`/`enable_application` report
    # whether the application id existed (`True` here -- this harness's
    # own application was set up by the caller) rather than staying
    # silent either way.
    assert harness.disable_application() is True
    with pytest.raises(AuthenticationError):
        harness.authenticate(other_secret)
    with pytest.raises(AuthenticationError):
        harness.assert_active(other_principal)
    assert harness.enable_application() is True
    harness.authenticate(other_secret)  # revived


def test_inmemory_credential_lifecycle_matches_the_contract() -> None:
    """Baseline: the SAME scenario script the PostgreSQL-backed test below
    runs, against `auth.CredentialStore` -- proves the in-memory store's
    own WP-2 rewrite (enabled/revoked independence) is contract-correct
    with no PostgreSQL involved at all."""
    _assert_contract_credential_lifecycle(_InMemoryCredentialHarness())


def test_postgres_credential_lifecycle_matches_the_contract(platform, credential_app) -> None:
    """WP-2 instruction #3: the identical scenario script above, run
    against `PostgresCredentialStore` instead -- the actual dual-
    implementation parity proof. Any divergence between this test's
    outcome and `test_inmemory_credential_lifecycle_matches_the_contract`
    above is, by construction, a real parity gap between the two stores."""
    _assert_contract_credential_lifecycle(_PostgresCredentialHarness(platform, credential_app))


def test_postgres_credential_store_construction_rejects_a_missing_or_short_pepper() -> None:
    """WP-2 instruction #4: fail-closed STORE CONSTRUCTION, mirroring
    `auth.CredentialStore.__init__`'s identical existing rule -- a process
    that somehow starts with no real pepper configured must never come up
    able to authenticate anything."""
    with pytest.raises(ValueError):
        PostgresCredentialStore("host=/tmp port=1 dbname=mitatedb_credential_store_construction_missing_pepper", pepper=None)
    with pytest.raises(ValueError):
        PostgresCredentialStore("host=/tmp port=1 dbname=mitatedb_credential_store_construction_short_pepper", pepper="too-short")


def test_postgres_credential_pepper_env_var_is_honored_when_no_explicit_pepper_is_given(monkeypatch) -> None:
    monkeypatch.setenv("MITATEDB_CREDENTIAL_PEPPER", _PARITY_PEPPER)
    store = PostgresCredentialStore("host=/tmp port=1 dbname=mitatedb_credential_store_pepper_env_var_placeholder")
    assert store is not None  # construction alone must not touch the network


def test_pepper_separation_detects_the_two_env_vars_configured_identically() -> None:
    """WP-2 instruction #4: the cross-check function itself (no
    composition root calls it yet in this WP -- see the function's own
    docstring). Only raises when BOTH values are present, non-empty, AND
    equal; either value missing is a distinct, already-fail-closed concern
    each store's own constructor already owns, not this function's job."""
    with pytest.raises(ValueError):
        assert_pepper_separation("same-secret-value-0123456789", "same-secret-value-0123456789")
    assert_pepper_separation("app-secret-0123456789", "control-secret-0123456789")
    assert_pepper_separation(None, "control-secret-0123456789")
    assert_pepper_separation("app-secret-0123456789", None)
    assert_pepper_separation(None, None)
    assert_pepper_separation("", "")


def test_postgres_credential_store_fails_closed_when_the_database_is_unreachable() -> None:
    """WP-2 instruction #5: a `PostgresCredentialStore` pointed at a DSN
    that cannot be connected to at all must raise `errors.
    AuthorizationStateUnavailable` -- this foundation's dedicated
    fail-closed exception for "we could not verify this" -- from every
    read path, never a raw `psycopg.Error`, and never silently treat
    "could not check" as "credential invalid" (`AuthenticationError` would
    be the wrong, fail-OPEN-shaped outcome here: it would let an operator
    mistake "the platform database is down" for "that credential does not
    exist"). Port 1 on the loopback admin/tcp path is not a real
    PostgreSQL listener in this test environment -- `connect_timeout=1`
    keeps this test from hanging on a black-holed port.

    WP-2 review m-3: deliberately takes no fixture at all (no `platform`,
    no `credential_app`) -- this test's own point is that it is entirely
    independent of whether a real local PostgreSQL cluster exists; pulling
    in `credential_app` (and therefore the module-scoped `platform`
    bootstrap) would make an otherwise network-independent test depend on
    unrelated cluster setup it never actually uses.
    """
    unreachable_dsn = "host=127.0.0.1 port=1 dbname=nonexistent connect_timeout=1"
    store = PostgresCredentialStore(unreachable_dsn, pepper=_PARITY_PEPPER, connect_timeout=1)
    with pytest.raises(AuthorizationStateUnavailable):
        store.authenticate("any-credential-id.any-secret")
    with pytest.raises(AuthorizationStateUnavailable):
        store.assert_active(Principal("any-app", "any-credential-id", Role.RUNTIME))
    with pytest.raises(AuthorizationStateUnavailable):
        store.get_state("any-credential-id")
    with pytest.raises(AuthorizationStateUnavailable):
        store.issue("any-app", Role.RUNTIME)
    with pytest.raises(AuthorizationStateUnavailable):
        store.revoke("any-credential-id")
    with pytest.raises(AuthorizationStateUnavailable):
        store.disable("any-credential-id")
    with pytest.raises(AuthorizationStateUnavailable):
        store.enable("any-credential-id")
    with pytest.raises(AuthorizationStateUnavailable):
        store.disable_application("any-app")
    with pytest.raises(AuthorizationStateUnavailable):
        store.enable_application("any-app")


def test_postgres_credential_store_rejects_a_nul_bearing_locator_before_any_lookup(platform) -> None:
    """WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 3,
    review F4): before `split_bearer_locator`'s own NUL-byte check
    existed, a bearer like `crd_x\\x00y.secret` would split "successfully"
    into a `credential_id` half carrying a NUL byte, which this store then
    bound as a REAL SQL query parameter -- psycopg refuses a NUL-bearing
    `text` parameter outright, and `authenticate`'s own generic `except
    psycopg.Error` mapped that to `AuthorizationStateUnavailable` (503,
    `AUTH_STATE_UNAVAILABLE`), a client-triggerable state-unavailable
    response that is also never durably audited (`AUTH_STATE_UNAVAILABLE`
    is not in the durable-denial code set) -- SI-14 regression.

    Exercised here against a REAL, reachable PostgreSQL connection (not a
    mock) specifically so this test would ALSO have caught the failure
    mode if the NUL check were somehow bypassed and a NUL byte genuinely
    reached psycopg: this store's own `authenticate` must raise `errors.
    AuthenticationError` (401-shaped, `AUTH_INVALID`), never `errors.
    AuthorizationStateUnavailable` (503-shaped), for either NUL-bearing
    half -- proving the rejection happens BEFORE any lookup, not merely
    that some exception was raised."""
    store = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    for locator in ("crd_\x00nulid.secret", "crd_nulid.sec\x00ret"):
        # `pytest.raises(AuthenticationError)` is already the load-bearing
        # distinction here -- `AuthorizationStateUnavailable` is a SIBLING
        # class (both extend `errors.FoundationError` independently), not
        # a subclass, so this block fails the test outright if a
        # regression ever raises that 503-shaped exception instead.
        with pytest.raises(AuthenticationError):
            store.authenticate(locator)


def test_postgres_credential_store_get_state_reports_both_independent_booleans(platform, credential_app) -> None:
    """R-4/CredentialsResult/CredentialStateResult: `enabled`/`revoked`
    are two independently-observable booleans on the PostgreSQL store
    too, not merely internally-independent-but-externally-conflated
    ones."""
    writer = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    credential_id, _secret = writer.issue(credential_app, Role.RUNTIME)
    assert writer.get_state(credential_id) == (True, False)
    writer.disable(credential_id)
    assert writer.get_state(credential_id) == (False, False)
    writer.enable(credential_id)
    assert writer.get_state(credential_id) == (True, False)
    writer.revoke(credential_id)
    assert writer.get_state(credential_id) == (True, True)
    writer.enable(credential_id)
    assert writer.get_state(credential_id) == (True, True), "enable must never clear revoked"
    assert writer.get_state("no-such-credential-id") is None


def test_postgres_credential_store_write_paths_reject_unknown_credential_ids(platform, credential_app) -> None:
    """Fail-closed parity with `auth.CredentialStore`: revoking/disabling/
    enabling a credential id that does not exist must raise `NotFoundError`,
    never silently succeed (an operator must not be told, by silence, that
    a nonexistent credential was revoked/disabled/enabled)."""
    writer = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    with pytest.raises(NotFoundError):
        writer.revoke("no-such-credential-id")
    with pytest.raises(NotFoundError):
        writer.disable("no-such-credential-id")
    with pytest.raises(NotFoundError):
        writer.enable("no-such-credential-id")


def test_postgres_credential_store_issue_rejects_an_unknown_application(platform) -> None:
    writer = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    with pytest.raises(AuthenticationError):
        writer.issue("no-such-application-id", Role.RUNTIME)


# --- WP-2 review M-1: permanent privilege misconfiguration is its own ------
# --- classification, never folded into AuthorizationStateUnavailable ------


def test_postgres_credential_store_write_methods_via_a_read_only_role_raise_storage_configuration_error(
    platform, credential_app
) -> None:
    """WP-2 review M-1 (blocker-adjacent): `mitatedbsvc_api` (migration
    0002) has `SELECT`-only on `credentials`/`applications` -- calling any
    write method through a store constructed with `platform.api_dsn` hits
    a REAL PostgreSQL `InsufficientPrivilege`, a PERMANENT grant
    misconfiguration for this role, never a transient one. This must
    raise `errors.StorageConfigurationError`, never `errors.
    AuthorizationStateUnavailable` (that class's own contract meaning --
    "could not be safely established right now" -- would be a lie here:
    retrying changes nothing about this role's own grants) and never a
    raw `psycopg.errors.InsufficientPrivilege` escaping this module's
    safe-classification boundary.
    """
    read_only = PostgresCredentialStore(platform.api_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    with pytest.raises(StorageConfigurationError):
        read_only.issue(credential_app, Role.RUNTIME)
    with pytest.raises(StorageConfigurationError):
        read_only.revoke("does-not-matter-privilege-fails-first")
    with pytest.raises(StorageConfigurationError):
        read_only.disable("does-not-matter-privilege-fails-first")
    with pytest.raises(StorageConfigurationError):
        read_only.enable("does-not-matter-privilege-fails-first")
    with pytest.raises(StorageConfigurationError):
        read_only.disable_application(credential_app)
    with pytest.raises(StorageConfigurationError):
        read_only.enable_application(credential_app)


@pytest.fixture
def no_select_grant_dsn(platform) -> Iterator[str]:
    """WP-2 review M-1: an ad hoc, throwaway login role with `CONNECT` on
    the platform database but NO grant of any kind on `mitatedb_registry`
    (not even `USAGE` on the schema) -- unlike every other role this
    module's own tests use, this one cannot even attempt a `SELECT`
    without PostgreSQL refusing it at the schema level. Exists solely to
    prove the READ-path `InsufficientPrivilege` reclassification (`
    authenticate`/`assert_active`/`get_state`) against a REAL grant
    boundary, not only via `mitatedbsvc_api` (which legitimately can read,
    so it cannot demonstrate a READ failing on privilege). Created and
    dropped via `platform.admin_dsn` (superuser), independent of the
    provisioning role's own `CREATEROLE` authority -- this role is not
    part of R-4's own provisioning topology at all, purely a test
    fixture.
    """
    role = "credparnopriv" + secrets.token_hex(4)
    password = secrets.token_urlsafe(24)
    admin = psycopg.connect(platform.admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} CONNECTION LIMIT 2").format(
                sql.Identifier(role), sql.Literal(password)
            ))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(platform.platform_db), sql.Identifier(role)
            ))
        yield _dsn_with(platform.admin_dsn, user=role, password=password, dbname=platform.platform_db)
    finally:
        with admin.cursor() as cur:
            # `DROP ROLE` refuses while this role's own `GRANT CONNECT`
            # above is still a live dependency (`DependentObjectsStillExist:
            # ... privileges for database`) -- revoke it first.
            cur.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                sql.Identifier(platform.platform_db), sql.Identifier(role)
            ))
            cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        admin.close()


def test_postgres_credential_store_reads_via_a_no_privilege_role_raise_storage_configuration_error(
    platform, no_select_grant_dsn,
) -> None:
    """WP-2 review M-1: the READ-path counterpart to the write-path test
    above -- `authenticate`/`assert_active`/`get_state` against a role
    with no grant at all on the registry schema must ALSO raise `errors.
    StorageConfigurationError`, not `errors.AuthorizationStateUnavailable`.
    """
    store = PostgresCredentialStore(no_select_grant_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    with pytest.raises(StorageConfigurationError):
        store.authenticate("any-credential-id.any-secret")
    with pytest.raises(StorageConfigurationError):
        store.assert_active(Principal("any-app", "any-credential-id", Role.RUNTIME))
    with pytest.raises(StorageConfigurationError):
        store.get_state("any-credential-id")


# --- WP-2 review m-1: disable_application/enable_application report -------
# --- whether a row existed, instead of staying silent either way ----------


def test_inmemory_disable_enable_application_report_whether_the_application_existed() -> None:
    store = CredentialStore(_PARITY_PEPPER)
    store.provision_application("credparbool")
    assert store.disable_application("credparbool") is True
    assert store.enable_application("credparbool") is True
    assert store.disable_application("no-such-application-id") is False
    assert store.enable_application("no-such-application-id") is False


def test_postgres_disable_enable_application_report_whether_the_application_existed(platform, credential_app) -> None:
    writer = PostgresCredentialStore(platform.controlplane_dsn, pepper=_PARITY_PEPPER, schema=platform.registry_schema)
    assert writer.disable_application(credential_app) is True
    assert writer.enable_application(credential_app) is True
    assert writer.disable_application("no-such-application-id") is False
    assert writer.enable_application("no-such-application-id") is False


# --- WP-2 review m-5: a role value outside Role's own vocabulary is a -----
# --- store-integrity fault, never silently downgraded to AuthenticationError


def test_role_or_state_unavailable_classifies_an_out_of_vocabulary_role_as_state_unavailable() -> None:
    """WP-2 review m-5: `_role_or_state_unavailable` is the single choke
    point `authenticate`/`assert_active` both route a DB-sourced `role`
    string through. A value outside `Role`'s own two members (`"runtime"`/
    `"developer"`) must raise `errors.AuthorizationStateUnavailable` (a
    store-integrity fault), never a bare `ValueError` (which would escape
    this module's safe-classification boundary entirely) and never
    silently produce a usable `Role` that would let a corrupted row
    authenticate as some arbitrary role.
    """
    assert _role_or_state_unavailable("runtime") == Role.RUNTIME
    assert _role_or_state_unavailable("developer") == Role.DEVELOPER
    with pytest.raises(AuthorizationStateUnavailable):
        _role_or_state_unavailable("control")  # a real contract role enum member, but not one this table's CHECK allows
    with pytest.raises(AuthorizationStateUnavailable):
        _role_or_state_unavailable("garbage-not-a-role-at-all")


# ===========================================================================
# Phase 6 WP-3 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-3): declared-type registry -- round trip, negative validation,
# catalog shape, migration 0006 backfill. All against the PostgreSQL
# backend (`test_foundation.py` carries the sqlite/in-process parity
# half -- design's own non-vacuity requirement that the choke point is
# real on BOTH backends, not only the one with a live domain concept).
# ===========================================================================


def _typed_fields(contract_types: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """`ApplicationCell.create_collection`/`create_entity`'s own `fields`
    parameter is `{name: FOUNDATION_type}` (`_FIELD_TYPE_VOCABULARY`,
    the low-level, pre-1.6.0 shape -- unlike `http.py`'s own wire-facing
    `fields` array of bare names) -- `field_types` (this WP's own new
    parameter) is a SEPARATE, parallel `{name: CONTRACT_type}` map. This
    helper builds both from one `{name: contract_type}` mapping, the
    shape these tests want to express directly."""
    fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[contract_type] for name, contract_type in contract_types.items()}
    return fields, dict(contract_types)


def test_declared_type_registry_round_trips_every_contract_type(app_a) -> None:
    """Write-then-read parity for all 7 contract-vocabulary types,
    exercised through `create_entity`'s own `field_types` (this WP's new
    capability): `object`/`array`/`json` come back as the EXACT JSON
    value written (design F2, never a string a caller must `json.loads()`
    again), and `boolean` comes back as a real JSON boolean (design F3),
    never `0`/`1`."""
    cell = make_cell(app_a)
    try:
        developer, runtime = sessions_for(cell, app_a.app_id)
        fields, field_types = _typed_fields({
            "s": "string", "i": "integer", "n": "number", "b": "boolean",
            "o": "object", "arr": "array", "j": "json",
        })
        developer.create_entity("typed_things", fields=fields, field_types=field_types)
        values = {
            "s": "hello", "i": 42, "n": 3.5, "b": True,
            "o": {"a": 1, "b": [1, 2]}, "arr": [1, "two", {"three": 3}],
            "j": "a plain string written to a json field",
        }
        runtime.insert("typed_things", values)
        rows = runtime.read("typed_things")
        assert len(rows) == 1
        row = rows[0]
        for key, expected in values.items():
            assert row[key] == expected, f"{key}: expected {expected!r}, got {row[key]!r}"
        assert row["b"] is True  # not 1 -- a real JSON boolean, not a truthy int
    finally:
        close_cell(cell)


def test_declared_type_registry_rejects_mismatched_values_for_six_words(app_a) -> None:
    """Design's own non-vacuity requirement (work order §0.1 item 1, WP-3
    completion condition 12): the negative side is exercised for `json`-
    excluded 6 words -- each gets one mismatched value that must be
    rejected `VALIDATION_FAILED` (`errors.ValidationError`) by the cell-
    layer choke point, before any statement reaches PostgreSQL (no row is
    ever inserted for the field under test)."""
    cell = make_cell(app_a)
    try:
        developer, runtime = sessions_for(cell, app_a.app_id)
        fields, field_types = _typed_fields({
            "s": "string", "i": "integer", "n": "number", "b": "boolean",
            "o": "object", "arr": "array",
        })
        developer.create_entity("typed_negatives", fields=fields, field_types=field_types)
        bad_values = {"s": 123, "i": "abc", "n": "abc", "b": 7, "o": [1, 2], "arr": {"a": 1}}
        for field, bad_value in bad_values.items():
            with pytest.raises(ValidationError):
                runtime.insert("typed_negatives", {field: bad_value})
        # None of the 6 rejected writes actually landed.
        assert runtime.read("typed_negatives") == []
    finally:
        close_cell(cell)


def test_declared_boolean_rejects_int_zero_and_one_too(app_a) -> None:
    """0/1 are historically what this backend physically stores a
    declared-boolean field as (design §1.5 finding 1b-2) -- this pins
    that the choke point rejects them as VALUES too, not merely a
    non-0/1 int like `7`: a silent accept-and-coerce here would make the
    boolean check meaningless in the one case that matters most (the
    exact physical representation this backend used to leak)."""
    cell = make_cell(app_a)
    try:
        developer, runtime = sessions_for(cell, app_a.app_id)
        fields, field_types = _typed_fields({"flag": "boolean"})
        developer.create_entity("bool_strict", fields=fields, field_types=field_types)
        for bad in (0, 1, 7):
            with pytest.raises(ValidationError):
                runtime.insert("bool_strict", {"flag": bad})
        assert runtime.read("bool_strict") == []
        runtime.insert("bool_strict", {"flag": False})
        assert runtime.read("bool_strict")[0]["flag"] is False
    finally:
        close_cell(cell)


def test_catalog_reports_four_keys_and_undeclared_fields_default_to_json(app_a) -> None:
    """`ApplicationRuntime.catalog()` (`cell.py`, `application_catalog:
    enabled` this same commit): the returned `EntityDescriptor` carries
    exactly `entity`/`fields`/`field_types`/`field_constraints` (never
    `mutation_class`/`address_fields`/`address_reuse`/`unique_keys` --
    design §1.5 finding 4, `row_addressability: unavailable`), `fields`
    and `field_types`' key set agree exactly, and a field named in
    `fields` but not in the request's own `field_types` reports `json`
    (decision (ii)).

    Phase 9 WP-3a (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)):
    `field_constraints` joined this same commit as `constraint_
    declarations` flipping to `enabled` -- four keys now, not three."""
    cell = make_cell(app_a)
    try:
        developer, runtime = sessions_for(cell, app_a.app_id)
        # `untyped` is deliberately omitted from `field_types` -- decision
        # (ii)'s own default applies (the SAME derivation `http.py`'s own
        # `create_entity` handler performs at the wire boundary: a name
        # with no entry in the request's own `field_types` gets physical
        # `json` and, through it, contract `json` too).
        developer.create_entity(
            "catalog_probe", fields={"typed": "integer", "untyped": "json"}, field_types={"typed": "integer"})
        entries = runtime.catalog()
        entry = next(e for e in entries if e["entity"] == "catalog_probe")
        assert set(entry.keys()) == {"entity", "fields", "field_types", "field_constraints"}
        assert set(entry["fields"]) == {"typed", "untyped"}
        assert set(entry["field_types"]) == set(entry["fields"])
        assert set(entry["field_constraints"]) == set(entry["fields"])
        assert entry["field_types"]["typed"] == "integer"
        assert entry["field_types"]["untyped"] == "json"
        # Every value in the enum is one of the contract's 7 words.
        for value in entry["field_types"].values():
            assert value in ("string", "integer", "number", "boolean", "object", "array", "json")
    finally:
        close_cell(cell)


def test_migration_0006_backfills_declared_types_for_a_pre_1_6_0_style_database(
    platform, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Simulates an application provisioned before this WP: drops the
    registry table the (now-updated) `0003` already created for it and
    adds a handful of raw columns via direct SQL, with no registry rows
    at all -- then runs the upgrade script `0006` and checks the
    backfilled rows match design §1.5 finding 2a's own table exactly,
    including the documented `object`/`array` -> `string` collapse
    limitation (both physically TEXT, indistinguishable from `information_
    schema` alone -- `0006`'s own header comment)."""
    app = provision_app(platform, "upgrade_probe")
    try:
        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._mdb_field_types")
                cur.execute(
                    "CREATE TABLE public.legacy_thing "
                    "(int_col BIGINT, num_col DOUBLE PRECISION, bool_col INTEGER, text_col TEXT)"
                )
        finally:
            conn.close()

        rewritten_dir = tmp_path_factory.mktemp("mitatedb_0006_" + platform.prefix)
        text = (MIGRATIONS_DIR / "0006_declared_field_types_upgrade.sql").read_text().replace("mitatedb", platform.prefix)
        rewritten_0006 = rewritten_dir / "0006_declared_field_types_upgrade.sql"
        rewritten_0006.write_text(text)

        _run_psql(platform.provision_dsn, rewritten_0006, {"app_id": "upgrade_probe"})

        conn = psycopg.connect(app.developer_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT field, declared_type FROM public._mdb_field_types "
                    "WHERE entity = 'legacy_thing' ORDER BY field"
                )
                rows = dict(cur.fetchall())
            conn.commit()
        finally:
            conn.close()
        assert rows == {
            "int_col": "integer", "num_col": "number", "bool_col": "boolean", "text_col": "string",
        }

        # Re-running it is a safe no-op (ON CONFLICT DO NOTHING) -- an
        # operator-corrected row (design's own documented object/array
        # remediation) must never be clobbered by a second run.
        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public._mdb_field_types SET declared_type = 'object' "
                    "WHERE entity = 'legacy_thing' AND field = 'text_col'"
                )
        finally:
            conn.close()
        _run_psql(platform.provision_dsn, rewritten_0006, {"app_id": "upgrade_probe"})
        conn = psycopg.connect(app.developer_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT declared_type FROM public._mdb_field_types "
                    "WHERE entity = 'legacy_thing' AND field = 'text_col'"
                )
                (declared_type,) = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
        assert declared_type == "object"

        # And the backend can actually read it back through the normal API.
        cell = make_cell(app)
        try:
            declared = cell._backend.field_types("legacy_thing")
            assert declared == {
                "int_col": "integer", "num_col": "number", "bool_col": "boolean", "text_col": "object",
            }
        finally:
            close_cell(cell)
    finally:
        deprovision_app(platform, "upgrade_probe")


def test_missing_field_types_registry_is_storage_configuration_error_not_validation_failed(platform) -> None:
    """WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 6,
    review F9): a `_mdb_field_types`-less application DB (migration 0006
    genuinely never applied -- not the `test_migration_0006_...` test
    above, which DOES apply it) is an OPERATOR/DEPLOYMENT defect, never a
    client mistake. Before this fix, `backend_postgres.py`'s `field_
    domains`/`field_types`/`all_field_types` each caught the resulting
    `psycopg.errors.UndefinedTable` only via their own generic `except
    psycopg.Error`, surfacing `ValidationError` (contract `VALIDATION_
    FAILED`, a CLIENT-fault code) for every read/write on the affected
    entity -- fail-closed, but the wrong fault attribution (an operator
    reading `VALIDATION_FAILED` back would reasonably suspect their OWN
    request, not a missing migration). `StorageConfigurationError` is
    this peer's own existing class for exactly this shape of defect
    (`credential_store_postgres.py`'s identical `InsufficientPrivilege`
    precedent), mapping to `SERVICE_UNAVAILABLE` at the HTTP boundary."""
    app = provision_app(platform, "no_registry_probe")
    try:
        conn = psycopg.connect(app.developer_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public._mdb_field_types")
                cur.execute("CREATE TABLE public.unregistered_thing (int_col BIGINT, text_col TEXT)")
        finally:
            conn.close()

        cell = make_cell(app)
        try:
            with pytest.raises(StorageConfigurationError):
                cell._backend.field_types("unregistered_thing")
            with pytest.raises(StorageConfigurationError):
                cell._backend.field_domains("unregistered_thing")
            with pytest.raises(StorageConfigurationError):
                cell._backend.all_field_types()
        finally:
            close_cell(cell)
    finally:
        deprovision_app(platform, "no_registry_probe")


# ---------------------------------------------------------------------------
# 追補 4 O-4 (M-6 の Postgres 脚, 版フリップ監査 §7/§16, `{scratchpad}/
# rulings-r3-r7-flip.md`): the SAME "a stored idempotency record with no
# `request_id` is treated as absent" guarantee `tests/test_denial_details_
# and_request_id.py::test_idempotency_record_without_request_id_on_
# mutation_is_treated_as_absent`/`..._on_schema_op_...` pin on the
# in-memory `SQLiteBackend`, now also pinned directly against a real
# PostgreSQL `PostgresBackend` -- the audit found the mechanism (`cell.py`'s
# own `has_request_id` gate, backend-independent) implemented but
# unproven on this backend. Manipulates the real `public._mdb_idempotency`
# row directly (mirrors this file's own `test_missing_field_types_
# registry_...` precedent immediately above for reaching into the real
# database) rather than through any backend-private Python attribute
# (`PostgresBackend` has no in-process dict like `SQLiteBackend._
# idempotency` to poke).
# ---------------------------------------------------------------------------


def test_postgres_idempotency_record_without_request_id_on_mutation_is_treated_as_absent(app_a) -> None:
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("o4idem_probe", {"title": "text"})
        key = "o4-pg-idem-mutation-key"
        first = runtime.transact(
            [{"type": "insert", "collection": "o4idem_probe", "values": {"title": "a"}, "idempotency_key": key}])
        assert first[-1]["request_id"]

        with cell._backend._runtime.cursor() as cur:
            cur.execute("SELECT response_json FROM public._mdb_idempotency WHERE key = %s", [key])
            (response_json,) = cur.fetchone()
            stored = json.loads(response_json)
            del stored[-1]["request_id"]
            cur.execute(
                "UPDATE public._mdb_idempotency SET response_json = %s WHERE key = %s",
                [json.dumps(stored), key],
            )
        cell._backend._runtime.commit()

        rows_before = runtime.read("o4idem_probe")
        second = runtime.transact(
            [{"type": "insert", "collection": "o4idem_probe", "values": {"title": "a"}, "idempotency_key": key}])
        rows_after = runtime.read("o4idem_probe")

        # A genuine re-execution happened (a second row was inserted),
        # never a replay of the stripped record.
        assert len(rows_after) == len(rows_before) + 1
        assert second[-1]["request_id"]
        assert second[-1]["request_id"] != first[-1]["request_id"]

        # `ON CONFLICT (key) DO UPDATE` (`_write_idempotency_row`) means
        # the record itself was overwritten by the fresh execution's own
        # write, and now carries `request_id` again.
        with cell._backend._runtime.cursor() as cur:
            cur.execute("SELECT response_json FROM public._mdb_idempotency WHERE key = %s", [key])
            (updated_json,) = cur.fetchone()
        cell._backend._runtime.commit()
        updated = json.loads(updated_json)
        assert updated[-1]["request_id"] == second[-1]["request_id"]
    finally:
        close_cell(cell)


def test_postgres_idempotency_record_without_request_id_on_schema_op_is_treated_as_absent(app_a) -> None:
    """Mirrors the mutation-level test above for the SCHEMA side -- a
    resend re-executes `add_field` as a genuinely new attempt, observed
    here as a `ConflictError` from the second, real attempt to add a
    field name that already exists (the tell-tale sign this was NOT
    answered from the stripped record, which would have returned
    successfully with no error at all)."""
    cell = make_cell(app_a)
    developer, runtime = sessions_for(cell, app_a.app_id)
    try:
        developer.create_collection("o4idem_probe_2", {"title": "text"})
        key = "o4-pg-idem-schema-key"
        first = developer.add_field("o4idem_probe_2", "o4_field", "text", idempotency_key=key)
        assert first["request_id"]

        with cell._backend._developer.cursor() as cur:
            cur.execute("SELECT response_json FROM public._mdb_idempotency WHERE key = %s", [key])
            (response_json,) = cur.fetchone()
            stored = json.loads(response_json)
            del stored["request_id"]
            cur.execute(
                "UPDATE public._mdb_idempotency SET response_json = %s WHERE key = %s",
                [json.dumps(stored), key],
            )
        cell._backend._developer.commit()

        with pytest.raises(ConflictError):
            developer.add_field("o4idem_probe_2", "o4_field", "text", idempotency_key=key)
    finally:
        close_cell(cell)
