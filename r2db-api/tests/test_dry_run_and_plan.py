"""Contract 1.7.0 R-4 (`dry_run` + stateless `plan`) -- design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-4, work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-2b.

Peer-local coverage underneath `conformance-tests/test_c22_dry_run_and_
plan.py`'s own cross-peer decision-agreement/external-effect-absence/plan
test: this file exercises `ApplicationCell` (in-memory) and `PostgresCell`
(real PostgreSQL) directly for the tx-exit-point mechanics C-22 cannot see
from outside (the plan digest/token helpers themselves, the single-exit
commit/rollback decision, `_next_id` snapshot/restore during a schema dry
run), and `DataService`/the HTTP boundary for the service-layer decisions
(audit-hook non-construction, capability gate removal, `assigned_addresses`
omission, `committed`/`plan` response shape).

Real PostgreSQL throughout the `PostgresCell` half (§5.3 C-5, matching
`tests/test_postgres.py`'s own convention): reuses that file's own
`app_a`/`make_cell` module fixtures directly (imported, not duplicated).
"""
from __future__ import annotations

import hashlib
from typing import Any

import pytest

from r2db_api.audit import ApplicationAuditSink
from r2db_api.errors import FoundationError
from r2db_api.limits import ResourceLimits
from r2db_api.postgres import PostgresCell
from r2db_api.structured import (
    ApplicationCell,
    Predicate,
    compute_plan_token,
    delete_confirmation_phrase,
    drop_entity_confirmation_phrase,
    normalize_request_for_plan,
)

from test_application_audit import build_service, developer_context, durable_events, runtime_context
from test_postgres import app_a, make_cell, platform  # noqa: F401 (fixtures)

LIMITS = ResourceLimits()


def _memory_cell_with_widgets() -> ApplicationCell:
    cell = ApplicationCell(application_id="app-mem")
    cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"]}, developer=True, limits=LIMITS)
    return cell


# ===========================================================================
# Section 1: the shared digest/plan helpers themselves (`structured.py`).
# ===========================================================================


def test_normalize_request_for_plan_excludes_plan_and_dry_run_only() -> None:
    """S-a: the two keys `plan`/`dry_run` are dropped; every other key
    (including one this helper has never seen before) survives."""
    request = {"operations": [{"operation": "insert"}], "transaction": "atomic", "budget": {"batch_items": 1}, "plan": "stale-token", "dry_run": True}
    normalized = normalize_request_for_plan(request)
    assert b'"plan"' not in normalized
    assert b'"dry_run"' not in normalized
    assert b'"operations"' in normalized
    assert b'"transaction"' in normalized
    assert b'"budget"' in normalized


def test_normalize_request_for_plan_is_key_order_independent() -> None:
    """S-a: `sort_keys=True` -- two dicts with the identical content but
    different insertion order normalize to the identical bytes."""
    a = {"operations": [1, 2], "transaction": "atomic", "budget": {"batch_items": 1}}
    b = {"budget": {"batch_items": 1}, "transaction": "atomic", "operations": [1, 2]}
    assert normalize_request_for_plan(a) == normalize_request_for_plan(b)


def test_normalize_request_for_plan_has_no_insignificant_whitespace_and_keeps_non_ascii() -> None:
    """S-a: no whitespace after `,`/`:`; non-ASCII left un-escaped (`ensure_ascii=False`)."""
    normalized = normalize_request_for_plan({"operations": [{"a": 1, "b": 2}], "label": "café"})
    assert b", " not in normalized
    assert b": " not in normalized
    assert "café".encode("utf-8") in normalized
    assert b"\\u00e9" not in normalized  # the escaped form must NOT appear


def test_compute_plan_token_is_deterministic_and_sensitive_to_both_inputs() -> None:
    """D-4 (7): identical request+revision -> identical token; changing
    EITHER input alone changes it."""
    request = {"operations": [{"operation": "insert", "values": {"label": "x"}}], "transaction": "atomic"}
    token = compute_plan_token(request, 3)
    assert compute_plan_token(dict(request), 3) == token
    assert compute_plan_token({**request, "transaction": "best_effort"}, 3) != token
    assert compute_plan_token(request, 4) != token


def test_compute_plan_token_format_is_sha256hex_dot_revision() -> None:
    """Review round F-7/G-3 (`{scratchpad}/rulings-r4.md`): the token
    format is FIXED as `"<sha256hex>.<schema_revision>"`, one literal
    `.` separating a 64-hex-digit sha256 of `normalize_request_for_plan`
    from the decimal schema revision -- pinned byte-for-byte here rather
    than only exercised indirectly through determinism/sensitivity."""
    request = {"operations": [{"operation": "insert", "values": {"label": "x"}}], "transaction": "atomic"}
    token = compute_plan_token(request, 7)
    expected_digest = hashlib.sha256(normalize_request_for_plan(request)).hexdigest()
    assert token == f"{expected_digest}.7"
    digest_part, _, revision_part = token.partition(".")
    assert len(digest_part) == 64
    assert all(c in "0123456789abcdef" for c in digest_part)
    assert revision_part == "7"


