"""R-82: `PostgresCell` keeps the catalog it read in this process and reads it again only when the application's schema revision has moved.

Each test below is one completion condition of docs/work-orders/WORK_ORDER_R82_SCHEMA_CACHE_V1.md section 4, driven on a real PostgreSQL database (two independent `PostgresCell` instances on one database where the condition is about another process changing the definition). A test asserts that what it counts or compares has at least one observation, so a run that observes nothing fails.

1  a warm cache makes `query`, `transact` and `catalog` read the token only (`_read_catalog_token`), never the live catalog (`_load_catalog`).
2  a definition another cell changed is used by the next request of this cell: a field added to the entity is usable, a narrowed `enum` is enforced.
3  a dry run and a refused schema operation leave nothing in the cache.
4  a data operation that waited for a schema operation's entity lock validates against what that operation committed.
5  the cache belongs to one cell, and its token is (the database's own `pg_database.oid`, `_r2db_schema_revision.revision`).
6  `_RevisionKeyedCache.put` under another token discards every value stored under the previous one.
7  what the cache hands out cannot be written to.
9  every application upgrade script raises the schema revision or is listed with the reason it need not.
"""
from __future__ import annotations

import dataclasses
import re
import types
from typing import Any

import psycopg
import pytest

from r2db_api import platform_upgrades
from r2db_api import postgres as postgres_module
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell, _RevisionKeyedCache

from test_postgres import MIGRATIONS_DIR, app_a, app_b, make_cell, platform  # noqa: F401 (fixtures)
from test_r102_schema_windows import _Stall, _pair
from test_r120_entity_lock import _raw_column, _run_entity_window

LIMITS = ResourceLimits()


def _create_notes(cell: PostgresCell, *, enum: list[str] | None = None) -> None:
    cell.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["title"], "field_types": {"title": "string"}}, developer=True, limits=LIMITS)
    if enum is not None:
        cell.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": enum}, developer=True, limits=LIMITS)


def _insert(cell: PostgresCell, values: dict[str, Any]) -> Any:
    return cell.transact("notes", [{"operation": "insert", "values": values}], LIMITS)


def _spy(monkeypatch: pytest.MonkeyPatch, name: str) -> dict[str, int]:
    calls = {"n": 0}
    real = getattr(PostgresCell, name)

    def spy(self: PostgresCell, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real(self, *args, **kwargs)

    monkeypatch.setattr(PostgresCell, name, spy)
    return calls


def test_a_warm_cache_serves_query_transact_and_catalog_from_the_token_alone(app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion condition 1. After one request of each kind has read the live catalog, the same three calls read the token once each and the live catalog not at all."""
    cell = make_cell(app_a)
    try:
        _create_notes(cell)
        _insert(cell, {"title": "warm"})
        cell.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS)
        cell.catalog()

        loads = _spy(monkeypatch, "_load_catalog")
        tokens = _spy(monkeypatch, "_read_catalog_token")
        cell.query("notes", select=["id", "title"], where=[], page_size=10, limits=LIMITS)
        _insert(cell, {"title": "hot"})
        entries = cell.catalog()
        assert [entry["entity"] for entry in entries] == ["notes"], "the cached catalog describes the entity"
        assert tokens["n"] == 3, f"one token read per request, three requests: {tokens['n']}"
        assert loads["n"] == 0, f"a warm cache must not read the live catalog: {loads['n']}"
    finally:
        cell.close()


def test_a_definition_another_cell_changed_is_used_by_the_next_request(app_a: types.SimpleNamespace) -> None:
    """Completion condition 2, both directions. Cell B has served requests (its cache is warm); cell A then adds a field and narrows an `enum`. B's next requests use the new definition: the added field is accepted, the value the narrowed `enum` no longer holds is refused."""
    cell_a, cell_b = _pair(app_a)
    try:
        _create_notes(cell_a, enum=["v", "w"])
        _insert(cell_b, {"title": "w"})
        cell_b.query("notes", select=["id"], where=[], page_size=10, limits=LIMITS)
        with pytest.raises(FoundationError) as before:
            _insert(cell_b, {"title": "w", "extra": "x"})
        assert before.value.code == "VALIDATION_FAILED", "the field does not exist yet, through B's warm cache"

        cell_a.apply_schema({"operation": "add_field", "entity": "notes", "field": "extra"}, developer=True, limits=LIMITS)
        cell_a.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["w"]}, developer=True, limits=LIMITS)

        _insert(cell_b, {"title": "w", "extra": "x"})
        with pytest.raises(FoundationError) as refused:
            _insert(cell_b, {"title": "v"})
        assert refused.value.code == "VALIDATION_FAILED" and refused.value.details == {"field": "operations/0/values/title", "violated_declaration": "enum", "declared_type": "string"}
        described = {entry["entity"]: entry for entry in cell_b.catalog()}["notes"]
        assert "extra" in described["fields"] and described["field_constraints"]["title"]["enum"] == ["w"]
        assert _raw_column(app_a, "notes", "extra") == [None, "x"]
    finally:
        cell_a.close()
        cell_b.close()


