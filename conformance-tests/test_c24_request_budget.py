"""C-24 -- a request-scoped `budget` narrows a declared bound downward
only (SI-08, SI-15).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-6, §6.2 "C-24 request budget", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-24")`
via the module-level `pytestmark`.

Declare-first, capability `request_budget` (contract 1.7.0, new), house
style shared with C-20/C-22/C-23 -- ONE test, no `pytest.skip`:

  - `unavailable` branch: a request carrying `budget` is refused
    `CAPABILITY_UNSUPPORTED` before execution, zero side effects.
  - `budget_enforced` branch: (1) `batch_items` -- `budget.batch_items = 2`
    lets a 2-operation mutate batch through and refuses a 3-operation one
    with `LIMIT_EXCEEDED`/`limit_class: batch_items` (design's own fixed
    recipe, §6.2 C-24 (1): this position sits below both the request
    schema's own `maxItems: 100` and this deployment's own declared
    `batch_items`, so the request-shape layer never fires first); (3) a
    `budget` value ABOVE the deployment's own declared bound is refused
    `VALIDATION_FAILED`/`violated_declaration: budget`, never silently
    clamped; (4) a `budget` naming a class that does not apply to the
    endpoint it was sent to (`result_items` on a mutation) is refused the
    same way, `field` naming `budget/<class>`; (6) the one externally
    observable ordering fact (D-6(3)): an over-deployment `budget` on an
    UNCONFIRMED destructive request is refused `VALIDATION_FAILED` before
    confirmation is even evaluated -- never `DESTRUCTIVE_CONFIRMATION_
    REQUIRED`.

**Disclosed scope limit (`result_items` non-vacuity, D-6 開示事項,
work order 完了条件 → 変異 14 の但し書き)**: `result_items` applies to
`query` (checked here: a valid `budget.result_items` on a query is
accepted, never refused as inapplicable) but is NOT driven at its own
N/N+1 boundary by this row -- MitateDB's own `result_items` refusal is
keyed to the requested page `limit` rather than the row count actually
returned (`MitateDB-api/src/mitatedb_api/cell.py:834-837`), which does not
compose into one recipe both peers satisfy the same way. `batch_items`
alone carries this row's own non-vacuity requirement (L8-15: an adapter
that silently drops `budget` turns vector (1) red on every plug).
`execution_ms` is not driven at all (same reason C-05 V2 excludes it: no
deterministic N/N+1 exists under `reference_wall_clock`, phase 8 D-1).

**Overlaps C-05**: the same limit classes, a different proposition (C-05
fixes the deployment's own declared bound; this row fixes one request's
downward narrowing of it).
"""
from __future__ import annotations

import pytest

from adapter import BatchOperation, ConformanceAdapter, ConformanceDenial, fresh_identifier
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-24")


def _status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("request_budget", {}).get(
        "status", "unavailable"
    )


def _expected_branch_for_status(status: str) -> str:
    return "unavailable" if status == "unavailable" else "budget_enforced"


