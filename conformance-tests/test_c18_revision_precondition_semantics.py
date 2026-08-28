"""C-18 -- revision precondition semantics (SI-05, SI-09, SI-11).

design: docs/design/R2DB_CCR13_STORAGE_V1.md section 4 "C-18 revision
precondition 意味論", registered in `conformance-tests/CONDITIONS.md`. Every
test here carries @pytest.mark.condition("C-18") via the module-level
`pytestmark`.

Structure: every test function branches once, at its top, on whether this
adapter's peer declares `revision_preconditions: enabled`. The `enabled`
branch performs the real behavioral assertion the test's name describes.
The *not*-enabled branch (currently only `MitateDB-api`) does not skip --
design principle 4 and this repository's own "skip is fail" rule both
forbid that. Unlike C-17's unavailable side (which needs `SurfaceAbsent`,
since `create_unique_index` truly has no receiving call on that peer), this
condition's unavailable side is a *real, present* denial: `MitateDB-api`'s
`transact()` dispatcher is a genuine entry point for `expected_revision`
(the same one `attempt_mutation`'s `upsert`/`expected_revision` handling
already presents it to), and refuses it with `CAPABILITY_UNSUPPORTED`
before touching any row (docs/design/CONFORMANCE_ADAPTER_V1.md section 12,
correction B-2, and the accompanying `cell.py` fix that closed the
allowlist gap that used to let it through silently). This is the "受理面を
持つpeerなら実行前CAPABILITY_UNSUPPORTED + 状態不変" half of the design's own
parenthetical for the unavailable side -- so every test function below
makes a genuine, real assertion against every registered adapter.
"""
from __future__ import annotations

import pytest

from adapter import (
    ConformanceDenial,
    Fixture,
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    fresh_identifier,
    load_contract_error_codes,
)

pytestmark = pytest.mark.condition("C-18")


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


def _revision_preconditions_enabled(adapter) -> bool:
    document = adapter.capability_document()
    return document.get("capabilities", {}).get("revision_preconditions", {}).get("status") == "enabled"


def _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx: Fixture) -> None:
    entity = fresh_identifier("c18_absent")
    adapter.create_entity(fx.developer_a, entity, {"label": "text"})
    adapter.attempt_mutation(fx.runtime_a, entity, "insert", values={"label": "seed"}, where_field=None, where_value=None)
    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "update",
            values={"label": "changed"}, where_field="label", where_value="seed",
            expected_revision="deadbeef-does-not-matter",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
        f"{adapter.name}: declares revision_preconditions unavailable; a real expected_revision attempt "
        f"was refused with {ei.value.code!r}, expected CAPABILITY_UNSUPPORTED"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, (
        f"{adapter.name}: state changed despite a refused expected_revision mutation"
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["label"], "label", "seed")
    assert rows, f"{adapter.name}: seeded row was mutated despite a refused expected_revision update"


def _seed_row(adapter, fx: Fixture, entity: str, **values):
    affected, addresses = adapter.attempt_mutation_with_addresses(
        fx.runtime_a, entity, "insert", values=values, where_field=None, where_value=None,
    )
    assert affected == 1 and addresses
    return addresses[0]["address"]


def _revision_of(adapter, fx: Fixture, entity: str, field: str, value) -> str:
    items, revisions = adapter.query_with_revisions(fx.runtime_a, entity, ["marker"], field, value)
    assert len(items) == 1, f"{adapter.name}: expected exactly one row matching {field}={value!r}, got {len(items)}"
    return revisions[0]


# --- 1. mismatch -> PRECONDITION_FAILED -------------------------------------


