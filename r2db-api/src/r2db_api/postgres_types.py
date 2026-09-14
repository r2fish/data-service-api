"""PostgreSQL DDL type objects for the r2db storage backend.

This is a pure leaf: it only maps an already validated contract field-type
word to a psycopg SQL composition object.  It neither opens a connection nor
executes SQL; catalog validation and every transaction boundary remain in
``postgres.PostgresCell``.
"""
from __future__ import annotations

from psycopg import sql


# R-2/R-7: `add_field`'s `field_type` maps to a real PostgreSQL column
# type; `create_entity`'s own fields (which never carry a `field_type` --
# rejected at the shared `bind_schema_operation` boundary) and an
# `add_field` with no `field_type` both keep the pre-CCR-13 default, JSONB.
# `object`/`array` map to the two DOMAINs `migrations/0003_provision_
# application.sql` provisions in every application database (WP-3 review,
# "object/array の DOMAIN 型統一") -- not bare `JSONB`, which cannot report
# which of the two a column was declared as. `sql.Identifier` (not
# `sql.SQL`) is used for these two: they are catalog objects (domain
# names), not built-in type keywords.
_JSONB_SQL = sql.SQL("JSONB")
_FIELD_TYPE_SQL: dict[str, sql.SQL | sql.Identifier] = {
    "string": sql.SQL("TEXT"),
    "integer": sql.SQL("BIGINT"),
    "number": sql.SQL("DOUBLE PRECISION"),
    "boolean": sql.SQL("BOOLEAN"),
    "object": sql.Identifier("_r2db_json_object"),
    "array": sql.Identifier("_r2db_json_array"),
    # Phase 6 WP-2 (design D-3, r2db decision (c)): `json` maps to the same
    # bare JSONB every untyped field already used -- `bind_schema_operation`
    # (structured.py) translates a declared `json` to the internal `None`
    # representation before this dict is ever consulted for it, so this
    # entry is not reached by that path; it exists so a per-field DDL
    # applier that looks a type word up here directly (rather than
    # special-casing `None` first) never hits a `KeyError` for `json`.
    "json": _JSONB_SQL,
}


def _column_type_sql(field_type: str | None) -> sql.SQL | sql.Identifier:
    """Shared by `_add_field` and `_create_entity`'s own per-field DDL (in `postgres.py`)
    (Phase 6 WP-2, design D-3): `None` (untyped/json) is the pre-CCR-13
    JSONB default; any other value is looked up in `_FIELD_TYPE_SQL`
    (falling back to JSONB defensively, never `KeyError`, for a value this
    dict does not carry -- `bind_schema_operation` is the real gate that
    already restricts values to the 7-word vocabulary before either caller
    is reached)."""
    if field_type is None:
        return _JSONB_SQL
    return _FIELD_TYPE_SQL.get(field_type, _JSONB_SQL)