def test_c24_request_budget(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    status = _status(adapter)
    document = adapter.capability_document()
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c24")
    entity = fresh_identifier("c24")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before_all = iso.count(runtime, entity)

    observed_branch: str
    if status == "unavailable":
        with pytest.raises(ConformanceDenial) as ei:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": "x"}, where_field=None, where_value=None,
                budget={"execution_ms": 1},
            )
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: request_budget is 'unavailable', but a budget-bearing request was refused "
            f"with {ei.value.code!r} instead of CAPABILITY_UNSUPPORTED"
        )
        assert iso.count(runtime, entity) == count_before_all, (
            f"{adapter.name}: a request refused as unavailable must have zero side effects"
        )
        observed_branch = "unavailable"
    else:
        # (1) batch_items: budget.batch_items = 2 admits a 2-op batch,
        # refuses a 3-op one -- the design's own fixed recipe (§6.2 C-24
        # (1)), sitting below both the request schema's own maxItems and
        # this deployment's own declared batch_items.
        def batch_of(n: int) -> list[BatchOperation]:
            return [
                BatchOperation(operation="insert", values={"label": fresh_identifier(f"c24b{i}")})
                for i in range(n)
            ]

        two_ops = iso.attempt_batch_with_result(runtime, entity, batch_of(2), budget={"batch_items": 2})
        assert two_ops.get("affected") == 2, (
            f"{adapter.name}: a 2-operation batch under budget.batch_items=2 must succeed -- {two_ops!r}"
        )
        with pytest.raises(ConformanceDenial) as ei_batch:
            iso.attempt_batch_with_result(runtime, entity, batch_of(3), budget={"batch_items": 2})
        assert ei_batch.value.code == "LIMIT_EXCEEDED", (
            f"{adapter.name}: a 3-operation batch under budget.batch_items=2 -> {ei_batch.value.code!r}, "
            "expected LIMIT_EXCEEDED"
        )
        assert ei_batch.value.details.get("limit_class") == "batch_items", ei_batch.value.details

        # (3) over-deployment budget -> VALIDATION_FAILED, never silently
        # clamped to the deployed value.
        deployed_execution_ms = document.get("limits", {}).get("execution_ms")
        assert isinstance(deployed_execution_ms, int), (
            f"{adapter.name}: capability_document()['limits']['execution_ms'] is not an int -- {document.get('limits')!r}"
        )
        with pytest.raises(ConformanceDenial) as ei_over:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": fresh_identifier("c24over")},
                where_field=None, where_value=None, budget={"execution_ms": deployed_execution_ms + 1},
            )
        assert ei_over.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: budget.execution_ms above the deployed value ({deployed_execution_ms}) -> "
            f"{ei_over.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei_over.value.details.get("violated_declaration") == "budget", ei_over.value.details

        # (4) inapplicable class: result_items does not apply to mutate.
        with pytest.raises(ConformanceDenial) as ei_inapplicable:
            iso.attempt_mutation_with_result(
                runtime, entity, "insert", values={"label": fresh_identifier("c24bad")},
                where_field=None, where_value=None, budget={"result_items": 1},
            )
        assert ei_inapplicable.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: budget.result_items on a mutation -> {ei_inapplicable.value.code!r}, expected "
            "VALIDATION_FAILED"
        )
        assert ei_inapplicable.value.details.get("violated_declaration") == "budget", ei_inapplicable.value.details
        assert ei_inapplicable.value.details.get("field") == "budget/result_items", ei_inapplicable.value.details

        # positive control: result_items DOES apply to query -- accepted,
        # never refused as inapplicable (disclosed: not driven at its own
        # N/N+1 boundary here, module docstring).
        accepted = iso.query_with_budget(runtime, entity, ["label"], None, None, budget={"result_items": 50})
        assert isinstance(accepted, dict) and "items" in accepted, (
            f"{adapter.name}: a query carrying an in-bound budget.result_items was refused -- {accepted!r}"
        )

        # (5) positive control: omitting budget entirely still succeeds.
        iso.attempt_mutation_with_result(
            runtime, entity, "insert", values={"label": fresh_identifier("c24nobudget")},
            where_field=None, where_value=None,
        )

        # (6) ordering: an over-deployment budget on an UNCONFIRMED
        # destructive request is refused VALIDATION_FAILED before
        # confirmation is evaluated -- never DESTRUCTIVE_CONFIRMATION_
        # REQUIRED (design D-6(3)).
        doomed_marker = fresh_identifier("c24doomed")
        iso.attempt_mutation(runtime, entity, "insert", values={"label": doomed_marker}, where_field=None, where_value=None)
        with pytest.raises(ConformanceDenial) as ei_order:
            iso.attempt_batch_with_result(
                runtime, entity,
                [BatchOperation(operation="delete", where_field="label", where_value=doomed_marker, destructive=True)],
                budget={"execution_ms": deployed_execution_ms + 1},
            )
        assert ei_order.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an UNCONFIRMED destructive delete carrying an over-deployment budget -> "
            f"{ei_order.value.code!r}, expected VALIDATION_FAILED (budget validation precedes confirmation "
            "evaluation, design D-6(3))"
        )
        assert len(iso.select_eq(runtime, entity, ["label"], "label", doomed_marker)) == 1, (
            f"{adapter.name}: the refused delete must not have executed"
        )

        observed_branch = "budget_enforced"

    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: request_budget status {status!r} recorded branch {observed_branch!r}, expected "
        f"{expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )
