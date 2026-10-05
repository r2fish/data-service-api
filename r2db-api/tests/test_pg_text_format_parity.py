"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-1a..C1-1c): `pg_text_format`'s three text forms that no earlier test
fixed -- a typed `number` column's negative exponent (`_float8out_text`),
an untyped column's jsonb numeric expansion of a small magnitude
(`_jsonb_numeric_text`), and a jsonb object's non-ASCII key order
(`_jsonb_text`).

Each test has two halves. The parity half drives the SAME `contains` /
`matches` needle through the in-memory `ApplicationCell` and a real
`PostgresCell` (the `test_postgres.py` fixture route: `app_a`, `make_cell`)
and asserts both cells return the same rows AND at least one row where a
needle is expected to hit (a needle that matches nothing on either cell
would "agree" vacuously). The leaf half calls the function directly with
the literal expected text. The expected texts are the ones a real
PostgreSQL 16.14 server measured (work order section 3.3).

R-123 added the four tests at the end of this file, each with a parity half
and a leaf half like the three above: C-1 `_float8out_text` at 1e15 <=
|x| < 1e16 (exponent form, plain form still up to 1e14); C-2
`_jsonb_numeric_text(-0.0)` (jsonb has no negative zero, a typed `number`
column's `-0` is unchanged); C-3 `_float8out_text` at the exact edge of a
double's rounding interval (1e23, 2.895354861634331e+16), checked over a
corpus of several thousand values against one real-server SELECT; C-4 a JSON
integer in a typed `number` column (a `double precision` cast like any other
value of the column).
"""
from __future__ import annotations

import math
import random
import struct
import types

import psycopg

from r2db_api.inmemory_predicate import _predicate_text
from r2db_api.pg_text_format import _float8out_text, _jsonb_numeric_text, _jsonb_text
from r2db_api.structured import ApplicationCell, Predicate

from test_postgres import LIMITS, P, app_a, make_cell, platform  # noqa: F401 (fixtures)


def _both_rows(pg, mem, entity: str, field: str, operator: str, needle: str) -> list:
    pg_items = pg.query(entity, select=[field], where=[P(field, operator, needle)], page_size=10, limits=LIMITS).items
    mem_items = mem.query(entity, select=[field], where=[Predicate(field, operator, needle)], page_size=10, limits=LIMITS).items
    assert pg_items == mem_items, (entity, operator, needle)
    return pg_items


def _expect_hit(pg, mem, entity: str, field: str, needle: str, expected_value) -> None:
    for operator in ("contains", "matches"):
        rows = _both_rows(pg, mem, entity, field, operator, needle)
        assert rows == [{field: expected_value}], (entity, operator, needle)


def _expect_miss(pg, mem, entity: str, field: str, needle: str) -> None:
    for operator in ("contains", "matches"):
        assert _both_rows(pg, mem, entity, field, operator, needle) == [], (entity, operator, needle)


def test_float8_negative_exponent_text_matches_postgres(app_a: types.SimpleNamespace) -> None:
    """C1-1a: a typed `number` column holding 1e-5, 1.5e-7, -1e-7 -- the
    text a needle sees is `float8out`'s `1e-05` / `1.5e-07` / `-1e-07`
    (two-digit exponent, zero padded), on both cells; the unpadded
    spellings are not found on either."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "readings", "fields": []}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "readings", "field": "n", "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("readings", [{"operation": "insert", "values": {"n": value}} for value in (1e-5, 1.5e-7, -1e-7)], LIMITS)

        _expect_hit(pg, mem, "readings", "n", "1e-05", 1e-5)
        _expect_hit(pg, mem, "readings", "n", "1.5e-07", 1.5e-7)
        _expect_hit(pg, mem, "readings", "n", "-1e-07", -1e-7)
        _expect_miss(pg, mem, "readings", "n", "1e-5")
        _expect_miss(pg, mem, "readings", "n", "1.5e-7")
        _expect_miss(pg, mem, "readings", "n", "-1e-7")
    finally:
        pg.close()

    assert _float8out_text(1e-5) == "1e-05"
    assert _float8out_text(1.5e-7) == "1.5e-07"
    assert _float8out_text(-1e-7) == "-1e-07"


def test_jsonb_numeric_small_magnitude_is_expanded_like_postgres(app_a: types.SimpleNamespace) -> None:
    """C1-1b: an untyped column holding 1e-07 and 1.234e-05 -- jsonb
    renders them as plain decimals (`0.0000001`, `0.00001234`), never the
    exponent form, on both cells."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["n"]}, developer=True, limits=LIMITS)
            cell.transact("items", [{"operation": "insert", "values": {"n": value}} for value in (1e-07, 1.234e-05)], LIMITS)

        _expect_hit(pg, mem, "items", "n", "0.0000001", 1e-07)
        _expect_hit(pg, mem, "items", "n", "0.00001234", 1.234e-05)
        _expect_miss(pg, mem, "items", "n", "1e-07")
        _expect_miss(pg, mem, "items", "n", "1.234e-05")
    finally:
        pg.close()

    assert _jsonb_numeric_text(1e-07) == "0.0000001"
    assert _jsonb_numeric_text(1.234e-05) == "0.00001234"


def test_jsonb_object_key_order_with_non_ascii_keys_matches_postgres(app_a: types.SimpleNamespace) -> None:
    """C1-1c: keys `z`, `ab`, `é`, `日本` come out in `(byte length, byte
    value)` order -- 1, 2, 2 (`ab` before `é`: 0x61 < 0xC3), 6 bytes -- on
    both cells, and the leaf renders the identical text."""
    value = {"é": 1, "z": 2, "ab": 3, "日本": 4}
    rendered = '{"z": 2, "ab": 3, "é": 1, "日本": 4}'
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["payload"]}, developer=True, limits=LIMITS)
            cell.transact("items", [{"operation": "insert", "values": {"payload": value}}], LIMITS)

        _expect_hit(pg, mem, "items", "payload", rendered, value)
        # The byte-only order (no length term) is `ab, z, é, 日本`.
        _expect_miss(pg, mem, "items", "payload", '{"ab": 3, "z": 2, "é": 1, "日本": 4}')
    finally:
        pg.close()

    assert _jsonb_text(value) == rendered


def test_float8_text_at_1e15_to_1e16_is_exponent_form_like_postgres(app_a: types.SimpleNamespace) -> None:
    """R-123 C-1: `float8out` switches to the exponent form once the first
    digit's decimal exponent reaches 15 (Python's `repr` waits for 16). A
    typed `number` column holding 1e15, 1000000000000000.1,
    9999999999999998, -1234567890123456 shows `1e+15`,
    `1.0000000000000001e+15`, `9.999999999999998e+15`,
    `-1.234567890123456e+15` on both cells; the plain spellings are found
    on neither. 1e14 and 100.0 stay plain (`100000000000000`, `100`) and
    1e20 stays `1e+20`. One column per value so a needle cannot hit a
    second value's text."""
    cases = [
        ("n1", 1e15, "1e+15", "1000000000000000"),
        ("n2", 1000000000000000.1, "1.0000000000000001e+15", "1000000000000000.1"),
        ("n3", 9999999999999998.0, "9.999999999999998e+15", "9999999999999998"),
        ("n4", -1234567890123456.0, "-1.234567890123456e+15", "-1234567890123456"),
        ("n5", 1e14, "100000000000000", None),
        ("n6", 100.0, "100", None),
        ("n7", 1e20, "1e+20", None),
    ]
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "wide", "fields": []}, developer=True, limits=LIMITS)
            for field, _value, _text, _plain in cases:
                cell.apply_schema({"operation": "add_field", "entity": "wide", "field": field, "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("wide", [{"operation": "insert", "values": {field: value for field, value, _t, _p in cases}}], LIMITS)

        for field, value, text, plain in cases:
            _expect_hit(pg, mem, "wide", field, text, value)
            if plain is not None:
                _expect_miss(pg, mem, "wide", field, plain)
    finally:
        pg.close()

    for _field, value, text, _plain in cases:
        assert _float8out_text(value) == text


def test_jsonb_negative_zero_is_zero_like_postgres(app_a: types.SimpleNamespace) -> None:
    """R-123 C-2: jsonb's numeric has no negative zero, so an untyped
    column's -0.0 is `0.0` at the top level, inside an array and inside an
    object (never `-0.0`), on both cells. A typed `number` column's -0.0
    stays `-0` (float8out keeps the sign), pinned here as unchanged."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "zeros", "fields": ["top", "arr", "obj"]}, developer=True, limits=LIMITS)
            cell.apply_schema({"operation": "add_field", "entity": "zeros", "field": "typed", "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("zeros", [{"operation": "insert", "values": {"top": -0.0, "arr": [-0.0], "obj": {"a": -0.0}, "typed": -0.0}}], LIMITS)

        _expect_hit(pg, mem, "zeros", "top", "0.0", -0.0)
        _expect_hit(pg, mem, "zeros", "arr", "[0.0]", [-0.0])
        _expect_hit(pg, mem, "zeros", "obj", '{"a": 0.0}', {"a": -0.0})
        _expect_miss(pg, mem, "zeros", "top", "-0.0")
        _expect_miss(pg, mem, "zeros", "arr", "[-0.0]")
        _expect_miss(pg, mem, "zeros", "obj", '{"a": -0.0}')
        _expect_hit(pg, mem, "zeros", "typed", "-0", -0.0)
    finally:
        pg.close()

    assert _jsonb_numeric_text(-0.0) == "0.0"
    assert _jsonb_numeric_text(0.0) == "0.0"
    assert _jsonb_text([-0.0]) == "[0.0]"
    assert _jsonb_text({"a": -0.0}) == '{"a": 0.0}'
    assert _float8out_text(-0.0) == "-0"
    assert _float8out_text(0.0) == "0"


def _float8_corpus() -> list[float]:
    """Finite doubles only (a JSON input never carries inf / nan)."""
    values: list[float] = []
    for k in range(-1074, 1024):
        power = math.ldexp(1.0, k)
        values.extend((power, math.nextafter(power, 0.0), math.nextafter(power, math.inf)))
    for exponent in range(-323, 309):
        power = float(f"1e{exponent}")
        values.extend((power, math.nextafter(power, 0.0), math.nextafter(power, math.inf)))
    values.extend((1e23, 2.895354861634331e16, 5e-324, 1.7976931348623157e308, 0.0))
    for edge in (1e15, 1e16, 1e-4, 1e-5):
        values.append(edge)
        for direction in (0.0, math.inf):
            value = edge
            for _ in range(3):
                value = math.nextafter(value, direction)
                values.append(value)
    rng = random.Random(123)
    random_values = 0
    while random_values < 2000:
        value = struct.unpack("<d", rng.getrandbits(64).to_bytes(8, "little"))[0]
        if math.isfinite(value):
            values.append(value)
            random_values += 1
    values.extend(-value for value in values[::5] if value != 0.0)
    return [value for value in values if math.isfinite(value)]


def test_float8_text_at_a_rounding_interval_edge_matches_postgres(app_a: types.SimpleNamespace) -> None:
    """R-123 C-3: PostgreSQL's shortest-digits algorithm excludes both ends
    of a double's rounding interval, so a value whose repr digits sit
    exactly on an end gets a longer digit string: 1e23 is
    `9.999999999999999e+22` and 2.895354861634331e+16 is
    `2.8953548616343312e+16` (never `1e+23` / `2.895354861634331e+16`).
    The parity half pins both on both cells; the leaf half compares
    `_float8out_text` with one real-server `select v::text from
    unnest(float8[])` over a corpus of powers of two and their neighbours,
    powers of ten and their neighbours, the 1e15 / 1e16 / 1e-4 / 1e-5
    switch points, the extreme values and 2000 seeded random bit patterns
    -- and asserts the corpus is not small (a short corpus would agree
    vacuously)."""
    cases = [
        ("e1", 1e23, "9.999999999999999e+22", "1e+23"),
        ("e2", 2.895354861634331e+16, "2.8953548616343312e+16", "2.895354861634331e+16"),
    ]
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "edges", "fields": []}, developer=True, limits=LIMITS)
            for field, _value, _text, _repr in cases:
                cell.apply_schema({"operation": "add_field", "entity": "edges", "field": field, "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("edges", [{"operation": "insert", "values": {field: value for field, value, _t, _r in cases}}], LIMITS)

        for field, value, text, repr_text in cases:
            _expect_hit(pg, mem, "edges", field, text, value)
            _expect_miss(pg, mem, "edges", field, repr_text)
    finally:
        pg.close()

    corpus = _float8_corpus()
    assert len(corpus) > 3000
    with psycopg.connect(app_a.runtime_dsn) as conn:
        rows = conn.execute("select v::text from unnest(%s::float8[]) with ordinality as t(v, i) order by i", (corpus,)).fetchall()
    assert len(rows) == len(corpus)

    mismatches = [(value, row[0], _float8out_text(value)) for value, row in zip(corpus, rows) if _float8out_text(value) != row[0]]
    assert mismatches == []


def test_typed_number_column_integer_is_float8_text_like_postgres(app_a: types.SimpleNamespace) -> None:
    """R-123 C-4: a JSON integer stored in a typed `number` column is a
    `double precision` value, so its `::text` is `float8out`'s: 10**15 is
    `1e+15`, 10**20 is `1e+20`, 42 stays `42`, on both cells; the plain
    spellings (`1000000000000000`, `100000000000000000000`) are found on
    neither. The leaf half pins `_predicate_text` for the same integers
    and that an untyped column keeps the integer's own text (jsonb numeric
    keeps it verbatim). One column per value."""
    cases = [
        ("i1", 10**15, "1e+15", "1000000000000000"),
        ("i2", 10**20, "1e+20", "100000000000000000000"),
        ("i3", 42, "42", None),
    ]
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "ints", "fields": []}, developer=True, limits=LIMITS)
            for field, _value, _text, _plain in cases:
                cell.apply_schema({"operation": "add_field", "entity": "ints", "field": field, "field_type": "number"}, developer=True, limits=LIMITS)
            cell.transact("ints", [{"operation": "insert", "values": {field: value for field, value, _t, _p in cases}}], LIMITS)

        for field, value, text, plain in cases:
            _expect_hit(pg, mem, "ints", field, text, value)
            if plain is not None:
                _expect_miss(pg, mem, "ints", field, plain)
    finally:
        pg.close()

    assert _predicate_text(10**15, "number") == "1e+15"
    assert _predicate_text(10**20, "number") == "1e+20"
    assert _predicate_text(42, "number") == "42"
    assert _predicate_text(10**15, None) == "1000000000000000"
