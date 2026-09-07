"""C-23 -- a peer declaring `idempotency` records each key with a digest of
its request, in the same transaction as that request's effects, and a
same-key/same-body resend returns the original result without
re-executing (SI-11, SI-08, SI-14).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-5, §6.2 "C-23 idempotency", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-23")`
via the module-level `pytestmark`. **Overlaps C-07 (ii)**: that row's own
positive branch becomes load-bearing on all four plugs the moment a peer
declares `idempotency` as anything other than `unavailable` -- unchanged
test, an input to it (the declaration) changing instead.

Declare-first, capability `idempotency` (existing, C-07 (ii)'s own gate),
written in the same house style as C-20/C-22 -- ONE test, no `pytest.skip`:

  - `unavailable` branch: identical to C-07 (ii)'s own `unavailable` branch
    (a key-bearing request is refused `CAPABILITY_UNSUPPORTED` before
    execution, zero side effects) -- kept here too so this row's own
    `@pytest.mark.condition("C-23")` marker has real, executable evidence
    on every plug at every point in time, not only after both peers flip.
  - `retry_same_result` branch: (i) a same-key/same-body resend returns
    the identical `affected`/`assigned_addresses`/`request_id`, with only
    ONE row actually added; (ii) a same-key/different-body resend is
    refused `CONFLICT` with `violated_declaration: idempotency_key`; (v) a
    FAILED attempt (an invalid item in the batch) leaves no record, so
    resending that same key afterward is a genuinely NEW execution; (vi) a
    DIFFERENT credential of the SAME Application presenting the same key
    is treated as the same request (cross-credential scope, design A-5);
    (vii) a destructive `delete`, executed once with a valid confirmation
    and a key, replays its original result on an identical resend --
    neither `NOT_FOUND` (the row it deleted is gone) nor `DESTRUCTIVE_
    CONFIRMATION_REQUIRED` (state has moved on) may appear; (full) once
    this deployment's own declared `idempotency_entries` bound is reached,
    recording one more NEW key is refused `LIMIT_EXCEEDED`/`limit_class:
    idempotency_entries`, decided at the record-lookup step BEFORE the
    request executes -- never execute-then-rollback (design D-5 (4)/(8),
    監督裁定 I-6) -- narrowed to plugs declaring a real (int)
    `idempotency_entries` bound in `limits`, disclosed as observed out of
    scope otherwise, driven in a FRESH Application so this leg's own
    committed-key count stays exact.

**Disclosed scope limits**: (iii) retention-window expiry is not tested --
it would need to actually wait out `idempotency_retention_ms`, which this
suite does not do (declared value read, not driven to elapse). (iv)
`SchemaOperationRequest.idempotency_key` (WP-1b rework, review point C: not
just an idempotent `add_field`, but the SAME 3 properties (i)/(ii)/(v)
above -- replay, `CONFLICT` on a same-key/different-body resend, and a
failed attempt leaving no record) and cross-entity idempotency (the
IDENTICAL 3 properties, via `attempt_cross_entity_batch_with_result`) are
both exercised; cross-entity idempotency is narrowed to plugs where
`cross_entity_mutation` is not itself `unavailable` -- where it is,
`attempt_cross_entity_batch_with_result` is not usable at all and this
leg is narrowed accordingly, disclosed inline rather than silently run
regardless.
"""
from __future__ import annotations

import pytest

from adapter import (
    BatchOperation,
    ConformanceAdapter,
    ConformanceDenial,
    ScopedBatchOperation,
    fresh_identifier,
    resolve_valid_confirmation,
)
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-23")


def _status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("idempotency", {}).get("status", "unavailable")


def _expected_branch_for_status(status: str) -> str:
    return "unavailable" if status == "unavailable" else "retry_same_result"


