"""Contract 1.7.0 R-5 (`idempotency_key` record-and-replay) -- design
docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-5,
work order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2c,
ruling集約 {scratchpad}/rulings-r5-r6.md I-1..I-13.

Peer-local coverage underneath `conformance-tests/test_c23_idempotency_
semantics.py`'s own cross-peer test (this file never imports or edits
anything under `conformance-tests/`): exercises `ApplicationCell`
(in-memory) and `DataService` directly for the WP-2c completion
conditions (§2 WP-2c 完了条件 1-9), and `PostgresCell` (real PostgreSQL,
§5.3 C-5) for the "same tx" / side-table persistence properties that are
invisible from the `ApplicationCell` half alone.

Reuses `test_application_audit.py`'s `build_service`/`runtime_context`/
`developer_context` fixtures (one Application `app-a`, runtime credential
`cred-a`/`secret-a`, developer credential `dev-a`/`dev-secret-a`, one
seeded entity `notes` with one row) and `test_postgres.py`'s `app_a`/
`make_cell`/`platform` fixtures, matching `test_dry_run_and_plan.py`'s own
established convention for this phase's peer-local test files.
"""
from __future__ import annotations

from typing import Any

import pytest

from r2db_api.audit import ApplicationAuditSink
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.structured import (
    ApplicationCell,
    idempotency_digest,
    normalize_request_for_idempotency,
)

from test_application_audit import build_service, developer_context, runtime_context
from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()


# ===========================================================================
# Section 1: the digest helper itself (`structured.py`).
# ===========================================================================


def test_normalize_request_for_idempotency_excludes_three_keys() -> None:
    """I-2: `plan`/`dry_run`/`idempotency_key` are dropped; every other
    key (including `budget`/`transaction`/`confirmation`) survives."""
    request = {
        "operations": [{"operation": "insert"}], "transaction": "atomic", "budget": {"batch_items": 1},
        "confirmation": "phrase", "plan": "stale-token", "dry_run": True, "idempotency_key": "my-key",
    }
    normalized = normalize_request_for_idempotency(request)
    assert b'"plan"' not in normalized
    assert b'"dry_run"' not in normalized
    assert b'"idempotency_key"' not in normalized
    assert b'"operations"' in normalized
    assert b'"transaction"' in normalized
    assert b'"budget"' in normalized
    assert b'"confirmation"' in normalized


def test_idempotency_digest_ignores_the_key_itself_but_not_the_body() -> None:
    """I-2: two requests differing only in `idempotency_key` digest
    identically; two requests differing in body digest differently."""
    a = {"entity": "widgets", "operations": [{"operation": "insert", "values": {"label": "x"}}], "idempotency_key": "k1"}
    b = {"entity": "widgets", "operations": [{"operation": "insert", "values": {"label": "x"}}], "idempotency_key": "k2"}
    c = {"entity": "widgets", "operations": [{"operation": "insert", "values": {"label": "y"}}], "idempotency_key": "k1"}
    assert idempotency_digest(a) == idempotency_digest(b)
    assert idempotency_digest(a) != idempotency_digest(c)


# ===========================================================================
# Section 2: `ApplicationCell` (in-memory backend) -- WP-2c 完了条件 1-9.
# ===========================================================================


def _memory_cell_with_widgets() -> ApplicationCell:
    cell = ApplicationCell(application_id="app-mem")
    # `label` is declared `string` (not left untyped) so a non-string
    # value is a real, deterministic `VALIDATION_FAILED` -- needed to
    # exercise "a failed attempt leaves no record" below.
    cell.apply_schema(
        {"operation": "create_entity", "entity": "widgets", "fields": ["label"], "field_types": {"label": "string"}},
        developer=True, limits=LIMITS,
    )
    return cell


def _mutate_plan_request(entity: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    return {"entity": entity, "operations": operations}


def test_condition_1_failed_attempt_leaves_no_record_and_resend_is_a_new_execution() -> None:
    """完了条件 1: 記録は data tx と同一 tx にのみ書かれる -- 失敗した試行
    (無効な値を含む batch) の後、同じ key の再送は新規実行になる (=
    最初の insert が実際に 2 回目で実行され、行が実際に増える)。"""
    cell = _memory_cell_with_widgets()
    failing_ops = [{"operation": "insert", "values": {"label": "one"}}, {"operation": "insert", "values": {"label": 123}}]
    with pytest.raises(FoundationError):
        cell.transact(
            "widgets", failing_ops, LIMITS, plan_request=_mutate_plan_request("widgets", failing_ops), idempotency_key="k1",
        )
    assert cell._idempotency == {}, "a failed attempt must leave no record"
    assert cell.entities["widgets"] == [], "the failed batch's own tentative insert must have rolled back"

    ok_ops = [{"operation": "insert", "values": {"label": "two"}}]
    outcome = cell.transact("widgets", ok_ops, LIMITS, plan_request=_mutate_plan_request("widgets", ok_ops), idempotency_key="k1")
    assert outcome.replayed is False, "the same key, presented after a failed attempt, must be a NEW execution"
    assert outcome.affected == 1
    assert len(cell.entities["widgets"]) == 1


def test_condition_2_same_key_same_body_replays_without_re_executing() -> None:
    """完了条件 2: 同一 key + 同一 body の再送が元の結果を返し、行が 1 つ
    しか増えていない。"""
    cell = _memory_cell_with_widgets()
    ops = [{"operation": "insert", "values": {"label": "one"}}]
    plan_request = _mutate_plan_request("widgets", ops)
    # M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): a record with
    # no `request_id` is treated as absent -- a real caller (`DataService`)
    # always supplies one, so this direct-to-cell test does too, to
    # exercise a genuinely REPLAYABLE record rather than accidentally
    # simulating the pre-1.7.0 (request_id-less) shape `test_idempotency_
    # records.py`'s condition-1-style tests are not testing here.
    first = cell.transact("widgets", ops, LIMITS, plan_request=plan_request, idempotency_key="k1", request_id="rid-cond2-1")
    assert first.replayed is False
    assert first.affected == 1
    assert len(cell.entities["widgets"]) == 1

    second = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="k1", request_id="rid-cond2-2")
    assert second.replayed is True
    assert second.affected == first.affected
    assert second.assigned_addresses == first.assigned_addresses
    assert len(cell.entities["widgets"]) == 1, "the row count must not have increased a second time"