def test_schema_plan_digest_covers_constraint_and_destructive_fields() -> None:
    """G-1 (`{scratchpad}/rulings-r4.md` addendum): the plan digest is the
    contract-level request object AS RECEIVED -- `field_constraints`/
    `enum`/`nullable` (constraint-declaration keys, WP-2a) and
    `destructive`/`confirmation` (the destructive-confirmation pair a
    `drop_entity`/`delete_field` schema operation carries) each change
    the digest on their own, proving none of them is silently dropped
    before `normalize_request_for_plan` sees the object -- not merely
    `operation`/`entity`/`field` as `test_compute_plan_token_...` above
    already covers for the mutation side."""
    base = {
        "operation": "add_field", "entity": "widgets", "field": "status", "field_type": "string",
        "field_constraints": {"enum": ["a", "b"], "nullable": False},
    }
    token = compute_plan_token(base, 1)
    assert compute_plan_token({**base, "field_constraints": {"enum": ["a", "c"], "nullable": False}}, 1) != token
    assert compute_plan_token({**base, "field_constraints": {"enum": ["a", "b"], "nullable": True}}, 1) != token

    destructive_base = {"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": "drop widgets"}
    destructive_token = compute_plan_token(destructive_base, 1)
    assert compute_plan_token({**destructive_base, "destructive": False}, 1) != destructive_token
    assert compute_plan_token({**destructive_base, "confirmation": "drop something-else"}, 1) != destructive_token


def test_mutation_plan_digest_uses_contract_item_shape_and_no_default_for_values() -> None:
    """H-2 (`{scratchpad}/rulings-r4.md` addendum 2): each element of
    `operations` is digested in the contract `Mutation`/`ScopedMutation`
    key shape -- `operation`/`values`/`where`/`expected_revision`/
    `destructive`/`confirmation` -- exactly as received, never this
    peer's own internal item shape (`type`/`filters`/`confirm`), and
    `values` is never defaulted: an operation item that OMITS `values`
    digests differently from one that carries `values: {}` explicitly."""
    omitted = {"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}]}]}
    empty = {"operations": [{"operation": "update", "where": [{"field": "id", "operator": "eq", "value": 1}], "values": {}}]}
    assert compute_plan_token(omitted, 1) != compute_plan_token(empty, 1)
    # Contract key names survive verbatim in the normalized bytes -- proof
    # this is the `Mutation` shape, not a peer-internal translation of it.
    normalized = normalize_request_for_plan({"operations": [{"operation": "insert", "values": {"a": 1}, "expected_revision": "5"}]})
    assert b'"operation"' in normalized
    assert b'"values"' in normalized
    assert b'"expected_revision"' in normalized


def test_schema_plan_digest_distinguishes_omitted_field_type_from_explicit_json() -> None:
    """H-3 (`{scratchpad}/rulings-r4.md` addendum 2): the schema digest
    never fills in `field_type`'s own default -- an `add_field` request
    that OMITS `field_type` (falls back to the `json` type at apply time,
    per the contract's own `field_types` description) digests differently
    from one that spells `field_type: "json"` explicitly, even though both
    apply identically."""
    base = {"operation": "add_field", "entity": "widgets", "field": "extra"}
    omitted_token = compute_plan_token(base, 1)
    explicit_json_token = compute_plan_token({**base, "field_type": "json"}, 1)
    assert omitted_token != explicit_json_token


def test_schema_plan_digest_covers_keys_this_operation_never_reads() -> None:
    """H-3: a key this peer's `apply_schema` never reads for a given
    operation (`index`/`unique`/`revision` on `add_field`, `destructive`/
    `confirmation` on a non-destructive operation) still changes the
    digest -- the digest commits to the request object AS RECEIVED, never
    to only the subset of keys this operation happens to consume."""
    base = {"operation": "add_field", "entity": "widgets", "field": "extra", "field_type": "string"}
    token = compute_plan_token(base, 1)
    assert compute_plan_token({**base, "index": "some_index"}, 1) != token
    assert compute_plan_token({**base, "unique": True}, 1) != token
    assert compute_plan_token({**base, "revision": "42"}, 1) != token
    assert compute_plan_token({**base, "destructive": True}, 1) != token
    assert compute_plan_token({**base, "confirmation": "whatever"}, 1) != token


# ===========================================================================
# Section 2: `ApplicationCell.transact` -- mutation-side dry_run/plan.
# ===========================================================================


def test_memory_dry_run_reaches_the_same_refusal_as_the_real_request() -> None:
    """Completion condition 1: a request this test constructs so it is
    refused regardless of `dry_run` (a filter with an incompatible value
    type) returns the SAME code both ways."""
    cell = _memory_cell_with_widgets()
    op = {"operation": "update", "where": [{"field": "id", "operator": "eq", "value": "not-an-int"}], "values": {"label": "y"}}
    with pytest.raises(FoundationError) as dry_exc:
        cell.transact("widgets", [op], LIMITS, dry_run=True)
    with pytest.raises(FoundationError) as real_exc:
        cell.transact("widgets", [op], LIMITS, dry_run=False)
    assert dry_exc.value.code == real_exc.value.code == "VALIDATION_FAILED"


def test_memory_dry_run_affected_matches_real_and_reports_committed_false() -> None:
    """Completion condition 2."""
    cell = _memory_cell_with_widgets()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "a"}}, {"operation": "insert", "values": {"label": "b"}}], LIMITS)
    update_op = {"operation": "update", "where": [{"field": "id", "operator": "gt", "value": 0}], "values": {"label": "z"}}
    dry = cell.transact("widgets", [update_op], LIMITS, dry_run=True)
    assert dry.committed is False
    real = cell.transact("widgets", [update_op], LIMITS, dry_run=False)
    assert dry.affected == real.affected == 2