def test_c23_idempotency_semantics(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    status = _status(adapter)
    developer, runtime, app_id = provision_pair(iso, app_prefix="c23")
    entity = fresh_identifier("c23")
    iso.create_entity(developer, entity, {"label": "text"})
    count_before_all = iso.count(runtime, entity)

    observed_branch: str
    if status == "unavailable":
        key = fresh_identifier("c23key")
        with pytest.raises(ConformanceDenial) as ei:
            iso.attempt_batch_with_result(
                runtime, entity, [BatchOperation(operation="insert", values={"label": "x"}, idempotency_key=key)],
            )
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: idempotency is 'unavailable', but a key-bearing request was refused with "
            f"{ei.value.code!r} instead of CAPABILITY_UNSUPPORTED"
        )
        assert iso.count(runtime, entity) == count_before_all, (
            f"{adapter.name}: a request refused as unavailable must have zero side effects"
        )
        observed_branch = "unavailable"
    else:
        # (i) same key, same body -> replayed result, exactly one row.
        key = fresh_identifier("c23key")
        marker = fresh_identifier("c23row")
        first = iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key)],
        )
        second = iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": marker}, idempotency_key=key)],
        )
        assert first.get("affected") == second.get("affected") and first.get("assigned_addresses") == second.get(
            "assigned_addresses"
        ), (
            f"{adapter.name}: resending the same idempotency_key/body returned a different result -- "
            f"{first!r} vs {second!r}"
        )
        if first.get("request_id") is not None:
            assert second.get("request_id") == first.get("request_id"), (
                f"{adapter.name}: a replayed result must carry the ORIGINAL execution's own request_id -- "
                f"first={first.get('request_id')!r}, resend={second.get('request_id')!r}"
            )
        assert len(iso.select_eq(runtime, entity, ["label"], "label", marker)) == 1, (
            f"{adapter.name}: a same-key/same-body resend must not have executed a second insert"
        )

        # (ii) same key, different body -> CONFLICT.
        other_marker = fresh_identifier("c23other")
        with pytest.raises(ConformanceDenial) as ei_conflict:
            iso.attempt_batch_with_result(
                runtime, entity, [BatchOperation(operation="insert", values={"label": other_marker}, idempotency_key=key)],
            )
        assert ei_conflict.value.code == "CONFLICT", (
            f"{adapter.name}: same idempotency_key, different body -> {ei_conflict.value.code!r}, expected "
            "CONFLICT"
        )
        assert ei_conflict.value.details.get("violated_declaration") == "idempotency_key", ei_conflict.value.details
        assert iso.select_eq(runtime, entity, ["label"], "label", other_marker) == [], (
            f"{adapter.name}: the CONFLICT-refused body must not have been written under a different row"
        )

        # (v) a failed attempt (an invalid item alongside the keyed one)
        # leaves no record -- resending that key afterward is a new
        # execution, not a replay of nothing.
        fail_key = fresh_identifier("c23failkey")
        fail_marker = fresh_identifier("c23failrow")
        bad_field = fresh_identifier("c23nosuch")
        with pytest.raises(ConformanceDenial):
            iso.attempt_batch_with_result(
                runtime, entity,
                [
                    BatchOperation(operation="insert", values={"label": fail_marker}, idempotency_key=fail_key),
                    BatchOperation(operation="insert", values={bad_field: "x"}, idempotency_key=fail_key),
                ],
            )
        assert iso.select_eq(runtime, entity, ["label"], "label", fail_marker) == [], (
            f"{adapter.name}: the whole failed batch must have rolled back (C-07 (i))"
        )
        retried = iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": fail_marker}, idempotency_key=fail_key)],
        )
        assert retried.get("affected") == 1, (
            f"{adapter.name}: resending the SAME key after its earlier attempt FAILED must be a genuinely "
            f"new execution (it must actually insert), not a no-op replay -- {retried!r}"
        )
        assert len(iso.select_eq(runtime, entity, ["label"], "label", fail_marker)) == 1

        # (vi) a DIFFERENT credential of the SAME Application, same key ->
        # treated as the same request.
        other_runtime = iso.authenticate(iso.issue_credential(app_id, "runtime"))
        cross_cred_key = fresh_identifier("c23crosskey")
        cross_marker = fresh_identifier("c23crossrow")
        via_first = iso.attempt_batch_with_result(
            runtime, entity, [BatchOperation(operation="insert", values={"label": cross_marker}, idempotency_key=cross_cred_key)],
        )
        via_second = iso.attempt_batch_with_result(
            other_runtime, entity,
            [BatchOperation(operation="insert", values={"label": cross_marker}, idempotency_key=cross_cred_key)],
        )
        assert via_first.get("affected") == via_second.get("affected"), (
            f"{adapter.name}: the same idempotency_key presented by a DIFFERENT credential of the same "
            f"Application was not treated as the same request -- {via_first!r} vs {via_second!r}"
        )
        assert len(iso.select_eq(runtime, entity, ["label"], "label", cross_marker)) == 1, (
            f"{adapter.name}: the cross-credential resend must not have inserted a second row"
        )

        # (vii) destructive replay: delete once with a valid confirmation +
        # key, resend the identical request -> the ORIGINAL result, not
        # NOT_FOUND, not DESTRUCTIVE_CONFIRMATION_REQUIRED.
        contract_version = adapter.capability_document()["contract_version"]
        delete_marker = fresh_identifier("c23del")
        iso.attempt_mutation(runtime, entity, "insert", values={"label": delete_marker}, where_field=None, where_value=None)

        def probe() -> None:
            iso.attempt_batch_with_result(
                runtime, entity,
                [BatchOperation(operation="delete", where_field="label", where_value=delete_marker, destructive=True)],
            )

        phrase = resolve_valid_confirmation(contract_version=contract_version, legacy_token="DELETE", probe=probe)
        delete_key = fresh_identifier("c23delkey")
        delete_op = [
            BatchOperation(
                operation="delete", where_field="label", where_value=delete_marker,
                destructive=True, confirmation=phrase, idempotency_key=delete_key,
            )
        ]
        first_delete = iso.attempt_batch_with_result(runtime, entity, delete_op)
        assert first_delete.get("affected") == 1, f"{adapter.name}: the confirmed delete did not affect a row"
        assert iso.select_eq(runtime, entity, ["label"], "label", delete_marker) == [], (
            f"{adapter.name}: the confirmed delete did not actually remove the row"
        )
        replayed_delete = iso.attempt_batch_with_result(runtime, entity, delete_op)
        assert replayed_delete.get("affected") == first_delete.get("affected"), (
            f"{adapter.name}: resending an identical, already-committed destructive delete (same key, same "
            f"body) must replay the ORIGINAL result -- first={first_delete!r}, resend={replayed_delete!r}"
        )

        # (iv) schema-request idempotency_key (D-5(1)(iv), newly added to
        # SchemaOperationRequest in this version) -- the SAME 3 properties
        # (i)/(ii)/(v) above exercise for a single-entity mutation, WP-1b
        # rework (review point C): not (i) alone.
        schema_key = fresh_identifier("c23schemakey")
        schema_field = fresh_identifier("c23sf")
        first_schema = iso.schema_operation_with_result(
            developer, entity, "add_field", field=schema_field, field_type="string",
            idempotency_key=schema_key,
        )
        second_schema = iso.schema_operation_with_result(
            developer, entity, "add_field", field=schema_field, field_type="string",
            idempotency_key=schema_key,
        )
        assert first_schema.get("revision") == second_schema.get("revision"), (
            f"{adapter.name}: a same-key/same-body schema resend must replay the ORIGINAL revision, not "
            f"advance it a second time -- {first_schema!r} vs {second_schema!r}"
        )
        if first_schema.get("request_id") is not None:
            assert second_schema.get("request_id") == first_schema.get("request_id"), (
                f"{adapter.name}: a replayed schema result must carry the ORIGINAL execution's own "
                f"request_id -- first={first_schema.get('request_id')!r}, resend={second_schema.get('request_id')!r}"
            )

        # (iv)(ii) same schema key, different body -> CONFLICT.
        schema_other_field = fresh_identifier("c23sfother")
        with pytest.raises(ConformanceDenial) as ei_schema_conflict:
            iso.schema_operation_with_result(
                developer, entity, "add_field", field=schema_other_field, field_type="string",
                idempotency_key=schema_key,
            )
        assert ei_schema_conflict.value.code == "CONFLICT", (
            f"{adapter.name}: same schema idempotency_key, different body -> "
            f"{ei_schema_conflict.value.code!r}, expected CONFLICT"
        )
        assert ei_schema_conflict.value.details.get("violated_declaration") == "idempotency_key", (
            ei_schema_conflict.value.details
        )

        # (iv)(v) a failed schema attempt (an unrecognized field_type) leaves
        # no record -- resending that key afterward with a VALID body is a
        # genuinely new execution, not a replay of nothing.
        schema_fail_key = fresh_identifier("c23schemafailkey")
        with pytest.raises(ConformanceDenial):
            iso.schema_operation_with_result(
                developer, entity, "add_field", field=fresh_identifier("c23sffail"),
                field_type="not-a-real-contract-type", idempotency_key=schema_fail_key,
            )
        schema_retry_field = fresh_identifier("c23sfretry")
        retried_schema = iso.schema_operation_with_result(
            developer, entity, "add_field", field=schema_retry_field, field_type="string",
            idempotency_key=schema_fail_key,
        )
        assert retried_schema.get("revision") is not None, (
            f"{adapter.name}: resending the SAME schema key after its earlier attempt FAILED must be a "
            f"genuinely new execution -- {retried_schema!r}"
        )

        # (iv) cross-entity idempotency (design §6.2 C-23 (iv), WP-1b
        # rework, review point C): the SAME 3 properties above, on
        # `attempt_cross_entity_batch_with_result`, narrowed to plugs
        # where `cross_entity_mutation` is not itself `unavailable`
        # (`attempt_cross_entity_batch_with_result` is not usable at all
        # otherwise -- disclosed, not silently run).
        cross_status = (
            adapter.capability_document().get("capabilities", {}).get("cross_entity_mutation", {}).get(
                "status", "unavailable"
            )
        )
        if cross_status != "unavailable":
            # (iv)(i) same key, same body -> replayed result, exactly one row.
            cross_key = fresh_identifier("c23crossbatchkey")
            cross_marker = fresh_identifier("c23crossbatchrow")
            cross_first = iso.attempt_cross_entity_batch_with_result(
                runtime, [ScopedBatchOperation(operation="insert", entity=entity, values={"label": cross_marker}, idempotency_key=cross_key)],
            )
            cross_second = iso.attempt_cross_entity_batch_with_result(
                runtime, [ScopedBatchOperation(operation="insert", entity=entity, values={"label": cross_marker}, idempotency_key=cross_key)],
            )
            assert cross_first.get("affected") == cross_second.get("affected"), (
                f"{adapter.name}: resending the same cross-entity idempotency_key/body returned a "
                f"different result -- {cross_first!r} vs {cross_second!r}"
            )
            assert len(iso.select_eq(runtime, entity, ["label"], "label", cross_marker)) == 1, (
                f"{adapter.name}: a same-key/same-body cross-entity resend must not have executed a "
                "second insert"
            )

            # (iv)(ii) same key, different body -> CONFLICT.
            cross_other_marker = fresh_identifier("c23crossother")
            with pytest.raises(ConformanceDenial) as ei_cross_conflict:
                iso.attempt_cross_entity_batch_with_result(
                    runtime, [ScopedBatchOperation(operation="insert", entity=entity, values={"label": cross_other_marker}, idempotency_key=cross_key)],
                )
            assert ei_cross_conflict.value.code == "CONFLICT", (
                f"{adapter.name}: same cross-entity idempotency_key, different body -> "
                f"{ei_cross_conflict.value.code!r}, expected CONFLICT"
            )
            assert ei_cross_conflict.value.details.get("violated_declaration") == "idempotency_key", (
                ei_cross_conflict.value.details
            )
            assert iso.select_eq(runtime, entity, ["label"], "label", cross_other_marker) == [], (
                f"{adapter.name}: the CONFLICT-refused cross-entity body must not have been written"
            )

            # (iv)(v) a failed attempt (an invalid item alongside the keyed
            # one) leaves no record -- resending that key afterward is a
            # new execution.
            cross_fail_key = fresh_identifier("c23crossfailkey")
            cross_fail_marker = fresh_identifier("c23crossfailrow")
            bad_cross_field = fresh_identifier("c23crossnosuch")
            with pytest.raises(ConformanceDenial):
                iso.attempt_cross_entity_batch_with_result(
                    runtime,
                    [
                        ScopedBatchOperation(operation="insert", entity=entity, values={"label": cross_fail_marker}, idempotency_key=cross_fail_key),
                        ScopedBatchOperation(operation="insert", entity=entity, values={bad_cross_field: "x"}, idempotency_key=cross_fail_key),
                    ],
                )
            assert iso.select_eq(runtime, entity, ["label"], "label", cross_fail_marker) == [], (
                f"{adapter.name}: the whole failed cross-entity batch must have rolled back"
            )
            cross_retried = iso.attempt_cross_entity_batch_with_result(
                runtime, [ScopedBatchOperation(operation="insert", entity=entity, values={"label": cross_fail_marker}, idempotency_key=cross_fail_key)],
            )
            assert cross_retried.get("affected") == 1, (
                f"{adapter.name}: resending the SAME cross-entity key after its earlier attempt FAILED "
                f"must be a genuinely new execution -- {cross_retried!r}"
            )
        # else: disclosed above (module docstring) -- cross_entity_mutation
        # unavailable on this plug leaves this leg unobserved here.

        # (full) idempotency_entries: recording a NEW key beyond this
        # deployment's own declared bound -- after any expired entries are
        # reclaimed -- is refused LIMIT_EXCEEDED / limit_class:
        # idempotency_entries, decided at the (8) lookup step BEFORE the
        # request executes, never execute-then-rollback (design D-5
        # (4)/(8), 監督裁定 I-6: separating "does it fit" from "run it" so
        # a request that will be refused never pays execution cost, SI-08).
        # Declaration-based, not a fixed driven count: this deployment's
        # own declared `idempotency_entries` -- narrowed to plugs that
        # declare it as a real (int) `limits` bound, disclosed as observed
        # out of scope otherwise (the same declare-first discipline every
        # other narrowed sub-leg in this file already uses; a plug may
        # declare `idempotency` enabled while this suite still has no
        # deterministic bound to drive against). A FRESH Application (own
        # `provision_pair`) keeps this leg's own committed-key count exact
        # -- the legs above already committed several keys into the
        # DEFAULT Application this test provisioned, and this leg must
        # know precisely how many committed keys separate it from the
        # bound.
        # Exercisability cap (supervisor, 2026-09-07): a deployment declaring a
        # large bound (the production default is 10000) is NOT driven -- driving
        # it would mean thousands of committed keys per run. The leg runs only
        # when the declared bound is small enough to fill deterministically
        # (the conformance isolation profiles declare 5); otherwise it is
        # disclosed as observed out of scope, exactly like C-05's own
        # `_MAX_EXERCISABLE_LIMIT` discipline.
        _MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES = 200
        declared_entries = iso.capability_document().get("limits", {}).get("idempotency_entries")
        if (
            isinstance(declared_entries, int)
            and 1 <= declared_entries <= _MAX_EXERCISABLE_IDEMPOTENCY_ENTRIES
        ):
            full_developer, full_runtime, _full_app_id = provision_pair(iso, app_prefix="c23full")
            full_entity = fresh_identifier("c23full")
            iso.create_entity(full_developer, full_entity, {"label": "text"})
            for i in range(declared_entries):
                iso.attempt_batch_with_result(
                    full_runtime, full_entity,
                    [
                        BatchOperation(
                            operation="insert", values={"label": fresh_identifier(f"c23fullrow{i}")},
                            idempotency_key=fresh_identifier(f"c23fullkey{i}"),
                        )
                    ],
                )
            count_before_full = iso.count(full_runtime, full_entity)
            with pytest.raises(ConformanceDenial) as ei_full:
                iso.attempt_batch_with_result(
                    full_runtime, full_entity,
                    [
                        BatchOperation(
                            operation="insert", values={"label": fresh_identifier("c23fulloverflowrow")},
                            idempotency_key=fresh_identifier("c23fulloverflowkey"),
                        )
                    ],
                )
            assert ei_full.value.code == "LIMIT_EXCEEDED", (
                f"{adapter.name}: recording a new idempotency key beyond the declared idempotency_entries "
                f"bound ({declared_entries}) -> {ei_full.value.code!r}, expected LIMIT_EXCEEDED"
            )
            assert ei_full.value.details.get("limit_class") == "idempotency_entries", ei_full.value.details
            assert iso.count(full_runtime, full_entity) == count_before_full, (
                f"{adapter.name}: an idempotency_entries-full refusal must be rejected BEFORE execution -- "
                "row count changed (design D-5 (8): the room check happens at the lookup step, before the "
                "request runs, never execute-then-rollback)"
            )
        # else: disclosed above -- a plug declaring `idempotency` enabled
        # without a real (int) `idempotency_entries` bound in `limits`
        # leaves this leg unobserved here.

        observed_branch = "retry_same_result"

    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: idempotency status {status!r} recorded branch {observed_branch!r}, expected "
        f"{expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )


