"""C-28 -- a client composing only the operations `common_baseline`
names completes one whole agent turn against every conformant peer,
reading no capability status at all, with no step branching on a
declaration: a `CAPABILITY_UNSUPPORTED` anywhere in the turn is a failure
of this row (SI-05, SI-09, SI-10, SI-11, SI-14).

design: docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-2/D-3/D-6, §7 (the
段の表), §7.1 (port v1.16 開示事項), §8.1 (SI 列), §11 (honest scope),
registered in `conformance-tests/CONDITIONS.md`. Work order: docs/work-
orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md WP-2. Every test here
carries `@pytest.mark.condition("C-28")` via the module-level
`pytestmark`.

**ONE test function, ONE scenario, 12 steps in order, no declaration
branch** (design X-2): (1) read capabilities/contract_version, (2) create
an entity carrying an `enum` and a `nullable: false` field under a
developer credential, (3) read the catalog under a runtime credential,
(4) build an `insert` from the catalog alone, carrying a value OUTSIDE the
declared enum, and receive `VALIDATION_FAILED`/`violated_declaration:
enum` naming the exact request-body position, (5) repair THAT SAME
request from the diagnosis and the catalog alone, (6) dry-run it carrying
the SAME `idempotency_key` step (7) will send for real, (7) send the
repaired request for real under that key while presenting step (6)'s own
`plan`, (8) resend the identical key/body and observe the FIRST
execution's own `request_id` with no second row, (9) query with each
baseline operator under `order_by`, a `page.size` and a `budget.
result_items` chained `R <= page.size <= budget.result_items <=
limits.result_items` (read from THIS isolated instance's own capability
document, never a literal -- design §7 段 (9), v0.3), (10) update by
predicate, (11) delete by predicate under declare-and-echo, (12) read the
resulting state back.

**段 (1) の版 assert は WP-3 で追加された** (design §7 段 (1), work order
WP-3 完了条件 6): both peers now declare 1.9.0 or higher (WP-3 flips both
`contract_version` declarations in the same commit as the served
`operation_catalog` behavior); step (1) asserts `parse_semver(
contract_version) >= (1, 9, 0)`, never `operations` non-emptiness (design
§7 段 (1)). **`page.cursor`/`next_page` は baseline の外** (design
D-6) -- this row never inspects `next_page`.

**port v1.16**: `attempt_filter_with_result` (`conformance-tests/
adapter.py`), used by 段 (9) alone.
"""
from __future__ import annotations

import pytest

import json

from adapter import (
    VALID_CONFIRMATION,
    ConformanceAdapter,
    ConformanceDenial,
    assert_no_payload_echo,
    fresh_identifier,
    load_contract,
    native_cause_of,
    parse_semver,
)
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-28")

# code review 2026-09-24 (WP-2 差し戻し R7): read the baseline operator set
# from the contract itself rather than a literal 7-name tuple.
# `common_baseline.operations`'s 5th item names the INCLUDED operators only
# inside prose ("eq, ne, lt, lte, gt, gte and in"), not as its own JSON
# array, so the included set is derived instead as `structured_operations.
# allowed_query_operators` (the full 10-operator vocabulary, itself a real
# JSON array) MINUS the 3 operators `common_baseline.outside` names by name
# ("the contains, matches and is_null operators") -- only that 3-name
# EXCLUSION remains a literal, matching `outside`'s own words verbatim.
_OUTSIDE_BASELINE_OPERATORS = ("contains", "matches", "is_null")
_BASELINE_OPERATORS = tuple(
    op for op in load_contract()["structured_operations"]["allowed_query_operators"]
    if op not in _OUTSIDE_BASELINE_OPERATORS
)

# code review 2026-09-24 (R7): `common_baseline.capabilities` read verbatim
# from the contract, not a literal copy -- 段 (1)'s own non-`unavailable`
# check.
_BASELINE_CAPABILITIES = tuple(load_contract()["common_baseline"]["capabilities"])


