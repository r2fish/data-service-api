"""Pure PostgreSQL type-mapping constants for the MitateDB storage backend."""
from __future__ import annotations

from psycopg import sql

# Foundation field-type vocabulary -> this backend's own native column
# type. `boolean` maps to `INTEGER`, not PostgreSQL's native `BOOLEAN`
# type, DELIBERATELY: PostgreSQL has no implicit (nor even explicit,
# `::boolean`/`::integer`) cast between `boolean` and any integer type, so
# a bound Python `bool` (this module's own `encode_value` below (in `backend_postgres.py`) converts
# every `bool` to `int`, matching the SQLite backend's own already-
# existing conversion) would fail to bind against a genuinely
# `BOOLEAN`-typed column. Using `INTEGER` for both backends' own
# `boolean` field type keeps their observable behavior identical (both
# backends store and round-trip a declared-boolean field as 0/1) without
# either backend needing to know the OTHER exists.
#
# m-7 (independent review): every value here is precomposed as a
# `sql.SQL` constant (not a bare Python string later joined with `+`), so
# every call site that uses one composes SQL exclusively via `.format()`
# placeholders -- no method in this module (in `backend_postgres.py`) builds a statement fragment by
# Python string concatenation.
_TYPES = {"text": "TEXT", "integer": "BIGINT", "real": "DOUBLE PRECISION",
          "boolean": "INTEGER", "json": "TEXT"}
_TYPE_SQL = {name: sql.SQL(native) for name, native in _TYPES.items()}

# B-1 (i): reverse map from PostgreSQL's own `information_schema.columns.
# data_type` string back to a DOMAIN category `encode_value` validates
# against, for the three UNAMBIGUOUS physical types (`bigint`/`integer`/
# `double precision` each correspond to exactly one foundation type --
# `integer`/`boolean`/`real` respectively). A physical `text` column does
# NOT get its domain from this table any more (Phase 6 WP-3, design D-3,
# L6-1 (v) correction of this comment's own prior claim): `text` covers
# FOUR distinct contract-vocabulary declared types on this backend
# (`string`/`object`/`array`/`json`, all physically TEXT) that a value
# declared `object` must NOT be treated as interchangeable with one
# declared `array` -- see `field_domains` below (in `backend_postgres.py`), which now sources a
# `text`-physical column's own domain from the declared-type REGISTRY
# (`_mdb_field_types`), never from `information_schema` alone. What
# nothing downstream needs to recover is a column's PHYSICAL storage
# class (still just TEXT either way) -- but it very much needs to recover
# WHICH declared contract type that physical TEXT column carries, and
# `information_schema` alone cannot answer that question.
_DOMAIN_BY_DATA_TYPE = {
    "bigint": "int64",           # this foundation's own `integer`
    "integer": "int32",          # this foundation's own `boolean`
    "double precision": "float",  # this foundation's own `real`
}

# Phase 6 WP-3 (design D-3): declared contract type (from the registry) ->
# this backend's own `_check_domain` category, for every declared type
# whose physical column is `text`. Kept as three DISTINCT domain names
# (never folded into one shared `"text"`) so `_check_domain` can, in
# principle, tell them apart -- even though, by the time a value reaches
# `encode_value`, `cell.ApplicationCell._normalize_value_for_storage` has
# already turned an `object`/`array`/`json`-declared value into a plain
# JSON-text `str` (the PRIMARY object-vs-array-vs-json shape check
# already ran, backend-independently, at that cell-layer choke point,
# design G3) -- so this backend's own check is `isinstance(value, str)`
# for all three, exactly as for `string`, and stays real defence-in-depth
# against anything that reaches this backend without going through that
# choke point.
_TEXT_DOMAIN_BY_DECLARED_TYPE = {
    "string": "string",
    "object": "object",
    "array": "array",
    "json": "json",
}