def test_condition_3_same_key_different_body_is_conflict() -> None:
    """完了条件 3: 同一 key + 異なる body が CONFLICT +
    violated_declaration = idempotency_key になる。元の要求内容は details
    に出てこない (denial は先の要求を開示しない)。"""
    cell = _memory_cell_with_widgets()
    ops_a = [{"operation": "insert", "values": {"label": "one"}}]
    # M-6: a `request_id`-bearing record is what makes this a genuine
    # CONFLICT test -- a request_id-less record would be treated as
    # absent (M-6) and the differing-digest resend would simply re-
    # execute instead of conflicting.
    cell.transact("widgets", ops_a, LIMITS, plan_request=_mutate_plan_request("widgets", ops_a), idempotency_key="k1", request_id="rid-cond3-1")

    ops_b = [{"operation": "insert", "values": {"label": "two"}}]
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", ops_b, LIMITS, plan_request=_mutate_plan_request("widgets", ops_b), idempotency_key="k1", request_id="rid-cond3-2")
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"violated_declaration": "idempotency_key", "field": "idempotency_key"}
    assert len(cell.entities["widgets"]) == 1, "the conflicting resend must not have executed"


def test_condition_3b_omitted_budget_then_resend_with_empty_budget_is_conflict_not_replay() -> None:
    """F-② (外部レビュー 2, scratchpad/review2/frame.md, 監督裁定 U-11):
    `budget` is part of what a resend must match (契約 1.7.0
    `idempotency.record`, "every other field, including budget,
    transaction and confirmation, is part of what a resend must match")
    -- an omitted `budget` and a present-but-empty `budget: {}` are two
    DIFFERENT requests. Pins r2db's own already-correct `if budget is not
    None:` (`service.py::DataService._mutate_outcome`) against the peer defect (`MitateDB-api`'s
    `cell.py` used `if budget:`, which dropped an empty-but-PRESENT
    `budget: {}` from the digest exactly as if it had been omitted)."""
    ops = [{"operation": "insert", "values": {"label": "one"}}]
    plan_request_omitted = _mutate_plan_request("widgets", ops)
    cell = _memory_cell_with_widgets()
    first = cell.transact("widgets", ops, LIMITS, plan_request=plan_request_omitted, idempotency_key="k1", request_id="rid-cond3b-1")
    assert first.replayed is False

    plan_request_empty_budget = dict(plan_request_omitted, budget={})
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", ops, LIMITS, plan_request=plan_request_empty_budget, idempotency_key="k1", request_id="rid-cond3b-2")
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"violated_declaration": "idempotency_key", "field": "idempotency_key"}
    assert len(cell.entities["widgets"]) == 1, "the conflicting resend must not have executed"


def test_condition_4_replay_of_a_destructive_operation_skips_target_existence_and_confirmation() -> None:
    """完了条件 4: 記録済み key の再送が target-existence / confirmation /
    precondition を評価せずに答える -- drop_entity の再送は entity がもう
    無くても、確認 phrase が無くても、元の結果を返す。"""
    cell = ApplicationCell(application_id="app-mem")
    cell.apply_schema({"operation": "create_entity", "entity": "gadgets", "fields": ["label"]}, developer=True, limits=LIMITS)

    from r2db_api.structured import drop_entity_confirmation_phrase

    phrase = drop_entity_confirmation_phrase("gadgets", cell.schema_revision)
    op = {"operation": "drop_entity", "entity": "gadgets", "destructive": True, "confirmation": phrase}
    plan_request = {key: value for key, value in op.items() if key not in ("plan", "dry_run")}
    # M-6: a request_id-bearing record, so the resend below is a genuine
    # replay (never a request_id-less record, treated as absent).
    first = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=plan_request, idempotency_key="k-drop", request_id="rid-cond4-1")
    assert first.committed is True
    assert "gadgets" not in cell.entities

    # Resend the IDENTICAL operation object -- the entity is gone and the
    # confirmation phrase (computed from schema_revision) is now stale --
    # yet the resend must answer from the record, never NOT_FOUND/
    # DESTRUCTIVE_CONFIRMATION_REQUIRED.
    second = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-drop", request_id="rid-cond4-2")
    assert second.replayed is True
    assert second.committed is True
    assert second.revision == first.revision


def test_condition_5_key_scope_is_application_not_credential() -> None:
    """完了条件 5: 同一 Application の別 credential から同じ key を送ると
    同一要求とみなされる (A-5) -- `ApplicationCell` は 1 インスタンス =
    1 Application なので、別 credential からの呼び出しも同じ dict を共有
    することで scope が Application であることが構造的に成り立つ。"""
    cell = _memory_cell_with_widgets()
    ops = [{"operation": "insert", "values": {"label": "one"}}]
    # Two distinct "credentials" reaching the SAME cell instance -- nothing
    # in `transact`'s own signature carries a credential identity at all,
    # which is exactly the point: the record is keyed only by
    # `idempotency_key`, scoped to the Application (the cell), never to a
    # caller identity.
    first = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="shared-key", request_id="rid-cond5-1")
    second = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="shared-key", request_id="rid-cond5-2")
    assert second.replayed is True
    assert second.affected == first.affected
    assert len(cell.entities["widgets"]) == 1


