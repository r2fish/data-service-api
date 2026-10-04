"""R-82: `PostgresBackend` keeps the collection snapshots it read in this process and reads them again only when the application's schema revision has moved.

Each test below is one completion condition of docs/work-orders/WORK_ORDER_R82_SCHEMA_CACHE_V1.md section 4, driven on a real PostgreSQL database (two independent backends on one database where the condition is about another process changing the definition). A test asserts that what it counts or compares has at least one observation, so a run that observes nothing fails.

1  a warm cache makes a read and a write read the token only (the statement naming `pg_database`), never the loader (`_load_collection_snapshot`).
2  a definition another backend changed is used by the next request of this one: a field added to the entity is usable, a narrowed `enum` is enforced.
3  a dry run and a schema-kind request scope leave nothing in the cache.
4  a request that took its entity lock after an earlier catalog read validates against what a schema operation committed meanwhile.
5  the cache belongs to one backend, and its token is (the database's own `pg_database.oid`, `_mdb_schema_revision.revision`).
6  `_RevisionKeyedCache.put` under another token discards every value stored under the previous one.
7  what a catalog read returns is a copy: writing to it does not change the next read.
9  every application upgrade script raises the schema revision or is listed with the reason it need not.
"""
from __future__ import annotations

import re
from typing import Any

import psycopg
import pytest

import mitatedb_api.backend_postgres as bp_module
from mitatedb_api import FoundationConfig, platform_upgrades
from mitatedb_api.backend_postgres import PostgresBackend, _RevisionKeyedCache
from mitatedb_api.cell import ApplicationCell
from mitatedb_api.errors import ValidationError

from .test_postgres import MIGRATIONS_DIR, app_a, app_b, platform, sessions_for  # noqa: F401 (fixtures)


def _make(app: Any) -> tuple[PostgresBackend, Any, Any]:
    backend = PostgresBackend(runtime_dsn=app.runtime_dsn, developer_dsn=app.developer_dsn)
    cell = ApplicationCell(app.app_id, FoundationConfig(), backend=backend)
    developer, runtime = sessions_for(cell, app.app_id)
    return backend, developer, runtime


def _create_notes(developer: Any, *, enum: list[str] | None = None) -> None:
    constraints = {"title": {"enum": enum}} if enum is not None else None
    developer.create_entity("notes", fields={"title": "text"}, field_types={"title": "string"}, field_constraints=constraints)


class _Spies:
    """Counts the token statement (the one naming `pg_database`) and the loader."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.token_reads = 0
        self.loads = 0
        real_execute = bp_module._execute
        real_load = PostgresBackend._load_collection_snapshot
        spies = self

        def execute(cursor: Any, statement: Any, params: Any = ()) -> Any:
            if "pg_database" in statement.as_string(cursor):
                spies.token_reads += 1
            return real_execute(cursor, statement, params)

        def load(self: PostgresBackend, *args: Any, **kwargs: Any) -> Any:
            spies.loads += 1
            return real_load(self, *args, **kwargs)

        monkeypatch.setattr(bp_module, "_execute", execute)
        monkeypatch.setattr(PostgresBackend, "_load_collection_snapshot", load)


def test_a_warm_cache_serves_a_read_and_a_write_from_the_token_alone(app_a: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 1. After one read and one write have loaded the snapshot, the same two requests read the token once each and the loader not at all."""
    backend, developer, runtime = _make(app_a)
    try:
        _create_notes(developer)
        runtime.insert("notes", {"title": "warm"})
        runtime.read("notes")

        spies = _Spies(monkeypatch)
        rows = runtime.read("notes")
        runtime.insert("notes", {"title": "hot"})
        assert len(rows) == 1, "the read returned the warm row"
        assert spies.token_reads == 2, f"one token read per request, two requests: {spies.token_reads}"
        assert spies.loads == 0, f"a warm cache must not run the loader: {spies.loads}"
    finally:
        backend.close()


def test_a_definition_another_backend_changed_is_used_by_the_next_request(app_a: Any) -> None:
    """Completion condition 2, both directions. Backend B has served requests (its cache is warm); backend A then adds a field and narrows an `enum`. B's next requests use the new definition: the added field is accepted, the value the narrowed `enum` no longer holds is refused."""
    backend_a, developer_a, _runtime_a = _make(app_a)
    backend_b, _developer_b, runtime_b = _make(app_a)
    try:
        _create_notes(developer_a, enum=["v", "w"])
        runtime_b.insert("notes", {"title": "w"})
        runtime_b.read("notes")
        with pytest.raises(ValidationError):
            runtime_b.insert("notes", {"title": "w", "extra": "x"})

        developer_a.add_field("notes", "extra", "text", contract_type="string")
        developer_a.alter_field("notes", "title", enum=["w"])

        runtime_b.insert("notes", {"title": "w", "extra": "x"})
        with pytest.raises(ValidationError) as refused:
            runtime_b.insert("notes", {"title": "v"})
        assert refused.value.details.get("violated_declaration") == "enum", refused.value.details
        assert sorted(row["extra"] or "" for row in runtime_b.read("notes")) == ["", "x"]
    finally:
        backend_a.close()
        backend_b.close()


