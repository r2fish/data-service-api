"""Contract 1.7.0 R-6 (request-scoped `budget`) -- design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-6, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2d, ruling集約
{scratchpad}/rulings-r5-r6.md B-1..B-6.

Peer-local coverage underneath `conformance-tests/test_c24_request_
budget.py`'s own cross-peer test (this file never imports or edits
anything under `conformance-tests/`): exercises `limits.narrow_limits_
by_budget` directly (the single narrowing point, B-2/B-5) and
`DataService` (query/mutate/schema) for the WP-2d completion conditions
(§2 WP-2d 完了条件 1-7), matching `test_dry_run_and_plan.py`'s/`test_
idempotency_records.py`'s established convention for this phase's
peer-local test files.
"""
from __future__ import annotations

import pytest

from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits, narrow_limits_by_budget

from test_application_audit import build_service, developer_context, runtime_context

LIMITS = ResourceLimits()


# ===========================================================================
# Section 1: `narrow_limits_by_budget` itself (`limits.py`) -- the single
# narrowing point (B-2/B-5).
# ===========================================================================


def test_budget_none_returns_the_deployed_limits_object_unchanged() -> None:
    """P-8-style laziness: an ordinary (unbudgeted) request pays no cost."""
    assert narrow_limits_by_budget(LIMITS, None, "mutate") is LIMITS


def test_narrow_by_batch_items_narrows_only_that_class() -> None:
    effective = narrow_limits_by_budget(LIMITS, {"batch_items": 2}, "mutate")
    assert effective.batch_items == 2
    assert effective.execution_ms == LIMITS.execution_ms
    assert effective.result_items == LIMITS.result_items


def test_budget_above_deployed_value_is_validation_failed() -> None:
    """完了条件 3: 配備値を上回る budget が VALIDATION_FAILED +
    violated_declaration = budget になる -- 黙って clamp しない。"""
    with pytest.raises(FoundationError) as exc:
        narrow_limits_by_budget(LIMITS, {"batch_items": LIMITS.batch_items + 1}, "mutate")
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}


def test_inapplicable_class_is_rejected_not_ignored() -> None:
    """完了条件 4: 適用外 class (query に batch_items、mutation に
    result_items) が VALIDATION_FAILED + field = budget/<class> になり、
    無視されない。"""
    with pytest.raises(FoundationError) as exc:
        narrow_limits_by_budget(LIMITS, {"batch_items": 1}, "query")
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}

    with pytest.raises(FoundationError) as exc2:
        narrow_limits_by_budget(LIMITS, {"result_items": 1}, "mutate")
    assert exc2.value.code == "VALIDATION_FAILED"
    assert exc2.value.details == {"violated_declaration": "budget", "field": "budget/result_items"}


def test_schema_endpoint_only_accepts_execution_ms() -> None:
    with pytest.raises(FoundationError) as exc:
        narrow_limits_by_budget(LIMITS, {"batch_items": 1}, "schema")
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}
    effective = narrow_limits_by_budget(LIMITS, {"execution_ms": 1000}, "schema")
    assert effective.execution_ms == 1000


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, "2", True, None])
def test_non_positive_integer_budget_values_are_rejected(bad_value) -> None:
    with pytest.raises(FoundationError) as exc:
        narrow_limits_by_budget(LIMITS, {"batch_items": bad_value}, "mutate")
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}


def test_narrowing_is_min_never_max() -> None:
    """変異 1 の裏取り: `min` を `max` にする変異が赤くなること -- 実効値
    は常に配備値以下である。"""
    effective = narrow_limits_by_budget(LIMITS, {"batch_items": 1}, "mutate")
    assert effective.batch_items == min(LIMITS.batch_items, 1) == 1
    assert effective.batch_items <= LIMITS.batch_items


# ===========================================================================
# Section 2: `DataService` -- WP-2d 完了条件 1/2/6/7 (`mutate_result`/
# `_query_outcome`/`schema`, driven end to end).
# ===========================================================================


def test_condition_1_batch_items_budget_narrows_exactly_at_the_requested_position() -> None:
    """完了条件 1 (設計 §6.2 C-24 (1) の確定レシピ): budget.batch_items = 2
    で 2 件の operation を含む要求は成功、3 件の要求は
    LIMIT_EXCEEDED(batch_items)。"""
    service, _control = build_service()
    context = runtime_context(service)
    two_ops = [{"operation": "insert", "values": {"body": "a"}}, {"operation": "insert", "values": {"body": "b"}}]
    result = service.mutate_result(context, "notes", two_ops, budget={"batch_items": 2})
    assert result.committed is True
    assert result.affected == 2

    three_ops = [{"operation": "insert", "values": {"body": "a"}}, {"operation": "insert", "values": {"body": "b"}}, {"operation": "insert", "values": {"body": "c"}}]
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(context, "notes", three_ops, budget={"batch_items": 2})
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert exc.value.details.get("limit_class") == "batch_items"


