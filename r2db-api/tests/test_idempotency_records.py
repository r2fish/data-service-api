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
    first = cell.transact("widgets", ops, LIMITS, plan_request=plan_request, idempotency_key="k1")
    assert first.replayed is False
    assert first.affected == 1
    assert len(cell.entities["widgets"]) == 1

    second = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="k1")
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
    cell.transact("widgets", ops_a, LIMITS, plan_request=_mutate_plan_request("widgets", ops_a), idempotency_key="k1")

    ops_b = [{"operation": "insert", "values": {"label": "two"}}]
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", ops_b, LIMITS, plan_request=_mutate_plan_request("widgets", ops_b), idempotency_key="k1")
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
    first = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=plan_request, idempotency_key="k-drop")
    assert first.committed is True
    assert "gadgets" not in cell.entities

    # Resend the IDENTICAL operation object -- the entity is gone and the
    # confirmation phrase (computed from schema_revision) is now stale --
    # yet the resend must answer from the record, never NOT_FOUND/
    # DESTRUCTIVE_CONFIRMATION_REQUIRED.
    second = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-drop")
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
    first = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="shared-key")
    second = cell.transact("widgets", ops, LIMITS, plan_request=_mutate_plan_request("widgets", ops), idempotency_key="shared-key")
    assert second.replayed is True
    assert second.affected == first.affected
    assert len(cell.entities["widgets"]) == 1


def test_condition_6_applies_to_schema_operation_request() -> None:
    """完了条件 6: SchemaOperationRequest にも適用される -- 同一 key の
    2 回目の create_entity は再実行されず、元の revision を返す。"""
    cell = ApplicationCell(application_id="app-mem")
    op = {"operation": "create_entity", "entity": "sprockets", "fields": ["label"]}
    plan_request = {key: value for key, value in op.items() if key not in ("plan", "dry_run")}
    first = cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-create")
    assert first.replayed is False
    assert first.committed is True

    second = cell.apply_schema(dict(op), developer=True, limits=LIMITS, plan_request=dict(plan_request), idempotency_key="k-create")
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
    assert document["limit_enforcement"]["idempotency_retention_ms"] == "enforced"


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
        outcome = cell.transact("pgwidgets", ok_ops, LIMITS, plan_request={"entity": "pgwidgets", "operations": ok_ops}, idempotency_key="pg-k1")
        assert outcome.replayed is False
        assert _row_count() == 1

        replay = cell.transact("pgwidgets", ok_ops, LIMITS, plan_request={"entity": "pgwidgets", "operations": ok_ops}, idempotency_key="pg-k1")
        assert replay.replayed is True
        assert _row_count() == 1, "a replay must not add a second row"
    finally:
        cell.close()