def test_a_dry_run_and_a_schema_kind_scope_leave_the_cache_as_it_was(app_a: Any) -> None:
    """Completion condition 3. A dry run `add_field` adds nothing, and a request naming its field is refused. A schema-kind request scope that reads the catalog while its own uncommitted DDL is visible (a tentative column, rolled back) must not keep that read: the next data-kind request does not see the column."""
    backend, developer, runtime = _make(app_a)
    try:
        _create_notes(developer)
        runtime.insert("notes", {"title": "t"})
        developer.add_field("notes", "extra", "text", contract_type="string", dry_run=True)
        with pytest.raises(ValidationError):
            runtime.insert("notes", {"title": "t", "extra": "x"})

        for warm in (False, True):  # an empty cache (the schema-kind read must not fill it) and a warm one (it must not be answered from it)
            backend._catalog_cache = _RevisionKeyedCache()
            if warm:
                with backend.request_scope("query") as scope:
                    backend.field_domains("notes", scope=scope)
            with backend.request_scope("schema") as scope:
                scope.lock_schema()
                scope.lock_entities(["notes"], shared=False)
                with scope.main.cursor() as cur:
                    cur.execute('ALTER TABLE public."notes" ADD COLUMN "ghost" text')
                tentative = backend.field_domains("notes", scope=scope)
                scope.main.rollback()
            assert "ghost" in tentative, f"the schema-kind read saw its own tentative column (warm cache: {warm})"

            with backend.request_scope("query") as scope:
                kept = backend.field_domains("notes", scope=scope)
            assert "ghost" not in kept, f"a tentative column of a rolled-back schema scope reached the cache (warm cache: {warm}): {sorted(kept)}"
            assert "title" in kept
    finally:
        backend.close()


def test_a_request_that_took_its_entity_lock_after_a_catalog_read_validates_against_what_was_committed_meanwhile(app_a: Any) -> None:
    """Completion condition 4. Backend B reads the collection's constraints in a data scope (its token is remembered), another backend narrows the `enum` and commits, and B then takes the shared entity lock: the lock discards the remembered token, so B's next read finds the revision moved and reads the committed definition. Without the discard B would read its own warm entry under the old token."""
    backend_a, developer_a, _runtime_a = _make(app_a)
    backend_b = PostgresBackend(runtime_dsn=app_a.runtime_dsn, developer_dsn=app_a.developer_dsn)
    try:
        _create_notes(developer_a, enum=["v", "w"])
        with backend_b.request_scope("dml") as scope:
            backend_b.lock_entities(["notes"], shared=True, scope=scope)
            assert backend_b.field_constraints("notes", scope=scope)["title"]["enum"] == ["v", "w"]

        with backend_b.request_scope("dml") as scope:
            before = backend_b.field_constraints("notes", scope=scope)["title"]["enum"]
            developer_a.alter_field("notes", "title", enum=["w"])
            backend_b.lock_entities(["notes"], shared=True, scope=scope)
            after = backend_b.field_constraints("notes", scope=scope)["title"]["enum"]
        assert before == ["v", "w"], "the read before the lock was served from the warm entry"
        assert after == ["w"], f"the read after the lock must see the committed enum: {after}"
    finally:
        backend_a.close()
        backend_b.close()


def test_each_backend_keeps_its_own_cache_and_the_token_is_the_databases_oid_and_revision(platform: Any, app_a: Any, app_b: Any) -> None:  # noqa: F811
    """Completion condition 5. Two applications hold an entity of the same name with different fields; each backend validates against its own. The token a backend reads equals an independent read of `pg_database.oid` (over the admin connection) and of the revision table (over the developer connection), and the two applications' tokens differ."""
    backend_a, developer_a, runtime_a = _make(app_a)
    backend_b, developer_b, runtime_b = _make(app_b)
    try:
        developer_a.create_entity("notes", fields={"only_a": "text"}, field_types={"only_a": "string"})
        developer_b.create_entity("notes", fields={"only_b": "text"}, field_types={"only_b": "string"})
        for _ in range(2):  # the second round is answered from each backend's own cache
            runtime_a.insert("notes", {"only_a": "a"})
            runtime_b.insert("notes", {"only_b": "b"})
            with pytest.raises(ValidationError):
                runtime_a.insert("notes", {"only_b": "b"})
            with pytest.raises(ValidationError):
                runtime_b.insert("notes", {"only_a": "a"})

        tokens = []
        for app, backend in ((app_a, backend_a), (app_b, backend_b)):
            with backend.request_scope("query") as scope:
                token = backend._catalog_token(scope)
            with psycopg.connect(platform.admin_dsn, autocommit=True) as admin:
                (oid,) = admin.execute("SELECT oid FROM pg_database WHERE datname = %s", [app.database]).fetchone()
            with psycopg.connect(app.developer_dsn, autocommit=True) as developer:
                (revision,) = developer.execute("SELECT revision FROM _mdb_schema_revision").fetchone()
            assert token == (oid, revision), (token, oid, revision)
            assert revision >= 1, "the entity creation raised the revision, so the revision half of the token is observed"
            tokens.append(token)
        assert tokens[0][0] != tokens[1][0], "two databases, two oids"
    finally:
        backend_a.close()
        backend_b.close()


