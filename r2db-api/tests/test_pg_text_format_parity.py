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

Not covered here (filed as R-123, work order section 5): `_float8out_text`
at 1e15 <= |x| < 1e16 and `_jsonb_numeric_text(-0.0)` disagree with a real
server today, so no value in either range is asserted.
"""
from __future__ import annotations

import types

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