def test_c23_fold_batch_idempotency_key_rejects_a_genuine_mixture(adapter: ConformanceAdapter, isolated) -> None:
    """WP-1b rework (差し戻し指示 7, port v1.13 §6.1 item (v)):
    `fold_batch_idempotency_key` (port-level plumbing, `conformance-tests/
    adapter.py`) enforces "every operation the same `idempotency_key`
    value, or every operation none" across every batch-shaped method on
    all 4 plugs -- both the pre-v1.13 `attempt_batch_with_addresses` and
    the v1.13 `attempt_batch_with_result` route through the SAME shared
    function (WP-1b rework, review point H: before this rework, the HTTP
    plugs' `attempt_batch_with_addresses` used an unguarded `next(...)`
    and the in-process plugs placed each operation's own raw key,
    neither of which enforced this rule at all).

    This is a PORT-usage rule, independent of the `idempotency`
    capability's own declared status -- the rule is enforced entirely
    inside the adapter, before any request ever reaches the peer, so this
    test runs unconditionally (no declare-first branching) on every plug.
    A genuine mixture -- two operations carrying two DIFFERENT non-`None`
    keys within the SAME `attempt_batch_with_result` call -- raises
    `AssertionError`, never a `ConformanceDenial` (a caller error, not a
    peer decision). Killing the guard (§6.1's own docstring rule) makes
    this test itself go red -- the load-bearing mutation for 差し戻し
    指示 7's "規則を殺すと赤になることを実測する" requirement.
    """
    iso = isolated
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c23fold")
    entity = fresh_identifier("c23fold")
    iso.create_entity(developer, entity, {"label": "text"})

    with pytest.raises(AssertionError):
        iso.attempt_batch_with_result(
            runtime, entity,
            [
                BatchOperation(
                    operation="insert", values={"label": fresh_identifier("c23folda")},
                    idempotency_key=fresh_identifier("c23foldkey1"),
                ),
                BatchOperation(
                    operation="insert", values={"label": fresh_identifier("c23foldb")},
                    idempotency_key=fresh_identifier("c23foldkey2"),
                ),
            ],
        )