def test_memory_dry_run_leaves_rows_unchanged_but_may_consume_the_id_sequence() -> None:
    """Completion condition 3 (rows unchanged; row content is the
    observable half of "外部可視の状態変化 0" this level can see -- audit/
    capability declaration are `DataService`-level, Section 5 below).

    WP-2b 監査 N-6(a) (`{scratchpad}/audit-wp2b.md`): the pre-fix name of
    this test additionally claimed the `_next_id` sequence position was
    "reported unchanged", but no assertion here ever touched `_next_id` at
    all -- and a DATA mutation dry run is explicitly permitted to consume
    it (F-15), unlike a SCHEMA dry run, which `test_memory_schema_dry_run_
    does_not_consume_the_id_sequence` above pins as snapshotted/restored.
    This version asserts the real behaviour instead of the misleading
    name: rows are unchanged, but the dry run's own `assigned_addresses`
    (this cell-level return value, never the `DataService` response,
    which omits the key entirely -- `test_service_mutate_result_dry_run_
    response_omits_assigned_addresses` below) DOES carry the id it
    consumed, and a REAL insert straight after gets the NEXT id, not a
    reused one."""
    cell = _memory_cell_with_widgets()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "a"}}], LIMITS)
    before = [dict(row) for row in cell.entities["widgets"]]
    dry = cell.transact("widgets", [{"operation": "insert", "values": {"label": "dry"}}], LIMITS, dry_run=True)
    after = [dict(row) for row in cell.entities["widgets"]]
    assert after == before
    assert dry.assigned_addresses[0]["address"]["id"] == 2
    real = cell.transact("widgets", [{"operation": "insert", "values": {"label": "b"}}], LIMITS)
    assert real.assigned_addresses[0]["address"]["id"] == 3


def test_memory_dry_run_plan_is_deterministic_across_two_calls() -> None:
    """Completion condition 6."""
    cell = _memory_cell_with_widgets()
    request = {"operations": [{"operation": "insert", "values": {"label": "a"}}], "transaction": "atomic"}
    dry1 = cell.transact("widgets", request["operations"], LIMITS, dry_run=True, plan_request=request)
    dry2 = cell.transact("widgets", request["operations"], LIMITS, dry_run=True, plan_request=request)
    assert dry1.plan and dry1.plan == dry2.plan


def test_memory_plan_valid_lets_the_real_request_through() -> None:
    """Completion condition (plan validity, D-4 (2)): the same plan
    against unchanged schema is honored."""
    cell = _memory_cell_with_widgets()
    operations = [{"operation": "insert", "values": {"label": "a"}}]
    request = {"operations": operations, "transaction": "atomic"}
    plan = cell.transact("widgets", operations, LIMITS, dry_run=True, plan_request=request).plan
    real = cell.transact("widgets", operations, LIMITS, plan=plan, plan_request=request)
    assert real.committed is True
    assert real.affected == 1
    assert [row["label"] for row in cell.entities["widgets"]] == ["a"]


def test_memory_plan_mismatch_on_different_body_is_precondition_failed() -> None:
    """Completion condition 7 (digest's own request scope): a plan taken
    for one body, presented with a different body."""
    cell = _memory_cell_with_widgets()
    operations_a = [{"operation": "insert", "values": {"label": "a"}}]
    plan = cell.transact("widgets", operations_a, LIMITS, dry_run=True, plan_request={"operations": operations_a, "transaction": "atomic"}).plan
    operations_b = [{"operation": "insert", "values": {"label": "b"}}]
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", operations_b, LIMITS, plan=plan, plan_request={"operations": operations_b, "transaction": "atomic"})
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}
    assert cell.entities["widgets"] == []


def test_memory_plan_digest_covers_budget_not_only_operations() -> None:
    """Completion condition 7 (digest scope, C-22 (10)): a `budget`-only
    change under the SAME operations/transaction is also refused --
    proof the digest is not `operations`-only."""
    cell = _memory_cell_with_widgets()
    operations = [{"operation": "insert", "values": {"label": "a"}}]
    plan = cell.transact("widgets", operations, LIMITS, dry_run=True, plan_request={"operations": operations, "transaction": "atomic"}).plan
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", operations, LIMITS, plan=plan, plan_request={"operations": operations, "transaction": "atomic", "budget": {"execution_ms": 1}})
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}


def test_memory_plan_staleness_after_a_schema_change() -> None:
    """Completion condition 8: a plan taken before a schema change,
    presented after it."""
    cell = _memory_cell_with_widgets()
    operations = [{"operation": "insert", "values": {"label": "a"}}]
    request = {"operations": operations, "transaction": "atomic"}
    plan = cell.transact("widgets", operations, LIMITS, dry_run=True, plan_request=request).plan
    cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "extra"}, developer=True, limits=LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", operations, LIMITS, plan=plan, plan_request=request)
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}
    assert cell.entities["widgets"] == []


def test_memory_plan_staleness_after_a_schema_change_to_a_different_entity() -> None:
    """WP-2b 監査 N-6(b) (`{scratchpad}/audit-wp2b.md`): the mutation-side
    sibling of the test above, but the intervening schema change lands on
    a DIFFERENT entity (`other`) than the one the mutation/plan target
    (`widgets`) -- proof that "the token names the Application's schema
    state, not one entity's" (contract `structured_operations.dry_run.
    plan`) is not merely a same-entity coincidence: `schema_revision` is a
    single per-Application counter (D-4 (7)), so ANY entity's schema
    change invalidates every outstanding plan. Before this test, no
    peer-local test asserted cross-entity invalidation positively -- the
    inline comment on `test_memory_stale_plan_on_unconfirmed_destructive_
    delete_is_confirmation_required_first` below claimed to, but that test
    is refused for the missing confirmation before plan comparison is ever
    reached (see its own corrected comment)."""
    cell = _memory_cell_with_widgets()
    operations = [{"operation": "insert", "values": {"label": "a"}}]
    request = {"operations": operations, "transaction": "atomic"}
    plan = cell.transact("widgets", operations, LIMITS, dry_run=True, plan_request=request).plan
    cell.apply_schema({"operation": "create_entity", "entity": "other", "fields": ["x"]}, developer=True, limits=LIMITS)
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", operations, LIMITS, plan=plan, plan_request=request)
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}
    assert cell.entities["widgets"] == []


