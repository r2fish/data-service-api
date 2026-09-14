"""Phase 9 WP-3d (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-6, 追補 R-g/S-l;
監督裁定集約 {scratchpad}/rulings-r5-r6.md B-1..B-6): local, peer-side
pinning for `config.narrow_limits_by_budget` and its wiring into `read`/
`transact`/the three schema operations. The conformance suite's own
`test_c24_request_budget.py` is the cross-peer evidence (including the
design's own fixed `batch_items` recipe); this file pins the helper
function itself and the per-endpoint apply table, including the two
classes (`result_items` on mutate, `batch_items` on query/schema) the
conformance suite's own recipe does not individually enumerate.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import ControlPlane, Filter, MitateDataService, Role
from mitatedb_api.config import FoundationConfig, narrow_limits_by_budget
from mitatedb_api.errors import ResourceLimitError, ValidationError


class NarrowLimitsByBudgetTests(unittest.TestCase):
    def setUp(self):
        self.deployed = FoundationConfig()

    def test_no_budget_returns_the_deployed_config_unchanged(self):
        self.assertIs(narrow_limits_by_budget(self.deployed, None, "mutate"), self.deployed)
        self.assertIs(narrow_limits_by_budget(self.deployed, {}, "mutate"), self.deployed)

    def test_narrows_to_the_smaller_value(self):
        effective = narrow_limits_by_budget(self.deployed, {"batch_items": 2}, "mutate")
        self.assertEqual(effective.max_batch_items, 2)
        # Every other field is untouched.
        self.assertEqual(effective.max_execution_ms, self.deployed.max_execution_ms)
        self.assertEqual(effective.max_result_rows, self.deployed.max_result_rows)

    def test_never_raises_the_bound(self):
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"batch_items": self.deployed.max_batch_items + 1}, "mutate")
        self.assertEqual(ctx.exception.details["violated_declaration"], "budget")
        self.assertEqual(ctx.exception.details["field"], "budget/batch_items")

    def test_inapplicable_class_on_mutate_result_items(self):
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"result_items": 1}, "mutate")
        self.assertEqual(ctx.exception.details["violated_declaration"], "budget")
        self.assertEqual(ctx.exception.details["field"], "budget/result_items")

    def test_inapplicable_class_on_query_batch_items(self):
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"batch_items": 1}, "query")
        self.assertEqual(ctx.exception.details["field"], "budget/batch_items")

    def test_schema_only_accepts_execution_ms(self):
        narrow_limits_by_budget(self.deployed, {"execution_ms": 100}, "schema")
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"batch_items": 1}, "schema")
        self.assertEqual(ctx.exception.details["field"], "budget/batch_items")

    def test_non_integer_value_carries_declared_and_observed_type(self):
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"execution_ms": "5000"}, "mutate")
        self.assertEqual(ctx.exception.details["violated_declaration"], "budget")
        self.assertEqual(ctx.exception.details["field"], "budget/execution_ms")
        self.assertEqual(ctx.exception.details["declared_type"], "integer")
        self.assertEqual(ctx.exception.details["observed_type"], "string")

    def test_boolean_is_not_an_integer(self):
        with self.assertRaises(ValidationError) as ctx:
            narrow_limits_by_budget(self.deployed, {"batch_items": True}, "mutate")
        self.assertEqual(ctx.exception.details["observed_type"], "boolean")

    def test_less_than_one_is_refused(self):
        with self.assertRaises(ValidationError):
            narrow_limits_by_budget(self.deployed, {"batch_items": 0}, "mutate")


class BudgetWiringTests(unittest.TestCase):
    """The design's own fixed C-24 (1) recipe, pinned directly against
    `ApplicationRuntime.transact`/`.read` (peer-local, not through the
    conformance port)."""

    def setUp(self):
        self.control = ControlPlane("synthetic-test-pepper-0123456789")
        self.control.provision_application("app_budget")
        self.dev_id, self.dev_secret = self.control.issue_credential("app_budget", Role.DEVELOPER)
        self.runtime_id, self.runtime_secret = self.control.issue_credential("app_budget", Role.RUNTIME)
        self.service = MitateDataService(self.control)
        self.dev = self.service.open_session(self.dev_secret)
        self.runtime = self.service.open_session(self.runtime_secret)
        self.dev.create_collection("notes", {"title": "text"})

    def _batch(self, n):
        return [{"type": "insert", "collection": "notes", "values": {"title": f"row-{i}"}} for i in range(n)]

    def test_batch_items_budget_admits_two_refuses_three(self):
        result = self.runtime.transact(self._batch(2), budget={"batch_items": 2})
        self.assertEqual(len(result), 2)
        with self.assertRaises(ResourceLimitError) as ctx:
            self.runtime.transact(self._batch(3), budget={"batch_items": 2})
        self.assertEqual(ctx.exception.details["limit_class"], "batch_items")

    def test_omitted_budget_still_reaches_the_deployed_bound(self):
        # Positive control: the deployed default (100) admits well more
        # than 2 operations with no budget at all.
        result = self.runtime.transact(self._batch(5))
        self.assertEqual(len(result), 5)

    def test_over_deployment_budget_is_validation_failed(self):
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "x"}}],
                budget={"execution_ms": 10_000_000},
            )
        self.assertEqual(ctx.exception.details["violated_declaration"], "budget")

    def test_result_items_inapplicable_on_mutate(self):
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "x"}}],
                budget={"result_items": 1},
            )
        self.assertEqual(ctx.exception.details["field"], "budget/result_items")

    def test_budget_validation_precedes_destructive_confirmation(self):
        """D-6(3): an over-deployment budget on an UNCONFIRMED destructive
        request is refused VALIDATION_FAILED, never DESTRUCTIVE_
        CONFIRMATION_REQUIRED -- budget validity is checked before pass 1
        (target existence/confirmation) even begins."""
        self.runtime.transact([{"type": "insert", "collection": "notes", "values": {"title": "doomed"}}])
        with self.assertRaises(ValidationError) as ctx:
            self.runtime.transact(
                [{"type": "delete", "collection": "notes", "destructive": True,
                  "filters": [Filter("title", "eq", "doomed")]}],
                budget={"execution_ms": 10_000_000},
            )
        self.assertEqual(ctx.exception.details["violated_declaration"], "budget")
        # The refused delete must not have executed.
        self.assertEqual(len(self.runtime.read("notes")), 1)

    def test_query_result_items_budget_is_accepted(self):
        self.runtime.transact([{"type": "insert", "collection": "notes", "values": {"title": "q"}}])
        rows = self.runtime.read("notes", budget={"result_items": 50})
        self.assertEqual(len(rows), 1)

    def test_query_result_items_budget_narrows_the_limit_check(self):
        for i in range(3):
            self.runtime.transact([{"type": "insert", "collection": "notes", "values": {"title": f"n{i}"}}])
        with self.assertRaises(ResourceLimitError) as ctx:
            # `limit=3` exceeds a budget-narrowed bound of 2.
            self.runtime.read("notes", limit=3, budget={"result_items": 2})
        self.assertEqual(ctx.exception.details["limit_class"], "result_items")

    def test_schema_operation_budget_execution_ms(self):
        result = self.dev.add_field("notes", "rank", "integer", budget={"execution_ms": 5000})
        self.assertIsNotNone(result["revision"])
        with self.assertRaises(ValidationError):
            self.dev.add_field("notes", "rank2", "integer", budget={"execution_ms": 10_000_000})

    def test_batch_embedded_in_filter_respects_budget_narrowed_batch_items(self):
        """K-3 (監督裁定集約 rulings-r5-r6.md, WP-3cd audit §11 必須 4,
        MitateDB `cell.py`'s `_bind_filters` -- the `in`-filter `batch_
        items` check): this was the ONE check point B-2 missed -- it used
        to read `self.config.max_batch_items` directly, ignoring a
        request's own budget-narrowed value, so a SINGLE-operation batch
        (well under a `budget={"batch_items": 2}` COUNT bound of 2) whose
        lone delete's own `in` filter names 3 values could still slip
        through at the deployed default (100). Deliberately no `confirm`/
        `destructive` setup: `_validate_delete_confirmation` runs `_bind_
        filters` (this check) BEFORE evaluating the confirmation phrase
        at all, so this refusal is reached regardless."""
        for i in range(3):
            self.runtime.transact([{"type": "insert", "collection": "notes", "values": {"title": f"del-{i}"}}])
        with self.assertRaises(ResourceLimitError) as ctx:
            self.runtime.transact(
                [{"type": "delete", "collection": "notes",
                  "filters": [Filter("title", "in", ["del-0", "del-1", "del-2"])]}],
                budget={"batch_items": 2},
            )
        self.assertEqual(ctx.exception.details["limit_class"], "batch_items")
        # Positive control: the SAME 3-value `in` filter, with no budget
        # at all, reaches the deployed default (100) and is accepted at
        # THIS check -- proving the refusal above is really about the
        # budget-narrowed bound, not about a 3-value `in` filter being
        # refused unconditionally (the delete goes on to fail its own
        # confirmation choke instead, a DIFFERENT, later refusal).
        from mitatedb_api.errors import DestructiveConfirmationRequired
        with self.assertRaises(DestructiveConfirmationRequired):
            self.runtime.transact(
                [{"type": "delete", "collection": "notes",
                  "filters": [Filter("title", "in", ["del-0", "del-1", "del-2"])]}])

    def test_gate_forwards_budget_and_endpoint_kind_to_limit_gate_on_query_and_mutate(self):
        """R-32 レビュー是正 (監督裁定): `_gate` が受け取った `budget`/
        `endpoint_kind` を `_limit_gate` へそのまま転送する配線そのものを
        query (`read`)/mutate (`transact`) の両経路で固定する -- `_limit_
        gate` をインスタンス属性として記録用 wrapper に monkeypatch し
        (`conformance/conformance_adapter_mitatedb.py`/`_http.py` 自身の
        `*args, **kwargs` 転送 wrapper と同じ convention)、元の実装へ転送
        したうえで、wrapper 自身が受け取った引数を検査する。製品コードは
        変更しない -- テストのみのインストルメンテーション。"""
        cell = self.runtime._ApplicationRuntime__cell  # noqa: SLF001 -- test-only instrumentation, same convention the conformance adapters use.
        original_limit_gate = cell._limit_gate  # noqa: SLF001
        for endpoint_kind in ("query", "mutate"):
            with self.subTest(endpoint_kind=endpoint_kind):
                recorded = []

                def _recording_limit_gate(*args, _orig=original_limit_gate, **kwargs):
                    recorded.append((kwargs.get("budget"), kwargs.get("endpoint_kind")))
                    return _orig(*args, **kwargs)

                cell._limit_gate = _recording_limit_gate  # noqa: SLF001
                try:
                    budget = {"execution_ms": 5000}
                    if endpoint_kind == "query":
                        self.runtime.read("notes", budget=budget)
                    else:
                        self.runtime.transact(
                            [{"type": "insert", "collection": "notes", "values": {"title": "wiring"}}],
                            budget=budget,
                        )
                finally:
                    cell._limit_gate = original_limit_gate  # noqa: SLF001
                # Non-vacuity: at least one call actually reached the wrapper.
                self.assertGreaterEqual(len(recorded), 1)
                observed_budget, observed_endpoint_kind = recorded[0]
                self.assertEqual(observed_budget, budget)
                self.assertEqual(observed_endpoint_kind, endpoint_kind)


if __name__ == "__main__":
    unittest.main()
