"""C-12 -- capability declaration agreement (SI-15, SI-05).

design: docs/design/CONFORMANCE_CONDITIONS_V1_1.md section 3 (C-12). Every
test here carries @pytest.mark.condition("C-12") via the module-level
`pytestmark`.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import registered_adapters
from adapter import (
    CATALOG_SURFACE_ABSENT,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    ConformanceDenial,
    Fixture,
    ScopedBatchOperation,
    SurfaceAbsent,
    fresh_identifier,
    load_contract,
    load_contract_error_codes,
)

pytestmark = pytest.mark.condition("C-12")

# design section 2 / 3: C-12 exercises insert/update/upsert only. delete is
# left to C-06 (`test_c06_destructive_confirmation.py`, executable as of
# port v1.6), which owns destructive-operation conformance for this
# vocabulary member.
_EXERCISED_OPERATIONS = ("insert", "update", "upsert")


def _unclassified_hint(code: str) -> str:
    if code != UNCLASSIFIED:
        return ""
    return (
        " -- code is adapter.UNCLASSIFIED: the peer raised a native "
        "exception the adapter could not map to a contract code. This is a "
        "finding under SI-05/SI-10, not a denial."
    )


def _assert_is_contract_code(code: str) -> None:
    contract_codes = load_contract_error_codes()
    assert code in contract_codes, f"denial code {code!r} is not a contract error code{_unclassified_hint(code)}"


def _declared_mutation_operations(capability_document: dict, contract: dict) -> set[str]:
    entry = capability_document.get("capabilities", {}).get("atomic_mutation", {})
    status = entry.get("status")
    if status == "enabled":
        return set(contract["structured_operations"]["allowed_mutations"])
    if status == "partial":
        return set(entry.get("operations", []))
    return set()


def _declared_query_operators(capability_document: dict) -> set[str]:
    entry = capability_document.get("capabilities", {}).get("structured_query", {})
    if entry.get("status") in ("enabled", "partial"):
        return set(entry.get("operators", []))
    return set()


# --- 1. declared vs. undeclared mutation operations -------------------------


def test_declared_mutation_operations_match_observed_behavior(adapter, fx: Fixture):
    contract = load_contract()
    capability_document = adapter.capability_document()
    declared = _declared_mutation_operations(capability_document, contract)

    entity = fresh_identifier("c12_mutation")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})

    for operation in _EXERCISED_OPERATIONS:
        marker = f"c12-{operation}-{uuid.uuid4().hex[:8]}"
        if operation in declared:
            # positive control: declared as supported, so a real,
            # legitimately-shaped attempt must succeed.
            if operation == "insert":
                affected = adapter.attempt_mutation(
                    fx.runtime_a, entity, "insert",
                    values={field_name: marker}, where_field=None, where_value=None,
                )
            elif operation == "update":
                adapter.attempt_mutation(
                    fx.runtime_a, entity, "insert",
                    values={field_name: marker}, where_field=None, where_value=None,
                )
                affected = adapter.attempt_mutation(
                    fx.runtime_a, entity, operation,
                    values={field_name: marker + "-updated"}, where_field=field_name, where_value=marker,
                )
            else:  # upsert
                # port v1.2 revision (docs/design/CONFORMANCE_ADAPTER_V1.md
                # section 12 / docs/design/R2DB_CCR13_STORAGE_V1.md section
                # 4 item 2, correction B-2): the contract's own precondition
                # for `upsert` is the entity's *declared domain uniqueness*
                # (`structured_operations.upsert`), so a positive control
                # that declares the capability supported but exercises it on
                # an entity with no declared unique key would not actually
                # be exercising a request the contract permits. This
                # positive control therefore runs on a dedicated entity that
                # declares exactly one unique key, via `create_unique_index`
                # -- never the bare `entity` above, which `insert`/`update`
                # share. (Verifying that upsert is correctly *refused* on an
                # entity with *no* declared unique key -- the negative side
                # of this same precondition -- is C-17's job, not C-12's:
                # C-12 only checks capability-declaration agreement at the
                # whole-capability granularity, and no registered adapter
                # declares `upsert` supported as of work package WP-1, so
                # this branch is not yet exercised by any adapter -- see
                # `test_at_least_one_adapter_exercises_a_positive_control_mutation`
                # below, which only requires `insert`/`update` to be
                # non-vacuous.)
                upsert_entity = fresh_identifier("c12_upsert")
                index_name = fresh_identifier("uniq")
                adapter.create_entity(fx.developer_a, upsert_entity, {field_name: "text"})
                adapter.create_unique_index(fx.developer_a, upsert_entity, index_name, [field_name])
                affected = adapter.attempt_mutation(
                    fx.runtime_a, upsert_entity, operation,
                    values={field_name: marker}, where_field=None, where_value=None,
                )
            assert affected and affected >= 1, (
                f"{adapter.name}: {operation} is declared supported but attempt_mutation() reported "
                f"{affected!r} rows affected"
            )
        else:
            count_before = adapter.count(fx.runtime_a, entity)
            with pytest.raises(ConformanceDenial) as ei:
                adapter.attempt_mutation(
                    fx.runtime_a, entity, operation,
                    values={field_name: marker}, where_field=field_name, where_value=marker,
                )
            _assert_is_contract_code(ei.value.code)
            assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
                f"{adapter.name}: {operation} is not declared supported, so attempt_mutation() must "
                f"deny with CAPABILITY_UNSUPPORTED, got {ei.value.code!r}{_unclassified_hint(ei.value.code)}"
            )
            count_after = adapter.count(fx.runtime_a, entity)
            assert count_after == count_before, (
                f"{adapter.name}: undeclared {operation!r} attempt changed {entity}'s row count "
                f"({count_before} -> {count_after})"
            )


# --- 2. application_catalog declaration agrees with catalog_document() -----


def test_application_catalog_declaration_matches_observed_behavior(adapter, fx: Fixture):
    capability_document = adapter.capability_document()
    status = capability_document.get("capabilities", {}).get("application_catalog", {}).get("status")

    try:
        document = adapter.catalog_document(fx.runtime_a)
    except ConformanceDenial as denial:
        _assert_is_contract_code(denial.code)
        assert denial.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: application_catalog is declared {status!r}, so catalog_document() must "
            f"deny with CAPABILITY_UNSUPPORTED if it denies at all, got {denial.code!r}"
            f"{_unclassified_hint(denial.code)}"
        )
        # Only "unavailable" is consistent with a denial: "partial"
        # declares some real, working catalog behavior (review finding 6).
        assert status == "unavailable", (
            f"{adapter.name}: application_catalog is declared {status!r}, but catalog_document() was "
            f"denied (code {denial.code!r}) -- only status 'unavailable' is consistent with no catalog "
            "document at all"
        )
        return

    if document == CATALOG_SURFACE_ABSENT:
        assert status == "unavailable", (
            f"{adapter.name}: application_catalog is declared {status!r}, but catalog_document() reports "
            "CATALOG_SURFACE_ABSENT -- only status 'unavailable' is consistent with a structurally absent "
            "catalog surface"
        )
        return

    assert status in {"enabled", "partial"}, (
        f"{adapter.name}: catalog_document() returned a real document, but application_catalog is "
        f"declared {status!r}"
    )
    assert document.get("application_scope") == adapter.scope_of(fx.runtime_a).application_id, (
        f"{adapter.name}: catalog_document()'s application_scope disagrees with the session's own scope"
    )


# --- 3. reverse condition: undeclared query operators/mutations refuse ------
#
# design docs/design/R2DB_CCR13_STORAGE_V1.md section 4 "C-12 逆向き条件"
# (WP-5a): tests 1/2 above only check the "declared enabled => executes"
# direction. The opposite direction -- "an operation/operator this peer's
# own capability document does NOT declare must be refused with
# CAPABILITY_UNSUPPORTED before execution, state unchanged" -- went
# unchecked, and that is exactly the shape two real defects took (WP-2
# review B-1, WP-3 review blocker-1: `expected_revision`/`create_index`/
# `upsert`/`field_type`/`matches` all became executable through a shared
# validation boundary while their capability declarations still said
# `unavailable`/`unsupported`). The mutation-operation half of this reverse
# direction is already covered by test 1's own "else" branch above (an
# undeclared `atomic_mutation` operation is exercised and must refuse); this
# section covers the other half design section 4 names explicitly: query
# *operators* (`structured_query.operators`), which tests 1/2 never touch at
# all.


def test_undeclared_query_operators_are_refused_before_execution(adapter, fx: Fixture):
    contract = load_contract()
    all_operators = set(contract["structured_operations"]["allowed_query_operators"])
    capability_document = adapter.capability_document()
    declared = _declared_query_operators(capability_document)
    undeclared = all_operators - declared

    entity = fresh_identifier("c12_operator")
    field_name = "label"
    adapter.create_entity(fx.developer_a, entity, {field_name: "text"})
    adapter.insert(fx.runtime_a, entity, {field_name: "seed-value"})

    for operator in sorted(undeclared):
        # Presented to the same real query entry point `select_eq`/
        # `attempt_filter` already uses -- this finding was discovered
        # (WP-1 review, correction B-2/M-1) by presenting a real,
        # contract-shaped request rather than assuming a peer's behavior,
        # and this reverse condition exists specifically to keep catching
        # that class of gap, not just this one instance of it.
        count_before = adapter.count(fx.runtime_a, entity)
        value = None if operator == "is_null" else "seed-value"
        with pytest.raises(ConformanceDenial) as ei:
            adapter.attempt_filter(fx.runtime_a, entity, [field_name], field_name, operator, value)
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: {operator!r} is not declared in structured_query.operators, so attempt_filter() "
            f"must deny with CAPABILITY_UNSUPPORTED before execution, got {ei.value.code!r}"
            f"{_unclassified_hint(ei.value.code)}"
        )
        count_after = adapter.count(fx.runtime_a, entity)
        assert count_after == count_before, (
            f"{adapter.name}: undeclared operator {operator!r} attempt changed {entity}'s row count "
            f"({count_before} -> {count_after})"
        )


def test_at_least_one_adapter_has_an_undeclared_query_operator_to_refuse():
    # Vacuity guard symmetric to the one below: if every registered adapter
    # declared the contract's entire operator vocabulary, the reverse-
    # condition test above would never actually exercise its refusal branch
    # anywhere in the registry.
    contract = load_contract()
    all_operators = set(contract["structured_operations"]["allowed_query_operators"])
    saw_undeclared_operator = False
    for name, adapter_obj in registered_adapters().items():
        declared = _declared_query_operators(adapter_obj.capability_document())
        if all_operators - declared:
            saw_undeclared_operator = True
            break
    assert saw_undeclared_operator, (
        "every registered adapter declares the entire allowed_query_operators vocabulary; "
        "test_undeclared_query_operators_are_refused_before_execution is vacuous across the whole registry"
    )


# --- 4. registry-wide positive-control vacuity guard (not per-adapter) -----


def test_at_least_one_adapter_exercises_a_positive_control_mutation():
    # Symmetric to C-11's `test_at_least_one_adapter_returns_a_real_
    # catalog_document` (design review finding 9): if every registered
    # adapter declared none of insert/update/upsert as supported, test 1
    # above would never actually run its positive-control branch anywhere
    # in the whole registry -- the "declared -> succeeds" half of C-12
    # would be vacuously unexercised even though every per-adapter test
    # run "passed". This does not re-run the mutation itself (test 1
    # already does, per adapter); it only proves the declared-operations
    # set that drives that branch is non-empty for at least one adapter.
    contract = load_contract()
    saw_declared_operation = False
    for name, adapter_obj in registered_adapters().items():
        capability_document = adapter_obj.capability_document()
        declared = _declared_mutation_operations(capability_document, contract)
        if declared & set(_EXERCISED_OPERATIONS):
            saw_declared_operation = True
            break
    assert saw_declared_operation, (
        "no registered adapter declares any of insert/update/upsert as supported; the positive-control "
        "branch of test_declared_mutation_operations_match_observed_behavior is vacuous across the whole "
        "registry"
    )


# --- 4b. update reports the REAL number of rows affected, not the count of
#         batch operations submitted (Phase 8 WP-1 rework 2, 裁定 1) -------


def test_update_reports_the_real_number_of_rows_affected(adapter, fx: Fixture):
    """Phase 8 WP-1 rework 2 (裁定 1, 監督裁定 2026-09-07): port
    `adapter.py`'s own `attempt_mutation` docstring (`adapter.py::ConformanceAdapter.attempt_mutation`) is "return
    the number of rows affected". Test 1 above
    (`test_declared_mutation_operations_match_observed_behavior`) is a
    positive control for "update is declared supported", but its own
    recipe seeds and matches EXACTLY ONE row, so it cannot itself catch
    a peer that always reports a constant `1` regardless of how many
    rows a real update actually touched (a `len(batch_operations)`
    confusion, not `len(rows_affected)`) -- 1 row affected and "1
    operation submitted" are indistinguishable at that recipe's own
    scale. This test drives an update whose predicate matches TWO real
    rows (must report 2) and a second update whose predicate matches
    ZERO rows (must report 0), on every adapter that declares "update"
    supported -- the two values a single-operation-count confusion can
    never produce together (a constant would have to equal both 2 and 0).

    Mutation (裁定 1's own, measured this WP): reverting `MitateDB-api`'s
    in-process `_attempt_mutation_outcome`'s `dispatched_op` to
    `len(session.transact([item]))` turns BOTH assertions below red for
    `MitateDB-api` (2-row case reports 1, not 2; 0-row case reports 1,
    not 0) -- see this WP's own report for the observed pytest output."""
    contract = load_contract()
    capability_document = adapter.capability_document()
    declared = _declared_mutation_operations(capability_document, contract)
    if "update" not in declared:
        pytest.skip(f"{adapter.name}: does not declare 'update' supported")

    entity = fresh_identifier("c12_update_rowcount")
    group_field = "group"
    adapter.create_entity(fx.developer_a, entity, {group_field: "text", "tag": "text"})

    for _ in range(2):
        affected = adapter.attempt_mutation(
            fx.runtime_a, entity, "insert",
            values={group_field: "match", "tag": "orig"}, where_field=None, where_value=None,
        )
        assert affected == 1, f"{adapter.name}: seed insert reported affected={affected!r}, expected 1"

    observed_affected_counts: list[int] = []

    affected_two = adapter.attempt_mutation(
        fx.runtime_a, entity, "update",
        values={"tag": "changed"}, where_field=group_field, where_value="match",
    )
    observed_affected_counts.append(affected_two)
    assert affected_two == 2, (
        f"{adapter.name}: an update whose predicate matches 2 real rows reported affected={affected_two!r}, "
        "expected 2 (port adapter.py::attempt_mutation: 'return the number of rows affected')"
    )

    affected_zero = adapter.attempt_mutation(
        fx.runtime_a, entity, "update",
        values={"tag": "changed-again"}, where_field=group_field, where_value="does-not-exist",
    )
    observed_affected_counts.append(affected_zero)
    assert affected_zero == 0, (
        f"{adapter.name}: an update whose predicate matches 0 rows reported affected={affected_zero!r}, "
        "expected 0"
    )

    assert len(observed_affected_counts) >= 1, (
        f"{adapter.name}: this test observed zero affected-count values -- would be vacuous"
    )


# --- 5. cross_entity_mutation declaration agreement (phase 3.5 WP-3) -------
#
# design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md section 3:
# "現行 C-12 は cross_entity を一切読まない" (WP-0 measurement) -- these two
# tests close that gap, using the SAME "declared -> executes / undeclared ->
# CAPABILITY_UNSUPPORTED before execution" shape test 1 above already
# establishes for atomic_mutation, applied to attempt_cross_entity_batch().
#
# The reverse (negative) direction -- "declared NOT provided => refused" --
# is scoped to adapters whose capability-unavailable form is a real
# `ConformanceDenial` (design section 3's own restriction): an in-process
# peer's absence form is `SurfaceAbsent`, port-defined and not itself a
# `ConformanceDenial` this direction's "refused with CAPABILITY_UNSUPPORTED"
# shape can assert against -- that peer's own absence claim is independently
# verified instead by C-16 V5's own SurfaceAbsent structural re-check
# (`conformance-tests/test_c16_cross_entity_atomicity.py`), not duplicated
# here (CONDITIONS.md's C-12/C-16 disclosure records this split explicitly).


def _declared_cross_entity_mutation(capability_document: dict, contract: dict) -> tuple[str, set[str], set[str]]:
    entry = capability_document.get("capabilities", {}).get("cross_entity_mutation", {})
    status = entry.get("status", "unavailable")
    if status == "enabled":
        # Mirrors _declared_mutation_operations' own "enabled with no
        # per-operation operations key" handling above (phase 3.5 WP-3
        # review m-5): a peer declaring the capability wholesale enabled,
        # without narrowing it via an `operations` list, declares the
        # FULL contract vocabulary for a ScopedMutation's own `operation`
        # enum -- never silently treated as an empty declared set (which
        # would leave this direction entirely untested for such a peer).
        operations = set(
            entry.get("operations", contract["definitions"]["ScopedMutation"]["properties"]["operation"]["enum"])
        )
        return status, operations, set(entry.get("unsupported", []))
    if status == "partial":
        return status, set(entry.get("operations", [])), set(entry.get("unsupported", []))
    return status, set(), set()


def test_declared_cross_entity_mutation_operations_match_observed_behavior(adapter, fx: Fixture):
    contract = load_contract()
    capability_document = adapter.capability_document()
    status, declared_ops, declared_unsupported = _declared_cross_entity_mutation(capability_document, contract)

    entity_a = fresh_identifier("c12ce_a")
    adapter.create_entity(fx.developer_a, entity_a, {"label": "text"})

    if status not in ("enabled", "partial"):
        marker = f"c12ce-absent-{uuid.uuid4().hex[:8]}"
        # M-3 (phase 3.5 WP-3 review): the same "refused ... and leaves
        # state unchanged" bracketing every other negative-direction check
        # in this file already uses (see test 1's own "else" branch above,
        # `test_c12_capability_agreement.py::test_declared_mutation_operations_match_observed_behavior`) -- entity_a is freshly created and untouched,
        # so its row count must still be 0 whichever honest form (below)
        # this adapter takes.
        count_before = adapter.count(fx.runtime_a, entity_a)

        def _attempt() -> None:
            adapter.attempt_cross_entity_batch(
                fx.runtime_a, [ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker})],
            )

        try:
            _attempt()
        except SurfaceAbsent:
            # design section 3: this direction is scoped to wire-surface
            # adapters -- see this section's own module-level comment.
            return
        except ConformanceDenial as denial:
            _assert_is_contract_code(denial.code)
            assert denial.code == "CAPABILITY_UNSUPPORTED", (
                f"{adapter.name}: cross_entity_mutation is declared {status!r}, so attempt_cross_entity_batch() "
                f"must deny with CAPABILITY_UNSUPPORTED if it denies at all, got {denial.code!r}"
                f"{_unclassified_hint(denial.code)}"
            )
            assert adapter.count(fx.runtime_a, entity_a) == count_before, (
                f"{adapter.name}: {entity_a!r} row count changed despite cross_entity_mutation being declared "
                f"{status!r} and the attempt being refused"
            )
            return
        else:
            raise AssertionError(
                f"{adapter.name}: cross_entity_mutation is declared {status!r}, but attempt_cross_entity_batch() "
                "executed outright"
            )

    for operation in sorted(declared_ops):
        marker = f"c12ce-{operation}-{uuid.uuid4().hex[:8]}"
        if operation == "insert":
            affected = adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker}),
            ])
        elif operation == "update":
            adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker}),
            ])
            affected = adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(
                    operation="update", entity=entity_a, values={"label": marker + "-updated"},
                    where_field="label", where_value=marker,
                ),
            ])
        elif operation == "delete":
            adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(operation="insert", entity=entity_a, values={"label": marker}),
            ])
            affected = adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(
                    operation="delete", entity=entity_a, where_field="label", where_value=marker,
                    destructive=True, confirmation=VALID_CONFIRMATION,
                ),
            ])
        else:
            # upsert: no currently-registered adapter declares this
            # supported for cross_entity_mutation (P35-D3) -- the loop
            # still iterates over whatever `declared_ops` a future adapter
            # names, but there is no positive-control shape to construct
            # for an operation this WP's own design scope excludes.
            continue
        assert affected and affected >= 1, (
            f"{adapter.name}: cross-entity {operation} is declared supported but attempt_cross_entity_batch() "
            f"reported {affected!r} rows affected"
        )

    for operation in sorted(declared_unsupported):
        marker = f"c12ce-unsupported-{operation}-{uuid.uuid4().hex[:8]}"
        # M-3: same "refused ... and leaves state unchanged" bracketing
        # as the unavailable-direction branch above -- entity_a's row
        # count (whatever it is at this point in the loop) must be
        # unchanged by a refused attempt.
        count_before = adapter.count(fx.runtime_a, entity_a)
        with pytest.raises(ConformanceDenial) as ei:
            adapter.attempt_cross_entity_batch(fx.runtime_a, [
                ScopedBatchOperation(operation=operation, entity=entity_a, values={"label": marker}),
            ])
        _assert_is_contract_code(ei.value.code)
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: cross-entity {operation!r} is declared unsupported, so attempt_cross_entity_batch() "
            f"must deny with CAPABILITY_UNSUPPORTED, got {ei.value.code!r}{_unclassified_hint(ei.value.code)}"
        )
        assert adapter.count(fx.runtime_a, entity_a) == count_before, (
            f"{adapter.name}: {entity_a!r} row count changed despite cross-entity {operation!r} being declared "
            "unsupported and the attempt being refused"
        )


def test_at_least_one_adapter_declares_a_cross_entity_mutation_operation():
    # Vacuity guard symmetric to test_at_least_one_adapter_exercises_a_
    # positive_control_mutation above: if no registered adapter declared
    # cross_entity_mutation enabled/partial, the positive-control branch of
    # test_declared_cross_entity_mutation_operations_match_observed_behavior
    # would never actually run anywhere in the registry.
    contract = load_contract()
    saw_declared_operation = False
    for _name, adapter_obj in registered_adapters().items():
        status, declared_ops, _unsupported = _declared_cross_entity_mutation(adapter_obj.capability_document(), contract)
        if status in ("enabled", "partial") and declared_ops:
            saw_declared_operation = True
            break
    assert saw_declared_operation, (
        "no registered adapter declares any cross_entity_mutation operation as supported; the "
        "positive-control branch of test_declared_cross_entity_mutation_operations_match_observed_behavior "
        "is vacuous across the whole registry"
    )