def test_memory_transact_does_not_compute_plan_token_without_dry_run_or_plan(monkeypatch) -> None:
    """N-1 (`{scratchpad}/audit-wp2b.md`) / review round F-5's own
    docstring claim on `transact` above ("A plain apply pays no `json.
    dumps`/`sha256` cost it never uses"): `compute_plan_token` (and the
    `normalize_request_for_plan`/sha256 work behind it) is only ever
    called when `dry_run` or a caller-presented `plan` actually consumes
    the digest -- never for an ordinary apply carrying neither. Before
    this test, no peer-local test pinned this at all: reverting
    `structured.py`'s `if plan_request is not None and (dry_run or plan
    is not None)` guard back to unconditional (`if plan_request is not
    None`) left `r2db-api/tests` (1061 passed) and `conformance-tests/
    test_c22_dry_run_and_plan.py` (4 passed) both fully green (audit
    mutation M-5) -- this test is the first thing that goes red."""
    import r2db_api.structured as structured_module

    calls = {"n": 0}
    real_compute = structured_module.compute_plan_token

    def counting(*args: Any, **kwargs: Any) -> str:
        calls["n"] += 1
        return real_compute(*args, **kwargs)

    monkeypatch.setattr(structured_module, "compute_plan_token", counting)

    cell = _memory_cell_with_widgets()
    request = {"operations": [{"operation": "insert", "values": {"label": "a"}}], "transaction": "atomic"}
    cell.transact("widgets", request["operations"], LIMITS, plan_request=request)
    assert calls["n"] == 0, "an ordinary apply (no dry_run, no plan) must not compute a plan token at all"

    cell.transact("widgets", request["operations"], LIMITS, plan_request=request, dry_run=True)
    assert calls["n"] == 1


def test_memory_stale_plan_on_unconfirmed_destructive_delete_is_confirmation_required_first() -> None:
    """Completion condition 9 (ordering, D-4 (2)): confirmation precedes
    precondition -- a stale plan on an UNCONFIRMED destructive delete is
    refused for the missing confirmation, never PRECONDITION_FAILED."""
    cell = _memory_cell_with_widgets()
    cell.transact("widgets", [{"operation": "insert", "values": {"label": "a"}}], LIMITS)
    where_predicates = [Predicate(field="label", operator="eq", value="a")]
    confirmed_phrase = delete_confirmation_phrase("widgets", where_predicates, cell.schema_revision)
    delete_op = {"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "a"}], "destructive": True, "confirmation": confirmed_phrase}
    request = {"operations": [delete_op], "transaction": "atomic"}
    stale_plan = cell.transact("widgets", [delete_op], LIMITS, dry_run=True, plan_request=request).plan
    # A second, unrelated schema change on the SAME Application (not this
    # entity) invalidates the plan (D-4 (7): per-application revision) --
    # but this test does NOT observe that invalidation itself: the
    # UNCONFIRMED delete below is refused for the missing confirmation
    # before plan comparison is ever reached (D-4 (2)'s ordering, this
    # test's own point). The positive cross-entity-invalidation assertion
    # lives in `test_memory_plan_staleness_after_a_schema_change_to_a_
    # different_entity` above.
    cell.apply_schema({"operation": "create_entity", "entity": "other", "fields": ["x"]}, developer=True, limits=LIMITS)
    unconfirmed_delete = {"operation": "delete", "where": [{"field": "label", "operator": "eq", "value": "a"}], "destructive": True}
    with pytest.raises(FoundationError) as exc:
        cell.transact("widgets", [unconfirmed_delete], LIMITS, plan=stale_plan, plan_request={"operations": [unconfirmed_delete], "transaction": "atomic"})
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert len(cell.entities["widgets"]) == 1


# ===========================================================================
# Section 3: `ApplicationCell.apply_schema` -- schema-side dry_run/plan.
# ===========================================================================


def test_memory_schema_dry_run_reports_pre_apply_revision_and_matching_descriptor() -> None:
    """Completion condition 5."""
    cell = _memory_cell_with_widgets()
    revision_r = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "a"}, developer=True, limits=LIMITS).revision
    dry = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "b"}, developer=True, limits=LIMITS, dry_run=True)
    assert dry.committed is False
    assert dry.revision == revision_r  # NOT the value the real apply would establish
    assert "b" in dry.descriptor["fields"]
    assert "b" not in cell.schema["widgets"]  # the real state never changed
    revision_r_plus_1 = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "b"}, developer=True, limits=LIMITS).revision
    assert revision_r_plus_1 == revision_r + 1


def test_memory_schema_dry_run_of_drop_entity_reports_no_descriptor() -> None:
    """D-4 (3): a dry-run `drop_entity` leaves nothing to describe
    afterwards -- `descriptor` is `None`, and the entity is untouched."""
    cell = _memory_cell_with_widgets()
    dry = cell.apply_schema(
        {"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": drop_entity_confirmation_phrase("widgets", cell.schema_revision)},
        developer=True, limits=LIMITS, dry_run=True,
    )
    assert dry.committed is False
    assert dry.descriptor is None
    assert "widgets" in cell.entities


