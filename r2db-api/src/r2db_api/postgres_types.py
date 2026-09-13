"""PostgreSQL DDL type objects for the r2db storage backend.

This is a pure leaf: it only maps an already validated contract field-type
word to a psycopg SQL composition object.  It neither opens a connection nor
executes SQL; catalog validation and every transaction boundary remain in
``postgres.PostgresCell``.
"""
from __future__ import annotations

from psycopg import sql


# `object` and `array` are PostgreSQL domain identifiers, while the other
# entries are built-in type keywords.  Keeping that distinction in the SQL
# object prevents either kind of name from being interpolated as raw text.
_JSONB_SQL = sql.SQL("JSONB")
_FIELD_TYPE_SQL: dict[str, sql.SQL | sql.Identifier] = {
    "string": sql.SQL("TEXT"),
    "integer": sql.SQL("BIGINT"),
    "number": sql.SQL("DOUBLE PRECISION"),
    "boolean": sql.SQL("BOOLEAN"),
    "object": sql.Identifier("_r2db_json_object"),
    "array": sql.Identifier("_r2db_json_array"),
    "json": _JSONB_SQL,
}


def _column_type_sql(field_type: str | None) -> sql.SQL | sql.Identifier:
    """Return the safe DDL type object for a validated field type.

    ``None`` is the untyped/JSON default.  The defensive JSONB fallback is
    intentionally retained for callers that bypass the normal binding gate;
    no client-provided text is ever made into SQL here.
    """
    if field_type is None:
        return _JSONB_SQL
    return _FIELD_TYPE_SQL.get(field_type, _JSONB_SQL)
