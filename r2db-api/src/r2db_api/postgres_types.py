"""PostgreSQL type objects and catalog value maps for the r2db storage backend.

This is a pure leaf: it maps an already validated contract field-type word
to a psycopg SQL composition object, maps PostgreSQL's own catalog
type/domain reporting back to the shared declared-type vocabulary, and
holds the ``_TableInfo`` record ``PostgresCell._load_catalog`` fills in. It
neither opens a connection nor executes SQL; catalog validation and every
transaction boundary remain in ``postgres.PostgresCell``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


# The two DOMAIN types' own bare names (as `information_schema.columns.domain_name` reports them -- unqualified confirmed empirically), mapped back to the shared `r2db_api.structured` vocabulary string `_load_catalog` reports for such a column's declared type.
# history: CH-0005
_DOMAIN_TO_DECLARED: dict[str, str] = {
    "_r2db_json_object": "object",
    "_r2db_json_array": "array",
}

# The inverse mapping, used by `_load_catalog` to recover each column's
# declared type (in the shared `r2db_api.structured` vocabulary: "string"/
# "integer"/"number"/"boolean", or `None` for untyped/JSONB-equivalent) from
# PostgreSQL's own `information_schema.columns.data_type` reporting, for a
# column that is *not* one of the two DOMAINs above (`_DOMAIN_TO_DECLARED`
# is consulted first -- see `_load_catalog`). `id` also happens to be
# `bigint` (looked up through this same table -- it is not a distinct
# physical type from a user-declared `field_type: "integer"` column, only a
# distinct *role*, which `_load_catalog` tracks separately).
_SQL_TYPE_TO_DECLARED: dict[str, str] = {
    "text": "string",
    "bigint": "integer",
    "double precision": "number",
    "boolean": "boolean",
}


@dataclass
class _TableInfo:
    """One entity table's live shape, as re-derived from PostgreSQL's own catalog by `PostgresCell._load_catalog` on every call (never cached across calls, never trusted as a standing assumption --).

    `columns`: declared field name -> declared type in the shared
    `r2db_api.structured` vocabulary (`"string"`/`"integer"`/`"number"`/
    `"boolean"`/`"object"`/`"array"`), or `None` for an untyped/JSONB-
    equivalent column. `"object"`/`"array"` are recovered from PostgreSQL's own `information_schema.columns.domain_name` ("object/array の DOMAIN 型統一") -- a plain `jsonb` column with no domain reports `None`. Includes `"id"` (always `"integer"`); never includes the invisible `"_r2db_revision"` column.

    `indexes`: client index name -> `{"physical": <table>__<index> name,
    "fields": (declared field name, ...), "unique": bool}`, covering every
    index `PostgresCell.apply_schema`'s own `create_index` has created on
    this table (both unique and non-unique -- SI-08/R-5: both count toward
    `schema_objects`), excluding the primary key on `id` (R-1/§2: an
    address, not a domain uniqueness declaration).

    History: CH-0006
    """

    columns: dict[str, str | None]
    indexes: dict[str, dict[str, Any]]
    # Contract 1.7.0: this entity's own declared `enum`/`nullable` constraints, read from the side-table registry (`_load_field_constraints` below (in `postgres.py`)) -- field name -> `FieldConstraints`, present ONLY for a field something was actually declared on (`FieldConstraints.is_declared`), same "absence = default" convention `columns`/`indexes` above never needed (there is no "undeclared column"). Defaults to `{}` so every EXISTING call site that builds a
    # `_TableInfo` without constraints in mind (there are none left after
    # this WP, but a future one) keeps working.
    # history: CH-0101
    constraints: dict[str, "FieldConstraints"] = field(default_factory=dict)