def test_memory_schema_dry_run_does_not_consume_the_id_sequence() -> None:
    """WP-2b 監査照合項目 2: unlike a data mutation (F-15, permitted to
    consume), `apply_schema` snapshots/restores `_next_id` -- a dry-run
    schema operation (which never touches rows at all) must not perturb
    it. Inserting after a schema dry run gets id 1, not a skipped value."""
    cell = _memory_cell_with_widgets()
    cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "dry", "dry_run": False}, developer=True, limits=LIMITS)  # unrelated real op, baseline
    cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "another"}, developer=True, limits=LIMITS, dry_run=True)
    row = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS).assigned_addresses[0]
    assert row["address"]["id"] == 1


def test_memory_schema_plan_valid_and_stale_paths() -> None:
    """Completion conditions 6-8, schema side: determinism, validity,
    and staleness (a second real op on the SAME entity)."""
    cell = _memory_cell_with_widgets()
    op = {"operation": "add_field", "entity": "widgets", "field": "a"}
    request = {k: v for k, v in op.items() if k not in ("plan", "dry_run")}
    dry1 = cell.apply_schema(op, developer=True, limits=LIMITS, dry_run=True, plan_request=request)
    dry2 = cell.apply_schema(op, developer=True, limits=LIMITS, dry_run=True, plan_request=request)
    assert dry1.plan and dry1.plan == dry2.plan
    real = cell.apply_schema(op, developer=True, limits=LIMITS, plan=dry1.plan, plan_request=request)
    assert real.committed is True
    assert "a" in cell.schema["widgets"]
    op2 = {"operation": "add_field", "entity": "widgets", "field": "b"}
    request2 = dict(op2)
    stale_plan = cell.apply_schema(op2, developer=True, limits=LIMITS, dry_run=True, plan_request=request2).plan
    cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "c"}, developer=True, limits=LIMITS)  # advances the revision
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(op2, developer=True, limits=LIMITS, plan=stale_plan, plan_request=request2)
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}
    assert "b" not in cell.schema["widgets"]


def test_memory_schema_drop_entity_confirmation_precedes_stale_plan_precondition() -> None:
    """N-5 (`{scratchpad}/audit-wp2b.md`): schema-side sibling of
    `test_memory_stale_plan_on_unconfirmed_destructive_delete_is_
    confirmation_required_first` (Section 2) -- D-4 (2)'s "confirmation
    precedes precondition" ordering, pinned for `apply_schema`'s own
    `drop_entity` branch this time. `structured.py`'s `expected_plan`/
    `plan` comparison for `apply_schema` sits AFTER every operation
    branch, including the `require_destructive_confirmation` call inside
    `drop_entity` -- so an UNCONFIRMED `drop_entity` carrying a stale plan
    is refused DESTRUCTIVE_CONFIRMATION_REQUIRED, never PRECONDITION_
    FAILED. Before this test, no peer-local test pinned this for the
    schema side (audit mutation M-3: moving the plan comparison earlier,
    to immediately after `expected_plan` is computed, left this WP's
    whole peer-local suite -- 33 tests at audit time -- fully green; only
    `conformance-tests`' own `PostgresCell`-backed leg caught it)."""
    cell = _memory_cell_with_widgets()
    confirmed_phrase = drop_entity_confirmation_phrase("widgets", cell.schema_revision)
    confirmed_drop = {"operation": "drop_entity", "entity": "widgets", "destructive": True, "confirmation": confirmed_phrase}
    request = {k: v for k, v in confirmed_drop.items() if k not in ("plan", "dry_run")}
    stale_plan = cell.apply_schema(confirmed_drop, developer=True, limits=LIMITS, dry_run=True, plan_request=request).plan
    # A second, unrelated schema change advances the revision (staling the
    # plan above) and, since the revision also feeds the confirmation
    # phrase, would make any OLD confirmation phrase wrong too -- this
    # test instead omits confirmation entirely, so the refusal reason is
    # unambiguous.
    cell.apply_schema({"operation": "create_entity", "entity": "other", "fields": ["x"]}, developer=True, limits=LIMITS)
    unconfirmed_drop = {"operation": "drop_entity", "entity": "widgets", "destructive": True}
    with pytest.raises(FoundationError) as exc:
        cell.apply_schema(unconfirmed_drop, developer=True, limits=LIMITS, plan=stale_plan, plan_request=dict(unconfirmed_drop))
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert "widgets" in cell.entities


def test_memory_apply_schema_does_not_compute_plan_token_without_dry_run_or_plan(monkeypatch) -> None:
    """N-1 (`{scratchpad}/audit-wp2b.md`), schema-side sibling of `test_
    memory_transact_does_not_compute_plan_token_without_dry_run_or_plan`
    (Section 2) -- same guard, `structured.py`'s `apply_schema` this
    time."""
    import r2db_api.structured as structured_module

    calls = {"n": 0}
    real_compute = structured_module.compute_plan_token

    def counting(*args: Any, **kwargs: Any) -> str:
        calls["n"] += 1
        return real_compute(*args, **kwargs)

    monkeypatch.setattr(structured_module, "compute_plan_token", counting)

    cell = _memory_cell_with_widgets()
    op = {"operation": "add_field", "entity": "widgets", "field": "plain"}
    request = {k: v for k, v in op.items() if k not in ("plan", "dry_run")}
    cell.apply_schema(op, developer=True, limits=LIMITS, plan_request=request)
    assert calls["n"] == 0, "an ordinary apply (no dry_run, no plan) must not compute a plan token at all"

    op2 = {"operation": "add_field", "entity": "widgets", "field": "dry_only"}
    request2 = {k: v for k, v in op2.items() if k not in ("plan", "dry_run")}
    cell.apply_schema(op2, developer=True, limits=LIMITS, plan_request=request2, dry_run=True)
    assert calls["n"] == 1


