"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-4a, C1-4b): `matches` over a label that contains or ends with a newline,
in-memory `ApplicationCell` against a real `PostgresCell`.

`inmemory_predicate`'s compiled pattern must agree with PostgreSQL's
`LIKE` on two newline cases: `_` and `%` match a newline (`'a\\nb' like
'a_b'` and `like 'a%b'` are both true), and a pattern without a wildcard
does not match a value that merely ends in a newline (`'a\\n' like 'a'` is
false, `like 'a%'` is true). Expected values: a real PostgreSQL 16.14
server (work order section 3.3). Each test asserts the literal rows and
that at least one row is found, on both cells.
"""
from __future__ import annotations

import types

from r2db_api.structured import ApplicationCell, Predicate

from test_postgres import LIMITS, P, app_a, make_cell, platform  # noqa: F401 (fixtures)


def _matches_rows(pg, mem, needle: str) -> list:
    pg_items = pg.query("items", select=["label"], where=[P("label", "matches", needle)], page_size=10, limits=LIMITS).items
    mem_items = mem.query("items", select=["label"], where=[Predicate("label", "matches", needle)], page_size=10, limits=LIMITS).items
    assert pg_items == mem_items, needle
    return pg_items


def _cells(app_a: types.SimpleNamespace, labels: list[str]):
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    for cell in (pg, mem):
        cell.apply_schema({"operation": "create_entity", "entity": "items", "fields": ["label"]}, developer=True, limits=LIMITS)
        cell.transact("items", [{"operation": "insert", "values": {"label": label}} for label in labels], LIMITS)
    return pg, mem


def test_matches_wildcards_match_a_newline_like_postgres(app_a: types.SimpleNamespace) -> None:
    """C1-4a: label `"a\\nb"` is found by `a_b` and by `a%b`."""
    pg, mem = _cells(app_a, ["a\nb"])
    try:
        assert _matches_rows(pg, mem, "a_b") == [{"label": "a\nb"}]
        assert _matches_rows(pg, mem, "a%b") == [{"label": "a\nb"}]
    finally:
        pg.close()


def test_matches_without_a_wildcard_does_not_match_a_trailing_newline_like_postgres(app_a: types.SimpleNamespace) -> None:
    """C1-4b: label `"a\\n"` is not found by `a`, and is found by `a%`."""
    pg, mem = _cells(app_a, ["a\n"])
    try:
        assert _matches_rows(pg, mem, "a") == []
        assert _matches_rows(pg, mem, "a%") == [{"label": "a\n"}]
    finally:
        pg.close()