def test_a_dry_run_and_a_refused_schema_operation_leave_the_cache_as_it_was(app_a: types.SimpleNamespace) -> None:
    """Completion condition 3. The dry run re-reads the catalog inside its own uncommitted transaction to describe the result; that read must not be kept. After it, and after a schema operation refused for want of a confirmation, a request naming the field the dry run only pretended to add is refused, and the catalog does not list it."""
    cell = make_cell(app_a)
    try:
        _create_notes(cell)
        dry = cell.apply_schema({"operation": "add_field", "entity": "notes", "field": "extra"}, developer=True, limits=LIMITS, dry_run=True)
        assert dry.committed is False and dry.descriptor is not None and "extra" in dry.descriptor["fields"], "the dry run described the field it did not add"
        with pytest.raises(FoundationError) as refused_op:
            cell.apply_schema({"operation": "drop_entity", "entity": "notes"}, developer=True, limits=LIMITS)
        assert refused_op.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"

        with pytest.raises(FoundationError) as refused:
            _insert(cell, {"title": "t", "extra": "x"})
        assert refused.value.code == "VALIDATION_FAILED", f"a field the dry run did not add was accepted: {refused.value!r}"
        (entry,) = cell.catalog()
        assert entry["fields"] == ["id", "title"], entry["fields"]
    finally:
        cell.close()


def test_a_data_operation_that_waited_for_a_schema_operation_validates_against_what_it_committed(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """Completion condition 4. A: `alter_field(notes.title, enum=[w])` on one cell, stopped just before its revision is raised (so it holds the entity lock EXCLUSIVE with its writes uncommitted). B, on the other cell and with a warm cache: an insert of `title = v`. B waits for the entity lock; once A has committed, B reads the token, finds it moved, and refuses `v` against the committed `enum`. A token read before the lock would have found B's own warm entry current and accepted `v`."""
    cell_a, cell_b = _pair(app_a)
    try:
        _create_notes(cell_a, enum=["v", "w"])
        _insert(cell_b, {"title": "w"})

        stall = _Stall()
        stall.install(monkeypatch, PostgresCell, "_bump_revision")
        window = _run_entity_window(
            stall,
            lambda: cell_a.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["w"]}, developer=True, limits=LIMITS),
            lambda: _insert(cell_b, {"title": "v"}),
            admin_dsn=platform.admin_dsn, database=app_a.database)

        assert window.advisory_waiters_seen >= 1 and not window.b_done_while_a_stopped, (
            f"B was not seen waiting on the entity lock while A was stopped (B completed while A stopped: {window.b_done_while_a_stopped}, advisory waiters seen: {window.advisory_waiters_seen})")
        assert "A" in window.results, f"A held the entity first and must succeed: {window.errors.get('A')!r}"
        refusal = window.errors.get("B")
        assert isinstance(refusal, FoundationError) and refusal.details == {"field": "operations/0/values/title", "violated_declaration": "enum", "declared_type": "string"}, f"B must be refused against the committed enum, got {refusal!r} / {window.results.get('B')!r}"
        assert _raw_column(app_a, "notes", "title") == ["w"]
    finally:
        cell_a.close()
        cell_b.close()


def test_each_cell_keeps_its_own_cache_and_the_token_is_the_databases_oid_and_revision(
    platform: types.SimpleNamespace, app_a: types.SimpleNamespace, app_b: types.SimpleNamespace,  # noqa: F811
) -> None:
    """Completion condition 5. Two applications hold an entity of the same name with different fields; each cell validates against its own. The token a cell reads equals an independent read of `pg_database.oid` (over the admin connection) and of the revision table (over the developer connection), and the two applications' tokens differ."""
    cell_a = make_cell(app_a)
    cell_b = make_cell(app_b)
    try:
        cell_a.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["only_a"], "field_types": {"only_a": "string"}}, developer=True, limits=LIMITS)
        cell_b.apply_schema({"operation": "create_entity", "entity": "notes", "fields": ["only_b"], "field_types": {"only_b": "string"}}, developer=True, limits=LIMITS)
        for _ in range(2):  # the second round is answered from each cell's own cache
            cell_a.transact("notes", [{"operation": "insert", "values": {"only_a": "a"}}], LIMITS)
            cell_b.transact("notes", [{"operation": "insert", "values": {"only_b": "b"}}], LIMITS)
            with pytest.raises(FoundationError):
                cell_a.transact("notes", [{"operation": "insert", "values": {"only_b": "b"}}], LIMITS)
            with pytest.raises(FoundationError):
                cell_b.transact("notes", [{"operation": "insert", "values": {"only_a": "a"}}], LIMITS)

        tokens = []
        for app, cell in ((app_a, cell_a), (app_b, cell_b)):
            with cell._runtime.connection() as conn:
                token = cell._read_catalog_token(conn)
                conn.rollback()
            with psycopg.connect(platform.admin_dsn, autocommit=True) as admin:
                (oid,) = admin.execute("SELECT oid FROM pg_database WHERE datname = %s", [app.database]).fetchone()
            with psycopg.connect(app.developer_dsn, autocommit=True) as developer:
                (revision,) = developer.execute("SELECT revision FROM _r2db_schema_revision").fetchone()
            assert token == (oid, revision), (token, oid, revision)
            assert revision >= 1, "the entity creation raised the revision, so the revision half of the token is observed"
            tokens.append(token)
        assert tokens[0][0] != tokens[1][0], "two databases, two oids"
    finally:
        cell_a.close()
        cell_b.close()


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