def test_condition_2_omitted_budget_is_a_positive_control_up_to_the_deployed_bound() -> None:
    """完了条件 2: budget を省略した同じ要求は配備値まで通る (正の対照)。"""
    tight_limits = ResourceLimits(batch_items=3)
    service, _control = build_service(limits=tight_limits)
    context = runtime_context(service)
    three_ops = [{"operation": "insert", "values": {"body": "a"}}, {"operation": "insert", "values": {"body": "b"}}, {"operation": "insert", "values": {"body": "c"}}]
    result = service.mutate_result(context, "notes", three_ops)
    assert result.affected == 3


def test_condition_5_limit_exceeded_details_are_not_budget_specific() -> None:
    """完了条件 5: 超過の LIMIT_EXCEEDED の details.limit_class が当該
    class であり、budget 専用の値ではない -- 配備値超過 (budget 無し) と
    同一の details 形になる。"""
    service, _control = build_service()
    context = runtime_context(service)
    three_ops = [{"operation": "insert", "values": {"body": "a"}}, {"operation": "insert", "values": {"body": "b"}}, {"operation": "insert", "values": {"body": "c"}}]

    with pytest.raises(FoundationError) as via_budget:
        service.mutate_result(context, "notes", three_ops, budget={"batch_items": 2})

    deployed_limits = ResourceLimits(batch_items=2)
    service2, _control2 = build_service(limits=deployed_limits)
    context2 = runtime_context(service2)
    with pytest.raises(FoundationError) as via_deployed:
        service2.mutate_result(context2, "notes", list(three_ops))

    assert via_budget.value.code == via_deployed.value.code == "LIMIT_EXCEEDED"
    assert via_budget.value.details == via_deployed.value.details


def test_condition_6_budget_validity_is_checked_before_destructive_confirmation() -> None:
    """完了条件 6: budget の妥当性検査が検証段で行われる -- 配備値超過の
    budget を持つ未確認の破壊操作 (`delete`, confirmation 無し) が
    VALIDATION_FAILED を返す (DESTRUCTIVE_CONFIRMATION_REQUIRED ではな
    い)。"""
    service, _control = build_service()
    context = runtime_context(service)
    unconfirmed_delete = [{"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}]}]
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(context, "notes", unconfirmed_delete, budget={"batch_items": LIMITS.batch_items + 1})
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}


def test_condition_7_capability_request_budget_is_enabled_and_gate_is_removed() -> None:
    """完了条件 7: capability `request_budget` が enabled であり、
    provisional gate は撤去済みである (budget を伴う要求が
    CAPABILITY_UNSUPPORTED で拒否されない)。"""
    service, _control = build_service()
    context = runtime_context(service)
    document = service.capabilities(context)
    assert document["capabilities"]["request_budget"] == {"status": "enabled"}

    result = service.mutate_result(context, "notes", [{"operation": "insert", "values": {"body": "x"}}], budget={"batch_items": 1})
    assert result.committed is True


def test_query_budget_narrows_result_items_and_execution_ms_only() -> None:
    """B-6 実測: query 経路は result_items/execution_ms のみ適用外の
    batch_items は VALIDATION_FAILED。"""
    service, _control = build_service()
    context = runtime_context(service)
    with pytest.raises(FoundationError) as exc:
        service.query_page(context, "notes", select=["id", "body"], budget={"batch_items": 1})
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}

    page = service.query_page(context, "notes", select=["id", "body"], budget={"result_items": 1000})
    assert isinstance(page.items, list)


def test_b6_result_items_is_driven_by_budget_alone_on_the_query_path() -> None:
    """B-6 実測: r2db の `result_items` 検査は「返した(=一致した)行数」
    (`min(len(rows), page_size)`, `structured.py`) を見る -- 要求された
    `limit`/`page_size` そのものではない (これは D-6 開示が MitateDB 側の
    非対称として書く形の裏返しである)。したがって budget だけで N/N+1 を
    挟むには一致行数が page_size 以上必要 -- 4 行の entity に対して
    budget.result_items = 2、page_size = 2 は成功、page_size = 3 は
    LIMIT_EXCEEDED(result_items) になる (どちらの page_size でも一致行数
    は 4 で十分あるので、min() は常に page_size 側で決まる)。"""
    service, _control = build_service()
    context = runtime_context(service)
    for label in ("b", "c", "d"):
        service.mutate_result(context, "notes", [{"operation": "insert", "values": {"body": label}}])
    ok = service.query_page(context, "notes", select=["id"], page_size=2, budget={"result_items": 2})
    assert isinstance(ok.items, list)
    with pytest.raises(FoundationError) as exc:
        service.query_page(context, "notes", select=["id"], page_size=3, budget={"result_items": 2})
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert exc.value.details.get("limit_class") == "result_items"


def test_schema_operation_budget_narrows_execution_ms_and_is_validated() -> None:
    service, _control = build_service()
    context = developer_context(service)
    with pytest.raises(FoundationError) as exc:
        service.schema(context, {"operation": "create_entity", "entity": "widgets", "fields": ["label"], "budget": {"batch_items": 1}})
    assert exc.value.details == {"violated_declaration": "budget", "field": "budget/batch_items"}

    outcome = service.schema(context, {"operation": "create_entity", "entity": "widgets2", "fields": ["label"], "budget": {"execution_ms": 1000}})
    assert outcome.committed is True
