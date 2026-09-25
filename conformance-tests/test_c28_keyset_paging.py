"""C-28 -- a peer declaring contract 1.9.0 returns query results in a
total order and pages them with a stateless keyset cursor (SI-01, SI-08,
SI-10).

design: docs/design/PHASE11_KEYSET_PAGING_V1.md D-4 (port `query_page`,
the 9-node split, the "空振り禁止" paragraph, the node-transition table),
§6.1 (Condition/Status text), §6.2 (relationship to existing conditions),
§6.3 (port v1.16); registered in `conformance-tests/CONDITIONS.md`. Every
test here carries `@pytest.mark.condition("C-28")` via the module-level
`pytestmark`.

Work order: docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md §3
(WP-2) task 3 and its own node table (§1.5).

Version-gated exactly like C-21/C-25/C-27 -- branches on the plug's own
declared `contract_version` (`adapter.parse_semver`, never a string
compare), with the runtime-attached `xfail` read at execution time
(`request.node.add_marker`). Only the concurrent-insert node
(`test_c28_concurrent_insert_discriminates_keyset_from_offset`, design D-4
(ii)) is `xfail(strict=True)` -- an offset implementation (or a 1.8.0 peer
with no keyset cursor at all) is EXPECTED to fail it, so passing it under a
still-1.8.0 declaration means the peer's own real behavior has outrun its
own declaration (D-1(7)). The other 8 nodes are `xfail(strict=False)`: an
offset-shaped or partially-keyset-shaped implementation may already
satisfy them honestly (r2db-api's own pre-existing `order_by`/`cursor`
support, CCR-13), and this suite must not call that a bug.

The `observed_branch` cross-check against the plug's own declared version
(work order §1's own hand-off from `WORK_ORDER_PHASE9_CONTRACT_170_V1.md`
§6 correction 7, mirrored from `test_c25_result_request_id.py`:433-450
and `test_c21_denial_details_vocabulary.py`:366-385) is done ONLY in the
`>= 1.9.0` branch: doing it unconditionally would make `expected_branch`
always disagree with a hardcoded `observed_branch` in the `< 1.9.0`
branch, making a genuine strict XPASS structurally impossible there. In
the `< 1.9.0` branch, each node's own unconditional body assertions above
are the entire detection mechanism.

**Disclosed** (design D-4's own "空振り禁止"/Status paragraphs, carried
into `CONDITIONS.md`'s own C-28 row): statelessness and determinism are
not falsifiable by this port alone (no registered plug spans more than
one process); connection independence and whether a cursor's own bytes
hold a coarse timestamp are likewise not observed here.
"""
from __future__ import annotations

from typing import Any

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, Fixture, fresh_identifier, parse_semver
from conftest import assert_details_vocabulary_values_safe, provision_pair

pytestmark = pytest.mark.condition("C-28")


_OBSERVED_BRANCH = "keyset_paging_1_9_0"


def _expected_branch_for_pre_1_9_0(pre_1_9_0: bool) -> str:
    return "pre_1_9_0" if pre_1_9_0 else _OBSERVED_BRANCH


def _pre_1_9_0_reason(adapter: ConformanceAdapter, contract_version: str) -> str:
    return (
        f"{adapter.name} declares contract_version {contract_version!r} (< 1.9.0) -- keyset paging is a "
        "conditional 1.9.0 obligation (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-1, subordinate "
        "ruling 14); this branch is expected to fail (not merely skip) until this peer's own version-flip "
        "commit lands, per the contract's own 1.9.0-only retroactivity rule."
    )


def _capability_status(adapter: ConformanceAdapter, name: str) -> str:
    return adapter.capability_document().get("capabilities", {}).get(name, {}).get("status", "unavailable")


