"""PostgreSQL text-output reproduction for jsonb and `double precision` (ST1).

This is a pure leaf: every function is a total, deterministic string
transform of an already-typed Python value. It opens no connection, reads
no catalog, and consults no request/limits/principal state; the choke
points that decide *which* of these functions applies to a given column
(`PostgresCell._text_expression`, `inmemory_predicate._predicate_text`)
remain in their own modules.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _float8out_text(value: float) -> str:
    """PostgreSQL `double precision`'s own text-output function,
    `float8out` (WP-3 confirmation review N-1) -- reproduced ONLY for a
    TYPED `"number"` column's TOP-LEVEL scalar (`PostgresCell._text_
    expression`'s plain `::text` cast on a real `double precision` column
    invokes this natively; nothing else in this file (`structured.py`) does). An integer-
    valued float drops its Python-repr trailing `.0` (`100.0` -> `"100"`).
    A value already in scientific notation (`repr`'s own choice for
    sufficiently large/small magnitudes, e.g. `1e+20`) never ends in `.0`
    to begin with, and PostgreSQL's own `float8out` for such magnitudes
    also uses scientific notation matching Python's -- so it passes
    through unchanged.
    """
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def _jsonb_numeric_text(value: float) -> str:
    """PostgreSQL jsonb's own numeric storage/output (WP-3 confirmation
    review N-1) -- used for every OTHER float position: an UNTYPED top-
    level column, or ANY nested position inside a dict/list, regardless of
    the enclosing field's own declared type (jsonb storage is jsonb either
    way, whether the column is bare or one of this backend's `_r2db_json_
    object`/`_r2db_json_array` DOMAINs over it). Confirmed empirically
    against a real server: jsonb preserves a number's original literal
    text almost verbatim, INCLUDING trailing zeros (`'100.0'::jsonb #>>
    '{}'` stays `"100.0"`, never drops the `.0` the way `float8out` does),
    but always EXPANDS scientific notation to full plain-decimal digits
    (`'1e+20'::jsonb #>> '{}'` -> `"100000000000000000000"`, never
    `"1e+20"`).

    `json.dumps(value)` reproduces the exact text psycopg's `Jsonb` adapter
    sends at INSERT time (this project's own round-trip) -- confirmed
    empirically to match jsonb's stored/re-emitted text byte-for-byte for
    every case that does not need exponent expansion. `Decimal` expands
    the scientific-notation case the same way PostgreSQL's own numeric
    parser does (exact decimal arithmetic, no float re-rounding): `Decimal
    (json.dumps(value))` parses the very same text, and `format(...,
    "f")` renders it in fixed (non-exponential) notation.
    """
    text = json.dumps(value)
    if "e" in text or "E" in text:
        return format(Decimal(text), "f")
    return text


def _jsonb_scalar_text(value: Any) -> str:
    """A JSON scalar's PostgreSQL `jsonb` text-output form for a NESTED
    position (inside a dict/list), or for an untyped, non-float, top-level
    scalar: `boolean` is the lowercase `true`/`false` literal; `float` uses
    `_jsonb_numeric_text` above (jsonb's own numeric rules, never
    `float8out` -- a nested float is never affected by the enclosing
    field's own declared type, since nesting only exists inside jsonb
    storage to begin with).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _jsonb_numeric_text(value)
    if value is None:
        return "null"
    return str(value)  # pragma: no cover - value is always JSON-shaped


def _jsonb_text(value: Any) -> str:
    """PostgreSQL's own `jsonb` text-output rendering for a dict/list value
    (WP-3 review N-1/N-2), used both directly (`_predicate_text`, below (in
    `inmemory_predicate.py`)) and recursively for a nested dict/list. Object
    key order is PostgreSQL's own storage order -- *not* the order the keys
    were written in JSON source, and not Python's default string sort either:
    `(byte length, byte value)`, ascending (confirmed empirically against a
    real server). Nested strings are quoted (`json.dumps`, `ensure_ascii=
    False` to keep non-ASCII characters literal like PostgreSQL's own jsonb
    text output does, rather than Python's default `\\uXXXX` escaping);
    nested scalars reuse `_jsonb_scalar_text` above (never `_float8out_
    text`: nesting only exists inside jsonb storage, so a nested float is
    always jsonb's own numeric rules, independent of whatever the
    enclosing top-level field's own declared type is).
    """
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: (len(k.encode("utf-8")), k.encode("utf-8")))
        parts = [f"{json.dumps(key, ensure_ascii=False)}: {_jsonb_text(value[key])}" for key in keys]
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_jsonb_text(item) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return _jsonb_scalar_text(value)