def test_condition_6_applies_to_schema_operation_request() -> None:
    """完了条件 6: SchemaOperationRequest にも適用される -- 同一 key の
    2 回目の create_entity は再実行されず、元の revision を返す。"""
    cell = ApplicationCell(application_id="app-mem")
    op = {"operation": "create_entity", "entity": "sprockets", "fields": ["label"]}
    plan_request = {key: value for key, value in op.items() if key not in ("plan", "dry_run")}
    first = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-create", request_id="rid-cond6-1")
    assert first.replayed is False
    assert first.committed is True

    second = cell.apply_schema(dict(op), developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-create", request_id="rid-cond6-2")
    assert second.replayed is True
    assert second.revision == first.revision
    # A genuine second create_entity (no key) would have failed CONFLICT
    # ("Entity already exists") -- the replay proves no re-execution
    # happened at all, not merely that this particular failure was masked.


def test_condition_7_full_store_refuses_before_execution_with_no_row_growth() -> None:
    """完了条件 7: 満杯の拒否が実行前に起き、LIMIT_EXCEEDED +
    limit_class: idempotency_entries であり、行が 1 つも増えていない。"""
    tiny_limits = ResourceLimits(idempotency_entries=1)
    cell = _memory_cell_with_widgets()
    ops1 = [{"operation": "insert", "values": {"label": "one"}}]
    cell.transact("widgets", ops1, tiny_limits, plan_request=_mutate_plan_request("widgets", ops1), idempotency_key="k1")
    assert len(cell._idempotency) == 1

    ops2 = [{"operation": "insert", "values": {"label": "two"}}]
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", ops2, tiny_limits, plan_request=_mutate_plan_request("widgets", ops2), idempotency_key="k2")
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert exc.value.details.get("limit_class") == "idempotency_entries"
    assert len(cell.entities["widgets"]) == 1, "the refused request must not have executed at all"
    assert len(cell._idempotency) == 1, "no new record was written either"


def test_condition_7b_expired_records_are_reclaimed_before_the_capacity_check() -> None:
    """I-6: 期限切れを回収してもなお満杯なら拒否 -- 逆に言えば、回収の結果
    空きができれば新規実行が通る。"""
    tiny_limits = ResourceLimits(idempotency_entries=1, idempotency_retention_ms=1)
    clock_value = [1000.0]
    cell = _memory_cell_with_widgets()
    ops1 = [{"operation": "insert", "values": {"label": "one"}}]
    cell.transact("widgets", ops1, tiny_limits, clock=lambda: clock_value[0], plan_request=_mutate_plan_request("widgets", ops1), idempotency_key="k1")
    clock_value[0] += 10.0  # far past the 1ms retention
    ops2 = [{"operation": "insert", "values": {"label": "two"}}]
    outcome = cell.transact("widgets", ops2, tiny_limits, clock=lambda: clock_value[0], plan_request=_mutate_plan_request("widgets", ops2), idempotency_key="k2")
    assert outcome.replayed is False
    assert len(cell._idempotency) == 1, "k1 was reclaimed, k2 took the single slot"
    assert "k2" in cell._idempotency


def test_condition_9_dry_run_never_consults_or_writes_a_record() -> None:
    """I-7: idempotency_key 付きの dry_run は記録も参照もしない -- 2 回の
    dry_run 呼び出しは共に committed=False で応答し、どちらも記録を残さな
    い (D-4)。"""
    cell = _memory_cell_with_widgets()
    ops = [{"operation": "insert", "values": {"label": "one"}}]
    outcome = cell.transact("widgets", ops, LIMITS, dry_run=True, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="k-dry")
    assert outcome.committed is False
    assert outcome.replayed is False
    assert cell._idempotency == {}
    assert cell.entities["widgets"] == []


# ===========================================================================
# Section 3: `DataService` (service.py) -- capability declaration, gate
# removal, and `plan` digest inclusion (I-10/I-12/I-13).
# ===========================================================================


def test_capability_idempotency_is_enabled_with_limits_declared_in_the_same_document() -> None:
    """完了条件 8/9: capability `idempotency` が `enabled` であり、同じ
    capability document に `limits.idempotency_entries`/
    `idempotency_retention_ms` と対応する `limit_enforcement` エントリが
    ある (C-05 V1 (e) の `_CAPABILITY_CONDITIONED` が要求する形)。"""
    service, _control = build_service()
    document = service.capabilities(runtime_context(service))
    assert document["capabilities"]["idempotency"] == {"status": "enabled"}
    assert "idempotency_entries" in document["limits"]
    assert "idempotency_retention_ms" in document["limits"]
    assert document["limit_enforcement"]["idempotency_entries"] == "enforced"
    # Ruling J-3 (WP-2cd audit N-3): a wall-clock DURATION, like
    # `execution_ms`, not a count -- `reference_wall_clock`, not `enforced`
    # (a retention window cannot be driven to a deterministic N/N+1
    # boundary within a bounded test run).
    assert document["limit_enforcement"]["idempotency_retention_ms"] == "reference_wall_clock"


def test_provisional_gate_is_removed_idempotency_key_is_accepted_not_rejected() -> None:
    """完了条件 9 (I-12): `idempotency_key` を伴う要求が
    CAPABILITY_UNSUPPORTED で拒否されない -- WP-1 の provisional gate は
    このコミットで撤去済みである。"""
    service, _control = build_service()
    context = runtime_context(service)
    result = service.mutate_result(context, "notes", [{"operation": "insert", "values": {"body": "x"}}], idempotency_key="gate-check")
    assert result.committed is True
    assert result.affected == 1


def test_replay_response_shape_matches_the_original_mutation() -> None:
    """I-8: replay 応答は記録した応答 object 全体 -- affected /
    assigned_addresses / committed が元の実行と一致する。"""
    service, _control = build_service()
    context = runtime_context(service)
    ops = [{"operation": "insert", "values": {"body": "hello"}}]
    first = service.mutate_result(context, "notes", ops, idempotency_key="svc-k1")
    second = service.mutate_result(context, "notes", list(ops), idempotency_key="svc-k1")
    assert second.committed == first.committed
    assert second.affected == first.affected
    assert second.assigned_addresses == first.assigned_addresses


def test_idempotency_key_is_included_in_the_plan_digest() -> None:
    """I-13: `idempotency_key` は plan の digest (`normalize_request_for_
    plan`) の対象に入る -- 同じ operations/entity/transaction でも key の
    有無で plan token が変わる。`normalize_request_for_idempotency`
    (idempotency 自身の digest) は逆に key を除く (この 2 関数は同じ dict
    に対して異なる結果を返す)。"""
    from r2db_api.structured import compute_plan_token, normalize_request_for_plan

    without_key = {"entity": "widgets", "operations": [{"operation": "insert", "values": {"label": "x"}}]}
    with_key = dict(without_key, idempotency_key="k1")
    assert normalize_request_for_plan(without_key) != normalize_request_for_plan(with_key)
    assert compute_plan_token(without_key, 0) != compute_plan_token(with_key, 0)
    # But the idempotency digest of `with_key` ignores `idempotency_key`
    # itself -- adding a DIFFERENT key to the identical body must not
    # change ITS OWN digest.
    with_other_key = dict(without_key, idempotency_key="k2")
    assert idempotency_digest(with_key) == idempotency_digest(with_other_key)


def test_service_plan_token_changes_with_idempotency_key_through_the_real_request_path() -> None:
    """Ruling J-1 (WP-2cd audit N-1, addendum I-13): fixes I-13's wiring
    THROUGH `DataService._mutate_outcome`'s own `plan_request` assembly
    (`service.py::DataService._mutate_outcome`'s `idempotency_key` branch), never by handing a hand-built dict straight
    to `normalize_request_for_plan`/`compute_plan_token` the way `test_
    idempotency_key_is_included_in_the_plan_digest` above does (that test
    fixes the HELPER; this one fixes the WIRING -- the monitor's own
    self-mutation, `service.py:1202-1203` turned into `if False:`, left
    that helper-level test, `r2db-api/tests` in full, and `test_c23_
    idempotency_semantics.py` all green; only a request-path test like
    this one goes red under that exact mutation).

    1. A `dry_run` WITHOUT `idempotency_key` gets plan token A.
    2. The identical `entity`/`operations` `dry_run` WITH `idempotency_
       key="k1"` gets plan token B -- `A != B` (G-1: `service.py` includes
       `idempotency_key` in `plan_request` only when the caller's own
       request object actually carried it).
    3. Token B, presented on the real (non-dry-run) request WITH
       `idempotency_key="k1"`, is honored (commits).
    4. Token B, presented WITHOUT `idempotency_key` (or with a different
       one), is refused `PRECONDITION_FAILED` -- fail-closed, never
       silently honored as if it were the no-key plan."""
    service, _control = build_service()
    runtime = runtime_context(service)
    operations = [{"operation": "insert", "values": {"body": "j1-wiring"}}]

    token_a = service.mutate_result(runtime, "notes", list(operations), dry_run=True).plan
    token_b = service.mutate_result(runtime, "notes", list(operations), dry_run=True, idempotency_key="k1").plan
    assert token_a is not None
    assert token_b is not None
    assert token_a != token_b, "the plan token must depend on whether idempotency_key was presented at all"

    # Step 3: the SAME key the plan was captured with -- honored, commits.
    committed = service.mutate_result(runtime, "notes", list(operations), plan=token_b, idempotency_key="k1")
    assert committed.committed is True
    assert committed.affected == 1

    # Step 4: token B presented WITHOUT idempotency_key -- fail-closed, no
    # second row (a silent "close enough" honor would double-insert).
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(runtime, "notes", list(operations), plan=token_b)
    assert exc.value.code == "PRECONDITION_FAILED"
    rows = [r for r in service.query(runtime, "notes", select=["id", "body"]) if r.get("body") == "j1-wiring"]
    assert len(rows) == 1, "the fail-closed PRECONDITION_FAILED resend must not have executed"


def test_service_omitted_budget_then_resend_with_empty_budget_is_conflict_through_the_real_request_path() -> None:
    """F-② (外部レビュー 2, 監督裁定 U-11), wiring-level pin -- mirrors
    `test_service_plan_token_changes_with_idempotency_key_through_the_
    real_request_path`'s own "fix the WIRING, not just the helper"
    rationale: drives `DataService._mutate_outcome`'s own `plan_request`
    assembly (`service.py::DataService._mutate_outcome`, `if budget is not None:`) through the
    real `mutate_result` entry point, rather than handing a hand-built
    `plan_request` straight to `cell.transact` the way `test_condition_3b_
    ...` above does."""
    service, _control = build_service()
    runtime = runtime_context(service)
    ops = [{"operation": "insert", "values": {"body": "budget-shape"}}]

    first = service.mutate_result(runtime, "notes", list(ops), idempotency_key="svc-budget-k1")
    assert first.committed is True

    with pytest.raises(FoundationError) as exc:
        service.mutate_result(runtime, "notes", list(ops), idempotency_key="svc-budget-k1", budget={})
    assert exc.value.code == "CONFLICT"
    assert exc.value.details == {"violated_declaration": "idempotency_key", "field": "idempotency_key"}
    rows = [r for r in service.query(runtime, "notes", select=["id", "body"]) if r.get("body") == "budget-shape"]
    assert len(rows) == 1, "the conflicting resend must not have executed"


def test_service_plan_digest_differs_between_omitted_and_empty_budget_through_the_real_request_path() -> None:
    """F-② companion: the plan token itself (not only the idempotency
    CONFLICT above) must differ between an omitted `budget` and a
    present-but-empty `budget: {}`, through the real `mutate_result`
    dry_run path (`service.py`'s own `plan_request` assembly, the SAME
    `if budget is not None:` line)."""
    service, _control = build_service()
    runtime = runtime_context(service)
    ops = [{"operation": "insert", "values": {"body": "budget-plan-shape"}}]

    plan_omitted = service.mutate_result(runtime, "notes", list(ops), dry_run=True).plan
    plan_empty_budget = service.mutate_result(runtime, "notes", list(ops), dry_run=True, budget={}).plan
    assert plan_omitted is not None
    assert plan_empty_budget is not None
    assert plan_omitted != plan_empty_budget, (
        "an omitted budget and an empty-but-present budget: {} must produce different plan digests"
    )


def test_audit_key_is_never_written_to_an_audit_event() -> None:
    """I-11: key を監査行に載せない。相関は request_id (2e で成立) --
    2c 時点では `_event`/`_make_audit_hook` に渡る `details`/フィールドの
    どこにも `idempotency_key` の値そのものが現れないことを実測する。
    destructive (`delete` + confirmation) mutation を使う -- 通常の
    `data_operation` allow event は buffer-class で durable sink に同期的
    には届かないため (D-4)、pre-commit hook が同期的に書く経路を使う。"""
    from r2db_api.structured import Predicate, delete_confirmation_phrase
    from test_application_audit import durable_events

    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    context = runtime_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)
    op = {"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}
    service.mutate_result(context, "notes", [op], idempotency_key="top-secret-key-value")
    events = durable_events(durable)
    assert len(events) >= 1, "test setup sanity check: at least one durable event must have been written"
    for event in events:
        assert "top-secret-key-value" not in repr(event)


def test_replay_of_a_destructive_delete_writes_its_own_audit_line() -> None:
    """Ruling J-4 (WP-2cd audit N-5, SI-14): a resend answered from the
    idempotency record still earns its OWN audit line -- a destructive
    `delete`'s replay must not return `committed: true` while leaving ZERO
    evidence of its own that this Application was touched at that time
    (SI-14's minimal "destructive schema/data operation" event class).
    Uses `ControlAuthority.audit_events()` (the legacy in-memory sink
    `_event` always appends to FIRST, unconditionally -- `service.py`'s own
    `_event` docstring) rather than the durable/buffered surface: this
    property must hold regardless of how the buffer-class routing beneath
    it behaves. The new row carries the REPLAY's own `request_id` (never
    the original), `outcome: "replayed"` (never `"allow"`), and -- like
    every event this method emits -- never the `idempotency_key` value
    itself (I-11)."""
    from r2db_api.structured import Predicate, delete_confirmation_phrase

    service, control = build_service()
    context = runtime_context(service)
    phrase = delete_confirmation_phrase("notes", [Predicate(field="id", operator="eq", value=1)], 0)
    op = {"operation": "delete", "where": [{"field": "id", "operator": "eq", "value": 1}], "destructive": True, "confirmation": phrase}

    first = service.mutate_result(context, "notes", [op], idempotency_key="k-replay-audit", request_id="rid-original")
    assert first.committed is True
    before = len(control.audit_events())

    second = service.mutate_result(context, "notes", [dict(op)], idempotency_key="k-replay-audit", request_id="rid-replay")
    assert second.committed is True
    after = control.audit_events()
    assert len(after) == before + 1, "the destructive replay must add EXACTLY one audit row"

    new_events = [event for event in after if event.get("request_id") == "rid-replay"]
    assert len(new_events) == 1
    event = new_events[0]
    assert event["outcome"] == "replayed"
    assert event["operation"] == "mutate"
    assert "k-replay-audit" not in repr(event)


def test_declared_audit_outcomes_include_replayed() -> None:
    """Ruling J-4 (WP-2cd audit N-5): the peer-local `outcome` vocabulary
    pin (`audit_query.py`'s `DECLARED_AUDIT_OUTCOMES`) includes `"replayed"`
    -- fixed against every real `outcome=` literal in `src/r2db_api/` by
    the SAME generalized AST scanner `test_audit_query.py`'s own
    `DECLARED_AUDIT_OPERATIONS`/`_TARGET_KINDS`/`_EVENT_CLASSES` tests use,
    so a future new `outcome=` word left undeclared here is caught, not
    silently permitted."""
    from r2db_api.audit_query import DECLARED_AUDIT_OUTCOMES
    from test_audit_query import _field_literal_union, _iter_src_files

    assert "replayed" in DECLARED_AUDIT_OUTCOMES
    emitted = _field_literal_union(_iter_src_files(), "outcome")
    assert emitted, "the AST scanner found zero outcome literals -- it is itself broken"
    assert emitted == DECLARED_AUDIT_OUTCOMES, (
        f"emittable-vs-declared mismatch: emitted but not declared: {emitted - DECLARED_AUDIT_OUTCOMES!r}; "
        f"declared but never actually emitted: {DECLARED_AUDIT_OUTCOMES - emitted!r}"
    )


# ===========================================================================
# Section 4: `PostgresCell` (real PostgreSQL, §5.3 C-5) -- I-1/U-3 = (A):
# the side table, written in the SAME transaction as the data effects.
# ===========================================================================


def test_postgres_record_is_written_in_the_same_transaction_as_the_data(app_a) -> None:  # noqa: F811
    """完了条件 1 realized against the real side table: a failed attempt
    (second op writes a non-string value to a `string`-typed field) leaves
    no row in `_r2db_idempotency`, and the entity table itself is
    unchanged."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "pgwidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )

        import psycopg

        def _row_count() -> int:
            with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM public._r2db_idempotency")
                    return cur.fetchone()[0]

        failing_ops = [{"operation": "insert", "values": {"label": "one"}}, {"operation": "insert", "values": {"label": 123}}]
        with pytest.raises(FoundationError):
            cell.transact(
                "pgwidgets", failing_ops, LIMITS,
                plan_request={"entity": "pgwidgets", "operations": failing_ops}, idempotency_key="pg-k1",
            )
        assert _row_count() == 0, "a failed attempt must leave no row in the side table"

        ok_ops = [{"operation": "insert", "values": {"label": "one"}}]
        # M-6 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): a
        # request_id-bearing record, so the replay below is genuine (a
        # request_id-less record is treated as absent).
        outcome = cell.transact("pgwidgets", ok_ops, LIMITS, plan_request={"entity": "pgwidgets", "operations": ok_ops}, idempotency_key="pg-k1", request_id="rid-pg-1")
        assert outcome.replayed is False
        assert _row_count() == 1

        replay = cell.transact("pgwidgets", ok_ops, LIMITS, plan_request={"entity": "pgwidgets", "operations": ok_ops}, idempotency_key="pg-k1", request_id="rid-pg-2")
        assert replay.replayed is True
        assert _row_count() == 1, "a replay must not add a second row"
    finally:
        cell.close()


def test_postgres_execution_failure_releases_lock_for_a_new_execution(app_a) -> None:  # noqa: F811
    """Code-review fix F4 (Opus review 2, WP-6d rework, should-fix): after
    a keyed request FAILS during EXECUTION (the idempotency lookup
    already found no record, and a real backend write was attempted and
    rolled back -- the SAME "second op writes a non-string value" shape
    the test above uses, not merely a pass-1 request-shape refusal), the
    SAME key's next request must execute as a brand-new request: success,
    its own `request_id`, exactly one row's worth of effect
    (`affected == 1`) -- never a replay, never a hang.

    For r2db-api this outcome is guaranteed by construction: `_idempotency
    _key_lock` is a `pg_advisory_xact_lock` (`postgres.py`), released
    AUTOMATICALLY at ROLLBACK regardless of which connection took it --
    unlike MitateDB-api's session-scoped `pg_advisory_lock`, there is no
    separate `idempotency_unlock` call here that could be skipped on a
    failure path (nothing analogous to F1/F3's own MitateDB-specific
    bugs is even structurally possible on this peer). This test is the
    direct evidence for that guarantee on the real database, over a
    cell with a real connection pool (`pool_size=2`, `make_cell`'s own
    default) -- not merely an inference from the lock TYPE."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "fwidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )

        import psycopg

        def _row_count() -> int:
            with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM public.fwidgets")
                    return cur.fetchone()[0]

        key = "f4-pg-rollback-1"
        failing_ops = [{"operation": "insert", "values": {"label": "one"}}, {"operation": "insert", "values": {"label": 123}}]
        with pytest.raises(FoundationError):
            cell.transact(
                "fwidgets", failing_ops, LIMITS,
                plan_request={"entity": "fwidgets", "operations": failing_ops}, idempotency_key=key,
            )
        assert _row_count() == 0, "the failed attempt's own tentative insert must have rolled back"

        ok_ops = [{"operation": "insert", "values": {"label": "two"}}]
        retried = cell.transact(
            "fwidgets", ok_ops, LIMITS, plan_request={"entity": "fwidgets", "operations": ok_ops},
            idempotency_key=key, request_id="rid-f4-pg-retry",
        )
        assert retried.replayed is False, "the same key, presented after a failed attempt, must be a NEW execution"
        assert retried.affected == 1
        assert retried.request_id == "rid-f4-pg-retry"
        assert _row_count() == 1
    finally:
        cell.close()