def _cross_check_observed_branch(adapter: ConformanceAdapter, pre_1_9_0: bool, contract_version: str) -> None:
    """Work order §1.5/design D-4's own non-vacuity paragraph: done ONLY
    in the `>= 1.9.0` branch -- see this module's own docstring for why an
    unconditional check here would make a genuine strict XPASS
    structurally impossible."""
    if pre_1_9_0:
        return
    observed_branch = _OBSERVED_BRANCH
    expected_branch = _expected_branch_for_pre_1_9_0(pre_1_9_0)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: contract_version {contract_version!r} implies branch {expected_branch!r}, but the "
        f"full body completed without any refusal -- observed {observed_branch!r} (an early implementation "
        "ahead of this peer's own version-flip commit, D-1(7))"
    )


# ---------------------------------------------------------------------------
# T -- test_c28_paged_traversal_is_the_unpaged_sequence (design D-4 (i)+(vi))
# ---------------------------------------------------------------------------

_ORDER_BY_VARIANTS = (
    "plain",
    "null_valued_field",
    "null_valued_field_desc",
    "mixed_direction",
    "field_outside_select",
    "select_every_declared_field",
    "tied_order_key",
)


@pytest.mark.parametrize("variant", _ORDER_BY_VARIANTS)
def test_c28_paged_traversal_is_the_unpaged_sequence(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest, variant: str,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28t")
    entity = fresh_identifier("c28t")
    declared_fields = ["bucket", "rank", "tag"]
    iso.create_entity(developer, entity, {"bucket": "text", "rank": "integer", "tag": "text"})

    if variant == "tied_order_key":
        # 他の変種の (bucket, rank) は全行 distinct なので tie-break `id`
        # に一度も届かない。この変種だけ、order_by 1 項 (bucket) の値を 2
        # 値だけに絞り (3 行が "x"、2 行が "y")、tie 群がページ境界
        # (page_size=2 の走査) を必ずまたぐ seed にする -- tie-break の
        # 方向を誤ると重複・欠落が現れる。
        rows: list[dict[str, Any]] = [
            {"bucket": "x", "rank": 1, "tag": "x"},
            {"bucket": "x", "rank": 2, "tag": "x"},
            {"bucket": "x", "rank": 3, "tag": "x"},
            {"bucket": "y", "rank": 4, "tag": "y"},
            {"bucket": "y", "rank": 5, "tag": "y"},
        ]
    else:
        # bucket/rank pairs are all distinct, so (bucket, rank) alone already
        # totally orders these 5 rows -- every variant below stays within the
        # isolated surface's own small query_complexity bound (len(where) +
        # len(select) + order_by_count <= 5, conformance_adapter_r2db.py's own
        # ISOLATED_APPLICATION_LIMITS) without needing a 3rd ordering term.
        rows = [
            {"bucket": "a", "rank": 3, "tag": "x"},
            {"bucket": "a", "rank": 1},  # tag omitted -- NULL
            {"bucket": "b", "rank": 2, "tag": "y"},
            {"bucket": "b", "rank": 4},  # tag omitted -- NULL
            {"bucket": "c", "rank": 5, "tag": "x"},
        ]
    for row in rows:
        iso.insert(runtime, entity, row)

    if variant == "plain":
        select = ["bucket", "rank"]
        order_by = [("bucket", "asc"), ("rank", "asc")]
    elif variant == "null_valued_field":
        select = ["bucket", "rank", "tag"]
        order_by = [("tag", "asc"), ("bucket", "asc")]
    elif variant == "null_valued_field_desc":
        # supervisor ruling (code-review 指摘 2): `null_valued_field` above
        # only exercises the ASC null branch (NULLS LAST) -- the DESC null
        # branch (NULLS FIRST, `postgres_sql.py`'s own `_NULLS_SQL["desc"]`/
        # `backend_sqlite.py`'s own `_NULLS_TOKENS["desc"]`) had no
        # observing node at all. With this seed, `tag desc` places the two
        # NULL-tag rows first (tie-broken by `bucket asc`: "a" then "b"),
        # so the `page_size=2` traversal's first-page cursor encodes a NULL
        # ordering value for `tag` -- the DESC-branch equivalent of `null_
        # valued_field`'s own ASC-branch cursor.
        select = ["bucket", "rank", "tag"]
        order_by = [("tag", "desc"), ("bucket", "asc")]
    elif variant == "mixed_direction":
        select = ["bucket", "rank"]
        order_by = [("bucket", "asc"), ("rank", "desc")]
    elif variant == "field_outside_select":
        select = ["bucket"]
        order_by = [("rank", "asc")]
    elif variant == "tied_order_key":
        select = ["bucket", "rank"]
        order_by = [("bucket", "asc")]
    else:
        assert variant == "select_every_declared_field"
        select = list(declared_fields)
        order_by = [("bucket", "asc"), ("rank", "asc")]

    unpaged_items, unpaged_next = iso.query_page(runtime, entity, select, order_by=order_by, page_size=len(rows))
    assert unpaged_next is None, f"{adapter.name}: a page carrying every row still reports a non-null next_page"
    assert len(unpaged_items) == len(rows), (
        f"{adapter.name}: unpaged read returned {len(unpaged_items)} items, expected {len(rows)}"
    )

    expected_keys = set(select)
    for item in unpaged_items:
        assert set(item.keys()) == expected_keys, (
            f"{adapter.name}: item keys {sorted(item.keys())} != select {sorted(expected_keys)} -- {item!r}"
        )

    paged_items: list[dict] = []
    cursor = None
    pages = 0
    while True:
        page_items, next_page = iso.query_page(runtime, entity, select, order_by=order_by, page_size=2, cursor=cursor)
        pages += 1
        paged_items.extend(page_items)
        if next_page is None:
            break
        cursor = next_page
        assert pages <= len(rows) + 2, f"{adapter.name}: traversal did not terminate after {pages} pages"
    # 空振り禁止 (design D-4): 少なくとも 2 ページに分かれたこと。
    assert pages >= 2, f"{adapter.name}: traversal spanned only {pages} page(s) -- non-vacuity requires >= 2"
    assert paged_items == unpaged_items, (
        f"{adapter.name}: the pages of a traversal, concatenated, are not the same sequence -- each row "
        f"exactly once -- as one unpaged read of the same request: paged={paged_items!r}, unpaged={unpaged_items!r}"
    )

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# I -- test_c28_concurrent_insert_discriminates_keyset_from_offset (D-4 (ii))
# ---------------------------------------------------------------------------

def test_c28_concurrent_insert_discriminates_keyset_from_offset(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        # design D-4 (vii): this is the ONE node whose version gate is
        # `strict=True` -- an offset implementation (or a 1.8.0 peer with
        # no cursor at all) is EXPECTED to fail this node for real, so an
        # early XPASS here means the peer's own real behavior has already
        # outrun its own 1.8.0 declaration (D-1(7)).
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=True))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28i")
    entity = fresh_identifier("c28i")
    iso.create_entity(developer, entity, {"rank": "integer"})
    for value in (10, 20, 30, 40):
        iso.insert(runtime, entity, {"rank": value})

    select = ["rank"]
    order_by = [("rank", "asc")]
    page1_items, cursor = iso.query_page(runtime, entity, select, order_by=order_by, page_size=2)
    assert len(page1_items) == 2, f"{adapter.name}: first page carried {len(page1_items)} items, expected 2"
    assert cursor is not None, f"{adapter.name}: a 2-of-4 page reported a null next_page"

    # (ii) の挿入 2 行: order key (rank) はこの entity の中で一意 (監督の
    # 追加 2026-09-24) -- 既存行との tie-break 依存を避ける。
    iso.insert(runtime, entity, {"rank": 15})  # cursor 位置 (rank=20 の直後) より前
    iso.insert(runtime, entity, {"rank": 35})  # cursor 位置より後 -- 出現は記録のみ
    # 空振り禁止: 挿入 2 件が実際に入ったこと。
    assert iso.count(runtime, entity) == 6, f"{adapter.name}: expected 6 rows after 2 concurrent inserts"

    remaining_items: list[dict] = []
    while cursor is not None:
        # 監督裁定 (コードレビュー差し戻し 1): 1 ページ目と同じ page_size=2
        # で読む -- page_size を変えると B node 側の性質 (page.size の変更
        # でも cursor は有効) まで同時に動かしてしまい、offset 実装が
        # 大きな page_size のせいで shape (size) の拒否に先に落ちて、この
        # node が検出したい重複 (下の assert not repeats) まで届かないこと
        # がある。
        items, cursor = iso.query_page(runtime, entity, select, order_by=order_by, page_size=2, cursor=cursor)
        remaining_items.extend(items)

    remaining_ranks = [item["rank"] for item in remaining_items]
    assert 15 not in remaining_ranks, (
        f"{adapter.name}: a row inserted BEFORE the cursor's own position (rank=15 precedes rank=20) was "
        f"returned by the continuation -- {remaining_ranks!r}"
    )
    already_returned = {item["rank"] for item in page1_items}
    repeats = [r for r in remaining_ranks if r in already_returned]
    assert not repeats, (
        f"{adapter.name}: row(s) already returned on page 1 reappeared in the continuation -- {repeats!r} "
        "(the offset-shape symptom this node discriminates: a row inserted before the cursor's position "
        "shifts a later OFFSET window)"
    )
    # 後に挿入した行 (rank=35) の出現は記録のみ、assert しない (design D-4
    # (ii), C-6 第 3 文: "once or not at all").
    _saw_row_inserted_after_cursor = 35 in remaining_ranks  # noqa: F841

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# B -- test_c28_cursor_binding (design D-4 (iii))
# ---------------------------------------------------------------------------