def test_revision_mismatch_is_precondition_failed(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_mismatch")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    _seed_row(adapter, fx, entity, marker="m")
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "update", values={"marker": "changed"},
            where_field="marker", where_value="m", expected_revision="not-the-real-revision",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "PRECONDITION_FAILED", f"{adapter.name}: revision mismatch: {ei.value.code!r}, expected PRECONDITION_FAILED"
    rows = adapter.select_eq(fx.runtime_a, entity, ["marker"], "marker", "m")
    assert rows, f"{adapter.name}: row was mutated despite a mismatched precondition"


# --- 2. predicate matches zero rows + precondition -> NOT_FOUND ------------


def test_zero_row_predicate_with_precondition_is_not_found(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_zerorow")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "update", values={"marker": "x"},
            where_field="marker", where_value="does-not-exist", expected_revision="anything",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "NOT_FOUND", f"{adapter.name}: 0-row predicate + precondition: {ei.value.code!r}, expected NOT_FOUND"


# --- 3. insert + expected_revision -> VALIDATION_FAILED --------------------


def test_insert_with_expected_revision_is_validation_failed(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_insertrev")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "insert", values={"marker": "x"},
            where_field=None, where_value=None, expected_revision="anything",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "VALIDATION_FAILED", f"{adapter.name}: insert + expected_revision: {ei.value.code!r}, expected VALIDATION_FAILED"
    assert adapter.count(fx.runtime_a, entity) == count_before, f"{adapter.name}: state changed despite a refused insert+precondition"


# --- 4/5. own-row revision changes; other row's revision does not ---------


def test_revision_changes_on_own_row_mutation_and_not_on_others(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_selfother")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text", "val": "text"})
    _seed_row(adapter, fx, entity, marker="one", val="v1")
    _seed_row(adapter, fx, entity, marker="two", val="v2")

    revision_one_before = _revision_of(adapter, fx, entity, "marker", "one")
    revision_two_before = _revision_of(adapter, fx, entity, "marker", "two")

    adapter.attempt_mutation(fx.runtime_a, entity, "update", values={"val": "v1-changed"}, where_field="marker", where_value="one")

    revision_one_after = _revision_of(adapter, fx, entity, "marker", "one")
    revision_two_after = _revision_of(adapter, fx, entity, "marker", "two")

    assert revision_one_after != revision_one_before, f"{adapter.name}: mutated row's own revision did not change"
    assert revision_two_after == revision_two_before, f"{adapter.name}: an untouched row's revision changed"


# --- 6. no precondition, 0-row update/delete still succeeds, affected 0 ---


def test_precondition_free_zero_row_mutation_succeeds_with_affected_zero(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_zeroaffected")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    affected_update = adapter.attempt_mutation(
        fx.runtime_a, entity, "update", values={"marker": "x"}, where_field="marker", where_value="does-not-exist",
    )
    assert affected_update == 0, f"{adapter.name}: precondition-free 0-row update should succeed with affected 0, got {affected_update!r}"
    # `attempt_mutation` never supplies destructive confirmation (item 11's
    # own test exercises that dimension); a real, *properly confirmed*
    # delete needs the dedicated `delete()` port method instead.
    affected_delete = adapter.delete(
        fx.runtime_a, entity, "marker", "does-not-exist", destructive=True, confirmation=VALID_CONFIRMATION,
    )
    assert affected_delete == 0, f"{adapter.name}: precondition-free 0-row delete should succeed with affected 0, got {affected_delete!r}"


# --- 7. query revisions are index-aligned with items ------------------------


def test_query_revisions_are_index_aligned_with_items(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_aligned")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text", "val": "text"})
    for i in range(3):
        _seed_row(adapter, fx, entity, marker="shared", val=f"v{i}")

    items, revisions = adapter.query_with_revisions(fx.runtime_a, entity, ["val"], "marker", "shared")
    assert len(items) == 3, f"{adapter.name}: expected 3 seeded rows, got {len(items)}"
    assert revisions is not None and len(revisions) == len(items), (
        f"{adapter.name}: revisions ({revisions!r}) is not index-aligned with items ({items!r})"
    )
    assert len(set(revisions)) == len(revisions), f"{adapter.name}: revisions are not distinct per row: {revisions!r}"
    for item, revision in zip(items, revisions):
        independently_observed = _revision_of(adapter, fx, entity, "val", item["val"])
        assert independently_observed == revision, (
            f"{adapter.name}: batch-query revision for {item!r} ({revision!r}) disagrees with an independent, "
            f"single-row observation ({independently_observed!r})"
        )


# --- 8. upsert + precondition never resolves to insert ----------------------


def test_upsert_with_precondition_never_resolves_to_insert(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_upsertprecond")
    adapter.create_entity(fx.developer_a, entity, {"tag": "text"})
    adapter.create_unique_index(fx.developer_a, entity, fresh_identifier("uniq"), ["tag"])

    count_before = adapter.count(fx.runtime_a, entity)
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "upsert", values={"tag": "brand-new-key"},
            where_field=None, where_value=None, expected_revision="anything",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "NOT_FOUND", (
        f"{adapter.name}: upsert+precondition against a non-matching key: {ei.value.code!r}, expected NOT_FOUND"
    )
    assert adapter.count(fx.runtime_a, entity) == count_before, (
        f"{adapter.name}: upsert+precondition against a non-matching key inserted a row -- a precondition must "
        "never be silently satisfied by resolving to insert"
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["tag"], "tag", "brand-new-key")
    assert not rows, f"{adapter.name}: a row was inserted for the non-matching upsert+precondition key"


# --- 9. predicate matches several rows; precondition still changes exactly one


def test_multi_row_predicate_with_precondition_changes_exactly_the_named_row(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_multirow")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text", "val": "text"})
    addr1 = _seed_row(adapter, fx, entity, marker="m1", val="shared")
    addr2 = _seed_row(adapter, fx, entity, marker="m2", val="shared")
    addr3 = _seed_row(adapter, fx, entity, marker="m3", val="shared")
    revision2 = _revision_of(adapter, fx, entity, "marker", "m2")

    affected = adapter.attempt_mutation(
        fx.runtime_a, entity, "update", values={"marker": "only-m2-touched"},
        where_field="val", where_value="shared", expected_revision=revision2,
    )
    assert affected == 1, f"{adapter.name}: a 3-row predicate + 1-row-precondition update reported affected {affected!r}, expected 1"

    unchanged_markers = {
        row["marker"] for row in adapter.select_eq(fx.runtime_a, entity, ["marker"], "val", "shared")
    } | {row["marker"] for row in adapter.select_eq(fx.runtime_a, entity, ["marker"], "marker", "only-m2-touched")}
    assert "m1" in unchanged_markers and "m3" in unchanged_markers, (
        f"{adapter.name}: sibling rows matching the same predicate were affected: {unchanged_markers!r}"
    )
    assert "only-m2-touched" in unchanged_markers and "m2" not in unchanged_markers, (
        f"{adapter.name}: the revision-named row was not the one actually updated: {unchanged_markers!r}"
    )
    del addr1, addr2, addr3  # addresses only needed to force real, distinct rows above


# --- 10. empty values + precondition -> VALIDATION_FAILED ------------------


def test_empty_values_with_precondition_is_validation_failed(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_emptyvalues")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    _seed_row(adapter, fx, entity, marker="m")
    revision = _revision_of(adapter, fx, entity, "marker", "m")

    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "update", values={},
            where_field="marker", where_value="m", expected_revision=revision,
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "VALIDATION_FAILED", (
        f"{adapter.name}: empty values + precondition: {ei.value.code!r}, expected VALIDATION_FAILED "
        "(a precondition must never be silently discarded by the empty-values no-op branch)"
    )
    # Precondition-free empty values remains the pre-existing no-op success
    # (this is the branch item 10 exists specifically to distinguish from).
    affected = adapter.attempt_mutation(fx.runtime_a, entity, "update", values={}, where_field="marker", where_value="m")
    assert affected == 1, f"{adapter.name}: precondition-free empty-values update on a matching row should succeed as a no-op"


# --- 11. destructive confirmation is evaluated before any precondition ----


def test_destructive_confirmation_is_checked_before_precondition(adapter, fx: Fixture):
    if not _revision_preconditions_enabled(adapter):
        _assert_expected_revision_is_capability_unsupported_and_state_unchanged(adapter, fx)
        return

    entity = fresh_identifier("c18_destructive")
    adapter.create_entity(fx.developer_a, entity, {"marker": "text"})
    _seed_row(adapter, fx, entity, marker="m")

    # An unconfirmed delete carrying an expected_revision that would *also*
    # fail on its own merits (a bogus value) must be refused for the
    # destructive-confirmation reason, not a revision-related one --
    # otherwise a client could use a bogus precondition to probe whether a
    # destructive operation would have gone through, without ever having to
    # supply a real confirmation.
    with pytest.raises(ConformanceDenial) as ei:
        adapter.attempt_mutation(
            fx.runtime_a, entity, "delete", values=None,
            where_field="marker", where_value="m", expected_revision="a-bogus-revision-value",
        )
    _assert_is_contract_code(ei.value.code)
    assert ei.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED", (
        f"{adapter.name}: unconfirmed delete + precondition: {ei.value.code!r}, expected "
        "DESTRUCTIVE_CONFIRMATION_REQUIRED (the confirmation check must precede precondition evaluation)"
    )
    rows = adapter.select_eq(fx.runtime_a, entity, ["marker"], "marker", "m")
    assert rows, f"{adapter.name}: row was deleted despite missing destructive confirmation"