# ===========================================================================
# Section 4: `PostgresCell` -- real ROLLBACK/COMMIT, real connections.
# ===========================================================================


def test_pg_dry_run_mutation_really_rolls_back(app_a) -> None:
    """Completion conditions 2/3, `PostgresCell`: `psycopg.Rollback` (not
    a plain early return) actually discards the tentative row -- real
    PostgreSQL, not an in-memory `deepcopy`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"]}, developer=True, limits=LIMITS)
        dry = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS, dry_run=True)
        assert dry.committed is False
        assert dry.affected == 1
        rows = cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items
        assert rows == []
        real = cell.transact("widgets", [{"operation": "insert", "values": {"label": "x"}}], LIMITS)
        assert real.committed is True
        rows_after = cell.query("widgets", select=["id"], where=[], page_size=10, limits=LIMITS).items
        assert len(rows_after) == 1
    finally:
        cell.close()


def test_pg_dry_run_schema_really_rolls_back_and_reports_pre_apply_revision(app_a) -> None:
    """Completion condition 5, `PostgresCell`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"]}, developer=True, limits=LIMITS)
        with cell._developer.connection() as conn:
            with conn.transaction():
                revision_before = cell._read_schema_revision(conn)
        dry = cell.apply_schema({"operation": "add_field", "entity": "widgets", "field": "extra"}, developer=True, limits=LIMITS, dry_run=True)
        assert dry.committed is False
        assert dry.revision == revision_before
        assert "extra" in dry.descriptor["fields"]
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert "extra" not in entry["fields"]
    finally:
        cell.close()