def _pg_strip_request_id(dsn: str, key: str) -> None:
    """Simulates the pre-1.7.0 `_r2db_idempotency` row shape directly
    against the real side table: strips `request_id` from the stored
    `response` jsonb for `key`, exactly what a record written before
    contract 1.7.0 would already look like on disk."""
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT response FROM public._r2db_idempotency WHERE idempotency_key = %s", (key,))
            (payload,) = cur.fetchone()
            del payload["request_id"]
            cur.execute("UPDATE public._r2db_idempotency SET response = %s WHERE idempotency_key = %s", (Jsonb(payload), key))


def _pg_stored_payload(dsn: str, key: str) -> dict:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT response FROM public._r2db_idempotency WHERE idempotency_key = %s", (key,))
            (payload,) = cur.fetchone()
            return payload


def test_postgres_replay_of_a_pre_1_7_0_record_is_treated_as_absent_and_re_executes(app_a) -> None:  # noqa: F811
    """WP-2e closure audit R-1 (`{scratchpad}/audit-wp2e-2.md`, ruling
    M-6): the real-`PostgresCell` mirror of `test_denial_details_and_
    request_id.py::test_idempotency_replay_of_a_pre_1_7_0_record_is_
    treated_as_absent_and_re_executes` -- M-6 point 4 ("postgres.py 側も
    同じ規律にすること") demands the SAME behaviour hold against the real
    side table, not only the in-memory dict."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "pgpre170", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        ops = [{"operation": "insert", "values": {"label": "one"}}]
        first = cell.transact("pgpre170", ops, LIMITS, plan_request={"entity": "pgpre170", "operations": ops}, idempotency_key="pg-pre170-key", request_id="rid-pg-pre170-1")
        assert first.replayed is False
        assert first.request_id == "rid-pg-pre170-1"

        _pg_strip_request_id(app_a.developer_dsn, "pg-pre170-key")
        assert "request_id" not in _pg_stored_payload(app_a.developer_dsn, "pg-pre170-key")

        second = cell.transact("pgpre170", ops, LIMITS, plan_request={"entity": "pgpre170", "operations": ops}, idempotency_key="pg-pre170-key", request_id="rid-pg-pre170-2")
        assert second.replayed is False, "a request_id-less record must be treated as absent -- a genuine re-execution, never a replay"
        assert second.request_id == "rid-pg-pre170-2"
        assert second.request_id != first.request_id
        # M-6: a REAL second insert, not a replay of the first's own
        # recorded result -- a distinct row address is the decisive proof.
        assert second.assigned_addresses != first.assigned_addresses

        # M-6 point 3: the new execution's result OVERWRITES the same
        # key's row (the `ON CONFLICT (idempotency_key) DO UPDATE` this
        # WP added to `_idempotency_store`) -- a request_id-less row is
        # not left behind forever, and this INSERT does not raise a
        # primary-key violation despite the row already existing.
        overwritten = _pg_stored_payload(app_a.developer_dsn, "pg-pre170-key")
        assert overwritten["request_id"] == "rid-pg-pre170-2"
    finally:
        cell.close()


def test_postgres_resend_of_a_request_id_less_record_with_a_different_digest_re_executes_rather_than_conflicting(app_a) -> None:  # noqa: F811
    """M-6 (R-1 point 2), Postgres-plug mirror: a request_id-less record
    is excluded from the digest comparison entirely -- checked BEFORE it,
    not after -- so a resend under the SAME key but a DIFFERENT request
    body must NOT raise `CONFLICT` against the real side table either."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "pgpre170b", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        ops_a = [{"operation": "insert", "values": {"label": "original"}}]
        first = cell.transact("pgpre170b", ops_a, LIMITS, plan_request={"entity": "pgpre170b", "operations": ops_a}, idempotency_key="pg-pre170b-key", request_id="rid-pg-pre170b-1")

        _pg_strip_request_id(app_a.developer_dsn, "pg-pre170b-key")

        # A DIFFERENT body -> a different idempotency digest than the
        # record (still) carries -- would be CONFLICT if the record were
        # honoured.
        ops_b = [{"operation": "insert", "values": {"label": "different-body-should-not-conflict"}}]
        second = cell.transact("pgpre170b", ops_b, LIMITS, plan_request={"entity": "pgpre170b", "operations": ops_b}, idempotency_key="pg-pre170b-key", request_id="rid-pg-pre170b-2")
        assert second.replayed is False
        assert second.request_id == "rid-pg-pre170b-2"
        assert second.assigned_addresses != first.assigned_addresses
    finally:
        cell.close()


