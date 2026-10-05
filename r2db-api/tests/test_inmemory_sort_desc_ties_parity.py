"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-2a..C1-2c): the in-memory ordering (`inmemory_sort._sort_rows`,
`_sort_key`, `_after_page_cursor`) against a real PostgreSQL for three
shapes no earlier test fixed -- tied rows under a descending `order_by`
(the id tie-break stays ascending), a typed `boolean` column's ascending
and descending order, and keyset paging over that boolean column.

Every test runs the same query against the in-memory `ApplicationCell` and
a real `PostgresCell` (the `test_postgres.py` fixture route: `app_a`,
`make_cell`) and asserts both return the literal id sequence below -- a
real server is the oracle, so the literals are PostgreSQL's own result for
`order by <field> <direction>, id asc`, and each sequence is non-empty.
"""
from __future__ import annotations

import types

from r2db_api.inmemory_sort import _after_page_cursor
from r2db_api.structured import ApplicationCell

from test_postgres import LIMITS, app_a, make_cell, platform  # noqa: F401 (fixtures)


def _ids(cell, entity: str, order_by: list, select: list[str]) -> list[int]:
    rows = cell.query(entity, select=select, where=[], page_size=50, limits=LIMITS, order_by=order_by).items
    assert rows, (entity, order_by)
    return [row["id"] for row in rows]


def _walk_ids(cell, entity: str, order_by: list, page_size: int) -> list[int]:
    walked: list[int] = []
    cursor = None
    pages = 0
    while True:
        page = cell.query(entity, select=["id", "flag"], where=[], page_size=page_size, limits=LIMITS, order_by=order_by, cursor=cursor)
        walked.extend(row["id"] for row in page.items)
        pages += 1
        assert pages <= 10, (entity, order_by, page_size)
        if page.next_cursor is None:
            return walked
        cursor = page.next_cursor


def _seed_flag(cell) -> None:
    cell.apply_schema({"operation": "create_entity", "entity": "flags", "fields": []}, developer=True, limits=LIMITS)
    cell.apply_schema({"operation": "add_field", "entity": "flags", "field": "flag", "field_type": "boolean"}, developer=True, limits=LIMITS)
    cell.transact("flags", [{"operation": "insert", "values": {"flag": flag}} for flag in (True, False, True, False)], LIMITS)


def test_descending_order_keeps_tied_rows_in_id_ascending_order(app_a: types.SimpleNamespace) -> None:
    """C1-2a: bucket x,x,x,y,y (ids 1-5) ordered by bucket desc is
    `[4, 5, 1, 2, 3]` -- the two `y` rows first, and within each tie the
    id ascends -- on both cells; ascending is `[1, 2, 3, 4, 5]`."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            cell.apply_schema({"operation": "create_entity", "entity": "rows", "fields": ["bucket"]}, developer=True, limits=LIMITS)
            cell.transact("rows", [{"operation": "insert", "values": {"bucket": bucket}} for bucket in "xxxyy"], LIMITS)
        desc = [{"field": "bucket", "direction": "desc"}]
        asc = [{"field": "bucket", "direction": "asc"}]
        assert _ids(pg, "rows", desc, ["id", "bucket"]) == [4, 5, 1, 2, 3]
        assert _ids(mem, "rows", desc, ["id", "bucket"]) == [4, 5, 1, 2, 3]
        assert _ids(pg, "rows", asc, ["id", "bucket"]) == [1, 2, 3, 4, 5]
        assert _ids(mem, "rows", asc, ["id", "bucket"]) == [1, 2, 3, 4, 5]
    finally:
        pg.close()


def test_typed_boolean_column_orders_false_before_true_ascending_and_reverse_descending(app_a: types.SimpleNamespace) -> None:
    """C1-2b: a typed boolean column holding True, False, True, False
    (ids 1-4): ascending is `[2, 4, 1, 3]` (the False rows, then the True
    rows, ties by id), descending `[1, 3, 2, 4]`, on both cells."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            _seed_flag(cell)
        for cell in (pg, mem):
            assert _ids(cell, "flags", [{"field": "flag", "direction": "asc"}], ["id", "flag"]) == [2, 4, 1, 3]
            assert _ids(cell, "flags", [{"field": "flag", "direction": "desc"}], ["id", "flag"]) == [1, 3, 2, 4]
    finally:
        pg.close()


def test_keyset_paging_over_a_typed_boolean_column_continues_after_the_cursor_value(app_a: types.SimpleNamespace) -> None:
    """C1-2c: walking the typed boolean column with `page.cursor` at page
    sizes 1 and 2 yields exactly the unpaged order, ascending `[2, 4, 1,
    3]` and descending `[1, 3, 2, 4]`, on both cells; and
    `_after_page_cursor` itself, read directly: after the cursor row
    (False, id 2) in an ascending order sit (False, id 4) and any True
    row, but not (False, id 1) nor the cursor row itself; descending
    reverses the boolean term only."""
    pg = make_cell(app_a)
    mem = ApplicationCell("parity-app", {})
    try:
        for cell in (pg, mem):
            _seed_flag(cell)
        for cell in (pg, mem):
            for page_size in (1, 2):
                assert _walk_ids(cell, "flags", [{"field": "flag", "direction": "asc"}], page_size) == [2, 4, 1, 3], page_size
                assert _walk_ids(cell, "flags", [{"field": "flag", "direction": "desc"}], page_size) == [1, 3, 2, 4], page_size
    finally:
        pg.close()

    asc = [("flag", "asc"), ("id", "asc")]
    desc = [("flag", "desc"), ("id", "asc")]
    assert _after_page_cursor([False, 4], [False, 2], asc) is True
    assert _after_page_cursor([True, 1], [False, 2], asc) is True
    assert _after_page_cursor([False, 1], [False, 2], asc) is False
    assert _after_page_cursor([False, 2], [False, 2], asc) is False
    assert _after_page_cursor([False, 2], [True, 3], asc) is False
    assert _after_page_cursor([False, 2], [True, 3], desc) is True
    assert _after_page_cursor([True, 1], [True, 3], desc) is False