def test_c28_cursor_binding(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28b")
    entity = fresh_identifier("c28b")
    iso.create_entity(developer, entity, {"bucket": "text", "rank": "integer"})
    for bucket, rank in [("a", 1), ("a", 2), ("a", 3), ("b", 1)]:
        iso.insert(runtime, entity, {"bucket": bucket, "rank": rank})

    where = [("bucket", "eq", "a")]
    order_by = [("rank", "asc")]
    select = ["bucket", "rank"]
    _first_items, cursor = iso.query_page(runtime, entity, select, where=where, order_by=order_by, page_size=2)
    assert cursor is not None, f"{adapter.name}: a 2-of-3 filtered page reported a null next_page"

    # select が変わっても cursor は有効。監督裁定 (差し戻し 2): select
    # だけを変え、page_size は発行時と同じ 2 のまま (2 つの性質を同時に
    # 動かさない -- page.size の変更は下の脚で別に観測する)。
    changed_select_items, _next1 = iso.query_page(
        runtime, entity, ["rank"], where=where, order_by=order_by, page_size=2, cursor=cursor,
    )
    assert changed_select_items, f"{adapter.name}: a cursor was refused across a select change"
    assert all(set(item.keys()) == {"rank"} for item in changed_select_items)

    # page.size が変わっても cursor は有効。
    changed_size_items, _next2 = iso.query_page(
        runtime, entity, select, where=where, order_by=order_by, page_size=1, cursor=cursor,
    )
    assert changed_size_items, f"{adapter.name}: a cursor was refused across a page.size change"

    # v0.6 (依頼者裁定 Q-3 見直し 1 点): 同じ where 述語を並べ替えただけの
    # 要求でも cursor は有効。空振り禁止: 並べ替え前後は 2 述語以上かつ
    # 並びが異なること。
    where_2 = [("bucket", "eq", "a"), ("rank", "gt", 0)]
    where_2_reordered = list(reversed(where_2))
    assert len(where_2) >= 2 and where_2 != where_2_reordered
    _reordered_first, reordered_cursor = iso.query_page(
        runtime, entity, select, where=where_2, order_by=order_by, page_size=2,
    )
    assert reordered_cursor is not None
    reordered_continuation, _next3 = iso.query_page(
        runtime, entity, select, where=where_2_reordered, order_by=order_by, page_size=2, cursor=reordered_cursor,
    )
    assert reordered_continuation, (
        f"{adapter.name}: a cursor was refused when the SAME where predicates were only reordered -- "
        f"issued under {where_2!r}, presented under {where_2_reordered!r}"
    )

    # where を変えると拒否。
    with pytest.raises(ConformanceDenial) as ei_where:
        iso.query_page(runtime, entity, select, where=[("bucket", "eq", "b")], order_by=order_by, page_size=2, cursor=cursor)
    assert ei_where.value.code == "VALIDATION_FAILED", f"{adapter.name}: where change -> {ei_where.value.code!r}"
    assert ei_where.value.details.get("violated_declaration") == "request_schema", ei_where.value.details
    assert ei_where.value.details.get("field") == "page/cursor", ei_where.value.details

    # order_by を変えると拒否。
    with pytest.raises(ConformanceDenial) as ei_order:
        iso.query_page(runtime, entity, select, where=where, order_by=[("rank", "desc")], page_size=2, cursor=cursor)
    assert ei_order.value.code == "VALIDATION_FAILED", f"{adapter.name}: order_by change -> {ei_order.value.code!r}"
    assert ei_order.value.details.get("violated_declaration") == "request_schema", ei_order.value.details
    assert ei_order.value.details.get("field") == "page/cursor", ei_order.value.details

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# A -- test_c28_cross_application_cursor_is_refused (design D-4 (iv))
# ---------------------------------------------------------------------------

def test_c28_cross_application_cursor_is_refused(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    dev_a, run_a, app_a = provision_pair(iso, app_prefix="c28aa")
    dev_b, run_b, app_b = provision_pair(iso, app_prefix="c28ab")
    entity = fresh_identifier("c28a")
    iso.create_entity(dev_a, entity, {"bucket": "text"})
    iso.create_entity(dev_b, entity, {"bucket": "text"})
    for bucket in ("x", "y"):
        iso.insert(run_a, entity, {"bucket": bucket})
        iso.insert(run_b, entity, {"bucket": bucket})

    select = ["bucket"]
    order_by = [("bucket", "asc")]
    _items_a, cursor_a = iso.query_page(run_a, entity, select, order_by=order_by, page_size=1)
    assert cursor_a is not None

    with pytest.raises(ConformanceDenial) as ei_cross_app:
        iso.query_page(run_b, entity, select, order_by=order_by, page_size=1, cursor=cursor_a)
    assert ei_cross_app.value.code == "VALIDATION_FAILED", f"{adapter.name}: {ei_cross_app.value.code!r}"
    assert ei_cross_app.value.details.get("violated_declaration") == "request_schema", ei_cross_app.value.details
    assert ei_cross_app.value.details.get("field") == "page/cursor", ei_cross_app.value.details
    assert_details_vocabulary_values_safe(ei_cross_app.value.details, adapter_name=adapter.name)
    # SI-01: 他 Application の存在・活動を details から推測できない。
    for value in ei_cross_app.value.details.values():
        rendered = str(value)
        assert app_a not in rendered and app_b not in rendered, (
            f"{adapter.name}: a cross-application cursor refusal leaked an Application id -- "
            f"{ei_cross_app.value.details!r}"
        )

    # 別 entity (同一 Application) の cursor も拒否 -- 束縛は entity も含む。
    other_entity = fresh_identifier("c28a2")
    iso.create_entity(dev_a, other_entity, {"bucket": "text"})
    with pytest.raises(ConformanceDenial) as ei_cross_entity:
        iso.query_page(run_a, other_entity, select, order_by=order_by, page_size=1, cursor=cursor_a)
    assert ei_cross_entity.value.code == "VALIDATION_FAILED", f"{adapter.name}: {ei_cross_entity.value.code!r}"
    assert ei_cross_entity.value.details.get("violated_declaration") == "request_schema", ei_cross_entity.value.details
    assert ei_cross_entity.value.details.get("field") == "page/cursor", ei_cross_entity.value.details

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# R -- test_c28_cursor_refusal_details (design D-4 (iii))
# ---------------------------------------------------------------------------

def test_c28_cursor_refusal_details(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    """An undecodable string, a cursor issued under a different
    Application, a cursor issued against a different entity, and a cursor
    whose `where` or `order_by` no longer matches the request presenting
    it, all answer with the SAME 2-key denial (design D-4's own node
    table).

    監督裁定 (コードレビュー差し戻し 3, 2026-09-25): この node は個数・型
    不一致の脚を持たない -- cursor は契約上 opaque であり、conformance
    suite は改変 token を作れない (`order_by` を変える脚は束縛違いの拒否
    と観測上区別がつかず、個数・型不一致だけを独立に駆動する黒箱の手段が
    無い)。個数・型検査の証拠は peer 固有の単体テスト (改変 token を知っ
    てよい層) に置く -- WP-5 (r2db) と WP-4 (MitateDB) で足す。この限界は
    `conformance-tests/CONDITIONS.md` の C-28 行 Status に開示する。"""
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28r")
    entity = fresh_identifier("c28r")
    iso.create_entity(developer, entity, {"bucket": "text", "rank": "integer"})
    for bucket, rank in [("a", 1), ("a", 2), ("b", 1)]:
        iso.insert(runtime, entity, {"bucket": bucket, "rank": rank})

    select = ["bucket", "rank"]
    where = [("bucket", "eq", "a")]
    order_by = [("rank", "asc")]

    denials: dict[str, ConformanceDenial] = {}

    with pytest.raises(ConformanceDenial) as ei_garbage:
        iso.query_page(runtime, entity, select, where=where, order_by=order_by, page_size=1, cursor="not-a-real-cursor-token")
    denials["undecodable"] = ei_garbage.value

    _items, cursor = iso.query_page(runtime, entity, select, where=where, order_by=order_by, page_size=1)
    assert cursor is not None, f"{adapter.name}: a 1-of-2 filtered page reported a null next_page"

    # 別 Application (同名 entity) で発行した cursor。
    other_developer, other_runtime, _other_app = provision_pair(iso, app_prefix="c28r2")
    iso.create_entity(other_developer, entity, {"bucket": "text", "rank": "integer"})
    iso.insert(other_runtime, entity, {"bucket": "a", "rank": 1})
    iso.insert(other_runtime, entity, {"bucket": "a", "rank": 2})
    _other_app_items, other_app_cursor = iso.query_page(
        other_runtime, entity, select, where=where, order_by=order_by, page_size=1,
    )
    assert other_app_cursor is not None
    with pytest.raises(ConformanceDenial) as ei_cross_app:
        iso.query_page(runtime, entity, select, where=where, order_by=order_by, page_size=1, cursor=other_app_cursor)
    denials["cross_application"] = ei_cross_app.value

    # 同一 Application、別 entity で発行した cursor。
    other_entity = fresh_identifier("c28r3")
    iso.create_entity(developer, other_entity, {"bucket": "text", "rank": "integer"})
    iso.insert(runtime, other_entity, {"bucket": "a", "rank": 1})
    iso.insert(runtime, other_entity, {"bucket": "a", "rank": 2})
    _other_entity_items, other_entity_cursor = iso.query_page(
        runtime, other_entity, select, where=where, order_by=order_by, page_size=1,
    )
    assert other_entity_cursor is not None
    with pytest.raises(ConformanceDenial) as ei_cross_entity:
        iso.query_page(runtime, entity, select, where=where, order_by=order_by, page_size=1, cursor=other_entity_cursor)
    denials["cross_entity"] = ei_cross_entity.value

    # where 束縛違い (同じ cursor、別 where)。
    with pytest.raises(ConformanceDenial) as ei_where:
        iso.query_page(runtime, entity, select, where=[("bucket", "eq", "b")], order_by=order_by, page_size=1, cursor=cursor)
    denials["where_changed"] = ei_where.value

    # order_by 束縛違い (同じ cursor、別 order_by)。
    with pytest.raises(ConformanceDenial) as ei_order:
        iso.query_page(runtime, entity, select, where=where, order_by=[("rank", "desc")], page_size=1, cursor=cursor)
    denials["order_by_changed"] = ei_order.value

    assert len(denials) == 5, f"{adapter.name}: fewer than 5 distinct refusal causes were observed -- {sorted(denials)}"
    reference = denials["undecodable"]
    assert reference.code == "VALIDATION_FAILED", f"{adapter.name}: undecodable -> {reference.code!r}"
    assert reference.details.get("violated_declaration") == "request_schema", reference.details
    assert reference.details.get("field") == "page/cursor", reference.details
    assert_details_vocabulary_values_safe(reference.details, adapter_name=adapter.name)
    for name, denial in denials.items():
        assert denial.code == reference.code, f"{adapter.name}: {name} -> {denial.code!r} != {reference.code!r}"
        assert denial.details.get("violated_declaration") == reference.details.get("violated_declaration"), (
            f"{adapter.name}: {name} -> {denial.details!r}"
        )
        assert denial.details.get("field") == reference.details.get("field"), f"{adapter.name}: {name} -> {denial.details!r}"
        assert_details_vocabulary_values_safe(denial.details, adapter_name=adapter.name)

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# S -- test_c28_cursor_is_stateless (design D-4 (v))
# ---------------------------------------------------------------------------

def test_c28_cursor_is_stateless(
    adapter: ConformanceAdapter, fx: Fixture, request: pytest.FixtureRequest,
) -> None:
    """Work order §3 task 3 / monitor note: this node deliberately does
    NOT use `isolated` -- the second session must be a genuinely different
    credential of the SAME Application as the one that issued the cursor,
    authenticated on the SHARED, session-scoped adapter (`fx`), never an
    `isolated_application_surface()` (a "FRESH, throwaway data-plane
    instance", adapter.py:1641 -- a second credential issued there is
    still the SAME isolated instance's own state, not an independent
    re-authentication path)."""
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    entity = fresh_identifier("c28s")
    adapter.create_entity(fx.developer_a, entity, {"bucket": "text"})
    for bucket in ("a", "b", "c"):
        adapter.insert(fx.runtime_a, entity, {"bucket": bucket})

    select = ["bucket"]
    order_by = [("bucket", "asc")]
    first_items, cursor = adapter.query_page(fx.runtime_a, entity, select, order_by=order_by, page_size=2)
    assert cursor is not None, f"{adapter.name}: a 2-of-3 page reported a null next_page"

    second_handle = adapter.issue_credential(fx.app_a, "runtime")
    second_session = adapter.authenticate(second_handle)
    assert second_session is not fx.runtime_a, f"{adapter.name}: the second credential authenticated to the SAME session object"

    # 監督裁定 (差し戻し 2): page_size は発行時と同じ 2 のまま -- 変わるのは
    # session/credential だけ。
    remaining_items, next_page = adapter.query_page(second_session, entity, select, order_by=order_by, page_size=2, cursor=cursor)
    assert remaining_items, f"{adapter.name}: a cursor from one session was refused in a second session of the same Application"
    assert next_page is None
    assert [i["bucket"] for i in first_items] + [i["bucket"] for i in remaining_items] == ["a", "b", "c"]

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# D -- test_c28_cursor_is_deterministic (design D-4 (viii))
# ---------------------------------------------------------------------------

def test_c28_cursor_is_deterministic(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28d")
    entity = fresh_identifier("c28d")
    iso.create_entity(developer, entity, {"bucket": "text"})
    for bucket in ("a", "b", "c"):
        iso.insert(runtime, entity, {"bucket": bucket})

    select = ["bucket"]
    order_by = [("bucket", "asc")]
    items1, next1 = iso.query_page(runtime, entity, select, order_by=order_by, page_size=2)
    items2, next2 = iso.query_page(runtime, entity, select, order_by=order_by, page_size=2)
    assert next1 is not None and next2 is not None, f"{adapter.name}: a 2-of-3 page reported a null next_page"
    assert next1 == next2, (
        f"{adapter.name}: two identical requests decided against unchanged stored content returned "
        f"different next_page values -- {next1!r} != {next2!r}"
    )
    assert items1 == items2

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# DP -- test_c28_default_page_is_the_largest_page (design D-4, D-1(2a))
# ---------------------------------------------------------------------------

def test_c28_default_page_is_the_largest_page(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28dp")
    entity = fresh_identifier("c28dp")
    iso.create_entity(developer, entity, {"bucket": "text"})
    select = ["bucket"]
    order_by = [("bucket", "asc")]

    # design D-4 node table / §6.2 (C-24 例外): this node ALONE carries
    # `budget` -- driving the default-page property against a small entity
    # instead of the deployment's own, much larger `limits.result_items`.
    if _capability_status(iso, "request_budget") != "unavailable":
        b = 3
        for i in range(b + 1):
            iso.insert(runtime, entity, {"bucket": f"row{i}"})
        first_items, cursor = iso.query_page(runtime, entity, select, order_by=order_by, budget={"result_items": b})
        # 空振り禁止: `budget` の経路が実際に走ったこと (items が b 件ちょうど)。
        assert len(first_items) == b, (
            f"{adapter.name}: default page under budget.result_items={b} carried {len(first_items)} items, expected {b}"
        )
        assert cursor is not None
        remaining_items, next_page = iso.query_page(runtime, entity, select, order_by=order_by, cursor=cursor, budget={"result_items": b})
        assert len(remaining_items) == 1
        assert next_page is None
    else:
        declared_result_items = iso.capability_document().get("limits", {}).get("result_items")
        assert isinstance(declared_result_items, int) and declared_result_items > 0, (
            f"{adapter.name}: capability_document()['limits']['result_items'] is not a positive int"
        )
        for i in range(declared_result_items + 1):
            iso.insert(runtime, entity, {"bucket": f"row{i}"})
        first_items, cursor = iso.query_page(runtime, entity, select, order_by=order_by)
        assert len(first_items) == declared_result_items
        assert cursor is not None
        remaining_items, next_page = iso.query_page(runtime, entity, select, order_by=order_by, cursor=cursor)
        assert len(remaining_items) == 1
        assert next_page is None

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)


# ---------------------------------------------------------------------------
# PS -- test_c28_page_size_outside_schema_is_refused_at_page_size (D-3.8/D-2b.2)
# ---------------------------------------------------------------------------

def test_c28_page_size_outside_schema_is_refused_at_page_size(
    adapter: ConformanceAdapter, isolated: ConformanceAdapter, request: pytest.FixtureRequest,
) -> None:
    iso = isolated
    contract_version = adapter.capability_document()["contract_version"]
    pre_1_9_0 = parse_semver(contract_version) < (1, 9, 0)
    if pre_1_9_0:
        request.node.add_marker(pytest.mark.xfail(reason=_pre_1_9_0_reason(adapter, contract_version), strict=False))

    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28ps")
    entity = fresh_identifier("c28ps")
    iso.create_entity(developer, entity, {"bucket": "text"})
    iso.insert(runtime, entity, {"bucket": "a"})

    select = ["bucket"]
    order_by = [("bucket", "asc")]

    for bad_size in (0, 1001):
        with pytest.raises(ConformanceDenial) as ei:
            iso.query_page(runtime, entity, select, order_by=order_by, page_size=bad_size)
        assert ei.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: page.size={bad_size} -> {ei.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei.value.details.get("violated_declaration") == "request_schema", ei.value.details
        assert ei.value.details.get("field") == "page/size", ei.value.details
        assert_details_vocabulary_values_safe(ei.value.details, adapter_name=adapter.name)

    _cross_check_observed_branch(adapter, pre_1_9_0, contract_version)