def test_postgres_upgrade_11_not_applied_fails_closed_at_lookup_before_execution(app_a, monkeypatch) -> None:  # noqa: F811
    """Ruling J-5 (WP-2cd audit N-6): an application that has never run
    upgrade `11` (`public._r2db_idempotency` missing) gets `SERVICE_
    UNAVAILABLE` for an `idempotency_key`-carrying request at the LOOKUP
    stage -- before target-existence/execution, with NO row added to the
    entity table (fail-closed, no execution cost paid first). Drops the
    real side table (never restored -- unlike `test_ops_declarations.py`'s
    module-scoped `platform` fixture that its own analogous test must put
    back, `app_a` here is function-scoped: `deprovision_app` drops this
    entire per-test database in its own `finally` block regardless of this
    table's state, so there is nothing further to protect) rather than
    provisioning a whole second Application that has genuinely never run
    upgrade 11 -- `app_a`'s own already-applied upgrade 11 is otherwise
    indistinguishable from one that was never applied, from `_idempotency_
    lookup`'s own point of view, once the table itself is gone.

    The FINAL error code and row count alone do NOT distinguish this fix
    from the pre-J-5 behavior: without it, `_idempotency_lookup` swallowed
    `UndefinedTable` into "no record", execution proceeded (catalog load,
    the real INSERT), and `_idempotency_store` then hit the SAME
    `UndefinedTable` at COMMIT time, unwinding the whole transaction back
    to the SAME `SERVICE_UNAVAILABLE` + 0 rows (confirmed empirically: this
    exact test, with the pre-fix `_idempotency_lookup` restored, still
    passes on those two assertions alone -- N-6's own "実行費用を払ってから"
    point exactly). What DOES distinguish them is real `_run()` dispatch
    count before the failure -- counted the same way `{scratchpad}/
    rtplugin.py`/`test_postgres_keyed_write_round_trip_count_after_
    removing_the_redundant_delete` above do: the fix fails after ONLY
    `_set_timeouts`'s 2 SET LOCAL statements + the lookup's own 2
    statements (`DELETE`+`SELECT`) -- 4 total, identical to a keyed
    REPLAY's own cost -- never reaching catalog load or the INSERT at all
    (measured directly at 10 `_run()` calls with the pre-fix behavior
    restored)."""
    import psycopg
    from psycopg import sql as psycopg_sql
    import r2db_api.postgres as pg_module

    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "j5widgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )

        def _row_count(table: str) -> int:
            with psycopg.connect(app_a.developer_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT count(*) FROM public.{table}")
                    return cur.fetchone()[0]

        with psycopg.connect(app_a.developer_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(psycopg_sql.SQL("DROP TABLE {table}").format(table=psycopg_sql.Identifier("_r2db_idempotency")))
            conn.commit()

        counts = {"n": 0}
        orig_run = pg_module._run

        def counting_run(cur, *args, **kwargs):
            counts["n"] += 1
            return orig_run(cur, *args, **kwargs)

        monkeypatch.setattr(pg_module, "_run", counting_run)

        ops = [{"operation": "insert", "values": {"label": "one"}}]
        with pytest.raises(FoundationError) as exc:
            cell.transact("j5widgets", ops, LIMITS, plan_request={"entity": "j5widgets", "operations": ops}, idempotency_key="j5-k1")
        assert exc.value.code == "SERVICE_UNAVAILABLE"
        assert counts["n"] == 5, (
            f"_run() dispatch count before the failure: {counts['n']} (expected 5 -- `_set_timeouts`'s own 2 SET LOCAL "
            f"statements + ruling U-7's own `_idempotency_key_lock` (WP-6d, {{scratchpad}}/review2/frame.md F-①: one "
            f"`pg_advisory_xact_lock` dispatch, taken BEFORE the lookup) + the lookup's own DELETE+SELECT, matching a "
            f"keyed REPLAY's identical 5-statement cost (was 4 before WP-6d); a value near/above 10 means catalog load "
            f"and/or the INSERT ran first too, i.e. the pre-J-5 execute-then-roll-back path -- measured directly: 10, "
            f"with `_idempotency_lookup`'s old `UndefinedTable`-swallowing restored)"
        )
        assert _row_count("j5widgets") == 0, "the fail-closed request must not have executed at all -- no row growth"
    finally:
        cell.close()


def test_postgres_keyed_write_round_trip_count_after_removing_the_redundant_delete(app_a, monkeypatch) -> None:  # noqa: F811
    """Ruling J-6 (WP-2cd audit N-7): `_idempotency_reserve`'s own
    lazy-reclaim DELETE (a second one on this same path, always 0 rows --
    `_idempotency_lookup`, same transaction, already ran the first one
    moments earlier) is removed. Counts real `postgres._run()` dispatch
    calls (the same technique `{scratchpad}/rtplugin.py` used for the
    audit's own P-8 measurement) for one keyed WRITE (a new record, no
    prior row) and one keyed REPLAY, pinning both exactly -- a mutation
    that re-introduces the DELETE turns the write assertion red (12, not
    11; verified directly by re-adding it and re-running this same test:
    `{scratchpad}/j6-verify-backup/` is that mutation's own cp/sha256
    restore point). This scenario's own absolute counts (11/4) differ from
    the audit's own reported baseline (10/4, a different insert scenario)
    -- what this test pins is the DELTA the fix produces (-1 on the write
    leg), measured directly against ITS OWN mutation, not a cross-scenario
    absolute number. The replay assertion (never calls `_idempotency_
    reserve` at all, since it returns before reaching it) stays at 4
    either way, pinned here as a non-regression contrast."""
    import r2db_api.postgres as pg_module

    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "rtwidgets", "fields": ["label"], "field_types": {"label": "string"}},
            developer=True, limits=LIMITS,
        )
        counts = {"n": 0}
        orig_run = pg_module._run

        def counting_run(cur, *args, **kwargs):
            counts["n"] += 1
            return orig_run(cur, *args, **kwargs)

        monkeypatch.setattr(pg_module, "_run", counting_run)

        ops = [{"operation": "insert", "values": {"label": "one"}}]
        counts["n"] = 0
        # M-6: request_id-bearing, so the replay leg below is genuine.
        outcome = cell.transact("rtwidgets", ops, LIMITS, plan_request={"entity": "rtwidgets", "operations": ops}, idempotency_key="rt-k1", request_id="rid-rt-1")
        assert outcome.replayed is False
        # Ruling U-7 (WP-6d, `{scratchpad}/review2/frame.md` F-①): +2 over
        # J-6's own 11 -- `_idempotency_key_lock` (before the lookup) and
        # `_idempotency_reserve_lock` (before the reserve-stage COUNT), one
        # `pg_advisory_xact_lock` dispatch each, both taken on a genuine
        # (non-replay) keyed write. Measured directly (13), matching J-6's
        # own "measure the delta, do not guess" convention.
        # R-120: +1 over WP-6d's 13 -- `_lock_entities` (the entity lock, SHARED), one `pg_advisory_xact_lock_shared` dispatch for the one entity, between the lookup and the count lock. Measured directly (14).
        # R-82: +1 over R-120's 14 -- the catalog token read (`_read_catalog_token`), one dispatch on this first request of the cell (an empty catalog cache: the live catalog is read as before). Measured directly (15).
        assert counts["n"] == 15, f"keyed write round trips: {counts['n']} (expected 15 after WP-6d's own 2 advisory-lock dispatches, R-120's entity-lock dispatch and R-82's catalog token read; 11 before them, per J-6)"

        counts["n"] = 0
        replay = cell.transact("rtwidgets", ops, LIMITS, plan_request={"entity": "rtwidgets", "operations": ops}, idempotency_key="rt-k1", request_id="rid-rt-2")
        assert replay.replayed is True
        # Ruling U-7: +1 over J-6's own 4 -- `_idempotency_key_lock` runs
        # even for a replay (it must, to serialize against a CONCURRENT
        # writer for this same key); `_idempotency_reserve_lock` still
        # does not (a replay returns before ever reaching the reserve
        # stage, unchanged from J-6).
        assert counts["n"] == 5, f"replay round trips: {counts['n']} (expected 5 after WP-6d's own 1 advisory-lock dispatch; 4 before it, per J-6 -- a replay never reaches _idempotency_reserve either way)"
    finally:
        cell.close()