def test_a_put_under_another_token_discards_what_the_previous_token_stored() -> None:
    """Completion condition 6. A `put` under a token other than the one the contents were stored under drops every value stored under the previous token: a value put under the old token is not returned for the new one, whether the new token has a smaller revision of the same database (a restore) or another database's oid."""
    cache = _RevisionKeyedCache()
    cache.put((7, 5), "old key", "stored under the old token")
    cache.put((7, 3), "new key", "stored under a smaller revision")
    assert cache.get((7, 3), "new key") == "stored under a smaller revision"
    assert cache.get((7, 3), "old key") is None, "a value stored under revision 5 must not answer revision 3"
    assert cache.get((7, 5), "old key") is None and cache.get((7, 5), "new key") is None, "the replaced token matches nothing"
    cache.put((8, 9), "other key", "stored under another database's token")
    assert cache.get((8, 9), "other key") == "stored under another database's token"
    assert cache.get((8, 9), "new key") is None, "a value stored under the previous token must not answer the next one"
    assert cache.get((7, 3), "new key") is None


def test_writing_to_what_a_catalog_read_returned_does_not_change_the_next_read(app_a: Any) -> None:
    """Completion condition 7. The four `field_*` reads return copies, `enum` list included: a caller that rewrites what it got (on the read that fills the cache and on one answered from it) leaves the next read as it was."""
    backend, developer, _runtime = _make(app_a)
    try:
        _create_notes(developer, enum=["v", "w"])
        observed = 0
        for _round in ("fills the cache", "answered from the cache"):
            with backend.request_scope("query") as scope:
                constraints = backend.field_constraints("notes", scope=scope)
                types, pair_constraints = backend.field_types_and_constraints("notes", scope=scope)
                domains = backend.field_domains("notes", scope=scope)
                declared = backend.field_types("notes", scope=scope)
                for returned in (constraints, pair_constraints):
                    returned["title"]["enum"].append("intruder")
                    returned["title"]["nullable"] = None
                    returned["intruder"] = {}
                for returned in (types, domains, declared):
                    returned["intruder"] = "x"
                    returned["title"] = "x"
                observed += 1
            with backend.request_scope("query") as scope:
                assert backend.field_constraints("notes", scope=scope) == {"title": {"nullable": True, "enum": ["v", "w"]}}
                assert backend.field_types("notes", scope=scope) == {"title": "string"}
                assert "intruder" not in backend.field_domains("notes", scope=scope)
        assert observed == 2
    finally:
        backend.close()


# A number is listed here only with the reason the script it names cannot change what the catalog read returns without the schema revision moving (docs/work-orders/WORK_ORDER_R82_SCHEMA_CACHE_V1.md D-8). A new application upgrade script either raises `_mdb_schema_revision.revision` or is added with its reason.
_R82_PRECEDING = "predates R-82: a process that requires this number answers requests only after its startup ledger check found it applied, and serves no cached read of an application before that"
_UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION: dict[int, str] = {
    6: _R82_PRECEDING,
    8: _R82_PRECEDING,
    9: _R82_PRECEDING,
    10: _R82_PRECEDING,
    15: _R82_PRECEDING,
}


def test_every_application_upgrade_script_raises_the_schema_revision_or_is_listed_with_its_reason() -> None:
    """Completion condition 9. Walks the scripts `platform_upgrades.discover_upgrade_scripts` lists for this peer; each either contains the statement that raises the revision or is in the table above, and the table lists nothing the walk did not find."""
    scripts = platform_upgrades.discover_upgrade_scripts(MIGRATIONS_DIR)
    assert scripts, "the walk found no application upgrade script"
    raises_revision = re.compile(r'\bUPDATE\s+(?:public\.)?"?_mdb_schema_revision"?\s+SET\s+revision\s*=\s*revision\s*\+\s*1\b', re.IGNORECASE)
    issued: list[str] = []
    real_execute = bp_module._execute
    bp_module._execute = lambda cursor, statement, params=(): issued.append(statement.as_string(None))
    try:
        PostgresBackend.__new__(PostgresBackend)._bump_schema_revision(None)
    finally:
        bp_module._execute = real_execute
    assert issued and raises_revision.search(issued[0]), f"the pattern does not match the statement `_bump_schema_revision` issues: {issued}"
    unaccounted = []
    for number, path in sorted(scripts.items()):
        text = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("--"))
        if not raises_revision.search(text) and number not in _UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION:
            unaccounted.append((number, path.name))
    assert not unaccounted, f"upgrade script(s) neither raise the schema revision nor are listed with a reason: {unaccounted}"
    assert set(_UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION) <= set(scripts), "the table lists a number the walk did not find"