def test_pg_dry_run_alter_field_really_rolls_back(app_a) -> None:
    """G-5 (`{scratchpad}/rulings-r4.md` addendum): `alter_field`'s own
    `PostgresCell` dry_run -- distinct code path from `add_field`
    (`_check_type`, revision-bump, constraint-table write, WP-2a) that
    `test_pg_dry_run_schema_really_rolls_back_and_reports_pre_apply_
    revision` above never exercises. A dry-run `alter_field` must leave
    the field's declared constraints exactly as they were, real
    ROLLBACK -- not an in-memory `deepcopy`."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema(
            {"operation": "create_entity", "entity": "widgets", "fields": ["status"], "field_types": {"status": "string"}, "field_constraints": {"status": {"enum": ["draft", "live"], "nullable": True}}},
            developer=True, limits=LIMITS,
        )
        with cell._developer.connection() as conn:
            with conn.transaction():
                revision_before = cell._read_schema_revision(conn)
        dry = cell.apply_schema(
            {"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"], "nullable": False},
            developer=True, limits=LIMITS, dry_run=True,
        )
        assert dry.committed is False
        assert dry.revision == revision_before
        entry = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry["field_constraints"]["status"] == {"enum": ["draft", "live"], "nullable": True}
        # A real apply afterwards still goes through -- the dry run above
        # left the table's own constraint side-table untouched, not
        # merely the response.
        real = cell.apply_schema(
            {"operation": "alter_field", "entity": "widgets", "field": "status", "enum": ["draft", "live", "archived"], "nullable": False},
            developer=True, limits=LIMITS,
        )
        assert real.revision == revision_before + 1
        entry_after = next(e for e in cell.catalog() if e["entity"] == "widgets")
        assert entry_after["field_constraints"]["status"] == {"enum": ["draft", "live", "archived"], "nullable": False}
    finally:
        cell.close()


def test_pg_plan_mismatch_is_precondition_failed_and_changes_nothing(app_a) -> None:
    """Completion condition 7, `PostgresCell`: a real transaction/
    connection, still refuses and leaves no row behind."""
    cell = make_cell(app_a)
    try:
        cell.apply_schema({"operation": "create_entity", "entity": "widgets", "fields": ["label"]}, developer=True, limits=LIMITS)
        operations_a = [{"operation": "insert", "values": {"label": "a"}}]
        plan = cell.transact("widgets", operations_a, LIMITS, dry_run=True, plan_request={"operations": operations_a, "transaction": "atomic"}).plan
        operations_b = [{"operation": "insert", "values": {"label": "b"}}]
        with pytest.raises(FoundationError) as exc:
            cell.transact("widgets", operations_b, LIMITS, plan=plan, plan_request={"operations": operations_b, "transaction": "atomic"})
        assert exc.value.code == "PRECONDITION_FAILED"
        assert exc.value.details == {"violated_declaration": "plan"}
        rows = cell.query("widgets", select=["label"], where=[], page_size=10, limits=LIMITS).items
        assert rows == []
    finally:
        cell.close()


# ===========================================================================
# Section 5: `DataService` -- capability gate, audit non-construction,
# `assigned_addresses` omission, response `committed`/`plan` shape.
# ===========================================================================


def test_service_dry_run_authorization_refusal_matches_the_real_request() -> None:
    """Completion condition 1 (authorization sub-leg, `DataService.
    schema`'s own role check): a runtime credential attempting a
    developer-only schema operation is refused FORBIDDEN identically
    whether or not `dry_run` accompanies it -- `dry_run` walks the SAME
    gates a real request does, no early-out (D-4 (2)). This is the
    peer-local substitute for `conformance-tests/test_c22_dry_run_and_
    plan.py`'s own `_auth_probe` sub-leg, which this WP's own suite
    cannot currently exercise end-to-end (see this WP's report: `conformance-
    tests/adapter.py`'s abstract `attempt_mutation_with_result` has no
    `destructive` parameter at all, so its sibling `_confirm_probe` sub-
    leg -- evaluated before `_auth_probe`'s own result would otherwise be
    checked in the SAME test function -- raises `TypeError` first, a
    pre-existing gap this WP does not own and cannot fix)."""
    service, _control = build_service()
    runtime = runtime_context(service)
    with pytest.raises(FoundationError) as dry_exc:
        service.schema(runtime, {"operation": "add_field", "entity": "notes", "field": "x", "dry_run": True})
    with pytest.raises(FoundationError) as real_exc:
        service.schema(runtime, {"operation": "add_field", "entity": "notes", "field": "x"})
    assert dry_exc.value.code == real_exc.value.code == "FORBIDDEN"


def test_service_dry_run_capability_is_enabled_and_gate_is_removed() -> None:
    """Completion condition 10 (part 1)."""
    service, _control = build_service()
    developer = developer_context(service)
    assert service.capabilities(developer)["capabilities"]["dry_run"]["status"] == "enabled"
    runtime = runtime_context(service)
    # No CAPABILITY_UNSUPPORTED any more for dry_run/plan.
    result = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}], dry_run=True)
    assert result.committed is False


def test_service_dry_run_mutation_writes_no_audit_event_at_all() -> None:
    """Completion condition 3 (audit half, U-2 = (A)): a real insert
    writes a buffer-class event once flushed; a dry-run insert writes
    NONE -- neither buffered nor legacy."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    runtime = runtime_context(service)
    service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "real"}}])
    service.flush_audit_buffer()
    count_after_real = len(durable_events(durable))
    assert count_after_real > 0

    service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "dry"}}], dry_run=True)
    service.flush_audit_buffer()
    assert len(durable_events(durable)) == count_after_real
    # The legacy in-memory sink (`ControlAuthority`/tests' own back door)
    # is also unaffected -- not merely the durable/buffered one.
    legacy_count_before = len(service._audit.events())
    service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "dry2"}}], dry_run=True)
    assert len(service._audit.events()) == legacy_count_before


def test_service_dry_run_schema_writes_no_audit_event_at_all() -> None:
    """Completion condition 3 (audit half), schema side: every schema
    operation is unconditionally fail-closed class when real -- `audit_
    hook.pre_commit()` performs a synchronous, already-committed durable
    INSERT (`audit_hook.py`'s own module docstring) -- so a real apply's
    own event is genuinely observable on `durable_events(durable)`. A dry
    run must still write nothing to EITHER sink.

    Review round F-3 (`{scratchpad}/rulings-r4.md`): the pre-round-2
    version of this test asserted only the durable count was unchanged
    by a dry run, without ever having first shown that count moves for a
    REAL schema apply (non-vacuity) -- and it never watched the LEGACY
    in-memory sink (`service._audit.events()`) at all, which `_event`
    appends to unconditionally, ahead of its own `already_durable` early
    return (`service.py`'s `_event`, `self._audit.append(...)` runs
    before the `if already_durable: return`). Removing `service.py`'s
    `if not dry_run:` guard around the schema-side `_event(...)` call
    left THIS test green (durable stays 0 either way, since `schema`
    always passes `already_durable=True`) while still growing the legacy
    sink by one row for the dry run -- a real regression the old
    assertion never could have caught. This version counts both sinks,
    before and after, around both calls."""
    durable = ApplicationAuditSink()
    service, _control = build_service(durable_audit=durable)
    developer = developer_context(service)

    durable_before_real = len(durable_events(durable))
    service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "real_field"})
    durable_after_real = len(durable_events(durable))
    assert durable_after_real > durable_before_real

    durable_before_dry = len(durable_events(durable))
    legacy_before_dry = len(service._audit.events())
    service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "dry_field", "dry_run": True})
    assert len(durable_events(durable)) == durable_before_dry
    assert len(service._audit.events()) == legacy_before_dry


def test_service_dry_run_still_consumes_the_concurrency_slot() -> None:
    """Prohibition 6 / non-vacuity item 3: dry_run does not bypass rate/
    concurrency accounting -- a dry_run request is refused `LIMIT_
    EXCEEDED` exactly like a real one when the concurrency bound is
    already exhausted (the SAME `_slot` context every real request goes
    through, no early-out for `dry_run` anywhere before it -- mirrors
    `test_foundation.py`'s own `service._active = 1` recipe)."""
    service, _control = build_service(limits=ResourceLimits(concurrency=1))
    runtime = runtime_context(service)
    service._active = 1
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}], dry_run=True)
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_service_mutate_result_dry_run_response_omits_assigned_addresses() -> None:
    """Completion condition 4. Review round F-6 (`{scratchpad}/
    rulings-r4.md`): the contract's "does not carry" means the KEY is
    absent, not merely emptied -- `None`, never `[]`."""
    service, _control = build_service()
    runtime = runtime_context(service)
    result = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}], dry_run=True)
    assert result.assigned_addresses is None
    assert result.committed is False
    assert result.plan


def test_service_mutate_result_real_response_carries_no_plan() -> None:
    """D-4 (3): a real (non-dry-run) response keeps its pre-1.7.0 shape
    besides `committed` -- `plan` is never surfaced on it."""
    service, _control = build_service()
    runtime = runtime_context(service)
    result = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}])
    assert result.committed is True
    assert result.plan is None


def test_service_mutate_plan_from_one_entity_is_rejected_for_a_different_entity() -> None:
    """H-1 (`{scratchpad}/rulings-r4.md` addendum 2): the plan digest
    commits to the request's own target entity -- `mutate`'s own URL path
    segment, not a `MutationRequest` body field. A plan taken from entity
    A's dry_run, presented against a DIFFERENT entity B's real apply
    (identical `operations`/`transaction`, identical schema_revision --
    `widgets` is created BEFORE the dry_run below, so no schema change
    lands between the two calls), is refused PRECONDITION_FAILED
    fail-closed, never silently honored as if it were entity B's own
    plan."""
    service, _control = build_service()
    developer = developer_context(service)
    service.schema(developer, {"operation": "create_entity", "entity": "widgets", "fields": ["body"]})
    runtime = runtime_context(service)
    operations = [{"operation": "insert", "values": {"body": "x"}}]
    plan_for_notes = service.mutate_result(runtime, "notes", operations, dry_run=True).plan
    assert plan_for_notes is not None
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(runtime, "widgets", operations, plan=plan_for_notes)
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}
    assert service.query(runtime, "widgets", select=["id"]) == []


def test_service_schema_plan_from_one_entity_is_rejected_for_a_different_entity() -> None:
    """H-1 schema-side sibling: `SchemaOperationRequest.entity` is already
    a required contract-level body field on this peer (this peer's own
    `/v1/schema/operations` route carries no `{entity}` URL segment at
    all), so it was already part of the plan digest object before this WP
    -- fixed here as a fixation test (not a behaviour change here, unlike
    the mutate-side test above, where `entity` is a path segment that is
    NOT a `MutationRequest` body field and genuinely needed adding)."""
    service, _control = build_service()
    developer = developer_context(service)
    service.schema(developer, {"operation": "create_entity", "entity": "widgets", "fields": ["body"]})
    dry = service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "extra", "dry_run": True})
    assert dry.plan is not None
    with pytest.raises(FoundationError) as exc:
        service.schema(developer, {"operation": "add_field", "entity": "widgets", "field": "extra", "plan": dry.plan})
    assert exc.value.code == "PRECONDITION_FAILED"
    assert exc.value.details == {"violated_declaration": "plan"}


def test_service_schema_always_returns_schema_outcome() -> None:
    """Review round F-8 (`{scratchpad}/rulings-r4.md`): `service.schema()`
    (and the backend `apply_schema` it is a pure passthrough of) always
    returns `SchemaOutcome`, `dry_run`/`plan` or neither -- a bare `int`
    for one request and a `SchemaOutcome` for the structurally identical
    request differing only in whether it happened to carry `plan` was two
    shapes for the same call, not a backward-compatibility rule (this
    test replaces the pre-round-2 version that pinned the OLD dual-shape
    behavior). Every pre-1.7.0 direct caller now reads `.revision`."""
    service, _control = build_service()
    developer = developer_context(service)
    outcome = service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "plain"})
    assert not isinstance(outcome, int)
    assert isinstance(outcome.revision, int)
    assert outcome.revision == 1
    assert outcome.committed is True
    assert outcome.descriptor is None
    assert outcome.plan is None


def test_service_budget_only_bare_gate_is_unaffected_by_wp_2b() -> None:
    """A bare `budget` with no `plan` is refused `CAPABILITY_UNSUPPORTED`
    (`request_budget` stays `unavailable` until WP-2d) -- unaffected by
    this WP either way."""
    service, _control = build_service()
    runtime = runtime_context(service)
    with pytest.raises(FoundationError) as exc:
        service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "x"}}], budget={"batch_items": 1})
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.details == {"violated_declaration": "capability", "field": "budget"}


def test_service_budget_with_plan_is_still_capability_gated() -> None:
    """Review round F-1 (`{scratchpad}/rulings-r4.md`, supervisor ruling
    -- `request_budget` stays `unavailable` regardless of `plan`): the
    round-1 implementation gated `budget` only `if budget is not None and
    plan is None`, so a `budget`-carrying request that ALSO presented a
    `plan` skipped this gate entirely and fell through to precondition
    checking -- and because `plan`'s digest rule (`structured_operations.
    dry_run.plan`) is published in the contract and the token's own
    format (`"<sha256hex>.<schema_revision>"`, review F-7) discloses the
    revision it was computed against in plaintext, a client could read
    the current revision off any plain dry run's own `plan`, recompute a
    matching digest for a `budget`-carrying body by the same published
    rule, and have `budget` silently accepted-and-ignored on the
    resulting apply (a P-3 violation: `request_budget: unavailable`
    stops being true). This pins the fix: `budget` is refused at the
    capability gate REGARDLESS of `plan`, and precondition evaluation
    (where `plan` would otherwise be checked) is never reached."""
    service, _control = build_service()
    developer = developer_context(service)
    runtime = runtime_context(service)

    # A plan a plain (budget-less) dry run actually produced -- exactly
    # the artifact the probe this ruling responds to would compute from.
    dry = service.mutate_result(runtime, "notes", [{"operation": "insert", "values": {"body": "probe"}}], dry_run=True)
    assert dry.plan is not None

    with pytest.raises(FoundationError) as exc:
        service.mutate_result(
            runtime, "notes", [{"operation": "insert", "values": {"body": "probe"}}],
            plan=dry.plan, budget={"batch_items": 1},
        )
    assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    assert exc.value.details == {"violated_declaration": "capability", "field": "budget"}

    # No side effect: the gated attempt above never reached execution.
    catalog = service.catalog(developer)
    rows = service.query(runtime, "notes", select=["id"], where=[{"field": "body", "operator": "eq", "value": "probe"}], page_size=10)
    assert rows == []
    assert catalog is not None