def test_c28_baseline_turn(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated

    # ------------------------------------------------------------------
    # 段 (1): capabilities を読み、契約版を読む。
    # ------------------------------------------------------------------
    capdoc = iso.capability_document()
    assert capdoc.get("contract_version"), f"{adapter.name}: C-28 段(1): capability_document carries no contract_version"
    # Phase 11 WP-3 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §7
    # 段 (1), work order docs/work-orders/
    # WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md WP-3 完了条件 6): the
    # version assert WP-2's own module docstring deferred -- 1.9.0's own
    # `common_baseline` obligation (a) is what makes every later step in
    # this scenario version-gated rather than capability-gated at all.
    # `operations` non-emptiness is deliberately NOT asserted here (design
    # §7 段 (1)) -- that is read once, later, from `common_baseline.
    # operations` itself (module-level constants above), not from this
    # capability document.
    assert parse_semver(capdoc["contract_version"]) >= (1, 9, 0), (
        f"{adapter.name}: C-28 段(1): contract_version {capdoc['contract_version']!r} "
        "is below the 1.9.0 common_baseline obligation this row exercises"
    )
    capabilities = capdoc.get("capabilities", {})
    for name in _BASELINE_CAPABILITIES:
        status = capabilities.get(name, {}).get("status", "unavailable")
        assert status != "unavailable", (
            f"{adapter.name}: C-28 段(1): baseline capability {name!r} is declared unavailable -- a "
            f"CAPABILITY_UNSUPPORTED anywhere in this turn is a failure of this row (capabilities[{name!r}]="
            f"{capabilities.get(name)!r})"
        )

    # ------------------------------------------------------------------
    # 段 (2): developer で entity を作る (enum と nullable: false field を含む)。
    # ------------------------------------------------------------------
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c28")
    entity = fresh_identifier("c28e")
    enum_field, nonnull_field, sort_field = "status", "req", "seq"
    create_result = iso.schema_operation_with_result(
        developer, entity, "create_entity",
        fields=[enum_field, nonnull_field, sort_field],
        field_types={enum_field: "string", nonnull_field: "string", sort_field: "integer"},
        field_constraints={enum_field: {"enum": ["a", "b"]}, nonnull_field: {"nullable": False}},
    )
    assert create_result.get("request_id"), (
        f"{adapter.name}: C-28 段(2): a successful create_entity result carries no request_id -- "
        f"{create_result!r}"
    )

    # ------------------------------------------------------------------
    # 段 (3): runtime で catalog を読む。
    # ------------------------------------------------------------------
    catalog = iso.catalog_document(runtime)
    row = {r["entity"]: r for r in catalog["entities"]}[entity]
    declared_enum = (row.get("field_constraints") or {}).get(enum_field, {}).get("enum")
    assert declared_enum == ["a", "b"], (
        f"{adapter.name}: C-28 段(3): catalog does not report {entity!r}.{enum_field}'s own declared enum "
        f"(created in 段(2)) -- {row.get('field_constraints')!r}"
    )

    # ------------------------------------------------------------------
    # 段 (4): catalog だけから要求を組み立て、enum 外の値で insert を送る。
    # 1 度組み立てた要求体 (`bad_values`) を、この段でも段(5)でも使う
    # (code review 2026-09-24 R2: 別物の dict を 2 つ組まない)。
    # ------------------------------------------------------------------
    marker = fresh_identifier("c28row")
    rejected_value = "outside-the-catalog-enum"
    bad_values = {enum_field: rejected_value, nonnull_field: marker, sort_field: 1}
    with pytest.raises(ConformanceDenial) as ei_bad:
        iso.attempt_mutation_with_result(
            runtime, entity, "insert", values=bad_values, where_field=None, where_value=None,
        )
    denial = ei_bad.value
    assert denial.code == "VALIDATION_FAILED", (
        f"{adapter.name}: C-28 段(4): an enum-violating insert was refused with {denial.code!r}, not "
        "VALIDATION_FAILED"
    )
    assert denial.details.get("violated_declaration") == "enum", (
        f"{adapter.name}: C-28 段(4): {denial.details!r} lacks violated_declaration=enum"
    )

    # code review 2026-09-24 R1 (SI-10 非開示): the rejection must name
    # WHERE the request violated the declaration, never the rejected
    # value itself, never a suggested replacement, and never a key
    # outside the contract's own closed vocabulary for this denial.
    details_text = json.dumps(denial.details, default=str)
    assert rejected_value not in details_text, (
        f"{adapter.name}: C-28 段(4) SI-10: the rejected value {rejected_value!r} is disclosed in the denial "
        f"details -- details={denial.details!r}"
    )
    # code review 2026-09-24b (再レビュー 指摘 1): `ConformanceDenial` has no
    # `message` attribute (`getattr(denial, "message", None)` always
    # returns `None` -- `conformance-tests/adapter.py:132-135, 163-172`),
    # so a message-side non-echo check needs the port's own non-echo
    # inspection point instead: `native_cause_of(denial)` (`adapter.py:433`,
    # sanctioned there for exactly this "non-echo inspection", never for
    # recovering denial semantics), whose `str()` on every currently-
    # registered plug is the peer's own real denial message (the in-process
    # plugs' native `FoundationError`/`ValidationError` message; the http
    # plugs' `_HttpFailure`, itself built only from the response's own safe
    # `message` field). `assert_no_payload_echo` (`adapter.py`, the SAME
    # helper C-03's own injection probes already use) applies the
    # established minimum-length guard (`_MIN_ECHO_PAYLOAD_LEN`) so a
    # 1-character declared-enum member is not itself checked (a real
    # non-disclosure gap on those would need a longer probe value, not this
    # generic check) -- `rejected_value` clears that bound.
    native_cause = native_cause_of(denial)
    if native_cause is not None:
        assert_no_payload_echo(native_cause, rejected_value, context=f"{adapter.name}: C-28 段(4) SI-10 native cause")
    # else: this plug exposes no native cause to inspect on this denial --
    # nothing further to check here (disclosed, not a gap this row covers).
    assert not any(isinstance(v, str) and v in declared_enum for v in denial.details.values()), (
        f"{adapter.name}: C-28 段(4) SI-10: the denial discloses a declared enum member as a suggested "
        f"replacement value -- details={denial.details!r}"
    )
    contract = load_contract()
    vocab = contract["errors"]["details_vocabulary"]
    allowed_detail_keys = set(vocab["VALIDATION_FAILED"]) | set(vocab["common_optional"])
    assert set(denial.details.keys()) <= allowed_detail_keys, (
        f"{adapter.name}: C-28 段(4) SI-10: denial details keys {sorted(denial.details.keys())!r} are outside "
        f"the contract's own VALIDATION_FAILED vocabulary {sorted(allowed_detail_keys)!r}"
    )

    # code review 2026-09-24 R5 (nullable:false 観測, 別要求体): 床の
    # operations 10 番目 ("declared enum and nullable constraints enforced
    # on every value written") のうち nullable 半分は enum 側の要求体で
    # は観測できないので、独立した 1 送信で観測する。段(5)の修正は enum
    # 側の要求体だけに掛ける (この送信は段(5)の継ぎ目に加わらない)。
    with pytest.raises(ConformanceDenial) as ei_null:
        iso.attempt_mutation_with_result(
            runtime, entity, "insert",
            values={enum_field: declared_enum[0], nonnull_field: None, sort_field: 2},
            where_field=None, where_value=None,
        )
    assert ei_null.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: C-28 段(4) nullable: a null on a nullable:false field was refused with "
        f"{ei_null.value.code!r}, not VALIDATION_FAILED"
    )
    assert ei_null.value.details.get("violated_declaration") == "nullable", (
        f"{adapter.name}: C-28 段(4) nullable: {ei_null.value.details!r} lacks violated_declaration=nullable"
    )

    # ------------------------------------------------------------------
    # 段 (5): 診断だけを使って同じ要求体を直す (値は catalog の enum から
    # 採る) -- 段(4)の `bad_values` を、`details.field` (contract
    # `errors.details_vocabulary.VALIDATION_FAILED.field`: 本文ルートから
    # の '/' 区切り path) の指す位置**だけ**書き換えて再利用する
    # (code review 2026-09-24 R2)。
    # ------------------------------------------------------------------
    fixed_value = declared_enum[0]
    body = {"operations": [{"values": dict(bad_values)}]}
    field_path = denial.details.get("field")
    assert field_path, f"{adapter.name}: C-28 段(5): the enum denial carries no details.field to repair from"
    parts = field_path.split("/")
    # code review 2026-09-24b (再レビュー 指摘 4): resolve inside a
    # try/except naming this step, rather than letting a bad path surface
    # as a bare KeyError/IndexError/TypeError -- a peer whose `details.
    # field` does not actually resolve against the request body it sent is
    # a real finding this row must report as its OWN failure, not as an
    # opaque traceback.
    try:
        target = body
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        leaf = parts[-1]
        resolved = target[int(leaf)] if leaf.isdigit() else target[leaf]
    except (KeyError, IndexError, TypeError) as exc:
        pytest.fail(
            f"{adapter.name}: C-28 段(5): details.field {field_path!r} does not resolve against the SAME "
            f"request body 段(4) actually sent -- body={body!r}, error={exc!r}"
        )
    assert resolved == rejected_value, (
        f"{adapter.name}: C-28 段(5): details.field {field_path!r} does not resolve, inside the SAME request "
        f"body 段(4) actually sent, to the value that was rejected -- resolved {resolved!r}, expected "
        f"{rejected_value!r} (body={body!r})"
    )
    if leaf.isdigit():
        target[int(leaf)] = fixed_value
    else:
        target[leaf] = fixed_value
    repaired_values = body["operations"][0]["values"]
    assert repaired_values == {**bad_values, enum_field: fixed_value}, (
        f"{adapter.name}: C-28 段(5): the repaired request body diverges from 段(4)'s own body beyond the "
        f"single diagnosed position -- repaired={repaired_values!r}, 段(4)={bad_values!r}"
    )

    # ------------------------------------------------------------------
    # 段 (6): 直した要求に、段(7)で使うのと同じ idempotency_key を付けて
    # dry_run: true で送る。
    # ------------------------------------------------------------------
    key = fresh_identifier("c28key")
    dry = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values=repaired_values, where_field=None, where_value=None,
        dry_run=True, idempotency_key=key,
    )
    assert dry.get("committed") is False, (
        f"{adapter.name}: C-28 段(6): dry_run=true result carries committed={dry.get('committed')!r}"
    )
    assert dry.get("affected") == 1, (
        f"{adapter.name}: C-28 段(6): dry_run=true result carries affected={dry.get('affected')!r}, not 1 "
        "(the real send's own row count)"
    )
    plan = dry.get("plan")
    assert plan, f"{adapter.name}: C-28 段(6): a dry-run result carries no 'plan' -- {dry!r}"
    rows_after_dry_run = iso.select_eq(runtime, entity, [nonnull_field], nonnull_field, marker)
    assert rows_after_dry_run == [], (
        f"{adapter.name}: C-28 段(6): dry_run=true left a real, readable row behind -- {rows_after_dry_run!r}"
    )

    # ------------------------------------------------------------------
    # 段 (7): 段(6)が返した plan をそのまま提示して、同じ要求に同じ
    # idempotency_key を付けて実送信する。plan 不一致による
    # PRECONDITION_FAILED / violated_declaration: plan が起きないこと。
    # ------------------------------------------------------------------
    real = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values=repaired_values, where_field=None, where_value=None,
        idempotency_key=key, plan=plan,
    )
    assert real.get("committed") is True, (
        f"{adapter.name}: C-28 段(7): the real send under 段(6)'s own idempotency_key and plan carries "
        f"committed={real.get('committed')!r}, not True"
    )
    first_request_id = real.get("request_id")
    assert first_request_id, f"{adapter.name}: C-28 段(7): a real, successful insert carries no request_id -- {real!r}"
    rows_after_real_send = iso.select_eq(runtime, entity, [nonnull_field], nonnull_field, marker)
    assert len(rows_after_real_send) == 1, (
        f"{adapter.name}: C-28 段(7): the real send did not leave exactly one row -- {rows_after_real_send!r}"
    )

    # ------------------------------------------------------------------
    # 段 (8): 同 key 同 body で再送する。同じ request_id が返り、行数が
    # 増えない。
    # ------------------------------------------------------------------
    resend = iso.attempt_mutation_with_result(
        runtime, entity, "insert", values=repaired_values, where_field=None, where_value=None,
        idempotency_key=key,
    )
    assert resend.get("request_id") == first_request_id, (
        f"{adapter.name}: C-28 段(8): a same-key/same-body resend carries request_id "
        f"{resend.get('request_id')!r}, not the FIRST execution's own {first_request_id!r}"
    )
    rows_after_resend = iso.select_eq(runtime, entity, [nonnull_field], nonnull_field, marker)
    assert len(rows_after_resend) == 1, (
        f"{adapter.name}: C-28 段(8): a same-key/same-body resend must not add a second row -- "
        f"{rows_after_resend!r}"
    )

    # ------------------------------------------------------------------
    # 段 (9): baseline の各演算子で order_by・page.size・budget 付き query
    # する。R <= page.size <= budget.result_items <= この配備が宣言する
    # limits.result_items (固定リテラル禁止、design §7 段(9) v0.3)。sort
    # key (sort_field) は entity 内で一意な値にし、tie を作らない。
    # ------------------------------------------------------------------
    declared_result_items = iso.capability_document().get("limits", {}).get("result_items")
    # code review 2026-09-24 R6: `declared_result_items >= 3` so
    # `extra_rows = min(3, declared_result_items - 2)` (below) never goes
    # negative and `page_size = max_sort + 1` (below, design D-6's own
    # "結果集合を page.size 未満に保つ") never exceeds the deployment's
    # own declared bound.
    assert isinstance(declared_result_items, int) and declared_result_items >= 3, (
        f"{adapter.name}: C-28 段(9): this isolated instance declares no usable limits.result_items -- "
        f"{iso.capability_document().get('limits')!r}"
    )
    extra_rows = min(3, declared_result_items - 2)
    max_sort = 1 + extra_rows
    # Inserted in DESCENDING order (max_sort down to 2) so that the default,
    # un-ordered storage/insertion sequence -- 1, max_sort, max_sort-1, ...,
    # 2 -- is NOT already ascending by `sort_field`. If it were, an adapter
    # that silently drops `order_by` could still pass the ascending-order
    # assertion below by coincidence (an in-memory backend that returns rows
    # in insertion order).
    for value in range(max_sort, 1, -1):
        iso.attempt_mutation(
            runtime, entity, "insert",
            values={enum_field: fixed_value, nonnull_field: fresh_identifier("c28fill"), sort_field: value},
            where_field=None, where_value=None,
        )
    # code review 2026-09-24 R6: `page_size` is strictly GREATER than the
    # total row count (`max_sort`), not equal to it, so every operator's
    # own R (bounded by `max_sort`) stays R < page.size (design D-6).
    page_size = max_sort + 1
    budget_result_items = page_size
    assert page_size <= budget_result_items <= declared_result_items, (
        f"{adapter.name}: C-28 段(9): the chain page.size<=budget.result_items<=limits.result_items does not "
        f"hold for page_size={page_size}, budget={budget_result_items}, declared={declared_result_items}"
    )
    all_sort_values = set(range(1, max_sort + 1))
    _operator_probe_values: dict[str, object] = {
        "eq": 1, "ne": 1, "lt": max_sort, "lte": max_sort, "gt": 1, "gte": 1, "in": [1],
    }
    # code review 2026-09-24 R3: the expected MATCHING SET per operator
    # (not merely "non-empty"/"len <= page_size") -- rows carry sort_field
    # in {1, ..., max_sort}; a peer whose operator semantics drift (e.g.
    # `lt` behaving as `lte`) must diverge from one of these sets.
    _expected_by_operator: dict[str, set[int]] = {
        "eq": {1},
        "in": {1},
        "ne": all_sort_values - {1},
        "gt": all_sort_values - {1},
        "lt": all_sort_values - {max_sort},
        "lte": set(all_sort_values),
        "gte": set(all_sort_values),
    }
    # 空振り禁止 (OPERATING_CONDITIONS.md §1.5 の 32): an empty operator set
    # would make every assertion inside the loop below vacuously unreached
    # rather than caught -- this guard is what turns that silent skip into
    # a real failure (mutation candidate N13, work order §3.6).
    assert _BASELINE_OPERATORS, "C-28 段(9): the baseline operator set must not be empty"
    operators_observed = 0
    for operator in _BASELINE_OPERATORS:
        operators_observed += 1
        result = iso.attempt_filter_with_result(
            runtime, entity, [nonnull_field, sort_field], sort_field, operator, _operator_probe_values[operator],
            order_by=[{"field": sort_field, "direction": "asc"}],
            page_size=page_size, budget={"result_items": budget_result_items},
        )
        items = result["items"]
        assert items, f"{adapter.name}: C-28 段(9): operator {operator!r} matched zero rows -- {result!r}"
        assert len(items) < page_size, (
            f"{adapter.name}: C-28 段(9): operator {operator!r} returned {len(items)} rows, not strictly less "
            f"than its own page.size={page_size} (design D-6)"
        )
        seq_values = [item[sort_field] for item in items]
        assert seq_values == sorted(seq_values), (
            f"{adapter.name}: C-28 段(9): operator {operator!r} under order_by did not return rows in "
            f"ascending {sort_field!r} order -- {seq_values!r}"
        )
        assert set(seq_values) == _expected_by_operator[operator], (
            f"{adapter.name}: C-28 段(9): operator {operator!r} matched {set(seq_values)!r}, not the expected "
            f"{_expected_by_operator[operator]!r} -- the operator's own semantics are not what this turn "
            "assumed"
        )
    assert operators_observed == len(_BASELINE_OPERATORS), (
        f"{adapter.name}: C-28 段(9): only {operators_observed} of {len(_BASELINE_OPERATORS)} baseline "
        "operators were actually observed"
    )

    # ------------------------------------------------------------------
    # 段 (10): 述語 update。
    # ------------------------------------------------------------------
    updated_marker = marker + "_upd"
    update_result = iso.attempt_mutation_with_result(
        runtime, entity, "update", values={nonnull_field: updated_marker},
        where_field=nonnull_field, where_value=marker,
    )
    assert update_result.get("affected") == 1, (
        f"{adapter.name}: C-28 段(10): predicate update affected {update_result.get('affected')!r} rows, not 1"
    )
    assert len(iso.select_eq(runtime, entity, [nonnull_field], nonnull_field, updated_marker)) == 1, (
        f"{adapter.name}: C-28 段(10): predicate update did not actually change the row"
    )

    # ------------------------------------------------------------------
    # 段 (11): 述語 delete (declare-and-echo)。
    # ------------------------------------------------------------------
    delete_result = iso.attempt_mutation_with_result(
        runtime, entity, "delete", values=None,
        where_field=nonnull_field, where_value=updated_marker,
        destructive=True, confirmation=VALID_CONFIRMATION,
    )
    assert delete_result.get("affected") == 1, (
        f"{adapter.name}: C-28 段(11): confirmed predicate delete affected {delete_result.get('affected')!r} "
        "rows, not 1"
    )
    assert iso.select_eq(runtime, entity, [nonnull_field], nonnull_field, updated_marker) == [], (
        f"{adapter.name}: C-28 段(11): confirmed predicate delete did not actually remove the row"
    )

    # ------------------------------------------------------------------
    # 段 (12): 最終 query で状態を確認する -- 残る行が (7)(10)(11) の帰結
    # (marker 由来の 1 行は update 後 delete されて残らない) と一致する。
    # ------------------------------------------------------------------
    final_count = iso.count(runtime, entity)
    assert final_count == extra_rows, (
        f"{adapter.name}: C-28 段(12): final row count {final_count} does not match 段(9) 前の fill rows "
        f"({extra_rows}) -- the 段(7) row must have been updated (段(10)) then deleted (段(11))"
    )