def test_what_the_cache_hands_out_cannot_be_written_to(app_a: types.SimpleNamespace) -> None:
    """Completion condition 7. The catalog `_catalog` returns, on a read that fills the cache and on one answered from it, is read-only at every level a caller could reach: the entity map, the three maps of an entity and each index entry, and an entity's own attributes cannot be reassigned (`_TableInfo` is frozen)."""
    cell = make_cell(app_a)
    try:
        _create_notes(cell)
        cell.apply_schema({"operation": "create_index", "entity": "notes", "index": "by_title", "fields": ["title"]}, developer=True, limits=LIMITS)
        cell.apply_schema({"operation": "alter_field", "entity": "notes", "field": "title", "enum": ["w"]}, developer=True, limits=LIMITS)
        observed = 0
        for _round in ("fills the cache", "answered from the cache"):
            with cell._runtime.connection() as conn:
                catalog = cell._catalog(conn)
                conn.rollback()
            info = catalog["notes"]
            assert info.indexes["by_title"] and info.constraints["title"].enum == ("w",)
            for target, key, value in (
                (catalog, "intruder", info),
                (info.columns, "intruder", "string"),
                (info.indexes, "intruder", {}),
                (info.indexes["by_title"], "unique", False),
                (info.constraints, "intruder", None),
            ):
                with pytest.raises(TypeError):
                    target[key] = value
                observed += 1
        assert observed == 10
        with pytest.raises(dataclasses.FrozenInstanceError):
            info.columns = {}
    finally:
        cell.close()


# A number is listed here only with the reason the script it names cannot change what the catalog read returns without the schema revision moving (docs/work-orders/WORK_ORDER_R82_SCHEMA_CACHE_V1.md D-8). A new application upgrade script either raises `_r2db_schema_revision.revision` or is added with its reason.
_UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION: dict[int, str] = {
    9: "creates the platform-upgrade ledger table, a bookkeeping table the catalog read excludes",
    10: "creates the field-constraints registry table empty; an absent registry and an empty one read the same",
    11: "creates the idempotency-record table, a bookkeeping table the catalog read excludes",
}


def test_every_application_upgrade_script_raises_the_schema_revision_or_is_listed_with_its_reason() -> None:
    """Completion condition 9. Walks the scripts `platform_upgrades.discover_upgrade_scripts` lists for this peer; each either contains the statement that raises the revision or is in the table above, and the table lists nothing the walk did not find."""
    scripts = platform_upgrades.discover_upgrade_scripts(MIGRATIONS_DIR)
    assert scripts, "the walk found no application upgrade script"
    raises_revision = re.compile(r'\bUPDATE\s+(?:public\.)?"?_r2db_schema_revision"?\s+SET\s+revision\s*=\s*revision\s*\+\s*1\b', re.IGNORECASE)
    issued: list[str] = []

    class _Stop(Exception):
        pass

    class _Cursor:
        def __enter__(self) -> "_Cursor":
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor()

    def record(cursor: Any, statement: Any, params: Any = ()) -> None:
        issued.append(statement.as_string(None))
        raise _Stop

    real_run = postgres_module._run
    postgres_module._run = record
    try:
        with pytest.raises(_Stop):
            PostgresCell.__new__(PostgresCell)._bump_revision(_Connection())
    finally:
        postgres_module._run = real_run
    assert issued and raises_revision.search(issued[0]), f"the pattern does not match the statement `_bump_revision` issues: {issued}"
    unaccounted = []
    for number, path in sorted(scripts.items()):
        text = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("--"))
        if not raises_revision.search(text) and number not in _UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION:
            unaccounted.append((number, path.name))
    assert not unaccounted, f"upgrade script(s) neither raise the schema revision nor are listed with a reason: {unaccounted}"
    assert set(_UPGRADES_THAT_DO_NOT_RAISE_THE_REVISION) <= set(scripts), "the table lists a number the walk did not find"
